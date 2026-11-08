// Area tiles: counts the slice area in r0 × r0 tiles, where r0 is the radius at h = 2. Reads only lesson.derive.
const R0 = lesson.derive(2).radius, U = 26, BASE = 108, X0 = 64;
let last = { k: 1, areaMultiple: 1, fullTiles: 1 };
const fmt = n => n.toFixed(2);
function render(s) {
  if (!s) return;
  const k = lesson.derive(s.h).radius / R0;
  const areaMultiple = k * k;
  const fullTiles = Math.floor(k + 1e-9) ** 2;
  const side = k * U, n = Math.ceil(k - 1e-9);
  let g = `<rect class="tile" x="8" y="${BASE - U}" width="${U}" height="${U}"/>`
    + `<path class="disc" d="M8 ${BASE} L8 ${BASE - U} A${U} ${U} 0 0 1 ${8 + U} ${BASE} Z"/>`
    + `<text x="8" y="${BASE + 11}">h = 2</text><text x="${8 + U / 2 - 5}" y="${BASE - U - 4}">r₀</text>`;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const w = Math.min(1, k - i), hh = Math.min(1, k - j), full = w > 1 - 1e-9 && hh > 1 - 1e-9;
    g += `<rect class="tile${full ? ' full' : ' part'}" x="${X0 + i * U}" y="${BASE - (j + hh) * U}" width="${w * U}" height="${hh * U}"/>`;
  }
  if (k > 0) g += `<path class="disc" d="M${X0} ${BASE} L${X0} ${BASE - side} A${side} ${side} 0 0 1 ${X0 + side} ${BASE} Z"/>`
    + `<rect class="edge" x="${X0}" y="${BASE - side}" width="${side}" height="${side}"/>`;
  g += `<text x="${X0}" y="${BASE + 11}">h = ${s.h.toFixed(1)}</text>`;
  document.getElementById('tiles-draw').innerHTML = g;
  document.getElementById('tiles-k').textContent = '×' + fmt(k);
  document.getElementById('tiles-sq').textContent = `${fmt(k)} × ${fmt(k)}`;
  document.getElementById('tiles-mult').textContent = '×' + fmt(areaMultiple);
  document.getElementById('tiles-desc').textContent = tr(
    `参考方块是 h = 2 时的 1 块。h = ${s.h.toFixed(1)} 时半径是 ${fmt(k)} 倍，r × r 方块含 ${fmt(areaMultiple)} 块，其中完整的有 ${fullTiles} 块。`,
    `The reference square is 1 tile at h = 2. At h = ${s.h.toFixed(1)} the radius is ${fmt(k)} times as long, and the r × r square holds ${fmt(areaMultiple)} tiles, ${fullTiles} of them whole.`);
  last = { k, areaMultiple, fullTiles };
}
evolve.register('area-tiles', { render, read: () => ({ ...last, shown: document.getElementById('tiles-mult').textContent }) });
