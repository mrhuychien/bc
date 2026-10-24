# -*- coding: utf-8 -*-
"""common.get_context_meta — mốc thời gian + cấu hình công khai cho SPA.

Cùng payload với window.BC_CONTEXT (www/bc.py) để nút "Làm mới" cập nhật mốc
(năm TC, mùa Tết) mà không cần tải lại trang.
"""

from __future__ import annotations

import frappe

from bc.api._common import (
	_guard,
	compare_mode_label,
	fy_label,
	fy_range,
	get_settings,
	iso,
	setting_int,
	target_pct,
	tet_group,
	tet_season,
	traditional_group,
)


def build_context_meta() -> dict:
	"""Payload thuần (không guard) — www page gọi sau khi đã tự kiểm quyền."""
	fy = fy_range()
	tet, tet_error = None, None
	try:
		s = tet_season()
		tet = {
			"year": s["tet_year"],
			"date": iso(s["tet_date"]),
			"seasonStart": iso(s["season_start"]),
			"seasonEnd": iso(s["season_end"]),
			"asof": iso(s["asof"]),
			"lyTetDate": iso(s["ly_tet_date"]),
			"betweenSeasons": s["between_seasons"],
			"nextDate": iso(s["next_tet_date"]),
			"compareMode": s["compare_mode"],
			"compareLabel": compare_mode_label(s["compare_mode"]),
		}
	except frappe.ValidationError as e:
		frappe.clear_last_message()
		tet_error = str(e)
	return {
		"fy": {
			"start": iso(fy["fy_start"]),
			"end": iso(fy["fy_end"]),
			"toDate": iso(fy["to_date"]),
			"spStart": iso(fy["sp_start"]),
			"spEnd": iso(fy["sp_end"]),
			"lyStart": iso(fy["ly_start"]),
			"lyEnd": iso(fy["ly_end"]),
			"label": fy_label(fy),
			"startMonth": setting_int("fy_start_month", 5),
		},
		"tet": tet,
		"tetError": tet_error,
		"groups": {"tet": tet_group(), "traditional": traditional_group()},
		"targetPct": target_pct(),
		"cacheTtl": setting_int("cache_ttl", 300),
		"hasTetDates": bool(get_settings().tet_dates),
	}


@frappe.whitelist()
def get_context_meta(refresh=0):
	"""fy_range + tet_season + settings công khai (không cache — rẻ, cần tươi)."""
	_guard()
	return build_context_meta()
