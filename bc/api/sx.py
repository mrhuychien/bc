# -*- coding: utf-8 -*-
"""bc.api.sx — Sản xuất Hàng Tết (port "Quản lý sản xuất Hàng Tết" + "Sản lượng sản
xuất theo ngày").

Nguồn: phiếu SẢN XUẤT nhập kho thành phẩm (production_filter(): Manufacture dòng thành phẩm +
Material Receipt không phải điều chỉnh kho), dòng nhập vào kho thành phẩm (BC Settings.sx_warehouse →
SX Settings.kho_tp → "Thành phẩm - HGC"); số lượng theo đơn vị kho (transfer_qty = hộp), thùng = hộp /
hệ số UOM "Thùng" của Item. Xuất bán = Sales Invoice (stock_qty, không tính trả).
Tồn kho = Bin.actual_qty hiện tại CHỈ kho thành phẩm (sx_warehouse, gồm kho con nếu là nhóm). Ảnh + nhóm hàng join Item ngay trong
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
	drop_hidden,
	get_settings,
	iso,
	pct,
	plan_column,
	plans_of,
	run_cached,
	short_name,
	sx_default_range,
	tet_group,
	to_cartons,
	traditional_group,
)

# Phiếu SẢN XUẤT nhập kho thành phẩm. Trước chỉ đếm Material Receipt → thiếu hàng có BOM (app sx
# ghi Work Order + Manufacture, sx_phieu_nhap_tp.py on_submit) và thừa phiếu điều chỉnh kho:
#  · Manufacture: chỉ dòng thành phẩm (is_finished_item) — bỏ dòng nguyên liệu / phế phẩm.
#  · Material Receipt: phiếu nhập tay trước khi có app sx + hàng chưa có BOM của sx ("Nhập tạm —"),
#    TRỪ phiếu điều chỉnh của app sx: kiểm kê / bù sau kiểm kê (custom_kiem_ke) và các lần dọn
#    lô / tồn (remarks bắt đầu bằng GHI_CHU của sx/api/lo_cu.py, lo_am.py, tonam.py).
#  · Material Transfer từ Kho Xưởng sản xuất (SX Settings.kho_xuong) vào Kho TP: trước D191 (12/10/2026)
#    thành phẩm vào Kho TP bằng phiếu chuyển này mà không ghi sản xuất vào Xưởng (sx README D192/D193) —
#    với lượng hàng đó phiếu chuyển là chứng từ DUY NHẤT đưa hàng vào Kho TP. Chuyển từ kho khác (cửa
#    hàng, hàng trả về, cách ly) không phải sản xuất. Chưa đặt kho_xuong → không tính nhánh này.
# Lọc theo `purpose` (chuẩn) chứ không theo tên Stock Entry Type (site có thể đổi tên loại).
PRODUCTION_PURPOSES = ("Manufacture", "Material Receipt")
ADJUSTMENT_REMARKS = ("Dọn tồn không lô sau bật lô", "Dọn âm lịch sử lô (D207)", "Dọn tồn âm thành phẩm")
SX_WAREHOUSE_DEFAULT = "Thành phẩm - HGC"


def _kho_xuong() -> str | None:
	"""SX Settings.kho_xuong (đọc mềm) — như sx tonam D193: chỉ đúng kho này, không lấy kho khác thay."""
	if not frappe.db.exists("DocType", "SX Settings"):
		return None
	try:
		return frappe.db.get_single_value("SX Settings", "kho_xuong") or None
	except Exception:
		frappe.clear_last_message()
		return None


def production_purposes() -> list:
	return [*PRODUCTION_PURPOSES, "Material Transfer"] if _kho_xuong() else list(PRODUCTION_PURPOSES)


def production_filter() -> str:
	"""Điều kiện WHERE cho dòng thành phẩm sản xuất — alias `se`/`sed`, PHẢI truyền %(sx_wh)s (xem _wh())."""
	# LOCATE(...) != 1 thay vì NOT LIKE 'x%': chuỗi không chứa % nên không vướng pyformat của frappe.db.sql.
	not_adjust = " AND ".join(f"LOCATE({frappe.db.escape(p)}, IFNULL(se.remarks, '')) != 1" for p in ADJUSTMENT_REMARKS)
	if frappe.db.has_column("Stock Entry", "custom_kiem_ke"):  # field của app sx — site không cài sx thì không có
		not_adjust += " AND IFNULL(se.custom_kiem_ke, '') = ''"
	xuong = _kho_xuong()
	transfer = (f"""
		OR (se.purpose = 'Material Transfer' AND sed.s_warehouse = {frappe.db.escape(xuong)} AND {not_adjust})"""
		if xuong and xuong != _wh() else "")
	return f"""se.docstatus = 1 AND sed.t_warehouse = %(sx_wh)s AND (
		(se.purpose = 'Manufacture' AND sed.is_finished_item = 1)
		OR (se.purpose = 'Material Receipt' AND {not_adjust}){transfer})"""


def _wh() -> str:
	"""Kho thành phẩm: BC Settings → kho TP của app sx (đọc mềm) → mặc định."""
	wh = get_settings().get("sx_warehouse")
	if not wh and frappe.db.exists("DocType", "SX Settings"):
		try:
			wh = frappe.db.get_single_value("SX Settings", "kho_tp")
		except Exception:
			frappe.clear_last_message()
			wh = None
	return wh or SX_WAREHOUSE_DEFAULT


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
	        plan, stock (hộp), stock_cartons (thùng), carton_factor, produced, outgoing,
	        plan_cartons, produced_cartons, outgoing_cartons (thùng),
	        produced_pct, outgoing_pct}] — sắp tồn kho giảm dần
	"""
	_guard("sx-tet")
	f, t = _range(from_date, to_date)

	def build():
		p = {"f": f, "t": t, "sx_wh": _wh()}
		produced = {r.item_code: flt(r.qty) for r in frappe.db.sql(
			# SQL thay ORM: join Stock Entry ↔ Detail + lọc dòng thành phẩm.
			f"""
			SELECT sed.item_code, SUM(sed.transfer_qty) AS qty
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {production_filter()} AND se.posting_date BETWEEN %(f)s AND %(t)s
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
				(SELECT COALESCE(SUM(b.actual_qty), 0) FROM `tabBin` b
				 JOIN `tabWarehouse` w ON w.name = b.warehouse
				 JOIN `tabWarehouse` root ON root.name = %(sx_wh)s
				 WHERE b.item_code = i.name AND w.lft >= root.lft AND w.rgt <= root.rgt) AS stock
			FROM `tabItem` i WHERE i.name IN %(codes)s
			""",
			{"codes": tuple(codes), "sx_wh": _wh()},
			as_dict=True,
		)
		plans = plans_of(codes)
		factors = carton_factors(codes)
		rows = []
		for it in items:
			plan = plans.get(it.item_code, 0.0)
			prod = produced.get(it.item_code, 0.0)
			out = outgoing.get(it.item_code, 0.0)
			rows.append({
				"item_code": it.item_code,
				"item_name": it.item_name,
				"short_name": short_name(it.item_name),
				"item_group": it.item_group,
				"group_key": _group_key(it.item_group),
				"image": it.image or None,
				"plan": plan,
				"stock": flt(it.stock),
				"stock_cartons": to_cartons(it.stock, factors.get(it.item_code)),
				"carton_factor": factors.get(it.item_code),
				"produced": prod,
				"outgoing": out,
				"plan_cartons": to_cartons(plan, factors.get(it.item_code)),
				"produced_cartons": to_cartons(prod, factors.get(it.item_code)),
				"outgoing_cartons": to_cartons(out, factors.get(it.item_code)),
				"produced_pct": pct(prod, plan),
				"outgoing_pct": pct(out, plan if plan else prod),
			})
		rows = drop_hidden(rows)  # mã admin đã ẩn khỏi báo cáo
		rows.sort(key=lambda r: (r["stock"], r["produced"]), reverse=True)  # tồn kho lớn → bé
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
		    JOIN `tabStock Entry` se ON se.name = sed.parent WHERE {production_filter()}""", {"sx_wh": _wh()})[0][0]
	return {
		"has_production": has_production,
		"entries_by_purpose": by_purpose,
		"entry_types": production_purposes(),
		"entry_type": " / ".join(production_purposes()),
		"warehouse": _wh(),
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
	_guard("sx-tet")
	year, month, start, end = _month_range(year, month)

	def build():
		raw = frappe.db.sql(
			f"""
			SELECT se.posting_date AS date, sed.item_code, SUM(sed.transfer_qty) AS boxes, SUM(sed.amount) AS amount
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {production_filter()} AND se.posting_date BETWEEN %(s)s AND %(e)s
			GROUP BY se.posting_date, sed.item_code
			""",
			{"s": start, "e": end, "sx_wh": _wh()},
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
	_guard("sx-tet")
	d = getdate(date or getdate())

	def build():
		raw = frappe.db.sql(
			f"""
			SELECT se.name AS voucher, sed.item_code, MAX(sed.item_name) AS item_name,
				SUM(sed.transfer_qty) AS boxes, SUM(sed.amount) AS amount
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE {production_filter()} AND se.posting_date = %(d)s
			GROUP BY se.name, sed.item_code
			ORDER BY se.name, sed.item_code
			""",
			{"d": d, "sx_wh": _wh()},
			as_dict=True,
		)
		factors = carton_factors(r.item_code for r in raw)
		rows = [{"item_code": r.item_code, "item_name": r.item_name, "boxes": flt(r.boxes),
			"cartons": to_cartons(r.boxes, factors.get(r.item_code)), "amount": flt(r.amount),
			"voucher": r.voucher} for r in raw]
		return {"rows": rows, "meta": {"date": iso(d)}}

	return run_cached("sx.get_daily_detail", {"d": iso(d)}, build, refresh)
