# -*- coding: utf-8 -*-
"""bc.ai.rules.attp — quy tắc nhóm ATTP (đặc tả §4.1, prefix attp.*). Hàm THUẦN trên gói số: không SQL,
không frappe.

Nguồn đã đối chiếu code bc.api.attp và view attp.js (bảng path: docs/ai-rules-audit.md, mục ATTP):
- attp.overview = attp.get_overview: linh_vuc[{ma, ten, bieu_mau, den: do|vang|xanh, so, nhan_so, dong[],
  nhac[{muc_do, tieu_de, chi_tiet}]}], dem {do, vang, xanh}. `so` / `nhan_so` là CHUỖI đã định dạng của sx
  ("55,6%", "0/0", "–") → không dùng làm số. nhac[].tieu_de / chi_tiet là chữ tự do (có thể có tên khách /
  NCC) → không đưa vào lời, chỉ đếm.
- attp.report = attp.get_report() (tháng trước): nam, chi_tieu[{chi_so, ten, so_sanh, muc_tieu, don_vi, ky,
  nam_luy_ke, dat_ky, dat_nam}] — dat_* True / False / None (chưa có số). don_vi "%" → giá trị đã ×100.

Luật:
- attp.den_do: một khoá `attp.den_do:<ma>` / lĩnh vực đèn đỏ (tìm theo ma, không theo vị trí); mức đỏ cố định
  (luật đèn của sx). Số việc treo / việc mức cao tự đếm → `tinh`.
- attp.chi_tieu: một khoá `attp.chi_tieu:<chi_so>` / chỉ tiêu có dat_nam là False (luỹ kế năm chưa đạt);
  mức vàng cố định. Hai chỉ tiêu cùng chỉ số → lấy dòng đầu.
- None / thiếu / rác → không tín hiệu, không bao giờ ném lỗi. Không gõ chữ số trong lời.
"""

from __future__ import annotations

import math
from decimal import Decimal

from bc.ai.registry import ph, resolve, rule

OV, RP = "attp.overview", "attp.report"


def _so(v):
	"""Số thật hữu hạn (int / float / Decimal của MariaDB — sx đọc muc_tieu Float thành Decimal) → chính nó."""
	if isinstance(v, Decimal):
		return v if v.is_finite() else None
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _chu(v) -> bool:
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


def _ma(v) -> bool:
	"""Mã dùng làm đối tượng của khoá tín hiệu: chuỗi ngắn, không khoảng trắng."""
	return isinstance(v, str) and 0 < len(v) <= 60 and not any(ch.isspace() for ch in v)


@rule("attp.den_do", section="attp", sources=[OV], label="Lĩnh vực ATTP báo đèn đỏ")
def den_do(pack, cfg):
	"""Mỗi lĩnh vực ATTP đèn đỏ → một tín hiệu đỏ."""
	rows = resolve(pack, f"{OV}.linh_vuc", None)
	if not isinstance(rows, list):
		return []
	out, da = [], set()
	for i, t in enumerate(rows):
		if not isinstance(t, dict) or t.get("den") != "do" or not _ma(t.get("ma")) or t["ma"] in da:
			continue
		da.add(t["ma"])
		p = f"{OV}.linh_vuc[{i}]"
		ten = ph(f"{p}.ten", "chu") if _chu(t.get("ten")) else "một lĩnh vực"
		nhac = [x for x in (t.get("nhac") or []) if isinstance(x, dict)] if isinstance(t.get("nhac"), list) else []
		cao = sum(1 for x in nhac if x.get("muc_do") == "cao")
		tinh = {}
		if nhac:
			tinh = {"viec": len(nhac), "cao": cao}
			detail = ("Còn {{@viec|so}} việc treo, trong đó {{@cao|so}} việc mức cao, Ban ATTP cần xử lý để "
				"giữ an toàn sản phẩm.")
		else:
			detail = "Lĩnh vực này đang không đạt yêu cầu an toàn thực phẩm, Ban ATTP cần kiểm tra ngay."
		out.append(cfg.signal("do", f"ATTP: {ten} đang báo đèn đỏ", detail=detail, paths=[f"{p}.ten"]
			if _chu(t.get("ten")) else [], tinh=tinh, obj=t["ma"]))
	return out


@rule("attp.chi_tieu", section="attp", sources=[RP], label="Chỉ tiêu ATTP năm luỹ kế chưa đạt")
def chi_tieu(pack, cfg):
	"""Mỗi chỉ tiêu năm có luỹ kế chưa đạt (dat_nam là False) → một tín hiệu vàng."""
	rows = resolve(pack, f"{RP}.chi_tieu", None)
	if not isinstance(rows, list):
		return []
	out, da = [], set()
	for i, c in enumerate(rows):
		if not isinstance(c, dict) or c.get("dat_nam") is not False or not _ma(c.get("chi_so")):
			continue
		if c["chi_so"] in da:
			continue
		da.add(c["chi_so"])
		p = f"{RP}.chi_tieu[{i}]"
		kieu = "pct" if c.get("don_vi") == "%" else "so"
		ten = ph(f"{p}.ten", "chu") if _chu(c.get("ten")) else "ATTP"
		title = f"Chỉ tiêu {ten} luỹ kế năm chưa đạt"
		paths = []
		if _so(c.get("nam_luy_ke")) is not None and _so(c.get("muc_tieu")) is not None:
			so_sanh = f" {ph(f'{p}.so_sanh', 'chu')}" if _chu(c.get("so_sanh")) else ""
			detail = (f"Luỹ kế năm đạt {ph(f'{p}.nam_luy_ke', kieu)}, mục tiêu{so_sanh} "
				f"{ph(f'{p}.muc_tieu', kieu)}, cần rà nguyên nhân với Ban ATTP.")
			paths = [f"{p}.nam_luy_ke", f"{p}.muc_tieu"]
		else:
			detail = "Luỹ kế năm chưa đạt mục tiêu đã đặt, cần rà nguyên nhân với Ban ATTP."
		out.append(cfg.signal("vang", title, detail=detail, paths=paths, obj=c["chi_so"]))
	return out
