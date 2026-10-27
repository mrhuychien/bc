// #/attp — An toàn thực phẩm / ISO 22000: 19 mảng đèn đỏ–vàng–xanh (= màn Tổng quan ATTP của Ban
// ISO trong app sx) + 16 chỉ số theo tháng so chỉ tiêu năm (= Báo cáo tháng ATTP).

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum } from '../lib/format.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const DEN = { do: { cls: 'bc-attp-do', label: 'Cần xử lý ngay' }, vang: { cls: 'bc-attp-vang', label: 'Cần theo dõi' },
    xanh: { cls: 'bc-attp-xanh', label: 'Ổn' } };
const NUM1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
const state = { thang: '' };

function val(v, donVi) {
    if (v === null || v === undefined) return '<span class="bc-muted">—</span>';
    return `${NUM1.format(v)}${donVi === '%' ? '%' : ''}`;
}

function cardHtml(t) {
    const den = DEN[t.den] || DEN.xanh;
    const nhac = t.nhac || [];
    return `<div class="bc-attp-card ${den.cls}">
        <div class="bc-attp-head"><span class="bc-attp-dot" title="${den.label}"></span>
            <div><div class="bc-attp-name">${escapeHtml(t.ten)}</div>
                ${t.bieu_mau ? `<div class="bc-attp-form">${escapeHtml(t.bieu_mau)}</div>` : ''}</div></div>
        <div class="bc-attp-num">${escapeHtml(t.so)}<span>${escapeHtml(t.nhan_so)}</span></div>
        ${(t.dong || []).map((x) => `<div class="bc-attp-line">${escapeHtml(x)}</div>`).join('')}
        ${nhac.length ? `<details class="bc-attp-todo"><summary>${fmtNum(nhac.length)} việc cần xử lý</summary>
            ${nhac.map((n) => `<div class="bc-attp-item ${n.muc_do === 'cao' ? 'bc-attp-item-cao' : ''}">
                <b>${escapeHtml(n.tieu_de)}</b>${n.chi_tiet ? `<div>${escapeHtml(n.chi_tiet)}</div>` : ''}</div>`).join('')}
        </details>` : ''}
    </div>`;
}

function overviewHtml(d) {
    const dem = d.dem || {};
    return `${d.du_lieu_mau ? `<div class="bc-alert">${escapeHtml(d.du_lieu_mau)} — số ATTP chưa phải số thật.</div>` : ''}
        ${kpiGrid([
            { label: '🔴 Cần xử lý ngay', value: fmtNum(dem.do), cls: dem.do ? 'bc-txt-danger' : '' },
            { label: '🟡 Cần theo dõi', value: fmtNum(dem.vang), cls: dem.vang ? 'bc-txt-warning' : '' },
            { label: '🟢 Ổn', value: fmtNum(dem.xanh), cls: 'bc-txt-success' },
        ], 3)}
        <div class="bc-attp-grid bc-mt-3">${(d.linh_vuc || []).map(cardHtml).join('')}</div>`;
}

function monthOptions(r) {
    // 12 tháng gần nhất đã bắt đầu (ngày 1 ≤ hôm qua — sx chỉ nhận tháng như vậy), mới nhất trước.
    const now = new Date();
    let y = now.getFullYear(), m = now.getMonth() + 1;
    if (now.getDate() === 1) { m -= 1; if (!m) { m = 12; y -= 1; } }
    const months = [];
    for (let i = 0; i < 12; i++) {
        months.push(`${y}-${String(m).padStart(2, '0')}`);
        m -= 1; if (!m) { m = 12; y -= 1; }
    }
    if (!months.includes(r.thang)) months.unshift(r.thang);
    return `<select class="bc-input" id="attp-thang" aria-label="Tháng báo cáo">${months.map((m) =>
        `<option value="${escapeHtml(m)}" ${m === r.thang ? 'selected' : ''}>Tháng ${escapeHtml(m.slice(5))}/${escapeHtml(m.slice(0, 4))}</option>`).join('')}</select>`;
}

function reportHtml(r) {
    if (!r.available) return emptyState({ icon: '📋', title: 'Chưa có báo cáo ATTP', message: 'Hệ thống sản xuất (app sx) chưa có bảng chỉ tiêu ATTP.' });
    const target = Object.fromEntries((r.chi_tieu || []).map((c) => [c.chi_so, c]));
    const rows = r.bang.map((b) => ({ ...b, target: target[b.ma] }));
    const dat = (ok) => (ok === true ? '<span class="bc-badge bc-badge-success">Đạt</span>'
        : ok === false ? '<span class="bc-badge bc-badge-danger">Chưa đạt</span>' : '<span class="bc-muted">—</span>');
    const main = dataTable({
        rows, pageSize: 20, emptyMessage: 'Chưa có số liệu',
        columns: [
            { key: 'ten', label: 'Chỉ số', align: 'left', sortable: false,
                render: (x) => `${escapeHtml(x.ten)}${x.kieu === 'hien_tai' ? ' <span class="bc-muted">(hiện tại)</span>' : ''}` },
            { key: 'ky', label: `Tháng ${r.thang.slice(5)}`, sortable: false, render: (x) => val(x.ky, x.don_vi) },
            { key: 'nam', label: `Luỹ kế ${r.nam}`, sortable: false, render: (x) => val(x.nam, x.don_vi) },
            { key: 'don_vi', label: 'Đơn vị', sortable: false },
            { key: 'target', label: 'Chỉ tiêu năm', sortable: false,
                render: (x) => (x.target ? `${escapeHtml(x.target.so_sanh || '')} ${val(x.target.muc_tieu, x.don_vi)}` : '<span class="bc-muted">—</span>') },
            { key: 'dat', label: 'Luỹ kế đạt?', sortable: false, render: (x) => (x.target ? dat(x.target.dat_nam) : '<span class="bc-muted">—</span>') },
        ],
    });
    const months = Object.keys((r.bang.find((x) => x.kieu === 'thang') || {}).thang || {}).sort();
    const byMonth = dataTable({
        rows: r.bang.filter((x) => x.kieu === 'thang'), pageSize: 20,
        columns: [{ key: 'ten', label: 'Chỉ số', align: 'left', sortable: false },
            ...months.map((m) => ({ key: m, label: `T${Number(m.slice(5))}`, sortable: false, render: (x) => val(x.thang[m], x.don_vi) }))],
    });
    return `<div class="bc-filter-bar">${monthOptions(r)}<span class="bc-text-sm">Số đến ${escapeHtml(fmtDate(r.cat))}</span></div>
        ${main}
        <div class="bc-card-title bc-mt-3">Theo tháng năm ${escapeHtml(r.nam)}</div>
        ${byMonth}`;
}

async function loadReport(isCurrent) {
    try {
        const r = await api.attp.report(state.thang || undefined);
        if (!isCurrent()) return;
        fill('attp-report', reportHtml(r));
        document.getElementById('attp-thang')?.addEventListener('change', (e) => {
            state.thang = e.target.value;
            fill('attp-report', skeleton(220));
            loadReport(isCurrent);
        });
    } catch (err) {
        if (isCurrent()) fill('attp-report', errorState(err));
    }
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">An toàn thực phẩm</div>
                <div class="bc-view-banner-sub" id="attp-sub">Cùng số với màn Tổng quan ATTP của Ban ISO</div></div>
            <span class="bc-view-banner-badge">🛡️ ISO 22000</span>
        </div>
        <div id="attp-overview">${skeletonGrid(3, 70, 'bc-grid-3')}${skeleton(320)}</div>
        <div class="bc-section-title">Chỉ số ATTP so chỉ tiêu năm</div>
        <div class="bc-card"><div id="attp-report">${skeleton(220)}</div></div>
        <div class="bc-note bc-mt-3">ⓘ Đèn đỏ: có việc mức cao (quá hạn, lô đang thu hồi, sự cố chưa xử lý…); vàng: có việc cần
            theo dõi; xanh: không việc treo. Số trong thẻ tính 30 ngày tới hôm qua; việc treo tính tới hôm nay.</div>`;
    const ov = api.attp.overview().then((d) => {
        if (!isCurrent()) return;
        if (!d.available) {
            fill('attp-overview', emptyState({ icon: '🛡️', title: 'Chưa có số liệu ATTP',
                message: 'Site chưa cài hệ thống sản xuất (app sx) hoặc phân hệ QC chưa được cập nhật.' }));
            return;
        }
        fill('attp-sub', `Kỳ ${escapeHtml(fmtDate(d.tu))} → ${escapeHtml(fmtDate(d.den))} · việc treo đến ${escapeHtml(fmtDate(d.ngay))}`);
        fill('attp-overview', overviewHtml(d));
    }).catch((err) => { if (isCurrent()) fill('attp-overview', errorState(err)); });
    await Promise.all([ov, loadReport(isCurrent)]);
}
