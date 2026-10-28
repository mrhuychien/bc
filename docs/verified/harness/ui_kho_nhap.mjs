// Kiểm màn #/nhap-tp thật (import map + view thật + API Python thật trên MariaDB) ở desktop 1366px và điện thoại 390px.
// node ui_kho_nhap.mjs <baseUrl>
// Số trên màn so với CHÍNH payload API gọi trong trang (định dạng bằng lib/format.js thật + đúng Intl view dùng) — không cố
// định số của seed, để chạy được trên seed gộp của cả nhóm Kho. Bắt pageerror, console error, response >= 400, cuộn ngang
// ở 390px; đổi tháng phải tải lại số của tháng đó. Thêm (review chéo): thẻ tổng tách hàng "trong tháng" / "tình hình hôm nay"
// (UX-5), ô Thùng của bảng 12 tháng kèm phần chưa khai quy cách thùng (XR-COMP-2), cột quyết định thấy ngay ở 390px (UX-13), và
// hai payload chặn tại trình duyệt (page.route): site chưa cài sx (UX-11d) + tháng lẫn đơn vị → biểu đồ theo thùng (XR-COMP-2).
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
/** textContent của phần tử, '' khi chưa có (không chờ 30 giây như page.textContent). */
const txt = (page, sel) => page.evaluate((x) => document.querySelector(x)?.textContent || '', sel).then(squash);
const fd = (s) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
const my = (t) => `${t.slice(5)}/${t.slice(0, 4)}`;

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

/** "+ N Hộp" / "+ N mã" — phần chưa khai quy cách thùng của một ô (như view), '' khi không có. */
async function plusText(page, r) {
    if (!r.items_without_carton_factor) return '';
    const b = r.boxes_without_carton_factor;
    if (b === null || b === undefined) return `+ ${(await fmt(page, 'num', [r.items_without_carton_factor]))[0]} mã`;
    return `+ ${(await fmt(page, 'qty', [b]))[0]} ${r.uom_without || ''}`.trim();
}

/** UX-5: hai hàng thẻ — số của THÁNG CHỌN và TÌNH HÌNH HÔM NAY; không thẻ nào trộn hai mốc. */
async function groupCheck(page, d, tag) {
    const th = await txt(page, '#nt-kpi-thang-title'), nh = await txt(page, '#nt-kpi-nay-title');
    const tg = await txt(page, '#nt-kpi-thang'), ng = await txt(page, '#nt-kpi-nay');
    check(`${tag} UX-5 thẻ tổng chia hai hàng: "Trong tháng ${my(d.meta.thang)}" / "Tình hình hôm nay ${fd(d.meta.as_of)} · không theo tháng chọn"`,
        th === `Trong tháng ${my(d.meta.thang)}` && nh.includes(`Tình hình hôm nay ${fd(d.meta.as_of)}`) && nh.includes('không theo tháng chọn'),
        `${th} | ${nh}`);
    check(`${tag} UX-5 hàng tháng chỉ có số của tháng (nhập kho, nhập giá vốn 0); hàng hôm nay có chờ duyệt / vào hộp / nợ BOM / đang tồn giá vốn 0`,
        tg.includes('Thành phẩm nhập kho trong tháng') && tg.includes('Nhập giá vốn 0 trong tháng') && !/chờ thủ kho|Nợ BOM|đang tồn/i.test(tg)
        && ['Phiếu nhập chờ thủ kho duyệt', 'Đã vào hộp, chưa nhập kho', 'Nợ BOM đang mở', 'Thành phẩm đang tồn giá vốn 0'].every((x) => ng.includes(x))
        && !/trong tháng/i.test(ng), `${tg.slice(0, 160)} || ${ng.slice(0, 200)}`);
    return { tg, ng };
}

async function kpiCheck(page, d, tag) {
    const k = squash(await page.textContent('#nt-kpis'));
    await groupCheck(page, d, tag);
    const g0 = d.gia_von_0;
    if (g0.available) {
        const nk = g0.nhap_ky;
        const [nq] = await fmt(page, 'qty', [nk.qty]);
        const head = nk.qty === null ? `${nk.entries} phiếu kho` : `${nq} ${nk.uom || 'hộp'}`;
        check(`${tag} KPI nhập giá vốn 0 trong tháng: ${head}, ${nk.entries} phiếu kho, ${nk.items} mã`,
            k.includes(`Nhập giá vốn 0 trong tháng ${head}`) && k.includes(`Phiếu kho${nk.entries}`) && k.includes(`Số mã${nk.items}`), k);
    }
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

/** UX-5: mỗi tiêu đề mục ghi "tình hình hôm nay" (không phân biệt hoa thường) → chữ của mọi phần tử đứng sau nó tới tiêu đề mục kế
 *  tiếp (cùng cha), BỎ các dòng ghi chú .bc-note (ghi chú được nhắc tên thẻ của tháng, ô số thì không). */
async function todaySections(page) {
    return page.evaluate(() => [...document.querySelectorAll('.bc-main .bc-section-title')]
        .filter((h) => /tình hình hôm nay/i.test(h.textContent)).map((h) => {
            let text = '';
            for (let e = h.nextElementSibling; e && !e.classList.contains('bc-section-title'); e = e.nextElementSibling) {
                if (e.classList.contains('bc-note')) continue;
                const c = e.cloneNode(true);
                c.querySelectorAll('.bc-note').forEach((x) => x.remove());
                text += ` ${c.textContent}`;
            }
            return { title: h.textContent.replace(/\s+/g, ' ').trim(), text: text.replace(/\s+/g, ' ').trim() };
        }));
}

/** Phần hiển thị (%) của từng tiêu đề cột trong khung cuộn của bảng (cuộn ngang ở vị trí đầu). */
async function colVis(page, sel) {
    return page.evaluate((x) => {
        const s = document.querySelector(`${x} .bc-table-scroll`);
        if (!s) return null;
        const box = s.getBoundingClientRect();
        return Object.fromEntries([...s.querySelectorAll('th')].map((th) => {
            const r = th.getBoundingClientRect();
            return [th.textContent.replace(/[↕▲▼]/g, '').trim(), Math.round(Math.max(0, Math.min(r.right, box.right) - Math.max(r.left, box.left)) / r.width * 100)];
        }));
    }, sel);
}

async function scenario(page, mobile) {
    await page.waitForSelector('.bc-view-banner', { timeout: 15000 });
    await settle(page);
    const banner = squash(await page.textContent('.bc-view-banner'));
    check('banner "Nhập TP & giá vốn"', banner.includes('Nhập TP & giá vốn') && banner.includes('nợ BOM'), banner);

    const d = await api(page);
    check('API có dữ liệu, đủ 6 khối', d.available && ['nhap', 'cho_duyet', 'vao_hop', 'no_bom', 'nvl_treo', 'gia_von_0']
        .every((x) => d[x] && 'available' in d[x]), JSON.stringify(d.meta));
    const range = squash(await page.textContent('#nt-filter'));
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
        const [gc] = await fmt(page, 'ct', [g.ton.cartons]);
        const ng = await txt(page, '#nt-kpi-nay');
        const plus = (await plusText(page, g.ton)).replace(/^\+ /, '');
        check(`KPI đang tồn giá vốn 0 (hôm nay): ${gq}, ${g.ton.items} mã, ${gc} thùng${plus ? ` + chưa khai thùng ${plus}` : ''}`,
            (g.ton.qty === null ? ng.includes(`${g.ton.rows} dòng`) : ng.includes(`Thành phẩm đang tồn giá vốn 0 ${gq} ${g.ton.uom || 'hộp'}`))
            && ng.includes(`Số mã${g.ton.items}`) && ng.includes(`Thùng${gc}`) && (!plus || ng.includes(`Chưa khai thùng${plus}`)), ng);
    }
    const vh = d.vao_hop;
    if (vh.available) {
        const [vq] = await fmt(page, 'qty', [vh.qty]);
        const [vc] = await fmt(page, 'ct', [vh.cartons]);
        const ng = await txt(page, '#nt-kpi-nay');
        const plus = (await plusText(page, vh)).replace(/^\+ /, '');
        check(`KPI đã vào hộp chưa nhập kho (hôm nay): ${vq} ${vh.uom}, ${vc} thùng${plus ? ` + chưa khai thùng ${plus}` : ''}, ${vh.items} mã, từ ${fd(vh.from)}`,
            ng.includes(`Đã vào hộp, chưa nhập kho ${vq} ${vh.uom}`) && ng.includes(`Thùng${vc}`) && (!plus || ng.includes(`Chưa khai thùng${plus}`))
            && ng.includes(`Số mã${vh.items}`) && ng.includes(`Vào hộp từ${fd(vh.from)}`), ng);
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
        const note = squash(await page.textContent('#nt-month .bc-note'));
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
        // XR-COMP-2: mỗi dòng ngày / tháng của API kèm phần chưa khai quy cách thùng; ô Thùng = số thùng + "+ N Hộp" của phần đó.
        check('XR-COMP-2 API: mọi dòng ngày / tháng có boxes_without_carton_factor + items_without_carton_factor + uom_without',
            [...n.by_day, ...n.by_month].every((r) => 'boxes_without_carton_factor' in r && 'items_without_carton_factor' in r && 'uom_without' in r),
            JSON.stringify(n.by_month[n.by_month.length - 1]));
        let whyC = '';
        const fc = await fmt(page, 'ct', rev.map((r) => r.cartons));
        for (const [i, r] of rev.entries()) {
            const want = `${fc[i]}${await plusText(page, r)}`;
            if (tds[i]?.[2] !== want) whyC += `${r.month}: [${tds[i]?.[2]}] ≠ [${want}]; `;
        }
        const anyNo = n.by_month.some((r) => r.items_without_carton_factor);
        check(`XR-COMP-2 ô Thùng 12 tháng = thùng + "+ N" chưa khai quy cách (${n.by_month.filter((r) => r.items_without_carton_factor).length} tháng có), ghi chú khi có`,
            !whyC && note.includes('dưới cột Thùng = hàng của mã chưa khai quy cách thùng') === anyNo, whyC || note);
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
        const pb = (await plusText(page, b)).replace(/^\+ /, '');
        check(`nợ BOM: thùng kèm phần chưa khai quy cách (${pb || 'không có'})`, !pb || nb.includes(`thùng + ${pb} chưa khai quy cách thùng`), nb.slice(0, 200));
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
        const [gq] = await fmt(page, 'qty', [g.ton.qty]);
        const [gc] = await fmt(page, 'ct', [g.ton.cartons]);
        const gp = await plusText(page, g.ton);
        // UX-5 (gap của người kiểm): khối này nằm dưới tiêu đề "… tình hình hôm nay" → chỉ số HÔM NAY: tồn giá vốn 0 + quy ra thùng
        // (kèm phần chưa khai quy cách thùng). Số nhập giá 0 của THÁNG CHỌN chỉ ở thẻ "Nhập giá vốn 0 trong tháng" của hàng tháng.
        const gNoNote = await page.evaluate(() => { const c = document.getElementById('nt-gv0').cloneNode(true);
            c.querySelectorAll('.bc-note').forEach((x) => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); });
        check(`UX-5 khối giá vốn 0 chỉ số hôm nay: tồn ${gq}, quy ra thùng ${gc}${gp ? ` ${gp}` : ''}; không ô nào của tháng`,
            (g.ton.qty === null || gt.includes(`Đang tồn giá vốn 0 (hôm nay) ${gq}`))
            && gt.includes(`Quy ra thùng ${gc}`) && (!gp || gt.includes(`${gp.replace(/^\+ /, '')} chưa khai quy cách thùng`))
            && !/trong tháng|Nhập giá 0/i.test(gNoNote), gNoNote.slice(0, 300));
        const gNote = squash(await page.textContent('#nt-gv0 .bc-note'));
        check('UX-5 ghi chú giá vốn 0 trỏ đúng thẻ "Nhập giá vốn 0 trong tháng" ở hàng tháng (thẻ đó có thật)',
            gNote.includes('thẻ "Nhập giá vốn 0 trong tháng"') && !gNote.includes('dòng "Nhập giá 0"')
            && (await txt(page, '#nt-kpi-thang')).includes('Nhập giá vốn 0 trong tháng'), gNote);
        const nrow = await page.$$eval('#nt-gv0 tbody tr', (e) => e.length);
        check('danh sách tồn giá 0: số dòng = API (≤ 8 / trang)', nrow === Math.min(8, g.ton.list.length), nrow);
        if (g.ton.list.length) {
            const top = g.ton.list.slice().sort((a, x) => x.qty - a.qty)[0];
            const c0 = await page.$eval('#nt-gv0 tbody tr td', (td) => [td.firstChild?.textContent, td.querySelector('div')?.textContent].join(' · '));
            check(`UX-13 tồn giá 0: kho ghi dòng phụ dưới tên (${top.short_name} · ${top.warehouse_label})`, c0 === `${top.short_name} · ${top.warehouse_label}`, c0);
        }
    }
    if (r.available && r.list.length) {
        const first = r.list[0];
        const cells = await page.$$eval('#nt-nvl tbody tr:first-child td', (e) => e.map((td, i) => (i ? td.textContent
            : [td.firstChild?.textContent, td.querySelector('div')?.textContent].join(' · ')).replace(/\s+/g, ' ').trim()));
        const [fv] = await fmt(page, 'money', [first.value]);
        const [fq] = await fmt(page, 'qty', [first.qty]);
        check(`UX-13 NVL treo: cột Nguyên liệu (kho dưới tên) · Giá trị · Số lượng — dòng đầu ${first.short_name}`,
            cells.length === 3 && cells[0] === `${first.short_name} · ${first.warehouse_label || '—'}`
            && cells[1] === (first.rate_source ? fv : 'chưa có giá vốn') && cells[2] === `${fq} ${first.uom || ''}`.trim(), cells.join(' | '));
    }
    if (mobile) {
        // UX-13: ở 390px cột quyết định thấy ngay, không phải vuốt: NVL treo (danh sách xếp theo giá trị) Giá trị + Số lượng;
        // tồn giá vốn 0 (xếp theo tồn) cột Tồn.
        const nv = r.available && r.list.length ? await colVis(page, '#nt-nvl') : null;
        if (nv) check('UX-13 390px: NVL treo thấy trọn cột Giá trị và Số lượng', nv['Giá trị'] === 100 && nv['Số lượng'] === 100, JSON.stringify(nv));
        const gv = g.available && g.ton.list.length ? await colVis(page, '#nt-gv0') : null;
        if (gv) check('UX-13 390px: tồn giá vốn 0 thấy trọn cột Tồn', gv['Tồn'] === 100, JSON.stringify(gv));
    }
    const titles = await page.$$eval('.bc-main .bc-section-title', (e) => e.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    check('UX-5 tiêu đề khối hàng đợi / giá vốn chưa thật ghi "tình hình hôm nay"', titles.includes('Hàng đợi — tình hình hôm nay')
        && titles.includes('Giá vốn chưa thật — tình hình hôm nay'), titles.join(' | '));
    // UX-5 (gap của người kiểm): dưới MỌI tiêu đề "tình hình hôm nay" (hàng thẻ hôm nay, Hàng đợi, Giá vốn chưa thật — 3 mục) không ô
    // số nào của tháng chọn: không có chữ "trong tháng" ngoài ghi chú.
    const today0 = await todaySections(page);
    const leak = today0.filter((x) => /trong tháng/i.test(x.text));
    check('UX-5 3 mục "tình hình hôm nay", không mục nào chứa ô số "trong tháng"', today0.length === 3 && !leak.length,
        `${today0.length} mục; ${leak.map((x) => `${x.title}: …${x.text.slice(Math.max(0, x.text.search(/trong tháng/i) - 80), x.text.search(/trong tháng/i) + 60)}…`).join(' || ')}`);

    // ── Đổi tháng: tải lại số của tháng đó ──
    const todayRow = await txt(page, '#nt-kpi-nay');
    const prev = d.meta.prev;
    await page.selectOption('#nt-thang', prev);
    const d2 = await api(page, prev);
    await page.waitForFunction((t) => document.getElementById('nt-range')?.textContent.includes(t), `Từ ${fd(d2.meta.from)}`, { timeout: 15000 });
    await settle(page);
    check(`đổi sang ${prev}: ô chọn giữ tháng, khoảng ngày đổi`, (await page.$eval('#nt-thang', (e) => e.value)) === prev
        && squash(await page.textContent('#nt-range')).includes(`đến ${fd(d2.meta.to)}`));
    await kpiCheck(page, d2, `[${prev}]`);
    // UX-5: đổi tháng → hàng "hôm nay" giữ nguyên (cùng số với tháng này), tiêu đề vẫn ngày hôm nay
    const ngPrev = await txt(page, '#nt-kpi-nay');
    check(`[${prev}] UX-5 hàng "tình hình hôm nay" không đổi theo tháng chọn`, ngPrev === todayRow && !!ngPrev, `${ngPrev.slice(0, 120)} ≠ ${todayRow.slice(0, 120)}`);
    // UX-5: cả 3 mục "tình hình hôm nay" (kể cả Hàng đợi và Giá vốn chưa thật phía dưới) giữ nguyên chữ khi đổi tháng — đúng là số hôm nay.
    const today1 = await todaySections(page);
    const moved = today1.filter((x, i) => x.title !== today0[i]?.title || x.text !== today0[i]?.text);
    check(`[${prev}] UX-5 mọi mục "tình hình hôm nay" không đổi theo tháng chọn`, today1.length === 3 && !moved.length,
        moved.map((x) => { const o = today0.find((y) => y.title === x.title)?.text || '';
            let i = 0; while (i < x.text.length && x.text[i] === o[i]) i++;
            return `${x.title}: …${o.slice(Math.max(0, i - 40), i + 60)}… → …${x.text.slice(Math.max(0, i - 40), i + 60)}…`; }).join(' || '));
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
    try { await scenario(page, mobile); } catch (e) { check('kịch bản chạy hết', false, e.message.split('\n')[0]); }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`không cuộn ngang trang (${overflow}px)`, overflow <= 1);
    check('không lỗi JS / HTTP', errors.length === 0, errors.join(' | '));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/nhap-tp-${mobile ? 'm' : 'd'}.png`, fullPage: true });
    await ctx.close();
}

/** Payload sửa tại trình duyệt (page.route): API thật trả về rồi đổi đúng phần cần thử — view vẽ đúng hình payload đó. */
async function variant(name, mutate, run) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    await page.route('**/api/method/bc.api.kho_nhap.get_overview*', async (route) => {
        const resp = await route.fetch();
        const j = await resp.json();
        j.message = mutate(j.message);
        await route.fulfill({ response: resp, json: j });
    });
    console.log(`\n— ${name}`);
    await page.goto(`${base}/bc#/nhap-tp`);
    try { await settle(page); await run(page, await api(page)); } catch (e) { check(`${name}: chạy hết`, false, e.message.split('\n')[0]); }
    check(`${name}: không lỗi JS`, errors.length === 0, errors.join(' | '));
    await ctx.close();
}

// UX-11 (d): site chưa cài sx — payload đúng hình API trả khi không có sx (test_kho_nhap: 5 khối {available: false}).
await variant('Site chưa cài sx (payload chặn tại trình duyệt)', (d) => ({ ...d, meta: { ...d.meta, sx: false },
    nhap: { available: false }, cho_duyet: { available: false }, vao_hop: { available: false }, no_bom: { available: false },
    nvl_treo: { available: false } }), async (page) => {
    const k = await txt(page, '#nt-kpis');
    check('chưa cài sx: dải cảnh báo + thẻ "Chưa cài sx"', k.includes('Hệ thống sản xuất (app sx) chưa cài') && k.includes('Chưa cài sx'), k.slice(0, 200));
    const bad = [];
    for (const id of ['nt-nhap', 'nt-month', 'nt-cho', 'nt-vaohop', 'nt-nobom', 'nt-nvl']) {
        const t = await txt(page, `#${id}`);
        if (!t.includes('Hệ thống sản xuất (app sx) chưa cài nên chưa có') || t.includes('Hệ thống sản xuất chưa có')) bad.push(`${id}: ${t}`);
    }
    check('UX-11d chưa cài sx: từng khối nói "chưa cài", không nói "chưa có phiếu" như thể sx có mà trống', !bad.length, bad.join(' || '));
    check('chưa cài sx: khối giá vốn 0 vẫn có số', (await txt(page, '#nt-gv0')).includes('Đang tồn giá vốn 0 (hôm nay)'));
    // Số nhập giá 0 của tháng chỉ còn ở thẻ hàng tháng → thẻ đó phải có số cả khi chưa cài sx (không mất số khi bỏ ô trùng ở khối dưới).
    const tg = await txt(page, '#nt-kpi-thang');
    check('chưa cài sx: thẻ "Nhập giá vốn 0 trong tháng" vẫn có số', /Nhập giá vốn 0 trong tháng \d/.test(tg) && tg.includes('Phiếu kho'), tg.slice(0, 200));
});

// XR-COMP-2: tháng chọn lẫn đơn vị (số lượng tháng null — như API trả khi lẫn Hộp + Kg) → biểu đồ 12 tháng vẽ theo thùng; tooltip từng
// cột nói phần chưa khai quy cách thùng mà cột thùng không gồm, ghi chú dưới bảng nói biểu đồ cũng không gồm. Kèm một khối lỗi tính.
await variant('Tháng lẫn đơn vị → biểu đồ theo thùng (payload chặn tại trình duyệt)', (d) => {
    const bm = d.nhap.by_month.map((r, i, a) => (i === a.length - 1 ? { ...r, qty: null, uom: null } : r));
    return { ...d, nhap: { ...d.nhap, by_month: bm }, vao_hop: { available: false, error: true } };
}, async (page, d) => {
    const n = d.nhap;
    await page.waitForFunction(() => window.Chart && window.Chart.getChart(document.getElementById('nt-month-chart')), null, { timeout: 15000 });
    const ch = await page.evaluate((len) => {
        const c = window.Chart.getChart(document.getElementById('nt-month-chart'));
        const cb = c.config.options.plugins.tooltip.callbacks;
        return { label: c.data.datasets[0].label, data: c.data.datasets[0].data, after: [...Array(len).keys()].map((i) => cb.afterLabel({ dataIndex: i })) };
    }, n.by_month.length);
    let why = '';
    for (const [i, r] of n.by_month.entries()) {
        const p = (await plusText(page, r)).replace(/^\+ /, '');
        const want = p ? `chưa gồm ${p} chưa khai quy cách thùng` : '';
        if (ch.after[i] !== want || Math.abs(ch.data[i] - r.cartons) > 1e-9) why += `${r.month}: [${ch.data[i]} · ${ch.after[i]}] ≠ [${r.cartons} · ${want}]; `;
    }
    const anyNo = n.by_month.some((r) => r.items_without_carton_factor);
    check(`XR-COMP-2 biểu đồ theo thùng: cột = thùng, tooltip nói phần chưa khai (${n.by_month.filter((r) => r.items_without_carton_factor).length} tháng)`,
        ch.label === 'Nhập kho (thùng)' && !why && anyNo, why || ch.label);
    const note = await txt(page, '#nt-month .bc-note');
    check('XR-COMP-2 ghi chú: biểu đồ vẽ theo thùng nên cũng không gồm phần chưa khai', note.includes('biểu đồ vẽ theo thùng nên cũng không gồm'), note);
    const kv = await txt(page, '#nt-kpi-nay');
    check('khối lỗi tính: "Không tính được" ở khối và thẻ', (await txt(page, '#nt-vaohop')).includes('Không tính được bảng vào hộp lúc này')
        && /Đã vào hộp, chưa nhập kho\s*—\s*Không tính được/.test(kv), kv.slice(0, 300));
});

await browser.close();
console.log(`\n${total - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
