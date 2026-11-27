#!/usr/bin/env node
// check_model.mjs — 全科建模五道通用闸门（零依赖）
// 用法: node check_model.mjs <课件.html|lesson.json> [--quiet]
// 退出码: 0 全绿 / 1 有失败项
// 说明: 只查"契约与结构"，不查学科正确性——学科正确性由 meta.lawCheck 那条手算背书。

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { basename, dirname, resolve, join } from 'node:path';

const TYPES = ['rigid', 'media', 'micro', 'field-wave', 'geometry', 'process', 'stats', 'map', 'bio-structure', 'abstract'];
const KERNELS = ['symbolic', 'closed-form', 'numeric', 'state-machine', 'statistical'];
const CARRIERS = ['three', 'iso-svg', 'canvas2d', 'shader', 'chart', 'video'];
const ACTS = ['slider', 'toggle', 'orbit', 'hold', 'record', 'custom'];

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith('--'));
const quiet = args.includes('--quiet');
if (!file) {
  console.error('用法: node check_model.mjs <课件.html|lesson.json> [--quiet]');
  process.exit(2);
}

const raw = readFileSync(file, 'utf8');
const size = Buffer.byteLength(raw, 'utf8');

function extractData(text) {
  // 1) 纯 JSON 文件
  const t = text.trim();
  if (t.startsWith('{')) {
    try { return JSON.parse(t); } catch { /* 继续尝试 HTML */ }
  }
  // 2) HTML 内的 window.__LESSON_DATA__ = {...};
  const m = text.match(/__LESSON_DATA__\s*=\s*/);
  if (!m) return null;
  let i = m.index + m[0].length;
  while (i < text.length && /\s/.test(text[i])) i++;
  if (text[i] !== '{') return null;
  let depth = 0, inStr = false, esc = false, start = i;
  for (; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) {
        try { return JSON.parse(text.slice(start, i + 1)); } catch (e) {
          console.error('__LESSON_DATA__ 不是合法 JSON:', e.message);
          return null;
        }
      }
    }
  }
  return null;
}

const fails = [];
const passes = [];
const warns = [];
const ok = (gate, msg) => passes.push(`${gate} ${msg}`);
const bad = (gate, msg) => fails.push(`${gate} ${msg}`);
const warn = (msg) => warns.push(msg);

const data = extractData(raw);
if (!data) {
  console.error('✗ 找不到契约数据。需要纯 JSON，或 HTML 里的 window.__LESSON_DATA__ = {...}');
  process.exit(1);
}

/* ---------- 结构 ---------- */
const meta = data.meta || {};
const type = data.type;
const kernel = data.kernel || {};
const carrier = data.carrier || {};
const law = data.law || {};
const model = data.model || {};
const console_ = data.console || {};
const steps = Array.isArray(data.steps) ? data.steps : [];

/* ---------- G-0 工单留痕（进门先验票） ----------
   产物是谁做的、按什么验收，必须能从磁盘上读出来。
   没有工单的产物，换个人接不了、出了问题追不到 —— 这是"调控者"和"工匠"的分界。 */
const orderPath = join(dirname(resolve(file)), '工单.md');
if (existsSync(orderPath)) {
  const ord = readFileSync(orderPath, 'utf8');
  const need = ['## 1 口径', '## 2 契约', '## 3 参数', '## 4 承包商', '## 5 验收线', '## 6 交付'];
  const miss = need.filter((h) => !ord.includes(h));
  if (miss.length) bad('G-0', `工单缺块：${miss.map((h) => h.replace('## ', '')).join(' / ')}`);
  const cm = ((ord.match(/-\s*主承包商[：:]\s*(.+)/) || [])[1] || '').trim();
  if (!cm) bad('G-0', '工单没写主承包商');
  else if (/^(我|自己|自制|本技能)$/.test(cm)) bad('G-0', `主承包商写成"${cm}"：没查名录就自己上手，兜底必须写「兜底（自制）」并登记待招岗位`);
  if (!/状态[：:]\s*\S+/.test(ord)) bad('G-0', '工单没写状态行（已开单/派活中/待验收/打回第 n 次/通过）');
  if (!fails.some((f) => f.startsWith('G-0'))) ok('G-0', `工单齐（承包商：${cm}）`);
} else {
  warn('同目录无 工单.md：本次交付的承包商与验收线无法追溯（存量产物可忽略，新课必须补单）');
}

/* ---------- G-A 量纲 ---------- */
const consts = Array.isArray(model.consts) ? model.consts : [];
const outputs = Array.isArray(model.outputs) ? model.outputs : [];
if (!consts.length) bad('G-A', 'model.consts 为空：一个模型至少要有一个常量');
if (!outputs.length) bad('G-A', 'model.outputs 为空：至少要有 1 个读数');
for (const c of consts) {
  if (!c || !c.k) bad('G-A', '常量缺 k');
  if (c && !c.unit) bad('G-A', `常量 ${c.k || '?'} 缺单位`);
  if (c && !c.from) bad('G-A', `常量 ${c.k || '?'} 缺 from（口径卡键名或"定义"）`);
  if (c && c.from && !/^定义$/.test(c.from) && !/^[a-z]{2,12}\.[A-Za-z0-9_]+$/.test(c.from)) {
    warn(`常量 ${c.k} 的 from="${c.from}" 不像口径卡键名（形如 phys.g_10）`);
  }
}
for (const o of outputs) {
  if (!o || !o.k) bad('G-A', '读数缺 k');
  if (o && !o.unit) bad('G-A', `读数 ${o.k || '?'} 缺单位：屏幕上的数必须带单位`);
}
if (consts.length && outputs.length) ok('G-A', `量纲字段齐（${consts.length} 常量 / ${outputs.length} 读数）`);

/* ---------- G-B 尺度 ---------- */
const scale = meta.scale || {};
if (!scale.unit) bad('G-B', 'meta.scale.unit 缺失（1 单位等于什么）');
if (!scale.note) bad('G-B', 'meta.scale.note 缺失（画面上的比例尺或简化声明）');
if (meta.thumb !== true) bad('G-B', 'meta.thumb 必须为 true：首帧即缩略图');
if (scale.unit && scale.note && meta.thumb === true) ok('G-B', `尺度已声明（1 单位 = 1 ${scale.unit}）`);

/* ---------- G-C 口径 ---------- */
for (const k of ['subject', 'grade', 'textbook']) {
  if (!meta[k]) bad('G-C', `meta.${k} 缺失：口径卡按此项选`);
}
if (!meta.lawCheck) bad('G-C', 'meta.lawCheck 缺失：学科正确性必须有一条手算凭据');
if (!meta.source) warn('meta.source 缺失：复刻/改编要留出处');
if (meta.subject && meta.grade && meta.textbook && meta.lawCheck) ok('G-C', `口径齐（${meta.subject}/${meta.grade}/${meta.textbook}）`);

/* ---------- G-D 确定性 ---------- */
// 第三方库（three.js 等）内部自带 Math.random / 性能计时，不算本课的非确定性。
// 只扫描"自己写的"部分：<script id="vendor"> 里的内容整段排除。
let own = raw;
const vendorBlocks = [...raw.matchAll(/<script[^>]*id=["']vendor["'][^>]*>([\s\S]*?)<\/script>/gi)];
for (const vb of vendorBlocks) own = own.replace(vb[1], '');
if (vendorBlocks.length) {
  const vbBytes = vendorBlocks.reduce((s, vb) => s + Buffer.byteLength(vb[1], 'utf8'), 0);
  warn(`已排除内联第三方库 ${(vbBytes / 1024).toFixed(0)} KB，G-D 只扫自写代码`);
}
const dirty = [];
if (/Math\s*\.\s*random\s*\(/.test(own)) dirty.push('Math.random()');
if (/Date\s*\.\s*now\s*\(/.test(own)) dirty.push('Date.now()');
if (/performance\s*\.\s*now\s*\(/.test(own) && !/requestAnimationFrame/.test(own)) dirty.push('performance.now() 无帧驱动');
if (dirty.length) bad('G-D', `非确定性调用：${dirty.join(', ')}`);
else ok('G-D', '无随机/时钟调用，同输入同帧');

/* ---------- G-E 可读 ---------- */
if (steps.length < 3 || steps.length > 8) bad('G-E', `步骤数 ${steps.length}，应为 3–8`);
const sliderKeys = new Set((console_.sliders || []).map((s) => s && s.k));
for (const s of steps) {
  if (!s || !s.expect) bad('G-E', `步骤「${(s && s.tag) || '?'}」缺 expect`);
  if (s && !s.concl) bad('G-E', `步骤「${s.tag || '?'}」缺 concl`);
  const act = (s && s.act) || {};
  if (!ACTS.includes(act.kind)) bad('G-E', `步骤「${(s && s.tag) || '?'}」act.kind 非法（应为 ${ACTS.join('/')}）`);
  if (act.kind === 'slider' && act.k && !sliderKeys.has(act.k)) bad('G-E', `步骤引用了不存在的滑块 ${act.k}`);
}
const nSlider = (console_.sliders || []).length;
const nSwitch = (console_.switches || []).length;
const nChart = Number(console_.charts || 0);
if (nSlider > 3) bad('G-E', `滑块 ${nSlider} 个，上限 3`);
if (nSwitch > 4) bad('G-E', `开关 ${nSwitch} 个，上限 4`);
if (nChart > 1) bad('G-E', `图表 ${nChart} 个，上限 1`);
for (const s of console_.sliders || []) {
  if (!s || !s.unit) bad('G-E', `滑块 ${(s && s.k) || '?'} 缺单位`);
  if (s && (s.min === undefined || s.max === undefined)) bad('G-E', `滑块 ${s.k} 缺 min/max`);
}
const ext = raw.match(/(?:src|href)\s*=\s*["']https?:\/\//gi) || [];
if (ext.length) bad('G-E', `有 ${ext.length} 处外链，断网打不开（three.js 必须内联）`);
if (size > 3.5 * 1024 * 1024) bad('G-E', `体积 ${(size / 1048576).toFixed(1)} MB，超过 3.5 MB 上限`);
if (!fails.some((f) => f.startsWith('G-E'))) ok('G-E', `可读性通过（${steps.length} 步 / ${nSlider} 滑块 / ${(size / 1024).toFixed(0)} KB）`);

/* ---------- G-F 投影可读 ----------
   教室投影的四条硬账：
   ① 舞台必须铺满视口、不许留黑边也不许被裁。两种合法形态：
      A 固定画布（#app 写死 1280×720 起 + 16:9）+ 外层 #stage 按 min(vw/W, vh/H) 等比缩放 —— 会留黑边，最小可用；
      B 流式网格（#app 100vw/100vh + grid，中间舞台 minmax(0,1fr)）—— 任何视口都铺满，2026-11-27 起作为首选；
   ② 屏幕上最小字号 ≥16px。1024px 投 2 m 宽时 1px≈1.95 mm，16px 字高约 31 mm，
      按"字高≥观看距离/200"够 6 m 内看清；后排 8–10 m 的教室要 ≥20px，属于校区差异，不在闸门里一刀切；
   ③ 必须留下比本 html 更新的截图——没有像素复核就等于没看。 */
const appRule = (raw.match(/(?:^|[\s,{}])#app\s*\{[^}]*\}/m) || [''])[0] ||
                (raw.match(/html\s*,\s*body\s*\{[^}]*\}/m) || [''])[0];
const cw = Number((appRule.match(/width\s*:\s*(\d+)px/) || [])[1] || 0);
const chh = Number((appRule.match(/height\s*:\s*(\d+)px/) || [])[1] || 0);
// 流式形态：100vw/100vh + grid + min-width 保护，才算真的铺满
const isFluid = /width\s*:\s*100vw/.test(raw) && /height\s*:\s*100vh/.test(raw) &&
                /display\s*:\s*grid/.test(raw) && /grid-template-columns/.test(raw) &&
                /min-width\s*:\s*1\d{3}px/.test(raw);
const minW = Number((raw.match(/min-width\s*:\s*(\d+)px/) || [])[1] || 0);
const minH = Number((raw.match(/min-height\s*:\s*(\d+)px/) || [])[1] || 0);
if (isFluid) {
  if (minW < 1280) bad('G-F', `流式布局最小宽 ${minW}px < 1280：窄窗口会把三栏挤扁，字号再大也读不出`);
  if (!minH || minH < 700) bad('G-F', '流式布局缺 min-height（≥700px）保护：窗口过矮时卡片会互相压住');
} else if (!cw || !chh) {
  bad('G-F', '找不到舞台：要么用流式（#app 100vw/100vh + grid + min-width:1280px），' +
             '要么用固定画布（#app 或 html,body 写死 width/height 的 px 值）+ #stage 等比缩放');
} else if (cw < 1280) {
  bad('G-F', `画布宽 ${cw}px < 1280：投影分辨率不够，字再大也是糊的`);
} else if (Math.abs(cw / chh - 16 / 9) > 0.02) {
  bad('G-F', `画布 ${cw}×${chh} 不是 16:9：投影仪会留黑边或裁切`);
}

const cssSizes = [...raw.matchAll(/font-size\s*:\s*(\d+(?:\.\d+)?)px/gi)].map((m) => +m[1]);
const minCss = cssSizes.length ? Math.min(...cssSizes) : 0;
if (minCss && minCss < 16) {
  const small = [...new Set(cssSizes.filter((v) => v < 16))].sort((a, b) => a - b);
  bad('G-F', `CSS 最小字号 ${small.join('/')}px < 16px：投影后字号 = 屏幕 px × 放大倍数不足，后排看不清`);
}

// 画布内文字按 2 倍备份绘制（canvas.width ≈ 2×CSS 宽），所以字号下限按 32px 算，等于屏幕 16px
const canvasFonts = [...raw.matchAll(/\.font\s*=\s*['"][^'"]*?(\d+)px/g)].map((m) => +m[1]);
const minCanvas = canvasFonts.length ? Math.min(...canvasFonts) : 0;
if (minCanvas && minCanvas < 32) {
  bad('G-F', `画布内字号 ${minCanvas}px < 32px（2 倍备份下等于屏幕 ${(minCanvas / 2).toFixed(0)}px）`);
}

// ④ 自适应：窗口小于画布时不许裁边、比画布大时不许留黑边。
//    真实事故（2026-11-27）：Windows 125% 缩放下视口只有 1344 px，写死 1600 的页面右侧整块读数卡被切掉，
//    学生看不见 H₂/O₂ 读数——比字小更致命，等于这节的证据没了。
//    第二次事故（同日）：换成 min() 等比缩放后，1920 宽屏上下/左右各留一条黑边，用户直接问"为什么没有撑满页面"。
//    所以两种做法都认，但必须选一种做对：
//      A 固定画布 + #stage 等比缩放（留黑边，可接受的最低配）；
//      B 流式网格（100vw/100vh + grid + canvas 跟着容器 resize）—— 铺满且不裁，推荐。
const hasStage = /id\s*=\s*["']stage["']/.test(raw);
const hasScale = /transform\s*:\s*scale|style\.transform\s*=\s*['"]scale/.test(raw);
const hasFluidFit = isFluid && /setSize\s*\(/.test(raw) && /clientWidth/.test(raw);
if (!(hasStage && hasScale) && !hasFluidFit) {
  bad('G-F', '舞台不自适应：窗口窄会被裁、宽会留黑边。二选一——' +
             'A：外层 #stage flex 居中 + scale=min(vw/W,vh/H)；' +
             'B：流式 grid（100vw/100vh）+ canvas 按容器 clientWidth/Height setSize + camera.aspect 跟着改');
}

// ⑤ 过程节奏：驱动量必须"看得见在变"。
//    真实事故：播放倍率 60×，600 s 十秒播完，读数在跳、画面像静态图，用户直接问"电解水没有过程"。
//    规矩：总时长 25–40 秒播完（即 15–24×）；动画量（气泡/粒子）用真实时间，读数用模拟时间，两者不许共用一个时钟。
const speedHits = [...raw.matchAll(/dt\s*\*\s*(\d+(?:\.\d+)?)/g)].map((m) => +m[1]).filter((v) => v > 1);
const fastest = speedHits.length ? Math.max(...speedHits) : 0;
if (fastest >= 30) {
  bad('G-F', `播放倍率 ${fastest}× 太快：过程一闪而过，看起来像静态图。总时长按 25–40 秒播完（15–24×）`);
}
if (!/S\.anim|anim\s*\+=|clock\.getElapsed/.test(raw)) {
  warn('G-F 没找到独立的动画时钟：气泡/粒子若跟读数同一个 t 走，会随播放倍率一起乱闪');
}

let shotInfo = '';
try {
  const dir = dirname(resolve(file));
  const htmlTime = statSync(file).mtimeMs;
  const shots = readdirSync(dir)
    .filter((f) => /\.(png|jpe?g)$/i.test(f))
    .map((f) => ({ f, t: statSync(join(dir, f)).mtimeMs }));
  const fresh = shots.filter((s) => s.t >= htmlTime).sort((a, b) => b.t - a.t);
  if (!shots.length) bad('G-F', '同目录没有截图：没看像素就不许交付（先截图再跑闸门）');
  else if (!fresh.length) bad('G-F', '截图比当前 html 旧：改完没重截，等于没看新像素');
  else shotInfo = `，像素复核 ${fresh.length} 张（最新 ${fresh[0].f}）`;
} catch {
  warn('G-F 无法读取目录，跳过截图核验');
}
// ⑥ 投影色复核：结构闸门查不出对比度。
//    真实事故（2026-11-27）：浅色卡片在模拟投影（对比度 .82 + 黑位抬升 + 白雾）下，
//    卡片边界、图表网格、公式注释全糊掉，主读数还在 —— "能读数"但结构信息丢了。
//    所以要求同目录有一张 proj.mjs 产出的劣化模拟图（文件名 P- 开头），且不比 html 旧。
let projInfo = '';
try {
  const dir2 = dirname(resolve(file));
  const htmlT2 = statSync(file).mtimeMs;
  const proj = readdirSync(dir2)
    .filter((f) => /^P-.*\.(png|jpe?g)$/i.test(f))
    .map((f) => ({ f, t: statSync(join(dir2, f)).mtimeMs }));
  if (!proj.length) {
    warn('G-F 没有投影模拟图（proj.mjs 产出、文件名 P- 开头）：浅色面板在教室里看不看得清，没人验过');
  } else {
    const freshP = proj.filter((s) => s.t >= htmlT2).sort((a, b) => b.t - a.t);
    if (!freshP.length) warn('G-F 投影模拟图比 html 旧：改完配色没重跑模拟，等于没看');
    else projInfo = `，投影模拟 ${freshP[0].f}`;
  }
} catch {}

if (!fails.some((f) => f.startsWith('G-F'))) {
  const stageInfo = isFluid ? `流式铺满（min ${minW}×${minH}）` : `${cw}×${chh} 16:9`;
  ok('G-F', `投影可用（${stageInfo}，最小字号 ${minCss}px${shotInfo}${projInfo}）`);
}

/* ---------- 契约字段 ---------- */
if (!TYPES.includes(type)) bad('契约', `type="${type}" 不在十类内（${TYPES.join('/')}）`);
if (!KERNELS.includes(kernel.kind)) bad('契约', `kernel.kind="${kernel.kind}" 非法`);
if (!kernel.precision) bad('契约', 'kernel.precision 缺失（精度要求）');
if (!CARRIERS.includes(carrier.kind)) bad('契约', `carrier.kind="${carrier.kind}" 非法`);
if (!carrier.why) bad('契约', 'carrier.why 缺失：必须说明为什么不用别的载体');
if (!law.name || !law.check) bad('契约', 'law.name / law.check 缺失：本类型硬律与验法');
if (TYPES.includes(type) && KERNELS.includes(kernel.kind) && CARRIERS.includes(carrier.kind) && carrier.why && law.name && law.check) {
  ok('契约', `${type} + ${kernel.kind} + ${carrier.kind}`);
}

/* ---------- 输出 ---------- */
const name = basename(file);
if (!quiet) {
  console.log(`\n${name}  ·  ${meta.title || '(无标题)'}  ·  ${meta.subject || '?'}/${meta.grade || '?'}`);
  console.log('─'.repeat(64));
  for (const p of passes) console.log('  ✓ ' + p);
  for (const f of fails) console.log('  ✗ ' + f);
  for (const w of warns) console.log('  ! ' + w);
  console.log('─'.repeat(64));
} else {
  for (const f of fails) console.log('  ✗ ' + f);
}
if (fails.length) {
  console.log(`\n结果: 失败 ${fails.length} 项，不许交付。\n`);
  process.exit(1);
}
console.log(`\n结果: 六闸全绿${warns.length ? `（${warns.length} 条提示）` : ''}。学科正确性另看 meta.lawCheck。\n`);
process.exit(0);
