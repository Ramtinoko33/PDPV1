#!/usr/bin/env python3
import asyncio, os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv('/app/backend/.env')
async def main():
    c=AsyncIOMotorClient(os.environ['MONGO_URL']); db=c[os.environ['DB_NAME']]
    res=await db.finance_clients.delete_one({'id':'bugtest-card-2111102130'})
    print(f'deleted_clients={res.deleted_count}')
    c.close()
asyncio.run(main())
