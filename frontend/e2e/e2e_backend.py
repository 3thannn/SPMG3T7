"""Run with uvicorn --app-dir frontend/e2e e2e_backend:app from the repo root.

No production routes or files are modified. The extra route exists only when
this wrapper is explicitly launched for testing; it exposes no URL or keys.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from fastapi import Query
from app.main import app
from app import supabase_client
from database_identity import proof


@app.get('/__e2e__/database-identity', include_in_schema=False)
def database_identity(challenge: str = Query(pattern=r'^[a-f0-9]{64}$')):
    client = supabase_client.admin()
    return {'proof': proof(str(client.supabase_url), client.supabase_key, challenge)}
