# -*- coding: utf-8 -*-
"""bc.api.kho_kk — Kiểm kê và điều chỉnh kho (K9–K10, đặc tả Kho bản chốt). Mảng "kiem-ke".

Một lượt get_overview(thang) trả các khối, mỗi khối một safe_block (khối lỗi chỉ tắt khối đó):

K9 — kiểm kê gần nhất theo kho (ảnh chụp hôm nay; kỳ chỉ dùng để đếm số lần kiểm trong tháng):
- kho: phạm vi = kho TP / BTP / xưởng của sx (SX Settings, đúng tên lưu) + mọi kho LÁ BÁN ĐƯỢC đang có tồn
  (|Bin.actual_qty| > 1e-6, gồm kho ngừng dùng còn hàng, kho đi đường có hàng; bỏ kho trả về / cách ly — kho.warehouses).
  · kho sx: phiếu SX Kiem Ke docstatus 1 mới nhất theo (kho, loai) — ORDER BY chot_luc DESC, creation DESC, name DESC;
    ngày hiệu lực = DATE(COALESCE(thoi_diem, chot_luc)) (phiếu chốt sổ lùi D195 hiệu lực ở thoi_diem); loai NULL → TP.
  · kho khác (cửa hàng…): Stock Reconciliation docstatus 1, purpose 'Stock Reconciliation' mới nhất theo dòng kho
    (Stock Reconciliation Item.warehouse), ngày = posting_date ≤ hôm nay. 'Opening Stock' / 'Adjustment Entry' không
    phải lần đếm. Không có → "chưa kiểm kê". Mức: > 30 ngày cảnh báo, > 90 ngày nguy, chưa kiểm kê.
  · kho sx CŨNG đọc Stock Reconciliation (đặc tả chỉ tách nguồn theo kho, không nói bỏ phiếu đếm trên Desk ở kho sx —
    phụ lục A1 coi nó là lần đếm của mọi kho, và K10.2 cùng màn đã tính nó): ngày = lần đếm MỚI NHẤT trong hai nguồn
    (hoà → sx), nguon_ngay cho biết nguồn, ngay_sx / ngay_sr là từng ngày; phieu / cach_dem / dang_dem vẫn của sx.
- dang_dem (KK M2): phiếu SX Kiem Ke nháp (docstatus 0) — tuổi (từ bat_dau_luc, trống thì creation), số ngày im lặng
  (từ dòng đếm cuối), số dòng / số mã đã đếm. Đang đếm lâu = kho vẫn bán / xuất trong lúc đếm.
- huy_chot (KK M6b): phiếu docstatus 2 có ngày hiệu lực (thoi_diem → chot_luc → modified) trong kỳ; "mở lại" = huỷ chốt
  của sx (ghi_chu có "[Huỷ chốt" — chỉ dò ở máy chủ, KHÔNG gửi ghi_chu).
- ira (KK M4): độ chính xác tồn của lần kiểm sx mới nhất mỗi (kho, loai) theo biên bản SX Kiem Ke Lo: mã khớp
  (|Σ chenh| ≤ 1e-6) / mã có sổ hoặc đếm ≠ 0, cộng THEO MÃ (chenh từng lô gồm cả chuyển lô) và BỎ dòng lô đang thu hồi.

K10 — chênh lệch kiểm kê và điều chỉnh trong kỳ (giá trị có dấu = Σ SLE.stock_value_difference, is_cancelled = 0):
1. kk_sx (KK M3): phiếu kho có custom_kiem_ke = lần kiểm (gồm phiếu bù chứng từ ghi lùi D216, remarks bắt đầu
   NHAN_BU), CHỈ dòng sổ ở kk.kho (chuyển lô / đổi cờ lô ở kho khác không tính), chỉ lần kiểm docstatus 1. Kỳ theo
   NGÀY HIỆU LỰC của lần kiểm (C7) — không theo posting_date của phiếu (phiếu bù D216 ghi lùi về giờ chứng từ gốc,
   phiếu chốt sổ lùi ghi ở thoi_diem). Thừa / thiếu xét THEO MÃ sau khi cộng mọi phiếu của lần kiểm (Repack chuyển
   lô ra 0); mã khớp số lượng mà còn giá trị = chênh giá. gt_bu = phần do phiếu bù D216.
2. kk_ch (K10.2): Stock Reconciliation purpose 'Stock Reconciliation', docstatus 1, posting_date trong kỳ, mọi kho của
   công ty. Số lượng chênh = Σ (qty − current_qty) trên dòng phiếu (dòng sổ không lô có actual_qty = 0;
   quantity_difference là varchar); dòng chỉ đổi giá (qty = current_qty) → "đổi giá"; phần còn lại xét thừa / thiếu theo
   (mã, kho) sau khi cộng.
3. don_sx (KK M7): ba loại dọn tồn của sx theo tiền tố remarks (bc.api.sx.ADJUSTMENT_REMARKS), posting_date trong kỳ,
   không mang custom_kiem_ke (cùng phân loại 'don_sx' của nhập–xuất–tồn K3). "Dọn âm lịch sử lô" ≈ 0 → chỉ hiện khi
   đáng kể.
4. xuat_khac (K10.4): −Σ svd của Material Issue không phải kiểm kê / dọn tồn sx / xuất NVL bù nợ BOM (tiêu hao thật) /
   phiếu đầu kỳ, theo stock_entry_type và kho — giữ "Xuất huỷ", "Xuất mẫu" tay.
tong = 1 + 2 + 3 − 4 (chỉ cộng dòng có số; day_du = False khi thiếu dòng). top_lech (KK M5): 10 dòng (mã, kho) chênh
lớn nhất theo |giá trị| trong kỳ, cả kiểm kê sx lẫn cửa hàng (chỉ dòng lệch số lượng). ve_0 (KK M6a): mã TP bị đưa
về 0 vì không đếm (có dòng biên bản, không dòng đếm) trong các lần kiểm sx của kỳ.

Không có sx (chưa cài / thiếu bảng SX Kiem Ke…): K9 chỉ theo Stock Reconciliation, khối sx = {available: False,
reason: 'khong_sx'}; thiếu cột Stock Entry.custom_kiem_ke → kk_sx tắt, xuat_khac bỏ điều kiện đó. Cột thêm ở sx sau
(loai, thoi_diem, cach_dem, bat_dau_luc) đọc qua has_column, thiếu thì mặc định.
Riêng tư: không trả người lập / chốt / đếm, ghi_chu, remarks, owner — chỉ mã phiếu kiểm kê (KK-…), kho, mã hàng. Không
import gì của app sx (chỉ đọc bảng); mốc ngày truyền từ Python; không ký tự % trong SQL (LOCATE, tham số).
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import flt, getdate

from bc.api import kho
from bc.api._common import _guard, carton_factors, drop_hidden, iso, pct, run_cached, safe_block, to_cartons

EPS = kho.EPS
TP_LOAI, BTP_LOAI = "Thành phẩm", "Bán thành phẩm"
KEM_HSD = "Kèm hạn sử dụng"
NHAN_BU = "Bù chứng từ ghi lùi sau kiểm kê (D216)"   # sx api/sau_kiem_ke.py NHAN
THU_HOI = "đang thu hồi"                             # SX Kiem Ke Lo.viec của lô thu hồi (sx_kiem_ke.VIEC["thu_hoi"])
HUY_CHOT = "[Huỷ chốt"                               # ghi_chu do sx api/kiemke.huy_chot thêm (D196)
SR_PURPOSE = "Stock Reconciliation"
SX_KK_TABLES = ("SX Kiem Ke", "SX Kiem Ke Lo", "SX Kiem Ke Dong")
NGUONG_CANH_BAO, NGUONG_NGUY = 30, 90   # số ngày từ lần kiểm gần nhất: > 30 cảnh báo, > 90 nguy
DANG_KE = 1000                          # "Dọn âm lịch sử lô" chỉ hiện khi |giá trị| ≥ 1.000 đ
TOP = 10
# Tiền tố remarks (bc.api.sx.ADJUSTMENT_REMARKS) → (khoá, nhãn).
DON_SX = {
	"Dọn tồn không lô sau bật lô": ("don_khong_lo", "Dọn tồn không lô sau bật lô"),
	"Dọn tồn âm thành phẩm": ("don_am_tp", "Dọn tồn âm thành phẩm"),
	"Dọn âm lịch sử lô (D207)": ("don_am_lo", "Dọn âm lịch sử lô"),
}
LINES = (("kk_sx", "Kiểm kê kho sản xuất"), ("kk_ch", "Kiểm kê cửa hàng"), ("don_sx", "Dọn tồn của sản xuất"),
	("xuat_khac", "Xuất huỷ, xuất mẫu, xuất khác"))


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	"""K9 + K10 của tháng `thang` ('YYYY-MM', mặc định tháng này; cắt ở hôm nay) — xem docstring module.

	{available, meta: {thang, from, to, as_of, prev, sx, kiem_ke_col, nguong}, kho, dang_dem, huy_chot, ira, kk_sx,
	 kk_ch, don_sx, xuat_khac, tong, top_lech, ve_0}
	"""
	_guard("kiem-ke")
	f, t, label = kho.month_period(thang)
	today = kho.today()
	return run_cached("kho_kk.get_overview", {"t": label, "d": iso(today)}, lambda: _build(f, t, label, today), refresh)


def _money(v):
	return round(flt(v), 2)


def _qty(v):
	return round(flt(v), 3)


def _month(d) -> str:
	return f"{d.year:04d}-{d.month:02d}"


# ─── Khung ───────────────────────────────────────────────────────────────────
class _Ctx:
	"""Tham số + dữ liệu đọc chung (ghi nhớ trong lượt; lỗi bước chung chỉ tắt các khối dùng nó)."""

	def __init__(self, f, t, today):
		self.f, self.t, self.today = f, t, today
		self.co = kho.company()
		self.wh = {w.name: w for w in kho.warehouses(self.co)}   # mọi kho của công ty (gồm kho nhóm)
		self.sx = kho.sx_on() and all(frappe.db.table_exists(d) for d in SX_KK_TABLES)
		self.kk_col = kho.has_kiem_ke_col()
		self.sr = frappe.db.table_exists("Stock Reconciliation") and frappe.db.table_exists("Stock Reconciliation Item")
		self._m: dict = {}

	def memo(self, key, fn):
		if key not in self._m:
			self._m[key] = fn()
		return self._m[key]

	def p(self, **kw):
		return {"co": self.co, "f": self.f, "t": self.t, "today": self.today, "tp": TP_LOAI, "eps": EPS, **kw}

	def label(self, w):
		x = self.wh.get(w)
		return x.label if x else w

	def role_label(self, w):
		x = self.wh.get(w)
		return x.role_label if x else kho.ROLE_LABELS["khac"]

	def cols(self) -> dict:
		"""Biểu thức cột SX Kiem Ke (alias kk) — cột thêm ở bản sx sau, thiếu thì giá trị mặc định."""
		def f():
			has = {c: bool(frappe.db.has_column("SX Kiem Ke", c)) for c in ("loai", "thoi_diem", "cach_dem", "bat_dau_luc",
				"ghi_chu")}
			return {
				"loai": "IFNULL(NULLIF(kk.loai, ''), %(tp)s)" if has["loai"] else "%(tp)s",
				"td": "kk.thoi_diem" if has["thoi_diem"] else "NULL",
				"cach": "NULLIF(kk.cach_dem, '')" if has["cach_dem"] else "NULL",
				"bd": "kk.bat_dau_luc" if has["bat_dau_luc"] else "NULL",
				"ghi": "kk.ghi_chu" if has["ghi_chu"] else "NULL",
			}
		return self.memo("cols", f)

	# ── sx: lần kiểm ──
	def sx_last(self) -> list:
		"""Lần kiểm docstatus 1 mới nhất mỗi (kho, loai) của kho công ty + số lần có hiệu lực trong kỳ."""
		def f():
			c = self.cols()
			eff = f"DATE(COALESCE({c['td']}, kk.chot_luc))"
			rows = frappe.db.sql(
				f"""SELECT t.name, t.kho, t.loai, t.cach_dem, t.ngay, t.so_lan FROM (
					SELECT kk.name, kk.kho, {c['loai']} AS loai, {c['cach']} AS cach_dem, {eff} AS ngay,
						SUM({eff} BETWEEN %(f)s AND %(t)s) OVER (PARTITION BY kk.kho, {c['loai']}) AS so_lan,
						ROW_NUMBER() OVER (PARTITION BY kk.kho, {c['loai']}
							ORDER BY kk.chot_luc DESC, kk.creation DESC, kk.name DESC) AS rn
					FROM `tabSX Kiem Ke` kk
					JOIN `tabWarehouse` w ON w.name = kk.kho AND w.company = %(co)s
					WHERE kk.docstatus = 1) t
				WHERE t.rn = 1""", self.p(), as_dict=True)
			for r in rows:
				r.so_lan = int(flt(r.so_lan))
			return rows
		return self.memo("sx_last", f)

	def sx_period(self) -> list:
		"""Lần kiểm docstatus 1 có NGÀY HIỆU LỰC trong kỳ (C7)."""
		def f():
			c = self.cols()
			eff = f"DATE(COALESCE({c['td']}, kk.chot_luc))"
			return frappe.db.sql(
				f"""SELECT kk.name, kk.kho, {c['loai']} AS loai, {eff} AS ngay
				FROM `tabSX Kiem Ke` kk
				JOIN `tabWarehouse` w ON w.name = kk.kho AND w.company = %(co)s
				WHERE kk.docstatus = 1 AND {eff} BETWEEN %(f)s AND %(t)s
				ORDER BY ngay, kk.chot_luc, kk.name""", self.p(), as_dict=True)
		return self.memo("sx_period", f)

	def sx_items(self) -> dict:
		"""{(lần kiểm, mã): {q, v, v_bu}} — sổ kho tại kk.kho của mọi phiếu kho mang custom_kiem_ke của các lần kiểm trong
		kỳ (gồm phiếu bù D216), dòng sổ sống, phiếu kho docstatus 1."""
		def f():
			kks = kho.in_tuple(r.name for r in self.sx_period())
			out: dict = {}
			if kks == ("\x00",):
				return out
			for r in frappe.db.sql(
					"""SELECT se.custom_kiem_ke AS kk, sle.item_code,
						LOCATE(%(nhan)s, IFNULL(se.remarks, '')) = 1 AS la_bu,
						SUM(sle.actual_qty) AS qty, SUM(sle.stock_value_difference) AS val
					FROM `tabStock Entry` se
					JOIN `tabSX Kiem Ke` kk ON kk.name = se.custom_kiem_ke AND kk.docstatus = 1
					JOIN `tabStock Ledger Entry` sle ON sle.voucher_type = 'Stock Entry' AND sle.voucher_no = se.name
						AND sle.is_cancelled = 0 AND sle.warehouse = kk.kho
					WHERE se.docstatus = 1 AND se.custom_kiem_ke IN %(kks)s
					GROUP BY se.custom_kiem_ke, sle.item_code, la_bu""", {"nhan": NHAN_BU, "kks": kks}, as_dict=True):
				x = out.setdefault((r.kk, r.item_code), {"q": 0.0, "v": 0.0, "v_bu": 0.0})
				x["q"] += flt(r.qty)
				x["v"] += flt(r.val)
				if int(flt(r.la_bu)):
					x["v_bu"] += flt(r.val)
			return out
		return self.memo("sx_items", f)

	# ── cửa hàng: Stock Reconciliation trong kỳ ──
	def sr_items(self) -> dict:
		"""{(mã, kho): {q, v, phieu: set}} của phần LỆCH SỐ LƯỢNG + {'doi_gia': [...]} các (phiếu, mã, kho) chỉ đổi giá."""
		def f():
			p = self.p(sr=SR_PURPOSE)
			where = """sr.docstatus = 1 AND sr.company = %(co)s AND sr.purpose = %(sr)s
				AND sr.posting_date BETWEEN %(f)s AND %(t)s"""
			lines = {(r.name, r.item_code, r.warehouse): r for r in frappe.db.sql(
				f"""SELECT sr.name, sri.item_code, sri.warehouse, SUM(sri.qty - sri.current_qty) AS dq,
					SUM(ABS(sri.qty - sri.current_qty) > %(eps)s) AS n_lech
				FROM `tabStock Reconciliation` sr
				JOIN `tabStock Reconciliation Item` sri ON sri.parent = sr.name AND sri.parenttype = 'Stock Reconciliation'
				WHERE {where}
				GROUP BY sr.name, sri.item_code, sri.warehouse""", p, as_dict=True)}
			vals = {(r.name, r.item_code, r.warehouse): flt(r.v) for r in frappe.db.sql(
				f"""SELECT sr.name, sle.item_code, sle.warehouse, SUM(sle.stock_value_difference) AS v
				FROM `tabStock Reconciliation` sr
				JOIN `tabStock Ledger Entry` sle ON sle.voucher_type = 'Stock Reconciliation' AND sle.voucher_no = sr.name
					AND sle.is_cancelled = 0
				WHERE {where}
				GROUP BY sr.name, sle.item_code, sle.warehouse""", p, as_dict=True)}
			agg: dict = {}
			doi_gia = []
			for key in dict.fromkeys([*lines, *vals]):
				ln = lines.get(key)
				v = vals.get(key, 0.0)
				if ln is not None and not int(flt(ln.n_lech)):   # mọi dòng qty = current_qty: chỉ đổi giá
					doi_gia.append({"phieu": key[0], "item_code": key[1], "kho": key[2], "v": v})
					continue
				x = agg.setdefault((key[1], key[2]), {"q": 0.0, "v": 0.0, "phieu": set()})
				x["q"] += flt(ln.dq) if ln is not None else 0.0
				x["v"] += v
				x["phieu"].add(key[0])
			return {"agg": agg, "doi_gia": doi_gia, "phieu": {k[0] for k in [*lines, *vals]}}
		return self.memo("sr_items", f)


def _muc(so_ngay):
	if so_ngay is None:
		return "chua"
	if so_ngay > NGUONG_NGUY:
		return "nguy"
	return "canh_bao" if so_ngay > NGUONG_CANH_BAO else "ok"


def _off(reason: str) -> dict:
	return {"available": False, "reason": reason}


# ─── K9. Kiểm kê gần nhất theo kho ───────────────────────────────────────────
def _kho(c: _Ctx) -> dict:
	scope: dict = {}    # (kho, loai) → lần kiểm sx gần nhất | None
	dang: set = set()   # (kho, loai) đang có phiếu đếm nháp
	if c.sx:
		last = {(r.kho, r.loai): r for r in c.sx_last()}
		for field, loai in (("kho_tp", TP_LOAI), ("kho_btp", BTP_LOAI), ("kho_xuong", BTP_LOAI)):
			w = kho.sx_setting(field)   # kho_xuong trùng kho_btp → cùng khoá, một dòng (sx cac_kho)
			if w and w in c.wh:
				scope[(w, loai)] = last.get((w, loai))
		for key, r in last.items():
			scope.setdefault(key, r)
		dang = {(r["kho"], r["loai"]) for r in _open_rows(c)}
	sx_whs = {w for w, _ in scope}
	holding = {r[0] for r in frappe.db.sql(
		"""SELECT DISTINCT b.warehouse FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %(co)s AND ABS(b.actual_qty) > %(eps)s""", c.p())}
	others = sorted(w for w in holding if w in c.wh and not c.wh[w].is_group and c.wh[w].sellable and w not in sx_whs)
	sr = {}   # kho → Stock Reconciliation đã duyệt mới nhất — MỌI kho của công ty, gồm cả kho sx (kiểm trên Desk)
	if c.sr:
		sr = {r.kho: r for r in frappe.db.sql(
			"""SELECT sri.warehouse AS kho, MAX(sr.posting_date) AS ngay,
				COUNT(DISTINCT CASE WHEN sr.posting_date BETWEEN %(f)s AND %(t)s THEN sr.name END) AS so_lan
			FROM `tabStock Reconciliation` sr
			JOIN `tabStock Reconciliation Item` sri ON sri.parent = sr.name AND sri.parenttype = 'Stock Reconciliation'
			WHERE sr.docstatus = 1 AND sr.company = %(co)s AND sr.purpose = %(sr)s AND sr.posting_date <= %(today)s
			GROUP BY sri.warehouse""", c.p(sr=SR_PURPOSE), as_dict=True)}

	def row(w, nguon, loai, kk):
		"""kk = lần kiểm sx gần nhất của (w, loai) (chỉ dòng sx). Ngày = lần đếm MỚI NHẤT của kho: lần kiểm sx hoặc phiếu
		Stock Reconciliation ở chính kho đó (kho sx kiểm trên Desk vẫn là một lần đếm thật — K10.2 cũng tính nó); hoà ngày
		thì giữ nguồn sx. Số lần trong kỳ = lần kiểm sx + phiếu Stock Reconciliation có ngày trong kỳ."""
		x = c.wh.get(w)
		s = sr.get(w)
		d_sx = getdate(kk.ngay) if kk and kk.ngay else None
		d_sr = getdate(s.ngay) if s and s.ngay else None
		if d_sr and (d_sx is None or d_sr > d_sx):
			ngay, nguon_ngay = d_sr, "sr"
		else:
			ngay, nguon_ngay = d_sx, ("sx" if d_sx else None)
		so_ngay = (c.today - ngay).days if ngay else None
		return {"kho": w, "label": c.label(w), "role": x.role if x else "khac", "role_label": c.role_label(w),
			"disabled": bool(x.disabled) if x else False, "nguon": nguon, "loai": loai,
			"cach_dem": ((kk.cach_dem or KEM_HSD) if kk else None) if nguon == "sx" and loai == TP_LOAI else None,
			"phieu": kk.name if kk else None, "ngay": iso(ngay), "so_ngay": so_ngay, "muc": _muc(so_ngay),
			"nguon_ngay": nguon_ngay, "ngay_sx": iso(d_sx) if nguon == "sx" else None, "ngay_sr": iso(d_sr),
			"so_lan_trong_ky": (int(flt(kk.so_lan)) if kk else 0) + (int(flt(s.so_lan)) if s else 0),
			"dang_dem": ((w, loai) in dang) if nguon == "sx" else None}

	rows = [row(w, "sx", loai, r) for (w, loai), r in scope.items()] + [row(w, "sr", None, None) for w in others]
	order = {k: i for i, k in enumerate(kho.ROLE_ORDER)}
	rows.sort(key=lambda x: (x["so_ngay"] is not None, -(x["so_ngay"] or 0), order.get(x["role"], 99), x["label"],
		x["loai"] or ""))
	return {"available": True, "rows": rows, "sx": c.sx, "tong": {
		"so_kho": len(rows), "chua_kiem": sum(1 for x in rows if x["so_ngay"] is None),
		"qua_30": sum(1 for x in rows if x["so_ngay"] is not None and x["so_ngay"] > NGUONG_CANH_BAO),
		"qua_90": sum(1 for x in rows if x["so_ngay"] is not None and x["so_ngay"] > NGUONG_NGUY)}}


def _open_rows(c: _Ctx) -> list:
	def f():
		k = c.cols()
		rows = frappe.db.sql(
			f"""SELECT kk.name, kk.kho, {k['loai']} AS loai, {k['cach']} AS cach_dem,
				COALESCE({k['bd']}, kk.creation) AS bat_dau, {k['td']} AS thoi_diem,
				IFNULL(d.so_dong, 0) AS so_dong, IFNULL(d.so_ma, 0) AS so_ma, d.dem_cuoi
			FROM `tabSX Kiem Ke` kk
			JOIN `tabWarehouse` w ON w.name = kk.kho AND w.company = %(co)s
			LEFT JOIN (SELECT d.parent, COUNT(*) AS so_dong, COUNT(DISTINCT d.item) AS so_ma, MAX(d.dem_luc) AS dem_cuoi
				FROM `tabSX Kiem Ke Dong` d WHERE d.parenttype = 'SX Kiem Ke' AND d.parentfield = 'dong'
				GROUP BY d.parent) d ON d.parent = kk.name
			WHERE kk.docstatus = 0""", c.p(), as_dict=True)
		out = []
		for r in rows:
			bd = getdate(r.bat_dau) if r.bat_dau else c.today
			cuoi = getdate(r.dem_cuoi) if r.dem_cuoi else bd
			tuoi = (c.today - bd).days
			out.append({"phieu": r.name, "kho": r.kho, "label": c.label(r.kho), "loai": r.loai,
				"cach_dem": (r.cach_dem or KEM_HSD) if r.loai == TP_LOAI else None, "bat_dau": iso(bd),
				"thoi_diem": iso(r.thoi_diem) if r.thoi_diem else None, "tuoi": tuoi, "im_lang": (c.today - cuoi).days,
				"so_dong": int(flt(r.so_dong)), "so_ma": int(flt(r.so_ma)), "cu": tuoi >= 2})
		out.sort(key=lambda x: (-x["tuoi"], x["label"], x["phieu"]))
		return out
	return c.memo("open", f)


def _dang_dem(c: _Ctx) -> dict:
	if not c.sx:
		return _off("khong_sx")
	rows = _open_rows(c)
	return {"available": True, "rows": rows, "so_phieu": len(rows), "cu": sum(1 for x in rows if x["cu"])}


def _huy_chot(c: _Ctx) -> dict:
	if not c.sx:
		return _off("khong_sx")
	k = c.cols()
	eff = f"DATE(COALESCE({k['td']}, kk.chot_luc, kk.modified))"
	rows = frappe.db.sql(
		f"""SELECT kk.name, kk.kho, {k['loai']} AS loai, {eff} AS ngay,
			LOCATE(%(huy)s, IFNULL({k['ghi']}, '')) > 0 AS mo_lai
		FROM `tabSX Kiem Ke` kk
		JOIN `tabWarehouse` w ON w.name = kk.kho AND w.company = %(co)s
		WHERE kk.docstatus = 2 AND {eff} BETWEEN %(f)s AND %(t)s
		ORDER BY ngay, kk.name""", c.p(huy=HUY_CHOT), as_dict=True)
	out = [{"phieu": r.name, "kho": r.kho, "label": c.label(r.kho), "loai": r.loai, "ngay": iso(r.ngay),
		"mo_lai": bool(int(flt(r.mo_lai)))} for r in rows]
	return {"available": True, "rows": out, "so_phieu": len(out), "so_mo_lai": sum(1 for x in out if x["mo_lai"])}


def _ira(c: _Ctx) -> dict:
	if not c.sx:
		return _off("khong_sx")
	last = c.sx_last()
	kks = kho.in_tuple(r.name for r in last)
	per: dict = {}
	if kks != ("\x00",):
		for r in frappe.db.sql(
				"""SELECT l.parent AS kk, l.item,
					SUM(CASE WHEN LOCATE(%(th)s, IFNULL(l.viec, '')) = 0 THEN l.so_truoc ELSE 0 END) AS so_sach,
					SUM(CASE WHEN LOCATE(%(th)s, IFNULL(l.viec, '')) = 0 THEN l.so_sau ELSE 0 END) AS dem,
					SUM(CASE WHEN LOCATE(%(th)s, IFNULL(l.viec, '')) = 0 THEN l.chenh ELSE 0 END) AS lech
				FROM `tabSX Kiem Ke Lo` l
				WHERE l.parenttype = 'SX Kiem Ke' AND l.parentfield = 'lo' AND l.parent IN %(kks)s
				GROUP BY l.parent, l.item""", {"th": THU_HOI, "kks": kks}, as_dict=True):
			if abs(flt(r.so_sach)) <= EPS and abs(flt(r.dem)) <= EPS:
				continue                                  # chỉ có lô đang thu hồi / không sổ không đếm
			x = per.setdefault(r.kk, [0, 0])
			x[0] += 1
			x[1] += 1 if abs(flt(r.lech)) <= EPS else 0
	rows = []
	for r in sorted(last, key=lambda x: (c.label(x.kho), x.loai)):
		n, khop = per.get(r.name, (0, 0))
		rows.append({"phieu": r.name, "kho": r.kho, "label": c.label(r.kho), "loai": r.loai, "ngay": iso(r.ngay),
			"so_ma": n, "so_ma_khop": khop, "ty_le": pct(khop, n)})
	n = sum(x["so_ma"] for x in rows)
	khop = sum(x["so_ma_khop"] for x in rows)
	return {"available": True, "rows": rows, "so_ma": n, "so_ma_khop": khop, "ty_le": pct(khop, n)}


# ─── K10. Chênh lệch kiểm kê và điều chỉnh trong kỳ ─────────────────────────
def _qty_sum(qty_by_item: dict, info: dict, factors: dict):
	"""{qty, uom, cartons, boxes_without_carton_factor} của các mã CÙNG đơn vị (|số lượng|), lẫn đơn vị → None."""
	if not qty_by_item:
		return None
	uoms = {(info.get(i) or {}).get("stock_uom") for i in qty_by_item}
	if len(uoms) != 1:
		return None
	ct = kho.carton_total({i: abs(q) for i, q in qty_by_item.items()}, factors)
	return {"qty": _qty(sum(abs(q) for q in qty_by_item.values())), "uom": uoms.pop(), "cartons": ct["cartons"],
		"boxes_without_carton_factor": ct["boxes_without_carton_factor"]}


def _kk_sx(c: _Ctx) -> dict:
	if not c.sx:
		return _off("khong_sx")
	if not c.kk_col:
		return _off("thieu_cot")
	counts = c.sx_period()
	items = c.sx_items()
	codes = {i for _, i in items}
	info = kho.item_info(codes)
	factors = carton_factors(codes)
	rows = []
	for k in counts:
		r = {"phieu": k.name, "kho": k.kho, "label": c.label(k.kho), "loai": k.loai, "ngay": iso(k.ngay),
			"gt_thua": 0.0, "gt_thieu": 0.0, "gt_chenh_gia": 0.0, "gt_rong": 0.0, "gt_bu": 0.0,
			"so_ma_thua": 0, "so_ma_thieu": 0, "so_ma_gia_0": 0}
		thua, thieu = {}, {}
		for (kk, item), x in items.items():
			if kk != k.name:
				continue
			r["gt_rong"] += x["v"]
			r["gt_bu"] += x["v_bu"]
			if x["q"] > EPS:
				r["gt_thua"] += x["v"]
				r["so_ma_thua"] += 1
				thua[item] = x["q"]
			elif x["q"] < -EPS:
				r["gt_thieu"] += x["v"]
				r["so_ma_thieu"] += 1
				thieu[item] = x["q"]
			else:
				r["gt_chenh_gia"] += x["v"]
			if abs(x["q"]) > EPS and abs(x["v"]) < 1:
				r["so_ma_gia_0"] += 1                   # nhập / xuất giá 0 (allow_zero_valuation_rate): lệch số, không tiền
		r["thua"], r["thieu"] = _qty_sum(thua, info, factors), _qty_sum(thieu, info, factors)
		rows.append(r)
	tong = {k: _money(sum(r[k] for r in rows)) for k in ("gt_thua", "gt_thieu", "gt_chenh_gia", "gt_rong", "gt_bu")}
	for r in rows:
		for k in ("gt_thua", "gt_thieu", "gt_chenh_gia", "gt_rong", "gt_bu"):
			r[k] = _money(r[k])
	huy = frappe.db.sql(
		"""SELECT COUNT(*) AS n, COUNT(DISTINCT se.custom_kiem_ke) AS kk
		FROM `tabStock Entry` se
		JOIN `tabSX Kiem Ke` kk ON kk.name = se.custom_kiem_ke AND kk.docstatus = 1
		JOIN `tabWarehouse` w ON w.name = kk.kho AND w.company = %(co)s
		WHERE se.docstatus = 2 AND LOCATE(%(nhan)s, IFNULL(se.remarks, '')) != 1""", c.p(nhan=NHAN_BU), as_dict=True)[0]
	return {"available": True, "so_lan": len(rows), **tong,
		"so_ma_thua": sum(r["so_ma_thua"] for r in rows), "so_ma_thieu": sum(r["so_ma_thieu"] for r in rows),
		"so_ma_gia_0": sum(r["so_ma_gia_0"] for r in rows), "rows": rows,
		"phieu_huy_le": {"so_phieu": int(flt(huy.n)), "so_kiem_ke": int(flt(huy.kk))}}


def _kk_ch(c: _Ctx) -> dict:
	if not c.sr:
		return _off("thieu_bang")
	d = c.sr_items()
	by: dict = {}

	def wrow(w):
		return by.setdefault(w, {"kho": w, "label": c.label(w), "role_label": c.role_label(w), "phieu": set(),
			"gt_thua": 0.0, "gt_thieu": 0.0, "gt_doi_gia": 0.0, "so_ma_thua": 0, "so_ma_thieu": 0})

	for (item, w), x in d["agg"].items():
		r = wrow(w)
		r["phieu"] |= x["phieu"]
		if x["q"] > EPS:
			r["gt_thua"] += x["v"]
			r["so_ma_thua"] += 1
		elif x["q"] < -EPS:
			r["gt_thieu"] += x["v"]
			r["so_ma_thieu"] += 1
		else:
			r["gt_doi_gia"] += x["v"]                   # số lượng cộng lại khớp: còn lại là chênh giá
	for x in d["doi_gia"]:
		r = wrow(x["kho"])
		r["phieu"].add(x["phieu"])
		r["gt_doi_gia"] += x["v"]
	rows = []
	for r in by.values():
		r["so_phieu"] = len(r.pop("phieu"))
		for k in ("gt_thua", "gt_thieu", "gt_doi_gia"):
			r[k] = _money(r[k])
		r["gt_rong"] = _money(r["gt_thua"] + r["gt_thieu"] + r["gt_doi_gia"])
		rows.append(r)
	rows.sort(key=lambda x: (-abs(x["gt_rong"]), x["label"]))
	tong = {k: _money(sum(r[k] for r in rows)) for k in ("gt_thua", "gt_thieu", "gt_doi_gia")}
	return {"available": True, **tong, "gt_rong": _money(sum(tong.values())), "so_phieu": len(d["phieu"]),
		"so_kho": len(rows), "so_ma_thua": sum(r["so_ma_thua"] for r in rows),
		"so_ma_thieu": sum(r["so_ma_thieu"] for r in rows), "so_dong_doi_gia": len(d["doi_gia"]), "rows": rows}


def _don_sx(c: _Ctx) -> dict:
	if not c.sx:
		return _off("khong_sx")
	from bc.api.sx import ADJUSTMENT_REMARKS
	p = c.p(**kho.adjust_params())
	n = len(ADJUSTMENT_REMARKS)
	case = " ".join(f"WHEN LOCATE(%(a{i})s, IFNULL(se.remarks, '')) = 1 THEN {i}" for i in range(1, n + 1))
	anyp = " OR ".join(f"LOCATE(%(a{i})s, IFNULL(se.remarks, '')) = 1" for i in range(1, n + 1))
	no_kk = "AND IFNULL(se.custom_kiem_ke, '') = ''" if c.kk_col else ""
	rows = frappe.db.sql(
		f"""SELECT se.name, CASE {case} END AS k, SUM(sle.stock_value_difference) AS val
		FROM `tabStock Entry` se
		JOIN `tabStock Ledger Entry` sle ON sle.voucher_type = 'Stock Entry' AND sle.voucher_no = se.name
			AND sle.is_cancelled = 0
		WHERE se.docstatus = 1 AND se.company = %(co)s AND se.posting_date BETWEEN %(f)s AND %(t)s
			AND ({anyp}) {no_kk}
		GROUP BY se.name, k""", p, as_dict=True)
	kinds = {}
	for i, prefix in enumerate(ADJUSTMENT_REMARKS, 1):
		key, label = DON_SX.get(prefix, (f"a{i}", prefix))
		kinds[i] = {"key": key, "label": label, "gia_tri": 0.0, "phieu": set()}
	for r in rows:
		x = kinds[int(flt(r.k))]
		x["gia_tri"] += flt(r.val)
		x["phieu"].add(r.name)
	out = []
	for x in kinds.values():
		x["so_phieu"] = len(x.pop("phieu"))
		x["gia_tri"] = _money(x["gia_tri"])
		x["hien"] = x["key"] != "don_am_lo" or abs(x["gia_tri"]) >= DANG_KE
		out.append(x)
	return {"available": True, "gia_tri": _money(sum(x["gia_tri"] for x in out)),
		"so_phieu": len({r.name for r in rows}), "rows": out}


def _xuat_khac(c: _Ctx) -> dict:
	p = c.p(**kho.adjust_params())
	rows = frappe.db.sql(
		f"""SELECT se.name, COALESCE(NULLIF(se.stock_entry_type, ''), se.purpose) AS loai, sle.warehouse,
			-SUM(sle.stock_value_difference) AS gia_tri
		FROM `tabStock Entry` se
		JOIN `tabStock Ledger Entry` sle ON sle.voucher_type = 'Stock Entry' AND sle.voucher_no = se.name
			AND sle.is_cancelled = 0
		WHERE se.docstatus = 1 AND se.company = %(co)s AND se.purpose = 'Material Issue'
			AND se.posting_date BETWEEN %(f)s AND %(t)s
			AND IFNULL(se.is_opening, 'No') != 'Yes'
			AND NOT {kho.is_adjust_sql('se')}
			AND LOCATE(%(p_bu_bom)s, IFNULL(se.remarks, '')) != 1
		GROUP BY se.name, loai, sle.warehouse""", p, as_dict=True)
	by: dict = {}
	for r in rows:
		t = by.setdefault(r.loai, {"loai": r.loai, "label": "Xuất kho (không ghi loại)" if r.loai == "Material Issue"
			else r.loai, "gia_tri": 0.0, "phieu": set(), "kho": {}})
		t["gia_tri"] += flt(r.gia_tri)
		t["phieu"].add(r.name)
		w = t["kho"].setdefault(r.warehouse, {"kho": r.warehouse, "label": c.label(r.warehouse), "gia_tri": 0.0,
			"phieu": set()})
		w["gia_tri"] += flt(r.gia_tri)
		w["phieu"].add(r.name)
	out = []
	for t in by.values():
		ws = []
		for w in t["kho"].values():
			w["so_phieu"] = len(w.pop("phieu"))
			w["gia_tri"] = _money(w["gia_tri"])
			ws.append(w)
		ws.sort(key=lambda x: (-x["gia_tri"], x["label"]))
		out.append({"loai": t["loai"], "label": t["label"], "gia_tri": _money(t["gia_tri"]), "so_phieu": len(t["phieu"]),
			"kho": ws})
	out.sort(key=lambda x: (-x["gia_tri"], x["label"]))
	return {"available": True, "gia_tri": _money(sum(x["gia_tri"] for x in out)),
		"so_phieu": len({r.name for r in rows}), "rows": out}


def _tong(parts: dict) -> dict:
	"""Tổng điều chỉnh = kiểm kê sx + kiểm kê cửa hàng + dọn tồn sx − xuất khác (dòng nào không có số thì bỏ)."""
	out = []
	for key, label in LINES:
		b = parts.get(key) or {}
		if not b.get("available"):
			out.append({"key": key, "label": label, "available": False, "gia_tri": None})
			continue
		v = b["gt_rong"] if key in ("kk_sx", "kk_ch") else b["gia_tri"]
		out.append({"key": key, "label": label, "available": True, "gia_tri": _money(-v if key == "xuat_khac" else v)})
	have = [x for x in out if x["available"]]
	return {"available": bool(have), "gia_tri": _money(sum(x["gia_tri"] for x in have)) if have else None,
		"day_du": len(have) == len(out), "parts": out}


def _top_lech(c: _Ctx, kk_sx: dict, kk_ch: dict) -> dict:
	rows = []
	if kk_sx.get("available"):
		kho_of = {k.name: k.kho for k in c.sx_period()}
		for (kk, item), x in c.sx_items().items():
			if abs(x["q"]) > EPS:
				rows.append({"item_code": item, "kho": kho_of.get(kk), "nguon": "sx", "phieu": kk, "q": x["q"], "v": x["v"]})
	if kk_ch.get("available"):
		for (item, w), x in c.sr_items()["agg"].items():
			if abs(x["q"]) > EPS:
				rows.append({"item_code": item, "kho": w, "nguon": "cua_hang", "phieu": None, "q": x["q"], "v": x["v"]})
	if not (kk_sx.get("available") or kk_ch.get("available")):
		return _off("khong_nguon")
	rows = drop_hidden(rows)
	rows.sort(key=lambda x: (-abs(x["v"]), -abs(x["q"]), x["item_code"], x["kho"] or ""))
	rows = rows[:TOP]
	info = kho.item_info(x["item_code"] for x in rows)
	factors = carton_factors({x["item_code"] for x in rows})
	out = []
	for x in rows:
		i = info.get(x["item_code"]) or frappe._dict()
		f = factors.get(x["item_code"])
		out.append({"item_code": x["item_code"], "item_name": i.item_name or x["item_code"],
			"short_name": i.short_name or x["item_code"], "kho": x["kho"], "kho_label": c.label(x["kho"]),
			"nguon": x["nguon"], "phieu": x["phieu"], "qty": _qty(x["q"]), "uom": i.stock_uom,
			"cartons": to_cartons(x["q"], f) if f else None, "value": _money(x["v"]), "gia_0": abs(x["v"]) < 1})
	return {"available": True, "rows": out}


def _ve_0(c: _Ctx, kk_sx: dict) -> dict:
	"""KK M6a: mã TP về 0 vì không đếm (có dòng biên bản lô, không có dòng đếm) trong các lần kiểm sx của kỳ."""
	if not c.sx:
		return _off("khong_sx")
	counts = {k.name: k for k in c.sx_period()}
	kks = kho.in_tuple(counts)
	rows = []
	if kks != ("\x00",):
		rows = frappe.db.sql(
			"""SELECT l.parent AS kk, l.item, SUM(l.so_truoc) AS so_sach
			FROM `tabSX Kiem Ke Lo` l
			WHERE l.parenttype = 'SX Kiem Ke' AND l.parentfield = 'lo' AND l.parent IN %(kks)s
				AND LOCATE(%(th)s, IFNULL(l.viec, '')) = 0
				AND NOT EXISTS (SELECT 1 FROM `tabSX Kiem Ke Dong` d WHERE d.parent = l.parent
					AND d.parenttype = 'SX Kiem Ke' AND d.parentfield = 'dong' AND d.item = l.item)
			GROUP BY l.parent, l.item
			HAVING ABS(SUM(l.so_sau)) < %(eps)s AND SUM(l.so_truoc) > %(eps)s""",
			{"kks": kks, "th": THU_HOI, "eps": EPS}, as_dict=True)
	vals = c.sx_items() if kk_sx.get("available") else None
	info = kho.item_info(r.item for r in rows)
	out = []
	for r in rows:
		i = info.get(r.item) or frappe._dict()
		v = (vals.get((r.kk, r.item)) or {}).get("v", 0.0) if vals is not None else None
		out.append({"phieu": r.kk, "kho": counts[r.kk].kho, "kho_label": c.label(counts[r.kk].kho), "item_code": r.item,
			"item_name": i.item_name or r.item, "short_name": i.short_name or r.item, "so_luong": _qty(r.so_sach),
			"uom": i.stock_uom, "gia_tri": _money(v) if v is not None else None})
	gia_tri = _money(sum(x["gia_tri"] for x in out)) if vals is not None else None
	shown = drop_hidden(out)
	shown.sort(key=lambda x: (x["gia_tri"] or 0, -x["so_luong"], x["item_code"]))
	return {"available": True, "so_ma": len(out), "gia_tri": gia_tri, "rows": shown[:TOP * 2]}


# ─── Dựng payload ────────────────────────────────────────────────────────────
def _build(f, t, label, today):
	prev = f - datetime.timedelta(days=1)
	meta = {"thang": label, "from": iso(f), "to": iso(t), "as_of": iso(today), "prev": _month(prev),
		"nguong": {"canh_bao": NGUONG_CANH_BAO, "nguy": NGUONG_NGUY}}
	try:
		c = _Ctx(f, t, today)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc.kho_kk.context")
		return {"available": False, "meta": meta}
	meta.update({"sx": bool(c.sx), "kiem_ke_col": bool(c.kk_col)})
	out = {"available": True, "meta": meta,
		"kho": safe_block("kho_kk.kho", _kho, c),
		"dang_dem": safe_block("kho_kk.dang_dem", _dang_dem, c),
		"huy_chot": safe_block("kho_kk.huy_chot", _huy_chot, c),
		"ira": safe_block("kho_kk.ira", _ira, c),
		"kk_sx": safe_block("kho_kk.kk_sx", _kk_sx, c),
		"kk_ch": safe_block("kho_kk.kk_ch", _kk_ch, c),
		"don_sx": safe_block("kho_kk.don_sx", _don_sx, c),
		"xuat_khac": safe_block("kho_kk.xuat_khac", _xuat_khac, c)}
	out["tong"] = safe_block("kho_kk.tong", _tong, out)
	out["top_lech"] = safe_block("kho_kk.top_lech", _top_lech, c, out["kk_sx"], out["kk_ch"])
	out["ve_0"] = safe_block("kho_kk.ve_0", _ve_0, c, out["kk_sx"])
	return out
