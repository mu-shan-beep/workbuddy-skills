import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as k from '../assets/anatomy/kit/iso-kit.mjs';
import * as G from '../assets/anatomy/kit/lathe.mjs';
import { tubePieces, tubeSvg } from '../assets/anatomy/kit/tube.mjs';

// Anatomy generates the turned surfaces and pipe skins; these original dimensions describe no real vehicle.
const target = fileURLToPath(new URL('../examples/rocket-launch.html', import.meta.url));
const F = G.frameAlong([0, 0, 0], [0, 0, 1]);
const P = { origin: [180, 575], scale: 1.2, azimuth: 40, elevation: 12 };
const path = points => k.pathOf(points, true);
const solid = (profile, projection = P, options = {}) => k.solidSvg(G.solidOf(profile, F, projection, { steps: 64, ...options }), { tone: 'mid' });
const ring = (z, r, projection = P, thickness = 2) => k.solidSvg(G.ringBand(z, z + thickness, r - 2, r, F, projection, { steps: 64 }), { tone: 'mid' });
const seam = (z, r, projection = P) => k.lineSvg(G.arcOf(F, z, r, projection), { tone: 'faint' });
const bolts = (z, r, projection = P, count = 12) => k.dotsSvg(G.dotsOf(F, z, r, count, projection, { all: true }), { size: .65, tone: 'hi' });
const pipe = (points, radius, projection) => tubePieces(points, radius, projection, { maxLength: 15 }).map(part => tubeSvg(part, { tone: 'mid' })).join('');
const projectSection = (x, z, projection = P) => {
  const centre = k.iso([0, 0, z], projection);
  return [centre[0] + x * projection.scale * Math.sqrt(1.6), centre[1]];
};
function chamber(projection) {
  let svg = solid([[55, 9], [59, 13], [78, 13], [84, 10]], projection, { bevel: .7 });
  for (const z of [58, 63, 79, 83]) svg += ring(z, 15, projection, 1.5) + bolts(z + 1.5, 12, projection);
  svg += k.fadedSvg(G.ribsOf(F, 64, 78, 13.3, 28, projection, { fade: [.08, .4], seams: true }), { tone: 'faint' });
  svg += solid([[84, 10], [87, 10], [87, 18], [90, 18]], projection, { bevel: .5 }) + bolts(90, 15.5, projection, 16);
  return svg;
}
function nozzle(projection) {
  const radius = s => 8 + 24 * (1 - s / 55) ** 1.65;
  const slope = s => -24 * 1.65 / 55 * (1 - s / 55) ** .65;
  const stations = [2, 10, 20, 30, 40, 48, 55];
  const bands = G.bandsOf([[2, radius(2)], [55, radius(55)]], stations.slice(1, -1), F, projection, { radius, slope, steps: 72, rows: 5 });
  const ordered = projection.elevation < 0 ? bands.bands.slice().reverse() : bands.bands;
  let svg = ordered.map((band, i) => k.solidSvg(band.paths, { tone: 'mid', inner: i % 2 ? k.lineSvg(band.seam, { tone: 'faint' }) : '' })).join('');
  svg += k.lineSvg(bands.sidesOf(2, 55, { ends: 'first', count: 44 }).d, { tone: 'faint' });
  svg += ring(0, 33, projection, 2) + ring(54, 10.2, projection, 1.4);
  if (projection.elevation < 0) {
    svg += `<path class="engine-void" d="${G.circleOf(F, 0, 29.8, projection)}"/>`;
    svg += k.lineSvg(G.arcOf(F, 0, 29.8, projection, { inward: true, least: -1 }), { tone: 'mid' });
  }
  return svg;
}
function engine(projection) {
  const nozzleSvg = `<g class="engine-nozzle" data-component="nozzle">${nozzle(projection)}</g>`;
  const chamberSvg = `<g data-component="chamber">${chamber(projection)}</g>`;
  let svg = projection.elevation < 0 ? chamberSvg + nozzleSvg : nozzleSvg + chamberSvg;
  svg += `<g data-component="feed">`;
  const supply = G.fillet([[21, 0, 89], [27, 0, 89], [27, 0, 63], [13, 0, 63]], 3, 16, { P: projection, tube: 1.8 });
  svg += pipe(supply, 1.8, projection);
  const cooling = G.fillet([[-19, 1, 89], [-25, 1, 89], [-25, 1, 17], [-21.2, 1, 17]], 3, 16, { P: projection, tube: 1.5 });
  svg += pipe(cooling, 1.5, projection);
  for (const [x, z] of [[27, 70], [-25, 75], [-25, 43]]) {
    const local = G.frameAlong([x, 0, z], [0, 0, 1]);
    svg += k.solidSvg(G.disc(-1.4, 1.4, 3.4, local, projection), { tone: 'mid' });
  }
  svg += '</g>';
  return svg;
}
function tankSection(bottom, top, r) {
  const left = projectSection(-r, bottom + 11), right = projectSection(0, bottom + 11);
  const yTop = projectSection(0, top - 11)[1], yBottom = left[1];
  const outer = `M${right[0]} ${yTop - 19}Q${left[0]} ${yTop - 19} ${left[0]} ${yTop}V${yBottom}Q${left[0]} ${yBottom + 19} ${right[0]} ${yBottom + 19}Z`;
  const inset = 3.6;
  const inner = `M${right[0]} ${yTop - 15}Q${left[0] + inset} ${yTop - 15} ${left[0] + inset} ${yTop + 1}V${yBottom - 1}Q${left[0] + inset} ${yBottom + 15} ${right[0]} ${yBottom + 15}Z`;
  return `<g class="section"><path class="tank-cavity" d="${outer}"/><path class="tank-cut" fill-rule="evenodd" d="${outer}${inner}"/><path class="tank-back-rib" d="M${left[0] + 9} ${yTop + 2}V${yBottom - 2}"/><path class="section-edge" d="M${right[0]} ${yTop - 19}V${yBottom + 19}"/></g>`;
}
function tank(bottom, top, r) {
  const profile = [[bottom, r - 8], [bottom + 3, r - 3], [bottom + 9, r], [top - 9, r], [top - 3, r - 3], [top, r - 8]];
  return `<g class="skin">${solid(profile)}${seam(bottom + 10, r)}${seam(top - 10, r)}${ring(bottom + 9, r + 1)}${ring(top - 11, r + 1)}</g>${tankSection(bottom, top, r)}`;
}
let vehicle = `<svg id="rocket-structure" class="technical-svg" viewBox="0 0 360 650" role="img" aria-labelledby="structure-title structure-desc"><title id="structure-title">通用液体火箭的结构剖面与轴向分解</title><desc id="structure-desc">四个组件从上到下为整流罩、两个独立储箱、推力架与发动机。剖面模式显示金属壳体厚度、储箱封头和通向发动机的管路。</desc><defs><clipPath id="rocket-right"><rect x="180" y="0" width="180" height="650"/></clipPath><linearGradient id="section-metal"><stop stop-color="#c3d0d1"/><stop offset=".45" stop-color="#f2f4ec"/><stop offset="1" stop-color="#a4b7bb"/></linearGradient></defs><ellipse cx="180" cy="608" rx="68" ry="10" class="technical-shadow"/>`;
vehicle += `<g data-assembly="engine">${engine(P)}${ring(90, 31)}${bolts(92, 27)}${solid([[92, 28], [103, 28]], P)}${k.fadedSvg(G.ribsOf(F, 93, 101, 28, 28, P, { fade: [.08, .4], seams: true }), { tone: 'faint' })}</g>`;
vehicle += `<g data-assembly="lower">${tank(104, 182, 31)}${ring(102, 33)}${bolts(104, 29)}${ring(181, 33)}</g>`;
vehicle += `<g data-assembly="upper">${tank(185, 267, 31)}${ring(183, 33)}${bolts(185, 29)}${ring(266, 33)}</g>`;
const noseRadius = s => 31 * (1 - ((s - 270) / 57) ** 1.3) ** .65;
const noseSlope = s => -31 * .65 * 1.3 / 57 * ((s - 270) / 57) ** .3 * Math.max(.00001, 1 - ((s - 270) / 57) ** 1.3) ** -.35;
const profile = Array.from({ length: 25 }, (_, i) => { const s = 270 + i / 24 * 56.99; return [s, noseRadius(s)]; });
vehicle += `<g data-assembly="fairing"><g class="skin">${k.solidSvg(G.solidOf(profile, F, P, { steps: 64, smooth: { slope: noseSlope, radius: noseRadius, rows: 5 }, rims: "none" }), { tone: "mid", crease: "none" })}${ring(268, 33)}${bolts(270, 29)}</g><g class="section"><path class="fairing-cut" d="${path([projectSection(0, 327), ...profile.slice().reverse().map(([s, r]) => projectSection(-r, s)), projectSection(0, 270)])}"/><path class="payload-bay" d="${path([projectSection(-20, 275), projectSection(-20, 293), projectSection(-5, 293), projectSection(-5, 275)])}"/></g></g>`;
vehicle += `<g class="section feed-section"><path class="feed-line" d="${k.pathOf([projectSection(-15, 112), projectSection(-15, 96), projectSection(-8, 96), projectSection(-8, 87)])}"/><path class="feed-line" d="${k.pathOf([projectSection(-4, 193), projectSection(-4, 101), projectSection(9, 101), projectSection(9, 87)])}"/></g></svg>`;
const detailP = { origin: [178, 281], scale: 2.12, azimuth: 40, elevation: -16 };
const detail = `<svg id="engine-detail" class="technical-svg engine-detail" viewBox="0 0 360 330" role="img" aria-labelledby="engine-title engine-desc"><title id="engine-title">液体发动机喷注器、燃烧室与钟形喷管</title><desc id="engine-desc">放大观察喷注器的螺栓法兰、燃烧室的环形加强结构、收缩喉部、带冷却通道示意的钟形喷管与两条供给管路。该构型不是任何真实发动机的复刻。</desc><ellipse cx="178" cy="304" rx="88" ry="13" class="technical-shadow"/>${engine(detailP)}</svg>`;
const html = readFileSync(target, 'utf8');
if (!html.includes('<!-- ROCKET_STRUCTURE_START -->') || !html.includes('<!-- ROCKET_ENGINE_START -->')) throw Error('Rocket visual markers are missing.');
writeFileSync(target, html.replace(/<!-- ROCKET_STRUCTURE_START -->[\s\S]*?<!-- ROCKET_STRUCTURE_END -->/, `<!-- ROCKET_STRUCTURE_START -->${vehicle}<!-- ROCKET_STRUCTURE_END -->`).replace(/<!-- ROCKET_ENGINE_START -->[\s\S]*?<!-- ROCKET_ENGINE_END -->/, `<!-- ROCKET_ENGINE_START -->${detail}<!-- ROCKET_ENGINE_END -->`));
console.log('Generated Anatomy lathe, ring, ribs, bolt circles and segmented pipes in the standalone rocket lesson.');
