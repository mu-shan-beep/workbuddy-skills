const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/bayes-base-rate.html')).href;
const slide = (page, id, value) => page.locator('#' + id).evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));
const text = (page, id) => page.locator('#' + id).textContent();
const ringed = page => page.locator('#g-grid circle[r="5.3"]').evaluateAll(rings => rings.filter(r => r.getAttribute('display') !== 'none').length);

async function predictAndCount(page, estimate = '9.2') {
  await page.locator('input[name="prediction"][value="90"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await page.locator('#positives-only').check();
  await page.locator('#estimate').fill(estimate);
  await page.getByRole('button', { name: 'Check my count' }).click();
}

test('bayes lesson hides results until a prediction, then counts true and false positives', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(url);
  assert.equal(await text(page, 'r-ppv'), '—');
  assert.equal(await page.locator('#positives-only').isDisabled(), true);
  assert.equal(await ringed(page), 0, 'no test results before the prediction');
  await page.locator('input[name="prediction"][value="90"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  assert.equal(await text(page, 'r-ppv'), '9.2%');
  assert.equal(await text(page, 'r-tp'), '9');
  assert.equal(await text(page, 'r-fp'), '89');
  assert.equal(await text(page, 'r-npv'), '99.9%');
  assert.equal(await text(page, 'r-lr'), '×10');
  assert.equal(await ringed(page), 98);
  // The estimate needs the positives filter first; the explanation stays locked until an estimate.
  assert.equal(await page.locator('#estimate').isDisabled(), true);
  assert.equal(await page.locator('#explanation').isVisible(), false);
  await page.locator('#positives-only').check();
  await page.locator('#estimate').fill('90');
  await page.getByRole('button', { name: 'Check my count' }).click();
  assert.match(await text(page, 'estimate-feedback'), /sensitivity, P\(positive \| sick\).*confusion of the inverse/);
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.match(await text(page, 'prediction-feedback'), /You predicted about 90%/);
  assert.match(await text(page, 'odds-line'), /Prior odds 1 : 99 × likelihood ratio 10 .* = 10 : 99.* = 9\.2%/);
  await page.locator('#estimate').fill('9.2');
  await page.getByRole('button', { name: 'Check my count' }).click();
  assert.match(await text(page, 'estimate-feedback'), /^Right\./);
  assert.deepEqual(errors, []);
  await page.close();
});

test('base rate and retesting move the posterior through the odds form', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  await page.goto(url);
  await predictAndCount(page);
  await slide(page, 'prevalence', 6); // 10%
  assert.equal(await page.locator('#prevalence-out').textContent(), '10% (1 in 10)');
  assert.equal(await text(page, 'r-ppv'), '52.6%'); // 90 / (90 + 81)
  await slide(page, 'fpr', 1);
  assert.equal(await text(page, 'r-lr'), '×90');
  await page.getByRole('button', { name: 'Back to 1% / 90% / 9%' }).click();
  assert.equal(await text(page, 'r-ppv'), '9.2%');
  await page.getByRole('button', { name: 'Retest the positives' }).click();
  assert.equal(await text(page, 'r-ppv'), '50.3%');
  assert.equal(await text(page, 'r-tp'), '8.1');
  assert.equal(await ringed(page), 16);
  await page.getByRole('button', { name: 'Retest the positives' }).click();
  assert.equal(await text(page, 'r-ppv'), '91.0%');
  assert.match(await page.locator('#odds-ladder li.now').textContent(), /3 positives → 91\.0%/);
  await page.getByRole('button', { name: 'Back to one test' }).click();
  assert.equal(await text(page, 'r-ppv'), '9.2%');
  await page.close();
});

test('independent practice fades the figure and names each misconception', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  await page.goto(url);
  await predictAndCount(page);
  await page.getByRole('button', { name: 'Start practice' }).click();
  // Case 1: dots only, numbers hidden, controls locked.
  assert.equal(await page.locator('#g-tree').getAttribute('display'), 'none');
  assert.equal(await text(page, 'r-ppv'), '?');
  assert.equal(await page.locator('#prevalence').isDisabled(), true);
  assert.equal(await ringed(page), 68);
  const answer = async v => { await page.locator('#practice-answer').fill(String(v)); await page.getByRole('button', { name: 'Check answer' }).click(); return text(page, 'practice-feedback'); };
  assert.match(await answer(95), /confusion of the inverse/);
  assert.match(await answer(28), /^Right: 27\.9%/);
  await page.getByRole('button', { name: 'Next case' }).click();
  // Case 2: a blank tree, no dots.
  assert.equal(await page.locator('#g-grid').getAttribute('display'), 'none');
  assert.ok((await page.locator('#g-tree').textContent()).includes('?'));
  assert.match(await answer(8), /sick and positive.*divide by all positives/);
  assert.match(await answer(8), /Worked through: .*80 ÷ 170 ≈ 47\.1%/);
  await page.getByRole('button', { name: 'Next case' }).click();
  // Case 3: no figure; odds misconception.
  assert.match(await page.locator('#g-note').textContent(), /No figure/);
  assert.match(await answer(40), /multiplies odds, not probabilities/);
  assert.match(await answer(29), /^Right: 29\.0%/);
  await page.getByRole('button', { name: 'Finish practice' }).click();
  assert.match(await text(page, 'practice-summary'), /You got 0 of 3 right on the first try/);
  assert.equal(await text(page, 'r-ppv'), '9.2%');
  assert.equal(await page.locator('#prevalence').isDisabled(), false);
  await page.close();
});

test('bayes transfer, reset, language, offline and short viewports', async () => {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const requests = []; context.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
  const page = await context.newPage();
  await page.goto(url);
  await predictAndCount(page);
  await page.locator('input[name="transfer"][value="weapon"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /confusion of the inverse/);
  await page.locator('input[name="transfer"][value="false"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct\. .*0\.0099%/);
  await page.locator('[data-set-lang="zh"]').click();
  assert.match(await text(page, 'summary'), /人检测阳性/);
  await page.locator('[data-set-lang="en"]').click();
  await page.getByRole('button', { name: 'Reset lesson' }).click();
  assert.equal(await text(page, 'r-ppv'), '—');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.deepEqual(requests, []);
  for (const [width, height] of [[1280, 720], [1024, 600], [768, 1024], [360, 800], [1440, 900]]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(100);
    const m = await page.evaluate(() => {
      const r = document.querySelector('.readouts').getBoundingClientRect();
      const twoPane = getComputedStyle(document.querySelector('.panel')).display === 'block';
      return { overflow: document.documentElement.scrollWidth - innerWidth, bottom: r.bottom, height: r.height, twoPane, vh: innerHeight };
    });
    assert.ok(m.overflow <= 0, `${width}x${height} horizontal overflow`);
    assert.ok(m.height >= 40, `${width}x${height} readouts collapsed`);
    if (m.twoPane) assert.ok(m.bottom <= m.vh, `${width}x${height} readouts below the fold`);
  }
  await context.close();
});
