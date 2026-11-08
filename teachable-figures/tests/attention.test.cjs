const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = name => pathToFileURL(resolve(__dirname, `../examples/${name}.html`)).href;

async function open(t, name, options = {}) {
  const context = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 1440, height: 900 }, ...options });
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
  t.after(async () => { assert.deepEqual(errors, []); assert.deepEqual(requests, []); await context.close(); });
  await page.goto(url(name));
  await page.waitForTimeout(150);
  return page;
}
const opacity = (page, part) => page.locator(`#experiment [data-part="${part}"]`).first().evaluate(el => Number(getComputedStyle(el).opacity));
const hot = (page, part) => page.locator(`#experiment [data-part="${part}"]`).first().evaluate(el => el.classList.contains('tf-hot'));
async function scrollPanelTo(page, selector) {
  await page.locator(selector).evaluate(el => { const panel = document.querySelector('.panel'); panel.scrollTop += el.getBoundingClientRect().top - panel.getBoundingClientRect().top - 40; });
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}

test('focus guide dims what the active step does not need, follows scroll and focus, and can be switched off', async t => {
  const page = await open(t, 'seasons');
  // Predict step is active on load: only the orbit and the sunbeam stay at full strength.
  assert.equal(await opacity(page, 'orbit'), 1);
  assert.equal(await opacity(page, 'beam'), 1);
  assert.ok(await opacity(page, 'year') < 0.5);
  assert.ok(await opacity(page, 'clock') < 0.5);
  assert.equal(await hot(page, 'orbit'), false, 'step focus dims others without a ring');
  // The planet step needs the orbit, the side view and the year chart.
  await scrollPanelTo(page, '[aria-labelledby="planet-title"]');
  assert.equal(await opacity(page, 'year'), 1);
  assert.ok(await opacity(page, 'beam') < 0.5);
  // A step without data-focus dims nothing.
  await scrollPanelTo(page, '[aria-labelledby="try-title"]');
  for (const part of ['orbit', 'close', 'beam', 'clock', 'year']) assert.equal(await opacity(page, part), 1, part);
  // Keyboard focus wins over the reading line.
  await scrollPanelTo(page, '[aria-labelledby="planet-title"]');
  await page.locator('input[name="prediction"][value="tilt"]').focus();
  await page.waitForFunction(() => getComputedStyle(document.querySelector('#experiment [data-part="beam"]')).opacity === '1', null, { timeout: 3000 });
  assert.equal(await opacity(page, 'beam'), 1);
  assert.ok(await opacity(page, 'year') < 0.5);
  // A presenter can turn the guide off; the choice persists.
  const toggle = page.getByRole('checkbox', { name: 'Focus guide' });
  assert.equal(await toggle.isChecked(), true);
  await toggle.uncheck();
  assert.equal(await opacity(page, 'year'), 1);
  await page.reload();
  await page.waitForTimeout(150);
  assert.equal(await page.getByRole('checkbox', { name: 'Focus guide' }).isChecked(), false);
  assert.equal(await opacity(page, 'year'), 1);
  await page.getByRole('checkbox', { name: 'Focus guide' }).check();
  assert.ok(await opacity(page, 'year') < 0.5);
});

test('ordered highlights step through parts on demand, with a caption, and Escape clears them', async t => {
  const page = await open(t, 'bayes-base-rate');
  await page.waitForTimeout(400);
  assert.equal(await page.locator('#experiment .tf-hot').count(), 0, 'nothing is highlighted before the learner asks');
  assert.equal(await page.locator('.focus-caption').innerText(), '');
  await page.locator('input[name="prediction"][value="90"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await page.locator('#positives-only').check();
  await page.locator('#estimate').fill('9');
  await page.locator('#estimate-check').click();
  await scrollPanelTo(page, '#explanation');
  const nav = page.locator('#explanation .look-nav');
  assert.equal(await nav.locator('.look-num').count(), 4);
  await nav.getByRole('button', { name: 'Next ›' }).click();
  assert.match(await page.locator('.focus-caption').innerText(), /^1\/4\s*Start with the grid/);
  assert.equal(await hot(page, 'grid'), true);
  assert.ok(await opacity(page, 'tree') < 0.5);
  await nav.getByRole('button', { name: 'Next ›' }).click();
  assert.match(await page.locator('.focus-caption').innerText(), /^2\/4/);
  assert.equal(await hot(page, 'tree'), true);
  assert.equal(await hot(page, 'tp'), true);
  assert.ok(await opacity(page, 'grid') < 0.5);
  assert.equal(await page.locator('#explanation ol.look > li').nth(1).getAttribute('aria-current'), 'step');
  await nav.locator('.look-num').nth(3).click();
  assert.match(await page.locator('.focus-caption').innerText(), /^4\/4.*9\.2%/);
  assert.equal(await hot(page, 'ppv'), true);
  await nav.getByRole('button', { name: '‹ Prev' }).click();
  assert.match(await page.locator('.focus-caption').innerText(), /^3\/4/);
  assert.equal(await hot(page, 'fp'), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.focus-caption').innerText(), '');
  assert.equal(await page.locator('#experiment .tf-hot').count(), 0);
  // Clicking an item works too, and Clear clears.
  await page.locator('#explanation ol.look > li').first().click();
  assert.equal(await hot(page, 'grid'), true);
  await nav.getByRole('button', { name: 'Clear' }).click();
  assert.equal(await page.locator('#experiment .tf-hot').count(), 0);
});

test('dual coding links terms and parts both ways, by mouse, keyboard and touch', async t => {
  const page = await open(t, 'seasons');
  const term = page.locator('legend [data-ref="orbit"]:visible');
  assert.equal(await term.getAttribute('role'), 'button');
  assert.equal(await term.getAttribute('tabindex'), '0');
  await term.hover();
  assert.equal(await hot(page, 'orbit'), true);
  assert.ok(await opacity(page, 'beam') < 0.5, 'hovering a term spotlights only its part');
  await page.mouse.move(5, 890);
  assert.equal(await hot(page, 'orbit'), false);
  await term.focus();
  assert.equal(await hot(page, 'orbit'), true);
  await term.blur();
  // Hovering a part shows its label and marks its terms.
  const box = await page.locator('#g-orbit').boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.move(box.x + box.width * 0.5 + 2, box.y + box.height * 0.5 + 2);
  const tip = page.locator('.part-tip');
  assert.equal(await tip.isVisible(), true);
  assert.equal(await tip.textContent(), 'Orbit: the axis keeps pointing the same way');
  assert.equal(await page.locator('legend [data-ref="orbit"]:visible').evaluate(el => el.classList.contains('tf-ref-on')), true);
  await page.mouse.move(1300, 880);
  assert.equal(await tip.isVisible(), false);
  // Keyboard pin with Enter, Escape clears.
  await term.focus();
  await page.keyboard.press('Enter');
  assert.equal(await term.getAttribute('aria-pressed'), 'true');
  await term.blur();
  assert.equal(await hot(page, 'orbit'), true, 'a pinned term keeps its part lit');
  await page.keyboard.press('Escape');
  assert.equal(await term.getAttribute('aria-pressed'), 'false');
  assert.equal(await hot(page, 'orbit'), false);
  await page.locator('.lang-switch [data-set-lang="zh"]').click();
  const box2 = await page.locator('#g-orbit').boundingBox();
  await page.mouse.move(box2.x + box2.width * 0.5, box2.y + box2.height * 0.5);
  await page.mouse.move(box2.x + box2.width * 0.5 + 2, box2.y + box2.height * 0.5 + 2);
  assert.equal(await tip.textContent(), '公转轨道：地轴方向在空间中固定');
});

test('on touch, tapping a term toggles its highlight and parts show no hover tooltip', async t => {
  const page = await open(t, 'gear-ratio', { hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  const term = page.locator('legend [data-ref="driver"]:visible');
  await term.tap();
  assert.equal(await term.getAttribute('aria-pressed'), 'true');
  assert.equal(await hot(page, 'driver'), true);
  await term.tap();
  assert.equal(await term.getAttribute('aria-pressed'), 'false');
  assert.equal(await hot(page, 'driver'), false);
  assert.equal(await page.locator('.part-tip').isVisible(), false);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
});

test('dimming animates only without reduced motion, and pilots stay within the viewport', async t => {
  const still = await open(t, 'gear-ratio');
  assert.equal(await still.locator('#experiment [data-part="driver"]').first().evaluate(el => getComputedStyle(el).transitionDuration.split(',')[0]), '0s');
  const moving = await open(t, 'gear-ratio', { reducedMotion: 'no-preference' });
  assert.notEqual(await moving.locator('#experiment [data-part="driver"]').first().evaluate(el => getComputedStyle(el).transitionDuration.split(',')[0]), '0s');
  // The gear predict step needs only the driver and the output.
  await moving.waitForFunction(() => Number(getComputedStyle(document.querySelector('#experiment [data-part="result"]')).opacity) < 0.5, null, { timeout: 3000 });
  assert.equal(await opacity(moving, 'output'), 1);
  for (const name of ['seasons', 'bayes-base-rate', 'gear-ratio']) {
    for (const viewport of [{ width: 360, height: 800 }, { width: 1280, height: 720 }]) {
      const page = await open(t, name, { viewport });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${name} ${viewport.width}`);
      assert.equal(await page.locator('.focus-bar').count(), 1);
    }
  }
});

// Every complete lesson uses the attention API: named parts, a focused first step, an ordered-highlight
// sequence, and terms that point at parts that exist. Parts drawn only after a prediction are listed here.
const LESSONS = ['seasons', 'bayes-base-rate', 'gear-ratio', 'ship-of-theseus', 'information-entropy', 'dynamic-equilibrium', 'natural-selection', 'price-ceiling', 'chinese-clothing', 'geometry-slices', 'human-anatomy', 'rocket-launch', 'transformer-flow', 'moon-phases', 'four-stroke-engine'];
const LATE_PARTS = { 'price-ceiling': ['cap'] };
test('every lesson names its figure parts, focuses its first step and links its terms to real parts', async t => {
  for (const name of LESSONS) {
    const page = await open(t, name);
    const r = await page.evaluate(() => {
      const ids = v => (v || '').split(/\s+/).filter(Boolean);
      const parts = new Set([...document.querySelectorAll('#experiment [data-part]')].flatMap(el => ids(el.dataset.part)));
      const first = document.querySelector('.panel .step');
      return {
        parts: [...parts],
        nested: document.querySelectorAll('#experiment [data-part] [data-part]').length,
        bars: document.querySelectorAll('.focus-bar').length,
        firstFocus: ids(first && first.dataset.focus),
        focus: [...document.querySelectorAll('[data-focus]')].flatMap(el => ids(el.dataset.focus)),
        refs: [...document.querySelectorAll('[data-ref]')].flatMap(el => ids(el.dataset.ref)),
        looks: document.querySelectorAll('ol.look > li[data-focus]').length,
        dimmed: [...document.querySelectorAll('#experiment [data-part]')].filter(el => Number(getComputedStyle(el).opacity) < 0.5).length,
      };
    });
    const known = new Set([...r.parts, ...(LATE_PARTS[name] || [])]);
    assert.equal(r.bars, 1, `${name}: focus bar`);
    assert.ok(r.parts.length >= 3, `${name}: at least three parts, found ${r.parts}`);
    assert.equal(r.nested, 0, `${name}: parts must not nest`);
    assert.ok(r.firstFocus.length > 0 && r.firstFocus.every(id => r.parts.includes(id)), `${name}: first step focuses existing parts`);
    assert.ok(r.dimmed > 0, `${name}: the first step dims what it does not need`);
    assert.ok(r.looks >= 3, `${name}: an ordered-highlight sequence`);
    assert.deepEqual([...new Set(r.focus.filter(id => !known.has(id)))], [], `${name}: data-focus targets`);
    assert.deepEqual([...new Set(r.refs.filter(id => !known.has(id)))], [], `${name}: data-ref targets`);
  }
});

test('pointing at an organ name lights that organ in the 3D chest without changing the lesson state', async t => {
  const page = await open(t, 'human-anatomy');
  const pixels = () => page.evaluate(() => document.getElementById('stage').toDataURL().length);
  const closed = await pixels();
  const term = page.locator('.legend [data-organ="heart"]');
  await term.hover();
  assert.equal(await hot(page, 'chest'), true);
  assert.notEqual(await pixels(), closed, 'the peek redraws the chest with the window open');
  assert.equal(await page.locator('#cutaway').isChecked(), false, 'the lesson state is untouched');
  assert.match(await page.locator('#window-readout').innerText(), /Closed/);
  await page.mouse.move(5, 890);
  assert.equal(await pixels(), closed);
});
