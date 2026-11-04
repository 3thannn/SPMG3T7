# Test Plan: Lincoln (ConnectSphere, SPMG3T7)

**Tester:** Lincoln · **Workload:** 12 tests (~160 min) · **Integration roles:** Integration 1: Lead and Tech Support · Integration 2: **lead** · Integration 3: Tech Support

Everything you need is in this file: accounts, setup recipes, your tests in run order, and the integration tests you play a role in. Each test shows the sprint, the user story, who implemented it and the Jira acceptance criteria, plus the steps that check each one.

**Rule:** you never test a story you implemented (or were the Sprint 1 buddy on). This list already respects that.

---

## 1. Accounts, setup and conventions

### 1.1 Accounts (password for all: `password`)

| Email | Name | Role | Lands on after sign-in |
|---|---|---|---|
| `organiser@connectsphere.com` | Dylan | Event Organiser | Events |
| `organiser2@connectsphere.com` | Riley | Event Organiser | Events |
| `organiser3@connectsphere.com` | Marcus | Event Organiser | Events |
| `coordinator@connectsphere.com` | Priya | Event Coordinator | Events |
| `coordinator2@connectsphere.com` | Sam Chen | Event Coordinator | Events |
| `coordinator3@connectsphere.com` | Aisha | Event Coordinator | Events |
| `coordinatorlead@connectsphere.com` | Jordan | Event Coordinator Lead | Unassigned Queue |
| `venuestaff@connectsphere.com` | Sam | Venue Staff | Venues |
| `safetyofficer@connectsphere.com` | Alex | Safety Officer | Safety Review |
| `technicalsupport@connectsphere.com` | Bryan | Technical Support | Equipment Requests |
| `attendee@connectsphere.com` | Casey | Attendee | Upcoming Events |
| `attendee2@connectsphere.com` | Morgan | Attendee | Upcoming Events |

Also `attendee3@` to `attendee8@connectsphere.com` (Wei Ling Tan, Arjun Nair, Hannah Lim, Farid Ismail, Chloe Ng, Daniel Koh), all Attendees, same password.

Note: Venue Staff is "Sam" and the second Coordinator is "Sam **Chen**". Don't mix them up.

**Demo data already in the database (reseeded 1 Nov 2026):** 22 venues, 18 equipment items and 51 realistic events in every status, with bookings, equipment, safety reviews, registrations and notifications. Your tests make their own `T…` data alongside it. Don't change the seeded events unless a step says to, because they are the demo for the prof.

### 1.2 Before you start (every tester)

1. Pull `main`.
2. Terminal 1:
   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --reload --port 8000
   ```
3. Terminal 2:
   ```bash
   cd frontend
   npm run dev
   ```
4. Open `http://localhost:5173`. → The page says **Backend connected**.
5. Use a private/incognito window per account when a test switches roles a lot, so you don't have to keep signing out.

All testers share one Supabase database, so follow the naming rules below and you won't break each other's tests.

### 1.3 Naming and data rules

- **Prefix everything you create with the test ID**, e.g. event `T7.1 Review event`, venue `T15.1 Hall`. This makes it easy to find in lists, and the screenshots show which test made it.
- **Use your own venues** (Recipe R0) for anything that books, holds, changes setup/turnaround or marks unavailable. Seeded venues are only for read-only tests and US14.1 / US14.5.
- **Event dates** must be in the future. Use the dates written in each test.
- Write down every **event ID**. It is the number at the end of the URL, e.g. `http://localhost:5173/#/events/123` → ID 123.

### 1.4 Recording results

- Tick each **→ Expected** line that passes. If one fails, mark the test ☒, log a Jira bug (template at the end) and keep going with the rest of the steps when you can.
- 📸 = take a screenshot. Name it `US<story>_<step>_<name>.png`, e.g. `US15.1_06_blocked.png`.
- The **Acceptance criteria** table under each test shows which steps check each AC. Use it for the traceability matrix.

---

## 2. Setup recipes (reused by many tests)

Each test says which recipe to run first, e.g. "Run R3 with title `T7.1 Approve me`". Replace the values in `<angle brackets>`.

### R0: Make your own test venue (Venue Staff, 2 min)
1. Sign in as `venuestaff@connectsphere.com`.
2. Top nav → **Add venue**.
3. Fill in:
   - Name: `<venue name>`
   - Location: `QA Block`
   - Capacity: `<capacity, default 300>`
   - Setup time (minutes): `<setup, default 0>`
   - Turnaround time (minutes): `<turnaround, default 0>`
   - Facilities: `Projector, PA system, Stage`
   - Accessibility features: `Wheelchair access, Hearing loop`
   - Supported layouts: `Theatre, Classroom, Banquet`
   - Operating hours: `00:00-23:59` (open every day, so hours never block your test)
4. Click **Add venue**.
   → Venue saved and shows in the catalogue.

### R1: Submitted event (Organiser, 3 min)
1. Sign in as `organiser@connectsphere.com`.
2. Top nav → **Create**.
3. Fill in:
   - Title: `<title>`
   - Description: `Test event for <test ID>`
   - Purpose: `QA testing`
   - Starts: `<date> <start time>` (e.g. 8 Dec 2026 08:00; the date picker uses your laptop's format, dd/mm/yyyy in Singapore)
   - Ends: `<date> <end time>` (e.g. 8 Dec 2026 20:00)
   - Expected attendance: `<attendance, default 50>`
   - Venue requirements: tick **Projector** and **PA system**
   - Preferred layout: **Theatre**
   - Accessibility needs: tick **Wheelchair access**
   - Equipment needs: `2 wireless microphones`
   - Registration needs: `Open registration`
4. Click **Submit**.
   → Status **Submitted**. No Coordinator shown. Write down the event ID.

### R2: Under Review, assigned to a Coordinator (+2 min)
1. Run R1.
2. Sign in as `coordinatorlead@connectsphere.com` → lands on **Unassigned Queue**.
3. Type the title in **Search events...**.
4. Click **+ Assign Coordinator** on that event → in the **Assign Coordinator** box click **Priya** (or the Coordinator the test says). Clicking the name assigns straight away.
   → Event leaves the queue. Open it: status **Under Review**, assigned Coordinator shown.

### R3: Approved event (+1 min)
1. Run R2.
2. Sign in as `coordinator@connectsphere.com` → **Events** → open the event.
3. Under **Review decision**, click **Approve event**.
   → Status **Approved**.

### R4: Planning event with a Confirmed booking (+4 min)
1. Run R3. If you don't have a venue yet, run R0.
2. As Priya, on the event page, go to the venue bookings section → **Request a venue**.
3. Venue: `<your venue>`. Starts/Ends: inside the event time (e.g. `10:00`–`12:00` on the event date). Headcount: `<attendance>`. Layout: `Theatre`. Facilities: `Projector`. Accessibility: `Wheelchair access`.
   → Shows **Suitable**.
4. Click **Request venue**.
   → Booking **Requested**. Event status **Planning**.
5. Sign in as `venuestaff@connectsphere.com` → **Booking Requests** → find the booking → **Approve**.
   → Booking **Confirmed**.

### R5: Confirmed event (+3 min)
1. Run R4. Don't add equipment lines (or make sure every line is Reserved).
2. As Priya, open the event → **Safety check** section → **Send for safety check**.
   → Status **Pending Safety Check**.
3. Sign in as `safetyofficer@connectsphere.com` → **Safety Review** → open the event → **Approve safety check**.
   → Status **Confirmed**.

**Shortcut times:** R1 ≈ 3 min, R2 ≈ 5, R3 ≈ 6, R4 ≈ 10, R5 ≈ 13.

---

---

---

## 3. Your tests: 12 tests (~160 min)

| # | User story | Sprint | Implemented by |
|---|---|---|---|
| L1 | US1.4 Add Coordinator Lead and Safety Officer roles | 3 | Ethan |
| L2 | US8.1 Automatically assign a Coordinator on submission | 2 | Ethan |
| L3 | US8.2 Lead views the unassigned queue | 3 | Ethan |
| L4 | US8.3 Lead assigns a Coordinator | 3 | Ethan |
| L5 | US8.6 Coordinators only manage events assigned to them | 3 | Ethan |
| L6 | US19.0 Seed sample equipment data | 3 | Ariel |
| L7 | US19.1 Equipment catalogue | 3 | Ariel |
| L8 | US19.2 Coordinator requests equipment for an event | 3 | Ariel |
| L9 | US19.3 Check equipment availability and reserve it | 4 | Ariel |
| L10 | US4.4 Pending Safety Check status and transitions | 4 | Ivy |
| L11 | US17.1 Safety Officer review queue | 4 | Ivy |
| L12 | US17.2 Safety Officer records a decision | 4 | Ivy |

### L1 · US1.4: Add Coordinator Lead and Safety Officer roles

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US1.4** | SPMG3T7-49 | Ethan | **Lincoln** | 10 min |

> **User story:** As the development team, I want the Event Coordinator Lead and Safety Officer roles added to the system, so that the new Week 7 features can be locked to the right people.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Both roles exist and can be given to test accounts. | 1, 4 |
| **AC2** | Login sends each role to its own landing view (Lead → unassigned queue in US8.2, Safety Officer → safety review queue in US17.1). | 2, 5 |
| **AC3** | US1.3's baseline access rule applies to both: out-of-role pages are blocked with a clear message. | 3, 6 |
| **AC4** | Fine-grained 'who sees which event' rules sit on US8.6 / US17.1, not here. | Tested in US8.6 / US17.1 |

**Setup:** none

**Steps**

1. Sign in as `coordinatorlead@connectsphere.com`.
   → Header shows **Jordan** and **Event Coordinator Lead**.
2. Check where you land.
   → **Unassigned Queue**. Nav also has **Team Assignments**. 📸
3. Type `#/safety-review`, then `#/venues/new`.
   → Both show "not open to your role".
4. Sign out. Sign in as `safetyofficer@connectsphere.com`.
   → Header shows **Alex** and **Safety Officer**.
5. Check where you land.
   → **Safety Review**. 📸
6. Type `#/unassigned-queue`, then `#/events/new`.
   → Both show "not open to your role".

**Pass/Fail:** ☐

---

### L2 · US8.1: Automatically assign a Coordinator on submission

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US8.1** | SPMG3T7-37 | Ethan | **Lincoln** | 8 min |

> **User story:** As the system, I want to automatically assign a Coordinator to a newly submitted event, so that every event has a single responsible owner without requiring manual selection.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | On an event's status changing to Submitted, the system assigns one available Event Coordinator automatically. | 1–2 (switched off by US8.2) |
| **AC2** | Assignment logic: round-robin across all Coordinator accounts (assumption — simplest fair-distribution rule, not customer-confirmed). | Superseded by US8.2 |
| **AC3** | Assigned Coordinator is shown on the event. | 3 |
| **AC4** | US4.1/US5.1/US5.2 visibility narrows to the assigned Coordinator only once set. | 4 and US8.6 |
| **AC5** | Migration note: Sprint 1's already-submitted test events need a one-time backfill run to get an assigned Coordinator when this ships. | 3–4 |

**Setup:** none

**Steps**

> US8.2 (Week 7 change #5) switched auto-assignment off. This test checks it stays off and that events assigned before then kept their Coordinator. Record as **Pass (superseded by US8.2)**.

1. Run R1 for `T8.1 No auto assign`.
   → Event shows **no** Coordinator. Status **Submitted**.
2. Sign in as `coordinatorlead@connectsphere.com` → **Unassigned Queue**.
   → `T8.1 No auto assign` is listed.
3. **Team Assignments**.
   → `T8.1 No auto assign` shows **Unassigned**. Every seeded event shows the Coordinator the Lead assigned. 📸
4. "Events auto-assigned before Week 7 keep their Coordinator" (US8.2 AC5) can't be checked on screen, because the 1 Nov reseed has no pre-Week 7 events left. Write **N/A, data reset** for this line.

**Pass/Fail:** ☐ (Pass = superseded behaviour confirmed)

---

### L3 · US8.2: Lead views the unassigned queue

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US8.2** | SPMG3T7-50 | Ethan | **Lincoln** | 10 min |

> **User story:** As an Event Coordinator Lead, I want newly submitted events to land in an unassigned queue I can see, so that I can decide who should handle each one.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | US8.1's auto-assignment is switched off: a newly Submitted event has no Coordinator. | 1 |
| **AC2** | Queue lists all Submitted events with no assigned Coordinator, oldest first, showing event name, proposed date, expected attendance, Organiser and submitted time. | 2–3 |
| **AC3** | Lead can open an event and see its basic info, read-only. | 4 |
| **AC4** | Only the Lead role can see the queue. | 5 |
| **AC5** | Events auto-assigned before this change keep their Coordinator (assumption, check with customer). | US8.1 step 3 |

**Setup:** R1 ×2

**Steps**

1. Run R1 for `T8.2 First`. Wait 1 minute. Run R1 for `T8.2 Second`.
   → Neither has a Coordinator.
2. Sign in as `coordinatorlead@connectsphere.com` → **Unassigned Queue**.
   → Both listed, **oldest first** (`T8.2 First` above `T8.2 Second`). 📸
3. Check what each row shows.
   → Event name, proposed date, expected attendance, Organiser (Dylan) and submitted time.
4. The queue card shows the basic info. To open the full event, type `#/events/<T8.2 First ID>`.
   → Event shown **read-only**: no edit, Approve event, Reject event or Request clarification.
5. Sign in as `coordinator@connectsphere.com`. Type `#/unassigned-queue`.
   → "not open to your role". 📸

**Pass/Fail:** ☐

---

### L4 · US8.3: Lead assigns a Coordinator

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US8.3** | SPMG3T7-51 | Ethan | **Lincoln** | 10 min |

> **User story:** As an Event Coordinator Lead, I want to assign an unassigned event to a specific Event Coordinator, so that every event has one responsible owner.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Lead picks a Coordinator from the list of Coordinator accounts. | 1–2 |
| **AC2** | Once assigned, the event leaves the unassigned queue and shows the assigned Coordinator. | 3–4 |
| **AC3** | Assignment is timestamped and attributable (who/when), reusing US4.2's audit pattern. | 5 |
| **AC4** | Assigned Coordinator gets a notification (US10.2). | 6 |
| **AC5** | Only the Lead can assign. | 7 |

**Setup:** `T8.2 First` and `T8.2 Second` from US8.2

**Steps**

1. As Jordan → **Unassigned Queue** → `T8.2 First` → **+ Assign Coordinator**.
2. Open the list.
   → The **Assign Coordinator** box lists only Coordinator accounts (Priya, Sam Chen, Aisha). No Lead, Organiser or other roles. 📸
3. Click **Priya** (assigns straight away).
   → Success. `T8.2 First` leaves the queue.
4. Open `T8.2 First`.
   → Assigned Coordinator **Priya**. Status **Under Review** (US4.5).
5. **Status history** / **Coordinator assignment**.
   → Shows assigned by **Jordan** with date and time. 📸
6. Sign in as Priya → **Notifications**.
   → New notice that `T8.2 First` was assigned to her. 📸
7. As Priya, check there is no way to assign `T8.2 Second` (no Unassigned Queue link, and the URL is refused).

**Pass/Fail:** ☐

---

### L5 · US8.6: Coordinators only manage events assigned to them

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US8.6** | SPMG3T7-52 | Ethan | **Lincoln** | 15 min |

> **User story:** As an Event Coordinator, I want to only see and manage events assigned to me, so that it's clear who is responsible for each event.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinators can view (US5.1), edit (US5.2), see status of (US4.1), decide on (US7.1) and request clarification on (US7.3) only events assigned to them. | 2–5 |
| **AC2** | Unassigned events are not visible to regular Coordinators. | 2, 6 |
| **AC3** | Trying to act on someone else's event is blocked with a clear message (US1.3 pattern). | 3, 5 |
| **AC4** | The Lead can still view all events. | 7 |
| **AC5** | Enforced in the database (RLS), not just hidden in the UI. | 8 |
| **AC6** | Regression: rerun US4.1/5.1/5.2/7.1/7.3 tests with an assigned and a non-assigned Coordinator account. | 2–5 |

**Setup:** assign `T8.2 Second` to **Sam Chen**

**Steps**

1. As Jordan, assign `T8.2 Second` to **Sam Chen**. Run R1 for `T8.6 Unassigned` and leave it in the queue.
2. Sign in as Priya → **Events**.
   → `T8.2 First` is listed. `T8.2 Second` and `T8.6 Unassigned` are **not**. 📸
3. Type `#/events/<T8.2 Second ID>`.
   → Refused with a clear message. No event details shown. 📸
4. Sign in as `coordinator2@connectsphere.com` (Sam Chen) → open `T8.2 Second`.
   → Can view and edit it, and sees **Approve event**, **Reject event** and **Request clarification**.
5. As Sam Chen, type `#/events/<T8.2 First ID>`.
   → Refused (Priya's event).
6. As Sam Chen → **Events**.
   → `T8.6 Unassigned` isn't listed.
7. Sign in as Jordan → **Team Assignments**.
   → All three events visible (Priya's, Sam Chen's, Unassigned).
8. Database-level check: from `backend/`, run
   ```bash
   pytest tests/test_lead_rls.py tests/test_event_route_guards.py -q
   ```
   → All pass. 📸 (Paste the terminal output as evidence of RLS.)

**Pass/Fail:** ☐

---

### L6 · US19.0: Seed sample equipment data

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US19.0** | SPMG3T7-64 | Ariel | **Lincoln** | 5 min |

> **User story:** As the development team, I want a set of sample equipment records created early, so that US19.2 (requests) and US19.3 (availability + reservation) have real data to test and demo against instead of an empty catalogue.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | At least 8-10 equipment items created via US19.1's create functionality (e.g. projectors, microphones, speakers, laptops, screens), with varied total quantities and locations. | 1–2 |
| **AC2** | Some items must have units marked out of service (damaged/maintenance) so US19.3's availability maths can be tested. | 3 |
| **AC3** | Can be done manually or with a small seed script. | Note |
| **AC4** | Should be done right after US19.1 works so US19.2/US19.3 aren't blocked. | Note |

**Setup:** none

**Steps**

1. Sign in as `coordinator@connectsphere.com` → **Equipment**.
   → 18 items, including Epson laser projector, Portable short-throw projector, Wireless handheld microphone, Lapel microphone, Powered PA speaker, Portable monitor speaker, Presentation laptop, Touchscreen laptop, Tripod projection screen, Large LED display. 📸
2. Check they vary.
   → Quantities range from 3 to 20. Locations include Main Campus AV Store, Library Store, East Campus Store.
3. Check out-of-service units.
   → Some items have them, e.g. Wireless handheld microphone 20 total / **3** out of service ("Battery faults"), Presentation laptop 10 / **2**.

**Pass/Fail:** ☐

---

### L7 · US19.1: Equipment catalogue

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US19.1** | SPMG3T7-63 | Ariel | **Lincoln** | 12 min |

> **User story:** As a Technical Support Staff member, I want to keep a list of our equipment and how much of it is usable, so that availability checks are based on real stock.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Tech Support can create and edit equipment items: name, type, description, location, total quantity (whole number ≥ 0). | 1–4 |
| **AC2** | Each item records how many units are out of service (damaged or under maintenance) and the reason. Out-of-service units are never counted as available. | 2–4 |
| **AC3** | Coordinators can view the catalogue, read-only. | 5 |
| **AC4** | Only Tech Support can create or edit. | 5–6 |

**Setup:** none

**Steps**

1. Sign in as `technicalsupport@connectsphere.com` → **Equipment** → **Add equipment**.
2. Name `T19 Test projector`, Type `Projector`, Description `QA item`, Location `QA Store`, Total quantity `10`, Out-of-service quantity `2`, Out-of-service reason `Lamp replacement` → **Save equipment**.
   → Saved. **Usable quantity** shows **8**. 📸
3. **Edit equipment**: Total quantity `-1` → **Save equipment**.
   → Error: must be a whole number ≥ 0.
4. Out-of-service quantity `12` (more than the total).
   → Refused. Put it back to Total `10`, Out of service `2`.
5. Sign in as Priya → **Equipment** → open `T19 Test projector`.
   → Marked **Read-only**. No **Add equipment**, **Edit equipment** or **Delete equipment**. 📸
6. Sign in as Venue Staff → type `#/equipment`.
   → Refused with "not open to your role" (only Coordinators, the Lead and Tech Support can see the catalogue).

**Keep:** `T19 Test projector` (10 total, 2 out of service), for US19.3.

**Pass/Fail:** ☐

---

### L8 · US19.2: Coordinator requests equipment for an event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US19.2** | SPMG3T7-65 | Ariel | **Lincoln** | 15 min |

> **User story:** As an Event Coordinator, I want to record what equipment an event needs, so that Technical Support Staff know what to check and reserve.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | The assigned Coordinator can add one or more equipment lines to an event: equipment type (from the catalogue), quantity (whole number ≥ 1), and technical notes. The time needed defaults to the event's start and end time. | 2–6 |
| **AC2** | New lines start as Requested. The Coordinator can edit or remove a line while it is still Requested. | 4–6 |
| **AC3** | Tech Support see all Requested lines in a queue, oldest first, and can add notes or update the line as arrangements are made. | 7–8 |
| **AC4** | Tech Support are notified of new requests (US10.2). | 9 |

**Setup:** R3 `T19.2 Equip event` on **Tue 15 Dec 2026 09:00–17:00**

**Steps**

1. Run R3.
2. As Priya, open the event → **Equipment requests** → **Request equipment**.
   → **Needed from** / **Needed until** are pre-filled with `15 Dec 2026 09:00` / `17:00`. 📸
3. Equipment type `Microphone`, Catalogue item `Wireless handheld microphone`, Quantity `0` → **Request equipment**.
   → Refused: quantity must be at least 1.
4. Quantity `3`, Technical requirements `Need spare batteries` → **Request equipment**.
   → Line listed as **Requested**. Add a second line: `Presentation laptop` × `2`.
5. On the laptop line click **Edit** → Quantity `1` → **Save request**.
   → Updated.
6. On the laptop line click **Remove**.
   → Removed. Only the microphone line is left.
7. Sign in as `technicalsupport@connectsphere.com` → **Equipment Requests**.
   → The microphone line is in the queue, **oldest first**. 📸
8. Open it → **Update request** → add arrangement notes `Batteries charged` → save.
   → Notes saved. Priya can see them on the event.
9. Tech Support → **Notifications**.
   → A notice about the new equipment request. 📸

**Pass/Fail:** ☐

---

### L9 · US19.3: Check equipment availability and reserve it

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US19.3** | SPMG3T7-77 | Ariel | **Lincoln** | 20 min |

> **User story:** As a Technical Support Staff member, I want to see the available qty of an item at the event's time period and reserve it, so that the same equipment is never tied/promised to two events at once.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | For a Requested equipment, the system shows the available quantity for that time: total − out of service − quantity already reserved for events whose times overlap. | 3, 5 |
| **AC2** | Reserve is only allowed if the available quantity is at least the requested quantity. Otherwise it is blocked and the shortfall is shown. Tech Support can instead mark the line Unavailable with a reason. | 4, 6–7 |
| **AC3** | A reservation stays linked to its event and reduces the available quantity for overlapping events. | 5 |
| **AC4** | The Coordinator is notified when a equipment is Reserved or Unavailable (US10.2). | 8 |
| **AC5** | Test case: 10 projectors, 2 out of service, 6 reserved for an overlapping event → at most 2 can be reserved. | 5–10 |
| **AC6** | Assumption: equipment overlap uses the equipment request’s needed-from/until time, which is defaulted to the event’s start/end time. | 1 |

**Setup:** `T19 Test projector` (10 total, 2 out of service) from US19.1; R3 `T19.3 Event A` **15 Dec 2026 09:00–17:00**; R3 `T19.3 Event B` **15 Dec 2026 13:00–18:00** (overlaps A)

**Steps**

1. As Priya: Event A → **Request equipment** → `T19 Test projector` × **6**. Event B → `T19 Test projector` × **3**.
2. As Tech Support → **Equipment Requests** → open Event A's line.
3. → **Reserve equipment** shows **Total stock 10**, **Out of service 2**, **Already reserved 0**, **Available 8**. 📸
4. **Reserve**.
   → Line **Reserved**.
5. Open Event B's line.
   → **Available 2** (10 − 2 − 6). 📸
6. **Reserve** (asks for 3).
   → **Blocked**. Shows the shortfall (needs 3, only 2 available). 📸
7. **Mark Unavailable**, Reason for Unavailable `Only 2 projectors free on 15 Dec` → save.
   → Line **Unavailable**.
8. Priya → **Notifications**.
   → Notices for Event A **Reserved** and Event B **Unavailable** (with the reason). 📸
9. As Priya, Event B line → **Revise and resubmit** → Quantity `2` → **Resubmit request**.
10. As Tech Support, open it → **Reserve**.
    → Reserved. That's the AC test case: at most 2 can be reserved. 📸

**Pass/Fail:** ☐

---

### L10 · US4.4: Pending Safety Check status and transitions

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US4.4** | SPMG3T7-74 | Ivy | **Lincoln** | 20 min |

> **User story:** As the system, I want a Pending Safety Check stage between planning and preparation, so that no event moves forward without a safety sign-off.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | New status label 'Pending Safety Check' added to US4.1's set. | 7 |
| **AC2** | New valid transitions:<br>• Planning → Pending Safety Check (once all active venue bookings are Confirmed and equipment is reserved)<br>• Pending Safety Check → Confirmed (Safety Officer approves)<br>• Pending Safety Check → Planning (Safety Officer requests changes or rejects, see US17.2) | 2–6 (Pending → Confirmed / Planning: US17.2) |
| **AC3** | Event can't reach Confirmed any other way. | 8 |
| **AC4** | Extends US4.3's trigger rather than replacing it. | Code (no UI test) |
| **AC5** | Assumption: 'preparation' in the customer brief = our Confirmed status. | Note |

**Setup:** R0 `T4.4 Hall`; R3 `T4.4 Safety A` and R3 `T4.4 Safety B`, both **Fri 18 Dec 2026 09:00–17:00**

**Steps**

1. Event A, as Priya: request `T4.4 Hall` **18 Dec 10:00–12:00**.
   → Event **Planning**. Booking **Requested**.
2. Open the **Safety check** section.
   → **Send for safety check** is refused or disabled, saying a venue booking isn't Confirmed yet. 📸
3. As Venue Staff, **Approve** the booking. As Priya, add equipment: `Lapel microphone` × 2.
4. **Send for safety check**.
   → Refused: equipment isn't reserved yet. 📸
5. As Tech Support, **Reserve** the lapel microphones.
6. As Priya → **Send for safety check**.
   → Status **Planning → Pending Safety Check**. 📸
7. **Events** filter.
   → **Pending Safety Check** is one of the labels, and the event shows it.
8. As Priya and as Organiser, look for any way to set **Confirmed**.
   → None. Only the Safety Officer can move it on (US17.2).
9. Event B: request `T4.4 Hall` **18 Dec 13:00–15:00**. Venue Staff approves. Priya → **Send for safety check** (no equipment).
   → **Pending Safety Check**. (Used in US17.2.)

**Pass/Fail:** ☐

---

### L11 · US17.1: Safety Officer review queue

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US17.1** | SPMG3T7-75 | Ivy | **Lincoln** | 10 min |

> **User story:** As a Safety Officer, I want to see events waiting for a safety check with everything I need to review them, so that I can assess them without chasing people for info.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | List shows events in Pending Safety Check, oldest first. | 1–2 |
| **AC2** | Detail view shows expected attendance, each booked venue's capacity, layout, accessibility and known restrictions, reserved equipment, and the event's accessibility requirements. | 3 |
| **AC3** | Read-only. | 4 |
| **AC4** | Safety Officer role only. | 5 |

**Setup:** `T4.4 Safety A` and `T4.4 Safety B` in Pending Safety Check

**Steps**

1. Sign in as `safetyofficer@connectsphere.com` → **Safety Review**.
   → Both events listed, **oldest first** (A, sent first, above B). Nothing in Planning/Confirmed is shown. 📸
2. Check the rows.
   → Each shows the title, the status Pending Safety Check and the expected attendance.
3. Open `T4.4 Safety A`.
   → Shows expected attendance; each booked venue's **capacity, layout, accessibility and known restrictions** (`T4.4 Hall`); **reserved equipment** (Lapel microphone × 2); the event's **accessibility requirements** (Wheelchair access). 📸
4. Check for edit controls.
   → None. Only the decision buttons (US17.2).
5. Sign in as Priya → type `#/safety-review`.
   → "not open to your role".

**Pass/Fail:** ☐

---

### L12 · US17.2: Safety Officer records a decision

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US17.2** | SPMG3T7-76 | Ivy | **Lincoln** | 25 min |

> **User story:** As a Safety Officer, I want to approve, reject, or request changes to an event's safety arrangements, so that only safe events move into preparation.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Approve → event moves to Confirmed. | 1–2 |
| **AC2** | Request changes → back to Planning; note required; affected venue/equipment arrangements flagged for re-review; assigned Coordinator notified (US10.2). | 3–7 |
| **AC3** | Reject → reason required. Assumption: back to Planning with the reason. | 8–9 |
| **AC4** | Every decision is timestamped and attributable (US4.2 audit pattern). | 2, 10 |
| **AC5** | An event coming back into Pending Safety Check needs a fresh decision. | 7 |

**Setup:** US17.1 state

**Steps**

1. As Alex, open `T4.4 Safety A` → **Approve safety check**.
   → Status **Confirmed** (not "Approved"). Leaves the queue. 📸
2. As Priya, open Event A.
   → **Confirmed**. **Earlier decisions on this event** shows Approved by **Alex** with date/time.
3. As Alex, open `T4.4 Safety B` → **Request changes** with **What needs to change** empty.
   → Refused: a note is required.
4. Note `Please provide an evacuation plan and fire exit map for T4.4 Hall` → submit.
   → Event **Pending Safety Check → Planning**. 📸
5. As Priya, open Event B.
   → The note is shown. The affected arrangement (`T4.4 Hall` booking) is listed under **Flagged for re-review**. 📸
6. Priya → **Notifications**.
   → A notice that the Safety Officer requested changes, with the note. 📸
7. Priya → **Send for safety check** straight away.
   → Refused (open re-review flags). Click **Mark re-reviewed** on the flag → **Send for safety check**.
   → **Pending Safety Check** again. In Alex's **Safety Review** it's back in the queue and needs a **new** decision (the earlier one is listed as history).
8. As Alex → **Reject safety check** with an empty reason.
   → Refused: a reason is required.
9. Reason `Fire exits blocked by staging` → reject.
   → Event back to **Planning** with the reason shown. Priya is notified.
10. Event B → **Earlier decisions on this event**.
    → Changes requested and Rejected, each with Alex and a timestamp. 📸

**Pass/Fail:** ☐

---

---

## 4. Integration tests (all-hands, after the story tests)

Your roles: Integration 1: Lead and Tech Support · Integration 2: **lead** · Integration 3: Tech Support

Each scenario has a **lead** who drives and fills in the result, and **players** who sign in as each role. Use **unique titles**: `INT1 …`, `INT2 …`, `INT3 …`.

### INTEGRATION 1: Full event lifecycle
**Lead:** Dylan · **Players:** Organiser = Ethan, Lead = Lincoln, Coordinator (Priya) = Ariel, Venue Staff = Ivy, Tech Support = Lincoln, Safety Officer = Ivy, Attendees = Ethan · **Time:** 40 min
**Covers:** US2.1, US8.2, US8.3, US4.5, US7.3, US11.1, US11.2, US7.1, US14.1, US18.1, US16.1, US19.2, US19.3, US4.4, US17.1, US17.2, US20.1, US10.1, US10.2

1. Organiser creates and submits `INT1 Annual Conference`, **Wed 13 Jan 2027 09:00–17:00**, attendance 120. → **Submitted**, no Coordinator.
2. Lead assigns Priya from the Unassigned Queue. → **Under Review**. Priya notified.
3. Priya → **Request clarification** "Confirm attendance". → Organiser notified.
4. Organiser proposes attendance 130 → Priya **Approve changes**. → Attendance 130.
5. Priya → **Approve event**. → **Approved**. Organiser notified.
6. Venue Staff makes R0 `INT1 Hall` (capacity 200). Priya requests it 09:00–17:00 (Suitable), plus **Seminar Room 4** 13:00–15:00, headcount 30 (clear layout/facilities/accessibility). → Event **Planning**.
7. Venue Staff approves both. → **Confirmed** bookings. Priya notified.
8. Priya requests `Wireless handheld microphone` × 3. Tech Support reserves. → **Reserved**.
9. Priya → **Send for safety check**. → **Pending Safety Check**.
10. Safety Officer reviews in the queue → **Approve safety check**. → **Confirmed**.
11. Priya opens registration (capacity 130). Casey and Morgan register. → Both **Registered**. Places left 128.
12. Check the **Status history**: Submitted → Under Review → Approved → Planning → Pending Safety Check → Confirmed, each with who/when.

- [ ] All transitions right · [ ] Notifications at each step · [ ] Each role saw only what it should · [ ] History complete

**Pass/Fail:** ☐

### INTEGRATION 2: Venue unavailability crisis
**Lead:** Lincoln · **Players:** Coordinator = Ariel, Venue Staff = Ethan · **Time:** 25 min
**Covers:** US14.1, US16.1, US12.1, US12.2, US10.2, US14.5, US12.3

1. R0 `INT2 Hall` (setup 15, turnaround 15). R3 `INT2 Event` **Thu 14 Jan 2027 09:00–17:00**. Priya requests `INT2 Hall` 10:00–12:00 (empty layout/facilities/accessibility). Venue Staff approves. → **Confirmed**.
2. Venue Staff marks `INT2 Hall` unavailable **13–15 Jan 2027**, reason **Safety concern**. → "1 booking flagged…"
3. Priya: booking **Needs replacement** with reason and dates. Event status unchanged. One notice.
4. Priya → **Find replacement** → filter Location `Library` → **Seminar Room 4** → **Request replacement**. → Old **Replaced**, new **Requested**.
5. Venue Staff approves Seminar Room 4. → **Confirmed**.
6. `INT2 Hall` availability for 10–20 Jan → shows the 13–15 Jan unavailability. The Replaced booking doesn't hold the slot any more.

- [ ] Auto-flagged · [ ] Replacement search excludes original · [ ] History kept (Replaced visible) · [ ] Event recovered

**Pass/Fail:** ☐

### INTEGRATION 3: Safety check loop
**Lead:** Ivy · **Players:** Coordinator = Dylan, Safety Officer = Ethan, Tech Support = Lincoln · **Time:** 25 min
**Covers:** US4.4, US17.1, US17.2, US10.2, US19.3, US20.1

1. R4 `INT3 Gala` **Fri 15 Jan 2027 18:00–22:00**, attendance 300, at R0 `INT3 Hall` (capacity 400). Priya requests `Powered PA speaker` × 2. → Event **Planning**.
2. Priya → **Send for safety check**. → Refused (equipment not reserved). Tech Support reserves. Priya sends again. → **Pending Safety Check**.
3. Safety Officer → **Request changes** "Add crowd management plan". → **Planning**. Booking flagged for re-review. Priya notified.
4. Priya → **Mark re-reviewed** → **Send for safety check**. → **Pending Safety Check**, needs a fresh decision.
5. Safety Officer → **Approve safety check**. → **Confirmed**.
6. Priya opens registration. Casey registers. → Works (normal flow resumes).

- [ ] Can't skip the safety check · [ ] Request-changes loop works · [ ] Final approval → Confirmed · [ ] Registration opens after

**Pass/Fail:** ☐

---

---

## 5. Your results

| # | Test | Pass / Fail | Bugs logged (Jira keys) |
|---|---|---|---|
| L1 | US1.4 Add Coordinator Lead and Safety Officer roles | ☐ | |
| L2 | US8.1 Automatically assign a Coordinator on submission | ☐ | |
| L3 | US8.2 Lead views the unassigned queue | ☐ | |
| L4 | US8.3 Lead assigns a Coordinator | ☐ | |
| L5 | US8.6 Coordinators only manage events assigned to them | ☐ | |
| L6 | US19.0 Seed sample equipment data | ☐ | |
| L7 | US19.1 Equipment catalogue | ☐ | |
| L8 | US19.2 Coordinator requests equipment for an event | ☐ | |
| L9 | US19.3 Check equipment availability and reserve it | ☐ | |
| L10 | US4.4 Pending Safety Check status and transitions | ☐ | |
| L11 | US17.1 Safety Officer review queue | ☐ | |
| L12 | US17.2 Safety Officer records a decision | ☐ | |

**Done on:** ___________

---

## Bug report template (Jira)

```
Summary: [US#.#] <what went wrong>
User story: US#.# (SPMG3T7-##)
Test / step: TEST US#.# step #
Severity: Critical (blocks core flow) / High (feature broken) / Medium (works with issues) / Low (cosmetic)

Steps to reproduce:
1.
2.

Expected (from the AC): 
Actual: 

Account / role used: 
Browser + OS: 
Evidence: <screenshot file names>
Found by: <name>   Date: 
```

## Notes

- Take a screenshot at every 📸.
- If a step can't run because an earlier test failed, mark it **Blocked** and say which test blocked it.
- Re-run failed steps after the fix and add "Retest: Pass, <date>" under the test.
- Tests that point to `pytest` files show the database/server rules that the UI can't reach. Paste the terminal output as evidence.
