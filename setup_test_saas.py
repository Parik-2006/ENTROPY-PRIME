import asyncio
import os
import hmac
import hashlib
from database import Database, create_tenant, create_site

async def setup():
    db_handler = Database()
    await db_handler.connect_to_mongo()
    
    # 1. Create a test tenant
    tenant_id = await create_tenant(db_handler.db, "Test Corp", "admin@test.com", "pro")
    print(f"Created Tenant: {tenant_id}")
    
    # 2. Create a test site
    raw_api_key = "test-sdk-key-123"
    api_key_secret = os.environ.get("EP_API_KEY_SECRET", "dev-only-api-key-secret-change-me")
    
    # In production, we store the HMAC digest
    key_digest = hmac.new(
        api_key_secret.encode(),
        raw_api_key.encode(),
        hashlib.sha256
    ).hexdigest()
    
    site_id = await create_site(
        db_handler.db, 
        tenant_id, 
        "Test Site", 
        "localhost", 
        key_digest
    )
    print(f"Created Site: {site_id}")
    print(f"API Key: {raw_api_key}")
    print(f"Key Digest: {key_digest}")
    
    await db_handler.close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(setup())
