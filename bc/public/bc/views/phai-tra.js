// #/phai-tra — Phải trả nhà cung cấp (sổ cái TK phải trả, hạn theo Purchase Invoice) + số dư quỹ
// tiền mặt / ngân hàng (như màn Quỹ của Kế toán). Một lượt gọi bc.api.cn.get_payables.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtMoney, fmtMoneyFull, fmtNum } from '../lib/format.js';
import { statCard } from '../components/stat-card.js';
import { kpiGrid } from '../components/kpi-grid.js';
import { dataTable } from '../components/data-table.js';
import { skeleton, skeletonGrid } from '../components/skeleton.js';
import { errorState } from '../components/empty-state.js';

const TYPE_LABEL = { Cash: 'Tiền mặt', Bank: 'Ngân hàng' };

function money(v) { return `<span title="${fmtMoneyFull(v)}">${fmtMoney(v)}</span>`; }

function kpisHtml(d) {
    const ap = d.ap, due = ap.due, cash = d.cash;
    return `<div class="bc-grid bc-grid-4">
        ${statCard({ label: 'Phải trả nhà cung cấp', icon: '🧾', value: money(ap.total),
            rows: [['Quá hạn', `<span class="${ap.overdue > 0 ? 'bc-txt-danger' : ''}">${fmtMoney(ap.overdue)}</span>`]] })}
        ${statCard({ label: `Đến hạn ${fmtNum(d.meta.due_ahead)} ngày tới`, icon: '📅', tone: 'warning', value: money(due.upcoming_total),
            rows: [['Số hoá đơn', fmtNum(due.upcoming_count)]] })}
        ${statCard({ label: 'Quá hạn chưa trả', icon: '⏰', tone: 'danger', value: money(due.overdue_total),
            rows: [['Số hoá đơn', fmtNum(due.overdue_count)]] })}
        ${statCard({ label: 'Quỹ tiền', icon: '🏦', tone: 'success', value: money(cash.total),
            rows: [['Tiền mặt', money(cash.cash)], ['Ngân hàng', money(cash.bank)]] })}
    </div>`;
}

function agingHtml(d) {
    const b = d.ap.buckets;
    return kpiGrid(d.meta.buckets.map((x) => ({ label: x.label, value: fmtMoney(b[x.key] || 0),
        cls: x.key !== 'current' && b[x.key] > 0 ? 'bc-txt-danger' : '' })), 5);
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Phải trả & quỹ tiền</div>
                <div class="bc-view-banner-sub" id="pt-sub">Theo sổ cái như Kế toán · tiền gồm VAT</div></div>
            <span class="bc-view-banner-badge">🏦 Tài chính</span>
        </div>
        <div id="pt-kpis">${skeletonGrid(4, 120)}</div>
        <div class="bc-section-title">Tuổi nợ phải trả</div>
        <div id="pt-aging">${skeleton(70)}</div>
        <div class="bc-grid bc-grid-split bc-mt-3">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Nhà cung cấp phải trả nhiều nhất</div></div><div id="pt-top">${skeleton(200)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Sắp đến hạn trả</div><div class="bc-card-sub" id="pt-due-sub"></div></div><div id="pt-due">${skeleton(200)}</div></div>
        </div>
        <div class="bc-section-title">Số dư quỹ</div>
        <div class="bc-card"><div id="pt-cash">${skeleton(160)}</div></div>
        <div class="bc-note bc-mt-3">ⓘ Phải trả = số dư sổ cái các tài khoản phải trả nhà cung cấp; tuổi nợ theo hạn trên hoá đơn mua.
            Số dư quỹ theo sổ cái các tài khoản tiền mặt / ngân hàng (số tài khoản ngân hàng được che bớt).</div>`;
    try {
        const d = await api.cn.payables();
        if (!isCurrent()) return;
        fill('pt-sub', `Đến ${escapeHtml(fmtDate(d.meta.as_of))} · tiền gồm VAT · ${escapeHtml(d.meta.company)}`);
        fill('pt-kpis', kpisHtml(d));
        fill('pt-aging', agingHtml(d));
        fill('pt-top', dataTable({ rows: d.ap.top, sortKey: 'outstanding', emptyMessage: 'Không có công nợ phải trả',
            columns: [
                { key: 'supplier', label: 'Nhà cung cấp', align: 'left' },
                { key: 'outstanding', label: 'Phải trả', render: (r) => money(r.outstanding) },
                { key: 'days_overdue', label: 'Quá hạn', render: (r) => (r.days_overdue ? `<b class="bc-txt-danger">${fmtNum(r.days_overdue)} ngày</b>` : 'Trong hạn') },
            ] }));
        fill('pt-due-sub', `${fmtNum(d.meta.due_ahead)} ngày tới · ${fmtNum(d.ap.due.upcoming_count)} hoá đơn`);
        fill('pt-due', dataTable({ rows: d.ap.due.rows, sortKey: 'days_to_due', sortDir: 'asc', emptyMessage: 'Không có hoá đơn sắp đến hạn',
            columns: [
                { key: 'supplier', label: 'Nhà cung cấp', align: 'left' },
                { key: 'due_date', label: 'Hạn trả', render: (r) => escapeHtml(fmtDate(r.due_date)), sortValue: (r) => r.due_date },
                { key: 'days_to_due', label: 'Còn', render: (r) => (r.days_to_due ? `${fmtNum(r.days_to_due)} ngày` : '<b class="bc-txt-warning">Hôm nay</b>') },
                { key: 'amount', label: 'Số tiền', render: (r) => money(r.amount) },
            ] }));
        fill('pt-cash', dataTable({ rows: d.cash.rows, sortKey: 'balance', emptyMessage: 'Không có tài khoản tiền có số dư',
            totalRow: { account: '<b>Tổng</b>', balance: `<b>${money(d.cash.total)}</b>` },
            columns: [
                { key: 'account', label: 'Tài khoản', align: 'left' },
                { key: 'type', label: 'Loại', render: (r) => escapeHtml(TYPE_LABEL[r.type] || r.type || '') },
                { key: 'balance', label: 'Số dư', render: (r) => `<span class="${r.balance < 0 ? 'bc-txt-danger' : ''}">${money(r.balance)}</span>` },
            ] }));
    } catch (err) {
        if (isCurrent()) fill('pt-kpis', errorState(err));
        ['pt-aging', 'pt-top', 'pt-due', 'pt-cash'].forEach((id) => fill(id, ''));
    }
}
