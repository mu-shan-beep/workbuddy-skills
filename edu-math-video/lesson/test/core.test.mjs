import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import '../engine/core.js';

const SV = globalThis.SV;
SV._katex = createRequire(import.meta.url)('katex');

test('tex: math token gets italic span with subscripts', () => {
  assert.equal(SV.tex('{BC1}'), '<span class="m">BC<sub>1</sub></span>');
  assert.equal(SV.tex('连接 {BC1}，'), '连接 <span class="m">BC<sub>1</sub></span>，');
});

test('tex: $...$ goes through KaTeX, plain text is escaped', () => {
  assert.match(SV.tex('$x^2$'), /class="katex"/);
  assert.match(SV.tex('$x$，求 $y$。'), /^<span class="nb">.*，<\/span>求 <span class="nb">.*。<\/span>$/s);  // punctuation stays with its formula
  assert.doesNotMatch(SV.tex('!!$y=2$!!'), /nb/);  // !!…!! markup is not glued
  assert.equal(SV.tex('a<b'), 'a&lt;b');
});

test('easing and progress', () => {
  const { ease, prog } = SV.u;
  assert.equal(ease(0), 0);
  assert.equal(ease(1), 1);
  assert.equal(prog(0.5, 1, 1), 0);
  assert.equal(prog(1.5, 1, 1), 0.5);
  assert.equal(prog(3, 1, 1), 1);
  assert.equal(prog(5, 1, 1, 4), 0);
});

test('svg label subscripts', () => {
  assert.match(SV.svgLabel('C1'), /^C<tspan[^>]*>1<\/tspan>$/);
  assert.equal(SV.svgLabel('A'), 'A');
});
