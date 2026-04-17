"""
Quote Context Service — Intelligent suggestion and assisted learning.
Determines quote_context (diagnostic vs customer_request) and tracks learning.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from db import db

logger = logging.getLogger(__name__)

CONTEXT_TYPES = ("diagnostic", "customer_request", "unknown")

# ============== AUTO-DETECTION ==============
def detect_context_from_source(ticket: dict) -> str:
    """Auto-detect quote_context from ticket source/channel."""
    if ticket.get("source_alert_id"):
        return "diagnostic"
    channel = (ticket.get("channel") or "").upper()
    if channel in ("TELEGRAM",) and ticket.get("source_alert_id"):
        return "diagnostic"
    if channel in ("WHATSAPP", "EMAIL"):
        return "customer_request"
    ticket_type = (ticket.get("type") or "").upper()
    if "MECANICA" in ticket_type and ticket.get("source_alert_id"):
        return "diagnostic"
    return "unknown"


# ============== SUGGESTION SCORING ==============
TECHNICAL_KEYWORDS = [
    "fuga", "distribuicao", "distribuição", "embraiagem", "sobreaquecimento",
    "radiador", "turbo", "alternador", "catalisador", "permutador",
    "egr", "motor arranque", "bomba", "junta", "rolamento", "sensor",
    "valvula", "injector", "correia", "suspensao", "suspensão",
    "amortecedor", "amortecedores", "braço", "braco", "diagnostico",
    "diagnóstico", "verificacao", "verificação", "inspecao", "inspeção",
]


def compute_suggestion_score(descriptions: list, ticket: dict = None) -> dict:
    """Compute a suggestion score for whether this quote is diagnostic.
    Returns { score, signals, suggested_context }."""
    score = 0
    signals = []

    combined_text = " ".join(d.lower() for d in descriptions if d)

    # Signal: multiple services / package ("+")
    has_package = any("+" in d for d in descriptions if d)
    if has_package or len(descriptions) >= 3:
        score += 2
        signals.append("multiple_services")

    # Signal: technical wording
    for kw in TECHNICAL_KEYWORDS:
        if kw in combined_text:
            score += 1
            signals.append(f"technical:{kw}")
            break  # Only count once

    # Signal: attachments/photos present
    if ticket and (ticket.get("attachments_count", 0) > 0 or len(ticket.get("attachments", [])) > 0):
        score += 1
        signals.append("has_attachments")

    # Signal: significant expansion from original request
    original_desc = (ticket.get("description") or "") if ticket else ""
    if original_desc and combined_text:
        orig_words = set(original_desc.lower().split())
        quote_words = set(combined_text.split())
        new_words = quote_words - orig_words
        if len(new_words) > 8:
            score += 2
            signals.append("expanded_from_original")

    # Signal: long or detailed description
    if len(combined_text) > 120:
        score += 1
        signals.append("long_description")

    suggested = "diagnostic" if score >= 2 else None

    return {
        "score": score,
        "signals": signals,
        "suggested_context": suggested,
    }


# ============== CONTEXT DISPLAY TEXT ==============
CONTEXT_DISPLAY_TEXT = {
    "diagnostic": "(Identificado na verificacao do veiculo)",
    "customer_request": "(Conforme pedido)",
    "unknown": "(Sujeito a verificacao em oficina)",
}


def get_context_display_text(context: str) -> str:
    return CONTEXT_DISPLAY_TEXT.get(context, CONTEXT_DISPLAY_TEXT["unknown"])


# ============== LEARNING ==============
async def record_learning_event(
    ticket_id: str,
    descriptions: list,
    suggestion_score: int,
    signals: list,
    suggested_context: str,
    user_action: str,
    user_id: str,
):
    """Record a learning event when user accepts or ignores a suggestion."""
    from services.quote_normalizer import normalize_description
    normalized_descs = [normalize_description(d).get("title", d) for d in descriptions if d]

    event = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "original_descriptions": descriptions,
        "normalized_descriptions": normalized_descs,
        "signals_detected": signals,
        "suggestion_score": suggestion_score,
        "suggested_context": suggested_context,
        "user_action": user_action,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.quote_context_learning_events.insert_one(event)

    # Update aggregated stats
    for norm_desc in normalized_descs:
        if not norm_desc:
            continue
        existing = await db.quote_context_learning_stats.find_one(
            {"normalized_description": norm_desc}, {"_id": 0}
        )
        if existing:
            update = {
                "$inc": {
                    "times_suggested": 1,
                    "times_accepted": 1 if user_action == "accepted" else 0,
                    "times_ignored": 1 if user_action == "ignored" else 0,
                },
                "$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()},
            }
            await db.quote_context_learning_stats.update_one(
                {"normalized_description": norm_desc}, update
            )
            # Recompute acceptance_rate
            doc = await db.quote_context_learning_stats.find_one(
                {"normalized_description": norm_desc}, {"_id": 0}
            )
            if doc and doc.get("times_suggested", 0) > 0:
                rate = round(doc.get("times_accepted", 0) / doc["times_suggested"] * 100, 1)
                await db.quote_context_learning_stats.update_one(
                    {"normalized_description": norm_desc},
                    {"$set": {"acceptance_rate": rate}}
                )
        else:
            await db.quote_context_learning_stats.insert_one({
                "id": str(uuid.uuid4()),
                "normalized_description": norm_desc,
                "times_suggested": 1,
                "times_accepted": 1 if user_action == "accepted" else 0,
                "times_ignored": 1 if user_action == "ignored" else 0,
                "acceptance_rate": 100.0 if user_action == "accepted" else 0.0,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            })

    logger.info(f"[QUOTE_CONTEXT] Learning event: ticket={ticket_id}, action={user_action}, score={suggestion_score}")


async def get_learning_stats(min_suggested: int = 1) -> list:
    """Get aggregated learning stats for admin view."""
    stats = await db.quote_context_learning_stats.find(
        {"times_suggested": {"$gte": min_suggested}},
        {"_id": 0}
    ).sort("times_suggested", -1).to_list(200)

    for s in stats:
        s["recommendation_status"] = "candidate" if (
            s.get("times_suggested", 0) >= 8 and s.get("acceptance_rate", 0) >= 80
        ) else "learning"

    return stats
