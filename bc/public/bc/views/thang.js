// #/thang — bar chart 12 tháng năm TC (bắt đầu theo BC Settings): Năm nay /
// Cùng kỳ năm trước / Trả hàng, nhãn tỷ/tr trên cột + bảng tháng có tăng trưởng.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtMoney, fmtNum, growthClass, growthText, calcGrowth, salesBasisNote } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { dataTable } from '../components/data-table.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { skeleton } from '../components/skeleton.js';
import { errorState } from '../components/empty-state.js';

const charts = chartRegistry();

export async function render({ container, isCurrent }) {
    charts.destroy();
    const fy = window.BC_CONTEXT?.fy;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Doanh số theo tháng</div>
                <div class="bc-view-banner-sub">Năm tài chính ${escapeHtml(fy?.label || '')} so với năm trước</div></div>
            <span class="bc-view-banner-badge">12 tháng</span>
        </div>
        <div id="th-kpi">${skeleton(70)}</div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Năm nay · Cùng kỳ · Trả hàng</div></div>
            <div class="bc-chart-wrap bc-tall" id="th-wrap"><canvas id="th-bar"></canvas></div></div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Chi tiết tháng</div></div><div id="th-table">${skeleton(200)}</div></div>
        ${salesBasisNote()}`;
    let res;
    try {
        res = await api.kd.monthly();
    } catch (err) {
        fill('th-kpi', errorState(err));
        fill('th-wrap', '');
        fill('th-table', '');
        return;
    }
    if (!isCurrent()) return;
    const cur = res.rows.filter((r) => r.period === 'current');
    const ly = res.rows.filter((r) => r.period === 'last_year');
    const toMonth = Number((res.meta.fy.to_date || '').slice(5, 7));
    const elapsed = cur.findIndex((r) => r.month === toMonth) + 1 || 12;
    const sum = (arr, k, n = 12) => arr.slice(0, n).reduce((a, r) => a + r[k], 0);
    const curTotal = sum(cur, 'sales'), lyAligned = sum(ly, 'sales', elapsed);
    fill('th-kpi', kpiGrid([
        { label: 'Lũy kế năm nay', value: fmtMoney(curTotal), sub: `${elapsed} tháng` },
        { label: 'Cùng kỳ (tháng)', value: fmtMoney(lyAligned), sub: `<span class="${growthClass(calcGrowth(curTotal, lyAligned))}">${growthText(calcGrowth(curTotal, lyAligned))}</span>` },
        { label: 'Cả năm trước', value: fmtMoney(sum(ly, 'sales')), sub: `Trả ${fmtMoney(sum(ly, 'returns'))}` },
    ]));

    const Chart = await loadChartLib();
    if (!isCurrent() || !document.getElementById('th-bar')) return;
    const labels = cur.map((r) => `T${r.month}`);
    const small = window.innerWidth < 640;
    charts.add(new Chart(document.getElementById('th-bar'), {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Năm nay', data: cur.map((r) => r.sales), backgroundColor: '#7c3aed', borderRadius: 6 },
            { label: 'Cùng kỳ', data: ly.map((r) => r.sales), backgroundColor: '#c4b5fd', borderRadius: 6 },
            { label: 'Trả hàng', data: cur.map((r) => r.returns), backgroundColor: '#f87171', borderRadius: 6 },
        ] },
        options: {
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom' },
                tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.raw)}` } },
                datalabels: { display: (c) => !small && c.datasetIndex < 2 && c.dataset.data[c.dataIndex] > 0,
                    anchor: 'end', align: 'end', rotation: -90, offset: 2, font: { size: 9, weight: 700 },
                    color: '#4b5563', formatter: (v) => fmtMoney(v) },
            },
            layout: { padding: { top: small ? 0 : 36 } },
            scales: { y: { ticks: { callback: (v) => fmtMoney(v) } } },
        },
    }));

    const rows = cur.map((r, i) => ({ month: `T${r.month}`, fy_month: r.fy_month, sales: r.sales, sp: ly[i]?.sales || 0,
        returns: r.returns, growth: calcGrowth(r.sales, ly[i]?.sales || 0) }));
    fill('th-table', dataTable({
        rows, sortKey: 'fy_month', sortDir: 'asc', pageSize: 12, scrollButtons: false,
        columns: [
            { key: 'month', label: 'Tháng', align: 'left', sortValue: (r) => r.fy_month },
            { key: 'sales', label: 'Năm nay', render: (r) => fmtNum(r.sales) },
            { key: 'sp', label: 'Cùng kỳ', render: (r) => fmtNum(r.sp) },
            { key: 'growth', label: 'Tăng trưởng', render: (r) => `<span class="${growthClass(r.growth)}">${growthText(r.growth)}</span>` },
            { key: 'returns', label: 'Trả hàng', render: (r) => fmtNum(r.returns) },
        ],
        totalRow: { month: 'Tổng', sales: fmtNum(sum(cur, 'sales')), sp: fmtNum(sum(ly, 'sales')), returns: fmtNum(sum(cur, 'returns')) },
    }));
}
