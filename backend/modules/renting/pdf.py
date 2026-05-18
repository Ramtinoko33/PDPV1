"""Renting module — PDF generation (technical request for the renting company)."""
import io
import logging
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader

from .models import WHEEL_POSITIONS, WHEEL_LABELS
from . import service

logger = logging.getLogger(__name__)

NAVY = HexColor("#0B2E4F")
YELLOW = HexColor("#F4B400")
GRAY = HexColor("#666666")
LIGHT = HexColor("#F3F4F6")
BORDER = HexColor("#D4D4D8")
BLACK = HexColor("#111827")

SUBTYPE_LABELS = {
    "tires": "Pedido de Pneus",
    "puncture": "Reparação de Furo",
    "adblue": "Reposição AdBlue",
    "other": "Outro Serviço",
}


def _draw_header(c, width, height, company_name: str):
    c.setFillColor(NAVY)
    c.rect(0, height - 80, width, 80, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    c.rect(0, height - 86, width, 6, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, height - 45, company_name)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, height - 65, "Pedido Renting — Documento Técnico")


def _draw_footer(c, width, page_num: int):
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 12 * mm, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.drawRightString(width - 20 * mm, 12 * mm, f"Página {page_num}")


def _check_page_break(c, y, width, height, page_state, min_y=40 * mm):
    """If y < min_y, finish page and start new. Returns new (y, page_num)."""
    if y < min_y:
        _draw_footer(c, width, page_state["page"])
        c.showPage()
        page_state["page"] += 1
        _draw_header(c, width, height, page_state["company_name"])
        return height - 110, page_state["page"]
    return y, page_state["page"]


async def build_renting_pdf(record: dict, company_name: str = "Pneus D. Pedro V") -> bytes:
    """Build a technical PDF for a Renting record.

    Excludes internal-only fields: observations, history, proposed_tires, authorization_number.
    """
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    page_state = {"page": 1, "company_name": company_name}

    _draw_header(c, width, height, company_name)

    # Title
    subtype = record.get("subtype") or "tires"
    title = SUBTYPE_LABELS.get(subtype, "Pedido Renting")
    y = height - 110
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, title)
    y -= 8 * mm
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    created = record.get("created_at") or ""
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created_str = created_dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            created_str = created[:16].replace("T", " ")
    else:
        created_str = "—"
    c.drawString(20 * mm, y, f"Data do pedido: {created_str}")
    c.drawRightString(width - 20 * mm, y, f"Ref: {(record.get('id') or '')[:8]}")

    # Info table (Cliente / Viatura)
    y -= 8 * mm
    info_rows = [
        ["Empresa Renting", record.get("renting_company") or "—", "Matrícula", record.get("license_plate") or "—"],
        ["Condutor", record.get("driver_name") or "—", "Telefone", record.get("driver_phone") or "—"],
        ["KM atuais", f"{record.get('km'):,}".replace(",", " ") if record.get("km") is not None else "—",
         "Tipo de serviço", record.get("service_type_label") or SUBTYPE_LABELS.get(subtype, "—")],
    ]
    t = Table(info_rows, colWidths=[35 * mm, 55 * mm, 35 * mm, 45 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (2, 0), (2, -1), NAVY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    t.wrapOn(c, width - 40 * mm, 60 * mm)
    table_h = 3 * 12 * mm  # approx
    y -= 2 * mm
    t.drawOn(c, 20 * mm, y - table_h + 6 * mm)
    y -= table_h + 4 * mm

    # ===== Subtype-specific section =====
    if subtype == "tires":
        y, _ = _check_page_break(c, y, width, height, page_state, min_y=160 * mm)
        y = _draw_wheels_table(c, record, width, y)
        y = await _draw_wheel_photos(c, record, width, height, y, page_state)
    elif subtype == "puncture":
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, "Detalhes da reparação de furo")
        y -= 7 * mm
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"Roda afetada: {record.get('puncture_wheel_label') or '—'}")
        y -= 8 * mm
    elif subtype == "adblue":
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, "Reposição AdBlue")
        y -= 7 * mm
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 10)
        liters = record.get("adblue_liters")
        c.drawString(20 * mm, y, f"Litros: {liters if liters is not None else '—'} L")
        y -= 8 * mm
    elif subtype == "other":
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, "Descrição do pedido")
        y -= 7 * mm
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 10)
        desc = record.get("description") or "—"
        for line in _wrap_text(desc, 90):
            c.drawString(20 * mm, y, line)
            y -= 5 * mm

    # ===== Plate & KM photos (always include) =====
    y, _ = _check_page_break(c, y, width, height, page_state, min_y=90 * mm)
    y -= 4 * mm
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Fotografias — Matrícula e Quilometragem")
    y -= 6 * mm
    plate_bytes = await service.get_photo_bytes(record.get("license_plate_photo"))
    km_bytes = await service.get_photo_bytes(record.get("km_photo"))
    photo_w, photo_h = 80 * mm, 55 * mm
    if plate_bytes:
        _draw_image(c, plate_bytes, 20 * mm, y - photo_h, photo_w, photo_h, "Matrícula")
    else:
        _draw_image_placeholder(c, 20 * mm, y - photo_h, photo_w, photo_h, "Matrícula (sem foto)")
    if km_bytes:
        _draw_image(c, km_bytes, 20 * mm + photo_w + 10 * mm, y - photo_h, photo_w, photo_h, "Quilómetros")
    else:
        _draw_image_placeholder(c, 20 * mm + photo_w + 10 * mm, y - photo_h, photo_w, photo_h, "KM (sem foto)")
    y -= photo_h + 8 * mm

    _draw_footer(c, width, page_state["page"])
    c.save()
    return buffer.getvalue()


def _draw_wheels_table(c, record, width, y):
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Tabela técnica dos pneus")
    y -= 5 * mm

    header = ["Posição", "Medida", "Marca / Modelo", "Índice C/V", "DOT", "Piso (mm)"]
    rows = [header]
    wheels_by_pos = {w.get("position"): w for w in (record.get("wheels") or [])}
    for pos in WHEEL_POSITIONS:
        w = wheels_by_pos.get(pos)
        if not w:
            rows.append([WHEEL_LABELS[pos], "—", "—", "—", "—", "—"])
            continue
        d = w.get("data") or {}
        brand_model = " ".join([s for s in [d.get("brand"), d.get("model")] if s]) or "—"
        rows.append([
            WHEEL_LABELS[pos],
            d.get("size") or "—",
            brand_model,
            d.get("load_speed") or "—",
            d.get("dot") or "—",
            f"{d.get('tread_mm')}" if d.get("tread_mm") is not None else "—",
        ])

    t = Table(rows, colWidths=[32 * mm, 28 * mm, 50 * mm, 22 * mm, 22 * mm, 20 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    table_h = 5 * 8 * mm
    t.wrapOn(c, width - 40 * mm, table_h)
    t.drawOn(c, 20 * mm, y - table_h)
    y -= table_h + 6 * mm
    return y


async def _draw_wheel_photos(c, record, width, height, y, page_state):
    """Draws each wheel's 3 photos (full, dot, tread) with labels."""
    wheels_by_pos = {w.get("position"): w for w in (record.get("wheels") or [])}
    photo_w, photo_h = 55 * mm, 45 * mm
    gap = 5 * mm
    label_h = 5 * mm

    for pos in WHEEL_POSITIONS:
        w = wheels_by_pos.get(pos)
        if not w:
            continue
        y, _ = _check_page_break(c, y, width, height, page_state, min_y=70 * mm)
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, f"Pneu {WHEEL_LABELS[pos]} ({pos})")
        y -= 5 * mm

        full_bytes = await service.get_photo_bytes(w.get("photo_full"))
        dot_bytes = await service.get_photo_bytes(w.get("photo_dot"))
        tread_bytes = await service.get_photo_bytes(w.get("photo_tread"))

        x = 20 * mm
        row_top = y
        items = [(full_bytes, "Flanco"), (dot_bytes, "DOT"), (tread_bytes, "Piso")]
        for b, label in items:
            if b:
                _draw_image(c, b, x, row_top - photo_h - label_h, photo_w, photo_h, label)
            else:
                _draw_image_placeholder(c, x, row_top - photo_h - label_h, photo_w, photo_h, f"{label} (sem foto)")
            x += photo_w + gap
        y -= photo_h + label_h + 6 * mm
    return y


def _draw_image(c, image_bytes: bytes, x, y, w, h, caption: str = ""):
    try:
        img = ImageReader(io.BytesIO(image_bytes))
        c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto")
        c.setStrokeColor(BORDER)
        c.rect(x, y, w, h, fill=0, stroke=1)
        if caption:
            c.setFillColor(GRAY)
            c.setFont("Helvetica", 8)
            c.drawString(x, y - 4 * mm, caption)
    except Exception as e:
        logger.warning(f"[RENTING_PDF] image draw failed: {e}")
        _draw_image_placeholder(c, x, y, w, h, caption or "Sem foto")


def _draw_image_placeholder(c, x, y, w, h, caption: str = ""):
    c.setFillColor(LIGHT)
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(BORDER)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(x + w / 2, y + h / 2, caption or "Sem foto")


def _wrap_text(text: str, max_chars: int):
    words = (text or "").split()
    lines = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ["—"]
