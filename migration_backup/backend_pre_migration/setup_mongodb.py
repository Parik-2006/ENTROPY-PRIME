#!/usr/bin/env python3
"""
MongoDB Setup Script for Entropy Prime
Automatically creates collections, indexes, and test data.
"""

import asyncio
import os
import sys
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def setup_mongodb():
    """Initialize MongoDB with collections, indexes, and users."""
    
    # Connection string (adjust if using different credentials)
    mongo_url = "mongodb://admin:changeme@localhost:27017/"
    db_name = "entropy_prime"
    
    print("=" * 60)
    print("Entropy Prime — MongoDB Setup")
    print("=" * 60)
    
    try:
        # Connect to MongoDB
        print("\n[1/5] Connecting to MongoDB...")
        client = AsyncIOMotorClient(mongo_url)
        
        # Ping to verify connection
        await client.admin.command("ping")
        print("    ✓ Connected successfully")
        
        # Get or create database
        db = client[db_name]
        print(f"\n[2/5] Using database: {db_name}")
        
        # Create collections
        print("\n[3/5] Creating collections...")
        collections_to_create = [
            "users",
            "sessions",
            "biometric_profiles",
            "drift_events",
            "feature_selections",
            "honeypot",
        ]
        
        existing_collections = await db.list_collection_names()
        
        for collection_name in collections_to_create:
            if collection_name not in existing_collections:
                await db.create_collection(collection_name)
                print(f"    ✓ Created collection: {collection_name}")
            else:
                print(f"    ✓ Collection already exists: {collection_name}")
        
        # Create indexes
        print("\n[4/5] Creating indexes...")
        
        await db.users.create_index("email", unique=True)
        print("    ✓ Index on users.email (unique)")
        
        await db.sessions.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0
        )
        print("    ✓ Index on sessions.expires_at (TTL)")
        
        await db.drift_events.create_index(
            [("timestamp", 1)],
            expireAfterSeconds=2592000  # 30 days
        )
        print("    ✓ Index on drift_events.timestamp (TTL 30 days)")
        
        await db.biometric_profiles.create_index("user_id")
        print("    ✓ Index on biometric_profiles.user_id")
        
        await db.honeypot.create_index([("timestamp", -1)])
        print("    ✓ Index on honeypot.timestamp")
        
        # Create application user (ep_user)
        print("\n[5/5] Creating application user...")
        try:
            admin_db = client["admin"]
            
            # Try to create the application user
            await admin_db.command(
                "createUser",
                "ep_user",
                pwd="ep_password",
                roles=[{"role": "readWrite", "db": db_name}],
            )
            print("    ✓ Created user: ep_user (password: ep_password)")
        except Exception as e:
            if "already exists" in str(e):
                print("    ✓ User ep_user already exists")
            else:
                print(f"    ⚠ Warning: Could not create user: {e}")
        
        # Verify setup
        print("\n[✓] MongoDB Setup Complete!")
        print("\nVerification:")
        
        collections = await db.list_collection_names()
        print(f"  - Collections: {len(collections)} found")
        for coll in collections:
            count = await db[coll].count_documents({})
            print(f"    • {coll}: {count} documents")
        
        print("\n" + "=" * 60)
        print("Connection String:")
        print(f"  mongodb://ep_user:ep_password@localhost:27017/{db_name}")
        print("=" * 60)
        
        client.close()
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure MongoDB is running: Get-Service MongoDB")
        print("  2. Check connection string is correct")
        print("  3. Verify credentials match MongoDB admin user")
        return False


if __name__ == "__main__":
    success = asyncio.run(setup_mongodb())
    sys.exit(0 if success else 1)
