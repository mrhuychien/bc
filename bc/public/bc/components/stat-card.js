import { escapeHtml, growthClass, growthText } from '../lib/format.js';

/**
 * Thẻ KPI: nhãn, giá trị lớn, các dòng phụ (cùng kỳ / tăng trưởng / cả năm ngoái).
 * rows: [[label, valueHtml]] — valueHtml do caller dựng (đã escape nếu là dữ liệu).
 */
export function statCard({ label, icon = '', value, rows = [], tone = '', growth = undefined }) {
    const g = growth === undefined ? '' :
        `<div class="bc-stat-row"><span>Tăng trưởng</span><b class="${growthClass(growth)}">${growthText(growth)}</b></div>`;
    return `<div class="bc-stat ${tone ? 'bc-tone-' + tone : ''}">
        <div class="bc-stat-label">${icon ? `<span>${icon}</span>` : ''}${escapeHtml(label)}</div>
        <div class="bc-stat-value" title="${escapeHtml(String(value).replace(/<[^>]+>/g, ''))}">${value}</div>
        <div class="bc-stat-rows">
            ${rows.map(([l, v]) => `<div class="bc-stat-row"><span>${escapeHtml(l)}</span><b>${v}</b></div>`).join('')}
            ${g}
        </div>
    </div>`;
}
