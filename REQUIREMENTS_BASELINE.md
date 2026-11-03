# Requirements baseline: ConnectSphere (SPMG3T7)

Built on 2026-11-03 from the sources below, read in full, and checked against the
code on `chore/playwright-test-reduction-handover` (which includes `main` at
`a6c8213`). Its job is to say what the system must do today, so test decisions
can be made against acceptance criteria instead of coverage.

## 1. Sources and precedence

| # | Source | What it gives | Read |
| --- | --- | --- | --- |
| 1 | Week 1 customer briefing | Organisation, roles, ~50 candidate features, the 14-step process, notifications, non-functional requirements | All |
| 2 | Week 2 clarification answers (21 Q&A) | Early process answers | All |
| 3 | Week 4 Project Instructions | The 20 core features, deliverables, rubric | All |
| 4 | Week 4 clarification answers (71 Q&A, updated 14 Sep) | Detailed rules | All |
| 5 | Week 7 customer changes (6 changes) | Changed requirements for Release 1 | All |
| 6 | Week 9 clarification answers (26 Q&A) | Answers about the Week 7 changes | All |
| 7 | Jira project `SPMG3T7` (22 epics, 65 stories) | The team's stories and ACs | All 87 issues. Issue comments were not read |
| 8 | Repo audits (`TEST_SUITE_US_AC_AUDIT.md`, `INDEPENDENT_TEST_REDUCTION_AUDIT.md`, `CONNECTSPHERE_AUDIT_REPORT.md`) | Earlier conflict analysis | Conflict, risk and fix-list sections |

When sources disagree, the later customer statement wins: Week 9 > Week 7 > Week 4
answers > Week 2 answers. A Jira AC that contradicts a later customer answer is
superseded, even if the story is marked Done. The rubric adds one rule of its own:
"100% coverage unless not possible and stated why."

## 2. The system in one page

ConnectSphere replaces spreadsheets and email for planning events at its venues.

**Roles:** Event Organiser (external client), Event Coordinator, Event Coordinator
Lead (Week 7), Venue Staff, Technical Support Staff, Safety Officer (Week 7),
Attendee. Accounts are pre-loaded; there is no self-registration (Week 4, Week 9).

**Event lifecycle as built and as the customer now wants it:**

```
Draft --submit--> Submitted --Lead assigns Coordinator--> Under Review
Under Review --approve--> Approved --first venue request--> Planning
Under Review --reject (reason)--> Rejected
Planning --all bookings Confirmed + equipment Reserved--> Pending Safety Check
Pending Safety Check --Safety approves--> (stays, "approved, awaiting Coordinator")
Pending Safety Check --Safety requests changes / rejects--> Planning
Pending Safety Check --Coordinator confirms, all approvals in--> Confirmed
Confirmed --important change accepted / replacement venue requested--> Planning
Confirmed --after end time, Coordinator--> Completed
any open status --Organiser or Coordinator, reason--> Cancelled (terminal)
```

**Venue booking lifecycle:** Held (Venue Staff, with expiry) → Requested → Confirmed
or Rejected; also Cancelled, Expired, Replaced, and the flags "Needs replacement"
(venue closed) and "Conflict – review needed" (setup or turnaround changed).

## 3. The 20 core features and the stories that deliver them

| # | Core feature (Project Instructions) | Jira epic | Stories |
| --- | --- | --- | --- |
| 1 | User Authorisation and Authentication | SPMG3T7-1 | US1.1 Login, US1.2 Logout, US1.3 Access enforcement, US1.4 Lead and Safety Officer roles |
| 2 | Event Request Creation | -2 | US2.1 Create and submit (reopened in Sprint 3: needs fields mandatory) |
| 3 | Draft Event Requests | -3 | US2.2 Save and resume a draft |
| 4 | Event Review and Approval | -4 | US7.1 Approve/reject, US7.3 Request clarification |
| 5 | Coordinator Assignment | -5 | US8.1 Auto-assign (**superseded**), US8.2 Unassigned queue, US8.3 Lead assigns, US8.4 Lead reassigns, US8.5 Lead sees all, US8.6 Coordinators only manage their own |
| 6 | Event Status Management | -6 | US4.1 View status, US4.2 Draft→Submitted, US4.3 Review transitions, US4.4 Pending Safety Check, US4.5 Missing transitions, US4.6 Cancel, US4.7 Coordinator confirms |
| 7 | Event Information Management | -7 | US3.1 View my events, US5.1 Coordinator views, US5.2 Coordinator edits, US5.3 Lock once Confirmed |
| 8 | Venue Catalogue | -8 | US9.0 Seed venues, US9.1a/b/c Create/update/delete, US9.2 View, US9.4 Setup/turnaround, US9.5 Block delete with future bookings |
| 9 | Venue Availability Calendar | -9 | US12.1 Mark unavailability, US12.2 Flag affected bookings, US12.3 Availability view |
| 10 | Venue Search and Filtering | -10 | US9.3 Search/filter |
| 11 | Venue Suitability Checking | -11 | US18.1 Suitability per booking |
| 12 | Venue Booking Request | -12 | US14.1 Request bookings, US14.2 Cancel one, US14.3 Tentative hold, US14.4 Holds expire, US14.5 Replacement venue, US12.4 Venue problem on Confirmed, US14.6 Update/release a hold (**To Do**) |
| 13 | Venue Booking Approval | -13 | US16.1 Approve or reject |
| 14 | Booking Conflict Detection | -14 | US15.1 Setup/turnaround in conflicts, US15.2 Flag clashes after a change |
| 15 | Equipment Request Management | -15 | US19.2 Coordinator requests equipment |
| 16 | Equipment Availability Checking | -16 | US19.0 Seed equipment, US19.1 Equipment catalogue |
| 17 | Equipment Reservation | -17 | US19.3 Check availability and reserve |
| 18 | Attendee Registration | -18 | US20.1 Register, US20.2 View and withdraw, US20.3 Organiser/Coordinator view |
| 19 | Event Change Requests | -19 | US11.1 Organiser requests a change, US11.2 Coordinator processes it, US11.3 Important change on Confirmed reopens planning |
| 20 | Notification System | -20 | US10.1 Organiser notices, US10.2 Coordinator notices, US10.3 Lead and confirmation notices, US10.4 Attendee change notices |
| — | Operational Safety Check (Week 7 #6) | -67 | US17.1 Safety review queue, US17.2 Safety decision |
| — | Technical enablers | -21 | US6.1 Repo and CI, US6.2 Database schema |

That is 65 stories: 64 Done, and US14.6 To Do. Every core feature has at least one
Done story. Housekeeping: 20 of the 22 epics are still "To Do" in Jira even though
their stories are Done. The backlog export is a graded deliverable, so tidy this
before exporting.

## 4. Rules the customer changed or clarified (current rule wins)

| Topic | Earlier rule | Current rule | Source | Jira | Code |
| --- | --- | --- | --- | --- | --- |
| Coordinator assignment | Auto-assigned, round-robin (Wk2, Wk4; US8.1) | Lead assigns manually; no auto-assignment; several Leads allowed | Wk7 #5, Wk9 | US8.2-8.6 | Done |
| Who acts on an event | "Any Coordinator for now" (US5.1, 5.2, 7.1, 7.3) | Only the assigned Coordinator; the Lead sees all | Wk9 | US8.6 | Done |
| Required fields at submit | Only name, purpose, date/time, attendance (US2.1 original) | Needs fields mandatory with "None / Not required" | Wk4 | US2.1 reopened | Done |
| Venue deletion | Hard delete (US9.1c) | Blocked while future bookings exist | team, after bookings existed | US9.5 | Done |
| Safety approval | Approve → Confirmed (US4.4, US17.2 original) | Approval is recorded; the Coordinator confirms once every approval is in | Wk9 | US17.2 updated, US4.7 | Done |
| Safety reject | Unclear | Back to Planning, like "request changes" | Wk9 | US17.2 | Done |
| Editing a Confirmed event | Coordinator may edit (US5.2) | No direct edits once Confirmed; use a change request | Wk4, Wk9 | US5.3 | Done (merged today) |
| Important change after Confirmed | Status kept, arrangements flagged (US11.2) | Back to Planning; all checks again, then re-confirm | Wk4, Wk9 | US11.3 | Done |
| Venue closed after booking | Event untouched (US12.2) | Don't cancel; flag and notify; for a Confirmed event the Coordinator reopens planning via a replacement | Wk7 #2, Wk9 | US12.2, US12.4 | Done |
| One venue per event | "Each event can only have one venue" (Wk4) | Several venues per event, each checked on its own | Wk7 #3 | US14.1, US18.1 | Done |
| Setup and turnaround | Not modelled | Part of every availability and conflict check | Wk7 #1 | US9.4, US15.1, US15.2 | Done |
| Equipment setup time | — | Not needed for Release 1 | Wk9 | — | n/a |
| Cancelled event | — | Terminal; start a new request instead | Wk4 (14 Sep) | US4.6 | Done |

## 5. Customer requirements with no story, or not met

These come from the answers and are not covered by any Done story. The "Release 1?"
column matters: the Week 1 briefing lists about 50 features, and Week 4 chose 20 of
them as core. An answer about a feature outside those 20 does not make it core.

| # | Customer said | Source | Release 1? | State in Jira and code |
| --- | --- | --- | --- | --- |
| G1 | Rejected events can be resubmitted after changes | Wk4 (three answers) | **Yes**: core "Event Review and Approval" and "Event Status Management" | **No story.** Rejected has no way out in `event_status.py` |
| G2 | Venue Staff set **and update** the hold duration | Wk9 | **Yes**: Week 7 change #4 | US14.6 is **To Do**; no update or release route |
| G3 | A hold starts **after** venue approval; the Coordinator confirms once Venue Staff approve | Wk9 | **Yes**: Week 7 change #4 | Built the other way round: Held → Requested → Confirmed (US14.3). Needs a team decision |
| G4a | Registration timing and closing are the **Organiser's** call, and capacity is at the Organiser's discretion | Wk4 | **Partly**: core "Attendee Registration" says "where enabled" but not by whom | US20.1 gives the switch and capacity to the **Coordinator** |
| G6 | One person can hold several roles | Wk4 (three answers) | **Partly**: core "User Authorisation and Authentication" | **No story.** A user has exactly one `role` |
| G7 | Room layouts are managed in the venue catalogue (add, edit, delete) | Wk9 | **Partly**: core "Venue Catalogue" includes supported layouts; "Room Layout Management" itself is not core | Layouts are a fixed list in `event_needs.py` |
| G11 | Safety Officer checks emergency access, crowd movement and equipment placement | Wk7 #6 | **Yes** | The review shows attendance, capacity, layout, accessibility and equipment. Wk9 says the Safety Officer "do not need to input but to approve", which may be enough. Worth one sentence in the docs |
| G4b | A waiting list is supported | Wk2, Wk4 | **No**: "Attendee Waiting List" is a separate, non-core feature | Not built |
| G5 | Reminders for incomplete arrangements, frequency configurable | Wk4 | **No**: "Reminder System" is non-core, though the answer was given about notifications | Not built; only hold-expiry notices exist |
| G8 | A single event calendar across all events | Wk4 | **No**: "Event Calendar" is non-core | US12.3 is per venue only |
| G9 | Organisers in one organisation see the organisation's events | Wk2, Wk4 | **No**: "Client Management" is non-core | Organisers see only their own events |
| G10 | Organiser can ask to withdraw a request via the Coordinator | Wk4 | **No**: "Cancellation Management" is non-core | Partly met anyway: US4.6 lets the Organiser cancel |

G1, G2 and G3 are the ones an instructor is most likely to test, because they sit
inside core features or Week 7 changes. The "No" rows need only a written
"not in Release 1" note in the backlog, not code or tests.

### Week 1 features outside the Release 1 core

User Profile Management, Client Management, Event Categories, Event Programme and
Agenda, Multi-Session Events (handled instead as several venue bookings, per Wk9),
Recurring or Similar Events, Comments and Discussion (Wk9 asks only that
clarification comments are recorded, which US7.3 does), Supporting Documents,
Tentative Venue Holding and Setup and Turnaround Time (both brought in by Week 7),
Venue Unavailability Management (brought in by Week 7 #2), Room Layout Management,
Event Capacity Management, Equipment Maintenance Status (partly in US19.1),
Technical Support Requests, Technical Staff Assignment, Event Readiness Tracking
and Outstanding Action Tracking (partly in US4.7's confirmation checks), Event
Confirmation (US4.7), Registration Capacity and Period, Attendee Waiting List,
Attendance Recording, Rescheduling, Cancellation Management (US4.6), Reminder
System, Event Calendar, Search and Filtering of events, Activity and Change History
(partly met by the audited status history), Role-Based Dashboard, and all reports
and exports.

## 6. What this means for the tests

1. **Every current AC needs at least one test, and the class method applies:** one
   happy path, plus negative and boundary cases where the AC has a rule or a limit.
   The stories in section 3 are the list to check against.
2. **Tests of superseded rules should go, with a note:** round-robin assignment
   (US8.1), Safety approval confirming the event (US4.4/US17.2 original), hard
   deletion with bookings (US9.1c), and direct edits of a Confirmed event (US5.2).
   One regression per rule that proves the *new* behaviour stays.
3. **Tests that encode a team assumption the customer contradicted** (G3, G4, G7)
   should stay until the team decides, and be labelled as assumptions.
4. **Gaps (section 5) have no tests,** and none should be written until the team
   decides what to build. Write the decision down either way.
5. **Coverage is a safety net, not the rule.** Keep 100% (the rubric asks for it),
   but choose tests by AC first.

## 7. Open questions for the team

1. For G1, G2, G3, G4a, G6, G7 and G11, which will the team build before Week 12,
   and which get a written decision instead?
2. Should the AC-to-test mapping go into the existing `MASTER_TEST_PLAN.md`, or into
   a separate traceability file?
