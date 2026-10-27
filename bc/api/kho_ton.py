# -*- coding: utf-8 -*-
"""bc.api.kho_ton — Tồn kho: giá trị, xu hướng, số ngày tồn, hàng chậm (K1–K5). ĐANG XÂY."""

from __future__ import annotations

import frappe

from bc.api._common import _guard


@frappe.whitelist()
def get_overview(refresh=0):
	_guard("ton-kho")
	return {"available": False, "meta": {}}


@frappe.whitelist()
def get_trend(refresh=0):
	_guard("ton-kho")
	return {"available": False, "meta": {}}
