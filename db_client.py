"""Shared MongoDB client with SSL certificate handling"""
import os
import ssl
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    """Create a Motor client with proper SSL certificates"""
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    try:
        import certifi
        return AsyncIOMotorClient(
            url,
            tls=True,
            tlsCAFile=certifi.where(),
            tlsAllowInvalidCertificates=False,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=20000,
        )
    except ImportError:
        return AsyncIOMotorClient(url)
