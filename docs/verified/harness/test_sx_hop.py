"""Báo cáo sản xuất (bc.api.sx_hop: số hộp QC ghi theo ngày ở phần Ghi hộp của sx) trên MariaDB thật, bảng sinh từ DocType
JSON v16 + app sx.

Số kỳ vọng TÍNH TAY từ dữ liệu dưới (hôm nay 27/10/2026: tháng mặc định 01–27/10, tháng trước 09/2026, 12 tháng 11/2025 →
10/2026). Bẫy có ca riêng: hai bảng một ngày, bảng đã huỷ, ngày SX đã huỷ (và ngày thay thế cùng ngày), dòng khoán / công
khoán chung / công nhật / vừa công nhật vừa khoán chung, dòng chưa chọn mã, mã không còn trong danh mục (tên lấy trên
dòng), mã chưa khai thùng, mã ẩn, mã nhóm khác, ngày có phiếu mà không có bảng, bảng không dòng, đồng bộ lương chờ / lỗi /
lỗi chỉ khoảng trắng, ngày Chủ nhật, biên tháng (30/09, 01/10), ngày sau hôm nay, tháng trước cùng khoảng (tháng 30 ngày
sau tháng 31 ngày, tháng 3 sau tháng 2), site không có sx / thiếu bảng / lỗi bất ngờ, quyền, cache, tham số rác. So vi sai
với sx.api.lich THẬT (thang("vaohop") + chi_tiet("vaohop")) trên cùng dòng; kiểm tĩnh riêng tư.

Chạy: BC_TEST_DB=bc_test_sx_hop python3 -B test_sx_hop.py
seed() chỉ THÊM dữ liệu tên HOP-… (gộp được vào seed giao diện): reset(); bc_settings(); seed().
"""
import ast
import datetime
import json
import os
import re

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset, single
from paths import BC_ROOT

import frappe  # noqa: E402

A, T, N, H, K, X = "HOP-A", "HOP-T", "HOP-N", "HOP-H", "HOP-K", "HOP-X"
PRIVATE = ["Nguyễn Văn Đóng Hộp HOP", "EMP-HOP-001", "qc.hop@hgc.vn", "quanly.hop@hgc.vn", "98765", "4321", "77777",
	"LỖI ĐỒNG BỘ HOP"]
FORBIDDEN = ("nhan_vien", "ten_nhan_vien", "nguoi_ghi", "don_gia", "thanh_tien", "tong_tien", "an_ca", "An Ca",
	"chot_ghiso_boi", "chot_vaohop_boi", "_boi")
SX_DOCTYPES = ("SX Ngay San Xuat", "SX Bang Vao Hop", "SX Bang Vao Hop Item")
_n = {"bang": 0}


def item(code, name, group, carton=None):
	insert("Item", name=code, item_code=code, item_name=name, item_group=group, stock_uom="Hộp", is_stock_item=1)
	if carton:
		insert("UOM Conversion Detail", parent=code, parenttype="Item", parentfield="uoms", idx=1, uom="Thùng",
			conversion_factor=carton)


def ngay(name, d, docstatus=0, can=0, loi=None, chot_cu=0):
	"""Phiếu ngày SX. can / loi = trạng thái đồng bộ lương phần vào hộp (viền xanh lịch = có bảng, không chờ, không lỗi)."""
	insert("SX Ngay San Xuat", name=name, ngay=d, docstatus=docstatus, can_dong_bo_vh=can, loi_dong_bo_vh=loi,
		chot_vaohop=chot_cu, chot_vaohop_boi=PRIVATE[3] if chot_cu else None, chot_ghiso_boi=PRIVATE[3])


def bang(ngay_sx, rows, docstatus=0, name=None):
	"""Bảng vào hộp. rows: [(mã | None, số hộp, loại)] — loại: 'k' khoán, 'kc' công khoán chung, 'cn' công nhật,
	'cnkc' vừa công nhật vừa khoán chung. Mỗi dòng đủ trường riêng tư (người, người ghi, đơn giá, tiền) + một dòng ăn ca."""
	_n["bang"] += 1
	name = name or f"HOP-B{_n['bang']:03d}"
	insert("SX Bang Vao Hop", name=name, ngay_sx=ngay_sx, docstatus=docstatus, tong_hop=sum(r[1] for r in rows),
		tong_tien=98765)
	for i, (sp, so, loai) in enumerate(rows, 1):
		insert("SX Bang Vao Hop Item", name=f"{name}-{i}", parent=name, parenttype="SX Bang Vao Hop", parentfield="dong",
			idx=i, docstatus=docstatus, san_pham=sp, so_hop=so, ten_san_pham="Bánh cũ HOP X" if sp == X else f"tên dòng {sp}",
			cong_nhat=1 if loai.startswith("cn") else 0, khoan_chung=1 if loai.endswith("kc") else 0,
			nhan_vien=None if loai.endswith("kc") else PRIVATE[1], ten_nhan_vien=PRIVATE[0], nguoi_ghi=PRIVATE[2],
			don_gia=4321, thanh_tien=77777)
	insert("SX Bang Vao Hop An Ca", name=f"{name}-AC", parent=name, parenttype="SX Bang Vao Hop", parentfield="an_ca",
		idx=1, docstatus=docstatus, nhan_vien=PRIVATE[1], ten_nhan_vien=PRIVATE[0])
	return name


def seed():
	"""Kịch bản Ghi hộp (mọi tên bắt đầu HOP-)."""
	item(A, "Bánh đậu xanh Rồng Vàng Hoàng Gia HOP A", "Hàng truyền thống", carton=20)
	item(T, "Hộp quà Tết HOP T", "Hàng Tết", carton=10)
	item(N, "Bánh HOP N chưa khai thùng", "Hàng truyền thống")
	item(H, "Bánh HOP ẩn", "Hàng truyền thống", carton=5)
	item(K, "Kẹo HOP K", "Kẹo khác", carton=4)
	# X: không có trong danh mục (mã đã xoá) — tên lấy ten_san_pham trên dòng, nhóm Khác, không thùng
	insert("BC Hidden Item", name="HOP-HID-1", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items",
		idx=7, item_code=H)

	# ── 10/2026 (hôm nay 27/10) ──
	ngay("HOP-N01", "2026-10-01")                                    # đã đồng bộ lương → chốt
	bang("HOP-N01", [(A, 100, "k"), (A, 20, "kc"), (T, 30, "cn"), (N, 7, "k")])
	bang("HOP-N01", [(A, 50, "k"), (H, 12, "k")], docstatus=1)        # bảng thứ hai cùng ngày (đã nộp)
	bang("HOP-N01", [(A, 999, "k")], docstatus=2)                     # bảng đã huỷ
	ngay("HOP-N02X", "2026-10-02", docstatus=2)                       # ngày SX đã huỷ (bảng của nó còn nháp)
	bang("HOP-N02X", [(A, 888, "k")])
	ngay("HOP-N02", "2026-10-02", can=1)                              # ngày thay thế, đang chờ đồng bộ → chưa chốt
	bang("HOP-N02", [(K, 40, "cnkc"), (X, 8, "k"), (None, 5, "k")])
	ngay("HOP-N04", "2026-10-04", docstatus=1, loi=PRIVATE[7])        # Chủ nhật; lỗi đồng bộ → chưa chốt
	bang("HOP-N04", [(A, 60, "k"), (T, 15, "kc")])
	ngay("HOP-N05", "2026-10-05")                                     # chỉ Ghi sổ, không bảng vào hộp
	ngay("HOP-N06", "2026-10-06")                                     # bảng không dòng → viền xanh, không hộp
	bang("HOP-N06", [])
	ngay("HOP-N07", "2026-10-07", loi="   ")                          # lỗi chỉ khoảng trắng: sx coi là CÓ lỗi
	bang("HOP-N07", [(A, 10, "k")])
	ngay("HOP-N27", "2026-10-27", chot_cu=1)                          # hôm nay
	bang("HOP-N27", [(A, 40, "cn")])
	ngay("HOP-N28", "2026-10-28")                                     # sau hôm nay
	bang("HOP-N28", [(A, 500, "k")])
	# ── 09/2026 (30 ngày) ──
	for nm, d, rows in (("HOP-S01", "2026-09-01", [(A, 100, "k")]), ("HOP-S27", "2026-09-27", [(T, 20, "k")]),
			("HOP-S28", "2026-09-28", [(A, 300, "k")]), ("HOP-S30", "2026-09-30", [(H, 10, "k")]),
			# ── 08/2026 (31 ngày) ──
			("HOP-U05", "2026-08-05", [(T, 5, "k")]), ("HOP-U31", "2026-08-31", [(A, 70, "k")]),
			# ── 02–03/2026, 10–11/2025 ──
			("HOP-F28", "2026-02-28", [(T, 9, "k")]), ("HOP-M31", "2026-03-31", [(A, 1, "k")]),
			("HOP-V10", "2025-11-10", [(A, 11, "k")]), ("HOP-O31", "2025-10-31", [(A, 13, "k")])):
		ngay(nm, d)
		bang(nm, rows)


def run(thang=None, refresh=1):
	from bc.api import sx_hop
	return sx_hop.get_overview(thang=thang, refresh=refresh)


def day(d=None, refresh=1):
	from bc.api import sx_hop
	return sx_hop.get_day(date=d, refresh=refresh)


def full():
	reset()
	bc_settings()
	seed()


def pick(d, *keys):
	return {k_: d.get(k_) for k_ in keys}


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


def lich(thang_, nam=2026):
	"""sx.api.lich THẬT dưới vai quản lý (System Manager) — đúng lịch Ghi hộp quản lý thấy."""
	from sx.api import lich as sx_lich
	frappe.session.user = "Administrator"
	try:
		return sx_lich.thang("vaohop", nam, thang_)
	finally:
		frappe.session.user = "viewer@example.com"


def lich_ngay(d):
	from sx.api import lich as sx_lich
	frappe.session.user = "Administrator"
	try:
		return sx_lich.chi_tiet("vaohop", d)
	finally:
		frappe.session.user = "viewer@example.com"


def chip_so(ra, prefix):
	m = next((re.match(r".*?(\d+) hộp", c) for c in ra["chips"] if isinstance(c, str) and c.startswith(prefix)), None)
	return int(m.group(1)) if m else 0


if __name__ == "__main__":
	c = Check()
	full()
	from bc.api import sx_hop

	d = run()
	m = d["meta"]
	c("có dữ liệu", d["available"] is True and m["sx"] is True)
	c("kỳ mặc định = tháng này cắt ở hôm nay; 12 tháng 11/2025 → 10/2026; ngày ghi gần nhất = hôm nay (28/10 sau hôm nay)",
		pick(m, "thang", "from", "to", "as_of", "prev", "last_day") == {"thang": "2026-10", "from": "2026-10-01",
		"to": "2026-10-27", "as_of": "2026-10-27", "prev": "2026-09", "last_day": "2026-10-27"}
		and m["months"] == ["2025-11", "2025-12"] + [f"2026-{i:02d}" for i in range(1, 11)], m)

	# ══ Từng ngày ══
	days = {x["date"]: x for x in d["days"]}
	c("mỗi ngày lịch một dòng 27 → 01/10 (mới nhất trước), thứ (T2 = 0)", len(d["days"]) == 27
		and [x["date"] for x in d["days"]] == [f"2026-10-{i:02d}" for i in range(27, 0, -1)]
		and days["2026-10-04"]["weekday"] == 6 and days["2026-10-05"]["weekday"] == 0, [x["date"] for x in d["days"]][:3])
	# 01/10: bảng 1 A 100 k + A 20 kc + T 30 cn + N 7 k; bảng 2 A 50 + H 12; bảng huỷ A 999 bỏ → 219 = khoán 189 + cn 30
	#   thùng A 170/20 = 8,5 + T 30/10 = 3 + H 12/5 = 2,4 (N chưa khai) = 13,9 · 4 mã · đã đồng bộ → chốt
	c("01/10: hai bảng cộng, bảng huỷ bỏ, khoán gồm khoán chung, mã ẩn vẫn vào tổng ngày", days["2026-10-01"] == {
		"date": "2026-10-01", "weekday": 3, "hop": 219, "khoan": 189, "cong_nhat": 30, "thung": 13.9, "so_ma": 4, "chot": True,
		"co": True}, days["2026-10-01"])
	# 02/10: ngày huỷ (A 888) bỏ; ngày thay thế: K 40 công nhật + khoán chung (→ công nhật), X 8, dòng chưa chọn mã 5
	#   → 53 = khoán 13 + cn 40; thùng K 40/4 = 10; 2 mã (dòng trống không là mã); đang chờ đồng bộ → chưa chốt
	c("02/10: ngày SX huỷ bỏ; dòng vừa công nhật vừa khoán chung = công nhật; dòng chưa chọn mã vào tổng", days["2026-10-02"]
		== {"date": "2026-10-02", "weekday": 4, "hop": 53, "khoan": 13, "cong_nhat": 40, "thung": 10.0, "so_ma": 2,
		"chot": False, "co": True}, days["2026-10-02"])
	c("04/10 (Chủ nhật): A 60 + T 15 khoán chung = 75, thùng 4,5; lỗi đồng bộ → chưa chốt", pick(days["2026-10-04"], "hop",
		"khoan", "cong_nhat", "thung", "so_ma", "chot") == {"hop": 75, "khoan": 75, "cong_nhat": 0, "thung": 4.5, "so_ma": 2,
		"chot": False}, days["2026-10-04"])
	c("ngày không ghi: co False, số 0 (03/10 trống, 05/10 chỉ có phiếu ngày)", all(pick(days[x], "hop", "co", "chot", "so_ma")
		== {"hop": 0, "co": False, "chot": False, "so_ma": 0} for x in ("2026-10-03", "2026-10-05")), days["2026-10-05"])
	c("06/10: bảng không dòng → không hộp, nhưng viền xanh như lịch sx", pick(days["2026-10-06"], "hop", "co", "chot") ==
		{"hop": 0, "co": False, "chot": True}, days["2026-10-06"])
	c("07/10: lỗi đồng bộ chỉ có khoảng trắng vẫn là lỗi (như sx) → chưa chốt", pick(days["2026-10-07"], "hop", "chot", "thung")
		== {"hop": 10, "chot": False, "thung": 0.5}, days["2026-10-07"])
	c("27/10 (hôm nay): A 40 công nhật, đã chốt", pick(days["2026-10-27"], "hop", "khoan", "cong_nhat", "chot") ==
		{"hop": 40, "khoan": 0, "cong_nhat": 40, "chot": True}, days["2026-10-27"])

	# ══ KPI ══
	k = d["kpis"]
	# 219 + 53 + 75 + 10 + 40 = 397 · khoán 189 + 13 + 75 + 10 = 287 · cn 30 + 40 + 40 = 110 (27,7 %) · 5 ngày → 79,4
	# thùng theo mã: A 280/20 = 14 + T 45/10 = 4,5 + H 12/5 = 2,4 + K 10 = 30,9 · 6 mã (A T N H K X) · chưa chốt: 02, 04, 07
	# tháng trước cùng khoảng 01–27/09: 100 + 20 = 120 (28/09 A 300 và 30/09 H 10 ngoài khoảng); trọn tháng 430 → +230,8 %
	c("KPI tháng", k == {"hop": 397, "thung": 30.9, "khoan": 287, "cong_nhat": 110, "cong_nhat_pct": 27.7, "so_ngay": 5,
		"tb_ngay": 79.4, "so_ma": 6, "ngay_cuoi": {"date": "2026-10-27", "hop": 40}, "chua_chot": 3, "prev_hop": 120,
		"prev_full": 430, "growth_pct": 230.8}, k)
	c("tổng ngày = tổng KPI (hộp, khoán, công nhật)", sum(x["hop"] for x in d["days"]) == k["hop"]
		and sum(x["khoan"] for x in d["days"]) == k["khoan"] and sum(x["cong_nhat"] for x in d["days"]) == k["cong_nhat"])
	c("kiểu số: hộp / số đếm là int, thùng / % là float", all(isinstance(k[x], int) and not isinstance(k[x], bool)
		for x in ("hop", "khoan", "cong_nhat", "so_ngay", "so_ma", "chua_chot", "prev_hop", "prev_full"))
		and all(isinstance(x["hop"], int) for x in d["days"]) and isinstance(k["thung"], float), k)

	# ══ Theo mã ══
	it = d["items"]
	c("theo mã: hộp giảm dần, mã ẩn H bỏ khỏi danh sách", [x["item_code"] for x in it] == [A, T, K, X, N], [x["item_code"] for x in it])
	c("A: tên ngắn, khoán 240 (gồm khoán chung 20) + cn 40, 14 thùng, 70,5 %, 4 ngày, 70/ngày", by(it, "item_code", A) == {
		"item_code": A, "item_name": "Bánh đậu xanh Rồng Vàng Hoàng Gia HOP A", "short_name": "HOP A", "group": "traditional",
		"hop": 280, "khoan": 240, "cong_nhat": 40, "thung": 14.0, "pct": 70.5, "so_ngay": 4, "tb_ngay": 70.0}, by(it, "item_code", A))
	c("T: nhóm Tết, 45 = khoán chung 15 + cn 30, 4,5 thùng, 11,3 %, 2 ngày", pick(by(it, "item_code", T), "group", "hop", "khoan",
		"cong_nhat", "thung", "pct", "so_ngay", "tb_ngay") == {"group": "tet", "hop": 45, "khoan": 15, "cong_nhat": 30,
		"thung": 4.5, "pct": 11.3, "so_ngay": 2, "tb_ngay": 22.5}, by(it, "item_code", T))
	c("K: nhóm khác → khac, 40 công nhật, 10 thùng", pick(by(it, "item_code", K), "group", "hop", "cong_nhat", "thung", "pct")
		== {"group": "khac", "hop": 40, "cong_nhat": 40, "thung": 10.0, "pct": 10.1}, by(it, "item_code", K))
	c("X: mã không còn trong danh mục → tên trên dòng, nhóm khac, 0 thùng", pick(by(it, "item_code", X), "item_name", "group",
		"hop", "thung", "pct") == {"item_name": "Bánh cũ HOP X", "group": "khac", "hop": 8, "thung": 0.0, "pct": 2.0},
		by(it, "item_code", X))
	c("N: chưa khai thùng → 0 thùng (tổng thùng chỉ gồm mã có quy cách)", pick(by(it, "item_code", N), "hop", "thung", "pct")
		== {"hop": 7, "thung": 0.0, "pct": 1.8}, by(it, "item_code", N))
	# Nhóm: Tết T 45 · truyền thống A 280 + N 7 + H 12 (ẩn vẫn tính) = 299 · khác K 40 + X 8 + dòng trống 5 = 53
	c("nhóm: tổng = 397, mã ẩn và dòng chưa chọn mã vẫn tính", d["groups"] == [
		{"key": "tet", "label": "Hàng Tết", "hop": 45, "pct": 11.3},
		{"key": "traditional", "label": "Hàng truyền thống", "hop": 299, "pct": 75.3},
		{"key": "khac", "label": "Khác", "hop": 53, "pct": 13.4}], d["groups"])

	# ══ 12 tháng ══
	tr = {x["thang"]: x for x in d["trend"]}
	c("12 tháng = meta.months", [x["thang"] for x in d["trend"]] == m["months"])
	c("12 tháng: 10/2026 cắt ở hôm nay (28/10 không tính), 09 430 / 4 ngày, 08 75 / 2, 11/2025 11 (31/10/2025 ngoài)",
		(tr["2026-10"], tr["2026-09"], tr["2026-08"], tr["2025-11"], tr["2026-07"]) == (
		{"thang": "2026-10", "hop": 397, "so_ngay": 5, "tb_ngay": 79.4}, {"thang": "2026-09", "hop": 430, "so_ngay": 4, "tb_ngay": 107.5},
		{"thang": "2026-08", "hop": 75, "so_ngay": 2, "tb_ngay": 37.5}, {"thang": "2025-11", "hop": 11, "so_ngay": 1, "tb_ngay": 11.0},
		{"thang": "2026-07", "hop": 0, "so_ngay": 0, "tb_ngay": 0}), d["trend"])

	# ══ Biên tháng, tháng trước cùng khoảng ══
	d9 = run("2026-09")
	k9 = d9["kpis"]
	# 09 (30 ngày) sau 08 (31 ngày): cùng khoảng = 01–30/08 → T 5 (31/08 A 70 ngoài); trọn tháng 75
	c("tháng 9 trọn tháng (30/09 có, 01/10 không); tháng trước 31 ngày: cùng khoảng 01–30/08 = 5, trọn 75",
		(pick(d9["meta"], "from", "to", "prev"), len(d9["days"]), k9["hop"], k9["prev_hop"], k9["prev_full"], k9["growth_pct"],
		k9["ngay_cuoi"]) == ({"from": "2026-09-01", "to": "2026-09-30", "prev": "2026-08"}, 30, 430, 5, 75, 8500.0,
		{"date": "2026-09-30", "hop": 10}), (d9["meta"], k9))
	c("tháng 9: mã ẩn H (chỉ có trong tháng 9) bỏ khỏi danh sách, vẫn trong tổng và số mã",
		[x["item_code"] for x in d9["items"]] == [A, T] and k9["so_ma"] == 3)
	d3 = run("2026-03")
	c("tháng 3 (31 ngày) sau tháng 2 (28 ngày): cùng khoảng kẹp 28/02 = trọn tháng = 9", pick(d3["kpis"], "hop", "prev_hop",
		"prev_full", "growth_pct") == {"hop": 1, "prev_hop": 9, "prev_full": 9, "growth_pct": -88.9}, d3["kpis"])
	d7 = run("2026-07")
	c("tháng trống: số 0, danh sách rỗng, không chia 0; last_day vẫn chỉ ngày có hộp gần nhất",
		pick(d7["kpis"], "hop", "thung", "so_ngay", "tb_ngay", "so_ma", "ngay_cuoi", "cong_nhat_pct", "chua_chot", "prev_hop",
		"growth_pct") == {"hop": 0, "thung": 0, "so_ngay": 0, "tb_ngay": 0, "so_ma": 0, "ngay_cuoi": None, "cong_nhat_pct": None,
		"chua_chot": 0, "prev_hop": 0, "growth_pct": None} and d7["items"] == [] and len(d7["days"]) == 31
		and not any(x["co"] for x in d7["days"]) and all(g["hop"] == 0 and g["pct"] is None for g in d7["groups"])
		and d7["meta"]["last_day"] == "2026-10-27", d7["kpis"])
	for bad in ("2026-11", "2027-01", "2026-13", "abc", "", None, "2026-1", "0001-01", "1999-12", "x' OR 1"):
		try:
			got = run(bad)["meta"]["thang"]
		except Exception as e:  # noqa: BLE001
			got = repr(e)
		c(f"tháng không hợp lệ / tương lai / cực đoan ({bad!r}) → tháng này, không lỗi", got == "2026-10", got)

	# Tháng 31 ngày qua bộ cắt gói số của Trợ lý AI (MAX_LIST = 30 phần tử đầu, cả Hỏi đáp qua qa.gon): ngày mới nhất phải còn
	from bc.ai import prompt as ai_prompt, qa as ai_qa
	d8 = run("2026-08")
	cut, n_cut = ai_prompt.truncate(d8)
	c("AI: tháng 31 ngày (08/2026) cắt còn 30 → còn 31/08 (ngày mới nhất, 70 hộp), mất 01/08", (len(d8["days"]), n_cut,
		cut["days"][0]["date"], cut["days"][0]["hop"], [x["date"] for x in cut["days"]].count("2026-08-01"), cut.get("_cat"))
		== (31, 1, "2026-08-31", 70, 0, {"days": 1}), [x["date"] for x in cut["days"]][:2])
	gon_obj, _txt = ai_qa.gon(d8, None)
	c("AI hỏi đáp: kết quả công cụ tháng 8 còn ngày 31/08", gon_obj and any(x["date"] == "2026-08-31" and x["hop"] == 70
		for x in gon_obj["days"]), gon_obj and [x["date"] for x in gon_obj["days"]][:2])
	# Hỏi đáp: tháng tương lai bị từ chối (khối theo tháng lặng lẽ trả THÁNG NÀY — mô hình sẽ đọc nhầm số)
	for key in (("san-xuat", "overview"), ("kiem-ke", "overview"), ("nhap-tp", "overview"), ("van-chuyen", "overview"),
			("attp", "report")):
		got = [ai_qa.check_params(key, {"thang": x}) for x in ("2026-11", "2027-03", "2026-10", "2026-09", "2025-12")]
		c(f"hỏi đáp {key[0]}: tháng tương lai (11/2026, 03/2027) bị từ chối, tháng này / trước nhận",
			[x[0] is None for x in got] == [True, True, False, False, False] and "chưa tới" in got[0][1], got)

	# ══ Chi tiết ngày ══
	g1 = day("2026-10-01")
	# A 100 k + 20 kc + 50 k = 170 (khoán chung 20) · T 30 cn · N 7 · H 12 (ẩn: bỏ khỏi dòng, vẫn trong tổng)
	c("ngày 01/10 theo mã: hộp giảm dần, mã ẩn bỏ", [(x["item_code"], x["hop"], x["khoan"], x["khoan_chung"], x["cong_nhat"],
		x["thung"], x["pct"]) for x in g1["rows"]] == [(A, 170, 170, 20, 0, 8.5, 77.6), (T, 30, 0, 0, 30, 3.0, 13.7),
		(N, 7, 7, 0, 0, 0.0, 3.2)], g1["rows"])
	c("ngày 01/10: tổng gồm mã ẩn = số ngày của tháng; đã chốt", g1["total"] == {"hop": 219, "khoan": 189, "cong_nhat": 30,
		"thung": 13.9} and pick(g1["meta"], "date", "chot", "co") == {"date": "2026-10-01", "chot": True, "co": True} and g1["available"] is True, (g1["total"], g1["meta"]))
	c("dòng của ngày đủ trường", set(g1["rows"][0]) == {"item_code", "item_name", "short_name", "group", "hop", "khoan",
		"khoan_chung", "cong_nhat", "thung", "pct"}, sorted(g1["rows"][0]))
	g2 = day("2026-10-02")
	c("ngày 02/10: K công nhật (khoán chung 0), X; dòng trống chỉ trong tổng; chưa chốt", ([(x["item_code"], x["hop"],
		x["khoan_chung"], x["cong_nhat"]) for x in g2["rows"]], g2["total"], g2["meta"]["chot"]) == ([(K, 40, 0, 40), (X, 8, 0, 0)],
		{"hop": 53, "khoan": 13, "cong_nhat": 40, "thung": 10.0}, False), g2)
	g4 = day("2026-10-04")
	c("ngày 04/10: T khoán chung 15 (trong khoán)", by(g4["rows"], "item_code", T) and pick(by(g4["rows"], "item_code", T),
		"hop", "khoan", "khoan_chung", "cong_nhat") == {"hop": 15, "khoan": 15, "khoan_chung": 15, "cong_nhat": 0}, g4["rows"])
	g6 = day("2026-10-06")
	c("ngày 06/10: bảng không dòng → không có gì, viền xanh", (g6["rows"], g6["total"]["hop"], g6["meta"]["co"],
		g6["meta"]["chot"]) == ([], 0, False, True), g6)
	for bad, want in (("2026-10-28", "2026-10-27"), ("2030-01-01", "2026-10-27"), ("abc", "2026-10-27"), ("", "2026-10-27"),
			(None, "2026-10-27"), ("2026-02-30", "2026-10-27"), ("1999-12-31", "2026-10-27"), ("0001-01-01", "2026-10-27"),
			("2026-10-01 08:00:00", "2026-10-01"), ("2026-9-1", "2026-10-27")):
		try:
			got = day(bad)["meta"]["date"]
		except Exception as e:  # noqa: BLE001
			got = repr(e)
		c(f"ngày {bad!r} → {want} (sai dạng / tương lai / quá cũ → hôm nay), không lỗi", got == want, got)
	c("ngày 28/10 (sau hôm nay) không xem được: về hôm nay = 40 hộp", day("2026-10-28")["total"]["hop"] == 40)

	# ══ So vi sai với lịch Ghi hộp THẬT của sx (vai quản lý) ══
	for mon, dd in ((10, d), (9, d9), (3, d3)):
		ref = lich(mon)["ngay"]
		mine = {x["date"]: x for x in dd["days"]}
		to = dd["meta"]["to"]
		ref_cut = {k_: v for k_, v in ref.items() if k_ <= to}
		lech = [(k_, v, mine.get(k_)) for k_, v in ref_cut.items() if not mine.get(k_) or v["so"] != mine[k_]["hop"]
			or v["phu"] != mine[k_]["cong_nhat"] or bool(v["chot"]) != mine[k_]["chot"]]
		thua = [x["date"] for x in dd["days"] if (x["hop"] or x["chot"]) and x["date"] not in ref_cut]
		c(f"vi sai {mon:02d}/2026: từng ngày (hộp, công nhật, viền xanh) = sx.api.lich.thang('vaohop')", not lech and not thua
			and ref_cut, (lech, thua))
	c("vi sai: tổng tháng = Σ lịch sx (tháng 9 trọn tháng)", lich(9)["tong"] == d9["kpis"]["hop"], (lich(9)["tong"], d9["kpis"]["hop"]))
	for dd in ("2026-10-01", "2026-10-02", "2026-10-04", "2026-10-06", "2026-10-07", "2026-10-27", "2026-09-30"):
		ra = lich_ngay(dd)
		g = day(dd)
		tm = next((kk["dong"] for kk in ra["khoi"] if kk["ten"] == "Theo mã hàng"), [])
		an = sum(r_["phai"] for r_ in tm) - sum(x["hop"] for x in g["rows"])  # phần sx có mà danh sách bc không: mã ẩn + dòng trống
		c(f"vi sai chi tiết {dd}: tổng, công nhật, công khoán chung = sx.api.lich.chi_tiet('vaohop')", (ra["so"],
			chip_so(ra, "công nhật"), chip_so(ra, "công khoán chung")) == (g["total"]["hop"], g["total"]["cong_nhat"],
			sum(x["khoan_chung"] for x in g["rows"])) and an == {"2026-10-01": 12, "2026-10-02": 5, "2026-09-30": 10}.get(dd, 0),
			(ra["so"], ra["chips"], g["total"], an))

	# ══ Riêng tư ══
	dump = json.dumps([d, d9, g1, g2, g4], ensure_ascii=False, default=str)
	c("không lộ người, người ghi, mã nhân viên, đơn giá, tiền, lỗi đồng bộ", not [x for x in PRIVATE if x in dump] and "@" not in dump,
		[x for x in PRIVATE if x in dump])
	src = open(os.path.join(BC_ROOT, "bc", "api", "sx_hop.py"), encoding="utf-8").read()
	c("tĩnh: sx_hop.py không nhắc tới trường người / tiền / ăn ca / người chốt (kể cả trong docstring)",
		not [x for x in FORBIDDEN if x in src], [x for x in FORBIDDEN if x in src])
	sql_strs = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
		and re.search(r"\bSELECT\b|\bFROM\b", n.value)]
	c("tĩnh: mọi SQL chỉ SELECT, không CURDATE / NOW / LIKE / ghi", sql_strs and not [s for s in sql_strs if re.search(
		r"CURDATE|NOW\(|SYSDATE|LIKE|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bREPLACE\b|\bALTER\b|\bDROP\b", s, re.I)]
		and not re.search(r"frappe\.db\.(set_value|delete|commit)|\.insert\(|\.save\(", src), sql_strs[:1])
	tree = ast.parse(src)
	for fname, sec in (("get_overview", "san-xuat"), ("get_day", "san-xuat")):
		fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == fname)
		first = fn.body[1] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body[0]
		c(f'{fname}: docstring rồi _guard("{sec}") ở dòng đầu, @frappe.whitelist', isinstance(fn.body[0], ast.Expr)
			and isinstance(fn.body[0].value, ast.Constant) and ast.unparse(first) == f"_guard('{sec}')"
			and any("whitelist" in ast.unparse(x) for x in fn.decorator_list), ast.unparse(first))
	from bc.api import _common
	c("SECTIONS có san-xuat ngay trước sx-tet, sau san-pham", _common.SECTIONS[_common.SECTIONS.index("san-xuat") - 1:
		_common.SECTIONS.index("san-xuat") + 2] == ("san-pham", "san-xuat", "sx-tet"), _common.SECTIONS)

	# ══ Quyền / ẩn mảng ══
	for fn, args in ((sx_hop.get_overview, {}), (sx_hop.get_day, {"date": "2026-10-01"})):
		frappe.session.user = "nobody@example.com"
		try:
			fn(refresh=1, **args)
			c(f"{fn.__name__}: người không có quyền bị chặn", False)
		except frappe.PermissionError:
			c(f"{fn.__name__}: người không có quyền bị chặn", True)
		finally:
			frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="san-xuat")
	for fn, args in ((sx_hop.get_overview, {}), (sx_hop.get_day, {"date": "2026-10-01"})):
		try:
			fn(refresh=1, **args)
			c(f"{fn.__name__}: mảng san-xuat đang ẩn → người xem bị chặn", False)
		except frappe.PermissionError as e:
			c(f"{fn.__name__}: mảng san-xuat đang ẩn → người xem bị chặn", "quản trị ẩn" in str(e), str(e))
	frappe.session.user = "Administrator"
	try:
		c("mảng ẩn: quản trị vẫn xem được", run()["kpis"]["hop"] == 397 and day("2026-10-01")["total"]["hop"] == 219)
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="sx-tet")
	c("ẩn mảng khác (sx-tet) không chặn san-xuat", run()["kpis"]["hop"] == 397)
	single("BC Settings", hidden_sections="")

	# ══ Cache ══
	single("BC Settings", cache_ttl=300)
	frappe.cache().store.clear()
	a1 = run(refresh=0)
	ngay("HOP-N26", "2026-10-26")
	bang("HOP-N26", [(A, 3, "k")])
	a2 = run(refresh=0)
	a3 = run(refresh=1)
	a4 = run("2026-09", refresh=0)
	c("cache: lần 2 trả bản cache (số cũ), refresh=1 tính lại, khoá theo tháng", (a1["meta"]["cached"], a2["meta"]["cached"],
		a2["kpis"]["hop"], a3["meta"]["cached"], a3["kpis"]["hop"], a4["meta"]["cached"], a4["kpis"]["hop"]) == (False, True, 397,
		False, 400, False, 430), (a2["kpis"]["hop"], a3["kpis"]["hop"], a4["meta"]))
	c("cache: khoá theo method + tham số", any(k_.startswith("bc:sx_hop.get_overview:") for k_ in frappe.cache().store))
	b1 = day("2026-10-26", refresh=0)
	bang("HOP-N26", [(T, 2, "k")])
	b2 = day("2026-10-26", refresh=0)
	b3 = day("2026-10-26", refresh=1)
	b4 = day("2026-10-27", refresh=0)
	c("cache ngày: bản cache → refresh, khoá theo ngày", (b1["total"]["hop"], b2["meta"]["cached"], b2["total"]["hop"],
		b3["total"]["hop"], b4["meta"]["cached"], b4["total"]["hop"]) == (3, True, 3, 5, False, 40), (b2["total"], b3["total"]))
	single("BC Settings", hidden_sections="san-xuat")
	try:
		run(refresh=0)
		c("ẩn rồi thì bản cache cũng không trả cho người xem", False)
	except frappe.PermissionError:
		c("ẩn rồi thì bản cache cũng không trả cho người xem", True)
	single("BC Settings", hidden_sections="", cache_ttl=0)

	# ══ sx cũ: chưa có cột đồng bộ (trước D123) → dùng chot_vaohop ══
	drop_column("SX Ngay San Xuat", "can_dong_bo_vh")
	dc = run()
	c("sx cũ chưa có cột đồng bộ: đã chốt = chot_vaohop (chỉ 27/10)", [x["date"] for x in dc["days"] if x["chot"]] == ["2026-10-27"]
		and dc["kpis"]["chua_chot"] == 5 and dc["kpis"]["hop"] == 402, ([x["date"] for x in dc["days"] if x["chot"]], dc["kpis"]))

	# ══ Không có sx / thiếu bảng / lỗi bất ngờ ══
	full()
	frappe.LOGGED.clear()
	frappe.INSTALLED_APPS.remove("sx")
	try:
		u = run()
		ud = day("2026-10-01")
		c("không cài sx: available False, mọi khối rỗng, meta vẫn có, không Error Log", (u["available"], u["meta"]["sx"],
			u["meta"]["thang"], u["kpis"], u["days"], u["items"], u["groups"], u["trend"], u.get("error"), ud["available"],
			ud["rows"], ud["total"], ud["meta"]["date"], frappe.LOGGED) == (False, False, "2026-10", {}, [], [], [], [], None, False,
			[], {}, "2026-10-01", []), (u, frappe.LOGGED))
	finally:
		frappe.INSTALLED_APPS.append("sx")
	drop_doctype("SX Bang Vao Hop Item")
	u2 = run()
	c("thiếu bảng dòng vào hộp: available False, không lỗi, không Error Log", (u2["available"], u2["meta"]["sx"], u2.get("error"),
		day()["available"], frappe.LOGGED) == (False, False, None, False, []), (u2, frappe.LOGGED))
	full()
	drop_column("SX Bang Vao Hop Item", "khoan_chung")
	u3 = run()
	u4 = day("2026-10-01")
	c("lỗi bất ngờ (cột thiếu): available False + error, ghi Error Log, không 500", (u3["available"], u3.get("error"), u3["kpis"],
		u4["available"], u4.get("error")) == (False, True, {}, False, True) and any("bc.sx_hop" in str(x) for x in frappe.LOGGED),
		(u3, frappe.LOGGED[-1:]))
	frappe.LOGGED.clear()

	# ══ Không có dữ liệu ══
	reset()
	bc_settings()
	e = run()
	c("sx có mà chưa ghi gì: available True, số 0, last_day None", (e["available"], e["kpis"]["hop"], e["items"],
		e["meta"]["last_day"], len(e["days"]), len(e["trend"]), day()["rows"]) == (True, 0, [], None, 27, 12, []), e["kpis"])

	# ══ Thùng: làm tròn một lần — dòng "Cả tháng" = cộng cột thùng của từng ngày, total get_day = dòng ngày ══
	reset()
	bc_settings()
	item("HOP-R3", "Bánh HOP R3", "Hàng truyền thống", carton=3)
	item("HOP-R3B", "Bánh HOP R3B", "Hàng truyền thống", carton=3)
	item("HOP-R5", "Bánh HOP R5 ẩn", "Hàng truyền thống", carton=5)
	insert("BC Hidden Item", name="HOP-HID-R", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items",
		idx=1, item_code="HOP-R5")
	for i, dd in enumerate(("2026-10-01", "2026-10-02", "2026-10-03")):
		ngay(f"HOP-R{i}", dd)
		bang(f"HOP-R{i}", [("HOP-R3", 1, "k"), ("HOP-R5", 7, "k")])   # 1/3 + 7/5 = 1,7333 → 1,73
	ngay("HOP-R9", "2026-10-09")
	bang("HOP-R9", [("HOP-R3", 1, "k"), ("HOP-R3B", 1, "k")])          # 1/3 + 1/3 = 0,667 → 0,67 (không phải 0,33 + 0,33)
	rr = run()
	rd = {x["date"]: x for x in rr["days"]}
	c("thùng ngày: làm tròn một lần trên tổng ngày (0,67; 1,73)", (rd["2026-10-09"]["thung"], rd["2026-10-01"]["thung"]) ==
		(0.67, 1.73), (rd["2026-10-09"], rd["2026-10-01"]))
	c("KPI thùng = cộng cột thùng các ngày (dòng Cả tháng khớp bảng): 3 × 1,73 + 0,67 = 5,86", rr["kpis"]["thung"] ==
		round(sum(x["thung"] for x in rr["days"]), 2) == 5.86, (rr["kpis"]["thung"], [x["thung"] for x in rr["days"] if x["co"]]))
	c("total thùng của get_day = thùng của dòng ngày", [day(x)["total"]["thung"] for x in ("2026-10-01", "2026-10-09")] ==
		[1.73, 0.67], [day(x)["total"] for x in ("2026-10-01", "2026-10-09")])

	# ══ Chi tiết ngày không cũ hơn dòng ngày: since = generated_at của overview đang hiện ══
	import frappe.utils as fu
	single("BC Settings", cache_ttl=300)
	frappe.cache().store.clear()
	gio = fu.FAKE_NOW_TIME
	try:
		fu.FAKE_NOW_TIME = datetime.time(10, 0, 0)
		s0 = sx_hop.get_day(date="2026-10-25")                            # mở 25/10 khi chưa ghi gì → vào cache
		ov0 = run(refresh=0)
		ngay("HOP-R25", "2026-10-25")
		bang("HOP-R25", [("HOP-R3", 40, "k")])                              # QC ghi tiếp sau đó
		fu.FAKE_NOW_TIME = datetime.time(10, 5, 0)
		ov = run(refresh=1)                                                  # ↻ / Làm mới
		row = next(x for x in ov["days"] if x["date"] == "2026-10-25")
		fu.FAKE_NOW_TIME = datetime.time(10, 6, 0)                          # người xem mở ngày một phút sau
		try:
			s1 = sx_hop.get_day(date="2026-10-25", since=ov["meta"]["generated_at"])
			s2 = sx_hop.get_day(date="2026-10-25", since=ov["meta"]["generated_at"])
			s3 = sx_hop.get_day(date="2026-10-25", since=ov0["meta"]["generated_at"])
			s4 = sx_hop.get_day(date="2026-10-25", since="rác' OR 1")
		except TypeError as e_:
			s1 = s2 = s3 = s4 = {"total": {}, "meta": {"err": repr(e_)}}
		c("sau Làm mới: chi tiết ngày (since = generated_at mới) tính lại = dòng ngày 40 hộp", (s0["total"]["hop"], row["hop"],
			s1["total"].get("hop"), s1["meta"].get("cached"), s1["meta"].get("co")) == (0, 40, 40, False, True), (s1["meta"], s1["total"]))
		c("since: bản cache mới hơn mốc vẫn dùng (không tính lại mỗi lần mở), mốc cũ / sai dạng → cache", (s2["meta"].get("cached"),
			s3["meta"].get("cached"), s4["meta"].get("cached"), s4["total"].get("hop")) == (True, True, True, 40), (s2["meta"], s3["meta"]))
	finally:
		fu.FAKE_NOW_TIME = gio
		single("BC Settings", cache_ttl=0)
	c.done()
