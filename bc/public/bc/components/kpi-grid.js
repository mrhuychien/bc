import { escapeHtml } from '../lib/format.js';

/** Lưới ô số nhỏ: items [{label, value, sub?, cls?}]; cols mặc định 3. */
export function kpiGrid(items, cols = 3) {
    return `<div class="bc-grid bc-grid-${cols}">${items.map((it) => `
        <div class="bc-kpi">
            <div class="bc-kpi-label">${escapeHtml(it.label)}</div>
            <div class="bc-kpi-value ${it.cls || ''}">${it.value}</div>
            ${it.sub ? `<div class="bc-kpi-sub">${it.sub}</div>` : ''}
        </div>`).join('')}</div>`;
}
