const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader','--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/natural-selection.html')).href;
const slide = (page, id, value) => page.locator('#' + id).evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));
const text = (page, id) => page.locator('#' + id).textContent();
// Independent reference: one-locus selection with C dominant, survival 1 − s·mismatch with the bark.
function reference(p, bark, s, gens) {
  for (let g = 0; g < gens; g++) {
    const wD = 1 - s * (1 - bark), wL = 1 - s * bark, q = 1 - p;
    p = p * wD / ((1 - q * q) * wD + q * q * wL);
  }
  return p;
}
async function open(options = {}) {
  const page = await browser.newPage({ reducedMotion: 'reduce', ...options });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const remote = []; page.on('request', r => { if (!r.url().startsWith('file:')) remote.push(r.url()); });
  await page.goto(url);
  return { page, errors, remote };
}
async function predict(page, value = 'select') {
  await page.locator(`input[name="prediction"][value="${value}"]`).check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
}

test('selection follows the one-locus model and unlocks the explanation only after the population shifts', async () => {
  const { page, errors, remote } = await open();
  assert.equal(await page.locator('#next').isDisabled(), true);
  assert.equal(await page.locator('#hunt').isDisabled(), true);
  assert.equal(await page.locator('#explanation').isVisible(), false);
  await predict(page, 'darken');
  await page.locator('#pop').selectOption('inf');
  assert.equal(await text(page, 'ro-gen'), '0');
  assert.equal(await text(page, 'ro-p'), '0.020');
  assert.equal(await text(page, 'ro-dark'), '4.0%');
  await page.locator('#next').click();
  assert.equal(await text(page, 'ro-p'), reference(0.02, 0.9, 0.3, 1).toFixed(3));
  assert.equal(await text(page, 'ro-surv'), '97% / 73%');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  await page.locator('#run10').click();
  const p11 = reference(0.02, 0.9, 0.3, 11);
  assert.equal(await text(page, 'ro-gen'), '11');
  assert.equal(await text(page, 'ro-p'), p11.toFixed(3));
  assert.equal(await text(page, 'ro-dark'), ((1 - (1 - p11) ** 2) * 100).toFixed(1) + '%');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.match(await text(page, 'prediction-feedback'), /^You predicted the light moth would darken itself/);
  // Clean air: the camouflaged morph flips and the dark allele starts to fall.
  const before = Number(await text(page, 'ro-p'));
  await slide(page, 'bark', 10);
  await page.locator('#next').click();
  assert.ok(Number(await text(page, 'ro-p')) < before);
  // Neutral bark: nothing to select.
  await slide(page, 'bark', 50);
  const neutral = await text(page, 'ro-p');
  await page.locator('#next').click();
  assert.equal(await text(page, 'ro-p'), neutral);
  assert.deepEqual(errors, []); assert.deepEqual(remote, []);
  await page.close();
});

test('no variation means no response, mutation supplies it, and drift is seeded', async () => {
  const { page } = await open();
  await predict(page);
  await page.locator('#pop').selectOption('inf');
  await slide(page, 'start', 0);
  await slide(page, 'bark', 100);
  for (let i = 0; i < 3; i++) await page.locator('#run10').click();
  assert.equal(await text(page, 'ro-gen'), '30');
  assert.equal(await text(page, 'ro-p'), '0.000');
  assert.equal(await text(page, 'ro-dark'), '0.0%');
  await page.locator('#mutation').check();
  await page.locator('#run10').click();
  assert.ok(Number(await text(page, 'ro-p')) > 0, 'mutation creates the variant selection can then act on');
  // Small population, no selection: frequencies wander, and the same seed replays the same path.
  await page.locator('#mutation').uncheck();
  await slide(page, 'strength', 0);
  await page.locator('#pop').selectOption('20');
  await slide(page, 'start', 50);
  await page.locator('#run10').click();
  const first = await text(page, 'ro-p');
  assert.notEqual(first, '0.500');
  await page.locator('#restart').click();
  assert.equal(await text(page, 'ro-gen'), '0');
  await page.locator('#run10').click();
  assert.equal(await text(page, 'ro-p'), first);
  await page.close();
});

test('the learner can be the bird: eaten moths set that generation’s survival', async () => {
  const { page } = await open();
  await predict(page);
  await page.locator('#hunt').click();
  assert.equal(await page.locator('#next').isDisabled(), true);
  const light = page.locator('#scene .moth[data-morph="light"]');
  const dark = page.locator('#scene .moth[data-morph="dark"]');
  assert.equal(await light.count() + await dark.count(), 40);
  const nDark = await dark.count();
  for (let i = 0; i < 3; i++) await light.nth(i).click();
  await page.locator('#finish-hunt').click();
  assert.equal(await text(page, 'ro-gen'), '1');
  const nLight = 40 - nDark;
  assert.equal(await text(page, 'ro-surv'), `100% / ${Math.round((1 - 3 / nLight) * 100)}%`);
  assert.match(await text(page, 'ro-surv-u'), /your hunt/);
  assert.match(await text(page, 'status'), new RegExp(`You ate 3 of ${nLight} light moths and 0 of ${nDark} black moths`));
  await page.close();
});

test('independent practice hides the supports and names the misconception behind each wrong answer', async () => {
  const { page } = await open();
  await predict(page);
  await page.locator('#run10').click(); await page.locator('#run10').click();
  assert.equal(await page.locator('#practice').isVisible(), true);
  await page.getByRole('button', { name: 'Start practice' }).click();
  assert.equal(await text(page, 'ro-p'), '—');
  assert.equal(await page.locator('#plot .p-line').count(), 0);
  assert.equal(await page.locator('#next').isDisabled(), true);
  await page.locator('input[name="p1"][value="yes"]').check();
  await page.locator('#p1-form button').click();
  assert.match(await text(page, 'p1-feedback'), /^Misconception: inheritance of acquired traits/);
  await page.locator('input[name="p1"][value="variation"]').check();
  await page.locator('#p1-form button').click();
  assert.match(await text(page, 'p1-feedback'), /^Right/);
  await page.locator('#p2-answer').fill('0.4');
  await page.locator('#p2-form button').click();
  assert.match(await text(page, 'p2-feedback'), /Misconception: the environment creates the trait it favors/);
  assert.equal(await page.locator('#scene .moth[data-morph="dark"]').count(), 0);
  await page.locator('#p2-answer').fill('0');
  await page.locator('#p2-form button').click();
  assert.match(await text(page, 'p2-feedback'), /^Right, still 0/);
  await page.locator('input[name="p3"][value="95"]').check();
  await page.locator('#p3-form button').click();
  assert.match(await text(page, 'p3-feedback'), /Misconception: selection acts all at once/);
  await page.locator('input[name="p3"][value="50"]').check();
  await page.locator('#p3-form button').click();
  const p10 = reference(0.02, 1, 0.3, 10);
  assert.match(await text(page, 'p3-feedback'), new RegExp(`^Right\\. The model gives ${Math.round((1 - (1 - p10) ** 2) * 100)}%`));
  assert.equal(await text(page, 'practice-score'), '0 of 3 right on the first try.');
  await page.getByRole('button', { name: 'Bring back the plot and readouts' }).click();
  assert.equal(await text(page, 'ro-gen'), '20');
  assert.equal(await page.locator('#plot .p-line').count(), 1);
  // Transfer, then reset.
  await page.locator('input[name="transfer"][value="learn"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Not quite/);
  await page.locator('input[name="transfer"][value="select"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct/);
  await page.getByRole('button', { name: 'Reset lesson' }).click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#next').isDisabled(), true);
  assert.equal(await text(page, 'ro-gen'), '0');
  await page.close();
});

test('the lesson switches language, passes its self-check, and fits phone and short laptop screens', async () => {
  for (const [width, height] of [[360, 800], [1280, 720], [1024, 600], [768, 1024], [1440, 900]]) {
    for (const colorScheme of ['light', 'dark']) {
      const { page, errors } = await open({ viewport: { width, height }, colorScheme });
      assert.deepEqual(await page.evaluate(() => CHECK), []);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${width} overflow`);
      if (width >= 960 && height >= 560) {
        const box = await page.locator('.readouts').boundingBox();
        assert.ok(box.y + box.height <= height, `${width}×${height} readouts in view`);
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
  }
  const { page } = await open();
  await page.getByRole('button', { name: '中文' }).click();
  assert.equal(await page.locator('h1 [lang="zh"]').isVisible(), true);
  assert.match(await text(page, 'summary'), /^第 0 代/);
  await page.close();
});
