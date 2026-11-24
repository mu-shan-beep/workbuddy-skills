import test from 'node:test';
import assert from 'node:assert/strict';
import '../engine/core.js';
import '../engine/figure.js';

const { figure, u } = globalThis.SV;

const prism = {
  type: 'solid3d',
  points: { A: [2, 0, 0], B: [0, 2, 0], C: [0, 0, 0], A1: [2, 0, 2], B1: [0, 2, 2], C1: [0, 0, 2] },
  faces: [['A', 'B', 'C'], ['A1', 'B1', 'C1'], ['A', 'B', 'B1', 'A1'], ['B', 'C', 'C1', 'B1'], ['A', 'C', 'C1', 'A1']],
  extra: [{ name: 'D', mid: ['A', 'B'] }, { name: 'E', mid: ['A', 'C1'] }],
};

test('solid3d: edges derived from faces', () => {
  const f = figure.create(prism, []);
  assert.equal(f.edges.length, 9);
});

test('solid3d: hidden lines from the textbook view', () => {
  const f = figure.create(prism, []);
  const { view } = figure.camBasis(225, 24);
  assert.equal(f.isHidden('A', 'B', view), false, 'front edge visible');
  assert.equal(f.isHidden('C', 'C1', view), true, 'back edge hidden');
  assert.equal(f.isHidden('D', 'E', view), true, 'interior segment hidden');
  assert.equal(f.isHidden('A1', 'B1', view), false, 'top edge visible');
});

test('solid3d: bestView turns the target face toward the camera', () => {
  const f = figure.create(prism, []);
  const v = f.bestView(['B', 'C', 'C1', 'B1'], f.home);
  const { view } = figure.camBasis(v.az, v.el);
  const face = f.faces.find((x) => x.names.includes('C') && x.names.includes('B1'));
  assert.ok(-u.v3.dot(face.n, view) > 0.35, `face should be front-facing, view=${JSON.stringify(v)}`);
});

test('solid3d: camera keyframes interpolate and settle', () => {
  const f = figure.create(prism, [{ kind: 'cam', az: 315, el: 20, at: 2, dur: 1 }]);
  assert.deepEqual(f.camera(0), { az: 225, el: 24 });
  assert.deepEqual(f.camera(5), { az: 315, el: 20 });
  const mid = f.camera(2.5);
  assert.ok(mid.az > 225 && mid.az < 315);
});

test('render: fit keeps every point inside the box; svg contains drawn ops', () => {
  const f = figure.create(prism, []);
  f.fit(500, 500, 10);
  const pr = f.proj(0);
  for (const p of Object.values(f.P)) {
    const [x, y] = pr(p);
    assert.ok(x >= 0 && x <= 500 && y >= 0 && y <= 500, `point out of box: ${x},${y}`);
  }
  const theme = { roles: { edge: { c: '#fff', w: 2 }, given: { c: '#fff', w: 2 }, key: { c: '#ff0', w: 4 } }, hid: { dash: '8 8' }, hidAcc: {}, labelSize: 24, labelColor: '#fff', dot: '#ff0' };
  const ops = [...f.intro(0), { op: 'seg', a: 'D', b: 'E', role: 'key', at: 1, dur: 0.5 }];
  const { svg } = f.render(10, ops, theme);
  assert.match(svg, /stroke="#ff0"/);
  assert.match(svg, /stroke-dasharray="8 8"/);
});

test('graph: compileFn handles ^ and Math names', () => {
  const f = figure.compileFn('x^2-2*x+3');
  assert.equal(f(1), 2);
  assert.equal(figure.compileFn('sqrt(x)')(9), 3);
});
