"""Trợ lý AI — quy tắc nhóm Công nợ (bc.ai.rules.cn): cn.qua_han_ty_le, cn.qua_han_lon, cn.vuot_han_muc, cn.dso_cao,
cn.chua_phan_bo, cn.phai_tra_qua_han, cn.thieu_tien_14_ngay (đặc tả §4.1).

A: PAYLOAD THẬT — seed của test_cn (+ hoá đơn riêng của bộ thử: INV8, PI3, PI4), gọi bc.api.cn thật dựng pack rồi chạy
quy tắc, đối chiếu số tính tay. B–H: pack DỰNG TAY từng quy tắc (vàng, đỏ, không báo, đúng ngưỡng, ghi đè, tắt, khối
nguồn hỏng, None / rác). I: AST (không frappe, không SQL), riêng tư, khai báo. Hôm nay giả 27/10/2026.

Chạy: BC_TEST_DB=bc_test_ai_rcnvc python3 -B test_ai_rules_cn.py
"""
import ast
import copy
import os
import re

from seed import Check, insert, reset
from paths import BC_ROOT

import frappe  # noqa: F401,E402  (giả)
import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.cn")

import test_cn  # noqa: E402
from bc.ai import render  # noqa: E402

c = Check()
TR = 1_000_000
CN = ("cn.qua_han_ty_le", "cn.qua_han_lon", "cn.vuot_han_muc", "cn.dso_cao", "cn.chua_phan_bo", "cn.phai_tra_qua_han",
	"cn.thieu_tien_14_ngay")
R, P = "cong-no.receivables", "phai-tra.payables"
MOI = []
TEN_KHACH = ["NPP-A", "NPP-B", "DL-1", "Khách Lớn Một", "Khách Lớn Hai", "Khách Ba", "Khách Bốn", "Khách Năm",
	"Khách Sáu", "Khách Bảy", "NCC Đường"]


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def A(key, name):
	return f"{registry.RULES[key.split(':')[0]].section}._ai.{registry.slug(key)}.{name}"


def chay(pack, only=CN, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def mot(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


def muc(pack, key, ov=None):
	run, sig, _ = mot(pack, key, ov)
	if key not in run.ran:
		return "KHONG-CHAY"
	return sig[key].severity if key in sig else (None if not sig else sorted(sig))


def tinh(sig, pack, name):
	return registry.resolve(pack, A(sig.key, name), "THIEU")


def khong_chay(key, block, lam_pack):
	mang, ten = block.split(".")
	for nhan, hong in (("thiếu khối", "XOA"), ("_error", {"_error": True}), ("available False", {"available": False}),
			("None", None)):
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
	eq(f"{key}: tắt → không sinh, vẫn tính là đã chạy", (run.signals, sorted(run.disabled), sorted(run.ran), run.not_run),
		([], [key], [key], {}))


def loi(sig, pack):
	"""Lời đã thay số (render thật) — để soát tên / số hiện ra đúng."""
	r = render.render_rule(sig.title, sig.detail, pack)
	assert r["ok"], r
	return r["title"] + " | " + r["body"]


# ═══ A. Payload thật ══════════════════════════════════════════════════════════
print("A. Payload thật: seed test_cn + INV8 (DL-1 60tr, hạn 15/06)")
reset()
test_cn.seed()
# DL-1 thêm INV8 60tr hạn 15/06 → DL-1 nợ 80 = INV5 20 (quá 104 ngày) + INV8 60 (quá 15+31+31+30+27 = 134 ngày)
test_cn.si("INV8", "DL-1", "Du lịch", "2026-06-01", 60, due="2026-06-15")


def pack_that():
	return {"cong-no": {"receivables": ai_testlib.goi("cn.get_receivables")},
		"phai-tra": {"payables": ai_testlib.goi("cn.get_payables")}}


p1 = pack_that()
DOC = [f"{R}.kpis.overdue_pct", f"{R}.kpis.overdue", f"{R}.kpis.receivable", f"{R}.kpis.over_limit",
	f"{R}.kpis.dso.dso", f"{R}.kpis.dso.debt", f"{R}.kpis.dso.revenue", f"{R}.kpis.dso.window_days",
	f"{R}.kpis.unallocated", f"{R}.top_overdue[0].customer", f"{R}.top_overdue[0].overdue", f"{R}.top_overdue[0].max_days",
	f"{P}.ap.due.overdue_total", f"{P}.ap.due.overdue_count", f"{P}.ap.due.upcoming_total", f"{P}.cash.total",
	f"{P}.meta.due_ahead"]
eq("mọi path quy tắc đọc có trên payload thật", [p for p in DOC if not registry.has(p1, p)], [])
r1 = chay(p1)
s1 = {s.key: s for s in r1.signals}
eq("cả 7 quy tắc chạy được", (r1.not_run, sorted(r1.ran)), ({}, sorted(CN)))
# Phải thu 220 + 60 = 280; quá hạn 120 + 60 = 180 → 180 / 280 = 64,29% → 64,3 > 35 → đỏ
eq("overdue_pct thật = 64,3", p1["cong-no"]["receivables"]["kpis"]["overdue_pct"], 64.3)
eq("tỷ lệ quá hạn 64,3% → đỏ", s1["cn.qua_han_ty_le"].severity, "do")
# DL-1: quá hạn 80tr, xa nhất 134 ngày > 90 và 80 ≥ 50 → 1 khách; NPP-A 40tr / 26 ngày, NPP-B 30tr / 57 ngày: không
s = s1["cn.qua_han_lon"]
eq("quá hạn lâu số lớn: vàng, 1 khách, tổng 80tr, mốc 90 ngày", (s.severity, tinh(s, p1, "so_khach"), tinh(s, p1, "tong"),
	tinh(s, p1, "so_ngay")), ("vang", 1, 80 * TR, 90))
eq("DL-1 đứng đầu top quá hạn, 134 ngày", (p1["cong-no"]["receivables"]["top_overdue"][0]["customer"],
	p1["cong-no"]["receivables"]["top_overdue"][0]["max_days"]), ("DL-1", 134))
c("lời dựng thật nêu tên DL-1 ở thân, không ở tiêu đề", "DL-1" in loi(s, p1).split(" | ")[1]
	and "DL-1" not in loi(s, p1).split(" | ")[0], loi(s, p1))
eq("vượt hạn mức 1 khách (NPP-A 80 > 50) → vàng", s1["cn.vuot_han_muc"].severity, "vang")
# DSO = nợ GL (208 + 60) / doanh thu (310 + 60) × 365 = 268 / 370 × 365 = 264,38 → 264,4 > 60 → đỏ
eq("DSO thật 264,4 → đỏ", (p1["cong-no"]["receivables"]["kpis"]["dso"]["dso"], s1["cn.dso_cao"].severity), (264.4, "do"))
eq("tiền chưa gắn HĐ 10tr < 100tr → không báo", "cn.chua_phan_bo" in s1, False)
eq("phải trả quá hạn 30tr (> 0, < 200) → vàng", s1["cn.phai_tra_qua_han"].severity, "vang")
# 14 ngày: quá hạn 30 + đến hạn 15 = 45; quỹ 80 + 500 = 580 → 7,8% → không báo
eq("phải trả 45 / quỹ 580 → không báo", "cn.thieu_tien_14_ngay" in s1, False)
eq("đúng 5 tín hiệu", sorted(s1), sorted(["cn.qua_han_ty_le", "cn.qua_han_lon", "cn.vuot_han_muc", "cn.dso_cao",
	"cn.phai_tra_qua_han"]))
eq("mọi tín hiệu thật dựng được lời", {k: ai_testlib.kiem_loi(v, p1) for k, v in s1.items() if ai_testlib.kiem_loi(v, p1)},
	{})
print("   ví dụ:", loi(s1["cn.qua_han_ty_le"], p1))

print("\nA2. Thêm PI3 600tr (đến hạn 01/11) và PI4 170tr (hạn 20/10, quá hạn)")
for name, sup, due, amt in [("PI3", "NCC Đường", "2026-11-01", 600), ("PI4", "NCC Bao bì", "2026-10-20", 170)]:
	insert("Purchase Invoice", name=name, docstatus=1, company=test_cn.C, supplier=sup, supplier_name=sup,
		posting_date="2026-10-01", due_date=due, grand_total=amt * TR, outstanding_amount=amt * TR)
p2 = pack_that()
r2 = chay(p2, only=("cn.phai_tra_qua_han", "cn.thieu_tien_14_ngay"))
s2 = {s.key: s for s in r2.signals}
# Quá hạn 30 + 170 = 200 ≥ 200 (đúng mốc, có dấu bằng) → đỏ; 2 hoá đơn
eq("quá hạn thật 200tr (đúng mốc đỏ ≥) → đỏ, 2 hoá đơn", (p2["phai-tra"]["payables"]["ap"]["due"]["overdue_total"],
	p2["phai-tra"]["payables"]["ap"]["due"]["overdue_count"], s2["cn.phai_tra_qua_han"].severity), (200 * TR, 2, "do"))
# Phải trả = 200 + (15 + 600) = 815; 815 / 580 × 100 = 140,517 → 140,5 > 100 → đỏ
s = s2["cn.thieu_tien_14_ngay"]
eq("phải trả 815 / quỹ 580 = 140,5% → đỏ", (s.severity, tinh(s, p2, "phai"), tinh(s, p2, "ty_le")), ("do", 815 * TR, 140.5))
eq("lời thật dựng được", [ai_testlib.kiem_loi(x, p2) for x in s2.values()], [[], []])
print("   ví dụ:", loi(s, p2))


# ═══ Pack dựng tay ═══════════════════════════════════════════════════════════
def rc(top=None, **k):
	kpis = {"receivable": 1000 * TR, "overdue": 250 * TR, "overdue_pct": 25.0, "over_limit": 0, "unallocated": 0.0,
		"dso": {"debt": 100 * TR, "revenue": 1000 * TR, "window_days": 365, "dso": 36.5}}
	kpis.update(k)
	return {"cong-no": {"receivables": {"kpis": kpis, "top_overdue": top if top is not None else []}}}


def pt(od=0.0, odn=0, up=0.0, quy=1000 * TR, ahead=14):
	return {"phai-tra": {"payables": {"meta": {"due_ahead": ahead},
		"ap": {"due": {"overdue_total": od, "overdue_count": odn, "upcoming_total": up, "upcoming_count": 0}},
		"cash": {"total": quy}}}}


print("\nB. cn.qua_han_ty_le (> 20 vàng / > 35 đỏ)")
K = "cn.qua_han_ty_le"
for v, want in ((20.0, None), (20.1, "vang"), (35.0, "vang"), (35.1, "do"), (0.0, None), (None, None)):
	eq(f"{v}% → {want}", muc(rc(overdue_pct=v), K), want)
eq("ghi đè vàng 30: 25% không báo; 31% vàng", (muc(rc(overdue_pct=25.0), K, {"vang": 30}),
	muc(rc(overdue_pct=31.0), K, {"vang": 30})), (None, "vang"))
eq("ghi đè đỏ 25: 26% đỏ", muc(rc(overdue_pct=26.0), K, {"do": 25}), "do")
eq("ghi đè 0 = dùng mặc định", muc(rc(overdue_pct=25.0), K, {"vang": 0, "do": 0}), "vang")
eq("giá trị rác (chuỗi, bool) → không báo", (muc(rc(overdue_pct="40"), K), muc(rc(overdue_pct=True), K)), (None, None))
run, sig, pk = mot(rc(overdue_pct=40.0), K)
eq("lời nêu % và hai số tiền", sorted(p for p, _k in registry.placeholders(sig[K].title + sig[K].detail)),
	sorted([f"{R}.kpis.overdue_pct", f"{R}.kpis.overdue", f"{R}.kpis.receivable"]))
run, sig, pk = mot(rc(overdue_pct=40.0, overdue=None), K)
eq("thiếu số tiền → thân không trích số, vẫn báo", (sig[K].severity, registry.placeholders(sig[K].detail)), ("do", []))
tat(K, rc(overdue_pct=40.0))
khong_chay(K, R, lambda: rc(overdue_pct=40.0))


print("\nC. cn.qua_han_lon (> 90 ngày và ≥ 50tr, gộp 1, ≤ 5 tên)")
K = "cn.qua_han_lon"


def kh(ten, od, days):
	return {"customer": ten, "channel": "NPP", "receivable": od, "overdue": od, "unknown": 0, "max_days": days}


eq("90 ngày đúng mốc → không (ngặt)", muc(rc(top=[kh("Khách Ba", 60 * TR, 90)]), K), None)
eq("91 ngày, 50tr đúng mốc → vàng (có dấu bằng)", muc(rc(top=[kh("Khách Ba", 50 * TR, 91)]), K), "vang")
eq("91 ngày, 49,9tr → không", muc(rc(top=[kh("Khách Ba", 49.9 * TR, 91)]), K), None)
eq("không có mức đỏ mặc định: 10 tỷ vẫn vàng", muc(rc(top=[kh("Khách Ba", 10_000 * TR, 400)]), K), "vang")
eq("đặt ngưỡng đỏ 200tr → khách 250tr làm đỏ", muc(rc(top=[kh("Khách Ba", 250 * TR, 100)]), K, {"do": 200 * TR}), "do")
eq("ghi đè vàng 100tr: 80tr không báo", muc(rc(top=[kh("Khách Ba", 80 * TR, 100)]), K, {"vang": 100 * TR}), None)
TOP = [kh("Khách Lớn Một", 300 * TR, 30), kh("Khách Lớn Hai", 120 * TR, 95), kh("Khách Ba", 110 * TR, 200),
	kh("Khách Bốn", 90 * TR, 91), kh("Khách Năm", 70 * TR, 150), kh("Khách Sáu", 60 * TR, 120),
	kh("Khách Bảy", 55 * TR, 100), kh("NPP-B", 40 * TR, 300), None, "rác", {"customer": "X", "overdue": None, "max_days": 99},
	{"customer": "Y", "overdue": 80 * TR, "max_days": "120"}]
run, sig, pk = mot(rc(top=TOP), K)
s = sig[K]
# Thoả: Hai 120, Ba 110, Bốn 90, Năm 70, Sáu 60, Bảy 55 = 6 khách, tổng 505tr; Một (30 ngày), NPP-B (40tr), rác: bỏ
eq("gộp 1 tín hiệu: 6 khách, tổng 505tr", (list(sig), tinh(s, pk, "so_khach"), tinh(s, pk, "tong")), ([K], 6, 505 * TR))
ten = [registry.resolve(pk, p) for p, k in registry.placeholders(s.detail) if k == "chu"]
eq("thân nêu 5 khách nợ quá hạn nhiều nhất, đúng thứ tự", ten, ["Khách Lớn Hai", "Khách Ba", "Khách Bốn", "Khách Năm",
	"Khách Sáu"])
eq("tiêu đề không có tên, không có tiền (D12: số tiền không phải phần quá 90 ngày)",
	[k for _p, k in registry.placeholders(s.title)], ["so", "so"])
# Danh sách không xếp sẵn: quy tắc tự xếp theo nợ quá hạn
run, sig, pk = mot(rc(top=[kh("Khách Năm", 70 * TR, 150), kh("Khách Ba", 110 * TR, 200)]), K)
eq("tự xếp theo nợ quá hạn giảm dần", [registry.resolve(pk, p) for p, k in registry.placeholders(sig[K].detail)
	if k == "chu"], ["Khách Ba", "Khách Năm"])
run, sig, pk = mot(rc(top=[kh(None, 70 * TR, 150)]), K)
eq("tên trống → vẫn báo, thân không nêu tên", (sig[K].severity, [k for _p, k in registry.placeholders(sig[K].detail)
	if k == "chu"]), ("vang", []))
# D12 (N6): NPP-C nợ quá hạn 100tr ở mọi tuổi (chỉ 1tr quá 149 ngày) → lời nói đúng số đó là gì.
run, sig, pk = mot(rc(top=[kh("NPP-C", 100 * TR, 149)]), K)
eq("D12: lời nói rõ tổng là nợ quá hạn ở mọi tuổi nợ, tiêu đề không có tiền", loi(sig[K], pk),
	"1 khách có hoá đơn quá hạn trên 90 ngày | Tổng nợ quá hạn ở mọi tuổi nợ của các khách này là 100 triệu, nhiều "
	"nhất NPP-C 100 triệu; cần thu hồi gấp trước khi thành nợ khó đòi.")
c("D12: không câu nào gắn tiền với 'trên 90 ngày'", not re.search(r"(quá hạn )?trên \S+ ngày,? tổng", loi(sig[K], pk)),
	loi(sig[K], pk))
eq("top rỗng / None / không phải list → chạy, không báo", (muc(rc(top=[]), K), muc(rc(top="x"), K)), (None, None))
pk = rc()
pk["cong-no"]["receivables"]["top_overdue"] = None
eq("top_overdue None → chạy, không báo", muc(pk, K), None)
tat(K, rc(top=TOP))
khong_chay(K, R, lambda: rc(top=TOP))


print("\nD. cn.vuot_han_muc (> 0 khách) · cn.dso_cao (> 45 / > 60) · cn.chua_phan_bo (≥ 100tr)")
K = "cn.vuot_han_muc"
eq("0 khách → không; 1 → vàng; 50 → vẫn vàng (không đỏ)", [muc(rc(over_limit=v), K) for v in (0, 1, 50, None)],
	[None, "vang", "vang", None])
eq("ghi đè vàng 2: 2 không, 3 vàng", (muc(rc(over_limit=2), K, {"vang": 2}), muc(rc(over_limit=3), K, {"vang": 2})),
	(None, "vang"))
tat(K, rc(over_limit=3))
khong_chay(K, R, lambda: rc(over_limit=3))
K = "cn.dso_cao"
DS = lambda v, **k: rc(dso={"debt": 100 * TR, "revenue": 500 * TR, "window_days": 365, "dso": v, **k})  # noqa: E731
eq("45 → không; 45,1 vàng; 60 vàng; 60,1 đỏ; None không", [muc(DS(v), K) for v in (45.0, 45.1, 60.0, 60.1, None)],
	[None, "vang", "vang", "do", None])
eq("ghi đè 90 / 120: 100 vàng", muc(DS(100.0), K, {"vang": 90, "do": 120}), "vang")
run, sig, pk = mot(DS(70.0, revenue=None), K)
eq("thiếu doanh thu → thân không trích số", registry.placeholders(sig[K].detail), [])
pk = rc()
pk["cong-no"]["receivables"]["kpis"]["dso"] = None
eq("dso None (dict thiếu) → chạy, không báo", muc(pk, K), None)
tat(K, DS(70.0))
khong_chay(K, R, lambda: DS(70.0))
K = "cn.chua_phan_bo"
eq("99,99tr không; 100tr đúng mốc vàng; 5 tỷ vẫn vàng", [muc(rc(unallocated=v), K) for v in (99.99 * TR, 100 * TR,
	5000 * TR, None)], [None, "vang", "vang", None])
eq("ghi đè vàng 300tr / đỏ 1 tỷ", [muc(rc(unallocated=v), K, {"vang": 300 * TR, "do": 1000 * TR}) for v in
	(200 * TR, 300 * TR, 1000 * TR)], [None, "vang", "do"])
tat(K, rc(unallocated=200 * TR))
khong_chay(K, R, lambda: rc(unallocated=200 * TR))


print("\nE. cn.phai_tra_qua_han (> 0 vàng / ≥ 200tr đỏ)")
K = "cn.phai_tra_qua_han"
eq("0 không; 1đ vàng; 199,99tr vàng; 200tr đỏ; None không", [muc(pt(od=v), K) for v in (0.0, 1.0, 199.99 * TR,
	200 * TR, None)], [None, "vang", "vang", "do", None])
eq("ghi đè vàng 50tr: 50tr không (ngặt), 51 vàng; đỏ 100tr: 100 đỏ", (muc(pt(od=50 * TR), K, {"vang": 50 * TR}),
	muc(pt(od=51 * TR), K, {"vang": 50 * TR}), muc(pt(od=100 * TR), K, {"do": 100 * TR})), (None, "vang", "do"))
run, sig, pk = mot(pt(od=10 * TR, odn=None), K)
eq("thiếu số hoá đơn → thân không trích số", registry.placeholders(sig[K].detail), [])
tat(K, pt(od=10 * TR))
khong_chay(K, P, lambda: pt(od=10 * TR))


print("\nF. cn.thieu_tien_14_ngay (phải trả / quỹ > 80 vàng / > 100 đỏ)")
K = "cn.thieu_tien_14_ngay"
# 40 + 40 = 80 / 100 = 80,0 → không; 40 + 40,1 = 80,1 → vàng; 100 / 100 → vàng; 100,1 → đỏ
eq("80% đúng mốc không; 80,1 vàng; 100 vàng; 100,1 đỏ", [muc(pt(od=40 * TR, up=u, quy=100 * TR), K) for u in
	(40 * TR, 40.1 * TR, 60 * TR, 60.1 * TR)], [None, "vang", "vang", "do"])
# 80,04% làm tròn 80,0 → không báo (so trên số 1 lẻ như màn)
eq("80,04% → làm tròn 80,0 → không báo", muc(pt(od=80.04 * TR, quy=100 * TR), K), None)
run, sig, pk = mot(pt(od=30 * TR, up=60 * TR, quy=100 * TR), K)
eq("90 / 100: vàng, phai 90tr, ty_le 90", (sig[K].severity, tinh(sig[K], pk, "phai"), tinh(sig[K], pk, "ty_le")),
	("vang", 90 * TR, 90.0))
eq("quỹ 0 / âm mà còn phải trả → đỏ, không nêu %", [(muc(pt(od=1 * TR, quy=q), K)) for q in (0.0, -5 * TR)], ["do", "do"])
run, sig, pk = mot(pt(od=1 * TR, quy=-5 * TR), K)
eq("quỹ âm: tinh chỉ có phai", sig[K].tinh, {"phai": 1 * TR})
eq("phải trả 0 (quỹ 0) → không báo", muc(pt(quy=0.0), K), None)
eq("thiếu số (None) → không báo", [muc(pt(od=None, up=50 * TR, quy=10 * TR), K), muc(pt(od=50 * TR, up=None, quy=10 * TR), K),
	muc(pt(od=50 * TR, quy=None), K)], [None, None, None])
eq("ghi đè 50 / 70: 60% vàng, 71% đỏ", [muc(pt(od=v, quy=100 * TR), K, {"vang": 50, "do": 70}) for v in (60 * TR, 71 * TR)],
	["vang", "do"])
pk = pt(od=90 * TR, quy=100 * TR)
del pk["phai-tra"]["payables"]["meta"]
run, sig, pk = mot(pk, K)
eq("thiếu meta.due_ahead → vẫn báo, lời không trỏ path thiếu", (sig[K].severity, ai_testlib.kiem_loi(sig[K], pk)),
	("vang", []))
tat(K, pt(od=90 * TR, quy=100 * TR))
khong_chay(K, P, lambda: pt(od=90 * TR, quy=100 * TR))
pk = {**rc(overdue_pct=40.0), **pt(od=90 * TR, quy=100 * TR)}
pk["phai-tra"]["payables"]["cash"] = {"available": False}
eq("khối con cash hỏng: quy tắc vẫn chạy (nguồn là cả payables), không báo, không lỗi",
	(muc(pk, K)), None)

print("\nG. Một khối hỏng không kéo khối kia")
pk = {**rc(overdue_pct=40.0), **pt(od=90 * TR, quy=100 * TR)}
pk["cong-no"]["receivables"] = {"_error": True}
run = chay(pk)
eq("phải thu lỗi: 5 quy tắc phải thu không chạy, 2 quy tắc phải trả vẫn báo",
	(sorted(run.not_run), sorted(s.key for s in run.signals)),
	(sorted(CN[:5]), ["cn.phai_tra_qua_han", "cn.thieu_tien_14_ngay"]))


# ═══ I. AST, riêng tư, khai báo ══════════════════════════════════════════════
print("\nI. Mã nguồn thuần; lời không lộ tên; khai báo")
FILE = os.path.join(BC_ROOT, "bc", "ai", "rules", "cn.py")
tree = ast.parse(open(FILE, encoding="utf-8").read())
imp = set()
for n in ast.walk(tree):
	if isinstance(n, ast.Import):
		imp |= {a.name for a in n.names}
	elif isinstance(n, ast.ImportFrom):
		imp.add(n.module)
eq("chỉ import thư viện chuẩn + bc.ai.registry", sorted(imp), ["__future__", "bc.ai.registry", "math"])
ten_goi = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree)
	if isinstance(n, ast.Attribute)}
eq("không frappe / db / sql / get_all / get_value / open / eval", sorted(ten_goi & {"frappe", "db", "sql", "get_all",
	"get_list", "get_value", "get_doc", "open", "eval", "exec", "__import__", "importlib", "requests"}), [])
SQL = re.compile(r"\b(select|insert|update|delete|alter|drop)\b[\s\S]*\b(from|into|set|table)\b|`tab", re.I)
eq("không chuỗi SQL", [n.value[:40] for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
	and SQL.search(n.value)], [])
khoa = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
	and n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant)}
eq("mọi khoá .get() có trên dòng top_overdue thật", sorted(khoa - set(p1["cong-no"]["receivables"]["top_overdue"][0])), [])
c("có đủ ca để soát chung", len(MOI) > 40 and {s.rule for s, _ in MOI} == set(CN), len(MOI))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("lời không chứa tên khách / NCC / email / ngoặc nhọn", sorted({bo_ph(s) for s, _ in MOI if "@" in bo_ph(s)
	or "{" in bo_ph(s) or "}" in bo_ph(s) or any(t in bo_ph(s) for t in TEN_KHACH)}), [])
eq("placeholder chữ chỉ trỏ tên khách top quá hạn", sorted({p for s, _ in MOI for p, k in
	registry.placeholders(s.title + " " + s.detail) if k == "chu"
	and not re.fullmatch(r"cong-no\.receivables\.top_overdue\[\d+\]\.customer", p)}), [])
eq("tên khách không ở tiêu đề", sorted({s.title for s, _ in MOI if "|chu}}" in s.title}), [])
eq("tinh chỉ là số", sorted({f"{s.key}.{k}" for s, _ in MOI for k, v in s.tinh.items()
	if isinstance(v, bool) or not isinstance(v, (int, float))}), [])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, pk)}" for s, pk in MOI
	if ai_testlib.kiem_loi(s, pk)}), [])
eq("path chỉ thuộc mảng của tín hiệu", sorted({f"{s.key}: {p}" for s, _ in MOI for p in s.paths
	if registry.section_of(p) != s.section}), [])
tu = lambda t: len(registry.PLACEHOLDER.sub("X", t).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân là MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khoá tín hiệu = mã quy tắc (không quy tắc nào nhiều tín hiệu)", sorted({s.key for s, _ in MOI} - set(CN)), [])
eq("khai báo quy tắc", {k: (r.section, r.sources, r.vang, r.do, r.unit, r.lower, r.audience, r.route)
	for k, r in registry.RULES.items()}, {
	"cn.qua_han_ty_le": ("cong-no", (R,), 20, 35, "%", False, "lanh-dao", "#/cong-no"),
	"cn.qua_han_lon": ("cong-no", (R,), 50 * TR, None, "đ", False, "lanh-dao", "#/cong-no"),
	"cn.vuot_han_muc": ("cong-no", (R,), 0, None, "khách", False, "lanh-dao", "#/cong-no"),
	"cn.dso_cao": ("cong-no", (R,), 45, 60, "ngày", False, "lanh-dao", "#/cong-no"),
	"cn.chua_phan_bo": ("cong-no", (R,), 100 * TR, None, "đ", False, "lanh-dao", "#/cong-no"),
	"cn.phai_tra_qua_han": ("phai-tra", (P,), 0, 200 * TR, "đ", False, "lanh-dao", "#/phai-tra"),
	"cn.thieu_tien_14_ngay": ("phai-tra", (P,), 80, 100, "%", False, "lanh-dao", "#/phai-tra")})
eq("nhãn: có, không chữ số", sorted(k for k, r in registry.RULES.items() if not r.label or r.label == k
	or re.search(r"\d", r.label)), [])
eq("mọi quy tắc thuộc nhóm tai-chinh", {registry.group_of(r.section) for r in registry.RULES.values()}, {"tai-chinh"})
KPI = [f"{R}.kpis.receivable", f"{R}.kpis.overdue", f"{R}.kpis.overdue_pct", f"{R}.kpis.overdue_customers",
	f"{R}.kpis.dso.dso", f"{R}.kpis.unallocated", f"{R}.kpis.over_limit", f"{R}.kpis.net",
	f"{P}.ap.total", f"{P}.ap.overdue", f"{P}.ap.due.overdue_total", f"{P}.ap.due.overdue_count",
	f"{P}.ap.due.upcoming_total", f"{P}.cash.total"]
eq("KPI đề xuất là số có thật trên payload thật", [p for p in KPI if isinstance(registry.resolve(p1, p, None), bool)
	or not isinstance(registry.resolve(p1, p, None), (int, float))], [])
c.done()
