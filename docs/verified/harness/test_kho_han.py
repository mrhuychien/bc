"""Hạn dùng & tồn âm (bc.api.kho_han: K6 hạn dùng, K7 không bán được, K8 tồn âm) trên MariaDB thật.

Hôm nay 27/10/2026, cận date mặc định 60 ngày. Số kỳ vọng TÍNH TAY từ seed() bên dưới (phép tính ghi ở chú thích).
Mọi mã / lô / chứng từ bắt đầu bằng HAN- (seed gộp được với các bộ thử Kho khác — seed_ui_kho.py).

Bẫy có ca riêng: lô hết hạn HÔM NAY (không tính hết hạn), biên 30/31/60/61/90/91 ngày, lô bundle (v15+) và lô ghi
SLE.batch_no (dữ liệu cũ), một phiếu xuất nhiều lô, phiếu huỷ, phiếu ghi ngày TƯƠNG LAI (tính như Bin), gói lô POS chưa
lên sổ, lô ở kho không bán được / kho công ty khác, phần chưa gắn lô +5 và −3, lô âm −2, mã TP không quản lý lô (có
phiếu kiểm kê không lô actual_qty = 0), mã đã tắt lô còn dòng lô cũ, lô TONCU và '-TONCU-2' (có ngày tạo — vẫn KHÔNG ước tính), lô chưa ghi HSD có HSD ước tính (NSX trước ngày tạo; đã quá
— vẫn KHÔNG vào hết hạn; ước tính đúng hôm nay chưa tính là qua), lô thu hồi → K7(b) (cả lô thu hồi của mã đã tắt lô:
KHÔNG vào K7(b)), một lô ở nhiều kho bán được (đếm MỘT lô), cùng mã khác giá vốn theo kho (giá trị từng dòng theo
Bin của đúng kho), lô dương ở kho giá vốn 0, nhóm con của Hàng Tết, mã ngừng dùng, mã bị ẩn (có ở MỌI danh sách:
hết hạn, trả về, thu hồi, tồn âm — bỏ khỏi danh sách, vẫn vào tổng), mã ngoài tập TP, giá vốn dự phòng đủ 5 nấc chỉ
trong công ty (công ty khác giữ cùng mã với Bin tồn lớn hơn / dòng sổ mới hơn giá cao hơn — không được dùng), dòng âm
ở kho cách ly / kho đi đường / kho công ty khác, tuổi hàng kho trả về / cách ly (bỏ phiếu xuất, phiếu huỷ, phiếu ghi
ngày sau), am_value không công bố (C8), nhãn 3 phần theo kho (không "kho bán"). Ảnh chụp Bin + lô (PERF-2): một lần đọc sổ
lô cho tập TP + một lần chỉ cho mã thu hồi ngoài tập TP, kho.rates một lần, cache riêng 3600 giây khoá theo hôm nay, trang
hết cache trong giờ dùng lại ảnh chụp, phiếu mới sau lúc chụp không làm lệch "chưa gắn lô", Làm mới chụp lại, tắt cache
thì không giữ. Tuổi kho trả về / cách ly sau kiểm kê (seed_tuoi — XR-T1): kiểm kê có lô hai chân đếm thiếu / khớp, chuyển
lô TONCU D191, phiếu dọn tồn, tồn đầu kỳ có lô / không lô, nhập thật sau kiểm kê. Các kịch bản phụ: N = 45 / N không hợp
lệ, tập TP theo sx.utils.items_tp, site không có sx (kho trả về = is_rejected_warehouse), thiếu cột thu hồi, DB rỗng, chưa
có công ty, một khối lỗi, quyền / mảng ẩn, cache, riêng tư, helper sx cấm import.
Sổ cho các lượt kiểm giao diện phụ (BC_TEST_DB=<db> python3 -B test_kho_han.py <lệnh>, rồi node ui_kho_han.mjs <url> <lượt>):
seed-empty (sổ rỗng → lượt empty), seed-thu-hoi (chỉ còn lô thu hồi + phần âm → lượt thu-hoi), seed-cache (bật cache trên
sổ đang có, không reset → lượt cache: giờ chụp số theo lô).
"""
import ast
import datetime
import json
import os
import re
import sys

from seed import Check, bc_settings, drop_column, insert, reset, single
from seed_kho import (BTP, CACH_LY, CH1, CH2, DI_DUONG, G_BB, G_NL, G_QUA_TET, G_TRAD, K, KHO_CU, NVL, RV, TP, TRA_VE,
	XUONG, base, bin_of)
from paths import BC_ROOT

import frappe

A, B, C, D, E, F, G, H, KK, NL, X, S = ("HAN-A", "HAN-B", "HAN-C", "HAN-D", "HAN-E", "HAN-F", "HAN-G", "HAN-H",
	"HAN-K", "HAN-NL", "HAN-X", "HAN-S")
P = "HAN-P"
SECRETS = ["kho.han@example.com", "qa.han@example.com", "admin.han@example.com", "GHI CHÚ RIÊNG HAN-KHO",
	"LÝ DO THU HỒI RIÊNG HAN", "GHI CHÚ ẨN RIÊNG HAN"]
DENY = ("_dong_du", "ma_lo_ton_cu", "prefix_lo", "gia_von_hien", "ghi_gia_tu_tinh")


def seed(k):
	"""Kịch bản HAN- trên cây kho chung (base(k) đã gọi; KHÔNG finalize). Phần lớn mã một đơn giá ở mọi kho → Bin.
	valuation_rate = đơn giá (A 10k, B 50k, C 8k, D 12k, E 7k, F 9k, H 11k, K 20k, NL 30k/kg). Riêng HAN-P giá vốn KHÁC
	theo kho (TP 10k, CH Bạch Đằng 20k, đi đường 0, công ty RV 99k) để kiểm giá trị lô = số lượng × Bin của ĐÚNG kho."""
	insert("SX San Pham Cong Bo", name="HAN-CB", han_dung_thang=9)
	# Mã TP đánh dấu Nhóm SX = TP như sx (items_tp) — cùng tập với cây nhóm Tết ∪ truyền thống (kịch bản phụ kiểm cả hai).
	tp = {"custom_sx_nhom": "TP"}
	k.item(A, "Bánh đậu xanh Rồng Vàng HAN A", G_TRAD, carton=20, batch=True, custom_sp_cong_bo="HAN-CB", **tp)
	k.item(B, "Hộp quà Tết HAN B", G_QUA_TET, carton=10, batch=True, **tp)  # nhóm CON của Hàng Tết
	k.item(C, "Bánh không lô HAN C", G_TRAD, carton=24, **tp)               # TP không quản lý lô
	k.item(D, "Bánh HAN D", G_TRAD, batch=True, shelf_life_in_days=180, **tp)  # không khai thùng
	k.item(E, "Bánh tắt lô HAN E", G_TRAD, carton=10, **tp)                 # đã tắt lô, còn dòng lô cũ trên sổ
	k.item(F, "Bánh ngừng HAN F", G_TRAD, carton=20, batch=True, disabled=1, **tp)
	k.item(G, "Bánh xưởng HAN G", G_TRAD, rate=15_000, **tp)                # chỉ có giá ở Item
	k.item(H, "Bánh ẩn HAN H", G_TRAD, carton=20, batch=True, **tp)         # admin ẩn khỏi danh sách
	k.item(KK, "Bánh cửa hàng HAN K", G_TRAD, **tp)
	k.item(NL, "Bột đậu HAN NL", G_NL, uom="Kg", batch=True)                # ngoài tập TP
	k.item(X, "Thùng carton HAN X", G_BB, uom="Cái")                        # không có giá vốn nào
	k.item(P, "Bánh nhiều giá HAN P", G_TRAD, carton=4, batch=True, **tp)   # giá vốn khác nhau theo kho
	k.item(S, "Đường HAN S", G_NL, uom="Kg")                                # chỉ còn giá trên sổ kho

	for name, item, exp, mfg, kw in [
			("HAN-A-EXP", A, "2026-10-26", None, {}),        # −1 ngày → hết hạn
			("HAN-A-TODAY", A, "2026-10-27", None, {}),      # 0 → còn hạn (0–30), cận date
			("HAN-A-D30", A, "2026-11-26", None, {}),        # +30 → 0–30
			("HAN-A-D31", A, "2026-11-27", None, {}),        # +31 → 31–60
			("HAN-A-D60", A, "2026-12-26", None, {}),        # +60 → 31–60, cận date (N = 60)
			("HAN-A-D61", A, "2026-12-27", None, {}),        # +61 → 61–90, KHÔNG cận date
			("HAN-A-D90", A, "2027-01-25", None, {}),        # +90 → 61–90
			("HAN-A-D91", A, "2027-01-26", None, {}),        # +91 → trên 90
			# TONCU có ngày tạo như site thật (01/02 + 9 tháng = 01/11 nếu lỡ ước tính) — KHÔNG bao giờ ước tính (T6).
			("HAN-A-TONCU", A, None, None, {"description": "Tồn KHÔNG LÔ chưa rõ HSD", "creation": "2026-02-01 10:00:00"}),
			# NSX TRƯỚC ngày tạo (§3.2 COALESCE(NSX, ngày tạo)): 31/12/2025 + 9 tháng = 30/09/2026 (đã qua!); nếu lấy ngày tạo
			# 15/08/2026 + 9 tháng = 15/05/2027.
			("HAN-A-NOHSD", A, None, "2025-12-31", {"creation": "2026-08-15 10:00:00"}),
			("HAN-A-NEG", A, "2027-05-15", None, {}),
			("HAN-A-RECALL", A, "2027-02-04", None, {"custom_thu_hoi": 1, "custom_ly_do_thu_hoi": "LÝ DO THU HỒI RIÊNG HAN",
				"custom_thu_hoi_boi": "qa.han@example.com"}),   # +100 ngày, đang thu hồi
			("HAN-A-RECALL2", A, "2027-02-04", None, {"custom_thu_hoi": 1}),
			("HAN-B-L1", B, "2026-12-01", None, {}),         # +35
			("HAN-B-L2", B, "2026-10-20", None, {}),         # −7
			("HAN-B-NEGQ", B, "2026-12-16", None, {}),
			("HAN-D-L1", D, "2026-11-10", None, {}),         # +14
			("HAN-D-NOHSD", D, None, None, {"creation": "2026-06-01 10:00:00"}),  # ước tính 01/06 + 180 ngày = 28/11/2026
			("HAN-D-NOHSD2", D, None, None, {"creation": "2026-04-30 10:00:00"}),  # 30/04 + 180 ngày = 27/10 = HÔM NAY: chưa qua
			# '{prefix}-TONCU-2' (sx thêm -2 khi tên trùng mã khác); D có hạn dùng 180 ngày → nếu lỡ ước tính: 28/08/2026 (đã qua).
			("HAN-D-TONCU-2", D, None, None, {"creation": "2026-03-01 10:00:00", "description": "Tồn KHÔNG LÔ chưa rõ HSD"}),
			("HAN-E-R", E, "2027-01-01", None, {"custom_thu_hoi": 1}),  # lô thu hồi của mã ĐÃ TẮT lô → không vào K7(b)
			("HAN-E-OLD", E, "2026-01-01", None, {}),        # lô cũ của mã đã tắt lô — đã quá hạn nhưng KHÔNG tính
			("HAN-F-L1", F, "2026-11-15", None, {}),         # +19
			("HAN-H-L1", H, "2026-10-01", None, {}),         # −26
			("HAN-H-R", H, "2027-03-01", None, {"custom_thu_hoi": 1}),  # mã ẩn, đang thu hồi, ở hai kho bán
			("HAN-H-NOHSD", H, None, None, {}),              # mã ẩn, lô chưa ghi HSD (danh sách chưa rõ HSD)
			("HAN-P-L1", P, "2026-11-06", None, {}),         # +10, ở BA kho bán được (một lô)
			("HAN-NL-L1", NL, "2026-09-01", None, {}),       # −56 nhưng không phải TP
			("HAN-NL-R", NL, "2027-03-01", None, {"custom_thu_hoi": 1})]:
		k.batch(name, item, exp, mfg, **kw)

	def mr(name, date, rows, **kw):
		return k.se("Material Receipt", date, [dict(item_code=i, t_warehouse=w, qty=q, rate=r, batch=b) for i, w, q, r, b in rows],
			name=name, **kw)

	def mi(name, date, rows):
		return k.se("Material Issue", date, [dict(item_code=i, s_warehouse=w, qty=q, rate=r, batch=b) for i, w, q, r, b in rows],
			name=name)

	# ── HAN-A (10.000 đ/hộp) ──
	mr("HAN-SE-01", "2026-08-20", [(A, TP, 30, 10_000, "HAN-A-EXP"), (A, CACH_LY, 9, 10_000, "HAN-A-EXP")],
		remarks="GHI CHÚ RIÊNG HAN-KHO", owner="kho.han@example.com")
	mr("HAN-SE-02", "2026-09-01", [(A, TP, 40, 10_000, "HAN-A-TODAY")])
	insert("Purchase Receipt", name="HAN-PR-01", docstatus=1, posting_date="2026-09-01", company=k.company)
	k.sle(A, TP, 15, 150_000, "2026-09-01", "Purchase Receipt", "HAN-PR-01", "08:00:00", batch="HAN-A-D31", bundle=False)
	k.sle(A, TP, 7, 70_000, "2026-09-01", "Purchase Receipt", "HAN-PR-01", "08:00:00", batch="HAN-A-NOHSD", bundle=False)
	mr("HAN-SE-03", "2026-09-01", [(A, TP, 25, 10_000, "HAN-A-D61"), (A, TP, 100, 10_000, "HAN-A-D91"),
		(A, TP, 25, 10_000, "HAN-A-D30")])
	k.se("Material Transfer", "2026-09-05", [dict(item_code=A, s_warehouse=TP, t_warehouse=CH1, qty=25, rate=10_000,
		batch="HAN-A-D30")], name="HAN-SE-04")
	mr("HAN-SE-05", "2026-09-10", [(A, DI_DUONG, 12, 10_000, "HAN-A-D60"), (A, KHO_CU, 8, 10_000, "HAN-A-D90"),
		(A, CH2, 63, 10_000, "HAN-A-TONCU"), (A, CH1, 18, 10_000, "HAN-A-RECALL"), (A, TRA_VE, 6, 10_000, "HAN-A-RECALL2")])
	mr("HAN-SE-06", "2026-09-12", [(A, TP, 5, 10_000, None)])                # chưa gắn lô ở TP: +5
	mr("HAN-SE-07", "2026-10-01", [(A, TRA_VE, 2, 10_000, None)])            # chưa gắn lô ở kho trả về: +2
	# Tuổi hàng ở kho trả về = lần NHẬP gần nhất ≤ hôm nay (01/10): phiếu XUẤT 20/10 và phiếu nhập ghi ngày 02/11 không tính
	# (Bin vẫn 6 + 2 − 1 + 1 = 8). Phiếu nhập đã HUỶ 25/10 vào kho cách ly không tính (tuổi A@cách ly vẫn từ 20/08).
	mi("HAN-SE-26", "2026-10-20", [(A, TRA_VE, 1, 10_000, None)])
	mr("HAN-SE-27", "2026-11-02", [(A, TRA_VE, 1, 10_000, None)])
	k.se("Material Receipt", "2026-10-25", [dict(item_code=A, t_warehouse=CACH_LY, qty=5, rate=10_000)], name="HAN-SE-28",
		docstatus=2)
	insert("Sales Invoice", name="HAN-SINV-01", docstatus=1, posting_date="2026-10-10", company=k.company, is_return=0,
		update_stock=1)
	k.sle(A, TP, -35, -350_000, "2026-10-10", "Sales Invoice", "HAN-SINV-01", "10:00:00",
		lots=[("HAN-A-D91", -30), ("HAN-A-D61", -5)])                        # MỘT dòng sổ, hai lô
	k.sale(A, TP, 5, 50_000, "2026-10-12", name="HAN-SINV-02", cancelled=1, batch="HAN-A-D91")  # đã huỷ
	k.sale(A, TP, 2, 20_000, "2026-10-15", name="HAN-SINV-03", batch="HAN-A-NEG")             # lô âm −2
	k.sale(A, CH1, 3, 30_000, "2026-10-16", name="HAN-SINV-04")                               # bán không lô: −3
	mr("HAN-SE-08", "2026-11-05", [(A, TP, 10, 10_000, "HAN-A-D91")])        # ghi ngày TƯƠNG LAI — Bin có tính
	mr("HAN-SE-09", "2026-09-01", [(A, RV, 50, 10_000, "HAN-A-D91")])        # kho công ty khác
	insert("POS Invoice", name="HAN-POS-01", docstatus=1, posting_date="2026-10-26", company=k.company)
	insert("Serial and Batch Bundle", name="HAN-SBB-POS", item_code=A, warehouse=TP, voucher_type="POS Invoice",
		voucher_no="HAN-POS-01", docstatus=1, is_cancelled=0, type_of_transaction="Outward", has_batch_no=1)
	insert("Serial and Batch Entry", name="HAN-SBE-POS", parent="HAN-SBB-POS", parenttype="Serial and Batch Bundle",
		parentfield="entries", idx=1, batch_no="HAN-A-D91", qty=-7, warehouse=TP, item_code=A, is_outward=1)  # chưa lên sổ
	# ── HAN-B (50.000) ──
	mr("HAN-SE-10", "2026-09-20", [(B, TP, 40, 50_000, "HAN-B-L1"), (B, CH2, 6, 50_000, "HAN-B-L2")])
	mi("HAN-SE-11", "2026-10-05", [(B, CACH_LY, 1, 50_000, "HAN-B-NEGQ")])  # lô âm ở kho cách ly
	# ── HAN-C (8.000, không lô) ──
	mr("HAN-SE-12", "2026-09-01", [(C, TP, 100, 8_000, None)])
	k.recon("2026-10-20", [dict(item_code=C, warehouse=TP, qty=90, current_qty=100, value_diff=-80_000)], name="HAN-RECO-01")
	k.sale(C, TP, 10, 80_000, "2026-10-22", name="HAN-SINV-05")              # TP: 100 → kiểm 90 → 80
	k.sale(C, CH1, 4, 32_000, "2026-10-23", name="HAN-SINV-06")              # CH1: −4
	k.sale(C, RV, 9, 72_000, "2026-10-23", name="HAN-SINV-07")               # công ty khác: −9
	# ── HAN-D (12.000), HAN-E (7.000), HAN-F (9.000), HAN-H (11.000) ──
	mr("HAN-SE-13", "2026-10-01", [(D, CH1, 10, 12_000, "HAN-D-L1"), (D, CH1, 3, 12_000, "HAN-D-NOHSD")])
	insert("Purchase Receipt", name="HAN-PR-02", docstatus=1, posting_date="2026-09-01", company=k.company)
	k.sle(E, TP, 20, 140_000, "2026-09-01", "Purchase Receipt", "HAN-PR-02", "08:00:00", batch="HAN-E-OLD", bundle=False)
	k.sle(E, CH2, 5, 35_000, "2026-09-01", "Purchase Receipt", "HAN-PR-02", "08:00:00", batch="HAN-E-R", bundle=False)
	mr("HAN-SE-29", "2026-10-01", [(D, CH2, 4, 12_000, "HAN-D-TONCU-2"), (D, TP, 2, 12_000, "HAN-D-NOHSD2")])
	mr("HAN-SE-14", "2026-10-02", [(F, TP, 10, 9_000, "HAN-F-L1")])
	mr("HAN-SE-15", "2026-07-01", [(H, TP, 4, 11_000, "HAN-H-L1")])
	mr("HAN-SE-30", "2026-09-15", [(H, TRA_VE, 2, 11_000, "HAN-H-L1")])      # mã ẩn ở kho trả về (K7(a))
	mr("HAN-SE-31", "2026-10-05", [(H, CH1, 3, 11_000, "HAN-H-R"), (H, TP, 1, 11_000, "HAN-H-R")])  # mã ẩn, lô thu hồi
	k.sale(H, CH2, 1, 11_000, "2026-10-21", name="HAN-SINV-10")              # mã ẩn âm −1 ở CH2 (K8)
	mr("HAN-SE-38", "2026-10-06", [(H, CH1, 2, 11_000, "HAN-H-NOHSD")])      # mã ẩn ở "chưa rõ HSD"
	# ── HAN-P: một lô +10 ngày ở 3 kho bán được với giá vốn khác nhau; âm ở CH2; công ty RV giữ 100 hộp giá 99.000 ──
	mr("HAN-SE-32", "2026-10-01", [(P, TP, 8, 10_000, "HAN-P-L1"), (P, CH1, 4, 20_000, "HAN-P-L1"),
		(P, DI_DUONG, 4, 0, "HAN-P-L1")])                                     # đi đường: Bin giá 0
	k.sale(P, CH2, 2, 20_000, "2026-10-20", name="HAN-SINV-09")              # CH2: −2, Bin giá 0
	mr("HAN-SE-33", "2026-09-01", [(P, RV, 100, 99_000, "HAN-P-L1")])        # công ty khác, Bin tồn lớn nhất
	# ── Tồn âm ──
	mi("HAN-SE-16", "2026-10-18", [(G, XUONG, 6, 0, None)])                   # TP âm ở kho xưởng, giá 0 trên sổ
	mr("HAN-SE-17", "2026-10-03", [(KK, CH2, 10, 20_000, None)])
	k.sale(KK, CH2, 12, 240_000, "2026-10-19", name="HAN-SINV-08")           # CH2: −2, Bin giữ giá 20.000
	mr("HAN-SE-18", "2026-08-01", [(NL, TP, 50, 30_000, "HAN-NL-L1"), (NL, CACH_LY, 3, 30_000, "HAN-NL-L1"),
		(NL, BTP, 4, 30_000, "HAN-NL-R")])
	mi("HAN-SE-19", "2026-10-21", [(NL, NVL, 5, 30_000, None)])              # NVL: −5
	mi("HAN-SE-20", "2026-10-22", [(X, XUONG, 3, 0, None)])                  # −3, không giá ở đâu cả
	mr("HAN-SE-21", "2026-07-01", [(S, NVL, 10, 6_000, None)])
	mi("HAN-SE-22", "2026-07-15", [(S, NVL, 10, 6_000, None)])               # dòng sổ cuối có giá 6.000
	mr("HAN-SE-23", "2026-08-01", [(S, NVL, 5, 0, None)])                    # nhập giá 0 → Bin NVL về giá 0
	mi("HAN-SE-24", "2026-08-15", [(S, NVL, 5, 0, None)])
	mi("HAN-SE-25", "2026-10-24", [(S, CH2, 2, 0, None)])                    # CH2: −2
	mi("HAN-SE-36", "2026-10-22", [(S, DI_DUONG, 1, 0, None)])               # hàng đi đường: −1 → nhóm "khác"
	# Công ty RV: dòng sổ S MỚI HƠN có giá 99.000 rồi điều chỉnh giá trị về 0 (Bin RV giá 0) — nấc "sổ kho" phải bỏ qua.
	k.se("Material Receipt", "2026-09-01", [dict(item_code=S, t_warehouse=RV, qty=1, rate=99_000)], name="HAN-SE-34")
	k.se("Material Receipt", "2026-09-02", [dict(item_code=S, t_warehouse=RV, qty=1, rate=0, value_in=-99_000)], name="HAN-SE-35")
	# Phiếu nhập S ở kho NVL (công ty) đã HUỶ, dòng sổ huỷ vẫn mang giá 50.000 như ERPNext — nấc "sổ kho" phải bỏ qua.
	k.se("Material Receipt", "2026-09-20", [dict(item_code=S, t_warehouse=NVL, qty=1, rate=50_000)], name="HAN-SE-37", docstatus=2)
	frappe.db.sql("""UPDATE `tabStock Ledger Entry` SET valuation_rate = 50000, stock_value = 50000
		WHERE voucher_no = 'HAN-SE-37' AND is_cancelled = 1""")
	insert("BC Hidden Item", name="HAN-HID-1", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items",
		idx=1, item_code=H, note="GHI CHÚ ẨN RIÊNG HAN", hidden_by="admin.han@example.com")


T1, T2, T3, T4, T5, T6, T7 = (f"HAN-T{i}" for i in range(1, 8))


def seed_tuoi(k):
	"""Tuổi hàng kho trả về / cách ly khi có KIỂM KÊ (XR-T1 / XR-REAL-2) — kịch bản riêng, gọi sau seed(k). recon() của
	seed_kho ghi mã có lô thành HAI chân như ERPNext v16 (−sổ rồi +đếm, kể cả khi đếm thiếu / khớp). Hôm nay 27/10/2026.
	Tuổi = hôm nay − lần NHẬP THẬT gần nhất (kiểm kê, phiếu điều chỉnh sx không phải nhập; tồn đầu kỳ là lần vào sổ):
	- T1 (lô) nhập TP 04/05, chuyển vào kho trả về 01/06 (nhập thật), kiểm 20/10 đếm 9/10 (THIẾU) → 01/06, 148 ngày;
	- T2 (lô) khách trả 01/07 vào kho trả về, kiểm 20/10 đếm KHỚP 5/5 (vẫn hai chân −5 / +5) → 01/07, 118 ngày;
	- T3 (vừa bật lô) nhập cách ly 01/08 không lô, sx chuyển sang lô TONCU 22/10 (xuất + nhập có custom_kiem_ke, D191)
	  → 01/08, 87 ngày;
	- T4 (không lô) nhập cách ly 01/09, phiếu "Dọn tồn âm thành phẩm" nhập +2 ngày 24/10 → 01/09, 56 ngày;
	- T5 (không lô) TỒN ĐẦU KỲ 01/03 ở cách ly (actual_qty 0, tồn sau 6) → 01/03, 240 ngày (trước: "—");
	- T6 (lô) TỒN ĐẦU KỲ 01/03 ở cách ly (chân nhập +6), kiểm 20/10 đếm 5/6 → 01/03, 240 ngày (cùng câu trả lời với T5);
	- T7 (lô) khách trả 01/06, kiểm 10/10 đếm 4/5, khách trả THÊM 2 ngày 15/10 (nhập thật SAU kiểm kê) → 15/10, 12 ngày.
	Số ngày: 01/06→27/10 = 30+31+31+30+26 = 148; 01/07→ = 31+31+30+26 = 118; 01/08→ = 31+30+26 = 87; 01/09→ = 30+26
	= 56; 01/03→ = 31+30+31+30+31+31+30+26 = 240; 15/10→27/10 = 12."""
	tp = {"custom_sx_nhom": "TP"}
	for code, name, lo in ((T1, "Bánh trả về kiểm thiếu HAN T1", True), (T2, "Bánh trả về kiểm khớp HAN T2", True),
			(T3, "Bánh vừa bật lô HAN T3", True), (T4, "Bánh dọn âm HAN T4", False), (T5, "Bánh tồn đầu không lô HAN T5", False),
			(T6, "Bánh tồn đầu có lô HAN T6", True), (T7, "Bánh trả thêm HAN T7", True)):
		k.item(code, name, G_TRAD, batch=lo, **tp)
	for b, item in (("HAN-T1-L1", T1), ("HAN-T2-L1", T2), ("HAN-T3-TONCU", T3), ("HAN-T6-L1", T6), ("HAN-T7-L1", T7)):
		k.batch(b, item, "2027-06-01")
	# T1: nhập TP 04/05 → chuyển kho trả về 01/06 → kiểm kê 20/10 đếm 9 / sổ 10 (chân −10 × 10k, +9 × 10k)
	k.se("Material Receipt", "2026-05-04", [dict(item_code=T1, t_warehouse=TP, qty=10, rate=10_000, batch="HAN-T1-L1")],
		name="HAN-SE-T1A")
	k.se("Material Transfer", "2026-06-01", [dict(item_code=T1, s_warehouse=TP, t_warehouse=TRA_VE, qty=10, rate=10_000,
		batch="HAN-T1-L1")], name="HAN-SE-T1B")
	k.recon("2026-10-20", [dict(item_code=T1, warehouse=TRA_VE, qty=9, current_qty=10, value_diff=-10_000, current_rate=10_000,
		batch="HAN-T1-L1")], name="HAN-RECO-T1")
	# T2: khách trả 5 hộp vào kho trả về 01/07 → kiểm 20/10 đếm khớp 5 (chân −5 / +5, giá trị −50k / +50k)
	k.sale(T2, TRA_VE, -5, -50_000, "2026-07-01", name="HAN-SINV-T2", batch="HAN-T2-L1", is_return=1)
	k.recon("2026-10-20", [dict(item_code=T2, warehouse=TRA_VE, qty=5, current_qty=5, value_diff=0, current_rate=10_000,
		batch="HAN-T2-L1")], name="HAN-RECO-T2")
	# T3: nhập cách ly 01/08 không lô → sx D191 (custom_kiem_ke) xuất 4 không lô + nhập 4 vào lô TONCU 22/10
	k.se("Material Receipt", "2026-08-01", [dict(item_code=T3, t_warehouse=CACH_LY, qty=4, rate=10_000)], name="HAN-SE-T3A")
	k.se("Material Issue", "2026-10-22", [dict(item_code=T3, s_warehouse=CACH_LY, qty=4, rate=10_000)], name="HAN-SE-T3B",
		kiem_ke="HAN-KK-T3")
	k.se("Material Receipt", "2026-10-22", [dict(item_code=T3, t_warehouse=CACH_LY, qty=4, rate=10_000, batch="HAN-T3-TONCU")],
		name="HAN-SE-T3C", kiem_ke="HAN-KK-T3")
	# T4: nhập cách ly 01/09 → phiếu dọn tồn âm của sx (remarks bắt đầu bằng tiền tố ADJUSTMENT_REMARKS) nhập +2 ngày 24/10
	k.se("Material Receipt", "2026-09-01", [dict(item_code=T4, t_warehouse=CACH_LY, qty=3, rate=10_000)], name="HAN-SE-T4A")
	k.se("Material Receipt", "2026-10-24", [dict(item_code=T4, t_warehouse=CACH_LY, qty=2, rate=10_000)], name="HAN-SE-T4B",
		remarks="Dọn tồn âm thành phẩm — HAN-T4")
	# T5 / T6: tồn đầu kỳ 01/03 ở cách ly (không lô: một dòng actual_qty 0; có lô: chân nhập +6); T6 kiểm 20/10 đếm 5/6
	k.recon("2026-03-01", [dict(item_code=T5, warehouse=CACH_LY, qty=6, current_qty=0, value_diff=60_000),
		dict(item_code=T6, warehouse=CACH_LY, qty=6, current_qty=0, value_diff=60_000, batch="HAN-T6-L1")],
		purpose="Opening Stock", name="HAN-RECO-T56")
	k.recon("2026-10-20", [dict(item_code=T6, warehouse=CACH_LY, qty=5, current_qty=6, value_diff=-10_000, current_rate=10_000,
		batch="HAN-T6-L1")], name="HAN-RECO-T6")
	# T7: khách trả 5 ngày 01/06 → kiểm 10/10 đếm 4/5 → khách trả thêm 2 ngày 15/10 (nhập thật)
	k.sale(T7, TRA_VE, -5, -50_000, "2026-06-01", name="HAN-SINV-T7A", batch="HAN-T7-L1", is_return=1)
	k.recon("2026-10-10", [dict(item_code=T7, warehouse=TRA_VE, qty=4, current_qty=5, value_diff=-10_000, current_rate=10_000,
		batch="HAN-T7-L1")], name="HAN-RECO-T7")
	k.sale(T7, TRA_VE, -2, -20_000, "2026-10-15", name="HAN-SINV-T7B", batch="HAN-T7-L1", is_return=1)


def seed_thu_hoi(k):
	"""Sổ RIÊNG (UX-11): thành phẩm ngoài kho trả về & cách ly chỉ còn LÔ THU HỒI và PHẦN ÂM — không có phần dương nào để
	xét hạn dùng, nhưng vẫn có tồn thành phẩm. Gọi trên base(k), KHÔNG kèm seed(k). Hôm nay 27/10/2026.
	- HAN-R1 (lô, 20 hộp/thùng): lô HAN-R1-L1 đang thu hồi (HSD 30/06/2027), nhập 10 hộp × 10.000 vào kho Thành phẩm 01/09
	  → Bin TP 10 / 100.000; lô thu hồi 10 hộp = 0,5 thùng, 100.000.
	- HAN-R2 (không lô, giá Item 12.000): bán 3 hộp ở CH Bạch Đằng 20/10 khi chưa nhập → Bin −3 / −36.000 (giá vốn Bin 0
	  → phần âm định giá theo giá Item: 3 × 12.000 = 36.000).
	Đối chiếu: 0 (các nhóm hạn dùng) + 10 (lô thu hồi) − 3 (phần âm) = 7 hộp = Bin 10 − 3; giá trị sổ 100.000 − 36.000 = 64.000."""
	tp = {"custom_sx_nhom": "TP"}
	k.item("HAN-R1", "Bánh thu hồi HAN R1", G_TRAD, carton=20, batch=True, **tp)
	k.batch("HAN-R1-L1", "HAN-R1", "2027-06-30", custom_thu_hoi=1)
	k.receipt("HAN-R1", TP, 10, 100_000, "2026-09-01", name="HAN-R-PR-1", batch="HAN-R1-L1")
	k.item("HAN-R2", "Bánh cửa hàng HAN R2", G_TRAD, rate=12_000, **tp)
	k.sale("HAN-R2", CH1, 3, 36_000, "2026-10-20", name="HAN-R-SINV-1")


def build(sx=True, extra=None, **settings):
	reset()
	bc_settings(**settings)
	k = K()
	base(k, sx=sx)
	seed(k)
	if extra:
		extra(k)
	k.finalize()
	return k


def build_empty():
	"""Sổ RỖNG có cây kho (công ty, kho, nhóm hàng, chưa có mã / phiếu) — kiểm giao diện trạng thái trống:
	BC_TEST_DB=<db> python3 -B test_kho_han.py seed-empty, rồi server.py + ui_kho_han.mjs."""
	reset()
	bc_settings()
	k = K()
	base(k)
	k.finalize()
	return k


def build_thu_hoi():
	"""Sổ chỉ còn lô thu hồi + phần âm (seed_thu_hoi), cache tắt: BC_TEST_DB=<db> python3 -B test_kho_han.py seed-thu-hoi,
	rồi server.py + node ui_kho_han.mjs <url> thu-hoi."""
	reset()
	bc_settings()
	k = K()
	base(k)
	seed_thu_hoi(k)
	k.finalize()
	return k


def run():
	frappe.local.__dict__.pop("sx_nho", None)  # nhớ-theo-request của sx — mỗi lượt gọi như một request mới
	from bc.api import kho_han
	return kho_han.get_overview(refresh=1)


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


def pick(d, *keys):
	return tuple(d.get(k) for k in keys)


if __name__ == "__main__" and sys.argv[1:] == ["seed-empty"]:
	build_empty()
	print("seeded empty kho book")
	sys.exit(0)

if __name__ == "__main__" and sys.argv[1:] == ["seed-thu-hoi"]:
	build_thu_hoi()
	print("seeded kho book: only recalled lot + negative part outside returns / quarantine")
	sys.exit(0)

if __name__ == "__main__" and sys.argv[1:] == ["seed-cache"]:
	# Bật cache trên sổ ĐANG CÓ (không reset) — lượt giao diện có ảnh chụp số theo lô (meta.lo_ttl_giay 3600, "tính lúc HH:MM"):
	# sau seed_ui_kho.py: BC_TEST_DB=<db> python3 -B test_kho_han.py seed-cache; node ui_kho_han.mjs <url> cache.
	single("BC Settings", cache_ttl=300)
	print("BC Settings cache_ttl = 300")
	sys.exit(0)

if __name__ == "__main__":
	c = Check()
	k_main = build()
	# ── Sổ seed đúng như tính tay (kiểm seed, không kiểm code) ──
	c("seed: Bin A@TP = 30+40+15+7+25+100+25−25+5−35−2+10 = 195", bin_of(A, TP) == (195.0, 1_950_000.0, 10_000.0), bin_of(A, TP))
	c("seed: Bin A@CH1 = 25+18−3 = 40; C@TP = 80; C@CH1 = −4 (giá 0); G@XUONG = −6",
		(bin_of(A, CH1)[0], bin_of(C, TP)[:2], bin_of(C, CH1), bin_of(G, XUONG)[0]) == (40.0, (80.0, 640_000.0), (-4.0, -32_000.0, 0.0), -6.0))
	c("seed: P giá vốn theo kho — TP 8 × 10k, CH1 4 × 20k, đi đường 4 × 0, CH2 −2 (giá 0), RV 100 × 99k",
		[bin_of(P, w) for w in (TP, CH1, DI_DUONG, CH2, RV)] == [(8.0, 80_000.0, 10_000.0), (4.0, 80_000.0, 20_000.0), (4.0, 0.0, 0.0),
			(-2.0, -20_000.0, 0.0), (100.0, 9_900_000.0, 99_000.0)], [bin_of(P, w) for w in (TP, CH1, DI_DUONG, CH2, RV)])
	c("seed: A@trả về 6+2−1+1 = 8 (80k); A@cách ly 9 (phiếu huỷ không vào); S@RV 2 giá 0; S@NVL 0 giá 0; H@TP 4+1 = 5; H@CH1 3+2",
		(bin_of(A, TRA_VE), bin_of(A, CACH_LY)[0], bin_of(S, RV), bin_of(S, NVL), bin_of(H, TP)[0], bin_of(H, CH1)[0])
		== ((8.0, 80_000.0, 10_000.0), 9.0, (2.0, 0.0, 0.0), (0.0, 0.0, 0.0), 5.0, 5.0))

	d = run()
	c("có dữ liệu, 3 khối", d["available"] and all(d[k_].get("available") for k_ in ("han", "khong_ban", "am")), d)
	m = d["meta"]
	c("meta: hôm nay, cận date 60, tập TP theo sx.utils.items_tp (10 mã HAN đánh dấu TP)",
		pick(m, "as_of", "can_date_ngay", "tp_nguon", "so_ma_tp", "co_cot_thu_hoi") == ("2026-10-27", 60, "sx", 10, True), m)
	c("meta: kho không bán được = trả về + cách ly", m["kho_khong_ban"] == ["Hàng trả về", "Kho cách ly"], m["kho_khong_ban"])

	# ═══ K6 ═══
	h = d["han"]
	bk = {x["key"]: x for x in h["buckets"]}
	c("đơn vị chung Hộp", h["uom"] == "Hộp", h["uom"])
	# Hết hạn: A-EXP@TP 30 (−1 ngày) + B-L2@CH2 6 (−7) + H-L1@TP 4 (−26, mã ẩn vẫn tính tổng) = 40 hộp;
	# 300.000 + 300.000 + 44.000 = 644.000; thùng 30/20 + 6/10 + 4/20 = 2,3. A-EXP@kho cách ly, H-L1@kho trả về, NL-L1
	# (không TP), lô E-OLD của mã đã tắt lô và lô ước tính đã quá (A-NOHSD) KHÔNG vào.
	c("hết hạn: 40 hộp, 644.000, 3 lô, 3 dòng, 3 mã, 2,3 thùng",
		pick(bk["het_han"], "qty", "uom", "value", "lots", "rows", "items", "cartons", "boxes_without_carton_factor")
		== (40, "Hộp", 644_000, 3, 3, 3, 2.3, 0), bk["het_han"])
	# 0–30: A-TODAY@TP 40 (hết hạn HÔM NAY vẫn còn hạn; 400k) + A-D30@CH1 25 (250k) + D-L1@CH1 10 (120k) + F-L1@TP 10
	# (mã ngừng dùng; 90k) + P-L1 ở BA kho, mỗi dòng theo Bin của ĐÚNG kho: TP 8 × 10k = 80k, CH1 4 × 20k = 80k,
	# đi đường 4 × 0 = 0 → 40+25+10+10+8+4+4 = 101 hộp; 1.020.000. Lô KHÁC NHAU: TODAY, D30, D-L1, F-L1, P-L1 = 5
	# (P-L1 một lô dù ở 3 kho); dòng lô × kho = 7. Thùng: A 65/20 = 3,25 + F 10/20 = 0,5 + P 16/4 = 4 → 7,75 → 7,8;
	# D không khai thùng: 10 hộp. Chưa có giá vốn ở kho đang giữ: P@đi đường 4 hộp (giá trị 0).
	c("0–30 ngày: 101 hộp, 1.020.000 (giá theo Bin từng kho), 5 lô / 7 dòng, 7,8 thùng + 10 hộp chưa khai, 4 hộp chưa có giá",
		pick(bk["d30"], "qty", "value", "lots", "rows", "items", "cartons", "boxes_without_carton_factor",
			"items_without_carton_factor", "qty_no_rate") == (101, 1_020_000, 5, 7, 4, 7.8, 10, 1, 4), bk["d30"])
	# 31–60: A-D31@TP 15 (lô ghi SLE.batch_no) + A-D60@Hàng đi đường 12 + B-L1@TP 40 (nhóm con Tết) = 67; 2.270.000.
	c("31–60 ngày: 67 hộp, 2.270.000, 3 lô (lô dữ liệu cũ, kho đi đường, nhóm con Tết)",
		pick(bk["d60"], "qty", "value", "lots", "cartons") == (67, 2_270_000, 3, round(27 / 20 + 40 / 10, 1)), bk["d60"])
	# 61–90: A-D61@TP 25 − 5 (phiếu bán hai lô) = 20 + A-D90@Kho cũ (ngừng dùng) 8 = 28; 280.000.
	c("61–90 ngày: 28 hộp, 280.000 (xuất nhiều lô một dòng sổ; kho ngừng dùng vẫn tính)",
		pick(bk["d90"], "qty", "value", "lots", "cartons") == (28, 280_000, 2, 1.4), bk["d90"])
	# Trên 90: A-D91@TP 100 − 30 + 10 (ghi ngày 05/11 — như Bin) = 80; phiếu huỷ −5, gói POS −7 chưa lên sổ, 50 ở kho RV,
	# lô thu hồi A-RECALL (+100 ngày) / H-R (+125 ngày) đều KHÔNG vào.
	c("trên 90 ngày: 80 hộp (gồm phiếu ngày tương lai; bỏ phiếu huỷ, gói POS, kho công ty khác, lô thu hồi)",
		pick(bk["tren90"], "qty", "value", "lots", "cartons") == (80, 800_000, 1, 4.0), bk["tren90"])
	cd = h["can_date"]
	# Cận date 0..60: 0–30 (101 hộp, 1.020.000) + A-D31 15 (150k) + A-D60 12 (120k) + B-L1 40 (2.000k) = 168 hộp;
	# 3.290.000; lô khác nhau 5 + 3 = 8; dòng 7 + 3 = 10.
	c("cận date ≤ 60 ngày: 168 hộp, 3.290.000, 8 lô / 10 dòng (lô +60 có, +61 không)",
		pick(cd, "ngay", "qty", "value", "lots", "rows") == (60, 168, 3_290_000, 8, 10), cd)
	cr = h["chua_ro"]
	parts = {p["key"]: p for p in cr["parts"]}
	# Chưa rõ HSD: TONCU A@CH2 63 (630k) + TONCU-2 D@CH2 4 (48k) + lô không HSD A-NOHSD@TP 7 (70k) + D-NOHSD@CH1 3 (36k)
	# + D-NOHSD2@TP 2 (24k) + H-NOHSD@CH1 2 (22k, mã ẩn — vào tổng) + chưa gắn lô A@TP 5 (50k) + mã không lô C@TP 80
	# (640k; 100 → kiểm kê 90 → bán 10) + E@TP 20 (140k; lô cũ của mã đã tắt lô) + E@CH2 5 (35k; lô thu hồi cũ của mã đã
	# tắt lô — vẫn là tồn của mã không lô) = 191 hộp, 1.695.000; 10 dòng, 6 lô (A-TONCU, D-TONCU-2, A-NOHSD, D-NOHSD,
	# D-NOHSD2, H-NOHSD), 5 mã (A, C, D, E, H).
	c("chưa rõ HSD: 191 hộp, 1.695.000, 10 dòng / 6 lô / 5 mã",
		pick(cr, "qty", "value", "rows", "lots", "items") == (191, 1_695_000, 10, 6, 5), cr)
	c("chưa rõ HSD tách: TONCU (gồm '-TONCU-2') 67 · lô chưa ghi HSD 14 · chưa gắn lô 5 · mã chưa quản lý lô 105",
		{k_: (p["qty"], p["value"], p["lots"]) for k_, p in parts.items()} == {"toncu": (67, 678_000, 2), "lo_khong_hsd": (14, 152_000, 4),
			"khong_lo": (5, 50_000, 0), "chua_quan_ly_lo": (105, 815_000, 0)}, parts)
	# Thùng: A 63+7+5 = 75/20 = 3,75; C 80/24 = 3,33; E 25/10 = 2,5; H 2/20 = 0,1 → 9,68 → 9,7; D 4+3+2 = 9 hộp chưa khai.
	c("chưa rõ HSD: thùng 9,7 + 9 hộp chưa khai thùng", pick(cr, "cartons", "boxes_without_carton_factor") == (9.7, 9), cr)
	# Ước tính đã qua: chỉ A-NOHSD (30/09). D-NOHSD 28/11 chưa tới; D-NOHSD2 = 27/10 = hôm nay → CHƯA qua; TONCU không ước tính.
	c("lô chưa ghi HSD có HSD ước tính đã qua: 1 (ước tính đúng hôm nay chưa tính; chỉ để hiện, không vào hết hạn)",
		cr["uoc_tinh_qua_han"] == 1, cr)
	pa = h["phan_am"]
	# Phần âm: lô A-NEG@TP −2 (Bin 10k) + chưa gắn lô A@CH1 −3 (Bin 10k) + C@CH1 −4 (Bin giá 0 → Bin khác C@TP 8k)
	# + G@XUONG −6 (Item 15k) + K@CH2 −2 (Bin 20k) + chưa gắn lô P@CH2 −2 (Bin 0 → Bin khác TRONG công ty có tồn lớn nhất
	# P@TP 8 × 10k — KHÔNG phải RV 100 × 99k) + chưa gắn lô H@CH2 −1 (Bin khác 11k) = −20 hộp;
	# −(20k + 30k + 32k + 90k + 40k + 20k + 11k) = −243.000. Số âm không quy thùng.
	c("phần âm: −20 hộp, −243.000 (giá vốn dự phòng trong công ty), 7 dòng, 1 lô, 6 mã, không quy thùng",
		pick(pa, "qty", "value", "rows", "lots", "items", "cartons", "boxes_without_carton_factor") == (-20, -243_000, 7, 1, 6, None, None), pa)
	# Lô thu hồi rút khỏi K6: A-RECALL@CH1 18 (180k) + H-R@CH1 3 (33k) + H-R@TP 1 (11k) = 22 hộp, 224.000; 2 lô, 3 dòng.
	c("lô thu hồi rút khỏi K6: 22 hộp, 224.000, 2 lô / 3 dòng", pick(h["thu_hoi"], "qty", "value", "lots", "rows") == (22, 224_000, 2, 3),
		h["thu_hoi"])
	t = h["tong"]
	# Mẫu số %: các phần DƯƠNG 40+101+67+28+80+191 = 507 hộp; 644k+1.020k+2.270k+280k+800k+1.695k = 6.709.000.
	c("tổng phần dương (mẫu số %): 507 hộp, 6.709.000, 4 hộp chưa có giá", pick(t, "qty", "value", "qty_no_rate") == (507, 6_709_000, 4), t)
	c("% giá trị: hết hạn 644/6709 = 9,6; cận date 3290/6709 = 49,0; chưa rõ 1695/6709 = 25,3; trên 90 800/6709 = 11,9",
		(bk["het_han"]["pct"], cd["pct"], cr["pct"], bk["tren90"]["pct"]) == (9.6, 49.0, 25.3, 11.9),
		(bk["het_han"]["pct"], cd["pct"], cr["pct"], bk["tren90"]["pct"]))
	dc = h["doi_chieu"]
	# Bin TP ở kho bán được: A 195+40+63+12+8 = 318; B 40+6 = 46; C 80−4 = 76; D 13+4+2 = 19; E 20+5 = 25; F 10;
	# H 5+5−1 = 9; G −6; K −2; P 8+4+4−2 = 14 → 509. Phần dương 507 + thu hồi 22 + phần âm −20 = 509 → lệch 0.
	# Giá trị Bin: A 3.180k + B 2.300k + C 608k + D 228k + E 175k + F 90k + H 99k + G 0 + K −40k + P 140k = 6.780.000.
	c("đối chiếu: phần dương 507 + thu hồi 22 + phần âm (−20) = Σ Bin TP ở kho bán được 509, khớp",
		pick(dc, "ton_kho_qty", "cac_phan_qty", "thu_hoi_qty", "khop") == (509, 487, 22, True)
		and dc["theo_dvt"] == [{"uom": "Hộp", "ton_kho": 509, "duong": 507, "am": -20, "cac_phan": 487, "thu_hoi": 22, "lech": 0}], dc)
	c("đối chiếu: giá trị tồn TP theo sổ 6.780.000", dc["ton_kho_value"] == 6_780_000, dc["ton_kho_value"])

	exp_can = [  # (mã, lô, kho, HSD, còn ngày, hộp, thùng, giá trị) — H-L1 bị ẩn; còn ngày tăng dần, rồi giá trị giảm, rồi kho
		(B, "HAN-B-L2", "CH Tuệ Tĩnh", "2026-10-20", -7, 6, 0.6, 300_000),
		(A, "HAN-A-EXP", "Thành phẩm", "2026-10-26", -1, 30, 1.5, 300_000),
		(A, "HAN-A-TODAY", "Thành phẩm", "2026-10-27", 0, 40, 2.0, 400_000),
		(P, "HAN-P-L1", "CH Bạch Đằng", "2026-11-06", 10, 4, 1.0, 80_000),    # 4 × 20k (Bin CH1)
		(P, "HAN-P-L1", "Thành phẩm", "2026-11-06", 10, 8, 2.0, 80_000),      # 8 × 10k (Bin TP)
		(P, "HAN-P-L1", "Hàng đi đường", "2026-11-06", 10, 4, 1.0, 0),        # Bin giá 0
		(D, "HAN-D-L1", "CH Bạch Đằng", "2026-11-10", 14, 10, None, 120_000),
		(F, "HAN-F-L1", "Thành phẩm", "2026-11-15", 19, 10, 0.5, 90_000),
		(A, "HAN-A-D30", "CH Bạch Đằng", "2026-11-26", 30, 25, 1.25, 250_000),
		(A, "HAN-A-D31", "Thành phẩm", "2026-11-27", 31, 15, 0.75, 150_000),
		(B, "HAN-B-L1", "Thành phẩm", "2026-12-01", 35, 40, 4.0, 2_000_000),
		(A, "HAN-A-D60", "Hàng đi đường", "2026-12-26", 60, 12, 0.6, 120_000)]
	got = [pick(r, "item_code", "lo", "kho", "hsd", "con_ngay", "qty", "cartons", "value") for r in h["lo_can_date"]]
	c("danh sách lô hết hạn / cận date: đúng 12 dòng, đúng thứ tự, giá trị theo Bin từng kho, mã ẩn bị bỏ",
		got == exp_can and h["lo_can_date_tong"] == 12, got)
	c("danh sách lô: cờ hết hạn + tên rút gọn", [r["het_han"] for r in h["lo_can_date"][:3]] == [True, True, False]
		and by(h["lo_can_date"], "lo", "HAN-A-TODAY")["short_name"] == "Rồng Vàng HAN A", h["lo_can_date"][:3])
	exp_cr = [(C, "chua_quan_ly_lo", None, "Thành phẩm", 80, 640_000, None),
		(A, "toncu", "HAN-A-TONCU", "CH Tuệ Tĩnh", 63, 630_000, None),             # có ngày tạo — vẫn KHÔNG ước tính
		(E, "chua_quan_ly_lo", None, "Thành phẩm", 20, 140_000, None),
		(A, "lo_khong_hsd", "HAN-A-NOHSD", "Thành phẩm", 7, 70_000, "2026-09-30"),  # NSX 31/12/2025 + 9 tháng (kẹp 30/9)
		(A, "khong_lo", None, "Thành phẩm", 5, 50_000, None),
		(D, "toncu", "HAN-D-TONCU-2", "CH Tuệ Tĩnh", 4, 48_000, None),
		(D, "lo_khong_hsd", "HAN-D-NOHSD", "CH Bạch Đằng", 3, 36_000, "2026-11-28"),  # tạo 01/06 + 180 ngày
		(E, "chua_quan_ly_lo", None, "CH Tuệ Tĩnh", 5, 35_000, None),
		(D, "lo_khong_hsd", "HAN-D-NOHSD2", "Thành phẩm", 2, 24_000, "2026-10-27")]  # tạo 30/04 + 180 ngày = hôm nay
	got = [pick(r, "item_code", "loai", "lo", "kho", "qty", "value", "hsd_uoc_tinh") for r in h["chua_ro_ds"]]
	c("danh sách chưa rõ HSD: giá trị giảm dần, HSD ước tính chỉ để hiện (TONCU / TONCU-2 không ước tính), mã ẩn bị bỏ",
		got == exp_cr and h["chua_ro_ds_tong"] == 9, got)

	# ═══ K7 ═══
	kb = d["khong_ban"]
	roles = {r["role"]: r for r in kb["kho_loai"]["roles"]}
	# (a) Hàng trả về: A 8 (80k) + H 2 (22k, mã ẩn — vào tổng) = 102.000. Cách ly: A 9 (90k) + NL 3 kg (90k) + B −1 (−50k)
	# = 130.000. Tổng 232.000.
	c("(a) kho trả về 102.000 (gồm mã ẩn), cách ly 130.000 (gồm dòng âm như tổng tồn), tổng 232.000",
		pick(roles["tra_ve"], "value", "rows", "items", "am_rows") == (102_000, 2, 2, 0)
		and pick(roles["cach_ly"], "value", "rows", "items", "am_rows") == (130_000, 3, 2, 1)
		and kb["kho_loai"]["value"] == 232_000, kb["kho_loai"]["roles"])
	# XR-COMP-5: dòng âm B@cách ly (Bin −1, stock_value −50.000) chỉ được ĐẾM (am_rows 1) — không công bố Bin.stock_value
	# của dòng âm (đặc tả C8 / W9: giá trị phần âm chỉ là |qty| × giá vốn dự phòng, ở K8 = 1 × 50.000).
	c("(a) vai trò không trả giá trị Bin của dòng âm (am_value) — chỉ số dòng âm",
		not [r["role"] for r in kb["kho_loai"]["roles"] if "am_value" in r], kb["kho_loai"]["roles"])
	# UX-3: nhãn theo KHO, không "kho bán" — (b), (c) tính ở mọi kho ngoài trả về & cách ly (gồm BTP: NL-R ở kho BTP).
	c("3 phần của tồn không bán được: nhãn theo kho, không nói 'kho bán'",
		[p["label"] for p in kb["parts"]] == ["Kho trả về & cách ly", "Lô đang thu hồi ngoài kho trả về & cách ly",
			"Thành phẩm hết hạn ngoài kho trả về & cách ly"] and not [p for p in kb["parts"] if "kho bán" in p["label"]],
		[p["label"] for p in kb["parts"]])
	got = [pick(r, "item_code", "kho", "qty", "value", "nhap_cuoi", "tuoi_ngay") for r in kb["kho_loai"]["ds"]]
	# Tuổi = hôm nay − lần NHẬP sống gần nhất ≤ hôm nay: A@cách ly 20/08 (phiếu huỷ 25/10 bỏ) → 68 ngày; NL@cách ly 01/08 → 87;
	# A@trả về 01/10 (bỏ phiếu xuất 20/10 và phiếu ghi ngày 02/11 — không thành −6 ngày) → 26. H@trả về bị ẩn.
	c("(a) danh sách: dòng dương, tuổi từ lần nhập sống gần nhất ≤ hôm nay, mã ẩn bị bỏ",
		got == [(A, "Kho cách ly", 9, 90_000, "2026-08-20", 68), (NL, "Kho cách ly", 3, 90_000, "2026-08-01", 87),
			(A, "Hàng trả về", 8, 80_000, "2026-10-01", 26)] and kb["kho_loai"]["ds_tong"] == 3, got)
	th = kb["thu_hoi"]
	# (b) A-RECALL@CH1 18 hộp (180k) + H-R@CH1 3 (33k) + H-R@TP 1 (11k) + NL-R@BTP 4 kg (120k) = 344.000; 4 dòng, 3 lô khác
	# nhau, 3 mã. A-RECALL2 ở kho trả về KHÔNG tính (đã ở (a)); E-R (mã đã tắt lô) KHÔNG tính (đã ở K6 "mã chưa quản lý lô").
	c("(b) lô đang thu hồi ở kho bán: 344.000, 3 lô / 4 dòng, số lượng không cộng Hộp + Kg",
		pick(th, "available", "value", "lots", "rows", "items", "qty", "uom") == (True, 344_000, 3, 4, 3, None, None), th)
	c("(b) danh sách lô thu hồi (mã ẩn bị bỏ)", [pick(r, "item_code", "lo", "kho", "qty", "value", "hsd") for r in th["ds"]]
		== [(A, "HAN-A-RECALL", "CH Bạch Đằng", 18, 180_000, "2027-02-04"), (NL, "HAN-NL-R", "Bán thành phẩm", 4, 120_000, "2027-03-01")]
		and th["ds_tong"] == 2, th["ds"])
	c("(c) = phần hết hạn của K6 (644.000, 40 hộp, 3 lô)", pick(kb["het_han"], "value", "qty", "lots") == (644_000, 40, 3), kb["het_han"])
	c("tồn không bán được = 232.000 + 344.000 + 644.000 = 1.220.000, đủ 3 phần, không phần nào lỗi",
		kb["tong"] == 1_220_000 and kb["day_du"] and [p.get("error") for p in kb["parts"]] == [False, False, False], (kb["tong"], kb["parts"]))

	# ═══ K8 ═══
	am = d["am"]
	# Dòng Bin âm của công ty: C@CH1 −4, G@XUONG −6, K@CH2 −2, B@CACH_LY −1, NL@NVL −5, X@XUONG −3, S@CH2 −2,
	# S@đi đường −1, P@CH2 −2, H@CH2 −1 (C@RV bỏ) → 10 dòng, 9 mã, 6 kho. |âm| × giá dự phòng TRONG công ty:
	# C 4×8k (Bin khác) + G 6×15k (Item) + K 2×20k (Bin) + B 1×50k (Bin khác) + NL 5×30k (Bin khác) + X 0 (chưa có giá vốn)
	# + S 2×6k + 1×6k (sổ kho: dòng SỐNG gần nhất ở kho CÔNG TY 15/07 giá 6.000 — dòng RV 01/09 giá 99.000 và dòng
	# huỷ 20/09 giá 50.000 bỏ)
	# + P 2×10k (Bin khác: P@TP tồn 8 > P@CH1 tồn 4; P@RV 100 × 99k là công ty khác) + H 1×11k (Bin khác)
	# = 32k + 90k + 40k + 50k + 150k + 0 + 18k + 20k + 11k = 411.000.
	c("tồn âm: 10 dòng, 9 mã, 6 kho, |giá trị| 411.000, 1 dòng chưa có giá vốn",
		pick(am, "rows", "items", "warehouses", "value_abs", "no_rate_rows") == (10, 9, 6, 411_000, 1), am)
	c("giá vốn dự phòng đủ 5 nấc", am["nguon_gia"] == {"bin": 1, "bin_khac": 5, "so_kho": 2, "item": 1, "khong": 1}, am["nguon_gia"])
	sp = {x["key"]: pick(x, "rows", "items", "value_abs") for x in am["split"]}
	# TP ở kho xưởng: G 90k. Cửa hàng: C 32k + K 40k + S 12k + P 20k + H 11k = 115k. Khác: B 50k + NL 150k + X 0
	# + S@đi đường 6k (kho đi đường KHÔNG phải cửa hàng) = 206k.
	c("tách: TP ở kho xưởng (G 90k) · cửa hàng (C, K, S, P, H 115k) · khác (B, NL, X, S@đi đường 206k)",
		sp == {"tp_xuong": (1, 1, 90_000), "cua_hang": (5, 5, 115_000), "khac": (4, 4, 206_000)}, sp)
	got = [pick(r, "item_code", "kho", "qty", "rate", "value_abs", "co_gia_von") for r in am["ds"]]
	c("danh sách tồn âm: |giá trị| giảm dần, giá trong công ty, mã ẩn bị bỏ, dòng chưa có giá vốn cuối", got == [
		(NL, "Kho NVL", -5, 30_000, 150_000, True), (G, "Kho Xưởng", -6, 15_000, 90_000, True), (B, "Kho cách ly", -1, 50_000, 50_000, True),
		(KK, "CH Tuệ Tĩnh", -2, 20_000, 40_000, True), (C, "CH Bạch Đằng", -4, 8_000, 32_000, True),
		(P, "CH Tuệ Tĩnh", -2, 10_000, 20_000, True), (S, "CH Tuệ Tĩnh", -2, 6_000, 12_000, True),
		(S, "Hàng đi đường", -1, 6_000, 6_000, True), (X, "Kho Xưởng", -3, 0, 0, False)] and am["ds_tong"] == 9, got)
	# Mức lô (mã TP quản lý lô A, B, D, F, H, P — mọi kho công ty): lô âm A-NEG@TP, B-NEGQ@cách ly; chưa gắn lô A@TP +5,
	# A@trả về +2 (8 − 6), A@CH1 −3, H@CH2 −1, P@CH2 −2.
	c("mức lô: 2 lô âm; 5 (mã, kho) còn tồn chưa gắn lô (2 dương, 3 âm)",
		am["lo"] == {"lo_am": 2, "lo_am_items": 2, "khong_lo": 5, "khong_lo_duong": 2, "khong_lo_am": 3}, am["lo"])

	c("cờ cho phép xuất âm (Stock Settings) chưa bật", am["cho_phep_am"] == {"kho": False, "lo": False}, am["cho_phep_am"])
	single("Stock Settings", allow_negative_stock=1)
	c("cờ cho phép xuất âm: bật kho, lô vẫn tắt", run()["am"]["cho_phep_am"] == {"kho": True, "lo": False})
	single("Stock Settings", allow_negative_stock=0)

	# ═══ Mã ẩn: có trong MỌI danh sách của seed nhưng bị bỏ khỏi danh sách; vẫn vào tổng (kiểm ở trên) ═══
	lists = {"lô hết hạn / cận date": h["lo_can_date"], "chưa rõ HSD": h["chua_ro_ds"], "kho trả về / cách ly": kb["kho_loai"]["ds"],
		"lô thu hồi": th["ds"], "tồn âm": am["ds"]}
	c("mã ẩn không có trong danh sách nào", not [n for n, rows in lists.items() if any(r["item_code"] == H for r in rows)],
		[n for n, rows in lists.items() if any(r["item_code"] == H for r in rows)])

	# ═══ Riêng tư + helper cấm ═══
	dump = json.dumps(d, ensure_ascii=False, default=str)
	c("riêng tư: không lộ email, ghi chú, lý do thu hồi", "@" not in dump and not [s for s in SECRETS if s in dump],
		[s for s in SECRETS if s in dump])
	keys = set(re.findall(r'"([a-z_]+)":', dump))
	c("riêng tư: không có khoá owner / nguoi_* / ghi_chu / ly_do / xu_ly_boi",
		not [k_ for k_ in keys if k_ in ("owner", "ghi_chu", "ly_do", "xu_ly_boi", "remarks", "description")
			or k_.startswith("nguoi_") or "thu_hoi_boi" in k_], keys)
	src = open(os.path.join(BC_ROOT, "bc", "api", "kho_han.py"), encoding="utf-8").read()
	c("không dùng helper sx có ghi DB / giá mua", not [x for x in DENY if x in src], [x for x in DENY if x in src])
	tree = ast.parse(src)
	imps = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
		[a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
	c("không import module của app khác (chỉ bc / frappe)", all(x.split(".")[0] in ("bc", "frappe", "__future__") for x in imps), imps)
	c("SQL: không CURDATE / NOW / LIKE '%'", not re.search(r"CURDATE|NOW\(\)|LIKE\s+'%", src))
	fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_overview")
	body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
	c("get_overview gọi _guard('han-dung') đầu tiên", ast.unparse(body[0]) == "_guard('han-dung')", ast.unparse(body[0]))

	# ═══ Quyền, mảng ẩn, cache ═══
	from bc.api import kho_han
	frappe.session.user = "nobody@example.com"
	try:
		kho_han.get_overview(refresh=1)
		c("người không có quyền bị chặn", False)
	except frappe.PermissionError:
		c("người không có quyền bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="han-dung")
	try:
		kho_han.get_overview(refresh=0)
		c("mảng đang ẩn: người xem bị chặn (cả khi có cache)", False)
	except frappe.PermissionError:
		c("mảng đang ẩn: người xem bị chặn (cả khi có cache)", True)
	frappe.session.user = "Administrator"
	try:
		c("mảng đang ẩn: quản trị vẫn xem", run()["han"]["available"])
	finally:
		frappe.session.user = "viewer@example.com"
	single("BC Settings", hidden_sections="", cache_ttl=300)
	frappe.cache().store.clear()
	d1 = kho_han.get_overview()
	d2 = kho_han.get_overview()
	c("cache: lần hai lấy từ cache, cùng số", d1["meta"]["cached"] is False and d2["meta"]["cached"] is True
		and d2["han"]["tong"] == d1["han"]["tong"])
	single("BC Settings", kho_can_date_ngay=45)
	d3 = kho_han.get_overview()
	# N = 45: bỏ A-D60 (+60): 168 − 12 = 156 hộp; 3.290.000 − 120.000 = 3.170.000; 7 lô; danh sách 12 − 1 = 11 dòng.
	c("đổi số ngày cận date → khoá cache mới; N = 45: 156 hộp, 3.170.000, 7 lô",
		d3["meta"]["cached"] is False and pick(d3["han"]["can_date"], "ngay", "qty", "value", "lots") == (45, 156, 3_170_000, 7)
		and d3["han"]["lo_can_date_tong"] == 11, d3["han"]["can_date"])
	for bad in (0, -5):
		single("BC Settings", kho_can_date_ngay=bad, cache_ttl=0)
		c(f"số ngày cận date không hợp lệ ({bad}) → 60", run()["han"]["can_date"]["ngay"] == 60)
	single("BC Settings", kho_can_date_ngay="")

	# ═══ PERF-2: ảnh chụp Bin + lô cache riêng ≤ 1 giờ (khoá theo hôm nay); K7(b) dùng lại lô đã đọc; giá vốn dự phòng
	# một lần mỗi lượt ═══
	from bc.api import kho as kho_mod
	cache = frappe.cache()
	spy = {"lot": [], "rates": [], "ttl": {}}
	o_lot, o_rates, o_today, o_set = kho_mod.lot_rows, kho_mod.rates, kho_mod.today, cache.set_value

	def lot_spy(items, whs):
		items = list(items)
		spy["lot"].append(sorted(set(items)))
		return o_lot(items, whs)

	def rates_spy(pairs, co=None):
		pairs = list(pairs)
		spy["rates"].append(set(pairs))
		return o_rates(pairs, co)

	def set_spy(key, value, expires_in_sec=None, **kw):
		spy["ttl"][key] = expires_in_sec
		return o_set(key, value, expires_in_sec=expires_in_sec, **kw)

	def lo_keys():
		return [k_ for k_ in cache.store if k_.startswith("bc:kho_han.lo:")]

	def calls_reset():
		spy["lot"].clear()
		spy["rates"].clear()

	TP_LO = [A, B, D, F, H, P]   # mã TP quản lý lô (C, E, G, K không lô; NL ngoài tập TP)
	kho_mod.lot_rows, kho_mod.rates, cache.set_value = lot_spy, rates_spy, set_spy
	try:
		single("BC Settings", cache_ttl=300, kho_can_date_ngay="")
		cache.store.clear()
		calls_reset()
		pa = run()   # Làm mới (refresh=1): chụp lại
		# Sổ lô đọc 2 lần: một lần cho cả tập mã TP có lô (ảnh chụp — K6, K7(b) phần mã TP, K8 mức lô), một lần CHỈ cho mã thu
		# hồi ngoài tập đó (NL — lô NL-R ở kho BTP). Trước: lần hai đọc lại cả A, H (lô thu hồi của mã TP) {A, H, NL}.
		c("lô: một lần đọc sổ cho tập mã TP có lô + một lần chỉ cho mã thu hồi ngoài tập TP (NL), không đọc lại A, H",
			spy["lot"] == [TP_LO, [NL]], spy["lot"])
		# Giá vốn dự phòng: K6 phần âm (A-NEG@TP, chưa gắn lô A@CH1 / P@CH2 / H@CH2, C@CH1, G@xưởng, K@CH2) ∪ K8 dòng Bin âm
		# (C@CH1, G@xưởng, K@CH2, B@cách ly, NL@NVL, X@xưởng, S@CH2, S@đi đường, P@CH2, H@CH2) = 7 + 10 − 5 trùng = 12 cặp.
		want = {(A, TP), (A, CH1), (C, CH1), (G, XUONG), (KK, CH2), (P, CH2), (H, CH2), (B, CACH_LY), (NL, NVL), (X, XUONG),
			(S, CH2), (S, DI_DUONG)}
		c("giá vốn dự phòng: MỘT lần gọi kho.rates cho hợp 12 cặp của K6 và K8", spy["rates"] == [want],
			[sorted(x) for x in spy["rates"]])
		pkey = [k_ for k_ in spy["ttl"] if k_.startswith("bc:kho_han.get_overview:")]
		c("ảnh chụp lô cache RIÊNG 3600 giây (trang 300 giây)", len(lo_keys()) == 1 and spy["ttl"].get(lo_keys()[0]) == 3600
			and len(pkey) == 1 and spy["ttl"][pkey[0]] == 300, (lo_keys(), spy["ttl"]))
		c("meta: thời điểm chụp lô, chụp mới (không từ cache), giữ 3600 giây",
			pa["meta"].get("lo_luc") and pa["meta"].get("lo_tu_cache") is False and pa["meta"].get("lo_ttl_giay") == 3600,
			pa["meta"])

		# Hết hạn cache TRANG (5 phút) mà chưa quá giờ: N = 45 → khoá trang mới, ảnh chụp dùng lại — không quét sổ lô của tập
		# TP; chỉ còn lần đọc nhỏ cho NL. Nhóm hạn dùng y hệt lượt chụp.
		single("BC Settings", kho_can_date_ngay=45)
		calls_reset()
		pb = kho_han.get_overview()
		c("trang hết cache trong giờ: dùng lại ảnh chụp (không đọc sổ lô tập TP), cùng thời điểm chụp, cùng nhóm hạn dùng",
			pb["meta"]["cached"] is False and spy["lot"] == [[NL]] and pb["meta"].get("lo_tu_cache") is True
			and pb["meta"].get("lo_luc") == pa["meta"]["lo_luc"] and pb["han"]["buckets"] == pa["han"]["buckets"],
			(spy["lot"], pb["meta"]))

		# Phiếu MỚI sau lúc chụp: bán 5 hộp lô A-D91 ở TP (Bin A@TP 195 → 190). Trong giờ, K6 vẫn là ảnh chụp — Bin và lô CÙNG
		# thời điểm: trên 90 ngày 80 hộp / 800.000, chưa gắn lô A@TP vẫn +5 (Bin 195 − Σ lô 190), khớp tồn kho 509. Nếu chỉ lô
		# lấy từ cache mà Bin mới: chưa gắn lô = 190 − 190 = 0 (mất 5 hộp giả). Không ảnh chụp: trên 90 = 75 ngay.
		k_main.sale(A, TP, 5, 50_000, "2026-10-26", name="HAN-SINV-90", batch="HAN-A-D91")
		frappe.db.sql("""UPDATE `tabBin` SET actual_qty = actual_qty - 5, stock_value = stock_value - 50000
			WHERE item_code = %s AND warehouse = %s""", (A, TP))
		single("BC Settings", kho_can_date_ngay=44)
		pc = kho_han.get_overview()
		bkc = {x["key"]: x for x in pc["han"]["buckets"]}
		khl = {x["key"]: x for x in pc["han"]["chua_ro"]["parts"]}["khong_lo"]
		c("phiếu sau lúc chụp: trong giờ K6 vẫn đúng ảnh chụp (trên 90: 80 hộp / 800.000; chưa gắn lô 5; khớp tồn kho 509)",
			pick(bkc["tren90"], "qty", "value") == (80, 800_000) and pick(khl, "qty", "value") == (5, 50_000)
			and pick(pc["han"]["doi_chieu"], "ton_kho_qty", "khop") == (509, True) and pc["meta"].get("lo_tu_cache") is True,
			(bkc["tren90"], khl, pc["han"]["doi_chieu"]))
		calls_reset()
		pd = run()   # Làm mới: chụp lại → 80 − 5 = 75 hộp / 750.000; chưa gắn lô vẫn 5; tồn kho 509 − 5 = 504
		bkd = {x["key"]: x for x in pd["han"]["buckets"]}
		khd = {x["key"]: x for x in pd["han"]["chua_ro"]["parts"]}["khong_lo"]
		c("Làm mới: chụp lại ngay (đọc sổ lô tập TP) → trên 90 = 75 hộp / 750.000, chưa gắn lô 5, khớp tồn kho 504",
			spy["lot"][:1] == [TP_LO] and pick(bkd["tren90"], "qty", "value") == (75, 750_000) and pick(khd, "qty") == (5,)
			and pick(pd["han"]["doi_chieu"], "ton_kho_qty", "khop") == (504, True) and pd["meta"].get("lo_tu_cache") is False,
			(spy["lot"], bkd["tren90"], khd, pd["han"]["doi_chieu"]))

		# Sang ngày mới: khoá có hôm nay → chụp lại dù chưa hết giờ.
		kho_mod.today = lambda: datetime.date(2026, 10, 28)
		calls_reset()
		pe = kho_han.get_overview()
		c("ngày mới (28/10): ảnh chụp hôm qua không dùng — đọc lại sổ lô", spy["lot"][:1] == [TP_LO]
			and pe["meta"].get("lo_tu_cache") is False and len(lo_keys()) == 2, (spy["lot"], lo_keys()))
		kho_mod.today = o_today

		# Tắt cache (cache_ttl = 0): không giữ ảnh chụp.
		single("BC Settings", cache_ttl=0, kho_can_date_ngay="")
		cache.store.clear()
		pf = kho_han.get_overview()
		c("tắt cache (cache_ttl 0): không giữ ảnh chụp lô", not lo_keys() and pf["meta"].get("lo_ttl_giay") == 0
			and pf["meta"].get("lo_tu_cache") is False, (lo_keys(), pf["meta"]))
	finally:
		kho_mod.lot_rows, kho_mod.rates, kho_mod.today = o_lot, o_rates, o_today
		cache.set_value = o_set
	# Gỡ phiếu bán thử để các ca sau dùng đúng seed.
	frappe.db.sql("""DELETE FROM `tabSerial and Batch Entry` WHERE parent IN
		(SELECT name FROM `tabSerial and Batch Bundle` WHERE voucher_no = 'HAN-SINV-90')""")
	for t_ in ("Serial and Batch Bundle", "Stock Ledger Entry"):
		frappe.db.sql(f"DELETE FROM `tab{t_}` WHERE voucher_no = 'HAN-SINV-90'")
	frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE name = 'HAN-SINV-90'")
	frappe.db.sql("UPDATE `tabBin` SET actual_qty = 195, stock_value = 1950000 WHERE item_code = %s AND warehouse = %s", (A, TP))
	cache.store.clear()
	c("gỡ phiếu thử: Bin A@TP về 195 / 1.950.000", bin_of(A, TP) == (195.0, 1_950_000.0, 10_000.0), bin_of(A, TP))

	# ═══ Tập TP: sx chưa đánh dấu mã nào → dự phòng cây nhóm Tết ∪ truyền thống (cùng 10 mã → cùng số) ═══
	TPS = (A, B, C, D, E, F, G, H, KK, P)
	frappe.db.sql("UPDATE `tabItem` SET custom_sx_nhom = NULL WHERE name IN %s", (TPS,))
	d4 = run()
	bk4 = {x["key"]: x for x in d4["han"]["buckets"]}
	c("sx chưa đánh dấu mã TP: dự phòng theo cây nhóm (gồm nhóm con Hộp quà Tết) — cùng số",
		pick(d4["meta"], "tp_nguon", "so_ma_tp") == ("nhom", 10) and pick(bk4["het_han"], "qty", "value") == (40, 644_000)
		and d4["han"]["tong"]["value"] == 6_709_000 and d4["han"]["doi_chieu"]["ton_kho_qty"] == 509, (d4["meta"], bk4["het_han"]))
	# ═══ Tập TP theo sx (items_tp): chỉ mã đánh dấu custom_sx_nhom = 'TP' — A (truyền thống) và NL (nhóm Nguyên liệu) ═══
	frappe.db.sql("UPDATE `tabItem` SET custom_sx_nhom = 'TP' WHERE name IN %s", ((A, NL),))
	d5 = run()
	h5 = d5["han"]
	bk5 = {x["key"]: x for x in h5["buckets"]}
	# TP = {A, NL}. Hết hạn: A-EXP@TP 30 hộp (300k) + NL-L1@TP 50 kg (1.500k) = 1.800.000, hai đơn vị → không cộng số lượng,
	# không có tổng thùng chung; từng đơn vị: 30 Hộp = 1,5 thùng; 50 Kg (không mã Kg nào khai thùng → không quy thùng).
	c("tập TP theo sx: hết hạn 1.800.000 gồm NL (Kg); không cộng Hộp + Kg; số lượng / thùng theo từng đơn vị",
		d5["meta"]["tp_nguon"] == "sx" and pick(bk5["het_han"], "value", "qty", "uom", "lots", "boxes_without_carton_factor", "cartons")
		== (1_800_000, None, None, 2, None, None) and h5["uom"] is None and bk5["het_han"]["theo_dvt"] == [
			{"uom": "Hộp", "qty": 30, "items": 1, "cartons": 1.5, "boxes_without_carton_factor": 0, "items_without_carton_factor": 0,
				"qty_no_rate": 0},
			{"uom": "Kg", "qty": 50, "items": 1, "cartons": None, "boxes_without_carton_factor": None, "items_without_carton_factor": None,
				"qty_no_rate": 0}], (d5["meta"].get("tp_nguon"), bk5["het_han"]))
	# 0–30 chỉ có A (A-TODAY@TP 40 + A-D30@CH1 25 = 65 hộp; 65/20 = 3,25 → 3,2 thùng) → phần này CÓ số lượng dù tập TP lẫn Kg.
	c("tập TP lẫn đơn vị: phần chỉ có Hộp vẫn có số lượng / thùng (65 Hộp, 3,2 thùng)",
		pick(bk5["d30"], "qty", "uom", "cartons", "boxes_without_carton_factor") == (65, "Hộp", 3.2, 0), bk5["d30"])
	# Phần âm: A-NEG −2 + A@CH1 −3 = −5 Hộp; NL@NVL −5 Kg → không cộng, không quy thùng.
	c("tập TP lẫn đơn vị: phần âm −5 Hộp và −5 Kg riêng, không quy thùng",
		h5["phan_am"]["qty"] is None and h5["phan_am"]["cartons"] is None
		and [pick(x, "uom", "qty", "cartons") for x in h5["phan_am"]["theo_dvt"]] == [("Hộp", -5, None), ("Kg", -5, None)], h5["phan_am"])
	# Đối chiếu theo đơn vị: Hộp A 318 = dương 305 + thu hồi 18 + âm −5; Kg NL: Bin 50 (TP) + 4 (BTP) − 5 (NVL) = 49
	# = dương 50 + thu hồi 4 + âm −5.
	c("tập TP theo sx: đối chiếu từng đơn vị vẫn khớp", h5["doi_chieu"]["khop"] and h5["doi_chieu"]["theo_dvt"] == [
		{"uom": "Hộp", "ton_kho": 318, "duong": 305, "am": -5, "cac_phan": 300, "thu_hoi": 18, "lech": 0},
		{"uom": "Kg", "ton_kho": 49, "duong": 50, "am": -5, "cac_phan": 45, "thu_hoi": 4, "lech": 0}], h5["doi_chieu"])
	c("tập TP theo sx: G không còn là TP → tồn âm ở xưởng sang 'khác'; mức lô: 1 lô âm, 4 chưa gắn lô (thêm NL@NVL −5)",
		by(d5["am"]["split"], "key", "tp_xuong")["rows"] == 0 and pick(d5["am"]["lo"], "lo_am", "khong_lo", "khong_lo_am") == (1, 4, 2),
		(d5["am"]["split"], d5["am"]["lo"]))
	frappe.db.sql("UPDATE `tabItem` SET custom_sx_nhom = NULL WHERE name = %s", (NL,))
	frappe.db.sql("UPDATE `tabItem` SET custom_sx_nhom = 'TP' WHERE name IN %s", (TPS,))

	# ═══ Thiếu cột thu hồi (sx chưa migrate) ═══
	drop_column("Batch", "custom_thu_hoi")
	d6 = run()
	bk6 = {x["key"]: x for x in d6["han"]["buckets"]}
	# A-RECALL (+100 ngày) và H-R (+125 ngày) thành lô thường: trên 90 = 80 + 18 + 3 + 1 = 102 hộp, 800k + 180k + 33k + 11k
	# = 1.024.000; 3 lô (A-D91, A-RECALL, H-R), 4 dòng. K7 = 232.000 + 644.000 (thiếu (b)) = 876.000.
	c("thiếu cột thu hồi: lô đó về trên 90 ngày (102 hộp); K7(b) báo 'chưa có cột' (không phải lỗi); tổng K7 = 876.000, chưa đủ",
		pick(bk6["tren90"], "qty", "value", "lots", "rows") == (102, 1_024_000, 3, 4)
		and d6["khong_ban"]["thu_hoi"] == {"available": False, "no_column": True}
		and [p.get("error") for p in d6["khong_ban"]["parts"]] == [False, False, False]
		and d6["khong_ban"]["tong"] == 876_000 and d6["khong_ban"]["day_du"] is False and d6["han"]["doi_chieu"]["khop"]
		and d6["meta"]["co_cot_thu_hoi"] is False, (bk6["tren90"], d6["khong_ban"]))

	# ═══ Một khối lỗi không làm hỏng trang ═══
	# Cột thu hồi CÓ (sx đã migrate) và có lô đang thu hồi — để (b) thật sự chạy và lỗi, khác ca "chưa có cột" ở trên.
	frappe.db.sql("ALTER TABLE `tabBatch` ADD COLUMN `custom_thu_hoi` int(1) NOT NULL DEFAULT 0")
	frappe.db.sql("UPDATE `tabBatch` SET custom_thu_hoi = 1 WHERE name IN %s",
		(("HAN-A-RECALL", "HAN-A-RECALL2", "HAN-H-R", "HAN-NL-R", "HAN-E-R"),))
	frappe.db.sql("DROP TABLE `tabSerial and Batch Entry`")
	d7 = run()
	k7 = d7["khong_ban"]
	c("bảng lô lỗi: K6 và K8 tắt (có ghi lỗi), K7 vẫn có phần kho trả về / cách ly; (b), (c) báo LỖI (không phải 'chưa có')",
		d7["available"] and d7["han"] == {"available": False, "error": True} and d7["am"] == {"available": False, "error": True}
		and k7["available"] and k7["tong"] == 232_000 and k7["day_du"] is False
		and k7["het_han"] == {"available": False, "error": True} and k7["thu_hoi"] == {"available": False, "error": True}
		and [p.get("error") for p in k7["parts"]] == [False, True, True], {k_: d7[k_] for k_ in ("han", "am", "khong_ban")})

	# ═══ XR-T1 / XR-REAL-2: tuổi hàng kho trả về / cách ly — kiểm kê và phiếu điều chỉnh sx KHÔNG phải lần nhập ═══
	build(extra=seed_tuoi)
	c("seed tuổi: có cột custom_kiem_ke (phiếu D191 mang lần kiểm)", frappe.db.has_column("Stock Entry", "custom_kiem_ke"))
	legs = [tuple(float(x) for x in r) for r in frappe.db.sql("""SELECT actual_qty, stock_value_difference
		FROM `tabStock Ledger Entry` WHERE voucher_no = 'HAN-RECO-T1' ORDER BY creation""")]
	# T1@trả về 10 → kiểm 9: chân −10 × 10k rồi +9 × 10k; Bin 9 / 90.000. T2 5 − 5 + 5 = 5. T3 4 − 4 + 4 = 4; T4 3 + 2 = 5;
	# T5 tồn đầu 6 (60k); T6 6 − 6 + 5 = 5 (60k − 60k + 50k); T7 5 − 5 + 4 + 2 = 6 (50k − 50k + 40k + 20k = 60k).
	c("seed tuổi: kiểm kê có lô ghi HAI chân như ERPNext (T1 −10 rồi +9) và Bin đúng sổ",
		legs == [(-10.0, -100_000.0), (9.0, 90_000.0)]
		and [bin_of(i, w)[:2] for i, w in ((T1, TRA_VE), (T2, TRA_VE), (T3, CACH_LY), (T4, CACH_LY), (T5, CACH_LY), (T6, CACH_LY),
			(T7, TRA_VE))] == [(9.0, 90_000.0), (5.0, 50_000.0), (4.0, 40_000.0), (5.0, 50_000.0), (6.0, 60_000.0), (5.0, 50_000.0),
				(6.0, 60_000.0)], legs)
	dt = run()["khong_ban"]["kho_loai"]
	age = {r["item_code"]: pick(r, "kho", "qty", "nhap_cuoi", "tuoi_ngay") for r in dt["ds"]}
	c("kiểm kê mã có lô (đếm THIẾU 9/10, đếm KHỚP 5/5) không làm mới tuổi: T1 từ 01/06 = 148 ngày, T2 từ 01/07 = 118 ngày",
		(age.get(T1), age.get(T2)) == (("Hàng trả về", 9, "2026-06-01", 148), ("Hàng trả về", 5, "2026-07-01", 118)), (age.get(T1), age.get(T2)))
	c("phiếu điều chỉnh sx không phải nhập: chuyển lô TONCU (custom_kiem_ke) T3 từ 01/08 = 87; dọn tồn âm T4 từ 01/09 = 56",
		(age.get(T3), age.get(T4)) == (("Kho cách ly", 4, "2026-08-01", 87), ("Kho cách ly", 5, "2026-09-01", 56)), (age.get(T3), age.get(T4)))
	c("tồn đầu kỳ là lần vào sổ, mã không lô (T5) và có lô (T6, kiểm lại 5/6) cùng câu trả lời: 01/03 = 240 ngày",
		(age.get(T5), age.get(T6)) == (("Kho cách ly", 6, "2026-03-01", 240), ("Kho cách ly", 5, "2026-03-01", 240)), (age.get(T5), age.get(T6)))
	c("nhập thật SAU kiểm kê vẫn tính: T7 khách trả thêm 15/10 = 12 ngày; ca cũ giữ nguyên (A@cách ly 68, NL 87, A@trả về 26)",
		age.get(T7) == ("Hàng trả về", 6, "2026-10-15", 12)
		and [pick(r, "item_code", "kho", "tuoi_ngay") for r in dt["ds"] if not r["item_code"].startswith("HAN-T")]
		== [(A, "Kho cách ly", 68), (NL, "Kho cách ly", 87), (A, "Hàng trả về", 26)], (age.get(T7), dt["ds"]))

	# ═══ Site không cài sx: không SX Settings; kho trả về đánh dấu is_rejected_warehouse ═══
	build(sx=False)
	frappe.db.sql("UPDATE `tabWarehouse` SET is_rejected_warehouse = 1 WHERE name = %s", (TRA_VE,))
	d8 = run()
	h8 = d8["han"]
	bk8 = {x["key"]: x for x in h8["buckets"]}
	# Kho cách ly thành kho bán được: hết hạn + A-EXP@cách ly 9 = 49 hộp, 734.000 — A-EXP giờ ở HAI kho bán được nhưng vẫn
	# là MỘT lô: 3 lô (A-EXP, B-L2, H-L1), 4 dòng. Phần âm + B-NEGQ@cách ly −1 (Bin khác 50k) = −21, −293.000;
	# Bin 509 + 9 − 1 = 517.
	c("không sx: kho cách ly bán được → hết hạn 49 hộp / 734.000 / 3 lô / 4 dòng, phần âm −21 / −293.000, vẫn khớp Bin 517",
		pick(bk8["het_han"], "qty", "value", "lots", "rows") == (49, 734_000, 3, 4) and pick(h8["phan_am"], "qty", "value") == (-21, -293_000)
		and pick(h8["doi_chieu"], "ton_kho_qty", "khop") == (517, True) and d8["meta"]["tp_nguon"] == "nhom", (bk8["het_han"], h8["phan_am"]))
	r8 = {r["role"]: r["value"] for r in d8["khong_ban"]["kho_loai"]["roles"]}
	# (a) chỉ kho trả về (is_rejected) 102.000; (b) 344.000; (c) 734.000 → 1.180.000.
	c("không sx: (a) chỉ kho trả về 102.000; tổng 1.180.000", r8 == {"tra_ve": 102_000, "cach_ly": 0}
		and d8["khong_ban"]["tong"] == 1_180_000, (r8, d8["khong_ban"]["tong"]))
	sp8 = {x["key"]: pick(x, "rows", "value_abs") for x in d8["am"]["split"]}
	c("không sx: không có kho xưởng → G sang 'khác'; tổng tồn âm không đổi",
		sp8 == {"tp_xuong": (0, 0), "cua_hang": (5, 115_000), "khac": (5, 296_000)} and d8["am"]["value_abs"] == 411_000, sp8)

	# ═══ Sổ chỉ còn lô thu hồi + phần âm (seed_thu_hoi — sổ của lượt giao diện thu-hoi, UX-11) ═══
	build_thu_hoi()
	dr = run()
	hr = dr["han"]
	# Phần dương rỗng (R1 chỉ có lô thu hồi; R2 chỉ có phần âm) nhưng tồn thành phẩm ngoài kho trả về & cách ly = 10 − 3 = 7.
	c("sổ chỉ còn lô thu hồi + phần âm: phần dương 0 dòng; thu hồi 1 dòng 10 hộp / 0,5 thùng / 100.000; âm 1 dòng −3 / −36.000",
		pick(hr["tong"], "rows", "qty", "value") == (0, 0, 0) and pick(hr["thu_hoi"], "rows", "qty", "cartons", "value") == (1, 10, 0.5, 100_000)
		and pick(hr["phan_am"], "rows", "qty", "value") == (1, -3, -36_000) and hr["chua_ro_ds"] == [] and hr["lo_can_date"] == [],
		(hr["tong"], hr["thu_hoi"], hr["phan_am"]))
	c("sổ chỉ còn lô thu hồi + phần âm: đối chiếu 0 + 10 − 3 = 7 hộp khớp Bin, giá trị sổ 100.000 − 36.000 = 64.000",
		hr["doi_chieu"]["khop"] and pick(hr["doi_chieu"], "ton_kho_qty", "ton_kho_value") == (7, 64_000)
		and [pick(x, "uom", "duong", "thu_hoi", "am", "ton_kho") for x in hr["doi_chieu"]["theo_dvt"]] == [("Hộp", 0, 10, -3, 7)],
		hr["doi_chieu"])
	c("sổ chỉ còn lô thu hồi + phần âm: không bán được = lô thu hồi 100.000; tồn âm 1 dòng 36.000",
		dr["khong_ban"]["tong"] == 100_000 and pick(dr["am"], "rows", "value_abs") == (1, 36_000), (dr["khong_ban"]["tong"], dr["am"]["rows"],
			dr["am"]["value_abs"]))

	# ═══ DB rỗng (có công ty, chưa có kho / mã) ═══
	reset()
	bc_settings()
	K()
	d9 = run()
	h9 = d9["han"]
	c("DB rỗng: mọi khối có, số 0, danh sách rỗng, đối chiếu khớp",
		d9["available"] and h9["available"] and h9["tong"]["qty"] == 0 and h9["tong"]["value"] == 0 and h9["lo_can_date"] == []
		and h9["doi_chieu"]["khop"] and h9["tong"]["pct"] is None and d9["khong_ban"]["tong"] == 0 and d9["am"]["rows"] == 0
		and d9["khong_ban"]["thu_hoi"]["value"] == 0 and h9["phan_am"]["qty"] == 0 and h9["phan_am"]["cartons"] is None, d9)
	# ═══ Chưa có công ty ═══
	reset()
	bc_settings()
	d10 = run()
	c("chưa xác định công ty: trả available False có lý do, không 500", d10["available"] is False and d10.get("reason"), d10)
	c.done()
