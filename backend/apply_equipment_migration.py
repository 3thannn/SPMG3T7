#!/usr/bin/env python3
"""Apply the rerunnable US19 SQL migration through SUPABASE_DB_URL."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    database_url = os.getenv("SUPABASE_DB_URL")
    if not database_url:
        raise SystemExit("Set SUPABASE_DB_URL in backend/.env before applying the migration.")
    sql = Path(__file__).with_name("SUPABASE_ADD_EQUIPMENT_REQUESTS.sql").read_text()
    with psycopg.connect(database_url, connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='equipment_requests'"
            )
            if cursor.fetchone()[0] < 10:
                raise RuntimeError("Equipment requests table was not created.")
    print("US19 equipment migration applied.")


if __name__ == "__main__":
    main()
