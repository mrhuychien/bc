"""Tồn kho (bc.api.kho_ton: K1 giá trị, K2 xu hướng, K3 nhập–xuất–tồn, K4 số ngày tồn, K5 hàng chậm, sức khoẻ §6) trên
MariaDB thật, bảng sinh từ DocType JSON v16.

Số kỳ vọng TÍNH TAY từ sổ dưới đây (hôm nay 27/10/2026, W = 90 → cửa sổ 30/07–27/10, chậm > 90, chết > 180 ngày).
Mỗi bẫy của đặc tả có một ca: nhóm con "Hộp quà Tết" (cây, không '='), mã ngừng dùng + kho ngừng dùng còn hàng, kho công ty
khác, kho đi đường / trả về / cách ly, dòng Bin âm, dòng chỉ còn giá trị, phiếu ghi ngày tương lai, phiếu huỷ (sổ + bán),
kiểm kê không lô (actual_qty = 0), trả hàng POS có sổ (không phải lần bán), phiếu giảm giá trả hàng update_stock = 0 (không
sổ, W2) + phiếu nhập trả lại, chuyển kho (không phải xuất), xuất huỷ, kiểm kê sx (custom_kiem_ke), dọn tồn sx, nhập tạm,
xuất NVL bù nợ BOM (W8), biên 30 / 90 / 180 ngày và biên cửa sổ DOI, giai đoạn Tết (không dùng sx_season), Thùng chưa khai.
Bẫy K5 thêm sau review: TP chỉ sản xuất (dòng NHẬN của Manufacture không phải "dùng"), mã chỉ có kiểm kê đầu kỳ (T1: SR
actual_qty 0 vẫn là lần nhập đầu), mã chỉ còn giá trị (tồn bán được = 0 → ngoài phạm vi), "Hạch toán bù nợ BOM" phải ở ĐẦU
diễn giải và là phiếu xuất NVL (Material Issue); phiếu ghi đúng HÔM NAY (điểm hôm nay gồm, future_value không), dòng sổ
công ty khác trong cửa sổ DOI / ghi ngày tương lai / là lần bán cuối, hàng Tết nằm kho trả về (không vào tồn hàng Tết).
Review chéo lần 2: "chưa khai quy cách thùng" một cơ sở cho thẻ thành phẩm và dải sức khoẻ (mã tồn âm không kéo số xuống,
XC-5 / UX-9), theo từng đơn vị — không cộng Hộp / Gói / Kg, bỏ đơn vị không đóng thùng (NUM-1 / XR-COMP-1); tính lại giá vốn
LỖI (Failed, XR-REAL-3); BC Settings kho_doi_days / kho_slow_days / kho_dead_days dùng thật + 0 / trống → mặc định
(XR-COMP-4); giá vốn bán đi từ sổ với chỉ mục thật v16 (EXPLAIN) và ba lượt quét cả lịch sử cache theo ngày, Làm mới tính
lại, mã mới vào phạm vi tính ngay (PERF-1); nhãn theo kho (UX-3), nhãn kiểm kê (UX-1), kho trả về chưa khai (UX-11c).
Review lần 3: đơn vị "đóng thùng" MỘT luật cho thẻ / nhóm hàng / tồn Tết và dải sức khoẻ — khối chỉ có Kg (không mã
thành phẩm Kg nào khai thùng) không hiện "0 thùng + … chưa khai" khi Hộp có thùng ở nơi khác (XR-COMP-1 / NUM-1 còn lại).

Chạy: BC_TEST_DB=bc_test_kho_ton python3 -B test_kho_ton.py
seed(k) chỉ THÊM dữ liệu tên TON-… lên base(k) (để gộp seed cho kiểm giao diện): reset(); bc_settings(); k = K(); base(k);
seed(k); k.finalize().
"""
import json
import os
import re

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset, single
from paths import BC_ROOT
from seed_kho import (BTP, CACH_LY, CH1, CH2, DI_DUONG, G_BB, G_NL, G_QUA_TET, G_TET, G_TRAD, KHO_CU, NVL, RV, TP, TRA_VE,
	XUONG, K, base)

import frappe  # noqa: E402

PRIVATE = ["thukho.bimat@hgc.vn", "Trần Thị Kho Bí Mật", "Khách Kho Bí Mật", "GHI CHÚ RIÊNG KHO", "posvien.bimat@hgc.vn"]
G_GUI = "TON-Hàng gửi bán"   # nhóm riêng ngoài cây Tết / truyền thống (mã TP "lạc nhóm" → tp_set_mismatch)


def seed(k: K):
	"""Kịch bản Tồn kho (mọi tên bắt đầu TON-). Giá trị = số lượng × đơn giá cố định mỗi mã (ghi rõ ở từng dòng)."""
	# ── Mã hàng ── TP đánh dấu custom_sx_nhom = 'TP' (sx.utils.items_tp, SX Settings không khai nhóm TP).
	k.group(G_GUI, "Tất cả nhóm hàng")
	k.item("TON-TET1", "Bánh Tết TON A", G_TET, carton=20, custom_sx_nhom="TP")          # 50.000 / hộp
	k.item("TON-QUA1", "Hộp quà TON", G_QUA_TET, carton=10, custom_sx_nhom="TP")         # 100.000 — nhóm CON của Hàng Tết
	k.item("TON-TRAD1", "Bánh đậu xanh TON 1", G_TRAD, carton=24, custom_sx_nhom="TP")   # 20.000
	k.item("TON-TRAD2", "Bánh TON 2", G_TRAD, custom_sx_nhom="TP")                       # 10.000 — CHƯA khai thùng
	k.item("TON-TRAD3", "Bánh TON ngừng", G_TRAD, carton=12, disabled=1, custom_sx_nhom="TP")  # 15.000 — mã ngừng dùng
	k.item("TON-TRAD4", "Bánh TON chưa đánh dấu", G_TRAD)                                # trong cây truyền thống, không 'TP'
	k.item("TON-TPK", "TP gửi bán TON", G_GUI, carton=6, custom_sx_nhom="TP")            # 30.000 — TP ngoài cây nhóm
	k.item("TON-NL1", "Đậu xanh TON", G_NL, uom="Kg", custom_sx_nhom="NVL")              # 40.000 / kg
	k.item("TON-NL2", "Đường TON", G_NL, uom="Kg", custom_sx_nhom="NVL")                 # 20.000
	k.item("TON-NL3", "Dầu TON", G_NL, uom="Kg", custom_sx_nhom="NVL")                   # 50.000 — bị ẩn khỏi danh sách
	k.item("TON-BB1", "Hộp giấy TON", G_BB, uom="Cái", custom_sx_nhom="Bao Bi")          # 2.000
	k.item("TON-BTP1", "Bột TON", G_NL, uom="Kg", custom_sx_nhom="BTP-Bot")              # 80.000 (60.000 ở xưởng)
	k.item("TON-DV1", "Dịch vụ TON", G_NL, uom="Lần")
	k.item("TON-FG1", "Bánh TON chỉ sản xuất", G_TRAD, carton=10, custom_sx_nhom="TP")   # 10.000 — sản xuất 2 lần, chưa bán
	k.item("TON-RM1", "Bột nếp TON", G_NL, uom="Kg", custom_sx_nhom="NVL")               # 10.000 / kg — NVL của FG1
	k.item("TON-SR1", "Mè TON", G_NL, uom="Kg", custom_sx_nhom="NVL")                    # 10.000 — chỉ có kiểm kê đầu kỳ
	k.item("TON-NL4", "Muối TON", G_NL, uom="Kg", custom_sx_nhom="NVL")                  # chỉ còn giá trị 5.000 (0 kg)
	k.item("TON-TET2", "Bánh Tết TON trả về", G_TET, carton=10, custom_sx_nhom="TP")     # 100.000 — chỉ nằm kho trả về
	frappe.db.sql("UPDATE `tabItem` SET is_stock_item = 0 WHERE name = 'TON-DV1'")
	insert("BC Hidden Item", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items", idx=1,
		item_code="TON-NL3")
	se_priv = {"owner": PRIVATE[0]}

	# ── Trước cửa sổ 12 tháng (≤ 30/09/2025): 8.150.000 = truyền thống 3.150.000 + khác 5.000.000 ──
	k.receipt("TON-TRAD3", KHO_CU, 10, 150_000, "2025-07-01", name="TON-PR-00")        # kho ngừng dùng còn hàng
	k.receipt("TON-TRAD3", TP, 200, 3_000_000, "2025-08-15", name="TON-PR-01")
	k.receipt("TON-NL3", NVL, 100, 5_000_000, "2025-09-10", name="TON-PR-02")
	# ── 10/2025: tồn đầu 50 tr (kiểm kê Opening Stock 10 tr + phiếu nhập is_opening 40 tr), mua 50 tr, bán −5 tr ──
	k.recon("2025-10-01", [dict(item_code="TON-TRAD1", warehouse=TP, qty=500, current_qty=0, value_diff=10_000_000,
		rate=20_000)], purpose="Opening Stock", name="TON-SR-OPEN")                       # không lô → actual_qty 0
	k.se("Material Receipt", "2025-10-01", [dict(item_code="TON-NL1", t_warehouse=NVL, qty=1000, rate=40_000)],
		is_opening="Yes", name="TON-SE-OPEN")
	k.recon("2025-10-01", [dict(item_code="TON-SR1", warehouse=NVL, qty=50, current_qty=0, value_diff=500_000,
		rate=10_000)], purpose="Opening Stock", name="TON-SR-OPEN2")                      # SR1: dòng sổ DUY NHẤT, actual_qty 0
	k.receipt("TON-TET1", TP, 1000, 50_000_000, "2025-10-05", name="TON-PR-03")
	k.se("Material Transfer", "2025-10-10", [dict(item_code="TON-TET1", s_warehouse=TP, t_warehouse=CH1, qty=200,
		rate=50_000)], name="TON-SE-TR1")
	k.sale("TON-TET1", CH1, 100, 5_000_000, "2025-10-25", name="TON-SI-01")
	k.sale("TON-TET1", TP, 400, 20_000_000, "2025-11-10", voucher_type="Delivery Note", name="TON-DN-01")   # 11: −20 tr
	k.receipt("TON-NL2", NVL, 500, 10_000_000, "2025-12-01", name="TON-PR-04")                               # 12: +10 tr
	k.sale("TON-TET1", TP, 300, 15_000_000, "2026-01-15", name="TON-SI-02")                                  # 01: −15 tr
	k.receipt("TON-RM1", NVL, 100, 1_000_000, "2026-02-20", name="TON-PR-09")                                # 02: +1 tr
	k.se("Manufacture", "2026-03-01", [dict(item_code="TON-RM1", s_warehouse=NVL, qty=10, rate=10_000),
		dict(item_code="TON-FG1", t_warehouse=TP, qty=10, rate=10_000, is_finished_item=1)], name="TON-SE-MFG2")  # 03: ròng 0
	k.receipt("TON-QUA1", TP, 100, 10_000_000, "2026-03-10", name="TON-PR-05")                               # 03: +10 tr
	k.receipt("TON-TPK", TP, 50, 1_500_000, "2026-04-10", name="TON-PR-06")                                  # 04: +1,5 tr
	k.sale("TON-TPK", TP, 10, 300_000, "2026-04-30", name="TON-SI-03")                                       # 04: −0,3 tr; đúng 180 ngày
	k.receipt("TON-NL4", NVL, 10, 100_000, "2026-05-01", name="TON-PR-10")                                   # 05: +0,1 tr
	k.receipt("TON-TRAD2", TP, 300, 3_000_000, "2026-05-20", name="TON-PR-07")                               # 05: +3 tr
	k.receipt("TON-BB1", NVL, 1000, 2_000_000, "2026-06-01", name="TON-PR-08")                               # 06: +2 tr
	k.se("Material Issue", "2026-06-01", [dict(item_code="TON-NL4", s_warehouse=NVL, qty=10, rate=10_000, value_out=95_000)],
		entry_type="Xuất huỷ", name="TON-SE-HUY2")                                          # 06: −95k; NL4 còn 0 kg / 5.000 đ
	# ── 07/2026: sản xuất (nội bộ, ròng 0), bán −1,2 tr ──
	k.se("Manufacture", "2026-07-28", [dict(item_code="TON-NL1", s_warehouse=NVL, qty=100, rate=40_000),
		dict(item_code="TON-BTP1", t_warehouse=BTP, qty=50, rate=80_000, is_finished_item=1)], name="TON-SE-MFG1")  # NL1: 91 ngày
	k.sale("TON-TRAD2", TP, 20, 200_000, "2026-07-29", name="TON-SI-04")      # ngoài cửa sổ DOI; TRAD2 đúng 90 ngày
	k.sale("TON-TRAD1", TP, 50, 1_000_000, "2026-07-30", name="TON-SI-05")    # ngày ĐẦU cửa sổ DOI
	# ── 08/2026: nhập tạm +2 tr, chuyển cửa hàng ──
	k.se("Material Receipt", "2026-08-05", [dict(item_code="TON-TRAD1", t_warehouse=TP, qty=100, rate=20_000)],
		remarks="Nhập tạm — TON phiếu 1", name="TON-SE-TAM1")
	k.se("Material Transfer", "2026-08-20", [dict(item_code="TON-TRAD1", s_warehouse=TP, t_warehouse=CH2, qty=100,
		rate=20_000)], name="TON-SE-TR2")
	# ── 09/2026: xuất huỷ −1 tr, kiểm kê sx +50k, dọn tồn sx −40k, kiểm kê cửa hàng −100k, Repack, phiếu huỷ, điều chỉnh +5k ──
	k.se("Material Issue", "2026-09-01", [dict(item_code="TON-NL3", s_warehouse=NVL, qty=20, rate=50_000)],
		entry_type="Xuất huỷ", remarks="Huỷ dầu hỏng, không phải Hạch toán bù nợ BOM — GHI CHÚ RIÊNG KHO", name="TON-SE-HUY1",
		**se_priv)                                          # cụm "Hạch toán bù nợ BOM" KHÔNG ở đầu → vẫn là xuất huỷ, không phải dùng
	k.se("Material Receipt", "2026-09-15", [dict(item_code="TON-TRAD2", t_warehouse=TP, qty=5, rate=10_000)],
		kiem_ke="TON-KK-01", name="TON-SE-KK1")
	k.se("Material Issue", "2026-09-20", [dict(item_code="TON-TRAD1", s_warehouse=TP, qty=2, rate=20_000)],
		remarks="Dọn tồn âm thành phẩm TON", name="TON-SE-DON1")
	k.recon("2026-09-25", [dict(item_code="TON-TRAD1", warehouse=CH2, qty=95, current_qty=100, value_diff=-100_000,
		rate=20_000)], name="TON-SR-CH2")
	k.se("Repack", "2026-09-27", [dict(item_code="TON-BTP1", s_warehouse=BTP, qty=10, rate=80_000),
		dict(item_code="TON-TRAD1", t_warehouse=TP, qty=40, rate=20_000)], name="TON-SE-RPK1")       # BTP1 dùng: 30 ngày
	k.se("Material Receipt", "2026-09-28", [dict(item_code="TON-TRAD1", t_warehouse=TP, qty=1000, rate=20_000)],
		docstatus=2, name="TON-SE-HUYPHIEU")                                                        # phiếu huỷ: +20 tr nếu lọt
	k.recon("2026-09-30", [dict(item_code="TON-NL2", warehouse=NVL, qty=500, current_qty=500, value_diff=5_000,
		rate=20_010)], purpose="Adjustment Entry", name="TON-SR-ADJ")
	# ── 10/2026 (tới 27/10) ──
	k.sale("TON-TPK", TP, 30, 900_000, "2026-10-01", name="TON-SI-X1", cancelled=1)      # bán đã huỷ
	k.sale("TON-TRAD1", TP, 100, 2_000_000, "2026-10-02", name="TON-SI-X2", cancelled=1)  # bán đã huỷ (trong cửa sổ DOI)
	k.se("Material Receipt", "2026-10-02", [dict(item_code="TON-BTP1", t_warehouse=XUONG, qty=10, rate=60_000)],
		name="TON-SE-XN1")                                                                  # nhap_khac +600k
	k.se("Material Issue", "2026-10-03", [dict(item_code="TON-BTP1", s_warehouse=XUONG, qty=10, rate=60_000,
		value_out=590_000)], entry_type="Xuất mẫu", name="TON-SE-XM1")                       # còn 0 cái / 10.000 đ
	k.receipt("TON-TET2", TRA_VE, 10, 1_000_000, "2026-10-01", name="TON-PR-11")               # hàng Tết chỉ ở kho trả về
	k.sale("TON-TET1", CH1, 50, 2_500_000, "2026-10-05", name="TON-SI-06")
	k.se("Material Transfer", "2026-10-05", [dict(item_code="TON-NL3", s_warehouse=NVL, t_warehouse=XUONG, qty=10,
		rate=50_000)], remarks="Hạch toán bù nợ BOM — chuyển kho nhầm loại phiếu TON", name="TON-SE-TR6")  # không phải Material Issue
	k.sle("TON-BB1", NVL, 100, 200_000, "2026-10-08", "Subcontracting Receipt", "TON-SCR-01")      # loại chứng từ khác → khac
	k.receipt("TON-NL1", NVL, 200, 8_000_000, "2026-10-09", voucher_type="Purchase Invoice", name="TON-PI-01")
	k.se("Material Issue", "2026-10-10", [dict(item_code="TON-NL2", s_warehouse=NVL, qty=100, rate=20_000)],
		remarks="Hạch toán bù nợ BOM TON-NB-01 — Trần Thị Kho Bí Mật", name="TON-SE-BOM1", **se_priv)  # W8: NL2 17 ngày
	k.se("Material Receipt", "2026-10-12", [dict(item_code="TON-TPK", t_warehouse=TP, qty=20, rate=30_000)],
		remarks="Nhập tạm — TON phiếu 2", name="TON-SE-TAM2")
	k.se("Repack", "2026-10-15", [dict(item_code="TON-BB1", s_warehouse=NVL, qty=50, rate=2_000),
		dict(item_code="TON-BB1", t_warehouse=NVL, qty=50, rate=2_000)], kiem_ke="TON-KK-02", name="TON-SE-KK2")
	k.se("Material Transfer", "2026-10-15", [dict(item_code="TON-NL1", s_warehouse=NVL, t_warehouse=XUONG, qty=300,
		rate=40_000)], name="TON-SE-TR3")
	k.se("Repack", "2026-10-16", [dict(item_code="TON-BB1", s_warehouse=NVL, qty=10, rate=2_000),
		dict(item_code="TON-BB1", t_warehouse=NVL, qty=10, rate=2_000)], remarks="Dọn tồn không lô sau bật lô TON",
		name="TON-SE-DON2")
	k.sale("TON-TRAD1", CH2, 30, 600_000, "2026-10-20", name="TON-SI-07")
	k.sale("TON-TRAD2", TRA_VE, -3, -30_000, "2026-10-20", name="TON-SI-RET1", is_return=1)  # trả POS có sổ (vào kho trả về)
	insert("Sales Invoice", name="TON-SI-CN1", docstatus=1, posting_date="2026-10-22", company="HGC", is_return=1,
		update_stock=0, customer_name=PRIVATE[2], net_total=-100_000)                         # W2: không sổ kho
	insert("Sales Invoice Item", parent="TON-SI-CN1", parenttype="Sales Invoice", parentfield="items", idx=1,
		item_code="TON-TRAD1", qty=-5, stock_qty=-5, delivered_qty=0)
	k.se("Material Receipt", "2026-10-23", [dict(item_code="TON-TRAD1", t_warehouse=TRA_VE, qty=5, rate=20_000)],
		name="TON-SE-NHAPTV")                                                                 # hàng trả nhập lại (nhap_khac)
	k.se("Material Issue", "2026-10-25", [dict(item_code="TON-TRAD1", s_warehouse=TP, qty=5, rate=20_000)],
		entry_type="Xuất mẫu", name="TON-SE-MAU1")
	k.sale("TON-TRAD1", TP, 20, 400_000, "2026-10-26", voucher_type="Delivery Note", name="TON-DN-02")
	k.se("Material Transfer", "2026-10-26", [dict(item_code="TON-TRAD1", s_warehouse=TP, t_warehouse=DI_DUONG, qty=10,
		rate=20_000)], name="TON-SE-TR4")
	k.se("Material Transfer", "2026-10-26", [dict(item_code="TON-TPK", s_warehouse=TP, t_warehouse=CACH_LY, qty=5,
		rate=30_000)], name="TON-SE-TR5")
	k.sale("TON-TRAD1", CH1, 4, 80_000, "2026-10-26", name="TON-SI-08")                    # bán khi chưa có hàng → Bin âm
	k.receipt("TON-RM1", NVL, 5, 50_000, "2026-10-27", name="TON-PR-12")                     # ghi đúng HÔM NAY
	k.se("Manufacture", "2026-10-27", [dict(item_code="TON-RM1", s_warehouse=NVL, qty=10, rate=10_000),
		dict(item_code="TON-FG1", t_warehouse=TP, qty=10, rate=10_000, is_finished_item=1)], name="TON-SE-MFG3")  # HÔM NAY
	k.receipt("TON-TET1", TP, 10, 500_000, "2026-10-30", name="TON-PR-FUT1")                 # tương lai TRONG tháng này
	k.receipt("TON-QUA1", TP, 20, 2_000_000, "2026-11-05", name="TON-PR-FUT")                # ghi ngày tương lai (tháng sau)
	rv = k.sle("TON-TRAD1", RV, 100, 1_000_000, "2026-10-01", "Purchase Receipt", "TON-PR-RV")
	frappe.db.sql("UPDATE `tabStock Ledger Entry` SET company = 'RV' WHERE name = %s", (rv,))  # công ty khác
	# Công ty khác: bán TRAD3 (HGC chưa từng bán) TRONG cửa sổ DOI + nhập ghi ngày tương lai — không được vào giá vốn, lần
	# bán cuối, sổ / tương lai của HGC.
	k.sale("TON-TRAD3", RV, 5, 75_000, "2026-10-10", name="TON-SI-RV1")
	frappe.db.sql("UPDATE `tabStock Ledger Entry` SET company = 'RV' WHERE voucher_no = 'TON-SI-RV1'")
	frappe.db.sql("UPDATE `tabSales Invoice` SET company = 'RV' WHERE name = 'TON-SI-RV1'")
	rvf = k.sle("TON-QUA1", RV, 10, 1_000_000, "2026-11-20", "Purchase Receipt", "TON-PR-RVFUT")
	frappe.db.sql("UPDATE `tabStock Ledger Entry` SET company = 'RV' WHERE name = %s", (rvf,))

	# ── Sức khoẻ số liệu ──
	single("Stock Settings", allow_negative_stock=1, allow_negative_stock_for_batch=0)
	# Failed: bộ lập lịch v16 không chạy lại (chỉ Queued / In Progress) → mục riêng; nháp / huỷ / công ty khác không tính.
	for n, ds, st, d, co in [("TON-RIV-1", 1, "Queued", "2026-10-26", "HGC"), ("TON-RIV-2", 1, "In Progress", "2026-10-20", "HGC"),
			("TON-RIV-3", 1, "Completed", "2026-10-01", "HGC"), ("TON-RIV-4", 0, "Queued", "2026-09-01", "HGC"),
			("TON-RIV-5", 1, "Queued", "2026-09-02", "RV"), ("TON-RIV-6", 1, "Failed", "2026-09-15", "HGC"),
			("TON-RIV-7", 1, "Failed", "2026-08-01", "RV"), ("TON-RIV-8", 0, "Failed", "2026-08-02", "HGC"),
			("TON-RIV-9", 2, "Failed", "2026-08-03", "HGC"), ("TON-RIV-10", 1, "Skipped", "2026-08-04", "HGC")]:
		insert("Repost Item Valuation", name=n, docstatus=ds, status=st, posting_date=d, company=co)
	for n, ds, ci, co in [("TON-POS-1", 1, "", "HGC"), ("TON-POS-2", 1, None, "HGC"), ("TON-POS-3", 1, "TON-SI-07", "HGC"),
			("TON-POS-4", 0, "", "HGC"), ("TON-POS-5", 1, "", "RV"), ("TON-POS-6", 2, "", "HGC")]:
		insert("POS Invoice", name=n, docstatus=ds, consolidated_invoice=ci, company=co, posting_date="2026-10-26",
			owner=PRIVATE[4], customer_name=PRIVATE[2])
	# Hoá đơn update_stock = 0 chưa trừ kho (> 7 ngày): NR1 (19/10, 8 ngày) + NR10 (giao 4/10) = 2, cũ nhất 15/09.
	for n, d, lines, kw in [
			("TON-SI-NR1", "2026-10-19", [("TON-TRAD1", 10, 10, 0, {})], {}),
			("TON-SI-NR2", "2026-10-20", [("TON-TRAD1", 10, 10, 0, {})], {}),                     # đúng 7 ngày → chưa tính
			("TON-SI-NR3", "2026-09-01", [("TON-TRAD1", 10, 10, 10, {})], {}),                    # giao đủ
			("TON-SI-NR5", "2026-09-01", [("TON-TRAD1", 2, 48, 2, {"uom": "Thùng"})], {}),        # giao đủ 2 thùng (= 48 hộp)
			("TON-SI-NR6", "2026-09-01", [("TON-TRAD1", 10, 10, 0, {"delivery_note": "TON-DN-02", "dn_detail": "x"})], {}),
			("TON-SI-NR7", "2026-09-01", [("TON-DV1", 1, 1, 0, {})], {}),                          # mã không quản lý kho
			("TON-SI-NR8", "2026-09-01", [("TON-TRAD1", 10, 10, 0, {})], {"company": "RV"}),
			("TON-SI-NR9", "2026-09-01", [("TON-TRAD1", 10, 10, 0, {})], {"is_opening": "Yes"}),
			("TON-SI-NR10", "2026-09-15", [("TON-TRAD1", 10, 10, 4, {}), ("TON-TRAD2", 5, 5, 5, {})], {}),
			("TON-SI-NR11", "2026-09-01", [("TON-TRAD1", 10, 10, 0, {})], {"docstatus": 0})]:
		insert("Sales Invoice", name=n, **{"docstatus": 1, "posting_date": d, "company": "HGC", "is_return": 0,
			"update_stock": 0, "customer_name": PRIVATE[2], "owner": PRIVATE[0], **kw})
		for i, (it, q, sq, dq, extra) in enumerate(lines, 1):
			insert("Sales Invoice Item", parent=n, parenttype="Sales Invoice", parentfield="items", idx=i, item_code=it,
				qty=q, stock_qty=sq, delivered_qty=dq, **extra)


def main_seed(sx=True):
	reset()
	bc_settings()
	k = K()
	base(k, sx=sx)
	seed(k)
	k.finalize()
	return k


def ov():
	from bc.api import kho_ton
	return kho_ton.get_overview(refresh=1)


def tr():
	from bc.api import kho_ton
	return kho_ton.get_trend(refresh=1)


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


def near(a, b, eps=0.005):
	return a is not None and b is not None and abs(a - b) < eps


if __name__ == "__main__":
	c = Check()
	km = main_seed()   # giữ K của seed: thêm sổ sau finalize phải nối số dòng sổ (SLE-…) của nó
	from bc.api import kho_ton

	d = ov()
	c("có dữ liệu", d["available"] is True and d["meta"]["asof"] == "2026-10-27" and d["meta"]["group_mode"] == "subtree"
		and d["meta"]["groups_found"] == {"tet": True, "traditional": True}, d.get("meta"))
	c("mọi khối đều có", all(d[b].get("available") for b in ("value", "doi", "slow", "tet_stock", "health")),
		{b: d[b].get("available") for b in ("value", "doi", "slow", "tet_stock", "health")})

	# ═══ K1. Giá trị tồn bây giờ ═══
	v = d["value"]
	t = v["totals"]
	# TRAD1 10.580.000 + TRAD2 2.880.000 + TRAD3 3.150.000 + TET1 8.000.000 (gồm 500k ghi 30/10) + QUA1 12.000.000 (gồm 2 tr
	# ghi 05/11) + TPK 1.800.000 + NL1 44.000.000 + NL2 8.005.000 + NL3 4.000.000 (NVL 70 kg + xưởng 10 kg) + BB1 2.200.000
	# + BTP1 3.210.000 + FG1 200.000 (20 hộp) + RM1 850.000 (100 − 10 − 10 + 5 kg) + SR1 500.000 + NL4 5.000 (0 kg)
	# + TET2 1.000.000 (kho trả về) = 102.380.000 (RV: TRAD1 +1 tr, TRAD3 bán, QUA1 tương lai — KHÔNG tính)
	c("K1 tổng = Σ Bin kho công ty (gồm mã / kho ngừng dùng, dòng âm, dòng chỉ còn giá trị, phiếu tương lai; bỏ công ty khác)",
		t["value"] == 102_380_000, t)
	c("K1 không bán được = trả về 1.130.000 (TRAD1 100k + TRAD2 30k + TET2 1 tr) + cách ly 150k; bán được = phần còn lại; đi đường 200k",
		(t["value_unsellable"], t["value_sellable"], t["value_transit"]) == (1_280_000, 101_100_000, 200_000), t)
	# 11 mã cũ + FG1, RM1, SR1, TET2 (NL4 0 kg không tính); 21 dòng Bin cũ + FG1, RM1, SR1, NL4 (chỉ giá trị), TET2, NL3@xưởng
	c("K1 15 mã còn tồn, 10 kho có hàng, 27 dòng Bin, 1 dòng âm",
		(t["items_in_stock"], t["warehouses_in_stock"], t["rows"], t["negative_rows"]) == (15, 10, 27, 1), t)
	role = {r["key"]: r["value"] for r in v["by_role"]}
	# TP: TRAD1 9.060.000 + TRAD2 2.850.000 + TRAD3 3.000.000 + TET1 5.500.000 + QUA1 12.000.000 + TPK 1.650.000 + FG1 200.000
	#   = 34.260.000
	# Cửa hàng: CH1 (TET1 2.500.000 − TRAD1 80.000) + CH2 TRAD1 1.300.000 = 3.720.000
	# Sản xuất: Xưởng (NL1 12.000.000 + BTP1 10.000 + NL3 500.000) + BTP 3.200.000 + NVL (NL1 32.000.000 + NL2 8.005.000
	#   + NL3 3.500.000 + BB1 2.200.000 + RM1 850.000 + SR1 500.000 + NL4 5.000) = 62.770.000
	c("K1 theo khu vực kho", role == {"tp": 34_260_000, "cua_hang": 3_720_000, "di_duong": 200_000, "san_xuat": 62_770_000,
		"khong_ban": 1_280_000, "khac": 150_000}, role)
	kb = by(v["by_role"], "key", "khong_ban")
	c("K1 không bán được tách trả về / cách ly", [(x["role"], x["value"]) for x in kb["roles"]] == [("tra_ve", 1_130_000), ("cach_ly", 150_000)],
		kb["roles"])
	# UX-3: khu vực đặt tên theo KHO (hàng hết hạn / thu hồi ở kho thường không nằm ở đây — trang Hạn dùng); UX-11c: có kho
	# trả về / cách ly (SX Settings) → configured.
	c("UX-3/UX-11c K1 khu vực 'Kho trả về & cách ly' (không phải 'Không bán được'), đã xác định kho từng vai trò",
		(kb["label"], kb.get("configured"), [x.get("configured") for x in kb["roles"]]) == ("Kho trả về & cách ly", True, [True, True]),
		(kb["label"], kb.get("configured"), kb["roles"]))
	kc = by(v["by_role"], "key", "khac")
	c("K1 kho ngừng dùng còn hàng nằm ở Kho khác, có cờ ngừng dùng", [(w["label"], w["value"], w["disabled"]) for w in kc["warehouses"]]
		== [("Kho cũ", 150_000, True)], kc["warehouses"])
	ch = by(v["by_role"], "key", "cua_hang")
	c("K1 cửa hàng: từng kho (CH Bạch Đằng 2.420.000 gồm dòng âm, CH Tuệ Tĩnh 1.300.000)",
		[(w["label"], w["value"]) for w in ch["warehouses"]] == [("CH Bạch Đằng", 2_420_000), ("CH Tuệ Tĩnh", 1_300_000)], ch["warehouses"])
	from bc.api.live import _finished_stock
	live_v = _finished_stock(TP)["value"]
	kt = v["kho_tp"]
	c("K1 Kho thành phẩm = live._finished_stock(_wh()) = 34.260.000 (cùng số màn Thời gian thực), cùng tập kho",
		kt["value"] == live_v == role["tp"] == 34_260_000 and kt["same"] is True and kt.get("role_stranded_value") == 0, (kt, live_v))
	c("K1 Kho thành phẩm không đưa số hộp / thùng của live (live cộng mọi đơn vị trong kho)",
		not ({"boxes", "cartons"} & set(kt)), sorted(kt))
	g = {x["key"]: x for x in v["by_group"]}
	# Tết theo CÂY: TET1 8.000.000 + QUA1 (nhóm con Hộp quà Tết) 12.000.000 + TET2 1.000.000; so '=' chỉ còn 9.000.000.
	# Truyền thống: 16.610.000 + FG1 200.000; khác: 63.215.000 + RM1 850.000 + SR1 500.000 + NL4 5.000.
	c("K1 nhóm theo cây: Tết 21.000.000 (gồm nhóm con), truyền thống 16.810.000, khác 64.570.000",
		(g["tet"]["value"], g["traditional"]["value"], g["other"]["value"]) == (21_000_000, 16_810_000, 64_570_000),
		{k_: x["value"] for k_, x in g.items()})
	c("K1 truyền thống bán được = 16.810.000 − kho trả về 130.000", g["traditional"]["value_sellable"] == 16_680_000, g["traditional"])
	# Tết (mọi kho): TET1 160 hộp (8 thùng) + QUA1 120 hộp (12 thùng) + TET2 10 hộp (1 thùng)
	c("K1 Tết: 290 hộp = 21 thùng", (g["tet"]["qty"], g["tet"]["uom"], g["tet"]["cartons"], g["tet"]["boxes_without_carton_factor"])
		== (290, "Hộp", 21.0, 0), g["tet"])
	# Truyền thống: TRAD1 529 (453+65+5+10−4) / 24 = 22,04; TRAD3 210 / 12 = 17,5; FG1 20 / 10 = 2 → 41,5 thùng; TRAD2 288 hộp chưa
	# khai thùng; 529 + 288 + 210 + 20 = 1.047 hộp
	c("K1 truyền thống: 1.047 hộp, 41,5 thùng + 288 hộp chưa khai quy cách (1 mã)",
		(g["traditional"]["qty"], g["traditional"]["cartons"], g["traditional"]["boxes_without_carton_factor"],
		g["traditional"]["items_without_carton_factor"]) == (1047, 41.5, 288, 1), g["traditional"])
	c("K1 nhóm khác lẫn Kg / Cái / Hộp → không cộng số lượng", g["other"]["qty"] is None and g["other"]["cartons"] is None, g["other"])
	osp = {x["key"]: x["value"] for x in v["other_split"]}
	c("K1 tách nhóm khác theo loại sx (NVL 44 + 8,005 + 4 + 0,85 + 0,5 + 0,005 tr, bao bì, bán thành phẩm, TP khác)",
		osp == {"nvl": 57_360_000, "bao_bi": 2_200_000, "btp": 3_210_000, "tp_khac": 1_800_000, "khac": 0}, osp)
	tp = v["tp"]
	# TP ở kho bán được (TET2 ở kho trả về → không): TET1 160 + QUA1 120 + TRAD1 524 + TRAD2 285 + TRAD3 210 + TPK 55 + FG1 20
	# = 1.374 hộp; 8 + 12 + 21,83 + 17,5 + 9,17 + 2 = 70,5 thùng; giá trị 8 + 12 + 10,48 + 2,85 + 3,15 + 1,65 + 0,2 = 38,33 tr
	c("K1 thành phẩm (kho bán được): 1.374 hộp, 70,5 thùng + 285 hộp chưa khai, 38.330.000",
		(tp["qty"], tp["uom"], tp["cartons"], tp["boxes_without_carton_factor"], tp["value"], tp["items"], tp["source"])
		== (1374, "Hộp", 70.5, 285, 38_330_000, 7, "sx"), tp)
	c("XC-5/UX-9 K1 thành phẩm: phần chưa khai quy cách thùng có hàng = TRAD2 285 hộp (1 mã) — cùng cơ sở với dải sức khoẻ",
		(tp.get("boxes_without_carton_in_stock"), tp.get("items_without_carton_in_stock")) == (285, 1), tp)
	tops = [(x["item_code"], x["value"]) for x in v["top"]]
	c("K1 top giá trị: mã ẩn (NL3) bỏ khỏi danh sách nhưng vẫn trong tổng", tops == [("TON-NL1", 44_000_000), ("TON-QUA1", 12_000_000),
		("TON-TRAD1", 10_580_000), ("TON-NL2", 8_005_000), ("TON-TET1", 8_000_000), ("TON-BTP1", 3_210_000), ("TON-TRAD3", 3_150_000),
		("TON-TRAD2", 2_880_000), ("TON-BB1", 2_200_000), ("TON-TPK", 1_800_000)], tops)
	c("K1 top: thùng chỉ khi có hệ số (QUA1 12 thùng, NL1 không)", by(v["top"], "item_code", "TON-QUA1")["cartons"] == 12
		and by(v["top"], "item_code", "TON-NL1")["cartons"] is None and by(v["top"], "item_code", "TON-TRAD1")["short_name"] == "TON 1", v["top"][:3])

	# ═══ K4. Số ngày tồn kho ═══
	o = d["doi"]
	# Giá vốn truyền thống 30/07–27/10: SI 30/07 1.000.000 + SI 20/10 600.000 − trả POS 30.000 + DN 26/10 400.000 + SI 26/10 80.000
	# = 2.050.000 (bán 29/07 ngoài cửa sổ; bán huỷ 02/10 không tính; phiếu giảm giá update_stock = 0 không có sổ; bán TRAD3 75.000
	# của công ty RV 10/10 không tính). DOI = 16.680.000 / (2.050.000 / 90) = 1.501.200.000 / 2.050.000 = 732,29 → 732,3 ngày.
	c("K4 cửa sổ 90 ngày 30/07 → 27/10", (o["window_days"], o["from"], o["to"]) == (90, "2026-07-30", "2026-10-27"), o)
	c("K4 truyền thống: giá trị bán được 16.680.000, giá vốn 2.050.000 (bỏ công ty khác), 732,3 ngày",
		(o["traditional"]["value"], o["traditional"]["cogs"], o["traditional"]["days"]) == (16_680_000, 2_050_000, 732.3), o["traditional"])
	c("K4 Tết ngoài giai đoạn bán (27/10 = chuẩn bị mùa) → không tính DOI; giá trị chỉ kho bán được (TET2 ở kho trả về không vào)",
		(o["tet"]["phase"], o["tet"]["applicable"], o["tet"]["days"], o["tet"]["value"], o["tet"]["cogs"])
		== ("chuan_bi", False, None, 20_000_000, 2_500_000), o["tet"])

	# ═══ K5. Hàng chậm / tồn chết ═══
	s = d["slow"]
	c("K5 ngưỡng", (s["slow_days"], s["dead_days"], s.get("slow_includes_dead")) == (90, 180, True), s)
	tot, stp, svt = s["total"], s["tp"], s["vat_tu"]
	# Phạm vi (trừ Tết, tồn bán được > 0) — ngày chưa xuất tính tay:
	#   TRAD1 10.480.000 (bán 26/10: 1 ngày), TRAD2 2.850.000 (bán 29/07: 90), TRAD3 3.150.000 (chưa xuất, nhập đầu 01/07/2025: 483;
	#   bán của công ty RV 10/10 KHÔNG tính), TPK 1.650.000 (bán 30/04: đúng 180 → chậm, chưa chết), FG1 200.000 (chỉ NHẬN từ 2 phiếu
	#   sản xuất 01/03 + 27/10, chưa bán: nhập đầu 01/03 → 240, chưa xuất), NL1 44.000.000 (sản xuất 28/07: 91), NL2 8.005.000 (bù nợ
	#   BOM 10/10: 17, W8), NL3 4.000.000 (chưa xuất: xuất huỷ có "bù nợ BOM" giữa câu + chuyển kho có "bù nợ BOM" đầu câu đều không
	#   phải dùng; nhập đầu 10/09/2025: 412), BB1 2.200.000 (kiểm kê / dọn tồn không phải dùng; nhập đầu 01/06: 148, chưa xuất),
	#   BTP1 3.210.000 (Repack 27/09: 30), RM1 850.000 (dùng sản xuất HÔM NAY 27/10: 0), SR1 500.000 (chỉ kiểm kê đầu kỳ 01/10/2025,
	#   actual_qty 0 vẫn là lần nhập đầu: 391, chưa xuất). NL4 0 kg (chỉ còn 5.000 đ) và hàng Tết KHÔNG thuộc phạm vi.
	#   = 12 mã, 81.095.000.
	# Chậm (> 90, GỒM tồn chết): TRAD3 + TPK + FG1 + NL1 + NL3 + BB1 + SR1 = 3,15 + 1,65 + 0,2 + 44 + 4 + 2,2 + 0,5 = 55.700.000
	# Chết (> 180): TRAD3 + FG1 + NL3 + SR1 = 7.850.000. Chưa xuất: TRAD3 + FG1 + NL3 + BB1 + SR1 = 10.050.000.
	# % trên giá trị kho bán được (mọi mã, cả Tết) 101.100.000: 55,7 / 101,1 = 55,09% → 55,1; 7,85 / 101,1 = 7,76% → 7,8.
	c("K5 phạm vi 12 mã / 81.095.000 (Tết loại ra, mã tồn bán được = 0 loại ra); mẫu số % = 101.100.000",
		(tot["items"], tot["value"], tot.get("sellable_value")) == (12, 81_095_000, 101_100_000), tot)
	c("K5 chậm (> 90 ngày, gồm tồn chết): 7 mã, 55.700.000 = 55,1% giá trị bán được",
		(tot["slow_items"], tot["slow_value"], tot["slow_pct"]) == (7, 55_700_000, 55.1), tot)
	c("K5 tồn chết (> 180): TRAD3 + FG1 + NL3 + SR1 = 7.850.000 (7,8%)", (tot["dead_items"], tot["dead_value"], tot["dead_pct"])
		== (4, 7_850_000, 7.8), tot)
	c("K5 chưa từng xuất: TRAD3 + FG1 + NL3 + BB1 + SR1 = 10.050.000", (tot["never_items"], tot["never_value"]) == (5, 10_050_000), tot)
	bk = {b["key"]: (b["items"], b["value"]) for b in tot["buckets"]}
	# 0-30: TRAD1 + NL2 + BTP1 + RM1 = 10,48 + 8,005 + 3,21 + 0,85; 31-90: TRAD2; 91-180: TPK + NL1 + BB1; >180: TRAD3 + FG1 + NL3 + SR1
	c("K5 tất cả theo tuổi", bk == {"0-30": (4, 22_545_000), "31-90": (1, 2_850_000), "91-180": (3, 47_850_000), ">180": (4, 7_850_000)}, bk)
	bk = {b["key"]: (b["items"], b["value"]) for b in stp["buckets"]}
	c("K5 thành phẩm theo tuổi: 0-30 TRAD1 (1 ngày), 31-90 TRAD2 (đúng 90), 91-180 TPK (đúng 180), >180 TRAD3 + FG1",
		bk == {"0-30": (1, 10_480_000), "31-90": (1, 2_850_000), "91-180": (1, 1_650_000), ">180": (2, 3_350_000)}, bk)
	# Thành phẩm: mẫu số = TP ở kho bán được 38.330.000 (gồm Tết). Chậm TRAD3 + TPK + FG1 = 5.000.000 → 13,04% → 13,0;
	# chết TRAD3 + FG1 = 3.350.000 → 8,74% → 8,7.
	c("K5 thành phẩm: 5 mã 18.330.000; chậm 3 mã 5.000.000 (13,0%), chết 2 mã 3.350.000 (8,7%), chưa xuất 2",
		(stp["items"], stp["value"], stp.get("sellable_value"), stp["slow_items"], stp["slow_value"], stp["slow_pct"], stp["dead_items"],
		stp["dead_value"], stp["dead_pct"], stp["never_items"]) == (5, 18_330_000, 38_330_000, 3, 5_000_000, 13.0, 2, 3_350_000, 8.7, 2), stp)
	bk = {b["key"]: (b["items"], b["value"]) for b in svt["buckets"]}
	c("K5 vật tư theo tuổi: 0-30 NL2 + BTP1 (đúng 30) + RM1 (dùng hôm nay), 91-180 NL1 (đúng 91) + BB1, >180 NL3 + SR1",
		bk == {"0-30": (3, 12_065_000), "31-90": (0, 0), "91-180": (2, 46_200_000), ">180": (2, 4_500_000)}, bk)
	c("K5 top thành phẩm: TRAD3 (ngừng dùng, chưa xuất, 483 ngày; RV bán không tính), TPK (bán huỷ 01/10 không tính: 180 ngày, chậm),"
		" FG1 (chỉ sản xuất ra, chưa bán: 240 ngày từ lần nhập đầu)",
		[(x["item_code"], x["status"], x["idle_days"], x["never"]) for x in stp["top"]]
		== [("TON-TRAD3", "dead", 483, True), ("TON-TPK", "slow", 180, False), ("TON-FG1", "dead", 240, True)], stp["top"])
	tpk = by(stp["top"], "item_code", "TON-TPK")
	c("K5 TPK: lần bán cuối 30/04, 9,2 thùng", (tpk["last_out"], tpk["last_sale"], tpk["qty"], tpk["cartons"]) == ("2026-04-30", "2026-04-30", 55, 9.17), tpk)
	fg = by(stp["top"], "item_code", "TON-FG1")
	c("K5 FG1: dòng NHẬN của phiếu sản xuất không phải lần dùng; nhập đầu 01/03; 20 hộp = 2 thùng",
		(fg["last_used"], fg["last_out"], fg["first_in"], fg["qty"], fg["cartons"]) == (None, None, "2026-03-01", 20, 2), fg)
	c("K5 top vật tư: NL1 (chuyển kho 15/10 không phải dùng → 91 ngày), BB1 (kiểm kê + dọn tồn không phải dùng), SR1 (chỉ kiểm kê đầu kỳ"
		" → 391 ngày); NL3 bị ẩn",
		[(x["item_code"], x["status"], x["idle_days"], x["last_out"], x["first_in"]) for x in svt["top"]]
		== [("TON-NL1", "slow", 91, "2026-07-28", "2025-10-01"), ("TON-BB1", "slow", 148, None, "2026-06-01"),
		("TON-SR1", "dead", 391, None, "2025-10-01")], svt["top"])
	# Vật tư: mẫu số = 101.100.000 − 38.330.000 = 62.770.000 (gồm NL4 5.000). Chậm NL1 + NL3 + BB1 + SR1 = 50.700.000 → 80,77% → 80,8;
	# chết NL3 + SR1 = 4.500.000 → 7,17% → 7,2.
	c("K5 vật tư: 7 mã 62.765.000; chậm 4 mã 50.700.000 (80,8%), chết NL3 (ẩn, vẫn tính) + SR1 4.500.000 (7,2%), chưa xuất 3",
		(svt["items"], svt["value"], svt.get("sellable_value"), svt["slow_items"], svt["slow_value"], svt["slow_pct"], svt["dead_items"],
		svt["dead_value"], svt["dead_pct"], svt["never_items"]) == (7, 62_765_000, 62_770_000, 4, 50_700_000, 80.8, 2, 4_500_000, 7.2, 3), svt)

	te = d["tet_stock"]
	c("K5 tồn hàng Tết: chuẩn bị mùa, 20.000.000, 280 hộp, 20 thùng (TET2 ở kho trả về không tính)",
		(te["phase"], te["label"], te["value"], te["qty"], te["cartons"], te["items"]) == ("chuan_bi", "Tồn hàng Tết chuẩn bị mùa",
		20_000_000, 280, 20.0, 2), te)
	c("K5 tồn Tết: top QUA1 12 tr, TET1 8 tr (8 thùng)", [(x["item_code"], x["value"], x["cartons"]) for x in te["top"]]
		== [("TON-QUA1", 12_000_000, 12), ("TON-TET1", 8_000_000, 8)], te["top"])

	# ═══ Sức khoẻ ═══
	h = d["health"]
	c("health: 2 phiếu tính lại giá đang chờ từ 20/10 (bỏ nháp, xong, công ty khác)", (h["pending_reposts"], h["repost_since"]) == (2, "2026-10-20"), h)
	c("health overview KHÔNG quét lại sổ cho hàng ghi ngày tương lai (lấy ở trend)", "future_value" not in h and "ledger_bin_diff" not in h, h)
	c("health: cho phép tồn âm bật / theo lô tắt", (h["allow_negative_stock"], h["allow_negative_stock_for_batch"]) == (True, False), h)
	c("health: 2 phiếu POS chưa gộp", h["pos_unconsolidated"] == 2, h)
	c("health: 2 hoá đơn chưa trừ kho > 7 ngày (bỏ đúng 7 ngày, giao đủ theo thùng, lập từ phiếu giao, mã dịch vụ, đầu kỳ, nháp, công ty khác)",
		h["si_no_stock_relief"] == {"count": 2, "oldest": "2026-09-15", "days": 7}, h["si_no_stock_relief"])
	c("health: tập TP sx lệch cây nhóm 1 / 1", h["tp_set_mismatch"] == {"source": "sx", "in_sx_not_group": 1, "in_group_not_sx": 1},
		h["tp_set_mismatch"])
	c("health: nhóm Tết có nhóm con", h["group_mode"] == "subtree" and h["group_has_children"] == {"tet": True, "traditional": False}, h)
	c("health: công ty / kho TP khớp sx", (h["company_mismatch"], h["kho_tp_mismatch"]) == (False, False), h)
	c("health: 1 mã TP chưa khai quy cách thùng (285 hộp)", (h["items_without_carton_factor"], h["boxes_without_carton_factor"]) == (1, 285), h)
	c("NUM-1 health: phần chưa khai quy cách thùng theo từng đơn vị kho", (h.get("uom_without_carton_factor"), h.get("without_carton_by_uom"))
		== ("Hộp", [{"uom": "Hộp", "items": 1, "qty": 285}]), h)
	# Failed: RIV-6 (HGC, 15/09) — RIV-7 công ty RV, RIV-8 nháp, RIV-9 huỷ, RIV-10 Skipped không tính; Queued / In Progress giữ 2 từ 20/10.
	c("XR-REAL-3 health: 1 lượt tính lại giá vốn LỖI từ 15/09 (bộ lập lịch không chạy lại), tách khỏi 2 lượt đang chờ",
		(h.get("failed_reposts"), h.get("failed_repost_since"), h["pending_reposts"], h["repost_since"]) == (1, "2026-09-15", 2, "2026-10-20"), h)
	c("health: 2 dòng chỉ còn giá trị (BTP1 xưởng 10.000 + NL4 5.000)", (h["stranded_value_rows"], h["stranded_value"]) == (2, 15_000), h)

	# ═══ K2. Xu hướng ═══
	T = tr()
	c("trend có dữ liệu", T["available"] and T["trend"]["available"] and T["nxt"]["available"], T.get("trend"))
	tt = T["trend"]
	pts = [(p["month"], p["value"]) for p in tt["points"]]
	# Cuối tháng (tính tay ở seed): 09/2025 8,15; 10/25 +50,5 (tồn đầu: SR TRAD1 10 + SR SR1 0,5 + phiếu đầu kỳ 40) +50 −5 = 103,65;
	# 11 −20; 12 +10; 01 −15; 02 +1 (RM1); 03 +10 (MFG2 ròng 0); 04 +1,2; 05 +3 +0,1 (NL4); 06 +2 −0,095 (NL4 huỷ); 07 −1,2; 08 +2;
	# 09 −1 −0,04 +0,05 −0,1 +0,005 = 95,57; hôm nay 27/10: −3,55 +0,2 +8 −2 +0,6 +0,7 −0,69 +1 (TET2) +0,05 (RM1 ghi HÔM NAY;
	# MFG3 hôm nay ròng 0) = 99,88 tr. Dòng RV không tính.
	c("K2 12 cuối tháng + hôm nay", pts == [("2025-10", 103_650_000), ("2025-11", 83_650_000), ("2025-12", 93_650_000),
		("2026-01", 78_650_000), ("2026-02", 79_650_000), ("2026-03", 89_650_000), ("2026-04", 90_850_000), ("2026-05", 93_950_000),
		("2026-06", 95_855_000), ("2026-07", 94_655_000), ("2026-08", 96_655_000), ("2026-09", 95_570_000), ("2026-10", 99_880_000)], pts)
	last = tt["points"][-1]
	# Hôm nay theo nhóm: Tết 21 − 2,5 (tương lai) = 18,5; truyền thống = K1 16,81 (gồm FG1 nhận HÔM NAY); khác = K1 64,57 (gồm
	# RM1 nhập 50k và xuất 100k HÔM NAY).
	c("K2 điểm hôm nay theo nhóm (Tết 18,5 tr; truyền thống 16,81 tr; khác 64,57 tr) gồm phiếu ghi HÔM NAY, cắt sau hôm nay",
		(last["today"], last["date"], last["tet"], last["traditional"], last["other"]) == (True, "2026-10-27", 18_500_000, 16_810_000, 64_570_000), last)
	c("K2 điểm 09/2026 theo nhóm", by(tt["points"], "month", "2026-09") | {} == {"month": "2026-09", "date": "2026-09-30", "today": False,
		"value": 95_570_000, "tet": 20_000_000, "traditional": 17_760_000, "other": 57_810_000}, by(tt["points"], "month", "2026-09"))
	c("K2 đầu năm TC (30/04/2026) và cùng kỳ (30/09/2025)", (tt["fy_start_date"], tt["fy_start_value"], tt["ly_month_end"], tt["ly_month_end_value"])
		== ("2026-04-30", 90_850_000, "2025-09-30", 8_150_000), tt)
	c("K2 phiếu tương lai 2,5 tr (30/10 cùng tháng KHÔNG vào điểm hôm nay; phiếu HÔM NAY không là tương lai; RV 20/11 không tính);"
		" sổ = Bin (lệch 0)", (tt["future_value"], tt["bin_total"], tt["ledger_bin_diff"]) == (2_500_000, 102_380_000, 0), tt)
	c("K2 hôm nay + tương lai = tổng K1", near(last["value"] + tt["future_value"], v["totals"]["value"]))

	# ═══ K3. Nhập – xuất – tồn ═══
	nx = T["nxt"]
	c("K3 13 tháng, mặc định tháng 09 + tháng này", (len(nx["months"]), nx["default_month"], nx["current_month"]) == (13, "2026-09", "2026-10"), nx["default_month"])
	ok = True
	for mo in nx["months"]:
		for gk, x in mo["groups"].items():
			if not near(x["opening"] + sum(x["flows"].values()), x["closing"]):
				ok = False
	prev = None
	for mo in nx["months"]:
		if prev and not near(prev["groups"]["all"]["closing"], mo["groups"]["all"]["opening"]):
			ok = False
		prev = mo
	c("K3 đẳng thức: đầu + Σ loại = cuối (mọi tháng, mọi nhóm); cuối tháng trước = đầu tháng sau", ok)
	c("K3 cuối tháng này = điểm hôm nay K2", near(nx["months"][-1]["groups"]["all"]["closing"], last["value"]))
	c("K3 nhóm cộng lại = tổng", all(near(sum(mo["groups"][g_]["closing"] for g_ in ("tet", "traditional", "other")), mo["groups"]["all"]["closing"])
		for mo in nx["months"]))

	def flows(month, grp="all"):
		mo = by(nx["months"], "month", month)
		return {k_: v_ for k_, v_ in mo["groups"][grp]["flows"].items() if v_}, mo["groups"][grp]["opening"], mo["groups"][grp]["closing"]

	c("K3 10/2025: tồn đầu 50,5 tr (Opening Stock 10 + 0,5 + phiếu đầu kỳ 40), mua 50, bán −5", flows("2025-10")
		== ({"ton_dau": 50_500_000, "mua": 50_000_000, "ban": -5_000_000}, 8_150_000, 103_650_000), flows("2025-10"))
	c("K3 03/2026: sản xuất FG1 từ RM1 = nội bộ (truyền thống +100k, khác −100k), tổng 0", (flows("2026-03", "traditional")[0],
		flows("2026-03", "other")[0].get("noi_bo"), flows("2026-03")[0]) == ({"noi_bo": 100_000}, -100_000, {"mua": 10_000_000}),
		(flows("2026-03", "traditional"), flows("2026-03")))
	c("K3 06/2026: mua bao bì 2 tr, xuất huỷ NL4 −95k", flows("2026-06") == ({"mua": 2_000_000, "xuat_khac": -95_000}, 93_950_000, 95_855_000),
		flows("2026-06"))
	c("K3 08/2026: nhập tạm 2 tr (remarks 'Nhập tạm — ')", flows("2026-08") == ({"nhap_tam": 2_000_000}, 94_655_000, 96_655_000), flows("2026-08"))
	c("K3 09/2026: xuất huỷ (có 'bù nợ BOM' giữa câu vẫn là xuất huỷ), kiểm kê sx, dọn tồn sx, kiểm kê cửa hàng, điều chỉnh"
		" (Adjustment Entry = khác); phiếu huỷ không vào",
		flows("2026-09") == ({"xuat_khac": -1_000_000, "kiem_ke_sx": 50_000, "don_sx": -40_000, "kiem_ke_ch": -100_000, "khac": 5_000},
		96_655_000, 95_570_000), flows("2026-09"))
	c("K3 09/2026 truyền thống: Repack nhận +800k (nội bộ theo nhóm)", flows("2026-09", "traditional")
		== ({"kiem_ke_sx": 50_000, "don_sx": -40_000, "kiem_ke_ch": -100_000, "noi_bo": 800_000}, 17_050_000, 17_760_000), flows("2026-09", "traditional"))
	# 10/2026: bán −2,5 −0,6 +0,03 −0,4 −0,08 = −3,55 tr; mua PI 8 + TET2 1 + RM1 (hôm nay) 0,05 = 9,05 tr; bù nợ BOM −2 tr (chuyển
	# kho NL3 có diễn giải bù nợ BOM ròng 0); nhập tạm 0,6; nhập khác 0,6 + 0,1 (trả về nhập lại); xuất khác −0,59 −0,1; khác 0,2
	# (Subcontracting Receipt); kiểm kê sx / dọn tồn / chuyển kho / sản xuất hôm nay ròng 0; bán TRAD3 của RV không vào.
	c("K3 10/2026 (tới hôm nay)", flows("2026-10") == ({"ban": -3_550_000, "mua": 9_050_000, "bu_no_bom": -2_000_000, "nhap_tam": 600_000,
		"nhap_khac": 700_000, "xuat_khac": -690_000, "khac": 200_000}, 95_570_000, 99_880_000), flows("2026-10"))
	c("K3 W2: phiếu giảm giá trả hàng update_stock = 0 không có sổ; hàng về qua phiếu nhập (nhập khác 100k truyền thống);"
		" FG1 sản xuất hôm nay +100k nội bộ",
		flows("2026-10", "traditional") == ({"ban": -1_050_000, "nhap_khac": 100_000, "xuat_khac": -100_000, "noi_bo": 100_000},
		17_760_000, 16_810_000), flows("2026-10", "traditional"))
	c("K3 nhãn đủ 12 loại", [x["key"] for x in T["meta"]["loai"]] == ["ton_dau", "mua", "ban", "nhap_tam", "bu_no_bom", "noi_bo", "nhap_khac",
		"xuat_khac", "kiem_ke_sx", "kiem_ke_ch", "don_sx", "khac"])
	lb = {x["key"]: x["label"] for x in T["meta"]["loai"]}
	# UX-1 / XC-1: kiem_ke_ch = MỌI Stock Reconciliation (cửa hàng, kho TP, kho trả về…) — không gọi là "cửa hàng"; kiem_ke_sx = mọi
	# phiếu của lần kiểm kê sx ở mọi kho (gồm phiếu bù tồn âm ở kho khác) — không gọi là "kho sản xuất".
	c("UX-1 K3 nhãn: 'Kiểm kê bằng phiếu kiểm kho (cửa hàng & kho khác)' / 'Kiểm kê sản xuất'",
		(lb["kiem_ke_ch"], lb["kiem_ke_sx"]) == ("Kiểm kê bằng phiếu kiểm kho (cửa hàng & kho khác)", "Kiểm kê sản xuất"), lb)

	# ═══ Riêng tư + import cấm ═══
	dump = json.dumps([d, T], ensure_ascii=False, default=str)
	c("riêng tư: không email / người tạo / ghi chú / tên khách trong payload", not [p for p in PRIVATE if p in dump] and "@" not in dump
		and "owner" not in dump and "remarks" not in dump and "Hạch toán" not in dump and "TON-NB-01" not in dump,
		[p for p in PRIVATE if p in dump])
	src = open(os.path.join(BC_ROOT, "bc", "api", "kho_ton.py"), encoding="utf-8").read()
	src_kho = open(os.path.join(BC_ROOT, "bc", "api", "kho.py"), encoding="utf-8").read()
	deny = ["_dong_du", "ma_lo_ton_cu", "prefix_lo", "gia_von_hien", "ghi_gia_tu_tinh", "lo_cu"]
	c("không import helper sx có ghi DB / giá mua", not [x for x in deny if re.search(rf"\b{x}\b", src)]
		and not re.search(r"^\s*(from|import)\s+sx\.api\.(lo_cu|mfg)", src + src_kho, re.M), [x for x in deny if x in src])
	c("SQL không CURDATE/NOW, không % literal", not re.search(r"CURDATE\(|NOW\(\)", src) and "%Y" not in src and "LIKE" not in src)
	import ast
	tree = ast.parse(src)
	guards = []
	for n in tree.body:
		if isinstance(n, ast.FunctionDef) and any(getattr(dc, "attr", None) == "whitelist" or
				(isinstance(dc, ast.Call) and getattr(dc.func, "attr", None) == "whitelist") for dc in n.decorator_list):
			first = n.body[1] if isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) else n.body[0]
			guards.append((n.name, ast.unparse(first)))
	c("mọi method whitelisted mở đầu _guard('ton-kho')", guards == [("get_overview", "_guard('ton-kho')"), ("get_trend", "_guard('ton-kho')")], guards)

	# ═══ Thùng chưa khai: MỘT cơ sở cho thẻ thành phẩm và dải sức khoẻ (XC-5 / UX-9), theo từng đơn vị (NUM-1 / XR-COMP-1) ═══
	# Sổ đã finalize → Bin ghi thẳng (chỉ K1 / sức khoẻ đọc Bin); sx nhớ items_tp theo request → xoá nhớ sau khi thêm mã.
	kx = km
	kx.item("TON-XN1", "Bánh âm XN1", G_TRAD, custom_sx_nhom="TP")       # Hộp, chưa khai thùng, tồn ÂM ở cửa hàng
	kx.item("TON-XN2", "Bánh âm XN2", G_TRAD, custom_sx_nhom="TP")       # Hộp, chưa khai thùng, tồn ÂM ở kho TP
	insert("Bin", name="BIN-TON-XN1", item_code="TON-XN1", warehouse=CH1, actual_qty=-6, stock_value=-60_000, valuation_rate=10_000,
		company="HGC")
	insert("Bin", name="BIN-TON-XN2", item_code="TON-XN2", warehouse=TP, actual_qty=-2, stock_value=-20_000, valuation_rate=10_000,
		company="HGC")
	frappe.local.__dict__.pop("sx_nho", None)
	dx = ov()
	tx, hx = dx["value"]["tp"], dx["health"]
	# Thẻ TP (kho bán được): 1.374 − 6 − 2 = 1.366 hộp; thùng 70,5 (XN không hệ số); phần RÒNG chưa khai = TRAD2 285 − 6 − 2 = 277
	# (3 mã khác 0) — Σ hộp = Σ thùng × hệ số + 277 như kho.carton_total. Phần màn hiện "chưa khai quy cách thùng" = mã không hệ
	# số có tồn > 0: chỉ TRAD2 285 hộp (1 mã) — đúng số dải sức khoẻ (trước sửa: thẻ 277 / sức khoẻ 285, hai số cho một việc).
	c("XC-5/UX-9 mã TP chưa khai thùng tồn ÂM: thẻ TP ròng 1.366 hộp / 70,5 thùng / ròng 277 (3 mã); 'chưa khai quy cách thùng' 285 hộp"
		" (1 mã) = dải sức khoẻ",
		(tx["qty"], tx["cartons"], tx["boxes_without_carton_factor"], tx["items_without_carton_factor"],
		tx.get("boxes_without_carton_in_stock"), tx.get("items_without_carton_in_stock"))
		== (1366, 70.5, 277, 3, 285, 1) and (hx["boxes_without_carton_factor"], hx["items_without_carton_factor"]) == (285, 1),
		(tx, {k_: hx.get(k_) for k_ in ("items_without_carton_factor", "boxes_without_carton_factor", "without_carton_by_uom")}))
	kx.item("TON-XK1", "Bột TP XK1", G_GUI, uom="Kg", custom_sx_nhom="TP")     # Kg: không mã Kg nào đóng thùng
	kx.item("TON-XG1", "Chè gói XG1", G_GUI, uom="Gói", custom_sx_nhom="TP")   # Gói chưa khai thùng
	kx.item("TON-XG2", "Chè gói XG2", G_GUI, uom="Gói", carton=50, custom_sx_nhom="TP")  # Gói CÓ thùng 50 → đơn vị Gói đóng thùng
	for n, it, wh, q, val in (("BIN-TON-XK1", "TON-XK1", TP, 12.5, 1_250_000), ("BIN-TON-XG1", "TON-XG1", TP, 208, 208_000),
			("BIN-TON-XG2", "TON-XG2", CH2, 100, 100_000)):
		insert("Bin", name=n, item_code=it, warehouse=wh, actual_qty=q, stock_value=val, valuation_rate=val / q, company="HGC")
	frappe.local.__dict__.pop("sx_nho", None)
	dm = ov()
	tm_, hm = dm["value"]["tp"], dm["health"]
	# TP lẫn Hộp / Kg / Gói → thẻ chỉ tiền: 38.330.000 − 80.000 + 1.250.000 + 208.000 + 100.000 = 39.808.000; 7 + 3 = 10 mã còn hàng.
	c("NUM-1 thẻ TP lẫn đơn vị: không số lượng / thùng / chưa khai (không cộng Hộp với Kg), 10 mã, 39.808.000",
		(tm_["qty"], tm_["cartons"], tm_["boxes_without_carton_factor"], tm_.get("boxes_without_carton_in_stock"), tm_["items"], tm_["value"])
		== (None, None, None, None, 10, 39_808_000), tm_)
	# Sức khoẻ: Hộp (có mã khai thùng) → TRAD2 285; Gói (XG2 có thùng) → XG1 208; Kg không mã nào đóng thùng → bỏ (không phải thiếu
	# quy cách). Hai đơn vị → không có một tổng (None). Trước sửa: 3 mã, 285 + 12,5 + 208 = 505,5 "hộp".
	c("NUM-1/XR-COMP-1 health: 2 mã chưa khai thùng — Gói 208 + Hộp 285 tách đơn vị, bỏ Kg, không tổng chung",
		(hm["items_without_carton_factor"], hm["boxes_without_carton_factor"], hm.get("uom_without_carton_factor"), hm.get("without_carton_by_uom"))
		== (2, None, None, [{"uom": "Gói", "items": 1, "qty": 208}, {"uom": "Hộp", "items": 1, "qty": 285}]),
		{k_: hm.get(k_) for k_ in ("items_without_carton_factor", "boxes_without_carton_factor", "without_carton_by_uom")})
	xs = ("TON-XN1", "TON-XN2", "TON-XK1", "TON-XG1", "TON-XG2")
	frappe.db.sql("DELETE FROM `tabBin` WHERE item_code IN %(x)s", {"x": xs})
	frappe.db.sql("DELETE FROM `tabUOM Conversion Detail` WHERE parent IN %(x)s", {"x": xs})
	frappe.db.sql("DELETE FROM `tabItem` WHERE name IN %(x)s", {"x": xs})
	frappe.local.__dict__.pop("sx_nho", None)
	t0 = ov()["value"]["tp"]
	c("dọn mã thử thùng: thẻ TP trở lại 1.374 hộp / 285 chưa khai", (t0["qty"], t0.get("boxes_without_carton_in_stock")) == (1374, 285), t0)

	# ═══ XR-COMP-4: BC Settings kho_doi_days / kho_slow_days / kho_dead_days được dùng thật ═══
	single("BC Settings", kho_doi_days=30, kho_slow_days=10, kho_dead_days=60)
	ds_ = ov()
	o_, s_ = ds_["doi"], ds_["slow"]
	# W = 30 → cửa sổ 28/09–27/10. Giá vốn truyền thống: SI 20/10 600.000 − trả POS 30.000 + DN 26/10 400.000 + SI 26/10 80.000
	# = 1.050.000 (SI 30/07 ra ngoài; bán huỷ 02/10, RV 10/10 không tính) → 16.680.000 × 30 / 1.050.000 = 476,57 → 476,6 ngày.
	# Tết: SI 05/10 2.500.000 (chuẩn bị mùa → không tính ngày).
	c("XR-COMP-4 kho_doi_days = 30: cửa sổ 28/09 → 27/10, giá vốn truyền thống 1.050.000 → 476,6 ngày; Tết 2.500.000",
		(o_["window_days"], o_["from"], o_["to"], o_["traditional"]["cogs"], o_["traditional"]["days"], o_["tet"]["cogs"])
		== (30, "2026-09-28", "2026-10-27", 1_050_000, 476.6, 2_500_000), o_)
	# Ngày chưa xuất (như trên): TRAD1 1, RM1 0 → bình thường; NL2 17, BTP1 30 → chậm (> 10); TRAD2 90, NL1 91, BB1 148, TPK 180,
	# FG1 240, SR1 391, NL3 412, TRAD3 483 → chết (> 60). Chậm (gồm chết) = 81.095.000 − 10.480.000 − 850.000 = 69.765.000 (10 mã)
	# → 69.765.000 / 101.100.000 = 69,006% → 69,0; chết = 2,85 + 3,15 + 1,65 + 0,2 + 44 + 4 + 2,2 + 0,5 = 58.550.000 (8 mã) → 57,91% → 57,9.
	tot_ = s_["total"]
	c("XR-COMP-4 kho_slow_days = 10 / kho_dead_days = 60: chậm 10 mã 69.765.000 (69,0%), chết 8 mã 58.550.000 (57,9%); meta.settings",
		(s_["slow_days"], s_["dead_days"], tot_["slow_items"], tot_["slow_value"], tot_["slow_pct"], tot_["dead_items"], tot_["dead_value"],
		tot_["dead_pct"], ds_["meta"]["settings"]) == (10, 60, 10, 69_765_000, 69.0, 8, 58_550_000, 57.9,
		{"kho_doi_days": 30, "kho_slow_days": 10, "kho_dead_days": 60, "kho_can_date_ngay": 60}), (s_["slow_days"], s_["dead_days"], tot_))
	single("BC Settings", kho_doi_days=0, kho_slow_days=None, kho_dead_days=-5)   # 0 / trống / âm → mặc định 90 / 90 / 180
	dd_ = ov()
	c("XR-COMP-4 0 / trống / âm → mặc định: cửa sổ 90 ngày (30/07), chậm 7 mã, chết 4 mã",
		(dd_["doi"]["window_days"], dd_["doi"]["from"], dd_["slow"]["slow_days"], dd_["slow"]["dead_days"], dd_["slow"]["total"]["slow_items"],
		dd_["slow"]["total"]["dead_items"]) == (90, "2026-07-30", 90, 180, 7, 4), dd_["doi"])
	single("BC Settings", kho_doi_days=None, kho_dead_days=None)

	# ═══ PERF-1: giá vốn bán đi từ SỔ (không từ Item); ba lượt quét cả lịch sử cache theo ngày, Làm mới tính lại ═══
	# Chỉ mục THẬT của v16 (stock_ledger_entry.py on_doctype_update + search_index trong JSON; Item.item_group): có chúng thì JOIN
	# thường làm MariaDB đi từ Item rồi đọc MỌI dòng sổ của từng mã — thấy được ngay trên sổ nhỏ này (đo trên 1 triệu dòng: 25 s).
	for ddl in ("CREATE INDEX item_warehouse ON `tabStock Ledger Entry` (item_code, warehouse, posting_datetime, creation)",
			"CREATE INDEX voucher_no_voucher_type ON `tabStock Ledger Entry` (voucher_no, voucher_type)",
			"CREATE INDEX voucher_type ON `tabStock Ledger Entry` (voucher_type)",
			"CREATE INDEX item_group ON `tabItem` (item_group)"):
		frappe.db.sql(ddl)
	frappe.db.sql("ANALYZE TABLE `tabStock Ledger Entry`, `tabItem`")
	seen = []
	real_sql = frappe.db.sql

	def spy(q, *a, **kw):
		seen.append((q, a[0] if a else kw.get("values")))
		return real_sql(q, *a, **kw)

	def run_spied(fn):
		seen.clear()
		frappe.db.sql = spy
		try:
			return fn()
		finally:
			frappe.db.__dict__.pop("sql", None)

	def heavy():
		return [q for q, _ in seen if "tabStock Ledger Entry" in q or "tabSales Invoice" in q]

	run_spied(ov)
	cq = [(q, v_) for q, v_ in seen if "AS cogs" in q]
	plan = frappe.db.sql("EXPLAIN " + cq[0][0], cq[0][1], as_dict=True) if cq else []
	c("PERF-1 giá vốn bán (S4): kế hoạch đi từ sổ kho, Item tra theo khoá chính (không đi từ Item rồi đọc mọi dòng sổ của mã)",
		bool(plan) and plan[0].table == "sle" and next((r.type for r in plan if r.table == "i"), None) == "eq_ref",
		[(r.table, r.type, r.key) for r in plan])
	c("PERF-1 Làm mới (refresh=1) quét lại cả ba: giá vốn bán, lần xuất cuối, hoá đơn chưa trừ kho", len(heavy()) >= 3,
		[q[:60] for q in heavy()])
	run_spied(lambda: kho_ton.get_overview())   # cache_ttl = 0 trong bộ thử → dựng lại như khi cache overview hết hạn
	c("PERF-1 dựng lại overview trong ngày (cache cache_ttl hết hạn, không Làm mới): không quét lại sổ kho / hoá đơn", not heavy(),
		[q[:60] for q in heavy()])
	kp = km
	kp.sale("TON-TRAD3", TP, 1, 15_000, "2026-10-27", name="TON-SI-PERF")   # TRAD3 (chưa từng bán) bán HÔM NAY — chỉ sổ
	dp = kho_ton.get_overview()
	t3 = by(dp["slow"]["tp"]["top"], "item_code", "TON-TRAD3")
	c("PERF-1 trong ngày không Làm mới: giá vốn / lần xuất cuối giữ bản cache (2.050.000; TRAD3 vẫn chưa từng xuất 483 ngày)",
		dp["doi"]["traditional"]["cogs"] == 2_050_000 and t3 is not None and (t3["never"], t3["idle_days"]) == (True, 483),
		(dp["doi"]["traditional"], t3))
	dr = ov()
	# Làm mới: giá vốn 2.050.000 + 15.000 = 2.065.000 → 16.680.000 × 90 / 2.065.000 = 726,97 → 727,0 ngày; TRAD3 bán hôm nay → 0 ngày,
	# bình thường → ra khỏi danh sách chậm.
	c("PERF-1 Làm mới tính lại: giá vốn 2.065.000 → 727,0 ngày; TRAD3 xuất hôm nay rời danh sách chậm",
		(dr["doi"]["traditional"]["cogs"], dr["doi"]["traditional"]["days"]) == (2_065_000, 727.0)
		and not by(dr["slow"]["tp"]["top"], "item_code", "TON-TRAD3"), (dr["doi"]["traditional"], dr["slow"]["tp"]["top"]))
	# Mã MỚI vào phạm vi sau lượt cache (nhập từ 01/01, Bin vừa có): tính riêng ngay, không chờ hết ngày → 299 ngày, tồn chết.
	kp.item("TON-PERF-OLD", "Bánh PERF cũ", G_TRAD)
	kp.receipt("TON-PERF-OLD", NVL, 10, 10_000, "2026-01-01", name="TON-PR-PERF")
	insert("Bin", name="BIN-TON-PERF-OLD", item_code="TON-PERF-OLD", warehouse=NVL, actual_qty=10, stock_value=10_000, valuation_rate=1_000,
		company="HGC")
	po = by(kho_ton.get_overview()["slow"]["total"]["top"], "item_code", "TON-PERF-OLD")
	c("PERF-1 mã mới vào phạm vi giữa ngày: lần nhập đầu 01/01 tính ngay (299 ngày, tồn chết)",
		po is not None and (po["first_in"], po["idle_days"], po["status"]) == ("2026-01-01", 299, "dead"), po)
	for v_no in ("TON-SI-PERF", "TON-PR-PERF"):
		frappe.db.sql("DELETE FROM `tabStock Ledger Entry` WHERE voucher_no = %s", (v_no,))
	frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE name = 'TON-SI-PERF'")
	frappe.db.sql("DELETE FROM `tabPurchase Receipt` WHERE name = 'TON-PR-PERF'")
	frappe.db.sql("DELETE FROM `tabBin` WHERE name = 'BIN-TON-PERF-OLD'")
	frappe.db.sql("DELETE FROM `tabItem` WHERE name = 'TON-PERF-OLD'")
	ov()   # Làm mới: cache theo ngày về sổ sạch cho các phần sau

	# ═══ Quyền ═══
	frappe.session.user = "nobody@example.com"
	try:
		for fn in (kho_ton.get_overview, kho_ton.get_trend):
			try:
				fn(refresh=1)
				c(f"người không có quyền bị chặn ({fn.__name__})", False)
			except frappe.PermissionError:
				c(f"người không có quyền bị chặn ({fn.__name__})", True)
	finally:
		frappe.session.user = "viewer@example.com"

	# ═══ Giai đoạn Tết (đặc tả ERP §5.2 — mặc định mùa sx 01/10 → 30/04; bộ thử chung đặt 8 → 2) ═══
	frappe.db.set_single_value("BC Settings", "sx_season_start_month", 10)
	frappe.db.set_single_value("BC Settings", "sx_season_end_month", 4)
	import datetime
	table = {"2026-04-20": "sau_mua", "2026-06-15": "sau_mua", "2026-09-30": "sau_mua", "2026-10-01": "chuan_bi",
		"2026-10-27": "chuan_bi", "2026-11-01": "ban", "2027-02-06": "ban", "2027-02-07": "sau_mua", "2027-03-01": "sau_mua"}
	got = {k_: kho_ton.tet_phase(datetime.date.fromisoformat(k_)) for k_ in table}
	c("giai đoạn Tết đúng bảng đặc tả (20/04 là sau mùa — không dùng sx_season)", got == table, {k_: v_ for k_, v_ in got.items() if v_ != table[k_]})
	frappe.utils.FAKE_TODAY = datetime.date(2026, 11, 15)
	try:
		d2 = ov()
		o2 = d2["doi"]
		# 15/11: cửa sổ 18/08–15/11; Tết giá vốn 2.500.000 (SI 05/10) → 20.000.000 / (2.500.000/90) = 720,0 ngày.
		# Truyền thống: 600.000 − 30.000 + 400.000 + 80.000 = 1.050.000 (RV 10/10 không tính) → 16.680.000 × 90 / 1.050.000 = 1.429,7.
		c("15/11 (mùa bán): Tết DOI 720 ngày, nhãn 'đang bán'", (o2["tet"]["phase"], o2["tet"]["applicable"], o2["tet"]["cogs"], o2["tet"]["days"],
			d2["tet_stock"]["label"]) == ("ban", True, 2_500_000, 720.0, "Tồn hàng Tết đang bán"), o2["tet"])
		c("15/11: truyền thống 1.429,7 ngày, cửa sổ 18/08", (o2["from"], o2["traditional"]["cogs"], o2["traditional"]["days"])
			== ("2026-08-18", 1_050_000, 1429.7), o2)
	finally:
		frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 27)
	frappe.db.sql("DELETE FROM `tabBC Tet Date`")
	d3 = ov()
	c("thiếu ngày Tết: giai đoạn None, trang vẫn chạy", (d3["doi"]["tet"]["phase"], d3["doi"]["tet"]["days"], d3["tet_stock"]["phase"],
		d3["tet_stock"]["label"], d3["doi"]["traditional"]["days"]) == (None, None, None, "Tồn hàng Tết", 732.3), d3["doi"]["tet"])

	# ═══ Lệch cấu hình sx: công ty, kho TP ═══
	frappe.db.set_single_value("SX Settings", "cong_ty", "RV")
	frappe.db.set_single_value("SX Settings", "kho_tp", KHO_CU)
	d4 = ov()
	h4, v4 = d4["health"], d4["value"]
	c("health: SX Settings khác công ty / kho TP khác BC Settings", (h4["company_mismatch"], h4["sx_company"], h4["kho_tp_mismatch"],
		h4["kho_tp_sx"]) == (True, "RV", True, KHO_CU), h4)
	c("kho TP lệch: vai trò TP = _wh() ∪ kho_tp (34.260.000 + Kho cũ 150.000); dòng Kho thành phẩm vẫn = màn Thời gian thực, khác tập kho",
		(by(v4["by_role"], "key", "tp")["value"], v4["kho_tp"]["value"], v4["kho_tp"]["same"], by(v4["by_role"], "key", "khac")["value"])
		== (34_410_000, 34_260_000, False, 0), (by(v4["by_role"], "key", "tp"), v4["kho_tp"]))
	frappe.db.set_single_value("SX Settings", "cong_ty", "HGC")
	frappe.db.set_single_value("SX Settings", "kho_tp", TP)

	# ═══ Thiếu nhóm "Hàng Tết" (đặc tả ERP §11) ═══
	frappe.db.set_single_value("BC Settings", "tet_item_group", "TON-Nhóm không có")
	dn = ov()
	gn = {x["key"]: x["value"] for x in dn["value"]["by_group"]}
	c("thiếu nhóm Tết: groups_found.tet = False, hàng Tết rơi vào nhóm khác (64.570.000 + 21.000.000), tổng giữ nguyên",
		(dn["meta"]["groups_found"], gn["tet"], gn["traditional"], gn["other"], dn["value"]["totals"]["value"],
		dn["health"]["group_has_children"]["tet"]) == ({"tet": False, "traditional": True}, 0, 16_810_000, 85_570_000, 102_380_000, False),
		(dn["meta"].get("groups_found"), gn))
	frappe.db.set_single_value("BC Settings", "tet_item_group", "Hàng Tết")

	# ═══ Sổ lệch Bin ═══
	frappe.db.sql("UPDATE `tabBin` SET stock_value = stock_value + 1000 WHERE item_code = 'TON-NL1' AND warehouse = %s", (NVL,))
	c("Bin lệch sổ 1.000 → ledger_bin_diff = −1.000", tr()["trend"]["ledger_bin_diff"] == -1000)

	# ═══ Dòng chỉ còn giá trị ở Kho thành phẩm (live bỏ dòng số lượng 0) + dòng 0,7 đ (dưới ngưỡng 1 đ của health) ═══
	insert("Bin", name="BIN-TON-STR1", item_code="TON-TRAD4", warehouse=TP, actual_qty=0, stock_value=7, valuation_rate=0, company="HGC")
	insert("Bin", name="BIN-TON-STR2", item_code="TON-TRAD4", warehouse=CH2, actual_qty=0, stock_value=0.7, valuation_rate=0,
		company="HGC")
	ds = ov()
	vs, hs = ds["value"], ds["health"]
	ks = vs["kho_tp"]
	c("dòng chỉ còn 7 đ ở Kho TP: khu vực TP 34.260.007 = live 34.260.000 + 7; cùng tập kho → không báo lệch cài đặt",
		(by(vs["by_role"], "key", "tp")["value"], ks["value"], ks.get("role_stranded_value"), ks["same"])
		== (34_260_007, 34_260_000, 7, True) and ks["role_value"] - ks.get("role_stranded_value", 0) == ks["value"], ks)
	c("ngưỡng dòng chỉ còn giá trị: 7 đ tính (3 dòng, 15.007), 0,7 đ vào tổng nhưng không tính là dòng lệch",
		(hs["stranded_value_rows"], hs["stranded_value"], vs["totals"]["value"]) == (3, 15_007, 102_381_007.7), (hs, vs["totals"]))
	frappe.db.sql("DELETE FROM `tabBin` WHERE name IN ('BIN-TON-STR1', 'BIN-TON-STR2')")

	# ═══ Thiếu bảng / cột cho từng mục health ═══
	drop_doctype("Repost Item Valuation")
	drop_doctype("POS Invoice")
	frappe.db.sql("DELETE FROM `tabDocType` WHERE name = 'Stock Settings'")
	drop_column("Sales Invoice Item", "delivered_qty")
	h5 = ov()["health"]
	c("health thiếu bảng tính lại giá / POS / Stock Settings / cột delivered_qty: chỉ bỏ các mục đó",
		h5["available"] and not ({"pending_reposts", "pos_unconsolidated", "allow_negative_stock", "si_no_stock_relief"} & set(h5))
		and h5["stranded_value_rows"] == 2 and h5["items_without_carton_factor"] == 1, h5)
	drop_doctype("Stock Entry")  # lỗi giữa chừng: chỉ khối dùng phiếu kho tắt
	d6 = ov()
	c("một khối lỗi (thiếu bảng Stock Entry) không làm hỏng cả trang", d6["slow"] == {"available": False, "error": True}
		and d6["value"]["available"] and d6["doi"]["available"] and d6["value"]["totals"]["value"] == 102_381_000, d6["slow"])
	T6 = tr()
	c("trend lỗi → hai khối trend/nxt tắt, method vẫn trả", T6["available"] and T6["trend"].get("available") is False
		and T6["nxt"].get("available") is False)

	# ═══ Site không cài sx ═══
	main_seed(sx=False)
	frappe.INSTALLED_APPS.remove("sx")
	drop_column("Stock Entry", "custom_kiem_ke")
	drop_column("Item", "custom_sx_nhom")
	try:
		d7, T7 = ov(), tr()
		v7 = d7["value"]
		role7 = {r["key"]: r["value"] for r in v7["by_role"]}
		# Không SX Settings: trả về / cách ly / xưởng / BTP / NVL / kho cũ đều là "Kho khác" (bán được); TP = _wh().
		c("không sx: tổng như cũ, không có kho 'không bán được', sản xuất gộp vào kho khác",
			(v7["totals"]["value"], v7["totals"]["value_unsellable"], role7["tp"], role7["khong_ban"], role7["san_xuat"], role7["khac"])
			== (102_380_000, 0, 34_260_000, 0, 0, 62_770_000 + 1_280_000 + 150_000), role7)
		kb7 = by(v7["by_role"], "key", "khong_ban")
		c("UX-11c không sx: chưa xác định kho trả về / cách ly (configured False) — màn hiện '—', không phải 0",
			(kb7.get("configured"), [x.get("configured") for x in kb7["roles"]]) == (False, [False, False]), kb7)
		c("không sx: tập TP theo cây nhóm (TPK sang vật tư), không cột custom_sx_nhom → nhóm khác một dòng",
			(v7["tp"]["source"], v7["sx_nhom"], [x["value"] for x in v7["other_split"] if x["value"]]) == ("nhom", False, [64_570_000]), v7["tp"])
		s7 = d7["slow"]
		# BB1: không còn cột custom_kiem_ke → Repack 15/10 tính là dùng (11 → 12 ngày); dọn tồn 16/10 vẫn loại (remarks) → 12 ngày.
		bb = [x for x in s7["vat_tu"]["top"] if x["item_code"] == "TON-BB1"]
		c("không sx: kiểm kê sx không còn nhận ra → BB1 hết chậm; TPK nằm ở vật tư", not bb and by(s7["vat_tu"]["top"], "item_code", "TON-TPK")
			and s7["tp_source"] == "nhom", s7["vat_tu"]["top"])
		h7 = d7["health"]
		c("không sx: không mục lệch công ty / kho TP; tập TP không so", "company_mismatch" not in h7 and "kho_tp_mismatch" not in h7
			and h7["tp_set_mismatch"]["in_sx_not_group"] is None, h7)
		c("không sx: Kho thành phẩm = cây _wh() → cùng tập kho", v7["kho_tp"]["same"] is True and v7["kho_tp"]["value"] == 34_260_000, v7["kho_tp"])
		f9 = by(T7["nxt"]["months"], "month", "2026-09")["groups"]["all"]["flows"]
		c("không sx: phiếu kiểm kê sx thành nhập khác (09/2026), đẳng thức vẫn đúng", (f9["kiem_ke_sx"], f9["nhap_khac"]) == (0, 50_000)
			and T7["trend"]["ledger_bin_diff"] == 0 and T7["trend"]["points"][-1]["value"] == 99_880_000, f9)
	finally:
		frappe.INSTALLED_APPS.append("sx")

	# ═══ Site trống / chưa có công ty ═══
	reset()
	bc_settings()
	frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'Global Defaults'")
	c("chưa khai công ty → available False (không 500)", ov()["available"] is False and tr()["available"] is False)
	k0 = K()
	base(k0)
	k0.finalize()
	d8, T8 = ov(), tr()
	c("site chưa có sổ kho: mọi khối có, số 0, % không chia cho 0", d8["available"] and d8["value"]["totals"]["value"] == 0
		and d8["slow"]["total"]["items"] == 0 and d8["slow"]["total"]["slow_pct"] is None
		and d8["doi"]["traditional"]["days"] is None and d8["tet_stock"]["qty"] is None and T8["trend"]["points"][-1]["value"] == 0
		and len(T8["nxt"]["months"]) == 13, (d8["value"].get("totals"), d8["slow"].get("total")))

	# ═══ Đơn vị "đóng thùng": MỘT luật cho thẻ / nhóm hàng / tồn Tết và dải sức khoẻ (XR-COMP-1 / NUM-1, phần còn lại) ═══
	# Trên base trống (k0): Hộp có mã khai thùng (YA 20 hộp / thùng), Kg không mã thành phẩm nào khai thùng. Trước sửa: dải
	# sức khoẻ bỏ Kg (luật cả tập thành phẩm) nhưng thẻ tồn Tết / dòng nhóm (khối CHỈ có Kg → "đơn vị duy nhất" xét theo
	# từng khối) vẫn hiện "0 thùng + 208 kg chưa khai quy cách thùng" — cùng một mã, hai kết luận trên một màn.
	k0.item("TON-YA", "Bánh YA", G_TRAD, carton=20, custom_sx_nhom="TP")          # Hộp, 20 hộp / thùng
	k0.item("TON-YH", "Bánh YH", G_TRAD, custom_sx_nhom="TP")                     # Hộp, chưa khai thùng
	k0.item("TON-YK", "Kẹo cân YK", G_TET, uom="Kg", custom_sx_nhom="TP")         # Kg, thành phẩm, không đóng thùng
	k0.item("TON-YC", "Hộp giấy YC", G_BB, uom="Cái", custom_sx_nhom="Bao Bi")    # Cái, bao bì (nhóm khác) — đơn vị không có ở thành phẩm
	for n, it, wh, q, val in (("BIN-TON-YA", "TON-YA", TP, 40, 400_000), ("BIN-TON-YH1", "TON-YH", TP, 6, 60_000),
			("BIN-TON-YH2", "TON-YH", DI_DUONG, 4, 40_000), ("BIN-TON-YK1", "TON-YK", TP, 180, 1_800_000),
			("BIN-TON-YK2", "TON-YK", CH1, 28, 280_000), ("BIN-TON-YC", "TON-YC", NVL, 50, 50_000)):
		insert("Bin", name=n, item_code=it, warehouse=wh, actual_qty=q, stock_value=val, valuation_rate=val / q, company="HGC")
	frappe.local.__dict__.pop("sx_nho", None)
	dy = ov()
	vy, hy, ty = dy["value"], dy["health"], dy["tet_stock"]
	gy = {x["key"]: x for x in vy["by_group"]}
	ck = ("cartons", "boxes_without_carton_factor", "items_without_carton_factor", "boxes_without_carton_in_stock",
		"items_without_carton_in_stock")
	# Thành phẩm còn hàng ở kho bán được: YA 40 hộp (có thùng), YH 6 + 4 (đi đường) = 10 hộp, YK 180 + 28 (cửa hàng) = 208 kg.
	# Hai đơn vị; Hộp có YA khai thùng → đóng thùng; Kg không mã nào khai → không. Sức khoẻ: 1 mã (YH), 10 hộp.
	c("đơn vị đóng thùng — sức khoẻ: 1 mã chưa khai thùng, 10 hộp; bỏ Kg",
		(hy["items_without_carton_factor"], hy["boxes_without_carton_factor"], hy.get("uom_without_carton_factor"),
		hy.get("without_carton_by_uom")) == (1, 10, "Hộp", [{"uom": "Hộp", "items": 1, "qty": 10}]),
		{k_: hy.get(k_) for k_ in ("items_without_carton_factor", "boxes_without_carton_factor", "without_carton_by_uom")})
	# Tồn Tết (kho bán được) = YK 208 kg, 1.800.000 + 280.000 = 2.080.000 → số lượng có, KHÔNG thùng / "chưa khai" (Kg không
	# đóng thùng — như sức khoẻ). Trước sửa: thùng 0,0 + 208 kg chưa khai.
	c("XR-COMP-1/NUM-1 tồn Tết chỉ Kg (Hộp đóng thùng ở nhóm khác): 208 kg, 2.080.000, không thùng / không 'chưa khai' — như sức khoẻ",
		(ty["qty"], ty["uom"], ty["value"], ty["items"]) == (208, "Kg", 2_080_000, 1) and all(ty[x] is None for x in ck),
		{x: ty.get(x) for x in ("qty", "uom", "value", "items") + ck})
	# Nhóm Tết (mọi kho) = cùng 208 kg → không thùng. Nhóm khác = YC 50 cái bao bì: không mã thành phẩm nào tính theo cái →
	# không đóng thùng → không thùng (trước sửa: khối chỉ một đơn vị → "0 thùng + 50 cái chưa khai quy cách thùng").
	c("XR-COMP-1 nhóm Tết 208 kg + nhóm khác 50 cái (bao bì): số lượng có, không thùng / không 'chưa khai'",
		(gy["tet"]["qty"], gy["tet"]["uom"], gy["other"]["qty"], gy["other"]["uom"]) == (208, "Kg", 50, "Cái")
		and all(gy[g][x] is None for g in ("tet", "other") for x in ck), {g: {x: gy[g].get(x) for x in ("qty", "uom") + ck}
		for g in ("tet", "other")})
	# Nhóm truyền thống (Hộp, đóng thùng) giữ nguyên: 40 + 10 = 50 hộp, 40 / 20 = 2,0 thùng, YH 10 hộp chưa khai (1 mã), 500.000.
	tr_y = gy["traditional"]
	c("nhóm truyền thống (Hộp đóng thùng) vẫn tính: 50 hộp, 2,0 thùng, 10 hộp chưa khai (1 mã), 500.000",
		(tr_y["qty"], tr_y["uom"], tr_y["cartons"], tr_y["boxes_without_carton_in_stock"], tr_y["items_without_carton_in_stock"],
		tr_y["value"]) == (50, "Hộp", 2.0, 10, 1, 500_000), tr_y)
	# Còn MỘT đơn vị thành phẩm (bỏ YA, YH): Kg là đơn vị duy nhất → vẫn nhắc (site chưa khai thùng cho mã nào) ở CẢ sức khoẻ,
	# thẻ thành phẩm và tồn Tết: 208 kg, 1 mã; thùng 0,0.
	frappe.db.sql("DELETE FROM `tabBin` WHERE item_code IN %(x)s", {"x": ("TON-YA", "TON-YH")})
	frappe.local.__dict__.pop("sx_nho", None)
	dz = ov()
	hz, tz, pz = dz["health"], dz["tet_stock"], dz["value"]["tp"]
	c("đơn vị duy nhất (Kg) vẫn nhắc ở cả sức khoẻ, thẻ thành phẩm và tồn Tết: 208 kg, 1 mã, 0,0 thùng",
		(hz["items_without_carton_factor"], hz["boxes_without_carton_factor"], hz.get("uom_without_carton_factor"))
		== (1, 208, "Kg") and (tz["cartons"], tz["boxes_without_carton_in_stock"], tz["items_without_carton_in_stock"])
		== (0.0, 208, 1) and (pz["qty"], pz["uom"], pz["cartons"], pz["boxes_without_carton_in_stock"],
		pz["items_without_carton_in_stock"]) == (208, "Kg", 0.0, 208, 1), (hz, tz, pz))
	c.done()
