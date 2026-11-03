# MASTER TEST PLAN: ConnectSphere (SPMG3T7)

Cross-testing plan for all 58 Jira user stories (59 tests, because US2.1 is tested in Sprint 1 and again after it was reopened in Sprint 3). Tests are grouped **by tester**, in the order to run them. Every test shows its sprint, user story, who implemented it, who tests it, and the Jira acceptance criteria, with the steps that check each one.

**Rule:** nobody tests a story they implemented (or were the Sprint 1 buddy on).

## Who tests what

| Tester | Tests | Est. time | Also |
|---|---|---|---|
| **Ethan** | 11 + S0 | ~168 min | S0 one-time setup (do first) |
| **Dylan** | 12 | ~159 min | Lead Integration 1 |
| **Ivy** | 12 | ~153 min | Lead Integration 3 |
| **Lincoln** | 12 | ~160 min | Lead Integration 2 |
| **Ariel** | 12 | ~162 min |  |

Everyone also plays a role in the three integration tests at the end.

### Index by user story

| User story | Title | Sprint | Implemented by | Tested by | Test ID |
|---|---|---|---|---|---|
| US1.1 | Login | 1 | Lincoln (buddy: Ariel) | Dylan | D1 |
| US1.2 | Logout | 1 | Ivy (buddy: Ethan) | Dylan | D2 |
| US1.3 | Baseline access enforcement | 1 | Dylan (buddy: Ivy) | Ariel | A1 |
| US2.1 | Create and submit an event request | 1 | Ivy (buddy: Ariel) | Ethan | E1 |
| US2.2 | Save and resume a draft | 1 | Dylan (buddy: Lincoln) | Ethan | E2 |
| US3.1 | View my events | 1 | Ariel (buddy: Ivy) | Ethan | E3 |
| US4.1 | View event status | 1 | Ethan (buddy: Dylan) | Ivy | I3 |
| US4.2 | Status transitions | 1 | Ariel | Ivy | I4 |
| US5.1 | Coordinator views event information | 1 | Lincoln (buddy: Ivy) | Dylan | D3 |
| US5.2 | Coordinator edits event information | 1 | Ethan (buddy: Lincoln) | Dylan | D4 |
| US6.1 | Project setup, repo, and CI pipeline | 1 | Dylan (buddy: Ariel) | Ivy | I1 |
| US6.2 | Core database schema | 1 | Ethan (buddy: Lincoln) | Ivy | I2 |
| US4.3 | Status transitions: Submitted → Under Review → Approved/Rejected | 2 | Ariel | Ethan | E7 |
| US7.1 | Coordinator makes a review decision (approve/reject) | 2 | Ariel | Ethan | E6 |
| US7.3 | Coordinator requests clarification/amendment | 2 | Dylan | Ethan | E5 |
| US8.1 | Automatically assign a Coordinator on submission | 2 | Ethan | Lincoln | L2 |
| US9.0 | Seed sample venue data | 2 | Ethan | Ariel | A2 |
| US9.1a | Create a venue record | 2 | Ariel | Ivy | I5 |
| US9.1b | Update a venue record | 2 | Lincoln | Ivy | I6 |
| US9.1c | Delete a venue record | 2 | Dylan | Ivy | I7 |
| US9.2 | View venue catalogue | 2 | Dylan | Ariel | A3 |
| US9.3 | Basic venue search/filter | 2 | Dylan | Ariel | A4 |
| US10.1 | Receive and manage notifications | 2 | Lincoln | Ethan | E8 |
| US11.1 | Organiser submits a change request on a submitted event | 2 | Ivy | Ethan | E9 |
| US12.1 | Venue Staff mark venue unavailability | 2 | Ivy | Dylan | D5 |
| US1.4 | Add Coordinator Lead and Safety Officer roles | 3 | Ethan | Lincoln | L1 |
| US2.1 (reopened) | Create and submit an event request | 3 | Ivy | Ethan | E4 |
| US4.5 | Missing lifecycle transitions | 3 | Ariel | Ivy | I12 |
| US8.2 | Lead views the unassigned queue | 3 | Ethan | Lincoln | L3 |
| US8.3 | Lead assigns a Coordinator | 3 | Ethan | Lincoln | L4 |
| US8.6 | Coordinators only manage events assigned to them | 3 | Ethan | Lincoln | L5 |
| US9.4 | Set venue setup and turnaround time | 3 | Ivy | Ariel | A5 |
| US10.2 | Coordinator notifications | 3 | Lincoln | Ariel | A12 |
| US14.1 | Request one or more venue bookings for an event | 3 | Dylan | Ariel | A6 |
| US14.2 | Cancel one venue booking | 3 | Dylan | Ariel | A8 |
| US14.3 | Place a tentative hold with an expiry | 3 | Lincoln | Ivy | I8 |
| US15.1 | Conflict check includes setup and turnaround time | 3 | Ivy | Ariel | A10 |
| US15.2 | Flag bookings that clash after a setup/turnaround change | 3 | Ivy | Ariel | A11 |
| US16.1 | Venue Staff approve or reject a booking request | 3 | Lincoln | Ariel | A9 |
| US18.1 | Venue suitability check per booking | 3 | Dylan | Ariel | A7 |
| US19.0 | Seed sample equipment data | 3 | Ariel | Lincoln | L6 |
| US19.1 | Equipment catalogue | 3 | Ariel | Lincoln | L7 |
| US19.2 | Coordinator requests equipment for an event | 3 | Ariel | Lincoln | L8 |
| US4.4 | Pending Safety Check status and transitions | 4 | Ivy | Lincoln | L10 |
| US4.6 | Cancel an event | 4 | Dylan | Ethan | E11 |
| US8.4 | Lead reassigns an event | 4 | Ethan | Ivy | I10 |
| US8.5 | Lead sees all assignments | 4 | Ethan | Ivy | I11 |
| US9.5 | Block deleting a venue that has future bookings | 4 | Lincoln | Dylan | D8 |
| US11.2 | Coordinator processes a change request | 4 | Ariel | Ethan | E10 |
| US12.2 | Flag bookings hit by venue unavailability | 4 | Ethan | Dylan | D6 |
| US12.3 | Venue availability view | 4 | Lincoln | Dylan | D9 |
| US14.4 | Holds expire automatically | 4 | Dylan | Ivy | I9 |
| US14.5 | Request a replacement venue | 4 | Ethan | Dylan | D7 |
| US17.1 | Safety Officer review queue | 4 | Ivy | Lincoln | L11 |
| US17.2 | Safety Officer records a decision | 4 | Ivy | Lincoln | L12 |
| US19.3 | Check equipment availability and reserve it | 4 | Ariel | Lincoln | L9 |
| US20.1 | Attendee registers for an event | 4 | Lincoln | Dylan | D10 |
| US20.2 | Attendee views registration and withdraws | 4 | Lincoln | Dylan | D11 |
| US20.3 | Organiser and Coordinator view registrations | 4 | Lincoln | Dylan | D12 |

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


# ETHAN: 11 tests + S0 (~168 min)

| # | User story | Sprint | Implemented by |
|---|---|---|---|
| E0 | S0 one-time setup (~5 min) | – | – |
| E1 | US2.1 Create and submit an event request | 1 | Ivy (buddy: Ariel) |
| E2 | US2.2 Save and resume a draft | 1 | Dylan (buddy: Lincoln) |
| E3 | US3.1 View my events | 1 | Ariel (buddy: Ivy) |
| E4 | US2.1 (reopened) Create and submit an event request | 3 | Ivy |
| E5 | US7.3 Coordinator requests clarification/amendment | 2 | Dylan |
| E6 | US7.1 Coordinator makes a review decision (approve/reject) | 2 | Ariel |
| E7 | US4.3 Status transitions: Submitted → Under Review → Approved/Rejected | 2 | Ariel |
| E8 | US10.1 Receive and manage notifications | 2 | Lincoln |
| E9 | US11.1 Organiser submits a change request on a submitted event | 2 | Ivy |
| E10 | US11.2 Coordinator processes a change request | 4 | Ariel |
| E11 | US4.6 Cancel an event | 4 | Dylan |

### E0 · S0: One-time setup (do this first, ~5 min)

Already done on 1 Nov 2026, so there's nothing to create:

| Check | Status |
|---|---|
| Database reseeded with the demo data (22 venues, 18 equipment items, 51 events) | Done |
| All 18 accounts switched to `@connectsphere.com` with password `password` | Done, all 18 checked in the database |
| Hold-expiry job `sweep-tentative-holds` running every 15 min (needed for US14.4) | Done |
| Repo files updated to the new logins (Playwright helpers, smoke test, seed scripts, READMEs) | Done, not yet committed |

What's left:

1. Start the backend and frontend (section 1.2).
2. Sign in through the app with each role account below and check where it lands:
   - `organiser@connectsphere.com` → **Events**
   - `coordinator@connectsphere.com` → **Events**
   - `coordinatorlead@connectsphere.com` → **Unassigned Queue**
   - `venuestaff@connectsphere.com` → **Venues** (22 venues listed)
   - `safetyofficer@connectsphere.com` → **Safety Review**
   - `technicalsupport@connectsphere.com` → **Equipment Requests** (the **Equipment** catalogue has 18 items)
   - `attendee@connectsphere.com` → **Upcoming Events**
3. Commit the updated repo files and post in the team chat: "S0 done. Database reseeded, logins are now `<role>@connectsphere.com` / `password`. Pull `main`, then sign out and back in before testing."

---

### E1 · US2.1: Create and submit an event request

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US2.1** | SPMG3T7-25 | Ivy (buddy: Ariel) | **Ethan** | 15 min |

> **User story:** As an Event Organiser, I want to fill in a new event request with all necessary details and submit it, so that ConnectSphere has what it needs to plan my event.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Form captures all fields as plain text/date/number inputs — no Venue/Equipment catalogue lookups yet (added in Sprint 2/3) | 1 |
| **AC2** | Submit requires: event name, purpose, proposed date, start/end time, and expected attendance (attendance must be a positive integer, end time after start time, date not in the past). Other fields optional. On success, status → submitted. | 3–10 |
| **AC3** | Row written to events table on success | 11–12 |
| **AC4** | Assumption: field requirements/limits are team-chosen defaults, not customer-confirmed | Note (no test) |

**Setup:** none

**Steps**

1. Sign in as `organiser@connectsphere.com` → top nav **Create**.
   → **New event** form. Fields: Title, Description, Purpose, Starts, Ends, Expected attendance, and the needs fields.
2. Fill in everything as in Recipe R1 with Title `T2.1 Tech Conference`, Starts `15 Dec 2026 09:00`, Ends `15 Dec 2026 17:00`, Expected attendance `150`. **Don't submit yet.**
3. Clear **Title** → **Submit**.
   → Error says the title is required. Not submitted. 📸
4. Put Title back. Clear **Purpose** → **Submit**.
   → Error says the purpose is required.
5. Put Purpose back. Set **Expected attendance** to `0` → **Submit**.
   → Error: attendance must be a positive whole number.
6. Set it to `-5`.
   → Same error.
7. Set it back to `150`. Set **Ends** to `15 Dec 2026 08:00` (before Starts) → **Submit**.
   → Error: the end must be after the start. 📸
8. Set Ends to `15 Dec 2026 17:00`. Set **Starts** to `1 Jan 2025 09:00` and **Ends** to `1 Jan 2025 17:00` → **Submit**.
   → Error: the date can't be in the past. 📸
9. Set Starts/Ends back to `15 Dec 2026 09:00` / `17:00`.
10. Click **Submit**.
    → Success. Status **Submitted**. Write down the ID. 📸
11. Go to **Events**.
    → `T2.1 Tech Conference` is listed with **Submitted**.
12. Refresh the page and reopen it.
    → All values are still there (the row was saved to the database).
13. Sign in as `coordinatorlead@connectsphere.com` → **Unassigned Queue**.
    → `T2.1 Tech Conference` is in the queue (nobody assigned yet, as per US8.2).

**Keep:** `T2.1 Tech Conference` (Submitted, unassigned). US3.1 uses it.

**Pass/Fail:** ☐

---

### E2 · US2.2: Save and resume a draft

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US2.2** | SPMG3T7-26 | Dylan (buddy: Lincoln) | **Ethan** | 10 min |

> **User story:** As an Event Organiser, I want to save an incomplete event request as a draft and reopen it later, so that I can complete it across multiple sessions before submitting.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Draft is saved with status "draft," distinct from "submitted," and is not visible to Event Coordinators | 3–4, 9 |
| **AC2** | Partial/incomplete data is accepted while in draft (no full-form validation) | 2–3 |
| **AC3** | Organiser can reopen and continue editing any of their own drafts | 5–6 |
| **AC4** | Submitting a resumed draft follows the same submit rule defined in US2.1 (full validation, then status becomes "submitted") | 7–8 |

**Setup:** none

**Steps**

1. Sign in as `organiser@connectsphere.com` → **Create**.
2. Fill in **only** Title `T2.2 Workshop Draft` and Description `Hands-on workshops`. Leave everything else empty.
3. Click **Save as draft**.
   → Saved. Status **Draft**. Write down the ID. 📸
4. Go to **Events** and wait a moment.
   → `T2.2 Workshop Draft` shows **Draft**.
5. Open it.
   → Title and Description are still filled. The form can still be edited. 📸
6. Add Purpose `Training`. Click **Save draft**.
   → Still **Draft**. Purpose is saved.
7. Click **Submit event** (some required fields are still empty).
   → Refused, with errors naming the missing fields. Still **Draft**.
8. Fill in the rest as in R1: Starts `16 Dec 2026 14:00`, Ends `16 Dec 2026 18:00`, attendance `50`, plus the needs fields → **Submit event**.
   → Status **Submitted**.
9. Make one more draft, `T2.2 Hidden draft` (title only, **Save as draft**). Sign in as `coordinator@connectsphere.com` → **Events**. Then type `http://localhost:5173/#/events/<draft ID>`.
   → The draft isn't in the list, and opening it by URL is refused. 📸

**Pass/Fail:** ☐

---

### E3 · US3.1: View my events

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US3.1** | SPMG3T7-27 | Ariel (buddy: Ivy) | **Ethan** | 10 min |

> **User story:** As an Event Organiser, I want to view a list of my event requests and open any one to see its full current information, so that I can track status and details in one place.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | List shows only requests belonging to the logged-in Organiser (no other Organiser's events are visible) | 1–2, 5–6 |
| **AC2** | Each list entry shows event name and current status | 2, 7 |
| **AC3** | Selecting an entry opens the event detail view, showing the latest saved information and current status. Drafts remain editable by the owning Organiser, while submitted requests are read-only. | 3–4 |

**Setup:** S0 (organiser2 exists), US2.1 and US2.2 done

**Steps**

1. Sign in as `organiser2@connectsphere.com` (Riley) → **Create** → Title `T3.1 Riley's event` → **Save as draft**.
2. Sign out. Sign in as `organiser@connectsphere.com` → **Events**.
   → Each row shows the event name and a status badge. `T2.1 Tech Conference` and `T2.2 Workshop Draft` are there. `T3.1 Riley's event` is **not**. 📸
3. Open `T2.2 Hidden draft` (Draft).
   → All saved fields shown. You can edit them (**Save draft** and **Submit event** buttons are there).
4. Go back and open `T2.1 Tech Conference` (Submitted).
   → All fields shown, but **read-only**: no **Save draft** or **Submit event** buttons, and the fields can't be typed in. The only action is **Request changes** (that's US11.1, which opens a change proposal rather than editing directly). 📸
5. Type `http://localhost:5173/#/events/<ID of T3.1 Riley's event>`.
   → Refused or "not found". Riley's data is not shown.
6. Sign in as `organiser2@connectsphere.com` → **Events**.
   → Only `T3.1 Riley's event`. None of Dylan's events.
7. Use the status filter buttons on Events (**All**, **Draft**, **Submitted**, …).
   → The list filters to that status.

**Pass/Fail:** ☐

---

### E4 · US2.1 (reopened): Mandatory fields and set options

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US2.1 (reopened)** | SPMG3T7-25 | Ivy | **Ethan** | 15 min |

> **User story:** As an Event Organiser, I want to fill in a new event request with all necessary details and submit it, so that ConnectSphere has what it needs to plan my event.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | On Submit, these are required: name, description, purpose, date, start/end time, expected attendance, venue requirements, preferred layout, accessibility needs, equipment needs, registration needs. | 2–4, 6 |
| **AC2** | Layout, facilities and accessibility use fixed lists that match the venue catalogue (US9.1a). | 1 |
| **AC3** | Fields that may not apply have a 'None / Not required' option. | 5–7 |
| **AC4** | Missing fields show a clear error and block submit. | 3 |
| **AC5** | Drafts still save without these checks (US2.2). | 8 |

**Setup:** none

**Steps**

1. Sign in as Organiser → **Create**.
   → **Preferred layout** is a dropdown (Theatre, Classroom, Boardroom, Banquet, …). **Venue requirements** and **Accessibility needs** are tick-box lists (e.g. Projector, PA system; Wheelchair access, Hearing loop). Each has **None / Not required**. 📸
2. Fill in Title, Description, Purpose, Starts `16 Dec 2026 10:00`, Ends `16 Dec 2026 12:00`, attendance `40`. Leave **all five needs fields empty** → **Submit**.
3. Check the errors.
   → One clear error **per** missing field: Venue requirements, Preferred layout, Accessibility needs, Equipment needs, Registration needs. Not submitted. 📸
4. Also clear Description → **Submit**.
   → Description error shown too (it's now mandatory).
5. Venue requirements: tick **Projector** and **PA system**, then tick **None / Not required**.
   → Projector and PA system are **unticked** automatically.
6. Fill in the rest: Layout **Theatre**, Accessibility **None / Not required**, Equipment needs tick **None / Not required**, Registration needs `Open registration`. Title `T2.1R Mandatory` → **Submit**.
   → **Submitted**.
7. Refresh.
   → Every answer kept, including the three "None / Not required" answers. 📸
8. **Create** → Title only `T2.1R Draft` → **Save as draft**.
   → Saves without any needs errors.
9. Sign in as Priya → type `#/events/new`.
   → "not open to your role" (only Organisers create).

**Pass/Fail:** ☐

---

### E5 · US7.3: Coordinator requests clarification/amendment

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US7.3** | SPMG3T7-36 | Dylan | **Ethan** | 12 min |

> **User story:** As an Event Coordinator, I want to request clarification or a change from the Organiser on a submitted event, so that I can get what I need before deciding.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Coordinator can attach a message to the event requesting info/changes. | 2–3, 7 |
| **AC2** | Status → Under Review. | 4 |
| **AC3** | Message is visible to the Organiser. | 5–6 |
| **AC4** | Organiser's response is handled by US11.1. | Tested in US11.1 |
| **AC5** | Any Coordinator can do this for now, not just the auto-assigned one. Can lock it down later once US8.1's working. | Now assigned Coordinator only: tested in US8.6 |

**Setup:** R2 (title `T7.3 Clarify event`, Priya)

**Steps**

1. Run R2 for `T7.3 Clarify event`.
2. Sign in as Priya → open it → **Request clarification**.
3. Type `Please break down the expected attendance. Will there be keynote sessions?` → **Send request**.
   → Success. 📸
4. Check the status.
   → **Under Review** (not "Needs Changes").
5. Sign in as `organiser@connectsphere.com` → **Notifications**.
   → A notice about the clarification request for `T7.3 Clarify event`.
6. Open the event → **Change and clarification history**.
   → Priya's message is shown word for word, with who and when. 📸
7. Try **Send request** with an empty message (as Priya on another event).
   → Refused: a message is needed.

**Pass/Fail:** ☐

---

### E6 · US7.1: Coordinator makes a review decision (approve/reject)

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US7.1** | SPMG3T7-35 | Ariel | **Ethan** | 15 min |

> **User story:** As an Event Coordinator, I want to approve or reject a submitted event, so that it either proceeds to planning or the Organiser knows it won't.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Only events in Under Review status can be decided. | 1, 8 |
| **AC2** | Approve → status Approved. | 3–4 |
| **AC3** | Reject → status Rejected, requires a non-empty reason, reason visible to the Organiser. | 5–7 |
| **AC4** | Decision is timestamped and attributable (who/when), reusing US4.2's audit pattern. | 9 |
| **AC5** | Any Coordinator can do this for now, not just the auto-assigned one. Can lock it down later once US8.1's working. | Now assigned Coordinator only: tested in US8.6 |

**Setup:** R1 ×1, R2 ×2

**Steps**

1. Run R1 for `T7.1 Not assigned` (leave it Submitted). Sign in as Priya and look for it in **Events**.
   → Not listed (not assigned). If it was visible, there would be no **Approve event** / **Reject event** buttons, because it isn't Under Review.
2. Run R2 for `T7.1 Approve me` and `T7.1 Reject me`.
3. As Priya, open `T7.1 Approve me` → **Approve event**.
   → Status **Approved**. 📸
4. Sign in as Organiser → open it.
   → **Approved**.
5. As Priya, open `T7.1 Reject me` → **Reject event**. Leave **Reason for rejection** empty and confirm.
   → Refused: a reason is required.
6. Type `Budget not approved for this event category` → confirm.
   → Status **Rejected**. 📸
7. Sign in as Organiser → open `T7.1 Reject me`.
   → **Rejected**. The reason is shown word for word. 📸
8. As Priya, open `T7.1 Approve me` again.
   → No **Approve event** / **Reject event** buttons (already decided).
9. On both events, look at **Status history**.
   → Approved/Rejected entries show **Priya** and a timestamp.

**Pass/Fail:** ☐

---

### E7 · US4.3: Status transitions: Submitted → Under Review → Approved/Rejected

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US4.3** | SPMG3T7-38 | Ariel | **Ethan** | 12 min |

> **User story:** As the system, I want event status to update automatically based on review/approval actions, so that status always reflects the real workflow state.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Valid transitions only: Submitted→Under Review, Under Review→Approved, Under Review→Rejected. | 1–3 |
| **AC2** | Any other transition attempt is blocked with a clear error. | 4–7 |
| **AC3** | Extends US4.2's existing trigger function rather than replacing it. | Code (no UI test) |

**Setup:** reuses the US7.1 events

**Steps**

1. Run R1 for `T4.3 Flow event`. Check status **Submitted**.
2. Assign it to Priya as in R2.
   → **Submitted → Under Review** happens automatically.
3. As Priya → **Approve event**.
   → **Under Review → Approved**. Status history shows all three steps with who/when. 📸
4. As Priya, open `T7.1 Approve me` (Approved).
   → No way to Reject it (Approved → Rejected not offered).
5. As Priya, open `T7.1 Reject me` (Rejected).
   → No way to Approve it.
6. (Server check, optional but recommended.) In the browser dev tools on the Approved event, Network tab → find any request with `Authorization: Bearer …` and copy the token. Then:
   ```bash
   curl -s -X POST http://localhost:8000/events/<T7.1 Approve me ID>/reject \
     -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"reason":"test"}'
   ```
   → HTTP 409 with a message like **"Only an event that is Under Review can be decided."** 📸
7. Same `curl` on `/approve` for a **Submitted, unassigned** event (e.g. `T7.1 Not assigned`).
   → Refused (409/403/404), with a clear message.

**Pass/Fail:** ☐

---

### E8 · US10.1: Receive and manage notifications

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US10.1** | SPMG3T7-44 | Lincoln | **Ethan** | 12 min |

> **User story:** As an Event Organiser, I want to be notified when my event's status changes and be able to mark notifications as read, so that I stay informed without my list becoming unmanageable.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Notification record created on Approved/Rejected/Under Review transitions. | 2 |
| **AC2** | Organiser sees an unread/read list, defaults to showing unread first, can toggle read state. | 3–6 |
| **AC3** | No email/push yet. | 7 |

**Setup:** reuses US7.3, US7.1 and US4.3 events

**Steps**

1. Sign in as `organiser@connectsphere.com`.
   → **Notifications** in the top nav has a number badge (unread count).
2. Open **Notifications**.
   → Notices for: `T7.1 Approve me` approved, `T7.1 Reject me` rejected (with the reason), and `T7.3 Clarify event` / `T4.3 Flow event` moved to Under Review. Each has a timestamp. 📸
3. Check the order.
   → Unread notices come first.
4. Click **Mark as read** on one.
   → Shows as read. Badge count goes down by 1. 📸
5. Click **Mark as unread** on the same one.
   → Unread again. Badge count goes back up.
6. Refresh.
   → Read/unread states are kept.
7. Check the Organiser's email inbox (if there is one).
   → No email was sent (in-app only).

**Pass/Fail:** ☐

---

### E9 · US11.1: Organiser submits a change request on a submitted event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US11.1** | SPMG3T7-45 | Ivy | **Ethan** | 12 min |

> **User story:** As an Event Organiser, I want to submit a request to change my submitted event's details, so that the Coordinator can review it instead of me editing it directly.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Submitting a change sets a "change requested" flag. | 4 |
| **AC2** | Event Organisers can open the existing event edit form to propose changes to their submitted event. | 2 |
| **AC3** | Event Organisers can edit the permitted event details and submit the proposed changes for Coordinator review. | 3 |
| **AC4** | The proposed changes are visible to the Event Coordinator for review. | 5 |
| **AC5** | Changes to date/time/attendance/venue/equipment fields are flagged important, same as US5.2's logging rule. | 5 |

**Setup:** R3 (title `T11.1 Change me`, attendance 150)

**Steps**

1. Run R3 for `T11.1 Change me` (Starts `8 Dec 2026 09:00`, Ends `8 Dec 2026 17:00`, attendance `150`).
2. Sign in as Organiser → open it.
   → Fields are read-only, with a **Request changes** button (the event is Approved).
3. Click **Request changes**. The fields become editable and a **Note for the Coordinator (optional)** box appears. Change Expected attendance `150` → `200`, Description → `Added breakout tracks`, note `Added a second track`. Click **Submit change request**.
   → Success. 📸
4. Check the event.
   → Shows a "change requested" flag. Status is still **Approved** (not changed). The current values are still 150 / old description until a Coordinator accepts.
5. Sign in as Priya → open `T11.1 Change me`.
   → **Requested changes** shows proposed vs current values. Attendance is marked **Important**. Description isn't. 📸
6. As Organiser, try **Submit change request** again while one is pending.
   → Refused: a request is already pending.

**Keep:** `T11.1 Change me` with its pending request, for US11.2.

**Pass/Fail:** ☐

---

### E10 · US11.2: Coordinator processes a change request

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US11.2** | SPMG3T7-78 | Ariel | **Ethan** | 25 min |

> **User story:** As an Event Coordinator, I want to accept or reject an Organiser's change request and see which arrangements it affects, so that changes don't quietly break bookings that were already made.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | The assigned Coordinator sees the change requests Organisers submitted (US11.1), with proposed values next to current values and important fields (date, time, attendance, venue, equipment) highlighted. | 1 |
| **AC2** | Accept applies the proposed values, logs them as important or routine (same rule as US5.2), clears the "change requested" flag and notifies the Organiser. | 6–8 |
| **AC3** | Reject needs a reason, keeps the current values and notifies the Organiser. | 2–4 |
| **AC4** | If an accepted change or a direct Coordinator edit changes the date, time or attendance, the system re-checks each venue booking for clashes (US15.1) and suitability (US18.1), and each equipment reservation for availability (US19.3). | 5–6, 9, 11 |
| **AC5** | Anything that now fails is marked 'Conflict – review needed' (same flag as US15.2). | 9 |
| **AC6** | Nothing is cancelled automatically, and the Coordinator is notified of what was flagged (US10.2). | 10 |

**Setup:** `T11.1 Change me` with its pending request (attendance 150 → 200)

**Steps**

1. As Priya, open `T11.1 Change me`.
   → **Requested changes**: proposed values next to current ones. Attendance (150 → 200) marked **Important**. Description not marked. 📸
2. **Reject changes** with an empty reason.
   → Refused: reason required.
3. Reason `Venue can't hold 200, keep at 150` → reject.
   → Attendance still **150**. "change requested" flag cleared.
4. As Organiser → **Notifications**.
   → Notice that the request was rejected, with the reason.
5. Set up the re-check: as Venue Staff, R0 `T11.2 Room` with **Capacity 160**. As Priya, request `T11.2 Room` for `8 Dec 2026 10:00–12:00`, headcount 150 → **Requested**.
6. As Organiser, open the event → attendance **200** → **Submit change request**.
7. As Priya → **Approve changes**.
   → Attendance now **200**. Flag cleared. **Change and clarification history** logs it as **Important**. 📸
8. As Organiser → **Notifications**.
   → "Requested changes approved" notice.
9. As Priya, look at **Arrangement review** on the event.
   → The re-check ran. Each booking/equipment line shows **Checks passed** or **Conflict – review needed: <reason>**. Expected: the `T11.2 Room` booking is flagged (capacity 160 < 200). If it shows Checks passed because the booking keeps its own headcount of 150, write down exactly what it shows and raise it with Ariel. 📸
10. Check the booking.
    → Still **Requested**, not cancelled. Priya → **Notifications**: notice listing what was flagged.
11. Direct edit path: as Priya, edit the event's Ends time → **Save changes**.
    → **Arrangement review** runs again (US11.2 says a direct Coordinator edit also re-checks).

**Pass/Fail:** ☐

---

### E11 · US4.6: Cancel an event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US4.6** | SPMG3T7-83 | Dylan | **Ethan** | 25 min |

> **User story:** As an Event Organiser or Event Coordinator, I want to cancel an event and have its bookings released, so that cancelled events don't keep holding venues and equipment.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | The owning Organiser or the assigned Coordinator can cancel any event that isn't Completed, Cancelled or Rejected. Reason required. | 3–4, 9–11 |
| **AC2** | Status → Cancelled, logged with who/when. The cancelled event becomes read-only. | 5 |
| **AC3** | All its active venue bookings and holds → Cancelled, and all equipment reservations are released, so the slots and quantities free up. | 6, 9 |
| **AC4** | Registrations are marked Event Cancelled. | 7 |
| **AC5** | The Coordinator, Organiser, affected Venue Staff, Tech Support and registered Attendees are notified. | 8–9 |
| **AC6** | Note: cancellation is not one of the 20 Release 1 core features, so this is the first story to drop if Sprint 4 runs short. | Note |

**Setup:** see steps 1–2

**Steps**

1. **Event X (Coordinator cancels):** R5 `T4.6 Coord cancels` on **Mon 21 Dec 2026 18:00–20:00** at a new R0 venue `T4.6 Hall`. Then as Priya, open registration (capacity 5). As Casey, register.
2. **Event Y (Organiser cancels):** R3 `T4.6 Org cancels` on **Tue 22 Dec 2026 09:00–12:00**. As Priya, request `T4.6 Hall` 09:00–10:00 (Requested). As Venue Staff, place a hold 10:00–11:00 expiring 21 Dec 2026 12:00. As Priya, request `Epson laser projector` × 2. As Tech Support, **Reserve** it.
3. As Priya, open Event X → **Cancel this event…** → leave the reason empty → **Confirm cancellation**.
   → Refused: reason required. **Keep event** closes it with no change.
4. Reason `Venue double-booked, no replacement found` → **Confirm cancellation**.
   → Status **Cancelled**. 📸
5. Check the event.
   → Read-only (no edit, booking or cancel buttons). **Status history** shows Cancelled by **Priya** with date/time and the reason.
6. Check its bookings.
   → The `T4.6 Hall` booking is **Cancelled**.
7. As Casey → **My Registrations**.
   → `T4.6 Coord cancels` shows **Event Cancelled**. 📸
8. **Notifications** for Organiser (Dylan), Venue Staff, and Casey.
   → Each has a cancellation notice. 📸
9. As Organiser, open Event Y → **Cancel this event…** → reason `Speaker unavailable` → confirm.
   → **Cancelled**. The Requested booking and the hold are both **Cancelled**. Tech Support gets a notice. 📸
   Equipment release check: run R3 `T4.6 Release check` on **22 Dec 2026 09:00–12:00**, request `Epson laser projector` × 1, and open it as Tech Support. → **Already reserved 0**, **Available 7** (8 total − 1 out of service), so Event Y's 2 projectors were released.
10. Open `T7.1 Reject me` (Rejected) and any Completed event (e.g. Ivy's `T4.5 Today`).
    → No **Cancel this event…** button.
11. As Sam Chen (not assigned), type the URL of a Priya event that's still active.
    → Refused, so he can't cancel it.

**Pass/Fail:** ☐

---


# DYLAN: 12 tests (~159 min)

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


# IVY: 12 tests (~153 min)

| # | User story | Sprint | Implemented by |
|---|---|---|---|
| I1 | US6.1 Project setup, repo, and CI pipeline | 1 | Dylan (buddy: Ariel) |
| I2 | US6.2 Core database schema | 1 | Ethan (buddy: Lincoln) |
| I3 | US4.1 View event status | 1 | Ethan (buddy: Dylan) |
| I4 | US4.2 Status transitions | 1 | Ariel |
| I5 | US9.1a Create a venue record | 2 | Ariel |
| I6 | US9.1b Update a venue record | 2 | Lincoln |
| I7 | US9.1c Delete a venue record | 2 | Dylan |
| I8 | US14.3 Place a tentative hold with an expiry | 3 | Lincoln |
| I9 | US14.4 Holds expire automatically | 4 | Dylan |
| I10 | US8.4 Lead reassigns an event | 4 | Ethan |
| I11 | US8.5 Lead sees all assignments | 4 | Ethan |
| I12 | US4.5 Missing lifecycle transitions | 3 | Ariel |

### I1 · US6.1: Project setup, repo, and CI pipeline

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US6.1** | SPMG3T7-31 | Dylan (buddy: Ariel) | **Ivy** | 10 min |

> **User story:** As the development team, I want a working repository, environment, and CI pipeline so that we can build, test, and integrate code reliably from Sprint 1 onward.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Git repository created with instructor access granted | 1–2 |
| **AC2** | CI pipeline runs on push/PR (build + tests at minimum) | 3–5, 7 |
| **AC3** | Local/dev environment instructions documented in README | 6–7 |

**Setup:** none

**Steps**

1. Open the GitHub repo.
   → Monorepo with `backend/` and `frontend/`.
2. **Settings → Collaborators** (needs an admin, ask Dylan if you can't see it).
   → The instructor account is listed. 📸
3. Open `.github/workflows/ci.yml`.
   → Runs `on: push: branches: [main]` and `pull_request`. Backend job: `ruff check .`, `python -m compileall -q app`, `pytest --cov`. Frontend job: `npm run lint`, `npm run build`, `npm test -- --coverage`.
4. **Actions** tab → open the latest run on `main`.
   → Both **backend** and **frontend** jobs are green. 📸
5. Open any recent merged PR → **Checks**.
   → CI ran on the PR.
6. Open `README.md`.
   → Has prerequisites, first-time setup for backend and frontend, Supabase `.env`, the SQL migration list, how to run both halves, and how to run the checks.
7. Follow "Run the checks" locally:
   ```bash
   cd backend && ruff check . && python -m compileall -q app && pytest --cov
   cd ../frontend && npm run lint && npm run build && npm test -- --coverage
   ```
   → All pass. 📸 the terminal.

**Pass/Fail:** ☐

---

### I2 · US6.2: Core database schema

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US6.2** | SPMG3T7-32 | Ethan (buddy: Lincoln) | **Ivy** | 10 min |

> **User story:** As the development team, I want an initial database schema for the core entities (User, Event, Venue, Equipment) so that Sprint 1 feature stories have a stable foundation to build on.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Schema covers entities and relationships needed by all Sprint 1 stories | 1–3 |
| **AC2** | Migrations/setup scripts are runnable by any team member | 4 |
| **AC3** | Schema is documented (e.g., in the repo or as part of the C4 model working notes) | 5 |

**Setup:** Supabase dashboard access

**Steps**

1. Open `backend/SUPABASE_SETUP.sql`.
   → Creates `users`, `events` (and the venue and equipment tables), plus the `user_role` and event status types.
2. Supabase → **Table Editor**.
   → Tables `users`, `events`, `venues`, `equipment` (or `equipment_items`) exist. 📸
3. Open `events` → look at the columns / foreign keys.
   → `organiser_id` links to `users`. Status column uses the status enum.
4. Check every script in the README "Required SQL migrations" table exists in `backend/` and says it is idempotent (safe to run twice). Pick one (e.g. `SUPABASE_ADD_VENUE_LAYOUTS.sql`) and run it again in the SQL Editor.
   → "Success. No rows returned." No error.
5. Check the schema is documented: README migration table and the C4 / schema notes in the SPM Google Doc.
   → Present. 📸

**Pass/Fail:** ☐

---

### I3 · US4.1: View event status

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US4.1** | SPMG3T7-28 | Ethan (buddy: Dylan) | **Ivy** | 10 min |

> **User story:** As an Event Organiser or Event Coordinator, I want to see an event's current status so that I understand where it stands.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Status is displayed wherever the event appears, using a fixed label set: Draft, Submitted, Under Review, Approved, Planning, Confirmed, Completed, Cancelled, Rejected | 2–4 |
| **AC2** | Visible to: the Organiser who owns the event, and any Event Coordinator (Sprint 1 — will narrow to only the assigned Coordinator once Coordinator Assignment exists in Sprint 2) | 5–6 |
| **AC3** | Venue Staff, Technical Support Staff, and Attendee visibility is out of scope for Sprint 1 — added when their respective features (Venue Booking, Equipment, Registration) are built | 7 |

**Setup:** R2 (title `T4.1 Status event`, assigned to Priya)

**Steps**

1. Run R2 for `T4.1 Status event`. Also save one draft, `T4.1 Draft`.
2. Sign in as `organiser@connectsphere.com` → **Events**.
   → Both events show a status badge: `T4.1 Status event` **Under Review**, `T4.1 Draft` **Draft**, in different colours.
3. Open `T4.1 Status event`.
   → Status badge at the top. **Status history** shows Draft → Submitted → Under Review. 📸
4. On **Events**, look at the filter buttons (there's one for each status that appears in your list, plus **All**). Click a few.
   → Every label comes from this set: Draft, Submitted, Under Review, Approved, Planning, Pending Safety Check, Confirmed, Completed, Cancelled, Rejected. No others (no "Ready" or "Ongoing"). Dylan has seeded events in most statuses, so most buttons show.
5. Sign in as `coordinator@connectsphere.com` (Priya, the assigned Coordinator) → **Events** → open `T4.1 Status event`.
   → Same status shown.
6. Sign in as `coordinator2@connectsphere.com` (Sam Chen, not assigned) → **Events**.
   → `T4.1 Status event` is not listed (narrowed to the assigned Coordinator, US8.1/US8.6).
7. Sign in as `venuestaff@connectsphere.com`. Type `http://localhost:5173/#/events/<T4.1 ID>`.
   → Refused.

**Pass/Fail:** ☐

---

### I4 · US4.2: Status transitions

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 1** | **US4.2** | SPMG3T7-29 | Ariel | **Ivy** | 10 min |

> **User story:** As an Event Organiser, I want my event's status to update automatically when I submit or save it, so that I always know my request has actually gone through and when the change happened.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Draft stays Draft on save. Submitting changes status to Submitted exactly once — a second submit attempt on an already-submitted event is rejected | 1–6 |
| **AC2** | Every status change is timestamped and attributable (who/when) for audit | 7 |
| **AC3** | Transitions beyond Draft→Submitted are out of scope until Review/Booking epics exist | Scope note (no test) |

**Setup:** none

**Steps**

1. Sign in as `organiser@connectsphere.com` → **Create** → Title `T4.2 Transition event` → **Save as draft**.
   → **Draft**.
2. Change Description → **Save draft**.
   → Still **Draft** (saving doesn't change the status).
3. Save it a second time.
   → Still **Draft**.
4. Fill in all the R1 fields (Starts `17 Dec 2026 10:00`, Ends `17 Dec 2026 16:00`) → **Submit event**.
   → **Submitted**. 📸
5. Refresh the page.
   → No **Submit event** button any more (it can't be submitted twice).
6. Open the same event in a second tab that was opened **before** step 4 (or press Back to the draft view) and click **Submit event**.
   → Refused with a message that it's already submitted. Status doesn't change and no second "Submitted" entry appears.
7. Look at **Status history**.
   → Shows Draft and Submitted, each with **who** (Dylan) and **when** (date and time). 📸

**Pass/Fail:** ☐

---

### I5 · US9.1a: Create a venue record

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.1a** | SPMG3T7-39 | Ariel | **Ivy** | 10 min |

> **User story:** As a Venue Staff member, I want to create a new venue record, so that it's available for Coordinators to plan around.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Restricted to Venue Staff. | 1, 8 |
| **AC2** | Required: name, capacity (positive integer), location. | 3–5 |
| **AC3** | Optional: facilities, accessibility flags, supported layouts, operating hours. | 6–7 |

**Setup:** none

**Steps**

1. Sign in as `venuestaff@connectsphere.com` → top nav **Add venue**.
   → Form: Name, Location, Capacity (Required). Setup time, Turnaround time, Facilities, Accessibility features, Supported layouts, Operating hours (Optional).
2. Fill in Name `T9.1 Innovation Lab`, Location `Science Building, Level 2`, Capacity `120`.
3. Clear **Name** → **Add venue**.
   → Error: name required.
4. Put the name back. Capacity `0` → **Add venue**.
   → Error: capacity must be a positive whole number. Try `-10` and `12.5`: same error. 📸
5. Capacity `120`. Clear **Location** → **Add venue**.
   → Error: location required.
6. Location back. Fill the optional fields: Facilities `Projector, Whiteboard, Video conferencing`, Accessibility features `Wheelchair access`, Supported layouts `Theatre, Classroom`, Operating hours `Mon-Fri 08:00-20:00`.
7. **Add venue**.
   → Saved. Opening it shows every value as entered. 📸
8. Sign in as `coordinator@connectsphere.com` → **Venues**.
   → No **Add venue** button. Typing `http://localhost:5173/#/venues/new` shows "not open to your role".

**Pass/Fail:** ☐

---

### I6 · US9.1b: Update a venue record

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.1b** | SPMG3T7-40 | Lincoln | **Ivy** | 8 min |

> **User story:** As a Venue Staff member, I want to update an existing venue's details, so that the catalogue stays accurate as facilities change.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Any field editable except system-generated ones (id, created_at). | 1–4 |
| **AC2** | Restricted to Venue Staff. | 5 |

**Setup:** `T9.1 Innovation Lab` from US9.1a

**Steps**

1. Venue Staff → **Venues** → open `T9.1 Innovation Lab` → **Edit venue**.
   → Form is pre-filled with the current values. No field for ID or created date.
2. Capacity `120` → `150`. Facilities: add `, Sound system`. Name → `T9.1 Innovation Lab B`.
3. **Save changes**.
   → Saved. 📸
4. Refresh.
   → Capacity 150, Sound system listed, new name.
5. Sign in as Priya → open the venue.
   → No **Edit venue** button. Typing `#/venues/<id>/edit` is refused.

**Pass/Fail:** ☐

---

### I7 · US9.1c: Delete a venue record

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 2** | **US9.1c** | SPMG3T7-41 | Dylan | **Ivy** | 5 min |

> **User story:** As a Venue Staff member, I want to remove a venue record, so that venues no longer in use don't clutter the catalogue.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Hard delete for Sprint 2 — no referential check needed yet since no bookings exist (that check becomes required once Sprint 3's booking feature exists). | 1–4 |
| **AC2** | Restricted to Venue Staff. | 5 |

**Setup:** `T9.1 Innovation Lab B` (no bookings)

**Steps**

1. Venue Staff → open `T9.1 Innovation Lab B` → **Delete venue**.
   → Confirmation shown with **Yes, delete it** / **Keep it**. 📸
2. **Keep it**.
   → Nothing is deleted.
3. **Delete venue** → **Yes, delete it**.
   → Back on Venues. It's gone.
4. Type its old URL `#/venues/<id>`.
   → Not found.
5. As Priya, open any venue.
   → No **Delete venue** button.

(The "blocked if it has future bookings" rule is tested in US9.5.)

**Pass/Fail:** ☐

---

### I8 · US14.3: Place a tentative hold with an expiry

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US14.3** | SPMG3T7-59 | Lincoln | **Ivy** | 15 min |

> **User story:** As a Venue Staff member, I want to place a tentative hold on a venue with an expiry date/time, so that I can keep a slot for a Coordinator who's still finalising, without blocking the venue forever.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | A hold is a venue booking with status Held, linked to an event and its Coordinator. | 4, 6 |
| **AC2** | Expiry date/time is required and must be in the future. | 2–3 |
| **AC3** | While Held and not expired, the slot counts as taken in US15.1. | 5 |
| **AC4** | Coordinator can turn the hold into a booking request before it expires (status → Requested). | 6–7 |
| **AC5** | A Held booking is never shown or counted as Confirmed. | 4, 6 |
| **AC6** | Assumption: Venue Staff place holds (customer to confirm if Coordinators can too). | 8 |

**Setup:** R0 `T14.3 Hall`; R3 `T14.3 Hold event` on **Mon 14 Dec 2026 08:00–20:00**

**Steps**

1. Run R0 and R3.
2. As Venue Staff, open `T14.3 Hall` → **Place a hold**: Event `T14.3 Hold event`, Starts `14 Dec 2026 14:00`, Ends `18:00`, leave **Hold expires** empty → **Place hold**.
   → Refused: expiry required.
3. Hold expires `1 Jan 2026 12:00` (in the past) → **Place hold**.
   → Refused: expiry must be in the future. 📸
4. Hold expires `13 Dec 2026 17:00` → **Place hold**.
   → Hold listed as **Held** with "Until 13 Dec 2026 17:00". Not shown as Confirmed. 📸
5. As Priya, try to request `T14.3 Hall` for `14 Dec 2026 15:00–16:00`.
   → Blocked: clashes with the hold.
6. As Priya, open `T14.3 Hold event`.
   → Booking shows **Held**, held by Sam, expiry time, and a **Request this venue** button. 📸
7. Click **Request this venue**.
   → Status **Held → Requested**. The expiry is no longer shown.
8. Sign in as Priya and look for **Place a hold** on any venue page.
   → Not there (Venue Staff only).

**Pass/Fail:** ☐

---

### I9 · US14.4: Holds expire automatically

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US14.4** | SPMG3T7-69 | Dylan | **Ivy** | 15 min active + up to 35 min waiting (do US8.4 / US8.5 while you wait) |

> **User story:** As the system, I want tentative holds to expire automatically at their deadline, so that venues don't stay blocked by holds nobody followed up on.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | A scheduled job checks holds at least every 15 minutes (team-chosen). | 1 |
| **AC2** | Holds past their expiry → Expired, and the slot is freed for other requests. | 5, 7 |
| **AC3** | Coordinator is notified 24h before expiry (assumption, customer to confirm) and again when it expires (US10.2). | 4, 6 |
| **AC4** | Expired holds stay in history and can't be turned into a booking request. | 5 |
| **AC5** | First time using a scheduler (e.g. Supabase pg_cron), so sized up for uncertainty. | Note |

**Setup:** R0 `T14.4 Hall`; R3 `T14.4 Expiry event` on **Wed 16 Dec 2026 08:00–20:00**

**Steps**

1. Supabase → SQL Editor: `select jobname, schedule from cron.job;`
   → A hold sweep job with schedule `*/15 * * * *`. 📸
2. Note the time now. As Venue Staff, open `T14.4 Hall` → **Place a hold**: Event `T14.4 Expiry event`, `16 Dec 2026 10:00–12:00`, **Hold expires = now + 20 min** → **Place hold**.
   → **Held**.
3. Go do **US8.4** and **US8.5**. Come back after **20 min**.
4. Priya → **Notifications**.
   → A **hold about to expire** notice for `T14.4 Hall` / `T14.4 Expiry event` (sent at the first sweep, because it expires within 24h). 📸
5. After the expiry time **plus up to 15 min** (or run `select public.sweep_tentative_holds();` in the SQL Editor to sweep now), open `T14.4 Expiry event` as Priya.
   → Booking shows **Hold expired** / **Expired**, still listed. **Request this venue** is gone or disabled. 📸
6. Priya → **Notifications**.
   → A **hold expired** notice. 📸
7. As Priya, request `T14.4 Hall` for `16 Dec 2026 10:00–12:00`.
   → Allowed (the slot was freed).

**Pass/Fail:** ☐

---

### I10 · US8.4: Lead reassigns an event

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US8.4** | SPMG3T7-72 | Ethan | **Ivy** | 15 min |

> **User story:** As an Event Coordinator Lead, I want to reassign an event to a different Coordinator, so that work can move if someone is overloaded or away.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Lead can change the assigned Coordinator on any active event. | 1, 6 |
| **AC2** | Old and new Coordinator are both notified (US10.2). | 3 |
| **AC3** | Old Coordinator loses access once reassigned (US8.6). | 4 |
| **AC4** | Reassignment logged with who/when and the previous Coordinator. (Update by the log window) | 5 |

**Setup:** R2 `T8.4 Reassign` (Priya); `T14.3 Hold event` (Planning) from US14.3

**Steps**

1. As Jordan, open `T8.4 Reassign` → **Reassign Coordinator** → pick **Sam Chen** → confirm.
   → Assigned Coordinator is now **Sam Chen**. 📸
2. As Sam Chen → **Events**.
   → `T8.4 Reassign` is listed, and he can act on it.
3. Priya and Sam Chen → **Notifications**.
   → Priya: reassigned away. Sam Chen: assigned to you. 📸 both.
4. As Priya, type `#/events/<T8.4 ID>`.
   → Refused.
5. As Jordan, open the event → **Coordinator assignment** / history.
   → **Status history** has an entry by **Jordan** with date and time, noting the reassignment. ⚠ The database stores it as `Coordinator reassigned from 2 to 10.` (user IDs, not names), and the history may label it like a Coordinator request. If the screen shows IDs instead of Priya → Sam Chen, mark this step ☒ and log a Low bug (AC: previous Coordinator must be logged). 📸
6. As Jordan, reassign `T14.3 Hold event` (Planning) to Sam Chen, then back to Priya.
   → Works for a Planning event too. Open `T4.5 Today` (Completed) or seeded `Freshmen Orientation Welcome Night` (Completed).
   → AC: only **active** events can be reassigned, so there should be no **Reassign Coordinator** button. ⚠ **Likely fail:** the code shows the button for any non-Draft event (`EventDetailPage.tsx` ~line 887) and the API doesn't check the status (`events.py` `reassign_coordinator`). If you can reassign a Completed event, mark ☒ and log a Medium bug.

**Pass/Fail:** ☐

---

### I11 · US8.5: Lead sees all assignments

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 4** | **US8.5** | SPMG3T7-73 | Ethan | **Ivy** | 10 min |

> **User story:** As an Event Coordinator Lead, I want to see all active events and who they're assigned to, so that I can keep track of workload across the team.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Lists all active events (not Draft, Completed, Cancelled or Rejected) with assigned Coordinator (or 'Unassigned') and status. | 1–3 |
| **AC2** | Can filter by Coordinator. | 4 |
| **AC3** | Shows a count of active events per Coordinator. | 5 |
| **AC4** | Read-only. Changes go through US8.3 / US8.4. | 6 |

**Setup:** data from earlier tests

**Steps**

1. As Jordan → **Team Assignments**.
   → Table with Event, Assigned Coordinator, Start Date, Status. 📸
2. Check what's excluded.
   → No Draft, Completed, Cancelled or Rejected events. E.g. seeded `Freshmen Orientation Welcome Night` (Completed), `Autumn Food Fiesta` (Cancelled) and `Rooftop Fireworks Party` (Rejected) are **not** listed.
3. Check what's included.
   → `T8.6 Unassigned` and seeded `Spring Career Fair 2027` show **Unassigned**. `T8.4 Reassign` shows **Sam Chen**. Seeded `AI in Finance Symposium` shows **Priya**.
4. Use the Coordinator filter → **Priya**.
   → Only Priya's events. Then **Unassigned** → only unassigned events.
5. **Workload Distribution**.
   → A count per Coordinator. Priya's count = the number of rows when filtered to Priya. 📸
6. Check for edit controls.
   → None on this page (changes happen through Assign / Reassign).

**Pass/Fail:** ☐

---

### I12 · US4.5: Missing lifecycle transitions

| Sprint | User story | Jira | Implemented by | Tested by | Time |
|---|---|---|---|---|---|
| **Sprint 3** | **US4.5** | SPMG3T7-60 | Ariel | **Ivy** | 35 min (includes waiting) |

> **User story:** As the system, I want the event status to move on automatically at the right points in the workflow, so that events don't get stuck at a status nobody can move them out of.

**Acceptance criteria (from Jira)**

| # | Acceptance criterion | Checked in steps |
|---|---|---|
| **AC1** | Submitted → Under Review automatically when the Lead assigns a Coordinator (US8.3). Needed as US7.1 can only decide events that are Under Review, and nothing else moves a complete request there. | 2 |
| **AC2** | Approved → Planning automatically when the Coordinator submits the first venue booking request for the event (US14.1). | 4 |
| **AC3** | Confirmed → Completed: the assigned Coordinator can mark the event Completed, but only after its end date/time has passed. | 5–9 |
| **AC4** | Under Review is only ever set from Submitted. A change request on an Approved or Planning event keeps the current status and uses the 'change requested' flag instead (US11.1 / US11.2). | 10 |
| **AC5** | Every transition is timestamped and attributable (US4.2 pattern). Any other transition is blocked with a clear error (US4.3 pattern). | 7, 11 |

**Setup:** R0 `T4.5 Hall`

**Steps**

> The event has to **end** before you can mark it Completed, so this uses **today's date**. Start the setup at least 30 min before the times you pick.

1. Note the time now (e.g. 14:00). Run R1 for `T4.5 Today` with Starts = **today, now + 25 min** and Ends = **today, now + 35 min** (e.g. 14:25–14:35).
   → **Submitted**.
2. As Jordan, assign it to Priya.
   → Status **Under Review** automatically (nothing else moved it). 📸
3. As Priya → **Approve event**.
   → **Approved**.
4. As Priya, request `T4.5 Hall` for the same 10 minutes.
   → Event **Approved → Planning** automatically. 📸
5. As Venue Staff, **Approve** the booking. As Priya, **Send for safety check**. As Alex, **Approve safety check**.
   → Event **Confirmed**.
6. As Priya, open the event (before the end time).
   → **Complete event** section says it can be marked Completed after the end. **Mark Completed** is **disabled**. 📸
7. (Optional server check) `curl -X POST http://localhost:8000/events/<id>/complete -H "Authorization: Bearer <Priya's token>"`
   → Refused with a message that the event hasn't ended.
8. Wait until after the end time (refresh the page).
   → **Mark Completed** becomes enabled.
9. Click **Mark Completed**.
   → "Completed. The status change has been recorded." Status **Completed**. 📸
10. Run R3 for `T4.5 Change while approved`. As Organiser, change attendance → **Submit change request**.
    → Status stays **Approved**. A "change requested" flag is shown. It does **not** go back to Under Review.
11. Look at **Status history** on `T4.5 Today`.
    → Every step (Submitted, Under Review, Approved, Planning, Pending Safety Check, Confirmed, Completed) has who and when. 📸

**Pass/Fail:** ☐

---


# LINCOLN: 12 tests (~160 min)

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


# ARIEL: 12 tests (~162 min)

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


# INTEGRATION TESTS (all-hands, run after the story tests)

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

## Test results summary

| Sprint | Tests | Passed | Failed | Blocked |
|---|---|---|---|---|
| Sprint 1 | 12 | | | |
| Sprint 2 | 13 | | | |
| Sprint 3 | 18 | | | |
| Sprint 4 | 16 | | | |
| Integration | 3 | | | |
| **Total** | **62** | | | |

| Tester | Assigned | Done | Passed | Failed |
|---|---|---|---|---|
| Ethan | 11 + S0 | | | |
| Dylan | 12 + Int 1 | | | |
| Ivy | 12 + Int 3 | | | |
| Lincoln | 12 + Int 2 | | | |
| Ariel | 12 | | | |

**Bugs found:** Critical ___ · High ___ · Medium ___ · Low ___
**Testing completed on:** ___________ · **Signed off by (PO):** ___________

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

**End of Master Test Plan**
