# -*- coding: utf-8 -*-
"""bc.ai.rules.kho — quy tắc nhóm Kho (đặc tả §4.1, prefix kho.*). Hàm THUẦN trên gói số: không SQL,
không frappe.

Nguồn đã đối chiếu code bc.api.kho_han / kho_ton / kho_kk / kho_nhap và view han-dung.js / ton-kho.js /
kiem-ke.js (bảng path: docs/ai-rules-audit.md, mục Kho). Tiền = VND theo giá vốn, chưa VAT; tỷ lệ đã nhân
100, mẫu số 0 → None.
- han-dung.overview = kho_han.get_overview: han (hạn dùng thành phẩm: buckets[{key, value, lots}],
  can_date {pct, value, ngay}), khong_ban {tong, day_du}, am {items, warehouses, value_abs}.
- ton-kho.overview = kho_ton.get_overview: slow.total {dead_pct, dead_value, dead_items}, slow.dead_days,
  doi {window_days, traditional {days, value}}, health {failed_reposts, failed_repost_since,
  pos_unconsolidated, si_no_stock_relief {count, days, oldest}} (mục lỗi / thiếu bảng bị bỏ khỏi health).
- ton-kho.trend = kho_ton.get_trend: trend {future_value, ledger_bin_diff} (hai mục cần quét cả sổ).
- kiem-ke.overview = kho_kk.get_overview (tháng này đến hôm nay): kho.tong {qua_30, qua_90, chua_kiem},
  meta.nguong {canh_bao, nguy} (SỐ NGÀY từ lần kiểm gần nhất), ira {ty_le, so_ma, so_ma_khop},
  xuat_khac {gia_tri, so_phieu}, meta {from, to}.
- nhap-tp.overview = kho_nhap.get_overview: no_bom {age_days, items}, gia_von_0 {ton.items,
  nhap_ky.items}.

Luật:
- Phần tử danh sách TÌM theo khoá (`key`), không theo vị trí. None / thiếu / không phải số → không tín
  hiệu, không bao giờ ném lỗi (trừ NotRunnable có chủ đích ở kho.kk_lech).
- kho.ton_am: hai thước đo — vàng theo SỐ MÃ âm (> ngưỡng vàng), đỏ theo GIÁ TRỊ âm (≥ ngưỡng đỏ, đồng).
- kho.suc_khoe (quản trị): mỗi mục một khoá `kho.suc_khoe:<mục>`, mức cố định theo đặc tả (định giá lại
  lỗi đỏ, còn lại vàng), không ngưỡng.
- kho.kk_lech: meta.nguong là ngưỡng SỐ NGÀY chưa kiểm → khoá `:tre` dùng đúng ngưỡng đó (đỏ: quá `nguy`
  ngày hoặc chưa kiểm lần nào; vàng: quá `canh_bao` ngày); khoá `:ira` = độ chính xác tồn dưới ngưỡng
  vàng (mặc định 80 — mốc tô màu của màn; càng thấp càng xấu). Site không có app sx (ira available False,
  reason khong_sx) → chỉ bỏ phần ira; ira lỗi / thiếu → NotRunnable (tín hiệu cũ giữ nguyên).
- Mọi số / tên từ dữ liệu trong lời là placeholder; số tự tính khai trong `tinh`, viết {{@tên|kiểu}}.
  Không chữ số gõ tay trong lời, không tên người / tên hàng / ghi chú.
"""

from __future__ import annotations

import datetime
import math

from bc.ai.registry import NotRunnable, ph, resolve, rule, source_ok

AM, HAN, KB = "han-dung.overview.am", "han-dung.overview.han", "han-dung.overview.khong_ban"
SLOW, DOI = "ton-kho.overview.slow", "ton-kho.overview.doi"
HEALTH, TREND = "ton-kho.overview.health", "ton-kho.trend.trend"
KK, KKM, IRA = "kiem-ke.overview.kho", "kiem-ke.overview.meta", "kiem-ke.overview.ira"
XK = "kiem-ke.overview.xuat_khac"
NB, GV0 = "nhap-tp.overview.no_bom", "nhap-tp.overview.gia_von_0"

LECH_SO = 1.0      # kho.suc_khoe:so_lech_bin — lệch sổ ↔ tồn từ ngần này đồng (đúng mốc của màn Tồn kho)


# ─── Tiện ích ────────────────────────────────────────────────────────────────
def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _n(pack, path):
	return _so(resolve(pack, path, None))


def _ngay(v) -> bool:
	"""Ngày dùng được cho placeholder kiểu ngay: date hoặc chuỗi ISO 'yyyy-mm-dd' có thật."""
	if isinstance(v, datetime.date):
		return True
	if not isinstance(v, str) or len(v) != 10:
		return False
	try:
		datetime.date.fromisoformat(v)
		return True
	except ValueError:
		return False


def _tim(pack, path, key):
	"""Path của phần tử đầu tiên có `key` == key trong danh sách tại path (None nếu không có)."""
	v = resolve(pack, path, None)
	if not isinstance(v, list):
		return None
	return next((f"{path}[{i}]" for i, r in enumerate(v)
		if isinstance(r, dict) and r.get("key") == key), None)


# ─── Hạn dùng & tồn âm ───────────────────────────────────────────────────────
@rule("kho.ton_am", section="han-dung", sources=[AM], vang=0, do=20_000_000, unit="đ",
	label="Tồn âm (vàng: số mã, đỏ: giá trị)")
def ton_am(pack, cfg):
	"""Có mã tồn âm (vàng, số mã > ngưỡng vàng) / giá trị phần âm ≥ ngưỡng đỏ (đỏ)."""
	items, val = _n(pack, f"{AM}.items"), _n(pack, f"{AM}.value_abs")
	muc = None
	if val is not None and cfg.do is not None and val >= cfg.do and (items is None or items > 0):
		muc = "do"
	elif items is not None and cfg.vang is not None and items > cfg.vang:
		muc = "vang"
	if not muc:
		return []
	so, tien = ph(f"{AM}.items", "so"), ph(f"{AM}.value_abs", "tien")
	if items is None:
		title = f"Kho đang tồn âm, giá trị phần âm {tien}"
	elif val is None:
		title = f"{so} mã hàng đang tồn âm"
	else:
		title = f"{so} mã hàng đang tồn âm, giá trị {tien}"
	ly_do = ("hàng đã xuất khi sổ chưa có hàng nên số tồn và giá vốn đang sai; kho cần nhập bù chứng từ "
		"còn thiếu.")
	detail = "Tồn âm nghĩa là " + ly_do
	if _n(pack, f"{AM}.warehouses") is not None:
		detail = f"Âm ở {ph(f'{AM}.warehouses', 'so')} kho: " + ly_do
	return [cfg.signal(muc, title, detail=detail,
		paths=[p for p in (f"{AM}.items", f"{AM}.value_abs") if _n(pack, p) is not None])]


@rule("kho.het_han", section="han-dung", sources=[HAN], do=0, unit="đ",
	label="Thành phẩm đã hết hạn còn trong kho")
def het_han(pack, cfg):
	"""Còn thành phẩm đã hết hạn ở kho bán được: giá trị > 0 → đỏ."""
	p = _tim(pack, f"{HAN}.buckets", "het_han")
	if not p:
		return []
	muc = cfg.muc(_n(pack, f"{p}.value"))
	if not muc:
		return []
	ly_do = "quá hạn dùng vẫn nằm ở kho bán được, cần tách ra và xử lý để không giao nhầm cho khách."
	detail = "Hàng " + ly_do
	if _n(pack, f"{p}.lots") is not None:
		detail = f"{ph(f'{p}.lots', 'so')} lô " + ly_do
	return [cfg.signal(muc, f"Còn {ph(f'{p}.value', 'tien')} thành phẩm đã hết hạn trong kho",
		detail=detail, paths=[f"{p}.value"])]


@rule("kho.can_date", section="han-dung", sources=[HAN], vang=10, do=20, unit="%",
	label="Hàng cận date / giá trị thành phẩm")
def can_date(pack, cfg):
	"""Giá trị lô còn 0..N ngày hạn dùng > 10% (vàng) / > 20% (đỏ) giá trị thành phẩm ở kho bán được."""
	c = f"{HAN}.can_date"
	muc = cfg.muc(_n(pack, f"{c}.pct"))
	if not muc:
		return []
	detail = "Cần đẩy bán sớm hoặc khuyến mãi trước khi hàng hết hạn."
	if _n(pack, f"{c}.value") is not None and _n(pack, f"{c}.ngay") is not None:
		detail = (f"{ph(f'{c}.value', 'tien')} hàng chỉ còn không quá {ph(f'{c}.ngay', 'so')} ngày "
			"hạn dùng, cần đẩy bán sớm trước khi hết hạn.")
	return [cfg.signal(muc, f"Hàng cận date chiếm {ph(f'{c}.pct', 'pct')} giá trị thành phẩm",
		detail=detail, paths=[f"{c}.pct"])]


@rule("kho.khong_ban_duoc", section="han-dung", sources=[KB], vang=50_000_000, do=200_000_000,
	unit="đ", label="Tồn không bán được")
def khong_ban_duoc(pack, cfg):
	"""Tổng tồn không bán được (kho trả về & cách ly + lô thu hồi + hết hạn) ≥ 50 tr / ≥ 200 tr."""
	muc = cfg.muc(_n(pack, f"{KB}.tong"), bang=True)
	if not muc:
		return []
	detail = ("Gồm hàng ở kho trả về và cách ly, lô đang thu hồi và hàng đã hết hạn; cần quyết định "
		"xử lý để giải phóng vốn.")
	if resolve(pack, f"{KB}.day_du", None) is False:
		detail = ("Số này chưa tính đủ mọi phần (có phần chưa lấy được số); gồm hàng ở kho trả về và "
			"cách ly, lô đang thu hồi và hàng đã hết hạn — cần quyết định xử lý.")
	return [cfg.signal(muc, f"Có {ph(f'{KB}.tong', 'tien')} hàng tồn không bán được", detail=detail,
		paths=[f"{KB}.tong"])]


# ─── Tồn kho ─────────────────────────────────────────────────────────────────
@rule("kho.ton_chet", section="ton-kho", sources=[SLOW], vang=5, do=10, unit="%",
	label="Tồn chết / giá trị hàng ở kho bán được")
def ton_chet(pack, cfg):
	"""Giá trị tồn chết (không xuất quá dead_days ngày) > 5% (vàng) / > 10% (đỏ) giá trị hàng ở kho
	bán được (phần tổng — mọi mã)."""
	t = f"{SLOW}.total"
	muc = cfg.muc(_n(pack, f"{t}.dead_pct"))
	if not muc:
		return []
	detail = "Vốn đang nằm chết trong kho; cần xem mã nào để xả hàng hoặc dừng nhập."
	can = (f"{t}.dead_items", f"{t}.dead_value", f"{SLOW}.dead_days")
	if all(_n(pack, p) is not None for p in can):
		detail = (f"{ph(can[0], 'so')} mã, giá trị {ph(can[1], 'tien')}, quá {ph(can[2], 'so')} ngày "
			"chưa xuất: vốn đang nằm chết, cần xả hàng hoặc dừng nhập.")
	return [cfg.signal(muc, f"Tồn chết chiếm {ph(f'{t}.dead_pct', 'pct')} giá trị hàng ở kho bán được",
		detail=detail, paths=[f"{t}.dead_pct"])]


@rule("kho.doi_cao", section="ton-kho", sources=[DOI], vang=45, do=75, unit="ngày",
	label="Số ngày tồn hàng truyền thống")
def doi_cao(pack, cfg):
	"""Số ngày tồn hàng truyền thống > 45 (vàng) / > 75 (đỏ). Không bán trong kỳ → days None."""
	tr = f"{DOI}.traditional"
	muc = cfg.muc(_n(pack, f"{tr}.days"))
	if not muc:
		return []
	detail = "Tồn kho cao so với sức bán; cần giảm sản xuất / nhập hoặc đẩy bán."
	if _n(pack, f"{tr}.value") is not None and _n(pack, f"{DOI}.window_days") is not None:
		detail = (f"Tồn {ph(f'{tr}.value', 'tien')} so với giá vốn bán "
			f"{ph(f'{DOI}.window_days', 'so')} ngày gần nhất là cao; cần giảm sản xuất / nhập hoặc đẩy bán.")
	return [cfg.signal(muc, f"Hàng truyền thống tồn đủ bán {ph(f'{tr}.days', 'so')} ngày",
		detail=detail, paths=[f"{tr}.days"])]


@rule("kho.suc_khoe", section="ton-kho", sources=[HEALTH, TREND], audience="quan-tri",
	label="Sức khoẻ số liệu kho")
def suc_khoe(pack, cfg):
	"""Mỗi mục một khoá: định giá lại lỗi (đỏ); hoá đơn chưa trừ kho, POS chưa gộp, sổ lệch tồn, phiếu
	ngày tương lai (vàng)."""
	out, h = [], HEALTH
	n = _n(pack, f"{h}.failed_reposts")
	if n is not None and n > 0:
		detail = "Giá trị tồn kho có thể sai cho tới khi kế toán chạy lại việc tính giá vốn."
		if _ngay(resolve(pack, f"{h}.failed_repost_since", None)):
			detail = (f"Từ {ph(f'{h}.failed_repost_since', 'ngay')} giá trị tồn kho có thể sai cho tới khi "
				"kế toán chạy lại việc tính giá vốn.")
		out.append(cfg.signal("do", f"{ph(f'{h}.failed_reposts', 'so')} lượt tính lại giá vốn bị lỗi",
			detail=detail, obj="dinh_gia_lai"))
	s = f"{h}.si_no_stock_relief"
	n = _n(pack, f"{s}.count")
	if n is not None and n > 0:
		detail = "Hàng đã bán chưa trừ khỏi kho nên tồn trên sổ đang cao hơn thực tế."
		if _n(pack, f"{s}.days") is not None and _ngay(resolve(pack, f"{s}.oldest", None)):
			detail = (f"Hoá đơn quá {ph(f'{s}.days', 'so')} ngày không có phiếu giao, cũ nhất từ "
				f"{ph(f'{s}.oldest', 'ngay')}: tồn trên sổ đang cao hơn thực tế.")
		out.append(cfg.signal("vang", f"{ph(f'{s}.count', 'so')} hoá đơn bán chưa trừ hàng khỏi kho",
			detail=detail, obj="hoa_don_chua_tru_kho"))
	n = _n(pack, f"{h}.pos_unconsolidated")
	if n is not None and n > 0:
		out.append(cfg.signal("vang",
			f"{ph(f'{h}.pos_unconsolidated', 'so')} phiếu bán lẻ cửa hàng chưa chốt ca",
			detail="Cửa hàng thực tế đang ít hàng hơn số trên sổ cho tới khi chốt ca.", obj="pos_chua_gop"))
	n = _n(pack, f"{TREND}.ledger_bin_diff")
	if n is not None and abs(n) >= LECH_SO:
		out.append(cfg.signal("vang",
			f"Sổ kho lệch {ph(f'{TREND}.ledger_bin_diff', 'tien')} so với số tồn hiện tại",
			detail="Số tồn kho đang không khớp với sổ, cần kế toán kho kiểm tra lại.", obj="so_lech_bin"))
	n = _n(pack, f"{TREND}.future_value")
	if n is not None and n != 0:
		out.append(cfg.signal("vang",
			f"Có {ph(f'{TREND}.future_value', 'tien')} hàng ghi sổ với ngày sau hôm nay",
			detail="Đã có trong tổng tồn nhưng chưa có trong biểu đồ; cần kiểm tra ngày chứng từ.",
			obj="phieu_tuong_lai"))
	return out


# ─── Kiểm kê ─────────────────────────────────────────────────────────────────
def _ira_tat(pack) -> bool:
	"""Khối ira tắt vì site không có app Sản xuất (không phải lỗi)."""
	v = resolve(pack, IRA, None)
	return isinstance(v, dict) and v.get("available") is False and v.get("reason") == "khong_sx" \
		and not v.get("error") and not v.get("_error")


@rule("kho.kk_lech", section="kiem-ke", sources=[KK, KKM], vang=80, lower=True, unit="%",
	label="Kiểm kê: kho lâu chưa kiểm / độ chính xác tồn thấp")
def kk_lech(pack, cfg):
	"""`:tre` — kho quá meta.nguong.nguy ngày hoặc chưa kiểm lần nào (đỏ) / quá canh_bao ngày (vàng).
	`:ira` — % mã khớp sổ của các lần kiểm gần nhất dưới ngưỡng vàng (80) / đỏ (mặc định không có)."""
	out = []
	t, ng = f"{KK}.tong", f"{KKM}.nguong"
	q30, q90, chua = (_n(pack, f"{t}.{k}") for k in ("qua_30", "qua_90", "chua_kiem"))
	do_n = (q90 or 0) + (chua or 0)
	if do_n > 0:
		detail = "Có kho chưa kiểm kê lần nào hoặc quá lâu chưa kiểm; số tồn trên sổ có thể đã lệch thực tế."
		if _n(pack, f"{ng}.nguy") is not None:
			detail = (f"Có kho chưa kiểm kê lần nào hoặc quá {ph(f'{ng}.nguy', 'so')} ngày chưa kiểm; số tồn "
				"trên sổ có thể đã lệch thực tế.")
		out.append(cfg.signal("do", "{{@so_kho|so}} kho quá lâu chưa kiểm kê", detail=detail,
			tinh={"so_kho": do_n}, obj="tre"))
	elif q30 is not None and q30 > 0 and _n(pack, f"{ng}.canh_bao") is not None:
		out.append(cfg.signal("vang",
			f"{ph(f'{t}.qua_30', 'so')} kho quá {ph(f'{ng}.canh_bao', 'so')} ngày chưa kiểm kê",
			detail="Nên lên lịch kiểm kê để số tồn trên sổ không lệch thực tế.", obj="tre"))
	if not source_ok(pack, IRA):
		if _ira_tat(pack):
			return out
		raise NotRunnable("ira")
	muc = cfg.muc(_n(pack, f"{IRA}.ty_le"))
	if muc:
		detail = ("Số đếm thực tế lệch sổ ở nhiều mã; cần tìm nguyên nhân (xuất không chứng từ, nhầm mã, "
			"nhầm lô).")
		if _n(pack, f"{IRA}.so_ma_khop") is not None and _n(pack, f"{IRA}.so_ma") is not None:
			detail = (f"Chỉ {ph(f'{IRA}.so_ma_khop', 'so')} trên {ph(f'{IRA}.so_ma', 'so')} mã đếm khớp sổ; "
				"cần tìm nguyên nhân (xuất không chứng từ, nhầm mã, nhầm lô).")
		out.append(cfg.signal(muc, f"Kiểm kê gần nhất chỉ {ph(f'{IRA}.ty_le', 'pct')} mã khớp sổ",
			detail=detail, obj="ira"))
	return out


@rule("kho.xuat_khac_cao", section="kiem-ke", sources=[XK], vang=30_000_000, unit="đ",
	label="Xuất kho ngoài bán hàng trong tháng")
def xuat_khac_cao(pack, cfg):
	"""Xuất khác (xuất mẫu, xuất huỷ… — không phải bán, kiểm kê, dọn tồn, bù nợ BOM) trong tháng ≥ 30 tr."""
	muc = cfg.muc(_n(pack, f"{XK}.gia_tri"), bang=True)
	if not muc:
		return []
	ly_do = "hàng ra khỏi kho không qua bán hàng, cần xem từng loại xuất có đúng mục đích không."
	detail = "Đây là " + ly_do
	if _n(pack, f"{XK}.so_phieu") is not None and _ngay(resolve(pack, f"{KKM}.from", None)) \
			and _ngay(resolve(pack, f"{KKM}.to", None)):
		detail = (f"{ph(f'{XK}.so_phieu', 'so')} phiếu từ {ph(f'{KKM}.from', 'ngay')} đến "
			f"{ph(f'{KKM}.to', 'ngay')}: " + ly_do)
	return [cfg.signal(muc, f"Xuất kho ngoài bán hàng {ph(f'{XK}.gia_tri', 'tien')} trong tháng",
		detail=detail, paths=[f"{XK}.gia_tri"])]


# ─── Nhập thành phẩm & giá vốn ───────────────────────────────────────────────
@rule("kho.no_bom", section="nhap-tp", sources=[NB], vang=7, do=30, unit="ngày", label="Nợ BOM lâu ngày")
def no_bom(pack, cfg):
	"""Phiếu nợ BOM cũ nhất còn chờ > 7 ngày (vàng) / > 30 ngày (đỏ)."""
	muc = cfg.muc(_n(pack, f"{NB}.age_days"))
	if not muc:
		return []
	ly_do = "nguyên liệu chưa được trừ khỏi kho và giá vốn đang là giá tạm."
	detail = "Đang chờ định mức: " + ly_do
	if _n(pack, f"{NB}.items") is not None:
		detail = f"{ph(f'{NB}.items', 'so')} mã thành phẩm đang chờ định mức: " + ly_do
	return [cfg.signal(muc,
		f"Thành phẩm nhập kho chưa có định mức (BOM) đã {ph(f'{NB}.age_days', 'so')} ngày",
		detail=detail, paths=[f"{NB}.age_days"])]


@rule("kho.gia_von_0", section="nhap-tp", sources=[GV0], vang=0, unit="mã",
	label="Thành phẩm chưa có giá vốn")
def gia_von_0(pack, cfg):
	"""Có mã thành phẩm tồn ở kho bán được với giá vốn ≤ 0, hoặc nhập trong tháng với đơn giá 0 → vàng."""
	ton, nhap = f"{GV0}.ton.items", f"{GV0}.nhap_ky.items"
	m1, m2 = cfg.muc(_n(pack, ton)), cfg.muc(_n(pack, nhap))
	if not (m1 or m2):
		return []
	if m1:
		title = f"{ph(ton, 'so')} mã thành phẩm đang tồn mà chưa có giá vốn"
		detail = "Giá trị tồn kho và lãi gộp khi bán các mã này đang bị tính sai."
		if m2:
			detail = (f"Trong tháng còn {ph(nhap, 'so')} mã nhập kho không có đơn giá; giá trị tồn và lãi "
				"gộp đang bị tính sai.")
	else:
		title = f"{ph(nhap, 'so')} mã thành phẩm nhập kho trong tháng không có đơn giá"
		detail = "Giá vốn các mã này sẽ bị tính thiếu, làm sai giá trị tồn và lãi gộp."
	return [cfg.signal("do" if "do" in (m1, m2) else "vang", title, detail=detail)]
