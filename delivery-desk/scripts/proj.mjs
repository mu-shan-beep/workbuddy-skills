/* proj.mjs — 投影劣化模拟截图
   用途：判断"浅色面板在教室投影上能不能看清"。
   劣化模型（近似真实教室：开灯 + 投影仪黑位抬升 + 白墙反光）：
     ① contrast .82  —— 投影仪对比度不足，暗部被压缩
     ② brightness 1.07 —— 灯泡把整体提亮
     ③ saturate .88 —— 色域损失
     ④ 半透明白雾 17% —— 环境光打到幕布上
   这不是精确测量，是"给个下限看"：如果这样还能读，实际投影基本没问题。
   用法：node proj.mjs <fileurl> <out.png> [W] [H] [waitMs] [#hash] */
import { chromium } from 'playwright';

const [, , url, out, W = '1600', H = '900', WAIT = '1800', HASH = ''] = process.argv;
if (!url || !out) {
  console.error('usage: node proj.mjs <fileurl> <out.png> [W] [H] [waitMs] [#hash]');
  process.exit(1);
}

const browser = await chromium.launch({
  executablePath: 'C:\\Users\\panUser\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe',
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
});
const page = await browser.newPage({ viewport: { width: +W, height: +H } });
await page.goto(url + HASH, { waitUntil: 'load' });
await page.waitForTimeout(+WAIT);

await page.addStyleTag({
  content: `
    html{ filter: contrast(.82) brightness(1.07) saturate(.88); }
    body::after{
      content:''; position:fixed; inset:0; z-index:99999; pointer-events:none;
      background: rgba(255,252,246,.17);
    }`
});
await page.waitForTimeout(350);
await page.screenshot({ path: out });
await browser.close();
console.log(JSON.stringify({ out, W:+W, H:+H, degraded: true }));
