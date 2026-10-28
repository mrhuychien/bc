# -*- coding: utf-8 -*-
"""bc.api.kho_nhap — Nhập kho thành phẩm và giá vốn chưa thật (đặc tả Kho bản chốt: K11, K12).

Một lượt get_overview(thang) trả 6 khối, mỗi khối một safe_block (lỗi / thiếu bảng chỉ tắt khối đó):
- nhap (K11): thành phẩm thủ kho ĐÃ DUYỆT nhận vào kho = Σ SX Phieu Nhap TP Item.so_dem của phiếu docstatus 1, theo
  NGÀY NHẬN của phiếu (SX Phieu Nhap TP.ngay — sx ghi mọi phiếu kho của phiếu đúng ngày này), từng ngày trong tháng và
  12 tháng đến tháng chọn; đơn vị kho (hộp) + thùng (carton_factors, kèm phần chưa khai quy cách thùng). Giá trị =
  Σ SLE.stock_value_difference (dòng sổ sống, actual_qty > 0) của các Stock Entry ghi trong ds_se của phiếu, CHỈ dòng
  thành phẩm: se.purpose = 'Material Receipt' (nhập tạm chưa có BOM) HOẶC sed.is_finished_item = 1 (Manufacture) — dòng
  phụ phẩm / phế phẩm (secondary_item_type) cũng chỉ có kho đích nhưng không phải thành phẩm (W6). Đối chiếu từng
  (phiếu, mã): Σ số lượng các dòng sổ đó phải = Σ so_dem (phiếu đã duyệt mà phiếu kho bị huỷ / lệch → đếm ra). Dòng
  kiểm tra "nhập Kho TP ngoài phiếu sx" = số nhập theo sổ kho (bc.api.sx.production_filter, đúng kho TP) − số theo
  phiếu, theo tháng; phần ngoài phiếu đếm chính xác = phiếu kho của production_filter không nằm trong ds_se của phiếu
  nào (kèm số phiếu kho ngoài phiếu mỗi tháng). Mọi tổng số lượng (ngày, tháng, sổ kho, ngoài phiếu, hai vế đối chiếu)
  giữ theo mã rồi kiểm đơn vị RIÊNG từng ô: lẫn Hộp + Kg → None ở đúng ô đó, kèm đơn vị khi cùng một đơn vị. Mỗi ô thùng
  (tổng tháng chọn, từng ngày, từng tháng) kèm boxes_without_carton_factor / items_without_carton_factor / uom_without —
  thùng chỉ tính mã CÓ quy cách, phần còn lại phải đi kèm, không âm thầm rơi khỏi cột / biểu đồ thùng.
- cho_duyet (K11): phiếu nháp (docstatus 0) — số phiếu, Σ so_dem (phiếu chưa đếm thì Σ so_lap), tuổi phiếu cũ nhất
  (từ ngày tạo), phần sẽ thành nợ BOM khi duyệt (mã chưa có BOM đang dùng: is_active + is_default + docstatus 1 như
  sx get_bom_active), phiếu Tết (nguon = 'Tết', cột có từ D122 — đọc mềm).
- vao_hop (K11): "đã vào hộp chưa nhập kho" — port sx.api.khotp.tran_con_lai, cửa sổ 30 ngày tới hôm nay: Σ so_hop bảng
  vào hộp (ngày SX docstatus < 2, bảng < 2) − Σ so_dem phiếu đã duyệt từ đầu cửa sổ (không chặn trên, như sx) − Σ so_dem
  phiếu nháp Tết; chỉ mã còn > 0. so_hop là số HỘP: mã có đơn vị kho khác Hộp liệt kê riêng, không cộng vào tổng.
- no_bom (K12a): SX No BOM trang_thai = 'Chờ BOM' (KHÔNG nộp được — không bao giờ dùng docstatus): số lượng + thùng,
  value_tam = Σ so_luong × gia_tam ("giá tạm lúc nhập" — sx không định giá lại thành phẩm khi hạch toán bù), phần giá 0,
  tuổi theo ngày nhập (0-7 / 8-30 / > 30 ngày, NGAY_NO_LAU = 7 như sx), mã đã có BOM ("xử lý được ngay").
- nvl_treo (K12b): nguyên liệu còn nằm trên sổ vì chưa trừ = bung BOM một cấp của nợ đang mở (chỉ mã kho, kho nguồn
  SX Settings.kho_btp cho nguyên liệu nhóm BTP*, còn lại kho_nvl — như sx chot._kho_nguon) × giá vốn dự phòng
  kho.rates() (DỪNG ở Item.valuation_rate — không Item Price, W7). Mã nợ chưa có BOM → "chưa ước tính được".
- gia_von_0 (K12c): thành phẩm đang tồn ở kho bán được mà giá vốn ≤ 0 (Bin, actual_qty > 0) + thành phẩm nhập trong tháng
  với đơn giá 0 (điều kiện production_filter, kho đích nới từ đúng kho TP ra mọi kho bán được của công ty, chỉ mã thành
  phẩm). Không cần app sx (tập thành phẩm dự phòng theo cây nhóm hàng).
Site không cài sx: 5 khối đầu {available: False}, gia_von_0 vẫn tính. Không gọi method whitelisted nào của sx (đều
guard theo phiên + trả cờ theo người dùng); không soft-import helper có ghi DB. Không trả người lập / duyệt / xử lý,
ghi chú, lý do, remarks, tên nhân viên vào hộp — chỉ số tổng hợp, mã hàng, tên phiếu, ngày.
"""

from __future__ import annotations

import datetime
import json

import frappe
from frappe.utils import add_days, flt, getdate

from bc.api import kho
from bc.api._common import _guard, carton_factors, drop_hidden, iso, run_cached, safe_block
from bc.api.sx import _wh, production_filter

CHO_BOM = "Chờ BOM"      # SX No BOM.trang_thai đang mở (sx_no_bom.json)
NGUON_TET = "Tết"        # SX Phieu Nhap TP.nguon của phiếu từ màn vào hộp Tết (sx api/tet.py NGUON)
NGAY_NO_LAU = 7          # = sx khotp.NGAY_NO_LAU — nợ quá chừng này ngày sx tô đỏ
SO_NGAY_TRAN = 30        # = sx khotp.SO_NGAY_TRAN — cửa sổ "đã vào hộp, chưa nhập kho"
BOX_UOM = "Hộp"          # so_hop của bảng vào hộp là số hộp
BUCKETS = (("0-7", "0–7 ngày", NGAY_NO_LAU), ("8-30", "8–30 ngày", 30), (">30", "Trên 30 ngày", None))
EPS = kho.EPS
PF_WH = "sed.t_warehouse = %(sx_wh)s"   # điều kiện kho trong production_filter — nới ra kho bán được ở K12c
LIST_MAX = 20


def _has(*doctypes) -> bool:
	return all(frappe.db.table_exists(d) for d in doctypes)


def _q(v) -> float:
	return round(flt(v), 3)


def _m(v) -> float:
	return round(flt(v), 2)


def _ym(d) -> str:
	d = getdate(d)
	return f"{d.year:04d}-{d.month:02d}"


MIN_K, MAX_K = 1 * 12, 9999 * 12 + 11   # chỉ số tháng (năm × 12 + tháng − 1) của 01/0001 và 12/9999


def _mk(k: int) -> datetime.date:
	"""Ngày 1 của tháng có chỉ số k, kẹp trong 01/0001 → 12/9999."""
	k = min(max(k, MIN_K), MAX_K)
	return datetime.date(k // 12, k % 12 + 1, 1)


def _months_back(f, n: int) -> list:
	"""n + 1 ngày đầu tháng từ (tháng của f − n) tới tháng của f, cũ trước — số học thuần trên (năm, tháng), KHÔNG qua
	add_months / getdate: tháng gần năm 1 làm add_months(f, −11) ném ValueError 'year 0' → HTTP 500 (SEC-1). Kỳ chọn
	month_period đã kẹp từ 2000 / 10 năm; đây là chốt thứ hai — dãy tháng chỉ ngắn lại ở biên, không bao giờ ném lỗi."""
	k0 = f.year * 12 + f.month - 1
	return [_mk(k) for k in range(max(k0 - n, MIN_K), k0 + 1)]


def _se_names(ds_se) -> list:
	"""ds_se của phiếu (JSON [{dt, name}]) → tên Stock Entry; hỏng / trống → []."""
	try:
		ds = json.loads(ds_se or "[]")
	except (TypeError, ValueError):
		return []
	if not isinstance(ds, list):
		return []
	return [x.get("name") for x in ds if isinstance(x, dict) and x.get("dt") == "Stock Entry" and x.get("name")]


def _bom_items(items) -> set:
	"""Mã có BOM đang dùng — đúng điều kiện sx get_bom_active (is_active, is_default, đã nộp)."""
	items = kho.in_tuple(items)
	if items == ("\x00",):
		return set()
	return set(frappe.db.sql_list(
		"""SELECT DISTINCT item FROM `tabBOM`
		WHERE item IN %(items)s AND is_active = 1 AND is_default = 1 AND docstatus = 1""", {"items": items}))


def _uom(info: dict, codes) -> str | None:
	return kho.one_uom([{"stock_uom": (info.get(c) or {}).get("stock_uom")} for c in codes]) if codes else None


def _cartons(qty_by_item: dict, factors: dict, info: dict | None = None) -> dict:
	"""Thùng + phần chưa khai quy cách thùng. Có `info`: phần chưa khai kèm đơn vị của nó (uom_without); phần đó lẫn
	nhiều đơn vị (Hộp + Kg) → boxes_without_carton_factor = None (không cộng khác đơn vị)."""
	q = {k: v for k, v in qty_by_item.items() if abs(flt(v)) > EPS}
	out = kho.carton_total(q, factors)
	if info is not None:
		no_f = [c for c in q if not factors.get(c)]
		out["uom_without"] = _uom(info, no_f)
		if no_f and not out["uom_without"]:
			out["boxes_without_carton_factor"] = None
	return out


def _sum1(info: dict, qty_by_item: dict) -> tuple:
	"""(Σ số lượng, đơn vị) khi mọi mã CÙNG đơn vị kho; lẫn đơn vị → (None, None); rỗng → (0, None)."""
	codes = [c for c, q in qty_by_item.items() if abs(flt(q)) > EPS]
	if not codes:
		return 0.0, None
	u = _uom(info, codes)
	return (_q(sum(flt(qty_by_item[c]) for c in codes)), u) if u else (None, None)


def _by_uom(info: dict, qty_by_item: dict) -> list:
	out: dict = {}
	for c, q in qty_by_item.items():
		u = (info.get(c) or {}).get("stock_uom") or ""
		out[u] = out.get(u, 0.0) + flt(q)
	return [{"uom": u or None, "qty": _q(q)} for u, q in sorted(out.items(), key=lambda x: -x[1])]


def _item_row(info: dict, code: str, **extra) -> dict:
	it = info.get(code) or {}
	return {"item_code": code, "short_name": it.get("short_name") or code, "uom": it.get("stock_uom"), **extra}


def _add(d: dict, k, v):
	d[k] = d.get(k, 0.0) + flt(v)


# ─── K11 · Thành phẩm nhập kho theo phiếu sx ────────────────────────────────
def _nhap(p: dict) -> dict:
	if not _has("SX Phieu Nhap TP", "SX Phieu Nhap TP Item"):
		return {"available": False}
	f, t, f12 = p["f"], p["t"], p["f12"]
	# Phiếu ĐÃ DUYỆT (docstatus 1) trong 12 tháng — lọc trạng thái MỘT chỗ; dòng phiếu lấy theo đúng danh sách này.
	slips = {r.name: r for r in frappe.db.sql(
		"""SELECT p.name, p.ngay, p.ds_se FROM `tabSX Phieu Nhap TP` p
		WHERE p.docstatus = 1 AND p.ngay BETWEEN %(f12)s AND %(t)s""", {"f12": f12, "t": t}, as_dict=True)}
	lines = frappe.db.sql(
		"""SELECT i.parent, i.item, SUM(IFNULL(i.so_dem, 0)) AS qty
		FROM `tabSX Phieu Nhap TP Item` i
		WHERE i.parent IN %(slips)s AND i.parenttype = 'SX Phieu Nhap TP' AND i.parentfield = 'dong'
		GROUP BY i.parent, i.item""", {"slips": kho.in_tuple(slips)}, as_dict=True)
	# Phiếu → phiếu kho của nó (ds_se). Một phiếu kho thuộc đúng một phiếu.
	se_slip: dict = {}
	for s in slips.values():
		for n in _se_names(s.ds_se):
			se_slip.setdefault(n, s.name)
	vals = frappe.db.sql(
		"""SELECT sle.voucher_no AS se, sle.item_code, se.purpose,
			SUM(sle.actual_qty) AS qty, SUM(sle.stock_value_difference) AS value
		FROM `tabStock Ledger Entry` sle
		JOIN `tabStock Entry` se ON se.name = sle.voucher_no
		JOIN `tabStock Entry Detail` sed ON sed.name = sle.voucher_detail_no AND sed.parent = sle.voucher_no
		WHERE sle.voucher_type = 'Stock Entry' AND sle.voucher_no IN %(names)s AND sle.is_cancelled = 0
			AND sle.actual_qty > 0 AND (se.purpose = 'Material Receipt' OR sed.is_finished_item = 1)
		GROUP BY sle.voucher_no, sle.item_code, se.purpose""", {"names": kho.in_tuple(se_slip)}, as_dict=True)
	# Sổ kho (production_filter, đúng kho TP): theo phiếu kho để tách phần ngoài phiếu sx.
	ledger = frappe.db.sql(
		f"""SELECT se.name AS se, se.posting_date AS d, sed.item_code, SUM(sed.transfer_qty) AS qty
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE {production_filter()} AND se.posting_date BETWEEN %(f12)s AND %(t)s
		GROUP BY se.name, se.posting_date, sed.item_code""", {"f12": f12, "t": t, "sx_wh": _wh()}, as_dict=True)

	codes = {r.item for r in lines} | {r.item_code for r in vals} | {r.item_code for r in ledger}
	info = kho.item_info(codes)
	factors = carton_factors(codes)
	# Mọi số lượng giữ theo MÃ ({mã: số}) tới lúc trả: mỗi ngày / tháng / vế đối chiếu tự kiểm đơn vị bằng _sum1 —
	# không bao giờ cộng Hộp với Kg (một tháng lẫn đơn vị chỉ làm tháng đó thành None, các tháng khác vẫn có số).
	months = {m: {"qty": {}, "value": 0.0, "slips": set(), "so_kho": {}, "ngoai": {}, "ngoai_se": set()}
		for m in p["months"]}
	# Cộng ngày bằng chỉ số (không bước qua t + 1 ngày: 31/12/9999 + 1 tràn ngày).
	days = {f + datetime.timedelta(days=i): {"qty": {}, "value": 0.0, "slips": set()} for i in range((t - f).days + 1)}
	sel_items: dict = {}       # mã → {qty, value} tháng chọn
	slip_qty: dict = {}        # (phiếu, mã) tháng chọn → Σ so_dem
	se_qty: dict = {}          # (phiếu, mã) tháng chọn → Σ số lượng dòng sổ thành phẩm
	kind = {"bom": {"qty": {}, "value": 0.0}, "tam": {"qty": {}, "value": 0.0}}
	for r in lines:
		s = slips[r.parent]
		ngay = getdate(s.ngay)
		mo = months.get(_ym(ngay))
		if mo is not None:
			_add(mo["qty"], r.item, r.qty)
			mo["slips"].add(s.name)
		if f <= ngay <= t:
			_add(days[ngay]["qty"], r.item, r.qty)
			days[ngay]["slips"].add(s.name)
			sel_items.setdefault(r.item, {"qty": 0.0, "value": 0.0})["qty"] += flt(r.qty)
			_add(slip_qty, (s.name, r.item), r.qty)
	for r in vals:
		s = slips.get(se_slip.get(r.se))
		if not s:
			continue
		ngay = getdate(s.ngay)
		mo = months.get(_ym(ngay))
		if mo is not None:
			mo["value"] += flt(r.value)
		if f <= ngay <= t:
			days[ngay]["value"] += flt(r.value)
			sel_items.setdefault(r.item_code, {"qty": 0.0, "value": 0.0})["value"] += flt(r.value)
			_add(se_qty, (s.name, r.item_code), r.qty)
			k = kind["tam" if r.purpose == "Material Receipt" else "bom"]
			_add(k["qty"], r.item_code, r.qty)
			k["value"] += flt(r.value)
	ngoai_items: dict = {}
	ngoai_se = set()
	for r in ledger:
		mo = months.get(_ym(r.d))
		outside = r.se not in se_slip
		if mo is not None:
			_add(mo["so_kho"], r.item_code, r.qty)
			if outside:
				_add(mo["ngoai"], r.item_code, r.qty)
				mo["ngoai_se"].add(r.se)
		if outside and f <= getdate(r.d) <= t:
			_add(ngoai_items, r.item_code, r.qty)
			ngoai_se.add(r.se)

	sel_qty = {c: v["qty"] for c, v in sel_items.items() if abs(v["qty"]) > EPS}
	total_value = sum(v["value"] for v in sel_items.values())
	by_day = []
	for dd, x in days.items():
		q, u = _sum1(info, x["qty"])
		by_day.append({"date": iso(dd), "qty": q, "uom": u, **_cartons(x["qty"], factors, info),
			"value": _m(x["value"]), "slips": len(x["slips"])})
	by_month = []
	for m in p["months"]:
		x = months[m]
		q, u = _sum1(info, x["qty"])
		sk, sku = _sum1(info, x["so_kho"])
		ng, ngu = _sum1(info, x["ngoai"])
		# Chênh sổ − phiếu chỉ khi hai vế cùng một đơn vị (vế trống = 0, không đơn vị).
		chenh = None if q is None or sk is None or (u and sku and u != sku) else _q(sk - q)
		by_month.append({"month": m, "qty": q, "uom": u, **_cartons(x["qty"], factors, info),
			"value": _m(x["value"]), "slips": len(x["slips"]), "so_kho_qty": sk, "so_kho_uom": sku, "chenh": chenh,
			"ngoai_phieu": ng, "ngoai_uom": ngu, "ngoai_entries": len(x["ngoai_se"])})
	top = drop_hidden([_item_row(info, c, qty=_q(v["qty"]), cartons=_cartons({c: v["qty"]}, factors)["cartons"],
		value=_m(v["value"])) for c, v in sel_items.items() if abs(v["qty"]) > EPS or abs(v["value"]) >= kho.VALUE_EPS])
	top.sort(key=lambda r: (-r["qty"], -r["value"], r["item_code"]))
	# Đối chiếu từng (phiếu, mã): phiếu lệch = có mã mà Σ so_dem ≠ Σ dòng sổ. Tổng hai vế / số lệch cộng theo mã, kiểm
	# đơn vị riêng từng vế (lẫn Hộp + Kg → None; số phiếu lệch vẫn đếm).
	slip_by, se_by, diff = {}, {}, {}
	lech = set()
	for key in set(slip_qty) | set(se_qty):
		_add(slip_by, key[1], slip_qty.get(key))
		_add(se_by, key[1], se_qty.get(key))
		dv = flt(slip_qty.get(key)) - flt(se_qty.get(key))
		if abs(dv) > EPS:
			lech.add(key[0])
			_add(diff, key[1], dv)
	sq, su = _sum1(info, slip_by)
	eq, eu = _sum1(info, se_by)
	lq, lu = _sum1(info, diff)
	ngoai = drop_hidden([_item_row(info, c, qty=_q(q)) for c, q in ngoai_items.items() if abs(q) > EPS])
	ngoai.sort(key=lambda r: (-r["qty"], r["item_code"]))
	tq, uom = _sum1(info, sel_qty)
	nq, nu = _sum1(info, ngoai_items)
	by_kind = {}
	for k, v in kind.items():
		kq, ku = _sum1(info, v["qty"])
		by_kind[k] = {"qty": kq, "uom": ku, "value": _m(v["value"])}
	return {
		"available": True,
		"total": {
			"qty": tq, "uom": uom, "by_uom": _by_uom(info, sel_qty), **_cartons(sel_qty, factors, info),
			"value": _m(total_value), "slips": len({n for n, _c in slip_qty}), "items": len(sel_qty),
			"days": sum(1 for x in days.values() if x["slips"]),
			"by_kind": by_kind,
		},
		"by_day": by_day,
		"by_month": by_month,
		"top_items": top[:LIST_MAX],
		"doi_chieu": {"slip_qty": sq, "slip_uom": su, "se_qty": eq, "se_uom": eu, "lech": lq, "lech_uom": lu,
			"slips_lech": len(lech)},
		"ngoai_phieu": {"qty": nq, "uom": nu, "entries": len(ngoai_se), "items": ngoai[:LIST_MAX]},
	}


# ─── K11 · Hàng đợi: phiếu chờ duyệt ────────────────────────────────────────
def _cho_duyet(p: dict) -> dict:
	if not _has("SX Phieu Nhap TP", "SX Phieu Nhap TP Item"):
		return {"available": False}
	nguon = "IFNULL(p.nguon, '')" if frappe.db.has_column("SX Phieu Nhap TP", "nguon") else "''"
	rows = frappe.db.sql(
		f"""SELECT p.name, p.ngay, p.creation, {nguon} AS nguon, i.item,
			SUM(IFNULL(i.so_dem, 0)) AS dem, SUM(IFNULL(i.so_lap, 0)) AS lap, COUNT(i.name) AS n_rows,
			MAX(CASE WHEN b.item IS NULL THEN 0 ELSE 1 END) AS co_bom
		FROM `tabSX Phieu Nhap TP` p
		LEFT JOIN `tabSX Phieu Nhap TP Item` i
			ON i.parent = p.name AND i.parenttype = 'SX Phieu Nhap TP' AND i.parentfield = 'dong'
		LEFT JOIN (SELECT DISTINCT item FROM `tabBOM` WHERE is_active = 1 AND is_default = 1 AND docstatus = 1) b
			ON b.item = i.item
		WHERE p.docstatus = 0
		GROUP BY p.name, p.ngay, p.creation, nguon, i.item""", as_dict=True)
	today = p["today"]
	slips: dict = {}
	for r in rows:
		s = slips.setdefault(r.name, {"r": r, "dem": {}, "lap": {}, "bom": set(), "n": 0})
		if r.item:
			_add(s["dem"], r.item, r.dem)
			_add(s["lap"], r.item, r.lap)
			s["n"] += int(r.n_rows or 0)
			if r.co_bom:
				s["bom"].add(r.item)
	info = kho.item_info({c for s in slips.values() for c in s["lap"]})
	out, all_qty = [], {}
	for name, s in slips.items():
		r = s["r"]
		dem = sum(s["dem"].values()) > EPS   # thủ kho đã đếm → số đếm; chưa đếm → số lập phiếu
		qty = s["dem"] if dem else s["lap"]
		for c, v in qty.items():
			_add(all_qty, c, v)
		created = getdate(r.creation) if r.creation else getdate(r.ngay)
		tq, uom = _sum1(info, qty)
		nb, _u = _sum1(info, {c: v for c, v in qty.items() if c not in s["bom"]})
		out.append({"name": name, "ngay": iso(r.ngay), "tao": iso(created), "age_days": (today - created).days,
			"n_rows": s["n"], "qty": tq, "uom": uom, "da_dem": dem, "no_bom_qty": nb if tq is not None else None,
			"tet": r.nguon == NGUON_TET})
	out.sort(key=lambda x: (-x["age_days"], x["name"]))
	oldest = out[0] if out else None
	tq, uom = _sum1(info, all_qty)
	return {
		"available": True, "count": len(out), "count_tet": sum(1 for x in out if x["tet"]), "qty": tq, "uom": uom,
		"no_bom_qty": _q(sum(flt(x["no_bom_qty"]) for x in out)) if tq is not None else None,
		"oldest_age_days": oldest["age_days"] if oldest else None, "oldest_date": oldest["tao"] if oldest else None,
		"chua_dem": sum(1 for x in out if not x["da_dem"]), "rows": out[:LIST_MAX],
	}


# ─── K11 · Đã vào hộp, chưa nhập kho (port khotp.tran_con_lai) ───────────────
def _vao_hop(p: dict) -> dict:
	if not _has("SX Phieu Nhap TP", "SX Phieu Nhap TP Item", "SX Bang Vao Hop", "SX Bang Vao Hop Item",
			"SX Ngay San Xuat"):
		return {"available": False}
	den = p["today"]
	tu = getdate(add_days(den, -SO_NGAY_TRAN + 1))
	q = {"tu": tu, "den": den, "tet": NGUON_TET}
	boxed = {r.item: flt(r.boxed) for r in frappe.db.sql(
		"""SELECT vi.san_pham AS item, SUM(vi.so_hop) AS boxed
		FROM `tabSX Bang Vao Hop Item` vi
		JOIN `tabSX Bang Vao Hop` b ON b.name = vi.parent AND vi.parenttype = 'SX Bang Vao Hop'
		JOIN `tabSX Ngay San Xuat` n ON n.name = b.ngay_sx
		WHERE n.ngay BETWEEN %(tu)s AND %(den)s AND n.docstatus < 2 AND b.docstatus < 2
			AND IFNULL(vi.san_pham, '') != ''
		GROUP BY vi.san_pham""", q, as_dict=True)}
	# Đã nhận: phiếu đã duyệt từ đầu cửa sổ, KHÔNG chặn trên (như sx _da_nhan_theo_ma).
	nhan = {r.item: flt(r.qty) for r in frappe.db.sql(
		"""SELECT i.item, SUM(IFNULL(i.so_dem, 0)) AS qty
		FROM `tabSX Phieu Nhap TP` p
		JOIN `tabSX Phieu Nhap TP Item` i ON i.parent = p.name AND i.parenttype = 'SX Phieu Nhap TP'
		WHERE p.docstatus = 1 AND p.ngay >= %(tu)s
		GROUP BY i.item""", q, as_dict=True)}
	if frappe.db.has_column("SX Phieu Nhap TP", "nguon"):  # D122: phiếu nháp Tết đã giữ phần hàng đó
		for r in frappe.db.sql(
				"""SELECT i.item, SUM(IFNULL(i.so_dem, 0)) AS qty
				FROM `tabSX Phieu Nhap TP` p
				JOIN `tabSX Phieu Nhap TP Item` i ON i.parent = p.name AND i.parenttype = 'SX Phieu Nhap TP'
				WHERE p.docstatus = 0 AND p.nguon = %(tet)s AND p.ngay >= %(tu)s
				GROUP BY i.item""", q, as_dict=True):
			_add(nhan, r.item, r.qty)
	con = {c: b - flt(nhan.get(c)) for c, b in boxed.items()}
	con = {c: v for c, v in con.items() if v > EPS}
	info = kho.item_info(con)
	factors = carton_factors(con)
	box = {c: v for c, v in con.items() if (info.get(c) or {}).get("stock_uom") == BOX_UOM}
	other = {c: v for c, v in con.items() if c not in box}
	rows = drop_hidden([_item_row(info, c, qty=_q(v), cartons=_cartons({c: v}, factors)["cartons"] if c in box else None,
		khac_dvt=c not in box) for c, v in con.items()])
	rows.sort(key=lambda r: (r["khac_dvt"], -r["qty"], r["item_code"]))
	return {"available": True, "from": iso(tu), "to": iso(den), "so_ngay": SO_NGAY_TRAN,
		"qty": _q(sum(box.values())), "uom": BOX_UOM, **_cartons(box, factors, info), "items": len(box),
		"items_khac_dvt": len(other),
		"rows": rows[:LIST_MAX]}


# ─── K12a · Nợ BOM đang mở ──────────────────────────────────────────────────
def _open_no(p: dict) -> list:
	return frappe.db.sql(
		"""SELECT nb.item, nb.so_luong, nb.gia_tam, nb.ngay FROM `tabSX No BOM` nb WHERE nb.trang_thai = %(cho_bom)s""",
		{"cho_bom": CHO_BOM}, as_dict=True)


def _bucket(age: int) -> str:
	return next(k for k, _l, lim in BUCKETS if lim is None or age <= lim)


def _no_bom(p: dict) -> dict:
	if not _has("SX No BOM"):
		return {"available": False}
	today = p["today"]
	rows = _open_no(p)
	items: dict = {}
	buckets = {k: {"key": k, "label": lbl, "rows": 0, "qty": 0.0} for k, lbl, _ in BUCKETS}
	for r in rows:
		ngay = getdate(r.ngay) if r.ngay else today
		age = max((today - ngay).days, 0)
		x = items.setdefault(r.item, {"qty": 0.0, "value": 0.0, "gia_0": 0.0, "rows": 0, "oldest": ngay})
		x["qty"] += flt(r.so_luong)
		x["value"] += flt(r.so_luong) * flt(r.gia_tam)
		x["rows"] += 1
		x["oldest"] = min(x["oldest"], ngay)
		if flt(r.gia_tam) <= 0:
			x["gia_0"] += flt(r.so_luong)
		b = buckets[_bucket(age)]
		b["rows"] += 1
		b["qty"] += flt(r.so_luong)
	co_bom = _bom_items(items)
	info = kho.item_info(items)
	factors = carton_factors(items)
	qty = {c: x["qty"] for c, x in items.items()}
	lst = []
	for c, x in items.items():
		age = max((today - x["oldest"]).days, 0)
		lst.append(_item_row(info, c, rows=x["rows"], qty=_q(x["qty"]), cartons=_cartons({c: x["qty"]}, factors)["cartons"],
			value_tam=_m(x["value"]), qty_gia_0=_q(x["gia_0"]), oldest=iso(x["oldest"]), age_days=age,
			lau=age > NGAY_NO_LAU, co_bom=c in co_bom))
	lst = drop_hidden(lst)
	lst.sort(key=lambda r: (not r["co_bom"], -r["age_days"], r["item_code"]))  # như sx: xử lý được ngay lên đầu
	oldest = min((x["oldest"] for x in items.values()), default=None)
	tq, uom = _sum1(info, qty)
	one = tq is not None   # lẫn đơn vị → các tổng số lượng None (giá trị, số dòng vẫn có)
	return {
		"available": True, "items": len(items), "rows": len(rows), "qty": tq, "uom": uom, **_cartons(qty, factors, info),
		"value_tam": _m(sum(x["value"] for x in items.values())),
		"qty_gia_0": _q(sum(x["gia_0"] for x in items.values())) if one else None,
		"rows_gia_0": sum(1 for r in rows if flt(r.gia_tam) <= 0),
		"oldest": iso(oldest), "age_days": max((today - oldest).days, 0) if oldest else None,
		"ngay_no_lau": NGAY_NO_LAU, "lau": sum(1 for r in lst if r["lau"]),
		"buckets": [{**b, "qty": _q(b["qty"]) if one else None} for b in buckets.values()],
		"xu_ly_ngay": {"items": len([c for c in items if c in co_bom]),
			"qty": _sum1(info, {c: q for c, q in qty.items() if c in co_bom})[0]},
		"list": lst[:LIST_MAX],
	}


# ─── K12b · Nguyên liệu còn treo trên sổ (ước tính) ─────────────────────────
def _nvl_treo(p: dict) -> dict:
	if not _has("SX No BOM"):
		return {"available": False}
	need = frappe.db.sql(
		"""SELECT nb.item AS fg, bi.item_code AS rm,
			SUM(nb.so_luong * bi.stock_qty / IF(IFNULL(bom.quantity, 0) = 0, 1, bom.quantity)) AS qty
		FROM `tabSX No BOM` nb
		JOIN (SELECT item, MAX(name) AS bom FROM `tabBOM`
			WHERE is_active = 1 AND is_default = 1 AND docstatus = 1 GROUP BY item) d ON d.item = nb.item
		JOIN `tabBOM` bom ON bom.name = d.bom
		JOIN `tabBOM Item` bi ON bi.parent = bom.name AND bi.parenttype = 'BOM'
		JOIN `tabItem` ri ON ri.name = bi.item_code AND ri.is_stock_item = 1
		WHERE nb.trang_thai = %(cho_bom)s
		GROUP BY nb.item, bi.item_code""", {"cho_bom": CHO_BOM}, as_dict=True)
	rms = {r.rm for r in need}
	nhom = {}
	if rms and frappe.db.has_column("Item", "custom_sx_nhom"):
		nhom = dict(frappe.db.sql("SELECT name, custom_sx_nhom FROM `tabItem` WHERE name IN %(c)s",
			{"c": kho.in_tuple(rms)}))
	kho_btp, kho_nvl = kho.sx_setting("kho_btp"), kho.sx_setting("kho_nvl")
	qty: dict = {}
	for r in need:  # như sx chot._kho_nguon: nguyên liệu nhóm BTP* rút Kho BTP, còn lại Kho NVL
		wh = kho_btp if str(nhom.get(r.rm) or "").startswith("BTP") else kho_nvl
		_add(qty, (r.rm, wh), r.qty)
	rates = kho.rates(list(qty))
	info = kho.item_info(rms)
	whs = kho.warehouse_map()
	rows = []
	for (rm, wh), q in qty.items():
		rate, src = rates.get((rm, wh), (0.0, None))
		rows.append(_item_row(info, rm, warehouse=wh, warehouse_label=(whs.get(wh) or {}).get("label") or wh,
			qty=_q(q), rate=_m(rate) if src else None, rate_source=src, value=_m(q * rate) if src else None))
	no_rate = [r for r in rows if r["rate_source"] is None]
	value = sum(flt(r["value"]) for r in rows if r["rate_source"])
	lst = drop_hidden(rows)
	lst.sort(key=lambda r: (r["rate_source"] is None, -flt(r["value"]), r["item_code"]))
	# Mã nợ chưa có BOM đang dùng → không bung được.
	open_rows = _open_no(p)
	co_bom = _bom_items({r.item for r in open_rows})
	chua: dict = {}
	for r in open_rows:
		if r.item not in co_bom:
			_add(chua, r.item, r.so_luong)
	cq, cu = _sum1(kho.item_info(chua), chua)
	return {
		"available": True, "value": _m(value), "n_rm": len(rows),
		"chua_co_gia": {"n": len(no_rate)},
		"chua_uoc_tinh": {"items": len(chua), "qty": cq, "uom": cu},
		"fg_items": len({r.fg for r in need}),
		"list": lst[:LIST_MAX],
	}


# ─── K12c · Thành phẩm chưa có giá vốn ──────────────────────────────────────
def _gia_von_0(p: dict) -> dict:
	co = kho.company()
	whs = kho.warehouse_map(co)
	tp, tp_source = kho.tp_items()
	bins = [b for b in kho.bin_rows(co, whs)
		if b.item_code in tp and b.sellable and b.qty > EPS and b.rate <= 0]
	codes = {b.item_code for b in bins}
	# Nhập trong kỳ với đơn giá 0: điều kiện production_filter, kho đích nới ra mọi kho bán được của công ty.
	pf = production_filter()
	pf = pf.replace(PF_WH, "sed.t_warehouse IN %(sell)s") if PF_WH in pf else pf
	recs = [r for r in frappe.db.sql(
		f"""SELECT se.name AS se, sed.item_code, SUM(sed.transfer_qty) AS qty
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE {pf} AND se.posting_date BETWEEN %(f)s AND %(t)s AND IFNULL(sed.basic_rate, 0) = 0
		GROUP BY se.name, sed.item_code""",
		{"f": p["f"], "t": p["t"], "sx_wh": _wh(), "sell": kho.sellable(whs)}, as_dict=True) if r.item_code in tp]
	codes |= {r.item_code for r in recs}
	info = kho.item_info(codes)
	factors = carton_factors(codes)
	ton_qty: dict = {}
	for b in bins:
		_add(ton_qty, b.item_code, b.qty)
	ton_list = drop_hidden([_item_row(info, b.item_code, warehouse=b.warehouse,
		warehouse_label=(whs.get(b.warehouse) or {}).get("label") or b.warehouse, role_label=kho.ROLE_LABELS.get(b.role),
		qty=_q(b.qty), cartons=_cartons({b.item_code: b.qty}, factors)["cartons"]) for b in bins])
	ton_list.sort(key=lambda r: (-r["qty"], r["item_code"], r["warehouse"]))
	rec_qty: dict = {}
	for r in recs:
		_add(rec_qty, r.item_code, r.qty)
	rec_list = drop_hidden([_item_row(info, c, qty=_q(q), cartons=_cartons({c: q}, factors)["cartons"])
		for c, q in rec_qty.items() if abs(q) > EPS])
	rec_list.sort(key=lambda r: (-r["qty"], r["item_code"]))
	tq, tu = _sum1(info, ton_qty)
	rq, ru = _sum1(info, rec_qty)
	return {
		"available": True, "tp_source": tp_source,
		"ton": {"rows": len(bins), "items": len(ton_qty), "qty": tq, "uom": tu, **_cartons(ton_qty, factors, info),
			"list": ton_list[:LIST_MAX]},
		"nhap_ky": {"qty": rq, "uom": ru, "entries": len({r.se for r in recs}),
			"items": len([c for c, q in rec_qty.items() if abs(q) > EPS]), "list": rec_list[:LIST_MAX]},
	}


def _off(_p):
	return {"available": False}


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	"""Nhập thành phẩm & giá vốn trong tháng `thang` ('YYYY-MM', mặc định tháng này; cắt ở hôm nay) — xem docstring module.

	{available, meta: {thang, from, to, as_of, prev, months, sx, kho_tp}, nhap, cho_duyet, vao_hop, no_bom, nvl_treo,
	 gia_von_0}
	"""
	_guard("nhap-tp")
	f, t, label = kho.month_period(thang)
	today = kho.today()

	def build():
		m12 = _months_back(f, 11)
		f12, months = m12[0], [_ym(x) for x in m12]
		prev = _months_back(f, 1)[0]
		p = {"f": f, "t": t, "f12": f12, "months": months, "today": today}
		sx = kho.sx_on()
		sx_block = (lambda name, fn: safe_block(f"kho_nhap.{name}", fn, p)) if sx else (lambda name, fn: _off(p))
		return {
			"available": True,
			"meta": {"thang": label, "from": iso(f), "to": iso(t), "as_of": iso(today), "prev": _ym(prev),
				"months": months, "sx": sx, "kho_tp": _wh()},
			"nhap": sx_block("nhap", _nhap),
			"cho_duyet": sx_block("cho_duyet", _cho_duyet),
			"vao_hop": sx_block("vao_hop", _vao_hop),
			"no_bom": sx_block("no_bom", _no_bom),
			"nvl_treo": sx_block("nvl_treo", _nvl_treo),
			"gia_von_0": safe_block("kho_nhap.gia_von_0", _gia_von_0, p),
		}

	return run_cached("kho_nhap.get_overview", {"t": label, "d": iso(today)}, build, refresh)
