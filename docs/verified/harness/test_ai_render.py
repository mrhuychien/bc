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
import sys
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
	("ngày 05.11.26", ["05.11.26"], "ngày viết bằng dấu chấm chỉ được ở dạng đủ d.m.yyyy (G1)"),
	("tăng 12.5 lần", ["12.5"], "'12.5' không phải ngày (dạng chấm chỉ nhận d.m.yyyy) — là số có phần lẻ"),
	# Dãy ≥ 3 chữ số
	("có 1250 đơn", ["1250"], "dãy 4 chữ số"),
	("quá hạn 120 ngày", ["120"], "số ngày 3 chữ số là số liệu (ngoại lệ thời hạn chỉ ≤ 2 chữ số)"),
	("top 100 khách", ["100"], "'top 100' cũng bị bắt (chấp nhận loại nhầm)"),
	("năm 1999", ["1999"], "năm ngoài 20xx"),
	("mã 20260", ["20260"], "5 chữ số bắt đầu bằng 20 không phải năm"),
	("iso 22000, ABC 22000", ["22000"], "số tiêu chuẩn chỉ được sau đúng các chữ HOA ISO, HACCP, TCVN, QCVN, TK, QĐ, NĐ, TT (G1)"),
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
	("giảm 10–15% so cùng kỳ", ["10", "15%"], "khoảng 10–15%: cả hai vế bị bắt (G1: '10' không thuộc dạng được phép)"),
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
	("vay 1tỷ6", ["1tỷ", "6"], "viết tắt '1 tỷ 6': đơn vị kẹp giữa hai chữ số"),
	("phí 2tr5 mỗi chuyến", ["2tr", "5"], "viết tắt '2 triệu rưỡi'"),
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
	# H4: ngày viết tay phải đủ năm 20xx — d/m trơ trọi / d/m/yy là số trần, dù chữ nào đứng trước
	("chốt ngày 5/11, hạn đến 30/11", ["5/11", "30/11"], "H4: d/m trơ trọi (kể cả sau 'ngày', 'đến')"),
	("xấp xỉ 1/2, khoảng 2/3 khách, mục tiêu 9/10 đơn, tương đương 3/1", ["1/2", "2/3", "9/10", "3/1"],
		"H4: phân số dạng ngày (verify3 N22–N24, N55–N58)"),
	("hạn 05/11/26", ["05/11/26"], "H4: năm hai chữ số"),
	("hạn 31/2/2026", ["31/2/2026"], "H4: ngày không có thật"),
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
	("tăng 35% lên 2 tỷ, top 5, còn 1250", ["35%", "2 tỷ", "5", "1250"], "nhiều mẩu, đúng thứ tự"),
	# G1 — chữ số viết tay chỉ được ở 4 dạng (năm, ngày, mã, thời hạn / thứ tự ≤ 2 chữ số sau / trước từ chỉ thời gian)
	("99 khách quá hạn, tăng 5 lần", ["99", "5"], "G1: số đếm / bội số ≤ 2 chữ số không kèm đơn vị KHÔNG còn lọt"),
	("top 10 khách, 18 x 10 đơn", ["10", "18"], "G1: 'top 10', '18 x 10' (mẩu trùng báo một lần)"),
	("từ 5-7/11 phải xong", ["5", "7/11"], "G1 + H4: khoảng ngày viết tắt — '5-' và d/m thiếu năm đều bị bắt"),
	("xử lý trong 24h, lúc 5:30, họp 17h30", ["24", "5", "30", "17"], "G1: giờ viết tay"),
	("quý 3, top 5, tuần 45, ca 2, lần 2, thứ 2", ["5", "2"], "G1: 'top' và 'lần' không phải từ chỉ thời gian / thứ tự"),
	("diện tích 50 m², mục x2", ["50", "2"], "G1: chữ số dính chữ thường không phải mã"),
	("5 khách, 7 trường hợp, 10 kênh, 3 đơn", ["5", "7", "10", "3"], "G1: số đếm viết tay"),
	("5 km, 2 kg, 10 KPI, 5 KH lớn", ["5", "2", "10"], "G1: số trước chữ / mã viết hoa đứng riêng"),
	("5 chục khách", ["5"], "G1: '5 chục'"),
	("12 ; tỷ, 3 • tỷ, 12 / tỷ, 12 | tỷ, 12‐tỷ, 12<!-- -->tỷ", ["12 ; tỷ", "3 • tỷ", "12 / tỷ", "12 | tỷ", "12‐tỷ",
		"12 tỷ"], "W1: mọi dấu chen giữa số và đơn vị"),
	("ước còn 5 tỏi, khoảng XII tỷ, XXXV phần trăm", ["5", "XII", "XXXV"], "W2: tiếng lóng 'tỏi' (G1 bắt chữ số), số La Mã + đơn vị"),
	("năm tỏi, hai ; tỷ, ba • triệu, chín mươi chín %", ["năm tỏi", "hai ; tỷ", "ba • triệu", "chín mươi chín %"],
		"W1/W2: từ chỉ số + dấu chen giữa / tiếng lóng + đơn vị"),
	("đ350000000, x1250, 10^9, 1 2 5 0 đơn", ["350000000", "1250", "10^9", "1 2 5 0"], "G1: các dạng viết khác"),
	("١٢ khách, quý ٤, trong ٧ ngày", ["١٢", "٤", "٧"], "G1: chữ số hệ khác (kể cả ≤ 2 chữ số, kể cả ở chỗ được phép) không "
		"bao giờ được phép"),
	("mã abc2026, x2026, 2026x", ["2026"], "G1: năm dính chữ thường không còn là năm"),
	("mục Ab12, Top5 khách", ["12", "5"], "G1: mã cần ≥ 2 chữ HOA hoặc chữ HOA đứng liền trước chữ số"),
]
for text, want, nhan in BAT:
	eq(f"bắt — {nhan}: {text!r}", render.lint(text), want)

print("\n— lint: PHẢI GIỮ (ngoại lệ của đặc tả + chữ dễ nhầm đơn vị) —")
GIU = [
	("Phòng Kế toán thu hồi công nợ trong 7 ngày.", "thời hạn trong khuyến nghị (đặc tả §9.3)"),
	("Rà soát trong 30 ngày tới, nhóm quá hạn trên 90 ngày", "số ngày ≤ 2 chữ số"),
	("Kế hoạch năm 2026 và mùa Tết 2027", "năm 20xx"),
	("giai đoạn 2025-2026", "khoảng năm"),
	("chốt ngày 5/11/2026", "ngày d/m/yyyy (H4: d/m phải kèm năm)"),
	("tăng ca từ 6/11/2026, giảm tải sau 7/11/2026, còn hạn đến 30/11/2026, khoảng 5/11/2026 sẽ giao", "động từ tăng "
		"giảm nhưng có chữ khác chen trước ngày; 'khoảng d/m/yyyy' là ngày"),
	("hoàn tất trước 05/11/2026", "ngày d/m/yyyy"),
	("kỳ tháng 10/2026 và quý 3/2026", "tháng/năm, quý/năm"),
	("đến 5/11/2026 phải xong, từ 5/11/2026 đến 7/11/2026", "ngày"),
	("ngày 05.11.2026, ngày 5-11-2026, mốc 2026-11-05", "G1: ngày đủ viết bằng dấu chấm / gạch"),
	("chuẩn ISO 22000:2018, HACCP 2020, TCVN 5603:2008, TT 200/2014/TT-BTC", "G1: số hiệu tiêu chuẩn / văn bản"),
	("quý4, tháng10, T10, tuần 2, ngày 5, mùng 3, thứ 2, ca 2, đợt 3, bước 1, kỳ 2, Tết 2027, lần thứ 3",
		"G1: thứ tự sau từ chỉ thời gian"),
	("trong 2 tuần, 3 tháng, 24 giờ, 15 phút, 2 hôm, 2 năm, 1 quý", "G1: thời hạn trước từ chỉ thời gian"),
	("2025-26 và 2026/27", "G1: cặp năm"),
	("Quý IV, QĐ II, mục III", "số La Mã không kèm đơn vị"),
	("giao được ngày 5/11/2026", "có chữ 'ngày' chen giữa nên không phải 'được a/b'"),
	("mốc 5/11/2026 tổng kết quý, mốc 7/11/2026 tổng hợp số", "'tổng kết', 'tổng hợp' sau ngày đủ"),
	("ngày 2/3/2026 số đơn tăng", "'a/b/yyyy số …' → ngày"),
	("từ 2/3/2026 tỷ lệ trả hàng tăng, 5/11/2026 đã giao, 7/11/2026 khách nhận", "ngày + 'tỷ lệ' / 'đã' / 'khách': không "
		"phải đơn vị"),
	("5/11/2026 số liệu được chốt, đến 5/11/2026 tổng hợp", "'số liệu', 'tổng hợp' sau ngày"),
	("năm tài chính 2026/2027, niên độ 2026/27", "năm/năm"),
	("kỳ Q3/2026 và T10/2026 (05/11/2026), từ 5/11/2026-10/11/2026", "mã kỳ, ngày trong ngoặc, khoảng ngày đủ"),
	("xử lý chậm nhất trong 48 giờ", "số giờ ≤ 2 chữ số"),
	("quý 3 tỷ giá tăng", "'tỷ giá'"),
	("quý 3, tuần 45, ca 2, lần thứ 2, thứ 2", "số thứ tự"),
	("mã SR900 bán chậm", "mã có chữ đứng liền trước (đặc tả)"),
	("phiếu KK-2026-002 và ACC-SINV-2026-00012", "số trong mã chứng từ viết hoa nối bằng gạch"),
	("phiếu ACC-SINV-PINV-STE-MAT-HGC-KK-2026-00012", "mã dài 39 ký tự vẫn là mã"),
	("kho HGC/2026/001", "mã nối bằng dấu /"),
	("kỳ T10, Q4, đợt N1", "mã ngắn"),
	("trong 5 ngày khách, 7 ngày trường hợp, đợt 3", "k / tr / đ là đầu một TỪ, không phải đơn vị"),
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
	("vài chục đơn", "'chục' không kèm đơn vị lớn: như số < 100 viết bằng số"),
	("phiếu KK_2026_002", "mã nối bằng gạch dưới"),
	("DSO 62 ngày", "GIỚI HẠN đã biết (G4): dạng được phép (≤ 2 chữ số trước 'ngày') lọt dù ở đây là số liệu — lint "
		"không biết thật / giả; đề bài (bc.ai.prompt) phải răn"),
	("chín mươi chín hoá đơn", "GIỚI HẠN đã biết (G4): số bằng chữ không kèm đơn vị, không sát placeholder"),
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
	("rất nhiều số nhỏ", "1 " * 20000, ["1 " * 19999 + "1"]),     # D7: dãy số rời cách dấu cách là MỘT số trần
	("rất nhiều ngày", "5/11/2026 " * 4000, []),
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
# D3: tên nằm GIỮA câu (đứng riêng thành từ) cũng được thay; khác hoa thường thì không
eq("chuỗi CHỨA tên đứng riêng thành từ: thay (D3); khác hoa thường: không thay; bằng tên sau khi bỏ khoảng trắng hai "
	"đầu: thay; chuỗi trong list / tuple lồng: thay", che["cong-no"]["ghi_chu"],
	["KH#0002 - chi nhánh Hà Nội", "Giao cho KH#0002", ABC.lower(), "KH#0002", ["lồng", ("KH#0002", 5)]])
eq("khoá dict KHÔNG thay (path phải như nhau trên hai bản), giá trị thì thay", che["cong-no"]["theo_khach"],
	{ABC: {"no": 5}, "CUST-0001": "KH#0001"})
gui = json.dumps({k: v for k, v in che.items()}, ensure_ascii=False, default=str)
c("§9.5: tên / mã khách, NCC không còn trong giá trị gửi mô hình",
	all(json.dumps(x, ensure_ascii=False) not in gui for x in (LAN_ANH, "CUST-0002", "SUP-0001", BAO_BI))
	and gui.count(ABC) == 1, gui[:300])      # ABC còn đúng 1 lần: khoá dict (D3: chuỗi con đứng riêng cũng bị thay)
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
# D4: mã chỉ hoàn nguyên được SAU khi đã gửi (mask phát ra) → mask trước, unmask sau
eq("thiếu tên hiển thị → dùng chuỗi của đối tác; chuỗi rỗng / None / không phải chuỗi bỏ qua",
	(M2.mask(["S-2", "", None, 7]), M2.unmask("NCC#0002")), (["NCC#0002", "", None, 7], "S-2"))
M2.mask(["X-1", "X-2"])
eq("mã tự đặt (không theo dạng XX#số): vẫn hoàn nguyên, mã dài không bị mã ngắn ăn mất",
	(M2.unmask("ĐT-A và ĐT-A-B."), M2.strip("ĐT-A-B,ĐT-A")), ("Mã Tự Đặt và Mã Tự Đặt Dài.", " , "))
eq("mã tự đặt dính chữ phía trước / sau: không phải mã", M2.unmask("ĐT-AX, XĐT-A, ĐT-A1"), "ĐT-AX, XĐT-A, ĐT-A1")

# ══ 6. render_insight ═════════════════════════════════════════════════════════
print("\n— render_insight: lời mô hình (đặc tả §5.3 bước 1–4, §9.3, §9.5; hợp đồng §1 mục 9) —")
RAW = {
	"title": f"KH#0001 quá hạn {{{{{R}.top_overdue[0].overdue|tien}}}}",
	"body": (f"Nợ quá hạn chiếm {{{{{R}.kpis.overdue_pct|pct}}}} phải thu (quá hạn {{{{{R}.kpis.overdue|tien}}}}, tổng "
		f"nợ {{{{{R}.kpis.total|tien}}}}). KH#0001 và {{{{{R}.top_overdue[1].customer_name|chu}}}} quá hạn lâu nhất, từ "
		f"{{{{{R}.top_overdue[0].oldest|ngay}}}}. Cần kiểm tra: lịch thanh toán với NCC#0001."),
	"advice": ["Phòng Kế toán đối chiếu và thu hồi trong 7 ngày.", "   ",
		"- Phòng Kinh doanh tạm dừng bán chịu cho KH#0001 trước 30/11/2026.",
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
	f"Nợ quá hạn chiếm 35,3% phải thu (quá hạn 33 triệu, tổng nợ 1,6 tỷ). {LAN_ANH} và {ABC} quá hạn lâu nhất, từ 8/7/2026. "
	f"Cần kiểm tra: lịch thanh toán với {BAO_BI}.")
eq("khuyến nghị: bỏ dòng rỗng, bỏ gạch / số đầu dòng, gộp một dòng, tối đa 3; 'trong 7 ngày', '30/11/2026', 'quý 4' giữ",
	r["advice"], ["Phòng Kế toán đối chiếu và thu hồi trong 7 ngày.",
	f"Phòng Kinh doanh tạm dừng bán chịu cho {LAN_ANH} trước 30/11/2026.", "Ban giám đốc duyệt hạn mức mới trong quý 4."])
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
r = ri(body=f"Phải thu cuối quý 4, top 5 {{{{{R}.top_overdue[0].customer_name|chu}}}}.")
c("G1/G2: 'top 5' viết tay, chữ số sát placeholder chu (mọi kiểu) → loại", r["ok"] is False
	and "so-tran:5" in r["errors"] and f"so-tran:5 {{{{{R}.top_overdue[0].customer_name|chu}}}}" in r["errors"], str(r["errors"]))
r = ri(body=f"Phải thu cuối quý 4, đứng đầu là {{{{{R}.top_overdue[0].customer_name|chu}}}}.")
eq("G2: chữ thường trước placeholder chu → nhận", (r["ok"], r["body"]),
	(True, f"Phải thu cuối quý 4, đứng đầu là {LAN_ANH}."))
# D7: số rời + dấu cách trước placeholder số bị loại với MỌI kiểu số ("quý 3 1,6 tỷ" đọc như "31,6 tỷ")
r = ri(body=f"Phải thu cuối quý 3 {{{{{R}.kpis.total|tien}}}}.")
c("D7: chữ số + dấu cách + placeholder tien → loại", r["ok"] is False
	and f"so-tran:3 {{{{{R}.kpis.total|tien}}}}" in r["errors"], str(r["errors"]))
# over_limit = 3. Ngày (11 đứng sau "/"), năm (4 chữ số), mã (900 dính chữ), giờ (30 đứng sau ":") KHÔNG phải đầu nhóm nghìn
r = ri(body=f"Đến 5/11/2026 {{{{{R}.kpis.over_limit|so}}}} khách vượt hạn mức; năm 2026 {{{{{R}.kpis.over_limit|so}}}} khách; "
	f"mã SR900 {{{{{R}.kpis.over_limit|so}}}} phiếu; lúc 5:30 {{{{{R}.kpis.over_limit|so}}}} đơn.")
c("G2: ngày / năm / mã đứng SÁT trước placeholder → loại (trước placeholder chỉ được chữ thường hoặc ( , : ; )",
	r["ok"] is False and all(f"so-tran:{x} {{{{{R}.kpis.over_limit|so}}}}" in r["errors"] for x in ("5/11/2026", "2026", "SR900",
	"5:30")),
	str(r["errors"]))
r = ri(body=f"Đến 5/11/2026, có {{{{{R}.kpis.over_limit|so}}}} khách vượt hạn mức; năm 2026 có {{{{{R}.kpis.over_limit|so}}}} "
	f"khách; mã SR900 còn {{{{{R}.kpis.over_limit|so}}}} phiếu.")
eq("G2: ngày / năm / mã rồi một từ (hoặc dấu phẩy + từ) trước placeholder → nhận", (r["ok"], r["errors"], r["body"]),
	(True, [], "Đến 5/11/2026, có 3 khách vượt hạn mức; năm 2026 có 3 khách; mã SR900 còn 3 phiếu."))
# Hai số THẬT đặt cạnh nhau có dấu phân cách rõ ("3/5"), chu dính so, so cách tien: không tạo ra con số nào mới
r = ri(body=f"{{{{{R}.kpis.over_limit|so}}}}/{{{{{R}.kpis.qua_120|so}}}} khách đã trả; "
	f"{{{{{R}.top_overdue[1].customer_name|chu}}}}{{{{{R}.kpis.over_limit|so}}}} đơn trễ.")
c("G2: '{{a|so}}/{{b|so}}' và chu dính so → loại (giữa hai placeholder phải có một từ)", r["ok"] is False
	and f"so-tran:{{{{{R}.kpis.over_limit|so}}}}/{{{{{R}.kpis.qua_120|so}}}}" in r["errors"]
	and f"so-tran:{{{{{R}.top_overdue[1].customer_name|chu}}}}{{{{{R}.kpis.over_limit|so}}}}" in r["errors"], str(r["errors"]))
# D7: hai placeholder số cách nhau bởi khoảng trắng bất kỳ (kể cả so + tien) bị loại
r = ri(body=f"Nhóm {{{{{R}.kpis.over_limit|so}}}} {{{{{R}.kpis.overdue|tien}}}}.")
c("D7: so cách tien một dấu cách → loại", r["ok"] is False
	and f"so-tran:{{{{{R}.kpis.over_limit|so}}}} {{{{{R}.kpis.overdue|tien}}}}" in r["errors"], str(r["errors"]))
r = ri(body=f"Nợ của KH#0001,{{{{{R}.top_overdue[0].overdue|tien}}}} đã quá hạn; KH#0002 {{{{{R}.kpis.over_limit|so}}}} đơn trễ.")
c("G2: mã giả HỢP LỆ đứng sát placeholder → loại (mã không phải chữ; tên thật có thể tận cùng bằng chữ số)",
	r["ok"] is False and any(e.startswith("so-tran:KH#…") for e in r["errors"]), str(r["errors"]))
r = ri(body=f"Nợ của KH#0001 là {{{{{R}.top_overdue[0].overdue|tien}}}}, đã quá hạn; KH#0002 có {{{{{R}.kpis.over_limit|so}}}} "
	"đơn trễ.")
eq("G2: mã giả + một từ trước placeholder → nhận, mã thành tên thật", (r["ok"], r["body"]),
	(True, f"Nợ của {LAN_ANH} là 251 triệu, đã quá hạn; {ABC} có 3 đơn trễ."))
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
# N11 / D7: tiêu đề của MÔ HÌNH dài quá 200 ký tự sau khi thay số → lỗi "dai" (không cắt rồi nhận); vẫn trả bản cắt
eq("tiêu đề mô hình dài → lỗi 'dai' (không ok); bản trả về cắt ở khoảng trắng ≤ 200 ký tự, kết bằng …",
	(len(r["title"]) <= 200, r["title"][:16], r["title"][-1], r["title"][-2] != " ", r["ok"], "dai" in r["errors"]),
	(True, "Nợ quá hạn tăng ", "…", True, False, True))
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
MK.mask("C-1")          # D4: mã đã gửi mới hoàn nguyên được
r = render.render_insight({"title": "KH#0001 quá hạn", "body": f"{{{{{R}.kpis.rong|chu}}}} Cần thu hồi sớm.",
	"advice": ["Phòng Kế toán làm việc với KH#0001."]}, PACK, NHOM, MK)
# E3: placeholder chu ra chuỗi rỗng → lỗi "chu-rong" (ok False); lời vẫn dựng như cũ
eq("khoảng trắng do tên thật / giá trị rỗng mang vào: tiêu đề + khuyến nghị gộp một dấu cách, thân bỏ đầu cuối; "
	"chu rỗng → lỗi chu-rong (E3)", (r["ok"], r["errors"], r["title"], r["body"], r["advice"]),
	(False, [f"chu-rong:{R}.kpis.rong"], "Đại lý Hai Cách quá hạn", "Cần thu hồi sớm.",
	["Phòng Kế toán làm việc với Đại lý Hai Cách."]))
r = ri(body=f"Chủ {{{{{R}.top_overdue[1].customer_name|chu}}}} tỷ phú, đến {{{{{R}.as_of|ngay}}}} không rõ.")
eq("G2: 'tỷ phú' (từ ghép) sau placeholder chu không phải đơn vị", (r["ok"], r["errors"]), (True, []))
r = ri(body=f"Chủ {{{{{R}.top_overdue[1].customer_name|chu}}}} tỷ, đến {{{{{R}.as_of|ngay}}}} k rõ.")
c("G2: đơn vị sau placeholder chu / ngay cũng bị loại (G2 xét MỌI kiểu)", r["ok"] is False
	and f"so-tran:{{{{{R}.top_overdue[1].customer_name|chu}}}} tỷ" in r["errors"]
	and f"so-tran:{{{{{R}.as_of|ngay}}}} k" in r["errors"], str(r["errors"]))
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

# ══ 7c. Vòng sửa sau soát chéo: D4 (mã đã gửi), D7 (lint), D8 (kiểu số) ═══════
print("\n— D8 (N2): placeholder số phải đúng kiểu thật của giá trị (kinds) —")
PK = copy.deepcopy(PACK)
PK["cong-no"]["receivables"]["kpis"]["he_so"] = 1.5          # tên khoá không đoán được → không xét


def rk(body, kinds, title="Công nợ", mask=None, pack=None):
	"""render_insight với kinds; bản trước sửa không có tham số kinds → coi như nhận (ok, không lỗi)."""
	try:
		return render.render_insight({"title": title, "body": body, "advice": []}, pack or PK, NHOM, mask, kinds=kinds)
	except TypeError:
		return {"ok": True, "errors": [], "title": title, "body": body, "advice": []}


KIEU_SAI = [
	(f"Khách vượt hạn mức chiếm {{{{{R}.kpis.over_limit|pct}}}} tổng khách.", f"kieu:{R}.kpis.over_limit",
		"số đếm (over_limit) viết thành %"),
	(f"Có {{{{{R}.kpis.overdue_pct|so}}}} khách quá hạn.", f"kieu:{R}.kpis.overdue_pct", "% (overdue_pct) viết thành số đếm"),
	(f"Nợ vượt hạn mức {{{{{R}.kpis.over_limit|tien}}}}.", f"kieu:{R}.kpis.over_limit", "số đếm viết thành tiền"),
	(f"Có {{{{{R}.kpis.total|so}}}} khách.", f"kieu:{R}.kpis.total", "tiền (total) viết thành số đếm"),
	(f"Tỷ lệ nợ {{{{{R}.kpis.dso|pct}}}}.", f"kieu:{R}.kpis.dso", "số ngày (dso) viết thành %"),
	(f"Khách lớn nhất nợ {{{{{R}.top_overdue[0].overdue|so}}}}.", f"kieu:{R}.top_overdue[0].overdue",
		"path có chỉ số: xét theo tên khoá sau khi bỏ chỉ số"),
	(f"Hoá đơn mua quá hạn chiếm {{{{phai-tra.payables.ap.due.overdue_count|pct}}}}.",
		"kieu:phai-tra.payables.ap.due.overdue_count", "*_count viết thành %"),
]
for body, want, nhan in KIEU_SAI:
	r = rk(body, {})
	c(f"D8: loại — {nhan} → {want}", r["ok"] is False and want in r["errors"], f"{r['ok']} {r['errors']}")
r = rk(f"Nhóm tuổi nợ vừa {{{{{R}.aging.31_60|so}}}}.", {f"{R}.aging.31_60": "tien"})
c("D8: path có trong kinds (kind_map) → phải đúng kiểu đó", r["ok"] is False and f"kieu:{R}.aging.31_60" in r["errors"],
	str(r["errors"]))
r = rk(f"Khách lớn nhất nợ {{{{{R}.top_overdue[0].overdue|so}}}}.", {f"{R}.top_overdue.overdue": "so"})
eq("D8: kinds thắng tên khoá (path đã bỏ chỉ số)", (r["ok"], r["errors"]), (True, []))
r = rk(f"Hệ số {{{{{R}.kpis.he_so|so}}}}, nhóm tuổi nợ vừa {{{{{R}.aging.31_60|tien}}}}.", {})
eq("D8/E2: khoá không đoán được tên → tien / so đều nhận", (r["ok"], r["errors"]), (True, []))
r = rk(f"Hệ số chiếm {{{{{R}.kpis.he_so|pct}}}}.", {})
eq("E2: khoá không đoán được tên → pct bị loại (tỷ lệ chỉ nhận trên khoá trông như tỷ lệ)", (r["ok"], r["errors"]),
	(False, [f"kieu:{R}.kpis.he_so"]))
r = rk(f"Nợ quá hạn {{{{{R}.kpis.overdue|tien}}}}, chiếm {{{{{R}.kpis.overdue_pct|pct}}}}; có {{{{{R}.kpis.over_limit|so}}}} khách "
	f"vượt hạn mức, DSO {{{{{R}.kpis.dso|so}}}} ngày.", {})
eq("D8: đúng kiểu → nhận", (r["ok"], r["errors"]), (True, []))
r = render.render_insight({"title": "Công nợ", "body": f"Chiếm {{{{{R}.kpis.over_limit|pct}}}}.", "advice": []}, PK, NHOM, None)
eq("D8: kinds=None (mặc định) giữ như cũ — không xét kiểu", (r["ok"], r["errors"]), (True, []))
f = render.fill(f"{{{{{R}.kpis.over_limit|pct}}}}", PK, NHOM) if True else None
eq("D8: fill(kinds=None) không xét kiểu", f.errors, [])
try:
	f = render.fill(f"{{{{{R}.kpis.over_limit|pct}}}}", PK, NHOM, kinds={})
	got = f.errors
except TypeError:
	got = "không có tham số kinds"
eq("D8: fill(kinds={}) xét theo tên khoá", got, [f"kieu:{R}.kpis.over_limit"])
# Tên lá của GÓI SỐ THẬT (seed_ui2 qua collect.build + detector + _ai) → kiểu (mẫu đại diện; đủ danh sách trong báo cáo)
LA_THAT = {
	"cong-no.receivables.kpis.overdue": "tien", "cong-no.receivables.kpis.overdue_pct": "pct",
	"cong-no.receivables.kpis.overdue_customers": "so", "cong-no.receivables.kpis.over_limit": "so",
	"cong-no.receivables.kpis.dso.dso": "so", "cong-no.receivables.kpis.dso.window_days": "so",
	"cong-no.receivables.kpis.unallocated": "tien", "cong-no.receivables.mt.buckets.b2": "tien",
	"cong-no.receivables.top_overdue.max_days": "so", "cong-no.receivables.mt.invoice_count": "so",
	"phai-tra.payables.ap.due.overdue_count": "so", "phai-tra.payables.ap.due.rows.days_to_due": "so",
	"phai-tra.payables.cash.total": "tien", "tong-quan.summary.meta.growth.sales": "pct",
	"tong-quan.summary.rows.return_rate": "pct", "tong-quan.summary.rows.sales": "tien",
	"san-pham.top_products.rows.growth_pct": "pct", "san-pham.top_products.rows.qty": "so",
	"han-dung.overview.am.no_rate_rows": "so", "han-dung.overview.han.tong.qty_no_rate": "so",
	"ton-kho.overview.health.stranded_value_rows": "so", "ton-kho.overview.health.stranded_value": "tien",
	"ton-kho.overview.value.totals.items_in_stock": "so", "ton-kho.overview.value.totals.value_sellable": "tien",
	"ton-kho.trend.nxt.months.groups.tet.flows.mua": "tien", "van-chuyen.overview.giao.total": "so",
	"van-chuyen.overview.giao.ty_le_giao": "pct", "van-chuyen.overview.cuoc.tra_chuyen_huy_tien": "tien",
	"van-chuyen.overview.cuoc.moi_chuyen": "tien", "van-chuyen.overview.chuyen.chuyen_moi_ngay": "so",
	"van-chuyen.overview.su_co.mo_qua_n": "so", "kiem-ke.overview.kho.tong.qua_90": "so",
	"kiem-ke.overview.kk_sx.gt_thieu": "tien", "nhan-su.overview.luong.bo_phan.thuc_nhan": "tien",
	"nhan-su.overview.bhxh.ty_le": "pct", "he-thong.dia_day.pct": "pct", "he-thong.hang_doi.so_hang": "so",
	# E2: lá vận chuyển / nhân sự / hệ thống trước đây không xếp được
	"he-thong.error_log.tong": "so", "van-chuyen.overview.cuoc.tong": "tien", "attp.overview.dem.do": "so",
	"ngay.daily.meta.year": "so", "van-chuyen.overview.cuoc.tra_bat_thuong": "so",
	"van-chuyen.overview.xe.chi_phi_nam.tong": "tien", "van-chuyen.overview_truoc.cuoc.tong": "tien",
	"van-chuyen.overview.chuyen.tai_tb": "pct", "van-chuyen.overview_truoc.chuyen.tai_tb": "pct",
	"van-chuyen.overview.giao.cho": "so", "van-chuyen.overview.xe.dang_dung": "so", "nhan-su.overview.bhxh.dong": "so",
	"nhan-su.overview.bhxh.dang_lam": "so", "van-chuyen.overview.xe.dem.dang_kiem.qua_han": "so",
	"nhan-su.overview.nhan_su.loai.Khoán": "so", "han-dung.overview.am.ds_tong": "so",
	# E2: "rate" trơ trọi là ĐƠN GIÁ (đồng); chỉ "*_rate" là tỷ lệ
	"han-dung.overview.am.ds.rate": "tien", "nhap-tp.overview.nvl_treo.list.rate": "tien",
	"tong-quan.channels.rows.return_rate": "pct",
	# không đoán (để trống): tên không nói rõ
	"nhan-su.overview.bhxh.rui_ro": None,
}
sai = {p: (getattr(render, "kieu_theo_ten", lambda x: "?")(p), k) for p, k in LA_THAT.items()
	if getattr(render, "kieu_theo_ten", lambda x: "?")(p) != k}
eq("D8: tên khoá của lá số thật → đúng kiểu (mẫu đại diện của gói số seed_ui2)", sai, {})
kpi_lech = [(p, k) for p, k, _l in registry.KPIS if getattr(render, "kieu_theo_ten", lambda x: k)(p) not in (None, k)]
eq("D8: luật tên khoá không trái với kiểu khai trong registry.KPIS", kpi_lech, [])

print("\n— D7 (S7, N3): đơn vị / dấu / số dính quanh placeholder số (kể cả chu trông như số) —")
PS = {"san-pham": {"top_products": {"rows": [{"item_code": "12345", "item_name": "Bánh đậu xanh 300g", "boxes": 250,
	"ty_le": "55,6%"}]}}, "tong-quan": {"summary": {"rows": [{"sales": 3.4e9, "invoices": 37}]}}}
P0 = "san-pham.top_products.rows[0]"


def rs(body):
	return render.render_insight({"title": "Tiêu đề", "body": body, "advice": []}, PS, {"san-pham", "tong-quan"},
		redact.Mask())


GHEP_MOI = [
	(f"Doanh số đạt {{{{{P0}.item_code|chu}}}} tỷ.", "chu trông như số + 'tỷ' (S7)"),
	(f"Tỷ lệ trả hàng lên {{{{{P0}.item_code|chu}}}}% so với cùng kỳ.", "chu trông như số + '%' (S7)"),
	(f"Còn {{{{{P0}.item_code|chu}}}}{{{{{P0}.item_code|chu}}}} hộp.", "hai chu trông như số dính nhau (S7)"),
	(f"Đạt {{{{{P0}.ty_le|chu}}}} 5 lượt.", "chu '55,6%' + số rời phía sau"),
	(f"Chiếm {{{{{P0}.boxes|so}}}}% tổng doanh số.", "so + '%'"),
	(f"Thiệt hại {{{{{P0}.boxes|so}}}} đ mỗi ngày.", "so + ' đ'"),
	(f"Thiệt hại {{{{{P0}.boxes|so}}}} đồng.", "so + ' đồng'"),
	(f"Khoảng {{{{{P0}.boxes|so}}}} USD.", "so + ' USD'"),
	(f"Chiếm {{{{{P0}.boxes|so}}}} phần trăm.", "so + 'phần trăm'"),
	(f"Gấp {{{{{P0}.boxes|so}}}} lần quý trước.", "so + 'lần'"),
	(f"Tăng {{{{tong-quan.summary.rows[0].sales|tien}}}} (tỷ).", "tien + '(tỷ)'"),
	(f"Chiếm {{{{{P0}.boxes|so}}}}<b>%</b>.", "so + thẻ HTML + '%'"),
	(f"Chiếm {{{{{P0}.boxes|so}}}}&#37;.", "so + thực thể HTML '%'"),
	(f"Có {{{{{P0}.boxes|so}}}}M khách.", "chữ nhân dính sau ('M')"),
	(f"Có {{{{{P0}.boxes|so}}}}E3 hộp.", "'E3' dính sau"),
	(f"Có {{{{{P0}.boxes|so}}}} 00 hộp.", "nhóm 2 chữ số cách sau"),
	(f"Giảm -{{{{tong-quan.summary.rows[0].sales|tien}}}}.", "dấu '-' trước placeholder"),
	(f"Lệch −{{{{{P0}.boxes|so}}}} hộp.", "dấu trừ '−' trước placeholder"),
	(f"Tăng +{{{{{P0}.boxes|so}}}} hộp.", "dấu '+' trước placeholder"),
	(f"Sai số ±{{{{{P0}.boxes|so}}}} hộp.", "'±' trước placeholder"),
	(f"Gấp ×{{{{{P0}.boxes|so}}}}.", "'×' trước placeholder"),
	(f"Có 1\u200b{{{{{P0}.boxes|so}}}} hộp.", "chữ số + ký tự vô hình + placeholder (dính)"),
	(f"Có {{{{{P0}.boxes|so}}}}\u200b4 hộp.", "placeholder + ký tự vô hình + chữ số (dính)"),
	(f"Có {{{{{P0}.boxes|so}}}}\t{{{{tong-quan.summary.rows[0].invoices|so}}}} hộp.", "hai placeholder cách tab"),
	(f"Có 1\t{{{{{P0}.boxes|so}}}} hộp.", "chữ số + tab + placeholder so"),
	(f"Có 12 {{{{tong-quan.summary.rows[0].sales|tien}}}}.", "số rời + dấu cách + placeholder tien"),
	(f"Từ {{{{{P0}.boxes|so}}}}-{{{{tong-quan.summary.rows[0].invoices|so}}}} hộp.", "G2: hai placeholder nối gạch"),
	(f"Mã KK-{{{{{P0}.boxes|so}}}}.", "G2: gạch dính chữ trước placeholder (kể cả nối mã)"),
	(f"Đến 5/11/2026 {{{{{P0}.boxes|so}}}} hộp.", "G2: ngày đứng sát trước placeholder"),
]
for body, nhan in GHEP_MOI:
	r = rs(body)
	c(f"D7: loại — {nhan}", r["ok"] is False and any(e.startswith("so-tran:") for e in r["errors"]),
		f"{r['ok']} {r['errors']} {r['body']!r}")
GIU_MOI = [
	f"Mã {{{{{P0}.item_name|chu}}}} bán {{{{{P0}.boxes|so}}}} hộp, đạt {{{{{P0}.ty_le|chu}}}} chỉ tiêu.",
	f"Doanh số ({{{{tong-quan.summary.rows[0].sales|tien}}}}) từ {{{{tong-quan.summary.rows[0].invoices|so}}}} hoá đơn.",
	f"Từ {{{{{P0}.boxes|so}}}} đến {{{{tong-quan.summary.rows[0].invoices|so}}}} hộp; mã KK-2026-002.",
	f"Đến 5/11/2026, còn {{{{{P0}.boxes|so}}}} hộp, trong 7 ngày, quý 4.",
]
for body in GIU_MOI:
	r = rs(body)
	c(f"D7: giữ — {body[:60]}…", r["ok"] is True, f"{r['errors']} {r['body']!r}")

print("\n— D7 (N8): lint bắt thêm đơn vị không dấu / tiếng Anh / cách bằng ngoặc, HTML; số có chữ thường đứng trước —")
LINT_MOI = [
	("Nợ quá hạn khoảng 2 ty dong", "2 ty dong"), ("Chiếm 35 phan tram", "35 phan tram"),
	("khoang 35 trieu moi khach", "35 trieu"), ("Còn 4 nghin hộp", "4 nghin"), ("Còn 4 ngan hộp", "4 ngan"),
	("Nợ 5 ti", "5 ti"), ("đạt 35 percent", "35 percent"), ("đạt 35 pct", "35 pct"), ("2 million", "2 million"),
	("3 billion", "3 billion"), ("2 mio", "2 mio"), ("3 bn", "3 bn"), ("tương đương 35M", "35M"), ("hoặc 2B.", "2B"),
	("50K đơn", "50K"), ("Kế toán thu 12 (tỷ) trong 7 ngày", "12 (tỷ"), ("Nợ 12-tỷ", "12-tỷ"),
	("Nợ <b>12</b> tỷ", "12 tỷ"), ("Nợ 12&nbsp;tỷ", "12 tỷ"), ("Chiếm 12&#37;", "12%"),
	("nợ đ350000000", "350000000"), ("Nợ x1250", "1250"), ("Nợ A100", "100"), ("khoảng 10^9", "10^9"),
	("khoảng 4E3 hộp", "4E3"), ("tổng 1 2 5 0 đơn", "1 2 5 0"), ("Chiếm 三十五%", "三十五%"),
	("Có 1\u200b250 khách", "1250"),
]
for text, want in LINT_MOI:
	got = render.lint(text)
	c(f"D7: lint bắt — {text!r} → {want!r}", want in got, str(got))
LINT_GIU = ["năm 2026", "ngày 5/11/2026", "mã SR900", "phiếu KK-2026-002", "trong 7 ngày", "quý 4", "quý 3 ty le",
	"PNTP-X120", "KKE-TP10", "TON-TRAD1", "HAN-SINV-90", "KKE-SR-26", "SE-NL-X8", "TET1", "X12", "LO-TET-01",
	"công ty Ba Tiến", "hàng ty vi", "trong 7 ngày (bảy ngày)", "Bước 1. Gọi khách"]
for text in LINT_GIU:
	c(f"D7: lint giữ — {text!r}", render.lint(text) == [], str(render.lint(text)))
for text, want in (("3 ty le", "3"), ("Top 5 Mart", "5"), ("trong 7 (bảy) ngày", "7"), ("Bước 1.\n2. Gọi khách", "2"),
		("5 khách, 12 đơn", "12")):
	c(f"G1: lint bắt (trước đây lọt) — {text!r} → {want!r}", want in render.lint(text), str(render.lint(text)))
t0 = time.monotonic()
dai = ("Nợ quá hạn của nhóm khách trong 12 ngày, mã SR900, ngày 5/11/2026, công ty ABC tăng. " * 1100)[:80000]
got = render.lint(dai)
dt = time.monotonic() - t0
c(f"D7: lint 80.000 ký tự lời thường < 5 s ({dt:.2f} s), sạch", dt < 5 and got == [], f"{dt:.2f} s {got[:3]}")
t0 = time.monotonic()
got = render.lint(("Nợ 2 ty dong, 35M, x1250, 1 2 5 0 đơn; " * 3000)[:80000])
dt = time.monotonic() - t0
c(f"D7: lint 80.000 ký tự đầy số trần < 5 s ({dt:.2f} s)", dt < 5 and len(got) >= 4, f"{dt:.2f} s {got[:4]}")
t0 = time.monotonic()
r = rs((f"Có {{{{{P0}.boxes|so}}}} hộp và {{{{{P0}.item_name|chu}}}} " * 1000)[:80000])
dt = time.monotonic() - t0
c(f"D7: render_insight thân 80.000 ký tự nhiều placeholder < 5 s ({dt:.2f} s)", dt < 5, f"{dt:.2f} s")

print("\n— N11: tiêu đề quá dài —")
r = rk("Cần thu hồi sớm.", None, title="Nợ " + "rất " * 46 + f"lớn, tổng {{{{{R}.kpis.unallocated|so}}}} đồng chưa phân bổ hết")
c("N11: tiêu đề MÔ HÌNH dài quá 200 ký tự sau khi thay số → lỗi 'dai' (không cắt rồi nhận)",
	r["ok"] is False and "dai" in r["errors"], f"{r['ok']} {r['errors']}")
rr = render.render_rule("A " * 95 + f"tổng {{{{{R}.kpis.total|so}}}} đồng chưa thu", "Chi tiết.", PK)
c("N11: tiêu đề QUY TẮC vẫn cắt (ok), nhưng không bao giờ giữa một con số", rr["ok"] and len(rr["title"]) <= 200
	and rr["title"].endswith("…") and not any(ch.isdigit() for ch in rr["title"]), repr(rr["title"][-30:]))
rr = render.render_rule("B" * 196 + "1.600.000 đồng", "Chi tiết.", PK)
c("N11: không có khoảng trắng nào → lùi qua chữ số ở cuối", rr["title"] == "B" * 196 + "…", repr(rr["title"][-12:]))
# "1,6" kết thúc ở ký tự 197, cắt ở ký tự 199 rơi giữa "tỷ" → bỏ cả "1,6" (không để "1,6…" mất đơn vị)
rr = render.render_rule("Nợ " + "x" * 185 + " tổng 1,6 tỷ đồng chưa thu", "Ct.", PK)
eq("N11: số đứng ngay trước chỗ cắt bị bỏ cùng đơn vị (không còn '1,6…' / '1,6 t…')", rr["title"],
	"Nợ " + "x" * 185 + " tổng…")

print("\n— D4 (S4): chỉ mã ĐÃ GỬI mới thành tên thật; mã khác bị lint bắt —")
M4 = redact.Mask([("KH#0001", LAN_ANH, {"CUST-0001", LAN_ANH}), ("KH#0002", ABC, {"CUST-0002", ABC}),
	("NCC#0001", BAO_BI, {"SUP-0001", BAO_BI})])
getattr(M4, "begin", lambda: None)()
gui4 = M4.mask({"top": [{"customer": "CUST-0001"}]})
r = render.render_insight({"title": "KH#0001 quá hạn", "body": "KH#0002 và NCC#0001 cũng cần lưu ý.", "advice": []},
	PACK, NHOM, M4)
c("D4: mã có trong bảng nhưng KHÔNG gửi trong đề bài này → bị loại (không hoàn nguyên thành tên người khác)",
	r["ok"] is False and "so-tran:KH#0002" in r["errors"] and "so-tran:NCC#0001" in r["errors"]
	and ABC not in r["body"] and BAO_BI not in r["body"], f"{r['errors']} {r['body']!r}")
r = render.render_insight({"title": "KH#0001 quá hạn", "body": "Cần thu hồi sớm.", "advice": []}, PACK, NHOM, M4)
eq("D4: mã đã gửi → tên thật", (r["ok"], r["title"]), (True, f"{LAN_ANH} quá hạn"))
getattr(M4, "begin", lambda: None)()
r = render.render_insight({"title": "KH#0001 quá hạn", "body": "Cần thu hồi sớm.", "advice": []}, PACK, NHOM, M4)
c("D4: begin() quên mã của đề bài trước → mã cũ thành mã lạ", r["ok"] is False and "so-tran:KH#0001" in r["errors"],
	f"{r['errors']}")
M5 = redact.Mask([("KH#0001", LAN_ANH, {"CUST-0001"})])
eq("D4: Mask chưa begin(), chưa phát mã nào → unmask / strip không đổi mã", (M5.unmask("KH#0001"), M5.strip("KH#0001")),
	("KH#0001", "KH#0001"))
M5.mask_text("gọi CUST-0001")
eq("D4: mã phát ra qua mask_text cũng tính là đã gửi", M5.unmask("KH#0001 nợ"), f"{LAN_ANH} nợ")

# ══ 7d. Vòng sửa 2: E1 (ngoặc nhọn), E2 (kiểu theo tên khoá), E3 (quanh placeholder), E4 (tốc độ), E5 ══════
print("\n— E1: lint KHÔNG bỏ qua chữ trong ngoặc nhọn (chỉ bỏ dấu ngoặc / thẻ trơn) —")
for text, want in (("Nợ quá hạn <khoảng 350 triệu> cần thu gấp.", "350 triệu"),
		("Doanh số đạt <b 1.250.000 đ> trong tháng.", "1.250.000 đ"), ("Tỷ lệ &lt;x 35%&gt; so với cùng kỳ.", "35%"),
		("Tỷ lệ trả hàng <uoc 35%> so với cùng kỳ.", "35%"), ("Có <x 1250> khách mới.", "1250"),
		("Nợ <b>12</b> tỷ", "12 tỷ"), ("Nợ <span class=\"a\">12</span> tỷ", "12 tỷ"), ("Nợ 12 <tr>", "12 tr"),
		("Nợ ＜khoảng 350 triệu＞", "350 triệu"), ("Nợ <it nhat 100 triệu> trong 7 ngày", "100 triệu")):
	got = render.lint(text)
	c(f"E1: lint bắt — {text!r} → {want!r}", want in got, str(got))
for text in ("Nợ quá hạn <b>tăng</b> trong 7 ngày", "Tỷ lệ < ngưỡng, mã <SR900>", "<i>quý 4</i>"):
	c(f"E1: lint giữ — {text!r}", render.lint(text) == [], str(render.lint(text)))
r = rs(f"Bình quân {{{{{P0}.boxes|so}}}} hộp; riêng nhóm khách lớn nợ <khoảng 350 triệu> và chiếm <uoc 70%> tổng nợ.")
c("E1: render_insight loại lời có số viết tay trong ngoặc nhọn", r["ok"] is False and "so-tran:350 triệu" in r["errors"]
	and "so-tran:70%" in r["errors"], f"{r['ok']} {r['errors']}")
r = rs(f"Chiếm {{{{{P0}.boxes|so}}}} <tr> mỗi tháng.")
c("E1: đơn vị trong ngoặc nhọn ngay sau placeholder → loại", r["ok"] is False, f"{r['ok']} {r['errors']}")

print("\n— E2: kiểu theo tên khoá — 'rate' là đơn giá, khoá không xếp được thì cấm pct —")
PR = {"han-dung": {"overview": {"am": {"ds": [{"item_code": "HAN-NL", "qty": -5.0, "rate": 30000.0,
	"value_abs": 150000.0}]}}}, "nhap-tp": {"overview": {"nvl_treo": {"list": [{"rate": 50000.0}]}}},
	"tong-quan": {"summary": {"rows": [{"return_rate": 1.1}]}},
	"attp": {"report": {"bang": [{"ma": "ty_le_luot", "don_vi": "%", "thang": {"2026-09": 87.5}, "ky": 87.5},
		{"ma": "su_co", "don_vi": "phiếu", "thang": {"2026-09": 3}, "ky": 3}]}}}
SR = {"han-dung", "nhap-tp", "tong-quan", "attp"}


def re2(body):
	return render.render_insight({"title": "Kho", "body": body, "advice": []}, PR, SR, None, kinds={})


for path, dung, sai in (("han-dung.overview.am.ds[0].rate", "tien", ("pct", "so")),
		("nhap-tp.overview.nvl_treo.list[0].rate", "tien", ("pct", "so")),
		("tong-quan.summary.rows[0].return_rate", "pct", ("tien", "so")),
		("attp.report.bang[0].thang.2026-09", "pct", ("tien", "so")), ("attp.report.bang[1].ky", "so", ("pct", "tien"))):
	r = re2(f"Mục này ở mức {{{{{path}|{dung}}}}} theo sổ.")
	c(f"E2: {path} |{dung} → nhận", r["ok"] is True, f"{r['errors']} {r['body']!r}")
	for k in sai:
		r = re2(f"Mục này ở mức {{{{{path}|{k}}}}} theo sổ.")
		c(f"E2: {path} |{k} → loại (kieu)", r["ok"] is False and f"kieu:{path}" in r["errors"], f"{r['ok']} {r['errors']}")
eq("E2: kieu_theo_ten — 'rate' → tien, '*_rate' → pct", [render.kieu_theo_ten(x) for x in (
	"han-dung.overview.am.ds.rate", "tong-quan.summary.rows.return_rate", "x.y.qty_no_rate")], ["tien", "pct", "so"])

# Gói số THẬT (seed gộp seed_ui2 + seed sổ kho seed_ui_kho): MỌI lá số phải xếp được kiểu (kinds của lượt → đơn vị của
# dòng → tên khoá); mọi lời quy tắc của lượt, chép nguyên làm lời mô hình, phải qua render_insight với kinds (E5).
# Mỗi seed chạy ở tiến trình riêng, DB riêng; kết quả trả qua stdout (gói số không ghi ra tệp).
LA_DE_TRONG = {}        # lá cố ý để trống (không xếp được): hiện không có
# G4: ≥ 60 nhận định ĐÚNG viết theo đề bài (bc.ai.prompt), đủ 7 nhóm, hai seed (g = seed_ui2, k = seed_ui_kho) —
# chỉ có placeholder, không số liệu; §path§ = chép mã giả có ở path đó trong gói đã che của lượt (như mô hình chép).
# (seed, nhóm, tiêu đề, thân, khuyến nghị). Gốc: các câu soạn tay ở những đợt kiểm lại, sửa theo G1 / G2.
DUNG = [
	("g", "kinh-doanh", "Doanh số luỹ kế tăng mạnh so với cùng kỳ",
		"Doanh số luỹ kế đạt {{tong-quan.summary.rows[0].sales|tien}}, tăng {{tong-quan.summary.meta.growth.sales|pct}} so với cùng kỳ năm trước ({{tong-quan.summary.rows[1].sales|tien}}). Mức tăng lớn bất thường, cần kiểm tra: có đơn hàng lớn một lần hay không.",
		["Kinh doanh rà lại các đơn lớn trong kỳ để xác nhận mức tăng là bền vững."]),
	("g", "kinh-doanh", "Doanh thu phụ thuộc nhiều vào kênh NPP",
		"Kênh {{tong-quan.channels.rows[0].channel|chu}} đạt {{tong-quan.channels.rows[0].sales|tien}}, trong tổng doanh số {{tong-quan.summary.rows[0].sales|tien}}, kênh {{tong-quan.channels.rows[1].channel|chu}} đứng sau với {{tong-quan.channels.rows[1].sales|tien}}. Doanh thu dồn vào một kênh thì rủi ro khi kênh đó chững lại.",
		["Kinh doanh lập kế hoạch mở rộng kênh MT và du lịch trong quý 4."]),
	("g", "kinh-doanh", "Khách lớn nhất chiếm phần đáng kể doanh số",
		"Khách §tong-quan.top_customers.rows[0].customer§ mua {{tong-quan.top_customers.rows[0].amount|tien}}, khách đứng thứ hai §tong-quan.top_customers.rows[1].customer§ mua {{tong-quan.top_customers.rows[1].amount|tien}}. Doanh số phụ thuộc vài khách lớn nên mất một khách sẽ ảnh hưởng mạnh.",
		["Kinh doanh lên kế hoạch chăm sóc riêng cho nhóm khách lớn.", "Kinh doanh tìm thêm khách mới để giảm phụ thuộc."]),
	("g", "kinh-doanh", "Doanh số tháng dồn vào những ngày gần đây",
		"Ngày {{ngay.daily.rows[8].date|ngay}} bán {{ngay.daily.rows[8].sales|tien}} với {{ngay.daily.rows[8].orders|so}} đơn, ngày {{ngay.daily.rows[9].date|ngay}} bán {{ngay.daily.rows[9].sales|tien}}; các ngày trước đó thấp hơn nhiều. Cần kiểm tra: đơn dồn cuối tháng hay ghi nhận trễ.",
		["Kế toán kiểm tra ngày ghi nhận của các hoá đơn lớn cuối tháng."]),
	("g", "kinh-doanh", "Hàng trả lại tập trung ở kênh NPP",
		"Kênh {{tong-quan.channels.rows[0].channel|chu}} có {{tong-quan.channels.rows[0].returns|tien}} hàng trả lại, tỷ lệ trả {{tong-quan.channels.rows[0].return_rate|pct}}; toàn công ty trả lại {{tong-quan.summary.rows[0].returns|tien}}. Cần kiểm tra: nguyên nhân trả hàng ngày {{ngay.daily.rows[2].date|ngay}} với {{ngay.daily.rows[2].return_orders|so}} đơn trả.",
		["Kinh doanh làm việc với nhà phân phối về lý do trả hàng.", "Chất lượng kiểm tra lô hàng bị trả."]),
	("g", "kinh-doanh", "Tháng 10 đạt doanh số cao nhất từ đầu năm tài chính",
		"Tháng 10 đạt {{thang.monthly.rows[5].sales|tien}}, cao hơn tháng 9 với {{thang.monthly.rows[4].sales|tien}}; hàng trả lại trong tháng là {{thang.monthly.rows[5].returns|tien}}. Cùng tháng năm trước chỉ đạt {{thang.monthly.rows[17].sales|tien}}.",
		["Kinh doanh giữ nhịp bán hàng cho mùa Tết sắp tới."]),
	("g", "tai-chinh", "Thu tiền bán hàng đang rất chậm",
		"Bình quân {{cong-no.receivables.kpis.dso.dso|so}} ngày mới thu được tiền, khách đang nợ {{cong-no.receivables.kpis.dso.debt|tien}}, doanh thu là {{cong-no.receivables.kpis.dso.revenue|tien}} trong {{cong-no.receivables.kpis.dso.window_days|so}} ngày gần nhất. Vốn bị khách giữ lâu làm thiếu tiền quay vòng.",
		["Kế toán đối chiếu công nợ với từng khách lớn trong 7 ngày.", "Kinh doanh thương lượng lại hạn thanh toán với khách nợ lâu."]),
	("g", "tai-chinh", "Nợ quá hạn chiếm tỷ trọng lớn",
		"Nợ quá hạn {{cong-no.receivables.kpis.overdue|tien}}, bằng {{cong-no.receivables.kpis.overdue_pct|pct}} tổng phải thu {{cong-no.receivables.kpis.receivable|tien}}, ở {{cong-no.receivables.kpis.overdue_customers|so}} khách. Khoản lớn nhất của §cong-no.receivables.top_overdue[0].customer§ là {{cong-no.receivables.top_overdue[0].overdue|tien}}, đã quá hạn {{cong-no.receivables.top_overdue[0].max_days|so}} ngày.",
		["Kế toán gửi đối chiếu công nợ cho các khách quá hạn trong 7 ngày.", "Kinh doanh tạm dừng bán chịu cho khách đã quá hạn trên 60 ngày."]),
	("g", "tai-chinh", "Tiền hàng nhà cung cấp đã quá hạn trả",
		"Còn {{phai-tra.payables.ap.due.overdue_total|tien}} quá hạn ở {{phai-tra.payables.ap.due.overdue_count|so}} hoá đơn mua, lớn nhất là §phai-tra.payables.ap.top[0].supplier§ với {{phai-tra.payables.ap.top[0].outstanding|tien}}, trễ {{phai-tra.payables.ap.top[0].days_overdue|so}} ngày. Quỹ hiện có {{phai-tra.payables.cash.total|tien}} nên đủ khả năng trả.",
		["Kế toán thanh toán khoản quá hạn cho nhà cung cấp trong 3 ngày."]),
	("g", "tai-chinh", "Có khách nợ vượt hạn mức tín dụng",
		"{{cong-no.receivables.kpis.over_limit|so}} khách đang nợ vượt hạn mức, trong khi tổng phải thu ròng là {{cong-no.receivables.kpis.net|tien}}. Bán thêm cho khách này làm tăng rủi ro mất vốn.",
		["Kinh doanh tạm dừng giao hàng cho khách vượt hạn mức đến khi thu được nợ.", "Kế toán trình duyệt lại hạn mức tín dụng."]),
	("g", "tai-chinh", "Công nợ kênh MT còn chờ hoá đơn điện tử",
		"Chuỗi §cong-no.receivables.mt.chains[0].chain§ còn nợ {{cong-no.receivables.mt.chains[0].amount|tien}}, trong đó {{cong-no.receivables.mt.chains[0].overdue|tien}} đã quá hạn và {{cong-no.receivables.mt.chains[0].einv_pending|tien}} chưa xuất hoá đơn điện tử. Chưa có hoá đơn thì chuỗi chưa thanh toán.",
		["Kế toán xuất hoá đơn điện tử cho chuỗi MT trong 5 ngày."]),
	("g", "tai-chinh", "Quỹ tiền đủ trả nợ nhà cung cấp đến hạn",
		"Quỹ hiện có {{phai-tra.payables.cash.total|tien}}, gồm ngân hàng {{phai-tra.payables.cash.bank|tien}} và tiền mặt {{phai-tra.payables.cash.cash|tien}}; phải trả nhà cung cấp tổng {{phai-tra.payables.ap.total|tien}}. Khả năng thanh toán tốt, không cần vay thêm.",
		["Kế toán lập lịch trả nhà cung cấp theo hạn để giữ uy tín."]),
	("g", "van-chuyen", "Đơn chờ giao quá hạn dồn nhiều",
		"{{van-chuyen.overview.giao.cho_qua_han.qua_n|so}} đơn đã chờ giao quá {{van-chuyen.overview.giao.cho_qua_han.so_ngay|so}} ngày, nhiều nhất ở nhóm {{van-chuyen.overview.giao.cho_qua_han.rows[0].hinh_thuc|chu}} với {{van-chuyen.overview.giao.cho_qua_han.rows[0].qua_n|so}} đơn. Tỷ lệ đã phân công mới đạt {{van-chuyen.overview.giao.ty_le_phan_cong|pct}}.",
		["Vận chuyển phân công ngay các đơn chưa có người giao trong 2 ngày."]),
	("g", "van-chuyen", "Xe quá hạn đăng kiểm vẫn đang dùng",
		"Xe {{van-chuyen.overview.xe.can_xu_ly[0].xe|chu}} đã quá hạn {{van-chuyen.overview.xe.can_xu_ly[0].viec[0].viec|chu}} từ {{van-chuyen.overview.xe.can_xu_ly[0].viec[0].han|ngay}}; thêm {{van-chuyen._ai.vc_xe_qua_han.sap_den|so}} xe sắp đến hạn. Xe quá hạn chạy đường sẽ bị phạt và không được bảo hiểm.",
		["Vận chuyển đưa xe đi đăng kiểm trong 3 ngày.", "Vận chuyển lên lịch bảo dưỡng cho xe sắp đến hạn."]),
	("g", "van-chuyen", "Đơn tự giao chưa xếp chuyến",
		"Còn {{van-chuyen.overview.giao.xep.chua_xep|so}} đơn tự giao chưa xếp lên chuyến và {{van-chuyen.overview.giao.xep.mot_phan|so}} đơn mới xếp một phần, trong khi đã xếp {{van-chuyen.overview.giao.xep.da_xep|so}} đơn. Đơn chưa xếp thì chưa có ai đi giao.",
		["Vận chuyển xếp chuyến cho các đơn còn lại trong ngày."]),
	("g", "van-chuyen", "Sự cố vận chuyển tồn lâu chưa xử lý",
		"{{van-chuyen.overview.su_co.mo_qua_n|so}} sự cố đã mở quá {{van-chuyen.overview.su_co.so_ngay|so}} ngày, tổng đang mở {{van-chuyen.overview.su_co.dang_mo|so}} vụ với giá trị ảnh hưởng {{van-chuyen.overview.su_co.gia_tri_anh_huong|tien}}. Bồi thường còn phải đòi {{van-chuyen.overview.su_co.boi_thuong_con_doi|tien}}.",
		["Vận chuyển chốt hướng xử lý từng sự cố trong 7 ngày.", "Kế toán theo dõi khoản bồi thường còn phải thu."]),
	("g", "van-chuyen", "Cước sửa tay cần duyệt lại",
		"Có {{van-chuyen._ai.vc_cuoc_canh_bao_sua_tay.so|so}} chuyến bị sửa cước bằng tay trên tổng {{van-chuyen.overview.cuoc.so_chuyen|so}} chuyến, tổng cước tháng {{van-chuyen.overview.cuoc.tong|tien}}, bằng {{van-chuyen.overview.cuoc.ty_le_doanh_thu|pct}} doanh thu đã giao. Cước ngoài bảng giá dễ phát sinh chi sai.",
		["Vận chuyển giải trình từng chuyến sửa cước.", "Kế toán đối chiếu cước với bảng giá trước khi chi."]),
	("g", "van-chuyen", "Tỷ lệ giao hàng trong tháng còn thấp",
		"Mới giao xong {{van-chuyen.overview.giao.da|so}} đơn, trong tổng số {{van-chuyen.overview.giao.total|so}} đơn, tỷ lệ {{van-chuyen.overview.giao.ty_le_giao|pct}}; còn {{van-chuyen.overview.giao.cho|so}} đơn chờ và {{van-chuyen.overview.giao.dang|so}} đơn đang giao. Giao chậm làm chậm ghi nhận doanh thu và thu tiền.",
		["Vận chuyển tăng chuyến để giải quyết đơn chờ trong tuần này."]),
	("g", "nhan-su", "Nhiều lao động chưa đóng BHXH",
		"{{nhan-su.overview.bhxh.rui_ro|so}} người quá một tháng chưa đóng BHXH mà chưa ghi lý do; hiện có {{nhan-su.overview.bhxh.dong|so}} người đóng, trong số {{nhan-su.overview.bhxh.dang_lam|so}} người đang làm, tỷ lệ {{nhan-su.overview.bhxh.ty_le|pct}}. Công ty có thể bị truy thu và phạt.",
		["Nhân sự đăng ký BHXH hoặc ghi rõ lý do cho từng người trong 7 ngày."]),
	("g", "nhan-su", "Hợp đồng lao động hết hạn chưa ký lại",
		"{{nhan-su.overview.giay_to.hd.do|so}} người đã hết hạn hợp đồng lao động và {{nhan-su.overview.giay_to.hd.vang|so}} người sẽ hết hạn trong {{nhan-su.overview.giay_to.so_ngay|so}} ngày tới. Làm việc không hợp đồng là vi phạm khi thanh tra lao động.",
		["Nhân sự ký lại hợp đồng cho người đã hết hạn trong 5 ngày."]),
	("g", "nhan-su", "Khám sức khỏe định kỳ đã quá hạn",
		"{{nhan-su.overview.giay_to.ksk.do|so}} người hết hạn khám sức khỏe, {{nhan-su.overview.giay_to.ksk.vang|so}} người sắp hết hạn. Với cơ sở thực phẩm, thiếu giấy khám là lỗi bị phạt khi kiểm tra.",
		["Nhân sự đặt lịch khám sức khỏe cho người hết hạn trong 10 ngày."]),
	("g", "nhan-su", "Trùng phiếu lương nháp cần xử lý",
		"Cảnh báo {{nhan-su.overview.canh_bao.rows[1].ten|chu}} đang có {{nhan-su.overview.canh_bao.rows[1].so_nguoi|so}} người; kỳ lương {{nhan-su.overview.luong.ky|chu}} còn {{nhan-su.overview.luong.loi_ky|so}} lỗi kỳ. Trả lương trùng sẽ thất thoát tiền.",
		["Nhân sự xoá phiếu lương trùng trước khi chốt kỳ.", "Kế toán chỉ chi lương sau khi nhân sự xác nhận."]),
	("g", "nhan-su", "Biến động nhân sự trong kỳ",
		"Đang làm {{nhan-su.overview.nhan_su.dang_lam|so}} người, tạm nghỉ {{nhan-su.overview.nhan_su.tam_nghi|so}} người; trong kỳ có {{nhan-su.overview.bien_dong.vao|so}} người vào và {{nhan-su.overview.bien_dong.nghi|so}} người nghỉ. Bộ phận {{nhan-su.overview.nhan_su.by_dept[0].bo_phan|chu}} đông nhất với {{nhan-su.overview.nhan_su.by_dept[0].dang_lam|so}} người.",
		["Nhân sự rà soát kế hoạch tuyển cho mùa cao điểm."]),
	("g", "attp", "Vòng kiểm hằng ngày đang thiếu lượt",
		"Lĩnh vực {{attp.overview.linh_vuc[0].ten|chu}} báo đèn đỏ: còn {{attp._ai.attp_den_do_vong_kiem.viec|so}} việc treo, trong đó {{attp._ai.attp_den_do_vong_kiem.cao|so}} việc mức cao; tỷ lệ lượt đủ mới đạt {{attp.overview.linh_vuc[0].so|chu}}. Bỏ lượt kiểm thì không phát hiện kịp nguy cơ mất an toàn.",
		["Chất lượng bố trí người đi đủ lượt kiểm mỗi ngày sản xuất.", "Sản xuất nhắc tổ trưởng ký xác nhận sau từng lượt."]),
	("g", "attp", "Phiếu sự cố ATTP quá hạn chưa đóng",
		"Lĩnh vực {{attp.overview.linh_vuc[1].ten|chu}} còn {{attp._ai.attp_den_do_su_co.viec|so}} việc treo, cả {{attp._ai.attp_den_do_su_co.cao|so}} việc đều ở mức cao. Hệ thống ghi nhận: {{attp.overview.linh_vuc[1].nhac[0].tieu_de|chu}}. Sự cố không đóng thì không biết lô hàng liên quan đã xử lý chưa.",
		["Chất lượng đóng phiếu sự cố quá hạn trong 3 ngày."]),
	("g", "attp", "Truy xuất, thu hồi còn việc treo",
		"Lĩnh vực {{attp.overview.linh_vuc[5].ten|chu}} còn {{attp._ai.attp_den_do_truy_xuat.viec|so}} việc treo, {{attp._ai.attp_den_do_truy_xuat.cao|so}} việc mức cao. Không truy xuất được lô thì khi có khiếu nại sẽ phải thu hồi rộng.",
		["Chất lượng hoàn tất diễn tập truy xuất còn thiếu trong tháng này."]),
	("g", "attp", "Nhiều lĩnh vực ATTP đang báo đỏ",
		"Trong kỳ {{attp.overview.so_ngay|so}} ngày có {{attp.overview.dem.do|so}} lĩnh vực đèn đỏ, {{attp.overview.dem.vang|so}} đèn vàng và {{attp.overview.dem.xanh|so}} đèn xanh. Số lĩnh vực đỏ nhiều cho thấy hồ sơ ATTP chưa được duy trì đều.",
		["Chất lượng lập kế hoạch xử lý từng lĩnh vực đỏ trong 14 ngày."]),
	("g", "he-thong", "Lỗi hệ thống tăng vọt trong ngày",
		"Ngày qua ghi nhận {{he-thong.error_log.tong|so}} lỗi, bình quân mỗi ngày {{he-thong.error_log.tb_ngay|so}} lỗi. Lỗi tăng thường do một tác vụ hỏng lặp lại.",
		["Quản trị xem Error Log và xử lý nhóm lỗi nhiều nhất trong ngày."]),
	("g", "he-thong", "Có tài khoản bị dò mật khẩu",
		"{{he-thong.dang_nhap_sai.so_tk|so}} tài khoản đăng nhập sai nhiều bất thường, nhiều nhất {{he-thong.dang_nhap_sai.max_lan|so}} lượt trong ngày qua, tổng cộng {{he-thong.dang_nhap_sai.tong|so}} lượt sai. Cần kiểm tra: có người dò mật khẩu hay nhân viên quên mật khẩu.",
		["Quản trị khoá tạm tài khoản và đổi mật khẩu trong ngày."]),
	("g", "he-thong", "Tác vụ định kỳ thất bại",
		"{{he-thong.job_that_bai.tong|so}} lượt tác vụ định kỳ thất bại trong ngày qua, thuộc {{he-thong.job_that_bai.so_loai|so}} loại việc. Việc chạy tự động có thể bị bỏ sót.",
		["Quản trị xem nhật ký tác vụ và chạy lại việc bị lỗi."]),
	("g", "he-thong", "Email gửi đi bị lỗi",
		"{{he-thong.email_loi.so|so}} email gửi lỗi trong ngày qua. Thư báo cho khách hoặc nội bộ có thể không tới nơi.",
		["Quản trị kiểm tra tài khoản email gửi đi."]),
	("g", "kinh-doanh", "Sản lượng bánh tăng mạnh so với cùng kỳ",
		"Mã {{san-pham.top_products.rows[0].item_code|chu}} bán {{san-pham.top_products.rows[0].qty|so}} hộp, tăng {{san-pham.top_products.rows[0].growth_pct|pct}} so với cùng kỳ ({{san-pham.top_products.rows[0].qty_sp|so}} hộp). Tăng nhanh thì cần chuẩn bị đủ hàng cho mùa Tết sắp tới.",
		["Sản xuất rà lại kế hoạch cho mã bán chạy."]),
	("g", "kinh-doanh", "Chưa phân được doanh số theo tỉnh",
		"Toàn bộ {{tinh-thanh.provinces.rows[0].sales|tien}} doanh số đang nằm ở nhóm {{tinh-thanh.provinces.rows[0].province|chu}}, chiếm {{tinh-thanh.provinces.rows[0].pct|pct}}. Cần kiểm tra: địa chỉ khách chưa khai tỉnh nên không phân tích được theo vùng.",
		["Kinh doanh bổ sung tỉnh thành cho hồ sơ khách hàng trong 14 ngày."]),
	("g", "kinh-doanh", "Hàng Tết và hàng truyền thống đóng góp gần ngang nhau",
		"Nhóm {{tong-quan.item_groups.rows[0].item_group|chu}} đạt {{tong-quan.item_groups.rows[0].amount|tien}}, nhóm {{tong-quan.item_groups.rows[1].item_group|chu}} đạt {{tong-quan.item_groups.rows[1].amount|tien}}. Hai nhóm cân bằng giúp giảm phụ thuộc mùa vụ.",
		["Kinh doanh giữ cơ cấu hàng cân bằng khi lập kế hoạch năm."]),
	("g", "tai-chinh", "Tiền khách trả chưa được gán vào hoá đơn",
		"Còn {{cong-no.receivables.kpis.unallocated|tien}} tiền khách đã trả chưa gán vào hoá đơn và {{cong-no.receivables.kpis.unknown|tien}} nợ chưa rõ hạn. Số liệu quá hạn có thể chưa chính xác cho tới khi kế toán gán xong.",
		["Kế toán gán các khoản đã thu vào hoá đơn trong 7 ngày."]),
	("g", "van-chuyen", "Chi phí xe từ đầu năm",
		"Chi phí xe từ đầu năm là {{van-chuyen.overview.xe.chi_phi_nam.tong|tien}}, lớn nhất là khoản {{van-chuyen.overview.xe.chi_phi_nam.rows[0].loai|chu}} với {{van-chuyen.overview.xe.chi_phi_nam.rows[0].tien|tien}}; công ty đang dùng {{van-chuyen.overview.xe.dang_dung|so}} xe. Cần kiểm tra: xe nào sửa chữa nhiều để cân nhắc thay.",
		["Vận chuyển lập bảng chi phí theo từng xe."]),
	("g", "nhan-su", "Quỹ lương nhóm văn phòng",
		"Nhóm {{nhan-su.overview.luong.bo_phan[0].nhom|chu}} có {{nhan-su.overview.luong.bo_phan[0].so_nguoi|so}} người, tổng lương {{nhan-su.overview.luong.bo_phan[0].tong_tien|tien}}, thực nhận {{nhan-su.overview.luong.bo_phan[0].thuc_nhan|tien}}.",
		["Nhân sự đối chiếu quỹ lương với kế hoạch."]),
	("g", "he-thong", "Chưa có bản sao lưu dữ liệu",
		"Hệ thống không tìm thấy bản sao lưu nào. Mất dữ liệu sẽ không khôi phục được.",
		["Quản trị bật sao lưu tự động ngay hôm nay."]),
	("g", "van-chuyen", "Tải xe còn thấp so với sức chứa",
		"Trong tháng có {{van-chuyen.overview.chuyen.so_chuyen|so}} chuyến, tải trung bình {{van-chuyen.overview.chuyen.tai_tb|pct}} sức chứa; {{van-chuyen.overview.chuyen.qua_tai|so}} chuyến quá tải và {{van-chuyen.overview.chuyen.thieu_cap|so}} chuyến thiếu cặp lái. Xe chạy non tải làm cước mỗi đơn cao.",
		["Vận chuyển gom đơn theo tuyến để tăng tải mỗi chuyến."]),
	("k", "kho-sx", "Hàng truyền thống tồn quá nhiều so với sức bán",
		"Hàng truyền thống đang tồn {{ton-kho.overview.doi.traditional.value|tien}}, đủ bán {{ton-kho.overview.doi.traditional.days|so}} ngày theo giá vốn bán {{ton-kho.overview.doi.traditional.cogs|tien}} của {{ton-kho.overview.doi.window_days|so}} ngày gần nhất. Tồn lâu làm đọng vốn và tăng rủi ro hết hạn.",
		["Kinh doanh lập chương trình đẩy hàng truyền thống trong quý 4.", "Sản xuất giảm kế hoạch nhập kho nhóm hàng này."]),
	("k", "kho-sx", "Thành phẩm hết hạn còn nằm trong kho bán",
		"Còn {{han-dung.overview.han.buckets[0].value|tien}} thành phẩm đã hết hạn, gồm {{han-dung.overview.han.buckets[0].lots|so}} lô với {{han-dung.overview.han.buckets[0].qty|so}} {{han-dung.overview.han.buckets[0].uom|chu}}; hàng cận hạn trong {{han-dung.overview.han.can_date_ngay|so}} ngày tới trị giá {{han-dung.overview.han.can_date.value|tien}}. Hàng hết hạn lẫn trong kho bán có thể bị giao nhầm cho khách.",
		["Kho tách riêng hàng hết hạn trong ngày.", "Chất lượng lập biên bản huỷ hàng hết hạn."]),
	("k", "kho-sx", "Nhiều kho quá lâu chưa kiểm kê",
		"{{kiem-ke._ai.kho_kk_lech_tre.so_kho|so}} kho chưa kiểm kê lần nào hoặc đã quá {{kiem-ke.overview.meta.nguong.nguy|so}} ngày; cả công ty có {{kiem-ke.overview.kho.tong.so_kho|so}} kho, trong đó {{kiem-ke.overview.kho.tong.chua_kiem|so}} kho chưa từng kiểm. Số tồn trên sổ có thể đã lệch thực tế.",
		["Kho lập lịch kiểm kê cho các kho quá hạn trong 14 ngày."]),
	("k", "kho-sx", "Thành phẩm nhập kho chưa có định mức",
		"{{nhap-tp.overview.no_bom.items|so}} mã thành phẩm với {{nhap-tp.overview.no_bom.qty|so}} {{nhap-tp.overview.no_bom.uom|chu}} đã nhập kho mà chưa có định mức, lâu nhất {{nhap-tp.overview.no_bom.age_days|so}} ngày, giá trị tạm tính {{nhap-tp.overview.no_bom.value_tam|tien}}. Nguyên liệu chưa được trừ kho nên giá vốn đang sai.",
		["Sản xuất khai định mức cho các mã còn thiếu trong 7 ngày.", "Kế toán tính lại giá vốn sau khi có định mức."]),
	("k", "kho-sx", "Tồn chết làm đọng vốn kho",
		"Tồn chết chiếm {{ton-kho.overview.slow.total.dead_pct|pct}} giá trị kho bán được, gồm {{ton-kho.overview.slow.total.dead_items|so}} mã trị giá {{ton-kho.overview.slow.total.dead_value|tien}}; hàng chậm bán chiếm thêm {{ton-kho.overview.slow.total.slow_pct|pct}}. Mã đọng nhiều nhất là {{ton-kho.overview.slow.total.top[0].short_name|chu}} với {{ton-kho.overview.slow.total.top[0].value|tien}}.",
		["Kinh doanh đề xuất phương án thanh lý hàng tồn chết.", "Kho rà lại hạn dùng của các mã này."]),
	("k", "kho-sx", "Tồn âm ở nhiều kho",
		"{{han-dung.overview.am.items|so}} mã đang tồn âm ở {{han-dung.overview.am.warehouses|so}} kho, giá trị {{han-dung.overview.am.value_abs|tien}}. Ví dụ mã {{han-dung.overview.am.ds[0].item_code|chu}} còn tồn {{han-dung.overview.am.ds[0].qty|so}} {{han-dung.overview.am.ds[0].uom|chu}} với đơn giá {{han-dung.overview.am.ds[0].rate|tien}}. Xuất trước khi nhập làm giá vốn sai.",
		["Kho nhập bù chứng từ còn thiếu trong 3 ngày."]),
	("k", "kho-sx", "Kiểm kê gần nhất lệch sổ nhiều",
		"Lần kiểm kê gần nhất chỉ {{kiem-ke.overview.ira.so_ma_khop|so}} mã khớp sổ, trong tổng số {{kiem-ke.overview.ira.so_ma|so}} mã đã đếm, tỷ lệ {{kiem-ke.overview.ira.ty_le|pct}}. Kiểm kê sản xuất thiếu {{kiem-ke.overview.kk_sx.gt_thieu|tien}} và thừa {{kiem-ke.overview.kk_sx.gt_thua|tien}}.",
		["Kho tìm nguyên nhân lệch cho từng mã.", "Kế toán chỉ duyệt điều chỉnh sau khi có giải trình."]),
	("k", "kho-sx", "Tính lại giá vốn bị lỗi",
		"{{ton-kho.overview.health.failed_reposts|so}} lượt tính lại giá vốn bị lỗi từ {{ton-kho.overview.health.failed_repost_since|ngay}}, còn {{ton-kho.overview.health.pending_reposts|so}} lượt đang chờ. Giá trị tồn kho {{ton-kho.overview.value.totals.value|tien}} có thể chưa đúng cho tới khi chạy lại.",
		["Kế toán chạy lại việc tính giá vốn và báo quản trị nếu vẫn lỗi."]),
	("k", "kho-sx", "Nguyên liệu treo chưa trừ kho",
		"Còn {{nhap-tp.overview.nvl_treo.n_rm|so}} nguyên liệu treo trị giá {{nhap-tp.overview.nvl_treo.value|tien}}; lớn nhất là {{nhap-tp.overview.nvl_treo.list[0].short_name|chu}} với {{nhap-tp.overview.nvl_treo.list[0].qty|so}} {{nhap-tp.overview.nvl_treo.list[0].uom|chu}}, đơn giá {{nhap-tp.overview.nvl_treo.list[0].rate|tien}}.",
		["Sản xuất khai định mức để hệ thống trừ nguyên liệu."]),
	("k", "kho-sx", "Thành phẩm tồn chưa có giá vốn",
		"{{nhap-tp.overview.gia_von_0.ton.items|so}} mã thành phẩm đang tồn mà chưa có giá vốn, trong tháng thêm {{nhap-tp.overview.gia_von_0.nhap_ky.items|so}} mã nhập kho không có đơn giá. Giá trị tồn và lãi gộp đang bị tính thiếu.",
		["Kế toán bổ sung giá vốn cho các mã còn thiếu trong 7 ngày."]),
	("k", "kho-sx", "Phiếu nhập thành phẩm chờ duyệt lâu",
		"{{nhap-tp.overview.cho_duyet.count|so}} phiếu nhập thành phẩm đang chờ duyệt với {{nhap-tp.overview.cho_duyet.qty|so}} {{nhap-tp.overview.cho_duyet.uom|chu}}, phiếu cũ nhất từ {{nhap-tp.overview.cho_duyet.oldest_date|ngay}}, đã {{nhap-tp.overview.cho_duyet.oldest_age_days|so}} ngày.",
		["Kho duyệt các phiếu tồn trong 2 ngày."]),
	("k", "kho-sx", "Mã bán chạy xuất vượt sản lượng sản xuất",
		"Mã {{sx-tet.items.rows[0].item_code|chu}} đã xuất {{sx-tet.items.rows[0].outgoing|so}} hộp, bằng {{sx-tet.items.rows[0].outgoing_pct|pct}} sản lượng sản xuất {{sx-tet.items.rows[0].produced|so}} hộp; tồn hiện còn {{sx-tet.items.rows[0].stock|so}} hộp.",
		["Sản xuất tăng kế hoạch cho mã này."]),
	("k", "van-chuyen", "Đơn chờ giao quá hạn chưa phân công",
		"{{van-chuyen.overview.giao.cho_qua_han.qua_n|so}} đơn chờ giao quá {{van-chuyen.overview.giao.cho_qua_han.so_ngay|so}} ngày, đều ở nhóm {{van-chuyen.overview.giao.cho_qua_han.rows[0].hinh_thuc|chu}}.",
		["Vận chuyển phân công người giao trong ngày."]),
	("k", "attp", "Truy xuất còn việc mức cao",
		"Lĩnh vực {{attp.overview.linh_vuc[5].ten|chu}} còn {{attp._ai.attp_den_do_truy_xuat.viec|so}} việc treo, {{attp._ai.attp_den_do_truy_xuat.cao|so}} việc mức cao.",
		["Chất lượng xử lý việc mức cao trong 3 ngày."]),
	("k", "kho-sx", "Giá trị tồn kho và phần không bán được",
		"Tổng tồn kho {{ton-kho.overview.value.totals.value|tien}} ở {{ton-kho.overview.value.totals.warehouses_in_stock|so}} kho với {{ton-kho.overview.value.totals.items_in_stock|so}} mã; phần không bán được là {{ton-kho.overview.value.totals.value_unsellable|tien}}, hàng đang đi đường {{ton-kho.overview.value.totals.value_transit|tien}}.",
		["Kho rà soát phần hàng không bán được."]),
	("g", "kinh-doanh", "Doanh số tăng mạnh so với cùng kỳ",
		"Từ đầu năm tài chính bán ra {{tong-quan.summary.rows[0].sales|tien}}, cùng kỳ năm trước chỉ {{tong-quan.summary.rows[1].sales|tien}}; tăng trưởng đạt {{tong-quan.summary.meta.growth.sales|pct}}.",
		["Kinh doanh: giữ nhịp giao hàng cho các khách lớn trong 30 ngày tới."]),
	("g", "kinh-doanh", "Kênh NPP trả hàng nhiều nhất",
		"Kênh {{tong-quan.channels.rows[0].channel|chu}} có tỷ lệ trả hàng {{tong-quan.channels.rows[0].return_rate|pct}}, giá trị trả về {{tong-quan.channels.rows[0].returns|tien}}; cần kiểm tra: nguyên nhân trả hàng theo từng nhà phân phối.",
		["Kinh doanh: rà lại các đơn trả của kênh NPP trong 7 ngày."]),
	("g", "kinh-doanh", "Doanh số dồn vào hai khách lớn",
		"Khách §tong-quan.top_customers.rows[0].customer§ mua {{tong-quan.top_customers.rows[0].amount|tien}} từ đầu năm, khách thứ hai là §tong-quan.top_customers.rows[1].customer§ với {{tong-quan.top_customers.rows[1].amount|tien}}.",
		["Kinh doanh: chăm sóc riêng hai khách lớn nhất và mở thêm khách mới để giảm phụ thuộc."]),
	("g", "kinh-doanh", "Hàng Tết dẫn đầu cơ cấu bán",
		"Nhóm {{tong-quan.item_groups.rows[0].item_group|chu}} đạt {{tong-quan.item_groups.rows[0].amount|tien}}, nhóm {{tong-quan.item_groups.rows[1].item_group|chu}} đạt {{tong-quan.item_groups.rows[1].amount|tien}}.",
		["Sản xuất: chuẩn bị nguyên liệu cho mùa Tết theo kế hoạch bán.", "Kinh doanh: chốt đơn Tết sớm với nhà phân phối."]),
	("g", "kinh-doanh", "Mã bánh Tết tăng nhanh",
		"Mã {{san-pham.top_products.rows[0].item_code|chu}} bán {{san-pham.top_products.rows[0].qty|so}} sản phẩm, tăng {{san-pham.top_products.rows[0].growth_pct|pct}} so với cùng kỳ.",
		["Kho: giữ đủ tồn mã này cho các đơn tuần tới."]),
	("g", "kinh-doanh", "Doanh số tháng giảm sau tháng đầu năm",
		"Tháng đầu năm tài chính đạt {{thang.monthly.rows[0].sales|tien}}, tháng kế tiếp giảm còn {{thang.monthly.rows[1].sales|tien}}; cần kiểm tra: lịch giao hàng của tháng sau.",
		["Kinh doanh: so lại kế hoạch bán từng tháng với thực tế."]),
	("g", "tai-chinh", "Nợ quá hạn chiếm phần lớn phải thu",
		"Nợ quá hạn {{cong-no.receivables.kpis.overdue|tien}}, chiếm {{cong-no.receivables.kpis.overdue_pct|pct}} tổng phải thu {{cong-no.receivables.kpis.receivable|tien}}; có {{cong-no.receivables.kpis.overdue_customers|so}} khách đang trễ hạn.",
		["Kế toán: gọi điện nhắc nợ từng khách quá hạn trong 7 ngày.", "Kinh doanh: tạm dừng giao thêm cho khách quá hạn lâu nhất."]),
	("g", "tai-chinh", "Khách nợ quá hạn lâu nhất",
		"Khách §cong-no.receivables.top_overdue[1].customer§ quá hạn {{cong-no.receivables.top_overdue[1].overdue|tien}}, khoản cũ nhất đã {{cong-no.receivables.top_overdue[1].max_days|so}} ngày.",
		["Kế toán: làm biên bản đối chiếu công nợ với khách này trong tuần."]),
	("g", "tai-chinh", "Tiền bán hàng thu về chậm",
		"Bình quân {{cong-no.receivables.kpis.dso.dso|so}} ngày mới thu được tiền, khách đang nợ {{cong-no.receivables.kpis.dso.debt|tien}} so với doanh thu {{cong-no.receivables.kpis.dso.revenue|tien}}.",
		["Kế toán: rút ngắn hạn thanh toán với khách mới."]),
	("g", "tai-chinh", "Còn hoá đơn mua quá hạn chưa trả",
		"Đã quá hạn {{phai-tra.payables.ap.due.overdue_total|tien}} với {{phai-tra.payables.ap.due.overdue_count|so}} hoá đơn; sắp đến hạn thêm {{phai-tra.payables.ap.due.upcoming_total|tien}}.",
		["Kế toán: lên lịch trả nhà cung cấp trong 7 ngày."]),
	("g", "tai-chinh", "Quỹ đủ trả nợ nhà cung cấp",
		"Tiền mặt và tiền gửi còn {{phai-tra.payables.cash.total|tien}}, trong đó tiền gửi ngân hàng {{phai-tra.payables.cash.bank|tien}}.",
		["Kế toán: ưu tiên trả các hoá đơn đã quá hạn."]),
	("g", "tai-chinh", "Có {{cong-no.receivables.kpis.over_limit|so}} khách vượt hạn mức tín dụng",
		"Ứng trước của khách {{cong-no.receivables.kpis.advances|tien}}, phải thu ròng {{cong-no.receivables.kpis.net|tien}}; cần kiểm tra: hạn mức có còn phù hợp.",
		["Kinh doanh: duyệt lại hạn mức của khách vượt hạn."]),
	("g", "van-chuyen", "Đơn chờ giao dồn nhiều",
		"Có {{van-chuyen.overview.giao.cho|so}} đơn đang chờ giao trên tổng {{van-chuyen.overview.giao.total|so}} đơn, tỷ lệ đã giao chỉ {{van-chuyen.overview.giao.ty_le_giao|pct}}.",
		["Vận chuyển: xếp thêm chuyến cho các đơn chờ lâu trong 2 ngày."]),
	("g", "van-chuyen", "Cước vận chuyển cao so với doanh thu",
		"Tổng cước tháng {{van-chuyen.overview.cuoc.tong|tien}}, bình quân {{van-chuyen.overview.cuoc.moi_chuyen|tien}} mỗi chuyến, bằng {{van-chuyen.overview.cuoc.ty_le_doanh_thu|pct}} doanh thu đơn đã giao.",
		["Vận chuyển: ghép đơn cùng tuyến để giảm số chuyến."]),
	("g", "van-chuyen", "Xe chạy chưa đầy tải",
		"Tải trung bình mỗi chuyến chỉ {{van-chuyen.overview.chuyen.tai_tb|pct}} sức chứa, có {{van-chuyen.overview.chuyen.thieu_cap|so}} chuyến thiếu cấp và {{van-chuyen.overview.chuyen.qua_tai|so}} chuyến quá tải.",
		["Vận chuyển: xem lại cách chia đơn theo sức chứa của xe."]),
	("g", "van-chuyen", "Xe quá hạn đăng kiểm",
		"Xe {{van-chuyen.overview.xe.can_xu_ly[0].xe|chu}} quá hạn {{van-chuyen.overview.xe.can_xu_ly[0].viec[0].viec|chu}} từ {{van-chuyen.overview.xe.can_xu_ly[0].viec[0].han|ngay}}; công ty đang dùng {{van-chuyen.overview.xe.dang_dung|so}} xe.",
		["Vận chuyển: đưa xe đi đăng kiểm ngay, không cho chạy đường dài."]),
	("g", "nhan-su", "BHXH mới phủ một phần người lao động",
		"Mới có {{nhan-su.overview.bhxh.dong|so}} người đóng BHXH, trong số {{nhan-su.overview.bhxh.dang_lam|so}} người đang làm, tỷ lệ {{nhan-su.overview.bhxh.ty_le|pct}}.",
		["Nhân sự: lập danh sách người cần đăng ký BHXH trong 30 ngày."]),
	("g", "nhan-su", "Người chưa đóng BHXH chưa ghi lý do",
		"Có {{nhan-su.overview.bhxh.rui_ro|so}} người quá một tháng chưa đóng BHXH và chưa ghi lý do; cần kiểm tra: hợp đồng thời vụ đã đúng hay chưa.",
		["Nhân sự: ghi rõ lý do hoặc đăng ký BHXH cho từng người."]),
	("g", "nhan-su", "Nhân sự tạm nghỉ ở bộ phận khoán",
		"Đang làm {{nhan-su.overview.nhan_su.dang_lam|so}} người, tạm nghỉ {{nhan-su.overview.nhan_su.tam_nghi|so}} người; riêng bộ phận {{nhan-su.overview.nhan_su.by_dept[0].bo_phan|chu}} có {{nhan-su.overview.nhan_su.by_dept[0].tam_nghi|so}} người tạm nghỉ.",
		["Nhân sự: hỏi lý do tạm nghỉ và kế hoạch đi làm lại."]),
	("g", "nhan-su", "Hợp đồng lao động hết hạn",
		"Có {{nhan-su.overview.giay_to.hd.do|so}} người đã hết hạn hợp đồng, {{nhan-su.overview.giay_to.hd.vang|so}} người sắp hết trong {{nhan-su.overview.giay_to.so_ngay|so}} ngày tới.",
		["Nhân sự: ký lại hợp đồng trước khi hết hạn."]),
	("g", "attp", "Vòng kiểm hằng ngày báo đỏ",
		"{{attp.overview.linh_vuc[0].ten|chu}} còn {{attp._ai.attp_den_do_vong_kiem.viec|so}} việc treo, trong đó {{attp._ai.attp_den_do_vong_kiem.cao|so}} việc mức cao; tỷ lệ lượt đủ {{attp.overview.linh_vuc[0].so|chu}}.",
		["Chất lượng: bổ sung lượt kiểm còn thiếu ngay trong ca."]),
	("g", "attp", "Nhiều lĩnh vực ATTP đang báo đỏ",
		"Có {{attp.overview.dem.do|so}} lĩnh vực báo đỏ, {{attp.overview.dem.vang|so}} lĩnh vực báo vàng và {{attp.overview.dem.xanh|so}} lĩnh vực đạt.",
		["Chất lượng: họp Ban ATTP chốt người xử lý từng lĩnh vực đỏ."]),
	("g", "attp", "Sự cố ATTP mức cao chưa đóng",
		"{{attp.overview.linh_vuc[1].ten|chu}}: còn {{attp._ai.attp_den_do_su_co.viec|so}} việc treo, {{attp._ai.attp_den_do_su_co.cao|so}} việc mức cao.",
		["Chất lượng: đóng sự cố mức cao trong 3 ngày."]),
	("g", "he-thong", "Ổ đĩa máy chủ cần theo dõi",
		"Ổ đĩa đã dùng {{he-thong.dia_day.pct|pct}}, chỉ còn {{he-thong.dia_day.con_trong_gb|so}} GB trống.",
		["Quản trị: dọn tệp tạm và bản sao lưu cũ trong 7 ngày."]),
	("g", "he-thong", "Chưa có bản sao lưu nào",
		"Không tìm thấy bản sao lưu dữ liệu, mất dữ liệu sẽ không khôi phục được; ổ đĩa đang dùng {{he-thong.dia_day.pct|pct}}.",
		["Quản trị: bật sao lưu tự động và kiểm tra bản đầu tiên hôm nay."]),
	("k", "kho-sx", "Tồn âm làm sai giá vốn",
		"{{han-dung.overview.am.items|so}} mã hàng đang âm ở {{han-dung.overview.am.warehouses|so}} kho, giá trị {{han-dung.overview.am.value_abs|tien}}; mã {{han-dung.overview.am.ds[0].item_code|chu}} âm với đơn giá sổ {{han-dung.overview.am.ds[0].rate|tien}}.",
		["Kho: nhập bù chứng từ còn thiếu trong 7 ngày."]),
	("k", "kho-sx", "Tồn chết chiếm tỷ trọng đáng kể",
		"Tồn chết chiếm {{ton-kho.overview.slow.total.dead_pct|pct}} giá trị hàng bán được, tương đương {{ton-kho.overview.slow.total.dead_value|tien}} của {{ton-kho.overview.slow.total.dead_items|so}} mã.",
		["Kinh doanh: lên chương trình xả hàng tồn lâu.", "Kho: dừng nhập thêm các mã tồn chết."]),
	("k", "kho-sx", "Độ khớp kiểm kê thấp",
		"Phiếu {{kiem-ke.overview.ira.rows[0].phieu|chu}} chỉ {{kiem-ke.overview.ira.rows[0].so_ma_khop|so}} mã khớp sổ, trong tổng số {{kiem-ke.overview.ira.rows[0].so_ma|so}} mã, đạt {{kiem-ke.overview.ira.rows[0].ty_le|pct}}; còn {{kiem-ke.overview.kho.tong.chua_kiem|so}} kho chưa kiểm lần nào.",
		["Kho: kiểm kê lại các kho chưa kiểm trong tháng này."]),
	("k", "kho-sx", "Nguyên liệu treo chưa trừ kho",
		"Có {{nhap-tp.overview.nvl_treo.n_rm|so}} nguyên liệu treo, giá trị {{nhap-tp.overview.nvl_treo.value|tien}}; {{nhap-tp.overview.nvl_treo.list[0].short_name|chu}} có đơn giá {{nhap-tp.overview.nvl_treo.list[0].rate|tien}}.",
		["Sản xuất: hoàn tất định mức để trừ nguyên liệu khỏi kho."]),
	("k", "kho-sx", "Tồn bánh truyền thống cao hơn sản xuất",
		"Mã {{sx-tet.items.rows[0].short_name|chu}} tồn {{sx-tet.items.rows[0].stock|so}} hộp, sản xuất {{sx-tet.items.rows[0].produced|so}} hộp và xuất {{sx-tet.items.rows[0].outgoing|so}} hộp trong kỳ.",
		["Sản xuất: giảm sản lượng mã này cho tới khi tồn về mức bình thường."]),
]
_CON = r"""
import json, os, re, sys, decimal, tempfile, importlib
sys.dont_write_bytecode = True
importlib.import_module(sys.argv[1])
import frappe
from bc.ai import collect, registry, render
frappe.session.user = "Administrator"
frappe.FAKE_SITE_PATH = tempfile.mkdtemp(prefix="bc_ai_r_")
now = frappe.utils.now_datetime()
pack = collect.build(frappe.utils.getdate(now))
pack["he-thong"] = registry.run_detectors(now)
rr = registry.run_rules(pack, registry.overrides_from_settings())
kinds = registry.kind_map(rr.signals)
kieu = getattr(render, "kieu_cua", None) or (lambda pk, p, kd: kd.get(registry.strip_index(p))
	or render.kieu_theo_ten(registry.strip_index(p)))
def walk(o, p=""):
	if isinstance(o, dict):
		for k, v in o.items():
			yield from walk(v, f"{p}.{k}" if p else str(k))
	elif isinstance(o, (list, tuple)):
		for i, v in enumerate(o):
			yield from walk(v, f"{p}[{i}]")
	else:
		yield p, o
la = {}
for p, v in walk(pack):
	if isinstance(v, bool) or not isinstance(v, (int, float, decimal.Decimal)):
		continue
	la.setdefault(registry.strip_index(p), set()).add(str(kieu(pack, p, kinds)))
quy_tac = []
for s in rr.signals:
	g = registry.group_of(s.section)
	secs = set(registry.GROUPS[g]["sections"]) if g else {s.section}
	r = render.render_insight({"title": s.title, "body": s.detail or s.title, "advice": []}, pack, secs, None, kinds=kinds)
	quy_tac.append([s.key, r["ok"], r["errors"]])
gia = {}
if "han-dung" in pack:
	for p in ("han-dung.overview.am.ds[0].rate", "nhap-tp.overview.nvl_treo.list[0].rate"):
		if registry.resolve(pack, p, None) is None:
			continue
		g = registry.group_of(p.split(".")[0])
		gia[p] = {k: render.render_insight({"title": "Kho", "body": "Đơn giá sổ {{" + p + "|" + k + "}} mỗi đơn vị.",
			"advice": []}, pack, set(registry.GROUPS[g]["sections"]), None, kinds=kinds)["ok"] for k in ("tien", "pct", "so")}
# G4: nhận định đúng (stdin) → như pipeline: che gói của nhóm, dựng đề bài, restrict, chép mã giả, render_insight
from bc.ai import prompt, redact
mask = redact.build()
dung = []
for i, nhom, title, body, advice in json.loads(sys.stdin.read() or "[]"):
	secs = list(registry.GROUPS[nhom]["sections"])
	getattr(mask, "begin", lambda: None)()
	goi = mask.mask({x: pack[x] for x in secs if x in pack})
	user, _ = prompt.build_user(nhom, goi, [], kinds=kinds)
	getattr(mask, "restrict", lambda t: None)(user)
	chep = lambda t: re.sub(r"§([^§]+)§", lambda m: str(registry.resolve(goi, m.group(1))), t)
	r = render.render_insight({"title": chep(title), "body": chep(body), "advice": [chep(a) for a in advice]}, pack,
		set(secs), mask, kinds=kinds)
	dung.append([i, r["ok"], r["errors"]])
print("@@KQ@@" + json.dumps({"la": {k: sorted(v) for k, v in la.items()}, "quy_tac": quy_tac, "gia": gia,
	"not_run": rr.not_run, "dung": dung}, ensure_ascii=False))
"""
THAT = {}
for ten, seed in (("chung", "seed_ui2"), ("kho", "seed_ui_kho")):
	env = dict(os.environ, BC_TEST_DB=os.environ.get("BC_TEST_DB", "bc_test_ai_render") + ("_g" if ten == "chung" else "_k"))
	vao = json.dumps([[i, x[1], x[2], x[3], x[4]] for i, x in enumerate(DUNG) if x[0] == {"chung": "g", "kho": "k"}[ten]], ensure_ascii=False)
	pr = subprocess.run([sys.executable, "-B", "-c", _CON, seed], cwd=os.path.dirname(os.path.abspath(__file__)),
		env=env, capture_output=True, text=True, timeout=900, input=vao)
	kq = [x for x in pr.stdout.splitlines() if x.startswith("@@KQ@@")]
	c(f"E2: dựng gói số thật ({seed}) trong tiến trình riêng", pr.returncode == 0 and len(kq) == 1,
		(pr.stderr or pr.stdout)[-800:])
	THAT[ten] = json.loads(kq[0][6:]) if kq else {"la": {}, "quy_tac": [], "gia": {}, "dung": []}
la_that = {}
for ten, kq in THAT.items():
	for p, ks in kq["la"].items():
		la_that.setdefault(p, set()).update(ks)
c("E2: gói số thật có đủ lá để soát (≥ 900 path, cả van-chuyen / nhan-su / han-dung / nhap-tp)", len(la_that) >= 900
	and all(any(p.startswith(m + ".") for p in la_that) for m in ("van-chuyen", "nhan-su", "han-dung", "nhap-tp")),
	len(la_that))
eq("E2: MỌI lá số của hai gói số thật đều xếp được kiểu (trừ danh sách cố ý để trống)",
	sorted(p for p, ks in la_that.items() if "None" in ks and p not in LA_DE_TRONG), [])
# (bảng chỉ số ATTP: cùng khoá, đơn vị theo từng dòng — "%" hoặc số đếm — nên được hai kiểu)
eq("E2: không lá nào bị hai kiểu khác nhau (trừ bảng chỉ số ATTP, kiểu theo don_vi của dòng)", sorted(p for p, ks
	in la_that.items() if len(ks - {"None"}) > 1 and not p.startswith(("attp.report.bang.", "attp.report.chi_tieu."))),
	[])
DUNG_THAT = {"van-chuyen.overview.chuyen.tai_tb": "pct", "van-chuyen.overview.cuoc.tong": "tien",
	"van-chuyen.overview.xe.chi_phi_nam.tong": "tien", "van-chuyen.overview.giao.cho": "so",
	"van-chuyen.overview.xe.dang_dung": "so", "nhan-su.overview.bhxh.dong": "so", "nhan-su.overview.bhxh.dang_lam": "so",
	"nhan-su.overview.bhxh.ty_le": "pct", "han-dung.overview.am.ds.rate": "tien",
	"nhap-tp.overview.nvl_treo.list.rate": "tien", "tong-quan.summary.rows.return_rate": "pct"}
eq("E2: lá đại diện trên gói số thật → đúng kiểu", {p: sorted(la_that.get(p, {"thiếu"})) for p, k in DUNG_THAT.items()
	if la_that.get(p) != {k}}, {})
eq("E2: đơn giá sổ thật (seed kho) — |tien nhận, |pct và |so loại", THAT["kho"]["gia"],
	{p: {"tien": True, "pct": False, "so": False} for p in ("han-dung.overview.am.ds[0].rate",
	"nhap-tp.overview.nvl_treo.list[0].rate")})
print("\n— E5: lời quy tắc (tiêu đề / chi tiết) chép nguyên làm lời mô hình → render_insight nhận (kinds của lượt) —")
c("E5: có lời quy tắc để soát (≥ 30 tín hiệu trên hai seed)", sum(len(k["quy_tac"]) for k in THAT.values()) >= 30,
	{t: len(k["quy_tac"]) for t, k in THAT.items()})
eq("E5: mọi lời quy tắc của seed chung + seed kho qua được luật của chính nó",
	[f"{t}:{k}: {e}" for t, kq in THAT.items() for k, ok, e in kq["quy_tac"] if not ok], [])

print("\n— G4: bộ nhận định ĐÚNG (≥ 60, đủ 7 nhóm, hai seed) — mọi câu phải được nhận —")
c("G4: bộ lời đúng ≥ 60 câu, đủ 7 nhóm, cả hai seed", len(DUNG) >= 60 and {x[1] for x in DUNG} == set(registry.GROUPS)
	and {x[0] for x in DUNG} == {"g", "k"}, (len(DUNG), sorted({x[1] for x in DUNG})))
c("G4: mọi câu đã chạy qua render_insight trên gói số thật", sum(len(k.get("dung", [])) for k in THAT.values())
	== len(DUNG), sum(len(k.get("dung", [])) for k in THAT.values()))
eq("G4: mọi nhận định đúng được nhận (không lỗi)", [f"#{i} [{DUNG[i][1]}] {DUNG[i][2]}: {e}" for kq in THAT.values()
	for i, ok, e in kq.get("dung", []) if not ok], [])

print("\n— E3: số / từ chỉ số / dấu quanh placeholder số —")
PS["attp"] = {"overview": {"du_lieu_mau": "", "gach": "–", "trang": "   ", "nhan": "Xanh"}}
P1 = "tong-quan.summary.rows[0].invoices"


def r3(body):
	return render.render_insight({"title": "Tiêu đề", "body": body, "advice": []}, PS, {"san-pham", "tong-quan", "attp"},
		redact.Mask())


for body, nhan in (
		(f"Còn {{{{{P1}|so}}}}{{{{attp.overview.du_lieu_mau|chu}}}}{{{{{P1}|so}}}} việc treo.", "chu rỗng giữa hai số"),
		(f"Còn 1{{{{attp.overview.du_lieu_mau|chu}}}}{{{{{P1}|so}}}} việc.", "chữ số + chu rỗng + số"),
		(f"Còn {{{{attp.overview.trang|chu}}}} {{{{{P1}|so}}}} việc.", "chu chỉ có khoảng trắng"),
		(f"Lệch {{{{attp.overview.gach|chu}}}}{{{{{P1}|so}}}} so với tuần trước.", "chu là dấu gạch trước số (dấu âm)"),
		(f"Có {{{{{P1}|so}}}}{{{{attp.overview.gach|chu}}}}5 việc.", "chu là dấu gạch + chữ số sau"),
		(f"Hơn mười {{{{{P1}|so}}}} khách quá hạn.", "'mười' trước placeholder"),
		(f"Có hai mươi {{{{{P1}|so}}}} khách.", "'mươi' trước placeholder"),
		(f"Có {{{{{P1}|so}}}} mươi khách chậm trả.", "'mươi' sau placeholder"),
		(f"Vượt {{{{{P1}|so}}}} rưỡi.", "'rưỡi' sau"), (f"Còn {{{{{P1}|so}}}} tá khách.", "'tá' sau"),
		(f"Còn {{{{{P1}|so}}}} lẻ hộp.", "'lẻ' sau"), (f"Có một trăm linh {{{{{P1}|so}}}} đơn.", "'linh' trước"),
		(f"Cứ 1/{{{{{P1}|so}}}} số khách trả chậm.", "'1/' trước"), (f"Tức {{{{{P1}|so}}}}/10 khách.", "'/10' sau"),
		(f"Tỷ số 3:{{{{{P1}|so}}}} khách.", "'3:' trước"), (f"Tỷ số {{{{{P1}|so}}}}: 4 khách.", "': 4' sau"),
		(f"Từ 5-{{{{{P1}|so}}}} ngày.", "'5-' dính trước"), (f"Từ {{{{{P1}|so}}}}–9 ngày.", "'–9' dính sau"),
		(f"Tăng trưởng thu nợ-{{{{{P0}.ty_le|chu}}}}.", "chu trông như số sau gạch dính chữ"),
		(f"Doanh số đạt {{{{tong-quan.summary.rows[0].sales|tien}}}}, đồng nghĩa tăng.", "(giữ chỗ: không lỗi)")):
	r = r3(body)
	if nhan.startswith("(giữ"):
		c(f"E3: giữ — 'đồng nghĩa' không phải đơn vị", r["ok"] is True, f"{r['errors']}")
		continue
	c(f"E3: loại — {nhan}", r["ok"] is False and any(e.startswith(("so-tran:", "chu-rong:")) for e in r["errors"]),
		f"{r['ok']} {r['errors']} {r['body']!r}")
PP = {"cong-no": {"receivables": {"kpis": {"overdue_pct": 54.5, "overdue": 120e6}}}}
r = render.render_insight({"title": "Nợ", "body": "Tăng trưởng thu nợ-{{cong-no.receivables.kpis.overdue_pct|pct}}.",
	"advice": []}, PP, {"cong-no"}, None, kinds={})
c("E3: '-' dính chữ ngay trước placeholder pct → loại", r["ok"] is False and any(e.startswith("so-tran:") for e in
	r["errors"]), f"{r['ok']} {r['errors']}")
r = render.render_insight({"title": "Nợ", "body": "Mã KK-{{cong-no.receivables.kpis.overdue|tien}} vẫn là nối.",
	"advice": []}, PP, {"cong-no"}, None, kinds={})
c("G2: '-' dính chữ trước placeholder tien (nối mã) nay cũng bị loại (trước placeholder chỉ chữ / ( , : ;)",
	r["ok"] is False and "so-tran:KK-{{cong-no.receivables.kpis.overdue|tien}}" in r["errors"], f"{r['errors']}")
r = r3(f"Nhãn {{{{attp.overview.nhan|chu}}}} đạt {{{{{P1}|so}}}} việc.")
c("E3: chu có chữ (không rỗng) bên cạnh vẫn nhận", r["ok"] is True, f"{r['errors']}")
for text, want in (("Nợ quá hạn (12) tỷ", "12) tỷ"), ("Tổng 12 x tỷ", "12 x tỷ"), ("Còn 12: tỷ", "12: tỷ"),
		("Đạt 12 = tỷ", "12 = tỷ"), ("Đạt 12 · tỷ", "12 · tỷ"), ("Nợ \"12\" tỷ", "12\" tỷ"), ("khoảng 4 per cent", "4 per cent"),
		("tăng 35 bps", "35 bps"), ("hao 5 phần nghìn", "5 phần nghìn"), ("đạt 3 phần mười", "3 phần mười"),
		("tức ba lăm % phải thu", "ba lăm %"), ("thêm 2 củ", "2 củ"), ("chín mươi%", "chín mươi%")):
	got = render.lint(text)
	c(f"E3: lint bắt — {text!r} → {want!r}", want in got, str(got))
for text in ("DSO 62 ngày, chín mươi chín khách quá hạn", "quý 3, đồng thời kho tăng", "Bước 5: kiểm kho", "trong 5 ngày",
		"trong 7 ngày (gấp)", "củ hành", "Ông Ba tới"):
	c(f"E3: lint giữ — {text!r}", render.lint(text) == [], str(render.lint(text)))

print("\n— E4: lint không chạy bậc hai trên dãy số dài —")
for nhan, text in (("một dãy 40.000 chữ số", "1" * 40000), ("'1.2.' × 10.000", "1.2." * 10000),
		("'12.' × 13.000", "12." * 13000), ("'4E' + 40.000 chữ số", "4E" + "1" * 40000)):
	t0 = time.monotonic()
	got = render.lint(text)
	dt = time.monotonic() - t0
	c(f"E4: lint {nhan} < 2 s ({dt:.2f} s), có bắt", dt < 2 and got, f"{dt:.2f} s")
t0 = time.monotonic()
r = rs(f"Có {{{{{P0}.boxes|so}}}} " + "1" * 20000)
dt = time.monotonic() - t0
c(f"E4: render_insight placeholder + 20.000 chữ số < 2 s ({dt:.2f} s), loại", dt < 2 and r["ok"] is False, f"{dt:.2f} s")

# ══ 7e. Vòng sửa 3: G1 (chữ số viết tay — danh sách CHO PHÉP), G2 (láng giềng placeholder — danh sách CHO PHÉP) ══
print("\n— G1 / G2: các lời sai W1–W6 của lần soát lại (verify2) và họ hàng của chúng —")
PW = {"cong-no": {"receivables": {"kpis": {"overdue": 120e6, "receivable": 220e6, "overdue_pct": 54.5,
		"overdue_customers": 4, "over_limit": 1}}},
	"van-chuyen": {"overview": {"giao": {"cho": 18}}},
	"nhan-su": {"overview": {"bhxh": {"dang_lam": 21, "ty_le": 38.1}}},
	"attp": {"overview": {"tieu_de": "1 phiếu sự cố quá hạn", "uom": "Thùng", "kho": "Kho 2", "nhan": "Xanh",
		"ma": "TET1", "qty": 120}, "_ai": {"viec": 2}},
	"ngay": {"daily": {"rows": [{"date": "2026-10-27", "orders": 5}]}}}
K3 = "cong-no.receivables.kpis"
Z, RC, Y, X, X2 = (f"{{{{{K3}.overdue|tien}}}}", f"{{{{{K3}.receivable|tien}}}}", f"{{{{{K3}.overdue_pct|pct}}}}",
	f"{{{{{K3}.overdue_customers|so}}}}", f"{{{{{K3}.over_limit|so}}}}")
VCG, NSD, NSY = "{{van-chuyen.overview.giao.cho|so}}", "{{nhan-su.overview.bhxh.dang_lam|so}}", "{{nhan-su.overview.bhxh.ty_le|pct}}"
CT, AV, UOM, KHO = ("{{attp.overview.tieu_de|chu}}", "{{attp._ai.viec|so}}", "{{attp.overview.uom|chu}}",
	"{{attp.overview.kho|chu}}")
NHAN, MA, QTY = "{{attp.overview.nhan|chu}}", "{{attp.overview.ma|chu}}", "{{attp.overview.qty|so}}"
DN, DO = "{{ngay.daily.rows[0].date|ngay}}", "{{ngay.daily.rows[0].orders|so}}"


def rw(body, mask=None):
	return render.render_insight({"title": "Tiêu đề", "body": body, "advice": []}, PW, None, mask, kinds={})


W_SAI = [
	("W1", "Nợ quá hạn " + Z + ", riêng nhóm lớn còn 12 ; tỷ chưa thu."), ("W1", "Nợ dồn khoảng 12 × tỷ."),
	("W1", "Nợ nhà cung cấp khoảng 3 ⋅ tỷ."), ("W1", "Nhóm lớn nợ 12‐tỷ chưa đối chiếu."),
	("W1", "Riêng kênh NPP 12 / tỷ."), ("W1", "Mục tiêu 12<!-- -->tỷ."), ("W1", "Khoảng 3 • tỷ là hàng Tết."),
	("W1", "Nợ 12 | tỷ."), ("W1", "Nợ 12 … tỷ."), ("W1", "Nợ 12 → tỷ."),
	("W2", "Ước còn 5 tỏi nợ chưa rõ hạn."), ("W2", "Nợ cũ khoảng XII tỷ chưa thu."), ("W2", "Tăng XXXV phần trăm."),
	("W2", "Còn năm tỏi nợ."),
	("W3", f"Có {VCG} lăm đơn đang chờ giao."), ("W3", f"Có {VCG} mốt đơn chưa xếp chuyến."),
	("W3", f"Chờ giao {VCG} x 10 đơn."), ("W3", f"Đơn chờ {VCG} trên 10 đơn mỗi xe."),
	("W3", f"Đang làm {NSD}÷10 tổ."), ("W3", f"Cứ 1⁄{NSD} người hết hạn hợp đồng."),
	("W3", f"Đang làm {NSD} - 5 người chưa khám."), ("W3", f"Cứ 1 trên {NSD} người bị trùng lương."),
	("W3", f"Đang làm {NSD} phần 10 chưa đóng BHXH."), ("W3", f"Đang làm {NSD}\\10 tổ."),
	("W3", f"Có muoi {X} khách."), ("W3", f"Có mười, {X} khách."), ("W3", f"Có mười ({X}) khách."),
	("W3", f"Có tư {X} khách."), ("W3", f"Có nghìn {X} khách."), ("W3", f"Có vài {X} khách."),
	("W3", f"Có {X} tư khách."), ("W3", f"Có bẩy {X} khách."),
	("W4", f"Còn {AV}{CT}."), ("W4", f"Ghi nhận 1{CT}."), ("W4", f"Ghi nhận -{CT}."), ("W4", f"Còn {AV} {CT}."),
	("W4", f"Đơn ngày {DO}{DN} cao bất thường."), ("W4", f"Ngày {DN}{DO} đơn."),
	("W5", f"Nợ quá hạn (−){Z} so với tháng trước."), ("W5", f"Nợ trong kỳ ({Z})0 cần thu."),
	("W5", f"Tăng trưởng thu nợ—{Y} so với kỳ trước."),
]
for w, body in W_SAI:
	r = rw(body)
	c(f"{w}: loại — {body!r}", r["ok"] is False and any(e.startswith("so-tran:") for e in r["errors"]),
		f"{r['ok']} {r['errors']} {r['body']!r}")
for body, want in ((f"Kho còn {X} linh kiện thay thế.", "Kho còn 4 linh kiện thay thế."),
		(f"Có {X} đồng hồ đo nhiệt chưa hiệu chuẩn.", "Có 4 đồng hồ đo nhiệt chưa hiệu chuẩn."),
		(f"Còn {X} đồng hồ nước, {X2} linh kiện.", "Còn 4 đồng hồ nước, 1 linh kiện.")):
	r = rw(body)
	eq(f"W6: nhận — {body!r}", (r["ok"], r["errors"], r["body"]), (True, [], want))

print("\n— G2: láng giềng của placeholder — dạng được phép / bị loại (mọi kiểu) —")
G2_NHAN = [
	(f"Nợ quá hạn {Z}, chiếm {Y} phải thu.", "Nợ quá hạn 120 triệu, chiếm 54,5% phải thu."),
	(f"Phải thu ({RC}) tăng; gồm: {Z} quá hạn.", "Phải thu (220 triệu) tăng; gồm: 120 triệu quá hạn."),
	(f"{X} khách trễ hạn; {X2} khách vượt hạn mức!", "4 khách trễ hạn; 1 khách vượt hạn mức!"),
	(f"Tổng cộng {Z}, đầu tư thêm {RC}.", "Tổng cộng 120 triệu, đầu tư thêm 220 triệu."),
	(f"Nợ quá hạn “{Z}”. Năm nay cần thu gấp.", "Nợ quá hạn “120 triệu”. Năm nay cần thu gấp."),
	(f"Mã {MA} còn {QTY} {UOM}.", "Mã TET1 còn 120 Thùng."),
	(f"Nhãn {NHAN}: {X} việc.", "Nhãn Xanh: 4 việc."),
	(f"Ngày {DN} có {DO} đơn, quý 4 đạt {Z}, trong 7 ngày.", "Ngày 27/10/2026 có 5 đơn, quý 4 đạt 120 triệu, trong 7 ngày."),
	(f"{Z} là nợ quá hạn", "120 triệu là nợ quá hạn"),
	(f"Có {X} khách. 7 ngày qua chưa thu.", "Có 4 khách. 7 ngày qua chưa thu."),
	(f"Đạt {Z}, năm ngoái chỉ {RC}.", "Đạt 120 triệu, năm ngoái chỉ 220 triệu."),
	(f"Từ đầu năm: {Z}.", "Từ đầu năm: 120 triệu."),
]
for body, want in G2_NHAN:
	r = rw(body)
	eq(f"G2: nhận — {body[:70]!r}", (r["ok"], r["errors"], r["body"]), (True, [], want))
G2_LOAI = [
	(f"Nợ {Z} ({Y}).", "ngoặc mở sau placeholder; hai placeholder chỉ cách dấu"), (f"Nợ {Z}: {Y}.", "{a}: {b}"),
	(f"Nợ {Z}–{Y}.", "{a}–{b}"), (f"Nợ {Z}/{RC}.", "{a}/{b}"), (f"Nợ {Z}. {RC} là phải thu.", "{a}. {b}"),
	(f"Có {X}, {X2} khách.", "{a}, {b}"), (f"Tuần 2, {X} khách.", "chữ số trước dấu phẩy rồi placeholder"),
	(f"Nợ 4,{Z}.", "4,{x} (thành phần lẻ)"), (f"Nợ 4.{Z}.", "4.{x}"), (f"Nợ quá hạn,{Z}.", "dấu phẩy dính placeholder"),
	(f"Có {X},5 khách.", "{x},5"), (f"Có {X}, 5 khách.", "{x}, 5"), (f"Có {X}.5 khách.", "{x}.5"),
	(f"Có {X}: 4 khách.", "{x}: 4"), (f"Có {X} năm liền.", "'năm' sau placeholder"), (f"Cả năm {Z}.", "'năm' trước"),
	(f"Bán lẻ {Z}.", "'lẻ' trước"), (f"Có {X} lần.", "'lần' sau"), (f"Có {X} lẻ.", "'lẻ' sau"),
	(f"Có {X} (cao).", "ngoặc mở sau placeholder"), (f"Nợ ({Z}) triệu.", "đơn vị sau dấu đóng"),
	(f"Nợ {Z}, triệu khách.", "đơn vị sau dấu phẩy"), (f"Nợ {Z}\ntriệu.", "đơn vị đầu dòng sau"),
	(f"12\n{Z}", "chữ số cuối dòng trên"), (f"Có XII {X} khách.", "số La Mã trước"), (f"Có {X} XII khách.", "số La Mã sau"),
	(f"Kho {KHO}{X} đơn.", "chu (giá trị tận cùng bằng chữ số) dính placeholder"),
	(f"Kho {KHO} {X} đơn.", "chu tận cùng bằng chữ số cách placeholder số một dấu cách"),
	(f"Nợ #{Z}.", "'#' trước"), (f"Nợ ~{Z}.", "'~' trước"), (f"Nợ ≈ {Z}.", "'≈' trước"), (f"Nợ {Z}*2.", "'*' sau"),
	(f"Nợ \"-{Z}\".", "dấu trừ trong nháy"), (f"Nợ -({Z}).", "dấu trừ trước ngoặc mở"),
	(f"Nợ {Z} tr.", "'tr' sau"), (f"Nợ {Z} x 2.", "'x' sau"), (f"Tăng {Y} pt.", "'pt' sau"),
	(f"Tăng {Y} điểm.", "'điểm' sau pct"),
	(f"Có {X}, 7 ngày qua chưa thu.", "chữ số (dạng G1 được phép) sau dấu phẩy, không có ngắt câu thật"),
	(f"Có {X}: 2 tuần chưa thu.", "chữ số sau dấu hai chấm"), (f"Có {X}, mười khách.", "từ chỉ số sau dấu phẩy"),
	(f"Có {X}) tá khách.", "từ chỉ số sau dấu đóng"),
]
for body, nhan in G2_LOAI:
	r = rw(body)
	c(f"G2: loại — {nhan}: {body!r}", r["ok"] is False and any(e.startswith("so-tran:") for e in r["errors"]),
		f"{r['ok']} {r['errors']} {r['body']!r}")

print("\n— G1 / G2: tốc độ trên lời 80 KB (tuyến tính) —")
for nhan, fn in (
		("lint 80 KB số đếm viết tay", lambda: render.lint(("có 5 khách, 12 đơn, tuần 3 ; tỷ, XII tỷ. " * 2500)[:80000])),
		("lint 80 KB mã / năm / ngày", lambda: render.lint(("mã KK-2026-002 ngày 5/11/2026 năm 2026 quý 4 " * 2000)[:80000])),
		("lint 80 KB dấu và chữ số xen kẽ", lambda: render.lint(("1;" * 40000)[:80000])),
		("render 80 KB placeholder + ngoặc", lambda: rw((f"Nợ {Z} ({Y}) " * 3000)[:80000])),
		("render placeholder + 80 KB khoảng trắng + tỷ", lambda: rw(f"Nợ {Z}" + " " * 80000 + "tỷ")),
		("render 80 KB chữ liền rồi placeholder", lambda: rw("a" * 80000 + Z)),
		("render 80 KB dấu phẩy giữa placeholder", lambda: rw((f"{X}, " * 4000)[:80000])),
		("render 80 KB từ chỉ số trước placeholder", lambda: rw((f"mười {X} " * 3000)[:80000]))):
	t0 = time.monotonic()
	got = fn()
	dt = time.monotonic() - t0
	c(f"G1/G2: {nhan} < 2 s ({dt:.2f} s)", dt < 2, f"{dt:.2f} s")

# ══ 7f. Vòng sửa 4: H1–H8 (các họ lỗi lọt của lần soát lại thứ ba — verify3) ══════════════════════════════
print("\n— H1–H8: mỗi luật có dòng PHẢI LOẠI và dòng PHẢI NHẬN (lời mô hình qua render_insight) —")


def r4(body="Nội dung.", title="Tiêu đề", advice=(), nguon=None):
	return render.render_insight({"title": title, "body": body, "advice": list(advice)}, PW, None, None, kinds={},
		nguon=nguon)


def h_loai(h, body, ho="so-tran:", **kw):
	r = r4(body, **kw)
	c(f"{h}: loại — {(kw.get('title') or '') + body!r}", r["ok"] is False and any(e.startswith(ho) for e in r["errors"]),
		f"{r['ok']} {r['errors']} {r['body']!r}")


def h_nhan(h, body, **kw):
	r = r4(body, **kw)
	c(f"{h}: nhận — {body!r}", r["ok"] is True and r["errors"] == [], f"{r['errors']} {r['body']!r}")


for body in ("Nhóm khách lớn nợ HAI TỶ.", "Ngân hàng còn Năm Trăm Triệu.", "Phạt tối đa ba mươi TRIỆU.",
		"Ước thêm hai_tỷ chưa ghi sổ.", "Còn hai~tỷ chưa đối chiếu.", "Còn hai*tỷ chưa đối chiếu.",
		"Còn hai`tỷ chưa đối chiếu.", "Riêng NPP nợ hai trieu dong.", "Kênh MT khoảng ba tram trieu.",
		"Dự phòng thêm muoi lam ty.", "Kênh MT chừng chín mươi tr.", "Phí mỗi khách hai mươi k.",
		"Mục tiêu tám mươi ٪.", "Mục tiêu tám mươi per cent.", "Dự phòng thêm five million.",
		"Tức là half phải thu.", "Ước thiệt hại hai vé.", "Chi phí khắc phục năm xị.", "Còn ba lố hàng.",
		"Chỉ ba phần năm đã đóng BHXH.", "Hai phần bảy chưa ký hợp đồng.", "Thiệt hại nhân đôi khi tính hàng hoàn.",
		"Thiệt hại tăng ba lần so với tháng trước.", "Nợ tăng gần hai mươi lần.", "Nợ gap doi cung ky.",
		"Thu được ba đô.", "Còn vài nghìn hộp tồn.", "Bán được mấy chai.", "Khoảng năm ; tỷ chưa thu."):
	h_loai("H1", body)
for body in ("Hai khách lớn nhất chưa trả nợ.", "Kế toán gọi khách hai lần mỗi tuần.", "Cả năm đồng thời tăng tỷ lệ trả.",
		"Ba đồng nghiệp nghỉ phép.", "Một phần nợ đã thu.", "Công nhân hai ca làm thêm.",
		"Đầu tư triển khai kênh mới.", "Ba Đình tăng doanh số.", "Năm nay cần thu gấp."):
	h_nhan("H1", body)
for body in ("Kênh MT khoảng I2O triệu.", "Trả hàng khoảng lOO triệu.", "Mã 1O0 và l00 chưa kiểm.",
		"Có I2O khách mới.", "Đơn IO5 chưa giao."):     # chữ giống số trộn chữ số: là số, không bao giờ là mã
	h_loai("H2", body)
for body in ("Riêng hàng Tết ЗОО triệu.", "Có 4 trӑm khách quá hạn.", "Nhóm lớn hai tу̉ chưa thu.", "Tỷ lệ μ tăng."):
	h_loai("H2", body, ho="chu-la:")
for body in ("Mã TOP10 bán chậm.", "Mã IO chưa kiểm.", "Kế toán đối chiếu ngày đầu tháng."):
	h_nhan("H2", body)
for body in ("Nợ quá hạn 5/11/2026 tỷ.", "Nợ quá hạn 2026/27 tỷ.", "Dự kiến thu 10/2026 triệu.",
		"Nợ quá hạn 5.11.2026 tỷ.", "Riêng mùa Tết 26 tỏi.", "Riêng tháng 10 tỏi rưỡi.", "Số dư TK 131 triệu.",
		"Mã SR900 triệu.", "Kiểm kê tháng 10 lần.", "Năm 2026 đô."):
	h_loai("H3", body)
for body in ("Thu hồi trong 7 ngày.", "Kế hoạch quý 4 năm 2026.", "Tuần 2 vừa qua chưa thu.", "Ca 2, lần thứ 2 kiểm lại.",
		"Năm 2026 đồng thời mở kênh mới."):
	h_nhan("H3", body)
for body in ("Chốt ngày 5/11.", "Xấp xỉ 1/2 phải thu.", "Mục tiêu 9/10 đơn.", "Hạn 5/11/26.", "Hạn 30/2/2026."):
	h_loai("H4", body)
for body in ("Chốt ngày 5/11/2026.", "Trực 24/7.", "Kỳ 10/2026 và ngày 05.11.2026."):
	h_nhan("H4", body)
NG4 = json.dumps({"pack": {"kho": {"phieu": ["KK-2026-002", "SR900"]}}, "ghi_chu": "dòng\nKK-2026-003"},
	ensure_ascii=False)
for body in ("Khách KH-0099 nợ lâu nhất.", "Nợ xấu nằm ở SL-350 khách nhỏ.", "Mã AB12 bán chậm.", "Mã SR90 bán chậm.",
		"Phiếu KK-2026-0021 chưa duyệt."):
	h_loai("H5", body, nguon=NG4)
for body in ("Phiếu KK-2026-002 chưa duyệt.", "Mã SR900 bán chậm.", "Phiếu KK-2026-003 chưa duyệt.",
		"Kỳ T10, Q3/2026, chuẩn ISO 22000.", "Phiếu KK-2026-002."):
	h_nhan("H5", body, nguon=NG4)
h_nhan("H5 (nguon=None: không xét — lời quy tắc, gọi trực tiếp)", "Khách KH-0099 nợ lâu nhất.")
h_loai("H6", "Nội dung.", title=f"Mã {KHO}\nNghìn hộp tồn")
h_loai("H6", "Nội dung.", advice=[f"Kho xả mã {KHO}\nTrăm hộp trong tuần."])
# gộp dòng TRƯỚC khi soát: "{{…}}\ntrừ …" ở thân là xuống dòng (được), ở tiêu đề / khuyến nghị là "{{…}} trừ" (bị loại)
h_loai("H6", "Nội dung.", title=f"Có {X}\ntrừ hàng hoàn")
h_loai("H6", "Nội dung.", advice=[f"Kế toán thu {X}\ncộng dồn trong tuần."])
for body in (f"Đang làm {NSD}\nNghìn người chưa đóng.", f"Mã {KHO}\nNăm hộp.", f"Mã {KHO}\n- Trăm hộp.",
		f"Mã {KHO}\n1. Trăm hộp.", f"Mã {KHO}\n12 hộp.", f"Có {X},\nNghìn khách.", f"Có {X}\ntriệu khách."):
	h_loai("H6", body)
for body in (f"Có {X} khách.\nKế toán gọi từng khách.", f"Mã {KHO}\nKho kiểm lại.", f"Có {X} khách. Nghìn việc phải làm."):
	h_nhan("H6", body)
r = r4("Nội dung.", title=f"Mã {MA}\n  còn hàng")
eq("H6: tiêu đề gộp một dòng TRƯỚC khi soát (thứ được soát là thứ được hiện)", (r["ok"], r["title"]),
	(True, "Mã TET1 còn hàng"))
for body in (f"Doanh thu xuất khẩu {X} đô.", f"Khách mua {X} yên hàng mẫu.", f"Thu {X} đồng bằng tiền mặt.",
		f"Khách trả {X2} đồng đều mỗi tháng.", f"Thu {X} đồng loạt.", f"Còn {Z} bảng Anh.", f"Còn {X} nhân dân tệ.",
		f"Còn {X} euro.", f"Đơn chờ giao {VCG} lố.", f"Còn {X} dong."):
	h_loai("H7", body)
for body in (f"Có {X} đồng hồ đo.", f"Có {X} đồng nghiệp nghỉ.", f"Có {X} đô thị mới.", f"Có {X} xu hướng mới.",
		f"Nợ {Z}, đồng nghĩa với rủi ro cao.", f"Vùng {NHAN} đồng bằng tăng."):
	h_nhan("H7", body)
for body in ("Có XII khách mới.", "XV mẫu chưa kiểm.", "Còn XX đơn.", "Có II kho lệch."):
	h_loai("H8", body)
for body in ("Kết quả quý IV tốt.", "Giai đoạn II đã xong.", "Thế kỷ XX.", "Lần thứ III kiểm lại.", "QĐ II đã ban hành.",
		"Kho CV và MC đủ hàng.", "Mã XV-2026 chưa duyệt."):
	h_nhan("H8", body)

print("\n— H1–H8: tốc độ (lượt mới tuyến tính, lời 80 KB < 2 s) —")
NG_DAI = json.dumps({"rows": [{"ma": f"MA-{i:05d}", "qty": i} for i in range(6000)]})
for nhan, fn in (
		("lint 80 KB từ chỉ số + dấu", lambda: render.lint(("hai ; ba _ năm ~ " * 6000)[:80000])),
		("lint 80 KB từ chỉ số + đơn vị", lambda: render.lint(("hai mươi lăm triệu, " * 5000)[:80000])),
		("lint 80 KB số La Mã", lambda: render.lint(("XII khách quý IV " * 5000)[:80000])),
		("lint 80 KB chữ giống số", lambda: render.lint(("I2O lOO triệu " * 6000)[:80000])),
		("render 80 KB chữ Kirin", lambda: rw(("Ж" * 80000))),
		("render 80 KB ngày + đơn vị", lambda: rw(("5/11/2026 tỷ tháng 10 tỏi " * 3000)[:80000])),
		("render 80 KB placeholder + xuống dòng + từ chỉ số", lambda: rw((f"{X}\nNghìn " * 3000)[:80000])),
		("render 80 KB mã khác nhau + đề bài 120 KB (H5)", lambda: r4(" ".join(f"AB{i}" for i in range(16000))[:80000],
			nguon=NG_DAI)),
		("render 80 KB mã có trong đề bài (H5)", lambda: r4(("MA-00001 " * 9000)[:80000], nguon=NG_DAI))):
	t0 = time.monotonic()
	got = fn()
	dt = time.monotonic() - t0
	c(f"H: {nhan} < 2 s ({dt:.2f} s)", dt < 2, f"{dt:.2f} s")
for nhan, unit in (("'1/' lặp", "1/"), ("'1-' lặp", "1-")):
	body = (unit * 40001)[:80000]
	t0 = time.monotonic()
	r = render.render_insight({"title": "T", "body": body, "advice": [body[:20000]]}, PW, None, None, kinds={})
	dt = time.monotonic() - t0
	c(f"H: render 80 KB {nhan} (+ 20 KB khuyến nghị) < 1 s ({dt:.2f} s), loại", dt < 1 and r["ok"] is False, f"{dt:.2f} s")

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
