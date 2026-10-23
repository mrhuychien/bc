// Lịch tháng dùng chung (KD ngày + SX Tết): thứ Hai đầu tuần, ô có ngày dương,
// ngày âm (Hồ Ngọc Đức), 1–2 dòng giá trị; ô có dữ liệu bấm được; nút ◀ ● ▶.

import { escapeHtml, isoOf, todayISO } from '../lib/format.js';
import { lunarLabel, isTetHoliday } from '../lib/lunar.js';

const DOW = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

/**
 * renderCalendar(el, {
 *   year, month,                       // month 1–12
 *   cells: { 'YYYY-MM-DD': { v1, v2, hot?, title? } },
 *   selected?, markTet?: bool,         // markTet → tô đỏ mùng 1–3 Tết
 *   onSelect(iso), onNav(year, month)  // onNav: ◀ / ● (tháng hiện tại) / ▶
 * })
 */
export function renderCalendar(el, opts) {
    const { year, month, cells = {}, selected = null, markTet = false } = opts;
    const first = new Date(year, month - 1, 1);
    const days = new Date(year, month, 0).getDate();
    const lead = (first.getDay() + 6) % 7;   // Thứ Hai = 0
    const today = todayISO();
    let grid = DOW.map((d, i) => `<div class="bc-cal-dow ${i === 6 ? 'bc-sun' : ''}">${d}</div>`).join('');
    for (let i = 0; i < lead; i++) grid += '<div class="bc-cal-cell bc-empty-cell"></div>';
    for (let d = 1; d <= days; d++) {
        const iso = isoOf(year, month, d);
        const c = cells[iso];
        const cls = ['bc-cal-cell'];
        if (c) cls.push('bc-has');
        if (c?.hot) cls.push('bc-hot');
        if (iso === today) cls.push('bc-today');
        if (iso === selected) cls.push('bc-selected');
        if (markTet && isTetHoliday(d, month, year)) cls.push('bc-tet');
        const tag = c ? 'button type="button"' : 'div';
        grid += `<${tag} class="${cls.join(' ')}" ${c ? `data-cal-date="${iso}"` : ''} ${c?.title ? `title="${escapeHtml(c.title)}"` : ''}>
            <div class="bc-cal-top"><span class="bc-cal-day">${d}</span><span class="bc-cal-lunar">${lunarLabel(d, month, year, d === 1)}</span></div>
            ${c ? `<div class="bc-cal-val">${c.v1 ?? ''}</div>${c.v2 ? `<div class="bc-cal-val2">${c.v2}</div>` : ''}` : ''}
        </${c ? 'button' : 'div'}>`;
    }
    el.innerHTML = `<div class="bc-cal-head">
            <div class="bc-cal-title">Tháng ${month}/${year}</div>
            <div class="bc-cal-nav">
                <button type="button" class="bc-cal-btn" data-cal-nav="-1" aria-label="Tháng trước">◀</button>
                <button type="button" class="bc-cal-btn" data-cal-nav="0" aria-label="Tháng hiện tại">●</button>
                <button type="button" class="bc-cal-btn" data-cal-nav="1" aria-label="Tháng sau">▶</button>
            </div>
        </div>
        <div class="bc-cal-grid">${grid}</div>`;
    el.onclick = (e) => {
        const nav = e.target.closest('[data-cal-nav]');
        if (nav && opts.onNav) {
            const step = Number(nav.dataset.calNav);
            let y = year, m = month;
            if (step === 0) { const t = new Date(); y = t.getFullYear(); m = t.getMonth() + 1; }
            else { m += step; if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; } }
            opts.onNav(y, m);
            return;
        }
        const cell = e.target.closest('[data-cal-date]');
        if (cell && opts.onSelect) opts.onSelect(cell.dataset.calDate);
    };
}
