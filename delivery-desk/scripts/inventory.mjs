#!/usr/bin/env node
/**
 * inventory.mjs —— 现查"今天谁能接活"
 *
 * 用法：
 *   node scripts/inventory.mjs                     # 扫默认两个技能根
 *   node scripts/inventory.mjs <root> [root2 ...]  # 扫指定目录（每个 root 下找 * /SKILL.md）
 *   node scripts/inventory.mjs --json              # 机器可读
 *   node scripts/inventory.mjs --grep 视频          # 只看描述里含关键词的
 *
 * 设计要点：统筹官不背名单。名单由这个脚本每次现算，装了什么就有什么。
 */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const here = path.dirname(url.fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const json = argv.includes('--json');
const gi = argv.indexOf('--grep');
const grep = gi >= 0 ? (argv[gi + 1] || '') : '';
const skipNext = gi >= 0 ? 1 : 0;

let roots = argv.filter((a, i) => !a.startsWith('--') && i !== gi + skipNext);

if (!roots.length) {
  roots = [
    path.resolve(here, '..', '..'),                  // .user_skills（本技能所在根）
    path.resolve(here, '..', '..', '..', '.skills'), // 内置 skills
  ];
}

function readFrontmatter(file) {
  const head = fs.readFileSync(file, 'utf8').slice(0, 6000);
  const m = head.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return null;
  const body = m[1];
  const get = (k) => {
    const r = body.match(new RegExp('^' + k + ':\\s*([\\s\\S]*?)(?=\\n[a-zA-Z][\\w-]*:|(?![\\s\\S]))', 'm'));
    if (!r) return '';
    let v = r[1].trim();
    if (/^[>|][-+]?$/.test((v.split('\n')[0] || '').trim())) {
      v = v.split('\n').slice(1).join(' ');
    }
    v = v.replace(/^["'\u201c]|["'\u201d]$/g, '');
    return v.replace(/\s+/g, ' ').trim();
  };
  return { name: get('name'), description: get('description') };
}

const rows = [];
const seen = new Map();
const problems = [];

for (const rootRaw of roots) {
  const root = path.resolve(rootRaw);
  if (!fs.existsSync(root)) { problems.push(`目录不存在：${root}`); continue; }
  for (const d of fs.readdirSync(root, { withFileTypes: true })) {
    if (!d.isDirectory()) continue;
    const f = path.join(root, d.name, 'SKILL.md');
    if (!fs.existsSync(f)) continue;
    const fm = readFrontmatter(f);
    if (!fm || !fm.name) { problems.push(`${path.join(root, d.name)} 读不出 frontmatter`); continue; }
    if (seen.has(fm.name)) {
      problems.push(`重名：${fm.name} 同时出现在 ${seen.get(fm.name)} 与 ${root}`);
      continue;
    }
    seen.set(fm.name, root);
    if (!fm.description) problems.push(`${fm.name} 的 description 为空，检索会漏`);
    rows.push({
      name: fm.name,
      dir: d.name,
      root,
      description: fm.description,
    });
  }
}

rows.sort((a, b) => a.name.localeCompare(b.name));
const terms = grep ? grep.split(/\s+/).filter(Boolean) : [];
const hit = terms.length
  ? rows.filter(r => {
      const hay = (r.name + ' ' + r.description).toLowerCase();
      return terms.some(t => hay.includes(t.toLowerCase()));
    })
  : rows;

if (json) {
  console.log(JSON.stringify({ total: hit.length, roots, rows: hit, problems }, null, 2));
} else {
  console.log(`\n当前可派活技能：${hit.length} 个${grep ? `（筛选：${grep}）` : ''}`);
  console.log(`扫描根：${roots.join('  |  ')}\n`);
  console.log('| 技能 | 来源 | 一句话能力 |');
  console.log('|---|---|---|');
  for (const r of hit) {
    const short = (r.description || '（无描述）').replace(/\|/g, '｜').slice(0, 78);
    console.log(`| \`${r.name}\` | ${path.basename(r.root)} | ${short}${r.description.length > 78 ? '…' : ''} |`);
  }
  if (problems.length) {
    console.log('\n需要处理：');
    for (const p of problems) console.log('  - ' + p);
  }
  console.log('');
}
