"""Seed cho kiểm giao diện màn Báo cáo sản xuất (ui_san_xuat.mjs): bảng Ghi hộp THẬT của sx (SX Ngay San Xuat, SX Bang Vao
Hop, SX Bang Vao Hop Item) — màn đọc qua bc.api.sx_hop thật.

BC_TEST_DB=bc_test_sxh_ui python3 -B seed_ui_san_xuat.py [seed|nosx]
	seed  (mặc định) hôm nay giả 27/10/2026: tháng 10 nhiều ngày (có Chủ nhật, hai bảng một ngày, bảng huỷ, ngày huỷ, khoán /
	      khoán chung / công nhật, mã chưa khai thùng, mã ẩn, ngày chưa chốt), 13 mã (bảng theo mã sang trang 2), tháng 9 đủ
	      tháng (so cùng kỳ), tháng 8 + tháng 3 (12 tháng), tháng 7 TRỐNG (tháng không có số).
	nosx  như seed rồi bỏ SX Settings (site không cài sx → available False).
	moc   như seed + mốc tính nợ vào hộp của sx (D230: SX Settings.no_vh_tu_ngay 15/10, no_vh_mang_sang HX-TT1 6 hộp chấm
	      05/10 + HX-KG 2 Kg) — ô "Đã ghi hộp, chưa nhập kho" phải ghi "tính từ mốc 15/10".
Dòng ghi hộp mang tên nhân viên / đơn giá / thành tiền giả có dấu hiệu riêng — màn không được hiện.

Khối "Ghi hộp so với nhập kho" (get_compare): phiếu nhập TP THẬT (SX Phieu Nhap TP / Item) đủ trạng thái — đã duyệt cùng
ngày / ngày sau / tháng sau, hai phiếu một ngày, số đếm lẻ, phiếu nháp (cả nháp Tết), phiếu đã huỷ; mã chỉ có ở phiếu nhập
(HX-TT3), mã chỉ ghi hộp (HX-KHAC), mã đơn vị kho khác Hộp (HX-KG), dòng ghi hộp chưa chọn mã, mã ẩn; nợ vào hộp
(SX No Vao Hop) đang chờ chấm / đã chấm bù / bỏ qua. Phiếu / nợ mang người lập, người duyệt, ghi chú, lý do có dấu hiệu
riêng — màn không được hiện; tên phiếu cũng không.
"""
import sys

from seed import bc_settings, insert, reset, single

SECRET_NV = "Nguyễn Văn Bí Mật"
SECRET_USER = "thukho.bimat@hgc.vn"
SECRET_NOTE = "GHI CHÚ NHẬP BÍ MẬT"
SECRET_LYDO = "LÝ DO NỢ BÍ MẬT"
GROUPS = {"tet": "Hàng Tết", "tt": "Hàng truyền thống", "khac": "Bánh khác"}
# (mã, tên, nhóm, quy cách thùng | None)
ITEMS = [
	("HX-TET1", "Bánh đậu xanh Rồng Vàng Hoàng Gia hộp quà Tết 450g", "tet", 12),
	("HX-TET2", "Bánh đậu xanh hộp thiếc Tết 300g", "tet", 20),
	("HX-TT1", "Bánh đậu xanh truyền thống 250g", "tt", 24),
	("HX-TT2", "Bánh đậu xanh truyền thống 170g", "tt", 30),
	("HX-KHAC", "Bánh thử nghiệm (chưa khai thùng)", "khac", None),
	("HX-AN", "Bánh mã đang ẩn", "tt", 10),
] + [(f"HX-P{i:02d}", f"Bánh phụ số {i}", "tt", 10) for i in range(1, 7)] + [
	("HX-P07", "Bánh phụ số 7 <img src=x onerror=window.__xss=1>", "tt", 10),  # tên có HTML: màn phải hiện thành chữ
	("HX-TT3", "Bánh đậu xanh truyền thống 400g", "tt", 12),  # chỉ có ở phiếu nhập (không ghi hộp)
]
# Mã đơn vị kho khác Hộp: liệt kê "ĐVT khác", không cộng vào tổng đối chiếu
ITEMS_KHAC_DVT = [("HX-KG", "Nhân đậu xanh rời (kg)", "khac", "Kg")]


def seed(sx=True):
	reset()
	bc_settings()
	if sx:
		single("SX Settings", cong_ty="HGC")
	for code, name, g, carton in ITEMS:
		insert("Item", name=code, item_code=code, item_name=name, item_group=GROUPS[g], stock_uom="Hộp", is_stock_item=1)
		if carton:
			insert("UOM Conversion Detail", parent=code, parenttype="Item", parentfield="uoms", idx=1, uom="Thùng",
				conversion_factor=carton)
	for code, name, g, uom in ITEMS_KHAC_DVT:
		insert("Item", name=code, item_code=code, item_name=name, item_group=GROUPS[g], stock_uom=uom, is_stock_item=1)
	# Mã ẩn (Quản trị › Ẩn sản phẩm): không có trong danh sách theo mã, tổng vẫn gồm
	insert("BC Hidden Item", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items", idx=1, item_code="HX-AN")

	n = {"i": 0}

	def ngay(date, chot=True, docstatus=1):
		n["i"] += 1
		return insert("SX Ngay San Xuat", name=f"NSX-{date}-{n['i']}", ngay=date, docstatus=docstatus,
			can_dong_bo_vh=0 if chot else 1, loi_dong_bo_vh="", chot_vaohop=1 if chot else 0)

	def bang(nsx, lines, docstatus=1):
		b = insert("SX Bang Vao Hop", ngay_sx=nsx, docstatus=docstatus, tong_hop=sum(x[1] for x in lines), tong_tien=999999)
		for i, (item, so, kind) in enumerate(lines, 1):
			insert("SX Bang Vao Hop Item", parent=b, parenttype="SX Bang Vao Hop", parentfield="dong", idx=i, san_pham=item,
				so_hop=so, cong_nhat=1 if kind == "cn" else 0, khoan_chung=1 if kind == "kc" else 0,
				nhan_vien=None if kind == "kc" else "HR-EMP-SECRET", ten_nhan_vien=None if kind == "kc" else SECRET_NV,
				don_gia=1234, thanh_tien=so * 1234, ten_san_pham=item, docstatus=docstatus)
		return b

	# ── Tháng 10/2026 (hôm nay giả 27/10) ──
	d = ngay("2026-10-01")
	bang(d, [("HX-TET1", 240, "k"), ("HX-TT1", 120, "k"), ("HX-KHAC", 30, "cn")])
	d = ngay("2026-10-02")
	bang(d, [("HX-TET1", 300, "k"), ("HX-TET2", 80, "kc")])
	bang(d, [("HX-TT2", 150, "cn"), ("HX-AN", 40, "k")])  # hai bảng một ngày
	bang(d, [("HX-TET1", 5000, "k")], docstatus=2)  # bảng đã huỷ: không tính
	d = ngay("2026-10-04")  # Chủ nhật
	bang(d, [("HX-TET2", 60, "k"), ("HX-TT1", 20, "cn")])
	d = ngay("2026-10-05", docstatus=2)  # ngày đã huỷ: không tính
	bang(d, [("HX-TET1", 7000, "k")])
	d = ngay("2026-10-07")
	bang(d, [("HX-TET1", 180, "k"), ("HX-TT1", 90, "kc"), ("HX-TT2", 45, "cn")])
	bang(d, [(None, 15, "k"), ("HX-KG", 20, "k")])  # dòng chưa chọn mã + mã ĐVT khác Hộp
	for i in range(1, 8):  # đủ 13 mã (sang trang 2 của bảng theo mã)
		d = ngay(f"2026-10-{8 + i:02d}")
		bang(d, [(f"HX-P{i:02d}", 10 * i, "k"), ("HX-TT1", 15, "k")])
	d = ngay("2026-10-20", chot=False)
	bang(d, [("HX-TET1", 210, "k"), ("HX-KHAC", 25, "k")])
	d = ngay("2026-10-26", chot=False)  # ngày ghi gần nhất, chưa chốt
	bang(d, [("HX-TET2", 130, "k"), ("HX-TT1", 55, "cn"), ("HX-TT2", 33, "kc")])

	# ── Tháng 9/2026: đủ tháng (cùng kỳ 1–27 + trọn tháng) ──
	for day, so in ((1, 200), (3, 150), (10, 260), (15, 310), (27, 90), (28, 400), (30, 120)):
		d = ngay(f"2026-09-{day:02d}")
		bang(d, [("HX-TET1", so, "k"), ("HX-TT1", so // 5, "cn")])
	# ── Tháng 8 và tháng 3/2026 (12 tháng); tháng 7 trống ──
	for date, so in (("2026-08-05", 500), ("2026-08-19", 350), ("2026-03-11", 220)):
		bang(ngay(date), [("HX-TT1", so, "k")])
	# ── Tháng 6/2026: số 6 chữ số có phần lẻ (thẻ điện thoại không được đè số) + mã lệch +0,004 (khớp ở thẻ lẫn chip) ──
	bang(ngay("2026-06-11"), [("HX-TT1", 987664, "k"), ("HX-TT2", 10, "k")])
	nhap_kho()
	print("seeded san-xuat" + ("" if sx else " (không sx)"))


def nhap_kho():
	"""Phiếu nhập thành phẩm (SX Phieu Nhap TP) + nợ vào hộp (SX No Vao Hop) cho khối đối chiếu."""
	n = {"i": 0}

	def phieu(ngay, rows, docstatus=1, nguon=None):
		"""rows: [(mã, số đếm)] — số lập phiếu = số đếm (lệch thủ kho không thuộc khối này)."""
		n["i"] += 1
		name = f"SXNTP-BIMAT-{n['i']:03d}"
		insert("SX Phieu Nhap TP", name=name, ngay=ngay, docstatus=docstatus, nguon=nguon, kho_dich="Thành phẩm - HGC",
			trang_thai={0: "Nháp", 1: "Đã duyệt", 2: "Đã huỷ"}[docstatus], creation=f"{ngay} 07:30:00", owner=SECRET_USER,
			nguoi_lap=SECRET_USER, nguoi_duyet=SECRET_USER if docstatus else None, ghi_chu=SECRET_NOTE,
			tong_dem=sum(r[1] for r in rows), duyet_luc=f"{ngay} 17:00:00" if docstatus == 1 else None)
		for i, (item, dem) in enumerate(rows, 1):
			insert("SX Phieu Nhap TP Item", name=f"{name}-{i}", parent=name, parenttype="SX Phieu Nhap TP", parentfield="dong",
				idx=i, docstatus=docstatus, item=item, ten=item, dvt="Hộp", so_lap=dem, so_dem=dem, lech=0, ghi_chu=SECRET_NOTE)
		return name

	# Tháng 9: nhập một phần; hàng ghi 30/9 nhập 01/10 (tháng sau)
	phieu("2026-09-02", [("HX-TET1", 200), ("HX-TT1", 40)])
	phieu("2026-09-16", [("HX-TET1", 410), ("HX-TT1", 92)])
	phieu("2026-09-29", [("HX-TET1", 490)])
	# Tháng 10 (hôm nay giả 27/10)
	phieu("2026-10-01", [("HX-TET1", 120), ("HX-TT1", 24)])       # hàng ghi 30/9
	phieu("2026-10-02", [("HX-TET1", 240), ("HX-TT1", 120)])      # ngày sau ngày ghi
	phieu("2026-10-02", [("HX-TT2", 150), ("HX-AN", 40)])         # hai phiếu một ngày; mã ẩn
	phieu("2026-10-03", [("HX-TET1", 300), ("HX-TET2", 80)])
	phieu("2026-10-04", [("HX-TET2", 60), ("HX-TT1", 20)])        # cùng ngày ghi (Chủ nhật)
	phieu("2026-10-08", [("HX-TET1", 180), ("HX-TT1", 100), ("HX-TT2", 44.5), ("HX-KG", 12.5)])  # số đếm lẻ; ĐVT khác
	phieu("2026-10-12", [("HX-P01", 10), ("HX-P02", 25), ("HX-TT1", 30), ("HX-TT3", 50)])  # nhập vượt; mã chỉ có ở phiếu
	phieu("2026-10-16", [("HX-P04", 40), ("HX-P05", 45), ("HX-TT1", 45)])
	phieu("2026-10-27", [("HX-TET2", 130), ("HX-TT1", 55)])       # hôm nay
	phieu("2026-10-21", [("HX-TET1", 210)], docstatus=0)            # nháp: chưa nhập kho
	phieu("2026-10-26", [("HX-TT2", 33)], docstatus=0, nguon="Tết")  # nháp Tết
	phieu("2026-10-09", [("HX-TET1", 999), ("HX-P03", 30)], docstatus=2)  # đã huỷ: không tính
	phieu("2026-06-11", [("HX-TT1", 987670.99), ("HX-TT2", 10.004)])  # tháng 6: số lớn có phần lẻ; lệch 0,004 = khớp
	# Nợ vào hộp (sx ghi khi kho nhận vượt số ghi): đang chờ chấm / đã chấm bù / bỏ qua; một khoản của mã ẩn
	for i, (item, sl, con, tt, ngay) in enumerate((
			("HX-TT3", 50, 50, "Chờ chấm", "2026-10-12"), ("HX-P02", 15, 15, "Chờ chấm", "2026-10-12"),
			("HX-TT1", 10, 6, "Chờ chấm", "2026-10-16"), ("HX-P02", 5, 5, "Chờ chấm", "2026-10-20"),
			("HX-AN", 8, 8, "Chờ chấm", "2026-10-02"), ("HX-TET1", 30, 0, "Đã chấm bù", "2026-10-03"),
			("HX-TT2", 12, 12, "Bỏ qua", "2026-10-05"),
			("HX-KG", 9.5, 9.5, "Chờ chấm", "2026-10-09")), 1):   # nợ mã Kg: không cộng vào số "hộp" của ô
		insert("SX No Vao Hop", name=f"NV-BIMAT-{i:04d}", item=item, ten=item, so_luong=sl, con_lai=con, trang_thai=tt, ngay=ngay,
			phieu_nhap="SXNTP-BIMAT-001", ly_do=SECRET_LYDO, xu_ly_boi=SECRET_USER if tt != "Chờ chấm" else None,
			xu_ly_luc=f"{ngay} 09:00:00" if tt != "Chờ chấm" else None, owner=SECRET_USER)


if __name__ == "__main__":
	cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
	if cmd == "seed":
		seed()
	elif cmd == "nosx":
		seed()
		from seed import drop_doctype
		drop_doctype("SX Settings")
		print("bỏ SX Settings")
	elif cmd == "moc":
		import json
		seed()
		single("SX Settings", no_vh_tu_ngay="2026-10-15", no_vh_mang_sang=json.dumps({"HX-TT1": [["2026-10-05", 6]],
			"HX-KG": [["2026-10-05", 2]]}))
		print("mốc tính nợ vào hộp 15/10")
	else:
		sys.exit("dùng: seed_ui_san_xuat.py [seed|nosx|moc]")
