"""Số sản xuất của bc: Manufacture (dòng thành phẩm) + Material Receipt trừ phiếu điều chỉnh của sx.

Chạy: python3 test_sx.py   (cần MariaDB + schema.py). Thử phá: BC_APP_ROOT trỏ bản cũ → phải đỏ.
"""
import datetime

from seed import Check, bc_settings, drop_column, insert, reset

import frappe

TODAY = "2026-10-27"
TP, XUONG, BTP = "Thành phẩm - HGC", "Kho Xưởng - HGC", "Bán thành phẩm - HGC"


def se(purpose, rows, docstatus=1, remarks=None, kiem_ke=None, date=TODAY, time="09:00:00", has_kk=True):
	extra = {"custom_kiem_ke": kiem_ke} if has_kk else {}
	name = insert("Stock Entry", docstatus=docstatus, purpose=purpose, stock_entry_type=purpose, posting_date=date,
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

	print("\nC. Kho thành phẩm lấy từ SX Settings khi BC Settings để trống")
	reset(); seed(); frappe.db.sql("DELETE FROM tabSingles WHERE doctype='BC Settings' AND field='sx_warehouse'")
	frappe.db.set_single_value("SX Settings", "kho_tp", "Kho Xưởng - HGC")
	from bc.api.sx import _wh
	c("_wh() = SX Settings.kho_tp", _wh() == "Kho Xưởng - HGC", _wh())
	frappe.db.sql("DELETE FROM tabSingles WHERE doctype='SX Settings'")
	c("_wh() mặc định khi cả hai trống", _wh() == "Thành phẩm - HGC", _wh())
	c.done()
