const test = require('node:test');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { resolve } = require('node:path');
const { mkdirSync } = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

let browser;
const errors = [];
const pageUrl = name => pathToFileURL(resolve(__dirname, `../assets/iso-figure/examples/${name}.html`)).href;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true }); });
test.after(async () => { await browser?.close(); });

for (const name of ['pocket-calculator', 'desk-synth']) {
  test(`${name} leaves writing fields alone and exposes native controls`, async () => {
    const page = await browser.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pageUrl(name));
    await page.evaluate(() => {
      const input = document.createElement('input');
      input.id = 'writing';
      input.setAttribute('aria-label', 'Explain what happened');
      document.querySelector('main').append(input);
    });
    await page.locator('#writing').pressSequentially(name === 'desk-synth' ? 'asdx123' : '123+4');
    assert.equal(await page.locator('#writing').inputValue(), name === 'desk-synth' ? 'asdx123' : '123+4');
    assert.ok(await page.getByRole('button').count() >= 10);
    assert.equal(await page.locator('#readout').getAttribute('aria-live'), 'polite');
    await page.close();
  });
}

test('calculator pointer, focused shortcuts, error recovery, and reset use the same model', async () => {
  const page = await browser.newPage();
  await page.goto(pageUrl('pocket-calculator'));
  await page.getByRole('button', { name: '4', exact: true }).click();
  await page.getByRole('button', { name: '+', exact: true }).click();
  await page.getByRole('button', { name: '5', exact: true }).click();
  await page.getByRole('button', { name: '=', exact: true }).click();
  assert.equal(await page.locator('#lcd').textContent(), '9');
  await page.locator('#stage').focus();
  await page.keyboard.press('Escape');
  for (const key of ['8', '/', '0', 'Enter']) await page.keyboard.press(key);
  assert.equal(await page.locator('#lcd').textContent(), 'Error');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#lcd').textContent(), '0');
  assert.equal(await page.locator('#readout').textContent(), 'ready');
  await page.close();
});

test('synth releases held keys on focus loss, resets, and supports mute', async () => {
  const page = await browser.newPage();
  await page.goto(pageUrl('desk-synth'));
  await page.locator('#stage').focus();
  await page.keyboard.down('a');
  assert.match(await page.locator('#readout').textContent(), /C4/);
  await page.getByRole('button', { name: 'Mute', exact: true }).click();
  await page.keyboard.up('a');
  assert.match(await page.locator('#readout').textContent(), /silent/);
  assert.equal(await page.getByRole('button', { name: 'Unmute', exact: true }).getAttribute('aria-pressed'), 'true');
  await page.getByLabel('Octave', { exact: true }).fill('6');
  await page.getByLabel('Octave', { exact: true }).dispatchEvent('change');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  assert.equal(await page.getByLabel('Octave', { exact: true }).inputValue(), '4');
  assert.match(await page.locator('#readout').textContent(), /saw · oct 4 · silent/);
  await page.close();
});

test('synth keeps a keyboard note held after a pointer on the same key releases', async () => {
  const page = await browser.newPage();
  await page.goto(pageUrl('desk-synth'));
  const face = page.locator('.key[data-semi="0"] .face.top');
  await face.hover();
  await page.mouse.down();
  await page.keyboard.down('a');
  await page.mouse.up();
  assert.match(await page.locator('#readout').textContent(), /C4/);
  await page.keyboard.up('a');
  assert.match(await page.locator('#readout').textContent(), /silent/);
  await page.getByRole('button', { name: 'C', exact: true }).click();
  assert.match(await page.locator('#readout').textContent(), /C4/);
  await page.waitForFunction(() => document.getElementById('readout').textContent.includes('silent'));
  await page.close();
});

test('desktop and mobile pages fit both themes and reduced motion keeps a stable scope', async () => {
  mkdirSync(resolve(__dirname, '../test-results'), { recursive: true });
  for (const name of ['pocket-calculator', 'desk-synth']) {
    for (const width of [360, 1000]) {
      for (const colorScheme of ['light', 'dark']) {
        const page = await browser.newPage({ viewport: { width, height: 900 }, colorScheme, reducedMotion: 'reduce', hasTouch: width === 360 });
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(pageUrl(name));
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        for (const box of await page.getByRole('button').evaluateAll(buttons => buttons.map(b => ({ width: b.getBoundingClientRect().width, height: b.getBoundingClientRect().height })))) {
          assert.ok(box.width >= 24 && box.height >= 24, 'native target must be at least 24px');
        }
        if (name === 'desk-synth') {
          await page.locator('#stage').focus();
          await page.keyboard.down('a');
          const initial = await page.locator('#scope').getAttribute('points');
          await page.waitForTimeout(100);
          assert.equal(await page.locator('#scope').getAttribute('points'), initial);
          await page.keyboard.up('a');
        }
        await page.screenshot({ path: resolve(__dirname, `../test-results/${name}-${width}-${colorScheme}.png`), fullPage: true });
        await page.close();
      }
    }
  }
  assert.deepEqual(errors, []);
});

test('gear lesson tests a misconception, compares both arrangements, transfers, and resets', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  await page.goto(pathToFileURL(resolve(__dirname, '../examples/gear-ratio.html')).href);
  assert.equal(await page.locator('#run').isDisabled(), true);
  await page.locator('input[name="prediction"][value="slower"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await page.locator('#run').click();
  assert.equal(await page.locator('#direct-result').textContent(), '0.50 turn');
  assert.equal(await page.locator('#direct-direction').textContent(), 'Counterclockwise');
  await page.locator('#idler').check();
  await page.locator('#run').click();
  assert.equal(await page.locator('#idler-result').textContent(), '0.50 turn');
  assert.equal(await page.locator('#idler-direction').textContent(), 'Clockwise');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  await page.locator('#explain-answer').fill('The idler reverses direction twice. Its tooth count cancels.');
  await page.locator('input[name="transfer"][value="same"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await page.locator('#transfer-feedback').textContent(), /^Yes\./);
  await page.locator('#reset').click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#run').isDisabled(), true);
  assert.equal(await page.locator('#explain-answer').inputValue(), '');
  assert.equal(await page.locator('#driver-count').textContent(), '0.00');
  await page.close();
});

test('gear lesson supports quarter-turn keyboard input, both themes, and mobile layout', async () => {
  for (const width of [360, 900]) {
    for (const colorScheme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, colorScheme, reducedMotion: 'reduce' });
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(error.message));
      await page.goto(pathToFileURL(resolve(__dirname, '../examples/gear-ratio.html')).href);
      await page.locator('input[name="prediction"][value="same"]').check();
      await page.getByRole('button', { name: 'Save my prediction' }).click();
      await page.locator('#turn').focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(await page.locator('#driver-count').textContent(), '0.25');
      assert.equal(await page.locator('#output-count').textContent(), '0.13');
      await page.keyboard.press('End');
      await page.locator('#idler').check();
      await page.locator('#run').click();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: resolve(__dirname, `../test-results/gear-${width}-${colorScheme}.png`), fullPage: true });
      assert.deepEqual(pageErrors, []);
      await page.close();
    }
  }
});
