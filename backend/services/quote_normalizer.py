"""
Quote Description Normalizer - Display-only transformation layer.
Loads all dictionaries from /config/normalizer_*.json.
Never modifies stored data. Only transforms for customer-facing display.
"""
import re
import json
import logging
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_LOG_DIR = Path(__file__).parent.parent / "logs"
_UNMATCHED_LOG = _LOG_DIR / "quote_normalizer_unmatched.json"


# ============== LOAD CONFIG FILES ==============
def _load_json(filename: str) -> dict:
    path = _CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_abbrev_cfg = _load_json("normalizer_abbreviations.json")
_svc_cfg = _load_json("normalizer_services.json")
_tire_cfg = _load_json("normalizer_tires.json")

# --- Abbreviations (location) ---
LOCATION_ABBREVS: dict = _abbrev_cfg  # key→translated

# --- Prepositions ---
PREPOSITION_ABBREVS: dict = _svc_cfg.get("prepositions", {})

# --- Typo corrections (applied early) ---
_TYPOS: dict = _svc_cfg.get("typos", {})

# --- Multi-word synonym normalization (applied early) ---
_SYNONYMS_PRE: dict = _svc_cfg.get("synonyms_pre", {})

# --- Service dictionary: normalized_key → display title ---
_SERVICES: dict = _svc_cfg.get("services", {})

# --- Priority classification ---
_PRIORITY_CRITICAL: set = set(_svc_cfg.get("priorities", {}).get("critical", []))
_PRIORITY_SAFETY: set = set(_svc_cfg.get("priorities", {}).get("safety", []))

# --- Known packages: frozenset(keys) → {title, priority} ---
KNOWN_PACKAGES: dict = {}
for key_str, pkg in _svc_cfg.get("packages", {}).items():
    keys = frozenset(key_str.split("+"))
    KNOWN_PACKAGES[keys] = pkg

# --- Tire brands ---
TIRE_BRANDS: dict = {}  # normalized_name → {display, tier, tagline}
_tier_taglines = {}
for tier_name, tier_data in _tire_cfg.get("tiers", {}).items():
    tagline = tier_data["tagline"]
    _tier_taglines[tier_name] = tagline
    for brand in tier_data["brands"]:
        TIRE_BRANDS[brand] = {"display": _tire_cfg["display_names"].get(brand, brand.capitalize()), "tier": tier_name}

# Add brands from display_names not yet in tiers (fallback to mid)
for brand_key, display in _tire_cfg.get("display_names", {}).items():
    if brand_key not in TIRE_BRANDS:
        TIRE_BRANDS[brand_key] = {"display": display, "tier": "mid"}

# Apply tire typo corrections
for typo, correct in _tire_cfg.get("typo_corrections", {}).items():
    _TYPOS[typo] = correct

TIRE_PRIORITY_MESSAGE = _tire_cfg.get("priority_message", "")

PRIORITY_MESSAGES = {
    "critical": "Recomendamos resolver de imediato para evitar danos graves",
    "safety": "Pode comprometer a seguranca do veiculo",
    "normal": "Manutencao recomendada para bom funcionamento",
}


# ============== HELPERS ==============
def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _expand_prepositions(text: str) -> str:
    for abbrev, full in PREPOSITION_ABBREVS.items():
        text = text.replace(abbrev, full)
    return text


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = _expand_prepositions(text)
    text = _remove_accents(text)
    text = re.sub(r'[€$]\s*[\d.,]+|[\d.,]+\s*[€$]', '', text)
    text = re.sub(r'[^\w\s/+]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _apply_synonyms(text: str) -> str:
    # Multi-word synonyms first (longest match)
    for typo, correction in sorted(_SYNONYMS_PRE.items(), key=lambda x: -len(x[0])):
        if typo in text:
            text = text.replace(typo, correction)
    # Single-word typos
    for typo, correction in sorted(_TYPOS.items(), key=lambda x: -len(x[0])):
        if typo in text:
            text = text.replace(typo, correction)
    return text


def _extract_locations(normalized: str) -> tuple:
    """Extract location abbreviations. Returns (cleaned_text, location_suffix)."""
    locations_found = []
    remaining = normalized
    for abbrev, full in sorted(LOCATION_ABBREVS.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(r'\b' + re.escape(abbrev) + r'\b')
        if pattern.search(remaining):
            remaining = pattern.sub('', remaining).strip()
            if full not in locations_found:
                locations_found.append(full)
    remaining = re.sub(r'\s+', ' ', remaining).strip()
    suffix = ", ".join(locations_found) if locations_found else ""
    return remaining, suffix


def _get_priority(key: str) -> str:
    if key in _PRIORITY_CRITICAL:
        return "critical"
    if key in _PRIORITY_SAFETY:
        return "safety"
    return "normal"


def _match_single(normalized: str) -> tuple:
    """Match against service dictionary. Returns (display_title, matched_key, priority) or (None,None,None)."""
    # Exact match
    if normalized in _SERVICES:
        return _SERVICES[normalized], normalized, _get_priority(normalized)
    # Longest substring match
    best_title, best_key, best_len = None, None, 0
    for keyword, title in _SERVICES.items():
        if len(keyword) <= 3:
            if re.search(r'\b' + re.escape(keyword) + r'\b', normalized):
                if len(keyword) > best_len:
                    best_title, best_key, best_len = title, keyword, len(keyword)
        elif keyword in normalized and len(keyword) > best_len:
            best_title, best_key, best_len = title, keyword, len(keyword)
    if best_title:
        return best_title, best_key, _get_priority(best_key)
    return None, None, None


def _best_priority(priorities: list) -> str:
    order = {"critical": 0, "safety": 1, "normal": 2}
    best = "normal"
    for p in priorities:
        if order.get(p, 2) < order.get(best, 2):
            best = p
    return best


# ============== TIRE DETECTION ==============
_QTY_PATTERN = re.compile(r'(\d)\s*x\b|\bx\s*(\d)', re.IGNORECASE)
_QTY_PNEUS_PATTERN = re.compile(r'\b(\d)\s+pneus?\b', re.IGNORECASE)


def _detect_tire(normalized: str) -> dict:
    found_brand = None
    for brand_key, brand_info in sorted(TIRE_BRANDS.items(), key=lambda x: -len(x[0])):
        if brand_key in normalized:
            found_brand = brand_info
            break

    qty = None
    qty_match = _QTY_PATTERN.search(normalized)
    if qty_match:
        qty = int(qty_match.group(1) or qty_match.group(2))
    else:
        qty_pneus = _QTY_PNEUS_PATTERN.search(normalized)
        if qty_pneus:
            qty = int(qty_pneus.group(1))

    has_tire_word = bool(re.search(r'\bpneus?\b', normalized))
    if not found_brand and not (qty and has_tire_word):
        return None

    qty_text = f" ({qty} unidades)" if qty else ""
    if found_brand:
        tier = found_brand["tier"]
        tagline = _tier_taglines.get(tier, "")
        title = f"Pneus {found_brand['display']}{qty_text} — {tagline}" if tagline else f"Pneus {found_brand['display']}{qty_text}"
        return {
            "title": title, "type": "single", "includes": [],
            "priority": "safety", "priority_message": TIRE_PRIORITY_MESSAGE,
            "recommended": tier == "premium", "brand_tier": tier,
        }
    return {
        "title": f"Pneus{qty_text}", "type": "single", "includes": [],
        "priority": "safety", "priority_message": TIRE_PRIORITY_MESSAGE,
        "recommended": False, "brand_tier": None,
    }


# ============== LOGGING ==============
def _log_unmatched(original: str, normalized: str):
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {"original": original, "normalized": normalized, "matched": False,
                 "created_at": datetime.now(timezone.utc).isoformat()}
        entries = []
        if _UNMATCHED_LOG.exists():
            try:
                entries = json.loads(_UNMATCHED_LOG.read_text(encoding="utf-8"))
            except Exception:
                entries = []
        if not any(e.get("normalized") == normalized for e in entries):
            entries.append(entry)
            entries = entries[-500:]
            _UNMATCHED_LOG.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[QUOTE_NORM] Unmatched logged: {normalized}")
    except Exception as e:
        logger.debug(f"[QUOTE_NORM] Log write error: {e}")


def _clean_fallback(raw: str) -> str:
    text = raw.strip()
    for sep in [". ", ".\n", "\n"]:
        if sep in text:
            text = text[:text.index(sep)]
            break
    text = re.sub(r'\s+', ' ', text).strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


# ============== MAIN ENTRY POINT ==============
def normalize_description(raw_description: str) -> dict:
    """Transform a quote option description for display. Never modifies stored data."""
    if not raw_description or not raw_description.strip():
        return {"title": raw_description or "", "type": "single", "includes": [],
                "priority": "normal", "priority_message": PRIORITY_MESSAGES["normal"]}

    normalized = _normalize(raw_description)
    normalized = _apply_synonyms(normalized)

    # Extract locations
    text_no_loc, location_suffix = _extract_locations(normalized)
    text_no_loc = _apply_synonyms(text_no_loc)

    def _append_loc(title: str) -> str:
        return f"{title} ({location_suffix})" if location_suffix else title

    # ---- TIRE (before packages) ----
    tire_result = _detect_tire(normalized)
    if tire_result and "+" not in normalized:
        return tire_result

    # ---- PACKAGE: "+" ----
    if "+" in normalized:
        parts = [p.strip() for p in normalized.split("+") if p.strip()]
        matched_keys, matched_titles = [], []
        tire_in_package = None
        package_locations = []

        for part in parts:
            part = _apply_synonyms(part)
            part_clean, part_loc = _extract_locations(part)
            part_clean = _apply_synonyms(part_clean)
            if part_loc:
                package_locations.append(part_loc)

            tire_part = _detect_tire(part)
            if tire_part:
                matched_titles.append(tire_part["title"])
                matched_keys.append("pneus")
                tire_in_package = tire_part
                continue

            title, key, _ = _match_single(part_clean)
            if not title:
                title, key, _ = _match_single(part)
            if title:
                if part_loc:
                    title = f"{title} ({part_loc})"
                matched_titles.append(title)
                if key:
                    matched_keys.append(key)
            else:
                matched_titles.append(_clean_fallback(part) or part)

        keys_set = frozenset(matched_keys)

        # Shared location for package title
        unique_locs = list(dict.fromkeys(package_locations))
        shared_loc = unique_locs[0] if len(unique_locs) == 1 else ""

        # a) Tire + services → branded pack
        if tire_in_package and len(matched_titles) > 1:
            svc_titles = [t for t in matched_titles if t != tire_in_package["title"]]
            tire_short = tire_in_package["title"].split(" — ")[0]
            title = f"Pack {tire_short} + {' + '.join(svc_titles)} — solucao completa para seguranca e desgaste uniforme"
            return {"title": title, "type": "package", "includes": matched_titles,
                    "priority": "safety", "priority_message": TIRE_PRIORITY_MESSAGE,
                    "recommended": tire_in_package.get("recommended", False),
                    "brand_tier": tire_in_package.get("brand_tier")}

        # b) Known package
        if keys_set in KNOWN_PACKAGES:
            pkg = KNOWN_PACKAGES[keys_set]
            pkg_title = f"{pkg['title']} ({shared_loc})" if shared_loc else pkg["title"]
            return {"title": pkg_title, "type": "package", "includes": matched_titles,
                    "priority": pkg["priority"], "priority_message": PRIORITY_MESSAGES[pkg["priority"]]}

        # c) Compose
        all_p = [_get_priority(k) for k in matched_keys]
        priority = _best_priority(all_p) if all_p else "normal"
        title = " + ".join(matched_titles) if len(matched_titles) > 1 else (matched_titles[0] if matched_titles else normalized.capitalize())
        result = {"title": title, "type": "package", "includes": matched_titles,
                  "priority": priority, "priority_message": PRIORITY_MESSAGES[priority]}
        if tire_in_package:
            result["priority_message"] = TIRE_PRIORITY_MESSAGE
            result["recommended"] = tire_in_package.get("recommended", False)
            result["brand_tier"] = tire_in_package.get("brand_tier")
        return result

    # ---- SMART " e " SPLIT ----
    if " e " in text_no_loc:
        idx = text_no_loc.index(" e ")
        left = _apply_synonyms(text_no_loc[:idx].strip())
        right = _apply_synonyms(text_no_loc[idx + 3:].strip())
        lt, lk, lp = _match_single(left)
        rt, rk, rp = _match_single(right)
        if lt and rt:
            keys_set = frozenset(filter(None, [lk, rk]))
            titles = [_append_loc(lt), _append_loc(rt)]
            if keys_set in KNOWN_PACKAGES:
                pkg = KNOWN_PACKAGES[keys_set]
                pkg_title = _append_loc(pkg["title"])
                return {"title": pkg_title, "type": "package", "includes": titles,
                        "priority": pkg["priority"], "priority_message": PRIORITY_MESSAGES[pkg["priority"]]}
            priority = _best_priority([lp, rp])
            return {"title": f"{_append_loc(lt)} + {_append_loc(rt)}", "type": "package",
                    "includes": titles, "priority": priority, "priority_message": PRIORITY_MESSAGES[priority]}

    # ---- SINGLE ITEM ----
    title, key, priority = _match_single(text_no_loc)
    if not title:
        title, key, priority = _match_single(normalized)
    if title:
        return {"title": _append_loc(title), "type": "single", "includes": [],
                "priority": priority, "priority_message": PRIORITY_MESSAGES[priority]}

    # ---- FALLBACK ----
    _log_unmatched(raw_description, normalized)
    fallback = _clean_fallback(raw_description) or raw_description.strip()
    return {"title": fallback, "type": "single", "includes": [],
            "priority": "normal", "priority_message": PRIORITY_MESSAGES["normal"]}
