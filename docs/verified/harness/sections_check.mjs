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
const hiddenNow = async (page) => JSON.stringify((await api(page, admin, 'bc.api.sections.get_hidden')).msg?.hidden);
const fresh = async (page, url) => { await page.goto('about:blank'); await page.goto(url); };  // mở /bc mới hẳn
const countIs = (page, text) => page.waitForFunction((t) => document.querySelector('#am-count')?.textContent.includes(t), text, { timeout: 15000 });

/** Bấm Làm mới, đếm: tải lại trang (document) và các lời gọi kd.* / cn.* có refresh=1 hay không. */
async function pressRefresh(page, expectReload) {
    let docs = 0; const posts = [];
    const onReq = (r) => {
        if (r.resourceType() === 'document') docs++;
        if (r.method() === 'POST' && /\/api\/method\/bc\.api\.(kd|cn)\./.test(r.url())) posts.push(r.postData() || '');
    };
    page.on('request', onReq);
    const click = page.click('#bc-btn-refresh');
    if (expectReload) await Promise.all([page.waitForNavigation({ timeout: 15000 }), click]); else await click;
    await page.waitForResponse((r) => /\/api\/method\/bc\.api\.(kd|cn)\./.test(r.url()), { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(800);
    page.off('request', onReq);
    return { docs, posts };
}
const allRefresh = (posts) => posts.length > 0 && posts.every((p) => /(^|&)refresh=1(&|$)/.test(p));

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
    await countIs(A, 'Đang ẩn 1');
    check('bấm công tắc Phải thu → máy chủ lưu ẩn cong-no', await hiddenNow(A) === '["cong-no"]');
    check('menu quản trị đánh dấu Phải thu "đang ẩn"', await A.$('#bc-sidebar a[data-route="/cong-no"] .bc-side-hidden') !== null
        && await A.$('#bc-sidebar a[data-route="/phai-tra"] .bc-side-hidden') === null);

    await A.click('[data-group="Công nợ"]');  // còn Phải trả đang hiện → "Ẩn cả nhóm"
    await countIs(A, 'Đang ẩn 2');
    check('Ẩn cả nhóm Công nợ', await hiddenNow(A) === '["cong-no","phai-tra"]');
    await A.click('[data-group="Công nợ"]');  // cả nhóm đang ẩn → "Hiện cả nhóm"
    await countIs(A, 'Đang hiện tất cả');
    check('Hiện cả nhóm Công nợ', await hiddenNow(A) === '[]');

    // Mạng chậm: trong lúc chờ máy chủ, công tắc vẽ theo trạng thái ĐÍCH (không nhảy về chỗ cũ), bị khoá.
    await A.route('**/api/method/bc.api.sections.set_hidden', async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });
    await A.click('.bc-am-row:has([data-section="attp"])');
    await A.waitForTimeout(400);
    const mid = await A.$eval('[data-section="attp"]', (el) => ({ checked: el.checked, disabled: el.disabled,
        label: el.closest('.bc-am-row').textContent }));
    check('đang lưu: công tắc ở trạng thái đích ("Đang ẩn…"), khoá tới khi xong', !mid.checked && mid.disabled && mid.label.includes('Đang ẩn…'),
        JSON.stringify(mid));
    await countIs(A, 'Đang ẩn 1');
    await A.waitForFunction(() => !document.querySelector('[data-section="attp"]').disabled, null, { timeout: 15000 });
    await A.unroute('**/api/method/bc.api.sections.set_hidden');
    check('xong: máy chủ đã ẩn attp', await hiddenNow(A) === '["attp"]');
    await setHidden(A, ['attp'], false);
    await A.goto(`${admin}/bc#/tong-quan`);
    await A.goto(`${admin}/bc#/an-mang`);
    await countIs(A, 'Đang hiện tất cả');

    await A.focus('[data-section="nhan-su"]');
    await A.keyboard.press('Space');  // công tắc dùng được bằng bàn phím
    await countIs(A, 'Đang ẩn 1');
    await A.waitForFunction(() => !document.querySelector('[data-section="nhan-su"]').disabled, null, { timeout: 15000 });
    check('bàn phím: sau khi lưu, focus vẫn ở công tắc vừa bấm', await A.evaluate(() => document.activeElement?.dataset?.section) === 'nhan-su',
        await A.evaluate(() => document.activeElement?.outerHTML?.slice(0, 120)));
    await A.click('.bc-am-row:has([data-section="cong-no"])');
    await countIs(A, 'Đang ẩn 2');
    check('ẩn Nhân sự (phím cách) + Phải thu', await hiddenNow(A) === '["cong-no","nhan-su"]');

    await A.goto(`${admin}/bc#/cong-no`);
    await A.waitForSelector('#cn-kpis .bc-stat', { timeout: 20000 });
    check('quản trị vẫn mở được mảng đang ẩn', true);

    console.log('— Người xem');
    await fresh(V, `${viewer}/bc#/tong-quan`);
    await V.waitForSelector('#bc-sidebar .bc-side-link', { timeout: 20000 });
    const side = await V.textContent('#bc-sidebar');
    check('menu người xem: không Phải thu, còn Phải trả', await V.$('a[data-route="/cong-no"]') === null && await V.$('a[data-route="/phai-tra"]') !== null);
    check('nhóm ẩn hết (Nhân sự) mất hẳn; nhóm chưa làm (Kho) vẫn "Sắp có"', !side.includes('Nhân sự') && side.includes('Kho') && side.includes('Sắp có'),
        side.replace(/\s+/g, ' '));
    check('người xem không thấy dấu "đang ẩn" / mục quản trị', await V.$('.bc-side-hidden') === null && !side.includes('Ẩn / hiện mảng'));
    await V.waitForSelector('.bc-stat', { timeout: 20000 });

    const r0 = await pressRefresh(V, false);
    check('Làm mới khi danh sách KHÔNG đổi: không tải lại trang, API gửi refresh=1', r0.docs === 0 && allRefresh(r0.posts),
        `docs=${r0.docs} ${r0.posts.join(' | ')}`);

    await V.goto(`${viewer}/bc#/cong-no`);
    await V.waitForFunction(() => location.hash === '#/tong-quan', null, { timeout: 15000 });
    check('gõ thẳng #/cong-no → về trang đầu, có thông báo', (await V.textContent('body')).includes('đang được quản trị ẩn'));
    const r1 = await api(V, viewer, 'bc.api.cn.get_receivables');
    const r2 = await api(V, viewer, 'bc.api.cn.get_payables');
    check('API mảng ẩn trả 403 (đang được quản trị ẩn), mảng còn mở trả 200', r1.status === 403 && r1.server.includes('quản trị ẩn')
        && r2.status === 200, `${r1.status} ${r1.server} ${r2.status}`);

    // Tab mở từ trước: quản trị mở lại Phải thu → người xem bấm link #/cong-no thì tab tự tải lại 1 lần và vào được.
    await setHidden(A, ['cong-no'], false);
    await Promise.all([V.waitForNavigation({ timeout: 15000 }), V.evaluate(() => { location.hash = '#/cong-no'; })]);
    await V.waitForSelector('#cn-kpis .bc-stat', { timeout: 20000 });
    check('tab cũ: mảng đã mở lại → tự tải lại, vào được Phải thu', (await V.evaluate(() => location.hash)) === '#/cong-no'
        && await V.$('a[data-route="/cong-no"]') !== null);

    // Danh sách THU HẸP (mở lại) cũng làm Làm mới tải lại trang; lượt đầu sau tải lại vẫn gửi refresh=1.
    await setHidden(A, ['nhan-su'], false);
    await V.goto(`${viewer}/bc#/tong-quan`);
    await V.waitForSelector('.bc-stat', { timeout: 20000 });
    const r3 = await pressRefresh(V, true);
    check('Làm mới khi danh sách đổi (mở lại Nhân sự): tải lại trang, menu có lại Nhân sự, lượt đầu vẫn refresh=1',
        r3.docs >= 1 && await V.$('a[data-route="/nhan-su"]') !== null && allRefresh(r3.posts), `docs=${r3.docs} ${r3.posts.join(' | ')}`);

    await setHidden(A, ['tong-quan', 'cong-no', 'nhan-su'], true);
    await fresh(V, `${viewer}/bc#/`);
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

    await fresh(V, `${viewer}/bc#/phai-tra`);
    await V.waitForSelector('#pt-kpis .bc-stat', { timeout: 20000 });
    await setHidden(A, ['phai-tra'], true);
    await Promise.all([V.waitForNavigation({ timeout: 15000 }), V.click('#bc-btn-refresh')]);
    await V.waitForSelector('#bc-sidebar .bc-side-link', { timeout: 20000 });
    check('quản trị ẩn thêm → người xem bấm Làm mới thì trang tải lại theo danh sách mới',
        await V.$('a[data-route="/phai-tra"]') === null && !(await V.textContent('#bc-sidebar')).includes('Công nợ'));

    await setHidden(A, ALL, true);
    await fresh(V, `${viewer}/bc#/`);
    await V.waitForSelector('.bc-empty-title', { timeout: 15000 });
    check('ẩn hết → người xem thấy "chưa có mảng nào được mở"', (await V.textContent('.bc-empty-title')).includes('Chưa có mảng báo cáo nào'));
    await fresh(V, `${viewer}/bc#/cong-no`);
    await V.waitForFunction(() => location.hash === '#/' && document.querySelector('.bc-empty-title'), null, { timeout: 15000 });
    check('ẩn hết + gõ thẳng #/cong-no → về #/ và thấy "chưa có mảng nào được mở"',
        (await V.textContent('.bc-empty-title')).includes('Chưa có mảng báo cáo nào'));

    // "Hiện tất cả" mở cả mảng bị ẩn ở tab khác SAU khi màn quản trị đã mở.
    await setHidden(A, ALL, false);
    await setHidden(A, ['cong-no'], true);
    await A.goto(`${admin}/bc#/tong-quan`);
    await A.goto(`${admin}/bc#/an-mang`);
    await countIs(A, 'Đang ẩn 1');
    await setHidden(A, ['van-chuyen'], true);  // tab khác / Desk
    await A.click('[data-show-all]');
    await countIs(A, 'Đang hiện tất cả');
    check('Hiện tất cả: mở cả mảng ai đó vừa ẩn ở tab khác', await hiddenNow(A) === '[]');
    await fresh(V, `${viewer}/bc#/tong-quan`);
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
