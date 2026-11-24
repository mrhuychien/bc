// #/hoi-dap — Hỏi đáp với Trợ lý AI (P3). Vào từ nút "Hỏi trợ lý" trên #/tro-ly; không có mục menu. Máy chủ chặn
// bằng _guard("tro-ly") — mảng Trợ lý AI ẩn với người xem thì shell không đăng ký route này (chuyển về #/tro-ly).
// bc.api.ai.get_qa → bật / còn mấy câu; ask(question, history) → {id}; get_answer(id) hỏi lại mỗi 2 giây, tối đa
// 180 giây (máy chủ dừng câu hỏi trong 150 giây kể từ lúc hỏi — chờ thêm 30 giây để luôn lấy được kết quả cuối). Lịch sử hỏi đáp CHỈ nằm trong bộ nhớ của tab (biến của module — tải lại trang là mất, không lưu đâu cả);
// 3 lượt hỏi đáp xong gần nhất gửi kèm câu mới làm `history`.
// Lời trả lời là VĂN BẢN THUẦN: mọi chuỗi máy chủ qua escapeHtml, giữ xuống dòng; đoạn u = true (số máy chưa đối
// chiếu được) gạch chấm + title "chưa kiểm". Câu SQL đã chạy chỉ vẽ cho quản trị (System Manager) — người xem không
// có khối đó trong DOM kể cả khi máy chủ lỡ gửi.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtNum } from '../lib/format.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

const POLL_MS = 2000;
const POLL_MAX_MS = (150 + 30) * 1000;   // = qa.TOTAL_SECONDS + 30
const HISTORY_TURNS = 3;
const NOTE = 'ⓘ Trợ lý chỉ đọc đúng số liệu bạn xem được trên các màn báo cáo. Câu trả lời do mô hình ngôn ngữ viết; '
    + 'số gạch chấm là số máy chưa đối chiếu được.';
const UNV_NOTE = 'Số gạch chấm: máy chưa đối chiếu được với số liệu đã tra — kiểm lại ở màn gốc trước khi dùng.';
const WAIT = 'Đang tra số liệu…';
const TIMEOUT = 'Quá 3 phút chưa có câu trả lời. Câu hỏi có thể vẫn đang chạy — thử hỏi lại sau ít phút.';

// Trạng thái của PHIÊN TRÌNH DUYỆT (sống cùng module, mất khi tải lại trang). items: cũ → mới.
// item = {key, q, id, status: 'cho' | 'xong' | 'loi' | 'het-gio', t0, segments, unverified, sources, steps, message}
const S = { qa: null, items: [], busy: false, draft: '' };
let keySeq = 0;
const isAdmin = () => !!window.BC_CONTEXT?.isSysManager;
const maxLen = () => Math.max(1, Number(S.qa?.max_question) || 500);

/** href chỉ khi route là đường dẫn nội bộ "#/…" — chuỗi khác (javascript:, http…) không thành link. */
function safeRoute(r) { return typeof r === 'string' && /^#\/[a-z0-9-]*$/.test(r) ? r : ''; }

function segs(x) { return (Array.isArray(x.segments) ? x.segments : []).filter((s) => s && typeof s === 'object'); }

/** Lời trả lời dạng chữ (cho history gửi kèm câu sau). */
function plain(x) { return segs(x).map((s) => String(s.t ?? '')).join(''); }

function history() {
    return S.items.filter((x) => x.status === 'xong').slice(-HISTORY_TURNS).map((x) => ({ q: x.q, a: plain(x) }));
}

const pending = () => S.items.some((x) => x.status === 'cho');
const remaining = () => Math.max(0, Number(S.qa?.remaining) || 0);

// ─── Vẽ ──────────────────────────────────────────────────────────────────────
function answerHtml(x) {
    const ss = segs(x);
    const body = ss.map((s) => (s.u
        ? `<span class="bc-ai-qa-unv" title="chưa kiểm">${escapeHtml(s.t)}</span>`
        : escapeHtml(s.t))).join('');
    const unv = ss.some((s) => s.u);
    const src = (Array.isArray(x.sources) ? x.sources : []).filter((s) => s && s.label);
    const sql = isAdmin() ? (Array.isArray(x.steps) ? x.steps : []).filter((s) => s && typeof s.sql === 'string' && s.sql.trim()) : [];
    return `<div class="bc-ai-qa-a">${body || '<span class="bc-ai-qa-none">(Trợ lý không viết gì.)</span>'}</div>
        ${unv ? `<div class="bc-ai-qa-unv-note">${escapeHtml(UNV_NOTE)}</div>` : ''}
        ${src.length ? `<div class="bc-ai-qa-src">Đã tra: ${src.map((s) => {
            const r = safeRoute(s.route);
            return r ? `<a href="${escapeHtml(r)}">${escapeHtml(s.label)}</a>` : `<span>${escapeHtml(s.label)}</span>`;
        }).join(', ')}</div>` : ''}
        ${sql.length ? `<details class="bc-ai-qa-sql"><summary>Câu SQL đã chạy (${fmtNum(sql.length)})</summary>
            ${sql.map((s) => `<div class="bc-ai-qa-sql-step">${s.label ? `<div class="bc-ai-sub">${escapeHtml(s.label)}</div>` : ''}
                <pre>${escapeHtml(s.sql)}</pre></div>`).join('')}</details>` : ''}`;
}

function itemHtml(x) {
    let main = '';
    if (x.status === 'cho') {
        const sec = Math.max(0, Math.floor((Date.now() - x.t0) / 1000));
        main = `<div class="bc-ai-qa-wait" role="status"><span class="bc-ai-qa-spin" aria-hidden="true"></span>${escapeHtml(WAIT)}
            <span class="bc-ai-qa-sec">${fmtNum(sec)} giây</span></div>`;
    } else if (x.status === 'xong') {
        main = answerHtml(x);
    } else {
        main = `<div class="bc-alert bc-ai-qa-err" role="alert">${escapeHtml(x.message || 'Trợ lý không trả lời được câu này.')}</div>`;
    }
    return `<article class="bc-card bc-ai-qa-item" data-qa="${escapeHtml(x.key)}" data-state="${escapeHtml(x.status)}">
        <div class="bc-ai-qa-q"><span class="bc-ai-sub">Bạn hỏi</span><div class="bc-ai-qa-qtext">${escapeHtml(x.q)}</div></div>
        <div class="bc-ai-qa-ans"><span class="bc-ai-sub">Trợ lý</span>${main}</div>
    </article>`;
}

function paintList() {
    const items = S.items.slice().reverse();  // mới nhất trên cùng, ngay dưới ô hỏi
    fill('hd-list', items.length ? items.map(itemHtml).join('')
        : `<div class="bc-ai-qa-empty">Chưa có câu hỏi nào trong phiên này. Hỏi về số liệu trên các màn báo cáo, ví dụ
            "Phải thu quá hạn hiện bao nhiêu?"</div>`);
}

function paintItem(x) {
    const el = document.querySelector(`[data-qa="${CSS.escape(x.key)}"]`);
    if (el) el.outerHTML = itemHtml(x); else paintList();
}

function paintLeft() {
    const n = remaining();
    fill('hd-left', n > 0 ? `Còn ${fmtNum(n)} câu hôm nay` : 'Đã hết lượt hỏi hôm nay');
    const el = document.getElementById('hd-left');
    if (el) el.dataset.remaining = String(n);
}

function paintForm() {
    const ta = document.getElementById('hd-q');
    const btn = document.getElementById('hd-ask');
    if (!ta || !btn) return;
    const len = ta.value.length;
    fill('hd-count', `${fmtNum(len)}/${fmtNum(maxLen())}`);
    const why = pending() ? 'Đang chờ câu trả lời trước' : (remaining() <= 0 ? 'Đã hết lượt hỏi hôm nay' : '');
    btn.disabled = S.busy || !!why || !ta.value.trim();
    btn.title = why;
}

function paintAll() {
    if (!document.getElementById('hd-root')) return;  // đã rời màn — trạng thái vẫn giữ, vẽ lại khi quay về
    paintLeft();
    paintList();
    paintForm();
}

// ─── Hỏi + chờ ───────────────────────────────────────────────────────────────
function setCounts(r) {
    if (!S.qa || !r) return;
    if (r.used !== undefined && r.used !== null) S.qa.used = Number(r.used) || 0;
    if (r.remaining !== undefined && r.remaining !== null) S.qa.remaining = Number(r.remaining) || 0;
}

async function poll(x) {
    if (x.status !== 'cho') return;
    let r;
    try {
        r = await api.ai.answer(x.id);
    } catch (err) {
        // 403 / 417: máy chủ đã từ chối hẳn (mảng bị ẩn, …) → dừng. Lỗi mạng thoáng qua → thử lại tới hết giờ.
        if (err?.status === 403 || err?.status === 417) {
            Object.assign(x, { status: 'loi', message: err.message });
            done(x);
            return;
        }
    }
    if (r && r.status === 'xong') {
        Object.assign(x, { status: 'xong', segments: r.segments, unverified: r.unverified, sources: r.sources, steps: r.steps });
        setCounts(r);
        done(x);
        return;
    }
    if (r && r.status === 'loi') {
        Object.assign(x, { status: 'loi', message: r.message });
        setCounts(r);
        done(x);
        return;
    }
    if (Date.now() - x.t0 >= POLL_MAX_MS) {
        Object.assign(x, { status: 'het-gio', message: TIMEOUT });
        done(x);
        return;
    }
    if (document.getElementById('hd-root')) paintItem(x);  // số giây chờ
    x.timer = setTimeout(() => poll(x), POLL_MS);
}

function done(x) {
    clearTimeout(x.timer);
    if (!document.getElementById('hd-root')) return;
    paintItem(x);
    paintLeft();
    paintForm();
}

async function ask() {
    const ta = document.getElementById('hd-q');
    const q = (ta?.value || '').trim();
    if (!q || S.busy || pending() || remaining() <= 0) return;
    S.busy = true;
    paintForm();
    try {
        const r = await api.ai.ask(q.slice(0, maxLen()), history());
        if (!r || !r.id) throw new Error('Máy chủ không nhận câu hỏi.');
        const x = { key: `q${++keySeq}`, q, id: String(r.id), status: 'cho', t0: Date.now() };
        S.items.push(x);
        if (S.qa) {  // máy chủ đếm câu ngay khi nhận; get_answer trả số chính xác khi xong
            S.qa.used = (Number(S.qa.used) || 0) + 1;
            S.qa.remaining = Math.max(0, remaining() - 1);
        }
        S.draft = '';
        const t = document.getElementById('hd-q');
        if (t) t.value = '';
        x.timer = setTimeout(() => poll(x), POLL_MS);
    } catch (err) {
        // Lời từ chối của máy chủ (tắt, hết lượt, vượt trần, đang có câu khác) — giữ nguyên câu hỏi trong ô.
        showToast(err.message, 'error', 6000);
        fill('hd-err', `<div class="bc-alert bc-ai-qa-err" role="alert">${escapeHtml(err.message)}</div>`);
    } finally {
        S.busy = false;
        paintAll();
    }
}

// ─── Màn ─────────────────────────────────────────────────────────────────────
function disabledHtml() {
    const admin = isAdmin();
    return emptyState({ icon: '🔒', title: 'Hỏi đáp đang tắt',
        message: admin ? 'Bật "Hỏi đáp" (ai_qa_enabled) trong BC Settings, mục Trợ lý AI, và khai khoá Claude.'
            : 'Quản trị chưa bật hỏi đáp với trợ lý.',
        action: `<div class="bc-ai-qa-actions">${admin ? '<a class="bc-btn bc-btn-sm" href="/app/bc-settings" target="_blank" rel="noopener">'
            + '<i class="fas fa-gear"></i> BC Settings</a>' : ''}<a class="bc-btn bc-btn-sm" href="#/tro-ly">‹ Về Trợ lý AI</a></div>` });
}

function formHtml() {
    const n = maxLen();
    return `<div class="bc-card bc-ai-qa-form">
        <label class="bc-ai-qa-label" for="hd-q">Câu hỏi về số liệu của công ty</label>
        <textarea id="hd-q" class="bc-input bc-ai-qa-input" rows="3" maxlength="${n}"
            placeholder="Ví dụ: Tồn kho thành phẩm hiện bao nhiêu? Khách nào nợ quá hạn nhiều nhất?">${escapeHtml(S.draft)}</textarea>
        <div class="bc-ai-qa-formbar">
            <span class="bc-ai-qa-count" id="hd-count" aria-live="polite">0/${fmtNum(n)}</span>
            <button type="button" class="bc-btn bc-btn-primary" id="hd-ask" disabled><i class="fas fa-paper-plane"></i> Hỏi</button>
        </div>
        <div id="hd-err"></div>
    </div>`;
}

export async function render({ container, isCurrent }) {
    container.innerHTML = `<div id="hd-root">
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Hỏi trợ lý</div>
                <div class="bc-view-banner-sub" id="hd-left">Đang tải…</div></div>
            <a class="bc-view-banner-badge bc-ai-qa-back" href="#/tro-ly">‹ Trợ lý AI</a>
        </div>
        <div id="hd-main">${skeleton(140)}</div>
        <div class="bc-note bc-mt-3">${escapeHtml(NOTE)}</div></div>`;
    let qa;
    try {
        qa = await api.ai.qa();
    } catch (err) {
        if (!isCurrent()) return;
        fill('hd-left', '');
        fill('hd-main', errorState(err));
        return;
    }
    if (!isCurrent()) return;
    S.qa = qa || {};
    if (!S.qa.enabled) {
        fill('hd-left', '');
        fill('hd-main', disabledHtml());
        return;
    }
    fill('hd-main', `${formHtml()}<div id="hd-list" class="bc-ai-qa-list"></div>`);
    const root = document.getElementById('hd-root');
    const ta = document.getElementById('hd-q');
    ta.addEventListener('input', () => { S.draft = ta.value; fill('hd-err', ''); paintForm(); });
    ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(); }
    });
    root.addEventListener('click', (e) => { if (e.target.closest('#hd-ask')) ask(); });
    paintAll();
}
