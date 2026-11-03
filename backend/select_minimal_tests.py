#!/usr/bin/env python3
"""Choose the smallest backend suite that keeps 100% coverage and every
documented test case.

Method (the "Light" reduction):

1. Protect every test the test-case documents cite (traceability), every
   real-database test (``integration/`` and ``*_db.py``), and every test in the
   small files that carry a rule the customer changed (``CUSTOMER_CHANGE_FILES``).
   Coverage cannot see that these matter, because other tests often exercise the
   same lines.
2. Add the fewest other tests needed so every line and branch arc that the full
   suite exercised is still exercised (a greedy set cover over per-test coverage).
3. Keep the best representative of every test class that would otherwise vanish,
   so each rule the suite names still has a test.
4. Keep the best test of any file that would otherwise be left with none.
5. Everything else is a candidate for removal.

Input is a coverage database recorded with per-test contexts:

    pytest --cov=app --cov-branch --cov-context=test --cov-fail-under=0

Usage: select_minimal_tests.py <coverage-file> <output.json>

The result is a proposal. Apply it with ``apply_test_selection.py`` and check
the real coverage afterwards; coverage by arc is slightly stricter than the
line-plus-branch gate, so a pass is expected but must be confirmed.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent

# Files whose tests prove a rule the customer set or changed in the Week 7
# changes and the clarification answers: Lead assignment and the unassigned
# queue, hold expiry, venue replacement, reconfirmation after a change, and
# Safety approval followed by the Coordinator's own confirmation (US4.7).
# Kept whole because each is small. Larger files (turnaround, unavailability,
# safety decisions) are covered by the class-representative rule instead.
CUSTOMER_CHANGE_FILES = {
    "tests/test_unassigned_queue.py",
    "tests/test_lead_assignment.py",
    "tests/test_lead_reassignment.py",
    "tests/test_lead_rls.py",
    "tests/test_reassignment_us8_4.py",
    "tests/test_hold_expiry_us14_4.py",
    "tests/test_venue_problem_us12_4.py",
    "tests/test_reconfirm_us11_3.py",
    "tests/test_confirm_event_us4_7.py",
    "tests/test_safety_review_us17_1.py",
}


def cited_tests() -> set[str]:
    names: set[str] = set()
    for doc in (BACKEND / "tests").glob("test_cases_*.md"):
        names |= set(re.findall(r"`(test_\w+)`", doc.read_text()))
    return names


def function_key(test_id: str) -> tuple[str, str, str]:
    """tests/test_x.py::Class::test_y[param] -> (file, class, test_y)."""
    parts = test_id.split("::")
    func = re.sub(r"\[.*\]$", "", parts[-1])
    owner = "::".join(parts[1:-1])
    return parts[0], owner, func


def main(coverage_file: str, out_file: str) -> None:
    db = sqlite3.connect(coverage_file)
    contexts = {cid: name for cid, name in db.execute("select id, context from context")}
    arcs_by_context: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    for file_id, context_id, fromno, tono in db.execute(
        "select file_id, context_id, fromno, tono from arc"
    ):
        arcs_by_context[context_id].add((file_id, fromno, tono))

    everything: set[tuple[int, int, int]] = set()
    always: set[tuple[int, int, int]] = set()
    per_function: dict[tuple[str, str, str], set] = defaultdict(set)
    cases_in: dict[tuple[str, str, str], int] = defaultdict(int)
    seen_ids: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for context_id, arcs in arcs_by_context.items():
        everything |= arcs
        name = contexts.get(context_id, "")
        if not name:
            always |= arcs  # import-time: not attributable to any test
            continue
        test_id = name.split("|")[0]
        if "::" not in test_id:
            always |= arcs
            continue
        key = function_key(test_id)
        per_function[key] |= arcs
        seen_ids[key].add(test_id)
    for key, ids in seen_ids.items():
        cases_in[key] = len(ids)

    cited = cited_tests()
    protected: dict[tuple[str, str, str], str] = {}
    for key in per_function:
        file, _, func = key
        if file.startswith("integration/") or file.endswith("_db.py"):
            protected[key] = "real database"
        elif func in cited:
            protected[key] = "cited by a test case"
        elif file in CUSTOMER_CHANGE_FILES:
            protected[key] = "customer-changed rule"

    covered = set(always)
    for key in protected:
        covered |= per_function[key]

    chosen: dict[tuple[str, str, str], str] = {}
    remaining = everything - covered
    candidates = {k: v for k, v in per_function.items() if k not in protected}
    while remaining:
        best = max(candidates, key=lambda k: len(candidates[k] & remaining), default=None)
        if best is None or not (candidates[best] & remaining):
            break
        chosen[best] = "needed for coverage"
        remaining -= candidates[best]
        del candidates[best]

    keep = {**protected, **chosen}

    # Every named test class keeps its best representative: the test that
    # exercises the most of the code, so the rule it names is still demonstrated.
    classes: dict[tuple[str, str], list] = defaultdict(list)
    for key in per_function:
        if key[1]:
            classes[(key[0], key[1])].append(key)
    for members in classes.values():
        if not any(m in keep for m in members):
            best = max(members, key=lambda m: (len(per_function[m]), m))
            keep[best] = "representative of its test class"

    # No test file is left empty: it keeps its single best test.
    files: dict[str, list] = defaultdict(list)
    for key in per_function:
        files[key[0]].append(key)
    for members in files.values():
        if not any(m in keep for m in members):
            best = max(members, key=lambda m: (len(per_function[m]), m))
            keep[best] = "only test kept for its file"
    result = {
        "protected": sum(1 for _ in protected),
        "needed_for_coverage": len(chosen),
        "uncovered_after": len(remaining),
        "functions_total": len(per_function),
        "keep": [
            {"file": k[0], "owner": k[1], "func": k[2], "why": why, "cases": cases_in[k]}
            for k, why in sorted(keep.items())
        ],
    }
    Path(out_file).write_text(json.dumps(result, indent=1))
    kept_cases = sum(cases_in[k] for k in keep)
    total_cases = sum(cases_in.values())
    print(
        f"functions: {len(per_function)} total, {len(protected)} protected, "
        f"{len(chosen)} added for coverage, {len(remaining)} arcs still uncovered"
    )
    print(f"test cases: keep {kept_cases} of {total_cases}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
