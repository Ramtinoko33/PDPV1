"""Assistências — invoice PDF extraction via GPT-4o vision.

Always uses vision (per user choice). Renders each page to image, sends to GPT-4o,
asks for structured invoice fields. Falls back gracefully if AI fails.
"""
import os
import base64
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _pdf_to_images(pdf_bytes: bytes, max_pages: int = 3) -> list:
    """Render the first N pages of a PDF to JPEG bytes."""
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("[ASSIST_PDF] pymupdf (fitz) not installed")
        return []
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=180)
            images.append(pix.tobytes("jpeg"))
        doc.close()
    except Exception as e:
        logger.error(f"[ASSIST_PDF] PDF render error: {e}")
    return images


async def extract_invoice_fields(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract invoice fields using GPT-4o vision.

    Returns a dict with keys:
      invoice_number, invoice_date (YYYY-MM-DD), invoice_total (float),
      invoice_customer, invoice_nif, registration_plate, document_type,
      confidence (low/medium/high), raw_response
    On any failure returns dict with all-None values and confidence='low'.
    """
    empty = {
        "invoice_number": None, "invoice_date": None, "invoice_total": None,
        "invoice_customer": None, "invoice_nif": None, "registration_plate": None,
        "document_type": None, "confidence": "low", "raw_response": None,
    }
    if not EMERGENT_LLM_KEY:
        logger.error("[ASSIST_PDF] EMERGENT_LLM_KEY not set")
        return empty

    images = _pdf_to_images(pdf_bytes, max_pages=3)
    if not images:
        return empty

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    except ImportError:
        logger.error("[ASSIST_PDF] emergentintegrations not installed")
        return empty

    system_prompt = (
        "You are an OCR specialist for Portuguese invoices ('fatura'). "
        "Extract EXACT values visible in the document. Reply ONLY in JSON, no commentary. "
        "Use null if a field is not clearly visible. "
        "For invoice_date use ISO format YYYY-MM-DD. "
        "invoice_total is a number (Euro amount, decimal point not comma). "
        "document_type is one of: fatura, fatura_recibo, fatura_simplificada, nota_credito, recibo, other."
    )
    user_text = (
        "Extract invoice fields and return JSON with keys: "
        "invoice_number, invoice_date, invoice_total, invoice_customer, "
        "invoice_nif, registration_plate, document_type, confidence (low/medium/high). "
        "If multiple pages, prefer the first page values."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="assist-invoice-extract",
            system_message=system_prompt,
        ).with_model("openai", "gpt-4o")

        image_contents = [
            ImageContent(image_base64=base64.b64encode(img).decode("utf-8"))
            for img in images
        ]
        msg = UserMessage(text=user_text, file_contents=image_contents)
        response = await chat.send_message(msg)

        # Try parse JSON from response
        import json
        import re
        text = response if isinstance(response, str) else str(response)
        # Strip code fences if present
        m = re.search(r"\{.*\}", text, re.DOTALL)
        json_str = m.group(0) if m else text
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"[ASSIST_PDF] Could not parse JSON from AI response: {text[:200]}")
            empty["raw_response"] = text[:1000]
            return empty

        # Normalize / coerce types
        def _as_float(v):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).replace(",", ".").replace("€", "").strip())
            except (ValueError, TypeError):
                return None

        result = {
            "invoice_number": data.get("invoice_number") or None,
            "invoice_date": data.get("invoice_date") or None,
            "invoice_total": _as_float(data.get("invoice_total")),
            "invoice_customer": data.get("invoice_customer") or None,
            "invoice_nif": data.get("invoice_nif") or None,
            "registration_plate": data.get("registration_plate") or None,
            "document_type": data.get("document_type") or None,
            "confidence": (data.get("confidence") or "medium").lower(),
            "raw_response": text[:1000],
        }
        return result
    except Exception as e:
        logger.error(f"[ASSIST_PDF] AI extraction error: {e}")
        empty["raw_response"] = str(e)[:500]
        return empty
