"""
Quote Description Normalizer - Display-only transformation layer.
Never modifies stored data. Only transforms for customer-facing display.
"""
import re
import json
import logging
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Unmatched log file
_LOG_DIR = Path(__file__).parent.parent / "logs"
_UNMATCHED_LOG = _LOG_DIR / "quote_normalizer_unmatched.json"


# ============== COMMERCIAL COPY ==============
PRIORITY_MESSAGES = {
    "critical": "Recomendamos resolver de imediato para evitar danos graves",
    "safety": "Pode comprometer a seguranca do veiculo",
    "normal": "Manutencao recomendada para bom funcionamento",
}


# ============== SYNONYM / TYPO MAP ==============
SYNONYMS = {
    # Multi-word (applied first, longest match)
    "mao de obra": "mao de obra",
    "mão de obra": "mao de obra",
    "filtro habitaculo": "filtro de habitaculo",
    "filtro habitáculo": "filtro de habitaculo",
    "filtro oleo": "filtro de oleo",
    "filtro óleo": "filtro de oleo",
    "filtro ar": "filtro de ar",
    "velas ignicao": "velas de ignicao",
    "velas ignição": "velas de ignicao",
    "bomba agua": "bomba de agua",
    "bomba de água": "bomba de agua",
    "bomba água": "bomba de agua",
    "motor arranque": "motor de arranque",
    "fuga de agua": "fuga de agua",
    "fuga agua": "fuga de agua",
    "fuga de água": "fuga de agua",
    "fuga oleo": "fuga de oleo",
    "fuga de oleo": "fuga de oleo",
    "fuga de óleo": "fuga de oleo",
    "permutador da egr": "permutador egr",
    "permutador de egr": "permutador egr",
    "pack rosa": "pack rosa",
    "oleo motor": "oleo motor",
    "mudanca de oleo": "mudanca de oleo",
    "mudança de oleo": "mudanca de oleo",
    "mudança de óleo": "mudanca de oleo",
    # Single-word typos
    "pstlhas": "pastilhas",
    "pastilha": "pastilhas",
    "calcos": "pastilhas",
    "calços": "pastilhas",
    "calco": "pastilhas",
    "calço": "pastilhas",
    "alinhamneto": "alinhamento",
    "alinhamnto": "alinhamento",
    "alinhameto": "alinhamento",
    "equilibragen": "equilibragem",
    "equilibrage": "equilibragem",
    "hannkook": "hankook",
    "hankock": "hankook",
    "hankok": "hankook",
    "batria": "bateria",
    "bateira": "bateria",
    "amortecedore": "amortecedores",
    "travão": "travoes",
    "travao": "travoes",
    "travões": "travoes",
    "óleo": "oleo",
    "peneu": "pneu",
    "peneus": "pneus",
    "distribuição": "distribuicao",
    "distribucao": "distribuicao",
    "embraiagen": "embraiagem",
    "embreagem": "embraiagem",
    "suspensão": "suspensao",
    "direção": "direcao",
    "corrsia": "correia",
    "escapamento": "escape",
    "catalizador": "catalisador",
    "sobreaquecimento": "sobreaquecimento",
}


# ============== KNOWN ITEMS (keyword → display info) ==============
KNOWN_ITEMS = {
    # --- CRITICAL: immediate damage risk ---
    "fuga de agua": {"title": "Reparação de fuga de água", "priority": "critical"},
    "fuga de oleo": {"title": "Reparação de fuga de óleo", "priority": "critical"},
    "radiador": {"title": "Radiador", "priority": "critical"},
    "sobreaquecimento": {"title": "Reparação de sobreaquecimento", "priority": "critical"},
    "motor de arranque": {"title": "Motor de arranque", "priority": "critical"},
    "turbo": {"title": "Turbo", "priority": "critical"},

    # --- SAFETY: braking, tires, suspension ---
    "pastilhas": {"title": "Pastilhas de travão", "priority": "safety"},
    "discos": {"title": "Discos de travão", "priority": "safety"},
    "disco": {"title": "Disco de travão", "priority": "safety"},
    "travoes": {"title": "Sistema de travagem", "priority": "safety"},
    "pneu": {"title": "Pneu", "priority": "safety"},
    "pneus": {"title": "Pneus", "priority": "safety"},
    "amortecedores": {"title": "Amortecedores", "priority": "safety"},
    "amortecedor": {"title": "Amortecedor", "priority": "safety"},
    "molas": {"title": "Molas de suspensão", "priority": "safety"},
    "suspensao": {"title": "Suspensão", "priority": "safety"},
    "bracos": {"title": "Braços de suspensão", "priority": "safety"},
    "braco": {"title": "Braço de suspensão", "priority": "safety"},
    "distribuicao": {"title": "Kit de distribuição", "priority": "safety"},
    "embraiagem": {"title": "Embraiagem", "priority": "safety"},
    "direcao": {"title": "Direção", "priority": "safety"},

    # --- NORMAL: routine maintenance ---
    "oleo": {"title": "Óleo do motor", "priority": "normal"},
    "oleo motor": {"title": "Óleo do motor", "priority": "normal"},
    "mudanca de oleo": {"title": "Mudança de óleo", "priority": "normal"},
    "filtro de ar": {"title": "Filtro de ar", "priority": "normal"},
    "filtro de oleo": {"title": "Filtro de óleo", "priority": "normal"},
    "filtro de habitaculo": {"title": "Filtro de habitáculo", "priority": "normal"},
    "filtro de combustivel": {"title": "Filtro de combustível", "priority": "normal"},
    "velas": {"title": "Velas de ignição", "priority": "normal"},
    "velas de ignicao": {"title": "Velas de ignição", "priority": "normal"},
    "correia": {"title": "Correia", "priority": "normal"},
    "bateria": {"title": "Bateria", "priority": "normal"},
    "alternador": {"title": "Alternador", "priority": "normal"},
    "bomba de agua": {"title": "Bomba de água", "priority": "normal"},
    "catalisador": {"title": "Catalisador", "priority": "normal"},
    "escape": {"title": "Sistema de escape", "priority": "normal"},
    "egr": {"title": "Válvula EGR", "priority": "normal"},
    "valvula egr": {"title": "Válvula EGR", "priority": "normal"},
    "permutador": {"title": "Permutador", "priority": "normal"},
    "permutador egr": {"title": "Permutador da EGR", "priority": "normal"},
    "alinhamento": {"title": "Alinhamento de direção", "priority": "normal"},
    "equilibragem": {"title": "Equilibragem", "priority": "normal"},
    "revisao": {"title": "Revisão", "priority": "normal"},
    "inspecao": {"title": "Inspeção", "priority": "normal"},
    "diagnostico": {"title": "Diagnóstico", "priority": "normal"},
    "mao de obra": {"title": "Mão de obra", "priority": "normal"},
    "pack rosa": {"title": "Pack Rosa", "priority": "normal"},
    "ar condicionado": {"title": "Ar condicionado", "priority": "normal"},
    "junta": {"title": "Junta", "priority": "normal"},
    "rolamento": {"title": "Rolamento", "priority": "normal"},
    "rolamentos": {"title": "Rolamentos", "priority": "normal"},
    "sensor": {"title": "Sensor", "priority": "normal"},
    "sensores": {"title": "Sensores", "priority": "normal"},
    "valvula": {"title": "Válvula", "priority": "normal"},
    "injector": {"title": "Injector", "priority": "normal"},
    "injectores": {"title": "Injectores", "priority": "normal"},
}


# ============== KNOWN PACKAGES ==============
KNOWN_PACKAGES = {
    frozenset(["pastilhas", "discos"]): {
        "title": "Kit de travagem (pastilhas + discos)",
        "priority": "safety",
    },
    frozenset(["pastilhas", "discos", "travoes"]): {
        "title": "Sistema de travagem completo",
        "priority": "safety",
    },
    frozenset(["alinhamento", "equilibragem"]): {
        "title": "Alinhamento e equilibragem",
        "priority": "normal",
    },
    frozenset(["oleo", "filtro de oleo"]): {
        "title": "Mudança de óleo com filtro",
        "priority": "normal",
    },
    frozenset(["mudanca de oleo", "filtro de oleo"]): {
        "title": "Mudança de óleo com filtro",
        "priority": "normal",
    },
    frozenset(["oleo", "filtro de oleo", "filtro de ar"]): {
        "title": "Revisão de filtros e óleo",
        "priority": "normal",
    },
    frozenset(["oleo", "filtro de oleo", "filtro de ar", "filtro de habitaculo"]): {
        "title": "Revisão completa de filtros",
        "priority": "normal",
    },
    frozenset(["pneus", "alinhamento", "equilibragem"]): {
        "title": "Pneus com alinhamento e equilibragem",
        "priority": "safety",
    },
    frozenset(["pneus", "alinhamento"]): {
        "title": "Pneus com alinhamento",
        "priority": "safety",
    },
    frozenset(["pneus", "equilibragem"]): {
        "title": "Pneus com equilibragem",
        "priority": "safety",
    },
    frozenset(["amortecedores", "molas"]): {
        "title": "Kit de suspensão (amortecedores + molas)",
        "priority": "safety",
    },
}


# ============== NORMALIZATION HELPERS ==============
def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ============== TIRE BRANDS & DETECTION ==============
TIRE_BRANDS = {
    "michelin": {"display": "Michelin", "tagline": "qualidade premium e maior durabilidade"},
    "bridgestone": {"display": "Bridgestone", "tagline": "tecnologia japonesa de alta performance"},
    "firestone": {"display": "Firestone", "tagline": "boa relacao qualidade/preco"},
    "hankook": {"display": "Hankook", "tagline": "boa performance com preco competitivo"},
    "continental": {"display": "Continental", "tagline": "engenharia alema de confianca"},
    "pirelli": {"display": "Pirelli", "tagline": "desempenho desportivo e aderencia superior"},
    "goodyear": {"display": "Goodyear", "tagline": "durabilidade e conforto de conducao"},
    "dunlop": {"display": "Dunlop", "tagline": "versatilidade e boa tracao"},
    "yokohama": {"display": "Yokohama", "tagline": "tecnologia japonesa e performance"},
    "kumho": {"display": "Kumho", "tagline": "qualidade coreana a preco acessivel"},
    "nexen": {"display": "Nexen", "tagline": "preco competitivo com boa durabilidade"},
    "toyo": {"display": "Toyo", "tagline": "fiabilidade e conforto"},
    "falken": {"display": "Falken", "tagline": "performance e preco equilibrado"},
    "bf goodrich": {"display": "BF Goodrich", "tagline": "robustez e tracao todo-o-terreno"},
    "bfgoodrich": {"display": "BF Goodrich", "tagline": "robustez e tracao todo-o-terreno"},
    "uniroyal": {"display": "Uniroyal", "tagline": "especialista em piso molhado"},
    "barum": {"display": "Barum", "tagline": "opcao economica do grupo Continental"},
    "laufenn": {"display": "Laufenn", "tagline": "linha acessivel da Hankook"},
    "vredestein": {"display": "Vredestein", "tagline": "conforto e design holandes"},
    "nokian": {"display": "Nokian", "tagline": "especialista em condicoes adversas"},
    "maxxis": {"display": "Maxxis", "tagline": "versatilidade e durabilidade"},
    "nankang": {"display": "Nankang", "tagline": "opcao economica com bom desempenho"},
    "imperial": {"display": "Imperial", "tagline": "preco acessivel para uso diario"},
    "sailun": {"display": "Sailun", "tagline": "preco competitivo"},
    "triangle": {"display": "Triangle", "tagline": "opcao economica"},
    "general tire": {"display": "General Tire", "tagline": "qualidade do grupo Continental"},
    "general": {"display": "General Tire", "tagline": "qualidade do grupo Continental"},
    "semperit": {"display": "Semperit", "tagline": "fiabilidade austriaca"},
    "cooper": {"display": "Cooper", "tagline": "robustez americana"},
    "avon": {"display": "Avon", "tagline": "tradicao britanica"},
    "debica": {"display": "Debica", "tagline": "opcao economica do grupo Goodyear"},
    "sava": {"display": "Sava", "tagline": "qualidade europeia acessivel"},
    "roadstone": {"display": "Roadstone", "tagline": "preco competitivo"},
}

# Quantity patterns: "4x", "x4", "4 x", "x 4", "2x", "4 pneus", etc.
_QTY_PATTERN = re.compile(r'(\d)\s*x\b|\bx\s*(\d)', re.IGNORECASE)
_QTY_PNEUS_PATTERN = re.compile(r'\b(\d)\s+pneus?\b', re.IGNORECASE)


def _detect_tire(normalized: str) -> dict:
    """Detect tire product from normalized text.
    Returns result dict if tire detected, None otherwise."""
    # Check for any known brand
    found_brand = None
    for brand_key, brand_info in sorted(TIRE_BRANDS.items(), key=lambda x: -len(x[0])):
        if brand_key in normalized:
            found_brand = brand_info
            break

    # Check for quantity pattern
    qty_match = _QTY_PATTERN.search(normalized)
    qty = None
    if qty_match:
        qty = int(qty_match.group(1) or qty_match.group(2))
    else:
        # Try "4 pneus" pattern
        qty_pneus = _QTY_PNEUS_PATTERN.search(normalized)
        if qty_pneus:
            qty = int(qty_pneus.group(1))

    # Also check for "pneu"/"pneus" keyword
    has_tire_word = bool(re.search(r'\bpneus?\b', normalized))

    # Must have brand OR (quantity pattern + tire word) to be a tire product
    if not found_brand and not (qty and has_tire_word):
        return None

    # Build title
    if found_brand:
        brand_display = found_brand["display"]
        tagline = found_brand["tagline"]
        qty_text = f" ({qty} unidades)" if qty else ""
        title = f"Pneus {brand_display}{qty_text} — {tagline}"
    else:
        # Has qty + pneu word but no brand
        qty_text = f" ({qty} unidades)" if qty else ""
        title = f"Pneus{qty_text}"

    return {
        "title": title,
        "type": "single",
        "includes": [],
        "priority": "safety",
        "priority_message": PRIORITY_MESSAGES["safety"],
    }


def _normalize(text: str) -> str:
    """Lowercase, remove accents, remove punctuation/prices, trim."""
    text = text.lower().strip()
    text = _remove_accents(text)
    text = re.sub(r'[€$]\s*[\d.,]+|[\d.,]+\s*[€$]', '', text)
    text = re.sub(r'[^\w\s/+]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _apply_synonyms(text: str) -> str:
    """Apply synonym/typo corrections (longest match first)."""
    for typo, correction in sorted(SYNONYMS.items(), key=lambda x: -len(x[0])):
        if typo in text:
            text = text.replace(typo, correction)
    return text


def _match_single(normalized: str) -> tuple:
    """Match normalized text against known items.
    Returns (matched_info_dict, matched_keyword) or (None, None)."""
    if normalized in KNOWN_ITEMS:
        return KNOWN_ITEMS[normalized], normalized

    best_match = None
    best_key = None
    best_len = 0
    for keyword, info in KNOWN_ITEMS.items():
        if len(keyword) <= 3:
            # Short keywords: require word boundary to avoid false matches
            if re.search(r'\b' + re.escape(keyword) + r'\b', normalized):
                if len(keyword) > best_len:
                    best_match = info
                    best_key = keyword
                    best_len = len(keyword)
        elif keyword in normalized and len(keyword) > best_len:
            best_match = info
            best_key = keyword
            best_len = len(keyword)

    return best_match, best_key


def _best_priority(priorities: list) -> str:
    """Return highest priority from list."""
    order = {"critical": 0, "safety": 1, "normal": 2}
    best = "normal"
    for p in priorities:
        if order.get(p, 2) < order.get(best, 2):
            best = p
    return best


def _log_unmatched(original: str, normalized: str):
    """Append unmatched description to log file for dictionary improvement."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "original": original,
            "normalized": normalized,
            "matched": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        entries = []
        if _UNMATCHED_LOG.exists():
            try:
                entries = json.loads(_UNMATCHED_LOG.read_text(encoding="utf-8"))
            except Exception:
                entries = []
        # Avoid duplicates (same normalized)
        if not any(e.get("normalized") == normalized for e in entries):
            entries.append(entry)
            # Keep last 500 entries
            entries = entries[-500:]
            _UNMATCHED_LOG.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[QUOTE_NORM] Unmatched logged: {normalized}")
    except Exception as e:
        logger.debug(f"[QUOTE_NORM] Log write error: {e}")


def _clean_fallback(raw: str) -> str:
    """Clean raw text for fallback display title."""
    text = raw.strip()
    # Truncate at first sentence boundary
    for sep in [". ", ".\n", "\n"]:
        if sep in text:
            text = text[:text.index(sep)]
            break
    # Capitalize first letter
    if text:
        text = text[0].upper() + text[1:]
    return text


# ============== MAIN ENTRY POINT ==============
def normalize_description(raw_description: str) -> dict:
    """
    Transform a quote option description for display.
    Returns: { title, type, includes, priority, priority_message }
    Never modifies stored data.
    """
    if not raw_description or not raw_description.strip():
        return {
            "title": raw_description or "",
            "type": "single",
            "includes": [],
            "priority": "normal",
            "priority_message": PRIORITY_MESSAGES["normal"],
        }

    normalized = _normalize(raw_description)
    normalized = _apply_synonyms(normalized)

    # ---- TIRE PRODUCT DETECTION (before general matching) ----
    tire_result = _detect_tire(normalized)
    if tire_result and "+" not in normalized:
        return tire_result

    # ---- PACKAGE DETECTION: "+" always means package ----
    is_package = "+" in normalized

    if is_package:
        parts = [p.strip() for p in normalized.split("+") if p.strip()]
        matched_keys = []
        matched_titles = []

        for part in parts:
            part = _apply_synonyms(part)
            # Try tire detection for this part first
            tire_part = _detect_tire(part)
            if tire_part:
                matched_titles.append(tire_part["title"])
                matched_keys.append("pneus")
                continue
            match, key = _match_single(part)
            if match:
                matched_titles.append(match["title"])
                if key:
                    matched_keys.append(key)
            else:
                # Unmatched part: clean capitalize
                cleaned = _clean_fallback(part)
                matched_titles.append(cleaned if cleaned else part)

        keys_set = frozenset(matched_keys)

        # a) Known package exact match
        if keys_set in KNOWN_PACKAGES:
            pkg = KNOWN_PACKAGES[keys_set]
            return {
                "title": pkg["title"],
                "type": "package",
                "includes": matched_titles,
                "priority": pkg["priority"],
                "priority_message": PRIORITY_MESSAGES[pkg["priority"]],
            }

        # b) Compose from parts
        all_priorities = [
            KNOWN_ITEMS.get(k, {}).get("priority", "normal") for k in matched_keys
        ]
        priority = _best_priority(all_priorities) if all_priorities else "normal"

        title = " + ".join(matched_titles) if len(matched_titles) > 1 else (
            matched_titles[0] if matched_titles else normalized.capitalize()
        )

        return {
            "title": title,
            "type": "package",
            "includes": matched_titles,
            "priority": priority,
            "priority_message": PRIORITY_MESSAGES[priority],
        }

    # ---- SMART " e " SPLIT: only if both sides are known ----
    if " e " in normalized:
        idx = normalized.index(" e ")
        left = _apply_synonyms(normalized[:idx].strip())
        right = _apply_synonyms(normalized[idx + 3:].strip())
        left_match, left_key = _match_single(left)
        right_match, right_key = _match_single(right)
        if left_match and right_match:
            keys_set = frozenset(filter(None, [left_key, right_key]))
            titles = [left_match["title"], right_match["title"]]

            if keys_set in KNOWN_PACKAGES:
                pkg = KNOWN_PACKAGES[keys_set]
                return {
                    "title": pkg["title"],
                    "type": "package",
                    "includes": titles,
                    "priority": pkg["priority"],
                    "priority_message": PRIORITY_MESSAGES[pkg["priority"]],
                }

            priority = _best_priority([left_match["priority"], right_match["priority"]])
            return {
                "title": f"{left_match['title']} + {right_match['title']}",
                "type": "package",
                "includes": titles,
                "priority": priority,
                "priority_message": PRIORITY_MESSAGES[priority],
            }

    # ---- SINGLE ITEM ----
    match, _ = _match_single(normalized)
    if match:
        return {
            "title": match["title"],
            "type": "single",
            "includes": [],
            "priority": match["priority"],
            "priority_message": PRIORITY_MESSAGES[match["priority"]],
        }

    # ---- FALLBACK: no match ----
    _log_unmatched(raw_description, normalized)

    fallback = _clean_fallback(raw_description)
    title = f"Intervenção identificada: {fallback}" if fallback else raw_description.strip()

    return {
        "title": title,
        "type": "single",
        "includes": [],
        "priority": "normal",
        "priority_message": PRIORITY_MESSAGES["normal"],
    }
