// #/san-xuat — Báo cáo sản xuất: số hộp QC ghi theo ngày ở phần Ghi hộp của app Sản xuất (gồm cả hộp công nhật; bảng đã huỷ
// không tính). Một lượt gọi bc.api.sx_hop.get_overview(thang) cho thẻ tổng, biểu đồ ngày, bảng theo ngày, bảng theo mã, 12 tháng;
// bấm một ngày → bc.api.sx_hop.get_day(date) mở chi tiết theo mã ngay dưới dòng đó. Khác Nhập TP (số thủ kho đã nhận vào kho)
// và SX Hàng Tết (phiếu sản xuất nhập kho).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum, fmtPct, growthClass, growthText, todayISO } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
const state = { thang: '', d: null, open: null };  // thang: CHỈ tháng người xem đã chọn và tải được — trống = tháng hiện tại
let seq = 0;      // lượt tải tháng mới nhất — đổi tháng nhanh thì lượt cũ về sau không đè lượt mới
let daySeq = 0;   // lượt mở chi tiết ngày mới nhất
const SECTIONS = ['sh-kpis', 'sh-days', 'sh-items', 'sh-trend'];
const Q = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });  // thùng (máy chủ làm tròn 2 số lẻ)
const D1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });  // TB hộp / ngày (1 số lẻ)
const THU = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];  // weekday của máy chủ: thứ Hai = 0
const SUNDAY = 6;
const GROUP = { tet: ['Tết', 'bc-badge-warning'], traditional: ['Truyền thống', 'bc-badge-primary'], khac: ['Khác', 'bc-badge-muted'] };
const NOTE = 'ⓘ Số lấy từ phần Ghi hộp của app Sản xuất: số hộp QC ghi theo ngày, gồm cả hộp công nhật; bảng đã huỷ không tính. '
    + 'Khác với màn Nhập TP (số đã nhập kho).';

const qn = (v) => (v === null || v === undefined ? '—' : Q.format(v));
const d1 = (v) => (v === null || v === undefined ? '—' : D1.format(v));
const dash = '<span class="bc-muted">—</span>';
function monthLabel(m) { return `T${Number(m.slice(5))}/${m.slice(2, 4)}`; }
function ym(m) { return `${m.slice(5)}/${m.slice(0, 4)}`; }
function shiftMonth(m, n) {
    let y = Number(m.slice(0, 4)), mo = Number(m.slice(5, 7)) + n;
    while (mo < 1) { mo += 12; y -= 1; }
    while (mo > 12) { mo -= 12; y += 1; }
    return `${y}-${String(mo).padStart(2, '0')}`;
}
/** Lúc máy chủ tính số (meta.generated_at của cache: "YYYY-MM-DD HH:MM:SS…") → "10:30 27/10/2026"; thiếu thì ngày as_of. */
function updatedAt(m) {
    const g = String(m.generated_at || '');
    return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(g) ? `${g.slice(11, 16)} ${fmtDate(g)}` : fmtDate(m.as_of);
}
function groupBadge(g) {
    const [label, cls] = GROUP[g] || GROUP.khac;
    return `<span class="bc-badge ${cls} sh-group">${escapeHtml(label)}</span>`;
}

// ─── Ô chọn tháng (‹ tháng ›) + cập nhật + làm mới ───────────────────────────
// Tháng hiện tại = tháng của meta.as_of (hôm nay của MÁY CHỦ) — không theo đồng hồ máy người xem; › tắt ở tháng hiện tại.
function switcherHtml(cur, asOf) {
    const now = (asOf || cur || todayISO()).slice(0, 7);  // chưa có số máy chủ (lỗi tải) → tháng theo máy người xem
    const months = [];
    for (let i = 0; i < 24; i++) months.push(shiftMonth(now, -i));
    if (cur && !months.includes(cur)) months.push(cur);
    const atNow = !cur || !now || cur >= now;
    return `<div class="sh-switch">
        <button type="button" class="bc-btn bc-btn-sm sh-nav" id="sh-prev" aria-label="Tháng trước" ${cur ? '' : 'disabled'}>‹</button>
        <select class="bc-input" id="sh-thang" aria-label="Tháng">${months.map((x) =>
            `<option value="${escapeHtml(x)}" ${x === cur ? 'selected' : ''}>Tháng ${escapeHtml(ym(x))}</option>`).join('')}</select>
        <button type="button" class="bc-btn bc-btn-sm sh-nav" id="sh-next" aria-label="Tháng sau" ${atNow ? 'disabled' : ''}>›</button>
        <button type="button" class="bc-btn bc-btn-sm sh-nav" id="sh-refresh" aria-label="Làm mới số liệu" title="Làm mới"><i class="fas fa-rotate"></i></button>
    </div>`;
}

function bindSwitcher(cur, asOf, info, isCurrent) {
    const refocus = document.activeElement?.id;
    fill('sh-filter', `${switcherHtml(cur, asOf)}<div class="sh-info" id="sh-info">${info}</div>`);
    const go = (m, refresh = false) => {
        SECTIONS.forEach((id) => fill(id, skeleton(120)));
        load(isCurrent, m, true, refresh);
    };
    document.getElementById('sh-thang')?.addEventListener('change', (e) => go(e.target.value));
    document.getElementById('sh-prev')?.addEventListener('click', () => cur && go(shiftMonth(cur, -1)));
    document.getElementById('sh-next')?.addEventListener('click', () => cur && go(shiftMonth(cur, 1)));
    document.getElementById('sh-refresh')?.addEventListener('click', () => go(cur || state.thang, true));
    if (refocus && ['sh-thang', 'sh-prev', 'sh-next', 'sh-refresh'].includes(refocus)) document.getElementById(refocus)?.focus();
}

// ─── Thẻ tổng ────────────────────────────────────────────────────────────────
function kpisHtml(d) {
    const k = d.kpis, m = d.meta;
    const prevLabel = monthLabel(m.prev);
    const c1 = statCard({ label: 'Tổng hộp tháng', icon: '📦', value: `${fmtNum(k.hop)} hộp`,
        rows: [[`Cùng kỳ ${prevLabel}`, fmtNum(k.prev_hop)],
            ['So cùng kỳ', `<span class="${growthClass(k.growth_pct)}" id="sh-growth">${growthText(k.growth_pct)}</span>`],
            [`Cả ${prevLabel}`, fmtNum(k.prev_full)]] });
    const c2 = statCard({ label: 'Quy thùng', icon: '🧳', value: `${qn(k.thung)} thùng`, rows: [['Hộp', fmtNum(k.hop)]] });
    const c3 = statCard({ label: 'TB hộp / ngày SX', icon: '📈', value: d1(k.tb_ngay), rows: [['Số ngày có ghi', fmtNum(k.so_ngay)]] });
    const c4 = k.ngay_cuoi ? statCard({ label: 'Ngày ghi gần nhất', icon: '🗓️', value: escapeHtml(fmtDate(k.ngay_cuoi.date)),
        rows: [['Hộp', fmtNum(k.ngay_cuoi.hop)]] })
        : statCard({ label: 'Ngày ghi gần nhất', icon: '🗓️', value: '—', rows: [['', 'Chưa ghi ngày nào']] });
    const c5 = statCard({ label: 'Công nhật', icon: '⏱️', value: `${fmtNum(k.cong_nhat)} hộp`,
        rows: [['Tỷ lệ', fmtPct(k.cong_nhat_pct)], ['Khoán', fmtNum(k.khoan)]] });
    const c6 = statCard({ label: 'Số mã', icon: '🏷️', value: fmtNum(k.so_ma), rows: [['Có ghi hộp', 'trong tháng']] });
    const warn = k.chua_chot > 0 ? `<div class="sh-warn"><span class="bc-badge bc-badge-warning" id="sh-chuachot"
        title="Ngày có ghi hộp nhưng chưa có viền xanh trên lịch Ghi hộp: số của ngày chưa đồng bộ xong sang bảng lương (đang chờ hoặc lỗi) — số còn có thể đổi">⚠ ${fmtNum(k.chua_chot)} ngày chưa chốt</span></div>` : '';
    return `${warn}<div class="bc-grid sh-kpi-grid" id="sh-kpi-grid">${c1}${c2}${c3}${c4}${c5}${c6}</div>`;
}

// ─── Theo ngày: biểu đồ cột chồng + bảng (thẻ trên điện thoại), bấm ngày → chi tiết theo mã ─
function dayRowHtml(r) {
    const v = (x, f = fmtNum) => (r.co ? f(x) : dash);
    const sun = r.weekday === SUNDAY;
    const chot = r.co ? (r.chot ? '<span class="bc-badge bc-badge-success">Đã chốt</span>' : '<span class="bc-badge bc-badge-warning">Chưa chốt</span>') : dash;
    return `<tr class="sh-day ${r.co ? 'bc-clickable' : 'sh-day-empty'} ${sun ? 'sh-sun' : ''}" data-date="${escapeHtml(r.date)}"
            ${r.co ? 'tabindex="0" role="button" aria-expanded="false"' : ''}>
        <td class="bc-left sh-day-date"><b>${escapeHtml(fmtDate(r.date, true))}</b> <span class="sh-thu">${THU[r.weekday] || ''}</span>${r.co ? '<i class="fas fa-chevron-down sh-caret"></i>' : ''}</td>
        <td data-label="Hộp" class="sh-c-hop">${r.co ? `<b>${fmtNum(r.hop)}</b>` : dash}</td>
        <td data-label="Thùng">${v(r.thung, qn)}</td>
        <td data-label="Khoán">${v(r.khoan)}</td>
        <td data-label="Công nhật">${v(r.cong_nhat)}</td>
        <td data-label="Số mã">${v(r.so_ma)}</td>
        <td data-label="Chốt">${chot}</td>
    </tr>`;
}

function daysHtml(d) {
    const rows = d.days;  // máy chủ trả ngày mới nhất trước
    const k = d.kpis;
    return `<div class="bc-chart-wrap" id="sh-day-wrap" style="height:220px"><canvas id="sh-day-chart"></canvas></div>
        <div class="bc-note sh-legend">Cột tím = khoán (gồm khoán chung), cột cam = công nhật; ngày <b class="sh-sun-txt">đỏ</b> là Chủ nhật.</div>
        <div class="sh-table-box"><table class="bc-table sh-day-table" id="sh-day-table">
            <thead><tr><th class="bc-left">Ngày</th><th>Hộp</th><th>Thùng</th><th>Khoán</th><th>Công nhật</th><th>Số mã</th><th>Chốt</th></tr></thead>
            <tbody>${rows.map(dayRowHtml).join('')}
                <tr class="bc-row-total sh-day-total"><td class="bc-left">Cả tháng</td><td data-label="Hộp">${fmtNum(k.hop)}</td>
                    <td data-label="Thùng">${qn(k.thung)}</td><td data-label="Khoán">${fmtNum(k.khoan)}</td>
                    <td data-label="Công nhật">${fmtNum(k.cong_nhat)}</td><td data-label="Số mã">${fmtNum(k.so_ma)}</td><td data-label="Chốt"></td></tr>
            </tbody></table></div>
        <div class="bc-note">Bấm một ngày để xem số hộp theo mã. "—" = ngày không có bảng ghi hộp. "Đã chốt" = ngày có viền xanh trên
            lịch Ghi hộp (số của ngày đã đồng bộ xong sang bảng lương); "Chưa chốt" = còn chờ đồng bộ hoặc đồng bộ lỗi, số còn có thể đổi.</div>`;
}

function detailHtml(day, x) {
    // error = máy chủ tính hỏng (Error Log) — khác với "không có số": không được nói là ngày này không ghi hộp.
    if (x?.error) return errorState(null, 'Không tải được chi tiết ngày — quản trị xem Error Log');
    if (!x || !x.available) return '<div class="bc-muted bc-text-sm">Không có số ghi hộp của ngày này.</div>';
    const t = x.total;
    const list = x.rows.map((r) => `<div class="sh-dt-row">
        <div class="sh-dt-name">${escapeHtml(r.short_name || r.item_name || r.item_code)} ${groupBadge(r.group)}
            <div class="bc-muted bc-text-sm">${escapeHtml(r.item_code)} · khoán ${fmtNum(r.khoan)}${r.khoan_chung ? ` (chung ${fmtNum(r.khoan_chung)})` : ''}
                · công nhật ${fmtNum(r.cong_nhat)}</div></div>
        <div class="sh-dt-num"><b>${fmtNum(r.hop)}</b> hộp<div class="bc-muted bc-text-sm">${r.thung ? `${qn(r.thung)} thùng · ` : ''}${fmtPct(r.pct)}</div></div>
    </div>`).join('');
    return `<div class="sh-detail" data-detail="${escapeHtml(day)}">
        <div class="sh-dt-head"><b>${escapeHtml(fmtDate(x.meta.date))}</b> <span class="sh-dt-total">${fmtNum(t.hop)} hộp · ${qn(t.thung)} thùng · khoán ${fmtNum(t.khoan)} · công nhật ${fmtNum(t.cong_nhat)}</span>
            ${x.meta.chot ? '<span class="bc-badge bc-badge-success">Đã chốt</span>' : '<span class="bc-badge bc-badge-warning">Chưa chốt</span>'}</div>
        ${list || '<div class="bc-muted bc-text-sm">Không có mã nào.</div>'}
    </div>`;
}

function closeDetail() {
    document.querySelectorAll('#sh-day-table tr.sh-detail-row').forEach((x) => x.remove());
    document.querySelectorAll('#sh-day-table tr.sh-day[aria-expanded="true"]').forEach((x) => { x.setAttribute('aria-expanded', 'false'); x.classList.remove('sh-open'); });
}

async function toggleDay(tr) {
    const date = tr.dataset.date;
    const wasOpen = state.open === date;
    closeDetail();
    state.open = null;
    if (wasOpen) return;
    state.open = date;
    tr.setAttribute('aria-expanded', 'true');
    tr.classList.add('sh-open');
    const row = document.createElement('tr');
    row.className = 'sh-detail-row';
    row.innerHTML = `<td colspan="7" class="bc-left">${skeleton(80)}</td>`;
    tr.after(row);
    const my = ++daySeq;
    try {
        // since = lúc máy chủ tính bảng đang hiện: bản cache của ngày cũ hơn thì máy chủ tính lại → chi tiết khớp dòng ngày
        // (kể cả sau ↻ hay Làm mới chung, khi dòng ngày đã là số mới mà chi tiết còn trong cache).
        const x = await api.sxHop.day(date, false, state.d?.meta?.generated_at);
        if (my !== daySeq || !row.isConnected) return;
        row.firstElementChild.innerHTML = detailHtml(date, x);
    } catch (err) {
        if (my !== daySeq || !row.isConnected) return;
        row.firstElementChild.innerHTML = errorState(err, 'Không tải được chi tiết ngày');
    }
}

function bindDays() {
    const tb = document.getElementById('sh-day-table');
    if (!tb) return;
    const hit = (e) => {
        const tr = e.target.closest('tr.sh-day.bc-clickable');
        return tr && tb.contains(tr) ? tr : null;
    };
    tb.addEventListener('click', (e) => { const tr = hit(e); if (tr) toggleDay(tr); });
    tb.addEventListener('keydown', (e) => {
        const tr = hit(e);
        if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleDay(tr); }
    });
}

// ─── Theo mã ─────────────────────────────────────────────────────────────────
function itemsHtml(d) {
    const g = d.groups || [];
    return `${g.length ? `<div id="sh-groups">${kpiGrid(g.map((x) => ({ label: x.label, value: fmtNum(x.hop), sub: fmtPct(x.pct) })), 3)}</div>` : ''}
        <div class="bc-mt-3" id="sh-item-table">${dataTable({ rows: d.items, sortKey: 'hop', pageSize: 10, scrollButtons: false,
            emptyMessage: 'Chưa có mã nào được ghi hộp',
            columns: [
                { key: 'short_name', label: 'Mã / tên', align: 'left', sortValue: (r) => r.short_name || r.item_code,
                    render: (r) => `<span class="sh-item-name">${escapeHtml(r.short_name || r.item_name || r.item_code)}</span> ${groupBadge(r.group)}
                        <div class="bc-muted bc-text-sm">${escapeHtml(r.item_code)}</div>` },
                { key: 'hop', label: 'Hộp', render: (r) => `<b>${fmtNum(r.hop)}</b>` },
                { key: 'thung', label: 'Thùng', render: (r) => (r.thung ? qn(r.thung) : dash) },
                { key: 'pct', label: '% tổng', render: (r) => fmtPct(r.pct) },
                { key: 'so_ngay', label: 'Số ngày', render: (r) => fmtNum(r.so_ngay) },
                { key: 'tb_ngay', label: 'TB / ngày', render: (r) => d1(r.tb_ngay) },
            ] })}</div>
        <div class="bc-note">Thùng theo quy cách "Thùng" khai trên mã hàng; mã chưa khai quy cách ("—") không quy ra thùng nên tổng thùng
            không gồm phần đó. Mã đang ẩn (Quản trị › Ẩn sản phẩm) không có trong bảng, tổng vẫn gồm.</div>`;
}

// ─── Biểu đồ ─────────────────────────────────────────────────────────────────
async function drawCharts(d, alive, empty) {
    const hasTrend = d.trend.some((r) => r.hop);
    if (!hasTrend) fill('sh-trend-wrap', emptyState({ icon: '📭', title: 'Chưa có số ghi hộp trong 12 tháng' }));
    if (empty && !hasTrend) return;
    const Chart = await loadChartLib();
    if (!alive()) return;
    if (!empty) {
        const el = document.getElementById('sh-day-chart');
        const days = d.days.slice().reverse();  // biểu đồ: ngày cũ bên trái (máy chủ trả mới nhất trước)
        // Tham chiếu: TB hộp / ngày SX của tháng trước (có sẵn trong trend) — chỉ vẽ khi tháng trước có ngày ghi.
        const prev = d.trend.find((r) => r.thang === d.meta.prev);
        const ref = prev && prev.so_ngay ? prev.tb_ngay : null;
        const datasets = [
            { label: 'Khoán', data: days.map((r) => (r.co ? r.khoan : 0)), backgroundColor: '#7c3aed', stack: 'hop', borderWidth: 0, maxBarThickness: 22 },
            { label: 'Công nhật', data: days.map((r) => (r.co ? r.cong_nhat : 0)), backgroundColor: '#f59e0b', stack: 'hop', borderWidth: 0, maxBarThickness: 22 },
        ];
        if (ref) datasets.push({ type: 'line', label: `TB / ngày SX ${monthLabel(d.meta.prev)}`, data: days.map(() => ref), stack: 'ref',
            borderColor: '#94a3b8', borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, fill: false });
        if (el) charts.add(new Chart(el, {
            type: 'bar',
            data: { labels: days.map((r) => fmtDate(r.date, true).slice(0, 2)), datasets },
            options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
                plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 12 } },
                    tooltip: { callbacks: {
                        title: (items) => { const r = days[items[0].dataIndex]; return `${THU[r.weekday]} ${fmtDate(r.date)}`; },
                        label: (c) => `${c.dataset.label}: ${D1.format(c.raw)} hộp`,
                        footer: (items) => { const r = days[items[0].dataIndex]; return r.co ? `Tổng ${fmtNum(r.hop)} hộp` : 'Không ghi hộp'; } } } },
                scales: { x: { stacked: true, ticks: { autoSkip: false, maxRotation: 0, font: { size: 10 },
                    color: (c) => (days[c.index]?.weekday === SUNDAY ? '#dc2626' : '#4b5563') } },
                y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } } },
        }));
    }
    if (hasTrend) {
        const el = document.getElementById('sh-trend-chart');
        if (el) charts.add(new Chart(el, {
            type: 'bar',
            data: { labels: d.trend.map((r) => monthLabel(r.thang)),
                datasets: [{ label: 'Hộp', data: d.trend.map((r) => r.hop), borderWidth: 0, borderRadius: 4, maxBarThickness: 28,
                    backgroundColor: d.trend.map((r) => (r.thang === d.meta.thang ? '#7c3aed' : '#c4b5fd')) }] },
            options: { maintainAspectRatio: false, plugins: { legend: { display: false },
                tooltip: { callbacks: { label: (c) => { const r = d.trend[c.dataIndex];
                    return `${fmtNum(r.hop)} hộp · ${fmtNum(r.so_ngay)} ngày · TB ${D1.format(r.tb_ngay)} / ngày`; } } } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { ticks: { autoSkip: true, maxRotation: 0 } } } },
        }));
    }
}

function trendHtml(d) {
    return `<div class="bc-chart-wrap" id="sh-trend-wrap" style="height:200px"><canvas id="sh-trend-chart"></canvas></div>
        <div class="bc-note">Cột đậm = tháng đang xem. Mỗi tháng tính trọn tháng (tháng này tính đến hôm nay).</div>`;
}

// ─── Tải ─────────────────────────────────────────────────────────────────────
async function load(isCurrent, thang = state.thang, chon = false, refresh = false) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    charts.destroy();
    state.open = null;
    try {
        const d = await api.sxHop.overview(thang || undefined, refresh);
        if (!alive()) return;
        if (!d || !d.available || (d.meta && d.meta.sx === false)) {
            if (d?.meta?.thang) bindSwitcher(d.meta.thang, d.meta.as_of, '', isCurrent);
            else bindSwitcher(state.thang, '', '', isCurrent);
            // Chỉ nói "chưa cài" khi máy chủ báo đúng thế (meta.sx === false). error = sx có mà tính hỏng (cột đổi sau khi sx
            // nâng cấp…): máy chủ đã ghi Error Log — báo lỗi tải, không bảo lãnh đạo là nhà máy chưa có hệ thống.
            fill('sh-kpis', d?.meta?.sx === false
                ? emptyState({ icon: '🏭', title: 'Chưa có số liệu ghi hộp',
                    message: 'Hệ thống sản xuất (app sx) chưa cài trên hệ thống này nên chưa có số hộp ghi theo ngày.' })
                : errorState(null, 'Không tải được số ghi hộp — quản trị xem Error Log'));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        if (chon) state.thang = d.meta.thang;
        state.d = d;
        const m = d.meta;
        bindSwitcher(m.thang, m.as_of, `<span id="sh-range">Từ ${escapeHtml(fmtDate(m.from))} đến ${escapeHtml(fmtDate(m.to))}</span>
            · <span id="sh-updated">Cập nhật ${escapeHtml(updatedAt(m))}</span>`, isCurrent);
        fill('sh-kpis', kpisHtml(d));
        const empty = !d.days.some((r) => r.co);
        if (empty) {
            const e = emptyState({ icon: '📭', title: 'Chưa có số ghi hộp trong tháng này', message: `Tháng ${ym(m.thang)}` });
            fill('sh-days', e);
            fill('sh-items', emptyState({ icon: '📭', title: 'Chưa có số ghi hộp trong tháng này' }));
        } else {
            fill('sh-days', daysHtml(d));
            bindDays();
            fill('sh-items', itemsHtml(d));
        }
        fill('sh-trend', trendHtml(d));
        // Biểu đồ lỗi (CDN chặn / mạng yếu) chỉ thay khung biểu đồ, không xoá số đã hiện.
        try { await drawCharts(d, alive, empty); } catch (e) {
            if (alive()) {
                if (!empty) fill('sh-day-wrap', emptyState({ title: 'Không tải được biểu đồ', message: e?.message || '' }));
                fill('sh-trend-wrap', '');
            }
        }
    } catch (err) {
        if (!alive()) return;
        bindSwitcher(state.thang, '', '', isCurrent);  // vẫn chọn lại được tháng — không kẹt ở màn lỗi
        fill('sh-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner sh-banner">
            <div class="sh-banner-head"><div class="bc-view-banner-title">Báo cáo sản xuất</div>
                <div class="bc-view-banner-sub">Số hộp đóng được mỗi ngày theo phần Ghi hộp của Sản xuất</div></div>
            <span class="bc-view-banner-badge">🏭 Sản xuất</span>
            <div class="sh-filter" id="sh-filter"></div>
        </div>
        <div id="sh-kpis">${skeletonGrid(6, 120)}</div>
        <div class="bc-section-title">Theo ngày</div>
        <div class="bc-card"><div id="sh-days">${skeleton(260)}</div></div>
        <div class="bc-section-title">Theo mã</div>
        <div class="bc-card"><div id="sh-items">${skeleton(220)}</div></div>
        <div class="bc-section-title">12 tháng</div>
        <div class="bc-card"><div id="sh-trend">${skeleton(200)}</div></div>
        <div class="bc-note bc-mt-3" id="sh-note">${escapeHtml(NOTE)}</div>`;
    await load(isCurrent);
}
