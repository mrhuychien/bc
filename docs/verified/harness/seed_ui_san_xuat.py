"""Seed cho kiểm giao diện màn Báo cáo sản xuất (ui_san_xuat.mjs): bảng Ghi hộp THẬT của sx (SX Ngay San Xuat, SX Bang Vao
Hop, SX Bang Vao Hop Item) — màn đọc qua bc.api.sx_hop thật.

BC_TEST_DB=bc_test_sxh_ui python3 -B seed_ui_san_xuat.py [seed|nosx]
	seed  (mặc định) hôm nay giả 27/10/2026: tháng 10 nhiều ngày (có Chủ nhật, hai bảng một ngày, bảng huỷ, ngày huỷ, khoán /
	      khoán chung / công nhật, mã chưa khai thùng, mã ẩn, ngày chưa chốt), 13 mã (bảng theo mã sang trang 2), tháng 9 đủ
	      tháng (so cùng kỳ), tháng 8 + tháng 3 (12 tháng), tháng 7 TRỐNG (tháng không có số).
	nosx  như seed rồi bỏ SX Settings (site không cài sx → available False).
Dòng ghi hộp mang tên nhân viên / đơn giá / thành tiền giả có dấu hiệu riêng — màn không được hiện.
"""
import sys

from seed import bc_settings, insert, reset, single

SECRET_NV = "Nguyễn Văn Bí Mật"
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
]


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
	print("seeded san-xuat" + ("" if sx else " (không sx)"))


if __name__ == "__main__":
	cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
	if cmd == "seed":
		seed()
	elif cmd == "nosx":
		seed()
		from seed import drop_doctype
		drop_doctype("SX Settings")
		print("bỏ SX Settings")
	else:
		sys.exit("dùng: seed_ui_san_xuat.py [seed|nosx]")
