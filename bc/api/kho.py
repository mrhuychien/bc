# -*- coding: utf-8 -*-
"""bc.api.kho — nền dùng chung cho nhóm màn Kho (kho_ton, kho_han, kho_kk, kho_nhap). KHÔNG có method whitelisted.

Quy ước số liệu (đặc tả Kho, bản chốt):
- Công ty = bc.api.cn.company(); kho thuộc công ty theo `tabWarehouse.company` (không dùng Bin.company — fetch_from,
  Bin cũ có thể trống).
- "Bây giờ" = Bin (gồm cả phiếu ghi ngày tương lai, đúng như ERPNext). Giá trị tại một ngày / dòng chảy trong kỳ
  = Σ SLE.stock_value_difference (is_cancelled = 0). Không bao giờ SUM(actual_qty) làm số tồn (phiếu kiểm kê
  không lô ghi actual_qty = 0); không dùng Batch.batch_qty; không dùng Stock Entry Detail.amount (không dấu).
- Đơn vị = Item.stock_uom. Thùng qua carton_factors; mọi tổng thùng kèm số hộp CHƯA khai quy cách thùng (to_cartons
  trả 0 khi thiếu hệ số → cộng thẳng là mất hàng). Không cộng Hộp với Kg.
- Vai trò kho (khớp đầu tiên): tra_ve (SX Settings.kho_hang_tra_ve hoặc is_rejected_warehouse), cach_ly, di_duong
  (warehouse_type Transit), tp (bc.api.sx._wh() ∪ SX Settings.kho_tp), cua_hang (kho của POS Profile đang dùng),
  xuong / btp / nvl (SX Settings), khac. "Bán được" = mọi kho lá trừ tra_ve, cach_ly. Kho nhóm cấu hình được bung
  xuống kho lá theo lft/rgt. Kho ngừng dùng còn giá trị vẫn tính.
- Tập thành phẩm: sx.utils.items_tp (đọc mềm, gồm mã ngừng dùng) → dự phòng: mọi mã trong cây nhóm Tết ∪ truyền thống.
- Nhóm hàng theo CÂY (lft/rgt): nhóm con của "Hàng Tết" vẫn là Tết. Các màn Kinh doanh so đúng tên nhóm — hai cách chỉ
  lệch khi nhóm Tết / truyền thống có nhóm con (health.group_has_children).
- Giá vốn dự phòng (khi Bin ≤ 0: tồn âm, mã chưa có giá): Bin(mã, kho) > 0 → Bin khác của mã > 0 → dòng sổ kho gần
  nhất > 0 → Item.valuation_rate > 0 → không có ("chưa có giá vốn"). KHÔNG dùng Item Price (giá mua, không phải giá vốn).
- Đọc mềm app sx (installed_apps + DocType + has_column). Chỉ gọi helper THUẦN của sx (items_tp); KHÔNG import
  lo_cu._dong_du / sx_kiem_ke.ma_lo_ton_cu / utils.prefix_lo (có ghi DB) hay mfg.gia_von_hien (dự phòng cuối là giá mua).
- Mốc ngày truyền từ Python (không CURDATE() trong SQL); không ký tự % trong SQL (dùng LOCATE).
"""

from __future__ import annotations

import calendar
import datetime
import re

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from bc.api._common import carton_factors, setting_int, short_name, tet_group, to_cartons, traditional_group

EPS = 0.000001          # ngưỡng số lượng (Bin / SLE); lô làm tròn 3 chữ số như sx
VALUE_EPS = 0.5         # ngưỡng giá trị (VND)
ROLE_LABELS = {
	"tp": "Kho thành phẩm", "cua_hang": "Cửa hàng", "di_duong": "Hàng đi đường", "xuong": "Kho xưởng",
	"btp": "Kho bán thành phẩm", "nvl": "Kho nguyên vật liệu", "khac": "Kho khác",
	"tra_ve": "Hàng trả về", "cach_ly": "Hàng cách ly",
}
ROLE_ORDER = ("tp", "cua_hang", "di_duong", "xuong", "btp", "nvl", "khac", "tra_ve", "cach_ly")
UNSELLABLE = ("tra_ve", "cach_ly")
# (vai trò, field SX Settings) theo thứ tự ưu tiên — tp chen giữa (sau di_duong), xem roles().
_SX_ROLE_FIELDS = {"tra_ve": "kho_hang_tra_ve", "cach_ly": "kho_cach_ly", "xuong": "kho_xuong", "btp": "kho_btp",
	"nvl": "kho_nvl"}
TRANSIT_TYPE = "Transit"
GROUP_KEYS = ("tet", "traditional", "other")

# Tiền tố remarks phiếu kho do sx tự sinh (khớp đúng chuỗi trong sx — đổi bên sx thì đổi ở đây).
P_NHAP_TAM = "Nhập tạm — "              # sx_phieu_nhap_tp.py: nhập TP chưa có BOM (dấu gạch U+2014)
P_BU_BOM = "Hạch toán bù nợ BOM"         # sx api/khotp.py → mfg.py: xuất NVL bù nợ BOM (tiêu hao thật, không phải hao hụt)

DEFAULTS = {"kho_doi_days": 90, "kho_slow_days": 90, "kho_dead_days": 180, "kho_can_date_ngay": 60}
_THANG = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ─── Mốc, cài đặt ────────────────────────────────────────────────────────────
def today() -> datetime.date:
	return getdate(nowdate())


def kho_int(field: str) -> int:
	"""BC Settings.kho_* (Int) — trống / ≤ 0 / site chưa migrate field → mặc định."""
	v = setting_int(field, DEFAULTS[field])
	return v if v > 0 else DEFAULTS[field]


def settings() -> dict:
	return {k: kho_int(k) for k in DEFAULTS}


def company() -> str:
	from bc.api.cn import company as _company  # một nguồn với Công nợ (Ketoan Portal Settings → Global Defaults)
	return _company()


def month_period(thang=None) -> tuple:
	"""(từ, đến, 'YYYY-MM'): tháng chọn (mặc định tháng này; tháng tương lai → tháng này), cắt ở hôm nay."""
	t0 = today()
	t = str(thang or "")[:7]
	if not _THANG.match(t) or getdate(f"{t}-01") > t0:
		t = f"{t0.year:04d}-{t0.month:02d}"
	y, m = int(t[:4]), int(t[5:])
	f = datetime.date(y, m, 1)
	e = datetime.date(y, m, calendar.monthrange(y, m)[1])
	return f, min(e, t0), t


# ─── App sx (đọc mềm) ────────────────────────────────────────────────────────
def sx_on() -> bool:
	return "sx" in frappe.get_installed_apps() and bool(frappe.db.exists("DocType", "SX Settings"))


def sx_setting(field: str):
	"""SX Settings.<field> hoặc None (site không cài sx / sx cũ chưa có field)."""
	if not frappe.db.exists("DocType", "SX Settings"):
		return None
	try:
		return frappe.db.get_single_value("SX Settings", field) or None
	except Exception:  # field chưa có trong meta → frappe.throw đã ghi message_log
		frappe.clear_last_message()
		return None


def has_kiem_ke_col() -> bool:
	return bool(frappe.db.has_column("Stock Entry", "custom_kiem_ke"))


def adjust_params() -> dict:
	"""Tham số tiền tố phiếu điều chỉnh của sx: %(a1)s %(a2)s %(a3)s (ADJUSTMENT_REMARKS), %(p_nhap_tam)s, %(p_bu_bom)s."""
	from bc.api.sx import ADJUSTMENT_REMARKS
	p = {f"a{i}": r for i, r in enumerate(ADJUSTMENT_REMARKS, 1)}
	return {**p, "p_nhap_tam": P_NHAP_TAM, "p_bu_bom": P_BU_BOM}


def is_adjust_sql(se: str = "se") -> str:
	"""Điều kiện (SQL, alias Stock Entry `se`): phiếu điều chỉnh của sx — kiểm kê (custom_kiem_ke) hoặc 3 loại dọn tồn
	(ADJUSTMENT_REMARKS). Cần adjust_params(). Dùng NOT (...) để loại."""
	from bc.api.sx import ADJUSTMENT_REMARKS
	conds = [f"LOCATE(%(a{i})s, IFNULL({se}.remarks, '')) = 1" for i in range(1, len(ADJUSTMENT_REMARKS) + 1)]
	if has_kiem_ke_col():
		conds.insert(0, f"IFNULL({se}.custom_kiem_ke, '') != ''")
	return "(" + " OR ".join(conds) + ")"


# ─── Kho và vai trò ──────────────────────────────────────────────────────────
def _subtree(rows: list, root: str | None) -> set:
	"""Tên mọi kho trong cây con của `root` (gồm chính nó) theo lft/rgt; root không thuộc công ty → set()."""
	node = next((w for w in rows if w.name == root), None) if root else None
	if not node:
		return set()
	return {w.name for w in rows if cint(w.lft) >= cint(node.lft) and cint(w.rgt) <= cint(node.rgt)}


def warehouses(co: str | None = None) -> list:
	"""Mọi kho của công ty (gồm kho nhóm, kho ngừng dùng) + vai trò của kho lá:
	[{name, label, is_group, disabled, role, role_label, sellable, top, top_label, lft, rgt}] theo lft."""
	co = co or company()
	rows = frappe.db.sql(
		"""SELECT w.name, w.warehouse_name, w.parent_warehouse, IFNULL(w.is_group, 0) AS is_group,
			IFNULL(w.disabled, 0) AS disabled, w.warehouse_type, IFNULL(w.is_rejected_warehouse, 0) AS rejected,
			w.lft, w.rgt
		FROM `tabWarehouse` w WHERE w.company = %(co)s ORDER BY w.lft, w.name""", {"co": co}, as_dict=True)
	cfg = {role: _subtree(rows, sx_setting(field)) for role, field in _SX_ROLE_FIELDS.items()}
	from bc.api.sx import _wh
	cfg["tp"] = _subtree(rows, _wh()) | _subtree(rows, sx_setting("kho_tp"))
	pos = set()
	if frappe.db.table_exists("POS Profile"):
		for (w,) in frappe.db.sql("""SELECT DISTINCT warehouse FROM `tabPOS Profile`
				WHERE IFNULL(disabled, 0) = 0 AND company = %(co)s AND IFNULL(warehouse, '') != ''""", {"co": co}):
			pos |= _subtree(rows, w)
	cfg["cua_hang"] = pos
	by_name = {w.name: w for w in rows}
	out = []
	for w in rows:
		if w.rejected or w.name in cfg["tra_ve"]:
			role = "tra_ve"
		elif w.name in cfg["cach_ly"]:
			role = "cach_ly"
		elif (w.warehouse_type or "") == TRANSIT_TYPE:
			role = "di_duong"
		else:
			role = next((r for r in ("tp", "cua_hang", "xuong", "btp", "nvl") if w.name in cfg[r]), "khac")
		# Nhóm cấp 2 cho giao diện: tổ tiên ngay dưới gốc (gốc = kho không có cha trong công ty).
		top, seen = w, set()
		while top.parent_warehouse in by_name and by_name[top.parent_warehouse].parent_warehouse in by_name \
				and top.name not in seen:
			seen.add(top.name)
			top = by_name[top.parent_warehouse]
		out.append(frappe._dict(name=w.name, label=w.warehouse_name or w.name, is_group=cint(w.is_group),
			disabled=cint(w.disabled), role=role, role_label=ROLE_LABELS[role], sellable=role not in UNSELLABLE,
			top=top.name, top_label=top.warehouse_name or top.name, lft=cint(w.lft), rgt=cint(w.rgt)))
	return out


def warehouse_map(co: str | None = None) -> dict:
	"""{tên kho lá: dòng warehouses()}."""
	return {w.name: w for w in warehouses(co) if not w.is_group}


def sellable(whs: dict) -> tuple:
	"""Tuple kho lá bán được (luôn ≥ 1 phần tử — IN () là lỗi cú pháp)."""
	return tuple(n for n, w in whs.items() if w.sellable) or ("\x00",)


# ─── Nhóm hàng (cây) và tập thành phẩm ───────────────────────────────────────
def group_params() -> dict:
	return {"g_tet": tet_group(), "g_trad": traditional_group()}


def group_join(item_alias: str = "i") -> str:
	"""JOIN cây nhóm hàng cho alias Item `item_alias` — dùng cùng group_case(); cần group_params()."""
	return f"""LEFT JOIN `tabItem Group` ig ON ig.name = {item_alias}.item_group
		LEFT JOIN `tabItem Group` g_tet ON g_tet.name = %(g_tet)s
		LEFT JOIN `tabItem Group` g_trad ON g_trad.name = %(g_trad)s"""


GROUP_CASE = """CASE WHEN ig.lft >= g_tet.lft AND ig.rgt <= g_tet.rgt THEN 'tet'
		WHEN ig.lft >= g_trad.lft AND ig.rgt <= g_trad.rgt THEN 'traditional' ELSE 'other' END"""


def group_labels() -> dict:
	return {"tet": tet_group(), "traditional": traditional_group(), "other": "Khác"}


def groups_meta() -> dict:
	"""{found: {tet, traditional}, has_children: {...}} — nhóm không có trên site / là nhóm cha (health)."""
	found, children = {}, {}
	for k, name in (("tet", tet_group()), ("traditional", traditional_group())):
		r = frappe.db.sql("SELECT lft, rgt FROM `tabItem Group` WHERE name = %s", (name,), as_dict=True)
		found[k] = bool(r)
		children[k] = bool(r and cint(r[0].rgt) - cint(r[0].lft) > 1)
	return {"found": found, "has_children": children}


def _tp_by_group() -> set:
	rows = frappe.db.sql(
		f"""SELECT i.name FROM `tabItem` i {group_join('i')}
		WHERE (ig.lft >= g_tet.lft AND ig.rgt <= g_tet.rgt) OR (ig.lft >= g_trad.lft AND ig.rgt <= g_trad.rgt)""",
		group_params())
	return {r[0] for r in rows}


def tp_items() -> tuple:
	"""(set mã thành phẩm, nguồn 'sx' | 'nhom'). sx.utils.items_tp là MỘT chỗ trả lời "cái gì là thành phẩm" (nhóm TP
	trong SX Settings hoặc custom_sx_nhom = 'TP'); gồm mã ngừng dùng (vẫn có thể còn tồn). Site không có sx / sx trả
	rỗng / lỗi → mọi mã trong cây nhóm Tết ∪ truyền thống."""
	if sx_on():
		try:
			from sx.utils import items_tp
		except ImportError:
			items_tp = None
		if callable(items_tp):
			try:
				rows = items_tp(["name"], {"disabled": ("in", [0, 1])})
			except Exception:
				frappe.log_error(frappe.get_traceback(), "bc.kho.tp_items")
				rows = None
			if rows:
				return {r.name for r in rows}, "sx"
	return _tp_by_group(), "nhom"


def in_tuple(values) -> tuple:
	"""Tuple cho `IN %(x)s` — không bao giờ rỗng."""
	t = tuple(dict.fromkeys(v for v in values if v))
	return t or ("\x00",)


# ─── Bin (số "bây giờ") ──────────────────────────────────────────────────────
def bin_rows(co: str | None = None, whs: dict | None = None) -> list:
	"""Mọi dòng Bin có tồn / có giá trị của kho thuộc công ty (gồm mã ngừng dùng, kho ngừng dùng, dòng âm):
	[{item_code, warehouse, qty, value, rate, item_name, stock_uom, has_batch_no, item_disabled, group_key, sx_nhom,
	  role, sellable}]."""
	co = co or company()
	whs = whs if whs is not None else warehouse_map(co)
	nhom = "i.custom_sx_nhom" if frappe.db.has_column("Item", "custom_sx_nhom") else "NULL"
	rows = frappe.db.sql(
		f"""SELECT b.item_code, b.warehouse, b.actual_qty AS qty, b.stock_value AS value, b.valuation_rate AS rate,
			i.item_name, i.stock_uom, IFNULL(i.has_batch_no, 0) AS has_batch_no, IFNULL(i.disabled, 0) AS item_disabled,
			{nhom} AS sx_nhom, {GROUP_CASE} AS group_key
		FROM `tabBin` b
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		JOIN `tabItem` i ON i.name = b.item_code
		{group_join('i')}
		WHERE w.company = %(co)s AND (ABS(b.actual_qty) > %(eps)s OR ABS(b.stock_value) >= %(veps)s)""",
		{"co": co, "eps": EPS, "veps": VALUE_EPS, **group_params()}, as_dict=True)
	for r in rows:
		w = whs.get(r.warehouse)
		r.qty, r.value, r.rate = flt(r.qty), flt(r.value), flt(r.rate)
		r.role = w.role if w else "khac"
		r.sellable = bool(w.sellable) if w else True
	return rows


# ─── Giá vốn dự phòng ────────────────────────────────────────────────────────
def rates(pairs) -> dict:
	"""{(item, kho): (đơn giá, nguồn)} cho các cặp — nguồn 'bin' | 'bin_khac' | 'so_kho' | 'item' | None (chưa có giá
	vốn, đơn giá 0). Thứ tự như ERPNext get_valuation_rate, DỪNG ở Item.valuation_rate (không Item Price)."""
	pairs = list(dict.fromkeys(pairs))
	if not pairs:
		return {}
	items = in_tuple(i for i, _ in pairs)
	own, other = {}, {}
	# "Bin khác": dòng có đơn giá > 0 và tồn lớn nhất của mã (xác định, không phụ thuộc thứ tự đọc).
	for r in frappe.db.sql(
			"""SELECT item_code, warehouse, valuation_rate, actual_qty FROM `tabBin`
			WHERE item_code IN %(items)s AND valuation_rate > 0
			ORDER BY item_code, actual_qty DESC, warehouse""", {"items": items}, as_dict=True):
		own[(r.item_code, r.warehouse)] = flt(r.valuation_rate)
		other.setdefault(r.item_code, flt(r.valuation_rate))
	need = in_tuple(i for i, w in pairs if (i, w) not in own and i not in other)
	sle = {}
	if need != ("\x00",):
		for r in frappe.db.sql(
				"""SELECT t.item_code, t.valuation_rate FROM (
					SELECT item_code, valuation_rate, ROW_NUMBER() OVER (PARTITION BY item_code
						ORDER BY posting_datetime DESC, creation DESC) AS rn
					FROM `tabStock Ledger Entry`
					WHERE is_cancelled = 0 AND item_code IN %(items)s AND valuation_rate > 0) t
				WHERE t.rn = 1""", {"items": need}, as_dict=True):
			sle[r.item_code] = flt(r.valuation_rate)
	need2 = in_tuple(i for i in need if i not in sle)
	item = {}
	if need2 != ("\x00",):
		item = {r[0]: flt(r[1]) for r in frappe.db.sql(
			"SELECT name, valuation_rate FROM `tabItem` WHERE name IN %(items)s AND valuation_rate > 0", {"items": need2})}
	out = {}
	for i, w in pairs:
		if (i, w) in own:
			out[(i, w)] = (own[(i, w)], "bin")
		elif i in other:
			out[(i, w)] = (other[i], "bin_khac")
		elif i in sle:
			out[(i, w)] = (sle[i], "so_kho")
		elif i in item:
			out[(i, w)] = (item[i], "item")
		else:
			out[(i, w)] = (0.0, None)
	return out


# ─── Lô (một định nghĩa duy nhất — như sx _so_lo / utils.ton_cac_lo) ─────────────
def lot_rows(items, whs) -> list:
	"""Tồn từng lô (KHÔNG giới hạn ngày → khớp Bin, gồm phiếu ghi ngày tương lai): [{item_code, warehouse, batch_no,
	qty}] với ROUND(qty, 3) != 0. Lô trong Serial and Batch Bundle (v15+) hoặc SLE.batch_no (dữ liệu cũ)."""
	items, whs = in_tuple(items), in_tuple(whs)
	if items == ("\x00",) or whs == ("\x00",):
		return []
	rows = frappe.db.sql(
		"""SELECT sle.item_code, sle.warehouse, COALESCE(e.batch_no, sle.batch_no) AS batch_no,
			SUM(COALESCE(e.qty, sle.actual_qty)) AS qty
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabSerial and Batch Entry` e ON e.parent = sle.serial_and_batch_bundle
		WHERE sle.is_cancelled = 0 AND sle.item_code IN %(items)s AND sle.warehouse IN %(whs)s
			AND COALESCE(e.batch_no, sle.batch_no, '') != ''
		GROUP BY sle.item_code, sle.warehouse, COALESCE(e.batch_no, sle.batch_no)
		HAVING ROUND(SUM(COALESCE(e.qty, sle.actual_qty)), 3) != 0""", {"items": items, "whs": whs}, as_dict=True)
	for r in rows:
		r.qty = round(flt(r.qty), 3)
	return rows


# ─── Thông tin mã, thùng ─────────────────────────────────────────────────────
def item_info(codes) -> dict:
	"""{mã: {item_name, short_name, stock_uom, has_batch_no, disabled}}."""
	codes = in_tuple(codes)
	if codes == ("\x00",):
		return {}
	rows = frappe.db.sql(
		"""SELECT name, item_name, stock_uom, IFNULL(has_batch_no, 0) AS has_batch_no, IFNULL(disabled, 0) AS disabled
		FROM `tabItem` WHERE name IN %(c)s""", {"c": codes}, as_dict=True)
	return {r.name: frappe._dict(item_name=r.item_name, short_name=short_name(r.item_name or r.name),
		stock_uom=r.stock_uom, has_batch_no=cint(r.has_batch_no), disabled=cint(r.disabled)) for r in rows}


def carton_total(qty_by_item: dict, factors: dict | None = None) -> dict:
	"""Tổng thùng của {mã: số lượng (đơn vị kho)} + phần chưa quy được thùng:
	{cartons, boxes_without_carton_factor, items_without_carton_factor}. Chỉ dùng cho mã cùng đơn vị (hộp)."""
	factors = carton_factors(qty_by_item) if factors is None else factors
	cartons = without = 0.0
	n = 0
	for code, q in qty_by_item.items():
		f = factors.get(code)
		if f:
			cartons += flt(q) / f
		elif abs(flt(q)) > EPS:
			without += flt(q)
			n += 1
	return {"cartons": round(cartons, 1), "boxes_without_carton_factor": round(without, 3),
		"items_without_carton_factor": n}


def cartons_of(qty, factor) -> float:
	return to_cartons(qty, factor)


def one_uom(rows, key: str = "stock_uom") -> str | None:
	"""Đơn vị chung nếu MỌI dòng cùng một đơn vị kho, không thì None (không cộng Hộp với Kg)."""
	uoms = {r.get(key) for r in rows}
	return uoms.pop() if len(uoms) == 1 else None
