// Tab mở TRƯỚC deploy: lib/format.js + lib/lunar.js là bản cũ (chưa có salesBasisNote / isTetDay), view là bản mới.
// Server chạy với BC_OLD_PUBLIC=<public/bc của bản cũ>. View phải hiện bình thường (không SyntaxError lúc link).
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8125';
let bad = 0, n = 0;
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
for (const r of ['/tong-quan', '/thang', '/tet', '/ngay', '/sx-tet', '/thoi-gian-thuc']) {
    errors.length = 0;
    await page.goto(`${base}/bc#${r}`);
    await page.waitForTimeout(2500);
    const t = await page.textContent('#bc-view');
    // Phải THẤY view đã vẽ (banner / khối thời gian thực) — trang trắng không được tính là đạt.
    const drawn = await page.$('#bc-view .bc-view-banner, #bc-view .bc-lv-hero') !== null;
    const ok = drawn && !t.includes('Lỗi tải trang') && !errors.some((e) => /export named|binding name|import not found/i.test(e));
    n++; if (!ok) bad++;
    console.log(ok ? '  ✓' : '  ✗', `tab cũ mở ${r}`, ok ? '' : (errors.join(' | ') || t.slice(0, 120)));
}
await browser.close();
console.log(`${n - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
