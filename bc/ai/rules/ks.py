# -*- coding: utf-8 -*-
"""bc.ai.rules.ks — quy tắc nhóm Kiểm soát (mảng tro-ly, đặc tả §4.3, hợp đồng P2 §3): ct.huy_nhieu, ct.ghi_lui,
ct.but_toan_tay_lon (nguồn pack["tro-ly"]["chung_tu"]), gia.ban_lech, gia.chiet_khau_cao, gia.mua_tang (nguồn
pack["tro-ly"]["gia"]) và kpi.lech_chuan (nguồn pack["tro-ly"]["kpi"]; tín hiệu mang mảng của KPI qua
Cfg.signal(section=…)). Ý nghĩa từng khối: docstring của bc.ai.detectors.chung_tu / gia / kpi.

Hàm THUẦN trên pack (không SQL, không frappe). Luật:
- Mỗi quy tắc MỘT tín hiệu (trừ kpi.lech_chuan: một tín hiệu / KPI, khoá "kpi.lech_chuan:<path>"); lời nêu dòng đứng
  đầu qua placeholder; Signal.documents (≤ 20, chỉ quản trị thấy) = chứng từ làm bằng chứng. route "" (không có màn
  nguồn) — riêng kpi.lech_chuan: route của mảng KPI.
- Mức vàng mặc định; đỏ chỉ khi quản trị đặt ngưỡng đỏ (threshold_red).
- Khối lọc theo ngưỡng (but_toan, ban_lech, chiet_khau, mua_tang) mang `nguong` = ngưỡng vàng detector đã dùng; khác
  ngưỡng vàng đang áp → NotRunnable (gói dựng theo ngưỡng khác — không kết luận được, tín hiệu cũ giữ nguyên).
- None / thiếu / không phải số → không tín hiệu, không bao giờ ném lỗi (trừ NotRunnable có chủ đích).
- Mọi số / tên trong lời là placeholder; số tự tính khai trong `tinh`, viết {{@tên|kiểu}}. Không chữ số gõ tay, không
  tên người. Tên khách / NCC chỉ qua {{…customer|chu}} / {{…supplier|chu}} (mã giả hoạt động).
"""

from __future__ import annotations

import math

from bc.ai.registry import KPI_TICH_LUY, KPIS, TRO_LY, NotRunnable, ph, resolve, rule, section_of, source_ok, strip_index

C, G, K = f"{TRO_LY}.chung_tu", f"{TRO_LY}.gia", f"{TRO_LY}.kpi"

SAN_HUY = 5                                          # ct.huy_nhieu: số chứng từ huỷ tối thiểu trong cửa sổ
SAN_KPI = {"tien": 1_000_000, "so": 1, "pct": 0.5}   # kpi.lech_chuan: độ lệch tuyệt đối tối thiểu theo kiểu
TL_SAN = 0.05                                        # kpi.lech_chuan: … và tối thiểu 5% |trung vị|
TL_MAD = 0.01                                        # kpi.lech_chuan: MAD không nhỏ hơn 1% |trung vị|
NGAY_MIN = 14                                        # kpi.lech_chuan: số ngày lịch sử tối thiểu
CUA_SO = 28                                          # kpi.lech_chuan: số ngày lịch sử (khi gói không ghi)
_KPI = {p: (k, nhan) for p, k, nhan in KPIS}


def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _n(pack, path):
	return _so(resolve(pack, path, None))


def _chu(v) -> bool:
	"""Chuỗi dùng được cho placeholder kiểu chu (không rỗng, ≤ 120 ký tự)."""
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


def _rows(pack, block) -> list:
	v = resolve(pack, f"{block}.rows", None)
	return v if isinstance(v, list) else []


def _dong(rows, i=0):
	return rows[i] if len(rows) > i and isinstance(rows[i], dict) else {}


def _docs(rows, dung=lambda r: True) -> list:
	"""[{doctype, name}] ≤ 20 của các dòng thoả `dung` (không trùng)."""
	out, gap = [], set()
	for r in rows:
		if isinstance(r, dict) and _chu(r.get("doctype")) and _chu(r.get("name")) and dung(r):
			k = (r["doctype"], r["name"])
			if k not in gap:
				gap.add(k)
				out.append({"doctype": r["doctype"], "name": r["name"]})
	return out[:20]


def _trong(pack) -> str:
	"""'trong <n> ngày qua' (n = cửa sổ của detector chung_tu / gia) — không có số thì 'trong tuần qua'."""
	for b in (C, G):
		if _n(pack, f"{b}.so_ngay") is not None:
			return f"trong {ph(f'{b}.so_ngay', 'so')} ngày qua"
	return "trong tuần qua"


def _nguong(pack, block, cfg):
	"""Khối lọc theo ngưỡng phải được dựng với đúng ngưỡng vàng đang áp."""
	ng = _n(pack, f"{block}.nguong")
	if ng is None or cfg.vang is None or float(ng) != float(cfg.vang):
		raise NotRunnable("nguong")
	return ng


def _ks(key, block, **kw):
	return rule(key, section=TRO_LY, sources=[block], route="", **kw)


# ─── Chứng từ ────────────────────────────────────────────────────────────────
@_ks("ct.huy_nhieu", f"{C}.huy", vang=2, unit="lần trung bình tuần",
	label="Chứng từ bị huỷ trong 7 ngày tăng vọt so với trung bình 8 tuần trước (và từ 5 chứng từ)")
def huy_nhieu(pack, cfg):
	"""so ≥ 5 và so > ngưỡng × trung bình tuần của 8 tuần trước (so ngặt, tính bằng số nguyên: so × 8 > ngưỡng × nền);
	nền 0 → chỉ cần so ≥ 5. Đỏ chỉ khi đặt ngưỡng đỏ (cùng cách so)."""
	b = f"{C}.huy"
	so, nen, tuan, tb = (_n(pack, f"{b}.{k}") for k in ("so", "so_nen", "so_tuan_nen", "so_tb_tuan"))
	if so is None or nen is None or tb is None or not tuan or tuan <= 0 or so < SAN_HUY:
		return []
	vuot = lambda k: k is not None and so * tuan > k * nen  # noqa: E731
	muc = "do" if vuot(cfg.do) else "vang" if vuot(cfg.vang) else None
	if not muc:
		return []
	rows = _rows(pack, b)
	loai = resolve(pack, f"{b}.theo_loai", None)
	detail = f"Trung bình {ph(f'{b}.so_tuan_nen', 'so')} tuần trước là {ph(f'{b}.so_tb_tuan', 'so')} chứng từ mỗi tuần"
	if isinstance(loai, list) and loai and isinstance(loai[0], dict) and _chu(loai[0].get("loai")) \
			and _so(loai[0].get("so")) is not None:
		detail += (f", nhiều nhất là {ph(f'{b}.theo_loai[0].loai', 'chu')} với "
			f"{ph(f'{b}.theo_loai[0].so', 'so')} chứng từ")
	detail += "; kế toán trưởng cần rà soát lý do huỷ."
	return [cfg.signal(muc, f"{ph(f'{b}.so', 'so')} chứng từ bị huỷ {_trong(pack)}", detail=detail,
		paths=[f"{b}.so_nen"], documents=_docs(rows))]


@_ks("ct.ghi_lui", f"{C}.ghi_lui", vang=10, unit="ngày",
	label="Chứng từ tạo trong 7 ngày (đã duyệt) có ngày hạch toán lùi xa so với ngày tạo")
def ghi_lui(pack, cfg):
	"""Chứng từ tạo trong 7 ngày có ngày hạch toán sớm hơn ngày tạo QUÁ ngưỡng ngày (ngặt) → một tín hiệu; đếm từ
	phan_bo. Mức theo số ngày lùi xa nhất (đỏ chỉ khi đặt ngưỡng đỏ)."""
	b = f"{C}.ghi_lui"
	pb = resolve(pack, f"{b}.phan_bo", None)
	if not isinstance(pb, list) or cfg.vang is None:
		return []
	cap = [(_so(x.get("so_ngay_lui")), _so(x.get("so"))) for x in pb if isinstance(x, dict)]
	cap = [(d, n) for d, n in cap if d is not None and n is not None and n > 0]
	so = sum(n for d, n in cap if d > cfg.vang)
	if not so:
		return []
	muc = cfg.muc(max(d for d, _n2 in cap)) or "vang"
	rows = _rows(pack, b)
	r0 = _dong(rows)
	if _so(r0.get("so_ngay_lui")) is not None and r0["so_ngay_lui"] > cfg.vang and _chu(r0.get("loai")) \
			and _chu(r0.get("name")):
		detail = (f"Lùi xa nhất {ph(f'{b}.rows[0].so_ngay_lui', 'so')} ngày ở {ph(f'{b}.rows[0].loai', 'chu')} số "
			f"{ph(f'{b}.rows[0].name', 'chu')}, kế toán cần kiểm tra lý do ghi sổ muộn.")
	else:
		detail = "Kế toán cần kiểm tra lý do ghi sổ muộn và khoá sổ các kỳ đã chốt."
	return [cfg.signal(muc, "{{@so|so}} chứng từ mới tạo bị ghi lùi ngày quá {{@nguong|so}} ngày", detail=detail,
		tinh={"so": so, "nguong": cfg.vang}, documents=_docs(rows, lambda r: (_so(r.get("so_ngay_lui")) or 0) > cfg.vang))]


@_ks("ct.but_toan_tay_lon", f"{C}.but_toan", vang=100_000_000, unit="đ",
	label="Bút toán nhập tay đã duyệt trong 7 ngày có số tiền lớn")
def but_toan_tay_lon(pack, cfg):
	"""Có bút toán nhập tay (đã duyệt, hạch toán trong 7 ngày) total_debit ≥ ngưỡng (có dấu bằng) → một tín hiệu; đỏ
	khi bút toán lớn nhất ≥ ngưỡng đỏ (chỉ khi đặt)."""
	b = f"{C}.but_toan"
	_nguong(pack, b, cfg)
	so = _n(pack, f"{b}.so")
	if not so or so <= 0:
		return []
	rows = _rows(pack, b)
	r0 = _dong(rows)
	top = _so(r0.get("gia_tri"))
	muc = "do" if cfg.do is not None and top is not None and top >= cfg.do else "vang"
	parts = []
	if _n(pack, f"{b}.gia_tri_tong") is not None:
		parts.append(f"Tổng {ph(f'{b}.gia_tri_tong', 'tien')}")
	if top is not None and _chu(r0.get("name")):
		parts.append(f"lớn nhất {ph(f'{b}.rows[0].gia_tri', 'tien')} ở bút toán {ph(f'{b}.rows[0].name', 'chu')}")
	detail = (", ".join(parts) + "; kế toán trưởng cần đối chiếu chứng từ gốc.") if parts else \
		"Kế toán trưởng cần đối chiếu chứng từ gốc của các bút toán này."
	if parts:
		detail = detail[0].upper() + detail[1:]
	return [cfg.signal(muc, f"{ph(f'{b}.so', 'so')} bút toán nhập tay từ {ph(f'{b}.nguong', 'tien')} trở lên "
		"trong tuần qua", detail=detail, documents=_docs(rows))]


# ─── Giá ─────────────────────────────────────────────────────────────────────
def _cho(b, r0) -> str:
	return f" bán cho {ph(f'{b}.rows[0].customer', 'chu')}" if _chu(r0.get("customer")) else ""


@_ks("gia.ban_lech", f"{G}.ban_lech", vang=15, unit="%",
	label="Dòng bán 7 ngày có giá thấp hơn trung vị 90 ngày của cùng mã và kênh")
def ban_lech(pack, cfg):
	"""Có dòng bán lệch dưới trung vị QUÁ ngưỡng % (ngặt, detector đã lọc) → một tín hiệu; mức theo dòng lệch nhiều
	nhất."""
	b = f"{G}.ban_lech"
	_nguong(pack, b, cfg)
	so = _n(pack, f"{b}.so_dong")
	if not so or so <= 0:
		return []
	rows = _rows(pack, b)
	r0 = _dong(rows)
	muc = cfg.muc(_so(r0.get("lech_pct"))) or "vang"
	if _chu(r0.get("item_name")) and _so(r0.get("rate")) is not None and _so(r0.get("trung_vi")) is not None \
			and _n(pack, f"{b}.so_ngay_nen") is not None:
		detail = (f"Lệch nhiều nhất là {ph(f'{b}.rows[0].item_name', 'chu')}{_cho(b, r0)} với đơn giá "
			f"{ph(f'{b}.rows[0].rate', 'tien')}, trung vị {ph(f'{b}.so_ngay_nen', 'so')} ngày trước đó là "
			f"{ph(f'{b}.rows[0].trung_vi', 'tien')}; phòng kinh doanh cần kiểm tra giá đã duyệt.")
	else:
		detail = "Phòng kinh doanh cần kiểm tra giá đã duyệt cho các dòng này."
	return [cfg.signal(muc, f"{ph(f'{b}.so_dong', 'so')} dòng hàng bán thấp hơn giá trung vị quá "
		f"{ph(f'{b}.nguong', 'pct')}", detail=detail, documents=_docs(rows))]


@_ks("gia.chiet_khau_cao", f"{G}.chiet_khau", vang=15, unit="%",
	label="Dòng bán 7 ngày có chiết khấu dòng cao")
def chiet_khau_cao(pack, cfg):
	"""Có dòng bán chiết khấu QUÁ ngưỡng % (ngặt, detector đã lọc) → một tín hiệu; mức theo dòng cao nhất."""
	b = f"{G}.chiet_khau"
	_nguong(pack, b, cfg)
	so = _n(pack, f"{b}.so_dong")
	if not so or so <= 0:
		return []
	rows = _rows(pack, b)
	r0 = _dong(rows)
	muc = cfg.muc(_so(r0.get("ck_pct"))) or "vang"
	if _chu(r0.get("item_name")) and _so(r0.get("ck_pct")) is not None:
		detail = f"Cao nhất {ph(f'{b}.rows[0].ck_pct', 'pct')} ở {ph(f'{b}.rows[0].item_name', 'chu')}{_cho(b, r0)}"
		if _n(pack, f"{b}.gia_tri") is not None:
			detail += f", tổng giá trị các dòng này {ph(f'{b}.gia_tri', 'tien')}"
		detail += "; phòng kinh doanh cần đối chiếu chính sách chiết khấu."
	else:
		detail = "Phòng kinh doanh cần đối chiếu chính sách chiết khấu cho các dòng này."
	return [cfg.signal(muc, f"{ph(f'{b}.so_dong', 'so')} dòng hàng bán có chiết khấu quá {ph(f'{b}.nguong', 'pct')}",
		detail=detail, documents=_docs(rows))]


@_ks("gia.mua_tang", f"{G}.mua_tang", vang=10, unit="%",
	label="Giá mua bình quân 30 ngày tăng so với 90 ngày trước đó (mã mua từ 20 triệu)")
def mua_tang(pack, cfg):
	"""Có mã (mua ≥ 20 triệu trong 30 ngày) giá mua bình quân tăng QUÁ ngưỡng % (ngặt, detector đã lọc) → một tín hiệu;
	mức theo mã tăng nhiều nhất."""
	b = f"{G}.mua_tang"
	_nguong(pack, b, cfg)
	so = _n(pack, f"{b}.so_ma")
	if not so or so <= 0:
		return []
	rows = _rows(pack, b)
	r0 = _dong(rows)
	muc = cfg.muc(_so(r0.get("tang_pct"))) or "vang"
	if _chu(r0.get("item_name")) and all(_so(r0.get(k)) is not None for k in ("tang_pct", "gia_cu", "gia_moi")):
		detail = (f"Tăng nhiều nhất là {ph(f'{b}.rows[0].item_name', 'chu')} với {ph(f'{b}.rows[0].tang_pct', 'pct')}, "
			f"giá bình quân từ {ph(f'{b}.rows[0].gia_cu', 'tien')} lên {ph(f'{b}.rows[0].gia_moi', 'tien')} mỗi đơn vị kho")
		if _chu(r0.get("supplier")):
			detail += f", nhà cung cấp chính {ph(f'{b}.rows[0].supplier', 'chu')}"
		detail += "; phòng mua hàng cần đối chiếu báo giá."
	else:
		detail = "Phòng mua hàng cần đối chiếu báo giá của các mã này."
	return [cfg.signal(muc, f"{ph(f'{b}.so_ma', 'so')} mã hàng mua vào tăng giá quá {ph(f'{b}.nguong', 'pct')}",
		detail=detail, documents=_docs(rows))]


# ─── KPI lệch chuẩn ──────────────────────────────────────────────────────────
@_ks("kpi.lech_chuan", K, vang=3, unit="MAD", label="Chỉ số theo dõi hằng ngày lệch xa trung vị 28 ngày")
def lech_chuan(pack, cfg):
	"""Mỗi KPI (không cộng dồn, ≥ 14 ngày lịch sử) có d = |hôm nay − trung vị| thoả d > ngưỡng × max(MAD, 1% |trung
	vị|) (ngặt) VÀ d ≥ max(5% |trung vị|, sàn theo kiểu: tien 1 triệu, so 1, pct 0,5) → tín hiệu khoá
	kpi.lech_chuan:<path>, MẢNG CỦA KPI. Hôm nay = giá trị tại path thật của KPI trong gói. Đỏ chỉ khi đặt ngưỡng đỏ.
	Lời nêu số ngày THẬT có số làm nền (n của dòng, 14 … 28) trong cửa sổ 28 ngày.

	KPI KHÔNG đánh giá được hôm nay → cfg.keep(path): tín hiệu đang mở của nó GIỮ NGUYÊN (không đóng rồi mở lại với
	first_seen mới — tuổi "tồn" của bản tin và phản biện không bị xoá). Không đánh giá được = khối nguồn của chính KPI
	(`<mảng>.<khối>`) lỗi / vắng, hoặc có số hôm nay mà lịch sử < 14 ngày (khoảng trống lượt chạy), hoặc dòng của
	detector có mà số hôm nay / trung vị / MAD không đọc được. KPI có khối nguồn tốt mà không có số hôm nay (danh sách
	rỗng — không còn gì để so) và KPI đánh giá được mà không lệch → đóng như thường."""
	from bc.ai.detectors.kpi import KPI_THEO_KY      # hằng số (không SQL ở đây)

	if cfg.vang is None:
		return []
	cua_so = _n(pack, f"{K}.cua_so") or CUA_SO
	out, gap = [], set()
	dong = {r.get("path"): r for r in _rows(pack, K) if isinstance(r, dict) and isinstance(r.get("path"), str)}
	for path in _KPI:
		if path in KPI_TICH_LUY or path in KPI_THEO_KY or path in dong:
			continue
		khoi = ".".join(strip_index(path).split(".")[:2])
		if not source_ok(pack, khoi) or _n(pack, path) is not None:
			cfg.keep(path)               # nguồn lỗi / lịch sử chưa đủ: không kết luận được → giữ tín hiệu cũ
	for r in _rows(pack, K):
		path = r.get("path") if isinstance(r, dict) else None
		if path not in _KPI or path in gap or path in KPI_TICH_LUY or path in KPI_THEO_KY:
			continue
		kieu, nhan = _KPI[path]
		x, med, mad, n = _n(pack, path), _so(r.get("trung_vi")), _so(r.get("mad")), _so(r.get("n"))
		if x is None or med is None or mad is None or n is None or n < NGAY_MIN:
			cfg.keep(path)
			continue
		d, mau = abs(x - med), max(mad, TL_MAD * abs(med))
		if not (d > cfg.vang * mau and d >= max(TL_SAN * abs(med), SAN_KPI[kieu])):
			continue
		gap.add(path)
		muc = "do" if cfg.do is not None and d > cfg.do * mau else "vang"
		out.append(cfg.signal(muc, "{{@nhan|chu}} khác thường so với {{@cua_so|so}} ngày qua",
			detail=(f"Hôm nay là {ph(path, kieu)}, trung vị của {{{{@so_ngay|so}}}} ngày có số trong {{{{@cua_so|so}}}} "
				f"ngày trước đó là {{{{@trung_vi|{kieu}}}}}; cần đối chiếu số trên màn gốc trước khi kết luận."),
			obj=path, section=section_of(path), paths=[path],
			tinh={"nhan": nhan, "so_ngay": int(n), "cua_so": cua_so, "trung_vi": med}))
	return out
