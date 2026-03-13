#!/bin/bash
# Start MongoDB in background
mongod --dbpath /data/db --bind_ip 127.0.0.1 --port 27017 --fork --logpath /var/log/mongod.log --nojournal --smallfiles 2>/dev/null || \
mongod --dbpath /data/db --bind_ip 127.0.0.1 --port 27017 --fork --logpath /var/log/mongod.log 2>/dev/null

# Wait for MongoDB to start
sleep 2

# Set local MONGO_URL 
export MONGO_URL="mongodb://127.0.0.1:27017"
export DB_NAME="credlocity"

# Start the app
exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8002}
