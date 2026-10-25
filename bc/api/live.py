# -*- coding: utf-8 -*-
"""bc.api.live — "Báo cáo thời gian thực": ảnh chụp vận hành HÔM NAY cho tab #/thoi-gian-thuc.

Một lượt gọi trả đủ khối: bán hàng hôm nay (so cùng giờ hôm qua), luỹ kế tháng (so cùng
kỳ tháng trước), sản xuất hôm nay (phiếu Material Receipt vào kho thành phẩm — cùng nguồn
với SX Hàng Tết), tồn kho thành phẩm, đơn chờ giao, nhập nguyên vật liệu, theo giờ, top
mã SX hôm nay và dòng sự kiện mới nhất; thêm số liệu THEO KHU cho card khi bấm vào sơ đồ 3D
(tồn từng kho ERPNext, doanh số theo kênh / khách, đơn chờ giao gần hạn, luỹ kế năm TC).
Cache 30 giây (dùng chung mọi người xem); SPA tự làm mới mỗi 60 giây. Mọi mốc thời gian
tính ở Python.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, now_datetime

from bc.api._common import (
	CHANNEL_LABELS,
	OPENING_FILTER,
	SI_AMOUNT,
	_guard,
	cached,
	cache_key,
	carton_factors,
	channel_of,
	drop_hidden,
	fy_label,
	fy_range,
	growth,
	iso,
	short_name,
	to_cartons,
)
from bc.api.sx import _wh

LIVE_TTL = 30
SO_OPEN = ("To Deliver and Bill", "To Deliver")


def _sales(day, until_time=None) -> dict:
	"""Bán / trả / số đơn / số khách của 1 ngày (tuỳ chọn: chỉ tính đến giờ until_time)."""
	cond = "AND si.posting_time <= %(t)s" if until_time else ""
	r = frappe.db.sql(
		# SQL thay ORM: tổng có điều kiện bán/trả + đếm đơn/khách trong 1 lượt.
		f"""
		SELECT SUM(CASE WHEN si.is_return = 0 THEN {SI_AMOUNT} ELSE 0 END) AS sales,
			SUM(CASE WHEN si.is_return = 1 THEN -{SI_AMOUNT} ELSE 0 END) AS returns,
			SUM(CASE WHEN si.is_return = 0 THEN 1 ELSE 0 END) AS orders,
			SUM(CASE WHEN si.is_return = 1 THEN 1 ELSE 0 END) AS return_orders,
			COUNT(DISTINCT CASE WHEN si.is_return = 0 THEN si.customer END) AS customers
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.posting_date = %(d)s {cond}
		""",
		{"d": day, "t": until_time},
		as_dict=True,
	)[0]
	return {"sales": flt(r.sales), "returns": flt(r.returns), "orders": cint(r.orders),
		"return_orders": cint(r.return_orders), "customers": cint(r.customers)}


def _sales_between(start, end) -> float:
	return flt(frappe.db.sql(
		f"""SELECT SUM({SI_AMOUNT}) FROM `tabSales Invoice` si
		    WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0
		      AND si.posting_date BETWEEN %s AND %s""", (start, end))[0][0])


def _production_rows(day, wh, until_time=None) -> list:
	cond = "AND se.posting_time <= %(t)s" if until_time else ""
	return frappe.db.sql(
		f"""
		SELECT sed.item_code, MAX(sed.item_name) AS item_name, HOUR(se.posting_time) AS hr,
			SUM(sed.transfer_qty) AS boxes, SUM(sed.amount) AS amount, COUNT(DISTINCT se.name) AS vouchers
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.docstatus = 1 AND se.stock_entry_type = 'Material Receipt' AND sed.t_warehouse = %(wh)s
		  AND se.posting_date = %(d)s {cond}
		GROUP BY sed.item_code, HOUR(se.posting_time)
		""",
		{"d": day, "wh": wh, "t": until_time},
		as_dict=True,
	)


def _voucher_count(day, wh) -> int:
	return cint(frappe.db.sql(
		"""SELECT COUNT(DISTINCT se.name) FROM `tabStock Entry` se JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		   WHERE se.docstatus = 1 AND se.stock_entry_type = 'Material Receipt' AND sed.t_warehouse = %s
		     AND se.posting_date = %s""", (wh, day))[0][0])


def _finished_stock(wh) -> dict:
	rows = frappe.db.sql(
		"""
		SELECT b.item_code, MAX(i.item_name) AS item_name, SUM(b.actual_qty) AS qty, SUM(b.stock_value) AS value
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		JOIN `tabWarehouse` root ON root.name = %(wh)s
		WHERE w.lft >= root.lft AND w.rgt <= root.rgt AND b.actual_qty != 0
		GROUP BY b.item_code
		""",
		{"wh": wh},
		as_dict=True,
	)
	f = carton_factors(r.item_code for r in rows)
	top = [{"item_code": r.item_code, "short_name": short_name(r.item_name), "boxes": flt(r.qty),
		"cartons": to_cartons(r.qty, f.get(r.item_code))} for r in rows if flt(r.qty) > 0]
	top = sorted(drop_hidden(top), key=lambda x: x["cartons"] or x["boxes"], reverse=True)[:5]
	return {
		"boxes": sum(flt(r.qty) for r in rows),
		"cartons": round(sum(to_cartons(r.qty, f.get(r.item_code)) for r in rows), 1),
		"value": sum(flt(r.value) for r in rows),
		"items": sum(1 for r in rows if flt(r.qty) > 0),
		"top": top,
	}


def _pending_orders(today) -> dict:
	"""Sales Order chờ giao: số đơn, giá trị còn giao, số đơn quá hạn giao, 5 đơn gần hạn nhất."""
	remain = "so.net_total * (100 - IFNULL(so.per_delivered, 0)) / 100"
	r = frappe.db.sql(
		f"""SELECT COUNT(*) AS n, SUM({remain}) AS amount,
		          SUM(CASE WHEN so.delivery_date < %(d)s THEN 1 ELSE 0 END) AS overdue
		   FROM `tabSales Order` so WHERE so.docstatus = 1 AND so.status IN %(st)s""",
		{"st": SO_OPEN, "d": today}, as_dict=True)[0]
	top = frappe.db.sql(
		f"""SELECT so.customer_name, so.delivery_date, {remain} AS amount
		   FROM `tabSales Order` so WHERE so.docstatus = 1 AND so.status IN %(st)s
		   ORDER BY so.delivery_date ASC, so.name ASC LIMIT 5""",
		{"st": SO_OPEN}, as_dict=True)
	return {"count": cint(r.n), "amount": flt(r.amount), "overdue": cint(r.overdue),
		"top": [{"customer": t.customer_name, "delivery_date": iso(t.delivery_date), "amount": flt(t.amount),
			"overdue": bool(t.delivery_date and getdate(t.delivery_date) < today)} for t in top]}


def _purchases(day) -> dict:
	r = frappe.db.sql(
		"""SELECT COUNT(*) AS n, SUM(pr.net_total) AS amount FROM `tabPurchase Receipt` pr
		   WHERE pr.docstatus = 1 AND pr.posting_date = %s""", (day,), as_dict=True)[0]
	return {"count": cint(r.n), "amount": flt(r.amount)}


def _sales_breakdown(day) -> dict:
	"""Doanh số bán hôm nay theo kênh + 5 khách mua nhiều nhất (cho card Phòng kinh doanh)."""
	rows = frappe.db.sql(
		f"""SELECT si.customer_group AS grp, si.customer, MAX(si.customer_name) AS customer_name,
		          SUM({SI_AMOUNT}) AS v
		   FROM `tabSales Invoice` si
		   WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0 AND si.posting_date = %s
		   GROUP BY si.customer_group, si.customer""", (day,), as_dict=True)
	by_ch: dict = {}
	by_cust: dict = {}
	for r in rows:
		ch = CHANNEL_LABELS[channel_of(r.grp)]
		by_ch[ch] = by_ch.get(ch, 0.0) + flt(r.v)
		c = by_cust.setdefault(r.customer, {"customer": r.customer_name or r.customer, "amount": 0.0})
		c["amount"] += flt(r.v)
	return {
		"by_channel": sorted(({"channel": k, "amount": v} for k, v in by_ch.items()), key=lambda x: x["amount"], reverse=True),
		"top_customers": sorted(by_cust.values(), key=lambda x: x["amount"], reverse=True)[:5],
	}


def _fy_sales() -> dict:
	"""Luỹ kế năm tài chính đến hôm nay vs cùng kỳ năm trước (card Phòng Chủ tịch)."""
	fy = fy_range()
	cur, prev = _sales_between(fy["fy_start"], fy["to_date"]), _sales_between(fy["sp_start"], fy["sp_end"])
	return {"sales": cur, "prev": prev, "growth": growth(cur, prev), "label": fy_label(fy)}


def _warehouses() -> list:
	"""Tồn kho từng kho ERPNext (kho lá, đang dùng): giá trị, số mã có tồn, 5 mã giá trị lớn nhất.

	SPA khớp tên kho với tên khu trên sơ đồ 3D (vd "Kho đường" ↔ "Kho đường - HGC").
	"""
	summary = frappe.db.sql(
		"""SELECT b.warehouse, MAX(w.warehouse_name) AS warehouse_name,
		          COUNT(DISTINCT CASE WHEN b.actual_qty > 0 THEN b.item_code END) AS items,
		          SUM(b.stock_value) AS value
		   FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
		   WHERE w.is_group = 0 AND IFNULL(w.disabled, 0) = 0
		   GROUP BY b.warehouse""", as_dict=True)
	tops: dict = {}
	# Window function (MariaDB ≥ 10.2): 8 mã giá trị lớn nhất mỗi kho trong 1 truy vấn.
	for r in frappe.db.sql(
		"""SELECT t.warehouse, t.item_code, t.item_name, t.stock_uom, t.qty, t.value FROM (
		       SELECT b.warehouse, b.item_code, i.item_name, i.stock_uom, b.actual_qty AS qty, b.stock_value AS value,
		              ROW_NUMBER() OVER (PARTITION BY b.warehouse ORDER BY b.stock_value DESC, b.actual_qty DESC) AS rn
		       FROM `tabBin` b JOIN `tabItem` i ON i.name = b.item_code
		       WHERE b.actual_qty > 0) t
		   WHERE t.rn <= 8""", as_dict=True):
		tops.setdefault(r.warehouse, []).append({"item_code": r.item_code, "item_name": short_name(r.item_name),
			"qty": flt(r.qty), "uom": r.stock_uom, "value": flt(r.value)})
	out = []
	for w in summary:
		if not cint(w.items) and not flt(w.value):
			continue
		out.append({"name": w.warehouse, "warehouse_name": w.warehouse_name or w.warehouse, "items": cint(w.items),
			"value": flt(w.value), "top": drop_hidden(tops.get(w.warehouse, []))[:5]})
	return out


def _feed(day, wh, limit=14) -> list:
	"""Sự kiện mới nhất trong ngày: hoá đơn bán/trả, phiếu nhập thành phẩm, nhập NVL."""
	ev = []
	for r in frappe.db.sql(
		f"""SELECT si.name, si.customer_name, si.customer_group, {SI_AMOUNT} AS amount, si.is_return, si.posting_time
		    FROM `tabSales Invoice` si
		    WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.posting_date = %s
		    ORDER BY si.posting_time DESC LIMIT %s""", (day, limit), as_dict=True):
		ev.append({"kind": "return" if cint(r.is_return) else "sale", "time": str(r.posting_time or "")[:5],
			"title": r.customer_name, "sub": CHANNEL_LABELS[channel_of(r.customer_group)],
			"amount": abs(flt(r.amount)), "doc": r.name, "doctype": "sales-invoice"})
	for r in frappe.db.sql(
		"""SELECT se.name, se.posting_time, SUM(sed.transfer_qty) AS boxes, COUNT(DISTINCT sed.item_code) AS items,
		          MAX(sed.item_name) AS item_name
		   FROM `tabStock Entry` se JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		   WHERE se.docstatus = 1 AND se.stock_entry_type = 'Material Receipt' AND sed.t_warehouse = %s
		     AND se.posting_date = %s
		   GROUP BY se.name, se.posting_time ORDER BY se.posting_time DESC LIMIT %s""", (wh, day, limit), as_dict=True):
		ev.append({"kind": "production", "time": str(r.posting_time or "")[:5],
			"title": short_name(r.item_name) + (f" +{cint(r.items) - 1} mã" if cint(r.items) > 1 else ""),
			"sub": "Nhập kho thành phẩm", "boxes": flt(r.boxes), "doc": r.name, "doctype": "stock-entry"})
	for r in frappe.db.sql(
		"""SELECT pr.name, pr.supplier_name, pr.net_total, pr.posting_time FROM `tabPurchase Receipt` pr
		   WHERE pr.docstatus = 1 AND pr.posting_date = %s ORDER BY pr.posting_time DESC LIMIT %s""",
		(day, limit), as_dict=True):
		ev.append({"kind": "purchase", "time": str(r.posting_time or "")[:5], "title": r.supplier_name,
			"sub": "Nhập nguyên vật liệu", "amount": flt(r.net_total), "doc": r.name, "doctype": "purchase-receipt"})
	ev.sort(key=lambda e: e["time"], reverse=True)
	return ev[:limit]


@frappe.whitelist()
def get_snapshot(refresh=0):
	"""Ảnh chụp vận hành hôm nay (xem docstring module)."""
	_guard()
	now = now_datetime()
	today = getdate(now)
	minute = now.strftime("%H:%M")

	def build():
		wh = _wh()
		t_now = now.strftime("%H:%M:%S")
		yday = getdate(add_days(today, -1))
		sales = _sales(today)
		sales_y = _sales(yday, t_now)
		mtd_start = get_first_day(today)
		prev_start = getdate(add_months(mtd_start, -1))
		prev_end = getdate(add_days(prev_start, (today - mtd_start).days))  # cùng số ngày đã trôi
		mtd, mtd_prev = _sales_between(mtd_start, today), _sales_between(prev_start, prev_end)

		prod_rows = _production_rows(today, wh)
		prod_y = _production_rows(yday, wh, t_now)
		f = carton_factors({r.item_code for r in prod_rows} | {r.item_code for r in prod_y})
		by_item: dict = {}
		hourly_prod = [0.0] * 24
		for r in prod_rows:
			it = by_item.setdefault(r.item_code, {"item_code": r.item_code, "item_name": r.item_name, "boxes": 0.0, "amount": 0.0})
			it["boxes"] += flt(r.boxes)
			it["amount"] += flt(r.amount)
			hourly_prod[cint(r.hr) % 24] += to_cartons(r.boxes, f.get(r.item_code))
		for it in by_item.values():
			it["cartons"] = to_cartons(it["boxes"], f.get(it["item_code"]))
			it["short_name"] = short_name(it["item_name"])
		top_prod = sorted(drop_hidden(list(by_item.values())), key=lambda x: x["cartons"] or x["boxes"], reverse=True)[:6]
		prod_cartons = round(sum(to_cartons(r.boxes, f.get(r.item_code)) for r in prod_rows), 1)
		prod_cartons_y = round(sum(to_cartons(r.boxes, f.get(r.item_code)) for r in prod_y), 1)

		hourly_sales = [0.0] * 24
		for r in frappe.db.sql(
			f"""SELECT HOUR(si.posting_time) AS hr, SUM({SI_AMOUNT}) AS v FROM `tabSales Invoice` si
			    WHERE si.docstatus = 1 AND {OPENING_FILTER} AND si.is_return = 0 AND si.posting_date = %s
			    GROUP BY HOUR(si.posting_time)""", (today,), as_dict=True):
			hourly_sales[cint(r.hr) % 24] = flt(r.v)

		return {
			"meta": {"date": iso(today), "time": minute, "warehouse": wh, "ttl": LIVE_TTL,
				"server_now": now.isoformat(timespec="seconds")},
			"sales": {**sales, "net": sales["sales"] - sales["returns"],
				"yesterday_same_time": sales_y["sales"], "growth": growth(sales["sales"], sales_y["sales"]),
				"orders_yesterday": sales_y["orders"], **_sales_breakdown(today)},
			"fy": _fy_sales(),
			"mtd": {"sales": mtd, "prev": mtd_prev, "growth": growth(mtd, mtd_prev),
				"from": iso(mtd_start), "prev_from": iso(prev_start), "prev_to": iso(prev_end)},
			"production": {"cartons": prod_cartons, "boxes": sum(flt(r.boxes) for r in prod_rows),
				"amount": sum(flt(r.amount) for r in prod_rows),
				"vouchers": _voucher_count(today, wh),
				"items": len(by_item), "yesterday_same_time": prod_cartons_y,
				"growth": growth(prod_cartons, prod_cartons_y), "top": top_prod},
			"stock": _finished_stock(wh),
			"pending": _pending_orders(today),
			"warehouses": _warehouses(),
			"purchases": _purchases(today),
			"hourly": {"sales": hourly_sales, "production": [round(v, 1) for v in hourly_prod]},
			"feed": _feed(today, wh),
		}

	# Key theo phút + TTL 30s: mọi người xem dùng chung 1 lần tính, số luôn tươi.
	return cached(cache_key("live.get_snapshot", {"m": f"{iso(today)} {minute}"}), build, ttl=LIVE_TTL, refresh=refresh)
