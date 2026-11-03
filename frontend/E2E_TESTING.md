# Browser (E2E) tests

The journeys in `e2e-isolated/` drive the real app in Chromium, one or more per
role, against `backend/e2e_server.py`: the real API over in-memory stores, reset
before every test. Nothing reaches the shared Supabase project.

```bash
npm run test:e2e
```

Playwright starts both servers (API on 8001, Vite on 5174). The backend's
`.venv` must exist (see `backend/README.md`). If the installed Chromium does not
match this Playwright version, point `PW_CHROMIUM_PATH` at a Chromium binary.

`e2e-isolated/support.ts` holds the accounts, a sign-in helper, and API helpers
that walk an event to a given status (submitted, assigned, approved, planning,
confirmed), so each journey drives only the step it is about through the
browser. Each test case these journeys prove is listed in
`docs/testing/test_cases.txt` (layer E2E).
