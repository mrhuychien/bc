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

GHI HỘP SO VỚI NHẬP KHO (get_compare, cùng tháng `thang`) — sx coi hai chứng từ là độc lập (khotp, D62: ghi hộp trả
lương, phiếu nhập sinh tồn); ở đây chỉ đặt cạnh nhau, theo đúng ba chỗ sx tự đối chiếu, không thêm luật thứ tư:
- Ghi hộp = đúng số hộp ở trên (_FROM / _by_day_item), theo NGÀY SẢN XUẤT.
- Nhập kho = phiếu SX Phieu Nhap TP thủ kho ĐÃ DUYỆT (docstatus 1) theo NGÀY NHẬN `ngay`, số = Σ so_dem của dòng
  (parenttype 'SX Phieu Nhap TP', parentfield 'dong') — đúng K11 của bc.api.kho_nhap (_nhap): tổng tháng và từng ngày
  bằng màn Nhập TP (bộ thử so vi sai). Phiếu nháp (kể cả phiếu nháp Tết) và phiếu huỷ không phải nhập kho.
- Chênh lệch = nhập kho − ghi hộp, theo mã — đúng dấu của sx.api.portal._vao_hop_vs_nhap_kho (bảng đối chiếu kho của
  Quản lý): âm = đã ghi hộp mà chưa nhập kho (bình thường khi hàng còn ở xưởng), dương = kho nhận vượt số ghi (thường
  ghi sót). sx cắt so_dem bằng cint; bc giữ số lẻ (flt, làm tròn 2 số lẻ MỘT lần lúc trả) — số nguyên thì trùng khớp.
- Đơn vị: so_hop là HỘP, so_dem theo đơn vị kho của mã. Mã có đơn vị kho khác "Hộp" (kho_nhap.BOX_UOM; mã không còn
  trong danh mục cũng tính là khác) vẫn liệt kê (khac_dvt) nhưng ra khỏi CẢ HAI vế của mọi tổng và mọi dòng ngày.
- Dòng ghi hộp chưa chọn mã: vẫn là hộp → vào ghi hộp của ngày / tháng, không phiếu nào khớp được → hop_chua_ma (nằm
  trong chua_nhap). Dòng phiếu không mã: không đối chiếu được, không cộng (như mã khác đơn vị).
- Mã ẩn: chỉ mất khỏi danh sách theo mã; mọi tổng và số đếm mã giữ nguyên.
- "Hiện tại" (tính tới HÔM NAY, không theo tháng chọn), mỗi khối một safe_block:
  cho_nhap = kho_nhap._vao_hop (port khotp.tran_con_lai / cho_nhan: 30 ngày tới hôm nay, trừ phiếu nháp Tết; mốc tính nợ
  vào hộp D230 đang áp → từ mốc + phần mang sang, kèm moc / mang_sang) — cùng số với khối "đã vào hộp chưa nhập kho" của
  màn Nhập TP; cho_duyet = kho_nhap._cho_duyet rút gọn (phiếu nháp chờ thủ
  kho); no_vao_hop = sổ SX No Vao Hop sx tự ghi khi phiếu nhận vượt số ghi (khotp.ghi_no_vao_hop /
  doi_soat_no_vao_hop / so_no_vao_hop): dòng đang mở trang_thai 'Chờ chấm' còn con_lai > EPS, gom theo mã, tuổi tính
  từ ngày nợ cũ nhất (đọc mềm — thiếu bảng / cột → khối đó available False). con_lai theo đơn vị kho của từng mã → số,
  số mã, số dòng, cũ nhất chỉ trên mã đơn vị Hộp; mã khác đơn vị đếm riêng (so_ma_khac_dvt), đứng cuối danh sách.
- Làm tròn 2 số lẻ MỘT lần từ số gốc ở mọi số lượng (kể cả cho_nhap / cho_duyet: lấy số chưa làm tròn của kho_nhap, không
  làm tròn 3 số lẻ rồi 2 số lẻ). chua_nhap / nhap_vuot = Σ max(0, hop − nhap) / Σ max(0, nhap − hop) trên MỌI mã đơn
  vị Hộp, nên lech = nhap_vuot − chua_nhap đúng cả sau làm tròn (_chia_lech dời 0,01 khi hai lần làm tròn lệch nhau).
  Số đếm mã (chưa nhập / nhập vượt / khớp) xếp theo lệch ĐÃ làm tròn — cùng ngưỡng với màn;
  mã khác đơn vị có lech None (nhập theo Kg / Gói trừ số hộp không phải lệch hộp). Ngày chỉ có dòng không so được (mã khác
  đơn vị, dòng phiếu không mã) không "co".
- Riêng tư như trên: chỉ mã, ngày, số lượng. Không đọc người lập / duyệt / xử lý, chú thích tự do, lý do, tên chứng
  từ; không trả tên phiếu hay tên dòng nợ.
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
from bc.api.kho_nhap import BOX_UOM, EPS, LIST_MAX, SO_NGAY_TRAN, _cho_duyet, _months_back, _vao_hop, _ym
from bc.api.sx import _group_key

DOCTYPES = ("SX Ngay San Xuat", "SX Bang Vao Hop", "SX Bang Vao Hop Item")
NHAP_DOCTYPES = ("SX Phieu Nhap TP", "SX Phieu Nhap TP Item")   # phiếu nhập kho thành phẩm của sx
NO_VH = "SX No Vao Hop"                                         # sổ nợ vào hộp của sx (khotp, D101)
CHO_CHAM = "Chờ chấm"                                           # SX No Vao Hop.trang_thai đang mở
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


# ─── Ghi hộp so với nhập kho (get_compare) — xem docstring module ───────────
def _on_compare() -> bool:
	"""sx có mặt, đủ ba bảng Ghi hộp và hai bảng phiếu nhập kho thành phẩm."""
	return _on() and all(frappe.db.table_exists(d) for d in NHAP_DOCTYPES)


def _r2(v) -> float:
	"""Làm tròn 2 số lẻ một lần lúc trả (+ 0.0: không bao giờ trả −0.0)."""
	return round(flt(v), 2) + 0.0


def _chia_lech(chua_nhap: float, nhap_vuot: float, lech2: float) -> tuple:
	"""(chua_nhap, nhap_vuot) làm tròn 2 số lẻ sao cho nhap_vuot − chua_nhap = lech2 (lệch tổng đã làm tròn) ĐÚNG như
	thẻ hiện. Mỗi số làm tròn một lần từ số gốc; hai lần làm tròn độc lập có thể lệch nhau 0,01 so với lech2 (gốc 0,005 −
	0,3749 = −0,3699 → −0,37 mà 0,01 − 0,37 = −0,36) — khi đó dời 0,01 ở số có sai số làm tròn lớn hơn theo chiều cần dời
	(mỗi số vẫn cách số gốc không quá 0,01, không âm)."""
	c2, v2 = _r2(chua_nhap), _r2(nhap_vuot)
	d = round(v2 - c2 - lech2, 2)
	if not d:
		return c2, v2
	v_moi, c_moi = _r2(v2 - d), _r2(c2 + d)
	if v_moi < 0 or (c_moi >= 0 and abs(c_moi - chua_nhap) < abs(v_moi - nhap_vuot)):
		return c_moi, v2
	return c2, v_moi


def _nhap_by_day_item(f, t) -> list:
	"""[{d, item, qty}] — Σ so_dem của phiếu nhập ĐÃ DUYỆT theo (ngày nhận, mã) trong [f, t] (như kho_nhap._nhap)."""
	return frappe.db.sql(
		"""SELECT p.ngay AS d, IFNULL(i.item, '') AS item, SUM(IFNULL(i.so_dem, 0)) AS qty
		FROM `tabSX Phieu Nhap TP` p
		JOIN `tabSX Phieu Nhap TP Item` i
			ON i.parent = p.name AND i.parenttype = 'SX Phieu Nhap TP' AND i.parentfield = 'dong'
		WHERE p.docstatus = 1 AND p.ngay BETWEEN %(f)s AND %(t)s
		GROUP BY p.ngay, IFNULL(i.item, '')""", {"f": f, "t": t}, as_dict=True)


def _empty_compare(meta: dict, error: bool = False) -> dict:
	off = {"available": False}
	out = {"available": False, "meta": meta, "total": {}, "days": [], "items": [], "cho_nhap": dict(off),
		"cho_duyet": dict(off), "no_vao_hop": dict(off)}
	if error:
		out["error"] = True
	return out


def _compare(p: dict) -> dict:
	f, t = p["f"], p["t"]
	hop_raw = _by_day_item(f, t)
	nhap_raw = _nhap_by_day_item(f, t)
	codes = {r.item for r in hop_raw if r.item} | {r.item for r in nhap_raw if r.item}
	info = _items(codes)
	uoms = {c: x.stock_uom for c, x in kho.item_info(codes).items()}

	def box(code) -> bool:
		return uoms.get(code) == BOX_UOM

	# Theo mã (mọi mã, kể cả mã ẩn / khác đơn vị) và theo ngày (chỉ phần so được: mã đơn vị Hộp + dòng chưa chọn mã)
	g_items: dict = {}
	per_day: dict = {}
	hop_chua_ma = 0
	# Ngày chỉ "có" (co) khi có dòng SO ĐƯỢC — ngày chỉ có mã khác đơn vị / dòng phiếu không mã không thành dòng 0 · 0 · 0
	# trông như "khớp" trên bảng Theo ngày.
	def day(v) -> dict:
		return per_day.setdefault(_as_date(v), {"hop": 0, "nhap": 0.0})

	for r in hop_raw:
		if not r.item:
			hop_chua_ma += _int(r.hop)
			day(r.d)["hop"] += _int(r.hop)
			continue
		g = g_items.setdefault(r.item, {"hop": 0, "nhap": 0.0, "ten": None})
		g["hop"] += _int(r.hop)
		g["ten"] = g["ten"] or r.ten
		if box(r.item):
			day(r.d)["hop"] += _int(r.hop)
	for r in nhap_raw:
		if not r.item:
			continue  # dòng phiếu không mã: không đối chiếu được
		g = g_items.setdefault(r.item, {"hop": 0, "nhap": 0.0, "ten": None})
		g["nhap"] += flt(r.qty)
		if box(r.item):
			day(r.d)["nhap"] += flt(r.qty)

	# Tổng (gồm mã ẩn), cộng trên số CHƯA làm tròn, làm tròn một lần lúc trả. SỐ MÃ xếp nhóm theo lệch ĐÃ làm tròn 2 số lẻ
	# — đúng số màn hiện ở bảng / chip: mã lệch 0,004 là "0 · khớp" ở mọi chỗ (không vừa "khớp" trong bảng vừa "nhập vượt
	# (1 mã)" ở thẻ); mã có hộp 0 và nhập làm tròn 0 không thành dòng, không vào số đếm. SỐ LƯỢNG chua_nhap / nhap_vuot thì
	# cộng max(0, ∓lệch gốc) của MỌI mã đơn vị Hộp (cả mã "khớp" lẫn mã không thành dòng) — nên lech = nhap_vuot − chua_nhap
	# đúng trên số gốc (ba mã +0,004 → nhập vượt 0,01 hộp, 0 mã), và đúng cả sau làm tròn (xem _chia_lech).
	tot = {"hop": hop_chua_ma, "nhap": 0.0, "chua_nhap": float(hop_chua_ma), "so_ma_chua_nhap": 0, "nhap_vuot": 0.0,
		"so_ma_nhap_vuot": 0, "so_ma_khop": 0, "ma_khac_dvt": 0, "hop_khac_dvt": 0}
	items = []
	for code, g in g_items.items():
		lech = g["nhap"] - g["hop"]
		khac = not box(code)
		if not khac:  # tổng số lượng: mọi dòng so được, kể cả mã "khớp" và mã không thành dòng
			tot["hop"] += g["hop"]
			tot["nhap"] += g["nhap"]
			tot["chua_nhap"] += max(0.0, -lech)
			tot["nhap_vuot"] += max(0.0, lech)
		if g["hop"] == 0 and _r2(g["nhap"]) == 0:
			continue
		l2 = _r2(lech)
		if khac:
			tot["ma_khac_dvt"] += 1
			tot["hop_khac_dvt"] += g["hop"]
		elif l2 < 0:
			tot["so_ma_chua_nhap"] += 1
		elif l2 > 0:
			tot["so_ma_nhap_vuot"] += 1
		else:
			tot["so_ma_khop"] += 1
		# Mã khác đơn vị: nhập (Kg / Gói…) trừ hộp không phải số hộp lệch → lech None (màn "—", Trợ lý AI không trích được).
		items.append({**_describe(code, g, info), "uom": uoms.get(code), "khac_dvt": khac, "hop": g["hop"],
			"nhap": _r2(g["nhap"]), "lech": None if khac else l2, "_lech": 0.0 if khac else lech})
	items = drop_hidden(items)
	items.sort(key=lambda x: (x["khac_dvt"], -abs(x["_lech"]), -x["hop"], x["item_code"]))  # thứ tự sx: |lệch| lớn trước
	for x in items:
		del x["_lech"]
	lech = tot["nhap"] - tot["hop"]
	chua_nhap, nhap_vuot = _chia_lech(tot["chua_nhap"], tot["nhap_vuot"], _r2(lech))
	total = {"hop": tot["hop"], "nhap": _r2(tot["nhap"]), "lech": _r2(lech),
		"lech_pct": round(lech / tot["hop"] * 100, 1) + 0.0 if tot["hop"] else None,
		"chua_nhap": chua_nhap, "so_ma_chua_nhap": tot["so_ma_chua_nhap"],
		"nhap_vuot": nhap_vuot, "so_ma_nhap_vuot": tot["so_ma_nhap_vuot"], "so_ma_khop": tot["so_ma_khop"],
		"hop_chua_ma": hop_chua_ma, "ma_khac_dvt": tot["ma_khac_dvt"], "hop_khac_dvt": tot["hop_khac_dvt"]}

	# Từng ngày lịch, luỹ kế từ `from`; trả mới nhất trước (như get_overview.days)
	days, luy_ke = [], 0.0
	for d in _days(f, t):
		x = per_day.get(d)
		hop = x["hop"] if x else 0
		nhap = x["nhap"] if x else 0.0
		luy_ke += nhap - hop
		days.append({"date": iso(d), "weekday": d.weekday(), "hop": hop, "nhap": _r2(nhap), "lech": _r2(nhap - hop),
			"luy_ke": _r2(luy_ke), "co": x is not None})
	days.reverse()
	return {"available": True, "total": total, "days": days, "items": items}


def _cho_nhap(p: dict) -> dict:
	"""kho_nhap._vao_hop rút gọn: cùng con số với khối "đã vào hộp chưa nhập kho" của màn Nhập TP; chỉ dòng đơn vị Hộp."""
	raw: dict = {}
	v = _vao_hop(p, raw)
	if not v.get("available"):
		return {"available": False}
	box = raw.get("box") or {}  # số còn lại CHƯA làm tròn (kho_nhap trả 3 số lẻ) — làm tròn 2 số lẻ một lần ở đây
	rows = [r for r in v["rows"] if not r.get("khac_dvt")][:LIST_MAX]
	info = kho.item_info([r["item_code"] for r in rows])
	return {"available": True, "from": v["from"], "to": v["to"], "so_ngay": v["so_ngay"], "qty": _r2(sum(box.values())),
		"items": v["items"],
		# D230: mốc tính nợ vào hộp đang áp (ISO | None) + phần mang sang (2 số lẻ từ số gốc; None khi không áp mốc)
		"moc": v.get("moc"), "mang_sang": _r2(raw["mang_sang"]) if v.get("moc") else None,
		"rows": [{"item_code": r["item_code"], "item_name": (info.get(r["item_code"]) or {}).get("item_name") or r["item_code"],
			"short_name": r["short_name"], "qty": _r2(box.get(r["item_code"], r["qty"]))} for r in rows]}


def _cho_duyet_gon(p: dict) -> dict:
	"""kho_nhap._cho_duyet rút gọn (phiếu nháp chờ thủ kho duyệt) — chỉ số đếm, không danh sách, không tên phiếu."""
	raw: dict = {}
	v = _cho_duyet(p, raw)
	if not v.get("available"):
		return {"available": False}
	out = {"available": True, **{k: v[k] for k in ("count", "count_tet", "qty", "uom", "oldest_age_days")}}
	if out["qty"] is not None:  # lẫn đơn vị → None như màn Nhập TP; cùng đơn vị → 2 số lẻ từ số gốc, làm tròn một lần
		out["qty"] = _r2(sum(flt(q) for q in (raw.get("qty") or {}).values() if abs(flt(q)) > EPS))
	return out


def _no_vao_hop(p: dict) -> dict:
	"""Nợ vào hộp đang mở (SX No Vao Hop 'Chờ chấm', con_lai > EPS) gom theo mã — như sx khotp.so_no_vao_hop."""
	if not frappe.db.table_exists(NO_VH) or not all(frappe.db.has_column(NO_VH, c) for c in
			("item", "con_lai", "ngay", "trang_thai")):
		return {"available": False}
	today = p["today"]
	raw = frappe.db.sql(
		"""SELECT IFNULL(nv.item, '') AS item, SUM(IFNULL(nv.con_lai, 0)) AS qty, COUNT(*) AS so_dong, MIN(nv.ngay) AS ngay
		FROM `tabSX No Vao Hop` nv
		WHERE nv.trang_thai = %(cho)s AND IFNULL(nv.con_lai, 0) > %(eps)s
		GROUP BY IFNULL(nv.item, '')""", {"cho": CHO_CHAM, "eps": EPS}, as_dict=True)
	info = kho.item_info({r.item for r in raw if r.item})
	rows = []
	for r in raw:
		ngay = _as_date(r.ngay) if r.ngay else today
		it = info.get(r.item) or {}
		rows.append({"item_code": r.item, "item_name": it.get("item_name") or r.item,
			"short_name": it.get("short_name") or r.item, "qty": flt(r.qty), "so_dong": cint(r.so_dong), "ngay": ngay,
			"age_days": max((today - ngay).days, 0), "khac_dvt": it.get("stock_uom") != BOX_UOM})
	# con_lai theo đơn vị kho của TỪNG mã (sx so so_dem với số hộp chấm cả với mã Kg / Gói): như sx so_no_vao_hop không cộng
	# lẫn mã — ở đây số / số mã / số dòng / cũ nhất chỉ trên mã đơn vị Hộp (như cho_nhap); mã khác đơn vị chỉ đếm riêng và
	# đứng cuối danh sách (khac_dvt).
	box = [x for x in rows if not x["khac_dvt"]]
	oldest = min((x["ngay"] for x in box), default=None)
	lst = drop_hidden(rows)
	lst.sort(key=lambda x: (x["khac_dvt"], -x["age_days"], -x["qty"], x["item_code"]))
	return {"available": True, "count": sum(x["so_dong"] for x in box), "so_ma": len(box),
		"qty": _r2(sum(x["qty"] for x in box)), "so_ma_khac_dvt": len(rows) - len(box),
		"oldest_date": iso(oldest), "oldest_age_days": max((today - oldest).days, 0) if oldest else None,
		"rows": [{**x, "qty": _r2(x["qty"]), "ngay": iso(x["ngay"])} for x in lst[:LIST_MAX]]}


@frappe.whitelist()
def get_compare(thang=None, refresh=0):
	"""Ghi hộp so với nhập kho của tháng `thang` ('YYYY-MM', mặc định tháng này, cắt ở hôm nay) + ba số tồn đọng tính
	tới hôm nay — xem docstring module (phần GHI HỘP SO VỚI NHẬP KHO).

	{available, meta: {thang, from, to, as_of, sx, so_ngay_cho},
	 total: {hop, nhap, lech, lech_pct, chua_nhap, so_ma_chua_nhap, nhap_vuot, so_ma_nhap_vuot, so_ma_khop, hop_chua_ma,
	         ma_khac_dvt, hop_khac_dvt} — chỉ phần so được; lech = nhap − hop = nhap_vuot − chua_nhap (đúng cả sau làm
         tròn; số lượng cộng mọi mã, số mã theo lệch đã làm tròn),
	 days: [{date, weekday (T2 = 0), hop, nhap, lech, luy_ke, co}] — mỗi ngày từ `to` lùi về `from` (mới nhất trước),
	 items: [{item_code, item_name, short_name, group, uom, khac_dvt, hop, nhap, lech}] — khác đơn vị cuối (lech None),
        |lệch| giảm dần,
	 cho_nhap: {available, from, to, so_ngay, qty, items, moc, mang_sang, rows: [{item_code, item_name, short_name, qty}]},
	 cho_duyet: {available, count, count_tet, qty, uom, oldest_age_days},
	 no_vao_hop: {available, count, so_ma, qty, so_ma_khac_dvt, oldest_date, oldest_age_days — chỉ mã đơn vị Hộp,
	              rows: [{item_code, item_name, short_name, qty, so_dong, ngay, age_days, khac_dvt}] — khác đơn vị cuối}}"""
	_guard("san-xuat")
	f, t, label = kho.month_period(thang)
	today = kho.today()

	def build():
		# meta.sx cùng nghĩa với get_overview (sx + ba bảng Ghi hộp): màn chỉ ẩn khối khi phần trên đã báo "chưa cài sx";
		# thiếu riêng bảng phiếu nhập → available False, meta.sx True (màn báo "chưa đối chiếu được").
		sx = _on()
		meta = {"thang": label, "from": iso(f), "to": iso(t), "as_of": iso(today), "sx": sx, "so_ngay_cho": SO_NGAY_TRAN}
		if not sx or not _on_compare():
			return _empty_compare(meta)
		p = {"f": f, "t": t, "today": today}
		r = safe_block("sx_hop.get_compare", _compare, p)
		out = {"available": True, "meta": meta, **{k: r[k] for k in ("total", "days", "items")}} if r.get("available") \
			else _empty_compare(meta, error=True)
		out["cho_nhap"] = safe_block("sx_hop.get_compare.cho_nhap", _cho_nhap, p)
		out["cho_duyet"] = safe_block("sx_hop.get_compare.cho_duyet", _cho_duyet_gon, p)
		out["no_vao_hop"] = safe_block("sx_hop.get_compare.no_vao_hop", _no_vao_hop, p)
		return out

	return run_cached("sx_hop.get_compare", {"t": label, "d": iso(today)}, build, refresh)
