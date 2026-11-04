#!/usr/bin/env python3
"""Remove the backend test functions that ``select_minimal_tests.py`` did not keep.

Usage: apply_test_selection.py <selection.json> [--dry-run]

Rules:

* Only whole test functions are removed (with their decorators). Fixtures,
  helpers and anything else in a test file are left alone.
* A function is always kept if a test-case document cites it, or if it lives in
  ``integration/`` or a ``*_db.py`` file (the real-database tests).
* A test class left with no members is removed too.

Run ``ruff check --fix`` afterwards to drop imports that nothing uses any more.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent


def cited_tests() -> set[str]:
    names: set[str] = set()
    for doc in (BACKEND / "tests").glob("test_cases_*.md"):
        names |= set(re.findall(r"`(test_\w+)`", doc.read_text()))
    return names


def span(node: ast.AST) -> tuple[int, int]:
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno] + [d.lineno for d in decorators])
    return start, node.end_lineno


def doomed_spans(tree: ast.Module, rel: str, keep: set, cited: set) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    def visit(body: list[ast.stmt], owner: str) -> bool:
        """Return True when nothing but a docstring is left in this body."""
        left = 0
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_") and (rel, owner, node.name) not in keep:
                    if node.name not in cited:
                        spans.append(span(node))
                        continue
                left += 1
            elif isinstance(node, ast.ClassDef):
                inner = f"{owner}::{node.name}" if owner else node.name
                before = len(spans)
                empty = visit(node.body, inner)
                if empty:
                    del spans[before:]
                    spans.append(span(node))
                else:
                    left += 1
            elif not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                left += 1
        return left == 0

    visit(tree.body, "")
    return spans


def main() -> None:
    selection = json.loads(Path(sys.argv[1]).read_text())
    dry = "--dry-run" in sys.argv
    keep = {(k["file"], k["owner"], k["func"]) for k in selection["keep"]}
    cited = cited_tests()
    removed = files_touched = 0
    for path in sorted((BACKEND / "tests").glob("test_*.py")):
        rel = f"tests/{path.name}"
        if path.name.endswith("_db.py"):
            continue
        source = path.read_text()
        spans = doomed_spans(ast.parse(source), rel, keep, cited)
        if not spans:
            continue
        lines = source.splitlines()
        for start, end in sorted(spans, reverse=True):
            del lines[start - 1 : end]
        removed += len(spans)
        files_touched += 1
        if not dry:
            path.write_text("\n".join(lines) + "\n")
    verb = "would remove" if dry else "removed"
    print(f"{verb} {removed} test functions in {files_touched} files")


if __name__ == "__main__":
    main()
