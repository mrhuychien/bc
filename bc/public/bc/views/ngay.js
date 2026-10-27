// #/ngay — lịch doanh số tháng (âm lịch, tô đậm ngày ≥70% max) + tổng tháng +
// line chart bán/trả theo ngày + chi tiết đơn của ngày chọn. Đổi tháng → gọi
// kd.get_daily(year, month) (1 tháng/lần), chọn ngày → kd.get_orders(date).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, todayISO, salesBasisNote } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { renderCalendar } from '../components/calendar.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';

const charts = chartRegistry();
const state = { year: null, month: null, selected: null, rows: [] };

function monthKpis(rows) {
    const total = rows.reduce((a, r) => a + r.sales, 0);
    const days = rows.filter((r) => r.sales > 0).length;
    const best = rows.reduce((b, r) => (r.sales > (b?.sales || 0) ? r : b), null);
    return kpiGrid([
        { label: 'Tổng tháng', value: fmtMoney(total), sub: `Trả ${fmtMoney(rows.reduce((a, r) => a + r.returns, 0))}` },
        { label: 'TB / ngày bán', value: fmtMoney(days ? total / days : 0), sub: `${days} ngày có đơn` },
        { label: 'Cao nhất', value: fmtMoney(best?.sales || 0), sub: best ? fmtDate(best.date, true) : '—' },
    ]);
}

async function drawLine(rows) {
    charts.destroy();
    const el = document.getElementById('ng-line');
    if (!el) return;
    if (!rows.length) { fill('ng-line-wrap', emptyState({ title: 'Tháng này chưa có doanh số' })); return; }
    const Chart = await loadChartLib();
    if (!document.getElementById('ng-line')) return;
    const days = new Date(state.year, state.month, 0).getDate();
    const map = Object.fromEntries(rows.map((r) => [Number(r.date.slice(8, 10)), r]));
    const labels = Array.from({ length: days }, (_, i) => i + 1);
    charts.add(new Chart(el, {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Doanh số', data: labels.map((d) => map[d]?.sales || 0), borderColor: '#7c3aed',
                backgroundColor: 'rgba(124,58,237,.12)', fill: true, tension: .3, pointRadius: 2 },
            { label: 'Trả hàng', data: labels.map((d) => map[d]?.returns || 0), borderColor: '#ef4444',
                backgroundColor: 'rgba(239,68,68,.08)', fill: true, tension: .3, pointRadius: 2 },
        ] },
        options: {
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.raw)}` } } },
            scales: { y: { ticks: { callback: (v) => fmtMoney(v) } }, x: { ticks: { maxTicksLimit: 16 } } },
        },
    }));
}

function paintCalendar() {
    const el = document.getElementById('ng-cal');
    if (!el) return;
    const max = Math.max(0, ...state.rows.map((r) => r.sales));
    const cells = {};
    state.rows.forEach((r) => {
        if (!r.sales && !r.returns) return;
        cells[r.date] = { v1: fmtMoney(r.sales), hot: max > 0 && r.sales >= 0.7 * max,
            title: `Bán ${fmtMoneyFull(r.sales)} · Trả ${fmtMoneyFull(r.returns)} · ${r.orders} đơn` };
    });
    renderCalendar(el, {
        year: state.year, month: state.month, cells, selected: state.selected,
        onNav: (y, m) => loadMonth(y, m),
        onSelect: (iso) => { state.selected = iso; paintCalendar(); loadOrders(iso); },
    });
}

async function loadMonth(year, month) {
    state.year = year; state.month = month;
    history.replaceState(null, '', `#/ngay?m=${year}-${String(month).padStart(2, '0')}`);
    fill('ng-month-kpi', skeleton(70));
    try {
        const res = await api.kd.daily(year, month);
        state.rows = res.rows;
        const inMonth = (iso) => iso && iso.startsWith(`${year}-${String(month).padStart(2, '0')}`);
        if (!inMonth(state.selected)) {
            const today = todayISO();
            const withData = state.rows.filter((r) => r.orders || r.return_orders);
            state.selected = inMonth(today) ? today : (withData.length ? withData[withData.length - 1].date : null);
        }
        paintCalendar();
        fill('ng-month-kpi', monthKpis(state.rows));
        await Promise.all([drawLine(state.rows), state.selected ? loadOrders(state.selected) : clearOrders()]);
    } catch (err) {
        fill('ng-month-kpi', errorState(err));
        showToast(err.message, 'error');
    }
}

function clearOrders() {
    fill('ng-day-title', 'Chọn một ngày trên lịch');
    fill('ng-day-kpi', '');
    fill('ng-orders', emptyState({ icon: '📅', title: 'Chưa chọn ngày' }));
}

async function loadOrders(iso) {
    fill('ng-day-title', `Đơn hàng ngày ${fmtDate(iso)}`);
    fill('ng-orders', skeleton(44, 4, 6));
    try {
        const res = await api.kd.orders(iso);
        if (state.selected !== iso) return;
        const sales = res.rows.filter((r) => !r.is_return);
        const rets = res.rows.filter((r) => r.is_return);
        const total = sales.reduce((a, r) => a + r.amount, 0);
        fill('ng-day-kpi', kpiGrid([
            { label: 'Số đơn', value: fmtNum(sales.length), sub: fmtMoney(total) },
            { label: 'TB / đơn', value: fmtMoney(sales.length ? total / sales.length : 0) },
            { label: 'Đơn trả', value: fmtNum(rets.length), sub: fmtMoney(rets.reduce((a, r) => a + r.amount, 0)), cls: rets.length ? 'bc-txt-danger' : '' },
        ]));
        fill('ng-orders', dataTable({
            rows: res.rows, emptyMessage: 'Không có hoá đơn trong ngày', sortKey: 'posting_time', sortDir: 'desc',
            columns: [
                { key: 'name', label: 'Hoá đơn', align: 'left',
                    render: (r) => `<a href="/app/sales-invoice/${encodeURIComponent(r.name)}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a>` },
                { key: 'customer_name', label: 'Khách hàng', align: 'left' },
                { key: 'channel', label: 'Kênh', align: 'left' },
                { key: 'amount', label: 'Giá trị', render: (r) => `<span class="${r.is_return ? 'bc-txt-danger' : ''}">${r.is_return ? '−' : ''}${fmtNum(r.amount)}</span>` },
                { key: 'is_return', label: 'Loại', render: (r) => r.is_return ? '<span class="bc-badge bc-badge-danger">Trả</span>' : '<span class="bc-badge bc-badge-success">Bán</span>' },
                { key: 'posting_time', label: 'Giờ' },
            ],
        }));
    } catch (err) {
        fill('ng-orders', errorState(err));
    }
}

export async function render({ container, query }) {
    charts.destroy();
    const now = new Date();
    let year = now.getFullYear(), month = now.getMonth() + 1;
    const m = /^(\d{4})-(\d{2})$/.exec(query?.m || '');
    if (m) { year = Number(m[1]); month = Number(m[2]); }
    state.selected = null;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Doanh số theo ngày</div>
                <div class="bc-view-banner-sub">Bấm một ngày để xem đơn hàng · ô tím đậm = ngày ≥ 70% cao nhất tháng</div></div>
            <span class="bc-view-banner-badge">📅 Âm lịch</span>
        </div>
        <div class="bc-grid bc-grid-split" style="align-items:start">
            <div class="bc-card"><div id="ng-cal">${skeleton(360)}</div></div>
            <div>
                <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Tổng tháng</div></div><div id="ng-month-kpi">${skeleton(70)}</div></div>
                <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title" id="ng-day-title">Chọn một ngày trên lịch</div></div><div id="ng-day-kpi"></div></div>
            </div>
        </div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Doanh số & trả hàng theo ngày</div></div>
            <div class="bc-chart-wrap" id="ng-line-wrap"><canvas id="ng-line"></canvas></div></div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Chi tiết đơn hàng</div></div><div id="ng-orders"></div></div>
        ${salesBasisNote()}`;
    await loadMonth(year, month);
}
