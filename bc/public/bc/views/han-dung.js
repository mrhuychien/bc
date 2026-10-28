// #/han-dung — Hạn dùng & tồn âm: thành phẩm ngoài kho trả về & cách ly theo hạn dùng (hết hạn / cận date / chưa rõ
// hạn, khớp với tồn kho), hàng không bán được (kho trả về & cách ly, lô thu hồi, hết hạn) và tồn âm. Một lượt gọi
// bc.api.kho_han.get_overview — số tồn hiện tại (số theo lô: ảnh chụp ≤ 1 giờ, meta.lo_luc); khối nào không tính được
// thì báo riêng khối đó. Nhãn theo KHO ("ngoài kho trả về & cách ly"), không nói "kho bán" — các kho đó gồm cả kho xưởng,
// bán thành phẩm, nguyên liệu (cùng cách gọi với màn Tồn kho). Điện thoại: cột đầu các bảng ghi thêm lô · kho (cột Lô / Kho
// nằm ngoài màn hình — không thì các dòng cùng mã trông như trùng).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, fmtPct } from '../lib/format.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const SECTIONS = ['hd-kpis', 'hd-buckets', 'hd-lots', 'hd-chuaro', 'hd-khongban', 'hd-am'];
const QTY = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
const CT = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
const CT2 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });   // thùng của từng lô (0,25 thùng = 5 hộp)
let seq = 0;  // lượt tải mới nhất — lượt cũ về sau không đè

const MUC = {   // nhóm hạn: [biểu tượng, lớp thanh, lớp nhãn]
    het_han: ['⛔', '', 'bc-badge-danger'],
    d30: ['⏰', 'bc-alt', 'bc-badge-warning'],
    d60: ['⏳', 'bc-alt', 'bc-badge-warning'],
    d90: ['🕒', 'bc-ok', 'bc-badge-success'],
    tren90: ['✅', 'bc-ok', 'bc-badge-success'],
    chua_ro: ['❔', '', 'bc-badge-muted'],
};
const PART_LABEL = { toncu: 'Lô tồn cũ', lo_khong_hsd: 'Lô chưa ghi hạn', khong_lo: 'Chưa gắn lô', chua_quan_ly_lo: 'Mã không theo lô' };

function money(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function qtyNum(v) { return v === null || v === undefined ? '—' : QTY.format(Number(v)); }
function off(what) { return `<div class="bc-muted bc-text-sm">Chưa tính được ${escapeHtml(what)}.</div>`; }

function q1(v, u) { return `${qtyNum(v)} ${escapeHtml(u || '')}`.trim(); }

/** Một đơn vị: "40 Hộp · 2,3 thùng (+10 chưa khai thùng)". Thùng chỉ khi API trả số (phần âm / Kg: null) và số dương. */
function oneQty(q, u, ct, bw) {
    let s = q1(q, u);
    if (ct !== null && ct !== undefined && Number(q) > 0) {
        if (ct) s += ` · ${CT.format(ct)} thùng`;
        if (bw > 0) s += ` (+${qtyNum(bw)} chưa khai thùng)`;
    }
    return s;
}

/** Số lượng một phần. qty null = phần lẫn đơn vị (không cộng Hộp với Kg) → từng đơn vị: "30 Hộp · 1,5 thùng + 50 Kg". */
function qtyText(x, uom) {
    if (!x) return '—';
    if (x.qty === null || x.qty === undefined) {
        const t = x.theo_dvt || [];
        const parts = t.map((p) => oneQty(p.qty, p.uom, p.cartons, p.boxes_without_carton_factor));
        return parts.length ? parts.join(t.some((p) => p.qty < 0) ? ', ' : ' + ') : 'nhiều đơn vị';
    }
    return oneQty(x.qty, x.uom || uom, x.cartons, x.boxes_without_carton_factor);
}

/** Hai dòng ngắn cho thẻ số (thẻ hẹp trên điện thoại): số lượng, thùng — phần lẫn đơn vị: từng đơn vị. */
function qtyRows(x, uom) {
    if (x.qty === null || x.qty === undefined) {
        const t = x.theo_dvt || [];
        const ct = t.filter((p) => p.cartons).map((p) => `${CT.format(p.cartons)} (${escapeHtml(p.uom || '')})`);
        return [['Số lượng', t.map((p) => q1(p.qty, p.uom)).join(' + ') || '—'], ['Thùng', ct.join(' + ') || '—']];
    }
    return [['Số lượng', q1(x.qty, x.uom || uom)], ['Thùng', x.cartons ? CT.format(x.cartons) : '—']];
}

/** Số lượng chưa có giá vốn ở kho đang giữ (giá trị tính 0), theo từng đơn vị. */
function noRateText(x) {
    return (x.theo_dvt || []).filter((p) => p.qty_no_rate > 0).map((p) => q1(p.qty_no_rate, p.uom)).join(' + ');
}

/** Giá trị một phần của "không bán được": lỗi tính ≠ site chưa có dữ liệu. */
function partVal(p) {
    if (p.available) return money(p.value);
    return `<span class="bc-muted">${p.error ? 'chưa tính được' : 'chưa có'}</span>`;
}

function cartons(v, fmt = CT) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : fmt.format(v); }

/** Màn hẹp (dưới mốc desktop 900px của shell): cột Lô / Kho bị đẩy khỏi màn → gộp vào dòng phụ của cột đầu. */
function narrow() { return typeof window !== 'undefined' && !window.matchMedia('(min-width: 900px)').matches; }

/** Cột Sản phẩm: tên rút gọn + dòng phụ. Màn rộng: mã hàng. Màn hẹp: "lô · kho" (dòng phụ xuống dòng được, không bị cắt). */
function itemCell(r) {
    const sub = narrow() ? [r.lo, r.kho].filter(Boolean).join(' · ') || r.item_code : r.item_code;
    return `<b>${escapeHtml(r.short_name || r.item_code)}</b><div class="bc-muted bc-text-sm hd-sub"${narrow() ? ' style="white-space:normal"' : ''}>${escapeHtml(sub)}</div>`;
}

/** "2026-10-27 14:05:33.1" → "14:05". */
function hhmm(s) { return escapeHtml(String(s || '').slice(11, 16)); }

function conNgay(n) {
    if (n === null || n === undefined) return '—';
    if (n < 0) return `<span class="bc-badge bc-badge-danger">Quá ${fmtNum(-n)} ngày</span>`;
    if (n === 0) return '<span class="bc-badge bc-badge-warning">Hết hạn hôm nay</span>';
    return `<span class="bc-badge ${n <= 30 ? 'bc-badge-warning' : 'bc-badge-muted'}">Còn ${fmtNum(n)} ngày</span>`;
}

function bucket(h, key) { return (h.buckets || []).find((b) => b.key === key); }

// ─── Thẻ số ──────────────────────────────────────────────────────────────────
function kpisHtml(d) {
    const h = d.han, k = d.khong_ban, a = d.am;
    const hh = h.available ? bucket(h, 'het_han') : null;
    const na = (label, icon) => statCard({ label, icon, value: '—', rows: [['', 'Chưa tính được']] });
    return `<div class="bc-grid bc-grid-5">
        ${hh ? statCard({ label: 'Thành phẩm đã hết hạn', icon: '⛔', tone: 'danger', value: money(hh.value),
            rows: [...qtyRows(hh, h.uom), ['Số lô', fmtNum(hh.lots)], ['% giá trị thành phẩm', fmtPct(hh.pct)]] })
            : na('Thành phẩm đã hết hạn', '⛔')}
        ${h.available ? statCard({ label: `Cận date (≤ ${fmtNum(h.can_date.ngay)} ngày)`, icon: '⏰', tone: 'warning', value: money(h.can_date.value),
            rows: [...qtyRows(h.can_date, h.uom), ['Số lô', fmtNum(h.can_date.lots)], ['% giá trị thành phẩm', fmtPct(h.can_date.pct)]] })
            : na('Cận date', '⏰')}
        ${h.available ? statCard({ label: 'Chưa rõ hạn dùng', icon: '❔', value: money(h.chua_ro.value),
            rows: [...qtyRows(h.chua_ro, h.uom), ['% giá trị thành phẩm', fmtPct(h.chua_ro.pct)]] })
            : na('Chưa rõ hạn dùng', '❔')}
        ${k.available ? statCard({ label: 'Tồn không bán được', icon: '🚫', tone: k.day_du ? 'danger' : 'warning', value: money(k.tong),
            rows: [...k.parts.map((p) => [p.label, partVal(p)]),
                ...(k.day_du ? [] : [['Lưu ý', '<span class="bc-txt-warning">tổng chưa đủ các phần</span>']])] })
            : na('Tồn không bán được', '🚫')}
        ${a.available ? statCard({ label: 'Tồn âm', icon: '➖', tone: 'warning',
            value: `<span class="${a.rows ? 'bc-txt-danger' : ''}">${fmtNum(a.rows)} dòng</span>`,
            rows: [['Giá trị phần âm', money(a.value_abs)], ['Mã / kho', `${fmtNum(a.items)} / ${fmtNum(a.warehouses)}`],
                ['Chưa có giá vốn', `${fmtNum(a.no_rate_rows)} dòng`]] })
            : na('Tồn âm', '➖')}
    </div>`;
}

// ─── Thành phẩm theo hạn dùng ────────────────────────────────────────────────
function barRow(icon, label, x, uom, cls, badge) {
    const w = Math.max(0, Math.min(100, Number(x.pct) || 0));
    return `<div class="bc-rank-row">
        <div class="bc-rank-no">${icon}</div>
        <div style="min-width:0">
            <div class="bc-rank-name">${badge ? `<span class="bc-badge ${badge}">${escapeHtml(label)}</span>` : escapeHtml(label)}</div>
            <div class="bc-rank-bars"><div class="bc-rank-bar"><div class="bc-progress ${cls}"><span style="width:${w}%"></span></div>
                <b>${x.pct === null || x.pct === undefined ? '—' : fmtPct(x.pct)}</b></div></div>
            <div class="bc-muted bc-text-sm">${qtyText(x, uom)}${x.lots ? ` · ${fmtNum(x.lots)} lô` : ''}</div>
        </div>
        <div class="bc-right"><b>${money(x.value)}</b></div>
    </div>`;
}

/** Phép cộng đối chiếu, từng đơn vị: nhóm hạn dùng (dương) + lô thu hồi − phần âm = tồn kho thành phẩm ngoài kho trả về & cách ly. */
function doiChieuHtml(h) {
    const dc = h.doi_chieu;
    const rows = dc.theo_dvt || [];
    if (!dc.khop) {
        const lech = rows.filter((x) => Math.abs(x.lech) > 0.001).map((x) => q1(x.lech, x.uom)).join(', ');
        return `<div class="bc-alert">Các phần chưa khớp tồn kho: lệch ${lech}. Báo bộ phận kho kiểm tra sổ lô.</div>`;
    }
    const eq = rows.map((x) => {
        let s = `${q1(x.duong, x.uom)} (các nhóm hạn dùng)`;
        if (x.thu_hoi) s += ` + ${q1(x.thu_hoi, x.uom)} lô đang thu hồi`;
        if (x.am) s += ` − ${q1(Math.abs(x.am), x.uom)} phần âm`;
        return `${s} = <b>${q1(x.ton_kho, x.uom)}</b>`;
    }).join('; ') || '0';
    return `<div class="bc-note" id="hd-doichieu">✔ <b>Khớp tồn kho</b>: ${eq} thành phẩm ngoài kho trả về & cách ly
        (giá trị theo sổ ${money(dc.ton_kho_value)}).</div>`;
}

function bucketsHtml(h) {
    if (!h.available) return off('tồn thành phẩm theo hạn dùng');
    const t = h.tong;
    if (!t.rows && !h.phan_am.rows && !h.thu_hoi.rows) {
        return emptyState({ icon: '📦', title: 'Không có tồn thành phẩm ngoài kho trả về & cách ly' });
    }
    const rows = h.buckets.map((b) => barRow(MUC[b.key][0], b.label, b, h.uom, MUC[b.key][1], MUC[b.key][2]));
    rows.push(barRow(MUC.chua_ro[0], 'Chưa rõ hạn dùng', h.chua_ro, h.uom, '', MUC.chua_ro[2]));
    const am = h.phan_am.rows ? `<div class="bc-note">Phần âm (sổ ghi xuất nhiều hơn nhập): ${qtyText(h.phan_am, h.uom)}, ${money(h.phan_am.value)}
        — xem mục Tồn âm.</div>` : '';
    const nr = noRateText(t);
    const noRate = nr ? `<div class="bc-note">${nr} chưa có giá vốn ở kho đang giữ — tính giá trị 0.</div>` : '';
    return `<div class="bc-rank-list">${rows.join('')}</div>
        <div class="bc-note">Cận date (còn 0–${fmtNum(h.can_date.ngay)} ngày): <b>${money(h.can_date.value)}</b> · ${qtyText(h.can_date, h.uom)}
            · ${fmtPct(h.can_date.pct)} giá trị thành phẩm. Tổng các nhóm hạn dùng (phần dương): ${qtyText(t, h.uom)}, ${money(t.value)}.</div>
        ${am}${noRate}${doiChieuHtml(h)}`;
}

function lotsHtml(h) {
    if (!h.available) return off('danh sách lô');
    const rows = h.lo_can_date || [];
    const more = h.lo_can_date_tong > rows.length ? `<div class="bc-note">Hiện ${fmtNum(rows.length)}/${fmtNum(h.lo_can_date_tong)} lô gần hạn nhất.</div>` : '';
    return `${dataTable({ rows, sortKey: 'con_ngay', sortDir: 'asc', emptyMessage: `Không có lô hết hạn hay còn ≤ ${h.can_date.ngay} ngày`,
        columns: [
            { key: 'short_name', label: 'Sản phẩm', align: 'left', render: itemCell },
            { key: 'con_ngay', label: 'Còn', render: (r) => conNgay(r.con_ngay) },
            { key: 'value', label: 'Giá trị ước tính', render: (r) => money(r.value) },
            { key: 'qty', label: 'Số lượng', render: (r) => `${qtyNum(r.qty)} <span class="bc-muted">${escapeHtml(r.uom || '')}</span>` },
            { key: 'cartons', label: 'Thùng', render: (r) => cartons(r.cartons, CT2) },
            { key: 'hsd', label: 'Hạn dùng', render: (r) => escapeHtml(fmtDate(r.hsd)) },
            { key: 'lo', label: 'Lô', align: 'left' },
            { key: 'kho', label: 'Kho', align: 'left' },
        ] })}${more}`;
}

function chuaRoHtml(h) {
    if (!h.available) return off('tồn chưa rõ hạn dùng');
    // Phần dương (các nhóm hạn dùng) rỗng thì không có gì để nói "đã rõ hạn" — không trấn an giả. "Không có tồn thành phẩm"
    // chỉ khi lô thu hồi và phần âm cũng rỗng (cùng điều kiện với khối hạn dùng ở trên); còn một trong hai thì dòng đối chiếu
    // ngay trên vẫn ghi số thành phẩm → nói rõ còn gì.
    if (!h.tong.rows) {
        if (!h.phan_am.rows && !h.thu_hoi.rows) return emptyState({ icon: '📦', title: 'Không có tồn thành phẩm' });
        const con = [
            h.thu_hoi.rows ? `lô đang thu hồi ${qtyText(h.thu_hoi, h.uom)} (xem Tồn không bán được)` : '',
            h.phan_am.rows ? `phần âm ${qtyText(h.phan_am, h.uom)} (sổ ghi xuất nhiều hơn nhập — xem Tồn âm)` : '',
        ].filter(Boolean);
        return `${emptyState({ icon: '📦', title: 'Không có thành phẩm cần xét hạn dùng' })}
            <div class="bc-note" id="hd-chuaro-con">Thành phẩm ngoài kho trả về & cách ly chỉ còn ${con.join(' và ')}.</div>`;
    }
    const cr = h.chua_ro;
    const parts = kpiGrid(cr.parts.map((p) => ({ label: p.label, value: money(p.value), sub: qtyText(p, h.uom) })), 4);
    const warn = cr.uoc_tinh_qua_han ? `<div class="bc-alert">${fmtNum(cr.uoc_tinh_qua_han)} lô chưa ghi hạn dùng mà hạn ước tính đã qua — cần kiểm tra bao bì và ghi hạn.</div>` : '';
    const more = h.chua_ro_ds_tong > (h.chua_ro_ds || []).length ? `<div class="bc-note">Hiện ${fmtNum(h.chua_ro_ds.length)}/${fmtNum(h.chua_ro_ds_tong)} dòng giá trị lớn nhất.</div>` : '';
    return `${warn}${parts}
        <div class="bc-mt-3">${dataTable({ rows: h.chua_ro_ds || [], sortKey: 'value', emptyMessage: 'Mọi thành phẩm đều đã rõ hạn dùng',
            columns: [
                { key: 'short_name', label: 'Sản phẩm', align: 'left', render: itemCell },
                { key: 'value', label: 'Giá trị ước tính', render: (r) => money(r.value) },
                { key: 'qty', label: 'Số lượng', render: (r) => `${qtyNum(r.qty)} <span class="bc-muted">${escapeHtml(r.uom || '')}</span>` },
                { key: 'loai', label: 'Loại', align: 'left', render: (r) => escapeHtml(PART_LABEL[r.loai] || r.loai) },
                { key: 'lo', label: 'Lô', align: 'left', render: (r) => (r.lo ? escapeHtml(r.lo) : '<span class="bc-muted">—</span>') },
                { key: 'kho', label: 'Kho', align: 'left' },
                { key: 'hsd_uoc_tinh', label: 'Hạn ước tính', render: (r) => (r.hsd_uoc_tinh ? escapeHtml(fmtDate(r.hsd_uoc_tinh)) : '<span class="bc-muted">—</span>') },
            ] })}</div>${more}
        <div class="bc-note">ⓘ Lô tồn cũ: hàng chưa có lô lúc chuyển sang quản lý theo lô. Hạn ước tính = ngày sản xuất (hoặc ngày tạo lô) + hạn dùng
            công bố — chỉ để tham khảo, không tính vào hết hạn hay cận date.</div>`;
}

// ─── Không bán được ──────────────────────────────────────────────────────────
function khongBanHtml(k) {
    if (!k.available) return off('tồn không bán được');
    const a = k.kho_loai, b = k.thu_hoi;
    const am = a.roles.filter((r) => r.am_rows);
    const head = kpiGrid([
        ...k.parts.map((p) => ({ label: p.label, value: partVal(p) })),
        { label: k.day_du ? 'Tổng' : 'Tổng (chưa đủ)', value: `<b>${money(k.tong)}</b>`, cls: k.tong ? 'bc-txt-danger' : '' },
    ], 2);
    const thieu = k.parts.filter((p) => !p.available);
    const chuaDu = thieu.length ? `<div class="bc-note">Tổng chưa gồm: ${thieu.map((p) => `${escapeHtml(p.label)} (${p.error ? 'chưa tính được' : 'chưa có dữ liệu'})`).join(', ')}.</div>` : '';
    const roles = a.roles.map((r) => `${escapeHtml(r.label)} ${money(r.value)} (${fmtNum(r.items)} mã)`).join(' · ');
    const dinhNghia = `<div class="bc-note" id="hd-kb-def">Tồn không bán được gồm 3 phần không trùng nhau: hàng đang nằm ở kho trả về
        & cách ly; lô đang thu hồi và thành phẩm đã hết hạn ở các kho còn lại (kể cả kho xưởng, bán thành phẩm, nguyên liệu).
        Phần đầu cùng số với thẻ "Kho trả về & cách ly" ở màn Tồn kho.</div>`;
    const thuHoi = b.available ? (b.ds && b.ds.length ? `<div class="bc-card-sub bc-mt-3">Lô đang thu hồi ngoài kho trả về & cách ly</div>
        ${dataTable({ rows: b.ds, sortKey: 'value', pageSize: 5,
            columns: [
                { key: 'short_name', label: 'Sản phẩm', align: 'left', render: itemCell },
                { key: 'value', label: 'Giá trị ước tính', render: (r) => money(r.value) },
                { key: 'qty', label: 'Số lượng', render: (r) => `${qtyNum(r.qty)} <span class="bc-muted">${escapeHtml(r.uom || '')}</span>` },
                { key: 'lo', label: 'Lô', align: 'left' },
                { key: 'kho', label: 'Kho', align: 'left' },
            ] })}` : '') : b.error ? off('lô đang thu hồi') : '<div class="bc-note">Hệ thống chưa có đánh dấu lô thu hồi — phần này chưa tính.</div>';
    return `${head}${chuaDu}${dinhNghia}
        <div class="bc-note">${roles}${am.length ? ` — đã trừ ${fmtNum(am.reduce((s, r) => s + r.am_rows, 0))} dòng âm (xem Tồn âm).` : ''}</div>
        <div class="bc-mt-3">${dataTable({ rows: a.ds, sortKey: 'value', pageSize: 8, emptyMessage: 'Không có hàng ở kho trả về / cách ly',
            columns: [
                { key: 'short_name', label: 'Sản phẩm', align: 'left', render: itemCell },
                { key: 'value', label: 'Giá trị', render: (r) => money(r.value) },
                { key: 'qty', label: 'Số lượng', render: (r) => `${qtyNum(r.qty)} <span class="bc-muted">${escapeHtml(r.uom || '')}</span>` },
                { key: 'kho', label: 'Kho', align: 'left' },
                { key: 'tuoi_ngay', label: 'Nằm kho', render: (r) => (r.tuoi_ngay === null || r.tuoi_ngay === undefined ? '—' : `${fmtNum(r.tuoi_ngay)} ngày`) },
            ] })}</div>
        ${thuHoi}`;
}

// ─── Tồn âm ──────────────────────────────────────────────────────────────────
function amHtml(a) {
    if (!a.available) return off('tồn âm');
    if (!a.rows && !a.lo.lo_am && !a.lo.khong_lo) {
        return emptyState({ icon: '✅', title: 'Không có tồn âm' });
    }
    const flags = [];
    if (a.cho_phep_am?.kho) flags.push('Hệ thống đang cho phép xuất kho âm.');
    if (a.cho_phep_am?.lo) flags.push('Hệ thống đang cho phép xuất lô âm.');
    return `${kpiGrid([
        { label: 'Dòng âm', value: fmtNum(a.rows), cls: a.rows ? 'bc-txt-danger' : '' },
        { label: 'Giá trị phần âm', value: money(a.value_abs) },
        { label: 'Chưa có giá vốn', value: fmtNum(a.no_rate_rows), sub: 'dòng' },
    ], 3)}
        <div class="bc-mt-3">${dataTable({ rows: a.split, scrollButtons: false,
            columns: [
                { key: 'label', label: 'Nhóm', align: 'left', sortable: false },
                { key: 'value_abs', label: 'Giá trị', sortable: false, render: (r) => money(r.value_abs) },
                { key: 'rows', label: 'Dòng', sortable: false, render: (r) => fmtNum(r.rows) },
                { key: 'items', label: 'Mã', sortable: false, render: (r) => fmtNum(r.items) },
            ] })}</div>
        <div class="bc-mt-3">${dataTable({ rows: a.ds, sortKey: 'value_abs', pageSize: 8, emptyMessage: 'Không có dòng âm',
            columns: [
                { key: 'short_name', label: 'Sản phẩm', align: 'left', render: itemCell },
                { key: 'value_abs', label: 'Giá trị', render: (r) => (r.co_gia_von ? money(r.value_abs) : '<span class="bc-badge bc-badge-muted">chưa có giá vốn</span>') },
                { key: 'qty', label: 'Số lượng', render: (r) => `<span class="bc-txt-danger">${qtyNum(r.qty)}</span> <span class="bc-muted">${escapeHtml(r.uom || '')}</span>` },
                { key: 'kho', label: 'Kho', align: 'left' },
            ] })}</div>
        <div class="bc-note">Theo lô (thành phẩm): ${fmtNum(a.lo.lo_am)} lô âm; ${fmtNum(a.lo.khong_lo)} chỗ còn tồn chưa gắn lô
            (${fmtNum(a.lo.khong_lo_duong)} dư, ${fmtNum(a.lo.khong_lo_am)} thiếu) — nên về 0 sau khi bộ phận kho dọn tồn.
            ${flags.map(escapeHtml).join(' ')}</div>
        <div class="bc-note">ⓘ Cửa hàng hay âm tạm do bán trước khi chốt ca. Giá trị phần âm = số lượng âm × giá vốn gần nhất của mã.</div>`;
}

async function load(isCurrent) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    try {
        const d = await api.kho.han();
        if (!alive()) return;
        if (!d.available) {
            fill('hd-kpis', emptyState({ icon: '📦', title: 'Chưa có số liệu kho', message: d.reason || '' }));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        const lo = d.meta.lo_luc && d.meta.lo_ttl_giay ? ` Số theo lô (hạn dùng, lô thu hồi, lô âm) tính lúc ${hhmm(d.meta.lo_luc)}
            — tự tính lại sau mỗi giờ, bấm Làm mới để tính ngay.` : '';
        fill('hd-asof', `Tồn đến hôm nay ${escapeHtml(fmtDate(d.meta.as_of))} (gồm phiếu ghi ngày sau). Cận date = còn 0–${fmtNum(d.meta.can_date_ngay)} ngày.${lo}`);
        fill('hd-kpis', kpisHtml(d));
        fill('hd-buckets', bucketsHtml(d.han));
        fill('hd-lots', lotsHtml(d.han));
        fill('hd-chuaro', chuaRoHtml(d.han));
        fill('hd-khongban', khongBanHtml(d.khong_ban));
        fill('hd-am', amHtml(d.am));
    } catch (err) {
        if (!alive()) return;
        fill('hd-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Hạn dùng & tồn âm</div>
                <div class="bc-view-banner-sub">Thành phẩm theo hạn dùng, hàng không bán được và tồn âm</div></div>
            <span class="bc-view-banner-badge">⏳ Kho</span>
        </div>
        <div class="bc-note" id="hd-asof"></div>
        <div id="hd-kpis">${skeletonGrid(5, 128, 'bc-grid-5')}</div>
        <div class="bc-section-title">Thành phẩm theo hạn dùng (ngoài kho trả về & cách ly)</div>
        <div class="bc-card"><div id="hd-buckets">${skeleton(240)}</div></div>
        <div class="bc-section-title">Lô hết hạn và cận date</div>
        <div class="bc-card"><div id="hd-lots">${skeleton(200)}</div></div>
        <div class="bc-section-title">Chưa rõ hạn dùng</div>
        <div class="bc-card"><div id="hd-chuaro">${skeleton(200)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Tồn không bán được</div></div><div id="hd-khongban">${skeleton(200)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Tồn âm</div></div><div id="hd-am">${skeleton(200)}</div></div>
        </div>
        <div class="bc-note bc-mt-3">ⓘ Giá trị theo giá vốn, chưa VAT. Giá trị theo lô là ước tính (số lượng × giá vốn bình quân của mã tại kho).
            Hạn dùng, lô thu hồi, hàng hết hạn tính ở mọi kho ngoài kho trả về & cách ly — gồm cả kho xưởng, bán thành phẩm,
            nguyên liệu, không chỉ kho đang bán. Lô hết hạn đúng hôm nay vẫn tính là còn hạn.</div>`;
    await load(isCurrent);
}
