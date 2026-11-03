# ConnectSphere user-story, acceptance-criteria and test-suite audit

Audit date: 3 November 2026; refreshed at `main` commit `9770290`  
Scope: current working tree after fast-forwarding `main`, including restored uncommitted files shown by `git status`  
Purpose: identify what the current tests prove, where ACs are stale or incomplete, and how to reduce the suite to a set the team can independently review and defend.

## 1. Executive overview

The repository has strong automated coverage but an indefensible quantity of tests for a five-person student team:

| Layer | Current result | Current size |
|---|---:|---:|
| Backend pytest | 2,504 passed, 10 skipped | 2,512 collected cases; 29,832 test lines |
| Frontend Vitest | 1,400 passed | 65 files; 18,327 test lines |
| Configured Playwright | 43 tests | 33 shared/live tests + 10 isolated tests; 1,339 lines |
| CI Postgres integration | 28 named test functions | Four modules; excluded from normal pytest collection and potentially expanded by parameterization |
| **Total configured automated cases** |  | **At least 3,983** |
| Manual test plans | 58 Jira stories / 59 manual cases | 6,969 lines |

Backend coverage is 100% statements and branches. Frontend coverage is 100% statements/lines/functions and 94.81% branches. Those numbers are genuine measurements, but the suite contains extensive duplication and coverage-driven tests that do not each represent a separate customer behavior.

The defensible post-pull target is approximately **660 automated cases**:

| Proposed layer | Target |
|---|---:|
| Backend feature/API tests | 350–390 |
| Backend database/integration and essential store tests | 40–50 |
| Frontend tests | 200–230 |
| Isolated browser E2E | 20, one per baseline E2E scenario |
| **Target total** | **610–690** |

With five reviewers, 660 cases means about 132 cases per person. That is demanding but reviewable in one concentrated day. Reviewing roughly 4,000 cases is not credible.

The pulled release has already corrected several stale tests and workflows: Safety approval is separate from Coordinator confirmation, accepted important changes reopen Planning, confirmed venue replacement reopens Planning, and production reassignment has a focused migration. Reduction must preserve representative regression coverage for those fixes while removing their newly added duplication.

## 2. What is creating the volume

### Backend

The backend now has 1,855 separately defined test functions. Parameterization expands those by another 657 cases to 2,512 collected cases. Parameterization is therefore only about a quarter of the problem.

| Category | Current cases | Assessment |
|---|---:|---|
| Feature/API files | 2,212 | Good behavior coverage, but severe duplication within large files |
| Store/client plumbing | 219 | Many mapping, `None`, empty-response and fake-client cases can be consolidated |
| Coverage/guard files | 73 | Primarily introduced to reach 100%; unique cases should move into owning feature files |
| Opt-in DB modules | 8 collected cases | Valuable when executed, but local unit success does not prove them; pytest reports 10 skips because two modules also skip at collection time |

The largest files alone account for most of the suite:

| File | Cases | Named test functions | Parameter expansion | Suggested target |
|---|---:|---:|---:|---:|
| `test_change_requests.py` | 186 | 113 | 73 | 25–30 |
| `test_venue_unavailability.py` | 148 | 83 | 65 | 20–25 |
| `test_registration_us20_1.py` | 122 | 73 | 49 | 20–25 |
| `test_safety_check_us4_4.py` | 111 | 54 | 57 | 15–20 after AC correction |
| `test_cancel_event_us4_6.py` | 104 | 75 | 29 | 10–15 |
| `test_venue_turnaround.py` | 93 | 50 | 43 | 12–18 |
| `test_safety_decision_us17_2.py` | 93 | 71 | 22 | 15–20 after AC correction |
| `test_event_needs.py` | 89 | 39 | 50 | 12–18 |
| `test_booking_conflicts.py` | 84 | 76 | 8 | 18–22 |
| `test_venues.py` | 81 | 81 | 0 | 12–18 |
| `test_venue_holds.py` | 75 | 55 | 20 | 10–14 |
| `test_venue_bookings.py` | 64 | 54 | 10 | 12–16 |
| `test_booking_decisions.py` | 57 | 47 | 10 | 12–16 |
| `test_equipment.py` | 55 | 39 | 16 | 16–20 |
| `test_events.py` | 54 | 54 | 0 | 12–16 |
| `test_suitability.py` | 53 | 43 | 10 | 10–14 |
| `test_event_decisions.py` | 54 | 23 | 31 | 10–14 |

New post-pull feature suites should also be consolidated rather than accepted wholesale:

| File | Cases | Suggested target | What must survive |
|---|---:|---:|---|
| `test_confirm_event_us4_7.py` | 29 | 10–12 | current Safety approval, readiness blockers, assigned Coordinator-only confirmation, atomic stale case |
| `test_reconfirm_us11_3.py` | 25 | 9–11 | important/routine/rejected distinction, Planning reflow, arrangement flags, fresh Safety and reconfirmation |
| `test_reassignment_us8_4.py` | 25 | 8–10 | active/closed rules, access transfer, both notices, audit names, stale write |
| `test_attendee_notices_us10_4.py` | 18 | 6–8 | date/time notice, replacement-venue notice, registered-only privacy, read toggle, best-effort failure |
| `test_venue_problem_us12_4.py` | 13 | 7–9 | Confirmed warning, Coordinator replacement action, Planning reflow and preserved other bookings |
| `test_notifications_us10_3.py` | 8 | 4–5 | all Leads on submission, Organiser on confirmation, recipient isolation/read state |

### Frontend

| Category | Current cases | Suggested target | Reason |
|---|---:|---:|---|
| `*.paths` / `*.calls` / route-coverage files | 146 | 15–25 | Move unique behaviors into normal feature tests; remove coverage-only permutations |
| Store/API tests | 235 | 50–70 | Keep request shape, error translation and state transitions; remove repeated fetch plumbing |
| Component/page tests | 750 | 120–150 | Keep customer-visible states/actions, consolidate rendering and failure permutations |
| Auth/routing/shared-rule tests | 269 | 30–45 | `status`, `permissions`, `draftRules` and `eventNeeds` have heavy table duplication |

Largest frontend targets:

- `EventBookings.test.tsx`: 75 → 12–16.
- `venuesStore.test.ts`: 63 → 8–12.
- `status.test.ts`: 63 → 8–10.
- `SafetyCheckPanel.test.tsx`: 60 → 12–16; preserve the new Safety-approved/Coordinator-confirm UI.
- `EventChangeRequest.test.tsx`: 48 → 10–14.
- `permissions.test.ts`: 43 → 8–10.
- `VenueUnavailability.test.tsx`: 43 → 10–12.
- `VenueFormPage.test.tsx`: 42 → 10–12.
- `EventDetailPage.test.tsx`: 42 → 12–16.
- `eventsStore.test.ts`: 41 → 8–12.
- `venueTurnaround.test.ts`: 36 → 6–8.
- `registrationStore.test.ts`: 35 → 8–10.
- `draftRules.test.ts`: 31 → 6–8.
- `eventNeeds.test.ts`: 30 → 8–10.

## 3. AC versioning problems that must be resolved before pruning

The manual plan faithfully records Jira history, but some early ACs are no longer the current product requirement. A reviewer cannot treat every historical AC as simultaneously valid.

1. **US8.1 is superseded.** It requires automatic round-robin assignment. Week 7 and US8.2 require no auto-assignment. Keep one regression proving submission remains unassigned; remove tests that expect round-robin.
2. **Early “any Coordinator” ACs are superseded.** US4.1, US5.1, US5.2, US7.1 and US7.3 originally allowed any Coordinator. US8.6 now requires assignment-scoped access. Retain current assignment-scoped tests, not both versions.
3. **US2.1 original validation is superseded by the reopened story.** The original AC makes several needs fields optional; the reopened AC makes them mandatory with “None / Not required.” Retain the reopened rule and a small draft exception set.
4. **US9.1c is superseded by US9.5.** Hard deletion without booking checks was only valid before bookings existed. Test the current future-booking guard.
5. **US12.1 is extended by US12.2.** It no longer only records/display closures; production triggers identify affected bookings.
6. **US4.4 and US17.2 historical ACs conflict with the later customer clarification.** The pulled US4.7 implementation/tests now correctly leave the event Pending Safety Check after approval until the assigned Coordinator confirms. The manual/Jira traceability must mark the older direct-confirm wording superseded.
7. **US12.2 is extended by US12.4 for Confirmed events.** A closure flags/notifies while preserving the event; the Coordinator's replacement request then atomically moves Confirmed to Planning. Retain the distinction in the AC history.
8. **US14.3 is incomplete.** Current AC covers setting expiry, but the customer also said Venue Staff can update hold expiry. No update endpoint exists.
9. **US11.2 is extended by US11.3 for post-Confirmed changes.** Accepted important Organiser changes now reopen Planning and require fresh Safety/confirmation. Direct Coordinator edits of Confirmed fields remain a separate unresolved contradiction.

These are requirement-management issues, not reasons to inflate the test count. Each superseded rule needs one clear note in the traceability document so the team can explain why obsolete tests were removed.

## 4. Story-by-story audit

Status meanings:

- **Aligned:** implementation and current AC agree.
- **Superseded:** historical AC was intentionally replaced; only the current rule should remain tested.
- **Partial:** some AC behavior or production proof is missing.
- **Contradicts customer:** Jira/test expectation conflicts with the later authoritative clarification.
- **Manual/deliverable:** best verified by repository/setup inspection rather than a large automated unit suite.

### Sprint 1 stories

| Story | AC/implementation audit | Current evidence | Retention decision |
|---|---|---|---|
| US1.1 Login | **Aligned.** Valid/invalid credentials, role landing and idle session are implemented. | `test_auth_login.py`, `SignInPage.test.tsx`, authentication Playwright | Keep 6–8 total: success, invalid, unknown-user indistinguishability, role-derived landing, idle expiry and one E2E. |
| US1.2 Logout | **Aligned.** Token invalidation and protected-route refusal exist. | `test_auth_logout.py`, `App.test.tsx`, authentication Playwright | Keep 3–4 total. Multiple post-logout pages are redundant. |
| US1.3 Access enforcement | **Aligned at API level.** Clear 401/403/404 behavior exists. | `test_access_enforcement.py`, `permissions.test.ts`, authentication Playwright | Keep permission-catalogue invariant, one allowed, one forbidden, one signed-out and a small role-routing table. Do not retain a separate 403 case for every role on every route. |
| US2.1 Original create/submit | **Superseded by reopened US2.1.** Original “optional needs” rule is no longer current. | `test_events.py`, `test_event_needs.py`, `NewEventPage.test.tsx` | Merge with reopened story. Retain persistence, valid submit and central validation boundaries; remove tests preserving optional-field behavior. |
| US2.2 Drafts | **Aligned.** Partial draft, ownership, resume and full validation on submit work. | `test_events.py`, `test_event_needs.py`, `draftRules.test.ts`, `NewEventPage.test.tsx` | Keep 8–10 across backend/frontend; one partial draft and one hidden-from-other-user scenario are enough. |
| US3.1 My events | **Aligned.** Organiser ownership filtering and detail/read-only behavior exist. | `test_events.py`, `EventsPage.test.tsx`, `EventDetailPage.test.tsx` | Keep 5–7. Do not reproduce the same ownership check across list, page and every store method. |
| US4.1 Status display | **Superseded in access scope; aligned in labels.** “Any Coordinator” was narrowed by US8.6. | `test_events.py`, `status.test.ts`, status components | Keep one canonical status table and 3–4 rendering/visibility tests. Sixty-three frontend status cases are unnecessary. |
| US4.2 Base transitions/audit | **Aligned.** Save stays Draft, submit happens once, history records actor/time. | `test_events.py`, lifecycle/status tests | Keep 5–7. Audit structure should be tested once, not on every transition in every layer. |
| US5.1 Coordinator view | **Superseded in scope.** Assigned Coordinator only is current. | `test_events.py`, assignment-scoped tests | Keep 3–4: assigned can read, unassigned/other cannot, all fields present. |
| US5.2 Coordinator edit | **Partial against current customer rules.** General edits/audit work, but Confirmed events can still be directly edited; US11.3 only fixes reviewed Organiser changes. | `test_change_requests.py`, `test_change_review_us11_2.py`, `test_reconfirm_us11_3.py`, Event detail tests | Keep 8–10 after adding a Confirmed-edit refusal. Delete tests that merely enumerate every editable field separately. |
| US6.1 Repo/CI/setup | **Partial manual deliverable.** CI and run instructions exist; README uses `git clone <this repo>` and instructor access cannot be proven from the snapshot. | `.github/workflows/ci.yml`, README, `test_cases_us6_1.md` | No large unit suite needed. Keep a manual checklist plus CI itself. |
| US6.2 Core schema | **Partial manual/integration deliverable.** Schema exists but migration ordering is manual, an essential SQL patch is untracked, and C4/schema documentation is incomplete. | `SUPABASE_*.sql`, README migration table | Verify with one clean-database migration integration job. Unit tests of fake query objects do not prove this AC. |

### Sprint 2 stories

| Story | AC/implementation audit | Current evidence | Retention decision |
|---|---|---|---|
| US4.3 Review transitions | **Aligned.** Under Review to Approved/Rejected guards work. | `test_event_decisions.py`, lifecycle tests | Keep 6–8 including invalid transition, required reject reason and audit. |
| US7.1 Review decision | **Superseded in actor scope; otherwise aligned.** Only assigned Coordinator is current. | `test_event_decisions.py`, `EventDecision.test.tsx` | Keep 6–8; remove old “any Coordinator” cases and repeated reason lengths. |
| US7.3 Clarification | **Superseded in actor scope; otherwise aligned.** Comment tracking and organiser visibility work. | `test_event_clarification.py`, `EventClarification.test.tsx` | Keep 6–8: assigned, message required, visible/history, organiser response, one unauthorized. |
| US8.1 Auto-assignment | **Superseded and now deliberately false.** | `test_coordinator_assignment.py` | Keep only 2 regression cases: submission remains unassigned with zero or many Coordinators. Delete round-robin-era expectations. |
| US9.0 Venue seeds | **Aligned manual/setup story.** Seed data exists. | seed SQL/scripts, manual plan | Keep one idempotent seed smoke test or manual verification, not per-row unit tests. |
| US9.1a Create venue | **Aligned.** Required fields, role restriction and optional catalogue fields exist. | `test_venues.py`, `VenueFormPage.test.tsx` | Keep 6–8. Collapse per-field invalid inputs into equivalence classes. |
| US9.1b Update venue | **Aligned.** Venue Staff update allowed fields. | venue API/store/UI tests | Keep 4–6. One full update plus auth/not-found/validation boundaries. |
| US9.1c Delete venue | **Superseded by US9.5.** | `test_venues.py`, `test_venue_delete_us9_5.py` | Remove pre-booking assumptions; retain current no-future-booking and guarded-delete cases under US9.5. |
| US9.2 Catalogue | **Aligned; “no filtering” historical limitation superseded by US9.3.** | venue list/detail tests | Keep 4–5 list/detail/read-only tests. |
| US9.3 Search/filter | **Aligned.** Combined AND filters cover date/time, capacity, location, accessibility, layout and facilities. | `test_venue_search_filters.py`, `VenuesPage.test.tsx`, store tests | Keep 8–12 using one combined happy path, one per distinct filter algorithm, and malformed date/time. |
| US10.1 Organiser notifications | **Aligned.** Create/list/read-toggle works. | `test_notifications.py`, `NotificationsPage.test.tsx` | Keep 7–9. Test ordering/toggle/ownership once. |
| US11.1 Organiser change request | **Aligned for proposals.** Direct submitted edit is blocked and important/routine classification exists. | `test_change_requests.py`, `EventChangeRequest.test.tsx` | Reduce 186-file footprint sharply: keep proposal happy path, direct-edit refusal, one important/routine mixed case, validation, ownership, concurrency and history. |
| US12.1 Venue unavailability | **Aligned as base feature; extended by US12.2.** | `test_venue_unavailability.py`, UI tests | Keep date validation, role, persistence/display and one overlap handoff to US12.2. |

### Sprint 3 stories

| Story | AC/implementation audit | Current evidence | Retention decision |
|---|---|---|---|
| US1.4 New roles | **Aligned.** Lead and Safety roles, landing routes and baseline permissions exist. | `test_new_role_auth.py`, access tests, assignment Playwright | Keep 4–6. Role enum/permission/landing tables can be one parameterized test. |
| US2.1 Reopened | **Aligned.** Mandatory needs, fixed options, none/not-required and draft exception exist. | `test_event_needs.py`, `eventNeeds.test.ts`, form tests | Keep 12–15 across layers. One missing-field table is enough; do not test every blank/whitespace variant at API, helper and page levels. |
| US4.5 Lifecycle completion | **Aligned with the new extensions.** Assignment/planning/completion guards work; US4.7 and US11.3 now supply the corrected confirmation/reconfirmation paths. | `test_lifecycle_us4_5.py`, `test_confirm_event_us4_7.py`, `test_reconfirm_us11_3.py` | Keep one canonical lifecycle matrix plus focused actor/atomic tests; avoid duplicating every transition in three files. |
| US8.2 Unassigned queue | **Aligned.** Oldest-first queue and Lead-only view work. | `test_unassigned_queue.py`, queue page/store tests | Keep 5–7. Search is a UI concern; queue scope/order belongs to backend. |
| US8.3 Lead assignment | **Aligned for initial assignment.** Queue removal, status, audit and notification work. | `test_lead_assignment.py`, `test_coordinator_notifications.py`, Playwright | Keep 7–9 including stale/invalid Coordinator and one E2E. |
| US8.6 Assignment-scoped access | **Partial proof.** FastAPI enforces it, but AC5 says RLS/database enforcement and normal API stores use the Supabase service role. | access/event tests, `test_lead_rls.py` | Keep a concise cross-route authorization matrix and add one real Postgres/RLS test. Do not repeat every endpoint/role permutation in unit tests. |
| US9.4 Setup/turnaround fields | **Aligned.** Persistence, visibility and recheck trigger work. | `test_venue_turnaround.py`, form/detail tests | Keep 10–14 including zero, customer boundary example, update-triggered recheck and role guard. |
| US10.2 Coordinator notifications | **Aligned for reassignment after the pull.** The production RPC atomically notifies old/new Coordinators; other trigger families remain. | `test_coordinator_notifications.py`, `test_reassignment_us8_4.py`, DB integration | Keep one representative per trigger plus atomic reassignment DB proof; helper-only duplicates can go. |
| US14.1 Multi-venue requests | **Aligned.** Independent booking rows/checks and assignment guard exist. | `test_venue_bookings.py`, `EventBookings.test.tsx` | Keep 10–12 including multiple bookings, independent failure, initial Planning transition, assignment guard and one UI/E2E path. |
| US14.2 Cancel one booking | **Aligned.** Reason/audit, slot release and other-booking preservation work. | `test_venue_booking_cancellation.py`, booking UI tests | Keep 7–9. |
| US14.3 Holds | **Aligned with Jira AC, partial against customer clarification.** Set/convert/occupy works; expiry cannot be updated. | `test_venue_holds.py`, hold component/store tests | Keep 8–10 and add one update-expiry story/test after implementation. Remove repeated status/refusal permutations. |
| US15.1 Conflict window | **Aligned.** Setup/turnaround, holds, requests, confirmed bookings, closures and touching-boundary rule work. | `test_booking_conflicts.py`, decision/suitability tests | Keep 16–20 because this is genuinely high risk: customer example, touch boundary, each active/inactive class, closure, privacy and atomic race. |
| US15.2 Recheck existing bookings | **Aligned.** Flags, notifications and resolution without deletion work. | conflict/turnaround tests, conflict UI | Keep 10–12: new clash, unaffected, no deletion, notice, resolve, failure isolation. |
| US16.1 Venue Staff decision | **Aligned.** Atomic recheck, approve/reject, reason, independence and notification work. | `test_booking_decisions.py`, requests page | Keep 12–15 including race/atomic database behavior. |
| US18.1 Suitability | **Aligned.** Headcount-per-booking and all stated factors work. | `test_suitability.py`, `test_venue_suitability.py`, booking component | Keep 10–12. Preserve capacity equality/+1 and one combined missing-requirements case. |
| US19.0 Equipment seeds | **Aligned manual/setup story.** | seed script and smoke test | Keep one idempotent smoke test. |
| US19.1 Equipment catalogue | **Aligned.** CRUD/role/out-of-service fields exist. | `test_equipment.py`, equipment page tests | Keep 8–10 catalogue cases. |
| US19.2 Equipment request | **Aligned.** Assigned Coordinator request/edit/remove and Tech queue/notes work. | `test_equipment.py`, equipment components/pages | Keep 9–12. Avoid re-testing generic validation already covered by request schema. |

### Sprint 4 stories

| Story | AC/implementation audit | Current evidence | Retention decision |
|---|---|---|---|
| US4.4 Pending Safety Check | **Historical AC superseded; current implementation aligned via US4.7.** Safety approval records approval while status remains Pending Safety Check; assigned Coordinator separately confirms. | `test_safety_check_us4_4.py`, `test_confirm_event_us4_7.py`, `SafetyCheckPanel.test.tsx` | Keep 18–22 across readiness, approval and confirmation; consolidate the current 111+29 backend and 60 frontend cases. |
| US4.6 Event cancellation | **Aligned with its Jira story but outside the original Release 1 core.** | `test_cancel_event_us4_6.py`, cancel panel | Keep 10–12 high-value cascade/authorization/audit cases. Remove exhaustive notification/persistence permutations. If schedule collapses, this is the documented first story to deprioritize. |
| US8.4 Reassignment | **Aligned after the pull.** A focused committed RPC handles active events, access transfer, named audit and both notifications; closed events are refused. | `test_reassignment_us8_4.py`, `test_lead_reassignment.py`, `integration/test_us8_4_db.py` | Keep 8–10 total; merge/delete the older overlapping Lead/helper cases. |
| US8.5 Team assignments | **Aligned.** Active filtering, Coordinator filter/count and read-only view exist. | `TeamAssignmentsPage.test.tsx` | Keep 6–8. |
| US9.5 Guarded venue deletion | **Aligned in feature tests.** | `test_venue_delete_us9_5.py`, isolated Playwright | Keep 6–8: future active blocks, inactive/past allows, “mark unavailable” message and DB referential guard. |
| US11.2 Change review | **Aligned for reviewed Organiser changes through US11.3.** Important Confirmed changes reopen Planning, recheck and require fresh Safety/confirmation. Direct Coordinator edits remain outside this corrected path. | `test_change_review_us11_2.py`, `test_reconfirm_us11_3.py`, integration DB test, change UI | Keep 14–17 across base review and reconfirmation; consolidate fake/store error branches. |
| US12.2 Unavailability impacts | **Aligned for Confirmed-event reflow through US12.4, with parity risk retained.** Coordinator replacement action reopens Planning; fake and SQL paths now have CI integration coverage. | `test_venue_unavailability.py`, `test_venue_problem_us12_4.py`, `integration/test_us12_4_db.py` | Keep 14–17 split between route and real Postgres trigger; remove the current 148-case duplication. |
| US12.3 Availability view | **Aligned.** Correct entry types, ordering, buffers and inactive filtering exist. | `test_venue_availability_us12_3.py`, component tests | Keep 8–10. |
| US14.4 Hold expiry | **Aligned.** Effective expiry, scheduler, history and notifications exist. | `test_hold_expiry_us14_4.py`, opt-in DB test | Keep 8–10, including one real DB sweep case. |
| US14.5 Replacement venue | **Production path is now committed through US12.4.** The wrapper RPC requests the replacement and reopens a Confirmed event atomically; README and CI include it. | `test_replacement_venue_us14_5.py`, `test_venue_problem_us12_4.py`, `integration/test_us12_4_db.py` | Keep 9–12 plus DB integration; delete obsolete assumptions tied to the untracked repair bundle. |
| US17.1 Safety review queue | **Aligned with Jira AC, partial against customer detail.** Queue/read-only/data works, but explicit emergency access, equipment placement and crowd movement are absent. | `test_safety_review_us17_1.py`, safety details/page tests | Keep 8–10 after resolving data scope. |
| US17.2 Safety decision | **Current implementation aligned through US4.7; historical AC wording remains stale.** Approval records a current decision and notifies Coordinator without changing status; request/reject still return to Planning. | `test_safety_decision_us17_2.py`, `test_confirm_event_us4_7.py`, safety component and isolated E2E | Retain 15–20 across decisions and separate confirmation; remove duplicated validation/status assertions. |
| US19.3 Equipment availability/reservation | **Aligned.** Overlap and out-of-service subtraction, reserve/unavailable and notifications work. | equipment reservation/API/store/DB tests | Keep 12–15, preserving the customer’s 10−2−6 example and one concurrency/atomic DB test. |
| US20.1 Registration | **Aligned with Jira AC.** Capacity, privacy, uniqueness, last-place race and full notice work. | `test_registration_us20_1.py`, registration DB/store/component/Attend tests | Keep 16–20 because capacity concurrency is high risk. Remove repeated validation and notification failure permutations. |
| US20.2 Withdrawal | **Aligned.** Status/list, pre-start withdrawal, capacity release and re-register work. | `test_registration_us20_2.py`, My Registrations/store tests | Keep 8–10. |
| US20.3 Managed registrations | **Aligned.** Owner/assigned Coordinator scope and attendee privacy work. | `test_registration_us20_3.py`, registration component/store tests | Keep 7–9. |

## 5. Exact consolidation plan

### Wave 1 — remove coverage scaffolding and obvious duplication

Expected reduction: approximately 700–900 cases.

1. Merge unique tests from these backend files into their owning feature and then remove the generic files:
   - `test_remaining_guards.py`
   - `test_event_route_guards.py`
   - most of `test_change_review_paths.py`
2. Reduce the 219 store/plumbing cases to roughly 50–60. Retain only:
   - row-to-domain mapping with a representative complete and legacy/null row;
   - exact atomic RPC name/payload for business-critical writes;
   - stale/empty result mapping where it changes API behavior;
   - no duplicate “query builder called `.eq()`” cases already covered by route behavior.
3. Remove or merge frontend coverage files after moving genuinely unique behavior:
   - `eventsStore.calls.test.ts`
   - `venuesStore.calls.test.ts`
   - `pages.paths.test.tsx`
   - `EventDetailPage.paths.test.tsx`
   - `EventEquipment.paths.test.tsx`
   - `EquipmentPage.paths.test.tsx`
   - `EquipmentRequestDetailPage.paths.test.tsx`
   - `App.routes.test.tsx`
4. Collapse frontend rule tables:
   - `status.test.ts`: one canonical transition/label table, not every text helper combination;
   - `permissions.test.ts`: one role-permission matrix and selected route consequences;
   - `draftRules.test.ts` / `eventNeeds.test.ts`: one equivalence case per validation rule.

### Wave 2 — consolidate the large feature files

Expected reduction: approximately 1,300–1,600 cases.

Apply these rules to every large feature file:

- Replace whitespace variants (`None`, `""`, spaces) with one representative unless parsing differs.
- Replace per-role denials with one permission-matrix test plus one route-level denial.
- Keep one below/equal/above boundary trio, not many numeric examples.
- Keep one missing and one malformed ID if they produce different errors; otherwise one.
- Keep one notification write-failure case globally per best-effort notification helper, not once per trigger.
- Test audit `who/when` once per action family, not for every refusal.
- Do not separately test the same validation rule in helper, store, route, component and page. Assign ownership to the lowest reliable layer and keep one UI display case.
- Preserve concurrency tests only where a transaction/lock/unique constraint is the requirement.

### Wave 3 — rebuild a small E2E layer

Expected final E2E count: 20 isolated scenarios.

The current Playwright situation is not defensible:

- 33 tests target a shared/live environment and are not run by CI.
- The 10 isolated tests now pass after aligning `backend/e2e_server.py` with the documented `@connectsphere.com` / `password` accounts and correcting the stale Safety auto-confirm scenario.
- Replacement-venue specs are ignored by the normal configuration.

Use one isolated E2E per baseline E2E-1…E2E-20. Each should test a complete role handoff. Remove smaller browser tests already proved at unit/API level, such as separate unknown-email and wrong-password browser cases.

## 6. What must not be cut

Retain these even if coverage remains high without them:

- Every current server-side access boundary and event-relationship rule.
- The customer’s exact setup/turnaround example and touching-window boundary.
- Database atomicity for double booking, last registration place, equipment stock and status compare-and-set.
- Active versus expired hold behavior.
- Confirmed-event changes and confirmed-event venue-unavailability regression tests after those workflows are fixed.
- Safety request-changes/reject/re-review/fresh-decision workflow.
- Reassignment old/new access, audit and both notifications against real Postgres.
- Multi-venue independence and replacement preserving other bookings.
- Equipment overlap and out-of-service arithmetic.
- Registration privacy, capacity and withdrawal.
- One end-to-end test per baseline E2E scenario.

## 7. Coverage policy after reduction

Do not lower coverage thresholds before the first consolidation pass. Hundreds of tests can be removed without losing a single covered branch because many cases execute the same code.

After the first pass:

1. Run coverage and inspect what actually became uncovered.
2. Restore a test only if the uncovered behavior represents a requirement, meaningful failure, security boundary or transaction rule.
3. Do not restore cases solely to execute defensive formatting/fake-client branches.
4. If 100% requires tests the team cannot independently justify, use an honest threshold such as 95% lines and 90% branches and document the excluded defensive paths.

The professor’s independent-review instruction takes precedence over an artificial coverage claim. A smaller reviewed suite with explicit gaps is more defensible than 100% coverage generated by tests nobody understands.

## 8. Human review package

Every retained test should receive a row in a review ledger:

| Story/AC | Automated test | Layer | Unique defect it catches | Human reviewer | Result |
|---|---|---|---|---|---|

Approval questions:

1. Which current AC or customer requirement does this test prove?
2. Is that AC still current, or was it superseded?
3. What distinct defect would survive if this test were removed?
4. Is the behavior already proved at a more appropriate layer?
5. Does the test assert customer-visible behavior rather than mocks/call order?
6. Can the reviewer explain the setup, action and assertion without AI assistance?
7. Has the reviewer run the test and, for critical cases, seen it fail when the behavior is deliberately broken or the assertion inverted?

No retained test should be signed off by its original implementer alone. The existing manual plan already assigns stories across Ethan, Dylan, Ivy, Lincoln and Ariel; use that allocation for independent review.

## 9. Current execution and environment findings

- Python 3.12.5 audit environment: **2,504 passed, 10 skipped, 3 warnings**, 100% statements and branches in 83.64 seconds.
- Frontend: **1,400 passed**, 100% statements/lines/functions, 94.81% branches.
- The repository’s local `backend/.venv` currently uses Python 3.13.12 and lacks `pytest-cov` and `psycopg`; `pytest --cov` and the integration modules fail to start there. The README/CI require Python 3.12. This should be rebuilt before the final rehearsal.
- The four CI Postgres integration modules (28 named test functions, potentially more collected cases after parameterization) could not run locally because Docker/Postgres was unavailable. CI is configured to run them.
- Ten opt-in database-related pytest cases are skipped by the normal backend suite.
- Isolated Playwright: **10 passed** after repairing the fixture credentials and updating US17/US4.7 to require separate Coordinator confirmation.
- Ruff and backend byte-compilation pass after formatting the migrated seed-account line.
- The current working tree contains uncommitted credential changes, the master/manual plans, and an obsolete omnibus SQL repair file alongside the focused committed migrations. Test reduction should not accidentally discard the plans or reintroduce the obsolete SQL bundle.

## 10. Recommended one-day definition of done

The reduction is complete only when all of the following are true:

- 610–690 automated cases remain, with no unexplained coverage-only files.
- Every retained case maps to a current AC/customer requirement or a named technical risk.
- Superseded ACs are marked as such in the traceability document.
- The corrected Safety-approval/Coordinator-confirmation expectation remains covered after consolidation.
- The isolated E2E harness signs in successfully and contains one scenario for each E2E-1…20.
- Backend, frontend, database integration and isolated E2E commands all run from the documented clean environment.
- Coverage is reported honestly after reduction.
- Each team member has independently reviewed and initialled their assigned retained tests.

This is the point at which the team can credibly answer the professor’s question: not “AI generated roughly 4,000 tests and coverage is 100%,” but “we retained about 650 tests, each tied to a current AC or a specific failure risk, and every one was independently reviewed by a named team member.”
