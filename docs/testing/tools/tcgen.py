"""Write test cases from compact rows: id|ac|category|scenario|pre|steps|data|expected|layer|test|why."""
import sys, textwrap
def wrap(key, text):
    lines = textwrap.wrap(f"  {key}: {text}", width=100, subsequent_indent="    ", break_long_words=False, break_on_hyphens=False)
    return "\n".join(lines)
out=[]
block=[]
for raw in open(sys.argv[1], encoding="utf-8"):
    line=raw.rstrip("\n")
    if not line.strip() or line.startswith("#"): continue
    parts=[p.strip() for p in line.split("|")]
    assert len(parts)==11, (len(parts), line)
    keys=["id","ac","category","scenario","preconditions","steps","data","expected","layer","test","why"]
    rec=dict(zip(keys,parts))
    s=[f"- id: {rec['id']}"]
    for k in keys[1:]:
        if k=="test": s.append(f"  test: {rec[k]}")
        else: s.append(wrap(k, rec[k]))
    out.append("\n".join(s))
sys.stdout.write("\n\n" + "\n\n".join(out) + "\n")
