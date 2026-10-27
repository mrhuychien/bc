// Định dạng số/tiền/ngày kiểu VN — tập trung 1 chỗ. Thuần, không DOM.

const NUM = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 });
const NUM1 = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function fmtNum(n) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    return NUM.format(Math.round(Number(n)));
}

/** Tiền rút gọn: 1.600.000.000 → "1,6 tỷ"; 33.000.000 → "33 tr"; 12.000 → "12k". */
export function fmtMoney(n) {
    n = Number(n) || 0;
    const a = Math.abs(n);
    const one = (v) => (Math.round(v * 10) / 10).toString().replace('.', ',');
    if (a >= 1e9) return one(n / 1e9) + ' tỷ';
    if (a >= 1e6) return (a >= 1e8 ? fmtNum(n / 1e6) : one(n / 1e6)) + ' tr';
    if (a >= 1e3) return fmtNum(n / 1e3) + 'k';
    return fmtNum(n);
}

export function fmtMoneyFull(n) { return fmtNum(n) + ' ₫'; }

/** % đã nhân 100 từ server (float) → "12,3%"; null → "—". */
export function fmtPct(v, digits = 1) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return (digits === 1 ? NUM1.format(v) : NUM.format(v)) + '%';
}

/** Tăng trưởng % (cur so prev), null nếu prev = 0. */
export function calcGrowth(cur, prev) {
    const p = Number(prev) || 0;
    if (!p) return null;
    return Math.round(((Number(cur) || 0) - p) / Math.abs(p) * 1000) / 10;
}

export function growthClass(v) { return v === null || v === undefined ? 'bc-muted' : (v >= 0 ? 'bc-up' : 'bc-down'); }
export function growthText(v) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return (v >= 0 ? '▲ ' : '▼ ') + NUM1.format(Math.abs(v)) + '%';
}

export function escapeHtml(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Cơ sở số doanh số (đã chốt: giữ net_total) — ghi rõ dưới mọi màn có doanh số. */
export const SALES_BASIS = 'Doanh số = tiền hàng trước VAT (net_total), không gồm hoá đơn số dư đầu kỳ. '
    + 'Portal NPP và Kế toán tính gồm VAT (grand_total) nên số ở đó cao hơn.';
export function salesBasisNote() { return `<div class="bc-note bc-mt-3">ⓘ ${escapeHtml(SALES_BASIS)}</div>`; }

export function pad2(n) { return String(n).padStart(2, '0'); }
export function isoOf(y, m, d) { return `${y}-${pad2(m)}-${pad2(d)}`; }
export function todayISO() { const d = new Date(); return isoOf(d.getFullYear(), d.getMonth() + 1, d.getDate()); }
export function parseISO(s) { const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); }

/** "2025-11-01" → "01/11/2025" (short=true → "01/11"). */
export function fmtDate(s, short = false) {
    if (!s) return '—';
    const [y, m, d] = String(s).slice(0, 10).split('-');
    return short ? `${d}/${m}` : `${d}/${m}/${y}`;
}

export function daysBetween(aIso, bIso) {
    return Math.round((parseISO(bIso) - parseISO(aIso)) / 86400000);
}

export function parseQuery(qs) {
    const out = {};
    if (!qs) return out;
    for (const pair of qs.replace(/^\?/, '').split('&')) {
        if (!pair) continue;
        const [k, v = ''] = pair.split('=');
        out[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, ' '));
    }
    return out;
}

export function debounce(fn, wait = 250) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}
