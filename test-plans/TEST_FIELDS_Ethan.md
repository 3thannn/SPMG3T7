# Ethan: exact fields to type

Use this next to `TEST_PLAN_Ethan.md`. Every form you fill in is below, in run order, with the exact value for each field.
Password for every account: `password`.
Date fields use dd/mm/yyyy (Singapore format) and 24-hour time. If your picker shows AM/PM, 14:00 = 02:00 PM.

---

## Standard event form (used whenever a test says "full form")

Top nav **Create** → fill in:

| Field | Value |
|---|---|
| Title | *(given in each test)* |
| Description | `Test event for Ethan's QA run` |
| Purpose | `QA testing` |
| Starts | *(given in each test)* |
| Ends | *(given in each test)* |
| Expected attendance | *(given in each test, default `50`)* |
| Venue requirements | ☑ **Projector** ☑ **PA system** |
| Preferred layout | **Theatre** |
| Accessibility needs | ☑ **Wheelchair access** |
| Equipment needs | `2 wireless microphones` |
| Registration needs | `Open registration` |

Then **Submit**.

## Assign to Priya (used whenever a test says "assign")

1. Sign in `coordinatorlead@connectsphere.com`.
2. **Unassigned Queue** → **Search events...** → type the title.
3. **+ Assign Coordinator** → click **Priya**.

## Approve as Priya (used whenever a test says "approve")

Sign in `coordinator@connectsphere.com` → **Events** → open the event → **Approve event**.

---

## E0 · S0 setup

Sign in with each account and check where it lands:

| Email | Should land on |
|---|---|
| `organiser@connectsphere.com` | Events |
| `coordinator@connectsphere.com` | Events |
| `coordinatorlead@connectsphere.com` | Unassigned Queue |
| `venuestaff@connectsphere.com` | Venues |
| `safetyofficer@connectsphere.com` | Safety Review |
| `technicalsupport@connectsphere.com` | Equipment Requests |
| `attendee@connectsphere.com` | Upcoming Events |

---

## E1 · US2.1 Create and submit

Sign in `organiser@connectsphere.com` → **Create** → standard form with:

| Field | Value |
|---|---|
| Title | `T2.1 Tech Conference` |
| Starts | `15/12/2026 09:00` |
| Ends | `15/12/2026 17:00` |
| Expected attendance | `150` |

Don't submit yet. Change one field at a time, click **Submit**, then put it back:

| Step | Change this | To | Expect |
|---|---|---|---|
| 3 | Title | *(empty)* | Title required |
| 4 | Purpose | *(empty)* | Purpose required |
| 5 | Expected attendance | `0` | Must be a positive whole number |
| 6 | Expected attendance | `-5` | Same error |
| 7 | Ends | `15/12/2026 08:00` | End must be after start |
| 8 | Starts / Ends | `01/01/2025 09:00` / `01/01/2025 17:00` | Date can't be in the past |

Put everything back to the first table, then **Submit**. Write down the event ID from the URL: ______

---

## E2 · US2.2 Save and resume a draft

**Create** → fill in only these, then **Save as draft**:

| Field | Value |
|---|---|
| Title | `T2.2 Workshop Draft` |
| Description | `Hands-on workshops` |

Reopen it → Purpose `Training` → **Save draft** → **Submit event** (should be refused).

Then fill in the rest and **Submit event**:

| Field | Value |
|---|---|
| Starts | `16/12/2026 14:00` |
| Ends | `16/12/2026 18:00` |
| Expected attendance | `50` |
| Venue requirements | ☑ Projector ☑ PA system |
| Preferred layout | Theatre |
| Accessibility needs | ☑ Wheelchair access |
| Equipment needs | `2 wireless microphones` |
| Registration needs | `Open registration` |

Second draft: **Create** → Title `T2.2 Hidden draft` → **Save as draft**. ID: ______
Then as `coordinator@connectsphere.com`, go to `http://localhost:5173/#/events/<Hidden draft ID>`.

---

## E3 · US3.1 View my events

Sign in `organiser2@connectsphere.com` → **Create** → Title `T3.1 Riley's event` → **Save as draft**. ID: ______
Sign in `organiser@connectsphere.com` → open `http://localhost:5173/#/events/<Riley's ID>` (should be refused).

---

## E4 · US2.1 (reopened) Mandatory fields

**Create** → fill in only these, leave all five needs fields empty → **Submit**:

| Field | Value |
|---|---|
| Title | `T2.1R Mandatory` |
| Description | `Mandatory field check` |
| Purpose | `QA testing` |
| Starts | `16/12/2026 10:00` |
| Ends | `16/12/2026 12:00` |
| Expected attendance | `40` |

Step 4: clear Description → **Submit** → put it back.
Step 5: Venue requirements ☑ Projector ☑ PA system, then ☑ **None / Not required** (the other two should untick themselves).

Step 6, then **Submit**:

| Field | Value |
|---|---|
| Venue requirements | ☑ None / Not required |
| Preferred layout | **Theatre** |
| Accessibility needs | ☑ None / Not required |
| Equipment needs | ☑ None / Not required |
| Registration needs | `Open registration` |

Step 8: **Create** → Title `T2.1R Draft` → **Save as draft**.
Step 9: as `coordinator@connectsphere.com`, open `http://localhost:5173/#/events/new`.

---

## E5 · US7.3 Clarification

1. Standard form: Title `T7.3 Clarify event`, Starts `05/01/2027 10:00`, Ends `05/01/2027 12:00`, attendance `50` → **Submit**.
2. Assign to Priya.
3. As `coordinator@connectsphere.com` → open it → **Request clarification** → message:
   `Please break down the expected attendance. Will there be keynote sessions?` → **Send request**.

---

## E6 · US7.1 Review decision

Standard forms, each **Submit**:

| Title | Starts | Ends | Then |
|---|---|---|---|
| `T7.1 Not assigned` | `06/01/2027 10:00` | `06/01/2027 12:00` | leave unassigned |
| `T7.1 Approve me` | `07/01/2027 10:00` | `07/01/2027 12:00` | assign to Priya |
| `T7.1 Reject me` | `08/01/2027 10:00` | `08/01/2027 12:00` | assign to Priya |

IDs: Not assigned ______ · Approve me ______ · Reject me ______

As Priya:
- `T7.1 Approve me` → **Approve event**.
- `T7.1 Reject me` → **Reject event** → Reason for rejection empty → confirm (refused), then Reason for rejection `Budget not approved for this event category` → confirm.

---

## E7 · US4.3 Status transitions

1. Standard form: Title `T4.3 Flow event`, Starts `11/01/2027 10:00`, Ends `11/01/2027 12:00`, attendance `50` → **Submit**.
2. Assign to Priya → Priya **Approve event**.
3. Optional server check. Copy Priya's token from DevTools → Network → any request → `Authorization: Bearer …`:
   ```bash
   curl -s -X POST http://localhost:8000/events/<T7.1 Approve me ID>/reject \
     -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"reason":"test"}'
   curl -s -X POST http://localhost:8000/events/<T7.1 Not assigned ID>/approve \
     -H "Authorization: Bearer <token>"
   ```

---

## E8 · US10.1 Notifications

No forms. Sign in `organiser@connectsphere.com` → **Notifications** → **Mark as read** / **Mark as unread** on one notice.

---

## E9 · US11.1 Change request

1. Standard form: Title `T11.1 Change me`, Starts `08/12/2026 09:00`, Ends `08/12/2026 17:00`, attendance `150` → **Submit** → assign to Priya → Priya **Approve event**. ID: ______
2. As `organiser@connectsphere.com` → open it → **Request changes**, then:

| Field | Value |
|---|---|
| Expected attendance | `200` |
| Description | `Added breakout tracks` |
| Note for the Coordinator (optional) | `Added a second track` |

→ **Submit change request**.

---

## E10 · US11.2 Process change request

As Priya on `T11.1 Change me`:
- **Reject changes**, reason empty → refused.
- **Reject changes**, reason `Venue can't hold 200, keep at 150` → confirm.

Make the venue as `venuestaff@connectsphere.com` → **Add venue**:

| Field | Value |
|---|---|
| Name | `T11.2 Room` |
| Location | `QA Block` |
| Capacity | `160` |
| Setup time (minutes) | `0` |
| Turnaround time (minutes) | `0` |
| Facilities | `Projector, PA system, Stage` |
| Accessibility features | `Wheelchair access, Hearing loop` |
| Supported layouts | `Theatre, Classroom, Banquet` |
| Operating hours | `00:00-23:59` |

As Priya on `T11.1 Change me` → **Request a venue**:

| Field | Value |
|---|---|
| Venue | `T11.2 Room` |
| Starts | `08/12/2026 10:00` |
| Ends | `08/12/2026 12:00` |
| Headcount | `150` |
| Layout | `Theatre` |
| Facilities | `Projector` |
| Accessibility | `Wheelchair access` |

→ **Request venue**.

As `organiser@connectsphere.com` → **Request changes** → Expected attendance `200` → **Submit change request**.
As Priya → **Approve changes** → look at **Arrangement review**.
Direct edit: as Priya, change Ends to `08/12/2026 17:30` → **Save changes**.

---

## E11 · US4.6 Cancel an event

**Venue** (as `venuestaff@connectsphere.com` → **Add venue**): same as `T11.2 Room` above, but Name `T4.6 Hall` and Capacity `300`.

**Event X**: standard form, Title `T4.6 Coord cancels`, Starts `21/12/2026 18:00`, Ends `21/12/2026 20:00`, attendance `50` → **Submit** → assign to Priya → **Approve event**. Then as Priya → **Request a venue**:

| Field | Value |
|---|---|
| Venue | `T4.6 Hall` |
| Starts | `21/12/2026 18:00` |
| Ends | `21/12/2026 20:00` |
| Headcount | `50` |
| Layout | `Theatre` |
| Facilities | `Projector` |
| Accessibility | `Wheelchair access` |

→ **Request venue**. Venue Staff → **Booking Requests** → **Approve**. Priya → **Send for safety check**. `safetyofficer@connectsphere.com` → **Safety Review** → open it → **Approve safety check**.

Priya → registration card: ☑ **Open registration to Attendees**, Capacity `5` → **Save registration**.
`attendee@connectsphere.com` → **Upcoming Events** → **Register** → Name `Casey`, Email `attendee@connectsphere.com` → **Confirm registration**.

**Event Y**: standard form, Title `T4.6 Org cancels`, Starts `22/12/2026 09:00`, Ends `22/12/2026 12:00`, attendance `50` → **Submit** → assign to Priya → **Approve event**.
- Priya → **Request a venue**: Venue `T4.6 Hall`, Starts `22/12/2026 09:00`, Ends `22/12/2026 10:00`, Headcount `50`, Layout `Theatre`, Facilities `Projector`, Accessibility `Wheelchair access` → **Request venue** (leave it Requested).
- Venue Staff → open venue `T4.6 Hall` → **Place a hold**: Event `T4.6 Org cancels`, Starts `22/12/2026 10:00`, Ends `22/12/2026 11:00`, Hold expires `21/12/2026 12:00` → **Place hold**.
- Priya → **Equipment requests** → **Request equipment**: Equipment type `Projector`, Catalogue item `Epson laser projector`, Quantity `2`, Technical requirements *(empty)* → **Request equipment**.
- `technicalsupport@connectsphere.com` → **Equipment Requests** → open it → **Reserve**.

**Cancelling:**
- Priya on Event X → **Cancel this event…** → reason empty → **Confirm cancellation** (refused) → **Keep event**.
- Priya on Event X → **Cancel this event…** → reason `Venue double-booked, no replacement found` → **Confirm cancellation**.
- `organiser@connectsphere.com` on Event Y → **Cancel this event…** → reason `Speaker unavailable` → **Confirm cancellation**.

**Release check:** standard form, Title `T4.6 Release check`, Starts `22/12/2026 09:00`, Ends `22/12/2026 12:00` → **Submit** → assign → approve. Priya → **Request a venue** (`T4.6 Hall`, `22/12/2026 09:00`–`10:00`, headcount `50`) so the event goes to Planning. Then **Request equipment**: Projector / `Epson laser projector` / Quantity `1`. Tech Support opens it → should show **Available 7**.

**Refusal checks:** open `T7.1 Reject me`, and seeded `Freshmen Orientation Welcome Night` (Completed). Sign in `coordinator2@connectsphere.com` → open `http://localhost:5173/#/events/<T11.1 Change me ID>`.

---

## Integration tests (your roles)

**Integration 1 (lead: Dylan). You are the Organiser and the Attendees.**
- Standard form: Title `INT1 Annual Conference`, Starts `13/01/2027 09:00`, Ends `13/01/2027 17:00`, attendance `120` → **Submit**.
- When Priya asks for clarification: **Request changes** → Expected attendance `130`, note `Confirmed 130 attendees` → **Submit change request**.
- Once it's Confirmed and registration is open:
  - `attendee@connectsphere.com` → **Register** → Name `Casey`, Email `attendee@connectsphere.com` → **Confirm registration**.
  - `attendee2@connectsphere.com` → **Register** → Name `Morgan`, Email `attendee2@connectsphere.com` → **Confirm registration**.

**Integration 2 (lead: Lincoln). You are Venue Staff.**
- **Add venue**: Name `INT2 Hall`, Location `QA Block`, Capacity `300`, Setup `15`, Turnaround `15`, Facilities `Projector, PA system, Stage`, Accessibility features `Wheelchair access, Hearing loop`, Supported layouts `Theatre, Classroom, Banquet`, Operating hours `00:00-23:59`.
- **Booking Requests** → **Approve** the `INT2 Hall` booking.
- Open `INT2 Hall` → **Mark dates unavailable**: Start date `13/01/2027`, End date `15/01/2027`, Reason **Safety concern** → **Mark unavailable**.
- **Booking Requests** → **Approve** the Seminar Room 4 replacement.

**Integration 3 (lead: Ivy). You are the Safety Officer** (`safetyofficer@connectsphere.com`).
- **Safety Review** → open `INT3 Gala` → **Request changes** → What needs to change: `Add crowd management plan` → submit.
- When it's back in the queue → open it → **Approve safety check**.
