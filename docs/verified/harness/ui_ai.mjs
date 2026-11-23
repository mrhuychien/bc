// Kiểm màn Trợ lý AI trên server thử thật (seed_ui_ai.py serve — LLM giả, hàng đợi giả, chặn mạng):
//   node ui_ai.mjs <viewerBase> <adminBase> fresh|stale
// #/tro-ly (người xem + quản trị) và #/ai (quản trị), desktop 1280px + điện thoại 390px: không lỗi JS / HTTP, không cuộn
// ngang trang; số thẻ / số trên chip = API; người xem không có nút quản trị, chứng từ, ghi chú quản trị, dòng kỹ thuật;
// chuỗi XSS / markdown hiện thành chữ, route không phải "#/…" không thành link, giữ xuống dòng; bản tin ≤ 5 dòng, bấm thì
// cuộn tới thẻ; chip lọc đúng; chấm đỏ menu theo get_badge (một lần, không nhân đôi); thao tác quản trị đi tới máy chủ
// thật (đang xử lý / bỏ qua 7 ngày / ghi chú giữ hạn bỏ qua / mở lại / xem việc đã đóng); #/ai: bảng quy tắc, lượt chạy,
// thử kết nối, chạy ngay (chỉ xếp hàng — pipeline KHÔNG chạy), lưu quy tắc bền qua tải lại. fresh: lượt ok mới, AI bật;
// stale: lượt ok cũ (> 26 giờ), AI tắt, trần 0, chưa khai giá, không việc đỏ.
// Chạy lại phải seed lại (bộ thử đổi dữ liệu): BC_TEST_DB=bc_test_ai_ui python3 -B seed_ui_ai.py fresh
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const VB = process.argv[2] || 'http://127.0.0.1:8128';
const AB = process.argv[3] || 'http://127.0.0.1:8129';
const PASS = process.argv[4] || 'fresh';
const FRESH = PASS === 'fresh';
const FAKE_KEY = 'sk-ant-api03-GIA-chi-de-thu-ui-0a1b2c3d4e5f';   // = seed_ui_ai.FAKE_KEY
const XSS = '<img src=x onerror=window.__xss=1>';
const GROUP_ORDER = ['kinh-doanh', 'kho-sx', 'van-chuyen', 'tai-chinh', 'nhan-su', 'attp', 'he-thong'];  // registry.GROUPS
const NOTE = 'ⓘ Tín hiệu do quy tắc tính trên cùng số liệu với các màn báo cáo. Phần lời có nhãn AI do mô hình ngôn ngữ '
    + 'viết; mọi con số trong lời do máy chủ chèn từ số liệu gốc. Cập nhật 5:30 mỗi sáng.';
let n = 0, bad = 0;
function check(label, ok, detail = '') {
    n++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 500)}`); }
}
const flat = (s) => (s || '').replace(/\s+/g, ' ').trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Gọi API trong trang (cùng phiên / vai của server đó) → {status, message}. */
function api(page, method, args = {}) {
    return page.evaluate(async ([m, a]) => {
        const body = new URLSearchParams();
        for (const [k, v] of Object.entries(a)) if (v !== undefined && v !== null) body.append(k, String(v));
        const r = await fetch(`/api/method/bc.api.ai.${m}?t=1`, { method: 'POST', body });  // ?t=1: lời gọi của bộ thử, không đếm
        let j = {};
        try { j = await r.json(); } catch { /* */ }
        return { status: r.status, message: j.message, j };
    }, [method, args]);
}

async function newPage(browser, mobile) {
    const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
        : { viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    const errors = [];
    const ignore = new Set();   // URL lỗi CỐ Ý của kịch bản (giả lập lỗi máy chủ)
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    // HTTP lỗi bắt ở 'response' (dòng console "Failed to load resource" của cùng lượt đó bỏ qua để không đếm hai lần).
    page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
    page.on('response', (r) => {
        const m = (r.url().split('/api/method/')[1] || '').split('?')[0];
        if (r.status() >= 400 && !r.url().endsWith('favicon.ico') && !ignore.has(m)) errors.push(`${r.status()} ${r.url()}`);
    });
    const reqs = [];
    page.on('request', (r) => { if (r.url().includes('/api/method/')) reqs.push({ m: r.url().split('/api/method/')[1], body: r.postData() || '', t: Date.now() }); });
    return { ctx, page, errors, ignore, reqs };
}

async function overflowOk(page, tag) {
    const o = await page.evaluate(() => document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth);
    check(`${tag}: không cuộn ngang trang (${o}px)`, o <= 1);
}

async function gotoTroLy(page, base) {
    await page.goto(`${base}/bc#/tro-ly`);
    await waitTroLy(page);
}
async function waitTroLy(page) {
    await page.waitForFunction(() => document.querySelector('#tl-mode') && document.querySelector('#tl-mode').textContent !== '…'
        && !document.querySelector('#tl-root .bc-skeleton'), null, { timeout: 20000 });
}

const cardsInfo = (page) => page.$$eval('[data-ai-card]', (els) => els.map((e) => ({ id: e.dataset.aiCard, group: e.dataset.group,
    text: e.textContent.replace(/\s+/g, ' ').trim() })));
const chipsInfo = (page) => page.$$eval('[data-chip]', (els) => els.map((e) => ({ key: e.dataset.chip,
    count: e.querySelector('.bc-tab-count')?.textContent.trim(), label: e.childNodes[0]?.textContent.trim(), active: e.classList.contains('bc-active') })));

function expectChips(ins) {
    const m = new Map();
    for (const x of ins) {
        const k = x.group || 'khac';
        if (!m.has(k)) m.set(k, { key: k, label: x.group_label || 'Khác', count: 0 });
        m.get(k).count++;
    }
    const rk = (k) => (GROUP_ORDER.indexOf(k) < 0 ? 99 : GROUP_ORDER.indexOf(k));
    return [{ key: 'all', label: 'Tất cả', count: ins.length }, ...[...m.values()].sort((a, b) => rk(a.key) - rk(b.key))];
}

/** Kiểm chung #/tro-ly cho một vai. */
async function troLyCommon(page, admin, tag) {
    const feed = (await api(page, 'get_feed')).message;
    const ins = feed.insights;
    const cs = await cardsInfo(page);
    check(`${tag}: số thẻ = số nhận định API (${ins.length})`, cs.length === ins.length && cs.every((c, i) => c.id === ins[i].id),
        JSON.stringify(cs.map((c) => c.id)));
    const ch = await chipsInfo(page);
    const ex = expectChips(ins).map((c) => `${c.key}:${c.label}:${c.count}`);
    check(`${tag}: chip nhóm + số = API, đúng thứ tự GROUPS`, JSON.stringify(ch.map((c) => `${c.key}:${c.label}:${c.count}`)) === JSON.stringify(ex),
        `${JSON.stringify(ch)} ≠ ${JSON.stringify(ex)}`);
    check(`${tag}: ${admin ? 'có' : 'không có'} chip Hệ thống`, admin === ch.some((c) => c.key === 'he-thong')
        && admin === ins.some((x) => x.group === 'he-thong'));
    // Banner
    const sub = flat(await page.textContent('#tl-sub'));
    const mode = flat(await page.textContent('#tl-mode'));
    const lastOk = feed.meta.last_ok ? (() => { const [d, t] = feed.meta.last_ok.split(' '); const [y, mo, dd] = d.split('-'); return `${dd}/${mo}/${y} ${t.slice(0, 5)}`; })() : null;
    check(`${tag}: banner "Cập nhật ${lastOk}"`, lastOk ? sub.includes(`Cập nhật ${lastOk}`) : sub.includes('Chưa chạy lần nào'), sub);
    check(`${tag}: badge chế độ "${feed.meta.ai_on ? 'AI' : 'Quy tắc'}" theo meta.ai_on`, mode === (feed.meta.ai_on ? 'AI' : 'Quy tắc'), mode);
    const alert = await page.$('#tl-alert .bc-alert');
    const at = alert ? flat(await alert.textContent()) : '';
    check(`${tag}: cảnh báo cũ ${feed.meta.stale ? 'có (đỏ)' : 'không có'}`, feed.meta.stale
        ? (at === `Trợ lý chưa chạy từ ${lastOk} — số dưới đây có thể đã cũ.` && await alert.evaluate((e) => e.classList.contains('bc-ai-alert-do')))
        : !alert, at);
    check(`${tag}: meta.stale = ${FRESH ? 'false' : 'true'} ở lượt ${PASS}`, feed.meta.stale === !FRESH);
    // Bản tin
    const bi = await page.$$eval('[data-brief]', (els) => els.map((e) => ({ id: e.dataset.brief, t: e.textContent })));
    const exB = (feed.brief?.items || []).slice(0, 5);
    check(`${tag}: bản tin ${exB.length} dòng (≤ 5) = API`, bi.length === exB.length && bi.length <= 5
        && bi.every((b, i) => b.id === exB[i].id && b.t === exB[i].title), JSON.stringify(bi));
    if (feed.brief) check(`${tag}: tiêu đề bản tin`, flat(await page.textContent('.bc-ai-brief .bc-card-title')).includes(feed.brief.title));
    // Chân trang
    const notes = await page.$$eval('#tl-root > .bc-note', (els) => els.map((e) => e.textContent.trim()));
    check(`${tag}: chân trang đúng câu đặc tả §8.8`, notes.includes(NOTE), JSON.stringify(notes));
    // Quyền
    const adm = await page.$$eval('#tl-root .bc-ai-admin, #tl-root [data-act], #tl-root .bc-ai-docs, #tl-root .bc-ai-tech, #tl-closed, #tl-root .bc-ai-note',
        (els) => els.length);
    check(`${tag}: ${admin ? 'có' : 'KHÔNG có'} điều khiển quản trị trong DOM`, admin ? adm > 0 : adm === 0, `${adm} phần tử`);
    // Mọi thẻ: meta line, link chỉ khi route "#/…"
    for (const x of ins) {
        const info = await page.$eval(`[data-ai-card="${x.id}"]`, (e) => ({ meta: e.querySelector('.bc-ai-meta')?.textContent.trim(),
            go: e.querySelector('a.bc-ai-go') ? { href: e.querySelector('a.bc-ai-go').getAttribute('href'), t: e.querySelector('a.bc-ai-go').textContent.trim() } : null,
            title: e.querySelector('.bc-ai-title')?.textContent, sev: e.classList.contains('bc-ai-do') ? 'do' : 'vang',
            advice: [...e.querySelectorAll('.bc-ai-advice li')].map((l) => l.textContent),
            badges: [...e.querySelectorAll('.bc-ai-badges .bc-badge')].map((b) => b.textContent.trim()) }));
        const meta = `${x.days} ngày · ${x.section_label} · ${x.source === 'ai' ? 'AI' : 'Quy tắc'}`;
        const goOk = x.route.startsWith('#/') ? (info.go && info.go.href === x.route && info.go.t.startsWith(`Xem ở màn ${x.section_label}`)) : info.go === null;
        const bx = [];
        if (x.status === 'dang-xu-ly') bx.push('Đang xử lý');
        if (x.review_verdict === 'nghi-ngo') bx.push('Cần kiểm chứng');
        if (admin && x.status === 'bo-qua') bx.push(x.mute_until ? `Đang bỏ qua đến ${x.mute_until.slice(8, 10)}/${x.mute_until.slice(5, 7)}/${x.mute_until.slice(0, 4)}` : 'Đang bỏ qua hẳn');
        if (admin && x.status === 'dong') bx.push('Đã đóng');
        if (admin && x.needs_check) bx.push('Lời AI bị loại');
        if (admin && x.audience === 'quan-tri') bx.push('Chỉ quản trị');
        const ok = info.meta === meta && goOk && info.title === x.title && info.sev === x.severity
            && JSON.stringify(info.advice) === JSON.stringify(x.advice) && JSON.stringify(info.badges) === JSON.stringify(bx);
        check(`${tag}: thẻ ${x.id} (tiêu đề, mức, khuyến nghị, "${meta}", nút xem ${x.route.startsWith('#/') ? x.route : 'không có'}, badge ${bx.join('/') || '—'})`,
            ok, JSON.stringify(info));
    }
    // Chuỗi XSS / markdown là chữ
    const xss = await page.evaluate(() => ({ flag: window.__xss, img: document.querySelectorAll('#tl-root img').length,
        js: [...document.querySelectorAll('a[href]')].filter((a) => /^\s*javascript:/i.test(a.getAttribute('href'))).length }));
    check(`${tag}: XSS không chạy (window.__xss trống, không <img> trong màn, không link javascript:)`, xss.flag === undefined && xss.img === 0 && xss.js === 0,
        JSON.stringify(xss));
    const x1 = ins.find((x) => x.title.includes(XSS));
    if (x1) {
        const tt = await page.$eval(`[data-ai-card="${x1.id}"] .bc-ai-title`, (e) => e.textContent);
        check(`${tag}: tiêu đề có "${XSS}" và "**bold**" hiện nguyên chữ`, tt === x1.title && tt.includes('**bold**'), tt);
        const body = await page.$eval(`[data-ai-card="${x1.id}"] .bc-ai-body`, (e) => ({ it: e.innerText, ws: getComputedStyle(e).whiteSpace, kids: e.children.length }));
        check(`${tag}: nội dung giữ xuống dòng (pre-line), không phần tử HTML con`, body.ws === 'pre-line' && body.kids === 0
            && body.it.split('\n').length === x1.body.split('\n').length && body.it.includes('**bold**'), JSON.stringify(body));
    } else if (FRESH) check(`${tag}: seed có nhận định chứa XSS`, false);
    if (!admin) {
        const main = await page.textContent('#tl-root');
        check(`${tag}: người xem không thấy ghi chú quản trị / phản biện / nhận định mảng ẩn`, !main.includes('Đã nhắc') && !main.includes('Phản biện')
            && !ins.some((x) => x.section === 'phai-tra') && !main.includes('Việc H1') && !main.includes('Việc H2'), main.slice(0, 200));
    }
    return feed;
}

/** Chip lọc + bấm bản tin khi thẻ bị lọc ẩn. */
async function filtersAndBrief(page, feed, tag) {
    const ins = feed.insights;
    const chips = expectChips(ins).filter((c) => c.key !== 'all');
    for (const c of chips.slice(0, 3)) {
        await page.click(`[data-chip="${c.key}"]`);
        const cs = await cardsInfo(page);
        check(`${tag}: chip ${c.label} → ${c.count} thẻ đúng nhóm`, cs.length === c.count && cs.every((x) => x.group === c.key)
            && (await chipsInfo(page)).find((x) => x.key === c.key)?.active, JSON.stringify(cs.map((x) => x.group)));
    }
    const items = feed.brief?.items || [];
    if (items.length && chips.length > 1) {
        const target = items[0];
        const other = chips.find((c) => c.key !== (ins.find((x) => x.id === target.id).group || 'khac'));
        await page.click(`[data-chip="${other.key}"]`);
        const hidden = !(await page.$(`[data-ai-card="${target.id}"]`));
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.click(`[data-brief="${target.id}"]`);
        await sleep(900);
        const r = await page.$eval(`[data-ai-card="${target.id}"]`, (e) => {
            const b = e.getBoundingClientRect();
            return { top: b.top, bottom: b.bottom, h: innerHeight, flash: e.classList.contains('bc-ai-flash') };
        }).catch(() => null);
        const all = (await chipsInfo(page)).find((x) => x.key === 'all')?.active;
        check(`${tag}: bấm dòng bản tin khi thẻ bị lọc → về "Tất cả", cuộn tới thẻ ${target.id}, nhấp nháy`,
            hidden && all && r && r.top < r.h && r.bottom > 0 && r.flash, JSON.stringify({ hidden, all, r }));
        const cs = await cardsInfo(page);
        check(`${tag}: sau đó hiện đủ ${ins.length} thẻ`, cs.length === ins.length);
    }
}

async function dotCheck(page, reqs, mobile, tag) {
    const b = (await api(page, 'get_badge')).message;
    const want = Number(b.do) > 0 ? 1 : 0;
    const count = () => page.evaluate(() => ({ side: document.querySelectorAll('#bc-sidebar [data-route="/tro-ly"] .bc-ai-dot').length,
        more: document.querySelectorAll('#bc-nav-more .bc-ai-dot').length, all: document.querySelectorAll('.bc-ai-dot').length,
        label: document.querySelector('.bc-ai-dot')?.getAttribute('aria-label') || '' }));
    let c = await count();
    check(`${tag}: chấm đỏ menu ${want ? 'có' : 'không'} (get_badge.do = ${b.do}), có aria-label`, c.side === want && (!want || c.label.length > 3),
        JSON.stringify(c));
    // Dựng lại menu (đổi danh sách mảng ẩn) + vào lại màn: không nhân đôi chấm, không gọi lại get_badge.
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('bc:hidden-sections', { detail: window.BC_CONTEXT.hiddenSections || [] })));
    await page.evaluate(() => { location.hash = '#/tro-ly?lai=1'; });
    await waitTroLy(page);
    await sleep(300);
    c = await count();
    const calls = reqs.filter((r) => r.m === 'bc.api.ai.get_badge').length;
    check(`${tag}: sau dựng lại menu + vào lại màn: vẫn ${want} chấm ở mục Trợ lý AI, get_badge chỉ gọi 1 lần từ shell`,
        c.side === want && calls === 1, JSON.stringify({ c, calls }));
    if (mobile) {
        check(`${tag}: điện thoại — nút "Thêm" ${want ? 'có' : 'không'} chấm (Trợ lý AI nằm trong menu Thêm)`, c.more === want, JSON.stringify(c));
        await page.click('#bc-nav-more');
        await page.waitForSelector('.bc-menu-tile', { timeout: 5000 });
        const t = await page.evaluate(() => document.querySelectorAll('.bc-menu-tile[href="#/tro-ly"] .bc-ai-dot').length);
        check(`${tag}: menu Thêm — ô Trợ lý AI ${want ? 'có 1' : 'không có'} chấm`, t === want, t);
        await page.keyboard.press('Escape');
    }
}

// ─── Người xem ───────────────────────────────────────────────────────────────
async function viewer(browser) {
    for (const mobile of [false, true]) {
        const tag = `người xem ${mobile ? '390' : '1280'}`;
        console.log(`\n— ${tag}`);
        const { ctx, page, errors, reqs } = await newPage(browser, mobile);
        try {
            await gotoTroLy(page, VB);
            const feed = await troLyCommon(page, false, tag);
            await overflowOk(page, `${tag} #/tro-ly`);
            await filtersAndBrief(page, feed, tag);
            await dotCheck(page, reqs, mobile, tag);
            await overflowOk(page, `${tag} #/tro-ly sau thao tác`);
        } catch (e) { check(`${tag}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        check(`${tag}: không lỗi JS/HTTP`, errors.length === 0, errors.join(' | '));
        await ctx.close();
    }
    // Người xem mở #/ai: không có màn quản trị; API quản trị 403.
    const { ctx, page } = await newPage(browser, false);
    try {
        await page.goto(`${VB}/bc#/ai`);
        await page.waitForFunction(() => location.hash !== '#/ai', null, { timeout: 15000 }).catch(() => {});
        await sleep(500);
        const has = await page.$('.bc-ai-admin-screen, #ai-rules, #ai-run');
        check('người xem mở #/ai → không có màn cấu hình AI, bị đưa đi chỗ khác', !has && !(await page.evaluate(() => location.hash)).startsWith('#/ai'),
            await page.evaluate(() => location.hash));
        const r = await Promise.all(['get_admin', 'run_now', 'set_rule', 'test_connection', 'set_status'].map((m) => api(page, m,
            m === 'set_rule' ? { rule_key: 'x' } : m === 'set_status' ? { insight: 'A1', status: 'mo' } : m === 'test_connection' ? { provider: 'claude' } : {})));
        check('người xem gọi API quản trị → 403 cả 5 method', r.every((x) => x.status === 403), JSON.stringify(r.map((x) => x.status)));
    } catch (e) { check('người xem #/ai: kịch bản chạy hết', false, e.message.split('\n')[0]); }
    await ctx.close();
}

// ─── Quản trị: #/tro-ly ─────────────────────────────────────────────────────
async function adminTroLy(browser, vpage) {
    for (const mobile of [true, false]) {
        const tag = `quản trị ${mobile ? '390' : '1280'}`;
        console.log(`\n— ${tag} #/tro-ly`);
        const { ctx, page, errors, ignore, reqs } = await newPage(browser, mobile);
        try {
            await gotoTroLy(page, AB);
            const feed = await troLyCommon(page, true, tag);
            await overflowOk(page, `${tag} #/tro-ly`);
            const ins = feed.insights;
            for (const x of ins) {
                const acts = await page.$$eval(`[data-ai-card="${x.id}"] [data-act]`, (els) => els.map((e) => e.dataset.act));
                const ex = x.status === 'dong' ? [] : [...(x.status !== 'mo' ? ['mo'] : []), ...(x.status !== 'dang-xu-ly' ? ['dang-xu-ly'] : []),
                    ...(x.status !== 'bo-qua' ? ['bo-qua-7', 'bo-qua-30', 'bo-qua'] : []), 'note'];
                const extra = await page.$eval(`[data-ai-card="${x.id}"]`, (e) => ({ note: e.querySelector('.bc-ai-note')?.value,
                    docs: [...e.querySelectorAll('.bc-ai-docs a')].map((a) => [a.getAttribute('href'), a.target, a.rel, a.textContent.trim()]),
                    tech: e.querySelector('.bc-ai-tech')?.textContent || '', bold: e.querySelectorAll('b').length, rv: e.querySelector('.bc-ai-review')?.textContent || '' }));
                const exDocs = (x.documents || []).map((d) => [`/app/${encodeURIComponent(d.doctype.toLowerCase().replace(/ /g, '-'))}/${encodeURIComponent(d.name)}`,
                    '_blank', 'noopener', `${d.doctype} · ${d.name}`]);
                check(`${tag}: thẻ ${x.id} — nút theo trạng thái ${x.status} [${ex.join(',')}], ghi chú, chứng từ, phản biện, dòng kỹ thuật`,
                    JSON.stringify(acts) === JSON.stringify(ex) && extra.note === x.admin_note && JSON.stringify(extra.docs) === JSON.stringify(exDocs)
                    && extra.tech.includes(x.rule) && extra.bold === 0 && (x.review_note ? extra.rv.includes(x.review_note) : !extra.rv),
                    JSON.stringify({ acts, extra }));
            }
            if (FRESH) {
                const a1 = ins.find((x) => x.id === 'A1');
                check(`${tag}: chứng từ có ký tự đặc biệt → mã hoá trong link`, (a1?.documents || []).length === 2
                    && await page.$(`[data-ai-card="A1"] a[href="/app/sales-invoice/SI%2F2026%200001%26x"]`) !== null);
            }
            await dotCheck(page, reqs, mobile, tag);
            if (!mobile && FRESH) await adminActions(page, vpage, ignore, reqs, tag);
            await overflowOk(page, `${tag} #/tro-ly sau thao tác`);
        } catch (e) { check(`${tag}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        check(`${tag} #/tro-ly: không lỗi JS/HTTP`, errors.length === 0, errors.join(' | '));
        await ctx.close();
    }
}

async function toastText(page, re) {
    await page.waitForFunction((s) => [...document.querySelectorAll('.bc-toast')].some((t) => new RegExp(s).test(t.textContent)), re.source, { timeout: 8000 });
    return page.$$eval('.bc-toast', (els) => els.map((e) => ({ t: e.textContent.trim(), b: e.querySelectorAll('b').length })));
}

async function adminActions(page, vpage, ignore, reqs, tag) {
    const one = async (id) => (await api(page, 'get_feed', { closed: 1 })).message.insights.find((x) => x.id === id);
    const vids = async () => (await api(vpage, 'get_feed')).message.insights.map((x) => x.id);
    // Đang xử lý (A4) — giữ chỗ đang xem
    await page.$eval('[data-ai-card="A4"]', (e) => e.scrollIntoView({ block: 'center' }));
    const top0 = await page.$eval('[data-ai-card="A4"]', (e) => e.getBoundingClientRect().top);
    await page.click('[data-ai-card="A4"] [data-act="dang-xu-ly"]');
    await page.waitForSelector('[data-ai-card="A4"] [data-b="xu-ly"]', { timeout: 8000 });
    const top1 = await page.$eval('[data-ai-card="A4"]', (e) => e.getBoundingClientRect().top);
    check(`${tag}: "Đang xử lý" → badge hiện, API trả dang-xu-ly, thẻ giữ chỗ (${Math.round(top0)}→${Math.round(top1)})`,
        (await one('A4')).status === 'dang-xu-ly' && Math.abs(top1 - top0) <= 2
        && JSON.stringify(await page.$$eval('[data-ai-card="A4"] [data-act]', (els) => els.map((e) => e.dataset.act)))
            === JSON.stringify(['mo', 'bo-qua-7', 'bo-qua-30', 'bo-qua', 'note']));
    await toastText(page, /Đang xử lý/);
    // Bỏ qua 7 ngày (A5): hôm nay giả 27/10/2026 + 7 = 03/11/2026; người xem không còn A5
    check(`${tag}: trước khi bỏ qua, người xem có A5`, (await vids()).includes('A5'));
    await page.click('[data-ai-card="A5"] [data-act="bo-qua-7"]');
    await page.waitForSelector('[data-ai-card="A5"] [data-b="bo-qua"]', { timeout: 8000 });
    let a5 = await one('A5');
    check(`${tag}: "Bỏ qua 7 ngày" → badge "Đang bỏ qua đến 03/11/2026", API bo-qua 2026-11-03`,
        a5.status === 'bo-qua' && String(a5.mute_until).startsWith('2026-11-03')
        && flat(await page.textContent('[data-ai-card="A5"] [data-b="bo-qua"]')) === 'Đang bỏ qua đến 03/11/2026', JSON.stringify(a5));
    check(`${tag}: người xem không còn A5 sau khi bỏ qua`, !(await vids()).includes('A5'));
    // Lưu ghi chú khi đang bỏ qua: hạn bỏ qua giữ nguyên (mute_days tính theo hôm nay của máy chủ, không theo đồng hồ máy)
    const note = 'Đã giao <i>kho</i> xử lý';
    await page.fill('[data-ai-card="A5"] .bc-ai-note', note);
    await page.click('[data-ai-card="A5"] [data-act="note"]');
    await toastText(page, /Đã lưu ghi chú/);
    a5 = await one('A5');
    check(`${tag}: lưu ghi chú → admin_note lưu nguyên chữ, vẫn bỏ qua đến 03/11/2026`, a5.admin_note === note && a5.status === 'bo-qua'
        && String(a5.mute_until).startsWith('2026-11-03') && await page.$eval('[data-ai-card="A5"] .bc-ai-note', (e) => e.value) === note, JSON.stringify(a5));
    // Mở lại
    await page.click('[data-ai-card="A5"] [data-act="mo"]');
    await page.waitForFunction(() => !document.querySelector('[data-ai-card="A5"] [data-b="bo-qua"]'), null, { timeout: 8000 });
    a5 = await one('A5');
    check(`${tag}: "Mở lại" → mo, hết hạn bỏ qua, người xem thấy lại A5`, a5.status === 'mo' && !a5.mute_until && (await vids()).includes('A5'), JSON.stringify(a5));
    // Bỏ qua hẳn (A7) → mute_until trống
    await page.click('[data-ai-card="A7"] [data-act="bo-qua"]');
    await page.waitForSelector('[data-ai-card="A7"] [data-b="bo-qua"]', { timeout: 8000 });
    const a7 = await one('A7');
    check(`${tag}: "Bỏ qua hẳn" → bo-qua, không hạn, badge "Đang bỏ qua hẳn"`, a7.status === 'bo-qua' && !a7.mute_until
        && flat(await page.textContent('[data-ai-card="A7"] [data-b="bo-qua"]')) === 'Đang bỏ qua hẳn', JSON.stringify(a7));
    // Lỗi máy chủ → toast đúng lời máy chủ (chữ thuần), nút bấm lại được
    ignore.add('bc.api.ai.set_status');
    await page.route('**/bc.api.ai.set_status', (r) => r.fulfill({ status: 417, contentType: 'application/json',
        body: JSON.stringify({ exc_type: 'ValidationError', _server_messages: JSON.stringify([JSON.stringify({ message: 'Lỗi thử <b>máy chủ</b>' })]) }) }));
    await page.click('[data-ai-card="A6"] [data-act="dang-xu-ly"]');
    const ts = await toastText(page, /Lỗi thử/);
    const en = await page.$eval('[data-ai-card="A6"] [data-act="dang-xu-ly"]', (e) => !e.disabled);
    check(`${tag}: lỗi máy chủ → toast lời máy chủ, không HTML, nút bật lại`, ts.some((t) => t.t.includes('Lỗi thử máy chủ') && !t.b) && en, JSON.stringify(ts));
    await page.unroute('**/bc.api.ai.set_status');
    await sleep(200);
    ignore.delete('bc.api.ai.set_status');
    // Xem cả việc đã đóng
    const before = (await cardsInfo(page)).length;
    await page.check('#tl-closed');
    await page.waitForSelector('[data-ai-card="C1"]', { timeout: 8000 });
    await waitTroLy(page);
    const fc = (await api(page, 'get_feed', { closed: 1 })).message.insights;
    const cs = await cardsInfo(page);
    const c1 = await page.$$eval('[data-ai-card="C1"] [data-act]', (els) => els.length);
    check(`${tag}: "Xem cả việc đã đóng" → ${fc.length} thẻ = API closed=1, có C1 "Đã đóng" không nút, không C2 (đóng > 30 ngày)`,
        cs.length === fc.length && cs.length === before + 1 && c1 === 0 && !cs.some((c) => c.id === 'C2')
        && flat(await page.textContent('[data-ai-card="C1"] [data-b="dong"]')) === 'Đã đóng', JSON.stringify(cs.map((c) => c.id)));
    check(`${tag}: yêu cầu get_feed của màn gửi closed=1`, (reqs.filter((r) => r.m === 'bc.api.ai.get_feed').pop()?.body || '') === 'closed=1');
    await page.uncheck('#tl-closed');
    await page.waitForFunction(() => !document.querySelector('[data-ai-card="C1"]') && !document.querySelector('#tl-root .bc-skeleton')
        && document.querySelectorAll('[data-ai-card]').length > 0, null, { timeout: 8000 });
    check(`${tag}: tắt "đã đóng" → C1 biến mất`, (await cardsInfo(page)).length === before);
}

// ─── Quản trị: #/ai ─────────────────────────────────────────────────────────
async function waitAi(page) {
    await page.waitForFunction(() => document.querySelector('#ai-rules') && !document.querySelector('#ai-root .bc-skeleton'), null, { timeout: 20000 });
}

async function adminAi(browser) {
    for (const mobile of [true, false]) {
        const tag = `quản trị ${mobile ? '390' : '1280'} #/ai`;
        console.log(`\n— ${tag}`);
        const { ctx, page, errors, ignore, reqs } = await newPage(browser, mobile);
        try {
            await page.goto(`${AB}/bc#/ai`);
            await waitAi(page);
            const d = (await api(page, 'get_admin')).message;
            const nRules = await page.$$eval('#ai-rules .bc-ai-rule', (els) => els.length);
            check(`${tag}: dòng quy tắc = get_admin().rules (${d.rules.length})`, nRules === d.rules.length && nRules > 0, nRules);
            const rk = await page.$$eval('#ai-rules .bc-ai-rule', (els) => els.map((e) => e.dataset.rule));
            check(`${tag}: đúng thứ tự khoá quy tắc`, JSON.stringify(rk) === JSON.stringify(d.rules.map((r) => r.key)));
            const lower = d.rules.find((r) => r.lower);
            if (lower) check(`${tag}: quy tắc "thấp là xấu" có ghi chú`, await page.$(`[data-rule="${lower.key}"] .bc-ai-lower`) !== null);
            const r0 = d.rules[0];
            const ph = await page.$eval(`[data-rule="${r0.key}"] [data-f="vang"]`, (e) => e.placeholder);
            check(`${tag}: ô ngưỡng vàng placeholder = mặc định`, r0.vang_default === null ? ph === 'không có' : ph === `mặc định ${r0.vang_default}`, ph);
            const nRuns = await page.$$eval('#ai-runs tbody tr', (els) => els.length);
            check(`${tag}: dòng lượt chạy = get_admin().runs (${d.runs.length})`, nRuns === d.runs.length, nRuns);
            const runsText = flat(await page.textContent('#ai-runs'));
            if (FRESH) {
                check(`${tag}: lượt chạy — trạng thái tiếng Việt, lỗi hiện nguyên chữ, "chưa khai giá" khi cost_known 0`,
                    runsText.includes('Hết credit') && runsText.includes('Tài khoản hết <credit> & dừng') && runsText.includes('chưa khai giá')
                    && runsText.includes('Thành công') && await page.$$eval('#ai-runs td credit', (e) => e.length) === 0, runsText.slice(0, 300));
                const cost = await page.evaluate(() => (0.0585).toLocaleString('vi-VN', { minimumFractionDigits: 4, maximumFractionDigits: 4 }));
                check(`${tag}: chi phí lượt có giá = ${cost} USD`, runsText.includes(`${cost} USD`));
            } else check(`${tag}: lượt chạy lỗi hiện "Lỗi"`, runsText.includes('Lỗi') && runsText.includes('lỗi đọc số'), runsText.slice(0, 200));
            const st = flat(await page.textContent('#ai-status'));
            check(`${tag}: khoá Claude "${d.keys.claude ? 'có' : 'chưa có'}", OpenAI "${d.keys.openai ? 'có' : 'chưa có'}", ghi chú giai đoạn sau`,
                flat(await page.textContent('#ai-key-claude')) === (d.keys.claude ? 'có' : 'chưa có')
                && flat(await page.textContent('#ai-key-openai')) === (d.keys.openai ? 'có' : 'chưa có') && st.includes('giai đoạn sau')
                && st.includes(d.models.claude), st);
            check(`${tag}: AI viết lời ${d.enabled ? 'Đang bật' : 'Đang tắt'}`, flat(await page.textContent('#ai-enabled')).startsWith(d.enabled ? 'Đang bật' : 'Đang tắt'));
            check(`${tag}: link BC Settings = settings_url, tab mới`, await page.$$eval(`#ai-root a[href="${d.settings_url}"][target="_blank"][rel="noopener"]`, (e) => e.length) >= 2);
            const b = d.budget.claude;
            const fmt = await page.evaluate(([s, c]) => [s, c].map((v) => `${Number(v).toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} USD`), [b.spent, b.cap]);
            const sp = flat(await page.textContent('#ai-spent'));
            check(`${tag}: chi phí ${fmt[0]} / ${fmt[1]}, thanh tiến độ`, sp === `${fmt[0]} / ${fmt[1]}` && await page.$('#ai-budget .bc-progress') !== null, sp);
            check(`${tag}: trần 0 → "đang chặn mọi lượt gọi" ${b.cap ? 'không' : 'có'}`, (await page.$('#ai-cap0') !== null) === !b.cap);
            check(`${tag}: chưa khai giá → báo ${b.price_known ? 'không' : 'có'}`, (await page.$('#ai-noprice') !== null) === !b.price_known);
            check(`${tag}: lượt gọi hôm nay ${b.calls_today} / ${b.max_calls}`, flat(await page.textContent('#ai-calls')) === `${b.calls_today} / ${b.max_calls}`);
            check(`${tag}: lời AI bị loại = ${d.rejected.length}, việc bỏ qua = ${d.muted.length}`,
                await page.$$eval('#ai-rejected .bc-ai-item', (e) => e.length) === d.rejected.length
                && await page.$$eval('#ai-muted .bc-ai-item', (e) => e.length) === d.muted.length
                && await page.$$eval('#ai-muted [data-reopen]', (e) => e.length) === d.muted.length);
            check(`${tag}: không chuỗi khoá trong trang`, !(await page.content()).includes(FAKE_KEY));
            await overflowOk(page, tag);
            if (!mobile) await aiActions(page, ignore, reqs, tag, d);
            await overflowOk(page, `${tag} sau thao tác`);
        } catch (e) { check(`${tag}: kịch bản chạy hết`, false, e.message.split('\n')[0]); }
        check(`${tag}: không lỗi JS/HTTP`, errors.length === 0, errors.join(' | '));
        await ctx.close();
    }
}

async function aiActions(page, ignore, reqs, tag, d) {
    // Thử kết nối: hai lần — bản giả trả lần lượt ok / lỗi có chứa khoá (máy chủ xoá); giữa hai lượt trần có thể chặn
    const outs = [];
    for (let i = 0; i < 2; i++) {
        await page.click('#ai-test');
        await page.waitForFunction(() => { const t = document.querySelector('#ai-test-out')?.textContent || ''; return t && t !== 'Đang thử…'; }, null, { timeout: 10000 });
        outs.push(await page.$eval('#ai-test-out', (e) => ({ t: e.textContent, kids: e.children.length })));
        await sleep(200);
    }
    const resp = reqs.filter((r) => r.m === 'bc.api.ai.test_connection');
    if (FRESH) {
        check(`${tag}: "Thử kết nối" hiện câu trả lời máy chủ: lần 1 kết nối được, lần 2 lỗi (khoá đã che), không HTML, không chuỗi khoá`,
            outs[0].t === 'Kết nối được (claude-sonnet-5-5)' && outs[1].t.startsWith('Không được: 401') && outs[1].t.includes('***')
            && outs[1].t.includes('<b>') && !outs.some((o) => o.t.includes(FAKE_KEY) || o.kids) && resp.length === 2 && resp[0].body === 'provider=claude',
            JSON.stringify(outs));
    } else {
        check(`${tag}: "Thử kết nối" khi trần 0 → báo đã chi tới trần (không gọi mô hình)`, outs.every((o) => o.t === 'Không được: đã chi tới trần kỳ này (claude-sonnet-5-5)'),
            JSON.stringify(outs));
    }
    // Quy tắc: tắt + lưu, đổi ngưỡng + lưu → tải lại vẫn giữ; get_admin đồng ý
    const r0 = d.rules[0], r1 = d.rules[1];
    await page.uncheck(`[data-rule="${r0.key}"] [data-f="on"]`);
    await page.click(`[data-rule="${r0.key}"] [data-save]`);
    await toastText(page, /Đã lưu quy tắc/);
    const sent = reqs.filter((r) => r.m === 'bc.api.ai.set_rule').pop()?.body || '';
    const sp = Object.fromEntries(new URLSearchParams(sent));
    check(`${tag}: lưu quy tắc gửi rule_key=${r0.key}, disabled=1, ngưỡng trống = 0`, sp.rule_key === r0.key && sp.disabled === '1'
        && sp.threshold === '0' && sp.threshold_red === '0', sent);
    await page.fill(`[data-rule="${r1.key}"] [data-f="vang"]`, '12.5');
    await page.fill(`[data-rule="${r1.key}"] [data-f="do"]`, '40');
    await page.click(`[data-rule="${r1.key}"] [data-save]`);
    await page.waitForFunction((k) => !document.querySelector(`[data-rule="${k}"] [data-save]`)?.disabled, r1.key, { timeout: 8000 });
    await sleep(300);
    await page.reload();
    await waitAi(page);
    const a = (await api(page, 'get_admin')).message;
    const g0 = a.rules.find((r) => r.key === r0.key), g1 = a.rules.find((r) => r.key === r1.key);
    const ui0 = await page.$eval(`[data-rule="${r0.key}"] [data-f="on"]`, (e) => e.checked);
    const ui1 = await page.$$eval(`[data-rule="${r1.key}"] input[type=number]`, (els) => els.map((e) => e.value));
    check(`${tag}: tắt quy tắc ${r0.key} → tải lại vẫn tắt, API disabled`, g0.disabled === true && ui0 === false, JSON.stringify(g0));
    check(`${tag}: ngưỡng ${r1.key} 12.5 / 40 → tải lại giữ, API vang 12.5 do 40`, g1.vang === 12.5 && g1.do === 40 && ui1[0] === '12.5' && ui1[1] === '40',
        JSON.stringify({ g1, ui1 }));
    // Xoá ngưỡng → về mặc định; bật lại
    await page.fill(`[data-rule="${r1.key}"] [data-f="vang"]`, '');
    await page.fill(`[data-rule="${r1.key}"] [data-f="do"]`, '');
    await page.click(`[data-rule="${r1.key}"] [data-save]`);
    await page.check(`[data-rule="${r0.key}"] [data-f="on"]`);
    await page.click(`[data-rule="${r0.key}"] [data-save]`);
    await sleep(800);
    const a2 = (await api(page, 'get_admin')).message;
    const h0 = a2.rules.find((r) => r.key === r0.key), h1 = a2.rules.find((r) => r.key === r1.key);
    check(`${tag}: xoá ngưỡng → về mặc định; bật lại quy tắc`, h1.vang === h1.vang_default && h1.do === h1.do_default && h0.disabled === false,
        JSON.stringify({ h0, h1 }));
    // Ngưỡng âm → máy chủ từ chối, toast lời máy chủ
    ignore.add('bc.api.ai.set_rule');
    await page.fill(`[data-rule="${r1.key}"] [data-f="vang"]`, '-3');
    await page.click(`[data-rule="${r1.key}"] [data-save]`);
    const tt = await toastText(page, /Ngưỡng vàng/);
    check(`${tag}: ngưỡng âm → toast lời máy chủ`, tt.some((t) => t.t.includes('Ngưỡng vàng phải là số không âm')), JSON.stringify(tt));
    await sleep(300);
    ignore.delete('bc.api.ai.set_rule');
    // Mở lại việc đang bỏ qua
    if (d.muted.length) {
        const m = d.muted[0];
        await page.click(`[data-item="${m.id}"] [data-reopen]`);
        await page.waitForFunction((id) => !document.querySelector(`#ai-muted [data-item="${id}"]`), m.id, { timeout: 8000 });
        const f = (await api(page, 'get_feed')).message.insights.find((x) => x.id === m.id);
        check(`${tag}: "Mở lại" việc đang bỏ qua ${m.id} → rời danh sách, API mo`, f?.status === 'mo', JSON.stringify(f));
    }
    // Chạy ngay: chỉ xếp hàng (hàng đợi giả, pipeline KHÔNG chạy) → nút "Đang chạy…" → hỏi lại 5 s → xong thì vẽ lại
    const runs0 = (await api(page, 'get_admin')).message.runs.length;
    check(`${tag}: trước Chạy ngay: nút bật, không chạy`, !(await page.$eval('#ai-run', (e) => e.disabled)));
    const t0 = Date.now();
    await page.click('#ai-run');
    await toastText(page, /Đã xếp lượt chạy/);
    const post = reqs.filter((r) => r.m === 'bc.api.ai.run_now');
    const btn = await page.$eval('#ai-run', (e) => ({ dis: e.disabled, t: e.textContent.trim() }));
    const ad = (await api(page, 'get_admin')).message;
    check(`${tag}: "Chạy ngay" gửi 1 POST run_now, nút tắt "Đang chạy…", API running`, post.length === 1 && btn.dis && btn.t === 'Đang chạy…' && ad.running === true,
        JSON.stringify({ post: post.length, btn, running: ad.running }));
    ignore.add('bc.api.ai.run_now');
    const again = await api(page, 'run_now');
    const msg = JSON.parse(again.j._server_messages || '[]').map((x) => JSON.parse(x).message).join(' ');
    check(`${tag}: gọi run_now khi đang chạy → máy chủ từ chối "${msg}"`, again.status === 417 && /đang chạy/.test(msg), JSON.stringify(again));
    await page.waitForFunction(() => { const b = document.querySelector('#ai-run'); return b && !b.disabled; }, null, { timeout: 25000 });
    const dt = Date.now() - t0;
    const polls = reqs.filter((r) => r.m === 'bc.api.ai.get_admin' && r.t > t0 && r.body === '').length;
    check(`${tag}: hết chạy → nút bật lại sau ${Math.round(dt / 1000)} s (hỏi lại mỗi 5 s), toast xong`, dt >= 4500 && polls >= 2
        && (await toastText(page, /Lượt chạy đã xong/)).length > 0, JSON.stringify({ dt, polls }));
    check(`${tag}: không lượt pipeline nào chạy thật (số lượt chạy không đổi: ${runs0})`, (await api(page, 'get_admin')).message.runs.length === runs0);
    ignore.delete('bc.api.ai.run_now');
    // Rời màn trong lúc chạy → ngừng hỏi
    await page.click('#ai-run');
    await toastText(page, /Đã xếp lượt chạy/);
    await page.evaluate(() => { location.hash = '#/tro-ly'; });
    await waitTroLy(page);
    const tl = Date.now();
    await sleep(11000);
    const after = reqs.filter((r) => r.m === 'bc.api.ai.get_admin' && r.t > tl).length;
    check(`${tag}: rời màn khi đang chạy → không hỏi get_admin nữa`, after === 0, after);
}

const browser = await chromium.launch();
console.log(`Lượt ${PASS}`);
await viewer(browser);
const vctx = await newPage(browser, false);
await vctx.page.goto(`${VB}/bc#/tro-ly`);
await waitTroLy(vctx.page);
await adminTroLy(browser, vctx.page);
await vctx.ctx.close();
await adminAi(browser);
if (!FRESH) {
    // Giả lập payload (route): chưa chạy lần nào + không có việc nào
    const { ctx, page, errors } = await newPage(browser, true);
    await page.route('**/bc.api.ai.get_feed', async (route) => {
        const resp = await route.fetch();
        const j = await resp.json();
        j.message.meta = { ...j.message.meta, last_ok: null, stale: true, running: true };
        j.message.insights = []; j.message.brief = null; j.message.counts = { do: 0, vang: 0 };
        await route.fulfill({ response: resp, json: j });
    });
    await gotoTroLy(page, VB);
    const t = flat(await page.textContent('#tl-root'));
    check('chưa chạy lần nào: banner "Chưa chạy lần nào · Đang chạy…", cảnh báo "Trợ lý chưa chạy lần nào."',
        flat(await page.textContent('#tl-sub')) === 'Chưa chạy lần nào · Đang chạy…' && flat(await page.textContent('#tl-alert')) === 'Trợ lý chưa chạy lần nào.', t.slice(0, 200));
    check('không việc nào: "Không có việc cần chú ý", không chip, không bản tin', t.includes('Không có việc cần chú ý')
        && !(await page.$('[data-chip]')) && !(await page.$('.bc-ai-brief')));
    check('giả lập: không lỗi JS/HTTP', errors.length === 0, errors.join(' | '));
    await ctx.close();
}
await browser.close();
console.log(`\n${n - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
