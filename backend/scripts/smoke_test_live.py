"""Run the whole event workflow against the live Supabase project, and report each step.

    python scripts/smoke_test_live.py

The unit tests run against in-memory stores, so they cannot see the database
itself: a migration that was never applied, a function that differs from the
repo, a constraint one script redefined over another. This walks the same
routes the pages call, signed in as each role, through all 20 Release 1 core
features plus holds, replacement venues, safety checks and cancellation, and
prints PASS or FAIL for each step with the server's own reason.

It writes to the project in backend/.env. Everything it makes is named
"Smoke ..." and lives at its own two venues, years out, so it does not touch
anyone's demo data; its events end Cancelled.
"""

import sys
import time
import traceback
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import supabase_client  # noqa: E402
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
NEEDS = {
    "venueRequirements": "Stage, Projector",
    "preferredLayout": "Theatre",
    "accessibilityNeeds": "Wheelchair access",
    "equipmentNeeds": "Two wireless microphones",
    "registrationNeeds": "Open registration",
}


class Failed(Exception):
    pass


class Smoke:
    def __init__(self) -> None:
        self.client = TestClient(app)
        self.sessions: dict[str, dict] = {}
        self.results: list[tuple[str, str, str]] = []
        self.stamp = local_now().strftime("%m%d-%H%M")
        # Years out, and a different day each run, so runs do not share slots.
        offset = 700 + (int(time.time()) // 60) % 300
        self.day = (local_now() + timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    # -- calling the API ------------------------------------------------------

    def session(self, role: str) -> dict:
        if role not in self.sessions:
            response = self.client.post(
                "/auth/login", json={"email": ACCOUNTS[role], "password": PASSWORD}
            )
            if response.status_code != 200:
                raise Failed(f"{role} could not sign in: {response.text[:200]}")
            self.sessions[role] = response.json()
        return self.sessions[role]

    def call(self, role, method, path, body=None, expect=(200, 201, 204)):
        headers = {"Authorization": f"Bearer {self.session(role)['token']}"}
        response = self.client.request(method, path, json=body, headers=headers)
        if response.status_code not in expect:
            try:
                detail = response.json().get("detail")
                detail = detail.get("message", detail) if isinstance(detail, dict) else detail
            except ValueError:
                detail = response.text[:300]
            raise Failed(f"{role} {method} {path} -> {response.status_code}: {detail}")
        return response.json() if response.content else None

    def at(self, day_offset: int, hour: int) -> str:
        return (self.day + timedelta(days=day_offset, hours=hour)).strftime("%Y-%m-%dT%H:%M")

    def date(self, day_offset: int) -> str:
        return (self.day + timedelta(days=day_offset)).strftime("%Y-%m-%d")

    # -- recording ------------------------------------------------------------

    def step(self, feature: str, name: str, action) -> object:
        try:
            value = action()
        except Failed as failed:
            self.results.append(("FAIL", feature, f"{name}: {failed}"))
            print(f"FAIL  {feature:28} {name}\n      {failed}")
            return None
        except Exception as error:  # noqa: BLE001 - a crash is a result too
            reason = f"{type(error).__name__}: {error}"
            self.results.append(("FAIL", feature, f"{name}: {reason}"))
            print(f"FAIL  {feature:28} {name}\n      {reason}")
            traceback.print_exc(limit=2)
            return None
        self.results.append(("PASS", feature, name))
        print(f"PASS  {feature:28} {name}")
        return value

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            raise Failed(message)

    # -- building blocks ------------------------------------------------------

    def new_event(self, title: str, day: int, attendance: int = 150) -> dict:
        return self.call("organiser", "POST", "/events", {
            "title": f"Smoke {self.stamp}: {title}",
            "purpose": "Live smoke test.",
            "description": "Created by scripts/smoke_test_live.py.",
            "startsAt": self.at(day, 18),
            "endsAt": self.at(day, 21),
            "expectedAttendance": attendance,
            **NEEDS,
        })

    def submitted_and_assigned(self, title: str, day: int) -> dict:
        event = self.new_event(title, day)
        self.call("organiser", "POST", f"/events/{event['id']}/submit")
        return self.call("lead", "POST", f"/events/{event['id']}/assign",
                         {"coordinatorId": self.session("coordinator")["id"]})

    def approved(self, title: str, day: int) -> dict:
        event = self.submitted_and_assigned(title, day)
        return self.call("coordinator", "POST", f"/events/{event['id']}/approve")

    def booking_body(self, venue_id, day: int, headcount: int = 150) -> dict:
        return {
            "venueId": venue_id,
            "startsAt": self.at(day, 18),
            "endsAt": self.at(day, 21),
            "headcount": headcount,
            "layout": "Theatre",
            "facilities": "Stage, Projector",
        }


def run() -> int:
    s = Smoke()
    print(f"Smoke run {s.stamp}, events from {s.day:%d %b %Y}\n")
    ctx: dict = {}

    # F1 User authorisation and authentication ---------------------------------
    def sign_in_all():
        for role in ACCOUNTS:
            s.session(role)
    s.step("F1 Auth", "every role signs in", sign_in_all)
    s.step("F1 Auth", "an Attendee cannot list internal events",
           lambda: s.call("attendee", "GET", "/events", expect=(403,)))
    s.step("F1 Auth", "an Organiser cannot add a venue",
           lambda: s.call("organiser", "POST", "/venues", {"name": "x"}, expect=(403,)))

    # F8 Venue catalogue -------------------------------------------------------
    def make_venues():
        base = {"location": "Smoke Campus", "facilities": "Stage, Projector",
                "accessibilityFeatures": "Wheelchair access",
                "operatingHours": "08:00-23:00", "supportedLayouts": "Theatre"}
        ctx["hall"] = s.call("venue staff", "POST", "/venues",
                             {**base, "name": f"Smoke Hall {s.stamp}", "capacity": 200})
        ctx["annex"] = s.call("venue staff", "POST", "/venues",
                              {**base, "name": f"Smoke Annex {s.stamp}", "capacity": 210})
        updated = s.call("venue staff", "PUT", f"/venues/{ctx['hall']['id']}",
                         {**base, "name": f"Smoke Hall {s.stamp}", "capacity": 220})
        s.check(updated["venue"]["capacity"] == 220 if "venue" in updated
                else updated.get("capacity") == 220, f"update not saved: {updated}")
    s.step("F8 Venue catalogue", "Venue Staff add and edit venues", make_venues)

    # F10 Venue search and filtering ---------------------------------------------
    def search():
        found = s.call("coordinator", "GET",
                       "/venues?minCapacity=215&location=Smoke%20Campus")
        names = {v["name"] for v in found}
        s.check(f"Smoke Hall {s.stamp}" in names, "the 220-seat hall is missing")
        s.check(f"Smoke Annex {s.stamp}" not in names, "the 210-seat annex should be filtered")
    if "hall" in ctx:
        s.step("F10 Venue search", "filter by capacity and location", search)

    # F2 Event request creation, F3 drafts, F6 status ----------------------------
    def draft_then_submit():
        draft = s.call("organiser", "POST", "/events",
                       {"title": f"Smoke {s.stamp}: Main event"})
        s.check(draft["status"] == "Draft", f"new event is {draft['status']}")
        full = {
            "title": f"Smoke {s.stamp}: Main event",
            "purpose": "Live smoke test.",
            "description": "Created by scripts/smoke_test_live.py.",
            "startsAt": s.at(0, 18), "endsAt": s.at(0, 21), "expectedAttendance": 150,
            **NEEDS,
        }
        saved = s.call("organiser", "PUT", f"/events/{draft['id']}", full)
        s.check(saved["status"] == "Draft", "saving a draft moved its status")
        submitted = s.call("organiser", "POST", f"/events/{draft['id']}/submit")
        s.check(submitted["status"] == "Submitted", f"submitted event is {submitted['status']}")
        ctx["main"] = submitted
    s.step("F2/F3/F6 Request + draft", "draft, complete, submit", draft_then_submit)

    # F5 Coordinator assignment ----------------------------------------------------
    def assign():
        queue = s.call("lead", "GET", "/events/unassigned")
        s.check(any(e["id"] == ctx["main"]["id"] for e in queue), "not in the unassigned queue")
        assigned = s.call("lead", "POST", f"/events/{ctx['main']['id']}/assign",
                          {"coordinatorId": s.session("coordinator")["id"]})
        s.check(assigned["status"] == "Under Review", f"assigned event is {assigned['status']}")
        others = [u for u in s.call("lead", "GET", "/auth/users")
                  if u["role"] == "Event Coordinator" and u["id"] != s.session("coordinator")["id"]]
        if others:
            s.call("lead", "POST", f"/events/{ctx['main']['id']}/reassign",
                   {"coordinatorId": others[0]["id"]})
            s.call("lead", "POST", f"/events/{ctx['main']['id']}/reassign",
                   {"coordinatorId": s.session("coordinator")["id"]})
    if "main" in ctx:
        s.step("F5 Coordinator assignment", "queue, assign, reassign and back", assign)

    # F4 Event review and approval ---------------------------------------------------
    def review():
        asked = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/clarification",
                       {"message": "Smoke test: please confirm the layout."})
        s.check(asked["status"] == "Under Review", f"clarified event is {asked['status']}")
        approved = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/approve")
        s.check(approved["status"] == "Approved", f"approved event is {approved['status']}")
        other = s.submitted_and_assigned("Rejected event", 1)
        rejected = s.call("coordinator", "POST", f"/events/{other['id']}/reject",
                          {"reason": "Smoke test rejection."})
        s.check(rejected["status"] == "Rejected", f"rejected event is {rejected['status']}")
    if "main" in ctx:
        s.step("F4 Review and approval", "clarify, approve; reject another", review)

    # F7 Event information management ------------------------------------------------
    def edit():
        event = s.call("coordinator", "GET", f"/events/{ctx['main']['id']}")
        body = {k: event[k] for k in (
            "title", "purpose", "description", "startsAt", "endsAt", *NEEDS)}
        body["expectedAttendance"] = 160
        saved = s.call("coordinator", "PUT", f"/events/{event['id']}", body)
        s.check(saved["expectedAttendance"] == 160, "the edit was not saved")
    if "main" in ctx:
        s.step("F7 Event information", "Coordinator edits an important field", edit)

    # F11 Venue suitability ----------------------------------------------------------
    def suitability():
        ok = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/bookings/suitability",
                    s.booking_body(ctx["hall"]["id"], 0))
        s.check(ok["suitable"], f"hall should suit 150: {ok['reasons']}")
        too_many = s.call("coordinator", "POST",
                          f"/events/{ctx['main']['id']}/bookings/suitability",
                          s.booking_body(ctx["hall"]["id"], 0, headcount=500))
        s.check(not too_many["suitable"], "500 people should not fit a 220-seat hall")
    if {"main", "hall"} <= ctx.keys():
        s.step("F11 Venue suitability", "suits 150, refuses 500", suitability)

    # F12 Booking request, F13 approval ------------------------------------------------
    def book():
        booking = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/bookings",
                         s.booking_body(ctx["hall"]["id"], 0))
        s.check(booking["status"] == "Requested", f"new booking is {booking['status']}")
        event = s.call("coordinator", "GET", f"/events/{ctx['main']['id']}")
        s.check(event["status"] == "Planning", f"event after a request is {event['status']}")
        approved = s.call("venue staff", "POST", f"/booking-requests/{booking['id']}/approve")
        s.check(approved["status"] == "Confirmed", f"approved booking is {approved['status']}")
        ctx["hall_booking"] = booking
        extra = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/bookings",
                       {**s.booking_body(ctx["annex"]["id"], 0), "startsAt": s.at(0, 9),
                        "endsAt": s.at(0, 11)})
        rejected = s.call("venue staff", "POST", f"/booking-requests/{extra['id']}/reject",
                          {"reason": "Smoke test: annex closed that morning.", "suggestion": ""})
        s.check(rejected["status"] == "Rejected", f"rejected booking is {rejected['status']}")
    if {"main", "hall", "annex"} <= ctx.keys():
        s.step("F12/F13 Booking + approval", "request, confirm; reject another", book)

    # F9 Venue availability calendar ---------------------------------------------------
    def calendar():
        seen = s.call("venue staff", "GET",
                      f"/venues/{ctx['hall']['id']}/availability?from={s.date(0)}&to={s.date(0)}")
        s.check(any(e.get("bookingId") == ctx["hall_booking"]["id"] for e in seen["entries"]),
                "the confirmed booking is not on the calendar")
    if "hall_booking" in ctx:
        s.step("F9 Availability calendar", "the confirmed booking shows", calendar)

    # F14 Booking conflict detection ---------------------------------------------------
    def conflict():
        other = s.approved("Clashing event", 0)
        ctx["clash"] = other
        s.call("coordinator", "POST", f"/events/{other['id']}/bookings",
               s.booking_body(ctx["hall"]["id"], 0), expect=(409,))
    if "hall_booking" in ctx:
        s.step("F14 Conflict detection", "the same slot is refused", conflict)

    # US14.3/14.4 Holds expire ---------------------------------------------------------
    def hold_and_expire():
        event = s.approved("Held event", 2)
        expires = (local_now() + timedelta(seconds=6)).strftime("%Y-%m-%dT%H:%M:%S")
        held = s.call("venue staff", "POST", "/holds", {
            "venueId": ctx["annex"]["id"], "eventId": event["id"],
            "startsAt": s.at(2, 18), "endsAt": s.at(2, 21), "expiresAt": expires})
        time.sleep(8)
        swept = supabase_client.admin().rpc("sweep_tentative_holds", {}).execute().data
        s.check(int(held["id"]) in swept["expired"], f"the sweep did not expire it: {swept}")
        [booking] = [b for b in s.call("coordinator", "GET", f"/events/{event['id']}/bookings")
                     if b["id"] == held["id"]]
        s.check(booking["status"] == "Expired", f"held booking is {booking['status']}")
    if "annex" in ctx:
        s.step("US14.3/14.4 Holds", "a 6-second hold expires and is swept", hold_and_expire)

    # F15-F17 Equipment request, availability, reservation ---------------------------
    def equipment():
        items = s.call("tech support", "GET", "/equipment")
        item = max(items, key=lambda i: i["usableQuantity"])
        line = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/equipment-requests",
                      {"equipmentId": int(item["id"]), "quantity": 1,
                       "technicalRequirements": "Smoke test."})
        stock = s.call("tech support", "GET", f"/equipment-requests/{line['id']}/availability")
        s.check(any(str(c["equipmentId"]) == str(item["id"]) and c["shortfall"] == 0
                    for c in stock), f"no stock reported: {stock}")
        reserved = s.call("tech support", "POST", f"/equipment-requests/{line['id']}/reserve",
                          {"version": line["version"], "equipmentId": int(item["id"])})
        s.check(reserved["status"] == "Reserved", f"line is {reserved['status']}")
        ctx["line"] = reserved
    if "hall_booking" in ctx:
        s.step("F15-F17 Equipment", "request, check stock, reserve", equipment)

    # US12.1/12.2 Unavailability flags a booking; US14.5 replacement venue -------------
    def unavailability():
        event = s.approved("Flagged event", 3)
        ctx["flagged_event"] = event
        booking = s.call("coordinator", "POST", f"/events/{event['id']}/bookings",
                         s.booking_body(ctx["annex"]["id"], 3))
        s.call("venue staff", "POST", f"/venues/{ctx['annex']['id']}/unavailability",
               {"startDate": s.date(3), "endDate": s.date(3), "reasonType": "maintenance",
                "otherReason": ""})
        [flagged] = [b for b in s.call("coordinator", "GET", f"/events/{event['id']}/bookings")
                     if b["id"] == booking["id"]]
        s.check(flagged["status"] == "Needs replacement", f"booking is {flagged['status']}")
        ctx["flagged_booking"] = flagged
    if "annex" in ctx:
        s.step("US12.1/12.2 Unavailability", "marking dates flags the booking", unavailability)

    def replacement():
        booking = ctx["flagged_booking"]
        options = s.call("coordinator", "GET", f"/bookings/{booking['id']}/replacement-venues")
        s.check(any(v["id"] == ctx["hall"]["id"] for v in options), "the free hall is not offered")
        replaced = s.call("coordinator", "POST", f"/bookings/{booking['id']}/request-replacement",
                          {"venueId": ctx["hall"]["id"]})
        s.check(replaced["status"] == "Requested", f"replacement is {replaced['status']}")
    if "flagged_booking" in ctx:
        s.step("US14.5 Replacement venue", "search and request a replacement", replacement)

    # US4.4/US17 Safety check -------------------------------------------------------
    def safety():
        sent = s.call("coordinator", "POST", f"/events/{ctx['main']['id']}/safety-check")
        s.check(sent["status"] == "Pending Safety Check", f"sent event is {sent['status']}")
        s.call("safety officer", "GET", f"/events/{ctx['main']['id']}/safety-review")
        confirmed = s.call("safety officer", "POST",
                           f"/events/{ctx['main']['id']}/safety-check/approve", {})
        s.check(confirmed["status"] == "Confirmed", f"approved event is {confirmed['status']}")
    if "line" in ctx:
        s.step("US4.4/US17 Safety check", "send, review, approve: Confirmed", safety)

    # F18 Attendee registration -------------------------------------------------------
    def registration():
        event_id = ctx["main"]["id"]
        s.call("coordinator", "PUT", f"/events/{event_id}/registration",
               {"open": True, "capacity": 50})
        open_events = s.call("attendee", "GET", "/attendee/events")
        s.check(any(e["id"] == event_id for e in open_events), "not listed for Attendees")
        s.call("attendee", "POST", f"/attendee/events/{event_id}/registrations",
               {"name": "Casey Tan", "email": ACCOUNTS["attendee"]})
        second = s.call("attendee 2", "POST", f"/attendee/events/{event_id}/registrations",
                        {"name": "Morgan Lee", "email": ACCOUNTS["attendee 2"]})
        withdrawn = s.call("attendee 2", "POST",
                           f"/attendee/registrations/{second['id']}/withdraw")
        s.check(withdrawn["status"] == "Withdrawn", f"withdrawn is {withdrawn['status']}")
        listed = s.call("organiser", "GET", f"/events/{event_id}/registrations")
        statuses = sorted(r["status"] for r in listed["registrations"])
        s.check(statuses == ["Registered", "Withdrawn"], f"Organiser sees {statuses}")
    if "main" in ctx:
        s.step("F18 Attendee registration", "open, register, withdraw, list", registration)

    # F19 Event change requests --------------------------------------------------------
    def change_request():
        event = s.call("organiser", "GET", f"/events/{ctx['main']['id']}")
        body = {k: event[k] for k in (
            "title", "purpose", "description", "startsAt", "endsAt", *NEEDS)}
        proposed = s.call("organiser", "POST", f"/events/{event['id']}/change-request",
                          {**body, "expectedAttendance": 170, "note": "Smoke: more guests."})
        s.check(proposed["changeRequested"], "no pending change after proposing")
        accepted = s.call("coordinator", "POST", f"/events/{event['id']}/change-request/approve")
        s.check(accepted["expectedAttendance"] == 170, "the change was not applied")
        s.check(not accepted.get("arrangementReviewPending"),
                f"arrangement checks did not finish: {accepted.get('arrangementReview')}")
    if "main" in ctx:
        s.step("F19 Change requests", "propose, accept, recheck arrangements", change_request)

    # F20 Notifications ------------------------------------------------------------------
    def notices():
        for role in ("organiser", "coordinator", "venue staff", "tech support"):
            mine = s.call(role, "GET", "/notifications")
            s.check(bool(mine), f"{role} has no notifications")
    s.step("F20 Notifications", "each role has its notices", notices)

    # US9.5 Venue delete is blocked by a future booking -----------------------------------
    if "hall" in ctx:
        s.step("US9.5 Venue delete", "a venue with future bookings cannot be deleted",
               lambda: s.call("venue staff", "DELETE", f"/venues/{ctx['hall']['id']}",
                              expect=(409,)))

    # US4.6 Cancel an event --------------------------------------------------------------
    def cancel():
        event_id = ctx["main"]["id"]
        cancelled = s.call("coordinator", "POST", f"/events/{event_id}/cancel",
                           {"reason": "Smoke test complete."})
        s.check(cancelled["status"] == "Cancelled", f"event is {cancelled['status']}")
        bookings = s.call("coordinator", "GET", f"/events/{event_id}/bookings")
        s.check(all(b["status"] in ("Cancelled", "Rejected") for b in bookings),
                f"bookings left active: {[b['status'] for b in bookings]}")
        lines = s.call("coordinator", "GET",
                       f"/events/{event_id}/equipment-requests?includeRemoved=true")
        s.check(all(line["status"] == "Removed" for line in lines), "equipment not released")
        listed = s.call("organiser", "GET", f"/events/{event_id}/registrations")
        s.check(all(r["status"] != "Registered" for r in listed["registrations"]),
                "a registration is still Registered")
    if "main" in ctx:
        s.step("US4.6 Cancel an event", "releases bookings, equipment, registrations", cancel)

    # Tidy up: the other open smoke events end Cancelled too.
    for key in ("clash", "flagged_event"):
        if key in ctx:
            try:
                s.call("organiser", "POST", f"/events/{ctx[key]['id']}/cancel",
                       {"reason": "Smoke test complete."})
            except Failed as failed:
                print(f"note: could not cancel the {key} event: {failed}")

    failed = [r for r in s.results if r[0] == "FAIL"]
    print(f"\n{len(s.results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
