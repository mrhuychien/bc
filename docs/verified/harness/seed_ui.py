"""Seed dữ liệu đủ cho các màn bc (Kinh doanh + SX + Thời gian thực) — chạy trước server.py."""
import datetime

from seed import bc_settings, insert, reset, single

import test_channel
import test_sx


def sales():
	# Hoá đơn bán theo kênh: năm TC nay (từ 01/05/2026) + cùng kỳ năm trước
	cust = {"NPP": "NPP Hà Nội", "Co.op": "Co.op Mart", "Du lịch": "Lữ hành Sao", "Showroom HN": "Showroom Hà Nội",
		"Khách lẻ": "Khách lẻ"}
	n = 0
	for grp, base in (("NPP", 90e6), ("Co.op", 45e6), ("Du lịch", 12e6), ("Showroom HN", 6e6), ("Khách lẻ", 2e6)):
		for d in ("2026-05-12", "2026-07-03", "2026-09-15", "2026-10-26", "2026-10-27", "2025-06-10", "2025-10-20"):
			n += 1
			si = insert("Sales Invoice", docstatus=1, posting_date=d, posting_time="09:30:00", customer=cust[grp],
				customer_name=cust[grp], customer_group=grp, net_total=base, grand_total=base * 1.08, is_return=0,
				is_opening="No", company="HGC", territory="Hà Nội")
			insert("Sales Invoice Item", parent=si, parenttype="Sales Invoice", parentfield="items", idx=1,
				item_code="TET1" if n % 2 else "TRAD1", item_name="Bánh", item_group="Hàng Tết" if n % 2 else "Hàng truyền thống",
				qty=10, stock_qty=10, net_amount=base, amount=base, uom="Hộp", docstatus=1)


if __name__ == "__main__":
	reset()
	test_sx.seed()
	from frappe import db
	for n, p, l, r in test_channel.GROUPS:
		insert("Customer Group", name=n, customer_group_name=n, parent_customer_group=p, lft=l + 100, rgt=r + 100)
	single("PKD Settings", kenh_npp="Nhà phân phối", kenh_mt="Siêu thị", kenh_dulich="Du lịch", kenh_showroom="Showroom")
	sales()
	print("seeded")
