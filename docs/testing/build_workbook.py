"""Build ConnectSphere_Test_Cases.xlsx from test_cases.txt and real test results.

    python docs/testing/build_workbook.py <results-dir>

<results-dir> holds JUnit XML from a run just made:
  backend.xml   pytest tests --junitxml=...
  db.xml        pytest integration --junitxml=... (TEST_POSTGRES_DSN set)
  frontend.xml  vitest run --reporter=junit --outputFile=...
  e2e.xml       PLAYWRIGHT_JUNIT_OUTPUT_NAME=... playwright test --reporter=junit

A test case is "Passed" only if its automated test ran in those results and
nothing in it failed. The layout follows the seniors' test script sheets.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))
from tcparse import parse  # noqa: E402

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results"
OUT = HERE / "ConnectSphere_Test_Cases.xlsx"

# -- Results -------------------------------------------------------------------


def junit(name):
    path = RESULTS / name
    if not path.exists():
        return []
    cases = []
    for case in ET.parse(path).getroot().iter("testcase"):
        failed = any(child.tag in ("failure", "error") for child in case)
        skipped = any(child.tag == "skipped" for child in case)
        cases.append((case.get("classname", ""), case.get("name", ""), failed, skipped))
    return cases


RUNS = {key: junit(f"{key}.xml") for key in ("backend", "db", "frontend", "e2e")}

#: Which run the results came from, for the summary sheet, e.g. "CI run 41870262896
#: on commit 62f66c4". Set RESULTS_FROM when building from a CI run's artifacts.
RESULTS_FROM = os.environ.get("RESULTS_FROM", "A local run")


def outcome(ref):
    """Passed / Failed / Not run for one test reference."""
    if ref.startswith("evidence:"):
        return "Evidence"
    path, *names = ref.split("::")
    if path.startswith("backend/"):
        rel = path[len("backend/") :].removesuffix(".py").replace("/", ".")
        cls = ".".join([rel, *names[:-1]])
        test = names[-1]
        # tests/*_db.py are skipped in the backend job and run in the db job,
        # so a backend test counts from either run.
        runs = RUNS["db"] if rel.startswith("integration") else RUNS["backend"] + RUNS["db"]
        hits = [r for r in runs if r[0] == cls and re.sub(r"\[.*\]$", "", r[1]) == test]
    else:
        title = "::".join(names)
        pattern = re.escape(title).replace(re.escape("%s"), ".+") + "$"
        runs = RUNS["e2e"] if "e2e-isolated" in path else RUNS["frontend"]
        stem = Path(path).name
        hits = [r for r in runs if stem in r[0] + r[1] and re.search(pattern, r[1])]
        if not hits:  # vitest puts the file in classname and "describe > title" in name
            hits = [r for r in runs if re.search(pattern, r[1]) and stem in r[0]]
    if not hits or all(r[3] for r in hits):
        # Opt-in tests that need a prepared database (see the case's Remarks).
        return "Not Executed"
    if any(r[2] for r in hits):
        return "Failed"
    return "Passed"


# -- Content -------------------------------------------------------------------

STORIES = yaml.safe_load((HERE / "acceptance_criteria.yaml").read_text(encoding="utf-8"))
AC = {a["id"]: a for s in STORIES for a in s["acceptance_criteria"]}
STORY = {s["story"]: s for s in STORIES}
CASES = parse(HERE / "test_cases.txt")


def story_of(ac_id):
    return ac_id.split("-AC")[0]


def ac_text(ac_ids):
    return "\n".join(f"{a}: {AC[a]['text']}" for a in ac_ids if a in AC)


def story_title(ac_ids):
    story = STORY.get(story_of(ac_ids[0]))
    return f"{story['story']} {story['title']}" if story else ac_ids[0]


THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="D9E1F2")
PASS = PatternFill("solid", fgColor="E2EFDA")
FAIL = PatternFill("solid", fgColor="F8CBAD")
WRAP = Alignment(wrap_text=True, vertical="top")
COLUMNS = [
    ("Title", 26),
    ("Test Case ID", 16),
    ("Test Scenario", 32),
    ("User Story Reference", 16),
    ("User Story / Acceptance Criteria", 44),
    ("Pre-Conditions", 30),
    ("Test Steps", 40),
    ("Test Input", 28),
    ("Expected Results", 44),
    ("Status (Pass/Fail/Not Executed)", 14),
    ("Test Type", 14),
    ("Automated Test", 50),
    ("Remarks", 40),
]


def header_block(ws, title, scenario):
    today = date.today().isoformat()
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    for label, value in (
        ("Created By:", "Ethan (Team G3T7)"),
        ("Date of Creation:", today),
        ("Executed By:", "Automated: pytest, Vitest, Playwright"),
        ("Date of Execution:", today),
        ("Test Scenario:", scenario),
    ):
        ws.append([label, value])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    ws.append([name for name, _ in COLUMNS])
    for col, (_, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(ws.max_row, col)
        cell.font = Font(bold=True)
        cell.fill = HEAD
        cell.border = BOX
        cell.alignment = WRAP
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = f"C{ws.max_row + 1}"


def case_sheet(wb, name, title, scenario, cases):
    ws = wb.create_sheet(name)
    header_block(ws, title, scenario)
    last_title = None
    for case in cases:
        acs = [a.strip() for a in case["ac"].split(",")]
        group = story_title(acs) if not case["id"].startswith("TC-D") else "Defects fixed (test-first)"
        status = outcome(case["test"])
        row = [
            group if group != last_title else "",
            case["id"],
            case["scenario"],
            ", ".join(acs),
            ac_text(acs),
            case["preconditions"],
            case["steps"],
            case["data"],
            case["expected"],
            status,
            case["layer"],
            case["test"],
            case["why"],
        ]
        last_title = group
        ws.append(row)
        for col in range(1, len(COLUMNS) + 1):
            cell = ws.cell(ws.max_row, col)
            cell.alignment = WRAP
            cell.border = BOX
        if row[0]:
            ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.cell(ws.max_row, 10).fill = (
            PASS if status in ("Passed", "Evidence") else FAIL if status == "Failed" else HEAD
        )
    return ws


def story_order(case):
    acs = [a.strip() for a in case["ac"].split(",")]
    order = list(STORY)
    s = story_of(acs[0])
    return (case["id"].startswith("TC-D"), order.index(s) if s in order else 999)


def main():
    wb = Workbook()
    wb.remove(wb.active)
    e2e = [c for c in CASES if c["layer"] == "E2E"]
    rest = sorted((c for c in CASES if c["layer"] != "E2E"), key=story_order)
    case_sheet(wb, "Unit & Integration Tests", "ConnectSphere: Unit and Integration Test Scripts",
               "Unit, API integration, component and database tests, by user story", rest)
    case_sheet(wb, "End-to-End Tests", "ConnectSphere: End-to-End Test Scripts",
               "Browser journeys for every role (Playwright, isolated server)",
               sorted(e2e, key=lambda c: c["id"]))

    # Stories and ACs, with how many test cases each AC has.
    ws = wb.create_sheet("User Stories & ACs")
    ws.append(["User Story", "Title", "AC ID", "Acceptance Criterion", "Kind", "Test Cases", "Note"])
    for col, width in zip("ABCDEFG", (10, 34, 14, 70, 12, 11, 50)):
        ws.column_dimensions[col].width = width
        ws[f"{col}1"].font = Font(bold=True)
        ws[f"{col}1"].fill = HEAD
    count = defaultdict(int)
    for c in CASES:
        for a in c["ac"].split(","):
            count[a.strip()] += 1
    for s in STORIES:
        for a in s["acceptance_criteria"]:
            ws.append([s["story"], s["title"], a["id"], a["text"], a["kind"], count[a["id"]],
                       a.get("note", "")])
            for col in range(1, 8):
                ws.cell(ws.max_row, col).alignment = WRAP

    # Summary first.
    ws = wb.create_sheet("Summary", 0)
    statuses = defaultdict(int)
    for c in CASES:
        statuses[outcome(c["test"])] += 1
    layers = defaultdict(int)
    for c in CASES:
        layers[c["layer"]] += 1
    behaviour = [a for a in AC.values() if a["kind"] == "behaviour"]
    covered = [a for a in behaviour if count[a["id"]]]
    lines = [
        ["ConnectSphere test cases (G3T7)"],
        [],
        ["How this was built", "Each Jira acceptance criterion was turned into test cases the Week 4 way: "
         "a happy path, one negative case per rule, and boundary values (just below, at, just above). "
         "Each test case points to the one automated test that checks it; we read every one."],
        ["Behaviour ACs", f"{len(covered)} of {len(behaviour)} have at least one test case"],
        ["Test cases", str(len(CASES))],
        *[[f"  {k}", str(v)] for k, v in sorted(layers.items())],
        ["Results of the run", ", ".join(f"{k} {v}" for k, v in sorted(statuses.items()))],
        ["Defects found and fixed", "D1, D2, D3, D4, D7, D8 (see CODE_AUDIT.md), each with a failing test first"],
        ["Results from", RESULTS_FROM],
        ["Coverage", "Measured 4 Nov 2026. Backend 86.22% combined line/branch coverage "
         "(88.82% lines, 74.77% branches); CI floor 85.6%. Frontend 53.34% lines, 51.82% "
         "statements, 50.00% functions and 49.73% branches. Not 100%: tests are chosen by "
         "acceptance criterion, not by line. Remaining gaps are mostly defensive database-error "
         "branches in the Supabase stores and UI loading/error states covered by the browser "
         "journeys instead. The SQL is tested on PostgreSQL 16 in CI, including a database built "
         "from nothing; the browser journeys use in-memory stores, not Supabase."],
        ["Source of truth", "docs/testing/test_cases.txt and acceptance_criteria.yaml; this file is generated "
         "by docs/testing/build_workbook.py"],
    ]
    for line in lines:
        ws.append(line)
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.cell(ws.max_row, 2).alignment = WRAP
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110
    wb.save(OUT)
    print(f"wrote {OUT.name}: {len(CASES)} cases; {dict(statuses)}")
    not_run = [c["id"] for c in CASES if outcome(c["test"]) == "Not Executed"]
    failed = [c["id"] for c in CASES if outcome(c["test"]) == "Failed"]
    print("not executed:", not_run or "none", "| failed:", failed or "none")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
