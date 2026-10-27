"""Kiểm kê & điều chỉnh (bc.api.kho_kk: K9 kiểm kê gần nhất theo kho, phiếu đang đếm, huỷ chốt, độ chính xác tồn; K10
chênh lệch kiểm kê sx / cửa hàng, dọn tồn sx, xuất khác, tổng điều chỉnh, top chênh lệch, mã về 0 không đếm) trên MariaDB
thật, bảng sinh từ DocType JSON v16 (+ SX Kiem Ke / Lo / Dong của app sx).

Số kỳ vọng TÍNH TAY từ sổ dưới đây (hôm nay 27/10/2026; kỳ mặc định 01/10 → 27/10; ngưỡng > 30 / > 90 ngày).
Bẫy có ca riêng: lần kiểm chốt sổ lùi (thoi_diem tháng 9, chot_luc tháng 10 — C7) + phiếu bù D216 ghi tháng 10 của lần
kiểm tháng 9; loai NULL → Thành phẩm; hai lần kiểm cùng chot_luc (thứ tự creation); biên 30 / 31 / 90 / 91 ngày; dòng
sổ ở kho khác (đổi cờ lô D191) mang custom_kiem_ke; dòng sổ huỷ trên chứng từ còn hiệu lực; phiếu kho huỷ lẻ; thừa / thiếu
xét theo MÃ sau khi cộng (lô −8 / +3, Repack chuyển lô chỉ lệch giá, mã giá 0); lô đang thu hồi trong biên bản (độ chính
xác); mã về 0 vì không đếm vs đếm 0; kiểm kê cửa hàng: hai phiếu cùng (mã, kho), dòng chỉ đổi giá, dòng lô, kho trả
về, Opening Stock / Adjustment Entry / phiếu nháp / huỷ / ghi ngày tương lai / công ty khác; dọn tồn theo tiền tố
(không phải chuỗi chứa), dọn tồn có custom_kiem_ke; xuất khác bỏ kiểm kê / dọn tồn / bù nợ BOM / phiếu đầu kỳ, giữ
Xuất huỷ tay; mã ẩn; site không sx, thiếu cột / bảng, khối lỗi, site trống, chưa có công ty.
Thêm sau review: kho sx có phiếu kiểm kho (Stock Reconciliation) mới hơn / cùng ngày / cũ hơn lần kiểm sx (K9 lấy lần đếm
mới nhất, khớp K10.2); cửa hàng bán hết (Bin 0) không thuộc bảng kho; mã về 0 vì không đếm còn lô thu hồi (bỏ dòng thu hồi);
phiếu nháp mở đúng 2 ngày (biên "mở lâu"); huỷ chốt của công ty khác.

Chạy: BC_TEST_DB=bc_test_kho_kk python3 -B test_kho_kk.py
seed(k) chỉ THÊM dữ liệu tên KKE-… lên base(k) (để gộp seed cho kiểm giao diện): reset(); bc_settings(); k = K(); base(k);
seed(k); k.finalize().
"""
import ast
import json
import os
import re

from seed import Check, bc_settings, child, drop_column, drop_doctype, insert, reset, single
from paths import BC_ROOT
from seed_kho import BTP, CACH_LY, CH1, CH2, CH_GROUP, G_NL, G_QUA_TET, G_TRAD, KHO_CU, NVL, RV, TP, TRA_VE, XUONG, K, base

import frappe  # noqa: E402

PRIVATE = ["thukho.bimat@hgc.vn", "Nguyễn Văn Kiểm Bí Mật", "GHI CHÚ KKE BÍ MẬT", "Đếm sai lô", "Trần Thị Kho Bí Mật",
	"DS_SE_BI_MAT", "chot.bimat@hgc.vn"]
CH3 = "KKE-CH Hàng Bông - HGC"
CH4 = "KKE-CH Hàng Gà - HGC"
CH5 = "KKE-CH Hàng Đào - HGC"   # bán hết → Bin 0
NHAN = "Bù chứng từ ghi lùi sau kiểm kê (D216)"
TP_L, BTP_L = "Thành phẩm", "Bán thành phẩm"


def _kk(name, kho, docstatus, chot=None, loai=TP_L, creation=None, thoi_diem=None, cach_dem=None, bat_dau=None,
		ghi_chu=None, modified=None, lo=(), dong=()):
	"""Một phiếu SX Kiem Ke + bảng lô (biên bản) + dòng đếm. lo: (item, batch, so_truoc, so_sau, viec);
	dong: (item, hsd, so_dem, dem_luc)."""
	insert("SX Kiem Ke", name=name, docstatus=docstatus, kho=kho, loai=loai, cach_dem=cach_dem,
		trang_thai={0: "Đang đếm", 1: "Đã chốt", 2: "Đã huỷ"}[docstatus], ngay=(thoi_diem or chot or creation)[:10],
		nguoi_lap=PRIVATE[0], nguoi_chot=PRIVATE[6] if chot else None, bat_dau_luc=bat_dau, thoi_diem=thoi_diem,
		chot_luc=chot, ghi_chu=ghi_chu, ds_se=PRIVATE[5], creation=creation or chot, modified=modified or chot or creation,
		owner=PRIVATE[0], so_ma=len({x[0] for x in lo}), tong_so_sach=sum(x[2] for x in lo), tong_dem=sum(x[3] for x in lo),
		tong_lech=sum(x[3] - x[2] for x in lo))
	child("SX Kiem Ke", name, "SX Kiem Ke Lo", "lo", [dict(item=i, ten=i, batch=b, so_truoc=a, so_sau=s, chenh=s - a, viec=v)
		for i, b, a, s, v in lo])
	child("SX Kiem Ke", name, "SX Kiem Ke Dong", "dong", [dict(item=i, ten=i, hsd=h, so_dem=q, dem_luc=t, nguoi_dem=PRIVATE[0])
		for i, h, q, t in dong])


def _rv(doctype, name):
	"""Chứng từ thuộc công ty khác (seed_kho ghi công ty mặc định)."""
	frappe.db.sql(f"UPDATE `tab{doctype}` SET company = 'RV' WHERE name = %s", (name,))


def seed(k: K):
	"""Kịch bản Kiểm kê (mọi tên bắt đầu KKE-). Giá trị = số lượng × đơn giá ghi ở từng dòng."""
	# ── Danh mục ── TP: custom_sx_nhom = 'TP'. Đơn giá: TP1 50.000, TP2 30.000, TP3 40.000, TP4 20.000 (lô), TP5 25.000
	# (chưa khai thùng), TP6 20.000, TP7 15.000, TP8 10.000 (bị ẩn), TP9 giá 0, TP10 15.000; BTP1 80.000 / kg, BTP2 60.000,
	# NL1 40.000.
	k.item("KKE-TP1", "Bánh đậu xanh KKE 1", G_TRAD, carton=20, custom_sx_nhom="TP")
	k.item("KKE-TP2", "Bánh KKE 2", G_TRAD, carton=12, custom_sx_nhom="TP")
	k.item("KKE-TP3", "Bánh KKE 3", G_TRAD, carton=10, custom_sx_nhom="TP")
	k.item("KKE-TP4", "Bánh KKE 4", G_TRAD, carton=24, batch=True, custom_sx_nhom="TP")
	k.item("KKE-TP5", "Bánh KKE 5", G_TRAD, custom_sx_nhom="TP")
	k.item("KKE-TP6", "Hộp quà KKE 6", G_QUA_TET, carton=20, custom_sx_nhom="TP")
	k.item("KKE-TP7", "Bánh KKE 7", G_TRAD, custom_sx_nhom="TP")
	k.item("KKE-TP8", "Bánh KKE 8", G_TRAD, carton=10, custom_sx_nhom="TP")
	k.item("KKE-TP9", "Bánh KKE 9", G_TRAD, carton=6, custom_sx_nhom="TP")
	k.item("KKE-TP10", "Bánh KKE 10", G_TRAD, carton=12, custom_sx_nhom="TP")
	k.item("KKE-BTP1", "Bột KKE", G_NL, uom="Kg", custom_sx_nhom="BTP-Bot")
	k.item("KKE-BTP2", "Nhân KKE", G_NL, uom="Kg", custom_sx_nhom="BTP-Dau")
	k.item("KKE-NL1", "Đường KKE", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.batch("KKE-L4A", "KKE-TP4", expiry="2027-01-31")
	k.batch("KKE-L4B", "KKE-TP4", expiry="2027-03-31")
	insert("BC Hidden Item", parent="BC Settings", parenttype="BC Settings", parentfield="hidden_items", idx=9,
		item_code="KKE-TP8")
	# Hai cửa hàng riêng của bộ thử (POS Profile → vai trò cửa hàng).
	k.wh(CH3, CH_GROUP)
	k.wh(CH4, CH_GROUP)
	k.wh(CH5, CH_GROUP)
	insert("POS Profile", name="KKE-POS Hàng Bông", company=k.company, warehouse=CH3, disabled=0)
	insert("POS Profile", name="KKE-POS Hàng Gà", company=k.company, warehouse=CH4, disabled=0)
	insert("POS Profile", name="KKE-POS Hàng Đào", company=k.company, warehouse=CH5, disabled=0)
	priv = {"owner": PRIVATE[0]}

	# ── Tồn đầu (phiếu nhập mua 10/01/2026 — không thuộc chỉ số nào của màn) ──
	for i, (item, wh, q, rate, b) in enumerate([
			("KKE-TP1", TP, 100, 50_000, None), ("KKE-TP2", TP, 50, 30_000, None), ("KKE-TP3", TP, 20, 40_000, None),
			("KKE-TP4", TP, 8, 20_000, "KKE-L4A"), ("KKE-TP4", TP, 10, 20_000, "KKE-L4B"), ("KKE-TP5", TP, 30, 25_000, None),
			("KKE-TP6", TP, 40, 20_000, None), ("KKE-TP8", TP, 10, 10_000, None),
			("KKE-TP1", CH1, 30, 50_000, None), ("KKE-TP2", CH1, 25, 30_000, None), ("KKE-TP4", CH1, 5, 20_000, "KKE-L4A"),
			("KKE-TP6", CH2, 10, 20_000, None), ("KKE-TP1", CH2, 10, 50_000, None),
			("KKE-TP1", CH3, 45, 50_000, None), ("KKE-TP2", CH3, 20, 30_000, None), ("KKE-TP6", CH3, 30, 20_000, None),
			("KKE-TP4", CH3, 10, 20_000, "KKE-L4B"), ("KKE-TP1", CH4, 31, 50_000, None),
			("KKE-TP2", TRA_VE, 3, 30_000, None), ("KKE-TP3", CACH_LY, 2, 40_000, None), ("KKE-TP5", KHO_CU, 4, 25_000, None),
			("KKE-NL1", NVL, 500, 40_000, None), ("KKE-BTP1", BTP, 100.5, 80_000, None), ("KKE-BTP2", BTP, 50, 60_000, None),
			("KKE-BTP1", XUONG, 20, 80_000, None), ("KKE-TP1", RV, 10, 50_000, None),
			("KKE-TP1", TRA_VE, 2, 50_000, None),    # kho trả về còn hàng sau SR-03 (đếm TP2 về 0)
			("KKE-TP10", TP, 8, 15_000, None), ("KKE-TP1", CH5, 5, 50_000, None)], 1):
		k.receipt(item, wh, q, q * rate, "2026-01-10", name=f"KKE-PR-{i:02d}", batch=b)
	# Cửa hàng Hàng Đào bán hết 5 hộp ngày 05/10 → Bin = 0: không còn giữ hàng → KHÔNG thuộc bảng kho K9 (chưa từng kiểm kê
	# nên lọt vào sẽ hiện "Chưa kiểm kê" đỏ).
	k.sale("KKE-TP1", CH5, 5, 250_000, "2026-10-05", name="KKE-SINV-01")

	# ═══ Kiểm kê sx (SX Kiem Ke) ═══
	# KK-01: TP, loai NULL (sx cũ) — chốt 15/08, cũ hơn KK-05 → không phải lần gần nhất.
	_kk("KKE-KK-01", TP, 1, chot="2026-08-15 10:00:00", loai=None, creation="2026-08-14 08:00:00",
		lo=[("KKE-TP1", None, 100, 100, "khớp sổ — giữ nguyên")])
	# KK-02: TP, CHỐT SỔ LÙI — thoi_diem 30/09 18:00, bấm chốt 03/10 → hiệu lực tháng 9 (C7). Phiếu chốt ghi 30/09; phiếu bù
	# D216 ghi 02/10 (tháng 10) nhưng vẫn thuộc lần kiểm tháng 9.
	_kk("KKE-KK-02", TP, 1, chot="2026-10-03 15:00:00", creation="2026-09-29 08:00:00", thoi_diem="2026-09-30 18:00:00",
		lo=[("KKE-TP1", None, 10, 8, "xuất thiếu 2"), ("KKE-TP2", None, 5, 6, "nhập thừa 1")])
	k.se("Material Issue", "2026-09-30", [dict(item_code="KKE-TP1", s_warehouse=TP, qty=2, rate=50_000)],     # −100.000
		kiem_ke="KKE-KK-02", time="18:00:00", remarks="Kiểm kê KKE-KK-02: xuất thiếu", name="KKE-SE-KK02-X", **priv)
	k.se("Material Receipt", "2026-09-30", [dict(item_code="KKE-TP2", t_warehouse=TP, qty=1, rate=30_000)],   # +30.000
		kiem_ke="KKE-KK-02", time="18:00:00", remarks="Kiểm kê KKE-KK-02: nhập thừa", name="KKE-SE-KK02-N")
	k.se("Material Receipt", "2026-10-02", [dict(item_code="KKE-TP2", t_warehouse=TP, qty=3, rate=30_000)],   # +90.000 bù
		kiem_ke="KKE-KK-02", time="11:00:00", remarks=f"{NHAN} — kiểm kê KKE-KK-02 (chốt 03/10)", name="KKE-SE-KK02-BU")
	# KK-03 / KK-04: BTP, CÙNG chot_luc 29/07 10:00 — KK-03 tạo sau (creation lớn hơn) → là lần gần nhất: 29/07 = 90 ngày.
	# KK-04 có thoi_diem 28/07 (91 ngày) — chọn nhầm thì thành "nguy" và độ chính xác 0/1.
	_kk("KKE-KK-03", BTP, 1, chot="2026-07-29 10:00:00", loai=BTP_L, creation="2026-07-29 09:00:00",
		lo=[("KKE-BTP1", "KKE-LB1", 100.5, 100.5, "khớp sổ — giữ nguyên"), ("KKE-BTP2", "KKE-LB2", 50, 48.25, "xuất thiếu 1.75")])
	k.se("Material Issue", "2026-07-29", [dict(item_code="KKE-BTP2", s_warehouse=BTP, qty=1.75, rate=60_000)],
		kiem_ke="KKE-KK-03", name="KKE-SE-KK03-X")
	_kk("KKE-KK-04", BTP, 1, chot="2026-07-29 10:00:00", loai=BTP_L, creation="2026-07-28 08:00:00",
		thoi_diem="2026-07-28 17:00:00", lo=[("KKE-BTP1", "KKE-LB1", 100.5, 99, "xuất thiếu 1.5")])
	# KK-05: TP, chốt 15/10 17:00, "Chỉ số lượng". Biên bản lô (so_truoc → so_sau):
	#   TP1 60→50 (−10) · TP2 20→26 (+6) · TP3 chuyển lô 5→0 / 0→5 (Σ 0, khớp) · TP4 lô A 8→0 (−8), lô B 10→13 (+3) → −5
	#   · TP5 12→0 KHÔNG có dòng đếm (về 0 vì không đếm, D188) · TP6 30→30 khớp + lô thu hồi 2→2 · TP7 CHỈ lô thu hồi 4→4
	#   · TP8 3→0 có dòng đếm số 0 (đã đếm, hết hàng) · TP9 0→5 (+5)
	#   · TP10 6→0 KHÔNG có dòng đếm + lô thu hồi 2→2 (về 0 vì không đếm; bỏ dòng thu hồi thì Σ so_sau = 0, Σ so_truoc = 6).
	# Độ chính xác: mã có sổ hoặc đếm ≠ 0 (bỏ dòng thu hồi) = TP1, 2, 3, 4, 5, 6, 8, 9, 10 = 9; khớp = TP3, TP6 → 2/9 = 22,2%.
	_kk("KKE-KK-05", TP, 1, chot="2026-10-15 17:00:00", creation="2026-10-14 07:30:00", bat_dau="2026-10-14 07:30:00",
		cach_dem="Chỉ số lượng", ghi_chu=f"Chốt bởi {PRIVATE[1]}", lo=[
			("KKE-TP1", "KKE-L1A", 60, 50, "xuất thiếu 10"), ("KKE-TP2", None, 20, 26, "nhập thừa 6"),
			("KKE-TP3", "KKE-L3OLD", 5, 0, "chuyển 5 sang lô HSD 01/03/27"), ("KKE-TP3", "KKE-L3NEW", 0, 5, "nhận 5 từ lô KKE-L3OLD"),
			("KKE-TP4", "KKE-L4A", 8, 0, "xuất thiếu 8"), ("KKE-TP4", "KKE-L4B", 10, 13, "nhập thừa 3"),
			("KKE-TP5", None, 12, 0, "xuất thiếu 12"),
			("KKE-TP6", None, 30, 30, "khớp sổ — giữ nguyên"), ("KKE-TP6", "KKE-L6TH", 2, 2, "đang thu hồi — không kiểm (2)"),
			("KKE-TP7", "KKE-L7TH", 4, 4, "đang thu hồi — không kiểm (4)"),
			("KKE-TP8", None, 3, 0, "xuất thiếu 3"), ("KKE-TP9", None, 0, 5, "nhập thừa 5"),
			("KKE-TP10", None, 6, 0, "xuất thiếu 6"), ("KKE-TP10", "KKE-L10TH", 2, 2, "đang thu hồi — không kiểm (2)")],
		dong=[("KKE-TP1", "2027-03-01", 50, "2026-10-15 09:00:00"), ("KKE-TP2", None, 26, "2026-10-15 09:10:00"),
			("KKE-TP3", None, 5, "2026-10-15 09:20:00"), ("KKE-TP4", None, 13, "2026-10-15 09:30:00"),
			("KKE-TP6", None, 30, "2026-10-15 09:40:00"), ("KKE-TP8", None, 0, "2026-10-15 09:50:00"),
			("KKE-TP9", None, 5, "2026-10-15 10:00:00")])
	t5 = "17:00:00"
	# Repack chuyển lô TP3: ra 5 × 40.200 = −201.000, vào 5 × 40.000 = +200.000 → số lượng 0, giá trị −1.000 (chênh giá).
	k.se("Repack", "2026-10-15", [dict(item_code="KKE-TP3", s_warehouse=TP, qty=5, rate=40_200),
		dict(item_code="KKE-TP3", t_warehouse=TP, qty=5, rate=40_000)], kiem_ke="KKE-KK-05", time=t5, name="KKE-SE-KK05-R")
	# Xuất thiếu: TP1 −10 × 50.000 = −500.000; TP4 lô A −8 × 20.000 = −160.000; TP5 −12 × 25.000 = −300.000; TP8 −3 × 10.000
	# = −30.000; TP10 −6 × 15.000 = −90.000 (lô thu hồi 2 hộp giữ nguyên trên sổ).
	k.se("Material Issue", "2026-10-15", [dict(item_code="KKE-TP1", s_warehouse=TP, qty=10, rate=50_000),
		dict(item_code="KKE-TP4", s_warehouse=TP, qty=8, rate=20_000, batch="KKE-L4A"),
		dict(item_code="KKE-TP5", s_warehouse=TP, qty=12, rate=25_000),
		dict(item_code="KKE-TP8", s_warehouse=TP, qty=3, rate=10_000),
		dict(item_code="KKE-TP10", s_warehouse=TP, qty=6, rate=15_000)], kiem_ke="KKE-KK-05", time=t5,
		remarks=f"Kiểm kê KKE-KK-05: xuất thiếu — {PRIVATE[2]}", name="KKE-SE-KK05-X", **priv)
	# Dòng sổ ĐÃ HUỶ (repost) trên phiếu còn hiệu lực: TP2 −50 → lọt vào thì TP2 thành thiếu.
	k.sle("KKE-TP2", TP, -50, -1_500_000, "2026-10-15", "Stock Entry", "KKE-SE-KK05-X", t5, cancelled=1)
	# Nhập thừa: TP2 +6 × 30.000 = +180.000; TP4 lô B +3 × 20.000 = +60.000; TP9 +5 giá 0.
	k.se("Material Receipt", "2026-10-15", [dict(item_code="KKE-TP2", t_warehouse=TP, qty=6, rate=30_000),
		dict(item_code="KKE-TP4", t_warehouse=TP, qty=3, rate=20_000, batch="KKE-L4B"),
		dict(item_code="KKE-TP9", t_warehouse=TP, qty=5, rate=0)], kiem_ke="KKE-KK-05", time=t5, name="KKE-SE-KK05-N")
	# Phiếu bù D216 ghi lùi 14/10 (trước lúc chốt): TP1 +4 × 50.000 = +200.000. Phiếu bù đã huỷ (sx tự huỷ) không tính.
	k.se("Material Receipt", "2026-10-14", [dict(item_code="KKE-TP1", t_warehouse=TP, qty=4, rate=50_000)],
		kiem_ke="KKE-KK-05", time="16:00:00", remarks=f"{NHAN} — kiểm kê KKE-KK-05", name="KKE-SE-KK05-BU")
	k.se("Material Issue", "2026-10-14", [dict(item_code="KKE-TP2", s_warehouse=TP, qty=1, rate=30_000)], docstatus=2,
		kiem_ke="KKE-KK-05", time="16:30:00", remarks=f"{NHAN} — kiểm kê KKE-KK-05", name="KKE-SE-KK05-BUH")
	# Phiếu kho của lần kiểm bị HUỶ LẺ (lần kiểm vẫn chốt) → cờ kiểm soát 1 phiếu.
	k.se("Material Receipt", "2026-10-15", [dict(item_code="KKE-TP2", t_warehouse=TP, qty=100, rate=30_000)], docstatus=2,
		kiem_ke="KKE-KK-05", time=t5, remarks="Kiểm kê KKE-KK-05: nhập thừa", name="KKE-SE-KK05-HUY")
	# Đổi cờ lô (D191) ở CỬA HÀNG 1 — cùng custom_kiem_ke nhưng KHÔNG ở kho kiểm: −7 × 50.000, +7 × 49.000 (lệch −7.000).
	k.se("Material Issue", "2026-10-15", [dict(item_code="KKE-TP1", s_warehouse=CH1, qty=7, rate=50_000)],
		kiem_ke="KKE-KK-05", time=t5, name="KKE-SE-KK05-D1")
	k.se("Material Receipt", "2026-10-15", [dict(item_code="KKE-TP1", t_warehouse=CH1, qty=7, rate=49_000)],
		kiem_ke="KKE-KK-05", time=t5, name="KKE-SE-KK05-D2")
	# Phiếu "dọn tồn" mang custom_kiem_ke (ở CH1): thuộc kiểm kê, KHÔNG phải dọn tồn (+50.000 nếu lọt sang dọn tồn).
	k.se("Material Receipt", "2026-10-15", [dict(item_code="KKE-TP1", t_warehouse=CH1, qty=1, rate=50_000)],
		kiem_ke="KKE-KK-05", time=t5, remarks="Dọn tồn không lô sau bật lô (trong lần kiểm)", name="KKE-SE-KK05-DL")
	# KK-07: TP, chốt 20/10 rồi HUỶ CHỐT (D196) → docstatus 2, phiếu kho huỷ theo. KK-08 = phiếu nháp mở lại.
	_kk("KKE-KK-07", TP, 2, chot="2026-10-20 10:00:00", creation="2026-10-18 07:00:00", modified="2026-10-20 11:00:00",
		bat_dau="2026-10-18 08:00:00",
		ghi_chu=f"Đếm lại — {PRIVATE[1]}\n[Huỷ chốt 20/10/2026 11:00 — {PRIVATE[0]}] {PRIVATE[3]}",
		lo=[("KKE-TP6", None, 40, 20, "xuất thiếu 20")])
	k.se("Material Issue", "2026-10-20", [dict(item_code="KKE-TP6", s_warehouse=TP, qty=20, rate=20_000)], docstatus=2,
		kiem_ke="KKE-KK-07", time="10:00:00", name="KKE-SE-KK07-X")
	# KK-08 nháp (TP) do huỷ chốt tạo lúc 20/10 11:00, GIỮ bat_dau_luc 18/10 08:00 của phiếu cũ → tuổi 9 ngày (theo creation
	# chỉ 7); dòng đếm cuối 24/10 → im lặng 3 ngày; 3 dòng, 2 mã.
	_kk("KKE-KK-08", TP, 0, creation="2026-10-20 11:00:00", bat_dau="2026-10-18 08:00:00", thoi_diem="2026-10-19 18:00:00",
		cach_dem="Chỉ số lượng", ghi_chu=f"Mở lại từ phiếu đã huỷ chốt KKE-KK-07: {PRIVATE[3]}",
		dong=[("KKE-TP1", "2027-03-01", 20, "2026-10-23 09:00:00"), ("KKE-TP1", "2027-04-01", 5, "2026-10-24 09:30:00"),
			("KKE-TP2", None, 10, "2026-10-22 14:00:00")])
	# KK-09: BTP, huỷ trên Desk (không phải huỷ chốt) 05/10. KK-10: TP, huỷ chốt, hiệu lực 25/09 (thoi_diem) → tháng 9.
	_kk("KKE-KK-09", BTP, 2, chot="2026-10-05 09:00:00", loai=BTP_L, modified="2026-10-06 08:00:00")
	_kk("KKE-KK-10", TP, 2, chot="2026-10-06 09:00:00", thoi_diem="2026-09-25 18:00:00", modified="2026-10-06 10:00:00",
		ghi_chu=f"[Huỷ chốt 06/10/2026 10:00 — {PRIVATE[0]}] sai giờ")
	# KK-16: BTP, duyệt rồi huỷ trên Desk, KHÔNG có thoi_diem lẫn chot_luc (tạo 28/09) → ngày hiệu lực = modified 08/10 (M6b).
	_kk("KKE-KK-16", BTP, 2, loai=BTP_L, creation="2026-09-28 08:00:00", modified="2026-10-08 09:00:00")
	# KK-11: BTP nháp, không bat_dau_luc (tạo trên Desk) → tính từ creation 26/10; chưa dòng nào.
	_kk("KKE-KK-11", BTP, 0, loai=BTP_L, creation="2026-10-26 07:00:00")
	# KK-14: phiếu nháp TP THỨ HAI (Desk tạo được dù app chỉ cho một) mở đúng 2 ngày (bat_dau 25/10) → biên "mở lâu" (≥ 2).
	_kk("KKE-KK-14", TP, 0, creation="2026-10-25 06:00:00", bat_dau="2026-10-25 07:00:00")
	# Công ty khác: nháp + lần kiểm đã chốt (kèm phiếu kho +2 × 50.000) — không bao giờ tính.
	_kk("KKE-KK-12", RV, 0, creation="2026-10-25 07:00:00")
	_kk("KKE-KK-13", RV, 1, chot="2026-10-10 10:00:00", lo=[("KKE-TP1", None, 10, 12, "nhập thừa 2")])
	# Công ty khác: huỷ chốt trong tháng 10 (12/10) — không vào danh sách huỷ chốt.
	_kk("KKE-KK-15", RV, 2, chot="2026-10-12 10:00:00", modified="2026-10-12 11:00:00",
		ghi_chu=f"[Huỷ chốt 12/10/2026 11:00 — {PRIVATE[0]}] {PRIVATE[3]}")
	k.se("Material Receipt", "2026-10-10", [dict(item_code="KKE-TP1", t_warehouse=RV, qty=2, rate=50_000)],
		kiem_ke="KKE-KK-13", name="KKE-SE-KK13-N")
	_rv("Stock Entry", "KKE-SE-KK13-N")

	# ═══ Kiểm kê cửa hàng (Stock Reconciliation) ═══
	# Tháng 10: SR-01 (12/10, CH3): TP1 45→40 (−5, −250.000) · TP2 20→22 (+2, +60.000) · TP6 30→30 chỉ đổi giá +15.000.
	k.recon("2026-10-12", [dict(item_code="KKE-TP1", warehouse=CH3, qty=40, current_qty=45, value_diff=-250_000),
		dict(item_code="KKE-TP2", warehouse=CH3, qty=22, current_qty=20, value_diff=60_000),
		dict(item_code="KKE-TP6", warehouse=CH3, qty=30, current_qty=30, value_diff=15_000, rate=20_500)], name="KKE-SR-01")
	k.sle("KKE-TP2", CH3, 0, 999_000, "2026-10-12", "Stock Reconciliation", "KKE-SR-01", "18:00:00", cancelled=1, sr_qty=99)
	# SR-02 (20/10, CH3): TP4 lô B 10→7 (−3, −60.000) · TP1 40→46 (+6, +300.000) · TP2 22→22 chỉ đổi giá −2.200.
	# → (TP1, CH3) cộng hai phiếu: +1, +50.000 = THỪA (xét từng phiếu thì thừa 300.000 + thiếu 250.000).
	k.recon("2026-10-20", [dict(item_code="KKE-TP4", warehouse=CH3, qty=7, current_qty=10, value_diff=-60_000, batch="KKE-L4B"),
		dict(item_code="KKE-TP1", warehouse=CH3, qty=46, current_qty=40, value_diff=300_000),
		dict(item_code="KKE-TP2", warehouse=CH3, qty=22, current_qty=22, value_diff=-2_200, rate=29_900)], name="KKE-SR-02")
	# SR-03 (15/10, kho TRẢ VỀ — không bán được, không nằm trong bảng kho K9 nhưng vẫn là kiểm kê): TP2 3→0 (−90.000).
	k.recon("2026-10-15", [dict(item_code="KKE-TP2", warehouse=TRA_VE, qty=0, current_qty=3, value_diff=-90_000)],
		name="KKE-SR-03")
	# Không phải lần đếm: Opening Stock (CH1 +5 tr), Adjustment Entry (CH1 −4.000), ghi ngày tương lai 29/10 (CH2 −250.000),
	# phiếu huỷ 14/10 (CH2, dòng sổ đã huỷ −400.000), phiếu nháp 25/10, công ty khác (RV −250.000).
	k.recon("2026-10-20", [dict(item_code="KKE-TP1", warehouse=CH1, qty=100, current_qty=0, value_diff=5_000_000)],
		purpose="Opening Stock", name="KKE-SR-04")
	k.recon("2026-10-22", [dict(item_code="KKE-TP2", warehouse=CH1, qty=25, current_qty=25, value_diff=-4_000)],
		purpose="Adjustment Entry", name="KKE-SR-05")
	k.recon("2026-10-29", [dict(item_code="KKE-TP1", warehouse=CH2, qty=5, current_qty=10, value_diff=-250_000)],
		name="KKE-SR-06")
	k.recon("2026-10-14", [dict(item_code="KKE-TP1", warehouse=CH2, qty=1, current_qty=9, value_diff=-400_000)],
		docstatus=2, name="KKE-SR-07")
	k.sle("KKE-TP1", CH2, 0, -400_000, "2026-10-14", "Stock Reconciliation", "KKE-SR-07", "18:00:00", cancelled=1, sr_qty=1)
	k.recon("2026-10-25", [dict(item_code="KKE-TP1", warehouse=CH4, qty=1, current_qty=31, value_diff=-1_500_000)],
		docstatus=0, name="KKE-SR-12")
	k.recon("2026-10-10", [dict(item_code="KKE-TP1", warehouse=RV, qty=5, current_qty=10, value_diff=-250_000)],
		name="KKE-SR-08")
	_rv("Stock Reconciliation", "KKE-SR-08")
	# Tháng 9: SR-09 (27/09, CH1 — đúng 30 ngày) TP2 20→18 (−60.000); SR-10 (26/09, CH2 — 31 ngày) TP6 10→12 (+40.000).
	k.recon("2026-09-27", [dict(item_code="KKE-TP2", warehouse=CH1, qty=18, current_qty=20, value_diff=-60_000)],
		name="KKE-SR-09")
	k.recon("2026-09-26", [dict(item_code="KKE-TP6", warehouse=CH2, qty=12, current_qty=10, value_diff=40_000)],
		name="KKE-SR-10")
	# Tháng 7: SR-11 (28/07, CH4 — 91 ngày) TP1 31→30 (−50.000).
	k.recon("2026-07-28", [dict(item_code="KKE-TP1", warehouse=CH4, qty=30, current_qty=31, value_diff=-50_000)],
		name="KKE-SR-11")

	# ═══ Dọn tồn của sx (tiền tố remarks, không custom_kiem_ke) ═══
	# Dọn tồn không lô 05/10: xuất CH1 TP4 −2 × 20.000 + xuất TP TP1 −1 × 50.000; nhập lại CH1 TP4 +2 vào lô → −50.000, 2 phiếu.
	k.se("Material Issue", "2026-10-05", [dict(item_code="KKE-TP4", s_warehouse=CH1, qty=2, rate=20_000),
		dict(item_code="KKE-TP1", s_warehouse=TP, qty=1, rate=50_000)],
		remarks="Dọn tồn không lô sau bật lô [DL-051026-090000] — xuất phần không lô", name="KKE-SE-DL1")
	k.se("Material Receipt", "2026-10-05", [dict(item_code="KKE-TP4", t_warehouse=CH1, qty=2, rate=20_000, batch="KKE-L4A")],
		remarks="Dọn tồn không lô sau bật lô [DL-051026-090000] — nhập vào lô", name="KKE-SE-DL2")
	# Dọn tồn âm TP ở xưởng 08/10: TP2 +4 × 30.000 = +120.000 (+ dòng sổ đã huỷ +500.000 trên chính phiếu này).
	k.se("Material Receipt", "2026-10-08", [dict(item_code="KKE-TP2", t_warehouse=XUONG, qty=4, rate=30_000)],
		remarks="Dọn tồn âm thành phẩm [DA-081026-100000] tại Kho Xưởng", name="KKE-SE-DA1")
	k.sle("KKE-TP2", XUONG, 10, 500_000, "2026-10-08", "Stock Entry", "KKE-SE-DA1", cancelled=1)
	# Dọn âm lịch sử lô 09/10: nhập 3 + xuất 3 cùng lô → 0 (2 phiếu, không đáng kể → ẩn).
	k.se("Material Receipt", "2026-10-09", [dict(item_code="KKE-TP4", t_warehouse=TP, qty=3, rate=20_000, batch="KKE-L4B")],
		remarks="Dọn âm lịch sử lô (D207) [AL-091026] nhập", name="KKE-SE-DAL1")
	k.se("Material Issue", "2026-10-09", [dict(item_code="KKE-TP4", s_warehouse=TP, qty=3, rate=20_000, batch="KKE-L4B")],
		remarks="Dọn âm lịch sử lô (D207) [AL-091026] xuất", name="KKE-SE-DAL2")
	# Tháng 9 (28/09): dọn tồn âm +30.000. Phiếu huỷ 10/10 và công ty khác 11/10 không tính.
	k.se("Material Receipt", "2026-09-28", [dict(item_code="KKE-TP2", t_warehouse=XUONG, qty=1, rate=30_000)],
		remarks="Dọn tồn âm thành phẩm [DA-280926]", name="KKE-SE-DA0")
	k.se("Material Receipt", "2026-10-10", [dict(item_code="KKE-TP2", t_warehouse=XUONG, qty=9, rate=30_000)], docstatus=2,
		remarks="Dọn tồn âm thành phẩm [DA-101026]", name="KKE-SE-DAX")
	k.se("Material Receipt", "2026-10-11", [dict(item_code="KKE-TP1", t_warehouse=RV, qty=2, rate=50_000)],
		remarks="Dọn tồn âm thành phẩm [DA-111026]", name="KKE-SE-DARV")
	_rv("Stock Entry", "KKE-SE-DARV")

	# ═══ Xuất khác (Material Issue không phải kiểm kê / dọn tồn / bù nợ BOM / đầu kỳ) ═══
	# Tháng 10: Xuất huỷ TP TP5 −10 × 25.000 = 250.000 (+ dòng sổ đã huỷ −1 tr); Xuất huỷ CH1 TP1 −1 × 50.000 = 50.000
	# (remarks CHỨA chữ "Dọn tồn âm thành phẩm" nhưng không bắt đầu bằng nó → vẫn là xuất huỷ); Xuất mẫu CH1 TP2 −2 × 30.000.
	k.se("Material Issue", "2026-10-06", [dict(item_code="KKE-TP5", s_warehouse=TP, qty=10, rate=25_000)],
		entry_type="Xuất huỷ", remarks=f"Huỷ hàng hết hạn — {PRIVATE[2]}", name="KKE-SE-HUY1", **priv)
	k.sle("KKE-TP5", TP, -40, -1_000_000, "2026-10-06", "Stock Entry", "KKE-SE-HUY1", cancelled=1)
	k.se("Material Issue", "2026-10-07", [dict(item_code="KKE-TP1", s_warehouse=CH1, qty=1, rate=50_000)],
		entry_type="Xuất huỷ", remarks="Huỷ hàng vỡ — Dọn tồn âm thành phẩm ở kho khác", name="KKE-SE-HUY2")
	k.se("Material Issue", "2026-10-07", [dict(item_code="KKE-TP2", s_warehouse=CH1, qty=2, rate=30_000)],
		entry_type="Xuất mẫu", name="KKE-SE-MAU1")
	# Không tính: xuất NVL bù nợ BOM (−400.000), phiếu đầu kỳ (−200.000), phiếu huỷ, tháng 9 (Xuất huỷ CH2 20.000 → kỳ 9),
	# công ty khác.
	k.se("Material Issue", "2026-10-10", [dict(item_code="KKE-NL1", s_warehouse=NVL, qty=10, rate=40_000)],
		remarks=f"Hạch toán bù nợ BOM KKE-NB-01 — {PRIVATE[4]}", name="KKE-SE-BOM1", **priv)
	k.se("Material Issue", "2026-10-03", [dict(item_code="KKE-NL1", s_warehouse=NVL, qty=5, rate=40_000)],
		is_opening="Yes", name="KKE-SE-OPEN")
	k.se("Material Issue", "2026-10-08", [dict(item_code="KKE-TP5", s_warehouse=TP, qty=2, rate=25_000)], docstatus=2,
		entry_type="Xuất huỷ", name="KKE-SE-HUYX")
	k.se("Material Issue", "2026-09-15", [dict(item_code="KKE-TP6", s_warehouse=CH2, qty=1, rate=20_000)],
		entry_type="Xuất huỷ", name="KKE-SE-HUY0")
	k.se("Material Issue", "2026-10-09", [dict(item_code="KKE-TP1", s_warehouse=RV, qty=1, rate=50_000)],
		entry_type="Xuất huỷ", name="KKE-SE-HUYRV")
	_rv("Stock Entry", "KKE-SE-HUYRV")


def main_seed(sx=True, extra=None):
	reset()
	bc_settings()
	k = K()
	base(k, sx=sx)
	seed(k)
	if extra:
		extra(k)
	k.finalize()
	return k


def seed_sr_kho_sx(k: K):
	"""Phiếu kiểm kho (Stock Reconciliation) ở CHÍNH các kho sx — kịch bản riêng cho K9 "lần đếm mới nhất của kho".
	BTP: lần kiểm sx gần nhất 29/07 (KK-03) nhưng kiểm trên Desk 25/10 → ngày 25/10. TP: phiếu 10/10 và 15/10 — 15/10 trùng
	ngày KK-05 → hoà giữ nguồn sx; 2 phiếu + 1 lần sx = 3 lần trong tháng. Xưởng: sx chưa đếm, phiếu 20/09 → 37 ngày.
	Không tính: Opening Stock ở xưởng 26/10, phiếu ghi ngày tương lai 30/10 ở BTP."""
	k.recon("2026-10-25", [dict(item_code="KKE-BTP2", warehouse=BTP, qty=46, current_qty=48.25, value_diff=-135_000)],
		name="KKE-SR-21")
	k.recon("2026-10-30", [dict(item_code="KKE-BTP2", warehouse=BTP, qty=40, current_qty=46, value_diff=-360_000)],
		name="KKE-SR-22")
	k.recon("2026-10-10", [dict(item_code="KKE-TP6", warehouse=TP, qty=39, current_qty=40, value_diff=-20_000)],
		name="KKE-SR-23")
	k.recon("2026-10-15", [dict(item_code="KKE-TP6", warehouse=TP, qty=39, current_qty=39, value_diff=3_900, rate=20_100)],
		time="08:00:00", name="KKE-SR-24")
	k.recon("2026-09-20", [dict(item_code="KKE-BTP1", warehouse=XUONG, qty=19, current_qty=20, value_diff=-80_000)],
		name="KKE-SR-25")
	k.recon("2026-10-26", [dict(item_code="KKE-BTP1", warehouse=XUONG, qty=25, current_qty=19, value_diff=480_000)],
		purpose="Opening Stock", name="KKE-SR-26")


def ov(thang=None):
	from bc.api import kho_kk
	return kho_kk.get_overview(thang=thang, refresh=1) if thang else kho_kk.get_overview(refresh=1)


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


def kho_rows(d):
	return [(r["kho"], r["loai"], r["nguon"], r["ngay"], r["so_ngay"], r["muc"]) for r in d["kho"]["rows"]]


if __name__ == "__main__":
	c = Check()
	main_seed()
	frappe.LOGGED.clear()
	d = ov()
	m = d["meta"]
	c("có dữ liệu, kỳ mặc định tháng 10 cắt ở hôm nay", d["available"] is True and (m["thang"], m["from"], m["to"], m["as_of"],
		m["prev"], m["sx"], m["kiem_ke_col"]) == ("2026-10", "2026-10-01", "2026-10-27", "2026-10-27", "2026-09", True, True), m)
	blocks = ("kho", "dang_dem", "huy_chot", "ira", "kk_sx", "kk_ch", "don_sx", "xuat_khac", "tong", "top_lech", "ve_0")
	c("mọi khối đều có, không ghi lỗi", all(d[b].get("available") for b in blocks) and not frappe.LOGGED,
		({b: d[b].get("available") for b in blocks}, frappe.LOGGED[:1]))

	# ═══ K9. Kiểm kê gần nhất theo kho ═══
	# sx: TP = KK-05 (chot 15/10 mới nhất; KK-01 loai NULL cùng nhóm TP; KK-07 đã huỷ) → 12 ngày; BTP = KK-03 (cùng chot_luc
	# với KK-04, creation sau) → 29/07 = 90 ngày → cảnh báo (chưa "nguy"); Xưởng chưa kiểm. Cửa hàng / kho khác có tồn:
	# CH1 27/09 = 30 ngày (Opening / Adjustment sau đó không tính) → ổn; CH2 26/09 = 31 → cảnh báo (phiếu 29/10 tương lai,
	# phiếu huỷ 14/10 không tính); CH3 20/10 = 7; CH4 28/07 = 91 → nguy; NVL, kho cũ (ngừng dùng) chưa kiểm. Không có: kho
	# trả về / cách ly (không bán được), đi đường (không tồn), CH5 (bán hết, Bin = 0), kho công ty khác. Thứ tự: chưa kiểm
	# (theo vai trò) → ngày giảm.
	exp = [(XUONG, BTP_L, "sx", None, None, "chua"), (NVL, None, "sr", None, None, "chua"),
		(KHO_CU, None, "sr", None, None, "chua"), (CH4, None, "sr", "2026-07-28", 91, "nguy"),
		(BTP, BTP_L, "sx", "2026-07-29", 90, "canh_bao"), (CH2, None, "sr", "2026-09-26", 31, "canh_bao"),
		(CH1, None, "sr", "2026-09-27", 30, "ok"), (TP, TP_L, "sx", "2026-10-15", 12, "ok"),
		(CH3, None, "sr", "2026-10-20", 7, "ok")]
	c("K9 bảng kho: phạm vi, nguồn, ngày hiệu lực, số ngày, mức, thứ tự", kho_rows(d) == exp, kho_rows(d))
	kt = by(d["kho"]["rows"], "kho", TP)
	c("K9 kho TP: phiếu KK-05, cách đếm 'Chỉ số lượng', 1 lần trong tháng (KK-02 hiệu lực tháng 9), đang có phiếu nháp",
		(kt["phieu"], kt["cach_dem"], kt["so_lan_trong_ky"], kt["dang_dem"], kt["label"], kt["role"])
		== ("KKE-KK-05", "Chỉ số lượng", 1, True, "Thành phẩm", "tp"), kt)
	kb = by(d["kho"]["rows"], "kho", BTP)
	c("K9 kho BTP: phiếu KK-03, không có cách đếm (BTP), có phiếu nháp KK-11",
		(kb["phieu"], kb["cach_dem"], kb["dang_dem"], kb["so_lan_trong_ky"]) == ("KKE-KK-03", None, True, 0), kb)
	kx = by(d["kho"]["rows"], "kho", XUONG)
	c("K9 xưởng chưa kiểm: không phiếu, không nháp", (kx["phieu"], kx["dang_dem"], kx["so_lan_trong_ky"]) == (None, False, 0), kx)
	k3 = by(d["kho"]["rows"], "kho", CH3)
	c("K9 cửa hàng chỉ có Stock Reconciliation: hiện ngày, 2 lần trong tháng, vai trò cửa hàng",
		(k3["so_lan_trong_ky"], k3["role_label"], k3["phieu"], k3["dang_dem"], k3["label"]) == (2, "Cửa hàng", None, None,
		"KKE-CH Hàng Bông"), k3)
	c("K9 kho ngừng dùng còn hàng có cờ", by(d["kho"]["rows"], "kho", KHO_CU)["disabled"] is True)
	c("K9 tổng: 9 kho, 3 chưa kiểm, 3 quá 30 ngày (91, 90, 31), 1 quá 90", d["kho"]["tong"] == {"so_kho": 9, "chua_kiem": 3,
		"qua_30": 3, "qua_90": 1}, d["kho"]["tong"])
	c("K9 cửa hàng bán hết hàng (Bin 0, chưa từng kiểm) không thuộc bảng kho", CH5 not in {r["kho"] for r in d["kho"]["rows"]}
		and [float(x[0]) for x in frappe.db.sql("SELECT actual_qty FROM `tabBin` WHERE warehouse = %s", (CH5,))] == [0.0],
		frappe.db.sql("SELECT item_code, actual_qty FROM `tabBin` WHERE warehouse = %s", (CH5,)))
	c("K9 kho sx chỉ có lần kiểm sx: ngày từ sx (chưa có phiếu kiểm kho ở kho đó)",
		[(r["kho"], r.get("nguon_ngay"), r.get("ngay_sx"), r.get("ngay_sr")) for r in d["kho"]["rows"] if r["nguon"] == "sx"]
		== [(XUONG, None, None, None), (BTP, "sx", "2026-07-29", None), (TP, "sx", "2026-10-15", None)]
		and {r.get("nguon_ngay", "?") for r in d["kho"]["rows"] if r["nguon"] == "sr"} == {"sr", None}, d["kho"]["rows"])

	# ═══ Phiếu đang đếm / huỷ chốt ═══
	dd = d["dang_dem"]
	# KK-14: mở 25/10 → đúng 2 ngày = "mở lâu" (biên ≥ 2); KK-11: 1 ngày = chưa.
	c("đang đếm: KK-08 (9 ngày từ bat_dau_luc, im lặng 3, 3 dòng / 2 mã, chốt sổ 19/10), KK-14 (đúng 2 ngày → mở lâu), KK-11 "
		"(từ creation, 1 ngày, chưa dòng); bỏ RV",
		[(r["phieu"], r["kho"], r["loai"], r["cach_dem"], r["bat_dau"], r["thoi_diem"], r["tuoi"], r["im_lang"], r["so_dong"],
		r["so_ma"], r["cu"]) for r in dd["rows"]] == [
		("KKE-KK-08", TP, TP_L, "Chỉ số lượng", "2026-10-18", "2026-10-19", 9, 3, 3, 2, True),
		("KKE-KK-14", TP, TP_L, "Kèm hạn sử dụng", "2026-10-25", None, 2, 2, 0, 0, True),
		("KKE-KK-11", BTP, BTP_L, None, "2026-10-26", None, 1, 1, 0, 0, False)] and (dd["so_phieu"], dd["cu"]) == (3, 2), dd)
	hc = d["huy_chot"]
	c("huỷ chốt trong tháng: KK-09 (Desk, 05/10), KK-16 (không thoi_diem / chot_luc → modified 08/10), KK-07 (mở lại, 20/10); "
		"KK-10 hiệu lực 25/09, KK-15 công ty khác không tính",
		[(r["phieu"], r["ngay"], r["mo_lai"]) for r in hc["rows"]] == [("KKE-KK-09", "2026-10-05", False),
		("KKE-KK-16", "2026-10-08", False), ("KKE-KK-07", "2026-10-20", True)] and (hc["so_phieu"], hc["so_mo_lai"]) == (3, 1),
		hc)

	# ═══ Độ chính xác tồn (lần kiểm sx gần nhất) ═══
	ira = d["ira"]
	# KK-03 (BTP): BTP1 khớp, BTP2 lệch → 1/2 = 50%; KK-05 (TP): 2/9 = 22,2% (TP7 chỉ có lô thu hồi → không tính; TP10 tính
	# phần không thu hồi 6 → 0) → tổng 3/11 = 27,27… → 27,3%.
	c("độ chính xác: BTP 1/2 = 50%, TP 2/9 = 22,2%, chung 3/11 = 27,3%",
		[(r["phieu"], r["so_ma"], r["so_ma_khop"], r["ty_le"]) for r in ira["rows"]] == [("KKE-KK-03", 2, 1, 50.0),
		("KKE-KK-05", 9, 2, 22.2)] and (ira["so_ma"], ira["so_ma_khop"], ira["ty_le"]) == (11, 3, 27.3), ira)

	# ═══ K10.1 Kiểm kê sx trong tháng (theo ngày hiệu lực) ═══
	ks = d["kk_sx"]
	# KK-05 tại kho TP (chốt + bù, dòng sổ sống, phiếu còn hiệu lực):
	#   TP1 −10 + 4 = −6 → thiếu −500.000 + 200.000 = −300.000 (D191 ở CH1 −7.000 không tính)
	#   TP2 +6 → thừa +180.000 (dòng sổ huỷ −50, phiếu huỷ lẻ +100, phiếu bù đã huỷ không tính)
	#   TP3 0 → chênh giá −1.000 · TP4 −8 + 3 = −5 → thiếu −100.000 · TP5 −12 → −300.000 · TP8 −3 → −30.000
	#   TP9 +5 giá 0 → thừa 0 · TP10 −6 → −90.000
	# thừa 180.000 · thiếu −300.000 − 100.000 − 300.000 − 30.000 − 90.000 = −820.000 · chênh giá −1.000
	# · ròng 180.000 − 820.000 − 1.000 = −641.000 · trong đó bù D216 +200.000.
	c("K10.1 chỉ KK-05 (KK-02 chốt 03/10 nhưng hiệu lực 30/09; KK-13 công ty khác)",
		[(r["phieu"], r["kho"], r["ngay"]) for r in ks["rows"]] == [("KKE-KK-05", TP, "2026-10-15")] and ks["so_lan"] == 1,
		ks["rows"])
	c("K10.1 thừa 180.000 / thiếu −820.000 / chênh giá −1.000 / ròng −641.000 / bù D216 200.000",
		(ks["gt_thua"], ks["gt_thieu"], ks["gt_chenh_gia"], ks["gt_rong"], ks["gt_bu"]) == (180_000, -820_000, -1_000, -641_000,
		200_000), ks)
	c("K10.1 2 mã thừa (TP2, TP9), 5 mã thiếu (TP1, TP4, TP5, TP8, TP10), 1 mã lệch số mà không có tiền (TP9 giá 0)",
		(ks["so_ma_thua"], ks["so_ma_thieu"], ks["so_ma_gia_0"]) == (2, 5, 1), ks)
	r5 = ks["rows"][0]
	# Thừa 6 + 5 = 11 hộp = 6/12 + 5/6 = 1,33 thùng; thiếu 6 + 5 + 12 + 3 + 6 = 32 hộp = 6/20 + 5/24 + 3/10 + 6/12
	# = 0,3 + 0,208 + 0,3 + 0,5 = 1,31 thùng + 12 hộp (TP5) chưa khai thùng.
	c("K10.1 số lượng theo lần kiểm: thừa 11 hộp (1,3 thùng), thiếu 32 hộp (1,3 thùng + 12 hộp chưa khai thùng)",
		r5["thua"] == {"qty": 11, "uom": "Hộp", "cartons": 1.3, "boxes_without_carton_factor": 0}
		and r5["thieu"] == {"qty": 32, "uom": "Hộp", "cartons": 1.3, "boxes_without_carton_factor": 12}, (r5["thua"], r5["thieu"]))
	c("K10.1 phiếu kho của lần kiểm đã chốt bị huỷ lẻ: 1 phiếu / 1 lần kiểm (phiếu bù D216 sx tự huỷ không tính)",
		ks["phieu_huy_le"] == {"so_phieu": 1, "so_kiem_ke": 1}, ks["phieu_huy_le"])

	# ═══ K10.2 Kiểm kê cửa hàng ═══
	kc = d["kk_ch"]
	# (TP1, CH3) −5 + 6 = +1 → thừa +50.000; (TP2, CH3) +2 → thừa +60.000; (TP4, CH3) −3 → thiếu −60.000;
	# (TP2, trả về) −3 → thiếu −90.000; chỉ đổi giá: TP6 CH3 +15.000, TP2 CH3 −2.200 → 12.800.
	c("K10.2 thừa 110.000 / thiếu −150.000 / đổi giá 12.800 / ròng −27.200", (kc["gt_thua"], kc["gt_thieu"], kc["gt_doi_gia"],
		kc["gt_rong"]) == (110_000, -150_000, 12_800, -27_200), kc)
	c("K10.2 3 phiếu, 2 kho, 2 cặp mã–kho thừa, 2 thiếu, 2 dòng chỉ đổi giá", (kc["so_phieu"], kc["so_kho"], kc["so_ma_thua"],
		kc["so_ma_thieu"], kc["so_dong_doi_gia"]) == (3, 2, 2, 2, 2), kc)
	c("K10.2 theo kho: trả về −90.000 (1 phiếu), CH3 thừa 110.000 / thiếu −60.000 / đổi giá 12.800 = 62.800 (2 phiếu)",
		[(r["kho"], r["gt_thua"], r["gt_thieu"], r["gt_doi_gia"], r["gt_rong"], r["so_phieu"]) for r in kc["rows"]]
		== [(TRA_VE, 0, -90_000, 0, -90_000, 1), (CH3, 110_000, -60_000, 12_800, 62_800, 2)], kc["rows"])

	# ═══ K10.3 Dọn tồn sx ═══
	ds = d["don_sx"]
	c("K10.3 dọn tồn không lô −50.000 (2 phiếu), dọn âm TP +120.000 (1), dọn âm lịch sử lô 0 (2, ẩn) → +70.000, 5 phiếu",
		[(r["key"], r["gia_tri"], r["so_phieu"], r["hien"]) for r in ds["rows"]] == [("don_khong_lo", -50_000, 2, True),
		("don_am_lo", 0, 2, False), ("don_am_tp", 120_000, 1, True)] and (ds["gia_tri"], ds["so_phieu"]) == (70_000, 5), ds)

	# ═══ K10.4 Xuất khác ═══
	xk = d["xuat_khac"]
	c("K10.4 xuất khác 360.000 / 3 phiếu (bỏ kiểm kê, dọn tồn, bù nợ BOM, đầu kỳ, phiếu huỷ, tháng 9, công ty khác)",
		(xk["gia_tri"], xk["so_phieu"]) == (360_000, 3), xk)
	c("K10.4 theo loại: Xuất huỷ 300.000 (TP 250.000, CH1 50.000), Xuất mẫu 60.000 (CH1)",
		[(r["loai"], r["gia_tri"], r["so_phieu"], [(w["kho"], w["gia_tri"], w["so_phieu"]) for w in r["kho"]]) for r in xk["rows"]]
		== [("Xuất huỷ", 300_000, 2, [(TP, 250_000, 1), (CH1, 50_000, 1)]), ("Xuất mẫu", 60_000, 1, [(CH1, 60_000, 1)])],
		xk["rows"])

	# ═══ Tổng điều chỉnh = 1 + 2 + 3 − 4 ═══
	tg = d["tong"]
	c("tổng điều chỉnh = −641.000 − 27.200 + 70.000 − 360.000 = −958.200, đủ 4 dòng",
		(tg["gia_tri"], tg["day_du"], [x["gia_tri"] for x in tg["parts"]]) == (-958_200, True, [-641_000, -27_200, 70_000,
		-360_000]), tg)

	# ═══ Top chênh lệch / về 0 không đếm ═══
	tl = d["top_lech"]["rows"]
	c("top chênh lệch: |giá trị| giảm, cùng giá trị thì |số lượng| lớn trước; mã ẩn (TP8) bỏ; TP3 chỉ lệch giá không vào",
		[(r["item_code"], r["kho"], r["nguon"], r["qty"], r["value"]) for r in tl] == [
		("KKE-TP5", TP, "sx", -12, -300_000), ("KKE-TP1", TP, "sx", -6, -300_000), ("KKE-TP2", TP, "sx", 6, 180_000),
		("KKE-TP4", TP, "sx", -5, -100_000), ("KKE-TP10", TP, "sx", -6, -90_000), ("KKE-TP2", TRA_VE, "cua_hang", -3, -90_000),
		("KKE-TP4", CH3, "cua_hang", -3, -60_000), ("KKE-TP2", CH3, "cua_hang", 2, 60_000),
		("KKE-TP1", CH3, "cua_hang", 1, 50_000), ("KKE-TP9", TP, "sx", 5, 0)], tl)
	t1 = by(tl, "item_code", "KKE-TP1")
	c("top: thùng theo hệ số (TP1 −6/20 = −0,3; TP5 chưa khai → không), tên rút gọn, đơn vị, cờ giá 0, phiếu kiểm kê",
		(t1["cartons"], t1["short_name"], t1["uom"], t1["phieu"], t1["kho_label"], tl[0]["cartons"], tl[-1]["gia_0"],
		tl[0]["gia_0"]) == (-0.3, "KKE 1", "Hộp", "KKE-KK-05", "Thành phẩm", None, True, False), t1)
	v0 = d["ve_0"]
	# TP5 12 hộp −300.000; TP10: phần không thu hồi 6 → 0 không có dòng đếm (lô thu hồi 2 → 2 bỏ ra) → 6 hộp −90.000.
	c("về 0 vì không đếm: TP5 (12 hộp, −300.000), TP10 (6 hộp không tính lô thu hồi, −90.000); TP8 đếm số 0 không tính, TP7 "
		"chỉ có lô thu hồi không tính",
		(v0["so_ma"], v0["gia_tri"], [(r["phieu"], r["item_code"], r["so_luong"], r["gia_tri"]) for r in v0["rows"]])
		== (2, -390_000, [("KKE-KK-05", "KKE-TP5", 12, -300_000), ("KKE-KK-05", "KKE-TP10", 6, -90_000)]), v0)

	# ═══ Riêng tư + helper sx bị cấm + guard ═══
	dump = json.dumps(d, ensure_ascii=False, default=str)
	c("riêng tư: không email / người lập / ghi chú / lý do / remarks trong payload", not [p for p in PRIVATE if p in dump]
		and "@" not in dump and not re.search(r"owner|remarks|ghi_chu|nguoi_|ly_do|ds_se|xu_ly_boi", dump),
		[p for p in PRIVATE if p in dump])
	src = open(os.path.join(BC_ROOT, "bc", "api", "kho_kk.py"), encoding="utf-8").read()
	deny = ["_dong_du", "ma_lo_ton_cu", "prefix_lo", "gia_von_hien", "ghi_gia_tu_tinh", "lo_cu", "xu_ly", "soat"]
	c("không import helper sx (có ghi DB / giá mua / whitelisted)", not [x for x in deny if re.search(rf"\b{x}\b", src)]
		and not re.search(r"^\s*(from|import)\s+sx\b", src, re.M), [x for x in deny if re.search(rf"\b{x}\b", src)])
	tree = ast.parse(src)
	fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_overview")
	first = fn.body[1] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body[0]
	c("get_overview: câu đầu là _guard('kiem-ke'), chữ ký (thang=None, refresh=0)", isinstance(first, ast.Expr)
		and ast.unparse(first) == "_guard('kiem-ke')" and ast.unparse(fn.args) == "thang=None, refresh=0", ast.unparse(first))
	c("SQL không CURDATE / NOW / %", not re.search(r"CURDATE|NOW\(\)|LIKE", src) and "%'" not in src and "'%" not in src)
	frappe.session.user = "nobody@example.com"
	try:
		ov()
		c("người không có vai trò bị chặn", False)
	except frappe.PermissionError:
		c("người không có vai trò bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"

	# ═══ Tháng 9 (C7 chiều ngược lại) ═══
	d9 = ov("2026-09")
	k9 = d9["kk_sx"]
	# KK-02 hiệu lực 30/09: TP1 −2 → thiếu −100.000; TP2 +1 + 3 (bù D216 ghi 02/10) = +4 → thừa +120.000 → ròng 20.000.
	c("tháng 9: kỳ 01/09 → 30/09", (d9["meta"]["thang"], d9["meta"]["from"], d9["meta"]["to"], d9["meta"]["prev"])
		== ("2026-09", "2026-09-01", "2026-09-30", "2026-08"), d9["meta"])
	c("tháng 9 K10.1: KK-02 (chốt tháng 10, hiệu lực 30/09) gồm cả phiếu bù ghi 02/10: thừa 120.000 / thiếu −100.000 / bù 90.000",
		([r["phieu"] for r in k9["rows"]], k9["gt_thua"], k9["gt_thieu"], k9["gt_rong"], k9["gt_bu"]) == (["KKE-KK-02"],
		120_000, -100_000, 20_000, 90_000), k9)
	c("tháng 9 K10.2: CH1 −60.000, CH2 +40.000 → −20.000, 2 phiếu", (d9["kk_ch"]["gt_thua"], d9["kk_ch"]["gt_thieu"],
		d9["kk_ch"]["gt_rong"], d9["kk_ch"]["so_phieu"]) == (40_000, -60_000, -20_000, 2), d9["kk_ch"])
	c("tháng 9 dọn tồn +30.000, xuất khác 20.000 (Xuất huỷ CH2), tổng 20.000 − 20.000 + 30.000 − 20.000 = 10.000",
		(d9["don_sx"]["gia_tri"], d9["xuat_khac"]["gia_tri"], d9["tong"]["gia_tri"]) == (30_000, 20_000, 10_000),
		(d9["don_sx"], d9["xuat_khac"], d9["tong"]))
	c("tháng 9 huỷ chốt: KK-10 (hiệu lực 25/09, mở lại)", [(r["phieu"], r["mo_lai"]) for r in d9["huy_chot"]["rows"]]
		== [("KKE-KK-10", True)], d9["huy_chot"])
	c("tháng 9 về 0 không đếm: không có; top chỉ KK-02 + cửa hàng tháng 9", d9["ve_0"]["so_ma"] == 0
		and [(r["item_code"], r["kho"], r["value"]) for r in d9["top_lech"]["rows"]] == [("KKE-TP2", TP, 120_000),
		("KKE-TP1", TP, -100_000), ("KKE-TP2", CH1, -60_000), ("KKE-TP6", CH2, 40_000)], d9["top_lech"])
	c("tháng 9: bảng kho / độ chính xác là ảnh chụp hôm nay (như tháng 10), chỉ số lần trong kỳ đổi",
		kho_rows(d9) == exp and d9["ira"]["ty_le"] == 27.3 and [(r["kho"], r["so_lan_trong_ky"]) for r in d9["kho"]["rows"]
		if r["so_lan_trong_ky"]] == [(CH2, 1), (CH1, 1), (TP, 1)], [(r["kho"], r["so_lan_trong_ky"]) for r in d9["kho"]["rows"]])
	c("tháng tương lai / sai dạng → tháng này", ov("2026-11")["meta"]["thang"] == "2026-10" and ov("abc")["meta"]["thang"]
		== "2026-10")

	# ═══ Thiếu cột của sx bản sau (thoi_diem, cach_dem, bat_dau_luc, ghi_chu) ═══
	for col in ("thoi_diem", "cach_dem", "bat_dau_luc", "ghi_chu"):
		drop_column("SX Kiem Ke", col)
	d2 = ov()
	k2 = d2["kk_sx"]
	# Không thoi_diem: KK-02 hiệu lực = chot 03/10 → vào tháng 10: thêm thừa 120.000 / thiếu −100.000 / bù 90.000
	# → thừa 300.000, thiếu −920.000, ròng −641.000 + 20.000 = −621.000, bù 290.000.
	c("thiếu thoi_diem: KK-02 tính theo chot_luc (03/10) → tháng 10 có 2 lần kiểm", ([r["phieu"] for r in k2["rows"]],
		k2["gt_thua"], k2["gt_thieu"], k2["gt_rong"], k2["gt_bu"]) == (["KKE-KK-02", "KKE-KK-05"], 300_000, -920_000, -621_000,
		290_000), k2)
	t2 = by(d2["kho"]["rows"], "kho", TP)
	b2 = by(d2["kho"]["rows"], "kho", BTP)
	c("thiếu cột: TP vẫn KK-05, cách đếm mặc định 'Kèm hạn sử dụng'; BTP KK-03 (KK-04 hết thoi_diem cũng 29/07)",
		(t2["phieu"], t2["cach_dem"], b2["phieu"], b2["so_ngay"]) == ("KKE-KK-05", "Kèm hạn sử dụng", "KKE-KK-03", 90), (t2, b2))
	dd2 = d2["dang_dem"]["rows"]
	c("thiếu bat_dau_luc: tuổi từ creation (KK-08 20/10 → 7 ngày, KK-14 25/10 → 2), không có ngày chốt sổ",
		[(r["phieu"], r["tuoi"], r["thoi_diem"], r["cach_dem"], r["cu"]) for r in dd2] == [
		("KKE-KK-08", 7, None, "Kèm hạn sử dụng", True), ("KKE-KK-14", 2, None, "Kèm hạn sử dụng", True),
		("KKE-KK-11", 1, None, None, False)], dd2)
	hc2 = d2["huy_chot"]
	c("thiếu ghi_chu: không nhận ra 'mở lại'; KK-10 hiệu lực theo chot 06/10 → vào tháng 10 (KK-15 công ty khác vẫn bỏ)",
		([r["phieu"] for r in hc2["rows"]], hc2["so_mo_lai"]) == (["KKE-KK-09", "KKE-KK-10", "KKE-KK-16", "KKE-KK-07"], 0), hc2)
	drop_column("SX Kiem Ke", "loai")
	d3 = ov()
	c("thiếu loai (sx cũ): mọi lần kiểm là Thành phẩm, không lỗi", d3["kho"]["available"] and by(d3["kho"]["rows"], "kho", TP)
		["phieu"] == "KKE-KK-05" and d3["kk_sx"]["available"] and d3["ira"]["available"], by(d3["kho"]["rows"], "kho", TP))

	# ═══ Kho sx có phiếu kiểm kho (Stock Reconciliation) — K9 lấy lần đếm MỚI NHẤT, khớp với K10.2 cùng màn ═══
	main_seed(extra=seed_sr_kho_sx)
	ds = ov()
	# BTP 25/10 = 2 ngày (không còn "90 ngày cảnh báo"); xưởng 20/09 = 37 ngày → cảnh báo; TP vẫn KK-05 15/10 (hoà).
	c("K9 kho sx có phiếu kiểm kho mới hơn: hiện ngày phiếu đó; thứ tự / mức theo ngày mới", kho_rows(ds) == [
		(NVL, None, "sr", None, None, "chua"), (KHO_CU, None, "sr", None, None, "chua"),
		(CH4, None, "sr", "2026-07-28", 91, "nguy"), (XUONG, BTP_L, "sx", "2026-09-20", 37, "canh_bao"),
		(CH2, None, "sr", "2026-09-26", 31, "canh_bao"), (CH1, None, "sr", "2026-09-27", 30, "ok"),
		(TP, TP_L, "sx", "2026-10-15", 12, "ok"), (CH3, None, "sr", "2026-10-20", 7, "ok"),
		(BTP, BTP_L, "sx", "2026-10-25", 2, "ok")] and ds["kho"]["tong"] == {"so_kho": 9, "chua_kiem": 2, "qua_30": 3,
		"qua_90": 1}, (kho_rows(ds), ds["kho"]["tong"]))
	sb, st, sw = (by(ds["kho"]["rows"], "kho", w) for w in (BTP, TP, XUONG))
	c("K9 nguồn ngày: BTP phiếu kiểm kho (sx đếm lần cuối 29/07, vẫn KK-03, 1 lần trong tháng); TP hoà 15/10 → sx, 1 + 2 = 3 "
		"lần; xưởng chỉ phiếu kiểm kho (Opening Stock 26/10 không tính, phiếu 30/10 tương lai không tính)",
		[(r.get("nguon_ngay"), r.get("ngay_sx"), r.get("ngay_sr"), r["phieu"], r["so_lan_trong_ky"], r["dang_dem"])
		for r in (sb, st, sw)]
		== [("sr", "2026-07-29", "2026-10-25", "KKE-KK-03", 1, True), ("sx", "2026-10-15", "2026-10-15", "KKE-KK-05", 3, True),
		("sr", None, "2026-09-20", None, 0, False)] and st["cach_dem"] == "Chỉ số lượng", (sb, st, sw))
	ch_kho = {r["kho"] for r in ds["kk_ch"]["rows"]}
	c("K9 khớp K10.2: kho sx nào có phiếu kiểm kho trong tháng thì bảng kho không báo cũ hơn phiếu đó",
		{BTP, TP} <= ch_kho and all(r["so_lan_trong_ky"] >= 1 and r["ngay"] >= "2026-10-01" for r in ds["kho"]["rows"]
		if r["kho"] in ch_kho), [(r["kho"], r["ngay"]) for r in ds["kho"]["rows"] if r["kho"] in ch_kho])

	# ═══ Khối lỗi giữa chừng: thiếu cột viec của biên bản lô → chỉ độ chính xác / về 0 tắt ═══
	main_seed()
	drop_column("SX Kiem Ke Lo", "viec")
	frappe.LOGGED.clear()
	d4 = ov()
	c("một khối lỗi không làm hỏng trang: ira, ve_0 = {available: False, error: True}; còn lại vẫn đúng",
		d4["ira"] == {"available": False, "error": True} and d4["ve_0"] == {"available": False, "error": True}
		and d4["kk_sx"]["gt_rong"] == -641_000 and d4["tong"]["gia_tri"] == -958_200 and len(frappe.LOGGED) == 2,
		(d4["ira"], d4["ve_0"], len(frappe.LOGGED)))

	# ═══ Thiếu cột Stock Entry.custom_kiem_ke (sx vẫn cài) ═══
	main_seed()
	drop_column("Stock Entry", "custom_kiem_ke")
	d5 = ov()
	# Không nhận ra phiếu kiểm kê: MI của KK-05 ở TP (500.000 + 160.000 + 300.000 + 30.000 + 90.000 = 1.080.000) + đổi cờ lô
	# ở CH1 (350.000) thành xuất kho không ghi loại → xuất khác 360.000 + 1.430.000 = 1.790.000.
	c("thiếu custom_kiem_ke: K10.1 tắt (thiếu cột), về 0 vẫn đếm mã nhưng không có tiền, top chỉ cửa hàng",
		d5["kk_sx"] == {"available": False, "reason": "thieu_cot"} and (d5["ve_0"]["so_ma"], d5["ve_0"]["gia_tri"]) == (2, None)
		and {r["nguon"] for r in d5["top_lech"]["rows"]} == {"cua_hang"} and d5["meta"]["kiem_ke_col"] is False, d5["ve_0"])
	c("thiếu custom_kiem_ke: xuất khác 1.790.000 (thêm 'Xuất kho (không ghi loại)' 1.430.000), tổng không đủ dòng",
		(d5["xuat_khac"]["gia_tri"], by(d5["xuat_khac"]["rows"], "loai", "Material Issue")["label"],
		by(d5["xuat_khac"]["rows"], "loai", "Material Issue")["gia_tri"], d5["tong"]["day_du"], d5["tong"]["gia_tri"])
		== (1_790_000, "Xuất kho (không ghi loại)", 1_430_000, False, -27_200 + 120_000 - 1_790_000), d5["xuat_khac"])
	# Phiếu "Dọn tồn không lô…" của lần kiểm KK-05 (+50.000) không còn nhận ra là kiểm kê → sang dọn tồn: −50.000 + 50.000 = 0.
	c("thiếu custom_kiem_ke: dọn tồn không lô 0 (phiếu dọn trong lần kiểm sang dọn tồn), tổng dọn tồn 120.000",
		[(r["key"], r["gia_tri"]) for r in d5["don_sx"]["rows"]] == [("don_khong_lo", 0), ("don_am_lo", 0), ("don_am_tp", 120_000)],
		d5["don_sx"])

	# ═══ Site không cài sx ═══
	main_seed(sx=False)
	frappe.INSTALLED_APPS.remove("sx")
	try:
		d6 = ov()
		c("không sx: các khối sx báo khong_sx, khối khác vẫn có", d6["meta"]["sx"] is False and all(d6[b] == {"available": False,
			"reason": "khong_sx"} for b in ("dang_dem", "huy_chot", "ira", "kk_sx", "don_sx", "ve_0")), {b: d6[b] for b in
			("dang_dem", "kk_sx", "don_sx")})
		# Không SX Settings: trả về / cách ly / xưởng / BTP / NVL / kho cũ thành "kho khác" bán được; mọi kho có tồn theo
		# Stock Reconciliation: TP chưa kiểm (vai trò tp đứng đầu), các kho khác chưa kiểm theo tên, rồi ngày giảm dần.
		c("không sx: K9 chỉ theo Stock Reconciliation", kho_rows(d6) == [(TP, None, "sr", None, None, "chua"),
			(BTP, None, "sr", None, None, "chua"), (NVL, None, "sr", None, None, "chua"),
			(XUONG, None, "sr", None, None, "chua"), (CACH_LY, None, "sr", None, None, "chua"),
			(KHO_CU, None, "sr", None, None, "chua"), (CH4, None, "sr", "2026-07-28", 91, "nguy"),
			(CH2, None, "sr", "2026-09-26", 31, "canh_bao"), (CH1, None, "sr", "2026-09-27", 30, "ok"),
			(TRA_VE, None, "sr", "2026-10-15", 12, "ok"), (CH3, None, "sr", "2026-10-20", 7, "ok")], kho_rows(d6))
		c("không sx: kiểm kê cửa hàng, xuất khác như cũ; tổng −27.200 − 360.000 = −387.200 (không đủ dòng)",
			(d6["kk_ch"]["gt_rong"], d6["xuat_khac"]["gia_tri"], d6["tong"]["gia_tri"], d6["tong"]["day_du"])
			== (-27_200, 360_000, -387_200, False) and [x["available"] for x in d6["tong"]["parts"]] == [False, True, False, True],
			d6["tong"])
		c("không sx: top chênh lệch chỉ cửa hàng", [(r["item_code"], r["kho"]) for r in d6["top_lech"]["rows"]] == [
			("KKE-TP2", TRA_VE), ("KKE-TP4", CH3), ("KKE-TP2", CH3), ("KKE-TP1", CH3)], d6["top_lech"])
	finally:
		frappe.INSTALLED_APPS.append("sx")

	# ═══ sx cài nhưng thiếu bảng SX Kiem Ke Dong (bản sx cũ) → như không sx; thiếu Stock Reconciliation ═══
	main_seed()
	drop_doctype("SX Kiem Ke Dong")
	d7 = ov()
	c("thiếu bảng SX Kiem Ke Dong: khối sx tắt, K9 theo Stock Reconciliation (TP chưa kiểm)", d7["kk_sx"]["available"] is False
		and d7["meta"]["sx"] is False and {r["nguon"] for r in d7["kho"]["rows"]} == {"sr"}
		and by(d7["kho"]["rows"], "kho", TP)["muc"] == "chua", d7["kk_sx"])
	main_seed()
	drop_doctype("Stock Reconciliation Item")
	d8 = ov()
	c("thiếu bảng Stock Reconciliation Item: K10.2 tắt, cửa hàng 'chưa kiểm kê', sx vẫn đủ",
		d8["kk_ch"] == {"available": False, "reason": "thieu_bang"} and by(d8["kho"]["rows"], "kho", CH3)["muc"] == "chua"
		and d8["kk_sx"]["gt_rong"] == -641_000 and d8["tong"]["gia_tri"] == -641_000 + 70_000 - 360_000, d8["kk_ch"])

	# ═══ Site trống / chưa có công ty ═══
	reset()
	bc_settings()
	k0 = K()
	base(k0)
	k0.finalize()
	d0 = ov()
	c("site chưa có sổ kho: mọi khối có, số 0, 3 kho sx chưa kiểm", d0["available"] and all(d0[b].get("available") for b in
		blocks) and kho_rows(d0) == [(TP, TP_L, "sx", None, None, "chua"), (XUONG, BTP_L, "sx", None, None, "chua"),
		(BTP, BTP_L, "sx", None, None, "chua")] and (d0["kk_sx"]["gt_rong"], d0["kk_ch"]["gt_rong"], d0["xuat_khac"]["gia_tri"],
		d0["tong"]["gia_tri"], d0["ira"]["ty_le"], d0["top_lech"]["rows"], d0["ve_0"]["so_ma"]) == (0, 0, 0, 0, None, [], 0),
		kho_rows(d0))
	frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'Global Defaults'")
	dn = ov()
	c("chưa khai công ty → available False (không 500)", dn["available"] is False and dn["meta"]["thang"] == "2026-10", dn)
	c.done()
