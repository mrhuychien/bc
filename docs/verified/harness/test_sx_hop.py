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


# ═══ Ghi hộp so với nhập kho (get_compare) — seed riêng, mọi tên CMP- ═══
CA, CB, CC, CD, CE, CF, CH, CK, CZ = ("CMP-A", "CMP-B", "CMP-C", "CMP-D", "CMP-E", "CMP-F", "CMP-H", "CMP-K", "CMP-Z")
# Chuỗi giả ở MỌI cột người / chữ tự do của phiếu nhập, dòng phiếu, sổ nợ vào hộp — không được ra payload
CMP_PRIVATE = ["Trần Thị Thủ Kho CMP", "thukho.cmp@hgc.vn", "quanly.cmp@hgc.vn", "GHI CHÚ PHIẾU CMP", "GHI CHÚ DÒNG CMP",
	"LÝ DO BỎ QUA CMP", "Lê Văn Xử Lý CMP", "VAO HOP TET CMP", "DS SE CMP", "TÊN DÒNG PHIẾU CMP", "TÊN NỢ CMP"]
CMP_FORBIDDEN = ("nguoi_lap", "nguoi_duyet", "duyet_luc", "xu_ly_boi", "xu_ly_luc", "ghi_chu", "ly_do", "phieu_nhap",
	"vao_hop_tet", "ds_se", "owner", "modified_by")


def cmp_slip(name, ngay, docstatus, rows, nguon=None, creation=None):
	"""Phiếu nhập TP. rows: [(mã | None, so_dem)] — mọi cột người / chữ tự do điền chuỗi giả."""
	insert("SX Phieu Nhap TP", name=name, ngay=ngay, docstatus=docstatus, nguon=nguon,
		trang_thai={0: "Nháp", 1: "Đã duyệt", 2: "Đã huỷ"}[docstatus], creation=creation or f"{ngay} 07:30:00",
		owner=CMP_PRIVATE[1], modified_by=CMP_PRIVATE[2], nguoi_lap=CMP_PRIVATE[1], nguoi_duyet=CMP_PRIVATE[2],
		duyet_luc=f"{ngay} 17:00:00", ghi_chu=CMP_PRIVATE[3], vao_hop_tet=CMP_PRIVATE[7], ds_se=CMP_PRIVATE[8],
		tong_dem=sum(r[1] for r in rows))
	for i, (it, dem) in enumerate(rows, 1):
		insert("SX Phieu Nhap TP Item", name=f"{name}-{i}", parent=name, parenttype="SX Phieu Nhap TP", parentfield="dong",
			idx=i, docstatus=docstatus, item=it, ten=CMP_PRIVATE[9], dvt=CMP_PRIVATE[0], so_lap=dem, so_dem=dem, lech=0,
			ghi_chu=CMP_PRIVATE[4], lap_uom=CMP_PRIVATE[0], dem_uom=CMP_PRIVATE[0], owner=CMP_PRIVATE[1])


def cmp_no(name, it, con_lai, ngay, tt="Chờ chấm"):
	insert("SX No Vao Hop", name=name, item=it, ten=CMP_PRIVATE[10], so_luong=con_lai or 5, con_lai=con_lai, trang_thai=tt,
		ngay=ngay, phieu_nhap="CMP-PN-01", ly_do=CMP_PRIVATE[5], xu_ly_boi=CMP_PRIVATE[1], owner=CMP_PRIVATE[2],
		xu_ly_luc=f"{ngay} 09:00:00", modified_by=CMP_PRIVATE[6])


def cmp_seed():
	"""Kịch bản so sánh (hôm nay 27/10/2026). Hộp: đơn vị kho Hộp trừ K (Kg); Z không còn trong danh mục; H ẩn."""
	item(CA, "Bánh đậu xanh CMP A", "Hàng truyền thống", carton=20)
	for code, name in ((CB, "Bánh CMP B"), (CC, "Bánh CMP C"), (CD, "Bánh CMP D"), (CE, "Bánh CMP E"), (CF, "Bánh CMP F lẻ"),
			(CH, "Bánh CMP H ẩn")):
		item(code, name, "Hàng truyền thống")
	insert("Item", name=CK, item_code=CK, item_name="Kẹo cân CMP K", item_group="Hàng truyền thống", stock_uom="Kg",
		is_stock_item=1)
	insert("BC Hidden Item", name="CMP-HID-1", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items",
		idx=3, item_code=CH)
	# ── Ghi hộp ──
	for nm, d, rows, st in (
			("CMP-N0929", "2026-09-29", [(CB, 8, "k")], 0),
			("CMP-N0930", "2026-09-30", [(CC, 25, "k")], 0),                       # ghi tháng 9, nhập 01/10
			("CMP-N1001", "2026-10-01", [(CA, 100, "k"), (CB, 40, "cn"), (None, 6, "kc"), (CK, 10, "k")], 0),
			("CMP-N1002", "2026-10-02", [(CA, 20, "kc"), (CE, 30, "k"), (CH, 12, "k")], 1),
			("CMP-N1005", "2026-10-05", [(CF, 10, "k"), (CZ, 4, "k")], 0),
			("CMP-N1009", "2026-10-09", [(CA, 999, "k")], 2),                      # ngày SX đã huỷ
			("CMP-N1027", "2026-10-27", [(CA, 50, "cn")], 0),                      # hôm nay
			("CMP-N1028", "2026-10-28", [(CA, 500, "k")], 0)):                     # sau hôm nay
		ngay(nm, d, docstatus=st)
		bang(nm, rows, docstatus=min(st, 1))
	# ── Phiếu nhập ──
	cmp_slip("CMP-PN-01", "2026-10-01", 1, [(CA, 90), (CC, 25)])                  # cùng ngày (A) + hộp tháng trước (C)
	cmp_slip("CMP-PN-02", "2026-10-03", 1, [(CA, 25), (CB, 40)])                  # ngày sau
	cmp_slip("CMP-PN-03", "2026-10-03", 1, [(CA, 5)])                             # hai phiếu một ngày
	cmp_slip("CMP-PN-04", "2026-10-04", 1, [(CD, 15)])                            # mã chỉ có phiếu
	cmp_slip("CMP-PN-05", "2026-10-05", 1, [(CF, 7.25), (CK, 3.5), (None, 9)])    # số lẻ, mã Kg, dòng không mã
	cmp_slip("CMP-PN-06", "2026-10-06", 1, [(CH, 12)])                            # mã ẩn
	cmp_slip("CMP-PN-07", "2026-10-06", 0, [(CA, 1000)], creation="2026-10-06 08:00:00")   # nháp
	cmp_slip("CMP-PN-08", "2026-10-06", 2, [(CA, 2000)])                          # đã huỷ
	cmp_slip("CMP-PN-09", "2026-10-07", 0, [(CE, 30)], nguon="Tết", creation="2026-10-07 08:00:00")   # nháp Tết
	cmp_slip("CMP-PN-10", "2026-10-28", 1, [(CA, 50)])                            # sau hôm nay
	# ── Sổ nợ vào hộp ──
	cmp_no("CMP-NV-01", CC, 25, "2026-10-01")
	cmp_no("CMP-NV-02", CD, 10, "2026-10-04")
	cmp_no("CMP-NV-03", CD, 5, "2026-10-20")
	cmp_no("CMP-NV-04", CA, 0, "2026-09-30", tt="Đã chấm bù")
	cmp_no("CMP-NV-05", CA, 7, "2026-09-29", tt="Bỏ qua")
	cmp_no("CMP-NV-06", CA, 9, "2026-09-28", tt="Đã huỷ")
	cmp_no("CMP-NV-07", CB, 0, "2026-09-28")                                       # 'Chờ chấm' mà đã về 0
	cmp_no("CMP-NV-08", CH, 3, "2026-10-10")                                       # mã ẩn
	cmp_no("CMP-NV-09", CF, 1.5, "2026-10-26")
	cmp_no("CMP-NV-10", CE, 4, "2026-10-01")                                       # cùng tuổi với C, ít hơn


def full_cmp():
	reset()
	bc_settings()
	cmp_seed()


def cmp_run(thang=None, refresh=1):
	from bc.api import sx_hop
	frappe.local.__dict__.pop("sx_nho", None)
	return sx_hop.get_compare(thang=thang, refresh=refresh)


def sx_doi_chieu(tu, den):
	"""sx.api.portal._vao_hop_vs_nhap_kho THẬT, dòng vào hộp lấy đúng như sx.api.portal.dashboard."""
	from sx.api import portal
	phieu = frappe.get_all("SX Ngay San Xuat", filters={"ngay": ("between", (tu, den)), "docstatus": ("<", 2)}, pluck="name")
	rows = []
	if phieu:
		bang_ = frappe.get_all("SX Bang Vao Hop", filters={"ngay_sx": ("in", phieu), "docstatus": ("<", 2)}, pluck="name")
		if bang_:
			rows = frappe.get_all("SX Bang Vao Hop Item", filters={"parent": ("in", bang_), "parenttype": "SX Bang Vao Hop"},
				fields=["san_pham", "so_hop"])
	return portal._vao_hop_vs_nhap_kho(rows, tu, den)


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
	# ════════════════════════════ GHI HỘP SO VỚI NHẬP KHO (get_compare) ════════════════════════════
	# Seed riêng (mọi tên CMP-), số kỳ vọng tính tay ở cmp_seed().
	full_cmp()
	from bc.api import kho_nhap
	cp = cmp_run()
	cm = cp["meta"]
	c("so sánh: có dữ liệu; meta = tháng này cắt ở hôm nay, cửa sổ chờ 30 ngày", cp["available"] is True and pick(cm, "thang",
		"from", "to", "as_of", "sx", "so_ngay_cho") == {"thang": "2026-10", "from": "2026-10-01", "to": "2026-10-27",
		"as_of": "2026-10-27", "sx": True, "so_ngay_cho": 30} and not cp.get("error"), cm)
	ct = cp["total"]
	# Ghi hộp (so được) = A 170 + B 40 + E 30 + F 10 + H 12 (ẩn) + dòng chưa chọn mã 6 = 268 (K Kg 10, Z ngoài danh mục 4: ra)
	# Nhập kho = A 90 + 25 + 5 · B 40 · C 25 (hộp ghi 30/09) · D 15 (chỉ có phiếu) · F 7,25 · H 12 = 219,25 (K 3,5 Kg ra; dòng
	#   phiếu không mã 9 ra; phiếu nháp A 1000, phiếu huỷ A 2000, phiếu nháp Tết E 30, phiếu 28/10 A 50: ra)
	# Lệch −48,75 = −18,2 % · chưa nhập A 50 + E 30 + F 2,75 + chưa mã 6 = 88,75 (3 mã) · nhập vượt C 25 + D 15 = 40 (2 mã)
	# Khớp B, H (2) · khác đơn vị K, Z (2 mã, 14 hộp)
	c("so sánh: tổng tháng tính tay", ct == {"hop": 268, "nhap": 219.25, "lech": -48.75, "lech_pct": -18.2, "chua_nhap": 88.75,
		"so_ma_chua_nhap": 3, "nhap_vuot": 40.0, "so_ma_nhap_vuot": 2, "so_ma_khop": 2, "hop_chua_ma": 6, "ma_khac_dvt": 2,
		"hop_khac_dvt": 14}, ct)
	# Trợ lý AI đọc khối này (san-xuat.compare): MỌI lá số của payload thật (gồm dòng của ba khối hiện tại) phải được
	# render.kieu_theo_ten xếp đúng — lech_pct → pct, còn lại → so; không lá nào là tiền, không lá nào bỏ trống.
	from bc.ai import render as ai_render

	def la_so(v, path, out):
		if isinstance(v, dict):
			for k, x in v.items():
				la_so(x, f"{path}.{k}", out)
		elif isinstance(v, list):
			for x in v:
				la_so(x, path, out)
		elif isinstance(v, (int, float)) and not isinstance(v, bool):
			out.add(path)
		return out

	las = la_so(cp, "san-xuat.compare", set())
	c("AI: payload thật có lá số ở mọi phần (tổng, ngày, mã, ba khối hiện tại gồm dòng)", {"san-xuat.compare.total.lech_pct",
		"san-xuat.compare.days.luy_ke", "san-xuat.compare.items.lech", "san-xuat.compare.cho_nhap.rows.qty",
		"san-xuat.compare.cho_duyet.oldest_age_days", "san-xuat.compare.no_vao_hop.rows.age_days"} <= las, sorted(las))
	c("AI: mọi lá số của payload thật xếp kiểu đúng (lech_pct → pct, còn lại → so)", {p: ai_render.kieu_theo_ten(p)
		for p in las if ai_render.kieu_theo_ten(p) != ("pct" if p.endswith(".lech_pct") else "so")} == {}, sorted(las))
	c("so sánh: bất biến lech = nhap − hop = nhap_vuot − chua_nhap", round(ct["nhap"] - ct["hop"], 2) == ct["lech"] ==
		round(ct["nhap_vuot"] - ct["chua_nhap"], 2), ct)
	c("so sánh: kiểu số — hộp int, nhập / lệch float", isinstance(ct["hop"], int) and not isinstance(ct["hop"], bool)
		and all(isinstance(ct[x], float) for x in ("nhap", "lech", "chua_nhap", "nhap_vuot", "lech_pct"))
		and all(isinstance(x["hop"], int) and isinstance(x["nhap"], float) for x in cp["days"] + cp["items"]), ct)
	cd = {x["date"]: x for x in cp["days"]}
	c("so sánh: mỗi ngày lịch một dòng 27 → 01/10 (mới nhất trước), 28/10 (sau hôm nay) không có", [x["date"] for x in cp["days"]]
		== [f"2026-10-{i:02d}" for i in range(27, 0, -1)] and cd["2026-10-05"]["weekday"] == 0, [x["date"] for x in cp["days"]][:3])
	want_days = {  # (hộp, nhập, lệch, luỹ kế, co)
		"2026-10-01": (146, 115.0, -31.0, -31.0, True),    # A 100 + B 40 + chưa mã 6 (K Kg ra) · A 90 cùng ngày + C 25 (hộp 30/09)
		"2026-10-02": (62, 0.0, -62.0, -93.0, True),       # A 20 + E 30 + H 12 (ẩn vẫn tính)
		"2026-10-03": (0, 70.0, 70.0, -23.0, True),        # hai phiếu một ngày: A 25 + B 40, A 5 (nhập ngày sau)
		"2026-10-04": (0, 15.0, 15.0, -8.0, True),         # D chỉ có phiếu
		"2026-10-05": (10, 7.25, -2.75, -10.75, True),     # F lẻ; Z, K, dòng phiếu không mã ra
		"2026-10-06": (0, 12.0, 12.0, 1.25, True),         # H 12; phiếu nháp / huỷ cùng ngày ra
		"2026-10-07": (0, 0.0, 0.0, 1.25, False),          # chỉ phiếu nháp Tết → không có gì
		"2026-10-09": (0, 0.0, 0.0, 1.25, False),          # ngày SX đã huỷ
		"2026-10-26": (0, 0.0, 0.0, 1.25, False),
		"2026-10-27": (50, 0.0, -50.0, -48.75, True),      # hôm nay
	}
	got_days = {k_: (cd[k_]["hop"], cd[k_]["nhap"], cd[k_]["lech"], cd[k_]["luy_ke"], cd[k_]["co"]) for k_ in want_days}
	c("so sánh: từng ngày (cùng ngày / ngày sau / hai phiếu một ngày / nháp, huỷ, Tết ra / ngày SX huỷ / luỹ kế)",
		got_days == want_days, {k_: v for k_, v in got_days.items() if v != want_days[k_]})
	c("so sánh: luỹ kế ngày mới nhất = lệch cả tháng; Σ cột = tổng", cp["days"][0]["luy_ke"] == ct["lech"]
		and sum(x["hop"] for x in cp["days"]) == ct["hop"] and round(sum(x["nhap"] for x in cp["days"]), 2) == ct["nhap"],
		cp["days"][0])
	ci = cp["items"]
	c("so sánh: theo mã — mã ẩn H bỏ, khác đơn vị cuối, |lệch| giảm dần (thứ tự sx)", [x["item_code"] for x in ci] ==
		[CA, CE, CC, CD, CF, CB, CK, CZ], [x["item_code"] for x in ci])
	c("so sánh: dòng mã đủ trường", set(ci[0]) == {"item_code", "item_name", "short_name", "group", "uom", "khac_dvt", "hop",
		"nhap", "lech"}, sorted(ci[0]))
	c("so sánh: A ghi 170 nhập 120 (cùng ngày + ngày sau, hai phiếu một ngày) lệch −50", by(ci, "item_code", CA) == {
		"item_code": CA, "item_name": "Bánh đậu xanh CMP A", "short_name": "CMP A", "group": "traditional", "uom": "Hộp",
		"khac_dvt": False, "hop": 170, "nhap": 120.0, "lech": -50.0}, by(ci, "item_code", CA))
	c("so sánh: C (hộp ghi tháng trước, nhập đầu tháng này) +25 · D chỉ có phiếu +15 · E chỉ có hộp −30 · F lẻ −2,75 · B khớp",
		[pick(by(ci, "item_code", x), "hop", "nhap", "lech", "khac_dvt") for x in (CC, CD, CE, CF, CB)] == [
		{"hop": 0, "nhap": 25.0, "lech": 25.0, "khac_dvt": False}, {"hop": 0, "nhap": 15.0, "lech": 15.0, "khac_dvt": False},
		{"hop": 30, "nhap": 0.0, "lech": -30.0, "khac_dvt": False}, {"hop": 10, "nhap": 7.25, "lech": -2.75, "khac_dvt": False},
		{"hop": 40, "nhap": 40.0, "lech": 0.0, "khac_dvt": False}], [by(ci, "item_code", x) for x in (CC, CD, CE, CF, CB)])
	# lech None: nhập theo Kg trừ số hộp không phải lệch hộp (Trợ lý AI đọc payload — không được có số để trích)
	c("so sánh: K (đơn vị Kg) và Z (không còn trong danh mục) liệt kê với khac_dvt, tên Z lấy trên dòng, lệch None",
		[pick(by(ci, "item_code", x), "uom", "khac_dvt", "hop", "nhap", "lech", "item_name") for x in (CK, CZ)] == [
		{"uom": "Kg", "khac_dvt": True, "hop": 10, "nhap": 3.5, "lech": None, "item_name": "Kẹo cân CMP K"},
		{"uom": None, "khac_dvt": True, "hop": 4, "nhap": 0.0, "lech": None, "item_name": f"tên dòng {CZ}"}],
		[by(ci, "item_code", x) for x in (CK, CZ)])

	# ── Hộp ghi cuối tháng trước, nhập tháng sau: tháng 9 ──
	c9 = cmp_run("2026-09")
	c("so sánh tháng 9: B 8 + C 25 ghi 29–30/09, nhập ở tháng 10 → −33 (−100 %); 30 ngày, luỹ kế cuối = −33",
		(pick(c9["total"], "hop", "nhap", "lech", "lech_pct", "chua_nhap", "so_ma_chua_nhap", "nhap_vuot"), len(c9["days"]),
		c9["days"][0]["date"], c9["days"][0]["luy_ke"], c9["days"][1]["luy_ke"], c9["days"][2]["luy_ke"]) == ({"hop": 33,
		"nhap": 0.0, "lech": -33.0, "lech_pct": -100.0, "chua_nhap": 33.0, "so_ma_chua_nhap": 2, "nhap_vuot": 0.0}, 30,
		"2026-09-30", -33.0, -8.0, 0.0), (c9["total"], c9["days"][:3]))
	c7 = cmp_run("2026-07")
	c("so sánh tháng trống: số 0, lech_pct None (không chia 0), danh sách rỗng, 31 ngày không co", (c7["available"],
		pick(c7["total"], "hop", "nhap", "lech", "lech_pct", "chua_nhap", "so_ma_khop", "ma_khac_dvt"), c7["items"],
		len(c7["days"]), any(x["co"] for x in c7["days"])) == (True, {"hop": 0, "nhap": 0.0, "lech": 0.0, "lech_pct": None,
		"chua_nhap": 0.0, "so_ma_khop": 0, "ma_khac_dvt": 0}, [], 31, False), c7["total"])
	for bad in ("2026-11", "abc", None, "x' OR 1", "0001-01"):
		try:
			got = cmp_run(bad)["meta"]["thang"]
		except Exception as e:  # noqa: BLE001
			got = repr(e)
		c(f"so sánh: tháng {bad!r} → tháng này, không lỗi", got == "2026-10", got)

	# ── "Hiện tại" ──
	cn_ = cp["cho_nhap"]
	# Cửa sổ 28/09 → 27/10: chấm A 170 · B 48 · C 25 · E 30 · F 10 · H 12 · K 10 · Z 4; đã nhận (đã duyệt từ 28/09, không chặn
	#   trên: A 120 + 50 của phiếu 28/10) + phiếu nháp Tết E 30 → còn B 8, F 2,75 (hộp) + K 6,5, Z 4 (khác đơn vị: không cộng)
	c("cho_nhap: = khotp.tran_con_lai qua kho_nhap._vao_hop (hộp B 8 + F 2,75; K, Z không cộng; nháp Tết trừ)", cn_ == {
		"available": True, "from": "2026-09-28", "to": "2026-10-27", "so_ngay": 30, "qty": 10.75, "items": 2, "rows": [
		{"item_code": CB, "item_name": "Bánh CMP B", "short_name": "Bánh CMP B", "qty": 8.0},
		{"item_code": CF, "item_name": "Bánh CMP F lẻ", "short_name": "Bánh CMP F lẻ", "qty": 2.75}]}, cn_)
	kn = kho_nhap.get_overview(refresh=1)
	vh = kn["vao_hop"]
	c("cho_nhap = khối 'đã vào hộp chưa nhập kho' của màn Nhập TP (số, số mã, dòng hộp)", (cn_["qty"], cn_["items"], cn_["from"],
		cn_["to"], [(r["item_code"], r["qty"]) for r in cn_["rows"]]) == (round(vh["qty"], 2), vh["items"], vh["from"], vh["to"],
		[(r["item_code"], round(r["qty"], 2)) for r in vh["rows"] if not r["khac_dvt"]]), (cn_, vh))
	cq = cp["cho_duyet"]
	# Phiếu nháp: A 1000 (tạo 06/10 → 21 ngày) + phiếu nháp Tết E 30 (tạo 07/10) = 2 phiếu, 1 Tết, 1030 hộp
	c("cho_duyet: 2 phiếu nháp (1 Tết), 1030 hộp, cũ nhất 21 ngày; không danh sách / tên phiếu", cq == {"available": True,
		"count": 2, "count_tet": 1, "qty": 1030, "uom": "Hộp", "oldest_age_days": 21}, cq)
	c("cho_duyet = khối phiếu chờ duyệt của màn Nhập TP", cq == {"available": True, **{k_: kn["cho_duyet"][k_] for k_ in ("count",
		"count_tet", "qty", "uom", "oldest_age_days")}}, kn["cho_duyet"])
	nv = cp["no_vao_hop"]
	# Mở ('Chờ chấm', còn > 0): C 25 (01/10) · E 4 (01/10) · D 10 (04/10) + 5 (20/10) · H 3 (ẩn) · F 1,5 (26/10) = 6 dòng, 5 mã,
	#   48,5; không tính: 'Đã chấm bù', 'Bỏ qua', 'Đã huỷ', 'Chờ chấm' còn 0
	c("no_vao_hop: dòng đang mở gom theo mã, tuổi từ ngày nợ cũ nhất; mã ẩn chỉ mất khỏi dòng", nv == {"available": True,
		"count": 6, "so_ma": 5, "qty": 48.5, "so_ma_khac_dvt": 0, "oldest_date": "2026-10-01", "oldest_age_days": 26, "rows": [
		{"item_code": CC, "item_name": "Bánh CMP C", "short_name": "Bánh CMP C", "qty": 25.0, "so_dong": 1, "ngay": "2026-10-01",
		"age_days": 26, "khac_dvt": False},
		{"item_code": CE, "item_name": "Bánh CMP E", "short_name": "Bánh CMP E", "qty": 4.0, "so_dong": 1, "ngay": "2026-10-01",
		"age_days": 26, "khac_dvt": False},
		{"item_code": CD, "item_name": "Bánh CMP D", "short_name": "Bánh CMP D", "qty": 15.0, "so_dong": 2, "ngay": "2026-10-04",
		"age_days": 23, "khac_dvt": False},
		{"item_code": CF, "item_name": "Bánh CMP F lẻ", "short_name": "Bánh CMP F lẻ", "qty": 1.5, "so_dong": 1,
		"ngay": "2026-10-26", "age_days": 1, "khac_dvt": False}]}, nv)
	c("hiện tại không theo tháng chọn (tháng 9 cùng ba khối)", all(c9[x] == cp[x] for x in ("cho_nhap", "cho_duyet",
		"no_vao_hop")))

	# ── So vi sai theo mã với sx.api.portal._vao_hop_vs_nhap_kho THẬT (bảng đối chiếu kho của Quản lý) ──
	for thang_, tu, den, dd in (("10", "2026-10-01", "2026-10-27", cp), ("09", "2026-09-01", "2026-09-30", c9)):
		ref = {g["item"]: g for g in sx_doi_chieu(tu, den) if g["item"]}
		mine = {x["item_code"]: x for x in dd["items"]}
		lech_ = []
		for code, x in mine.items():
			g = ref.get(code)
			# sx cắt so_dem bằng cint, bc giữ số lẻ: so trên phần nguyên (F 7,25 → 7) — số nguyên thì phải bằng hẳn
			if not g or (g["vao_hop"], g["nhap_kho"], g["lech"]) != (x["hop"], int(x["nhap"]), x["hop"] * -1 + int(x["nhap"])):
				lech_.append((code, g, x))
		thua = [k_ for k_ in ref if k_ not in mine and k_ != CH]
		c(f"vi sai {thang_}/2026 theo mã: (ghi hộp, nhập kho, lệch) = sx.api.portal._vao_hop_vs_nhap_kho (cùng dấu)", not lech_
			and not thua and mine, (lech_, thua))
		so_duoc = [k_ for k_ in [g["item"] for g in sx_doi_chieu(tu, den)] if k_ in mine and not mine[k_]["khac_dvt"]]
		c(f"vi sai {thang_}/2026: thứ tự mã so được = thứ tự của sx (|lệch| lớn trước)", so_duoc ==
			[x["item_code"] for x in dd["items"] if not x["khac_dvt"]], so_duoc)
	c("vi sai: phần lẻ là chỗ khác duy nhất (sx 7, bc 7,25)", next(g["nhap_kho"] for g in sx_doi_chieu("2026-10-01",
		"2026-10-27") if g["item"] == CF) == 7 and by(cp["items"], "item_code", CF)["nhap"] == 7.25)

	# ── So vi sai số nhập kho với màn Nhập TP (bc.api.kho_nhap) ──
	kd = {r["date"]: r for r in kn["nhap"]["by_day"]}
	hop_uom = [r for r in kn["nhap"]["total"]["by_uom"] if r["uom"] == "Hộp"]
	c("vi sai Nhập TP: nhập kho tháng = phần đơn vị Hộp của tổng tháng màn Nhập TP", hop_uom and hop_uom[0]["qty"] == ct["nhap"],
		(kn["nhap"]["total"]["by_uom"], ct["nhap"]))
	khac = [x for x in kd if kd[x]["qty"] is None]
	c("vi sai Nhập TP: từng ngày (trừ ngày lẫn đơn vị 05/10) = số nhập của màn Nhập TP", khac == ["2026-10-05"] and all(
		cd[x]["nhap"] == round(kd[x]["qty"], 2) for x in kd if x not in khac) and set(kd) == set(cd),
		[(x, cd[x]["nhap"], kd[x]["qty"]) for x in kd if x not in khac and cd[x]["nhap"] != kd[x]["qty"]])
	frappe.db.sql("DELETE FROM `tabSX Phieu Nhap TP Item` WHERE item = %s OR item IS NULL", (CK,))
	kn2 = kho_nhap.get_overview(refresh=1)
	cp2 = cmp_run()
	c("vi sai Nhập TP sau khi bỏ dòng Kg / không mã: tổng tháng và MỌI ngày bằng nhau", kn2["nhap"]["total"]["qty"] ==
		cp2["total"]["nhap"] == 219.25 and all({x["date"]: x for x in cp2["days"]}[r["date"]]["nhap"] == r["qty"]
		for r in kn2["nhap"]["by_day"]), (kn2["nhap"]["total"]["qty"], cp2["total"]["nhap"]))

	# ── Đơn vị, làm tròn một lần, ngưỡng lệch (seed riêng CMX-, hôm nay 27/10) ──
	reset()
	bc_settings()
	XA, XK, XG, XC, XT, XR = "CMX-A", "CMX-K", "CMX-G", "CMX-C", "CMX-T", "CMX-R"
	for code in (XA, XC, XT, XR):
		item(code, f"Bánh {code}", "Hàng truyền thống")
	for code, u in ((XK, "Kg"), (XG, "Gói")):
		insert("Item", name=code, item_code=code, item_name=f"Hàng {code}", item_group="Hàng truyền thống", stock_uom=u,
			is_stock_item=1)
	for nm, d, rows in (("CMX-N02", "2026-10-02", [(XA, 10, "k"), (XK, 5, "k")]),
			("CMX-N03", "2026-10-03", [(XG, 7, "k")]),                  # ngày chỉ có hộp của mã Gói
			("CMX-N08", "2026-10-08", [(XT, 10, "k")]),
			("CMX-N20", "2026-10-20", [(XR, 1, "k")])):
		ngay(nm, d)
		bang(nm, rows)
	cmp_slip("CMX-P1", "2026-10-02", 1, [(XA, 10), (XC, 0.001)])        # XC: nhập 0,001, không hộp
	cmp_slip("CMX-P2", "2026-10-04", 1, [(None, 3)])                     # ngày chỉ có dòng phiếu không mã
	cmp_slip("CMX-P3", "2026-10-05", 1, [(XK, 2.5)])                     # ngày chỉ có phiếu mã Kg
	cmp_slip("CMX-P4", "2026-10-08", 1, [(XT, 10.004)])                  # lệch +0,004 → làm tròn 0 = khớp
	cmp_slip("CMX-P5", "2026-10-21", 1, [(XR, 0.6251)])                  # còn 0,3749 → 0,37 (không 0,375 → 0,38)
	cmp_slip("CMX-P6", "2026-10-22", 0, [(XA, 0.3749)], creation="2026-10-22 08:00:00")   # nháp 0,3749 → 0,37
	cmp_no("CMX-V1", XK, 40, "2026-10-05")                               # nợ Kg
	cmp_no("CMX-V2", XG, 2.5, "2026-10-06")                              # nợ Gói
	cmp_no("CMX-V3", XA, 3, "2026-10-07")                                # nợ hộp
	cx = cmp_run()
	nv = cx["no_vao_hop"]
	c("no_vao_hop: chỉ cộng nợ của mã đơn vị Hộp (Kg 40, Gói 2,5 không thành '45,5 hộp'); mã khác đơn vị đếm riêng, cuối dòng",
		(nv["qty"], nv["so_ma"], nv["count"], nv["oldest_date"], nv["oldest_age_days"], nv.get("so_ma_khac_dvt"),
		[(r["item_code"], r["qty"], r.get("khac_dvt")) for r in nv["rows"]]) == (3.0, 1, 1, "2026-10-07", 20, 2,
		[(XA, 3.0, False), (XK, 40.0, True), (XG, 2.5, True)]), nv)
	from sx.api import khotp as sx_khotp
	g0 = sx_khotp.guard_card
	sx_khotp.guard_card = lambda *a, **k: None
	try:
		sxn = {g_["item"]: g_["con_lai"] for g_ in sx_khotp.so_no_vao_hop()["nhom"]}
	finally:
		sx_khotp.guard_card = g0
	c("no_vao_hop vi sai sx.api.khotp.so_no_vao_hop THẬT: từng mã bằng nhau, phần hộp = qty", sxn == {r["item_code"]: r["qty"]
		for r in nv["rows"]} and sum(v for k_, v in sxn.items() if k_ == XA) == nv["qty"], (sxn, nv["rows"]))
	kn = kho_nhap.get_overview(refresh=1)
	c("cho_nhap.qty làm tròn MỘT lần từ số gốc (0,3749 → 0,37; không 0,375 → 0,38); dòng cũng vậy", (cx["cho_nhap"]["qty"],
		[r["qty"] for r in cx["cho_nhap"]["rows"]], kn["vao_hop"]["qty"]) == (0.37, [0.37], 0.375), (cx["cho_nhap"],
		kn["vao_hop"]["qty"]))
	c("cho_duyet.qty làm tròn MỘT lần từ số gốc (0,3749 → 0,37); số phiếu = màn Nhập TP", (cx["cho_duyet"]["qty"],
		cx["cho_duyet"]["count"], kn["cho_duyet"]["count"]) == (0.37, 1, 1), (cx["cho_duyet"], kn["cho_duyet"]["qty"]))
	xi = {x["item_code"]: x for x in cx["items"]}
	xt = cx["total"]
	c("ngưỡng lệch một chỗ: XT +0,004 là khớp ở thẻ lẫn bảng; XC nhập 0,001 không thành dòng, không đếm",
		(XC in xi, xi[XT]["lech"], xt["so_ma_nhap_vuot"], xt["nhap_vuot"], xt["so_ma_khop"], xt["so_ma_chua_nhap"],
		xt["chua_nhap"]) == (False, 0.0, 0, 0.0, 2, 1, 0.37), (xt, list(xi)))
	c("ngưỡng lệch: số mã trong thẻ = số dòng bảng theo lệch đã làm tròn (như chip của màn)", (xt["so_ma_chua_nhap"],
		xt["so_ma_nhap_vuot"], xt["so_ma_khop"]) == (sum(1 for x in cx["items"] if not x["khac_dvt"] and x["lech"] < 0),
		sum(1 for x in cx["items"] if not x["khac_dvt"] and x["lech"] > 0),
		sum(1 for x in cx["items"] if not x["khac_dvt"] and x["lech"] == 0)), xt)
	c("mã khác đơn vị: lech None (Kg / Gói trừ hộp không phải lệch hộp), vẫn có hộp / nhập", [(x["item_code"], x["hop"],
		x["nhap"], x["lech"]) for x in cx["items"] if x["khac_dvt"]] == [(XG, 7, 0.0, None), (XK, 5, 2.5, None)],
		[x for x in cx["items"] if x["khac_dvt"]])
	xd = {x["date"]: x for x in cx["days"]}
	c("ngày chỉ có dòng không so được (hộp mã Gói 03/10, phiếu không mã 04/10, phiếu mã Kg 05/10) không 'co'",
		[(d, xd[d]["co"]) for d in ("2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-08")] == [
		("2026-10-02", True), ("2026-10-03", False), ("2026-10-04", False), ("2026-10-05", False), ("2026-10-08", True)],
		{d: xd[d] for d in ("2026-10-03", "2026-10-04", "2026-10-05")})

	c("CMX: bất biến sau làm tròn lech = nhap_vuot − chua_nhap (gốc +0,005 / −0,3749: hai lần làm tròn độc lập ra −0,36)",
		(xt["lech"], xt["nhap_vuot"], xt["chua_nhap"], round(xt["nhap_vuot"] - xt["chua_nhap"], 2)) == (-0.37, 0.0, 0.37, -0.37),
		xt)

	# Ba mã đơn vị Hộp lệch +0,004 / −0,004 (mỗi mã "khớp"): lệch tổng ±0,01 phải nằm trong nhập vượt / chưa nhập (0 mã)
	for dau, nhap_ma in ((1, 10.004), (-1, 9.996)):
		reset()
		bc_settings()
		ba = ("CMV-A", "CMV-B", "CMV-C")
		for code in ba:
			item(code, f"Bánh {code}", "Hàng truyền thống")
		ngay("CMV-N10", "2026-10-10")
		bang("CMV-N10", [(code, 10, "k") for code in ba])
		cmp_slip("CMV-P11", "2026-10-11", 1, [(code, nhap_ma) for code in ba])
		vt = cmp_run()["total"]
		c(f"ba mã lệch {dau * 0.004:+} (khớp): lệch tổng {dau * 0.01:+} = nhap_vuot − chua_nhap, số mã vẫn theo lệch đã làm "
			"tròn (0 mã lệch, 3 khớp)", (vt["lech"], round(vt["nhap_vuot"] - vt["chua_nhap"], 2), vt["nhap_vuot"],
			vt["chua_nhap"], vt["so_ma_nhap_vuot"], vt["so_ma_chua_nhap"], vt["so_ma_khop"]) == (dau * 0.01, dau * 0.01,
			0.01 if dau > 0 else 0.0, 0.01 if dau < 0 else 0.0, 0, 0, 3), vt)

	# ── Riêng tư ──
	full_cmp()
	cp = cmp_run()
	dump = json.dumps([cp, cmp_run("2026-09")], ensure_ascii=False, default=str)
	c("so sánh riêng tư: không người lập / duyệt / xử lý, ghi chú, lý do, tên phiếu, tên dòng nợ, @", not [x for x in CMP_PRIVATE
		if x in dump] and "@" not in dump and "CMP-PN" not in dump and "CMP-NV" not in dump,
		[x for x in CMP_PRIVATE if x in dump] + [x for x in ("CMP-PN", "CMP-NV") if x in dump])

	# ── Quyền / ẩn mảng ──
	frappe.session.user = "nobody@example.com"
	try:
		cmp_run()
		c("get_compare: người không có quyền bị chặn", False)
	except frappe.PermissionError:
		c("get_compare: người không có quyền bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="san-xuat")
	try:
		cmp_run()
		c("get_compare: mảng san-xuat đang ẩn → người xem bị chặn", False)
	except frappe.PermissionError as e:
		c("get_compare: mảng san-xuat đang ẩn → người xem bị chặn", "quản trị ẩn" in str(e), str(e))
	frappe.session.user = "Administrator"
	try:
		c("get_compare: mảng ẩn — quản trị vẫn xem được", cmp_run()["total"]["hop"] == 268)
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="")

	# ── Cache ──
	single("BC Settings", cache_ttl=300)
	frappe.cache().store.clear()
	try:
		k1 = cmp_run(refresh=0)
		cmp_slip("CMP-PN-40", "2026-10-26", 1, [(CA, 50)])
		k2 = cmp_run(refresh=0)
		k3 = cmp_run(refresh=1)
		k4 = cmp_run("2026-09", refresh=0)
		c("get_compare cache: lần 2 bản cache (số cũ), refresh=1 tính lại, khoá theo tháng", (k1["meta"]["cached"],
			k2["meta"]["cached"], k2["total"]["nhap"], k3["meta"]["cached"], k3["total"]["nhap"], k4["meta"]["cached"],
			k4["total"]["hop"]) == (False, True, 219.25, False, 269.25, False, 33), (k2["total"]["nhap"], k3["total"]["nhap"]))
		c("get_compare cache: khoá riêng của method", any(k_.startswith("bc:sx_hop.get_compare:") for k_ in frappe.cache().store))
		single("BC Settings", hidden_sections="san-xuat")
		try:
			cmp_run(refresh=0)
			c("get_compare: ẩn rồi thì bản cache cũng không trả", False)
		except frappe.PermissionError:
			c("get_compare: ẩn rồi thì bản cache cũng không trả", True)
	finally:
		single("BC Settings", hidden_sections="", cache_ttl=0)

	# ── Không có sx / thiếu bảng / lỗi bất ngờ ──
	frappe.LOGGED.clear()
	off = {"available": False}
	frappe.INSTALLED_APPS.remove("sx")
	try:
		u = cmp_run()
		c("get_compare không cài sx: available False, meta có, mọi khối rỗng / tắt, không Error Log", (u["available"],
			u["meta"]["sx"], u["meta"]["thang"], u["total"], u["days"], u["items"], u["cho_nhap"], u["cho_duyet"],
			u["no_vao_hop"], u.get("error"), frappe.LOGGED) == (False, False, "2026-10", {}, [], [], off, off, off, None, []),
			(u, frappe.LOGGED))
	finally:
		frappe.INSTALLED_APPS.append("sx")
	drop_doctype("SX No Vao Hop")
	u = cmp_run()
	c("thiếu bảng SX No Vao Hop: chỉ khối nợ tắt, phần còn lại có số, không Error Log", (u["available"], u["total"]["hop"],
		u["cho_nhap"]["available"], u["no_vao_hop"], frappe.LOGGED) == (True, 268, True, off, []), (u["no_vao_hop"], frappe.LOGGED))
	full_cmp()
	drop_column("SX No Vao Hop", "con_lai")
	u = cmp_run()
	c("SX No Vao Hop thiếu cột con_lai: khối nợ tắt, không Error Log", (u["no_vao_hop"], u["total"]["hop"], frappe.LOGGED) ==
		(off, 268, []), (u["no_vao_hop"], frappe.LOGGED))
	full_cmp()
	drop_doctype("SX Phieu Nhap TP Item")
	u = cmp_run()
	c("thiếu bảng dòng phiếu nhập: available False (meta.sx True như get_overview — màn báo chưa đối chiếu được), không lỗi,"
		" không Error Log", (u["available"],
		u["meta"]["sx"], u.get("error"), u["total"], u["cho_nhap"], frappe.LOGGED) == (False, True, None, {}, off, []),
		(u, frappe.LOGGED))
	full_cmp()
	drop_column("SX Bang Vao Hop Item", "khoan_chung")
	u = cmp_run()
	c("lỗi bất ngờ ở phần tháng: available False + error, Error Log; ba khối hiện tại vẫn tính riêng", (u["available"],
		u.get("error"), u["total"], u["days"], u["items"], u["cho_nhap"].get("qty"), u["cho_duyet"].get("count"), u["no_vao_hop"].get("qty"))
		== (False, True, {}, [], [], 10.75, 2, 48.5) and any("bc.sx_hop.get_compare" in str(x) for x in frappe.LOGGED),
		(u.get("error"), frappe.LOGGED[-1:]))
	frappe.LOGGED.clear()
	full_cmp()
	frappe.db.sql("DROP TABLE `tabSX Phieu Nhap TP`")
	frappe.db.sql("CREATE TABLE `tabSX Phieu Nhap TP` (name VARCHAR(140))")    # bảng còn, cột mất → lỗi khối
	u = cmp_run()
	c("lỗi bất ngờ ở khối phiếu: khối đó error True, không 500", u.get("error") is True and u["cho_duyet"] == {"available": False,
		"error": True} and any("bc.sx_hop.get_compare.cho_duyet" in str(x) for x in frappe.LOGGED), (u.get("error"),
		u["cho_duyet"]))
	frappe.LOGGED.clear()

	# ── Tĩnh: get_compare ──
	fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "get_compare")
	c('get_compare: docstring rồi _guard("san-xuat") ở dòng đầu, @frappe.whitelist', isinstance(fn.body[0], ast.Expr)
		and isinstance(fn.body[0].value, ast.Constant) and ast.unparse(fn.body[1]) == "_guard('san-xuat')"
		and any("whitelist" in ast.unparse(x) for x in fn.decorator_list), ast.unparse(fn.body[1]))
	c("tĩnh: sx_hop.py không nhắc tới người lập / duyệt / xử lý, ghi chú, lý do, phiếu gốc của nợ", not [x for x in
		CMP_FORBIDDEN if x in src], [x for x in CMP_FORBIDDEN if x in src])
	c("tĩnh: phiếu nhập chỉ đọc phiếu ĐÃ DUYỆT, dòng 'dong'; nợ chỉ 'Chờ chấm'", "p.docstatus = 1" in src
		and "i.parentfield = 'dong'" in src and 'CHO_CHAM = "Chờ chấm"' in src)
	c.done()
