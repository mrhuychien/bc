// #/tong-quan — 4 thẻ tổng quan + 4 thẻ kênh + 3 doughnut (ngành hàng, kênh, top KH).
// Các khối tải song song, khối nào về trước vẽ trước.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtMoney, fmtMoneyFull, fmtPct } from '../lib/format.js';
// Namespace (không import theo tên): tab mở trước deploy giữ format.js cũ chưa có export này.
import * as fmt from '../lib/format.js';
import { loadChartLib, chartRegistry, PALETTE } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
const CHANNEL_ICONS = { npp: '🚚', mt: '🏬', dulich: '🧳', showroom: '🏪', khac: '📦' };

function byPeriod(rows) { return Object.fromEntries(rows.map((r) => [r.period, r])); }
function money(v) { return `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function ptsDiff(cur, prev) {
    if (cur === null || prev === null || cur === undefined || prev === undefined) return '—';
    const d = Math.round((cur - prev) * 10) / 10;
    return `<span class="${d <= 0 ? 'bc-up' : 'bc-down'}">${d > 0 ? '+' : ''}${String(d).replace('.', ',')} điểm</span>`;
}

function summaryHtml(res) {
    const p = byPeriod(res.rows);
    const cur = p.current, sp = p.same_period, ly = p.last_year;
    const g = res.meta.growth || {};
    return `<div class="bc-grid bc-grid-4">
        ${statCard({ label: 'Doanh số bán ra', icon: '💰', value: money(cur.sales),
            rows: [['Cùng kỳ', money(sp.sales)], ['Cả năm ngoái', money(ly.sales)]], growth: g.sales })}
        ${statCard({ label: 'Trả về', icon: '↩️', value: money(cur.returns), tone: 'danger',
            rows: [['Cùng kỳ', money(sp.returns)], ['Cả năm ngoái', money(ly.returns)]], growth: g.returns })}
        ${statCard({ label: 'Thực bán', icon: '✅', value: money(cur.net), tone: 'success',
            rows: [['Cùng kỳ', money(sp.net)], ['Cả năm ngoái', money(ly.net)]], growth: g.net })}
        ${statCard({ label: 'Tỷ lệ trả', icon: '📉', value: fmtPct(cur.return_rate), tone: 'warning',
            rows: [['Cùng kỳ', fmtPct(sp.return_rate)], ['Cả năm ngoái', fmtPct(ly.return_rate)],
                ['So cùng kỳ', ptsDiff(cur.return_rate, sp.return_rate)]] })}
    </div>`;
}

function channelsHtml(res) {
    const get = (period, k) => res.rows.find((r) => r.period === period && r.channel_key === k) || {};
    // Showroom chỉ hiện khi có số (site chưa khai kênh Showroom trong PKD Settings → giữ 4 thẻ như cũ).
    const keys = ['npp', 'mt', 'dulich', 'showroom', 'khac'].filter((k) => k !== 'showroom'
        || ['current', 'same_period'].some((p) => get(p, k).sales || get(p, k).returns));
    return `<div class="bc-grid ${keys.length > 4 ? 'bc-grid-5' : 'bc-grid-4'}">${keys.map((k) => {
        const cur = get('current', k), sp = get('same_period', k);
        const g = sp.sales ? Math.round((cur.sales - sp.sales) / sp.sales * 1000) / 10 : null;
        return statCard({ label: cur.channel || k, icon: CHANNEL_ICONS[k], value: money(cur.sales),
            rows: [['Cùng kỳ', money(sp.sales)], ['Tỷ lệ trả', fmtPct(cur.return_rate)]], growth: g });
    }).join('')}</div>`;
}

async function doughnut(canvasId, labels, values) {
    const Chart = await loadChartLib();
    const el = document.getElementById(canvasId);
    if (!el) return;
    const total = values.reduce((a, b) => a + b, 0) || 1;
    charts.add(new Chart(el, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 2, borderColor: '#fff' }] },
        options: {
            cutout: '58%',
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
                tooltip: { callbacks: { label: (c) => `${c.label}: ${fmtMoney(c.raw)} (${fmtPct(c.raw / total * 100)})` } },
                datalabels: { display: (c) => c.dataset.data[c.dataIndex] / total >= 0.06, color: '#fff',
                    font: { weight: 700, size: 10 }, formatter: (v) => fmtPct(v / total * 100, 0) },
            },
        },
    }));
}

function chartCard(id, title) {
    return `<div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">${title}</div></div>
        <div class="bc-chart-wrap" id="${id}-wrap"><canvas id="${id}"></canvas></div></div>`;
}

function top(rows, n, labelKey) {
    const head = rows.slice(0, n);
    const rest = rows.slice(n).reduce((a, r) => a + (r.amount || 0), 0);
    const labels = head.map((r) => r[labelKey]);
    const values = head.map((r) => r.amount || 0);
    if (rest > 0) { labels.push('Khác'); values.push(rest); }
    return [labels, values];
}

export async function render({ container, isCurrent }) {
    charts.destroy();
    const fy = window.BC_CONTEXT?.fy;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Tổng quan kinh doanh</div>
                <div class="bc-view-banner-sub">Năm tài chính ${escapeHtml(fy?.label || '')} · so cùng kỳ năm trước</div></div>
            <span class="bc-view-banner-badge">NTC ${escapeHtml((fy?.start || '').slice(0, 4))}</span>
        </div>
        <div id="tq-summary">${skeletonGrid(4, 128)}</div>
        <div class="bc-section-title">Theo kênh</div>
        <div id="tq-channels">${skeletonGrid(4, 110)}</div>
        <div class="bc-section-title">Cơ cấu doanh số</div>
        <div class="bc-grid bc-grid-charts">
            ${chartCard('tq-c-groups', 'Ngành hàng')}${chartCard('tq-c-channels', 'Kênh bán')}${chartCard('tq-c-customers', 'Top khách hàng')}
        </div>
        ${fmt.salesBasisNote ? fmt.salesBasisNote() : ''}`;

    const block = (promise, onOk, targetId) => promise.then((res) => { if (isCurrent()) onOk(res); })
        .catch((err) => { if (isCurrent()) fill(targetId, errorState(err)); });

    await Promise.all([
        block(api.kd.summary(), (r) => fill('tq-summary', summaryHtml(r)), 'tq-summary'),
        block(api.kd.channels(), (r) => {
            fill('tq-channels', channelsHtml(r));
            const cur = r.rows.filter((x) => x.period === 'current' && x.sales > 0);
            if (!cur.length) return fill('tq-c-channels-wrap', emptyState({ title: 'Chưa có doanh số' }));
            return doughnut('tq-c-channels', cur.map((x) => x.channel), cur.map((x) => x.sales));
        }, 'tq-channels'),
        block(api.kd.itemGroups(), (r) => {
            if (!r.rows.length) return fill('tq-c-groups-wrap', emptyState({ title: 'Chưa có doanh số' }));
            const [l, v] = top(r.rows, 7, 'item_group');
            return doughnut('tq-c-groups', l, v);
        }, 'tq-c-groups-wrap'),
        block(api.kd.topCustomers(8), (r) => {
            if (!r.rows.length) return fill('tq-c-customers-wrap', emptyState({ title: 'Chưa có doanh số' }));
            return doughnut('tq-c-customers', r.rows.map((x) => x.customer), r.rows.map((x) => x.amount));
        }, 'tq-c-customers-wrap'),
    ]);
}
