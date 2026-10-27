// #/cong-no — Phải thu khách hàng: số dư sổ cái như Kế toán (quá hạn phân bổ FIFO), MT theo
// bảng kê chuỗi. Một lượt gọi bc.api.cn.get_receivables; tiền GỒM VAT (khác doanh số trước VAT).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, fmtPct } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
// Tuổi nợ: xanh (trong hạn) → vàng → cam → đỏ đậm; xám = chưa rõ hạn.
const BUCKET_COLORS = { current: '#10b981', b1: '#facc15', b2: '#f59e0b', b3: '#f97316', over: '#b91c1c', unknown: '#9ca3af' };

function money(v) { return `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }

function kpisHtml(d) {
    const k = d.kpis, dso = k.dso || {};
    return `<div class="bc-grid bc-grid-4">
        ${statCard({ label: 'Phải thu', icon: '💳', value: money(k.receivable),
            rows: [['Khách trả trước', money(k.advances)], ['Còn phải thu ròng', money(k.net)]] })}
        ${statCard({ label: 'Quá hạn', icon: '⏰', value: money(k.overdue), tone: 'danger',
            rows: [['Tỷ lệ', fmtPct(k.overdue_pct)], ['Số khách quá hạn', fmtNum(k.overdue_customers)],
                ['Chưa rõ hạn', money(k.unknown)]] })}
        ${statCard({ label: `DSO ${fmtNum(dso.window_days)} ngày`, icon: '📆', tone: 'warning',
            value: dso.dso === null || dso.dso === undefined ? '—' : `${String(dso.dso).replace('.', ',')} ngày`,
            rows: [['Nợ trên sổ cái', money(dso.debt)], ['Doanh thu gồm VAT', money(dso.revenue)]] })}
        ${statCard({ label: 'Cần lưu ý', icon: '⚠️',
            value: `${fmtNum(k.over_limit)} <span class="bc-text-sm">khách vượt hạn mức</span>`,
            rows: [['Tiền trả chưa gắn HĐ', money(k.unallocated)]] })}
    </div>`;
}

function agingTable(d) {
    const B = d.meta.buckets;
    const cols = [
        { key: 'label', label: 'Kênh', align: 'left', sortable: false },
        { key: 'receivable', label: 'Phải thu', render: (r) => money(r.receivable), sortable: false },
        ...B.map((b) => ({ key: b.key, label: b.label, sortable: false,
            render: (r) => (r.buckets[b.key] ? money(r.buckets[b.key]) : '<span class="bc-muted">–</span>') })),
        { key: 'cus', label: 'Khách nợ / quá hạn', sortable: false,
            render: (r) => `${fmtNum(r.customers)} / <b class="${r.overdue_customers ? 'bc-txt-danger' : ''}">${fmtNum(r.overdue_customers)}</b>` },
    ];
    const tot = { label: '<b>Tổng</b>', receivable: `<b>${money(d.kpis.receivable)}</b>`,
        cus: `${fmtNum(d.channels.reduce((a, c) => a + c.customers, 0))} / ${fmtNum(d.kpis.overdue_customers)}` };
    B.forEach((b) => {
        const v = d.channels.reduce((a, c) => a + (c.buckets[b.key] || 0), 0);
        tot[b.key] = v ? `<b>${money(v)}</b>` : '<span class="bc-muted">–</span>';
    });
    return dataTable({ columns: cols, rows: d.channels, totalRow: tot, emptyMessage: 'Không có công nợ phải thu' });
}

async function agingChart(d, isCurrent) {
    const rows = d.channels.filter((c) => c.receivable > 0);
    if (!rows.length) { fill('cn-chart-wrap', emptyState({ title: 'Không có công nợ phải thu' })); return; }
    const Chart = await loadChartLib();
    const el = document.getElementById('cn-chart');
    if (!isCurrent() || !el) return;  // lượt vẽ cũ (Làm mới / chuyển trang lúc đang tải Chart.js) không chiếm canvas mới
    charts.add(new Chart(el, {
        type: 'bar',
        data: {
            labels: rows.map((c) => c.label),
            datasets: d.meta.buckets.map((b) => ({ label: b.label, data: rows.map((c) => c.buckets[b.key] || 0),
                backgroundColor: BUCKET_COLORS[b.key], borderWidth: 0, barThickness: 22 })),
        },
        options: {
            indexAxis: 'y', maintainAspectRatio: false,
            scales: { x: { stacked: true, ticks: { callback: (v) => fmtMoney(v) } }, y: { stacked: true } },
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
                tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.raw)}` } } },
        },
    }));
}

function topHtml(d) {
    return dataTable({
        rows: d.top_overdue, sortKey: 'overdue', emptyMessage: 'Không có khách quá hạn',
        columns: [
            { key: 'customer', label: 'Khách hàng', align: 'left' },
            { key: 'channel', label: 'Kênh' },
            { key: 'receivable', label: 'Phải thu', render: (r) => money(r.receivable) },
            { key: 'overdue', label: 'Quá hạn', render: (r) => `<b class="bc-txt-danger">${money(r.overdue)}</b>` },
            { key: 'max_days', label: 'Quá hạn xa nhất', render: (r) => `${fmtNum(r.max_days)} ngày` },
            { key: 'unknown', label: 'Chưa rõ hạn', render: (r) => (r.unknown ? money(r.unknown) : '–') },
        ],
    });
}

function mtHtml(d) {
    const m = d.mt, meta = d.meta.mt || {};
    if (!m) {
        const why = meta.error ? 'Không đọc được bảng kê chuỗi (lỗi đã ghi Error Log).'
            : 'Hệ thống Kế toán chưa có bảng kê thanh toán của chuỗi.';
        return `<div class="bc-alert">${escapeHtml(why)} Công nợ MT đang tính theo sổ cái như các kênh khác.</div>`;
    }
    const cols = [
        { key: 'chain', label: 'Chuỗi', align: 'left' },
        { key: 'amount', label: 'Còn nợ', render: (r) => money(r.amount) },
        { key: 'overdue', label: 'Quá hạn', render: (r) => (r.overdue ? `<b class="bc-txt-danger">${money(r.overdue)}</b>` : '–') },
        { key: 'count', label: 'Số hoá đơn' },
        { key: 'unknown_term', label: 'HĐ chưa khai hạn', render: (r) => (r.unknown_term ? fmtNum(r.unknown_term) : '–') },
    ];
    if (m.einv_known) cols.push({ key: 'einv_pending', label: 'Nợ trên HĐ chưa có số HĐĐT', render: (r) => (r.einv_pending ? money(r.einv_pending) : '–') });
    const notes = [escapeHtml(meta.basis || '')];
    if (meta.gl_total !== null && meta.gl_total !== undefined) {
        const diff = meta.gl_total - m.total;
        notes.push(`Số dư sổ cái của khách MT: ${money(meta.gl_total)}${Math.abs(diff) >= 1000 ? ` (chênh ${money(diff)} — xem màn Đối chiếu MT của Kế toán)` : ''}.`);
    }
    const warn = [];
    if (m.orphan_return_count) warn.push(`${fmtNum(m.orphan_return_count)} hoá đơn trả hàng MT (${fmtMoney(m.orphan_return_amount)}) chưa gắn hoá đơn gốc — số còn nợ đang cao hơn thực tế chừng đó.`);
    if (m.pending_review) warn.push(`${fmtMoney(m.pending_review)} tiền chuỗi đã trả nhưng dòng bảng kê còn chờ Kế toán xác nhận — chưa trừ vào nợ.`);
    return `${warn.length ? `<div class="bc-alert">${warn.map(escapeHtml).join('<br>')}</div>` : ''}
        ${dataTable({ rows: m.chains, columns: cols, sortKey: 'overdue', emptyMessage: 'Không còn hoá đơn MT chưa thu' })}
        <div class="bc-note">${notes.join(' ')}</div>`;
}

export async function render({ container, isCurrent }) {
    charts.destroy();
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Phải thu khách hàng</div>
                <div class="bc-view-banner-sub" id="cn-sub">Theo sổ cái như Kế toán · tiền gồm VAT</div></div>
            <span class="bc-view-banner-badge" id="cn-badge">💳 Công nợ</span>
        </div>
        <div id="cn-kpis">${skeletonGrid(4, 128)}</div>
        <div class="bc-section-title">Tuổi nợ theo kênh</div>
        <div class="bc-card"><div class="bc-chart-wrap" id="cn-chart-wrap"><canvas id="cn-chart"></canvas></div>
            <div id="cn-aging" class="bc-mt-3">${skeleton(160)}</div></div>
        <div class="bc-section-title">Khách quá hạn nhiều nhất</div>
        <div class="bc-card"><div id="cn-top">${skeleton(200)}</div></div>
        <div class="bc-section-title">Siêu thị (MT) theo chuỗi</div>
        <div class="bc-card"><div id="cn-mt">${skeleton(160)}</div></div>
        <div class="bc-note bc-mt-3" id="cn-basis"></div>`;
    try {
        const d = await api.cn.receivables();
        if (!isCurrent()) return;
        fill('cn-sub', `Đến ${escapeHtml(fmtDate(d.meta.as_of))} · tiền gồm VAT · ${escapeHtml(d.meta.company)}`);
        fill('cn-kpis', kpisHtml(d));
        fill('cn-aging', agingTable(d));
        fill('cn-top', topHtml(d));
        fill('cn-mt', mtHtml(d));
        fill('cn-basis', `ⓘ Ngoài MT: số dư sổ cái từng khách (như danh sách công nợ của Kế toán). Quá hạn phân bổ theo
            hoá đơn mới nhất trước; hạn = hạn trên hoá đơn, trống thì ngày hoá đơn + ${fmtNum(d.meta.due_days)} ngày. Phần nợ không
            gắn được hoá đơn (vd nợ đầu kỳ ghi bằng bút toán) để ở cột "Chưa rõ hạn". Kênh theo nhóm khách hiện tại.
            DSO tính như Kế toán: nợ sổ cái toàn công ty / doanh thu gồm VAT.`);
        // Biểu đồ lỗi (CDN Chart.js chặn / mạng yếu) chỉ thay khung biểu đồ, không xoá số đã hiện.
        try { await agingChart(d, isCurrent); } catch (e) {
            if (isCurrent()) fill('cn-chart-wrap', emptyState({ title: 'Không tải được biểu đồ', message: e?.message || '' }));
        }
    } catch (err) {
        if (!isCurrent()) return;
        fill('cn-kpis', errorState(err));
        ['cn-aging', 'cn-top', 'cn-mt'].forEach((id) => fill(id, ''));
    }
}
