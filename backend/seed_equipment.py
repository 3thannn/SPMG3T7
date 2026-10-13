#!/usr/bin/env python3
"""Create US19 demo equipment through the signed-in create API. Safe to rerun."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

API = os.getenv("SEED_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = "technicalsupport@spmg3t7.edu"
PASSWORD = os.getenv("SEED_PASSWORD", "Sprint1!demo")

SAMPLES = [
    ("Epson laser projector", "Projector", "Main Campus AV Store", 8, 1, "Lens maintenance"),
    ("Portable short-throw projector", "Projector", "Library Store", 4, 0, ""),
    ("Wireless handheld microphone", "Microphone", "Main Campus AV Store", 20, 3, "Battery faults"),
    ("Lapel microphone", "Microphone", "East Campus Store", 12, 2, "Cable damage"),
    ("Powered PA speaker", "Speaker", "Main Campus AV Store", 10, 1, "Amplifier repair"),
    ("Portable monitor speaker", "Speaker", "East Campus Store", 6, 0, ""),
    ("Presentation laptop", "Laptop", "Library Store", 10, 2, "Operating system maintenance"),
    ("Touchscreen laptop", "Laptop", "Main Campus AV Store", 5, 0, ""),
    ("Tripod projection screen", "Screen", "East Campus Store", 7, 1, "Tripod replacement"),
    ("Large LED display", "Screen", "Main Campus AV Store", 3, 0, ""),
]


def call(path: str, method: str = "GET", body: dict | None = None, token: str = ""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error).get("detail", {})
            message = (
                detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            )
        except (ValueError, OSError):
            message = error.reason
        raise RuntimeError(f"{method} {path} failed ({error.code}): {message}") from error


def seed() -> tuple[int, int]:
    token = call("/auth/login", "POST", {"email": EMAIL, "password": PASSWORD})["token"]
    existing = {item["name"].casefold() for item in call("/equipment", token=token)}
    created = skipped = 0
    for name, kind, location, total, out, reason in SAMPLES:
        if name.casefold() in existing:
            skipped += 1
            continue
        call(
            "/equipment",
            "POST",
            {
                "name": name,
                "type": kind,
                "description": f"Demo {kind.lower()} equipment",
                "location": location,
                "totalQuantity": total,
                "outOfServiceQuantity": out,
                "outOfServiceReason": reason,
            },
            token,
        )
        created += 1
        existing.add(name.casefold())
    return created, skipped


if __name__ == "__main__":
    added, unchanged = seed()
    print(f"Equipment samples: {added} created, {unchanged} already present.")
