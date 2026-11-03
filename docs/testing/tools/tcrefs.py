import ast,pathlib,re,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from tcparse import parse
ROOT=pathlib.Path(__file__).resolve().parents[3]
def exists(ref):
    if ref.startswith("evidence: "):
        return all((ROOT/x.strip()).exists() for x in ref[len("evidence: "):].split(","))
    f,*names=ref.split("::")
    p=ROOT/f
    if not p.exists(): return False
    if f.endswith((".ts",".tsx")):
        t=re.escape(names[0] if len(names)==1 else "::".join(names))
        each = r"(\.each\((?:[^()]|\([^()]*\))*\))?"
        return re.search(r"(it|test)" + each + r"\(\s*['\"`]" + t + r"['\"`]", p.read_text(), re.S) is not None
    body=ast.parse(p.read_text()).body
    for n in names:
        n=re.sub(r"\[.*\]$","",n)
        node=next((x for x in body if isinstance(x,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==n),None)
        if node is None: return False
        body=getattr(node,"body",[])
    return True
cs=parse(sys.argv[1])
missing=[(c["id"],c["test"]) for c in cs if not exists(c["test"])]
print("missing refs:",missing or "none")
