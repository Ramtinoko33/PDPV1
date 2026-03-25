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
    q: str = "",
    plate: str = "",
    phone: str = "",
    name: str = ""
):
    """
    Search customers by phone, plate or name for auto-complete.
    Also searches in past tickets for matches.
    Returns multiple matches if found - frontend should let user choose.
    """
    # Use specific field if provided, otherwise use general query
    search_plate = plate.strip().upper() if plate else ""
    search_phone = phone.strip() if phone else ""
    search_name = name.strip() if name else ""
    general_query = q.strip() if q else ""
    
    # Need at least 2 chars to search
    if not any([len(search_plate) >= 2, len(search_phone) >= 2, len(search_name) >= 2, len(general_query) >= 2]):
        return []
    
    customer_ids_found = set()
    customers_data = {}
    
    # 1. Search in customers collection by phone
    if search_phone or general_query:
        phone_query = search_phone or general_query
        customers_by_phone = await db.customers.find(
            {"phones": {"$regex": phone_query, "$options": "i"}},
            {"_id": 0}
        ).limit(15).to_list(15)
        
        for c in customers_by_phone:
            if c["id"] not in customer_ids_found:
                customer_ids_found.add(c["id"])
                customers_data[c["id"]] = c
    
    # 2. Search in vehicles collection by plate
    if search_plate or general_query:
        plate_query = search_plate or general_query
        vehicles_by_plate = await db.vehicles.find(
            {"plate": {"$regex": plate_query, "$options": "i"}},
            {"_id": 0}
        ).limit(15).to_list(15)
        
        plate_customer_ids = [v["customer_id"] for v in vehicles_by_plate if v["customer_id"] not in customer_ids_found]
        if plate_customer_ids:
            customers_from_plates = await db.customers.find(
                {"id": {"$in": plate_customer_ids}},
                {"_id": 0}
            ).to_list(15)
            for c in customers_from_plates:
                if c["id"] not in customer_ids_found:
                    customer_ids_found.add(c["id"])
                    customers_data[c["id"]] = c
    
    # 3. Search in customers collection by name
    if search_name or general_query:
        name_query = search_name or general_query
        customers_by_name = await db.customers.find(
            {"name": {"$regex": name_query, "$options": "i"}},
            {"_id": 0}
        ).limit(15).to_list(15)
        
        for c in customers_by_name:
            if c["id"] not in customer_ids_found:
                customer_ids_found.add(c["id"])
                customers_data[c["id"]] = c
    
    # 4. Search in past tickets by plate, phone, or email
    ticket_query_conditions = []
    if search_plate or general_query:
        ticket_query_conditions.append({"vehicle_plate": {"$regex": search_plate or general_query, "$options": "i"}})
    if search_phone or general_query:
        ticket_query_conditions.append({"customer_phone": {"$regex": search_phone or general_query, "$options": "i"}})
    if search_name or general_query:
        ticket_query_conditions.append({"customer_name": {"$regex": search_name or general_query, "$options": "i"}})
    
    if ticket_query_conditions:
        tickets = await db.tickets.find(
            {"$or": ticket_query_conditions},
            {"_id": 0, "customer_name": 1, "customer_phone": 1, "customer_email": 1, "vehicle_plate": 1}
        ).sort("created_at", -1).limit(20).to_list(20)
        
        # Create virtual customer entries from tickets that don't match existing customers
        for t in tickets:
            # Generate a unique key for deduplication
            ticket_key = f"ticket_{t.get('customer_phone', '')}_{t.get('vehicle_plate', '')}"
            if ticket_key not in customers_data and t.get("customer_name"):
                customers_data[ticket_key] = {
                    "id": ticket_key,
                    "name": t.get("customer_name", ""),
                    "phones": [t["customer_phone"]] if t.get("customer_phone") else [],
                    "emails": [t["customer_email"]] if t.get("customer_email") else [],
                    "from_ticket": True,
                    "_plate": t.get("vehicle_plate")  # Temporary for building result
                }
    
    # Batch fetch all vehicles for found customers
    real_customer_ids = [cid for cid in customer_ids_found]
    if real_customer_ids:
        all_vehicles = await db.vehicles.find(
            {"customer_id": {"$in": real_customer_ids}},
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
    seen_combinations = set()
    
    for cid, c in customers_data.items():
        # Get phone and email (first available)
        phone = c.get("phones", [])[0] if c.get("phones") else ""
        email = c.get("emails", [])[0] if c.get("emails") else ""
        name = c.get("name", "")
        
        # Get plates
        if c.get("from_ticket"):
            plates = [c.get("_plate")] if c.get("_plate") else []
        else:
            plates = [v["plate"] for v in vehicles_by_customer.get(cid, [])]
        
        # Deduplicate by name+phone combination
        combo_key = f"{name}_{phone}"
        if combo_key in seen_combinations:
            continue
        seen_combinations.add(combo_key)
        
        results.append({
            "id": cid,
            "name": name,
            "phone": phone,
            "email": email,
            "phones": c.get("phones", []),
            "emails": c.get("emails", []),
            "plates": plates,
            "display": f"{name}" + (f" - {phone}" if phone else "") + (f" - {email}" if email else "") + (f" - {', '.join(plates)}" if plates else ""),
            "from_ticket": c.get("from_ticket", False)
        })
    
    # Sort by name
    results.sort(key=lambda x: x["name"].lower())
    
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


@router.post("/import")
async def import_customers(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Import customers from Excel file."""
    if current_user["role"] not in [UserRole.ADMIN.value, UserRole.SUPERVISOR.value]:
        raise HTTPException(status_code=403, detail="Sem permissão para importar")
    
    import pandas as pd
    import io
    
    content = await file.read()
    xlsx = pd.ExcelFile(io.BytesIO(content))
    
    imported_customers = 0
    imported_vehicles = 0
    errors = []
    
    customers_df = None
    vehicles_df = None
    
    for sheet in xlsx.sheet_names:
        if 'cliente' in sheet.lower():
            customers_df = pd.read_excel(xlsx, sheet_name=sheet)
        elif 'viatura' in sheet.lower():
            vehicles_df = pd.read_excel(xlsx, sheet_name=sheet)
    
    if customers_df is None:
        raise HTTPException(status_code=400, detail="Folha de clientes não encontrada")
    
    now = datetime.now(timezone.utc).isoformat()
    customer_map = {}
    
    for _, row in customers_df.iterrows():
        try:
            code = str(row.get('Código', '')).strip()
            if not code or code == 'nan':
                continue
            
            name = str(row.get('Nome', '')).strip()
            if not name or name == 'nan':
                continue
            
            if code not in customer_map:
                customer_map[code] = {
                    "code": code,
                    "name": name,
                    "nif": str(row.get('Nif', '')).strip() if pd.notna(row.get('Nif')) else None,
                    "customer_type": str(row.get('tipo de cliente', '')).strip() if pd.notna(row.get('tipo de cliente')) else None,
                    "address": str(row.get('Morada', '')).strip() if pd.notna(row.get('Morada')) else None,
                    "phones": set(),
                    "fax": str(row.get('Fax', '')).strip() if pd.notna(row.get('Fax')) else None,
                    "emails": set()
                }
            
            for phone_col in ['Telefone1', 'Telefone2']:
                phone = row.get(phone_col)
                if pd.notna(phone):
                    phone_str = str(int(phone) if isinstance(phone, float) else phone).strip()
                    if phone_str and phone_str != 'nan':
                        customer_map[code]["phones"].add(phone_str)
            
            email = row.get('Email')
            if pd.notna(email):
                email_str = str(email).strip()
                if email_str and email_str != 'nan' and '@' in email_str:
                    customer_map[code]["emails"].add(email_str)
        except Exception as e:
            errors.append(f"Erro na linha cliente: {str(e)}")
    
    customer_id_map = {}
    for code, cdata in customer_map.items():
        try:
            existing = await db.customers.find_one({"code": code})
            if existing:
                customer_id_map[cdata["name"]] = existing["id"]
                await db.customers.update_one(
                    {"id": existing["id"]},
                    {"$addToSet": {
                        "phones": {"$each": list(cdata["phones"])},
                        "emails": {"$each": list(cdata["emails"])}
                    }}
                )
                continue
            
            customer_id = str(uuid.uuid4())
            customer_doc = {
                "id": customer_id,
                "code": code,
                "name": cdata["name"],
                "nif": cdata["nif"],
                "customer_type": cdata["customer_type"],
                "address": cdata["address"],
                "phones": list(cdata["phones"]),
                "fax": cdata["fax"],
                "emails": list(cdata["emails"]),
                "created_at": now,
                "updated_at": now
            }
            await db.customers.insert_one(customer_doc)
            customer_id_map[cdata["name"]] = customer_id
            imported_customers += 1
        except Exception as e:
            errors.append(f"Erro ao criar cliente {cdata['name']}: {str(e)}")
    
    if vehicles_df is not None:
        for _, row in vehicles_df.iterrows():
            try:
                plate = str(row.get('Matrícula', '')).strip().upper()
                if not plate or plate == 'NAN':
                    continue
                
                client_name = str(row.get('Cliente', '')).strip()
                model = str(row.get('Modelo', '')).strip() if pd.notna(row.get('Modelo')) else None
                obs = str(row.get('Observações', '')).strip() if pd.notna(row.get('Observações')) else None
                
                customer_id = customer_id_map.get(client_name)
                if not customer_id:
                    customer = await db.customers.find_one({"name": client_name}, {"_id": 0, "id": 1})
                    if customer:
                        customer_id = customer["id"]
                    else:
                        continue
                
                existing = await db.vehicles.find_one({"plate": plate})
                if existing:
                    continue
                
                vehicle_doc = {
                    "id": str(uuid.uuid4()),
                    "customer_id": customer_id,
                    "plate": plate,
                    "model": model,
                    "observations": obs
                }
                await db.vehicles.insert_one(vehicle_doc)
                imported_vehicles += 1
            except Exception as e:
                errors.append(f"Erro ao criar veículo: {str(e)}")
    
    return {
        "message": "Importação concluída",
        "imported_customers": imported_customers,
        "imported_vehicles": imported_vehicles,
        "errors": errors[:10]
    }
