"""Prepare the US4.6 (cancel an event) and US14.4 (holds expire) demo.

Run from backend/ with the virtual environment active:

    python scripts/demo_cancel_and_hold_expiry.py setup     # once, before recording
    python scripts/demo_cancel_and_hold_expiry.py hold 3    # just before the hold take
    python scripts/demo_cancel_and_hold_expiry.py hold-event  # a clean event for a retake
    python scripts/demo_cancel_and_hold_expiry.py open-house  # a new event to cancel
    python scripts/demo_cancel_and_hold_expiry.py quick-hold 15  # hold, expire, sweep
    python scripts/demo_cancel_and_hold_expiry.py sweep     # run the pg_cron job now
    python scripts/demo_cancel_and_hold_expiry.py status    # where the demo events stand

`setup` makes two events, each through the same routes the pages call, signed in
as the role that does that step, so the data has passed the same rules a person
would have met:

* "Demo: Open House" for US4.6, taken all the way to Confirmed: a Confirmed venue
  booking, a Reserved equipment line, registration open and two Attendees
  registered. Cancelling it releases every one of those.
* "Demo: Alumni Networking Night" for US14.4, Approved and assigned, so Venue
  Staff can hold a venue for it.

`hold N` places a hold on the second event that expires N minutes from now
(Singapore time, as the app reads it). Run it again for each retake.

It writes to the Supabase project in backend/.env, which the team shares. Every
event it makes is titled "Demo:" so it is easy to tell apart, and `setup` makes
new ones each time, because a cancelled event cannot be cancelled twice.
"""

import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.booking_store import local_now  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "Sprint1!demo"
ACCOUNTS = {
    "organiser": "organiser@spmg3t7.edu",
    "coordinator": "coordinator@spmg3t7.edu",
    "lead": "coordinatorlead@spmg3t7.edu",
    "venue staff": "venuestaff@spmg3t7.edu",
    "safety officer": "safetyofficer@spmg3t7.edu",
    "tech support": "technicalsupport@spmg3t7.edu",
    "attendee": "attendee@spmg3t7.edu",
    "attendee 2": "attendee2@spmg3t7.edu",
}

CANCEL_TITLE = "Demo: Open House"
HOLD_TITLE = "Demo: Alumni Networking Night"

#: Tried in order until one is free on the chosen day. Each suits the event's
#: needs (capacity, layout, facilities), so the request is not refused as unsuitable.
CANCEL_VENUES = ("Orchard Conference Hall", "Changi Business Park Auditorium", "Great Hall")
HOLD_VENUES = (
    "Marina Grand Ballroom",
    "Changi Business Park Auditorium",
    "Orchard Conference Hall",
)
MICROPHONE = "Wireless handheld microphone"


class Demo:
    """Signs each role in once and calls the API as them, stopping on any refusal."""

    def __init__(self) -> None:
        self.client = TestClient(app)
        self.sessions: dict[str, dict] = {}

    def session(self, role: str) -> dict:
        if role not in self.sessions:
            response = self.client.post(
                "/auth/login", json={"email": ACCOUNTS[role], "password": PASSWORD}
            )
            if response.status_code != 200:
                sys.exit(f"Could not sign in as {role} ({ACCOUNTS[role]}): {response.text}")
            self.sessions[role] = response.json()
        return self.sessions[role]

    def call(self, role: str, method: str, path: str, body: dict | None = None,
             ok: tuple[int, ...] = (200, 201, 204)):
        headers = {"Authorization": f"Bearer {self.session(role)['token']}"}
        response = self.client.request(method, path, json=body, headers=headers)
        if response.status_code not in ok:
            raise Refused(role, method, path, response.status_code, _detail(response))
        return response.json() if response.content else None

    def try_call(self, role: str, method: str, path: str, body: dict | None = None):
        """The answer, or None when the server refused with a 400 or 409."""
        try:
            return self.call(role, method, path, body)
        except Refused as refused:
            if refused.status in (400, 409):
                print(f"    {refused.message}")
                return None
            raise


class Refused(Exception):
    def __init__(self, role, method, path, status, message):
        super().__init__(f"{role}: {method} {path} answered {status}: {message}")
        self.status = status
        self.message = message


def _detail(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text[:200]
    return detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)


def _demo_day() -> datetime:
    """A day four to ten months out, different on each run, so runs rarely share a slot."""
    offset = 120 + (int(time.time()) // 60) % 180
    return (local_now() + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)


def _at(day: datetime, hour: int) -> str:
    return day.replace(hour=hour).strftime("%Y-%m-%dT%H:%M")


def _ids_by_name(rows: list[dict], key: str = "name") -> dict[str, str]:
    return {row[key]: row["id"] for row in rows}


def _create_assigned_event(demo: Demo, title: str, day: datetime, start: int, end: int,
                           attendance: int, layout: str, registration: str) -> dict:
    """Organiser creates and submits; the Lead assigns Priya; Priya approves."""
    event = demo.call("organiser", "POST", "/events", {
        "title": title,
        "purpose": "Recorded demo for the Week 12 sprint review.",
        "description": "Created by scripts/demo_cancel_and_hold_expiry.py.",
        "startsAt": _at(day, start),
        "endsAt": _at(day, end),
        "expectedAttendance": attendance,
        "venueRequirements": "Stage, Projector",
        "preferredLayout": layout,
        "accessibilityNeeds": "Wheelchair access",
        "equipmentNeeds": "Two wireless microphones",
        "registrationNeeds": registration,
    })
    event_id = event["id"]
    demo.call("organiser", "POST", f"/events/{event_id}/submit")
    coordinator_id = demo.session("coordinator")["id"]
    demo.call("lead", "POST", f"/events/{event_id}/assign", {"coordinatorId": coordinator_id})
    return demo.call("coordinator", "POST", f"/events/{event_id}/approve")


def setup(demo: Demo) -> None:
    day = _demo_day()
    open_house(demo, day)
    hold_event(demo, day + timedelta(days=7))


def open_house(demo: Demo, day: datetime | None = None) -> None:
    """A fresh US4.6 event, Confirmed with everything a cancellation releases."""
    venues = _ids_by_name(demo.call("venue staff", "GET", "/venues"))
    equipment = _ids_by_name(demo.call("tech support", "GET", "/equipment"))
    day = day or _demo_day()

    print(f"US4.6 - {CANCEL_TITLE}, {day:%a %d %b %Y}")
    event = _create_assigned_event(
        demo, CANCEL_TITLE, day, 18, 21, 150, "Theatre", "Open registration, 50 places"
    )
    event_id = event["id"]
    print(f"  event {event_id}: created, submitted, assigned to Priya, approved")

    booking = None
    for name in CANCEL_VENUES:
        if name not in venues:
            continue
        print(f"  requesting {name} ...")
        booking = demo.try_call("coordinator", "POST", f"/events/{event_id}/bookings", {
            "venueId": venues[name],
            "startsAt": _at(day, 18),
            "endsAt": _at(day, 21),
            "headcount": 150,
            "layout": "Theatre",
            "facilities": "Stage, Projector",
        })
        if booking:
            break
    if not booking:
        sys.exit("No demo venue was free on that day. Run setup again for another day.")
    demo.call("venue staff", "POST", f"/booking-requests/{booking['id']}/approve")
    print(f"  {booking['venueName']}: requested by Priya, confirmed by Venue Staff")

    line = demo.call("coordinator", "POST", f"/events/{event_id}/equipment-requests", {
        "equipmentId": int(equipment[MICROPHONE]),
        "quantity": 2,
        "technicalRequirements": "Two channels for the welcome speeches.",
    })
    demo.call("tech support", "POST", f"/equipment-requests/{line['id']}/reserve", {
        "version": line["version"],
        "equipmentId": int(equipment[MICROPHONE]),
    })
    print(f"  2 x {MICROPHONE}: requested, reserved by Tech Support")

    demo.call("coordinator", "POST", f"/events/{event_id}/safety-check")
    demo.call("safety officer", "POST", f"/events/{event_id}/safety-check/approve", {})
    print("  sent for the safety check, approved by the Safety Officer: Confirmed")

    demo.call("coordinator", "PUT", f"/events/{event_id}/registration",
              {"open": True, "capacity": 50})
    for role, name in (("attendee", "Casey Tan"), ("attendee 2", "Morgan Lee")):
        demo.call(role, "POST", f"/attendee/events/{event_id}/registrations",
                  {"name": name, "email": ACCOUNTS[role]})
    print("  registration opened; Casey and Morgan registered")
    print(f"\nReady: open http://localhost:5173/#/events/{event_id} as the Coordinator.")


def hold_event(demo: Demo, day: datetime | None = None) -> None:
    """A fresh US14.4 event, so a retake does not show the last take's expired holds."""
    day = day or _demo_day()
    print(f"\nUS14.4 - {HOLD_TITLE}, {day:%a %d %b %Y}")
    event = _create_assigned_event(
        demo, HOLD_TITLE, day, 19, 22, 120, "Banquet", "None / Not required"
    )
    print(f"  event {event['id']}: created, submitted, assigned to Priya, approved")
    print("\nReady. Before the hold take, run:")
    print("  python scripts/demo_cancel_and_hold_expiry.py hold 3")


def _latest(demo: Demo, title: str) -> dict:
    events = [e for e in demo.call("lead", "GET", "/events") if e["title"] == title]
    if not events:
        sys.exit(f'No "{title}" event yet. Run setup first.')
    return max(events, key=lambda event: int(event["id"]))


def _place_hold(demo: Demo, expires_at: Callable[[], str]) -> None:
    """Hold the first demo venue free at the US14.4 event's time.

    The expiry is worked out just before each request rather than up front:
    signing in and reading the catalogue take a few seconds, which would come
    out of a 15-second hold.
    """
    event = _latest(demo, HOLD_TITLE)
    if event["status"] not in ("Approved", "Planning"):
        sys.exit(
            f"{HOLD_TITLE} is {event['status']}; a hold needs Approved or Planning. Run setup."
        )
    venues = _ids_by_name(demo.call("venue staff", "GET", "/venues"))
    starts, ends = event["startsAt"][:16], event["endsAt"][:16]

    for name in HOLD_VENUES:
        print(f"Holding {name} for {HOLD_TITLE} ...")
        held = demo.try_call("venue staff", "POST", "/holds", {
            "venueId": venues[name],
            "eventId": event["id"],
            "startsAt": starts,
            "endsAt": ends,
            "expiresAt": expires_at(),
        })
        if held:
            print(f"  venue id {venues[name]}, event id {event['id']}")
            print(f"  slot {starts.replace('T', ' ')} to {ends[11:]}")
            return
    sys.exit("Every demo venue is held or booked at that time. Run setup for a new event.")


def hold(demo: Demo, minutes: int) -> None:
    now = local_now().replace(second=0, microsecond=0)
    expires = now + timedelta(minutes=minutes + 1)
    _place_hold(demo, lambda: expires.strftime("%Y-%m-%dT%H:%M"))
    print(
        f"  held, until {expires:%H:%M} Singapore time "
        f"({minutes}-{minutes + 1} minutes from now)"
    )
    next_sweep = 15 - now.minute % 15
    print(f"  the scheduled sweep next runs in {next_sweep} minute(s), at :00/:15/:30/:45")


def quick_hold(demo: Demo, seconds: int) -> None:
    """A hold that lapses `seconds` from now, then the sweep that records it.

    The form only takes whole minutes; the API takes seconds too, which is what
    makes a take this short possible.
    """
    sent: list[datetime] = []

    def expiry() -> str:
        sent.append(local_now().replace(microsecond=0) + timedelta(seconds=seconds))
        return sent[-1].strftime("%Y-%m-%dT%H:%M:%S")

    _place_hold(demo, expiry)
    expires = sent[-1]
    print(f"  held until {expires:%H:%M:%S}. Refresh the Coordinator's event page: Held.")
    while (left := (expires - local_now()).total_seconds()) > 0:
        print(f"  {round(left)} s left", flush=True)
        time.sleep(min(5.0, left))
    print("  expired: the slot is free now, before any sweep has run")
    # A moment's margin, in case the database clock is a little behind this one.
    time.sleep(2)
    sweep()
    print("  Refresh the Coordinator's page: Hold expired, and a notice that it has expired.")


def sweep() -> None:
    """Run the job pg_cron runs, now, through the same service-role client the API uses.

    The SQL Editor does the same with `SELECT public.sweep_tentative_holds();`,
    which reads better on camera.
    """
    from app import supabase_client

    result = supabase_client.admin().rpc("sweep_tentative_holds", {}).execute().data
    print(f"Swept: {len(result['expired'])} expired {result['expired']}, "
          f"{len(result['warned'])} warned {result['warned']}")


def status(demo: Demo) -> None:
    for title in (CANCEL_TITLE, HOLD_TITLE):
        try:
            event = _latest(demo, title)
        except SystemExit as missing:
            print(missing)
            continue
        event_id = event["id"]
        print(f"{title} (event {event_id}): {event['status']}, {event['startsAt'][:16]}")
        for booking in demo.call("coordinator", "GET", f"/events/{event_id}/bookings"):
            expiry = booking.get("holdExpiresAt")
            until = f" until {expiry[:16]}" if expiry else ""
            print(f"  venue      {booking['venueName']}: {booking['status']}{until}")
        lines = demo.call(
            "coordinator", "GET", f"/events/{event_id}/equipment-requests?includeRemoved=true"
        )
        for line in lines:
            name = line.get("equipmentName") or line["equipmentType"]
            print(f"  equipment  {line['quantity']} x {name}: {line['status']}")
        registered = demo.call("coordinator", "GET", f"/events/{event_id}/registrations")
        for person in registered.get("registrations", []):
            print(f"  attendee   {person['name']}: {person['status']}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sweep":
        sweep()
        return
    demo = Demo()
    try:
        if command == "setup":
            setup(demo)
        elif command == "hold-event":
            hold_event(demo)
        elif command == "open-house":
            open_house(demo)
        elif command == "hold":
            hold(demo, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
        elif command == "quick-hold":
            quick_hold(demo, int(sys.argv[2]) if len(sys.argv) > 2 else 15)
        elif command == "status":
            status(demo)
        else:
            sys.exit(__doc__)
    except Refused as refused:
        sys.exit(f"Stopped: {refused}")


if __name__ == "__main__":
    main()
