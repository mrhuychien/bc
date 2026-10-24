// Nút "Ẩn khỏi báo cáo" cạnh tên sản phẩm — CHỈ render cho System Manager (server vẫn
// guard bc.api.hidden.*). bindHide(root, onHidden) gắn 1 listener delegation trên root.

import * as api from '../lib/api.js';
import { escapeHtml } from '../lib/format.js';
import { showToast } from './toast.js';

export const canHide = () => !!window.BC_CONTEXT?.isSysManager;

export function hideBtn(itemCode, itemName) {
    if (!canHide() || !itemCode) return '';
    return `<button type="button" class="bc-hide-btn" data-hide-item="${escapeHtml(itemCode)}" data-hide-name="${escapeHtml(itemName || itemCode)}"
        title="Ẩn sản phẩm này khỏi báo cáo (chỉ quản trị)" aria-label="Ẩn khỏi báo cáo"><i class="fas fa-eye-slash"></i></button>`;
}

export function bindHide(root, onHidden) {
    if (!root || !canHide()) return;
    root.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-hide-item]');
        if (!btn) return;
        e.stopPropagation();
        const code = btn.dataset.hideItem;
        const note = window.prompt(`Ẩn "${btn.dataset.hideName}" khỏi báo cáo?\nLý do (tuỳ chọn) — hiện lại ở Quản trị › Ẩn sản phẩm:`, '');
        if (note === null) return;
        btn.disabled = true;
        try {
            await api.hidden.hide(code, note);
            showToast(`Đã ẩn ${btn.dataset.hideName}`, 'success');
            onHidden(code);
        } catch (err) {
            showToast(err.message, 'error');
            btn.disabled = false;
        }
    });
}
