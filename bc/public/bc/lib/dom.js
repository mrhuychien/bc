// Template helpers nhỏ — không virtual DOM. `html` KHÔNG tự escape: dữ liệu
// người dùng phải qua escapeHtml(...).

import { escapeHtml } from './format.js';

export { escapeHtml };

export function html(strings, ...values) {
    let out = '';
    strings.forEach((str, i) => {
        out += str;
        if (i < values.length) {
            const v = values[i];
            if (Array.isArray(v)) out += v.join('');
            else if (v !== null && v !== undefined && v !== false) out += String(v);
        }
    });
    return out;
}

export function $(sel, root = document) { return root.querySelector(sel); }
export function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

/** Event delegation: handler(e, matchedEl) khi target khớp selector bên trong root. */
export function on(root, type, selector, handler) {
    root.addEventListener(type, (e) => {
        const t = e.target.closest(selector);
        if (t && root.contains(t)) handler(e, t);
    });
}

/** Ghi nội dung vào phần tử con theo id nếu còn tồn tại (view có thể đã bị thay). */
export function fill(id, markup) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = markup;
    return el;
}
