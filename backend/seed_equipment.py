#!/usr/bin/env python3
"""Create US19 sample equipment and refresh old placeholder descriptions."""

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
    ("Epson laser projector", "Projector", "Main Campus AV Store", 8, 1, "Lens maintenance",
     "Laser projector for presentations in larger rooms."),
    ("Portable short-throw projector", "Projector", "Library Store", 4, 0, "",
     "Portable projector for rooms with limited projection distance."),
    ("Wireless handheld microphone", "Microphone", "Main Campus AV Store", 20, 3, "Battery faults",
     "Wireless microphone for speeches and audience questions."),
    ("Lapel microphone", "Microphone", "East Campus Store", 12, 2, "Cable damage",
     "Clip-on microphone for hands-free presentations."),
    ("Powered PA speaker", "Speaker", "Main Campus AV Store", 10, 1, "Amplifier repair",
     "Powered speaker for event audio and announcements."),
    ("Portable monitor speaker", "Speaker", "East Campus Store", 6, 0, "",
     "Portable speaker for stage monitoring or small events."),
    ("Presentation laptop", "Laptop", "Library Store", 10, 2, "Operating system maintenance",
     "Laptop for slides and video playback at events."),
    ("Touchscreen laptop", "Laptop", "Main Campus AV Store", 5, 0, "",
     "Touchscreen laptop for interactive presentations."),
    ("Tripod projection screen", "Screen", "East Campus Store", 7, 1, "Tripod replacement",
     "Portable projection screen with a tripod stand."),
    ("Large LED display", "Screen", "Main Campus AV Store", 3, 0, "",
     "Large display for presentations, video and event signage."),
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


def seed() -> tuple[int, int, int]:
    token = call("/auth/login", "POST", {"email": EMAIL, "password": PASSWORD})["token"]
    existing = {item["name"].casefold(): item for item in call("/equipment", token=token)}
    created = updated = skipped = 0
    for name, kind, location, total, out, reason, description in SAMPLES:
        item = existing.get(name.casefold())
        if item:
            if item["description"] == f"Demo {kind.lower()} equipment":
                body = {key: item[key] for key in (
                    "name", "type", "location", "totalQuantity",
                    "outOfServiceQuantity", "outOfServiceReason",
                )}
                body["description"] = description
                call(f"/equipment/{item['id']}", "PUT", body, token)
                updated += 1
            else:
                skipped += 1
            continue
        call(
            "/equipment",
            "POST",
            {
                "name": name,
                "type": kind,
                "description": description,
                "location": location,
                "totalQuantity": total,
                "outOfServiceQuantity": out,
                "outOfServiceReason": reason,
            },
            token,
        )
        created += 1
    return created, updated, skipped


if __name__ == "__main__":
    added, refreshed, unchanged = seed()
    print(
        f"Equipment samples: {added} created, "
        f"{refreshed} descriptions updated, {unchanged} unchanged."
    )
