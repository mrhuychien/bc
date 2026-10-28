// #/nhap-tp — Nhập thành phẩm & giá vốn theo tháng: thành phẩm thủ kho đã nhận (theo phiếu nhập của sản xuất, từng
// ngày + 12 tháng), phiếu chờ duyệt, hàng đã vào hộp chưa nhập kho, nợ BOM (giá vốn tạm), nguyên liệu còn treo trên sổ,
// thành phẩm chưa có giá vốn. Một lượt gọi bc.api.kho_nhap.get_overview(thang); khối nào thiếu dữ liệu thì báo riêng.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
const state = { thang: '' };  // CHỈ tháng người xem đã chọn và tải được — trống = tháng hiện tại
let seq = 0;  // lượt tải mới nhất — đổi tháng nhanh thì lượt cũ về sau không đè lượt mới
const SECTIONS = ['nt-kpis', 'nt-nhap', 'nt-month', 'nt-cho', 'nt-vaohop', 'nt-nobom', 'nt-nvl', 'nt-gv0'];
const Q = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
const C1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });

function money(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function qn(v) { return v === null || v === undefined ? '—' : Q.format(v); }
function ct(v) { return v === null || v === undefined ? '—' : C1.format(v); }
/** Số lượng kèm đơn vị; lẫn đơn vị (server trả null) → "—". */
function qu(v, uom) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `${qn(v)} ${escapeHtml(uom || '')}`.trim(); }
/** Khối không có số: lỗi tính → "không tính được"; site chưa cài sx (meta.sx false) → nói rõ chưa cài, không ngụ ý "chưa có phiếu". */
function off(what, x, sx = true) {
    if (x && x.error) return `<div class="bc-muted bc-text-sm">Không tính được ${escapeHtml(what)} lúc này.</div>`;
    return sx === false ? `<div class="bc-muted bc-text-sm">Hệ thống sản xuất (app sx) chưa cài nên chưa có ${escapeHtml(what)}.</div>`
        : `<div class="bc-muted bc-text-sm">Hệ thống sản xuất chưa có ${escapeHtml(what)}.</div>`;
}
/** Phần chưa quy được thùng — chữ thường (tooltip biểu đồ vẽ trên canvas, không phải HTML). */
function noCartonText(x) {
    if (!x || !x.items_without_carton_factor) return '';
    const n = x.boxes_without_carton_factor;
    return `${n === null || n === undefined ? `${fmtNum(x.items_without_carton_factor)} mã` : `${qn(n)} ${x.uom_without || ''}`.trim()} chưa khai quy cách thùng`;
}
/** Như trên — chuỗi HTML đã escape. */
function noCarton(x) { return escapeHtml(noCartonText(x)); }
/** Ô "Thùng" của một tổng (ngày / tháng): số thùng + dòng "+ N hộp" của mã chưa khai quy cách thùng (thùng không gồm phần đó). */
function ctCell(x) {
    if (!x.items_without_carton_factor) return ct(x.cartons);
    const n = x.boxes_without_carton_factor;
    const plus = n === null || n === undefined ? `${fmtNum(x.items_without_carton_factor)} mã` : `${qn(n)} ${escapeHtml(x.uom_without || '')}`.trim();
    return `${ct(x.cartons)}<div class="bc-muted bc-text-sm nt-nocarton" title="${noCarton(x)} — không quy ra thùng">+ ${plus}</div>`;
}
function monthLabel(m) { return `T${Number(m.slice(5))}/${m.slice(2, 4)}`; }
const BOX = 'Hộp';  // đơn vị thường gặp — ô bảng chỉ ghi đơn vị khi KHÁC hộp
/** Ô số lượng của bảng tháng: lẫn đơn vị (server trả null) → "—"; đơn vị khác hộp thì ghi kèm. */
function qm(v, uom) {
    if (v === null || v === undefined) return '<span class="bc-muted" title="Lẫn nhiều đơn vị (hộp, kg…) — không cộng chung">—</span>';
    return uom && uom !== BOX ? `${qn(v)} ${escapeHtml(uom)}` : qn(v);
}
/** Đơn vị chung của một dãy ngày / tháng để vẽ theo số lượng; ô nào lẫn đơn vị hoặc hai đơn vị khác nhau → null (vẽ theo thùng). */
function chartUnit(rows, fallback) {
    if (rows.some((r) => r.qty === null || r.qty === undefined)) return null;
    const us = new Set(rows.filter((r) => r.qty).map((r) => r.uom || ''));
    return us.size > 1 ? null : ([...us][0] || fallback);
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
    return `<select class="bc-input" id="nt-thang" aria-label="Tháng">${months.map((x) =>
        `<option value="${escapeHtml(x)}" ${x === cur ? 'selected' : ''}>Tháng ${escapeHtml(x.slice(5))}/${escapeHtml(x.slice(0, 4))}</option>`).join('')}</select>`;
}

// ─── Thẻ tổng ────────────────────────────────────────────────────────────────
// Hai hàng tách bạch: số CỦA THÁNG CHỌN (nhập kho, nhập giá vốn 0) và TÌNH HÌNH HÔM NAY (phiếu chờ duyệt, đã vào hộp chưa nhập,
// nợ BOM đang mở, thành phẩm đang tồn giá vốn 0 — không đổi theo tháng chọn). Không thẻ nào trộn số hôm nay với số của tháng.
function kpisHtml(d) {
    const m = d.meta, n = d.nhap, q = d.cho_duyet, v = d.vao_hop, b = d.no_bom, g = d.gia_von_0;
    const na = (label, icon, why) => statCard({ label, icon, value: '—', rows: [['', escapeHtml(why)]] });
    const noSx = 'Chưa cài sx';  // ngắn: thẻ hẹp ở 390px; dải cảnh báo phía trên giải thích đủ
    let c1;
    if (n.available) {
        const t = n.total;
        const rows = [['Thùng', ct(t.cartons)], ['Giá trị (giá vốn)', money(t.value)], ['Phiếu đã duyệt', fmtNum(t.slips)],
            ['Nhập tạm, chưa có BOM', qu(t.by_kind.tam.qty, t.by_kind.tam.uom || t.uom)]];
        if (t.items_without_carton_factor) rows.push(['Chưa khai thùng', noCarton(t).replace(' chưa khai quy cách thùng', '')]);
        c1 = statCard({ label: 'Thành phẩm nhập kho trong tháng', icon: '📦',
            value: t.qty === null ? `${ct(t.cartons)} thùng` : qu(t.qty, t.uom || 'hộp'), rows });
    } else c1 = na('Thành phẩm nhập kho trong tháng', '📦', n.error ? 'Không tính được' : noSx);
    const nk = g.available ? g.nhap_ky : null;
    const c5 = nk ? statCard({ label: 'Nhập giá vốn 0 trong tháng', icon: '🪙', tone: nk.entries ? 'warning' : '',
        value: nk.qty === null ? `${fmtNum(nk.entries)} phiếu kho` : qu(nk.qty, nk.uom || 'hộp'),
        rows: [['Phiếu kho', fmtNum(nk.entries)], ['Số mã', fmtNum(nk.items)]] })
        : na('Nhập giá vốn 0 trong tháng', '🪙', 'Không tính được');
    const c2 = q.available ? statCard({ label: 'Phiếu nhập chờ thủ kho duyệt', icon: '⏳', tone: q.count ? 'warning' : '',
        value: fmtNum(q.count), rows: [['Số lượng', qu(q.qty, q.uom)],
            ['Phiếu cũ nhất', q.oldest_age_days === null ? '—' : `<span class="${q.oldest_age_days > 2 ? 'bc-txt-danger' : ''}">${fmtNum(q.oldest_age_days)} ngày</span>`],
            ['Sẽ thành nợ BOM', qu(q.no_bom_qty, q.uom)], ['Phiếu hàng Tết', fmtNum(q.count_tet)]] })
        : na('Phiếu nhập chờ thủ kho duyệt', '⏳', q.error ? 'Không tính được' : noSx);
    let cv;
    if (v.available) {
        const rows = [['Thùng', ct(v.cartons)], ['Số mã', fmtNum(v.items)], ['Vào hộp từ', escapeHtml(fmtDate(v.from))]];
        if (v.items_without_carton_factor) rows.splice(1, 0, ['Chưa khai thùng', noCarton(v).replace(' chưa khai quy cách thùng', '')]);
        cv = statCard({ label: 'Đã vào hộp, chưa nhập kho', icon: '📥', value: qu(v.qty, v.uom), rows });
    } else cv = na('Đã vào hộp, chưa nhập kho', '📥', v.error ? 'Không tính được' : noSx);
    const c3 = b.available ? statCard({ label: 'Nợ BOM đang mở', icon: '🧾', tone: b.rows ? 'warning' : '',
        value: b.qty === null ? `${fmtNum(b.rows)} dòng` : qu(b.qty, b.uom || 'hộp'),
        rows: [['Giá tạm lúc nhập', money(b.value_tam)], ['Giá tạm 0', qu(b.qty_gia_0, b.uom)],
            ['Nợ cũ nhất', b.age_days === null ? '—' : `<span class="${b.age_days > b.ngay_no_lau ? 'bc-txt-danger' : ''}">${fmtNum(b.age_days)} ngày</span>`],
            ['Xử lý được ngay', `${fmtNum(b.xu_ly_ngay.items)} mã`]] })
        : na('Nợ BOM đang mở', '🧾', b.error ? 'Không tính được' : noSx);
    let c4;
    if (g.available) {
        const t = g.ton;
        const rows = [['Số mã', fmtNum(t.items)], ['Thùng', ct(t.cartons)]];
        if (t.items_without_carton_factor) rows.push(['Chưa khai thùng', noCarton(t).replace(' chưa khai quy cách thùng', '')]);
        c4 = statCard({ label: 'Thành phẩm đang tồn giá vốn 0', icon: '⚠️', tone: t.rows ? 'danger' : '',
            value: t.qty === null ? `${fmtNum(t.rows)} dòng` : qu(t.qty, t.uom || 'hộp'), rows });
    } else c4 = na('Thành phẩm đang tồn giá vốn 0', '⚠️', 'Không tính được');
    const ym = `${m.thang.slice(5)}/${m.thang.slice(0, 4)}`;
    return `<div class="bc-section-title" id="nt-kpi-thang-title">Trong tháng ${escapeHtml(ym)}</div>
        <div class="bc-grid bc-grid-2" id="nt-kpi-thang">${c1}${c5}</div>
        <div class="bc-section-title" id="nt-kpi-nay-title">Tình hình hôm nay ${escapeHtml(fmtDate(m.as_of))} · không theo tháng chọn</div>
        <div class="bc-grid bc-grid-4" id="nt-kpi-nay">${c2}${cv}${c3}${c4}</div>`;
}

// ─── Nhập kho trong tháng ────────────────────────────────────────────────────
function nhapHtml(n, meta) {
    if (!n.available) return off('phiếu nhập thành phẩm', n, meta.sx);
    const t = n.total, k = t.by_kind, dc = n.doi_chieu, np = n.ngoai_phieu;
    const box = t.uom || 'hộp';
    const khop = !dc.slips_lech;
    const dcText = khop ? '<span class="bc-txt-success">Khớp</span>'
        : `<span class="bc-txt-danger">${fmtNum(dc.slips_lech)} phiếu lệch</span>`;
    // Hai vế chỉ in khi mỗi vế cùng một đơn vị (lẫn Hộp + Kg → không cộng).
    const haiVe = dc.slip_qty !== null && dc.se_qty !== null;
    return `<div class="bc-chart-wrap" id="nt-day-wrap" style="height:200px"><canvas id="nt-day-chart"></canvas></div>
        ${kpiGrid([
            { label: 'Có định mức', value: money(k.bom.value), sub: `${qu(k.bom.qty, k.bom.uom || t.uom)} · đã trừ nguyên liệu` },
            { label: 'Nhập tạm', value: money(k.tam.value), sub: `${qu(k.tam.qty, k.tam.uom || t.uom)} · chưa có BOM`, cls: k.tam.qty ? 'bc-txt-warning' : '' },
            { label: 'Phiếu ↔ sổ kho', value: dcText, sub: khop ? `${fmtNum(t.slips)} phiếu`
                : haiVe ? `phiếu ${qu(dc.slip_qty, dc.slip_uom)} · sổ ${qu(dc.se_qty, dc.se_uom)}` : 'nhiều đơn vị, không cộng chung' },
        ], 3)}
        ${np.entries ? `<div class="bc-note">Nhập Kho thành phẩm ngoài phiếu sản xuất: <b>${qu(np.qty, np.uom)}</b> (${fmtNum(np.entries)} phiếu kho
            — nhập tay, chuyển từ xưởng, tồn đầu kỳ)${np.items.length ? `: ${np.items.slice(0, 5).map((r) => `${escapeHtml(r.short_name)} ${qm(r.qty, r.uom)}`).join(', ')}` : ''}.</div>` : ''}
        ${khop ? '' : `<div class="bc-alert">${fmtNum(dc.slips_lech)} phiếu đã duyệt nhưng phiếu kho đi kèm bị huỷ hoặc lệch số${haiVe
            ? ` (theo phiếu ${qu(dc.slip_qty, dc.slip_uom)}, trên sổ kho ${qu(dc.se_qty, dc.se_uom)})` : ''} — giá trị tháng này thiếu phần đó.</div>`}
        <div class="bc-mt-3" id="nt-top">${dataTable({ rows: n.top_items, sortKey: 'qty', pageSize: 10,
            emptyMessage: `Không nhập thành phẩm nào trong tháng ${meta.thang.slice(5)}/${meta.thang.slice(0, 4)}`,
            columns: [
                { key: 'short_name', label: 'Thành phẩm', align: 'left', render: (r) => escapeHtml(r.short_name) },
                { key: 'qty', label: 'Số lượng', render: (r) => qu(r.qty, r.uom) },
                { key: 'cartons', label: 'Thùng', render: (r) => (r.cartons ? ct(r.cartons) : '<span class="bc-muted">—</span>') },
                { key: 'value', label: 'Giá trị', render: (r) => money(r.value) },
            ] })}</div>
        ${noCarton(t) ? `<div class="bc-note">${noCarton(t)} (không quy ra thùng${chartUnit(n.by_day, t.uom || BOX)
            ? '' : '; biểu đồ theo ngày vẽ theo thùng vì tháng có mã khác đơn vị nên không gồm phần này'}).</div>` : ''}`;
}

function monthHtml(n, meta) {
    if (!n.available) return off('phiếu nhập thành phẩm', n, meta.sx);
    const rows = n.by_month.slice().reverse().map((r) => ({ ...r, label: monthLabel(r.month) }));
    // Có nhập ngoài phiếu = có phiếu kho ngoài phiếu (đếm), KHÔNG suy từ số lượng: tháng lẫn đơn vị có số lượng null.
    const anyNgoai = n.by_month.some((r) => r.ngoai_entries > 0);
    const mixed = n.by_month.some((r) => r.qty === null || r.so_kho_qty === null || r.ngoai_phieu === null);
    const anyNoCarton = n.by_month.some((r) => r.items_without_carton_factor);
    const byCarton = !chartUnit(n.by_month, n.total.uom || BOX);  // biểu đồ 12 tháng vẽ theo thùng
    const ngoaiCell = (r) => {
        if (!r.ngoai_entries) return '0';
        const v = r.ngoai_phieu === null ? `${fmtNum(r.ngoai_entries)} phiếu kho` : qm(r.ngoai_phieu, r.ngoai_uom);
        return `<b class="bc-txt-warning">${v}</b>`;
    };
    return `<div class="bc-chart-wrap" id="nt-month-wrap" style="height:200px"><canvas id="nt-month-chart"></canvas></div>
        <div class="bc-mt-3" id="nt-month-table">${dataTable({ rows, pageSize: 12, scrollButtons: false,
            columns: [
                { key: 'label', label: 'Tháng', align: 'left', sortable: false },
                { key: 'qty', label: 'Theo phiếu', sortable: false, render: (r) => qm(r.qty, r.uom) },
                { key: 'cartons', label: 'Thùng', sortable: false, render: ctCell },
                { key: 'value', label: 'Giá trị', sortable: false, render: (r) => money(r.value) },
                { key: 'so_kho_qty', label: 'Theo sổ kho', sortable: false, render: (r) => qm(r.so_kho_qty, r.so_kho_uom) },
                { key: 'ngoai_phieu', label: 'Ngoài phiếu', sortable: false, render: ngoaiCell },
            ] })}</div>
        <div class="bc-note">"Theo sổ kho" = mọi phiếu nhập Kho thành phẩm từ sản xuất (gồm nhập tay, chuyển từ xưởng, tồn đầu kỳ; bỏ kiểm kê,
            dọn tồn). ${anyNgoai ? '"Ngoài phiếu" là phần không đi qua phiếu nhập của sản xuất — nên bằng 0.' : 'Mọi tháng đều không có nhập ngoài phiếu.'}
            ${mixed ? '"—" = tháng có mã khác đơn vị (hộp, kg…), không cộng chung; "Ngoài phiếu" khi đó ghi số phiếu kho.' : ''}
            ${anyNoCarton ? `"+ …" dưới cột Thùng = hàng của mã chưa khai quy cách thùng, không quy ra thùng được (số thùng chưa gồm phần này${byCarton
                ? '; biểu đồ vẽ theo thùng nên cũng không gồm' : ''}).` : ''}</div>`;
}

async function charts2(n, alive) {
    if (!n.available) return;
    // Không có số thì báo ngay, không chờ tải thư viện biểu đồ.
    const hasDay = n.by_day.some((r) => r.slips), hasMonth = n.by_month.some((r) => r.slips);
    if (!hasDay) fill('nt-day-wrap', emptyState({ icon: '📭', title: 'Tháng này chưa nhập thành phẩm nào' }));
    if (!hasMonth) fill('nt-month-wrap', emptyState({ icon: '📭', title: 'Chưa có phiếu nhập trong 12 tháng' }));
    if (!hasDay && !hasMonth) return;
    const Chart = await loadChartLib();
    if (!alive()) return;
    // Mỗi biểu đồ tự chọn: cả dãy cùng một đơn vị → theo số lượng; lẫn đơn vị → theo thùng (không cộng hộp với kg).
    const mk = (id, labels, rows, color) => {
        const el = document.getElementById(id);
        if (!el) return;
        const u = chartUnit(rows, n.total.uom || BOX);
        const unit = u || 'thùng';
        const val = (r) => (u ? r.qty : r.cartons);
        charts.add(new Chart(el, {
            type: 'bar',
            data: { labels, datasets: [{ label: `Nhập kho (${unit})`, data: rows.map(val), backgroundColor: color, borderWidth: 0,
                borderRadius: 4, maxBarThickness: 26 }] },
            options: { maintainAspectRatio: false, plugins: { legend: { display: false },
                tooltip: { callbacks: { label: (c) => `${qn(c.raw)} ${unit} · ${fmtMoney(rows[c.dataIndex].value)}`,
                    // Vẽ theo thùng: thùng không gồm mã chưa khai quy cách — nói rõ phần thiếu của đúng cột đó.
                    afterLabel: (c) => (!u && rows[c.dataIndex].items_without_carton_factor ? `chưa gồm ${noCartonText(rows[c.dataIndex])}` : '') } } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { ticks: { autoSkip: true, maxRotation: 0 } } } },
        }));
    };
    if (hasDay) mk('nt-day-chart', n.by_day.map((r) => fmtDate(r.date, true).slice(0, 2)), n.by_day, '#7c3aed');
    if (hasMonth) mk('nt-month-chart', n.by_month.map((r) => monthLabel(r.month)), n.by_month, '#10b981');
}

// ─── Hàng đợi ────────────────────────────────────────────────────────────────
function choHtml(q, sx) {
    if (!q.available) return off('phiếu nhập thành phẩm', q, sx);
    if (!q.count) return emptyState({ icon: '✅', title: 'Không có phiếu nào chờ duyệt' });
    return `${dataTable({ rows: q.rows, sortKey: 'age_days', pageSize: 8,
        columns: [
            { key: 'name', label: 'Phiếu', align: 'left', render: (r) => `${escapeHtml(r.name)}${r.tet ? ' <span class="bc-badge bc-badge-warning">Tết</span>' : ''}` },
            { key: 'age_days', label: 'Chờ', render: (r) => `<span class="${r.age_days > 2 ? 'bc-txt-danger' : ''}">${fmtNum(r.age_days)} ngày</span>` },
            { key: 'qty', label: 'Số lượng', render: (r) => `${qu(r.qty, r.uom)}${r.da_dem ? '' : ' <span class="bc-muted bc-text-sm">(chưa đếm)</span>'}` },
            { key: 'no_bom_qty', label: 'Sẽ nợ BOM', render: (r) => (r.no_bom_qty ? `<b class="bc-txt-warning">${qn(r.no_bom_qty)}</b>` : qn(r.no_bom_qty)) },
        ] })}
        <div class="bc-note">Hàng trên phiếu nháp CHƯA vào sổ kho. Tuổi tính từ ngày lập phiếu; phiếu chưa đếm lấy số lập phiếu.
            "Sẽ nợ BOM" = mã chưa có định mức đang dùng — duyệt sẽ nhập kho mà chưa trừ nguyên liệu.</div>`;
}

function vaoHopHtml(v, sx) {
    if (!v.available) return off('bảng vào hộp', v, sx);
    const other = v.rows.filter((r) => r.khac_dvt);
    return `${kpiGrid([
        { label: 'Hộp chưa nhập kho', value: qn(v.qty), sub: `${fmtNum(v.items)} mã` },
        { label: 'Quy ra thùng', value: ct(v.cartons), sub: noCarton(v) },
    ], 2)}
        <div class="bc-mt-3">${dataTable({ rows: v.rows.filter((r) => !r.khac_dvt), sortKey: 'qty', pageSize: 8,
            emptyMessage: 'Hàng đã vào hộp đều đã nhập kho',
            columns: [
                { key: 'short_name', label: 'Thành phẩm', align: 'left', render: (r) => escapeHtml(r.short_name) },
                { key: 'qty', label: 'Hộp', render: (r) => qn(r.qty) },
                { key: 'cartons', label: 'Thùng', render: (r) => (r.cartons ? ct(r.cartons) : '<span class="bc-muted">—</span>') },
            ] })}</div>
        ${other.length ? `<div class="bc-note">Mã không tính bằng hộp (không cộng vào tổng): ${other.map((r) =>
            `${escapeHtml(r.short_name)} ${qn(r.qty)}`).join(', ')}.</div>` : ''}
        <div class="bc-note">Đã vào hộp từ ${escapeHtml(fmtDate(v.from))} đến ${escapeHtml(fmtDate(v.to))} trừ phần thủ kho đã nhận và phần
            đã nằm trên phiếu nháp hàng Tết.</div>`;
}

// ─── Giá vốn chưa thật ───────────────────────────────────────────────────────
function noBomHtml(b, sx) {
    if (!b.available) return off('sổ nợ BOM', b, sx);
    if (!b.rows) return emptyState({ icon: '✅', title: 'Không còn nợ BOM nào đang mở' });
    const size = (x) => (b.qty === null ? x.rows : x.qty);  // độ dài thanh theo số lượng (lẫn đơn vị → theo số dòng)
    const maxQ = Math.max(1e-9, ...b.buckets.map(size));
    const cls = { '0-7': 'bc-ok', '8-30': 'bc-alt', '>30': '' };
    return `${kpiGrid([
        { label: 'Đang nợ', value: qu(b.qty, b.uom), sub: `${fmtNum(b.items)} mã · ${fmtNum(b.rows)} dòng${b.cartons ? ` · ${ct(b.cartons)} thùng` : ''}${
            b.items_without_carton_factor ? ` + ${noCarton(b)}` : ''}` },
        { label: 'Giá tạm lúc nhập', value: money(b.value_tam), sub: 'giá vốn đang ghi sổ cho số hàng này' },
        { label: 'Nhập với giá 0', value: qu(b.qty_gia_0, b.uom), cls: b.qty_gia_0 ? 'bc-txt-danger' : '', sub: `${fmtNum(b.rows_gia_0)} dòng` },
        { label: 'Xử lý được ngay', value: `${fmtNum(b.xu_ly_ngay.items)} mã`, cls: b.xu_ly_ngay.items ? 'bc-txt-success' : '',
            sub: `${qu(b.xu_ly_ngay.qty, b.uom)} — mã đã có định mức` },
    ], 4)}
        <div class="bc-rank-list bc-mt-3" id="nt-buckets">${b.buckets.map((x) => `<div class="bc-rank-row">
            <div class="bc-rank-no">${x.key === '>30' ? '⛔' : x.key === '8-30' ? '⏰' : '🕒'}</div>
            <div style="min-width:0"><div class="bc-rank-name">Nợ ${escapeHtml(x.label)}</div>
                <div class="bc-rank-bars"><div class="bc-rank-bar"><div class="bc-progress ${cls[x.key]}"><span style="width:${Math.round(size(x) / maxQ * 100)}%"></span></div>
                <b>${qu(x.qty, b.uom)}</b></div></div>
                <div class="bc-muted bc-text-sm">${fmtNum(x.rows)} dòng</div></div></div>`).join('')}</div>
        <div class="bc-mt-3">${dataTable({ rows: b.list, pageSize: 8,
            columns: [
                { key: 'short_name', label: 'Thành phẩm', align: 'left', render: (r) => `${escapeHtml(r.short_name)}${r.co_bom
                    ? ' <span class="bc-badge bc-badge-success">Có BOM</span>' : ''}` },
                { key: 'qty', label: 'Số lượng', render: (r) => qu(r.qty, r.uom) },
                { key: 'value_tam', label: 'Giá tạm', render: (r) => money(r.value_tam) },
                { key: 'qty_gia_0', label: 'Giá 0', render: (r) => (r.qty_gia_0 ? `<b class="bc-txt-danger">${qn(r.qty_gia_0)}</b>` : '0') },
                { key: 'age_days', label: 'Nợ cũ nhất', render: (r) => `<span class="${r.lau ? 'bc-txt-danger' : ''}">${fmtNum(r.age_days)} ngày</span>` },
            ] })}</div>
        <div class="bc-note">Nợ BOM = thành phẩm đã nhập kho khi mã chưa có định mức nên nguyên liệu chưa trừ. Khi hạch toán bù, nguyên liệu
            trừ vào ngày bù; giá vốn lô thành phẩm giữ nguyên giá tạm lúc nhập (giá 0 thì bán ra giá vốn 0).</div>`;
}

function nvlHtml(r, sx) {
    if (!r.available) return off('sổ nợ BOM', r, sx);
    const cu = r.chua_uoc_tinh;
    return `${kpiGrid([
        { label: 'Nguyên liệu còn treo (ước tính)', value: money(r.value), sub: `${fmtNum(r.n_rm)} nguyên liệu` },
        { label: 'Chưa ước tính được', value: `${fmtNum(cu.items)} mã`, sub: cu.items ? `${qu(cu.qty, cu.uom)} nợ chưa có định mức` : '',
            cls: cu.items ? 'bc-txt-warning' : '' },
    ], 2)}
        <div class="bc-mt-3" id="nt-nvl-list">${dataTable({ rows: r.list, pageSize: 8, emptyMessage: 'Không có nợ nào bung được theo định mức',
            // Danh sách xếp theo giá trị: cột Giá trị + Số lượng ngay sau tên (điện thoại thấy ngay), kho xuống dòng phụ dưới tên.
            columns: [
                { key: 'short_name', label: 'Nguyên liệu', align: 'left', render: (x) => `${escapeHtml(x.short_name)}<div class="bc-muted bc-text-sm">${escapeHtml(x.warehouse_label || '—')}</div>` },
                { key: 'value', label: 'Giá trị', render: (x) => (x.rate_source ? money(x.value)
                    : '<span class="bc-muted bc-text-sm nt-no-rate">chưa có <br>giá vốn</span>') },
                { key: 'qty', label: 'Số lượng', render: (x) => qu(x.qty, x.uom) },
            ] })}</div>
        <div class="bc-note">Nguyên liệu đáng lẽ đã trừ cho phần nợ BOM nhưng vẫn nằm trên sổ (kiểm kê sẽ thấy thiếu đúng phần này). Bung định mức
            hiện tại một cấp × giá vốn đang ghi sổ; chưa có giá vốn thì để trống, không lấy giá mua.</div>`;
}

function gv0Html(g, meta) {
    if (!g.available) return off('số liệu giá vốn', g, meta.sx);
    const t = g.ton;
    // Khối nằm dưới tiêu đề "… tình hình hôm nay" → chỉ số HÔM NAY. Số nhập giá 0 của THÁNG CHỌN chỉ ở thẻ "Nhập giá vốn 0
    // trong tháng" của hàng tháng phía trên (không lặp ở đây, để không trộn hai mốc dưới một tiêu đề).
    return `${kpiGrid([
        { label: 'Đang tồn giá vốn 0 (hôm nay)', value: qu(t.qty, t.uom), sub: `${fmtNum(t.items)} mã · ${fmtNum(t.rows)} dòng kho`, cls: t.rows ? 'bc-txt-danger' : '' },
        { label: 'Quy ra thùng', value: ct(t.cartons), sub: noCarton(t) },
    ], 2)}
        <div class="bc-mt-3" id="nt-gv0-list">${dataTable({ rows: t.list, sortKey: 'qty', pageSize: 8, emptyMessage: 'Không có thành phẩm nào tồn với giá vốn 0',
            // Kho xuống dòng phụ dưới tên: cột Tồn (khoá sắp xếp) thấy ngay ở 390px; cùng mã ở hai kho không trông như dòng lặp.
            columns: [
                { key: 'short_name', label: 'Thành phẩm', align: 'left', render: (x) => `${escapeHtml(x.short_name)}<div class="bc-muted bc-text-sm">${escapeHtml(x.warehouse_label || '')}</div>` },
                { key: 'qty', label: 'Tồn', render: (x) => qu(x.qty, x.uom) },
                { key: 'cartons', label: 'Thùng', render: (x) => (x.cartons ? ct(x.cartons) : '<span class="bc-muted">—</span>') },
            ] })}</div>
        <div class="bc-note">Thành phẩm ở kho bán được có tồn mà giá vốn bằng 0 — bán ra sẽ ghi giá vốn 0, lãi bị thổi lên. Mã vừa có lô giá 0
            vừa có lô có giá thì giá vốn bị kéo thấp chứ không về 0, nên xem thêm thẻ "Nhập giá vốn 0 trong tháng" ở đầu trang.</div>`;
}

/** Ô chọn tháng. Dựng lại sau mỗi lượt tải: trả focus về ô nếu người dùng đang ở đó. */
function bindPicker(cur, extra, isCurrent) {
    const refocus = document.activeElement?.id === 'nt-thang';
    fill('nt-filter', `${monthOptions(cur)}${extra}`);
    const sel = document.getElementById('nt-thang');
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
        const d = await api.kho.nhapTp(thang || undefined);
        if (!alive()) return;
        if (!d || !d.available) {
            fill('nt-kpis', emptyState({ icon: '🏭', title: 'Chưa có số liệu nhập thành phẩm', message: 'Màn này chưa sẵn sàng trên hệ thống.' }));
            SECTIONS.slice(1).forEach((id) => fill(id, ''));
            return;
        }
        if (chon) state.thang = d.meta.thang;
        bindPicker(d.meta.thang, `<span class="bc-text-sm" id="nt-range">Từ ${escapeHtml(fmtDate(d.meta.from))} đến ${escapeHtml(fmtDate(d.meta.to))}</span>`, isCurrent);
        fill('nt-kpis', `${d.meta.sx ? '' : '<div class="bc-alert">Hệ thống sản xuất (app sx) chưa cài: chỉ có phần thành phẩm chưa có giá vốn.</div>'}${kpisHtml(d)}`);
        fill('nt-nhap', nhapHtml(d.nhap, d.meta));
        fill('nt-month', monthHtml(d.nhap, d.meta));
        fill('nt-cho', choHtml(d.cho_duyet, d.meta.sx));
        fill('nt-vaohop', vaoHopHtml(d.vao_hop, d.meta.sx));
        fill('nt-nobom', noBomHtml(d.no_bom, d.meta.sx));
        fill('nt-nvl', nvlHtml(d.nvl_treo, d.meta.sx));
        fill('nt-gv0', gv0Html(d.gia_von_0, d.meta));
        // Biểu đồ lỗi (CDN chặn / mạng yếu) chỉ thay khung biểu đồ, không xoá số đã hiện.
        try { await charts2(d.nhap, alive); } catch (e) {
            if (alive()) {
                fill('nt-day-wrap', emptyState({ title: 'Không tải được biểu đồ', message: e?.message || '' }));
                fill('nt-month-wrap', '');
            }
        }
    } catch (err) {
        if (!alive()) return;
        bindPicker(state.thang, '', isCurrent);  // ô chọn tháng vẫn còn — chọn lại được, không kẹt ở màn lỗi
        fill('nt-kpis', errorState(err));
        SECTIONS.slice(1).forEach((id) => fill(id, ''));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Nhập TP & giá vốn</div>
                <div class="bc-view-banner-sub">Thành phẩm nhập kho theo phiếu sản xuất, phiếu chờ duyệt, nợ BOM và hàng chưa có giá vốn</div></div>
            <span class="bc-view-banner-badge">🏭 Kho</span>
        </div>
        <div class="bc-filter-bar" id="nt-filter"></div>
        <div id="nt-kpis">${skeletonGrid(4, 128)}</div>
        <div class="bc-section-title">Thành phẩm nhập kho trong tháng (theo ngày)</div>
        <div class="bc-card"><div id="nt-nhap">${skeleton(220)}</div></div>
        <div class="bc-section-title">12 tháng gần nhất</div>
        <div class="bc-card"><div id="nt-month">${skeleton(200)}</div></div>
        <div class="bc-section-title">Hàng đợi — tình hình hôm nay</div>
        <div class="bc-grid bc-grid-even">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Phiếu nhập chờ thủ kho duyệt</div></div><div id="nt-cho">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Đã vào hộp, chưa nhập kho</div></div><div id="nt-vaohop">${skeleton(160)}</div></div>
        </div>
        <div class="bc-section-title">Giá vốn chưa thật — tình hình hôm nay</div>
        <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Nợ BOM đang mở (giá vốn tạm)</div></div><div id="nt-nobom">${skeleton(200)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Nguyên liệu còn treo trên sổ</div></div><div id="nt-nvl">${skeleton(160)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Thành phẩm chưa có giá vốn</div></div><div id="nt-gv0">${skeleton(160)}</div></div>
        </div>
        <div class="bc-note bc-mt-3">ⓘ Số lượng theo đơn vị kho của mã (thường là hộp); thùng theo quy cách khai trên mã hàng. Giá trị theo giá vốn,
            chưa VAT. Nhập kho tính theo ngày nhận trên phiếu nhập thành phẩm đã được thủ kho duyệt. Phiếu chờ duyệt, nợ BOM, hàng đã vào hộp
            và tồn giá vốn 0 là số tại hôm nay, không theo tháng chọn.</div>`;
    await load(isCurrent);
}
