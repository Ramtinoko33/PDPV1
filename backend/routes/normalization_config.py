"""
Normalization Config Routes — Admin CRUD for tire brands and services.
Falls back to JSON config if no DB config exists.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from db import db
from core.security import get_current_user
import json
from pathlib import Path

router = APIRouter()
_CONFIG_DIR = Path(__file__).parent.parent / "config"


# ============== SCHEMAS ==============
class TireBrandItem(BaseModel):
    name: str
    aliases: List[str] = []
    tier: str = "mid"

class ServiceItem(BaseModel):
    keyword: str
    display_name: str
    active: bool = True

class NormConfigUpdate(BaseModel):
    tire_brands: Optional[List[TireBrandItem]] = None
    services: Optional[List[ServiceItem]] = None


# ============== HELPERS ==============
def _load_default_tires() -> list:
    """Load default tire brands from JSON config."""
    path = _CONFIG_DIR / "normalizer_tires.json"
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    brands = []
    display_names = cfg.get("display_names", {})
    for tier_name, tier_data in cfg.get("tiers", {}).items():
        for brand_key in tier_data.get("brands", []):
            display = display_names.get(brand_key, brand_key.capitalize())
            aliases = [brand_key]
            # Add known typo corrections as aliases
            for typo, correct in cfg.get("typo_corrections", {}).items():
                if correct == brand_key and typo not in aliases:
                    aliases.append(typo)
            brands.append({"name": display, "aliases": aliases, "tier": tier_name})
    return brands


def _load_default_services() -> list:
    """Load default services from JSON config."""
    path = _CONFIG_DIR / "normalizer_services.json"
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    services = []
    seen = set()
    for keyword, display_name in cfg.get("services", {}).items():
        if display_name not in seen:
            services.append({"keyword": keyword, "display_name": display_name, "active": True})
            seen.add(display_name)
    return services


# ============== ENDPOINTS ==============
@router.get("/normalization-config")
async def get_normalization_config(current_user: dict = Depends(get_current_user)):
    """Get current normalization config (DB or defaults)."""
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    config = await db.normalization_config.find_one({"type": "main"}, {"_id": 0})

    if config:
        return {
            "tire_brands": config.get("tire_brands", []),
            "services": config.get("services", []),
            "updated_at": config.get("updated_at"),
            "source": "database",
        }

    # Fallback to JSON defaults
    return {
        "tire_brands": _load_default_tires(),
        "services": _load_default_services(),
        "updated_at": None,
        "source": "default",
    }


@router.put("/normalization-config/tire-brands")
async def update_tire_brands(data: dict, current_user: dict = Depends(get_current_user)):
    """Update tire brands config."""
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    brands = data.get("tire_brands", [])

    # Validate
    names = set()
    all_aliases = set()
    for b in brands:
        if not b.get("name", "").strip():
            raise HTTPException(status_code=400, detail="Nome da marca não pode ser vazio")
        if b["name"] in names:
            raise HTTPException(status_code=400, detail=f"Marca duplicada: {b['name']}")
        names.add(b["name"])
        for alias in b.get("aliases", []):
            if alias in all_aliases:
                raise HTTPException(status_code=400, detail=f"Alias duplicado: {alias}")
            all_aliases.add(alias)

    now = datetime.now(timezone.utc).isoformat()
    await db.normalization_config.update_one(
        {"type": "main"},
        {"$set": {"tire_brands": brands, "updated_at": now}},
        upsert=True,
    )

    # Rebuild JSON config for normalizer hot-reload
    await _rebuild_tire_json(brands)

    return {"status": "success", "count": len(brands)}


@router.put("/normalization-config/services")
async def update_services(data: dict, current_user: dict = Depends(get_current_user)):
    """Update services config."""
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    services = data.get("services", [])

    # Validate
    keywords = set()
    for s in services:
        if not s.get("keyword", "").strip():
            raise HTTPException(status_code=400, detail="Keyword não pode ser vazio")
        if not s.get("display_name", "").strip():
            raise HTTPException(status_code=400, detail="Nome de exibição não pode ser vazio")
        if s["keyword"] in keywords:
            raise HTTPException(status_code=400, detail=f"Keyword duplicado: {s['keyword']}")
        keywords.add(s["keyword"])

    now = datetime.now(timezone.utc).isoformat()
    await db.normalization_config.update_one(
        {"type": "main"},
        {"$set": {"services": services, "updated_at": now}},
        upsert=True,
    )

    # Rebuild JSON config for normalizer hot-reload
    await _rebuild_services_json(services)

    return {"status": "success", "count": len(services)}


@router.get("/normalization-config/positions")
async def get_positions(current_user: dict = Depends(get_current_user)):
    """Get position tokens (read-only)."""
    if current_user["role"] not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Sem permissão")

    path = _CONFIG_DIR / "normalizer_abbreviations.json"
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return {
        "axis": cfg.get("axis", {}),
        "side": cfg.get("side", {}),
        "combos": cfg.get("combos", {}),
        "other": cfg.get("other", {}),
    }


# ============== REBUILD JSON (for hot-reload) ==============
async def _rebuild_tire_json(brands: list):
    """Rebuild normalizer_tires.json from DB config."""
    path = _CONFIG_DIR / "normalizer_tires.json"
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Rebuild tiers and display_names
    tiers = {"premium": {"tagline": cfg["tiers"]["premium"]["tagline"], "brands": []},
             "mid": {"tagline": cfg["tiers"]["mid"]["tagline"], "brands": []},
             "budget": {"tagline": cfg["tiers"]["budget"]["tagline"], "brands": []}}
    display_names = {}
    typo_corrections = {}

    for b in brands:
        tier = b.get("tier", "mid")
        if tier not in tiers:
            tier = "mid"
        primary_alias = b["aliases"][0] if b.get("aliases") else b["name"].lower()
        tiers[tier]["brands"].append(primary_alias)
        display_names[primary_alias] = b["name"]
        # Additional aliases → typo corrections
        for alias in b.get("aliases", [])[1:]:
            typo_corrections[alias] = primary_alias
            display_names[alias] = b["name"]

    cfg["tiers"] = tiers
    cfg["display_names"] = display_names
    cfg["typo_corrections"] = typo_corrections

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # Force normalizer to reload
    _reload_normalizer()


async def _rebuild_services_json(services: list):
    """Rebuild normalizer_services.json services section from DB config."""
    path = _CONFIG_DIR / "normalizer_services.json"
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    new_services = {}
    for s in services:
        if s.get("active", True):
            new_services[s["keyword"]] = s["display_name"]

    cfg["services"] = new_services

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    _reload_normalizer()


def _reload_normalizer():
    """Force normalizer module to reload config."""
    try:
        import importlib
        import services.quote_normalizer as qn
        importlib.reload(qn)
    except Exception:
        pass  # Hot reload will catch file change
