import re,sys
def parse(path):
    cases=[];cur=None;key=None
    for raw in open(path,encoding="utf-8"):
        line=raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"): continue
        m=re.match(r"^- id: (.+)$",line)
        if m:
            cur={"id":m.group(1).strip()};cases.append(cur);key="id";continue
        m=re.match(r"^  ([a-z_]+): ?(.*)$",line)
        if m and cur is not None:
            key=m.group(1);cur[key]=m.group(2).strip();continue
        if line.startswith("    ") and cur is not None and key:
            cur[key]=(cur[key]+" "+line.strip()).strip();continue
        raise ValueError(f"cannot read line: {line!r}")
    return cases
if __name__=="__main__":
    cs=parse(sys.argv[1]); print(len(cs),"test cases"); 
    need={"id","ac","category","scenario","preconditions","steps","data","expected","layer","test","why"}
    bad=[c["id"] for c in cs if need-set(c)]
    print("missing fields:",bad or "none")
