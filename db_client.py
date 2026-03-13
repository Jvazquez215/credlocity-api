"""Shared MongoDB client"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    """Create a Motor client - OpenSSL 1.1.1 (Bullseye) works natively with Atlas"""
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    return AsyncIOMotorClient(url, serverSelectionTimeoutMS=30000)
