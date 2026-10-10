#!/usr/bin/env python3
"""Add new enum values to user_role using direct SQL execution."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: Missing Supabase credentials")
    exit(1)

# Execute raw SQL via Supabase REST API
sql_queries = [
    "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Event Coordinator Lead'",
    "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'Safety Officer'"
]

print("🔧 Adding new role values to user_role enum...")

for query in sql_queries:
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json"
            },
            json={"query": query}
        )

        if response.status_code == 200:
            print(f"   ✅ {query[:50]}...")
        else:
            print(f"   ⚠️  Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

print("\n✅ Enum update complete!")
print("\nNow running full setup script...")

# Now run the full setup
os.system("python setup_new_roles_complete.py")
