#!/usr/bin/env python3
import asyncio, os, json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv('/app/backend/.env')
IDS = ['0971295c-2738-4939-83a5-b0179a53012c','d55ed1ba-3589-4d2f-b592-afd9423798f4']
async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    docs=[]
    for id in IDS:
        d = await db.finance_imports.find_one({'id': id}, {'_id': 0, 'id': 1, 'type': 1, 'totals': 1})
        docs.append(d)
    print(json.dumps(docs, ensure_ascii=False, indent=2))
    client.close()
asyncio.run(main())
