"""Shared MongoDB client"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

def get_client(mongo_url=None):
    url = mongo_url or os.environ.get('MONGO_URL', 'mongodb://127.0.0.1:27017')
    return AsyncIOMotorClient(url, serverSelectionTimeoutMS=30000)
