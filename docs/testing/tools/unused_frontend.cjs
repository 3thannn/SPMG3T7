// Remove top-level declarations TypeScript reports as unused, in test files only. Repeat until stable.
const fs = require('fs'), path = require('path')
const dir = process.argv[2]
const ts = require(path.join(dir, 'node_modules/typescript'))
function testFiles(d, out = []) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f)
    if (f === 'node_modules') continue
    if (fs.statSync(p).isDirectory()) testFiles(p, out)
    else if (/\.(test|spec)\.tsx?$|fixtures\.ts$|helpers\.ts$/.test(f)) out.push(p)
  }
  return out
}
const files = ['src', 'e2e', 'e2e-isolated'].flatMap((d) => fs.existsSync(path.join(dir, d)) ? testFiles(path.join(dir, d)) : [])
let total = 0
for (let round = 0; round < 6; round++) {
  const program = ts.createProgram(files, {
    noUnusedLocals: true, noEmit: true, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, skipLibCheck: true,
    allowImportingTsExtensions: true, types: ['vitest/globals', 'node'],
  })
  let changed = 0
  for (const file of files) {
    const sf = program.getSourceFile(file)
    if (!sf) continue
    const diags = program.getSemanticDiagnostics(sf).concat(program.getSuggestionDiagnostics ? [] : [])
      .filter((d) => [6133, 6196, 6198, 6192].includes(d.code))
    const cuts = []
    for (const d of diags) {
      const stmt = sf.statements.find((s) => s.getStart() <= d.start && d.start < s.getEnd())
      if (!stmt) continue
      if (ts.isImportDeclaration(stmt)) continue // oxlint handles imports
      const ok = ts.isFunctionDeclaration(stmt) || ts.isInterfaceDeclaration(stmt) || ts.isTypeAliasDeclaration(stmt) ||
        (ts.isVariableStatement(stmt) && stmt.declarationList.declarations.length === 1)
      if (ok && !cuts.some((c) => c[0] === stmt.getFullStart())) cuts.push([stmt.getFullStart(), stmt.getEnd()])
    }
    if (!cuts.length) continue
    let src = fs.readFileSync(file, 'utf8')
    for (const [a, b] of cuts.sort((x, y) => y[0] - x[0])) src = src.slice(0, a) + src.slice(b)
    fs.writeFileSync(file, src.replace(/\n{3,}/g, '\n\n'))
    changed += cuts.length
  }
  total += changed
  if (!changed) break
}
console.log('removed', total, 'unused declarations')
