"""Trợ lý AI — quy tắc nhóm Kho (bc.ai.rules.kho): kho.ton_am, kho.het_han, kho.can_date, kho.khong_ban_duoc,
kho.ton_chet, kho.doi_cao, kho.suc_khoe, kho.kk_lech, kho.xuat_khac_cao, kho.no_bom, kho.gia_von_0 (đặc tả §4.1)
+ đề xuất KPI của 5 mảng Kho & SX.

A: PAYLOAD THẬT — sổ kho gộp như seed_ui_kho.py (reset, bc_settings, K, base, seed của 4 bộ thử Kho, finalize), gọi
bc.api.kho_han / kho_ton / kho_kk / kho_nhap thật dựng pack rồi chạy quy tắc. B–L: pack DỰNG TAY từng quy tắc: vàng,
đỏ, không báo, đúng ngưỡng, ngưỡng ghi đè, tắt, khối nguồn thiếu / _error / available False, None / rỗng / rác,
khoá nhiều tín hiệu ổn định. M: AST (không frappe, không SQL), riêng tư, khai báo. Số kỳ vọng TÍNH TAY.

Chạy: BC_TEST_DB=bc_test_ai_rkho python3 -B test_ai_rules_kho.py
"""
import ast
import copy
import os
import re

from seed import Check, bc_settings, reset
from paths import BC_ROOT

import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.kho")

from seed_kho import K, base  # noqa: E402
import test_kho_han, test_kho_kk, test_kho_nhap, test_kho_ton  # noqa: E402,E401

c = Check()
TR = 1_000_000
KHO = ("kho.ton_am", "kho.het_han", "kho.can_date", "kho.khong_ban_duoc", "kho.ton_chet", "kho.doi_cao",
	"kho.suc_khoe", "kho.kk_lech", "kho.xuat_khac_cao", "kho.no_bom", "kho.gia_von_0")
MOI = []            # mọi (tín hiệu, pack) đã sinh — soát chung ở mục M
AM, HAN, KB = "han-dung.overview.am", "han-dung.overview.han", "han-dung.overview.khong_ban"
SLOW, DOI, HEALTH, TREND = "ton-kho.overview.slow", "ton-kho.overview.doi", "ton-kho.overview.health", "ton-kho.trend.trend"
KK, KKM, IRA, XK = "kiem-ke.overview.kho", "kiem-ke.overview.meta", "kiem-ke.overview.ira", "kiem-ke.overview.xuat_khac"
NB, GV0 = "nhap-tp.overview.no_bom", "nhap-tp.overview.gia_von_0"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def P(path, kind):
	return "{{" + f"{path}|{kind}" + "}}"


def A(key, name):
	return f"{registry.RULES[key.split(':')[0]].section}._ai.{registry.slug(key)}.{name}"


def chay(pack, only=KHO, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def mot(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


def muc(pack, key, ov=None, sig_key=None):
	"""Mức của tín hiệu `sig_key` (mặc định = key) — None: chạy, không báo; 'KHONG-CHAY': không chạy được."""
	run, sig, _ = mot(pack, key, ov)
	if key not in run.ran:
		return "KHONG-CHAY"
	return sig[sig_key or key].severity if (sig_key or key) in sig else None


def muc_all(pack, key, ov=None):
	"""{khoá tín hiệu: mức} — 'KHONG-CHAY' nếu quy tắc không chạy được."""
	run, sig, _ = mot(pack, key, ov)
	return "KHONG-CHAY" if key not in run.ran else {k: s.severity for k, s in sig.items()}


# ═══ A. Payload thật ═════════════════════════════════════════════════════════
print("A. Payload thật — sổ kho gộp 4 bộ thử Kho, hôm nay 27/10/2026")
reset()
bc_settings()
k = K()
base(k)
for t in (test_kho_ton, test_kho_han, test_kho_kk, test_kho_nhap):
	t.seed(k)
k.finalize()
GOI = (("han-dung", "overview", "kho_han.get_overview"), ("ton-kho", "overview", "kho_ton.get_overview"),
	("ton-kho", "trend", "kho_ton.get_trend"), ("kiem-ke", "overview", "kho_kk.get_overview"),
	("nhap-tp", "overview", "kho_nhap.get_overview"), ("sx-tet", "items", "sx.get_items"),
	("sx-tet", "daily", "sx.get_daily_summary"))
THAT = {}
for mang, ten, method in GOI:
	kw = {"year": 2026, "month": 10} if method == "sx.get_daily_summary" else {}
	THAT.setdefault(mang, {})[ten] = ai_testlib.goi(method, **kw)

DOC = [f"{AM}.items", f"{AM}.value_abs", f"{AM}.warehouses", f"{HAN}.buckets", f"{HAN}.can_date.pct",
	f"{HAN}.can_date.value", f"{HAN}.can_date.ngay", f"{KB}.tong", f"{KB}.day_du", f"{SLOW}.total.dead_pct",
	f"{SLOW}.total.dead_value", f"{SLOW}.total.dead_items", f"{SLOW}.dead_days", f"{DOI}.traditional.days",
	f"{DOI}.traditional.value", f"{DOI}.window_days", f"{HEALTH}.failed_reposts", f"{HEALTH}.failed_repost_since",
	f"{HEALTH}.pos_unconsolidated", f"{HEALTH}.si_no_stock_relief.count", f"{HEALTH}.si_no_stock_relief.days",
	f"{HEALTH}.si_no_stock_relief.oldest", f"{TREND}.ledger_bin_diff", f"{TREND}.future_value",
	f"{KK}.tong.qua_30", f"{KK}.tong.qua_90", f"{KK}.tong.chua_kiem", f"{KKM}.nguong.canh_bao", f"{KKM}.nguong.nguy",
	f"{IRA}.ty_le", f"{IRA}.so_ma", f"{IRA}.so_ma_khop", f"{XK}.gia_tri", f"{XK}.so_phieu", f"{KKM}.from", f"{KKM}.to",
	f"{NB}.age_days", f"{NB}.items", f"{GV0}.ton.items", f"{GV0}.nhap_ky.items"]
eq("mọi path quy tắc đọc có trên payload thật", [p for p in DOC if not registry.has(THAT, p)], [])
hh = [b for b in THAT["han-dung"]["overview"]["han"]["buckets"] if b["key"] == "het_han"]
c("han.buckets có đúng một phần key 'het_han'", len(hh) == 1, hh)
eq("mọi khối nguồn khai báo dùng được trên payload thật", [s for r in KHO for s in registry.RULES[r].sources
	if not registry.source_ok(THAT, s)], [])

p1 = copy.deepcopy(THAT)
run = chay(p1)
sig = {s.key: s for s in run.signals}
eq("chạy đủ 11 quy tắc, không quy tắc nào không chạy được", (sorted(run.ran), run.not_run), (sorted(KHO), {}))
eq("tín hiệu + mức trên payload thật (ngưỡng mặc định)", {k2: s.severity for k2, s in sig.items()}, {
	"kho.ton_am": "vang",               # 11 mã âm > 0; phần âm 509.000 < 20 tr → chưa đỏ
	"kho.het_han": "do",                # 644.000 > 0
	"kho.ton_chet": "do",               # 15,5% > 10
	"kho.doi_cao": "do",                # 1.307,2 ngày > 75
	"kho.suc_khoe:dinh_gia_lai": "do", "kho.suc_khoe:hoa_don_chua_tru_kho": "vang",
	"kho.suc_khoe:pos_chua_gop": "vang", "kho.suc_khoe:so_lech_bin": "vang", "kho.suc_khoe:phieu_tuong_lai": "vang",
	"kho.kk_lech:tre": "do", "kho.kk_lech:ira": "vang",
	"kho.no_bom": "do",                 # 31 ngày > 30
	"kho.gia_von_0": "vang"})
# Kiểm số tay theo seed:
# - test_kho_han: hết hạn = A-EXP@TP 30 hộp 300.000 + B-L2@CH2 6 hộp 300.000 + H-L1@TP 4 hộp 44.000 = 644.000, 3 lô.
s = sig["kho.het_han"]
bpath = f"{HAN}.buckets[{THAT['han-dung']['overview']['han']['buckets'].index(hh[0])}]"
eq("het_han: lời trỏ đúng phần hết hạn (tìm theo key) = 644.000 đ, 3 lô",
	(s.title, registry.resolve(p1, f"{bpath}.value"), registry.resolve(p1, f"{bpath}.lots")),
	(f"Còn {P(bpath + '.value', 'tien')} thành phẩm đã hết hạn trong kho", 644_000, 3))
# - test_kho_nhap: nợ BOM đang mở cũ nhất NTP-NB-10 ngày 26/09/2026 → 27/10 − 26/09 = 4 + 27 = 31 ngày > 30 → đỏ.
eq("no_bom: nợ cũ nhất 31 ngày (26/09 → 27/10)", registry.resolve(p1, f"{NB}.age_days"), 31)
# - test_kho_ton: Repost Item Valuation HGC, docstatus 1, Failed: chỉ TON-RIV-6 (15/09) → 1 lượt lỗi, từ 2026-09-15;
#   hoá đơn chưa trừ kho > 7 ngày: NR1 + NR10 = 2.
eq("suc_khoe: 1 lượt tính lại giá vốn lỗi từ 15/09, 2 hoá đơn chưa trừ kho",
	(registry.resolve(p1, f"{HEALTH}.failed_reposts"), registry.resolve(p1, f"{HEALTH}.failed_repost_since"),
	registry.resolve(p1, f"{HEALTH}.si_no_stock_relief.count")), (1, "2026-09-15", 2))
eq("suc_khoe: mục định giá lại lỗi nêu ngày từ", sig["kho.suc_khoe:dinh_gia_lai"].detail.startswith(
	f"Từ {P(HEALTH + '.failed_repost_since', 'ngay')}"), True)
eq("suc_khoe: audience quản trị, mảng ton-kho, route #/ton-kho", {(s.audience, s.section, s.route)
	for k2, s in sig.items() if k2.startswith("kho.suc_khoe")}, {("quan-tri", "ton-kho", "#/ton-kho")})
# kk_lech:tre — số kho tự tính = qua_90 + chua_kiem của payload (đỏ: quá nguy ngày hoặc chưa kiểm lần nào)
tong = THAT["kiem-ke"]["overview"]["kho"]["tong"]
eq("kk_lech:tre: số kho = quá 90 ngày + chưa kiểm (1 + 4 = 5)",
	(registry.resolve(p1, A("kho.kk_lech:tre", "so_kho")), tong["qua_90"] + tong["chua_kiem"]), (5, 5))
eq("mọi tín hiệu thật dựng được lời", {s.key: ai_testlib.kiem_loi(s, p1) for s in run.signals if
	ai_testlib.kiem_loi(s, p1)}, {})
# Ngưỡng ghi đè làm các quy tắc còn lại cũng báo trên số thật: cận date 4,6% > 4; không bán được 2.680.000 ≥ 1 tr;
# xuất khác 1.260.000 ≥ 1 tr
p2 = copy.deepcopy(THAT)
run2 = chay(p2, only=("kho.can_date", "kho.khong_ban_duoc", "kho.xuat_khac_cao"), ov={
	"kho.can_date": {"vang": 4}, "kho.khong_ban_duoc": {"vang": TR}, "kho.xuat_khac_cao": {"vang": TR}})
eq("ghi đè ngưỡng: cận date / không bán được / xuất khác báo vàng trên số thật",
	{s.key: s.severity for s in run2.signals}, {"kho.can_date": "vang", "kho.khong_ban_duoc": "vang",
	"kho.xuat_khac_cao": "vang"})
eq("…và lời dựng được", [ai_testlib.kiem_loi(s, p2) for s in run2.signals], [[], [], []])

# ═══ Pack dựng tay ════════════════════════════════════════════════════════════


def pk(**o):
	"""Pack tối thiểu đủ khối của 11 quy tắc, mặc định KHÔNG báo gì. o: {"path.con": giá trị} ghi đè (path đầy đủ)."""
	p = {
		"han-dung": {"overview": {"available": True,
			"han": {"available": True, "buckets": [
				{"key": "het_han", "value": 0.0, "lots": 0, "items": 0},
				{"key": "d30", "value": 5 * TR, "lots": 2, "items": 2}],
				"can_date": {"ngay": 60, "value": 1 * TR, "pct": 3.0}},
			"khong_ban": {"available": True, "tong": 0.0, "day_du": True},
			"am": {"available": True, "rows": 0, "items": 0, "warehouses": 0, "value_abs": 0.0}}},
		"ton-kho": {"overview": {"available": True,
			"slow": {"available": True, "dead_days": 180, "total": {"dead_pct": 1.0, "dead_value": TR, "dead_items": 1}},
			"doi": {"available": True, "window_days": 90, "traditional": {"value": 10 * TR, "days": 20.0,
				"no_sales": False}},
			"health": {"available": True, "failed_reposts": 0, "failed_repost_since": None, "pos_unconsolidated": 0,
				"si_no_stock_relief": {"count": 0, "oldest": None, "days": 7}}},
			"trend": {"available": True, "trend": {"available": True, "future_value": 0.0, "ledger_bin_diff": 0.0}}},
		"kiem-ke": {"overview": {"available": True, "meta": {"from": "2026-10-01", "to": "2026-10-27",
				"nguong": {"canh_bao": 30, "nguy": 90}},
			"kho": {"available": True, "tong": {"so_kho": 5, "chua_kiem": 0, "qua_30": 0, "qua_90": 0}},
			"ira": {"available": True, "ty_le": 95.0, "so_ma": 20, "so_ma_khop": 19},
			"xuat_khac": {"available": True, "gia_tri": 0.0, "so_phieu": 0}}},
		"nhap-tp": {"overview": {"available": True,
			"no_bom": {"available": True, "age_days": None, "items": 0, "rows": 0},
			"gia_von_0": {"available": True, "ton": {"items": 0}, "nhap_ky": {"items": 0}}}},
	}
	for path, v in o.items():
		*head, last = registry.split_path(path)
		cur = p
		for seg in head:
			cur = cur[seg]
		if v == "XOA":
			del cur[last]
		else:
			cur[last] = v
	return p


def khong_chay(key, block):
	"""Khối nguồn thiếu / _error / available False / None → not_run (không vào ran), không tín hiệu, không ném lỗi."""
	for nhan, hong in (("thiếu khối", "XOA"), ("_error", {"_error": True}), ("available False",
			{"available": False, "error": True}), ("None", None)):
		run = chay(pk(**{block: hong}), only=(key,))
		eq(f"{key}: {block.split('.', 1)[1]} {nhan} → không chạy được", (list(run.not_run), sorted(run.ran),
			run.signals), ([key], [], []))
	run = chay({}, only=(key,))
	eq(f"{key}: pack rỗng → không chạy được", (list(run.not_run), run.signals), ([key], []))


def tat(key, p):
	run = chay(copy.deepcopy(p), only=(key,), ov={key: {"disabled": True}})
	eq(f"{key}: tắt → không sinh, vẫn tính là đã chạy", (run.signals, sorted(run.disabled), sorted(run.ran),
		run.not_run), ([], [key], [key], {}))


eq("pack dựng tay mặc định: 11 quy tắc chạy, không tín hiệu nào", (sorted(chay(pk()).ran), chay(pk()).signals),
	(sorted(KHO), []))

# ═══ B. kho.ton_am ═══════════════════════════════════════════════════════════
print("\nB. kho.ton_am (có mã âm → vàng; giá trị âm ≥ 20 tr → đỏ)")
T = "kho.ton_am"
am = lambda items, val, **kw: pk(**{f"{AM}.items": items, f"{AM}.value_abs": val, f"{AM}.warehouses": 2,  # noqa: E731
	**kw})
eq("1 mã âm, 100.000 đ → vàng", muc(am(1, 100_000), T), "vang")
eq("0 mã âm → không báo", muc(am(0, 0.0), T), None)
eq("đúng 20.000.000 đ → đỏ (≥)", muc(am(3, 20 * TR), T), "do")
eq("19.999.999 đ → vàng", muc(am(3, 20 * TR - 1), T), "vang")
eq("ghi đè vàng = 5 mã: 5 mã → không; 6 mã → vàng", (muc(am(5, TR), T, {"vang": 5}), muc(am(6, TR), T, {"vang": 5})),
	(None, "vang"))
eq("ghi đè đỏ = 30 tr: 25 tr → vàng; 30 tr → đỏ", (muc(am(3, 25 * TR), T, {"do": 30 * TR}),
	muc(am(3, 30 * TR), T, {"do": 30 * TR})), ("vang", "do"))
eq("số mã None, giá trị 25 tr → đỏ (lời chỉ nêu giá trị)", (muc(am(None, 25 * TR), T),
	mot(am(None, 25 * TR), T)[1][T].title), ("do", f"Kho đang tồn âm, giá trị phần âm {P(AM + '.value_abs', 'tien')}"))
eq("None / rác → không báo", [muc(am(None, None), T), muc(am("3", "x"), T), muc(am(True, None), T)], [None] * 3)
_, sg, pp = mot(am(4, 21 * TR), T)
eq("lời đỏ: số mã + giá trị + số kho", (sg[T].title, sg[T].detail.startswith(f"Âm ở {P(AM + '.warehouses', 'so')} kho")),
	(f"{P(AM + '.items', 'so')} mã hàng đang tồn âm, giá trị {P(AM + '.value_abs', 'tien')}", True))
khong_chay(T, AM)
tat(T, am(4, 21 * TR))

# ═══ C. kho.het_han ══════════════════════════════════════════════════════════
print("\nC. kho.het_han (giá trị hết hạn > 0 → đỏ)")
T = "kho.het_han"
hh = lambda v, lots=2, **kw: pk(**{f"{HAN}.buckets[0].value": v, f"{HAN}.buckets[0].lots": lots, **kw})  # noqa: E731
eq("1 đ → đỏ; 0 → không báo", (muc(hh(1.0), T), muc(hh(0.0), T)), ("do", None))
eq("ghi đè đỏ = 1.000: 1.000 → không; 1.001 → đỏ", (muc(hh(1000.0), T, {"do": 1000}), muc(hh(1001.0), T,
	{"do": 1000})), (None, "do"))
dao = pk(**{f"{HAN}.buckets": [{"key": "d30", "value": 9 * TR, "lots": 9}, {"key": "d60", "value": 8 * TR},
	{"key": "het_han", "value": 300_000.0, "lots": 1}]})
_, sg, pp = mot(dao, T)
eq("phần hết hạn ở vị trí 3 → path [2] (tìm theo key, không theo vị trí)", (sg[T].title, sg[T].paths[0]),
	(f"Còn {P(HAN + '.buckets[2].value', 'tien')} thành phẩm đã hết hạn trong kho", f"{HAN}.buckets[2].value"))
eq("không có phần het_han / danh sách rỗng / không phải list → không báo",
	[muc(pk(**{f"{HAN}.buckets": x}), T) for x in ([{"key": "d30", "value": 5.0}], [], "x", None)], [None] * 4)
eq("giá trị None / chuỗi → không báo", (muc(hh(None), T), muc(hh("5"), T)), (None, None))
eq("lô None → lời không nêu số lô", mot(hh(5.0, lots=None), T)[1][T].detail.startswith("Hàng quá hạn"), True)
khong_chay(T, HAN)
tat(T, hh(5.0))

# ═══ D. kho.can_date ═════════════════════════════════════════════════════════
print("\nD. kho.can_date (cận date > 10% vàng / > 20% đỏ giá trị thành phẩm)")
T = "kho.can_date"
cd = lambda x: pk(**{f"{HAN}.can_date.pct": x})  # noqa: E731
eq("10 → không; 10,1 → vàng; 20 → vàng; 20,1 → đỏ", [muc(cd(x), T) for x in (10.0, 10.1, 20.0, 20.1)],
	[None, "vang", "vang", "do"])
eq("ghi đè 5 / 8: 6 → vàng, 9 → đỏ", (muc(cd(6.0), T, {"vang": 5, "do": 8}), muc(cd(9.0), T, {"vang": 5, "do": 8})),
	("vang", "do"))
eq("pct None (không có tồn dương) → không báo", muc(cd(None), T), None)
_, sg, _p = mot(cd(25.0), T)
eq("lời: tỷ lệ + giá trị + số ngày N", (sg[T].title, sg[T].detail.startswith(
	f"{P(HAN + '.can_date.value', 'tien')} hàng chỉ còn không quá {P(HAN + '.can_date.ngay', 'so')} ngày")),
	(f"Hàng cận date chiếm {P(HAN + '.can_date.pct', 'pct')} giá trị thành phẩm", True))
khong_chay(T, HAN)
tat(T, cd(30.0))

# ═══ E. kho.khong_ban_duoc ═══════════════════════════════════════════════════
print("\nE. kho.khong_ban_duoc (≥ 50 tr vàng / ≥ 200 tr đỏ)")
T = "kho.khong_ban_duoc"
kb = lambda x, dd=True: pk(**{f"{KB}.tong": x, f"{KB}.day_du": dd})  # noqa: E731
eq("49.999.999 → không; 50 tr → vàng; 199.999.999 → vàng; 200 tr → đỏ",
	[muc(kb(x), T) for x in (50 * TR - 1, 50 * TR, 200 * TR - 1, 200 * TR)], [None, "vang", "vang", "do"])
eq("ghi đè 10 tr / 20 tr: 10 tr → vàng; 20 tr → đỏ", (muc(kb(10 * TR), T, {"vang": 10 * TR, "do": 20 * TR}),
	muc(kb(20 * TR), T, {"vang": 10 * TR, "do": 20 * TR})), ("vang", "do"))
eq("chưa đủ phần (day_du sai) → vẫn báo, lời nói chưa tính đủ", mot(kb(60 * TR, False), T)[1][T].detail
	.startswith("Số này chưa tính đủ"), True)
eq("tổng None → không báo", muc(kb(None), T), None)
khong_chay(T, KB)
tat(T, kb(300 * TR))

# ═══ F. kho.ton_chet ═════════════════════════════════════════════════════════
print("\nF. kho.ton_chet (tồn chết > 5% vàng / > 10% đỏ)")
T = "kho.ton_chet"
tc = lambda x: pk(**{f"{SLOW}.total.dead_pct": x})  # noqa: E731
eq("5 → không; 5,1 → vàng; 10 → vàng; 10,1 → đỏ", [muc(tc(x), T) for x in (5.0, 5.1, 10.0, 10.1)],
	[None, "vang", "vang", "do"])
eq("ghi đè 1 / 2: 1,5 → vàng", muc(tc(1.5), T, {"vang": 1, "do": 2}), "vang")
eq("None → không báo", muc(tc(None), T), None)
eq("chỉ đọc phần tổng (thành phẩm 50% không làm báo)", muc(pk(**{f"{SLOW}.tp": {"dead_pct": 50.0}}), T), None)
_, sg, _p = mot(tc(12.0), T)
eq("lời: tỷ lệ; thân nêu số mã, giá trị, số ngày tồn chết", (sg[T].title, sg[T].detail.startswith(
	f"{P(SLOW + '.total.dead_items', 'so')} mã, giá trị {P(SLOW + '.total.dead_value', 'tien')}, quá "
	f"{P(SLOW + '.dead_days', 'so')} ngày")),
	(f"Tồn chết chiếm {P(SLOW + '.total.dead_pct', 'pct')} giá trị hàng ở kho bán được", True))
khong_chay(T, SLOW)
tat(T, tc(12.0))

# ═══ G. kho.doi_cao ══════════════════════════════════════════════════════════
print("\nG. kho.doi_cao (số ngày tồn truyền thống > 45 vàng / > 75 đỏ)")
T = "kho.doi_cao"
dc = lambda x: pk(**{f"{DOI}.traditional.days": x})  # noqa: E731
eq("45 → không; 45,1 → vàng; 75 → vàng; 75,1 → đỏ", [muc(dc(x), T) for x in (45.0, 45.1, 75.0, 75.1)],
	[None, "vang", "vang", "do"])
eq("không bán trong kỳ (days None) → không báo", muc(dc(None), T), None)
eq("ghi đè 30 / 40: 35 → vàng", muc(dc(35.0), T, {"vang": 30, "do": 40}), "vang")
eq("phần Tết không xét", muc(pk(**{f"{DOI}.tet": {"days": 500.0}}), T), None)
khong_chay(T, DOI)
tat(T, dc(100.0))

# ═══ H. kho.suc_khoe ═════════════════════════════════════════════════════════
print("\nH. kho.suc_khoe (quản trị; mỗi mục một khoá)")
T = "kho.suc_khoe"
SK = {f"{T}:{m}" for m in ("dinh_gia_lai", "hoa_don_chua_tru_kho", "pos_chua_gop", "so_lech_bin", "phieu_tuong_lai")}
het = pk(**{f"{HEALTH}.failed_reposts": 2, f"{HEALTH}.failed_repost_since": "2026-09-01",
	f"{HEALTH}.pos_unconsolidated": 4, f"{HEALTH}.si_no_stock_relief": {"count": 3, "oldest": "2026-09-10", "days": 7},
	f"{TREND}.ledger_bin_diff": -15_000.0, f"{TREND}.future_value": 2_000_000.0})
eq("đủ 5 mục: định giá lại lỗi đỏ, còn lại vàng", muc_all(het, T), {f"{T}:dinh_gia_lai": "do",
	f"{T}:hoa_don_chua_tru_kho": "vang", f"{T}:pos_chua_gop": "vang", f"{T}:so_lech_bin": "vang",
	f"{T}:phieu_tuong_lai": "vang"})
eq("chạy lại → cùng bộ khoá (ổn định, không theo vị trí)", set(muc_all(het, T)), SK)
eq("tất cả bằng 0 → không báo", muc_all(pk(), T), {})
eq("lệch sổ 0,5 đ → không; −1 đ → vàng (|lệch| ≥ 1 như màn)", (muc_all(pk(**{f"{TREND}.ledger_bin_diff": 0.5}), T),
	muc_all(pk(**{f"{TREND}.ledger_bin_diff": -1.0}), T)), ({}, {f"{T}:so_lech_bin": "vang"}))
eq("phiếu tương lai âm −100 đ → vàng", muc_all(pk(**{f"{TREND}.future_value": -100.0}), T),
	{f"{T}:phieu_tuong_lai": "vang"})
eq("hoá đơn chưa trừ kho 1 → vàng", muc_all(pk(**{f"{HEALTH}.si_no_stock_relief.count": 1}), T),
	{f"{T}:hoa_don_chua_tru_kho": "vang"})
_, sg, _p = mot(pk(**{f"{HEALTH}.failed_reposts": 1}), T)
eq("định giá lại lỗi không có ngày → lời không nêu ngày", sg[f"{T}:dinh_gia_lai"].detail.startswith("Giá trị tồn"), True)
mat = pk(**{HEALTH: {"available": True}, f"{TREND}.ledger_bin_diff": "XOA", f"{TREND}.future_value": "XOA"})
eq("mục health bị bỏ (thiếu bảng / lỗi) → không báo, vẫn chạy", muc_all(mat, T), {})
eq("rác / None → không báo", muc_all(pk(**{f"{HEALTH}.failed_reposts": None, f"{HEALTH}.pos_unconsolidated": "3",
	f"{HEALTH}.si_no_stock_relief": None, f"{TREND}.ledger_bin_diff": None, f"{TREND}.future_value": True}), T), {})
khong_chay(T, HEALTH)
khong_chay(T, TREND)
khong_chay(T, "ton-kho.trend")
tat(T, het)
eq("ngưỡng ghi đè không làm đổi mục (không có ngưỡng)", muc_all(het, T, {"vang": 99, "do": 99}), muc_all(het, T))

# ═══ I. kho.kk_lech ══════════════════════════════════════════════════════════
print("\nI. kho.kk_lech (:tre theo meta.nguong — số ngày; :ira độ chính xác < 80%)")
T = "kho.kk_lech"
kt = lambda q30=0, q90=0, chua=0, **kw: pk(**{f"{KK}.tong.qua_30": q30, f"{KK}.tong.qua_90": q90,  # noqa: E731
	f"{KK}.tong.chua_kiem": chua, **kw})
eq("1 kho quá 90 ngày → :tre đỏ", muc_all(kt(q30=1, q90=1), T), {f"{T}:tre": "do"})
eq("2 kho chưa kiểm lần nào → :tre đỏ", muc_all(kt(chua=2), T), {f"{T}:tre": "do"})
eq("2 kho quá 30 ngày (không quá 90) → :tre vàng", muc_all(kt(q30=2), T), {f"{T}:tre": "vang"})
eq("không kho nào trễ → không báo", muc_all(kt(), T), {})
_, sg, pp = mot(kt(q30=3, q90=1, chua=2), T)
eq(":tre đỏ: số kho tự tính = quá 90 + chưa kiểm = 1 + 2 = 3", (sg[f"{T}:tre"].title,
	registry.resolve(pp, A(f"{T}:tre", "so_kho"))), (f"{P(A(T + ':tre', 'so_kho'), 'so')} kho quá lâu chưa kiểm kê", 3))
eq(":tre đỏ nêu ngưỡng nguy có sẵn trong meta", P(f"{KKM}.nguong.nguy", "so") in sg[f"{T}:tre"].detail, True)
_, sg, _p = mot(kt(q30=2), T)
eq(":tre vàng: lời nêu số kho + ngưỡng cảnh báo trong meta", sg[f"{T}:tre"].title,
	f"{P(KK + '.tong.qua_30', 'so')} kho quá {P(KKM + '.nguong.canh_bao', 'so')} ngày chưa kiểm kê")
ira = lambda x, **kw: pk(**{f"{IRA}.ty_le": x, **kw})  # noqa: E731
eq("độ chính xác 80 → không; 79,9 → :ira vàng", (muc_all(ira(80.0), T), muc_all(ira(79.9), T)), ({},
	{f"{T}:ira": "vang"}))
eq("ghi đè đỏ 50: 49 → đỏ; 60 → vàng", (muc_all(ira(49.0), T, {"do": 50}), muc_all(ira(60.0), T, {"do": 50})),
	({f"{T}:ira": "do"}, {f"{T}:ira": "vang"}))
eq("ghi đè vàng 60: 70 → không", muc_all(ira(70.0), T, {"vang": 60}), {})
eq("chưa có lần kiểm (ty_le None) → không báo", muc_all(ira(None), T), {})
eq("cả hai cùng báo: 2 khoá", muc_all(kt(q30=1, **{f"{IRA}.ty_le": 10.0}), T), {f"{T}:tre": "vang", f"{T}:ira": "vang"})
khong_sx = kt(q90=1, **{IRA: {"available": False, "reason": "khong_sx"}})
eq("site không có app Sản xuất (ira tắt): vẫn chạy, chỉ còn :tre", muc_all(khong_sx, T), {f"{T}:tre": "do"})
for nhan, hong in (("_error", {"_error": True}), ("lỗi khối", {"available": False, "error": True}), ("thiếu", "XOA"),
		("None", None)):
	run = chay(kt(q90=1, **{IRA: hong}), only=(T,))
	eq(f"ira {nhan} → không chạy được (giữ tín hiệu cũ), không ném lỗi", (sorted(run.not_run), run.ran, run.signals),
		([T], set(), []))
eq("meta thiếu ngưỡng: tre vàng không nêu được ngưỡng → không báo vàng; đỏ vẫn báo",
	(muc_all(kt(q30=2, **{f"{KKM}.nguong": {}}), T), muc_all(kt(q90=1, **{f"{KKM}.nguong": {}}), T)),
	({}, {f"{T}:tre": "do"}))
khong_chay(T, KK)
khong_chay(T, KKM)
tat(T, kt(q90=1, **{f"{IRA}.ty_le": 10.0}))

# ═══ J. kho.xuat_khac_cao ════════════════════════════════════════════════════
print("\nJ. kho.xuat_khac_cao (≥ 30 tr trong tháng → vàng)")
T = "kho.xuat_khac_cao"
xk = lambda x: pk(**{f"{XK}.gia_tri": x, f"{XK}.so_phieu": 4})  # noqa: E731
eq("29.999.999 → không; 30 tr → vàng; 1 tỷ → vẫn vàng (không có mốc đỏ)",
	[muc(xk(x), T) for x in (30 * TR - 1, 30 * TR, 1000 * TR)], [None, "vang", "vang"])
eq("ghi đè đỏ 100 tr → 100 tr đỏ", muc(xk(100 * TR), T, {"do": 100 * TR}), "do")
eq("None → không báo", muc(xk(None), T), None)
eq("lời nêu khoảng ngày từ meta", P(f"{KKM}.from", "ngay") in mot(xk(40 * TR), T)[1][T].detail, True)
khong_chay(T, XK)
tat(T, xk(40 * TR))

# ═══ K. kho.no_bom ═══════════════════════════════════════════════════════════
print("\nK. kho.no_bom (nợ BOM cũ nhất > 7 ngày vàng / > 30 ngày đỏ)")
T = "kho.no_bom"
nb = lambda x: pk(**{f"{NB}.age_days": x, f"{NB}.items": 2})  # noqa: E731
eq("7 → không; 8 → vàng; 30 → vàng; 31 → đỏ", [muc(nb(x), T) for x in (7, 8, 30, 31)], [None, "vang", "vang", "do"])
eq("không có nợ (None) → không báo", muc(nb(None), T), None)
eq("ghi đè 3 / 5: 4 → vàng, 6 → đỏ", (muc(nb(4), T, {"vang": 3, "do": 5}), muc(nb(6), T, {"vang": 3, "do": 5})),
	("vang", "do"))
khong_chay(T, NB)
tat(T, nb(40))

# ═══ L. kho.gia_von_0 ════════════════════════════════════════════════════════
print("\nL. kho.gia_von_0 (có mã thành phẩm giá vốn 0 → vàng)")
T = "kho.gia_von_0"
gv = lambda ton, nhap: pk(**{f"{GV0}.ton.items": ton, f"{GV0}.nhap_ky.items": nhap})  # noqa: E731
eq("0 / 0 → không; tồn 1 → vàng; nhập 1 → vàng", [muc(gv(*x), T) for x in ((0, 0), (1, 0), (0, 1))],
	[None, "vang", "vang"])
eq("tồn 2 → lời theo tồn; chỉ nhập 3 → lời theo nhập", (mot(gv(2, 0), T)[1][T].title, mot(gv(0, 3), T)[1][T].title),
	(f"{P(GV0 + '.ton.items', 'so')} mã thành phẩm đang tồn mà chưa có giá vốn",
	f"{P(GV0 + '.nhap_ky.items', 'so')} mã thành phẩm nhập kho trong tháng không có đơn giá"))
eq("cả hai → thân nêu số mã nhập", P(f"{GV0}.nhap_ky.items", "so") in mot(gv(2, 3), T)[1][T].detail, True)
eq("ghi đè vàng 2: tồn 2 → không; tồn 3 → vàng", (muc(gv(2, 0), T, {"vang": 2}), muc(gv(3, 0), T, {"vang": 2})),
	(None, "vang"))
eq("None / rác → không báo", (muc(gv(None, None), T), muc(gv("2", []), T)), (None, None))
khong_chay(T, GV0)
tat(T, gv(2, 2))

# ═══ M. AST, riêng tư, khai báo ══════════════════════════════════════════════
print("\nM. Mã nguồn quy tắc thuần; lời không lộ tên; khai báo đúng đặc tả")
FILE = os.path.join(BC_ROOT, "bc", "ai", "rules", "kho.py")
src = open(FILE, encoding="utf-8").read()
tree = ast.parse(src)
imp = set()
for n in ast.walk(tree):
	if isinstance(n, ast.Import):
		imp |= {a.name for a in n.names}
	elif isinstance(n, ast.ImportFrom):
		imp.add(n.module)
eq("chỉ import thư viện chuẩn + bc.ai.registry", sorted(imp), ["__future__", "bc.ai.registry", "datetime", "math"])
ten_goi = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree)
	if isinstance(n, ast.Attribute)}
eq("không frappe / db / sql / get_all / get_value / open / eval / exec", sorted(ten_goi & {"frappe", "db", "sql",
	"get_all", "get_list", "get_value", "get_doc", "open", "eval", "exec", "__import__", "importlib", "requests"}), [])
SQL = re.compile(r"\b(select|insert|update|delete|alter|drop)\b[\s\S]*\b(from|into|set|table)\b|`tab", re.I)
doc = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
	and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
eq("không chuỗi SQL", [n.value[:40] for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
	and id(n) not in doc and SQL.search(n.value)], [])
c("có đủ ca để soát chung", len(MOI) > 80 and {s.rule for s, _ in MOI} == set(KHO), (len(MOI), {s.rule for s, _ in MOI}))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("không placeholder kiểu chữ (quy tắc Kho không nêu tên nào)", sorted({p for s, _ in MOI
	for p, k2 in registry.placeholders(s.title + " " + s.detail) if k2 == "chu"}), [])
RIENG = list(test_kho_ton.PRIVATE) + ["@", "{", "}"]
eq("lời / số tự tính không chứa email, tên, ghi chú riêng của seed, ký tự placeholder hỏng",
	sorted({bo_ph(s) for s, _ in MOI if any(t in bo_ph(s) for t in RIENG)}
	| {f"{s.key}.{k2}={v!r}" for s, _ in MOI for k2, v in s.tinh.items() if isinstance(v, bool)
	or not isinstance(v, (int, float))}), [])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, p)}" for s, p in MOI
	if ai_testlib.kiem_loi(s, p)}), [])
eq("path của tín hiệu chỉ thuộc mảng của chính nó", sorted({f"{s.key}: {p}" for s, _ in MOI for p in s.paths
	if registry.section_of(p) != s.section}), [])
tu = lambda t: len(registry.PLACEHOLDER.sub("X", t).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân là MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khoá tín hiệu: <rule> hoặc kho.suc_khoe:<mục> / kho.kk_lech:<tre|ira>", sorted({s.key for s, _ in MOI}
	- (set(KHO) - {"kho.suc_khoe", "kho.kk_lech"}) - SK - {"kho.kk_lech:tre", "kho.kk_lech:ira"}), [])
eq("khai báo quy tắc (mảng, nguồn, ngưỡng vàng / đỏ, chiều, audience)", {k2: (r.section, r.sources, r.vang, r.do,
	r.lower, r.audience) for k2, r in registry.RULES.items()}, {
	"kho.ton_am": ("han-dung", (AM,), 0, 20 * TR, False, "lanh-dao"),
	"kho.het_han": ("han-dung", (HAN,), None, 0, False, "lanh-dao"),
	"kho.can_date": ("han-dung", (HAN,), 10, 20, False, "lanh-dao"),
	"kho.khong_ban_duoc": ("han-dung", (KB,), 50 * TR, 200 * TR, False, "lanh-dao"),
	"kho.ton_chet": ("ton-kho", (SLOW,), 5, 10, False, "lanh-dao"),
	"kho.doi_cao": ("ton-kho", (DOI,), 45, 75, False, "lanh-dao"),
	"kho.suc_khoe": ("ton-kho", (HEALTH, TREND), None, None, False, "quan-tri"),
	"kho.kk_lech": ("kiem-ke", (KK, KKM), 80, None, True, "lanh-dao"),
	"kho.xuat_khac_cao": ("kiem-ke", (XK,), 30 * TR, None, False, "lanh-dao"),
	"kho.no_bom": ("nhap-tp", (NB,), 7, 30, False, "lanh-dao"),
	"kho.gia_von_0": ("nhap-tp", (GV0,), 0, None, False, "lanh-dao")})

# ═══ N. KPI đề xuất (path có thật trên payload thật, là số) ═══════════════════
print("\nN. KPI đề xuất")
KPIS = [
	("ton-kho.overview.value.totals.value", "tien", "Tổng giá trị tồn kho"),
	("ton-kho.overview.value.totals.value_sellable", "tien", "Tồn ở kho bán được"),
	("ton-kho.overview.value.totals.value_unsellable", "tien", "Tồn ở kho trả về & cách ly"),
	("ton-kho.overview.value.tp.value", "tien", "Tồn thành phẩm"),
	("ton-kho.overview.doi.traditional.days", "so", "Số ngày tồn hàng truyền thống"),
	("ton-kho.overview.slow.total.slow_pct", "pct", "Tỷ lệ hàng chậm luân chuyển"),
	("ton-kho.overview.slow.total.dead_pct", "pct", "Tỷ lệ tồn chết"),
	("ton-kho.overview.tet_stock.value", "tien", "Tồn hàng Tết"),
	("han-dung.overview.khong_ban.het_han.value", "tien", "Thành phẩm đã hết hạn"),
	("han-dung.overview.han.can_date.value", "tien", "Hàng cận date"),
	("han-dung.overview.han.can_date.pct", "pct", "Tỷ lệ cận date / thành phẩm"),
	("han-dung.overview.khong_ban.tong", "tien", "Tồn không bán được"),
	("han-dung.overview.am.value_abs", "tien", "Giá trị tồn âm"),
	("han-dung.overview.am.items", "so", "Số mã tồn âm"),
	("han-dung.overview.khong_ban.thu_hoi.value", "tien", "Lô đang thu hồi"),
	("kiem-ke.overview.ira.ty_le", "pct", "Độ chính xác tồn"),
	("kiem-ke.overview.kho.tong.chua_kiem", "so", "Kho chưa kiểm kê lần nào"),
	("kiem-ke.overview.kho.tong.qua_30", "so", "Kho quá 30 ngày chưa kiểm"),
	("kiem-ke.overview.kho.tong.qua_90", "so", "Kho quá 90 ngày chưa kiểm"),
	("kiem-ke.overview.tong.gia_tri", "tien", "Tổng điều chỉnh kho trong tháng"),
	("kiem-ke.overview.xuat_khac.gia_tri", "tien", "Xuất khác trong tháng"),
	("kiem-ke.overview.dang_dem.so_phieu", "so", "Phiếu kiểm kê đang đếm dở"),
	("nhap-tp.overview.nhap.total.value", "tien", "Giá trị nhập thành phẩm trong tháng"),
	("nhap-tp.overview.cho_duyet.count", "so", "Phiếu nhập TP chờ duyệt"),
	("nhap-tp.overview.no_bom.items", "so", "Mã đang nợ BOM"),
	("nhap-tp.overview.no_bom.age_days", "so", "Tuổi nợ BOM cũ nhất"),
	("nhap-tp.overview.no_bom.value_tam", "tien", "Giá trị nợ BOM (giá tạm)"),
	("nhap-tp.overview.nvl_treo.value", "tien", "Nguyên liệu treo chưa trừ"),
	("nhap-tp.overview.gia_von_0.ton.items", "so", "Mã thành phẩm tồn giá vốn 0"),
]
eq("mọi KPI có trên payload thật và là số", [p for p, _k, _l in KPIS if not registry.has(THAT, p)
	or isinstance(registry.resolve(THAT, p), bool) or not isinstance(registry.resolve(THAT, p), (int, float))], [])
eq("sx-tet: payload chỉ có danh sách (không số tổng) → không KPI", sorted(
	k2 for k2, v in {**THAT["sx-tet"]["items"], **{f"d.{a}": b for a, b in THAT["sx-tet"]["daily"].items()}}.items()
	if isinstance(v, (int, float)) and not isinstance(v, bool)), [])

c.done()
