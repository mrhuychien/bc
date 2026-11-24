// #/ai — Cấu hình Trợ lý AI (CHỈ System Manager; server guard mọi method bc.api.ai quản trị).
// Một lượt bc.api.ai.get_admin(): khoá (chỉ có / không — không bao giờ có chuỗi khoá), model, chi phí kỳ này so trần,
// quy tắc (bật / tắt, ngưỡng ghi đè — 0 / trống = mặc định), 20 lượt chạy gần nhất, lời AI bị loại, việc đang bỏ qua.
// "Chạy ngay": xếp hàng lượt chạy nền rồi hỏi lại mỗi 5 giây tới khi xong (tối đa 5 phút, rời màn thì dừng).
// P2: chi phí Claude + OpenAI (phản biện), "Thử kết nối OpenAI", "Tạo bản tin tuần / tháng" (xếp hàng job nền —
// bc.api.ai.run_brief) + bảng 6 bản tin gần nhất; nhãn bước đọc được (step_label của máy chủ: "Phản biện · <nhóm>").

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum } from '../lib/format.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { dataTable } from '../components/data-table.js';
import { emptyState, errorState } from '../components/empty-state.js';

const POLL_MS = 5000;
const POLL_MAX_MS = 5 * 60 * 1000;
const RUN_STATUS = { 'ok': ['Thành công', 'bc-badge-success'], 'loi': ['Lỗi', 'bc-badge-danger'],
    'het-credit': ['Hết credit', 'bc-badge-danger'], 'vuot-tran': ['Vượt trần chi', 'bc-badge-warning'],
    'tat': ['AI đang tắt', 'bc-badge-muted'], 'khong-khoa': ['Chưa có khoá', 'bc-badge-warning'] };
const RUN_TYPE = { 'ngay': 'Hằng ngày', 'tuan': 'Hằng tuần', 'thang': 'Hằng tháng', 'tay': 'Chạy tay', 'hoi-dap': 'Hỏi đáp' };
const BRIEF_KIND = { tuan: 'Tuần', thang: 'Tháng' };
const PROVIDER = { claude: 'Claude', openai: 'OpenAI' };
const STEP = { 'tong': 'Tổng hợp', 'ai': 'Bước AI', 'test': 'Thử kết nối', 'review': 'Phản biện' };
const AUDIENCE = { 'lanh-dao': 'Lãnh đạo', 'quan-tri': 'Quản trị' };

let st = { d: null, polling: false, briefQueued: {} };
let pollSeq = 0;

function fmtDT(s) {
    if (!s) return '—';
    const [d, t] = String(s).replace('T', ' ').split(' ');
    return `${fmtDate(d)}${t ? ' ' + t.slice(0, 5) : ''}`;
}
function usd(v, digits = 2) {
    const n = Number(v) || 0;
    return `${n.toLocaleString('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, 4) })} USD`;
}
function settingsUrl(d) {
    const u = String(d?.settings_url || '');
    return u.startsWith('/app/') ? u : '/app/bc-settings';
}
const yesNo = (on, yes = 'có', no = 'chưa có') =>
    `<span class="bc-badge ${on ? 'bc-badge-success' : 'bc-badge-warning'}">${on ? yes : no}</span>`;
/** Khoá: có · chưa có · khai sai dạng (dán lẫn dấu cách / xuống dòng — máy chủ coi như chưa có). */
const keyState = (d, p) => (d.keys_bad?.[p]
    ? '<span class="bc-badge bc-badge-danger" title="Khoá lẫn dấu cách hoặc xuống dòng — dán lại vào site_config">khai sai dạng</span>'
    : yesNo(d.keys?.[p]));

// ─── Trạng thái + chi phí ───────────────────────────────────────────────────
function statusHtml(d) {
    const m = d.models || {};
    return `<div class="bc-ai-kv">
        <div><span>Khoá Claude</span><b id="ai-key-claude">${keyState(d, 'claude')}</b></div>
        <div><span>Model hằng ngày</span><b>${escapeHtml(m.claude || '—')}</b></div>
        <div><span>Model bản tin tuần / tháng</span><b>${escapeHtml(m.claude_deep || '—')}</b></div>
        <div><span>AI viết lời</span><b id="ai-enabled">${d.enabled ? '<span class="bc-badge bc-badge-success">Đang bật</span>'
            : '<span class="bc-badge bc-badge-muted">Đang tắt — chỉ lời quy tắc</span>'}</b></div>
        <div><span>Khoá OpenAI</span><b id="ai-key-openai">${keyState(d, 'openai')}</b></div>
        <div><span>Model OpenAI</span><b>${escapeHtml(m.openai || '—')}</b></div>
    </div>
    <div class="bc-flex bc-gap-2 bc-wrap bc-items-center bc-mt-3">
        <button type="button" class="bc-btn bc-btn-sm" id="ai-test"><i class="fas fa-plug"></i> Thử kết nối Claude</button>
        <span class="bc-ai-test-out" id="ai-test-out" role="status"></span>
    </div>
    <div class="bc-flex bc-gap-2 bc-wrap bc-items-center bc-mt-2">
        <button type="button" class="bc-btn bc-btn-sm" id="ai-test-openai"><i class="fas fa-plug"></i> Thử kết nối OpenAI</button>
        <span class="bc-ai-test-out" id="ai-test-openai-out" role="status"></span>
    </div>
    <div class="bc-note" id="ai-openai-note">OpenAI phản biện lời AI của lượt hằng ngày (badge "Cần kiểm chứng" khi nghi ngờ).
        ${m.openai ? 'Đang bật phản biện.' : 'Model OpenAI trống — phản biện đang tắt.'} Bật / tắt AI, đổi model, trần chi và
        bối cảnh công ty: <a href="${escapeHtml(settingsUrl(d))}" target="_blank" rel="noopener">BC Settings › Trợ lý AI</a>.</div>`;
}

/** Chi phí kỳ này của một nhà cung cấp. id của Claude giữ như P1 (ai-spent…), OpenAI thêm hậu tố -openai. */
function budgetOne(d, p) {
    const b = d.budget?.[p];
    const sx = p === 'claude' ? '' : `-${p}`;
    if (!b) return `<div class="bc-muted bc-text-sm" data-budget="${p}">Chưa có số chi phí ${escapeHtml(PROVIDER[p])}.</div>`;
    const spent = Number(b.spent) || 0, cap = Number(b.cap) || 0;
    const pct = cap > 0 ? Math.min(100, Math.round(spent / cap * 100)) : 100;
    const noModel = p === 'openai' && !d.models?.openai;
    const warnPrice = noModel ? `<div class="bc-ai-warn" id="ai-nomodel${sx}">Chưa đặt model OpenAI — phản biện đang tắt.</div>`
        : (b.price_known ? '' : `<div class="bc-ai-warn" id="ai-noprice${sx}">${p === 'claude' ? 'Model hằng ngày' : 'Model OpenAI'} chưa khai giá — chi phí không tính được (vẫn giới hạn số lượt gọi).</div>`);
    return `<div class="bc-ai-budget" data-budget="${p}">
        <div class="bc-ai-sub">${escapeHtml(PROVIDER[p])}</div>
        <div class="bc-ai-budget-num" id="ai-spent${sx}"><b>${escapeHtml(usd(spent))}</b> / ${escapeHtml(usd(cap))}</div>
        <div class="bc-progress ${pct >= 80 ? 'bc-alt' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"
            aria-label="${escapeHtml(`Đã chi ${PROVIDER[p]} so với trần`)}"><span style="width:${pct}%"></span></div>
        ${cap <= 0 ? `<div class="bc-ai-warn" id="ai-cap0${sx}">Trần 0 USD — đang chặn mọi lượt gọi.</div>` : ''}
        <div class="bc-ai-kv bc-mt-2">
            <div><span>Kỳ tính từ</span><b>${escapeHtml(fmtDate(b.cycle_start))}</b></div>
            <div><span>Lượt gọi hôm nay</span><b id="ai-calls${sx}">${fmtNum(b.calls_today)} / ${fmtNum(b.max_calls)}</b></div>
        </div>
        ${warnPrice}
    </div>`;
}

function budgetHtml(d) {
    return `${budgetOne(d, 'claude')}<div class="bc-ai-budget-sep"></div>${budgetOne(d, 'openai')}`;
}

function runBtnHtml(d) {
    const run = !!d.running || st.polling;
    return `<button type="button" class="bc-btn bc-btn-primary" id="ai-run" ${run ? 'disabled' : ''}>
            <i class="fas ${run ? 'fa-spinner fa-spin' : 'fa-play'}"></i> ${run ? 'Đang chạy…' : 'Chạy ngay'}</button>
        <span class="bc-muted bc-text-sm">${run ? 'Lượt chạy đang làm nền — màn tự cập nhật khi xong.' : 'Chạy lượt hằng ngày ngay bây giờ (thường chạy 5:30 sáng).'}</span>`;
}

// ─── Quy tắc ─────────────────────────────────────────────────────────────────
function ruleHtml(r) {
    const val = (cur, def) => (cur !== null && cur !== undefined && Number(cur) !== Number(def ?? NaN) ? String(cur) : '');
    const ph = (def) => (def === null || def === undefined ? 'không có' : `mặc định ${def}`);
    return `<div class="bc-ai-rule ${r.disabled ? 'bc-ai-rule-off' : ''}" data-rule="${escapeHtml(r.key)}">
        <div class="bc-ai-rule-head">
            <div class="bc-ai-rule-name">${escapeHtml(r.label)}</div>
            <label class="bc-ai-toggle"><input type="checkbox" role="switch" class="bc-switch" data-f="on" ${r.disabled ? '' : 'checked'}
                aria-label="${escapeHtml(`Bật quy tắc ${r.label}`)}"><span>${r.disabled ? 'Tắt' : 'Bật'}</span></label>
        </div>
        <div class="bc-ai-rule-meta">${escapeHtml(r.section_label)} · ${escapeHtml(AUDIENCE[r.audience] || r.audience || '')}
            ${r.unit ? ` · đơn vị ${escapeHtml(r.unit)}` : ''} · <span data-open>${fmtNum(r.open)} tín hiệu đang mở</span>
            ${r.lower ? ' · <span class="bc-ai-lower">thấp hơn ngưỡng là xấu</span>' : ''}</div>
        <div class="bc-ai-rule-form">
            <label>Ngưỡng vàng<input type="number" inputmode="decimal" step="any" min="0" class="bc-input" data-f="vang"
                value="${escapeHtml(val(r.vang, r.vang_default))}" placeholder="${escapeHtml(ph(r.vang_default))}"></label>
            <label>Ngưỡng đỏ<input type="number" inputmode="decimal" step="any" min="0" class="bc-input" data-f="do"
                value="${escapeHtml(val(r.do, r.do_default))}" placeholder="${escapeHtml(ph(r.do_default))}"></label>
            <button type="button" class="bc-btn bc-btn-sm bc-btn-primary" data-save>Lưu</button>
        </div>
        <div class="bc-ai-tech">${escapeHtml(r.key)}</div>
    </div>`;
}

function rulesHtml(d) {
    const rules = d.rules || [];
    return rules.length ? rules.map(ruleHtml).join('') : emptyState({ icon: '📭', title: 'Chưa nạp được quy tắc nào' });
}

// ─── Lượt chạy ───────────────────────────────────────────────────────────────
function wrapText(t) { return `<div class="bc-ai-cell">${escapeHtml(t)}</div>`; }

/** Chi phí một lượt: không gọi model (không nhà cung cấp / 0 token) → "—"; có token mà chưa khai giá → cảnh báo. */
function costCell(r) {
    if (!r.provider || (!Number(r.tokens_in) && !Number(r.tokens_out))) return '<span class="bc-muted" data-cost="none">—</span>';
    return Number(r.cost_known) ? escapeHtml(usd(r.cost_usd, 4)) : '<span class="bc-txt-warning" data-cost="unpriced">chưa khai giá</span>';
}

function runsHtml(d) {
    return dataTable({ rows: d.runs || [], pageSize: 20, emptyMessage: 'Chưa có lượt chạy nào', columns: [
        { key: 'started', label: 'Lúc', align: 'left', sortable: false, render: (r) => escapeHtml(fmtDT(r.started)) },
        { key: 'run_type', label: 'Loại', align: 'left', sortable: false,
            render: (r) => `${escapeHtml(RUN_TYPE[r.run_type] || r.run_type || '')}<div class="bc-muted bc-text-sm" data-step>${escapeHtml(r.step_label || STEP[r.step] || r.step || '')}</div>` },
        { key: 'model', label: 'Nhà cung cấp / model', align: 'left', sortable: false,
            render: (r) => (r.provider ? `${escapeHtml(r.provider)}<div class="bc-muted bc-text-sm">${escapeHtml(r.model || '')}</div>` : '—') },
        { key: 'status', label: 'Trạng thái', sortable: false, render: (r) => {
            const [t, c] = RUN_STATUS[r.status] || [r.status || '—', 'bc-badge-muted'];
            return `<span class="bc-badge ${c}">${escapeHtml(t)}</span>`;
        } },
        { key: 'signals', label: 'Tín hiệu / lời AI / bị loại', sortable: false,
            render: (r) => `${fmtNum(r.signals)} / ${fmtNum(r.insights_ai)} / ${fmtNum(r.rejected)}` },
        { key: 'tokens_in', label: 'Token vào / ra', sortable: false, render: (r) => `${fmtNum(r.tokens_in)} / ${fmtNum(r.tokens_out)}` },
        { key: 'cost_usd', label: 'Chi phí', sortable: false,
            render: costCell },
        { key: 'error', label: 'Lỗi', align: 'left', sortable: false, render: (r) => (r.error ? wrapText(r.error) : '') },
    ] });
}

// ─── Bản tin tuần / tháng ───────────────────────────────────────────────────
function briefBtnHtml(d) {
    const btn = (kind, label) => {
        const run = !!d.briefs_running?.[kind] || !!st.briefQueued?.[kind];
        return `<button type="button" class="bc-btn bc-btn-sm" id="ai-brief-${kind}" data-brief-kind="${kind}" ${run ? 'disabled' : ''}>
            <i class="fas ${run ? 'fa-spinner fa-spin' : 'fa-newspaper'}"></i> ${run ? 'Đang tạo…' : label}</button>`;
    };
    return `${btn('tuan', 'Tạo bản tin tuần')}${btn('thang', 'Tạo bản tin tháng')}
        <span class="bc-muted bc-text-sm">Tự chạy thứ Hai 6:00 (tuần trước) và ngày 2 hằng tháng 7:00 (tháng trước).</span>`;
}

function periodText(b) {
    const p = (s) => String(s || '').slice(0, 10).split('-');
    const [y1, m1, d1] = p(b.period_from), [y2, m2, d2] = p(b.period_to);
    if (b.type === 'thang' && y2) return `${Number(m2)}/${y2}`;
    return y1 && y2 ? `${d1}/${m1} – ${d2}/${m2}/${y2}` : '—';
}

function briefsHtml(d) {
    return dataTable({ rows: d.briefs || [], pageSize: 6, emptyMessage: 'Chưa có bản tin tuần / tháng nào', columns: [
        { key: 'date', label: 'Ngày', align: 'left', sortable: false, render: (b) => escapeHtml(fmtDate(b.date)) },
        { key: 'type', label: 'Loại · kỳ', align: 'left', sortable: false,
            render: (b) => `${escapeHtml(BRIEF_KIND[b.type] || b.type || '')}<div class="bc-muted bc-text-sm">${escapeHtml(periodText(b))}</div>` },
        { key: 'title', label: 'Tiêu đề', align: 'left', sortable: false, render: (b) => wrapText(b.title || '') },
        { key: 'source', label: 'Nguồn', sortable: false, render: (b) => (b.source === 'ai'
            ? '<span class="bc-badge bc-badge-primary">AI</span>' : '<span class="bc-badge bc-badge-muted">Quy tắc</span>') },
        { key: 'model', label: 'Model', align: 'left', sortable: false, render: (b) => (b.model ? escapeHtml(b.model) : '—') },
        { key: 'items', label: 'Số mục', sortable: false, render: (b) => fmtNum(b.items) },
    ] });
}

// ─── Lời AI bị loại + việc đang bỏ qua ──────────────────────────────────────
function itemHtml(x, muted) {
    return `<div class="bc-ai-item" data-item="${escapeHtml(x.id)}">
        <div class="bc-ai-item-main">
            <div class="bc-ai-item-title">${escapeHtml(x.title)}</div>
            <div class="bc-ai-rule-meta">${escapeHtml(x.section_label)} · ${fmtNum(x.days)} ngày · quy tắc ${escapeHtml(x.rule || '—')}
                ${muted ? ` · ${x.mute_until ? `bỏ qua đến ${escapeHtml(fmtDate(x.mute_until))}` : 'bỏ qua hẳn'}` : ''}</div>
        </div>
        ${muted ? '<button type="button" class="bc-btn bc-btn-sm" data-reopen>Mở lại</button>' : ''}
    </div>`;
}

function rejectedHtml(d) {
    const xs = d.rejected || [];
    return xs.length ? `<div class="bc-note" style="margin:0 0 .5rem">Lượt gần nhất AI viết sai (số không khớp, viết số trần…) —
        đang hiện lời của quy tắc.</div>${xs.map((x) => itemHtml(x, false)).join('')}`
        : '<div class="bc-muted bc-text-sm">Không có lời AI nào bị loại.</div>';
}

function mutedHtml(d) {
    const xs = d.muted || [];
    return xs.length ? xs.map((x) => itemHtml(x, true)).join('') : '<div class="bc-muted bc-text-sm">Không có việc nào đang bỏ qua.</div>';
}

// ─── Vẽ + tương tác ─────────────────────────────────────────────────────────
function paint(d) {
    st.d = d;
    fill('ai-status', statusHtml(d));
    fill('ai-budget', budgetHtml(d));
    fill('ai-runbar', runBtnHtml(d));
    fill('ai-rules', rulesHtml(d));
    fill('ai-runs', runsHtml(d));
    st.briefQueued = {};   // máy chủ (briefs_running) nói từ đây
    fill('ai-briefbar', briefBtnHtml(d));
    fill('ai-briefs', briefsHtml(d));
    fill('ai-rejected', rejectedHtml(d));
    fill('ai-muted', mutedHtml(d));
}

async function load(isCurrent) {
    try {
        const d = await api.ai.admin();
        if (!isCurrent()) return;
        paint(d);
        if (d.running && !st.polling) poll(isCurrent);
    } catch (err) {
        if (isCurrent()) fill('ai-status', errorState(err));
    }
}

/** Hỏi lại mỗi 5 giây tới khi lượt chạy xong (≤ 5 phút); rời màn → dừng. Xong → vẽ lại toàn màn. */
function poll(isCurrent) {
    const my = ++pollSeq;
    const t0 = Date.now();
    st.polling = true;
    const tick = async () => {
        if (my !== pollSeq || !isCurrent()) { if (my === pollSeq) st.polling = false; return; }
        let d = null;
        try { d = await api.ai.admin(); } catch { /* lỗi mạng tạm thời: hỏi lại lượt sau */ }
        if (my !== pollSeq || !isCurrent()) { if (my === pollSeq) st.polling = false; return; }
        if (d && !d.running) {
            st.polling = false;
            paint(d);
            showToast('Lượt chạy đã xong', 'success');
            return;
        }
        if (Date.now() - t0 >= POLL_MAX_MS) {
            st.polling = false;
            if (d) paint(d);
            showToast('Lượt chạy vẫn chưa xong sau 5 phút — bấm Làm mới để xem lại.', 'warning');
            return;
        }
        setTimeout(tick, POLL_MS);
    };
    setTimeout(tick, POLL_MS);
}

async function onRun(btn, isCurrent) {
    btn.disabled = true;
    try {
        await api.ai.runNow();
        showToast('Đã xếp lượt chạy — đang chạy nền', 'success');
        st.polling = true;
        fill('ai-runbar', runBtnHtml({ ...st.d, running: true }));
        poll(isCurrent);
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
    }
}

async function onTest(btn, provider = 'claude') {
    const out = document.getElementById(provider === 'claude' ? 'ai-test-out' : `ai-test-${provider}-out`);
    btn.disabled = true;
    if (out) { out.className = 'bc-ai-test-out bc-muted'; out.textContent = 'Đang thử…'; }
    try {
        const r = await api.ai.test(provider);
        if (out) {
            out.className = `bc-ai-test-out ${r.ok ? 'bc-txt-success' : 'bc-txt-danger'}`;
            out.textContent = r.ok ? `Kết nối được (${r.model || ''})` : `Không được: ${r.error || 'không rõ lỗi'}${r.model ? ` (${r.model})` : ''}`;
        }
    } catch (err) {
        if (out) { out.className = 'bc-ai-test-out bc-txt-danger'; out.textContent = err.message; }
    } finally {
        btn.disabled = false;
    }
}

/** Tạo bản tin ngay: chỉ xếp hàng job nền (máy chủ từ chối xếp thêm khi một bản tin đang chạy → queued false). */
async function onBrief(btn) {
    const kind = btn.dataset.briefKind;
    const label = kind === 'thang' ? 'bản tin tháng' : 'bản tin tuần';
    btn.disabled = true;
    try {
        // Tab mở trước deploy có thể còn lib/api.js cũ (chưa có runBrief) → gọi thẳng method.
        const r = await (api.ai.runBrief ? api.ai.runBrief(kind) : api.call('bc.api.ai.run_brief', { kind }));
        if (r?.queued) {
            st.briefQueued = { ...(st.briefQueued || {}), [kind]: true };
            fill('ai-briefbar', briefBtnHtml(st.d || {}));
            showToast(`Đã xếp ${label} — đang tạo nền, tải lại màn sau ít phút để xem`, 'success');
        } else {
            showToast('Một bản tin đang được tạo — chờ xong rồi thử lại.', 'warning');
            btn.disabled = false;
        }
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
    }
}

async function onSaveRule(row) {
    const key = row.dataset.rule;
    const get = (f) => row.querySelector(`[data-f="${f}"]`);
    const num = (el) => { const v = String(el?.value ?? '').trim(); return v === '' ? 0 : v; };  // trống = mặc định (0)
    const btn = row.querySelector('[data-save]');
    btn.disabled = true;
    try {
        const r = await api.ai.setRule(key, get('on').checked ? 0 : 1, num(get('vang')), num(get('do')));
        const i = (st.d?.rules || []).findIndex((x) => x.key === key);
        if (i >= 0) st.d.rules[i] = r;
        row.outerHTML = ruleHtml(r);
        showToast(`Đã lưu quy tắc "${r.label}"`, 'success');
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
    }
}

async function onReopen(btn) {
    const item = btn.closest('[data-item]');
    const id = item?.dataset.item;
    btn.disabled = true;
    try {
        await api.ai.setStatus(id, 'mo');
        if (st.d) st.d.muted = (st.d.muted || []).filter((x) => x.id !== id);
        fill('ai-muted', mutedHtml(st.d || {}));
        showToast('Đã mở lại', 'success');
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
    }
}

export async function render({ container, isCurrent }) {
    if (!window.BC_CONTEXT?.isSysManager) {
        container.innerHTML = emptyState({ icon: '🔒', title: 'Chỉ dành cho quản trị' });
        return;
    }
    st = { d: null, polling: false, briefQueued: {} };
    pollSeq++;  // lượt hỏi của lần vào trước (nếu còn) tự dừng
    container.innerHTML = `<div id="ai-root" class="bc-ai-admin-screen">
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Cấu hình Trợ lý AI</div>
                <div class="bc-view-banner-sub">Khoá, chi phí, quy tắc và các lượt chạy · chỉ quản trị</div></div>
            <span class="bc-view-banner-badge">🤖 Quản trị</span>
        </div>
        <div class="bc-grid bc-grid-even" style="align-items:start">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Trạng thái</div></div><div id="ai-status">${skeleton(150)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Chi phí kỳ này</div></div><div id="ai-budget">${skeleton(150)}</div></div>
        </div>
        <div class="bc-filter-bar bc-mt-3 bc-ai-runbar" id="ai-runbar"></div>
        <div class="bc-section-title">Quy tắc</div>
        <div class="bc-card"><div class="bc-note" style="margin:0 0 .5rem">Ô ngưỡng để trống (hoặc 0) = dùng mặc định. Tắt quy tắc thì
            lượt chạy sau không sinh tín hiệu của quy tắc đó.</div><div id="ai-rules">${skeleton(200)}</div></div>
        <div class="bc-section-title">Lượt chạy gần nhất</div>
        <div class="bc-card"><div id="ai-runs">${skeleton(200)}</div></div>
        <div class="bc-section-title">Bản tin tuần / tháng</div>
        <div class="bc-card"><div class="bc-ai-briefbar" id="ai-briefbar"></div><div id="ai-briefs">${skeleton(120)}</div></div>
        <div class="bc-grid bc-grid-even bc-mt-3" style="align-items:start">
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Lời AI bị loại</div></div><div id="ai-rejected">${skeleton(80)}</div></div>
            <div class="bc-card"><div class="bc-card-head"><div class="bc-card-title">Việc đang bỏ qua</div></div><div id="ai-muted">${skeleton(80)}</div></div>
        </div>
        <div class="bc-note bc-mt-3">ⓘ Khoá API nằm trong site_config của máy chủ, màn này chỉ cho biết có hay chưa. Mọi thay đổi
            cấu hình khác: <a href="/app/bc-settings" id="ai-settings" target="_blank" rel="noopener">mở BC Settings</a>.</div></div>`;
    const root = document.getElementById('ai-root');
    root.addEventListener('click', (e) => {
        const t = e.target;
        if (t.closest('#ai-run')) { onRun(t.closest('#ai-run'), isCurrent); return; }
        if (t.closest('#ai-test')) { onTest(t.closest('#ai-test')); return; }
        if (t.closest('#ai-test-openai')) { onTest(t.closest('#ai-test-openai'), 'openai'); return; }
        const bk = t.closest('[data-brief-kind]');
        if (bk) { onBrief(bk); return; }
        const s = t.closest('[data-save]');
        if (s) { onSaveRule(s.closest('[data-rule]')); return; }
        const o = t.closest('[data-reopen]');
        if (o) onReopen(o);
    });
    root.addEventListener('change', (e) => {
        if (e.target.dataset?.f === 'on') {
            const lab = e.target.parentElement?.querySelector('span');
            if (lab) lab.textContent = e.target.checked ? 'Bật' : 'Tắt';
        }
    });
    await load(isCurrent);
    if (st.d) {
        const a = document.getElementById('ai-settings');
        if (a) a.href = settingsUrl(st.d);
    }
}
