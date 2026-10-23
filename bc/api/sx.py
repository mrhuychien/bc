# -*- coding: utf-8 -*-
"""bc.api.sx — Sản xuất Hàng Tết (port "Quản lý sản xuất Hàng Tết" + "Sản lượng sản
xuất theo ngày").

Nguồn: Stock Entry mục đích Manufacture (docstatus=1), dòng thành phẩm
(is_finished_item=1); số lượng theo đơn vị kho (transfer_qty = hộp), thùng = hộp /
hệ số UOM "Thùng" của Item. Xuất bán = Sales Invoice (stock_qty, không tính trả).
Tồn kho = Bin.actual_qty hiện tại (mọi kho). Ảnh + nhóm hàng join Item ngay trong
SQL (bỏ frappe.client.get_list phía client).
[VERIFY port] đối chiếu với SQL gốc (docs/report-sql/) — đặc biệt kho/nhóm được lọc.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, cint, flt, get_last_day, getdate

from bc.api._common import (
	OPENING_FILTER,
	_guard,
	carton_factors,
	iso,
	pct,
	plan_column,
	plans_of,
	run_cached,
	sx_default_range,
	tet_group,
	to_cartons,
	traditional_group,
)

FINISHED_FILTER = """se.docstatus = 1 AND se.purpose = 'Manufacture' AND sed.is_finished_item = 1"""


def _range(from_date, to_date) -> tuple:
	"""Khoảng lọc: tham số client, thiếu thì mặc định BC Settings / mùa sản xuất (sx_season)."""
	if from_date and to_date:
		f, t = getdate(from_date), getdate(to_date)
	else:
		df, dt = sx_default_range()
		f, t = getdate(from_date or df), getdate(to_date or dt)
	if f > t:
		frappe.throw("'Từ ngày' phải trước 'Đến ngày'")
	if (t - f).days > 731:
		frappe.throw("Khoảng thời gian tối đa 2 năm")
	return f, t


def _group_key(item_group: str | None) -> str:
	if item_group == tet_group():
		return "tet"
	if item_group == traditional_group():
		return "traditional"
	return "other"


@frappe.whitelist()
def get_items(from_date=None, to_date=None, refresh=0):
	"""Kế hoạch / tồn / đã sản xuất / đã xuất bán theo mã trong khoảng ngày.

	rows: [{item_code, item_name, item_group, group_key (tet|traditional|other), image,
	        plan, stock, produced, outgoing, produced_pct, outgoing_pct}]
	"""
	_guard()
	f, t = _range(from_date, to_date)

	def build():
		p = {"f": f, "t": t}
		produced = {r.item_code: flt(r.qty) for r in frappe.db.sql(
			# SQL thay ORM: join Stock Entry ↔ Detail + lọc dòng thành phẩm.
			f"""
			SELECT sed.item_code, SUM(sed.transfer_qty) AS qty
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {FINISHED_FILTER} AND se.posting_date BETWEEN %(f)s AND %(t)s
			GROUP BY sed.item_code
			""", p, as_dict=True)}
		outgoing = {r.item_code: flt(r.qty) for r in frappe.db.sql(
			f"""
			SELECT sii.item_code, SUM(sii.stock_qty) AS qty
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
			  AND si.posting_date BETWEEN %(f)s AND %(t)s
			GROUP BY sii.item_code
			""", p, as_dict=True)}
		# Luôn hiện mọi mã đang dùng của 2 nhóm chính (kể cả chưa sản xuất trong khoảng)
		# để vẫn thấy tồn kho / kế hoạch trước khi mùa bắt đầu; nhóm khác chỉ hiện khi có SX.
		col = plan_column()
		group_codes = frappe.db.sql_list(
			"""SELECT name FROM `tabItem` WHERE disabled = 0 AND has_variants = 0 AND item_group IN %(g)s""",
			{"g": (tet_group(), traditional_group())})
		codes = set(produced) | set(group_codes)
		diag = _diagnose(f, t, bool(produced))
		if not codes:
			return {"rows": [], "meta": _meta(f, t, plan_column=col, diag=diag)}
		items = frappe.db.sql(
			"""
			SELECT i.name AS item_code, i.item_name, i.item_group, i.image,
				(SELECT COALESCE(SUM(b.actual_qty), 0) FROM `tabBin` b WHERE b.item_code = i.name) AS stock
			FROM `tabItem` i WHERE i.name IN %(codes)s
			""",
			{"codes": tuple(codes)},
			as_dict=True,
		)
		plans = plans_of(codes)
		rows = []
		for it in items:
			plan = plans.get(it.item_code, 0.0)
			prod = produced.get(it.item_code, 0.0)
			out = outgoing.get(it.item_code, 0.0)
			rows.append({
				"item_code": it.item_code,
				"item_name": it.item_name,
				"item_group": it.item_group,
				"group_key": _group_key(it.item_group),
				"image": it.image or None,
				"plan": plan,
				"stock": flt(it.stock),
				"produced": prod,
				"outgoing": out,
				"produced_pct": pct(prod, plan),
				"outgoing_pct": pct(out, plan if plan else prod),
			})
		rows.sort(key=lambda r: (r["plan"], r["produced"]), reverse=True)
		return {"rows": rows, "meta": _meta(f, t, plan_column=col, diag=diag)}

	return run_cached("sx.get_items", {"f": iso(f), "t": iso(t)}, build, refresh)


def _diagnose(f, t, has_production: bool) -> dict:
	"""Giải thích khi khoảng lọc không có số SX: phiếu theo loại trong khoảng, phiếu SX gần nhất,
	và khoảng mùa trước để UI gợi ý xem lại."""
	by_purpose = {r.purpose: cint(r.n) for r in frappe.db.sql(
		"""SELECT purpose, COUNT(*) AS n FROM `tabStock Entry`
		   WHERE docstatus = 1 AND posting_date BETWEEN %(f)s AND %(t)s GROUP BY purpose""",
		{"f": f, "t": t}, as_dict=True)}
	last = frappe.db.sql(
		f"""SELECT MAX(se.posting_date) FROM `tabStock Entry Detail` sed
		    JOIN `tabStock Entry` se ON se.name = sed.parent WHERE {FINISHED_FILTER}""")[0][0]
	return {
		"has_production": has_production,
		"entries_by_purpose": by_purpose,
		"last_manufacture": iso(last),
		"prev_from": iso(add_months(f, -12)),
		"prev_to": iso(get_last_day(add_months(t, -12))),
	}


def _meta(f, t, **extra) -> dict:
	return {"from_date": iso(f), "to_date": iso(t), "groups": {"tet": tet_group(), "traditional": traditional_group()},
		**extra}


def _month_range(year, month) -> tuple:
	today = getdate()
	year, month = cint(year) or today.year, cint(month) or today.month
	if not (1 <= month <= 12 and 2000 <= year <= 2100):
		frappe.throw("Tháng/năm không hợp lệ")
	start = getdate(f"{year:04d}-{month:02d}-01")
	return year, month, start, getdate(get_last_day(start))


@frappe.whitelist()
def get_daily_summary(year=None, month=None, refresh=0):
	"""Sản lượng thành phẩm theo ngày của 1 tháng.

	rows: [{date, cartons, boxes, amount}] — amount = giá trị nhập kho (Stock Entry amount).
	"""
	_guard()
	year, month, start, end = _month_range(year, month)

	def build():
		raw = frappe.db.sql(
			f"""
			SELECT se.posting_date AS date, sed.item_code, SUM(sed.transfer_qty) AS boxes, SUM(sed.amount) AS amount
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {FINISHED_FILTER} AND se.posting_date BETWEEN %(s)s AND %(e)s
			GROUP BY se.posting_date, sed.item_code
			""",
			{"s": start, "e": end},
			as_dict=True,
		)
		factors = carton_factors(r.item_code for r in raw)
		days: dict = {}
		for r in raw:
			d = days.setdefault(iso(r.date), {"date": iso(r.date), "cartons": 0.0, "boxes": 0.0, "amount": 0.0})
			d["boxes"] += flt(r.boxes)
			d["cartons"] += to_cartons(r.boxes, factors.get(r.item_code))
			d["amount"] += flt(r.amount)
		rows = sorted(days.values(), key=lambda x: x["date"])
		for r in rows:
			r["cartons"] = round(r["cartons"], 2)
		return {"rows": rows, "meta": {"year": year, "month": month, "start": iso(start), "end": iso(end)}}

	return run_cached("sx.get_daily_summary", {"y": year, "m": month}, build, refresh)


@frappe.whitelist()
def get_daily_detail(date=None, refresh=0):
	"""Chi tiết thành phẩm nhập kho trong 1 ngày, theo phiếu.

	rows: [{item_code, item_name, boxes, cartons, amount, voucher}] — voucher mở
	/app/stock-entry/{voucher}.
	"""
	_guard()
	d = getdate(date or getdate())

	def build():
		raw = frappe.db.sql(
			f"""
			SELECT se.name AS voucher, sed.item_code, MAX(sed.item_name) AS item_name,
				SUM(sed.transfer_qty) AS boxes, SUM(sed.amount) AS amount
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {FINISHED_FILTER} AND se.posting_date = %(d)s
			GROUP BY se.name, sed.item_code
			ORDER BY se.name, sed.item_code
			""",
			{"d": d},
			as_dict=True,
		)
		factors = carton_factors(r.item_code for r in raw)
		rows = [{"item_code": r.item_code, "item_name": r.item_name, "boxes": flt(r.boxes),
			"cartons": to_cartons(r.boxes, factors.get(r.item_code)), "amount": flt(r.amount),
			"voucher": r.voucher} for r in raw]
		return {"rows": rows, "meta": {"date": iso(d)}}

	return run_cached("sx.get_daily_detail", {"d": iso(d)}, build, refresh)
