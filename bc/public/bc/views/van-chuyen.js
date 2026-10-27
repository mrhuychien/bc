// #/van-chuyen — Vận chuyển theo tháng: giao hàng theo hình thức, chuyến xe, cước, sự cố, thu hồi hàng, lịch
// xe. Một lượt gọi bc.api.vc.get_overview(thang); khối nào hệ thống Vận chuyển chưa có thì báo riêng khối đó.

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
const state = { thang: '' };  // CHỈ tháng người xem đã chọn và tải được — mặc định để trống = tháng hiện tại
let seq = 0;  // lượt tải mới nhất — đổi tháng nhanh thì lượt cũ về sau không đè lượt mới
const SECTIONS = ['vc-kpis', 'vc-giao', 'vc-cho', 'vc-chuyen', 'vc-cuoc', 'vc-suco', 'vc-thuhoi', 'vc-xe'];

function money(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function cnt(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : fmtNum(v); }
function off(what) { return `<div class="bc-muted bc-text-sm">Hệ thống Vận chuyển chưa có ${escapeHtml(what)}.</div>`; }
function num1(v) { return v === null || v === undefined ? '—' : String(v).replace('.', ','); }

function monthOptions(cur) {
    const now = new Date();
    let y = now.getFullYear(), m = now.getMonth() + 1;
    const months = [];
    for (let i = 0; i < 12; i++) {
        months.push(`${y}-${String(m).padStart(2, '0')}`);
        m -= 1; if (!m) { m = 12; y -= 1; }
    }
    if (cur && !months.includes(cur)) months.unshift(cur);
    return `<select class="bc-input" id="vc-thang" aria-label="Tháng">${months.map((x) =>
        `<option value="${escapeHtml(x)}" ${x === cur ? 'selected' : ''}>Tháng ${escapeHtml(x.slice(5))}/${escapeHtml(x.slice(0, 4))}</option>`).join('')}</select>`;
}

function kpisHtml(d) {
    const g = d.giao, k = d.cuoc, s = d.su_co;
    const ch = g.available ? g.cho_qua_han : null;
    return `<div class="bc-grid bc-grid-4">
        ${g.available ? statCard({ label: 'Đơn giao trong tháng', icon: '📦', value: fmtNum(g.total),
            rows: [['Đã giao', `${fmtNum(g.da)} · ${fmtPct(g.ty_le_giao)}`], ['Đang giao', fmtNum(g.dang)], ['Chưa giao', fmtNum(g.cho)]] })
            : statCard({ label: 'Đơn giao trong tháng', icon: '📦', value: '—', rows: [['', 'Chưa có trạng thái vận chuyển']] })}
        ${ch ? statCard({ label: `Chờ giao quá ${fmtNum(ch.so_ngay)} ngày (đến hôm nay)`, icon: '⏰', tone: 'danger',
            value: `<span class="${ch.qua_n ? 'bc-txt-danger' : ''}">${fmtNum(ch.qua_n)}</span>`,
            rows: g.xep ? [['Tự giao chưa xếp chuyến', fmtNum(g.xep.chua_xep)], ['Tự giao xếp một phần', fmtNum(g.xep.mot_phan)]] : [] }) : ''}
        ${k.available ? statCard({ label: 'Cước xe nhà', icon: '🚚', tone: 'warning', value: k.an ? '<span class="bc-muted">ẩn</span>' : money(k.tong),
            rows: k.an ? [['Số chuyến', fmtNum(k.so_chuyen)], ['', `Dưới ${fmtNum(k.k)} lái xe — không hiện tiền`]]
                : [['% doanh thu đã giao', fmtPct(k.ty_le_doanh_thu)], ['Mỗi chuyến', money(k.moi_chuyen)], ['Chưa trả', money(k.chua_tra)]] }) : ''}
        ${s.available ? statCard({ label: 'Sự cố đang mở', icon: '⚠️', value: fmtNum(s.dang_mo),
            rows: [[`Mở quá ${fmtNum(s.so_ngay)} ngày`, `<span class="${s.mo_qua_n ? 'bc-txt-danger' : ''}">${fmtNum(s.mo_qua_n)}</span>`],
                ['Phát sinh trong tháng', fmtNum(s.trong_ky)], ['Giá trị ảnh hưởng', money(s.gia_tri_anh_huong)]] }) : ''}
    </div>`;
}

function giaoHtml(g) {
    if (!g.available) return off('trạng thái vận chuyển trên hoá đơn');
    const ld = g.lan_dau;
    return `${dataTable({ rows: g.by_type, sortKey: 'n', emptyMessage: 'Không có đơn trong tháng',
        totalRow: { hinh_thuc: '<b>Tổng</b>', n: `<b>${fmtNum(g.total)}</b>`, gt: `<b>${money(g.value)}</b>`, cho: fmtNum(g.cho),
            dang: fmtNum(g.dang), da: fmtNum(g.da), ty_le_giao: `<b>${fmtPct(g.ty_le_giao)}</b>` },
        columns: [
            { key: 'hinh_thuc', label: 'Hình thức', align: 'left' },
            { key: 'n', label: 'Đơn', render: (r) => fmtNum(r.n) },
            { key: 'gt', label: 'Giá trị', render: (r) => money(r.gt) },
            { key: 'cho', label: 'Chưa giao', render: (r) => fmtNum(r.cho) },
            { key: 'dang', label: 'Đang giao', render: (r) => fmtNum(r.dang) },
            { key: 'da', label: 'Đã giao', render: (r) => fmtNum(r.da) },
            { key: 'ty_le_giao', label: '% giao', render: (r) => fmtPct(r.ty_le_giao) },
        ] })}
        ${ld && ld.so_don ? `<div class="bc-note">Xe nhà giao được ngay lần đầu: <b>${fmtPct(ld.ty_le)}</b> (${fmtNum(ld.da_giao)}/${fmtNum(ld.so_don)} đơn;
            khách hẹn ${fmtNum(ld.khach_hen)}, hoàn ${fmtNum(ld.hoan)}).</div>` : ''}
        <div class="bc-note">Đã phân công hình thức: ${fmtPct(g.ty_le_phan_cong)} số đơn. Trạng thái đơn đi hãng ngoài / xe vào bốc do
            điều phối cập nhật tay nên có thể trễ.</div>`;
}

function choHtml(g) {
    if (!g.available) return '';
    const ch = g.cho_qua_han;
    return `${dataTable({ rows: ch.rows, sortKey: 'qua_n', emptyMessage: 'Không có đơn chờ giao',
        columns: [
            { key: 'hinh_thuc', label: 'Hình thức', align: 'left' },
            { key: 'cho', label: 'Chưa giao', render: (r) => fmtNum(r.cho) },
            { key: 'qua_n', label: `Quá ${ch.so_ngay} ngày`, render: (r) => (r.qua_n ? `<b class="bc-txt-danger">${fmtNum(r.qua_n)}</b>` : '0') },
        ] })}
        <div class="bc-note">Tính đến hôm nay, mọi tháng (bỏ đơn cũ hơn ${fmtNum(ch.tu_ngay)} ngày), từ ngày hoá đơn.</div>`;
}

function chuyenHtml(x) {
    if (!x.available) return off('chuyến xe');
    const st = x.by_status || {};
    return `${kpiGrid([
        { label: 'Số chuyến', value: fmtNum(x.so_chuyen), sub: `Hoàn thành ${fmtNum(st['Hoàn thành'] || 0)} · đang giao ${fmtNum(st['Đang giao'] || 0)} · nháp ${fmtNum(st['Nháp'] || 0)}` },
        { label: 'Đơn / chuyến', value: num1(x.don_moi_chuyen) },
        { label: 'Chuyến / ngày chạy', value: num1(x.chuyen_moi_ngay) },
        { label: 'Tải trung bình (% thể tích)', value: fmtPct(x.tai_tb) },
        { label: 'Chuyến quá tải', value: fmtNum(x.qua_tai), cls: x.qua_tai ? 'bc-txt-danger' : '' },
        { label: 'Chuyến chưa có sức chứa xe', value: fmtNum(x.thieu_cap), cls: x.thieu_cap ? 'bc-txt-warning' : '' },
    ], 3)}
        <div class="bc-chart-wrap bc-mt-3" id="vc-chart-wrap" style="height:180px"><canvas id="vc-chart"></canvas></div>`;
}

async function chuyenChart(x, alive) {
    if (!x.available || !x.by_day.length) { fill('vc-chart-wrap', ''); return; }
    const Chart = await loadChartLib();
    const el = document.getElementById('vc-chart');
    if (!alive() || !el) return;
    charts.add(new Chart(el, {
        type: 'bar',
        data: { labels: x.by_day.map((r) => fmtDate(r.date, true)),
            datasets: [{ label: 'Chuyến', data: x.by_day.map((r) => r.n), backgroundColor: '#6366f1', borderWidth: 0, maxBarThickness: 22 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    }));
}

function cuocHtml(k) {
    if (!k.available) return off('chuyến xe');
    const warn = [];
    if (k.tra_bat_thuong) warn.push(`${fmtNum(k.tra_bat_thuong)} chuyến đánh dấu đã trả cước nhưng bút toán chi chưa duyệt hoặc đã huỷ.`);
    if (k.tra_chuyen_huy) {
        warn.push(`${fmtNum(k.tra_chuyen_huy)} chuyến đã huỷ nhưng bút toán trả cước${k.an ? '' : ` (${fmtMoney(k.tra_chuyen_huy_tien)})`} vẫn còn hiệu lực.`);
    }
    if (k.sua_tay) warn.push(`${fmtNum(k.sua_tay)} chuyến cước sửa tay.`);
    const alert = warn.length ? `<div class="bc-alert">${warn.map(escapeHtml).join('<br>')}</div>` : '';
    if (k.an) {
        return `${alert}${kpiGrid([
            { label: 'Chuyến đã duyệt', value: fmtNum(k.so_chuyen) },
            { label: 'Lái xe chạy trong tháng', value: fmtNum(k.so_lai_xe) },
            { label: 'Chuyến chưa trả cước', value: cnt(k.so_chua_tra) },
        ], 3)}
        <div class="bc-note">Dưới ${fmtNum(k.k)} lái xe chạy trong tháng: tổng cước gần như là thu nhập từng người nên không hiện tiền.</div>`;
    }
    return `${alert}
        ${dataTable({ rows: k.thanh_phan, sortKey: 'tien', pageSize: 10,
            totalRow: { label: '<b>Tổng cước</b>', tien: `<b>${money(k.tong)}</b>` },
            columns: [{ key: 'label', label: 'Khoản', align: 'left', sortable: false },
                { key: 'tien', label: 'Tiền', sortable: false, render: (r) => money(r.tien) }] })}
        ${kpiGrid([
            { label: 'Đã trả', value: money(k.da_tra) },
            { label: 'Chưa trả', value: money(k.chua_tra), sub: k.so_chua_tra === null ? '' : `${fmtNum(k.so_chua_tra)} chuyến`,
                cls: k.chua_tra ? 'bc-txt-warning' : '' },
            { label: 'Mỗi điểm giao', value: money(k.moi_diem) },
        ], 3)}
        <div class="bc-note">Chỉ chuyến đã duyệt, theo ngày giao. % doanh thu = cước / doanh thu trước VAT của phần hàng đã giao, cả hai
            chỉ tính trên chuyến đã hoàn thành (${fmtNum(k.don_da_giao)} đơn, ${money(k.dt_da_giao)}; đơn tách nhiều chuyến chia theo số kiện).</div>`;
}

function suCoHtml(s) {
    if (!s.available) return off('sổ sự cố');
    return `${dataTable({ rows: s.by_type, sortKey: 'n', emptyMessage: 'Không có sự cố trong tháng',
        columns: [{ key: 'loai', label: 'Loại sự cố', align: 'left' },
            { key: 'n', label: 'Số vụ', render: (r) => fmtNum(r.n) },
            { key: 'gt', label: 'Giá trị ảnh hưởng', render: (r) => money(r.gt) }] })}
        ${kpiGrid([
            { label: 'Mất đường', value: money(s.mat_duong), sub: 'hàng không về' },
            { label: 'Đã đòi được', value: money(s.boi_thuong_da_thu), cls: 'bc-txt-success', sub: 'bồi thường' },
            { label: 'Còn đòi', value: money(s.boi_thuong_con_doi), cls: s.boi_thuong_con_doi ? 'bc-txt-warning' : '', sub: 'bồi thường' },
            { label: 'Hàng chưa về', value: cnt(s.hang_chua_ve), sub: 'sự cố có hàng quay về, đang mở' },
            { label: 'Xử lý TB', value: s.ngay_xu_ly_tb === null ? '—' : `${num1(s.ngay_xu_ly_tb)} ngày`, sub: 'sự cố đóng trong tháng' },
        ], 3)}`;
}

function thuHoiHtml(h) {
    if (!h.available) return off('lô thu hồi hàng');
    const gt = h.gia_tri;
    return `${kpiGrid([
        { label: 'Lô đang mở', value: fmtNum(h.dang_mo) },
        { label: 'Mở quá 30 ngày', value: fmtNum(h.mo_qua_30), cls: h.mo_qua_30 ? 'bc-txt-danger' : '' },
        { label: 'Lô tạo trong tháng', value: fmtNum(h.trong_ky) },
    ], 3)}
        ${dataTable({ rows: h.stages, pageSize: 12, emptyMessage: 'Chưa có lô thu hồi',
            columns: [
                { key: 'chang', label: 'Chặng', align: 'left', sortable: false },
                { key: 'n', label: 'Số lô', sortable: false, render: (r) => fmtNum(r.n) },
                { key: 'a7', label: '≤ 7 ngày', sortable: false, render: (r) => fmtNum(r.a7) },
                { key: 'a30', label: '8–30 ngày', sortable: false, render: (r) => fmtNum(r.a30) },
                { key: 'a30p', label: '> 30 ngày', sortable: false,
                    render: (r) => (r.a30p && !['Xong', 'Đã hủy'].includes(r.chang) ? `<b class="bc-txt-danger">${fmtNum(r.a30p)}</b>` : fmtNum(r.a30p)) },
            ] })}
        <div class="bc-note">${h.ke_toan ? 'Chặng theo phiếu kiểm hàng của Kế toán khi đã có phiếu.' : 'Chặng theo trạng thái lô (chưa có phiếu kiểm của Kế toán).'}
            Tuổi tính từ ngày yêu cầu.${gt ? ` Hàng trả về của các lô tạo trong tháng: ${fmtNum(gt.so_hd)} hoá đơn trả đã duyệt
            (${fmtNum(gt.so_lo)} lô), ${money(gt.net)} trước VAT.` : ''}</div>`;
}

/** Như nhat_ky_xe.nhan_muc của vanchuyen: phần đã quá hạn đứng trước (đọc lướt chỉ kịp thấy chữ đầu). */
function hanText(w) {
    const p = [];  // [quá hạn?, chữ]
    if (w.con_km !== null && w.con_km !== undefined) {
        p.push(w.con_km < 0 ? [1, `quá ${fmtNum(-w.con_km)} km`] : w.con_km === 0 ? [1, 'đến mốc km'] : [0, `còn ${fmtNum(w.con_km)} km`]);
    }
    if (w.con_ngay !== null && w.con_ngay !== undefined) {
        p.push(w.con_ngay < 0 ? [1, `quá hạn ${fmtNum(-w.con_ngay)} ngày`]
            : w.con_ngay === 0 ? [0, 'đến hạn hôm nay'] : [0, `còn ${fmtNum(w.con_ngay)} ngày`]);
    }
    return p.sort((a, b) => b[0] - a[0]).map((x) => x[1]).join(' · ');
}

function xeHtml(v) {
    if (!v.available) return off('lịch xe');
    const dk = v.dem.dang_kiem, td = v.dem.thay_dau;
    const cp = v.chi_phi_nam;
    return `${kpiGrid([
        { label: 'Xe đang dùng', value: fmtNum(v.dang_dung) },
        { label: 'Đăng kiểm quá hạn / sắp đến', value: `${fmtNum(dk.qua_han)} / ${fmtNum(dk.sap_den)}`, cls: dk.qua_han ? 'bc-txt-danger' : '',
            sub: dk.chua_co ? `${fmtNum(dk.chua_co)} xe chưa khai lịch` : '' },
        { label: 'Thay dầu quá hạn / sắp đến', value: `${fmtNum(td.qua_han)} / ${fmtNum(td.sap_den)}`, cls: td.qua_han ? 'bc-txt-danger' : '',
            sub: td.chua_co ? `${fmtNum(td.chua_co)} xe chưa khai lịch` : '' },
    ], 3)}
        <div class="bc-grid bc-grid-split bc-mt-3">
            <div>${dataTable({ rows: v.can_xu_ly, pageSize: 8, emptyMessage: 'Không xe nào đến hạn',
                columns: [
                    { key: 'xe', label: 'Xe', align: 'left', render: (r) => `${escapeHtml(r.xe)} <span class="bc-muted">${escapeHtml(r.loai || '')}</span>` },
                    { key: 'viec', label: 'Việc đến hạn', align: 'left', sortable: false,
                        render: (r) => r.viec.map((w) => `<div><span class="bc-badge ${w.muc === 'qua_han' ? 'bc-badge-danger' : 'bc-badge-warning'}">${escapeHtml(w.viec)}</span>
                            <span class="bc-text-sm">${escapeHtml(hanText(w))}</span></div>`).join('') },
                ] })}</div>
            <div>${dataTable({ rows: cp.rows, sortKey: 'tien', emptyMessage: `Chưa ghi chi phí xe năm ${cp.nam}`,
                totalRow: { loai: '<b>Tổng</b>', tien: `<b>${money(cp.tong)}</b>` },
                columns: [{ key: 'loai', label: `Chi phí xe ${cp.nam}`, align: 'left' },
                    { key: 'so', label: 'Lần', render: (r) => fmtNum(r.so) },
                    { key: 'tien', label: 'Tiền', render: (r) => money(r.tien) }] })}</div>
        </div>`;
}

/** Ô chọn tháng. Dựng lại sau mỗi lượt tải: trả focus về ô nếu người dùng đang ở đó (đi bằng phím mũi tên). */
function bindPicker(cur, extra, isCurrent) {
    const refocus = document.activeElement?.id === 'vc-thang';
    fill('vc-filter', `${monthOptions(cur)}${extra}`);
    const sel = document.getElementById('vc-thang');
    sel?.addEventListener('change', (e) => {
        SECTIONS.forEach((id) => fill(id, skeleton(120)));
        load(isCurrent, e.target.value, true);
    });
    if (refocus) sel?.focus();
}

async function load(isCurrent, thang = state.thang, chon = false) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    charts.destroy();
    try {
        const d = await api.vc.overview(thang || undefined);
        if (!alive()) return;
        if (!d.available) {
            fill('vc-kpis', emptyState({ icon: '🚚', title: 'Chưa có số liệu vận chuyển',
                message: 'Site chưa cài hệ thống Vận chuyển (app vanchuyen).' }));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        // Chỉ nhớ tháng người xem tự chọn (để mặc định thì sang tháng mới / Làm mới vẫn theo tháng hiện tại).
        if (chon) state.thang = d.meta.thang;
        bindPicker(d.meta.thang, `<span class="bc-text-sm">Từ ${escapeHtml(fmtDate(d.meta.from))} đến ${escapeHtml(fmtDate(d.meta.to))}</span>`, isCurrent);
        fill('vc-kpis', kpisHtml(d));
        fill('vc-giao', giaoHtml(d.giao));
        fill('vc-cho', choHtml(d.giao));
        fill('vc-chuyen', chuyenHtml(d.chuyen));
        fill('vc-cuoc', cuocHtml(d.cuoc));
        fill('vc-suco', suCoHtml(d.su_co));
        fill('vc-thuhoi', thuHoiHtml(d.thu_hoi));
        fill('vc-xe', xeHtml(d.xe));
        // Biểu đồ lỗi (CDN chặn / mạng yếu) chỉ thay khung biểu đồ, không xoá số đã hiện.
        try { await chuyenChart(d.chuyen, alive); } catch (e) {
            if (alive()) fill('vc-chart-wrap', emptyState({ title: 'Không tải được biểu đồ', message: e?.message || '' }));
        }
    } catch (err) {
        if (!alive()) return;
        // Ô chọn tháng vẫn còn (chọn lại tháng khác / tháng cũ được) — không kẹt ở màn lỗi tới khi F5.
        bindPicker(state.thang, '', isCurrent);
        fill('vc-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Vận chuyển</div>
                <div class="bc-view-banner-sub">Giao hàng, chuyến xe nhà, cước, sự cố và thu hồi hàng</div></div>
            <span class="bc-view-banner-badge">🚚 Vận chuyển</span>
        </div>
        <div class="bc-filter-bar" id="vc-filter"></div>
        <div id="vc-kpis">${skeletonGrid(4, 128)}</div>
        <div class="bc-section-title">Đơn theo hình thức vận chuyển</div>
        <div class="bc-card"><div id="vc-giao">${skeleton(200)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Đơn chưa giao</div></div><div id="vc-cho">${skeleton(200)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Sự cố giao hàng</div></div><div id="vc-suco">${skeleton(200)}</div></div>
        </div>
        <div class="bc-section-title">Chuyến xe nhà</div>
        <div class="bc-card"><div id="vc-chuyen">${skeleton(160)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Cước xe nhà</div></div><div id="vc-cuoc">${skeleton(200)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Thu hồi hàng</div></div><div id="vc-thuhoi">${skeleton(160)}</div></div>
        </div>
        <div class="bc-section-title">Đội xe</div>
        <div class="bc-card"><div id="vc-xe">${skeleton(160)}</div></div>
        <div class="bc-note bc-mt-3">ⓘ Đơn = hoá đơn bán đã duyệt trong tháng (bỏ hàng trả, hoá đơn đầu kỳ và nhóm khách Showroom), giá trị
            trước VAT. Chuyến, cước theo ngày giao của chuyến. Không hiện tên lái xe, khách hay người liên hệ.</div>`;
    await load(isCurrent);
}
