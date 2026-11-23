# -*- coding: utf-8 -*-
"""bc.ai.llm — CỬA DUY NHẤT ra mô hình ngôn ngữ (đặc tả §5.1). Chỉ package này import `requests` và đọc khoá
`bc_ai_*_key` trong site_config (bộ thử AST chặn nơi khác).

Khoá đọc bằng frappe.conf.get(...) NGAY TRONG hàm gọi; không gán biến module, không đưa vào message lỗi / log.
Bộ thử thay `bc.ai.llm.call` bằng bản giả — không test nào được ra mạng.
"""

from __future__ import annotations

PROVIDERS = {"claude": "bc_ai_anthropic_key", "openai": "bc_ai_openai_key"}   # provider → khoá trong site_config
KINDS = ("no_key", "credit", "rate", "http", "timeout", "schema", "refusal")


class LLMError(Exception):
	"""Lỗi gọi mô hình. kind ∈ KINDS; message ≤ 300 ký tự, ĐÃ xoá mọi chuỗi trùng khoá."""

	def __init__(self, kind: str, message: str = ""):
		super().__init__(message)
		self.kind = kind
		self.message = message


def run_status(kind: str) -> str:
	"""LLMError.kind → BC AI Run.status."""
	return {"credit": "het-credit", "no_key": "khong-khoa"}.get(kind, "loi")


def has_key(provider: str) -> bool:
	"""Site có khai khoá của provider không (chỉ trả có / không)."""
	raise NotImplementedError


def call(provider: str, model: str, system: str, user: str, schema_name: str, schema: dict,
		max_tokens: int = 16000, timeout: int = 300) -> dict:
	"""Một lượt gọi → {"data": dict theo schema, "tokens_in": int, "tokens_out": int, "model": str (mô hình thực trả
	lời)}. Lỗi → LLMError(kind). Retry tối đa 2 lần (5 s / 20 s) chỉ cho 429 giới hạn tốc độ, 5xx, timeout; hết credit →
	kind "credit", KHÔNG retry."""
	raise NotImplementedError
