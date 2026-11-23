# -*- coding: utf-8 -*-
"""bc.ai.redact — mã giả khách / nhà cung cấp trước khi gửi gói số cho mô hình (đặc tả §5.4).

Bảng ánh xạ dựng MỖI LƯỢT từ tabCustomer (name, customer_name) và tabSupplier (name, supplier_name) → "KH#0001…",
"NCC#0001…" (một đối tác một mã, cả mã chứng từ lẫn tên hiển thị cùng về mã đó). Chỉ thay chuỗi BẰNG ĐÚNG một tên
(không thay chuỗi con). Bảng không lưu, không gửi. Path luôn phân giải trên pack GỐC (bc.ai.render) nên số / tên chèn
vào lời là thật.
"""

from __future__ import annotations


class Mask:
	"""Bộ mã giả của một lượt chạy. Mask() rỗng = không che gì (ai_mask_parties tắt)."""

	def __init__(self, parties=None):
		"""parties: [(mã_giả, tên_hiển_thị, {các chuỗi cần thay})]."""
		raise NotImplementedError

	def mask(self, obj):
		"""Bản SAO sâu của obj (dict / list / scalar), mọi chuỗi (giá trị, KHÔNG phải khoá dict) bằng đúng một tên đã
		biết → mã giả. Không đổi obj gốc."""
		raise NotImplementedError

	def unmask(self, text: str) -> str:
		"""Thay mọi mã giả ĐÃ BIẾT trong text về tên hiển thị thật."""
		raise NotImplementedError

	def strip(self, text: str) -> str:
		"""Bỏ mọi mã giả ĐÃ BIẾT khỏi text (thay bằng dấu cách) — để lint không bắt nhầm chữ số trong mã giả; mã giả lạ
		(mô hình bịa) giữ nguyên để lint bắt."""
		raise NotImplementedError


def build(enabled: bool = True) -> Mask:
	"""Mask từ tabCustomer / tabSupplier (đọc mềm: thiếu bảng thì bỏ). enabled False → Mask rỗng. Mã đánh số theo thứ
	tự `name` tăng dần (ổn định trong một lượt)."""
	raise NotImplementedError
