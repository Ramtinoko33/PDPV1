"""Seed 2 finance_imports for anomaly UI testing (TSTANOMUI prefix)."""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    await db.finance_imports.delete_many({'filename': {'$regex': '^TSTANOMUI-'}})
    for suffix, days, totals in [
        ('ui-prev', 2, {'clients': 100, 'documents': 300, 'total_overdue': 10000, 'total_balance': 10000}),
        ('ui-cur', 0, {'clients': 105, 'documents': 305, 'total_overdue': 20000, 'total_balance': 20000}),
    ]:
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        await db.finance_imports.insert_one({
            'id': str(uuid.uuid4()),
            'type': 'overdue_balances',
            'source_method': 'manual_upload',
            'filename': f'TSTANOMUI-{suffix}.xlsx',
            'file_hash': uuid.uuid4().hex,
            'as_of_date': dt.date().isoformat(),
            'uploaded_by': 'test',
            'uploaded_at': dt.isoformat(),
            'status': 'imported',
            'original_file_path': None,
            'totals': totals,
            'warnings': [], 'errors': [],
        })
    print('seeded 2 imports')

def cleanup():
    async def _go():
        c = AsyncIOMotorClient(os.environ['MONGO_URL'])
        db = c[os.environ['DB_NAME']]
        r = await db.finance_imports.delete_many({'filename': {'$regex': '^TSTANOMUI-'}})
        await db.finance_anomaly_validations.delete_many({'comment': {'$regex': 'UITESTE47'}})
        print(f'deleted {r.deleted_count} imports and validations')
    asyncio.run(_go())

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup':
        cleanup()
    else:
        asyncio.run(main())
