// Remove every Vitest/Playwright test whose title is not referenced in test_cases.txt.
// Usage: node prune_frontend.cjs <frontendDir> <keep.json> [--dry-run]
const fs = require('fs'), path = require('path')
const [dir, keepFile, flag] = process.argv.slice(2)
const ts = require(path.join(dir, 'node_modules/typescript'))
const keep = JSON.parse(fs.readFileSync(keepFile, 'utf8')) // { "src/x.test.tsx": ["title", ...] }
const dry = flag === '--dry-run'
function walk(d, out = []) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f)
    if (f === 'node_modules') continue
    if (fs.statSync(p).isDirectory()) walk(p, out)
    else if (/\.(test|spec)\.tsx?$/.test(f)) out.push(p)
  }
  return out
}
const files = ['src', 'e2e', 'e2e-isolated'].flatMap((d) => fs.existsSync(path.join(dir, d)) ? walk(path.join(dir, d)) : [])
let kept = 0, removed = 0
const report = { deleted: [], kept: {} }
const isCall = (n, names) => {
  if (!ts.isExpressionStatement(n) || !ts.isCallExpression(n.expression)) return null
  let e = n.expression.expression
  if (ts.isCallExpression(e)) e = e.expression // it.each([...])(...)
  let base = e
  while (ts.isPropertyAccessExpression(base)) base = base.expression // test.describe, it.only
  const full = e.getText()
  if (!ts.isIdentifier(base) || !names.includes(base.text)) return null
  return full
}
for (const file of files) {
  const rel = path.relative(dir, file).split(path.sep).join('/')
  const src = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const titles = new Set(keep[rel] || [])
  const cuts = []
  function visit(stmts) {
    let left = 0
    for (const st of stmts) {
      const callee = isCall(st, ['it', 'test', 'describe'])
      if (!callee) continue
      if (/\.(beforeEach|afterEach|beforeAll|afterAll|use|configure|setTimeout|slow|step|extend)\b/.test(callee)) continue
      const call = st.expression
      const isDescribe = /describe/.test(callee)
      const arg = call.arguments[0]
      const title = arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) ? arg.text : (arg ? arg.getText() : '')
      if (isDescribe) {
        const fn = [...call.arguments].reverse().find((a) => ts.isArrowFunction(a) || ts.isFunctionExpression(a))
        const body = fn && (ts.isArrowFunction(fn) || ts.isFunctionExpression(fn)) && ts.isBlock(fn.body) ? fn.body.statements : []
        const before = cuts.length
        const inner = visit(body)
        if (inner === 0) { cuts.splice(before); cuts.push([st.getFullStart(), st.getEnd()]) } else left += inner
        continue
      }
      if (/\.(skip|todo)$/.test(callee)) { cuts.push([st.getFullStart(), st.getEnd()]); continue }
      if (titles.has(title)) { left++; kept++; (globalThis.hit ||= new Set()).add(rel + "::" + title) } else { cuts.push([st.getFullStart(), st.getEnd()]); removed++ }
    }
    return left
  }
  const left = visit(sf.statements)
  if (left === 0) { report.deleted.push(rel); if (!dry) fs.unlinkSync(file); continue }
  report.kept[rel] = left
  if (!dry && cuts.length) {
    let out = src
    for (const [a, b] of cuts.sort((x, y) => y[0] - x[0])) out = out.slice(0, a) + out.slice(b)
    fs.writeFileSync(file, out.replace(/\n{3,}/g, '\n\n'))
  }
}
const missing = []
for (const [rel, ts_] of Object.entries(keep)) if (!fs.existsSync(path.join(dir, rel))) missing.push(rel)
console.log(`kept ${kept}, removed ${removed}, deleted ${report.deleted.length} files; missing ${JSON.stringify(missing)}`)
console.log(report.deleted.join('\n'))
for (const [rel, ts_] of Object.entries(keep)) for (const t of ts_) if (!(globalThis.hit || new Set()).has(rel + '::' + t)) console.log('NOT KEPT', rel, '::', t)
