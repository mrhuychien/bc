"""Trợ lý AI — quy tắc nhóm Kinh doanh (bc.ai.rules.kd): kd.tang_truong_am, kd.tra_hang_cao, kd.kenh_sut,
tet.npp_tut, tet.cham_muc_tieu (đặc tả §4.1) + đề xuất KPI của 6 mảng kinh doanh.

A–C chạy trên PAYLOAD THẬT: seed_ui.sales (hoá đơn theo kênh) + hoá đơn riêng của bộ thử này (tiền tố RKD- / TET-),
gọi bc.api.kd / bc.api.tet thật để dựng pack rồi chạy quy tắc; hai mốc "hôm nay": 27/10/2026 (giữa hai mùa Tết) và
15/12/2026 (trong mùa). D–I là pack DỰNG TAY: mỗi quy tắc có ca vàng, đỏ, không báo, đúng ngưỡng, ngưỡng ghi đè,
tắt, khối nguồn thiếu / _error / available False, giá trị None / rỗng / rác, khoá nhiều tín hiệu ổn định.
J: AST (không frappe, không SQL), riêng tư, khai báo quy tắc. Số kỳ vọng TÍNH TAY (phép tính ghi cạnh).

Chạy: BC_TEST_DB=bc_test_ai_rkd python3 -B test_ai_rules_kd.py
"""
import ast
import copy
import datetime
import os
import re

from seed import Check, bc_settings, insert, reset, single
from paths import BC_ROOT

import frappe  # noqa: E402  (giả)
import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.kd")

import seed_ui  # noqa: E402
import test_channel  # noqa: E402

c = Check()
TR = 1_000_000
KD = ("kd.tang_truong_am", "kd.tra_hang_cao", "kd.kenh_sut", "tet.npp_tut", "tet.cham_muc_tieu")
S, C, T = "tong-quan.summary", "tong-quan.channels", "tet.npp_growth"
MOI = []            # mọi (tín hiệu, pack) đã sinh trong cả bộ thử — soát chung ở mục J
TEN_KHACH = ["NPP An Phát", "NPP Bình Minh", "NPP Cường Thịnh", "NPP Đại Lộc", "NPP Én Nhỏ", "NPP Phú Quý",
	"NPP Gia Hưng", "NPP Hà Nội", "Co.op Mart", "Đại lý Một", "Đại lý Hai", "Đại lý Ba", "Đại lý Bốn"]


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def A(key, name):
	"""Path của số quy tắc tự tính: <mảng>._ai.<khoá đã đổi ký tự lạ>.<tên>."""
	return f"{registry.RULES[key.split(':')[0]].section}._ai.{registry.slug(key)}.{name}"


def P(path, kind):
	return "{{" + f"{path}|{kind}" + "}}"


def chay(pack, only=KD, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def mot(pack, key, ov=None):
	"""Chạy MỘT quy tắc trên bản sao pack → (RuleRun, {khoá tín hiệu: Signal}, pack đã chạy)."""
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


def muc(pack, key, ov=None):
	"""Mức của tín hiệu duy nhất của quy tắc (None = chạy được nhưng không báo; 'KHONG-CHAY' = không chạy được)."""
	run, sig, _ = mot(pack, key, ov)
	if key not in run.ran:
		return "KHONG-CHAY"
	return sig[key].severity if key in sig else (None if not sig else sorted(sig))


def tinh(sig, pack, name):
	return registry.resolve(pack, A(sig.key, name), "THIEU")


# ═══ Seed thật ═══════════════════════════════════════════════════════════════
def hd(name, date, group, customer, amount, ten=None, item_group="Hàng truyền thống", ret=0, **kw):
	"""Một hoá đơn bán (ret=1: trả hàng, số âm như ERPNext) + một dòng hàng."""
	sign = -1 if ret else 1
	insert("Sales Invoice", name=name, docstatus=kw.pop("docstatus", 1), posting_date=date, posting_time="09:00:00",
		customer=customer, customer_name=ten or customer, customer_group=group, net_total=sign * amount,
		grand_total=sign * amount * 1.08, is_return=ret, is_opening=kw.pop("is_opening", "No"), company="HGC")
	insert("Sales Invoice Item", parent=name, parenttype="Sales Invoice", parentfield="items", idx=1,
		item_code="TET1" if item_group == "Hàng Tết" else "TRAD1", item_name="Bánh", item_group=item_group,
		qty=sign * 10, stock_qty=sign * 10, net_amount=sign * amount, amount=sign * amount, uom="Hộp", docstatus=1)


def seed():
	bc_settings()
	for n, p, l, r in test_channel.GROUPS:
		insert("Customer Group", name=n, customer_group_name=n, parent_customer_group=p, lft=l, rgt=r,
			is_group=int(r - l > 1))
	single("PKD Settings", kenh_npp="Nhà phân phối", kenh_mt="Siêu thị", kenh_dulich="Du lịch",
		kenh_showroom="Showroom")
	# 1. seed_ui.sales: mỗi nhóm 5 hoá đơn năm TC này (12/5, 3/7, 15/9, 26/10, 27/10/2026) + 2 hoá đơn cùng kỳ
	#    (10/6, 20/10/2025): NPP 90 tr, Co.op 45 tr, Du lịch 12 tr, Showroom HN 6 tr, Khách lẻ 2 tr mỗi hoá đơn.
	seed_ui.sales()
	# 2. Thêm cho quy tắc tổng quan (cùng kỳ năm trước cao hơn năm nay; trả hàng năm nay tăng)
	hd("RKD-1", "2025-08-01", "NPP", "NPP Hà Nội", 400 * TR)
	hd("RKD-2", "2025-08-01", "Co.op", "Co.op Mart", 210 * TR)
	hd("RKD-3", "2025-08-01", "Du lịch", "Lữ hành Sao", 60 * TR)
	hd("RKD-4", "2026-10-10", "NPP", "NPP Hà Nội", 31 * TR, ret=1)
	hd("RKD-5", "2025-09-05", "Co.op", "Co.op Mart", 9.8 * TR, ret=1)
	hd("RKD-6", "2026-08-08", "NPP", "NPP Hà Nội", 999 * TR, is_opening="Yes")      # số dư đầu kỳ: không tính
	hd("RKD-7", "2026-08-09", "NPP", "NPP Hà Nội", 500 * TR, docstatus=2)           # đã huỷ: không tính
	# 3. Hàng Tết kênh NPP. Mùa 2027: 01/11/2026 → 15/12/2026, cùng kỳ 01/11/2025 → 15/12/2025 (theo lịch dương).
	tet = lambda n, d, kh, ten, tien, **kw: hd(n, d, kw.pop("group", "NPP"), kh, tien * TR, ten=ten,  # noqa: E731
		item_group=kw.pop("item_group", "Hàng Tết"), **kw)
	tet("TET-A1", "2025-11-20", "KH-A", "NPP An Phát", 200)
	tet("TET-A2", "2026-01-10", "KH-A", "NPP An Phát", 500)          # mùa trước nhưng SAU cùng kỳ → không vào last_year
	tet("TET-A3", "2026-11-20", "KH-A", "NPP An Phát", 120)
	tet("TET-A4", "2026-12-01", "KH-A", "NPP An Phát", 20, ret=1)    # trả về mùa này → this_year = 120 − 20
	tet("TET-A5", "2026-11-21", "KH-A", "NPP An Phát", 700, item_group="Hàng truyền thống")   # không phải hàng Tết
	tet("TET-B1", "2025-12-01", "KH-B", "NPP Bình Minh", 150)
	tet("TET-B2", "2026-12-05", "KH-B", "NPP Bình Minh", 100)
	tet("TET-C1", "2025-11-15", "KH-C", "NPP Cường Thịnh", 100)      # đúng mốc 100 tr
	tet("TET-C2", "2026-11-15", "KH-C", "NPP Cường Thịnh", 79)
	tet("TET-D1", "2025-12-15", "KH-D", "NPP Đại Lộc", 300)          # đúng ngày cùng kỳ (tính)
	tet("TET-D2", "2025-12-16", "KH-D", "NPP Đại Lộc", 900)          # sau cùng kỳ 1 ngày (không tính)
	tet("TET-D3", "2026-12-15", "KH-D", "NPP Đại Lộc", 240)          # đúng hôm nay (tính)
	tet("TET-E1", "2025-12-12", "KH-E", "NPP Én Nhỏ", 50)            # năm trước dưới 100 tr
	tet("TET-E2", "2026-12-12", "KH-E", "NPP Én Nhỏ", 10)
	tet("TET-F1", "2025-11-25", "KH-F", "NPP Phú Quý", 100)
	tet("TET-F2", "2026-11-25", "KH-F", "NPP Phú Quý", 400)
	tet("TET-G1", "2026-12-14", "KH-G", "NPP Gia Hưng", 30)          # NPP mới: năm trước 0
	tet("TET-M1", "2025-12-01", "KH-M", "Co.op Mart", 500, group="Co.op")     # kênh MT: không vào npp_growth
	tet("TET-M2", "2026-12-01", "KH-M", "Co.op Mart", 100, group="Co.op")
	# 4. Mùa 2025 (trước nữa) — để ở mốc 27/10/2026 (giữa hai mùa, mùa 2026 đã khoá) có 3 NPP đang "tụt"
	tet("TET-A0", "2024-12-01", "KH-A", "NPP An Phát", 1000)
	tet("TET-B0", "2024-12-01", "KH-B", "NPP Bình Minh", 400)
	tet("TET-C0", "2024-12-01", "KH-C", "NPP Cường Thịnh", 300)


GOI = (("tong-quan", "summary", "kd.get_summary"), ("tong-quan", "channels", "kd.get_channels"),
	("tong-quan", "item_groups", "kd.get_item_groups"), ("tong-quan", "top_customers", "kd.get_top_customers"),
	("ngay", "daily", "kd.get_daily"), ("thang", "monthly", "kd.get_monthly"),
	("tet", "npp_growth", "tet.get_npp_growth"), ("tet", "items", "tet.get_items"),
	("tinh-thanh", "provinces", "kd.get_provinces"), ("san-pham", "top_products", "kd.get_top_products"))


def pack_that(today):
	"""Pack 6 mảng kinh doanh từ method THẬT (đúng tham số bảng §3 của đặc tả) tại mốc `today`."""
	frappe.utils.FAKE_TODAY = today
	frappe.cache().store.clear()
	pack = {}
	for mang, ten, method in GOI:
		kw = {"year": today.year, "month": today.month} if method == "kd.get_daily" else (
			{"group": "all"} if method == "kd.get_top_products" else {})
		pack.setdefault(mang, {})[ten] = ai_testlib.goi(method, **kw)
	return pack


def dong(pack, block, **khop):
	"""Chỉ số của dòng đầu tiên khớp mọi cặp khoá = giá trị trong <block>.rows."""
	rows = registry.resolve(pack, f"{block}.rows")
	return next(i for i, r in enumerate(rows) if all(r.get(k) == v for k, v in khop.items()))


# ═══ A. Payload thật, 27/10/2026 (giữa hai mùa Tết) ═══════════════════════════
print("A. Payload thật — 27/10/2026: quy tắc tổng quan")
reset()
seed()
p1 = pack_that(datetime.date(2026, 10, 27))
c("mọi khối là payload thật (không lỗi)", all(isinstance(b, dict) and "rows" in b and "meta" in b
	for m in p1.values() for b in m.values()), {m: list(v) for m, v in p1.items()})
DOC = [f"{S}.meta.growth.net", f"{S}.rows[0].period", f"{S}.rows[0].net", f"{S}.rows[0].return_rate",
	f"{S}.rows[0].returns", f"{S}.rows[1].net", f"{S}.rows[1].return_rate", f"{C}.rows[0].period",
	f"{C}.rows[0].channel_key", f"{C}.rows[0].channel", f"{C}.rows[0].sales", f"{C}.rows[14].sales",
	f"{T}.meta.between_seasons", f"{T}.meta.target_pct", f"{T}.meta.asof", f"{T}.rows[0].customer",
	f"{T}.rows[0].this_year", f"{T}.rows[0].last_year", f"{T}.rows[0].growth_pct"]
eq("mọi path quy tắc đọc đều có trên payload thật", [p for p in DOC if not registry.has(p1, p)], [])
eq("summary: 3 kỳ đúng thứ tự", [r["period"] for r in p1["tong-quan"]["summary"]["rows"]],
	["current", "same_period", "last_year"])
eq("channels: 3 kỳ × 5 kênh", [(r["period"], r["channel_key"]) for r in p1["tong-quan"]["channels"]["rows"]],
	[(p, k) for p in ("current", "same_period", "last_year") for k in ("npp", "mt", "dulich", "showroom", "khac")])
# Số nền (tính tay từ seed):
#   năm nay  : bán 5 × (90 + 45 + 12 + 6 + 2) = 775 tr; trả 31 tr; thực bán 744 tr; tỷ lệ trả 31 / 775 = 4,0%
#   cùng kỳ  : bán 2 × 155 + 400 + 210 + 60 = 980 tr; trả 9,8 tr; thực bán 970,2 tr; tỷ lệ trả 9,8 / 980 = 1,0%
#   tăng trưởng thực bán (744 − 970,2) / 970,2 = −23,31…% → −23,3
tq = p1["tong-quan"]["summary"]
eq("nền: năm nay", {k: tq["rows"][0][k] for k in ("sales", "returns", "net", "return_rate")},
	{"sales": 775 * TR, "returns": 31 * TR, "net": 744 * TR, "return_rate": 4.0})
eq("nền: cùng kỳ", {k: tq["rows"][1][k] for k in ("sales", "returns", "net", "return_rate")},
	{"sales": 980 * TR, "returns": 9.8 * TR, "net": 970.2 * TR, "return_rate": 1.0})
eq("nền: growth.net", tq["meta"]["growth"]["net"], -23.3)

r1 = chay(p1)
s1 = {s.key: s for s in r1.signals}
eq("không quy tắc nào hỏng", (r1.not_run, sorted(r1.ran)), ({}, sorted(KD)))
eq("tín hiệu sinh ra", sorted(s1), ["kd.kenh_sut:mt", "kd.kenh_sut:npp", "kd.tang_truong_am", "kd.tra_hang_cao"])

s = s1["kd.tang_truong_am"]
eq("tang_truong_am: đỏ (−23,3 < −20)", s.severity, "do")
eq("tang_truong_am: mức giảm tự tính = 23,3", tinh(s, p1, "giam"), 23.3)
eq("tang_truong_am: lời", s.title, f"Thực bán giảm {P(A(s.key, 'giam'), 'pct')} so với cùng kỳ năm trước")
eq("tang_truong_am: thân nêu thực bán hai kỳ", s.detail, f"Từ đầu năm tài chính thực bán {P(S + '.rows[0].net', 'tien')}, "
	f"cùng kỳ năm trước {P(S + '.rows[1].net', 'tien')}; cần xem kênh và nhóm hàng nào kéo xuống.")
eq("tang_truong_am: paths", s.paths, [f"{S}.meta.growth.net", f"{S}.rows[0].net", f"{S}.rows[1].net",
	A(s.key, "giam")])
eq("tang_truong_am: mảng / route / người xem / rule", (s.section, s.route, s.audience, s.rule),
	("tong-quan", "#/tong-quan", "lanh-dao", "kd.tang_truong_am"))

s = s1["kd.tra_hang_cao"]
eq("tra_hang_cao: vàng (4,0 > 3; cao hơn cùng kỳ 4,0 − 1,0 = 3,0 điểm; chưa quá 5)", s.severity, "vang")
eq("tra_hang_cao: chênh tự tính = 3,0", tinh(s, p1, "chenh"), 3.0)
eq("tra_hang_cao: lời", s.title, f"Hàng trả về chiếm {P(S + '.rows[0].return_rate', 'pct')} doanh số bán ra")
eq("tra_hang_cao: thân", s.detail, f"Cao hơn cùng kỳ năm trước {P(A(s.key, 'chenh'), 'so')} điểm (cùng kỳ "
	f"{P(S + '.rows[1].return_rate', 'pct')}); hàng trả về từ đầu năm tài chính trị giá "
	f"{P(S + '.rows[0].returns', 'tien')}.")

# Kênh (doanh số BÁN RA, chưa trừ trả):
#   npp     450 vs 180 + 400 = 580 → (450 − 580) / 580 = −22,41% → giảm 22,4; tỷ trọng 450 / 775 = 58,1%; cùng kỳ 580 / 980 = 59,2%
#   mt      225 vs  90 + 210 = 300 → −25,0%; tỷ trọng 225 / 775 = 29,0%; cùng kỳ 300 / 980 = 30,6%
#   dulich   60 vs  24 +  60 =  84 → −28,57% → giảm 28,6 NHƯNG tỷ trọng 60 / 775 = 7,7% và 84 / 980 = 8,6% (< 10) → không báo
#   showroom 30 vs 12, khac 10 vs 4 → tăng
s = s1["kd.kenh_sut:npp"]
i_nay, i_truoc = dong(p1, C, period="current", channel_key="npp"), dong(p1, C, period="same_period", channel_key="npp")
eq("kenh_sut npp: vàng, giảm 22,4 (theo BÁN RA 450 / 580, không phải thực bán 419 / 580 = 27,8)",
	(s.severity, tinh(s, p1, "giam")), ("vang", 22.4))
eq("kenh_sut npp: tỷ trọng năm nay 58,1 / cùng kỳ 59,2", (tinh(s, p1, "ty_trong"), tinh(s, p1, "ty_trong_cung_ky")),
	(58.1, 59.2))
eq("kenh_sut npp: lời", s.title, f"Kênh {P(f'{C}.rows[{i_nay}].channel', 'chu')} giảm "
	f"{P(A(s.key, 'giam'), 'pct')} doanh số so với cùng kỳ")
eq("kenh_sut npp: thân", s.detail, f"Từ đầu năm tài chính kênh này bán {P(f'{C}.rows[{i_nay}].sales', 'tien')}, "
	f"cùng kỳ năm trước {P(f'{C}.rows[{i_truoc}].sales', 'tien')}; kênh đang chiếm "
	f"{P(A(s.key, 'ty_trong'), 'pct')} doanh số cả công ty.")
eq("kenh_sut npp: số trên path đúng số nền", [registry.resolve(p1, f"{C}.rows[{i}].sales") for i in (i_nay, i_truoc)],
	[450 * TR, 580 * TR])
eq("kenh_sut npp: tên kênh", registry.resolve(p1, f"{C}.rows[{i_nay}].channel"), "NPP")
s = s1["kd.kenh_sut:mt"]
eq("kenh_sut mt: vàng, giảm 25,0; tỷ trọng 29,0 / 30,6", (s.severity, tinh(s, p1, "giam"), tinh(s, p1, "ty_trong"),
	tinh(s, p1, "ty_trong_cung_ky")), ("vang", 25.0, 29.0, 30.6))
c("kenh_sut: Du lịch giảm 28,6% nhưng dưới 10% doanh số → không báo", "kd.kenh_sut:dulich" not in s1, sorted(s1))

print("\nB. Payload thật — 27/10/2026: giữa hai mùa Tết")
# Mùa 2026 đã khoá (01/11/2025 → 17/02/2026) so 01/11/2024 → 17/02/2025:
#   KH-A 200 + 500 = 700 vs 1000 → −30,0; KH-B 150 vs 400 → −62,5; KH-C 100 vs 300 → −66,7 (3 NPP đủ điều kiện tụt)
m1 = p1["tet"]["npp_growth"]["meta"]
eq("meta: giữa hai mùa, mùa 2026 đã khoá", (m1["between_seasons"], m1["tet_year"], m1["asof"]), (True, 2026, "2026-02-17"))
nt1 = {r["customer_id"]: (r["this_year"], r["last_year"], r["growth_pct"]) for r in p1["tet"]["npp_growth"]["rows"]}
eq("nền: 3 NPP đang tụt ở mùa đã khoá", [nt1.get(k) for k in ("KH-A", "KH-B", "KH-C")],
	[(700 * TR, 1000 * TR, -30.0), (150 * TR, 400 * TR, -62.5), (100 * TR, 300 * TR, -66.7)])
c("giữa hai mùa: quy tắc Tết CHẠY nhưng không báo", {"tet.npp_tut", "tet.cham_muc_tieu"} <= r1.ran
	and not [k for k in s1 if k.startswith("tet.")], (sorted(r1.ran), sorted(s1)))
p1b = copy.deepcopy(p1)
p1b["tet"]["npp_growth"]["meta"]["between_seasons"] = False
r1b, s1b, p1b = mot(p1b, "tet.npp_tut")
eq("đối chứng: cùng số đó mà đang trong mùa → báo 3 NPP, hụt 300 + 250 + 200 = 750 tr",
	(sorted(s1b), tinh(s1b["tet.npp_tut"], p1b, "so_npp"), tinh(s1b["tet.npp_tut"], p1b, "hut")),
	(["tet.npp_tut"], 3, 750 * TR))

# ═══ C. Payload thật, 15/12/2026 (trong mùa Tết 2027) ═════════════════════════
print("\nC. Payload thật — 15/12/2026: trong mùa Tết")
p2 = pack_that(datetime.date(2026, 12, 15))
eq("mọi path quy tắc đọc đều có (mốc trong mùa)", [p for p in DOC if not registry.has(p2, p)], [])
m2 = p2["tet"]["npp_growth"]["meta"]
eq("meta: trong mùa 2027, tính đến 15/12, cùng kỳ đến 15/12/2025, mục tiêu 20%", (m2["between_seasons"], m2["tet_year"],
	m2["season_start"], m2["asof"], m2["ly_asof"], m2["target_pct"]), (False, 2027, "2026-11-01", "2026-12-15",
	"2025-12-15", 20.0))
# NPP (năm nay / cùng kỳ / tăng trưởng):
#   KH-A 120 − 20 = 100 / 200 / −50,0   tụt, hụt 100      (500 tr ngày 10/01/2026 nằm sau cùng kỳ → không tính)
#   KH-B 100 / 150 / −33,3              tụt, hụt 50
#   KH-C  79 / 100 / −21,0              tụt, hụt 21       (năm trước đúng mốc 100 tr)
#   KH-D 240 / 300 / −20,0              KHÔNG (đúng 20%, phải giảm QUÁ 20%; 900 tr ngày 16/12/2025 không tính)
#   KH-E  10 /  50 / −80,0              KHÔNG (năm trước dưới 100 tr)
#   KH-F 400 / 100 / +300,0             tăng
#   KH-G  30 /   0 / None               NPP mới
#   Tổng năm nay 100 + 100 + 79 + 240 + 10 + 400 + 30 = 959; cùng kỳ 200 + 150 + 100 + 300 + 50 + 100 = 900
#   tăng trưởng 59 / 900 = 6,555…% → 6,6; thiếu so mục tiêu 20 − 6,6 = 13,4 điểm → vàng (≥ 10, < 20)
nt2 = {r["customer_id"]: (r["this_year"], r["last_year"], r["growth_pct"]) for r in p2["tet"]["npp_growth"]["rows"]}
eq("nền: 7 NPP (kênh MT không vào)", nt2, {"KH-A": (100 * TR, 200 * TR, -50.0), "KH-B": (100 * TR, 150 * TR, -33.3),
	"KH-C": (79 * TR, 100 * TR, -21.0), "KH-D": (240 * TR, 300 * TR, -20.0), "KH-E": (10 * TR, 50 * TR, -80.0),
	"KH-F": (400 * TR, 100 * TR, 300.0), "KH-G": (30 * TR, 0.0, None)})
r2 = chay(p2)
s2 = {s.key: s for s in r2.signals}
eq("không quy tắc nào hỏng (mốc trong mùa)", (r2.not_run, sorted(r2.ran)), ({}, sorted(KD)))
c("có đủ hai tín hiệu Tết, mỗi quy tắc MỘT tín hiệu (gộp)", sorted(k for k in s2 if k.startswith("tet.")) ==
	["tet.cham_muc_tieu", "tet.npp_tut"], sorted(s2))
iA, iB, iC = (dong(p2, T, customer_id=k) for k in ("KH-A", "KH-B", "KH-C"))
s = s2["tet.npp_tut"]
eq("npp_tut: vàng, 3 NPP (A, B, C)", (s.severity, tinh(s, p2, "so_npp")), ("vang", 3))
eq("npp_tut: hụt 100 + 50 + 21 = 171 tr; năm nay 279 tr; cùng kỳ 450 tr", (tinh(s, p2, "hut"), tinh(s, p2, "nam_nay"),
	tinh(s, p2, "nam_truoc")), (171 * TR, 279 * TR, 450 * TR))
eq("npp_tut: lời", s.title, f"{P(A(s.key, 'so_npp'), 'so')} NPP lớn giảm mua hàng Tết hơn "
	f"{P(A(s.key, 'nguong_giam'), 'pct')} so cùng kỳ")
neu = ", ".join(f"{P(f'{T}.rows[{i}].customer', 'chu')} ({P(f'{T}.rows[{i}].growth_pct', 'pct')})" for i in (iA, iB, iC))
eq("npp_tut: thân nêu A, B, C theo số tiền hụt giảm dần — tên chỉ qua placeholder", s.detail,
	f"Các NPP này mua ít hơn cùng kỳ năm trước tổng cộng {P(A(s.key, 'hut'), 'tien')}; hụt nhiều nhất: {neu}.")
eq("npp_tut: tên trên path là tên khách thật", [registry.resolve(p2, f"{T}.rows[{i}].customer") for i in (iA, iB, iC)],
	["NPP An Phát", "NPP Bình Minh", "NPP Cường Thịnh"])
eq("npp_tut: paths = 4 path / NPP + số tự tính có trong lời", s.paths, [f"{T}.rows[{i}].{k}" for i in (iA, iB, iC)
	for k in ("growth_pct", "this_year", "last_year", "customer")] + [A(s.key, "so_npp"), A(s.key, "nguong_giam"),
	A(s.key, "hut")])
eq("npp_tut: mảng / route", (s.section, s.route, s.audience), ("tet", "#/tet", "lanh-dao"))
s = s2["tet.cham_muc_tieu"]
eq("cham_muc_tieu: vàng; tăng trưởng 6,6; thiếu 13,4 điểm", (s.severity, tinh(s, p2, "tang_truong"), tinh(s, p2, "thieu")),
	("vang", 6.6, 13.4))
eq("cham_muc_tieu: năm nay 959 tr, cùng kỳ 900 tr", (tinh(s, p2, "nam_nay"), tinh(s, p2, "nam_truoc")),
	(959 * TR, 900 * TR))
eq("cham_muc_tieu: lời", s.title, f"Hàng Tết kênh NPP tăng trưởng {P(A(s.key, 'tang_truong'), 'pct')}, mục tiêu "
	f"{P(T + '.meta.target_pct', 'pct')}")
eq("cham_muc_tieu: thân", s.detail, f"Thấp hơn mục tiêu {P(A(s.key, 'thieu'), 'so')} điểm: mùa này NPP mua "
	f"{P(A(s.key, 'nam_nay'), 'tien')}, cùng kỳ năm trước {P(A(s.key, 'nam_truoc'), 'tien')} (tính đến "
	f"{P(T + '.meta.asof', 'ngay')}).")
# Kênh MT ở mốc 15/12: năm nay 225 + 100 (TET-M2) = 325; cùng kỳ (đến 15/12/2025) 300 + 500 (TET-M1) = 800
#   → (325 − 800) / 800 = −59,375% → −59,4
eq("kenh_sut mt ở mốc 15/12: giảm 59,4", tinh(s2["kd.kenh_sut:mt"], p2, "giam") if "kd.kenh_sut:mt" in s2 else None, 59.4)
for ten, pk, run in (("27/10", p1, r1), ("15/12", p2, r2)):
	eq(f"mọi tín hiệu trên payload thật ({ten}) có lời dựng được", {s.key: ai_testlib.kiem_loi(s, pk)
		for s in run.signals if ai_testlib.kiem_loi(s, pk)}, {})

print("\nC2. KPI đề xuất có thật trên payload và là số")
KPIS = [
	(f"{S}.rows[0].sales", "tien", "Doanh số bán ra từ đầu năm tài chính"),
	(f"{S}.rows[0].returns", "tien", "Hàng trả về từ đầu năm tài chính"),
	(f"{S}.rows[0].net", "tien", "Thực bán từ đầu năm tài chính"),
	(f"{S}.rows[0].return_rate", "pct", "Tỷ lệ trả hàng"),
	(f"{S}.meta.growth.sales", "pct", "Tăng trưởng doanh số so cùng kỳ"),
	(f"{S}.meta.growth.net", "pct", "Tăng trưởng thực bán so cùng kỳ"),
	(f"{C}.rows[0].sales", "tien", "Doanh số kênh NPP từ đầu năm tài chính"),
	(f"{C}.rows[1].sales", "tien", "Doanh số kênh MT từ đầu năm tài chính"),
	("tinh-thanh.provinces.rows[0].pct", "pct", "Tỷ trọng doanh số của tỉnh đứng đầu"),
]
for pk in (p1, p2):
	eq("KPI: path có thật và giá trị là số", [p for p, _k, _l in KPIS if not registry.has(pk, p)
		or isinstance(registry.resolve(pk, p), bool) or not isinstance(registry.resolve(pk, p), (int, float))], [])
eq("KPI: kiểu hợp lệ, mảng thuộc nhóm kinh-doanh", [p for p, k, _l in KPIS if k not in registry.KINDS
	or registry.group_of(registry.section_of(p)) != "kinh-doanh"], [])
eq("KPI: chỉ số dòng cố định đúng nghĩa (rows[0] = năm nay; kênh 0 = NPP, 1 = MT)",
	(p2["tong-quan"]["summary"]["rows"][0]["period"], [(r["period"], r["channel_key"])
		for r in p2["tong-quan"]["channels"]["rows"][:2]]), ("current", [("current", "npp"), ("current", "mt")]))
eq("KPI: giá trị ở mốc 27/10 (tính tay ở mục A)", [registry.resolve(p1, p) for p, _k, _l in KPIS[:8]],
	[775 * TR, 31 * TR, 744 * TR, 4.0, -20.9, -23.3, 450 * TR, 225 * TR])     # (775 − 980) / 980 = −20,9
old = registry.KPIS
registry.KPIS = KPIS
eq("KPI: snapshot_kpis lấy đủ 9 số", sorted(registry.snapshot_kpis(p1)), sorted(p for p, _k, _l in KPIS))
registry.KPIS = old
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 27)


# ═══ Pack dựng tay ════════════════════════════════════════════════════════════
def tq_pack(growth, tl=4.0, tl_truoc=2.0, dao=False, **doi):
	"""tong-quan.summary dựng tay — đúng hình payload kd.get_summary."""
	rows = [{"period": "current", "sales": 1000 * TR, "returns": 40 * TR, "net": 960 * TR, "return_rate": tl},
		{"period": "same_period", "sales": 900 * TR, "returns": 18 * TR, "net": 882 * TR, "return_rate": tl_truoc},
		{"period": "last_year", "sales": 2000 * TR, "returns": 30 * TR, "net": 1970 * TR, "return_rate": 1.5}]
	rows[0].update(doi)
	if dao:
		rows.reverse()
	return {"tong-quan": {"summary": {"rows": rows, "meta": {"growth": {"sales": 11.1, "returns": None,
		"net": growth}}}}}


KENH = (("npp", "NPP"), ("mt", "MT"), ("dulich", "Du lịch"), ("showroom", "Showroom"), ("khac", "Khác"))


def kenh_pack(nay, truoc, dao=False):
	"""tong-quan.channels dựng tay (triệu đồng theo kênh) — đúng hình payload kd.get_channels: 3 kỳ × 5 kênh."""
	rows = [{"period": p, "channel": ten, "channel_key": k, "sales": d.get(k, 0) * TR, "returns": 0.0,
		"net": d.get(k, 0) * TR, "return_rate": 0.0}
		for p, d in (("current", nay), ("same_period", truoc), ("last_year", truoc)) for k, ten in KENH]
	if dao:
		rows.reverse()
	return {"tong-quan": {"channels": {"rows": rows, "meta": {}}}}


def tet_pack(rows, between=False, target=20.0, asof="2026-12-15", bo=()):
	"""tet.npp_growth dựng tay: rows = [(mã, tên, năm nay tr, cùng kỳ tr, tăng trưởng %)]."""
	meta = {"between_seasons": between, "target_pct": target, "asof": asof, "channel": "npp", "tet_year": 2027}
	for k in bo:
		meta.pop(k)
	return {"tet": {"npp_growth": {"rows": [{"customer": ten, "customer_id": ma, "this_year": nn * TR,
		"last_year": nt * TR, "growth_pct": g} for ma, ten, nn, nt, g in rows], "meta": meta}}}


def khong_chay(key, block, lam_pack):
	"""Khối nguồn thiếu / _error / available False / None → quy tắc vào not_run (không vào ran), không ném lỗi."""
	mang, ten = block.split(".")
	for nhan, hong in (("thiếu khối", "XOA"), ("_error", {"_error": True}), ("available False", {"available": False,
			"rows": []}), ("None", None)):
		pk = lam_pack()
		if hong == "XOA":
			del pk[mang][ten]
		else:
			pk[mang][ten] = hong
		run = chay(pk, only=(key,))
		eq(f"{key}: {nhan} → không chạy được, không tín hiệu", (run.not_run, sorted(run.ran), run.signals),
			({key: f"nguon:{block}"}, [], []))
	run = chay({}, only=(key,))
	eq(f"{key}: pack rỗng → không chạy được", (list(run.not_run), run.signals), ([key], []))


def tat(key, pk):
	run = chay(copy.deepcopy(pk), only=(key,), ov={key: {"disabled": True}})
	eq(f"{key}: tắt → không sinh, vẫn tính là đã chạy (để đóng tín hiệu cũ)", (run.signals, sorted(run.disabled),
		sorted(run.ran), run.not_run), ([], [key], [key], {}))


# ═══ D. kd.tang_truong_am ═════════════════════════════════════════════════════
print("\nD. kd.tang_truong_am (thực bán giảm quá 10% vàng / quá 20% đỏ)")
K = "kd.tang_truong_am"
eq("các mức: −15,2 vàng · −20,1 đỏ · −20,0 vàng (đúng ngưỡng đỏ) · −10,1 vàng · −10,0 không (đúng ngưỡng) · "
	"−9,9 · 0 · +5 · None không",
	[muc(tq_pack(g), K) for g in (-15.2, -20.1, -20.0, -10.1, -10.0, -9.9, 0.0, 5.0, None)],
	["vang", "do", "vang", "vang", None, None, None, None, None])
run, sig, pk = mot(tq_pack(-15.2), K)
eq("−15,2: mức giảm 15,2; lời dựng được", (tinh(sig[K], pk, "giam"), ai_testlib.kiem_loi(sig[K], pk)), (15.2, []))
run, sig, pk = mot(tq_pack(-15.2, dao=True), K)
eq("dòng đảo thứ tự: vẫn lấy đúng dòng năm nay / cùng kỳ theo `period`", ([registry.resolve(pk, p) for p in
	sig[K].paths[1:3]], sig[K].paths[1:3]), ([960 * TR, 882 * TR], [f"{S}.rows[2].net", f"{S}.rows[1].net"]))
pk0 = tq_pack(-15.2)
pk0["tong-quan"]["summary"]["rows"] = []
run, sig, pk = mot(pk0, K)
eq("không có dòng nào: vẫn báo theo growth.net, thân không trích số", (sig[K].severity, sig[K].detail,
	sig[K].paths[:1]), ("vang", "Cần xem kênh và nhóm hàng nào kéo thực bán xuống.", [f"{S}.meta.growth.net"]))
run, sig, pk = mot(tq_pack(-15.2, net=None), K)
eq("thực bán năm nay None: thân không trích số, không lỗi", (sig[K].detail, run.not_run),
	("Cần xem kênh và nhóm hàng nào kéo thực bán xuống.", {}))
eq("ghi đè vàng 5 / đỏ 12: −6 vàng · −12,5 đỏ · −12,0 vàng · −5,0 không",
	[muc(tq_pack(g), K, {"vang": 5, "do": 12}) for g in (-6.0, -12.5, -12.0, -5.0)], ["vang", "do", "vang", None])
eq("ghi đè 0 / trống = mặc định: −6 không · −15 vàng · −25 đỏ",
	[muc(tq_pack(g), K, {"vang": 0, "do": None}) for g in (-6.0, -15.0, -25.0)], [None, "vang", "do"])
eq("chỉ ghi đè đỏ 12: −11 vàng (vàng mặc định 10) · −13 đỏ",
	[muc(tq_pack(g), K, {"do": 12}) for g in (-11.0, -13.0)], ["vang", "do"])
tat(K, tq_pack(-30.0))
khong_chay(K, "tong-quan.summary", lambda: tq_pack(-30.0))
rac = []
for g in ("-30", True, float("nan"), float("-inf"), [-30], {"x": 1}):
	rac.append(muc(tq_pack(g), K))
eq("growth.net không phải số (chuỗi, bool, NaN, vô cực, list, dict) → chạy, không báo", rac, [None] * 6)
for nhan, pk0 in (("meta thiếu", {"tong-quan": {"summary": {"rows": []}}}),
		("growth thiếu", {"tong-quan": {"summary": {"rows": [], "meta": {}}}}),
		("payload rỗng", {"tong-quan": {"summary": {}}}),
		("rows / meta là None", {"tong-quan": {"summary": {"rows": None, "meta": None}}})):
	run, sig, _ = mot(pk0, K)
	eq(f"{nhan} → chạy được, không tín hiệu, không lỗi", (sorted(run.ran), run.not_run, sig), ([K], {}, {}))

# ═══ E. kd.tra_hang_cao ═══════════════════════════════════════════════════════
print("\nE. kd.tra_hang_cao (> 5% đỏ; > 3% và cao hơn cùng kỳ ≥ 1 điểm vàng)")
K = "kd.tra_hang_cao"
CA = [  # (năm nay, cùng kỳ, mức cần, ghi chú)
	(4.0, 2.9, "vang", "chênh 1,1"),
	(4.1, 3.1, "vang", "chênh đúng 1,0 (4.1 − 3.1 = 0,9999… trên số thực máy)"),
	(4.0, 3.1, None, "chênh 0,9"),
	(3.0, 0.5, None, "đúng 3,0 chưa quá ngưỡng dù chênh 2,5"),
	(3.1, 2.0, "vang", "vừa quá 3"),
	(5.0, 1.0, "vang", "đúng 5,0 chưa đỏ"),
	(5.1, 6.0, "do", "quá 5 → đỏ dù THẤP hơn cùng kỳ"),
	(5.1, None, "do", "quá 5, cùng kỳ không có số"),
	(4.5, None, None, "cùng kỳ không có số → không so được → không vàng"),
	(4.5, 4.5, None, "bằng cùng kỳ"),
	(None, 1.0, None, "năm nay chưa bán"),
	(0.0, 0.0, None, "không trả hàng"),
	(2.0, 0.0, None, "dưới 3"),
	(4.0, 0.0, "vang", "cùng kỳ 0,0 là SỐ (không trả hàng) → so được, chênh 4,0"),
]
eq("các mức", [(a, b, muc(tq_pack(-1.0, a, b), K)) for a, b, _m, _g in CA], [(a, b, m) for a, b, m, _g in CA])
run, sig, pk = mot(tq_pack(-1.0, 4.1, 3.1), K)
eq("4,1 so 3,1: chênh ghi 1,0", tinh(sig[K], pk, "chenh"), 1.0)
run, sig, pk = mot(tq_pack(-1.0, 5.1, 6.0), K)
eq("đỏ mà thấp hơn cùng kỳ: thân chỉ nêu số cùng kỳ; chênh −0,9", (sig[K].detail, tinh(sig[K], pk, "chenh"),
	ai_testlib.kiem_loi(sig[K], pk)), (f"Cùng kỳ năm trước là {P(S + '.rows[1].return_rate', 'pct')}; hàng trả về từ "
	f"đầu năm tài chính trị giá {P(S + '.rows[0].returns', 'tien')}.", -0.9, []))
run, sig, pk = mot(tq_pack(-1.0, 5.1, None), K)
eq("đỏ, cùng kỳ None: thân không trích số cùng kỳ, không có số chênh", (sig[K].detail, tinh(sig[K], pk, "chenh"),
	sig[K].paths), (f"Cùng kỳ năm trước chưa có số để so; hàng trả về từ đầu năm tài chính trị giá "
	f"{P(S + '.rows[0].returns', 'tien')}.", "THIEU", [f"{S}.rows[0].return_rate", f"{S}.rows[0].returns"]))
run, sig, pk = mot(tq_pack(-1.0, 5.1, 2.0, returns=None), K)
eq("giá trị trả về None: thân bỏ vế tiền", sig[K].detail, f"Cao hơn cùng kỳ năm trước {P(A(K, 'chenh'), 'so')} điểm "
	f"(cùng kỳ {P(S + '.rows[1].return_rate', 'pct')}).")
run, sig, pk = mot(tq_pack(-1.0, 4.0, 2.0, dao=True), K)
eq("dòng đảo thứ tự: path theo `period`", sig[K].paths[:2], [f"{S}.rows[2].return_rate", f"{S}.rows[1].return_rate"])
pk0 = tq_pack(-1.0, 5.5, 1.0)
del pk0["tong-quan"]["summary"]["rows"][1]
eq("thiếu dòng cùng kỳ: quá 5 vẫn đỏ", muc(pk0, K), "do")
pk0 = tq_pack(-1.0, 4.5, 1.0)
del pk0["tong-quan"]["summary"]["rows"][1]
eq("thiếu dòng cùng kỳ: 4,5 không vàng", muc(pk0, K), None)
pk0 = tq_pack(-1.0, 9.0, 1.0)
del pk0["tong-quan"]["summary"]["rows"][0]
eq("thiếu dòng năm nay → không tín hiệu", muc(pk0, K), None)
eq("ghi đè vàng 2 / đỏ 4: (2,5; 1,0) vàng · (4,2; 4,0) đỏ · (2,5; 2,0) không · (2,0; 0,5) không",
	[muc(tq_pack(-1.0, a, b), K, {"vang": 2, "do": 4}) for a, b in ((2.5, 1.0), (4.2, 4.0), (2.5, 2.0), (2.0, 0.5))],
	["vang", "do", None, None])
eq("chỉ ghi đè đỏ 3,5: (4,0; 3,9) đỏ", muc(tq_pack(-1.0, 4.0, 3.9), K, {"do": 3.5}), "do")
tat(K, tq_pack(-1.0, 9.0, 1.0))
khong_chay(K, "tong-quan.summary", lambda: tq_pack(-1.0, 9.0, 1.0))
eq("tỷ lệ không phải số (chuỗi, bool, NaN) → chạy, không báo",
	[muc(tq_pack(-1.0, a, 1.0), K) for a in ("9.0", True, float("nan"))], [None] * 3)
eq("cùng kỳ là chuỗi → coi như không có số: 4,5 không vàng, 5,5 vẫn đỏ",
	[muc(tq_pack(-1.0, a, "1.0"), K) for a in (4.5, 5.5)], [None, "do"])
pk0 = tq_pack(-1.0, 9.0, 1.0)
pk0["tong-quan"]["summary"]["rows"] = [None, "x", 5, {"period": None, "return_rate": 9.0}, {"return_rate": 9.0}]
run, sig, _ = mot(pk0, K)
eq("dòng rác (None, chuỗi, số, thiếu period) → chạy, không báo, không lỗi", (sorted(run.ran), run.not_run, sig),
	([K], {}, {}))

# ═══ F. kd.kenh_sut ═══════════════════════════════════════════════════════════
print("\nF. kd.kenh_sut (kênh ≥ 10% doanh số giảm quá 15% so cùng kỳ; mỗi kênh một tín hiệu)")
K = "kd.kenh_sut"
# Năm nay 600 / 200 / 100 / 60 / 40 (tổng 1000); cùng kỳ 800 / 235 / 119 / 30 / 16 (tổng 1200)
#   npp      (600 − 800) / 800 = −25,0 → giảm 25,0; tỷ trọng 60,0 / cùng kỳ 800 / 1200 = 66,7       → báo
#   mt       (200 − 235) / 235 = −14,89 → giảm 14,9 (chưa quá 15)                                  → không
#   dulich   (100 − 119) / 119 = −15,97 → giảm 16,0; tỷ trọng ĐÚNG 10,0 / cùng kỳ 119 / 1200 = 9,9 → báo (≥ 10)
#   showroom 60 vs 30, khac 40 vs 16: tăng                                                         → không
NAY, TRUOC = dict(npp=600, mt=200, dulich=100, showroom=60, khac=40), dict(npp=800, mt=235, dulich=119, showroom=30,
	khac=16)
run, sig, pk = mot(kenh_pack(NAY, TRUOC), K)
eq("khoá = mã kênh", sorted(sig), [f"{K}:dulich", f"{K}:npp"])
eq("npp: vàng, giảm 25,0, tỷ trọng 60,0 / 66,7", (sig[f"{K}:npp"].severity, tinh(sig[f"{K}:npp"], pk, "giam"),
	tinh(sig[f"{K}:npp"], pk, "ty_trong"), tinh(sig[f"{K}:npp"], pk, "ty_trong_cung_ky")), ("vang", 25.0, 60.0, 66.7))
eq("dulich: giảm 16,0, tỷ trọng đúng 10,0 (cùng kỳ 9,9)", (tinh(sig[f"{K}:dulich"], pk, "giam"),
	tinh(sig[f"{K}:dulich"], pk, "ty_trong"), tinh(sig[f"{K}:dulich"], pk, "ty_trong_cung_ky")), (16.0, 10.0, 9.9))
eq("npp: paths = bán ra năm nay (dòng 0), cùng kỳ (dòng 5), tên kênh + số tự tính trong lời", sig[f"{K}:npp"].paths,
	[f"{C}.rows[0].sales", f"{C}.rows[5].sales", f"{C}.rows[0].channel", A(f"{K}:npp", "giam"), A(f"{K}:npp", "ty_trong")])
eq("mọi lời dựng được", [ai_testlib.kiem_loi(s, pk) for s in sig.values()], [[], []])
run2, sig2, pk2 = mot(kenh_pack(NAY, TRUOC, dao=True), K)
eq("đảo thứ tự dòng: cùng bộ khoá, cùng số (khoá không phụ thuộc vị trí)", ({k: (s.severity, tinh(s, pk2, "giam"))
	for k, s in sig2.items()}), {k: (s.severity, tinh(s, pk, "giam")) for k, s in sig.items()})
eq("đảo thứ tự dòng: path trỏ đúng dòng (npp năm nay = dòng 14, cùng kỳ = dòng 9)", sig2[f"{K}:npp"].paths[:3],
	[f"{C}.rows[14].sales", f"{C}.rows[9].sales", f"{C}.rows[14].channel"])
#   đúng ngưỡng giảm: npp 850 vs 1000 = −15,0 → không; 849 vs 1000 = −15,1 → vàng
eq("giảm đúng 15,0 → không; 15,1 → vàng", [sorted(mot(kenh_pack(dict(npp=n, mt=150), dict(npp=1000, mt=150)), K)[1])
	for n in (850, 849)], [[], [f"{K}:npp"]])
#   tỷ trọng: mt 80 / 1000 = 8,0% năm nay, 99 / 1000 = 9,9% cùng kỳ, giảm (80 − 99) / 99 = 19,2% → không (dưới 10 cả hai kỳ)
eq("kênh dưới 10% cả hai kỳ giảm 19,2% → không báo", sorted(mot(kenh_pack(dict(npp=920, mt=80), dict(npp=901, mt=99)),
	K)[1]), [])
#   kênh sụt mạnh: mt 50 vs 300 (−83,3; tỷ trọng 5,0 năm nay nhưng 30,0 cùng kỳ) → báo; dulich 50 vs 100 (−50,0; 5,0 và
#   đúng 10,0 cùng kỳ) → báo; npp 900 vs 600 tăng
run, sig, pk = mot(kenh_pack(dict(npp=900, mt=50, dulich=50), dict(npp=600, mt=300, dulich=100)), K)
eq("kênh sụt mạnh đã tụt dưới 10% năm nay vẫn báo theo tỷ trọng cùng kỳ", {k: (tinh(s, pk, "giam"), tinh(s, pk, "ty_trong"),
	tinh(s, pk, "ty_trong_cung_ky")) for k, s in sig.items()}, {f"{K}:mt": (83.3, 5.0, 30.0),
	f"{K}:dulich": (50.0, 5.0, 10.0)})
#   cùng kỳ = 0 → không tính được tăng trưởng → bỏ kênh đó (npp); mt 500 vs 1000 = −50,0 → báo
eq("cùng kỳ 0 → bỏ kênh đó", sorted(mot(kenh_pack(dict(npp=500, mt=500), dict(npp=0, mt=1000)), K)[1]), [f"{K}:mt"])
#   năm nay chưa bán gì: npp 0 vs 1000 → giảm 100,0; tổng năm nay 0 → không có tỷ trọng năm nay
run, sig, pk = mot(kenh_pack(dict(), dict(npp=1000)), K)
s = sig.get(f"{K}:npp")
eq("năm nay 0, cùng kỳ 1000: giảm 100,0; không có tỷ trọng năm nay; thân không nêu tỷ trọng", (tinh(s, pk, "giam"),
	tinh(s, pk, "ty_trong"), tinh(s, pk, "ty_trong_cung_ky"), s.detail, ai_testlib.kiem_loi(s, pk)), (100.0, "THIEU",
	100.0, f"Từ đầu năm tài chính kênh này bán {P(C + '.rows[0].sales', 'tien')}, cùng kỳ năm trước "
	f"{P(C + '.rows[5].sales', 'tien')}.", []))
eq("ghi đè vàng 30 → không kênh nào", sorted(mot(kenh_pack(NAY, TRUOC), K, {"vang": 30})[1]), [])
run, sig, pk = mot(kenh_pack(NAY, TRUOC), K, {"vang": 10, "do": 20})
eq("ghi đè vàng 10 / đỏ 20: npp đỏ (25,0) · mt vàng (14,9) · dulich vàng (16,0)", {k: s.severity for k, s in sig.items()},
	{f"{K}:npp": "do", f"{K}:mt": "vang", f"{K}:dulich": "vang"})
eq("mặc định không có mức đỏ: kênh giảm 100% vẫn vàng", [s.severity for s in mot(kenh_pack(dict(mt=5), dict(npp=1000)),
	K)[1].values()], ["vang"])
tat(K, kenh_pack(NAY, TRUOC))
khong_chay(K, "tong-quan.channels", lambda: kenh_pack(NAY, TRUOC))
pk0 = kenh_pack(NAY, TRUOC)
pk0["tong-quan"]["channels"]["rows"] += [None, "x", {"period": "current", "sales": 5}, {"period": "current",
	"channel_key": "", "sales": 9 * TR}, {"period": "current", "channel_key": "la", "sales": None},
	{"period": "current", "channel_key": 7, "sales": 9 * TR}, {"period": "same_period", "channel_key": "la",
	"sales": "1000"}]
run, sig, pk = mot(pk0, K)
eq("dòng rác (None, thiếu mã kênh, doanh số None / chuỗi) → bỏ qua, kết quả như cũ, không lỗi", (sorted(sig),
	run.not_run), ([f"{K}:dulich", f"{K}:npp"], {}))
pk0 = kenh_pack(NAY, TRUOC)
pk0["tong-quan"]["channels"]["rows"][0]["channel"] = None
run, sig, pk = mot(pk0, K)
eq("tên kênh None: vẫn báo, lời không trích tên", (sig[f"{K}:npp"].title, ai_testlib.kiem_loi(sig[f"{K}:npp"], pk)),
	(f"Một kênh bán hàng giảm {P(A(f'{K}:npp', 'giam'), 'pct')} doanh số so với cùng kỳ", []))
for nhan, rows in (("rows rỗng", []), ("rows None", None), ("rows là dict", {"a": 1})):
	run, sig, _ = mot({"tong-quan": {"channels": {"rows": rows, "meta": {}}}}, K)
	eq(f"{nhan} → chạy, không báo", (sorted(run.ran), run.not_run, sig), ([K], {}, {}))

# ═══ G. tet.npp_tut ═══════════════════════════════════════════════════════════
print("\nG. tet.npp_tut (trong mùa: ≥ 3 NPP có năm trước ≥ 100 tr giảm quá 20% → gộp một tín hiệu)")
K = "tet.npp_tut"
R = [("K1", "Đại lý Một", 500, 400, 25.0),            # tăng
	("K2", "Đại lý Hai", 300, 400, -25.0),             # tụt, hụt 100
	("K3", "Đại lý Ba", 150, 300, -50.0),              # tụt, hụt 150
	("K4", "Đại lý Bốn", 79.9, 100, -20.1),            # tụt (đúng mốc 100 tr, vừa quá 20%), hụt 20,1
	("K5", "Đại lý Năm", 80, 100, -20.0),              # KHÔNG: đúng 20,0%
	("K6", "Đại lý Sáu", 10, 99.999999, -90.0),        # KHÔNG: năm trước 99.999.999 đ
	("K7", "Đại lý Bảy", 20, 0, None)]                 # NPP mới
run, sig, pk = mot(tet_pack(R), K)
s = sig.get(K)
eq("một tín hiệu gộp, vàng", (sorted(sig), s.severity), ([K], "vang"))
eq("3 NPP; hụt 100 + 150 + 20,1 = 270,1 tr; năm nay 300 + 150 + 79,9 = 529,9 tr; cùng kỳ 800 tr; mốc giảm 20",
	(tinh(s, pk, "so_npp"), tinh(s, pk, "hut"), tinh(s, pk, "nam_nay"), tinh(s, pk, "nam_truoc"),
	tinh(s, pk, "nguong_giam")), (3, 270.1 * TR, 529.9 * TR, 800 * TR, 20.0))
neu = ", ".join(f"{P(f'{T}.rows[{i}].customer', 'chu')} ({P(f'{T}.rows[{i}].growth_pct', 'pct')})" for i in (2, 1, 3))
eq("thân: nêu theo tiền hụt giảm dần (Ba 150, Hai 100, Bốn 20,1)", s.detail,
	f"Các NPP này mua ít hơn cùng kỳ năm trước tổng cộng {P(A(K, 'hut'), 'tien')}; hụt nhiều nhất: {neu}.")
eq("lời dựng được", ai_testlib.kiem_loi(s, pk), [])
R2 = [r if r[0] != "K4" else ("K4", "Đại lý Bốn", 80.1, 100, -19.9) for r in R]
eq("chỉ 2 NPP tụt → không báo", muc(tet_pack(R2), K), None)
eq("ghi đè vàng 2 → 2 NPP là báo", muc(tet_pack(R2), K, {"vang": 2}), "vang")
eq("ghi đè vàng 4 → 3 NPP chưa báo", muc(tet_pack(R), K, {"vang": 4}), None)
eq("ghi đè đỏ 3 → 3 NPP đỏ (có dấu bằng)", muc(tet_pack(R), K, {"do": 3}), "do")
eq("giữa hai mùa → chạy, không báo", muc(tet_pack(R, between=True), K), None)
eq("between_seasons = 1 (số) cũng là giữa hai mùa", muc(tet_pack(R, between=1), K), None)
eq("meta thiếu between_seasons → coi là trong mùa", muc(tet_pack(R, bo=("between_seasons",)), K), "vang")
eq("between_seasons None / 0 → trong mùa", [muc(tet_pack(R, between=b), K) for b in (None, 0)], ["vang", "vang"])
# 6 NPP tụt, hụt lần lượt 10·i: nêu tên 3 NPP hụt nhiều nhất (K16, K15, K14), paths gồm 5 NPP đầu (4 path mỗi NPP)
R6 = [(f"K1{i}", f"Đại lý số {i}", 200 - 10 * i, 200, -5.0 * i - 20.5) for i in range(1, 7)]
run, sig, pk = mot(tet_pack(R6), K)
s = sig[K]
eq("6 NPP tụt: đếm 6, hụt 10 + … + 60 = 210 tr", (tinh(s, pk, "so_npp"), tinh(s, pk, "hut")), (6, 210 * TR))
eq("6 NPP tụt: nêu 3 tên (dòng 5, 4, 3), paths của 5 NPP (dòng 5, 4, 3, 2, 1)", ([p for p, k in
	registry.placeholders(s.detail) if k == "chu"], [p for p in s.paths if p.endswith(".growth_pct")]),
	([f"{T}.rows[{i}].customer" for i in (5, 4, 3)], [f"{T}.rows[{i}].growth_pct" for i in (5, 4, 3, 2, 1)]))
R3 = [("K2", None, 300, 400, -25.0), ("K3", "x" * 121, 150, 300, -50.0), ("K4", "Đại lý Bốn", 79.9, 100, -20.1)]
run, sig, pk = mot(tet_pack(R3), K)
eq("tên None / dài quá 120 ký tự: vẫn đếm đủ 3, chỉ nêu tên hợp lệ, lời dựng được", (tinh(sig[K], pk, "so_npp"),
	[p for p, k in registry.placeholders(sig[K].detail) if k == "chu"], ai_testlib.kiem_loi(sig[K], pk)),
	(3, [f"{T}.rows[2].customer"], []))
R4 = [("K2", None, 300, 400, -25.0), ("K3", None, 150, 300, -50.0), ("K4", "", 79.9, 100, -20.1)]
run, sig, pk = mot(tet_pack(R4), K)
eq("không tên nào hợp lệ: thân chỉ nêu tổng hụt", sig[K].detail,
	f"Các NPP này mua ít hơn cùng kỳ năm trước tổng cộng {P(A(K, 'hut'), 'tien')}.")
tat(K, tet_pack(R))
khong_chay(K, "tet.npp_growth", lambda: tet_pack(R))
pk0 = tet_pack(R)
pk0["tet"]["npp_growth"]["rows"] += [None, "x", {}, {"this_year": "1", "last_year": 500 * TR, "growth_pct": -90.0},
	{"this_year": 1.0, "last_year": None, "growth_pct": -90.0}, {"this_year": 1.0, "last_year": 500 * TR,
	"growth_pct": "-90"}, {"this_year": True, "last_year": 500 * TR, "growth_pct": -90.0}]
run, sig, pk = mot(pk0, K)
eq("dòng rác / thiếu số → bỏ qua (vẫn 3 NPP), không lỗi", (tinh(sig[K], pk, "so_npp"), run.not_run), (3, {}))
for nhan, pk0 in (("rows rỗng", tet_pack([])), ("rows None", {"tet": {"npp_growth": {"rows": None, "meta": {}}}}),
		("payload rỗng", {"tet": {"npp_growth": {}}}), ("meta None", {"tet": {"npp_growth": {"rows": [], "meta": None}}})):
	run, sig, _ = mot(pk0, K)
	eq(f"{nhan} → chạy, không báo", (sorted(run.ran), run.not_run, sig), ([K], {}, {}))

# ═══ H. tet.cham_muc_tieu ═════════════════════════════════════════════════════
print("\nH. tet.cham_muc_tieu (trong mùa: tăng trưởng cả kênh NPP thấp hơn mục tiêu ≥ 10 điểm vàng / ≥ 20 đỏ)")
K = "tet.cham_muc_tieu"


def hai(nay, **kw):
	"""Hai NPP: năm nay tổng `nay` tr (700 + phần còn lại), cùng kỳ 600 + 400 = 1000 tr."""
	return tet_pack([("K1", "Đại lý Một", 700, 600, 16.7), ("K2", "Đại lý Hai", nay - 700, 400, 0.0)], **kw)


#   mục tiêu 20; cùng kỳ 1000: năm nay 1100 → +10,0 → thiếu 10,0 (vàng, có dấu bằng); 1101 → +10,1 → thiếu 9,9 (không);
#   1000 → 0,0 → thiếu 20,0 (đỏ, có dấu bằng); 1001 → +0,1 → thiếu 19,9 (vàng); 900 → −10,0 → thiếu 30,0 (đỏ);
#   1300 → +30,0 → vượt mục tiêu (không)
eq("các mức quanh ngưỡng", [muc(hai(n), K) for n in (1100, 1101, 1000, 1001, 900, 1300)],
	["vang", None, "do", "vang", "do", None])
run, sig, pk = mot(hai(900), K)
s = sig[K]
eq("giảm 10%: tăng trưởng −10,0; thiếu 30,0; năm nay 900 tr; cùng kỳ 1000 tr", (tinh(s, pk, "tang_truong"),
	tinh(s, pk, "thieu"), tinh(s, pk, "nam_nay"), tinh(s, pk, "nam_truoc")), (-10.0, 30.0, 900 * TR, 1000 * TR))
eq("paths: mục tiêu, ngày tính đến + số tự tính trong lời", s.paths, [f"{T}.meta.target_pct", f"{T}.meta.asof",
	A(K, "tang_truong"), A(K, "thieu"), A(K, "nam_nay"), A(K, "nam_truoc")])
eq("lời dựng được", ai_testlib.kiem_loi(s, pk), [])
#   làm tròn như màn hình (Math.round): 1062,5 / 1000 → +6,25% → 6,3 (không phải 6,2); thiếu 20 − 6,3 = 13,7
run, sig, pk = mot(hai(1062.5), K)
eq("làm tròn đúng giữa như màn gốc: 6,25 → 6,3; thiếu 13,7", (tinh(sig[K], pk, "tang_truong"), tinh(sig[K], pk, "thieu")),
	(6.3, 13.7))
eq("mục tiêu 0%: năm nay 850 (−15,0) → thiếu 15,0 vàng; 1000 (0,0) → đạt", [muc(hai(n, target=0.0), K)
	for n in (850, 1000)], ["vang", None])
eq("mục tiêu None / chuỗi → không báo", [muc(hai(900, target=t), K) for t in (None, "20")], [None, None])
eq("giữa hai mùa → chạy, không báo (dù thiếu 30 điểm)", muc(hai(900, between=True), K), None)
eq("meta thiếu between_seasons → coi là trong mùa", muc(hai(900, bo=("between_seasons",)), K), "do")
#   ghi đè vàng 5 / đỏ 8: 1130 → +13,0 → thiếu 7,0 vàng; 1120 → +12,0 → thiếu 8,0 đỏ; 1151 → +15,1 → thiếu 4,9 không
eq("ghi đè vàng 5 / đỏ 8", [muc(hai(n), K, {"vang": 5, "do": 8}) for n in (1130, 1120, 1151)], ["vang", "do", None])
eq("cùng kỳ tổng 0 → không tính được → không báo", muc(tet_pack([("K1", "Đại lý Một", 500, 0, None)]), K), None)
eq("chưa có NPP nào → không báo", muc(tet_pack([]), K), None)
run, sig, pk = mot(hai(900, asof="chưa rõ"), K)
eq("ngày tính đến không hợp lệ: thân bỏ vế ngày, lời vẫn dựng được", (sig[K].detail.endswith("{{tet._ai.tet_cham_muc_tieu"
	".nam_truoc|tien}}."), f"{T}.meta.asof" in sig[K].paths, ai_testlib.kiem_loi(sig[K], pk)), (True, False, []))
eq("ngày không có thật (30/02) → bỏ vế ngày", f"{T}.meta.asof" in mot(hai(900, asof="2026-02-30"), K)[1][K].paths, False)
pk0 = hai(900)
pk0["tet"]["npp_growth"]["rows"] += [None, "x", {"this_year": "9e9", "last_year": None}, {"this_year": True}]
run, sig, pk = mot(pk0, K)
eq("dòng rác không làm lệch tổng, không lỗi", (tinh(sig[K], pk, "nam_nay"), tinh(sig[K], pk, "nam_truoc"), run.not_run),
	(900 * TR, 1000 * TR, {}))
tat(K, hai(900))
khong_chay(K, "tet.npp_growth", lambda: hai(900))

# ═══ I. Chạy chung: một khối hỏng không kéo quy tắc khác ═════════════════════
print("\nI. Chạy cả nhóm trên một pack")
pk = {**tq_pack(-30.0, 6.0, 1.0), **tet_pack(R)}
pk["tong-quan"]["channels"] = {"_error": True}
run = chay(pk)
eq("channels lỗi: chỉ kd.kenh_sut không chạy; 4 quy tắc còn lại vẫn báo", (run.not_run, sorted(s.key for s in run.signals)),
	({"kd.kenh_sut": "nguon:tong-quan.channels"}, ["kd.tang_truong_am", "kd.tra_hang_cao", "tet.cham_muc_tieu",
	"tet.npp_tut"]))
eq("số tự tính nằm ở <mảng>._ai.<khoá>", (sorted(pk["tong-quan"]["_ai"]), sorted(pk["tet"]["_ai"])),
	(["kd_tang_truong_am", "kd_tra_hang_cao"], ["tet_cham_muc_tieu", "tet_npp_tut"]))
pk = {"tong-quan": {"available": False, "summary": tq_pack(-30.0)["tong-quan"]["summary"]}}
run = chay(pk, only=("kd.tang_truong_am",))
eq("mảng cha available False → không chạy", run.not_run, {"kd.tang_truong_am": "nguon:tong-quan.summary"})

# ═══ J. AST, riêng tư, khai báo ══════════════════════════════════════════════
print("\nJ. Mã nguồn quy tắc thuần; lời không lộ tên; khai báo đúng đặc tả")
FILE = os.path.join(BC_ROOT, "bc", "ai", "rules", "kd.py")
src = open(FILE, encoding="utf-8").read()
tree = ast.parse(src)
imp = set()
for n in ast.walk(tree):
	if isinstance(n, ast.Import):
		imp |= {a.name for a in n.names}
	elif isinstance(n, ast.ImportFrom):
		imp.add(n.module)
eq("chỉ import thư viện chuẩn + bc.ai.registry (không frappe, không bc.api)", sorted(imp),
	["__future__", "bc.ai.registry", "datetime", "math"])
ten_goi = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree)
	if isinstance(n, ast.Attribute)}
eq("không frappe / db / sql / get_all / get_value / open / eval / exec trong mã", sorted(ten_goi & {"frappe", "db", "sql",
	"get_all", "get_list", "get_value", "get_doc", "open", "eval", "exec", "__import__", "importlib", "requests"}), [])
SQL = re.compile(r"\b(select|insert|update|delete|alter|drop)\b[\s\S]*\b(from|into|set|table)\b|`tab", re.I)
doc = {id(n.value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
	and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) for n in [n.body[0]]}
eq("không chuỗi SQL", [n.value[:40] for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
	and id(n) not in doc and SQL.search(n.value)], [])
# Khoá đọc bằng .get("…") trong quy tắc phải có thật trên dòng của payload thật (bắt gõ sai tên khoá)
khoa = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
	and n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant)}
that = set(p2["tong-quan"]["summary"]["rows"][0]) | set(p2["tong-quan"]["channels"]["rows"][0]) | set(
	p2["tet"]["npp_growth"]["rows"][0])
eq("mọi khoá .get() trong quy tắc có trên dòng payload thật", sorted(khoa - that), [])
c("có đủ ca để soát chung", len(MOI) > 80 and {s.rule for s, _ in MOI} == set(KD), len(MOI))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số nào", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("lời không chứa tên khách / email / ký tự placeholder hỏng", sorted({bo_ph(s) for s, _ in MOI if "@" in bo_ph(s)
	or "{" in bo_ph(s) or "}" in bo_ph(s) or any(t in bo_ph(s) for t in TEN_KHACH)}), [])
eq("placeholder kiểu chữ chỉ trỏ tên khách (.customer) hoặc tên kênh (.channel)", sorted({p for s, _ in MOI
	for p, k in registry.placeholders(s.title + " " + s.detail) if k == "chu"
	and not re.fullmatch(r"(tet\.npp_growth\.rows\[\d+\]\.customer|tong-quan\.channels\.rows\[\d+\]\.channel)", p)}), [])
eq("tên khách không nằm trong tiêu đề (chỉ ở thân, qua placeholder)", sorted({s.title for s, _ in MOI
	if ".customer|" in s.title}), [])
eq("số tự tính chỉ là số (không chuỗi, không tên)", sorted({f"{s.key}.{k}={v!r}" for s, _ in MOI for k, v in s.tinh.items()
	if isinstance(v, bool) or not isinstance(v, (int, float))}), [])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, pk)}" for s, pk in MOI
	if ai_testlib.kiem_loi(s, pk)}), [])
eq("path của tín hiệu chỉ thuộc mảng của chính nó (ẩn mảng → ẩn nhận định)", sorted({f"{s.key}: {p}" for s, _ in MOI
	for p in s.paths if registry.section_of(p) != s.section}), [])
tu = lambda t: len(registry.PLACEHOLDER.sub("X", t).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân là MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khoá tín hiệu: <rule> hoặc kd.kenh_sut:<mã kênh>", sorted({s.key for s, _ in MOI} - set(KD)
	- {f"kd.kenh_sut:{k}" for k, _t in KENH}), [])
eq("khai báo quy tắc (mảng, nguồn, ngưỡng vàng / đỏ, đơn vị, chiều)", {k: (r.section, r.sources, r.vang, r.do, r.unit,
	r.lower, r.audience, r.route) for k, r in registry.RULES.items()}, {
	"kd.tang_truong_am": ("tong-quan", ("tong-quan.summary",), 10, 20, "%", False, "lanh-dao", "#/tong-quan"),
	"kd.tra_hang_cao": ("tong-quan", ("tong-quan.summary",), 3, 5, "%", False, "lanh-dao", "#/tong-quan"),
	"kd.kenh_sut": ("tong-quan", ("tong-quan.channels",), 15, None, "%", False, "lanh-dao", "#/tong-quan"),
	"tet.npp_tut": ("tet", ("tet.npp_growth",), 3, None, "NPP", False, "lanh-dao", "#/tet"),
	"tet.cham_muc_tieu": ("tet", ("tet.npp_growth",), 10, 20, "điểm", False, "lanh-dao", "#/tet")})
eq("nhãn quy tắc: có, không chữ số, không trùng mã", sorted(k for k, r in registry.RULES.items() if not r.label
	or r.label == k or re.search(r"\d", r.label)), [])
eq("mọi quy tắc thuộc nhóm kinh-doanh", {registry.group_of(r.section) for r in registry.RULES.values()}, {"kinh-doanh"})
c.done()
