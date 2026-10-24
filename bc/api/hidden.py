# -*- coding: utf-8 -*-
"""bc.api.hidden — ẩn mã hàng khỏi danh sách sản phẩm của báo cáo (CHỈ System Manager).

Phạm vi ẩn: danh sách / bảng THEO MÃ (thẻ SX Hàng Tết + thống kê nhanh của nó, bảng Mã
hàng Tết, Sản phẩm bán chạy). Tổng doanh số, kênh, tỉnh, lịch ngày, lịch SX và chi tiết
phiếu GIỮ NGUYÊN — ẩn mã không được làm lệch số tổng công ty.
Lưu ở BC Settings.hidden_items (permlevel 1). Đổi danh sách → xoá cache báo cáo.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from bc.api._common import clear_cache, hidden_items

DT = "BC Hidden Item"
PARENT = "BC Settings"


def _admin_guard():
	"""Chỉ System Manager được ẩn / hiện lại sản phẩm. Gọi ở DÒNG ĐẦU mọi method."""
	if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
		frappe.throw(_("Chỉ quản trị (System Manager) được ẩn sản phẩm khỏi báo cáo."), frappe.PermissionError)


@frappe.whitelist()
def list_hidden():
	"""Danh sách mã đang ẩn (kèm nhóm hàng hiện tại)."""
	_admin_guard()
	rows = frappe.db.sql(
		"""SELECT h.name, h.item_code, COALESCE(i.item_name, h.item_name) AS item_name, i.item_group,
			h.note, h.hidden_by, h.hidden_on
		   FROM `tabBC Hidden Item` h LEFT JOIN `tabItem` i ON i.name = h.item_code
		   WHERE h.parent = %s AND h.parenttype = %s ORDER BY h.hidden_on DESC""",
		(PARENT, PARENT), as_dict=True)
	for r in rows:
		r["hidden_on"] = str(r.hidden_on or "")[:16]
	return {"rows": rows}


@frappe.whitelist()
def search_items(q=None):
	"""Tìm mã hàng để ẩn (mã hoặc tên, tối đa 20), đánh dấu mã đã ẩn."""
	_admin_guard()
	q = (q or "").strip()
	if len(q) < 2:
		return {"rows": []}
	like = f"%{q}%"
	rows = frappe.db.sql(
		"""SELECT name AS item_code, item_name, item_group FROM `tabItem`
		   WHERE disabled = 0 AND has_variants = 0 AND (name LIKE %s OR item_name LIKE %s)
		   ORDER BY item_name LIMIT 20""", (like, like), as_dict=True)
	hid = hidden_items()
	for r in rows:
		r["hidden"] = r.item_code in hid
	return {"rows": rows}


@frappe.whitelist()
def hide_item(item_code, note=None):
	"""Ẩn 1 mã khỏi danh sách sản phẩm của báo cáo (idempotent)."""
	_admin_guard()
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Không tìm thấy mã hàng: {0}").format(item_code))
	if item_code in hidden_items():
		return {"ok": True, "item_code": item_code}
	idx = int(frappe.db.sql("SELECT COALESCE(MAX(idx), 0) FROM `tabBC Hidden Item` WHERE parent=%s", PARENT)[0][0]) + 1
	frappe.get_doc({
		"doctype": DT,
		"name": frappe.generate_hash(length=12),
		"parent": PARENT, "parenttype": PARENT, "parentfield": "hidden_items", "idx": idx,
		"item_code": item_code,
		"item_name": frappe.db.get_value("Item", item_code, "item_name"),
		"note": (note or "").strip()[:140] or None,
		"hidden_by": frappe.session.user,
		"hidden_on": now_datetime(),
	}).db_insert()  # ghi thẳng dòng con, không save cả BC Settings
	clear_cache()
	return {"ok": True, "item_code": item_code}


@frappe.whitelist()
def unhide_item(item_code):
	"""Hiện lại 1 mã."""
	_admin_guard()
	frappe.db.delete(DT, {"parent": PARENT, "item_code": item_code})
	clear_cache()
	return {"ok": True, "item_code": item_code}
