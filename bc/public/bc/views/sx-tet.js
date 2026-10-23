// #/sx-tet — Sản xuất Hàng Tết: bộ lọc ngày (mặc định từ BC Settings / mùa Tết),
// lịch SX tháng (thùng + giá trị, mùng 1–3 Tết tô đỏ) → bottom-sheet chi tiết ngày,
// thống kê nhanh Hàng Tết / Truyền thống, 3 tab thẻ sản phẩm có ảnh + tiến độ.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { debounce, escapeHtml, fmtDate, fmtMoney, fmtNum, fmtPct, todayISO } from '../lib/format.js';
import { renderCalendar } from '../components/calendar.js';
import { dataTable } from '../components/data-table.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { showModal } from '../components/modal.js';
import { tabs, bindTabs } from '../components/tabs.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const NO_IMG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72"><rect width="72" height="72" rx="10" fill="#f4f2fb"/><text x="36" y="44" font-size="28" text-anchor="middle">📦</text></svg>');
const state = { from: null, to: null, rows: [], tab: 'tet', sort: 'stock', q: '', year: null, month: null, days: [] };

const sum = (rows, k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
const pctOf = (a, b) => (b ? Math.round(a / b * 1000) / 10 : null);
const clampW = (v) => Math.max(0, Math.min(100, v || 0));

function groupStats(rows, title, icon) {
    const plan = sum(rows, 'plan'), prod = sum(rows, 'produced'), out = sum(rows, 'outgoing');
    const th = (k) => `${fmtNum(sum(rows, k))} thùng`;
    return `<div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">${icon} ${escapeHtml(title)}</div>
        <span class="bc-badge bc-badge-primary">${rows.length} mã</span></div>
        ${kpiGrid([
            { label: 'Kế hoạch', value: th('plan_cartons'), sub: `${fmtNum(plan)} hộp` },
            { label: 'Sản xuất', value: th('produced_cartons'), sub: `${fmtNum(prod)} hộp<br><b class="bc-prod-note">Đạt ${fmtPct(pctOf(prod, plan))} KH</b>` },
            { label: 'Xuất bán', value: th('outgoing_cartons'), sub: `${fmtNum(out)} hộp<br><b class="bc-prod-note">${fmtPct(pctOf(out, plan || prod))} ${plan ? 'KH' : 'SX'}</b>` },
            { label: 'Tồn kho', value: `${fmtNum(sum(rows, 'stock_cartons'))} thùng`, sub: `${fmtNum(sum(rows, 'stock'))} hộp` },
        ], 2)}</div>`;
}

/** Dòng "Nhãn  1.200 hộp · 50 thùng  [ghi chú]" — chưa khai hệ số Thùng thì hiện "—". */
function qtyLine(label, boxes, cartons, r) {
    return `<div class="bc-prod-line"><span>${label}</span>
        <span><b>${fmtNum(boxes)}</b> hộp · <b>${r.carton_factor ? fmtNum(cartons) : '—'}</b> thùng</span></div>`;
}

function progLine(pct, cls, label) {
    return `<div class="bc-prod-bar"><div class="bc-progress ${cls}"><span style="width:${clampW(pct)}%"></span></div><b class="bc-prod-note">${label}</b></div>`;
}

function imgSrc(r) {
    return r.image || `/files/${encodeURIComponent(r.item_code)}.jpg`;
}

function card(r) {
    return `<div class="bc-prod">
        <img class="bc-prod-img" loading="lazy" alt="" src="${escapeHtml(imgSrc(r))}" data-fallback="${escapeHtml(r.image ? `/files/${encodeURIComponent(r.item_code)}.jpg` : '')}">
        <div style="min-width:0">
            <div class="bc-prod-name" title="${escapeHtml(r.item_name)}">${escapeHtml(r.item_name)}</div>
            <div class="bc-prod-code">${escapeHtml(r.item_code)}</div>
            ${qtyLine('Kế hoạch', r.plan, r.plan_cartons, r)}
            ${qtyLine('Tồn kho', r.stock, r.stock_cartons, r)}
            ${qtyLine('Sản xuất', r.produced, r.produced_cartons, r)}
            ${progLine(r.produced_pct, 'bc-ok', r.plan ? `Đạt ${fmtPct(r.produced_pct, 0)} KH` : 'Chưa có KH')}
            ${qtyLine('Bán', r.outgoing, r.outgoing_cartons, r)}
            ${progLine(r.outgoing_pct, '', r.outgoing_pct === null || r.outgoing_pct === undefined ? '—' : `${fmtPct(r.outgoing_pct, 0)} ${r.plan ? 'KH' : 'SX'}`)}
        </div></div>`;
}

function paintProducts() {
    const q = state.q.trim().toLowerCase();
    let rows = state.rows.filter((r) => r.group_key === state.tab);
    if (q) rows = rows.filter((r) => `${r.item_code} ${r.item_name}`.toLowerCase().includes(q));
    const sorters = {
        stock: (a, b) => b.stock - a.stock || b.produced - a.produced,
        plan: (a, b) => b.plan - a.plan || b.produced - a.produced,
        produced: (a, b) => b.produced - a.produced,
        name: (a, b) => String(a.item_name).localeCompare(String(b.item_name), 'vi'),
    };
    rows.sort(sorters[state.sort]);
    fill('sx-prods', rows.length ? `<div class="bc-prod-grid">${rows.map(card).join('')}</div>`
        : emptyState({ title: q ? 'Không có mã khớp tìm kiếm' : 'Không có mã trong nhóm này' }));
}

function paintStats() {
    const g = window.BC_CONTEXT?.groups || {};
    const tet = state.rows.filter((r) => r.group_key === 'tet');
    const tt = state.rows.filter((r) => r.group_key === 'traditional');
    fill('sx-stats', `<div class="bc-grid bc-grid-2" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">
        ${groupStats(tet, g.tet || 'Hàng Tết', '🧧')}${groupStats(tt, g.traditional || 'Hàng truyền thống', '🥮')}</div>`);
    const counts = { tet: tet.length, traditional: tt.length, other: state.rows.length - tet.length - tt.length };
    fill('sx-tabs', tabs([
        { key: 'tet', label: g.tet || 'Hàng Tết', count: counts.tet },
        { key: 'traditional', label: g.traditional || 'Truyền thống', count: counts.traditional },
        { key: 'other', label: 'Khác', count: counts.other },
    ], state.tab, 'sx'));
    bindTabs(document.getElementById('sx-tabs'), 'sx', (k) => { state.tab = k; paintProducts(); });
}

function paintMonthAvg() {
    const d = state.days.filter((x) => x.cartons > 0 || x.amount > 0);
    fill('sx-avg', kpiGrid([
        { label: `TB / ngày SX (thùng) · T${state.month}`, value: fmtNum(d.length ? sum(d, 'cartons') / d.length : 0), sub: `${d.length} ngày sản xuất` },
        { label: `TB / ngày SX (giá trị) · T${state.month}`, value: fmtMoney(d.length ? sum(d, 'amount') / d.length : 0), sub: `Tổng ${fmtMoney(sum(d, 'amount'))}` },
    ], 2));
}

async function openDay(iso) {
    const body = showModal({ title: `Sản xuất ngày ${fmtDate(iso)}`, body: skeleton(44, 4, 6) });
    try {
        const res = await api.sx.dailyDetail(iso);
        if (!body?.isConnected) return;
        const rows = res.rows;
        body.innerHTML = dataTable({
            rows, sortKey: 'cartons', emptyMessage: 'Không có phiếu sản xuất',
            columns: [
                { key: 'item_code', label: 'Mã', align: 'left' },
                { key: 'item_name', label: 'Tên', align: 'left' },
                { key: 'boxes', label: 'Hộp', render: (r) => fmtNum(r.boxes) },
                { key: 'cartons', label: 'Thùng', render: (r) => fmtNum(r.cartons) },
                { key: 'amount', label: 'Giá trị', render: (r) => fmtNum(r.amount) },
                { key: 'voucher', label: 'Phiếu', align: 'left',
                    render: (r) => `<a href="/app/stock-entry/${encodeURIComponent(r.voucher)}" target="_blank" rel="noopener">${escapeHtml(r.voucher)}</a>` },
            ],
            totalRow: { item_code: 'Tổng', boxes: fmtNum(sum(rows, 'boxes')), cartons: fmtNum(sum(rows, 'cartons')), amount: fmtNum(sum(rows, 'amount')) },
        });
    } catch (err) {
        if (body?.isConnected) body.innerHTML = errorState(err);
    }
}

async function loadMonth(year, month) {
    state.year = year; state.month = month;
    const el = document.getElementById('sx-cal');
    if (!el) return;
    el.innerHTML = skeleton(360);
    try {
        const res = await api.sx.dailySummary(year, month);
        state.days = res.rows;
        const max = Math.max(0, ...res.rows.map((r) => r.cartons));
        const cells = {};
        res.rows.forEach((r) => {
            cells[r.date] = { v1: `${fmtNum(r.cartons)} th`, v2: fmtMoney(r.amount), hot: max > 0 && r.cartons >= 0.7 * max,
                title: `${fmtNum(r.cartons)} thùng · ${fmtNum(r.boxes)} hộp · ${fmtNum(r.amount)} ₫` };
        });
        renderCalendar(el, { year, month, cells, markTet: true, onNav: loadMonth, onSelect: openDay });
        paintMonthAvg();
    } catch (err) {
        el.innerHTML = errorState(err);
    }
}

function paintDiag(d) {
    if (!d || d.has_production) { fill('sx-diag', ''); return; }
    const other = Object.entries(d.entries_by_purpose || {}).filter(([k]) => k !== d.entry_type);
    const today = todayISO();
    const why = state.from > today
        ? `Mùa ${fmtDate(state.from)} → ${fmtDate(state.to)} chưa bắt đầu nên chưa có phiếu sản xuất.`
        : `Không có phiếu ${d.entry_type} nhập kho "${d.warehouse}" từ ${fmtDate(state.from)} đến ${fmtDate(state.to)}.`;
    fill('sx-diag', `<div class="bc-alert">
        <b>${escapeHtml(why)}</b>
        ${d.last_manufacture ? `<br>Phiếu sản xuất gần nhất: ${fmtDate(d.last_manufacture)}.` : `<br>Chưa tìm thấy phiếu ${escapeHtml(d.entry_type)} nào nhập kho "${escapeHtml(d.warehouse)}".`}
        ${other.length ? `<br>Trong khoảng này có phiếu kho loại khác: ${other.map(([k, n]) => `${escapeHtml(k)} (${n})`).join(', ')} — báo cáo chỉ tính phiếu ${escapeHtml(d.entry_type)} vào kho "${escapeHtml(d.warehouse)}".` : ''}
        <div class="bc-mt-2"><button type="button" class="bc-btn bc-btn-sm bc-btn-primary" id="sx-prev">Xem mùa trước (${fmtDate(d.prev_from)} → ${fmtDate(d.prev_to)})</button></div>
    </div>`);
    document.getElementById('sx-prev')?.addEventListener('click', async () => {
        state.from = d.prev_from; state.to = d.prev_to;
        await loadItems();
        await loadMonth(Number(d.prev_from.slice(0, 4)), Number(d.prev_from.slice(5, 7)));
    });
}

async function loadItems() {
    fill('sx-stats', skeletonGrid(2, 150, 'bc-grid-2'));
    fill('sx-prods', skeleton(96, 4, 8));
    try {
        const res = await api.sx.items(state.from, state.to);
        state.rows = res.rows;
        state.from = res.meta.from_date;
        state.to = res.meta.to_date;
        const f = document.getElementById('sx-from'), t = document.getElementById('sx-to');
        if (f) f.value = state.from;
        if (t) t.value = state.to;
        fill('sx-range', `${fmtDate(state.from)} → ${fmtDate(state.to)}${res.meta.plan_column ? '' : ' · chưa có cột kế hoạch trên Item'}`);
        paintDiag(res.meta.diag);
        paintStats();
        paintProducts();
    } catch (err) {
        fill('sx-stats', errorState(err));
        fill('sx-prods', '');
    }
}

export async function render({ container }) {
    state.rows = [];
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Sản xuất Hàng Tết</div>
                <div class="bc-view-banner-sub" id="sx-range">Mặc định: mùa sản xuất 01/10 → 30/04</div></div>
            <span class="bc-view-banner-badge">🏭 SX</span>
        </div>
        <div class="bc-card">
            <div class="bc-filter-bar" style="margin-bottom:0">
                <label>Từ ngày<input type="date" class="bc-input" id="sx-from"></label>
                <label>Đến ngày<input type="date" class="bc-input" id="sx-to"></label>
                <button type="button" class="bc-btn bc-btn-primary" id="sx-apply"><i class="fas fa-filter"></i> Lọc</button>
                <input type="search" class="bc-input bc-search" id="sx-q" placeholder="🔍 Tìm mã / tên sản phẩm">
            </div>
        </div>
        <div id="sx-diag" class="bc-mt-3"></div>
        <div class="bc-grid bc-grid-split bc-mt-3" style="align-items:start">
            <div class="bc-card"><div id="sx-cal">${skeleton(360)}</div>
                <div class="bc-note">Bấm ngày có số để xem chi tiết phiếu · ô đỏ = mùng 1–3 Tết</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Trung bình tháng đang xem</div></div><div id="sx-avg">${skeleton(70)}</div></div>
        </div>
        <div class="bc-section-title">Thống kê nhanh</div>
        <div id="sx-stats"></div>
        <div class="bc-section-title">Sản phẩm</div>
        <div class="bc-flex bc-justify-between bc-items-center bc-wrap bc-gap-2">
            <div id="sx-tabs" style="min-width:0;flex:1"></div>
            <select class="bc-input" id="sx-sort" aria-label="Sắp xếp" style="margin-bottom:.75rem">
                <option value="stock">Tồn kho lớn → bé</option><option value="plan">Sắp theo kế hoạch</option><option value="produced">Sắp theo sản lượng</option><option value="name">Sắp theo tên</option>
            </select>
        </div>
        <div id="sx-prods"></div>`;
    document.getElementById('sx-sort').value = state.sort;
    document.getElementById('sx-q').value = state.q;
    document.getElementById('sx-sort').addEventListener('change', (e) => { state.sort = e.target.value; paintProducts(); });
    document.getElementById('sx-q').addEventListener('input', debounce((e) => { state.q = e.target.value; paintProducts(); }, 200));
    document.getElementById('sx-apply').addEventListener('click', () => {
        const f = document.getElementById('sx-from').value, t = document.getElementById('sx-to').value;
        if (f && t && f > t) return;
        state.from = f || null; state.to = t || null;
        loadItems();
    });
    // Ảnh: image → /files/{item_code}.jpg → ảnh mặc định (sự kiện error không nổi bọt → capture).
    container.addEventListener('error', (e) => {
        const img = e.target;
        if (!(img instanceof HTMLImageElement) || !img.classList.contains('bc-prod-img')) return;
        const next = img.dataset.fallback;
        img.dataset.fallback = '';
        img.src = next || NO_IMG;
    }, true);

    const now = todayISO();
    await loadItems();
    // Tháng lịch mặc định: tháng hôm nay nếu nằm trong khoảng lọc; trước khoảng → tháng đầu
    // (vd 15/06 xem mùa 01/10 → 30/04 thì mở tháng 10); sau khoảng → tháng cuối.
    const ref = state.from && now < state.from ? state.from : (state.to && now > state.to ? state.to : now);
    await loadMonth(Number(ref.slice(0, 4)), Number(ref.slice(5, 7)));
}
