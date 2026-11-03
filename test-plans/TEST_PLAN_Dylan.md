# Test Plan: Dylan (ConnectSphere, SPMG3T7)

**Tester:** Dylan · **Workload:** 12 tests (~159 min) · **Integration roles:** Integration 1: **lead** · Integration 3: Coordinator

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

## 3. Your tests: 12 tests (~159 min)

| # | User story | Sprint | Implemented by |
|---|---|---|---|
| D1 | US1.1 Login | 1 | Lincoln (buddy: Ariel) |
| D2 | US1.2 Logout | 1 | Ivy (buddy: Ethan) |
| D3 | US5.1 Coordinator views event information | 1 | Lincoln (buddy: Ivy) |
| D4 | US5.2 Coordinator edits event information | 1 | Ethan (buddy: Lincoln) |
| D5 | US12.1 Venue Staff mark venue unavailability | 2 | Ivy |
| D6 | US12.2 Flag bookings hit by venue unavailability | 4 | Ethan |
| D7 | US14.5 Request a replacement venue | 4 | Ethan |
| D8 | US9.5 Block deleting a venue that has future bookings | 4 | Lincoln |
| D9 | US12.3 Venue availability view | 4 | Lincoln |
| D10 | US20.1 Attendee registers for an event | 4 | Lincoln |
| D11 | US20.2 Attendee views registration and withdraws | 4 | Lincoln |
| D12 | US20.3 Organiser and Coordinator view registrations | 4 | Lincoln |

### D1 · US1.1: Login

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US1.1** | SPMG3T7-22 | Lincoln (buddy: Ariel) | **Dylan** | 10 min |

> **User story:** As a user (any role), I want to log in with my credentials so that I can access the system appropriate to my role.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Valid credentials grant access and redirect to a role-appropriate view | 1–6 |
| **AC2** | Invalid credentials show a clear error and do not grant access | 7–9 |
| **AC3** | Session remains active for the duration of normal use and expires after a defined period of inactivity (e.g. 30 minutes) | 10–14 |

**Setup:** none

**Steps**

1. Open `http://localhost:5173` → **Sign in**.
2. Email `organiser@connectsphere.com`, password `password` → **Sign in**.
   → Lands on **Events**. Top right shows **Dylan** and **Event Organiser**. 📸
3. **Sign out**. Sign in as `venuestaff@connectsphere.com`.
   → Lands on **Venues**.
4. **Sign out**. Sign in as `coordinatorlead@connectsphere.com`.
   → Lands on **Unassigned Queue**.
5. **Sign out**. Sign in as `attendee@connectsphere.com`.
   → Lands on **Upcoming Events**.
6. **Sign out**.
7. Email `organiser@connectsphere.com`, password `wrongpassword` → **Sign in**.
   → A clear error message. Still on the sign-in page. 📸
8. Email `nobody@connectsphere.com`, password `password` → **Sign in**.
   → Same error. Not signed in.
9. Email `ORGANISER@connectsphere.com` (capitals), correct password.
   → Signs in (email isn't case-sensitive). Sign out.
10. Stop the backend (Ctrl+C in terminal 1). Restart it with a 1-minute idle limit:
    ```bash
    SESSION_IDLE_MINUTES=1 uvicorn app.main:app --reload --port 8000
    ```
11. Sign in as Organiser. Don't touch the mouse or keyboard for **70 seconds**.
    → You are signed out and sent back to **Sign in**. 📸
12. Sign in again and keep clicking around for 2 minutes.
    → Still signed in (using the app keeps the session alive).
13. Stop the backend and restart it normally (without `SESSION_IDLE_MINUTES`).
14. Confirm the default is 30 min: `grep -n DEFAULT_SESSION_IDLE_MINUTES backend/app/config.py`
    → `DEFAULT_SESSION_IDLE_MINUTES = 30`

**Pass/Fail:** ☐

---

### D2 · US1.2: Logout

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US1.2** | SPMG3T7-23 | Ivy (buddy: Ethan) | **Dylan** | 5 min |

> **User story:** As a user, I want to log out of the system so that my session ends securely.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Logout ends the session immediately | 1–3 |
| **AC2** | Subsequent requests require re-authentication | 4–6 |

**Setup:** none

**Steps**

1. Sign in as `organiser@connectsphere.com`. Go to **Events** and copy the URL.
2. Click **Sign out** (top right). 📸
   → Back on **Sign in**. No name in the header.
3. Press the browser **Back** button.
   → Doesn't show the events list. You're asked to sign in.
4. Paste the Events URL from step 1 into the address bar.
   → Sent to **Sign in**.
5. Paste `http://localhost:5173/#/venues`.
   → Sent to **Sign in**.
6. Sign in again.
   → Works normally (you can sign in again after logging out).

**Pass/Fail:** ☐

---

### D3 · US5.1: Coordinator views event information

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US5.1** | SPMG3T7-33 | Lincoln (buddy: Ivy) | **Dylan** | 8 min |

> **User story:** As an Event Coordinator, I want to view an event's full current information, so that I can assess its status before making changes.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinator can open any submitted event (Sprint 1: any Coordinator, no formal assignment yet — that's a Sprint 2 feature) and see all captured fields, read-only. | 2–4 |

**Setup:** R2 (title `T5.1 View event`, assigned to Priya)

**Steps**

1. Run R2 for `T5.1 View event`.
2. Sign in as `coordinator@connectsphere.com` → **Events** → open `T5.1 View event`.
   → Every field the Organiser entered is shown: Title, Description, Purpose, Starts, Ends, Expected attendance, Venue requirements, Preferred layout, Accessibility needs, Equipment needs, Registration needs. 📸
3. Compare each value with what you typed in R1.
   → All match.
4. Try typing in a field without clicking any edit control.
   → It's read-only.

**Pass/Fail:** ☐

---

### D4 · US5.2: Coordinator edits event information

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US5.2** | SPMG3T7-34 | Ethan (buddy: Lincoln) | **Dylan** | 12 min |

> **User story:** As an Event Coordinator, I want to update relevant event information during planning, so that arrangements stay accurate as the event evolves.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinator can edit general event fields (name, purpose, date/time, attendance, venue/accessibility/equipment/registration requirements) — per customer clarification, Coordinator has general edit rights; Venue/Technical Support Staff edit only their own domain's prep info (out of scope until Sprint 2/3). | 1–4 |
| **AC2** | Edits to date, time, expected attendance, venue requirements, or equipment requirements are logged as important changes; other edits logged as routine. | 5 |
| **AC3** | Test with any Coordinator account — formal assignment is a Sprint 2 feature. | 6 |

**Setup:** uses `T5.1 View event`

**Steps**

1. As Priya, open `T5.1 View event`. As the assigned Coordinator, the fields can be edited straight away, and the button at the bottom says **Save changes**.
2. Change Expected attendance `50` → `75`. Click **Save changes**.
   → Saved. Shows `75`.
3. Change Description to `Edited by coordinator`. Click **Save changes**.
4. Refresh.
   → Both changes are still there. 📸
5. Look at **Change and clarification history**.
   → The attendance change is marked **Important**. The description change is **routine** (not marked Important). Each has who and when. 📸
6. Sign in as `coordinator2@connectsphere.com`. Type `http://localhost:5173/#/events/<T5.1 ID>`.
   → Refused. Sam Chen can't edit it.

**Pass/Fail:** ☐

---

### D5 · US12.1: Venue Staff mark venue unavailability

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US12.1** | SPMG3T7-46 | Ivy | **Dylan** | 10 min |

> **User story:** As a Venue Staff member, I want to mark date ranges when a venue is unavailable (maintenance, closure), so that Coordinators don't consider it during planning.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Venue Staff can record an unavailable date range for a venue by specifying a start date and end date. | 2, 4 |
| **AC2** | The system validates that the end date is not earlier than the start date. | 3 |
| **AC3** | The system stores the unavailable date range for the selected venue. | 6 |
| **AC4** | Coordinators can view a venue’s unavailable date ranges when viewing the venue. | 7 |
| **AC5** | The system only records and displays blackout periods; booking-conflict checks are not required in this sprint because venue bookings are not implemented until Sprint 3 | Note |

**Setup:** R0 venue `T12.1 Hall`

**Steps**

1. Run R0 for `T12.1 Hall`.
2. As Venue Staff, open `T12.1 Hall` → **Mark dates unavailable**.
3. Start date `18 Dec 2026`, End date `15 Dec 2026`, Reason **Maintenance** → **Mark unavailable**.
   → Error: the end date can't be before the start date. 📸
4. End date `18 Dec 2026` → **Mark unavailable**.
   → "Marked unavailable: 15–18 Dec 2026." Listed as **Upcoming**.
5. Reason **Other** with **Custom reason** left empty.
   → Refused (Other needs free text, US12.2 rule).
6. Refresh.
   → The range is still listed (stored).
7. Sign in as Priya → **Venues** → open `T12.1 Hall`.
   → Sees 15–18 Dec 2026 listed as unavailable, with the reason. Can't add or remove ranges. 📸

**Pass/Fail:** ☐

---

### D6 · US12.2: Flag bookings hit by venue unavailability

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US12.2** | SPMG3T7-70 | Ethan | **Dylan** | 25 min |

> **User story:** As a Venue Staff member, I want bookings affected by a new unavailability period to be flagged and their Coordinators told, so that alternative arrangements can be made without the event being cancelled.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | When Venue Staff marks a venue unavailable (done in US12.1), they must pick a reason (maintenance, equipment failure, renovation, safety concern, or other, where “other” needs free text), and the reason is saved as a new column on US12.1’s db table. | 5–6 |
| **AC2** | Every active booking (Requested, Held or Confirmed) at that venue whose effective window (US15.1, including setup and turnaround) overlaps the period is set to ‘Needs replacement’. | 7 |
| **AC3** | Expired, Cancelled, Rejected and Replaced bookings, and bookings at other venues, are ignored. | 8 |
| **AC4** | The event, its status and its details are not changed or cancelled, and other bookings on the same event are untouched. | 8 |
| **AC5** | Each affected event’s assigned Coordinator is notified once per event (US10.2) with the venue, dates and reason, even if several of its bookings are flagged. | 9 |
| **AC6** | The flagged booking shows on the event detail view with its label, reason and dates, and stays flagged until it is replaced (US14.5) or cancelled (US14.2). | 7 (stays flagged until replaced: US14.5 step 8) |
| **AC7** | After saving, Venue Staff see how many bookings were flagged (including 0). | 6, 10 |
| **AC8** | Test case: a venue is unavailable 10–12 Nov with a Confirmed booking on 11 Nov, a Cancelled booking on 11 Nov, and a Confirmed booking on 20 Nov, so only the first is flagged and its Coordinator is notified. | 2–9 |

**Setup:** R0 `T12.2 Hall` with **Setup 15, Turnaround 15**; R3 `T12.2 Event A` on **Wed 11 Nov 2026 08:00–20:00**; R3 `T12.2 Event B` on **Fri 20 Nov 2026 08:00–20:00**

**Steps**

For **all** bookings in this test, leave Layout, Facilities and Accessibility **empty**. US14.5 then has a simple replacement.

1. Run R0 and both R3s.
2. Event A, as Priya: request `T12.2 Hall` **11 Nov 10:00–12:00** → then **Cancel** it, reason `Test cancelled booking`.
   → Booking X **Cancelled**.
3. Event A: request `T12.2 Hall` **11 Nov 10:00–12:00** again (booking Y), and **11 Nov 14:00–15:00** (booking W).
   → Both **Requested**.
4. Event B: request `T12.2 Hall` **20 Nov 10:00–12:00** (booking Z). As Venue Staff → **Booking Requests** → **Approve** Y and Z (leave W as Requested).
   → Y and Z **Confirmed**. W **Requested**. Write down both events' statuses (should be Planning).
5. As Venue Staff, open `T12.2 Hall` → **Mark dates unavailable**: Start `10 Nov 2026`, End `12 Nov 2026`, Reason **Other**, Custom reason empty → **Mark unavailable**.
   → Refused: Other needs a description.
6. Reason **Equipment failure** → **Mark unavailable**.
   → "Marked unavailable: 10–12 Nov 2026. **2 bookings flagged as needing replacement.**" 📸
7. As Priya, open `T12.2 Event A`.
   → **Y (Confirmed)** and **W (Requested)** both show **Needs replacement**, with reason Equipment failure and dates 10–12 Nov. 📸
8. On the same page, check the rest.
   → Cancelled booking X is **not** flagged (still Cancelled). Event status is **unchanged** (Planning). Event details unchanged. Then open `T12.2 Event B`: Z (20 Nov) is still **Confirmed**, not flagged.
9. Priya → **Notifications**.
   → **One** notice for Event A (even though 2 bookings were flagged), naming `T12.2 Hall`, 10–12 Nov and Equipment failure. **No** notice for Event B. 📸
10. Zero-count check: as Venue Staff, mark `T12.2 Hall` unavailable **1 Dec 2026 – 2 Dec 2026**, reason Maintenance.
    → The message says **0 bookings flagged**. If no count is shown, mark this step ☒ and log a Low bug. 📸

**Keep:** Event A with Y and W flagged, for US14.5. Event B with Z, for US9.5 and US12.3.

**Pass/Fail:** ☐

---

### D7 · US14.5: Request a replacement venue

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US14.5** | SPMG3T7-71 | Ethan | **Dylan** | 20 min |

> **User story:** As an Event Coordinator, I want to search for and request a replacement venue for a booking that's been affected, so that my event can still go ahead.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | From a 'Needs replacement' booking, Coordinator can search venues (US9.3 filters), only showing venues free for the same time (US15.1). | 1–5 |
| **AC2** | Requesting a replacement creates a new booking request on the same event. Old booking is marked Replaced and kept for history. | 6–7, 9 |
| **AC3** | Other bookings on the event are untouched. | 8 |

**Setup:** `T12.2 Event A` from US12.2

**Steps**

1. As Priya, open `T12.2 Event A`. On booking **Y** (Needs replacement) click **Find replacement**.
   → **Find a replacement venue** opens, showing Y's date and time (11 Nov 10:00–12:00) and filter fields. 📸
2. Look at the results without filters.
   → `T12.2 Hall` is **not** listed. Only venues free on 11 Nov 10:00–12:00 are shown.
3. Minimum capacity `50`, Location `Library` → **Apply filters**.
   → **Seminar Room 4** (60, Library Level 1). Bertha Room isn't shown (capacity 40). 📸
4. **Clear filters**.
   → Full list of free venues again.
5. Pick **Seminar Room 4** (under **Choose a replacement venue**).
6. **Request replacement**.
   → Success. 📸
7. Check the bookings list.
   → Y (`T12.2 Hall`) is **Replaced**, still listed for history. A **new** booking at Seminar Room 4, **11 Nov 10:00–12:00**, same headcount, status **Requested**.
8. Check the rest.
   → W is still **Needs replacement** (untouched). Event status unchanged. 📸
9. As Venue Staff → **Booking Requests** → **Approve** the Seminar Room 4 booking.
   → **Confirmed**. Priya sees Replaced (Y) + Confirmed (Seminar Room 4).

**Pass/Fail:** ☐

---

### D8 · US9.5: Block deleting a venue that has future bookings

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US9.5** | SPMG3T7-68 | Lincoln | **Dylan** | 10 min |

> **User story:** As a Venue Staff member, I want the system to stop me deleting a venue that still has future bookings, so that events don't quietly lose their venue.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Delete is blocked if the venue has any future active booking. Message tells staff to mark it unavailable instead (US12.2). | 1–2 |
| **AC2** | Venues with no future bookings can still be deleted as in US9.1c. | 3–4 |
| **AC3** | This is the follow-up US9.1c flagged for when bookings exist. | Note |

**Setup:** `T12.2 Hall` (Z on 20 Nov is Confirmed); `T12.1 Hall` from US12.1 (no bookings)

**Steps**

1. As Venue Staff, open `T12.2 Hall` → **Delete venue** → **Yes, delete it**.
   → Blocked. Message: "`T12.2 Hall` has future bookings, so it cannot be deleted. Mark it unavailable instead…" 📸
2. Refresh.
   → Venue still there. Its bookings are unchanged.
3. Open `T12.1 Hall` (only an unavailability period, no bookings) → **Delete venue** → **Yes, delete it**.
   → Deleted. 📸
4. **Venues**.
   → `T12.1 Hall` gone. `T12.2 Hall` still there.

**Pass/Fail:** ☐

---

### D9 · US12.3: Venue availability view

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US12.3** | SPMG3T7-82 | Lincoln | **Dylan** | 15 min |

> **User story:** As an Event Coordinator or Venue Staff member, I want to see everything that is taking up a venue over a date range, so that I can tell at a glance when it can be requested.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | From a venue's page, pick a date range (default: next 14 days). | 2 |
| **AC2** | Shows a chronological list of Confirmed bookings, Requested bookings, tentative holds (with expiry time) and unavailability periods, each labelled by type. | 3–5, 7 |
| **AC3** | Booking entries show the full occupied window including setup and turnaround (US15.1). | 5 |
| **AC4** | Expired, Cancelled and Rejected entries are hidden. | 6 |
| **AC5** | Team decision: a list view is enough for Release 1; a calendar grid can come later. (Do list first, if not too difficult then do a calendar grid) | Note (list view built) |

**Setup:** `T12.2 Hall` (setup 15 / turnaround 15)

**Steps**

1. Setup extras on `T12.2 Hall`:
   - As Venue Staff, place a **hold** for `T12.2 Event B`, **20 Nov 14:00–15:00**, Hold expires `19 Nov 2026 17:00`.
   - As Priya, request **20 Nov 16:00–17:00** on Event B (stays **Requested**).
2. As Venue Staff, open `T12.2 Hall` → availability section.
   → **From** = today, **To** = today + 14 days (default). 📸
3. Set From `1 Nov 2026`, To `30 Nov 2026` → **Show**.
4. Read the list.
5. → In date/time order, each labelled by type:
     - **Unavailable** 10–12 Nov (Equipment failure)
     - **Confirmed** booking Z, 20 Nov, shows **09:45–12:15** (10:00–12:00 plus 15 min setup and 15 min turnaround)
     - **Hold** 20 Nov 13:45–15:15, with expiry 19 Nov 17:00
     - **Requested** 20 Nov 15:45–17:15 📸
6. Check what's hidden.
   → Cancelled booking X (11 Nov) is **not** listed.
7. Sign in as Priya → open `T12.2 Hall` → same range → **Show**.
   → Same list.

**Pass/Fail:** ☐

---

### D10 · US20.1: Attendee registers for an event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US20.1** | SPMG3T7-79 | Lincoln | **Dylan** | 20 min |

> **User story:** As an Attendee, I want to register for a confirmed event, so that I have a place at it.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | The assigned Coordinator can turn registration on for an event and set a registration capacity (whole number ≥ 1, defaults to expected attendance). | 2–3 |
| **AC2** | Attendees see Confirmed events with registration turned on: name, date/time, venue(s) and places left. Internal planning info (bookings, equipment, notes) is never shown to Attendees. | 4–6 |
| **AC3** | An Attendee registers with name and email (both required). Only one active registration per Attendee per event. | 7–9 |
| **AC4** | Once registrations reach capacity, registering is blocked with an 'Event is full' message. If two Attendees try for the last place at the same time, only one succeeds (enforced in the database). | 10–11 |
| **AC5** | The Coordinator and Organiser are notified when the event becomes full (US10.2). | 12 |

**Setup:** R4 `T20 Reg event` on **Thu 17 Dec 2026 18:00–21:00**, attendance `2`, at a new R0 venue `T20 Hall`

**Steps**

1. Run R0 and R4 (event is now **Planning** with a Confirmed booking).
2. As Priya, open the event → registration card → tick **Open registration to Attendees**.
   → **Capacity** is pre-filled with **2** (the attendance).
3. Capacity `0` → **Save registration**.
   → Refused (must be ≥ 1). Set Capacity `1` → **Save registration**.
   → Saved. Card says **Not visible to Attendees yet** (not Confirmed). 📸
4. Sign in as `attendee@connectsphere.com` → **Upcoming Events**.
   → `T20 Reg event` is **not** listed.
5. As Priya, **Send for safety check**. As Alex, **Approve safety check**.
   → Event **Confirmed**. Card says **Visible to Attendees**.
6. As Casey → **Upcoming Events**.
   → `T20 Reg event` is listed with name, date/time (When), venue (Where `T20 Hall`) and **Places** left **1**. No bookings, equipment or internal notes shown. 📸
7. **Register** → clear Name → **Confirm registration**.
   → Refused: name required. Same with Email empty.
8. Name `Casey Tan`, Email `attendee@connectsphere.com` → **Confirm registration**.
   → Registered. Places left **0**. 📸
9. As Casey, try to register again.
   → Not possible (shows Registered / no Register button).
10. Sign in as `attendee2@connectsphere.com` (Morgan) → **Register** on `T20 Reg event` → fill in → **Confirm registration**.
    → Blocked: **"Event is full."** 📸
11. Two-at-once check is DB-enforced, so run
    ```bash
    cd backend && pytest tests/test_registration_us20_1.py tests/test_registration_store.py -q
    ```
    → All pass. 📸
12. Priya and Organiser (Dylan) → **Notifications**.
    → Each has a notice that `T20 Reg event` is full. 📸

**Pass/Fail:** ☐

---

### D11 · US20.2: Attendee views registration and withdraws

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US20.2** | SPMG3T7-80 | Lincoln | **Dylan** | 12 min |

> **User story:** As an Attendee, I want to see my registrations and withdraw if I can't go, so that I always have the latest event details and my place can go to someone else.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | An Attendee sees their registrations with status (Registered or Withdrawn) and the event's current date, time and venue. | 1 |
| **AC2** | An Attendee can withdraw before the event starts. Avaiable places left goes up by 1. | 2–4, 8 |
| **AC3** | A withdrawn Attendee can register again if places are still available. | 5–7 |

**Setup:** US20.1 state (Casey registered, capacity 1, full)

**Steps**

1. As Casey → **My Registrations**.
   → `T20 Reg event` with status **Registered**, When 17 Dec 2026 18:00–21:00, Where `T20 Hall`. 📸
2. Click **Withdraw…**.
   → Confirmation with **Confirm withdrawal** / **Keep my place**.
3. **Confirm withdrawal**.
   → Status **Withdrawn**. Still listed (not removed). 📸
4. As Morgan → **Upcoming Events**.
   → Places left **1** (went up by 1). Morgan registers → success.
5. As Casey → **My Registrations** → **Register again**.
   → Blocked: "Event is full." (no places left)
6. As Morgan → **My Registrations** → **Withdraw…** → **Confirm withdrawal**.
7. As Casey → **Register again**.
   → Registered again. 📸
8. Withdrawing after the start time can't be done on a future event, so run `cd backend && pytest tests/test_registration_us20_2.py -q`.
   → All pass.

**Pass/Fail:** ☐

---

### D12 · US20.3: Organiser and Coordinator view registrations

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US20.3** | SPMG3T7-81 | Lincoln | **Dylan** | 12 min |

> **User story:** As an Event Organiser or Event Coordinator, I want to see who has registered for my event, so that I can plan for the actual numbers.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | The owning Organiser and the assigned Coordinator can see the registration list: name, email, registration time, status, and registered count vs capacity. | 1–2 |
| **AC2** | Other Organisers and non-assigned Coordinators are blocked (US3.1 / US8.6 rules). Attendees can't see other Attendees' registrations. | 3–5 |

**Setup:** US20.2 state

**Steps**

1. As Organiser (Dylan), open `T20 Reg event` → **People registered for this event**.
   → Rows for Casey (Registered) and Morgan (Withdrawn), each with **name, email, registration time, status**. Count vs capacity shown as **"1 of 1 registered"**. 📸
2. As Priya, open the same event.
   → Same list and count. 📸
3. As Sam Chen (not assigned), type `#/events/<T20 ID>`.
   → Refused. No registration list.
4. As Riley (`organiser2`), type `#/events/<T20 ID>`.
   → Refused.
5. As Casey → **My Registrations** and **Upcoming Events**.
   → Only Casey's own registration. No list of other people. 📸

**Pass/Fail:** ☐

---

---

## 4. Integration tests (all-hands, after the story tests)

Your roles: Integration 1: **lead** · Integration 3: Coordinator

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
| D1 | US1.1 Login | ☐ | |
| D2 | US1.2 Logout | ☐ | |
| D3 | US5.1 Coordinator views event information | ☐ | |
| D4 | US5.2 Coordinator edits event information | ☐ | |
| D5 | US12.1 Venue Staff mark venue unavailability | ☐ | |
| D6 | US12.2 Flag bookings hit by venue unavailability | ☐ | |
| D7 | US14.5 Request a replacement venue | ☐ | |
| D8 | US9.5 Block deleting a venue that has future bookings | ☐ | |
| D9 | US12.3 Venue availability view | ☐ | |
| D10 | US20.1 Attendee registers for an event | ☐ | |
| D11 | US20.2 Attendee views registration and withdraws | ☐ | |
| D12 | US20.3 Organiser and Coordinator view registrations | ☐ | |

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
