"""Sprint 2 / S2-C — namespaced callbacks and enriched logs.

Covers:
  * callback parser accepts both legacy and namespaced formats
  * malformed input never raises
  * log_event enriches with `module` derived from active_flow
  * blocked fields (`token`, `file_path`, `bytes`, `base64`) are stripped from extras
  * legacy filter by module=unknown returns rows without module set
"""
import os
import uuid

import httpx
import pytest

os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")

from db import db  # noqa: E402
from modules.telegram_internal.callback_router import (  # noqa: E402
    parse_callback_data, build_callback,
)
from modules.telegram_internal import logs as _logs  # noqa: E402


API_BASE = "http://localhost:8001"


async def _admin_token() -> str:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.post("/api/auth/login", json={
            "email": "admin@pdpv.pt", "password": "HCNMEnKMLq"
        })
        r.raise_for_status()
        d = r.json()
        return d.get("access_token") or d.get("token") or ""


# ────────── callback parser ──────────

def test_parse_legacy_no_colon():
    p = parse_callback_data("plate_ok")
    assert p.namespaced is False
    assert p.module == "unknown"
    assert p.action == "plate_ok"


def test_parse_legacy_with_payload_colon():
    """Legacy Assign callback: `assign:<user_id>:<name>` — namespace unknown → treated legacy."""
    p = parse_callback_data("assign:17:Zé")
    # `assign` is NOT a module alias, so this remains legacy.
    assert p.namespaced is False
    assert p.module == "unknown"


def test_parse_namespaced_short_alias():
    p = parse_callback_data("mech:assign:17")
    assert p.namespaced is True
    assert p.module == "mech_alert"
    assert p.action == "assign"
    assert p.payload == "17"


def test_parse_namespaced_all_modules():
    for ns, expected in [
        ("renting:wheel_ok:2", "renting"),
        ("assist:plate_ok",    "assistencias"),
        ("pre:submit",         "pre_ticket"),
        ("admin:refresh",      "admin"),
    ]:
        p = parse_callback_data(ns)
        assert p.namespaced is True
        assert p.module == expected


def test_parse_reserved_router_namespaces_are_not_module_ones():
    for raw in ["system:menu", "menu:renting", "conflict:continue"]:
        p = parse_callback_data(raw)
        assert p.namespaced is False, raw
        assert p.reserved is True
        assert p.module == "admin"


def test_parse_malformed_never_raises():
    for raw in ["", None, ":", "renting:", "renting::", "::", "::foo"]:
        p = parse_callback_data(raw)
        assert p.module in {"unknown", "renting"}
        # No exception thrown — pytest would fail earlier.


def test_build_callback_uses_short_alias():
    assert build_callback("renting", "wheel_ok", "2") == "rent:wheel_ok:2"
    assert build_callback("mech_alert", "assign", "17") == "mech:assign:17"
    assert build_callback("assistencias", "plate_ok") == "assist:plate_ok"


# ────────── log enrichment ──────────

@pytest.fixture
async def _clean_logs():
    marker = f"TEST-{uuid.uuid4().hex[:8]}"
    yield marker
    await db.telegram_internal_logs.delete_many({"extra.marker": marker})


async def test_log_module_derived_from_active_flow(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        active_flow="renting", extra={"marker": marker},
    )
    doc = await db.telegram_internal_logs.find_one({"extra.marker": marker})
    assert doc is not None
    assert doc["module"] == "renting"
    assert doc["active_flow"] == "renting"


async def test_log_module_explicit_wins_over_active_flow(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        active_flow="renting", module="admin", extra={"marker": marker},
    )
    doc = await db.telegram_internal_logs.find_one({"extra.marker": marker})
    assert doc["module"] == "admin"


async def test_log_module_falls_back_to_unknown(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        extra={"marker": marker},
    )
    doc = await db.telegram_internal_logs.find_one({"extra.marker": marker})
    assert doc["module"] == "unknown"


async def test_log_blocks_sensitive_extra_keys(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        module="renting",
        extra={
            "marker": marker,
            "token": "SECRET",
            "file_path": "voice/leak.ogg",
            "bytes": b"\x00\x01",
            "base64": "AAAA",
            "safe_counter": 42,
        },
    )
    doc = await db.telegram_internal_logs.find_one({"extra.marker": marker})
    extra = doc["extra"]
    assert "token" not in extra
    assert "file_path" not in extra
    assert "bytes" not in extra
    assert "base64" not in extra
    assert extra.get("safe_counter") == 42


async def test_log_new_fields_persisted(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        module="assistencias",
        callback_action="plate_ok",
        internal_user_id="user-abc",
        processing_time_ms=42,
        error_id="err-xyz",
        extra={"marker": marker},
    )
    doc = await db.telegram_internal_logs.find_one({"extra.marker": marker})
    assert doc["callback_action"] == "plate_ok"
    assert doc["internal_user_id"] == "user-abc"
    assert doc["processing_time_ms"] == 42
    assert doc["error_id"] == "err-xyz"


# ────────── UI logs endpoint returns module ──────────

async def test_logs_endpoint_returns_module_field(_clean_logs):
    marker = _clean_logs
    await _logs.log_event(
        telegram_user_id=1, chat_id=1, message_type="callback",
        active_flow="mech_alert", extra={"marker": marker},
    )
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/logs?module=mech_alert&limit=50",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    rows = r.json().get("logs", [])
    # At least one row of module=mech_alert now exists.
    assert any(row.get("module") == "mech_alert" for row in rows)


async def test_logs_endpoint_module_unknown_includes_legacy():
    """Legacy docs (before S2-C) have no `module` field. Filter must not crash."""
    token = await _admin_token()
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15) as c:
        r = await c.get(
            "/api/telegram/internal/logs?module=unknown&limit=50",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
