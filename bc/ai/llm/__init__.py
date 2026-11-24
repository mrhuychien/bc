# -*- coding: utf-8 -*-
"""bc.ai.llm — CỬA DUY NHẤT ra mô hình ngôn ngữ (đặc tả §5.1). Chỉ package này import `requests` và đọc khoá
`bc_ai_*_key` trong site_config (bộ thử AST chặn nơi khác).

Luật khoá: đọc bằng frappe.conf.get(...) NGAY TRONG hàm cần dùng; không gán biến module, không nằm trong dict trả về,
không nằm trong message lỗi / log. Mọi LLMError tự làm sạch message lúc tạo (clean): xoá mọi chuỗi trùng khoá đang
khai (cả dạng repr và từng mảnh dài của khoá khai sai có dấu cách / xuống dòng) + mọi chuỗi có dạng khoá Anthropic / OpenAI
(tiền tố s, k, gạch ngang — cả dạng …-proj-…, …-svcacct-…), RỒI mới cắt 300 ký tự (cắt trước thì nửa khoá nằm ở mép sẽ lọt). Lỗi ra khỏi
call() được ném NGOÀI khối except (không kéo theo ngoại lệ gốc — lời của thư viện HTTP có thể chứa khoá), vết lỗi
chỉ còn khung của call() và khung đó đã bỏ các biến mang đề bài / gói số.
Module khác cần lưu / ghi log một chuỗi lỗi bất kỳ của bước AI: đưa qua clean() trước.

Đầu ra mô hình được kiểm lại theo schema ở đây (schema_error) dù nhà cung cấp đã ép cấu trúc — sai → kind "schema".
Bộ thử thay `bc.ai.llm.call` / `bc.ai.llm.chat` bằng bản giả — không test nào được ra mạng.
"""

from __future__ import annotations

import os
import re

import frappe

PROVIDERS = {"claude": "bc_ai_anthropic_key", "openai": "bc_ai_openai_key"}   # provider → khoá trong site_config
KINDS = ("no_key", "credit", "rate", "http", "timeout", "schema", "refusal")
MAX_MESSAGE = 300
MASK = "***"
# Mọi thứ trông như khoá API (khoá cũ, khoá của site khác, khoá bị cắt cụt) — không bắt nhầm chữ thường có cùng hai
# chữ cái đứng trước gạch ngang ở giữa từ (task…, risk…). Viết [k] để gói phần mềm không chứa nguyên chuỗi tiền tố.
_KEY_LIKE = re.compile(r"(?<![A-Za-z0-9])s[k]-[A-Za-z0-9_\-]{8,}")
MIN_FRAGMENT = 6   # mảnh của khoá khai sai (tách theo khoảng trắng) dài từ chừng này trở lên cũng bị xoá


def key_ok(key) -> bool:
	"""Khoá (đã gọt hai đầu) khác rỗng và chỉ gồm ký tự in được 0x21–0x7E — có dấu cách / xuống dòng / ký tự lạ ở
	giữa → coi như chưa khai (thư viện HTTP sẽ ném lỗi chép nguyên khoá)."""
	k = str(key or "").strip()
	return bool(k) and all(0x21 <= ord(ch) <= 0x7E for ch in k)


def _key_forms(k: str) -> list:
	"""Mọi dạng của khoá có thể nằm trong lời lỗi, dài trước ngắn sau: nguyên văn, đã gọt, dạng repr (xuống dòng thành
	hai ký tự \\n), rồi từng mảnh ≥ MIN_FRAGMENT ký tự tách theo khoảng trắng."""
	if not k:
		return []
	forms = {k, k.strip(), repr(k)[1:-1], repr(k.strip())[1:-1]}
	forms |= {m for m in k.split() if len(m) >= MIN_FRAGMENT}
	forms |= {repr(m)[1:-1] for m in k.split() if len(m) >= MIN_FRAGMENT}
	return sorted((f for f in forms if f), key=len, reverse=True)


def clean(text) -> str:
	"""Chuỗi an toàn để lưu vào BC AI Run.error / ghi log: đã xoá mọi chuỗi trùng khoá API đang khai (và mọi chuỗi có
	dạng khoá), cắt MAX_MESSAGE ký tự."""
	s = "" if text is None else str(text)
	for name in PROVIDERS.values():
		try:
			k = str(frappe.conf.get(name) or "")
		except Exception:   # ngoài ngữ cảnh site (không có conf): vẫn còn lớp xoá theo mẫu ở dưới
			k = ""
		for v in _key_forms(k):   # khoá khai thừa / lẫn dấu cách, xuống dòng: xoá mọi dạng
			s = s.replace(v, MASK)
	return _KEY_LIKE.sub(MASK, s)[:MAX_MESSAGE]


class LLMError(Exception):
	"""Lỗi gọi mô hình. kind ∈ KINDS; message ≤ 300 ký tự, ĐÃ xoá mọi chuỗi trùng khoá.

	tokens_in / tokens_out / cost_tokens_in / model: số token ĐÃ BỊ TÍNH TIỀN của lượt hỏng khi máy chủ có trả lời (từ chối, đầu ra bị
	cắt, sai cấu trúc) — nơi gọi nên ghi vào Run để trần chi không đếm thiếu; lỗi HTTP / mạng thì 0."""

	def __init__(self, kind: str, message: str = ""):
		message = clean(message)
		super().__init__(message)
		self.kind = kind
		self.message = message
		self.tokens_in = 0
		self.tokens_out = 0
		self.cost_tokens_in = 0.0   # token vào quy theo giá thường (ghi cache × 1,25, đọc cache × 0,1) — xem chat()
		self.model = ""

	def __reduce__(self):   # pickle (job nền) dựng lại đúng (kind, message) thay vì chỉ args
		return (type(self), (self.kind, self.message))


def run_status(kind: str) -> str:
	"""LLMError.kind → BC AI Run.status."""
	return {"credit": "het-credit", "no_key": "khong-khoa"}.get(kind, "loi")


def has_key(provider: str) -> bool:
	"""Site có khai khoá DÙNG ĐƯỢC của provider không (chỉ trả có / không). Khoá có ký tự ngoài 0x21–0x7E sau khi gọt
	hai đầu (dán bị xuống dòng, có dấu cách ở giữa) → False: lượt chạy báo khong-khoa."""
	name = PROVIDERS.get(provider)
	return bool(name and key_ok(frappe.conf.get(name)))


def key_malformed(provider: str) -> bool:
	"""Site CÓ khai khoá của provider nhưng sai dạng (dấu cách / xuống dòng / ký tự lạ ở giữa) — để màn quản trị nói
	rõ lý do thay vì "chưa có khoá". Chỉ trả có / không."""
	name = PROVIDERS.get(provider)
	k = str(frappe.conf.get(name) or "").strip() if name else ""
	return bool(k) and not key_ok(k)


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
		if str(frappe.conf.get(PROVIDERS[provider]) or "").strip():
			raise LLMError("no_key", f"{PROVIDERS[provider]} khai sai dạng (có dấu cách / xuống dòng / ký tự lạ)")
		raise LLMError("no_key", f"chưa khai {PROVIDERS[provider]} trong site_config")
	if not str(model or "").strip():
		raise LLMError("http", "chưa chọn mô hình (ô model trong BC Settings đang trống)")
	# nạp muộn: hai adapter import LLMError từ đây. claude → Messages API; openai (phản biện, P2) → Responses API.
	if provider == "claude":
		from bc.ai.llm import anthropic as adapter
	else:
		from bc.ai.llm import openai as adapter
	out = adapter.call(model, system, user, schema_name, schema, max_tokens=max_tokens, timeout=timeout)
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


def _dispatch_chat(provider: str, model: str, system: str, messages: list, tools: list, max_tokens: int, timeout: int,
		tool_choice, retries=None) -> dict:
	if provider != "claude":   # hỏi đáp chỉ chạy trên Claude (đặc tả P3 §0) — không gọi mạng
		raise LLMError("http", "hỏi đáp chỉ hỗ trợ nhà cung cấp claude")
	if not has_key(provider):   # trước mọi lời gọi mạng
		if str(frappe.conf.get(PROVIDERS[provider]) or "").strip():
			raise LLMError("no_key", f"{PROVIDERS[provider]} khai sai dạng (có dấu cách / xuống dòng / ký tự lạ)")
		raise LLMError("no_key", f"chưa khai {PROVIDERS[provider]} trong site_config")
	if not str(model or "").strip():
		raise LLMError("http", "chưa chọn mô hình (ô model trong BC Settings đang trống)")
	from bc.ai.llm import anthropic as adapter
	return adapter.chat(model, system, messages, tools, max_tokens=max_tokens, timeout=timeout, tool_choice=tool_choice,
		retries=retries)


def chat(provider: str, model: str, system: str, messages: list, tools: list, max_tokens: int = 2000,
		timeout: int = 60, tool_choice=None, retries=None) -> dict:
	"""Một lượt gọi Messages API CÓ công cụ (P3 hỏi đáp). provider phải là "claude".

	messages: [{"role": "user" | "assistant", "content": chuỗi | [khối]}] — content của lượt assistant trước gửi lại
	NGUYÊN như đã nhận (mọi khối, kể cả thinking / fallback, không sửa); kết quả công cụ: MỘT tin user gồm các khối
	tool_result. tools: [{"name", "description", "input_schema"}]; tool_choice: None (auto) hoặc {"type": "none"}.
	→ {"content": [khối nguyên như API trả], "stop_reason": "end_turn" | "tool_use" | "max_tokens" | …, "tokens_in",
	"tokens_out", "cost_tokens_in", "model"}; tokens_in = vào + ghi cache + đọc cache, cost_tokens_in = vào + 1,25 × ghi
	+ 0,1 × đọc. Lỗi → LLMError (kind như call; "refusal" khi cả chuỗi fallback từ chối — mang token đã tính tiền); cùng
	luật khoá, cùng retry (5 s / 20 s cho 429 / 5xx / quá giờ; hết credit không retry). retries: số lần thử lại tối
	đa (None = như call; 0 = không thử lại — hỏi đáp dùng 0 để mỗi lượt gọi có đủ thời gian trong hạn của câu)."""
	err = None
	try:
		return _dispatch_chat(provider, model, system, messages, tools, max_tokens, timeout, tool_choice, retries)
	except LLMError as e:
		err = e
	except Exception as e:   # lỗi không lường: chỉ TÊN loại + nơi lỗi — lời của nó có thể chép câu hỏi / kết quả công cụ
		err = LLMError("http", f"lỗi không lường khi gọi mô hình{_noi_loi(e)}: {type(e).__name__}")
	# Như call: ném ngoài except, bỏ vết bên trong và bỏ biến mang đề bài / câu hỏi / kết quả công cụ.
	del system, messages, tools
	raise err.with_traceback(None)
