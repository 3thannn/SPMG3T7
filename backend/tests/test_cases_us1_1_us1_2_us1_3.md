# Test Cases for US1.1, US1.2, US1.3: Login, Logout and Access Enforcement

> **US1.1** As a user, I want to sign in with my email and password, so that I
> reach the view for my role.
>
> **US1.2** As a user, I want to sign out, so that nobody can carry on my session
> after I leave.
>
> **US1.3** As the system, I want to block requests outside a user's role and
> explain why, so that each role can only do what it is meant to.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| US1.1 AC1 | Valid credentials grant access and redirect to a role-appropriate view | Done |
| US1.1 AC2 | Invalid credentials show a clear error | Done |
| US1.1 AC3 | A session stays active during normal use and expires after a defined inactivity period | Done — 30 minutes, sliding |
| US1.2 AC1 | Logout ends the session immediately | Done |
| US1.2 AC2 | Subsequent requests require re-authentication | Done |
| US1.3 AC1 | Out-of-role access attempts are blocked | Done — 403 from the API; the page is guarded too |
| US1.3 AC2 | A clear message explains the denial | Done — names the role, what was refused and who may do it |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **The inactivity period is 30 minutes** (`SESSION_IDLE_MINUTES`), and it slides:
  every authenticated request restarts it, so a session lasts as long as someone
  keeps working. The browser counts down the same window and signs itself out.
- **The server picks the landing page**, not the browser. The login response
  carries a `home` route per role and the client follows it.
- **One message for a wrong password and an unknown email** ("Incorrect email or
  password."), so the form cannot be used to find out who has an account.
- **Four refusals stay distinct**: `invalid_credentials`, `not_authenticated`,
  `session_expired` and `forbidden`. Being idle never reads as a wrong password, and
  an unreachable server never blames the password.
- **Sessions are server-side** so logout can end one outright. Signing out on one
  device leaves the same user's other sessions alone.
- **Known gap:** sessions are held in the API's memory, so restarting the API signs
  everyone out. Credentials themselves live in Supabase Auth (US6.3).

## Workflow Visualization

```
Sign-in form ── POST /auth/login ──► Supabase Auth checks the password
                                        │
         wrong / unknown ◄──────────────┤──────────► ok
         401 invalid_credentials        │            token, role, permissions,
         "Incorrect email or password." │            home route, idleMinutes = 30
                                                       │
                       browser goes to `home` ◄────────┘
                       (Organiser, Coordinator → /events; Lead → /unassigned-queue;
                        Venue Staff → /venues; Safety Officer → /safety-review;
                        Tech Support → /equipment-requests)
                                                       │
   every request ── Bearer token ──► require_permission(...)
        │ unknown token → 401 not_authenticated      │ wrong role → 403 forbidden
        │ idle > 30 min → 401 session_expired        │ "The <role> role cannot …"
        ▼                                            ▼
   POST /auth/logout → 204, token dead at once; next request → 401
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `test_auth_login.py` (US1.1), `test_auth_logout.py` (US1.2), `test_access_enforcement.py` (US1.3), `test_sessions.py`, `test_security.py`, `test_users.py`, `test_config.py` |
| Frontend | `SignInPage.test.tsx`, `App.test.tsx`, `permissions.test.ts`, `session.test.ts`, `api.test.ts` (`login`, `logout`, `fetchMe`, `authorizedFetch` blocks) |

---

## 1. HAPPY PATH TEST CASES

### TC-A01: Valid credentials return a session (US1.1 AC1)
- **Pre-conditions**: An Event Organiser account
- **Test Steps**: `POST /auth/login` with `{"email": ..., "password": ...}`
- **Expected Result**: HTTP 200 with a token, the role from the account (not chosen at sign-in), the role's permissions and a `home` route; the password is not in the response
- **Automated**: `test_valid_credentials_return_a_session`, `test_the_role_comes_from_the_account_and_is_not_chosen_at_sign_in`, `test_the_password_is_never_echoed_back`, `test_the_session_carries_the_permissions_the_role_holds`; frontend "posts the credentials to the sign-in route", "returns the session the server issued", "hands the session up when the credentials are accepted"

### TC-A02: Each role lands on its own view (US1.1 AC1)
- **Expected Result**: Organiser and Coordinator → `/events`; Coordinator Lead → `/unassigned-queue`; Venue Staff → `/venues`; Safety Officer → `/safety-review`; Tech Support → `/equipment-requests`. The browser goes wherever the server says
- **Automated**: `test_each_role_is_told_where_its_own_view_is`; frontend "sends the user to the view the server picked for their role", "sends an Organiser to the events list", "uses whatever landing route the server sends, without deciding for itself", "routes a Coordinator Lead to the unassigned queue on sign-in", "routes a Safety Officer to the safety review page on sign-in"

### TC-A03: The session stays alive during normal use (US1.1 AC3)
- **Test Steps**: Sign in, then make requests, each less than 30 minutes apart
- **Expected Result**: Every request succeeds; each one restarts the 30 minutes
- **Automated**: `test_the_session_survives_normal_use`, `test_use_slides_the_window_so_an_active_session_stays_alive`, `test_a_session_survives_inactivity_shorter_than_the_timeout`; frontend "keeps the session alive while the user is still working"

### TC-A04: The session expires after 30 minutes without use (US1.1 AC3)
- **Test Steps**: Sign in, wait 31 minutes, call `GET /auth/me`
- **Expected Result**: 401 `session_expired`, "Your session expired after a period of inactivity. Sign in again to continue."; the open page signs itself out at the same point and says it was 30 minutes of inactivity
- **Automated**: `test_the_session_expires_after_the_inactivity_period`, `test_the_client_is_told_how_long_the_idle_window_is`, `test_a_session_expires_once_the_idle_window_passes`; frontend "signs the user out after the inactivity window and says why", "explains an expired session instead of just showing the form again"

### TC-A05: Logout ends the session immediately (US1.2 AC1)
- **Test Steps**: `POST /auth/logout` with the token, then `GET /auth/me` with the same token
- **Expected Result**: 204, then 401 `not_authenticated`; the session is removed from the store, not left to time out
- **Automated**: `test_logout_succeeds_for_a_signed_in_user`, `test_the_token_stops_working_the_moment_the_session_ends`, `test_the_ended_session_is_released_rather_than_left_behind`, `test_revoking_ends_the_session_immediately`; frontend "ends the session on the server when the user signs out", "sends the token so the server can end that session"

### TC-A06: Later requests need a fresh sign-in (US1.2 AC2)
- **Expected Result**: Every protected route refuses the ended token; signing in again works and gives a different token; a guarded page sends the user back to the form
- **Automated**: `test_every_protected_route_refuses_the_ended_session`, `test_signing_in_again_after_logout_works`, `test_the_new_session_after_signing_back_in_is_a_different_one`; frontend "needs a fresh sign-in for a guarded page after signing out"

### TC-A07: A role that holds the permission gets through (US1.3)
- **Test Steps**: `GET /auth/users` as an Event Coordinator
- **Expected Result**: 200 with the user directory
- **Automated**: `test_an_allowed_role_gets_through`; frontend "lets an Organiser through to the page a Coordinator is refused"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-A10: Each kind of refusal says what actually happened
- **Expected Result**: a wrong password, a signed-out caller, an idle session and a wrong role get four different codes; an unreachable server says "Could not reach the server." and never mentions the password
- **Automated**: `test_an_expired_session_is_not_confused_with_a_bad_password`, `test_being_signed_out_and_being_out_of_role_are_different_answers`, `test_an_unknown_token_is_unknown_rather_than_expired`; frontend "says the server is unreachable rather than blaming the password", "raises AuthError on 401 so the form can name the real problem", "raises a plain error on a server fault, not AuthError", "reports an expired session distinctly from a rejected one"

### TC-A11: A stored session is checked with the server, not trusted
- **Expected Result**: on page load the stored token is sent to `GET /auth/me`; a live one opens the page, a revoked or expired one is dropped and the form explains why; an unreadable stored record reads as signed out
- **Automated**: frontend "restores a stored session and opens the guarded page", "checks the stored token with the server rather than trusting it", "signs the user out when the stored token has been revoked"; `session.test.ts`

### TC-A12: Signing out on one device leaves the others signed in
- **Automated**: `test_logging_out_of_one_device_leaves_the_other_signed_in`, `test_revoking_one_session_leaves_the_users_other_sessions_alone`, `test_revoke_all_ends_every_session_for_one_user_only`

### TC-A13: The browser follows the server's permissions
- **Expected Result**: the page reads the permissions the login returned; links a role cannot use are left out of the header (no "create" link for a Coordinator)
- **Automated**: `permissions.test.ts` (`can`, `canOpen`); frontend "leaves the create link out of the header for a Coordinator", "offers the create link to an Organiser", "offers the events link to a role that can open it"

### TC-A14: A refused page shows none of what it guards
- **Expected Result**: the API returns no guarded data with a 403; the page renders "Access denied" before building the guarded content, and offers somewhere to go
- **Automated**: `test_a_blocked_request_returns_none_of_the_data_it_guarded`; frontend "renders none of the guarded page when the role is refused", "gives a blocked role somewhere to go"

### TC-A15: Tokens cannot be guessed
- **Expected Result**: every sign-in gets a new, long, URL-safe token
- **Automated**: `test_tokens_are_unique_and_long_enough_to_be_unguessable`, `test_a_token_is_url_safe_so_it_survives_a_header_and_a_query_string`, `test_two_sign_ins_get_two_different_tokens`, `test_each_session_gets_its_own_token`

### TC-A16: The permission catalogue is complete and no role holds everything
- **Automated**: `TestPermissionCatalogue` (every role has a set, no role holds every permission, Organisers and Coordinators hold different things, every permission can be named in a denial)

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-A20 | Wrong password | 401 `invalid_credentials`, "Incorrect email or password."; no session created | `test_a_wrong_password_is_rejected`, `test_a_rejected_sign_in_issues_no_session`; frontend "surfaces a rejected credential clearly" |
| TC-A21 | Email with no account | The same 401 and message as a wrong password | `test_an_unknown_email_is_rejected_the_same_way_as_a_wrong_password`, `test_an_address_with_no_credential_is_refused` |
| TC-A22 | Account half-made (credential without profile) | Refused | `test_a_credential_with_no_profile_is_refused` |
| TC-A23 | Request missing `email` or `password` | 422 validation error, not treated as a sign-in | `test_a_request_missing_a_field_is_a_validation_error_not_a_sign_in` |
| TC-A24 | Empty or malformed email in the form | "Enter your email address." / "Enter a valid email address."; no request sent | frontend "asks for an email before calling the server", "rejects a malformed email" |
| TC-A25 | Server unreachable | "Could not reach the server."; no way past the form | frontend "says the server is unreachable rather than blaming the password", "offers no way past the form when the server cannot be reached" |
| TC-A26 | Organiser calls `GET /auth/users` | 403 `forbidden`, "The Event Organiser role cannot view the user directory. That is available to: Event Coordinator, Event Coordinator Lead." | `test_an_out_of_role_request_is_blocked`, `test_the_denial_says_what_was_refused_and_who_may_do_it` |
| TC-A27 | Coordinator opens the create-event page | "Access denied" with the reason | frontend "blocks a Coordinator from creating an event and explains why"; `permissions.test.ts` `denialMessage` |
| TC-A28 | No token; a made-up token; a malformed `Authorization` header | 401 | `test_a_missing_token_asks_the_caller_to_sign_in`, `test_a_made_up_token_is_refused`, `test_a_malformed_authorization_header_is_refused` |
| TC-A29 | Signed-out visitor opens a guarded page | Sent to the sign-in form | frontend "sends an anonymous visitor to sign in rather than the events list", "blocks every route without a session" |
| TC-A30 | Login response with no role, permissions or token | Refused rather than guessed | frontend "refuses a response with no role instead of assuming one", "refuses a response with no permissions", "refuses a response with no token" |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-A40 | Idle just under / just over the window | Still active / expired | `test_a_session_survives_inactivity_shorter_than_the_timeout`, `test_a_session_expires_once_the_idle_window_passes` |
| TC-A41 | An expired token used twice | `session_expired` once, then `not_authenticated` | `test_an_expired_session_is_reported_once_then_forgotten` |
| TC-A42 | Email in another case or with spaces | Matched | `test_the_email_is_matched_without_case_or_padding`, `test_the_address_is_matched_case_insensitively` |
| TC-A43 | Password in another case or with spaces | Not matched | `test_the_password_is_matched_exactly` |
| TC-A44 | Logout twice, or with no token | 204, not an error; the browser never blocks a sign-out | `test_logging_out_twice_is_not_an_error`, `test_logging_out_without_a_token_is_not_an_error`; frontend "never throws, so a sign-out is not blocked by an unreachable server" |
| TC-A45 | `SESSION_IDLE_MINUTES` unset, set, or not a positive number | 30 / the value / 30 (never "no expiry") | `test_session_idle_defaults_to_thirty_minutes`, `test_session_idle_is_configurable`, `test_a_nonsense_idle_window_falls_back_rather_than_never_expiring` |
| TC-A46 | Expired sessions in the count | Not counted as active | `test_active_count_ignores_sessions_that_have_timed_out` |

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 74 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 112 passed |
