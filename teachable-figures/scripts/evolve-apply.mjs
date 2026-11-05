import { readFileSync, writeFileSync, renameSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { dirname, resolve, relative } from 'node:path';
import { pathToFileURL } from 'node:url';

// Applies a typed evolution patch to an artifact, validates the candidate in headless Chrome,
// and writes the next version only if every check passes. See references/evolving-artifacts.md.
// Usage: node scripts/evolve-apply.mjs <artifact.html> <patch.json> <out.html> [--report report.json]
const [artifactPath, patchPath, outPath, ...rest] = process.argv.slice(2);
if (!artifactPath || !patchPath || !outPath) { console.error('usage: evolve-apply.mjs <artifact.html> <patch.json> <out.html> [--report file]'); process.exit(2); }
const reportPath = rest[0] === '--report' ? rest[1] : outPath.replace(/\.html$/, '.report.json');

const STRUCTURAL = new Set(['add_representation', 'replace_representation', 'add_layer', 'add_interaction', 'add_probe', 'generate_transfer_task', 'remove_component', 'remove_scaffold', 'restore_scaffold']);
const VALUE = new Set(['set_value']);
const sha = text => createHash('sha256').update(text).digest('hex').slice(0, 16);
const fail = (message, report) => {
  console.error(`REJECTED: ${message}`);
  if (report) { report.ok = false; report.error = message; writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n'); }
  process.exit(1);
};

const source = readFileSync(artifactPath, 'utf8');
const patchText = readFileSync(patchPath, 'utf8');
const patch = JSON.parse(patchText);
const patchDir = dirname(resolve(patchPath));
const load = ref => ref?.startsWith('@') ? readFileSync(resolve(patchDir, ref.slice(1)), 'utf8').trimEnd() : ref;

const STATE_RE = /<script type="application\/json" id="artifact-state">\n([\s\S]*?)\n<\/script>/;
const stateMatch = source.match(STATE_RE);
if (!stateMatch) fail('artifact has no #artifact-state block');
const state = JSON.parse(stateMatch[1]);
const report = { ok: false, artifact: state.artifact_id, from: state.version, to: patch.to_version, patch: relative(process.cwd(), resolve(patchPath)), checks: [], diff: null };

if (patch.schema !== 'teachable-figures/patch@1') fail(`unknown patch schema ${patch.schema}`, report);
if (patch.artifact_id !== state.artifact_id) fail(`patch is for ${patch.artifact_id}, artifact is ${state.artifact_id}`, report);
if (patch.from_version !== state.version) fail(`patch expects version ${patch.from_version}, artifact is version ${state.version}`, report);
if (patch.to_version !== state.version + 1) fail('to_version must be from_version + 1', report);

const evidenceText = readFileSync(resolve(patchDir, patch.evidence_ref), 'utf8');
const evidence = JSON.parse(evidenceText);
if (evidence.schema !== 'teachable-figures/evidence@1' || evidence.artifact?.id !== state.artifact_id || evidence.artifact?.version !== state.version)
  fail('evidence does not match this artifact version', report);

// ---- apply ----
let html = source;
const before = { components: Object.keys(state.components), scaffolds: { ...state.scaffolds } };
const slotRe = name => new RegExp(`(<!-- evolve:slot ${name} -->\\n)([\\s\\S]*?)(<!-- /evolve:slot ${name} -->)`);
function insertIntoSlot(name, block) {
  const re = slotRe(name);
  if (!re.test(html)) fail(`artifact has no slot "${name}"`, report);
  html = html.replace(re, (_, open, body, close) => open + body + block + '\n' + close);
}
function removeComponent(id) {
  const re = new RegExp(`<(div|style|script) data-component="${id}"[^>]*>[\\s\\S]*?</\\1>\\n`, 'g');
  html = html.replace(re, '');
  delete state.components[id];
}
function addComponent(op) {
  const c = op.component;
  if (!c?.id || !/^[a-z][a-z0-9-]*$/.test(c.id)) fail(`${op.op} needs a component with a kebab-case id`, report);
  if (state.components[c.id] && op.op !== 'replace_representation') fail(`component ${c.id} already exists; use replace_representation`, report);
  if (!Array.isArray(c.invariants)) fail(`component ${c.id} must declare invariants (may be empty only for purely decorative parts)`, report);
  if (op.op === 'replace_representation') removeComponent(c.id);
  const slot = op.target.replace(/^slot:/, '');
  insertIntoSlot(slot, `<div data-component="${c.id}" data-added-in="${patch.to_version}">\n${load(c.markup)}\n</div>`);
  if (c.css) insertIntoSlot('css', `<style data-component="${c.id}">\n${load(c.css)}\n</style>`);
  if (c.js) insertIntoSlot('script', `<script data-component="${c.id}">\n'use strict';\n(() => {\n${load(c.js)}\n})();\n</script>`);
  state.components[c.id] = { op: op.op, slot, added_in: patch.to_version, invariants: c.invariants };
}
function setScaffold(id, hidden) {
  const re = new RegExp(`data-scaffold="${id}"( hidden)?`);
  if (!re.test(html)) fail(`artifact has no scaffold "${id}"`, report);
  html = html.replace(re, `data-scaffold="${id}"${hidden ? ' hidden' : ''}`);
  state.scaffolds[id] = hidden ? 'hidden' : 'visible';
}
for (const op of patch.operations) {
  if (!STRUCTURAL.has(op.op) && !VALUE.has(op.op)) fail(`unsupported operation "${op.op}"`, report);
  if (['add_representation', 'replace_representation', 'add_layer', 'add_interaction', 'add_probe', 'generate_transfer_task'].includes(op.op)) addComponent(op);
  else if (op.op === 'remove_component') removeComponent(op.target.replace(/^component:/, ''));
  else if (op.op === 'remove_scaffold') setScaffold(op.target.replace(/^scaffold:/, ''), true);
  else if (op.op === 'restore_scaffold') setScaffold(op.target.replace(/^scaffold:/, ''), false);
  else if (op.op === 'set_value') { const [scope, key] = op.target.split(':'); if (scope !== 'preserved') fail('set_value only targets preserved:<key>', report); state.preserved[key] = op.value; }
}
for (const key of patch.preserve || []) {
  if (!(key in state.bindings)) fail(`cannot preserve "${key}": no binding`, report);
  state.preserved[key] = evidence.answers?.[key] ?? null;
}
state.version = patch.to_version;
state.lineage.push({
  version: patch.to_version, from: patch.from_version, created: patch.created,
  why: patch.hypothesis.statement, confidence: patch.hypothesis.confidence,
  decision: patch.decision,
  operations: patch.operations.map(o => ({ op: o.op, kind: STRUCTURAL.has(o.op) ? 'structural' : 'value', target: o.target, component: o.component?.id, reason: o.reason })),
  evidence: { ref: patch.evidence_ref, sha256: sha(evidenceText) },
  patch: { ref: relative(dirname(resolve(outPath)), resolve(patchPath)), sha256: sha(patchText) },
  preserved: patch.preserve || [],
  outcome: null,
});
html = html.replace(STATE_RE, () => `<script type="application/json" id="artifact-state">\n${JSON.stringify(state, null, 2).replace(/</g, '\\u003c')}\n</script>`);

report.diff = {
  components: { before: before.components, after: Object.keys(state.components), added: Object.keys(state.components).filter(id => !before.components.includes(id)), removed: before.components.filter(id => !(id in state.components)) },
  scaffolds: Object.fromEntries(Object.keys(state.scaffolds).filter(id => before.scaffolds[id] !== state.scaffolds[id]).map(id => [id, `${before.scaffolds[id]} → ${state.scaffolds[id]}`])),
  preserved: Object.keys(state.preserved),
  operations: patch.operations.map(o => `${o.op}${STRUCTURAL.has(o.op) ? ' (structural)' : ' (value)'} → ${o.target}${o.component ? ` [${o.component.id}]` : ''}`),
  bytes: { before: source.length, after: html.length },
};

// ---- validate ----
const candidate = resolve(dirname(resolve(outPath)), `.candidate-${process.pid}.html`);
writeFileSync(candidate, html);
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const check = (name, ok, detail) => report.checks.push({ name, ok: Boolean(ok), ...(detail ? { detail } : {}) });
try {
  for (const [w, h] of [[1440, 900], [1280, 720], [360, 800]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, reducedMotion: 'reduce' });
    const errors = [], network = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => m.type() === 'error' && errors.push(m.text()));
    await page.route('**/*', route => { const u = route.request().url(); if (u.startsWith('file:') || u.startsWith('data:') || u.startsWith('blob:')) return route.continue(); network.push(u); return route.abort(); });
    await page.goto(pathToFileURL(candidate).href + '?lang=en');
    const tag = `${w}×${h}`;
    if (w === 1440) {
      check('base self-check', await page.evaluate(expr => { try { return eval(expr) === true; } catch { return false; } }, state.validation.self_check));
      check('state version', await page.evaluate(() => evolve.state.version) === state.version);
      for (const id of Object.keys(state.components)) check(`component present: ${id}`, await page.locator(`div[data-component="${id}"]`).count() > 0);
      for (const sample of state.validation.samples) {
        await page.locator(state.validation.control).evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(sample));
        for (const [id, c] of Object.entries(state.components)) for (const inv of c.invariants) {
          const ok = await page.evaluate(expr => { try { return eval(expr) === true; } catch (e) { return 'threw: ' + e.message; } }, inv.expr);
          check(`invariant ${id}/${inv.id} @ ${sample}`, ok === true, ok === true ? undefined : `${inv.description}${typeof ok === 'string' ? ' — ' + ok : ''}`);
        }
      }
      for (const [key, sel] of Object.entries(state.bindings)) {
        const want = state.preserved[key];
        if (want == null) continue;
        const got = await page.evaluate(sel => { const el = document.querySelector(sel.includes('name=') ? sel + ':checked' : sel); return el ? el.value : null; }, sel);
        check(`preserved answer: ${key}`, got === want, got === want ? undefined : `expected ${JSON.stringify(want)}, found ${JSON.stringify(got)}`);
      }
      for (const [id, s] of Object.entries(state.scaffolds)) {
        const hidden = await page.locator(`[data-scaffold="${id}"]`).evaluate(el => !el.checkVisibility());
        check(`scaffold ${id} is ${s}`, hidden === (s === 'hidden'));
      }
    }
    const layout = await page.evaluate(ids => ({
      overflow: document.documentElement.scrollWidth - innerWidth,
      parts: ids.map(id => { const el = document.querySelector(`div[data-component="${id}"]`); const b = el.getBoundingClientRect(); return { id, w: b.width, right: b.right }; }),
    }), Object.keys(state.components));
    check(`no horizontal overflow @ ${tag}`, layout.overflow <= 1, layout.overflow > 1 ? `${layout.overflow}px` : undefined);
    for (const p of layout.parts) check(`component ${p.id} laid out @ ${tag}`, p.w > 0 && p.right <= w + 1, p.w > 0 && p.right <= w + 1 ? undefined : `width ${p.w}, right ${p.right}`);
    check(`no page errors @ ${tag}`, errors.length === 0, errors.length ? errors.join(' | ') : undefined);
    check(`no network @ ${tag}`, network.length === 0, network.length ? network.join(' ') : undefined);
    await page.close();
  }
} finally {
  await browser.close();
}

const failed = report.checks.filter(c => !c.ok);
if (failed.length) {
  rmSync(candidate, { force: true });
  for (const c of failed) console.error(`  ✗ ${c.name}${c.detail ? ` — ${c.detail}` : ''}`);
  fail(`${failed.length} of ${report.checks.length} checks failed; ${outPath} was not written`, report);
}
renameSync(candidate, outPath);
report.ok = true;
writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(`v${report.from} → v${report.to}: ${report.checks.length} checks passed; wrote ${outPath}`);
console.log('structural diff:');
for (const line of report.diff.operations) console.log(`  ${line}`);
console.log(`  components: [${report.diff.components.before.join(', ')}] → [${report.diff.components.after.join(', ')}]`);
for (const [id, change] of Object.entries(report.diff.scaffolds)) console.log(`  scaffold ${id}: ${change}`);
console.log(`  preserved from evidence: ${report.diff.preserved.join(', ') || 'none'}`);
