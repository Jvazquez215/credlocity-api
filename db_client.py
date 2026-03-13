"""Shared MongoDB client with SSL certificate handling"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    """Create a Motor client with proper SSL certificates for Atlas on Google Cloud"""
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    try:
        import certifi
        return AsyncIOMotorClient(url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=30000)
    except ImportError:
        return AsyncIOMotorClient(url, serverSelectionTimeoutMS=30000)
