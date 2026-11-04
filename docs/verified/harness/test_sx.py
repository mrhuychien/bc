"""Số sản xuất của bc: Manufacture (dòng thành phẩm) + Material Receipt trừ phiếu điều chỉnh của sx.

Chạy: python3 test_sx.py   (cần MariaDB + schema.py). Thử phá: BC_APP_ROOT trỏ bản cũ → phải đỏ.
"""
import datetime
import json

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset

import frappe

TODAY = "2026-10-27"
TP, XUONG, BTP = "Thành phẩm - HGC", "Kho Xưởng - HGC", "Bán thành phẩm - HGC"


def se(purpose, rows, docstatus=1, remarks=None, kiem_ke=None, date=TODAY, time="09:00:00", has_kk=True, name=None,
		creation=None):
	extra = {"custom_kiem_ke": kiem_ke} if has_kk else {}
	name = insert("Stock Entry", name=name, creation=creation or f"{date} {time}", docstatus=docstatus, purpose=purpose, stock_entry_type=purpose, posting_date=date,
		posting_time=time, remarks=remarks, company="HGC", **extra)
	for i, r in enumerate(rows, 1):
		insert("Stock Entry Detail", parent=name, parenttype="Stock Entry", parentfield="items", idx=i, docstatus=docstatus,
			item_name=r["item_code"], **r)
	return name


def seed(has_kk=True):
	bc_settings()
	for i, (w, parent) in enumerate([(TP, None), (XUONG, None), (BTP, None)]):
		insert("Warehouse", name=w, warehouse_name=w.split(" - ")[0], lft=10 * i + 1, rgt=10 * i + 2, is_group=0)
	insert("Item", name="TET1", item_name="Bánh đậu xanh Tết hộp quà", item_group="Hàng Tết", stock_uom="Hộp")
	insert("Item", name="TRAD1", item_name="Bánh đậu xanh truyền thống", item_group="Hàng truyền thống", stock_uom="Hộp")
	insert("Item", name="BOT", item_name="Bột đậu", item_group="Nguyên liệu", stock_uom="Kg")
	insert("UOM Conversion Detail", parent="TET1", parenttype="Item", parentfield="uoms", uom="Thùng", conversion_factor=12)
	insert("UOM Conversion Detail", parent="TRAD1", parenttype="Item", parentfield="uoms", uom="Thùng", conversion_factor=20)
	kw = {"has_kk": has_kk}
	# 1. Sản xuất có BOM (app sx: WO + Manufacture): dòng NL, dòng TP, dòng phế phẩm
	se("Manufacture", [
		{"item_code": "BOT", "s_warehouse": XUONG, "transfer_qty": 30, "qty": 30, "amount": 900},
		{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 120, "qty": 120, "is_finished_item": 1, "amount": 6000},
		{"item_code": "BOT", "t_warehouse": TP, "transfer_qty": 5, "qty": 5, "secondary_item_type": "Scrap", "amount": 50},
	], remarks="Phiếu nhập TP PNTP-0001", time="08:15:00", **kw)
	# 2. Hàng chưa có BOM — Material Receipt "Nhập tạm" (sx D97)
	se("Material Receipt", [{"item_code": "TRAD1", "t_warehouse": TP, "transfer_qty": 40, "qty": 40, "amount": 800}],
		remarks="Nhập tạm — PNTP-0002 chưa có BOM", time="09:20:00", **kw)
	# 3. Kiểm kê thừa (custom_kiem_ke)
	se("Material Receipt", [{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 30, "qty": 30}],
		remarks="Kiểm kê KK-0001: nhập phần thừa", kiem_ke="KK-0001" if has_kk else None, **kw)
	# 4. Dọn tồn không lô (lo_cu.py)
	se("Material Receipt", [{"item_code": "TRAD1", "t_warehouse": TP, "transfer_qty": 10, "qty": 10}],
		remarks="Dọn tồn không lô sau bật lô [DL-261027-101500]: TRAD1 — phần không lô", **kw)
	# 5. Dọn âm lịch sử lô (lo_am.py)
	se("Material Receipt", [{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 7, "qty": 7}],
		remarks="Dọn âm lịch sử lô (D207) [LA-1]: lô X ở TP âm 7", **kw)
	# 6. Phiếu nhập tay kiểu cũ (trước khi có app sx) — vẫn là sản xuất
	se("Material Receipt", [{"item_code": "TRAD1", "t_warehouse": TP, "transfer_qty": 20, "qty": 20, "amount": 400}],
		remarks=None, time="10:05:00", **kw)
	# 7. Repack chuyển lô lúc kiểm kê vào TP — không phải sản xuất
	se("Repack", [{"item_code": "TET1", "s_warehouse": TP, "transfer_qty": 50, "qty": 50},
		{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 50, "qty": 50, "is_finished_item": 1}],
		remarks="Kiểm kê KK-0001: chuyển lô", **kw)
	# 8. Manufacture bán thành phẩm vào kho BTP
	se("Manufacture", [{"item_code": "BOT", "t_warehouse": BTP, "transfer_qty": 80, "qty": 80, "is_finished_item": 1}], **kw)
	# 9. Manufacture đã huỷ
	se("Manufacture", [{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 99, "qty": 99, "is_finished_item": 1}],
		docstatus=2, **kw)
	# 10. Dọn tồn âm (tonam.py) — dù lỡ vào TP vẫn loại
	se("Material Receipt", [{"item_code": "TET1", "t_warehouse": TP, "transfer_qty": 3, "qty": 3}],
		remarks="Dọn tồn âm thành phẩm [TA-1] ở TP: tồn âm do chuyển ra", **kw)


def kiem_ke(name, kho, chot, lo, xuat=None, docstatus=1, thoi_diem=None, dem=()):
	"""SX Kiem Ke đã chốt + biên bản lô (SX Kiem Ke Lo: (mã, số trước, số sau[, việc])) + dòng đếm (SX Kiem Ke Dong,
	`dem`: [(mã, số đếm)] — "Không còn" = số 0) + phiếu kho xuất của lần kiểm kê (custom_kiem_ke) và dòng sổ kho của nó
	ở `kho` — xuat: {mã: số xuất} (mặc định = số trước − số sau)."""
	insert("SX Kiem Ke", name=name, docstatus=docstatus, kho=kho, chot_luc=chot, thoi_diem=thoi_diem, ngay=chot[:10])
	for i, row in enumerate(lo, 1):
		item, truoc, sau = row[:3]
		insert("SX Kiem Ke Lo", parent=name, parenttype="SX Kiem Ke", parentfield="lo", idx=i, item=item,
			batch=f"{item}-L{i}", so_truoc=truoc, so_sau=sau, viec=row[3] if len(row) > 3 else None)
	for i, (item, so) in enumerate(dem, 1):
		insert("SX Kiem Ke Dong", parent=name, parenttype="SX Kiem Ke", parentfield="dong", idx=i, item=item, so_dem=so)
	ra = xuat if xuat is not None else {item: r[1] - r[2] for r in lo for item in [r[0]] if r[1] - r[2]}
	if not ra:
		return
	xuat_kk(name, kho, chot, ra, docstatus, f"Kiểm kê {name}: xuất hết tồn KHÔNG LÔ")


def xuat_kk(kk, kho, luc, ra, docstatus=1, remarks=None):
	"""Phiếu xuất mang custom_kiem_ke = kk + dòng sổ kho (ra: {mã: số xuất})."""
	ph = se("Material Issue", [{"item_code": k, "s_warehouse": kho, "transfer_qty": q, "qty": q} for k, q in ra.items()],
		docstatus=docstatus, remarks=remarks, kiem_ke=kk, date=luc[:10], time=luc[11:19])
	for k, q in ra.items():
		insert("Stock Ledger Entry", item_code=k, warehouse=kho, actual_qty=-q, voucher_type="Stock Entry", voucher_no=ph,
			posting_date=luc[:10], posting_time=luc[11:19], posting_datetime=luc, is_cancelled=1 if docstatus == 2 else 0,
			company="HGC")
	return ph


def seed_nhap_lai():
	"""Kiểm kê đưa mã về 0 rồi nhập lại đúng số đó (KK-2026-002, 10/2026). Kho TP = Thành phẩm - HGC; Xưởng tính sản xuất."""
	seed()
	frappe.db.set_single_value("SX Settings", "kho_xuong", XUONG)
	for code in ("DTL", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10", "X11", "X12", "X13", "X14", "X15", "X16"):
		insert("Item", name=code, item_name=f"Bánh {code}", item_group="Hàng Tết", stock_uom="Hộp")
	insert("UOM Conversion Detail", parent="DTL", parenttype="Item", parentfield="uoms", uom="Thùng", conversion_factor=20)
	mr = lambda code, q, d, name=None, t="09:00:00", rows=None, creation=None, remarks=None: se(  # noqa: E731
		"Material Receipt", rows or [{"item_code": code, "t_warehouse": TP, "transfer_qty": q, "qty": q}],
		remarks=remarks or f"Nhập tạm — {code} chưa có BOM", date=d, time=t, name=name, creation=creation)
	# Hàng vào Kho TP trước kiểm kê (sản xuất thật)
	se("Material Transfer", [{"item_code": "DTL", "s_warehouse": XUONG, "t_warehouse": TP, "transfer_qty": 100, "qty": 100}],
		date="2026-10-07")
	mr("X2", 50, "2026-10-12", t="09:00:00")   # sản xuất sáng 12/10, ĐÚNG số — TRƯỚC giờ chốt kiểm kê 15:07 → không bỏ
	for code, q, d in (("X3", 30, "2026-10-03"), ("X10", 30, "2026-10-03"), ("X4", 40, "2026-10-03"),
			("X5", 20, "2026-10-03"), ("X6", 25, "2026-10-03"), ("X7", 70, "2026-10-03"), ("X8", 40, "2026-10-03"),
			("X9", 15, "2026-10-01"), ("X11", 12, "2026-10-03"), ("X13", 20, "2026-10-03"), ("X14", 15, "2026-10-03"),
			("X15", 8, "2026-10-03")):
		mr(code, q, d)
	se("Material Transfer", [{"item_code": "X12", "s_warehouse": XUONG, "t_warehouse": TP, "transfer_qty": 46, "qty": 46}],
		date="2026-10-08")
	# KK-T1 chốt 12/10 15:07 ở Kho TP: DTL (2 lô 60 + 40 → 0), X2, X3, X10, X8 về 0; X4 còn 10 (không về 0);
	# X7 biên bản 70 → 0 nhưng sổ chỉ xuất 60 (lệch — không đoán).
	# X11, X12, X13 về 0 (không đếm); X14: lô thường 10 → 0, lô ĐANG THU HỒI 5 giữ nguyên ("không kiểm"); X15 bấm
	# "Không còn" (dòng đếm 0) → hàng hết thật, không xét nhập lại.
	kiem_ke("KK-T1", TP, "2026-10-12 15:07:08", [("DTL", 60, 0), ("DTL", 40, 0), ("X2", 50, 0), ("X3", 30, 0), ("X10", 30, 0),
		("X4", 40, 10), ("X7", 70, 0), ("X8", 40, 0), ("X11", 12, 0), ("X12", 46, 0), ("X13", 20, 0), ("X14", 10, 0),
		("X14", 5, 5, "đang thu hồi — không kiểm (5)"), ("X15", 8, 0)], dem=[("X15", 0)],
		xuat={"DTL": 100, "X2": 50, "X3": 30, "X10": 30, "X4": 30, "X7": 60, "X8": 40, "X11": 12, "X12": 46, "X13": 20,
			"X14": 10, "X15": 8})
	# Phiếu bù chứng từ ghi lùi D216 cũng mang custom_kiem_ke = KK-T1 (bán POS trước lúc đếm, gộp sau chốt) — X13 −3.
	xuat_kk("KK-T1", TP, "2026-10-12 11:00:00", {"X13": 3}, remarks="Bù chứng từ ghi lùi sau kiểm kê (D216): KK-T1 — POS")
	kiem_ke("KK-T2", TP, "2026-10-12 16:00:00", [("X5", 20, 0)], docstatus=2)          # đã huỷ
	kiem_ke("KK-X", XUONG, "2026-10-12 16:30:00", [("X6", 25, 0)])                      # kho khác
	# X16: sản xuất 25 ngày 14/10 (SAU lần kiểm kê KK-T1, TRƯỚC KK-T3) — đúng số mà KK-T3 sẽ đưa về 0 nhưng là sản xuất thật.
	mr("X16", 25, "2026-10-14")
	kiem_ke("KK-T3", TP, "2026-10-20 10:00:00", [("X9", 15, 0), ("X16", 25, 0)])
	mr("X16", 25, "2026-10-22", name="SE-NL-X16")
	# Sau kiểm kê
	mr("DTL", 60, "2026-10-15")                                  # khác số → sản xuất thật
	mr("DTL", 100, "2026-10-20", name="SE-NL-DTL-2")             # ĐÚNG số, đầu tiên → nhập lại
	mr("DTL", 100, "2026-10-22")                                 # đúng số lần hai → sản xuất thật (đã ghép phiếu trên)
	mr("X3", 30, "2026-12-12")                                   # ngày thứ 61 → ngoài cửa sổ
	mr("X10", 30, "2026-12-11", name="SE-NL-X10", t="15:07:08")  # tạo đúng giây cuối của 60 ngày → còn trong cửa sổ
	mr("X4", 30, "2026-10-15")
	mr("X5", 20, "2026-10-15")
	mr("X6", 25, "2026-10-15")
	mr("X7", 70, "2026-10-15")
	mr("X8", 0, "2026-10-15", name="SE-NL-X8", rows=[{"item_code": "X8", "t_warehouse": TP, "transfer_qty": 25, "qty": 25},
		{"item_code": "X8", "t_warehouse": TP, "transfer_qty": 15, "qty": 15}])   # hai dòng lô cộng 40
	mr("X9", 15, TODAY, name="SE-NL-X9", t="11:00:00")             # nhập lại hôm nay
	# X11: phiếu Nhập TP lập ngày 12/10 (ngày ghi sổ = ngày lập, giờ = lúc duyệt 08:40 hôm sau) → giờ ghi sổ TRƯỚC giờ chốt
	# nhưng TẠO sau giờ chốt → nhập lại.
	mr("X11", 12, "2026-10-12", name="SE-NL-X11", t="08:40:00", creation="2026-10-13 08:40:00")
	# X12: MỘT phiếu Nhập TP hai lô hạn dùng → sx ghi HAI phiếu kho (30 + 16 = 46) — gộp theo phiếu Nhập TP.
	a12 = mr("X12", 30, "2026-10-15", name="SE-X12-1", t="10:00:00", remarks="Nhập tạm — X12 chưa có BOM (phiếu PNTP-X12 dòng 1)")
	b12 = mr("X12", 16, "2026-10-15", name="SE-X12-2", t="10:00:00", remarks="Nhập tạm — X12 chưa có BOM (phiếu PNTP-X12 dòng 2)")
	insert("SX Phieu Nhap TP", name="PNTP-X12", docstatus=1, ngay="2026-10-15", kho_dich=TP,
		ds_se=json.dumps([{"dt": "Stock Entry", "name": a12}, {"dt": "Stock Entry", "name": b12}]))
	mr("X13", 20, "2026-10-16", name="SE-NL-X13")
	mr("X14", 10, "2026-10-16", name="SE-NL-X14")
	mr("X15", 8, "2026-10-16")                                   # "Không còn" → sản xuất thật
	frappe.cache().store.clear()


def run(check, label, expect_tet, expect_trad, vouchers=3):
	from bc.api import sx, live
	items = {r["item_code"]: r for r in sx.get_items(TODAY, TODAY, refresh=1)["rows"]}
	check(f"{label}: get_items TET1 = {expect_tet} hộp", items.get("TET1", {}).get("produced") == expect_tet,
		items.get("TET1", {}).get("produced"))
	check(f"{label}: get_items TRAD1 = {expect_trad} hộp", items.get("TRAD1", {}).get("produced") == expect_trad,
		items.get("TRAD1", {}).get("produced"))
	check(f"{label}: thùng TET1 = {expect_tet / 12}", items.get("TET1", {}).get("produced_cartons") == round(expect_tet / 12, 2))
	day = sx.get_daily_summary(2026, 10, refresh=1)["rows"]
	d = next((r for r in day if r["date"] == TODAY), {})
	check(f"{label}: daily_summary hộp = {expect_tet + expect_trad}", d.get("boxes") == expect_tet + expect_trad, d)
	det = sx.get_daily_detail(TODAY, refresh=1)["rows"]
	check(f"{label}: daily_detail tổng hộp", sum(r["boxes"] for r in det) == expect_tet + expect_trad, det)
	snap = live.get_snapshot(refresh=1)
	p = snap["production"]
	check(f"{label}: live hộp hôm nay = {expect_tet + expect_trad}", p["boxes"] == expect_tet + expect_trad, p)
	check(f"{label}: live số phiếu = {vouchers}", p["vouchers"] == vouchers, p["vouchers"])
	feed = [e for e in snap["feed"] if e["kind"] == "production"]
	check(f"{label}: live feed {vouchers} phiếu sản xuất", len(feed) == vouchers, [e["sub"] for e in feed])
	check(f"{label}: giờ 8h có SX (Manufacture 08:15)", snap["hourly"]["production"][8] == 10.0, snap["hourly"]["production"][8])
	return items


if __name__ == "__main__":
	c = Check()
	print("A. Site có app sx (cột custom_kiem_ke)")
	reset(); seed(has_kk=True)
	run(c, "có sx", expect_tet=120.0, expect_trad=60.0)
	from bc.api import sx
	diag = sx._diagnose(datetime.date(2026, 10, 27), datetime.date(2026, 10, 27), True)
	c("diag: entry_types gồm Manufacture + Material Receipt", diag["entry_types"] == ["Manufacture", "Material Receipt"], diag)
	c("diag: phiếu SX gần nhất = hôm nay", diag["last_manufacture"] == TODAY, diag["last_manufacture"])

	print("\nB. Site KHÔNG có app sx (không có cột custom_kiem_ke) — truy vấn không được nổ")
	reset(); drop_column("Stock Entry", "custom_kiem_ke"); seed(has_kk=False)
	frappe.cache().store.clear()
	# Không có cột kiểm kê → phiếu kiểm kê (30) không nhận diện được, chỉ còn loại theo remarks.
	run(c, "không sx", expect_tet=150.0, expect_trad=60.0, vouchers=4)

	print("\nD. Phiếu chuyển Xưởng → Kho TP (trước D191 thành phẩm vào kho bằng phiếu này)")
	reset(); seed()
	insert("Warehouse", name="Cửa hàng - HGC", warehouse_name="Cửa hàng", lft=40, rgt=41, is_group=0)
	se("Material Transfer", [{"item_code": "TRAD1", "s_warehouse": XUONG, "t_warehouse": TP, "transfer_qty": 15, "qty": 15}],
		time="11:00:00")
	se("Material Transfer", [{"item_code": "TRAD1", "s_warehouse": "Cửa hàng - HGC", "t_warehouse": TP, "transfer_qty": 4, "qty": 4}])
	se("Material Transfer", [{"item_code": "TET1", "s_warehouse": XUONG, "t_warehouse": TP, "transfer_qty": 6, "qty": 6}],
		kiem_ke="KK-0002")
	frappe.cache().store.clear()
	run(c, "chưa đặt kho_xuong", expect_tet=120.0, expect_trad=60.0)
	frappe.db.set_single_value("SX Settings", "kho_xuong", XUONG)
	run(c, "kho_xuong = Xưởng", expect_tet=120.0, expect_trad=75.0, vouchers=4)
	from bc.api import sx as SXA
	c("diag: entry_types thêm Material Transfer khi có kho_xuong", "Material Transfer" in SXA.production_purposes())

	print("\nE. Kiểm kê đưa mã về 0 rồi nhập lại ĐÚNG số đó (10/2026): phiếu nhập lại không phải sản xuất")
	reset(); seed_nhap_lai()
	from bc.api import live
	from bc.api import sx as SXE
	nl = SXE.nhap_lai_sau_kiem_ke()
	got = sorted((x["item_code"], x["kiem_ke"], x["so"], x["phieu"], x["ngay_nhap"], len(x["dong"])) for x in nl)
	want = sorted([("DTL", "KK-T1", 100.0, "SE-NL-DTL-2", "2026-10-20", 1), ("X10", "KK-T1", 30.0, "SE-NL-X10", "2026-12-11", 1),
		("X8", "KK-T1", 40.0, "SE-NL-X8", "2026-10-15", 2), ("X9", "KK-T3", 15.0, "SE-NL-X9", TODAY, 1),
		("X11", "KK-T1", 12.0, "SE-NL-X11", "2026-10-12", 1), ("X12", "KK-T1", 46.0, "PNTP-X12", "2026-10-15", 2),
		("X13", "KK-T1", 20.0, "SE-NL-X13", "2026-10-16", 1), ("X14", "KK-T1", 10.0, "SE-NL-X14", "2026-10-16", 1),
		("X16", "KK-T3", 25.0, "SE-NL-X16", "2026-10-22", 1)])
	c("nhận diện đúng 9 phiếu nhập lại (DTL phiếu 100 TẠO ĐẦU TIÊN sau chốt; X8 hai dòng lô 25 + 15; X10 ngày thứ 60; X9 hôm nay; "
		"X11 ghi sổ trước giờ chốt nhưng tạo sau; X12 một phiếu Nhập TP hai phiếu kho; X13 bỏ phiếu bù D216 khi đối chiếu; "
		"X14 bỏ lô đang thu hồi; X16 phiếu đúng số tạo giữa hai lần kiểm kê là sản xuất thật)", got == want, got)
	items = {r["item_code"]: r for r in SXE.get_items("2026-10-01", "2027-01-31", refresh=1)["rows"]}
	# Hộp sản xuất kỳ vọng (tính tay, xem seed_nhap_lai): DTL 100 chuyển Xưởng + 60 (khác số) + 100 (phiếu đúng số THỨ HAI —
	# sản xuất thật) = 260 (bỏ 100 ngày 20/10); X2 50 (phiếu gốc đúng số nhưng TRƯỚC kiểm kê); X3 30 + 30 (ngày 61) = 60;
	# X10 30 (bỏ 30 ngày 60); X4 40 + 30 (kiểm kê còn 10 — không về 0) = 70; X5 20 + 20 (kiểm kê đã huỷ) = 40;
	# X6 25 + 25 (kiểm kê ở kho khác) = 50; X7 70 + 70 (biên bản 70 mà sổ chỉ xuất 60) = 140; X8 40 (bỏ 25 + 15);
	# X9 15 (bỏ 15 hôm nay).
	# X11 12 (bỏ 12); X12 46 chuyển Xưởng (bỏ 30 + 16); X13 20 (bỏ 20); X14 15 (bỏ 10); X15 8 + 8 = 16 ("Không còn" — hàng
	# hết thật, phiếu 8 sau đó là sản xuất); X16 25 (14/10, sản xuất thật) + 25 (22/10, nhập lại sau KK-T3 — bỏ) = 25.
	exp = {"DTL": (260.0, 100.0), "X2": (50.0, 0), "X3": (60.0, 0), "X10": (30.0, 30.0), "X4": (70.0, 0), "X5": (40.0, 0),
		"X6": (50.0, 0), "X7": (140.0, 0), "X8": (40.0, 40.0), "X9": (15.0, 15.0), "X11": (12.0, 12.0), "X12": (46.0, 46.0),
		"X13": (20.0, 20.0), "X14": (15.0, 10.0), "X15": (16.0, 0), "X16": (25.0, 25.0)}
	bad = {k: (items.get(k, {}).get("produced"), items.get(k, {}).get("nhap_lai")) for k in exp
		if (items.get(k, {}).get("produced"), items.get(k, {}).get("nhap_lai")) != exp[k]}
	c("get_items: sản xuất bỏ đúng phần nhập lại, giữ mọi phiếu khác (16 mã)", not bad, bad)
	c("get_items: DTL thùng = 260 / 20 = 13", items["DTL"]["produced_cartons"] == 13.0, items["DTL"]["produced_cartons"])
	ds = items["DTL"]["nhap_lai_ds"]
	c("get_items: DTL ghi rõ phiếu nhập lại ↔ lần kiểm kê", ds == [{"kiem_ke": "KK-T1", "ngay_kiem": "2026-10-12", "so": 100.0,
		"phieu": "SE-NL-DTL-2", "ngay_nhap": "2026-10-20"}], ds)
	n10 = {r["item_code"]: r for r in SXE.get_items("2026-10-01", "2026-10-31", refresh=1)["rows"]}
	c("get_items tháng 10: X10 nhập lại ngày 11/12 ngoài kỳ → không ghi bỏ trong kỳ, sản xuất 30",
		n10["X10"]["produced"] == 30.0 and n10["X10"]["nhap_lai"] == 0, (n10["X10"]["produced"], n10["X10"]["nhap_lai"]))
	day = {r["date"]: r for r in SXE.get_daily_summary(2026, 10, refresh=1)["rows"]}
	c("daily_summary 27/10: 180 hộp (bỏ 15 hộp X9 nhập lại hôm nay)", day[TODAY]["boxes"] == 180.0, day.get(TODAY))
	c("daily_summary 20/10: 100 hộp DTL nhập lại không thành ngày sản xuất", "2026-10-20" not in day, day.get("2026-10-20"))
	det = SXE.get_daily_detail(TODAY, refresh=1)["rows"]
	c("daily_detail hôm nay: không có phiếu SE-NL-X9", all(r["voucher"] != "SE-NL-X9" for r in det), [r["voucher"] for r in det])
	snap = live.get_snapshot(refresh=1)
	c("Thời gian thực: sản xuất hôm nay 180 hộp, 3 phiếu (bỏ phiếu nhập lại X9)",
		snap["production"]["boxes"] == 180.0 and snap["production"]["vouchers"] == 3, (snap["production"]["boxes"], snap["production"]["vouchers"]))
	c("Thời gian thực: dòng sự kiện không có phiếu nhập lại", all(e.get("doc") != "SE-NL-X9" for e in snap["feed"]))
	raw = frappe.db.sql(f"""SELECT SUM(sed.transfer_qty) FROM `tabStock Entry Detail` sed JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE {SXE.production_filter()} AND sed.item_code = 'DTL'""", {"sx_wh": "Thành phẩm - HGC"})[0][0]
	c("production_filter() mặc định (đối chiếu sổ ↔ phiếu ở Kho › Nhập TP) vẫn theo sổ: DTL 360", float(raw) == 360.0, raw)

	print("\nF. Site chưa có bảng biên bản kiểm kê (SX Kiem Ke Lo): không bỏ gì, không lỗi")
	reset(); seed_nhap_lai(); drop_doctype("SX Kiem Ke Lo")
	from bc.api import sx as SXF
	c("không bảng biên bản → không nhận diện", SXF.nhap_lai_sau_kiem_ke() == [])
	itf = {r["item_code"]: r for r in SXF.get_items("2026-10-01", "2027-01-31", refresh=1)["rows"]}
	c("không bảng biên bản → DTL sản xuất theo sổ 360", itf["DTL"]["produced"] == 360.0 and itf["DTL"]["nhap_lai"] == 0,
		itf["DTL"]["produced"])

	print("\nC. Kho thành phẩm lấy từ SX Settings khi BC Settings để trống")
	reset(); seed(); frappe.db.sql("DELETE FROM tabSingles WHERE doctype='BC Settings' AND field='sx_warehouse'")
	frappe.db.set_single_value("SX Settings", "kho_tp", "Kho Xưởng - HGC")
	from bc.api.sx import _wh
	c("_wh() = SX Settings.kho_tp", _wh() == "Kho Xưởng - HGC", _wh())
	frappe.db.sql("DELETE FROM tabSingles WHERE doctype='SX Settings'")
	c("_wh() mặc định khi cả hai trống", _wh() == "Thành phẩm - HGC", _wh())
	c.done()
