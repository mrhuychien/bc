# -*- coding: utf-8 -*-
"""bc.api.tet — Phân tích Hàng Tết (port 4 Query Report "Tet *", SPEC 3 + 3b).

KHÔNG có CURDATE()/NOW()/ngày Tết literal trong SQL: mọi mốc lấy từ tet_season()
(xem docs/tet-curdate-audit.md). Lọc theo item_group = BC Settings.tet_item_group
(đúng tên, không còn quy tắc "Tết = không phải truyền thống"). Kênh theo Customer
Group snapshot trên hoá đơn (NPP / MT).

Định nghĩa cột (giá trị tiền = SII_AMOUNT; dòng trả hàng ERPNext mang số âm):
  this_year       thực bán mùa này: season_start → asof (bán − trả)
  total_in        tổng nhập (bán ra, không tính trả) mùa này
  total_return    tổng về (trả lại) mùa này, số dương
  last_year       thực bán CẢ mùa trước: ly_season_start → ly_season_end
  last_year_out   thực bán mùa trước tính đến cùng kỳ (ly_asof theo tet_compare_mode)
  last_year_target last_year × (1 + tet_target_pct)
  return_pct      total_return / total_in × 100
  growth_pct      (this_year / last_year_out − 1) × 100
[VERIFY port] đối chiếu từng cột với SQL gốc bằng bc.scripts.compare_tet_reports.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

from bc.api._common import (
	OPENING_FILTER,
	SII_AMOUNT,
	_guard,
	carton_factors,
	drop_hidden,
	channel_of,
	compare_mode_label,
	growth,
	iso_dict,
	pct,
	plan_column,
	plans_of,
	run_cached,
	short_name,
	target_pct,
	tet_group,
	tet_season,
	to_cartons,
	groups_of,
)


def _params() -> tuple[dict, dict]:
	s = tet_season()
	p = {k: s[k] for k in ("tet_year", "season_start", "season_end", "asof", "ly_season_start",
		"ly_season_end", "ly_asof")}
	p["tet_group"] = tet_group()
	return s, p


def _meta(s: dict, **extra) -> dict:
	m = iso_dict(s)
	m["compare_label"] = compare_mode_label(s["compare_mode"])
	m["target_pct"] = target_pct()
	m["tet_group"] = tet_group()
	m.update(extra)
	return m


def _customer_rows(channel: str, p: dict) -> list:
	"""Số liệu theo khách của 1 kênh — 1 lượt quét 2 mùa (tổng có điều kiện)."""
	q = dict(p, g=groups_of(channel))
	return frappe.db.sql(
		# SQL thay ORM: tổng có điều kiện 2 mùa × bán/trả theo khách trong 1 truy vấn.
		f"""
		SELECT si.customer, MAX(si.customer_name) AS customer_name,
			SUM(CASE WHEN si.posting_date BETWEEN %(season_start)s AND %(asof)s THEN {SII_AMOUNT} ELSE 0 END) AS this_year,
			SUM(CASE WHEN si.posting_date BETWEEN %(season_start)s AND %(asof)s AND si.is_return = 0 THEN {SII_AMOUNT} ELSE 0 END) AS total_in,
			SUM(CASE WHEN si.posting_date BETWEEN %(season_start)s AND %(asof)s AND si.is_return = 1 THEN -{SII_AMOUNT} ELSE 0 END) AS total_return,
			SUM(CASE WHEN si.posting_date BETWEEN %(ly_season_start)s AND %(ly_season_end)s THEN {SII_AMOUNT} ELSE 0 END) AS last_year,
			SUM(CASE WHEN si.posting_date BETWEEN %(ly_season_start)s AND %(ly_asof)s THEN {SII_AMOUNT} ELSE 0 END) AS last_year_out
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND {OPENING_FILTER}
		  AND sii.item_group = %(tet_group)s
		  AND si.customer_group IN %(g)s
		  AND (si.posting_date BETWEEN %(season_start)s AND %(asof)s
		       OR si.posting_date BETWEEN %(ly_season_start)s AND %(ly_season_end)s)
		GROUP BY si.customer
		""",
		q,
		as_dict=True,
	)


def _detail(channel: str) -> dict:
	s, p = _params()
	tp = target_pct()
	rows = []
	for r in _customer_rows(channel, p):
		ly, ly_out, ty = flt(r.last_year), flt(r.last_year_out), flt(r.this_year)
		tin, tret = flt(r.total_in), flt(r.total_return)
		if not any((ly, ty, tin, tret)):
			continue
		rows.append({
			"customer": r.customer_name or r.customer,
			"customer_id": r.customer,
			"last_year": ly,
			"last_year_target": round(ly * (1 + tp / 100), 0),
			"last_year_out": ly_out,
			"this_year": ty,
			"total_in": tin,
			"total_return": tret,
			"return_pct": pct(tret, tin),
			"growth_pct": growth(ty, ly_out),
		})
	rows.sort(key=lambda x: x["this_year"], reverse=True)
	return {"rows": rows, "meta": _meta(s, channel=channel)}


@frappe.whitelist()
def get_npp_growth(refresh=0):
	"""NPP tăng trưởng Hàng Tết: năm nay (đến asof) vs năm trước cùng kỳ.

	rows: [{customer, customer_id, this_year, last_year, growth_pct}]
	"""
	_guard()

	def build():
		s, p = _params()
		rows = [{"customer": r.customer_name or r.customer, "customer_id": r.customer,
			"this_year": flt(r.this_year), "last_year": flt(r.last_year_out),
			"growth_pct": growth(r.this_year, r.last_year_out)}
			for r in _customer_rows("npp", p) if flt(r.this_year) or flt(r.last_year_out)]
		rows.sort(key=lambda x: x["this_year"], reverse=True)
		return {"rows": rows, "meta": _meta(s, channel="npp")}

	return run_cached("tet.get_npp_growth", {}, build, refresh)


@frappe.whitelist()
def get_npp_detail(refresh=0):
	"""NPP chi tiết Hàng Tết: NT, NT+mục tiêu, NT đi, năm nay, tổng nhập/về, % về, tăng trưởng."""
	_guard()
	return run_cached("tet.get_npp_detail", {}, lambda: _detail("npp"), refresh)


@frappe.whitelist()
def get_mt_detail(refresh=0):
	"""Siêu thị (kênh MT) chi tiết Hàng Tết — cùng cột với get_npp_detail."""
	_guard()
	return run_cached("tet.get_mt_detail", {}, lambda: _detail("mt"), refresh)


@frappe.whitelist()
def get_items(refresh=0):
	"""Mã hàng Tết: giá trị, kế hoạch, hộp/thùng xuất – về, tách MT / GT (= ngoài MT) và NPP.

	rows: [{item_code, item_name, short_name, value, plan, net_boxes, boxes_out, cartons_out,
	        boxes_back, return_pct, mt, gt, mt_out, mt_back, mt_return_pct, npp_out, npp_back,
	        npp_return_pct, plan_pct}]
	"""
	_guard()

	def build():
		s, p = _params()
		raw = frappe.db.sql(
			# stock_qty = số hộp (đơn vị kho); dòng trả mang số âm.
			f"""
			SELECT sii.item_code, MAX(sii.item_name) AS item_name, si.customer_group,
				SUM({SII_AMOUNT}) AS value,
				SUM(CASE WHEN si.is_return = 0 THEN sii.stock_qty ELSE 0 END) AS out_qty,
				SUM(CASE WHEN si.is_return = 1 THEN -sii.stock_qty ELSE 0 END) AS back_qty
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND {OPENING_FILTER}
			  AND sii.item_group = %(tet_group)s
			  AND si.posting_date BETWEEN %(season_start)s AND %(asof)s
			GROUP BY sii.item_code, si.customer_group
			""",
			p,
			as_dict=True,
		)
		items: dict[str, dict] = {}
		for r in raw:
			it = items.setdefault(r.item_code, {"item_code": r.item_code, "item_name": r.item_name, "value": 0.0,
				"boxes_out": 0.0, "boxes_back": 0.0, "mt_out": 0.0, "mt_back": 0.0, "npp_out": 0.0, "npp_back": 0.0})
			ch = channel_of(r.customer_group)
			o, b = flt(r.out_qty), flt(r.back_qty)
			it["value"] += flt(r.value)
			it["boxes_out"] += o
			it["boxes_back"] += b
			if ch == "mt":
				it["mt_out"] += o
				it["mt_back"] += b
			elif ch == "npp":
				it["npp_out"] += o
				it["npp_back"] += b
		factors = carton_factors(items)
		plans = plans_of(items)
		rows = []
		for code, it in items.items():
			net = it["boxes_out"] - it["boxes_back"]
			mt_net = it["mt_out"] - it["mt_back"]
			plan = plans.get(code, 0.0)
			rows.append({
				**it,
				"short_name": short_name(it["item_name"]),
				"plan": plan,
				"net_boxes": net,
				"cartons_out": to_cartons(it["boxes_out"], factors.get(code)),
				"return_pct": pct(it["boxes_back"], it["boxes_out"]),
				"mt": mt_net,
				"gt": net - mt_net,
				"mt_return_pct": pct(it["mt_back"], it["mt_out"]),
				"npp_return_pct": pct(it["npp_back"], it["npp_out"]),
				"plan_pct": pct(net, plan),
			})
		rows = drop_hidden(rows)  # mã admin đã ẩn khỏi báo cáo
		rows.sort(key=lambda x: x["value"], reverse=True)
		return {"rows": rows, "meta": _meta(s, plan_column=plan_column())}

	return run_cached("tet.get_items", {}, build, refresh)
