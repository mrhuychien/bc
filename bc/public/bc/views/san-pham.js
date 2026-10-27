// #/san-pham — Top sản phẩm theo số hộp: lọc Tất cả / Hàng TT / Hàng Tết (lọc theo
// item_group phía server), mỗi dòng 2 thanh năm nay / cùng kỳ + badge tăng trưởng.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum, growthText, salesBasisNote } from '../lib/format.js';
import { tabs, bindTabs } from '../components/tabs.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';
import { hideBtn, bindHide } from '../components/hide-item.js';

const PAGE = 10;
const state = { group: 'all', rows: [], page: 0, meta: null };

function badge(v) {
    const cls = v === null || v === undefined ? 'bc-badge-muted' : (v >= 0 ? 'bc-badge-success' : 'bc-badge-danger');
    return `<span class="bc-badge ${cls}">${growthText(v)}</span>`;
}

function paint() {
    const { rows, page } = state;
    if (!rows.length) { fill('sp-list', emptyState({ title: 'Không có sản phẩm phát sinh' })); return; }
    const max = Math.max(...rows.map((r) => Math.max(r.qty, r.qty_sp)), 1);
    const pages = Math.ceil(rows.length / PAGE);
    const slice = rows.slice(page * PAGE, page * PAGE + PAGE);
    fill('sp-list', `<div class="bc-rank-list">${slice.map((r, i) => `
        <div class="bc-rank-row">
            <div class="bc-rank-no">${page * PAGE + i + 1}</div>
            <div style="min-width:0">
                <div class="bc-rank-name" title="${escapeHtml(r.item_name)}">${escapeHtml(r.short_name)}</div>
                <div class="bc-rank-bars">
                    <div class="bc-rank-bar"><div class="bc-progress"><span style="width:${Math.max(0, r.qty) / max * 100}%"></span></div><b>${fmtNum(r.qty)}</b></div>
                    <div class="bc-rank-bar"><div class="bc-progress bc-alt"><span style="width:${Math.max(0, r.qty_sp) / max * 100}%"></span></div><b>${fmtNum(r.qty_sp)}</b></div>
                </div>
            </div>
            <div class="bc-flex bc-items-center bc-gap-2">${badge(r.growth_pct)}${hideBtn(r.item_code, r.item_name)}</div>
        </div>`).join('')}</div>
        ${pages > 1 ? `<div class="bc-pager">
            <button type="button" class="bc-pager-btn" data-sp-page="-1" ${page <= 0 ? 'disabled' : ''}>‹ Trước</button>
            <span class="bc-pager-info">Trang ${page + 1}/${pages} · ${rows.length} SP</span>
            <button type="button" class="bc-pager-btn" data-sp-page="1" ${page >= pages - 1 ? 'disabled' : ''}>Sau ›</button></div>` : ''}`);
}

async function load(group) {
    state.group = group;
    state.page = 0;
    fill('sp-list', skeleton(52, 6, 8));
    fill('sp-sub', '');
    try {
        const res = await api.kd.topProducts(group);
        if (state.group !== group) return;
        state.rows = res.rows;
        state.meta = res.meta;
        const m = res.meta;
        const win = m.window === 'tet'
            ? `Mùa Tết ${m.tet_year}: ${fmtDate(m.cs)} → ${fmtDate(m.ce)} · cùng kỳ đến ${fmtDate(m.pe)}`
            : `Năm TC: ${fmtDate(m.cs)} → ${fmtDate(m.ce)} · cùng kỳ ${fmtDate(m.ps)} → ${fmtDate(m.pe)}`;
        fill('sp-sub', `${escapeHtml(win)}${m.item_group ? ` · nhóm "${escapeHtml(m.item_group)}"` : ''}`);
        paint();
    } catch (err) {
        fill('sp-list', errorState(err));
    }
}

export async function render({ container }) {
    const g = window.BC_CONTEXT?.groups || {};
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Sản phẩm bán chạy</div>
                <div class="bc-view-banner-sub">Xếp theo số hộp thực bán (đã trừ trả) · thanh tím = năm nay, vàng = cùng kỳ</div></div>
            <span class="bc-view-banner-badge">📦 Top SP</span>
        </div>
        ${tabs([{ key: 'all', label: 'Tất cả' }, { key: 'traditional', label: g.traditional || 'Hàng TT' }, { key: 'tet', label: g.tet || 'Hàng Tết' }], state.group, 'sp')}
        <div class="bc-card"><div class="bc-card-sub" id="sp-sub" style="margin-bottom:.6rem"></div><div id="sp-list"></div></div>
        ${salesBasisNote()}`;
    bindTabs(container, 'sp', (k) => load(k));
    bindHide(container.querySelector('#sp-list'), (code) => { state.rows = state.rows.filter((r) => r.item_code !== code); paint(); });
    container.querySelector('#sp-list').addEventListener('click', (e) => {
        const b = e.target.closest('[data-sp-page]');
        if (!b) return;
        state.page += Number(b.dataset.spPage);
        paint();
    });
    await load(state.group);
}
