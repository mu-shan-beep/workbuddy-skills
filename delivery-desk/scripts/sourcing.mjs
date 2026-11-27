#!/usr/bin/env node
/**
 * sourcing.mjs —— 查重 ①③ 级的执行器
 *
 * 用法：
 *   node scripts/sourcing.mjs --grep "发布 方案 策划"
 *   node scripts/sourcing.mjs --grep "婚礼" --base "/path/to/extra-assets"
 *   node scripts/sourcing.mjs --list          # 只列扫描概况
 *
 * 扫描对象（与任何机器、任何技能名、任何资产库名解绑）：
 *   [技能]  本机已安装技能 —— 技能根自动定位（与 inventory.mjs 同源），零配置即用
 *   [资产]  可选资产根 —— env DELIVERY_DESK_ASSETS / config.json assetsRoot / --base
 *           目录树下所有 SKILL.md / README.md / catalog.json 都算可检索能力描述
 *
 * 定位顺序（资产根）：--base > 环境变量 > config.json（机器本地，见 config.example.json）
 *
 * 退出码：0 = 有命中；2 = 无命中
 */

import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname, basename, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const argv = process.argv.slice(2);
const getArg = (name) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
};
const hasFlag = (name) => argv.includes(name);

const grep = (getArg('--grep') || '').split(/\s+/).filter(Boolean);
const explicitBase = getArg('--base');
const listOnly = hasFlag('--list');

// 中英同义映射：能力描述多数是英文，只用中文词必然搜不到。
// 命中任一写法即算命中；未收录的词按原样匹配。
const ALIASES = {
  发布: ['launch', 'release', 'rollout', 'go-to-market', 'gtm', 'ship'],
  方案: ['plan', 'proposal', 'playbook', 'framework', 'blueprint'],
  策划: ['planning', 'plan', 'strategy', 'playbook', 'campaign'],
  提案: ['proposal', 'pitch', 'deck', 'brief'],
  活动: ['event', 'activation', 'campaign', 'offsite'],
  营销: ['marketing', 'campaign', 'growth', 'promotion'],
  品牌: ['brand', 'positioning', 'messaging'],
  文档: ['document', 'doc', 'docx', 'writing', 'report'],
  报告: ['report', 'brief', 'analysis'],
  表格: ['table', 'sheet', 'spreadsheet', 'csv', 'excel'],
  演示: ['slide', 'presentation', 'deck', 'ppt', 'storyboard'],
  数据: ['data', 'dataset', 'analytics', 'metrics', 'kpi'],
  流程: ['process', 'workflow', 'pipeline', 'procedure'],
  验收: ['review', 'qa', 'acceptance', 'checklist', 'readiness'],
  定价: ['pricing', 'price', 'packaging'],
  竞品: ['competitive', 'competitor', 'battlecard', 'intel'],
  用户: ['user', 'customer', 'persona', 'journey'],
  需求: ['requirement', 'prd', 'spec'],
  视觉: ['visual', 'design', 'ui', 'ux', 'graphic'],
  视频: ['video', 'film', 'motion'],
  音频: ['audio', 'sound', 'voice'],
  图: ['image', 'graphic', 'svg', 'illustration'],
  课: ['lesson', 'course', 'teaching', 'class'],
  模型: ['model', '3d', 'mesh', 'blender'],
  团队: ['team', 'stakeholder', 'collaboration'],
  风险: ['risk', 'premortem', 'mitigation'],
  指标: ['metric', 'measure', 'kpi'],
  复盘: ['retro', 'review', 'postmortem', 'lessons'],
  论文: ['paper', 'thesis', 'manuscript', 'article', 'preprint'],
  学术: ['academic', 'scholarly', 'research', 'scientific'],
  文献: ['literature', 'reference', 'bibliography', 'citation'],
  引用: ['citation', 'cite', 'reference'],
  投稿: ['submission', 'journal', 'conference', 'venue'],
};

const expand = (k) => [k, ...(ALIASES[k] || [])].map((s) => s.toLowerCase());

if (!listOnly && grep.length === 0) {
  console.error('用法: node scripts/sourcing.mjs --grep "关键词1 关键词2"');
  console.error('      node scripts/sourcing.mjs --list');
  process.exit(2);
}

// —— 定位 ——
// 技能根与 inventory.mjs 同源：本技能所在根 + 其上级内置 skills 目录
const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = dirname(SCRIPTS_DIR);

function loadConfig() {
  const p = join(SKILL_DIR, 'config.json');
  if (!existsSync(p)) return {};
  try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return {}; }
}
const cfg = loadConfig();

function expandPath(p) {
  if (!p) return p;
  if (p === '~' || p.startsWith('~/')) return join(homedir(), p.slice(1));
  return p;
}

function skillRoots() {
  const roots = [
    resolve(SKILL_DIR, '..'),                          // 本技能所在根（.user_skills / skills 等）
    resolve(SKILL_DIR, '..', '..', '.skills'),         // 客户端内置 skills
  ];
  const extra = cfg.skillsRoots;
  if (Array.isArray(extra)) roots.push(...extra.map(expandPath));
  else if (typeof extra === 'string') roots.push(expandPath(extra));
  return roots;
}

function assetRoots() {
  const raw = [];
  if (explicitBase) raw.push(explicitBase);
  else {
    if (process.env.DELIVERY_DESK_ASSETS) raw.push(process.env.DELIVERY_DESK_ASSETS);
    if (cfg.assetsRoot) {
      if (Array.isArray(cfg.assetsRoot)) raw.push(...cfg.assetsRoot);
      else raw.push(cfg.assetsRoot);
    }
  }
  return raw.map(expandPath).filter(Boolean);
}

// —— 工具 ——
const HEAD_LINES = 90;

function readHead(file) {
  try {
    const raw = readFileSync(file, 'utf8');
    return raw.split(/\r?\n/).slice(0, HEAD_LINES).join('\n');
  } catch {
    return '';
  }
}

function extractMeta(text, dirName) {
  const name = (text.match(/^name:\s*(.+)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');
  let desc = (text.match(/^description:\s*(.+)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');

  // YAML 块标量：description: | 或 > 或 |- 等。正则只能抓到那个竖线，
  // 不往下读就等于这条技能没有描述——查重时永远搜不到它。
  if (desc && /^[|>][-+0-9]*$/.test(desc)) {
    const lines = text.split(/\r?\n/);
    const idx = lines.findIndex((l) => /^description:\s*[|>]/.test(l));
    if (idx >= 0) {
      const buf = [];
      for (let i = idx + 1; i < lines.length && buf.length < 20; i++) {
        const l = lines[i];
        if (l.trim() === '') { buf.push(''); continue; }
        if (/^\S/.test(l)) break; // 回到顶层 key，块结束
        buf.push(l.trim());
      }
      const block = buf.join(' ').trim();
      if (block) desc = block;
    }
  }

  if (!desc) {
    // md 里没有 frontmatter：取第一个非空标题或正文行
    const line = text.split(/\r?\n/).find((l) => l.trim() && !l.startsWith('---') && !l.startsWith('#!'));
    desc = line ? line.replace(/^#+\s*/, '').trim() : '';
  }
  return { name: name || dirName, desc: desc || '' };
}

function walk(dir, out, depth = 0) {
  if (depth > 6) return;
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.git') continue;
      walk(p, out, depth + 1);
    } else if (e.isFile() && (e.name === 'SKILL.md' || e.name === 'README.md' || e.name === 'catalog.json')) {
      out.push(p);
    }
  }
}

// —— [技能] 本机已安装技能（零配置，总扫） ——
function scanSkills() {
  const rows = [];
  const seen = new Set();
  for (const root of skillRoots()) {
    if (!existsSync(root)) continue;
    let dirs;
    try {
      dirs = readdirSync(root, { withFileTypes: true });
    } catch { continue; }
    for (const d of dirs) {
      if (!d.isDirectory()) continue;
      const f = join(root, d.name, 'SKILL.md');
      if (!existsSync(f)) continue;
      const meta = extractMeta(readHead(f), d.name);
      const key = meta.name;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({ lib: '技能', ...meta, file: f });
    }
  }
  return rows;
}

// —— [资产] 可选资产根（env / config / --base） ——
function scanAssets() {
  const roots = assetRoots();
  if (!roots.length) return [];
  const rows = [];
  const seen = new Set();
  for (const root of roots) {
    if (!existsSync(root)) {
      console.error(`⚠ 资产根不存在，跳过：${root}`);
      continue;
    }
    const files = [];
    walk(root, files);
    for (const f of files) {
      const dirName = basename(dirname(f));
      const meta = f.endsWith('catalog.json')
        ? readCatalog(f)
        : extractMeta(readHead(f), dirName);
      if (!meta || (!meta.name && !meta.desc)) continue;
      const key = `${root}::${meta.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({ lib: basename(root), ...meta, file: f });
    }
  }
  return rows;
}

// catalog.json：数组或 {items|courses:[...]}，字段 title/name/subject/grade/desc
function readCatalog(file) {
  try {
    const data = JSON.parse(readFileSync(file, 'utf8'));
    const arr = Array.isArray(data) ? data : (data.items || data.courses || []);
    const first = arr[0] || {};
    return {
      name: `${basename(dirname(file))}（${arr.length} 条索引）`,
      desc: [first.subject, first.grade, first.desc || first.description].filter(Boolean).join(' · '),
    };
  } catch {
    return null;
  }
}

const skillRows = scanSkills();
const assetRows = scanAssets();
const rows = [...skillRows, ...assetRows];

console.log(`技能根: ${skillRoots().join('  |  ')}`);
if (assetRoots().length) console.log(`资产根: ${assetRoots().join('  |  ')}`);
else console.log('资产根: 未配置（只查已装技能；如需查本地资产库，设 DELIVERY_DESK_ASSETS、config.json 或 --base）');
console.log(`[技能] ${skillRows.length} 个 / [资产] ${assetRows.length} 条 / 可检索能力描述 ${rows.length} 条`);
console.log('⚠ 本脚本只覆盖 ① 与 ③。② 自有站、④ 公共生态（GitHub）必须另查——缺一行，整次查重视为没做。');

if (listOnly) {
  const byLib = new Map();
  for (const r of rows) byLib.set(r.lib, (byLib.get(r.lib) || 0) + 1);
  for (const [lib, n] of [...byLib.entries()].sort()) console.log(`  ${lib.padEnd(22)} ${n}`);
  process.exit(0);
}

const hits = rows.filter((r) => {
  const hay = `${r.name} ${r.desc} ${r.lib}`.toLowerCase();
  return grep.some((k) => expand(k).some((w) => hay.includes(w)));
});

if (hits.length === 0) {
  console.log(`\n关键词 [${grep.join(' / ')}]：0 条命中。`);
  console.log('→ 记入工单该级："查了 <关键词>，无命中"。');
  process.exit(2);
}

const skills = hits.filter((r) => r.lib === '技能');
const assets = hits.filter((r) => r.lib !== '技能');
for (const [label, group] of [['技能（可派活）', skills], ['资产（可查重）', assets]]) {
  if (!group.length) continue;
  console.log(`\n[${label}] ${group.length} 条命中`);
  for (const h of group.slice(0, 20)) {
    const desc = (h.desc || '').replace(/\s+/g, ' ').slice(0, 88);
    console.log(`  ${(h.lib + '/' + h.name).padEnd(44)} ${desc}`);
  }
  if (group.length > 20) console.log(`  …另有 ${group.length - 20} 条，用更细的关键词再筛`);
}

console.log(`\n提示：技能命中 ≠ 已验收能力。派活前打开它的 SKILL.md 看"输入 / 输出 / 边界"，没用过的先出 10 分钟小样。`);
console.log('⚠ 技能命中也不代表查完：② 与 ④ 仍未查，别把这份输出当成查重结果。');
process.exit(0);
