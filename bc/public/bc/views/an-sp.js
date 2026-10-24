// #/an-sp — Quản lý sản phẩm ẩn khỏi báo cáo (CHỈ System Manager; server guard).
// Mã bị ẩn không hiện ở danh sách theo mã (SX Hàng Tết, Mã hàng Tết, Sản phẩm bán chạy);
// tổng doanh số / sản lượng công ty không đổi.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { debounce, escapeHtml } from '../lib/format.js';
import { dataTable } from '../components/data-table.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

function fmtDT(s) {
    if (!s) return '—';
    const [d, t] = String(s).split(' ');
    const [y, m, dd] = d.split('-');
    return `${dd}/${m}/${y}${t ? ' ' + t.slice(0, 5) : ''}`;
}

async function loadHidden() {
    fill('an-list', skeleton(44, 4, 6));
    try {
        const res = await api.hidden.list();
        fill('an-count', `${res.rows.length} mã đang ẩn`);
        fill('an-list', res.rows.length ? dataTable({
            rows: res.rows, sortKey: 'hidden_on', sortDir: 'desc', emptyMessage: 'Chưa ẩn mã nào',
            columns: [
                { key: 'item_name', label: 'Sản phẩm', align: 'left',
                    render: (r) => `<b>${escapeHtml(r.item_name || r.item_code)}</b><div class="bc-muted" style="font-size:.75rem">${escapeHtml(r.item_code)}${r.item_group ? ' · ' + escapeHtml(r.item_group) : ''}</div>` },
                { key: 'note', label: 'Lý do', align: 'left', render: (r) => escapeHtml(r.note || '—') },
                { key: 'hidden_on', label: 'Ẩn lúc', render: (r) => `${fmtDT(r.hidden_on)}<div class="bc-muted" style="font-size:.72rem">${escapeHtml(r.hidden_by || '')}</div>` },
                { key: 'item_code', label: '', sortable: false,
                    render: (r) => `<button type="button" class="bc-btn bc-btn-sm" data-unhide="${escapeHtml(r.item_code)}"><i class="fas fa-eye"></i> Hiện lại</button>` },
            ],
        }) : emptyState({ icon: '👁️', title: 'Chưa ẩn sản phẩm nào', message: 'Tìm mã ở ô phía trên, hoặc bấm biểu tượng 👁‍🗨 cạnh tên sản phẩm trong báo cáo.' }));
    } catch (err) {
        fill('an-list', errorState(err));
    }
}

async function search(q) {
    if (q.trim().length < 2) { fill('an-results', ''); return; }
    try {
        const res = await api.hidden.search(q);
        fill('an-results', res.rows.length ? `<div class="bc-an-results">${res.rows.map((r) => `
            <div class="bc-an-row">
                <div style="min-width:0"><b>${escapeHtml(r.item_name)}</b>
                    <div class="bc-muted" style="font-size:.75rem">${escapeHtml(r.item_code)} · ${escapeHtml(r.item_group || '')}</div></div>
                ${r.hidden ? '<span class="bc-badge bc-badge-muted">Đang ẩn</span>'
                    : `<button type="button" class="bc-btn bc-btn-sm" data-hide-code="${escapeHtml(r.item_code)}" data-hide-name="${escapeHtml(r.item_name)}"><i class="fas fa-eye-slash"></i> Ẩn</button>`}
            </div>`).join('')}</div>` : '<div class="bc-muted bc-text-sm">Không tìm thấy mã nào.</div>');
    } catch (err) {
        fill('an-results', errorState(err));
    }
}

export async function render({ container }) {
    if (!window.BC_CONTEXT?.isSysManager) {
        container.innerHTML = emptyState({ icon: '🔒', title: 'Chỉ dành cho quản trị' });
        return;
    }
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Ẩn sản phẩm khỏi báo cáo</div>
                <div class="bc-view-banner-sub">Mã bị ẩn không hiện ở SX Hàng Tết, Mã hàng Tết, Sản phẩm bán chạy · tổng doanh số không đổi</div></div>
            <span class="bc-view-banner-badge" id="an-count">…</span>
        </div>
        <div class="bc-card">
            <div class="bc-card-head"><div class="bc-card-title">🔍 Tìm mã để ẩn</div></div>
            <input type="search" class="bc-input" id="an-q" placeholder="Nhập mã hoặc tên sản phẩm (≥ 2 ký tự)" autocomplete="off" style="width:100%">
            <div id="an-results" class="bc-mt-2"></div>
        </div>
        <div class="bc-section-title">Đang ẩn</div>
        <div class="bc-card"><div id="an-list"></div></div>`;
    const q = document.getElementById('an-q');
    q.addEventListener('input', debounce(() => search(q.value), 300));
    document.getElementById('an-results').addEventListener('click', async (e) => {
        const b = e.target.closest('[data-hide-code]');
        if (!b) return;
        const note = window.prompt(`Ẩn "${b.dataset.hideName}" khỏi báo cáo? Lý do (tuỳ chọn):`, '');
        if (note === null) return;
        b.disabled = true;
        try {
            await api.hidden.hide(b.dataset.hideCode, note);
            showToast('Đã ẩn', 'success');
            search(q.value);
            loadHidden();
        } catch (err) { showToast(err.message, 'error'); b.disabled = false; }
    });
    document.getElementById('an-list').addEventListener('click', async (e) => {
        const b = e.target.closest('[data-unhide]');
        if (!b) return;
        b.disabled = true;
        try {
            await api.hidden.unhide(b.dataset.unhide);
            showToast('Đã hiện lại', 'success');
            loadHidden();
            if (q.value) search(q.value);
        } catch (err) { showToast(err.message, 'error'); b.disabled = false; }
    });
    await loadHidden();
}
