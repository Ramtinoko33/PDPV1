"""
Customer Auto-Creation Service
Handles automatic creation of customers and vehicles when they don't exist in the database.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import logging

from db import db

logger = logging.getLogger(__name__)


async def find_or_create_customer_vehicle(
    license_plate: Optional[str],
    customer_name: str,
    customer_phone: Optional[str] = None,
    customer_email: Optional[str] = None,
    vehicle_brand: Optional[str] = None,
    vehicle_model: Optional[str] = None,
    source: str = "auto_created"
) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Find existing customer/vehicle by license plate, or create new ones if they don't exist.
    
    Returns:
        Tuple of (customer_id, vehicle_id, was_created)
        - If plate not provided: (None, None, False)
        - If found existing: (customer_id, vehicle_id, False)
        - If created new: (customer_id, vehicle_id, True)
    """
    if not license_plate:
        return None, None, False
    
    # Normalize plate
    plate = license_plate.upper().replace(" ", "-")
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        # 1. Check if vehicle exists
        existing_vehicle = await db.vehicles.find_one(
            {"plate": {"$regex": f"^{plate}$", "$options": "i"}},
            {"_id": 0, "id": 1, "customer_id": 1}
        )
        
        if existing_vehicle:
            # Vehicle exists - check if we should update customer data
            customer_id = existing_vehicle.get("customer_id")
            vehicle_id = existing_vehicle.get("id")
            
            if customer_id:
                # Update customer with any new info
                updates = {}
                if customer_email:
                    # Only update email if current is empty
                    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0, "email": 1})
                    if customer and not customer.get("email"):
                        updates["email"] = customer_email
                
                if customer_phone:
                    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0, "phone": 1})
                    if customer and not customer.get("phone"):
                        updates["phone"] = customer_phone
                
                if updates:
                    updates["updated_at"] = now
                    await db.customers.update_one({"id": customer_id}, {"$set": updates})
                    logger.info(f"[AUTO-CREATE] Updated customer {customer_id} with new data")
            
            logger.info(f"[AUTO-CREATE] Found existing vehicle {plate}")
            return customer_id, vehicle_id, False
        
        # 2. Check if customer exists by phone or name
        existing_customer = None
        if customer_phone:
            existing_customer = await db.customers.find_one(
                {"phone": customer_phone},
                {"_id": 0, "id": 1}
            )
        
        # 3. Create customer if doesn't exist
        if existing_customer:
            customer_id = existing_customer["id"]
            logger.info(f"[AUTO-CREATE] Found existing customer by phone: {customer_id}")
            
            # Update customer with email if missing
            if customer_email:
                customer = await db.customers.find_one({"id": customer_id}, {"_id": 0, "email": 1})
                if customer and not customer.get("email"):
                    await db.customers.update_one(
                        {"id": customer_id},
                        {"$set": {"email": customer_email, "updated_at": now}}
                    )
        else:
            # Create new customer
            customer_id = str(uuid.uuid4())
            customer_doc = {
                "id": customer_id,
                "name": customer_name,
                "phone": customer_phone or "",
                "email": customer_email or "",
                "nif": "",
                "notes": "",
                "source": source,
                "created_at": now,
                "updated_at": now
            }
            await db.customers.insert_one(customer_doc)
            logger.info(f"[AUTO-CREATE] Created new customer: {customer_name} ({customer_id})")
        
        # 4. Create vehicle linked to customer
        vehicle_id = str(uuid.uuid4())
        vehicle_doc = {
            "id": vehicle_id,
            "plate": plate,
            "brand": vehicle_brand or "",
            "model": vehicle_model or "",
            "customer_id": customer_id,
            "source": source,
            "created_at": now,
            "updated_at": now
        }
        await db.vehicles.insert_one(vehicle_doc)
        logger.info(f"[AUTO-CREATE] Created new vehicle: {plate} ({vehicle_id})")
        
        return customer_id, vehicle_id, True
        
    except Exception as e:
        logger.error(f"[AUTO-CREATE] Error: {e}")
        return None, None, False


async def get_customer_stats() -> dict:
    """
    Get customer statistics for dashboard.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Calculate week start (Monday)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # Calculate month start
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    try:
        # Total customers
        total = await db.customers.count_documents({})
        
        # New today
        new_today = await db.customers.count_documents({
            "created_at": {"$gte": today_start}
        })
        
        # New this week
        new_week = await db.customers.count_documents({
            "created_at": {"$gte": week_start}
        })
        
        # New this month
        new_month = await db.customers.count_documents({
            "created_at": {"$gte": month_start}
        })
        
        # Auto-created vs manual
        auto_created = await db.customers.count_documents({
            "source": "auto_created"
        })
        
        return {
            "total_customers": total,
            "new_customers_today": new_today,
            "new_customers_week": new_week,
            "new_customers_month": new_month,
            "auto_created_customers": auto_created,
            "manual_customers": total - auto_created
        }
        
    except Exception as e:
        logger.error(f"[CUSTOMER-STATS] Error: {e}")
        return {
            "total_customers": 0,
            "new_customers_today": 0,
            "new_customers_week": 0,
            "new_customers_month": 0,
            "auto_created_customers": 0,
            "manual_customers": 0
        }
