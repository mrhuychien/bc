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
	channel_of,
	drop_hidden,
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


@frappe.whitelist()
def get_monthly(refresh=0):
	"""Doanh số 12 tháng năm TC (T{fy_start_month} → …): năm nay và năm trước.

	rows: [{period: current|last_year, month (1-12), fy_month (1-12, tháng đầu năm TC = 1),
	        sales, returns}]
	"""
	_guard()

	def build():
		fy, p = _fy_params()
		start_m = fy["fy_start"].month
		rows = frappe.db.sql(
			# SQL thay ORM: GROUP BY năm-tháng 2 năm TC trong 1 truy vấn.
			f"""
			SELECT CASE WHEN si.posting_date >= %(fy_start)s THEN 'current' ELSE 'last_year' END AS period,
				MONTH(si.posting_date) AS month,
				SUM(CASE WHEN si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS sales,
				SUM(CASE WHEN si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS returns
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND {OPENING_FILTER}
			  AND si.posting_date BETWEEN %(ly_start)s AND %(to_date)s
			GROUP BY period, month
			""",
			p,
			as_dict=True,
		)
		got = {(r.period, cint(r.month)): r for r in rows}
		out = []
		for period in ("current", "last_year"):
			for i in range(12):
				m = (start_m - 1 + i) % 12 + 1
				r = got.get((period, m))
				out.append({"period": period, "month": m, "fy_month": i + 1,
					"sales": flt(r.sales) if r else 0.0, "returns": flt(r.returns) if r else 0.0})
		return {"rows": out, "meta": {"fy": _fy_meta(fy)}}

	return run_cached("kd.get_monthly", {}, build, refresh)


@frappe.whitelist()
def get_provinces(refresh=0):
	"""Doanh số bán ra theo tỉnh (chuẩn hoá 34 tỉnh), năm TC đến hôm nay.

	rows: [{province, sales, pct}] giảm dần; pct = % tổng doanh số.
	"""
	_guard()
	from bc.api import _provinces

	def build():
		fy, p = _fy_params()
		col = _provinces.province_column()
		agg: dict[str, float] = {}
		if col:
			rows = frappe.db.sql(
				# col ∈ whitelist PROV_COLUMNS — không phải input người dùng.
				f"""
				SELECT si.`{col}` AS prov, MAX(si.customer_name) AS cname, SUM({SI_AMOUNT}) AS sales
				FROM `tabSales Invoice` si
				WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
				  AND si.posting_date BETWEEN %(fy_start)s AND %(to_date)s
				GROUP BY si.`{col}`
				""",
				p,
				as_dict=True,
			)
			for r in rows:
				k = _provinces.resolve(r.prov)
				agg[k] = agg.get(k, 0.0) + flt(r.sales)
		else:
			rows = frappe.db.sql(
				f"""
				SELECT c.territory, c.customer_name, SUM({SI_AMOUNT}) AS sales
				FROM `tabSales Invoice` si
				LEFT JOIN `tabCustomer` c ON c.name = si.customer
				WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
				  AND si.posting_date BETWEEN %(fy_start)s AND %(to_date)s
				GROUP BY si.customer, c.territory, c.customer_name
				""",
				p,
				as_dict=True,
			)
			for r in rows:
				k = _provinces.resolve(None, r.territory, r.customer_name)
				agg[k] = agg.get(k, 0.0) + flt(r.sales)
		total = sum(agg.values())
		out = sorted(({"province": k, "sales": v, "pct": pct(v, total)} for k, v in agg.items()),
			key=lambda x: x["sales"], reverse=True)
		return {"rows": out, "meta": {"fy": _fy_meta(fy), "source": col or "customer.territory", "total": total}}

	return run_cached("kd.get_provinces", {}, build, refresh)


@frappe.whitelist()
def get_top_products(group="all", refresh=0):
	"""Top sản phẩm theo số hộp (đơn vị kho, đã trừ trả) — lọc theo item_group.

	group: all | tet | traditional. tet dùng mùa Tết (season_start → asof, so cùng kỳ
	mùa trước theo BC Settings.tet_compare_mode); còn lại dùng năm TC vs cùng kỳ.
	rows: [{item_code, item_name, short_name, item_group, qty, qty_sp, growth_pct}]
	"""
	_guard()
	if group not in ("all", "tet", "traditional"):
		frappe.throw("Nhóm không hợp lệ")

	def build():
		params: dict = {}
		group_sql = ""
		if group == "tet":
			s = tet_season()
			params.update(cs=s["season_start"], ce=s["asof"], ps=s["ly_season_start"], pe=s["ly_asof"])
			meta = {"window": "tet", "tet_year": s["tet_year"], "compare_mode": s["compare_mode"],
				**{k: iso(v) for k, v in params.items()}}
			params["grp"] = tet_group()
			group_sql = "AND sii.item_group = %(grp)s"
		else:
			fy = fy_range()
			params.update(cs=fy["fy_start"], ce=fy["to_date"], ps=fy["sp_start"], pe=fy["sp_end"])
			meta = {"window": "fy", **{k: iso(v) for k, v in params.items()}}
			if group == "traditional":
				params["grp"] = traditional_group()
				group_sql = "AND sii.item_group = %(grp)s"
		rows = frappe.db.sql(
			# stock_qty của dòng trả hàng là số âm → SUM ra số hộp thực bán.
			f"""
			SELECT sii.item_code, MAX(sii.item_name) AS item_name, MAX(sii.item_group) AS item_group,
				SUM(CASE WHEN si.posting_date BETWEEN %(cs)s AND %(ce)s THEN sii.stock_qty ELSE 0 END) AS qty,
				SUM(CASE WHEN si.posting_date BETWEEN %(ps)s AND %(pe)s THEN sii.stock_qty ELSE 0 END) AS qty_sp
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND {OPENING_FILTER}
			  AND (si.posting_date BETWEEN %(cs)s AND %(ce)s OR si.posting_date BETWEEN %(ps)s AND %(pe)s)
			  {group_sql}
			GROUP BY sii.item_code
			HAVING qty > 0 OR qty_sp > 0
			ORDER BY qty DESC
			LIMIT 300
			""",
			params,
			as_dict=True,
		)
		meta["group"] = group
		meta["item_group"] = params.get("grp")
		rows = drop_hidden(rows)  # mã admin đã ẩn khỏi báo cáo
		return {"rows": [{"item_code": r.item_code, "item_name": r.item_name, "short_name": short_name(r.item_name),
			"item_group": r.item_group, "qty": flt(r.qty), "qty_sp": flt(r.qty_sp),
			"growth_pct": growth(r.qty, r.qty_sp)} for r in rows], "meta": meta}

	return run_cached("kd.get_top_products", {"group": group}, build, refresh)
