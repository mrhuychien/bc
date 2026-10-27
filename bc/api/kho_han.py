# -*- coding: utf-8 -*-
"""bc.api.kho_han — Hạn dùng, tồn không bán được, tồn âm (K6–K8, đặc tả Kho bản chốt). Mảng "han-dung".

Một lượt get_overview() trả 3 khối, mỗi khối một safe_block (khối lỗi chỉ tắt khối đó):

- han (K6) — Tồn THÀNH PHẨM ở kho BÁN ĐƯỢC theo hạn dùng, số "bây giờ" (Bin, gồm phiếu ghi ngày tương lai).
  Tập TP = kho.tp_items() (sx.utils.items_tp → dự phòng cây nhóm Tết ∪ truyền thống). Tồn từng lô = kho.lot_rows
  (MỘT định nghĩa, không giới hạn ngày → khớp Bin). Phân loại theo Item.has_batch_no HIỆN TẠI (sx bật / tắt cờ lô
  tạm thời — đặc tả lô T10): mã quản lý lô = các lô + phần chưa gắn lô (Bin − Σ lô, LO Q3); mã không quản lý lô =
  cả dòng Bin (lô cũ ghi trên sổ của mã đã tắt lô KHÔNG tính riêng — tính hai lần là lệch tồn kho).
  Các phần RỜI NHAU, cộng lại ĐÚNG bằng Σ Bin.actual_qty của tập TP ở kho bán được (trả về `doi_chieu`):
    · lô dương có HSD → het_han (còn < 0 ngày; lô hết hạn HÔM NAY vẫn còn hạn, như ERPNext / sx) · d30 (0–30)
      · d60 (31–60) · d90 (61–90) · tren90; "cận date" = 0..N ngày (N = BC Settings.kho_can_date_ngay, mặc định 60);
    · chua_ro (chưa rõ HSD) = lô dương không có HSD (TONCU tách riêng — tên '-TONCU' / '-TONCU-n') + phần chưa
      gắn lô dương + dòng Bin dương của mã chưa quản lý lô;
    · phan_am = lô âm + phần chưa gắn lô âm + dòng Bin âm của mã không quản lý lô (chi tiết ở K8);
    · lô ĐANG THU HỒI (Batch.custom_thu_hoi = 1, có cột mới đọc) bị rút khỏi các phần trên → K7(b); đối chiếu
      cộng lại phần này.
  Giá trị phần dương = số lượng × Bin.valuation_rate của ĐÚNG (mã, kho) — ƯỚC TÍNH theo giá vốn bình quân kho (Bin giá
  0 → giá trị 0, số hộp báo ở qty_no_rate). Phần âm = −|số lượng| × giá vốn dự phòng (kho.rates trong công ty, như K8).
  "Số lô" = số lô KHÁC NHAU (mã, lô) — một lô HSD (D131) nằm ở Kho TP và nhiều cửa hàng vẫn là một lô; số dòng
  (lô × kho) ở `rows`. Đơn vị tính THEO TỪNG PHẦN: phần chỉ gồm mã cùng đơn vị có qty / thùng; phần lẫn Hộp với Kg có
  qty None và `theo_dvt` (số lượng, thùng từng đơn vị — đơn vị không mã nào khai thùng thì không quy thùng); phần âm
  không quy thùng.
  % giá trị = trên Σ giá trị các phần DƯƠNG (lô dương + chưa gắn lô dương + mã không lô dương), cùng cơ sở ước tính.
  HSD ước tính (NSX / ngày tạo lô + hạn dùng công bố tháng hoặc shelf_life ngày) CHỈ để hiện cạnh lô chưa ghi HSD,
  không bao giờ vào nhóm hết hạn / cận date (TONCU không ước tính).
- khong_ban (K7) — (a) Σ Bin.stock_value ở kho hàng trả về / cách ly (mọi mã, gồm dòng âm như tổng K1) + tuổi
  (ngày từ lần nhập gần nhất vào kho đó, dòng sổ sống, ngày ≤ hôm nay — phiếu ghi ngày sau có trong số lượng nhưng
  không làm tuổi âm); (b) lô đang thu hồi còn tồn dương ở kho BÁN ĐƯỢC (mã quản lý lô, ước tính
  như K6); (c) = phần het_han của K6 (cùng số, không tính lại). (b) ⊥ (c) vì K6 đã rút lô thu hồi.
- am (K8) — dòng Bin âm (< −1e-6) ở MỌI kho của công ty: số dòng / mã / kho, giá trị |âm| = Σ |qty| × giá vốn dự
  phòng C2 TRONG CÔNG TY (C5): Bin(mã, kho) → Bin khác của mã ở kho công ty (tồn lớn nhất) → dòng sổ gần nhất ở kho
  công ty → Item.valuation_rate → "chưa có giá vốn" (không dùng Bin.stock_value của dòng âm, không dùng Item Price,
  không lấy giá vốn của công ty khác giữ cùng mã); tách TP ở kho xưởng (đích dọn âm của sx) / cửa hàng (bán POS trước khi chốt ca) /
  khác. Mức lô (mã TP quản lý lô, mọi kho công ty): số lô âm, số (mã, kho) có phần chưa gắn lô ≠ 0.

Đơn vị = Item.stock_uom; số lượng cộng chỉ khi mọi mã cùng một đơn vị (không cộng Hộp với Kg → qty None), thùng qua
carton_factors kèm số hộp chưa khai quy cách thùng. Danh sách qua drop_hidden, tổng thì không. Không trả người
tạo / người thu hồi / lý do / ghi chú — chỉ mã hàng, tên rút gọn, lô, kho. Không import gì của app sx (tập TP đọc mềm
qua kho.tp_items; helper sx có ghi DB hay chuỗi giá vốn có giá mua bị cấm — đặc tả §5); mốc ngày truyền từ Python.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, add_months, cint, flt, getdate

from bc.api import kho
from bc.api._common import _guard, drop_hidden, iso, pct, run_cached, safe_block, short_name, to_cartons

EPS = kho.EPS
LOT_EPS = 0.0005        # lô làm tròn 3 chữ số (Serial and Batch Entry.qty) — như sx
TOP_LO = 50             # dòng tối đa của mỗi danh sách lô
TOP_DS = 20             # dòng tối đa của danh sách kho không bán được / tồn âm
BUCKETS = (("het_han", "Đã hết hạn"), ("d30", "Còn 0–30 ngày"), ("d60", "Còn 31–60 ngày"),
	("d90", "Còn 61–90 ngày"), ("tren90", "Còn trên 90 ngày"))
PARTS = (("toncu", "Lô tồn cũ chưa rõ hạn"), ("lo_khong_hsd", "Lô chưa ghi hạn dùng"),
	("khong_lo", "Tồn chưa gắn lô"), ("chua_quan_ly_lo", "Mã chưa quản lý theo lô"))
SPLIT_AM = (("tp_xuong", "Thành phẩm ở kho xưởng"), ("cua_hang", "Cửa hàng"), ("khac", "Kho khác"))


@frappe.whitelist()
def get_overview(refresh=0):
	"""K6 + K7 + K8. Không tham số kỳ: mọi số là tồn hiện tại."""
	_guard("han-dung")
	today = kho.today()
	n = kho.kho_int("kho_can_date_ngay")
	return run_cached("kho_han.get_overview", {"today": iso(today), "can_date": n}, lambda: _build(today, n), refresh)


# ─── Khung ───────────────────────────────────────────────────────────────────
class _Ctx:
	"""Dữ liệu dùng chung giữa các khối, đọc một lần (lỗi thì mỗi khối tự báo lỗi — không ghi nhớ lỗi)."""

	def __init__(self, today, n):
		self.today, self.n = today, n
		self.co = kho.company()
		self.whs = kho.warehouse_map(self.co)                                  # kho lá của công ty
		self.sell = {w for w, x in self.whs.items() if x.sellable}
		self._m: dict = {}

	def _memo(self, key, fn):
		if key not in self._m:
			self._m[key] = fn()
		return self._m[key]

	def bins(self):
		return self._memo("bins", lambda: kho.bin_rows(self.co, self.whs))

	def tp(self):
		return self._memo("tp", kho.tp_items)

	def tp_info(self):
		return self._memo("tp_info", lambda: kho.item_info(self.tp()[0]))

	def tp_lots(self):
		"""Lô của mã TP đang quản lý lô (cờ HIỆN TẠI), ở MỌI kho lá của công ty (K6 lọc kho bán được, K8 lấy hết)."""
		def f():
			info = self.tp_info()
			return kho.lot_rows([i for i, x in info.items() if x.has_batch_no], list(self.whs))
		return self._memo("tp_lots", f)

	def thu_hoi_col(self) -> bool:
		return self._memo("thu_hoi_col", lambda: bool(frappe.db.has_column("Batch", "custom_thu_hoi")))

	def wh_label(self, w):
		x = self.whs.get(w)
		return x.label if x else w


def _build(today, n):
	try:
		c = _Ctx(today, n)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc.kho_han.context")
		frappe.clear_last_message()
		return {"available": False, "reason": "Chưa xác định được công ty hoặc danh sách kho.",
			"meta": {"as_of": iso(today), "can_date_ngay": n}}
	han = safe_block("kho_han.han", _han, c)
	khong_ban = safe_block("kho_han.khong_ban", _khong_ban, c, han)
	am = safe_block("kho_han.am", _am, c)
	return {"available": True, "han": han, "khong_ban": khong_ban, "am": am, "meta": _meta(c)}


def _meta(c) -> dict:
	m = {"as_of": iso(c.today), "can_date_ngay": c.n, "company": c.co,
		"kho_ban_duoc": len(c.sell), "kho_khong_ban": sorted(x.label for x in c.whs.values() if not x.sellable),
		"basis": "Giá trị theo giá vốn, chưa VAT; giá trị theo lô là ước tính (số lượng × giá vốn bình quân của mã tại kho)."}
	try:
		tp, src = c.tp()
		m.update(tp_nguon=src, so_ma_tp=len(tp), co_cot_thu_hoi=c.thu_hoi_col())
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc.kho_han.meta")
	return m


# ─── Cộng dồn một phần (số lượng theo mã, giá trị, lô, mã) ───────────────────
class _Acc:
	def __init__(self):
		self.q: dict = {}
		self.v = 0.0
		self.rows: set = set()      # (mã, kho, lô | None) — một dòng trên sổ
		self.lots: set = set()      # (mã, lô) — một lô dù nằm ở mấy kho
		self.nr: dict = {}          # số lượng chưa có giá vốn ở kho đang giữ, theo mã

	def add(self, e):
		self.q[e["item"]] = self.q.get(e["item"], 0.0) + e["qty"]
		self.v += e["value"]
		self.rows.add((e["item"], e["wh"], e["lo"]))
		if e["lo"]:
			self.lots.add((e["item"], e["lo"]))
		if e.get("no_rate"):
			self.nr[e["item"]] = self.nr.get(e["item"], 0.0) + e["qty"]

	def theo_dvt(self, info: dict, factors: dict, cartons: bool = True) -> list:
		"""Số lượng từng đơn vị kho của phần này. Thùng chỉ khi phần có MỘT đơn vị hoặc đơn vị đó có mã khai thùng
		(Kg không quy thùng); phần âm (cartons=False) không quy thùng."""
		by_u: dict = {}
		for i, q in self.q.items():
			by_u.setdefault(info[i].stock_uom, {})[i] = q
		out = []
		for u, qs in sorted(by_u.items(), key=lambda x: str(x[0])):
			ct = kho.carton_total(qs, factors)
			show = cartons and (len(by_u) == 1 or any(factors.get(i) for i in qs))
			out.append({"uom": u, "qty": round(sum(qs.values()), 3), "items": len(qs),
				"cartons": ct["cartons"] if show else None,
				"boxes_without_carton_factor": ct["boxes_without_carton_factor"] if show else None,
				"items_without_carton_factor": ct["items_without_carton_factor"] if show else None,
				"qty_no_rate": round(sum(self.nr.get(i, 0.0) for i in qs), 3)})
		return out

	def out(self, info: dict, factors: dict, den=None, cartons: bool = True) -> dict:
		theo = self.theo_dvt(info, factors, cartons)
		one = len(theo) <= 1
		x = theo[0] if theo else {"uom": None, "qty": 0.0, "cartons": 0.0 if cartons else None,
			"boxes_without_carton_factor": 0.0 if cartons else None, "items_without_carton_factor": 0 if cartons else None,
			"qty_no_rate": 0.0}
		return {
			"uom": x["uom"] if one else None,
			"qty": x["qty"] if one else None,                     # không cộng Hộp với Kg
			"cartons": x["cartons"] if one else None,
			"boxes_without_carton_factor": x["boxes_without_carton_factor"] if one else None,
			"items_without_carton_factor": x["items_without_carton_factor"] if one else None,
			"qty_no_rate": x["qty_no_rate"] if one else None,
			"theo_dvt": theo,
			"value": round(self.v, 2),
			"pct": pct(self.v, den) if den is not None else None,
			"rows": len(self.rows),
			"lots": len(self.lots),
			"items": len(self.q),
		}


def _bucket(days: int) -> str:
	if days < 0:
		return "het_han"           # hết hạn hôm nay (days = 0) vẫn còn hạn
	if days <= 30:
		return "d30"
	if days <= 60:
		return "d60"
	if days <= 90:
		return "d90"
	return "tren90"


def _is_toncu(name) -> bool:
	"""Lô tồn cũ D191 của sx: '{prefix}-TONCU' hoặc '{prefix}-TONCU-2' (trùng tên mã khác)."""
	s = str(name or "")
	return s.endswith("-TONCU") or "-TONCU-" in s


def _batches(names, thu_hoi_col: bool) -> dict:
	"""{lô: {expiry_date, manufacturing_date, tao, thu_hoi}} — chỉ các cột không riêng tư."""
	names = kho.in_tuple(names)
	if names == ("\x00",):
		return {}
	th = "IFNULL(b.custom_thu_hoi, 0)" if thu_hoi_col else "0"
	rows = frappe.db.sql(
		f"""SELECT b.name, b.expiry_date, b.manufacturing_date, DATE(b.creation) AS tao, {th} AS thu_hoi
		FROM `tabBatch` b WHERE b.name IN %(b)s""", {"b": names}, as_dict=True)
	return {r.name: r for r in rows}


def _bin_rates(c, pairs) -> dict:
	"""{(mã, kho): Bin.valuation_rate} — dòng Bin bin_rows bỏ qua (tồn ≈ 0, giá trị ≈ 0) đọc thẳng."""
	have = {(r.item_code, r.warehouse): r.rate for r in c.bins()}
	miss = [p for p in pairs if p not in have]
	if miss:
		for r in frappe.db.sql(
				"""SELECT item_code, warehouse, valuation_rate FROM `tabBin`
				WHERE item_code IN %(i)s AND warehouse IN %(w)s""",
				{"i": kho.in_tuple(i for i, _ in miss), "w": kho.in_tuple(w for _, w in miss)}, as_dict=True):
			have.setdefault((r.item_code, r.warehouse), flt(r.valuation_rate))
	return {p: flt(have.get(p)) for p in pairs}


def _hsd_uoc_tinh(entries) -> None:
	"""Ghi e['hsd_uoc_tinh'] cho lô KHÔNG có HSD (trừ TONCU): (NSX hoặc ngày tạo lô) + hạn dùng công bố (tháng theo
	lịch) → Item.shelf_life_in_days (ngày) → None. Chỉ để hiện — không vào nhóm hạn."""
	lots = [e for e in entries if e["lo"] and not e["exp"] and not _is_toncu(e["lo"])]
	if not lots:
		return
	items = kho.in_tuple(e["item"] for e in lots)
	cb = frappe.db.has_column("Item", "custom_sp_cong_bo") and frappe.db.table_exists("SX San Pham Cong Bo")
	thang_sel = "IFNULL(cb.han_dung_thang, 0)" if cb else "0"
	join = "LEFT JOIN `tabSX San Pham Cong Bo` cb ON cb.name = i.custom_sp_cong_bo" if cb else ""
	han = {r.name: r for r in frappe.db.sql(
		f"""SELECT i.name, {thang_sel} AS thang, IFNULL(i.shelf_life_in_days, 0) AS ngay
		FROM `tabItem` i {join} WHERE i.name IN %(i)s""", {"i": items}, as_dict=True)}
	for e in lots:
		h, base = han.get(e["item"]), e.get("mfg") or e.get("tao")
		if not h or not base:
			continue
		if cint(h.thang) > 0:
			e["hsd_uoc_tinh"] = getdate(add_months(base, cint(h.thang)))
		elif cint(h.ngay) > 0:
			e["hsd_uoc_tinh"] = getdate(add_days(base, cint(h.ngay)))


# ─── K6. Tồn TP theo hạn dùng ────────────────────────────────────────────────
def _han(c) -> dict:
	tp, _src = c.tp()
	info = c.tp_info()
	bins = [r for r in c.bins() if r.item_code in tp and r.warehouse in c.sell]
	binq = {(r.item_code, r.warehouse): r.qty for r in bins}
	lots = [l for l in c.tp_lots() if l.warehouse in c.sell and abs(flt(l.qty)) >= LOT_EPS]
	meta = _batches({l.batch_no for l in lots}, c.thu_hoi_col())
	by_pair: dict = {}
	for l in lots:
		by_pair.setdefault((l.item_code, l.warehouse), []).append(l)

	ent = []  # mỗi phần tử: một lô / phần chưa gắn lô / dòng mã không lô, ở một kho
	for (i, w), ls in by_pair.items():
		for l in ls:
			b = meta.get(l.batch_no) or {}
			ent.append({"item": i, "wh": w, "lo": l.batch_no, "qty": flt(l.qty), "kind": "lo",
				"exp": getdate(b.get("expiry_date")) if b.get("expiry_date") else None, "thu_hoi": cint(b.get("thu_hoi")),
				"mfg": b.get("manufacturing_date"), "tao": b.get("tao")})
	batch_pairs = {p for p in binq if info.get(p[0]) and info[p[0]].has_batch_no} | set(by_pair)
	for p in batch_pairs:  # LO Q3: phần chưa gắn lô = Bin − Σ lô (cả hai dấu)
		r = round(flt(binq.get(p)) - sum(flt(l.qty) for l in by_pair.get(p, [])), 6)
		if abs(r) > EPS:
			ent.append({"item": p[0], "wh": p[1], "lo": None, "qty": r, "kind": "khong_lo", "exp": None, "thu_hoi": 0})
	for (i, w), q in binq.items():
		if not info[i].has_batch_no and abs(q) > EPS:
			ent.append({"item": i, "wh": w, "lo": None, "qty": q, "kind": "chua_quan_ly_lo", "exp": None, "thu_hoi": 0})

	rate = _bin_rates(c, {(e["item"], e["wh"]) for e in ent})
	neg = [e for e in ent if e["qty"] < 0]
	rt_neg = kho.rates([(e["item"], e["wh"]) for e in neg], c.co)
	for e in ent:
		if e["qty"] < 0:
			e["slice"], e["value"] = "phan_am", -abs(e["qty"]) * rt_neg[(e["item"], e["wh"])][0]
			continue
		r = rate[(e["item"], e["wh"])]
		e["value"], e["no_rate"] = e["qty"] * r, r <= 0
		if e["kind"] == "lo" and e["thu_hoi"]:
			e["slice"] = "thu_hoi"
		elif e["kind"] == "lo" and e["exp"]:
			e["days"] = (e["exp"] - c.today).days
			e["slice"] = _bucket(e["days"])
		elif e["kind"] == "lo":
			e["slice"], e["part"] = "chua_ro", "toncu" if _is_toncu(e["lo"]) else "lo_khong_hsd"
		else:
			e["slice"], e["part"] = "chua_ro", e["kind"]

	acc = {k: _Acc() for k in (*[b for b, _ in BUCKETS], "can_date", "chua_ro", "phan_am", "thu_hoi", "tong",
		*[p for p, _ in PARTS])}
	for e in ent:
		acc[e["slice"]].add(e)
		if e["slice"] in dict(BUCKETS) or e["slice"] == "chua_ro":
			acc["tong"].add(e)
		if e["slice"] == "chua_ro":
			acc[e["part"]].add(e)
		if e.get("days") is not None and 0 <= e["days"] <= c.n:
			acc["can_date"].add(e)

	uoms = {info[e["item"]].stock_uom for e in ent} | {info[r.item_code].stock_uom for r in bins}
	same = len(uoms) <= 1
	f = kho.carton_factors({e["item"] for e in ent})
	den = acc["tong"].v
	_hsd_uoc_tinh([e for e in ent if e["slice"] == "chua_ro"])

	# Đối chiếu với tồn kho (Bin) theo từng đơn vị: phần dương + lô thu hồi + phần âm (≤ 0) = Σ Bin.actual_qty TP ở kho
	# bán được (cac_phan = dương + âm, giữ cho tương thích).
	dv: dict = {}
	for r in bins:
		dv.setdefault(info[r.item_code].stock_uom, [0.0, 0.0, 0.0, 0.0])[0] += r.qty
	for e in ent:
		x = dv.setdefault(info[e["item"]].stock_uom, [0.0, 0.0, 0.0, 0.0])
		x[3 if e["slice"] == "thu_hoi" else 2 if e["slice"] == "phan_am" else 1] += e["qty"]
	theo_dvt = [{"uom": u, "ton_kho": round(b, 3), "duong": round(d, 3), "am": round(a, 3), "cac_phan": round(d + a, 3),
		"thu_hoi": round(t, 3), "lech": round(b - d - a - t, 3)} for u, (b, d, a, t) in sorted(dv.items(), key=lambda x: str(x[0]))]

	def row(e):
		x = info[e["item"]]
		return {"item_code": e["item"], "short_name": x.short_name, "lo": e["lo"], "kho": c.wh_label(e["wh"]),
			"qty": round(e["qty"], 3), "uom": x.stock_uom, "cartons": to_cartons(e["qty"], f.get(e["item"])) if f.get(e["item"]) else None,
			"value": round(e["value"], 2)}

	can = sorted((e for e in ent if e.get("days") is not None and e["days"] <= c.n),
		key=lambda e: (e["days"], -e["value"], e["item"], e["wh"], e["lo"]))
	can = drop_hidden([{**row(e), "hsd": iso(e["exp"]), "con_ngay": e["days"], "het_han": e["days"] < 0} for e in can])
	cr = sorted((e for e in ent if e["slice"] == "chua_ro"), key=lambda e: (-e["value"], e["item"], e["wh"], e["lo"] or ""))
	cr = drop_hidden([{**row(e), "loai": e["part"], "hsd_uoc_tinh": iso(e.get("hsd_uoc_tinh"))} for e in cr])
	uoc = [e for e in ent if e.get("hsd_uoc_tinh")]

	return {
		"available": True,
		"uom": next(iter(uoms)) if len(uoms) == 1 else None,
		"can_date_ngay": c.n,
		"buckets": [{"key": k, "label": lb, **acc[k].out(info, f, den)} for k, lb in BUCKETS],
		"can_date": {"ngay": c.n, **acc["can_date"].out(info, f, den)},
		"chua_ro": {**acc["chua_ro"].out(info, f, den),
			"parts": [{"key": k, "label": lb, **acc[k].out(info, f, den)} for k, lb in PARTS],
			"uoc_tinh_qua_han": sum(1 for e in uoc if e["hsd_uoc_tinh"] < c.today)},   # HSD ước tính = hôm nay: chưa qua
		"phan_am": acc["phan_am"].out(info, f, cartons=False),   # số âm không quy thùng
		"thu_hoi": acc["thu_hoi"].out(info, f),
		"tong": acc["tong"].out(info, f, den),
		"doi_chieu": {
			"ton_kho_qty": round(sum(r.qty for r in bins), 3) if same else None,
			"ton_kho_value": round(sum(r.value for r in bins), 2),
			"cac_phan_qty": round(sum(e["qty"] for e in ent if e["slice"] != "thu_hoi"), 3) if same else None,
			"thu_hoi_qty": round(sum(acc["thu_hoi"].q.values()), 3) if same else None,
			"theo_dvt": theo_dvt,
			"khop": all(abs(x["lech"]) <= 0.001 for x in theo_dvt),
		},
		"lo_can_date": can[:TOP_LO], "lo_can_date_tong": len(can),
		"chua_ro_ds": cr[:TOP_LO], "chua_ro_ds_tong": len(cr),
	}


# ─── K7. Tồn không bán được ──────────────────────────────────────────────────
def _last_in(pairs, today) -> dict:
	"""{(mã, kho): ngày nhập gần nhất} — dòng sổ sống, số lượng vào > 0, ngày ≤ hôm nay (phiếu ghi ngày sau không làm
	tuổi âm; số lượng Bin vẫn gồm nó). Lọc theo mã: dùng chỉ mục mã-kho."""
	pairs = set(pairs)
	if not pairs:
		return {}
	rows = frappe.db.sql(
		"""SELECT item_code, warehouse, MAX(posting_date) AS d FROM `tabStock Ledger Entry`
		WHERE is_cancelled = 0 AND actual_qty > 0 AND posting_date <= %(t)s AND item_code IN %(i)s AND warehouse IN %(w)s
		GROUP BY item_code, warehouse""",
		{"t": today, "i": kho.in_tuple(i for i, _ in pairs), "w": kho.in_tuple(w for _, w in pairs)}, as_dict=True)
	return {(r.item_code, r.warehouse): getdate(r.d) for r in rows if (r.item_code, r.warehouse) in pairs}


def _thu_hoi(c) -> dict:
	"""(b) Lô đang thu hồi (mã quản lý lô) còn tồn dương ở kho bán được — giá trị ước tính như K6. "Số lô" = lô khác nhau
	(mã, lô); số dòng lô × kho ở `rows`. Site chưa có cột thu hồi → {available: False, no_column: True} (khác lỗi)."""
	if not c.thu_hoi_col():
		return {"available": False, "no_column": True}
	rec = {r.name: r for r in frappe.db.sql(
		"""SELECT b.name, b.item, b.expiry_date FROM `tabBatch` b JOIN `tabItem` i ON i.name = b.item
		WHERE IFNULL(b.custom_thu_hoi, 0) = 1 AND IFNULL(i.has_batch_no, 0) = 1""", as_dict=True)}
	lots = [l for l in kho.lot_rows({r.item for r in rec.values()}, c.sell) if l.batch_no in rec and l.qty > LOT_EPS] \
		if rec else []
	info = kho.item_info({l.item_code for l in lots})
	rate = _bin_rates(c, {(l.item_code, l.warehouse) for l in lots})
	f = kho.carton_factors({l.item_code for l in lots})
	uoms = {info[l.item_code].stock_uom for l in lots}
	ds = sorted(({"item_code": l.item_code, "short_name": info[l.item_code].short_name, "lo": l.batch_no,
		"kho": c.wh_label(l.warehouse), "hsd": iso(rec[l.batch_no].expiry_date), "qty": round(flt(l.qty), 3),
		"uom": info[l.item_code].stock_uom, "cartons": to_cartons(l.qty, f.get(l.item_code)) if f.get(l.item_code) else None,
		"value": round(flt(l.qty) * rate[(l.item_code, l.warehouse)], 2)} for l in lots),
		key=lambda x: (-x["value"], x["item_code"], x["kho"], x["lo"]))
	value = sum(flt(l.qty) * rate[(l.item_code, l.warehouse)] for l in lots)
	ds = drop_hidden(ds)
	return {"available": True, "value": round(value, 2),
		"qty": round(sum(flt(l.qty) for l in lots), 3) if len(uoms) <= 1 else None,
		"uom": next(iter(uoms)) if len(uoms) == 1 else None, "rows": len(lots),
		"lots": len({(l.item_code, l.batch_no) for l in lots}), "items": len({l.item_code for l in lots}),
		"ds": ds[:TOP_DS], "ds_tong": len(ds)}


def _khong_ban(c, han) -> dict:
	rows = [r for r in c.bins() if r.role in kho.UNSELLABLE]
	roles = []
	for role in kho.UNSELLABLE:
		rr = [r for r in rows if r.role == role]
		am = [r for r in rr if r.qty < -EPS]
		roles.append({"role": role, "label": kho.ROLE_LABELS[role], "value": round(sum(r.value for r in rr), 2),
			"rows": len(rr), "items": len({r.item_code for r in rr if r.qty > EPS}),
			"warehouses": len({r.warehouse for r in rr}), "am_rows": len(am), "am_value": round(sum(r.value for r in am), 2)})
	pos = [r for r in rows if r.qty > EPS]
	last = _last_in(((r.item_code, r.warehouse) for r in pos), c.today)
	top = sorted(({"item_code": r.item_code, "short_name": short_name(r.item_name or r.item_code), "kho": c.wh_label(r.warehouse),
		"vai_tro": kho.ROLE_LABELS[r.role], "qty": round(r.qty, 3), "uom": r.stock_uom, "value": round(r.value, 2),
		"nhap_cuoi": iso(last.get((r.item_code, r.warehouse))),
		"tuoi_ngay": (c.today - last[(r.item_code, r.warehouse)]).days if (r.item_code, r.warehouse) in last else None}
		for r in pos), key=lambda x: (-x["value"], x["item_code"], x["kho"]))
	top = drop_hidden(top)
	a = {"value": round(sum(r.value for r in rows), 2), "roles": roles, "ds": top[:TOP_DS], "ds_tong": len(top)}
	b = safe_block("kho_han.thu_hoi", _thu_hoi, c)
	hh = next((x for x in han.get("buckets", []) if x["key"] == "het_han"), None) if han.get("available") else None
	cc = {"available": True, "value": hh["value"], "qty": hh["qty"], "uom": hh["uom"], "lots": hh["lots"], "items": hh["items"]} \
		if hh else {"available": False, "error": bool(han.get("error"))}
	# error: khối tính lỗi (khác "site chưa có đánh dấu thu hồi" — no_column) để giao diện nói đúng lý do.
	parts = [{"key": "kho_loai", "label": "Hàng trả về, cách ly", "value": a["value"], "available": True, "error": False},
		{"key": "thu_hoi", "label": "Lô đang thu hồi còn ở kho bán", "value": b.get("value"), "available": bool(b.get("available")),
			"error": bool(b.get("error"))},
		{"key": "het_han", "label": "Thành phẩm hết hạn ở kho bán", "value": cc.get("value"), "available": cc["available"],
			"error": bool(cc.get("error"))}]
	return {"available": True, "tong": round(sum(flt(p["value"]) for p in parts if p["available"]), 2),
		"day_du": all(p["available"] for p in parts), "parts": parts, "kho_loai": a, "thu_hoi": b, "het_han": cc}


# ─── K8. Tồn âm ──────────────────────────────────────────────────────────────
def _stock_flag(field):
	try:
		v = frappe.db.get_single_value("Stock Settings", field)
	except Exception:
		frappe.clear_last_message()
		return None
	return bool(cint(v))


def _am(c) -> dict:
	tp, _src = c.tp()
	neg = [r for r in c.bins() if r.qty < -EPS]
	rt = kho.rates([(r.item_code, r.warehouse) for r in neg], c.co)
	sp = {k: {"key": k, "label": lb, "rows": 0, "items": set(), "value_abs": 0.0} for k, lb in SPLIT_AM}
	ds = []
	for r in neg:
		rate, src = rt[(r.item_code, r.warehouse)]
		v = abs(r.qty) * rate
		k = "tp_xuong" if r.item_code in tp and r.role == "xuong" else "cua_hang" if r.role == "cua_hang" else "khac"
		sp[k]["rows"] += 1
		sp[k]["items"].add(r.item_code)
		sp[k]["value_abs"] += v
		ds.append({"item_code": r.item_code, "short_name": short_name(r.item_name or r.item_code), "kho": c.wh_label(r.warehouse),
			"vai_tro": kho.ROLE_LABELS.get(r.role, r.role), "nhom": k, "qty": round(r.qty, 3), "uom": r.stock_uom,
			"rate": round(rate, 2), "co_gia_von": src is not None, "value_abs": round(v, 2)})
	ds = drop_hidden(sorted(ds, key=lambda x: (-x["value_abs"], x["qty"], x["item_code"], x["kho"])))
	nguon = {}
	for rate, src in rt.values():
		nguon[src or "khong"] = nguon.get(src or "khong", 0) + 1

	# Mức lô: mã TP quản lý lô, mọi kho lá của công ty.
	info = c.tp_info()
	lots = c.tp_lots()
	lo_am = [l for l in lots if l.qty < -LOT_EPS]
	sums: dict = {}
	for l in lots:
		sums[(l.item_code, l.warehouse)] = sums.get((l.item_code, l.warehouse), 0.0) + flt(l.qty)
	binq = {(r.item_code, r.warehouse): r.qty for r in c.bins()
		if r.item_code in tp and info.get(r.item_code) and info[r.item_code].has_batch_no}
	rem = {p: round(flt(binq.get(p)) - sums.get(p, 0.0), 6) for p in set(binq) | set(sums)}
	kl = [v for v in rem.values() if abs(v) > EPS]
	return {
		"available": True,
		"rows": len(neg), "items": len({r.item_code for r in neg}), "warehouses": len({r.warehouse for r in neg}),
		"value_abs": round(sum(x["value_abs"] for x in sp.values()), 2),
		"no_rate_rows": sum(1 for r in neg if rt[(r.item_code, r.warehouse)][1] is None),
		"nguon_gia": nguon,
		"split": [{**x, "items": len(x["items"]), "value_abs": round(x["value_abs"], 2)} for x in sp.values()],
		"lo": {"lo_am": len(lo_am), "lo_am_items": len({l.item_code for l in lo_am}),
			"khong_lo": len(kl), "khong_lo_duong": sum(1 for v in kl if v > 0), "khong_lo_am": sum(1 for v in kl if v < 0)},
		"ds": ds[:TOP_DS], "ds_tong": len(ds),
		"cho_phep_am": {"kho": _stock_flag("allow_negative_stock"), "lo": _stock_flag("allow_negative_stock_for_batch")},
	}
