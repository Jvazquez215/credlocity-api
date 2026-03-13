"""Shared MongoDB client"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    try:
        import certifi
        return AsyncIOMotorClient(url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=30000)
    except ImportError:
        return AsyncIOMotorClient(url, serverSelectionTimeoutMS=30000)
