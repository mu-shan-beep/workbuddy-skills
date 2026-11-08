import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const source = fileURLToPath(new URL('../assets/anatomy/', import.meta.url));
const work = mkdtempSync(join(tmpdir(), 'teachable-figures-'));
cpSync(source, work, { recursive: true });
test.after(() => rmSync(work, { recursive: true, force: true }));

for (const example of ['desk-computer', 'dial-indicator', 'arcade-cabinet', 'raptor-engine', 'ripple-tank', 'turning-dial']) {
  for (const light of [false, true]) {
    test(`${example} builds a self-contained ${light ? 'light' : 'dark'} page`, () => {
      const dir = join(work, 'examples', example);
      const result = spawnSync(process.execPath, ['build.mjs', ...(light ? ['--light'] : [])], { cwd: dir, encoding: 'utf8', timeout: 120000 });
      assert.equal(result.status, 0, result.stdout + result.stderr);
      const html = readFileSync(join(dir, `${example}${light ? '-light' : ''}.html`), 'utf8');
      assert.match(html, /<svg/);
      assert.match(html, /<script/);
      assert.ok(!/<(?:script|link)[^>]+(?:src|href)=["']https?:/i.test(html), 'page must work offline');
    });
  }
}
