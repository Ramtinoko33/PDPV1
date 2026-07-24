#!/usr/bin/env python3
import asyncio, os, json, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv('/app/backend/.env')
async def main():
    c=AsyncIOMotorClient(os.environ['MONGO_URL']); db=c[os.environ['DB_NAME']]
    cid='bugtest-card-2111102130'
    now=datetime.now(timezone.utc).isoformat()
    await db.finance_clients.delete_one({'id':cid})
    await db.finance_clients.insert_one({'id':cid,'genes_code':'2111102130','name':'TRANSFRADELOS, LDA. CARD TEST','total_balance':0.0,'overdue_balance_accounting':0.0,'overdue_balance_collectable':0.0,'residual_balance':0.0,'oldest_overdue_days':0,'collection_index':0.0,'financial_status':'OK','traffic_light':'GREEN','is_residual_only':False,'is_blocked':False,'created_at':now,'updated_at':now})
    print(cid)
    c.close()
asyncio.run(main())
