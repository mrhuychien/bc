# -*- coding: utf-8 -*-
"""Năm tài chính RVHG = 01/05 → 30/04 năm sau. Site đã cài bản đầu được seed 4 (01/04)
→ đổi sang 5. Chỉ đổi khi đang là giá trị seed cũ (4) hoặc trống — không đè cấu hình
quản trị đã tự chọn khác."""

import frappe


def execute():
	current = frappe.db.get_single_value("BC Settings", "fy_start_month")
	if current in (None, 0, 4):
		frappe.db.set_single_value("BC Settings", "fy_start_month", 5)
		frappe.clear_document_cache("BC Settings", "BC Settings")
		frappe.cache().delete_keys("bc:")
