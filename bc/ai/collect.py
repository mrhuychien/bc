# -*- coding: utf-8 -*-
"""bc.ai.collect — dựng gói số (pack) từ CHÍNH các method bc.api.* (đặc tả §3): AI thấy đúng cái lãnh đạo thấy trên
màn hình, đã qua luật riêng tư của bc. File này KHÔNG đọc DocType nghiệp vụ nào trực tiếp và chỉ import frappe,
bc.api.*, thư viện chuẩn (bộ thử AST chặn). Muốn AI thấy thêm số gì → thêm vào màn bc trước.

Luật:
- Danh sách lời gọi CỐ ĐỊNH (CALLS) — đúng bảng §3 của đặc tả, tên method và tên tham số đã đối chiếu với bc/api/*.py.
  Không có thoi-gian-thuc (5:30 sáng chưa có số trong ngày) và không có tro-ly (chính mảng này).
- Mọi lời gọi refresh=1: tính lại + ghi cache. Tham số còn lại để ĐÚNG như màn hình gọi lúc mở (tháng này, mùa này)
  nên khoá cache trùng với khoá màn sẽ đọc buổi sáng: kd.get_daily / sx.get_daily_summary nhận năm + tháng của
  `today`; kho_kk / kho_nhap / vc / attp.get_report để mặc định (tháng này); kd.get_top_products nhóm "all".
- Một lời gọi lỗi (kể cả _guard chặn, module không import được) → riêng mục đó thành {"_error": True}, các mục khác
  vẫn có số; frappe.clear_last_message() để lời báo lỗi không lọt ra ngoài. Error Log chỉ ghi TÊN loại lỗi + vị trí
  dòng code — KHÔNG ghi lời của lỗi, không traceback kèm biến (lời lỗi / biến có thể chứa số liệu, tên khách).
- Không đổi người dùng ở đây: nơi gọi (bc.ai.pipeline) đã set_user("Administrator") nên qua _guard kể cả mảng đang
  ẩn. Gọi dưới người xem → mảng đang ẩn với người đó thành _error (không ném lỗi).
"""

from __future__ import annotations

import importlib
import traceback

import frappe


def _khong(today) -> dict:
	"""Không tham số: method tự lấy kỳ mặc định (năm tài chính / mùa / tháng này)."""
	return {}


def _nam_thang(today) -> dict:
	"""Năm + tháng của `today` (kd.get_daily, sx.get_daily_summary)."""
	return {"year": today.year, "month": today.month}


def _moi_nhom(today) -> dict:
	"""kd.get_top_products: mọi nhóm hàng."""
	return {"group": "all"}


# (mảng, tên, "module.method" trong bc.api, hàm dựng tham số từ today → dict kwargs)
CALLS: tuple = (
	("tong-quan", "summary", "kd.get_summary", _khong),
	("tong-quan", "channels", "kd.get_channels", _khong),
	("tong-quan", "item_groups", "kd.get_item_groups", _khong),
	("tong-quan", "top_customers", "kd.get_top_customers", _khong),
	("ngay", "daily", "kd.get_daily", _nam_thang),
	("thang", "monthly", "kd.get_monthly", _khong),
	("tet", "npp_growth", "tet.get_npp_growth", _khong),
	("tet", "items", "tet.get_items", _khong),
	("tinh-thanh", "provinces", "kd.get_provinces", _khong),
	("san-pham", "top_products", "kd.get_top_products", _moi_nhom),
	("sx-tet", "items", "sx.get_items", _khong),
	("sx-tet", "daily", "sx.get_daily_summary", _nam_thang),
	("ton-kho", "overview", "kho_ton.get_overview", _khong),
	("ton-kho", "trend", "kho_ton.get_trend", _khong),
	("han-dung", "overview", "kho_han.get_overview", _khong),
	("kiem-ke", "overview", "kho_kk.get_overview", _khong),
	("nhap-tp", "overview", "kho_nhap.get_overview", _khong),
	("van-chuyen", "overview", "vc.get_overview", _khong),
	("cong-no", "receivables", "cn.get_receivables", _khong),
	("phai-tra", "payables", "cn.get_payables", _khong),
	("nhan-su", "overview", "ns.get_overview", _khong),
	("attp", "overview", "attp.get_overview", _khong),
	("attp", "report", "attp.get_report", _khong),
)


def _goi(dotted: str, kwargs: dict):
	"""Gọi thẳng hàm Python bc.api.<module>.<method>(refresh=1, **kwargs) — không qua HTTP."""
	mod, fn = dotted.split(".")
	return getattr(importlib.import_module(f"bc.api.{mod}"), fn)(refresh=1, **kwargs)


def _ghi_loi(dotted: str, e: BaseException) -> None:
	"""Error Log không dữ liệu: tên loại lỗi + các dòng code (file:dòng hàm). KHÔNG str(e), không biến cục bộ."""
	try:
		noi = " <- ".join(f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno} {f.name}"
			for f in reversed(traceback.extract_tb(e.__traceback__)[-6:]))
		frappe.log_error(title=f"bc.ai collect {dotted}", message=f"{type(e).__name__} tại {noi or '?'}")
	except Exception:  # ghi nhật ký hỏng không được làm hỏng lượt chạy
		pass


def build(today=None) -> dict:
	"""pack = {mảng: {tên: payload}} — gọi thẳng hàm Python với refresh=1 (tính lại + làm ấm cache), mỗi lời gọi bọc
	try/except: lỗi → {"_error": True} + frappe.clear_last_message() (không ghi traceback có dữ liệu). Nơi gọi phải
	đang là Administrator (qua _guard kể cả mảng đang ẩn). Không lấy thoi-gian-thuc."""
	today = frappe.utils.getdate(today)
	pack: dict = {}
	for section, name, dotted, tham_so in CALLS:
		try:
			payload = _goi(dotted, tham_so(today))
			if not isinstance(payload, dict):
				raise TypeError("payload không phải dict")
		except Exception as e:
			payload = {"_error": True}
			frappe.clear_last_message()
			_ghi_loi(dotted, e)
		pack.setdefault(section, {})[name] = payload
	return pack
