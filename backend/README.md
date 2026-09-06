# SPMG3T7 — Backend

FastAPI service for the SPMG3T7 project. The frontend lives in a separate repo:
[SPMG3T7FrontEnd](https://github.com/sjzdylan/SPMG3T7FrontEnd).

## Prerequisites

- Python 3.12 or newer (`python --version`)
- Git

## Local setup

Clone and create a virtual environment:

```bash
git clone https://github.com/sjzdylan/SPMG3T7BackEnd.git
cd SPMG3T7BackEnd
python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

`requirements.txt` holds runtime dependencies only; `requirements-dev.txt` includes
those plus the test and lint tooling, and is what CI installs.

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

- API root: <http://localhost:8000>
- Health check: <http://localhost:8000/health> → `{"status": "ok"}`
- Interactive docs: <http://localhost:8000/docs>

## Run the checks

These are the same three steps CI runs, so a green run here means a green run there:

```bash
ruff check .            # lint
python -m compileall -q app   # build
pytest                  # tests
```

## Environment variables

| Variable       | Default                  | Purpose                                            |
| -------------- | ------------------------ | -------------------------------------------------- |
| `CORS_ORIGINS` | `http://localhost:5173`  | Comma-separated list of origins allowed to call the API |

The default matches the Vite dev server, so the frontend works locally with no
configuration. Deployed environments should set `CORS_ORIGINS` to the real
frontend URL.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to `main`
and on every pull request. It installs dependencies, lints, byte-compiles the
sources, and runs the test suite. A failing step fails the build and blocks the PR.

## Project structure

```
app/
  main.py       FastAPI application and routes
  config.py     environment-driven settings
tests/
  test_health.py
  test_config.py
```
