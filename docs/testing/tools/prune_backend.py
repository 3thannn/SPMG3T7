"""Remove every backend test not referenced in docs/testing/test_cases.txt.

Whole test functions (with decorators) go; a Test* class left with no tests goes;
a file left with no tests is deleted unless another test module imports it.
"""
import ast, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tcparse import parse

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
cases = parse(ROOT / "docs/testing/test_cases.txt")
keep = set()
for c in cases:
    t = c["test"]
    if t.startswith("backend/"):
        f, *names = t.split("::")
        keep.add((f[len("backend/"):], "::".join(re.sub(r"\[.*\]$", "", n) for n in names)))

files = sorted(list((BACKEND / "tests").glob("test_*.py")) + list((BACKEND / "integration").glob("test_*.py")))
imported = set()
for f in (BACKEND / "tests").glob("*.py"):
    for m in re.findall(r"^from tests\.(\w+) import", f.read_text(), re.M):
        imported.add(m)
    for m in re.findall(r"^from tests import (\w+)", f.read_text(), re.M):
        imported.add(m)

dry = "--dry-run" in sys.argv
removed = kept = 0
deleted_files = []
for path in files:
    rel = str(path.relative_to(BACKEND))
    src = path.read_text()
    tree = ast.parse(src)
    spans = []
    def span(n):
        return min([n.lineno] + [d.lineno for d in n.decorator_list]), n.end_lineno
    def visit(body, owner):
        global removed, kept
        left = 0
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                name = f"{owner}::{node.name}" if owner else node.name
                if (rel, name) in keep:
                    left += 1; kept += 1
                else:
                    spans.append(span(node)); removed += 1
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                before = len(spans)
                inner_left = visit(node.body, f"{owner}::{node.name}" if owner else node.name)
                if inner_left == 0:
                    del spans[before:]
                    spans.append(span(node))
                else:
                    left += inner_left
        return left
    left = visit(tree.body, "")
    if left == 0 and path.stem not in imported:
        deleted_files.append(rel)
        if not dry: path.unlink()
        continue
    if spans and not dry:
        lines = src.splitlines(keepends=True)
        for start, end in sorted(spans, reverse=True):
            # also drop blank lines left directly above
            del lines[start - 1:end]
        path.write_text("".join(lines))
print(f"kept {kept} test functions, removed {removed}; deleted {len(deleted_files)} files")
for f in deleted_files: print("  deleted", f)
missing = {k for k in keep if not (BACKEND / k[0]).exists()}
print("referenced but missing files:", missing or "none")
