# Gap closure, 4 November 2026: what changed in the stories, the ACs and Jira

**Why these changes were made.** Two audits on 4 November 2026 (a rule-by-rule
trace of every Week 7 change and Week 9 answer through the code, and a whole-project
audit) found places where the system, its user stories and its acceptance
criteria did not follow the customer's latest answers. The team decided to **close
the gaps in the product rather than only document them**. Changing the code meant
the user stories, their acceptance criteria, Jira and the product backlog had to
change with it, so that every story still describes what the system does and
every AC still has tests. This log records each of those changes and the customer
answer behind it.

Precedence, as in [`REQUIREMENTS_BASELINE.md`](../REQUIREMENTS_BASELINE.md):
Week 9 > Week 7 > Week 4 > Week 2. Branch: `fix/close-audit-gaps`.

## Summary

| Gap | Customer said | What was built | Stories and ACs changed |
| --- | --- | --- | --- |
| G3 / A1 | Week 9: the tentative hold starts **after** venue approval; the Coordinator confirms once Venue Staff approve | Venue Staff approve a request as a hold (Requested → Held, with an expiry); the Coordinator confirms it (Held → Confirmed) before it lapses. The hold-first route and Held → Requested are removed | US14.3 reworked (title, AC1-AC7), US14.4-AC4, US16.1-AC2 |
| G2 / A2 | Week 9: Venue Staff set **and update** the hold duration | US14.6 built: change a hold's expiry, release it with a reason; the Coordinator is told | US14.6: To Do → built, all five ACs live |
| G12 / C1 | Week 9: a Confirmed event whose venue closes reverts to planning/change review | The closure moves a Confirmed event to Planning at once, with the reason, and tells the Coordinator and the Organiser | US12.4-AC1, AC2, AC3 amended |
| G7 / A7 | Week 9: layouts are added, edited and deleted through the catalogue | The Organiser's layout choices are the standard names plus every layout a venue lists | US2.1-AC2 amended |
| G13 | Week 1 notification list | Notices for a booking requested (Venue Staff), registration opened or closed (Attendees), an Attendee withdrawing (Organiser, Coordinator) | New story US10.5 (five ACs) |
| G14 | Week 1: mobile-friendly | Phone-width Playwright check of every role's pages; two layout overflows fixed | No story change (non-functional) |
| A3 | Deliverable 6: clear run instructions | One tested fresh-install order (CI builds an empty database from it); `request_replacement_venue` committed; the seed script makes all seven roles | None |
| A5 | Rubric: coverage stated honestly | README figures replaced with measured ones | None |
| A9 | — | Duplicate test case id `TC-US8.4-01` (DB case) renumbered `TC-US8.4-09` | None |
| G6 | Week 4: one person may hold several roles | **Not built; written decision** (sign-in and every role check would change two days before submission) | Backlog note only |
| G10 | Week 4: the Organiser asks the Coordinator to withdraw | **Kept as built; written decision** (the Organiser cancels directly with a reason, the Coordinator is told) | Backlog note only |

## Jira: changes to make

Done in Jira on 4 November 2026.
Each edited story keeps its original ACs struck through above the current ones,
so the change history stays visible, and carries the label `reworked-wk9`.

- [x] **SPMG3T7-59 (US14.3)**: rename to *US14.3 Approve a booking request as a
  tentative hold with an expiry*. Keep status Done, add label `reworked-wk9`, and
  replace the description with:

  > As a Venue Staff member, I want to approve a booking request as a tentative
  > hold with an expiry, so that the venue is kept for the Coordinator while they
  > finalise, without blocking it forever.
  >
  > **Acceptance Criteria:**
  > * Venue Staff can approve a Requested booking as a tentative hold instead of
  >   confirming it outright. It becomes Held, linked to the event and its
  >   Coordinator, with the approval (who, when), who holds it and the expiry on
  >   record. Approving with no expiry still confirms outright (US16.1).
  > * The hold's expiry date/time is required and must be in the future, and no
  >   later than the booking starts.
  > * While Held and not expired, the slot counts as taken in US15.1.
  > * The assigned Coordinator confirms the held booking before it expires
  >   (Held → Confirmed). An expired hold cannot be confirmed, and its slot is free
  >   (US14.4).
  > * A Held booking is never shown or counted as Confirmed until the Coordinator
  >   confirms it, so it holds up the safety check (US4.4) until then. Venue Staff
  >   cannot decide it a second time.
  > * The Coordinator is told when Venue Staff approve a booking as a hold, and
  >   until when (US10.2).
  >
  > _Week 7 change #4, reworked 4 Nov 2026 for Week 9 (G3-5 D20, D27): the hold
  > starts after venue approval. The earlier order (Venue Staff hold first, the
  > Coordinator turns it into a request) is superseded._

- [x] **SPMG3T7-89 (US14.6)**: moved To Do → Done, priority High, assigned, Sprint 5. Replace the ACs with:

  > * Venue Staff can change the expiry of a Held booking, longer or shorter. The
  >   new expiry must be in the future, and no later than the booking start
  >   (US14.3 rule). An expired hold cannot be changed.
  > * Venue Staff can release a hold early, with a reason. Its status becomes
  >   Cancelled and the slot is freed (no longer counted in US15.1).
  > * The assigned Coordinator is notified of either change (US10.2).
  > * A release is recorded with who, when and why (US14.2's cancellation record).
  >   An expiry change is recorded in the Coordinator's notice, with the new expiry.
  > * Venue Staff only.
  >
  > _Built 4 Nov 2026 to meet Week 9 (G3-5 D21, D24)._

- [x] **SPMG3T7-87 (US12.4)**: replace the first three ACs with:

  > * When a booking on a Confirmed event is flagged "Needs replacement" (US12.2),
  >   the event moves Confirmed → Planning at once, with who marked the venue
  >   unavailable and why in its history. It is never cancelled, and its other
  >   bookings are untouched (Week 7 #2, Week 9).
  > * The Coordinator is told about the booking and that the event is back in
  >   Planning; the Organiser is told the event is back in Planning, and why.
  > * Requesting a replacement venue (US14.5) on an event still Confirmed (one
  >   flagged before this change) moves it Confirmed → Planning, with the reason
  >   recorded. The event's other bookings are untouched.
  >
  > _Amended 4 Nov 2026: Week 9 asks for "status reverting to planning/change
  > review"; the earlier AC kept the event Confirmed until a replacement was
  > requested._

- [x] **SPMG3T7-25 (US2.1)**: replace AC2 with: *Layout, facilities and
  accessibility use lists that match the venue catalogue (US9.1a). The layout list
  is the standard names plus every layout a venue in the catalogue lists, so a
  layout Venue Staff add, rename or remove on a venue is reflected (Week 9).*

- [x] **SPMG3T7-62 (US16.1)**: replace AC2 with: *Approve → booking status
  Confirmed, or Held with an expiry when approved as a tentative hold (US14.3).
  The conflict check (US15.1) runs again at approval. If the booking now clashes,
  approval is blocked and the clash is shown, so two requests for the same slot
  can't both be approved.*

- [x] **SPMG3T7-69 (US14.4)**: replace AC4 with: *Expired holds stay in history
  and can't be confirmed (US14.3 as reworked).*

- [x] **New story under the Notification System epic (SPMG3T7-20)**: created as
  **SPMG3T7-92**, *US10.5 Week 1 notifications for booking requests, registration
  and withdrawals*, Done, Sprint 5. Its key is in `docs/testing/acceptance_criteria.yaml`.

  > As an Organiser, Coordinator, Venue Staff member or Attendee, I want to be told
  > about the Week 1 events that concern me, so that nothing waits on someone who
  > does not know about it.
  >
  > **Acceptance Criteria:**
  > * When a Coordinator requests a venue booking (US14.1, or a replacement in
  >   US14.5), every Venue Staff member is notified with the venue, event and start.
  > * When registration opens for an event (US20.1), every Attendee is notified.
  >   Saving it open again notifies nobody.
  > * When registration closes, each Attendee with an active registration is
  >   notified that their place is kept.
  > * When an Attendee withdraws (US20.2), the Organiser and the assigned
  >   Coordinator are notified that a place is free again.
  > * Uses US10.1's list and read/unread toggle. In-app only, best effort.
  >
  > _Added 4 Nov 2026 to close G13 (Week 1 briefing, notifications)._

- [x] **Epics**: the 20 epics still at To Do (SPMG3T7-3 to -21 and -67) moved to
  Done; all 66 of their stories were already Done. All 22 epics are now Done.

## Product backlog workbook (`Product_Backlog.xlsx`): changes to make

The workbook is not in the repository, so these are listed for its owner. Keep
the historical rows and estimates; add the current state beside them rather than
rewriting the past.

| Where | Change |
| --- | --- |
| US14.3 row (`User Stories!F38` in the audited copy) | Replace the ACs with the US14.3 text above; add "Reworked 4 Nov 2026 for Week 9 (G3)" in the notes |
| US14.6 row (row 70) | Status Done, priority High, owner and final sprint filled in, ACs as above |
| US12.4 row | ACs as above; note "Amended 4 Nov 2026 for Week 9 (G12)" |
| US2.1 row | AC2 as above |
| US16.1 row | AC2 as above |
| New row | US10.5 as above |
| Rows for US17.2 (reopened), US4.7, US8.4 (reopened), US5.3, US11.3, US12.4, US10.3, US10.4 | Status to match Jira (Done) if the team's Definition of Done was met |
| US8.1 row | Label "Superseded by US8.2/US8.3 (Week 7 #5)"; keep its history |
| Customer Changes Impact sheet, change #2 and #4 | Record the Week 9 answers and these decisions (G2, G3, G12) |
| Known limitations | G6 (one role per account) and G10 (Organiser cancels directly), with the reasons in REQUIREMENTS_BASELINE.md section 5 |
| Table range | Extend `Table1` to cover every row (it stopped at row 60 in the audited copy) |

## In the repository

| File | What changed |
| --- | --- |
| `docs/testing/acceptance_criteria.yaml` | US14.3, US14.4-AC4, US16.1-AC2, US12.4-AC1-3, US2.1-AC2, US14.6 (now behaviour, not "not built"), new US10.5. 224 behavioural ACs, every one with a test case |
| `docs/testing/test_cases.txt` | 27 US14.3 cases rewritten for the Week 9 order; 20 US14.6, 6 US10.5, 8 US2.1 and 6 US12.4 cases added; TC-US12.2-05, TC-US14.4-05, TC-E2E-22 updated; TC-US8.4-01 (DB) renumbered TC-US8.4-09 |
| `REQUIREMENTS_BASELINE.md` | Gap table and precedence table brought up to date |
| `README.md` | Tested fresh-install order, measured coverage, CI description |

The test workbook (`docs/testing/ConnectSphere_Test_Cases.xlsx`) is generated by
`docs/testing/build_workbook.py` from a fresh test run, and should be regenerated
from the final commit before submission.
