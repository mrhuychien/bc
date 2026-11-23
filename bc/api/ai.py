# -*- coding: utf-8 -*-
"""bc.api.ai — Trợ lý AI (màn #/tro-ly và #/ai). ĐANG XÂY."""

from __future__ import annotations

import frappe
from frappe import _

from bc.api._common import _guard, is_admin


def _admin_guard():
	"""Chỉ System Manager. Gọi ở DÒNG ĐẦU mọi method quản trị."""
	if not is_admin():
		frappe.throw(_("Chỉ quản trị (System Manager) được cấu hình Trợ lý AI."), frappe.PermissionError)


@frappe.whitelist()
def get_feed(refresh=0, closed=0):
	"""Nhận định cho người gọi (đã lọc theo vai và mảng ẩn)."""
	_guard("tro-ly")
	return {"meta": {}, "brief": None, "counts": {"do": 0, "vang": 0}, "insights": []}


@frappe.whitelist()
def get_badge(refresh=0):
	"""Số nhận định đỏ / vàng sau lọc — chấm đỏ trên menu."""
	_guard("tro-ly")
	return {"do": 0, "vang": 0}


@frappe.whitelist()
def get_admin():
	"""Trạng thái cấu hình, chi phí, quy tắc, lượt chạy (chỉ quản trị)."""
	_admin_guard()
	return {}


@frappe.whitelist(methods=["POST"])
def run_now():
	"""Chạy lượt ngày ngay (chỉ quản trị)."""
	_admin_guard()
	return {"queued": False}


@frappe.whitelist(methods=["POST"])
def set_status(insight, status, mute_days=None, note=None):
	"""Đổi trạng thái một nhận định (chỉ quản trị)."""
	_admin_guard()
	return {}


@frappe.whitelist(methods=["POST"])
def set_rule(rule_key, disabled=None, threshold=None, threshold_red=None):
	"""Tắt / đổi ngưỡng một quy tắc (chỉ quản trị)."""
	_admin_guard()
	return {}


@frappe.whitelist(methods=["POST"])
def test_connection(provider):
	"""Gọi thử một lượt tối thiểu tới nhà cung cấp (chỉ quản trị)."""
	_admin_guard()
	return {"ok": False}
