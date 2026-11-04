#!/usr/bin/env python3
"""Complete setup for new roles: enum values + user records."""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: Missing Supabase credentials in .env")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

print("🔧 Setting up new roles in database...")

# Step 1: Add enum values (requires raw SQL)
print("\n1️⃣ Adding new role values to user_role enum...")
try:
    supabase.postgrest.rpc(
        "exec_sql",
        {
            "query": """
                ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead';
                ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Safety Officer';
            """
        }
    ).execute()
    print("   ✅ Enum values added")
except Exception as e:
    # If the function doesn't exist, we need to add the values manually via dashboard
    print(f"   ⚠️  Need to add enum values manually: {e}")
    print("   Run this SQL in Supabase Dashboard → SQL Editor:")
    print("   ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead';")
    print("   ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Safety Officer';")

# Step 2: Insert user records
print("\n2️⃣ Creating user records in public.users...")

users_to_create = [
    {
        "id": 3,
        "email": "coordinatorlead@connectsphere.com",
        "name": "Jordan",
        "role": "Event Coordinator Lead"
    },
    {
        "id": 5,
        "email": "safetyofficer@connectsphere.com",
        "name": "Alex",
        "role": "Safety Officer"
    }
]

for user in users_to_create:
    try:
        # Check if exists
        existing = supabase.table("users").select("*").eq("id", user["id"]).execute()

        if existing.data:
            # Update
            supabase.table("users").update({
                "email": user["email"],
                "name": user["name"],
                "role": user["role"]
            }).eq("id", user["id"]).execute()
            print(f"   ✅ Updated {user['email']} (ID: {user['id']})")
        else:
            # Insert
            supabase.table("users").insert(user).execute()
            print(f"   ✅ Created {user['email']} (ID: {user['id']})")
    except Exception as e:
        print(f"   ❌ Error with {user['email']}: {e}")

# Step 3: Verify
print("\n3️⃣ Verifying users...")
all_users = supabase.table("users").select("id, email, name, role").order("id").execute()

print("\n📋 All users in database:")
for user in all_users.data:
    print(f"   {user['id']}: {user['name']} ({user['role']}) - {user['email']}")

print("\n✅ Setup complete!")
print("\n🎉 You can now sign in with:")
print("   Coordinator Lead: coordinatorlead@connectsphere.com / password")
print("   Safety Officer:   safetyofficer@connectsphere.com / password")
