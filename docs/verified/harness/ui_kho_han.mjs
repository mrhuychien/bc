// Kiểm màn #/han-dung (Hạn dùng & tồn âm) trên server thử thật: node ui_kho_han.mjs <baseUrl>
// Desktop 1366px + điện thoại 390px: không lỗi JS / HTTP, không cuộn ngang trang, banner + các khối dựng xong, số trên
// màn = số API (gọi lại API ngay trong trang, định dạng bằng CHÍNH lib/format.js của trang) — không cố định số seed
// (chạy được trên seed gộp của cả nhóm Kho, seed lẫn đơn vị Hộp + Kg, seed thiếu bảng lô).
// So từng Ô của MỌI trang các bảng (lô hết hạn / cận date, chưa rõ hạn, kho trả về, lô thu hồi, tồn âm, tách tồn âm),
// từng ô số của "không bán được" và "chưa rõ hạn", dòng đối chiếu tồn kho, số lô / thùng / số lượng của các nhóm hạn.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const base = process.argv[2] || 'http://127.0.0.1:8132';
const SHOTS = process.env.SHOTS || '';
let n = 0, bad = 0;
function check(label, ok, detail = '') {
    n++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 600)}`); }
}
const flat = (s) => (s || '').replace(/\s+/g, ' ').trim();
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const firstDiff = (a, b) => {
    for (let i = 0; i < Math.max(a.length, b.length); i++) if (!same(a[i], b[i])) return `#${i}: ${JSON.stringify(a[i])} ≠ ${JSON.stringify(b[i])}`;
    return '';
};

/** Ô của MỌI trang của bảng thứ `idx` trong `sel` (bấm "Sau ›" đến hết; textContent đã gộp khoảng trắng). */
async function allRows(page, sel, idx = 0) {
    const out = [];
    for (let guard = 0; guard < 60; guard++) {
        const wrap = (await page.$$(`${sel} [data-dt]`))[idx];
        if (!wrap) return null;
        out.push(...await wrap.$$eval('tbody tr', (trs) => trs.map((tr) => [...tr.querySelectorAll('td')]
            .map((td) => td.textContent.replace(/\s+/g, ' ').trim()))));
        const next = await wrap.$('.bc-pager-btn[data-dir="1"]:not([disabled])');
        if (!next) break;
        await next.click();
    }
    return out;
}

async function scenario(page) {
    await page.waitForSelector('.bc-view-banner', { timeout: 15000 });
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
    const banner = flat(await page.textContent('.bc-view-banner'));
    check('banner: tiêu đề + mô tả', banner.includes('Hạn dùng & tồn âm') && banner.includes('không bán được'), banner);
    const main = flat(await page.textContent('.bc-main'));
    check('không hiện lỗi tải', !main.includes('Không tải được'), main.slice(0, 200));
    check('không có "số thùng âm" trên màn (phần âm không quy thùng)', !/-\s?[\d.,]+ thùng/.test(main), (main.match(/.{30}-\s?[\d.,]+ thùng/) || [''])[0]);

    // API + kết quả kỳ vọng từng ô, định dạng bằng lib/format.js của trang (số liệu lấy từ API, không từ seed)
    const r = await page.evaluate(async () => {
        const f = await import('/assets/bc/bc/lib/format.js');
        const res = await fetch('/api/method/bc.api.kho_han.get_overview', { method: 'POST', body: new URLSearchParams({}) });
        const d = (await res.json()).message;
        const QTY = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
        const CT = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
        const CT2 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
        const m = (v) => f.fmtMoney(v);
        const q = (v, u) => `${QTY.format(Number(v))} ${u || ''}`.trim();
        const one = (qq, u, ct, bw) => {   // "40 Hộp · 2,3 thùng (+10 chưa khai thùng)"
            let s = q(qq, u);
            if (ct !== null && ct !== undefined && Number(qq) > 0) {
                if (ct) s += ` · ${CT.format(ct)} thùng`;
                if (bw > 0) s += ` (+${QTY.format(bw)} chưa khai thùng)`;
            }
            return s;
        };
        const qtyText = (x, uom) => (x.qty === null || x.qty === undefined
            ? (x.theo_dvt || []).map((p) => one(p.qty, p.uom, p.cartons, p.boxes_without_carton_factor))
                .join((x.theo_dvt || []).some((p) => p.qty < 0) ? ', ' : ' + ') || 'nhiều đơn vị'
            : one(x.qty, x.uom || uom, x.cartons, x.boxes_without_carton_factor));
        const con = (nn) => (nn < 0 ? `Quá ${f.fmtNum(-nn)} ngày` : nn === 0 ? 'Hết hạn hôm nay' : `Còn ${f.fmtNum(nn)} ngày`);
        const item = (x) => `${x.short_name || x.item_code}${x.item_code}`;
        const LOAI = { toncu: 'Lô tồn cũ', lo_khong_hsd: 'Lô chưa ghi hạn', khong_lo: 'Chưa gắn lô', chua_quan_ly_lo: 'Mã không theo lô' };
        const partVal = (p) => (p.available ? m(p.value) : p.error ? 'chưa tính được' : 'chưa có');
        const sorted = (rows, key, dir) => {   // sắp như data-table (ổn định), mọi trang
            const s = rows.slice();
            s.sort((a, b) => ((a[key] ?? -Infinity) - (b[key] ?? -Infinity)) * (dir === 'asc' ? 1 : -1));
            return s;
        };
        const out = { d, fm: {} };
        if (!d.available) return out;
        const h = d.han, k = d.khong_ban, a = d.am;
        if (h.available) {
            const hh = h.buckets.find((b) => b.key === 'het_han');
            out.fm.het_han = m(hh.value);
            out.fm.het_han_lots = f.fmtNum(hh.lots);
            out.fm.can_date = m(h.can_date.value);
            out.fm.can_date_lots = f.fmtNum(h.can_date.lots);
            out.fm.chua_ro = m(h.chua_ro.value);
            const sl = [...h.buckets, h.chua_ro];
            out.fm.buckets = sl.map((b) => ({ v: m(b.value), p: f.fmtPct(b.pct),
                sub: `${qtyText(b, h.uom)}${b.lots ? ` · ${f.fmtNum(b.lots)} lô` : ''}` }));
            out.fm.ton_kho = m(h.doi_chieu.ton_kho_value);
            out.fm.doi_chieu = (h.doi_chieu.theo_dvt || []).map((x) => {
                let s = `${q(x.duong, x.uom)} (các nhóm hạn dùng)`;
                if (x.thu_hoi) s += ` + ${q(x.thu_hoi, x.uom)} lô đang thu hồi`;
                if (x.am) s += ` − ${q(Math.abs(x.am), x.uom)} phần âm`;
                return `${s} = ${q(x.ton_kho, x.uom)}`;
            }).join('; ');
            out.fm.tong_line = `Tổng các nhóm hạn dùng (phần dương): ${qtyText(h.tong, h.uom)}, ${m(h.tong.value)}.`;
            out.fm.lots = sorted(h.lo_can_date, 'con_ngay', 'asc').map((x) => [item(x), con(x.con_ngay), m(x.value),
                q(x.qty, x.uom), x.cartons === null || x.cartons === undefined ? '—' : CT2.format(x.cartons), f.fmtDate(x.hsd), x.lo, x.kho]);
            out.fm.cr_parts = h.chua_ro.parts.map((p) => [p.label, m(p.value), qtyText(p, h.uom)]);
            out.fm.cr_rows = sorted(h.chua_ro_ds, 'value', 'desc').map((x) => [item(x), m(x.value), q(x.qty, x.uom), LOAI[x.loai] || x.loai,
                x.lo || '—', x.kho, x.hsd_uoc_tinh ? f.fmtDate(x.hsd_uoc_tinh) : '—']);
        }
        if (k.available) {
            out.fm.khong_ban = m(k.tong);
            out.fm.kb_parts = [...k.parts.map((p) => [p.label, partVal(p)]), [k.day_du ? 'Tổng' : 'Tổng (chưa đủ)', m(k.tong)]];
            out.fm.kb_card_rows = k.parts.map((p) => [p.label, partVal(p)]);
            out.fm.kb_rows = sorted(k.kho_loai.ds, 'value', 'desc').map((x) => [item(x), m(x.value), q(x.qty, x.uom), x.kho,
                x.tuoi_ngay === null || x.tuoi_ngay === undefined ? '—' : `${f.fmtNum(x.tuoi_ngay)} ngày`]);
            if (k.thu_hoi.available) out.fm.th_rows = sorted(k.thu_hoi.ds, 'value', 'desc').map((x) => [item(x), m(x.value), q(x.qty, x.uom), x.lo, x.kho]);
        }
        if (a.available) {
            out.fm.am_rows = f.fmtNum(a.rows);
            out.fm.am_value = m(a.value_abs);
            out.fm.am_split = a.split.map((x) => [x.label, m(x.value_abs), f.fmtNum(x.rows), f.fmtNum(x.items)]);
            out.fm.am_ds = sorted(a.ds, 'value_abs', 'desc').map((x) => [item(x), x.co_gia_von ? m(x.value_abs) : 'chưa có giá vốn',
                q(x.qty, x.uom), x.kho]);
        }
        return out;
    });
    const d = r.d, fm = r.fm;
    check('API trả dữ liệu', d && d.available === true, JSON.stringify(d).slice(0, 200));
    if (!d || !d.available) return;
    const k = flat(await page.textContent('#hd-kpis'));
    const cards = await page.$$eval('#hd-kpis .bc-stat', (els) => els.map((e) => ({
        label: e.querySelector('.bc-stat-label').textContent.trim(), value: e.querySelector('.bc-stat-value').textContent.trim(),
        rows: [...e.querySelectorAll('.bc-stat-row')].map((x) => [x.querySelector('span').textContent.trim(), x.querySelector('b').textContent.replace(/\s+/g, ' ').trim()]) })));
    check('5 thẻ số', cards.length === 5, JSON.stringify(cards));
    const card = (s) => cards.find((c) => c.label.includes(s));
    const cardRow = (s, l) => (card(s)?.rows.find((x) => x[0] === l) || [])[1];
    if (d.han.available) {
        check(`thẻ hết hạn = API (${fm.het_han}, ${fm.het_han_lots} lô)`, card('đã hết hạn')?.value === fm.het_han
            && cardRow('đã hết hạn', 'Số lô') === fm.het_han_lots, JSON.stringify(card('đã hết hạn')));
        check(`thẻ cận date = API (${fm.can_date}, ${fm.can_date_lots} lô, ≤ ${d.han.can_date.ngay} ngày)`, card('Cận date')?.value === fm.can_date
            && cardRow('Cận date', 'Số lô') === fm.can_date_lots && cards.some((c) => c.label.includes(`≤ ${d.han.can_date.ngay} ngày`)),
            JSON.stringify(card('Cận date')));
        check(`thẻ chưa rõ hạn = API (${fm.chua_ro})`, card('Chưa rõ hạn')?.value === fm.chua_ro, card('Chưa rõ hạn')?.value);
        const empty = !d.han.tong.rows && !d.han.phan_am.rows && !d.han.thu_hoi.rows;
        const b = flat(await page.textContent('#hd-buckets'));
        if (empty) {
            check('không có tồn thành phẩm: khối hạn dùng báo trống', b.includes('Không có tồn thành phẩm'), b.slice(0, 200));
        } else {
            const rows = await page.$$eval('#hd-buckets .bc-rank-row', (els) => els.map((e) => ({
                v: e.querySelector('.bc-right').textContent.trim(), p: e.querySelector('.bc-rank-bar b').textContent.trim(),
                sub: e.querySelector('.bc-muted.bc-text-sm').textContent.replace(/\s+/g, ' ').trim() })));
            check('dải hạn dùng: 5 nhóm + chưa rõ — giá trị, %, số lượng / thùng / số lô = API', same(rows, fm.buckets), firstDiff(rows, fm.buckets));
            check('dòng tổng ghi rõ "phần dương" và = API', b.includes(fm.tong_line), `${fm.tong_line} | ${b.slice(0, 400)}`);
            if (d.han.doi_chieu.khop) {
                const dc = flat(await page.textContent('#hd-doichieu'));
                check(`đối chiếu: phép cộng tường minh = API (${fm.doi_chieu})`, dc.includes('Khớp tồn kho') && dc.includes(fm.doi_chieu)
                    && dc.includes(fm.ton_kho), dc);
            } else {
                check('đối chiếu: báo chưa khớp', b.includes('chưa khớp'), b.slice(-300));
            }
        }
        const lots = d.han.lo_can_date;
        const lt = flat(await page.textContent('#hd-lots'));
        if (lots.length) {
            check(`bảng lô hết hạn / cận date: ${lots.length} dòng như API`, lt.includes(`${lots.length} dòng`), lt.slice(0, 120));
            const got = await allRows(page, '#hd-lots');
            check(`bảng lô: từng ô mọi trang (${fm.lots.length} dòng: sản phẩm, còn ngày, giá trị, số lượng, thùng, hạn dùng, lô, kho) = API`,
                same(got, fm.lots), firstDiff(got || [], fm.lots));
        } else {
            check('bảng lô rỗng có lời nhắn', lt.includes('Không có lô'), lt);
        }
        const crParts = await page.$$eval('#hd-chuaro .bc-kpi', (els) => els.map((e) => [e.querySelector('.bc-kpi-label').textContent.trim(),
            e.querySelector('.bc-kpi-value').textContent.trim(), (e.querySelector('.bc-kpi-sub')?.textContent || '').replace(/\s+/g, ' ').trim()]));
        check('chưa rõ hạn: 4 phần — tên, giá trị, số lượng = API', same(crParts, fm.cr_parts), firstDiff(crParts, fm.cr_parts));
        const cr = flat(await page.textContent('#hd-chuaro'));
        if (d.han.chua_ro_ds.length) {
            check(`chưa rõ hạn: ${d.han.chua_ro_ds.length} dòng như API`, cr.includes(`${d.han.chua_ro_ds.length} dòng`), cr.slice(0, 300));
            const got = await allRows(page, '#hd-chuaro');
            check('chưa rõ hạn: từng ô mọi trang (sản phẩm, giá trị, số lượng, loại, lô, kho, hạn ước tính) = API', same(got, fm.cr_rows),
                firstDiff(got || [], fm.cr_rows));
        }
    }
    if (d.khong_ban.available) {
        const kb = d.khong_ban;
        check(`thẻ không bán được = API (${fm.khong_ban}), từng phần đúng (lỗi ≠ chưa có)`, card('không bán được')?.value === fm.khong_ban
            && same(card('không bán được').rows.slice(0, 3), fm.kb_card_rows), JSON.stringify(card('không bán được')));
        if (!kb.day_du) check('thẻ không bán được: báo tổng chưa đủ', cardRow('không bán được', 'Lưu ý') === 'tổng chưa đủ các phần');
        const parts = await page.$$eval('#hd-khongban .bc-kpi', (els) => els.map((e) => [e.querySelector('.bc-kpi-label').textContent.trim(),
            e.querySelector('.bc-kpi-value').textContent.trim()]));
        check('khối không bán được: 3 phần + tổng — giá trị từng ô = API', same(parts, fm.kb_parts), firstDiff(parts, fm.kb_parts));
        const kt = flat(await page.textContent('#hd-khongban'));
        if (kb.kho_loai.ds.length) {
            const g0 = await allRows(page, '#hd-khongban', 0);
            check('kho trả về / cách ly: từng ô mọi trang (sản phẩm, giá trị, số lượng, kho, nằm kho) = API', same(g0, fm.kb_rows),
                firstDiff(g0 || [], fm.kb_rows));
        }
        if (fm.th_rows && fm.th_rows.length) {
            const g1 = await allRows(page, '#hd-khongban', kb.kho_loai.ds.length ? 1 : 0);
            check('lô thu hồi: từng ô mọi trang = API', same(g1, fm.th_rows), firstDiff(g1 || [], fm.th_rows));
        }
        if (kb.thu_hoi.error) check('lô thu hồi lỗi: báo "chưa tính được", không nói "chưa có đánh dấu"', kt.includes('Chưa tính được lô đang thu hồi')
            && !kt.includes('chưa có đánh dấu'), kt.slice(-300));
        else if (!kb.thu_hoi.available) check('site chưa có cột thu hồi: báo chưa có đánh dấu', kt.includes('chưa có đánh dấu lô thu hồi'), kt.slice(-300));
    }
    if (d.am.available) {
        check(`thẻ tồn âm = API (${fm.am_rows} dòng, ${fm.am_value})`, card('Tồn âm')?.value === `${fm.am_rows} dòng` && k.includes(fm.am_value),
            `${card('Tồn âm')?.value} | ${k.slice(-200)}`);
        const am = flat(await page.textContent('#hd-am'));
        if (d.am.rows || d.am.lo.lo_am || d.am.lo.khong_lo) {
            const g0 = await allRows(page, '#hd-am', 0);
            check('tách tồn âm: từng ô (nhóm, giá trị, dòng, mã) = API', same(g0, fm.am_split), firstDiff(g0 || [], fm.am_split));
            if (d.am.ds.length) {
                check(`bảng tồn âm ${d.am.ds.length} dòng như API`, am.includes(`${d.am.ds.length} dòng`), am.slice(0, 200));
                const g1 = await allRows(page, '#hd-am', 1);
                check('bảng tồn âm: từng ô mọi trang (sản phẩm, giá trị / chưa có giá vốn, số lượng, kho) = API', same(g1, fm.am_ds),
                    firstDiff(g1 || [], fm.am_ds));
            }
        } else {
            check('không có tồn âm: báo trống', am.includes('Không có tồn âm'), am.slice(0, 200));
        }
    }
    check('không lộ email trên màn', !main.includes('@') && !(await page.textContent('.bc-main')).includes('@'));
    const nav = await page.textContent('body');
    check('menu có Hạn dùng & tồn âm', nav.includes('Hạn dùng & tồn âm'));

    // Nút Làm mới của khung: gọi lại API với refresh=1, dựng lại đủ thẻ
    const wait = page.waitForResponse((x) => x.url().includes('kho_han.get_overview') && (x.request().postData() || '').includes('refresh=1'),
        { timeout: 20000 });
    await page.click('#bc-btn-refresh');
    const resp = await wait;
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton') && document.querySelectorAll('#hd-kpis .bc-stat').length === 5,
        null, { timeout: 20000 });
    check('Làm mới: gọi lại API (refresh=1), dựng lại đủ 5 thẻ', resp.status() === 200);
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
    await page.goto(`${base}/bc#/han-dung`);
    try { await scenario(page); } catch (e) { check('kịch bản chạy hết', false, e.message.split('\n')[0]); }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`không cuộn ngang trang (${overflow}px)`, overflow <= 1);
    check('không lỗi JS/HTTP', errors.length === 0, errors.join(' | '));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/han-dung-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    await ctx.close();
}
await browser.close();
console.log(`\n${n - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
