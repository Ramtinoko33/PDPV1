"""
Module Loader
Loads optional modules based on config/modules.json
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Path to modules config
CONFIG_PATH = Path(__file__).parent.parent / "config" / "modules.json"


def load_modules_config() -> Dict[str, bool]:
    """Load modules configuration from JSON file."""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
                logger.info(f"[MODULES] Loaded config: {config}")
                return config
        else:
            logger.warning(f"[MODULES] Config file not found: {CONFIG_PATH}")
            return {}
    except Exception as e:
        logger.error(f"[MODULES] Error loading config: {e}")
        return {}


def get_enabled_modules() -> Dict[str, bool]:
    """Get dictionary of module names and their enabled status."""
    return load_modules_config()


def is_module_enabled(module_name: str) -> bool:
    """Check if a specific module is enabled."""
    config = load_modules_config()
    return config.get(module_name, False)


def load_module_router(module_name: str) -> Optional[APIRouter]:
    """
    Dynamically load a module's router if the module is enabled.
    Returns None if module is disabled or doesn't exist.
    """
    if not is_module_enabled(module_name):
        logger.info(f"[MODULES] Module '{module_name}' is disabled, skipping")
        return None
    
    try:
        if module_name == "intake":
            from modules.intake import router
            logger.info(f"[MODULES] Loaded module: {module_name}")
            return router
        elif module_name == "telegram":
            from modules.telegram import router
            logger.info(f"[MODULES] Loaded module: {module_name}")
            return router
        elif module_name == "whatsapp":
            # Future: from modules.whatsapp import router
            logger.info(f"[MODULES] Module '{module_name}' not yet implemented")
            return None
        else:
            logger.warning(f"[MODULES] Unknown module: {module_name}")
            return None
    except ImportError as e:
        logger.error(f"[MODULES] Failed to import module '{module_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"[MODULES] Error loading module '{module_name}': {e}")
        return None


def register_modules(api_router: APIRouter) -> list:
    """
    Register all enabled modules with the main API router.
    Returns list of registered module names.
    """
    registered = []
    config = load_modules_config()
    
    for module_name, enabled in config.items():
        if enabled:
            router = load_module_router(module_name)
            if router:
                api_router.include_router(router)
                registered.append(module_name)
                logger.info(f"[MODULES] Registered module: {module_name}")
    
    if registered:
        logger.info(f"[MODULES] Total modules registered: {len(registered)} - {registered}")
    else:
        logger.info("[MODULES] No modules enabled")
    
    return registered
