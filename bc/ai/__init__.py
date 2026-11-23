# -*- coding: utf-8 -*-
"""bc.ai — Trợ lý AI của app bc (đặc tả: docs/SPEC_bc_ai.md).

Luồng: bc.ai.jobs (xếp hàng) → bc.ai.pipeline.run_daily: collect (gói số từ bc.api.*) → detector hệ thống → quy tắc
sinh tín hiệu → lưu BC AI Insight → (bật AI) Claude viết lời → máy chủ thay số, kiểm số trần → nhật ký BC AI Run.
"""

from __future__ import annotations

import frappe

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_SIGNALS = 40


def conf(field: str, default=None):
	"""BC Settings.<field> đọc thẳng tabSingles (luôn tươi, không vướng meta khi site chưa migrate). Chưa từng lưu
	(không có dòng) hoặc chuỗi rỗng → `default`. Trả CHUỖI như lưu — nơi gọi tự cint / flt.

	Dùng cho các ô mà "chưa lưu" phải khác "tắt": ai_mask_parties chưa lưu = BẬT (không được hiểu là 0)."""
	r = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", ("BC Settings", field))
	if not r or r[0][0] in (None, ""):
		return default
	return r[0][0]


def daily_model() -> str:
	"""Model Claude viết lời hằng ngày: BC Settings.ai_claude_model, để trống → DEFAULT_CLAUDE_MODEL. MỘT nơi phân giải
	cho pipeline, màn Cấu hình AI và nút Thử kết nối (màn không được báo "chưa chọn model" trong khi lượt chạy vẫn
	gọi model mặc định)."""
	return str(conf("ai_claude_model") or "").strip() or DEFAULT_CLAUDE_MODEL
