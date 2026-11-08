const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/four-stroke-engine.html')).href;
const text = (page, id) => page.locator('#' + id).textContent();
const step = (page, label) => page.locator('#steps button', { hasText: label }).click();
const setAngle = (page, value) => page.locator('#angle').evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));

async function open(t, options = {}) {
  const context = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 1440, height: 900 }, ...options });
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
  t.after(async () => { assert.deepEqual(errors, []); assert.deepEqual(requests, []); await context.close(); });
  await page.goto(url);
  await page.waitForTimeout(100);
  return page;
}
async function predict(page, turns = '1', next = 'power') {
  await page.locator(`input[name="turns"][value="${turns}"]`).check();
  await page.locator(`input[name="next"][value="${next}"]`).check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
}

test('engine: one spark and one opening of each valve per 720°, with the strokes in order', async t => {
  const page = await open(t);
  assert.equal(await page.locator('#angle').isDisabled(), true, 'no turning before a prediction');
  assert.equal(await text(page, 'ro-angle'), '0°');
  await predict(page, '1', 'power');
  assert.match(await text(page, 'prediction-feedback'), /plug stays idle through 0°–360°/);
  assert.match(await text(page, 'prediction-feedback'), /rising with both valves shut is compression/);
  const seen = [];
  for (let i = 0; i < 16; i++) {
    await step(page, '+45°');
    seen.push([await text(page, 'ro-angle'), await text(page, 'ro-stroke'), await text(page, 'ro-valves')]);
  }
  const at = deg => seen.find(([a]) => a === deg + '°');
  assert.deepEqual(at(90).slice(1), ['Intake', 'Intake open']);
  assert.deepEqual(at(270).slice(1), ['Compression', 'Both shut']);
  assert.deepEqual(at(450).slice(1), ['Power', 'Both shut']);
  assert.deepEqual(at(630).slice(1), ['Exhaust', 'Exhaust open']);
  assert.equal(seen.filter(([, , v]) => v === 'Intake open').length, 3, 'intake open only at 45°, 90°, 135°');
  assert.equal(seen.filter(([, , v]) => v === 'Exhaust open').length, 3, 'exhaust open only at 585°, 630°, 675°');
  assert.equal(seen[seen.length - 1][0], '720°');
  for (const id of ['seen-compress', 'seen-spark', 'seen-cycle']) assert.match(await page.locator('#' + id).getAttribute('class'), /done/);
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.equal(await page.locator('#practice').isVisible(), true);
  // Volume and pressure: compression ratio 10, and the spark lifts pressure at the same volume.
  await setAngle(page, 0); assert.equal(await text(page, 'ro-p-u'), '44 cm³');
  await setAngle(page, 180); assert.equal(await text(page, 'ro-p-u'), '443 cm³');
  await setAngle(page, 359); const before = parseFloat(await text(page, 'ro-p'));
  await setAngle(page, 361); const after = parseFloat(await text(page, 'ro-p'));
  assert.ok(after > 2.5 * before, `pressure jumps at the spark (${before} → ${after})`);
  await setAngle(page, 360);
  assert.match(await text(page, 'ro-stroke-u'), /spark/);
  assert.equal(await page.locator('#rt-spark *').count() > 0, true);
  await setAngle(page, 0);
  assert.equal(await page.locator('#rt-spark *').count(), 0, 'no spark at the end of exhaust');
  await page.locator('input[name="transfer"][value="180"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct/);
  await page.locator('input[name="transfer"][value="90"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /each cylinder fires every turn/);
});

test('engine: timing marks show the cams at half speed, and the crank can be dragged', async t => {
  const page = await open(t);
  await predict(page, '2', 'compression');
  assert.match(await text(page, 'belt-status'), /All three marks point up/);
  await step(page, '+360°');
  assert.equal(await text(page, 'ro-angle'), '360°');
  assert.match(await text(page, 'ro-angle-u'), /cams 180°/);
  assert.match(await text(page, 'belt-status'), /cam marks point down/);
  await step(page, '+360°');
  assert.match(await text(page, 'ro-angle-u'), /cams 360°/);
  await setAngle(page, 0);
  // Drag the crank disc clockwise a quarter turn around its centre.
  const box = await page.locator('#engine [data-part=crank] .iso-solid').last().boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2, r = box.width * 0.35;
  // Start at nine o'clock on the web (the rod covers twelve o'clock at 0°) and sweep to twelve.
  await page.mouse.move(cx - r, cy); await page.mouse.down();
  for (let i = 1; i <= 10; i++) { const a = -Math.PI / 2 + i / 10 * Math.PI / 2; await page.mouse.move(cx + r * Math.sin(a), cy - r * Math.cos(a)); }
  await page.mouse.up();
  const angle = parseInt(await text(page, 'ro-angle'), 10);
  assert.ok(angle > 60 && angle < 120, `dragging a quarter turn clockwise moves the crank about 90° (got ${angle}°)`);
});

test('engine: practice fades the readouts, names misconceptions, and restores the controls', async t => {
  const page = await open(t);
  await predict(page);
  for (let i = 0; i < 4; i++) await step(page, '+180°');
  await setAngle(page, 100);
  await page.getByRole('button', { name: 'Start practice' }).click();
  assert.equal(await page.locator('#angle').isDisabled(), true);
  assert.equal(await text(page, 'ro-angle'), '450°');
  assert.equal(await text(page, 'ro-stroke'), '—');
  assert.equal(await text(page, 'ro-valves'), '—');
  const p0 = page.locator('.problem[data-problem="0"]');
  await p0.locator('input[value="intake"]').check(); await p0.getByRole('button', { name: 'Check' }).click();
  assert.match(await p0.locator('[data-feedback]').textContent(), /falling piston means intake/);
  assert.equal(await text(page, 'ro-stroke'), 'Power', 'readouts return after checking');
  await page.getByRole('button', { name: 'Next case →' }).click();
  const p1 = page.locator('.problem[data-problem="1"]');
  await p1.locator('input').fill('50'); await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /assumes a spark every turn/);
  await p1.locator('input').fill('25'); await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /^Correct: 25/);
  await page.getByRole('button', { name: 'Next case →' }).click();
  const p2 = page.locator('.problem[data-problem="2"]');
  await p2.locator('input[value="every"]').check(); await p2.getByRole('button', { name: 'Check' }).click();
  assert.match(await p2.locator('[data-feedback]').textContent(), /^Correct/);
  assert.equal(await text(page, 'practice-score'), 'All 3 done; 1 right on the first try.');
  await page.getByRole('button', { name: 'Leave practice' }).click();
  assert.equal(await page.locator('#angle').isDisabled(), false);
  assert.equal(await text(page, 'ro-angle'), '100°');
  await page.getByRole('button', { name: 'Reset everything' }).click();
  assert.equal(await page.locator('#angle').isDisabled(), true);
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await text(page, 'ro-angle'), '0°');
});

test('engine: focus guide follows the steps and the look sequence', async t => {
  const page = await open(t);
  const opacity = part => page.locator(`#experiment [data-part="${part}"]`).first().evaluate(el => Number(getComputedStyle(el).opacity));
  assert.equal(await opacity('piston'), 1);
  assert.equal(await opacity('valves'), 1);
  assert.ok(await opacity('cams') < 0.5, 'predict step dims the cams');
  await predict(page);
  for (let i = 0; i < 4; i++) await step(page, '+180°');
  await page.locator('ol.look > li').nth(3).click();
  await page.waitForTimeout(50);
  assert.equal(await opacity('cams'), 1);
  assert.equal(await opacity('belt'), 1);
  assert.ok(await opacity('piston') < 0.5, 'the timing step dims the piston');
});

test('engine: phone, dark and Chinese layouts stay inside the screen; short screens keep readouts in view', async t => {
  for (const options of [{ viewport: { width: 360, height: 780 } }, { viewport: { width: 1440, height: 900 }, colorScheme: 'dark' }]) {
    const page = await open(t, options);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no horizontal overflow');
    assert.ok((await page.locator('#engine').boundingBox()).height > 200, 'the cutaway stays readable');
  }
  const zh = await open(t);
  await zh.goto(url + '?lang=zh');
  assert.equal(await zh.locator('#ro-stroke').textContent(), '进气');
  for (const [width, height] of [[1280, 720], [1366, 768], [1024, 600]]) {
    const page = await open(t, { viewport: { width, height } });
    const layout = await page.evaluate(() => {
      const pane = document.querySelector('.lesson > .figure-pane'), r = pane.querySelector('.readouts').getBoundingClientRect();
      return { twoPane: matchMedia('(min-width:960px) and (min-height:560px)').matches, top: r.top, bottom: r.bottom, height: r.height, bar: document.querySelector('.bar').getBoundingClientRect().bottom,
        overflow: pane.scrollHeight - pane.clientHeight, cue: !document.querySelector('.pane-more')?.hidden };
    });
    assert.ok(layout.height >= 40, `${width}×${height}: readouts are not squashed`);
    if (layout.twoPane) {
      assert.ok(layout.top >= layout.bar && layout.bottom <= height, `${width}×${height}: readouts stay inside the viewport`);
      assert.equal(layout.cue, layout.overflow > 1, `${width}×${height}: the more-below cue matches overflow`);
    }
  }
});
