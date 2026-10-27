# -*- coding: utf-8 -*-
"""bc.api.attp — ATTP / ISO 22000 cho Ban lãnh đạo, lấy từ app sx (đọc mềm).

Cùng số với màn "Tổng quan ATTP" và "Báo cáo tháng" của Ban ISO: GỌI helper của sx thay vì chép
logic (19 mảng, hộp nhắc và luật đèn rất dài — chép là lệch). Hai chỗ của sx phụ thuộc người đang
mở màn nên bc làm lại:
- Vòng kiểm: sx.api.qc_attp._vong_kiem gọi Q.dashboard (whitelisted, _guard_manager) → BC Viewer bị
  chặn, sx nuốt lỗi thành "chưa có số liệu". bc tính lại 7 chỉ số đó đúng công thức dashboard.
- Biên bản: Q._du_lieu_nhac gọi bien_ban.nhac(d, frappe.session.user, roles) → có mục "biên bản chờ
  BẠN ký" theo người xem; cache của bc dùng chung mọi người nên thay bằng bien_ban.nhac(d) không user.
Kỳ số liệu như sx: 30 ngày tới HÔM QUA (hôm nay đang làm, chưa đủ lượt); việc treo tính tới hôm nay.
Không trả route của sx (BC Viewer không mở được SPA /sx) và bỏ chi tiết dòng sổ (#/so/…: có thể là
tên khách ra vào, nhà cung cấp) — chỉ giữ tiêu đề việc treo.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import frappe
from frappe.utils import add_days, cint, getdate, nowdate

from bc.api._common import _guard, iso, run_cached

SO_NGAY = 30
_CARD_FNS = ("_su_co", "_khac_phuc", "_khieu_nai", "_xuat_xuong", "_truy_xuat", "_thiet_bi", "_kiem_nghiem", "_cat",
	"_vai_u", "_dong_vat", "_ncc", "_kiem_xe", "_luu_mau", "_rework", "_viec_dinh_ky", "_tai_lieu", "_bien_ban",
	"_so_khac")
_Q_FNS = ("_du_lieu_nhac", "_ngay_san_xuat")
_THANG = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _sx():
	"""Các module QC của sx nếu site có app sx và API riêng còn khớp, không thì None."""
	if "sx" not in frappe.get_installed_apps():  # bench nhiều site: import được mà site không cài
		return None
	try:
		from sx.api import qc as Q
		from sx.api import qc_attp as QA
		from sx.qc import attp as A
		from sx.qc import muc as M
		from sx.qc import nhac as NH
	except ImportError:
		return None
	if not all(hasattr(QA, f) for f in _CARD_FNS) or not all(hasattr(Q, f) for f in _Q_FNS):
		return None  # sx đổi tên hàm riêng → báo "chưa có" thay vì số sai
	if not (frappe.db.table_exists("SX QC Round") and frappe.db.table_exists("SX Su Co")):
		return None
	return SimpleNamespace(Q=Q, QA=QA, A=A, M=M, NH=NH)


def _thu(f):
	try:
		return f()
	except Exception:
		return None


def _du_lieu_mau() -> str:
	"""Câu cảnh báo khi site sx còn dữ liệu mẫu (sx.qc.mau_in) — rỗng nếu không."""
	try:
		from sx.qc.mau_in import BAN_THU, in_ban_thu
		return BAN_THU if in_ban_thu() else ""
	except Exception:
		return ""


def _du_lieu_nhac(S, d) -> dict:
	"""Đầu vào hộp nhắc của sx (Q._du_lieu_nhac) — mục biên bản thay bằng bản KHÔNG theo người xem."""
	dl = S.Q._du_lieu_nhac(d)
	try:
		from sx.qc import bien_ban
		dl["bien_ban"] = bien_ban.nhac(d)
	except Exception:
		dl["bien_ban"] = {}
	return dl


def _vong_kiem(S, d, tu, den, dl) -> dict:
	"""= sx.api.qc_attp._vong_kiem với 7 chỉ số của Q.dashboard (bị guard) tính tại chỗ, cùng công thức."""
	M, Q = S.M, S.Q
	rounds = frappe.get_all("SX QC Round", filters={"ngay": ("between", [tu, den]), "docstatus": 1},
		fields=["ngay", "luot", "ghi_muon", "reviewed_on"])
	do_dang = frappe.get_all("SX QC Round", filters={"ngay": ("between", [tu, den]), "docstatus": 0}, fields=["ngay"])
	ngay_sx = Q._ngay_san_xuat(tu, den, list(rounds) + list(do_dang))
	chinh = [r for r in rounds if r["luot"] != M.BO_SUNG]  # lượt bổ sung không thay 1 trong 3 lượt
	dem: dict = {}
	for r in chinh:
		dem[str(r["ngay"])] = dem.get(str(r["ngay"]), 0) + 1
	can = len(M.LUOT_TRONG_NGAY)
	can_co = len(ngay_sx) * can
	hom = [r for r in dl["luot"] if str(r.get("ngay")) == str(d)]
	xong = {M.DAU_SANG if r.get("luot") == M.TUAN else r.get("luot") for r in hom if r.get("docstatus") == 1}
	return {"ty_le": round(min(len(chinh), can_co) * 100.0 / can_co, 1) if can_co else 0,
		"so_luot": len(chinh), "can_co": can_co,
		"ngay_thieu": sum(1 for x in ngay_sx if dem.get(x, 0) < can),
		"ghi_muon": sum(1 for r in rounds if cint(r["ghi_muon"])),
		"chua_xem_xet": sum(1 for r in rounds if not r["reviewed_on"]),
		"so_bo_sung": len(rounds) - len(chinh),
		"hom_nay_xong": len(xong & set(M.LUOT_TRONG_NGAY)),
		"hom_nay_sx": bool(Q._ngay_san_xuat(d, d, hom))}


def _lam_sach(out: dict) -> dict:
	"""Bỏ route SPA sx; bỏ chi tiết dòng sổ (#/so/…) — chỉ giữ tiêu đề việc treo."""
	for t in out.get("linh_vuc") or []:
		t.pop("route", None)
		for x in t.get("nhac") or []:
			if str(x.get("route") or "").startswith("#/so/"):
				x["chi_tiet"] = ""
			x.pop("route", None)
			x.pop("nhom", None)
	return out


@frappe.whitelist()
def get_overview(refresh=0):
	"""Tổng quan ATTP — 19 mảng, đèn đỏ/vàng/xanh, việc treo (= sx.api.qc_attp.tong_quan, hôm nay).

	{available, linh_vuc: [{ma, ten, bieu_mau, den: do|vang|xanh, so, nhan_so, dong[], nhac[{muc_do, tieu_de, chi_tiet}]}],
	 dem: {do, vang, xanh}, ngay, tu, den, so_ngay, du_lieu_mau}
	"""
	_guard()
	S = _sx()
	if not S:
		return {"available": False, "meta": {}}
	d = getdate(nowdate())

	def build():
		tu, den = getdate(add_days(d, -SO_NGAY)), getdate(add_days(d, -1))
		dl = _du_lieu_nhac(S, d)
		QA = S.QA
		so = {
			"vong_kiem": _thu(lambda: _vong_kiem(S, d, tu, den, dl)),
			"su_co": _thu(lambda: QA._su_co(d, tu, den)),
			"khac_phuc": _thu(lambda: QA._khac_phuc(d, tu, den)),
			"khieu_nai": _thu(lambda: QA._khieu_nai(d, tu, den)),
			"xuat_xuong": _thu(lambda: QA._xuat_xuong(tu, den, dl)),
			"truy_xuat": _thu(lambda: QA._truy_xuat(d)),
			"thiet_bi": _thu(lambda: QA._thiet_bi(dl)),
			"kiem_nghiem": _thu(lambda: QA._kiem_nghiem(d)),
			"cat": _thu(lambda: QA._cat(dl)),
			"vai_u": _thu(lambda: QA._vai_u(tu, den, dl)),
			"dong_vat": _thu(lambda: QA._dong_vat(tu, den, dl)),
			"ncc": _thu(lambda: QA._ncc(d)),
			"kiem_xe": _thu(lambda: QA._kiem_xe(d, tu, den, dl)),
			"luu_mau": _thu(lambda: QA._luu_mau(dl)),
			"rework": _thu(lambda: QA._rework(tu, den)),
			"viec_dinh_ky": _thu(lambda: QA._viec_dinh_ky(d, dl)),
			"tai_lieu": _thu(lambda: QA._tai_lieu(dl)),
			"bien_ban": _thu(lambda: QA._bien_ban(tu, den, dl)),
			"so_khac": _thu(lambda: QA._so_khac(tu, den, dl)),
		}
		out = _lam_sach(S.A.tong_hop(S.NH.tinh(d, **dl), so))
		frappe.clear_last_message()  # helper sx lỗi (chưa migrate) có thể đã msgprint — không đẩy ra màn bc
		return dict(out, available=True, ngay=iso(d), tu=iso(tu), den=iso(den), so_ngay=SO_NGAY,
			du_lieu_mau=_du_lieu_mau())

	return run_cached("attp.get_overview", {"d": iso(d)}, build, refresh)


def _thang_hop_le(thang) -> str | None:
	"""'YYYY-MM' mà ngày 1 đã qua (≤ hôm qua) — như sx qc_baocao._ky đòi; sai thì None (= tháng trước).
	Kiểm ở bc vì _ky dùng frappe.throw: bắt được lỗi nhưng thông báo vẫn lọt ra client."""
	t = str(thang or "")[:7]
	if not _THANG.match(t):
		return None
	return t if getdate(f"{t}-01") <= getdate(add_days(getdate(nowdate()), -1)) else None


@frappe.whitelist()
def get_report(thang=None, refresh=0):
	"""16 chỉ số ATTP theo tháng từ đầu năm + mức đạt chỉ tiêu năm (= sx.api.qc_baocao.so_lieu).

	{available, thang, nam, dau, cat, bang: [{ma, ten, don_vi, kieu, huong, thang{YYYY-MM: v}, ky, nam}],
	 chi_tieu: [{chi_so, ten, so_sanh, muc_tieu, ky, nam_luy_ke, dat_ky, dat_nam}]}
	"""
	_guard()
	if "sx" not in frappe.get_installed_apps() or not frappe.db.table_exists("SX Chi Tieu ATTP"):
		return {"available": False, "meta": {}}
	try:
		from sx.api.qc_baocao import _du_lieu
	except ImportError:
		return {"available": False, "meta": {}}
	t = _thang_hop_le(thang)
	today = iso(getdate(nowdate()))

	def build():
		r = _du_lieu(t)
		frappe.clear_last_message()
		chi_tieu = []
		for c in r.get("chi_tieu") or []:
			# sx ghi đè khoá `nam` (năm) bằng số luỹ kế năm — tách lại cho rõ.
			chi_tieu.append({"chi_so": c.get("chi_so"), "ten": c.get("ten"), "so_sanh": c.get("so_sanh"),
				"muc_tieu": c.get("muc_tieu"), "don_vi": c.get("don_vi"), "ky": c.get("ky"),
				"nam_luy_ke": c.get("nam"), "dat_ky": c.get("dat_ky"), "dat_nam": c.get("dat_nam")})
		return {"available": True, "thang": r.get("thang"), "nam": r.get("nam"), "dau": r.get("dau"),
			"cat": r.get("cat"), "bang": r.get("bang") or [], "chi_tieu": chi_tieu, "hom_nay": today}

	return run_cached("attp.get_report", {"t": t or "", "d": today}, build, refresh)
