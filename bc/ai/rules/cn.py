# -*- coding: utf-8 -*-
"""bc.ai.rules.cn — quy tắc nhóm Công nợ (đặc tả §4.1). Hàm THUẦN trên gói số: không SQL, không frappe.

Nguồn đã đối chiếu code bc.api.cn và view cong-no.js / phai-tra.js:
- cong-no.receivables = cn.get_receivables: kpis{receivable, overdue, overdue_pct (đã ×100, 1 số lẻ, None khi
  phải thu 0), dso{debt, revenue, window_days, dso (ngày, None khi doanh thu 0)}, unallocated, over_limit (số
  khách)}; top_overdue[{customer (TÊN THẬT), overdue, max_days, …}] ≤ 10 khách ngoài MT, xếp overdue giảm dần.
- phai-tra.payables = cn.get_payables: meta.due_ahead (= 14), ap.due{overdue_total, overdue_count (số HOÁ ĐƠN),
  upcoming_total, upcoming_count}, cash.total (Σ số dư TK tiền mặt + ngân hàng, có thể âm).
Mọi số tiền VND GỒM VAT.

Luật:
- Giá trị None / thiếu / không phải số → không tín hiệu, không bao giờ ném lỗi.
- Mọi số / tên từ dữ liệu trong lời là placeholder; số tự tính khai trong `tinh`, viết {{@tên|kiểu}}. Tên khách
  chỉ qua {{…customer|chu}} và chỉ ở thân (mã giả thay được). Không tên nhân viên.
- Mốc phụ không nằm trong 2 ô ngưỡng của BC Settings là hằng số ở dưới (QUA_NGAY, NEU_KHACH).
"""

from __future__ import annotations

import math

from bc.ai.registry import ph, resolve, rule

R, P = "cong-no.receivables", "phai-tra.payables"

QUA_NGAY = 90     # cn.qua_han_lon: khách có hoá đơn quá hạn QUÁ ngần này ngày
NEU_KHACH = 5     # cn.qua_han_lon: số khách nêu tên trong lời


def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _chu(v) -> bool:
	"""Chuỗi dùng được cho placeholder kiểu chu (không rỗng, ≤ 120 ký tự)."""
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


def _tron(x: float) -> float:
	"""1 số lẻ, đúng giữa thì làm tròn lên (như Math.round của view)."""
	return math.floor(x * 10 + 0.5) / 10


def _num(pack, path):
	return _so(resolve(pack, path, None))


# ─── Phải thu ────────────────────────────────────────────────────────────────
@rule("cn.qua_han_ty_le", section="cong-no", sources=[R], vang=20, do=35, unit="%", label="Tỷ lệ nợ quá hạn")
def qua_han_ty_le(pack, cfg):
	"""Nợ quá hạn chiếm quá 20% (vàng) / 35% (đỏ) tổng phải thu."""
	v = _num(pack, f"{R}.kpis.overdue_pct")
	muc = cfg.muc(v)
	if not muc:
		return []
	od, rc = f"{R}.kpis.overdue", f"{R}.kpis.receivable"
	if _num(pack, od) is not None and _num(pack, rc) is not None:
		detail = (f"Đã quá hạn {ph(od, 'tien')} trên tổng phải thu {ph(rc, 'tien')}, "
			"cần thúc thu các khách nợ lâu trước khi thành nợ khó đòi.")
	else:
		detail = "Cần thúc thu các khách nợ lâu trước khi thành nợ khó đòi."
	return [cfg.signal(muc, f"Nợ quá hạn chiếm {ph(f'{R}.kpis.overdue_pct', 'pct')} tổng phải thu", detail=detail,
		paths=[f"{R}.kpis.overdue_pct"])]


@rule("cn.qua_han_lon", section="cong-no", sources=[R], vang=50_000_000, unit="đ",
	label="Khách nợ quá hạn lâu với số tiền lớn")
def qua_han_lon(pack, cfg):
	"""Khách (top 10 quá hạn, ngoài MT) có hoá đơn quá hạn quá 90 ngày và nợ quá hạn ≥ 50 triệu → GỘP 1 tín hiệu.

	`overdue` của payload là nợ quá hạn ở MỌI tuổi nợ của khách (không riêng phần > 90 ngày) → lời nói rõ như vậy,
	không câu nào ngụ ý số tiền là phần quá 90 ngày."""
	rows = resolve(pack, f"{R}.top_overdue", None)
	if not isinstance(rows, list):
		return []
	hit = []   # (nợ quá hạn, chỉ số, mức)
	for i, r in enumerate(rows):
		if not isinstance(r, dict):
			continue
		od, days = _so(r.get("overdue")), _so(r.get("max_days"))
		if od is None or days is None or days <= QUA_NGAY:
			continue
		m = cfg.muc(od, bang=True)
		if m:
			hit.append((od, i, m))
	if not hit:
		return []
	hit.sort(key=lambda x: (-x[0], x[1]))
	muc = "do" if any(m == "do" for _o, _i, m in hit) else "vang"
	ten = [f"{ph(f'{R}.top_overdue[{i}].customer', 'chu')} {ph(f'{R}.top_overdue[{i}].overdue', 'tien')}"
		for _o, i, _m in hit if _chu(rows[i].get("customer"))][:NEU_KHACH]
	detail = "Tổng nợ quá hạn ở mọi tuổi nợ của các khách này là {{@tong|tien}}"
	if ten:
		detail += f", nhiều nhất {', '.join(ten)}"
	detail += "; cần thu hồi gấp trước khi thành nợ khó đòi."
	return [cfg.signal(muc, "{{@so_khach|so}} khách có hoá đơn quá hạn trên {{@so_ngay|so}} ngày",
		detail=detail, paths=[f"{R}.top_overdue[{i}].max_days" for _o, i, _m in hit[:NEU_KHACH]],
		tinh={"so_khach": len(hit), "so_ngay": QUA_NGAY, "tong": round(sum(o for o, _i, _m in hit), 2)})]


@rule("cn.vuot_han_muc", section="cong-no", sources=[R], vang=0, unit="khách", label="Khách nợ vượt hạn mức tín dụng")
def vuot_han_muc(pack, cfg):
	"""Có khách nợ vượt hạn mức tín dụng (> 0 khách)."""
	path = f"{R}.kpis.over_limit"
	muc = cfg.muc(_num(pack, path))
	if not muc:
		return []
	return [cfg.signal(muc, f"{ph(path, 'so')} khách nợ vượt hạn mức tín dụng",
		detail="Bán thêm cho các khách này làm tăng rủi ro mất vốn, cần duyệt lại hạn mức hoặc tạm dừng giao hàng.")]


@rule("cn.dso_cao", section="cong-no", sources=[R], vang=45, do=60, unit="ngày", label="Số ngày thu tiền bình quân")
def dso_cao(pack, cfg):
	"""Số ngày thu tiền bình quân (DSO) quá 45 (vàng) / 60 (đỏ) ngày."""
	d = f"{R}.kpis.dso"
	muc = cfg.muc(_num(pack, f"{d}.dso"))
	if not muc:
		return []
	if all(_num(pack, f"{d}.{k}") is not None for k in ("debt", "revenue", "window_days")):
		detail = (f"Khách đang nợ {ph(f'{d}.debt', 'tien')} so với doanh thu gồm VAT {ph(f'{d}.revenue', 'tien')} "
			f"trong {ph(f'{d}.window_days', 'so')} ngày gần nhất, tiền bị khách giữ lâu làm thiếu vốn quay vòng.")
	else:
		detail = "Tiền bị khách giữ lâu làm thiếu vốn quay vòng, cần siết thời hạn thanh toán."
	return [cfg.signal(muc, f"Bình quân {ph(f'{d}.dso', 'so')} ngày mới thu được tiền bán hàng", detail=detail)]


@rule("cn.chua_phan_bo", section="cong-no", sources=[R], vang=100_000_000, unit="đ",
	label="Tiền khách trả chưa gắn hoá đơn")
def chua_phan_bo(pack, cfg):
	"""Tiền khách trả chưa gắn vào hoá đơn từ 100 triệu."""
	path = f"{R}.kpis.unallocated"
	muc = cfg.muc(_num(pack, path), bang=True)
	if not muc:
		return []
	return [cfg.signal(muc, f"{ph(path, 'tien')} tiền khách trả chưa gắn vào hoá đơn",
		detail="Kế toán cần gắn khoản này vào hoá đơn, nếu không nợ quá hạn của khách bị báo cao hơn thực tế.")]


# ─── Phải trả ────────────────────────────────────────────────────────────────
@rule("cn.phai_tra_qua_han", section="phai-tra", sources=[P], vang=0, do=200_000_000, unit="đ",
	label="Tiền hàng nhà cung cấp quá hạn")
def phai_tra_qua_han(pack, cfg):
	"""Hoá đơn mua quá hạn chưa trả: > 0 (vàng) / ≥ 200 triệu (đỏ)."""
	path = f"{P}.ap.due.overdue_total"
	v = _num(pack, path)
	if not cfg.muc(v):              # vàng so ngặt (> 0)
		return []
	muc = "do" if cfg.muc(v, bang=True) == "do" else "vang"   # đỏ có dấu bằng (≥ 200 tr)
	n = f"{P}.ap.due.overdue_count"
	detail = "Trả chậm dễ bị nhà cung cấp dừng giao hàng hoặc tính phạt."
	if _num(pack, n) is not None:
		detail = f"Gồm {ph(n, 'so')} hoá đơn mua, trả chậm dễ bị nhà cung cấp dừng giao hàng hoặc tính phạt."
	return [cfg.signal(muc, f"{ph(path, 'tien')} tiền hàng nhà cung cấp đã quá hạn chưa trả", detail=detail)]


@rule("cn.thieu_tien_14_ngay", section="phai-tra", sources=[P], vang=80, do=100, unit="%",
	label="Phải trả sắp tới so với quỹ tiền")
def thieu_tien_14_ngay(pack, cfg):
	"""(Quá hạn + đến hạn 14 ngày tới) / quỹ tiền > 80% (vàng) / > 100% (đỏ); quỹ ≤ 0 mà còn phải trả → đỏ."""
	od, up, q = f"{P}.ap.due.overdue_total", f"{P}.ap.due.upcoming_total", f"{P}.cash.total"
	a, b, quy = _num(pack, od), _num(pack, up), _num(pack, q)
	if a is None or b is None or quy is None:
		return []
	phai = round(a + b, 2)
	if phai <= 0:
		return []
	ngay = f"{P}.meta.due_ahead"
	toi = f"{ph(ngay, 'so')} ngày tới" if _num(pack, ngay) is not None else "sắp tới"
	if quy <= 0:
		return [cfg.signal("do", "Quỹ tiền đã hết trong khi còn {{@phai|tien}} phải trả",
			detail=(f"Quá hạn {ph(od, 'tien')} cộng đến hạn {toi} {ph(up, 'tien')} mà quỹ tiền mặt và ngân hàng còn "
				f"{ph(q, 'tien')}, cần lên kế hoạch dòng tiền ngay."), tinh={"phai": phai})]
	ty_le = _tron(phai / quy * 100)
	muc = cfg.muc(ty_le)
	if not muc:
		return []
	return [cfg.signal(muc, "Tiền phải trả sắp tới bằng {{@ty_le|pct}} quỹ tiền hiện có",
		detail=(f"Quá hạn {ph(od, 'tien')} cộng đến hạn {toi} {ph(up, 'tien')} trong khi quỹ tiền mặt và ngân hàng "
			f"còn {ph(q, 'tien')}, cần lên kế hoạch dòng tiền."), tinh={"phai": phai, "ty_le": ty_le})]
