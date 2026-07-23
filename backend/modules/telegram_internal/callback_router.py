"""Callback data parsing with S2-C namespace support.

Two formats are accepted:

  1. New namespaced format:  ``<module>:<action>[:<payload>]``
     e.g. ``renting:wheel_ok:2``, ``assist:plate_ok``, ``mech:assign:17``

  2. Legacy formats (kept for full backwards-compatibility with the 4 flows):
     - ``system:*``, ``menu:*``, ``conflict:*`` — reserved namespaces owned
       by the central router.
     - Anything else — passed through to the active_flow handler unchanged.

`parse_callback_data` NEVER raises. On malformed input it returns a
CallbackParse with module="unknown", action=<raw>, payload="".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Namespaces the central router owns (must NOT be treated as module namespaces).
RESERVED_ROUTER_NAMESPACES = {"system", "menu", "conflict"}

# Namespaces that map 1-1 to a module. Multiple aliases are accepted so
# short module labels can be used in-line without ambiguity.
MODULE_NAMESPACE_ALIASES = {
    "renting":      "renting",
    "rent":         "renting",
    "assistencias": "assistencias",
    "assist":       "assistencias",
    "mech_alert":   "mech_alert",
    "mech":         "mech_alert",
    "pre_ticket":   "pre_ticket",
    "pre":          "pre_ticket",
    "admin":        "admin",
}


@dataclass(frozen=True)
class CallbackParse:
    """Structured result of parsing a callback_data string.

    - namespaced: True when the raw string uses the new ``mod:action[:payload]``
      format AND the module is a known alias.
    - module: resolved module name (``renting``, ``assistencias``, ...) or
      ``unknown`` for legacy / malformed strings.
    - action: the middle segment (or the whole raw string for legacy formats).
    - payload: everything after the second colon (may be empty).
    - reserved: True when the namespace belongs to the central router
      (``system:``, ``menu:``, ``conflict:``) — module returned is ``admin``.
    """
    raw: str
    namespaced: bool
    module: str
    action: str
    payload: str
    reserved: bool


def parse_callback_data(raw: Optional[str]) -> CallbackParse:
    """Never raises. Empty/None → CallbackParse('', False, 'unknown', '', '', False)."""
    if not raw or not isinstance(raw, str):
        return CallbackParse("", False, "unknown", "", "", False)

    if ":" not in raw:
        # Pure legacy shape (e.g. "plate_ok", "photo_yes"). No module info here.
        return CallbackParse(raw, False, "unknown", raw, "", False)

    ns, _, rest = raw.partition(":")
    ns = ns.strip()

    # Reserved router namespaces — action follows immediately, module=admin.
    if ns in RESERVED_ROUTER_NAMESPACES:
        action, _, payload = rest.partition(":")
        return CallbackParse(raw, False, "admin", action, payload, True)

    # Module namespace?
    module = MODULE_NAMESPACE_ALIASES.get(ns)
    if module:
        action, _, payload = rest.partition(":")
        # Defensive: enforce non-empty action for a valid namespaced call.
        if not action:
            return CallbackParse(raw, False, "unknown", ns, rest, False)
        return CallbackParse(raw, True, module, action, payload, False)

    # Unknown namespace with a colon — treat as legacy, module unknown.
    return CallbackParse(raw, False, "unknown", raw, "", False)


def build_callback(module: str, action: str, payload: str = "") -> str:
    """Utility for new buttons to emit namespaced callback strings.

    Falls back to the short alias when possible for Telegram's 64-byte limit.
    """
    short_aliases = {v: k for k, v in MODULE_NAMESPACE_ALIASES.items() if len(k) <= 6}
    prefix = short_aliases.get(module, module)
    if payload:
        return f"{prefix}:{action}:{payload}"
    return f"{prefix}:{action}"
