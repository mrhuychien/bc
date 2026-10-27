// #/thoi-gian-thuc — Báo cáo thời gian thực: vận hành HÔM NAY + sơ đồ xưởng 3D có số liệu sống.
// Số liệu: bc.api.live.get_snapshot (cache 30s phía server); tự làm mới mỗi 60s khi tab đang mở
// và trang đang hiển thị. Sơ đồ 3D chạy trong iframe /bc_xuong (cùng origin) — gửi số liệu
// xuống bằng postMessage, bridge.js gắn bảng số + vòng sáng lên từng khu.

import { call } from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtNum, growthClass, growthText } from '../lib/format.js';
// Namespace (không import theo tên): tab mở trước deploy giữ format.js cũ chưa có export này.
import * as fmt from '../lib/format.js';
import { solarToLunar } from '../lib/lunar.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const REFRESH_SEC = 60;
const charts = chartRegistry();
const DOW = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
const FEED = {
    sale: { icon: '🧾', cls: 'sale', verb: 'Bán' },
    return: { icon: '↩️', cls: 'ret', verb: 'Trả hàng' },
    production: { icon: '🏭', cls: 'prod', verb: 'Nhập TP' },
    purchase: { icon: '🚚', cls: 'buy', verb: 'Nhập NVL' },
};
let timers = [];
let last = null;
const shown = {};   // giá trị đang hiển thị của từng KPI (để đếm số từ cũ → mới)

function stopTimers() { timers.forEach((t) => clearInterval(t)); timers = []; }

function countUp(id, to, fmt) {
    const el = document.getElementById(id);
    if (!el) return;
    const from = shown[id] ?? 0;
    shown[id] = to;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || from === to) { el.textContent = fmt(to); return; }
    const t0 = performance.now();
    const step = (t) => {
        const k = Math.min(1, (t - t0) / 900);
        const v = from + (to - from) * (1 - Math.pow(1 - k, 3));
        el.textContent = fmt(k < 1 ? v : to);
        if (k < 1 && el.isConnected) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

function delta(v, suffix) {
    return `<span class="${growthClass(v)}">${growthText(v)}</span> <span class="bc-lv-muted">${suffix}</span>`;
}

function tile(id, icon, label) {
    return `<div class="bc-lv-kpi"><div class="bc-lv-kpi-label"><span>${icon}</span>${label}</div>
        <div class="bc-lv-kpi-value" id="${id}">—</div><div class="bc-lv-kpi-sub" id="${id}-sub">&nbsp;</div></div>`;
}

function paintKpis(d) {
    const fmtCart = (v) => `${fmtNum(v)} thùng`;
    countUp('lv-sales', d.sales.sales, fmtMoney);
    fill('lv-sales-sub', delta(d.sales.growth, 'so cùng giờ hôm qua'));
    countUp('lv-orders', d.sales.orders, fmtNum);
    fill('lv-orders-sub', `${fmtNum(d.sales.customers)} khách · ${d.sales.return_orders ? `<span class="bc-down">${d.sales.return_orders} đơn trả</span>` : '0 đơn trả'}`);
    countUp('lv-prod', d.production.cartons, fmtCart);
    fill('lv-prod-sub', delta(d.production.growth, `· ${d.production.vouchers} phiếu`));
    countUp('lv-stock', d.stock.cartons, fmtCart);
    fill('lv-stock-sub', `${fmtNum(d.stock.boxes)} hộp · ${fmtMoney(d.stock.value)}`);
    countUp('lv-pending', d.pending.count, (v) => `${fmtNum(v)} đơn`);
    fill('lv-pending-sub', `Còn giao ${fmtMoney(d.pending.amount)}`);
    countUp('lv-mtd', d.mtd.sales, fmtMoney);
    fill('lv-mtd-sub', delta(d.mtd.growth, 'so cùng kỳ tháng trước'));
}

function paintFeed(d) {
    const canOpen = !!window.BC_CONTEXT?.isSysManager;
    if (!d.feed.length) { fill('lv-feed', emptyState({ icon: '🌅', title: 'Chưa có giao dịch hôm nay' })); return; }
    fill('lv-feed', `<ol class="bc-lv-feed">${d.feed.map((e, i) => {
        const k = FEED[e.kind] || FEED.sale;
        const val = e.kind === 'production' ? `${fmtNum(e.boxes)} hộp` : fmtMoney(e.amount);
        const title = escapeHtml(e.title || '');
        const name = canOpen ? `<a href="/app/${e.doctype}/${encodeURIComponent(e.doc)}" target="_blank" rel="noopener">${title}</a>` : title;
        return `<li class="bc-lv-ev bc-lv-${k.cls}" style="animation-delay:${i * 40}ms">
            <span class="bc-lv-ev-time">${escapeHtml(e.time)}</span><span class="bc-lv-ev-icon">${k.icon}</span>
            <div class="bc-lv-ev-body"><div class="bc-lv-ev-title">${name}</div><div class="bc-lv-ev-sub">${k.verb} · ${escapeHtml(e.sub || '')}</div></div>
            <b class="bc-lv-ev-val">${e.kind === 'return' ? '−' : ''}${val}</b></li>`;
    }).join('')}</ol>`);
}

function paintTop(d) {
    const top = d.production.top;
    if (!top.length) { fill('lv-top', emptyState({ icon: '🏭', title: 'Chưa có phiếu nhập thành phẩm hôm nay' })); return; }
    const max = Math.max(...top.map((t) => t.cartons || t.boxes), 1);
    fill('lv-top', `<div class="bc-lv-top">${top.map((t, i) => `
        <div class="bc-lv-top-row"><span class="bc-lv-top-no">${i + 1}</span>
            <div style="min-width:0"><div class="bc-lv-top-name" title="${escapeHtml(t.item_name)}">${escapeHtml(t.short_name)}</div>
                <div class="bc-progress bc-ok"><span style="width:${(t.cartons || t.boxes) / max * 100}%"></span></div></div>
            <b>${t.cartons ? `${fmtNum(t.cartons)} th` : `${fmtNum(t.boxes)} hộp`}</b></div>`).join('')}</div>`);
}

async function paintHourly(d) {
    const Chart = await loadChartLib().catch(() => null);
    const el = document.getElementById('lv-hourly');
    if (!Chart || !el) return;
    const used = d.hourly.sales.map((v, h) => (v || d.hourly.production[h] ? h : null)).filter((h) => h !== null);
    const from = Math.min(6, ...used), to = Math.max(21, ...used);
    const hours = Array.from({ length: to - from + 1 }, (_, i) => from + i);
    const nowH = Number((d.meta.time || '0').slice(0, 2));
    charts.destroy();
    charts.add(new Chart(el, {
        data: {
            labels: hours.map((h) => `${h}h`),
            datasets: [
                { type: 'bar', label: 'Sản xuất (thùng)', data: hours.map((h) => d.hourly.production[h]), yAxisID: 'y1',
                    backgroundColor: hours.map((h) => (h === nowH ? '#f59e0b' : 'rgba(245,158,11,.55)')), borderRadius: 5 },
                { type: 'line', label: 'Doanh số', data: hours.map((h) => d.hourly.sales[h]), yAxisID: 'y',
                    borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,.18)', fill: true, tension: .35, pointRadius: 2 },
            ],
        },
        options: {
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'bottom', labels: { color: '#cbd5e1' } },
                tooltip: { callbacks: { label: (c) => (c.dataset.yAxisID === 'y' ? `Doanh số: ${fmtMoney(c.raw)}` : `Sản xuất: ${fmtNum(c.raw)} thùng`) } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,.12)' } },
                y: { position: 'left', ticks: { color: '#7dd3fc', callback: (v) => fmtMoney(v) }, grid: { color: 'rgba(148,163,184,.12)' } },
                y1: { position: 'right', ticks: { color: '#fcd34d' }, grid: { display: false } },
            },
        },
    }));
}

// ─── Số liệu THEO KHU cho card chi tiết khi bấm vào sơ đồ 3D ─────────────────
// id khu theo mô hình RVHG-Xuong-3D; bridge.js gửi danh sách khu thật (id, tên, nhóm) khi sẵn sàng.
// Khu không có số liệu phù hợp (WC, thay đồ, trạm biến áp…) → card chỉ hiện mô tả của mô hình.
const PROCESS_ZONES = new Set(['roast', 'shell', 'grind', 'cook', 'mix', 'roll', 'powder', 'left-pack']);
let zones = [];

const toneOf = (g) => (g === null || g === undefined ? '' : (g >= 0 ? 'up' : 'down'));
const plain = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd');
/** Chuẩn hoá tên kho/khu để khớp: bỏ dấu, bỏ hậu tố công ty " - ABC", bỏ chữ "kho"/"phòng" đầu, bỏ ký hiệu. */
function normName(s) {
    return plain(s).replace(/\s+-\s+[a-z0-9]{1,8}$/, '').replace(/[·•().,/_-]+/g, ' ')
        .replace(/^\s*(kho|phong)\s+/, '').replace(/\s+/g, ' ').trim();
}
/** Kho ERPNext ứng với 1 khu trên sơ đồ ("Kho đường" ↔ "Kho đường - HGC"); ưu tiên khớp đúng tên. */
function matchWarehouse(title, warehouses) {
    const t = normName(title);
    if (!t) return null;
    let best = null;
    for (const w of warehouses || []) {
        for (const cand of [w.warehouse_name, w.name]) {
            const n = normName(cand);
            if (!n) continue;
            if (n === t) return w;
            if (n.length >= 3 && (t.includes(n) || n.includes(t)) && (!best || n.length > best.len)) best = { w, len: n.length };
        }
    }
    return best?.w || null;
}
const boxesOrCartons = (t) => (t.cartons ? `${fmtNum(t.cartons)} thùng` : `${fmtNum(t.boxes)} hộp`);

function prodInfo(d, isMain) {
    const p = d.production;
    return {
        title: 'Sản xuất hôm nay', headline: `${fmtNum(p.cartons)} thùng`, level: p.cartons > 0 ? 'hot' : 'idle', pin: isMain,
        scope: isMain ? 'Sản xuất hôm nay' : 'Sản xuất toàn xưởng hôm nay',
        tiles: [
            { label: 'Sản xuất hôm nay', value: `${fmtNum(p.cartons)} thùng`, sub: `${fmtNum(p.boxes)} hộp` },
            { label: 'So cùng giờ hôm qua', value: growthText(p.growth), tone: toneOf(p.growth), sub: `Hôm qua ${fmtNum(p.yesterday_same_time)} thùng` },
            { label: 'Phiếu nhập TP', value: fmtNum(p.vouchers), sub: `${fmtNum(p.items)} mã hàng` },
            { label: 'Giá trị nhập kho', value: fmtMoney(p.amount) },
        ],
        lists: [{ title: 'Sản xuất nhiều nhất hôm nay', empty: 'Chưa có phiếu nhập thành phẩm hôm nay',
            rows: p.top.slice(0, 5).map((t) => [t.short_name, boxesOrCartons(t)]) }],
        note: isMain ? `Nguồn: phiếu sản xuất (Manufacture + nhập thẳng, đã loại kiểm kê / dọn lô) nhập kho ${d.meta.warehouse} hôm nay.`
            : 'Số liệu chung toàn xưởng — hệ thống chưa ghi nhận sản lượng riêng theo công đoạn.',
    };
}

function finishedInfo(d) {
    const st = d.stock;
    return {
        title: 'Tồn kho thành phẩm', headline: `${fmtNum(st.cartons)} thùng`, level: 'ok', pin: true, scope: 'Tồn kho thành phẩm',
        tiles: [
            { label: 'Tồn kho', value: `${fmtNum(st.cartons)} thùng`, sub: `${fmtNum(st.boxes)} hộp` },
            { label: 'Giá trị tồn', value: fmtMoney(st.value) },
            { label: 'Số mã có tồn', value: fmtNum(st.items) },
            { label: 'Nhập kho hôm nay', value: `${fmtNum(d.production.cartons)} thùng` },
        ],
        lists: [{ title: 'Tồn nhiều nhất', empty: 'Kho đang trống', rows: (st.top || []).map((t) => [t.short_name, boxesOrCartons(t)]) }],
        note: `Kho ERPNext: ${d.meta.warehouse}`,
    };
}

function warehouseInfo(w) {
    return {
        title: w.warehouse_name, headline: fmtMoney(w.value), level: 'ok', pin: false, scope: 'Tồn kho hiện tại',
        tiles: [{ label: 'Giá trị tồn', value: fmtMoney(w.value) }, { label: 'Số mã có tồn', value: fmtNum(w.items) }],
        lists: [{ title: 'Giá trị tồn lớn nhất', empty: 'Kho đang trống',
            rows: (w.top || []).map((t) => [t.item_name, `${fmtNum(t.qty)} ${t.uom || ''}`.trim()]) }],
        note: `Kho ERPNext: ${w.name}`,
    };
}

function materialsInfo(d, w) {
    const pu = d.purchases;
    const base = w ? warehouseInfo(w) : { tiles: [], lists: [] };
    return {
        title: 'Nhập NVL hôm nay', headline: `${fmtNum(pu.count)} phiếu`, level: pu.count > 0 ? 'hot' : 'idle', pin: pu.count > 0,
        scope: 'Nhập nguyên vật liệu',
        tiles: [{ label: 'Phiếu nhập mua hôm nay', value: fmtNum(pu.count) }, { label: 'Giá trị nhập', value: fmtMoney(pu.amount) }, ...base.tiles],
        lists: [{ title: 'Phiếu nhập hôm nay', empty: 'Chưa có phiếu nhập mua hôm nay',
            rows: d.feed.filter((e) => e.kind === 'purchase').slice(0, 5).map((e) => [`${e.time} · ${e.title}`, fmtMoney(e.amount)]) }, ...base.lists],
        note: w ? base.note : 'Nguồn: Purchase Receipt hôm nay.',
    };
}

const ZONE_BUILDERS = {
    sales: (d) => {
        const s = d.sales;
        return {
            title: 'Doanh số hôm nay', headline: fmtMoney(s.sales), level: s.orders > 0 ? 'hot' : 'idle', pin: true, scope: 'Bán hàng hôm nay',
            tiles: [
                { label: 'Doanh số', value: fmtMoney(s.sales), sub: `Thực bán ${fmtMoney(s.net)}` },
                { label: 'So cùng giờ hôm qua', value: growthText(s.growth), tone: toneOf(s.growth), sub: `Hôm qua ${fmtMoney(s.yesterday_same_time)}` },
                { label: 'Hoá đơn', value: fmtNum(s.orders), sub: `${fmtNum(s.customers)} khách` },
                { label: 'Trả hàng', value: fmtMoney(s.returns), tone: s.returns ? 'warn' : '', sub: `${fmtNum(s.return_orders)} đơn` },
            ],
            lists: [
                { title: 'Theo kênh', empty: 'Chưa có đơn hôm nay', rows: (s.by_channel || []).map((c) => [c.channel, fmtMoney(c.amount)]) },
                { title: 'Khách mua nhiều nhất', empty: 'Chưa có đơn hôm nay', rows: (s.top_customers || []).map((c) => [c.customer, fmtMoney(c.amount)]) },
            ],
        };
    },
    accounting: (d) => {
        const s = d.sales;
        return {
            title: 'Hoá đơn hôm nay', headline: `${fmtNum(s.orders)} đơn`, level: 'ok', pin: false, scope: 'Chứng từ bán hàng hôm nay',
            tiles: [
                { label: 'Hoá đơn bán', value: fmtNum(s.orders) },
                { label: 'Hoá đơn trả', value: fmtNum(s.return_orders), tone: s.return_orders ? 'warn' : '' },
                { label: 'Thực bán', value: fmtMoney(s.net) },
                { label: 'Giá trị trả', value: fmtMoney(s.returns) },
            ],
            lists: [{ title: 'Hoá đơn mới nhất', empty: 'Chưa có hoá đơn hôm nay',
                rows: d.feed.filter((e) => e.kind === 'sale' || e.kind === 'return').slice(0, 5)
                    .map((e) => [`${e.time} · ${e.title}`, `${e.kind === 'return' ? '−' : ''}${fmtMoney(e.amount)}`, e.kind === 'return' ? 'warn' : '']) }],
        };
    },
    director: (d) => ({
        // Phòng giám đốc sát phòng kinh doanh → khung nổi (khi bật "Số liệu") đặt cao hơn để không chồng.
        title: 'Luỹ kế tháng', headline: fmtMoney(d.mtd.sales), level: 'ok', pin: true, lift: 16, scope: 'Điều hành',
        tiles: [
            { label: 'Luỹ kế tháng', value: fmtMoney(d.mtd.sales) },
            { label: 'So cùng kỳ tháng trước', value: growthText(d.mtd.growth), tone: toneOf(d.mtd.growth), sub: `Tháng trước ${fmtMoney(d.mtd.prev)}` },
            { label: 'Doanh số hôm nay', value: fmtMoney(d.sales.sales) },
            { label: 'Sản xuất hôm nay', value: `${fmtNum(d.production.cartons)} thùng` },
        ],
        note: `Cùng kỳ = ${fmtDate(d.mtd.prev_from)} → ${fmtDate(d.mtd.prev_to)} (cùng số ngày đã trôi).`,
    }),
    chairman: (d) => ({
        title: 'Luỹ kế năm tài chính', headline: fmtMoney(d.fy.sales), level: 'ok', pin: false, scope: 'Năm tài chính',
        tiles: [
            { label: 'Luỹ kế năm TC', value: fmtMoney(d.fy.sales) },
            { label: 'So cùng kỳ năm trước', value: growthText(d.fy.growth), tone: toneOf(d.fy.growth), sub: `Năm trước ${fmtMoney(d.fy.prev)}` },
            { label: 'Luỹ kế tháng', value: fmtMoney(d.mtd.sales) },
            { label: 'Giá trị tồn thành phẩm', value: fmtMoney(d.stock.value) },
        ],
        note: `Năm tài chính ${d.fy.label}.`,
    }),
    meeting: (d) => ({
        title: 'Toàn cảnh hôm nay', level: 'ok', pin: false, scope: 'Toàn cảnh hôm nay',
        tiles: [
            { label: 'Doanh số hôm nay', value: fmtMoney(d.sales.sales), tone: '', sub: `So cùng giờ hôm qua ${growthText(d.sales.growth)}` },
            { label: 'Sản xuất hôm nay', value: `${fmtNum(d.production.cartons)} thùng` },
            { label: 'Tồn kho thành phẩm', value: `${fmtNum(d.stock.cartons)} thùng` },
            { label: 'Đơn chờ giao', value: fmtNum(d.pending.count), tone: d.pending.overdue ? 'warn' : '' },
        ],
    }),
    guard: (d) => ({
        title: 'Ra vào cổng hôm nay', level: 'ok', pin: false, scope: 'Hàng ra vào hôm nay',
        tiles: [
            { label: 'Hàng bán ra', value: `${fmtNum(d.sales.orders)} đơn` },
            { label: 'Hàng trả về', value: `${fmtNum(d.sales.return_orders)} đơn` },
            { label: 'Nhập nguyên vật liệu', value: `${fmtNum(d.purchases.count)} phiếu` },
            { label: 'Nhập thành phẩm', value: `${fmtNum(d.production.vouchers)} phiếu` },
        ],
        lists: [{ title: 'Mới nhất', empty: 'Chưa có giao dịch hôm nay',
            rows: d.feed.slice(0, 5).map((e) => [`${e.time} · ${(FEED[e.kind] || FEED.sale).verb} · ${e.title}`,
                e.kind === 'production' ? `${fmtNum(e.boxes)} hộp` : fmtMoney(e.amount)]) }],
        note: 'Theo chứng từ trên ERPNext (không phải sổ bảo vệ).',
    }),
    parking: (d) => {
        const pe = d.pending;
        return {
            title: 'Đơn chờ giao', headline: `${fmtNum(pe.count)} đơn`, level: pe.overdue ? 'warn' : (pe.count ? 'hot' : 'ok'), pin: pe.count > 0,
            scope: 'Giao hàng',
            tiles: [
                { label: 'Đơn chờ giao', value: fmtNum(pe.count) },
                { label: 'Giá trị còn giao', value: fmtMoney(pe.amount) },
                { label: 'Quá hạn giao', value: fmtNum(pe.overdue), tone: pe.overdue ? 'down' : '' },
            ],
            lists: [{ title: 'Gần hạn giao nhất', empty: 'Không có đơn chờ giao',
                rows: (pe.top || []).map((o) => [`${fmtDate(o.delivery_date, true)} · ${o.customer}`, fmtMoney(o.amount), o.overdue ? 'warn' : '']) }],
            note: 'Nguồn: Sales Order đã duyệt, trạng thái chờ giao.',
        };
    },
};

function zonesPayload(d) {
    const out = {};
    for (const z of zones) {
        let info = null;
        if (z.id === 'main-pack') info = prodInfo(d, true);
        else if (PROCESS_ZONES.has(z.id)) info = prodInfo(d, false);
        else if (z.id === 'finished') info = finishedInfo(d);
        else if (z.id === 'materials') info = materialsInfo(d, matchWarehouse(z.title, d.warehouses));
        else if (ZONE_BUILDERS[z.id]) info = ZONE_BUILDERS[z.id](d);
        else if (/^kho\b/.test(plain(z.title)) || z.id === 'tools') {
            const w = matchWarehouse(z.title, d.warehouses);
            if (w) info = warehouseInfo(w);
        }
        if (info) out[z.id] = info;
    }
    return out;
}

function sendTo3d() {
    const frame = document.getElementById('lv-3d');
    if (!frame?.contentWindow || !last || !zones.length) return;
    const d = last;
    const ticker = d.feed.slice(0, 10).map((e) => {
        const k = FEED[e.kind] || FEED.sale;
        const val = e.kind === 'production' ? `${fmtNum(e.boxes)} hộp` : fmtMoney(e.amount);
        return `<b>${escapeHtml(e.time)}</b> ${k.icon} ${escapeHtml(k.verb)} · ${escapeHtml(e.title || '')} — ${escapeHtml(val)}`;
    });
    frame.contentWindow.postMessage({ type: 'bc-live', zones: zonesPayload(d), ticker, stamp: d.meta.time }, location.origin);
}

function onFrameMessage(e) {
    if (e.origin !== location.origin || e.data?.type !== 'bc-3d-ready') return;
    if (Array.isArray(e.data.zones) && e.data.zones.length) zones = e.data.zones;
    sendTo3d();
}

async function load(isCurrent) {
    const dot = document.getElementById('lv-dot');
    dot?.classList.add('bc-lv-busy');
    try {
        const d = await call('bc.api.live.get_snapshot');
        if (!isCurrent()) return;
        const first = !last;
        last = d;
        if (first) {
            fill('lv-kpis', `<div class="bc-lv-kpis">
                ${tile('lv-sales', '💰', 'Doanh số hôm nay')}${tile('lv-orders', '🧾', 'Đơn hàng hôm nay')}
                ${tile('lv-prod', '🏭', 'Sản xuất hôm nay')}${tile('lv-stock', '📦', 'Tồn kho thành phẩm')}
                ${tile('lv-pending', '🚚', 'Đơn chờ giao')}${tile('lv-mtd', '📈', 'Luỹ kế tháng')}</div>`);
        }
        paintKpis(d);
        paintFeed(d);
        paintTop(d);
        paintHourly(d);
        sendTo3d();
        fill('lv-updated', `Cập nhật ${escapeHtml(d.meta.time)}`);
    } catch (err) {
        if (!isCurrent()) return;
        if (!last) fill('lv-kpis', errorState(err));
        fill('lv-updated', 'Lỗi tải — thử lại sau');
    } finally {
        dot?.classList.remove('bc-lv-busy');
    }
}

function tickClock() {
    const now = new Date();
    const l = solarToLunar(now.getDate(), now.getMonth() + 1, now.getFullYear());
    fill('lv-clock', now.toLocaleTimeString('vi-VN', { hour12: false }));
    fill('lv-date', `${DOW[now.getDay()]}, ${now.toLocaleDateString('vi-VN')} · ${l.day}/${l.month} âm lịch`);
}

export async function render({ container, isCurrent }) {
    stopTimers();
    charts.destroy();
    last = null;
    Object.keys(shown).forEach((k) => delete shown[k]);
    window.removeEventListener('message', onFrameMessage);
    window.addEventListener('message', onFrameMessage);
    const v = encodeURIComponent(window.BC_CONTEXT?.assetVersion || '');
    container.innerHTML = `
        <section class="bc-lv">
            <div class="bc-lv-hero">
                <div>
                    <div class="bc-lv-eyebrow"><span class="bc-lv-dot" id="lv-dot"></span>TRỰC TIẾP · BÁO CÁO THỜI GIAN THỰC</div>
                    <div class="bc-lv-clock" id="lv-clock">--:--:--</div>
                    <div class="bc-lv-date" id="lv-date"></div>
                </div>
                <div class="bc-lv-refresh">
                    <svg viewBox="0 0 36 36" class="bc-lv-ring"><circle cx="18" cy="18" r="15.5"/><circle cx="18" cy="18" r="15.5" id="lv-ring" style="stroke-dasharray:97.4;stroke-dashoffset:0"/></svg>
                    <div><div class="bc-lv-count" id="lv-count">${REFRESH_SEC}s</div><div class="bc-lv-updated" id="lv-updated">Đang tải…</div></div>
                </div>
            </div>
            <div id="lv-kpis">${skeleton(110, 1, 0)}</div>
            <div class="bc-lv-3d-head">
                <div class="bc-lv-title">🏭 Sơ đồ xưởng</div>
                <div class="bc-lv-muted">Chạm vào khu vực để xem số liệu · nút ▦ Số liệu bật khung số trên sơ đồ</div>
            </div>
            <iframe id="lv-3d" class="bc-lv-3d" src="/bc_xuong?v=${v}" title="Sơ đồ xưởng 3D RVHG" loading="lazy" allow="fullscreen" allowfullscreen></iframe>
            <div class="bc-lv-grid">
                <div class="bc-lv-card"><div class="bc-lv-title">⚡ Hoạt động trong ngày</div><div id="lv-feed">${skeleton(48, 5, 6)}</div></div>
                <div class="bc-lv-col">
                    <div class="bc-lv-card"><div class="bc-lv-title">⏱️ Theo giờ hôm nay</div><div class="bc-chart-wrap"><canvas id="lv-hourly"></canvas></div></div>
                    <div class="bc-lv-card"><div class="bc-lv-title">🥇 Sản xuất nhiều nhất hôm nay</div><div id="lv-top">${skeleton(32, 4, 6)}</div></div>
                </div>
            </div>
            ${fmt.salesBasisNote ? fmt.salesBasisNote() : ''}
        </section>`;
    document.getElementById('lv-3d')?.addEventListener('load', () => setTimeout(sendTo3d, 300));
    tickClock();
    let left = REFRESH_SEC;
    timers.push(setInterval(() => {
        if (!isCurrent() || !document.getElementById('lv-clock')) { stopTimers(); window.removeEventListener('message', onFrameMessage); return; }
        tickClock();
        if (document.hidden) return;   // tab ẩn: không đếm, không gọi API
        left -= 1;
        const ring = document.getElementById('lv-ring');
        if (ring) ring.style.strokeDashoffset = String(97.4 * (1 - left / REFRESH_SEC));
        fill('lv-count', `${left}s`);
        if (left <= 0) { left = REFRESH_SEC; load(isCurrent); }
    }, 1000));
    await load(isCurrent);
}

