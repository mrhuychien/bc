// #/thoi-gian-thuc — Báo cáo thời gian thực: vận hành HÔM NAY + sơ đồ xưởng 3D có số liệu sống.
// Số liệu: bc.api.live.get_snapshot (cache 30s phía server); tự làm mới mỗi 60s khi tab đang mở
// và trang đang hiển thị. Sơ đồ 3D chạy trong iframe /bc_xuong (cùng origin) — gửi số liệu
// xuống bằng postMessage, bridge.js gắn bảng số + vòng sáng lên từng khu.

import { call } from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtMoney, fmtNum, growthClass, growthText } from '../lib/format.js';
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

/** Số liệu gắn lên từng khu của sơ đồ 3D (id phòng theo mô hình RVHG-Xuong-3D). */
function roomsPayload(d) {
    const s = d.sales, p = d.production;
    return {
        'main-pack': { lines: ['Sản xuất hôm nay', `${fmtNum(p.cartons)} thùng`], level: p.cartons > 0 ? 'hot' : 'idle',
            detail: [`SX hôm nay: ${fmtNum(p.cartons)} thùng`, `${fmtNum(p.boxes)} hộp`, `${p.vouchers} phiếu nhập`, `${p.items} mã`] },
        finished: { lines: ['Tồn kho thành phẩm', `${fmtNum(d.stock.cartons)} thùng`], level: 'ok',
            detail: [`Tồn: ${fmtNum(d.stock.boxes)} hộp`, `${fmtNum(d.stock.cartons)} thùng`, `Giá trị ${fmtMoney(d.stock.value)}`] },
        sales: { lines: ['Doanh số hôm nay', fmtMoney(s.sales)], level: s.orders > 0 ? 'hot' : 'idle',
            detail: [`DS hôm nay: ${fmtMoney(s.sales)}`, `${s.orders} hoá đơn · ${s.customers} khách`,
                `${s.return_orders} đơn trả · ${fmtMoney(s.returns)}`, `So cùng giờ hôm qua: ${growthText(s.growth)}`] },
        parking: { lines: ['Đơn chờ giao', `${fmtNum(d.pending.count)} đơn`], level: d.pending.count > 0 ? 'warn' : 'ok',
            detail: [`${d.pending.count} đơn bán chờ giao`, `Giá trị còn giao ${fmtMoney(d.pending.amount)}`] },
        materials: { lines: ['Nhập NVL hôm nay', `${fmtNum(d.purchases.count)} phiếu`], level: d.purchases.count > 0 ? 'hot' : 'idle',
            detail: [`${d.purchases.count} phiếu nhập mua`, fmtMoney(d.purchases.amount)] },
        // Phòng giám đốc sát phòng kinh doanh → nâng nhãn cao hơn để không chồng.
        director: { lines: ['Luỹ kế tháng', fmtMoney(d.mtd.sales)], level: 'ok', lift: 16,
            detail: [`Luỹ kế tháng: ${fmtMoney(d.mtd.sales)}`, `So cùng kỳ: ${growthText(d.mtd.growth)}`] },
    };
}

function sendTo3d() {
    const frame = document.getElementById('lv-3d');
    if (!frame?.contentWindow || !last) return;
    const d = last;
    const ticker = d.feed.slice(0, 10).map((e) => {
        const k = FEED[e.kind] || FEED.sale;
        const val = e.kind === 'production' ? `${fmtNum(e.boxes)} hộp` : fmtMoney(e.amount);
        return `<b>${escapeHtml(e.time)}</b> ${k.icon} ${escapeHtml(k.verb)} · ${escapeHtml(e.title || '')} — ${escapeHtml(val)}`;
    });
    frame.contentWindow.postMessage({
        type: 'bc-live', rooms: roomsPayload(d), ticker,
        headline: `TRỰC TIẾP · ${escapeHtml(d.meta.time)} · DS ${escapeHtml(fmtMoney(d.sales.sales))} · SX ${escapeHtml(fmtNum(d.production.cartons))} thùng`,
    }, location.origin);
}

function onFrameMessage(e) {
    if (e.origin === location.origin && e.data?.type === 'bc-3d-ready') sendTo3d();
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
            <div class="bc-lv-3d-card">
                <div class="bc-lv-card-head"><div><div class="bc-lv-title">🏭 Sơ đồ xưởng · số liệu sống trên từng khu</div>
                    <div class="bc-lv-muted">Kéo để xoay · bấm vào phòng để xem chi tiết · nút ⤢ trong khung để toàn màn hình</div></div></div>
                <iframe id="lv-3d" class="bc-lv-3d" src="/bc_xuong?v=${v}" title="Sơ đồ xưởng 3D RVHG" loading="lazy" allow="fullscreen" allowfullscreen></iframe>
            </div>
            <div class="bc-lv-grid">
                <div class="bc-lv-card"><div class="bc-lv-title">⚡ Hoạt động trong ngày</div><div id="lv-feed">${skeleton(48, 5, 6)}</div></div>
                <div class="bc-lv-col">
                    <div class="bc-lv-card"><div class="bc-lv-title">⏱️ Theo giờ hôm nay</div><div class="bc-chart-wrap"><canvas id="lv-hourly"></canvas></div></div>
                    <div class="bc-lv-card"><div class="bc-lv-title">🥇 Sản xuất nhiều nhất hôm nay</div><div id="lv-top">${skeleton(32, 4, 6)}</div></div>
                </div>
            </div>
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

