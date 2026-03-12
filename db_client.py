"""Shared MongoDB client with SSL certificate handling"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    """Create a Motor client"""
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    try:
        import certifi
        return AsyncIOMotorClient(url, tlsCAFile=certifi.where())
    except ImportError:
        return AsyncIOMotorClient(url)
