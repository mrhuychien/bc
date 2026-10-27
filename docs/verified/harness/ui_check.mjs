// Kiểm màn /bc thật (import map + view thật + API Python thật trên MariaDB).
// node ui_check.mjs <baseUrl> [routes...]   — bắt pageerror, console error, response >= 400.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const base = process.argv[2] || 'http://127.0.0.1:8124';
const SHOTS = process.env.SHOTS || '';
const checks = [];
let bad = 0;
function check(label, ok, detail = '') {
    checks.push(label);
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${detail}`); }
}

const SCEN = {
    '/tong-quan': async (page) => {
        await page.waitForSelector('#tq-channels .bc-stat', { timeout: 15000 });
        const labels = await page.$$eval('#tq-channels .bc-stat-label', (els) => els.map((e) => e.textContent.trim()));
        check('Tổng quan: có thẻ Showroom', labels.some((l) => l.includes('Showroom')), JSON.stringify(labels));
        check('Tổng quan: 5 thẻ kênh dùng lưới 5 cột', await page.$('#tq-channels .bc-grid-5') !== null);
        const note = await page.textContent('.bc-main');
        check('Tổng quan: ghi chú trước VAT', note.includes('trước VAT'));
    },
    '/sx-tet': async (page) => {
        await page.waitForSelector('.bc-main', { timeout: 15000 });
        await page.waitForTimeout(1500);
        const t = await page.textContent('.bc-main');
        check('SX Tết: không hiện lỗi', !t.includes('Không tải được'), t.slice(0, 200));
    },
    '/thoi-gian-thuc': async (page) => {
        await page.waitForSelector('#lv-kpis .bc-lv-kpis', { timeout: 15000 });
        await page.waitForTimeout(800);
        const t = await page.textContent('#lv-kpis');
        check('Thời gian thực: KPI sản xuất có số', /Sản xuất hôm nay/.test(t), t.slice(0, 300));
        const main = await page.textContent('.bc-main');
        check('Thời gian thực: ghi chú trước VAT', main.includes('trước VAT'));
    },
    '/cong-no': async (page) => {
        await page.waitForSelector('#cn-kpis .bc-stat', { timeout: 15000 });
        const k = await page.textContent('#cn-kpis');
        check('Phải thu: KPI 220 tr', k.includes('220 tr'), k.slice(0, 200));
        const aging = await page.textContent('#cn-aging');
        check('Phải thu: bảng tuổi nợ có NPP, MT, Du lịch', ['NPP', 'MT', 'Du lịch'].every((x) => aging.includes(x)), aging.slice(0, 200));
        await page.waitForFunction(() => document.querySelector('#cn-chart')?.width > 0, null, { timeout: 15000 });
        check('Phải thu: có biểu đồ tuổi nợ', true);
        const mt = await page.textContent('#cn-mt');
        check('Phải thu: MT theo chuỗi Saigon Co.op + cảnh báo trả hàng mồ côi', mt.includes('Saigon Co.op') && mt.includes('chưa gắn hoá đơn gốc'), mt.slice(0, 300));
        const top = await page.textContent('#cn-top');
        check('Phải thu: top quá hạn có NPP-A, không có khách MT', top.includes('NPP-A') && !top.includes('COOP-1'), top.slice(0, 200));
    },
    '/phai-tra': async (page) => {
        await page.waitForSelector('#pt-kpis .bc-stat', { timeout: 15000 });
        const k = await page.textContent('#pt-kpis');
        check('Phải trả: KPI 45 tr, quỹ 580 tr', k.includes('45 tr') && k.includes('580 tr'), k.slice(0, 300));
        const cash = await page.textContent('#pt-cash');
        check('Phải trả: số TK ngân hàng bị che', cash.includes('•••7890') && !cash.includes('0011004567890'), cash);
        const due = await page.textContent('#pt-due');
        check('Phải trả: lịch 14 ngày có NCC Bao bì', due.includes('NCC Bao bì'), due);
    },
    '/attp': async (page) => {
        await page.waitForSelector('.bc-attp-card', { timeout: 20000 });
        const n = await page.$$eval('.bc-attp-card', (els) => els.length);
        check('ATTP: 19 thẻ mảng', n === 19, String(n));
        const red = await page.$$eval('.bc-attp-card.bc-attp-do', (els) => els.length);
        check('ATTP: có thẻ đỏ (sự cố, thu hồi, khiếu nại…)', red >= 3, String(red));
        const first = await page.$eval('.bc-attp-card', (el) => el.className);
        check('ATTP: thẻ đỏ xếp đầu', first.includes('bc-attp-do'), first);
        await page.waitForSelector('#attp-thang', { timeout: 15000 });
        const rows = await page.$$eval('#attp-report table', (t) => t[0]?.querySelectorAll('tbody tr').length || 0);
        check('ATTP: bảng 16 chỉ số', rows === 16, String(rows));
        await page.selectOption('#attp-thang', { index: 2 });
        await page.waitForSelector('#attp-thang', { timeout: 15000 });
        await page.waitForTimeout(500);
        const t = await page.textContent('#attp-report');
        check('ATTP: đổi tháng vẫn hiện bảng', t.includes('Luỹ kế'), t.slice(0, 200));
        const nav = await page.textContent('#bc-sidebar');
        check('Menu: có Phải thu, Phải trả & quỹ, An toàn thực phẩm', ['Phải thu', 'Phải trả & quỹ', 'An toàn thực phẩm'].every((x) => nav.includes(x)));
    },
    '/van-chuyen': async (page) => {
        await page.waitForSelector('#vc-kpis .bc-stat', { timeout: 20000 });
        // Số trên màn phải khớp API (seed gộp có cả hoá đơn của bộ thử khác → không cố định 9 đơn ở đây).
        const api = (thang) => page.evaluate((t) => fetch('/api/method/bc.api.vc.get_overview', { method: 'POST',
            body: new URLSearchParams(t ? { thang: t } : {}) }).then((r) => r.json()).then((j) => j.message), thang);
        const d = await api();
        const k = await page.textContent('#vc-kpis');
        check(`Vận chuyển: KPI khớp API (${d.giao.total} đơn, chờ quá 3 ngày ${d.giao.cho_qua_han.qua_n}, cước 1,3 tr, sự cố mở 3)`,
            new RegExp(`Đơn giao trong tháng\\s*${d.giao.total}\\b`).test(k) && new RegExp(`quá 3 ngày\\s*${d.giao.cho_qua_han.qua_n}\\b`).test(k)
            && k.includes('1,3 tr') && /Sự cố đang mở\s*3/.test(k), k.replace(/\s+/g, ' ').slice(0, 400));
        const g = await page.textContent('#vc-giao');
        check('Vận chuyển: bảng hình thức có Tự vận chuyển, Chưa phân công; giao lần đầu 66,7%',
            g.includes('Tự vận chuyển') && g.includes('Chưa phân công') && g.includes('66,7%'), g.replace(/\s+/g, ' ').slice(0, 300));
        const cu = await page.textContent('#vc-cuoc');
        check('Vận chuyển: cảnh báo trả cước bất thường + điều chỉnh tay', cu.includes('đã huỷ') && cu.includes('Điều chỉnh tay'), cu.slice(0, 300));
        const th = await page.textContent('#vc-thuhoi');
        check('Vận chuyển: thu hồi theo chặng phiếu kiểm', th.includes('Đang kiểm') && th.includes('Đã kiểm hàng') && !th.includes('Hủy tại chỗ'), th.slice(0, 300));
        const xe = await page.textContent('#vc-xe');
        check('Vận chuyển: xe đến hạn có 29C-111.11 quá hạn 7 ngày, không lộ xe ngừng',
            xe.includes('29C-111.11') && xe.includes('quá hạn 7 ngày') && !xe.includes('29C-333.33'), xe.replace(/\s+/g, ' ').slice(0, 300));
        const all = await page.textContent('main');
        check('Vận chuyển: không lộ tên lái xe / khách', !all.includes('Nguyễn Văn Lái') && !all.includes('Khách Bí Mật'));
        await page.selectOption('#vc-thang', '2026-09');
        await page.waitForFunction(() => /Từ 01\/09\/2026/.test(document.querySelector('#vc-filter')?.textContent || ''), null, { timeout: 15000 });
        const d9 = await api('2026-09');
        const k9 = await page.textContent('#vc-kpis');
        check(`Vận chuyển: đổi sang tháng 9 → khớp API (${d9.giao.total} đơn, khác tháng 10)`, d9.giao.total !== d.giao.total
            && new RegExp(`Đơn giao trong tháng\\s*${d9.giao.total}\\b`).test(k9), k9.replace(/\s+/g, ' ').slice(0, 200));
        const nav = await page.textContent('.bc-sidebar, nav, body');
        check('Menu: có nhóm Vận chuyển', nav.includes('Giao hàng & xe'));
    },
};

const routes = process.argv.slice(3).length ? process.argv.slice(3) : Object.keys(SCEN);
const browser = await chromium.launch();
for (const mobile of [false, true]) {
    const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
        : { viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('favicon.ico')) errors.push(`${r.status()} ${r.url()}`); });
    console.log(mobile ? '\n— Điện thoại 390px' : '— Desktop 1366px');
    for (const r of routes) {
        errors.length = 0;
        await page.goto(`${base}/bc#${r}`);
        try { await (SCEN[r] || (async (p) => { await p.waitForTimeout(2000); }))(page); }
        catch (e) { check(`${r}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        check(`${r}: không cuộn ngang trang (${overflow}px)`, overflow <= 1);
        check(`${r}: không lỗi JS/HTTP`, errors.length === 0, errors.join(' | '));
        if (SHOTS) await page.screenshot({ path: `${SHOTS}/${r.slice(1)}-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    }
    await ctx.close();
}
await browser.close();
console.log(`\n${checks.length - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
