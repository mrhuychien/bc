// Kiểm màn #/kiem-ke (Kiểm kê & điều chỉnh) trên server thử thật: node ui_kho_kk.mjs <baseUrl>
// Desktop 1366px + điện thoại 390px: không lỗi JS / HTTP, không cuộn ngang trang, banner + các khối dựng xong, số trên
// màn = số API (gọi lại API ngay trong trang, định dạng bằng CHÍNH lib/format.js của trang) — không cố định số seed
// (chạy được trên seed gộp của cả nhóm Kho). Đổi tháng → tải lại đúng tháng; nút Làm mới gọi lại API với refresh=1.
// Sau review chéo: thẻ "Kiểm kê sản xuất" có dòng "Ở kho khác khi bật lô" (XC-1); thẻ phiếu kiểm kho không gọi kho khác là
// cửa hàng, tách Cửa hàng / Kho khác (UX-1); tổng thiếu khoản nào nói đúng khoản đó, không hiện số như đủ, dòng ghi chú
// không bị cắt (UX-2 — payload giả lập lỗi / không sx, dựng theo đúng luật _tong của máy chủ); bảng kho ghi "hiện tại / đến
// hôm nay", độ chính xác ghi ngày lần kiểm và theo tháng chọn, cột độ chính xác bảng kho là của hôm nay (UX-5); ô đầu các
// bảng không bị cắt chữ (UX-7) — kể cả khi khối không có số (không app Sản xuất, thiếu cột liên kết, thiếu bảng / lỗi phiếu
// kiểm kho: lời giải thích trong bảng điều chỉnh xuống dòng, không cụt); khối phiếu kiểm kho không có số cũng không gọi là
// "kiểm kê cửa hàng" (UX-1).
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
            // Tổng thiếu khoản thật (không tính khoản "không áp dụng") → thẻ không đưa con số như thể đủ.
            fm.thieu = d.tong.available ? d.tong.parts.filter((p) => !p.available && (d.tong.thieu || []).includes(p.key)).map((p) => p.label) : [];
            fm.tong = d.tong.available && !fm.thieu.length ? m(d.tong.gia_tri) : '—';
            fm.tongPartial = d.tong.available ? m(d.tong.gia_tri) : '—';
            fm.sx = d.kk_sx.available ? m(d.kk_sx.gt_rong) : '—';
            fm.sxKhac = d.kk_sx.available && d.kk_sx.gt_kho_khac ? m(d.kk_sx.gt_kho_khac) : null;
            fm.ch = d.kk_ch.available ? m(d.kk_ch.gt_rong) : '—';
            fm.chCua = d.kk_ch.available ? m(d.kk_ch.cua_hang?.gt_rong) : '—';
            fm.chKhac = d.kk_ch.available ? m(d.kk_ch.kho_khac?.gt_rong) : '—';
            fm.iraNgay = d.ira.available ? f.fmtDate(d.ira.ngay_moi_nhat) : '—';
            fm.asOf = f.fmtDate(d.meta.as_of);
            // Cột độ chính xác của bảng kho (trang 1) = tỷ lệ HÔM NAY của lần kiểm trên dòng đó.
            const now = (d.ira.available && d.ira.ty_le_hien_tai) || {};
            if (d.kho.available) fm.khoIra = d.kho.rows.slice(0, 12).map((x) => (x.phieu && Object.prototype.hasOwnProperty.call(now, x.phieu)
                ? f.fmtPct(now[x.phieu]) : '—'));
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
        label: e.querySelector('.bc-stat-label').textContent.trim(), value: e.querySelector('.bc-stat-value').textContent.trim(),
        rows: [...e.querySelectorAll('.bc-stat-row')].map((r) => [r.children[0]?.textContent.replace(/\s+/g, ' ').trim(),
            r.children[1]?.textContent.replace(/\s+/g, ' ').trim()]) })));
}

/** Ô đầu các bảng của trang (nhãn + dòng phụ): không ô nào bị cắt chữ (nội dung rộng hơn ô). */
async function clipped(page) {
    return page.$$eval('.bc-main .bc-table tbody td:first-child', (tds) => tds.filter((td) => td.scrollWidth > td.clientWidth + 1)
        .map((td) => `${td.closest('[id^="kk-"]')?.id}: ${td.textContent.replace(/\s+/g, ' ').trim().slice(0, 60)} (${td.scrollWidth}>${td.clientWidth})`));
}

/** Các dòng của thẻ số nằm trọn trong thẻ (thẻ overflow:hidden — tràn là bị cắt). */
async function cardRowsInside(page, labelPart) {
    return page.$$eval('#kk-kpis .bc-stat', (els, lp) => {
        const c = els.find((e) => e.querySelector('.bc-stat-label').textContent.includes(lp));
        if (!c) return ['không thấy thẻ'];
        const right = c.getBoundingClientRect().right;
        return [...c.querySelectorAll('.bc-stat-row > *')].filter((x) => x.getBoundingClientRect().right > right + 0.5
            || x.scrollWidth > x.clientWidth + 1).map((x) => x.textContent.trim().slice(0, 60));
    }, labelPart);
}

async function checkMonth(page, r, tag) {
    const d = r.d;
    const cs = await cards(page);
    const card = (s) => cs.find((c) => c.label.includes(s))?.value;
    const row = (s, l) => cs.find((c) => c.label.includes(s))?.rows.find((x) => x[0] === l)?.[1];
    check(`${tag}5 thẻ số`, cs.length === 5, JSON.stringify(cs));
    check(`${tag}thẻ tổng điều chỉnh = API (${r.fm.tong})`, card('Tổng điều chỉnh') === r.fm.tong, card('Tổng điều chỉnh'));
    check(`${tag}thẻ kiểm kê sản xuất = API (${r.fm.sx})`, card('Kiểm kê sản xuất') === r.fm.sx, card('Kiểm kê sản xuất'));
    if (r.fm.sxKhac) {
        check(`${tag}thẻ kiểm kê sản xuất: dòng "Ở kho khác khi bật lô" = API (${r.fm.sxKhac})`,
            row('Kiểm kê sản xuất', 'Ở kho khác khi bật lô') === r.fm.sxKhac, JSON.stringify(cs.find((c) => c.label.includes('Kiểm kê sản xuất'))?.rows));
    }
    // UX-1: phiếu kiểm kho ở mọi kho — nhãn không gọi là "cửa hàng", tách Cửa hàng / Kho khác.
    check(`${tag}thẻ phiếu kiểm kho (cửa hàng & kho khác) = API (${r.fm.ch}), không thẻ nào tên "Kiểm kê cửa hàng"`,
        card('Phiếu kiểm kho') === r.fm.ch && !cs.some((c) => /Kiểm kê cửa hàng/i.test(c.label)), JSON.stringify(cs.map((c) => c.label)));
    if (d.kk_ch.available) {
        check(`${tag}thẻ phiếu kiểm kho: Cửa hàng ${r.fm.chCua} · Kho khác ${r.fm.chKhac} = API`,
            row('Phiếu kiểm kho', 'Cửa hàng') === r.fm.chCua && row('Phiếu kiểm kho', 'Kho khác') === r.fm.chKhac,
            JSON.stringify(cs.find((c) => c.label.includes('Phiếu kiểm kho'))?.rows));
    }
    check(`${tag}thẻ xuất huỷ / khác = API (${r.fm.xk})`, card('Xuất huỷ') === r.fm.xk, card('Xuất huỷ'));
    check(`${tag}thẻ độ chính xác = API (${r.fm.ira}), ghi ngày lần kiểm mới nhất ${r.fm.iraNgay}`, card('Độ chính xác') === r.fm.ira
        && (!d.ira.available || row('Độ chính xác', 'Lần kiểm mới nhất') === r.fm.iraNgay),
        JSON.stringify(cs.find((c) => c.label.includes('Độ chính xác'))));
    const cut = await clipped(page);
    check(`${tag}ô đầu các bảng không bị cắt chữ (nhãn, dòng kho / số phiếu xuống dòng)`, !cut.length, JSON.stringify(cut).slice(0, 400));
    if (d.kk_sx.available && d.kk_sx.rows.some((x) => x.kho_khac?.length)) {
        const sxt = flat(await page.textContent('#kk-sx'));
        const want = d.kk_sx.rows.flatMap((x) => x.kho_khac || []).map((w) => w.label);
        check(`${tag}kiểm kê sản xuất: dòng "ở kho khác khi bật lô" ghi đủ kho (${want.join(', ')})`,
            sxt.includes('ở kho khác khi bật lô') && want.every((l) => sxt.includes(l)), sxt.slice(0, 300));
    }
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

    // UX-5: phần "hôm nay" ghi rõ — bảng kho, phiếu đang đếm
    const khoNote = flat(await page.textContent('#kk-kho'));
    check(`bảng kho ghi "hiện tại, đến hôm nay ${r.fm.asOf}"`, khoNote.includes('Tình hình hiện tại') && khoNote.includes(`đến hôm nay ${r.fm.asOf}`),
        khoNote.slice(0, 160));
    const dangTitle = flat(await page.$eval('#kk-dang', (e) => e.closest('.bc-card').querySelector('.bc-card-title').textContent));
    check('thẻ phiếu đang đếm ghi "hiện tại"', dangTitle.includes('hiện tại'), dangTitle);
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
    if (rp.d.kho.available && rp.d.kho.rows.length) {
        // Bảng kho luôn là hôm nay: cột độ chính xác lấy tỷ lệ hôm nay của lần kiểm trên dòng, KHÔNG phải tỷ lệ của tháng chọn.
        const col = await page.$$eval('#kk-kho tbody tr', (trs) => trs.map((tr) => tr.children[5]?.textContent.trim()));
        check(`tháng ${mm}: cột độ chính xác bảng kho = tỷ lệ hôm nay (${rp.fm.khoIra.filter((x) => x !== '—').join(' · ')})`,
            JSON.stringify(col) === JSON.stringify(rp.fm.khoIra), JSON.stringify(col));
    }

    // Nút Làm mới của khung: gọi lại API (refresh=1) cho đúng tháng đang chọn
    const wait = page.waitForResponse((x) => x.url().includes('kho_kk.get_overview') && (x.request().postData() || '').includes('refresh=1'),
        { timeout: 20000 });
    await page.click('#bc-btn-refresh');
    const resp = await wait;
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton') && document.querySelectorAll('#kk-kpis .bc-stat').length === 5,
        null, { timeout: 20000 });
    check('Làm mới: gọi lại API (refresh=1) cho tháng đang chọn, dựng lại đủ 5 thẻ', resp.status() === 200
        && (resp.request().postData() || '').includes(`thang=${prev}`), resp.request().postData());

    // UX-2: tổng thiếu đúng khoản nào thì nói khoản đó (payload thật của máy chủ, chỉ tắt khối theo đúng luật _tong).
    // Sau MỖI lần giả lập: ô đầu các bảng không bị cắt (UX-7) — lời giải thích "không có số" trong bảng điều chỉnh là chữ dài
    // nhất của ô (vd. "Không áp dụng: site chưa cài app Sản xuất." 279px trong ô 230px ở 390px trước khi sửa).
    const lx = await degraded(page, 'loi_xuat_khac', { xuat_khac: { available: false, error: true } });
    if (lx) {
        const c0 = (await cards(page)).find((c) => c.label.includes('Tổng điều chỉnh'));
        const txt = JSON.stringify(c0?.rows || []);
        check(`xuất khác lỗi: thẻ tổng không đưa số như đủ (—), "Các khoản đã có ${lx.partial}", "Chưa gồm: ${lx.label}"`,
            c0?.value === '—' && c0.rows.some((x) => x[0] === 'Các khoản đã có' && x[1] === lx.partial)
            && c0.rows.some((x) => x[0] === `Chưa gồm: ${lx.label}`) && !/kiểm kê sản xuất/i.test(txt), JSON.stringify(c0));
        const inside = await cardRowsInside(page, 'Tổng điều chỉnh');
        check('xuất khác lỗi: dòng ghi chú của thẻ tổng không bị cắt', !inside.length, JSON.stringify(inside));
        const dc = flat(await page.textContent('#kk-dc'));
        check('xuất khác lỗi: bảng điều chỉnh ghi "chưa gồm" đúng khoản', dc.includes(`chưa gồm: ${lx.label}`), dc.slice(-300));
        await notClipped(page, 'xuất khác lỗi');
    }
    const ns = await degraded(page, 'khong_sx', { kk_sx: { available: false, reason: 'khong_sx' }, don_sx: { available: false, reason: 'khong_sx' } });
    if (ns) {
        const c0 = (await cards(page)).find((c) => c.label.includes('Tổng điều chỉnh'));
        check(`không app Sản xuất: thẻ tổng là số (${ns.total}), không báo thiếu`, c0?.value === ns.total
            && !/Thiếu số|Chưa gồm/.test(JSON.stringify(c0.rows)), JSON.stringify(c0));
        const dc = flat(await page.textContent('#kk-dc'));
        check('không app Sản xuất: dòng kiểm kê / dọn tồn sản xuất ghi "Không áp dụng", tổng không "chưa gồm"',
            dc.includes('Không áp dụng') && !dc.includes('chưa gồm'), dc.slice(0, 300));
        await notClipped(page, 'không app Sản xuất');
    }
    // sx cũ chưa có cột Stock Entry.custom_kiem_ke (kk_sx 'thieu_cot' — chữ dài nhất: "phiếu kho chưa ghi liên kết với lần kiểm
    // kê") + lỗi riêng khối phiếu kiểm kho.
    const tc = await degraded(page, 'thieu_cot + lỗi phiếu kiểm kho', { kk_sx: { available: false, reason: 'thieu_cot' },
        kk_ch: { available: false, error: true } });
    if (tc) {
        const dc = flat(await page.textContent('#kk-dc'));
        check(`thiếu cột liên kết: bảng điều chỉnh ghi lý do + "chưa gồm: ${tc.label}"`,
            dc.includes('phiếu kho chưa ghi liên kết với lần kiểm kê') && dc.includes(`chưa gồm: ${tc.label}`), dc.slice(0, 400));
        await notClipped(page, 'thiếu cột liên kết');
        const inside = await cardRowsInside(page, 'Tổng điều chỉnh');
        check('thiếu cột liên kết: dòng "Chưa gồm" của thẻ tổng không bị cắt', !inside.length, JSON.stringify(inside));
        await chKhongCuaHang(page, 'lỗi phiếu kiểm kho', 'Không tải được');
    }
    // Site chưa có bảng phiếu kiểm kho (kk_ch 'thieu_bang').
    const tb = await degraded(page, 'thiếu bảng phiếu kiểm kho', { kk_ch: { available: false, reason: 'thieu_bang' } });
    if (tb) {
        await notClipped(page, 'thiếu bảng phiếu kiểm kho');
        await chKhongCuaHang(page, 'thiếu bảng phiếu kiểm kho', 'hệ thống chưa có phiếu kiểm kho');
    }
    await page.unroute('**/bc.api.kho_kk.get_overview');
}

/** Sau một lần giả lập: không ô đầu bảng nào bị cắt chữ (UX-7). */
async function notClipped(page, tag) {
    const cut = await clipped(page);
    check(`${tag}: ô đầu các bảng không bị cắt chữ (lời giải thích "không có số" xuống dòng)`, !cut.length, JSON.stringify(cut).slice(0, 400));
}

/** Khối phiếu kiểm kho không có số: lời nhắn gọi đúng tên khối ("phiếu kiểm kho" — mọi kho), không gọi "kiểm kê cửa hàng"
 *  (UX-1: khối gồm cả kho khác); cả trang không còn chữ "kiểm kê cửa hàng". */
async function chKhongCuaHang(page, tag, why) {
    const ch = flat(await page.textContent('#kk-ch'));
    const main = flat(await page.textContent('.bc-main'));
    check(`${tag}: khối phiếu kiểm kho báo "${why}" và gọi đúng tên "phiếu kiểm kho", không "kiểm kê cửa hàng"`,
        ch.includes(why) && /phiếu kiểm kho/i.test(ch) && !/kiểm kê cửa hàng/i.test(ch) && !/kiểm kê cửa hàng/i.test(main), ch.slice(0, 200));
}

/** Tải lại trang với payload THẬT của máy chủ nhưng tắt khối như máy chủ làm khi lỗi / không có app Sản xuất / thiếu cột,
 *  thiếu bảng (`off` = {khối: {available:false, error|reason}}) — tổng tính lại theo đúng luật kho_kk._tong (khoản tắt vì
 *  'khong_sx' không áp dụng; lý do khác là thiếu). */
async function degraded(page, kind, off) {
    await page.unroute('**/bc.api.kho_kk.get_overview');
    let info = null;
    await page.route('**/bc.api.kho_kk.get_overview', async (route) => {
        const resp = await route.fetch();
        const j = await resp.json();
        const d = j.message;
        if (d && d.available && d.tong?.available) {
            Object.assign(d, off);
            for (const p of d.tong.parts) {
                if (off[p.key]) Object.assign(p, { available: false, gia_tri: null, reason: off[p.key].error ? 'loi' : off[p.key].reason });
            }
            const have = d.tong.parts.filter((p) => p.available);
            d.tong.gia_tri = Math.round(have.reduce((a, p) => a + p.gia_tri, 0) * 100) / 100;
            d.tong.thieu = d.tong.parts.filter((p) => !p.available && p.reason !== 'khong_sx').map((p) => p.key);
            d.tong.khong_ap_dung = d.tong.parts.filter((p) => !p.available && p.reason === 'khong_sx').map((p) => p.key);
            d.tong.day_du = !d.tong.thieu.length;
            info = { label: d.tong.parts.filter((p) => !p.available && p.reason !== 'khong_sx').map((p) => p.label).join('; '),
                gia_tri: d.tong.gia_tri };
        }
        await route.fulfill({ response: resp, json: j });
    });
    await page.reload();
    await page.waitForFunction(() => document.querySelectorAll('#kk-kpis .bc-stat').length === 5
        && !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
    if (!info) { check(`giả lập ${kind}: có payload`, false); return null; }
    const f = await page.evaluate(async (v) => (await import('/assets/bc/bc/lib/format.js')).fmtMoney(v), info.gia_tri);
    return { label: info.label, partial: f, total: f };
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
