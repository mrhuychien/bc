// Kiểm màn #/kiem-ke (Kiểm kê & điều chỉnh) trên server thử thật: node ui_kho_kk.mjs <baseUrl>
// Desktop 1366px + điện thoại 390px: không lỗi JS / HTTP, không cuộn ngang trang, banner + các khối dựng xong, số trên
// màn = số API (gọi lại API ngay trong trang, định dạng bằng CHÍNH lib/format.js của trang) — không cố định số seed
// (chạy được trên seed gộp của cả nhóm Kho). Đổi tháng → tải lại đúng tháng; nút Làm mới gọi lại API với refresh=1.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const base = process.argv[2] || 'http://127.0.0.1:8133';
const SHOTS = process.env.SHOTS || '';
let n = 0, bad = 0;
function check(label, ok, detail = '') {
    n++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${detail}`); }
}
const flat = (s) => (s || '').replace(/\s+/g, ' ').trim();

/** API + chuỗi định dạng bằng lib/format.js của trang (cùng hàm view dùng). */
async function apiFmt(page, thang) {
    return page.evaluate(async (thang) => {
        const f = await import('/assets/bc/bc/lib/format.js');
        const body = new URLSearchParams(thang ? { thang } : {});
        const res = await fetch('/api/method/bc.api.kho_kk.get_overview', { method: 'POST', body });
        const d = (await res.json()).message;
        const m = (v) => (v === null || v === undefined ? '—' : f.fmtMoney(v));
        const fm = {};
        if (d.available) {
            fm.tong = d.tong.available ? m(d.tong.gia_tri) : '—';
            fm.sx = d.kk_sx.available ? m(d.kk_sx.gt_rong) : '—';
            fm.ch = d.kk_ch.available ? m(d.kk_ch.gt_rong) : '—';
            fm.xk = d.xuat_khac.available ? m(d.xuat_khac.gia_tri) : '—';
            fm.ira = d.ira.available ? f.fmtPct(d.ira.ty_le) : '—';
            if (d.kho.available) fm.chua = f.fmtNum(d.kho.tong.chua_kiem);
            if (d.kho.available && d.kho.rows.length) fm.firstDays = d.kho.rows[0].so_ngay === null ? 'Chưa kiểm kê' : `${f.fmtNum(d.kho.rows[0].so_ngay)} ngày`;
            fm.parts = d.tong.available ? d.tong.parts.map((p) => (p.available ? m(p.gia_tri) : '—')) : [];
            if (d.top_lech.available && d.top_lech.rows.length) fm.top0 = m(d.top_lech.rows[0].value);
            fm.from = f.fmtDate(d.meta.from);
            // Bảng kho trang 1: ngày đang hiện + nguồn của ngày (kho Sản xuất có thể có phiếu kiểm kho mới hơn).
            if (d.kho.available) {
                fm.kho = d.kho.rows.slice(0, 12).map((x) => ({ ngay: x.ngay ? f.fmtDate(x.ngay) : '—',
                    head: x.nguon === 'sr' || x.nguon_ngay === 'sr' ? 'Phiếu kiểm kho' : 'Sản xuất đếm',
                    sub: x.nguon === 'sx' && x.nguon_ngay === 'sr'
                        ? (x.ngay_sx ? `Sản xuất đếm lần cuối ${f.fmtDate(x.ngay_sx)}` : 'Sản xuất chưa đếm lần nào') : '' }));
            }
            // Kiểm kê sx: số lượng thừa / thiếu + quy thùng + phần hộp chưa khai quy cách thùng (cùng cách làm tròn của view).
            if (d.kk_sx.available) {
                const n1 = (v) => (Math.round(v * 10) / 10).toLocaleString('vi-VN');
                // Các dòng nhỏ dưới số tiền: [số lượng, thùng (nếu quy được), +hộp chưa khai thùng (nếu có)].
                const lines = (x) => (x ? [`${n1(x.qty)} ${x.uom || ''}`.trim(), ...(x.cartons ? [`${n1(x.cartons)} thùng`] : []),
                    ...(x.boxes_without_carton_factor ? [`+${n1(x.boxes_without_carton_factor)} ${x.uom || ''} chưa khai thùng`.trim()] : [])] : []);
                fm.sxQty = d.kk_sx.rows.slice(0, 10).map((r) => ({ thua: lines(r.thua), thieu: lines(r.thieu),
                    bw: (r.thua?.boxes_without_carton_factor || 0) + (r.thieu?.boxes_without_carton_factor || 0) }));
            }
        }
        return { d, fm };
    }, thang || null);
}

async function cards(page) {
    return page.$$eval('#kk-kpis .bc-stat', (els) => els.map((e) => ({
        label: e.querySelector('.bc-stat-label').textContent.trim(), value: e.querySelector('.bc-stat-value').textContent.trim() })));
}

async function checkMonth(page, r, tag) {
    const d = r.d;
    const cs = await cards(page);
    const card = (s) => cs.find((c) => c.label.includes(s))?.value;
    check(`${tag}5 thẻ số`, cs.length === 5, JSON.stringify(cs));
    check(`${tag}thẻ tổng điều chỉnh = API (${r.fm.tong})`, card('Tổng điều chỉnh') === r.fm.tong, card('Tổng điều chỉnh'));
    check(`${tag}thẻ kiểm kê sản xuất = API (${r.fm.sx})`, card('kho sản xuất') === r.fm.sx, card('kho sản xuất'));
    check(`${tag}thẻ kiểm kê cửa hàng = API (${r.fm.ch})`, card('cửa hàng') === r.fm.ch, card('cửa hàng'));
    check(`${tag}thẻ xuất huỷ / khác = API (${r.fm.xk})`, card('Xuất huỷ') === r.fm.xk, card('Xuất huỷ'));
    check(`${tag}thẻ độ chính xác = API (${r.fm.ira})`, card('Độ chính xác') === r.fm.ira, card('Độ chính xác'));
    // Bảng điều chỉnh: 4 khoản + dòng tổng, giá trị = API
    if (d.tong.available) {
        const vals = await page.$$eval('#kk-dc tbody tr', (trs) => trs.map((tr) => tr.children[1]?.textContent.trim()));
        check(`${tag}bảng điều chỉnh: 4 khoản + tổng = API (${r.fm.parts.join(' · ')} → ${r.fm.tong})`,
            JSON.stringify(vals) === JSON.stringify([...r.fm.parts, r.fm.tong]), JSON.stringify(vals));
    }
    if (d.kk_sx.available) {
        const sx = flat(await page.textContent('#kk-sx'));
        check(`${tag}kiểm kê sản xuất: ${d.kk_sx.rows.length} lần kiểm như API`, d.kk_sx.rows.length
            ? d.kk_sx.rows.every((x) => sx.includes(x.phieu)) : sx.includes('Không có lần kiểm'), sx.slice(0, 200));
        if (d.kk_sx.rows.length) {
            // Ô Thừa (cột 2) / Thiếu (cột 3): số lượng, thùng và phần hộp chưa khai quy cách thùng = API.
            const cells = await page.$$eval('#kk-sx tbody tr', (trs) => trs.map((tr) => [...tr.children].map((td) =>
                [...td.querySelectorAll('.bc-muted')].map((e) => e.textContent.replace(/\s+/g, ' ').trim()))));
            const bad = r.fm.sxQty.map((w, i) => {
                const [, thua, thieu] = cells[i] || [];
                return JSON.stringify(thua) === JSON.stringify(w.thua) && JSON.stringify(thieu) === JSON.stringify(w.thieu)
                    ? null : { i, thua, thieu, w };
            }).filter(Boolean);
            const bw = r.fm.sxQty.reduce((a, w) => a + w.bw, 0);
            check(`${tag}kiểm kê sản xuất: số hộp thừa / thiếu, quy thùng${bw ? ' + hộp chưa khai quy cách thùng' : ''} = API`,
                !bad.length, JSON.stringify(bad).slice(0, 400));
        }
    }
    if (d.kk_ch.available) {
        const rows = await page.$$eval('#kk-ch tbody tr', (trs) => trs.length);
        check(`${tag}kiểm kê cửa hàng: ${d.kk_ch.rows.length} kho như API`, d.kk_ch.rows.length ? rows === Math.min(10, d.kk_ch.rows.length)
            : (await page.textContent('#kk-ch')).includes('Không có phiếu kiểm kho'), String(rows));
    }
    if (d.xuat_khac.available) {
        const xk = flat(await page.textContent('#kk-xk'));
        check(`${tag}xuất khác: đủ ${d.xuat_khac.rows.length} loại phiếu`, d.xuat_khac.rows.length
            ? d.xuat_khac.rows.every((x) => xk.includes(x.label)) : xk.includes('Không có phiếu xuất huỷ'), xk.slice(0, 200));
    }
    if (d.top_lech.available) {
        const tp = flat(await page.textContent('#kk-top'));
        if (d.top_lech.rows.length) {
            const first = flat(await page.textContent('#kk-top tbody tr'));
            check(`${tag}top chênh lệch: ${d.top_lech.rows.length} dòng, dòng đầu ${d.top_lech.rows[0].item_code} ${r.fm.top0}`,
                tp.includes(`${d.top_lech.rows.length} dòng`) && first.includes(d.top_lech.rows[0].item_code) && first.includes(r.fm.top0), first);
        } else {
            check(`${tag}top chênh lệch rỗng có lời nhắn`, tp.includes('Không có mã nào lệch'), tp.slice(0, 120));
        }
    }
}

async function scenario(page) {
    await page.waitForSelector('.bc-view-banner', { timeout: 15000 });
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
    const banner = flat(await page.textContent('.bc-view-banner'));
    check('banner: tiêu đề + mô tả', banner.includes('Kiểm kê & điều chỉnh') && banner.includes('lâu chưa kiểm'), banner);
    const main = flat(await page.textContent('.bc-main'));
    check('không hiện lỗi tải', !main.includes('Không tải được'), main.slice(0, 200));
    const r = await apiFmt(page);
    const d = r.d;
    check('API trả dữ liệu', d && d.available === true, JSON.stringify(d).slice(0, 200));
    if (!d || !d.available) return;
    const filt = flat(await page.textContent('#kk-filter'));
    check(`ô chọn tháng + kỳ (từ ${r.fm.from})`, filt.includes(`Từ ${r.fm.from}`)
        && await page.$eval('#kk-thang', (e) => e.value) === d.meta.thang, filt);
    await checkMonth(page, r, '');

    // K9: bảng kho
    if (d.kho.available) {
        const kt = flat(await page.textContent('#kk-kho'));
        check(`bảng kho: ${d.kho.rows.length} kho như API, "chưa kiểm kê lần nào" = ${r.fm.chua}`, kt.includes(`${d.kho.rows.length} dòng`)
            && new RegExp(`Chưa kiểm kê lần nào\\s*${r.fm.chua}\\b`).test(kt), kt.slice(0, 300));
        if (d.kho.rows.length) {
            const first = flat(await page.textContent('#kk-kho tbody tr'));
            check(`bảng kho: dòng đầu ${d.kho.rows[0].label} — ${r.fm.firstDays}`, first.includes(d.kho.rows[0].label)
                && first.includes(r.fm.firstDays), first);
            const page1 = d.kho.rows.slice(0, 12);
            const want = { danger: page1.filter((x) => x.muc === 'chua' || x.muc === 'nguy').length,
                warning: page1.filter((x) => x.muc === 'canh_bao').length, success: page1.filter((x) => x.muc === 'ok').length };
            const got = await page.$$eval('#kk-kho tbody tr', (trs) => {
                const o = { danger: 0, warning: 0, success: 0 };
                trs.forEach((tr) => { const b = tr.children[1]?.querySelector('.bc-badge'); if (!b) return;
                    for (const k of Object.keys(o)) if (b.classList.contains(`bc-badge-${k}`)) o[k]++; });
                return o;
            });
            check(`bảng kho: màu mức (đỏ ${want.danger} · vàng ${want.warning} · xanh ${want.success}) theo API`,
                JSON.stringify(got) === JSON.stringify(want), JSON.stringify(got));
            const cells = await page.$$eval('#kk-kho tbody tr', (trs) => trs.map((tr) => ({
                ngay: tr.children[2]?.textContent.replace(/\s+/g, ' ').trim(),
                cach: tr.children[3]?.textContent.replace(/\s+/g, ' ').trim() })));
            const bad = r.fm.kho.map((w, i) => {
                const g = cells[i] || {};
                return g.ngay === w.ngay && (g.cach || '').startsWith(w.head) && (!w.sub || g.cach.includes(w.sub)) ? null : { i, g, w };
            }).filter(Boolean);
            const nSr = r.fm.kho.filter((w) => w.sub).length;
            check(`bảng kho: ngày kiểm + cách kiểm từng dòng = API (${nSr} kho Sản xuất có phiếu kiểm kho mới hơn lần đếm của Sản xuất)`,
                cells.length === r.fm.kho.length && !bad.length, JSON.stringify(bad).slice(0, 400));
        }
    }
    if (d.dang_dem.available) {
        const rows = await page.$$eval('#kk-dang tbody tr', (trs) => trs.map((tr) => tr.textContent.replace(/\s+/g, ' ').trim()));
        check(`phiếu đang đếm: ${d.dang_dem.rows.length} phiếu như API`, d.dang_dem.rows.length
            ? rows.length === Math.min(10, d.dang_dem.rows.length) && d.dang_dem.rows.slice(0, 10).every((x, i) => rows[i].includes(x.phieu))
            : (await page.textContent('#kk-dang')).includes('Không có phiếu nào đang đếm'), JSON.stringify(rows).slice(0, 300));
    }
    if (d.ira.available && d.ira.rows.length) {
        const ir = await page.$$eval('#kk-ira-list .bc-rank-row', (els) => els.length);
        check(`độ chính xác: ${d.ira.rows.length} dòng lần kiểm`, ir === d.ira.rows.length, String(ir));
    }
    check('không lộ email trên màn', !(await page.textContent('.bc-main')).includes('@'));
    const nav = await page.textContent('body');
    check('menu có Kiểm kê & điều chỉnh', nav.includes('Kiểm kê & điều chỉnh'));

    // Đổi tháng → tháng trước: tải lại đúng tháng, số = API tháng đó; ô chọn giữ focus
    const prev = d.meta.prev;
    const [y, mm] = prev.split('-');
    const waitPrev = page.waitForResponse((x) => x.url().includes('kho_kk.get_overview') && (x.request().postData() || '').includes(`thang=${prev}`),
        { timeout: 20000 });
    await page.focus('#kk-thang');
    await page.selectOption('#kk-thang', prev);
    await waitPrev;
    await page.waitForFunction((t) => (document.querySelector('#kk-filter')?.textContent || '').includes(t)
        && !document.querySelector('.bc-main .bc-skeleton'), `Từ 01/${mm}/${y}`, { timeout: 20000 });
    const rp = await apiFmt(page, prev);
    check(`đổi sang tháng ${mm}/${y}: kỳ hiển thị đúng`, rp.d.meta.thang === prev && await page.$eval('#kk-thang', (e) => e.value) === prev);
    await checkMonth(page, rp, `tháng ${mm}: `);
    check('ô chọn tháng vẫn giữ focus sau khi tải', await page.evaluate(() => document.activeElement?.id === 'kk-thang'));

    // Nút Làm mới của khung: gọi lại API (refresh=1) cho đúng tháng đang chọn
    const wait = page.waitForResponse((x) => x.url().includes('kho_kk.get_overview') && (x.request().postData() || '').includes('refresh=1'),
        { timeout: 20000 });
    await page.click('#bc-btn-refresh');
    const resp = await wait;
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton') && document.querySelectorAll('#kk-kpis .bc-stat').length === 5,
        null, { timeout: 20000 });
    check('Làm mới: gọi lại API (refresh=1) cho tháng đang chọn, dựng lại đủ 5 thẻ', resp.status() === 200
        && (resp.request().postData() || '').includes(`thang=${prev}`), resp.request().postData());
}

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
    await page.goto(`${base}/bc#/kiem-ke`);
    try { await scenario(page); } catch (e) { check('kịch bản chạy hết', false, e.message.split('\n')[0]); }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`không cuộn ngang trang (${overflow}px)`, overflow <= 1);
    check('không lỗi JS/HTTP', errors.length === 0, errors.join(' | '));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/kiem-ke-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    await ctx.close();
}
await browser.close();
console.log(`\n${n - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
