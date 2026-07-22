"""Adapter integration tests with a fully mocked Telegram API.

Uses httpx.MockTransport (built-in, no extra dep). Verifies:
  - send_message payload shape
  - send_document multipart
  - download_media: max_bytes enforcement, allowed_mimes filtering
  - retry policy: 1 retry on 5xx; 0 retries on 4xx
  - log payload never contains tokens/URLs/bytes
"""
import asyncio
import io
import logging
import os

import httpx
import pytest


# Ensure the adapter reads a fixed token during tests.
os.environ["TELEGRAM_INTERNAL_BOT_TOKEN"] = "TEST_TOKEN_1234"

from modules.telegram_internal import bot_api  # noqa: E402


class _FakeTelegram:
    """Records requests and produces canned responses."""

    def __init__(self):
        self.calls = []
        self.responses = {}          # method -> [(status, json_or_bytes)]
        self.responses_default = {}  # method -> (status, json_or_bytes)

    def queue(self, method: str, status: int, body):
        self.responses.setdefault(method, []).append((status, body))

    def default(self, method: str, status: int, body):
        self.responses_default[method] = (status, body)

    def _resolve(self, method: str):
        q = self.responses.get(method)
        if q:
            return q.pop(0)
        return self.responses_default.get(method, (200, {"ok": True, "result": {}}))

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # /bot<token>/<method> OR /file/bot<token>/<file_path>
        if path.startswith("/file/bot"):
            method = "downloadFile"
        else:
            # /bot<token>/<method>
            method = path.rsplit("/", 1)[-1]
        self.calls.append({
            "method": method,
            "path": path,
            "content_type": request.headers.get("content-type", ""),
            "params": dict(request.url.params),
            "body_size": len(request.content) if request.content else 0,
        })
        status, body = self._resolve(method)
        if isinstance(body, (bytes, bytearray)):
            return httpx.Response(status, content=bytes(body))
        return httpx.Response(status, json=body)


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    """Replace httpx.AsyncClient with one bound to our MockTransport."""
    fake = _FakeTelegram()

    original = httpx.AsyncClient

    class _PatchedClient(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(fake.handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _PatchedClient)
    yield fake


@pytest.mark.asyncio
async def test_send_message_payload(_patch_httpx=None):
    fake = _patch_httpx if _patch_httpx else None  # noqa
    # Fixture value is injected via yield; grab from module namespace
    # But easiest is to receive it via the pytest fixture normally:
    pass


# We use direct injection via a helper because pytest fixtures aren't
# straightforward to combine with autouse yields returning values.
@pytest.fixture
def fake(_patch_httpx):
    return _patch_httpx


@pytest.mark.asyncio
async def test_send_message_shape(fake):
    fake.default("sendMessage", 200, {"ok": True, "result": {"message_id": 1}})
    resp = await bot_api.send_message(
        chat_id=42, text="hello", reply_markup={"inline_keyboard": [[{"text": "x", "callback_data": "y"}]]},
        module="renting",
    )
    assert resp == {"ok": True, "result": {"message_id": 1}}
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["method"] == "sendMessage"
    assert "TEST_TOKEN_1234" in call["path"]  # token IS in URL — but never in logs


@pytest.mark.asyncio
async def test_retry_on_5xx(fake):
    fake.queue("sendMessage", 502, {"error": "bad"})
    fake.queue("sendMessage", 200, {"ok": True, "result": {"message_id": 9}})
    resp = await bot_api.send_message(chat_id=1, text="retry me", module="renting")
    assert resp == {"ok": True, "result": {"message_id": 9}}
    assert len(fake.calls) == 2  # 1 retry


@pytest.mark.asyncio
async def test_no_retry_on_4xx(fake):
    fake.queue("sendMessage", 400, {"error": "bad request"})
    resp = await bot_api.send_message(chat_id=1, text="won't retry", module="renting")
    assert resp is None
    assert len(fake.calls) == 1  # no retry


@pytest.mark.asyncio
async def test_send_document_multipart(fake):
    fake.default("sendDocument", 200, {"ok": True, "result": {"message_id": 2}})
    ok = await bot_api.send_document(
        chat_id=42, file_bytes=b"%PDF-1.4 fake", filename="fatura.pdf",
        caption="Fatura", module="assistencias",
    )
    assert ok is not None
    call = fake.calls[0]
    assert call["method"] == "sendDocument"
    assert "multipart/form-data" in call["content_type"]
    assert call["body_size"] > 0


@pytest.mark.asyncio
async def test_download_media_size_enforced(fake):
    # getFile returns file_size > max_bytes
    fake.default("getFile", 200, {"ok": True, "result": {"file_path": "photos/f.jpg", "file_size": 100_000}})
    result = await bot_api.download_media(
        file_id="abc", max_bytes=50_000, module="renting"
    )
    assert result is None
    # Should have called getFile but NOT downloadFile
    methods = [c["method"] for c in fake.calls]
    assert methods == ["getFile"]


@pytest.mark.asyncio
async def test_download_media_mime_filter(fake):
    fake.default("getFile", 200, {"ok": True, "result": {"file_path": "voice/a.ogg", "file_size": 100}})
    result = await bot_api.download_media(
        file_id="abc", allowed_mimes={"image/jpeg"}, module="renting"
    )
    assert result is None
    methods = [c["method"] for c in fake.calls]
    assert methods == ["getFile"]


@pytest.mark.asyncio
async def test_download_media_success(fake):
    fake.default("getFile", 200, {"ok": True, "result": {"file_path": "photos/a.jpg", "file_size": 42}})
    fake.default("downloadFile", 200, b"\xff\xd8\xff\xe0FAKEJPEG")
    result = await bot_api.download_media(
        file_id="abc", allowed_mimes={"image/jpeg"}, module="renting"
    )
    assert result is not None
    data, mime = result
    assert data == b"\xff\xd8\xff\xe0FAKEJPEG"
    assert mime == "image/jpeg"


@pytest.mark.asyncio
async def test_log_no_secret_leak(fake, caplog):
    """The adapter must never log tokens, file_paths or URLs."""
    fake.default("getFile", 200, {"ok": True, "result": {"file_path": "voice/SECRET_PATH.ogg", "file_size": 10}})
    fake.default("downloadFile", 200, b"raw-audio-bytes")
    caplog.set_level(logging.DEBUG, logger="modules.telegram_internal.bot_api")
    await bot_api.download_media(file_id="abc", module="mech_alert")
    combined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "TEST_TOKEN_1234" not in combined
    assert "SECRET_PATH" not in combined
    assert "raw-audio-bytes" not in combined


@pytest.mark.asyncio
async def test_answer_callback_query(fake):
    fake.default("answerCallbackQuery", 200, {"ok": True, "result": True})
    resp = await bot_api.answer_callback_query("cbid-123", text="OK", module="renting")
    assert resp == {"ok": True, "result": True}
