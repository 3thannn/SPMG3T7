#!/usr/bin/env python3
"""Seed new users (Coordinator Lead and Safety Officer) into Supabase Auth.

Run this AFTER running SUPABASE_ADD_NEW_ROLES.sql

Usage:
    python seed_new_users.py
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PASSWORD = os.getenv("SEED_PASSWORD", "Sprint1!demo")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    exit(1)

# Create Supabase admin client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# New users to create
NEW_USERS = [
    {
        "email": "coordinatorlead@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {
            "name": "Jordan",
            "role": "Event Coordinator Lead"
        }
    },
    {
        "email": "safetyofficer@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {
            "name": "Alex",
            "role": "Safety Officer"
        }
    }
]

print("🔧 Creating auth accounts for new roles...")
print(f"Password for all accounts: {PASSWORD}")
print()

for user_data in NEW_USERS:
    try:
        # Check if user already exists
        response = supabase.auth.admin.list_users()
        existing = next(
            (u for u in response if u.email == user_data["email"]),
            None
        )

        if existing:
            print(f"⚠️  {user_data['email']} already exists (ID: {existing.id})")
            # Update password if needed
            supabase.auth.admin.update_user_by_id(
                existing.id,
                {"password": user_data["password"]}
            )
            print(f"   ✅ Password updated")
        else:
            # Create new auth user
            result = supabase.auth.admin.create_user(user_data)
            print(f"✅ Created {user_data['email']} (ID: {result.user.id})")

    except Exception as e:
        print(f"❌ Error creating {user_data['email']}: {e}")

print()
print("✅ Done! You can now sign in with:")
print(f"   Coordinator Lead: coordinatorlead@spmg3t7.edu / {PASSWORD}")
print(f"   Safety Officer:   safetyofficer@spmg3t7.edu / {PASSWORD}")
