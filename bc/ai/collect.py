# -*- coding: utf-8 -*-
"""bc.ai.collect — dựng gói số (pack) từ CHÍNH các method bc.api.* (đặc tả §3): AI thấy đúng cái lãnh đạo thấy trên
màn hình, đã qua luật riêng tư của bc. File này KHÔNG đọc DocType nghiệp vụ nào trực tiếp và chỉ import frappe,
bc.api.*, thư viện chuẩn (bộ thử AST chặn). Muốn AI thấy thêm số gì → thêm vào màn bc trước.
"""

from __future__ import annotations

# (mảng, tên, "module.method" trong bc.api, hàm dựng tham số từ today → dict kwargs)
CALLS: tuple = ()


def build(today=None) -> dict:
	"""pack = {mảng: {tên: payload}} — gọi thẳng hàm Python với refresh=1 (tính lại + làm ấm cache), mỗi lời gọi bọc
	try/except: lỗi → {"_error": True} + frappe.clear_last_message() (không ghi traceback có dữ liệu). Nơi gọi phải
	đang là Administrator (qua _guard kể cả mảng đang ẩn). Không lấy thoi-gian-thuc."""
	raise NotImplementedError
