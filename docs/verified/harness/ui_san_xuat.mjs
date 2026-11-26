// Kiểm màn #/san-xuat (Báo cáo sản xuất — số ghi hộp theo ngày) thật: import map + view thật + bc.api.sx_hop thật trên MariaDB
// (seed_ui_san_xuat.py, bảng Ghi hộp thật của sx). Hai server cùng DB: vai người xem (BC Viewer) và vai quản trị.
// node ui_san_xuat.mjs <viewerBase> <adminBase> [nosx|moc]
//   (mặc định) mỗi vai × desktop 1366px + điện thoại 390px: mọi số trên màn = payload API gọi trong trang (định dạng bằng
//   lib/format.js thật + đúng Intl của view), biểu đồ ngày (khoán / công nhật chồng, Chủ nhật đỏ, đường TB tháng trước) + 12
//   tháng, bảng theo ngày ("—" ngày không ghi), bấm ngày → chi tiết theo mã = get_day, bảng theo mã 10 dòng / trang, đổi tháng
//   (‹ › + ô chọn), tháng trống, › tắt ở tháng hiện tại, nút làm mới gửi refresh=1, tên có HTML hiện thành chữ, không lộ tên
//   người; dấu build; không lỗi JS / HTTP; không cuộn ngang. Rồi: quản trị ẩn mảng → người xem mất menu + route + API 403,
//   quản trị vẫn thấy (dấu "đang ẩn"); API lỗi → màn báo lỗi, ô chọn tháng còn.
//   Khối "Ghi hộp so với nhập kho" (get_compare, giữa Theo ngày và Theo mã): 3 thẻ tháng (dấu + chữ), dải "Hiện tại" (= khối
//   Nhập TP), biểu đồ ghi hộp / nhập kho / luỹ kế, bảng ngày có số, bảng theo mã + 3 chip lọc (đếm), ghi chú; đổi tháng + làm mới
//   tải lại khối; khối hỏng (HTTP 500 / error: true) không xoá phần còn lại và ngược lại; khối chậm không chặn phần trên.
//   nosx  site không cài sx (seed_ui_san_xuat.py nosx): màn báo chưa có số liệu, không lỗi; khối đối chiếu ẩn.
//   moc   seed có mốc tính nợ vào hộp của sx (seed_ui_san_xuat.py moc, D230): ô "Đã ghi hộp, chưa nhập kho" ghi "tính từ
//         mốc dd/mm" ở cả hai khổ màn, số = API = khối vào hộp của màn Nhập TP.
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const viewer = process.argv[2] || 'http://127.0.0.1:8160';
const admin = process.argv[3] || 'http://127.0.0.1:8161';
const MODE = process.argv[4] || '';
const SHOTS = process.env.SHOTS || '';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.BC_APP_ROOT || path.resolve(HERE, '..', '..', '..');
const SHELL_BUILD = (fs.readFileSync(path.join(ROOT, 'bc', 'www', 'bc.py'), 'utf8').match(/SHELL_BUILD = "([^"]+)"/) || [])[1];
const SECRET = ['Nguyễn Văn Bí Mật', 'HR-EMP', '1.234', '999.999',  // tên / mã nhân viên, đơn giá, tổng tiền trên seed
    'thukho.bimat', 'GHI CHÚ NHẬP BÍ MẬT', 'LÝ DO NỢ BÍ MẬT', 'SXNTP-BIMAT', 'NV-BIMAT'];  // người / ghi chú / lý do / tên phiếu, nợ

let bad = 0, total = 0;
function check(label, ok, detail = '') {
    total++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 500)}`); }
}
const squash = (s) => (s || '').replace(/\s+/g, ' ').trim();
const txt = (page, sel) => page.evaluate((x) => document.querySelector(x)?.textContent || '', sel).then(squash);
const fd = (s) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
const THU = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

async function post(page, method, args = {}) {
    return page.evaluate(([m, a]) => fetch(`/api/method/${m}`, { method: 'POST', body: new URLSearchParams(a) })
        .then(async (r) => ({ status: r.status, j: await r.json().catch(() => ({})) })), [method, args]);
}
async function api(page, thang) {
    return (await post(page, 'bc.api.sx_hop.get_overview', thang ? { thang } : {})).j.message;
}
async function apiDay(page, date) { return (await post(page, 'bc.api.sx_hop.get_day', { date })).j.message; }
async function apiCmp(page, thang) { return (await post(page, 'bc.api.sx_hop.get_compare', thang ? { thang } : {})).j.message; }

/** Định dạng như view: số / % bằng lib/format.js THẬT; thùng Intl tối đa 2 số lẻ; TB / ngày tối đa 1 số lẻ. */
async function F(page) {
    return page.evaluate(async () => {
        const f = await import('/assets/bc/bc/lib/format.js');
        window.__shF = f;
        return true;
    }).then(() => ({
        num: (vs) => page.evaluate((v) => v.map((x) => window.__shF.fmtNum(x)), vs),
        pct: (vs) => page.evaluate((v) => v.map((x) => window.__shF.fmtPct(x)), vs),
        growth: (v) => page.evaluate((x) => window.__shF.growthText(x), v),
        q: (vs) => page.evaluate((v) => v.map((x) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(x)), vs),
        d1: (vs) => page.evaluate((v) => v.map((x) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(x)), vs),
    }));
}

async function settle(page) {
    await page.waitForSelector('#sh-filter #sh-thang', { timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
}
async function waitMonth(page, thang) {
    await page.waitForFunction((t) => document.getElementById('sh-thang')?.value === t
        && !document.querySelector('.bc-main .bc-skeleton'), thang, { timeout: 20000 });
}
async function waitChart(page, id) {
    await page.waitForFunction((x) => window.Chart && window.Chart.getChart(document.getElementById(x)), id, { timeout: 15000 });
}

async function kpiCheck(page, d, f, tag) {
    const k = d.kpis;
    const s = await txt(page, '#sh-kpis');
    const [hop, ph, pf, sn, nc, cn, kh, sm] = await f.num([k.hop, k.prev_hop, k.prev_full, k.so_ngay, k.ngay_cuoi?.hop ?? 0, k.cong_nhat, k.khoan, k.so_ma]);
    const [th] = await f.q([k.thung]);
    const [tb] = await f.d1([k.tb_ngay]);
    const [cp] = await f.pct([k.cong_nhat_pct]);
    const g = await f.growth(k.growth_pct);
    const pl = `T${Number(d.meta.prev.slice(5))}/${d.meta.prev.slice(2, 4)}`;
    check(`${tag} thẻ Tổng hộp: ${hop} hộp, cùng kỳ ${pl} ${ph}, so cùng kỳ ${g}, cả ${pl} ${pf}`,
        s.includes(`Tổng hộp tháng ${hop} hộp`) && s.includes(`Cùng kỳ ${pl}${ph}`) && s.includes(`So cùng kỳ${g}`) && s.includes(`Cả ${pl}${pf}`), s);
    const gcls = await page.$eval('#sh-growth', (e) => e.className).catch(() => '');
    const want = k.growth_pct === null ? 'bc-muted' : (k.growth_pct >= 0 ? 'bc-up' : 'bc-down');
    check(`${tag} màu tăng / giảm theo dấu (${want})`, gcls === want, gcls);
    check(`${tag} thẻ Quy thùng ${th}, TB / ngày SX ${tb} (${sn} ngày có ghi)`, s.includes(`Quy thùng ${th} thùng`)
        && s.includes(`TB hộp / ngày SX ${tb}`) && s.includes(`Số ngày có ghi${sn}`), s);
    check(`${tag} thẻ Ngày ghi gần nhất ${k.ngay_cuoi ? `${fd(k.ngay_cuoi.date)} · ${nc} hộp` : '—'}`,
        k.ngay_cuoi ? s.includes(`Ngày ghi gần nhất ${fd(k.ngay_cuoi.date)} Hộp${nc}`) : s.includes('Ngày ghi gần nhất — Chưa ghi ngày nào'), s);
    check(`${tag} thẻ Công nhật ${cn} hộp, tỷ lệ ${cp}, khoán ${kh}; Số mã ${sm}`, s.includes(`Công nhật ${cn} hộp`)
        && s.includes(`Tỷ lệ${cp}`) && s.includes(`Khoán${kh}`) && s.includes(`Số mã ${sm}`), s);
    const badge = await txt(page, '#sh-chuachot');
    const [cc] = await f.num([k.chua_chot]);
    check(`${tag} nhãn "ngày chưa chốt" ${k.chua_chot > 0 ? `= ${cc}` : 'vắng'}`, k.chua_chot > 0 ? badge === `⚠ ${cc} ngày chưa chốt` : badge === '', badge);
}

async function daysCheck(page, d, f, tag) {
    const rows = await page.$$eval('#sh-day-table tbody tr.sh-day', (e) => e.map((tr) => ({
        date: tr.dataset.date, cells: [...tr.children].map((td) => td.textContent.replace(/\s+/g, ' ').trim()) })));
    // API trả ngày mới nhất trước (gói số AI cắt 30 phần tử đầu — ngày bị cắt của tháng 31 ngày là ngày 1); bảng cũng thế.
    const asc = d.days.slice().sort((a, b) => a.date.localeCompare(b.date));
    const exp = asc.slice().reverse();
    check(`${tag} API: days mới nhất trước`, JSON.stringify(d.days.map((x) => x.date)) === JSON.stringify(exp.map((x) => x.date)),
        d.days.slice(0, 2).map((x) => x.date).join(','));
    let why = '';
    if (rows.length !== exp.length) why = `${rows.length} dòng ≠ ${exp.length} ngày`;
    for (const [i, r] of exp.entries()) {
        if (why) break;
        const [hop, kh, cn, sm] = await f.num([r.hop, r.khoan, r.cong_nhat, r.so_ma]);
        const [th] = await f.q([r.thung]);
        const want = [`${fd(r.date).slice(0, 5)} ${THU[r.weekday]}`, ...(r.co ? [hop, th, kh, cn, sm, r.chot ? 'Đã chốt' : 'Chưa chốt'] : Array(6).fill('—'))];
        const got = rows[i];
        if (got.date !== r.date || want.some((w, j) => got.cells[j] !== w)) why = `${r.date}: [${got.cells.join(' | ')}] ≠ [${want.join(' | ')}]`;
    }
    check(`${tag} bảng theo ngày: ${exp.length} dòng, mới nhất trước, số = API, ngày không ghi là "—", thứ đúng`, !why, why);
    const tot = await page.$$eval('#sh-day-table tr.sh-day-total td', (e) => e.map((td) => td.textContent.trim()));
    const k = d.kpis;
    const [hop, kh, cn, sm] = await f.num([k.hop, k.khoan, k.cong_nhat, k.so_ma]);
    const [th] = await f.q([k.thung]);
    check(`${tag} dòng Cả tháng = KPI`, JSON.stringify(tot.slice(0, 6)) === JSON.stringify(['Cả tháng', hop, th, kh, cn, sm]), tot.join(' | '));
    const sun = await page.$$eval('#sh-day-table tr.sh-day.sh-sun', (e) => e.map((x) => x.dataset.date));
    const wantSun = exp.filter((x) => x.weekday === 6).map((x) => x.date);
    check(`${tag} Chủ nhật đánh dấu (${wantSun.length} ngày)`, JSON.stringify(sun) === JSON.stringify(wantSun) && wantSun.length > 0, sun.join(','));

    await waitChart(page, 'sh-day-chart');
    const ch = await page.evaluate(() => {
        const c = window.Chart.getChart(document.getElementById('sh-day-chart'));
        const col = c.config.options.scales.x.ticks.color;  // hàm gốc (c.options trả giá trị đã giải không theo nhãn)
        return { labels: c.data.labels, sets: c.data.datasets.map((x) => ({ label: x.label, type: x.type || 'bar', data: x.data, stack: x.stack })),
            colors: c.data.labels.map((_, i) => (typeof col === 'function' ? col({ index: i }) : col)), stacked: !!c.options.scales.y.stacked };
    });
    const kh2 = asc.map((r) => (r.co ? r.khoan : 0)), cn2 = asc.map((r) => (r.co ? r.cong_nhat : 0));  // biểu đồ: cũ bên trái
    const prev = d.trend.find((r) => r.thang === d.meta.prev);
    const line = ch.sets.find((x) => x.type === 'line');
    const okSets = ch.sets[0]?.label === 'Khoán' && JSON.stringify(ch.sets[0].data) === JSON.stringify(kh2)
        && ch.sets[1]?.label === 'Công nhật' && JSON.stringify(ch.sets[1].data) === JSON.stringify(cn2)
        && ch.sets[0].stack === ch.sets[1].stack && ch.stacked;
    check(`${tag} biểu đồ ngày: ${d.days.length} cột, khoán + công nhật chồng = API`, ch.labels.length === d.days.length && okSets,
        JSON.stringify(ch.sets).slice(0, 300));
    const red = asc.every((r, i) => (r.weekday === 6) === (ch.colors[i] === '#dc2626'))
        && JSON.stringify(ch.labels) === JSON.stringify(asc.map((r) => fd(r.date).slice(0, 2)));
    check(`${tag} biểu đồ ngày: nhãn Chủ nhật màu đỏ, ngày khác không`, red, ch.colors.join(','));
    const refOk = prev && prev.so_ngay ? (line && line.data.every((v) => v === prev.tb_ngay) && line.stack !== ch.sets[0].stack) : !line;
    check(`${tag} đường TB / ngày SX tháng trước ${prev && prev.so_ngay ? `= ${prev.tb_ngay}` : 'vắng (tháng trước không ghi)'}`, refOk,
        JSON.stringify(line || null).slice(0, 200));
}

async function itemRowsCheck(page, rows, f, tag) {
    const got = await page.$$eval('#sh-item-table tbody tr', (e) => e.map((tr) => [...tr.children].map((td, i) => (i
        ? td.textContent : `${td.querySelector('.sh-item-name')?.textContent}|${td.querySelector('.sh-group')?.textContent}|${td.querySelector('div')?.textContent}`)
        .replace(/\s+/g, ' ').trim())));
    const G = { tet: 'Tết', traditional: 'Truyền thống', khac: 'Khác' };
    let why = got.length !== rows.length ? `${got.length} dòng ≠ ${rows.length}` : '';
    for (const [i, r] of rows.entries()) {
        if (why) break;
        const [hop, sn] = await f.num([r.hop, r.so_ngay]);
        const [th] = await f.q([r.thung]);
        const [pc] = await f.pct([r.pct]);
        const [tb] = await f.d1([r.tb_ngay]);
        const want = [`${r.short_name || r.item_name || r.item_code}|${G[r.group]}|${r.item_code}`, hop, r.thung ? th : '—', pc, sn, tb];
        if (want.some((w, j) => got[i][j] !== w)) why = `${r.item_code}: [${got[i].join(' / ')}] ≠ [${want.join(' / ')}]`;
    }
    check(`${tag} ${rows.length} dòng = API (tên, nhóm, hộp, thùng / "—", % tổng, số ngày, TB / ngày)`, !why, why);
}

async function itemsCheck(page, d, f, tag) {
    const items = d.items;
    check(`${tag} mã ẩn HX-AN không có trong API theo mã (tổng vẫn gồm)`, !items.some((r) => r.item_code === 'HX-AN')
        && !(await txt(page, '#sh-items')).includes('HX-AN'));
    await itemRowsCheck(page, items.slice(0, 10), f, `${tag} bảng theo mã trang 1:`);
    const pager = await txt(page, '#sh-item-table .bc-pager-info');
    const pages = Math.ceil(items.length / 10);
    check(`${tag} bảng theo mã 10 dòng / trang: "Trang 1/${pages} · ${items.length} dòng"`, items.length > 10 && pager === `Trang 1/${pages} · ${items.length} dòng`, pager);
    if (items.length > 10) {
        await page.click('#sh-item-table [data-dt-page][data-dir="1"]');
        await itemRowsCheck(page, items.slice(10, 20), f, `${tag} bảng theo mã trang 2:`);
        await page.click('#sh-item-table [data-dt-page][data-dir="-1"]');
    }
    const gr = await page.$$eval('#sh-groups .bc-kpi', (e) => e.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    let gw = [];
    for (const g of d.groups) { const [h] = await f.num([g.hop]); const [p] = await f.pct([g.pct]); gw.push(`${g.label} ${h} ${p}`); }
    check(`${tag} ô nhóm hàng = API (${gw.join(' · ')})`, JSON.stringify(gr) === JSON.stringify(gw), gr.join(' · '));
    check(`${tag} tên có thẻ HTML hiện thành chữ, không chạy`, (await txt(page, '#sh-items')).includes('<img src=x')
        && await page.evaluate(() => window.__xss === undefined));
}

async function trendCheck(page, d, tag) {
    await waitChart(page, 'sh-trend-chart');
    const ch = await page.evaluate(() => { const c = window.Chart.getChart(document.getElementById('sh-trend-chart'));
        return { labels: c.data.labels, data: c.data.datasets[0].data }; });
    const lab = d.trend.map((r) => `T${Number(r.thang.slice(5))}/${r.thang.slice(2, 4)}`);
    check(`${tag} 12 tháng: ${lab[0]} → ${lab[11]}, cột = hộp từng tháng của API`, d.trend.length === 12
        && JSON.stringify(ch.labels) === JSON.stringify(lab) && JSON.stringify(ch.data) === JSON.stringify(d.trend.map((r) => r.hop))
        && JSON.stringify(d.trend.map((r) => r.thang)) === JSON.stringify(d.meta.months), JSON.stringify(ch));
}

// ─── Khối "Ghi hộp so với nhập kho" ──────────────────────────────────────────
const EPS = 0.005;
async function sgn(f, v) {  // −120 / +30 / 0 (dấu trừ Unicode) — viết lại độc lập với view
    if (v > EPS) return `+${(await f.q([v]))[0]}`;
    if (v < -EPS) return `−${(await f.q([-v]))[0]}`;
    return '0';
}
async function sgnPct(page, v) {
    if (v === null || v === undefined) return '—';
    const a = await page.evaluate((x) => new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(x), Math.abs(v));
    return `${v > 0 ? '+' : (v < 0 ? '−' : '')}${a}%`;
}
async function lechText(f, v) {
    if (v < -EPS) return `${await sgn(f, v)} hộp · chưa nhập kho`;
    if (v > EPS) return `${await sgn(f, v)} hộp · nhập vượt số ghi`;
    return '0 · khớp';
}
const CHIPS = { all: (r) => true, chua: (r) => !r.khac_dvt && r.lech < -EPS, vuot: (r) => !r.khac_dvt && r.lech > EPS };

async function cmpItemRows(page, rows, f, tag) {
    const got = await page.$$eval('#sh-cmp-item-table tbody tr', (e) => e.map((tr) => [...tr.children].map((td, i) => (i
        ? td.textContent : `${td.querySelector('.sh-item-name')?.textContent}|${td.querySelector('.sh-group')?.textContent}|${td.querySelector('.sh-dvt') ? 'ĐVT khác' : ''}|${td.querySelector('div')?.textContent}`)
        .replace(/\s+/g, ' ').trim())));
    const G = { tet: 'Tết', traditional: 'Truyền thống', khac: 'Khác' };
    let why = got.length !== rows.length ? `${got.length} dòng ≠ ${rows.length}` : '';
    for (const [i, r] of rows.entries()) {
        if (why) break;
        const [hop] = await f.num([r.hop]);
        const [nh] = await f.q([r.nhap]);
        const want = [`${r.short_name || r.item_name || r.item_code}|${G[r.group]}|${r.khac_dvt ? 'ĐVT khác' : ''}|${r.item_code}`, hop,
            r.khac_dvt ? `${nh} ${r.uom}` : nh, r.khac_dvt ? '—' : await sgn(f, r.lech)];
        if (want.some((w, j) => got[i][j] !== w)) why = `${r.item_code}: [${got[i].join(' / ')}] ≠ [${want.join(' / ')}]`;
    }
    check(`${tag} ${rows.length} dòng = API (tên, nhóm, "ĐVT khác", ghi hộp, nhập kho, chênh lệch có dấu)`, !why, why);
}

/** Thẻ (dòng bảng dạng lưới) có ô đè nhau, ô tràn chữ (scrollWidth > clientWidth) hay ô ra ngoài màn → danh sách lỗi. */
async function cardBad(page, sel) {
    return page.evaluate((s) => {
        const out = [];
        for (const tr of document.querySelectorAll(s)) {
            const tds = [...tr.children].filter((td) => getComputedStyle(td).display !== 'none');
            const rs = tds.map((td) => td.getBoundingClientRect());
            const name = (td) => td.textContent.replace(/\s+/g, ' ').trim().slice(0, 30);
            tds.forEach((td, i) => {
                if (td.scrollWidth > td.clientWidth + 1) out.push(`tràn: ${name(td)} (${td.scrollWidth} > ${td.clientWidth})`);
                if (rs[i].right > window.innerWidth + 0.5 || rs[i].left < -0.5) out.push(`ngoài màn: ${name(td)}`);
                for (let j = i + 1; j < tds.length; j++) {
                    const a = rs[i], b = rs[j];
                    if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5) {
                        out.push(`đè: ${name(td)} × ${name(tds[j])}`);
                    }
                }
            });
        }
        return out;
    }, sel);
}

async function cmpCheck(page, c, f, tag, mobile = false) {
    const order = await page.evaluate(() => {
        const a = document.getElementById('sh-days'), b = document.getElementById('sh-cmp-sec'), i = document.getElementById('sh-items');
        return !!(a && b && i) && !!(a.compareDocumentPosition(b) & 4) && !!(b.compareDocumentPosition(i) & 4) && !b.hidden;
    });
    check(`${tag} khối "Ghi hộp so với nhập kho" nằm giữa Theo ngày và Theo mã`, order
        && (await txt(page, '#sh-cmp-title')) === 'Ghi hộp so với nhập kho');
    check(`${tag} API so sánh có số: tháng ${c.meta.thang}, cùng tháng với phần trên`, c.available && c.meta.sx
        && c.meta.thang === (await page.$eval('#sh-thang', (e) => e.value)), JSON.stringify(c.meta));
    const t = c.total;
    // Bất biến của máy chủ (khối dựa vào): lech = nhap − hop = nhap_vuot − chua_nhap
    check(`${tag} API: lech = nhập − ghi = nhập vượt − chưa nhập`, Math.abs(t.lech - (t.nhap - t.hop)) < 0.011
        && Math.abs(t.lech - (t.nhap_vuot - t.chua_nhap)) < 0.011, JSON.stringify(t));
    const empty = !c.days.some((r) => r.co) && !c.items.length && !t.hop && !t.nhap;
    const s = await txt(page, '#sh-cmp');
    if (empty) {
        check(`${tag} tháng không ghi hộp lẫn nhập kho → "Tháng này chưa có số ghi hộp lẫn nhập kho", không thẻ / bảng`,
            s.includes('Tháng này chưa có số ghi hộp lẫn nhập kho') && !(await page.$('#sh-cmp-kpis')) && !(await page.$('#sh-cmp-day-table')), s);
    } else {
        const k = await txt(page, '#sh-cmp-kpis');
        const [hop, mc, mv, mk] = await f.num([t.hop, t.so_ma_chua_nhap, t.so_ma_nhap_vuot, t.so_ma_khop]);
        const [nh, cn, nv] = await f.q([t.nhap, t.chua_nhap, t.nhap_vuot]);
        const lw = await lechText(f, t.lech), lp = await sgnPct(page, t.lech_pct);
        check(`${tag} thẻ Ghi hộp ${hop} hộp · Nhập kho ${nh} hộp (phiếu thủ kho đã duyệt)`, k.includes(`Ghi hộp ${hop} hộp`)
            && k.includes(`Nhập kho ${nh} hộp`) && k.includes('phiếu thủ kho đã duyệt'), k);
        check(`${tag} thẻ Chênh lệch "${lw}" (${lp}), chưa nhập ${cn} hộp (${mc} mã), nhập vượt ${nv} hộp (${mv} mã), khớp ${mk} mã`,
            (await txt(page, '#sh-cmp-lech')) === lw && (await txt(page, '#sh-cmp-pct')) === lp
            && k.includes(`Chưa nhập kho${cn} hộp (${mc} mã)`) && k.includes(`Nhập vượt số ghi${nv} hộp (${mv} mã)`) && k.includes(`Khớp${mk} mã`), k);
        if (t.hop_chua_ma) {
            const [hc] = await f.num([t.hop_chua_ma]);
            check(`${tag} thẻ Ghi hộp: chưa chọn mã ${hc} hộp`, k.includes(`Chưa chọn mã${hc} hộp`), k);
        }
        // Bảng ngày: chỉ ngày có số, mới nhất trước + Cả tháng
        const rows = await page.$$eval('#sh-cmp-day-table tbody tr.sh-cmp-day', (e) => e.map((tr) => ({ date: tr.dataset.date,
            sun: tr.classList.contains('sh-sun'), cells: [...tr.children].map((td) => td.textContent.replace(/\s+/g, ' ').trim()) })));
        const exp = c.days.filter((r) => r.co);
        let why = rows.length !== exp.length ? `${rows.length} dòng ≠ ${exp.length}` : '';
        for (const [i, r] of exp.entries()) {
            if (why) break;
            const [h] = await f.num([r.hop]); const [n] = await f.q([r.nhap]);
            const want = [`${fd(r.date).slice(0, 5)} ${THU[r.weekday]}`, h, n, await sgn(f, r.lech), await sgn(f, r.luy_ke)];
            if (rows[i].date !== r.date || rows[i].sun !== (r.weekday === 6) || want.some((w, j) => rows[i].cells[j] !== w)) {
                why = `${r.date}: [${rows[i].cells.join(' | ')}] ≠ [${want.join(' | ')}]`;
            }
        }
        check(`${tag} bảng ngày đối chiếu: ${exp.length} ngày có số, mới nhất trước, ghi / nhập / chênh / luỹ kế = API, Chủ nhật đánh dấu`,
            !why && exp.length > 0, why);
        const tot = await page.$$eval('#sh-cmp-day-table tr.sh-cmp-total td', (e) => e.map((td) => td.textContent.trim()));
        check(`${tag} dòng Cả tháng = tổng (${hop} / ${nh} / ${await sgn(f, t.lech)})`,
            JSON.stringify(tot.slice(0, 4)) === JSON.stringify(['Cả tháng', hop, nh, await sgn(f, t.lech)]), tot.join(' | '));
        // luỹ kế: cộng dồn lech từ ngày đầu tháng (kiểm trên payload, cột luỹ kế ở trên = payload)
        const asc = c.days.slice().reverse();
        let run = 0, okRun = true;
        for (const r of asc) { run += r.lech; if (Math.abs(run - r.luy_ke) > 0.011) okRun = false; }
        check(`${tag} API: luỹ kế = cộng dồn chênh lệch từ đầu tháng, ngày cuối = chênh lệch cả tháng`, okRun && Math.abs(run - t.lech) < 0.011);
        if (mobile) {
            const card = await page.evaluate(() => ({ thead: getComputedStyle(document.querySelector('#sh-cmp-day-table thead')).display,
                tr: getComputedStyle(document.querySelector('#sh-cmp-day-table tr.sh-cmp-day')).display }));
            check(`${tag} 390px: bảng ngày đối chiếu thành thẻ`, card.thead === 'none' && card.tr === 'grid', JSON.stringify(card));
            const bad = await cardBad(page, '#sh-cmp-day-table tbody tr');
            check(`${tag} 390px: thẻ ngày đối chiếu + Cả tháng — không số nào đè / tràn sang ô bên`, !bad.length, bad.slice(0, 4).join(' | '));
        }
        // Biểu đồ: ngày cũ bên trái, cột ghi hộp + nhập kho (không chồng) + đường luỹ kế, Chủ nhật đỏ
        await waitChart(page, 'sh-cmp-chart');
        const ch = await page.evaluate(() => {
            const x = window.Chart.getChart(document.getElementById('sh-cmp-chart'));
            const col = x.config.options.scales.x.ticks.color;
            return { labels: x.data.labels, sets: x.data.datasets.map((d) => ({ label: d.label, type: d.type || 'bar', data: d.data, stack: d.stack })),
                stacked: !!x.options.scales.x.stacked || !!x.options.scales.y.stacked,
                colors: x.data.labels.map((_, i) => (typeof col === 'function' ? col({ index: i }) : col)) };
        });
        const J = JSON.stringify;
        const okCh = J(ch.labels) === J(asc.map((r) => fd(r.date).slice(0, 2)))
            && ch.sets[0]?.label === 'Ghi hộp' && ch.sets[0].type === 'bar' && J(ch.sets[0].data) === J(asc.map((r) => r.hop))
            && ch.sets[1]?.label === 'Nhập kho' && ch.sets[1].type === 'bar' && J(ch.sets[1].data) === J(asc.map((r) => r.nhap))
            && ch.sets[2]?.label === 'Luỹ kế chênh lệch' && ch.sets[2].type === 'line' && J(ch.sets[2].data) === J(asc.map((r) => r.luy_ke))
            && !ch.stacked && ch.sets[0].stack === undefined;
        check(`${tag} biểu đồ đối chiếu: ${asc.length} ngày (cũ bên trái), cột ghi hộp + nhập kho cạnh nhau, đường luỹ kế = API`, okCh,
            J(ch.sets).slice(0, 300));
        check(`${tag} biểu đồ đối chiếu: nhãn Chủ nhật đỏ, ngày khác không`, asc.every((r, i) => (r.weekday === 6) === (ch.colors[i] === '#dc2626')),
            ch.colors.join(','));
        // Theo mã: chip + bảng 10 dòng / trang
        const items = c.items;
        check(`${tag} mã ẩn HX-AN không có trong bảng đối chiếu (API cũng không)`, !items.some((r) => r.item_code === 'HX-AN')
            && !(await txt(page, '#sh-cmp-item-table')).includes('HX-AN'));
        const chips = await page.$$eval('#sh-cmp-chips [data-cmp-chip]', (e) => e.map((x) => `${x.dataset.cmpChip}=${x.textContent.replace(/\s+/g, ' ').trim()}`));
        const nAll = items.length, nC = items.filter(CHIPS.chua).length, nV = items.filter(CHIPS.vuot).length;
        // Thẻ và chip đếm mã theo CÙNG một ngưỡng (lệch đã làm tròn): mã lệch 0,004 không được vừa "khớp" ở bảng vừa "nhập
        // vượt (1 mã)" ở thẻ. (Mã ẩn của seed đều khớp nên không lệch số đếm hai nhóm này.)
        check(`${tag} số mã ở thẻ = số ở chip: chưa nhập ${t.so_ma_chua_nhap} = ${nC}, nhập vượt ${t.so_ma_nhap_vuot} = ${nV}`,
            t.so_ma_chua_nhap === nC && t.so_ma_nhap_vuot === nV, JSON.stringify(t));
        const [a1, a2, a3] = await f.num([nAll, nC, nV]);
        check(`${tag} chip: Tất cả ${a1} · Chưa nhập kho ${a2} · Nhập vượt ${a3}`, J(chips) === J([`all=Tất cả${a1}`, `chua=Chưa nhập kho${a2}`, `vuot=Nhập vượt${a3}`]), chips.join(' · '));
        await cmpItemRows(page, items.slice(0, 10), f, `${tag} bảng đối chiếu theo mã trang 1:`);
        if (items.length > 10) {
            const pager = await txt(page, '#sh-cmp-item-table .bc-pager-info');
            check(`${tag} bảng đối chiếu theo mã: "Trang 1/${Math.ceil(items.length / 10)} · ${items.length} dòng"`,
                pager === `Trang 1/${Math.ceil(items.length / 10)} · ${items.length} dòng`, pager);
            await page.click('#sh-cmp-item-table [data-dt-page][data-dir="1"]');
            await cmpItemRows(page, items.slice(10, 20), f, `${tag} bảng đối chiếu theo mã trang 2:`);
        }
        if (mobile) {
            // 390px: bảng theo mã thành thẻ — mọi ô (kể cả Chênh lệch) trong khung màn, không ô nào đè / tràn ô khác.
            const bad = await cardBad(page, '#sh-cmp-item-table tbody tr');
            check(`${tag} 390px: bảng đối chiếu theo mã thành thẻ, cột Chênh lệch luôn thấy, không ô nào đè / tràn`, !bad.length
                && await page.$eval('#sh-cmp-item-table thead', (e) => getComputedStyle(e).display) === 'none', bad.slice(0, 4).join(' | '));
        }
        for (const key of ['chua', 'vuot', 'all']) {
            await page.click(`#sh-cmp-chips [data-cmp-chip="${key}"]`);
            const on = await page.$$eval('#sh-cmp-chips .bc-active', (e) => e.map((x) => x.dataset.cmpChip));
            const want = items.filter(CHIPS[key]);
            check(`${tag} chip "${key}" bật, chỉ một chip sáng`, J(on) === J([key]), on.join(','));
            await cmpItemRows(page, want.slice(0, 10), f, `${tag} chip ${key}:`);
        }
        if (items.some((r) => r.item_code === 'HX-P07')) {
            check(`${tag} tên có thẻ HTML trong bảng đối chiếu hiện thành chữ`, (await txt(page, '#sh-cmp-item-table')).includes('<img src=x')
                && await page.evaluate(() => window.__xss === undefined));
        }
        const note = await txt(page, '#sh-cmp-note');
        check(`${tag} ghi chú: chênh lệch = nhập kho − ghi hộp, số âm / số dương, ngày sản xuất vs ngày nhận, luỹ kế`,
            note.startsWith('Chênh lệch = nhập kho − ghi hộp, như bảng đối chiếu của Quản lý trên app Sản xuất.')
            && note.includes('Số âm: đã ghi hộp nhưng chưa nhập kho') && note.includes('số dương: kho nhận nhiều hơn số ghi hộp')
            && note.includes('xem cột Luỹ kế') && note.includes('nhập đầu tháng này cũng làm lệch'), note);
        const ex = await txt(page, '#sh-cmp-extra');
        const [hc, mk2] = await f.num([t.hop_chua_ma, t.ma_khac_dvt]);
        check(`${tag} ghi chú phụ: ${t.hop_chua_ma ? `${hc} hộp chưa chọn mã` : 'không dòng chưa chọn mã'} · ${t.ma_khac_dvt ? `${mk2} mã ĐVT khác` : 'không mã ĐVT khác'}`,
            (t.hop_chua_ma ? ex.includes(`${hc} hộp chưa chọn mã không đối chiếu được`) : !ex.includes('chưa chọn mã'))
            && (t.ma_khac_dvt ? ex.includes(`${mk2} mã có đơn vị kho khác Hộp không cộng vào tổng`) : !ex.includes('đơn vị kho khác')), ex);
    }
    await nowCheck(page, c, f, tag);
}

/** Dải "Hiện tại" — không theo tháng chọn; "Đã ghi hộp, chưa nhập kho" và "chờ duyệt" = khối của màn Nhập TP. */
async function nowCheck(page, c, f, tag) {
    const v = c.cho_nhap, q = c.cho_duyet, n = c.no_vao_hop;
    const title = await txt(page, '#sh-cmp-now .sh-now-title');
    check(`${tag} dải "Hiện tại (đến hôm nay ${fd(c.meta.as_of)}) · không theo tháng chọn"`,
        title === `Hiện tại (đến hôm nay ${fd(c.meta.as_of)}) · không theo tháng chọn`, title);
    const t1 = await txt(page, '#sh-now-chonhap'), t2 = await txt(page, '#sh-now-choduyet'), t3 = await txt(page, '#sh-now-novaohop');
    const [vq, q2, nq] = await f.q([v.qty, q.qty, n.qty]);
    const [vi, qc, qt, nm, na] = await f.num([v.items, q.count, q.count_tet, n.so_ma, n.oldest_age_days]);
    // D230: mốc tính nợ vào hộp của sx đang áp (lượt `moc`) → "tính từ mốc dd/mm"; chưa đặt mốc → "30 ngày gần nhất"
    check(MODE === 'moc' ? `${tag} D230 API cho_nhap có moc + mang_sang > 0` : `${tag} D230 API cho_nhap không mốc (moc / mang_sang null)`,
        MODE === 'moc' ? !!v.moc && v.mang_sang > 0 : v.moc === null && v.mang_sang === null, JSON.stringify([v.moc, v.mang_sang]));
    const sau = v.moc ? `tính từ mốc ${v.moc.slice(8, 10)}/${v.moc.slice(5, 7)}` : '30 ngày gần nhất';
    check(`${tag} Đã ghi hộp, chưa nhập kho: ${vq} hộp · ${vi} mã · ${sau}`, v.available
        && t1 === `Đã ghi hộp, chưa nhập kho${vq} hộp ${vi} mã · ${sau}`, t1);
    const qWant = q.qty === null ? 'nhiều đơn vị kho, không cộng' : `${q2} ${q.uom}`;
    check(`${tag} Phiếu nhập chờ thủ kho duyệt: ${qc} phiếu · ${qWant}`, q.available
        && t2 === `Phiếu nhập chờ thủ kho duyệt${qc} phiếu ${qWant}${q.count_tet ? ` · ${qt} phiếu Tết` : ''}`, t2);
    const [nk] = await f.num([n.so_ma_khac_dvt || 0]);
    const khac = n.so_ma_khac_dvt ? ` · ${nk} mã đơn vị khác không cộng` : '';
    check(`${tag} Kho nhận vượt số ghi hộp: ${nq} hộp · ${nm} mã · lâu nhất ${na} ngày${khac}`, n.available
        && t3 === `Kho nhận vượt số ghi hộp${nq} hộp ${nm} mã · lâu nhất ${na} ngày${khac}`, t3);
    // Nợ vào hộp tính theo đơn vị kho của từng mã: số "hộp" của ô = Σ nợ của mã đơn vị Hộp (seed: HX-KG nợ 9,5 Kg không
    // cộng) — dựng lại độc lập từ dòng API + danh mục (không tin tổng của máy chủ).
    const boxRows = (n.rows || []).filter((r) => r.khac_dvt === false);
    const kgRow = (n.rows || []).find((r) => r.item_code === 'HX-KG');
    check(`${tag} nợ vào hộp: chỉ cộng mã đơn vị Hộp (HX-KG 9,5 Kg đứng riêng, cuối), ô ghi "1 mã đơn vị khác không cộng"`,
        !!kgRow && kgRow.khac_dvt === true && kgRow.qty === 9.5 && n.rows[n.rows.length - 1] === kgRow && n.so_ma_khac_dvt === 1
        && Math.abs(boxRows.reduce((a, r) => a + r.qty, 0) + 8 - n.qty) < 0.005 && n.so_ma === boxRows.length + 1  // + mã ẩn HX-AN (8 hộp, không có dòng)
        && t3.endsWith('· 1 mã đơn vị khác không cộng'), JSON.stringify([n.qty, n.so_ma, n.so_ma_khac_dvt, n.rows.map((r) => [r.item_code, r.qty, r.khac_dvt])]));
    const hrefs = await page.$$eval('#sh-cmp-now a.sh-now-tile', (e) => e.map((a) => `${a.id}:${a.getAttribute('href')}`));
    check(`${tag} hai ô đầu mở #/nhap-tp, ô nợ vào hộp không phải liên kết`, JSON.stringify(hrefs)
        === JSON.stringify(['sh-now-chonhap:#/nhap-tp', 'sh-now-choduyet:#/nhap-tp']), hrefs.join(','));
    // Cùng số với màn Nhập TP (bc.api.kho_nhap — vai quản trị / người xem đều được gọi khi mảng không ẩn)
    const k = (await post(page, 'bc.api.kho_nhap.get_overview', {})).j.message || {};
    {
        check(`${tag} = màn Nhập TP: đã vào hộp chưa nhập ${k.vao_hop.qty} (${k.vao_hop.items} mã), chờ duyệt ${k.cho_duyet?.count} phiếu`,
            !!k.vao_hop && k.vao_hop.qty === v.qty && k.vao_hop.items === v.items && k.cho_duyet.count === q.count && k.cho_duyet.qty === q.qty
            && k.vao_hop.moc === v.moc && (v.mang_sang === null ? k.vao_hop.mang_sang === null : Math.abs(k.vao_hop.mang_sang - v.mang_sang) < 0.005)
            && k.cho_duyet.count_tet === q.count_tet, JSON.stringify([k.vao_hop.qty, k.cho_duyet.count, v.qty, q.count]));
    }
}

async function detailCheck(page, date, f, tag, keyboard = false) {
    const x = await apiDay(page, date);
    const sel = `#sh-day-table tr.sh-day[data-date="${date}"]`;
    if (keyboard) { await page.focus(sel); await page.keyboard.press('Enter'); } else await page.click(sel);
    await page.waitForSelector(`#sh-day-table .sh-detail[data-detail="${date}"]`, { timeout: 15000 });
    const head = await txt(page, '#sh-day-table .sh-dt-head');
    const t = x.total;
    const [hop, kh, cn] = await f.num([t.hop, t.khoan, t.cong_nhat]);
    const [th] = await f.q([t.thung]);
    check(`${tag} chi tiết ${fd(date)}${keyboard ? ' (phím Enter)' : ''}: ${hop} hộp · ${th} thùng · khoán ${kh} · công nhật ${cn} · ${x.meta.chot ? 'Đã chốt' : 'Chưa chốt'}`,
        head === `${fd(date)} ${hop} hộp · ${th} thùng · khoán ${kh} · công nhật ${cn} ${x.meta.chot ? 'Đã chốt' : 'Chưa chốt'}`, head);
    const rows = await page.$$eval('#sh-day-table .sh-dt-row', (e) => e.map((r) => r.textContent.replace(/\s+/g, ' ').trim()));
    let why = rows.length !== x.rows.length ? `${rows.length} ≠ ${x.rows.length}` : '';
    const G = { tet: 'Tết', traditional: 'Truyền thống', khac: 'Khác' };
    for (const [i, r] of x.rows.entries()) {
        if (why) break;
        const [h, k, c, kc] = await f.num([r.hop, r.khoan, r.cong_nhat, r.khoan_chung]);
        const [tt] = await f.q([r.thung]);
        const [p] = await f.pct([r.pct]);
        const want = `${r.short_name || r.item_name} ${G[r.group]} ${r.item_code} · khoán ${k}${r.khoan_chung ? ` (chung ${kc})` : ''} · công nhật ${c} `
            + `${h} hộp${r.thung ? `${tt} thùng · ` : ''}${p}`;  // textContent: "hộp" liền dòng phụ (div)
        if (rows[i] !== want) why = `[${rows[i]}] ≠ [${want}]`;
    }
    check(`${tag} chi tiết ${fd(date)}: ${x.rows.length} mã = get_day (khoán, khoán chung, công nhật, thùng, %)`, !why && x.rows.length > 0, why);
    const exp = await page.$eval(sel, (e) => e.getAttribute('aria-expanded'));
    if (keyboard) await page.keyboard.press('Enter'); else await page.click(sel);
    await page.waitForFunction(() => !document.querySelector('#sh-day-table .sh-detail-row'), null, { timeout: 5000 }).catch(() => {});
    check(`${tag} bấm lại ${fd(date)} → đóng chi tiết`, exp === 'true' && !(await page.$('#sh-day-table .sh-detail-row'))
        && await page.$eval(sel, (e) => e.getAttribute('aria-expanded')) === 'false');
    return x;
}

async function scenario(page, mobile, role) {
    const tag = `[${role}${mobile ? ' 390' : ''}]`;
    await settle(page);
    const f = await F(page);
    const banner = await txt(page, '.bc-view-banner');
    check(`${tag} banner "Báo cáo sản xuất", tiêu đề trang`, banner.includes('Báo cáo sản xuất')
        && (await page.title()).startsWith('Báo cáo sản xuất'), banner);
    const build = await page.evaluate(() => window.BC?.build);
    check(`${tag} dấu build shell = www/bc.py (${SHELL_BUILD})`, !!SHELL_BUILD && build === SHELL_BUILD && SHELL_BUILD === 'bc-p10-r3', `${build} / ${SHELL_BUILD}`);
    const menu = await page.$('a[data-route="/san-xuat"]');
    check(`${tag} menu có "Báo cáo sản xuất" trong nhóm Sản xuất, trước SX Hàng Tết`, !!menu && await page.evaluate(() => {
        const a = [...document.querySelectorAll('#bc-sidebar .bc-side-link')].map((x) => x.dataset.route);
        return a.indexOf('/san-xuat') >= 0 && a.indexOf('/san-xuat') === a.indexOf('/sx-tet') - 1;
    }));

    const d = await api(page);
    check(`${tag} API có số: tháng ${d.meta.thang}, ${d.days.length} ngày, ${d.items.length} mã`, d.available && d.meta.sx && d.days.length > 20 && d.items.length > 10);
    const info = await txt(page, '#sh-info');
    const g = String(d.meta.generated_at || '');
    const upd = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(g) ? `${g.slice(11, 16)} ${fd(g)}` : fd(d.meta.as_of);
    check(`${tag} khoảng ngày Từ ${fd(d.meta.from)} đến ${fd(d.meta.to)} · Cập nhật ${upd}`,
        info === `Từ ${fd(d.meta.from)} đến ${fd(d.meta.to)} · Cập nhật ${upd}`, info);
    check(`${tag} › tắt ở tháng hiện tại, ‹ bật`, await page.$eval('#sh-next', (e) => e.disabled) && !(await page.$eval('#sh-prev', (e) => e.disabled)));
    await kpiCheck(page, d, f, tag);
    await daysCheck(page, d, f, tag);
    if (mobile) {
        const card = await page.evaluate(() => ({ thead: getComputedStyle(document.querySelector('#sh-day-table thead')).display,
            tr: getComputedStyle(document.querySelector('#sh-day-table tr.sh-day')).display }));
        check(`${tag} 390px: bảng theo ngày thành thẻ (ẩn tiêu đề cột, dòng là lưới)`, card.thead === 'none' && card.tr === 'grid', JSON.stringify(card));
    }
    await itemsCheck(page, d, f, tag);
    await trendCheck(page, d, tag);
    const c = await apiCmp(page);
    // Seed phủ đủ các trường hợp (không thì các kiểm dưới trống nghĩa)
    check(`${tag} seed đối chiếu tháng 10 phủ: chưa nhập, nhập vượt, khớp, mã chỉ ở phiếu, ĐVT khác, hộp chưa chọn mã, > 10 mã, ngày chỉ có nhập`,
        c.available && c.total.so_ma_chua_nhap > 0 && c.total.so_ma_nhap_vuot > 0 && c.total.so_ma_khop > 0 && c.total.hop_chua_ma > 0
        && c.items.some((r) => r.khac_dvt) && c.items.some((r) => !r.hop && r.nhap) && c.items.length > 10
        && c.days.some((r) => r.co && !r.hop && r.nhap) && c.total.lech < 0, JSON.stringify(c.total));
    await cmpCheck(page, c, f, tag, mobile);
    await detailCheck(page, '2026-10-02', f, tag);
    await detailCheck(page, '2026-10-26', f, tag, true);
    const empty = d.days.find((r) => !r.co);
    if (empty) {
        await page.click(`#sh-day-table tr.sh-day[data-date="${empty.date}"]`);
        await page.waitForTimeout(300);
        check(`${tag} ngày không ghi (${fd(empty.date)}) không mở chi tiết`, !(await page.$('#sh-day-table .sh-detail-row')));
    }
    const note = await txt(page, '#sh-note');
    check(`${tag} ghi chú cuối trang nói nguồn Ghi hộp, gồm công nhật, khác Nhập TP`, note.startsWith('ⓘ Số lấy từ phần Ghi hộp của app Sản xuất')
        && note.includes('gồm cả hộp công nhật') && note.includes('bảng đã huỷ không tính') && note.includes('Khác với màn Nhập TP'), note);

    // ── Làm mới: lượt gọi mang refresh=1 ──
    const reqs = [], creqs = [];
    const onReq = (r) => { if (r.url().includes('sx_hop.get_overview')) reqs.push(r.postData() || '');
        if (r.url().includes('sx_hop.get_compare')) creqs.push(r.postData() || ''); };
    page.on('request', onReq);
    const resP = page.waitForResponse((r) => r.url().includes('sx_hop.get_overview'), { timeout: 15000 });
    await page.click('#sh-refresh');
    const gen = (await (await resP).json())?.message?.meta?.generated_at;
    await waitMonth(page, d.meta.thang);
    page.off('request', onReq);
    check(`${tag} nút làm mới tải lại tháng đang xem với refresh=1`, reqs.length === 1 && /(^|&)refresh=1(&|$)/.test(reqs[0])
        && /thang=2026-10/.test(reqs[0]), reqs.join(' | '));
    check(`${tag} nút làm mới tải lại cả khối đối chiếu (cùng tháng, refresh=1)`, creqs.length === 1 && /(^|&)refresh=1(&|$)/.test(creqs[0])
        && /thang=2026-10/.test(creqs[0]) && !!(await page.$('#sh-cmp-kpis')), creqs.join(' | '));
    // Mở một ngày SAU làm mới: get_day mang since = generated_at của bảng vừa tải → bản cache cũ hơn của ngày bị tính lại
    // (chi tiết không cũ hơn dòng ngày). Máy chủ xử lý since: test_sx_hop.py.
    const dreq = page.waitForRequest((r) => r.url().includes('sx_hop.get_day'), { timeout: 15000 });
    await page.click('#sh-day-table tr.sh-day[data-date="2026-10-26"]');
    const since = new URLSearchParams((await dreq).postData() || '').get('since');
    await page.waitForSelector('#sh-day-table .sh-detail[data-detail="2026-10-26"]', { timeout: 15000 });
    check(`${tag} sau làm mới, mở ngày → get_day mang since = generated_at của bảng (${gen})`, !!gen && since === gen, `${since} / ${gen}`);
    await page.click('#sh-day-table tr.sh-day[data-date="2026-10-26"]');
    await page.waitForFunction(() => !document.querySelector('#sh-day-table .sh-detail-row'), null, { timeout: 5000 }).catch(() => {});

    // ── Đổi tháng: ‹ → tháng trước ──
    await page.click('#sh-prev');
    await waitMonth(page, d.meta.prev);
    const d2 = await api(page, d.meta.prev);
    check(`${tag} ‹ → tháng ${d2.meta.thang}: ô chọn + khoảng ngày đổi, › bật`, (await txt(page, '#sh-range')) === `Từ ${fd(d2.meta.from)} đến ${fd(d2.meta.to)}`
        && !(await page.$eval('#sh-next', (e) => e.disabled)));
    await kpiCheck(page, d2, f, `${tag}[${d2.meta.thang}]`);
    await daysCheck(page, d2, f, `${tag}[${d2.meta.thang}]`);
    await cmpCheck(page, await apiCmp(page, d.meta.prev), f, `${tag}[${d2.meta.thang}]`, mobile);
    // ── Tháng trống (7/2026) qua ô chọn ──
    await page.selectOption('#sh-thang', '2026-07');
    await waitMonth(page, '2026-07');
    const d7 = await api(page, '2026-07');
    const ds = await txt(page, '#sh-days'), is = await txt(page, '#sh-items');
    check(`${tag} tháng trống 07/2026: "Chưa có số ghi hộp trong tháng này" ở khối ngày và theo mã`, d7.available && d7.kpis.hop === 0
        && ds.includes('Chưa có số ghi hộp trong tháng này') && is.includes('Chưa có số ghi hộp trong tháng này')
        && !(await page.$('#sh-day-table')), `${ds} | ${is}`);
    await kpiCheck(page, d7, f, `${tag}[2026-07]`);
    await cmpCheck(page, await apiCmp(page, '2026-07'), f, `${tag}[2026-07]`, mobile);
    await trendCheck(page, d7, `${tag}[2026-07]`);
    // ── › về lại tới tháng hiện tại ──
    await page.click('#sh-next');
    await waitMonth(page, '2026-08');
    check(`${tag} › → 08/2026`, (await txt(page, '#sh-range')).startsWith('Từ 01/08/2026'));
    await page.selectOption('#sh-thang', d.meta.thang);
    await waitMonth(page, d.meta.thang);
    check(`${tag} chọn lại tháng hiện tại: › tắt`, await page.$eval('#sh-next', (e) => e.disabled));
    // ── Tháng 6/2026: số 6 chữ số có phần lẻ (987.670,99), mã lệch +0,004 → khớp ở thẻ, bảng lẫn chip ──
    await page.selectOption('#sh-thang', '2026-06');
    await waitMonth(page, '2026-06');
    const c6 = await apiCmp(page, '2026-06');
    const tt2 = c6.items.find((r) => r.item_code === 'HX-TT2');
    check(`${tag}[2026-06] API: HX-TT2 ghi 10 nhập 10,004 → lệch 0, đếm là khớp (không "nhập vượt 1 mã")`, !!tt2 && tt2.lech === 0
        && c6.total.so_ma_nhap_vuot === 1 && c6.total.so_ma_khop === 1 && c6.total.nhap === 987680.99, JSON.stringify(c6.total));
    await cmpCheck(page, c6, f, `${tag}[2026-06]`, mobile);
    check(`${tag}[2026-06] khối ghi tháng của nó: "Tháng 06/2026"`, (await txt(page, '#sh-cmp-month')).startsWith('Tháng 06/2026'));
    await page.selectOption('#sh-thang', d.meta.thang);
    await waitMonth(page, d.meta.thang);

    const all = await page.textContent('.bc-main');
    check(`${tag} không lộ tên / mã nhân viên, đơn giá, tiền`, !SECRET.some((x) => all.includes(x)), SECRET.filter((x) => all.includes(x)).join(','));
    check(`${tag} không còn khung chờ, không báo lỗi tải`, !all.includes('Không tải được') && !(await page.$('.bc-main .bc-skeleton')));
}

function watch(page, errors) {
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('favicon.ico')) errors.push(`${r.status()} ${r.url()}`); });
}
async function overflow(page) { return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth); }
const setHidden = (page, keys, hidden) => page.request.post(`${admin}/api/method/bc.api.sections.set_hidden`,
    { form: { sections: JSON.stringify(keys), hidden: hidden ? 1 : 0 } });

const browser = await chromium.launch();
const ctxOf = (mobile) => browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
    : { viewport: { width: 1366, height: 900 } });

if (MODE === 'moc') {
    // D230: seed có mốc tính nợ vào hộp (seed_ui_san_xuat.py moc) — dải "Hiện tại" hai khổ màn, số = API = màn Nhập TP
    for (const mobile of [false, true]) {
        const page = await (await ctxOf(mobile)).newPage();
        const errors = [];
        watch(page, errors);
        await page.goto(`${viewer}/bc#/san-xuat`);
        const tag = `[mốc${mobile ? ' 390' : ''}]`;
        try {
            await settle(page);
            await page.waitForSelector('#sh-now-chonhap', { timeout: 15000 });
            await nowCheck(page, await apiCmp(page), await F(page), tag);
        } catch (e) { check(`${tag} kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        const o = await overflow(page);
        check(`${tag} không cuộn ngang (${o}px)`, o <= 1);
        check(`${tag} không lỗi JS / HTTP`, errors.length === 0, errors.join(' | '));
        await page.context().close();
    }
} else if (MODE === 'nosx') {
    for (const mobile of [false, true]) {
        const page = await (await ctxOf(mobile)).newPage();
        const errors = [];
        watch(page, errors);
        await page.goto(`${viewer}/bc#/san-xuat`);
        const tag = `[không sx${mobile ? ' 390' : ''}]`;
        try {
            await settle(page);
            const d = await api(page);
            const k = await txt(page, '#sh-kpis');
            check(`${tag} API available false, meta.sx false`, d.available === false && d.meta.sx === false, JSON.stringify(d.meta));
            check(`${tag} màn báo "Chưa có số liệu ghi hộp" + app sx chưa cài`, k.includes('Chưa có số liệu ghi hộp') && k.includes('app sx'), k);
            check(`${tag} các khối khác trống, ô chọn tháng còn`, !(await txt(page, '#sh-days')) && !(await txt(page, '#sh-items'))
                && !!(await page.$('#sh-thang')));
            const c = await apiCmp(page);
            check(`${tag} khối đối chiếu: API available false, sx false → khối ẩn, không thêm lời nào`, c.available === false && c.meta?.sx === false
                && await page.$eval('#sh-cmp-sec', (e) => e.hidden) && !(await txt(page, '#sh-cmp')) && !(await page.isVisible('#sh-cmp-title')),
                JSON.stringify(c).slice(0, 200));
        } catch (e) { check(`${tag} kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        const o = await overflow(page);
        check(`${tag} không cuộn ngang (${o}px)`, o <= 1);
        check(`${tag} không lỗi JS / HTTP`, errors.length === 0, errors.join(' | '));
        await page.context().close();
    }
} else {
    await setHidden(await (await ctxOf(false)).newPage(), ['san-xuat'], false).catch(() => {});
    for (const [role, base] of [['người xem', viewer], ['quản trị', admin]]) {
        for (const mobile of [false, true]) {
            const page = await (await ctxOf(mobile)).newPage();
            const errors = [];
            watch(page, errors);
            console.log(`\n— ${role} · ${mobile ? 'điện thoại 390px' : 'desktop 1366px'}`);
            await page.goto(`${base}/bc#/san-xuat`);
            try { await scenario(page, mobile, role); } catch (e) { check(`[${role}${mobile ? ' 390' : ''}] kịch bản chạy hết`, false, e.message.split('\n')[0]); }
            const o = await overflow(page);
            check(`[${role}${mobile ? ' 390' : ''}] không cuộn ngang trang (${o}px)`, o <= 1);
            check(`[${role}${mobile ? ' 390' : ''}] không lỗi JS / HTTP`, errors.length === 0, errors.join(' | '));
            if (SHOTS) await page.screenshot({ path: `${SHOTS}/san-xuat-${role === 'quản trị' ? 'a' : 'v'}-${mobile ? 'm' : 'd'}.png`, fullPage: true });
            await page.context().close();
        }
    }

    // ── Quản trị ẩn mảng → người xem mất menu, route, API 403; quản trị vẫn thấy ──
    console.log('\n— Ẩn mảng Báo cáo sản xuất');
    const A = await (await ctxOf(false)).newPage();
    const V = await (await ctxOf(false)).newPage();
    try {
        const r = await setHidden(A, ['san-xuat'], true);
        check('quản trị ẩn mảng san-xuat', r.status() === 200, r.status());
        await V.goto(`${viewer}/bc#/san-xuat`);
        await V.waitForFunction(() => location.hash !== '#/san-xuat', null, { timeout: 15000 });
        await V.waitForSelector('#bc-sidebar .bc-side-link', { timeout: 15000 });
        check('người xem: mở #/san-xuat bị đưa về trang đầu, menu không còn mục', !(await V.$('a[data-route="/san-xuat"]'))
            && !(await V.textContent('#bc-sidebar')).includes('Báo cáo sản xuất') && (await V.$('a[data-route="/sx-tet"]')) !== null, V.url());
        for (const [m, a] of [['bc.api.sx_hop.get_overview', {}], ['bc.api.sx_hop.get_day', { date: '2026-10-02' }],
            ['bc.api.sx_hop.get_compare', {}]]) {
            const x = await post(V, m, a);
            check(`người xem: ${m} → 403`, x.status === 403 && !x.j.message, `${x.status} ${JSON.stringify(x.j).slice(0, 200)}`);
        }
        await A.goto(`${admin}/bc#/san-xuat`);
        await settle(A);
        check('quản trị: vẫn mở được, menu có dấu "đang ẩn"', (await A.$('#bc-sidebar a[data-route="/san-xuat"] .bc-side-hidden')) !== null
            && (await txt(A, '#sh-kpis')).includes('Tổng hộp tháng'));
        const x = await post(A, 'bc.api.sx_hop.get_overview', {});
        check('quản trị: API vẫn 200', x.status === 200 && x.j.message?.available === true, x.status);
    } catch (e) {
        check('ẩn mảng: kịch bản chạy hết', false, e.message.split('\n')[0]);
    } finally {
        await setHidden(A, ['san-xuat'], false).catch(() => {});
    }
    await V.goto(`${viewer}/bc#/san-xuat`);
    await settle(V).catch(() => {});
    check('mở lại mảng → người xem có lại màn + menu', (await V.$('a[data-route="/san-xuat"]')) !== null && (await txt(V, '#sh-kpis')).includes('Tổng hộp tháng'));
    await A.context().close();
    await V.context().close();

    // ── API lỗi (chặn tại trình duyệt): màn báo lỗi, ô chọn tháng còn để chọn lại ──
    console.log('\n— API lỗi');
    const E = await (await ctxOf(true)).newPage();
    const pe = [];
    E.on('pageerror', (e) => pe.push(e.message));
    await E.route('**/api/method/bc.api.sx_hop.get_overview*', (route) => route.fulfill({ status: 500, contentType: 'application/json',
        body: JSON.stringify({ exc_type: 'Exception', exception: 'Exception: hỏng thử' }) }));
    await E.goto(`${viewer}/bc#/san-xuat`);
    try {
        await E.waitForFunction(() => document.querySelector('#sh-kpis .bc-empty'), null, { timeout: 15000 });
        const k = await txt(E, '#sh-kpis');
        check('API lỗi: "Không tải được dữ liệu" + lời lỗi, ô chọn tháng còn, không pageerror', k.includes('Không tải được dữ liệu')
            && k.includes('hỏng thử') && !!(await E.$('#sh-thang')) && !pe.length, `${k} ${pe.join(' | ')}`);
        await E.waitForSelector('#sh-cmp-kpis', { timeout: 15000 });
        check('API tổng lỗi: khối đối chiếu vẫn hiện đủ (thẻ, bảng ngày, bảng mã), không bị xoá', !!(await E.$('#sh-cmp-day-table'))
            && !!(await E.$('#sh-cmp-item-table tbody tr')) && (await txt(E, '#sh-cmp-kpis')).includes('Chênh lệch'));
    } catch (e) { check('API lỗi: kịch bản chạy hết', false, e.message.split('\n')[0]); }
    await E.context().close();

    // ── Tổng lỗi đúng tháng vừa chọn: ô chọn tháng, khối đối chiếu và ↻ phải cùng MỘT tháng (không lùi ô chọn về tháng cũ
    //    trong khi khối hiện số của tháng mới) ──
    console.log('\n— Tổng lỗi khi đổi tháng');
    for (const mobile of [false, true]) {
        const M = await (await ctxOf(mobile)).newPage();
        const tg = `[tổng lỗi tháng 09${mobile ? ' 390' : ''}]`;
        await M.route('**/api/method/bc.api.sx_hop.get_overview*', (route) => (/thang=2026-09/.test(route.request().postData() || '')
            ? route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ exc_type: 'Exception', exception: 'Exception: tổng tháng 9 hỏng' }) })
            : route.continue()));
        await M.goto(`${viewer}/bc#/san-xuat`);
        try {
            await settle(M);
            const f = await F(M);
            await M.selectOption('#sh-thang', '2026-09');
            await M.waitForFunction(() => document.querySelector('#sh-kpis .bc-empty') && document.querySelector('#sh-cmp-kpis')
                && !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
            const c9 = await apiCmp(M, '2026-09');
            const lw = await lechText(f, c9.total.lech);
            const sel = await M.$eval('#sh-thang', (e) => e.value);
            const mon = await txt(M, '#sh-cmp-month');
            check(`${tg} tổng báo lỗi; ô chọn vẫn 09/2026 = tháng khối đối chiếu đang hiện ("${lw}"), khối ghi "Tháng 09/2026"`,
                (await txt(M, '#sh-kpis')).includes('tổng tháng 9 hỏng') && sel === '2026-09' && mon.startsWith('Tháng 09/2026')
                && (await txt(M, '#sh-cmp-lech')) === lw, `${sel} | ${mon} | ${await txt(M, '#sh-cmp-lech')}`);
            const creq = M.waitForRequest((r) => r.url().includes('sx_hop.get_compare'), { timeout: 15000 });
            await M.click('#sh-refresh');
            const body = (await creq).postData() || '';
            await M.waitForFunction(() => document.querySelector('#sh-cmp-kpis') && !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
            check(`${tg} ↻ tải lại khối đúng tháng 09/2026 (refresh=1), ô chọn vẫn 09/2026`, /thang=2026-09/.test(body) && /(^|&)refresh=1(&|$)/.test(body)
                && await M.$eval('#sh-thang', (e) => e.value) === '2026-09' && (await txt(M, '#sh-cmp-month')).startsWith('Tháng 09/2026'), body);
        } catch (e) { check(`${tg} kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        await M.context().close();
    }

    // ── Máy chủ tính hỏng (safe_block: available False + error, sx CÓ cài) ≠ "app sx chưa cài" ──
    console.log('\n— Máy chủ tính hỏng (error: true)');
    const R = await (await ctxOf(true)).newPage();
    const pe2 = [];
    R.on('pageerror', (e) => pe2.push(e.message));
    const errOv = { available: false, error: true, kpis: {}, days: [], items: [], groups: [], trend: [],
        meta: { thang: '2026-10', from: '2026-10-01', to: '2026-10-27', as_of: '2026-10-27', prev: '2026-09', months: [], sx: true, last_day: null } };
    await R.route('**/api/method/bc.api.sx_hop.get_overview*', (route) => route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ message: errOv }) }));
    await R.goto(`${viewer}/bc#/san-xuat`);
    try {
        await R.waitForFunction(() => document.querySelector('#sh-kpis .bc-empty'), null, { timeout: 15000 });
        const k = await txt(R, '#sh-kpis');
        check('error: true → "Không tải được số ghi hộp — quản trị xem Error Log", không nói "chưa cài", ô chọn tháng còn',
            k.includes('Không tải được số ghi hộp') && k.includes('Error Log') && !k.includes('chưa cài') && !!(await R.$('#sh-thang'))
            && !pe2.length, `${k} ${pe2.join(' | ')}`);
        await R.waitForSelector('#sh-cmp-kpis', { timeout: 15000 });
        check('tổng error: true → khối đối chiếu vẫn hiện đủ', !!(await R.$('#sh-cmp-day-table')) && !(await txt(R, '#sh-cmp')).includes('Không tải được'));
    } catch (e) { check('error: true: kịch bản chạy hết', false, e.message.split('\n')[0]); }
    // Chi tiết ngày tính hỏng: bảng tháng thật, get_day trả error → báo lỗi tải, không "không có số ghi hộp"
    await R.unroute('**/api/method/bc.api.sx_hop.get_overview*');
    await R.route('**/api/method/bc.api.sx_hop.get_day*', (route) => route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ message: { available: false, error: true, meta: { date: '2026-10-02', chot: false, co: false }, rows: [], total: {} } }) }));
    try {
        await R.reload();
        await R.waitForSelector('#sh-day-table tr.sh-day[data-date="2026-10-02"]', { timeout: 15000 });
        await R.click('#sh-day-table tr.sh-day[data-date="2026-10-02"]');
        await R.waitForFunction(() => document.querySelector('#sh-day-table .sh-detail-row .bc-empty, #sh-day-table .sh-detail-row .bc-muted'),
            null, { timeout: 15000 });
        const t = await txt(R, '#sh-day-table .sh-detail-row');
        check('chi tiết ngày error: true → "Không tải được chi tiết ngày", không "Không có số ghi hộp của ngày này"',
            t.includes('Không tải được chi tiết ngày') && !t.includes('Không có số ghi hộp') && !pe2.length, `${t} ${pe2.join(' | ')}`);
    } catch (e) { check('chi tiết ngày error: kịch bản chạy hết', false, e.message.split('\n')[0]); }
    await R.context().close();

    // ── Khối đối chiếu hỏng / chậm / dấu chữ — phần còn lại của màn không bị ảnh hưởng và ngược lại ──
    console.log('\n— Khối đối chiếu: hỏng, chậm, dấu');
    const restIntact = async (P) => (await txt(P, '#sh-kpis')).includes('Tổng hộp tháng') && !!(await P.$('#sh-day-table tr.sh-day'))
        && !!(await P.$('#sh-item-table tbody tr')) && !!(await P.$('#sh-trend-chart'));
    const variants = [
        ['HTTP 500', (route) => route.fulfill({ status: 500, contentType: 'application/json',
            body: JSON.stringify({ exc_type: 'Exception', exception: 'Exception: đối chiếu hỏng thử' }) }),
            (t) => t.includes('Không tải được phần đối chiếu') && t.includes('đối chiếu hỏng thử')],
        ['error: true', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: {
            available: false, error: true, meta: { thang: '2026-10', from: '2026-10-01', to: '2026-10-27', as_of: '2026-10-27', sx: true, so_ngay_cho: 30 },
            total: {}, days: [], items: [], cho_nhap: { available: false }, cho_duyet: { available: false }, no_vao_hop: { available: false } } }) }),
            (t) => t.includes('Không tải được phần đối chiếu — quản trị xem Error Log') && !t.includes('chưa cài')],
    ];
    for (const mobile of [false, true]) {
        for (const [name, handler, okText] of variants) {
            const P = await (await ctxOf(mobile)).newPage();
            const pe3 = [];
            P.on('pageerror', (e) => pe3.push(e.message));
            await P.route('**/api/method/bc.api.sx_hop.get_compare*', handler);
            await P.goto(`${viewer}/bc#/san-xuat`);
            const tg = `[đối chiếu ${name}${mobile ? ' 390' : ''}]`;
            try {
                await settle(P);
                const t = await txt(P, '#sh-cmp');
                check(`${tg} khối báo lỗi riêng, phần còn lại của màn vẫn đủ số`, okText(t) && await restIntact(P) && !pe3.length
                    && !(await P.$('#sh-cmp-kpis')), `${t} ${pe3.join(' | ')}`);
                const o = await overflow(P);
                check(`${tg} không cuộn ngang (${o}px)`, o <= 1);
            } catch (e) { check(`${tg} kịch bản chạy hết`, false, e.message.split('\n')[0]); }
            await P.context().close();
        }
    }
    // Chậm: khối đối chiếu chậm không chặn phần trên; phần trên chậm không chặn khối đối chiếu
    for (const [slow, other, label] of [['get_compare', '#sh-kpis .sh-kpi-grid', 'đối chiếu chậm → phần trên hiện trước'],
        ['get_overview', '#sh-cmp-kpis', 'tổng chậm → khối đối chiếu hiện trước']]) {
        const P = await (await ctxOf(false)).newPage();
        let release;
        const gate = new Promise((r) => { release = r; });
        await P.route(`**/api/method/bc.api.sx_hop.${slow}*`, async (route) => { await gate; await route.continue(); });
        await P.goto(`${viewer}/bc#/san-xuat`);
        try {
            await P.waitForSelector(other, { timeout: 15000 });
            const sk = slow === 'get_compare' ? '#sh-cmp .bc-skeleton' : '#sh-kpis .bc-skeleton';
            check(`[chậm] ${label}, khối kia còn khung chờ`, !!(await P.$(sk)));
            release();
            await settle(P);
            check(`[chậm] ${label}: rồi cả hai cùng có số`, !!(await P.$('#sh-cmp-kpis')) && (await txt(P, '#sh-kpis')).includes('Tổng hộp tháng'));
        } catch (e) { release(); check(`[chậm] ${label}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        await P.context().close();
    }
    // Dấu + chữ của thẻ Chênh lệch (sửa payload THẬT): dương → "+30 hộp · nhập vượt số ghi", 0 → "0 · khớp"; % giữ dấu;
    // khối "hiện tại" available False → "—"; compare báo sx False (phần trên vẫn có) → khối ẩn.
    const tweak = (fn) => async (route) => {
        const r = await route.fetch();
        const j = await r.json();
        fn(j.message);
        await route.fulfill({ response: r, body: JSON.stringify(j) });
    };
    for (const [name, fn, test] of [
        ['dương', (m) => { m.total.lech = 30; m.total.lech_pct = 1.4; }, async (P) => (await txt(P, '#sh-cmp-lech')) === '+30 hộp · nhập vượt số ghi'
            && (await txt(P, '#sh-cmp-pct')) === '+1,4%' && await P.$eval('#sh-cmp-lech', (e) => e.className) === 'sh-cmp-pos'],
        ['âm', (m) => { m.total.lech = -120; m.total.lech_pct = -5.25; }, async (P) => (await txt(P, '#sh-cmp-lech')) === '−120 hộp · chưa nhập kho'
            && (await txt(P, '#sh-cmp-pct')) === '−5,3%'],
        ['bằng 0', (m) => { m.total.lech = 0; m.total.lech_pct = 0; }, async (P) => (await txt(P, '#sh-cmp-lech')) === '0 · khớp'
            && (await txt(P, '#sh-cmp-pct')) === '0,0%' && await P.$eval('#sh-cmp-lech', (e) => e.className) === 'sh-cmp-zero'],
        ['ghi hộp 0', (m) => { m.total.lech_pct = null; }, async (P) => (await txt(P, '#sh-cmp-pct')) === '—'],
        ['hiện tại không tính được', (m) => { m.cho_nhap = { available: false }; m.cho_duyet = { available: false, error: true }; m.no_vao_hop = { available: false }; },
            async (P) => (await txt(P, '#sh-now-chonhap')) === 'Đã ghi hộp, chưa nhập kho—' && (await txt(P, '#sh-now-choduyet')) === 'Phiếu nhập chờ thủ kho duyệt— Không tính được'
                && (await txt(P, '#sh-now-novaohop')) === 'Kho nhận vượt số ghi hộp—' && !!(await P.$('#sh-cmp-kpis'))],
        ['không nợ vào hộp', (m) => { Object.assign(m.no_vao_hop, { count: 0, so_ma: 0, qty: 0, so_ma_khac_dvt: 0, oldest_age_days: null, rows: [] }); },
            async (P) => (await txt(P, '#sh-now-novaohop')) === 'Kho nhận vượt số ghi hộp0 hộp Không có khoản nào đang chờ chấm'],
        ['chỉ nợ mã khác đơn vị', (m) => { Object.assign(m.no_vao_hop, { count: 0, so_ma: 0, qty: 0, so_ma_khac_dvt: 2, oldest_age_days: null }); },
            async (P) => (await txt(P, '#sh-now-novaohop')) === 'Kho nhận vượt số ghi hộp0 hộp Không có khoản hộp nào đang chờ chấm · 2 mã đơn vị khác không cộng'],
        // Phiếu nháp lẫn đơn vị (Hộp + Kg): máy chủ trả qty / uom null như Nhập TP → không được hiện "— hộp" như một số hộp.
        ['chờ duyệt lẫn đơn vị', (m) => { m.cho_duyet.qty = null; m.cho_duyet.uom = null; },
            async (P) => { const t = await txt(P, '#sh-now-choduyet');
                return /^Phiếu nhập chờ thủ kho duyệt\d+ phiếu nhiều đơn vị kho, không cộng/.test(t) && !t.includes('—'); }],
        ['sx False', (m) => { m.available = false; m.meta.sx = false; },
            async (P) => await P.$eval('#sh-cmp-sec', (e) => e.hidden) && !(await txt(P, '#sh-cmp')) && await restIntact(P)],
        // Máy chủ: phần tháng hỏng vẫn tính riêng ba khối hiện tại (safe_block từng khối) → báo lỗi + dải hiện tại vẫn có số.
        ['phần tháng hỏng, hiện tại còn', (m) => { Object.assign(m, { available: false, error: true, total: {}, days: [], items: [] }); },
            async (P) => (await txt(P, '#sh-cmp')).includes('Không tải được phần đối chiếu — quản trị xem Error Log')
                && !(await P.$('#sh-cmp-kpis')) && !(await P.$('#sh-cmp-day-table'))
                && /^Đã ghi hộp, chưa nhập kho[\d.,]+ hộp/.test(await txt(P, '#sh-now-chonhap')) && await restIntact(P)],
        ['bảng thiếu', (m) => { m.available = false; },
            async (P) => (await txt(P, '#sh-cmp')).includes('Chưa đối chiếu được') && await restIntact(P)],
    ]) {
        const P = await (await ctxOf(true)).newPage();
        await P.route('**/api/method/bc.api.sx_hop.get_compare*', tweak(fn));
        await P.goto(`${viewer}/bc#/san-xuat`);
        try {
            await settle(P);
            check(`[dấu] ${name}`, await test(P), await txt(P, '#sh-cmp-kpis') + ' | ' + await txt(P, '#sh-cmp-now'));
        } catch (e) { check(`[dấu] ${name}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        await P.context().close();
    }
}

await browser.close();
console.log(`\n${total - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
