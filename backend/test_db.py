"""Quick test of database connection."""

import asyncio
from database import Database


async def test_db():
    db = Database()
    await db.connect_to_mongo()
    
    # Test user creation
    await db.db.users.insert_one({
        "email": "test@entropy.local",
        "name": "Test User"
    })
    user = await db.db.users.find_one({"email": "test@entropy.local"})
    
    print("✓ Database connected and working")
    print(f"✓ Created user: {user['email']}")
    
    collections = await db.db.list_collection_names()
    print(f"✓ Collections: {len(collections)} created")
    
    await db.close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(test_db())
