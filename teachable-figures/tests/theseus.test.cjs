const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader','--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/ship-of-theseus.html')).href;
const slide = (page, id, value) => page.locator('#' + id).evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));
const verdicts = page => page.evaluate(() => ['matter', 'continuity', 'form', 'name'].map(k => document.getElementById('v-' + k).textContent));

test('ship of theseus criteria agree until reassembly splits them', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  assert.equal(await page.locator('#step-year').isDisabled(), true);
  assert.equal(await page.locator('#collector').isDisabled(), true);
  await page.locator('input[name="prediction"][value="B"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  assert.deepEqual(await verdicts(page), ['Ship A', 'Ship A', 'Ship A', 'Ship A']);
  assert.equal(await page.locator('#v-summary').textContent(), 'All four agree');
  await page.locator('#step-year').click();
  assert.equal(await page.locator('#ro-a').textContent(), '92%');
  await page.locator('#collector').check();
  await slide(page, 'year', 6);
  assert.equal((await verdicts(page))[0], 'Tie');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  for (let i = 0; i < 6; i++) await page.locator('#step-year').click();
  assert.equal(await page.locator('#ro-a').textContent(), '0%');
  assert.equal(await page.locator('#ro-b').textContent(), '100%');
  assert.deepEqual(await verdicts(page), ['Ship B', 'Ship A', 'Both', 'Ship A']);
  assert.equal(await page.locator('#v-summary').textContent(), 'Four criteria, 3 answers');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.match(await page.locator('#prediction-feedback').textContent(), /You predicted “Ship B\.” Criteria that back you: matter/);
  // An overnight rebuild breaks continuity; raising the tolerance restores it.
  await slide(page, 'rate', 24);
  assert.equal((await verdicts(page))[1], 'Neither');
  await slide(page, 'tolerance', 23); assert.equal((await verdicts(page))[1], 'Neither');
  await slide(page, 'rate', 7); await slide(page, 'tolerance', 7); assert.equal((await verdicts(page))[1], 'Ship A');
  await slide(page, 'tolerance', 6); assert.equal((await verdicts(page))[1], 'Neither');
  await page.close();
});

test('copying copies loses design information while a blueprint holds it', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  await page.locator('input[name="prediction"][value="both"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await page.locator('#collector').check(); await slide(page, 'year', 12);
  assert.equal(await page.locator('#error').isDisabled(), true);
  await page.locator('input[name="drift"][value="less"]').check();
  await page.getByRole('button', { name: 'Save this prediction' }).click();
  await slide(page, 'error', 5);
  await page.getByRole('button', { name: 'Repair until every plank is copied 3 times' }).click();
  assert.equal(await page.locator('#year').inputValue(), '36');
  assert.equal(await page.locator('#ro-info').textContent(), '43%');
  const match = Number((await page.locator('#ro-info-u').textContent()).match(/(\d+)% match/)[1]);
  assert.ok(match > 75, 'most bits still match even though less than half the information remains');
  assert.equal((await verdicts(page))[2], 'Ship B');
  assert.match(await page.locator('#drift-feedback').textContent(), /You predicted less than half/);
  await slide(page, 'year', 72);
  assert.ok(Number((await page.locator('#ro-info').textContent()).replace('%', '')) < 43, 'more generations never add information');
  await page.locator('#blueprint').check();
  assert.equal(await page.locator('#ro-info').textContent(), '71%');
  assert.equal((await verdicts(page))[2], 'Both');
  await page.locator('input[name="transfer"][value="form"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await page.locator('#transfer-feedback').textContent(), /^Correct/);
  await page.locator('#reset').click();
  assert.equal(await page.locator('#year').inputValue(), '0');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#step-year').isDisabled(), true);
  await page.close();
});

test('ship of theseus animates plank swaps only after prediction and works offline at both widths', async () => {
  for (const width of [360, 1440]) for (const colorScheme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme });
    const errors = [], remote = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (/^https?:/.test(r.url())) remote.push(r.url()); });
    await page.goto(url);
    assert.equal(await page.locator('#ghosts path').count(), 0);
    await page.locator('input[name="prediction"][value="A"]').check();
    await page.getByRole('button', { name: 'Save my prediction' }).click();
    await page.locator('#step-year').click();
    assert.equal(await page.locator('#ghosts path').count(), 2, 'two old planks fly to storage');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('[data-set-lang="zh"]').click();
    assert.match(await page.locator('#v-summary').textContent(), /四条标准/);
    assert.deepEqual(errors, []); assert.deepEqual(remote, []);
    await page.close();
  }
});
