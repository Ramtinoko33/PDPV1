"""
Quote Description Normalizer - Display-only transformation layer.
Never modifies stored data. Only transforms for customer-facing display.
"""
import re
import unicodedata


# ============== SYNONYM / TYPO MAP ==============
SYNONYMS = {
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
    "amortecedor": "amortecedores",
    "travao": "travoes",
    "travão": "travoes",
    "travoes": "travoes",
    "travões": "travoes",
    "oleo": "oleo",
    "óleo": "oleo",
    "peneu": "pneu",
    "peneus": "pneus",
    "filtro ar": "filtro de ar",
    "filtro oleo": "filtro de oleo",
    "filtro óleo": "filtro de oleo",
    "filtro habitaculo": "filtro de habitaculo",
    "filtro habitáculo": "filtro de habitaculo",
    "distribucao": "distribuicao",
    "distribuição": "distribuicao",
    "distribuicao": "distribuicao",
    "embraiagen": "embraiagem",
    "embreagem": "embraiagem",
    "suspensao": "suspensao",
    "suspensão": "suspensao",
    "direcao": "direcao",
    "direção": "direcao",
    "correia": "correia",
    "corrsia": "correia",
    "vela": "velas",
    "velas ignicao": "velas de ignicao",
    "escape": "escape",
    "escapamento": "escape",
    "catalizador": "catalisador",
    "mao de obra": "mao de obra",
    "mão de obra": "mao de obra",
}


# ============== KNOWN ITEMS (keyword → display info) ==============
KNOWN_ITEMS = {
    # Pneus
    "pneu": {"title": "Pneu", "priority": "safety"},
    "pneus": {"title": "Pneus", "priority": "safety"},
    # Travões
    "pastilhas": {"title": "Pastilhas de travão", "priority": "critical"},
    "discos": {"title": "Discos de travão", "priority": "critical"},
    "travoes": {"title": "Sistema de travagem", "priority": "critical"},
    "disco": {"title": "Disco de travão", "priority": "critical"},
    # Suspensão
    "amortecedores": {"title": "Amortecedores", "priority": "safety"},
    "amortecedor": {"title": "Amortecedor", "priority": "safety"},
    "molas": {"title": "Molas de suspensão", "priority": "safety"},
    "suspensao": {"title": "Suspensão", "priority": "safety"},
    # Direção
    "alinhamento": {"title": "Alinhamento de direção", "priority": "normal"},
    "equilibragem": {"title": "Equilibragem", "priority": "normal"},
    "direcao": {"title": "Direção", "priority": "safety"},
    # Motor / Manutenção
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
    "distribuicao": {"title": "Kit de distribuição", "priority": "safety"},
    "embraiagem": {"title": "Embraiagem", "priority": "safety"},
    "bateria": {"title": "Bateria", "priority": "normal"},
    "alternador": {"title": "Alternador", "priority": "normal"},
    "motor arranque": {"title": "Motor de arranque", "priority": "normal"},
    "radiador": {"title": "Radiador", "priority": "normal"},
    "bomba agua": {"title": "Bomba de água", "priority": "normal"},
    "bomba de agua": {"title": "Bomba de água", "priority": "normal"},
    "catalisador": {"title": "Catalisador", "priority": "normal"},
    "escape": {"title": "Sistema de escape", "priority": "normal"},
    "egr": {"title": "Válvula EGR", "priority": "normal"},
    "permutador": {"title": "Permutador", "priority": "normal"},
    "permutador da egr": {"title": "Permutador da EGR", "priority": "normal"},
    "turbo": {"title": "Turbo", "priority": "normal"},
    # Serviços
    "revisao": {"title": "Revisão", "priority": "normal"},
    "inspecao": {"title": "Inspeção", "priority": "normal"},
    "diagnostico": {"title": "Diagnóstico", "priority": "normal"},
    "mao de obra": {"title": "Mão de obra", "priority": "normal"},
    "pack rosa": {"title": "Pack Rosa", "priority": "normal"},
}


# ============== KNOWN PACKAGES ==============
KNOWN_PACKAGES = {
    frozenset(["pastilhas", "discos"]): {
        "title": "Kit de travagem (pastilhas + discos)",
        "priority": "critical",
    },
    frozenset(["pastilhas", "discos", "travoes"]): {
        "title": "Sistema de travagem completo",
        "priority": "critical",
    },
    frozenset(["alinhamento", "equilibragem"]): {
        "title": "Alinhamento e equilibragem",
        "priority": "normal",
    },
    frozenset(["oleo", "filtro de oleo"]): {
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


# ============== NORMALIZATION ==============
def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Lowercase, remove accents, remove punctuation/prices, trim."""
    text = text.lower().strip()
    text = _remove_accents(text)
    # Remove prices (e.g. 123.45€, 123,45 €, €123)
    text = re.sub(r'[€$]\s*[\d.,]+|[\d.,]+\s*[€$]', '', text)
    # Remove punctuation except / + and spaces
    text = re.sub(r'[^\w\s/+]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _try_split_package(normalized: str) -> list:
    """Try to split text into package parts using + or ' e ' separator.
    Only splits on ' e ' if both sides match known items."""
    # Explicit "+" always splits
    if "+" in normalized:
        return [p.strip() for p in normalized.split("+") if p.strip()]

    # Try " e " — only if both sides match known keywords
    if " e " in normalized:
        idx = normalized.index(" e ")
        left = normalized[:idx].strip()
        right = normalized[idx + 3:].strip()
        left_match = _match_single(_apply_synonyms(left))
        right_match = _match_single(_apply_synonyms(right))
        if left_match and right_match:
            return [left, right]

    return None


def _apply_synonyms(text: str) -> str:
    """Apply synonym/typo corrections."""
    # Try multi-word synonyms first (longest match)
    for typo, correction in sorted(SYNONYMS.items(), key=lambda x: -len(x[0])):
        if typo in text:
            text = text.replace(typo, correction)
    return text


def _match_single(normalized: str) -> dict:
    """Try to match a single normalized text against known items."""
    # Exact key match
    if normalized in KNOWN_ITEMS:
        return KNOWN_ITEMS[normalized]

    # Keyword containment (longest match first)
    best_match = None
    best_len = 0
    for keyword, info in KNOWN_ITEMS.items():
        if keyword in normalized and len(keyword) > best_len:
            best_match = info
            best_len = len(keyword)

    return best_match


# ============== MAIN ENTRY POINT ==============
def normalize_description(raw_description: str) -> dict:
    """
    Transform a quote option description for display.
    Returns: { title, type, includes, priority }
    Never modifies stored data.
    """
    if not raw_description or not raw_description.strip():
        return {
            "title": raw_description or "",
            "type": "single",
            "includes": [],
            "priority": "normal",
        }

    normalized = _normalize(raw_description)
    normalized = _apply_synonyms(normalized)

    # Detect package (explicit "+" or smart " e " split)
    parts = _try_split_package(normalized)
    is_package = parts is not None and len(parts) > 1

    if is_package:
        matched_keys = []
        matched_titles = []

        for part in parts:
            part = _apply_synonyms(part)
            match = _match_single(part)
            if match:
                matched_titles.append(match["title"])
                # Find the key that matched
                for kw in KNOWN_ITEMS:
                    if kw in part:
                        matched_keys.append(kw)
                        break
            else:
                # Keep cleaned part as-is
                matched_titles.append(part.strip().capitalize())

        keys_set = frozenset(matched_keys)

        # a) Package exact match
        if keys_set in KNOWN_PACKAGES:
            pkg = KNOWN_PACKAGES[keys_set]
            return {
                "title": pkg["title"],
                "type": "package",
                "includes": matched_titles,
                "priority": pkg["priority"],
            }

        # b) Package composition — build title from parts
        priority = _best_priority([
            KNOWN_ITEMS.get(k, {}).get("priority", "normal") for k in matched_keys
        ])

        if len(matched_titles) > 1:
            title = " + ".join(matched_titles)
        else:
            title = matched_titles[0] if matched_titles else normalized.capitalize()

        return {
            "title": title,
            "type": "package",
            "includes": matched_titles,
            "priority": priority,
        }

    # Single item
    match = _match_single(normalized)
    if match:
        return {
            "title": match["title"],
            "type": "single",
            "includes": [],
            "priority": match["priority"],
        }

    # Fallback: capitalize cleaned text, one sentence max
    fallback = raw_description.strip()
    # Truncate at first sentence boundary if multiple
    for sep in [". ", ".\n", "\n"]:
        if sep in fallback:
            fallback = fallback[:fallback.index(sep)]
            break
    # Capitalize first letter
    if fallback:
        fallback = fallback[0].upper() + fallback[1:]

    return {
        "title": fallback,
        "type": "single",
        "includes": [],
        "priority": "normal",
    }


def _best_priority(priorities: list) -> str:
    """Return highest priority from list."""
    order = {"critical": 0, "safety": 1, "normal": 2}
    best = "normal"
    for p in priorities:
        if order.get(p, 2) < order.get(best, 2):
            best = p
    return best
