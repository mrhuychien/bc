// Kiểm màn #/ton-kho thật (import map + view thật + API Python thật trên MariaDB) ở desktop 1366px và điện thoại 390px.
// node ui_kho_ton.mjs <baseUrl>
// Số trên màn so với CHÍNH payload API gọi trong trang (định dạng bằng lib/format.js thật) — không cố định số của seed,
// để chạy được trên seed gộp của cả nhóm Kho. Bắt pageerror, console error, response >= 400, cuộn ngang ở 390px.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const base = process.argv[2] || 'http://127.0.0.1:8131';
const SHOTS = process.env.SHOTS || '';
let bad = 0, total = 0;
function check(label, ok, detail = '') {
    total++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 400)}`); }
}
const squash = (s) => (s || '').replace(/\s+/g, ' ').trim();

async function api(page, fn) {
    return page.evaluate((f) => fetch(`/api/method/bc.api.kho_ton.${f}`, { method: 'POST', body: new URLSearchParams({}) })
        .then((r) => r.json()).then((j) => j.message), fn);
}

/** Định dạng bằng lib/format.js THẬT trong trang (qua import map) — cùng hàm view dùng. */
async function fmt(page, kind, values) {
    return page.evaluate(async ([k, vs]) => {
        const f = await import('/assets/bc/bc/lib/format.js');
        const n1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
        const fn = { money: f.fmtMoney, num: f.fmtNum, num1: (v) => n1.format(v), pct: f.fmtPct }[k];
        return vs.map((v) => (v === null || v === undefined ? null : fn(v)));
    }, [kind, values]);
}

const monthLabel = (m) => `T${Number(m.slice(5))}/${m.slice(0, 4)}`;

async function scenario(page, mobile) {
    await page.waitForSelector('.bc-view-banner', { timeout: 15000 });
    await page.waitForSelector('#tk-kpis .bc-stat', { timeout: 20000 });
    await page.waitForSelector('#tk-nxt table', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
    const banner = squash(await page.textContent('.bc-view-banner'));
    check('banner "Tồn kho" + ngày số liệu', banner.includes('Tồn kho') && /Số đến \d\d\/\d\d\/\d{4}/.test(banner), banner);

    const d = await api(page, 'get_overview');
    const T = await api(page, 'get_trend');
    check('API overview + trend có dữ liệu', d.available && T.available && d.value.available && T.trend.available, JSON.stringify(d.meta));

    // ── KPI ──
    const t = d.value.totals;
    const [mTot, mSell, mUns] = await fmt(page, 'money', [t.value, t.value_sellable, t.value_unsellable]);
    const k = squash(await page.textContent('#tk-kpis'));
    check(`KPI khớp API: tổng ${mTot}, bán được ${mSell}, không bán được ${mUns}`,
        k.includes(`Tổng giá trị tồn ${mTot}`) && k.includes(`Bán được ${mSell}`) && k.includes(`Không bán được ${mUns}`), k);
    const tp = d.value.tp;
    const tpCard = squash(await page.textContent('#tk-kpis .bc-stat:nth-child(4)'));
    const tpHead = squash(await page.textContent('#tk-kpis .bc-stat:nth-child(4) .bc-stat-value'));
    if (tp.qty !== null && tp.cartons) {
        const [c1] = await fmt(page, 'num1', [tp.cartons]);
        const [q] = await fmt(page, 'num', [tp.qty]);
        check(`KPI thành phẩm: tiêu đề ${c1} thùng, dòng ${q} hộp`, tpHead === `${c1} thùng` && tpCard.includes(`${q} hộp`), tpCard);
    } else if (tp.qty !== null) {
        // Chưa quy được ra thùng (thùng = 0): tiêu đề là số hộp, không phải "0 thùng".
        const [q] = await fmt(page, 'num', [tp.qty]);
        check(`KPI thành phẩm chưa quy ra thùng: tiêu đề ${q} ${tp.uom}`, tpHead === `${q} ${(tp.uom || '').toLowerCase()}`, tpCard);
    } else {
        const [tv] = await fmt(page, 'money', [tp.value]);
        check(`KPI thành phẩm ${tp.items ? 'nhiều đơn vị' : 'chưa có hàng'}: tiêu đề tiền ${tv}`, tpHead === tv
            && tpCard.includes(tp.items ? 'Nhiều đơn vị' : 'Số mã còn hàng') && !(tp.items === 0 && tpCard.includes('Nhiều đơn vị')), tpCard);
    }

    // ── Khu vực kho / nhóm / mã lớn ──
    const role = squash(await page.textContent('#tk-role'));
    const roles = d.value.by_role.filter((r) => r.value || r.warehouses.length);
    const rv = await fmt(page, 'money', roles.map((r) => r.value));
    check(`khu vực kho: ${roles.length} dòng, nhãn + giá trị khớp API`, roles.every((r, i) => role.includes(r.label) && role.includes(rv[i]))
        && (await page.$$eval('#tk-role .bc-rank-row', (e) => e.length)) === roles.length, role);
    const whs = roles.flatMap((r) => r.warehouses);
    check('khu vực kho: liệt kê từng kho', whs.every((w) => role.includes(w.label)), role);
    const kt = d.value.kho_tp;
    const note = await page.$('#tk-role-khotp');
    check(`ghi chú kho thành phẩm ${kt.same ? 'ẩn (cùng tập kho)' : 'hiện (khác tập kho)'}`, kt.same ? !note : !!note
        && squash(await note.textContent()).includes((await fmt(page, 'money', [kt.value]))[0]), kt.same);
    const grp = squash(await page.textContent('#tk-group'));
    const gv = await fmt(page, 'money', d.value.by_group.map((r) => r.value));
    check('nhóm hàng: Tết / truyền thống / khác khớp API', d.value.by_group.every((r, i) => grp.includes(r.label) && grp.includes(gv[i])), grp);
    if (d.value.top.length) {
        const first = squash(await page.textContent('#tk-top tbody tr'));
        const [tv] = await fmt(page, 'money', [d.value.top[0].value]);
        check(`mã lớn nhất: ${d.value.top[0].short_name} ${tv}`, first.includes(d.value.top[0].short_name) && first.includes(tv), first);
        const n = await page.$$eval('#tk-top tbody tr', (e) => e.length);
        check('mã lớn: số dòng = API (≤ 10)', n === Math.min(10, d.value.top.length), n);
    }

    // ── Xu hướng ──
    const pts = T.trend.points;
    const [today, fy] = await fmt(page, 'money', [pts[pts.length - 1].value, T.trend.fy_start_value]);
    const tr = squash(await page.textContent('#tk-trend'));
    check(`xu hướng: hôm nay ${today}, đầu năm TC ${fy}`, tr.includes(today) && tr.includes(fy), tr);
    if (pts.every((p) => !p.value)) {
        check('biểu đồ: sổ trống → lời nhắn thay biểu đồ', tr.includes('Chưa có phát sinh sổ kho'), tr);
    } else {
        await page.waitForFunction(() => window.Chart && window.Chart.getChart(document.getElementById('tk-chart')), null, { timeout: 15000 });
        const chart = await page.evaluate(() => { const c = window.Chart.getChart(document.getElementById('tk-chart'));
            return { n: c.data.labels.length, w: c.width, sums: c.data.labels.map((_, i) => c.data.datasets.reduce((a, ds) => a + (ds.data[i] || 0), 0)) }; });
        check('biểu đồ: 13 cột, tổng mỗi cột = giá trị API', chart.n === pts.length && chart.w > 0
            && chart.sums.every((s, i) => Math.abs(s - pts[i].value) < 1), JSON.stringify(chart));
    }

    // ── Nhập – xuất – tồn ──
    const nx = T.nxt;
    const byM = Object.fromEntries(nx.months.map((m) => [m.month, m]));
    const closingRow = async () => squash(await page.textContent('#tk-nxt-table tr.bc-row-total'));
    const headTxt = async () => squash(await page.textContent('#tk-nxt-table thead'));
    const sel = await page.$eval('#tk-nxt-thang', (e) => e.value);
    const [c0, c1] = await fmt(page, 'money', [byM[nx.default_month].groups.all.closing, byM[nx.current_month].groups.all.closing]);
    let h = await headTxt(), cr = await closingRow();
    check(`NXT mặc định ${nx.default_month} + tháng này: cuối kỳ ${c0} / ${c1}`, sel === nx.default_month
        && h.includes(monthLabel(nx.default_month).toUpperCase()) && h.includes(monthLabel(nx.current_month).toUpperCase())
        && cr.includes(c0) && cr.includes(c1), `${h} | ${cr}`);
    const [o0] = await fmt(page, 'money', [byM[nx.default_month].groups.all.opening]);
    check('NXT dòng tồn đầu tháng khớp API', squash(await page.textContent('#tk-nxt-table tbody tr')).includes(o0));
    check('NXT ghi chú tháng này tính đến hôm nay', squash(await page.textContent('#tk-nxt-table')).includes(`${monthLabel(nx.current_month)} tính đến hôm nay`));
    const fit = await page.evaluate(() => {
        const sc = document.querySelector('#tk-nxt-table .bc-table-scroll');
        const r = sc.getBoundingClientRect();
        const cells = [...sc.querySelectorAll('tr')].map((tr) => tr.lastElementChild.getBoundingClientRect());
        return { sw: sc.scrollWidth, cw: sc.clientWidth, right: Math.round(r.right),
            out: cells.filter((b) => b.right > r.right + 1).length };
    });
    check(`NXT vừa khung${mobile ? ' ở 390px' : ''}: không cột nào bị giấu (${fit.sw}/${fit.cw}px)`, fit.sw <= fit.cw + 1 && fit.out === 0,
        JSON.stringify(fit));
    const other = nx.months[0].month;
    await page.selectOption('#tk-nxt-thang', other);
    await page.waitForFunction((m) => document.querySelector('#tk-nxt-table thead')?.textContent.includes(m), monthLabel(other).toUpperCase(), { timeout: 5000 });
    const [co] = await fmt(page, 'money', [byM[other].groups.all.closing]);
    cr = await closingRow();
    check(`NXT đổi sang ${other}: tiêu đề + cuối kỳ ${co} đổi theo`, cr.includes(co) && !(await headTxt()).includes(monthLabel(nx.default_month).toUpperCase()), cr);
    await page.click('#tk-nxt [data-tabs="tk-nxt"] [data-tab-key="traditional"]');
    const [ct] = await fmt(page, 'money', [byM[other].groups.traditional.closing]);
    await page.waitForFunction((v) => document.querySelector('#tk-nxt-table tr.bc-row-total')?.textContent.includes(v), ct, { timeout: 5000 })
        .catch(() => {});
    check(`NXT nhóm truyền thống: cuối kỳ ${ct}`, (await closingRow()).includes(ct), await closingRow());
    const flowRows = await page.$$eval('#tk-nxt-table tbody tr:not(.bc-row-total)', (e) => e.length);
    const nonzero = T.meta.loai.filter((l) => [byM[other], byM[nx.current_month]].some((m) => m.groups.traditional.flows[l.key])).length;
    check('NXT chỉ hiện các khoản có phát sinh (+ tồn đầu)', flowRows === nonzero + 1, `${flowRows} vs ${nonzero + 1}`);
    await page.selectOption('#tk-nxt-thang', nx.default_month);  // trả lại cho lượt sau

    // ── Số ngày tồn ──
    const doi = squash(await page.textContent('#tk-doi'));
    const o = d.doi;
    const [dd] = await fmt(page, 'num', [o.traditional.days]);
    check(`số ngày tồn truyền thống ${dd ?? '—'}`, o.traditional.days === null ? doi.includes('—') : doi.includes(`${dd} ngày`), doi);
    const [td] = await fmt(page, 'num', [o.tet.days]);
    if (o.tet.applicable) check(`Tết: ${td} ngày`, doi.includes(`${td} ngày`), doi);
    else if (o.tet.phase) check('Tết: ngoài mùa bán', doi.includes('Ngoài mùa bán') && !doi.includes('Chưa khai ngày Tết'), doi);
    else check('Tết: chưa khai ngày Tết → "—", không nói "ngoài mùa bán"', doi.includes('Chưa khai ngày Tết') && !doi.includes('Ngoài mùa bán'), doi);

    // ── Hàng chậm ──
    const s = d.slow;
    for (const key of ['tp', 'vat_tu', 'total']) {
        await page.click(`#tk-slow [data-tab-key="${key}"]`);
        const x = s[key];
        const [sv, dv, nv] = await fmt(page, 'money', [x.slow_value, x.dead_value, x.never_value]);
        const [sp, dp] = await fmt(page, 'pct', [x.slow_pct, x.dead_pct]);
        const txt = squash(await page.textContent('#tk-slow-body'));
        check(`hàng chậm [${key}]: % trên hàng bán được ${sp ?? '—'} / ${dp ?? '—'}`, txt.includes(`${sp ?? '—'} hàng bán được · gồm tồn chết`)
            && txt.includes(`${dp ?? '—'} hàng bán được`), txt.slice(0, 300));
        const rows = await page.$$eval('#tk-slow-body tbody tr', (e) => e.length);
        check(`hàng chậm [${key}]: chậm ${sv}, chết ${dv}, chưa xuất ${nv}, ${x.top.length} mã trong danh sách`,
            txt.includes(sv) && txt.includes(dv) && txt.includes(nv) && rows === (x.top.length ? Math.min(10, x.top.length) : 0)
            && x.top.every((r) => txt.includes(r.short_name)), txt.slice(0, 300));
    }
    await page.click('#tk-slow [data-tab-key="tp"]');

    // ── Tồn hàng Tết ──
    const tet = squash(await page.textContent('#tk-tet'));
    const [tv] = await fmt(page, 'money', [d.tet_stock.value]);
    check(`tồn hàng Tết: "${d.tet_stock.label}" ${tv}`, tet.includes(d.tet_stock.label) && tet.includes(tv), tet);

    // ── Sức khoẻ số liệu (thu gọn) ──
    const closed = await page.$eval('#tk-health-box', (e) => !e.open);
    await page.click('#tk-health-box summary');
    const hb = await page.evaluate(() => ({ open: document.getElementById('tk-health-box').open,
        badge: document.querySelector('#tk-health-box summary .bc-badge').textContent.trim(),
        items: document.querySelectorAll('#tk-health-box .bc-alert > div').length }));
    check(`sức khoẻ số liệu: thu gọn sẵn, mở ra ${hb.items} lưu ý khớp nhãn "${hb.badge}"`, closed && hb.open
        && (hb.items ? hb.badge === `${hb.items} lưu ý` : hb.badge === 'ổn'), JSON.stringify(hb));
    check('sức khoẻ: overview không tự quét sổ cho hàng ghi ngày tương lai', !('future_value' in d.health));
    if (T.trend.available && T.trend.future_value) {
        const [fv] = await fmt(page, 'money', [T.trend.future_value]);
        check(`sức khoẻ: hàng ghi ngày sau hôm nay ${fv} (từ xu hướng)`, squash(await page.textContent('#tk-health')).includes(`Có ${fv} hàng ghi sổ`));
    }
    await page.click('#tk-health-box summary');

    // ── Riêng tư ──
    const all = await page.textContent('.bc-main');
    check('không lộ email / người tạo trên màn', !all.includes('@'));
    check('không còn khung chờ, không báo lỗi tải', !all.includes('Không tải được') && !(await page.$('.bc-main .bc-skeleton')));
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
    await page.goto(`${base}/bc#/ton-kho`);
    try { await scenario(page, mobile); } catch (e) { check('kịch bản chạy hết', false, e.message.split('\n')[0]); }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`không cuộn ngang trang (${overflow}px)`, overflow <= 1);
    check('không lỗi JS / HTTP', errors.length === 0, errors.join(' | '));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/ton-kho-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    await ctx.close();
}
await browser.close();
console.log(`\n${total - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
