const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/dynamic-equilibrium.html')).href;
const text = (page, id) => page.locator('#' + id).textContent();
const skip = async (page, times) => { for (let i = 0; i < times; i++) await page.locator('#skip').click(); };
async function open(options = {}) {
  const page = await browser.newPage({ reducedMotion: 'reduce', ...options });
  const errors = [], external = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) external.push(r.url()); });
  await page.goto(url);
  return { page, errors, external };
}

test('equilibrium keeps both rates running, and tracer exchange unlocks the explanation', async () => {
  const { page, errors, external } = await open();
  assert.equal(await page.locator('#run').isDisabled(), true);
  assert.equal(await page.locator('#skip').isDisabled(), true);
  await page.waitForTimeout(400);
  assert.match(await page.locator('#figure').textContent(), /t = 0\.0 s/);
  await page.locator('input[name="prediction"][value="stopped"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await skip(page, 4);
  assert.equal(await text(page, 'ro-a'), '33.8');
  assert.equal(await text(page, 'ro-b'), '12.5');
  assert.equal(await text(page, 'ro-q'), '4.60');
  assert.match(await text(page, 'ro-q-u'), /^= K/);
  assert.equal(await text(page, 'ro-rates'), '1.24 ⇄ 1.24');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  await page.locator('#tag').check();
  assert.equal(await text(page, 'ro-tag'), '25% · 0%');
  await skip(page, 1);
  assert.equal(await text(page, 'ro-a'), '33.8');
  assert.equal(await text(page, 'ro-tag'), '21% · 19%');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.match(await text(page, 'prediction-feedback'), /^You predicted the reaction had stopped/);
  // Starting from the other side reaches the same equilibrium.
  await page.locator('input[name="start"][value="product"]').check();
  assert.equal(await text(page, 'ro-b'), '80.0');
  assert.match(await text(page, 'ro-q-u'), /^> K/);
  await skip(page, 4);
  assert.equal(await text(page, 'ro-a'), '33.8');
  assert.equal(await text(page, 'ro-b'), '12.5');
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  await page.close();
});

test('adding reactant raises only the forward rate first; heating raises K', async () => {
  const { page } = await open();
  await page.locator('input[name="prediction"][value="both"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await skip(page, 4); await page.locator('#tag').check(); await skip(page, 1);
  assert.equal(await page.locator('#add').isDisabled(), true);
  await page.locator('input[name="disturb"][value="forward"]').check();
  await page.getByRole('button', { name: 'Save, then add it' }).click();
  await page.locator('#add').click();
  assert.equal(await text(page, 'ro-a'), '43.8');
  assert.equal(await text(page, 'ro-rates'), '1.61 ⇄ 1.24');
  assert.match(await text(page, 'ro-q-u'), /^< K/);
  assert.match(await text(page, 'disturb-feedback'), /^You predicted it\. Splitting jumped from 1\.24 to 1\.61/);
  await skip(page, 4);
  assert.match(await text(page, 'ro-q-u'), /^= K/);
  const coolB = Number(await text(page, 'ro-b'));
  await page.locator('#temp').evaluate(el => { el.value = '60'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  assert.match(await text(page, 'temp-out'), /^60 °C · K = 5\d\.\d mM$/);
  assert.match(await text(page, 'ro-q-u'), /^< K/);
  await skip(page, 4);
  assert.ok(Number(await text(page, 'ro-b')) > coolB * 2);
  await page.close();
});

test('independent practice hides the figure supports and names each misconception', async () => {
  const { page, errors } = await open();
  await page.locator('input[name="prediction"][value="both"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await skip(page, 4); await page.locator('#tag').check(); await skip(page, 1);
  await page.getByRole('button', { name: 'Start practice' }).click();
  assert.equal(await text(page, 'ro-a'), '—');
  assert.equal(await text(page, 'ro-rates'), '—');
  assert.equal(await page.locator('#run').isDisabled(), true);
  assert.equal(await page.locator('#tag').isDisabled(), true);
  assert.match(await page.locator('#figure').textContent(), /Hidden during practice/);
  const rate = (await text(page, 'p1-q')).match(/splitting rate is ([\d.]+) mM\/s/)[1];
  await page.locator('#p1-answer').fill('0'); await page.locator('#p1 button').click();
  assert.match(await text(page, 'p1-feedback'), /“reaction has stopped” idea/);
  await page.locator('#p1-answer').fill(String(rate * 2)); await page.locator('#p1 button').click();
  assert.match(await text(page, 'p1-feedback'), /counted NO₂ instead of N₂O₄/);
  await page.locator('#p1-answer').fill(rate); await page.locator('#p1 button').click();
  assert.match(await text(page, 'p1-feedback'), /^Correct/);
  await page.locator('#p2-answer').fill('0.6'); await page.locator('#p2 button').click();
  assert.match(await text(page, 'p2-feedback'), /without squaring/);
  await page.locator('#p2-answer').fill('1.2'); await page.locator('#p2 button').click();
  assert.match(await text(page, 'p2-feedback'), /multiplied by the coefficient/);
  await page.locator('#p2-answer').fill('7.2'); await page.locator('#p2 button').click();
  assert.match(await text(page, 'p2-feedback'), /^Correct: Q = 12² \/ 20 = 7\.2 mM/);
  await page.locator('input[name="p3"][value="none"]').check(); await page.locator('#p3 button').click();
  assert.match(await text(page, 'p3-feedback'), /^Sealed is not the same as at equilibrium/);
  await page.locator('input[name="p3"][value="backward"]').check(); await page.locator('#p3 button').click();
  assert.match(await text(page, 'p3-feedback'), /^Correct/);
  assert.equal(await text(page, 'practice-score'), '3 of 3 correct.');
  await page.getByRole('button', { name: 'Bring back the figure' }).click();
  assert.equal(await text(page, 'ro-a'), '33.8');
  assert.equal(await page.locator('#run').isDisabled(), false);
  await page.locator('input[name="transfer"][value="spread"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct\. In a saturated solution/);
  await page.locator('button[data-set-lang="zh"]').click();
  assert.match(await text(page, 'status'), /[一-鿿]/);
  await page.locator('button[data-set-lang="en"]').click();
  await page.getByRole('button', { name: 'Reset lesson' }).click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#run').isDisabled(), true);
  assert.equal(await text(page, 'ro-b'), '0.0');
  assert.deepEqual(errors, []);
  await page.close();
});

test('equilibrium lesson fits phones and short laptops in both schemes', async () => {
  for (const [width, height] of [[360, 800], [1280, 720], [1024, 600], [1440, 900]]) {
    for (const colorScheme of ['light', 'dark']) {
      const { page, errors } = await open({ viewport: { width, height }, colorScheme });
      const m = await page.evaluate(() => {
        const r = document.querySelector('.figure-pane .readouts').getBoundingClientRect();
        return { overflow: document.documentElement.scrollWidth - innerWidth, bottom: r.bottom, top: r.top, two: getComputedStyle(document.querySelector('.panel')).display !== 'contents', h: innerHeight };
      });
      assert.ok(m.overflow <= 0, `${width}x${height} ${colorScheme} overflows by ${m.overflow}`);
      if (m.two) assert.ok(m.bottom <= m.h && m.top >= 0, `${width}x${height} readouts out of view`);
      assert.deepEqual(errors, []);
      await page.close();
    }
  }
});
