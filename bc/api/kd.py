# -*- coding: utf-8 -*-
"""bc.api.kd — Báo cáo Kinh doanh tổng quát (port từ các Query Report "Dashboard KD *").

Mọi method: _guard() dòng đầu, tham số `refresh`, trả {rows, meta}. Mốc thời gian
do fy_range() tính ở Python (period-aligned: năm nay đến hôm nay vs cùng kỳ năm
trước cùng số ngày). Doanh số loại opening; trả hàng = hoá đơn is_return=1 (giá trị
âm trên ERPNext → đổi dấu thành số dương ở cột `returns`).

[VERIFY port] SQL dưới đây dựng theo mô tả cột của 15 report (SPEC bảng 3) vì phiên
build không truy cập được site. Trước khi nghiệm thu chạy:
  bench --site <site> execute bc.scripts.dump_report_sql.run      # lưu SQL gốc → docs/report-sql/
rồi so từng điều kiện (kênh, tỉnh, loại trả hàng) và chạy bc.scripts.compare_reports.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt, getdate

from bc.api._common import (
	CHANNEL_LABELS,
	OPENING_FILTER,
	SI_AMOUNT,
	SII_AMOUNT,
	_guard,
	carton_factors,
	channel_of,
	fy_label,
	fy_range,
	growth,
	iso,
	iso_dict,
	pct,
	run_cached,
	short_name,
	tet_group,
	tet_season,
	traditional_group,
)

PERIODS = ("current", "same_period", "last_year")


def _fy_params():
	fy = fy_range()
	return fy, dict(fy)


def _period_sums_by_group() -> tuple[dict, dict]:
	"""{customer_group: {period: {sales, returns}}} cho 3 kỳ trong 1 lượt quét."""
	fy, p = _fy_params()
	rows = frappe.db.sql(
		# SQL thay ORM: tổng có điều kiện 3 kỳ × bán/trả trong 1 lượt quét hoá đơn.
		f"""
		SELECT si.customer_group AS grp,
			SUM(CASE WHEN si.posting_date BETWEEN %(fy_start)s AND %(to_date)s AND si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS cur_s,
			SUM(CASE WHEN si.posting_date BETWEEN %(fy_start)s AND %(to_date)s AND si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS cur_r,
			SUM(CASE WHEN si.posting_date BETWEEN %(sp_start)s AND %(sp_end)s AND si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS sp_s,
			SUM(CASE WHEN si.posting_date BETWEEN %(sp_start)s AND %(sp_end)s AND si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS sp_r,
			SUM(CASE WHEN si.posting_date BETWEEN %(ly_start)s AND %(ly_end)s AND si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS ly_s,
			SUM(CASE WHEN si.posting_date BETWEEN %(ly_start)s AND %(ly_end)s AND si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS ly_r
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND {OPENING_FILTER}
		  AND si.posting_date BETWEEN %(ly_start)s AND %(to_date)s
		GROUP BY si.customer_group
		""",
		p,
		as_dict=True,
	)
	out = {}
	for r in rows:
		out[r.grp or ""] = {
			"current": {"sales": flt(r.cur_s), "returns": flt(r.cur_r)},
			"same_period": {"sales": flt(r.sp_s), "returns": flt(r.sp_r)},
			"last_year": {"sales": flt(r.ly_s), "returns": flt(r.ly_r)},
		}
	return out, fy


def _finish(sales, returns) -> dict:
	sales, returns = flt(sales), flt(returns)
	return {"sales": sales, "returns": returns, "net": sales - returns, "return_rate": pct(returns, sales)}


def _fy_meta(fy) -> dict:
	m = iso_dict(fy)
	m["label"] = fy_label(fy)
	return m


@frappe.whitelist()
def get_summary(refresh=0):
	"""4 thẻ tổng quan: doanh số / trả về / thực bán / tỷ lệ trả × 3 kỳ.

	rows: [{period: current|same_period|last_year, sales, returns, net, return_rate}]
	"""
	_guard()

	def build():
		by_group, fy = _period_sums_by_group()
		rows = []
		for period in PERIODS:
			s = sum(v[period]["sales"] for v in by_group.values())
			r = sum(v[period]["returns"] for v in by_group.values())
			rows.append({"period": period, **_finish(s, r)})
		cur, sp = rows[0], rows[1]
		return {"rows": rows, "meta": {"fy": _fy_meta(fy),
			"growth": {k: growth(cur[k], sp[k]) for k in ("sales", "returns", "net")}}}

	return run_cached("kd.get_summary", {}, build, refresh)


@frappe.whitelist()
def get_channels(refresh=0):
	"""Doanh số theo kênh (NPP/MT/Du lịch/Khác) × 3 kỳ.

	rows: [{period, channel, channel_key, sales, returns, net, return_rate}]
	"""
	_guard()

	def build():
		by_group, fy = _period_sums_by_group()
		agg = {(p, k): [0.0, 0.0] for p in PERIODS for k in CHANNEL_LABELS}
		for grp, periods in by_group.items():
			k = channel_of(grp)
			for p in PERIODS:
				agg[(p, k)][0] += periods[p]["sales"]
				agg[(p, k)][1] += periods[p]["returns"]
		rows = [{"period": p, "channel": CHANNEL_LABELS[k], "channel_key": k, **_finish(*agg[(p, k)])}
			for p in PERIODS for k in CHANNEL_LABELS]
		return {"rows": rows, "meta": {"fy": _fy_meta(fy)}}

	return run_cached("kd.get_channels", {}, build, refresh)


@frappe.whitelist()
def get_daily(year=None, month=None, refresh=0):
	"""Doanh số theo ngày của 1 tháng (mặc định tháng hiện tại) — tải 1 tháng/lần.

	rows: [{date, sales, returns, orders, return_orders}] (chỉ ngày có phát sinh)
	"""
	_guard()
	today = getdate()
	year, month = cint(year) or today.year, cint(month) or today.month
	if not (1 <= month <= 12 and 2000 <= year <= 2100):
		frappe.throw("Tháng/năm không hợp lệ")
	start = getdate(f"{year:04d}-{month:02d}-01")
	end = frappe.utils.get_last_day(start)

	def build():
		rows = frappe.db.sql(
			# SQL thay ORM: GROUP BY ngày + đếm đơn bán/trả trong 1 truy vấn.
			f"""
			SELECT si.posting_date AS date,
				SUM(CASE WHEN si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS sales,
				SUM(CASE WHEN si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS returns,
				SUM(CASE WHEN si.is_return = 0 THEN 1 ELSE 0 END) AS orders,
				SUM(CASE WHEN si.is_return = 1 THEN 1 ELSE 0 END) AS return_orders
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND {OPENING_FILTER}
			  AND si.posting_date BETWEEN %(start)s AND %(end)s
			GROUP BY si.posting_date ORDER BY si.posting_date
			""",
			{"start": start, "end": end},
			as_dict=True,
		)
		return {
			"rows": [{"date": iso(r.date), "sales": flt(r.sales), "returns": flt(r.returns),
				"orders": cint(r.orders), "return_orders": cint(r.return_orders)} for r in rows],
			"meta": {"year": year, "month": month, "start": iso(start), "end": iso(end)},
		}

	return run_cached("kd.get_daily", {"y": year, "m": month}, build, refresh)


@frappe.whitelist()
def get_orders(date=None, refresh=0):
	"""Danh sách hoá đơn bán/trả của 1 ngày.

	rows: [{name, customer, customer_name, channel, amount, is_return, posting_time}]
	"""
	_guard()
	d = getdate(date or getdate())

	def build():
		rows = frappe.db.sql(
			f"""
			SELECT si.name, si.customer, si.customer_name, si.customer_group,
				{SI_AMOUNT} AS amount, si.is_return, si.posting_time
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.posting_date = %(d)s
			ORDER BY si.posting_time DESC, si.name DESC
			""",
			{"d": d},
			as_dict=True,
		)
		return {
			"rows": [{"name": r.name, "customer": r.customer, "customer_name": r.customer_name or r.customer,
				"channel": CHANNEL_LABELS[channel_of(r.customer_group)], "amount": abs(flt(r.amount)),
				"is_return": cint(r.is_return), "posting_time": str(r.posting_time or "")[:5]} for r in rows],
			"meta": {"date": iso(d)},
		}

	return run_cached("kd.get_orders", {"d": iso(d)}, build, refresh)


@frappe.whitelist()
def get_item_groups(refresh=0):
	"""Doanh số bán ra theo ngành hàng (item_group dòng hoá đơn), năm TC đến hôm nay.

	rows: [{item_group, amount}] giảm dần
	"""
	_guard()

	def build():
		fy, p = _fy_params()
		rows = frappe.db.sql(
			f"""
			SELECT sii.item_group, SUM({SII_AMOUNT}) AS amount
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
			  AND si.posting_date BETWEEN %(fy_start)s AND %(to_date)s
			GROUP BY sii.item_group ORDER BY amount DESC
			""",
			p,
			as_dict=True,
		)
		return {"rows": [{"item_group": r.item_group or "Khác", "amount": flt(r.amount)} for r in rows],
			"meta": {"fy": _fy_meta(fy)}}

	return run_cached("kd.get_item_groups", {}, build, refresh)


@frappe.whitelist()
def get_top_customers(limit=8, refresh=0):
	"""Top khách hàng theo doanh số bán ra năm TC đến hôm nay.

	rows: [{customer, customer_id, amount}]
	"""
	_guard()
	limit = min(max(cint(limit) or 8, 1), 50)

	def build():
		fy, p = _fy_params()
		p["limit"] = limit
		rows = frappe.db.sql(
			f"""
			SELECT si.customer AS customer_id, MAX(si.customer_name) AS customer, SUM({SI_AMOUNT}) AS amount
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
			  AND si.posting_date BETWEEN %(fy_start)s AND %(to_date)s
			GROUP BY si.customer ORDER BY amount DESC LIMIT %(limit)s
			""",
			p,
			as_dict=True,
		)
		return {"rows": [{"customer": r.customer or r.customer_id, "customer_id": r.customer_id,
			"amount": flt(r.amount)} for r in rows], "meta": {"fy": _fy_meta(fy), "limit": limit}}

	return run_cached("kd.get_top_customers", {"limit": limit}, build, refresh)
