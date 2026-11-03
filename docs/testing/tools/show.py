"""Print the source of chosen tests: backend `file::Class::test` or frontend `file::title`."""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]


def backend(ref):
    file, *names = ref.split("::")
    path = ROOT / "backend" / file
    src = path.read_text()
    body = ast.parse(src).body
    node = None
    for name in names:
        name = re.sub(r"\[.*\]$", "", name)
        node = next(
            n for n in body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
        )
        body = getattr(node, "body", [])
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    lines = src.splitlines()[start - 1 : node.end_lineno]
    return "\n".join(lines)


def frontend(ref):
    file, title = ref.split("::", 1)
    src = (ROOT / "frontend/src" / file).read_text().splitlines()
    for i, line in enumerate(src):
        if re.search(r"(it|test)(\.each\([^)]*\))?\(\s*['\"`]" + re.escape(title.strip()), line):
            depth, out = 0, []
            for j in range(i, min(i + 60, len(src))):
                out.append(src[j])
                depth += src[j].count("{") - src[j].count("}")
                if depth <= 0 and j > i:
                    break
            return "\n".join(out)
    return f"NOT FOUND: {title}"


for ref in sys.argv[1:]:
    print(f"\n===== {ref}")
    try:
        print(frontend(ref) if ref.split("::")[0].endswith((".ts", ".tsx")) else backend(ref))
    except StopIteration:
        print("NOT FOUND")
