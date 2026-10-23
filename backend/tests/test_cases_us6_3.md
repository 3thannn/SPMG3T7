# Test Cases for US6.3: Move Accounts and Events into Supabase

> As a developer on the team, I want accounts and events stored in Supabase, so
> that data survives a restart or a refresh and the server, not the browser,
> enforces the rules.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | Accounts come from Supabase; passwords are checked by Supabase Auth | Done — `auth.users` joined to `public.users` by email |
| AC2 | Events and their status history are stored in Supabase, not in server memory or `localStorage` | Done |
| AC3 | The existing schema is used as it stands | Done — no new columns or migrations in this story |
| AC4 | The test suites and CI run without Supabase credentials | Done — in-memory stores behind the same interface |
| AC5 | Missing configuration says what is missing and where to put it | Done |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Supabase Auth owns the password.** `public.users` has no credential column, so
  this project stops hashing passwords; a second copy nothing checks would only be
  something else to get wrong.
- **The session token stays this project's own** rather than Supabase's JWT, because
  a JWT cannot be revoked before it expires and US1.2 needs sign-out to end a
  session at once. Sessions are still held in the API's memory, so restarting the
  API signs everyone out; the data does not go anywhere.
- **The schema shaped two rules**: `status_changes.old_status` is NOT NULL, so the
  "Created" history entry is derived from `events.created_at`; and roles use the
  `user_role` enum's names (Event Organiser, Event Coordinator).
- **A role with no features yet is skipped**, not half-supported. A profile row with
  such a role is left out of the directory rather than crashing it.
- **Each store sits behind a swappable interface**, so tests use in-memory stores
  and CI needs no Supabase keys.

## Workflow Visualization

```
Sign in ── email, password ──► Supabase Auth (auth.users)
                                    │ ok
                                    ▼
             profile from public.users (same email) → role
                                    │
             this API issues its own session token (revocable)

Events:  /events routes ──► Repository interface
                              ├── SupabaseEvents   (events, status_changes)   ← running app
                              └── InMemoryEvents                            ← tests and CI
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `test_supabase_config.py`, `test_users.py`, `test_draft_store.py`; `test_events.py` and the auth tests run against the in-memory stores through the same interface |
| Frontend | `eventsStore.test.ts` (the page calls the API, not `localStorage`) |
| Database | the existing tables: `users`, `events`, `status_changes` (`SUPABASE_SETUP.sql`) |

---

## 1. HAPPY PATH TEST CASES

### TC-DB01: Sign in through Supabase Auth (AC1)
- **Pre-conditions**: an account in `auth.users` with a profile in `public.users` under the same email
- **Test Steps**: `POST /auth/login` with the right password
- **Expected Result**: the profile comes back with its role
- **Automated**: `test_the_right_password_returns_the_profile`, `test_a_modelled_role_becomes_a_user`

### TC-DB02: Events and their history are read from and written to Supabase (AC2)
- **Test Steps**: create, save and submit an event
- **Expected Result**: the event and its `status_changes` rows are in the Supabase tables; a draft with no date writes a NULL date and keeps its text exactly as typed
- **Automated**: `test_a_partial_draft_writes_a_null_date_without_trimming_text` (Supabase store with a fake client); the browser side: `eventsStore.test.ts` (`listEvents`, `createEvent`, `saveEvent`, `submitEvent` call the API)

### TC-DB03: Data survives a restart (AC2)
- **Test Steps**: create an event, restart the API, sign in again
- **Expected Result**: the event and its history are still there
- **Manual**

### TC-DB04: End to end against the live project (AC1, AC2)
- **Test Steps**: sign in, create, save, submit, submit again, open the event as the other role, sign out
- **Expected Result**: each works; the second submit is refused; a Coordinator sees the submitted event but not a Draft
- **Manual**: see §5

### TC-DB05: The suites run without Supabase (AC4)
- **Expected Result**: `pytest` and `vitest` pass on a machine with no `backend/.env`, as in CI
- **Automated**: every test uses the in-memory stores from `conftest.py`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-DB10: One bad profile row does not break the directory
- **Expected Result**: a row with a role this build does not model is skipped; the other users still load
- **Automated**: `test_an_unmodelled_role_is_skipped_not_raised`, `test_one_unusable_row_does_not_take_the_directory_with_it`, `test_venue_staff_became_a_modelled_role_with_us9_1`

### TC-DB11: One caller's session never leaks into another's
- **Expected Result**: each sign-in uses its own Supabase client; a client made for a user carries that user's token; the admin client is shared and can be reset
- **Automated**: `test_each_anonymous_client_is_its_own`, `test_a_user_client_carries_the_callers_token`, `test_the_admin_client_is_cached_and_droppable`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-DB20 | Wrong password | Refused | `test_a_wrong_password_is_refused` |
| TC-DB21 | An email with no Supabase Auth account | Refused | `test_an_address_with_no_credential_is_refused` |
| TC-DB22 | A Supabase Auth account with no profile row | Refused | `test_a_credential_with_no_profile_is_refused` |
| TC-DB23 | `SUPABASE_URL`, `SUPABASE_ANON_KEY` or `SUPABASE_SERVICE_ROLE_KEY` missing | The error names the variable and points to `.env.example` | `test_a_missing_credential_names_itself_and_says_where_to_put_it` |
| TC-DB24 | A credential left blank in `.env` | Treated as missing | `test_a_blank_credential_counts_as_missing` |
| TC-DB25 | Asking whether Supabase is configured, when it is not | Reports `False` instead of raising | `test_configured_reports_rather_than_raises` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-DB30 | Email in a different case from the profile | Matched | `test_the_address_is_matched_case_insensitively` |
| TC-DB31 | `SUPABASE_URL` with a trailing slash | Slash dropped | `test_a_trailing_slash_on_the_url_is_dropped` |
| TC-DB32 | `SUPABASE_DB_URL` unset | Allowed (only needed for direct database tests) | `test_the_database_url_is_optional` |

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| End to end against the live Supabase project (TC-DB04): sign-in, create, save, submit, a refused second submit, cross-role visibility, logout | 2026-09-08 | Passed (recorded with the US6.3 commit) |
| Backend `pytest` on the files above | 2026-10-23 | 21 passed |
| Frontend `vitest` on `eventsStore.test.ts` | 2026-10-23 | 36 passed |
