// #/an-mang — Ẩn / hiện mảng báo cáo với người xem (CHỈ System Manager; server guard bc.api.sections.*).
// Mảng bị ẩn: người xem không thấy trong menu, gõ thẳng đường dẫn bị đưa về trang đầu, máy chủ chặn API của
// mảng. Quản trị vẫn thấy hết (menu có dấu 👁‍🗨) để kiểm tra trước khi mở lại.

import * as api from '../lib/api.js';
import { NAV_GROUPS, sectionOf } from '../lib/nav.js';
import { escapeHtml, fmtNum } from '../lib/format.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const st = { known: new Set(), hidden: new Set(), busy: false };

function groups() {
    return NAV_GROUPS.filter((g) => g.items.length).map((g) => ({ ...g, keys: g.items.map((it) => sectionOf(it.route)) }));
}

function rowHtml(it) {
    const k = sectionOf(it.route);
    const known = st.known.has(k);
    const shown = !st.hidden.has(k);
    return `<label class="bc-am-row ${shown ? '' : 'bc-am-off'}">
        <span class="bc-am-name"><i class="fas ${it.icon}"></i>${escapeHtml(it.label)}
            ${known ? '' : '<span class="bc-badge bc-badge-muted">máy chủ chưa hỗ trợ</span>'}</span>
        <span class="bc-am-state">${shown ? 'Đang hiện' : 'Đang ẩn'}</span>
        <input type="checkbox" role="switch" class="bc-switch" data-section="${escapeHtml(k)}" ${shown ? 'checked' : ''}
            ${known && !st.busy ? '' : 'disabled'} aria-label="${escapeHtml(`Hiện ${it.label} với người xem`)}">
    </label>`;
}

function bodyHtml() {
    const all = groups();
    const total = all.reduce((a, g) => a + g.keys.filter((k) => st.known.has(k)).length, 0);
    const an = [...st.hidden].length;
    return `<div class="bc-filter-bar">
            <span class="bc-badge ${an ? 'bc-badge-warning' : 'bc-badge-success'}" id="am-count">${an ? `Đang ẩn ${fmtNum(an)} / ${fmtNum(total)} mảng` : 'Đang hiện tất cả'}</span>
            <button type="button" class="bc-btn bc-btn-sm" data-show-all ${an && !st.busy ? '' : 'disabled'}><i class="fas fa-eye"></i> Hiện tất cả</button>
        </div>
        <div class="bc-grid bc-grid-even" style="align-items:start">${all.map((g) => {
            const known = g.keys.filter((k) => st.known.has(k));
            const anyShown = known.some((k) => !st.hidden.has(k));
            return `<div class="bc-card"><div class="bc-card-head">
                    <div class="bc-card-title">${escapeHtml(g.title)}</div>
                    ${known.length > 1 ? `<button type="button" class="bc-btn bc-btn-sm" data-group="${escapeHtml(g.title)}" ${st.busy ? 'disabled' : ''}>
                        <i class="fas ${anyShown ? 'fa-eye-slash' : 'fa-eye'}"></i> ${anyShown ? 'Ẩn cả nhóm' : 'Hiện cả nhóm'}</button>` : ''}
                </div>${g.items.map(rowHtml).join('')}</div>`;
        }).join('')}</div>`;
}

function paint() {
    const el = document.getElementById('am-body');
    if (el) el.innerHTML = bodyHtml();
}

async function apply(keys, hide, isCurrent) {
    if (st.busy || !keys.length) return;
    st.busy = true;
    paint();
    try {
        const res = await api.sections.set(keys, hide);
        st.hidden = new Set(res.hidden);
        window.dispatchEvent(new CustomEvent('bc:hidden-sections', { detail: res.hidden }));  // menu cập nhật dấu
        showToast(hide ? 'Đã ẩn với người xem' : 'Đã hiện lại với người xem', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        st.busy = false;
        if (isCurrent()) paint();  // lỗi → vẽ lại theo trạng thái máy chủ đã biết (công tắc về vị trí cũ)
    }
}

export async function render({ container, isCurrent }) {
    if (!window.BC_CONTEXT?.isSysManager) {
        container.innerHTML = emptyState({ icon: '🔒', title: 'Chỉ dành cho quản trị' });
        return;
    }
    st.busy = false;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Ẩn / hiện mảng báo cáo</div>
                <div class="bc-view-banner-sub">Áp dụng cho mọi người xem (BC Viewer) · quản trị vẫn thấy để kiểm tra</div></div>
            <span class="bc-view-banner-badge">🧩 Quản trị</span>
        </div>
        <div id="am-body">${skeleton(60)}${skeleton(220)}</div>
        <div class="bc-note bc-mt-3">ⓘ Mảng bị ẩn: người xem không thấy trong menu, mở đường dẫn cũ sẽ về trang đầu, và máy chủ từ chối
            trả số liệu của mảng đó. Người xem đang mở trang sẽ thấy thay đổi khi tải lại hoặc bấm Làm mới. Số liệu dùng chung có
            thể vẫn hiện ở mảng khác (vd doanh số hôm nay ở Thời gian thực).</div>`;
    const body = document.getElementById('am-body');
    body.addEventListener('change', (e) => {
        const sw = e.target.closest('[data-section]');
        if (sw) apply([sw.dataset.section], !sw.checked, isCurrent);
    });
    body.addEventListener('click', (e) => {
        const g = e.target.closest('[data-group]');
        if (g) {
            const grp = groups().find((x) => x.title === g.dataset.group);
            const keys = (grp?.keys || []).filter((k) => st.known.has(k));
            const anyShown = keys.some((k) => !st.hidden.has(k));
            apply(keys, anyShown, isCurrent);
            return;
        }
        if (e.target.closest('[data-show-all]')) apply([...st.hidden], false, isCurrent);
    });
    try {
        const res = await api.sections.get();
        if (!isCurrent()) return;
        st.known = new Set(res.sections);
        st.hidden = new Set(res.hidden);
        paint();
    } catch (err) {
        if (isCurrent()) body.innerHTML = errorState(err);
    }
}
