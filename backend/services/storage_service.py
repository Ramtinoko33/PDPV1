"""
Storage Service Module.
Contains functions for object storage (Emergent Object Storage) operations.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# File storage - Local (temporary) and Object Storage (persistent)
ROOT_DIR = Path(__file__).parent.parent
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Object Storage configuration
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
APP_NAME = "pdpv-tickets"  # Prefix all paths to avoid bucket collisions
_storage_key = None  # Module-level, set once and reused globally


def init_storage():
    """Initialize object storage - call once at startup."""
    global _storage_key
    if _storage_key:
        return _storage_key
    if not EMERGENT_KEY:
        return None
    try:
        import requests as req
        resp = req.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        return _storage_key
    except Exception as e:
        logger.error(f"Failed to initialize object storage: {e}")
        return None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload file to object storage."""
    key = init_storage()
    if not key:
        raise Exception("Object storage not initialized")
    import requests as req
    resp = req.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple:
    """Download file from object storage."""
    key = init_storage()
    if not key:
        raise Exception("Object storage not initialized")
    import requests as req
    resp = req.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def get_storage_client():
    """Get storage key, initializing if needed."""
    return init_storage()


def is_storage_available() -> bool:
    """Check if object storage is available."""
    return init_storage() is not None
