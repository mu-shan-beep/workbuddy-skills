const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
let browser;
test.before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true, args: ['--use-angle=swiftshader','--enable-unsafe-swiftshader'] }); });
test.after(async () => { await browser?.close(); });
const url = pathToFileURL(resolve(__dirname, '../examples/price-ceiling.html')).href;
const slide = (page, id, value) => page.locator('#' + id).evaluate((el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }, String(value));
const text = (page, id) => page.locator('#' + id).textContent();
const pick = (page, name, value) => page.locator(`label:has(input[name="${name}"][value="${value}"])`).click();
const millions = s => Number(s.replace(/[$M]/g, ''));
async function predict(page, value = 'more') {
  await page.locator(`input[name="prediction"][value="${value}"]`).check();
  await page.getByRole('button', { name: 'Save my prediction' }).click();
}
async function budgetAddsUp(page) {
  const [cs, ps, dwl, loss, total] = await Promise.all(['r-cs', 'r-ps', 'r-dwl', 'r-loss', 'budget-total'].map(id => text(page, id)));
  assert.ok(Math.abs(millions(cs) + millions(ps) + millions(dwl) + millions(loss) - millions(total.split(' ')[0])) <= 0.03, `${cs} + ${ps} + ${dwl} + ${loss} = ${total}`);
}

test('a binding rent cap shrinks the quantity actually rented to the short side, more so in the long run', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  assert.equal(await page.locator('#price').isDisabled(), true);
  assert.equal(await page.locator('input[name="run"][value="lr"]').isDisabled(), true);
  assert.equal(await page.locator('.cap-line').count(), 0, 'no cap is drawn before the prediction');
  await predict(page, 'more');
  assert.equal(await text(page, 'r-qd'), '15.0k');
  assert.equal(await text(page, 'r-qs'), '9.5k');
  assert.equal(await text(page, 'r-traded'), '9.5k');
  assert.equal(await text(page, 'r-gap'), '5.5k');
  assert.equal(await text(page, 'r-dwl'), '$0.14M');
  await budgetAddsUp(page);
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.match(await text(page, 'status'), /Now switch to the long run/);
  await pick(page, 'run', 'lr');
  assert.equal(await text(page, 'r-traded'), '5.0k');
  assert.equal(await text(page, 'r-gap'), '10.0k');
  assert.equal(await text(page, 'r-dwl'), '$2.50M');
  await budgetAddsUp(page);
  assert.equal(await page.locator('#explanation').isVisible(), true);
  assert.match(await text(page, 'prediction-feedback'), /You predicted more\..*fall from 10\.0k to 9\.5k \(short run\) and 5\.0k \(long run\)/);
  // A cap above the market rent does nothing.
  await slide(page, 'price', 2400);
  assert.equal(await text(page, 'r-traded'), '10.0k');
  assert.equal(await text(page, 'r-gap'), '0.0k');
  assert.equal(await text(page, 'r-dwl'), '$0.00M');
  assert.match(await text(page, 'status'), /doesn’t bind/);
  assert.equal(await page.locator('.cap-line.off').count(), 1);
  // Lower caps: quantity demanded rises while quantity rented falls.
  await slide(page, 'price', 1200);
  assert.equal(await text(page, 'r-qd'), '18.0k');
  assert.equal(await text(page, 'r-traded'), '2.0k');
  await budgetAddsUp(page);
  await page.close();
});

test('rationing by lottery or queue loses more than the deadweight triangle', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  await predict(page, 'fewer');
  await pick(page, 'run', 'lr'); await pick(page, 'run', 'sr'); await pick(page, 'run', 'lr');
  assert.match(await text(page, 'prediction-feedback'), /^You predicted fewer\. Right/);
  assert.equal(await text(page, 'r-loss'), '$0.00M');
  const winners = () => page.locator('#buyers .cell').evaluateAll(cells => cells.map(c => c.dataset.state).join(''));
  const efficient = await winners();
  await pick(page, 'rule', 'lottery');
  assert.equal(await text(page, 'r-loss'), '$2.50M');
  assert.equal(await text(page, 'r-dwl'), '$2.50M');
  await budgetAddsUp(page);
  assert.match(await text(page, 'rule-status'), /2× the highest-value-first loss/);
  const first = await winners();
  assert.notEqual(first, efficient, 'some low-value households win the lottery');
  assert.equal((first.match(/got/g) || []).length, 5);
  await page.locator('#redraw').click();
  const second = await winners();
  assert.notEqual(second, first, 'a new draw picks different winners');
  assert.equal((second.match(/got/g) || []).length, 5);
  assert.equal(await text(page, 'r-loss'), '$2.50M', 'the expected loss does not depend on the draw');
  await pick(page, 'rule', 'queue');
  assert.equal(await text(page, 'r-loss'), '$5.00M');
  assert.equal(await text(page, 'r-cs'), '$1.25M');
  assert.match(await text(page, 'rule-status'), /more than the \$2\.50M transfer/);
  await budgetAddsUp(page);
  await page.close();
});

test('independent practice hides the chart and names the misconception behind wrong answers', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  await predict(page); await pick(page, 'run', 'lr');
  assert.equal(await page.locator('#prob-1').isVisible(), false);
  await page.getByRole('button', { name: 'Start practice (hide the chart)' }).click();
  assert.equal(await text(page, 'r-traded'), '?');
  assert.equal(await text(page, 'r-dwl'), '?');
  assert.equal(await page.locator('#price').isDisabled(), true);
  assert.equal(await page.locator('input[name="rule"][value="lottery"]').isDisabled(), true);
  assert.equal(await page.locator('#chart .curve').count(), 0, 'curves are hidden');
  assert.match(await page.locator('#chart').textContent(), /Practice: chart hidden/);
  assert.equal(await page.locator('#prob-2').isVisible(), false);
  await page.locator('#p1').fill('2'); await page.locator('#prob-1 button').click();
  assert.match(await text(page, 'p1-fb'), /^Not quite\. You measured only how far supply fell/);
  await page.locator('#p1').fill('7'); await page.locator('#prob-1 button').click();
  assert.match(await text(page, 'p1-fb'), /quantity demanded/);
  await page.locator('#p1').fill('3'); await page.locator('#prob-1 button').click();
  assert.match(await text(page, 'p1-fb'), /^Correct: 3/);
  await page.locator('#p2').fill('9'); await page.locator('#prob-2 button').click();
  assert.match(await text(page, 'p2-fb'), /used the shortage \(3\) as the base/);
  await page.locator('#p2').fill('8'); await page.locator('#prob-2 button').click();
  assert.match(await text(page, 'p2-fb'), /transfer rectangle/);
  await page.locator('#p2').fill('6'); await page.locator('#prob-2 button').click();
  assert.match(await text(page, 'p2-fb'), /^Correct: 6/);
  await page.locator('input[name="p3"][value="same"]').check(); await page.locator('#prob-3 button').click();
  assert.match(await text(page, 'p3-fb'), /^Not quite\. The quantity sold is the same, but who gets it changes/);
  await page.locator('input[name="p3"][value="larger"]').check(); await page.locator('#prob-3 button').click();
  assert.match(await text(page, 'p3-fb'), /^Correct: larger/);
  // Restore the chart for the practice market to check the answers.
  await page.getByRole('button', { name: 'Draw this market to check' }).click();
  assert.equal(await text(page, 'r-gap'), '3.0k bags');
  assert.equal(await text(page, 'r-dwl'), '$6.0k');
  await pick(page, 'rule', 'lottery');
  assert.equal(await text(page, 'r-loss'), '$12.0k');
  assert.equal(await page.locator('#price').isDisabled(), true, 'the practice market keeps its own cap');
  await page.getByRole('button', { name: 'Back to the rent market' }).click();
  assert.equal(await page.locator('#price').isDisabled(), false);
  assert.match(await text(page, 'r-traded'), /k$/);
  await page.close();
});

test('the price-floor transfer, then the floor mode confirms a surplus; reset restores the start', async () => {
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  await predict(page); await pick(page, 'run', 'lr'); await pick(page, 'run', 'sr');
  assert.equal(await page.locator('#floor').isVisible(), false);
  await page.locator('input[name="transfer"][value="shortage"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Not quite\. A higher price makes farmers want to sell more/);
  await page.locator('input[name="transfer"][value="surplus"]').check();
  await page.getByRole('button', { name: 'Check my answer' }).click();
  assert.match(await text(page, 'transfer-feedback'), /^Right\./);
  await page.locator('#floor').check();
  assert.equal(await text(page, 'r-gap-k'), 'Unsold surplus');
  assert.equal(await text(page, 'r-qs'), '10.5k');
  assert.equal(await text(page, 'r-traded'), '5.0k');
  assert.equal(await text(page, 'r-gap'), '5.5k');
  assert.equal(await page.locator('input[name="rule"][value="queue"]').isDisabled(), true);
  await budgetAddsUp(page);
  await page.getByRole('button', { name: 'Reset lesson' }).click();
  assert.equal(await page.locator('#explanation').isVisible(), false);
  assert.equal(await page.locator('#price').isDisabled(), true);
  assert.equal(await page.locator('input[name="prediction"][value="more"]').isDisabled(), false);
  assert.equal(await page.locator('#floor').isChecked(), false);
  assert.equal(await text(page, 'r-gap-k'), 'Shortage');
  await page.close();
});

test('dragging the cap line on the chart moves the cap', async () => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' }); await page.goto(url);
  await predict(page);
  const box = await page.locator('#chart .cap-hit').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 60, { steps: 6 });
  await page.mouse.up();
  const price = Number(await page.locator('#price').inputValue());
  assert.ok(price > 1500 && price % 50 === 0, `cap moved up to ${price}`);
  assert.equal(await text(page, 'price-out'), '$' + price.toLocaleString('en-US'));
  await page.close();
});

test('price ceiling works offline, in Chinese, and keeps readouts in view on short screens', async () => {
  const requests = [], errors = [];
  for (const colorScheme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width: 360, height: 800 }, colorScheme, reducedMotion: 'reduce' });
    page.on('request', r => { if (!r.url().startsWith('file:')) requests.push(r.url()); });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(url); await predict(page);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `no horizontal overflow at 360 ${colorScheme}`);
    await page.close();
  }
  for (const [width, height] of [[1280, 720], [1366, 768], [1024, 600], [768, 1024], [1440, 900]]) {
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(url); await predict(page); await page.waitForTimeout(150);
    const where = `${width}×${height}`;
    const layout = await page.evaluate(() => {
      const pane = document.querySelector('.lesson > .figure-pane'), readouts = pane.querySelector('.readouts').getBoundingClientRect();
      return { twoPane: matchMedia('(min-width:960px) and (min-height:560px)').matches, horizontal: document.documentElement.scrollWidth - innerWidth,
        readouts: { top: readouts.top, bottom: readouts.bottom, height: readouts.height }, bar: document.querySelector('.bar').getBoundingClientRect().bottom,
        overflow: pane.scrollHeight - pane.clientHeight, cue: !document.querySelector('.pane-more')?.hidden,
        chart: document.getElementById('chart').getBoundingClientRect().height };
    });
    assert.ok(layout.horizontal <= 0, `${where}: no horizontal overflow`);
    assert.ok(layout.readouts.height >= 40, `${where}: readouts are not squashed`);
    assert.ok(layout.chart >= 250, `${where}: the chart keeps a usable height`);
    if (layout.twoPane) {
      assert.ok(layout.readouts.top >= layout.bar && layout.readouts.bottom <= height, `${where}: readouts stay inside the viewport`);
      assert.equal(layout.cue, layout.overflow > 1, `${where}: the more-below cue shows exactly when the pane overflows`);
    }
    await page.close();
  }
  const page = await browser.newPage({ reducedMotion: 'reduce' }); await page.goto(url);
  page.on('pageerror', e => errors.push(e.message));
  await predict(page);
  await page.locator('[data-set-lang="zh"]').click();
  assert.equal(await text(page, 'r-traded'), '9.5 千套');
  assert.match(await text(page, 'status'), /短期：\$1,500 时/);
  assert.match(await page.title(), /限租令/);
  await page.close();
  assert.deepEqual(requests, []);
  assert.deepEqual(errors, []);
});
