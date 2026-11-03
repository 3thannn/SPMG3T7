# ConnectSphere requirements audit

Audit date: 3 November 2026; refreshed after pulling `main` at `9770290`  
Audited artefact: current repository working tree, including restored uncommitted changes, checked against `ConnectSphere_Audit_Pack.zip` sources  
Method: requirements-to-source check, Python/SQL/React inspection, history/status inspection, PDF visual verification, and executable checks. No product code was changed.

## 1. Summary

- The pulled release fixes four former P0 gaps: separate Coordinator confirmation, post-Confirmed important-change reflow, Coordinator-driven venue replacement reflow, and production reassignment.
- The largest remaining customer contradiction is that Coordinators can still directly edit **Confirmed** event fields.
- Hold expiry can be set but not updated by Venue Staff; Safety review still lacks explicit emergency-access, equipment-placement and crowd-movement data.
- Python: **2,504 passed, 10 skipped**, 100% line and branch coverage. Frontend: **1,400 passed**, 100% lines/functions/statements and 94.81% branches.
- Isolated Playwright: **10 passed** after aligning the in-memory server with the documented `@connectsphere.com` / `password` accounts and updating the Safety scenario for separate Coordinator confirmation. CI still does not run Playwright.
- CI now runs four Postgres integration modules, but they were not locally executable because Docker/Postgres was unavailable; the normal suite still skips 10 opt-in DB cases.
- Ruff and byte-compilation now pass. An obsolete omnibus repair SQL file is preserved on the controlled branch alongside the current focused migrations and must not be applied without review.
- C4 diagrams and a real Git repository URL remain absent.

### Evidence key used by the matrix

Every matrix row cites one or more code and test evidence keys below. Line numbers refer to the audited snapshot.

| Key | Code evidence |
|---|---|
| C-A | `backend/app/permissions.py:13-30,139-233` (`Role`, `ROLE_PERMISSIONS`); `backend/app/auth.py` (`login`, session dependencies); `backend/app/events.py:439-498` (`_readable`, `list_events`) |
| C-B | `backend/app/events.py:672-819` (`create_event`, `save_event`, `submit_event`); `backend/app/event_validation.py` (`validate_event`, mandatory needs); `backend/app/event_store.py` (`create_event`, `save_event`) |
| C-C | `backend/app/events.py` (`request_clarification`, `approve_event`, `reject_event`); `backend/app/event_store.py` (`decide_event`); `backend/app/notifications.py` (status/clarification notices) |
| C-D | `backend/app/events.py:520-680` (`assign_coordinator`, `reassign_coordinator`); `backend/app/event_store.py` (`assign_coordinator`, `reassign_coordinator`); `backend/app/reassignment.py`; committed `SUPABASE_US8_4_REASSIGN_COORDINATOR.sql` |
| C-E | `backend/app/event_status.py` (status groups/transitions); `backend/app/event_confirmation.py`; `backend/app/events.py:1170-1240` (readiness/Coordinator confirmation); `backend/SUPABASE_US4_7_CONFIRM_EVENT.sql` |
| C-F | `backend/app/venues.py:167-285,941-1011` (search/calendar/unavailability); `backend/app/suitability.py:225-268` (`assess`); `backend/app/venue_turnaround.py:76-184` (occupied window/recheck) |
| C-G | `backend/app/events.py:2035-2197` (booking request); `backend/app/booking_decisions.py:259-338` (approval/rejection); `backend/app/availability.py:43-149` (slot rules); `backend/app/booking_store.py` (multi-booking persistence) |
| C-H | `backend/app/holds.py:1-25,174-230` (place/list holds); `backend/app/booking_store.py:196-223` (effective expiry); `backend/SUPABASE_US14_4_HOLD_EXPIRY.sql:64-124`; `backend/SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql:1-23` |
| C-I | `backend/app/equipment.py` (catalogue, request, update, availability, decision); `backend/app/equipment_store.py` (overlap/out-of-service/reservation persistence); `backend/SUPABASE_ADD_EQUIPMENT_REQUESTS.sql` and equipment reservation SQL functions |
| C-J | `backend/app/registrations.py:111-196,211-257,263-421,424-560` (settings, attendee list/register/withdraw, managed-event list); `backend/app/registration_store.py` and `backend/SUPABASE_US20_1_REGISTRATION.sql` |
| C-K | `backend/app/change_requests.py` (permitted/important fields and reopen reason); `backend/app/events.py:700-810,1730-1780` (direct edit and review); `backend/app/arrangement_review.py`; committed `SUPABASE_US11_3_RECONFIRM.sql` |
| C-L | `backend/app/venues.py` (`mark_unavailable`); `backend/app/replacement_venues.py:130-215`; `backend/app/booking_store.py:401-438,791-840`; committed `SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql` |
| C-M | `backend/app/safety_check.py` (readiness); `backend/app/safety_review.py` (review material); `backend/app/events.py` (send/decide/confirm); `backend/app/event_confirmation.py`; committed `SUPABASE_US4_7_CONFIRM_EVENT.sql` |
| C-N | `backend/app/notifications.py` (`notify_*`, including submission, confirmation, reassignment, planning-reopen and attendee-update notices); reassignment notifications are written atomically by `SUPABASE_US8_4_REASSIGN_COORDINATOR.sql` |
| C-O | Focused committed migrations now cover US4.7, US8.4, US11.3 and US12.4 and are included in README order/CI integration. `backend/SUPABASE_FOUR_STORY_FIX.sql` remains an obsolete untracked repair bundle and should not be submitted as an additional migration. |

| Key | Test evidence |
|---|---|
| T-A | `backend/tests/test_auth_login.py::test_valid_credentials_return_a_session`; `test_access_enforcement.py::test_an_out_of_role_request_is_blocked`; `test_assignment_scoped_events.py`; frontend permission/router tests |
| T-B | `backend/tests/test_events.py::TestCreateEvent`; `test_events.py::TestSubmitEvent`; `test_drafts.py`; `test_event_needs.py`; `frontend/src/pages/NewEventPage.test.tsx` |
| T-C | `backend/tests/test_event_review.py`; `test_clarification.py`; `test_notifications.py`; `frontend/src/pages/EventDetailPage.test.tsx` |
| T-D | `backend/tests/test_coordinator_assignment.py`; `test_reassignment_us8_4.py` (route/store/closed/status/access/notices); `backend/integration/test_us8_4_db.py` is now in CI |
| T-E | `backend/tests/test_confirm_event_us4_7.py`; updated Safety tests assert approval leaves the event Pending Safety Check until assigned Coordinator confirms; `SafetyCheckPanel.test.tsx` covers the UI action |
| T-F | `backend/tests/test_venues.py`; `test_venue_search_filters.py`; `test_venue_suitability.py`; `test_venue_turnaround.py`; `test_venue_availability_us12_3.py` |
| T-G | `backend/tests/test_venue_bookings.py`; `test_booking_decisions.py::TestApproving::test_tc_d07_two_requests_for_one_slot_cannot_both_be_approved`; `test_booking_conflicts.py::TestTheOccupiedWindow::test_tc_c01_the_customer_s_worked_example` |
| T-H | `backend/tests/test_holds.py`; `test_hold_expiry_us14_4.py::TestBeforeTheSweep::test_an_expired_hold_never_holds_its_venue`; no test for updating an expiry because no update route exists |
| T-I | `backend/tests/test_equipment.py::test_request_happy_path_and_notifications`; equipment reservation/availability tests; opt-in `test_equipment_reservations_db.py` was skipped |
| T-J | `backend/tests/test_registration_us20_1.py::TestRegister::test_an_attendee_registers_with_a_name_and_an_email`; `test_registration_us20_2.py::TestWithdraw::test_a_registration_before_its_confirmed_event_starts_may_be_withdrawn`; `test_registration_us20_3.py` |
| T-K | `backend/tests/test_change_requests.py`; `test_reconfirm_us11_3.py` covers Confirmed important change → Planning → fresh Safety approval → Coordinator reconfirm; `test_change_review_us11_2.py::test_direct_edit_and_accept_use_same_checks` still demonstrates direct Coordinator edit |
| T-L | `backend/tests/test_venue_problem_us12_4.py`; `test_replacement_venue_us14_5.py`; `backend/integration/test_us12_4_db.py` is now in CI and covers the committed production RPC/reopen transaction |
| T-M | `backend/tests/test_safety_review_us17_1.py`; updated `test_safety_decision_us17_2.py`; `test_confirm_event_us4_7.py`; approval/request/reject and fresh-check paths are separated |
| T-N | `backend/tests/test_notifications_us10_3.py`; `test_attendee_notices_us10_4.py`; `test_reassignment_us8_4.py`; trigger-specific notification suites |
| T-O | Four integration modules are configured in CI. They were not run locally because no Docker/Postgres service was available; normal unit tests still use fakes and skip 10 opt-in DB cases. |

## 2. Traceability matrix

| Req ID | Verdict | Code evidence | Test evidence | Notes |
|---|---|---|---|---|
| R-ROLE-01 | IMPLEMENTED | C-A; seed scripts | T-A | No self-registration; accounts are externally seeded/preloaded. |
| R-ROLE-02 | IMPLEMENTED | C-A, C-D | T-A, T-D | Multiple Lead accounts share the full queue; only one Lead is in the basic seed list. |
| R-AUTH-01 | IMPLEMENTED | C-A | T-A | Supabase Auth in production; in-memory credentials in tests. |
| R-AUTH-02 | IMPLEMENTED | C-A | T-A | Role and event relationship are checked server-side. |
| R-AUTH-03 | IMPLEMENTED | C-A, C-J | T-A, T-J | Organiser/Attendee projections are scoped. |
| R-AUTH-04 | IMPLEMENTED | C-A | T-A, T-D | Coordinator reads/manages assigned events only. |
| R-AUTH-05 | IMPLEMENTED | C-A, C-D | T-A, T-D | Lead sees assigned and unassigned events. |
| R-AUTH-06 | IMPLEMENTED | C-K | T-K | Organiser direct submitted edit returns 409. |
| R-CF2-01 | IMPLEMENTED | C-B | T-B | All stated request fields are persisted/validated. |
| R-CF2-02 | PARTIAL | C-F, C-G | T-F, T-G | Hours are enforced when assessing/requesting a venue, not when the initial event request is submitted. |
| R-CF2-03 | IMPLEMENTED | C-B | T-B | Mandatory fields and explicit none/not-required choices enforced. Jira clarification still needs source confirmation. |
| R-CF3-01 | IMPLEMENTED | C-B | T-B | Partial drafts can be resumed. |
| R-CF3-02 | IMPLEMENTED | C-E | T-B | Draft is a distinct status. |
| R-CF4-01 | IMPLEMENTED | C-C | T-C | Clarify/approve/reject paths exist. |
| R-CF4-02 | IMPLEMENTED | C-C, C-N | T-C | Outcome/history/notifications exposed. |
| R-CF4-03 | IMPLEMENTED | C-C | T-C | System records tracking comments; conversation remains offline. |
| R-CF4-04 | IMPLEMENTED | C-C | T-C | Decisions remain in history. |
| R-CF5-01 | IMPLEMENTED | C-D, C-O | T-D | Initial assignment and production reassignment use separate committed atomic RPCs. |
| R-CF5-02 | IMPLEMENTED | C-D | T-D | Submission remains unassigned; no active round-robin. |
| R-CF5-03 | IMPLEMENTED | C-D, C-O | T-D | Lead-only production route/RPC reassigns active events. |
| R-CF5-04 | IMPLEMENTED | C-D, C-O | T-D | Planning/Pending/Confirmed active events can be reassigned; closed events are refused. |
| R-CF5-05 | IMPLEMENTED | C-N, C-O | T-N | Initial assignment and atomic reassignment notify relevant Coordinators. |
| R-CF6-01 | IMPLEMENTED | C-E, C-K, C-L | T-E, T-K, T-L | Confirmation and both required post-Confirmed reflows now have explicit audited transitions. |
| R-CF6-02 | OPEN | C-E | T-E | Current set: Draft, Submitted, Under Review, Approved, Planning, Pending Safety Check, Confirmed, Completed, Cancelled, Rejected. |
| R-CF6-03 | IMPLEMENTED | C-E, C-M | T-E | Safety approval records approval/notifies; assigned Coordinator performs the only transition to Confirmed after readiness checks. |
| R-CF7-01 | IMPLEMENTED | C-K | T-K | Assigned Coordinator can update during planning. |
| R-CF7-02 | IMPLEMENTED | C-K | T-K | Important fields are classified and audited. |
| R-CF7-03 | CONTRADICTS | C-K | T-K | `save_event` allows Coordinator edits in Confirmed; a test exercises this behavior. |
| R-CF7-04 | UNCLEAR | C-A, C-I, C-K | T-A, T-I | Code implements broad Coordinator edit plus domain-specific prep edits, but Jira-only clarification is unverified and conflicts with R-CF7-03 after confirmation. |
| R-CF8-01 | IMPLEMENTED | C-F | T-F | Venue catalogue includes the stated attributes. |
| R-CF8-02 | IMPLEMENTED | C-F | T-F | Layout values can be added/edited/deleted as part of the venue record. |
| R-CF8-03 | IMPLEMENTED | C-F | T-F | Setup/turnaround configurable. |
| R-CF9-01 | IMPLEMENTED | C-F | T-F | Internal availability/calendar view exists. |
| R-CF9-02 | IMPLEMENTED | C-F, C-G | T-F, T-G | Bookings and closures shown. |
| R-CF9-03 | IMPLEMENTED | C-F, C-G, C-H | T-F, T-G, T-H | Buffers and active holds included. |
| R-CF10-01 | IMPLEMENTED | C-F | T-F | All named filters are supported. |
| R-CF11-01 | IMPLEMENTED | C-F | T-F | Suitability result and reasons returned. |
| R-CF11-02 | IMPLEMENTED | C-F | T-F | Over-capacity and missing facilities fail. |
| R-CF11-03 | IMPLEMENTED | C-F, C-G | T-F, T-G | Other named factors are checked. |
| R-CF11-04 | IMPLEMENTED | C-G | T-G, T-L | Per-booking independent assessment. |
| R-CF12-01 | IMPLEMENTED | C-G | T-G | Coordinator submits full booking needs. |
| R-CF12-02 | IMPLEMENTED | C-G | T-G | Multiple bookings per event. |
| R-CF12-03 | IMPLEMENTED | C-G | T-G | Sessions are separate booking requests under one event. |
| R-CF13-01 | IMPLEMENTED | C-G | T-G | Venue Staff decision queue/actions. |
| R-CF13-02 | IMPLEMENTED | C-G | T-G | Rejection reason and optional suggestion retained. |
| R-CF13-03 | IMPLEMENTED | C-G | T-G | Decisions affect only one booking. |
| R-CF13-04 | IMPLEMENTED | C-F, C-G | T-G | Approval rechecks buffered occupied window. |
| R-CF14-01 | IMPLEMENTED | C-G | T-G | Atomic conflict recheck prevents double booking. |
| R-CF14-02 | IMPLEMENTED | C-G | T-G | Confirmed bookings occupy slots. |
| R-CF14-03 | IMPLEMENTED | C-F, C-G | T-G | Effective window uses setup/turnaround; exact boundary tested. |
| R-CF14-04 | IMPLEMENTED | C-F | T-F, T-G | Existing clashes are flagged, not removed. |
| R-CF14-05 | IMPLEMENTED | C-H | T-H | Active hold occupies; effective expiry frees; expired is not confirmed. |
| R-CF14-06 | IMPLEMENTED | C-G | T-G | Independent venue conflict checks. |
| R-CF14-07 | OPEN | C-G | T-G | Current behavior: Requested blocks another request, but not approval; first approved wins. |
| R-CF15-01 | IMPLEMENTED | C-I | T-I | Exact item/type, quantity and technical requirements recorded. |
| R-CF15-02 | IMPLEMENTED | C-I | T-I | Technical Support reviews and updates support-side fields. |
| R-CF16-01 | IMPLEMENTED | C-I | T-I | Time-aware suitable stock is calculated. |
| R-CF16-02 | IMPLEMENTED | C-I | T-I | Reserved overlaps and out-of-service units reduce stock. |
| R-CF16-03 | OPEN | C-I | T-I | Current choice is the broader W4 reading: real stock/overlap availability, not catalogue presence alone. |
| R-CF17-01 | IMPLEMENTED | C-I | T-I | Reserve action exists. |
| R-CF17-02 | IMPLEMENTED | C-I | T-I | Reservation is event-linked and reduces overlapping availability. |
| R-CF18-01 | IMPLEMENTED | C-J | T-J | Attendee list/register/status/withdraw works for Confirmed events. |
| R-CF18-02 | IMPLEMENTED | C-J | T-J | Owning Organiser and assigned Coordinator only. |
| R-CF18-03 | IMPLEMENTED | C-J | T-J | Attendee catalogue exposes Confirmed events only. |
| R-CF18-04 | UNCLEAR | C-J | T-J | Baseline marks these extras out of scope; capacity is nevertheless implemented, while period/waitlist/attendance recording are not. |
| R-CF19-01 | IMPLEMENTED | C-K | T-K | Organiser proposes; assigned Coordinator reviews. |
| R-CF19-02 | IMPLEMENTED | C-K | T-K | Important changes trigger arrangement rechecks/flags. |
| R-CF19-03 | IMPLEMENTED | C-K, C-M | T-K, T-M | An accepted important Organiser change moves Confirmed → Planning atomically, rechecks arrangements, requires fresh Safety approval and Coordinator reconfirmation. |
| R-CF19-04 | OPEN | C-K | T-K | Current permitted fields are title, purpose, description, date/time, attendance, and all event-needs fields. |
| R-CF19-05 | OPEN | C-K | T-K | Current behavior preserves lifecycle status and does not repeat original Coordinator review approval. |
| R-CF20-01 | IMPLEMENTED | C-C, C-N | T-C, T-N | Core status, decision, booking and registration notices exist. |
| R-CF20-02 | IMPLEMENTED | C-L, C-M, C-N | T-L, T-M, T-N | Assignment/reassignment, hold, conflict, venue problem and Safety triggers notify relevant users. |
| R-CF20-03 | IMPLEMENTED | C-N | T-C, T-N | In-app channel used. |
| R-W7-1a | IMPLEMENTED | C-F | T-F | Configurable buffers. |
| R-W7-1b | IMPLEMENTED | C-F, C-G | T-G | All main availability/conflict paths use buffers. |
| R-W7-1c | IMPLEMENTED | C-F | T-G | Recheck flags without removing. |
| R-W7-1d | IMPLEMENTED | C-G | T-G | Approval rechecks buffered window. |
| R-W7-1e | OPEN | C-F | T-F | Current behavior checks advertised event/booking time against hours, not the entire buffered window; buffers may extend outside hours. |
| R-W7-2a | IMPLEMENTED | C-L | T-L | Venue Staff record typed temporary unavailability. |
| R-W7-2b | IMPLEMENTED | C-L | T-L | Existing future bookings do not block closure creation. |
| R-W7-2c | IMPLEMENTED | C-L | T-L | Event is not cancelled. |
| R-W7-2d | IMPLEMENTED | C-L | T-L | SQL flags affected bookings and notifies current Coordinator. |
| R-W7-2e | IMPLEMENTED | C-L | T-L | Event and original booking history preserved. |
| R-W7-2f | IMPLEMENTED | C-L, C-O | T-L | Search/request uses the committed atomic replacement RPC. |
| R-W7-2g | IMPLEMENTED | C-K, C-L | T-K, T-L | Closure flags/notifies; Coordinator replacement action atomically moves a Confirmed event to Planning, followed by venue/Safety/confirmation checks. |
| R-W7-2h | IMPLEMENTED | C-L | T-L | Coordinator chooses the replacement; original becomes history, other bookings remain, replacement is independently approved, then Safety/confirmation repeat. |
| R-W7-3a | IMPLEMENTED | C-G | T-G | Multiple bookings. |
| R-W7-3b | IMPLEMENTED | C-F, C-G | T-F, T-G | Independent checks. |
| R-W7-3c | IMPLEMENTED | C-G | T-G | Same event association. |
| R-W7-3d | IMPLEMENTED | C-L | T-L | Replacement/cancellation preserves other bookings. |
| R-W7-3e | IMPLEMENTED | C-G | T-G | Assigned Coordinator cancellation route. |
| R-W7-3f | IMPLEMENTED | C-G | T-G | One request per session. |
| R-W7-3g | IMPLEMENTED | C-G | T-G | Independent decisions. |
| R-W7-4a | IMPLEMENTED | C-H | T-H | Venue Staff place holds. |
| R-W7-4b | IMPLEMENTED | C-H | T-H | Expiry mandatory. |
| R-W7-4c | PARTIAL | C-H | T-H | Venue Staff set arbitrary expiry (up to booking start), but cannot update it; no PATCH/PUT route. |
| R-W7-4d | IMPLEMENTED | C-H | T-H | Effective expiry immediately frees slot; sweep records Expired. |
| R-W7-4e | IMPLEMENTED | C-H, C-N | T-H, T-N | Warning at <=24h and expiry notification. |
| R-W7-4f | IMPLEMENTED | C-H | T-H | Expired never Confirmed. |
| R-W7-4g | IMPLEMENTED | C-H | T-H | Active hold occupies slot. |
| R-W7-4h | OPEN | C-H, C-G | T-H, T-G | Current flow: Venue Staff hold an Approved/Planning event; Coordinator converts Held to Requested; Venue Staff then decide. |
| R-W7-4i | OPEN | C-H | T-H | Current warning window is 24 hours; sweep runs every 15 minutes. |
| R-W7-5a | IMPLEMENTED | C-A | T-A | Lead role/permissions exist. |
| R-W7-5b | IMPLEMENTED | C-D | T-D | Unassigned queue. |
| R-W7-5c | IMPLEMENTED | C-D, C-O | T-D | Review, initial assignment and production reassignment work. |
| R-W7-5d | IMPLEMENTED | C-A | T-A, T-D | Assignment-scoped Coordinator access. |
| R-W7-5e | IMPLEMENTED | C-A, C-D | T-A, T-D | Lead supervisory views. |
| R-W7-5f | IMPLEMENTED | C-N, C-O | T-N | Assignment and atomic reassignment notify relevant users. |
| R-W7-5g | IMPLEMENTED | C-D | T-D | No auto-assignment. |
| R-W7-5h | IMPLEMENTED | C-A, C-D | T-A, T-D | Permission model supports many Leads/full queue. |
| R-W7-5i | IMPLEMENTED | C-D, C-O | T-D | Production reassignment supports any active event, including after arrangements. |
| R-W7-6a | IMPLEMENTED | C-A, C-M | T-A, T-M | Safety Officer role exists. |
| R-W7-6b | IMPLEMENTED | C-M | T-M | Readiness gates confirmed venues/reserved equipment/no conflicts. |
| R-W7-6c | PARTIAL | C-M | T-M | Attendance, capacity/layout/accessibility/equipment/restrictions shown; no explicit emergency-access, equipment-placement or crowd-movement data. |
| R-W7-6d | IMPLEMENTED | C-M | T-M | Review is read-only; officer records decision/comment only. |
| R-W7-6e | IMPLEMENTED | C-M | T-M | Queue, review and attributable decision/comment. |
| R-W7-6f | IMPLEMENTED | C-M | T-M | Three outcomes. |
| R-W7-6g | IMPLEMENTED | C-M | T-M | Request changes returns to Planning and flags selected arrangements. |
| R-W7-6h | IMPLEMENTED | C-M | T-M | Reject returns to Planning, not terminal. |
| R-W7-6i | IMPLEMENTED | C-M | T-M | Approval notifies the assigned Coordinator, who decides when to confirm; request/reject return to planning. |
| R-W7-6j | IMPLEMENTED | C-E, C-M | T-E, T-M | Only the assigned Coordinator can confirm, and only after current Safety approval and all readiness checks. |
| R-W7-6k | UNCLEAR | C-M | T-M | Customer assumption that the officer responds is not a software behavior. |
| R-W7-6l | IMPLEMENTED | C-K, C-M | T-K, T-M | Important Confirmed changes return to Planning and require a fresh Safety decision and reconfirmation. |
| R-W7-6m | OPEN | C-M | T-M | Current behavior: assigned Coordinator explicitly sends a ready Planning event to Safety. |

## 3. End-to-end scenarios

“Product” means the code paths support the scenario. “Automated E2E” means a browser-level test can currently execute it. The isolated browser suite cannot pass login; CI runs no Playwright suite.

| ID | Product result | Automated E2E | Break point / evidence |
|---|---|---|---|
| E2E-1 | YES | NO | Product flow now separates Safety approval and Coordinator confirmation (C-E/C-M, T-E); no runnable browser scenario covers the full chain. |
| E2E-2 | YES | NO | Clarification comment and notification work (C-C, T-C); no runnable browser scenario. |
| E2E-3 | YES | NO | Rejection/outcome/notice work (C-C, T-C). |
| E2E-4 | YES | NO | 12:30 blocked and 12:45 allowed by half-open buffered window (C-G, T-G). |
| E2E-5 | YES | NO | Buffer update flags both sides without deletion (C-F, T-G). |
| E2E-6 | YES | NO | Flag/notify/preserve/replace-one and independent approval use committed code/SQL (C-L/C-O). |
| E2E-7 | YES | NO | Coordinator replacement action reopens Confirmed to Planning and requires replacement approval, Safety and reconfirmation (C-L/T-L). |
| E2E-8 | YES | NO | Warning, effective expiry and free slot work; Venue Staff still cannot amend expiry (C-H). |
| E2E-9 | YES | NO | Request-changes/re-review/fresh Safety approval/Coordinator confirmation are supported (C-M/T-M). |
| E2E-10 | YES | NO | Safety rejection returns to Planning and retains event (C-M, T-M). |
| E2E-11 | YES | NO | Accepted important change reopens Planning, rechecks, requires Safety and Coordinator reconfirmation (C-K/T-K). |
| E2E-12 | YES | NO | Organiser direct edit returns 409 and change-request route works (C-K, T-K). |
| E2E-13 | **NO** | NO | Coordinator direct edit on Confirmed returns 200 (C-K, T-K). |
| E2E-14 | YES | NO | Coordinator B receives 404; Lead sees all (C-A, T-A/T-D). |
| E2E-15 | YES | NO | Production RPC reassigns active events atomically, transfers access and notifies both Coordinators (C-D/C-N/C-O). |
| E2E-16 | YES | NO | Overlap/out-of-service stock leaves one usable unit and blocks quantity two (C-I, T-I). |
| E2E-17 | YES | NO | Equality passes; +1 and missing facility fail (C-F, T-F). |
| E2E-18 | YES | NO | Register/withdraw and manager-scoped list work (C-J, T-J). |
| E2E-19 | YES | NO | Authorization model supports two Leads sharing the queue; no browser scenario (C-A/C-D). |
| E2E-20 | YES | **NO (current suite)** | UI/API support layout list edits, but the isolated venue spec fails at login before exercising it (C-F). |

## 4. Known-risk checks

Here “Yes” means the named risk is present.

| Risk | Yes/No | Evidence and conclusion |
|---|---|---|
| Leftover auto-assignment | **No** | Submission leaves `coordinator_id` empty; `test_submissions_no_longer_auto_assign` and `test_no_auto_assignment_regardless_of_coordinators` pass (C-D/T-D). |
| Safety approval auto-setting Confirmed | **No** | Safety approval records a current approval and notifies the Coordinator; `confirm_event` is the only path into Confirmed (C-E/C-M/T-E). |
| Organiser can directly edit submitted event | **No** | `save_event` returns `change-request-required`; direct-edit refusal tests pass (C-K/T-K). |
| Confirmed fields can be edited | **Yes** | `save_event` still excludes only Completed/Rejected/Cancelled and accepts direct Coordinator edits to Confirmed (C-K/T-K). The new reflow covers accepted Organiser change requests, not direct edits. |
| No Confirmed → planning path after important change/unavailability | **No for the specified workflows** | Accepted important Organiser changes and Coordinator replacement actions now atomically move Confirmed to Planning (C-K/C-L). |
| Automatic cancellation/removal | **No cancellation**, but **automatic mutation exists** | Unavailability trigger automatically changes bookings to `Needs replacement`; it does not cancel/delete event or other bookings. Existing buffer conflicts are only flagged (C-L, T-L/T-G). This is borderline against “system should not automatically update” in R-W7-2h. |
| In-memory/Supabase drift | **Reduced, still a risk** | Focused committed RPCs and two new CI DB modules cover reassignment and confirmed replacement reflow. Many unit rules still run against fakes, 10 opt-in DB cases skip normally, and the obsolete untracked omnibus patch can reintroduce migration ambiguity (C-D/C-L/C-O). |
| Access enforced only in UI | **No** | FastAPI permission dependencies and relationship filters enforce it. However the backend uses Supabase service-role/admin access, so DB RLS is bypassed by normal API operations; API authorization remains the security boundary (C-A). |
| Setup/turnaround absent from any main path | **No** | Search, calendar, request conflict and approval use the effective window (C-F/C-G). Open caveat: buffers need not fit operating hours. |
| Expired holds still occupy/count as confirmed | **No** | Effective status frees the slot immediately, even before the sweep; Expired remains history (C-H/T-H). |
| Equipment ignores overlaps/out-of-service | **No** | Both are deducted in availability/reservation paths (C-I/T-I). |
| Dead code/duplicate rules/failures/skips/missing migrations | **Yes** | Same lifecycle/conflict logic exists in Python and SQL; 10 DB-related tests skip; obsolete repair SQL overlaps focused committed migrations; browser E2E remains absent from CI. |

Additional drift: unit tests for venue-unavailability use an in-memory store that merely records the closure; production side effects are performed by a Postgres trigger. The route tests therefore do not prove the production trigger. The committed trigger’s active-hold time comparison uses a different time basis from the untracked correction.

## 5. Deliverables check

| Deliverable visible in repo | Result | Evidence |
|---|---|---|
| README run steps | **PARTIAL** | Root/backend/frontend READMEs have setup/run/test commands and a long manual SQL list. Root says “exactly what CI runs” but omits CI’s Postgres integration command. Ruff now passes. |
| Git repo link / instructor access | **MISSING / not verifiable** | README still says `git clone <this repo>` and contains no repository URL. Access cannot be inferred from a snapshot. |
| CI pipeline and tests | **PRESENT, INCOMPLETE** | `.github/workflows/ci.yml`: Python 3.12, Ruff, compile, `pytest --cov`, four Postgres integration modules; Node 22, lint, build, Vitest coverage. No Playwright. Several opt-in `*_db.py` modules still are not in CI. |
| Traceable test-case documents | **PRESENT but partly uncommitted** | Many `backend/tests/test_cases_*.md`; `MASTER_TEST_PLAN.md` and `test-plans/` provide story/AC/manual traceability but are untracked. They do not trace directly to all 124 baseline IDs or the baseline E2E-1…20 set. |
| C4 model diagrams | **MISSING** | No C4, PlantUML, Mermaid or draw.io design artefact found in the repo snapshot. |
| Seed accounts for all seven roles | **PARTIAL** | Scripts/docs collectively cover Organiser, Coordinator, Lead, Venue Staff, Safety Officer, Technical Support and Attendee. Base three are documented as manual Supabase creation; `seed_new_users.py` seeds only Lead/Safety/Tech/Attendees. No one-command fresh seed for all roles. |
| Reproducible migrations / order | **PARTIAL** | README now lists focused US4.7/US8.4/US11.3/US12.4 migrations and CI tests the latter two, but application remains a long manual “run after” list without a versioned runner/status table. The old omnibus repair SQL is still untracked and should be removed rather than applied too. |

### Executed checks

| Check | Result |
|---|---|
| Python 3.12.5 `pytest --cov` | **2,504 passed, 10 skipped, 3 warnings** in 83.64s; backend statements/lines/branches **100%**. Skips are opt-in database tests/modules. |
| Frontend Vitest `npm test -- --coverage` | **65 files, 1,400 tests passed**; statements **100%**, lines **100%**, functions **100%**, branches **94.81%**. |
| Frontend build | **PASS** (`tsc -b && vite build`). |
| Frontend lint | **PASS with two React warnings** in `TeamAssignmentsPage.tsx`. |
| Backend Ruff/compile command | **PASS** after formatting the credential-migration line in `backend/seed_new_users.py`. |
| Isolated Playwright | **10 passed** in 13.7s. The isolated API now seeds `@connectsphere.com` / `password`, and the Safety scenario proves Safety approval followed by assigned-Coordinator confirmation. |
| CI Postgres integration | **NOT RUN LOCALLY** | Docker daemon/Postgres was unavailable. CI now runs 28 named test functions across four integration modules, including US8.4 and US12.4; parameterization may expand the collected case count. |
| Live/shared Supabase Playwright | **NOT RUN** | It writes to a shared external database and credentials were not supplied for an isolated audit. Configuration also ignores replacement-venue specs. |

The history shows sustained tests and CI work, but it also shows deleted isolated scenarios and a coverage-focused final phase. Coverage is not proof of customer behavior. The pulled release corrected the former Safety auto-confirm expectation, but the remaining duplication still needs requirement-level review.

## 6. Changes carried onto the controlled handover branch

The controlled branch preserves the former 18 modified files plus the audit/test-plan files, `backend/SUPABASE_FOUR_STORY_FIX.sql`, and `test-plans/`, then adds the isolated Playwright repair and this handover.

| Group | Files | Behavioral impact |
|---|---|---|
| Credential/domain rewrite | `README.md`, `backend/README.md`, role/equipment SQL and seed/setup/smoke scripts, frontend E2E docs/fixtures/helpers/spec, `backend/e2e_server.py` | **Yes.** Changes demo logins from `@spmg3t7.edu` / `Sprint1!demo` to `@connectsphere.com` / `password`. The isolated fixture and Ruff formatting are now aligned and verified. |
| Four-story SQL patch | `backend/SUPABASE_FOUR_STORY_FIX.sql` (untracked) | **Now obsolete and risky.** Focused committed migrations implement reassignment/reconfirmation/replacement. Applying the old omnibus bundle as well could overwrite newer functions; remove it from the submission after confirming the focused migrations contain every needed repair. |
| Test planning | `MASTER_TEST_PLAN.md`, `test-plans/` (untracked) | No runtime effect, but submission/traceability evidence disappears if omitted. |
| E2E documentation/fixtures | `frontend/E2E_AUDIT.md`, `E2E_TESTING.md`, `PLAYWRIGHT_QUICKSTART.md`, `e2e/*`, isolated venue spec | Test behavior/documentation changes; currently makes the isolated suite unusable. |
| Remaining SQL/script edits | `SUPABASE_ADD_EQUIPMENT_REQUESTS.sql`, `SUPABASE_ADD_NEW_ROLES.sql`, `TEST_US1.4...sql`, seed/smoke/setup scripts | Mainly seed identities/credentials, but these affect reproducible demo setup and must be committed consistently or reverted consistently. |

## 7. Prioritised fix list

The list is deliberately limited to work feasible in roughly three working days.

### P0 — broken MUST workflows/E2E

1. **R-CF7-03 (E2E-13): block direct Confirmed edits.** Add a server guard in `events.py::save_event` and `us11_edit`; keep all Confirmed changes on the reviewed Organiser-change path that now performs the correct reflow. Add API, SQL integration and browser refusal tests.

### P1 — partial MUSTs and notification/deployment gaps

1. **R-W7-4c:** add Venue Staff hold-expiry update endpoint/store/RPC, recheck future/max-booking-start/conflicts, and test shorter/longer/expired/race cases.
2. **R-W7-6c:** add explicit emergency access, equipment placement and crowd movement inputs or document a defensible mapping; show them in the read-only Safety review and test them.
3. **R-CF2-02:** record/validate the chosen venue-hours interpretation. If the rule is meant at venue request, clarify the AC; if initial request must comply, model the pre-agreed operating window.
4. **Production parity:** run all four CI integration modules on a clean local/CI Postgres and remove the obsolete untracked omnibus SQL after verifying the focused migrations supersede it.
5. **Browser regression:** keep the repaired isolated credential seed green; add isolated E2E-1/7/11/13/15 and Playwright to CI.

### P2 — submission and maintainability

1. Fix the Ruff line, React lint warnings, placeholder repo URL, and README’s inaccurate “exactly what CI runs” statement.
2. Commit the master/manual test plans and add mapping from all baseline IDs and E2E-1…20 to automated/manual cases.
3. Add the required C4 context/container/component diagrams and keep them versioned with design changes.
4. Replace the long manual SQL checklist with ordered migrations plus a repeatable runner/status table; provide one safe seed command for all seven roles.
5. Consolidate duplicated lifecycle/conflict rules or add parity contract tests so Python fakes cannot silently disagree with SQL.

## 8. Baseline errors

No wrong QA number or material source misstatement was found in baseline sections 2–5 after checking the Week 1/Week 4 text, Q&A rows, and both Week 7 PDFs. The baseline correctly labels synthesis/conflict items as `OPEN`, `INTERPRETATION`, `JIRA, confirm`, or `OUT OF SCOPE`.

One wording caution is worth preserving, not correcting: R-W7-2h’s “system should not automatically update” can be read more broadly than QA-22. The implementation automatically flags the affected booking as `Needs replacement` but does not choose a new venue, cancel the event, or remove other bookings. Whether the flag itself violates the clarification should be confirmed with the customer; the baseline’s Coordinator-driven approval meaning is otherwise faithful.
