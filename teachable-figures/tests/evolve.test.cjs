const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { execFileSync } = require('node:child_process');
const { readFileSync, writeFileSync, existsSync, mkdtempSync, copyFileSync, cpSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { resolve, join } = require('node:path');
const { pathToFileURL } = require('node:url');

const dir = resolve(__dirname, '../examples/evolve/geometry-slices');
const apply = resolve(__dirname, '../scripts/evolve-apply.mjs');
const url = (file, lang = 'en') => pathToFileURL(join(dir, file)).href + '?lang=' + lang;
const slide = (page, value) => page.locator('#height').evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });

function scratch() {
  const work = mkdtempSync(join(tmpdir(), 'evolve-'));
  for (const f of ['v1.html', 'patch-1.json', 'evidence-1.json']) copyFileSync(join(dir, f), join(work, f));
  cpSync(join(dir, 'components'), join(work, 'components'), { recursive: true });
  return work;
}
const run = (work, patch, out) => { try { return { code: 0, out: execFileSync('node', [apply, 'v1.html', patch, out], { cwd: work, encoding: 'utf8', stdio: 'pipe' }) }; } catch (e) { return { code: e.status, out: String(e.stdout) + String(e.stderr) }; } };

test('applying patch-1 to v1 reproduces the published v2 and passes validation', { timeout: 120000 }, () => {
  const work = scratch();
  const { code, out } = run(work, 'patch-1.json', 'v2.html');
  assert.equal(code, 0, out);
  assert.match(out, /checks passed/);
  assert.match(out, /add_representation \(structural\) → slot:figure \[area-tiles\]/);
  assert.equal(readFileSync(join(work, 'v2.html'), 'utf8'), readFileSync(join(dir, 'v2.html'), 'utf8'));
  const report = JSON.parse(readFileSync(join(work, 'v2.report.json'), 'utf8'));
  assert.equal(report.ok, true);
  assert.deepEqual(report.diff.components.added, ['area-tiles', 'tile-probe']);
  assert.equal(report.diff.scaffolds['formula-hint'], 'visible → hidden');
});

test('a patch whose component breaks the square law is rejected and nothing is written', { timeout: 120000 }, () => {
  const work = scratch();
  const js = join(work, 'components/area-tiles.js');
  const source = readFileSync(js, 'utf8');
  assert.ok(source.includes('const areaMultiple = k * k;'));
  writeFileSync(js, source.replace('const areaMultiple = k * k;', 'const areaMultiple = k;'));
  const { code, out } = run(work, 'patch-1.json', 'v2.html');
  assert.equal(code, 1);
  assert.match(out, /area-multiple-matches-model @ 4/);
  assert.match(out, /v2\.html was not written/);
  assert.equal(existsSync(join(work, 'v2.html')), false);
  assert.equal(readFileSync(join(work, 'v1.html'), 'utf8'), readFileSync(join(dir, 'v1.html'), 'utf8'));
});

test('a patch for the wrong version is refused before any change', { timeout: 30000 }, () => {
  const work = scratch();
  const patch = JSON.parse(readFileSync(join(work, 'patch-1.json'), 'utf8'));
  writeFileSync(join(work, 'stale.json'), JSON.stringify({ ...patch, from_version: 2, to_version: 3 }));
  const { code, out } = run(work, 'stale.json', 'v3.html');
  assert.equal(code, 1);
  assert.match(out, /expects version 2, artifact is version 1/);
  assert.equal(existsSync(join(work, 'v3.html')), false);
});

test('v1 exports evidence that matches the schema', async () => {
  const page = await browser.newPage(); await page.goto(url('v1.html'));
  assert.equal(await page.locator('[data-scaffold="formula-hint"]').isVisible(), true);
  await page.locator('input[name="prediction"][value="4"]').check();
  await page.getByRole('button', { name: 'Compare h = 4' }).click();
  await page.getByRole('button', { name: 'Compare my prediction' }).click();
  await page.locator('#explanation').fill('The area doubles too.');
  await page.locator('#explanation').blur();
  await page.locator('input[name="transfer"][value="3"]').check();
  await page.getByRole('button', { name: 'Check transfer' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export learning evidence' }).click();
  assert.match((await download).suggestedFilename(), /^evidence-geometry-slices-v1\.json$/);
  const evidence = JSON.parse(await page.locator('#evidence-out').textContent());
  assert.equal(evidence.schema, 'teachable-figures/evidence@1');
  assert.deepEqual(evidence.artifact, { id: 'geometry-slices', version: 1, components: [], scaffolds_visible: ['formula-hint'] });
  assert.equal(evidence.after_change, null);
  assert.deepEqual(evidence.answers, { prediction: '4', explanation: 'The area doubles too.', transfer: '3' });
  assert.deepEqual(evidence.events.map(e => e.type), ['prediction', 'trial', 'check', 'explanation', 'transfer', 'export']);
  assert.ok(evidence.events.every(e => Number.isInteger(e.t) && e.t >= 0));
  assert.equal(evidence.events.find(e => e.type === 'check').result, 'match');
  assert.ok(!/name|email/i.test(Object.keys(evidence.session).join(' ')));
  // The published sample evidence follows the same shape.
  const sample = JSON.parse(readFileSync(join(dir, 'evidence-1.json'), 'utf8'));
  assert.deepEqual(Object.keys(sample).sort(), Object.keys(evidence).sort());
  await page.close();
});

test('v2 adds a tile view in sync with the slider, keeps earlier answers, and hides the formula hint', async () => {
  const page = await browser.newPage(); const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(url('v2.html'));
  assert.equal(await page.locator('#crumb').textContent(), 'evolve/geometry-slices · v2');
  assert.match(await page.locator('#changes').textContent(), /Version 2: this figure changed in response to your answers/);
  assert.equal(await page.locator('input[name="prediction"][value="4"]').isChecked(), true);
  assert.match(await page.locator('#explanation').inputValue(), /^The area doubles too, because h doubled/);
  assert.match(await page.locator('#carried-explanation').textContent(), /version 1/);
  assert.equal(await page.locator('[data-scaffold="formula-hint"]').isVisible(), false);
  for (const [h, k, tiles, whole] of [[2, '×1.00', '×1.00', 1], [4, '×2.00', '×4.00', 4], [6, '×3.00', '×9.00', 9], [5, '×2.50', '×6.25', 4]]) {
    await slide(page, h);
    assert.equal(await page.locator('#tiles-k').textContent(), k);
    assert.equal(await page.locator('#tiles-mult').textContent(), tiles);
    assert.equal(await page.locator('#ratio').textContent(), tiles);
    assert.equal(await page.locator('#tiles-draw rect.tile.full').count(), whole);
  }
  await page.locator('input[name="tile-probe"][value="9"]').check();
  await page.getByRole('button', { name: 'Check tiles' }).click();
  assert.match(await page.locator('#tile-probe-feedback').textContent(), /^Yes\. Three rows of three is 9 tiles/);
  await page.getByRole('button', { name: 'Export learning evidence' }).click();
  const evidence = JSON.parse(await page.locator('#evidence-out').textContent());
  assert.deepEqual(evidence.artifact.components, ['area-tiles', 'tile-probe']);
  assert.deepEqual(evidence.artifact.scaffolds_visible, []);
  assert.deepEqual(evidence.after_change, { version: 2, from: 1 });
  assert.equal(evidence.answers['tile-probe'], '9');
  assert.deepEqual(evidence.events.find(e => e.type === 'probe'), { ...evidence.events.find(e => e.type === 'probe'), id: 'tile-probe', value: '9', correct: true });
  await page.getByRole('button', { name: '中文' }).click();
  assert.match(await page.locator('#changes').textContent(), /第 2 版/);
  assert.match(await page.locator('#tiles-desc').textContent(), /参考方块/);
  assert.deepEqual(errors, []);
  await page.close();
});
