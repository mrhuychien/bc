# -*- coding: utf-8 -*-
"""bc.api.vc — Vận chuyển cho Ban lãnh đạo, đọc mềm app vanchuyen (+ phiếu kiểm thu hồi của ketoan).

Một lượt gọi get_overview(thang) trả 6 khối, khối nào thiếu bảng / cột thì `available: False`:
- giao: đơn trong kỳ theo hình thức × trạng thái vận chuyển (SI docstatus=1, không trả, bỏ đúng nhóm
  'Showroom' như vanchuyen.tong_quan, loại hoá đơn đầu kỳ như mọi số doanh số của bc), giao được ngay lần
  đầu; ẢNH CHỤP hôm nay (mọi tháng, ≤ 180 ngày, như pool điều phối): đơn chờ giao quá N ngày và đơn Tự vận
  chuyển chưa xếp chuyến (tính theo dòng chuyến như chuyen_xe.da_xep — reconcile chỉ chạy lúc submit nên
  cột custom_trang_thai_xep trễ với chuyến nháp).
- chuyen: chuyến theo ngày giao (kế hoạch), đơn/chuyến, tải theo m³ có trọng số (bỏ xe chưa khai sức chứa).
- cuoc: chỉ chuyến docstatus=1 (như chi_cuoc); % = cước / doanh thu đã giao, CẢ HAI trên chuyến đã hoàn
  thành (doanh thu chia theo kiện, trước VAT). Tháng < K lái xe: không hiện tiền (cước = thu nhập lái xe).
- su_co, thu_hoi (chặng tổng = phiếu kiểm ketoan nếu có, như vanchuyen/ketoan api.thu_hoi), xe (gọi helper
  thuần nhat_ky_xe.lich_cua_xe / bao_duong_moi_nhat).
Không trả tên lái xe, SĐT, tên khách / người liên hệ, ghi chú tự do (chỉ số tổng hợp). Biển số xe là tài sản
công ty nên được hiện. Không gọi whitelisted method nào của vanchuyen/ketoan (đều guard theo phiên).
Cột thêm ở bản vanchuyen sau (nhóm hàng-về, cước) đọc qua _cot; mỗi khối chạy trong safe_block.
"""

from __future__ import annotations

import calendar
import datetime
import re

import frappe
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

from bc.api._common import (K_AN_DANH, OPENING_FILTER, SI_AMOUNT, _guard, iso, pct, real_column, run_cached,
	safe_block)

CHO_QUA_NGAY = 3        # đơn chưa giao quá N ngày từ ngày hoá đơn → "chờ giao quá hạn"
CHO_TU_NGAY = 180       # không xét đơn cũ hơn (trạng thái hãng ngoài nhập tay, hay bị bỏ quên)
SU_CO_QUA_NGAY = 7      # sự cố mở quá N ngày
EPS = 0.001             # = chuyen_xe.EPS
SHOWROOM = "Showroom"   # vanchuyen loại đúng nhóm này (tong_quan.py, dieu_hanh.py)
DA_GIAO_SI = ("Đã giao hàng, chụp chứng từ", "Đã nộp chứng từ")
DANG_GIAO_SI = ("Đang giao hàng",)
CHUA_PHAN_CONG = "Chưa phân công"
TU_VAN_CHUYEN = "Tự vận chuyển"
TT_GIAO = ("Đã giao", "Khách hẹn", "Hoàn")  # trạng thái cuối của một dòng chuyến (api/lai_xe.py)
SC_DONG = ("Đã xử lý", "Đóng")
CHANG = ("Tạo yêu cầu", "Đã lấy hàng", "Đã nhận hàng", "Hủy tại chỗ", "Đang kiểm", "Đã kiểm hàng",
	"Đã nhập chứng từ", "Xong", "Đã hủy")
_THANG = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


col = real_column  # tên cột thật (NFC trước, NFD sau) hoặc None


def _has(*doctypes) -> bool:
	return all(frappe.db.table_exists(d) for d in doctypes)


def _cot(dt: str, field: str, alias: str = "", default: str = "NULL") -> str:
	"""Cột tuỳ chọn (thêm ở bản vanchuyen sau bảng — vd nhóm hàng-về, cước): có thì `alias.field`, không có
	thì giá trị mặc định — bản vanchuyen cũ chỉ mất chỉ số đó, không vỡ cả khối (như ketoan mt_hoan._sc_col)."""
	return f"{alias + '.' if alias else ''}`{field}`" if frappe.db.has_column(dt, field) else default


def period(thang=None) -> tuple:
	"""(từ, đến, nhãn 'YYYY-MM'): tháng chọn (mặc định tháng này), cắt ở hôm nay."""
	today = getdate(nowdate())
	t = str(thang or "")[:7]
	if not _THANG.match(t) or getdate(f"{t}-01") > today:
		t = f"{today.year:04d}-{today.month:02d}"
	y, m = int(t[:4]), int(t[5:])
	f = datetime.date(y, m, 1)
	e = datetime.date(y, m, calendar.monthrange(y, m)[1])
	return f, min(e, today), t


def _scope(st: str, ht: str) -> str:
	"""Đơn trong kỳ — alias si; tham số %(f)s %(t)s %(showroom)s."""
	return f"""si.docstatus = 1 AND si.is_return = 0 AND {OPENING_FILTER}
		AND COALESCE(si.customer_group, '') != %(showroom)s AND si.posting_date BETWEEN %(f)s AND %(t)s"""


def _cho(st: str) -> str:
	"""ẢNH CHỤP hôm nay: đơn chưa giao xong, mọi tháng trong CHO_TU_NGAY ngày — alias si; tham số %(floor)s
	%(today)s %(showroom)s %(da_giao)s. Như pool điều phối của vanchuyen (không giới hạn tháng)."""
	return f"""si.docstatus = 1 AND si.is_return = 0 AND {OPENING_FILTER}
		AND COALESCE(si.customer_group, '') != %(showroom)s AND COALESCE(si.`{st}`, '') NOT IN %(da_giao)s
		AND si.posting_date BETWEEN %(floor)s AND %(today)s"""


def _rollup(st: str | None) -> str:
	if st in DA_GIAO_SI:
		return "da"
	if st in DANG_GIAO_SI:
		return "dang"
	return "cho"


# ─── 1. Giao hàng ────────────────────────────────────────────────────────────
def _giao(p: dict, today) -> dict:
	st, ht = col("Sales Invoice", "custom_trạng_thái_vận_chuyển"), col("Sales Invoice", "custom_hình_thức_vận_chuyển")
	if not (st and ht):
		return {"available": False}
	scope = _scope(st, ht)
	rows = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(si.`{st}`, ''), 'Chờ xử lý') AS st,
			COALESCE(NULLIF(si.`{ht}`, ''), %(cpc)s) AS ht,
			COUNT(*) AS n, COALESCE(SUM({SI_AMOUNT}), 0) AS gt
		FROM `tabSales Invoice` si WHERE {scope}
		GROUP BY st, ht""", {**p, "cpc": CHUA_PHAN_CONG}, as_dict=True)
	by: dict = {}
	for r in rows:
		h = by.setdefault(r.ht, {"hinh_thuc": r.ht, "n": 0, "gt": 0.0, "cho": 0, "dang": 0, "da": 0})
		h["n"] += cint(r.n)
		h["gt"] += flt(r.gt)
		h[_rollup(r.st)] += cint(r.n)
	types = sorted(by.values(), key=lambda x: (x["hinh_thuc"] == CHUA_PHAN_CONG, -x["n"]))
	total = sum(x["n"] for x in types)
	da = sum(x["da"] for x in types)
	out = {
		"available": True,
		"total": total, "value": round(sum(x["gt"] for x in types), 2),
		"cho": sum(x["cho"] for x in types), "dang": sum(x["dang"] for x in types), "da": da,
		"ty_le_giao": pct(da, total),
		"ty_le_phan_cong": pct(total - by.get(CHUA_PHAN_CONG, {}).get("n", 0), total),
		"by_type": [{**x, "gt": round(x["gt"], 2), "ty_le_giao": pct(x["da"], x["n"])} for x in types],
	}
	# Đơn chờ giao quá N ngày + xếp chuyến — ẢNH CHỤP hôm nay (mọi tháng), không theo kỳ chọn.
	ps = {**p, "today": today, "floor": getdate(add_days(today, -CHO_TU_NGAY)), "da_giao": DA_GIAO_SI}
	cho = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(si.`{ht}`, ''), %(cpc)s) AS ht, COUNT(*) AS cho,
			SUM(DATEDIFF(%(today)s, si.posting_date) > %(n)s) AS qua_n
		FROM `tabSales Invoice` si WHERE {_cho(st)}
		GROUP BY ht""", {**ps, "cpc": CHUA_PHAN_CONG, "n": CHO_QUA_NGAY}, as_dict=True)
	out["cho_qua_han"] = {"so_ngay": CHO_QUA_NGAY, "tu_ngay": CHO_TU_NGAY,
		"rows": sorted(({"hinh_thuc": r.ht, "cho": cint(r.cho), "qua_n": cint(r.qua_n)} for r in cho),
			key=lambda x: -x["qua_n"]),
		"qua_n": sum(cint(r.qua_n) for r in cho)}
	out["xep"] = _xep(ps, st, ht) if _has("Chuyen Xe", "Chuyen Xe Don Hang") else None
	out["lan_dau"] = _lan_dau(p) if _has("Chuyen Xe", "Chuyen Xe Don Hang") else None
	return out


def _xep(p: dict, st: str, ht: str) -> dict:
	"""Đơn Tự vận chuyển chưa giao (ảnh chụp như `_cho`): chưa xếp / một phần / đã xếp — như pool điều phối
	và chuyen_xe.da_xep, gom 1 SQL."""
	kien = col("Sales Invoice", "custom_tổng_kiện")
	tong = f"COALESCE(si.`{kien}`, 0)" if kien else "0"
	rows = frappe.db.sql(
		f"""
		SELECT {tong} AS tong, COALESCE(h.held, 0) AS held, COALESCE(h.n_trip, 0) AS n_trip
		FROM `tabSales Invoice` si
		LEFT JOIN (
			SELECT cxd.sales_invoice, SUM(cxd.so_kien) AS held, COUNT(DISTINCT cx.name) AS n_trip
			FROM `tabChuyen Xe Don Hang` cxd
			JOIN `tabChuyen Xe` cx ON cx.name = cxd.parent AND cxd.parenttype = 'Chuyen Xe'
			WHERE cx.docstatus < 2 AND NOT (cx.trang_thai = 'Hoàn thành' AND cxd.trang_thai_giao != 'Đã giao')
			GROUP BY cxd.sales_invoice
		) h ON h.sales_invoice = si.name
		WHERE {_cho(st)} AND si.`{ht}` = %(tvc)s""", {**p, "tvc": TU_VAN_CHUYEN}, as_dict=True)
	out = {"chua_xep": 0, "mot_phan": 0, "da_xep": 0}
	for r in rows:
		t, h = flt(r.tong), flt(r.held)
		if t <= 0:  # lô nguyên (không có số kiện): có chuyến giữ là đã xếp
			out["da_xep" if cint(r.n_trip) else "chua_xep"] += 1
		elif h <= EPS:
			out["chua_xep"] += 1
		elif t - h > EPS:
			out["mot_phan"] += 1
		else:
			out["da_xep"] += 1
	return out


def _lan_dau(p: dict) -> dict:
	"""Giao được ngay lần đầu: dòng chuyến KẾT THÚC đầu tiên của mỗi đơn (theo ngày giao) là 'Đã giao'."""
	rows = frappe.db.sql(
		"""
		SELECT x.tt, COUNT(*) AS n FROM (
			SELECT cxd.sales_invoice, cxd.trang_thai_giao AS tt, cx.ngay_giao,
				ROW_NUMBER() OVER (PARTITION BY cxd.sales_invoice ORDER BY cx.ngay_giao, cx.creation) AS rn
			FROM `tabChuyen Xe Don Hang` cxd
			JOIN `tabChuyen Xe` cx ON cx.name = cxd.parent AND cxd.parenttype = 'Chuyen Xe'
			WHERE cx.docstatus = 1 AND cxd.trang_thai_giao IN %(tt)s
		) x
		WHERE x.rn = 1 AND x.ngay_giao BETWEEN %(f)s AND %(t)s
		GROUP BY x.tt""", {**p, "tt": TT_GIAO}, as_dict=True)
	d = {r.tt: cint(r.n) for r in rows}
	n = sum(d.values())
	return {"so_don": n, "da_giao": d.get("Đã giao", 0), "khach_hen": d.get("Khách hẹn", 0), "hoan": d.get("Hoàn", 0),
		"ty_le": pct(d.get("Đã giao", 0), n)}


# ─── 2. Chuyến xe ────────────────────────────────────────────────────────────
def _chuyen(p: dict) -> dict:
	if not _has("Chuyen Xe"):
		return {"available": False}
	rows = frappe.db.sql(
		"""
		SELECT cx.ngay_giao AS d, COALESCE(NULLIF(cx.trang_thai, ''), 'Nháp') AS st, COUNT(*) AS n,
			SUM(cx.tong_don) AS don, SUM(cx.tong_kien) AS kien,
			SUM(CASE WHEN cx.the_tich_xe > 0 THEN cx.tong_the_tich ELSE 0 END) AS m3_co_cap,
			SUM(CASE WHEN cx.the_tich_xe > 0 THEN cx.the_tich_xe ELSE 0 END) AS cap,
			SUM(cx.the_tich_xe > 0 AND cx.ti_le_tai > 100) AS qua_tai,
			SUM(COALESCE(cx.the_tich_xe, 0) <= 0) AS thieu_cap
		FROM `tabChuyen Xe` cx
		WHERE cx.docstatus != 2 AND cx.ngay_giao BETWEEN %(f)s AND %(t)s
		GROUP BY d, st""", p, as_dict=True)
	by_day: dict = {}
	by_st = {"Nháp": 0, "Đang giao": 0, "Hoàn thành": 0}
	tot = {"n": 0, "don": 0, "kien": 0.0, "m3": 0.0, "cap": 0.0, "qua_tai": 0, "thieu_cap": 0}
	for r in rows:
		by_day[iso(r.d)] = by_day.get(iso(r.d), 0) + cint(r.n)
		by_st[r.st] = by_st.get(r.st, 0) + cint(r.n)
		tot["n"] += cint(r.n)
		tot["don"] += cint(r.don)
		tot["kien"] += flt(r.kien)
		tot["m3"] += flt(r.m3_co_cap)
		tot["cap"] += flt(r.cap)
		tot["qua_tai"] += cint(r.qua_tai)
		tot["thieu_cap"] += cint(r.thieu_cap)
	ngay_co_chuyen = len(by_day)
	return {
		"available": True, "so_chuyen": tot["n"], "by_status": by_st,
		"don_moi_chuyen": round(tot["don"] / tot["n"], 1) if tot["n"] else None,
		"chuyen_moi_ngay": round(tot["n"] / ngay_co_chuyen, 1) if ngay_co_chuyen else None,
		"tai_tb": pct(tot["m3"], tot["cap"]),  # m³ chở / sức chứa, chỉ chuyến có khai sức chứa
		"qua_tai": tot["qua_tai"], "thieu_cap": tot["thieu_cap"],
		"by_day": [{"date": d, "n": n} for d, n in sorted(by_day.items())],
	}


# ─── 3. Cước ─────────────────────────────────────────────────────────────────
CX, SC = "Chuyen Xe", "Su Co Van Chuyen"
HOAN_THANH = "Hoàn thành"
THANH_PHAN = (("cuoc_goc", "goc", "Cước gốc theo tỉnh"), ("phu_phi_gui_xe", "gui", "Phụ phí gửi xe"),
	("phu_phi_nhieu_diem", "nhieu_diem", "Phụ phí nhiều điểm"), ("phu_phi_chuyen_2", "chuyen_2", "Phụ phí chuyến thứ 2"),
	("phu_phi_xe", "pp_xe", "Phụ phí xe"))


def _cuoc(p: dict) -> dict:
	"""Cước chuyến ĐÃ DUYỆT theo ngày giao (như chi_cuoc). Cước là thu nhập của lái xe: tháng có < K lái xe
	chạy thì không hiện tiền (như lương nhóm < K người), chỉ còn số chuyến."""
	if not _has(CX, "Chuyen Xe Don Hang") or not frappe.db.has_column(CX, "tong_cuoc"):
		return {"available": False}
	c = {f: _cot(CX, f, "cx", "0") for f, _k, _l in THANH_PHAN}
	da = _cot(CX, "da_tra_cuoc", "cx")
	je = _cot(CX, "cuoc_je", "cx")  # thiếu cột → NULL: LEFT JOIN không khớp gì
	r = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS so_chuyen, COUNT(DISTINCT NULLIF({_cot(CX, "lai_xe", "cx")}, '')) AS so_lai_xe,
			COALESCE(SUM(cx.tong_don), 0) AS so_diem, COALESCE(SUM(cx.tong_cuoc), 0) AS tong,
			COALESCE(SUM(CASE WHEN cx.trang_thai = %(ht)s THEN cx.tong_cuoc ELSE 0 END), 0) AS tong_ht,
			{", ".join(f"COALESCE(SUM({c[f]}), 0) AS {k}" for f, k, _l in THANH_PHAN)},
			SUM(COALESCE({_cot(CX, "cuoc_thu_cong", "cx", "0")}, 0) = 1) AS sua_tay,
			SUM(CASE WHEN COALESCE({da}, 0) = 1 THEN cx.tong_cuoc ELSE 0 END) AS da_tra,
			SUM(CASE WHEN COALESCE({da}, 0) = 0 AND cx.tong_cuoc > 0 THEN cx.tong_cuoc ELSE 0 END) AS chua_tra,
			SUM(COALESCE({da}, 0) = 0 AND cx.tong_cuoc > 0) AS so_chua_tra,
			SUM(COALESCE({da}, 0) = 1 AND COALESCE(je.docstatus, -1) != 1) AS tra_bat_thuong
		FROM `tabChuyen Xe` cx LEFT JOIN `tabJournal Entry` je ON je.name = {je}
		WHERE cx.docstatus = 1 AND cx.ngay_giao BETWEEN %(f)s AND %(t)s""", {**p, "ht": HOAN_THANH}, as_dict=True)[0]
	# Chuyến đã trả cước (bút toán còn hiệu lực) rồi bị huỷ: chi_cuoc.cancel_trip không chặn — tiền đã ra.
	huy = frappe.db.sql(
		f"""SELECT COUNT(*) AS n, COALESCE(SUM(cx.tong_cuoc), 0) AS tien
		FROM `tabChuyen Xe` cx JOIN `tabJournal Entry` je ON je.name = {je}
		WHERE cx.docstatus = 2 AND COALESCE({da}, 0) = 1 AND je.docstatus = 1
			AND cx.ngay_giao BETWEEN %(f)s AND %(t)s""", p, as_dict=True)[0]
	kien = col("Sales Invoice", "custom_tổng_kiện")
	tong = f"COALESCE(si.`{kien}`, 0)" if kien else "0"
	# % cước / doanh thu: CẢ HAI vế chỉ trên chuyến đã hoàn thành (chuyến đang giao có cước mà chưa có dòng
	# 'Đã giao' → % ảo). Đơn tách nhiều chuyến chia doanh thu theo kiện.
	dt = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT cxd.sales_invoice) AS so_don,
			COALESCE(SUM(CASE WHEN {tong} > 0 THEN {SI_AMOUNT} * LEAST(cxd.so_kien / {tong}, 1)
				ELSE {SI_AMOUNT} END), 0) AS dt
		FROM `tabChuyen Xe Don Hang` cxd
		JOIN `tabChuyen Xe` cx ON cx.name = cxd.parent AND cxd.parenttype = 'Chuyen Xe'
		JOIN `tabSales Invoice` si ON si.name = cxd.sales_invoice
		WHERE cx.docstatus = 1 AND cx.trang_thai = %(ht)s AND cxd.trang_thai_giao = 'Đã giao'
			AND cx.ngay_giao BETWEEN %(f)s AND %(t)s""", {**p, "ht": HOAN_THANH}, as_dict=True)[0]
	so_chuyen, so_lx = cint(r.so_chuyen), cint(r.so_lai_xe)
	tong_cuoc = flt(r.tong)
	co_tra = da != "NULL"
	sum_tp = sum(flt(r[k]) for _f, k, _l in THANH_PHAN)
	out = {
		"available": True, "so_chuyen": so_chuyen, "so_lai_xe": so_lx, "k": K_AN_DANH,
		"an": bool(so_chuyen) and so_lx < K_AN_DANH,
		"tong": round(tong_cuoc, 2),
		"moi_chuyen": round(tong_cuoc / so_chuyen, 0) if so_chuyen else None,
		"moi_diem": round(tong_cuoc / cint(r.so_diem), 0) if cint(r.so_diem) else None,
		"don_da_giao": cint(dt.so_don), "dt_da_giao": round(flt(dt.dt), 2),
		"ty_le_doanh_thu": pct(flt(r.tong_ht), flt(dt.dt), 2),
		"thanh_phan": [{"key": k, "label": lbl, "tien": round(flt(r[k]), 2)} for _f, k, lbl in THANH_PHAN] + (
			[{"key": "tay", "label": "Điều chỉnh tay", "tien": round(tong_cuoc - sum_tp, 2)}]
			if abs(tong_cuoc - sum_tp) >= 1 else []),
		"sua_tay": cint(r.sua_tay),
		"da_tra": round(flt(r.da_tra), 2) if co_tra else None,
		"chua_tra": round(flt(r.chua_tra), 2) if co_tra else None,
		"so_chua_tra": cint(r.so_chua_tra) if co_tra else None,
		"tra_bat_thuong": cint(r.tra_bat_thuong) if co_tra else 0,  # đã trả mà bút toán chưa duyệt / đã huỷ
		"tra_chuyen_huy": cint(huy.n), "tra_chuyen_huy_tien": round(flt(huy.tien), 2),
	}
	if out["an"]:  # dưới K lái xe: tổng cước ≈ thu nhập từng người → chỉ giữ số đếm
		for key in ("tong", "moi_chuyen", "moi_diem", "ty_le_doanh_thu", "da_tra", "chua_tra", "tra_chuyen_huy_tien"):
			out[key] = None
		out["thanh_phan"] = []
	return out


# ─── 4. Sự cố ────────────────────────────────────────────────────────────────
HANG_VE_LOAI = ("Hoàn hàng", "Giao một phần", "Khách từ chối, sai địa chỉ", "Giao nhầm")


def _su_co(p: dict, today) -> dict:
	if not _has(SC):
		return {"available": False}
	gia, mat = _cot(SC, "gia_tri_anh_huong", "sc", "0"), _cot(SC, "tong_mat_duong", "sc")
	btt, bts = _cot(SC, "boi_thuong_trang_thai", "sc"), _cot(SC, "boi_thuong_so_tien", "sc", "0")
	rows = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(sc.trang_thai, ''), 'Mới') AS tt, COALESCE(NULLIF(sc.loai_su_co, ''), 'Khác') AS loai,
			COUNT(*) AS n, SUM(COALESCE({gia}, 0)) AS gt, SUM(COALESCE({mat}, 0)) AS mat,
			SUM(CASE WHEN {btt} = 'Đã thu' THEN COALESCE({bts}, 0) ELSE 0 END) AS bt_thu,
			SUM(CASE WHEN {btt} IN ('Chưa đòi', 'Đã đòi') THEN COALESCE({bts}, 0) ELSE 0 END) AS bt_con
		FROM `tabSu Co Van Chuyen` sc WHERE sc.ngay_phat_sinh BETWEEN %(f)s AND %(t)s
		GROUP BY tt, loai""", p, as_dict=True)
	loai: dict = {}
	for r in rows:
		x = loai.setdefault(r.loai, {"loai": r.loai, "n": 0, "gt": 0.0})
		x["n"] += cint(r.n)
		x["gt"] += flt(r.gt)
	# "Hàng chưa về": hang_ve_trang_thai mặc định 'Chưa về' trên MỌI sự cố → chỉ tính sự cố có hàng quay về
	# (loại trả hàng, hướng xử lý hoàn / giao một phần, hoặc có dòng hàng trả).
	hv = _cot(SC, "hang_ve_trang_thai", "sc")
	if hv != "NULL":
		con = (" OR EXISTS (SELECT 1 FROM `tabSu Co Hang Ve` h WHERE h.parent = sc.name"
			" AND h.parenttype = 'Su Co Van Chuyen' AND h.sl_tra > 0)") if (
			_has("Su Co Hang Ve") and frappe.db.has_column("Su Co Hang Ve", "sl_tra")) else ""
		hang = (f"SUM({hv} IN ('Chưa về', 'Đang về') AND (sc.loai_su_co IN %(tra)s"
			f" OR {_cot(SC, 'huong_xu_ly', 'sc')} IN ('Hoàn toàn bộ', 'Giao một phần'){con}))")
	else:
		hang = "NULL"
	snap = frappe.db.sql(
		f"""SELECT COUNT(*) AS mo, SUM(DATEDIFF(%(today)s, sc.ngay_phat_sinh) > %(n)s) AS qua_n, {hang} AS hang_chua_ve
		   FROM `tabSu Co Van Chuyen` sc WHERE COALESCE(sc.trang_thai, '') NOT IN %(dong)s""",
		{"today": today, "n": SU_CO_QUA_NGAY, "dong": SC_DONG, "tra": HANG_VE_LOAI}, as_dict=True)[0]
	dong = _cot(SC, "ngay_dong")
	xu_ly = frappe.db.sql(
		f"""SELECT AVG(DATEDIFF({dong}, ngay_phat_sinh)) FROM `tabSu Co Van Chuyen`
		   WHERE {dong} BETWEEN %(f)s AND %(t)s""", p)[0][0] if dong != "NULL" else None
	co_bt = btt != "NULL"
	return {
		"available": True, "trong_ky": sum(cint(r.n) for r in rows),
		"gia_tri_anh_huong": round(sum(flt(r.gt) for r in rows), 2),
		"mat_duong": round(sum(flt(r.mat) for r in rows), 2) if mat != "NULL" else None,
		"boi_thuong_da_thu": round(sum(flt(r.bt_thu) for r in rows), 2) if co_bt else None,
		"boi_thuong_con_doi": round(sum(flt(r.bt_con) for r in rows), 2) if co_bt else None,
		"by_type": sorted(({**x, "gt": round(x["gt"], 2)} for x in loai.values()), key=lambda x: -x["n"]),
		"dang_mo": cint(snap.mo), "mo_qua_n": cint(snap.qua_n), "so_ngay": SU_CO_QUA_NGAY,
		"hang_chua_ve": None if hang == "NULL" else cint(snap.hang_chua_ve),
		"ngay_xu_ly_tb": round(flt(xu_ly), 1) if xu_ly is not None else None,
	}


# ─── 5. Thu hồi hàng ─────────────────────────────────────────────────────────
def _thu_hoi(p: dict, today) -> dict:
	if not _has("Lo Thu Hoi"):
		return {"available": False}
	co_kt = "ketoan" in frappe.get_installed_apps() and _has("Kiem Hang Thu Hoi")
	if co_kt:
		chang = """(CASE WHEN k.name IS NULL THEN
				(CASE WHEN l.trang_thai = 'Hủy tại chỗ' THEN 'Đã kiểm hàng' ELSE l.trang_thai END)
			WHEN IFNULL(k.trang_thai, '') = '' THEN 'Đang kiểm' ELSE k.trang_thai END)"""
		join = "LEFT JOIN `tabKiem Hang Thu Hoi` k ON k.lo_thu_hoi = l.name"
	else:
		chang, join = "l.trang_thai", ""
	rows = frappe.db.sql(
		f"""
		SELECT {chang} AS chang, COUNT(*) AS n,
			SUM(DATEDIFF(%(today)s, l.ngay_yeu_cau) <= 7) AS a7, SUM(DATEDIFF(%(today)s, l.ngay_yeu_cau) BETWEEN 8 AND 30) AS a30,
			SUM(DATEDIFF(%(today)s, l.ngay_yeu_cau) > 30) AS a30p, MAX(DATEDIFF(%(today)s, l.ngay_yeu_cau)) AS max_tuoi,
			SUM(l.ngay_yeu_cau BETWEEN %(f)s AND %(t)s) AS trong_ky
		FROM `tabLo Thu Hoi` l {join}
		GROUP BY chang""", {**p, "today": today}, as_dict=True)
	order = {c: i for i, c in enumerate(CHANG)}
	stages = sorted(({"chang": r.chang or "Tạo yêu cầu", "n": cint(r.n), "a7": cint(r.a7), "a30": cint(r.a30),
		"a30p": cint(r.a30p), "max_tuoi": cint(r.max_tuoi), "trong_ky": cint(r.trong_ky)} for r in rows),
		key=lambda x: order.get(x["chang"], 99))
	mo = [s for s in stages if s["chang"] not in ("Xong", "Đã hủy")]
	out = {"available": True, "ke_toan": co_kt, "stages": stages, "dang_mo": sum(s["n"] for s in mo),
		"mo_qua_30": sum(s["a30p"] for s in mo), "trong_ky": sum(s["trong_ky"] for s in stages if s["chang"] != "Đã hủy"),
		"gia_tri": None}
	if co_kt and frappe.db.has_column("Sales Invoice", "custom_kiem_hang_thu_hoi"):
		v = frappe.db.sql(
			"""SELECT COUNT(DISTINCT r.custom_kiem_hang_thu_hoi) AS so_lo, COUNT(*) AS so_hd,
				COALESCE(SUM(ABS(r.net_total)), 0) AS gt
			   FROM `tabSales Invoice` r JOIN `tabLo Thu Hoi` l ON l.name = r.custom_kiem_hang_thu_hoi
			   WHERE r.is_return = 1 AND r.docstatus = 1 AND l.ngay_yeu_cau BETWEEN %(f)s AND %(t)s""", p, as_dict=True)[0]
		out["gia_tri"] = {"so_lo": cint(v.so_lo), "so_hd": cint(v.so_hd), "net": round(flt(v.gt), 2)}
	return out


# ─── 6. Xe ───────────────────────────────────────────────────────────────────
def _nk():
	if "vanchuyen" not in frappe.get_installed_apps():
		return None
	try:
		from vanchuyen.van_chuyen.doctype.nhat_ky_xe import nhat_ky_xe as nk
	except ImportError:
		return None
	if not all(hasattr(nk, a) for a in ("lich_cua_xe", "bao_duong_moi_nhat", "TRUONG_LICH", "loai_xe", "ngung_su_dung")):
		return None
	return nk


_MUC = {"qua_han": "qua_han", "sap_den": "sap_den", "ok": "ok"}


def _xe(today) -> dict:
	nk = _nk()
	if not nk or not frappe.db.has_column("Vehicle", "custom_han_dang_kiem"):
		return {"available": False}
	meta_cols = set(frappe.db.get_table_columns("Vehicle"))
	fields = ["name", "last_odometer"] + [f for f in ("custom_loai_xe", "custom_ngung_su_dung", *nk.TRUONG_LICH)
		if f in meta_cols]
	vs = frappe.get_all("Vehicle", fields=fields, order_by="name asc")
	bd = nk.bao_duong_moi_nhat([v.name for v in vs]) if vs and _has("Nhat Ky Xe") else {}
	dem = {k: {"qua_han": 0, "sap_den": 0, "ok": 0, "chua_co": 0} for k in ("dang_kiem", "thay_dau")}
	can = []
	dang_dung = 0
	for v in vs:
		if nk.ngung_su_dung(v):
			continue
		dang_dung += 1
		lich = nk.lich_cua_xe(v, today, bd.get(v.name))
		viec = []
		for k, nhan in (("dang_kiem", "Đăng kiểm"), ("thay_dau", "Thay dầu")):
			m = _MUC.get((lich.get(k) or {}).get("muc"), "chua_co")
			dem[k][m] += 1
			if m in ("qua_han", "sap_den"):
				it = lich[k]
				viec.append({"viec": nhan, "muc": m, "han": it.get("han"), "con_ngay": it.get("con_ngay"),
					"con_km": it.get("con_km")})
		b = lich.get("bao_duong") or {}
		if b.get("muc") in ("qua_han", "sap_den"):
			viec.append({"viec": "Bảo dưỡng", "muc": b["muc"], "han": b.get("han"), "con_ngay": b.get("con_ngay"),
				"con_km": b.get("con_km")})
		if viec:
			can.append({"xe": v.name, "loai": nk.loai_xe(v.get("custom_loai_xe")), "viec": viec,
				"qua_han": any(x["muc"] == "qua_han" for x in viec)})
	can.sort(key=lambda x: (not x["qua_han"], x["xe"]))
	chi_phi = []
	if _has("Nhat Ky Xe"):
		y = today.year
		chi_phi = [{"loai": r.loai, "tien": round(flt(r.tien), 2), "so": cint(r.so)} for r in frappe.db.sql(
			"""SELECT loai, COALESCE(SUM(chi_phi), 0) AS tien, COUNT(*) AS so FROM `tabNhat Ky Xe`
			   WHERE ngay BETWEEN %(tu)s AND %(den)s GROUP BY loai ORDER BY tien DESC""",
			{"tu": f"{y}-01-01", "den": f"{y}-12-31"}, as_dict=True)]
	return {"available": True, "dang_dung": dang_dung, "dem": dem, "can_xu_ly": can,
		"chi_phi_nam": {"nam": today.year, "rows": chi_phi, "tong": round(sum(x["tien"] for x in chi_phi), 2)}}


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	"""Vận chuyển trong tháng `thang` ('YYYY-MM', mặc định tháng này; cắt ở hôm nay) — xem docstring module.

	{available, meta: {thang, from, to, as_of}, giao, chuyen, cuoc, su_co, thu_hoi, xe}
	"""
	_guard("van-chuyen")
	if "vanchuyen" not in frappe.get_installed_apps() or not _has("Chuyen Xe"):
		return {"available": False, "meta": {}}
	f, t, label = period(thang)
	today = getdate(nowdate())

	def build():
		p = {"f": f, "t": t, "showroom": SHOWROOM}
		return {
			"available": True,
			"meta": {"thang": label, "from": iso(f), "to": iso(t), "as_of": iso(today),
				"prev": f"{getdate(add_months(f, -1)).year:04d}-{getdate(add_months(f, -1)).month:02d}"},
			"giao": safe_block("vc.giao", _giao, p, today), "chuyen": safe_block("vc.chuyen", _chuyen, p),
			"cuoc": safe_block("vc.cuoc", _cuoc, p), "su_co": safe_block("vc.su_co", _su_co, p, today),
			"thu_hoi": safe_block("vc.thu_hoi", _thu_hoi, p, today), "xe": safe_block("vc.xe", _xe, today),
		}

	return run_cached("vc.get_overview", {"t": label, "d": iso(today)}, build, refresh)
