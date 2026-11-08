import test from 'node:test';
import assert from 'node:assert/strict';

test('temperature spec probabilities normalize and spread with increasing temperature', () => {
  const probabilities = temperature => {
    const weights = [0.8, 0.15, 0.05].map(p => p ** (1 / temperature));
    return weights.map(w => w / weights.reduce((sum, value) => sum + value, 0));
  };
  const low = probabilities(0.5), high = probabilities(2);
  for (const temperature of [0.5, 1, 2]) {
    const values = probabilities(temperature);
    assert.ok(Math.abs(values.reduce((sum, p) => sum + p, 0) - 1) < 1e-12);
    assert.ok(values.every(p => p > 0 && p < 1));
  }
  assert.ok(Math.abs(low[0] - 0.962406015) < 1e-8);
  assert.ok(Math.abs(high[0] - 0.594172580) < 1e-8);
  assert.ok(high[0] < low[0]);
  assert.ok(high[1] > low[1], 'a lower-scored correct candidate can become more likely');
});

test('idler spec separates direction from speed-ratio magnitude and transfers to a new output', () => {
  const direct = -12 / 24;
  for (const idler of [12, 24, 36]) {
    const intermediate = -12 / idler;
    const output = -intermediate * idler / 24;
    assert.equal(output, 0.5);
    assert.equal(Math.abs(output), Math.abs(direct));
    assert.equal(Math.sign(output), -Math.sign(direct));
    assert.ok(Math.abs(-intermediate * idler / 36 - 1 / 3) < 1e-12);
  }
});
