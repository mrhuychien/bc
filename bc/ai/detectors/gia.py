# -*- coding: utf-8 -*-
"""bc.ai.detectors.gia — detector "gia" (mảng tro-ly, đặc tả §4.3, hợp đồng P2 §3.1): giá bán lệch trung vị, chiết khấu
dòng cao, giá mua tăng. Kết quả vào pack["tro-ly"]["gia"]; quy tắc gia.* ở bc.ai.rules.ks. Luật chung (cửa sổ, SELECT,
đầu kỳ, khoá đối tác, khối con lỗi riêng): xem bc.ai.detectors.chung_tu.

Dòng bán xét (ban_lech, chiet_khau): Sales Invoice Item của hoá đơn docstatus 1, không trả hàng (is_return 0), không đầu
kỳ, posting_date trong 7 ngày, net_rate > 0 (bỏ hàng tặng / giá 0). Kênh = _common.channel_of(si.customer_group) (nhóm
khách CHỤP trên hoá đơn — như mọi màn doanh số).
- ban_lech (gia.ban_lech): đơn giá theo ĐƠN VỊ KHO = net_rate / conversion_factor (dòng conversion_factor ≤ 0 bỏ). Nền =
  dòng cùng mã × kênh, cùng điều kiện, posting_date trong 90 ngày TRƯỚC cửa sổ ([today − 96, today − 7]); cần ≥ 5 dòng
  nền, không đủ thì bỏ dòng. lech_pct = (trung vị − đơn giá) / trung vị × 100, 1 số lẻ (làm tròn kiểu Math.round);
  dòng lệch khi lech_pct > nguong (ngưỡng vàng đang áp của quy tắc, ngặt). → so_dong_xet (dòng có đủ nền), so_dong,
  so_hd, rows ≤ 20 lệch nhiều trước.
- chiet_khau (gia.chiet_khau_cao): discount_percentage > nguong (ngặt) → so_dong, so_hd, gia_tri (Σ net_amount các dòng
  đó), rows ≤ 20 chiết khấu cao trước.
- mua_tang (gia.mua_tang): Purchase Invoice Item của hoá đơn mua docstatus 1, không trả, không đầu kỳ. Giá mua bình
  quân theo đơn vị kho = Σ base_net_amount / Σ stock_qty (tiền công ty — hoá đơn mua ngoại tệ đã quy đổi). Kỳ mới = 30
  ngày [today − 29, today]; nền = 90 ngày trước đó [today − 119, today − 30]. Chỉ mã có giá trị mua kỳ mới ≥ 20 triệu
  (GIA_TRI_SAN, hằng số) và có mua trong nền (Σ stock_qty > 0 cả hai kỳ). tang_pct (1 số lẻ) > nguong → so_ma, rows ≤ 20
  tăng nhiều trước (nhà cung cấp chính = NCC có giá trị mua kỳ mới lớn nhất, name = hoá đơn mua mới nhất của mã trong kỳ
  mới).

Hiệu năng (EXPLAIN): mọi truy vấn lọc `tabSales Invoice` / `tabPurchase Invoice` theo posting_date (có chỉ mục) trong dải
7 / 96 / 120 ngày rồi nối dòng con qua chỉ mục `parent`; truy vấn nền chỉ lấy mã hàng có trong cửa sổ.
"""

from __future__ import annotations

import datetime
import math
import statistics

import frappe
from frappe.utils import cint, flt

from bc.ai.detectors.chung_tu import DONG_MAX, OPENING, SO_NGAY, cua_so, iso, khoi, nguong
from bc.ai.registry import TRO_LY, detector
from bc.api._common import CHANNEL_LABELS, channel_of

SO_NGAY_NEN = 90         # gia.ban_lech: nền 90 ngày trước cửa sổ
DONG_NEN_MIN = 5         # gia.ban_lech: số dòng nền tối thiểu cho một mã × kênh
SO_NGAY_MUA = 30         # gia.mua_tang: kỳ mới
SO_NGAY_MUA_NEN = 90     # gia.mua_tang: nền
GIA_TRI_SAN = 20_000_000  # gia.mua_tang: giá trị mua kỳ mới tối thiểu của một mã

_BAN = f"""si.docstatus = 1 AND IFNULL(si.is_return, 0) = 0 AND {OPENING.format(a='si.')}
	AND si.posting_date BETWEEN %(tu)s AND %(den)s AND sii.net_rate > 0"""
_MUA = f"""pi.docstatus = 1 AND IFNULL(pi.is_return, 0) = 0 AND {OPENING.format(a='pi.')}
	AND pi.posting_date BETWEEN %(tu)s AND %(den)s"""


def tron(x: float) -> float:
	"""1 số lẻ, đúng giữa làm tròn lên (Math.round của view)."""
	return math.floor(x * 10 + 0.5) / 10


def _kenh(group) -> tuple:
	k = channel_of(group)
	return k, CHANNEL_LABELS.get(k, k)


def _dong_ban(ctx) -> list:
	tu, den = cua_so(ctx)
	return frappe.db.sql(f"""SELECT si.name, si.posting_date, si.customer, si.customer_group, sii.item_code,
			sii.item_name, sii.net_rate, sii.conversion_factor, sii.discount_percentage, sii.net_amount
		FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			AND sii.parenttype = 'Sales Invoice'
		WHERE {_BAN} ORDER BY si.posting_date, si.name, sii.idx""", {"tu": tu, "den": den}, as_dict=True)


def _don_gia(r):
	cf = flt(r.conversion_factor)
	return flt(r.net_rate) / cf if cf > 0 else None


def _ban_lech(ctx, dong: list) -> dict:
	cut = nguong("gia.ban_lech")
	tu, _den = cua_so(ctx)
	ma = sorted({r.item_code for r in dong if r.item_code})
	nen: dict = {}
	if ma:
		for r in frappe.db.sql(f"""SELECT si.customer_group, sii.item_code, sii.net_rate, sii.conversion_factor
				FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
					AND sii.parenttype = 'Sales Invoice'
				WHERE {_BAN} AND sii.item_code IN %(ma)s""", {"tu": tu - datetime.timedelta(days=SO_NGAY_NEN),
				"den": tu - datetime.timedelta(days=1), "ma": tuple(ma)}, as_dict=True):
			g = _don_gia(r)
			if g is not None:
				nen.setdefault((r.item_code, _kenh(r.customer_group)[0]), []).append(g)
	trung_vi = {k: (statistics.median(v), len(v)) for k, v in nen.items() if len(v) >= DONG_NEN_MIN}
	xet, lech = 0, []
	for r in dong:
		g = _don_gia(r)
		k, nhan = _kenh(r.customer_group)
		tv = trung_vi.get((r.item_code, k))
		if g is None or tv is None or tv[0] <= 0:
			continue
		xet += 1
		l = tron((tv[0] - g) / tv[0] * 100)
		if cut is not None and l > cut:
			lech.append({"doctype": "Sales Invoice", "name": r.name, "posting_date": iso(r.posting_date),
				"customer": r.customer, "item_code": r.item_code, "item_name": r.item_name or r.item_code,
				"kenh": nhan, "rate": round(g, 2), "trung_vi": round(tv[0], 2), "lech_pct": l, "so_dong_nen": tv[1]})
	lech.sort(key=lambda x: (-x["lech_pct"], x["name"], x["item_code"]))
	return {"nguong": cut, "so_ngay_nen": SO_NGAY_NEN, "so_dong_xet": xet, "so_dong": len(lech),
		"so_hd": len({x["name"] for x in lech}), "rows": lech[:DONG_MAX]}


def _chiet_khau(ctx, dong: list) -> dict:
	cut = nguong("gia.chiet_khau_cao")
	hit = [r for r in dong if cut is not None and flt(r.discount_percentage) > cut]
	rows = [{"doctype": "Sales Invoice", "name": r.name, "posting_date": iso(r.posting_date), "customer": r.customer,
		"item_code": r.item_code, "item_name": r.item_name or r.item_code, "kenh": _kenh(r.customer_group)[1],
		"ck_pct": round(flt(r.discount_percentage), 2), "gia_tri": round(flt(r.net_amount), 2)} for r in hit]
	rows.sort(key=lambda x: (-x["ck_pct"], -x["gia_tri"], x["name"]))
	return {"nguong": cut, "so_dong": len(hit), "so_hd": len({r.name for r in hit}),
		"gia_tri": round(sum(flt(r.net_amount) for r in hit), 2), "rows": rows[:DONG_MAX]}


def _mua(tu, den, ma=None) -> dict:
	p = {"tu": tu, "den": den}
	them = ""
	if ma is not None:
		p["ma"] = tuple(ma)
		them = " AND pii.item_code IN %(ma)s"
	return {r.item_code: r for r in frappe.db.sql(f"""SELECT pii.item_code, MAX(pii.item_name) AS item_name,
			SUM(pii.base_net_amount) AS tien, SUM(pii.stock_qty) AS sl, COUNT(DISTINCT pi.name) AS so_hd
		FROM `tabPurchase Invoice` pi JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
			AND pii.parenttype = 'Purchase Invoice'
		WHERE {_MUA}{them} GROUP BY pii.item_code""", p, as_dict=True) if r.item_code}


def _mua_tang(ctx) -> dict:
	cut = nguong("gia.mua_tang")
	_tu, den = cua_so(ctx)
	tu = den - datetime.timedelta(days=SO_NGAY_MUA - 1)
	cu_den = tu - datetime.timedelta(days=1)
	cu_tu = tu - datetime.timedelta(days=SO_NGAY_MUA_NEN)
	moi = {k: r for k, r in _mua(tu, den).items() if flt(r.tien) >= GIA_TRI_SAN and flt(r.sl) > 0}
	cu = _mua(cu_tu, cu_den, moi) if moi else {}
	xet, tang = 0, []
	for k, r in moi.items():
		c = cu.get(k)
		if c is None or flt(c.sl) <= 0 or flt(c.tien) <= 0:
			continue
		xet += 1
		g_moi, g_cu = flt(r.tien) / flt(r.sl), flt(c.tien) / flt(c.sl)
		t = tron((g_moi - g_cu) / g_cu * 100)
		if cut is not None and t > cut:
			tang.append({"item_code": k, "item_name": r.item_name or k, "gia_moi": round(g_moi, 2),
				"gia_cu": round(g_cu, 2), "tang_pct": t, "gia_tri_mua": round(flt(r.tien), 2), "so_hd": cint(r.so_hd)})
	tang.sort(key=lambda x: (-x["tang_pct"], x["item_code"]))
	tang = tang[:DONG_MAX]
	if tang:
		p = {"tu": tu, "den": den, "ma": tuple(x["item_code"] for x in tang)}
		ncc, hd = {}, {}
		for r in frappe.db.sql(f"""SELECT pii.item_code, pi.supplier, SUM(pii.base_net_amount) AS tien
				FROM `tabPurchase Invoice` pi JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
					AND pii.parenttype = 'Purchase Invoice'
				WHERE {_MUA} AND pii.item_code IN %(ma)s GROUP BY pii.item_code, pi.supplier
				ORDER BY pii.item_code, tien DESC, pi.supplier""", p, as_dict=True):
			ncc.setdefault(r.item_code, r.supplier)
		for r in frappe.db.sql(f"""SELECT pii.item_code, pi.name FROM `tabPurchase Invoice` pi
				JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name AND pii.parenttype = 'Purchase Invoice'
				WHERE {_MUA} AND pii.item_code IN %(ma)s ORDER BY pi.posting_date DESC, pi.creation DESC, pi.name DESC""",
				p, as_dict=True):
			hd.setdefault(r.item_code, r.name)
		for x in tang:
			if ncc.get(x["item_code"]):
				x["supplier"] = ncc[x["item_code"]]
			if hd.get(x["item_code"]):
				x.update(doctype="Purchase Invoice", name=hd[x["item_code"]])
	return {"nguong": cut, "so_ngay": SO_NGAY_MUA, "so_ngay_nen": SO_NGAY_MUA_NEN, "gia_tri_san": GIA_TRI_SAN,
		"so_ma_xet": xet, "so_ma": len(tang), "rows": tang}


@detector("gia", section=TRO_LY)
def d_gia(ctx):
	tu, den = cua_so(ctx)
	dong = khoi("gia.dong_ban", lambda: {"dong": _dong_ban(ctx)})
	out = {"tu": iso(tu), "den": iso(den), "so_ngay": SO_NGAY}
	if dong.get("_error"):
		out["ban_lech"] = out["chiet_khau"] = {"_error": True}
	else:
		out["ban_lech"] = khoi("gia.ban_lech", _ban_lech, ctx, dong["dong"])
		out["chiet_khau"] = khoi("gia.chiet_khau", _chiet_khau, ctx, dong["dong"])
	out["mua_tang"] = khoi("gia.mua_tang", _mua_tang, ctx)
	return out
