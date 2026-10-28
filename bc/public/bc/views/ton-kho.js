// #/ton-kho — Tồn kho: giá trị tồn bây giờ (theo khu vực kho, nhóm hàng, mã lớn nhất), xu hướng 12 tháng + nhập–xuất–tồn,
// số ngày tồn kho, hàng chậm luân chuyển / tồn chết, tồn hàng Tết, sức khoẻ số liệu (thu gọn).
// Hai lượt gọi song song: bc.api.kho_ton.get_overview (Bin + ba lượt quét cả sổ cache theo ngày) và get_trend (quét cả sổ
// kho, cache 6 giờ). Lần đầu trong ngày (hoặc Làm mới) cả hai đều quét sổ; các lần sau overview chỉ đọc Bin.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum, fmtPct } from '../lib/format.js';
import { loadChartLib, chartRegistry } from '../lib/chart.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { tabs, bindTabs } from '../components/tabs.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const charts = chartRegistry();
const state = { ov: null, tr: null, nxtMonth: '', nxtGroup: 'all', slowTab: 'tp', healthOpen: false };
let seq = 0;  // lượt tải mới nhất — rời màn / Làm mới giữa chừng thì lượt cũ về sau không vẽ đè
const OV_IDS = ['tk-kpis', 'tk-role', 'tk-group', 'tk-top', 'tk-doi', 'tk-slow', 'tk-tet', 'tk-health'];
const TR_IDS = ['tk-trend', 'tk-nxt'];
const NUM1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
const BUCKET_LABELS = { '0-30': '0–30 ngày', '31-90': '31–90 ngày', '91-180': '91–180 ngày', '>180': 'Trên 180 ngày' };
const GROUP_COLORS = { tet: '#ec4899', traditional: '#7c3aed', other: '#f59e0b' };

function money(v) { return v === null || v === undefined ? '<span class="bc-muted">—</span>' : `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }
function num1(v) { return v === null || v === undefined ? '—' : NUM1.format(v); }
// Khối tắt: lỗi máy chủ (safe_block → error: true, đã ghi Error Log) nói rõ là lỗi để người xem báo lại — khác thiếu dữ liệu.
function off(b, what) {
    return b && b.error
        ? `<div class="bc-muted bc-text-sm">Không tải được ${escapeHtml(what)} lúc này (lỗi hệ thống — đã ghi nhật ký, hãy báo quản trị).</div>`
        : `<div class="bc-muted bc-text-sm">Chưa tính được ${escapeHtml(what)} (thiếu dữ liệu trên hệ thống).</div>`;
}
function monthLabel(m) { return m ? `T${Number(m.slice(5))}/${m.slice(0, 4)}` : ''; }
function qtyText(q, uom) { return q === null || q === undefined ? '—' : `${fmtNum(q)} ${escapeHtml((uom || '').toLowerCase())}`; }
function qtyLabel(uom) { return !uom || uom.toLowerCase() === 'hộp' ? 'Số hộp' : 'Số lượng'; }
// "Chưa khai quy cách thùng": MỘT cơ sở trên cả màn = mã không hệ số thùng có tồn ròng > 0 (boxes_without_carton_in_stock,
// cùng số với dải sức khoẻ), kèm ĐƠN VỊ của khối (không mặc định "hộp").
function noFactor(o) { const n = o?.boxes_without_carton_in_stock ?? o?.boxes_without_carton_factor; return n > 0 ? n : 0; }
function cartonText(o) {
    if (!o || o.cartons === null || o.cartons === undefined) return '';
    const n = noFactor(o);
    const miss = n ? `${fmtNum(n)} ${escapeHtml((o.uom || '').toLowerCase())} chưa khai quy cách thùng` : '';
    if (!o.cartons) return miss;
    return `${num1(o.cartons)} thùng${miss ? ` + ${miss}` : ''}`;
}
function groupLabel(key) {
    const g = state.ov?.meta?.groups || {};
    return key === 'all' ? 'Tất cả' : (g[key] || { tet: 'Hàng Tết', traditional: 'Hàng truyền thống', other: 'Khác' }[key]);
}

// ─── Thẻ KPI ───────────────────────────────────────────────────────────────
function kpisHtml(d) {
    const v = d.value;
    if (!v.available) return off(v, 'giá trị tồn kho');
    const t = v.totals, role = Object.fromEntries(v.by_role.map((r) => [r.key, r]));
    const kb = role.khong_ban || { roles: [] };
    const tp = v.tp;
    // Tiêu đề: thùng nếu quy được (> 0), không thì số lượng (chưa khai quy cách thùng); lẫn đơn vị → chỉ tiền.
    const tpVal = tp.qty === null ? money(tp.value) : tp.cartons ? `${num1(tp.cartons)} thùng` : qtyText(tp.qty, tp.uom);
    const tpRows = tp.qty === null ? (tp.items ? [['Nhiều đơn vị', 'chỉ cộng tiền']] : [['Số mã còn hàng', '0']])
        : tp.cartons ? [[qtyLabel(tp.uom), qtyText(tp.qty, tp.uom)], ['Giá trị', money(tp.value)]] : [['Giá trị', money(tp.value)]];
    const tpMiss = tp.qty === null ? 0 : noFactor(tp);
    // Chia theo KHO (không theo hàng bán được hay không): kho trả về / cách ly của cài đặt sản xuất (hoặc kho hàng lỗi).
    const known = kb.configured !== false;
    const kbVal = known ? `<span class="${t.value_unsellable ? 'bc-txt-danger' : ''}">${money(t.value_unsellable)}</span>`
        : '<span class="bc-muted">—</span>';
    const kbRows = known ? kb.roles.map((r) => [r.label, r.configured === false ? '<span class="bc-muted">chưa khai kho</span>' : money(r.value)])
        : [['Chưa xác định kho', 'trả về / cách ly']];
    return `<div class="bc-grid bc-grid-4">
        ${statCard({ label: 'Tổng giá trị tồn', icon: '📦', value: money(t.value), rows: [
            ['Kho thành phẩm', money(role.tp?.value)], ['Cửa hàng', money(role.cua_hang?.value)],
            ['Kho sản xuất', money(role.san_xuat?.value)]] })}
        ${statCard({ label: 'Ngoài kho trả về & cách ly', icon: '🏬', value: money(t.value_sellable), rows: [
            ['Tỷ lệ trên tổng', fmtPct(t.value ? t.value_sellable / t.value * 100 : null)], ['Đang đi đường', money(t.value_transit)],
            ['Số mã còn hàng', fmtNum(t.items_in_stock)]] })}
        ${statCard({ label: 'Kho trả về & cách ly', icon: '⛔', tone: known ? 'danger' : '', value: kbVal, rows: kbRows })}
        ${statCard({ label: 'Thành phẩm ngoài kho trả về & cách ly', icon: '🧁', tone: 'warning', value: tpVal, rows: [...tpRows,
            ...(tpMiss ? [['Chưa khai quy cách thùng', `${fmtNum(tpMiss)} ${escapeHtml((tp.uom || '').toLowerCase())} · ${fmtNum(tp.items_without_carton_in_stock ?? tp.items_without_carton_factor)} mã`]] : [])] })}
    </div>
    <div class="bc-note" id="tk-kpi-note">Hai thẻ giữa chia theo kho, không theo hàng còn bán được: hàng hết hạn, lô đang thu hồi chưa chuyển
        sang kho trả về / cách ly vẫn tính ở "Ngoài kho trả về & cách ly" (gồm cả nguyên liệu, bán thành phẩm). Hàng không bán được
        (hết hạn, thu hồi, trả về) xem ở trang Hạn dùng & tồn âm.${known ? '' : ' Chưa xác định được kho trả về / cách ly (chưa khai trong cài đặt sản xuất) nên chưa tách được phần này.'}</div>`;
}

// ─── Khu vực kho / nhóm hàng / mã lớn ──────────────────────────────────────
function roleHtml(v) {
    if (!v.available) return off(v, 'giá trị theo kho');
    const rows = v.by_role.filter((r) => r.value || r.warehouses.length);
    if (!rows.length) return emptyState({ icon: '📭', title: 'Chưa có hàng tồn' });
    const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
    const k = v.kho_tp;
    return `<div class="bc-rank-list">${rows.map((r, i) => `
        <div class="bc-rank-row">
            <div class="bc-rank-no">${i + 1}</div>
            <div style="min-width:0">
                <div class="bc-rank-name">${escapeHtml(r.label)} <span class="bc-muted bc-text-sm">${fmtPct(r.pct)}</span></div>
                <div class="bc-progress ${r.sellable ? '' : 'bc-alt'}"><span style="width:${Math.max(0, r.value) / max * 100}%"></span></div>
                <div class="bc-rank-bars">${r.warehouses.map((w) => `<div class="bc-rank-bar"><span>${escapeHtml(w.label)}${w.disabled
                    ? ' <span class="bc-badge bc-badge-muted">ngừng dùng</span>' : ''}</span><b>${money(w.value)}</b></div>`).join('')}</div>
            </div>
            <b>${money(r.value)}</b>
        </div>`).join('')}</div>
        ${k && !k.same ? `<div class="bc-note" id="tk-role-khotp">Màn Thời gian thực chỉ tính kho "${escapeHtml(k.label)}": ${money(k.value)}.
            Khu vực "Kho thành phẩm" ở đây theo cả cài đặt sản xuất nên khác số đó.</div>` : ''}
        <div class="bc-note">"Kho trả về & cách ly" = kho hàng trả về và kho cách ly (hàng hết hạn / thu hồi còn ở kho khác: xem trang
            Hạn dùng & tồn âm). Cửa hàng: phiếu bán lẻ chỉ trừ kho lúc chốt ca.</div>`;
}

function groupHtml(v) {
    if (!v.available) return off(v, 'giá trị theo nhóm hàng');
    const other = v.other_split.filter((x) => x.value);
    const max = Math.max(...v.by_group.map((r) => Math.abs(r.value)), 1);
    return `<div class="bc-rank-list">${v.by_group.map((r, i) => `
        <div class="bc-rank-row">
            <div class="bc-rank-no">${i + 1}</div>
            <div style="min-width:0">
                <div class="bc-rank-name">${escapeHtml(r.label)}</div>
                <div class="bc-progress"><span style="width:${Math.max(0, r.value) / max * 100}%"></span></div>
                <div class="bc-rank-bars">
                    <div class="bc-rank-bar tk-grp-all"><span>Mọi kho: ${!r.items ? 'chưa có hàng' : r.qty === null ? 'nhiều đơn vị — chỉ cộng tiền'
                        : `${qtyText(r.qty, r.uom)}${cartonText(r) ? ` · ${cartonText(r)}` : ''}`}</span><b></b></div>
                    <div class="bc-rank-bar"><span>Ngoài kho trả về & cách ly</span><b>${money(r.value_sellable)}</b></div>
                    ${r.key === 'other' && v.sx_nhom ? other.map((x) => `<div class="bc-rank-bar"><span>· ${escapeHtml(x.label)}</span><b>${money(x.value)}</b></div>`).join('') : ''}
                </div>
            </div>
            <b>${money(r.value)}</b>
        </div>`).join('')}</div>
        <div class="bc-note">Nhóm tính cả nhóm con (vd hộp quà Tết thuộc Hàng Tết). Số lượng ("Mọi kho") và giá trị bên phải gồm mọi
            kho của công ty, kể cả kho trả về / cách ly.</div>`;
}

function topHtml(v) {
    if (!v.available) return off(v, 'mã hàng');
    const g = state.ov.meta.groups || {};
    return dataTable({ rows: v.top, sortKey: 'value', emptyMessage: 'Chưa có hàng tồn',
        columns: [
            { key: 'short_name', label: 'Mã hàng', align: 'left', render: (r) => `<span title="${escapeHtml(r.item_code)}">${escapeHtml(r.short_name)}</span>` },
            { key: 'value', label: 'Giá trị', render: (r) => money(r.value) },
            { key: 'qty', label: 'Số lượng', render: (r) => `${qtyText(r.qty, r.uom)}${r.cartons !== null ? ` <span class="bc-muted">· ${num1(r.cartons)} thùng</span>` : ''}` },
            { key: 'group_key', label: 'Nhóm', align: 'left', render: (r) => escapeHtml(g[r.group_key] || r.group_key) },
        ] });
}

// ─── Số ngày tồn kho ───────────────────────────────────────────────────────
const PHASE_TEXT = { ban: 'đang mùa bán Tết', chuan_bi: 'đang chuẩn bị mùa Tết', sau_mua: 'đã qua mùa Tết' };

function doiHtml(o) {
    if (!o.available) return off(o, 'số ngày tồn kho');
    const tr = o.traditional, te = o.tet;
    const g = state.ov.meta.groups || {};
    const days = (x) => (x.days === null ? '<span class="bc-muted">—</span>' : `${fmtNum(x.days)} ngày`);
    return `${kpiGrid([
        { label: g.traditional || 'Hàng truyền thống', value: days(tr),
            sub: tr.no_sales ? `Không bán trong ${fmtNum(o.window_days)} ngày` : `Tồn ${fmtMoney(tr.value)} · giá vốn bán ${fmtMoney(tr.cogs)}` },
        te.applicable
            ? { label: g.tet || 'Hàng Tết', value: days(te), sub: te.no_sales ? `Không bán trong ${fmtNum(o.window_days)} ngày`
                : `Tồn ${fmtMoney(te.value)} · giá vốn bán ${fmtMoney(te.cogs)}` }
            : te.phase
                ? { label: g.tet || 'Hàng Tết', value: '<span class="bc-muted">Ngoài mùa bán</span>',
                    sub: `Hiện ${PHASE_TEXT[te.phase]} — xem tồn hàng Tết bên dưới` }
                : { label: g.tet || 'Hàng Tết', value: '<span class="bc-muted">—</span>',
                    sub: 'Chưa khai ngày Tết trong cài đặt nên chưa biết đang mùa nào' },
    ], 2)}
        <div class="bc-note">Số ngày tồn = giá trị tồn ngoài kho trả về & cách ly ÷ giá vốn hàng xuất bán bình quân một ngày trong
            ${fmtNum(o.window_days)} ngày gần nhất (${escapeHtml(fmtDate(o.from))} – ${escapeHtml(fmtDate(o.to))}). Hàng Tết chỉ tính trong mùa bán.</div>`;
}

// ─── Hàng chậm / tồn chết ──────────────────────────────────────────────────
const SLOW_SCOPE = { tp: 'thành phẩm', vat_tu: 'nguyên liệu, bao bì, bán thành phẩm', total: 'mọi mã' };

function slowBody(s, key) {
    const x = s[key];
    if (!x) return '';
    const status = (r) => (r.status === 'dead' ? '<span class="bc-badge bc-badge-danger">Tồn chết</span>'
        : r.status === 'slow' ? '<span class="bc-badge bc-badge-warning">Chậm</span>' : '');
    const max = Math.max(x.value, 1);
    return `${kpiGrid([
        { label: `Chậm (quá ${fmtNum(s.slow_days)} ngày)`, value: money(x.slow_value), cls: x.slow_value ? 'bc-txt-warning' : '',
            sub: `${fmtNum(x.slow_items)} mã · ${fmtPct(x.slow_pct)} giá trị tồn · gồm tồn chết` },
        { label: `Tồn chết (quá ${fmtNum(s.dead_days)} ngày)`, value: money(x.dead_value), cls: x.dead_value ? 'bc-txt-danger' : '',
            sub: `${fmtNum(x.dead_items)} mã · ${fmtPct(x.dead_pct)} giá trị tồn` },
        { label: 'Chưa từng xuất', value: money(x.never_value), sub: `${fmtNum(x.never_items)} mã` },
    ], 3)}
        <div class="bc-section-title">Giá trị theo số ngày chưa xuất (${fmtNum(x.items)} mã, ${money(x.value)})</div>
        <div class="bc-rank-bars">${x.buckets.map((b) => `<div class="bc-rank-bar"><div><span class="bc-text-sm">${escapeHtml(BUCKET_LABELS[b.key] || b.key)}
            · ${fmtNum(b.items)} mã</span><div class="bc-progress ${b.key === '>180' || b.key === '91-180' ? 'bc-alt' : 'bc-ok'}"><span style="width:${Math.max(0, b.value) / max * 100}%"></span></div></div>
            <b>${money(b.value)}</b></div>`).join('')}</div>
        <div class="bc-section-title">Mã chậm / tồn chết lớn nhất</div>
        ${dataTable({ rows: x.top, sortKey: 'value', emptyMessage: 'Không có mã chậm luân chuyển',
            columns: [
                // Điện thoại chỉ thấy cột đầu + Giá trị: số ngày chưa xuất và tình trạng nằm ngay dưới tên mã.
                { key: 'short_name', label: 'Mã hàng', align: 'left', render: (r) => `<span title="${escapeHtml(r.item_code)}">${escapeHtml(r.short_name)}</span>
                    <div class="bc-muted bc-text-sm tk-slow-sub">${fmtNum(r.idle_days)} ngày · ${r.status === 'dead' ? '<span class="bc-txt-danger">Tồn chết</span>'
                        : r.status === 'slow' ? '<span class="bc-txt-warning">Chậm</span>' : 'Bình thường'}</div>` },
                { key: 'value', label: 'Giá trị', render: (r) => money(r.value) },
                { key: 'qty', label: 'Số lượng', render: (r) => `${qtyText(r.qty, r.uom)}${r.cartons !== null ? ` <span class="bc-muted">· ${num1(r.cartons)} thùng</span>` : ''}` },
                { key: 'idle_days', label: 'Ngày chưa xuất', render: (r) => fmtNum(r.idle_days) },
                { key: 'last_out', label: 'Lần xuất cuối', render: (r) => (r.never ? '<span class="bc-muted">chưa từng xuất</span>' : escapeHtml(fmtDate(r.last_out))) },
                { key: 'status', label: 'Tình trạng', sortable: false, align: 'left', render: status },
            ] })}
        <div class="bc-note">% = trên giá trị tồn của ${escapeHtml(SLOW_SCOPE[key] || '')} ngoài kho trả về & cách ly (${money(x.sellable_value)}, gồm cả hàng Tết).</div>
        ${key === 'vat_tu' ? '<div class="bc-note">Bao bì theo mùa (hộp, túi Tết…) ngoài mùa trông như tồn chết — xem cùng kế hoạch sản xuất.</div>' : ''}`;
}

function slowHtml(s) {
    if (!s.available) return off(s, 'hàng chậm luân chuyển');
    return `${tabs([
        { key: 'tp', label: 'Thành phẩm', count: s.tp.items },
        { key: 'vat_tu', label: 'Nguyên liệu, bao bì, BTP', count: s.vat_tu.items },
        { key: 'total', label: 'Tất cả', count: s.total.items },
    ], state.slowTab, 'tk-slow')}
        <div id="tk-slow-body">${slowBody(s, state.slowTab)}</div>
        <div class="bc-note">Ngày chưa xuất = hôm nay − lần xuất cuối (bán, hoặc dùng cho sản xuất); mã chưa từng xuất tính từ lần nhập đầu.
            Không tính trả hàng, chuyển kho, xuất huỷ, kiểm kê. "Chậm" gồm cả tồn chết. Hàng Tết tính riêng bên dưới. Chỉ mã còn hàng ngoài
            kho trả về & cách ly.</div>`;
}

function bindSlow(s) {
    const root = document.getElementById('tk-slow');
    if (!root || !s.available) return;
    bindTabs(root, 'tk-slow', (k) => { state.slowTab = k; fill('tk-slow-body', slowBody(s, k)); });
}

function tetHtml(t) {
    if (!t.available) return off(t, 'tồn hàng Tết');
    const risk = t.phase === 'sau_mua';
    // Số thùng như cartonText: không quy được thùng nào → "—" (không "0 + …"); đơn vị không đóng thùng (cartons null,
    // vd kg) → "—" kèm lời giải thích, không nhắc "chưa khai quy cách thùng" (cùng luật với dải sức khoẻ).
    const unit = escapeHtml((t.uom || '').toLowerCase());
    const miss = noFactor(t) ? `${fmtNum(noFactor(t))} ${unit} chưa khai quy cách thùng` : '';
    const ctSub = t.qty !== null && t.qty !== undefined && t.cartons === null ? `hàng tính theo ${unit}, không quy ra thùng`
        : t.cartons && miss ? `+ ${miss}` : miss;
    return `<div class="bc-card-head"><div class="bc-card-title">${escapeHtml(t.label)}</div>
            <span class="bc-badge ${risk ? 'bc-badge-danger' : t.phase === 'ban' ? 'bc-badge-success' : 'bc-badge-primary'}">${escapeHtml(t.phase
                ? PHASE_TEXT[t.phase] : 'chưa khai ngày Tết')}</span></div>
        ${kpiGrid([
            { label: 'Giá trị', value: money(t.value), cls: risk && t.value ? 'bc-txt-danger' : '' },
            { label: qtyLabel(t.uom), value: qtyText(t.qty, t.uom) },
            { label: 'Số thùng', value: t.cartons ? num1(t.cartons) : '—', sub: ctSub },
        ], 3)}
        ${t.top.length ? `<div class="bc-rank-bars bc-mt-3">${t.top.map((x) => `<div class="bc-rank-bar"><span>${escapeHtml(x.short_name)}
            <span class="bc-muted bc-text-sm">${qtyText(x.qty, x.uom)}${x.cartons !== null ? ` · ${num1(x.cartons)} thùng` : ''}</span></span><b>${money(x.value)}</b></div>`).join('')}</div>` : ''}
        <div class="bc-note">${risk ? 'Hàng Tết còn lại sau mùa — hạn dùng thường 9 tháng, cần kế hoạch xử lý.' : 'Hàng Tết ngoài kho trả về & cách ly.'}</div>`;
}

// ─── Sức khoẻ số liệu ──────────────────────────────────────────────────────
function healthItems(h, trend) {
    const out = [];
    const g = state.ov?.meta?.groups || {};
    if (h.pending_reposts) out.push(`Giá vốn đang được tính lại từ ${fmtDate(h.repost_since)} (${fmtNum(h.pending_reposts)} lượt) — số giá trị có thể còn đổi.`);
    if (h.failed_reposts) {
        out.push(`${fmtNum(h.failed_reposts)} lượt tính lại giá vốn bị lỗi, hệ thống không tự chạy lại (từ ${fmtDate(h.failed_repost_since)}): giá trị
            tồn từ ngày đó có thể sai cho tới khi kế toán chạy lại.`);
    }
    if (trend?.available && trend.future_value) {
        out.push(`Có ${fmtMoney(trend.future_value)} hàng ghi sổ với ngày sau hôm nay: đã có trong tổng tồn, chưa có trong biểu đồ.`);
    }
    if (trend?.available && Math.abs(trend.ledger_bin_diff || 0) >= 1) {
        out.push(`Tổng tồn theo sổ kho lệch ${fmtMoney(trend.ledger_bin_diff)} so với số tồn hiện tại — cần kiểm tra lại sổ kho.`);
    }
    if (h.allow_negative_stock) out.push('Hệ thống đang cho phép xuất kho khi chưa có hàng (tồn âm).');
    if (h.allow_negative_stock_for_batch) out.push('Hệ thống đang cho phép xuất lô khi lô chưa có hàng (lô âm).');
    if (h.pos_unconsolidated) out.push(`${fmtNum(h.pos_unconsolidated)} phiếu bán lẻ cửa hàng chưa chốt ca: cửa hàng thực tế đang ít hàng hơn số trên sổ.`);
    const nr = h.si_no_stock_relief;
    if (nr && nr.count) out.push(`${fmtNum(nr.count)} hoá đơn bán quá ${fmtNum(nr.days)} ngày chưa xuất kho (không có phiếu giao, từ ${fmtDate(nr.oldest)}): hàng chưa trừ khỏi kho.`);
    const tm = h.tp_set_mismatch;
    if (tm && (tm.in_sx_not_group || tm.in_group_not_sx)) {
        out.push(`Danh sách thành phẩm của sản xuất lệch nhóm hàng: ${fmtNum(tm.in_sx_not_group)} mã thành phẩm nằm ngoài nhóm Tết / truyền thống,
            ${fmtNum(tm.in_group_not_sx)} mã trong hai nhóm đó chưa đánh dấu là thành phẩm.`);
    }
    const hc = h.group_has_children || {};
    for (const k of ['tet', 'traditional']) {
        if (hc[k]) out.push(`Nhóm "${g[k] || k}" có nhóm con: trang Kho tính cả nhóm con, các trang Kinh doanh chỉ tính đúng nhóm này.`);
    }
    if (h.company_mismatch) out.push(`Cài đặt sản xuất đang dùng công ty khác (${h.sx_company}).`);
    if (h.kho_tp_mismatch) out.push(`Kho thành phẩm của báo cáo (${h.kho_tp_bc}) khác kho thành phẩm của sản xuất (${h.kho_tp_sx}); khu vực "Kho thành phẩm" tính cả hai.`);
    if (h.items_without_carton_factor) {
        // Theo từng đơn vị kho (không cộng hộp với kg) — cùng số với dòng "Chưa khai quy cách thùng" của thẻ thành phẩm.
        const per = (h.without_carton_by_uom || []).map((u) => `${fmtNum(u.qty)} ${(u.uom || '').toLowerCase()}`);
        out.push(`${fmtNum(h.items_without_carton_factor)} mã thành phẩm còn hàng chưa khai quy cách thùng${per.length ? ` (${per.join(', ')})` : ''}.`);
    }
    if (h.stranded_value_rows) out.push(`${fmtNum(h.stranded_value_rows)} dòng tồn đã hết hàng nhưng còn giá trị (${fmtMoney(h.stranded_value)}) — kế toán cần xử lý chênh lệch.`);
    return out;
}

function healthHtml() {
    const h = state.ov?.health;
    if (h && h.available === false && h.error) return `<div class="bc-card bc-mt-3">${off(h, 'sức khoẻ số liệu')}</div>`;
    if (!h || !h.available) return '';
    const items = healthItems(h, state.tr?.trend);
    return `<details class="bc-card bc-mt-3" id="tk-health-box"${state.healthOpen ? ' open' : ''}>
        <summary style="cursor:pointer" class="bc-flex bc-items-center bc-justify-between bc-gap-2">
            <span class="bc-card-title">Sức khoẻ số liệu</span>
            <span class="bc-badge ${items.length ? 'bc-badge-warning' : 'bc-badge-success'}">${items.length ? `${fmtNum(items.length)} lưu ý` : 'ổn'}</span>
        </summary>
        <div class="bc-mt-3">${items.length ? `<div class="bc-alert">${items.map((x) => `<div>• ${escapeHtml(x)}</div>`).join('')}</div>`
            : '<div class="bc-muted bc-text-sm">Không có điểm nào cần lưu ý.</div>'}
        <div class="bc-note">Những điểm làm số tồn kho trên trang có thể khác thực tế; không phải chỉ tiêu kinh doanh.</div></div>
    </details>`;
}

function paintHealth() {
    fill('tk-health', healthHtml());
    document.getElementById('tk-health-box')?.addEventListener('toggle', (e) => { state.healthOpen = e.target.open; });
}

// ─── Xu hướng + nhập–xuất–tồn ──────────────────────────────────────────────
function trendHtml(t) {
    if (!t.available) return off(t, 'xu hướng giá trị tồn');
    const pts = t.points, last = pts[pts.length - 1], prev = pts[pts.length - 2];
    const empty = pts.every((p) => !p.value);  // sổ trống: lời nhắn thay khung biểu đồ (không để trống 240px)
    const growth = (a, b) => (b ? (a - b) / Math.abs(b) * 100 : null);
    const gtxt = (a, b, what) => { const x = growth(a, b); return x === null ? '' : `${what} ${x >= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(x))}`; };
    return `${kpiGrid([
        { label: `Hôm nay (${fmtDate(last.date, true)})`, value: money(last.value), sub: gtxt(last.value, prev.value, 'So cuối tháng trước') },
        { label: `Cuối ${monthLabel(prev.month)}`, value: money(prev.value) },
        { label: `Đầu năm tài chính (${fmtDate(t.fy_start_date)})`, value: money(t.fy_start_value),
            sub: gtxt(last.value, t.fy_start_value, 'Hôm nay so với đầu năm') },
        { label: `Cùng kỳ năm trước (${fmtDate(t.ly_month_end)})`, value: money(t.ly_month_end_value),
            sub: gtxt(prev.value, t.ly_month_end_value, `Cuối ${monthLabel(prev.month)} so cùng kỳ`) },
    ], 4)}
        ${empty ? '<div class="bc-muted bc-text-sm bc-mt-3" id="tk-chart-empty">Chưa có phát sinh sổ kho trong 12 tháng.</div>'
            : '<div class="bc-chart-wrap bc-mt-3" id="tk-chart-wrap"><canvas id="tk-chart"></canvas></div>'}
        <div class="bc-note">Giá trị cuối mỗi tháng theo sổ kho; điểm cuối là hôm nay (chưa gồm hàng ghi sổ ngày sau hôm nay).
            Nhóm hàng theo nhóm hiện tại của mã.</div>`;
}

async function trendChart(t, alive) {
    if (!t.available || !document.getElementById('tk-chart')) return;  // sổ trống: trendHtml đã thay biểu đồ bằng lời nhắn
    const Chart = await loadChartLib();
    const el = document.getElementById('tk-chart');
    if (!alive() || !el) return;
    const keys = ['traditional', 'tet', 'other'];
    charts.add(new Chart(el, {
        type: 'bar',
        data: { labels: t.points.map((p) => (p.today ? 'Hôm nay' : monthLabel(p.month).replace(/\/20/, '/'))),
            datasets: keys.map((k) => ({ label: groupLabel(k), data: t.points.map((p) => p[k]), backgroundColor: GROUP_COLORS[k],
                borderWidth: 0, maxBarThickness: 34, stack: 'v' })) },
        options: {
            maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtMoney(c.raw)}`,
                footer: (items) => `Tổng: ${fmtMoney(items.reduce((a, x) => a + (x.raw || 0), 0))}` } } },
            scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: (x) => fmtMoney(x) } } },
        },
    }));
}

function nxtTable() {
    const n = state.tr?.nxt;
    if (!n || !n.available) return off(n, 'nhập – xuất – tồn');
    const loai = state.tr.meta.loai || [];
    const pick = n.months.find((m) => m.month === state.nxtMonth) || n.months[n.months.length - 2];
    const cur = n.months[n.months.length - 1];
    const cols = pick.month === cur.month ? [pick] : [pick, cur];
    const g = state.nxtGroup;
    const colKey = (i) => `m${i}`;
    const head = (m) => monthLabel(m.month);
    const wrap = (html) => `<span style="white-space:normal">${html}</span>`;  // nhãn dài xuống dòng: bảng vừa màn 390px
    const rows = [{ label: wrap('<b>Tồn đầu tháng</b>'), ...Object.fromEntries(cols.map((m, i) => [colKey(i), `<b>${money(m.groups[g].opening)}</b>`])) }];
    for (const lo of loai) {
        const vals = cols.map((m) => m.groups[g].flows[lo.key] || 0);
        if (vals.every((x) => !x)) continue;
        rows.push({ label: wrap(`<span title="${escapeHtml(lo.desc || '')}">${escapeHtml(lo.label)}</span>`), ...Object.fromEntries(vals.map((x, i) => [colKey(i),
            `<span class="${x < 0 ? 'bc-down' : x > 0 ? 'bc-up' : ''}">${x > 0 ? '+' : ''}${money(x)}</span>`])) });
    }
    const curNote = cols.some((m) => m.current) ? `<div class="bc-muted bc-text-sm" style="margin-bottom:6px">${escapeHtml(monthLabel(cur.month))}
        tính đến hôm nay ${escapeHtml(fmtDate(cur.to))}.</div>` : '';
    return curNote + dataTable({ rows, pageSize: 20, scrollButtons: false,
        columns: [{ key: 'label', label: 'Khoản', align: 'left', sortable: false, render: (r) => r.label },
            ...cols.map((m, i) => ({ key: colKey(i), label: head(m), sortable: false, render: (r) => r[colKey(i)] }))],
        totalRow: { label: 'Tồn cuối tháng', ...Object.fromEntries(cols.map((m, i) => [colKey(i), money(m.groups[g].closing)])) } });
}

function nxtHtml() {
    const n = state.tr?.nxt;
    if (!n || !n.available) return off(n, 'nhập – xuất – tồn');
    const opts = n.months.slice().reverse().map((m) => `<option value="${escapeHtml(m.month)}" ${m.month === state.nxtMonth ? 'selected' : ''}>${escapeHtml(
        m.current ? `Tháng này (${monthLabel(m.month)})` : `Tháng ${monthLabel(m.month).slice(1)}`)}</option>`).join('');
    return `<div class="bc-filter-bar">
            <label>Tháng<select class="bc-input" id="tk-nxt-thang" aria-label="Tháng">${opts}</select></label>
            <div style="min-width:0;flex:1 1 220px">${tabs(['all', 'traditional', 'tet', 'other'].map((k) => ({ key: k, label: groupLabel(k) })), state.nxtGroup, 'tk-nxt')}</div>
        </div>
        <div id="tk-nxt-table">${nxtTable()}</div>
        <div class="bc-note" id="tk-nxt-note">Theo giá trị (giá vốn, chưa VAT), theo ngày ghi sổ. "Xuất bán (giá vốn)" là hàng đã xuất kho để bán,
            chưa trừ hàng khách trả qua phiếu giảm giá — hàng trả về được nhập kho bằng phiếu riêng (dòng "Nhập khác"). "Kiểm kê sản xuất"
            gồm mọi phiếu của các lần kiểm kê sản xuất, ở mọi kho; trang Kiểm kê tính theo ngày kiểm nên hai số chỉ lệch khi phiếu ghi sổ
            khác tháng với ngày kiểm (phiếu bù ghi lùi ngày). "Kiểm kê bằng phiếu kiểm kho" là phiếu kiểm kho ở mọi kho, không riêng cửa hàng.</div>`;
}

function bindNxt() {
    const sel = document.getElementById('tk-nxt-thang');
    sel?.addEventListener('change', (e) => { state.nxtMonth = e.target.value; fill('tk-nxt-table', nxtTable()); });
    const root = document.getElementById('tk-nxt');
    if (root) bindTabs(root, 'tk-nxt', (k) => { state.nxtGroup = k; fill('tk-nxt-table', nxtTable()); });
}

// ─── Tải ───────────────────────────────────────────────────────────────────
async function loadTrend(alive) {
    try {
        const t = await api.kho.trend();
        if (!alive()) return;
        state.tr = t;
        if (!t.available) { TR_IDS.forEach((id) => fill(id, '')); return; }
        if (!state.nxtMonth || !t.nxt.months?.some((m) => m.month === state.nxtMonth)) state.nxtMonth = t.nxt.default_month || '';
        fill('tk-trend', trendHtml(t.trend));
        fill('tk-nxt', nxtHtml());
        bindNxt();
        paintHealth();
        try { await trendChart(t.trend, alive); } catch (e) {
            if (alive()) fill('tk-chart-wrap', `<div class="bc-muted bc-text-sm">Biểu đồ chưa hiện được (${escapeHtml(e?.message || 'lỗi mạng')}).</div>`);
        }
    } catch (err) {
        if (!alive()) return;
        fill('tk-trend', errorState(err, 'Chưa lấy được xu hướng tồn kho'));
        fill('tk-nxt', '');
    }
}

async function load(isCurrent) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    charts.destroy();
    state.tr = null;
    const trendP = loadTrend(alive);  // chạy song song; overview nhẹ hơn nên thường về trước
    try {
        const d = await api.kho.ton();
        if (!alive()) return;
        state.ov = d;
        if (!d.available) {
            fill('tk-kpis', emptyState({ icon: '📦', title: 'Chưa có số liệu tồn kho',
                message: 'Chưa xác định công ty mặc định (Ketoan Portal Settings / Global Defaults).' }));
            [...OV_IDS.slice(1), ...TR_IDS].forEach((id) => fill(id, ''));
            return;
        }
        fill('tk-asof', `Số đến ${escapeHtml(fmtDate(d.meta.asof))}`);
        fill('tk-kpis', kpisHtml(d));
        fill('tk-role', roleHtml(d.value));
        fill('tk-group', groupHtml(d.value));
        fill('tk-top', topHtml(d.value));
        fill('tk-doi', doiHtml(d.doi));
        fill('tk-slow', slowHtml(d.slow));
        bindSlow(d.slow);
        fill('tk-tet', tetHtml(d.tet_stock));
        paintHealth();
    } catch (err) {
        if (!alive()) return;
        fill('tk-kpis', errorState(err));
        OV_IDS.slice(1).forEach((id) => fill(id, ''));
    }
    await trendP;
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Tồn kho</div>
                <div class="bc-view-banner-sub">Giá trị hàng tồn, xu hướng, số ngày tồn và hàng chậm luân chuyển · <span id="tk-asof"></span></div></div>
            <span class="bc-view-banner-badge">📦 Kho</span>
        </div>
        <div id="tk-kpis">${skeletonGrid(4, 128)}</div>
        <div id="tk-health"></div>
        <div class="bc-section-title">Hàng đang nằm ở đâu</div>
        <div class="bc-grid bc-grid-even">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Theo khu vực kho</div></div><div id="tk-role">${skeleton(220)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Theo nhóm hàng</div></div><div id="tk-group">${skeleton(160)}</div></div>
        </div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Mã hàng tồn nhiều tiền nhất</div></div><div id="tk-top">${skeleton(200)}</div></div>
        <div class="bc-section-title">Xu hướng 12 tháng</div>
        <div class="bc-card"><div id="tk-trend">${skeleton(300)}</div></div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Nhập – xuất – tồn theo tháng</div></div><div id="tk-nxt">${skeleton(260)}</div></div>
        <div class="bc-section-title">Vòng quay hàng</div>
        <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Số ngày tồn kho</div></div><div id="tk-doi">${skeleton(110)}</div></div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Hàng chậm luân chuyển, tồn chết</div></div><div id="tk-slow">${skeleton(260)}</div></div>
        <div class="bc-card bc-mt-3"><div id="tk-tet">${skeleton(140)}</div></div>
        <div class="bc-note bc-mt-3">ⓘ Giá trị theo giá vốn (giá trị tồn trên sổ kho), chưa VAT. Số lượng theo đơn vị kho của từng mã; chỉ cộng số
            lượng khi cùng đơn vị. Tồn hiện tại gồm cả hàng đã ghi sổ với ngày sau hôm nay (như sổ kho ERPNext).</div>`;
    await load(isCurrent);
}
