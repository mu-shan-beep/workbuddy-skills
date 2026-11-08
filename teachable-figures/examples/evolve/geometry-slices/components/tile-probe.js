// Tile probe: a counting question whose answer key comes from the truth model, not from the markup.
const key = (lesson.derive(6).radius / lesson.derive(2).radius) ** 2;
const chosen = () => document.querySelector('input[name="tile-probe"]:checked')?.value ?? null;
document.getElementById('tile-probe-check').addEventListener('click', () => {
  const v = chosen(), correct = v !== null && Number(v) === key;
  evolve.log('probe', { id: 'tile-probe', value: v, correct });
  say('tile-probe-feedback', () => v === null ? tr('先选一个答案。', 'Choose an answer first.')
    : correct ? tr('对。3 行乘 3 列是 9 块：长度乘 3，面积乘 3 × 3。把滑块拖到 h = 6 看看，再回去改一改你的解释。', 'Yes. Three rows of three is 9 tiles: lengths ×3, area ×3 × 3. Drag the slider to h = 6 to see it, then revise your explanation.')
    : tr('把滑块拖到 h = 6，数一数左边方块的行数和列数。', 'Drag the slider to h = 6 and count the rows and the columns of tiles on the left.'));
});
evolve.register('tile-probe', { read: () => ({ key, choices: [...document.querySelectorAll('input[name="tile-probe"]')].map(el => Number(el.value)) }), answers: () => ({ 'tile-probe': chosen() }) });
