const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/information-entropy.html')).href;
const pick = (page, name, value) => page.locator(`label:has(input[name="${name}"][value="${value}"])`).click();
const readouts = async page => Promise.all(['#r-entropy', '#r-average', '#r-gap'].map(id => page.locator(id).textContent()));

test('entropy lesson: question trees approach but never beat the entropy floor', async () => {
  const page = await browser.newPage();
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
  await page.goto(url);
  assert.equal(await page.locator('input[name="climate"][value="desert"]').isDisabled(), true, 'controls wait for a prediction');
  assert.equal(await page.locator('#send').isDisabled(), true);
  assert.deepEqual(await readouts(page), ['3.00', '3.00', '0.00']);

  await page.locator('input[name="prediction"][value="one"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();

  await pick(page, 'strategy', 'one');
  assert.deepEqual(await readouts(page), ['3.00', '4.38', '+1.38'], 'one at a time is worse than halving when outcomes are equally likely');

  await pick(page, 'climate', 'seaside');
  await pick(page, 'strategy', 'halving');
  assert.deepEqual(await readouts(page), ['1.98', '3.00', '+1.02'], 'halving ignores probabilities');
  await pick(page, 'strategy', 'huffman');
  assert.deepEqual(await readouts(page), ['1.98', '1.98', '0.00'], 'Huffman meets H when every probability is a power of one half');

  await pick(page, 'climate', 'desert');
  assert.equal(await page.locator('#sunny').inputValue(), '90');
  assert.deepEqual(await readouts(page), ['0.75', '1.29', '+0.54'], 'one report at a time cannot go below one question');
  assert.equal(await page.locator('#explanation').isHidden(), true);

  await page.locator('#send').click();
  const firstRun = await page.locator('#r-sample').textContent();
  assert.match(firstRun, /^\d+$/);
  assert.equal(await page.locator('#tape li').count(), 24);

  await pick(page, 'block', '2');
  assert.deepEqual(await readouts(page), ['0.75', '0.90', '+0.15'], 'bundling two reports breaks the one-question floor');
  assert.equal(await page.locator('#tape li').count(), 12, 'the same 24 reports are re-encoded in pairs');
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.equal(await page.locator('input[name="strategy"][value="build"]').isDisabled(), true);
  await pick(page, 'block', '3');
  assert.deepEqual(await readouts(page), ['0.75', '0.81', '+0.06']);

  await page.locator('input[name="transfer"][value="barely"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await page.locator('#transfer-feedback').textContent(), /^Correct/);

  await page.locator('#reset').click();
  assert.deepEqual(await readouts(page), ['3.00', '3.00', '0.00']);
  assert.equal(await page.locator('#explanation').isHidden(), true);
  assert.equal(await page.locator('#r-sample').textContent(), '—');
  await page.locator('input[name="prediction"][value="below"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await pick(page, 'climate', 'desert');
  await pick(page, 'strategy', 'huffman');
  await page.locator('#send').click();
  assert.equal(await page.locator('#r-sample').textContent(), firstRun, 'the seeded simulation replays after reset');
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, []);
  await page.close();
});

test('entropy lesson: a hand-built tree is scored by the same model', async () => {
  const page = await browser.newPage();
  await page.goto(url);
  await page.locator('input[name="prediction"][value="three"]').check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
  await pick(page, 'climate', 'seaside');
  await pick(page, 'strategy', 'build');
  assert.equal(await page.locator('#r-average').textContent(), '—', 'an unfinished tree has no average');
  const join = async (a, b) => {
    await page.locator(`#chips button[data-leaves="${a}"]`).click();
    await page.locator(`#chips button[data-leaves="${b}"]`).click();
  };
  // Always join the two least likely groups: Huffman's rule.
  await join('6', '7'); await join('5', '6,7'); await join('4', '5,6,7'); await join('3', '4,5,6,7');
  await join('2', '3,4,5,6,7'); await join('1', '2,3,4,5,6,7');
  await page.getByRole('button', { name: 'Undo' }).click();
  await join('1', '2,3,4,5,6,7'); await join('0', '1,2,3,4,5,6,7');
  assert.deepEqual(await readouts(page), ['1.98', '1.98', '0.00']);
  await page.getByRole('button', { name: 'Start over' }).click();
  // Pairing neighbours builds the halving tree, which ignores probability.
  await join('0', '1'); await join('2', '3'); await join('4', '5'); await join('6', '7');
  await join('0,1', '2,3'); await join('4,5', '6,7'); await join('0,1,2,3', '4,5,6,7');
  assert.deepEqual(await readouts(page), ['1.98', '3.00', '+1.02']);
  await page.locator('[data-set-lang="zh"]').click();
  assert.match(await page.locator('#summary').textContent(), /自己搭的树/);
  await page.close();
});
