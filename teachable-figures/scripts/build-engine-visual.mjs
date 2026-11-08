import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as k from '../assets/anatomy/kit/iso-kit.mjs';
import * as G from '../assets/anatomy/kit/lathe.mjs';

// Anatomy turns the piston, valves, spark plug, crank web and camshafts; the cut faces are flat sections in the y = 0 plane.
// Dimensions are original and describe no real engine. 1 unit = 3 mm: bore 84 mm, stroke 72 mm, compression ratio 10.
const target = fileURLToPath(new URL('../examples/four-stroke-engine.html', import.meta.url));
const P = { origin: [228, 455], scale: 3.05, azimuth: 70, elevation: 14 };
const CRANK = 12, ROD = 40, PIN_UP = 6, CROWN = 10, BORE = 14;
const TDC_PIN = CRANK + ROD, TDC_TOP = TDC_PIN + CROWN;
const DECK = TDC_TOP + 2 * CRANK / 9; // clearance height that gives a compression ratio of 10
const TILT = 20 * Math.PI / 180, SEAT_X = 7, STEM = 26, CAM_BASE = 4.5, LIFT = 3.5;
const axisOf = side => [side * Math.sin(TILT), 0, Math.cos(TILT)];
const seatOf = side => [side * SEAT_X, 0, DECK + .6];
const camOf = side => { const a = axisOf(side), s = seatOf(side), d = STEM + .4 + CAM_BASE; return [s[0] + a[0] * d, 0, s[2] + a[2] * d]; };
const r2 = v => Math.round(v * 100) / 100;
const at = ([x, z], y = 0) => k.iso([x, y, z], P);
const poly = (points, y = 0) => k.pathOf(points.map(p => at(p, y)), true);
const arc = (cx, cz, r, a0, a1, n = 24) => Array.from({ length: n + 1 }, (_, i) => { const a = a0 + (a1 - a0) * i / n; return [cx + r * Math.cos(a), cz + r * Math.sin(a)]; });
const solid = (profile, F, options = {}) => k.solidSvg(G.solidOf(profile, F, P, { steps: 64, ...options }), { tone: 'mid' });

// Cut faces of the block (crankcase + cylinder) and the head, with the cavities behind them.
const lip = Math.sqrt(22 * 22 - BORE * BORE);
const cavityCrank = [[BORE, DECK], [BORE, lip], ...arc(0, 0, 22, Math.atan2(lip, BORE), Math.atan2(lip, -BORE) - 2 * Math.PI, 40), [-BORE, lip], [-BORE, DECK]];
const blockOuter = [[-26, -30], [26, -30], [31, -25], [31, 12], [20, 24], [20, DECK], [-20, DECK], [-20, 24], [-31, 12], [-31, -25]];
const headOuter = [[-23, DECK], [23, DECK], [23, DECK + 13], [19, DECK + 17], [-19, DECK + 17], [-23, DECK + 13]];
const port = side => [[side * 1.6, DECK], [side * 3.8, DECK + 5], [side * 10, DECK + 11.2], [side * 23, DECK + 11.6], [side * 23, DECK + 5], [side * 15, DECK + 4.4], [side * 12.4, DECK]].map(([x, z]) => [x, z]);
const plugHole = [[-2.3, DECK], [2.3, DECK], [2.3, DECK + 17], [-2.3, DECK + 17]];
const guide = side => { const a = axisOf(side), s = seatOf(side), n = [a[2], -a[0]]; const p0 = [s[0] + a[0] * 7, s[2] + a[2] * 7], p1 = [s[0] + a[0] * 19, s[2] + a[2] * 19]; return [[p0[0] + n[0] * 1.3, p0[1] + n[1] * 1.3], [p1[0] + n[0] * 1.3, p1[1] + n[1] * 1.3], [p1[0] - n[0] * 1.3, p1[1] - n[1] * 1.3], [p0[0] - n[0] * 1.3, p0[1] - n[1] * 1.3]]; };

const cavity = `<path class="cavity" d="${poly(cavityCrank)}"/><path class="cavity deep" d="${poly(port(-1))}"/><path class="cavity deep" d="${poly(port(1))}"/>`;
const blockCut = `<path class="cut" fill-rule="evenodd" d="${poly(blockOuter)}${poly(cavityCrank)}"/>`;
const headCut = `<path class="cut" fill-rule="evenodd" d="${poly(headOuter)}${poly(port(-1))}${poly(port(1))}${poly(plugHole)}${poly(guide(-1))}${poly(guide(1))}"/>`
  + `<path class="cut-edge" d="${k.pathOf([at([-BORE, DECK]), at([BORE, DECK])])}"/>`;

// Turned parts. Moving ones are drawn at their reference position and translated along their axis at runtime.
const webF = G.frameAlong([0, -11, 0], [0, 1, 0]);
const web = solid([[0, 17], [4, 17]], webF, { bevel: .5 });
const journal = solid([[0, 4.2], [7, 4.2]], G.frameAlong([0, -18, 0], [0, 1, 0]));
const pistonF = G.frameAlong([0, 0, TDC_PIN - PIN_UP], [0, 0, 1]);
const piston = solid([[0, 13.4], [PIN_UP + CROWN - 1, 13.6], [PIN_UP + CROWN, 13.1]], pistonF, { bevel: .4 })
  + [PIN_UP + CROWN - 2, PIN_UP + CROWN - 3.4, PIN_UP + CROWN - 4.8].map(s => k.lineSvg(G.arcOf(pistonF, s, 13.6, P), { tone: 'hi' })).join('');
const valve = side => { const F = G.frameAlong(seatOf(side), axisOf(side)); return solid([[0, 5.4], [.9, 5.4], [2.6, 1.7], [3.4, 1]], F) + solid([[3, .95], [STEM, .95]], F) + solid([[STEM - 3.4, 3.2], [STEM - 2.4, 3.2]], F); };
const plugF = G.frameAlong([0, 0, DECK - 1.6], [0, 0, 1]);
const plug = [[[0, .5], [1, .5]], [[.8, 1.9], [11, 1.9]], [[11, 3.3], [14.6, 3.3]], [[14.6, 2.3], [23.5, 1.9], [26, 1.1]]].map(profile => solid(profile, plugF)).join('');
const camshaft = side => solid([[0, 2.2], [9, 2.2]], G.frameAlong([camOf(side)[0], -11, camOf(side)[2]], [0, 1, 0]));

const geometry = { P, CRANK, ROD, PIN_UP, CROWN, BORE, DECK: r2(DECK), TDC_PIN, TILT_DEG: 20, SEAT_X, STEM, CAM_BASE, LIFT, cams: [-1, 1].map(s => camOf(s).map(r2)), axes: [-1, 1].map(s => axisOf(s).map(v => Math.round(v * 1e4) / 1e4)) };
const label = (zh, en) => `data-zh-label="${zh}" data-en-label="${en}"`;
const art = `<g id="engine-art" data-geometry='${JSON.stringify(geometry)}'>`
  + `<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" class="hatch-bg"/><line x1="0" y1="0" x2="0" y2="5" class="hatch-line"/></pattern></defs>`
  + `<ellipse cx="${r2(at([0, -34])[0])}" cy="${r2(at([0, -34])[1])}" rx="120" ry="12" class="floor"/>`
  + `<g data-part="chamber" ${label('燃烧室：活塞顶和缸盖之间的气体', 'Chamber: the gas between piston and head')}>${cavity}<g id="rt-gas"></g></g>`
  + `<g data-part="crank" ${label('曲轴：活塞往复，曲轴转圈', 'Crankshaft: the piston slides, the crank turns')}>${journal}${web}<g id="rt-crank"></g></g>`
  + `<g data-part="cams" ${label('凸轮轴：顶开气门，转速只有曲轴一半', 'Camshafts: open the valves at half crank speed')}>${camshaft(-1)}${camshaft(1)}<g id="rt-cams"></g></g>`
  + `<g data-part="rod" ${label('连杆：把活塞的推力传给曲轴', 'Connecting rod: carries the push to the crank')}><g id="rt-rod"></g></g>`
  + `<g data-part="block" ${label('缸体与缸盖（剖面）', 'Block and head (cut away)')}>${blockCut}</g>`
  + `<g data-part="piston" ${label('活塞', 'Piston')}><g id="piston-solid">${piston}</g></g>`
  + `<g data-part="block" ${label('缸体与缸盖（剖面）', 'Block and head (cut away)')}>${headCut}</g>`
  + `<g data-part="valves" ${label('进气门（左）与排气门（右）', 'Intake valve (left) and exhaust valve (right)')}><g id="rt-springs"></g><g id="valve-in">${valve(-1)}</g><g id="valve-ex">${valve(1)}</g></g>`
  + `<g data-part="plug" ${label('火花塞：只在做功冲程开始时点火', 'Spark plug: fires only as the power stroke begins')}>${plug}<g id="rt-spark"></g></g>`
  + `<g data-part="belt" ${label('正时皮带：曲轴小轮转两圈，凸轮大轮转一圈', 'Timing belt: small crank wheel turns twice per cam turn')}><g id="rt-belt"></g></g>`
  + `<g id="rt-labels"></g></g>`;

const html = readFileSync(target, 'utf8');
if (!html.includes('<!-- ENGINE_ART_START -->')) throw Error('Engine visual markers are missing.');
writeFileSync(target, html.replace(/<!-- ENGINE_ART_START -->[\s\S]*?<!-- ENGINE_ART_END -->/, () => `<!-- ENGINE_ART_START -->${art}<!-- ENGINE_ART_END -->`));
console.log('Generated Anatomy lathe solids (piston, valves, plug, crank web, camshafts) and cut faces in the engine lesson.');
