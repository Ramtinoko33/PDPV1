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
TIRE_TIER_TAGLINES = {
    "premium": "maxima seguranca e durabilidade",
    "mid": "excelente equilibrio entre preco e qualidade",
    "budget": "solucao economica e funcional",
}

TIRE_PRIORITY_MESSAGE = "Pneus em mau estado podem comprometer travagem e aderencia"

TIRE_BRANDS = {
    # --- PREMIUM ---
    "michelin":     {"display": "Michelin",     "tier": "premium"},
    "continental":  {"display": "Continental",  "tier": "premium"},
    "bridgestone":  {"display": "Bridgestone",  "tier": "premium"},
    "goodyear":     {"display": "Goodyear",     "tier": "premium"},
    "pirelli":      {"display": "Pirelli",      "tier": "premium"},
    "nokian":       {"display": "Nokian",       "tier": "premium"},
    "vredestein":   {"display": "Vredestein",   "tier": "premium"},
    # --- MID ---
    "hankook":      {"display": "Hankook",      "tier": "mid"},
    "firestone":    {"display": "Firestone",     "tier": "mid"},
    "dunlop":       {"display": "Dunlop",       "tier": "mid"},
    "yokohama":     {"display": "Yokohama",     "tier": "mid"},
    "kumho":        {"display": "Kumho",        "tier": "mid"},
    "nexen":        {"display": "Nexen",        "tier": "mid"},
    "toyo":         {"display": "Toyo",         "tier": "mid"},
    "falken":       {"display": "Falken",       "tier": "mid"},
    "bf goodrich":  {"display": "BF Goodrich",  "tier": "mid"},
    "bfgoodrich":   {"display": "BF Goodrich",  "tier": "mid"},
    "uniroyal":     {"display": "Uniroyal",     "tier": "mid"},
    "cooper":       {"display": "Cooper",       "tier": "mid"},
    "general tire": {"display": "General Tire", "tier": "mid"},
    "general":      {"display": "General Tire", "tier": "mid"},
    "semperit":     {"display": "Semperit",     "tier": "mid"},
    "laufenn":      {"display": "Laufenn",      "tier": "mid"},
    "maxxis":       {"display": "Maxxis",       "tier": "mid"},
    "avon":         {"display": "Avon",         "tier": "mid"},
    # --- BUDGET ---
    "barum":        {"display": "Barum",        "tier": "budget"},
    "nankang":      {"display": "Nankang",      "tier": "budget"},
    "imperial":     {"display": "Imperial",     "tier": "budget"},
    "sailun":       {"display": "Sailun",       "tier": "budget"},
    "triangle":     {"display": "Triangle",     "tier": "budget"},
    "debica":       {"display": "Debica",       "tier": "budget"},
    "sava":         {"display": "Sava",         "tier": "budget"},
    "roadstone":    {"display": "Roadstone",    "tier": "budget"},
    "massimo":      {"display": "Massimo",      "tier": "budget"},
    "roadx":        {"display": "RoadX",        "tier": "budget"},
    "linglong":     {"display": "Linglong",     "tier": "budget"},
    "westlake":     {"display": "Westlake",     "tier": "budget"},
    "hifly":        {"display": "Hifly",        "tier": "budget"},
    "aplus":        {"display": "Aplus",        "tier": "budget"},
    "minerva":      {"display": "Minerva",      "tier": "budget"},
    "rotalla":      {"display": "Rotalla",      "tier": "budget"},
    "torque":       {"display": "Torque",       "tier": "budget"},
    "fullrun":      {"display": "Fullrun",      "tier": "budget"},
    "fortuna":      {"display": "Fortuna",      "tier": "budget"},
    "dayton":       {"display": "Dayton",       "tier": "budget"},
    "radar":        {"display": "Radar",        "tier": "budget"},
    "accelera":     {"display": "Accelera",     "tier": "budget"},
    "goodride":     {"display": "Goodride",     "tier": "budget"},
    "wanli":        {"display": "Wanli",        "tier": "budget"},
    "zeetex":       {"display": "Zeetex",       "tier": "budget"},
}

# Quantity patterns
_QTY_PATTERN = re.compile(r'(\d)\s*x\b|\bx\s*(\d)', re.IGNORECASE)
_QTY_PNEUS_PATTERN = re.compile(r'\b(\d)\s+pneus?\b', re.IGNORECASE)


def _detect_tire(normalized: str) -> dict:
    """Detect tire product from normalized text.
    Returns result dict if tire detected, None otherwise."""
    # Check for any known brand (longest key first)
    found_brand = None
    for brand_key, brand_info in sorted(TIRE_BRANDS.items(), key=lambda x: -len(x[0])):
        if brand_key in normalized:
            found_brand = brand_info
            break

    # Check for quantity
    qty = None
    qty_match = _QTY_PATTERN.search(normalized)
    if qty_match:
        qty = int(qty_match.group(1) or qty_match.group(2))
    else:
        qty_pneus = _QTY_PNEUS_PATTERN.search(normalized)
        if qty_pneus:
            qty = int(qty_pneus.group(1))

    has_tire_word = bool(re.search(r'\bpneus?\b', normalized))

    # Must have brand OR (qty + tire word)
    if not found_brand and not (qty and has_tire_word):
        return None

    # Build output
    qty_text = f" ({qty} unidades)" if qty else ""

    if found_brand:
        tier = found_brand["tier"]
        brand_display = found_brand["display"]
        tagline = TIRE_TIER_TAGLINES[tier]
        recommended = tier == "premium"
        title = f"Pneus {brand_display}{qty_text} — {tagline}"
    else:
        tier = None
        brand_display = None
        recommended = False
        title = f"Pneus{qty_text}"

    return {
        "title": title,
        "type": "single",
        "includes": [],
        "priority": "safety",
        "priority_message": TIRE_PRIORITY_MESSAGE,
        "recommended": recommended,
        "brand_tier": tier,
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
        tire_in_package = None  # Track tire part for pack title

        for part in parts:
            part = _apply_synonyms(part)
            # Try tire detection for this part first
            tire_part = _detect_tire(part)
            if tire_part:
                matched_titles.append(tire_part["title"])
                matched_keys.append("pneus")
                tire_in_package = tire_part
                continue
            match, key = _match_single(part)
            if match:
                matched_titles.append(match["title"])
                if key:
                    matched_keys.append(key)
            else:
                cleaned = _clean_fallback(part)
                matched_titles.append(cleaned if cleaned else part)

        keys_set = frozenset(matched_keys)

        # a) Tire + service(s) → branded pack title takes priority
        if tire_in_package and len(matched_titles) > 1:
            service_titles = [t for t in matched_titles if t != tire_in_package["title"]]
            services_text = " + ".join(service_titles)
            tire_title_short = tire_in_package["title"].split(" — ")[0]  # "Pneus Brand (X unidades)"
            title = f"Pack {tire_title_short} + {services_text} — solucao completa para seguranca e desgaste uniforme"
            return {
                "title": title,
                "type": "package",
                "includes": matched_titles,
                "priority": "safety",
                "priority_message": TIRE_PRIORITY_MESSAGE,
                "recommended": tire_in_package.get("recommended", False),
                "brand_tier": tire_in_package.get("brand_tier"),
            }

        # b) Known package exact match (non-tire)
        if keys_set in KNOWN_PACKAGES:
            pkg = KNOWN_PACKAGES[keys_set]
            return {
                "title": pkg["title"],
                "type": "package",
                "includes": matched_titles,
                "priority": pkg["priority"],
                "priority_message": PRIORITY_MESSAGES[pkg["priority"]],
            }

        # c) Generic compose from parts
        all_priorities = [
            KNOWN_ITEMS.get(k, {}).get("priority", "normal") for k in matched_keys
        ]
        priority = _best_priority(all_priorities) if all_priorities else "normal"

        title = " + ".join(matched_titles) if len(matched_titles) > 1 else (
            matched_titles[0] if matched_titles else normalized.capitalize()
        )

        result = {
            "title": title,
            "type": "package",
            "includes": matched_titles,
            "priority": priority,
            "priority_message": PRIORITY_MESSAGES[priority],
        }
        if tire_in_package:
            result["priority_message"] = TIRE_PRIORITY_MESSAGE
            result["recommended"] = tire_in_package.get("recommended", False)
            result["brand_tier"] = tire_in_package.get("brand_tier")
        return result

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
