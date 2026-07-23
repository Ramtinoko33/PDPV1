"""Cleanup UI seed data for Iteration 44 focused verification."""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path("/app")
load_dotenv(ROOT / "backend" / ".env")
MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ["DB_NAME"].strip('"')
PREFIX = "TSTOVUI"


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    imports = await db.finance_imports.find({"filename": {"$regex": f"^{PREFIX}-"}}, {"_id": 0, "original_file_path": 1}).to_list(100)
    for imp in imports:
        p = imp.get("original_file_path")
        if p and Path(p).exists():
            try:
                Path(p).unlink()
            except Exception:
                pass
    await db.finance_imports.delete_many({"filename": {"$regex": f"^{PREFIX}-"}})
    await db.finance_documents.delete_many({"genes_code": {"$regex": f"^{PREFIX}"}})
    await db.finance_clients.delete_many({"genes_code": {"$regex": f"^{PREFIX}"}})
    client.close()


if __name__ == "__main__":
    asyncio.run(main())