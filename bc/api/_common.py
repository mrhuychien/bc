# -*- coding: utf-8 -*-
"""Helper dùng chung cho mọi method bc.api.* (SPEC mục 2, 3, 6).

Nguyên tắc số liệu (frappe-sales-analytics), áp ở mọi truy vấn doanh số:
- docstatus = 1 + loại hoá đơn opening (IFNULL(is_opening,'No') != 'Yes').
- Không mốc thời gian nào lấy từ CURDATE()/NOW() trong SQL: Python tính rồi truyền
  tham số (fy_range / tet_season), để "hôm nay" đồng nhất giữa các khối và test được.
- Mọi tỷ lệ guard chia 0 → None; % trả float 1 chữ số thập phân, không trả chuỗi.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_last_day, getdate, nowdate

ACCESS_ROLES = {"BC Viewer", "System Manager"}
CACHE_PREFIX = "bc:"

# Cột tiền dùng cho doanh số. [VERIFY khi đối chiếu Query Report gốc] — report cũ
# có thể dùng grand_total (gồm VAT); nếu diff lệch đúng phần thuế thì đổi ở ĐÂY,
# một chỗ duy nhất cho mọi method.
SI_AMOUNT = "si.net_total"
SII_AMOUNT = "sii.net_amount"

# Đơn vị thùng (frappe-sales-analytics luật #4).
CARTON_UOMS = ("Thùng", "Box")

OPENING_FILTER = "IFNULL(si.is_opening, 'No') != 'Yes'"


# ─── Quyền ──────────────────────────────────────────────────────────────────
def has_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Guest":
		return False
	return bool(ACCESS_ROLES & set(frappe.get_roles(user)))


def _guard():
	"""Chặn mọi user không có BC Viewer / System Manager. Gọi ở DÒNG ĐẦU mọi method."""
	if not has_access():
		frappe.throw(_("Không có quyền"), frappe.PermissionError)


# ─── Settings ───────────────────────────────────────────────────────────────
def get_settings():
	"""BC Settings (cached doc — Frappe tự xoá cache khi doc được lưu)."""
	return frappe.get_cached_doc("BC Settings")


def setting_int(field: str, default: int) -> int:
	v = get_settings().get(field)
	try:
		return int(v) if v not in (None, "") else default
	except (TypeError, ValueError):
		return default


def tet_group() -> str:
	return get_settings().tet_item_group or "Hàng Tết"


def traditional_group() -> str:
	return get_settings().traditional_item_group or "Hàng truyền thống"


def target_pct() -> float:
	v = get_settings().tet_target_pct
	return flt(v) if v not in (None, "") else 20.0


def compare_mode() -> str:
	return get_settings().tet_compare_mode or "calendar"


# ─── Cache dùng chung mọi user (dữ liệu không phụ thuộc user — đã guard role) ─
def cache_key(method: str, params: dict | None = None) -> str:
	raw = json.dumps(params or {}, sort_keys=True, default=str)
	return f"{CACHE_PREFIX}{method}:{hashlib.md5(raw.encode()).hexdigest()}"


def cached(key: str, fn, ttl: int | None = None, refresh=False):
	"""Bọc frappe.cache: refresh=1 bỏ qua cache và ghi lại. ttl mặc định = Settings."""
	ttl = setting_int("cache_ttl", 300) if ttl is None else int(ttl)
	refresh = frappe.utils.cint(refresh)
	if ttl > 0 and not refresh:
		hit = frappe.cache().get_value(key)
		if hit is not None:
			hit.setdefault("meta", {})["cached"] = True
			return hit
	value = fn()
	value.setdefault("meta", {})
	value["meta"]["cached"] = False
	value["meta"]["generated_at"] = frappe.utils.now()
	if ttl > 0:
		frappe.cache().set_value(key, value, expires_in_sec=ttl)
	return value


def clear_cache():
	frappe.cache().delete_keys(CACHE_PREFIX)


def run_cached(method: str, params: dict, fn, refresh=False):
	"""Shortcut: key theo method + params, rồi cached()."""
	return cached(cache_key(method, params), fn, refresh=refresh)


# ─── Năm tài chính (copy logic calculateDates() của dashboard KD v29) ──────────
def fy_range(today=None) -> dict:
	"""Năm TC chứa `today` + cùng kỳ năm trước (period-aligned) + cả năm trước.

	fy_start..to_date        năm nay, tính đến hôm nay (to_date = min(today, fy_end))
	sp_start..sp_end         cùng kỳ: đầu năm TC trước → cùng ngày/tháng năm trước
	ly_start..ly_end         trọn năm TC trước
	"""
	today = getdate(today or nowdate())
	m = setting_int("fy_start_month", 5)  # năm TC RVHG: 01/05 → 30/04 năm sau
	y = today.year if today.month >= m else today.year - 1
	fy_start = datetime.date(y, m, 1)
	fy_end = add_days(add_months(fy_start, 12), -1)
	to_date = min(today, getdate(fy_end))
	ly_start = getdate(add_months(fy_start, -12))
	ly_end = getdate(add_days(fy_start, -1))
	return {
		"fy_start": fy_start,
		"fy_end": getdate(fy_end),
		"to_date": to_date,
		"sp_start": ly_start,
		"sp_end": getdate(add_months(to_date, -12)),
		"ly_start": ly_start,
		"ly_end": ly_end,
	}


def fy_label(fy: dict) -> str:
	return f"{fmt_vn(fy['fy_start'])} → {fmt_vn(fy['to_date'])}"


def fmt_vn(d) -> str:
	d = getdate(d)
	return f"{d.day}/{d.month}/{d.year}"


# ─── Mùa Tết (SPEC 3b bước 2) ───────────────────────────────────────────────
def tet_dates() -> dict[int, datetime.date]:
	return {int(r.year): getdate(r.tet_date) for r in get_settings().tet_dates if r.year and r.tet_date}


def _require_tet(dates: dict, year: int) -> datetime.date:
	if year not in dates:
		frappe.throw(_("Chưa khai báo ngày Tết {0} trong BC Settings").format(year),
			title=_("Thiếu ngày Tết"))
	return dates[year]


def tet_season(today=None) -> dict:
	"""Mốc mùa Tết cho mọi truy vấn Tết. KHÔNG có CURDATE() trong SQL.

	Ứng viên = tet_date gần nhất ≥ today − 60 ngày. Nếu hôm nay còn TRƯỚC đầu mùa
	của ứng viên (giữa 2 mùa, vd tháng 6–10) → dùng Tết vừa qua, mùa đã khoá
	(between_seasons=True, asof = season_end): panel hiện "Kết quả Tết {year}".
	"""
	today = getdate(today or nowdate())
	dates = tet_dates()
	start_month = setting_int("tet_season_start_month", 11)
	limit = getdate(add_days(today, -60))
	candidates = sorted(y for y, d in dates.items() if d >= limit)
	if not candidates:
		frappe.throw(_("Chưa khai báo ngày Tết {0} trong BC Settings").format(today.year + 1),
			title=_("Thiếu ngày Tết"))
	tet_year = candidates[0]
	between = False
	if today < datetime.date(tet_year - 1, start_month, 1):
		tet_year -= 1
		between = True

	td = _require_tet(dates, tet_year)
	ly_td = _require_tet(dates, tet_year - 1)
	season_start = datetime.date(tet_year - 1, start_month, 1)
	season_end = td  # mùa kết thúc ĐÚNG mùng 1 Tết (đã chốt)
	asof = min(today, season_end)  # edge (c): xem sau Tết → số khoá ở mùng 1
	ly_asof_aligned = getdate(add_days(ly_td, -(td - asof).days))
	ly_asof_calendar = getdate(add_months(asof, -12))
	mode = compare_mode()
	upcoming = sorted(d for d in dates.values() if d >= today)
	return {
		"tet_year": tet_year,
		"tet_date": td,
		"season_start": season_start,
		"season_end": season_end,
		"asof": asof,
		"ly_tet_date": ly_td,
		"ly_season_start": datetime.date(tet_year - 2, start_month, 1),
		"ly_season_end": ly_td,
		"ly_asof_aligned": ly_asof_aligned,
		"ly_asof_calendar": ly_asof_calendar,
		"ly_asof": ly_asof_aligned if mode == "tet_aligned" else ly_asof_calendar,
		"compare_mode": mode,
		"between_seasons": between,
		"next_tet_date": upcoming[0] if upcoming else None,
	}


def sx_season(today=None) -> tuple:
	"""Mùa sản xuất Tết chứa `today`, hoặc mùa SẮP TỚI nếu đang ở khoảng nghỉ giữa 2 mùa.

	Mùa của Tết năm Y = 01/{sx_season_start_month}/(Y−1) → hết tháng {sx_season_end_month}/Y
	(mặc định 01/10 → 30/04 — mùa SX bắt đầu sớm hơn mùa bán Tết 01/11). Không cần bảng
	ngày Tết. Ví dụ 23/10/2026 → 01/10/2026 → 30/04/2027; 15/06/2026 (nghỉ) → mùa tới.
	"""
	today = getdate(today or nowdate())
	start_m = setting_int("sx_season_start_month", 10)
	end_m = setting_int("sx_season_end_month", 4)
	year = today.year + 1 if today >= datetime.date(today.year, start_m, 1) else today.year
	end = getdate(get_last_day(datetime.date(year, end_m, 1)))
	if today > end:  # khoảng nghỉ (vd T5–T10) → mùa tới
		year += 1
		end = getdate(get_last_day(datetime.date(year, end_m, 1)))
	return datetime.date(year - 1, start_m, 1), end


def sx_default_range(today=None) -> tuple:
	"""Khoảng mặc định view SX Tết: mốc cố định trong Settings (nếu có), trống thì theo sx_season()."""
	s = get_settings()
	season_from, season_to = sx_season(today)
	return (getdate(s.sx_default_from or season_from), getdate(s.sx_default_to or season_to))


def compare_mode_label(mode: str) -> str:
	return "căn theo Tết" if mode == "tet_aligned" else "theo lịch dương"


# ─── Số học ─────────────────────────────────────────────────────────────────
def pct(num, den, digits: int = 1):
	d = flt(den)
	return round(flt(num) / d * 100, digits) if d else None


def growth(cur, prev, digits: int = 1):
	p = flt(prev)
	return round((flt(cur) - p) / p * 100, digits) if p else None


def iso(d):
	return str(getdate(d)) if d else None


def iso_dict(d: dict) -> dict:
	return {k: (iso(v) if isinstance(v, (datetime.date, datetime.datetime)) else v) for k, v in d.items()}


# ─── Tên rút gọn sản phẩm (copy cleanProductName) ────────────────────────────
_SHORT_PATTERNS = [r"bánh đậu xanh", r"rồng vàng hoàng gia", r"\brvhg\b", r"hương vị"]


def short_name(name: str | None) -> str:
	s = unicodedata.normalize("NFC", name or "")
	for p in _SHORT_PATTERNS:
		s = re.sub(p, " ", s, flags=re.IGNORECASE)
	s = re.sub(r"\s+", " ", s).strip()
	s = re.sub(r"^[-–\s]+", "", s).strip()
	return s or (name or "")


# ─── Kênh (NPP / MT / Du lịch / Khác) theo Customer Group snapshot trên hoá đơn ─
CHANNEL_LABELS = {"npp": "NPP", "mt": "MT", "dulich": "Du lịch", "khac": "Khác"}
_CHANNEL_KEY = CACHE_PREFIX + "channel_map"
_KEYWORDS = (
	("npp", (r"phan phoi", r"\bnpp\b", r"dai ly")),
	("mt", (r"sieu thi", r"\bmt\b", r"modern trade", r"chuoi")),
	("dulich", (r"du lich", r"\btour")),
)


def _plain(s: str) -> str:
	s = unicodedata.normalize("NFD", (s or "").lower())
	s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
	return re.sub(r"\s+", " ", s)


def channel_map() -> dict[str, str]:
	"""{customer_group: 'npp'|'mt'|'dulich'|'khac'} — cache 10 phút.

	Ưu tiên cấu hình kênh của app pkd (PKD Settings: 3 root nested-set) nếu site có
	— đọc mềm, không phụ thuộc cứng (shipping-gotchas #22). Không có thì dò từ khoá
	trên tên nhóm và các nhóm cha. [VERIFY với CASE kênh trong report "Dashboard KD
	Kenh Ban"] — lệch thì chỉnh _KEYWORDS, không sửa từng method.
	"""
	hit = frappe.cache().get_value(_CHANNEL_KEY)
	if hit is not None:
		return hit
	groups = frappe.get_all("Customer Group", fields=["name", "parent_customer_group", "lft", "rgt"])
	mapping = {g.name: "khac" for g in groups}

	roots = {}
	if frappe.db.exists("DocType", "PKD Settings"):  # Single → không có bảng tab riêng
		try:
			for key, field in (("npp", "kenh_npp"), ("mt", "kenh_mt"), ("dulich", "kenh_dulich")):
				v = frappe.db.get_single_value("PKD Settings", field)
				if v:
					roots[key] = v
		except Exception:
			roots = {}
	if roots:
		by_name = {g.name: g for g in groups}
		for key, root in roots.items():
			node = by_name.get(root)
			if not node:
				continue
			for g in groups:
				if g.lft >= node.lft and g.rgt <= node.rgt:
					mapping[g.name] = key
	else:
		parent = {g.name: g.parent_customer_group for g in groups}
		for g in groups:
			node, seen = g.name, set()
			while node and node not in seen:
				seen.add(node)
				text = _plain(node)
				found = next((k for k, pats in _KEYWORDS if any(re.search(p, text) for p in pats)), None)
				if found:
					mapping[g.name] = found
					break
				node = parent.get(node)
	frappe.cache().set_value(_CHANNEL_KEY, mapping, expires_in_sec=600)
	return mapping


def channel_of(group: str | None) -> str:
	return channel_map().get(group or "", "khac")


def groups_of(*channels: str) -> tuple:
	"""Tuple Customer Group thuộc các kênh — dùng cho `si.customer_group IN %(g)s`.

	Luôn trả tuple ≥ 1 phần tử (IN () là lỗi cú pháp) — '\x00' không khớp nhóm nào.
	"""
	gs = tuple(g for g, k in channel_map().items() if k in channels)
	return gs or ("\x00",)


# ─── Hệ số Thùng (hộp/thùng) theo Item ───────────────────────────────────────
def carton_factors(item_codes) -> dict[str, float]:
	"""{item_code: số đơn vị kho (hộp) / 1 thùng} từ UOM Conversion Detail."""
	codes = tuple(set(item_codes))
	if not codes:
		return {}
	rows = frappe.db.sql(
		# SQL thay ORM: lấy hệ số max theo item trong 1 lượt, lọc nhiều UOM.
		"""SELECT parent AS item_code, MAX(conversion_factor) AS f
		   FROM `tabUOM Conversion Detail`
		   WHERE parenttype = 'Item' AND parent IN %(codes)s AND uom IN %(uoms)s
		   GROUP BY parent""",
		{"codes": codes, "uoms": CARTON_UOMS},
		as_dict=True,
	)
	return {r.item_code: flt(r.f) for r in rows if flt(r.f) > 0}


def to_cartons(boxes, factor) -> float:
	return round(flt(boxes) / factor, 2) if factor else 0.0


# ─── Kế hoạch (plan) theo Item — cột tuỳ biến, đọc mềm ────────────────────────
# Cột thật trên site: custom_kế_hoạch (fieldname CÓ DẤU — shipping-gotchas #3; dò cả NFC lẫn
# NFD phòng lệch chuẩn Unicode khi tạo field). Các tên ASCII sau là dự phòng. Report "Tet Ma Hang"/"Quản lý sản xuất Hàng
# Tết" có cột kế hoạch; whitelist ứng viên (identifier nội suy vào SQL nên KHÔNG lấy
# từ input). Không cột nào tồn tại → plan = 0 và meta.plan_column = None.
PLAN_COLUMNS = ("custom_kế_hoạch", "custom_kế_hoạch", "custom_ke_hoach", "custom_kehoach", "custom_ke_hoach_san_xuat", "custom_ke_hoach_sx",
	"custom_plan", "custom_ke_hoach_tet")


def plan_column() -> str | None:
	for c in PLAN_COLUMNS:
		if frappe.db.has_column("Item", c):
			return c
	return None


def plans_of(item_codes) -> dict[str, float]:
	col = plan_column()
	codes = tuple(set(item_codes))
	if not col or not codes:
		return {}
	rows = frappe.db.sql(
		f"SELECT name, `{col}` AS plan FROM `tabItem` WHERE name IN %(codes)s",  # col ∈ whitelist
		{"codes": codes}, as_dict=True)
	return {r.name: flt(r.plan) for r in rows}


# ─── Mã hàng ẩn khỏi danh sách sản phẩm (quản lý ở bc.api.hidden) ───────────
_HIDDEN_KEY = CACHE_PREFIX + "hidden_items"


def hidden_items() -> set[str]:
	"""Tập mã hàng admin đã ẩn. Cache tới khi danh sách đổi (clear_cache xoá bc:*)."""
	hit = frappe.cache().get_value(_HIDDEN_KEY)
	if hit is not None:
		return set(hit)
	codes = frappe.get_all("BC Hidden Item", filters={"parent": "BC Settings", "parenttype": "BC Settings"},
		pluck="item_code")
	frappe.cache().set_value(_HIDDEN_KEY, list(codes), expires_in_sec=3600)
	return set(codes)


def drop_hidden(rows: list, key: str = "item_code") -> list:
	"""Bỏ các dòng có mã hàng đang ẩn."""
	hid = hidden_items()
	return [r for r in rows if r.get(key) not in hid] if hid else rows

