# -*- coding: utf-8 -*-
"""bc.api.kho_ton — Tồn kho cho Ban lãnh đạo (màn #/ton-kho): giá trị tồn bây giờ, xu hướng 12 tháng, nhập–xuất–tồn,
số ngày tồn kho, hàng chậm luân chuyển / tồn chết, tồn hàng Tết, sức khoẻ số liệu (đặc tả Kho bản chốt K1–K5, §6).

Hai method, tải riêng để trang hiện nhanh:
- get_overview(): khối `value` (K1), `doi` (K4), `slow` (K5), `tet_stock` (K5 phần Tết), `health` (§6). Số "bây giờ" theo
  Bin (gồm cả phiếu ghi ngày tương lai, đúng như ERPNext / GL) — xem quy ước chung trong bc.api.kho.
- get_trend(): `trend` (K2) + `nxt` (K3) dựng từ MỘT lượt quét sổ kho (SLE), cache 6 giờ, khoá theo hôm nay. Hai mục sức
  khoẻ cần quét cả sổ — future_value (phiếu ghi ngày sau hôm nay) và ledger_bin_diff — nằm ở `trend`, KHÔNG quét lại ở
  get_overview (posting_date không có chỉ mục); màn gộp chúng vào dải sức khoẻ khi trend về.

Luật (đặc tả §1–§4, các bẫy đã kiểm trong bộ thử test_kho_ton.py):
- K1: Σ Bin.stock_value mọi dòng có tồn / có giá trị của kho thuộc công ty (tabWarehouse.company) — gồm mã ngừng dùng,
  kho ngừng dùng, dòng âm (tổng giữ như ERPNext). Theo khu vực kho (vai trò kho, kho.warehouses) và theo nhóm hàng theo
  CÂY lft/rgt (nhóm con của "Hàng Tết" vẫn là Tết). Số lượng chỉ cộng khi cả nhóm cùng MỘT đơn vị kho (không cộng Hộp với
  Kg); thùng qua carton_factors, kèm số hộp chưa khai quy cách thùng. "Kho thành phẩm" (kho_tp) = live._finished_stock(_wh())
  — cùng con số với màn Thời gian thực; live chỉ đọc dòng Bin có số lượng nên khu vực TP = live + dòng chỉ còn giá trị
  (role_stranded_value) khi `same` (khu vực TP gồm đúng các kho của cây _wh()). Thành phẩm (thẻ hộp/thùng) = tập thành
  phẩm (kho.tp_items) ở kho bán được.
- K2: giá trị ngày D = Σ SLE.stock_value_difference (is_cancelled = 0, sle.company) có posting_date ≤ D; 12 cuối tháng
  đã qua + hôm nay + đầu năm tài chính + cùng kỳ năm trước. Kiểm: Σ mọi svd (cả tương lai) = Σ Bin (ledger_bin_diff).
- K3: cùng lượt quét, thêm CASE `loai` (đặc tả §4 K3). Tồn đầu tháng = luỹ kế trước tháng, cuối tháng = đầu + Σ loai — đẳng
  thức đúng tuyệt đối vì cùng các dòng sổ. "ban" là giá vốn hàng XUẤT bán (≈ gộp: phiếu trả hàng NPP/MT/du lịch không
  nhập kho qua hoá đơn — hàng về bằng phiếu nhập riêng, nằm ở "nhap_khac").
- K4: DOI = giá trị tồn ở kho bán được / (giá vốn xuất bán W ngày / W); W = kho_doi_days. Truyền thống luôn tính; Tết chỉ
  tính trong giai đoạn 'ban' (giai đoạn theo đặc tả ERP §5.2 — KHÔNG dùng sx_season()[0]); tet_season lỗi → phase None.
- K5: mã có tồn bán được > 0 (trừ nhóm Tết): ngày chưa xuất = hôm nay − (lần xuất cuối hoặc lần nhập đầu). Xuất = bán
  (SI/DN, dòng âm), dùng cho sản xuất (Manufacture / Material Consumption / Repack, trừ phiếu kiểm kê + dọn tồn của sx) và
  phiếu xuất NVL "Hạch toán bù nợ BOM" (W8). Không tính: trả hàng, chuyển kho, xuất huỷ / xuất khác, phiếu huỷ. Chậm =
  quá kho_slow_days (GỒM cả tồn chết, đặc tả K5 / ERP §6.2); tồn chết = quá kho_dead_days. % = trên giá trị hàng ở kho bán
  được của cùng phần (thành phẩm / vật tư / tất cả — gồm cả hàng Tết, đặc tả ERP §6.2). Chia thành phẩm / vật tư.
- Riêng tư: chỉ số tổng hợp + mã / tên hàng / tên kho; không người tạo, ghi chú, diễn giải phiếu, tên khách.
- Không gọi whitelisted method của app khác; chỉ helper thuần (sx.utils.items_tp qua kho.tp_items). Mốc ngày từ Python.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import frappe
from frappe.utils import add_days, cint, flt, getdate

from bc.api import kho
from bc.api._common import (
	_guard, cache_key, cached, carton_factors, drop_hidden, fy_range, iso, pct, run_cached, safe_block, setting_int,
	short_name, tet_season,
)

TREND_TTL = 6 * 3600
NO_STOCK_RELIEF_DAYS = 7      # hoá đơn không trừ kho quá N ngày (health.si_no_stock_relief)
STRANDED_VALUE = 1            # dòng Bin không còn số lượng mà còn ≥ 1 đồng (đặc tả ERP §10)
TOP_N = 10

# Khu vực kho trên màn (gộp vai trò kho của kho.warehouses) — đặc tả K1.
ROLE_BUCKETS = (
	("tp", "Kho thành phẩm", ("tp",)),
	("cua_hang", "Cửa hàng", ("cua_hang",)),
	("di_duong", "Hàng đi đường", ("di_duong",)),
	("san_xuat", "Kho sản xuất", ("xuong", "btp", "nvl")),          # xưởng, bán thành phẩm, nguyên vật liệu
	("khong_ban", "Không bán được", ("tra_ve", "cach_ly")),        # hàng trả về, cách ly
	("khac", "Kho khác", ("khac",)),
)
# Tách nhóm "Khác" theo custom_sx_nhom của sx (chỉ tiền — các loại này khác đơn vị).
OTHER_SPLIT = (("nvl", "Nguyên vật liệu"), ("bao_bi", "Bao bì"), ("btp", "Bán thành phẩm"), ("tp_khac", "Thành phẩm khác"),
	("khac", "Khác"))
# Nhập–xuất–tồn: thứ tự dòng trên màn (key khớp CASE loai trong _scan) — (key, nhãn ngắn, giải thích).
LOAI = (
	("ton_dau", "Tồn đầu khai báo", "Số dư tồn kho khai báo khi bắt đầu dùng hệ thống (phiếu đầu kỳ)"),
	("mua", "Mua hàng", "Hàng mua nhập kho (phiếu nhập mua, hoá đơn mua có nhập kho)"),
	("ban", "Xuất bán (giá vốn)", "Giá vốn hàng xuất kho để bán (hoá đơn có xuất kho, phiếu giao hàng); chưa trừ hàng trả qua "
		"phiếu giảm giá"),
	("nhap_tam", "Thành phẩm nhập tạm", "Thành phẩm nhập kho khi chưa có công thức (giá tạm)"),
	("bu_no_bom", "NVL bù nợ công thức", "Nguyên liệu xuất bù cho thành phẩm đã nhập tạm khi có công thức"),
	("noi_bo", "Sản xuất, chuyển kho", "Sản xuất, đóng gói, chuyển kho nội bộ (cả công ty gần bằng 0; theo nhóm là thành phẩm "
		"tăng, nguyên liệu giảm)"),
	("nhap_khac", "Nhập khác, hàng trả", "Phiếu nhập khác, gồm hàng khách trả được nhập lại kho"),
	("xuat_khac", "Xuất huỷ, mẫu, khác", "Phiếu xuất khác: huỷ hàng, hàng mẫu, biếu tặng…"),
	("kiem_ke_sx", "Kiểm kê kho sản xuất", "Chênh lệch kiểm kê của hệ thống sản xuất (theo ngày ghi sổ)"),
	("kiem_ke_ch", "Kiểm kê cửa hàng", "Chênh lệch kiểm kê cửa hàng / kho khác"),
	("don_sx", "Dọn tồn (sản xuất)", "Phiếu dọn tồn âm / tồn không lô của hệ thống sản xuất"),
	("khac", "Điều chỉnh khác", "Điều chỉnh giá trị và chứng từ kho khác"),
)
LOAI_KEYS = tuple(x[0] for x in LOAI)
PHASE_LABELS = {"ban": "Tồn hàng Tết đang bán", "chuan_bi": "Tồn hàng Tết chuẩn bị mùa", "sau_mua": "Tồn hàng Tết sau mùa"}
BUCKETS = (("0-30", 30), ("31-90", 90), ("91-180", 180), (">180", None))
GROUPS = ("tet", "traditional", "other")
BASIS = "Giá trị theo giá vốn (giá trị tồn kho trên sổ), chưa VAT"


def _money(v) -> float:
	return round(flt(v), 2)


def _qty(v) -> float:
	return round(flt(v), 3)


class _Ctx:
	"""Số dùng chung giữa các khối của một lượt get_overview — tính lười, lỗi ở đâu chỉ khối đó tắt (safe_block)."""

	def __init__(self, co, today):
		self.co, self.today, self._m = co, today, {}

	def _get(self, key, fn):
		if key not in self._m:
			self._m[key] = fn()
		return self._m[key]

	@property
	def wh_all(self):
		return self._get("wh_all", lambda: kho.warehouses(self.co))  # gồm kho nhóm (cây con của _wh())

	@property
	def whs(self):
		return self._get("whs", lambda: {w.name: w for w in self.wh_all if not w.is_group})  # = kho.warehouse_map

	@property
	def bins(self):
		return self._get("bins", lambda: kho.bin_rows(self.co, self.whs))

	@property
	def tp(self):
		return self._get("tp", kho.tp_items)  # (set mã, nguồn 'sx' | 'nhom')

	@property
	def phase(self):
		return self._get("phase", lambda: tet_phase(self.today))


# ─── Giai đoạn mùa Tết (đặc tả ERP §5.2) ─────────────────────────────────────
def tet_phase(today) -> str | None:
	"""'ban' (01/11 → mùng 1 Tết) | 'chuan_bi' (đầu mùa sản xuất → trước mùa bán) | 'sau_mua' | None (chưa khai ngày Tết).
	Mốc chuẩn bị = 01/{sx_season_start_month}/NĂM NAY — không dùng sx_season()[0]: từ sau Tết tới 30/04 hàm đó trả mùa
	sản xuất đang chạy (bắt đầu tháng 10 năm trước) → 20/04 sẽ thành 'chuan_bi' sai."""
	today = getdate(today)
	try:
		s = tet_season(today)
	except Exception:  # thiếu ngày Tết trong BC Settings → frappe.throw
		frappe.clear_last_message()
		return None
	m = setting_int("sx_season_start_month", 10)
	sx_start = datetime.date(today.year, m if 1 <= m <= 12 else 10, 1)
	if not s["between_seasons"] and today <= getdate(s["tet_date"]):
		return "ban"
	if s["between_seasons"] and today >= sx_start:
		return "chuan_bi"
	return "sau_mua"


# ─── K1. Giá trị tồn bây giờ ─────────────────────────────────────────────────
def _other_key(sx_nhom) -> str:
	n = (sx_nhom or "").strip()
	if n == "NVL":
		return "nvl"
	if n == "Bao Bi":
		return "bao_bi"
	if n.startswith("BTP"):
		return "btp"
	if n == "TP":
		return "tp_khac"
	return "khac"


def _per_item(rows) -> dict:
	"""{mã: {qty, value, stock_uom, item_name, group_key}} cộng các dòng Bin."""
	out: dict = {}
	for r in rows:
		x = out.setdefault(r.item_code, frappe._dict(item_code=r.item_code, item_name=r.item_name, stock_uom=r.stock_uom,
			group_key=r.group_key, qty=0.0, value=0.0))
		x.qty += r.qty
		x.value += r.value
	return out


def _uom_block(items: dict, factors: dict) -> dict:
	"""Số lượng + thùng của một nhóm mã: chỉ khi MỌI mã có tồn cùng một đơn vị kho (không cộng Hộp với Kg)."""
	live = [x for x in items.values() if abs(x.qty) > kho.EPS]
	uom = kho.one_uom(live)
	if not uom:
		return {"qty": None, "uom": None, "cartons": None, "boxes_without_carton_factor": None,
			"items_without_carton_factor": None}
	ct = kho.carton_total({x.item_code: x.qty for x in live}, factors)
	return {"qty": _qty(sum(x.qty for x in live)), "uom": uom, **ct}


def _top(items, factors, n=TOP_N) -> list:
	rows = [{"item_code": x.item_code, "short_name": short_name(x.item_name or x.item_code), "group_key": x.group_key,
		"qty": _qty(x.qty), "uom": x.stock_uom, "cartons": kho.cartons_of(x.qty, factors.get(x.item_code)) if factors.get(x.item_code) else None,
		"value": _money(x.value)} for x in items]
	rows = sorted(drop_hidden(rows), key=lambda r: (-r["value"], r["item_code"]))
	return rows[:n]


def _value(ctx: _Ctx) -> dict:
	from bc.api.live import _finished_stock
	from bc.api.sx import _wh

	bins, whs = ctx.bins, ctx.whs
	total = sum(r.value for r in bins)
	labels = kho.group_labels()
	items_all = _per_item(bins)
	factors = carton_factors(items_all)

	# Khu vực kho (vai trò) + từng kho.
	by_wh: dict = {}
	for r in bins:
		w = by_wh.setdefault(r.warehouse, {"value": 0.0, "items": set()})
		w["value"] += r.value
		if r.qty > kho.EPS:
			w["items"].add(r.item_code)
	by_role = []
	for key, label, roles in ROLE_BUCKETS:
		rows = [r for r in bins if r.role in roles]
		v = sum(r.value for r in rows)
		wl = []
		for name, w in by_wh.items():
			info = whs.get(name)
			if (info.role if info else "khac") in roles:
				wl.append({"name": name, "label": info.label if info else name, "role": info.role if info else "khac",
					"disabled": bool(info.disabled) if info else False, "value": _money(w["value"]), "items": len(w["items"])})
		by_role.append({"key": key, "label": label, "value": _money(v), "pct": pct(v, total),
			"sellable": key != "khong_ban",
			"roles": [{"role": ro, "label": kho.ROLE_LABELS[ro], "value": _money(sum(r.value for r in rows if r.role == ro))}
				for ro in roles],
			"warehouses": sorted(wl, key=lambda x: (-x["value"], x["label"]))})

	# Nhóm hàng (cây).
	by_group = []
	for g in GROUPS:
		rows = [r for r in bins if r.group_key == g]
		its = _per_item(rows)
		by_group.append({"key": g, "label": labels[g], "value": _money(sum(r.value for r in rows)),
			"value_sellable": _money(sum(r.value for r in rows if r.sellable)), "items": sum(1 for x in its.values() if x.qty > kho.EPS),
			**_uom_block(its, factors)})
	other_split = []
	for key, label in OTHER_SPLIT:
		v = sum(r.value for r in bins if r.group_key == "other" and _other_key(r.sx_nhom) == key)
		other_split.append({"key": key, "label": label, "value": _money(v)})

	# Thành phẩm ở kho bán được (C3) — thẻ hộp / thùng.
	tp_set, tp_src = ctx.tp
	tp_items = _per_item([r for r in bins if r.sellable and r.item_code in tp_set])
	tp = {"source": tp_src, "value": _money(sum(x.value for x in tp_items.values())),
		"items": sum(1 for x in tp_items.values() if x.qty > kho.EPS), **_uom_block(tp_items, factors)}

	# Kho thành phẩm = đúng con số màn Thời gian thực (cây con của _wh()). Chỉ lấy GIÁ TRỊ của live: số hộp / thùng của live
	# cộng mọi đơn vị trong kho (Hộp + Kg) nên không đưa ra. live bỏ dòng Bin số lượng 0 → so cùng gốc: khu vực TP = live +
	# dòng chỉ còn giá trị của khu vực TP. `same` theo TẬP KHO (không theo số tiền): khu vực "Kho thành phẩm" gồm đúng các kho
	# lá của cây _wh() — lệch khi SX Settings.kho_tp khác _wh() hoặc kho trả về / cách ly / đi đường nằm trong cây đó.
	wh = _wh()
	fs = _finished_stock(wh)
	tp_bucket = by_role[0]
	sub = kho._subtree(ctx.wh_all, wh) & set(whs)
	role_tp = {n for n, w in whs.items() if w.role == "tp"}
	stranded_tp = sum(r.value for r in bins if r.role == "tp" and abs(r.qty) <= kho.EPS)
	kho_tp = {"warehouse": wh, "label": (whs.get(wh).label if whs.get(wh) else wh.split(" - ")[0]),
		"value": _money(fs["value"]), "items": cint(fs["items"]), "role_value": tp_bucket["value"],
		"role_stranded_value": _money(stranded_tp), "same": sub == role_tp}

	unsell = sum(r.value for r in bins if not r.sellable)
	return {
		"available": True,
		"totals": {
			"value": _money(total), "value_sellable": _money(total - unsell), "value_unsellable": _money(unsell),
			"value_transit": _money(sum(r.value for r in bins if r.role == "di_duong")),
			"items_in_stock": len({r.item_code for r in bins if r.qty > kho.EPS}),
			"warehouses_in_stock": len({r.warehouse for r in bins if r.qty > kho.EPS}),
			"rows": len(bins), "negative_rows": sum(1 for r in bins if r.qty < -kho.EPS),
		},
		"by_role": by_role,
		"by_group": by_group,
		"other_split": other_split,
		"sx_nhom": bool(frappe.db.has_column("Item", "custom_sx_nhom")),
		"tp": tp,
		"kho_tp": kho_tp,
		"top": _top(items_all.values(), factors),
	}


# ─── K4. Số ngày tồn kho ─────────────────────────────────────────────────────
def _cogs(co, w_from, today) -> dict:
	"""Giá vốn hàng xuất bán theo nhóm (S4): −Σ svd của SLE Sales Invoice / Delivery Note trong [w_from, today]."""
	rows = frappe.db.sql(
		f"""SELECT {kho.GROUP_CASE} AS group_key, -SUM(sle.stock_value_difference) AS cogs
		FROM `tabStock Ledger Entry` sle
		JOIN `tabItem` i ON i.name = sle.item_code
		{kho.group_join('i')}
		WHERE sle.is_cancelled = 0 AND sle.company = %(co)s
			AND sle.voucher_type IN ('Sales Invoice', 'Delivery Note')
			AND sle.posting_date BETWEEN %(f)s AND %(t)s
		GROUP BY group_key""", {"co": co, "f": w_from, "t": today, **kho.group_params()}, as_dict=True)
	return {r.group_key: flt(r.cogs) for r in rows}


def _doi_of(v, cogs, w):
	return round(v / (cogs / w), 1) if cogs > 0 else None


def _doi(ctx: _Ctx) -> dict:
	w = kho.kho_int("kho_doi_days")
	today = ctx.today
	w_from = getdate(add_days(today, -(w - 1)))
	cogs = _cogs(ctx.co, w_from, today)
	sell = {g: sum(r.value for r in ctx.bins if r.sellable and r.group_key == g) for g in GROUPS}
	phase = ctx.phase
	trad_v, trad_c = sell["traditional"], cogs.get("traditional", 0.0)
	tet_v, tet_c = sell["tet"], cogs.get("tet", 0.0)
	return {
		"available": True, "window_days": w, "from": iso(w_from), "to": iso(today),
		"traditional": {"value": _money(trad_v), "cogs": _money(trad_c), "days": _doi_of(trad_v, trad_c, w),
			"no_sales": trad_c <= 0},
		"tet": {"phase": phase, "applicable": phase == "ban", "value": _money(tet_v), "cogs": _money(tet_c),
			"days": _doi_of(tet_v, tet_c, w) if phase == "ban" else None, "no_sales": tet_c <= 0},
	}


# ─── K5. Hàng chậm luân chuyển / tồn chết ────────────────────────────────────
def _last_moves(co, codes, today) -> dict:
	"""S5 + W8: {mã: (last_sale, last_used, first_in)} — chỉ dòng sổ sống, posting_date ≤ hôm nay."""
	codes = kho.in_tuple(codes)
	if codes == ("\x00",):
		return {}
	adj = kho.is_adjust_sql("se")
	rows = frappe.db.sql(
		f"""SELECT sle.item_code,
			MAX(CASE WHEN sle.actual_qty < 0 AND sle.voucher_type IN ('Sales Invoice', 'Delivery Note')
				THEN sle.posting_date END) AS last_sale,
			MAX(CASE WHEN sle.actual_qty < 0 AND sle.voucher_type = 'Stock Entry' AND (
					(se.purpose IN ('Manufacture', 'Material Consumption for Manufacture', 'Repack') AND NOT {adj})
					OR (se.purpose = 'Material Issue' AND LOCATE(%(p_bu_bom)s, IFNULL(se.remarks, '')) = 1))
				THEN sle.posting_date END) AS last_used,
			MIN(CASE WHEN sle.actual_qty > 0 OR sle.voucher_type = 'Stock Reconciliation'
				THEN sle.posting_date END) AS first_in
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabStock Entry` se ON sle.voucher_type = 'Stock Entry' AND se.name = sle.voucher_no
		WHERE sle.is_cancelled = 0 AND sle.company = %(co)s AND sle.item_code IN %(codes)s AND sle.posting_date <= %(today)s
		GROUP BY sle.item_code""", {"co": co, "codes": codes, "today": today, **kho.adjust_params()}, as_dict=True)
	return {r.item_code: (r.last_sale, r.last_used, r.first_in) for r in rows}


def _bucket(idle: int) -> str:
	return next(k for k, top in BUCKETS if top is None or idle <= top)


def _slow_summary(rows, factors, sellable_value) -> dict:
	"""Một phần (thành phẩm / vật tư / tất cả). Chậm = idle > kho_slow_days, GỒM cả tồn chết (status 'dead'); % trên giá trị
	hàng ở kho bán được của cùng phần (`sellable_value`, gồm hàng Tết và mã ngoài phạm vi) — đặc tả K5 / ERP §6.2."""
	base = sum(r["value"] for r in rows)
	slow = [r for r in rows if r["status"] in ("slow", "dead")]
	dead = [r for r in rows if r["status"] == "dead"]
	never = [r for r in rows if r["never"]]
	den = sellable_value if sellable_value >= kho.VALUE_EPS else 0  # 0 / âm → pct None
	buckets = [{"key": k, "value": _money(sum(r["value"] for r in rows if r["bucket"] == k)),
		"items": sum(1 for r in rows if r["bucket"] == k)} for k, _ in BUCKETS]
	top = sorted(drop_hidden([r for r in rows if r["status"] != "ok"]), key=lambda r: (-r["value"], r["item_code"]))[:TOP_N]
	return {
		"items": len(rows), "value": _money(base), "sellable_value": _money(sellable_value),
		"slow_items": len(slow), "slow_value": _money(sum(r["value"] for r in slow)),
		"slow_pct": pct(sum(r["value"] for r in slow), den),
		"dead_items": len(dead), "dead_value": _money(sum(r["value"] for r in dead)),
		"dead_pct": pct(sum(r["value"] for r in dead), den),
		"never_items": len(never), "never_value": _money(sum(r["value"] for r in never)),
		"buckets": buckets,
		"top": [{**r, "value": _money(r["value"]), "qty": _qty(r["qty"]),
			"cartons": kho.cartons_of(r["qty"], factors.get(r["item_code"])) if factors.get(r["item_code"]) else None}
			for r in top],
	}


def _slow(ctx: _Ctx) -> dict:
	slow_days, dead_days = kho.kho_int("kho_slow_days"), kho.kho_int("kho_dead_days")
	today = ctx.today
	sell = _per_item([r for r in ctx.bins if r.sellable and r.group_key != "tet"])
	scope = {c: x for c, x in sell.items() if x.qty > kho.EPS}
	moves = _last_moves(ctx.co, scope, today)
	tp_set, tp_src = ctx.tp
	rows = []
	for code, x in scope.items():
		last_sale, last_used, first_in = moves.get(code, (None, None, None))
		outs = [getdate(d) for d in (last_sale, last_used) if d]  # không dùng GREATEST() trong SQL: NULL nuốt cả hai
		last_out = max(outs) if outs else None
		ref = last_out or (getdate(first_in) if first_in else None)
		idle = max((today - ref).days, 0) if ref else 0
		status = "dead" if idle > dead_days else "slow" if idle > slow_days else "ok"
		rows.append({"item_code": code, "short_name": short_name(x.item_name or code), "group_key": x.group_key,
			"split": "tp" if code in tp_set else "vat_tu", "qty": x.qty, "uom": x.stock_uom, "value": x.value,
			"last_sale": iso(last_sale), "last_used": iso(last_used), "last_out": iso(last_out), "first_in": iso(first_in),
			"idle_days": idle, "never": last_out is None, "bucket": _bucket(idle), "status": status})
	factors = carton_factors(r["item_code"] for r in rows if r["split"] == "tp")
	# Mẫu số %: giá trị ở kho bán được (mọi mã, cả hàng Tết) — thành phẩm = tập TP, vật tư = phần còn lại.
	sv_all = sum(r.value for r in ctx.bins if r.sellable)
	sv_tp = sum(r.value for r in ctx.bins if r.sellable and r.item_code in tp_set)
	return {
		"available": True, "slow_days": slow_days, "dead_days": dead_days, "tp_source": tp_src,
		"buckets_def": [k for k, _ in BUCKETS], "slow_includes_dead": True,
		"total": _slow_summary(rows, factors, sv_all),
		"tp": _slow_summary([r for r in rows if r["split"] == "tp"], factors, sv_tp),
		"vat_tu": _slow_summary([r for r in rows if r["split"] == "vat_tu"], factors, sv_all - sv_tp),
	}


def _tet_stock(ctx: _Ctx) -> dict:
	phase = ctx.phase
	its = _per_item([r for r in ctx.bins if r.sellable and r.group_key == "tet"])
	factors = carton_factors(its)
	return {"available": True, "phase": phase, "label": PHASE_LABELS.get(phase, "Tồn hàng Tết"),
		"group": kho.group_labels()["tet"], "value": _money(sum(x.value for x in its.values())),
		"items": sum(1 for x in its.values() if x.qty > kho.EPS), **_uom_block(its, factors),
		"top": _top([x for x in its.values() if x.qty > kho.EPS], factors, 5)}


# ─── §6. Sức khoẻ số liệu ────────────────────────────────────────────────────
def _soft(h: dict, name: str, fn):
	"""Một mục health: lỗi / thiếu bảng / thiếu cột → bỏ mục (không làm hỏng cả dải)."""
	try:
		v = fn()
	except LookupError:  # site không có DocType đó (Single chưa cài) — bỏ mục, không ghi lỗi
		return
	except Exception:
		frappe.clear_last_message()
		frappe.log_error(frappe.get_traceback(), f"bc.kho_ton.health.{name}")
		return
	if isinstance(v, dict) and v.pop("_merge", False):
		h.update(v)
	elif v is not None:
		h[name] = v


def _single(doctype, field):
	if not frappe.db.exists("DocType", doctype):
		raise LookupError(doctype)
	return frappe.db.get_single_value(doctype, field)  # field chưa có trong meta → throw → _soft bỏ mục


def _reposts(co):
	if not frappe.db.table_exists("Repost Item Valuation"):
		return None
	r = frappe.db.sql("""SELECT COUNT(*) AS n, MIN(posting_date) AS since FROM `tabRepost Item Valuation`
		WHERE docstatus = 1 AND status IN ('Queued', 'In Progress') AND company = %(co)s""", {"co": co}, as_dict=True)[0]
	return {"_merge": True, "pending_reposts": cint(r.n), "repost_since": iso(r.since)}


def _pos_unconsolidated(co):
	if not (frappe.db.table_exists("POS Invoice") and frappe.db.has_column("POS Invoice", "consolidated_invoice")):
		return None
	return cint(frappe.db.sql("""SELECT COUNT(*) FROM `tabPOS Invoice`
		WHERE docstatus = 1 AND company = %(co)s AND IFNULL(consolidated_invoice, '') = ''""", {"co": co})[0][0])


def _si_no_stock_relief(co, today):
	"""Hoá đơn bán (không trả, không đầu kỳ) update_stock = 0, có mã hàng kho chưa giao đủ và không lập từ phiếu giao,
	quá N ngày: hàng chưa bao giờ trừ khỏi sổ kho (ERP T11). delivered_qty theo ĐƠN VỊ BÁN → so với sii.qty (không
	stock_qty: dòng bán theo Thùng có stock_qty = qty × quy cách)."""
	for dt, col in (("Sales Invoice", "update_stock"), ("Sales Invoice Item", "delivered_qty"), ("Item", "is_stock_item")):
		if not frappe.db.has_column(dt, col):
			return None
	cut = getdate(add_days(today, -NO_STOCK_RELIEF_DAYS))
	r = frappe.db.sql(
		"""SELECT COUNT(DISTINCT si.name) AS n, MIN(si.posting_date) AS oldest
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name AND sii.parenttype = 'Sales Invoice'
		JOIN `tabItem` i ON i.name = sii.item_code
		WHERE si.docstatus = 1 AND IFNULL(si.is_return, 0) = 0 AND IFNULL(si.update_stock, 0) = 0
			AND IFNULL(si.is_opening, 'No') != 'Yes' AND si.company = %(co)s AND si.posting_date < %(cut)s
			AND i.is_stock_item = 1 AND IFNULL(sii.delivery_note, '') = '' AND IFNULL(sii.dn_detail, '') = ''
			AND IFNULL(sii.delivered_qty, 0) < IFNULL(sii.qty, 0) - %(eps)s""",
		{"co": co, "cut": cut, "eps": kho.EPS}, as_dict=True)[0]
	return {"count": cint(r.n), "oldest": iso(r.oldest), "days": NO_STOCK_RELIEF_DAYS}


def _tp_mismatch(ctx: _Ctx):
	tp_set, src = ctx.tp
	if src != "sx":
		return {"source": src, "in_sx_not_group": None, "in_group_not_sx": None}
	grp = kho._tp_by_group()
	return {"source": src, "in_sx_not_group": len(tp_set - grp), "in_group_not_sx": len(grp - tp_set)}


def _company_mismatch(co):
	if not frappe.db.exists("DocType", "SX Settings"):
		return None
	sx_co = kho.sx_setting("cong_ty")
	return {"_merge": True, "company_mismatch": bool(sx_co) and sx_co != co, "sx_company": sx_co}


def _kho_tp_mismatch():
	if not frappe.db.exists("DocType", "SX Settings"):
		return None
	from bc.api.sx import _wh
	k = kho.sx_setting("kho_tp")
	return {"_merge": True, "kho_tp_mismatch": bool(k) and k != _wh(), "kho_tp_bc": _wh(), "kho_tp_sx": k}


def _no_carton(ctx: _Ctx):
	tp_set, _src = ctx.tp
	its = {c: x for c, x in _per_item([r for r in ctx.bins if r.sellable and r.item_code in tp_set]).items() if x.qty > kho.EPS}
	f = carton_factors(its)
	miss = [x for c, x in its.items() if not f.get(c)]
	return {"_merge": True, "items_without_carton_factor": len(miss),
		"boxes_without_carton_factor": _qty(sum(x.qty for x in miss))}


def _stranded(ctx: _Ctx):
	rows = [r for r in ctx.bins if abs(r.qty) <= kho.EPS and abs(r.value) >= STRANDED_VALUE]
	return {"_merge": True, "stranded_value_rows": len(rows), "stranded_value": _money(sum(r.value for r in rows))}


def _health(ctx: _Ctx) -> dict:
	"""Đặc tả §6, trừ future_value / ledger_bin_diff (cần quét cả sổ kho → lấy ở get_trend().trend, cùng lượt quét K2)."""
	co, today = ctx.co, ctx.today
	h: dict = {"available": True}
	_soft(h, "reposts", lambda: _reposts(co))
	_soft(h, "allow_negative_stock", lambda: bool(cint(_single("Stock Settings", "allow_negative_stock"))))
	_soft(h, "allow_negative_stock_for_batch", lambda: bool(cint(_single("Stock Settings", "allow_negative_stock_for_batch"))))
	_soft(h, "pos_unconsolidated", lambda: _pos_unconsolidated(co))
	_soft(h, "si_no_stock_relief", lambda: _si_no_stock_relief(co, today))
	_soft(h, "tp_set_mismatch", lambda: _tp_mismatch(ctx))
	_soft(h, "groups", lambda: {"_merge": True, "group_mode": "subtree",
		"group_has_children": kho.groups_meta()["has_children"]})
	_soft(h, "company", lambda: _company_mismatch(co))
	_soft(h, "kho_tp", _kho_tp_mismatch)
	_soft(h, "cartons", lambda: _no_carton(ctx))
	_soft(h, "stranded", lambda: _stranded(ctx))
	return h


# ─── Method ──────────────────────────────────────────────────────────────────
def _company_or_none():
	try:
		return kho.company()
	except Exception:  # chưa khai công ty mặc định → frappe.throw
		frappe.clear_last_message()
		return None


@frappe.whitelist()
def get_overview(refresh=0):
	"""Tồn kho bây giờ (K1), số ngày tồn (K4), hàng chậm / tồn chết + tồn hàng Tết (K5), sức khoẻ số liệu (§6).

	{available, meta: {asof, company, groups, groups_found, group_mode, settings, basis}, value, doi, slow, tet_stock, health}
	health không có future_value / ledger_bin_diff — hai mục đó ở get_trend().trend (một lượt quét sổ, cache 6 giờ).
	"""
	_guard("ton-kho")
	today = kho.today()

	def build():
		co = _company_or_none()
		if not co:
			return {"available": False, "meta": {"asof": iso(today), "reason": "no_company"}}
		ctx = _Ctx(co, today)
		gm = safe_block("kho_ton.groups", kho.groups_meta)
		return {
			"available": True,
			"meta": {"asof": iso(today), "company": co, "groups": kho.group_labels(), "groups_found": gm.get("found"),
				"group_mode": "subtree", "settings": kho.settings(), "basis": BASIS},
			"value": safe_block("kho_ton.value", _value, ctx),
			"doi": safe_block("kho_ton.doi", _doi, ctx),
			"slow": safe_block("kho_ton.slow", _slow, ctx),
			"tet_stock": safe_block("kho_ton.tet_stock", _tet_stock, ctx),
			"health": safe_block("kho_ton.health", _health, ctx),
		}

	return run_cached("kho_ton.get_overview", {"today": iso(today)}, build, refresh)


# ─── K2 + K3: một lượt quét sổ kho ───────────────────────────────────────────
def _loai_case() -> str:
	from bc.api.sx import ADJUSTMENT_REMARKS
	don = " OR ".join(f"LOCATE(%(a{i})s, IFNULL(se.remarks, '')) = 1" for i in range(1, len(ADJUSTMENT_REMARKS) + 1))
	kk = "WHEN IFNULL(se.custom_kiem_ke, '') != '' THEN 'kiem_ke_sx'" if kho.has_kiem_ke_col() else ""
	return f"""CASE
		WHEN sle.voucher_type = 'Stock Reconciliation' AND sr.purpose = 'Opening Stock' THEN 'ton_dau'
		WHEN sle.voucher_type = 'Stock Entry' AND se.is_opening = 'Yes' THEN 'ton_dau'
		WHEN sle.voucher_type IN ('Purchase Receipt', 'Purchase Invoice') THEN 'mua'
		WHEN sle.voucher_type IN ('Sales Invoice', 'Delivery Note') THEN 'ban'
		WHEN sle.voucher_type = 'Stock Reconciliation' AND sr.purpose = 'Adjustment Entry' THEN 'khac'
		WHEN sle.voucher_type = 'Stock Reconciliation' THEN 'kiem_ke_ch'
		WHEN sle.voucher_type <> 'Stock Entry' THEN 'khac'
		{kk}
		WHEN {don} THEN 'don_sx'
		WHEN LOCATE(%(p_nhap_tam)s, IFNULL(se.remarks, '')) = 1 THEN 'nhap_tam'
		WHEN LOCATE(%(p_bu_bom)s, IFNULL(se.remarks, '')) = 1 THEN 'bu_no_bom'
		WHEN se.purpose = 'Material Receipt' THEN 'nhap_khac'
		WHEN se.purpose = 'Material Issue' THEN 'xuat_khac'
		ELSE 'noi_bo' END"""


def _scan(co, today) -> list:
	"""S3 mở rộng: Σ svd theo (năm, tháng, tương lai?, nhóm, loai) — MỘT lượt quét toàn sổ (không chặn dưới: luỹ kế cần
	cả lịch sử). LEFT JOIN Item: mã đã xoá vẫn vào tổng (nhóm 'other') để đối chiếu Bin."""
	return frappe.db.sql(
		f"""SELECT YEAR(sle.posting_date) AS y, MONTH(sle.posting_date) AS m, (sle.posting_date > %(today)s) AS fut,
			{kho.GROUP_CASE} AS group_key, {_loai_case()} AS loai, SUM(sle.stock_value_difference) AS v
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabItem` i ON i.name = sle.item_code
		{kho.group_join('i')}
		LEFT JOIN `tabStock Entry` se ON sle.voucher_type = 'Stock Entry' AND se.name = sle.voucher_no
		LEFT JOIN `tabStock Reconciliation` sr ON sle.voucher_type = 'Stock Reconciliation' AND sr.name = sle.voucher_no
		WHERE sle.is_cancelled = 0 AND sle.company = %(co)s
		GROUP BY y, m, fut, group_key, loai""",
		{"co": co, "today": today, **kho.group_params(), **kho.adjust_params()}, as_dict=True)


def _ym(y, m, back=0) -> tuple:
	i = y * 12 + (m - 1) - back
	return i // 12, i % 12 + 1


def _month_end(y, m) -> datetime.date:
	ny, nm = _ym(y, m, -1)
	return datetime.date(ny, nm, 1) - datetime.timedelta(days=1)


def _label(y, m) -> str:
	return f"{y:04d}-{m:02d}"


def _trend(co, today) -> dict:
	rows = _scan(co, today)
	zero = Decimal(0)
	flows: dict = {}          # (y, m) → {(group, loai): Decimal} — chỉ dòng ≤ hôm nay
	future = zero
	for r in rows:
		v = Decimal(r.v or 0)
		if cint(r.fut):
			future += v
			continue
		key = (cint(r.y), cint(r.m))
		g = r.group_key if r.group_key in GROUPS else "other"
		d = flows.setdefault(key, {})
		d[(g, r.loai)] = d.get((g, r.loai), zero) + v
	ty, tm = today.year, today.month
	window = [_ym(ty, tm, b) for b in range(12, -1, -1)]   # 12 tháng đã qua + tháng này (tới hôm nay)
	first = window[0]

	def cum_before(ym) -> dict:
		"""Luỹ kế theo nhóm của mọi tháng < ym."""
		out = {g: zero for g in GROUPS}
		for k, d in flows.items():
			if k < ym:
				for (g, _l), v in d.items():
					out[g] += v
		return out

	run = cum_before(first)
	points, months = [], []
	for (y, m) in window:
		d = flows.get((y, m), {})
		opening = dict(run)
		per = {g: {lo: zero for lo in LOAI_KEYS} for g in GROUPS}
		for (g, lo), v in d.items():
			per[g][lo if lo in per[g] else "khac"] += v
		for g in GROUPS:
			run[g] = opening[g] + sum(per[g].values())
		cur = (y, m) == (ty, tm)
		end = today if cur else _month_end(y, m)
		points.append({"month": _label(y, m), "date": iso(end), "today": cur, "value": _money(sum(run.values())),
			**{g: _money(run[g]) for g in GROUPS}})
		grp = {g: {"opening": _money(opening[g]), "closing": _money(run[g]),
			"flows": {lo: _money(per[g][lo]) for lo in LOAI_KEYS}} for g in GROUPS}
		grp["all"] = {"opening": _money(sum(opening.values())), "closing": _money(sum(run.values())),
			"flows": {lo: _money(sum(per[g][lo] for g in GROUPS)) for lo in LOAI_KEYS}}
		months.append({"month": _label(y, m), "from": iso(datetime.date(y, m, 1)), "to": iso(end), "current": cur,
			"groups": grp})

	def value_at_end(y, m):
		c = cum_before(_ym(y, m, -1))
		return _money(sum(c.values()))

	fy_start = getdate(fy_range(today)["fy_start"])
	fy_y, fy_m = _ym(fy_start.year, fy_start.month, 1)
	ly_y, ly_m = _ym(ty, tm, 13)
	ledger = sum((sum(d.values(), zero) for d in flows.values()), zero) + future
	bin_total = Decimal(frappe.db.sql("""SELECT COALESCE(SUM(b.stock_value), 0) FROM `tabBin` b
		JOIN `tabWarehouse` w ON w.name = b.warehouse WHERE w.company = %(co)s""", {"co": co})[0][0] or 0)
	trend = {
		"available": True, "points": points,
		"fy_start": iso(fy_start), "fy_start_date": iso(_month_end(fy_y, fy_m)), "fy_start_value": value_at_end(fy_y, fy_m),
		"ly_month_end": iso(_month_end(ly_y, ly_m)), "ly_month_end_value": value_at_end(ly_y, ly_m),
		"future_value": _money(future), "bin_total": _money(bin_total), "ledger_bin_diff": _money(ledger - bin_total),
	}
	nxt = {"available": True, "months": months, "default_month": months[-2]["month"], "current_month": months[-1]["month"]}
	return {"trend": trend, "nxt": nxt}


@frappe.whitelist()
def get_trend(refresh=0):
	"""Xu hướng giá trị tồn 12 tháng (K2) + nhập–xuất–tồn theo tháng (K3) — một lượt quét sổ kho, cache 6 giờ.

	{available, meta: {asof, company, groups, loai, basis}, trend: {points, fy_start_value, ly_month_end_value, future_value,
	 ledger_bin_diff, …}, nxt: {months: [{month, from, to, current, groups: {all|tet|traditional|other: {opening, flows,
	 closing}}}], default_month, current_month}}
	"""
	_guard("ton-kho")
	today = kho.today()

	def build():
		co = _company_or_none()
		if not co:
			return {"available": False, "meta": {"asof": iso(today), "reason": "no_company"}}
		res = safe_block("kho_ton.trend", _trend, co, today)
		if res.get("available") is False:
			res = {"trend": res, "nxt": res}
		return {
			"available": True,
			"meta": {"asof": iso(today), "company": co, "groups": kho.group_labels(), "group_mode": "subtree",
				"loai": [{"key": k, "label": lb, "desc": ds} for k, lb, ds in LOAI], "basis": BASIS},
			**res,
		}

	return cached(cache_key("kho_ton.get_trend", {"today": iso(today)}), build, ttl=TREND_TTL, refresh=refresh)
