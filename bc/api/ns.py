# -*- coding: utf-8 -*-
"""bc.api.ns — Nhân sự cho Ban lãnh đạo: CHỈ số tổng hợp, đọc mềm Employee (+ field của app ns), phiếu
lương SalaryDay (công nhật, DocType tạo trên site) / SX Phieu Luong (khoán, app sx), giấy tờ NS Giay To.

Một lượt gọi get_overview() trả 6 khối, khối nào thiếu bảng / cột thì `available: False`:
- nhan_su: quân số theo trạng thái × bộ phận (khoán = bộ phận "Công khoán - HGC" như ns.common.loai_luong).
- bien_dong: vào / nghỉ 12 tháng theo date_of_joining / relieving_date (KHÔNG dùng modified, KHÔNG dùng
  NS Su Kien — sự kiện chỉ có từ 24/10/2026 và vài loại hỏng option).
- bhxh: tỷ lệ đóng trong số đang làm (cờ ns_dong_bhxh; thiếu app ns → ước tính theo custom_bảo_hiểm > 0).
- luong: quỹ lương THỰC NHẬN 12 tháng theo loại (công nhật / khoán), mỗi (nhân viên, tháng) một phiếu như
  ns.phieu.chon_phieu (đã duyệt mới nhất, không có thì nháp mới nhất). Tháng trước + tháng này = tạm tính
  (gồm nháp); tháng cũ hơn chỉ phiếu đã duyệt. Trước tháng đầu tiên có phiếu → None ("chưa có dữ liệu").
  Theo bộ phận chỉ cho tháng trước, ẩn nhóm < K người (an_danh), làm tròn 100.000 đ. Không gồm Ban lãnh đạo.
- giay_to: HĐ / khám SK / ATTP hết hạn (đỏ) / ≤ 30 ngày (vàng) như ns.canh_bao — ATTP khớp lỏng vì option
  trong NS Giay To lưu sai chữ ("Xác nhậ3n kiến thức ATTP").
- canh_bao: đếm số NGƯỜI theo từng mã cảnh báo của ns (gọi hàm thuần ns.api.canh_bao.tinh), bỏ sinh nhật
  và 3 mã giấy tờ (đã có khối riêng).
Không trả tên, mã nhân viên, CCCD, ngân hàng, mức lương từng người, lý do không đóng BHXH từng người.
Không gọi whitelisted method nào của ns (đều guard HR theo phiên — cache bc dùng chung mọi user).
"""

from __future__ import annotations

import re
import unicodedata

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from bc.api._common import _guard, iso, pct, real_column, run_cached

K_AN_DANH = 5                   # nhóm < K người: không hiện tiền (gộp nhóm nhỏ)
LAM_TRON = -5                   # làm tròn tiền 100.000 đ
BO_PHAN_KHOAN = "Công khoán - HGC"  # = ns.api.common.BO_PHAN_KHOAN
KHONG_BO_PHAN = "__none__"
TAM_NGHI = ("Inactive", "Suspended")
LOAI_HD = ("Hợp đồng lao động", "Phụ lục HĐLĐ")
LOAI_KSK = "Giấy khám sức khỏe"
GIAY_TO_NGAY = 30               # = canh_bao: vàng nếu hết hạn trong 30 ngày tới
BHXH_NGAY = 30                  # = canh_bao.bhxh_rui_ro: vào làm quá 30 ngày chưa đóng, chưa ghi lý do
BO_MA = {"sinh_nhat", "hd_het_han", "kham_sk_het_han", "attp_het_han"}
F_BAO_HIEM = "custom_bảo_hiểm"
_DUOI_CONG_TY = re.compile(r"\s+-\s+[A-Z0-9]{2,6}$")


def _nfc(s) -> str:
	return unicodedata.normalize("NFC", s or "")


def la_khoan(dept) -> bool:
	return _nfc(dept) == _nfc(BO_PHAN_KHOAN)


def ten_bo_phan(dept) -> str:
	if not dept or dept == KHONG_BO_PHAN:
		return "Chưa có bộ phận"
	return _DUOI_CONG_TY.sub("", dept)


def _ym(y: int, m: int) -> int:
	return y * 100 + m


def _lui(y: int, m: int, n: int) -> tuple:
	t = y * 12 + (m - 1) - n
	return t // 12, t % 12 + 1


def _nhan(ym: int) -> str:
	return f"{ym // 100:04d}-{ym % 100:02d}"


def _tron(v):
	return None if v is None else round(flt(v), LAM_TRON)


def an_danh(cells: list, k: int = K_AN_DANH, keys=("tong_tien", "thuc_nhan"), gop="Nhóm nhỏ (gộp)", tat_ca="Tất cả") -> list:
	"""Ẩn nhóm < k người. cells: [{"nhom", "n", <keys>}] của MỘT kỳ. Nhóm nhỏ gộp lại; gộp vẫn < k thì nhập vào
	nhóm lớn nhỏ nhất (không để đúng một ô ẩn suy ra được bằng tổng − các ô hiện); không có nhóm lớn nào thì
	chỉ trả tổng số người, không tiền."""
	lon = [dict(c) for c in cells if c["n"] >= k]
	nho = [c for c in cells if 0 < c["n"] < k]
	if not nho:
		return lon
	g = {"nhom": gop, "n": sum(c["n"] for c in nho), **{x: sum(flt(c[x]) for c in nho) for x in keys}}
	if g["n"] >= k:
		return lon + [g]
	if lon:
		m = min(lon, key=lambda c: c["n"])
		m["nhom"] += " + nhóm nhỏ"
		m["n"] += g["n"]
		for x in keys:
			m[x] = flt(m[x]) + g[x]
		return lon
	return [{"nhom": tat_ca, "n": g["n"], **{x: None for x in keys}}]


# ─── 1. Quân số ──────────────────────────────────────────────────────────────
def _nhan_su(today) -> dict:
	rows = frappe.db.sql(
		"""SELECT e.status AS st, IFNULL(NULLIF(e.department, ''), %(none)s) AS dept, COUNT(*) AS n
		   FROM `tabEmployee` e GROUP BY st, dept""", {"none": KHONG_BO_PHAN}, as_dict=True)
	st = {"Active": 0, "tam_nghi": 0, "Left": 0, "khac": 0}
	dept: dict = {}
	loai = {"Nhật": 0, "Khoán": 0}
	for r in rows:
		n = cint(r.n)
		key = "Active" if r.st == "Active" else "tam_nghi" if r.st in TAM_NGHI else "Left" if r.st == "Left" else "khac"
		st[key] += n
		if key in ("Active", "tam_nghi"):
			d = dept.setdefault(_nfc(r.dept), {"bo_phan": ten_bo_phan(r.dept), "loai": "Khoán" if la_khoan(r.dept) else "Nhật",
				"dang_lam": 0, "tam_nghi": 0})
			d["dang_lam" if key == "Active" else "tam_nghi"] += n
			if key == "Active":
				loai[d["loai"]] += n
	sai = frappe.db.sql("""SELECT COUNT(*) FROM `tabEmployee` WHERE status = 'Active' AND relieving_date < %(t)s""",
		{"t": today})[0][0]
	return {"dang_lam": st["Active"], "tam_nghi": st["tam_nghi"], "da_nghi": st["Left"], "khac": st["khac"],
		"loai": loai, "by_dept": sorted(dept.values(), key=lambda x: (-x["dang_lam"], -x["tam_nghi"], x["bo_phan"])),
		"active_da_nghi": cint(sai)}


# ─── 2. Vào / nghỉ 12 tháng ──────────────────────────────────────────────────
def _bien_dong(today, months: list) -> dict:
	tu = getdate(f"{_nhan(months[0])}-01")
	p = {"tu": tu, "den": today}
	vao = dict(frappe.db.sql(
		"""SELECT YEAR(date_of_joining) * 100 + MONTH(date_of_joining) AS ym, COUNT(*) FROM `tabEmployee`
		   WHERE date_of_joining BETWEEN %(tu)s AND %(den)s GROUP BY ym""", p))
	nghi = dict(frappe.db.sql(
		"""SELECT YEAR(relieving_date) * 100 + MONTH(relieving_date) AS ym, COUNT(*) FROM `tabEmployee`
		   WHERE status = 'Left' AND relieving_date BETWEEN %(tu)s AND %(den)s GROUP BY ym""", p))
	khong_ngay = frappe.db.sql("""SELECT COUNT(*) FROM `tabEmployee` WHERE status = 'Left' AND relieving_date IS NULL""")[0][0]
	rows = [{"thang": _nhan(ym), "vao": cint(vao.get(ym)), "nghi": cint(nghi.get(ym))} for ym in months]
	return {"rows": rows, "vao": sum(r["vao"] for r in rows), "nghi": sum(r["nghi"] for r in rows),
		"nghi_khong_ngay": cint(khong_ngay)}


# ─── 3. BHXH ─────────────────────────────────────────────────────────────────
def _bhxh(today) -> dict:
	co = frappe.db.has_column("Employee", "ns_dong_bhxh")
	bh = real_column("Employee", F_BAO_HIEM)
	if not co and not bh:
		return {"available": False}
	if not co:  # chưa cài ns: ước tính "đang đóng" = có mức trừ BH
		r = frappe.db.sql(f"""SELECT COUNT(*) AS n, SUM(IFNULL(`{bh}`, 0) > 0) AS dong FROM `tabEmployee`
			WHERE status = 'Active'""", as_dict=True)[0]
		return {"available": True, "uoc_tinh": True, "dang_lam": cint(r.n), "dong": cint(r.dong),
			"ty_le": pct(r.dong, r.n), "chua_muc": None, "lech": None, "rui_ro": None, "ly_do": []}
	bh_sql = f"IFNULL(`{bh}`, 0)" if bh else None
	ly = frappe.db.has_column("Employee", "ns_ly_do_khong_bhxh")
	r = frappe.db.sql(
		f"""SELECT COUNT(*) AS n, SUM(ns_dong_bhxh = 1) AS dong,
			{f"SUM(ns_dong_bhxh = 1 AND {bh_sql} = 0)" if bh_sql else "NULL"} AS chua_muc,
			{f"SUM(ns_dong_bhxh = 0 AND {bh_sql} > 0)" if bh_sql else "NULL"} AS lech,
			SUM(ns_dong_bhxh = 0 AND date_of_joining <= %(moc)s
				{"AND IFNULL(ns_ly_do_khong_bhxh, '') = ''" if ly else ""}) AS rui_ro
		FROM `tabEmployee` WHERE status = 'Active'""", {"moc": getdate(add_days(today, -BHXH_NGAY))}, as_dict=True)[0]
	ly_do = []
	if ly:
		cells = [{"nhom": x[0] or "", "n": cint(x[1])} for x in frappe.db.sql(
			"""SELECT IFNULL(ns_ly_do_khong_bhxh, '') AS ly_do, COUNT(*) FROM `tabEmployee`
			   WHERE status = 'Active' AND ns_dong_bhxh = 0 GROUP BY ly_do""")]
		chua = [c for c in cells if not c["nhom"]]
		# Lý do từng người (vd đang hưởng lương hưu) là riêng tư → nhóm < K gộp, như tiền lương.
		ly_do = [{"ly_do": "Chưa ghi lý do", "n": chua[0]["n"]}] if chua else []
		ly_do += [{"ly_do": c["nhom"], "n": c["n"]} for c in an_danh([c for c in cells if c["nhom"]], keys=(),
			gop="Lý do khác (gộp)", tat_ca="Có ghi lý do (gộp)")]
	return {"available": True, "uoc_tinh": False, "dang_lam": cint(r.n), "dong": cint(r.dong), "ty_le": pct(r.dong, r.n),
		"chua_muc": None if r.chua_muc is None else cint(r.chua_muc), "lech": None if r.lech is None else cint(r.lech),
		"rui_ro": cint(r.rui_ro), "ly_do": ly_do}


# ─── 4. Quỹ lương ────────────────────────────────────────────────────────────
NGUON = {
	# loại: (DocType, cột năm, cột tháng, cột tổng thu nhập, cột thực nhận)
	"nhat": ("SalaryDay", "year", "month", "tongtien", "luongthucnhan"),
	"khoan": ("SX Phieu Luong", "nam", "thang", "tong_tien", "luong_thuc_nhan"),
}


def _nguon_co(loai: str) -> bool:
	dt, y, m, tong, thuc = NGUON[loai]
	if loai == "khoan" and "sx" not in frappe.get_installed_apps():
		return False
	return frappe.db.table_exists(dt) and all(frappe.db.has_column(dt, c) for c in ("employee", y, m, tong, thuc))


def _phieu(loai: str, tu: int, den: int) -> list:
	"""Mỗi (nhân viên, tháng) 1 phiếu như ns.phieu.chon_phieu → gom theo (ym, bộ phận, docstatus phiếu chọn)."""
	dt, y, m, tong, thuc = NGUON[loai]
	if loai == "nhat":
		snap = "sd.department" if frappe.db.has_column(dt, "department") else "NULL"
		dept = f"IFNULL(NULLIF(t.dept, ''), IFNULL(NULLIF(e.department, ''), '{KHONG_BO_PHAN}'))"
	else:
		snap, dept = "NULL", "NULL"  # khoán: không lưu bộ phận theo kỳ — cả loại là một nhóm
	return frappe.db.sql(
		f"""
		SELECT t.ym, {dept} AS dept, t.docstatus, COUNT(*) AS n, SUM(t.tong) AS tong, SUM(t.thuc) AS thuc
		FROM (
			SELECT sd.employee, sd.`{y}` * 100 + sd.`{m}` AS ym, {snap} AS dept, sd.docstatus,
				sd.`{tong}` AS tong, sd.`{thuc}` AS thuc,
				ROW_NUMBER() OVER (PARTITION BY sd.employee, sd.`{y}`, sd.`{m}` ORDER BY sd.docstatus DESC, sd.modified DESC) AS rn
			FROM `tab{dt}` sd
			WHERE sd.docstatus < 2 AND IFNULL(sd.employee, '') != ''
				AND sd.`{m}` BETWEEN 1 AND 12 AND sd.`{y}` BETWEEN 2000 AND 2100
				AND sd.`{y}` * 100 + sd.`{m}` BETWEEN %(tu)s AND %(den)s
		) t
		LEFT JOIN `tabEmployee` e ON e.name = t.employee
		WHERE t.rn = 1
		GROUP BY t.ym, dept, t.docstatus""", {"tu": tu, "den": den}, as_dict=True)


def _dau_ky(loai: str):
	dt, y, m, *_r = NGUON[loai]
	v = frappe.db.sql(f"""SELECT MIN(`{y}` * 100 + `{m}`) FROM `tab{dt}` WHERE docstatus < 2 AND IFNULL(employee, '') != ''
		AND `{m}` BETWEEN 1 AND 12 AND `{y}` BETWEEN 2000 AND 2100""")[0][0]
	return cint(v) or None


def _loi_ky(loai: str) -> int:
	dt, y, m, *_r = NGUON[loai]
	return cint(frappe.db.sql(f"""SELECT COUNT(*) FROM `tab{dt}` WHERE docstatus < 2
		AND NOT (`{m}` BETWEEN 1 AND 12 AND `{y}` BETWEEN 2000 AND 2100)""")[0][0])


def _o(rows: list, tam_tinh: bool) -> dict:
	"""Một ô (tháng, loại): tạm tính gồm phiếu nháp được chọn; tháng đã chốt chỉ phiếu đã duyệt."""
	dung = [r for r in rows if tam_tinh or cint(r.docstatus) == 1]
	n = sum(cint(r.n) for r in dung)
	cell = {"so_nguoi": n, "so_nhap": sum(cint(r.n) for r in rows if cint(r.docstatus) == 0),
		"tong_tien": _tron(sum(flt(r.tong) for r in dung)), "thuc_nhan": _tron(sum(flt(r.thuc) for r in dung)), "an": False}
	if 0 < n < K_AN_DANH:
		cell.update(tong_tien=None, thuc_nhan=None, an=True)
	return cell


def _luong(months: list, ky: int) -> dict:
	co = {l: _nguon_co(l) for l in NGUON}
	if not any(co.values()):
		return {"available": False}
	tam_tu = ky  # tháng trước + tháng này: tạm tính
	series = [{"thang": _nhan(ym), "tam_tinh": ym >= tam_tu} for ym in months]
	out = {"available": True, "k": K_AN_DANH, "ky": _nhan(ky), "co": co, "dau_ky": {}, "loi_ky": 0,
		"hook_tat": bool(co["nhat"]) and not cint(frappe.conf.get("ns_tinh_lai_salaryday")),
		"series": series, "bo_phan": []}
	cells_ky = []
	for loai in NGUON:
		if not co[loai]:
			for s in series:
				s[loai] = None
			continue
		dau = _dau_ky(loai)
		out["dau_ky"][loai] = _nhan(dau) if dau else None
		out["loi_ky"] += _loi_ky(loai)
		rows = _phieu(loai, months[0], months[-1])
		for s, ym in zip(series, months):
			s[loai] = None if (not dau or ym < dau) else _o([r for r in rows if cint(r.ym) == ym], s["tam_tinh"])
		if dau and ky >= dau:
			ky_rows = [r for r in rows if cint(r.ym) == ky]
			if loai == "nhat":
				by: dict = {}
				for r in ky_rows:
					c = by.setdefault(_nfc(r.dept), {"nhom": ten_bo_phan(r.dept), "loai": "Công nhật", "n": 0, "tong_tien": 0.0, "thuc_nhan": 0.0})
					c["n"] += cint(r.n)
					c["tong_tien"] += flt(r.tong)
					c["thuc_nhan"] += flt(r.thuc)
				cells_ky += [{**c, "loai": "Công nhật"} for c in an_danh(list(by.values()))]
			else:
				n = sum(cint(r.n) for r in ky_rows)
				if n:
					an = n < K_AN_DANH
					cells_ky.append({"nhom": "Công khoán", "loai": "Khoán", "n": n,
						"tong_tien": None if an else sum(flt(r.tong) for r in ky_rows),
						"thuc_nhan": None if an else sum(flt(r.thuc) for r in ky_rows)})
	out["bo_phan"] = [{**c, "tong_tien": _tron(c["tong_tien"]), "thuc_nhan": _tron(c["thuc_nhan"])} for c in cells_ky]
	return out


# ─── 5. Giấy tờ hết hạn ──────────────────────────────────────────────────────
def _nhom_giay(loai) -> str | None:
	l = _nfc(loai)
	if l in {_nfc(x) for x in LOAI_HD}:
		return "hd"
	if l == _nfc(LOAI_KSK):
		return "ksk"
	if "ATTP" in l.upper():  # option lưu sai "Xác nhậ3n kiến thức ATTP" — /ns không khớp được, bc khớp lỏng
		return "attp"
	return None


def _muc(d, today, han):
	if not d:
		return None
	d = getdate(d)
	return "do" if d < today else "vang" if d <= han else None


def _giay_to(today) -> dict:
	if not frappe.db.table_exists("NS Giay To"):
		return {"available": False}
	han = getdate(add_days(today, GIAY_TO_NGAY))
	moi: dict = {}  # (nhân viên, nhóm) → khoá dòng mới nhất (như canh_bao._moi_nhat)
	for r in frappe.db.sql(
			"""SELECT g.parent, g.loai, g.ngay_het_han, g.ngay_cap, g.idx FROM `tabNS Giay To` g
			   JOIN `tabEmployee` e ON e.name = g.parent
			   WHERE g.parenttype = 'Employee' AND g.parentfield = 'ns_giay_to' AND e.status != 'Left'""", as_dict=True):
		nhom = _nhom_giay(r.loai)
		if not nhom:
			continue
		k = (str(r.ngay_het_han or ""), str(r.ngay_cap or ""), cint(r.idx))
		cur = moi.get((r.parent, nhom))
		if cur is None or k > cur[0]:
			moi[(r.parent, nhom)] = (k, r.ngay_het_han)
	muc: dict = {(e, n): _muc(v[1], today, han) for (e, n), v in moi.items()}
	for e, d in frappe.db.sql("""SELECT name, contract_end_date FROM `tabEmployee`
			WHERE status != 'Left' AND contract_end_date IS NOT NULL"""):
		m = _muc(d, today, han)
		cur = muc.get((e, "hd"))
		muc[(e, "hd")] = "do" if "do" in (cur, m) else "vang" if "vang" in (cur, m) else None
	out = {"available": True, "so_ngay": GIAY_TO_NGAY}
	for nhom in ("hd", "ksk", "attp"):
		vals = [m for (e, n), m in muc.items() if n == nhom]
		out[nhom] = {"do": vals.count("do"), "vang": vals.count("vang")}
	return out


# ─── 6. Cảnh báo của ns ──────────────────────────────────────────────────────
def _ns():
	if "ns" not in frappe.get_installed_apps():
		return None
	try:
		from ns.api import canh_bao, common
	except ImportError:
		return None
	if not (all(hasattr(canh_bao, a) for a in ("tinh", "ngu_canh", "THU_TU", "TEN"))
			and all(hasattr(common, a) for a in ("lay_nhan_vien", "lay_giay_to"))):
		return None
	return canh_bao, common


def _canh_bao() -> dict:
	mods = _ns()
	if not mods or not frappe.db.has_column("Employee", "ns_dong_bhxh") or not frappe.db.table_exists("NS Giay To"):
		return {"available": False}
	cb, common = mods
	emps = common.lay_nhan_vien({"status": ("!=", "Left")})
	gt = common.lay_giay_to([e.name for e in emps])
	ctx = cb.ngu_canh()
	dem: dict = {}
	khoan_thieu = 0
	for e in emps:
		ma = {c["ma"]: c["muc"] for c in cb.tinh(e, gt.get(e.name, []), ctx)}
		for m, muc in ma.items():
			if m in BO_MA:
				continue
			x = dem.setdefault(m, {"ma": m, "ten": cb.TEN.get(m, m), "muc": muc, "so_nguoi": 0})
			x["so_nguoi"] += 1
			if muc == "do":
				x["muc"] = "do"
		if "luong_thieu_phieu" in ma and la_khoan(e.get("department")):
			khoan_thieu += 1
	thu_tu = {m: i for i, m in enumerate(cb.THU_TU)}
	rows = sorted(dem.values(), key=lambda x: (x["muc"] != "do", thu_tu.get(x["ma"], 99)))
	t, n = ctx.get("thang_truoc") or (None, None)
	return {"available": True, "rows": rows, "khoan_thieu_phieu": khoan_thieu,
		"thang_truoc": f"{cint(n):04d}-{cint(t):02d}" if t else None}


@frappe.whitelist()
def get_overview(refresh=0):
	"""Nhân sự hiện tại + 12 tháng gần nhất (tới hôm nay) — xem docstring module.

	{available, meta: {as_of, thang, ky, k}, nhan_su, bien_dong, bhxh, luong, giay_to, canh_bao}
	"""
	_guard()
	if not frappe.db.table_exists("Employee"):
		return {"available": False, "meta": {}}
	today = getdate(nowdate())

	def build():
		y, m = today.year, today.month
		months = [_ym(*_lui(y, m, i)) for i in range(11, -1, -1)]
		ky = _ym(*_lui(y, m, 1))
		return {
			"available": True,
			"meta": {"as_of": iso(today), "thang": _nhan(months[-1]), "ky": _nhan(ky), "k": K_AN_DANH},
			"nhan_su": _nhan_su(today), "bien_dong": _bien_dong(today, months), "bhxh": _bhxh(today),
			"luong": _luong(months, ky), "giay_to": _giay_to(today), "canh_bao": _canh_bao(),
		}

	return run_cached("ns.get_overview", {"d": iso(today)}, build, refresh)
