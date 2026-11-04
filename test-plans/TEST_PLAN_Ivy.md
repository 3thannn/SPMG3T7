# Test Plan: Ivy (ConnectSphere, SPMG3T7)

**Tester:** Ivy · **Workload:** 12 tests (~153 min) · **Integration roles:** Integration 1: Venue Staff and Safety Officer · Integration 3: **lead**

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

## 3. Your tests: 12 tests (~153 min)

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

---

## 4. Integration tests (all-hands, after the story tests)

Your roles: Integration 1: Venue Staff and Safety Officer · Integration 3: **lead**

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
| I1 | US6.1 Project setup, repo, and CI pipeline | ☐ | |
| I2 | US6.2 Core database schema | ☐ | |
| I3 | US4.1 View event status | ☐ | |
| I4 | US4.2 Status transitions | ☐ | |
| I5 | US9.1a Create a venue record | ☐ | |
| I6 | US9.1b Update a venue record | ☐ | |
| I7 | US9.1c Delete a venue record | ☐ | |
| I8 | US14.3 Place a tentative hold with an expiry | ☐ | |
| I9 | US14.4 Holds expire automatically | ☐ | |
| I10 | US8.4 Lead reassigns an event | ☐ | |
| I11 | US8.5 Lead sees all assignments | ☐ | |
| I12 | US4.5 Missing lifecycle transitions | ☐ | |

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
