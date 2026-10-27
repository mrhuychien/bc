// #/nhan-su — Nhân sự: quân số, vào / nghỉ 12 tháng, BHXH, quỹ lương thực nhận theo loại (công nhật / khoán),
// giấy tờ hết hạn, việc cần làm của Phòng nhân sự. Một lượt gọi bc.api.ns.get_overview — chỉ số tổng hợp,
// không tên / mã nhân viên; nhóm < K người không hiện tiền.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, fmtPct } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
const SECTIONS = ['ns-kpis', 'ns-dept', 'ns-move', 'ns-luong', 'ns-luong-bp', 'ns-bhxh', 'ns-giay', 'ns-viec'];
const MUC = { do: ['bc-badge-danger', 'Gấp'], vang: ['bc-badge-warning', 'Cần làm'] };

function money(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function thang(s) { return `T${Number(String(s).slice(5))}/${String(s).slice(0, 4)}`; }
function off(what) { return `<div class="bc-muted bc-text-sm">Hệ thống chưa có ${escapeHtml(what)}.</div>`; }

/** Một ô lương: null = trước khi có phiếu; an = nhóm < K người. */
function cellHtml(c) {
    if (c === null || c === undefined) return '<span class="bc-muted">chưa có dữ liệu</span>';
    if (c.an) return `<span class="bc-muted" title="Dưới ${fmtNum(c.k)} người có tiền trên phiếu — không hiện tiền">${fmtNum(c.so_nguoi)} người · ẩn</span>`;
    return `${money(c.thuc_nhan)} <span class="bc-muted bc-text-sm">· ${fmtNum(c.so_nguoi)} ng${c.so_nhap ? ` · ${fmtNum(c.so_nhap)} nháp` : ''}</span>`;
}

const TEN_LOAI = { nhat: 'công nhật', khoan: 'khoán' };

/** Tổng thực nhận của một tháng: null nếu chưa loại nào có phiếu; an nếu có ô bị ẩn; thieu = loại đã có trên
 *  hệ thống nhưng tháng đó chưa có dữ liệu (vd khoán trước khi có phiếu khoán) — tổng khi đó KHÔNG đủ. */
function monthTotal(L, s) {
    const ks = ['nhat', 'khoan'].filter((k) => L.co[k]);
    const parts = ks.map((k) => s[k]).filter(Boolean);
    if (!parts.length) return null;
    const thieu = ks.filter((k) => !s[k]).map((k) => TEN_LOAI[k]);
    if (parts.some((p) => p.an)) return { an: true, thieu };
    return { an: false, thieu, tong: parts.reduce((a, p) => a + (p.thuc_nhan || 0), 0), nhap: parts.reduce((a, p) => a + p.so_nhap, 0) };
}

function kyTotal(L) {
    const s = (L.series || []).find((x) => x.thang === L.ky) || {};
    const t = monthTotal(L, s);
    return t && { ...t, parts: s };
}

function kpisHtml(d) {
    const q = d.nhan_su, b = d.bien_dong, h = d.bhxh, L = d.luong;
    const kt = L.available ? kyTotal(L) : null;
    return `<div class="bc-grid bc-grid-4">
        ${statCard({ label: 'Đang làm', icon: '👥', value: fmtNum(q.dang_lam),
            rows: [['Công nhật', fmtNum(q.loai['Nhật'])], ['Công khoán', fmtNum(q.loai['Khoán'])], ['Tạm nghỉ', fmtNum(q.tam_nghi)]] })}
        ${statCard({ label: 'Vào / nghỉ 12 tháng', icon: '🔁', tone: 'warning',
            value: `<span class="bc-txt-success">+${fmtNum(b.vao)}</span> / <span class="bc-txt-danger">−${fmtNum(b.nghi)}</span>`,
            rows: [['Nghỉ chưa ghi ngày nghỉ', fmtNum(b.nghi_khong_ngay)], ['Đang làm mà đã có ngày nghỉ', fmtNum(q.active_da_nghi)]] })}
        ${h.available ? statCard({ label: h.uoc_tinh ? 'Đóng BHXH (ước tính)' : 'Đóng BHXH', icon: '🛡️', tone: 'success', value: fmtPct(h.ty_le),
            rows: [['Đang đóng', `${fmtNum(h.dong)} / ${fmtNum(h.dang_lam)}`],
                ...(h.rui_ro === null ? [] : [['Quá 30 ngày chưa đóng, chưa ghi lý do', `<span class="${h.rui_ro ? 'bc-txt-danger' : ''}">${fmtNum(h.rui_ro)}</span>`]]),
                ...(h.chua_muc === null ? [] : [['Đóng nhưng chưa có mức trừ', fmtNum(h.chua_muc)]])] })
            : statCard({ label: 'Đóng BHXH', icon: '🛡️', value: '—', rows: [['', 'Chưa có dữ liệu BHXH']] })}
        ${kt ? statCard({ label: `Quỹ lương ${thang(L.ky)} (tạm tính${kt.thieu.length ? `, chưa gồm ${kt.thieu.join(', ')}` : ''})`, icon: '💰', tone: 'danger',
            value: kt.an ? '<span class="bc-muted">ẩn</span>' : money(kt.tong),
            rows: [['Công nhật', kt.parts.nhat ? (kt.parts.nhat.an ? 'ẩn' : money(kt.parts.nhat.thuc_nhan)) : '—'],
                ['Công khoán', kt.parts.khoan ? (kt.parts.khoan.an ? 'ẩn' : money(kt.parts.khoan.thuc_nhan)) : '—'],
                ['Phiếu còn nháp', kt.an ? '—' : fmtNum(kt.nhap)]] })
            : statCard({ label: 'Quỹ lương tháng trước', icon: '💰', value: '—', rows: [['', 'Chưa có phiếu lương']] })}
    </div>`;
}

function deptHtml(q) {
    return dataTable({ rows: q.by_dept, sortKey: 'dang_lam', emptyMessage: 'Chưa có nhân viên',
        totalRow: { bo_phan: '<b>Tổng</b>', dang_lam: `<b>${fmtNum(q.dang_lam)}</b>`, tam_nghi: `<b>${fmtNum(q.tam_nghi)}</b>` },
        columns: [
            { key: 'bo_phan', label: 'Bộ phận', align: 'left' },
            { key: 'loai', label: 'Lương', render: (r) => `<span class="bc-badge ${r.loai === 'Khoán' ? 'bc-badge-primary' : 'bc-badge-muted'}">${escapeHtml(r.loai === 'Khoán' ? 'Khoán' : 'Công nhật')}</span>` },
            { key: 'dang_lam', label: 'Đang làm', render: (r) => fmtNum(r.dang_lam) },
            { key: 'tam_nghi', label: 'Tạm nghỉ', render: (r) => (r.tam_nghi ? fmtNum(r.tam_nghi) : '<span class="bc-muted">–</span>') },
        ] });
}

async function moveChart(b, alive) {
    const Chart = await loadChartLib();
    const el = document.getElementById('ns-move-chart');
    if (!alive() || !el) return;
    charts.add(new Chart(el, {
        type: 'bar',
        data: { labels: b.rows.map((r) => thang(r.thang)),
            datasets: [{ label: 'Vào làm', data: b.rows.map((r) => r.vao), backgroundColor: '#10b981', borderWidth: 0, maxBarThickness: 18 },
                { label: 'Nghỉ việc', data: b.rows.map((r) => r.nghi), backgroundColor: '#ef4444', borderWidth: 0, maxBarThickness: 18 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    }));
}

function luongHtml(L) {
    if (!L.available) return off('phiếu lương (SalaryDay / phiếu lương khoán)');
    const rows = L.series.slice().reverse().map((s) => ({ ...s, k: L.k }));
    const warn = [];
    if (L.hook_tat) warn.push('Phiếu công nhật chưa bật tính lại tự động trên máy chủ: phiếu chấm công lưu từ màn chấm công có thể chưa cập nhật tổng tiền.');
    if (L.loi_ky) warn.push(`${fmtNum(L.loi_ky)} phiếu lương chưa có tháng / năm hợp lệ — không tính vào quỹ.`);
    const tot = (s) => {
        const t = monthTotal(L, s);
        if (!t) return '<span class="bc-muted">—</span>';
        if (t.an) return '<span class="bc-muted">ẩn</span>';
        return t.thieu.length ? `${money(t.tong)} <span class="bc-muted bc-text-sm">chưa gồm ${escapeHtml(t.thieu.join(', '))}</span>`
            : `<b>${money(t.tong)}</b>`;
    };
    return `${warn.length ? `<div class="bc-alert">${warn.map(escapeHtml).join('<br>')}</div>` : ''}
        ${dataTable({ rows, pageSize: 12, columns: [
            { key: 'thang', label: 'Tháng', align: 'left', sortable: false,
                render: (s) => `${escapeHtml(thang(s.thang))}${s.tam_tinh ? ' <span class="bc-badge bc-badge-warning">tạm tính</span>' : ''}` },
            { key: 'nhat', label: 'Công nhật', sortable: false, render: (s) => (L.co.nhat ? cellHtml(s.nhat && { ...s.nhat, k: L.k }) : '<span class="bc-muted">—</span>') },
            { key: 'khoan', label: 'Công khoán', sortable: false, render: (s) => (L.co.khoan ? cellHtml(s.khoan && { ...s.khoan, k: L.k }) : '<span class="bc-muted">—</span>') },
            { key: 'tong', label: 'Tổng thực nhận', sortable: false, render: tot },
        ] })}
        <div class="bc-note">Lương THỰC NHẬN (sau bảo hiểm, phạt), mỗi người mỗi tháng một phiếu như màn Lương của Nhân sự; làm tròn
            100.000 đ. Tháng trước và tháng này tạm tính (gồm phiếu nháp); tháng cũ hơn chỉ phiếu đã duyệt, "nháp" là phiếu còn treo
            chưa tính. Không gồm lương Ban lãnh đạo. Dưới ${fmtNum(L.k)} người có tiền trên phiếu thì không hiện tiền.</div>`;
}

function luongBpHtml(L) {
    if (!L.available) return '';
    if (!L.bo_phan.length) return `<div class="bc-muted bc-text-sm">Chưa có phiếu lương đã duyệt ${escapeHtml(thang(L.ky_bo_phan))}.</div>`;
    return `${dataTable({ rows: L.bo_phan, sortKey: 'so_nguoi', columns: [
        { key: 'nhom', label: 'Nhóm', align: 'left' },
        { key: 'loai', label: 'Loại' },
        { key: 'so_nguoi', label: 'Số người', render: (r) => fmtNum(r.so_nguoi) },
        { key: 'thuc_nhan', label: 'Thực nhận', render: (r) => money(r.thuc_nhan), sortValue: (r) => r.thuc_nhan ?? -1 },
        { key: 'tong_tien', label: 'Tổng thu nhập', render: (r) => money(r.tong_tien), sortValue: (r) => r.tong_tien ?? -1 },
    ] })}
        <div class="bc-note">Tháng đã chốt gần nhất, chỉ phiếu đã duyệt (tháng tạm tính thay đổi theo từng phiếu nên không chia bộ
            phận). Công nhật theo bộ phận ghi trên phiếu lương; bộ phận dưới ${fmtNum(L.k)} người có tiền được gộp để không suy ra lương
            từng người. Công khoán tính chung một nhóm.</div>`;
}

function bhxhHtml(h, k) {
    if (!h.available) return off('dữ liệu BHXH');
    if (h.uoc_tinh) return `<div class="bc-note">Chưa cài phân hệ Nhân sự: "đang đóng" ước tính theo nhân viên có mức trừ bảo hiểm.</div>`;
    return `${dataTable({ rows: h.ly_do, sortKey: 'n', emptyMessage: 'Mọi người đang làm đều đóng BHXH',
        columns: [{ key: 'ly_do', label: 'Lý do không đóng', align: 'left' }, { key: 'n', label: 'Số người', render: (r) => fmtNum(r.n) }] })}
        ${h.lech ? `<div class="bc-alert">${fmtNum(h.lech)} người có mức trừ bảo hiểm nhưng chưa đánh dấu đóng BHXH.</div>` : ''}
        <div class="bc-note">Lý do dưới ${fmtNum(k)} người được gộp (lý do từng người là thông tin riêng).</div>`;
}

function giayHtml(g) {
    if (!g.available) return off('giấy tờ nhân viên');
    const v = (x) => `<span class="${x.do ? 'bc-txt-danger' : ''}">${fmtNum(x.do)}</span> / <span class="${x.vang ? 'bc-txt-warning' : ''}">${fmtNum(x.vang)}</span>`;
    return `${kpiGrid([
        { label: 'Hợp đồng', value: v(g.hd), sub: 'hết hạn / sắp hết' },
        { label: 'Khám sức khỏe', value: v(g.ksk), sub: 'hết hạn / sắp hết' },
        { label: 'Xác nhận ATTP', value: v(g.attp), sub: 'hết hạn / sắp hết' },
    ], 3)}
        <div class="bc-note">Số người còn làm hoặc tạm nghỉ có giấy tờ đã hết hạn / hết hạn trong ${fmtNum(g.so_ngay)} ngày tới (giấy mới nhất mỗi loại).</div>`;
}

function viecHtml(c) {
    if (!c.available) return off('phân hệ Nhân sự (app ns)');
    return `${dataTable({ rows: c.rows, pageSize: 12, emptyMessage: 'Không có việc tồn',
        columns: [
            { key: 'ten', label: 'Việc', align: 'left', sortable: false },
            { key: 'muc', label: 'Mức', sortable: false, render: (r) => `<span class="bc-badge ${(MUC[r.muc] || MUC.vang)[0]}">${(MUC[r.muc] || MUC.vang)[1]}</span>` },
            { key: 'so_nguoi', label: 'Số người', sortable: false, render: (r) => fmtNum(r.so_nguoi) },
        ] })}
        ${c.khoan_thieu_phieu ? `<div class="bc-note">Trong "chưa có phiếu lương" có ${fmtNum(c.khoan_thieu_phieu)} người công khoán
            (${escapeHtml(thang(c.thang_truoc))}) — phiếu lương khoán chỉ có trên hệ thống từ khi Sản xuất chốt lương khoán.</div>` : ''}
        <div class="bc-note">Như màn Việc cần làm của Phòng nhân sự, đếm theo người (không gồm giấy tờ — xem khối trên, và sinh nhật).</div>`;
}

export async function render({ container, isCurrent }) {
    charts.destroy();
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Nhân sự</div>
                <div class="bc-view-banner-sub" id="ns-sub">Quân số, BHXH, quỹ lương — chỉ số tổng hợp, không hiện tên</div></div>
            <span class="bc-view-banner-badge">👥 Nhân sự</span>
        </div>
        <div id="ns-kpis">${skeletonGrid(4, 128)}</div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Quân số theo bộ phận</div></div><div id="ns-dept">${skeleton(200)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Vào / nghỉ 12 tháng</div></div><div id="ns-move">${skeleton(200)}</div></div>
        </div>
        <div class="bc-section-title">Quỹ lương thực nhận 12 tháng</div>
        <div class="bc-card"><div id="ns-luong">${skeleton(260)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title" id="ns-luong-bp-title">Quỹ lương tháng đã chốt theo bộ phận</div></div><div id="ns-luong-bp">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">BHXH — người chưa đóng</div></div><div id="ns-bhxh">${skeleton(160)}</div></div>
        </div>
        <div class="bc-section-title">Giấy tờ hết hạn</div>
        <div class="bc-card"><div id="ns-giay">${skeleton(90)}</div></div>
        <div class="bc-section-title">Việc tồn của Phòng nhân sự</div>
        <div class="bc-card"><div id="ns-viec">${skeleton(200)}</div></div>`;
    try {
        const d = await api.ns.overview();
        if (!isCurrent()) return;
        if (!d.available) {
            fill('ns-kpis', emptyState({ icon: '👥', title: 'Chưa có dữ liệu nhân sự' }));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        fill('ns-sub', `Đến ${escapeHtml(fmtDate(d.meta.as_of))} · chỉ số tổng hợp, không hiện tên`);
        fill('ns-kpis', kpisHtml(d));
        fill('ns-dept', deptHtml(d.nhan_su));
        fill('ns-move', `<div class="bc-chart-wrap" id="ns-move-wrap" style="height:220px"><canvas id="ns-move-chart"></canvas></div>
            <div class="bc-note">Theo ngày vào làm / ngày nghỉ việc trên hồ sơ. Công nhân thời vụ chuyển "tạm nghỉ" không tính là nghỉ việc.</div>`);
        fill('ns-luong', luongHtml(d.luong));
        if (d.luong.available) fill('ns-luong-bp-title', `Quỹ lương ${escapeHtml(thang(d.luong.ky_bo_phan))} theo bộ phận (đã chốt)`);
        fill('ns-luong-bp', luongBpHtml(d.luong));
        fill('ns-bhxh', bhxhHtml(d.bhxh, d.meta.k));
        fill('ns-giay', giayHtml(d.giay_to));
        fill('ns-viec', viecHtml(d.canh_bao));
        try { await moveChart(d.bien_dong, isCurrent); } catch (e) {
            if (isCurrent()) fill('ns-move-wrap', emptyState({ title: 'Không tải được biểu đồ', message: e?.message || '' }));
        }
    } catch (err) {
        if (!isCurrent()) return;
        fill('ns-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}
