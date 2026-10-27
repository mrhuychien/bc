// Ẩn / hiện mảng báo cáo, chạy giao diện thật: quản trị bật/tắt ở #/an-mang (server chạy vai quản trị) → người
// xem (server vai BC Viewer, CÙNG DB) không thấy menu, không mở được route, API trả 403; quản trị vẫn thấy, có dấu.
// node sections_check.mjs <viewerBase> <adminBase>
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const viewer = process.argv[2] || 'http://127.0.0.1:8124';
const admin = process.argv[3] || 'http://127.0.0.1:8126';
const checks = [];
function check(label, ok, detail = '') {
    checks.push(ok);
    console.log(`  ${ok ? '✓' : '✗'} ${label}${ok ? '' : `  ${String(detail).slice(0, 300)}`}`);
}
const ALL = ['thoi-gian-thuc', 'tong-quan', 'ngay', 'thang', 'tet', 'tinh-thanh', 'san-pham', 'sx-tet', 'van-chuyen',
    'cong-no', 'phai-tra', 'nhan-su', 'attp'];

function watch(page, errors) {
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('favicon.ico')) errors.push(`${r.status()} ${r.url()}`); });
}
async function api(page, base, method, args = {}) {
    const r = await page.request.post(`${base}/api/method/${method}`, { form: args });
    let j = {};
    try { j = await r.json(); } catch { /* */ }
    let server = '';  // Frappe: _server_messages = JSON list các JSON {message} (mã hoá 2 lớp)
    try { server = JSON.parse(j._server_messages || '[]').map((x) => JSON.parse(x).message).join(' '); } catch { /* */ }
    return { status: r.status(), msg: j.message, server, raw: JSON.stringify(j) };
}
const setHidden = (page, keys, hidden) => api(page, admin, 'bc.api.sections.set_hidden', { sections: JSON.stringify(keys), hidden: hidden ? 1 : 0 });

const browser = await chromium.launch();
const eA = [], eV = [];
const A = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage(); watch(A, eA);
const V = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage(); watch(V, eV);

try {
    await setHidden(A, ALL, false);  // trạng thái sạch

    console.log('— Quản trị: #/an-mang');
    await A.goto(`${admin}/bc#/an-mang`);
    await A.waitForSelector('.bc-switch', { timeout: 20000 });
    const n = await A.$$eval('.bc-switch', (els) => els.length);
    const on = await A.$$eval('.bc-switch', (els) => els.filter((e) => e.checked).length);
    check('13 công tắc, đều đang hiện', n === 13 && on === 13, `${n}/${on}`);
    check('menu quản trị có mục Ẩn / hiện mảng', (await A.textContent('#bc-sidebar')).includes('Ẩn / hiện mảng'));

    await A.click('.bc-am-row:has([data-section="cong-no"])');
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang ẩn 1'), null, { timeout: 15000 });
    let g = await api(A, admin, 'bc.api.sections.get_hidden');
    check('bấm công tắc Phải thu → máy chủ lưu ẩn cong-no', JSON.stringify(g.msg?.hidden) === '["cong-no"]', g.raw);
    check('menu quản trị đánh dấu Phải thu "đang ẩn"', await A.$('#bc-sidebar a[data-route="/cong-no"] .bc-side-hidden') !== null
        && await A.$('#bc-sidebar a[data-route="/phai-tra"] .bc-side-hidden') === null);

    await A.click('[data-group="Công nợ"]');  // còn Phải trả đang hiện → "Ẩn cả nhóm"
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang ẩn 2'), null, { timeout: 15000 });
    g = await api(A, admin, 'bc.api.sections.get_hidden');
    check('Ẩn cả nhóm Công nợ', JSON.stringify(g.msg?.hidden) === '["cong-no","phai-tra"]', g.raw);
    await A.click('[data-group="Công nợ"]');  // cả nhóm đang ẩn → "Hiện cả nhóm"
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang hiện tất cả'), null, { timeout: 15000 });
    check('Hiện cả nhóm Công nợ', JSON.stringify((await api(A, admin, 'bc.api.sections.get_hidden')).msg?.hidden) === '[]');

    await A.focus('[data-section="nhan-su"]');
    await A.keyboard.press('Space');  // công tắc dùng được bằng bàn phím
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang ẩn 1'), null, { timeout: 15000 });
    await A.click('.bc-am-row:has([data-section="cong-no"])');
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang ẩn 2'), null, { timeout: 15000 });
    g = await api(A, admin, 'bc.api.sections.get_hidden');
    check('ẩn Nhân sự (phím cách) + Phải thu', JSON.stringify(g.msg?.hidden) === '["cong-no","nhan-su"]', g.raw);

    await A.goto(`${admin}/bc#/cong-no`);
    await A.waitForSelector('#cn-kpis .bc-stat', { timeout: 20000 });
    check('quản trị vẫn mở được mảng đang ẩn', true);

    console.log('— Người xem');
    await V.goto(`${viewer}/bc#/tong-quan`);
    await V.waitForSelector('#bc-sidebar .bc-side-link', { timeout: 20000 });
    const side = await V.textContent('#bc-sidebar');
    check('menu người xem: không Phải thu, còn Phải trả', await V.$('a[data-route="/cong-no"]') === null && await V.$('a[data-route="/phai-tra"]') !== null);
    check('nhóm ẩn hết (Nhân sự) mất hẳn; nhóm chưa làm (Kho) vẫn "Sắp có"', !side.includes('Nhân sự') && side.includes('Kho') && side.includes('Sắp có'),
        side.replace(/\s+/g, ' '));
    check('người xem không thấy dấu "đang ẩn" / mục quản trị', await V.$('.bc-side-hidden') === null && !side.includes('Ẩn / hiện mảng'));

    await V.goto(`${viewer}/bc#/cong-no`);
    await V.waitForFunction(() => location.hash === '#/tong-quan', null, { timeout: 15000 });
    check('gõ thẳng #/cong-no → về trang đầu, có thông báo', (await V.textContent('body')).includes('đang được quản trị ẩn'));
    const r1 = await api(V, viewer, 'bc.api.cn.get_receivables');
    const r2 = await api(V, viewer, 'bc.api.cn.get_payables');
    check('API mảng ẩn trả 403 (đang được quản trị ẩn), mảng còn mở trả 200', r1.status === 403 && r1.server.includes('quản trị ẩn')
        && r2.status === 200, `${r1.status} ${r1.server} ${r2.status}`);

    await setHidden(A, ['tong-quan'], true);
    await V.goto('about:blank');  // mở /bc mới (tab cũ đang ở Tổng quan sẽ nhận 403 khi tự tải — đúng ý, nhưng không phải ca này)
    await V.goto(`${viewer}/bc#/`);
    await V.waitForFunction(() => location.hash === '#/thoi-gian-thuc', null, { timeout: 15000 });
    check('ẩn Tổng quan → trang đầu là màn còn mở đầu tiên (Thời gian thực)', true);

    const M = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
    watch(M, eV);
    await M.goto(`${viewer}/bc#/thoi-gian-thuc`);
    await M.waitForSelector('#bc-bottom-nav .bc-nav-item', { timeout: 20000 });
    const bottom = await M.$$eval('#bc-bottom-nav [data-route]', (els) => els.map((e) => e.dataset.route));
    check('điện thoại: thanh dưới bỏ màn ẩn, bù màn kế tiếp (4 + Thêm)', bottom.length === 5 && !bottom.includes('/tong-quan') && bottom.includes('/ngay'),
        bottom.join(','));
    await M.click('#bc-nav-more');
    const sheet = await M.textContent('.bc-modal, [role="dialog"], body');
    check('điện thoại: sheet "Thêm" không có Phải thu / Nhân sự', !sheet.includes('Phải thu') && !sheet.includes('Nhân sự & lương'));
    await M.close();  // Thời gian thực tự làm mới 60 s — không để chạy tiếp khi ẩn hết bên dưới

    await V.goto(`${viewer}/bc#/phai-tra`);
    await V.waitForSelector('#pt-kpis .bc-stat', { timeout: 20000 });
    await setHidden(A, ['phai-tra'], true);
    await Promise.all([V.waitForNavigation({ timeout: 15000 }), V.click('#bc-btn-refresh')]);
    await V.waitForSelector('#bc-sidebar .bc-side-link', { timeout: 20000 });
    check('quản trị ẩn thêm → người xem bấm Làm mới thì trang tải lại theo danh sách mới',
        await V.$('a[data-route="/phai-tra"]') === null && !(await V.textContent('#bc-sidebar')).includes('Công nợ'));

    await setHidden(A, ALL, true);
    await V.goto('about:blank');
    await V.goto(`${viewer}/bc#/`);
    await V.waitForSelector('.bc-empty-title', { timeout: 15000 });
    check('ẩn hết → người xem thấy "chưa có mảng nào được mở"', (await V.textContent('.bc-empty-title')).includes('Chưa có mảng báo cáo nào'));

    await A.goto(`${admin}/bc#/an-mang`);
    await A.waitForSelector('[data-show-all]:not([disabled])', { timeout: 20000 });
    await A.click('[data-show-all]');
    await A.waitForFunction(() => document.querySelector('#am-count')?.textContent.includes('Đang hiện tất cả'), null, { timeout: 15000 });
    check('Hiện tất cả', JSON.stringify((await api(A, admin, 'bc.api.sections.get_hidden')).msg?.hidden) === '[]');
    await V.goto('about:blank');
    await V.goto(`${viewer}/bc#/tong-quan`);
    await V.waitForSelector('a[data-route="/cong-no"]', { timeout: 20000 });
    check('mở lại → người xem thấy đủ menu', await V.$$eval('#bc-sidebar .bc-side-link', (els) => els.length) === 13);
} catch (e) {
    check('kịch bản chạy hết', false, e.message.split('\n')[0]);
} finally {
    await setHidden(A, ALL, false).catch(() => {});
}
check('quản trị: không lỗi JS/HTTP', eA.length === 0, eA.join(' | '));
check('người xem: không lỗi JS/HTTP', eV.length === 0, eV.join(' | '));
await browser.close();
const bad = checks.filter((x) => !x).length;
console.log(`\n${checks.length - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
