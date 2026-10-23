# -*- coding: utf-8 -*-
"""after_install — seed BC Settings mặc định (idempotent, lỗi không làm chết install).

after_install có thể chạy TRƯỚC sync_fixtures → tự tạo Role BC Viewer nếu chưa có.
"""

from __future__ import annotations

import frappe

# Mùng 1 Tết (dương lịch) — chỉ là giá trị khởi tạo; về sau quản trị sửa trong
# BC Settings, code KHÔNG đọc bảng này (mọi nơi đọc từ BC Settings.tet_dates).
SEED_TET_DATES = {
	2023: "2023-01-22", 2024: "2024-02-10", 2025: "2025-01-29", 2026: "2026-02-17",
	2027: "2027-02-06", 2028: "2028-01-26", 2029: "2029-02-13", 2030: "2030-02-03",
}


def after_install():
	try:
		if not frappe.db.exists("Role", "BC Viewer"):
			frappe.get_doc({"doctype": "Role", "role_name": "BC Viewer", "desk_access": 0,
				"home_page": "/bc"}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc after_install: tạo Role BC Viewer")

	try:
		seed_settings()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc after_install: seed BC Settings")


def seed_settings():
	"""Điền giá trị mặc định cho các ô còn trống — không ghi đè cấu hình đã có."""
	s = frappe.get_single("BC Settings")
	if not s.fy_start_month:
		s.fy_start_month = 4
	if not s.tet_season_start_month:
		s.tet_season_start_month = 11
	if not s.cache_ttl:
		s.cache_ttl = 300
	if not s.tet_target_pct:
		s.tet_target_pct = 20
	if not s.tet_compare_mode:
		s.tet_compare_mode = "calendar"
	for field, group in (("tet_item_group", "Hàng Tết"), ("traditional_item_group", "Hàng truyền thống")):
		if not s.get(field) and frappe.db.exists("Item Group", group):
			s.set(field, group)
	have = {int(r.year) for r in s.tet_dates}
	for year, d in SEED_TET_DATES.items():
		if year not in have:
			s.append("tet_dates", {"year": year, "tet_date": d})
	s.flags.ignore_permissions = True
	s.flags.ignore_mandatory = True
	s.save()
