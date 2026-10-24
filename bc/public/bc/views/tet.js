// #/tet — Phân tích Hàng Tết {năm}: 4 panel bảng (NPP tăng trưởng, NPP chi tiết,
// Siêu thị MT, Mã hàng). Mốc mùa + cách so cùng kỳ từ BC Settings (server trả meta).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum, fmtPct, growthClass, growthText } from '../lib/format.js';
import { dataTable } from '../components/data-table.js';
import { skeleton } from '../components/skeleton.js';
import { errorState } from '../components/empty-state.js';
import { hideBtn, bindHide } from '../components/hide-item.js';

const num = (k) => (r) => fmtNum(r[k]);
const growthBadge = (v) => `<span class="bc-badge ${v === null || v === undefined ? 'bc-badge-muted' : (v >= 0 ? 'bc-badge-success' : 'bc-badge-danger')}">${growthText(v)}</span>`;
const growthCell = (k) => (r) => `<span class="${growthClass(r[k])}">${growthText(r[k])}</span>`;
function retCell(v) {
    if (v === null || v === undefined) return '<span class="bc-muted">—</span>';
    return `<span class="${v > 15 ? 'bc-txt-danger' : (v > 10 ? 'bc-txt-warning' : 'bc-txt-success')}">${fmtPct(v)}</span>`;
}
function planBadge(v) {
    if (v === null || v === undefined) return '<span class="bc-badge bc-badge-muted">—</span>';
    return `<span class="bc-badge ${v >= 100 ? 'bc-badge-success' : (v >= 70 ? 'bc-badge-warning' : 'bc-badge-danger')}">${fmtPct(v, 0)}</span>`;
}
const sum = (rows, k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
const pctOf = (a, b) => (b ? Math.round(a / b * 1000) / 10 : null);

function panel(id, title, sub) {
    return `<div class="bc-card"><div class="bc-card-head"><div><div class="bc-card-title">${title}</div>
        <div class="bc-card-sub" id="${id}-sub">${sub || ''}</div></div></div><div id="${id}">${skeleton(220)}</div></div>`;
}

function nppGrowthTable(res) {
    const rows = res.rows;
    const ty = sum(rows, 'this_year'), ly = sum(rows, 'last_year');
    return dataTable({
        rows, sortKey: 'this_year', emptyMessage: 'Chưa có NPP mua Hàng Tết',
        columns: [
            { key: 'customer', label: 'NPP', align: 'left', render: (r) => escapeHtml(r.customer) },
            { key: 'this_year', label: 'Năm nay', render: num('this_year') },
            { key: 'last_year', label: 'Năm trước (cùng kỳ)', render: num('last_year') },
            { key: 'growth_pct', label: 'Tăng trưởng', render: growthCell('growth_pct') },
        ],
        totalRow: { customer: `Tổng (${rows.length})`, this_year: fmtNum(ty), last_year: fmtNum(ly),
            growth_pct: `<span class="${growthClass(pctOf(ty - ly, ly))}">${growthText(pctOf(ty - ly, ly))}</span>` },
    });
}

function detailTable(res, who, targetPct) {
    const rows = res.rows;
    const tin = sum(rows, 'total_in'), tret = sum(rows, 'total_return');
    return dataTable({
        rows, sortKey: 'this_year', emptyMessage: `Chưa có ${who} mua Hàng Tết`,
        columns: [
            { key: 'customer', label: who, align: 'left', render: (r) => `${escapeHtml(r.customer)} ${growthBadge(r.growth_pct)}`, sortValue: (r) => r.customer },
            { key: 'last_year', label: 'Năm trước', render: num('last_year') },
            { key: 'last_year_target', label: `NT + ${fmtNum(targetPct)}%`, render: num('last_year_target') },
            { key: 'last_year_out', label: 'NT đi (cùng kỳ)', render: num('last_year_out') },
            { key: 'this_year', label: 'Năm nay', render: num('this_year') },
            { key: 'total_in', label: 'Tổng nhập', render: num('total_in') },
            { key: 'total_return', label: 'Tổng về', render: num('total_return') },
            { key: 'return_pct', label: '% Về', render: (r) => retCell(r.return_pct) },
            { key: 'growth_pct', label: 'Tăng trưởng', render: growthCell('growth_pct') },
        ],
        totalRow: { customer: `Tổng (${rows.length})`, last_year: fmtNum(sum(rows, 'last_year')),
            last_year_target: fmtNum(sum(rows, 'last_year_target')), last_year_out: fmtNum(sum(rows, 'last_year_out')),
            this_year: fmtNum(sum(rows, 'this_year')), total_in: fmtNum(tin), total_return: fmtNum(tret),
            return_pct: retCell(pctOf(tret, tin)) },
    });
}

function itemsTable(res) {
    const rows = res.rows;
    const out = sum(rows, 'boxes_out'), back = sum(rows, 'boxes_back');
    const mtOut = sum(rows, 'mt_out'), mtBack = sum(rows, 'mt_back');
    const nppOut = sum(rows, 'npp_out'), nppBack = sum(rows, 'npp_back');
    const plan = sum(rows, 'plan'), net = sum(rows, 'net_boxes');
    return dataTable({
        rows, sortKey: 'value', emptyMessage: 'Chưa có mã Hàng Tết phát sinh',
        columns: [
            { key: 'short_name', label: 'Mã hàng', align: 'left',
                render: (r) => `<div class="bc-flex bc-items-center bc-gap-2">${hideBtn(r.item_code, r.item_name)}<div><b>${escapeHtml(r.short_name)}</b><div class="bc-muted" style="font-size:.68rem">${escapeHtml(r.item_code)}</div></div></div>` },
            { key: 'value', label: 'Giá trị', render: num('value') },
            { key: 'plan', label: 'Kế hoạch', render: num('plan') },
            { key: 'plan_pct', label: '% KH', render: (r) => planBadge(r.plan_pct) },
            { key: 'net_boxes', label: 'Thực (hộp)', render: num('net_boxes') },
            { key: 'boxes_out', label: 'Hộp đi', render: num('boxes_out') },
            { key: 'cartons_out', label: 'Thùng đi', render: (r) => fmtNum(r.cartons_out) },
            { key: 'boxes_back', label: 'Hộp về', render: num('boxes_back') },
            { key: 'return_pct', label: '% Về', render: (r) => retCell(r.return_pct) },
            { key: 'mt', label: 'MT', render: num('mt') },
            { key: 'gt', label: 'GT', render: num('gt') },
            { key: 'mt_out', label: 'MT đi', render: num('mt_out') },
            { key: 'mt_back', label: 'MT về', render: num('mt_back') },
            { key: 'mt_return_pct', label: '% MT về', render: (r) => retCell(r.mt_return_pct) },
            { key: 'npp_out', label: 'NPP đi', render: num('npp_out') },
            { key: 'npp_back', label: 'NPP về', render: num('npp_back') },
            { key: 'npp_return_pct', label: '% NPP về', render: (r) => retCell(r.npp_return_pct) },
        ],
        totalRow: { short_name: `Tổng (${rows.length})`, value: fmtNum(sum(rows, 'value')), plan: fmtNum(plan),
            plan_pct: planBadge(pctOf(net, plan)), net_boxes: fmtNum(net), boxes_out: fmtNum(out),
            cartons_out: fmtNum(sum(rows, 'cartons_out')), boxes_back: fmtNum(back), return_pct: retCell(pctOf(back, out)),
            mt: fmtNum(sum(rows, 'mt')), gt: fmtNum(sum(rows, 'gt')), mt_out: fmtNum(mtOut), mt_back: fmtNum(mtBack),
            mt_return_pct: retCell(pctOf(mtBack, mtOut)), npp_out: fmtNum(nppOut), npp_back: fmtNum(nppBack),
            npp_return_pct: retCell(pctOf(nppBack, nppOut)) },
    });
}

function seasonLine(m) {
    return `Mùa ${fmtDate(m.season_start)} → ${fmtDate(m.asof)} · so cùng kỳ: ${escapeHtml(m.compare_label)} (đến ${fmtDate(m.ly_asof)})`;
}

export async function render({ container, isCurrent }) {
    const ctx = window.BC_CONTEXT || {};
    const t = ctx.tet;
    const title = t ? (t.betweenSeasons ? `Kết quả Tết ${t.year}` : `Phân tích Hàng Tết ${t.year}`) : 'Phân tích Hàng Tết';
    const targetPct = ctx.targetPct ?? 20;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">${escapeHtml(title)}</div>
                <div class="bc-view-banner-sub">${t ? `Mùng 1 Tết ${fmtDate(t.date)} · so cùng kỳ: ${escapeHtml(t.compareLabel)}` : escapeHtml(ctx.tetError || '')}</div></div>
            <span class="bc-view-banner-badge">🧧 ${escapeHtml(ctx.groups?.tet || 'Hàng Tết')}</span>
        </div>
        ${t?.betweenSeasons ? `<div class="bc-alert">Đang giữa hai mùa — số liệu đã khoá tại mùng 1 Tết ${fmtDate(t.date)}. Mùa Tết ${t.year + 1} bắt đầu tính từ 01/${String(t.seasonStart).slice(5, 7)}/${t.year}.</div>` : ''}
        ${panel('tet-growth', 'NPP tăng trưởng')}
        ${panel('tet-npp', 'NPP chi tiết Hàng Tết', `Cột NT + ${fmtNum(targetPct)}% = mục tiêu trong BC Settings`)}
        ${panel('tet-mt', 'Siêu thị (MT)')}
        ${panel('tet-items', 'Mã hàng Tết')}`;

    const block = (promise, id, toHtml) => promise.then((res) => {
        if (!isCurrent()) return;
        fill(id, toHtml(res));
        const sub = document.getElementById(`${id}-sub`);
        if (sub && res.meta && !sub.textContent) sub.innerHTML = seasonLine(res.meta);
        else if (sub && res.meta) sub.innerHTML = `${seasonLine(res.meta)}<br>${sub.innerHTML}`;
    }).catch((err) => { if (isCurrent()) fill(id, errorState(err)); });

    // Admin ẩn 1 mã ở bảng Mã hàng → tải lại bảng (server đã xoá cache).
    bindHide(document.getElementById('tet-items'), () => api.tet.items()
        .then((r) => fill('tet-items', itemsTable(r))).catch((err) => fill('tet-items', errorState(err))));
    await Promise.all([
        block(api.tet.nppGrowth(), 'tet-growth', nppGrowthTable),
        block(api.tet.nppDetail(), 'tet-npp', (r) => detailTable(r, 'NPP', r.meta?.target_pct ?? targetPct)),
        block(api.tet.mtDetail(), 'tet-mt', (r) => detailTable(r, 'Siêu thị', r.meta?.target_pct ?? targetPct)),
        block(api.tet.items(), 'tet-items', (r) => itemsTable(r) + (r.meta && !r.meta.plan_column
            ? '<div class="bc-note">Chưa tìm thấy cột kế hoạch trên Item — cột Kế hoạch/% KH để trống.</div>' : '')),
    ]);
}
