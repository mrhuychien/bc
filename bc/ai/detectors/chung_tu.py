# -*- coding: utf-8 -*-
"""bc.ai.detectors.chung_tu — detector "chung_tu" (mảng tro-ly, đặc tả §4.3, hợp đồng P2 §3.1): chứng từ bị huỷ nhiều,
chứng từ ghi lùi ngày, bút toán nhập tay lớn. Kết quả vào pack["tro-ly"]["chung_tu"]; quy tắc ct.* ở bc.ai.rules.ks.

Luật chung (dùng lại ở bc.ai.detectors.gia):
- SQL CHỈ SELECT; mọi mốc ngày là THAM SỐ tính từ ctx["today"] (không NOW() / CURDATE()); trung vị tính ở Python.
- "7 ngày" = hôm nay và 6 ngày trước (cửa sổ [today − 6, today], đủ ngày lịch); cột datetime so bằng
  [00:00 của today − 6, 00:00 của today + 1).
- docstatus như _common (1 = đã duyệt, 2 = đã huỷ); chứng từ đầu kỳ (IFNULL(is_opening, 'No') = 'Yes') bị loại ở MỌI
  khối (Stock Entry để is_opening trống mặc định → IFNULL).
- Gói số chỉ có số đếm, số tiền, ngày, mã / tên chứng từ, loại chứng từ, mã hàng và tên khách / NCC đặt dưới khoá
  `customer` / `supplier` (redact.PARTY_KEYS / SUPPLIER_KEYS → mã giả). KHÔNG owner / modified_by / tên người, không
  diễn giải (user_remark, title, remarks — chữ tự do). Payment Entry cho nhân viên (party_type Employee): không nêu
  đối tượng.
- Mỗi khối con tính riêng: lỗi → {"_error": True} (Error Log) — chỉ quy tắc đọc khối đó "không chạy được".

Khối:
- huy (ct.huy_nhieu): chứng từ docstatus 2 của 5 loại (CAC_LOAI) có `modified` (lúc huỷ — chứng từ đã huỷ không sửa
  được nữa) trong 7 ngày → so; nền = cùng cách đếm cho 8 tuần ngay trước cửa sổ ([today − 62, today − 7]) → so_nen,
  so_tuan_nen (8), so_tb_tuan (1 số lẻ, chỉ để đọc — quy tắc so bằng số nguyên). theo_loai [{doctype, loai, so}] giảm
  dần; rows ≤ 20 chứng từ huỷ trong cửa sổ, mới huỷ trước.
- ghi_lui (ct.ghi_lui): chứng từ docstatus 1 của 5 loại TẠO trong 7 ngày (`creation`) có posting_date sớm hơn
  DATE(creation): so_ngay_lui = DATEDIFF(DATE(creation), posting_date) ≥ 1. phan_bo [{so_ngay_lui, so}] (mọi giá trị,
  giảm dần — quy tắc tự đếm theo ngưỡng của nó), so (tổng), rows ≤ 20 lùi xa nhất. Bút toán do hệ thống sinh (như
  but_toan) không tính: không phải người ghi lùi.
- but_toan (ct.but_toan_tay_lon): Journal Entry docstatus 1, posting_date trong 7 ngày, NHẬP TAY = không phải đầu kỳ,
  is_system_generated = 0, không do chứng từ khác sinh (process_deferred_accounting trống, voucher_type ∉ JE_TU_DONG),
  total_debit ≥ nguong (ngưỡng vàng ĐANG ÁP của quy tắc — mặc định + ghi đè BC Settings) → so, gia_tri_tong, rows ≤ 20
  lớn trước. `nguong` nằm trong gói để quy tắc biết gói được lọc theo ngưỡng nào.

Hiệu năng (EXPLAIN): huy lọc theo `modified` — v16 KHÔNG đánh chỉ mục `modified` cho 5 loại này (sort_field creation;
site nâng cấp từ bản cũ có thể còn chỉ mục) → mỗi bảng quét một lượt, mỗi ngày một lần lúc 05:30, chỉ đọc docstatus /
modified (+ ≤ 20 dòng). ghi_lui lọc `creation` (v16 đánh chỉ mục `creation` cho mọi bảng chứng từ) — dải 7 ngày.
but_toan lọc `posting_date` (có chỉ mục trên Journal Entry) — dải 7 ngày.
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import cint, flt, getdate

from bc.ai import registry
from bc.ai.registry import TRO_LY, detector

SO_NGAY = 7            # cửa sổ: hôm nay + 6 ngày trước
SO_TUAN_NEN = 8        # ct.huy_nhieu: nền = 8 tuần trước cửa sổ
DONG_MAX = 20          # số dòng chứng từ tối đa trong gói (= số chứng từ tối đa của Signal.documents)
OPENING = "IFNULL({a}is_opening, 'No') != 'Yes'"

# (DocType, nhãn tiếng Việt, biểu thức số tiền, cột đối tác → khoá gói số)
CAC_LOAI = (
	("Sales Invoice", "hoá đơn bán", "base_grand_total"),
	("Purchase Invoice", "hoá đơn mua", "base_grand_total"),
	("Payment Entry", "phiếu thu chi", "base_paid_amount"),
	("Journal Entry", "bút toán", "total_debit"),
	("Stock Entry", "phiếu kho", "GREATEST(IFNULL(total_outgoing_value, 0), IFNULL(total_incoming_value, 0))"),
)
NHAN = {dt: nhan for dt, nhan, _t in CAC_LOAI}
# Journal Entry do chứng từ / tác vụ khác sinh ra (khấu hao, thanh lý tài sản, đánh giá lại ngoại tệ, chênh lệch tỷ giá,
# phân bổ doanh thu / chi phí trả trước) và bút toán đầu kỳ — không phải "nhập tay".
JE_TU_DONG = ("Opening Entry", "Depreciation Entry", "Asset Disposal", "Exchange Rate Revaluation",
	"Exchange Gain Or Loss", "Deferred Revenue", "Deferred Expense")
JE_TAY = ("IFNULL({a}is_system_generated, 0) = 0 AND IFNULL({a}process_deferred_accounting, '') = '' "
	"AND IFNULL({a}voucher_type, '') NOT IN %(je_tu_dong)s")


# ─── Tiện ích dùng chung (gia.py import) ─────────────────────────────────────
def cua_so(ctx, so_ngay: int = SO_NGAY) -> tuple:
	"""(từ, đến) = (today − (so_ngay − 1), today) — ngày lịch, đủ hai đầu."""
	den = getdate(ctx["today"])
	return den - datetime.timedelta(days=so_ngay - 1), den


def moc(d) -> datetime.datetime:
	"""00:00 của ngày d (so cột datetime: [moc(từ), moc(đến + 1))."""
	return datetime.datetime.combine(getdate(d), datetime.time())


def iso(d):
	return str(getdate(d)) if d else None


def nguong(key: str):
	"""Ngưỡng vàng ĐANG ÁP của quy tắc `key` (mặc định ở @rule + ghi đè BC Settings.ai_rules) — detector lọc gói theo
	đúng ngưỡng quy tắc sẽ dùng trong cùng lượt (quy tắc kiểm lại `nguong` trong gói)."""
	registry.load()
	return registry.Cfg(registry.RULES[key], registry.overrides_from_settings().get(key)).vang


def khoi(ten: str, fn, *args) -> dict:
	"""Một khối con: lỗi → {"_error": True} (Error Log không dữ liệu nghiệp vụ), khối khác vẫn chạy."""
	try:
		return fn(*args)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"bc.ai detector {ten}")
		frappe.clear_last_message()
		return {"_error": True}


def doi_tac(dong: dict, loai: str | None, ten) -> None:
	"""Gắn tên đối tác dưới khoá redact biết (customer / supplier); loại khác (Employee, Shareholder…) → bỏ."""
	ten = str(ten or "").strip()
	if not ten:
		return
	if loai == "Customer":
		dong["customer"] = ten
	elif loai == "Supplier":
		dong["supplier"] = ten


def _co_bang(dt: str) -> bool:
	return bool(frappe.db.table_exists(dt))


def _doi_tac_sql(dt: str) -> str:
	"""(loại, tên) đối tác của chứng từ — chỉ khách / NCC. Tên = TÊN HIỂN THỊ chụp trên chứng từ (trống thì mã hồ sơ),
	như các màn khác của bc; doi_tac() bỏ loại đối tác khác (nhân viên, cổ đông) nên không có tên người."""
	if dt == "Sales Invoice":
		return "'Customer' AS pt, COALESCE(NULLIF(customer_name, ''), customer) AS party"
	if dt == "Purchase Invoice":
		return "'Supplier' AS pt, COALESCE(NULLIF(supplier_name, ''), supplier) AS party"
	if dt == "Payment Entry":
		return "party_type AS pt, COALESCE(NULLIF(party_name, ''), party) AS party"
	return "NULL AS pt, NULL AS party"


def _them_dk(dt: str) -> str:
	"""Điều kiện riêng của loại: Journal Entry chỉ tính bút toán người nhập (JE_TAY)."""
	return (" AND " + JE_TAY.format(a="")) if dt == "Journal Entry" else ""


def _dong(dt: str, r) -> dict:
	d = {"doctype": dt, "loai": NHAN[dt], "name": r.name, "posting_date": iso(r.posting_date),
		"gia_tri": round(flt(r.gia_tri), 2)}
	doi_tac(d, r.pt, r.party)
	return d


# ─── Khối ────────────────────────────────────────────────────────────────────
def _huy(ctx) -> dict:
	tu, den = cua_so(ctx)
	tu_nen = tu - datetime.timedelta(days=7 * SO_TUAN_NEN)
	p = {"den": den, "tu_nen": moc(tu_nen), "het": moc(den + datetime.timedelta(days=1)), "tu": moc(tu),
		"je_tu_dong": JE_TU_DONG}
	so = so_nen = 0
	theo_loai, rows = [], []
	for dt, _nhan, tien in CAC_LOAI:
		if not _co_bang(dt):
			continue
		dem = frappe.db.sql(f"""SELECT FLOOR(DATEDIFF(%(den)s, DATE(modified)) / 7) AS tuan, COUNT(*) AS n
			FROM `tab{dt}` WHERE docstatus = 2 AND modified >= %(tu_nen)s AND modified < %(het)s
				AND {OPENING.format(a='')}{_them_dk(dt)} GROUP BY tuan""", p, as_dict=True)
		n = sum(cint(r.n) for r in dem if cint(r.tuan) == 0)
		so += n
		so_nen += sum(cint(r.n) for r in dem if 1 <= cint(r.tuan) <= SO_TUAN_NEN)
		if n:
			theo_loai.append({"doctype": dt, "loai": NHAN[dt], "so": n})
			for r in frappe.db.sql(f"""SELECT name, posting_date, DATE(modified) AS ngay_huy, {tien} AS gia_tri,
					{_doi_tac_sql(dt)} FROM `tab{dt}`
				WHERE docstatus = 2 AND modified >= %(tu)s AND modified < %(het)s AND {OPENING.format(a='')}{_them_dk(dt)}
				ORDER BY modified DESC, name DESC LIMIT {DONG_MAX}""", p, as_dict=True):
				d = _dong(dt, r)
				d["cancel_date"] = iso(r.ngay_huy)
				rows.append(d)
	theo_loai.sort(key=lambda x: (-x["so"], x["doctype"]))
	rows.sort(key=lambda x: (x["cancel_date"] or "", x["gia_tri"]), reverse=True)
	return {"so": so, "so_nen": so_nen, "so_tuan_nen": SO_TUAN_NEN, "so_tb_tuan": round(so_nen / SO_TUAN_NEN, 1),
		"theo_loai": theo_loai, "rows": rows[:DONG_MAX]}


def _ghi_lui(ctx) -> dict:
	tu, den = cua_so(ctx)
	p = {"tu": moc(tu), "het": moc(den + datetime.timedelta(days=1)), "je_tu_dong": JE_TU_DONG}
	phan_bo: dict = {}
	rows = []
	for dt, _nhan, tien in CAC_LOAI:
		if not _co_bang(dt):
			continue
		dk = (f"docstatus = 1 AND creation >= %(tu)s AND creation < %(het)s AND {OPENING.format(a='')} "
			"AND posting_date < DATE(creation)" + _them_dk(dt))
		for r in frappe.db.sql(f"""SELECT DATEDIFF(DATE(creation), posting_date) AS lui, COUNT(*) AS n
				FROM `tab{dt}` WHERE {dk} GROUP BY lui""", p, as_dict=True):
			phan_bo[cint(r.lui)] = phan_bo.get(cint(r.lui), 0) + cint(r.n)
		for r in frappe.db.sql(f"""SELECT name, posting_date, DATE(creation) AS ngay_tao,
				DATEDIFF(DATE(creation), posting_date) AS lui, {tien} AS gia_tri, {_doi_tac_sql(dt)},
				IFNULL(amended_from, '') != '' AS sua_lai
			FROM `tab{dt}` WHERE {dk} ORDER BY lui DESC, creation DESC LIMIT {DONG_MAX}""", p, as_dict=True):
			d = _dong(dt, r)
			d.update(creation_date=iso(r.ngay_tao), so_ngay_lui=cint(r.lui), sua_lai=bool(cint(r.sua_lai)))
			rows.append(d)
	rows.sort(key=lambda x: (-x["so_ngay_lui"], x["doctype"], x["name"]))
	return {"so": sum(phan_bo.values()), "phan_bo": [{"so_ngay_lui": k, "so": v} for k, v in
		sorted(phan_bo.items(), reverse=True)], "rows": rows[:DONG_MAX]}


def _but_toan(ctx) -> dict:
	tu, den = cua_so(ctx)
	cut = nguong("ct.but_toan_tay_lon")
	p = {"tu": tu, "den": den, "cut": flt(cut), "je_tu_dong": JE_TU_DONG}
	dk = (f"je.docstatus = 1 AND je.posting_date BETWEEN %(tu)s AND %(den)s AND {OPENING.format(a='je.')} "
		f"AND {JE_TAY.format(a='je.')} AND je.total_debit >= %(cut)s")
	tong = frappe.db.sql(f"SELECT COUNT(*) AS n, IFNULL(SUM(je.total_debit), 0) AS t FROM `tabJournal Entry` je "
		f"WHERE {dk}", p, as_dict=True)[0]
	rows = [{"doctype": "Journal Entry", "loai": NHAN["Journal Entry"], "name": r.name,
		"posting_date": iso(r.posting_date), "voucher_type": r.voucher_type, "gia_tri": round(flt(r.gia_tri), 2)}
		for r in frappe.db.sql(f"""SELECT je.name, je.posting_date, je.voucher_type, je.total_debit AS gia_tri
			FROM `tabJournal Entry` je WHERE {dk} ORDER BY je.total_debit DESC, je.name ASC LIMIT {DONG_MAX}""",
			p, as_dict=True)]
	return {"nguong": cut, "so": cint(tong.n), "gia_tri_tong": round(flt(tong.t), 2), "rows": rows}


@detector("chung_tu", section=TRO_LY)
def d_chung_tu(ctx):
	tu, den = cua_so(ctx)
	return {"tu": iso(tu), "den": iso(den), "so_ngay": SO_NGAY,
		"huy": khoi("chung_tu.huy", _huy, ctx), "ghi_lui": khoi("chung_tu.ghi_lui", _ghi_lui, ctx),
		"but_toan": khoi("chung_tu.but_toan", _but_toan, ctx)}
