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
that is expected, not a build failure.

## Available scripts

| Command            | What it does                                    |
| ------------------ | ----------------------------------------------- |
| `npm run dev`      | Start the dev server with hot reload            |
| `npm run build`    | Type-check (`tsc -b`) and bundle to `dist/`     |
| `npm run lint`     | Lint with oxlint                                |
| `npm test`         | Run the test suite once (Vitest)                |
| `npm run test:watch` | Re-run tests on change                        |
| `npm run preview`  | Serve the production build locally              |

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

[`../.github/workflows/frontend-ci.yml`](../.github/workflows/frontend-ci.yml)
runs on every push to `main` and on every pull request that touches `frontend/`.
It installs dependencies with `npm ci`, lints, builds, and runs the tests. A
failing step fails the build and blocks the PR.

`npm ci` installs strictly from `package-lock.json`, so the lockfile is committed
and must be kept in sync with `package.json`.

## Project structure

```
src/
  main.tsx        React entry point
  App.tsx         root component, shows backend connection status
  LoginForm.tsx   login UI
  api.ts          backend client
  api.test.ts     tests for the client
  App.test.tsx    tests for the component
  LoginForm.test.tsx  tests for the login form
  test/setup.ts   Vitest setup (jest-dom matchers, cleanup)
```
