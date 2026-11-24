"""Trợ lý AI P2 — detector kpi + quy tắc kpi.lech_chuan + phân loại KPI_TICH_LUY (hợp đồng P2 §3.2).

A: phân loại (KPI_TICH_LUY ⊂ KPIS, đúng tập đã đọc từ method gốc; KPI_THEO_KY rời KPI_TICH_LUY). B: detector trên bảng
BC AI Run thật: cửa sổ 28 ngày trước hôm nay (đúng biên), ảnh chụp muộn nhất mỗi ngày, chỉ dòng tổng ok của lượt ngày /
tay, ≥ 14 ngày, KPI cộng dồn / tỷ lệ theo kỳ bị bỏ, số tính tay. C: quy tắc trên gói dựng tay: ngưỡng 3 MAD ngặt, MAD
tối thiểu 1% trung vị, sàn theo kiểu (tiền 1 triệu, số 1, % 0,5) và 5% trung vị, chuỗi phẳng không báo, đỏ chỉ khi
đặt, mảng / route / số tự tính theo KPI, nguồn lỗi, E5. D: run_daily thật: tín hiệu nằm ở nhóm của KPI (tai-chinh),
người xem mất nó khi ẩn mảng của KPI, khối kpi không vào đề bài nào.

Chạy: BC_TEST_DB=bc_test_ai_p2b_kpi python3 -B test_ai_kpi.py
"""
import copy
import datetime
import json
import os
import re
import socket

from seed import Check, bc_settings, child, insert, reset, single
from paths import BC_ROOT

import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.ks", "bc.ai.detectors.chung_tu", "bc.ai.detectors.gia",
	"bc.ai.detectors.kpi")

import frappe  # noqa: E402
import frappe.utils  # noqa: E402
from bc.ai import redact, render  # noqa: E402
from bc.ai.detectors import kpi as KD  # noqa: E402

c = Check()
T = "tro-ly"
K = "kpi.lech_chuan"
NOW = frappe.utils.now_datetime()          # 27/10/2026 10:30
TODAY = NOW.date()
KEY = "sk-ant-api03-KHOAGIA-p2b-kpi-5Tz"
PCT, TIEN, SO = "cong-no.receivables.kpis.overdue_pct", "cong-no.receivables.kpis.overdue", \
	"cong-no.receivables.kpis.overdue_customers"
TL, TK = "tong-quan.summary.rows[0].sales", "tong-quan.summary.meta.growth.net"
QUA30 = "kiem-ke.overview.kho.tong.qua_30"
MOI = []


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def d(s):
	return datetime.date.fromisoformat(s)


def dt(s):
	return datetime.datetime.fromisoformat(s)


class MangBiChan(RuntimeError):
	pass


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


socket.socket.connect, socket.socket.connect_ex = _chan(socket.socket.connect), _chan(socket.socket.connect_ex)

# ═══ A. Phân loại ════════════════════════════════════════════════════════════
print("A. KPI_TICH_LUY / KPI_THEO_KY")
P_KPI = {p for p, _k, _l in registry.KPIS}
eq("70 KPI", len(registry.KPIS), 70)
eq("KPI_TICH_LUY ⊂ KPIS, KPI_THEO_KY ⊂ KPIS, rời nhau", (registry.KPI_TICH_LUY - P_KPI, KD.KPI_THEO_KY - P_KPI,
	registry.KPI_TICH_LUY & KD.KPI_THEO_KY), (set(), set(), set()))
eq("KPI_TICH_LUY = tổng / đếm luỹ kế trong kỳ (đọc từng method gốc)", sorted(registry.KPI_TICH_LUY), sorted([
	"tong-quan.summary.rows[0].sales", "tong-quan.summary.rows[0].returns", "tong-quan.summary.rows[0].net",
	"tong-quan.channels.rows[0].sales", "tong-quan.channels.rows[1].sales", "kiem-ke.overview.tong.gia_tri",
	"kiem-ke.overview.xuat_khac.gia_tri", "nhap-tp.overview.nhap.total.value", "van-chuyen.overview.giao.total",
	"nhan-su.overview.bien_dong.vao", "nhan-su.overview.bien_dong.nghi"]))
eq("KPI_THEO_KY = tỷ lệ trên kỳ tới hôm nay", sorted(KD.KPI_THEO_KY), sorted([
	"tong-quan.summary.rows[0].return_rate", "tong-quan.summary.meta.growth.sales", "tong-quan.summary.meta.growth.net",
	"tinh-thanh.provinces.rows[0].pct", "van-chuyen.overview.giao.ty_le_giao", "van-chuyen.overview.giao.lan_dau.ty_le",
	"van-chuyen.overview.cuoc.ty_le_doanh_thu"]))
c("KPI_TICH_LUY là frozenset", isinstance(registry.KPI_TICH_LUY, frozenset))
audit = open(os.path.join(BC_ROOT, "docs", "ai-rules-audit.md"), encoding="utf-8").read()
eq("docs/ai-rules-audit.md ghi phân loại của ĐỦ 70 path", sorted(p for p in P_KPI if f"`{p}`" not in audit), [])
eq("NO_SEND có (tro-ly, kpi)", (T, "kpi") in registry.NO_SEND, True)

# ═══ B. Detector ═════════════════════════════════════════════════════════════
print("\nB. Detector kpi trên BC AI Run thật — hôm nay 27/10, lịch sử [29/9, 26/10]")
reset(only={"BC AI Run", "BC AI Insight", "BC AI Brief", "BC AI Rule", "BC AI Model Price", "BC Tet Date",
	"BC Hidden Item", "BC Share Link", "Customer", "Supplier", "Sales Invoice", "Sales Invoice Item", "Purchase Invoice",
	"Purchase Invoice Item", "Payment Entry", "Journal Entry", "Stock Entry", "Customer Group"})
bc_settings()
_n = iter(range(1, 10000))


NULL = object()


def run(when, kpis, *, status="ok", run_type="ngay", step="tong", raw=None):
	insert("BC AI Run", name=f"RUN-{next(_n):04d}", step=step, status=status, run_type=run_type, started=when,
		finished=when + datetime.timedelta(minutes=5), creation=when, modified=when,
		kpis=None if raw is NULL else raw if raw is not None else json.dumps(kpis))


# overdue_pct (pct) 20 ngày 7/10 … 26/10: trung vị 20, MAD 1 (8 số lệch 0, 8 số lệch 1, 4 số lệch 2).
GT_PCT = [20, 21, 19, 20, 22, 18, 20, 21, 19, 20, 20, 21, 19, 20, 22, 18, 20, 21, 19, 20]
NGAY20 = [d("2026-10-07") + datetime.timedelta(days=i) for i in range(20)]
# overdue (tiền): 29/9 (đầu biên — ngày thứ 14) + 14/10 … 26/10 (13 ngày), đều 100 triệu.
# overdue_customers (số): chỉ 13 ngày 14/10 … 26/10 → thiếu lịch sử. Cộng dồn (TL) và tỷ lệ theo kỳ (TK): đủ 20 ngày.
for i, ng in enumerate(NGAY20):
	k = {PCT: GT_PCT[i], TL: 1e9 + i, TK: 5.0, QUA30: 2}
	if ng >= d("2026-10-14"):
		k.update({TIEN: 100_000_000, SO: 3})
	run(datetime.datetime.combine(ng, datetime.time(5, 30)), k)
run(dt("2026-09-29 00:00:00"), {TIEN: 100_000_000})                  # đầu biên: vào lịch sử
run(dt("2026-09-28 23:59:59"), {TIEN: 1, SO: 1, PCT: 99})              # ngoài cửa sổ
# Cùng ngày 26/10: lượt muộn hơn (14:00) thắng lượt 05:30 (giá trị lạ ở 05:30 không được dùng).
run(dt("2026-10-26 04:00:00"), {PCT: 77, TIEN: 1})
run(dt("2026-10-26 14:00:00"), {PCT: 20, TIEN: 100_000_000, SO: 3, TL: 1e9 + 19, TK: 5.0, QUA30: 2})
# Không vào lịch sử: lượt hỏng, bản tin tuần / tháng / hỏi đáp, dòng gọi mô hình, lượt HÔM NAY, JSON hỏng.
run(dt("2026-10-25 20:00:00"), {PCT: 555}, status="loi")
for rt in ("tuan", "thang", "hoi-dap"):
	run(dt("2026-10-25 21:00:00"), {PCT: 666}, run_type=rt)
run(dt("2026-10-25 22:00:00"), {PCT: 777}, step="tai-chinh")
run(dt("2026-10-27 01:00:00"), {PCT: 888})
run(dt("2026-10-24 23:00:00"), None, raw="null")                       # JSON null / danh sách / NULL: bỏ dòng,
run(dt("2026-10-23 23:00:00"), None, raw="[1, 2]")                     # ảnh chụp sớm hơn trong ngày vẫn giữ
run(dt("2026-10-22 23:00:00"), None, raw=NULL)
run(dt("2026-10-10 23:30:00"), {PCT: "20", TIEN: True})                # không phải số → bỏ giá trị, ngày vẫn tính

ls = KD.lich_su(TODAY)
eq("lịch sử: 29/9 + 7/10 … 26/10 (21 ngày), không ngày ngoài cửa sổ / hôm nay", sorted(ls), sorted([d("2026-09-29")]
	+ NGAY20))
eq("cùng ngày: lượt muộn nhất thắng (26/10 14:00); lượt hỏng / tuần / tháng / hỏi đáp / dòng nhóm không vào",
	(ls[d("2026-10-26")][PCT], ls[d("2026-10-25")][PCT]), (20, GT_PCT[18]))
eq("10/10: dòng 23:30 (giá trị không phải số) thắng; 22, 23, 24/10: dòng NULL / danh sách / null muộn hơn KHÔNG đè "
	"ảnh chụp 05:30", (ls[d("2026-10-10")], ls[d("2026-10-22")][PCT], ls[d("2026-10-23")][PCT], ls[d("2026-10-24")][PCT]),
	({PCT: "20", TIEN: True}, GT_PCT[15], GT_PCT[16], GT_PCT[17]))

PACK_NAY = {"cong-no": {"receivables": {"kpis": {"overdue_pct": 23.5, "overdue": 104_000_000, "overdue_customers": 9}}},
	"tong-quan": {"summary": {"rows": [{"sales": 9e12}], "meta": {"growth": {"net": -80.0}}}},
	"kiem-ke": {"overview": {"kho": {"tong": {"qua_30": 2}}}}}
out = KD.d_kpi({"now": NOW, "today": TODAY, "pack": PACK_NAY})
rows = {r["path"]: r for r in out["rows"]}
eq("so_ngay = 21 ngày có ảnh chụp; cửa sổ 28; tối thiểu 14", (out["so_ngay"], out["cua_so"], out["ngay_min"]), (21, 28, 14))
eq("rows: overdue_pct (20 ngày, 10/10 bỏ giá trị chuỗi → 19), overdue (14 ngày, gồm 29/9), kho quá 30 ngày; KHÔNG "
	"overdue_customers (13 ngày), cộng dồn, tỷ lệ theo kỳ", sorted(rows), sorted([PCT, TIEN, QUA30]))
# overdue_pct: 10/10 = GT_PCT[3] = 20 bị thay bởi chuỗi "20" → bỏ; còn 19 số, trung vị 20, MAD 1 (7 số lệch 0, 8 lệch 1).
v19 = [v for i, v in enumerate(GT_PCT) if i != 3]
eq("overdue_pct: đúng từng trường (trung vị 20, MAD 1, lệch 3,5 = 3,5 MAD)", rows.get(PCT), {"path": PCT, "kieu": "pct",
	"nhan": "Tỷ lệ nợ quá hạn", "hom_nay": 23.5, "trung_vi": 20, "mad": 1, "lech": 3.5, "so_mad": 3.5, "n": len(v19)})
eq("overdue: trung vị 100 triệu, MAD 0 → mẫu = 1% = 1 triệu → 4 MAD", {k: rows.get(TIEN, {}).get(k) for k in ("trung_vi",
	"mad", "lech", "so_mad", "n")}, {"trung_vi": 100_000_000, "mad": 0, "lech": 4_000_000, "so_mad": 4.0, "n": 14})
eq("chuỗi phẳng, hôm nay bằng trung vị → lệch 0, trung vị 0 không chia (so_mad None khi mẫu 0)",
	{k: rows.get(QUA30, {}).get(k) for k in ("trung_vi", "mad", "lech", "so_mad")},
	{"trung_vi": 2, "mad": 0, "lech": 0, "so_mad": 0.0})
eq("pack None → không lỗi, không dòng", KD.d_kpi({"now": NOW, "today": TODAY, "pack": None})["rows"], [])

# ═══ C. Quy tắc ══════════════════════════════════════════════════════════════
print("\nC. kpi.lech_chuan trên gói dựng tay")


def chay(pack, ov=None):
	run_ = registry.run_rules(pack, overrides={K: ov} if ov else None, only=(K,))
	MOI.extend((s, pack) for s in run_.signals)
	return run_


def dat(p, path, x):
	"""Đặt giá trị x tại path (tạo dict / danh sách trung gian)."""
	segs = registry.split_path(path)
	cur = p
	for i, seg in enumerate(segs[:-1]):
		nxt = segs[i + 1]
		if isinstance(seg, int):
			cur = cur[seg]
			continue
		if isinstance(nxt, int):
			cur = cur.setdefault(seg, [])
			while len(cur) <= nxt:
				cur.append({})
		else:
			cur = cur.setdefault(seg, {})
	cur[segs[-1]] = x
	return p


def GP(path, x, med, mad, n=20, cua_so=28):
	"""Gói: giá trị hôm nay x tại path thật + dòng lịch sử."""
	return dat({T: {"kpi": {"so_ngay": n, "cua_so": cua_so, "rows": [{"path": path, "kieu": "?", "nhan": "?",
		"hom_nay": x, "trung_vi": med, "mad": mad, "lech": None, "so_mad": None, "n": n}]}}}, path, x)


def M(path, x, med, mad, ov=None, **kw):
	p = copy.deepcopy(GP(path, x, med, mad, **kw))
	r = chay(p, ov)
	return "KHONG-CHAY" if K not in r.ran else {s.key.split(":", 1)[1]: s.severity for s in r.signals}


eq("pct: trung vị 20, MAD 1 → 23 (= 3 MAD) không; 23,1 vàng; 16,9 vàng (giảm cũng tính)",
	[M(PCT, v, 20, 1) for v in (23, 23.1, 16.9)], [{}, {PCT: "vang"}, {PCT: "vang"}])
eq("pct: MAD 0 → mẫu = 1% trung vị (0,2) nhưng sàn 5% trung vị (1) và 0,5 điểm: 20,9 không; 21 vàng",
	[M(PCT, v, 20, 0) for v in (20.9, 21)], [{}, {PCT: "vang"}])
eq("pct: trung vị 2, MAD 0 → sàn 0,5 điểm: 2,4 không; 2,5 vàng", [M(PCT, v, 2, 0) for v in (2.4, 2.5)],
	[{}, {PCT: "vang"}])
eq("tiền: trung vị 100 tr, MAD 0 → 104 tr (4 MAD nhưng < 5%) không; 105 tr vàng (đúng 5%, có dấu bằng)",
	[M(TIEN, v, 100_000_000, 0) for v in (104_000_000, 105_000_000)], [{}, {TIEN: "vang"}])
eq("tiền: trung vị 10 tr → sàn 1 triệu thắng 5%: 10,9 tr không; 11 tr vàng", [M(TIEN, v, 10_000_000, 0)
	for v in (10_900_000, 11_000_000)], [{}, {TIEN: "vang"}])
eq("số: trung vị 0, MAD 0 (phẳng ở 0) → 0 không; 1 vàng (sàn 1)", [M(SO, v, 0, 0) for v in (0, 1)], [{}, {SO: "vang"}])
eq("số: trung vị 3, MAD 1 → 6 (= 3 MAD) không; 7 vàng", [M(SO, v, 3, 1) for v in (6, 7)], [{}, {SO: "vang"}])
eq("chuỗi gần phẳng (nhiễu nhỏ): tiền 100 tr ± 0,4% không báo dù vượt nhiều MAD", [M(TIEN, 100_400_000, 100_000_000, 10)],
	[{}])
eq("đỏ chỉ khi đặt: ghi đè vàng 3 đỏ 6 → 26 (6 MAD) vàng, 26,1 đỏ; không đặt → vàng ở 50 MAD",
	[M(PCT, v, 20, 1, {"vang": 3, "do": 6}) for v in (26, 26.1)] + [M(PCT, 70, 20, 1)],
	[{PCT: "vang"}, {PCT: "do"}, {PCT: "vang"}])
eq("ghi đè vàng 6: MAD 0 → mẫu = 1% trung vị (1 tr): 105,5 tr (qua sàn 5%, nhưng = 5,5 mẫu) không; 106,1 tr vàng",
	[M(TIEN, v, 100_000_000, 0, {"vang": 6}) for v in (105_500_000, 106_100_000)], [{}, {TIEN: "vang"}])
eq("ghi đè vàng 5: 24 (4 MAD) không; 25,1 vàng", [M(PCT, v, 20, 1, {"vang": 5}) for v in (24, 25.1)], [{}, {PCT: "vang"}])
eq("tắt → không tín hiệu", M(PCT, 99, 20, 1, {"disabled": True}), {})
eq("cộng dồn / tỷ lệ theo kỳ KHÔNG BAO GIỜ báo (lệch 1000 lần)", [M(TL, 1e15, 1e9, 1), M(TK, -900.0, 5.0, 0.1)], [{}, {}])
eq("n < 14 trong dòng → bỏ; path không phải KPI → bỏ", [M(PCT, 99, 20, 1, n=13),
	M("cong-no.receivables.kpis.zz", 99, 20, 1)], [{}, {}])
p = GP(PCT, 99, 20, 1)
del p["cong-no"]
r = chay(p)
eq("giá trị hôm nay không có trong gói → chạy, không tín hiệu (không làm hỏng quy tắc)", (K in r.ran, r.signals), (True, []))
p = GP(PCT, 99, 20, 1)
p["cong-no"]["receivables"]["kpis"]["overdue_pct"] = "99"
eq("giá trị hôm nay không phải số → không tín hiệu", chay(p).signals, [])
eq("nguồn kpi _error / available False / thiếu → không chạy được", [("KHONG-CHAY" if K not in chay({T: {"kpi": b}}
	if b is not None else {T: {}}).ran else "chay") for b in ({"_error": True}, {"available": False}, None)],
	["KHONG-CHAY"] * 3)
p = GP(PCT, 99, 20, 1)
p[T]["kpi"]["rows"].append(dict(p[T]["kpi"]["rows"][0]))
eq("dòng trùng path → một tín hiệu (không trùng khoá)", len(chay(p).signals), 1)

p = GP(PCT, 23.5, 20, 1)
s = chay(p).signals[0]
TP = f"cong-no._ai.{registry.slug(K + ':' + PCT)}"
eq("khoá / mảng / route / audience theo KPI", (s.key, s.rule, s.section, s.route, s.audience),
	(f"{K}:{PCT}", K, "cong-no", "#/cong-no", "lanh-dao"))
eq("số tự tính ở mảng CỦA KPI; paths gồm path thật của KPI", (registry.resolve(p, TP), sorted(s.paths)),
	({"nhan": "Tỷ lệ nợ quá hạn", "so_ngay": 28, "trung_vi": 20}, sorted([PCT, f"{TP}.nhan", f"{TP}.so_ngay",
	f"{TP}.trung_vi"])))
eq("tro-ly không có _ai (không số tự tính nào ở mảng của quy tắc)", "_ai" in p[T], False)
eq("lời: nhãn + giá trị hôm nay qua path thật + trung vị 28 ngày; không nêu nguyên nhân",
	render.fill(s.title + " | " + s.detail, p).text, "Tỷ lệ nợ quá hạn khác thường so với 28 ngày qua | Hôm nay là 23,5%, "
	"trung vị 28 ngày trước đó là 20,0%; cần đối chiếu số trên màn gốc trước khi kết luận.")
p = GP(TIEN, 130_000_000, 100_000_000, 5_000_000)
s = chay(p).signals[0]
eq("tiền: lời", render.fill(s.title + " | " + s.detail, p).text, "Nợ phải thu quá hạn khác thường so với 28 ngày qua | "
	"Hôm nay là 130 triệu, trung vị 28 ngày trước đó là 100 triệu; cần đối chiếu số trên màn gốc trước khi kết luận.")
p = GP(QUA30, 9, 2, 0)
s = chay(p).signals[0]
eq("nhãn có chữ số (Kho quá 30 ngày chưa kiểm) đi qua chỗ giữ chu, mảng kiem-ke", (s.section, render.fill(s.title, p).text),
	("kiem-ke", "Kho quá 30 ngày chưa kiểm khác thường so với 28 ngày qua"))
eq("kind_map: trung vị cùng kiểu với KPI", {k: v for k, v in registry.kind_map([s]).items() if "_ai" in k},
	{f"kiem-ke._ai.{registry.slug(K + ':' + QUA30)}.so_ngay": "so", f"kiem-ke._ai.{registry.slug(K + ':' + QUA30)}"
	".trung_vi": "so"})

# Mọi KPI không cộng dồn: một tín hiệu dựng được, E5 với kinds + nguon (mảng KPI).
TAT_CA = {}
for path, kieu, _l in registry.KPIS:
	if KD.bo_qua(path):
		continue
	co = 1_000_000.0 if kieu == "tien" else 1.0           # tiền: vượt sàn 1 triệu
	p = dat({T: {"kpi": {"cua_so": 28, "rows": [{"path": path, "trung_vi": 100.0 * co, "mad": 1.0 * co, "n": 20}]}}},
		path, 150.0 * co)
	sg = chay(p).signals
	TAT_CA[path] = (len(sg), sg[0].section if sg else None)
eq("mọi KPI không cộng dồn (52): đúng 1 tín hiệu, mảng = khoá cấp 1 của path", {p: v for p, v in TAT_CA.items()
	if v != (1, registry.section_of(p))}, {})
eq("số KPI được so", len(TAT_CA), 70 - len(registry.KPI_TICH_LUY) - len(KD.KPI_THEO_KY))


def e5(s, p):
	m = redact.build(True)
	m.begin()
	nguon = json.dumps({"pack": m.mask(p), "loi": s.title + " — " + s.detail}, ensure_ascii=False, default=str)
	m.restrict(nguon)
	out = render.render_insight({"title": s.title, "body": s.detail or s.title, "advice": []}, p, {s.section}, m,
		kinds=registry.kind_map([s]), nguon=nguon)
	render.forget_source()
	return out


c("có đủ ca để soát (≥ 60 tín hiệu)", len(MOI) >= 60, len(MOI))
eq("E5: mọi lời kpi.lech_chuan (mọi KPI) qua render_insight trong MẢNG CỦA KPI, kinds + nguon",
	sorted({f"{s.key}: {e5(s, p)['errors']}" for s, p in MOI if not e5(s, p)["ok"]}), [])
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không chữ số; tiêu đề ≤ 12 từ; thân một câu", sorted({bo_ph(s) for s, _ in MOI
	if re.search(r"\d", bo_ph(s))} | {s.title for s, _ in MOI if len(registry.PLACEHOLDER.sub("X", s.title).split()) > 12}
	| {s.detail for s, _ in MOI if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("không nêu nguyên nhân (do / vì / bởi / nguyên nhân)", sorted({bo_ph(s) for s, _ in MOI if re.search(
	r"\b(do|vì|bởi|nguyên nhân)\b", bo_ph(s))}), [])
eq("khai báo quy tắc", (registry.RULES[K].section, registry.RULES[K].sources, registry.RULES[K].vang, registry.RULES[K].do,
	registry.RULES[K].unit, registry.RULES[K].route), (T, (f"{T}.kpi",), 3, None, "MAD", ""))

# ═══ D. run_daily thật ═══════════════════════════════════════════════════════
print("\nD. run_daily thật: tín hiệu ở nhóm của KPI, ẩn mảng KPI → người xem mất, khối kpi không vào đề bài")
from bc.ai import collect, llm, pipeline, review  # noqa: E402
from bc.api import ai as api  # noqa: E402

bc_settings(ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_openai_model="", hidden_sections="")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
	[{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15}])
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.cache().store.clear()
collect.build = lambda today: copy.deepcopy(PACK_NAY)
GOI = []


def echo(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	GOI.append({"nhom": obj["nhom"], "user": user, "obj": obj})
	out = []
	for t in obj["tin_hieu"]:
		tt, _, bd = t["loi_quy_tac"].partition(" — ")
		out.append({"signal": t["id"], "severity": t["muc"], "priority": 3, "title": tt, "body": bd or tt, "advice": []})
	return {"data": {"insights": out}, "tokens_in": 1000, "tokens_out": 100, "model": model}


llm.call = echo
review.run_group = lambda **kw: None
frappe.session.user = "viewer@example.com"
o = pipeline.run_daily()
eq("lượt chạy ok: 1 tín hiệu (overdue_pct 3,5 MAD), lời quy tắc chép lại được nhận (E5)", (o.get("status"),
	o.get("signals"), o.get("accepted"), o.get("rejected")), ("ok", 1, 1, 0))
eq("nhóm được gọi: nhóm có số (kinh-doanh, kho-sx: chỉ nhận định tự do) + tai-chinh (nhóm của KPI); không kiem-soat",
	[g["nhom"] for g in GOI], ["kinh-doanh", "kho-sx", "tai-chinh"])
eq("tín hiệu chỉ gửi ở nhóm tai-chinh", {g["nhom"]: [t["rule"] for t in g["obj"]["tin_hieu"]] for g in GOI},
	{"kinh-doanh": [], "kho-sx": [], "tai-chinh": [K]})
g0 = next((g for g in GOI if g["nhom"] == "tai-chinh"), {"user": "", "obj": {"tin_hieu": [], "pack": {}}})
eq("đề bài tai-chinh: tín hiệu kpi.lech_chuan; pack chỉ cong-no", ([t["rule"] for t in g0["obj"]["tin_hieu"]],
	sorted(g0["obj"]["pack"])), ([K], ["cong-no"]))
eq("không đề bài nào chứa khối kpi / lịch sử (so_mad, mad, hom_nay, tro-ly)", [g["nhom"] for g in GOI
	if any(x in g["user"] for x in ('"so_mad"', '"mad"', '"hom_nay"', '"kpi"', '"tro-ly"'))], [])
c("đề bài tai-chinh: không số của mảng khác (tong-quan, kiem-ke)", not any(x in g0["user"] for x in ("tong-quan",
	"kiem-ke")))
row = frappe.db.sql("SELECT * FROM `tabBC AI Insight` WHERE signal_key = %s", (f"{K}:{PCT}",), as_dict=True)
row = row[0] if row else frappe._dict()
eq("Insight: mảng cong-no, route #/cong-no, sections_used cong-no, lời AI (đã thay số)", (row.section, row.route,
	row.sections_used, row.source, row.title), ("cong-no", "#/cong-no", "cong-no", "ai",
	"Tỷ lệ nợ quá hạn khác thường so với 28 ngày qua"))
eq("ảnh chụp KPI hôm nay được lưu ở dòng tổng (nền cho ngày mai)", json.loads(frappe.db.sql(
	"SELECT kpis FROM `tabBC AI Run` WHERE name = %s", (o.get("run"),))[0][0]).get(PCT), 23.5)

frappe.session.user = "Administrator"
fa = {x["signal_key"]: x for x in api.get_feed()["insights"]}
eq("quản trị: tín hiệu ở nhóm tai-chinh (Công nợ), route #/cong-no", [(x["group"], x["group_label"], x["route"])
	for k, x in fa.items() if k.startswith(K)], [("tai-chinh", "Công nợ", "#/cong-no")])
frappe.session.user = "viewer@example.com"
eq("người xem: thấy tín hiệu ở nhóm tai-chinh", [x["group"] for x in api.get_feed()["insights"]], ["tai-chinh"])
single("BC Settings", hidden_sections="cong-no")
eq("ẩn cong-no (mảng của KPI): người xem mất tín hiệu", api.get_feed()["insights"], [])
frappe.session.user = "Administrator"
eq("ẩn cong-no: quản trị vẫn thấy", [x["signal_key"] for x in api.get_feed()["insights"]], [f"{K}:{PCT}"])
single("BC Settings", hidden_sections="tro-ly")
frappe.session.user = "viewer@example.com"
try:
	vt = [x["signal_key"] for x in api.get_feed()["insights"]]
except frappe.PermissionError:
	vt = "CHAN"
eq("ẩn tro-ly (mảng của QUY TẮC): người xem bị chặn cả màn (không phải lọc theo mảng tín hiệu)", vt, "CHAN")
single("BC Settings", hidden_sections="")

# Lượt sau: cong-no đang ẩn → tín hiệu không gửi mô hình (mảng của tín hiệu ẩn), vẫn còn mở.
single("BC Settings", hidden_sections="cong-no")
GOI.clear()
frappe.cache().store.clear()
o2 = pipeline.run_daily(run_type="tay")
eq("ẩn cong-no: lượt chạy ok, tín hiệu vẫn còn, nhóm tai-chinh không được gọi (tín hiệu dùng số mảng ẩn)",
	(o2.get("status"), o2.get("signals"), [g["nhom"] for g in GOI]), ("ok", 1, ["kinh-doanh", "kho-sx"]))
single("BC Settings", hidden_sections="")

c.done()
