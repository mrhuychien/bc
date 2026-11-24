// Kiểm màn Hỏi đáp (#/hoi-dap, P3) trên server thử (seed_ui_qa.py serve — method API + _guard thật, phần máy hỏi đáp
// là kịch bản, chặn mạng):
//   node ui_qa.mjs <viewerBase> <adminBase> <modeFile>
// Hai vai, desktop 1280 px + điện thoại 390 px. Hỏi đáp tắt → không có nút "Hỏi trợ lý" trên #/tro-ly, #/hoi-dap báo
// đang tắt, không ô nhập. Bật → nút có, vào màn; "Còn n câu hôm nay", đếm ký tự / tối đa 500; dòng "Đang tra số liệu…"
// khi chờ; hỏi lại get_answer mỗi ~2 giây; xong → đoạn chưa kiểm gạch chấm + title "chưa kiểm", đoạn đã kiểm KHÔNG có
// dấu, giữ xuống dòng, ghi chú số gạch chấm, nguồn là link "#/…" (route lạ không thành link); lời có HTML hiện thành
// chữ; lỗi của câu (loi) hiện thành chữ; ask bị từ chối (417) → lời báo, câu hỏi còn trong ô; 3 lượt hỏi đáp xong gần
// nhất gửi kèm làm history (lượt lỗi không tính); hết lượt → nút tắt; lịch sử chỉ trong phiên (đổi màn còn, tải lại
// mất); quá 180 giây (đồng hồ giả) → lời báo hết giờ; người xem KHÔNG có khối SQL (kể cả khi máy chủ lỡ gửi câu SQL),
// quản trị có khối gập; mảng Trợ lý AI ẩn với người xem → #/hoi-dap không mở được, get_qa 403; 390 px không cuộn ngang.
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const VB = process.argv[2] || 'http://127.0.0.1:8150';
const AB = process.argv[3] || 'http://127.0.0.1:8151';
const MODE = process.argv[4] || '/tmp/bc_ui_qa_mode.json';
const XSS = '<img src=x onerror=window.__xss=1>';
const NOTE = 'ⓘ Trợ lý chỉ đọc đúng số liệu bạn xem được trên các màn báo cáo. Câu trả lời do mô hình ngôn ngữ viết; '
    + 'số gạch chấm là số máy chưa đối chiếu được.';
const UNV_NOTE = 'Số gạch chấm: máy chưa đối chiếu được với số liệu đã tra — kiểm lại ở màn gốc trước khi dùng.';
const M_TRAN = 'Trợ lý đã dùng hết ngân sách kỳ này — báo quản trị.';
const DEFAULT_A = 'Phải thu quá hạn hiện là 1,6 tỷ, tăng 251 triệu so với tháng trước (tự tính).\n- Khách lớn nhất: Công ty Mẫu\n'
    + '- Tồn kho: 35,2% là hàng Tết.';
let n = 0, bad = 0;
function check(label, ok, detail = '') {
    n++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 500)}`); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let gen = Date.now();
function setMode(enabled, limit) { fs.writeFileSync(MODE, JSON.stringify({ enabled, limit, gen: ++gen })); }

async function newPage(browser, mobile, base) {
    const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
        : { viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    const errors = [];
    const ignore = new Set();   // method lỗi CỐ Ý của kịch bản (ask 417, get_qa 403 khi mảng ẩn)
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
    page.on('response', (r) => {
        const m = (r.url().split('/api/method/')[1] || '').split('?')[0];
        if (r.status() >= 400 && !r.url().endsWith('favicon.ico') && !ignore.has(m)) errors.push(`${r.status()} ${r.url()}`);
    });
    const reqs = [];
    page.on('request', (r) => { if (r.url().includes('/api/method/')) reqs.push({ m: r.url().split('/api/method/')[1].split('?')[0], body: r.postData() || '', t: Date.now() }); });
    return { ctx, page, errors, ignore, reqs, base };
}

function api(page, method, args = {}) {
    return page.evaluate(async ([m, a]) => {
        const body = new URLSearchParams();
        for (const [k, v] of Object.entries(a)) if (v !== undefined && v !== null) body.append(k, String(v));
        const r = await fetch(`/api/method/${m}`, { method: 'POST', body });
        let j = {};
        try { j = await r.json(); } catch { /* */ }
        return { status: r.status, message: j.message };
    }, [method, args]);
}

async function overflowOk(page, tag) {
    const o = await page.evaluate(() => document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth);
    check(`${tag}: không cuộn ngang trang (${o}px)`, o <= 1);
}

async function gotoTroLy(P) {
    const qa = P.page.waitForResponse((r) => r.url().includes('bc.api.ai.get_qa'), { timeout: 20000 });
    await P.page.goto(`${P.base}/bc#/tro-ly`);
    await P.page.waitForFunction(() => document.querySelector('#tl-mode') && document.querySelector('#tl-mode').textContent !== '…'
        && !document.querySelector('#tl-root .bc-skeleton'), null, { timeout: 20000 });
    await qa;
    await sleep(200);
}
async function gotoQa(P, fresh = true) {
    if (fresh) { await P.page.goto('about:blank'); await P.page.goto(`${P.base}/bc#/hoi-dap`); } else await P.page.evaluate(() => { location.hash = '#/hoi-dap'; });
    await P.page.waitForFunction(() => document.querySelector('#hd-root') && !document.querySelector('#hd-root .bc-skeleton'), null, { timeout: 20000 });
}
const text = (page, sel) => page.$eval(sel, (e) => e.textContent.replace(/\s+/g, ' ').trim()).catch(() => null);
const newest = (page) => page.evaluate(() => {
    const e = document.querySelector('[data-qa]');
    return e ? { state: e.dataset.state, q: e.querySelector('.bc-ai-qa-qtext')?.textContent, html: e.innerHTML } : null;
});

/** Gõ câu hỏi, bấm Hỏi, chờ trạng thái cuối của câu mới nhất (≠ cho). → {askBody, item, polls} */
async function ask(P, q, { expectWait = false, final = true } = {}) {
    const { page, reqs } = P;
    const before = reqs.length;
    await page.fill('#hd-q', q);
    await page.click('#hd-ask');
    if (expectWait) {
        await page.waitForFunction((qq) => { const e = document.querySelector('[data-qa]');
            return e && e.dataset.state === 'cho' && e.querySelector('.bc-ai-qa-qtext')?.textContent === qq; }, q, { timeout: 10000 });
    }
    if (final) {
        await page.waitForFunction((qq) => { const e = document.querySelector('[data-qa]');
            return e && e.dataset.state !== 'cho' && e.querySelector('.bc-ai-qa-qtext')?.textContent === qq; }, q, { timeout: 30000 });
    }
    const mine = reqs.slice(before);
    const a = mine.find((r) => r.m === 'bc.api.ai.ask');
    return { askBody: a ? new URLSearchParams(a.body) : null, askT: a?.t, polls: mine.filter((r) => r.m === 'bc.api.ai.get_answer'), item: await newest(page) };
}

const browser = await chromium.launch();
try {
    // ═══ Người xem, desktop ═══
    console.log('— Người xem (desktop)');
    const V = await newPage(browser, false, VB);
    const p = V.page;

    setMode(false, 5);
    await gotoTroLy(V);
    check('tắt: #/tro-ly không có nút "Hỏi trợ lý"', (await p.$('#tl-qa-btn')) === null && (await p.$$('a[href="#/hoi-dap"]')).length === 0);
    await gotoQa(V);
    check('tắt: #/hoi-dap báo đang tắt, không có ô nhập', (await text(p, '#hd-main'))?.includes('Hỏi đáp đang tắt') && (await p.$('#hd-q')) === null,
        await text(p, '#hd-main'));
    check('tắt: người xem không thấy hướng dẫn BC Settings', !(await p.$('#hd-main a[href="/app/bc-settings"]')));

    setMode(true, 6);
    await gotoTroLy(V);
    const btn = await p.$('#tl-qa-btn');
    check('bật: #/tro-ly có nút "Hỏi trợ lý" → #/hoi-dap', !!btn && (await btn.textContent()).includes('Hỏi trợ lý') && (await btn.getAttribute('href')) === '#/hoi-dap');
    check('không có mục menu #/hoi-dap', (await p.$$('#bc-sidebar a[href="#/hoi-dap"], #bc-bottom-nav a[href="#/hoi-dap"]')).length === 0);
    if (btn) await btn.click();
    await p.waitForFunction(() => location.hash === '#/hoi-dap' && document.querySelector('#hd-q'), null, { timeout: 15000 });
    check('màn mở từ nút, tiêu đề "Hỏi trợ lý"', (await text(p, '#bc-header-title')) === 'Hỏi trợ lý', await text(p, '#bc-header-title'));
    check('"Còn 6 câu hôm nay"', (await text(p, '#hd-left')) === 'Còn 6 câu hôm nay', await text(p, '#hd-left'));
    check('ô nhập tối đa 500 ký tự', (await p.getAttribute('#hd-q', 'maxlength')) === '500');
    check('chưa gõ → nút Hỏi tắt, đếm 0/500', await p.$eval('#hd-ask', (b) => b.disabled) && (await text(p, '#hd-count')) === '0/500');
    await p.fill('#hd-q', 'abc');
    check('gõ 3 ký tự → 3/500, nút bật', (await text(p, '#hd-count')) === '3/500' && !(await p.$eval('#hd-ask', (b) => b.disabled)));
    await p.fill('#hd-q', 'x'.repeat(520));
    check('dán 520 ký tự → giữ 500, đếm 500/500', (await p.$eval('#hd-q', (t) => t.value.length)) === 500 && (await text(p, '#hd-count')) === '500/500');
    check('chân trang có lời ghi chú', (await text(p, '#hd-root .bc-note')) === NOTE, await text(p, '#hd-root .bc-note'));
    check('chưa hỏi → danh sách trống có lời gợi ý', (await text(p, '#hd-list'))?.includes('Chưa có câu hỏi nào'));

    // Q1 mặc định
    const Q1 = 'Phải thu quá hạn bao nhiêu?';
    const r1 = await ask(V, Q1, { expectWait: false, final: false });
    await p.waitForFunction(() => document.querySelector('[data-qa]')?.dataset.state === 'cho', null, { timeout: 10000 });
    const waitTxt = await text(p, '[data-qa] .bc-ai-qa-wait');
    check('đang chờ: dòng "Đang tra số liệu…" hiện', waitTxt?.startsWith('Đang tra số liệu…'), waitTxt);
    check('đang chờ: nút Hỏi tắt (một câu một lúc)', await p.$eval('#hd-ask', (b) => b.disabled));
    check('đang chờ: ô nhập đã xoá câu vừa hỏi', (await p.$eval('#hd-q', (t) => t.value)) === '');
    await p.waitForFunction(() => document.querySelector('[data-qa]')?.dataset.state === 'xong', null, { timeout: 30000 });
    const ask1 = V.reqs.find((r) => r.m === 'bc.api.ai.ask');
    const b1 = new URLSearchParams(ask1.body);
    check('ask gửi câu hỏi + history rỗng', b1.get('question') === Q1 && b1.get('history') === '[]', ask1.body);
    const polls1 = V.reqs.filter((r) => r.m === 'bc.api.ai.get_answer');
    const gaps = [polls1[0].t - ask1.t, ...polls1.slice(1).map((x, i) => x.t - polls1[i].t)];
    check('hỏi lại get_answer mỗi ~2 giây (3 lượt)', polls1.length === 3 && gaps.every((g) => g >= 1800 && g <= 3500), JSON.stringify(gaps));
    check('get_answer gửi đúng id', polls1.every((x) => new URLSearchParams(x.body).get('id')?.startsWith('QA')));
    const a1 = await p.evaluate(() => {
        const it = document.querySelector('[data-qa]');
        const a = it.querySelector('.bc-ai-qa-a');
        const unv = [...a.querySelectorAll('.bc-ai-qa-unv')];
        const plain = [...a.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent).join('|');
        return { text: a.textContent, inner: a.innerText, unv: unv.map((u) => ({ t: u.textContent, title: u.title,
            deco: getComputedStyle(u).textDecorationStyle, line: getComputedStyle(u).textDecorationLine })),
            plain, ws: getComputedStyle(a).whiteSpace,
            note: it.querySelector('.bc-ai-qa-unv-note')?.textContent,
            links: [...it.querySelectorAll('.bc-ai-qa-src a')].map((x) => [x.getAttribute('href'), x.textContent]),
            src: it.querySelector('.bc-ai-qa-src')?.textContent.replace(/\s+/g, ' ').trim(),
            sql: !!document.querySelector('.bc-ai-qa-sql, details pre'), select: document.body.innerHTML.includes('SELECT') };
    });
    check('lời trả lời đúng chữ, giữ xuống dòng', a1.text === DEFAULT_A && a1.ws === 'pre-wrap' && a1.inner.includes('\n- Khách lớn nhất'), JSON.stringify(a1.text));
    check('đoạn chưa kiểm: đúng "251 triệu", gạch chấm, title "chưa kiểm"', a1.unv.length === 1 && a1.unv[0].t === '251 triệu'
        && a1.unv[0].title === 'chưa kiểm' && a1.unv[0].deco === 'dotted' && a1.unv[0].line.includes('underline'), JSON.stringify(a1.unv));
    check('đoạn đã kiểm ("1,6 tỷ", "35,2%") không có dấu', a1.plain.includes('1,6 tỷ') && a1.plain.includes('35,2%'), a1.plain);
    check('ghi chú số gạch chấm', a1.note === UNV_NOTE, a1.note);
    check('nguồn: "Đã tra" link sang màn', JSON.stringify(a1.links) === JSON.stringify([['#/cong-no', 'Phải thu'], ['#/ton-kho', 'Tồn kho']])
        && a1.src === 'Đã tra: Phải thu, Tồn kho, Nguồn lạ', JSON.stringify(a1.links) + ' ' + a1.src);
    check('người xem: không có khối SQL (máy chủ giả có gửi câu SQL)', !a1.sql && !a1.select);
    check('còn 5 câu sau khi hỏi', (await text(p, '#hd-left')) === 'Còn 5 câu hôm nay', await text(p, '#hd-left'));
    V.ignore.add('bc.api.cn.get_receivables');  // seed Trợ lý không có sổ công nợ — chỉ kiểm link đưa sang đúng màn
    await p.click('.bc-ai-qa-src a[href="#/cong-no"]');
    await p.waitForFunction(() => location.hash === '#/cong-no', null, { timeout: 10000 });
    check('bấm nguồn → sang màn Phải thu', true);
    await p.waitForTimeout(800);
    await gotoQa(V, false);
    check('đổi màn rồi quay lại: lịch sử phiên còn', (await p.$$('[data-qa]')).length === 1 && (await newest(p)).state === 'xong');

    // Q2: HTML trong lời
    const r2 = await ask(V, `[html] câu có ${XSS}`);
    const a2 = await p.evaluate(() => {
        const it = document.querySelector('[data-qa]');
        return { a: it.querySelector('.bc-ai-qa-a').textContent, q: it.querySelector('.bc-ai-qa-qtext').textContent,
            tags: it.querySelectorAll('.bc-ai-qa-a *:not(.bc-ai-qa-unv), .bc-ai-qa-qtext *').length, img: document.querySelectorAll('#hd-root img').length,
            xss: window.__xss, unv: [...it.querySelectorAll('.bc-ai-qa-unv')].map((u) => u.textContent) };
    });
    check('lời có HTML hiện thành chữ, không thẻ nào chạy', r2.item.state === 'xong' && a2.a.includes(XSS) && a2.a.includes('<b>đậm</b> & ký tự "lạ"')
        && a2.tags === 0 && a2.img === 0 && a2.xss === undefined, JSON.stringify(a2));
    check('câu hỏi có HTML hiện thành chữ', a2.q === `[html] câu có ${XSS}`);
    check('đoạn chưa kiểm chứa HTML vẫn là chữ', JSON.stringify(a2.unv) === JSON.stringify(['<i>12 tỷ</i>']));

    // Q3: lỗi của câu
    const r3 = await ask(V, '[loi] câu bị từ chối');
    check('câu lỗi: trạng thái loi, lời báo là chữ', r3.item.state === 'loi'
        && (await text(p, '[data-qa] .bc-ai-qa-err')) === 'Trợ lý từ chối <b>câu này</b>' && !(await p.$('[data-qa] .bc-ai-qa-err b')));

    // Q4: ask bị từ chối 417
    V.ignore.add('bc.api.ai.ask');
    await p.fill('#hd-q', '[tuchoi] hỏi khi chạm trần');
    await p.click('#hd-ask');
    await p.waitForFunction(() => document.querySelector('#hd-err')?.textContent.trim(), null, { timeout: 10000 });
    check('ask bị từ chối: hiện lời máy chủ', (await text(p, '#hd-err')) === M_TRAN, await text(p, '#hd-err'));
    check('ask bị từ chối: câu hỏi còn trong ô, không thêm mục', (await p.$eval('#hd-q', (t) => t.value)) === '[tuchoi] hỏi khi chạm trần'
        && (await p.$$('[data-qa]')).length === 3);
    check('ask bị từ chối: có toast', (await text(p, '#bc-toast-mount'))?.includes(M_TRAN));
    V.ignore.delete('bc.api.ai.ask');

    // Q5, Q6, Q7: history = 3 lượt XONG gần nhất (lượt lỗi không tính, Q1 bị đẩy ra)
    const Q5 = 'Tồn kho thành phẩm?', Q6 = 'Doanh số tháng này?', Q7 = 'So với năm ngoái?';
    const r5 = await ask(V, Q5);
    const h5 = JSON.parse(r5.askBody.get('history'));
    check('history của Q5 = Q1, Q2 (bỏ câu lỗi)', h5.length === 2 && h5[0].q === Q1 && h5[0].a === DEFAULT_A && h5[1].q.startsWith('[html]'), JSON.stringify(h5));
    await ask(V, Q6);
    const r7 = await ask(V, Q7);
    const h7 = JSON.parse(r7.askBody.get('history'));
    check('history của Q7 = đúng 3 lượt xong gần nhất (Q2, Q5, Q6)', h7.length === 3 && h7[0].q.startsWith('[html]') && h7[1].q === Q5
        && h7[2].q === Q6 && h7.every((h) => typeof h.a === 'string' && h.a.length > 0), JSON.stringify(h7).slice(0, 300));
    check('mới nhất trên cùng', (await newest(p)).q === Q7);
    check('hết lượt: "Đã hết lượt hỏi hôm nay"', (await text(p, '#hd-left')) === 'Đã hết lượt hỏi hôm nay', await text(p, '#hd-left'));
    await p.fill('#hd-q', 'còn hỏi được không?');
    check('hết lượt: nút Hỏi tắt dù có chữ', await p.$eval('#hd-ask', (b) => b.disabled));
    await p.reload();
    await p.waitForFunction(() => document.querySelector('#hd-root') && !document.querySelector('#hd-root .bc-skeleton'), null, { timeout: 20000 });
    check('tải lại trang: lịch sử mất (chỉ trong phiên)', (await p.$$('[data-qa]')).length === 0);
    check('tải lại trang: số lượt theo máy chủ (hết)', (await text(p, '#hd-left')) === 'Đã hết lượt hỏi hôm nay');
    check('người xem desktop: không lỗi JS / HTTP', V.errors.length === 0, V.errors.join(' | '));

    // ═══ Người xem, 390 px + hết giờ (đồng hồ giả) ═══
    console.log('— Người xem (390 px)');
    setMode(true, 5);
    const M = await newPage(browser, true, VB);
    await M.page.clock.install();
    await gotoQa(M);
    await ask(M, '[dai] câu dài', { final: false });
    for (let i = 0; i < 6 && (await newest(M.page))?.state !== 'xong'; i++) { await M.page.clock.runFor(2100); await sleep(400); }
    check('390 px: câu dài xong', (await newest(M.page))?.state === 'xong');
    await overflowOk(M.page, '390 px #hd-root (lời dài)');
    check('390 px người xem: không có khối SQL', !(await M.page.$('.bc-ai-qa-sql')));
    await ask(M, 'Câu sẽ quá giờ [cham]', { final: false });
    await M.page.waitForFunction(() => document.querySelector('[data-qa]')?.dataset.state === 'cho', null, { timeout: 10000 });
    const before = M.reqs.filter((r) => r.m === 'bc.api.ai.get_answer').length;
    let sawWait = false;
    for (let i = 0; i < 110 && (await newest(M.page))?.state === 'cho'; i++) {
        if (i === 30) sawWait = (await text(M.page, '[data-qa] .bc-ai-qa-wait'))?.includes('Đang tra số liệu…');
        await M.page.clock.runFor(2000);
        await sleep(120);
    }
    const tp = M.reqs.filter((r) => r.m === 'bc.api.ai.get_answer').length - before;
    const it = await newest(M.page);
    check('chờ lâu: dòng chờ vẫn hiện ở giây ~60', sawWait);
    // máy chủ dừng câu hỏi trong 150 giây kể từ lúc hỏi; màn chờ 150 + 30 giây để luôn lấy được kết quả cuối
    check('quá 180 giây → báo hết giờ rõ ràng', it?.state === 'het-gio'
        && (await text(M.page, '[data-qa] .bc-ai-qa-err'))?.startsWith('Quá 3 phút chưa có câu trả lời'), JSON.stringify(it?.state));
    check(`hết giờ: dừng hỏi sau ~90 lượt (không bỏ cuộc trước hạn 150 giây của máy chủ) (${tp})`, tp >= 85 && tp <= 92);
    const tpAfter = M.reqs.filter((r) => r.m === 'bc.api.ai.get_answer').length;
    await M.page.clock.runFor(10000); await sleep(300);
    check('hết giờ: không hỏi thêm', M.reqs.filter((r) => r.m === 'bc.api.ai.get_answer').length === tpAfter);
    await overflowOk(M.page, '390 px #hd-root (hết giờ)');
    await gotoTroLy(M);
    await overflowOk(M.page, '390 px #/tro-ly có nút');
    check('390 px: không lỗi JS / HTTP', M.errors.length === 0, M.errors.join(' | '));
    await M.ctx.close();

    // ═══ Quản trị ═══
    console.log('— Quản trị');
    setMode(true, 5);
    const A = await newPage(browser, false, AB);
    await gotoTroLy(A);
    check('quản trị: #/tro-ly có nút "Hỏi trợ lý"', !!(await A.page.$('#tl-qa-btn')));
    await gotoQa(A);
    const ra = await ask(A, 'Khách nào nợ nhiều nhất?');
    const sq = await A.page.evaluate(() => {
        const d = document.querySelector('[data-qa] details.bc-ai-qa-sql');
        return d ? { open: d.open, sum: d.querySelector('summary').textContent.trim(), pre: [...d.querySelectorAll('pre')].map((x) => x.textContent) } : null;
    });
    check('quản trị: khối SQL gập sẵn, đúng câu lệnh', ra.item.state === 'xong' && sq && !sq.open && sq.sum === 'Câu SQL đã chạy (1)'
        && sq.pre.length === 1 && sq.pre[0].startsWith('SELECT customer, SUM(outstanding_amount) FROM `tabSales Invoice` WHERE docstatus = 1 AND x < 5'), JSON.stringify(sq));
    await A.page.click('[data-qa] details.bc-ai-qa-sql summary');
    check('quản trị: bấm thì mở khối SQL', await A.page.$eval('[data-qa] details.bc-ai-qa-sql', (d) => d.open));
    check('quản trị: chân trang + đoạn chưa kiểm như người xem', (await text(A.page, '#hd-root .bc-note')) === NOTE
        && (await A.page.$$('[data-qa] .bc-ai-qa-unv[title="chưa kiểm"]')).length === 1);
    check('quản trị desktop: không lỗi JS / HTTP', A.errors.length === 0, A.errors.join(' | '));
    const AM = await newPage(browser, true, AB);
    await gotoQa(AM);
    await ask(AM, '[dai] SQL dài');
    await AM.page.click('[data-qa] details.bc-ai-qa-sql summary');
    await overflowOk(AM.page, '390 px quản trị, khối SQL dài mở');
    check('390 px quản trị: không lỗi JS / HTTP', AM.errors.length === 0, AM.errors.join(' | '));
    await AM.ctx.close();

    // ═══ Mảng Trợ lý AI ẩn với người xem ═══
    console.log('— Mảng Trợ lý AI ẩn');
    setMode(true, 5);
    const h = await api(A.page, 'bc.api.sections.set_hidden', { sections: JSON.stringify(['tro-ly']), hidden: 1 });
    check('quản trị ẩn mảng tro-ly', h.status === 200, JSON.stringify(h));
    const H = await newPage(browser, false, VB);
    H.ignore.add('bc.api.ai.get_qa');
    await H.page.goto(`${VB}/bc#/hoi-dap`);
    await H.page.waitForFunction(() => location.hash !== '#/hoi-dap' && location.hash !== '#/tro-ly', null, { timeout: 20000 }).catch(() => {});
    await H.page.waitForTimeout(800);
    check('người xem: #/hoi-dap không mở được khi mảng ẩn', !(await H.page.$('#hd-root')) && !['#/hoi-dap', '#/tro-ly'].includes(await H.page.evaluate(() => location.hash)),
        await H.page.evaluate(() => location.hash));
    check('người xem: get_qa bị chặn (403)', (await api(H.page, 'bc.api.ai.get_qa')).status === 403);
    check('quản trị vẫn mở được #/hoi-dap khi mảng ẩn', await (async () => { await gotoQa(A); return !!(await A.page.$('#hd-q')); })());
    check('mảng ẩn: người xem không lỗi JS', H.errors.length === 0, H.errors.join(' | '));
    await api(A.page, 'bc.api.sections.set_hidden', { sections: JSON.stringify(['tro-ly']), hidden: 0 });
    await H.ctx.close();
    await A.ctx.close();
    await V.ctx.close();
} catch (e) {
    check('kịch bản chạy hết', false, e.stack || e.message);
} finally {
    await browser.close();
}
console.log(`\n${n - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
