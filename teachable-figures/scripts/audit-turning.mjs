import { cpSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const work = mkdtempSync(join(tmpdir(), 'teachable-turning-audit-'));
try {
  cpSync(fileURLToPath(new URL('../assets/anatomy/', import.meta.url)), work, { recursive: true });
  const result = spawnSync(process.execPath, [join(work, 'examples/turning-dial/build.mjs'), '--audit', ...process.argv.slice(2)], { stdio: 'inherit' });
  if (result.error) console.error(result.error);
  process.exitCode = result.status ?? 1;
} finally {
  rmSync(work, { recursive: true, force: true });
}
