# -*- coding: utf-8 -*-
"""bc.api.sx_hop — Báo cáo sản xuất: số hộp QC GHI theo ngày ở phần Ghi hộp của app sx (mảng `san-xuat`).

Khác SX Hàng Tết (bc.api.sx — hàng ĐÃ NHẬP KHO theo phiếu kho) và Nhập TP (bc.api.kho_nhap — phiếu nhập thủ kho duyệt):
ở đây là số hộp ĐÃ GHI LÀ ĐÓNG XONG trong ngày, trước khi vào kho.

Nguồn (chỉ đọc, đọc mềm — bc không bao giờ ghi bảng của sx):
- Ngày sản xuất = SX Ngay San Xuat docstatus < 2 (bỏ ngày đã huỷ), ngày = `ngay`.
- Bảng vào hộp = SX Bang Vao Hop docstatus < 2 có `ngay_sx` = ngày đó; dòng = SX Bang Vao Hop Item (parenttype
  'SX Bang Vao Hop'): `san_pham`, `so_hop`, `cong_nhat`, `khoan_chung`, `ten_san_pham`.
- Mọi dòng đều là hộp đã làm: dòng khoán của từng người, dòng công khoán chung (`khoan_chung`) — cả hai là "khoán" — và
  dòng công nhật (`cong_nhat`; dòng vừa công nhật vừa khoán chung tính là công nhật, như sx). Tổng ngày = đúng con số ô
  ngày của lịch tháng tab Ghi hộp mà QUẢN LÝ thấy (sx.api.lich.thang("vaohop") / _ct_vao_hop — bộ thử so vi sai với code
  sx thật). Dòng chưa chọn mã vẫn vào tổng ngày như lịch sx, nhưng không có dòng "theo mã" (rơi vào nhóm Khác).
- "Đã chốt" của một ngày = viền xanh của lịch Ghi hộp: từ D123 sx bỏ nút chốt (cờ chot_vaohop không còn ai đặt — sx
  kiemke D211), lịch tô xanh ngày có bảng vào hộp còn hiệu lực mà phần vào hộp ĐÃ ĐỒNG BỘ LƯƠNG xong: không chờ
  (`can_dong_bo_vh` = 0) và không lỗi (`loi_dong_bo_vh` trống). Ở đây theo đúng lịch đó; sx cũ chưa có hai cột này thì
  dùng chot_vaohop.
- Tên mã: Item.item_name → `ten_san_pham` trên dòng → mã. Nhóm: tet / traditional / khac như bc.api.sx._group_key (so
  đúng tên nhóm trong BC Settings; mã không còn trong danh mục → khac).
- Thùng = hộp / quy cách "Thùng" của mã (carton_factors) — như SX Hàng Tết: mã chưa khai quy cách không góp thùng nào
  (tổng thùng chỉ gồm mã có quy cách; số hộp vẫn đủ). Làm tròn 2 số lẻ MỘT lần ở mỗi số trả ra: thùng của một ngày (và
  total của get_day) = Σ hộp / quy cách chưa làm tròn của các mã trong ngày; thùng một mã = hộp tháng / quy cách; KPI thùng
  = Σ thùng các ngày ĐÃ làm tròn — dòng "Cả tháng" của bảng theo ngày đúng bằng cộng cột (lệch tối đa vài phần trăm thùng
  so với Σ thùng theo mã, vốn không cộng ra tổng được vì mã ẩn).
- Mã ẩn (Quản trị › Ẩn sản phẩm): bỏ khỏi danh sách THEO MÃ (items / rows của ngày); mọi tổng (KPI, từng ngày, nhóm,
  12 tháng, total của ngày) không đổi — như SX Hàng Tết / Nhập TP.
- Riêng tư: chỉ số hộp theo ngày × mã × loại dòng. Không đọc người, người ghi, đơn giá, tiền, bảng ăn ca, người chốt.

Tháng `thang` = 'YYYY-MM' qua kho.month_period (mặc định tháng này, tháng này cắt ở hôm nay, sai dạng / tương lai → tháng
này — như mọi màn theo tháng; Hỏi đáp chặn tháng tương lai ngay ở bc.ai.qa.check_params). `days` xếp MỚI NHẤT TRƯỚC (như
bảng trên màn): gói số của Trợ lý AI cắt mọi danh sách còn 30 phần tử đầu (prompt.MAX_LIST) — tháng 31 ngày thì ngày bị
cắt là ngày 1, không phải hôm nay. Mốc ngày truyền từ Python (không CURDATE / NOW trong SQL). Site không cài sx / thiếu bảng → available False, mọi
khối rỗng, không Error Log; lỗi bất ngờ khác → safe_block (Error Log, available False, error True).
"""

from __future__ import annotations

import calendar
import datetime
import re

import frappe
from frappe.utils import cint, flt

from bc.api import kho
from bc.api._common import (
	_guard,
	cache_key,
	carton_factors,
	drop_hidden,
	growth,
	iso,
	pct,
	run_cached,
	safe_block,
	short_name,
	tet_group,
	to_cartons,
	traditional_group,
)
from bc.api.kho_nhap import _months_back, _ym
from bc.api.sx import _group_key

DOCTYPES = ("SX Ngay San Xuat", "SX Bang Vao Hop", "SX Bang Vao Hop Item")
GROUP_ORDER = ("tet", "traditional", "khac")
MIN_DATE = datetime.date(2000, 1, 1)
_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GEN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?$")  # meta.generated_at (frappe.utils.now())

# Dòng vào hộp của ngày SX còn hiệu lực, bảng còn hiệu lực (như sx.api.lich._ngay_sx + _dong_vao_hop). Cần %(f)s %(t)s.
_FROM = """FROM `tabSX Bang Vao Hop Item` vi
		JOIN `tabSX Bang Vao Hop` b ON b.name = vi.parent AND vi.parenttype = 'SX Bang Vao Hop'
		JOIN `tabSX Ngay San Xuat` n ON n.name = b.ngay_sx
		WHERE n.docstatus < 2 AND b.docstatus < 2 AND n.ngay BETWEEN %(f)s AND %(t)s"""
# Ba phần của một dòng: công nhật (cờ công nhật, kể cả khi cũng đánh khoán chung) · khoán (mọi dòng khác) · trong khoán,
# phần công khoán chung.
_SUMS = """SUM(IFNULL(vi.so_hop, 0)) AS hop,
		SUM(CASE WHEN IFNULL(vi.cong_nhat, 0) = 1 THEN IFNULL(vi.so_hop, 0) ELSE 0 END) AS cong_nhat,
		SUM(CASE WHEN IFNULL(vi.cong_nhat, 0) = 1 THEN 0 ELSE IFNULL(vi.so_hop, 0) END) AS khoan,
		SUM(CASE WHEN IFNULL(vi.cong_nhat, 0) = 0 AND IFNULL(vi.khoan_chung, 0) = 1 THEN IFNULL(vi.so_hop, 0) ELSE 0 END)
			AS khoan_chung"""


def _on() -> bool:
	"""App sx có mặt và đủ ba bảng Ghi hộp (đọc mềm — không có thì không đụng SQL nào của sx)."""
	return kho.sx_on() and all(frappe.db.table_exists(d) for d in DOCTYPES)


def _int(v) -> int:
	return cint(flt(v))


def _month_end(d: datetime.date) -> datetime.date:
	return datetime.date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _days(f, t) -> list:
	out, d = [], f
	while d <= t:
		out.append(d)
		d += datetime.timedelta(days=1)
	return out


# ─── Đọc ─────────────────────────────────────────────────────────────────────
def _by_day_item(f, t) -> list:
	"""[{d, item, ten, hop, cong_nhat, khoan, khoan_chung}] theo (ngày, mã) trong [f, t]."""
	return frappe.db.sql(
		f"""SELECT n.ngay AS d, IFNULL(vi.san_pham, '') AS item, MAX(vi.ten_san_pham) AS ten,
		{_SUMS}
		{_FROM}
		GROUP BY n.ngay, IFNULL(vi.san_pham, '')""", {"f": f, "t": t}, as_dict=True)


def _by_day(f, t) -> dict:
	"""{date: hộp} theo ngày trong [f, t] (cho tháng trước + 12 tháng)."""
	return {_as_date(r.d): _int(r.hop) for r in frappe.db.sql(
		f"""SELECT n.ngay AS d, SUM(IFNULL(vi.so_hop, 0)) AS hop
		{_FROM}
		GROUP BY n.ngay""", {"f": f, "t": t}, as_dict=True)}


def _as_date(v) -> datetime.date:
	return v if isinstance(v, datetime.date) and not isinstance(v, datetime.datetime) else datetime.date.fromisoformat(str(v)[:10])


def _last_day(today) -> datetime.date | None:
	"""Ngày gần nhất (≤ hôm nay) có hộp — để màn gợi ý khi tháng chọn trống."""
	r = frappe.db.sql(
		f"""SELECT MAX(x.d) FROM (
			SELECT n.ngay AS d, SUM(IFNULL(vi.so_hop, 0)) AS hop
			{_FROM}
			GROUP BY n.ngay HAVING SUM(IFNULL(vi.so_hop, 0)) > 0) x""", {"f": MIN_DATE, "t": today})
	return _as_date(r[0][0]) if r and r[0][0] else None


def _chot(f, t) -> set:
	"""Ngày (date) đã chốt vào hộp trong [f, t] — viền xanh của lịch Ghi hộp (xem docstring module)."""
	if frappe.db.has_column("SX Ngay San Xuat", "can_dong_bo_vh") and frappe.db.has_column("SX Ngay San Xuat",
			"loi_dong_bo_vh"):
		# CHAR_LENGTH thay "= ''": chuỗi chỉ có khoảng trắng vẫn là "có lỗi" như Python (so sánh PAD SPACE của MariaDB thì không).
		dk = "IFNULL(n.can_dong_bo_vh, 0) = 0 AND CHAR_LENGTH(IFNULL(n.loi_dong_bo_vh, '')) = 0"
	elif frappe.db.has_column("SX Ngay San Xuat", "chot_vaohop"):
		dk = "IFNULL(n.chot_vaohop, 0) = 1"
	else:
		return set()
	return {_as_date(d) for (d,) in frappe.db.sql(
		f"""SELECT DISTINCT n.ngay FROM `tabSX Ngay San Xuat` n
		WHERE n.docstatus < 2 AND n.ngay BETWEEN %(f)s AND %(t)s AND {dk}
			AND EXISTS (SELECT 1 FROM `tabSX Bang Vao Hop` b WHERE b.ngay_sx = n.name AND b.docstatus < 2)""",
		{"f": f, "t": t})}


def _items(codes) -> dict:
	"""{mã: {item_name, item_group}} — chỉ tên + nhóm."""
	codes = kho.in_tuple(codes)
	if codes == ("\x00",):
		return {}
	return {r.name: r for r in frappe.db.sql(
		"SELECT name, item_name, item_group FROM `tabItem` WHERE name IN %(c)s", {"c": codes}, as_dict=True)}


# ─── Gộp ─────────────────────────────────────────────────────────────────────
def _item_rows(raw: list) -> dict:
	"""{mã: {hop, khoan, khoan_chung, cong_nhat, ten, days: set}} gộp từ _by_day_item (bỏ dòng chưa chọn mã)."""
	out: dict = {}
	for r in raw:
		if not r.item:
			continue
		g = out.setdefault(r.item, {"hop": 0, "khoan": 0, "khoan_chung": 0, "cong_nhat": 0, "ten": None, "days": set()})
		for k in ("hop", "khoan", "khoan_chung", "cong_nhat"):
			g[k] += _int(r[k])
		g["ten"] = g["ten"] or r.ten
		if _int(r.hop) > 0:
			g["days"].add(_as_date(r.d))
	return out


def _describe(code: str, g: dict, info: dict) -> dict:
	it = info.get(code) or {}
	name = it.get("item_name") or g.get("ten") or code
	return {"item_code": code, "item_name": name, "short_name": short_name(name), "group": _gkey(it.get("item_group"))}


def _gkey(item_group) -> str:
	k = _group_key(item_group) if item_group else "other"
	return "khac" if k == "other" else k


def _group_label(key: str) -> str:
	return {"tet": tet_group(), "traditional": traditional_group()}.get(key, "Khác")


def _thung(hop, factor) -> float:
	"""Thùng CHƯA làm tròn (to_cartons làm tròn 2 số lẻ — chỉ dùng cho số trả ra từng mã)."""
	return flt(hop) / factor if factor else 0.0


def _tb(hop, so_ngay) -> float:
	return round(flt(hop) / so_ngay, 1) if so_ngay else 0


def _empty_overview(meta: dict, error: bool = False) -> dict:
	out = {"available": False, "meta": meta, "kpis": {}, "days": [], "items": [], "groups": [], "trend": []}
	if error:
		out["error"] = True
	return out


def _overview(p: dict) -> dict:
	f, t, today = p["f"], p["t"], p["today"]
	raw = _by_day_item(f, t)
	codes = {r.item for r in raw if r.item}
	info = _items(codes)
	factors = carton_factors(codes)
	chot = _chot(f, t)

	# Từng ngày (mọi dòng, kể cả mã ẩn / chưa chọn mã)
	per_day: dict = {}
	for r in raw:
		d = _as_date(r.d)
		x = per_day.setdefault(d, {"hop": 0, "khoan": 0, "cong_nhat": 0, "thung": 0.0, "ma": set()})
		for k in ("hop", "khoan", "cong_nhat"):
			x[k] += _int(r[k])
		x["thung"] += _thung(r.hop, factors.get(r.item)) if r.item else 0.0
		if r.item and _int(r.hop) != 0:
			x["ma"].add(r.item)
	days = []
	for d in reversed(_days(f, t)):  # mới nhất trước — xem docstring module
		x = per_day.get(d)
		days.append({"date": iso(d), "weekday": d.weekday(), "hop": x["hop"] if x else 0, "khoan": x["khoan"] if x else 0,
			"cong_nhat": x["cong_nhat"] if x else 0, "thung": round(x["thung"], 2) if x else 0.0,
			"so_ma": len(x["ma"]) if x else 0, "chot": d in chot, "co": x is not None})

	# Theo mã
	g_items = _item_rows(raw)
	total = sum(x["hop"] for x in days)
	items = []
	for code, g in g_items.items():
		if g["hop"] == 0:
			continue
		nd = len(g["days"])
		items.append({**_describe(code, g, info), "hop": g["hop"], "khoan": g["khoan"], "cong_nhat": g["cong_nhat"],
			"thung": to_cartons(g["hop"], factors.get(code)), "pct": pct(g["hop"], total), "so_ngay": nd,
			"tb_ngay": _tb(g["hop"], nd)})
	thung = round(sum(x["thung"] for x in days), 2)  # = cộng cột thùng của bảng theo ngày (gồm mã ẩn)
	so_ma = len(items)
	by_group = {k: 0 for k in GROUP_ORDER}
	for x in items:
		by_group[x["group"]] += x["hop"]
	by_group["khac"] += sum(_int(r.hop) for r in raw if not r.item)  # dòng chưa chọn mã
	items = drop_hidden(items)
	items.sort(key=lambda x: (-x["hop"], x["item_code"]))
	groups = [{"key": k, "label": _group_label(k), "hop": by_group[k], "pct": pct(by_group[k], total)} for k in GROUP_ORDER]

	# Tháng trước (cùng khoảng ngày + trọn tháng) và 12 tháng — một lượt theo ngày
	f12 = p["f12"]
	daily = _by_day(f12, t)
	pf = p["prev"]
	pe = _month_end(pf)
	ps = datetime.date(pf.year, pf.month, min(t.day, pe.day))
	prev_hop = sum(v for d, v in daily.items() if pf <= d <= ps)
	prev_full = sum(v for d, v in daily.items() if pf <= d <= pe)
	trend = []
	for m in p["m12"]:
		me = min(_month_end(m), t)
		vals = [v for d, v in daily.items() if m <= d <= me]
		hop = sum(vals)
		nd = sum(1 for v in vals if v > 0)
		trend.append({"thang": _ym(m), "hop": hop, "so_ngay": nd, "tb_ngay": _tb(hop, nd)})

	cn = sum(x["cong_nhat"] for x in days)
	co_hop = [x for x in days if x["hop"] > 0]
	cuoi = co_hop[0] if co_hop else None  # days mới nhất trước
	kpis = {
		"hop": total, "thung": thung, "khoan": sum(x["khoan"] for x in days), "cong_nhat": cn,
		"cong_nhat_pct": pct(cn, total), "so_ngay": len(co_hop), "tb_ngay": _tb(total, len(co_hop)), "so_ma": so_ma,
		"ngay_cuoi": {"date": cuoi["date"], "hop": cuoi["hop"]} if cuoi else None,
		"chua_chot": sum(1 for x in co_hop if not x["chot"]),
		"prev_hop": prev_hop, "prev_full": prev_full, "growth_pct": growth(total, prev_hop),
	}
	return {"available": True, "last_day": iso(_last_day(today)), "kpis": kpis, "days": days, "items": items,
		"groups": groups, "trend": trend}


@frappe.whitelist()
def get_overview(thang=None, refresh=0):
	"""Số hộp đã ghi theo ngày của tháng `thang` ('YYYY-MM', mặc định tháng này, cắt ở hôm nay) — xem docstring module.

	{available, meta: {thang, from, to, as_of, prev, months (12, cũ trước), sx, last_day},
	 kpis: {hop, thung, khoan, cong_nhat, cong_nhat_pct, so_ngay, tb_ngay, so_ma, ngay_cuoi, chua_chot, prev_hop, prev_full,
	        growth_pct},
	 days: [{date, weekday (T2 = 0), hop, khoan, cong_nhat, thung, so_ma, chot, co}] — mỗi ngày từ `to` lùi về `from`
	       (mới nhất trước),
	 items: [{item_code, item_name, short_name, group, hop, khoan, cong_nhat, thung, pct, so_ngay, tb_ngay}] — hộp giảm dần,
	 groups: [{key, label, hop, pct}] (tet, traditional, khac), trend: [{thang, hop, so_ngay, tb_ngay}] (12 tháng)}
	so_ngay = số ngày có hộp; prev_hop = tháng trước từ ngày 1 tới cùng ngày-trong-tháng của `to` (kẹp cuối tháng)."""
	_guard("san-xuat")
	f, t, label = kho.month_period(thang)
	today = kho.today()

	def build():
		m12 = _months_back(f, 11)
		prev = _months_back(f, 1)[0]
		sx = _on()
		meta = {"thang": label, "from": iso(f), "to": iso(t), "as_of": iso(today), "prev": _ym(prev),
			"months": [_ym(m) for m in m12], "sx": sx, "last_day": None}
		if not sx:
			return _empty_overview(meta)
		r = safe_block("sx_hop.get_overview", _overview,
			{"f": f, "t": t, "today": today, "f12": m12[0], "m12": m12, "prev": prev})
		if not r.get("available"):
			return _empty_overview(meta, error=True)
		meta["last_day"] = r.pop("last_day")
		return {"available": True, "meta": meta, **{k: r[k] for k in ("kpis", "days", "items", "groups", "trend")}}

	return run_cached("sx_hop.get_overview", {"t": label, "d": iso(today)}, build, refresh)


def _parse_date(date, today) -> datetime.date:
	"""'YYYY-MM-DD' hợp lệ trong [01/01/2000, hôm nay]; sai dạng / ngày tương lai / quá cũ → hôm nay (không ném lỗi)."""
	s = str(date or "")[:10]
	if _NGAY.match(s):
		try:
			d = datetime.date.fromisoformat(s)
		except ValueError:
			d = None
		if d and MIN_DATE <= d <= today:
			return d
	return today


def _day(d) -> dict:
	raw = _by_day_item(d, d)
	codes = {r.item for r in raw if r.item}
	info = _items(codes)
	factors = carton_factors(codes)
	tot = {"hop": sum(_int(r.hop) for r in raw), "khoan": sum(_int(r.khoan) for r in raw),
		"cong_nhat": sum(_int(r.cong_nhat) for r in raw),
		# như thùng của ngày ở get_overview: làm tròn một lần trên tổng chưa làm tròn (gồm mã ẩn)
		"thung": round(sum(_thung(r.hop, factors.get(r.item)) for r in raw if r.item), 2)}
	rows = []
	for code, g in _item_rows(raw).items():
		if g["hop"] == 0:
			continue
		rows.append({**_describe(code, g, info), "hop": g["hop"], "khoan": g["khoan"], "khoan_chung": g["khoan_chung"],
			"cong_nhat": g["cong_nhat"], "thung": to_cartons(g["hop"], factors.get(code)), "pct": pct(g["hop"], tot["hop"])})
	rows = drop_hidden(rows)
	rows.sort(key=lambda x: (-x["hop"], x["item_code"]))
	return {"available": True, "meta": {"date": iso(d), "chot": d in _chot(d, d), "co": bool(raw)}, "rows": rows,
		"total": tot}


def _older(hit, since) -> bool:
	"""Bản cache `hit` tính KHÔNG sau mốc `since` ('YYYY-MM-DD HH:MM:SS[.ffffff]') — mốc sai dạng → False (giữ cache)."""
	try:
		mine = datetime.datetime.fromisoformat(str(((hit or {}).get("meta") or {}).get("generated_at") or ""))
		moc = datetime.datetime.fromisoformat(str(since)) if _GEN.match(str(since)) else None
	except ValueError:
		return False
	return moc is not None and mine <= moc


@frappe.whitelist()
def get_day(date=None, refresh=0, since=None):
	"""Chi tiết một ngày theo mã ('YYYY-MM-DD', mặc định hôm nay; sai dạng / tương lai → hôm nay).

	{available, meta: {date, chot, co}, rows: [{item_code, item_name, short_name, group, hop, khoan, khoan_chung,
	 cong_nhat, thung, pct}] — hộp giảm dần, mã ẩn bỏ, total: {hop, khoan, cong_nhat, thung} — gồm cả mã ẩn}.
	khoan gồm khoan_chung. `since` = meta.generated_at của get_overview màn đang hiện: bản cache của ngày tính KHÔNG
	sau mốc đó thì tính lại — chi tiết mở ra không bao giờ cũ hơn dòng ngày trên màn (kể cả sau Làm mới)."""
	_guard("san-xuat")
	today = kho.today()
	d = _parse_date(date, today)
	params = {"d": iso(d), "today": iso(today)}
	if not cint(refresh) and since and _older(frappe.cache().get_value(cache_key("sx_hop.get_day", params)), since):
		refresh = 1

	def build():
		empty = {"available": False, "meta": {"date": iso(d), "chot": False, "co": False}, "rows": [], "total": {}}
		if not _on():
			return empty
		r = safe_block("sx_hop.get_day", _day, d)
		return r if r.get("available") else {**empty, "error": True}

	return run_cached("sx_hop.get_day", params, build, refresh)
