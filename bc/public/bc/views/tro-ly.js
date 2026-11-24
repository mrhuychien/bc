// #/tro-ly — Trợ lý AI: việc cần chú ý do quy tắc phát hiện trên cùng số liệu các màn báo cáo (lời có thể do AI viết).
// Một lượt gọi bc.api.ai.get_feed(closed) — máy chủ đã lọc theo vai và mảng đang ẩn (người xem không nhận chứng từ,
// ghi chú quản trị, nhóm Hệ thống). Lời quy tắc / AI là VĂN BẢN THUẦN: mọi chuỗi máy chủ qua escapeHtml, không markdown.
// Quản trị (System Manager): thêm nút đổi trạng thái, ghi chú, chứng từ, dòng kỹ thuật — người xem không có trong DOM.
// Bản tin tuần / tháng (feed.briefs) vẽ dưới bản tin ngày: máy chủ đã bỏ mục dùng số của mảng ẩn (người xem), mục là
// chữ thuần. Nhóm Kiểm soát (chứng từ / giá) không có nút "Xem ở màn" — máy chủ trả route trống.
// P3: nút "Hỏi trợ lý" sang #/hoi-dap, chỉ hiện khi bc.api.ai.get_qa().enabled.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtDate, fmtNum, daysBetween, isoOf, parseISO, todayISO } from '../lib/format.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

// Thứ tự nhóm = registry.GROUPS của máy chủ (chỉ khoá — nhãn và việc nào có lấy từ dữ liệu). Nhóm lạ xếp sau.
const GROUP_ORDER = ['kinh-doanh', 'kho-sx', 'van-chuyen', 'tai-chinh', 'nhan-su', 'attp', 'kiem-soat', 'he-thong'];
const BRIEF_KIND = { tuan: 'Bản tin tuần', thang: 'Bản tin tháng' };
const OPEN = ['mo', 'dang-xu-ly'];
const NOTE = 'ⓘ Tín hiệu do quy tắc tính trên cùng số liệu với các màn báo cáo. Phần lời có nhãn AI do mô hình ngôn ngữ '
    + 'viết; mọi con số trong lời do máy chủ chèn từ số liệu gốc. Cập nhật 5:30 mỗi sáng.';

const st = { feed: null, group: 'all', closed: false };
let seq = 0;  // lượt tải mới nhất — bật / tắt "đã đóng" nhanh thì lượt cũ về sau không đè lượt mới
const isAdmin = () => !!window.BC_CONTEXT?.isSysManager;

/** "2026-10-27 05:40:00" → "27/10/2026 05:40". */
function fmtDT(s) {
    if (!s) return '—';
    const [d, t] = String(s).replace('T', ' ').split(' ');
    return `${fmtDate(d)}${t ? ' ' + t.slice(0, 5) : ''}`;
}

/** Hôm nay theo MÁY CHỦ (giữ hạn bỏ qua khi chỉ lưu ghi chú): ngày của bản tin, không thì first_seen + days. */
function serverToday() {
    const f = st.feed;
    if (f?.brief?.date) return String(f.brief.date).slice(0, 10);
    const x = (f?.insights || []).find((i) => i.first_seen && i.days > 0);
    if (x) {
        const d = parseISO(x.first_seen);
        d.setDate(d.getDate() + Number(x.days));
        return isoOf(d.getFullYear(), d.getMonth() + 1, d.getDate());
    }
    return todayISO();
}

/** href chỉ khi route là đường dẫn nội bộ "#/…" — chuỗi khác (javascript:, http…) không thành link. */
function safeRoute(r) { return typeof r === 'string' && r.startsWith('#/') ? r : ''; }

function docHref(d) {
    const slug = String(d?.doctype || '').toLowerCase().replace(/ /g, '-');
    return `/app/${encodeURIComponent(slug)}/${encodeURIComponent(String(d?.name ?? ''))}`;
}

function groupKey(x) { return x.group || 'khac'; }

function groups(list) {
    const seen = new Map();
    for (const x of list) {
        const k = groupKey(x);
        if (!seen.has(k)) seen.set(k, { key: k, label: x.group_label || 'Khác', count: 0 });
        seen.get(k).count++;
    }
    const rank = (k) => { const i = GROUP_ORDER.indexOf(k); return i < 0 ? GROUP_ORDER.length : i; };
    return [...seen.values()].sort((a, b) => rank(a.key) - rank(b.key));
}

/** "2026-10-25 05:30:00" → "25/10". */
function fmtDM(s) {
    const d = String(s || '').slice(0, 10).split('-');
    return d.length === 3 ? `${d[2]}/${d[1]}` : '';
}

// ─── Thẻ nhận định ──────────────────────────────────────────────────────────
function badges(x, admin) {
    const b = [];
    // Lượt chạy ok gần nhất không làm mới việc này (quy tắc không chạy được) — số là số của ngày last_seen.
    if (x.stale) b.push(`<span class="bc-badge bc-badge-warning" data-b="cu">${escapeHtml(`Số ngày ${fmtDM(x.last_seen)} — chưa cập nhật được`)}</span>`);
    if (x.status === 'dang-xu-ly') b.push('<span class="bc-badge bc-badge-primary" data-b="xu-ly">Đang xử lý</span>');
    if (x.review_verdict === 'nghi-ngo') b.push('<span class="bc-badge bc-badge-warning" data-b="kiem-chung">Cần kiểm chứng</span>');
    if (admin) {
        if (x.status === 'bo-qua') {
            b.push(`<span class="bc-badge bc-badge-muted" data-b="bo-qua">Đang bỏ qua${x.mute_until
                ? ` đến ${escapeHtml(fmtDate(x.mute_until))}` : ' hẳn'}</span>`);
        }
        if (x.status === 'dong') b.push('<span class="bc-badge bc-badge-muted" data-b="dong">Đã đóng</span>');
        if (x.needs_check) b.push('<span class="bc-badge bc-badge-danger" data-b="loai">Lời AI bị loại</span>');
        if (x.audience === 'quan-tri') b.push('<span class="bc-badge bc-badge-muted" data-b="quan-tri">Chỉ quản trị</span>');
    }
    return b.length ? `<div class="bc-ai-badges">${b.join('')}</div>` : '';
}

/** Nút hợp với trạng thái hiện tại (dong: không đổi được — máy chủ cũng từ chối). */
function actions(x) {
    if (x.status === 'dong') return '';
    const btn = (act, label, primary = false) =>
        `<button type="button" class="bc-btn bc-btn-sm ${primary ? 'bc-btn-primary' : ''}" data-act="${act}">${label}</button>`;
    const out = [];
    if (x.status !== 'mo') out.push(btn('mo', 'Mở lại', x.status === 'bo-qua'));
    if (x.status !== 'dang-xu-ly') out.push(btn('dang-xu-ly', 'Đang xử lý', x.status === 'mo'));
    if (x.status !== 'bo-qua') out.push(btn('bo-qua-7', 'Bỏ qua 7 ngày'), btn('bo-qua-30', 'Bỏ qua 30 ngày'), btn('bo-qua', 'Bỏ qua hẳn'));
    return `<div class="bc-ai-actions">${out.join('')}</div>`;
}

function adminBlock(x) {
    const docs = Array.isArray(x.documents) ? x.documents : [];
    const edit = x.status !== 'dong';
    return `<div class="bc-ai-admin">
        ${actions(x)}
        <label class="bc-ai-note-label">Ghi chú quản trị (đưa vào lượt chạy sau)
            <textarea class="bc-input bc-ai-note" rows="2" maxlength="500" ${edit ? '' : 'disabled'}>${escapeHtml(x.admin_note || '')}</textarea></label>
        ${edit ? '<button type="button" class="bc-btn bc-btn-sm" data-act="note"><i class="fas fa-floppy-disk"></i> Lưu ghi chú</button>' : ''}
        ${docs.length ? `<div class="bc-ai-docs"><div class="bc-ai-sub">Chứng từ</div><ul>${docs.map((d) => `<li>
            <a href="${escapeHtml(docHref(d))}" target="_blank" rel="noopener">${escapeHtml(d.doctype)} · ${escapeHtml(d.name)}</a></li>`).join('')}</ul></div>` : ''}
        ${x.review_note ? `<div class="bc-ai-review"><span class="bc-ai-sub">Phản biện:</span> ${escapeHtml(x.review_note)}</div>` : ''}
        <div class="bc-ai-tech">Quy tắc ${escapeHtml(x.rule || '—')} · ${escapeHtml(x.signal_key || '')}</div>
    </div>`;
}

function cardHtml(x) {
    const admin = isAdmin();
    const route = safeRoute(x.route);
    const sev = x.severity === 'do' ? 'do' : 'vang';
    const advice = Array.isArray(x.advice) ? x.advice : [];
    return `<article class="bc-card bc-ai-card bc-ai-${sev} ${x.status === 'dong' || x.status === 'bo-qua' ? 'bc-ai-faded' : ''}"
            data-ai-card="${escapeHtml(x.id)}" data-group="${escapeHtml(groupKey(x))}" aria-label="${sev === 'do' ? 'Mức đỏ' : 'Mức vàng'}">
        ${badges(x, admin)}
        <h3 class="bc-ai-title">${escapeHtml(x.title)}</h3>
        ${x.body ? `<div class="bc-ai-body">${escapeHtml(x.body)}</div>` : ''}
        ${advice.length ? `<ul class="bc-ai-advice">${advice.map((a) => `<li>${escapeHtml(a)}</li>`).join('')}</ul>` : ''}
        <div class="bc-ai-meta">${fmtNum(x.days)} ngày · ${escapeHtml(x.section_label)} · ${x.source === 'ai' ? 'AI' : 'Quy tắc'}</div>
        ${route ? `<a class="bc-btn bc-btn-sm bc-ai-go" href="${escapeHtml(route)}">Xem ở màn ${escapeHtml(x.section_label)} ›</a>` : ''}
        ${admin ? adminBlock(x) : ''}
    </article>`;
}

// ─── Vẽ ──────────────────────────────────────────────────────────────────────
function paintHead(f) {
    const m = f.meta || {};
    fill('tl-sub', `${m.last_ok ? `Cập nhật ${escapeHtml(fmtDT(m.last_ok))}` : 'Chưa chạy lần nào'}${m.running ? ' · Đang chạy…' : ''}`);
    fill('tl-mode', m.ai_on ? 'AI' : 'Quy tắc');
    fill('tl-alert', m.stale ? `<div class="bc-alert bc-ai-alert-do" role="alert">${m.last_ok
        ? `Trợ lý chưa chạy từ ${escapeHtml(fmtDT(m.last_ok))} — số dưới đây có thể đã cũ.` : 'Trợ lý chưa chạy lần nào.'}</div>` : '');
    const nCu = (f.insights || []).filter((x) => x.stale).length;
    fill('tl-stale', nCu ? `<div class="bc-alert bc-ai-stale-line" role="status">${fmtNum(nCu)} việc chưa cập nhật được ở lượt chạy gần nhất
        — số trên các thẻ đó là số của ngày ghi trên thẻ.</div>` : '');
    const b = f.brief;
    const items = b && Array.isArray(b.items) ? b.items.slice(0, 5) : [];
    fill('tl-brief', b && items.length ? `<div class="bc-card bc-ai-brief">
        <div class="bc-card-head"><div class="bc-card-title">☀️ ${escapeHtml(b.title)}</div></div>
        <ol class="bc-ai-brief-list">${items.map((it) => `<li><button type="button" class="bc-ai-brief-item bc-ai-${it.severity === 'do' ? 'do' : 'vang'}"
            data-brief="${escapeHtml(it.id)}">${escapeHtml(it.title)}</button></li>`).join('')}</ol></div>` : '');
}

/** Kỳ của bản tin: tuần "19/10 – 25/10/2026", tháng "Tháng 10/2026". */
function periodText(b) {
    const p = (s) => String(s || '').slice(0, 10).split('-');
    const [y1, m1, d1] = p(b.period_from), [y2, m2, d2] = p(b.period_to);
    if (b.type === 'thang' && y2) return `Tháng ${Number(m2)}/${y2}`;
    if (y1 && y2) return `${d1}/${m1} – ${d2}/${m2}/${y2}`;
    return b.date ? fmtDate(b.date) : '';
}

function periodBriefHtml(b) {
    const admin = isAdmin();
    const ai = b.source === 'ai';
    const parts = (Array.isArray(b.parts) ? b.parts : []).filter((p) => Array.isArray(p.items) && p.items.length);
    return `<article class="bc-card bc-ai-pbrief" data-pbrief="${escapeHtml(b.type)}">
        <div class="bc-ai-pbrief-head">
            <div class="bc-ai-pbrief-kind">${escapeHtml(BRIEF_KIND[b.type] || b.type || '')} · ${escapeHtml(periodText(b))}</div>
            <span class="bc-badge ${ai ? 'bc-badge-primary' : 'bc-badge-muted'}" data-src="${ai ? 'ai' : 'quy-tac'}">${ai ? 'AI' : 'Quy tắc'}</span>
        </div>
        <h3 class="bc-ai-title">${escapeHtml(b.title)}</h3>
        ${parts.map((p) => `<div class="bc-ai-pbrief-part" data-part="${escapeHtml(p.key)}">
            <div class="bc-ai-sub">${escapeHtml(p.title)}</div>
            <ul class="bc-ai-advice">${p.items.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul></div>`).join('')}
        ${admin && b.model ? `<div class="bc-ai-tech">${escapeHtml(b.model)}</div>` : ''}
    </article>`;
}

function paintBriefs(f) {
    const bs = Array.isArray(f.briefs) ? f.briefs : [];
    fill('tl-briefs', bs.length ? `<div class="bc-ai-pbriefs">${bs.map(periodBriefHtml).join('')}</div>` : '');
}

function paintChips() {
    const list = st.feed?.insights || [];
    if (!list.length) { fill('tl-chips', ''); return; }
    const gs = groups(list);
    if (st.group !== 'all' && !gs.some((g) => g.key === st.group)) st.group = 'all';
    const chip = (key, label, count) => `<button type="button" role="tab" class="bc-tab ${key === st.group ? 'bc-active' : ''}"
        data-chip="${escapeHtml(key)}" aria-selected="${key === st.group}">${escapeHtml(label)}<span class="bc-tab-count">${fmtNum(count)}</span></button>`;
    fill('tl-chips', `<div class="bc-tabs bc-ai-chips" role="tablist">${chip('all', 'Tất cả', list.length)}${gs.map((g) => chip(g.key, g.label, g.count)).join('')}</div>`);
}

function paintList() {
    const list = st.feed?.insights || [];
    if (!list.length) {
        fill('tl-list', emptyState({ icon: '✅', title: 'Không có việc cần chú ý' }));
        return;
    }
    const shown = st.group === 'all' ? list : list.filter((x) => groupKey(x) === st.group);
    fill('tl-list', shown.map(cardHtml).join(''));
}

function paintTools() {
    if (!isAdmin()) return;
    fill('tl-tools', `<label class="bc-ai-toggle"><input type="checkbox" role="switch" class="bc-switch" id="tl-closed" ${st.closed ? 'checked' : ''}>
        <span>Xem cả việc đã đóng (30 ngày)</span></label>`);
}

/** Báo shell số việc đang mở (chấm đỏ trên menu) — không gọi thêm API. */
function announce() {
    const list = (st.feed?.insights || []).filter((x) => OPEN.includes(x.status));
    const detail = { do: list.filter((x) => x.severity === 'do').length, vang: list.filter((x) => x.severity !== 'do').length };
    window.dispatchEvent(new CustomEvent('bc:ai-badge', { detail }));
}

async function load(isCurrent) {
    const my = ++seq;
    const alive = () => my === seq && isCurrent();
    fill('tl-list', skeleton(140, 3, 10));
    try {
        const f = await api.ai.feed(st.closed && isAdmin());
        if (!alive()) return;
        st.feed = f;
        paintHead(f);
        paintBriefs(f);
        paintTools();
        paintChips();
        paintList();
        announce();
    } catch (err) {
        if (!alive()) return;
        fill('tl-brief', '');
        fill('tl-briefs', '');
        fill('tl-stale', '');
        fill('tl-chips', '');
        fill('tl-list', errorState(err));
    }
}

// ─── Tương tác ───────────────────────────────────────────────────────────────
function cardEl(id) { return document.querySelector(`[data-ai-card="${CSS.escape(id)}"]`); }

function flash(id) {
    if (!(st.feed?.insights || []).some((x) => x.id === id)) return;
    if (!cardEl(id)) { st.group = 'all'; paintChips(); paintList(); }
    const el = cardEl(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.remove('bc-ai-flash');
    void el.offsetWidth;  // chạy lại hiệu ứng khi bấm lại cùng dòng
    el.classList.add('bc-ai-flash');
    setTimeout(() => el.classList.remove('bc-ai-flash'), 1800);
}

/** Thay MỘT thẻ bằng nhận định máy chủ trả về, giữ nguyên chỗ đang xem. */
function replaceCard(x) {
    const list = st.feed.insights;
    const i = list.findIndex((y) => y.id === x.id);
    if (i >= 0) list[i] = { ...list[i], ...x };
    const el = cardEl(x.id);
    if (!el) return;
    const top = el.getBoundingClientRect().top;
    el.outerHTML = cardHtml(i >= 0 ? list[i] : x);
    const now = cardEl(x.id);
    if (now) window.scrollBy(0, now.getBoundingClientRect().top - top);
    paintChips();
    announce();
}

const DONE = { 'mo': 'Đã mở lại', 'dang-xu-ly': 'Đã chuyển sang Đang xử lý', 'bo-qua-7': 'Đã bỏ qua 7 ngày',
    'bo-qua-30': 'Đã bỏ qua 30 ngày', 'bo-qua': 'Đã bỏ qua hẳn', 'note': 'Đã lưu ghi chú' };

async function onAction(btn) {
    const card = btn.closest('[data-ai-card]');
    const id = card?.dataset.aiCard;
    const x = (st.feed?.insights || []).find((y) => y.id === id);
    if (!x) return;
    const act = btn.dataset.act;
    let status = act, days, note;
    if (act === 'bo-qua-7' || act === 'bo-qua-30') { status = 'bo-qua'; days = act === 'bo-qua-7' ? 7 : 30; }
    if (act === 'note') {
        status = x.status;
        note = card.querySelector('.bc-ai-note')?.value ?? '';
        // Chỉ lưu ghi chú: giữ hạn bỏ qua đang có (máy chủ hiểu mute_days trống = bỏ qua hẳn).
        if (x.status === 'bo-qua' && x.mute_until) days = Math.max(1, daysBetween(serverToday(), String(x.mute_until).slice(0, 10)));
    }
    card.querySelectorAll('[data-act]').forEach((b) => { b.disabled = true; });
    try {
        const res = await api.ai.setStatus(id, status, days, note);
        replaceCard(res);
        showToast(DONE[act] || 'Đã lưu', 'success');
    } catch (err) {
        showToast(err.message, 'error');
        card.querySelectorAll('[data-act]').forEach((b) => { b.disabled = false; });
    }
}

export async function render({ container, isCurrent }) {
    st.feed = null;
    container.innerHTML = `<div id="tl-root">
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Trợ lý AI</div>
                <div class="bc-view-banner-sub" id="tl-sub">Đang tải…</div></div>
            <span class="bc-view-banner-badge" id="tl-mode">…</span>
        </div>
        <div id="tl-qa"></div>
        <div id="tl-alert"></div>
        <div id="tl-stale"></div>
        <div id="tl-brief">${skeleton(120)}</div>
        <div id="tl-briefs"></div>
        ${isAdmin() ? '<div class="bc-filter-bar bc-ai-tools" id="tl-tools"></div>' : ''}
        <div id="tl-chips"></div>
        <div id="tl-list" class="bc-ai-list"></div>
        <div class="bc-note bc-mt-3">${escapeHtml(NOTE)}</div></div>`;
    const root = document.getElementById('tl-root');  // nghe trên phần tử của màn (container dùng chung mọi màn)
    root.addEventListener('click', (e) => {
        const b = e.target.closest('[data-brief]');
        if (b) { flash(b.dataset.brief); return; }
        const c = e.target.closest('[data-chip]');
        if (c) { st.group = c.dataset.chip; paintChips(); paintList(); return; }
        const a = e.target.closest('[data-act]');
        if (a && isAdmin()) onAction(a);
    });
    root.addEventListener('change', (e) => {
        if (e.target.id === 'tl-closed') { st.closed = e.target.checked; load(isCurrent); }
    });
    qaButton(isCurrent);
    await load(isCurrent);
}

/** Nút "Hỏi trợ lý" (#/hoi-dap) — chỉ khi get_qa().enabled; lỗi / lib/api.js cũ (tab mở trước deploy) → không có nút. */
async function qaButton(isCurrent) {
    try {
        const q = await api.ai.qa();
        if (!isCurrent() || !q?.enabled) return;
        fill('tl-qa', `<div class="bc-ai-qa-bar"><a class="bc-btn bc-btn-primary bc-btn-sm" id="tl-qa-btn" href="#/hoi-dap">
            <i class="fas fa-comments"></i> Hỏi trợ lý</a></div>`);
    } catch { /* không có nút */ }
}
