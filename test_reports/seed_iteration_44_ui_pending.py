"""Seed one pending overdue_balances import for focused UI approval-alert verification."""
import asyncio
import io
import os
import uuid
from datetime import datetime, timezone, date
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from openpyxl import Workbook

ROOT = Path("/app")
load_dotenv(ROOT / "backend" / ".env")
MONGO_URL = os.environ["MONGO_URL"].strip('"')
DB_NAME = os.environ["DB_NAME"].strip('"')
PREFIX = "TSTOVUI"
TODAY = date.today().isoformat()


def build_zero_doc_xlsx(marker: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append([
        "Cliente", "Cód. Cliente", "Localidade", "Região", "Email",
        "Telefone1", "Telefone2", "Importe Total Vencido", "Saldo Cliente",
    ])
    for i in range(5):
        ws.append([f"Cliente UI {i} {marker}", f"{PREFIX}Z{i:02d}", "Lisboa", "Sul", "", "", "", 0.0, 0.0])
    ws["Z1"] = marker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.finance_imports.delete_many({"filename": {"$regex": f"^{PREFIX}-"}})
    await db.finance_documents.delete_many({"genes_code": {"$regex": f"^{PREFIX}"}})
    await db.finance_clients.delete_many({"genes_code": {"$regex": f"^{PREFIX}"}})

    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for i in range(3):
        docs.append({
            "id": f"{PREFIX}A_SEED{i}",
            "client_id": None,
            "genes_code": f"{PREFIX}A",
            "document_type": "FT",
            "document_number": f"SEED{i}",
            "invoice_date": "2025-11-01",
            "due_date": "2025-12-01",
            "amount_original": 100.0,
            "amount_open": 100.0,
            "amount_overdue": 100.0,
            "days_overdue": 30,
            "classification": "collectable",
            "effective_classification": "collectable",
            "manually_marked_collectable": False,
            "manual_action": None,
            "last_import_id": f"{PREFIX}-seed",
            "created_at": now,
            "updated_at": now,
        })
    await db.finance_documents.insert_many(docs)

    marker = uuid.uuid4().hex[:8]
    import_id = str(uuid.uuid4())
    upload_dir = ROOT / "backend" / "uploads" / "finance_imports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{PREFIX}-{import_id}.xlsx"
    file_path.write_bytes(build_zero_doc_xlsx(marker))
    await db.finance_imports.insert_one({
        "id": import_id,
        "type": "overdue_balances",
        "source_method": "manual_upload",
        "filename": f"{PREFIX}-pending-{marker}.xlsx",
        "file_hash": uuid.uuid4().hex,
        "as_of_date": TODAY,
        "uploaded_by": "test-verification",
        "uploaded_at": now,
        "status": "pending_approval",
        "original_file_path": str(file_path),
        "totals": {"clients": 5, "documents": 0, "total_balance": 0, "total_overdue": 0},
        "warnings": ["seed pending import for UI guard verification"],
        "errors": [],
        "approved_by": None,
        "approved_at": None,
    })
    print(import_id)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())