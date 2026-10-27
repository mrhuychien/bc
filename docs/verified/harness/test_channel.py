"""Kênh Showroom: bc đọc kenh_showroom của PKD Settings như pkd; site pkd chưa có field vẫn giữ 3 kênh."""
from seed import Check, bc_settings, insert, reset, single

import frappe
import schema

GROUPS = [  # name, parent, lft, rgt
	("All Customer Groups", None, 1, 20), ("Nhà phân phối", "All Customer Groups", 2, 5), ("NPP", "Nhà phân phối", 3, 4),
	("Siêu thị", "All Customer Groups", 6, 9), ("Co.op", "Siêu thị", 7, 8), ("Du lịch", "All Customer Groups", 10, 11),
	("Showroom", "All Customer Groups", 12, 15), ("Showroom HN", "Showroom", 13, 14), ("Khách lẻ", "All Customer Groups", 16, 17)]


def seed():
	bc_settings()
	for n, p, l, r in GROUPS:
		insert("Customer Group", name=n, customer_group_name=n, parent_customer_group=p, lft=l, rgt=r, is_group=int(r - l > 1))
	for i, (g, amt, ret) in enumerate([("NPP", 1000, 0), ("Co.op", 500, 0), ("Du lịch", 200, 0), ("Showroom HN", 80, 1), ("Khách lẻ", 30, 0)]):
		insert("Sales Invoice", docstatus=1, posting_date="2026-10-20", customer=f"C{i}", customer_name=f"C{i}", customer_group=g,
			net_total=-amt if ret else amt, is_return=ret, is_opening="No", company="HGC")


if __name__ == "__main__":
	c = Check()
	from bc.api import _common, kd
	print("A. PKD Settings đủ 4 root")
	reset(); seed()
	single("PKD Settings", kenh_npp="Nhà phân phối", kenh_mt="Siêu thị", kenh_dulich="Du lịch", kenh_showroom="Showroom")
	m = _common.channel_map()
	c("NPP con → npp", m["NPP"] == "npp", m)
	c("Showroom HN → showroom", m["Showroom HN"] == "showroom", m)
	c("Khách lẻ → khac", m["Khách lẻ"] == "khac", m)
	rows = kd.get_channels(refresh=1)["rows"]
	keys = [r["channel_key"] for r in rows if r["period"] == "current"]
	c("get_channels có đủ 5 kênh theo thứ tự", keys == ["npp", "mt", "dulich", "showroom", "khac"], keys)
	cur = {r["channel_key"]: r for r in rows if r["period"] == "current"}
	c("Showroom: trả 80 tách khỏi Khác", cur["showroom"]["returns"] == 80 and cur["khac"]["sales"] == 30, (cur["showroom"], cur["khac"]))

	print("\nB. pkd chưa migrate (không có field kenh_showroom trong meta) → vẫn đọc 3 root, Showroom về Khác")
	reset(); bc_settings()
	# Tên trung tính: từ khoá dự phòng KHÔNG khớp → chỉ đường đọc root PKD mới cho ra npp/mt.
	for n, p, l, r in [("All Customer Groups", None, 1, 12), ("Kênh A", "All Customer Groups", 2, 5), ("Đối tác Bắc", "Kênh A", 3, 4),
			("Kênh B", "All Customer Groups", 6, 9), ("Co.op", "Kênh B", 7, 8), ("Showroom HN", "All Customer Groups", 10, 11)]:
		insert("Customer Group", name=n, customer_group_name=n, parent_customer_group=p, lft=l, rgt=r)
	single("PKD Settings", kenh_npp="Kênh A", kenh_mt="Kênh B")
	f, meta = schema.doctype_files()["PKD Settings"]
	orig = meta["fields"]
	meta["fields"] = [x for x in orig if x.get("fieldname") != "kenh_showroom"]
	try:
		frappe.cache().store.clear()
		m = _common.channel_map()
		c("Nhóm con theo root PKD (không rơi về dò từ khoá)", m["Đối tác Bắc"] == "npp" and m["Co.op"] == "mt", m)
		c("Showroom HN → khac khi chưa có root", m["Showroom HN"] == "khac", m["Showroom HN"])
	finally:
		meta["fields"] = orig

	print("\nC. Không có PKD Settings → dò từ khoá, có từ khoá showroom")
	reset(); seed(); frappe.db.sql("DELETE FROM tabDocType WHERE name='PKD Settings'")
	m = _common.channel_map()
	c("Showroom HN → showroom (từ khoá nhóm cha)", m["Showroom HN"] == "showroom", m)
	c("NPP → npp (từ khoá)", m["NPP"] == "npp", m)
	c.done()
