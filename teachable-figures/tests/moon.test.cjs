const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/moon-phases.html')).href;
const text = (page, id) => page.locator('#' + id).textContent();
const phase = (page, e) => page.locator(`#phases button[data-e="${e}"]`).click();
const viewFrom = (page, v) => page.locator(`#views button[data-view="${v}"]`).click();

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
async function unlock(page) {
  await phase(page, '40'); await phase(page, '180'); await viewFrom(page, 'above');
}

test('moon: the answer stays hidden until a prediction, then the phase follows the Sun–Earth–Moon angle', async t => {
  const page = await open(t);
  assert.equal(await page.locator('#elong').isDisabled(), true);
  assert.equal(await text(page, 'ro-angle'), '90°');
  assert.equal(await text(page, 'ro-lit'), '?');
  assert.equal(await text(page, 'ro-rise'), '?');
  await predict(page, 'shadow');
  assert.match(await text(page, 'prediction-feedback'), /points directly away from the Sun/);
  assert.equal(await text(page, 'ro-lit'), '50%');
  assert.equal(await text(page, 'ro-lit-u'), 'First quarter · lit on the right');
  assert.equal(await text(page, 'ro-rise'), '12:00');
  assert.equal(await text(page, 'ro-rise-u'), 'highest 18:00 · sets 0:00');
  // A crescent is nowhere near Earth's shadow.
  await phase(page, '40');
  assert.equal(await text(page, 'ro-lit'), '12%');
  assert.equal(await text(page, 'ro-ecl'), 'None');
  assert.equal(await text(page, 'ro-ecl-u'), '139.7° from the shadow’s centre');
  // Full Moon: fully lit, rises at sunset, and with the real tilt it misses the shadow.
  await phase(page, '180');
  assert.equal(await text(page, 'ro-lit'), '100%');
  assert.equal(await text(page, 'ro-rise'), '18:00');
  assert.equal(await text(page, 'ro-ecl-u'), '5.1° from the shadow’s centre');
  assert.equal(await page.locator('#explanation').isVisible(), false);
  await viewFrom(page, 'above');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.equal(await page.locator('#practice').isVisible(), true);
  // Non-linear: 135° is 85% lit, not 75%. The southern hemisphere sees the mirror image.
  await phase(page, '135');
  assert.equal(await text(page, 'ro-lit'), '85%');
  await phase(page, '90');
  await page.locator('label:has(input[name="hemi"][value="south"])').click();
  assert.equal(await text(page, 'ro-lit-u'), 'First quarter · lit on the left');
  await phase(page, '270');
  assert.equal(await text(page, 'ro-rise'), '0:00');
  assert.equal(await text(page, 'ro-lit-u'), 'Third quarter · lit on the right');
});

test('moon: turning the 3D view changes the drawing, never the model', async t => {
  const page = await open(t);
  await predict(page, 'half');
  await phase(page, '135');
  const snapshot = () => page.evaluate(() => ({
    readouts: [...document.querySelectorAll('.readout strong, .readout .u')].map(n => n.textContent),
    summary: document.querySelector('#summary').textContent,
    sky: document.querySelector('#g-sky').innerHTML,
    clock: document.querySelector('#g-clock').innerHTML,
    space: document.querySelector('#g-space').innerHTML,
    moonDisk: document.querySelector('#g-space [data-part="moon"] path')?.getAttribute('d')
  }));
  const before = await snapshot();
  // Sliders, preset, keyboard and drag all turn the camera.
  await page.locator('#yaw').fill('200');
  await page.locator('#pitch').fill('60');
  const afterSliders = await snapshot();
  await page.locator('#figure').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#yaw').inputValue(), '210');
  await page.keyboard.press('ArrowUp');
  assert.equal(await page.locator('#pitch').inputValue(), '65');
  const box = await page.locator('#g-space .hit').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 30, { steps: 4 });
  await page.mouse.up();
  assert.notEqual(await page.locator('#yaw').inputValue(), '210');
  const after = await snapshot();
  for (const s of [afterSliders, after]) {
    assert.notEqual(s.space, before.space, 'space view redrawn');
    assert.deepEqual(s.readouts, before.readouts);
    assert.equal(s.summary, before.summary);
    assert.equal(s.sky, before.sky);
    assert.equal(s.clock, before.clock);
  }
  // From the Sun's side the Moon in space looks fully lit whatever its phase.
  await viewFrom(page, 'sun');
  assert.equal(await page.locator('#g-space [data-part="moon"] circle.moon-lit, #g-space [data-part="moon"] path.moon-lit').count(), 1);
  assert.equal(await text(page, 'ro-lit'), '85%');
  await page.getByRole('button', { name: 'Reset view' }).click();
  assert.equal(await page.locator('#yaw').inputValue(), '270');
  assert.equal(await page.locator('#pitch').inputValue(), '28');
});

test('moon: eclipses need the full Moon near a node; a flat orbit would eclipse every month', async t => {
  const page = await open(t);
  await predict(page, 'half');
  await unlock(page);
  assert.match(await text(page, 'eclipse-status'), /no solar eclipse.*no lunar eclipse; the Moon passes 5\.1° from the shadow’s centre/);
  await page.locator('button[data-node="5"]').click();
  assert.match(await text(page, 'eclipse-status'), /a solar eclipse.*a lunar eclipse/);
  assert.equal(await text(page, 'ro-ecl'), 'Lunar eclipse');
  await page.locator('button[data-node="90"]').click();
  assert.equal(await text(page, 'ro-ecl'), 'None');
  await page.locator('label:has(input[name="incl"][value="0"])').click();
  assert.match(await text(page, 'eclipse-status'), /a solar eclipse.*a lunar eclipse/);
  assert.equal(await text(page, 'ro-ecl'), 'Lunar eclipse');
  await page.locator('#node').fill('40');
  assert.equal(await text(page, 'ro-ecl'), 'Lunar eclipse');
  await page.locator('label:has(input[name="incl"][value="5.145"])').click();
  assert.equal(await text(page, 'ro-ecl'), 'None');
  await page.locator('input[name="transfer"][value="small"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Not quite\. Earth’s umbra reaches/);
  await page.locator('input[name="transfer"][value="tilt"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Correct/);
});

test('moon: independent practice hides the answers, fades the hints, and names misconceptions', async t => {
  const page = await open(t);
  await predict(page, 'half');
  await unlock(page);
  await page.locator('#elong').fill('200');
  await page.getByRole('button', { name: 'Start practice' }).click();
  assert.equal(await page.locator('#elong').isDisabled(), true);
  assert.equal(await page.locator('#node').isDisabled(), true);
  assert.equal(await page.locator('#yaw').isDisabled(), false, 'the view still turns during practice');
  assert.equal(await text(page, 'ro-angle'), '135°', 'first case keeps the angle as a scaffold');
  assert.equal(await text(page, 'ro-lit'), '?');
  assert.equal(await page.locator('#g-sky .q').count(), 1);
  const p1 = page.locator('.problem[data-problem="0"]');
  assert.equal(await p1.locator('.hint').isVisible(), true);
  await p1.locator('input[name="answer"]').fill('75');
  await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /^Not yet\. You split it by angle/);
  assert.equal(await text(page, 'ro-lit'), '85%');
  await p1.locator('input[name="answer"]').fill('85');
  await p1.getByRole('button', { name: 'Check' }).click();
  assert.match(await p1.locator('[data-feedback]').textContent(), /^Correct/);
  await page.getByRole('button', { name: 'Next case →' }).click();
  assert.equal(await text(page, 'ro-angle'), '?', 'later cases drop the scaffold');
  const p2 = page.locator('.problem[data-problem="1"]');
  assert.equal(await p2.locator('.hint').count(), 0);
  await p2.locator('input[value="dark"]').check();
  await p2.getByRole('button', { name: 'Check' }).click();
  assert.match(await p2.locator('[data-feedback]').textContent(), /does not belong only to the night/);
  assert.equal(await text(page, 'ro-rise'), '0:00');
  await page.getByRole('button', { name: 'Next case →' }).click();
  const p3 = page.locator('.problem[data-problem="2"]');
  await p3.locator('input[value="shadow"]').check();
  await p3.getByRole('button', { name: 'Check' }).click();
  assert.match(await p3.locator('[data-feedback]').textContent(), /That is the shadow model\. .* 139\.7° from this crescent/);
  assert.equal(await text(page, 'practice-score'), 'All 3 done; 0 right on the first try.');
  await page.getByRole('button', { name: 'Leave practice' }).click();
  assert.equal(await page.locator('#elong').isDisabled(), false);
  assert.equal(await text(page, 'ro-angle'), '200°');
  await page.getByRole('button', { name: 'Reset everything' }).click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#elong').isDisabled(), true);
  assert.equal(await text(page, 'ro-angle'), '90°');
  assert.equal(await text(page, 'ro-lit'), '?');
});

test('moon: language switch, short laptops and phones', async t => {
  const page = await open(t, { width: 1280, height: 720 });
  await page.getByRole('button', { name: '中文' }).click();
  await page.locator('input[name="prediction"][value="half"]').check();
  await page.locator('#prediction-form button[type="submit"]').click();
  assert.match(await text(page, 'summary'), /上弦月/);
  assert.equal(await text(page, 'ro-rise'), '12:00');
  for (const [width, height] of [[1280, 720], [1366, 768], [1024, 600], [768, 1024], [360, 800]]) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(50);
    const box = await page.evaluate(() => {
      const r = document.querySelector('.readouts').getBoundingClientRect();
      return { bottom: r.bottom, height: r.height, overflow: document.documentElement.scrollWidth - innerWidth, twoPane: getComputedStyle(document.querySelector('.panel')).display === 'block' };
    });
    assert.equal(box.overflow, 0, `no horizontal overflow at ${width}`);
    assert.ok(box.height > 40);
    if (box.twoPane) assert.ok(box.bottom <= height, `readouts in view at ${width}×${height}`);
  }
});
