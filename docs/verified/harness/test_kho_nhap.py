"""Nhập TP & giá vốn (bc.api.kho_nhap: K11 nhập kho thành phẩm theo phiếu sx, hàng đợi, đã vào hộp chưa nhập kho; K12 nợ
BOM, nguyên liệu còn treo, thành phẩm chưa có giá vốn) trên MariaDB thật, bảng sinh từ DocType JSON v16 + app sx.

Số kỳ vọng TÍNH TAY từ dữ liệu dưới (hôm nay 27/10/2026, tháng mặc định 01–27/10, 12 tháng = 11/2025 → 10/2026, cửa sổ
vào hộp 28/09 → 27/10). Mỗi bẫy của đặc tả có một ca: phiếu đã duyệt / nháp / huỷ, phiếu đã duyệt mà phiếu kho bị huỷ
(đối chiếu Σ số lượng = Σ so_dem lệch), ds_se hỏng, dòng phế phẩm chỉ có kho đích (W6), dòng so_dem = 0, phiếu nháp chưa
đếm (lấy số lập), phiếu nháp Tết + cột nguon thiếu, tuổi phiếu theo ngày tạo, mã chỉ có BOM không mặc định / BOM nháp /
BOM ngừng (sx coi là CHƯA có BOM), nợ BOM đủ 4 trạng thái (chỉ 'Chờ BOM' mở — không docstatus), gia_tam 0, biên
tuổi 7 / 8 / 30 / 31 ngày, BOM quantity 0 (chia 1) và 10, nguyên liệu không phải hàng kho, nguyên liệu nhóm BTP rút kho
BTP, giá vốn dự phòng (Bin kho khác, Item.valuation_rate, KHÔNG Item Price), nhập kho TP ngoài phiếu (nhập tay, chuyển từ
xưởng, đầu kỳ) vs điều chỉnh sx (kiểm kê, dọn tồn — loại), tồn giá vốn 0 ở kho bán được (cửa hàng, đi đường, kho ngừng
dùng) vs kho trả về / cách ly / công ty khác / tồn âm / mã không phải thành phẩm, mã ẩn, vào hộp (ngày SX huỷ, bảng huỷ,
ngoài cửa sổ, mã đơn vị Kg, phiếu đã duyệt ghi ngày SAU hôm nay — phía đã nhận không chặn trên), nợ BOM của mã chỉ có BOM
không mặc định (không "xử lý được ngay", "chưa ước tính được"), mã có nợ cũ nhất đúng 7 ngày (chưa "lâu"), lẫn đơn vị
Hộp + Kg kiểm RIÊNG từng ô (ngày, tháng, sổ kho, ngoài phiếu, hai vế đối chiếu), site không cài sx, thiếu bảng / cột, sổ
trống.

Chạy: BC_TEST_DB=bc_test_kho_nhap python3 -B test_kho_nhap.py
seed(k) chỉ THÊM dữ liệu tên NTP-… lên base(k) (để gộp seed cho kiểm giao diện): reset(); bc_settings(); k = K(); base(k);
seed(k); k.finalize().
"""
import ast
import datetime
import json
import os
import re

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset, single
from paths import BC_ROOT
from seed_kho import BTP, CACH_LY, CH1, CH2, DI_DUONG, G_BB, G_NL, G_QUA_TET, G_TRAD, KHO_CU, NVL, RV, TP, TRA_VE, XUONG, K, base

import frappe  # noqa: E402

PRIVATE = ["thukho.ntp@hgc.vn", "quanly.ntp@hgc.vn", "GHI CHÚ NTP RIÊNG", "LÝ DO NTP RIÊNG", "Nguyễn Văn Đóng Hộp NTP",
	"EMP-NTP-001", "khách NTP Bí Mật", "Lý do lệch NTP"]
DENY = ("_dong_du", "ma_lo_ton_cu", "prefix_lo", "gia_von_hien", "ghi_gia_tu_tinh")
SX_DOCTYPES = ("SX Phieu Nhap TP", "SX Phieu Nhap TP Item", "SX No BOM", "SX Bang Vao Hop", "SX Bang Vao Hop Item",
	"SX Ngay San Xuat")
A, B, C, D, E, KG, Z, H = "NTP-A", "NTP-B", "NTP-C", "NTP-D", "NTP-E", "NTP-K", "NTP-Z", "NTP-H"
NL1, NL2, NL3, NL4, BB1, BB2, NUOC, PP = ("NTP-NL1", "NTP-NL2", "NTP-NL3", "NTP-NL4", "NTP-BB1", "NTP-BB2", "NTP-NUOC",
	"NTP-PP")
TAM = "Nhập tạm — {} chưa có BOM. Nguyên liệu CHƯA trừ, ghi nợ ở SX No BOM (phiếu {} dòng 1)."


def _slip(name, ngay, docstatus, rows, ses=(), nguon=None, creation=None, ds_raw=None):
	"""Phiếu nhập TP. rows: [(mã, so_lap, so_dem)]. ds_se = Work Order + các Stock Entry (như sx on_submit)."""
	ds = ds_raw if ds_raw is not None else json.dumps(
		[{"dt": "Work Order", "name": f"{name}-WO"}] + [{"dt": "Stock Entry", "name": s} for s in ses])
	insert("SX Phieu Nhap TP", name=name, ngay=ngay, docstatus=docstatus, kho_dich=TP, ds_se=ds, nguon=nguon,
		trang_thai={0: "Nháp", 1: "Đã duyệt", 2: "Đã huỷ"}[docstatus], creation=creation or f"{ngay} 07:30:00",
		owner=PRIVATE[0], nguoi_lap=PRIVATE[0], nguoi_duyet=PRIVATE[1] if docstatus else None, ghi_chu=PRIVATE[2],
		tong_dem=sum(r[2] for r in rows), duyet_luc=f"{ngay} 17:00:00" if docstatus else None)
	for i, (item, lap, dem) in enumerate(rows, 1):
		insert("SX Phieu Nhap TP Item", name=f"{name}-{i}", parent=name, parenttype="SX Phieu Nhap TP", parentfield="dong",
			idx=i, docstatus=docstatus, item=item, ten=item, dvt="Hộp", so_lap=lap, so_dem=dem, lech=dem - lap,
			ghi_chu=PRIVATE[7] if dem != lap else None)


def _no(name, item, qty, gia, ngay, tt="Chờ BOM", phieu=None, se=None, **kw):
	insert("SX No BOM", name=name, item=item, ten=item, so_luong=qty, dvt="Hộp", trang_thai=tt, ngay=ngay, phieu_nhap=phieu,
		dong_idx=1, se_nhap=se, kho=TP, gia_tam=gia, **kw)


def _bom(name, item, qty, rows, active=1, default=1, docstatus=1):
	insert("BOM", name=name, item=item, is_active=active, is_default=default, docstatus=docstatus, quantity=qty,
		company="HGC")
	for i, (rm, sq) in enumerate(rows, 1):
		insert("BOM Item", name=f"{name}-{i}", parent=name, parenttype="BOM", parentfield="items", idx=i, item_code=rm,
			stock_qty=sq, qty=sq, docstatus=docstatus)


def _vh(ngay_sx, ngay, nsx_status, tables):
	"""Ngày sản xuất + bảng vào hộp: tables = [(tên bảng, docstatus, [(mã, số hộp)])]."""
	insert("SX Ngay San Xuat", name=ngay_sx, ngay=ngay, docstatus=nsx_status)
	for vh, st, rows in tables:
		insert("SX Bang Vao Hop", name=vh, ngay_sx=ngay_sx, docstatus=st, tong_hop=sum(r[1] for r in rows))
		for i, (sp, n) in enumerate(rows, 1):
			insert("SX Bang Vao Hop Item", name=f"{vh}-{i}", parent=vh, parenttype="SX Bang Vao Hop", parentfield="dong",
				idx=i, docstatus=st, san_pham=sp, so_hop=n, nhan_vien=PRIVATE[5], ten_nhan_vien=PRIVATE[4])


def seed(k: K):
	"""Kịch bản Nhập TP & giá vốn (mọi tên bắt đầu NTP-). Đơn giá ghi ở từng dòng; giá trị = số lượng × đơn giá."""
	tp = {"custom_sx_nhom": "TP"}
	# ── Mã hàng ── thành phẩm đánh dấu custom_sx_nhom = 'TP' (sx.utils.items_tp)
	k.item(A, "Bánh NTP A", G_TRAD, carton=20, **tp)          # có BOM (BOM-A, quantity 10)
	k.item(B, "Bánh NTP B", G_TRAD, carton=10, **tp)          # chỉ có BOM NHÁP → coi như chưa có
	k.item(C, "Hộp quà NTP C", G_QUA_TET, **tp)               # nhóm CON của Hàng Tết; CHƯA khai thùng; BOM ngừng dùng
	k.item(D, "Bánh NTP D", G_TRAD, carton=12, **tp)          # có BOM (BOM-D, quantity 0 → chia 1)
	k.item(E, "Bánh NTP E", G_TRAD, carton=24, **tp)          # chỉ BOM không mặc định → coi như chưa có
	k.item(KG, "Kẹo NTP cân", G_TRAD, uom="Kg", **tp)         # thành phẩm đơn vị Kg (vào hộp không cộng)
	k.item(Z, "Bánh NTP Z", G_TRAD, carton=6, **tp)           # tồn giá vốn 0 ở cửa hàng / đi đường / cách ly / RV
	k.item(H, "Bánh NTP ẩn", G_TRAD, **tp)                    # mã ẩn khỏi danh sách (vẫn vào tổng)
	k.item(PP, "Phế phẩm NTP", G_NL, uom="Kg")
	k.item(NL1, "Bột NTP", G_NL, uom="Kg", custom_sx_nhom="BTP-Bot")    # rút Kho BTP
	k.item(NL2, "Đường NTP", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.item(NL3, "Hương NTP", G_NL, uom="Kg", custom_sx_nhom="NVL")       # không có giá vốn nào (chỉ có giá MUA)
	k.item(NL4, "Bột nếp NTP", G_NL, uom="Kg", custom_sx_nhom="BTP-Nep")  # nhóm BTP nhưng chỉ có tồn ở Kho NVL
	k.item(BB1, "Hộp giấy NTP", G_BB, uom="Cái", custom_sx_nhom="Bao Bi")
	k.item(BB2, "Màng co NTP", G_BB, uom="Cái", custom_sx_nhom="Bao Bi", rate=300)  # chỉ có Item.valuation_rate
	k.item(NUOC, "Nước NTP", G_NL, uom="Lít")
	frappe.db.sql("UPDATE `tabItem` SET is_stock_item = 0 WHERE name = %s", (NUOC,))
	insert("Item Price", name="NTP-IP-1", item_code=NL3, price_list="Standard Buying", buying=1, price_list_rate=99_999)
	insert("BC Hidden Item", name="NTP-HID-1", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items",
		idx=9, item_code=H)

	# ── BOM ── chỉ "active + default + đã nộp" mới là có BOM (sx get_bom_active)
	_bom("NTP-BOM-A", A, 10, [(NL1, 1.0), (BB1, 10), (NUOC, 2)])
	_bom("NTP-BOM-D", D, 0, [(NL1, 0.2), (NL2, 0.1), (BB1, 1), (BB2, 2), (NL3, 0.05), (NL4, 0.1), (NUOC, 1)])
	_bom("NTP-BOM-E1", E, 1, [(NL1, 1)], default=0)            # không mặc định
	_bom("NTP-BOM-B0", B, 1, [(NL1, 1)], docstatus=0)          # nháp
	_bom("NTP-BOM-C0", C, 1, [(NL1, 1)], active=0)             # ngừng dùng

	# ── Nguyên liệu ──
	k.receipt(NL1, BTP, 100, 5_000_000, "2026-09-01", name="NTP-PR-01")   # 50.000 / kg
	k.receipt(NL1, NVL, 10, 400_000, "2026-09-02", name="NTP-PR-02")      # 40.000 / kg ở kho NVL (sai kho nguồn)
	k.receipt(NL2, NVL, 500, 10_000_000, "2026-08-01", name="NTP-PR-03")  # 20.000
	k.receipt(BB1, NVL, 1000, 2_000_000, "2026-08-01", name="NTP-PR-04")  # 2.000
	k.receipt(NL4, NVL, 10, 300_000, "2026-09-03", name="NTP-PR-05")      # 30.000

	# ── Phiếu nhập TP đã duyệt + phiếu kho của chúng (ghi đúng ngày phiếu) ──
	# 31/10/2025 — NGOÀI 12 tháng của tháng 10 (trong 12 tháng của tháng 9); ds_se hỏng → không gắn được giá trị
	k.se("Manufacture", "2025-10-31", [dict(item_code=A, t_warehouse=TP, qty=11, rate=7000, is_finished_item=1)],
		name="NTP-SE-31")
	_slip("NTP-PN-10", "2025-10-31", 1, [(A, 11, 11)], ds_raw="{hỏng")
	# 01/11/2025 — ngày ĐẦU cửa sổ 12 tháng
	k.se("Manufacture", "2025-11-01", [dict(item_code=A, t_warehouse=TP, qty=10, rate=7000, is_finished_item=1)],
		name="NTP-SE-30")
	_slip("NTP-PN-09", "2025-11-01", 1, [(A, 10, 10)], ["NTP-SE-30"])
	# 03/06/2026 — D, B chưa có BOM: nhập tạm (Material Receipt); nợ đã hạch toán bù / bỏ qua
	k.se("Material Receipt", "2026-06-03", [dict(item_code=D, t_warehouse=TP, qty=100, rate=5000)],
		remarks=TAM.format(D, "NTP-PN-07"), name="NTP-SE-10")
	k.se("Material Receipt", "2026-06-03", [dict(item_code=B, t_warehouse=TP, qty=10, rate=8000)],
		remarks=TAM.format(B, "NTP-PN-07"), name="NTP-SE-12")
	_slip("NTP-PN-07", "2026-06-03", 1, [(D, 100, 100), (B, 10, 10)], ["NTP-SE-10", "NTP-SE-12"])
	# 09/2026
	k.se("Manufacture", "2026-09-10", [dict(item_code=A, t_warehouse=TP, qty=200, rate=7000, is_finished_item=1)],
		name="NTP-SE-09")
	_slip("NTP-PN-06", "2026-09-10", 1, [(A, 200, 200)], ["NTP-SE-09"])
	k.se("Material Receipt", "2026-09-26", [dict(item_code=C, t_warehouse=TP, qty=5, rate=0)],
		remarks=TAM.format(C, "NTP-PN-15"), name="NTP-SE-35")
	_slip("NTP-PN-15", "2026-09-26", 1, [(C, 5, 5)], ["NTP-SE-35"])
	k.se("Material Receipt", "2026-09-27", [dict(item_code=B, t_warehouse=TP, qty=20, rate=0)],
		remarks=TAM.format(B, "NTP-PN-12"), name="NTP-SE-32")
	_slip("NTP-PN-12", "2026-09-27", 1, [(B, 20, 20)], ["NTP-SE-32"])
	# 10/2026
	k.se("Material Receipt", "2026-10-01", [dict(item_code=A, t_warehouse=TP, qty=50, rate=6000)],
		remarks=TAM.format(A, "NTP-PN-14"), name="NTP-SE-34")                     # A chưa có BOM lúc đó
	_slip("NTP-PN-14", "2026-10-01", 1, [(A, 50, 50)], ["NTP-SE-34"])
	k.se("Manufacture", "2026-10-05", [
		dict(item_code=NL1, s_warehouse=BTP, qty=9.8, rate=50_000),
		dict(item_code=BB1, s_warehouse=NVL, qty=98, rate=2000),
		dict(item_code=A, t_warehouse=TP, qty=98, rate=7000, is_finished_item=1),   # 686.000
		dict(item_code=PP, t_warehouse=TP, qty=5, rate=1000, secondary_item_type="Scrap"),  # W6: KHÔNG là thành phẩm
	], name="NTP-SE-01")
	k.se("Material Receipt", "2026-10-05", [dict(item_code=B, t_warehouse=TP, qty=50, rate=8000)],
		remarks=TAM.format(B, "NTP-PN-01"), name="NTP-SE-02")
	_slip("NTP-PN-01", "2026-10-05", 1, [(A, 100, 98), (B, 50, 50)], ["NTP-SE-01", "NTP-SE-02"])
	k.se("Material Receipt", "2026-10-05", [dict(item_code=C, t_warehouse=TP, qty=30, rate=0)],
		remarks=TAM.format(C, "NTP-PN-02"), name="NTP-SE-03")
	_slip("NTP-PN-02", "2026-10-05", 1, [(C, 30, 30), (A, 5, 0)], ["NTP-SE-03"])      # dòng A khai 5, nhận 0
	k.se("Manufacture", "2026-10-15", [dict(item_code=A, t_warehouse=TP, qty=60, rate=7000, is_finished_item=1)],
		docstatus=2, name="NTP-SE-08")                                                   # phiếu kho bị huỷ ngoài luồng
	_slip("NTP-PN-05", "2026-10-15", 1, [(A, 60, 60)], ["NTP-SE-08"])
	k.se("Material Receipt", "2026-10-19", [dict(item_code=D, t_warehouse=TP, qty=6, rate=5000)],
		remarks=TAM.format(D, "NTP-PN-13"), name="NTP-SE-33")
	_slip("NTP-PN-13", "2026-10-19", 1, [(D, 6, 6)], ["NTP-SE-33"])
	k.se("Manufacture", "2026-10-20", [
		dict(item_code=NL1, s_warehouse=BTP, qty=4, rate=50_000),
		dict(item_code=BB1, s_warehouse=NVL, qty=40, rate=2000),
		dict(item_code=A, t_warehouse=TP, qty=40, rate=7000, is_finished_item=1),   # 280.000
	], name="NTP-SE-04")
	k.se("Material Receipt", "2026-10-20", [dict(item_code=D, t_warehouse=TP, qty=24, rate=5000)],
		remarks=TAM.format(D, "NTP-PN-03"), name="NTP-SE-05")
	_slip("NTP-PN-03", "2026-10-20", 1, [(A, 40, 40), (D, 24, 24)], ["NTP-SE-04", "NTP-SE-05"])
	# 28/10 — SAU hôm nay (thủ kho ghi ngày tới): ngoài mọi kỳ nhập (kỳ cắt ở hôm nay) nhưng vẫn trừ vào "đã vào hộp chưa
	# nhập" (phía đã nhận không chặn trên — TP bẫy 13). Giá 9.000 → không phải giá vốn 0.
	k.se("Material Receipt", "2026-10-28", [dict(item_code=E, t_warehouse=TP, qty=12, rate=9000)],
		remarks=TAM.format(E, "NTP-PN-16"), name="NTP-SE-36")
	_slip("NTP-PN-16", "2026-10-28", 1, [(E, 12, 12)], ["NTP-SE-36"])
	# Phiếu đã HUỶ (sx huỷ phiếu → huỷ phiếu kho)
	k.se("Manufacture", "2026-10-12", [dict(item_code=A, t_warehouse=TP, qty=1000, rate=7000, is_finished_item=1)],
		docstatus=2, name="NTP-SE-06")
	k.se("Material Receipt", "2026-10-12", [dict(item_code=B, t_warehouse=TP, qty=777, rate=0)], docstatus=2,
		remarks=TAM.format(B, "NTP-PN-04"), name="NTP-SE-07")
	_slip("NTP-PN-04", "2026-10-12", 2, [(A, 1000, 1000), (B, 777, 777)], ["NTP-SE-06", "NTP-SE-07"])

	# ── Phiếu kho KHÔNG từ phiếu sx ──
	k.se("Material Receipt", "2026-10-08", [dict(item_code=A, t_warehouse=TP, qty=12, rate=7000)],
		remarks="Nhập lại hàng trả về — khách NTP Bí Mật", name="NTP-SE-20", owner=PRIVATE[1])   # ngoài phiếu ✓
	k.se("Material Receipt", "2026-09-30", [dict(item_code=B, t_warehouse=XUONG, qty=6, rate=8000)], name="NTP-SE-40")
	k.se("Material Transfer", "2026-10-09", [dict(item_code=B, s_warehouse=XUONG, t_warehouse=TP, qty=6, rate=8000)],
		name="NTP-SE-21")                                                                # từ Xưởng → ngoài phiếu ✓
	k.se("Material Receipt", "2026-09-14", [dict(item_code=A, t_warehouse=XUONG, qty=8, rate=7000)], name="NTP-SE-41")
	k.se("Material Transfer", "2026-09-15", [dict(item_code=A, s_warehouse=XUONG, t_warehouse=TP, qty=8, rate=7000)],
		name="NTP-SE-28")                                                                # tháng 9 ngoài phiếu ✓
	k.se("Material Receipt", "2026-10-10", [dict(item_code=A, t_warehouse=TP, qty=3, rate=0)], kiem_ke="NTP-KK-1",
		name="NTP-SE-22")                                                                # kiểm kê sx → loại
	k.se("Material Receipt", "2026-10-11", [dict(item_code=A, t_warehouse=TP, qty=4, rate=0)],
		remarks="Dọn tồn âm thành phẩm NTP", name="NTP-SE-23")                          # dọn tồn sx → loại
	k.se("Material Receipt", "2026-10-02", [dict(item_code=C, t_warehouse=TP, qty=7, rate=0)], is_opening="Yes",
		name="NTP-SE-24")                                                                # đầu kỳ → ngoài phiếu ✓, giá 0 ✓
	k.se("Material Receipt", "2026-10-10", [dict(item_code=B, t_warehouse=CH1, qty=5, rate=0)], name="NTP-SE-25")
	k.se("Material Receipt", "2026-10-11", [dict(item_code=A, t_warehouse=TRA_VE, qty=9, rate=0)], name="NTP-SE-26")
	k.se("Material Receipt", "2026-10-11", [dict(item_code=NL2, t_warehouse=XUONG, qty=100, rate=0)], name="NTP-SE-27")
	k.se("Material Receipt", "2026-10-12", [dict(item_code=C, t_warehouse=TP, qty=50, rate=0)], docstatus=0,
		name="NTP-SE-29")                                                                # nháp → không sổ
	k.se("Material Issue", "2026-10-22", [
		dict(item_code=NL1, s_warehouse=BTP, qty=20, rate=50_000), dict(item_code=NL2, s_warehouse=NVL, qty=10, rate=20_000),
		dict(item_code=BB1, s_warehouse=NVL, qty=100, rate=2000)],
		remarks="Hạch toán bù nợ BOM NTP-NB-05: 100 NTP-D nhập ngày 2026-06-03 (phiếu NTP-PN-07) theo NTP-BOM-D",
		name="NTP-SE-11")
	k.se("Material Receipt", "2026-07-01", [dict(item_code=H, t_warehouse=TP, qty=3, rate=0)], name="NTP-SE-42")
	k.se("Material Receipt", "2026-08-01", [dict(item_code=Z, t_warehouse=CH2, qty=18, rate=0)], name="NTP-SE-43")
	k.se("Material Transfer", "2026-10-25", [dict(item_code=Z, s_warehouse=CH2, t_warehouse=DI_DUONG, qty=6, rate=0)],
		name="NTP-SE-44")
	k.se("Material Receipt", "2026-08-02", [dict(item_code=Z, t_warehouse=CACH_LY, qty=4, rate=0)], name="NTP-SE-45")
	k.se("Material Receipt", "2026-08-03", [dict(item_code=Z, t_warehouse=RV, qty=3, rate=0)], name="NTP-SE-46")
	k.se("Material Receipt", "2025-12-01", [dict(item_code=C, t_warehouse=KHO_CU, qty=2, rate=0)], name="NTP-SE-47")
	k.sale(E, CH1, 2, 0, "2026-10-26", name="NTP-SI-01")                              # tồn âm giá 0 → không phải "tồn"

	# ── Phiếu NHÁP (hàng đợi) ──
	_slip("NTP-PN-21", "2026-10-26", 0, [(A, 30, 30), (E, 12, 12), (B, 6, 0)], creation="2026-10-26 08:00:00")  # B khai 6, đếm 0
	_slip("NTP-PN-22", "2026-10-25", 0, [(C, 25, 20)], nguon="Tết", creation="2026-10-25 10:00:00")
	_slip("NTP-PN-23", "2026-09-29", 0, [(B, 15, 0)], nguon="Tết", creation="2026-09-20 09:00:00")   # chưa đếm
	_slip("NTP-PN-24", "2026-09-27", 0, [(A, 7, 7)], nguon="Tết", creation="2026-09-27 09:00:00")    # trước cửa sổ

	# ── Sổ nợ BOM ── (đủ 4 trạng thái; chỉ 'Chờ BOM' đang mở)
	_no("NTP-NB-01", B, 50, 8000, "2026-10-05", phieu="NTP-PN-01", se="NTP-SE-02")
	_no("NTP-NB-02", C, 30, 0, "2026-10-05", phieu="NTP-PN-02", se="NTP-SE-03")
	_no("NTP-NB-03", D, 24, 5000, "2026-10-20", phieu="NTP-PN-03", se="NTP-SE-05")             # 7 ngày
	_no("NTP-NB-04", B, 777, 0, "2026-10-12", tt="Đã huỷ", phieu="NTP-PN-04", ly_do=PRIVATE[3])
	_no("NTP-NB-05", D, 100, 5000, "2026-06-03", tt="Đã hạch toán bù", phieu="NTP-PN-07", se="NTP-SE-10",
		se_bu="NTP-SE-11", bom="NTP-BOM-D", xu_ly_boi=PRIVATE[1], xu_ly_luc="2026-10-22 10:00:00")
	_no("NTP-NB-06", B, 10, 8000, "2026-06-03", tt="Bỏ qua", phieu="NTP-PN-07", se="NTP-SE-12", ly_do=PRIVATE[3],
		xu_ly_boi=PRIVATE[1], xu_ly_luc="2026-07-01 10:00:00")
	_no("NTP-NB-07", B, 20, 0, "2026-09-27", phieu="NTP-PN-12", se="NTP-SE-32")                # 30 ngày, giá 0 (cột số NOT NULL)
	_no("NTP-NB-08", D, 6, 5000, "2026-10-19", phieu="NTP-PN-13", se="NTP-SE-33")              # 8 ngày
	_no("NTP-NB-09", A, 50, 6000, "2026-10-01", phieu="NTP-PN-14", se="NTP-SE-34")
	_no("NTP-NB-10", C, 5, 0, "2026-09-26", phieu="NTP-PN-15", se="NTP-SE-35")                 # 31 ngày
	# E chỉ có BOM KHÔNG mặc định → chưa "xử lý được ngay", "chưa ước tính được"; nợ cũ nhất của E đúng 7 ngày → chưa "lâu"
	_no("NTP-NB-11", E, 12, 9000, "2026-10-20")

	# ── Vào hộp (cửa sổ 28/09 → 27/10) ──
	_vh("NTP-NSX-1", "2026-10-25", 0, [("NTP-VH-1", 0, [(A, 250), (B, 30), (C, 60), (KG, 15), ("", 7)]),
		("NTP-VH-5", 2, [(B, 888)])])                                   # bảng huỷ → bỏ
	_vh("NTP-NSX-2", "2026-10-10", 2, [("NTP-VH-2", 1, [(A, 999)])])     # ngày SX huỷ → bỏ
	_vh("NTP-NSX-3", "2026-09-27", 1, [("NTP-VH-3", 1, [(A, 500)])])     # trước cửa sổ → bỏ
	_vh("NTP-NSX-4", "2026-09-28", 1, [("NTP-VH-4", 1, [(D, 36)])])      # ngày ĐẦU cửa sổ
	_vh("NTP-NSX-5", "2026-10-27", 0, [("NTP-VH-6", 0, [(E, 24)])])      # hôm nay


def mixed_ledger(k: K):
	"""Lẫn đơn vị, vế SỔ: nhập tay mã Kg vào Kho TP, không qua phiếu — 09/10 (2,5 kg, cùng tháng với các mã hộp) và 05/08
	(1,5 kg, tháng chỉ có kg). Thêm được sau finalize (K11 đọc phiếu kho, không đọc Bin)."""
	k.se("Material Receipt", "2026-10-09", [dict(item_code=KG, t_warehouse=TP, qty=2.5, rate=1000)], name="NTP-SE-50")
	k.se("Material Receipt", "2026-08-05", [dict(item_code=KG, t_warehouse=TP, qty=1.5, rate=1000)], name="NTP-SE-51")


def mixed_slip(k: K):
	"""Lẫn đơn vị, vế PHIẾU: phiếu đã duyệt 21/10 mã Kg 4,5 chưa có phiếu kho (ds_se trống) + nợ BOM Kg 2; phiếu đã duyệt
	22/10 mã Kg 3 CÓ phiếu kho nhập tạm (3 × 1.000) — dòng sổ Kg vào "nhập tạm" và vào vế sổ của đối chiếu."""
	_slip("NTP-PN-30", "2026-10-21", 1, [(KG, 4.5, 4.5)], ds_raw="[]")
	_no("NTP-NB-30", KG, 2, 1000, "2026-10-21", phieu="NTP-PN-30")
	k.se("Material Receipt", "2026-10-22", [dict(item_code=KG, t_warehouse=TP, qty=3, rate=1000)],
		remarks=TAM.format(KG, "NTP-PN-31"), name="NTP-SE-52")
	_slip("NTP-PN-31", "2026-10-22", 1, [(KG, 3, 3)], ["NTP-SE-52"])


def unmixed():
	for se in ("NTP-SE-50", "NTP-SE-51", "NTP-SE-52"):
		frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE voucher_no = %s", (se,))
		frappe.db.sql("DELETE FROM `tabStock Entry Detail` WHERE parent = %s", (se,))
		frappe.db.sql("DELETE FROM `tabStock Entry` WHERE name = %s", (se,))
	frappe.db.sql("DELETE FROM `tabSX Phieu Nhap TP` WHERE name IN ('NTP-PN-30', 'NTP-PN-31')")
	frappe.db.sql("DELETE FROM `tabSX Phieu Nhap TP Item` WHERE parent IN ('NTP-PN-30', 'NTP-PN-31')")
	frappe.db.sql("DELETE FROM `tabSX No BOM` WHERE name = 'NTP-NB-30'")


def run(thang=None):
	from bc.api import kho_nhap
	frappe.local.__dict__.pop("sx_nho", None)  # nhớ-theo-request của sx — mỗi lượt gọi như một request mới
	return kho_nhap.get_overview(thang=thang, refresh=1)


def full(sx=True):
	reset()
	bc_settings()
	k = K()
	base(k, sx=sx)
	seed(k)
	k.finalize()
	return k


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


def pick(d, *keys):
	return {k_: d.get(k_) for k_ in keys}


if __name__ == "__main__":
	c = Check()
	k = full()
	from bc.api import kho_nhap

	d = run()
	c("có dữ liệu", d["available"] is True)
	c("kỳ mặc định = tháng này cắt ở hôm nay; 12 tháng 11/2025 → 10/2026",
		pick(d["meta"], "thang", "from", "to", "as_of", "prev", "sx", "kho_tp") == {"thang": "2026-10", "from": "2026-10-01",
		"to": "2026-10-27", "as_of": "2026-10-27", "prev": "2026-09", "sx": True, "kho_tp": TP}
		and d["meta"]["months"][0] == "2025-11" and d["meta"]["months"][-1] == "2026-10" and len(d["meta"]["months"]) == 12,
		d["meta"])

	# ══ K11 · nhập kho theo phiếu ══
	n = d["nhap"]
	t = n["total"]
	# Phiếu đã duyệt 01–27/10: PN-14 A 50 · PN-01 A 98 + B 50 · PN-02 C 30 + A 0 · PN-05 A 60 · PN-13 D 6 · PN-03 A 40 + D 24
	#   = 50 + 148 + 30 + 60 + 6 + 64 = 358 (A 248, B 50, C 30, D 30); PN-04 đã huỷ (1777) không tính.
	c("số lượng = Σ so_dem phiếu đã duyệt theo ngày phiếu (bỏ phiếu huỷ / nháp)", (t["qty"], t["uom"], t["slips"], t["items"])
		== (358, "Hộp", 6, 4), pick(t, "qty", "uom", "slips", "items"))
	# Thùng: A 248/20 = 12,4 · B 50/10 = 5 · D 30/12 = 2,5 → 19,9; C (30 hộp) chưa khai thùng
	c("thùng + phần chưa khai quy cách thùng", (t["cartons"], t["boxes_without_carton_factor"], t["items_without_carton_factor"],
		t["uom_without"]) == (19.9, 30, 1, "Hộp"), pick(t, "cartons", "boxes_without_carton_factor", "items_without_carton_factor"))
	# Giá trị (sổ, dòng thành phẩm): SE-34 50×6.000 = 300.000 · SE-01 FG 98×7.000 = 686.000 (phế phẩm 5.000 KHÔNG tính) ·
	#   SE-02 400.000 · SE-03 0 · SE-04 FG 280.000 · SE-05 120.000 · SE-33 30.000 · SE-08 huỷ 0 → 1.816.000
	c("giá trị = Σ chênh lệch giá trị sổ của dòng thành phẩm (W6: bỏ dòng phế phẩm, bỏ sổ huỷ)", t["value"] == 1_816_000, t["value"])
	# Có BOM: SE-01 A 98 + SE-04 A 40 = 138 (686.000 + 280.000); nhập tạm: SE-34 A 50 + SE-02 B 50 + SE-03 C 30 + SE-33 D 6 +
	#   SE-05 D 24 = 160 (300.000 + 400.000 + 0 + 30.000 + 120.000). PN-16 ngày 28/10 (sau hôm nay) không vào kỳ.
	c("trong đó có BOM (Manufacture) / nhập tạm", t["by_kind"] == {"bom": {"qty": 138, "uom": "Hộp", "value": 966_000},
		"tam": {"qty": 160, "uom": "Hộp", "value": 850_000}}, t["by_kind"])
	c("số ngày có nhập", t["days"] == 5, t["days"])
	c("đơn vị theo mã", t["by_uom"] == [{"uom": "Hộp", "qty": 358}], t["by_uom"])
	bd = {r["date"]: r for r in n["by_day"]}
	c("theo ngày: đủ 27 ngày (ngày không nhập = 0, không đơn vị); ngày có nhập kèm đơn vị", len(n["by_day"]) == 27
		and n["by_day"][0]["date"] == "2026-10-01" and n["by_day"][-1]["date"] == "2026-10-27"
		and (bd["2026-10-02"]["qty"], bd["2026-10-02"]["uom"], bd["2026-10-05"]["uom"]) == (0, None, "Hộp"), len(n["by_day"]))
	# 05/10: A 98 + B 50 + C 30 = 178; thùng 4,9 + 5 = 9,9; 686.000 + 400.000 + 0
	c("theo ngày 01/10, 05/10, 15/10, 19/10, 20/10", [pick(bd[x], "qty", "cartons", "value", "slips") for x in
		("2026-10-01", "2026-10-05", "2026-10-15", "2026-10-19", "2026-10-20")] == [
		{"qty": 50, "cartons": 2.5, "value": 300_000, "slips": 1}, {"qty": 178, "cartons": 9.9, "value": 1_086_000, "slips": 2},
		{"qty": 60, "cartons": 3.0, "value": 0, "slips": 1}, {"qty": 6, "cartons": 0.5, "value": 30_000, "slips": 1},
		{"qty": 64, "cartons": 4.0, "value": 400_000, "slips": 1}], [bd[x] for x in ("2026-10-05", "2026-10-15")])
	c("Σ theo ngày = tổng tháng", round(sum(r["qty"] for r in n["by_day"]), 3) == t["qty"]
		and round(sum(r["value"] for r in n["by_day"]), 2) == t["value"])
	# Đối chiếu Σ số lượng dòng sổ = Σ so_dem: 358 − (SE-08 huỷ: 60) = 298 → lệch 60, 1 phiếu (PN-05)
	c("đối chiếu Σ dòng sổ thành phẩm vs Σ so_dem: phiếu đã duyệt mà phiếu kho bị huỷ", n["doi_chieu"] == {"slip_qty": 358,
		"slip_uom": "Hộp", "se_qty": 298, "se_uom": "Hộp", "lech": 60, "lech_uom": "Hộp", "slips_lech": 1}, n["doi_chieu"])
	bm = {r["month"]: r for r in n["by_month"]}
	c("12 tháng, cũ trước", [r["month"] for r in n["by_month"]] == d["meta"]["months"])
	# Sổ kho (production_filter đúng kho TP) tháng 10: 298 (phiếu kho của phiếu) + SE-20 12 (nhập tay) + SE-21 6 (từ Xưởng) +
	#   SE-24 7 (đầu kỳ) = 323; KHÔNG: SE-22 kiểm kê, SE-23 dọn tồn, SE-25 cửa hàng, SE-26 trả về, SE-08/06/07 huỷ, SE-29 nháp
	c("tháng 10: phiếu 358 · sổ kho 323 · chênh −35 · ngoài phiếu 25 (3 phiếu kho), cùng đơn vị hộp", pick(bm["2026-10"],
		"qty", "uom", "value", "slips", "cartons", "so_kho_qty", "so_kho_uom", "chenh", "ngoai_phieu", "ngoai_uom",
		"ngoai_entries") == {"qty": 358, "uom": "Hộp", "value": 1_816_000, "slips": 6, "cartons": 19.9, "so_kho_qty": 323,
		"so_kho_uom": "Hộp", "chenh": -35, "ngoai_phieu": 25, "ngoai_uom": "Hộp", "ngoai_entries": 3}, bm["2026-10"])
	# Tháng 9: PN-06 A 200 (1.400.000) + PN-15 C 5 (0) + PN-12 B 20 (0) = 225; thùng 10 + 2 = 12; sổ 225 + SE-28 8 = 233
	c("tháng 9", pick(bm["2026-09"], "qty", "value", "slips", "cartons", "so_kho_qty", "chenh", "ngoai_phieu",
		"ngoai_entries") == {"qty": 225, "value": 1_400_000, "slips": 3, "cartons": 12.0, "so_kho_qty": 233, "chenh": 8,
		"ngoai_phieu": 8, "ngoai_entries": 1}, bm["2026-09"])
	# 06/2026: PN-07 D 100 (500.000) + B 10 (80.000); thùng 100/12 + 1 = 9,33 → 9,3
	c("tháng 6", pick(bm["2026-06"], "qty", "value", "slips", "cartons", "so_kho_qty", "chenh") == {"qty": 110, "value": 580_000,
		"slips": 1, "cartons": 9.3, "so_kho_qty": 110, "chenh": 0}, bm["2026-06"])
	c("tháng 7: chỉ nhập tay mã ẩn (ngoài phiếu 3, 1 phiếu kho)", pick(bm["2026-07"], "qty", "uom", "so_kho_qty", "ngoai_phieu",
		"ngoai_entries", "chenh") == {"qty": 0, "uom": None, "so_kho_qty": 3, "ngoai_phieu": 3, "ngoai_entries": 1, "chenh": 3},
		bm["2026-07"])
	c("11/2025 (ngày đầu cửa sổ) có, 31/10/2025 nằm ngoài", pick(bm["2025-11"], "qty", "value", "slips") == {"qty": 10,
		"value": 70_000, "slips": 1} and "2025-10" not in bm, bm.get("2025-11"))
	c("tháng không nhập = 0", pick(bm["2026-01"], "qty", "uom", "value", "slips", "so_kho_qty", "ngoai_phieu", "ngoai_entries")
		== {"qty": 0, "uom": None, "value": 0, "slips": 0, "so_kho_qty": 0, "ngoai_phieu": 0, "ngoai_entries": 0}, bm["2026-01"])
	# ══ XR-COMP-2 · mỗi ô thùng (từng ngày, từng tháng của bảng 12 tháng) kèm phần chưa khai quy cách thùng — thùng chỉ tính
	# mã CÓ hệ số; mã không hệ số (C, hộp quà Tết) không được âm thầm rơi khỏi cột "Thùng" / biểu đồ thùng ══
	ck = ("cartons", "boxes_without_carton_factor", "items_without_carton_factor", "uom_without")
	# T10: A 248 / 20 = 12,4 · B 50 / 10 = 5 · D 30 / 12 = 2,5 → 19,9 thùng; C 30 hộp KHÔNG có hệ số → 30 Hộp, 1 mã
	c("XR-COMP-2 tháng 10: 19,9 thùng + 30 Hộp chưa khai thùng (C), 1 mã", pick(bm["2026-10"], *ck) == {"cartons": 19.9,
		"boxes_without_carton_factor": 30, "items_without_carton_factor": 1, "uom_without": "Hộp"}, pick(bm["2026-10"], *ck))
	# T9 (tháng CŨ của bảng 12 tháng): A 200 / 20 = 10 · B 20 / 10 = 2 → 12,0; C 5 (PN-15) chưa khai
	c("XR-COMP-2 tháng 9 trong bảng 12 tháng: 12 thùng + 5 Hộp chưa khai", pick(bm["2026-09"], *ck) == {"cartons": 12.0,
		"boxes_without_carton_factor": 5, "items_without_carton_factor": 1, "uom_without": "Hộp"}, pick(bm["2026-09"], *ck))
	# T6: D 100 / 12 + B 10 / 10 = 9,33 → 9,3 — mọi mã có hệ số → phần chưa khai 0, 0 mã, không đơn vị; tháng trống 01/2026 → 0
	c("XR-COMP-2 tháng đủ hệ số (T6) / tháng trống (T1): phần chưa khai 0", (pick(bm["2026-06"], *ck), pick(bm["2026-01"], *ck))
		== ({"cartons": 9.3, "boxes_without_carton_factor": 0, "items_without_carton_factor": 0, "uom_without": None},
		{"cartons": 0, "boxes_without_carton_factor": 0, "items_without_carton_factor": 0, "uom_without": None}),
		(pick(bm["2026-06"], *ck), pick(bm["2026-01"], *ck)))
	# Ngày 05/10: A 98 / 20 = 4,9 + B 50 / 10 = 5 → 9,9; C 30 chưa khai · 01/10: A 50 / 20 = 2,5 · 02/10: không nhập
	c("XR-COMP-2 theo ngày: 05/10 9,9 thùng + 30 Hộp chưa khai; 01/10 2,5 thùng; 02/10 trống", [pick(bd[x], *ck) for x in
		("2026-10-05", "2026-10-01", "2026-10-02")] == [{"cartons": 9.9, "boxes_without_carton_factor": 30,
		"items_without_carton_factor": 1, "uom_without": "Hộp"}, {"cartons": 2.5, "boxes_without_carton_factor": 0,
		"items_without_carton_factor": 0, "uom_without": None}, {"cartons": 0, "boxes_without_carton_factor": 0,
		"items_without_carton_factor": 0, "uom_without": None}], [pick(bd[x], *ck) for x in ("2026-10-05", "2026-10-01")])
	# Bất biến: Σ phần chưa khai theo ngày = phần chưa khai của tổng tháng = ô tháng 10 (30); Σ thùng theo ngày = 19,9
	c("XR-COMP-2 Σ theo ngày phần chưa khai = tổng tháng = ô tháng 10 (30); Σ thùng theo ngày = 19,9",
		round(sum(r.get("boxes_without_carton_factor") or 0 for r in n["by_day"]), 3) == t["boxes_without_carton_factor"]
		== bm["2026-10"].get("boxes_without_carton_factor") == 30 and round(sum(r["cartons"] for r in n["by_day"]), 1) == 19.9,
		round(sum(r.get("boxes_without_carton_factor") or 0 for r in n["by_day"]), 3))

	np_ = n["ngoai_phieu"]
	c("nhập Kho TP ngoài phiếu sx tháng 10: 3 phiếu kho, A 12 / C 7 / B 6", (np_["qty"], np_["entries"],
		[(r["item_code"], r["qty"]) for r in np_["items"]]) == (25, 3, [(A, 12), (C, 7), (B, 6)]), np_)
	top = n["top_items"]
	c("mã nhập trong tháng (nhiều trước): A 248 / 1.266.000 · B 50 / 400.000 · C, D 30",
		[(r["item_code"], r["qty"], r["value"]) for r in top] == [(A, 248, 1_266_000), (B, 50, 400_000), (D, 30, 150_000),
		(C, 30, 0)] and top[0]["cartons"] == 12.4 and top[0]["short_name"] == "Bánh NTP A" and top[0]["uom"] == "Hộp",
		[(r["item_code"], r["qty"], r["value"]) for r in top])

	# ══ K11 · phiếu chờ duyệt ══
	q = d["cho_duyet"]
	# PN-21: đã đếm (Σ so_dem > 0 → số đếm cả phiếu, dòng B khai 6 đếm 0 góp 0) A 30 + E 12 + B 0 = 42 (E chỉ BOM không mặc
	#   định → nợ BOM 12; B 0) · PN-22 Tết: đếm 20 (C, BOM ngừng → 20) ·
	# PN-23 Tết CHƯA đếm → số lập 15 (B, BOM nháp → 15) · PN-24 Tết A 7 (có BOM → 0). Tổng 84, nợ BOM 47.
	c("phiếu chờ duyệt: số phiếu, phiếu Tết, số lượng (chưa đếm → số lập), phần thành nợ BOM",
		pick(q, "count", "count_tet", "qty", "no_bom_qty", "chua_dem") == {"count": 4, "count_tet": 3, "qty": 84,
		"no_bom_qty": 47, "chua_dem": 1}, pick(q, "count", "count_tet", "qty", "no_bom_qty", "chua_dem"))
	c("phiếu cũ nhất theo NGÀY TẠO (20/09 → 37 ngày), không theo ngày phiếu",
		(q["oldest_age_days"], q["oldest_date"]) == (37, "2026-09-20"), (q["oldest_age_days"], q["oldest_date"]))
	c("danh sách phiếu: cũ trước, có tuổi / Tết / phần nợ BOM", [(r["name"], r["age_days"], r["qty"], r["no_bom_qty"], r["tet"])
		for r in q["rows"]] == [("NTP-PN-23", 37, 15, 15, True), ("NTP-PN-24", 30, 7, 0, True), ("NTP-PN-22", 2, 20, 20, True),
		("NTP-PN-21", 1, 42, 12, False)], q["rows"])

	# ══ K11 · đã vào hộp chưa nhập kho (28/09 → 27/10) ══
	v = d["vao_hop"]
	# Vào hộp: A 250, B 30, C 60, Kg 15 (NSX-1) + D 36 (28/09) + E 24 (hôm nay); bỏ bảng / ngày huỷ, 27/09, dòng không mã.
	# Đã nhận (đã duyệt, ngày ≥ 28/09, KHÔNG chặn trên): A 50+98+0+60+40 = 248 · B 50 · C 30 · D 6+24 = 30 · E 12 (PN-16 ngày
	#   28/10 — sau hôm nay vẫn trừ); nháp Tết ≥ 28/09: C 20 (PN-24 27/09 bỏ)
	# Còn: A 2 · B −20 (bỏ) · C 60−30−20 = 10 · D 6 · E 24−12 = 12 · Kg 15 (đơn vị khác, liệt kê riêng)
	c("cửa sổ 30 ngày tới hôm nay", (v["from"], v["to"]) == ("2026-09-28", "2026-10-27"), (v["from"], v["to"]))
	c("đã vào hộp chưa nhập: mã còn > 0, trừ phiếu đã duyệt + nháp Tết", [(r["item_code"], r["qty"], r["khac_dvt"])
		for r in v["rows"]] == [(E, 12, False), (C, 10, False), (D, 6, False), (A, 2, False), (KG, 15, True)], v["rows"])
	# Hộp: 12 + 10 + 6 + 2 = 30. Thùng: E 12/24 = 0,5 · D 6/12 = 0,5 · A 2/20 = 0,1 → 1,1; C 10 Hộp chưa khai thùng (kèm đơn vị
	#   để thẻ ghi "10 Hộp", không phải "10"); Kg không cộng
	c("tổng hộp (bỏ mã đơn vị Kg) + thùng + phần chưa khai kèm đơn vị", pick(v, "qty", "items", "items_khac_dvt", "cartons",
		"boxes_without_carton_factor", "uom_without") == {"qty": 30, "items": 4, "items_khac_dvt": 1, "cartons": 1.1,
		"boxes_without_carton_factor": 10, "uom_without": "Hộp"},
		pick(v, "qty", "items", "items_khac_dvt", "cartons", "boxes_without_carton_factor", "uom_without"))

	# ══ K12a · nợ BOM đang mở ══
	b = d["no_bom"]
	# Mở: NB-01 B 50×8.000 · NB-02 C 30×0 · NB-03 D 24×5.000 · NB-07 B 20×0 · NB-08 D 6×5.000 · NB-09 A 50×6.000 · NB-10 C 5×0
	#   · NB-11 E 12×9.000 = 197; giá tạm 400.000 + 120.000 + 30.000 + 300.000 + 108.000 = 958.000; giá 0: 30 + 20 + 5 = 55 (3 dòng)
	c("nợ BOM mở = trang_thai 'Chờ BOM' (bỏ Đã huỷ / Đã hạch toán bù / Bỏ qua)", pick(b, "items", "rows", "qty", "value_tam",
		"qty_gia_0", "rows_gia_0") == {"items": 5, "rows": 8, "qty": 197, "value_tam": 958_000, "qty_gia_0": 55, "rows_gia_0": 3},
		pick(b, "items", "rows", "qty", "value_tam", "qty_gia_0", "rows_gia_0"))
	c("thùng: A 2,5 + B 7 + D 2,5 + E 0,5; C 35 chưa khai", (b["uom"], b["cartons"], b["boxes_without_carton_factor"])
		== ("Hộp", 12.5, 35), (b["uom"], b["cartons"], b["boxes_without_carton_factor"]))
	c("nợ cũ nhất 26/09 → 31 ngày", (b["oldest"], b["age_days"]) == ("2026-09-26", 31), (b["oldest"], b["age_days"]))
	# 0-7: NB-03 D 24 + NB-11 E 12 (20/10, 7 ngày) · 8-30: NB-08 (8) + NB-01 + NB-02 (22) + NB-09 (26) + NB-07 (30)
	#   = 6+50+30+50+20 · >30: NB-10 (31)
	c("tuổi nợ: biên 7 / 8 / 30 / 31 ngày", [(x["key"], x["rows"], x["qty"]) for x in b["buckets"]] == [("0-7", 2, 36),
		("8-30", 5, 156), (">30", 1, 5)], b["buckets"])
	c("xử lý được ngay = mã đã có BOM đang dùng (A 50 + D 30) — E (chỉ BOM không mặc định) / B (BOM nháp) / C (BOM ngừng) không",
		b["xu_ly_ngay"] == {"items": 2, "qty": 80}, b["xu_ly_ngay"])
	c("danh sách: có BOM trước, rồi nợ lâu", [(r["item_code"], r["qty"], r["value_tam"], r["qty_gia_0"], r["age_days"],
		r["co_bom"], r["rows"]) for r in b["list"]] == [(A, 50, 300_000, 0, 26, True, 1), (D, 30, 150_000, 0, 8, True, 2),
		(C, 35, 0, 35, 31, False, 2), (B, 70, 400_000, 20, 30, False, 2), (E, 12, 108_000, 0, 7, False, 1)], b["list"])
	# Quá 7 ngày: A 26, D 8 (nợ cũ nhất NB-08), C 31, B 30 = 4; E cũ nhất đúng 7 ngày → chưa lâu
	c("mã nợ quá 7 ngày (nợ đúng 7 ngày chưa tính)", b["lau"] == 4 and by(b["list"], "item_code", E)["lau"] is False
		and by(b["list"], "item_code", D)["lau"] is True, (b["lau"], [(r["item_code"], r["lau"]) for r in b["list"]]))

	# ══ K12b · nguyên liệu còn treo ══
	r = d["nvl_treo"]
	# A 50 (BOM-A quantity 10): NL1 5 kg, BB1 50; D 30 (BOM-D quantity 0 → 1): NL1 6, NL2 3, BB1 30, BB2 60, NL3 1,5, NL4 3;
	# Nước (không phải hàng kho) bỏ. Giá: NL1 @BTP 50.000 (Bin) · BB1 @NVL 2.000 · NL4 nhóm BTP → kho BTP không có → Bin kho
	# khác 30.000 · NL2 @NVL 20.000 · BB2 Item.valuation_rate 300 · NL3 chưa có giá vốn (giá mua 99.999 KHÔNG dùng).
	# 11×50.000 + 80×2.000 + 3×30.000 + 3×20.000 + 60×300 = 550.000 + 160.000 + 90.000 + 60.000 + 18.000 = 878.000
	c("NVL treo = bung BOM một cấp × giá vốn dự phòng", (r["value"], r["n_rm"], r["chua_co_gia"], r["fg_items"])
		== (878_000, 6, {"n": 1}, 2), pick(r, "value", "n_rm", "chua_co_gia", "fg_items"))
	c("từng nguyên liệu: kho nguồn, đơn giá, nguồn giá", [(x["item_code"], x["warehouse"], x["qty"], x["rate"], x["rate_source"],
		x["value"]) for x in r["list"]] == [(NL1, BTP, 11, 50_000, "bin", 550_000), (BB1, NVL, 80, 2000, "bin", 160_000),
		(NL4, BTP, 3, 30_000, "bin_khac", 90_000), (NL2, NVL, 3, 20_000, "bin", 60_000), (BB2, NVL, 60, 300, "item", 18_000),
		(NL3, NVL, 1.5, None, None, None)], r["list"])
	c("mã nợ chưa có BOM đang dùng → chưa ước tính được (B 70 + C 35 + E 12, E chỉ có BOM không mặc định)",
		r["chua_uoc_tinh"] == {"items": 3, "qty": 117, "uom": "Hộp"}, r["chua_uoc_tinh"])

	# ══ K12c · thành phẩm chưa có giá vốn ══
	g = d["gia_von_0"]
	tn = g["ton"]
	# Bin TP, kho bán được, tồn > 0, giá ≤ 0: B@CH1 5 · C@TP 30+7+5 = 42 · C@Kho cũ (ngừng dùng) 2 · Z@CH2 12 · Z@đi đường 6 ·
	#   H@TP 3 (ẩn) = 70. KHÔNG: A@trả về 9, Z@cách ly 4, Z@RV (công ty khác), E@CH1 −2 (âm), NL2@Xưởng (không phải TP)
	c("tồn thành phẩm giá vốn 0 ở kho bán được", pick(tn, "rows", "items", "qty", "uom", "cartons", "boxes_without_carton_factor")
		== {"rows": 6, "items": 4, "qty": 70, "uom": "Hộp", "cartons": 3.5, "boxes_without_carton_factor": 47},
		pick(tn, "rows", "items", "qty", "uom", "cartons", "boxes_without_carton_factor"))
	c("danh sách tồn giá 0: bỏ mã ẩn, nhiều trước, có kho", [(x["item_code"], x["warehouse"], x["qty"]) for x in tn["list"]] == [
		(C, TP, 42), (Z, CH2, 12), (Z, DI_DUONG, 6), (B, CH1, 5), (C, KHO_CU, 2)]
		and by(tn["list"], "warehouse", DI_DUONG)["role_label"] == "Hàng đi đường", tn["list"])
	nk = g["nhap_ky"]
	# Nhập tháng 10 đơn giá 0 (điều kiện sản xuất, kho bán được, mã TP): SE-03 C 30 + SE-24 C 7 (đầu kỳ) + SE-25 B 5 (cửa hàng)
	#   = 42; KHÔNG: SE-26 trả về, SE-27 nguyên liệu, SE-22/23 điều chỉnh sx, SE-07 huỷ, SE-29 nháp, SE-35/32 tháng 9
	c("nhập thành phẩm đơn giá 0 trong tháng", (nk["qty"], nk["entries"], nk["items"], [(x["item_code"], x["qty"])
		for x in nk["list"]]) == (42, 3, 2, [(C, 37), (B, 5)]), nk)
	c("tập thành phẩm theo sx", g["tp_source"] == "sx", g["tp_source"])

	# ══ Riêng tư + nguồn ══
	dump = json.dumps(d, ensure_ascii=False, default=str)
	c("không lộ người lập / duyệt / xử lý, ghi chú, lý do, remarks, nhân viên vào hộp",
		not [x for x in PRIVATE if x in dump] and "@" not in dump, [x for x in PRIVATE if x in dump])
	c("không trả trường riêng tư", not re.search(r'"(owner|nguoi_[a-z_]+|ghi_chu|ly_do|xu_ly_boi|remarks|nhan_vien)"', dump))
	src = open(os.path.join(BC_ROOT, "bc", "api", "kho_nhap.py"), encoding="utf-8").read()
	c("không dùng helper sx có ghi DB / giá mua", not [x for x in DENY if x in src], [x for x in DENY if x in src])
	c("không CURDATE / NOW / ký tự % trong SQL, không Batch.batch_qty / SED.amount",
		not re.search(r"CURDATE|NOW\(\)|batch_qty|sed\.amount|LIKE", src), re.findall(r"CURDATE|NOW\(\)|batch_qty|sed\.amount|LIKE", src))
	fn = next(x for x in ast.parse(src).body if isinstance(x, ast.FunctionDef) and x.name == "get_overview")
	first = fn.body[1] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body[0]
	c('dòng đầu get_overview là _guard("nhap-tp")', ast.unparse(first) == "_guard('nhap-tp')", ast.unparse(first))

	# ══ Tháng 9 ══
	d9 = run("2026-09")
	n9 = d9["nhap"]
	c("tháng 9 trọn tháng; 12 tháng 10/2025 → 09/2026", pick(d9["meta"], "from", "to", "prev") == {"from": "2026-09-01",
		"to": "2026-09-30", "prev": "2026-08"} and d9["meta"]["months"][0] == "2025-10" and len(n9["by_day"]) == 30, d9["meta"])
	c("tháng 9: 225 hộp (A 200, C 5, B 20), 1.400.000, 3 phiếu; C 5 chưa khai thùng", pick(n9["total"], "qty", "value", "slips",
		"items", "cartons", "boxes_without_carton_factor") == {"qty": 225, "value": 1_400_000, "slips": 3, "items": 3, "cartons": 12.0,
		"boxes_without_carton_factor": 5}, n9["total"])
	c("tháng 9: đối chiếu khớp, ngoài phiếu = chuyển từ Xưởng A 8", n9["doi_chieu"]["lech"] == 0
		and (n9["ngoai_phieu"]["qty"], n9["ngoai_phieu"]["entries"]) == (8, 1), (n9["doi_chieu"], n9["ngoai_phieu"]))
	b9 = {r["month"]: r for r in n9["by_month"]}
	c("10/2025: phiếu có ds_se hỏng — số lượng vẫn tính, giá trị 0, phiếu kho của nó thành 'ngoài phiếu'",
		pick(b9["2025-10"], "qty", "value", "so_kho_qty", "ngoai_phieu") == {"qty": 11, "value": 0, "so_kho_qty": 11, "ngoai_phieu": 11},
		b9["2025-10"])
	# 10/2025 (tháng cũ nhất của bảng tháng 9): A 11 / 20 = 0,55 → 0,6 (round 1 số lẻ), đủ hệ số · 26/09: C 5 → 0 thùng + 5 Hộp
	c("XR-COMP-2 (kỳ tháng 9): 10/2025 0,6 thùng, không phần chưa khai; ngày 26/09 0 thùng + 5 Hộp chưa khai",
		(pick(b9["2025-10"], *ck), pick({r["date"]: r for r in n9["by_day"]}["2026-09-26"], *ck)) == ({"cartons": 0.6,
		"boxes_without_carton_factor": 0, "items_without_carton_factor": 0, "uom_without": None}, {"cartons": 0,
		"boxes_without_carton_factor": 5, "items_without_carton_factor": 1, "uom_without": "Hộp"}), b9["2025-10"])
	c("tháng 9: nhập giá 0 = PN-12 B 20 + PN-15 C 5", (d9["gia_von_0"]["nhap_ky"]["qty"], d9["gia_von_0"]["nhap_ky"]["entries"])
		== (25, 2), d9["gia_von_0"]["nhap_ky"])
	c("hàng đợi / nợ / tồn giá 0 là ảnh chụp hôm nay — như tháng 10", d9["cho_duyet"] == q and d9["no_bom"] == b
		and d9["vao_hop"] == v and d9["gia_von_0"]["ton"] == tn)
	for bad in ("2026-11", "2026-13", "abc", "", None, "2026-1"):
		c(f"tháng không hợp lệ / tương lai ({bad!r}) → tháng này", run(bad)["meta"]["thang"] == "2026-10")

	# ══ SEC-1 · tháng cực đoan không bao giờ thành HTTP 500 ══
	# (a) Qua đường thật (kho.month_period kẹp từ 2000 và không quá 10 năm: mốc dưới hôm nay = 10/2016) → tháng này.
	for bad in ("0001-01", "0001-02", "0000-01", "1900-01", "1999-12", "2016-09", "9999-12"):
		try:
			got = run(bad)["meta"]["thang"]
		except Exception as e:  # noqa: BLE001 — chính lỗi cần bắt
			got = repr(e)
		c(f"SEC-1 tháng cực đoan {bad!r} → tháng này, không ném lỗi", got == "2026-10", got)
	# Mốc dưới vẫn giữ: 10/2016 → 12 tháng 11/2015 → 10/2016, tháng trước 09/2016, 31 ngày (cắt ở cuối tháng, không ở hôm nay)
	d16 = run("2016-10")
	c("SEC-1 mốc dưới 10/2016 giữ nguyên", (d16["meta"]["thang"], d16["meta"]["months"][0], len(d16["meta"]["months"]),
		d16["meta"]["prev"], len(d16["nhap"]["by_day"]), d16["nhap"]["total"]["qty"]) == ("2016-10", "2015-11", 12, "2016-09", 31, 0),
		d16["meta"])
	# (b) Chốt thứ hai TRONG kho_nhap: giả lập month_period để lọt tháng năm 1 / 12/9999 → dãy 12 tháng, tháng trước, từng ngày vẫn
	# dựng được (trước sửa: add_months(01/0001, −11) ném ValueError 'year 0'; bước 31/12/9999 + 1 ngày tràn OverflowError).
	# 01/0001: chỉ còn 1 tháng (không có tháng trước năm 1), tháng trước kẹp = 0001-01, 31 ngày · 02/0001: 0001-01, 0001-02,
	# 28 ngày · 12/9999: 9999-01 → 9999-12 (12 tháng), tháng trước 9999-11, 31 ngày. Không có phiếu nào → 0.
	from bc.api import kho as kho_mod
	orig_mp = kho_mod.month_period
	try:
		for f_, t_, lbl, want in (
				(datetime.date(1, 1, 1), datetime.date(1, 1, 31), "0001-01", (["0001-01"], "0001-01", 31, 0)),
				(datetime.date(1, 2, 1), datetime.date(1, 2, 28), "0001-02", (["0001-01", "0001-02"], "0001-01", 28, 0)),
				(datetime.date(9999, 12, 1), datetime.date(9999, 12, 31), "9999-12",
					([f"9999-{m_:02d}" for m_ in range(1, 13)], "9999-11", 31, 0))):
			kho_mod.month_period = lambda thang=None, _r=(f_, t_, lbl): _r
			try:
				dx = run(lbl)
				got = (dx["meta"]["months"], dx["meta"]["prev"], len(dx["nhap"]["by_day"]), dx["nhap"]["total"]["qty"])
			except Exception as e:  # noqa: BLE001
				got = repr(e)
			c(f"SEC-1 kho_nhap tự chốt khi kỳ lọt {lbl}: không add_months / không tràn ngày", got == want, got)
	finally:
		kho_mod.month_period = orig_mp

	# ══ Quyền / ẩn mảng ══
	frappe.session.user = "nobody@example.com"
	try:
		kho_nhap.get_overview(refresh=1)
		c("người không có quyền bị chặn", False)
	except frappe.PermissionError:
		c("người không có quyền bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="nhap-tp")
	try:
		kho_nhap.get_overview(refresh=1)
		c("mảng nhap-tp đang ẩn → người xem bị chặn", False)
	except frappe.PermissionError:
		c("mảng nhap-tp đang ẩn → người xem bị chặn", True)
	frappe.session.user = "Administrator"
	try:
		c("mảng ẩn: quản trị vẫn xem được", run()["nhap"]["total"]["qty"] == 358)
	finally:
		frappe.session.user = "viewer@example.com"
		single("BC Settings", hidden_sections="")

	# ══ Lẫn đơn vị — KHÔNG bao giờ cộng Hộp với Kg; kiểm đơn vị RIÊNG từng ô (ngày, tháng, vế sổ, ngoài phiếu, đối chiếu) ══
	# (A) Chỉ vế SỔ có kg: nhập tay Kg vào Kho TP 09/10 (2,5) + 05/08 (1,5); mọi phiếu vẫn là hộp.
	mixed_ledger(k)
	dl = run()
	nl = dl["nhap"]
	bl = {x["month"]: x for x in nl["by_month"]}
	# T10: phiếu 358 hộp (không đổi) · sổ 323 hộp + 2,5 kg → None (KHÔNG phải 325,5) · ngoài phiếu A 12 + C 7 + B 6 hộp + 2,5 kg
	#   → None, 3 + 1 = 4 phiếu kho · chênh None
	c("lẫn đơn vị vế sổ (T10): sổ kho / ngoài phiếu / chênh None, phiếu vẫn 358 hộp, 4 phiếu kho ngoài phiếu",
		pick(bl["2026-10"], "qty", "uom", "so_kho_qty", "so_kho_uom", "chenh", "ngoai_phieu", "ngoai_uom", "ngoai_entries") == {
		"qty": 358, "uom": "Hộp", "so_kho_qty": None, "so_kho_uom": None, "chenh": None, "ngoai_phieu": None, "ngoai_uom": None,
		"ngoai_entries": 4}, bl["2026-10"])
	# T8: không phiếu; sổ chỉ 1,5 kg → có số, kèm đơn vị Kg; chênh 1,5 − 0 = 1,5
	c("tháng chỉ có kg (T8): sổ kho 1,5 Kg, ngoài phiếu 1,5 Kg, chênh 1,5", pick(bl["2026-08"], "qty", "uom", "so_kho_qty",
		"so_kho_uom", "chenh", "ngoai_phieu", "ngoai_uom", "ngoai_entries") == {"qty": 0, "uom": None, "so_kho_qty": 1.5,
		"so_kho_uom": "Kg", "chenh": 1.5, "ngoai_phieu": 1.5, "ngoai_uom": "Kg", "ngoai_entries": 1}, bl["2026-08"])
	c("lẫn đơn vị vế sổ: tháng chỉ hộp (T9) giữ nguyên 233 / chênh 8", pick(bl["2026-09"], "so_kho_qty", "so_kho_uom", "chenh",
		"ngoai_phieu") == {"so_kho_qty": 233, "so_kho_uom": "Hộp", "chenh": 8, "ngoai_phieu": 8}, bl["2026-09"])
	c("lẫn đơn vị vế sổ: tổng ngoài phiếu tháng None, 4 phiếu kho, danh sách A 12 / C 7 / B 6 / Kg 2,5; tổng phiếu và đối chiếu "
		"không đổi", (nl["ngoai_phieu"]["qty"], nl["ngoai_phieu"]["uom"], nl["ngoai_phieu"]["entries"], [(x["item_code"], x["qty"])
		for x in nl["ngoai_phieu"]["items"]], nl["total"]["qty"], nl["doi_chieu"]["slip_qty"], nl["doi_chieu"]["slips_lech"]) == (
		None, None, 4, [(A, 12), (C, 7), (B, 6), (KG, 2.5)], 358, 358, 1), nl["ngoai_phieu"])

	# (B) Thêm vế PHIẾU kg: phiếu đã duyệt 21/10 Kg 4,5 (chưa có phiếu kho) + nợ BOM Kg 2; phiếu 22/10 Kg 3 có phiếu kho.
	mixed_slip(k)
	dm = run()
	tm, bm2 = dm["nhap"]["total"], dm["no_bom"]
	c("lẫn Hộp + Kg: tổng số lượng None, tách theo đơn vị; thùng giữ nguyên; phần chưa khai thùng lẫn đơn vị → None",
		pick(tm, "qty", "uom", "by_uom", "cartons", "items_without_carton_factor", "boxes_without_carton_factor", "slips") == {
		"qty": None, "uom": None, "by_uom": [{"uom": "Hộp", "qty": 358}, {"uom": "Kg", "qty": 7.5}], "cartons": 19.9,
		"items_without_carton_factor": 2, "boxes_without_carton_factor": None, "slips": 8}, tm)
	# Có BOM: chỉ hộp → 138; nhập tạm: 160 hộp + 3 kg (SE-52) → None, giá trị 850.000 + 3.000 vẫn cộng
	c("lẫn đơn vị: có BOM giữ 138 hộp; nhập tạm lẫn Hộp + Kg → None, giá trị vẫn cộng", tm["by_kind"] == {
		"bom": {"qty": 138, "uom": "Hộp", "value": 966_000}, "tam": {"qty": None, "uom": None, "value": 853_000}}, tm["by_kind"])
	dd = {x["date"]: x for x in dm["nhap"]["by_day"]}
	c("lẫn đơn vị theo NGÀY: mỗi ngày tự kiểm — 21/10 4,5 Kg, 22/10 3 Kg, 05/10 178 hộp, 20/10 64 hộp", [(dd[x]["qty"],
		dd[x]["uom"]) for x in ("2026-10-21", "2026-10-22", "2026-10-05", "2026-10-20")] == [(4.5, "Kg"), (3, "Kg"), (178, "Hộp"),
		(64, "Hộp")]
		and dd["2026-10-21"]["slips"] == 1, [dd[x] for x in ("2026-10-21", "2026-10-05")])
	b2 = {x["month"]: x for x in dm["nhap"]["by_month"]}
	c("lẫn đơn vị theo THÁNG: chỉ T10 thành None; T9 (chỉ hộp) giữ 225 / 233 / 8; T8 giữ 1,5 Kg",
		pick(b2["2026-10"], "qty", "uom", "cartons", "so_kho_qty", "chenh", "ngoai_phieu", "ngoai_entries") == {"qty": None,
		"uom": None, "cartons": 19.9, "so_kho_qty": None, "chenh": None, "ngoai_phieu": None, "ngoai_entries": 4}
		and pick(b2["2026-09"], "qty", "uom", "so_kho_qty", "chenh", "ngoai_phieu", "ngoai_entries") == {"qty": 225, "uom": "Hộp",
		"so_kho_qty": 233, "chenh": 8, "ngoai_phieu": 8, "ngoai_entries": 1}
		and (b2["2026-08"]["so_kho_qty"], b2["2026-08"]["so_kho_uom"]) == (1.5, "Kg"), (b2["2026-10"], b2["2026-09"]))
	# Đối chiếu (phiếu, mã): vế phiếu 358 hộp + Kg 4,5 + 3 → None; vế sổ 298 hộp + Kg 3 (SE-52) → None; lệch (PN-05, A) 60 hộp +
	#   (PN-30, Kg) 4,5 kg → None; PN-31 khớp → 2 phiếu lệch (KHÔNG phải 365,5 / 301 / 64,5)
	# XR-COMP-2 lẫn đơn vị: T10 phần chưa khai = C 30 Hộp + Kg 4,5 + 3 → lẫn đơn vị → None (KHÔNG 37,5), 2 mã; thùng 19,9 giữ ·
	#   ngày 21/10: Kg 4,5 → 0 thùng + 4,5 Kg (1 mã) · 22/10: Kg 3 → 3 Kg
	c("XR-COMP-2 lẫn đơn vị: ô tháng 10 phần chưa khai None / 2 mã; ngày 21/10 4,5 Kg, 22/10 3 Kg",
		(pick(b2["2026-10"], *ck), pick(dd["2026-10-21"], *ck), pick(dd["2026-10-22"], *ck)) == ({"cartons": 19.9,
		"boxes_without_carton_factor": None, "items_without_carton_factor": 2, "uom_without": None}, {"cartons": 0,
		"boxes_without_carton_factor": 4.5, "items_without_carton_factor": 1, "uom_without": "Kg"}, {"cartons": 0,
		"boxes_without_carton_factor": 3, "items_without_carton_factor": 1, "uom_without": "Kg"}), pick(b2["2026-10"], *ck))
	c("lẫn đơn vị: đối chiếu không cộng Hộp + Kg, vẫn đếm 2 phiếu lệch", dm["nhap"]["doi_chieu"] == {"slip_qty": None,
		"slip_uom": None, "se_qty": None, "se_uom": None, "lech": None, "lech_uom": None, "slips_lech": 2}, dm["nhap"]["doi_chieu"])
	c("lẫn đơn vị: nợ BOM — số lượng / tuổi nợ None, giá trị vẫn cộng (958.000 + 2.000), xử lý ngay A + D = 80 hộp",
		(bm2["qty"], bm2["uom"], bm2["qty_gia_0"], bm2["value_tam"], bm2["rows"], [x["qty"] for x in bm2["buckets"]],
		bm2["xu_ly_ngay"]) == (None, None, None, 960_000, 9, [None, None, None], {"items": 2, "qty": 80}), bm2)
	unmixed()
	c("dọn ca lẫn đơn vị: về số gốc", run()["nhap"]["by_month"][-1]["so_kho_qty"] == 323)

	# ══ Thiếu cột nguon (sx trước D122): không có phiếu Tết, không trừ nháp Tết ══
	drop_column("SX Phieu Nhap TP", "nguon")
	d2 = run()
	c("thiếu cột nguon: hàng đợi vẫn đủ 4 phiếu, 0 phiếu Tết", (d2["cho_duyet"]["count"], d2["cho_duyet"]["count_tet"]) == (4, 0),
		d2["cho_duyet"])
	c("thiếu cột nguon: C vào hộp còn 60 − 30 = 30", by(d2["vao_hop"]["rows"], "item_code", C)["qty"] == 30, d2["vao_hop"]["rows"])
	# ══ Thiếu custom_sx_nhom: mọi nguyên liệu rút Kho NVL (NL1 @NVL 40.000 → 440.000; NL4 @NVL 'bin') ══
	drop_column("Item", "custom_sx_nhom")
	r3 = run()["nvl_treo"]
	c("thiếu custom_sx_nhom: nguyên liệu rút Kho NVL", r3["value"] == 768_000 and by(r3["list"], "item_code", NL1)["rate"] == 40_000
		and by(r3["list"], "item_code", NL4)["rate_source"] == "bin", (r3["value"], r3["list"][:2]))
	# ══ Thiếu bảng: chỉ khối đó tắt; một khối lỗi không làm hỏng trang ══
	drop_doctype("SX No BOM")
	d4 = run()
	c("thiếu bảng SX No BOM: nợ BOM + NVL treo tắt, nhập kho vẫn có", d4["no_bom"] == {"available": False}
		and d4["nvl_treo"] == {"available": False} and d4["nhap"]["total"]["qty"] == 358, (d4["no_bom"], d4["nvl_treo"]))
	drop_doctype("SX Bang Vao Hop")
	d5 = run()
	c("thiếu bảng vào hộp: chỉ khối vào hộp tắt", d5["vao_hop"] == {"available": False} and d5["cho_duyet"]["count"] == 4)
	drop_column("SX Phieu Nhap TP Item", "so_lap")
	d6 = run()
	c("một khối lỗi (thiếu cột so_lap) → {available: False, error: True}, khối khác vẫn có",
		d6["cho_duyet"] == {"available": False, "error": True} and d6["nhap"]["available"] and d6["gia_von_0"]["available"],
		d6["cho_duyet"])

	# ══ Site không cài sx ══
	full(sx=False)
	for dt in SX_DOCTYPES:
		drop_doctype(dt)
	frappe.INSTALLED_APPS.remove("sx")
	try:
		d7 = run()
		c("không có sx: các khối sx tắt, trang vẫn trả", d7["available"] and d7["meta"]["sx"] is False and all(
			d7[x] == {"available": False} for x in ("nhap", "cho_duyet", "vao_hop", "no_bom", "nvl_treo")), pick(d7, "nhap", "no_bom"))
		g7 = d7["gia_von_0"]
		# Không SX Settings → không biết kho trả về / cách ly → hai kho đó thành "bán được": thêm A@trả về 9 + Z@cách ly 4 → 83;
		# tập TP theo cây nhóm (Tết ∪ truyền thống) — cùng các mã. Nhập giá 0: + SE-26 A 9 (trả về) = 51.
		c("không có sx: tồn giá 0 vẫn tính (tập TP theo nhóm hàng)", (g7["available"], g7["tp_source"], g7["ton"]["rows"],
			g7["ton"]["qty"], g7["nhap_ky"]["qty"], g7["nhap_ky"]["entries"]) == (True, "nhom", 8, 83, 51, 4),
			(g7.get("tp_source"), g7.get("ton", {}).get("qty"), g7.get("nhap_ky")))
	finally:
		frappe.INSTALLED_APPS.append("sx")

	# ══ Sổ trống ══
	reset()
	bc_settings()
	k0 = K()
	base(k0)
	k0.finalize()
	d8 = run()
	c("sổ trống: mọi khối có, số 0, danh sách rỗng", d8["nhap"]["total"]["qty"] == 0 and d8["nhap"]["total"]["value"] == 0
		and d8["nhap"]["total"]["uom"] is None and len(d8["nhap"]["by_day"]) == 27 and d8["nhap"]["top_items"] == []
		and d8["cho_duyet"]["count"] == 0 and d8["cho_duyet"]["oldest_age_days"] is None and d8["vao_hop"]["rows"] == []
		and d8["no_bom"]["qty"] == 0 and d8["no_bom"]["oldest"] is None and d8["nvl_treo"]["value"] == 0
		and d8["gia_von_0"]["ton"]["rows"] == 0 and d8["gia_von_0"]["nhap_ky"]["qty"] == 0,
		pick(d8, "nhap", "cho_duyet"))
	c.done()
