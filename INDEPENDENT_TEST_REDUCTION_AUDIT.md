# Independent Test-Reduction Audit: ConnectSphere (SPMG3T7)

**Scope:** the local working tree at `/Users/ethan/Documents/GitHub/SPMG3T7`. That is branch `main` at `e2b305c` (PR #54) plus the uncommitted changes: 18 modified files, and untracked `MASTER_TEST_PLAN.md`, `backend/SUPABASE_FOUR_STORY_FIX.sql` and `test-plans/`.
**Date:** 3 Nov 2026.
**Method:** audit only. No product or test file was changed. I worked on a snapshot copy, ran every suite I safely could, and read the requirement sources and the code.
**Independence:** I recorded my own inventory, AC assessment, targets and product gaps first. Only then did I open the two earlier reports (see §12).

> **Important timing note.** `origin/main` is **4 commits ahead** of the local checkout. PR #55 (US11.3) and PR #56 (US4.7) are already merged there:
> - Safety approval no longer confirms the event; the Coordinator confirms it.
> - An accepted important change sends a Confirmed event back to Planning.
> - Two new test files were added: `test_confirm_event_us4_7.py` (27 test functions) and `test_reconfirm_us11_3.py` (19). Six existing test files were rewritten.
>
> This report audits the local tree, as instructed. Where `origin/main` already fixes a finding, the finding is marked **[fixed on origin/main]**. **Pull before pruning.** The pruning plan applies to the pulled tree, and the two new files need the same treatment (targets in §5).

---

## 1. Executive summary

- **Size today:**
  - 2,394 backend pytest cases, plus 37 opt-in DB test functions that never run in CI
  - 19 Postgres integration cases
  - 1,361 Vitest cases
  - 43 Playwright tests

  That is about **3,850 automated cases**. Five students can't honestly review that in a day.
- **Results:**
  - Backend: 2,386 passed and 10 skipped, at 100% line and branch coverage (Python 3.12.3).
  - Integration: 19/19 passed against local Postgres 16.
  - Vitest: 1,361/1,361 passed. Branch coverage is 94.62%.
  - Isolated Playwright: **0/10 passed** on the current tree. The uncommitted credential rename broke sign-in. On the committed fixtures, 10/10 pass.
  - Ruff **fails** on the current tree (`seed_new_users.py:76`, E501), so CI would go red before pytest runs.
- **Most of the volume isn't distinct behaviour.**
  - 639 backend cases are parametrised copies of one equivalence class (for example, 42 malformed-date variants in a single file).
  - Name patterns flag about 540 role/permission cases, about 220 not-found/malformed-ID cases and about 90 blank/whitespace cases. These overlap with the parametrised cases.
  - 207 backend store/plumbing cases and 138 frontend `*.paths`/`*.calls`/route-coverage cases mainly re-execute code the feature tests already reach.
  - Many rules are tested again at five levels: helper, route, store, component and page.
- **Some tests prove the wrong thing.** Several suites pass while asserting behaviour that contradicts the later customer clarifications:
  - Safety approval auto-confirms the event. [fixed on origin/main]
  - An accepted change keeps the event Confirmed. [fixed on origin/main]
  - A Coordinator can edit a Confirmed event.
  - Reassignment works only in the in-memory fake. Production calls an RPC that refuses already-assigned events.
  - Holds can't be updated by Venue Staff.

  These tests need **rewriting, not deleting**.
- **The most valuable tests are the least run.** The database tests are the only proof of registration capacity under concurrency, the hold-expiry sweep, triggers and constraints. 37 of them are opt-in and never run in CI. No Playwright test runs in CI.
- **Proposed target:** about **570 retained tests**, plus about 12 to rewrite or add. It was derived file by file from distinct behaviours and risks, not from a round number:
  - backend unit/API: 339
  - opt-in DB tests (to be made runnable): 19
  - CI integration: 14
  - Vitest: 186
  - isolated Playwright: 12

  That's about 114 tests per person, roughly 5 hours of reading plus 1 hour of running and ledger work.
- **Coverage will drop.** 100% branch coverage can't be kept honestly at this size. I recommend an 85–90% line gate on `backend/app`, no branch gate, and documented exclusions (§8).

## 2. Current test inventory and executed results

### 2.1 Repository state

| Item | Value |
|---|---|
| Branch / HEAD | `main` @ `e2b305c` (Merge PR #54 `test/coverage-100`) |
| Behind `origin/main` | 4 commits: PR #55 US11.3, PR #56 US4.7 |
| Modified (uncommitted) | `README.md`, `backend/README.md`, 3 SQL files, `scripts/smoke_test_live.py`, `seed_equipment.py`, `seed_new_users.py`, `setup_new_roles_complete.py`, 4 frontend docs, `e2e-isolated/venue-delete-us9-5.spec.ts`, `e2e/ARIEL-README.md`, `e2e/ariel-fixtures.ts`, `e2e/helpers.ts`, `e2e/replacement-fixtures.ts` |
| Untracked | `MASTER_TEST_PLAN.md`, `backend/SUPABASE_FOUR_STORY_FIX.sql` (the only definition of `request_replacement_venue` and `reassign_event_coordinator`), `test-plans/`, and the two earlier audit reports |
| Behavioural effect of the uncommitted work | Demo credentials change from `@spmg3t7.edu` / `Sprint1!demo` to `@connectsphere.com` / `password`, but the isolated E2E backend still seeds the old ones, so all isolated E2E tests break. One line in `seed_new_users.py` breaks Ruff. Without `SUPABASE_FOUR_STORY_FIX.sql`, production replacement-venue requests fail, because the app calls an RPC defined nowhere else. |

### 2.2 Backend (Python 3.12.3, temporary venv, `pip install -r requirements-dev.txt`)

| Measure | Result |
|---|---|
| `pytest --collect-only` (tests/) | **2,394 collected** = **1,755 named test functions** + **639 parametrised expansions** |
| `pytest --cov` | **2,386 passed, 0 failed, 10 skipped**; 100% statements (5,384) and 100% branches (1,176); `fail_under = 100` |
| The 10 skips | `test_hold_expiry_db.py` (module skip, 3 functions) and `test_registration_db.py` (module skip, 34 functions) need `SPMG3T7_DB_TESTS=1` and a live database, so I **did not run them**. `test_equipment_item_migration_db.py` (4) and `test_equipment_reservations_db.py` (4) need `US19_DB_TEST_URL`. Locally, the 4 migration tests **passed**. The 4 reservation tests **errored** (`relation "users" does not exist`): they need a fully migrated schema, and the migration order isn't scripted. |
| Integration (`backend/integration/`, local Postgres 16, `TEST_POSTGRES_DSN`) | **19 passed**: `test_change_review_db.py` 12, `test_unavailability_db.py` 7 |
| Ruff | **FAIL**: `seed_new_users.py:76` E501 (101 > 100), an uncommitted edit |

**Backend cases by group** (calculated from the collect output):

| Group | Files | Cases |
|---|---:|---:|
| Feature/API story tests | 44 | 2,115 |
| Store/plumbing (`*_store*.py`, `test_supabase_config.py`, `test_config.py`, `test_event_store_queries.py`) | 11 | 207 |
| Generic guard/coverage (`test_remaining_guards.py`, `test_event_route_guards.py`, `test_change_review_paths.py`) | 3 | 59 |
| DB-backed in tests/ (skipped or opt-in) | 4 | 8 collected (+37 functions in module-skipped files) |
| Small infra (`health`, `security`, `seed_equipment`) | 3 | 5 |
| Integration (`backend/integration`) | 2 | 19 |

Per-file counts are in §5 and Appendix A.

### 2.3 Frontend

| Measure | Result |
|---|---|
| `npm test -- --coverage` (Vitest) | **1,361 passed** in **65 files**. Coverage: statements 100%, lines 100%, functions 100%, **branches 94.62%**. Thresholds are 100/100/100/94. |
| `*.paths.test.*` / `*.calls.test.*` / route-coverage | 7 files, 118 cases; with `App.routes.test.tsx`, 138 |
| Store tests (`*Store*.test.ts`, excluding `.calls`) | 9 files, 203 cases |

### 2.4 Playwright

| Config | Files | Tests | Target | Run? | In CI? |
|---|---|---:|---|---|---|
| `playwright.config.ts` (shared/live Supabase) | `authentication` 11, `coordinator-lead-assignment` 11, `ariel-events` 3, `ariel-catalogues` 3, `ariel-equipment` 2, `change-review-us11-2` 1 (plus parametrised loops) | **33** listed | Live shared Supabase | **Not run.** They write to the shared live database; no isolated credentials were authorised. | No |
| same config, `testIgnore` | `replacement-venue-us14-5.spec.ts` 2, `replacement-venue-us14-5-comprehensive.spec.ts` 3 | 5 (ignored) | Live | Not run | No |
| `playwright.isolated.config.ts` | `safety-check-us17` 5, `venue-delete-us9-5` 5 | **10** | `backend/e2e_server.py` (in-memory) on :8001 + Vite on :5174 | **Run:** 0 passed / 10 failed on the current tree (sign-in); **10/10 passed** with HEAD fixtures | No |

Two shared specs have conditional bodies that pass without testing the feature:
- `US8.3 … (if events exist)` passes as soon as the page heading renders.
- `US8.4 … reassign` skips its assertions when the button is hidden.

### 2.5 What CI actually executes (`.github/workflows/ci.yml`)

- **Backend:**
  1. `ruff check`
  2. `compileall`
  3. `pytest --cov` (100% gate)
  4. `integration/test_unavailability_db.py` and `integration/test_change_review_db.py` against a Postgres 16 service
- **Frontend:** lint, build, `npm test -- --coverage`.
- **Not in CI:** any Playwright test, the opt-in DB modules, the equipment DB tests, and the replacement/reassignment SQL.

The README's claim that this is "exactly what CI runs" is accurate only for the steps listed above.

---

## 3. Acceptance-criteria versioning and conflicts

Precedence used: Customer Q&A (QA-n = row n under the header in `Customer QA Clarifications.tsv`) and Week 7 > Week 4 > current/reopened Jira AC (`MASTER_TEST_PLAN.md`) > superseded AC > comments.

| # | Topic | Historical AC | Current requirement (source) | Code today (local tree) | Verdict | Effect on tests |
|---|---|---|---|---|---|---|
| C1 | Coordinator assignment | US8.1 AC1–5: auto round-robin on submit | Lead assigns manually; no system auto-assignment (QA17; US8.2 AC1) | Auto-assign removed; a submitted event stays unassigned (`test_coordinator_assignment.py` asserts this) | US8.1 **SUPERSEDED** | Keep **one** regression ("submission leaves no coordinator"). Delete the other six no-auto-assign variants. |
| C2 | Who may act on an event | US5.2 AC3, US7.1 AC5, US7.3 AC5: "any Coordinator for now" | Only the assigned Coordinator; the Lead sees all (US8.6; QA) | Assignment-scoped (`_readable`, relationship filters) | Early ACs **SUPERSEDED** | Keep scoped tests. Any test that lets an unassigned Coordinator act is stale. None found that asserts the old rule. |
| C3 | Event form fields | US2.1 AC2: only name/purpose/date/time/attendance required; others optional | US2.1 reopened AC1–5: needs fields mandatory, fixed lists, "None / Not required" | Reopened rule is implemented (`event_needs.py`) | US2.1 original **SUPERSEDED** in part (AC1/AC3 still hold) | Remove tests that submit with needs fields blank. Keep the draft exception. |
| C4 | Room layouts | Fixed `LAYOUT_OPTIONS` list (US2.1r AC2) | Venue Catalogue must support add/edit/delete of layouts (QA1) | Hard-coded tuple `event_needs.LAYOUT_OPTIONS`; the venue holds free-text layouts | **PARTIAL** | The `test_event_needs.py` param tables lock in the hard-coded list. Rewrite when layouts become catalogue data. |
| C5 | Safety approval vs confirmation | US4.4 AC2 and US17.2 AC1: Safety approve → Confirmed | Coordinator marks Confirmed once all approvals are in; Safety approval comes before that (QA8, QA5) | `OUTCOME_STATUS[APPROVED] = CONFIRMED` | **CONTRADICTS CUSTOMER** [fixed on origin/main by US4.7] | `test_approval_confirms_the_event` (US4.4 and US17.2 files), `SafetyCheckPanel` approve tests and the isolated E2E all assert the wrong rule. **Rewrite.** |
| C6 | Editing a Confirmed event | US5.2 AC1: Coordinator general edit | Once Confirmed, fields can't be changed directly (QA7) | `save_event` blocks only Completed/Rejected/Cancelled | **CONTRADICTS CUSTOMER** (still open on origin/main) | No test asserts a refusal. `test_coordinator_can_edit_any_event` has no Confirmed case. **Add or rewrite.** |
| C7 | Change after Confirmed | US11.2 AC2: accept applies values; status preserved (US4.5 AC4) | Date/time/attendance change after Confirmed → change process; all checks again, then re-confirm (QA14) | Accept keeps Confirmed and only flags arrangements | **CONTRADICTS CUSTOMER** [fixed on origin/main by US11.3] | `test_change_review_us11_2.py::test_request_question_revision_and_accept_preserve_status[Confirmed]` asserts the wrong rule. **Rewrite.** |
| C8 | Venue unavailable after booking | US12.2 AC4: event status unchanged | W7#2: don't cancel; flag affected bookings; inform the Coordinator. QA12: for a **Confirmed** event, notify stakeholders and revert to planning/change review. | Trigger flags bookings "Needs replacement"; event stays Confirmed; no Coordinator revert action | **PARTIAL** (right for non-confirmed events, missing for Confirmed) | Keep the flagging tests. Add one test for the Confirmed revert once it exists. |
| C9 | Venue deletion | US9.1c AC1: hard delete, no referential check | US9.5: blocked when future active bookings exist | US9.5 implemented | US9.1c **SUPERSEDED** | Remove hard-delete-with-bookings assumptions. Keep "no bookings → delete" and "future booking → blocked". |
| C10 | Hold expiry | US14.3 AC2: expiry set at placement; AC6 assumes Venue Staff place holds | Venue Staff set **and update** the duration (QA23). Hold starts **after** venue approval; the Coordinator then confirms (QA19, QA30). | Hold is a new booking placed by Venue Staff **before** a request (Held → Requested → Confirmed). No update or release route (`holds.py` has GET/GET/POST only). | **CONTRADICTS CUSTOMER** (order) + **PARTIAL** (update) | Tests of the Held → Requested conversion encode the team's order. Keep them until the flow changes; add an update test when the route exists. |
| C11 | Reassignment | US8.4 AC1: Lead can change the Coordinator on any active event | Lead can reassign, even after arrangements are confirmed (QA25) | Route allows it. In-memory fake allows it. **Supabase store calls `assign_event_coordinator`, which only updates `status='Submitted' AND coordinator_id IS NULL`**. `reassign_event_coordinator` exists only in the untracked SQL file, and nothing calls it. | **PRODUCTION DRIFT** (still open on origin/main) | All 14 `test_lead_reassignment.py` tests pass against the fake. `test_lifecycle_us4_5.py` checks the initial-assign RPC name only. No test exercises production. **Add a DB test.** |
| C12 | Notifications | US10.1 AC1: notify on Under Review/Approved/Rejected | W4/QA: stakeholders informed at key points | Organiser notified only for those three; no Confirmed notice [added on origin/main]; no "new submission" notice to Leads | **PARTIAL** against the customer; **ALIGNED** with the Jira AC | Keep one notification test per trigger family, not per permutation. |
| C13 | Equipment availability | US19.3: overlap and out-of-service maths | QA: "for release one, you can assume that it is available if it is in the catalogue" | Full availability maths implemented | **ALIGNED** (goes beyond the customer's minimum) | Keep the customer-style example (10 − 2 − 6 = 2). |
| C14 | US4.5 AC4 | Change request on Approved/Planning keeps status | Still current for pre-Confirmed events | Implemented | **ALIGNED** | Keep, but the `[Confirmed]` parameter falls under C7. |

**Baseline / Jira AC errors to correct in the traceability document:**
- US4.4 AC2 and US17.2 AC1 (C5).
- US5.2 AC1, which says nothing about the Confirmed lock (C6).
- US12.2 AC4, which needs a Confirmed-event exception (C8).
- US14.3 AC6, which is still marked "assumption" although QA23 answered it.

---

## 4. Story-by-story audit

Retained counts are written **B/F/D/E**: backend unit/API, Vitest, DB (CI integration or opt-in DB), Playwright.

**Overlap rule.** A test is counted once, under the story that owns it. Shared tests (permission matrix, stale-race guard, notification-failure guard) are counted under US1.3, US4.2 and US10.1 or US10.2, and only referenced elsewhere. The sum of the story counts (≈571) differs from the per-file totals in §5 (≈570) by rounding in the cross-cutting rows.

### 4.1 Summary table

| Story | Current AC summary | AC status | Implementation result | Automated evidence | Redundancy/problems | Recommended retained tests |
|---|---|---|---|---|---|---|
| **E1 US2.1** Create & submit (original) | Form captures fields; submit requires name/purpose/date/time/attendance; row written | **SUPERSEDED** (AC2 by US2.1r); AC1/AC3 still current | Submit validation lives in `events.py` + `event_needs.py` | `test_events.py`, `test_event_needs.py`, `NewEventPage.test.tsx`, `draftRules.test.ts`, `ariel-events.spec.ts` (live) | The same required/end>start/positive-attendance rules are tested in `draftRules`, `NewEventPage`, `test_events` and `test_event_needs` | 4/2/0/0: create persists as Draft; submit moves to Submitted with history; end ≤ start refused (boundary); past date refused |
| **E2 US2.2** Save & resume draft | Draft distinct from Submitted, hidden from Coordinators; partial accepted; reopen; submit = full validation | **ALIGNED** | Implemented | `test_events.py`, `test_draft_store.py` (1), `draftRules.test.ts`, `NewEventPage.test.tsx` | `test_draft_store` is a single store-shape test (merge) | 4/3/0/0: partial draft saves; Coordinator gets 404 on a draft; owner reopens; resumed submit validated |
| **E3 US3.1** View my events | Only own events; name+status; open detail; drafts editable, submitted read-only | **ALIGNED** | Implemented | `test_events.py`, `test_access_enforcement.py`, `EventsPage.test.tsx`, `EventDetailPage.test.tsx` | Read-only checks repeated in `EventDetailPage.paths` | 3/3/0/0: other Organiser's event invisible; list shows status; submitted detail is read-only |
| **E4 US2.1 (reopened)** Mandatory fields & set options | Needs fields required on submit; fixed lists match catalogue; "None / Not required"; drafts exempt | **PARTIAL** (C4: layouts must be catalogue-managed) | Lists hard-coded in `LAYOUT_OPTIONS` | `test_event_needs.py` (89; 50 param expansions), `eventNeeds.test.ts` (30), `EventNeedsFields.test.tsx`, `NewEventPage.test.tsx` | Every list value tested individually at helper, route and component level | 8/6/0/1: each list (one valid, one invalid); Not required accepted; missing field blocks with message; draft exempt; **E2E-1 submit flow** |
| **E5 US7.3** Clarification | Coordinator asks; Organiser responds; history; AC5 "any Coordinator" | AC1–4 **ALIGNED**; AC5 **SUPERSEDED** (US8.6) | Implemented | `test_event_clarification.py` (34), `EventClarification.test.tsx` (19) | 9 role-style denials | 6/3/0/0: assigned Coordinator asks (note required, limit); Organiser notified; Organiser answers through a change request; unassigned Coordinator refused; history row |
| **E6 US7.1** Review decision | Approve/reject Under Review; reject needs reason; AC5 any Coordinator | **ALIGNED** (AC5 **SUPERSEDED**) | Implemented, atomic RPC | `test_event_decisions.py` (53; 30 params), `EventDecision.test.tsx`, `ariel-events.spec.ts` | Role × status parametrisation | 6/3/0/1: approve; reject with reason; reject without reason refused; only Under Review; only assigned; stale race |
| **E7 US4.3** Submitted → Under Review → Approved/Rejected | Valid transitions only | **ALIGNED** | `VALID_TRANSITIONS` | `test_safety_check_us4_4.py::TestOnlyWayToConfirmed` (22), `status.test.ts` (63) | Full 10 × 10 matrices in Python and TS | 4/3/0/0: one table test of the allowed set; one refused transition with message; UI label table |
| **E8 US10.1** Notifications | Notice on Under Review/Approved/Rejected; unread first; toggle read; in-app only | **ALIGNED** (customer-level **PARTIAL**, C12) | Implemented | `test_notifications.py` (23), `test_notification_store.py`, `NotificationsPage.test.tsx` (22) | Notice-write-failure tested in ~6 feature files | 5/4/0/0: notice created per trigger (1 table); own notices only; mark read; unread first; **one shared write-failure test** |
| **E9 US11.1** Organiser change request | Owner proposes on submitted event; important flag; one pending; no direct edit | **ALIGNED** | Implemented | `test_change_requests.py` (186; 73 params), `EventChangeRequest.test.tsx` (44) | 23 + 6 validation params, label/order trivia, 5 status params | 12/4/0/0: propose → flag set and event unchanged; owner only; draft/closed refused; one pending; no-op refused; note limit; important vs routine (1 table); validation invalid + boundary; stale race |
| **E10 US11.2** Coordinator processes change | Accept applies + logs + notifies; reject needs reason; recheck bookings/equipment; flag "Conflict – review needed"; nothing cancelled | **ALIGNED** for pre-Confirmed; **CONTRADICTS CUSTOMER** for Confirmed (C7) [fixed on origin/main] | Atomic RPCs; recheck in `arrangement_review.py` | `test_change_review_us11_2.py` (36), `test_change_review_paths.py` (20), `test_change_requests.py`, `integration/test_change_review_db.py` (12), `change-review-us11-2.spec.ts` (live) | Status-preservation parameters include `[Confirmed]`; paths file is coverage-only | 14/4/8/1: accept/reject; recheck flags venue, equipment and pending; stale recheck can't clear newer marker; **DB: concurrent decisions, rollback, SQL safety guard**; **rewrite [Confirmed] → Planning**; E2E-11 |
| **E11 US4.6** Cancel event | Owner or assigned Coordinator cancels with reason; releases arrangements; notifies; final | **ALIGNED** | Implemented | `test_cancel_event_us4_6.py` (104), `CancelEventPanel.test.tsx` (22) | Per-status ×8, per-role ×5, notification permutations | 12/4/0/0: who may; reason required; closed refuse (1 table); bookings/holds/equipment released; registrations closed; affected told, not the canceller; notice failure doesn't undo; nothing reopens; race |
| **D1 US1.1** Login | Valid sign-in; invalid refused; role landing | **ALIGNED** | Implemented | `test_auth_login.py` (17), `test_sessions.py`, `SignInPage.test.tsx`, `authentication.spec.ts` (live) | Wrong password and unknown email both tested in browser and API | 5/4/0/1: success; wrong password; unknown email gives the same message; disabled/deleted account; role landing; **E2E sign-in** |
| **D2 US1.2** Logout | Session invalidated; protected pages need sign-in | **ALIGNED** | Implemented | `test_auth_logout.py` (9), `useIdleSignOut.test.ts`, `App.test.tsx` | Multiple post-logout routes | 3/2/0/0: token revoked; reuse gives 401; idle sign-out |
| **D3 US5.1** Coordinator views event | Assigned Coordinator sees all fields | **ALIGNED** (AC "any" **SUPERSEDED**) | Implemented | `test_events.py`, `EventDetailPage.test.tsx` | — | 3/2/0/0 |
| **D4 US5.2** Coordinator edits | General edit; important vs routine log | **CONTRADICTS CUSTOMER** (C6: Confirmed must be locked) | Edits allowed in Pending Safety Check and Confirmed | `test_events.py` (5 per-field tracking tests) | Per-field tracking tests duplicate one classification rule | 8/3/0/0: edit + important/routine (1 table); end>start; assigned only; **ADD: Confirmed edit refused (409)**; UI hides edit on Confirmed |
| **D5 US12.1** Mark unavailability | Staff record date range + reason | **ALIGNED** | Implemented | `test_venue_unavailability.py` (148; 65 params), `test_venue_unavailability_store.py` (32), `VenueUnavailability.test.tsx` (43) | 24 date-format + 18 calendar params; 404 ×10; per-role denials | 8/3/0/0: record; reason enum; Other needs text; limit; end ≥ start; one malformed date; 404 venue; staff-only |
| **D6 US12.2** Flag affected bookings | Active bookings overlapping (with buffers) → Needs replacement; event untouched; Coordinator notified once; count shown | **PARTIAL** (C8) | Done by a Postgres trigger; unit tests use a fake that only records the range | `test_venue_unavailability.py`, `integration/test_unavailability_db.py` (7), `VenueUnavailability.test.tsx` | **The unit tests don't prove the production trigger.** Only the integration file does. | 6/2/4/1: API count response; **DB: flagged once, decisions preserved, midnight boundaries, reason reaches notice**; E2E-7 once the Confirmed revert exists |
| **D7 US14.5** Replacement venue | Search free venues; new request; old → Replaced; others untouched | **ALIGNED** in code; **PRODUCTION DRIFT** risk (RPC `request_replacement_venue` exists only in untracked SQL) | Implemented | `test_replacement_venue_us14_5.py` (28; 18 params), `EventBookings.replacement.test.tsx`, two ignored E2E specs | Param repetition; E2E ignored | 6/3/0/1: only from Needs replacement; only free venues listed; new request + Replaced; others untouched; closed event refused; **un-ignore one isolated E2E** |
| **D8 US9.5** Block delete with future bookings | Blocked with message; otherwise delete | **ALIGNED** | Implemented | `test_venue_delete_us9_5.py` (30), `venue-delete-us9-5.spec.ts` (isolated, 5) | 5 isolated E2E for one rule | 5/1/0/1: future active blocks; past/cancelled don't; message; staff-only; **1 E2E** |
| **D9 US12.3** Availability view | Calendar of bookings/unavailability with full window | **ALIGNED** | Implemented | `test_venue_availability_us12_3.py` (37), `VenueAvailability.test.tsx` (28) | — | 5/4/0/0 |
| **D10 US20.1** Register | Coordinator opens with capacity; Attendees see Confirmed only; one per Attendee; full blocked; **DB-enforced last place**; full notice | **ALIGNED** | Python + SQL trigger/index | `test_registration_us20_1.py` (122), `test_registration_store.py` (34), `test_registration_db.py` (34 opt-in, **never in CI**), `EventRegistration.test.tsx`, `AttendPage.test.tsx` | Role params ×5/×6, email params; **the concurrency proof isn't run** | 14/6/7/0: open rule (1 table); capacity default and ≥ taken; assigned only; privacy (no planning data); register; one per attendee; full; full notice once; **DB: two at once → one wins; trigger refuses over-capacity; unique index** |
| **D11 US20.2** View & withdraw | Withdraw frees place; history kept; too late after start | **ALIGNED** | Implemented | `test_registration_us20_2.py` (45), `test_registration_db.py`, `MyRegistrationsPage.test.tsx` | — | 6/4/3/0 |
| **D12 US20.3** View registrations | Organiser and assigned Coordinator see; others blocked; Attendee privacy | **ALIGNED** | Implemented | `test_registration_us20_3.py` (29; 21 role-style) | Per-role denials | 5/2/0/0: owner sees; assigned sees; permission matrix row; Attendee can't list others |
| **I1 US6.1** Setup/CI | Repo, CI pipeline | **MANUAL/DELIVERABLE** | CI exists; Ruff currently red; no Playwright in CI | `test_health.py`, `test_config.py`, `test_supabase_config.py` | Config trivia | 3/2/0/0: health; config fails fast when env is missing; CORS/security headers |
| **I2 US6.2** Core schema | Tables, constraints | **MANUAL/DELIVERABLE** | Migration order is documented in prose only | `test_equipment_item_migration_db.py`, integration files | — | 2/0/2/0 |
| **I3 US4.1** View status | Status label shown | **ALIGNED** | Implemented | `status.test.ts`, `StatusBadge`, `StatusTimeline` | 63 status-helper cases | 3/5/0/0 |
| **I4 US4.2** Status transitions logged | Timestamped and attributable; save never moves status | **ALIGNED** | Implemented | `test_events.py`, `test_lifecycle_us4_5.py` | — | 5/1/0/0: history row on transition; save leaves status; **shared stale-race test (counted here)** |
| **I5 US9.1a** Create venue | Staff create with required fields | **ALIGNED** (layouts **PARTIAL**, C4) | Implemented | `test_venues.py` (81), `VenueFormPage.test.tsx` (42), `venuesStore.test.ts` (63) | Field-by-field validation at 3 levels | 6/5/0/0 |
| **I6 US9.1b** Update venue | Staff edit | **ALIGNED** | Implemented | same | — | 3/2/0/0 |
| **I7 US9.1c** Delete venue | Hard delete, no referential check | **SUPERSEDED** by US9.5 | Replaced by the US9.5 guard | `test_venues.py` delete tests | Duplicates US9.5 | 0/0/0/0 (owned by D8) |
| **I8 US14.3** Tentative hold | Staff hold with future expiry; counts as taken; → Requested before expiry; never Confirmed | **CONTRADICTS CUSTOMER** (order, C10) + **PARTIAL** (no update) | Implemented as the team designed it | `test_venue_holds.py` (75), `holdsStore.test.ts` (20), `VenueHolds.test.tsx` | TC-H permutations | 10/4/0/0: place; expiry required and future; slot taken; → Requested; expired can't convert; never Confirmed; no-coordinator refused; **ADD: staff update/release** |
| **I9 US14.4** Hold expiry | Sweep ≤ 15 min; Expired frees slot; warn and notify; history | **ALIGNED** | pg_cron sweep (SQL) + effective-status read | `test_hold_expiry_us14_4.py` (18), `test_hold_expiry_db.py` (3, **never in CI**) | Sweep only proven by the opt-in DB file | 6/2/3/0 |
| **I10 US8.4** Lead reassigns | Any active event; both notified; old loses access; logged | **PRODUCTION DRIFT** (C11) + **PARTIAL** (AC2: `notify_reassigned` is defined and unit-tested but **never called** by `POST /events/{id}/reassign`; still true on origin/main) | Production RPC refuses assigned events and raises an unhandled `StaleEventStatus`; no reassignment notices | `test_lead_reassignment.py` (14, fake only), `test_coordinator_notifications.py` (calls the helper directly), `coordinator-lead-assignment.spec.ts` (live, conditional) | Passes for the wrong reason: `test_reassignment_is_recorded_in_history` asserts `len(after) >= len(before)`, which is always true. The E2E skips its assertions when the button is hidden. | 6/2/0/1: **rewrite** with a Planning/Confirmed event; old Coordinator loses access; both notified; history; **ADD DB test of the Supabase path**; one non-conditional E2E |
| **I11 US8.5** Lead sees all | Read-only overview | **ALIGNED** | Implemented | `TeamAssignmentsPage.test.tsx` | — | 2/2/0/0 |
| **I12 US4.5** Missing transitions | Assign → Under Review; first booking → Planning; Complete after end; change keeps status | **ALIGNED** (AC4 limited by C7) | Implemented | `test_lifecycle_us4_5.py` (18) | RPC-name test is used as if it proved reassignment | 6/2/0/0 |
| **L1 US1.4** New roles | Lead and Safety Officer roles exist and route | **ALIGNED** | Implemented | `test_new_role_auth.py`, `permissions.test.ts`, `test_lead_rls.py` | — | 3/2/0/0 |
| **L2 US8.1** Auto-assign | Round-robin | **SUPERSEDED** (C1) | Removed | `test_coordinator_assignment.py` (7 negatives) | 6 redundant negatives | 1/0/0/0 |
| **L3 US8.2** Unassigned queue | Lead sees unassigned; search | **ALIGNED** | Implemented | `test_unassigned_queue.py`, `UnassignedQueuePage.test.tsx`, `unassignedQueueStore.test.ts` | — | 3/4/0/0 |
| **L4 US8.3** Lead assigns | Assign → Under Review; Coordinator notified | **ALIGNED** | Implemented (atomic RPC) | `test_lead_assignment.py` (11), live E2E (conditional) | E2E passes without assigning | 5/2/0/1 |
| **L5 US8.6** Assignment scoping | Only assigned; unassigned invisible; clear block; Lead sees all; RLS | **ALIGNED** at API; AC5 "RLS" is **PARTIAL** (service-role key bypasses RLS; API is the real boundary) | Implemented | `test_access_enforcement.py`, `test_lead_rls.py`, `test_event_route_guards.py` | Per-route denials | 8/2/0/0: one role × route matrix (counted under US1.3) plus scoped read/edit/decide/clarify/book |
| **L6 US19.0** Seed equipment | Seeded with out-of-service units | **MANUAL/DELIVERABLE** | Seed script | `test_seed_equipment.py` | — | 1/0/0/0 |
| **L7 US19.1** Equipment catalogue | Tech Support CRUD | **ALIGNED** | Implemented | `test_equipment.py`, `EquipmentPage.test.tsx`, `equipmentStore.test.ts` | — | 5/4/0/0 |
| **L8 US19.2** Request equipment | Assigned Coordinator requests; Tech Support notified | **ALIGNED** | Implemented | `test_equipment.py`, `EventEquipment.test.tsx` | — | 5/5/0/0 |
| **L9 US19.3** Availability & reserve | total − out-of-service − overlapping reserved; shortfall shown; notify | **ALIGNED** (C13) | Python + SQL | `test_equipment_reservations.py` (26), `test_equipment_reservations_db.py` (4, errors locally), `integration/test_change_review_db.py::test_sql_reservation_peak_demand` | DB file can't run without a documented migration order | 8/6/5/1: customer example 10/2/6 → 2; shortfall blocks; Unavailable path; notify; **DB peak demand + concurrent reserve** |
| **L10 US4.4** Pending Safety Check | Planning → PSC when ready; PSC → Confirmed/Planning; no other route to Confirmed | **CONTRADICTS CUSTOMER** (AC2, C5) [fixed on origin/main] | Readiness gate correct; approval auto-confirms | `test_safety_check_us4_4.py` (111; 20-case matrix), `SafetyCheckPanel.test.tsx` (51), `safety-check-us17.spec.ts` (isolated) | Decision tests duplicated with the US17.2 file; RPC-shape tests | 10/4/1/1: readiness rule (6 distinct blockers); assigned-only send; race; queue order; Confirmed only via Coordinator confirm after approval; **E2E-9** |
| **L11 US17.1** Safety queue | Officer sees pending, oldest first, details | **ALIGNED** | Implemented | `test_safety_review_us17_1.py` (37), `SafetyReviewDetails`, `SafetyReviewPage` | Role params | 6/3/0/0 |
| **L12 US17.2** Safety decision | Approve; request changes (note, flags, notify); reject (reason); audit; fresh decision | **CONTRADICTS CUSTOMER** (AC1, C5) [fixed on origin/main] | Approve → Confirmed | `test_safety_decision_us17_2.py` (92), isolated E2E | Outcome × role parametrisation | 11/5/0/1: three outcomes; notes required; flags + notify; officer-only; pending-only; decided-twice; audit; fresh decision after resend; **rewrite approve** |
| **A1 US1.3** Access enforcement | 401/403/404 consistently | **ALIGNED** | Implemented | `test_access_enforcement.py` (20), `permissions.test.ts` (43), `App.routes.test.tsx` (20), `authentication.spec.ts` | One denial per role per route at three layers | 6/4/0/0: **one parametrised role × route matrix**; 401 when signed out; 404-not-403 for others' events; UI route guard table |
| **A2 US9.0** Seed venues | Sample venues | **MANUAL/DELIVERABLE** | Seed SQL | — | — | 1/0/0/0 |
| **A3 US9.2** Catalogue | List venues with details | **ALIGNED** | Implemented | `test_venues.py`, `VenuesPage.test.tsx` (32) | — | 3/5/0/0 |
| **A4 US9.3** Search/filter | Capacity, layout, facilities, time | **ALIGNED** | Implemented | `test_venue_search_filters.py` (19), `VenuesPage.test.tsx` | — | 5/3/0/0 |
| **A5 US9.4** Setup/turnaround | Configurable non-negative minutes | **ALIGNED** | Implemented | `test_venue_turnaround.py` (93; 43 params), `venueTurnaround.test.ts` (36) | Boundary param repetition | 6/4/0/0 |
| **A6 US14.1** Multi-venue booking | Several bookings; each checked independently; assigned only | **ALIGNED** | Implemented | `test_venue_bookings.py` (64), `EventBookings.test.tsx` (74) | 15 UI error permutations | 9/7/0/0 |
| **A7 US18.1** Suitability | Capacity/layout/facilities/accessibility per booking | **ALIGNED** | Implemented | `test_suitability.py` (53) **and** `test_venue_suitability.py` (41) | **Two files test the same rule** | 9/3/0/0 (after merging) |
| **A8 US14.2** Cancel one booking | Assigned Coordinator; others untouched; slot freed | **ALIGNED** | Implemented | `test_venue_booking_cancellation.py` (34) | Per-role denials | 7/3/0/0 |
| **A9 US16.1** Approve/reject booking | Oldest first; approve re-checks conflict; reason; notify | **ALIGNED** | Implemented | `test_booking_decisions.py` (57), `BookingRequestsPage.test.tsx` | — | 8/4/0/0 |
| **A10 US15.1** Conflict window | (start − setup) to (end + turnaround); customer example; held/requested/confirmed count; touching allowed | **ALIGNED** | Python + SQL | `test_booking_conflicts.py` (84, TC-F numbered) | Many near-identical TC-F cases | 10/3/0/0: **customer example 10:00–12:00 → 09:30–12:45**; statuses that count and don't; unavailability blocks; message names clash; touching allowed |
| **A11 US15.2** Re-flag after change | Recheck future bookings; flag, don't delete; notify | **ALIGNED** | Implemented | `test_booking_conflicts.py`, `BookingConflictsPage.test.tsx` | — | 6/3/0/0 |
| **A12 US10.2** Coordinator notifications | Assign/reassign, hold, decision, conflict, safety | **ALIGNED** (reassign notices depend on C11) | Implemented | `test_coordinator_notifications.py` (20) | One test per permutation | 6/2/0/0: one per trigger family |

### 4.2 Gaps that passing unit tests hide

1. **Reassignment notices are never sent.** `notifications.notify_reassigned` has three unit tests but no caller in `app/`, so US8.4 AC2 and US10.2's reassign trigger are unimplemented. The helper tests hide this.
2. **Fake/production drift (reassignment).** `InMemoryEvents.assign_coordinator` allows reassignment. `SupabaseEvents.assign_coordinator` calls `assign_event_coordinator` (`SUPABASE_US4_5_LIFECYCLE.sql:7`), which only updates rows where `status = 'Submitted' AND coordinator_id IS NULL`. Production reassignment returns a stale or failed response, but all 14 reassignment tests pass. The route doesn't catch `StaleEventStatus`, so production most likely returns a 500 (`main.py` has no handler for it).
3. **The unavailability trigger.** Unit tests use a fake that only stores the range. The flagging is done by the Postgres trigger, and only `integration/test_unavailability_db.py` proves it.
4. **The replacement RPC** (`request_replacement_venue`) is defined only in the untracked `SUPABASE_FOUR_STORY_FIX.sql`. The replacement unit tests pass against the fake regardless.
5. **Registration concurrency** (US20.1 AC4 "enforced in the database") is proven only by `test_registration_db.py`, which never runs in CI.
6. **The hold sweep** (pg_cron) is proven only by `test_hold_expiry_db.py`, which never runs in CI.
7. **The Confirmed edit lock** has no test at all, so 100% coverage reports nothing missing.
8. **Browser handoffs.** Isolated E2E is broken by the credential rename. The shared E2E is not in CI and contains conditional tests.

---

## 5. File-by-file reduction table

All current counts are calculated from `pytest --collect-only` and the Vitest JSON report. "Signals" are name-pattern counts used to find redundancy. Each one was checked by reading the file; they are not a substitute for reading. For brevity, rows with an empty guidance cell in the generator use the default guidance: keep the distinct normal, boundary and denial cases, and merge params of one equivalence class.

**Pulled-tree additions (origin/main):**

| File | Functions | Target |
|---|---:|---:|
| `test_confirm_event_us4_7.py` | 27 | 8 |
| `test_reconfirm_us11_3.py` | 19 | 6 |

### 5.1 Backend (pytest)

The backend total includes the 37 functions in the two module-skipped DB files (2,394 collected + 37 = 2,431).

| Test file | Current cases | Distinct behaviours found (signals) | Redundancy type | Proposed target | Keep/merge/remove guidance |
|---|---:|---|---|---:|---|
| backend/tests/test_change_requests.py | 186 | 113 named; 73 param exp; role-like 37, 404-like 5, blank-like 6, store-like 27, notify 0, race 7 | param equivalence; helper+route duplication; role denials | 22 | Keep: propose happy path, status/flag set, owner-only, draft/closed refusals, one-pending, no-op refused, note limit, important-vs-routine classification (1 table test), accept applies+notifies, reject needs reason+keeps values, coordinator scoping, stale race. Collapse 23+6 validation params to 3 (invalid, boundary, multi-field). Drop label/order/typing trivia. |
| backend/tests/test_venue_unavailability.py | 148 | 83 named; 65 param exp; role-like 14, 404-like 74, blank-like 13, store-like 7, notify 0, race 1 | repeated malformed-date params (42); per-role denials; 404 x10 | 12 | Keep: record range (staff), reason enum + Other needs text + limit, end>=start, one malformed-date case, 404 venue, permission matrix (1), viewing order, flagging behaviour. Collapse 24 format + 18 calendar params to 1-2. |
| backend/tests/test_registration_us20_1.py | 122 | 73 named; 49 param exp; role-like 30, 404-like 9, blank-like 2, store-like 0, notify 8, race 0 | role-denial params; email/name validation params; attendee-route matrix | 14 | Keep: open/close rule by status (1 table), coordinator sets capacity + default, capacity>=taken, assigned-only, attendee listing hides planning info, register happy, one-per-attendee, full refused, full notice once, privacy. Collapse x5/x6 role and email params. |
| backend/tests/test_safety_check_us4_4.py | 111 | 54 named; 57 param exp; role-like 58, 404-like 2, blank-like 0, store-like 5, notify 0, race 10 | 20-case transition matrix; decision tests duplicated in US17.2 file; store RPC call tests | 10 | Keep: readiness rule (confirmed venue, no live hold/requested/conflict, equipment reserved, pending change blocks), coordinator-only send, assigned-only, stale race, queue order, Confirmed only via Pending Safety Check (1 table test). Move decision tests to US17.2 file. Drop RPC-call-shape tests (covered by DB layer). |
| backend/tests/test_cancel_event_us4_6.py | 104 | 75 named; 29 param exp; role-like 36, 404-like 5, blank-like 2, store-like 13, notify 14, race 3 | per-status params; notification permutations; per-role params | 12 | Keep: organiser/assigned coordinator may cancel, reason required, closed statuses refuse, bookings/holds/equipment released, registrations closed, notices to affected not canceller, notice failure does not undo, nothing reopens cancelled, stale race. |
| backend/tests/test_venue_turnaround.py | 93 | 50 named; 43 param exp; role-like 11, 404-like 2, blank-like 1, store-like 12, notify 0, race 0 | boundary params; validation variants | 9 | Keep: setup/turnaround non-negative integer bounds (1 invalid table + 1 boundary), staff-only, window maths (customer 10:00-12:00 example), change triggers recheck/flag, touching windows allowed. |
| backend/tests/test_safety_decision_us17_2.py | 92 | 70 named; 22 param exp; role-like 26, 404-like 4, blank-like 2, store-like 17, notify 1, race 4 | outcome x role params; note variants | 11 | REWRITE approval test (approve must NOT confirm; Coordinator confirms - QA8). Keep: three outcomes, note required for changes/reject, limit, officer-only, pending-only, decided-twice refused, history attributable, request-changes flags arrangements + notifies coordinator, re-sent needs fresh decision. |
| backend/tests/test_event_needs.py | 89 | 39 named; 50 param exp; role-like 2, 404-like 33, blank-like 5, store-like 7, notify 0, race 15 | 50 param expansions over fixed lists | 9 | Keep: each list validated (layout/facilities/accessibility) with one valid+one invalid, None/Not required option, required on submit, drafts skip, catalogue alignment. ADD/REWRITE: layout list must come from catalogue (QA1) not hard-coded LAYOUT_OPTIONS. |
| backend/tests/test_booking_conflicts.py | 84 | 76 named; 8 param exp; role-like 12, 404-like 1, blank-like 3, store-like 14, notify 4, race 25 | TC-F numbered permutations; overlapping cases | 12 | Keep: effective window (customer example), held/requested/confirmed count, expired/cancelled/replaced do not, unavailability blocks, message names clash, touching allowed, recheck on setup change flags not deletes, coordinator notified once, clearing failure isolated. |
| backend/tests/test_venues.py | 81 | 81 named; 0 param exp; role-like 20, 404-like 5, blank-like 7, store-like 1, notify 0, race 0 | 81 named, many field-by-field validation | 11 | Keep: create/update/delete staff-only (1 matrix), required fields, capacity bounds, catalogue list, search basic, delete hard-delete rule superseded by US9.5 (rewrite). Merge field validations into 2 table tests. |
| backend/tests/test_venue_holds.py | 75 | 55 named; 20 param exp; role-like 19, 404-like 6, blank-like 1, store-like 7, notify 0, race 6 | TC-H permutations; validation variants | 10 | Keep: staff place hold, expiry required & future, slot taken while held, hold->request before expiry, expired cannot be requested, held never confirmed, no-coordinator refused. ADD: staff update/release hold (QA23) - currently missing. |
| backend/tests/test_venue_bookings.py | 64 | 54 named; 10 param exp; role-like 8, 404-like 4, blank-like 3, store-like 2, notify 0, race 1 | validation variants | 9 | Keep: request multiple venues per event, each checked independently, one failure does not block others, assigned-only, approved->planning transition, headcount/layout fields. |
| backend/tests/test_booking_decisions.py | 57 | 47 named; 10 param exp; role-like 17, 404-like 2, blank-like 1, store-like 7, notify 5, race 4 | role/status params | 8 | Keep: queue oldest first with window, approve->Confirmed, conflict re-check at approval blocks, reject needs reason, staff-only, coordinator notified, stale race. |
| backend/tests/test_equipment.py | 55 | 39 named; 16 param exp; role-like 10, 404-like 8, blank-like 0, store-like 1, notify 3, race 5 | param variants | 8 | Keep: catalogue CRUD by Tech Support, request by assigned coordinator, quantity validation, tech support notified, out-of-service counted. |
| backend/tests/test_events.py | 54 | 54 named; 0 param exp; role-like 13, 404-like 3, blank-like 3, store-like 0, notify 0, race 0 | field-by-field edit tracking tests (5) | 12 | Keep: create draft, submit required fields, coordinator scoping, owner cannot edit submitted, important vs routine (1 table), end>start. REWRITE: coordinator edit must be refused on Confirmed (QA7). Drop duplicate field-tracking tests. |
| backend/tests/test_event_decisions.py | 53 | 23 named; 30 param exp; role-like 21, 404-like 3, blank-like 1, store-like 2, notify 0, race 4 | 30 param expansions over roles/statuses | 6 | Keep: approve/reject under review only, reason for reject, assigned coordinator only, organiser notified, history row. Collapse params. |
| backend/tests/test_suitability.py | 53 | 43 named; 10 param exp; role-like 9, 404-like 2, blank-like 1, store-like 0, notify 0, race 0 | duplicates test_venue_suitability.py | 6 | Merge with test_venue_suitability.py: capacity, layout, facilities, accessibility each pass/fail once, result shown per booking. |
| backend/tests/test_registration_us20_2.py | 45 | 35 named; 10 param exp; role-like 7, 404-like 3, blank-like 1, store-like 0, notify 0, race 0 | minor | 6 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_venue_suitability.py | 41 | 37 named; 4 param exp; role-like 10, 404-like 1, blank-like 2, store-like 2, notify 0, race 1 | duplicates test_suitability.py | 5 | Merge (see above). |
| backend/tests/test_booking_store.py | 40 | 36 named; 4 param exp; role-like 2, 404-like 4, blank-like 7, store-like 27, notify 0, race 1 | store query-builder tests duplicated by API tests | 3 | Keep only RPC contract tests that the API tests cannot reach (Supabase payload for atomic RPCs). Better: replace with DB integration. |
| backend/tests/test_venue_availability_us12_3.py | 37 | 27 named; 10 param exp; role-like 10, 404-like 1, blank-like 1, store-like 0, notify 0, race 0 | minor | 5 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_safety_review_us17_1.py | 37 | 24 named; 13 param exp; role-like 19, 404-like 2, blank-like 3, store-like 3, notify 0, race 0 | role params | 6 | Keep: officer queue only pending, oldest first, detail shows bookings/equipment, others denied. |
| backend/tests/test_change_review_us11_2.py | 36 | 17 named; 19 param exp; role-like 7, 404-like 0, blank-like 0, store-like 1, notify 0, race 4 | status params (x5) assert status preserved incl. Confirmed | 8 | REWRITE [Confirmed] case: accepting date/time/attendance change on Confirmed must send it back through checks (QA14). Keep recheck/flag tests, stale-marker race. |
| backend/tests/test_event_clarification.py | 34 | 34 named; 0 param exp; role-like 9, 404-like 1, blank-like 2, store-like 0, notify 0, race 1 | minor | 6 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_registration_store.py | 34 | 23 named; 11 param exp; role-like 0, 404-like 0, blank-like 1, store-like 3, notify 0, race 4 | store tests duplicated by API | 3 | Keep RPC-contract only; DB file owns behaviour. |
| backend/tests/test_venue_booking_cancellation.py | 34 | 32 named; 2 param exp; role-like 9, 404-like 4, blank-like 2, store-like 1, notify 0, race 1 | role denials | 7 | Keep: assigned coordinator cancels one booking, others untouched, slot freed, roles denied (1 matrix), race refused. |
| backend/tests/test_registration_db.py | 34 | opt-in DB functions | DB opt-in, never run in CI | 10 | Keep concurrency (2), trigger/index (3), withdraw/cancel (4), open rule (3); drop duplicates of API validation. |
| backend/tests/test_venue_unavailability_store.py | 32 | 27 named; 5 param exp; role-like 1, 404-like 3, blank-like 8, store-like 27, notify 0, race 0 | store mapping tests | 2 | Keep row-mapping contract (1) + RPC call (1); behaviour is in integration/test_unavailability_db.py. |
| backend/tests/test_venue_delete_us9_5.py | 30 | 22 named; 8 param exp; role-like 2, 404-like 0, blank-like 0, store-like 0, notify 0, race 5 | minor | 5 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_registration_us20_3.py | 29 | 23 named; 6 param exp; role-like 21, 404-like 2, blank-like 0, store-like 0, notify 0, race 0 | 21 role-pattern tests | 5 | Collapse to permission matrix + organiser/assigned coordinator view + attendee privacy. |
| backend/tests/test_replacement_venue_us14_5.py | 28 | 10 named; 18 param exp; role-like 11, 404-like 0, blank-like 0, store-like 2, notify 0, race 4 | 18 param expansions | 6 | Keep: search free venues only, request creates new booking, old marked Replaced, others untouched, only Needs-replacement, closed events refused. |
| backend/tests/test_venue_store.py | 26 | 26 named; 0 param exp; role-like 0, 404-like 0, blank-like 3, store-like 12, notify 0, race 0 | store query-builder | 2 | Keep only Supabase mapping contract. |
| backend/tests/test_equipment_reservations.py | 26 | 16 named; 10 param exp; role-like 0, 404-like 1, blank-like 0, store-like 0, notify 3, race 0 | minor | 6 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_equipment_store.py | 25 | 25 named; 0 param exp; role-like 2, 404-like 3, blank-like 0, store-like 5, notify 1, race 1 | store query-builder | 2 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_remaining_guards.py | 23 | 22 named; 1 param exp; role-like 4, 404-like 3, blank-like 0, store-like 0, notify 4, race 4 | coverage-only grab-bag | 3 | Move the 3 real risks (deleted-account session, race reported stale, non-numeric id) into feature files; delete the rest. |
| backend/tests/test_notifications.py | 23 | 21 named; 2 param exp; role-like 5, 404-like 3, blank-like 0, store-like 1, notify 11, race 0 | notification-failure permutations | 5 | Keep: list unread first, toggle read, own-only, write failure does not fail action (1 shared test). |
| backend/tests/test_access_enforcement.py | 20 | 20 named; 0 param exp; role-like 13, 404-like 2, blank-like 0, store-like 0, notify 0, race 2 | per-role denials | 4 | Replace with 1-2 parametrised permission-matrix tests (role x route) + 401 unauthenticated. |
| backend/tests/test_change_review_paths.py | 20 | 20 named; 0 param exp; role-like 5, 404-like 0, blank-like 0, store-like 5, notify 2, race 3 | coverage-only paths | 2 | Merge 2 genuine edge cases into test_change_review_us11_2.py; delete rest. |
| backend/tests/test_coordinator_notifications.py | 20 | 16 named; 4 param exp; role-like 4, 404-like 0, blank-like 0, store-like 1, notify 15, race 0 | per-event-type permutations | 5 | Keep one test per AC1 trigger family (assign/reassign, hold, booking decision, conflict/unavailability, safety). |
| backend/tests/test_event_route_guards.py | 16 | 14 named; 2 param exp; role-like 4, 404-like 1, blank-like 1, store-like 3, notify 0, race 4 | coverage-only guards | 2 | Merge into feature files. |
| backend/tests/test_event_store_queries.py | 14 | 14 named; 0 param exp; role-like 2, 404-like 1, blank-like 0, store-like 0, notify 0, race 4 | store query-builder | 2 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_lead_reassignment.py | 14 | 14 named; 0 param exp; role-like 6, 404-like 1, blank-like 0, store-like 0, notify 0, race 0 | only tests Submitted/Under Review in-memory | 6 | REWRITE: reassign a Planning/Confirmed event; add Supabase-path test (production RPC refuses reassign). |
| backend/tests/test_supabase_config.py | 12 | 10 named; 2 param exp; role-like 1, 404-like 4, blank-like 1, store-like 3, notify 0, race 1 | config trivia | 2 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_user_store.py | 11 | 10 named; 1 param exp; role-like 1, 404-like 2, blank-like 1, store-like 1, notify 0, race 0 | store | 1 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_notification_store.py | 7 | 7 named; 0 param exp; role-like 1, 404-like 1, blank-like 0, store-like 0, notify 5, race 0 | store | 1 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_coordinator_assignment.py | 7 | 7 named; 0 param exp; role-like 1, 404-like 0, blank-like 0, store-like 0, notify 0, race 0 | historical US8.1 negative tests | 1 | Keep one: submission leaves coordinator unassigned. |
| backend/tests/test_equipment_reservations_db.py | 4 | 4 named; 0 param exp; role-like 1, 404-like 0, blank-like 0, store-like 0, notify 1, race 0 | DB - keep | 4 | Keep; document migration order so it runs. |
| backend/tests/test_equipment_item_migration_db.py | 4 | 3 named; 1 param exp; role-like 0, 404-like 0, blank-like 0, store-like 1, notify 2, race 0 | minor | 2 | Keep the distinct normal/boundary/denial cases; merge params of one equivalence class. |
| backend/tests/test_hold_expiry_db.py | 3 | opt-in DB functions | DB opt-in, never run in CI | 3 | Keep all 3; add to CI against local Postgres. |
| backend/tests/test_draft_store.py | 1 | 1 named; 0 param exp; role-like 0, 404-like 0, blank-like 1, store-like 0, notify 0, race 0 | store | 0 | Merge into test_events.py |
| *other backend files (15)* | 143 | see Appendix A | small | 47 | Keep as listed in Appendix A |
| **Backend total** | **2431** | | | **358** | |

### 5.2 Frontend (Vitest)

| Test file | Current cases | Redundancy type | Proposed target | Keep/merge/remove guidance |
|---|---:|---|---:|---|
| frontend/src/components/EventBookings.test.tsx | 74 | permutation/duplication | 12 | Keep: request multi-venue form, per-venue result (one fails, others succeed), status chips incl. Needs replacement/Held/Expired, cancel one booking, conflict message shown, suitability warnings. Collapse 15 error permutations to 2. |
| frontend/src/status.test.ts | 63 | permutation/duplication | 5 | One table for label/colour per status + one for allowed-action helper. Drop text-helper combinations. |
| frontend/src/venuesStore.test.ts | 63 | permutation/duplication | 4 | Store plumbing: keep error-translation (1), list/search query shape (1), create/update payload (2). Behaviour belongs to page tests. |
| frontend/src/components/SafetyCheckPanel.test.tsx | 51 | permutation/duplication | 6 | REWRITE approve path (no auto-Confirmed; Coordinator confirm button). Keep readiness reasons shown, send button only for assigned coordinator, officer decision form note required. |
| frontend/src/pages/EventChangeRequest.test.tsx | 44 | permutation/duplication | 6 | Keep: proposed vs current with important highlighted, accept, reject needs reason, one validation error, refusal messages (1). |
| frontend/src/permissions.test.ts | 43 | permutation/duplication | 3 | One role x permission matrix (it.each) + 2 route-consequence tests. |
| frontend/src/components/VenueUnavailability.test.tsx | 43 | permutation/duplication | 5 | Keep: reason picker incl. Other text, date validation display, flagged count shown (incl. 0), staff-only form. |
| frontend/src/pages/EventDetailPage.test.tsx | 42 | permutation/duplication | 7 | Keep: role-scoped actions (organiser read-only after submit, coordinator edit), status timeline, REWRITE: no edit button on Confirmed. |
| frontend/src/pages/VenueFormPage.test.tsx | 42 | permutation/duplication | 5 | Keep: required fields error, setup/turnaround inputs, layout/facility lists, save success, server error shown. |
| frontend/src/eventsStore.test.ts | 41 | permutation/duplication | 4 | Keep error translation + submit/save payloads; drop per-endpoint plumbing. |
| frontend/src/venueTurnaround.test.ts | 36 | permutation/duplication | 3 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/registrationStore.test.ts | 35 | permutation/duplication | 3 | Keep error->sentence mapping for full / already registered / closed. |
| frontend/src/pages/NewEventPage.test.tsx | 33 | permutation/duplication | 7 | Keep: mandatory fields block submit with message, None/Not required options, draft saves partial, submit success. Merge draftRules display duplicates. |
| frontend/src/pages/VenuesPage.test.tsx | 32 | permutation/duplication | 5 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/draftRules.test.ts | 31 | permutation/duplication | 4 | One equivalence case per rule (required, end>start, attendance positive, date not past). |
| frontend/src/eventNeeds.test.ts | 30 | permutation/duplication | 2 | Keep list membership + Not required; layout list should come from catalogue (QA1). |
| frontend/src/App.test.tsx | 29 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/components/EventRegistration.test.tsx | 29 | permutation/duplication | 5 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/eventsStore.calls.test.ts | 28 | coverage-only (.calls) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/components/VenueAvailability.test.tsx | 28 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/api.test.ts | 27 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/pages.paths.test.tsx | 26 | coverage-only (.paths) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/pages/VenueDetailPage.test.tsx | 25 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/equipmentStore.test.ts | 22 | permutation/duplication | 2 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/components/CancelEventPanel.test.tsx | 22 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/EventDetailPage.paths.test.tsx | 22 | coverage-only (.paths) | 2 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/NotificationsPage.test.tsx | 22 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/App.routes.test.tsx | 20 | route-coverage table | 3 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/holdsStore.test.ts | 20 | permutation/duplication | 2 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/EventClarification.test.tsx | 19 | permutation/duplication | 3 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/venuesStore.calls.test.ts | 18 | coverage-only (.calls) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/components/EventEquipment.test.tsx | 18 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/UnassignedQueuePage.test.tsx | 17 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/BookingRequestsPage.test.tsx | 15 | permutation/duplication | 4 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/components/EventEquipment.paths.test.tsx | 9 | coverage-only (.paths) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/pages/EquipmentPage.paths.test.tsx | 9 | coverage-only (.paths) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/unassignedQueueStore.test.ts | 8 | store plumbing | 1 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/bookingRequestsStore.test.ts | 7 | store plumbing | 1 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/pages/EquipmentRequestDetailPage.paths.test.tsx | 6 | coverage-only (.paths) | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| frontend/src/notificationsStore.test.ts | 4 | store plumbing | 1 | Keep the customer-visible states and one error state; drop permutations. |
| frontend/src/bookingConflictsStore.test.ts | 3 | store plumbing | 0 | Merge unique behaviour into the owning page/component test, then delete. |
| *other frontend files (24)* | 205 | small | 49 | See Appendix A |
| **Frontend total** | **1361** | | **186** | |

### 5.3 Database integration and opt-in DB files

| Test file | Current cases | Distinct behaviours | Redundancy type | Proposed target | Guidance |
|---|---:|---|---|---:|---|
| `backend/integration/test_change_review_db.py` | 12 | concurrent decisions, rollback, per-field accept, direct-edit marker + SGT timestamp, equipment guard, stale-check publish (×2), snapshot match, SQL safety guard (×3), reservation peak demand | 2 small param sets | 10 | **Keep.** Collapse `stale_check…` to 1 param and `sql_safety_guard…` to 2 (venue, pending). |
| `backend/integration/test_unavailability_db.py` | 7 | migration rerunnable, flagged once and decisions preserved, midnight boundaries, reason → booking and notice (×4) | reason enum ×4 | 4 | **Keep.** Collapse reasons to Other-with-text + one enum value. |
| `backend/tests/test_registration_db.py` | 34 functions (module-skipped) | concurrency (2), trigger/index (3), open rule, withdraw, cancel cascade | Duplicates the API validation | 10 | **Keep all concurrency, trigger and index tests.** Move into `integration/` and run in CI. |
| `backend/tests/test_hold_expiry_db.py` | 3 (module-skipped) | sweep warns/expires once; expired frees slot; expiry kept | none | 3 | **Keep. Run in CI.** |
| `backend/tests/test_equipment_reservations_db.py` | 4 (errors without a full schema) | concurrent reserve, stock | none | 4 | **Keep.** Script the migration order so it runs. |
| `backend/tests/test_equipment_item_migration_db.py` | 4 | migration idempotent | param | 2 | Keep 2. |
| **To add** | — | reassignment via the Supabase path (C11); Confirmed-edit refusal in SQL; venue-unavailability revert on Confirmed (after the fix) | — | +3 | New tests, needed to close drift |

### 5.4 Playwright

| File | Config | Current | Target | Guidance |
|---|---|---:|---:|---|
| `e2e-isolated/safety-check-us17.spec.ts` | isolated | 5 | 3 | **Rewrite** for Safety approve → Coordinator confirm (pull origin/main). Keep request changes → resend → approve → confirm, and reject. |
| `e2e-isolated/venue-delete-us9-5.spec.ts` | isolated | 5 | 1 | Keep "future booking blocks delete". The rest is proven at API level. |
| `e2e/authentication.spec.ts` | shared | 11 | 2 | Move to isolated. Keep: sign in → role landing; sign out → protected page needs sign-in. |
| `e2e/coordinator-lead-assignment.spec.ts` | shared | 11 | 2 | Move to isolated. Keep: submit → Lead assigns → Coordinator sees it; reassign → old Coordinator loses it. **Remove the conditional `if` bodies.** |
| `e2e/change-review-us11-2.spec.ts` | shared | 1 | 1 | Move to isolated (E2E-11). |
| `e2e/ariel-events.spec.ts` | shared | 3 | 1 | Keep: create → submit → approve. |
| `e2e/ariel-catalogues.spec.ts` | shared | 3 | 0 | Catalogue CRUD is proven at API and page level. |
| `e2e/ariel-equipment.spec.ts` | shared | 2 | 1 | Request → reserve handoff. |
| `e2e/replacement-venue-us14-5*.spec.ts` | shared, **ignored** | 5 | 1 | Un-ignore one (E2E-7) and move to isolated. |
| **Total** | | **43 (+5 ignored)** | **12** | **Fix fixtures first.** Make `e2e/helpers.ts` and `backend/e2e_server.py` read one credential source. Add `npx playwright test -c playwright.isolated.config.ts` to CI. |

---

## 6. Tests that must not be removed

These are kept whatever coverage says, because each is the only proof of a distinct risk.

1. **Database atomicity and concurrency:**
   - `test_registration_db.py::…::test_at_the_same_moment_exactly_one_gets_the_place`
   - `test_registration_db.py::…::test_the_second_waits_for_the_first_then_finds_the_event_full`
   - the trigger and index tests (`test_the_trigger_refuses_a_direct_insert_beyond_capacity`, `…_when_registration_is_off`, `test_the_index_refuses_a_second_active_row_for_one_attendee`)
   - `integration/test_change_review_db.py::test_revisions_history_and_concurrent_decisions`
   - `integration/test_change_review_db.py::test_reject_assignment_and_transaction_rollback`
   - `integration/test_change_review_db.py::test_sql_reservation_peak_demand`
   - `test_equipment_reservations_db.py` (all)
2. **Production triggers:**
   - `integration/test_unavailability_db.py::test_active_bookings_flagged_once_and_decisions_preserved`
   - `integration/test_unavailability_db.py::test_setup_turnaround_overlap_excludes_exact_midnight_boundaries`
   - `test_hold_expiry_db.py` (all 3)
3. **Customer worked examples:**
   - the 10:00–12:00 + 30 + 45 → 09:30–12:45 window and the touching-window case (`test_booking_conflicts.py`, `test_venue_turnaround.py`, `venueTurnaround.test.ts`, one each)
   - the US12.2 AC8 10–12 Nov example
   - the US19.3 AC5 10/2/6 → 2 example
4. **One stale-race test per write family:** submit, decide, assign, change-request decide, send for safety, safety decide, cancel, booking decide, booking cancel. Examples are `test_a_race_lost_in_the_store_is_reported_as_stale` and `test_losing_a_race_to_another_cancel_is_refused_not_crashed`.
5. **The role × route permission matrix**, plus 401-when-signed-out and 404-not-403 for another user's event.
6. **Safety readiness blockers:**
   - no Confirmed venue
   - Requested booking present
   - live hold
   - conflict-flagged booking
   - equipment line not reserved
   - pending change request

   Each is a distinct reason in `safety_check.py`.
7. **Multi-venue independence:** one booking failing doesn't block the others (US14.1 AC3), cancelling one leaves the others (US14.2), and replacement leaves the others (US14.5 AC3).
8. **Cancellation side effects:** releases bookings, holds and equipment; closes registrations; a notice-write failure doesn't undo the cancel.
9. **Attendee privacy:** `test_nothing_of_the_planning_is_shown` and `test_an_attendee_reaches_none_of_the_internal_routes` (as one matrix).
10. **Expired hold ≠ confirmed booking:** frees the slot and can't be converted.

## 7. Tests that assert wrong or stale behaviour

Rewrite these; don't silently delete them.

| Test (local tree) | What it asserts | Why it's wrong | Rewrite to |
|---|---|---|---|
| `test_safety_decision_us17_2.py::…::test_approval_confirms_the_event` and `test_safety_check_us4_4.py::TestSafetyOfficerDecision::test_approval_confirms_the_event` | Safety approve → Confirmed | QA8: the Coordinator confirms after all approvals | Approve leaves the event approved/awaiting confirmation; the Coordinator confirms. **[Done on origin/main: verify after pulling.]** |
| `test_safety_check_us4_4.py::TestOnlyWayToConfirmed::test_end_to_end_from_draft_to_confirmed`, `SafetyCheckPanel.test.tsx` approve cases, `e2e-isolated/safety-check-us17.spec.ts` | Same flow | Same | Add the Coordinator confirm step. [Partly done on origin/main] |
| `test_change_review_us11_2.py::test_request_question_revision_and_accept_preserve_status[Confirmed]` | Accepted change keeps Confirmed | QA14 | An important change on Confirmed → Planning, then re-check and re-confirm. [Done on origin/main] |
| `test_events.py::test_coordinator_can_edit_any_event` (+ absent Confirmed case) | Coordinator edit allowed at any non-closed status | QA7: no direct edit once Confirmed | Add a parametrised refusal for Confirmed (409, "use a change request"). **Still open on origin/main.** |
| `test_lead_reassignment.py` (all 14) | Reassign works (in-memory) | Production RPC refuses; no Planning/Confirmed case; no notice | Run reassignment of a Planning event through Postgres. Assert old/new access, both notices, and a history row. |
| `test_lead_reassignment.py::test_reassignment_is_recorded_in_history` | `len(after) >= len(before)` | Always true, so it passes for the wrong reason | Assert one new entry naming the previous and new Coordinator (US8.4 AC4) |
| `test_lifecycle_us4_5.py` Supabase `assign_coordinator` RPC test | RPC name/payload for assignment | Used as the only "production" evidence for reassignment | Keep for assignment; add a reassignment equivalent |
| `test_coordinator_notifications.py` reassign helper tests (3) | Helper builds two notices | No route calls the helper | Test through `POST /events/{id}/reassign` |
| `test_event_needs.py` layout parametrisation; `eventNeeds.test.ts` | Hard-coded layout list | QA1: catalogue-managed layouts | One test that the event layout list equals the catalogue's list |
| `test_venues.py` delete tests that assume no bookings exist | US9.1c hard delete | Superseded by US9.5 | Fold into the US9.5 file ("no future bookings → deleted") |
| `test_venue_holds.py` Held → Requested tests | Hold before request | QA19/QA30: hold after venue approval | Keep until the flow is changed; flag in the ledger as **encodes team assumption** |
| `test_coordinator_assignment.py` (6 of 7) | Several variants of "no auto-assign" | US8.1 superseded; one regression suffices | Keep `test_submissions_no_longer_auto_assign` only |
| `coordinator-lead-assignment.spec.ts` US8.3 and US8.4 | Conditional `if (visible)` bodies | Can pass without doing anything | Seed an event; assert unconditionally |
| `e2e/helpers.ts`, `venue-delete-us9-5.spec.ts` (uncommitted) | `@connectsphere.com` / `password` | `e2e_server.py` seeds `@spmg3t7.edu` / `Sprint1!demo` | Use one shared fixture source |

## 8. Proposed final test budget

Derived bottom-up: per file (§5), cross-checked per story (§4).

| Layer | Current | Target | Owns |
|---|---:|---:|---|
| Backend unit/API (pytest, in-memory) | 2,394 | **339** | Authorisation, business rules, validation boundaries, stale-race handling |
| Opt-in DB tests → make runnable in CI | 37 functions + 8 | **19** | Concurrency, triggers, unique indexes, sweep |
| CI integration (Postgres) | 19 | **14** (+3 to add) | Atomic RPCs, trigger side effects, drift checks |
| Vitest | 1,361 | **186** | Customer-visible states, form errors, role-specific actions |
| Playwright (isolated, in CI) | 43 (+5 ignored) | **12** | Critical role handoffs (E2E-1, 7, 9, 11, 13, 15 and sign-in) |
| **Total** | **≈3,850** | **≈570** (+≈12 rewrites/adds) | |
| On origin/main, also prune | `test_confirm_event_us4_7.py` (27 fns), `test_reconfirm_us11_3.py` (19 fns) | 8 + 6 | Confirm gate (all approvals in, assigned only, race); Confirmed → Planning on important change only |

**Reviewability.**
- 570 ÷ 5 ≈ **114 tests per person**.
- At about 2.5 minutes each (read, run, explain, fill one ledger row): ≈ 4.75 h.
- Add about 1 h for running suites and cross-review. That fits one 6-hour day.
- A target above about 650 doesn't fit. Below about 450 starts dropping distinct ACs.

**Coverage tradeoff.** After pruning, backend coverage will fall below 100%, and branch coverage furthest. The uncovered lines will mostly be:
- defensive `# pragma`-style guards
- fake-client error branches
- formatting fallbacks
- "impossible" states, e.g. `save_event`'s draft check, which is already marked unreachable

Keeping roughly 1,800 extra tests only to execute those lines would defeat the professor's independent-review requirement.

- **Recommendation:**
  - Set `fail_under` to the measured line coverage after pruning, rounded down; I expect 85–90%.
  - Drop the branch gate.
  - Lower the Vitest thresholds to the measured values.
  - List the excluded defensive paths in the README.
- **Restore rule:** restore a test only if the newly uncovered code is a requirement, a security boundary, a transaction or a real failure path.

## 9. One-day consolidation sequence

Run on a branch, in this order. Each step ends green.

| Time | Step | Who |
|---|---|---|
| 0:00–0:30 | `git pull` (gets US4.7/US11.3). Fix the Ruff line. Make the isolated E2E fixtures share one credential source. Confirm the baseline is green. | Ethan |
| 0:30–1:30 | **Wave 1, delete scaffolding.** Move the 3 real cases out of `test_remaining_guards.py`, `test_event_route_guards.py` and `test_change_review_paths.py`, then delete those files. Merge the `*.paths` / `*.calls` / `App.routes` files into their owning tests (keep ≤ 4 cases in total), then delete them. Cut store tests to RPC-contract only. | each owner, their files |
| 1:30–3:30 | **Wave 2, collapse classes in the big files** (§5 guidance): one param case per equivalence class; one permission matrix; one 404 and one malformed ID; one notification-failure test per helper; merge `test_suitability.py` with `test_venue_suitability.py`; move safety decision tests from the US4.4 file to the US17.2 file. | per §10 allocation |
| 3:30–4:15 | **Wave 3, rewrite stale tests** (§7) and add the missing ones: Confirmed edit refused; reassign through Postgres; reassign notices; hold update (once implemented). | owners of D4, I10, I8 |
| 4:15–4:45 | **DB/E2E.** Move `test_registration_db.py` and `test_hold_expiry_db.py` into `integration/` (or set the env in CI). Script the migration order. Add isolated Playwright to CI. Cut E2E to 12. | Ivy + Lincoln |
| 4:45–5:15 | Run everything. Measure coverage and set honest thresholds. Restore only tests that cover requirement or security lines. | Ethan |
| 5:15–6:00 | **Cross-review.** Each person reviews another person's retained tests using the ledger. | all |

## 10. Human-review allocation and checklist

**Allocation.** Reviewers follow the `MASTER_TEST_PLAN.md` tester assignments, so the tester is not the implementer. Two stories move to Ivy to balance the load.

| Reviewer | Stories (MASTER_TEST_PLAN IDs) | ≈ Retained tests |
|---|---|---:|
| Ethan | E1–E8, E10, E11 (US2.1, 2.2, 3.1, 2.1r, 7.3, 7.1, 4.3, 10.1, 11.2, 4.6) | 112 |
| Dylan | D1–D10, D12 (US1.1, 1.2, 5.1, 5.2, 12.1, 12.2, 14.5, 9.5, 12.3, 20.1, 20.3) | 115 |
| Ivy | I1–I12 + E9 US11.1 + D11 US20.2 | 114 |
| Lincoln | L1–L12 (US1.4, 8.1, 8.2, 8.3, 8.6, 19.0–19.3, 4.4, 17.1, 17.2) | 113 |
| Ariel | A1–A12 (US1.3, 9.0, 9.2, 9.3, 9.4, 14.1, 18.1, 14.2, 16.1, 15.1, 15.2, 10.2) | 117 |

If someone implemented a story they're assigned to review, swap that story with a neighbour. Nobody signs off their own code.

**Checklist for each retained test.** Every answer must be yes, or the test is cut or rewritten.

1. It names a current story/AC (not a superseded one) or a named technical risk.
2. I can name the defect that would ship if this test were deleted, and no other retained test would catch it.
3. It sits at the right layer: DB for atomicity/triggers, API for rules and authorisation, UI for what the user sees, E2E for handoffs.
4. It asserts behaviour (status, response, visible text), not mock call order or internal shape.
5. It can't pass for the wrong reason: no `>=` on lengths, no conditional `if visible`, no assertions on the fake only when production differs.
6. I can explain its setup, action and assertion without help.
7. Someone other than the implementer has reviewed it.

**Review ledger template** (one row per retained test; commit as `TEST_REVIEW_LEDGER.md`):

| Story/AC | Test path and name | Layer | Unique risk | Reviewer | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| US15.1 AC2 | `backend/tests/test_booking_conflicts.py::…customer_example…` | API | Buffers not applied → double booking | Ariel | Pass | Customer worked example |
| US20.1 AC4 | `backend/integration/test_registration_db.py::…exactly_one_gets_the_place` | DB | Two attendees take the last place | Dylan | | Needs CI DB |
| US8.4 AC1 | `backend/integration/test_reassign_db.py::reassign_planning_event` (to add) | DB | Production RPC refuses reassignment | Ivy | Fail (expected until fixed) | Drift C11 |
| | | | | | | |

## 11. Risks of the proposed reduction

1. **Coverage visibly drops**, and markers may read that as lower quality. Mitigation: the ledger plus a written coverage policy (§8). The claim becomes "every test is reviewed and tied to an AC".
2. **Removing a param case that was a hidden distinct class**, e.g. a date format that takes a different parser branch. Mitigation: when collapsing, keep one case per *code path*. Run coverage before and after each file and inspect any newly uncovered line.
3. **Fakes keep drifting from SQL.** A smaller API suite makes the fake/RPC gap more dangerous. Mitigation: keep the integration tests, add the 3 drift tests, and run the opt-in DB tests in CI.
4. **Pruning on a stale checkout.** The local tree is 4 commits behind. Pruning before pulling causes conflicts in 6 test files and leaves the US4.7/US11.3 tests unpruned. Mitigation: pull first (§9 step 1).
5. **Uncommitted work lost.** `MASTER_TEST_PLAN.md`, `SUPABASE_FOUR_STORY_FIX.sql` and `test-plans/` are untracked. A careless `git clean` or branch switch loses them. Mitigation: commit them before pruning.
6. **Over-reliance on E2E** that has never been in CI. Mitigation: add it to CI before deleting overlapping API tests, and keep the API tests that own rules.
7. **Some rewrites depend on unbuilt product fixes:** Confirmed edit lock, reassign RPC, hold update, Confirmed unavailability revert. Until those are built, mark the tests as `xfail` with a reason pointing to the story, so the gap stays visible rather than hidden.

---

## 12. Comparison with the two previous audits

I opened `CONNECTSPHERE_AUDIT_REPORT.md` (requirements audit) and `TEST_SUITE_US_AC_AUDIT.md` (test-suite audit) only after recording my own conclusions. Every agreement below is something I had verified in code before reading them.

### 12.1 Where I agree (independently reached)

| Topic | Previous audits | This audit |
|---|---|---|
| Safety approval auto-confirms (C5) | Both: contradicts QA8; tests must be rewritten | Same. Since fixed on origin/main by US4.7. |
| Coordinator can edit Confirmed (C6) | Requirements audit: P0 | Same. **Still open on origin/main.** |
| No Confirmed → Planning after an important change (C7) | Both | Same. Fixed on origin/main by US11.3. |
| Reassignment fake/SQL drift (C11) | Requirements audit: "material drift" | Same: `assign_event_coordinator` requires Submitted + NULL. |
| Reassign notifications not sent | Requirements audit (C-N evidence) | Same. I found it independently via the missing `notify_reassigned` call. |
| No hold update by Venue Staff (C10) | Both | Same. I also flag the hold **order** (QA19/QA30), which neither report raised. |
| Superseded ACs: US8.1, early "any Coordinator", US2.1 original, US9.1c | Test-suite audit §3 | Same set |
| Isolated E2E broken by the credential rename; no Playwright in CI; replacement specs ignored | Both | Same, and I ran both states (0/10 current, 10/10 HEAD) |
| Ruff fails on `seed_new_users.py:76` | Requirements audit | **I missed this in my first pass. Verified after reading: correct.** |
| `request_replacement_venue` exists only in untracked SQL | Requirements audit | Verified: correct |
| RLS bypassed by the service-role key; API is the real boundary | Requirements audit | Same (US8.6 AC5 PARTIAL) |
| Overall target size | Test-suite audit: 575–655 (≈640) | ≈570 bottom-up. Close agreement. |
| Retire `*.paths`/`*.calls`/guard files; one permission matrix; one notification-failure test per helper | Test-suite audit Waves 1–2 | Same |

### 12.2 Where I disagree, and why

| Topic | Previous position | My position | Reason |
|---|---|---|---|
| E2E target | 20 isolated scenarios, one per baseline E2E-1…20 | **12** | Only 10 isolated tests exist today, and they're broken. Writing 10 more browser scenarios is test *generation* and doesn't fit in the one-day budget. The 12 cover the role handoffs where an API test can't substitute. The other baseline scenarios are proven at API/DB level and recorded as manual in `MASTER_TEST_PLAN.md`. |
| Opt-in DB evidence | "10 skipped cases" | **37 functions in module-skipped files + 8 equipment DB cases** | `test_registration_db.py` (34) and `test_hold_expiry_db.py` (3) are skipped at module level, so pytest reports each as one skip. The previous figure understates how much database proof is never run, including the only concurrency proof for US20.1 AC4. |
| Coverage policy | Keep thresholds for the first pass, then about 95% lines / 90% branches | Measure after pruning; expect 85–90% lines; **no branch gate** | At about 15% of the current count, 90% branch coverage would force keeping fake-client and defensive branches that fail checklist item 2. A 95/90 target would quietly bring the coverage-driven tests back. |
| Unavailability flagging as "automatic mutation … borderline" | Requirements audit | **Not a contradiction** | W7#2 asks for affected bookings to be *identified* and Coordinators *informed*. Setting a booking flag is identification. The real gap is the missing Confirmed-event revert (QA12), which I mark PARTIAL. |
| Safety test targets | 15–20 each for US4.4 and US17.2 | 10 + 11 (decision tests moved to the US17.2 file) | The two files duplicate the decision behaviour; one owner is enough. |
| `test_equipment.py` | 16–20 | 8 | The 39 named tests cover about 8 distinct rules; overlap with `test_equipment_reservations.py` is high. |
| Frontend `status.test.ts` | 8–10 | 5 | Two tables (label/colour per status; allowed actions) cover it. |

### 12.3 What this audit adds

1. **`origin/main` has moved on.** It is 4 commits ahead, with US4.7 and US11.3 merged, 46 new test functions and 6 rewritten test files. Both earlier reports and this one audit `e2b305c`. **Pull before pruning.**
2. **An always-true assertion.** `test_reassignment_is_recorded_in_history` asserts `len(after) >= len(before)`, so it passes for the wrong reason.
3. **Conditional Playwright bodies** (`if (hasAssignButton)`, `if (await reassignButton.isVisible())`) mean the US8.3 and US8.4 browser tests can pass without exercising the feature.
4. **Duplicate suitability suites.** `test_suitability.py` and `test_venue_suitability.py` (53 + 41) test the same rule. The test-suite audit kept both.
5. **Hold-order contradiction (QA19, QA30).** This is separate from the missing update route.
6. **A story-level allocation** that keeps tester ≠ implementer, with balanced counts and a filled ledger example.

### 12.4 Not verified

The requirements audit reports a Singapore-time comparison difference in the hold handling between the committed trigger and the untracked SQL patch. I did not check this, and make no claim either way.

## 13. Final recommendation

1. **Pull `origin/main` and commit the untracked work** (`MASTER_TEST_PLAN.md`, the SQL patch, split into focused migrations, and `test-plans/`) before touching any test.
2. **Prune to about 570 tests in one day** using §5 and §9. Delete the coverage scaffolding first; it's the cheapest and safest cut.
3. **Rewrite the stale tests** (§7). Leave the ones that depend on unbuilt fixes as `xfail` with a story reference, so the gaps stay visible:
   - Confirmed edit lock
   - production reassignment and its notices
   - hold update
   - Confirmed unavailability revert
4. **Make the database and browser proofs run in CI:**
   - the opt-in DB tests
   - the scripted migration order
   - isolated Playwright with one credential source
5. **Replace the 100% claim with an honest threshold and the review ledger.** Every retained test should have a named reviewer who isn't its implementer.

### Largest safe reductions

| Cut | Cases removed (approx.) |
|---|---:|
| Collapse parametrised equivalence classes, mainly malformed dates, role lists, status matrices and fixed-list values | ≈ 550 |
| Per-role denials → one permission matrix per resource | ≈ 250 |
| `*.paths` / `*.calls` / `App.routes` / guard files (backend + frontend) | ≈ 190 |
| Store and query-builder tests duplicated by API tests | ≈ 380 (backend 190, frontend 190) |
| Field-by-field validation repeated at helper, route, store, component and page | ≈ 600 |
| Notification-failure and 404/malformed-ID permutations | ≈ 200 |
| Duplicate suites (suitability ×2; safety decision ×2) | ≈ 120 |
| Shared E2E moved to isolated and cut to handoffs | 31 |

The categories overlap. The rest of the ≈3,280-case reduction comes from consolidating each large feature file to its §5 target.

### Tests to rewrite, not delete

- Safety "approval confirms" tests: two backend files, `SafetyCheckPanel`, and the isolated E2E. Already rewritten on origin/main; verify.
- `test_change_review_us11_2.py::…preserve_status[Confirmed]`. Already rewritten on origin/main; verify.
- The Coordinator edit tests: they need a Confirmed refusal case.
- All `test_lead_reassignment.py` tests. They need a Planning/Confirmed event, the Postgres path, both notices and a real history assertion.
- The `notify_reassigned` helper tests: test them through the route.
- The layout-list tests: they should check against the catalogue.
- The US9.1c hard-delete tests: fold them into US9.5.
- The conditional Playwright tests for US8.3 and US8.4.
- The isolated E2E fixtures: use one credential source.

---

## Appendix A: per-file current vs target (all files)

| Layer | File | Current | Target |
|---|---|---:|---:|
| backend | tests/test_change_requests.py | 186 | 22 |
| backend | tests/test_venue_unavailability.py | 148 | 12 |
| backend | tests/test_registration_us20_1.py | 122 | 14 |
| backend | tests/test_safety_check_us4_4.py | 111 | 10 |
| backend | tests/test_cancel_event_us4_6.py | 104 | 12 |
| backend | tests/test_venue_turnaround.py | 93 | 9 |
| backend | tests/test_safety_decision_us17_2.py | 92 | 11 |
| backend | tests/test_event_needs.py | 89 | 9 |
| backend | tests/test_booking_conflicts.py | 84 | 12 |
| backend | tests/test_venues.py | 81 | 11 |
| backend | tests/test_venue_holds.py | 75 | 10 |
| backend | tests/test_venue_bookings.py | 64 | 9 |
| backend | tests/test_booking_decisions.py | 57 | 8 |
| backend | tests/test_equipment.py | 55 | 8 |
| backend | tests/test_events.py | 54 | 12 |
| backend | tests/test_event_decisions.py | 53 | 6 |
| backend | tests/test_suitability.py | 53 | 6 |
| backend | tests/test_registration_us20_2.py | 45 | 6 |
| backend | tests/test_venue_suitability.py | 41 | 5 |
| backend | tests/test_booking_store.py | 40 | 3 |
| backend | tests/test_venue_availability_us12_3.py | 37 | 5 |
| backend | tests/test_safety_review_us17_1.py | 37 | 6 |
| backend | tests/test_change_review_us11_2.py | 36 | 8 |
| backend | tests/test_event_clarification.py | 34 | 6 |
| backend | tests/test_registration_store.py | 34 | 3 |
| backend | tests/test_venue_booking_cancellation.py | 34 | 7 |
| backend | tests/test_registration_db.py | 34 | 10 |
| backend | tests/test_venue_unavailability_store.py | 32 | 2 |
| backend | tests/test_venue_delete_us9_5.py | 30 | 5 |
| backend | tests/test_registration_us20_3.py | 29 | 5 |
| backend | tests/test_replacement_venue_us14_5.py | 28 | 6 |
| backend | tests/test_venue_store.py | 26 | 2 |
| backend | tests/test_equipment_reservations.py | 26 | 6 |
| backend | tests/test_equipment_store.py | 25 | 2 |
| backend | tests/test_remaining_guards.py | 23 | 3 |
| backend | tests/test_notifications.py | 23 | 5 |
| backend | tests/test_access_enforcement.py | 20 | 4 |
| backend | tests/test_change_review_paths.py | 20 | 2 |
| backend | tests/test_coordinator_notifications.py | 20 | 5 |
| backend | tests/test_venue_search_filters.py | 19 | 5 |
| backend | tests/test_lifecycle_us4_5.py | 18 | 6 |
| backend | tests/test_hold_expiry_us14_4.py | 18 | 6 |
| backend | tests/test_auth_login.py | 17 | 5 |
| backend | tests/test_event_route_guards.py | 16 | 2 |
| backend | tests/test_event_store_queries.py | 14 | 2 |
| backend | tests/test_lead_reassignment.py | 14 | 6 |
| backend | tests/test_sessions.py | 12 | 3 |
| backend | tests/test_supabase_config.py | 12 | 2 |
| backend | tests/test_user_store.py | 11 | 1 |
| backend | tests/test_lead_assignment.py | 11 | 5 |
| backend | tests/test_users.py | 10 | 2 |
| backend | tests/test_new_role_auth.py | 9 | 3 |
| backend | tests/test_auth_logout.py | 9 | 3 |
| backend | tests/test_notification_store.py | 7 | 1 |
| backend | tests/test_coordinator_assignment.py | 7 | 1 |
| backend | tests/test_unassigned_queue.py | 6 | 3 |
| backend | tests/test_config.py | 5 | 1 |
| backend | tests/test_lead_rls.py | 4 | 2 |
| backend | tests/test_equipment_reservations_db.py | 4 | 4 |
| backend | tests/test_equipment_item_migration_db.py | 4 | 2 |
| backend | tests/test_hold_expiry_db.py | 3 | 3 |
| backend | tests/test_security.py | 2 | 1 |
| backend | tests/test_health.py | 2 | 1 |
| backend | tests/test_seed_equipment.py | 1 | 1 |
| backend | tests/test_draft_store.py | 1 | 0 |
| frontend | src/components/EventBookings.test.tsx | 74 | 12 |
| frontend | src/status.test.ts | 63 | 5 |
| frontend | src/venuesStore.test.ts | 63 | 4 |
| frontend | src/components/SafetyCheckPanel.test.tsx | 51 | 6 |
| frontend | src/pages/EventChangeRequest.test.tsx | 44 | 6 |
| frontend | src/permissions.test.ts | 43 | 3 |
| frontend | src/components/VenueUnavailability.test.tsx | 43 | 5 |
| frontend | src/pages/EventDetailPage.test.tsx | 42 | 7 |
| frontend | src/pages/VenueFormPage.test.tsx | 42 | 5 |
| frontend | src/eventsStore.test.ts | 41 | 4 |
| frontend | src/venueTurnaround.test.ts | 36 | 3 |
| frontend | src/registrationStore.test.ts | 35 | 3 |
| frontend | src/pages/NewEventPage.test.tsx | 33 | 7 |
| frontend | src/pages/VenuesPage.test.tsx | 32 | 5 |
| frontend | src/draftRules.test.ts | 31 | 4 |
| frontend | src/eventNeeds.test.ts | 30 | 2 |
| frontend | src/App.test.tsx | 29 | 4 |
| frontend | src/components/EventRegistration.test.tsx | 29 | 5 |
| frontend | src/eventsStore.calls.test.ts | 28 | 0 |
| frontend | src/components/VenueAvailability.test.tsx | 28 | 4 |
| frontend | src/api.test.ts | 27 | 4 |
| frontend | src/pages/pages.paths.test.tsx | 26 | 0 |
| frontend | src/pages/VenueDetailPage.test.tsx | 25 | 4 |
| frontend | src/equipmentStore.test.ts | 22 | 2 |
| frontend | src/components/CancelEventPanel.test.tsx | 22 | 4 |
| frontend | src/pages/EventDetailPage.paths.test.tsx | 22 | 2 |
| frontend | src/pages/NotificationsPage.test.tsx | 22 | 4 |
| frontend | src/App.routes.test.tsx | 20 | 3 |
| frontend | src/holdsStore.test.ts | 20 | 2 |
| frontend | src/pages/EventClarification.test.tsx | 19 | 3 |
| frontend | src/venuesStore.calls.test.ts | 18 | 0 |
| frontend | src/components/EventEquipment.test.tsx | 18 | 4 |
| frontend | src/pages/UnassignedQueuePage.test.tsx | 17 | 4 |
| frontend | src/pages/BookingRequestsPage.test.tsx | 15 | 4 |
| frontend | src/pages/AttendPage.test.tsx | 14 | 3 |
| frontend | src/router.test.ts | 13 | 1 |
| frontend | src/components/EventNeedsFields.test.tsx | 13 | 3 |
| frontend | src/components/VenueHolds.test.tsx | 13 | 3 |
| frontend | src/pages/MyRegistrationsPage.test.tsx | 13 | 3 |
| frontend | src/pages/EventDecision.test.tsx | 12 | 3 |
| frontend | src/pages/TeamAssignmentsPage.test.tsx | 12 | 2 |
| frontend | src/components/SafetyReviewDetails.test.tsx | 11 | 2 |
| frontend | src/pages/SignInPage.test.tsx | 11 | 3 |
| frontend | src/session.test.ts | 10 | 2 |
| frontend | src/pages/EventsPage.test.tsx | 10 | 2 |
| frontend | src/status.messages.test.ts | 9 | 0 |
| frontend | src/components/EquipmentReservation.test.tsx | 9 | 3 |
| frontend | src/components/EventBookings.replacement.test.tsx | 9 | 3 |
| frontend | src/components/EventEquipment.paths.test.tsx | 9 | 0 |
| frontend | src/pages/BookingConflictsPage.test.tsx | 9 | 2 |
| frontend | src/pages/EquipmentPage.paths.test.tsx | 9 | 0 |
| frontend | src/unassignedQueueStore.test.ts | 8 | 1 |
| frontend | src/components/TopNav.test.tsx | 8 | 2 |
| frontend | src/pages/EquipmentPage.test.tsx | 8 | 3 |
| frontend | src/bookingRequestsStore.test.ts | 7 | 1 |
| frontend | src/pages/EquipmentRequestDetailPage.paths.test.tsx | 6 | 0 |
| frontend | src/pages/SafetyReviewPage.test.tsx | 5 | 2 |
| frontend | src/notificationsStore.test.ts | 4 | 1 |
| frontend | src/useIdleSignOut.test.ts | 4 | 1 |
| frontend | src/api.errors.test.ts | 3 | 1 |
| frontend | src/bookingConflictsStore.test.ts | 3 | 0 |
| frontend | src/pages/EquipmentRequestDetailPage.test.tsx | 3 | 2 |
| frontend | src/components/StatusBadge.test.tsx | 2 | 1 |
| frontend | src/components/StatusTimeline.test.tsx | 2 | 1 |
| frontend | src/pages/EquipmentQueuePage.test.tsx | 2 | 1 |
