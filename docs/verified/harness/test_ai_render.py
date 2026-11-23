"""Trợ lý AI — bc.ai.render (placeholder → số thật, định dạng, lint "số trần") và bc.ai.redact (mã giả khách / NCC).

Đặc tả §5.3 bước 1–4, §5.4, §9.3, §9.5; hợp đồng chung §1 mục 8 (số quy tắc tự tính), 9 (thứ tự fill → lint → hoàn
nguyên), 12. Số kỳ vọng TÍNH TAY (phép tính ghi trong comment); riêng định dạng tiền còn so thêm với CHÍNH
`lib/format.js` chạy bằng node (nguồn chuẩn của "khớp màn gốc"). Chỉ redact.build cần MariaDB (tabCustomer,
tabSupplier); mọi phần khác là hàm thuần.

Chạy: BC_TEST_DB=bc_test_ai_render python3 -B test_ai_render.py
"""
import ast
import copy
import datetime
import json
import os
import random
import shutil
import subprocess
import time
from decimal import Decimal

from seed import Check, drop_column, drop_doctype, insert, reset
from paths import BC_ROOT

import frappe  # noqa: E402,F401  (giả)
import ai_testlib  # noqa: E402

from bc.ai import redact, registry, render  # noqa: E402

c = Check()
TEN_DAI, TEN_VUA = "x" * 121, "y" * 120
LAN_ANH, ABC, BAO_BI = "Tạp hoá 268 Lan Anh", "Công ty ABC", "NCC Bao Bì Số 1"   # tên khách có CHỮ SỐ: 268
R = "cong-no.receivables"

PACK = {
	"cong-no": {"receivables": {
		"as_of": "2026-11-05",
		"aging": {"31_60": 7_000_000},
		"kpis": {"total": 1_600_000_000, "overdue": 33_000_000, "overdue_pct": 35.25, "dso": 45.3, "over_limit": 3,
			"unallocated": 450_000, "trong": None, "co": True, "ten_dai": TEN_DAI, "ten_vua": TEN_VUA,
			"nhan": "Bánh {đặc biệt}  hộp\n12 cái", "rong": "", "qua_120": 5},
		"top_overdue": [
			{"customer": "CUST-0001", "customer_name": LAN_ANH, "overdue": 250_500_000, "max_days": 120,
				"oldest": datetime.date(2026, 7, 8)},
			{"customer": "CUST-0002", "customer_name": ABC, "overdue": 99_950_000, "max_days": 95},
		],
	}},
	"phai-tra": {"payables": {"ap": {"due": {"overdue_total": 1_050_000, "overdue_count": 12}},
		"top": [{"supplier": "SUP-0001", "supplier_name": BAO_BI, "amount": 999_999_999}]}},
	"ton-kho": {"overview": {"value": 2_000_000_000}},
}
NHOM = ("cong-no", "phai-tra")      # nhóm tai-chinh


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def loi(fn, *a):
	"""Tên lỗi ném ra (None nếu không ném)."""
	try:
		fn(*a)
	except Exception as e:  # noqa: BLE001
		return type(e).__name__
	return None


# ══ 1. fmt ════════════════════════════════════════════════════════════════════
print("\n— fmt('tien'): ngưỡng và làm tròn của fmtMoney (lib/format.js), đơn vị viết đủ —")
# fmtMoney: a ≥ 1e9 → one(n/1e9) + " tỷ"; a ≥ 1e8 → fmtNum(n/1e6) + " tr"; a ≥ 1e6 → one(n/1e6) + " tr";
# one(v) = Math.round(v*10)/10, bỏ ",0", KHÔNG nhóm nghìn; fmtNum = Math.round rồi nhóm nghìn; Math.round: đúng giữa → +∞.
TIEN = [
	(0, "0 đ"), (999, "999 đ"), (450_000, "450.000 đ"), (999_999, "999.999 đ"),
	(999_999.4, "999.999 đ"),            # < 1e6: Math.round(999999,4) = 999999
	(999_999.5, "1.000.000 đ"),          # < 1e6 nhưng tròn lên: vẫn nhánh "đ" (ngưỡng xét trên số gốc)
	(1_000_000, "1 triệu"),              # one(1) = "1"
	(1_049_999, "1 triệu"),              # 10,49999 → 10 → "1"
	(1_050_000, "1,1 triệu"),            # 10,5 đúng giữa → 11 → "1,1"
	(1_500_000, "1,5 triệu"), (33_000_000, "33 triệu"),
	(33_040_000, "33 triệu"),            # 330,4 → 330 → "33"
	(33_050_000, "33,1 triệu"),          # 330,5 → 331
	(99_949_999, "99,9 triệu"),          # 999,49999 → 999
	(99_950_000, "100 triệu"),           # 999,5 → 1000 → one = "100" (chưa tới 1e8 nhưng hiện 100)
	(99_999_999, "100 triệu"),
	(100_000_000, "100 triệu"),          # ≥ 1e8: số nguyên triệu
	(250_000_000, "250 triệu"), (250_400_000, "250 triệu"),
	(250_500_000, "251 triệu"),          # 250,5 → 251 (nhánh ≥ 1e8 KHÔNG có số lẻ)
	(999_499_999, "999 triệu"),
	(999_500_000, "1.000 triệu"),        # 999,5 → 1000, nhóm nghìn → "1.000 tr" trên màn gốc
	(999_999_999, "1.000 triệu"),        # vẫn < 1e9 nên KHÔNG thành "1 tỷ" — y như màn gốc
	(1_000_000_000, "1 tỷ"), (1_040_000_000, "1 tỷ"),
	(1_050_000_000, "1,1 tỷ"),           # 10,5 → 11
	(1_600_000_000, "1,6 tỷ"), (1_950_000_000, "2 tỷ"), (2_000_000_000.0, "2 tỷ"),
	(12_345_600_000_000, "12345,6 tỷ"),  # one() không nhóm nghìn (Number.toString)
	# Số âm: giữ dấu; Math.round đúng giữa về +∞ nên −10,5 → −10 (lệch đối xứng, y như màn gốc)
	(-1_600_000_000, "-1,6 tỷ"), (-1_050_000_000, "-1 tỷ"), (-1_250_000_000, "-1,2 tỷ"), (-33_000_000, "-33 triệu"),
	(-1_050_000, "-1 triệu"), (-250_500_000, "-250 triệu"), (-450_000, "-450.000 đ"),
	(-0.4, "0 đ"),                       # không bao giờ ra "-0"
]
for v, want in TIEN:
	eq(f"tien {v!r} → {want}", render.fmt(v, "tien"), want)

print("\n— fmt: so / pct / ngay / chu —")
SO = [
	(0, "0"), (12, "12"), (12_345, "12.345"), (1_234_567, "1.234.567"), (12_345.0, "12.345"), (-1_234, "-1.234"),
	(12.5, "12,5"), (45.3, "45,3"),
	(1_234.56, "1.234,6"),               # 1 số lẻ + nhóm nghìn phần nguyên
	(12.04, "12"),                       # tròn về 12,0 → bỏ ",0"
	(0.15, "0,2"), (0.25, "0,3"),        # nửa ra xa 0 trên dạng thập phân ngắn nhất (0,15 nhị phân < 0,15 vẫn lên 0,2)
	(-12.25, "-12,3"), (-0.04, "0"), (99.95, "100"),
]
for v, want in SO:
	eq(f"so {v!r} → {want}", render.fmt(v, "so"), want)
PCT = [
	(35.25, "35,3%"), (35.24, "35,2%"), (35, "35,0%"), (0, "0,0%"), (100, "100,0%"), (0.05, "0,1%"), (-12.25, "-12,3%"),
	(1_234.56, "1.234,6%"), (99.95, "100,0%"),
	(-0.04, "0,0%"),                     # chủ ý khác fmtPct ("-0,0%"): không hiện số 0 âm
]
for v, want in PCT:
	eq(f"pct {v!r} → {want}", render.fmt(v, "pct"), want)
NGAY = [("2026-11-05", "5/11/2026"), ("2026-01-31", "31/1/2026"), (datetime.date(2026, 7, 8), "8/7/2026"),
	(datetime.datetime(2026, 12, 25, 23, 59), "25/12/2026"), ("2026-11-05 10:30:00", "5/11/2026"),
	("2026-11-05T10:30:00.123456", "5/11/2026")]
for v, want in NGAY:
	eq(f"ngay {v!r} → {want}", render.fmt(v, "ngay"), want)
# Decimal (SUM / cột decimal của MariaDB chưa qua flt) cũng là số: 1,6e9 → "1,6 tỷ"; 35,25 → "35,3%"; 12,000… → "12"
eq("Decimal được nhận như số", [render.fmt(Decimal("1600000000.000000000"), "tien"), render.fmt(Decimal("35.25"), "pct"),
	render.fmt(Decimal("12.000000000"), "so"), render.fmt(Decimal("1234.56"), "so"), render.fmt(Decimal("-450000.4"), "tien")],
	["1,6 tỷ", "35,3%", "12", "1.234,6", "-450.000 đ"])
eq("chu: giữ nguyên chuỗi", render.fmt(LAN_ANH, "chu"), LAN_ANH)
eq("chu: đúng 120 ký tự được", render.fmt(TEN_VUA, "chu"), TEN_VUA)
eq("chu: khoảng trắng / xuống dòng gộp một dấu cách", render.fmt(" Bánh  quy\nbơ ", "chu"), "Bánh quy bơ")
SAI = [
	("tien", True), ("so", False), ("pct", True),                # bool không phải số
	("tien", None), ("so", "12"), ("pct", "35%"), ("tien", [1]), ("so", {"a": 1}),
	("tien", float("nan")), ("so", float("inf")), ("pct", float("-inf")),
	("so", Decimal("NaN")), ("tien", Decimal("Infinity")), ("pct", Decimal("sNaN")),
	("ngay", "05/11/2026"), ("ngay", "2026-13-01"), ("ngay", "2026-02-30"), ("ngay", 20261105), ("ngay", None),
	("ngay", "2026-11-05abc"), ("ngay", ""),
	("chu", TEN_DAI), ("chu", 12), ("chu", None), ("chu", ["a"]),
	("tien", 10**400), ("so", 10**40), ("pct", 10**40),          # số quá lớn: lỗi kiểu, không nổ lỗi khác
	("xyz", 1), ("", 1), ("Tien", 1),
]
for kind, v in SAI:
	c(f"sai kiểu → ValueError: {kind} ← {str(v)[:20]!r}", loi(render.fmt, v, kind) == "ValueError", loi(render.fmt, v, kind))
# Số không hữu hạn: MỌI kiểu số × mọi dạng (float / Decimal, NaN / ±vô cực / sNaN) đều là ValueError, không lỗi nào khác
VO_HAN = [float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("sNaN")]
sot = [(k, str(v)) for k in ("tien", "so", "pct") for v in VO_HAN if loi(render.fmt, v, k) != "ValueError"]
c("số không hữu hạn: 3 kiểu × 7 giá trị đều ValueError", not sot, str(sot))


def doi_chieu_node():
	"""So với CHÍNH lib/format.js (fmtMoney / fmtPct / fmtNum) trên dải giá trị quanh mọi ngưỡng + ngẫu nhiên cố định."""
	node = shutil.which("node")
	if not node:
		print("  (BỎ QUA đối chiếu node: máy không có node)")
		return
	rnd = random.Random(20261123)
	tien = set()
	for moc in (1e3, 1e6, 1e8, 1e9, 1e10):
		for d in (-50_001, -50_000, -49_999, -1, 0, 1, 49_999, 50_000, 50_001, 499_999, 500_000, 500_001):
			tien.add(int(moc + d))
	for k in range(1, 60):                       # đúng giữa của từng nấc làm tròn
		tien |= {k * 100_000 + 50_000, k * 1_000_000 + 500_000 + 100_000_000, k * 100_000_000 + 50_000_000 + 10**9}
	for _ in range(600):
		tien.add(int(rnd.random() * rnd.choice([1e4, 1e6, 1e7, 1e8, 1e9, 1e10, 1e12])))
	tien |= {-v for v in tien}
	tien = sorted(tien) + [v + 0.5 for v in sorted(tien)[::7]]
	pct = sorted({round(rnd.uniform(-150, 150), rnd.choice([0, 1, 2, 3])) for _ in range(500)}
		| {k / 100 + 0.005 for k in range(-40, 40)} | {k + 0.05 for k in range(-20, 20)} | {1234.56, 99.95, 0.15})
	so = sorted({int(rnd.uniform(-5e6, 5e6)) for _ in range(200)} | {0, 999, 1000, 999_999, 1_000_000})
	js = ("import fs from 'node:fs';"
		f"import {{ fmtMoney, fmtPct, fmtNum }} from {json.dumps('file://' + os.path.join(BC_ROOT, 'bc/public/bc/lib/format.js'))};"
		"const d = JSON.parse(fs.readFileSync(0, 'utf8'));"
		"console.log(JSON.stringify({tien: d.tien.map(v => [fmtMoney(v), fmtNum(v)]), pct: d.pct.map(v => fmtPct(v)),"
		" so: d.so.map(v => fmtNum(v))}));")
	p = subprocess.run([node, "--input-type=module", "-e", js], input=json.dumps({"tien": tien, "pct": pct, "so": so}),
		capture_output=True, text=True, timeout=120)
	if p.returncode != 0:
		c("node chạy được lib/format.js", False, p.stderr[-400:])
		return
	ra = json.loads(p.stdout)
	lech = []
	for v, (money, num) in zip(tien, ra["tien"]):
		if abs(v) >= 1e6:                        # "1,6 tỷ" giữ; "33 tr" → "33 triệu"
			want = money[:-3] + " triệu" if money.endswith(" tr") else money
		else:                                    # dưới 1 triệu: viết đủ đồng (màn gốc viết "450k")
			want = ("0" if num == "-0" else num) + " đ"
		if render.fmt(v, "tien") != want:
			lech.append((v, render.fmt(v, "tien"), want))
	c(f"tien khớp fmtMoney trên {len(tien)} giá trị (mọi ngưỡng tỷ / triệu, đúng giữa, âm)", not lech, str(lech[:5]))
	c("  … trong đó có đủ cả 3 nhánh", {m[-2:] for m, _ in ra["tien"]} >= {"tỷ", "tr"} and any(abs(v) < 1e6 for v in tien))
	lech = [(v, render.fmt(v, "pct"), w) for v, w in zip(pct, ra["pct"]) if render.fmt(v, "pct") != w.replace("-0,0%", "0,0%")]
	c(f"pct khớp fmtPct trên {len(pct)} giá trị (trừ số 0 âm)", not lech, str(lech[:5]))
	lech = [(v, render.fmt(v, "so"), w) for v, w in zip(so, ra["so"]) if render.fmt(v, "so") != w]
	c(f"so (số nguyên) khớp fmtNum trên {len(so)} giá trị", not lech, str(lech[:5]))


doi_chieu_node()

# ══ 2. fill ═══════════════════════════════════════════════════════════════════
print("\n— fill: thay placeholder, path / kiểu / nhóm / cú pháp —")
f = render.fill(f"Phải thu {{{{{R}.kpis.total|tien}}}}, quá hạn {{{{{R}.kpis.overdue|tien}}}} "
	f"({{{{ {R}.kpis.overdue_pct | pct }}}}), DSO {{{{{R}.kpis.dso|so}}}} ngày, tính đến {{{{{R}.as_of|ngay}}}}; "
	f"phải trả quá hạn {{{{phai-tra.payables.ap.due.overdue_total|tien}}}} / {{{{{R}.kpis.total|tien}}}}", PACK)
# 1,6e9 → "1,6 tỷ"; 33e6 → "33 triệu"; 35,25 → "35,3%"; 45,3 → "45,3"; 2026-11-05 → "5/11/2026"; 1.050.000 → "1,1 triệu"
eq("lời đã thay số (cả placeholder có dấu cách)", f.text,
	"Phải thu 1,6 tỷ, quá hạn 33 triệu (35,3%), DSO 45,3 ngày, tính đến 5/11/2026; phải trả quá hạn 1,1 triệu / 1,6 tỷ")
eq("paths theo thứ tự, không trùng", f.paths, [f"{R}.kpis.total", f"{R}.kpis.overdue", f"{R}.kpis.overdue_pct",
	f"{R}.kpis.dso", f"{R}.as_of", "phai-tra.payables.ap.due.overdue_total"])
eq("sections_used theo thứ tự, không trùng", f.sections_used, ["cong-no", "phai-tra"])
eq("không lỗi", f.errors, [])
f = render.fill(f"{{{{{R}.top_overdue[1].customer_name|chu}}}} nợ {{{{{R}.top_overdue[1].overdue|tien}}}} "
	f"({{{{{R}.top_overdue[1].max_days|so}}}} ngày), từ {{{{{R}.top_overdue[0].oldest|ngay}}}}", PACK, NHOM)
eq("path có chỉ số mảng + kiểu chu / ngay (date)", (f.text, f.errors), ("Công ty ABC nợ 100 triệu (95 ngày), từ 8/7/2026", []))
eq("999.999.999 trong lời → '1.000 triệu'", render.fill("{{phai-tra.payables.top[0].amount|tien}}", PACK).text, "1.000 triệu")

LOI_FILL = [
	(f"{{{{{R}.kpis.khong_co|tien}}}}", None, [f"path:{R}.kpis.khong_co"], "path không có"),
	(f"{{{{{R}.top_overdue[5].overdue|tien}}}}", None, [f"path:{R}.top_overdue[5].overdue"], "chỉ số mảng vượt"),
	("{{cong-no..kpis|so}}", None, ["path:cong-no..kpis"], "path sai cú pháp"),
	("{{@so_khach|so}}", None, ["path:@so_khach"], "@tên chưa mở (chỉ registry.run_rules mở)"),
	(f"{{{{{R}.kpis.total|chu}}}}", None, [f"kieu:{R}.kpis.total"], "số mà khai chu"),
	(f"{{{{{R}.as_of|tien}}}}", None, [f"kieu:{R}.as_of"], "chuỗi ngày mà khai tien"),
	(f"{{{{{R}.kpis.trong|so}}}}", None, [f"kieu:{R}.kpis.trong"], "giá trị None"),
	(f"{{{{{R}.kpis.co|so}}}}", None, [f"kieu:{R}.kpis.co"], "bool không phải số"),
	(f"{{{{{R}.kpis.ten_dai|chu}}}}", None, [f"kieu:{R}.kpis.ten_dai"], "chu dài 121 ký tự"),
	(f"{{{{{R}.kpis.total|xyz}}}}", None, [f"kieu:{R}.kpis.total"], "kiểu lạ"),
	(f"{{{{{R}.kpis|so}}}}", None, [f"kieu:{R}.kpis"], "trỏ vào cả khối"),
	(f"{{{{{R}.kpis.total|ngay}}}}", None, [f"kieu:{R}.kpis.total"], "số mà khai ngay"),
	("{{ton-kho.overview.value|tien}}", NHOM, ["ngoai-nhom:ton-kho.overview.value"], "path NGOÀI nhóm (dù có thật)"),
	("{{he-thong.khong.co|so}}", NHOM, ["ngoai-nhom:he-thong.khong.co"], "ngoài nhóm xét trước khi phân giải"),
	(f"{{{{{R}.kpis.total}}}}", None, ["cu-phap"], "thiếu kiểu"),
	(f"{{{{{R}.kpis.total|Tien}}}}", None, ["cu-phap"], "kiểu viết hoa"),
	(f"{{{R}.kpis.total|tien}}", None, ["cu-phap"], "ngoặc nhọn đơn"),
	(f"{{{{{R}.kpis.total|tien}}", None, ["cu-phap"], "thiếu ngoặc đóng"),
	("còn }} lẻ", None, ["cu-phap"], "ngoặc đóng lẻ"),
	(f"{{{{{R}.kpis.x|so}}}} {{{{{R}.kpis.x|so}}}} {{{{a|so}}", None, [f"path:{R}.kpis.x", "cu-phap"], "lỗi không lặp"),
]
for text, secs, want, nhan in LOI_FILL:
	f = render.fill(text, PACK, secs)
	c(f"fill lỗi — {nhan} → {want}", f.errors == want and f.paths == [] and f.sections_used == [], f"{f.errors}")
f = render.fill(f"{{{{{R}.kpis.khong_co|tien}}}}", PACK)
eq("placeholder lỗi để nguyên trong lời", f.text, f"{{{{{R}.kpis.khong_co|tien}}}}")
f = render.fill(f"A {{{{{R}.kpis.total|tien}}}} B {{{{cong-no.x|so}}}}", PACK)
eq("một đúng một sai: cái đúng vẫn thay, path đúng vẫn ghi", (f.text, f.paths, f.errors),
	("A 1,6 tỷ B {{cong-no.x|so}}", [f"{R}.kpis.total"], ["path:cong-no.x"]))
eq("ton-kho hợp lệ khi không giới hạn nhóm", render.fill("{{ton-kho.overview.value|tien}}", PACK).text, "2 tỷ")
eq("sections nhận list / set", render.fill("{{ton-kho.overview.value|tien}}", PACK, {"ton-kho"}).errors, [])
eq("sections là MỘT chuỗi = một mảng (không tách từng ký tự)", (render.fill(f"{{{{{R}.kpis.total|tien}}}}", PACK, "cong-no").errors,
	render.fill("{{ton-kho.overview.value|tien}}", PACK, "cong-no").errors), ([], ["ngoai-nhom:ton-kho.overview.value"]))
f = render.fill(f"Mã {{{{{R}.kpis.nhan|chu}}}}", PACK)
eq("GIÁ TRỊ có ngoặc nhọn không bị coi là placeholder hỏng", (f.text, f.errors), ("Mã Bánh {đặc biệt} hộp 12 cái", []))
eq("lời rỗng / None", (render.fill("", PACK).text, render.fill(None, PACK).text, render.fill(None, PACK).errors), ("", "", []))
eq("strip_placeholders: mỗi placeholder hợp lệ → một dấu cách", render.strip_placeholders(
	f"Nợ {{{{{R}.kpis.total|tien}}}}, chiếm {{{{ {R}.kpis.overdue_pct | pct }}}}%"), "Nợ  , chiếm  %")
eq("strip_placeholders: placeholder hỏng giữ nguyên", render.strip_placeholders("a {{b}} c"), "a {{b}} c")
c("fill không đổi pack", PACK["cong-no"]["receivables"]["kpis"]["total"] == 1_600_000_000)

# ══ 3. lint ═══════════════════════════════════════════════════════════════════
print("\n— lint: PHẢI BẮT (mọi dạng số trần mô hình có thể viết) —")
BAT = [
	# Ba ca của đặc tả §9.3
	("Doanh thu đạt 1.250.000 trong tháng", ["1.250.000"], "nhóm nghìn bằng dấu chấm"),
	("Nợ quá hạn chiếm 35% phải thu", ["35%"], "số + %"),
	("Tồn kho khoảng 2 tỷ", ["2 tỷ"], "số + tỷ"),
	# Dấu nhóm nghìn / phần lẻ: mọi số có . , giữa các chữ số là số liệu, dù ngắn
	("còn 1,250 hộp", ["1,250"], "nhóm nghìn bằng dấu phẩy"),
	("tổng 1 250 000 đ", ["1 250 000 đ"], "nhóm nghìn bằng dấu cách"),
	("tổng 1\u00a0250\u00a0000", ["1 250 000"], "nhóm nghìn bằng dấu cách không ngắt (NBSP)"),
	("tổng 1\u202f250", ["1 250"], "nhóm nghìn bằng dấu cách hẹp"),
	("DSO 45,3 ngày", ["45,3"], "số có phần lẻ không kèm đơn vị vẫn là số liệu"),
	("ngày 05.11.2026", ["05.11.2026"], "ngày viết bằng dấu chấm KHÔNG thuộc ngoại lệ (chỉ nhận dấu /)"),
	# Dãy ≥ 3 chữ số
	("có 1250 đơn", ["1250"], "dãy 4 chữ số"),
	("quá hạn 120 ngày", ["120"], "số ngày 3 chữ số là số liệu (ngoại lệ thời hạn chỉ ≤ 2 chữ số)"),
	("top 100 khách", ["100"], "'top 100' cũng bị bắt (chấp nhận loại nhầm)"),
	("năm 1999", ["1999"], "năm ngoài 20xx"),
	("mã 20260", ["20260"], "5 chữ số bắt đầu bằng 20 không phải năm"),
	("ISO 22000", ["22000"], "số tiêu chuẩn cách chữ một dấu cách: không phải mã dính liền"),
	("Bánh quy 300g bán chậm", ["300"], "tên hàng có số viết thẳng → phải đi qua {{…|chu}}"),
	("từ 100-200 đơn", ["100", "200"], "khoảng số: gạch nối sau SỐ không tạo thành mã"),
	("giảm-150 đơn", ["150"], "gạch nối sau chữ thường không tạo thành mã"),
	("mức A1.250.000 chưa rõ", ["1.250.000"], "số có dấu nhóm nghìn dính chữ: không phải mã"),
	# Số + đơn vị (kể cả 1–2 chữ số), dính liền hay cách
	("tăng 35 % so cùng kỳ", ["35 %"], "số, dấu cách, %"),
	("tồn 2tỷ hàng Tết", ["2tỷ"], "số dính liền đơn vị"),
	("nợ 2 tỉ", ["2 tỉ"], "chính tả 'tỉ'"),
	("nợ 2 tỷ đồng", ["2 tỷ đồng"], "tỷ đồng"),
	("quá hạn 1,5 triệu", ["1,5 triệu"], "số lẻ + triệu"),
	("mỗi đơn 50k", ["50k"], "k"),
	("mỗi đơn 50K", ["50K"], "K hoa"),
	("còn 12 nghìn hộp", ["12 nghìn"], "nghìn"),
	("còn 12 ngàn hộp", ["12 ngàn"], "ngàn"),
	("tăng 12,5%", ["12,5%"], "số lẻ + %"),
	("giảm 10–15% so cùng kỳ", ["15%"], "khoảng 10–15%: vế có % bị bắt → cả lời bị loại"),
	("phí 7 tr mỗi tháng", ["7 tr"], "tr"),
	("phí 7tr/tháng", ["7tr"], "tr dính liền"),
	("nợ 50 trđ", ["50 trđ"], "trđ"),
	("nợ 3 trăm triệu", ["3 trăm triệu"], "số + trăm triệu"),
	("giá 450.000đ", ["450.000đ"], "đ dính liền"),
	("giá 5 đ", ["5 đ"], "đ"),
	("giá 450.000 ₫", ["450.000 ₫"], "₫"),
	("giá 20 đồng", ["20 đồng"], "đồng"),
	("giá 50 USD", ["50 USD"], "USD"),
	("giá $50", ["$50"], "ký hiệu tiền đứng TRƯỚC"),
	("giá VND 50 mỗi hộp", ["VND 50"], "chữ VND đứng TRƯỚC"),
	("chiếm 35 phần trăm", ["35 phần trăm"], "'phần trăm' viết chữ"),
	("tăng 2 điểm phần trăm", ["2 điểm phần trăm"], "điểm phần trăm"),
	("tăng 2 điểm %", ["2 điểm %"], "điểm %"),
	("tỷ lệ 5‰", ["5‰"], "phần nghìn"),
	("tăng12% so cùng kỳ", ["12%"], "đơn vị thắng luật 'dính chữ đứng trước'"),
	("dự kiến 2026 triệu", ["2026 triệu"], "năm 20xx kèm đơn vị không còn là năm"),
	("vay 1tỷ6", ["1tỷ"], "viết tắt '1 tỷ 6': đơn vị kẹp giữa hai chữ số"),
	("phí 2tr5 mỗi chuyến", ["2tr"], "viết tắt '2 triệu rưỡi'"),
	("tồn 2 tỷ giá trị hàng", ["2 tỷ"], "'tỷ giá trị' vẫn là tiền (khác 'tỷ giá')"),
	("khoảng 1,2-1,5 tỷ", ["1,2", "1,5 tỷ"], "khoảng số lẻ"),
	("đạt 100% chỉ tiêu", ["100%"], "'100%' cũng là số liệu"),
	# Chữ số không phải ASCII, ký tự vô hình
	("có １２５０ đơn", ["1250"], "chữ số toàn chiều rộng"),
	("chiếm ３５％", ["35%"], "chữ số và % toàn chiều rộng"),
	("có 1\u200b250 đơn", ["1250"], "ký tự vô hình chen giữa chữ số"),
	("có ١٢٥٠ đơn", ["١٢٥٠"], "chữ số Ả Rập"),
	("nợ **2** tỷ, tăng `35` %", ["2 tỷ", "35 %"], "dấu nhấn markdown chen giữa số và đơn vị"),
	# Số viết bằng chữ / tự tính
	("khoảng hai tỷ đồng", ["hai tỷ"], "số bằng chữ + tỷ"),
	("nợ vài trăm triệu", ["vài trăm triệu"], "ước lượng bằng chữ"),
	("nợ hai mươi tư triệu", ["hai mươi tư triệu"], "số bằng chữ nhiều từ"),
	# Tối đa 8 từ số trước một đơn vị: 8 từ đầu + "năm" không phải đơn vị → lùi về 7 từ + đơn vị "trăm"; phần còn lại
	# "năm mươi sáu" + "tỷ" thành mẩu thứ hai. (Không chặn 8 thì regex chạy bậc hai trên lời dài toàn chữ số.)
	("một trăm hai mươi ba nghìn bốn trăm năm mươi sáu tỷ", ["một trăm hai mươi ba nghìn bốn trăm", "năm mươi sáu tỷ"],
		"số bằng chữ rất dài: bắt thành hai mẩu"),
	("phiếu X" + "-ABC" * 12 + "-123", ["123"], "chuỗi nối gạch dài hơn 40 ký tự không còn là mã"),
	("tăng mười phần trăm", ["mười phần trăm"], "phần trăm bằng chữ"),
	("thiệt hại nhiều tỷ đồng", ["nhiều tỷ"], "'nhiều tỷ'"),
	("mất nửa tỷ", ["nửa tỷ"], "'nửa tỷ'"),
	("có hàng trăm khách", ["hàng trăm"], "'hàng trăm'"),
	("có hàng chục NPP giảm mua", ["hàng chục"], "'hàng chục'"),
	("có ba trăm khách", ["ba trăm"], "số đếm ≥ 100 viết bằng chữ"),
	("mất khoảng tỷ rưỡi", ["tỷ rưỡi"], "'tỷ rưỡi'"),
	("hàng tồn tiền tỷ, lỗ cả tỷ đồng", ["tiền tỷ", "cả tỷ"], "'tiền tỷ', 'cả tỷ'"),
	("tăng gấp đôi cùng kỳ", ["gấp đôi"], "bội số bằng chữ"),
	("cao gấp 3 lần", ["gấp 3"], "bội số"),
	("cao gấp 1,5 lần", ["1,5"], "bội số có phần lẻ (bắt một lần)"),
	("tăng ×3", ["×3"], "dấu nhân"),
	("chiếm 2/3 doanh số", ["2/3"], "'chiếm a/b' là phân số, không phải ngày"),
	("đạt 3/5 chỉ tiêu", ["3/5"], "'đạt a/b' là phân số"),
	("doanh số giảm 1/3 so với cùng kỳ, chỉ còn gần 1/4 chưa thu", ["1/3", "1/4"], "'giảm a/b', 'còn gần a/b' là phân số"),
	("tăng 1/2, mất 2/5, thêm 1/5, thiếu 3/4, vượt 1/10", ["1/2", "2/5", "1/5", "3/4", "1/10"], "động từ tăng giảm + a/b"),
	("1/3 số khách giảm mua", ["1/3"], "'a/b số …' là phân số"),
	("nợ khoảng 2/3 tỷ đồng", ["2/3", "tỷ đồng"], "a/b + ĐƠN VỊ là phân số, không phải ngày (không có chữ gợi ý đứng "
		"trước); 'tỷ đồng' còn lại trơ trọi cũng bị bắt — chỗ đã bắt KHÔNG bắc cầu thành 'khoảng tỷ'"),
	("2/3 tổng nợ nằm ở một khách", ["2/3"], "'a/b tổng …' là phân số"),
	("đạt 45/60 điểm", ["45/60"], "a/b không thể là ngày"),
	("mốc 32/13 và 12/15", ["32/13", "12/15"], "ngày > 31, tháng > 12: không phải ngày"),
	("tuần 45/2026", ["45/2026"], "45 không phải tháng (chấp nhận loại nhầm 'tuần/năm')"),
	("được 95/100 điểm", ["95/100"], "a/b có 3 chữ số"),
	("hạn 05/11/1999", ["05/11/1999"], "năm ngoài 20xx trong ngày"),
	("kỳ 13/2026", ["13/2026"], "tháng 13"),
	("chiếm một nửa nợ quá hạn", ["một nửa"], "'một nửa'"),
	("một phần ba số khách", ["một phần ba"], "phân số bằng chữ"),
	("chiếm ½ doanh số", ["½"], "ký tự phân số"),
	# Đơn vị "trăm" / "vạn" sau chữ số; nói độ lớn KHÔNG kèm số ("gần tỷ", "tỷ hai", "… tỷ đồng")
	("có 5 trăm khách", ["5 trăm"], "số + trăm: '5 trăm' = 500 (viết '500' thì đã bị bắt)"),
	("khoảng 5 vạn hộp", ["5 vạn"], "số + vạn"),
	("còn vài vạn hộp", ["vài vạn"], "'vài vạn'"),
	("nợ gần tỷ đồng", ["gần tỷ"], "ước lượng không có số: 'gần tỷ'"),
	("mất hơn trăm khách, lên tới nghìn đơn", ["hơn trăm", "tới nghìn"], "'hơn trăm', 'tới nghìn'"),
	("vốn đầu tư tỷ đồng chưa giải ngân", ["tỷ đồng"], "'… tỷ đồng' trơ trọi vẫn là nói độ lớn; và 'đầu tư tỷ' "
		"KHÔNG phải 'tư tỷ' (bốn tỷ)"),
	("nợ tỷ hai, lỗ triệu mốt", ["tỷ hai", "triệu mốt"], "'tỷ hai' = 1,2 tỷ; 'triệu mốt' = 1,1 triệu"),
	("chi tiền triệu mỗi chuyến", ["tiền triệu"], "'tiền triệu'"),
	("nửa số khách giảm mua", ["nửa"], "'nửa' trơ trọi là tỷ phần"),
	("nợ __2__ tỷ, tăng _35_%", ["2 tỷ", "35%"], "nhấn markdown bằng gạch dưới chen giữa số và đơn vị"),
	("Hai tỷ đồng nợ quá hạn, nợ 5 Tỷ", ["Hai tỷ", "5 Tỷ"], "chữ số viết hoa đầu câu; sau CHỮ SỐ thì đơn vị viết hoa vẫn bắt"),
	# Mã giả mô hình bịa hoặc chép hỏng (mã hợp lệ đã được Mask.strip bỏ trước khi lint)
	("KH#0099 nợ lớn", ["KH#0099"], "mã giả lạ"),
	("trả NCC#2026 trước", ["NCC#2026"], "mã giả lạ trùng dạng năm cũng không lọt"),
	("KH0001 nợ lớn nhất", ["KH0001"], "mã giả chép hỏng (mất #): không được coi là 'mã có chữ đứng trước'"),
	("KH #0001 và NCC# 0002", ["KH #0001", "NCC# 0002"], "mã giả chép hỏng (thêm dấu cách quanh #)"),
	# Trùng → báo một lần; nhiều mẩu → theo thứ tự xuất hiện
	("1.250.000 rồi lại 1.250.000", ["1.250.000"], "mẩu trùng báo một lần"),
	("tăng 35% lên 2 tỷ, top 5, còn 1250", ["35%", "2 tỷ", "1250"], "nhiều mẩu, đúng thứ tự"),
]
for text, want, nhan in BAT:
	eq(f"bắt — {nhan}: {text!r}", render.lint(text), want)

print("\n— lint: PHẢI GIỮ (ngoại lệ của đặc tả + chữ dễ nhầm đơn vị) —")
GIU = [
	("Phòng Kế toán thu hồi công nợ trong 7 ngày.", "thời hạn trong khuyến nghị (đặc tả §9.3)"),
	("Rà soát trong 30 ngày tới, nhóm quá hạn trên 90 ngày", "số ngày ≤ 2 chữ số"),
	("Kế hoạch năm 2026 và mùa Tết 2027", "năm 20xx"),
	("giai đoạn 2025-2026", "khoảng năm"),
	("chốt ngày 5/11", "ngày d/m"),
	("tăng ca từ 6/11, giảm tải sau 7/11, còn hạn đến 30/11, khoảng 5/11 sẽ giao", "động từ tăng giảm nhưng có chữ khác "
		"chen trước ngày; 'khoảng d/m' là ngày"),
	("hoàn tất trước 05/11/2026", "ngày d/m/yyyy"),
	("hạn 05/11/26", "ngày d/m/yy"),
	("kỳ tháng 10/2026 và quý 3/2026", "tháng/năm, quý/năm"),
	("từ 5-7/11, đến 5/11 phải xong", "khoảng ngày"),
	("giao được ngày 5/11", "có chữ 'ngày' chen giữa nên không phải 'được a/b'"),
	("mốc 5/11 tổng kết quý, mốc 7/11 tổng hợp số", "'tổng kết', 'tổng hợp' sau ngày (không có chữ chỉ ngày đứng trước)"),
	("ngày 2/3 số đơn tăng", "'a/b số …' nhưng có chữ 'ngày' đứng trước → ngày"),
	("từ 2/3 tỷ lệ trả hàng tăng, 5/11 đã giao, 7/11 khách nhận", "ngày + 'tỷ lệ' / 'đã' / 'khách': không phải đơn vị"),
	("5/11 số liệu được chốt, đến 5/11 tổng hợp", "'số liệu', 'tổng hợp' sau ngày"),
	("năm tài chính 2026/2027, niên độ 2026/27", "năm/năm"),
	("kỳ Q3/2026 và T10/2026 (05/11), từ 5/11-10/11", "mã kỳ, ngày trong ngoặc, khoảng ngày"),
	("xử lý trong 24h, chậm nhất 48 giờ", "số giờ ≤ 2 chữ số"),
	("quý 3 tỷ giá tăng", "'tỷ giá'"),
	("cập nhật lúc 5:30 mỗi sáng, họp 17h30", "giờ"),
	("quý 3, top 5, tuần 45, ca 2, lần 2, thứ 2", "số thứ tự"),
	("mã SR900 bán chậm", "mã có chữ đứng liền trước (đặc tả)"),
	("phiếu KK-2026-002 và ACC-SINV-2026-00012", "số trong mã chứng từ viết hoa nối bằng gạch"),
	("phiếu ACC-SINV-PINV-STE-MAT-HGC-KK-2026-00012", "mã dài 39 ký tự vẫn là mã"),
	("kho HGC/2026/001", "mã nối bằng dấu /"),
	("kỳ T10, Q4, đợt N1", "mã ngắn"),
	("diện tích 50 m²", "m² → m2 sau chuẩn hoá: chữ số dính chữ"),
	("5 khách, 7 trường hợp, 10 kênh, 3 đơn, 12 đơn vị, 3 đợt", "k / tr / đ là đầu một TỪ, không phải đơn vị"),
	("5 km, 2 kg, 10 KPI, 5 KH lớn", "km / kg / KPI / KH"),
	("Quý 3 tỷ lệ giao lần đầu giảm", "'3 tỷ lệ': tỷ lệ không phải đơn vị"),
	("trong 2026 tỷ lệ trả hàng tăng, tháng 10 tỷ trọng kênh MT tăng", "tỷ lệ / tỷ trọng sau số"),
	("trong năm tỷ lệ trả hàng tăng", "'năm tỷ lệ': không phải 'năm tỷ'"),
	("ngày 5 triệu tập họp", "'triệu tập'"),
	("thứ tư triệu tập họp, vốn đầu tư tỷ lệ thấp", "'tư triệu tập', 'đầu tư tỷ lệ'"),
	("tính theo tỷ lệ phần trăm, bao nhiêu phần trăm chưa rõ", "'phần trăm' không có số đứng trước"),
	("một số khách, ba kênh, hai NPP lớn", "số đếm nhỏ viết bằng chữ"),
	("cần gấp rút xử lý", "'gấp rút'"),
	("nửa đầu tháng 11, hơn nửa đầu năm", "'nửa đầu …' là thời gian"),
	("hơn nửa năm qua, gần nửa tháng nay", "'nửa năm', 'nửa tháng' là thời gian"),
	("cả năm tỷ lệ trả hàng thấp, số tiền tỷ giá chênh lệch nhỏ", "'cả năm tỷ lệ', 'tiền tỷ giá'"),
	("ba mươi khách, hai chục đơn", "số đếm < 100 viết bằng chữ (như '30 khách' viết số)"),
	("năm ngoái, năm nay, hằng năm", "'năm' là thời gian"),
	("hỗ trợ 24/7", "trùng dạng ngày d/m — chấp nhận lọt (đặc tả giữ d/m)"),
	("vượt tỷ lệ cho phép, đến tỷ giá mới, gần triệu chứng cũ", "chữ ước lượng + 'tỷ lệ' / 'tỷ giá' / 'triệu chứng'"),
	("nửa cuối năm, nửa sau tháng 11, nửa đêm, nửa mùa Tết, làm nửa chừng, nửa vời", "'nửa …' chỉ thời gian / thành ngữ"),
	("mã KH-0001 và NCC-2026-001", "mã viết hoa nối gạch là mã chứng từ thật — mã giả luôn có dấu #"),
	("rà soát quá tỉ mỉ, dẫn đến triệu hồi sản phẩm", "'tỉ mỉ', 'triệu hồi' không phải đơn vị"),
	("giao đến Triệu Sơn, hàng Vạn Phúc, tiền Triệu Sơn, cả Vạn Ninh, Tỷ Hai", "tên riêng viết HOA: đơn vị không có "
		"chữ số đứng trước chỉ nhận khi viết thường"),
	("5 chục khách, vài chục đơn", "'chục' không kèm đơn vị lớn: như số < 100 viết bằng số"),
	("phiếu KK_2026_002", "mã nối bằng gạch dưới"),
	("DSO 62 ngày, tăng 5 lần", "GIỚI HẠN đã biết: số ≤ 2 chữ số không kèm đơn vị luôn lọt (đặc tả cho phép "
		"'trong 7 ngày') dù ở đây là số liệu — đề bài (bc.ai.prompt) phải răn, lint không phân biệt được"),
	("mục x2", "chữ số dính chữ đứng trước (đặc tả giữ)"),
	("", "lời rỗng"),
	(None, "None"),
	("Không có số nào trong lời này.", "lời không có số"),
]
for text, nhan in GIU:
	eq(f"giữ — {nhan}: {text!r}", render.lint(text), [])
eq("lời còn placeholder: bỏ placeholder rồi mới lint", render.lint(render.strip_placeholders(
	f"Nợ {{{{{R}.kpis.total|tien}}}}, chiếm {{{{{R}.kpis.overdue_pct|pct}}}} trong 7 ngày")), [])

print("\n— lint: lời rất dài / dị dạng vẫn soát xong nhanh (không chạy bậc hai) —")
# Mỗi ca ~0,1–0,2 s khi tuyến tính; bản chạy bậc hai mất hàng chục giây → ngưỡng 5 s cách xa cả hai phía.
DAI = [
	("chuỗi chữ số bằng chữ không có đơn vị", "một hai ba bốn năm sáu bảy tám chín mười " * 1000, []),
	("mã nối gạch rất dài", "A" + "-123" * 10000, ["123"]),       # quá 40 ký tự đầu thì không còn là mã
	("rất nhiều số nhỏ", "1 " * 20000, []),
	("rất nhiều ngày", "5/11 " * 8000, []),
]
for nhan, text, want in DAI:
	t0 = time.monotonic()
	got = render.lint(text)
	dt = time.monotonic() - t0
	c(f"{nhan} ({len(text)} ký tự): đúng kết quả và < 5 s", got == want and dt < 5, f"{dt:.1f} s, {got[:3]}")

# ══ 4. render_rule ════════════════════════════════════════════════════════════
print("\n— render_rule: lời quy tắc (không lint) + số quy tắc tự tính (hợp đồng §1 mục 8) —")
r = render.render_rule(f"Nợ quá hạn chiếm {{{{{R}.kpis.overdue_pct|pct}}}} phải thu",
	f"Quá hạn {{{{{R}.kpis.overdue|tien}}}} trên {{{{{R}.kpis.total|tien}}}}; ngưỡng 20% / 35%, khách quá 90 ngày và ≥ 50 triệu.",
	PACK)
eq("lời quy tắc đã thay số; số trần do CODE viết không bị lint", r, {"ok": True, "title": "Nợ quá hạn chiếm 35,3% phải thu",
	"body": "Quá hạn 33 triệu trên 1,6 tỷ; ngưỡng 20% / 35%, khách quá 90 ngày và ≥ 50 triệu.",
	"paths": [f"{R}.kpis.overdue_pct", f"{R}.kpis.overdue", f"{R}.kpis.total"], "sections_used": ["cong-no"], "errors": []})
r = render.render_rule(f"Nợ {{{{{R}.kpis.sai|tien}}}}", "", PACK)
eq("quy tắc viết sai path → không ok", (r["ok"], r["errors"], r["body"]), (False, [f"path:{R}.kpis.sai"], ""))
r = render.render_rule("Tồn kho {{ton-kho.overview.value|tien}}", f"Phải thu {{{{{R}.kpis.total|tien}}}}", PACK)
eq("lời quy tắc dùng mọi mảng; sections_used gồm cả hai", (r["ok"], r["sections_used"]), (True, ["ton-kho", "cong-no"]))
r = render.render_rule("  ", "thân", PACK)
eq("tiêu đề rỗng → 'rong'", (r["ok"], r["errors"]), (False, ["rong"]))
r = render.render_rule("A" * 250, "", PACK)
eq("tiêu đề quy tắc cắt 200 ký tự, kết bằng …", (len(r["title"]), r["title"][-2:], r["ok"]), (200, "A…", True))

ai_testlib.chi_module()             # không nạp module quy tắc nào của agent khác


@registry.rule("thu.tinh", section="cong-no", sources="cong-no.receivables", vang=1)
def _thu(pack, cfg):
	rows = pack["cong-no"]["receivables"]["top_overdue"]
	return [cfg.signal("vang", "{{@so_khach|so}} khách quá hạn, tổng {{@tong|tien}}",
		detail=f"Lớn nhất: {{{{{R}.top_overdue[0].customer_name|chu}}}} ({{{{{R}.top_overdue[0].overdue|tien}}}})",
		tinh={"so_khach": len(rows), "tong": sum(x["overdue"] for x in rows)})]


pack2 = copy.deepcopy(PACK)
sig = registry.run_rules(pack2, only={"thu.tinh"}).signals[0]
r = render.render_rule(sig.title, sig.detail, pack2)
# tổng = 250.500.000 + 99.950.000 = 350.450.000 → ≥ 1e8 → Math.round(350,45) = 350 → "350 triệu"; 250,5 → "251 triệu"
eq("{{@tên|kiểu}} đã mở thành path _ai và thay được số", r, {"ok": True, "title": "2 khách quá hạn, tổng 350 triệu",
	"body": "Lớn nhất: Tạp hoá 268 Lan Anh (251 triệu)", "paths": ["cong-no._ai.thu_tinh.so_khach",
	"cong-no._ai.thu_tinh.tong", f"{R}.top_overdue[0].customer_name", f"{R}.top_overdue[0].overdue"],
	"sections_used": ["cong-no"], "errors": []})
eq("mô hình cũng trích được số tự tính (cùng nhóm)", render.fill("{{cong-no._ai.thu_tinh.tong|tien}}", pack2, NHOM).text,
	"350 triệu")

# ══ 5. redact.Mask ════════════════════════════════════════════════════════════
print("\n— redact.Mask: thay đúng chuỗi, một mã một đối tác, hoàn nguyên, strip —")
M = redact.Mask([
	("KH#0001", LAN_ANH, {"CUST-0001", LAN_ANH}),
	("KH#0002", ABC, {"CUST-0002", ABC}),
	("NCC#0001", BAO_BI, {"SUP-0001", BAO_BI}),
])
goc = copy.deepcopy(PACK)
goc["cong-no"]["ghi_chu"] = [ABC + " - chi nhánh Hà Nội", "Giao cho " + ABC, ABC.lower(), f"  {ABC}  ", ["lồng", (ABC, 5)]]
goc["cong-no"]["theo_khach"] = {ABC: {"no": 5}, "CUST-0001": LAN_ANH}
truoc = copy.deepcopy(goc)
che = M.mask(goc)
c("mask không đổi obj gốc", goc == truoc)
c("mask trả bản sao SÂU (list / dict con là đối tượng mới)", che is not goc
	and che["cong-no"]["receivables"]["top_overdue"] is not goc["cong-no"]["receivables"]["top_overdue"]
	and che["cong-no"]["receivables"]["top_overdue"][0] is not goc["cong-no"]["receivables"]["top_overdue"][0])
t0 = che["cong-no"]["receivables"]["top_overdue"][0]
eq("mã chứng từ và tên hiển thị của MỘT khách về cùng một mã", (t0["customer"], t0["customer_name"]), ("KH#0001", "KH#0001"))
eq("khách thứ hai, NCC", (che["cong-no"]["receivables"]["top_overdue"][1]["customer_name"],
	che["phai-tra"]["payables"]["top"][0]["supplier"], che["phai-tra"]["payables"]["top"][0]["supplier_name"]),
	("KH#0002", "NCC#0001", "NCC#0001"))
eq("số, ngày, None, bool giữ nguyên", (t0["overdue"], t0["oldest"], che["cong-no"]["receivables"]["kpis"]["trong"],
	che["cong-no"]["receivables"]["kpis"]["co"]), (250_500_000, datetime.date(2026, 7, 8), None, True))
eq("chuỗi chỉ CHỨA tên (chuỗi con), khác hoa thường: không thay; bằng tên sau khi bỏ khoảng trắng hai đầu: thay; "
	"chuỗi trong list / tuple lồng: thay", che["cong-no"]["ghi_chu"],
	[ABC + " - chi nhánh Hà Nội", "Giao cho " + ABC, ABC.lower(), "KH#0002", ["lồng", ("KH#0002", 5)]])
eq("khoá dict KHÔNG thay (path phải như nhau trên hai bản), giá trị thì thay", che["cong-no"]["theo_khach"],
	{ABC: {"no": 5}, "CUST-0001": "KH#0001"})
gui = json.dumps({k: v for k, v in che.items()}, ensure_ascii=False, default=str)
c("§9.5: tên / mã khách, NCC không còn trong giá trị gửi mô hình",
	all(json.dumps(x, ensure_ascii=False) not in gui for x in (LAN_ANH, "CUST-0002", "SUP-0001", BAO_BI))
	and gui.count(ABC) == 3, gui[:300])      # ABC còn đúng 3 lần: 2 chuỗi con + 1 khoá dict (đã kiểm ở trên)
eq("cùng path: bản gốc ra tên thật, bản che ra mã giả", (registry.resolve(goc, f"{R}.top_overdue[0].customer_name"),
	registry.resolve(che, f"{R}.top_overdue[0].customer_name")), (LAN_ANH, "KH#0001"))
eq("unmask mọi mã đã biết", M.unmask("KH#0001 và KH#0002, trả (NCC#0001). KH#0001"),
	f"{LAN_ANH} và {ABC}, trả ({BAO_BI}). {LAN_ANH}")
eq("unmask: mã lạ, mã dài hơn, mã dính chữ để nguyên", M.unmask("KH#0099 KH#00012 KH#0001x XKH#0001 kh#0001 NCC#0002"),
	"KH#0099 KH#00012 KH#0001x XKH#0001 kh#0001 NCC#0002")
eq("strip: mã đã biết → dấu cách, mã lạ sống sót", M.strip("KH#0001 nợ, KH#0099 nợ, NCC#0001."), "  nợ, KH#0099 nợ,  .")
eq("mã lạ sống sót qua strip nên lint bắt", render.lint(M.strip("KH#0001 và KH#0099 và KH#00012")), ["KH#0099", "KH#00012"])
eq("mã hợp lệ đã strip thì lint sạch (chữ số trong mã giả không bị bắt)", render.lint(M.strip("KH#0001 và NCC#0001")), [])
R0 = redact.Mask()
c("Mask() rỗng: mask là bản sao y nguyên, unmask / strip không đổi lời", R0.mask(goc) == goc and R0.mask(goc) is not goc
	and R0.unmask("KH#0001") == "KH#0001" and R0.strip("KH#0001") == "KH#0001")
eq("mask scalar", (M.mask(ABC), M.mask("khác"), M.mask(5), M.mask(None)), ("KH#0002", "khác", 5, None))
# Tên như một con số; trùng chuỗi giữa hai đối tác (đối tác đứng trước giữ chuỗi, hoàn nguyên vẫn đúng tên)
M2 = redact.Mask([
	("KH#0001", "1000", {"2026", "1000"}),
	("KH#0002", "Trùng Tên", {"C-2", "Trùng Tên"}),
	("KH#0003", "Trùng Tên", {"C-3", "Trùng Tên"}),
	("NCC#0001", "Trùng Tên", {"S-1", "Trùng Tên"}),
	("NCC#0002", None, {"S-2", "", None, 7}),
	("ĐT-A", "Mã Tự Đặt", {"X-1"}),
	("ĐT-A-B", "Mã Tự Đặt Dài", {"X-2"}),
])
eq("tên như số: chỉ CHUỖI '1000' / '2026' bị thay, số 1000 / 2026 giữ nguyên",
	M2.mask({"a": "1000", "b": 1000, "c": "2026", "d": 2026, "e": "10000", "f": 1000.0}),
	{"a": "KH#0001", "b": 1000, "c": "KH#0001", "d": 2026, "e": "10000", "f": 1000.0})
eq("tên như số hoàn nguyên được", M2.unmask("KH#0001 nợ"), "1000 nợ")
eq("trùng tên hiển thị: chuỗi về mã của đối tác đứng TRƯỚC; mã chứng từ mỗi bên vẫn riêng",
	M2.mask(["Trùng Tên", "C-2", "C-3", "S-1"]), ["KH#0002", "KH#0002", "KH#0003", "NCC#0001"])
eq("… và mã nào cũng hoàn nguyên về đúng tên hiển thị", M2.unmask("KH#0002 / KH#0003 / NCC#0001"),
	"Trùng Tên / Trùng Tên / Trùng Tên")
eq("thiếu tên hiển thị → dùng chuỗi của đối tác; chuỗi rỗng / None / không phải chuỗi bỏ qua",
	(M2.unmask("NCC#0002"), M2.mask(["S-2", "", None, 7])), ("S-2", ["NCC#0002", "", None, 7]))
eq("mã tự đặt (không theo dạng XX#số): vẫn hoàn nguyên, mã dài không bị mã ngắn ăn mất",
	(M2.unmask("ĐT-A và ĐT-A-B."), M2.strip("ĐT-A-B,ĐT-A")), ("Mã Tự Đặt và Mã Tự Đặt Dài.", " , "))
eq("mã tự đặt dính chữ phía trước / sau: không phải mã", M2.unmask("ĐT-AX, XĐT-A, ĐT-A1"), "ĐT-AX, XĐT-A, ĐT-A1")

# ══ 6. render_insight ═════════════════════════════════════════════════════════
print("\n— render_insight: lời mô hình (đặc tả §5.3 bước 1–4, §9.3, §9.5; hợp đồng §1 mục 9) —")
RAW = {
	"title": f"KH#0001 quá hạn {{{{{R}.top_overdue[0].overdue|tien}}}}",
	"body": (f"Nợ quá hạn chiếm {{{{{R}.kpis.overdue_pct|pct}}}} phải thu ({{{{{R}.kpis.overdue|tien}}}} trên "
		f"{{{{{R}.kpis.total|tien}}}}). KH#0001 và {{{{{R}.top_overdue[1].customer_name|chu}}}} quá hạn lâu nhất, từ "
		f"{{{{{R}.top_overdue[0].oldest|ngay}}}}. Cần kiểm tra: lịch thanh toán với NCC#0001."),
	"advice": ["Phòng Kế toán đối chiếu và thu hồi trong 7 ngày.", "   ",
		"- Phòng Kinh doanh tạm dừng bán chịu cho KH#0001 trước 30/11.",
		"1. Ban giám đốc duyệt hạn mức mới\ntrong quý 4.",
		"Dòng thứ tư bị cắt.", "Dòng thứ năm có 1.250.000 nhưng đã bị cắt nên không xét."],
}


def ri(**doi):
	raw = {**RAW, **doi}
	return render.render_insight(raw, PACK, NHOM, M)


r = ri()
eq("lời đúng → ok, không lỗi", (r["ok"], r["errors"]), (True, []))
eq("tiêu đề: thay số TRƯỚC, hoàn nguyên tên SAU (tên có '268' không bị lint)", r["title"], f"{LAN_ANH} quá hạn 251 triệu")
eq("thân: tỷ / triệu / % / ngày đúng định dạng, mã giả → tên thật, 'chu' lấy tên thật từ pack gốc", r["body"],
	f"Nợ quá hạn chiếm 35,3% phải thu (33 triệu trên 1,6 tỷ). {LAN_ANH} và {ABC} quá hạn lâu nhất, từ 8/7/2026. "
	f"Cần kiểm tra: lịch thanh toán với {BAO_BI}.")
eq("khuyến nghị: bỏ dòng rỗng, bỏ gạch / số đầu dòng, gộp một dòng, tối đa 3; 'trong 7 ngày', '30/11', 'quý 4' được giữ",
	r["advice"], ["Phòng Kế toán đối chiếu và thu hồi trong 7 ngày.",
	f"Phòng Kinh doanh tạm dừng bán chịu cho {LAN_ANH} trước 30/11.", "Ban giám đốc duyệt hạn mức mới trong quý 4."])
eq("paths của cả tiêu đề + thân, theo thứ tự", r["paths"], [f"{R}.top_overdue[0].overdue", f"{R}.kpis.overdue_pct",
	f"{R}.kpis.overdue", f"{R}.kpis.total", f"{R}.top_overdue[1].customer_name", f"{R}.top_overdue[0].oldest"])
eq("sections_used", r["sections_used"], ["cong-no"])
c("lời lưu không còn mã giả, không còn placeholder", not any(x in json.dumps(r, ensure_ascii=False) for x in ("KH#", "NCC#", "{{")))
r = ri(advice=["Phòng Mua hàng làm việc với NCC#0001 về {{phai-tra.payables.ap.due.overdue_count|so}} hoá đơn."])
eq("path trong khuyến nghị cũng vào paths / sections_used", (r["ok"], r["advice"], r["paths"][-1], r["sections_used"]),
	(True, [f"Phòng Mua hàng làm việc với {BAO_BI} về 12 hoá đơn."], "phai-tra.payables.ap.due.overdue_count",
	["cong-no", "phai-tra"]))

# Hợp đồng §1 mục 12: lời quy tắc gửi mô hình là lời CÒN placeholder → không mang tên thật, đi qua mask y nguyên;
# mô hình chép lại placeholder thì máy chủ chèn tên thật + số thật từ pack GỐC (250.500.000 → "251 triệu").
tin_hieu = [{"id": "S1", "rule": "cn.qua_han_lon", "muc": "do", "trang_thai": "mo", "so_ngay": 3,
	"loi_quy_tac": f"{{{{{R}.top_overdue[0].customer_name|chu}}}} quá hạn {{{{{R}.top_overdue[0].overdue|tien}}}}",
	"paths": [f"{R}.top_overdue[0].customer_name", f"{R}.top_overdue[0].overdue"], "ghi_chu_quan_tri": LAN_ANH}]
che_th = M.mask(tin_hieu)
eq("mục 12: lời quy tắc còn placeholder + paths đi qua mask y nguyên; ghi chú BẰNG ĐÚNG tên khách thì bị che",
	(che_th[0]["loi_quy_tac"], che_th[0]["paths"], che_th[0]["ghi_chu_quan_tri"], che_th[0]["rule"], che_th[0]["so_ngay"]),
	(tin_hieu[0]["loi_quy_tac"], tin_hieu[0]["paths"], "KH#0001", "cn.qua_han_lon", 3))
c("… tín hiệu gửi đi không có tên / mã khách thật", not any(x in json.dumps(che_th, ensure_ascii=False)
	for x in (LAN_ANH, "CUST-0001")))
r = render.render_insight({"title": che_th[0]["loi_quy_tac"], "body": "Cần thu hồi sớm.", "advice": []}, PACK, NHOM, M)
eq("… mô hình chép lại lời quy tắc → lời lưu có tên thật và số thật", (r["ok"], r["title"]),
	(True, f"{LAN_ANH} quá hạn 251 triệu"))

LOI_INSIGHT = [
	({"body": "Doanh thu 1.250.000 trong tháng."}, "so-tran:1.250.000", "§9.3: '1.250.000' viết trần"),
	({"body": "Nợ quá hạn chiếm 35% phải thu."}, "so-tran:35%", "§9.3: '35%' viết trần"),
	({"title": "Tồn kho 2 tỷ"}, "so-tran:2 tỷ", "§9.3: '2 tỷ' viết trần (ở tiêu đề)"),
	({"advice": ["Thu trong 7 ngày.", "Giảm hạn mức xuống 500 triệu."]}, "so-tran:500 triệu", "số trần ở khuyến nghị"),
	({"title": "Tồn kho {{ton-kho.overview.value|tien}}"}, "ngoai-nhom:ton-kho.overview.value", "path ngoài nhóm"),
	({"body": f"Nợ {{{{{R}.kpis.khong_co|tien}}}}"}, f"path:{R}.kpis.khong_co", "path sai"),
	({"body": f"Nợ {{{{{R}.kpis.total|ngay}}}}"}, f"kieu:{R}.kpis.total", "sai kiểu"),
	({"advice": [f"Xem {{{{{R}.kpis.total|chu}}}}"]}, f"kieu:{R}.kpis.total", "sai kiểu ở khuyến nghị"),
	({"body": f"Nợ {{{{{R}.kpis.total}}}}"}, "cu-phap", "placeholder hỏng"),
	({"body": "KH#0099 nợ lớn nhất."}, "so-tran:KH#0099", "mã giả mô hình bịa"),
	({"body": "KH#00012 nợ lớn nhất."}, "so-tran:KH#00012", "mã giả lạ có mã thật làm tiền tố"),
	({"title": ""}, "rong", "tiêu đề rỗng"),
	({"title": "  \n "}, "rong", "tiêu đề toàn khoảng trắng"),
	({"title": None}, "rong", "tiêu đề None"),
	({"body": ""}, "rong", "thân rỗng"),
	({"body": 12}, "rong", "thân không phải chuỗi"),
	({"body": f"Có 1{{{{{R}.kpis.over_limit|so}}}} khách vượt hạn mức."}, f"so-tran:1{{{{{R}.kpis.over_limit|so}}}}",
		"chữ số GHÉP trước placeholder (1 + '3' = '13')"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}}.000 khách."}, f"so-tran:{{{{{R}.kpis.over_limit|so}}}}.0",
		"chữ số GHÉP sau placeholder ('3' + '.000')"),
	({"body": f"Vượt {{{{{R}.kpis.over_limit|so}}}} triệu."}, f"so-tran:{{{{{R}.kpis.over_limit|so}}}} triệu",
		"đơn vị nhân sau placeholder số ('3' thành '3 triệu')"),
	({"body": f"Vượt {{{{{R}.kpis.overdue|tien}}}}k."}, f"so-tran:{{{{{R}.kpis.overdue|tien}}}}k", "'k' sau placeholder tiền"),
	({"body": f"Có 1 {{{{{R}.kpis.over_limit|so}}}} khách."}, f"so-tran:1 {{{{{R}.kpis.over_limit|so}}}}",
		"chữ số + dấu cách + placeholder kiểu so ('1 3' đọc như nhóm nghìn)"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}} 000 khách."}, f"so-tran:{{{{{R}.kpis.over_limit|so}}}} 000",
		"placeholder kiểu so + ' 000'"),
	({"body": f"Tháng 11 {{{{{R}.kpis.over_limit|so}}}} khách vượt hạn mức."}, f"so-tran:11 {{{{{R}.kpis.over_limit|so}}}}",
		"số RỜI 2 chữ số + placeholder so ('11 250' dễ đọc thành một số)"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}} trăm khách."}, f"so-tran:{{{{{R}.kpis.over_limit|so}}}} trăm",
		"'trăm' sau placeholder số (3 thành 300)"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}} chục khách."}, f"so-tran:{{{{{R}.kpis.over_limit|so}}}} chục",
		"'chục' sau placeholder số (3 thành 30)"),
	({"body": "KH0001 nợ lớn nhất."}, "so-tran:KH0001", "mã giả chép hỏng (mất #) trong lời mô hình"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}}{{{{{R}.kpis.qua_120|so}}}} khách."},
		f"so-tran:{{{{{R}.kpis.over_limit|so}}}}{{{{{R}.kpis.qua_120|so}}}}", "hai placeholder số dính liền (3 và 5 thành '35')"),
	({"body": f"Gấp {{{{{R}.kpis.over_limit|so}}}},{{{{{R}.kpis.qua_120|so}}}} lần."},
		f"so-tran:{{{{{R}.kpis.over_limit|so}}}},{{{{{R}.kpis.qua_120|so}}}}", "hai placeholder số nối bằng dấu phẩy ('3,5')"),
	({"body": f"Nợ {{{{{R}.kpis.total|tien}}}}.{{{{{R}.kpis.over_limit|so}}}} đồng."},
		f"so-tran:{{{{{R}.kpis.total|tien}}}}.{{{{{R}.kpis.over_limit|so}}}}", "tien + '.' + so"),
	({"body": f"Có {{{{{R}.kpis.over_limit|so}}}} {{{{{R}.kpis.qua_120|so}}}} khách."},
		f"so-tran:{{{{{R}.kpis.over_limit|so}}}} {{{{{R}.kpis.qua_120|so}}}}", "hai placeholder so cách một dấu cách ('3 5' / '3 250')"),
]
for doi, want, nhan in LOI_INSIGHT:
	r = ri(**doi)
	c(f"loại — {nhan} → {want}", r["ok"] is False and want in r["errors"], f"{r['ok']} {r['errors']}")
r = ri(body=f"Giao lần đầu {{{{{R}.kpis.overdue_pct|pct}}}} tỷ lệ còn thấp; {{{{{R}.kpis.over_limit|so}}}} khách, "
	f"{{{{{R}.kpis.over_limit|so}}}} trường hợp.")
eq("'tỷ lệ', 'khách', 'trường hợp' sau placeholder số không phải đơn vị nhân", (r["ok"], r["errors"]), (True, []))
r = ri(body=f"Phải thu cuối quý 3 {{{{{R}.kpis.total|tien}}}}, top 5 {{{{{R}.top_overdue[0].customer_name|chu}}}}.")
eq("chữ số + dấu cách + placeholder tien / chu: không phải ghép số", (r["ok"], r["body"]),
	(True, f"Phải thu cuối quý 3 1,6 tỷ, top 5 {LAN_ANH}."))
# over_limit = 3. Ngày (11 đứng sau "/"), năm (4 chữ số), mã (900 dính chữ), giờ (30 đứng sau ":") KHÔNG phải đầu nhóm nghìn
r = ri(body=f"Đến 5/11 {{{{{R}.kpis.over_limit|so}}}} khách vượt hạn mức; năm 2026 {{{{{R}.kpis.over_limit|so}}}} khách; "
	f"mã SR900 {{{{{R}.kpis.over_limit|so}}}} lần; lúc 5:30 {{{{{R}.kpis.over_limit|so}}}} đơn.")
eq("ngày / năm / mã / giờ đứng trước placeholder so không phải số ghép", (r["ok"], r["errors"], r["body"]),
	(True, [], "Đến 5/11 3 khách vượt hạn mức; năm 2026 3 khách; mã SR900 3 lần; lúc 5:30 3 đơn."))
# Hai số THẬT đặt cạnh nhau có dấu phân cách rõ ("3/5"), chu dính so, so cách tien: không tạo ra con số nào mới
r = ri(body=f"{{{{{R}.kpis.over_limit|so}}}}/{{{{{R}.kpis.qua_120|so}}}} khách đã trả; "
	f"{{{{{R}.top_overdue[1].customer_name|chu}}}}{{{{{R}.kpis.over_limit|so}}}} lần trễ; "
	f"nhóm {{{{{R}.kpis.over_limit|so}}}} {{{{{R}.kpis.overdue|tien}}}}.")
eq("'{{a|so}}/{{b|so}}', chu dính so, so cách tien: không phải số ghép", (r["ok"], r["errors"], r["body"]),
	(True, [], "3/5 khách đã trả; Công ty ABC3 lần trễ; nhóm 3 33 triệu."))
r = ri(body=f"Nợ của KH#0001,{{{{{R}.top_overdue[0].overdue|tien}}}} đã quá hạn; KH#0002 {{{{{R}.kpis.over_limit|so}}}} lần trễ.")
eq("chữ số trong mã giả HỢP LỆ đứng sát placeholder không phải số ghép", (r["ok"], r["body"]),
	(True, f"Nợ của {LAN_ANH},251 triệu đã quá hạn; {ABC} 3 lần trễ."))
# Khoá "31_60": nếu lint chạy trên lời CHƯA bỏ placeholder thì ".31_60" thành dãy 4 chữ số "3160" → bị bắt nhầm.
# 7.000.000 → one(7,0) = "7" → "7 triệu"
r = ri(body=f"Có {{{{{R}.kpis.qua_120|so}}}} khách quá hạn lâu, nhóm trễ vừa {{{{{R}.aging.31_60|tien}}}}, "
	f"lớn nhất {{{{{R}.top_overdue[0].overdue|tien}}}}.")
eq("chữ số nằm TRONG path của placeholder (qua_120, aging.31_60, [0]) không bị lint", (r["ok"], r["errors"], r["body"]),
	(True, [], "Có 5 khách quá hạn lâu, nhóm trễ vừa 7 triệu, lớn nhất 251 triệu."))
r = ri(title="Nợ 35% và 35% nữa", body="Lại 35%.")
eq("lỗi trùng báo một lần", r["errors"], ["so-tran:35%"])
r = ri(title=f"{{{{{R}.kpis.x|so}}}} và 2 tỷ", body="")
eq("gom đủ mọi loại lỗi", r["errors"], [f"path:{R}.kpis.x", "so-tran:2 tỷ", "rong"])

dai = "Nợ quá hạn tăng " + "rất " * 60 + "nhanh"       # 16 + 240 + 5 = 261 ký tự
r = ri(title=dai)
eq("tiêu đề dài → cắt còn đúng 200 ký tự, kết bằng …, vẫn ok", (len(r["title"]), r["title"][:16], r["title"][-1], r["ok"]),
	(200, "Nợ quá hạn tăng ", "…", True))
r = ri(title="A" * 200)
eq("tiêu đề đúng 200 ký tự giữ nguyên", r["title"], "A" * 200)
r = ri(title="  Nợ quá hạn\n  tăng nhanh ", body="\n  Cần thu hồi sớm.\nƯu tiên khách lớn.  \n")
eq("tiêu đề gộp một dòng; thân bỏ khoảng trắng hai đầu, giữ xuống dòng giữa", (r["title"], r["body"], r["ok"]),
	("Nợ quá hạn tăng nhanh", "Cần thu hồi sớm.\nƯu tiên khách lớn.", True))
# 198 ký tự trước khi hoàn nguyên (190 + 1 + 7); tên thật dài 19 → 210 ký tự → lấy 199 ký tự đầu = B×190 + " Tạp hoá "
# → bỏ dấu cách cuối (198) + "…" = 199 ký tự
r = ri(title="B" * 190 + " KH#0001")
eq("cắt SAU khi hoàn nguyên tên (không để lọt quá 200)", r["title"], "B" * 190 + " Tạp hoá…")
# 205 ký tự, mã giả nằm vắt qua mốc 200: hoàn nguyên → B×194 + " Tạp hoá 268 Lan Anh nợ"; 199 ký tự đầu = B×194 + " Tạp "
r = ri(title="B" * 194 + " KH#0001 nợ")
eq("mã giả vắt qua mốc cắt: hoàn nguyên TRƯỚC rồi mới cắt (không để sót mẩu 'KH#0')", r["title"], "B" * 194 + " Tạp…")
MK = redact.Mask([("KH#0001", "Đại lý  Hai\tCách", {"C-1"})])
r = render.render_insight({"title": "KH#0001 quá hạn", "body": f"{{{{{R}.kpis.rong|chu}}}} Cần thu hồi sớm.",
	"advice": ["Phòng Kế toán làm việc với KH#0001."]}, PACK, NHOM, MK)
eq("khoảng trắng do tên thật / giá trị rỗng mang vào: tiêu đề + khuyến nghị gộp một dấu cách, thân bỏ đầu cuối",
	(r["ok"], r["title"], r["body"], r["advice"]), (True, "Đại lý Hai Cách quá hạn", "Cần thu hồi sớm.",
	["Phòng Kế toán làm việc với Đại lý Hai Cách."]))
r = ri(body=f"Chủ {{{{{R}.top_overdue[1].customer_name|chu}}}} tỷ phú, đến {{{{{R}.as_of|ngay}}}} k rõ.")
eq("đơn vị nhân chỉ xét sau placeholder SỐ (sau chu / ngay thì không)", (r["ok"], r["errors"]), (True, []))
eq("advice không phải list → []; chuỗi → tách dòng", (ri(advice=None)["advice"], ri(advice="Một.\nHai.")["advice"]),
	([], ["Một.", "Hai."]))
eq("advice có phần tử không phải chuỗi → bỏ", ri(advice=[None, 5, "Được."])["advice"], ["Được."])
eq("khuyến nghị thành rỗng sau khi thay số → bỏ", ri(advice=[f"{{{{{R}.kpis.rong|chu}}}}", "Được."])["advice"], ["Được."])
r = ri(advice=["a.", "b.", "c.", "d."])
eq("đúng 3 khuyến nghị đầu", r["advice"], ["a.", "b.", "c."])
r = ri(advice=["a.", "b.", "Giảm 35% hạn mức.", "d."])
eq("số trần trong 3 khuyến nghị được giữ → loại", (r["ok"], r["errors"]), (False, ["so-tran:35%"]))
for xau in (None, "chuỗi", [], 5):
	r = render.render_insight(xau, PACK, NHOM, M)
	c(f"raw không phải dict ({type(xau).__name__}) → không ok, 'rong'", r["ok"] is False and r["errors"] == ["rong"]
		and r["title"] == "" and r["advice"] == [], str(r))
# Không che tên (ai_mask_parties tắt): mask None / Mask() — mã giả trong lời đều là bịa; tên thật có số viết thẳng bị loại
for nhan, m in (("mask=None", None), ("Mask() rỗng", redact.Mask())):
	r = render.render_insight(RAW, PACK, NHOM, m)
	c(f"{nhan}: mã giả trong lời là mã lạ → loại", r["ok"] is False and "so-tran:KH#0001" in r["errors"], str(r["errors"]))
	r = render.render_insight({"title": f"{{{{{R}.top_overdue[0].customer_name|chu}}}} quá hạn", "body": "Cần thu hồi sớm.",
		"advice": []}, PACK, NHOM, m)
	eq(f"{nhan}: tên qua {{{{…|chu}}}} vẫn dùng được", (r["ok"], r["title"]), (True, f"{LAN_ANH} quá hạn"))
r = render.render_insight({"title": f"{LAN_ANH} quá hạn", "body": "Cần thu hồi sớm."}, PACK, NHOM, None)
eq("tên thật có chữ số viết THẲNG trong lời (không qua placeholder / mã giả) → bị lint bắt", r["errors"], ["so-tran:268"])
r = render.render_insight({"title": "Tồn kho {{ton-kho.overview.value|tien}}", "body": "Ổn."}, PACK, ("ton-kho",), M)
eq("nhóm khác: ton-kho hợp lệ trong nhóm của nó", (r["ok"], r["title"], r["sections_used"]), (True, "Tồn kho 2 tỷ", ["ton-kho"]))
r = render.render_insight({"title": "Tồn kho {{ton-kho.overview.value|tien}}", "body": "Ổn."}, PACK, None, M)
eq("sections=None: không giới hạn nhóm", r["ok"], True)

# ══ 7. redact.build (MariaDB) ═════════════════════════════════════════════════
print("\n— redact.build: bảng ánh xạ từ tabCustomer / tabSupplier —")
reset(only={"Customer", "Supplier"})
# Ghi KHÔNG theo thứ tự name; có tên thường (collation của DB xếp 'an-binh' trước 'CUST-…', Python xếp sau)
insert("Customer", name="CUST-0002", customer_name=ABC)
insert("Customer", name="an-binh", customer_name="Đại lý An Bình")
insert("Customer", name="CUST-0001", customer_name=LAN_ANH)
insert("Customer", name="CUST-0003", customer_name=ABC)              # trùng tên hiển thị với CUST-0002
insert("Customer", name="2026", customer_name="1000")                # tên như số
insert("Customer", name="CUST-0010", customer_name=None)             # không có tên hiển thị
insert("Customer", name="CUST-0011", customer_name="  ", disabled=1)  # tên toàn khoảng trắng; khách đã khoá vẫn che
insert("Supplier", name="SUP-0002", supplier_name=ABC)               # NCC trùng tên một khách
insert("Supplier", name="SUP-0001", supplier_name=BAO_BI)
insert("Supplier", name="CUST-0001", supplier_name="Trùng Mã Khách")  # mã chứng từ trùng mã một khách
B = redact.build()
# Sắp theo name (mã ký tự): "2026" < "CUST-0001" < "CUST-0002" < "CUST-0003" < "CUST-0010" < "CUST-0011" < "an-binh"
# NCC: "CUST-0001" < "SUP-0001" < "SUP-0002"
eq("đánh số theo name tăng dần (không theo thứ tự ghi, không theo collation DB)",
	B.mask(["2026", "CUST-0001", "CUST-0002", "CUST-0003", "CUST-0010", "CUST-0011", "an-binh", "SUP-0001", "SUP-0002"]),
	["KH#0001", "KH#0002", "KH#0003", "KH#0004", "KH#0005", "KH#0006", "KH#0007", "NCC#0002", "NCC#0003"])
eq("tên hiển thị về cùng mã với mã chứng từ", B.mask(["1000", LAN_ANH, "Đại lý An Bình", BAO_BI, "Trùng Mã Khách"]),
	["KH#0001", "KH#0002", "KH#0007", "NCC#0002", "NCC#0001"])
eq("trùng tên giữa hai khách và một NCC: chuỗi về khách có name nhỏ nhất (khách trước NCC)", B.mask(ABC), "KH#0003")
eq("hoàn nguyên: mọi mã về đúng tên hiển thị; không có tên → mã chứng từ",
	B.unmask("KH#0001|KH#0002|KH#0003|KH#0004|KH#0005|KH#0006|KH#0007|NCC#0001|NCC#0002|NCC#0003|KH#0008|NCC#0004"),
	f"1000|{LAN_ANH}|{ABC}|{ABC}|CUST-0010|CUST-0011|Đại lý An Bình|Trùng Mã Khách|{BAO_BI}|{ABC}|KH#0008|NCC#0004")
eq("số 1000 / 2026 trong gói số không bị đụng", B.mask({"nam": 2026, "sl": 1000, "ma": "2026"}),
	{"nam": 2026, "sl": 1000, "ma": "KH#0001"})
che = B.mask(PACK)
gui = json.dumps(che, ensure_ascii=False, default=str)
c("§9.5 trên bảng thật: không tên / mã khách, NCC nào trong gói gửi đi", not any(x in gui for x in
	(LAN_ANH, ABC, BAO_BI, "CUST-000", "SUP-000")) and "KH#0002" in gui and "NCC#0002" in gui, gui[:200])
r = render.render_insight({"title": "KH#0002 quá hạn {{cong-no.receivables.top_overdue[0].overdue|tien}}",
	"body": "KH#0003 cũng quá hạn; cần kiểm tra: công nợ với NCC#0002.", "advice": []}, PACK, NHOM, B)
eq("§9.5: lời lưu có tên thật", (r["ok"], r["title"], r["body"]), (True, f"{LAN_ANH} quá hạn 251 triệu",
	f"{ABC} cũng quá hạn; cần kiểm tra: công nợ với {BAO_BI}."))
eq("dựng lại cho ra cùng bảng (ổn định trong một lượt)", redact.build().mask(["an-binh", "SUP-0002"]), ["KH#0007", "NCC#0003"])
E = redact.build(enabled=False)
eq("enabled=False → không che gì", (E.mask([ABC, "CUST-0001"]), E.unmask("KH#0001")), ([ABC, "CUST-0001"], "KH#0001"))
eq("enabled=0 (giá trị Check) cũng tắt", redact.build(0).mask(ABC), ABC)
frappe.db.queries.clear()
redact.build()
c("build chỉ SELECT", frappe.db.queries and all(q.lstrip().upper().startswith("SELECT") for q in frappe.db.queries),
	str(frappe.db.queries))
drop_column("Supplier", "supplier_name")
B = redact.build()
eq("thiếu cột tên hiển thị → vẫn che mã chứng từ, hoàn nguyên về mã chứng từ",
	(B.mask(["SUP-0001", BAO_BI]), B.unmask("NCC#0002")), (["NCC#0002", BAO_BI], "SUP-0001"))
drop_doctype("Supplier")
B = redact.build()
eq("thiếu tabSupplier → chỉ còn khách", B.mask(["CUST-0001", "SUP-0001", BAO_BI, ABC]), ["KH#0002", "SUP-0001", BAO_BI, "KH#0003"])
drop_doctype("Customer")
B = redact.build()
eq("thiếu cả hai bảng → không lỗi, không che", (B.mask([ABC, "CUST-0001"]), B.unmask("KH#0001 nợ")),
	([ABC, "CUST-0001"], "KH#0001 nợ"))

# ══ 7b. Chữ tự do (ghi chú quản trị) ═════════════════════════════════════════
print("\n— mask_text: che tên khách / NCC nằm giữa câu trong chữ tự do —")
MT = redact.Mask([
	("KH#0001", "Công ty Hùng Phát", {"CUST-0001", "Công ty Hùng Phát"}),
	("KH#0002", "Hùng Phát", {"CUST-0002", "Hùng Phát"}),
	("KH#0003", "An", {"An"}),
	("NCC#0001", "Bột mì Bình Đông (2024)", {"SUP-0001", "Bột mì Bình Đông (2024)"}),
])
eq("tên nằm giữa câu → mã giả", MT.mask_text("Đã gọi Hùng Phát hôm qua, hẹn trả cuối tuần"),
	"Đã gọi KH#0002 hôm qua, hẹn trả cuối tuần")
eq("tên dài thắng tên ngắn là phần của nó", MT.mask_text("Công ty Hùng Phát xin giãn nợ"), "KH#0001 xin giãn nợ")
eq("mã chứng từ cũng được che", MT.mask_text("xem CUST-0001 và SUP-0001."), "xem KH#0001 và NCC#0001.")
eq("tên có ký tự đặc biệt của biểu thức", MT.mask_text("NCC Bột mì Bình Đông (2024) báo tăng giá"),
	"NCC NCC#0001 báo tăng giá")
eq("tên ngắn hơn 4 ký tự không thay (dễ trùng từ thường)", MT.mask_text("An toàn thực phẩm: gọi An"),
	"An toàn thực phẩm: gọi An")
eq("tên dính chữ / số hai bên không thay", MT.mask_text("xHùng Phát, Hùng Phát2, CUST-00012"),
	"xHùng Phát, Hùng Phát2, CUST-00012")
eq("phân biệt hoa thường như mask", MT.mask_text("hùng phát"), "hùng phát")
eq("None / rỗng → chuỗi rỗng", (MT.mask_text(None), MT.mask_text("")), ("", ""))
eq("Mask rỗng (tắt che) → giữ nguyên", redact.Mask().mask_text("Đã gọi Hùng Phát"), "Đã gọi Hùng Phát")
eq("chỉ toàn tên ngắn → giữ nguyên", redact.Mask([("KH#0001", "An", {"An"})]).mask_text("gọi An"), "gọi An")
eq("lời đã che hoàn nguyên được", MT.unmask(MT.mask_text("Đã gọi Hùng Phát hôm qua")), "Đã gọi Hùng Phát hôm qua")
eq("gọi lại lần hai cho cùng kết quả", MT.mask_text("Hùng Phát và Công ty Hùng Phát"), "KH#0002 và KH#0001")

# ══ 8. Luật tĩnh ══════════════════════════════════════════════════════════════
print("\n— luật tĩnh: render thuần (không DB), không module nào đụng mạng / khoá —")
for ten in ("render", "redact"):
	src = open(os.path.join(BC_ROOT, "bc", "ai", f"{ten}.py"), encoding="utf-8").read()
	cay = ast.parse(src)
	nhap = {a.name for n in ast.walk(cay) if isinstance(n, ast.Import) for a in n.names} | {
		f"{n.module}.{a.name}" for n in ast.walk(cay) if isinstance(n, ast.ImportFrom) for a in n.names}
	goi = {n.attr for n in ast.walk(cay) if isinstance(n, ast.Attribute)}
	c(f"{ten}.py không import requests / bc.ai.llm, không đọc khoá", not any("requests" in x or "llm" in x for x in nhap)
		and "bc_ai_" not in src and "conf" not in goi, str(sorted(nhap)))
	if ten == "render":
		c("render.py không import frappe, không gọi db", "frappe" not in nhap and "db" not in goi and "sql" not in goi,
			str(sorted(nhap)))
		c("render.py chỉ import bc.ai.registry trong bc", {x for x in nhap if x.startswith("bc")} == {"bc.ai.registry"},
			str(sorted(nhap)))
	else:
		chuoi = " ".join(n.value for n in ast.walk(cay) if isinstance(n, ast.Constant) and isinstance(n.value, str)
			and "tab" in n.value)
		c("redact.py: SQL không có INSERT / UPDATE / DELETE / ALTER / DROP", not any(k in chuoi.upper() for k in
			("INSERT", "UPDATE", "DELETE", "ALTER", "DROP")) and not {x for x in nhap if x.startswith("bc")}, chuoi)

c.done()
