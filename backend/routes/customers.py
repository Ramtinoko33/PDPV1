"""
Customer management routes.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from db import db
from schemas.user import UserRole
from schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    VehicleCreate,
    VehicleResponse,
)
from core.security import get_current_user

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    current_user: dict = Depends(get_current_user),
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """List all customers with optional search."""
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"nif": {"$regex": search, "$options": "i"}},
            {"phones": {"$regex": search, "$options": "i"}},
            {"emails": {"$regex": search, "$options": "i"}}
        ]
    
    customers = await db.customers.find(query, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    
    if not customers:
        return []
    
    # Batch fetch all vehicles for these customers (avoid N+1)
    customer_ids = [c["id"] for c in customers]
    all_vehicles = await db.vehicles.find(
        {"customer_id": {"$in": customer_ids}}, 
        {"_id": 0}
    ).to_list(1000)
    
    # Group vehicles by customer_id
    vehicles_by_customer = {}
    for v in all_vehicles:
        cid = v["customer_id"]
        if cid not in vehicles_by_customer:
            vehicles_by_customer[cid] = []
        vehicles_by_customer[cid].append(v)
    
    # Build result with vehicles
    result = []
    for c in customers:
        c["vehicles"] = vehicles_by_customer.get(c["id"], [])
        c["ticket_count"] = 0  # Skip ticket count query for list performance
        result.append(CustomerResponse(**c))
    
    return result


@router.get("/search")
async def search_customers(
    current_user: dict = Depends(get_current_user),
    q: str = ""
):
    """Search customers by phone, plate or name for auto-complete."""
    if len(q) < 2:
        return []
    
    customer_ids_found = set()
    customers_data = {}
    
    # Search by phone
    customers_by_phone = await db.customers.find(
        {"phones": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    for c in customers_by_phone:
        if c["id"] not in customer_ids_found:
            customer_ids_found.add(c["id"])
            customers_data[c["id"]] = c
    
    # Search by plate
    vehicles_by_plate = await db.vehicles.find(
        {"plate": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    plate_customer_ids = [v["customer_id"] for v in vehicles_by_plate if v["customer_id"] not in customer_ids_found]
    if plate_customer_ids:
        customers_from_plates = await db.customers.find(
            {"id": {"$in": plate_customer_ids}},
            {"_id": 0}
        ).to_list(10)
        for c in customers_from_plates:
            if c["id"] not in customer_ids_found:
                customer_ids_found.add(c["id"])
                customers_data[c["id"]] = c
    
    # Search by name
    customers_by_name = await db.customers.find(
        {"name": {"$regex": q, "$options": "i"}},
        {"_id": 0}
    ).limit(10).to_list(10)
    
    for c in customers_by_name:
        if c["id"] not in customer_ids_found:
            customer_ids_found.add(c["id"])
            customers_data[c["id"]] = c
    
    # Batch fetch all vehicles
    if customer_ids_found:
        all_vehicles = await db.vehicles.find(
            {"customer_id": {"$in": list(customer_ids_found)}},
            {"_id": 0}
        ).to_list(500)
        
        vehicles_by_customer = {}
        for v in all_vehicles:
            cid = v["customer_id"]
            if cid not in vehicles_by_customer:
                vehicles_by_customer[cid] = []
            vehicles_by_customer[cid].append({"plate": v["plate"], "model": v.get("model")})
    else:
        vehicles_by_customer = {}
    
    # Build results
    results = []
    for cid, c in customers_data.items():
        results.append({
            "id": c["id"],
            "name": c["name"],
            "phones": c.get("phones", []),
            "emails": c.get("emails", []),
            "vehicles": vehicles_by_customer.get(cid, [])
        })
    
    return results[:15]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific customer by ID."""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    customer["vehicles"] = vehicles
    
    ticket_count = await db.tickets.count_documents({
        "$or": [
            {"customer_phone": {"$in": customer.get("phones", [])}},
            {"customer_email": {"$in": customer.get("emails", [])}}
        ]
    })
    customer["ticket_count"] = ticket_count
    
    return CustomerResponse(**customer)


@router.get("/{customer_id}/history")
async def get_customer_history(customer_id: str, current_user: dict = Depends(get_current_user)):
    """Get all tickets and vehicles for a customer."""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    vehicle_plates = [v["plate"] for v in vehicles]
    
    query = {"$or": []}
    if customer.get("phones"):
        query["$or"].append({"customer_phone": {"$in": customer["phones"]}})
    if customer.get("emails"):
        query["$or"].append({"customer_email": {"$in": customer["emails"]}})
    if vehicle_plates:
        query["$or"].append({"vehicle_plate": {"$in": vehicle_plates}})
    
    if not query["$or"]:
        tickets = []
    else:
        tickets = await db.tickets.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    return {
        "customer": customer,
        "vehicles": vehicles,
        "tickets": tickets,
        "total_tickets": len(tickets)
    }


@router.post("", response_model=CustomerResponse)
async def create_customer(customer_data: CustomerCreate, current_user: dict = Depends(get_current_user)):
    """Create a new customer."""
    now = datetime.now(timezone.utc).isoformat()
    customer_id = str(uuid.uuid4())
    
    customer_doc = {
        "id": customer_id,
        "code": customer_data.code,
        "name": customer_data.name,
        "nif": customer_data.nif,
        "customer_type": customer_data.customer_type,
        "address": customer_data.address,
        "phones": customer_data.phones,
        "fax": customer_data.fax,
        "emails": customer_data.emails,
        "created_at": now,
        "updated_at": now
    }
    await db.customers.insert_one(customer_doc)
    
    # Create vehicles
    vehicles = []
    for v in customer_data.vehicles:
        vehicle_id = str(uuid.uuid4())
        vehicle_doc = {
            "id": vehicle_id,
            "customer_id": customer_id,
            "plate": v.plate.upper().strip(),
            "model": v.model,
            "observations": v.observations
        }
        await db.vehicles.insert_one(vehicle_doc)
        vehicles.append(vehicle_doc)
    
    customer_doc["vehicles"] = vehicles
    customer_doc["ticket_count"] = 0
    return CustomerResponse(**customer_doc)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, customer_data: CustomerUpdate, current_user: dict = Depends(get_current_user)):
    """Update a customer."""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if customer_data.name is not None:
        update_doc["name"] = customer_data.name
    if customer_data.nif is not None:
        update_doc["nif"] = customer_data.nif
    if customer_data.customer_type is not None:
        update_doc["customer_type"] = customer_data.customer_type
    if customer_data.address is not None:
        update_doc["address"] = customer_data.address
    if customer_data.phones is not None:
        update_doc["phones"] = customer_data.phones
    if customer_data.fax is not None:
        update_doc["fax"] = customer_data.fax
    if customer_data.emails is not None:
        update_doc["emails"] = customer_data.emails
    
    await db.customers.update_one({"id": customer_id}, {"$set": update_doc})
    
    updated = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    vehicles = await db.vehicles.find({"customer_id": customer_id}, {"_id": 0}).to_list(100)
    updated["vehicles"] = vehicles
    updated["ticket_count"] = 0
    return CustomerResponse(**updated)


@router.delete("/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a customer (admin only)."""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Apenas admins podem eliminar clientes")
    
    result = await db.customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    await db.vehicles.delete_many({"customer_id": customer_id})
    
    return {"message": "Cliente eliminado"}


@router.post("/{customer_id}/vehicles", response_model=VehicleResponse)
async def add_vehicle(customer_id: str, vehicle_data: VehicleCreate, current_user: dict = Depends(get_current_user)):
    """Add a vehicle to a customer."""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    vehicle_id = str(uuid.uuid4())
    vehicle_doc = {
        "id": vehicle_id,
        "customer_id": customer_id,
        "plate": vehicle_data.plate.upper().strip(),
        "model": vehicle_data.model,
        "observations": vehicle_data.observations
    }
    await db.vehicles.insert_one(vehicle_doc)
    return VehicleResponse(**vehicle_doc)
