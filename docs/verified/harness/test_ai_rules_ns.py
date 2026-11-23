"""Trợ lý AI — quy tắc nhóm Nhân sự (bc.ai.rules.ns: ns.bhxh_rui_ro, ns.giay_to, ns.viec_ton) và ATTP
(bc.ai.rules.attp: attp.den_do, attp.chi_tieu) + đề xuất KPI của hai mảng.

A: PAYLOAD THẬT — seed của test_ns + test_attp (+ 3 chỉ tiêu ATTP năm 2026), gọi bc.api.ns.get_overview,
bc.api.attp.get_overview / get_report thật dựng pack rồi chạy quy tắc. B–F: pack DỰNG TAY từng quy tắc: vàng, đỏ, không
báo, đúng ngưỡng, ngưỡng ghi đè, tắt, khối nguồn thiếu / _error / available False, None / rỗng / rác, khoá nhiều tín
hiệu ổn định. G: AST (không frappe, không SQL), riêng tư, lời. H: KPI. Số kỳ vọng TÍNH TAY.

Chạy: BC_TEST_DB=bc_test_ai_rnsht python3 -B test_ai_rules_ns.py
"""
import ast
import copy
import json
import os
import re
from decimal import Decimal

from seed import Check, insert, reset
from paths import BC_ROOT

import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.ns", "bc.ai.rules.attp")

import test_attp, test_ns  # noqa: E402,E401
from bc.ai import render  # noqa: E402

c = Check()
RULES = ("ns.bhxh_rui_ro", "ns.giay_to", "ns.viec_ton", "attp.den_do", "attp.chi_tieu")
MOI = []
O = "nhan-su.overview"
BH, GT, CB = f"{O}.bhxh", f"{O}.giay_to", f"{O}.canh_bao"
OV, RP = "attp.overview", "attp.report"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def P(path, kind):
	return "{{" + f"{path}|{kind}" + "}}"


def loi(sig, pack):
	"""kiem_loi (Decimal của MariaDB coi là số như render) + render.fill thật không lỗi."""
	e = [x for x in ai_testlib.kiem_loi(sig, pack) if not (x.startswith("kieu:") and "Decimal(" in x)]
	return e + render.fill(sig.title + " " + sig.detail, pack).errors


def chay(pack, only=RULES, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def muc_all(pack, key, ov=None):
	"""{khoá tín hiệu: mức} — 'KHONG-CHAY' nếu quy tắc không chạy được."""
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return "KHONG-CHAY" if key not in run.ran else {s.key: s.severity for s in run.signals}


def mot(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


# ═══ A. Payload thật ═════════════════════════════════════════════════════════
print("A. Payload thật — seed test_ns + test_attp, hôm nay 27/10/2026")
reset()
test_ns.seed()
test_attp.seed()
for cs, ss, mt in (("su_co", "≤", 0), ("khieu_nai", "≤", 5), ("ty_le_luot", "≥", 95)):
	insert("SX Chi Tieu ATTP", nam=2026, chi_so=cs, so_sanh=ss, muc_tieu=mt, ngung=0)
THAT = {"nhan-su": {"overview": ai_testlib.goi("ns.get_overview")},
	"attp": {"overview": ai_testlib.goi("attp.get_overview"), "report": ai_testlib.goi("attp.get_report", thang="2026-10")}}
DOC = [f"{BH}.rui_ro", f"{BH}.uoc_tinh", f"{GT}.so_ngay"] + [f"{GT}.{g}.{m}" for g in ("hd", "ksk", "attp")
	for m in ("do", "vang")] + [f"{CB}.rows[0].ma", f"{CB}.rows[0].ten", f"{CB}.rows[0].muc", f"{CB}.rows[0].so_nguoi",
	f"{OV}.linh_vuc[0].ma", f"{OV}.linh_vuc[0].ten", f"{OV}.linh_vuc[0].den", f"{OV}.linh_vuc[0].nhac",
	f"{RP}.chi_tieu[0].chi_so", f"{RP}.chi_tieu[0].ten", f"{RP}.chi_tieu[0].so_sanh", f"{RP}.chi_tieu[0].muc_tieu",
	f"{RP}.chi_tieu[0].don_vi", f"{RP}.chi_tieu[0].nam_luy_ke", f"{RP}.chi_tieu[0].dat_nam"]
eq("mọi path quy tắc đọc có trên payload thật", [p for p in DOC if not registry.has(THAT, p)], [])
eq("mọi khối nguồn dùng được trên payload thật", [s for r in RULES for s in registry.RULES[r].sources
	if not registry.source_ok(THAT, s)], [])

p1 = copy.deepcopy(THAT)
run = chay(p1)
sig = {s.key: s for s in run.signals}
eq("chạy đủ 5 quy tắc", (sorted(run.ran), run.not_run), (sorted(RULES), {}))
eq("tín hiệu + mức trên payload thật", {k: s.severity for k, s in sig.items()}, {
	# rui_ro = E04, E05, E06, E13 (đang làm, cờ BHXH 0, vào làm ≤ 27/09/2026, không lý do) = 4 > 0
	"ns.bhxh_rui_ro": "do",
	# HĐ: E01 (HĐ 01/10) + E02 (contract_end 20/10) đã hết = 2; E03 (20/11 ≤ 26/11) sắp hết = 1
	"ns.giay_to:hd": "do", "ns.giay_to:ksk": "do", "ns.giay_to:attp": "do",
	# cảnh báo đỏ: bhxh_rui_ro (bỏ — đã có quy tắc riêng), luong_trung 1 người
	"ns.viec_ton:luong_trung": "do",
	# 6 lĩnh vực đỏ theo seed test_attp
	"attp.den_do:vong_kiem": "do", "attp.den_do:su_co": "do", "attp.den_do:khac_phuc": "do",
	"attp.den_do:khieu_nai": "do", "attp.den_do:xuat_xuong": "do", "attp.den_do:truy_xuat": "do",
	# tháng 10: sự cố 2 phiếu > mục tiêu ≤ 0; lượt kiểm 55,6% < 95% → chưa đạt; khiếu nại 1 ≤ 5 → đạt
	"attp.chi_tieu:su_co": "vang", "attp.chi_tieu:ty_le_luot": "vang"})
eq("bhxh: rui_ro = 4 (E04, E05, E06, E13)", (registry.resolve(p1, f"{BH}.rui_ro"), sig["ns.bhxh_rui_ro"].title),
	(4, f"{P(BH + '.rui_ro', 'so')} người quá một tháng chưa đóng BHXH, chưa ghi lý do"))
eq("giay_to:hd: 2 đã hết, 1 sắp hết", (registry.resolve(p1, f"{GT}.hd"), sig["ns.giay_to:hd"].title),
	({"do": 2, "vang": 1}, f"{P(GT + '.hd.do', 'so')} người hết hạn hợp đồng lao động, {P(GT + '.hd.vang', 'so')} "
	"người sắp hết"))
rows = THAT["nhan-su"]["overview"]["canh_bao"]["rows"]
i = [r["ma"] for r in rows].index("luong_trung")
eq("viec_ton: trỏ đúng dòng luong_trung (tìm theo mã), 1 người",
	(sig["ns.viec_ton:luong_trung"].title, rows[i]["so_nguoi"]),
	(f"{P(f'{CB}.rows[{i}].ten', 'chu')}: {P(f'{CB}.rows[{i}].so_nguoi', 'so')} người", 1))
lv = THAT["attp"]["overview"]["linh_vuc"]
j = [t["ma"] for t in lv].index("vong_kiem")
s = sig["attp.den_do:vong_kiem"]
# vòng kiểm: 3 việc treo, 1 việc mức cao (seed test_attp: thiếu lượt 22/10 mức cao…)
eq("den_do:vong_kiem: 3 việc treo, 1 mức cao (tinh)", (s.title, s.tinh),
	(f"ATTP: {P(f'{OV}.linh_vuc[{j}].ten', 'chu')} đang báo đèn đỏ", {"viec": 3, "cao": 1}))
eq("den_do:vong_kiem: số tự tính vào pack attp._ai", registry.resolve(p1, "attp._ai.attp_den_do_vong_kiem.viec"), 3)
ct = THAT["attp"]["report"]["chi_tieu"]
k = [x["chi_so"] for x in ct].index("ty_le_luot")
s = sig["attp.chi_tieu:ty_le_luot"]
eq("chi_tieu:ty_le_luot: luỹ kế 55,6% (5/9 lượt), mục tiêu ≥ 95 — kiểu pct",
	(s.detail, ct[k]["nam_luy_ke"], float(ct[k]["muc_tieu"])),
	(f"Luỹ kế năm đạt {P(f'{RP}.chi_tieu[{k}].nam_luy_ke', 'pct')}, mục tiêu {P(f'{RP}.chi_tieu[{k}].so_sanh', 'chu')} "
	f"{P(f'{RP}.chi_tieu[{k}].muc_tieu', 'pct')}, cần rà nguyên nhân với Ban ATTP.", 55.6, 95.0))
eq("chi_tieu:ty_le_luot dựng lời thật", render.fill(s.detail, p1).text,
	"Luỹ kế năm đạt 55,6%, mục tiêu ≥ 95,0%, cần rà nguyên nhân với Ban ATTP.")
eq("mọi tín hiệu payload thật dựng được lời", {k2: loi(s2, p1) for k2, s2 in sig.items() if loi(s2, p1)}, {})
eq("audience lãnh đạo, route theo mảng", {(s2.audience, s2.route) for s2 in sig.values()},
	{("lanh-dao", "#/nhan-su"), ("lanh-dao", "#/attp")})
# Riêng tư trên payload thật: lời đã thay số không có tên / mã NV / tiêu đề việc treo của sx.
viec = {x.get("tieu_de") for t in lv for x in t.get("nhac") or [] if x.get("tieu_de")}
txt = " ".join(render.fill(s2.title + " " + s2.detail, p1).text for s2 in sig.values())
eq("lời thật không lộ tên / mã nhân viên / số giấy tờ / tiêu đề việc treo",
	[x for x in [test_ns.TEN, "HR-EMP", "SO-BI-MAT", test_ns.LUONG_HUU, *viec] if x and x in txt], [])

# ═══ B. ns.bhxh_rui_ro ═══════════════════════════════════════════════════════
print("\nB. ns.bhxh_rui_ro")


def NS(**blocks):
	base = {"available": True, "meta": {}, "bhxh": {"available": True, "uoc_tinh": False, "rui_ro": 0},
		"giay_to": {"available": True, "so_ngay": 30, "hd": {"do": 0, "vang": 0}, "ksk": {"do": 0, "vang": 0},
		"attp": {"do": 0, "vang": 0}}, "canh_bao": {"available": True, "rows": []}}
	base.update(blocks)
	return {"nhan-su": {"overview": base}}


K = "ns.bhxh_rui_ro"
bh = lambda v, **kw: NS(bhxh={"available": True, "uoc_tinh": False, "rui_ro": v, **kw})  # noqa: E731
eq("rui_ro 1 → đỏ; 0 → không", (muc_all(bh(1), K), muc_all(bh(0), K)), ({K: "do"}, {}))
eq("ghi đè đỏ 3: 3 không (ngặt), 4 đỏ", (muc_all(bh(3), K, {"do": 3}), muc_all(bh(4), K, {"do": 3})), ({}, {K: "do"}))
eq("ghi đè thêm vàng 0, đỏ 5: 2 → vàng", muc_all(bh(2), K, {"vang": 0.5, "do": 5}), {K: "vang"})
eq("tắt", muc_all(bh(9), K, {"disabled": True}), {})
eq("ước tính (rui_ro None) / chuỗi / bool → không báo", [muc_all(bh(v), K) for v in (None, "4", True)], [{}, {}, {}])
eq("khối bhxh thiếu / _error / available False → không chạy", [muc_all(NS(bhxh=b), K) for b in
	({"_error": True}, {"available": False})] + [muc_all({"nhan-su": {"overview": {"available": True}}}, K),
	muc_all({"nhan-su": {"overview": {"available": False}}}, K), muc_all({}, K)], ["KHONG-CHAY"] * 5)

# ═══ C. ns.giay_to ═══════════════════════════════════════════════════════════
print("\nC. ns.giay_to")
K = "ns.giay_to"


def gt(hd=(0, 0), ksk=(0, 0), attp=(0, 0), **kw):
	return NS(giay_to={"available": True, "so_ngay": 30, "hd": {"do": hd[0], "vang": hd[1]},
		"ksk": {"do": ksk[0], "vang": ksk[1]}, "attp": {"do": attp[0], "vang": attp[1]}, **kw})


eq("mỗi nhóm một khoá: hd đỏ (đã hết), ksk vàng (sắp hết), attp không", muc_all(gt((1, 0), (0, 2)), K),
	{"ns.giay_to:hd": "do", "ns.giay_to:ksk": "vang"})
eq("không gì hết hạn → không", muc_all(gt(), K), {})
eq("ghi đè vàng 2, đỏ 1: hd (1, 2) không; ksk (2, 0) đỏ; attp (0, 3) vàng",
	muc_all(gt((1, 2), (2, 0), (0, 3)), K, {"vang": 2, "do": 1}), {"ns.giay_to:ksk": "do", "ns.giay_to:attp": "vang"})
_, sg, pk = mot(gt((0, 2)), K)
eq("lời vàng nêu số sắp hết + số ngày", (sg["ns.giay_to:hd"].title, sg["ns.giay_to:hd"].detail.count(P(GT + ".so_ngay",
	"so"))), (f"{P(GT + '.hd.vang', 'so')} người sắp hết hạn hợp đồng lao động", 1))
_, sg, pk = mot(gt((3, 0), so_ngay=None), K)
eq("đỏ không có sắp hết → không nêu vế 'sắp hết'; so_ngay None → lời không trỏ so_ngay",
	(sg["ns.giay_to:hd"].title, "so_ngay" in sg["ns.giay_to:hd"].detail), (f"{P(GT + '.hd.do', 'so')} người hết hạn "
	"hợp đồng lao động", False))
eq("nhóm thiếu / None / rác → bỏ nhóm đó, không lỗi", muc_all(NS(giay_to={"available": True, "hd": None,
	"ksk": {"do": None, "vang": "2"}, "attp": {"do": 1}}), K), {"ns.giay_to:attp": "do"})
eq("tắt / khối _error", (muc_all(gt((5, 5)), K, {"disabled": True}), muc_all(NS(giay_to={"_error": True}), K)),
	({}, "KHONG-CHAY"))

# ═══ D. ns.viec_ton ══════════════════════════════════════════════════════════
print("\nD. ns.viec_ton")
K = "ns.viec_ton"
R = lambda ma, muc, n, ten="Việc X": {"ma": ma, "ten": ten, "muc": muc, "so_nguoi": n}  # noqa: E731
cb = lambda *rows: NS(canh_bao={"available": True, "rows": list(rows)})  # noqa: E731
eq("chỉ mã đỏ, bỏ bhxh_rui_ro; vàng không báo", muc_all(cb(R("bhxh_rui_ro", "do", 4), R("luong_trung", "do", 1),
	R("thieu_cccd", "vang", 9)), K), {"ns.viec_ton:luong_trung": "do"})
a = muc_all(cb(R("a_x", "do", 2), R("b_y", "do", 1)), K)
b = muc_all(cb(R("b_y", "do", 1), R("a_x", "do", 2), R("a_x", "do", 7)), K)
eq("khoá theo mã, không theo vị trí; mã trùng lấy dòng đầu", (a, b), ({"ns.viec_ton:a_x": "do", "ns.viec_ton:b_y": "do"},
	{"ns.viec_ton:a_x": "do", "ns.viec_ton:b_y": "do"}))
_, sg, _ = mot(cb(R("b_y", "do", 1), R("a_x", "do", 2)), K)
eq("lời trỏ đúng dòng của mã", sg["ns.viec_ton:a_x"].paths[0], f"{CB}.rows[1].so_nguoi")
eq("so_nguoi 0 / None → không; ghi đè đỏ 2: 2 không, 3 đỏ", (muc_all(cb(R("a", "do", 0), R("b", "do", None)), K),
	muc_all(cb(R("a", "do", 2), R("b", "do", 3)), K, {"do": 2})), ({}, {"ns.viec_ton:b": "do"}))
_, sg, pk = mot(cb(R("a", "do", 1, ten=None)), K)
eq("tên mã thiếu → lời chung, vẫn dựng được", (sg["ns.viec_ton:a"].title.startswith("Việc nhân sự mức gấp"),
	loi(sg["ns.viec_ton:a"], pk)), (True, []))
eq("rows rác / mã rỗng → không lỗi", [muc_all(NS(canh_bao={"available": True, "rows": v}), K) for v in
	(None, "x", [None, 3, {"muc": "do", "so_nguoi": 3}, {"ma": "", "muc": "do", "so_nguoi": 3}])], [{}, {}, {}])
eq("canh_bao available False (không có app ns) → không chạy", muc_all(NS(canh_bao={"available": False}), K), "KHONG-CHAY")

# ═══ E. attp.den_do ══════════════════════════════════════════════════════════
print("\nE. attp.den_do")
K = "attp.den_do"


def AT(linh_vuc=None, chi_tieu=None, ov=None, rp=None):
	return {"attp": {"overview": ov or {"available": True, "linh_vuc": linh_vuc or [], "dem": {}},
		"report": rp or {"available": True, "nam": 2026, "chi_tieu": chi_tieu or []}}}


L = lambda ma, den, nhac=(): {"ma": ma, "ten": f"Mảng {ma}", "den": den, "so": "1", "nhan_so": "x",  # noqa: E731
	"nhac": [{"muc_do": m, "tieu_de": "Khách Bí Mật ATTP", "chi_tiet": ""} for m in nhac]}
eq("đỏ → một khoá / lĩnh vực; vàng / xanh không", muc_all(AT([L("su_co", "do", ("cao", "thuong")), L("cat", "vang"),
	L("ncc", "xanh"), L("rework", "do")]), K), {"attp.den_do:su_co": "do", "attp.den_do:rework": "do"})
_, sg, pk = mot(AT([L("cat", "xanh"), L("su_co", "do", ("cao", "thuong", "cao"))]), K)
s = sg["attp.den_do:su_co"]
eq("đếm việc treo 3, mức cao 2; lời trỏ đúng phần tử", (s.tinh, s.paths[0]), ({"viec": 3, "cao": 2},
	f"{OV}.linh_vuc[1].ten"))
eq("lời không chứa tiêu đề việc treo", "Bí Mật" in render.fill(s.title + s.detail, pk).text, False)
_, sg, pk = mot(AT([L("su_co", "do")]), K)
eq("không việc treo → không tinh, lời chung", (sg["attp.den_do:su_co"].tinh, loi(sg["attp.den_do:su_co"], pk)), ({}, []))
eq("tắt / overview available False (không có sx) / _error → (tắt: chạy, không tín hiệu) / không chạy",
	(muc_all(AT([L("a", "do")]), K, {"disabled": True}), muc_all(AT(ov={"available": False, "meta": {}}), K),
	muc_all(AT(ov={"_error": True}), K)), ({}, "KHONG-CHAY", "KHONG-CHAY"))
eq("linh_vuc rác / mã có khoảng trắng / trùng mã → không lỗi, mã trùng một khoá",
	muc_all(AT([None, {"den": "do"}, {"ma": "a b", "den": "do"}, L("x", "do"), L("x", "do")]), K),
	{"attp.den_do:x": "do"})

# ═══ F. attp.chi_tieu ════════════════════════════════════════════════════════
print("\nF. attp.chi_tieu")
K = "attp.chi_tieu"
CT = lambda cs, dat, nlk=3, mt=Decimal("0E-9"), dv="phiếu": {"chi_so": cs, "ten": f"Chỉ tiêu {cs}",  # noqa: E731
	"so_sanh": "≤", "muc_tieu": mt, "don_vi": dv, "ky": 1, "nam_luy_ke": nlk, "dat_ky": dat, "dat_nam": dat}
eq("chỉ dat_nam False báo (True / None không)", muc_all(AT(chi_tieu=[CT("su_co", False), CT("khieu_nai", True),
	CT("rework", None)]), K), {"attp.chi_tieu:su_co": "vang"})
_, sg, pk = mot(AT(chi_tieu=[CT("ty_le_luot", False, 80.0, 95.0, "%"), CT("su_co", False)]), K)
eq("đơn vị % → kiểu pct; khác → so; Decimal dựng được", ([k2 for p, k2 in registry.placeholders(
	sg["attp.chi_tieu:ty_le_luot"].detail) if p.endswith("nam_luy_ke")], [k2 for p, k2 in registry.placeholders(
	sg["attp.chi_tieu:su_co"].detail) if p.endswith("muc_tieu")], render.fill(sg["attp.chi_tieu:su_co"].detail, pk).text),
	(["pct"], ["so"], "Luỹ kế năm đạt 3, mục tiêu ≤ 0, cần rà nguyên nhân với Ban ATTP."))
_, sg, pk = mot(AT(chi_tieu=[CT("su_co", False, None)]), K)
eq("luỹ kế None → lời không số (chỉ path tên)", (sg["attp.chi_tieu:su_co"].paths, loi(sg["attp.chi_tieu:su_co"], pk)),
	([f"{RP}.chi_tieu[0].ten"], []))
eq("chỉ số trùng → một khoá; rác → bỏ", muc_all(AT(chi_tieu=[CT("su_co", False), CT("su_co", False), None,
	{"dat_nam": False}]), K), {"attp.chi_tieu:su_co": "vang"})
eq("report available False / thiếu → không chạy; overview hỏng không ảnh hưởng chi_tieu",
	(muc_all(AT(rp={"available": False, "meta": {}}), K), muc_all({"attp": {"overview": {"available": True}}}, K),
	muc_all(AT(chi_tieu=[CT("a", False)], ov={"_error": True}), K)), ("KHONG-CHAY", "KHONG-CHAY", {"attp.chi_tieu:a": "vang"}))

# ═══ G. AST, riêng tư, lời ═══════════════════════════════════════════════════
print("\nG. AST, riêng tư, lời")
SQL = re.compile(r"\b(select|insert|update|delete|alter|drop)\b[\s\S]*\b(from|into|set|table)\b|`tab", re.I)
for f in ("ns.py", "attp.py"):
	src = open(os.path.join(BC_ROOT, "bc", "ai", "rules", f), encoding="utf-8").read()
	tree = ast.parse(src)
	imp = sorted({a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
		| {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)})
	eq(f"{f}: chỉ import registry + thư viện chuẩn", [m for m in imp if m not in ("__future__", "math", "decimal",
		"bc.ai.registry")], [])
	eq(f"{f}: không frappe / db / get_all / sql", sorted({n.attr if isinstance(n, ast.Attribute) else n.id
		for n in ast.walk(tree) if (isinstance(n, ast.Attribute) and n.attr in ("db", "sql", "get_all", "get_list",
		"get_value", "get_doc")) or (isinstance(n, ast.Name) and n.id in ("frappe", "eval", "exec", "open"))}), [])
	doc = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
		and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
	eq(f"{f}: không chuỗi SQL", [n.value[:40] for n in ast.walk(tree) if isinstance(n, ast.Constant)
		and isinstance(n.value, str) and id(n) not in doc and SQL.search(n.value)], [])
c("có đủ ca để soát chung", len(MOI) > 40 and {s.rule for s, _ in MOI} == set(RULES), (len(MOI), {s.rule for s, _ in MOI}))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
RIENG = [test_ns.TEN, "HR-EMP", "SO-BI-MAT", "079123456789", test_ns.LUONG_HUU, "Bí Mật", "@", "{", "}"]
eq("lời / tinh / documents không có tên, mã NV, email, ghi chú", sorted({bo_ph(s) for s, _ in MOI
	if any(t in bo_ph(s) for t in RIENG)} | {f"{s.key}.{k}={v!r}" for s, _ in MOI for k, v in s.tinh.items()
	if isinstance(v, bool) or not isinstance(v, (int, float))} | {s.key for s, _ in MOI if s.documents}), [])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {loi(s, p)}" for s, p in MOI if loi(s, p)}), [])
eq("path chỉ thuộc mảng của tín hiệu", sorted({f"{s.key}: {p}" for s, _ in MOI for p in s.paths
	if registry.section_of(p) != s.section}), [])
eq("placeholder chu chỉ trỏ ten / so_sanh (nhãn, không tên người)", sorted({p.rsplit(".", 1)[1] for s, _ in MOI
	for p, k in registry.placeholders(s.title + " " + s.detail) if k == "chu"}), ["so_sanh", "ten"])
tu = lambda t: len(registry.PLACEHOLDER.sub("X", t).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân là MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khai báo quy tắc (mảng, nguồn, vàng, đỏ, audience)", {k: (r.section, r.sources, r.vang, r.do, r.lower, r.audience)
	for k, r in registry.RULES.items()}, {
	"ns.bhxh_rui_ro": ("nhan-su", (BH,), None, 0, False, "lanh-dao"),
	"ns.giay_to": ("nhan-su", (GT,), 0, 0, False, "lanh-dao"),
	"ns.viec_ton": ("nhan-su", (CB,), None, 0, False, "lanh-dao"),
	"attp.den_do": ("attp", (OV,), None, None, False, "lanh-dao"),
	"attp.chi_tieu": ("attp", (RP,), None, None, False, "lanh-dao")})
dump = json.dumps([s.__dict__ for s, _ in MOI if s.section == "nhan-su"], ensure_ascii=False, default=str)
eq("tín hiệu nhân sự (cả path) không chứa tên / mã nhân viên", [x for x in (test_ns.TEN, "HR-EMP", "employee")
	if x in dump], [])

# ═══ H. KPI ══════════════════════════════════════════════════════════════════
print("\nH. KPI đề xuất")
KPIS = [
	("nhan-su.overview.nhan_su.dang_lam", "so", "Số người đang làm"),
	("nhan-su.overview.nhan_su.tam_nghi", "so", "Số người tạm nghỉ"),
	("nhan-su.overview.bien_dong.vao", "so", "Vào làm 12 tháng"),
	("nhan-su.overview.bien_dong.nghi", "so", "Nghỉ việc 12 tháng"),
	("nhan-su.overview.bhxh.ty_le", "pct", "Tỷ lệ đóng BHXH"),
	("nhan-su.overview.bhxh.rui_ro", "so", "Người quá một tháng chưa đóng BHXH, chưa ghi lý do"),
	("nhan-su.overview.giay_to.hd.do", "so", "Người hết hạn hợp đồng"),
	("nhan-su.overview.giay_to.ksk.do", "so", "Người hết hạn khám sức khỏe"),
	("attp.overview.dem.do", "so", "Lĩnh vực ATTP đèn đỏ"),
	("attp.overview.dem.vang", "so", "Lĩnh vực ATTP đèn vàng"),
]
eq("mọi KPI có trên payload thật và là số", [p for p, _k, _l in KPIS if not registry.has(THAT, p)
	or isinstance(registry.resolve(THAT, p), bool) or not isinstance(registry.resolve(THAT, p), (int, float))], [])
eq("KPI = số tay theo seed (đang làm 21, tạm nghỉ 3, BHXH 8/21 = 38,1%, đèn đỏ 6)", [registry.resolve(THAT, p)
	for p in ("nhan-su.overview.nhan_su.dang_lam", "nhan-su.overview.nhan_su.tam_nghi", "nhan-su.overview.bhxh.ty_le",
	"attp.overview.dem.do")], [21, 3, 38.1, 6])

c.done()
