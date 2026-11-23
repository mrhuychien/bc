"""Trợ lý AI — quy tắc nhóm Vận chuyển (bc.ai.rules.vc): vc.cho_qua_han, vc.chua_xep_chuyen, vc.giao_lan_dau,
vc.su_co_mo, vc.cuoc_canh_bao, vc.xe_qua_han (đặc tả §4.1).

A: PAYLOAD THẬT — seed của test_vc (vanchuyen + lịch xe THẬT), gọi bc.api.vc.get_overview thật dựng pack, đối chiếu số
tính tay trong test_vc. B–G: pack DỰNG TAY từng quy tắc (vàng, đỏ, không báo, đúng ngưỡng, ghi đè, tắt, khối nguồn
hỏng, None / rác, khoá nhiều tín hiệu ổn định, chế độ ẩn tiền cước). H: AST, riêng tư, khai báo.

Chạy: BC_TEST_DB=bc_test_ai_rcnvc python3 -B test_ai_rules_vc.py
"""
import ast
import copy
import os
import re

from seed import Check, reset
from paths import BC_ROOT

import frappe  # noqa: F401,E402  (giả)
import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.vc")

import test_vc  # noqa: E402  (thêm app vanchuyen vào sys.path)
from bc.ai import render  # noqa: E402

c = Check()
VC = ("vc.cho_qua_han", "vc.chua_xep_chuyen", "vc.giao_lan_dau", "vc.su_co_mo", "vc.cuoc_canh_bao", "vc.xe_qua_han")
O = "van-chuyen.overview"
G, CUOC, SC, XE = f"{O}.giao", f"{O}.cuoc", f"{O}.su_co", f"{O}.xe"
MOI = []


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def A(key, name):
	return f"{registry.RULES[key.split(':')[0]].section}._ai.{registry.slug(key)}.{name}"


def chay(pack, only=VC, ov=None):
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


def loi(sig, pack):
	r = render.render_rule(sig.title, sig.detail, pack)
	assert r["ok"], r
	return r["title"] + " | " + r["body"]


def khong_chay(key, block, lam_pack):
	"""Khối nguồn (sâu) thiếu / _error / available False / None, và cả trang available False → not_run."""
	for nhan, hong in (("thiếu khối", "XOA"), ("_error", {"_error": True}), ("available False", {"available": False,
			"error": True}), ("None", None)):
		pk = lam_pack()
		cha, ten = block.rsplit(".", 1)
		goc = registry.resolve(pk, cha)
		if hong == "XOA":
			del goc[ten]
		else:
			goc[ten] = hong
		run = chay(pk, only=(key,))
		eq(f"{key}: {nhan} → không chạy được", (run.not_run, sorted(run.ran), run.signals), ({key: f"nguon:{block}"}, [], []))
	pk = lam_pack()
	pk["van-chuyen"]["overview"]["available"] = False
	run = chay(pk, only=(key,))
	eq(f"{key}: cả trang available False → không chạy được", (list(run.not_run), run.signals), ([key], []))


def tat(key, pk):
	run = chay(copy.deepcopy(pk), only=(key,), ov={key: {"disabled": True}})
	eq(f"{key}: tắt → không sinh, vẫn tính là đã chạy", (run.signals, sorted(run.disabled), sorted(run.ran), run.not_run),
		([], [key], [key], {}))


# ═══ A. Payload thật ══════════════════════════════════════════════════════════
print("A. Payload thật: seed test_vc (tháng 10/2026, hôm nay 27/10)")
reset()
test_vc.seed()
p1 = {"van-chuyen": {"overview": ai_testlib.goi("vc.get_overview")}}
DOC = [f"{G}.cho_qua_han.qua_n", f"{G}.cho_qua_han.so_ngay", f"{G}.cho_qua_han.rows[0].hinh_thuc",
	f"{G}.cho_qua_han.rows[0].qua_n", f"{G}.xep.chua_xep", f"{G}.xep.mot_phan", f"{G}.lan_dau.ty_le", f"{G}.lan_dau.so_don",
	f"{G}.lan_dau.khach_hen", f"{G}.lan_dau.hoan", f"{SC}.mo_qua_n", f"{SC}.so_ngay", f"{CUOC}.an", f"{CUOC}.tra_bat_thuong",
	f"{CUOC}.tra_chuyen_huy", f"{CUOC}.tra_chuyen_huy_tien", f"{CUOC}.sua_tay", f"{XE}.can_xu_ly[0].xe",
	f"{XE}.can_xu_ly[0].qua_han"]
eq("mọi path quy tắc đọc có trên payload thật", [p for p in DOC if not registry.has(p1, p)], [])
r1 = chay(p1)
s1 = {s.key: s for s in r1.signals}
eq("cả 6 quy tắc chạy được", (r1.not_run, sorted(r1.ran)), ({}, sorted(VC)))
eq("tín hiệu thật: khoá + mức", {k: v.severity for k, v in s1.items()}, {
	"vc.cho_qua_han": "vang",            # 6 đơn chờ quá 3 ngày (test_vc: qua_n = 6) — > 0, ≤ 10
	"vc.chua_xep_chuyen": "vang",        # chua_xep = 3 (S3, S9, X7)
	"vc.su_co_mo": "vang",               # mo_qua_n = 3 sự cố mở > 7 ngày
	"vc.cuoc_canh_bao:tra_bat_thuong": "vang",   # CX2: đã trả, JE-2 đã huỷ
	"vc.cuoc_canh_bao:tra_chuyen_huy": "vang",   # CX4 huỷ, JE-3 còn hiệu lực, 777đ
	"vc.cuoc_canh_bao:sua_tay": "vang",          # CX2 cước thủ công
	"vc.xe_qua_han": "do"})              # 29C-111.11 quá hạn đăng kiểm + thay dầu, 29C-222.22 sắp bảo dưỡng
# Giao lần đầu tháng 10: 3 đơn, 2 đã giao → 66,7% (< 80 là đỏ) nhưng 3 < 10 đơn → chưa xét
eq("giao lần đầu 66,7% trên 3 đơn → chưa đủ mẫu, không báo", (p1["van-chuyen"]["overview"]["giao"]["lan_dau"]["ty_le"],
	"vc.giao_lan_dau" in s1), (66.7, False))
x = s1["vc.xe_qua_han"]
eq("xe: 1 quá hạn, 1 sắp đến", (tinh(x, p1, "qua_han"), tinh(x, p1, "sap_den")), (1, 1))
t = loi(x, p1)
c("lời xe nêu biển số xe quá hạn, không nêu xe sắp đến", "29C-111.11" in t and "29C-222.22" not in t
	and "thêm 1 xe sắp đến hạn" in t, t)
t = loi(s1["vc.cho_qua_han"], p1)
c("chờ giao: 6 đơn, dồn nhiều nhất ở Tự vận chuyển (5 đơn)", t.startswith("6 đơn chờ giao quá 3 ngày")
	and "Tự vận chuyển với 5 đơn" in t, t)
t = loi(s1["vc.cuoc_canh_bao:tra_chuyen_huy"], p1)
c("chuyến huỷ đã chi: tháng đủ lái xe → nêu tiền 777đ", "777" in t, t)
t = loi(s1["vc.chua_xep_chuyen"], p1)
c("chưa xếp 3 đơn, thêm 1 đơn xếp một phần", t.startswith("3 đơn") and "thêm 1 đơn" in t, t)
eq("mọi tín hiệu thật dựng được lời", {k: ai_testlib.kiem_loi(v, p1) for k, v in s1.items() if ai_testlib.kiem_loi(v, p1)}, {})
for k in sorted(s1):
	print("   ", loi(s1[k], p1))
c("lời thật không chứa tên lái xe / khách / SĐT / ghi chú", not any(b in loi(s, p1) for s in s1.values()
	for b in test_vc.BI_MAT), "")

# Tháng 9: 1 lái xe → cước ẩn tiền (an True); test_vc đã khẳng định payload an
p9 = {"van-chuyen": {"overview": ai_testlib.goi("vc.get_overview", thang="2026-09")}}
eq("tháng 9 thật: cước ở chế độ ẩn tiền", p9["van-chuyen"]["overview"]["cuoc"]["an"], True)
r9 = chay(p9, only=("vc.cuoc_canh_bao",))
eq("tháng 9 thật: chạy được, không lỗi", (r9.not_run, sorted(r9.ran)), ({}, ["vc.cuoc_canh_bao"]))


# ═══ Pack dựng tay ═══════════════════════════════════════════════════════════
def vp(qua_n=0, chua_xep=0, mot_phan=0, ld=None, mo_qua_n=0, cuoc=None, can=None):
	return {"van-chuyen": {"overview": {"available": True, "meta": {"thang": "2026-10"},
		"giao": {"available": True, "total": 50, "cho_qua_han": {"so_ngay": 3, "tu_ngay": 180, "qua_n": qua_n,
			"rows": [{"hinh_thuc": "Nhất Tín", "cho": qua_n, "qua_n": qua_n}] if qua_n else []},
			"xep": {"chua_xep": chua_xep, "mot_phan": mot_phan, "da_xep": 2},
			"lan_dau": ld if ld is not None else {"so_don": 40, "da_giao": 38, "khach_hen": 1, "hoan": 1, "ty_le": 95.0}},
		"su_co": {"available": True, "dang_mo": mo_qua_n, "mo_qua_n": mo_qua_n, "so_ngay": 7},
		"cuoc": {"available": True, "an": False, "so_chuyen": 30, "so_lai_xe": 6, "tra_bat_thuong": 0, "tra_chuyen_huy": 0,
			"tra_chuyen_huy_tien": 0.0, "sua_tay": 0, **(cuoc or {})},
		"xe": {"available": True, "dang_dung": 5, "can_xu_ly": can or []}}}}


def LD(so_don, ty_le, **k):
	return {"so_don": so_don, "da_giao": 0, "khach_hen": 2, "hoan": 3, "ty_le": ty_le, **k}


print("\nB. vc.cho_qua_han (> 0 vàng / > 10 đỏ) · vc.chua_xep_chuyen (> 0 / > 10)")
K = "vc.cho_qua_han"
eq("0 không; 1 vàng; 10 vàng; 11 đỏ; None không", [muc(vp(qua_n=v), K) for v in (0, 1, 10, 11, None)],
	[None, "vang", "vang", "do", None])
eq("ghi đè 5 / 20: 5 không, 6 vàng, 21 đỏ", [muc(vp(qua_n=v), K, {"vang": 5, "do": 20}) for v in (5, 6, 21)],
	[None, "vang", "do"])
pk = vp(qua_n=4)
pk["van-chuyen"]["overview"]["giao"]["cho_qua_han"]["rows"] = [{"hinh_thuc": None, "qua_n": 4}]
run, sig, pk = mot(pk, K)
eq("hình thức trống → không nêu tên, vẫn báo", (sig[K].severity, [k for _p, k in registry.placeholders(sig[K].detail)]),
	("vang", []))
pk = vp()
pk["van-chuyen"]["overview"]["giao"]["cho_qua_han"] = None
eq("cho_qua_han None → chạy, không báo", muc(pk, K), None)
tat(K, vp(qua_n=5))
khong_chay(K, G, lambda: vp(qua_n=5))
K = "vc.chua_xep_chuyen"
eq("0 không; 1 vàng; 10 vàng; 11 đỏ", [muc(vp(chua_xep=v), K) for v in (0, 1, 10, 11)], [None, "vang", "vang", "do"])
eq("chỉ xếp một phần (chua_xep 0) → không báo", muc(vp(mot_phan=5), K), None)
pk = vp()
pk["van-chuyen"]["overview"]["giao"]["xep"] = None
eq("xep None (site thiếu bảng chuyến) → chạy, không báo", muc(pk, K), None)
run, sig, pk = mot(vp(chua_xep=2), K)
eq("không có đơn xếp một phần → thân không trích số", registry.placeholders(sig[K].detail), [])
tat(K, vp(chua_xep=2))
khong_chay(K, G, lambda: vp(chua_xep=2))


print("\nC. vc.giao_lan_dau (< 90 vàng / < 80 đỏ, đủ 10 đơn)")
K = "vc.giao_lan_dau"
eq("90 không; 89,9 vàng; 80 vàng; 79,9 đỏ; None không", [muc(vp(ld=LD(20, v)), K) for v in (90.0, 89.9, 80.0, 79.9,
	None)], [None, "vang", "vang", "do", None])
eq("9 đơn 50% → chưa đủ mẫu; 10 đơn 50% → đỏ", (muc(vp(ld=LD(9, 50.0)), K), muc(vp(ld=LD(10, 50.0)), K)), (None, "do"))
eq("ghi đè 95 / 85: 92 vàng, 84 đỏ", [muc(vp(ld=LD(20, v)), K, {"vang": 95, "do": 85}) for v in (92.0, 84.0)],
	["vang", "do"])
pk = vp()
pk["van-chuyen"]["overview"]["giao"]["lan_dau"] = None
eq("lan_dau None → chạy, không báo", muc(pk, K), None)
run, sig, pk = mot(vp(ld=LD(20, 70.0, hoan=None)), K)
eq("thiếu số hoàn → thân không trích số", registry.placeholders(sig[K].detail), [])
tat(K, vp(ld=LD(20, 50.0)))
khong_chay(K, G, lambda: vp(ld=LD(20, 50.0)))


print("\nD. vc.su_co_mo (> 0 sự cố mở quá 7 ngày)")
K = "vc.su_co_mo"
eq("0 không; 1 vàng; 30 vẫn vàng (không đỏ mặc định); None không", [muc(vp(mo_qua_n=v), K) for v in (0, 1, 30, None)],
	[None, "vang", "vang", None])
eq("đặt đỏ 5: 6 đỏ", muc(vp(mo_qua_n=6), K, {"do": 5}), "do")
tat(K, vp(mo_qua_n=2))
khong_chay(K, SC, lambda: vp(mo_qua_n=2))


print("\nE. vc.cuoc_canh_bao (mỗi cảnh báo > 0 một khoá; ẩn tiền khi an)")
K = "vc.cuoc_canh_bao"
run, sig, pk = mot(vp(cuoc={"tra_bat_thuong": 2, "tra_chuyen_huy": 1, "tra_chuyen_huy_tien": 500_000, "sua_tay": 4}), K)
eq("3 khoá ổn định theo tên trường", sorted(sig), [f"{K}:sua_tay", f"{K}:tra_bat_thuong", f"{K}:tra_chuyen_huy"])
eq("đủ lái xe: chuyến huỷ nêu tiền", [p for p, _k in registry.placeholders(sig[f"{K}:tra_chuyen_huy"].detail)],
	[f"{CUOC}.tra_chuyen_huy_tien"])
run, sig, pk = mot(vp(cuoc={"an": True, "tra_chuyen_huy": 1, "tra_chuyen_huy_tien": None, "tong": None}), K)
eq("an True: vẫn báo số chuyến, KHÔNG trỏ số tiền nào", (sorted(sig), [p for s in sig.values()
	for p, k in registry.placeholders(s.title + s.detail) if k == "tien"]), ([f"{K}:tra_chuyen_huy"], []))
run, sig, pk = mot(vp(cuoc={"an": True, "tra_chuyen_huy": 1, "tra_chuyen_huy_tien": 999}), K)
eq("an True mà payload còn tiền (phòng hờ) → vẫn không nêu tiền", [k for s in sig.values()
	for _p, k in registry.placeholders(s.title + s.detail)], ["so"])
pk = vp(cuoc={"tra_chuyen_huy": 1, "tra_chuyen_huy_tien": 999})
del pk["van-chuyen"]["overview"]["cuoc"]["an"]
run, sig, pk = mot(pk, K)
eq("thiếu cờ an → coi như ẩn tiền", [k for s in sig.values() for _p, k in registry.placeholders(s.title + s.detail)],
	["so"])
eq("chỉ sửa tay → 1 khoá", muc(vp(cuoc={"sua_tay": 1}), K), [f"{K}:sua_tay"])
eq("không cảnh báo / None (site thiếu cột da_tra_cuoc) → chạy, không báo", (muc(vp(), K),
	muc(vp(cuoc={"tra_bat_thuong": None, "tra_chuyen_huy": None, "sua_tay": None}), K)), (None, None))
eq("ghi đè vàng 3: sửa tay 3 không, 4 có", (muc(vp(cuoc={"sua_tay": 3}), K, {"vang": 3}),
	muc(vp(cuoc={"sua_tay": 4}), K, {"vang": 3})), (None, [f"{K}:sua_tay"]))
tat(K, vp(cuoc={"sua_tay": 2}))
khong_chay(K, CUOC, lambda: vp(cuoc={"sua_tay": 2}))


print("\nF. vc.xe_qua_han (quá hạn đỏ / sắp đến vàng, gộp 1)")
K = "vc.xe_qua_han"


def xe(bien, qua):
	return {"xe": bien, "loai": "Xe tải", "qua_han": qua, "viec": [{"viec": "Đăng kiểm", "muc": "qua_han" if qua
		else "sap_den", "han": "2026-11-01", "con_ngay": 5, "con_km": None}]}


eq("không xe → không; 1 sắp đến → vàng; 1 quá hạn → đỏ", [muc(vp(can=v), K) for v in ([], [xe("29C-1", False)],
	[xe("29C-1", True)])], [None, "vang", "do"])
CAN = [xe("29C-2", False), xe("29C-1", True), xe("29C-3", False), xe("29C-4", True), None, "rác"]
run, sig, pk = mot(vp(can=CAN), K)
s = sig[K]
eq("gộp: 2 quá hạn, 2 sắp đến, đỏ", (list(sig), s.severity, tinh(s, pk, "qua_han"), tinh(s, pk, "sap_den")),
	([K], "do", 2, 2))
eq("có xe quá hạn → chỉ nêu biển số xe quá hạn", [registry.resolve(pk, p) for p, k in
	registry.placeholders(s.detail) if k == "chu"], ["29C-1", "29C-4"])
run, sig, pk = mot(vp(can=[xe(f"30A-{i}", False) for i in range(5)]), K)
eq("chỉ xe sắp đến hạn → nêu tối đa 3 biển số", [registry.resolve(pk, p) for p, k in
	registry.placeholders(sig[K].detail) if k == "chu"], ["30A-0", "30A-1", "30A-2"])
eq("ghi đè đỏ 2: 2 xe quá hạn chỉ vàng", muc(vp(can=CAN), K, {"do": 2}), "vang")
eq("ghi đè vàng 3: 2 xe sắp đến → không", muc(vp(can=[xe("A", False), xe("B", False)]), K, {"vang": 3}), None)
run, sig, pk = mot(vp(can=[{"xe": None, "qua_han": False}]), K)
eq("biển số trống → vẫn báo, thân không nêu tên", (sig[K].severity, [k for _p, k in
	registry.placeholders(sig[K].detail)]), ("vang", []))
pk = vp()
pk["van-chuyen"]["overview"]["xe"]["can_xu_ly"] = None
eq("can_xu_ly None → chạy, không báo", muc(pk, K), None)
tat(K, vp(can=CAN))
khong_chay(K, XE, lambda: vp(can=CAN))

print("\nG. Một khối hỏng không kéo khối kia")
pk = vp(qua_n=3, mo_qua_n=1, cuoc={"sua_tay": 1}, can=[xe("A", True)])
pk["van-chuyen"]["overview"]["giao"] = {"available": False, "error": True}
run = chay(pk)
eq("giao hỏng: 3 quy tắc giao không chạy, 3 quy tắc còn lại vẫn báo", (sorted(run.not_run),
	sorted(s.key for s in run.signals)), (sorted(VC[:3]), ["vc.cuoc_canh_bao:sua_tay", "vc.su_co_mo", "vc.xe_qua_han"]))


# ═══ H. AST, riêng tư, khai báo ══════════════════════════════════════════════
print("\nH. Mã nguồn thuần; lời; khai báo")
FILE = os.path.join(BC_ROOT, "bc", "ai", "rules", "vc.py")
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
o = p1["van-chuyen"]["overview"]
that = set(o["giao"]["cho_qua_han"]["rows"][0]) | set(o["xe"]["can_xu_ly"][0])
khoa = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
	and n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant)}
eq("mọi khoá .get() có trên dòng payload thật", sorted(khoa - that), [])
c("có đủ ca để soát chung", len(MOI) > 40 and {s.rule for s, _ in MOI} == set(VC), len(MOI))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("lời không có tên lái xe / khách / SĐT / email / ngoặc nhọn", sorted({bo_ph(s) for s, _ in MOI if "@" in bo_ph(s)
	or "{" in bo_ph(s) or "}" in bo_ph(s) or any(b in bo_ph(s) for b in test_vc.BI_MAT)}), [])
eq("placeholder chữ chỉ trỏ hình thức giao hoặc biển số", sorted({p for s, _ in MOI for p, k in
	registry.placeholders(s.title + " " + s.detail) if k == "chu" and not re.fullmatch(
	r"van-chuyen\.overview\.(giao\.cho_qua_han\.rows\[0\]\.hinh_thuc|xe\.can_xu_ly\[\d+\]\.xe)", p)}), [])
eq("tinh chỉ là số", sorted({f"{s.key}.{k}" for s, _ in MOI for k, v in s.tinh.items()
	if isinstance(v, bool) or not isinstance(v, (int, float))}), [])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, pk)}" for s, pk in MOI
	if ai_testlib.kiem_loi(s, pk)}), [])
eq("path chỉ thuộc mảng van-chuyen", sorted({p for s, _ in MOI for p in s.paths if registry.section_of(p) != "van-chuyen"}),
	[])
tu = lambda t: len(registry.PLACEHOLDER.sub("X", t).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân là MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khoá tín hiệu: mã quy tắc hoặc vc.cuoc_canh_bao:<trường>", sorted({s.key for s, _ in MOI} - set(VC)
	- {f"vc.cuoc_canh_bao:{k}" for k in ("tra_bat_thuong", "tra_chuyen_huy", "sua_tay")}), [])
eq("khai báo quy tắc", {k: (r.section, r.sources, r.vang, r.do, r.unit, r.lower, r.audience, r.route)
	for k, r in registry.RULES.items()}, {
	"vc.cho_qua_han": ("van-chuyen", (G,), 0, 10, "đơn", False, "lanh-dao", "#/van-chuyen"),
	"vc.chua_xep_chuyen": ("van-chuyen", (G,), 0, 10, "đơn", False, "lanh-dao", "#/van-chuyen"),
	"vc.giao_lan_dau": ("van-chuyen", (G,), 90, 80, "%", True, "lanh-dao", "#/van-chuyen"),
	"vc.su_co_mo": ("van-chuyen", (SC,), 0, None, "sự cố", False, "lanh-dao", "#/van-chuyen"),
	"vc.cuoc_canh_bao": ("van-chuyen", (CUOC,), 0, None, "chuyến", False, "lanh-dao", "#/van-chuyen"),
	"vc.xe_qua_han": ("van-chuyen", (XE,), 0, 0, "xe", False, "lanh-dao", "#/van-chuyen")})
eq("nhãn: có, không chữ số", sorted(k for k, r in registry.RULES.items() if not r.label or r.label == k
	or re.search(r"\d", r.label)), [])
eq("mọi quy tắc thuộc nhóm van-chuyen", {registry.group_of(r.section) for r in registry.RULES.values()}, {"van-chuyen"})
KPI = [f"{G}.total", f"{G}.ty_le_giao", f"{G}.cho_qua_han.qua_n", f"{G}.xep.chua_xep", f"{G}.lan_dau.ty_le",
	f"{SC}.dang_mo", f"{SC}.mo_qua_n", f"{CUOC}.ty_le_doanh_thu"]
eq("KPI đề xuất là số có thật trên payload thật", [p for p in KPI if isinstance(registry.resolve(p1, p, None), bool)
	or not isinstance(registry.resolve(p1, p, None), (int, float))], [])
c.done()
