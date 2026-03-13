"""Shared MongoDB client with SSL handling"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    """Create a Motor client - handles Atlas M0 TLS issues"""
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    
    # Atlas M0 free tier has TLS issues with modern OpenSSL
    # Use tlsInsecure as workaround for shared clusters
    return AsyncIOMotorClient(
        url,
        tls=True,
        tlsInsecure=True,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=20000,
    )
