// Kiểm màn #/nhap-tp thật (import map + view thật + API Python thật trên MariaDB) ở desktop 1366px và điện thoại 390px.
// node ui_kho_nhap.mjs <baseUrl>
// Số trên màn so với CHÍNH payload API gọi trong trang (định dạng bằng lib/format.js thật + đúng Intl view dùng) — không cố
// định số của seed, để chạy được trên seed gộp của cả nhóm Kho. Bắt pageerror, console error, response >= 400, cuộn ngang
// ở 390px; đổi tháng phải tải lại số của tháng đó.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const base = process.argv[2] || 'http://127.0.0.1:8134';
const SHOTS = process.env.SHOTS || '';
let bad = 0, total = 0;
function check(label, ok, detail = '') {
    total++;
    if (ok) console.log(`  ✓ ${label}`); else { bad++; console.log(`  ✗ ${label} ${String(detail).slice(0, 400)}`); }
}
const squash = (s) => (s || '').replace(/\s+/g, ' ').trim();

async function api(page, thang) {
    return page.evaluate((t) => fetch('/api/method/bc.api.kho_nhap.get_overview', { method: 'POST',
        body: new URLSearchParams(t ? { thang: t } : {}) }).then((r) => r.json()).then((j) => j.message), thang);
}

/** Định dạng như view: tiền bằng lib/format.js THẬT (qua import map), số lượng Intl tối đa 2 số lẻ, thùng 1 số lẻ. */
async function fmt(page, kind, values) {
    return page.evaluate(async ([k, vs]) => {
        const f = await import('/assets/bc/bc/lib/format.js');
        const q = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
        const c1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
        const fn = { money: f.fmtMoney, num: f.fmtNum, qty: (v) => q.format(v), ct: (v) => c1.format(v) }[k];
        return vs.map((v) => (v === null || v === undefined ? null : fn(v)));
    }, [kind, values]);
}

/** Đơn vị vẽ của một dãy ngày / tháng — đúng quy tắc view: ô nào null hoặc hai đơn vị khác nhau → vẽ theo thùng. */
function chartVal(rows) {
    const mixed = rows.some((r) => r.qty === null || r.qty === undefined)
        || new Set(rows.filter((r) => r.qty).map((r) => r.uom || '')).size > 1;
    return (r) => (mixed ? r.cartons : r.qty);
}

async function settle(page) {
    await page.waitForSelector('#nt-kpis .bc-stat', { timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector('.bc-main .bc-skeleton'), null, { timeout: 20000 });
}

async function kpiCheck(page, d, tag) {
    const k = squash(await page.textContent('#nt-kpis'));
    const n = d.nhap;
    if (n.available) {
        const t = n.total;
        const [q] = await fmt(page, 'qty', [t.qty]);
        const [c] = await fmt(page, 'ct', [t.cartons]);
        const [v] = await fmt(page, 'money', [t.value]);
        const head = t.qty === null ? `${c} thùng` : `${q} ${t.uom || 'hộp'}`;
        check(`${tag} KPI nhập kho: ${head}, ${c} thùng, ${v}, ${t.slips} phiếu`, k.includes(`Thành phẩm nhập kho trong tháng ${head}`)
            && k.includes(`Thùng${c}`) && k.includes(`Giá trị (giá vốn)${v}`) && k.includes(`Phiếu đã duyệt${t.slips}`), k);
    } else {
        check(`${tag} KPI nhập kho: khối tắt hiện "—"`, k.includes('Thành phẩm nhập kho trong tháng —'), k);
    }
    return k;
}

async function scenario(page) {
    await page.waitForSelector('.bc-view-banner', { timeout: 15000 });
    await settle(page);
    const banner = squash(await page.textContent('.bc-view-banner'));
    check('banner "Nhập TP & giá vốn"', banner.includes('Nhập TP & giá vốn') && banner.includes('nợ BOM'), banner);

    const d = await api(page);
    check('API có dữ liệu, đủ 6 khối', d.available && ['nhap', 'cho_duyet', 'vao_hop', 'no_bom', 'nvl_treo', 'gia_von_0']
        .every((x) => d[x] && 'available' in d[x]), JSON.stringify(d.meta));
    const range = squash(await page.textContent('#nt-filter'));
    const fd = (s) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
    check(`bộ lọc: tháng ${d.meta.thang}, từ ${fd(d.meta.from)} đến ${fd(d.meta.to)}`, range.includes(`Từ ${fd(d.meta.from)} đến ${fd(d.meta.to)}`)
        && (await page.$eval('#nt-thang', (e) => e.value)) === d.meta.thang, range);

    // ── KPI ── (dòng phụ của thẻ: <span>nhãn</span><b>số</b> — textContent không có khoảng trắng giữa hai phần)
    const k = await kpiCheck(page, d, '[tháng này]');
    const q = d.cho_duyet, b = d.no_bom, g = d.gia_von_0;
    if (q.available) {
        const [qq] = await fmt(page, 'qty', [q.qty]);
        check(`KPI phiếu chờ duyệt: ${q.count} phiếu, ${qq}, cũ nhất ${q.oldest_age_days ?? '—'} ngày`,
            k.includes(`Phiếu nhập chờ thủ kho duyệt ${q.count}`) && (q.qty === null || k.includes(`Số lượng${qq}`))
            && (q.oldest_age_days === null ? k.includes('Phiếu cũ nhất—') : k.includes(`Phiếu cũ nhất${q.oldest_age_days} ngày`)), k);
    }
    if (b.available) {
        const [bv] = await fmt(page, 'money', [b.value_tam]);
        const [bq] = await fmt(page, 'qty', [b.qty]);
        check(`KPI nợ BOM: ${bq} ${b.uom || ''}, giá tạm ${bv}, xử lý ngay ${b.xu_ly_ngay.items} mã`,
            k.includes(`Giá tạm lúc nhập${bv}`) && k.includes(`Xử lý được ngay${b.xu_ly_ngay.items} mã`)
            && (b.qty === null ? k.includes(`Nợ BOM đang mở ${b.rows} dòng`) : k.includes(`Nợ BOM đang mở ${bq} ${b.uom || 'hộp'}`)), k);
    }
    if (g.available) {
        const [gq] = await fmt(page, 'qty', [g.ton.qty]);
        check(`KPI chưa có giá vốn: ${gq}, ${g.ton.items} mã`, (g.ton.qty === null ? k.includes(`${g.ton.rows} dòng`)
            : k.includes(`Thành phẩm chưa có giá vốn ${gq} ${g.ton.uom || 'hộp'}`)) && k.includes(`Số mã${g.ton.items}`), k);
    }

    // ── Nhập kho trong tháng: biểu đồ ngày, bảng mã, 12 tháng ──
    const n = d.nhap;
    if (n.available) {
        const wantDay = chartVal(n.by_day), wantMonth = chartVal(n.by_month);
        if (n.by_day.some((r) => r.slips)) {
            await page.waitForFunction(() => window.Chart && window.Chart.getChart(document.getElementById('nt-day-chart')), null, { timeout: 15000 });
            const ch = await page.evaluate(() => { const c = window.Chart.getChart(document.getElementById('nt-day-chart'));
                return { n: c.data.labels.length, w: c.width, data: c.data.datasets[0].data }; });
            check(`biểu đồ ngày: ${n.by_day.length} cột, mỗi cột = API`, ch.n === n.by_day.length && ch.w > 0
                && ch.data.every((v, i) => Math.abs(v - wantDay(n.by_day[i])) < 1e-6), JSON.stringify(ch).slice(0, 200));
        } else {
            const ok = await page.waitForFunction(() => document.getElementById('nt-nhap')?.textContent.includes('chưa nhập thành phẩm'),
                null, { timeout: 5000 }).then(() => true, () => false);
            check('biểu đồ ngày: tháng không nhập → lời nhắn', ok && !(await page.$('#nt-day-chart')));
        }
        if (n.by_month.some((r) => r.slips)) {
            await page.waitForFunction(() => window.Chart && window.Chart.getChart(document.getElementById('nt-month-chart')), null, { timeout: 15000 });
            const cm = await page.evaluate(() => window.Chart.getChart(document.getElementById('nt-month-chart')).data.datasets[0].data);
            check('biểu đồ 12 tháng = API', cm.length === 12 && cm.every((v, i) => Math.abs(v - wantMonth(n.by_month[i])) < 1e-6), JSON.stringify(cm));
        }
        const mt = squash(await page.textContent('#nt-month-table'));
        const cur = n.by_month[n.by_month.length - 1];
        const [mq, mv] = [(await fmt(page, 'qty', [cur.qty]))[0], (await fmt(page, 'money', [cur.value]))[0]];
        const firstRow = squash(await page.textContent('#nt-month-table tbody tr'));
        check(`bảng 12 tháng: tháng chọn đứng đầu (${mq}, ${mv}), đủ 12 dòng`, firstRow.includes(mq ?? '—') && firstRow.includes(mv)
            && (await page.$$eval('#nt-month-table tbody tr', (e) => e.length)) === 12, firstRow + ' | ' + mt.slice(0, 120));
        // Từng ô "Theo phiếu" / "Theo sổ kho" / "Ngoài phiếu" của 12 dòng = API: lẫn đơn vị (null) → "—"; đơn vị khác hộp ghi
        // kèm; ngoài phiếu: không có phiếu kho → "0", có mà lẫn đơn vị → "N phiếu kho" (KHÔNG được thành "—" hay 0).
        const tds = await page.$$eval('#nt-month-table tbody tr', (trs) => trs.map((tr) => [...tr.querySelectorAll('td')]
            .map((td) => td.textContent.replace(/\s+/g, ' ').trim())));
        const rev = n.by_month.slice().reverse();
        const fq = await fmt(page, 'qty', rev.flatMap((r) => [r.qty, r.so_kho_qty, r.ngoai_phieu]));
        const cq = (v, f, u) => (v === null ? '—' : (u && u !== 'Hộp' ? `${f} ${u}` : f));
        let why = '';
        rev.forEach((r, i) => {
            const [qf, sf, nf] = fq.slice(i * 3, i * 3 + 3);
            const want = [cq(r.qty, qf, r.uom), cq(r.so_kho_qty, sf, r.so_kho_uom), !r.ngoai_entries ? '0'
                : r.ngoai_phieu === null ? `${r.ngoai_entries} phiếu kho` : cq(r.ngoai_phieu, nf, r.ngoai_uom)];
            const got = [tds[i]?.[1], tds[i]?.[4], tds[i]?.[5]];
            if (want.some((w, j) => w !== got[j])) why += `${r.month}: [${got.join(' | ')}] ≠ [${want.join(' | ')}]; `;
        });
        check('bảng 12 tháng: từng ô phiếu / sổ kho / ngoài phiếu = API (đơn vị, "—" khi lẫn đơn vị, số phiếu kho ngoài phiếu)', !why, why);
        const note = squash(await page.textContent('#nt-month .bc-note'));
        const anyN = n.by_month.some((r) => r.ngoai_entries > 0);
        check(`ghi chú 12 tháng theo số phiếu kho ngoài phiếu (${anyN ? 'có' : 'không'})`, note.includes('Mọi tháng đều không có nhập ngoài phiếu') === !anyN
            && note.includes('"—" = tháng có mã khác đơn vị') === n.by_month.some((r) => r.qty === null || r.so_kho_qty === null || r.ngoai_phieu === null), note);
        if (n.top_items.length) {
            const top = n.top_items.slice().sort((a, x) => x.qty - a.qty)[0];
            const [tq] = await fmt(page, 'qty', [top.qty]);
            const row = squash(await page.textContent('#nt-top tbody tr'));
            check(`mã nhập nhiều nhất: ${top.short_name} ${tq}`, row.includes(top.short_name) && row.includes(tq), row);
        }
        const nx = squash(await page.textContent('#nt-nhap'));
        const [bv, tv] = await fmt(page, 'money', [n.total.by_kind.bom.value, n.total.by_kind.tam.value]);
        const dc = n.doi_chieu;
        let dcOk = dc.slips_lech ? nx.includes(`${dc.slips_lech} phiếu lệch`) : nx.includes('Khớp');
        if (dc.slips_lech && dc.slip_qty !== null && dc.se_qty !== null) {
            const [a, b2] = await fmt(page, 'qty', [dc.slip_qty, dc.se_qty]);
            dcOk = dcOk && nx.includes(`phiếu ${a} ${dc.slip_uom}`) && nx.includes(`sổ ${b2} ${dc.se_uom}`);
        } else if (dc.slips_lech) {
            dcOk = dcOk && nx.includes('nhiều đơn vị, không cộng chung') && !nx.includes('theo phiếu');  // không in tổng lẫn Hộp + Kg
        }
        check(`có định mức ${bv} / nhập tạm ${tv}; đối chiếu ${dc.slips_lech ? `${dc.slips_lech} phiếu lệch` : 'khớp'}`, nx.includes(bv)
            && nx.includes(tv) && dcOk, nx.slice(0, 400));
        if (n.ngoai_phieu.entries) {
            check(`nhập ngoài phiếu: ${n.ngoai_phieu.entries} phiếu kho`, nx.includes(`(${n.ngoai_phieu.entries} phiếu kho`), nx);
        }
    }

    // ── Hàng đợi / vào hộp ──
    if (q.available) {
        const rows = await page.$$eval('#nt-cho tbody tr', (e) => e.length);
        check(`phiếu chờ duyệt: ${Math.min(8, q.rows.length)} dòng trên trang đầu`, q.count ? rows === Math.min(8, q.rows.length)
            : squash(await page.textContent('#nt-cho')).includes('Không có phiếu nào chờ duyệt'), rows);
        if (q.rows.length) {
            const first = squash(await page.textContent('#nt-cho tbody tr'));
            check(`phiếu chờ lâu nhất đứng đầu: ${q.rows[0].name} ${q.rows[0].age_days} ngày`, first.includes(q.rows[0].name)
                && first.includes(`${q.rows[0].age_days} ngày`), first);
        }
    }
    const v = d.vao_hop;
    if (v.available) {
        const [vq] = await fmt(page, 'qty', [v.qty]);
        const vt = squash(await page.textContent('#nt-vaohop'));
        check(`đã vào hộp chưa nhập kho: ${vq} hộp, ${v.items} mã`, vt.includes(`Hộp chưa nhập kho ${vq}`) && vt.includes(`${v.items} mã`)
            && vt.includes(fd(v.from)), vt.slice(0, 200));
    }

    // ── Nợ BOM / NVL treo / giá vốn 0 ──
    if (b.available && b.rows) {
        const nb = squash(await page.textContent('#nt-nobom'));
        const n3 = await page.$$eval('#nt-buckets .bc-rank-row', (e) => e.length);
        const bq = await fmt(page, 'qty', b.buckets.map((x) => x.qty));
        check('tuổi nợ: 3 nhóm, số dòng + số lượng khớp API', n3 === 3 && b.buckets.every((x, i) => nb.includes(`Nợ ${x.label}`)
            && nb.includes(`${x.rows} dòng`) && (x.qty === null || nb.includes(bq[i]))), nb.slice(0, 300));
        const first = squash(await page.textContent('#nt-nobom tbody tr'));
        check(`danh sách nợ: ${b.list[0].short_name} đứng đầu${b.list[0].co_bom ? ' (có BOM)' : ''}`, first.includes(b.list[0].short_name)
            && (!b.list[0].co_bom || first.includes('Có BOM')), first);
    }
    const r = d.nvl_treo;
    if (r.available) {
        const [rv] = await fmt(page, 'money', [r.value]);
        const nt = squash(await page.textContent('#nt-nvl'));
        check(`nguyên liệu còn treo: ${rv}, ${r.n_rm} nguyên liệu, chưa ước tính ${r.chua_uoc_tinh.items} mã`,
            nt.includes(`Nguyên liệu còn treo (ước tính) ${rv}`) && nt.includes(`${r.n_rm} nguyên liệu`)
            && nt.includes(`Chưa ước tính được ${r.chua_uoc_tinh.items} mã`), nt.slice(0, 300));
        if (r.chua_co_gia.n) check('nguyên liệu chưa có giá vốn có nhãn riêng', nt.includes('chưa có giá vốn'));
    }
    if (g.available) {
        const gt = squash(await page.textContent('#nt-gv0'));
        const [gq, nq] = await fmt(page, 'qty', [g.ton.qty, g.nhap_ky.qty]);
        check(`tồn giá vốn 0: ${gq}; nhập giá 0 trong tháng ${nq}`, (g.ton.qty === null || gt.includes(`Đang tồn giá vốn 0 ${gq}`))
            && (g.nhap_ky.qty === null || gt.includes(`Nhập giá 0 trong tháng ${nq}`)), gt.slice(0, 300));
        const nrow = await page.$$eval('#nt-gv0 tbody tr', (e) => e.length);
        check('danh sách tồn giá 0: số dòng = API (≤ 8 / trang)', nrow === Math.min(8, g.ton.list.length), nrow);
    }

    // ── Đổi tháng: tải lại số của tháng đó ──
    const prev = d.meta.prev;
    await page.selectOption('#nt-thang', prev);
    const d2 = await api(page, prev);
    await page.waitForFunction((t) => document.getElementById('nt-range')?.textContent.includes(t), `Từ ${fd(d2.meta.from)}`, { timeout: 15000 });
    await settle(page);
    check(`đổi sang ${prev}: ô chọn giữ tháng, khoảng ngày đổi`, (await page.$eval('#nt-thang', (e) => e.value)) === prev
        && squash(await page.textContent('#nt-range')).includes(`đến ${fd(d2.meta.to)}`));
    await kpiCheck(page, d2, `[${prev}]`);
    if (d2.nhap.available && d2.nhap.by_day.some((x) => x.slips)) {
        await page.waitForFunction(() => window.Chart && window.Chart.getChart(document.getElementById('nt-day-chart')), null, { timeout: 15000 });
        const nn = await page.evaluate(() => window.Chart.getChart(document.getElementById('nt-day-chart')).data.labels.length);
        check(`đổi tháng: biểu đồ ngày ${d2.nhap.by_day.length} cột`, nn === d2.nhap.by_day.length, nn);
    }
    await page.selectOption('#nt-thang', d.meta.thang);
    await page.waitForFunction((t) => document.getElementById('nt-range')?.textContent.includes(t), `Từ ${fd(d.meta.from)}`, { timeout: 15000 });
    await settle(page);

    // ── Riêng tư ──
    const all = await page.textContent('.bc-main');
    check('không lộ email / người tạo trên màn', !all.includes('@'));
    check('không còn khung chờ, không báo lỗi tải', !all.includes('Không tải được') && !all.includes('Không tính được')
        && !(await page.$('.bc-main .bc-skeleton')));
}

const browser = await chromium.launch();
for (const mobile of [false, true]) {
    const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
        : { viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('favicon.ico')) errors.push(`${r.status()} ${r.url()}`); });
    console.log(mobile ? '\n— Điện thoại 390px' : '— Desktop 1366px');
    await page.goto(`${base}/bc#/nhap-tp`);
    try { await scenario(page); } catch (e) { check('kịch bản chạy hết', false, e.message.split('\n')[0]); }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`không cuộn ngang trang (${overflow}px)`, overflow <= 1);
    check('không lỗi JS / HTTP', errors.length === 0, errors.join(' | '));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/nhap-tp-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    await ctx.close();
}
await browser.close();
console.log(`\n${total - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
