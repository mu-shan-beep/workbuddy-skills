const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/seasons.html')).href;
const text = (page, id) => page.locator('#' + id).textContent();
const day = (page, label) => page.locator('#dates button', { hasText: label }).click();
const place = (page, value) => page.locator(`label:has(input[name="place"][value="${value}"])`).click();

async function open(t, viewport) {
  const page = await browser.newPage({ reducedMotion: 'reduce', viewport });
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
  t.after(async () => { assert.deepEqual(errors, []); assert.deepEqual(requests, []); await page.close(); });
  await page.goto(url);
  return page;
}
async function predict(page, value) {
  await page.locator(`input[name="prediction"][value="${value}"]`).check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
}

test('seasons: angle and day length change, distance runs the other way, hemispheres oppose', async t => {
  const page = await open(t);
  assert.equal(await page.locator('#day').isDisabled(), true);
  assert.equal(await page.locator('#tilt').isDisabled(), true);
  await predict(page, 'distance');
  await day(page, 'Jun 21');
  assert.equal(await text(page, 'ro-noon'), '73.5°');
  assert.equal(await text(page, 'ro-day'), '14 h 50 min');
  assert.equal(await text(page, 'ro-q'), '483');
  await day(page, 'Dec 21');
  assert.equal(await text(page, 'ro-noon'), '26.7°');
  assert.equal(await text(page, 'ro-day'), '9 h 10 min');
  assert.equal(await text(page, 'ro-q'), '157');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  // Same day, mirror latitude: the daylight is what Beijing lacks.
  await place(page, 'sydney');
  assert.equal(await text(page, 'lat-out'), '33.9°S');
  const sydney = await text(page, 'ro-day');
  assert.match(sydney, /^14 h \d+ min$/);
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.equal(await page.locator('#practice').isVisible(), true);
  assert.match(await text(page, 'prediction-feedback'), /closest to the Sun around January 3/);
  // Closest in January, farthest in July.
  await place(page, 'beijing');
  await day(page, 'Jan 3'); assert.equal(await text(page, 'ro-r'), '0.983 AU');
  await day(page, 'Jul 4'); assert.equal(await text(page, 'ro-r'), '1.017 AU');
  // Polar night: Tromsø on Dec 21.
  await place(page, 'tromso'); await day(page, 'Dec 21');
  assert.equal(await text(page, 'ro-day'), '0 h 0 min');
  assert.equal(await text(page, 'ro-noon'), 'Below horizon');
  await page.locator('input[name="transfer"][value="poles"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct/);
});

test('seasons: with no tilt only distance is left, and it moves both hemispheres together', async t => {
  const page = await open(t);
  await predict(page, 'tilt');
  assert.match(await text(page, 'planet-status'), /opposite seasons/);
  await page.locator('button[data-tilt="0"]').click();
  assert.equal(await text(page, 'tilt-out'), '0.0°');
  assert.match(await text(page, 'planet-status'), /nearly flat/);
  await page.locator('label:has(input[name="ecc"][value="0.2"])').click();
  assert.match(await text(page, 'planet-status'), /rise and fall together/);
  await page.locator('button[data-tilt="23.44"]').click();
  await page.locator('label:has(input[name="ecc"][value="0.0167"])').click();
  assert.match(await text(page, 'planet-status'), /opposite seasons/);
});

test('seasons: independent practice fades the figure, names misconceptions, and restores the controls', async t => {
  const page = await open(t);
  await predict(page, 'tilt');
  await day(page, 'Jun 21'); await day(page, 'Dec 21'); await place(page, 'sydney');
  await page.getByRole('button', { name: 'Start practice' }).click();
  assert.equal(await page.locator('#day').isDisabled(), true);
  assert.equal(await page.locator('#tilt').isDisabled(), true);
  assert.equal(await text(page, 'ro-noon'), '?');
  assert.equal(await page.locator('#g-year').isVisible(), false);
  assert.equal(await page.locator('#g-clock').isVisible(), false);
  const p1 = page.locator('.problem[data-problem="0"]');
  await p1.locator('input[name="answer"]').fill('60');
  await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /^Not yet\. You used the equinox Sun/);
  assert.equal(await text(page, 'ro-noon'), '83.4°');
  await p1.locator('input[name="answer"]').fill('83.4');
  await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /^Correct/);
  await page.getByRole('button', { name: 'Next case →' }).click();
  assert.equal(await text(page, 'ro-q'), '?');
  const p2 = page.locator('.problem[data-problem="1"]');
  await p2.locator('input[value="july"]').check();
  await p2.getByRole('button', { name: 'Check' }).click();
  assert.match(await p2.locator('[data-feedback]').textContent(), /“July is summer” habit/);
  await page.getByRole('button', { name: 'Next case →' }).click();
  const p3 = page.locator('.problem[data-problem="2"]');
  await p3.locator('input[name="answer"]').fill('7');
  await p3.getByRole('button', { name: 'Check' }).click();
  assert.match(await p3.locator('[data-feedback]').textContent(), /assumed the Sun rises every day/);
  assert.equal(await text(page, 'ro-day'), '0 h 0 min');
  assert.equal(await text(page, 'practice-score'), 'All 3 done; 0 right on the first try.');
  await page.getByRole('button', { name: 'Leave practice' }).click();
  assert.equal(await page.locator('#day').isDisabled(), false);
  assert.equal(await text(page, 'day-out'), 'Dec 21');
  assert.equal(await text(page, 'lat-out'), '33.9°S');
  await page.getByRole('button', { name: 'Reset everything' }).click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#practice').isVisible(), false);
  assert.equal(await page.locator('#day').isDisabled(), true);
  assert.equal(await text(page, 'day-out'), 'Mar 20');
});

test('seasons: language switch, short laptops and phones', async t => {
  const page = await open(t, { width: 1280, height: 720 });
  await page.getByRole('button', { name: '中文' }).click();
  assert.match(await text(page, 'summary'), /北京/);
  assert.equal(await text(page, 'day-out'), '3月20日');
  for (const [width, height] of [[1280, 720], [1024, 600], [768, 1024], [360, 800]]) {
    await page.setViewportSize({ width, height });
    const box = await page.evaluate(() => {
      const r = document.querySelector('.readouts').getBoundingClientRect();
      return { bottom: r.bottom, height: r.height, overflow: document.documentElement.scrollWidth - innerWidth, twoPane: getComputedStyle(document.querySelector('.panel')).display === 'block' };
    });
    assert.equal(box.overflow, 0, `no horizontal overflow at ${width}`);
    assert.ok(box.height > 40);
    if (box.twoPane) assert.ok(box.bottom <= height, `readouts in view at ${width}×${height}`);
  }
});

test('seasons: the 3D orbit turns by drag, slider and reset without changing the model, and its globe agrees with the model', async t => {
  const page = await open(t, { width: 1440, height: 900 });
  await predict(page, 'tilt');
  await day(page, 'Jun 21');
  const readouts = () => page.locator('.readouts').innerText();
  const before = await readouts(), summary = await text(page, 'summary');
  assert.equal(await page.locator('#g-orbit').getAttribute('data-view'), '0,28');
  const globe = await page.locator('#g-globe').innerHTML();
  // Drag across the orbit panel, away from the Sun.
  const box = await page.locator('#g-orbit .hit').boundingBox();
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.2 + 60, box.y + box.height * 0.3 + 40, { steps: 4 });
  await page.mouse.up();
  const turned = await page.locator('#g-orbit').getAttribute('data-view');
  assert.notEqual(turned, '0,28');
  assert.notEqual(await page.locator('#g-globe').innerHTML(), globe, 'the globe is redrawn from the new camera');
  assert.equal(await readouts(), before);
  assert.equal(await text(page, 'summary'), summary);
  // Keyboard: the view sliders are native ranges.
  await page.locator('#view-az').focus();
  await page.keyboard.press('ArrowRight');
  assert.notEqual(await page.locator('#g-orbit').getAttribute('data-view'), turned);
  await page.locator('#view-el').fill('90');
  assert.match(await page.locator('#g-orbit').getAttribute('data-view'), /,90$/);
  assert.equal(await readouts(), before);
  await page.getByRole('button', { name: 'Reset view' }).click();
  assert.equal(await page.locator('#g-orbit').getAttribute('data-view'), '0,28');
  // The lit share of the latitude circle on the globe is the model's daylight.
  const share = Number(await page.locator('#g-globe').getAttribute('data-lit-share'));
  const [h, min] = (await text(page, 'ro-day')).match(/\d+/g).map(Number);
  assert.ok(Math.abs(share * 24 - (h + min / 60)) < 0.25, `${share * 24} vs ${h}:${min}`);
  await place(page, 'tromso'); await day(page, 'Dec 21');
  assert.equal(Number(await page.locator('#g-globe').getAttribute('data-lit-share')), 0, 'polar night: no lit arc');
});
