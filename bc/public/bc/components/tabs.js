import { escapeHtml } from '../lib/format.js';

/**
 * Hàng tab dạng pill. Trả HTML; bind bằng bindTabs(root, onChange).
 * items: [{key, label, count?}]
 */
export function tabs(items, active, name = 'tab') {
    return `<div class="bc-tabs" role="tablist" data-tabs="${escapeHtml(name)}">${items.map((it) => `
        <button type="button" role="tab" class="bc-tab ${it.key === active ? 'bc-active' : ''}" data-tab-key="${escapeHtml(it.key)}"
            aria-selected="${it.key === active}">${escapeHtml(it.label)}${it.count !== undefined ? `<span class="bc-tab-count">${escapeHtml(it.count)}</span>` : ''}</button>`).join('')}
    </div>`;
}

export function bindTabs(root, name, onChange) {
    const bar = root.querySelector(`[data-tabs="${name}"]`);
    if (!bar) return;
    bar.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-tab-key]');
        if (!btn) return;
        bar.querySelectorAll('.bc-tab').forEach((b) => {
            const on = b === btn;
            b.classList.toggle('bc-active', on);
            b.setAttribute('aria-selected', on);
        });
        onChange(btn.dataset.tabKey);
    });
}
