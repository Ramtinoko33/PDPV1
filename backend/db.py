"""
Database connection module.
Centralizes MongoDB connection and exposes the db instance.
"""
from motor.motor_asyncio import AsyncIOMotorClient
import os

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

__all__ = ["client", "db"]
