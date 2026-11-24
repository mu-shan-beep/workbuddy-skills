import test from 'node:test';
import assert from 'node:assert/strict';
import { toSpeak } from '../scripts/speak.mjs';

test('letters are spelled, symbols read as words', () => {
  assert.equal(toSpeak('DE∥平面BCC₁B₁'), 'D E 平行于平面 B C C 1 B 1');
  assert.equal(toSpeak('连接 {BC1}，'), '连接 B C 1，');
  assert.equal(toSpeak('∠DEF=45°'), '角 D E F 等于45度');
});

test('pronunciation markup: kept for TTS, stripped from captions', async () => {
  const { captionText } = await import('../scripts/compile.mjs');
  assert.equal(captionText('所以当[dāng] {x} 等于 1 时'), '所以当 x 等于 1 时');
  assert.equal(toSpeak('长[cháng]度'), '长[cháng]度');
});

test('markup and raw latex are dropped', () => {
  assert.equal(toSpeak('**结论**成立'), '结论成立');
  assert.equal(toSpeak('由 $x^2$ 可知'), '由 可知');
});
