# Backend tests

The pytest suite for `backend/app`: unit tests of the rules, and API tests through FastAPI's test client over the in-memory stores. `pytest --cov` runs them with the coverage floor in `backend/pyproject.toml`.

The `test_cases_*.md` files are the per-story test notes written as each story was built, kept as process evidence. The test cases maintained now, one or more per acceptance criterion and each linked to the automated test that runs it, are in [`docs/testing/test_cases.txt`](../../docs/testing/test_cases.txt), from which the submitted workbook is generated.

Two files here need a real PostgreSQL: `test_hold_expiry_db.py` and `test_equipment_reservations_db.py`. CI runs them on a fresh database built by `scripts/fresh_install.py`; locally they skip unless `TEST_POSTGRES_DSN` points at a disposable server.
