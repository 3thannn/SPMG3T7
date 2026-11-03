# Test Plan: Ethan (ConnectSphere, SPMG3T7)

**Tester:** Ethan · **Workload:** 11 tests + S0 (~168 min) · **Integration roles:** Integration 1: Organiser and Attendees · Integration 2: Venue Staff · Integration 3: Safety Officer

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

## 3. Your tests: 11 tests + S0 (~168 min)

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

---

## 4. Integration tests (all-hands, after the story tests)

Your roles: Integration 1: Organiser and Attendees · Integration 2: Venue Staff · Integration 3: Safety Officer

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
| E0 | S0 one-time setup (~5 min) | ☐ | |
| E1 | US2.1 Create and submit an event request | ☐ | |
| E2 | US2.2 Save and resume a draft | ☐ | |
| E3 | US3.1 View my events | ☐ | |
| E4 | US2.1 (reopened) Create and submit an event request | ☐ | |
| E5 | US7.3 Coordinator requests clarification/amendment | ☐ | |
| E6 | US7.1 Coordinator makes a review decision (approve/reject) | ☐ | |
| E7 | US4.3 Status transitions: Submitted → Under Review → Approved/Rejected | ☐ | |
| E8 | US10.1 Receive and manage notifications | ☐ | |
| E9 | US11.1 Organiser submits a change request on a submitted event | ☐ | |
| E10 | US11.2 Coordinator processes a change request | ☐ | |
| E11 | US4.6 Cancel an event | ☐ | |

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
