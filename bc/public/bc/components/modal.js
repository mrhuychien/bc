// Modal: bottom-sheet trên mobile, hộp giữa trên desktop. Đóng bằng nút ×,
// click nền, phím ESC, hoặc vuốt xuống (kéo từ tay nắm/tiêu đề, hoặc khi nội dung
// đang ở đỉnh cuộn).

import { escapeHtml } from '../lib/format.js';

let closeHandler = null;

function root() { return document.getElementById('bc-modal-mount'); }

function onKey(e) { if (e.key === 'Escape') closeModal(); }

export function showModal({ title, body, onClose = null }) {
    const el = root();
    if (!el) return null;
    closeHandler = onClose;
    el.innerHTML = `<div class="bc-modal-content" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="bc-modal-grip"></div>
        <div class="bc-modal-header">
            <h3 class="bc-modal-title">${escapeHtml(title)}</h3>
            <button type="button" class="bc-modal-close" aria-label="Đóng"><i class="fas fa-times"></i></button>
        </div>
        <div class="bc-modal-body">${body}</div>
    </div>`;
    el.classList.add('bc-show');
    document.body.style.overflow = 'hidden';
    el.querySelector('.bc-modal-close').onclick = closeModal;
    el.onclick = (e) => { if (e.target === el) closeModal(); };
    document.addEventListener('keydown', onKey);
    bindSwipe(el.querySelector('.bc-modal-content'));
    return el.querySelector('.bc-modal-body');
}

function bindSwipe(sheet) {
    let startY = null, dy = 0;
    sheet.addEventListener('touchstart', (e) => {
        const fromHandle = e.target.closest('.bc-modal-grip, .bc-modal-header');
        if (!fromHandle && sheet.scrollTop > 0) { startY = null; return; }
        startY = e.touches[0].clientY;
        dy = 0;
        sheet.style.transition = 'none';
    }, { passive: true });
    sheet.addEventListener('touchmove', (e) => {
        if (startY === null) return;
        dy = Math.max(0, e.touches[0].clientY - startY);
        if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    }, { passive: true });
    sheet.addEventListener('touchend', () => {
        if (startY === null) return;
        sheet.style.transition = '';
        if (dy > 90) closeModal();
        else sheet.style.transform = '';
        startY = null;
    });
}

export function closeModal() {
    const el = root();
    if (!el || !el.classList.contains('bc-show')) return;
    el.classList.remove('bc-show');
    el.innerHTML = '';
    document.body.style.overflow = '';
    document.removeEventListener('keydown', onKey);
    if (closeHandler) { try { closeHandler(); } catch (e) { console.error(e); } closeHandler = null; }
}
