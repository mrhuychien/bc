# -*- coding: utf-8 -*-
"""bc.ai.rules.ns — quy tắc nhóm Nhân sự (đặc tả §4.1, prefix ns.*). Hàm THUẦN trên gói số: không SQL,
không frappe.

Nguồn đã đối chiếu code bc.api.ns.get_overview và view nhan-su.js (bảng path: docs/ai-rules-audit.md, mục
Nhân sự). Mọi khối con qua safe_block: lỗi → {"_error": True}, thiếu app / bảng → {"available": False}.
- bhxh {available, uoc_tinh, dang_lam, dong, ty_le, chua_muc, lech, rui_ro, ly_do[]}: rui_ro = số NGƯỜI đang
  làm, vào làm quá 30 ngày, chưa đóng, chưa ghi lý do; None khi uoc_tinh (site chưa cài ns).
- giay_to {available, so_ngay, hd|ksk|attp: {do, vang}}: số người có giấy (mới nhất mỗi loại) đã hết hạn (do)
  / hết hạn trong so_ngay ngày tới (vang).
- canh_bao {available, rows[{ma, ten, muc, so_nguoi}], …}: số người theo mã cảnh báo của ns; ten = nhãn mã
  (ns.api.canh_bao.TEN), không phải tên người.

Luật:
- ns.bhxh_rui_ro: rui_ro > ngưỡng đỏ (mặc định 0) → đỏ (ns tô mã này mức đỏ).
- ns.giay_to: một khoá / nhóm giấy `ns.giay_to:<hd|ksk|attp>`; đỏ khi số người ĐÃ hết hạn > ngưỡng đỏ, vàng
  khi số người SẮP hết hạn > ngưỡng vàng (hai thước đo, mặc định 0 / 0).
- ns.viec_ton: một khoá / mã cảnh báo mức đỏ `ns.viec_ton:<ma>` (dòng tìm theo ma, không theo vị trí); bỏ mã
  bhxh_rui_ro (đã là quy tắc riêng, cùng số) để không báo hai lần.
- Không tên, mã nhân viên, lý do từng người. Mọi số trong lời là placeholder; không gõ chữ số.
- None / thiếu / không phải số → không tín hiệu, không bao giờ ném lỗi.
"""

from __future__ import annotations

import math

from bc.ai.registry import ph, resolve, rule

O = "nhan-su.overview"
BH, GT, CB = f"{O}.bhxh", f"{O}.giay_to", f"{O}.canh_bao"
NHOM_GIAY = (("hd", "hợp đồng lao động"), ("ksk", "khám sức khỏe"), ("attp", "xác nhận ATTP"))
MA_BHXH = "bhxh_rui_ro"     # mã cảnh báo đã có quy tắc riêng


def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _n(pack, path):
	return _so(resolve(pack, path, None))


def _chu(v) -> bool:
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


@rule("ns.bhxh_rui_ro", section="nhan-su", sources=[BH], do=0, unit="người",
	label="Người làm quá một tháng chưa đóng BHXH, chưa ghi lý do")
def bhxh_rui_ro(pack, cfg):
	"""Có người vào làm quá 30 ngày chưa đóng BHXH mà chưa ghi lý do (> 0 → đỏ)."""
	p = f"{BH}.rui_ro"
	muc = cfg.muc(_n(pack, p))
	if not muc:
		return []
	return [cfg.signal(muc, f"{ph(p, 'so')} người quá một tháng chưa đóng BHXH, chưa ghi lý do",
		detail="Công ty có thể bị truy thu và phạt, bộ phận nhân sự cần đăng ký BHXH hoặc ghi rõ lý do.",
		paths=[p])]


@rule("ns.giay_to", section="nhan-su", sources=[GT], vang=0, do=0, unit="người",
	label="Giấy tờ nhân sự đã hết / sắp hết hạn (vàng: sắp hết, đỏ: đã hết)")
def giay_to(pack, cfg):
	"""Mỗi nhóm giấy (HĐ, khám SK, ATTP): đã hết hạn > ngưỡng đỏ → đỏ; sắp hết hạn > ngưỡng vàng → vàng."""
	out = []
	so_ngay = _n(pack, f"{GT}.so_ngay")
	for ma, ten in NHOM_GIAY:
		pd, pv = f"{GT}.{ma}.do", f"{GT}.{ma}.vang"
		da, sap = _n(pack, pd), _n(pack, pv)
		if da is not None and cfg.do is not None and da > cfg.do:
			muc = "do"
		elif sap is not None and cfg.vang is not None and sap > cfg.vang:
			muc = "vang"
		else:
			continue
		if muc == "do":
			title = f"{ph(pd, 'so')} người hết hạn {ten}"
			if sap:
				title += f", {ph(pv, 'so')} người sắp hết"
		else:
			title = f"{ph(pv, 'so')} người sắp hết hạn {ten}"
		han = f"trong {ph(f'{GT}.so_ngay', 'so')} ngày tới" if so_ngay is not None else "sắp tới"
		detail = (f"Giấy hết hạn hoặc hết hạn {han} cần được bộ phận nhân sự làm lại để tránh vi phạm khi "
			"thanh tra.")
		out.append(cfg.signal(muc, title, detail=detail,
			paths=[p for p in (pd, pv) if _n(pack, p) is not None], obj=ma))
	return out


@rule("ns.viec_ton", section="nhan-su", sources=[CB], do=0, unit="người",
	label="Việc nhân sự mức gấp còn tồn (mỗi mã cảnh báo đỏ)")
def viec_ton(pack, cfg):
	"""Mỗi mã cảnh báo mức đỏ của ns (trừ BHXH rủi ro — đã có quy tắc riêng): số người > ngưỡng đỏ → đỏ."""
	rows = resolve(pack, f"{CB}.rows", None)
	if not isinstance(rows, list):
		return []
	out, da = [], set()
	for i, r in enumerate(rows):
		if not isinstance(r, dict) or r.get("muc") != "do":
			continue
		ma = r.get("ma")
		if not isinstance(ma, str) or not ma.strip() or ma == MA_BHXH or ma in da:
			continue
		da.add(ma)
		p = f"{CB}.rows[{i}]"
		muc = cfg.muc(_so(r.get("so_nguoi")))
		if not muc:
			continue
		viec = ph(f"{p}.ten", "chu") if _chu(r.get("ten")) else "Việc nhân sự mức gấp"
		out.append(cfg.signal(muc, f"{viec}: {ph(f'{p}.so_nguoi', 'so')} người",
			detail="Hồ sơ nhân sự còn việc mức gấp chưa xử lý, bộ phận nhân sự cần làm xong trên màn Nhân sự.",
			paths=[f"{p}.so_nguoi"], obj=ma))
	return out
