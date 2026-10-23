#!/usr/bin/env python3
"""Seed development accounts in Supabase Auth and public.users.

For Coordinator Lead and Safety Officer, run SUPABASE_ADD_NEW_ROLES.sql first.
Technical Support and Attendee are already in the base role enum. The two
Attendees (US20.1) are two so that registering for the last place can be tried
by two people.

Usage:
    python seed_new_users.py
    python seed_new_users.py --tech-only
    python seed_new_users.py --attendees-only
"""

import argparse
import os

from dotenv import load_dotenv
from supabase import Client, create_client

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
        "user_metadata": {"name": "Jordan", "role": "Event Coordinator Lead"},
    },
    {
        "email": "safetyofficer@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {"name": "Alex", "role": "Safety Officer"},
    },
    {
        "email": "technicalsupport@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {"name": "Bryan", "role": "Technical Support Staff"},
    },
]

#: US20.1: registering for Confirmed events.
ATTENDEES = [
    {
        "email": "attendee@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {"name": "Casey", "role": "Attendee"},
    },
    {
        "email": "attendee2@spmg3t7.edu",
        "password": PASSWORD,
        "email_confirm": True,
        "user_metadata": {"name": "Morgan", "role": "Attendee"},
    },
]


def seed_user(user_data: dict) -> None:
    email = user_data["email"]
    metadata = user_data["user_metadata"]
    role = "Technical Support" if email == "technicalsupport@spmg3t7.edu" else metadata["role"]
    existing_auth = next((u for u in supabase.auth.admin.list_users() if u.email == email), None)
    if existing_auth is None:
        created = supabase.auth.admin.create_user(user_data)
        if created.user is None:
            raise RuntimeError(f"Supabase did not return the new Auth account for {email}.")
        print(f"Created Auth account: {email}")
    else:
        print(f"Auth account already exists: {email}; password unchanged.")

    profiles = (
        supabase.table("users").select("id, name, role").eq("email", email).limit(1).execute().data
        or []
    )
    if profiles:
        if profiles[0]["role"] != role:
            raise RuntimeError(f"Profile {email} has role {profiles[0]['role']}, expected {role}.")
        print(f"Profile already exists: {email}; unchanged.")
    else:
        profile = {"email": email, "name": metadata["name"], "role": role}
        try:
            supabase.table("users").insert(profile).execute()
        except Exception as error:
            if getattr(error, "code", None) != "23505" or "users_pkey" not in str(error):
                raise
            # Existing manually assigned IDs can leave the serial sequence behind.
            highest = (
                supabase.table("users").select("id").order("id", desc=True).limit(1).execute().data
            )
            profile["id"] = (highest[0]["id"] if highest else 0) + 1
            supabase.table("users").insert(profile).execute()
        print(f"Created profile: {email} ({role}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tech-only", action="store_true", help="Set up Bryan only")
    parser.add_argument(
        "--attendees-only", action="store_true", help="Set up the two Attendees only (US20.1)"
    )
    arguments = parser.parse_args()
    if arguments.tech_only:
        selected = NEW_USERS[-1:]
    elif arguments.attendees_only:
        selected = ATTENDEES
    else:
        selected = NEW_USERS + ATTENDEES
    for account in selected:
        seed_user(account)
    print("Account setup complete. Newly created accounts use the configured seed password.")
