# Test Plan: Ariel (ConnectSphere, SPMG3T7)

**Tester:** Ariel · **Workload:** 12 tests (~162 min) · **Integration roles:** Integration 1: Coordinator (Priya) · Integration 2: Coordinator (Priya)

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

## 3. Your tests: 12 tests (~162 min)

| # | User story | Sprint | Implemented by |
|---|---|---|---|
| A1 | US1.3 Baseline access enforcement | 1 | Dylan (buddy: Ivy) |
| A2 | US9.0 Seed sample venue data | 2 | Ethan |
| A3 | US9.2 View venue catalogue | 2 | Dylan |
| A4 | US9.3 Basic venue search/filter | 2 | Dylan |
| A5 | US9.4 Set venue setup and turnaround time | 3 | Ivy |
| A6 | US14.1 Request one or more venue bookings for an event | 3 | Dylan |
| A7 | US18.1 Venue suitability check per booking | 3 | Dylan |
| A8 | US14.2 Cancel one venue booking | 3 | Dylan |
| A9 | US16.1 Venue Staff approve or reject a booking request | 3 | Lincoln |
| A10 | US15.1 Conflict check includes setup and turnaround time | 3 | Ivy |
| A11 | US15.2 Flag bookings that clash after a setup/turnaround change | 3 | Ivy |
| A12 | US10.2 Coordinator notifications | 3 | Lincoln |

### A1 · US1.3: Baseline access enforcement

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US1.3** | SPMG3T7-24 | Dylan (buddy: Ivy) | **Ariel** | 10 min |

> **User story:** As a user, I want the system to block me from actions or pages outside my role's permissions, so that I can't accidentally or deliberately access things I'm not authorised for.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Any attempt to access an out-of-role action or page is blocked | 1–7 |
| **AC2** | A clear message explains the request was denied (not a silent failure or generic error) | 2, 4, 6, 7 |

**Setup:** none

**Steps**

1. Sign in as `organiser@connectsphere.com`.
   → Top nav doesn't show **Venues**, **Booking Requests**, **Unassigned Queue** or **Safety Review**.
2. Type `http://localhost:5173/#/venues` in the address bar.
   → Page says **This page is not open to your role** and names your role, with a **Go to my dashboard** button. Not a blank page, not a generic error. 📸
3. Click **Go to my dashboard**.
   → Back on **Events**.
4. Type `http://localhost:5173/#/unassigned-queue`.
   → Same "not open to your role" page.
5. Sign out. Sign in as `venuestaff@connectsphere.com`.
   → Nav shows **Venues**, **Add venue**, **Booking Requests**, **Booking Conflicts**. No **Create** link.
6. Type `http://localhost:5173/#/events/new`.
   → "not open to your role" page. 📸
7. Sign out. Sign in as `attendee@connectsphere.com`. Type `http://localhost:5173/#/venues`.
   → "not open to your role" page.

**Pass/Fail:** ☐

---

### A2 · US9.0: Seed sample venue data

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.0** | SPMG3T7-48 | Ethan | **Ariel** | 5 min |

> **User story:** As the development team, I want a handful of sample venue records created early in the sprint, so that US9.2 (view catalogue) and US9.3 (search/filter) have real data to test and demo against instead of an empty table.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | At least 5-10 venues created via US9.1a's create functionality, with varied capacity, location, and accessibility attributes so US9.3's filters have something meaningful to test. | 1–2 |
| **AC2** | Can be done manually or with a small seed script — team's choice. | Note |
| **AC3** | Should be done early in the sprint (right after US9.1a is working) so US9.2/US9.3 aren't blocked waiting for data. | Note |

**Setup:** none

**Steps**

1. Sign in as `coordinator@connectsphere.com` → **Venues**.
   → 22 venues, including these 6: Great Hall (500, Main Campus Building A), Rosewood Auditorium (280), Innovation Studio (120), Harbour View Terrace (150), Seminar Room 4 (60, Library Level 1), Bertha Room (40, Library Level 3). 📸
2. Check they vary:
   → Capacities 20–800. Many locations (Main Campus, Library, Business School, Sports Centre, partner venues). Accessibility differs (e.g. hearing loop at Great Hall and Seminar Room 4; Bertha Room has none).

**Pass/Fail:** ☐

---

### A3 · US9.2: View venue catalogue

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.2** | SPMG3T7-42 | Dylan | **Ariel** | 5 min |

> **User story:** As an Event Coordinator, I want to view the list of ConnectSphere venues and their details, so that I can start identifying suitable options for an event.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinators can list and open any venue record, read-only. | 1–3 |
| **AC2** | No search/filter yet — that's US9.3. | Note |

**Setup:** none

**Steps**

1. Sign in as `coordinator@connectsphere.com` → **Venues**.
   → List of venues with name, location and capacity. 📸
2. Open **Great Hall**.
   → Shows location, capacity 500, facilities, accessibility features, supported layouts, operating hours `Mon-Sat 08:00-22:00`, setup and turnaround time.
3. Check for edit controls.
   → No **Edit venue**, **Delete venue** or **Add venue**. 📸

**Pass/Fail:** ☐

---

### A4 · US9.3: Basic venue search/filter

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.3** | SPMG3T7-43 | Dylan | **Ariel** | 12 min |

> **User story:** As an Event Coordinator, I want to filter the venue catalogue by capacity, location, and accessibility, so that I can narrow down options faster than scrolling the full list.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Filters combine with AND logic. | 5 |
| **AC2** | Returns only venues meeting all applied criteria. | 2–7 |
| **AC3** | Builds on US9.1/US9.2 — no new table, just query params. | Code (no UI test) |

**Setup:** none (seeded venues)

**Steps**

1. As Priya → **Venues** → find **Narrow the catalogue**.
2. **Minimum capacity** `100` → **Apply filters**.
   → 11 seeded venues: Great Hall, Rosewood Auditorium, Innovation Studio, Harbour View Terrace, Lecture Theatre 3, Multipurpose Hall, Black Box Theatre, Courtyard Lawn, Marina Grand Ballroom, Orchard Conference Hall, Sentosa Terrace Garden (plus any test venues ≥100). **Not** Seminar Room 4 (60) or Bertha Room (40). 📸
3. **Clear**. **Location** `Library` → **Apply filters**.
   → Seminar Room 4 and Bertha Room only (plus any test venues with Library in the location).
4. **Clear**. **Accessibility** `Hearing loop` → **Apply filters**.
   → Great Hall, Rosewood Auditorium, Seminar Room 4, Lecture Theatre 3, Marina Grand Ballroom, Orchard Conference Hall. **Not** Bertha Room (no accessibility recorded).
5. **Clear**. Minimum capacity `50` **and** Location `Library` → **Apply filters**.
   → **Seminar Room 4 only** (AND logic: Bertha Room fails capacity). 📸
6. Location `Nowhere` → **Apply filters**.
   → "Nothing matches those filters".
7. **Clear filters**.
   → All venues back.

**Pass/Fail:** ☐

---

### A5 · US9.4: Set venue setup and turnaround time

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US9.4** | SPMG3T7-54 | Ivy | **Ariel** | 10 min |

> **User story:** As a Venue Staff member, I want to set a setup time and turnaround time for each venue, so that bookings leave enough time to prepare and reset the room.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Two fields per venue: setup time and turnaround time, in minutes, whole number ≥ 0, default 0. | 1–4 |
| **AC2** | Settable on create and edit, Venue Staff only. | 4–5, 7 |
| **AC3** | Shown on the venue detail view for Coordinators (US9.2). | 6 |
| **AC4** | Changing either value kicks off the re-check in US15.2. | Tested in US15.2 |

**Setup:** none

**Steps**

1. Venue Staff → **Add venue**: Name `T9.4 Room`, Location `QA Block`, Capacity `40`. Leave Setup and Turnaround **empty** → **Add venue**.
   → Saved. Opening it shows Setup **0** min, Turnaround **0** min (the default).
2. **Edit venue** → Setup time `-5` → **Save changes**.
   → Error: must be a whole number ≥ 0.
3. Setup time `7.5`.
   → Same error.
4. Setup time `45`, Turnaround time `30` → **Save changes**.
   → Saved. 📸
5. Make another venue with Setup `15` and Turnaround `10` filled in on the **Add venue** form.
   → Saved with those values (settable when creating).
6. Sign in as Priya → open `T9.4 Room`.
   → Shows setup 45 min and turnaround 30 min. 📸
7. As Priya, try `#/venues/<id>/edit`.
   → Refused.

**Pass/Fail:** ☐

---

### A6 · US14.1: Request one or more venue bookings for an event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US14.1** | SPMG3T7-55 | Dylan | **Ariel** | 20 min |

> **User story:** As an Event Coordinator, I want to request one or more venue bookings for a single event, so that bigger events can use several spaces at once (e.g. main hall plus breakout rooms).

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Each venue booking is its own record linked to the event (venue, start, end, status). One event can have many. | 4–5, 7 |
| **AC2** | Schema: new venue_bookings table. If US6.2's schema has a single venue column on events, migrate it. | Schema (no UI test) |
| **AC3** | Each booking is checked on its own for suitability and availability/conflicts (US15.1). One venue failing doesn't block the others. | 3, 5–6 |
| **AC4** | All bookings for the event show together on the event detail view. | 7 |
| **AC5** | New booking starts as Requested, waiting for Venue Staff approval (Venue Booking Approval epic). | 4–5 |
| **AC6** | Only the assigned Coordinator can request (US8.6). | 8 |

**Setup:** R0 `T14.1 Hall` (capacity 300), R3 `T14.1 Booking event` on **Tue 8 Dec 2026 09:00–18:00**, attendance 100

**Steps**

1. Run R0 (`T14.1 Hall`) and R3 (`T14.1 Booking event`).
2. As Priya, open the event → **Request a venue**.
3. Venue `T14.1 Hall`, Starts `8 Dec 2026 10:00`, Ends `8 Dec 2026 16:00`, Headcount `100`, Layout `Theatre`, Facilities `Projector, PA system`, Accessibility `Wheelchair access`.
   → **Suitable**. 📸
4. **Request venue**.
   → Booking listed as **Requested**. Event status **Approved → Planning** (first booking).
5. **Request a venue** again: Venue **Seminar Room 4**, `8 Dec 2026 13:00`–`15:00`, Headcount `30`, Layout `Classroom`, Facilities `Video conferencing`, Accessibility **empty**. If the form pre-fills layout, facilities or accessibility from the event, clear them first. Seminar Room 4 has no projector or wheelchair entry, so the pre-filled values would fail.
   → **Suitable** → **Request venue** → second booking **Requested**.
6. Try a third: **Bertha Room**, `10:00`–`11:00`, Headcount `60`.
   → **Not suitable** (capacity 40), so it can't be requested. The two existing bookings are **unchanged** (one failing doesn't block the others).
7. Look at the venue bookings section.
   → Both bookings (`T14.1 Hall`, Seminar Room 4) listed together, each with venue, start, end and status. Event still **Planning**. 📸
8. Sign in as Sam Chen → `#/events/<T14.1 ID>`.
   → Refused. Can't request venues on Priya's event.

**Keep:** `T14.1 Booking event` and both bookings, for US14.2 and US16.1.

**Pass/Fail:** ☐

---

### A7 · US18.1: Venue suitability check per booking

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US18.1** | SPMG3T7-61 | Dylan | **Ariel** | 15 min |

> **User story:** As an Event Coordinator, I want the system to tell me whether a venue is suitable before I request it, so that I don't book a room that's too small or missing what the event needs.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Each venue booking has its own expected headcount, defaulting to the event's expected attendance. This is so breakout rooms in a multi-venue event (Week 7 #3) are not checked against the whole event's attendance. | 3 |
| **AC2** | When the Coordinator picks a venue for a booking (US14.1), the system shows Suitable or Not suitable with the reasons. | 4–9 |
| **AC3** | Not suitable if any of these is true: headcount is more than the venue capacity; the required layout is not one the venue supports; a required facility or accessibility need is missing; the booking time is outside the venue's operating hours. | 5–8 |
| **AC4** | A not suitable venue can't be requested. | 5 |
| **AC5** | Test cases: headcount = capacity → Suitable; headcount = capacity + 1 → Not suitable. | 4–5 |

**Setup:** venue `T18.1 Room` (see step 1), R3 `T18.1 Fit event` on **Wed 9 Dec 2026 08:00–20:00**, attendance 120

**Steps**

1. As Venue Staff, **Add venue**: Name `T18.1 Room`, Location `QA Block`, Capacity `50`, Facilities `Projector`, Accessibility features `Wheelchair access`, Supported layouts `Theatre`, Operating hours `Mon-Fri 09:00-18:00`.
2. Run R3 for `T18.1 Fit event`.
3. As Priya, open the event → **Request a venue** → pick `T18.1 Room`.
   → **Headcount** is pre-filled with **120** (the event's attendance).
4. Headcount `50`, Starts `9 Dec 2026 10:00`, Ends `12:00`, Layout `Theatre`, Facilities `Projector`, Accessibility `Wheelchair access`.
   → **Suitable** (headcount = capacity). 📸
5. Headcount `51`.
   → **Not suitable**. The reason says capacity. **Request venue** is disabled or refused. 📸
6. Headcount `50`. Layout `Banquet`.
   → **Not suitable**: layout not supported.
7. Layout `Theatre`. Facilities `Projector, Stage`.
   → **Not suitable**: Stage is missing. Change Accessibility to `Hearing loop`.
   → Not suitable: accessibility need missing.
8. Facilities `Projector`, Accessibility `Wheelchair access`. Time `17:00`–`19:00`.
   → **Not suitable**: outside operating hours (closes 18:00).
9. Set everything wrong at once (headcount 51, layout Banquet, time 17:00–19:00).
   → **Every** reason is listed, not just the first. 📸
10. Put it back to valid (step 4 values) → **Request venue**.
    → **Requested**.

**Pass/Fail:** ☐

---

### A8 · US14.2: Cancel one venue booking

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US14.2** | SPMG3T7-58 | Dylan | **Ariel** | 10 min |

> **User story:** As an Event Coordinator, I want to cancel one venue booking on an event without touching the others, so that I can change one room without redoing the whole plan.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinator can cancel a single booking: status → Cancelled, reason required, who/when logged. | 1–4 |
| **AC2** | Other venue bookings on the same event are unchanged. | 5 |
| **AC3** | Event status is unchanged. | 5 |
| **AC4** | Cancelled booking frees the venue for that slot (no longer counted in US15.1). | 6 |

**Setup:** `T14.1 Booking event` with 2 Requested bookings

**Steps**

1. As Priya, open `T14.1 Booking event`. On the **Seminar Room 4** booking click **Cancel**.
   → Reason box with **Cancel booking** / **Keep booking**.
2. Leave the reason empty → **Cancel booking**.
   → Refused: reason required.
3. Reason `Found a better breakout room` → **Cancel booking**.
   → Booking **Cancelled**. 📸
4. Check the cancelled booking.
   → Shows the reason, **Priya**, and the date/time. It stays in the list (not deleted).
5. Check the rest.
   → `T14.1 Hall` booking still **Requested**. Event still **Planning**. 📸
6. Request **Seminar Room 4** again for the same slot (`8 Dec 2026 13:00–15:00`).
   → Allowed (the cancelled booking no longer holds the slot).

**Pass/Fail:** ☐

---

### A9 · US16.1: Venue Staff approve or reject a booking request

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US16.1** | SPMG3T7-62 | Lincoln | **Ariel** | 20 min |

> **User story:** As a Venue Staff member, I want to approve or reject venue booking requests, so that only bookings we can actually support get confirmed and the Coordinator knows where they stand.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Venue Staff see all Requested bookings, oldest first, showing event name, venue, booking time, the full occupied window including setup/turnaround (US15.1), headcount and layout. | 1–2 |
| **AC2** | Approve → booking status Confirmed. The conflict check (US15.1) runs again at approval. If the booking now clashes, approval is blocked and the clash is shown, so two requests for the same slot can't both be approved. | 3–4, 9 |
| **AC3** | Reject → reason required; Venue Staff can optionally suggest an alternative venue or time (free text). Booking status Rejected and the slot is freed. | 5–7 |
| **AC4** | Approving or rejecting one booking doesn't change the event's other bookings. | 4, 7 |
| **AC5** | The assigned Coordinator is notified of the decision and reason (US10.2). | 8 |
| **AC6** | Venue Staff only. Decision logged with who/when. | 4, 10 |

**Setup:** `T14.1 Booking event` (T14.1 Hall booking and the re-requested Seminar Room 4 booking)

**Steps**

1. Sign in as `venuestaff@connectsphere.com` → **Booking Requests**.
   → Requested bookings listed **oldest first**.
2. Find the `T14.1 Hall` booking.
   → Shows event name, venue, booking time, **Occupies the venue** (full window with setup/turnaround), headcount and layout. 📸
3. Click **Approve**.
   → Leaves the list. Booking **Confirmed**.
4. As Priya, open `T14.1 Booking event`.
   → `T14.1 Hall` **Confirmed** with who (Sam) and when. Seminar Room 4 still **Requested**.
5. As Venue Staff, Seminar Room 4 booking → **Reject** → leave reason empty → **Reject booking**.
   → Refused: reason required.
6. Reason `Room under maintenance that afternoon`. **Suggest another venue or time (optional)**: `Try Innovation Studio, same time` → **Reject booking**.
   → **Rejected**. 📸
7. As Priya, open the event.
   → Seminar Room 4 **Rejected** with the reason, the suggestion, who and when. `T14.1 Hall` still **Confirmed**. 📸
8. Priya → **Notifications**.
   → One notice for the approval and one for the rejection (with the reason).
9. Approval re-check: the request-time check (US15.1) already stops two overlapping requests, so this can't be set up in the UI. Run
   ```bash
   cd backend && pytest tests/test_booking_decisions.py -q
   ```
   → All pass. 📸 output.
10. Sign in as Priya. Type `#/booking-requests`.
    → "not open to your role".

**Pass/Fail:** ☐

---

### A10 · US15.1: Conflict check includes setup and turnaround time

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US15.1** | SPMG3T7-56 | Ivy | **Ariel** | 20 min |

> **User story:** As an Event Coordinator, I want availability checked against the full time a venue is occupied, including setup and turnaround, so that I don't book a room that's still being prepared or reset.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Effective occupied window = (start − venue setup time) to (end + venue turnaround time). | 2 |
| **AC2** | Test case from customer: event 10:00–12:00, setup 30 min, turnaround 45 min → occupies 9:30–12:45. | 2 |
| **AC3** | Request is blocked if its window overlaps another active booking's window at the same venue. Held, Requested and Confirmed count. Expired, Cancelled and Replaced don't. | 3, 5–6 |
| **AC4** | Also blocked if it overlaps a venue unavailability period (US12.1). | 7 |
| **AC5** | Blocked request says which booking or period it clashes with. | 3, 6, 7 |
| **AC6** | Windows that only touch (one ends 12:45, next starts 12:45) are allowed. | 4 |

**Setup:** R0 `T15.1 Hall` with **Setup 30**, **Turnaround 45**; R3 `T15.1 Clash event` from **Thu 10 Dec 2026 08:00 to Fri 11 Dec 2026 20:00** (two days, so step 7 has room)

**Steps**

Time maths for this test (write it in your evidence):

| Booking | Booked time | Occupies (−30 / +45) |
|---|---|---|
| A | 10:00–12:00 | **09:30–12:45** (the customer's test case) |
| B | 12:30–13:30 | 12:00–14:15 → overlaps A → **blocked** |
| C | 13:15–14:00 | 12:45–14:45 → only **touches** A → **allowed** |
| Hold H | 16:00–17:00 | 15:30–17:45 |
| D | 18:30–19:00 | 18:00–19:45 → overlaps H → **blocked** |

1. Run R0 and R3 as above.
2. As Priya → **Request a venue**: `T15.1 Hall`, `10 Dec 2026 10:00`–`12:00`, headcount 50.
   → Before you submit, the form says **"Available: the venue would be occupied 10 Dec 2026, 09:30–12:45, setup and turnaround included."** (date format may differ). 📸 Then **Request venue** → booking A **Requested**.
3. Request `12:30`–`13:30`.
   → **Blocked** (Not available). The message names booking A / its time. Can't be requested. 📸
4. Request `13:15`–`14:00`.
   → **Allowed** (windows only touch at 12:45). Booking C **Requested**. 📸
5. As Venue Staff, open `T15.1 Hall` → **Place a hold**: Event `T15.1 Clash event`, Starts `10 Dec 2026 16:00`, Ends `17:00`, Hold expires `9 Dec 2026 12:00` → **Place hold**.
   → Hold **Held**.
6. As Priya, request `18:30`–`19:00`.
   → **Blocked**: clashes with the hold (Held counts as taken).
7. As Venue Staff, mark `T15.1 Hall` unavailable **11 Dec 2026 – 11 Dec 2026**, reason Maintenance. Then as Priya, request `11 Dec 2026 10:00`–`11:00`.
   → **Blocked**: the message names the unavailability period. 📸

**Pass/Fail:** ☐

---

### A11 · US15.2: Flag bookings that clash after a setup/turnaround change

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US15.2** | SPMG3T7-57 | Ivy | **Ariel** | 20 min |

> **User story:** As the system, I want existing bookings that clash under new setup/turnaround times to be flagged, so that clashes get sorted out instead of bookings being silently removed.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | When a venue's setup or turnaround time changes, all its future active bookings are re-checked with US15.1's rule. | 4 |
| **AC2** | Newly clashing bookings are marked 'Conflict – review needed'. Never deleted or cancelled automatically. | 4–5 |
| **AC3** | Venue Staff see a list of flagged bookings; the assigned Coordinator is notified (US10.2). | 6–7 |
| **AC4** | Flag clears once the clash is resolved (booking moved, cancelled or replaced). | 8 |

**Setup:** R0 `T15.2 Hall` (setup 0, turnaround 0); R3 `T15.2 Event` on **Fri 11 Dec 2026 08:00–20:00**

**Steps**

| | Before (0/0) | After turnaround → 30 |
|---|---|---|
| A 10:00–12:00 | 10:00–12:00 | 10:00–**12:30** |
| B 12:00–14:00 | 12:00–14:00 (touches A, allowed) | 12:00–**14:30** → **overlaps A** |

1. Run R0 and R3.
2. As Priya, request A `11 Dec 2026 10:00–12:00` and B `12:00–14:00` at `T15.2 Hall`.
   → Both allowed. Both **Requested**.
3. As Venue Staff → **Booking Requests** → **Approve** both.
   → Both **Confirmed**.
4. As Venue Staff, `T15.2 Hall` → **Edit venue** → Turnaround time `30`.
   → Before saving, the form previews the clash (**New with this change**). Click **Save changes**. 📸
   → Saved. A **Review booking conflicts** link appears.
5. As Priya, open `T15.2 Event`.
   → The clashing booking(s) show **Conflict – review needed**. Status is still **Confirmed**: not cancelled, not deleted. 📸
6. As Venue Staff → **Booking Conflicts**.
   → The flagged booking(s) listed with venue, booking, coordinator and occupied window. 📸
7. Priya → **Notifications**.
   → Notice about the flagged booking at `T15.2 Hall`.
8. As Priya, **Cancel** booking B (reason `Resolve clash`).
   → The flag on A clears. **Booking Conflicts** no longer lists it.

**Pass/Fail:** ☐

---

### A12 · US10.2: Coordinator notifications

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US10.2** | SPMG3T7-53 | Lincoln | **Ariel** | 15 min |

> **User story:** As an Event Coordinator, I want to be notified about events that need my attention, so that I don't miss assignments or booking problems.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | A notification is created for the relevant Coordinator when:<br>• an event is assigned or reassigned to/away from them (US8.3, US8.4)<br>• a tentative hold is about to expire or has expired (US14.4)<br>• a booking is hit by venue unavailability or a setup/turnaround change (US12.2, US15.2)<br>• the Safety Officer requests changes (US17.2) | Assigned/reassigned 1–3 · booking hit 4–5 · hold expiry and Safety Officer 6 |
| **AC2** | Same unread/read list and toggle as US10.1, reusing the notifications table with a recipient field. | 7 |
| **AC3** | In-app only, no email/push. | 8 |

**Setup:** do this after your US15.2 test

**Steps**

1. Run R1 for `T10.2 Notify`. As Jordan, assign it to **Priya**.
2. Sign in as Priya → **Notifications**.
   → "assigned to you" notice for `T10.2 Notify`. 📸
3. As Jordan, open `T10.2 Notify` → **Reassign Coordinator** → **Sam Chen**.
   → Priya gets a "reassigned away" notice. Sam Chen gets an "assigned to you" notice. 📸 both.
4. As Priya, check for the notice from your US15.2 test (turnaround change on `T15.2 Hall`).
   → Notice that a booking now clashes / needs review.
5. Run R4 for `T10.2 Unavail` using a new R0 venue `T10.2 Hall` (booking on 14 Dec 2026). As Venue Staff, mark `T10.2 Hall` unavailable 14–14 Dec 2026, reason **Maintenance**.
   → Priya gets a notice naming the venue, dates and reason. 📸
6. Hold expiry and Safety Officer notices are covered with screenshots in **US14.4** (Ivy) and **US17.2** (Lincoln). Check those screenshots exist and attach them to this test's evidence.
7. On one notice click **Mark as read**, then **Mark as unread**.
   → Same behaviour as US10.1. Badge count updates.
8. No email or push notification was received.

**Pass/Fail:** ☐

---

---

## 4. Integration tests (all-hands, after the story tests)

Your roles: Integration 1: Coordinator (Priya) · Integration 2: Coordinator (Priya)

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
| A1 | US1.3 Baseline access enforcement | ☐ | |
| A2 | US9.0 Seed sample venue data | ☐ | |
| A3 | US9.2 View venue catalogue | ☐ | |
| A4 | US9.3 Basic venue search/filter | ☐ | |
| A5 | US9.4 Set venue setup and turnaround time | ☐ | |
| A6 | US14.1 Request one or more venue bookings for an event | ☐ | |
| A7 | US18.1 Venue suitability check per booking | ☐ | |
| A8 | US14.2 Cancel one venue booking | ☐ | |
| A9 | US16.1 Venue Staff approve or reject a booking request | ☐ | |
| A10 | US15.1 Conflict check includes setup and turnaround time | ☐ | |
| A11 | US15.2 Flag bookings that clash after a setup/turnaround change | ☐ | |
| A12 | US10.2 Coordinator notifications | ☐ | |

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
