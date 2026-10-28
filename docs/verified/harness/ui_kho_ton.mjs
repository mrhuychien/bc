// Kiểm màn #/ton-kho thật (import map + view thật + API Python thật trên MariaDB) ở desktop 1366px và điện thoại 390px.
// node ui_kho_ton.mjs <baseUrl>
// Số trên màn so với CHÍNH payload API gọi trong trang (định dạng bằng lib/format.js thật) — không cố định số của seed,
// để chạy được trên seed gộp của cả nhóm Kho. Bắt pageerror, console error, response >= 400, cuộn ngang ở 390px.
// Trạng thái seed không tạo được (khối lỗi máy chủ, sổ trống, chưa khai kho trả về, sức khoẻ lẫn đơn vị) dựng bằng cách sửa
// payload API thật trên đường về (page.route) — kiểm cách màn vẽ, không kiểm số.
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
    // UX-3: hai thẻ giữa đặt tên theo KHO (không "Bán được" / "Không bán được"), ghi chú chỉ sang trang Hạn dùng.
    check(`KPI khớp API: tổng ${mTot}, ngoài kho trả về & cách ly ${mSell}, kho trả về & cách ly ${mUns}`,
        k.includes(`Tổng giá trị tồn ${mTot}`) && k.includes(`Ngoài kho trả về & cách ly ${mSell}`) && k.includes(`Kho trả về & cách ly ${mUns}`)
        && !/Không bán được|Bán được/.test(k), k);
    const kn = squash(await page.textContent('#tk-kpi-note').catch(() => ''));
    check('KPI: ghi chú hàng hết hạn / thu hồi xem ở trang Hạn dùng', kn.includes('Hạn dùng & tồn âm') && kn.includes('hết hạn'), kn);
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
    if (tp.qty !== null) {
        // XC-5 / UX-9: "Chưa khai quy cách thùng" cùng MỘT số với dải sức khoẻ (mã không hệ số có tồn > 0), kèm đơn vị.
        const miss = tp.boxes_without_carton_in_stock;
        if (miss > 0) {
            const [mq, mn] = await fmt(page, 'num', [miss, tp.items_without_carton_in_stock]);
            check(`KPI thành phẩm: "Chưa khai quy cách thùng ${mq} ${(tp.uom || '').toLowerCase()} · ${mn} mã"`,
                tpCard.includes(`Chưa khai quy cách thùng${mq} ${(tp.uom || '').toLowerCase()} · ${mn} mã`) && !tpCard.includes('Chưa quy được'), tpCard);  // nhãn | số liền nhau trong textContent
        }
        check('KPI thành phẩm = dải sức khoẻ: cùng số hộp / số mã chưa khai quy cách thùng (API)',
            d.health.boxes_without_carton_factor === (tp.boxes_without_carton_in_stock ?? null)
            && d.health.items_without_carton_factor === tp.items_without_carton_in_stock,
            JSON.stringify([tp.boxes_without_carton_in_stock, tp.items_without_carton_in_stock, d.health.boxes_without_carton_factor,
                d.health.items_without_carton_factor]));
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
    // UX-4: dòng số lượng (mọi kho) ghi rõ "Mọi kho:", đứng trên dòng "Ngoài kho trả về & cách ly" (giá trị bán được).
    const gq = await fmt(page, 'num', d.value.by_group.map((r) => r.qty));
    const gAll = (await page.$$eval('#tk-group .tk-grp-all', (e) => e.map((x) => x.textContent.replace(/\s+/g, ' ').trim())));
    check('nhóm hàng: số lượng ghi "Mọi kho: …", giá trị bán được ghi "Ngoài kho trả về & cách ly"', gAll.length === d.value.by_group.length
        && d.value.by_group.every((r, i) => gAll[i].startsWith('Mọi kho:') && (r.qty === null || !r.items || gAll[i].includes(`${gq[i]} ${(r.uom || '').toLowerCase()}`)))
        && grp.includes('Ngoài kho trả về & cách ly') && !grp.includes('Ở kho bán được'), JSON.stringify(gAll));
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
    // UX-1 / XC-1: dòng phiếu kiểm kho mang nhãn mọi kho; ghi chú: kiểm kê sx chỉ lệch trang Kiểm kê do ngày ghi sổ ≠ ngày kiểm.
    const lb = Object.fromEntries(T.meta.loai.map((l) => [l.key, l.label]));
    const shown = [byM[nx.default_month], byM[nx.current_month]];
    const tbl = squash(await page.textContent('#tk-nxt-table'));
    if (shown.some((m) => m.groups.all.flows.kiem_ke_ch)) {
        check(`NXT dòng "${lb.kiem_ke_ch}"`, lb.kiem_ke_ch === 'Kiểm kê bằng phiếu kiểm kho (cửa hàng & kho khác)' && tbl.includes(lb.kiem_ke_ch)
            && !tbl.includes('Kiểm kê cửa hàng'), tbl.slice(0, 300));
    }
    if (shown.some((m) => m.groups.all.flows.kiem_ke_sx)) check(`NXT dòng "${lb.kiem_ke_sx}"`, lb.kiem_ke_sx === 'Kiểm kê sản xuất' && tbl.includes(lb.kiem_ke_sx));
    const nn = squash(await page.textContent('#tk-nxt-note').catch(() => ''));
    check('NXT ghi chú: kiểm kê sản xuất chỉ lệch trang Kiểm kê do phiếu ghi sổ khác tháng với ngày kiểm',
        nn.includes('chỉ lệch khi phiếu ghi sổ khác tháng với ngày kiểm') && nn.includes('ở mọi kho') && !nn.includes('có thể khác tháng so với trang Kiểm kê'), nn);
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
        check(`hàng chậm [${key}]: % trên giá trị tồn ${sp ?? '—'} / ${dp ?? '—'} (không nói "hàng bán được")`,
            txt.includes(`${sp ?? '—'} giá trị tồn · gồm tồn chết`) && txt.includes(`${dp ?? '—'} giá trị tồn`) && !txt.includes('hàng bán được'),
            txt.slice(0, 300));
        if (x.top.length) {
            // UX-13: số ngày chưa xuất + tình trạng nằm ngay dưới tên mã, thấy được không cần cuộn bảng (390px).
            const sorted = [...x.top].sort((a, b) => b.value - a.value);
            const [idle] = await fmt(page, 'num', [sorted[0].idle_days]);
            const want = `${idle} ngày · ${sorted[0].status === 'dead' ? 'Tồn chết' : 'Chậm'}`;
            const cell = await page.evaluate(() => {
                const td = document.querySelector('#tk-slow-body tbody tr td:first-child');
                const sc = td?.closest('.bc-table-scroll');
                const sub = td?.querySelector('.tk-slow-sub');
                if (!td || !sc || !sub) return null;
                const a = sub.getBoundingClientRect(), b = sc.getBoundingClientRect();
                return { text: sub.textContent.replace(/\s+/g, ' ').trim(), visible: a.left >= b.left - 1 && a.right <= b.right + 1 && a.width > 0 };
            });
            check(`hàng chậm [${key}]: dòng đầu ghi "${want}" ngay dưới tên mã, nằm trong khung`, !!cell && cell.text === want && cell.visible,
                JSON.stringify(cell));
        }
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
    // Ô "Số thùng" (XR-COMP-1 / NUM-1 còn lại): không bao giờ "0" + "… chưa khai"; đơn vị không đóng thùng → "—" + giải thích,
    // không nhắc "chưa khai"; "+ " chỉ khi có thùng.
    const ts = d.tet_stock;
    if (ts.qty !== null && ts.qty !== undefined) {
        const tile = await page.$eval('#tk-tet .bc-kpi:nth-child(3)', (e) => ({
            v: e.querySelector('.bc-kpi-value').textContent.trim(), sub: (e.querySelector('.bc-kpi-sub')?.textContent || '').replace(/\s+/g, ' ').trim() }));
        const unit = (ts.uom || '').toLowerCase();
        const miss = ts.boxes_without_carton_in_stock > 0 ? `${(await fmt(page, 'num', [ts.boxes_without_carton_in_stock]))[0]} ${unit} chưa khai quy cách thùng` : '';
        const want = ts.cartons ? { v: (await fmt(page, 'num1', [ts.cartons]))[0], sub: miss ? `+ ${miss}` : '' }
            : ts.cartons === null ? { v: '—', sub: `hàng tính theo ${unit}, không quy ra thùng` } : { v: '—', sub: miss };
        check(`tồn hàng Tết: ô Số thùng "${want.v}" / "${want.sub}"`, tile.v === want.v && tile.sub === want.sub, JSON.stringify(tile));
    }
    // Một luật đơn vị đóng thùng cho mọi khối và dải sức khoẻ: khối không tính thùng (cartons null) thì sức khoẻ không nhắc
    // đơn vị đó, và dòng nhóm không có chữ "thùng".
    const hU = new Set((d.health.without_carton_by_uom || []).map((u) => u.uom));
    const blk = [['tồn Tết', ts], ['thẻ thành phẩm', d.value.tp], ...d.value.by_group.map((r) => [`nhóm ${r.key}`, r])]
        .filter(([, b]) => b.qty !== null && b.qty !== undefined && b.uom);
    check('đơn vị đóng thùng: khối không tính thùng ⇔ sức khoẻ không nhắc đơn vị đó', blk.every(([, b]) => !(b.cartons === null && hU.has(b.uom))),
        JSON.stringify(blk.map(([n, b]) => [n, b.uom, b.cartons, b.boxes_without_carton_in_stock]).concat([[...hU]])));
    check('nhóm hàng: khối không tính thùng → dòng "Mọi kho" không có thùng / "chưa khai"', d.value.by_group.every((r, i) =>
        r.qty === null || r.cartons !== null || !/thùng|chưa khai/.test(gAll[i])), JSON.stringify(gAll));

    // ── Sức khoẻ số liệu (thu gọn) ──
    const closed = await page.$eval('#tk-health-box', (e) => !e.open);
    await page.click('#tk-health-box summary');
    const hb = await page.evaluate(() => ({ open: document.getElementById('tk-health-box').open,
        badge: document.querySelector('#tk-health-box summary .bc-badge').textContent.trim(),
        items: document.querySelectorAll('#tk-health-box .bc-alert > div').length }));
    check(`sức khoẻ số liệu: thu gọn sẵn, mở ra ${hb.items} lưu ý khớp nhãn "${hb.badge}"`, closed && hb.open
        && (hb.items ? hb.badge === `${hb.items} lưu ý` : hb.badge === 'ổn'), JSON.stringify(hb));
    check('sức khoẻ: overview không tự quét sổ cho hàng ghi ngày tương lai', !('future_value' in d.health));
    const hText = squash(await page.textContent('#tk-health'));
    if (d.health.failed_reposts) {
        const [nf] = await fmt(page, 'num', [d.health.failed_reposts]);
        check(`sức khoẻ: ${nf} lượt tính lại giá vốn bị LỖI (XR-REAL-3)`, hText.includes(`${nf} lượt tính lại giá vốn bị lỗi`), hText);
    }
    if (d.health.items_without_carton_factor) {
        const [n] = await fmt(page, 'num', [d.health.items_without_carton_factor]);
        const per = await fmt(page, 'num', (d.health.without_carton_by_uom || []).map((u) => u.qty));
        const want = `${n} mã thành phẩm còn hàng chưa khai quy cách thùng (${(d.health.without_carton_by_uom || []).map((u, i) => `${per[i]} ${(u.uom || '').toLowerCase()}`).join(', ')})`;
        check(`sức khoẻ: "${want}" (theo đơn vị)`, hText.includes(want), hText);
    }
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

/** Trạng thái seed không tạo được — sửa payload API THẬT trên đường về (route), kiểm cách màn vẽ. */
async function synthetic(browser) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const errors = [];
    async function open(ovEdit, trEdit) {
        const page = await ctx.newPage();
        page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
        page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
        const patch = (edit) => async (route) => {
            const resp = await route.fetch();
            const j = await resp.json();
            if (j.message) edit(j.message);
            await route.fulfill({ response: resp, json: j });
        };
        await page.route('**/api/method/bc.api.kho_ton.get_overview', patch(ovEdit));
        await page.route('**/api/method/bc.api.kho_ton.get_trend', patch(trEdit));
        await page.goto(`${base}/bc#/ton-kho`);
        await page.waitForSelector('#tk-kpis .bc-stat', { timeout: 20000 });
        await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 30000 });
        return page;
    }
    console.log('\n— Trạng thái tạo bằng cách sửa payload (390px)');
    // A. UX-6: khối lỗi máy chủ (safe_block → error) nói "Không tải được … lỗi hệ thống", không đổ cho thiếu dữ liệu.
    let page = await open((m) => { m.slow = { available: false, error: true }; m.health = { available: false, error: true }; },
        (m) => { m.trend = { available: false, error: true }; m.nxt = { available: false, error: true }; });
    const txt = async (sel) => squash(await page.textContent(sel));
    for (const [sel, what] of [['#tk-slow', 'hàng chậm luân chuyển'], ['#tk-trend', 'xu hướng giá trị tồn'], ['#tk-nxt', 'nhập – xuất – tồn'],
        ['#tk-health', 'sức khoẻ số liệu']]) {
        const t = await txt(sel);
        check(`khối lỗi ${sel}: "Không tải được ${what} lúc này (lỗi hệ thống…)", không "thiếu dữ liệu"`,
            t.includes(`Không tải được ${what} lúc này`) && t.includes('lỗi hệ thống') && !t.includes('thiếu dữ liệu'), t);
    }
    await page.close();
    // B. UX-11b sổ trống: không khung biểu đồ rỗng; UX-11c chưa xác định kho trả về / cách ly: "—" + lời nhắn, không phải 0;
    // NUM-1 sức khoẻ lẫn đơn vị: liệt kê từng đơn vị, không cộng.
    page = await open((m) => {
        const kb = m.value.by_role.find((r) => r.key === 'khong_ban');
        Object.assign(kb, { configured: false, value: 0, warehouses: [] });
        kb.roles.forEach((r) => Object.assign(r, { configured: false, value: 0 }));
        m.value.totals.value_unsellable = 0;
        Object.assign(m.health, { items_without_carton_factor: 2, boxes_without_carton_factor: null, uom_without_carton_factor: null,
            without_carton_by_uom: [{ uom: 'Gói', items: 1, qty: 208 }, { uom: 'Hộp', items: 1, qty: 10 }] });
    }, (m) => { m.trend.points.forEach((p) => Object.assign(p, { value: 0, tet: 0, traditional: 0, other: 0 })); });
    const card3 = await txt('#tk-kpis .bc-stat:nth-child(3)');
    const v3 = await txt('#tk-kpis .bc-stat:nth-child(3) .bc-stat-value');
    check('chưa xác định kho trả về / cách ly: thẻ hiện "—" + "Chưa xác định kho", không phải 0', v3 === '—' && card3.includes('Chưa xác định kho')
        && (await txt('#tk-kpi-note')).includes('Chưa xác định được kho trả về / cách ly'), `${card3} | ${v3}`);
    const tr = await txt('#tk-trend');
    const wrap = await page.evaluate(() => { const w = document.querySelector('#tk-trend .bc-chart-wrap'); return w ? w.getBoundingClientRect().height : 0; });
    check('sổ trống: lời nhắn thay biểu đồ, không để khung biểu đồ rỗng', tr.includes('Chưa có phát sinh sổ kho trong 12 tháng') && wrap === 0, `${wrap}px`);
    await page.click('#tk-health-box summary');
    const ht = await txt('#tk-health');
    check('sức khoẻ lẫn đơn vị: "2 mã … (208 gói, 10 hộp)" — không cộng gói với hộp',
        ht.includes('2 mã thành phẩm còn hàng chưa khai quy cách thùng (208 gói, 10 hộp)'), ht);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`trạng thái sửa payload: không cuộn ngang (${overflow}px)`, overflow <= 1);
    await page.close();
    // C. Tồn Tết Hộp (đơn vị đóng thùng) mà không mã nào khai thùng: thùng 0 → ô "—" + "50 hộp chưa khai quy cách thùng",
    // không "0" / "+ …"; nhóm Tết Kg không đóng thùng: "Mọi kho: 208 kg" (không "chưa khai").
    const carton = { cartons: 0, boxes_without_carton_factor: 50, items_without_carton_factor: 1, boxes_without_carton_in_stock: 50,
        items_without_carton_in_stock: 1 };
    const none = { cartons: null, boxes_without_carton_factor: null, items_without_carton_factor: null, boxes_without_carton_in_stock: null,
        items_without_carton_in_stock: null };
    page = await open((m) => {
        Object.assign(m.tet_stock, { qty: 50, uom: 'Hộp', items: 1, top: [], ...carton });
        Object.assign(m.value.by_group.find((r) => r.key === 'tet'), { qty: 208, uom: 'Kg', items: 1, ...none });
    }, () => {});
    const tile = await page.$eval('#tk-tet .bc-kpi:nth-child(3)', (e) => ({ v: e.querySelector('.bc-kpi-value').textContent.trim(),
        sub: (e.querySelector('.bc-kpi-sub')?.textContent || '').replace(/\s+/g, ' ').trim() }));
    check('tồn Tết chưa khai thùng mã nào: ô Số thùng "—" + "50 hộp chưa khai quy cách thùng" (không "0", không "+")',
        tile.v === '—' && tile.sub === '50 hộp chưa khai quy cách thùng', JSON.stringify(tile));
    const gTet = (await page.$$eval('#tk-group .tk-grp-all', (e) => e.map((x) => x.textContent.replace(/\s+/g, ' ').trim())))[0];
    check('nhóm Tết Kg không đóng thùng: "Mọi kho: 208 kg", không thùng / "chưa khai"', gTet === 'Mọi kho: 208 kg', gTet);
    await page.close();
    // D. Tồn Tết Kg không đóng thùng (cartons null): ô "—" + "hàng tính theo kg, không quy ra thùng".
    page = await open((m) => { Object.assign(m.tet_stock, { qty: 208, uom: 'Kg', items: 1, top: [], ...none }); }, () => {});
    const tile2 = await page.$eval('#tk-tet .bc-kpi:nth-child(3)', (e) => ({ v: e.querySelector('.bc-kpi-value').textContent.trim(),
        sub: (e.querySelector('.bc-kpi-sub')?.textContent || '').replace(/\s+/g, ' ').trim() }));
    check('tồn Tết Kg không đóng thùng: ô Số thùng "—" + "hàng tính theo kg, không quy ra thùng", không "chưa khai"',
        tile2.v === '—' && tile2.sub === 'hàng tính theo kg, không quy ra thùng', JSON.stringify(tile2));
    const ov2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`tồn Tết sửa payload: không cuộn ngang (${ov2}px)`, ov2 <= 1);
    await page.close();
    check('trạng thái sửa payload: không lỗi JS', errors.length === 0, errors.join(' | '));
    await ctx.close();
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
try { await synthetic(browser); } catch (e) { check('kịch bản sửa payload chạy hết', false, e.message.split('\n')[0]); }
await browser.close();
console.log(`\n${total - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
