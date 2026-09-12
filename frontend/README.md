# SPMG3T7 — Frontend

React + TypeScript client for the SPMG3T7 project, built with Vite. The API lives
alongside it in this same repo, under [`../backend/`](../backend/); see the
[root README](../README.md) for how to run both halves together.

## Prerequisites

- Node.js 22 or newer (`node --version`)
- npm 10 or newer (ships with Node)
- Git

## Local setup

All commands below are run from this `frontend/` directory.

```bash
npm install
```

## Run the app

```bash
npm run dev
```

Open <http://localhost:5173>. The home page calls the backend's `/health` endpoint
and shows whether the API is reachable, so you can confirm both halves of the
system are talking to each other.

To see it report **Backend connected**, start the backend first (see
[its README](../backend/README.md)):

```bash
cd ../backend
uvicorn app.main:app --reload --port 8000
```

Without the backend running, the page loads and reports **Backend unreachable** —
that is expected, not a build failure. Signing in, though, needs the API: there
is no way past the form without it, by design.

## Signing in

Use one of the development accounts — [the backend
README](../backend/README.md#development-accounts) has the table. Both share the
password `Sprint1!demo`.

Where you land is the server's decision, sent on the session rather than decided
here:

| Role        | Lands on  | Can reach                       |
| ----------- | --------- | ------------------------------- |
| Organiser   | `/events` | the events list, create, detail |
| Coordinator | `/events` | the events list and detail      |

The boundary between the two is creating an event: an Organiser proposes, a
Coordinator reviews. Open `#/events/new` while signed in as a Coordinator and
you get an access-denied page naming the role and who the page is for, rather
than a form that fails on submit.

### How it fits together

- [`api.ts`](src/api.ts) — the calls, and the error types that keep a wrong
  password, a lapsed session and a blocked role distinct from one another
- [`session.ts`](src/session.ts) — the stored session, which is checked with the
  server on every load rather than trusted
- [`permissions.ts`](src/permissions.ts) — which route needs which permission,
  and how to explain a refusal
- [`useIdleSignOut.ts`](src/useIdleSignOut.ts) — signs out after the same idle
  window the server uses, which the server sends on the session

The route guard and the hidden nav links are conveniences: they keep people out
of dead ends. The API refuses the request regardless, and that refusal is what
actually enforces the rule — anything the client checks, a user can edit.

## Available scripts

| Command              | What it does                                |
| -------------------- | ------------------------------------------- |
| `npm run dev`        | Start the dev server with hot reload        |
| `npm run build`      | Type-check (`tsc -b`) and bundle to `dist/` |
| `npm run lint`       | Lint with oxlint                            |
| `npm test`           | Run the test suite once (Vitest)            |
| `npm run test:watch` | Re-run tests on change                      |
| `npm run preview`    | Serve the production build locally          |

## Run the checks

These are the same three steps CI runs, so a green run here means a green run there:

```bash
npm run lint
npm run build
npm test
```

## Environment variables

| Variable            | Default                  | Purpose                     |
| ------------------- | ------------------------ | --------------------------- |
| `VITE_API_BASE_URL` | `http://localhost:8000`  | Base URL of the backend API |

Copy [`.env.example`](.env.example) to `.env.local` to override. Only variables
prefixed with `VITE_` are exposed to the browser — never put secrets in them.

## Continuous integration

The `frontend` job in [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml)
runs on every push to `main` and on every pull request. It installs dependencies
with `npm ci`, lints, builds, and runs the tests. A failing step fails the build
and blocks the PR.

It runs alongside the `backend` job on every change, not only on changes under
`frontend/` — the two halves call each other, so a green client against a broken
API is not a useful signal.

`npm ci` installs strictly from `package-lock.json`, so the lockfile is committed
and must be kept in sync with `package.json`.

## Project structure

```
src/
  main.tsx           React entry point
  App.tsx            root component: session, route guards, health status
  router.ts          hash router — five routes, no routing dependency
  api.ts             backend client and its error types
  session.ts         the stored session, revived on load
  permissions.ts     which route needs which permission
  eventsStore.ts     the /events client
  status.ts          event status model and roles
  useIdleSignOut.ts  signs out after the server's idle window
  pages/             sign-in, landing, events, event detail, new event, access denied
  components/        top nav, status badge, status timeline
  test/              Vitest setup and shared session builders
```

Tests sit next to what they cover, as `*.test.ts` / `*.test.tsx`.
