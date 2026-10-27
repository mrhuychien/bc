# -*- coding: utf-8 -*-
"""bc.api.kho_kk — Kiểm kê và điều chỉnh kho (K9–K10). ĐANG XÂY."""

from __future__ import annotations

import frappe

from bc.api._common import _guard


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	_guard("kiem-ke")
	return {"available": False, "meta": {}}
