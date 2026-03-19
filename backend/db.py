"""
Database connection module.
Centralizes MongoDB connection and exposes the db instance.
"""
from motor.motor_asyncio import AsyncIOMotorClient
import os

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
# Use MONGO_DATABASE_NAME (Emergent production) or DB_NAME (local dev) or fallback
db = client[os.environ.get('MONGO_DATABASE_NAME', os.environ.get('DB_NAME', 'test_database'))]

__all__ = ["client", "db"]
