# -*- coding: utf-8 -*-
"""bc.ai.rules.kd — quy tắc nhóm Kinh doanh (đặc tả §4.1). Hàm THUẦN trên gói số: không SQL, không frappe.

Nguồn đã đối chiếu code bc.api.kd / bc.api.tet và view tong-quan.js / tet.js (bảng path:
docs/ai-rules-audit.md):
- tong-quan.summary  = kd.get_summary: rows[{period, sales, returns, net, return_rate}] × 3 kỳ (current,
  same_period, last_year) + meta.growth.{sales, returns, net}. Tiền VND chưa VAT, trả về là số dương; tỷ lệ
  đã nhân 100, 1 số lẻ, mẫu số 0 → None.
- tong-quan.channels = kd.get_channels: rows[{period, channel, channel_key, sales, …}] 3 kỳ × 5 kênh. KHÔNG
  có sẵn tăng trưởng / tỷ trọng theo kênh → tự tính đúng công thức thẻ kênh trên màn (doanh số bán ra).
- tet.npp_growth     = tet.get_npp_growth: rows[{customer, customer_id, this_year, last_year, growth_pct}]
  (chỉ kênh NPP; last_year = năm trước CÙNG KỲ) + meta.{between_seasons, target_pct, asof, …}. Không có
  dòng tổng → tự cộng.

Luật:
- Dòng trong danh sách TÌM theo `period` / `channel_key`, không theo vị trí. Giá trị None / thiếu / không
  phải số → không tín hiệu, không bao giờ ném lỗi.
- "Giảm" khai bằng MỨC GIẢM dương (giam = −tăng trưởng): "< −10% / < −20%" của đặc tả = giam > 10 / > 20
  (so ngặt) — ngưỡng trong BC Settings là số dương.
- Số làm tròn 1 số lẻ kiểu Math.round của JS (đúng giữa thì về +∞) để khớp từng chữ số với màn gốc.
- Mốc phụ không nằm trong 2 ô ngưỡng của BC Settings là hằng số ở dưới (CHENH_DIEM, TY_TRONG_KENH, NPP_*).
- Mọi số / tên từ dữ liệu trong lời là placeholder; số tự tính khai trong `tinh`, viết {{@tên|kiểu}}. Tên
  khách chỉ qua {{…customer|chu}} (mã giả thay được). Không tên nhân viên.
- Quy tắc Tết chỉ chạy khi meta.between_seasons sai (đang trong mùa); giữa hai mùa → chạy, không tín hiệu
  (tín hiệu cũ được đóng).
"""

from __future__ import annotations

import datetime
import math

from bc.ai.registry import ph, resolve, rule

S, C, T = "tong-quan.summary", "tong-quan.channels", "tet.npp_growth"

CHENH_DIEM = 1.0             # kd.tra_hang_cao (vàng): tỷ lệ trả cao hơn cùng kỳ từ ngần này điểm
TY_TRONG_KENH = 10.0         # kd.kenh_sut: chỉ xét kênh chiếm từ ngần này % doanh số (năm nay hoặc cùng kỳ)
NPP_NAM_TRUOC = 100_000_000  # tet.npp_tut: NPP có năm trước cùng kỳ từ ngần này đồng
NPP_GIAM = 20.0              # tet.npp_tut: NPP giảm QUÁ ngần này % so cùng kỳ
NPP_NEU, NPP_PATHS = 3, 5    # tet.npp_tut: số NPP nêu tên trong lời / số NPP đưa vào paths


# ─── Tiện ích ────────────────────────────────────────────────────────────────
def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _chu(v) -> bool:
	"""Chuỗi dùng được cho placeholder kiểu chu (không rỗng, ≤ 120 ký tự)."""
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


def _ngay(v) -> bool:
	"""Ngày dùng được cho placeholder kiểu ngay: date / datetime hoặc chuỗi ISO 'yyyy-mm-dd' có thật."""
	if isinstance(v, datetime.date):
		return True
	if not isinstance(v, str) or len(v) != 10:
		return False
	try:
		datetime.date.fromisoformat(v)
		return True
	except ValueError:
		return False


def _tron(x: float) -> float:
	"""1 số lẻ kiểu Math.round(x * 10) / 10 của JS."""
	return math.floor(x * 10 + 0.5) / 10


def _ty_le(tu, mau):
	"""tu / mau × 100, 1 số lẻ — đúng phép tính `Math.round(a / b * 1000) / 10` của view; mau ≤ 0 → None."""
	return math.floor(tu / mau * 1000 + 0.5) / 10 if mau and mau > 0 else None


def _rows(pack, path) -> list:
	"""[(chỉ số, dòng)] các dòng là dict của danh sách tại path (thiếu / không phải list → [])."""
	v = resolve(pack, path, None)
	return [(i, r) for i, r in enumerate(v) if isinstance(r, dict)] if isinstance(v, list) else []


def _ky(pack) -> dict:
	"""{kỳ: path của dòng} trong tong-quan.summary.rows — dòng đầu tiên của mỗi `period`."""
	out: dict = {}
	for i, r in _rows(pack, f"{S}.rows"):
		if isinstance(r.get("period"), str):
			out.setdefault(r["period"], f"{S}.rows[{i}]")
	return out


def _trong_mua(pack) -> bool:
	"""Đang trong mùa Tết: meta.between_seasons sai (giữa hai mùa số đã khoá, không còn gì để thúc)."""
	return not resolve(pack, f"{T}.meta.between_seasons", None)


# ─── Tổng quan ───────────────────────────────────────────────────────────────
@rule("kd.tang_truong_am", section="tong-quan", sources=[S], vang=10, do=20, unit="%",
	label="Thực bán giảm so với cùng kỳ")
def tang_truong_am(pack, cfg):
	"""Thực bán (bán ra − trả về) năm tài chính đến nay giảm quá 10% (vàng) / 20% (đỏ) so cùng kỳ."""
	g = _so(resolve(pack, f"{S}.meta.growth.net", None))
	if g is None:
		return []
	giam = -g
	muc = cfg.muc(giam)
	if not muc:
		return []
	paths, detail = [f"{S}.meta.growth.net"], "Cần xem kênh và nhóm hàng nào kéo thực bán xuống."
	ky = _ky(pack)
	nay, truoc = (f"{ky[k]}.net" if k in ky else None for k in ("current", "same_period"))
	if nay and truoc and None not in (_so(resolve(pack, nay, None)), _so(resolve(pack, truoc, None))):
		paths += [nay, truoc]
		detail = (f"Từ đầu năm tài chính thực bán {ph(nay, 'tien')}, cùng kỳ năm trước {ph(truoc, 'tien')}; "
			"cần xem kênh và nhóm hàng nào kéo xuống.")
	return [cfg.signal(muc, "Thực bán giảm {{@giam|pct}} so với cùng kỳ năm trước", detail=detail, paths=paths,
		tinh={"giam": giam})]


@rule("kd.tra_hang_cao", section="tong-quan", sources=[S], vang=3, do=5, unit="%",
	label="Tỷ lệ hàng trả về trên doanh số bán ra")
def tra_hang_cao(pack, cfg):
	"""Tỷ lệ trả hàng năm nay > 5% → đỏ; > 3% VÀ cao hơn cùng kỳ từ 1 điểm → vàng (cùng kỳ không có số thì
	không so được → không vàng)."""
	ky = _ky(pack)
	if "current" not in ky:
		return []
	nay = f"{ky['current']}.return_rate"
	tl = _so(resolve(pack, nay, None))
	muc = cfg.muc(tl)
	if not muc:
		return []
	truoc = f"{ky['same_period']}.return_rate" if "same_period" in ky else None
	tl_truoc = _so(resolve(pack, truoc, None)) if truoc else None
	chenh = _tron(tl - tl_truoc) if tl_truoc is not None else None
	if muc == "vang" and (chenh is None or chenh < CHENH_DIEM):
		return []
	paths, tinh = [nay], {}
	if chenh is None:
		detail = "Cùng kỳ năm trước chưa có số để so"
	else:
		paths.append(truoc)
		tinh["chenh"] = chenh
		detail = (f"Cao hơn cùng kỳ năm trước {{{{@chenh|so}}}} điểm (cùng kỳ {ph(truoc, 'pct')})" if chenh > 0
			else f"Cùng kỳ năm trước là {ph(truoc, 'pct')}")
	tra = f"{ky['current']}.returns"
	if _so(resolve(pack, tra, None)) is not None:
		paths.append(tra)
		detail += f"; hàng trả về từ đầu năm tài chính trị giá {ph(tra, 'tien')}"
	return [cfg.signal(muc, f"Hàng trả về chiếm {ph(nay, 'pct')} doanh số bán ra", detail=detail + ".",
		paths=paths, tinh=tinh)]


@rule("kd.kenh_sut", section="tong-quan", sources=[C], vang=15, unit="%",
	label="Doanh số một kênh giảm so với cùng kỳ")
def kenh_sut(pack, cfg):
	"""Kênh chiếm từ 10% doanh số (năm nay hoặc cùng kỳ) có doanh số bán ra giảm quá 15% so cùng kỳ — mỗi kênh
	một tín hiệu, khoá kd.kenh_sut:<channel_key>."""
	o: dict = {}       # (kỳ, kênh) → (chỉ số dòng, doanh số bán ra)
	for i, r in _rows(pack, f"{C}.rows"):
		k, ds = r.get("channel_key"), _so(r.get("sales"))
		if isinstance(k, str) and k.strip() and ds is not None:
			o.setdefault((r.get("period"), k), (i, ds))
	tong = {p: sum(ds for (pp, _k), (_i, ds) in o.items() if pp == p) for p in ("current", "same_period")}
	out = []
	for (p, k), (i_nay, nay) in o.items():
		if p != "current" or ("same_period", k) not in o:
			continue
		i_truoc, truoc = o[("same_period", k)]
		tang = _ty_le(nay - truoc, truoc)
		if tang is None:
			continue
		muc = cfg.muc(-tang)
		tt, tt_truoc = _ty_le(nay, tong["current"]), _ty_le(truoc, tong["same_period"])
		if not muc or max(tt or 0, tt_truoc or 0) < TY_TRONG_KENH:
			continue
		p_nay, p_truoc = f"{C}.rows[{i_nay}]", f"{C}.rows[{i_truoc}]"
		paths, tinh = [f"{p_nay}.sales", f"{p_truoc}.sales"], {"giam": -tang}
		ten = "Một kênh bán hàng"
		if _chu(resolve(pack, f"{p_nay}.channel", None)):
			paths.append(f"{p_nay}.channel")
			ten = f"Kênh {ph(p_nay + '.channel', 'chu')}"
		detail = (f"Từ đầu năm tài chính kênh này bán {ph(p_nay + '.sales', 'tien')}, cùng kỳ năm trước "
			f"{ph(p_truoc + '.sales', 'tien')}")
		if tt_truoc is not None:
			tinh["ty_trong_cung_ky"] = tt_truoc
		if tt is not None:
			tinh["ty_trong"] = tt
			detail += "; kênh đang chiếm {{@ty_trong|pct}} doanh số cả công ty"
		out.append(cfg.signal(muc, ten + " giảm {{@giam|pct}} doanh số so với cùng kỳ", detail=detail + ".",
			paths=paths, tinh=tinh, obj=k))
	return out


# ─── Hàng Tết ────────────────────────────────────────────────────────────────
@rule("tet.npp_tut", section="tet", sources=[T], vang=3, unit="NPP",
	label="Số NPP lớn mua hàng Tết giảm mạnh so với cùng kỳ")
def npp_tut(pack, cfg):
	"""Trong mùa: từ 3 NPP (năm trước cùng kỳ ≥ 100 triệu) giảm quá 20% so cùng kỳ → GỘP một tín hiệu."""
	if not _trong_mua(pack):
		return []
	tut = []           # (số tiền hụt, chỉ số dòng, năm nay, năm trước)
	for i, r in _rows(pack, f"{T}.rows"):
		nn, nt, g = _so(r.get("this_year")), _so(r.get("last_year")), _so(r.get("growth_pct"))
		if None in (nn, nt, g):
			continue
		if nt >= NPP_NAM_TRUOC and -g > NPP_GIAM:
			tut.append((nt - nn, i, nn, nt))
	muc = cfg.muc(len(tut), bang=True)
	if not muc:
		return []
	tut.sort(key=lambda x: (-x[0], x[1]))    # hụt nhiều tiền nhất trước
	paths, neu = [], []
	for _hut, i, _nn, _nt in tut[:NPP_PATHS]:
		p = f"{T}.rows[{i}]"
		paths += [f"{p}.growth_pct", f"{p}.this_year", f"{p}.last_year"]
		if _chu(resolve(pack, f"{p}.customer", None)):
			paths.append(f"{p}.customer")
			if len(neu) < NPP_NEU:
				neu.append(f"{ph(p + '.customer', 'chu')} ({ph(p + '.growth_pct', 'pct')})")
	detail = "Các NPP này mua ít hơn cùng kỳ năm trước tổng cộng {{@hut|tien}}"
	if neu:
		detail += "; hụt nhiều nhất: " + ", ".join(neu)
	tinh = {"so_npp": len(tut), "nguong_giam": NPP_GIAM, "hut": sum(x[0] for x in tut),
		"nam_nay": sum(x[2] for x in tut), "nam_truoc": sum(x[3] for x in tut)}
	return [cfg.signal(muc, "{{@so_npp|so}} NPP lớn mua hàng Tết giảm hơn {{@nguong_giam|pct}} so với cùng kỳ",
		detail=detail + ".", paths=paths, tinh=tinh)]


@rule("tet.cham_muc_tieu", section="tet", sources=[T], vang=10, do=20, unit="điểm",
	label="Tăng trưởng hàng Tết kênh NPP thấp hơn mục tiêu")
def cham_muc_tieu(pack, cfg):
	"""Trong mùa: tăng trưởng cùng kỳ của cả kênh NPP thấp hơn mục tiêu (meta.target_pct) từ 10 điểm (vàng) /
	20 điểm (đỏ)."""
	if not _trong_mua(pack):
		return []
	muc_tieu = _so(resolve(pack, f"{T}.meta.target_pct", None))
	if muc_tieu is None:
		return []
	nay = truoc = 0.0
	for _i, r in _rows(pack, f"{T}.rows"):
		nay += _so(r.get("this_year")) or 0
		truoc += _so(r.get("last_year")) or 0
	tang = _ty_le(nay - truoc, truoc)
	if tang is None:
		return []
	thieu = _tron(muc_tieu - tang)
	muc = cfg.muc(thieu, bang=True)
	if not muc:
		return []
	p_mt, p_asof = f"{T}.meta.target_pct", f"{T}.meta.asof"
	paths = [p_mt]
	detail = ("Thấp hơn mục tiêu {{@thieu|so}} điểm: mùa này NPP mua {{@nam_nay|tien}}, cùng kỳ năm trước "
		"{{@nam_truoc|tien}}")
	if _ngay(resolve(pack, p_asof, None)):
		paths.append(p_asof)
		detail += f" (tính đến {ph(p_asof, 'ngay')})"
	title = "Hàng Tết kênh NPP tăng trưởng {{@tang_truong|pct}}, mục tiêu " + ph(p_mt, "pct")
	return [cfg.signal(muc, title, detail=detail + ".", paths=paths,
		tinh={"tang_truong": tang, "thieu": thieu, "nam_nay": nay, "nam_truoc": truoc})]

