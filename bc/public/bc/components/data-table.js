// Bảng dữ liệu: cuộn ngang + cột đầu sticky, sort theo cột (bấm tiêu đề), phân
// trang 10 dòng, nút cuộn ngang ◀ ▶. Trả CHUỖI HTML (nhúng vào template bất kỳ);
// trạng thái giữ trong registry, sự kiện qua delegation cấp document (bind 1 lần).
// Lọc/tìm làm TRƯỚC khi đưa rows vào; đổi lọc → gọi dataTable() mới (về trang 1).

import { escapeHtml } from '../lib/format.js';
import { emptyState } from './empty-state.js';

const REG = new Map();
let seq = 0;

/**
 * @param {Array<{key,label,render?,sortable?,sortValue?,align?}>} opts.columns
 * @param {Array<object>} opts.rows
 * @param {number}   [opts.pageSize=10]
 * @param {string}   [opts.sortKey]   sort ban đầu
 * @param {'asc'|'desc'} [opts.sortDir='desc']
 * @param {object}   [opts.totalRow]  dòng tổng {key: HTML đã dựng sẵn} — tính trên FULL set, ghim cuối mỗi trang
 * @param {function} [opts.onRowClick] (row) => void
 * @param {boolean}  [opts.scrollButtons=true]
 */
export function dataTable(opts) {
    const { rows = [], emptyMessage = 'Không có dữ liệu' } = opts;
    if (!rows.length) return emptyState({ icon: '📭', title: emptyMessage });
    const id = 'dt' + (++seq);
    if (REG.size > 100) REG.delete(REG.keys().next().value);
    REG.set(id, {
        columns: opts.columns, rows: rows.slice(), pageSize: opts.pageSize || 10, page: 0,
        sortKey: opts.sortKey || null, sortDir: opts.sortDir || 'desc',
        totalRow: opts.totalRow || null, onRowClick: opts.onRowClick || null,
        scrollButtons: opts.scrollButtons !== false,
    });
    applySort(REG.get(id));
    return `<div class="bc-table-wrap" data-dt="${id}">${inner(id)}</div>`;
}

function sortVal(col, row) {
    const v = col.sortValue ? col.sortValue(row) : row[col.key];
    return v === null || v === undefined ? -Infinity : v;
}

function applySort(st) {
    if (!st.sortKey) return;
    const col = st.columns.find((c) => c.key === st.sortKey);
    if (!col) return;
    const dir = st.sortDir === 'asc' ? 1 : -1;
    st.rows.sort((a, b) => {
        const x = sortVal(col, a), y = sortVal(col, b);
        if (typeof x === 'string' || typeof y === 'string') return String(x).localeCompare(String(y), 'vi') * dir;
        return (x - y) * dir;
    });
}

function cell(col, row) {
    return col.render ? col.render(row) : escapeHtml(row[col.key] ?? '');
}

function inner(id) {
    const st = REG.get(id);
    const total = st.rows.length;
    const pages = Math.max(1, Math.ceil(total / st.pageSize));
    const start = st.page * st.pageSize;
    const slice = st.rows.slice(start, start + st.pageSize);
    const head = st.columns.map((c) => {
        const sortable = c.sortable !== false;
        const sorted = st.sortKey === c.key;
        const ico = sorted ? (st.sortDir === 'asc' ? '▲' : '▼') : (sortable ? '↕' : '');
        return `<th class="${c.align === 'left' ? 'bc-left' : ''} ${sortable ? 'bc-sortable' : ''} ${sorted ? 'bc-sorted' : ''}"
            ${sortable ? `data-dt-sort="${id}" data-key="${escapeHtml(c.key)}"` : ''}>${escapeHtml(c.label)}${ico ? `<span class="bc-sort-ico">${ico}</span>` : ''}</th>`;
    }).join('');
    const body = slice.map((r, i) => `<tr class="${st.onRowClick ? 'bc-clickable' : ''}" data-dt-row="${id}" data-i="${start + i}">
        ${st.columns.map((c) => `<td class="${c.align === 'left' ? 'bc-left' : ''}">${cell(c, r)}</td>`).join('')}</tr>`).join('');
    const totalRow = st.totalRow ? `<tr class="bc-row-total">${st.columns.map((c) =>
        `<td class="${c.align === 'left' ? 'bc-left' : ''}">${st.totalRow[c.key] ?? ''}</td>`).join('')}</tr>` : '';
    const scroll = st.scrollButtons ? `<div class="bc-scroll-btns">
        <button type="button" class="bc-btn bc-btn-sm" data-dt-scroll="${id}" data-dir="-1" aria-label="Cuộn trái">◀</button>
        <button type="button" class="bc-btn bc-btn-sm" data-dt-scroll="${id}" data-dir="1" aria-label="Cuộn phải">▶</button></div>` : '';
    const pager = pages > 1 ? `<div class="bc-pager">
        <button type="button" class="bc-pager-btn" data-dt-page="${id}" data-dir="-1" ${st.page <= 0 ? 'disabled' : ''}>‹ Trước</button>
        <span class="bc-pager-info">Trang ${st.page + 1}/${pages} · ${total} dòng</span>
        <button type="button" class="bc-pager-btn" data-dt-page="${id}" data-dir="1" ${st.page >= pages - 1 ? 'disabled' : ''}>Sau ›</button></div>` : '';
    return `${scroll ? `<div class="bc-flex bc-justify-between bc-items-center" style="margin-bottom:6px">
            <span class="bc-muted bc-text-sm">${total} dòng</span>${scroll}</div>` : ''}
        <div class="bc-table-scroll"><table class="bc-table"><thead><tr>${head}</tr></thead>
        <tbody>${body}${totalRow}</tbody></table></div>${pager}`;
}

function redraw(id, keepScroll = true) {
    const el = document.querySelector(`[data-dt="${id}"]`);
    if (!el) { REG.delete(id); return; }
    const left = el.querySelector('.bc-table-scroll')?.scrollLeft || 0;
    el.innerHTML = inner(id);
    if (keepScroll) { const sc = el.querySelector('.bc-table-scroll'); if (sc) sc.scrollLeft = left; }
}

document.addEventListener('click', (e) => {
    const sortTh = e.target.closest('[data-dt-sort]');
    if (sortTh) {
        const st = REG.get(sortTh.dataset.dtSort);
        if (!st) return;
        const key = sortTh.dataset.key;
        st.sortDir = st.sortKey === key && st.sortDir === 'desc' ? 'asc' : 'desc';
        st.sortKey = key;
        st.page = 0;
        applySort(st);
        redraw(sortTh.dataset.dtSort);
        return;
    }
    const pg = e.target.closest('[data-dt-page]');
    if (pg) {
        const st = REG.get(pg.dataset.dtPage);
        if (!st) return;
        const pages = Math.max(1, Math.ceil(st.rows.length / st.pageSize));
        st.page = Math.min(Math.max(0, st.page + Number(pg.dataset.dir)), pages - 1);
        redraw(pg.dataset.dtPage, false);
        return;
    }
    const sc = e.target.closest('[data-dt-scroll]');
    if (sc) {
        const box = document.querySelector(`[data-dt="${sc.dataset.dtScroll}"] .bc-table-scroll`);
        if (box) box.scrollBy({ left: Number(sc.dataset.dir) * box.clientWidth * 0.7, behavior: 'smooth' });
        return;
    }
    const tr = e.target.closest('[data-dt-row]');
    if (tr && !e.target.closest('a')) {
        const st = REG.get(tr.dataset.dtRow);
        if (st?.onRowClick) st.onRowClick(st.rows[Number(tr.dataset.i)]);
    }
});
