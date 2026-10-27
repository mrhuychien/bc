// #/an-mang — Ẩn / hiện mảng báo cáo với người xem (CHỈ System Manager; server guard bc.api.sections.*).
// Mảng bị ẩn: người xem không thấy trong menu, gõ thẳng đường dẫn bị đưa về trang đầu, máy chủ chặn API của
// mảng. Quản trị vẫn thấy hết (menu có dấu 👁‍🗨) để kiểm tra trước khi mở lại.

import * as api from '../lib/api.js';
import { NAV_GROUPS, sectionOf } from '../lib/nav.js';
import { escapeHtml, fmtNum } from '../lib/format.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

// Trạng thái sống qua các lần vào màn (module): một lệnh đang chờ máy chủ (pending) giữ busy tới khi xong — vào
// lại màn giữa chừng thì chờ lệnh đó rồi mới đọc lại, không đọc trạng thái cũ hơn lệnh đang chạy.
const st = { known: new Set(), hidden: new Set(), busy: false, target: null };
let pending = null;

function groups() {
    return NAV_GROUPS.filter((g) => g.items.length).map((g) => ({ ...g, keys: g.items.map((it) => sectionOf(it.route)) }));
}

/** Đang hiện? Trong lúc chờ máy chủ thì vẽ theo trạng thái ĐÍCH (công tắc không nhảy về chỗ cũ). */
function isShown(k) {
    return st.target && st.target.keys.includes(k) ? !st.target.hide : !st.hidden.has(k);
}

function rowHtml(it) {
    const k = sectionOf(it.route);
    const known = st.known.has(k);
    const shown = isShown(k);
    const dang = st.busy && st.target?.keys.includes(k);
    return `<label class="bc-am-row ${shown ? '' : 'bc-am-off'}">
        <span class="bc-am-name"><i class="fas ${it.icon}"></i>${escapeHtml(it.label)}
            ${known ? '' : '<span class="bc-badge bc-badge-muted">máy chủ chưa hỗ trợ</span>'}</span>
        <span class="bc-am-state">${dang ? (shown ? 'Đang mở…' : 'Đang ẩn…') : (shown ? 'Đang hiện' : 'Đang ẩn')}</span>
        <input type="checkbox" role="switch" class="bc-switch" data-section="${escapeHtml(k)}" ${shown ? 'checked' : ''}
            ${known && !st.busy ? '' : 'disabled'} aria-label="${escapeHtml(`Hiện ${it.label} với người xem`)}">
    </label>`;
}

function bodyHtml() {
    const all = groups();
    const total = all.reduce((a, g) => a + g.keys.filter((k) => st.known.has(k)).length, 0);
    const an = [...st.known].filter((k) => !isShown(k)).length;
    return `<div class="bc-filter-bar">
            <span class="bc-badge ${an ? 'bc-badge-warning' : 'bc-badge-success'}" id="am-count">${an ? `Đang ẩn ${fmtNum(an)} / ${fmtNum(total)} mảng` : 'Đang hiện tất cả'}</span>
            <button type="button" class="bc-btn bc-btn-sm" data-show-all ${an && !st.busy ? '' : 'disabled'}><i class="fas fa-eye"></i> Hiện tất cả</button>
        </div>
        <div class="bc-grid bc-grid-even" style="align-items:start">${all.map((g) => {
            const known = g.keys.filter((k) => st.known.has(k));
            const anyShown = known.some(isShown);
            return `<div class="bc-card"><div class="bc-card-head">
                    <div class="bc-card-title">${escapeHtml(g.title)}</div>
                    ${known.length > 1 ? `<button type="button" class="bc-btn bc-btn-sm" data-group="${escapeHtml(g.title)}" ${st.busy ? 'disabled' : ''}>
                        <i class="fas ${anyShown ? 'fa-eye-slash' : 'fa-eye'}"></i> ${anyShown ? 'Ẩn cả nhóm' : 'Hiện cả nhóm'}</button>` : ''}
                </div>${g.items.map(rowHtml).join('')}</div>`;
        }).join('')}</div>`;
}

/** Vẽ lại; `focusSel` = điều khiển đang có focus trước khi vẽ (bàn phím / trình đọc màn hình không mất chỗ). */
function paint(focusSel) {
    const el = document.getElementById('am-body');
    if (!el) return;
    el.innerHTML = bodyHtml();
    if (focusSel) el.querySelector(focusSel)?.focus();
}

function focusKey() {
    const a = document.activeElement;
    if (!a || !a.closest?.('#am-body')) return null;
    if (a.dataset.section) return `[data-section="${CSS.escape(a.dataset.section)}"]`;
    if (a.dataset.group) return `[data-group="${CSS.escape(a.dataset.group)}"]`;
    if (a.hasAttribute('data-show-all')) return '[data-show-all]';
    return null;
}

async function apply(keys, hide) {
    if (st.busy || !keys.length) return;
    const fk = focusKey();
    st.busy = true;
    st.target = { keys, hide };
    paint(fk);
    try {
        pending = api.sections.set(keys, hide);
        const res = await pending;
        st.hidden = new Set(res.hidden);
        window.dispatchEvent(new CustomEvent('bc:hidden-sections', { detail: res.hidden }));  // menu cập nhật dấu
        showToast(hide ? 'Đã ẩn với người xem' : 'Đã hiện lại với người xem', 'success');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        pending = null;
        st.busy = false;
        st.target = null;
        paint(fk);  // lỗi → vẽ theo trạng thái máy chủ đã biết (công tắc về vị trí cũ); rời màn thì không có gì để vẽ
    }
}

export async function render({ container, isCurrent }) {
    if (!window.BC_CONTEXT?.isSysManager) {
        container.innerHTML = emptyState({ icon: '🔒', title: 'Chỉ dành cho quản trị' });
        return;
    }
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Ẩn / hiện mảng báo cáo</div>
                <div class="bc-view-banner-sub">Áp dụng cho mọi người xem (BC Viewer) · quản trị vẫn thấy để kiểm tra</div></div>
            <span class="bc-view-banner-badge">🧩 Quản trị</span>
        </div>
        <div id="am-body">${skeleton(60)}${skeleton(220)}</div>
        <div class="bc-note bc-mt-3">ⓘ Mảng bị ẩn: người xem không thấy trong menu, mở đường dẫn cũ sẽ về trang đầu, và máy chủ từ chối
            trả số liệu của mảng đó. Người xem đang mở trang sẽ thấy thay đổi khi tải lại hoặc bấm Làm mới. Số liệu dùng chung có
            thể vẫn hiện ở mảng khác (vd doanh số hôm nay ở Thời gian thực). Mỗi lần đổi được ghi vào lịch sử của BC Settings.</div>`;
    const body = document.getElementById('am-body');
    body.addEventListener('change', (e) => {
        const sw = e.target.closest('[data-section]');
        if (sw) apply([sw.dataset.section], !sw.checked);
    });
    body.addEventListener('click', (e) => {
        const g = e.target.closest('[data-group]');
        if (g) {
            const grp = groups().find((x) => x.title === g.dataset.group);
            const keys = (grp?.keys || []).filter((k) => st.known.has(k));
            apply(keys, keys.some(isShown));
            return;
        }
        // Hiện tất cả: gửi MỌI mảng (kể cả mảng ai đó vừa ẩn ở tab khác / trên Desk sau khi màn này mở).
        if (e.target.closest('[data-show-all]')) apply([...st.known], false);
    });
    if (pending) await pending.catch(() => {});  // vào lại màn khi lệnh trước còn chạy: chờ xong rồi mới đọc
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
