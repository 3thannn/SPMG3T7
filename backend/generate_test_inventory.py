#!/usr/bin/env python3
"""Generate the test inventory and test-case register as CSV files.

Run from anywhere; paths are relative to the repository root. Use the backend
virtualenv's Python so pytest is importable, and run `npm ci` in `frontend/`
first so Vitest and Playwright can list their tests.

    cd backend && source .venv/bin/activate && python generate_test_inventory.py

Writes two files at the repository root:

* ``test_inventory.csv``  - one row per automated test (unit, integration, E2E),
  linked to its user story and to the test case in ``backend/tests/test_cases_*.md``
  that it automates.
* ``test_case_register.csv`` - one row per test case written in those documents,
  in the course's template fields (ID, scenario, pre-conditions, steps/data,
  expected result), with the automated tests it points to and whether they still
  exist. A test case whose automated tests are missing is a documentation drift.

Nothing here claims a test was written first. Whether a test came before its
code is a question for the git history, not for this file.
"""

from __future__ import annotations

import ast
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DOCS = sorted((BACKEND / "tests").glob("test_cases_*.md"))

CATEGORY_HEADINGS = (
    ("happy", "Happy path"),
    ("cross-cutting", "Cross-cutting"),
    ("negative", "Negative"),
    ("boundary", "Boundary"),
)


def run(cmd: list[str], cwd: Path) -> str:
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return done.stdout


def norm(text: str) -> str:
    """Normalise quotes and whitespace so doc titles match test titles."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def story_from(text: str) -> str:
    match = re.search(r"us[_ .]?(\d+)[_.](\d+)", text, re.IGNORECASE)
    return f"US{match.group(1)}.{match.group(2)}" if match else ""


_FILE_STORY_CACHE: dict[str, str] = {}


def story_from_file(rel: str) -> str:
    """The one user story a file mentions, if it names exactly one."""
    if rel not in _FILE_STORY_CACHE:
        stories = set(re.findall(r"\bUS(\d+)\.(\d+)\b", (ROOT / rel).read_text()))
        only = next(iter(stories)) if len(stories) == 1 else None
        _FILE_STORY_CACHE[rel] = f"US{only[0]}.{only[1]}" if only else ""
    return _FILE_STORY_CACHE[rel]


SCAFFOLD_FILE = re.compile(
    r"\.paths\.test\.|\.calls\.test\.|remaining_guards|route_guards|App\.routes"
)


def audit_flag(test: dict, case: dict | None, cases_in_function: int) -> str:
    """Why a reviewer should look at this test again. Empty means no flag.

    These are prompts for human review, not verdicts: nothing is deleted on a
    flag alone.
    """
    flags = []
    if SCAFFOLD_FILE.search(test["file"]):
        flags.append("coverage-scaffold file: fold into the owning feature test")
    if cases_in_function >= 6:
        flags.append(f"{cases_in_function} cases in one test: keep one per equivalence class")
    if case is None and test["layer"] != "E2E":
        flags.append("no test case cites it: map to an AC or remove")
    return "; ".join(flags)


def humanise(name: str) -> str:
    words = re.sub(r"^test_", "", name).replace("_", " ").strip()
    return words[:1].upper() + words[1:]


# ---------------------------------------------------------------- test-case docs


def parse_docs() -> list[dict]:
    """Read every TC entry out of the test-case documents."""
    cases: list[dict] = []
    for doc in DOCS:
        category = ""
        current: dict | None = None
        for line in doc.read_text().splitlines():
            heading = re.match(r"^##\s+\d*\.?\s*(.+)$", line)
            if heading:
                title = heading.group(1).lower()
                for key, label in CATEGORY_HEADINGS:
                    if key in title:
                        category = label
                        break
                else:
                    category = ""
                current = None
                continue

            block = re.match(r"^###\s+(TC[-\w.]*)\s*[:.-]?\s*(.*)$", line)
            if block:
                current = {
                    "id": block.group(1),
                    "scenario": block.group(2).strip(),
                    "category": category,
                    "doc": doc.name,
                    "pre": "",
                    "steps": "",
                    "expected": "",
                    "text": line,
                }
                cases.append(current)
                continue

            row = re.match(r"^\|\s*(TC[-\w.]*)\s*\|(.*)\|\s*$", line)
            if row:
                cells = [c.strip() for c in row.group(2).split("|")]
                current = {
                    "id": row.group(1),
                    "scenario": cells[0] if cells else "",
                    "category": category,
                    "doc": doc.name,
                    "pre": "",
                    "steps": "",
                    "expected": cells[1] if len(cells) > 1 else "",
                    "text": line,
                }
                cases.append(current)
                current = None
                continue

            if current is not None:
                current["text"] += "\n" + line
                field = re.match(r"^- \*\*(.+?)\*\*:\s*(.*)$", line)
                if field:
                    key = field.group(1).lower()
                    value = field.group(2).strip()
                    if key.startswith("pre"):
                        current["pre"] = value
                    elif key.startswith("test steps") or key.startswith("test data"):
                        current["steps"] = (current["steps"] + " " + value).strip()
                    elif key.startswith("expected"):
                        current["expected"] = value
    for case in cases:
        text = case["text"]
        case["acs"] = ", ".join(sorted(set(re.findall(r"\bAC\d+\b", text))))
        case["py_refs"] = sorted(set(re.findall(r"`(test_\w+)`", text)))
        # Frontend tests are cited as: frontend "title one", "title two". Only
        # quoted strings after the word "frontend" are titles; quotes elsewhere
        # are expected messages and must not be mistaken for tests.
        titles: set[str] = set()
        for part in re.split(r"(?i)frontend", text)[1:]:
            part = part.split("\n")[0]
            titles |= {
                norm(q)
                for q in re.findall(r"[\"“]([^\"”]{8,})[\"”]", part)
            }
        case["fe_refs"] = sorted(titles)
    return cases


# ----------------------------------------------------------------- backend tests


def _visit(node: ast.AST, owner: str, source: str, rel: str, info: dict) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _visit(child, child.name, source, rel, info)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if child.name.startswith("test_"):
                args = {a.arg for a in child.args.args}
                body = ast.get_source_segment(source, child) or ""
                uses_client = "client" in args or "client." in body or "TestClient(" in body
                info[(rel, child.name)] = {
                    "line": child.lineno,
                    "class": owner,
                    "client": uses_client,
                }


def backend_function_info() -> dict[tuple[str, str], dict]:
    """(file, function) -> line, class and whether it drives the API client."""
    info: dict[tuple[str, str], dict] = {}
    files = list((BACKEND / "tests").glob("test_*.py")) + list(
        (BACKEND / "integration").glob("test_*.py")
    )
    for path in files:
        source = path.read_text()
        rel = path.relative_to(BACKEND).as_posix()
        _visit(ast.parse(source), "", source, rel, info)
    return info


def collect_backend(info: dict) -> list[dict]:
    out = run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings", "--no-cov"],
        BACKEND,
    )
    rows = []
    for line in out.splitlines():
        match = re.match(r"^((?:tests|integration)/[^:]+\.py)::(.+)$", line.strip())
        if not match:
            continue
        file, rest = match.groups()
        parts = rest.split("::")
        func = re.sub(r"\[.*\]$", "", parts[-1])
        meta = info.get((file, func), {"line": "", "class": "", "client": False})
        real_db = file.startswith("integration/") or file.endswith("_db.py")
        if real_db:
            layer, needs = "Integration", "TEST_POSTGRES_DSN"
            scope = "Real PostgreSQL (functions, triggers, RPCs)"
        elif meta["client"]:
            layer, needs = "Integration", ""
            scope = "API route through FastAPI TestClient (fake database)"
        elif "store" in Path(file).stem or "Store" in meta["class"]:
            layer, needs = "Unit", ""
            scope = "Store/query logic against a fake Supabase client"
        else:
            layer, needs = "Unit", ""
            scope = "Business rule or helper in isolation"
        rows.append(
            {
                "layer": layer,
                "scope": scope,
                "framework": "pytest",
                "file": "backend/" + file,
                "line": meta["line"],
                "suite": meta["class"],
                "name": parts[-1],
                "func": func,
                "needs": needs,
            }
        )
    return rows


# ---------------------------------------------------------------- frontend tests


def collect_vitest() -> list[dict]:
    out = run(["npx", "vitest", "list", "--json"], FRONTEND)
    try:
        listed = json.loads(out)
    except json.JSONDecodeError:
        return []
    rows = []
    for item in listed:
        file = Path(item["file"]).relative_to(ROOT).as_posix()
        is_component = file.endswith(".tsx")
        rows.append(
            {
                "layer": "Unit",
                "scope": "React component or page (Testing Library, mocked API)"
                if is_component
                else "Frontend logic, store or API client (mocked fetch)",
                "framework": "vitest",
                "file": file,
                "line": item.get("location", {}).get("line", ""),
                "suite": "",
                "name": item["name"],
                "func": item["name"],
                "needs": "",
            }
        )
    return rows


def walk_playwright(suites: list, trail: list[str], file: str, out: list, scope: str) -> None:
    for suite in suites:
        title = suite.get("title", "")
        here = trail + ([title] if title and title != file else [])
        for spec in suite.get("specs", []):
            out.append(
                {
                    "layer": "E2E",
                    "scope": scope,
                    "framework": "playwright",
                    "file": f"frontend/e2e{'-isolated' if 'isolated' in scope else ''}/{file}",
                    "line": spec.get("line", ""),
                    "suite": " > ".join(here),
                    "name": spec["title"],
                    "func": spec["title"],
                    "needs": "Isolated local servers (ports 8001 and 5174)"
                    if "isolated" in scope
                    else "Running backend and Supabase (shared/live)",
                }
            )
        walk_playwright(suite.get("suites", []), here, file, out, scope)


def collect_playwright() -> list[dict]:
    rows: list[dict] = []
    for config, scope in (
        ("playwright.config.ts", "Browser journey, shared/live backend"),
        ("playwright.isolated.config.ts", "Browser journey, isolated local servers"),
    ):
        cmd = ["npx", "playwright", "test", "-c", config, "--list", "--reporter=json"]
        out = run(cmd, FRONTEND)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue
        for top in data.get("suites", []):
            walk_playwright([top], [], top.get("title", ""), rows, scope)
    return rows


# ------------------------------------------------------------------------ output


def main() -> None:
    cases = parse_docs()
    by_py: dict[str, dict] = {}
    by_fe: dict[str, dict] = {}
    for case in cases:
        for name in case["py_refs"]:
            by_py.setdefault(name, case)
        for title in case["fe_refs"]:
            by_fe.setdefault(title, case)

    info = backend_function_info()
    tests = collect_backend(info) + collect_vitest() + collect_playwright()

    present_py = {t["func"] for t in tests if t["framework"] == "pytest"}
    present_fe = {norm(t["name"]) for t in tests if t["framework"] != "pytest"}

    cases_in = defaultdict(int)
    for test in tests:
        if test["framework"] == "pytest":
            cases_in[(test["file"], test["func"], test["suite"])] += 1
    rows = []
    counters: defaultdict[str, int] = defaultdict(int)
    prefix = {"Unit": "UT", "Integration": "IT", "E2E": "E2E"}
    for test in tests:
        if test["framework"] == "pytest":
            case = by_py.get(test["func"])
        else:
            case = by_fe.get(norm(test["name"]))
        counters[test["layer"]] += 1
        candidates = (
            ("file name", story_from(test["file"])),
            ("test name", story_from(test["name"])),
            ("test-case document", story_from(case["doc"]) if case else ""),
            ("file content (one story named)", story_from_file(test["file"])),
        )
        story, source = next(((v, k) for k, v in candidates if v), ("", ""))
        description = humanise(test["func"]) if test["framework"] == "pytest" else test["name"]
        rows.append(
            {
                "Test ID": f"{prefix[test['layer']]}-{counters[test['layer']]:04d}",
                "Layer": test["layer"],
                "Scope": test["scope"],
                "Framework": test["framework"],
                "File": test["file"],
                "Line": test["line"],
                "Suite / Class": test["suite"],
                "Test Name": test["name"],
                "What It Checks": description,
                "User Story": story,
                "User Story Source": source,
                "Test Case ID": case["id"] if case else "",
                "Test Case Category": case["category"] if case else "",
                "Acceptance Criteria": case["acs"] if case else "",
                "Test Case Document": case["doc"] if case else "",
                "Linked To A Test Case": "Yes" if case else "No",
                "Audit Flag": audit_flag(
                    test, case, cases_in.get((test["file"], test["func"], test["suite"]), 1)
                ),
                "Needs": test["needs"],
            }
        )

    with open(ROOT / "test_inventory.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    register = []
    for case in cases:
        py_missing = [n for n in case["py_refs"] if n not in present_py]
        fe_missing = [t for t in case["fe_refs"] if t not in present_fe]
        refs = len(case["py_refs"]) + len(case["fe_refs"])
        missing = len(py_missing) + len(fe_missing)
        register.append(
            {
                "Test Case ID": case["id"],
                "User Story": story_from(case["doc"]),
                "Test Scenario": case["scenario"],
                "Category": case["category"],
                "Acceptance Criteria": case["acs"],
                "Pre-conditions": case["pre"],
                "Test Steps / Test Data": case["steps"],
                "Expected Result": case["expected"],
                "Automated Tests Cited": refs,
                "Automated Tests Missing": missing,
                "Missing Backend Tests": "; ".join(py_missing),
                "Document": case["doc"],
                "Status": "No automated test cited"
                if refs == 0
                else (
                    "All cited tests present"
                    if missing == 0
                    else "Cited tests missing from suite"
                ),
            }
        )
    with open(ROOT / "test_case_register.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(register[0]))
        writer.writeheader()
        writer.writerows(register)

    by_layer = defaultdict(int)
    for row in rows:
        by_layer[row["Layer"]] += 1
    linked = sum(r["Linked To A Test Case"] == "Yes" for r in rows)
    print(f"test_inventory.csv: {len(rows)} tests", dict(by_layer), f"linked: {linked}")
    stale = sum(r["Status"] == "Cited tests missing from suite" for r in register)
    print(f"test_case_register.csv: {len(register)} test cases; {stale} cite missing tests")


if __name__ == "__main__":
    main()
