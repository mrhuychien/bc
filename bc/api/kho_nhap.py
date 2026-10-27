# -*- coding: utf-8 -*-
"""bc.api.kho_nhap — Nhập kho thành phẩm và giá vốn chưa thật (K11–K12). ĐANG XÂY."""

from __future__ import annotations

import frappe

from bc.api._common import _guard


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	_guard("nhap-tp")
	return {"available": False, "meta": {}}
