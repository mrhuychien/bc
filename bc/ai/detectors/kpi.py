# -*- coding: utf-8 -*-
"""bc.ai.detectors.kpi — detector "kpi" (mảng tro-ly, hợp đồng P2 §3.2): lịch sử 28 ngày của từng KPI (registry.KPIS) từ
BC AI Run.kpis + giá trị hôm nay = registry.snapshot_kpis(ctx["pack"]). Quy tắc kpi.lech_chuan ở bc.ai.rules.ks.

- Lịch sử: dòng tổng (step 'tong') status 'ok', run_type 'ngay' / 'tay', `started` trong 28 ngày TRƯỚC hôm nay
  ([today − 28, today − 1], ngày lịch); mỗi ngày lấy ảnh chụp MUỘN NHẤT (started lớn nhất, rồi name). Ảnh chụp hỏng
  (JSON sai / không phải dict) bỏ qua; giá trị không phải số bỏ qua.
- Bỏ KPI cộng dồn trong kỳ (registry.KPI_TICH_LUY) và tỷ lệ tính trên kỳ tới hôm nay (KPI_THEO_KY — đầu kỳ chỉ có vài
  ngày số nên dao động mạnh, đổi kỳ là đổi nền: so trung vị 28 ngày chỉ ra báo động giả mỗi đầu tháng / đầu năm tài
  chính). Lý do từng path: docs/ai-rules-audit.md mục "Kiểm soát".
- rows: KPI có giá trị hôm nay VÀ ≥ 14 ngày lịch sử: {path, kieu, nhan, hom_nay, trung_vi (trung vị 28 ngày), mad
  (trung vị |giá trị − trung vị|, KHÔNG nhân hệ số), lech (hôm nay − trung vị), so_mad (|lech| / max(mad, 1% |trung
  vị|); mẫu 0 → None), n (số ngày lịch sử của KPI)}. Số làm tròn 6 chữ số lẻ (khử sai số dấu phẩy động, không đổi phép
  so của quy tắc). so_ngay = số ngày có ảnh chụp.
- Khối này nằm trong registry.NO_SEND: số của MỌI mảng, không bao giờ gửi mô hình.

Hiệu năng: BC AI Run chỉ vài dòng mỗi ngày (giữ ≤ 400 ngày); lọc started trong dải 28 ngày.
"""

from __future__ import annotations

import datetime
import json
import math
import statistics
from decimal import Decimal

import frappe
from frappe.utils import getdate

from bc.ai import registry
from bc.ai.registry import TRO_LY, detector

CUA_SO = 28          # số ngày lịch sử
NGAY_MIN = 14        # số ngày lịch sử tối thiểu của một KPI
RUN_TYPES = ("ngay", "tay")

# Tỷ lệ tính trên kỳ tới hôm nay (không cộng dồn — không thuộc KPI_TICH_LUY — nhưng nền đổi mỗi đầu kỳ).
KPI_THEO_KY: frozenset = frozenset({
	"tong-quan.summary.rows[0].return_rate",       # năm tài chính tới hôm nay
	"tong-quan.summary.meta.growth.sales",         # năm tài chính tới hôm nay so cùng kỳ
	"tong-quan.summary.meta.growth.net",
	"tinh-thanh.provinces.rows[0].pct",            # tỷ trọng tỉnh đứng đầu, năm tài chính tới hôm nay
	"van-chuyen.overview.giao.ty_le_giao",         # tháng này tới hôm nay
	"van-chuyen.overview.giao.lan_dau.ty_le",      # tháng này tới hôm nay
	"van-chuyen.overview.cuoc.ty_le_doanh_thu",    # tháng này tới hôm nay
})


def _so(v):
	if isinstance(v, Decimal):
		v = float(v)
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def bo_qua(path: str) -> bool:
	"""KPI không so với trung vị 28 ngày."""
	return path in registry.KPI_TICH_LUY or path in KPI_THEO_KY


def lich_su(today) -> dict:
	"""{ngày: {path: số}} — ảnh chụp muộn nhất mỗi ngày trong [today − 28, today − 1]."""
	today = getdate(today)
	tu = datetime.datetime.combine(today - datetime.timedelta(days=CUA_SO), datetime.time())
	den = datetime.datetime.combine(today, datetime.time())
	out: dict = {}
	for r in frappe.db.sql("""SELECT started, kpis FROM `tabBC AI Run`
			WHERE step = 'tong' AND status = 'ok' AND run_type IN %(rt)s AND started >= %(tu)s AND started < %(den)s
			ORDER BY started ASC, name ASC""", {"rt": RUN_TYPES, "tu": tu, "den": den}, as_dict=True):
		try:
			k = json.loads(r.kpis) if isinstance(r.kpis, str) else r.kpis
		except ValueError:
			continue
		if isinstance(k, dict):
			out[frappe.utils.get_datetime(r.started).date()] = k     # muộn hơn ghi đè
	return out


def _r(x):
	return None if x is None else round(x, 6)


@detector("kpi", section=TRO_LY)
def d_kpi(ctx):
	if not frappe.db.table_exists("BC AI Run"):
		return {"available": False}
	ls = lich_su(ctx["today"])
	nay = registry.snapshot_kpis(ctx.get("pack") or {})
	rows = []
	for path, kieu, nhan in registry.KPIS:
		x = nay.get(path)
		if x is None or bo_qua(path):
			continue
		vals = [v for v in (_so(d.get(path)) for _ngay, d in sorted(ls.items())) if v is not None]
		if len(vals) < NGAY_MIN:
			continue
		med = statistics.median(vals)
		mad = statistics.median([abs(v - med) for v in vals])
		mau = max(mad, 0.01 * abs(med))
		lech = x - med
		rows.append({"path": path, "kieu": kieu, "nhan": nhan, "hom_nay": x, "trung_vi": _r(med), "mad": _r(mad),
			"lech": _r(lech), "so_mad": _r(abs(lech) / mau) if mau > 0 else None, "n": len(vals)})
	return {"so_ngay": len(ls), "cua_so": CUA_SO, "ngay_min": NGAY_MIN, "rows": rows}
