# -*- coding: utf-8 -*-
"""bc.api.kho_han — Hạn dùng, tồn không bán được, tồn âm (K6–K8). ĐANG XÂY."""

from __future__ import annotations

import frappe

from bc.api._common import _guard


@frappe.whitelist()
def get_overview(refresh=0):
	_guard("han-dung")
	return {"available": False, "meta": {}}
