// #/kiem-ke — Kiểm kê & điều chỉnh: lần kiểm kê gần nhất từng kho + phiếu đang đếm (tình hình HÔM NAY), độ chính xác tồn
// (lần kiểm gần nhất tính đến cuối tháng chọn), chênh lệch kiểm kê (sản xuất — gồm phần ở kho khác khi bật lô — và phiếu
// kiểm kho ở cửa hàng & kho khác), dọn tồn, xuất huỷ / xuất khác trong tháng. Một lượt gọi
// bc.api.kho_kk.get_overview(thang); khối nào thiếu số (site chưa cài app Sản xuất…) thì báo riêng khối đó.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, fmtPct } from '../lib/format.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const state = { thang: '' };  // CHỈ tháng người xem đã chọn và tải được — trống = tháng hiện tại
let seq = 0;  // lượt tải mới nhất — đổi tháng nhanh thì lượt cũ về sau không đè lượt mới
const SECTIONS = ['kk-kpis', 'kk-kho', 'kk-dang', 'kk-ira', 'kk-dc', 'kk-sx', 'kk-ch', 'kk-xk', 'kk-don', 'kk-top', 'kk-ve0'];

const muted = '<span class="bc-muted">—</span>';
function money(v) { return v === null || v === undefined ? muted : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
/** Tiền có dấu: âm đỏ (mất / thiếu), dương xanh (thừa). */
function signed(v) {
    if (v === null || v === undefined) return muted;
    const cls = v < 0 ? 'bc-txt-danger' : v > 0 ? 'bc-txt-success' : '';
    return `<span class="${cls}" title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`;
}
function num(v, digits = 0) {
    if (v === null || v === undefined) return '—';
    return digits ? (Math.round(v * 10 ** digits) / 10 ** digits).toLocaleString('vi-VN') : fmtNum(v);
}
function note(text) { return `<div class="bc-muted bc-text-sm">${escapeHtml(text)}</div>`; }
/** Dòng phụ trong ô bảng: XUỐNG DÒNG được (ô đầu bảng hẹp, cắt chữ thì mất số — "60k" thành "60") + title đủ chữ.
 *  min-width giữ cột đầu đủ rộng (không co về một từ khi các cột số chiếm hết chỗ trên điện thoại).
 *  `text` là chữ thô (escape ở đây). */
function sub(text) {
    return `<div class="bc-muted bc-text-sm" style="white-space:normal;min-width:min(38vw,9rem)" title="${escapeHtml(text)}">${escapeHtml(text)}</div>`;
}
/** Nhãn ô đầu bảng xuống dòng được (`html` đã escape). */
function wrap(html) { return `<span style="white-space:normal">${html}</span>`; }
/** Khối không có số: lỗi riêng khối / chưa cài app Sản xuất / thiếu dữ liệu nguồn. `as` = cách hiện câu: note (cả khối) hoặc
 *  sub (trong ô đầu bảng — ô đó nowrap + cắt chữ, câu giải thích phải xuống dòng, không cụt trên điện thoại). */
function off(b, what, as = note) {
    if (b && b.error) return as(`Không tải được ${what}.`);
    if (b?.reason === 'khong_sx' && what === 'số') return as('Không áp dụng: site chưa cài app Sản xuất.');
    const why = { khong_sx: 'site chưa cài app Sản xuất', thieu_cot: 'phiếu kho chưa ghi liên kết với lần kiểm kê',
        thieu_bang: 'hệ thống chưa có phiếu kiểm kho', khong_nguon: 'chưa có số kiểm kê' }[b?.reason] || 'chưa có số liệu';
    return as(`Chưa có ${what}: ${why}.`);
}

function monthOptions(cur) {
    const now = new Date();
    let y = now.getFullYear(), m = now.getMonth() + 1;
    const months = [];
    for (let i = 0; i < 12; i++) {
        months.push(`${y}-${String(m).padStart(2, '0')}`);
        m -= 1; if (!m) { m = 12; y -= 1; }
    }
    if (cur && !months.includes(cur)) months.unshift(cur);
    return `<select class="bc-input" id="kk-thang" aria-label="Tháng">${months.map((x) =>
        `<option value="${escapeHtml(x)}" ${x === cur ? 'selected' : ''}>Tháng ${escapeHtml(x.slice(5))}/${escapeHtml(x.slice(0, 4))}</option>`).join('')}</select>`;
}

const LOAI_TXT = { 'Thành phẩm': 'Thành phẩm', 'Bán thành phẩm': 'Bán thành phẩm' };

function dayBadge(r) {
    if (r.muc === 'chua') return '<span class="bc-badge bc-badge-danger">Chưa kiểm kê</span>';
    const cls = r.muc === 'nguy' ? 'bc-badge-danger' : r.muc === 'canh_bao' ? 'bc-badge-warning' : 'bc-badge-success';
    return `<span class="bc-badge ${cls}">${fmtNum(r.so_ngay)} ngày</span>`;
}

// ─── Thẻ số ──────────────────────────────────────────────────────────────────
/** Nhãn các khoản của tổng còn THIẾU số thật (lỗi / thiếu cột…) — khoản "không áp dụng" (site không có app Sản xuất)
 *  không tính là thiếu. */
function thieuLabels(t) {
    const miss = new Set(t.thieu || []);
    return (t.parts || []).filter((p) => !p.available && miss.has(p.key)).map((p) => p.label);
}

function kpisHtml(d) {
    const t = d.tong, s = d.kk_sx, ch = d.kk_ch, x = d.xuat_khac, ira = d.ira;
    const parts = Object.fromEntries((t.parts || []).map((p) => [p.key, p.gia_tri]));
    const sum = (...v) => (v.every((a) => a === null || a === undefined) ? null : v.reduce((a, b) => a + (b || 0), 0));
    const thieu = t.available ? thieuLabels(t) : [];
    // Thiếu một khoản thì KHÔNG đưa một con số như thể đủ: giá trị "—", số các khoản đã có + tên đúng khoản còn thiếu
    // (nhãn ở ô trái của dòng — xuống dòng được, không bị cắt trên điện thoại).
    const tong = !t.available
        ? statCard({ label: 'Tổng điều chỉnh trong tháng', icon: '⚖️', value: '—', rows: [['', 'Chưa có số']] })
        : thieu.length
            ? statCard({ label: 'Tổng điều chỉnh trong tháng', icon: '⚖️', tone: 'warning', value: muted,
                rows: [['Các khoản đã có', signed(t.gia_tri)], [`Chưa gồm: ${thieu.join('; ')}`, '']] })
            : statCard({ label: 'Tổng điều chỉnh trong tháng', icon: '⚖️', tone: t.gia_tri < 0 ? 'danger' : 'success',
                value: signed(t.gia_tri), rows: [['Kiểm kê', signed(sum(parts.kk_sx, parts.kk_ch))],
                    ['Dọn tồn, xuất huỷ', signed(sum(parts.don_sx, parts.xuat_khac))]] });
    return `<div class="bc-grid bc-grid-5">
        ${tong}
        ${s.available ? statCard({ label: 'Kiểm kê sản xuất', icon: '🏭', tone: s.gt_rong < 0 ? 'danger' : '',
            value: signed(s.gt_rong), rows: [['Thừa', signed(s.gt_thua)], ['Thiếu', signed(s.gt_thieu)],
                ...(s.gt_kho_khac ? [['Ở kho khác khi bật lô', signed(s.gt_kho_khac)]] : []), ['Số lần kiểm', fmtNum(s.so_lan)]] })
            : statCard({ label: 'Kiểm kê sản xuất', icon: '🏭', value: '—', rows: [['', s.reason === 'khong_sx' ? 'Chưa cài app Sản xuất' : 'Chưa có số']] })}
        ${ch.available ? statCard({ label: 'Phiếu kiểm kho (cửa hàng & kho khác)', icon: '🏪', tone: ch.gt_rong < 0 ? 'warning' : '',
            value: signed(ch.gt_rong), rows: [['Cửa hàng', signed(ch.cua_hang?.gt_rong)], ['Kho khác', signed(ch.kho_khac?.gt_rong)],
                ['Số phiếu', fmtNum(ch.so_phieu)]] })
            : statCard({ label: 'Phiếu kiểm kho (cửa hàng & kho khác)', icon: '🏪', value: '—', rows: [['', 'Chưa có số']] })}
        ${x.available ? statCard({ label: 'Xuất huỷ, xuất mẫu, xuất khác', icon: '🗑️', tone: x.gia_tri ? 'warning' : '',
            value: money(x.gia_tri), rows: [['Số phiếu', fmtNum(x.so_phieu)],
                ...(x.rows.length ? [[x.rows[0].label, money(x.rows[0].gia_tri)]] : [])] })
            : statCard({ label: 'Xuất huỷ, xuất mẫu, xuất khác', icon: '🗑️', value: '—', rows: [['', 'Chưa có số']] })}
        ${ira.available ? statCard({ label: 'Độ chính xác tồn', icon: '🎯', tone: ira.ty_le !== null && ira.ty_le < 80 ? 'warning' : 'success',
            value: fmtPct(ira.ty_le), rows: [['Mã khớp sổ', `${fmtNum(ira.so_ma_khop)}/${fmtNum(ira.so_ma)}`],
                ['Lần kiểm mới nhất', ira.ngay_moi_nhat ? escapeHtml(fmtDate(ira.ngay_moi_nhat)) : '—'], ['Kho Sản xuất', fmtNum(ira.rows.length)]] })
            : statCard({ label: 'Độ chính xác tồn', icon: '🎯', value: '—', rows: [['', ira.reason === 'khong_sx' ? 'Chưa cài app Sản xuất' : 'Chưa có số']] })}
    </div>`;
}

// ─── K9. Kiểm kê gần nhất theo kho ──────────────────────────────────────────
function khoHtml(k, ira, nguong, asOf) {
    if (!k.available) return off(k, 'bảng kiểm kê theo kho');
    // Cột độ chính xác: lần kiểm gần nhất HÔM NAY của từng kho (bảng này luôn là hôm nay, kể cả khi chọn tháng cũ).
    const now = (ira.available && ira.ty_le_hien_tai) || {};
    const acc = (r) => (r.phieu && Object.prototype.hasOwnProperty.call(now, r.phieu) ? fmtPct(now[r.phieu]) : muted);
    const t = k.tong;
    return `<div class="bc-muted bc-text-sm" style="margin-bottom:.5rem" id="kk-kho-asof">Tình hình hiện tại, đến hôm nay
            ${escapeHtml(fmtDate(asOf))} — không đổi theo tháng chọn (trừ cột "Lần trong tháng").</div>
        ${kpiGrid([
        { label: 'Kho cần kiểm', value: fmtNum(t.so_kho) },
        { label: 'Chưa kiểm kê lần nào', value: fmtNum(t.chua_kiem), cls: t.chua_kiem ? 'bc-txt-danger' : '' },
        { label: `Quá ${fmtNum(nguong.canh_bao)} ngày chưa kiểm`, value: fmtNum(t.qua_30), cls: t.qua_30 ? 'bc-txt-warning' : '' },
        { label: `Quá ${fmtNum(nguong.nguy)} ngày chưa kiểm`, value: fmtNum(t.qua_90), cls: t.qua_90 ? 'bc-txt-danger' : '' },
    ], 4)}
        <div class="bc-mt-3">${dataTable({ rows: k.rows, pageSize: 12, emptyMessage: 'Không có kho nào đang giữ hàng',
            columns: [
                { key: 'label', label: 'Kho', align: 'left', render: (r) => `${wrap(escapeHtml(r.label))}${r.disabled ? ' <span class="bc-badge bc-badge-muted">ngừng dùng</span>' : ''}
                    ${sub(`${r.role_label}${r.loai ? ` · ${LOAI_TXT[r.loai] || r.loai}` : ''}`)}` },
                { key: 'so_ngay', label: 'Cách đây', sortValue: (r) => (r.so_ngay === null ? 1e9 : r.so_ngay), render: dayBadge },
                { key: 'ngay', label: 'Ngày kiểm', render: (r) => (r.ngay ? escapeHtml(fmtDate(r.ngay)) : muted) },
                { key: 'nguon', label: 'Cách kiểm', align: 'left', sortable: false, render: cachKiem },
                { key: 'so_lan_trong_ky', label: 'Lần trong tháng', render: (r) => fmtNum(r.so_lan_trong_ky) },
                { key: 'ira', label: 'Độ chính xác', sortable: false, render: acc },
                { key: 'dang_dem', label: 'Đang đếm', sortable: false,
                    render: (r) => (r.dang_dem ? '<span class="bc-badge bc-badge-primary">Đang đếm</span>' : '') },
            ] })}</div>
        <div class="bc-note">Kho cần kiểm = kho thành phẩm, bán thành phẩm, xưởng của Sản xuất và mọi kho bán được đang có hàng.
            Màu: quá ${fmtNum(nguong.canh_bao)} ngày vàng, quá ${fmtNum(nguong.nguy)} ngày đỏ. Kho Sản xuất tính theo lần kiểm đã chốt
            (ngày chốt sổ nếu kiểm lùi ngày), hoặc phiếu kiểm kho nếu phiếu đó mới hơn; cửa hàng tính theo phiếu kiểm kho đã duyệt
            (không tính phiếu tồn đầu kỳ).</div>`;
}

/** Cột "Cách kiểm" của bảng kho: nguồn của NGÀY đang hiện (kho Sản xuất có thể được kiểm bằng phiếu kiểm kho mới hơn). */
function cachKiem(r) {
    const sub = (t) => `<div class="bc-muted bc-text-sm">${escapeHtml(t)}</div>`;
    if (r.nguon === 'sx' && r.nguon_ngay === 'sr') {
        return `Phiếu kiểm kho${sub(r.ngay_sx ? `Sản xuất đếm lần cuối ${fmtDate(r.ngay_sx)}` : 'Sản xuất chưa đếm lần nào')}`;
    }
    if (r.nguon === 'sx') return `Sản xuất đếm${r.cach_dem ? sub(r.cach_dem) : ''}`;
    return 'Phiếu kiểm kho';
}

function dangHtml(dd, hc) {
    if (!dd.available) return off(dd, 'phiếu đang đếm');
    const huy = hc.available ? (hc.so_phieu
        ? `<div class="bc-alert bc-mt-3">Trong tháng có ${fmtNum(hc.so_phieu)} lần kiểm đã chốt bị huỷ${hc.so_mo_lai
            ? ` (${fmtNum(hc.so_mo_lai)} lần huỷ chốt để đếm lại)` : ''}: ${hc.rows.map((r) => `${escapeHtml(r.phieu)} · ${escapeHtml(r.label)}
            ${escapeHtml(fmtDate(r.ngay))}`).join('; ')}.</div>`
        : '<div class="bc-note">Không có lần kiểm nào bị huỷ chốt trong tháng.</div>') : '';
    return `${dataTable({ rows: dd.rows, emptyMessage: 'Không có phiếu nào đang đếm', scrollButtons: false,
        columns: [
            { key: 'phieu', label: 'Phiếu', align: 'left', sortable: false,
                render: (r) => `${escapeHtml(r.phieu)}${sub(`${r.label} · ${LOAI_TXT[r.loai] || r.loai || ''}`)}` },
            { key: 'tuoi', label: 'Mở từ', sortable: false,
                render: (r) => `<span class="bc-badge ${r.cu ? 'bc-badge-warning' : 'bc-badge-muted'}">${fmtNum(r.tuoi)} ngày</span>
                    <div class="bc-muted bc-text-sm">${escapeHtml(fmtDate(r.bat_dau))}</div>` },
            { key: 'so_ma', label: 'Đã đếm', sortable: false, render: (r) => `${fmtNum(r.so_ma)} mã · ${fmtNum(r.so_dong)} dòng
                <div class="bc-muted bc-text-sm">${r.im_lang ? `${fmtNum(r.im_lang)} ngày chưa đếm thêm` : 'đếm hôm nay'}</div>` },
        ] })}
        ${dd.cu ? `<div class="bc-note">${fmtNum(dd.cu)} phiếu mở từ 2 ngày trở lên: kho vẫn bán / xuất trong lúc đếm, chốt sẽ bị chặn
            vì có chứng từ sau giờ đếm.</div>` : ''}${huy}`;
}

function iraHtml(ira) {
    if (!ira.available) return off(ira, 'độ chính xác tồn');
    if (!ira.rows.length) return emptyState({ icon: '🎯', title: `Chưa có lần kiểm Sản xuất nào đã chốt đến ${fmtDate(ira.den_ngay)}` });
    return `<div class="bc-rank-list" id="kk-ira-list">${ira.rows.map((r, i) => `<div class="bc-rank-row">
            <div class="bc-rank-no">${i + 1}</div>
            <div style="min-width:0">
                <div class="bc-rank-name">${escapeHtml(r.label)} · ${escapeHtml(LOAI_TXT[r.loai] || r.loai)}</div>
                <div class="bc-rank-bars"><div class="bc-rank-bar"><div class="bc-progress ${r.ty_le !== null && r.ty_le >= 80 ? 'bc-ok' : 'bc-alt'}">
                    <span style="width:${Math.max(0, Math.min(100, r.ty_le || 0))}%"></span></div><b>${fmtPct(r.ty_le)}</b></div></div>
                <div class="bc-muted bc-text-sm">${escapeHtml(r.phieu)} · ${escapeHtml(fmtDate(r.ngay))} · ${fmtNum(r.so_ma_khop)}/${fmtNum(r.so_ma)} mã khớp</div>
            </div>
            <div class="bc-right"></div></div>`).join('')}</div>
        <div class="bc-note">Lần kiểm Sản xuất gần nhất của từng kho tính đến ${escapeHtml(fmtDate(ira.den_ngay))} (cuối tháng chọn).
            Mã khớp = số đếm bằng số sổ của mã đó (cộng mọi lô). Không tính lô đang thu hồi.</div>`;
}

// ─── K10. Điều chỉnh trong tháng ────────────────────────────────────────────
function dcHtml(d) {
    const t = d.tong;
    if (!t.available) return off(t, 'tổng điều chỉnh');
    const detail = {
        kk_sx: (b) => `Thừa ${fmtMoney(b.gt_thua)} · thiếu ${fmtMoney(b.gt_thieu)}${b.gt_kho_khac
            ? ` · ở kho khác khi bật lô ${fmtMoney(b.gt_kho_khac)}` : ''} · ${fmtNum(b.so_lan)} lần kiểm`,
        kk_ch: (b) => `Cửa hàng ${fmtMoney(b.cua_hang?.gt_rong)} · kho khác ${fmtMoney(b.kho_khac?.gt_rong)} · ${fmtNum(b.so_phieu)} phiếu`,
        don_sx: (b) => `${fmtNum(b.so_phieu)} phiếu`,
        xuat_khac: (b) => `${fmtNum(b.so_phieu)} phiếu`,
    };
    const rows = t.parts.map((p) => ({ ...p, detail: p.available ? detail[p.key](d[p.key]) : null, why: d[p.key] }));
    const thieu = thieuLabels(t);
    return `${dataTable({ rows, scrollButtons: false,
        totalRow: { label: `<b>Tổng điều chỉnh</b>${thieu.length ? sub(`chưa gồm: ${thieu.join('; ')}`) : ''}`,
            gia_tri: `<b>${signed(t.gia_tri)}</b>` },
        columns: [
            { key: 'label', label: 'Khoản', align: 'left', sortable: false,
                render: (r) => `${wrap(escapeHtml(r.label))}${r.available ? sub(r.detail)
                    : off({ ...(r.why || {}), reason: r.reason || r.why?.reason }, 'số', sub)}` },
            { key: 'gia_tri', label: 'Giá trị', sortable: false, render: (r) => (r.available ? signed(r.gia_tri) : muted) },
        ] })}
        <div class="bc-note">Tăng (+) là hàng nhiều hơn sổ, giảm (−) là hàng mất / thiếu / huỷ. Tổng = kiểm kê sản xuất + phiếu kiểm kho
            + dọn tồn − xuất huỷ / xuất khác. Kiểm kê sản xuất tính vào tháng của ngày chốt sổ, gồm phần bù chứng từ ghi lùi
            sau kiểm kê và phần ở kho khác khi lần kiểm bật quản lý lô (bù tồn âm về 0), nên khớp dòng "Kiểm kê sản xuất" của
            trang Tồn kho trừ phiếu ghi sổ khác tháng; các khoản khác theo ngày phiếu.</div>`;
}

function sxHtml(s) {
    if (!s.available) return off(s, 'kiểm kê sản xuất');
    const warn = [];
    if (s.phieu_huy_le?.so_phieu) {
        warn.push(`Hiện có ${fmtNum(s.phieu_huy_le.so_phieu)} phiếu kho của ${fmtNum(s.phieu_huy_le.so_kiem_ke)} lần kiểm đã chốt bị huỷ riêng (lần kiểm vẫn chốt, tính mọi tháng) — cần xem lại.`);
    }
    if (s.so_ma_gia_0) warn.push(`${fmtNum(s.so_ma_gia_0)} mã lệch số lượng nhưng chưa có giá vốn (không thành tiền).`);
    // Số lượng, quy ra thùng, rồi phần hộp của mã chưa khai quy cách thùng (thùng chỉ quy được phần còn lại) — mỗi ý một dòng
    // ngắn để cột không phình trên điện thoại.
    const q = (x) => {
        if (!x) return '';
        const line = (t) => `<div class="bc-muted bc-text-sm">${t}</div>`;
        const uom = escapeHtml(x.uom || '');
        return `${line(`${num(x.qty, 1)} ${uom}`)}${x.cartons ? line(`${num(x.cartons, 1)} thùng`) : ''}${x.boxes_without_carton_factor
            ? line(`+${num(x.boxes_without_carton_factor, 1)} ${uom} chưa khai thùng`) : ''}`;
    };
    return `${dataTable({ rows: s.rows, emptyMessage: 'Không có lần kiểm Sản xuất nào trong tháng', scrollButtons: false,
        columns: [
            { key: 'phieu', label: 'Lần kiểm', align: 'left', sortable: false,
                render: (r) => `${escapeHtml(r.phieu)}${sub(`${r.label} · ${fmtDate(r.ngay)}`)}${r.gt_bu
                    ? sub(`gồm bù sau kiểm kê ${fmtMoney(r.gt_bu)}`) : ''}${r.gt_chenh_gia
                    ? sub(`chênh giá ${fmtMoney(r.gt_chenh_gia)}`) : ''}${r.gt_kho_khac || r.kho_khac?.length
                    ? sub(`ở kho khác khi bật lô ${fmtMoney(r.gt_kho_khac)}${r.kho_khac?.length
                        ? `: ${r.kho_khac.map((w) => `${w.label} ${fmtMoney(w.gia_tri)}`).join(' · ')}` : ''}`) : ''}` },
            { key: 'gt_thua', label: 'Thừa', sortable: false, render: (r) => `${signed(r.gt_thua)}${q(r.thua)}` },
            { key: 'gt_thieu', label: 'Thiếu', sortable: false, render: (r) => `${signed(r.gt_thieu)}${q(r.thieu)}` },
            { key: 'gt_rong', label: 'Ròng', sortable: false, render: (r) => `<b>${signed(r.gt_rong)}</b>` },
        ] })}
        ${warn.length ? `<div class="bc-alert bc-mt-3">${warn.map(escapeHtml).join('<br>')}</div>` : ''}
        ${s.gt_kho_khac ? `<div class="bc-note">Thừa / thiếu là số đếm tại kho được kiểm. "Ở kho khác khi bật lô": lần kiểm chuyển mã sang
            quản lý lô thì Sản xuất đưa tồn chưa có lô ở cửa hàng / xưởng vào lô (gần như không đổi giá trị) và nhập bù kho đang âm
            về 0 — phần này làm đổi giá trị kho thật nên tính trong Ròng (${escapeHtml(fmtMoney(s.gt_kho_khac))}).</div>` : ''}`;
}

function chHtml(ch) {
    if (!ch.available) return off(ch, 'số liệu phiếu kiểm kho');  // khối gồm mọi kho (UX-1) — không gọi là "kiểm kê cửa hàng"
    return `${dataTable({ rows: ch.rows, emptyMessage: 'Không có phiếu kiểm kho nào trong tháng', scrollButtons: false,
        columns: [
            { key: 'label', label: 'Kho', align: 'left', sortable: false,
                render: (r) => `${wrap(escapeHtml(r.label))}${sub(`${r.role_label} · ${fmtNum(r.so_phieu)} phiếu`)}${r.gt_doi_gia
                    ? sub(`đổi giá ${fmtMoney(r.gt_doi_gia)}`) : ''}` },
            { key: 'gt_thua', label: 'Thừa', sortable: false, render: (r) => signed(r.gt_thua) },
            { key: 'gt_thieu', label: 'Thiếu', sortable: false, render: (r) => signed(r.gt_thieu) },
            { key: 'gt_rong', label: 'Ròng', sortable: false, render: (r) => `<b>${signed(r.gt_rong)}</b>` },
        ] })}
        ${ch.cua_hang && ch.kho_khac ? `<div class="bc-note" id="kk-ch-tach">Cửa hàng ${signed(ch.cua_hang.gt_rong)} (${fmtNum(ch.cua_hang.so_kho)} kho)
            · kho khác ${signed(ch.kho_khac.gt_rong)} (${fmtNum(ch.kho_khac.so_kho)} kho: kho thành phẩm, trả về…).</div>` : ''}
        ${ch.so_dong_doi_gia ? `<div class="bc-note">${fmtNum(ch.so_dong_doi_gia)} dòng kiểm chỉ đổi giá vốn, không lệch số lượng.</div>` : ''}`;
}

function xkHtml(x) {
    if (!x.available) return off(x, 'xuất khác');
    return `${dataTable({ rows: x.rows, emptyMessage: 'Không có phiếu xuất huỷ / xuất khác trong tháng', scrollButtons: false,
        totalRow: x.rows.length > 1 ? { label: '<b>Tổng</b>', gia_tri: `<b>${money(x.gia_tri)}</b>`, so_phieu: `<b>${fmtNum(x.so_phieu)}</b>` } : null,
        columns: [
            { key: 'label', label: 'Loại phiếu', align: 'left', sortable: false,
                render: (r) => `${wrap(escapeHtml(r.label))}${sub(r.kho.map((w) => `${w.label} ${fmtMoney(w.gia_tri)}`).join(' · '))}` },
            { key: 'so_phieu', label: 'Phiếu', sortable: false, render: (r) => fmtNum(r.so_phieu) },
            { key: 'gia_tri', label: 'Giá trị', sortable: false, render: (r) => money(r.gia_tri) },
        ] })}
        <div class="bc-note">Phiếu xuất kho không phải bán hàng, kiểm kê, dọn tồn hay xuất nguyên liệu bù nợ BOM (đó là tiêu hao sản xuất).</div>`;
}

function donHtml(dn) {
    if (!dn.available) return off(dn, 'dọn tồn của sản xuất');
    const rows = dn.rows.filter((r) => r.hien && r.so_phieu);
    return `${dataTable({ rows, emptyMessage: 'Không có phiếu dọn tồn trong tháng', scrollButtons: false,
        columns: [
            { key: 'label', label: 'Loại dọn tồn', align: 'left', sortable: false, render: (r) => wrap(escapeHtml(r.label)) },
            { key: 'so_phieu', label: 'Phiếu', sortable: false, render: (r) => fmtNum(r.so_phieu) },
            { key: 'gia_tri', label: 'Giá trị', sortable: false, render: (r) => signed(r.gia_tri) },
        ] })}
        <div class="bc-note">Sản xuất tự điều chỉnh ngoài lần kiểm: đưa tồn âm thành phẩm về 0, dọn phần tồn chưa gắn lô sau khi bật
            quản lý lô. Tổng ${signed(dn.gia_tri)}.</div>`;
}

function topHtml(tl) {
    if (!tl.available) return off(tl, 'danh sách mã chênh lệch');
    return `${dataTable({ rows: tl.rows, emptyMessage: 'Không có mã nào lệch số lượng trong tháng',
        columns: [
            { key: 'short_name', label: 'Mã hàng · kho', align: 'left', sortable: false,
                render: (r) => `${wrap(escapeHtml(r.short_name))}${sub(`${r.item_code} · ${r.kho_label}`)}
                    <div class="bc-text-sm"><span class="bc-badge ${r.nguon === 'sx' ? 'bc-badge-primary' : 'bc-badge-muted'}">${r.nguon === 'sx' ? 'Sản xuất đếm' : 'Phiếu kiểm kho'}</span></div>` },
            { key: 'qty', label: 'Lệch', sortable: false,
                render: (r) => `${num(r.qty, 3)} ${escapeHtml(r.uom || '')}${r.cartons !== null && r.cartons !== undefined ? `<div class="bc-muted bc-text-sm">${num(r.cartons, 2)} thùng</div>` : ''}` },
            { key: 'value', label: 'Giá trị', sortable: false,
                render: (r) => (r.gia_0 ? `${signed(r.value)}<div class="bc-text-sm bc-txt-warning">chưa có giá vốn</div>` : signed(r.value)) },
        ] })}`;
}

function ve0Html(v) {
    if (!v.available) return off(v, 'mã về 0 vì không đếm');
    if (!v.so_ma) return '<div class="bc-note">Không có mã nào bị đưa về 0 vì không được đếm trong các lần kiểm của tháng.</div>';
    return `<div class="bc-alert">${fmtNum(v.so_ma)} mã thành phẩm còn trên sổ nhưng không được đếm nên bị đưa về 0 khi chốt
            ${v.gia_tri !== null ? `(${escapeHtml(fmtMoney(v.gia_tri))})` : ''} — cần kiểm tra lại có thật hết hàng không.</div>
        ${dataTable({ rows: v.rows, emptyMessage: 'Các mã này đang được ẩn khỏi danh sách', scrollButtons: false,
            columns: [
                { key: 'short_name', label: 'Mã hàng', align: 'left', sortable: false,
                    render: (r) => `${wrap(escapeHtml(r.short_name))}${sub(`${r.item_code} · ${r.phieu}`)}` },
                { key: 'so_luong', label: 'Sổ trước chốt', sortable: false, render: (r) => `${num(r.so_luong, 3)} ${escapeHtml(r.uom || '')}` },
                { key: 'gia_tri', label: 'Giá trị', sortable: false, render: (r) => signed(r.gia_tri) },
            ] })}`;
}

/** Ô chọn tháng. Dựng lại sau mỗi lượt tải: trả focus về ô nếu người dùng đang ở đó. */
function bindPicker(cur, extra, isCurrent) {
    const refocus = document.activeElement?.id === 'kk-thang';
    fill('kk-filter', `${monthOptions(cur)}${extra}`);
    const sel = document.getElementById('kk-thang');
    sel?.addEventListener('change', (e) => {
        SECTIONS.forEach((id) => fill(id, skeleton(120)));
        load(isCurrent, e.target.value, true);
    });
    if (refocus) sel?.focus();
}

async function load(isCurrent, thang = state.thang, chon = false) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    try {
        const d = await api.kho.kiemKe(thang || undefined);
        if (!alive()) return;
        if (!d.available) {
            bindPicker(state.thang, '', isCurrent);
            fill('kk-kpis', emptyState({ icon: '📋', title: 'Chưa có số liệu kiểm kê',
                message: 'Chưa xác định được công ty hoặc kho của công ty.' }));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        if (chon) state.thang = d.meta.thang;
        bindPicker(d.meta.thang, `<span class="bc-text-sm">Từ ${escapeHtml(fmtDate(d.meta.from))} đến ${escapeHtml(fmtDate(d.meta.to))}</span>`, isCurrent);
        fill('kk-kpis', kpisHtml(d));
        fill('kk-kho', khoHtml(d.kho, d.ira, d.meta.nguong, d.meta.as_of));
        fill('kk-dang', dangHtml(d.dang_dem, d.huy_chot));
        fill('kk-ira', iraHtml(d.ira));
        fill('kk-dc', dcHtml(d));
        fill('kk-sx', sxHtml(d.kk_sx));
        fill('kk-ch', chHtml(d.kk_ch));
        fill('kk-xk', xkHtml(d.xuat_khac));
        fill('kk-don', donHtml(d.don_sx));
        fill('kk-top', topHtml(d.top_lech));
        fill('kk-ve0', ve0Html(d.ve_0));
    } catch (err) {
        if (!alive()) return;
        bindPicker(state.thang, '', isCurrent);  // vẫn chọn lại được tháng khác — không kẹt ở màn lỗi tới khi F5
        fill('kk-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Kiểm kê & điều chỉnh</div>
                <div class="bc-view-banner-sub">Kho nào lâu chưa kiểm, kiểm ra thừa thiếu bao nhiêu, hàng huỷ và điều chỉnh trong tháng</div></div>
            <span class="bc-view-banner-badge">📋 Kho</span>
        </div>
        <div class="bc-filter-bar" id="kk-filter"></div>
        <div id="kk-kpis">${skeletonGrid(5, 128, 'bc-grid-5')}</div>
        <div class="bc-section-title">Kiểm kê gần nhất theo kho</div>
        <div class="bc-card"><div id="kk-kho">${skeleton(240)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Phiếu đang đếm (hiện tại)</div></div><div id="kk-dang">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Độ chính xác tồn</div></div><div id="kk-ira">${skeleton(160)}</div></div>
        </div>
        <div class="bc-section-title">Điều chỉnh kho trong tháng</div>
        <div class="bc-card"><div id="kk-dc">${skeleton(180)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Kiểm kê Sản xuất</div></div><div id="kk-sx">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Phiếu kiểm kho: cửa hàng và kho khác</div></div><div id="kk-ch">${skeleton(160)}</div></div>
        </div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Xuất huỷ, xuất mẫu, xuất khác</div></div><div id="kk-xk">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Dọn tồn của Sản xuất</div></div><div id="kk-don">${skeleton(160)}</div></div>
        </div>
        <div class="bc-section-title">Mã chênh lệch kiểm kê lớn nhất trong tháng</div>
        <div class="bc-card"><div id="kk-top">${skeleton(200)}</div></div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Mã bị đưa về 0 vì không đếm</div></div><div id="kk-ve0">${skeleton(100)}</div></div>
        <div class="bc-note bc-mt-3">ⓘ Giá trị theo giá vốn trên sổ kho, chưa VAT. Bảng kho và phiếu đang đếm là tình hình hôm nay; độ
            chính xác tồn theo lần kiểm gần nhất tính đến cuối tháng chọn; các khoản điều chỉnh theo tháng chọn. Không hiện người đếm,
            người chốt hay ghi chú trên phiếu.</div>`;
    await load(isCurrent);
}
