#!/usr/bin/env python3
import asyncio, os, json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv('/app/backend/.env')
async def main():
    c=AsyncIOMotorClient(os.environ['MONGO_URL']); db=c[os.environ['DB_NAME']]
    clients=await db.finance_clients.find({'genes_code':'2111102130'}, {'_id':0, 'id':1,'name':1,'genes_code':1}).to_list(10)
    evo=await db.finance_credit_evolution.find_one({'genes_code':'2111102130'}, {'_id':0, 'genes_code':1,'periods':1})
    print(json.dumps({'clients':clients,'evo':evo}, ensure_ascii=False, indent=2))
    c.close()
asyncio.run(main())
