# -*- coding: utf-8 -*-
"""bc.ai.llm — CỬA DUY NHẤT ra mô hình ngôn ngữ (đặc tả §5.1). Chỉ package này import `requests` và đọc khoá
`bc_ai_*_key` trong site_config (bộ thử AST chặn nơi khác).

Luật khoá: đọc bằng frappe.conf.get(...) NGAY TRONG hàm cần dùng; không gán biến module, không nằm trong dict trả về,
không nằm trong message lỗi / log. Mọi LLMError tự làm sạch message lúc tạo (clean): xoá mọi chuỗi trùng khoá đang
khai + mọi chuỗi có dạng khoá `sk-…`, RỒI mới cắt 300 ký tự (cắt trước thì nửa khoá nằm ở mép sẽ lọt). Lỗi ra khỏi
call() được ném NGOÀI khối except (không kéo theo ngoại lệ gốc — lời của thư viện HTTP có thể chứa khoá), vết lỗi
chỉ còn khung của call() và khung đó đã bỏ các biến mang đề bài / gói số.
Module khác cần lưu / ghi log một chuỗi lỗi bất kỳ của bước AI: đưa qua clean() trước.

Đầu ra mô hình được kiểm lại theo schema ở đây (schema_error) dù nhà cung cấp đã ép cấu trúc — sai → kind "schema".
Bộ thử thay `bc.ai.llm.call` bằng bản giả — không test nào được ra mạng.
"""

from __future__ import annotations

import os
import re

import frappe

PROVIDERS = {"claude": "bc_ai_anthropic_key", "openai": "bc_ai_openai_key"}   # provider → khoá trong site_config
KINDS = ("no_key", "credit", "rate", "http", "timeout", "schema", "refusal")
MAX_MESSAGE = 300
MASK = "***"
# Mọi thứ trông như khoá API (khoá cũ, khoá của site khác, khoá bị cắt cụt) — không bắt nhầm "task-…", "risk-…".
_KEY_LIKE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{8,}")


def clean(text) -> str:
	"""Chuỗi an toàn để lưu vào BC AI Run.error / ghi log: đã xoá mọi chuỗi trùng khoá API đang khai (và mọi chuỗi có
	dạng khoá), cắt MAX_MESSAGE ký tự."""
	s = "" if text is None else str(text)
	for name in PROVIDERS.values():
		try:
			k = str(frappe.conf.get(name) or "")
		except Exception:   # ngoài ngữ cảnh site (không có conf): vẫn còn lớp xoá theo mẫu ở dưới
			k = ""
		for v in (k, k.strip()):   # khoá khai thừa dấu cách / xuống dòng: xoá cả hai dạng
			if v:
				s = s.replace(v, MASK)
	return _KEY_LIKE.sub(MASK, s)[:MAX_MESSAGE]


class LLMError(Exception):
	"""Lỗi gọi mô hình. kind ∈ KINDS; message ≤ 300 ký tự, ĐÃ xoá mọi chuỗi trùng khoá.

	tokens_in / tokens_out / model: số token ĐÃ BỊ TÍNH TIỀN của lượt hỏng khi máy chủ có trả lời (từ chối, đầu ra bị
	cắt, sai cấu trúc) — nơi gọi nên ghi vào Run để trần chi không đếm thiếu; lỗi HTTP / mạng thì 0."""

	def __init__(self, kind: str, message: str = ""):
		message = clean(message)
		super().__init__(message)
		self.kind = kind
		self.message = message
		self.tokens_in = 0
		self.tokens_out = 0
		self.model = ""

	def __reduce__(self):   # pickle (job nền) dựng lại đúng (kind, message) thay vì chỉ args
		return (type(self), (self.kind, self.message))


def run_status(kind: str) -> str:
	"""LLMError.kind → BC AI Run.status."""
	return {"credit": "het-credit", "no_key": "khong-khoa"}.get(kind, "loi")


def has_key(provider: str) -> bool:
	"""Site có khai khoá của provider không (chỉ trả có / không)."""
	name = PROVIDERS.get(provider)
	return bool(name and str(frappe.conf.get(name) or "").strip())


# ─── Kiểm đầu ra theo schema (phần JSON Schema mà structured outputs nhận) ───────────────────────────────────
_TYPES = {
	"object": lambda v: isinstance(v, dict),
	"array": lambda v: isinstance(v, list),
	"string": lambda v: isinstance(v, str),
	"integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
	"number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
	"boolean": lambda v: isinstance(v, bool),
	"null": lambda v: v is None,
}


def schema_error(data, schema, path: str = "$"):
	"""Chỗ ĐẦU TIÊN `data` không khớp `schema` (vd "$.insights[0].severity") hoặc None nếu khớp. Hiểu: type (chuỗi /
	danh sách), enum, const, anyOf, properties, required, additionalProperties False, items. Từ khoá khác bỏ qua.
	Không bao giờ đưa GIÁ TRỊ vào kết quả (chỉ vị trí) — đầu ra mô hình không được lọt vào log."""
	if not isinstance(schema, dict):
		return None
	if isinstance(schema.get("anyOf"), list) and all(schema_error(data, s, path) for s in schema["anyOf"]):
		return path
	if "enum" in schema and not any(type(data) is type(x) and data == x for x in schema["enum"]):
		return path
	if "const" in schema and not (type(data) is type(schema["const"]) and data == schema["const"]):
		return path
	t = schema.get("type")
	if t is not None and not any(_TYPES.get(x, lambda v: True)(data) for x in (t if isinstance(t, list) else [t])):
		return path
	if isinstance(data, dict):
		props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
		for k in schema.get("required") or []:
			if k not in data:
				return f"{path}.{k}"
		if schema.get("additionalProperties") is False and any(k not in props for k in data):
			return f"{path} (khoá lạ)"
		for k, sub in props.items():
			if k in data:
				bad = schema_error(data[k], sub, f"{path}.{k}")
				if bad:
					return bad
	if isinstance(data, list) and isinstance(schema.get("items"), dict):
		for i, v in enumerate(data):
			bad = schema_error(v, schema["items"], f"{path}[{i}]")
			if bad:
				return bad
	return None


def _noi_loi(e: BaseException) -> str:
	"""' [file.py:dòng]' của khung trong cùng — đủ để lần ra lỗi lập trình khi vết lỗi đã bị bỏ."""
	tb = e.__traceback__
	while tb is not None and tb.tb_next is not None:
		tb = tb.tb_next
	return f" [{os.path.basename(tb.tb_frame.f_code.co_filename)}:{tb.tb_lineno}]" if tb is not None else ""


def _dispatch(provider: str, model: str, system: str, user: str, schema_name: str, schema: dict, max_tokens: int,
		timeout: int) -> dict:
	if provider not in PROVIDERS:
		raise LLMError("http", "nhà cung cấp mô hình không được hỗ trợ")
	if not has_key(provider):   # trước mọi lời gọi mạng
		raise LLMError("no_key", f"chưa khai {PROVIDERS[provider]} trong site_config")
	if provider != "claude":   # OpenAI (phản biện) là P2
		raise LLMError("http", "chưa hỗ trợ")
	if not str(model or "").strip():
		raise LLMError("http", "chưa chọn mô hình (ô model trong BC Settings đang trống)")
	from bc.ai.llm import anthropic   # nạp muộn: module này import LLMError từ đây
	out = anthropic.call(model, system, user, schema_name, schema, max_tokens=max_tokens, timeout=timeout)
	where = schema_error(out.get("data"), schema)
	if where:
		err = LLMError("schema", f"đầu ra của mô hình sai cấu trúc tại {where}")
		err.tokens_in, err.tokens_out = out.get("tokens_in") or 0, out.get("tokens_out") or 0
		err.model = out.get("model") or ""
		raise err
	return out


def call(provider: str, model: str, system: str, user: str, schema_name: str, schema: dict,
		max_tokens: int = 16000, timeout: int = 300) -> dict:
	"""Một lượt gọi → {"data": dict theo schema, "tokens_in": int, "tokens_out": int, "model": str (mô hình thực trả
	lời)}. Lỗi → LLMError(kind). Retry tối đa 2 lần (5 s / 20 s) chỉ cho 429 giới hạn tốc độ, 5xx, timeout; hết credit →
	kind "credit", KHÔNG retry."""
	err = None
	try:
		return _dispatch(provider, model, system, user, schema_name, schema, max_tokens, timeout)
	except LLMError as e:
		err = e
	except Exception as e:   # lỗi không lường (kể cả lỗi lập trình): vẫn là LLMError, lời đã làm sạch
		err = LLMError("http", f"lỗi không lường khi gọi mô hình{_noi_loi(e)}: {type(e).__name__}: {e}")
	# Ném NGOÀI khối except (không kéo theo ngoại lệ gốc), bỏ vết các khung bên trong và bỏ các biến mang đề bài: vết
	# lỗi KÈM BIẾN của Frappe (get_traceback(with_context=True) ở developer_mode) cũng không thấy khoá, đề bài, gói số.
	del system, user, schema
	raise err.with_traceback(None)
