"""Static guard: outbound Telegram calls must go through the unified adapter.

Any runtime module that reads TELEGRAM_RENTING_BOT_TOKEN,
TELEGRAM_ALERTS_BOT_TOKEN or TELEGRAM_ASSISTENCIAS_BOT_TOKEN inside a function
body is an error. The env vars themselves are allowed to remain as
top-level `BOT_TOKEN = os.environ.get(...)` LEGACY placeholders (rollback
support) but they must be marked and unused.

This test scans /app/backend and fails if any *new* uses appear.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path("/app/backend")

LEGACY_TOKENS = [
    "TELEGRAM_RENTING_BOT_TOKEN",
    "TELEGRAM_ALERTS_BOT_TOKEN",
    "TELEGRAM_ASSISTENCIAS_BOT_TOKEN",
    "TELEGRAM_ASSISTENCIAS_WEBHOOK_SECRET",
]

# Files that are legitimate keepers of the placeholder (top-level LEGACY line).
ALLOWLIST_PLACEHOLDERS = {
    "modules/renting/service.py",
    "modules/telegram_alerts/service.py",
    "modules/assistencias/bot_api.py",
}

EXCLUDE_DIRS = {"__pycache__", "tests", "scripts", ".git"}


def _iter_py_files():
    for p in BACKEND.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def test_no_legacy_token_reads_outside_allowlist():
    """Legacy token names must appear ONLY as top-level placeholders in the allowlist."""
    offences: list[str] = []
    for py in _iter_py_files():
        rel = str(py.relative_to(BACKEND))
        text = py.read_text(encoding="utf-8", errors="ignore")
        for tok in LEGACY_TOKENS:
            if tok not in text:
                continue
            # Only allow one occurrence in each allowlisted file, and only in
            # the top-level BOT_TOKEN/WEBHOOK_SECRET assignment.
            if rel in ALLOWLIST_PLACEHOLDERS:
                # Count occurrences; must be at most one, at module top.
                lines = [i for i, ln in enumerate(text.splitlines(), start=1)
                         if tok in ln]
                for ln in lines:
                    # Must be a top-level assignment (`= os.environ.get(...)`).
                    line_text = text.splitlines()[ln - 1]
                    if not re.match(
                        r'^[A-Z_]+ = os\.environ\.get\(["\']' + tok, line_text
                    ):
                        offences.append(f"{rel}:{ln} — legacy token used beyond placeholder")
            else:
                for i, ln in enumerate(text.splitlines(), start=1):
                    if tok in ln:
                        offences.append(f"{rel}:{i} — legacy token reference outside allowlist")
    assert not offences, "Legacy token misuse detected:\n" + "\n".join(offences)


def test_no_direct_telegram_api_url_in_runtime():
    """No runtime module (outside allowlist) may build https://api.telegram.org URLs.

    All outbound calls MUST go through modules.telegram_internal.bot_api.
    """
    # Allow bot_api itself, plus the LEGACY constants (TELEGRAM_API = "..." string).
    allow_url_files = {
        "modules/telegram_internal/bot_api.py",
        "modules/renting/service.py",   # placeholder constant only
        "modules/telegram_alerts/service.py",
        "modules/assistencias/bot_api.py",
        "modules/telegram/service.py",  # legacy client bot (deprecated but kept)
    }
    pattern = re.compile(r'https?://api\.telegram\.org')
    offences: list[str] = []
    for py in _iter_py_files():
        rel = str(py.relative_to(BACKEND))
        if rel in allow_url_files:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for i, ln in enumerate(text.splitlines(), start=1):
            if pattern.search(ln):
                offences.append(f"{rel}:{i} — direct telegram URL")
    assert not offences, "Direct Telegram URLs outside adapter:\n" + "\n".join(offences)


def test_placeholder_files_do_not_call_bot_token_at_runtime():
    """The 3 allowlisted files must not call sendMessage/getFile/setWebhook/etc. directly.

    Their functions must delegate to modules.telegram_internal.bot_api.
    """
    forbidden = re.compile(
        r'(TELEGRAM_API\s*\+\s*|f["\'][^"\']*\{BOT_TOKEN\}[^"\']*["\'])'
    )
    for rel in ALLOWLIST_PLACEHOLDERS:
        path = BACKEND / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, ln in enumerate(text.splitlines(), start=1):
            if forbidden.search(ln):
                raise AssertionError(
                    f"{rel}:{i} — legacy service still builds a Telegram URL directly: {ln.strip()!r}"
                )
