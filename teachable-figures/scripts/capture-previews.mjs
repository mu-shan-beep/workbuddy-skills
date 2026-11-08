import { mkdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

// Screenshots each lesson's figure pane for the example directory cards, in both languages and color schemes.
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright');
const examples = fileURLToPath(new URL('../examples/', import.meta.url));
const out = fileURLToPath(new URL('../examples/previews/', import.meta.url));
// Crop to the figure where it stands alone; keep the whole pane where readouts are the picture.
// Where the reset state hides the mechanism, a setup step reveals it before the capture.
const stages = {
  'how-it-works': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="spec"]').check();
    await page.locator('#prediction-form button[type="submit"]').click();
    await page.locator('input[name="request"][value="chest"]').check();
    await page.locator('#skip-renderer').check();
  } },
  'geometry-slices': { selector: '#experiment .stage' },
  'human-anatomy': { selector: '#experiment .stage', setup: page => page.locator('#cutaway').check() },
  'rocket-launch': { selector: '#experiment' },
  'transformer-flow': { selector: '#experiment', setup: page => page.locator('[data-stage="3"]').click() },
  'chinese-clothing': { selector: '#experiment .stage' },
  'gear-ratio': { selector: '#experiment .stage' },
  'ship-of-theseus': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="B"]').check();
    await page.locator('#prediction-form button').click();
    await page.locator('#collector').check();
    await page.locator('#year').fill('12');
    await page.locator('input[name="drift"][value="less"]').check();
    await page.locator('#drift-form button').click();
    await page.locator('#error').fill('5');
    await page.locator('#year').fill('36');
  } },
  'information-entropy': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="one"]').check();
    await page.locator('#prediction-form button').click();
    await page.locator('label:has(input[name="climate"][value="desert"])').click();
    await page.locator('label:has(input[name="strategy"][value="huffman"])').click();
    await page.locator('#send').click();
  } },
  'bayes-base-rate': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="90"]').check();
    await page.locator('#prediction-form button').click();
    await page.locator('#positives-only').check();
  } },
  'seasons': { selector: '#experiment .stage', setup: async page => {
    await page.locator('input[name="prediction"][value="tilt"]').check();
    await page.locator('#prediction-form button').click();
    await page.locator('#dates button[data-day="172"]').click();
  } },
  'moon-phases': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="half"]').check();
    await page.locator('#prediction-form button[type=submit]').click();
    await page.locator('#phases button[data-e="40"]').click();
  } },
  'four-stroke-engine': { selector: '#experiment .stage', setup: async page => {
    await page.locator('input[name="turns"][value="2"]').check();
    await page.locator('input[name="next"][value="compression"]').check();
    await page.locator('#prediction-form').evaluate(f => f.requestSubmit());
    await page.locator('#angle').evaluate(el => { el.value = 400; el.dispatchEvent(new Event('input', { bubbles: true })); });
  } },
  'dynamic-equilibrium': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="both"]').check();
    await page.locator('#prediction-form button').click();
    for (let i = 0; i < 4; i++) await page.locator('#skip').click();
    await page.locator('#tag').check();
    await page.locator('#skip').click();
  } },
  'natural-selection': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="select"]').check();
    await page.locator('#prediction-form button').click();
    for (let i = 0; i < 3; i++) await page.locator('#run10').click();
    await page.locator('#bark').evaluate(el => { el.value = 10; el.dispatchEvent(new Event('input', { bubbles: true })); });
    for (let i = 0; i < 4; i++) await page.locator('#run10').click();
  } },
  'price-ceiling': { selector: '#experiment', setup: async page => {
    await page.locator('input[name="prediction"][value="fewer"]').check();
    await page.locator('#prediction-form button').click();
    await page.locator('label:has(input[name="run"][value="lr"])').click();
    await page.locator('label:has(input[name="rule"][value="lottery"])').click();
  } },
};
// Pass lesson names to recapture only those, e.g. `node scripts/capture-previews.mjs gear-ratio`.
const only = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
try {
  for (const [name, { selector, setup }] of Object.entries(stages)) {
    if (only.length && !only.includes(name)) continue;
    for (const lang of ['zh', 'en']) {
      for (const colorScheme of ['light', 'dark']) {
        const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme, reducedMotion: 'reduce' });
        // Card thumbnails show the whole figure: no step dimming, focus bar or overflow cue.
        await page.addInitScript(() => { try { localStorage.setItem('tf-focus-guide', 'off'); } catch {} });
        await page.goto(`${pathToFileURL(`${examples}${name}.html`).href}?lang=${lang}`);
        await page.addStyleTag({ content: '.focus-bar,.pane-more{display:none!important}' });
        await setup?.(page);
        await page.waitForTimeout(600);
        await page.locator(selector).first().screenshot({ path: `${out}${name}-${lang}-${colorScheme}.jpg`, type: 'jpeg', quality: 80 });
        await page.close();
        console.log(`${name}-${lang}-${colorScheme}.jpg`);
      }
    }
  }
} finally {
  await browser.close();
}
