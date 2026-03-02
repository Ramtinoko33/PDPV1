"""
Vehicle routes.
"""
from fastapi import APIRouter, Depends, HTTPException

from db import db
from core.security import get_current_user

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a vehicle."""
    result = await db.vehicles.delete_one({"id": vehicle_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Veículo não encontrado")
    return {"message": "Veículo eliminado"}
