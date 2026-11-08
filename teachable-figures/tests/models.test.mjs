import test from 'node:test';
import assert from 'node:assert/strict';
import { waveOf, omegaOf, wavenumberOf, nodalCount, stateOf, readoutOf, wordsOf } from '../assets/anatomy/examples/ripple-tank/model.mjs';

test('ripple dispersion solver agrees with the stated equation at control bounds', () => {
  for (const frequency of [8, 18, 28]) {
    assert.ok(Math.abs(omegaOf(wavenumberOf(frequency)) - 2 * Math.PI * frequency) < 1e-9);
    const wave = waveOf(frequency);
    for (const value of Object.values(wave)) assert.ok(Number.isFinite(value) && value > 0);
  }
  assert.ok(waveOf(8).lambda > waveOf(28).lambda);
});

test('spacing changes interference count without changing wavelength', () => {
  const optics = { caustic: 20, magnification: 2 };
  const near = stateOf(18, 20, optics);
  const far = stateOf(18, 80, optics);
  assert.equal(near.lambdaMm, far.lambdaMm);
  assert.ok(far.nodal > near.nodal);
  assert.equal(far.nodal, nodalCount(80, far.lambdaMm));
  assert.ok(readoutOf(far).includes(`${far.nodal} nodal lines`));
  assert.ok(wordsOf(far).includes(`${far.nodal} nodal lines`));
  assert.equal(far.projected, far.lambdaMm * optics.magnification);
});
