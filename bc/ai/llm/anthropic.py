# -*- coding: utf-8 -*-
"""bc.ai.llm.anthropic — Claude qua Messages API bằng `requests` (không thêm dependency). Nơi DUY NHẤT gọi mạng và
đọc khoá bc_ai_anthropic_key. Chỉ gọi qua bc.ai.llm.call.

Định dạng lấy từ tài liệu Claude API (bản 2026-10-21), không code theo trí nhớ:
- POST https://api.anthropic.com/v1/messages; header x-api-key, anthropic-version, content-type.
- Ép đầu ra bằng STRUCTURED OUTPUTS: output_config.format = {"type": "json_schema", "schema": …}. KHÔNG gửi
  tool_choice (model mặc định trả 400 với tool_choice tool / any), KHÔNG gửi thinking (luôn bật, điều chỉnh bằng
  output_config.effort), KHÔNG gửi temperature / top_p / top_k (bản API này trả 400).
- Thinking tính vào max_tokens → mặc định 16000; một lượt có thể chạy vài phút → timeout đọc 300 s.
- Trả lời: JSON nằm ở khối type == "text" ĐẦU TIÊN của content (trước nó có thể là khối thinking / fallback) — đọc
  theo type, không theo vị trí. stop_reason "refusal" (HTTP 200, content rỗng hoặc dở) → LLMError("refusal");
  "max_tokens" (đầu ra bị cắt, JSON dở) → LLMError("schema").
- Model trong FALLBACK_MODELS: gửi thêm "fallbacks": "default" + header anthropic-beta — máy chủ tự chạy lại lượt bị
  bộ phân loại an toàn từ chối trên mô hình khác. Tổ chức chưa được bật beta này → 400 có nhắc anthropic-beta /
  fallbacks → gọi lại MỘT lần không kèm hai thứ đó (không tính vào số lần retry).
- Token: usage.iterations (mỗi lượt thử một mục — nguồn đúng khi có fallback) nếu có, không thì usage cấp trên; token
  vào gồm cả cache_creation_input_tokens + cache_read_input_tokens. `model` trả về = model THỰC trả lời.

Lỗi (LLMError.kind):
- credit (KHÔNG retry): 402 / billing_error; 429 có error.details.error_code = enforced_spend_limit_reached (chạm trần
  chi tháng — retry vô ích); 4xx có "credit balance" trong message.
- rate: 429 khác, sau khi retry.   - http: 5xx / 529 sau khi retry; 4xx khác (401, 403, 404, 400, 413) không retry.
- timeout: quá thời gian / lỗi nối, sau khi retry.
Retry tối đa 2 lần, chờ 5 s rồi 20 s. `sleep` và `http_post` là tên cấp module để bộ thử thay.

chat() (P3, hỏi đáp — vòng tool use thủ công của Messages API; cùng khoá, cùng _send / _classify / retry / fallback):
- Thân: model, max_tokens, messages (NGUYÊN như nơi gọi đưa: khối của lượt trước — thinking, tool_use, fallback… — gửi
  lại không sửa một byte nào của nội dung; kết quả công cụ nằm trong MỘT tin user gồm các khối tool_result), tools
  ({name, description, input_schema}), system, cache_control {"type": "ephemeral"} ở CẤP TRÊN (cache tự đặt ở khối
  cuối, dời theo hội thoại), output_config.effort như call (giữ cố định: đổi effort làm mất cache), tool_choice chỉ
  {"type": "none"} (lượt cuối buộc trả lời; "any" / "tool" bị 400 trên model mới; None = auto, không gửi trường).
  Không thinking, không tham số lấy mẫu, không output_config.format.
- Trả lời: content trả NGUYÊN (không lọc, không chép lại), stop_reason trả nguyên (end_turn / tool_use / max_tokens /
  pause_turn / …) — chỉ "refusal" thành LLMError("refusal") (cả chuỗi fallback đều từ chối; fallback đã trả lời thì
  stop_reason khác refusal, model = model thực trả lời, khối fallback nằm trong content để gửi lại đúng chỗ).
- Token: tokens_in = vào + ghi cache + đọc cache; cost_tokens_in = vào + 1,25 × ghi cache + 0,1 × đọc cache (giá ghi
  cache 5 phút / đọc cache theo tài liệu prompt caching) — cùng nguồn usage.iterations / usage cấp trên như call.
"""

from __future__ import annotations

import json
import time

import frappe
import requests

from bc.ai.llm import PROVIDERS, LLMError, key_ok

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2026-10-21"
BETA_FALLBACK = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset({"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5",
	"claude-sonnet-5-5"})
EFFORT = "medium"
RETRY_WAITS = (5, 20)     # giây chờ trước lần thử lại thứ 1, thứ 2
CONNECT_TIMEOUT = 10      # giây chờ nối; chờ đọc = tham số timeout của call
SPEND_LIMIT = "enforced_spend_limit_reached"
# Lỗi mạng thử lại được (bắt bằng lớp thật của requests, lấy lúc import — bản giả của bộ thử chỉ cần có .post).
_NET_ERRORS = (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
	requests.exceptions.ChunkedEncodingError)

sleep = time.sleep


def http_post(url: str, headers: dict, data: bytes, timeout):
	"""MỘT lượt POST. Bộ thử thay hàm này (hoặc cả tên `requests` của module) bằng bản giả — không test nào ra mạng.
	Không theo chuyển hướng: requests chép header tự đặt (x-api-key) sang máy chủ được chuyển tới."""
	return requests.post(url, headers=headers, data=data, timeout=timeout, allow_redirects=False)


def _request(key: str, model: str, system: str, user: str, schema: dict, max_tokens: int, fallback: bool) -> tuple:
	"""(headers, thân JSON dạng bytes UTF-8) của một lượt gọi."""
	headers = {"x-api-key": key, "anthropic-version": VERSION, "content-type": "application/json"}
	body = {"model": model, "max_tokens": int(max_tokens), "messages": [{"role": "user", "content": user}],
		"output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}}}
	if system:
		body["system"] = system
	if fallback:
		headers["anthropic-beta"] = BETA_FALLBACK
		body["fallbacks"] = "default"
	return headers, json.dumps(body, ensure_ascii=False).encode("utf-8", "replace")


def _send(headers: dict, data: bytes, timeout) -> tuple:
	"""Một lượt gửi → (status, thân dict | None, chữ). status 0: quá thời gian / lỗi nối (thử lại được); -1: lỗi gửi
	khác (không thử lại) — chỉ ghi TÊN loại ngoại lệ (lời của nó có thể chép nguyên header mang khoá). Chữ của lỗi mạng
	có thể chứa khoá — chỉ đi tiếp vào LLMError (tự làm sạch)."""
	try:
		r = http_post(URL, headers, data, (CONNECT_TIMEOUT, timeout))
		status, text = int(r.status_code), str(r.text or "")
	except _NET_ERRORS as e:
		return 0, None, f"{type(e).__name__}: {e}"
	except Exception as e:
		return -1, None, type(e).__name__
	try:
		body = json.loads(text)
	except ValueError:
		body = None
	return status, body if isinstance(body, dict) else None, text


def _classify(status: int, body, text: str) -> tuple:
	"""Lượt hỏng → (kind, thử_lại_được, message)."""
	if status == 0:
		return "timeout", True, f"không nối được máy chủ Anthropic hoặc quá thời gian chờ ({text})"
	if status < 0:
		return "http", False, f"không gửi được yêu cầu ({text})"
	err = (body or {}).get("error")
	err = err if isinstance(err, dict) else {}
	etype, emsg = str(err.get("type") or ""), str(err.get("message") or "")
	details = err.get("details") if isinstance(err.get("details"), dict) else {}
	msg = f"HTTP {status} {etype}: {emsg}" if (etype or emsg) else f"HTTP {status}: {text[:200]}"
	if (status == 402 or etype == "billing_error" or (status == 429 and details.get("error_code") == SPEND_LIMIT)
			or (400 <= status < 500 and "credit balance" in emsg.lower())):
		return "credit", False, msg
	if status == 429:
		return "rate", True, msg
	if status >= 500:
		return "http", True, msg
	return "http", False, msg


def _n(v) -> int:
	return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


_USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
CACHE_WRITE = 1.25   # giá ghi cache (TTL 5 phút) so với token vào thường
CACHE_READ = 0.1     # giá đọc cache so với token vào thường


def _tokens(rows: list) -> tuple:
	"""(vào thường, ghi cache, đọc cache, ra) cộng qua các dòng usage."""
	return tuple(sum(_n(r.get(f)) for r in rows) for f in _USAGE_FIELDS)


def _usage_parts(usage) -> tuple:
	"""(vào thường, ghi cache, đọc cache, ra) của CẢ lượt gọi: cộng mọi mục usage.iterations nếu có, không thì usage cấp
	trên. Các mục iterations không mang số token nào (tài liệu chỉ tả trường `type`) → dùng usage cấp trên, không báo 0."""
	usage = usage if isinstance(usage, dict) else {}
	its = usage.get("iterations")
	rows = [r for r in its if isinstance(r, dict)] if isinstance(its, list) else []
	tong = _tokens(rows)
	return tong if any(tong) else _tokens([usage])


def _usage(usage) -> tuple:
	"""(token vào gồm cả ghi + đọc cache, token ra) của cả lượt gọi."""
	vao, ghi, doc, ra = _usage_parts(usage)
	return vao + ghi + doc, ra


def _cost_in(usage) -> float:
	"""Token vào quy theo giá token thường: vào + 1,25 × ghi cache + 0,1 × đọc cache (trần chi tính trên số này)."""
	vao, ghi, doc, _ra = _usage_parts(usage)
	return float(vao + CACHE_WRITE * ghi + CACHE_READ * doc)


def _fail(kind: str, message: str, body: dict, model: str) -> LLMError:
	"""LLMError của một lượt máy chủ ĐÃ trả lời (đã tính tiền): mang theo token + model để nơi gọi ghi chi phí."""
	err = LLMError(kind, message)
	err.tokens_in, err.tokens_out = _usage(body.get("usage"))
	err.cost_tokens_in = _cost_in(body.get("usage"))
	err.model = str(body.get("model") or model)
	return err


def _parse(body: dict, model: str) -> dict:
	"""Thân trả lời 200 → dict kết quả; từ chối / bị cắt / không phải JSON → ném LLMError."""
	stop = body.get("stop_reason")
	if stop == "refusal":   # xét TRƯỚC khi đọc content (rỗng hoặc dở)
		cat = (body.get("stop_details") or {}).get("category") if isinstance(body.get("stop_details"), dict) else None
		raise _fail("refusal", "mô hình từ chối trả lời" + (f" (loại: {cat})" if isinstance(cat, str) else ""),
			body, model)
	if stop == "max_tokens":
		raise _fail("schema", "đầu ra bị cắt vì chạm max_tokens", body, model)
	content = body.get("content") if isinstance(body.get("content"), list) else []
	text = next((b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"), None)
	if not isinstance(text, str) or not text.strip():
		raise _fail("schema", "trả lời không có khối văn bản", body, model)
	try:
		data = json.loads(text)
	except ValueError:
		data = None
	if not isinstance(data, dict):   # không chép đầu ra của mô hình vào message
		raise _fail("schema", "đầu ra của mô hình không phải JSON hợp lệ", body, model)
	vao, ra = _usage(body.get("usage"))
	return {"data": data, "tokens_in": vao, "tokens_out": ra, "model": str(body.get("model") or model)}


def _nhac_fallback(message: str) -> bool:
	low = message.lower()
	return "anthropic-beta" in low or "fallbacks" in low


def _key() -> str:
	"""Khoá Claude đã gọt — chỉ sống trong khung hàm gọi; chưa khai / khai sai dạng → LLMError no_key (trước mọi lời gọi
	mạng: khoá có dấu cách / xuống dòng ở giữa thì thư viện HTTP sẽ chép nguyên khoá vào lời lỗi)."""
	key = str(frappe.conf.get(PROVIDERS["claude"]) or "").strip()
	if not key:
		raise LLMError("no_key", f"chưa khai {PROVIDERS['claude']} trong site_config")
	if not key_ok(key):
		raise LLMError("no_key", f"{PROVIDERS['claude']} khai sai dạng (có dấu cách / xuống dòng / ký tự lạ)")
	return key


def _post(key: str, model: str, timeout, build) -> dict:
	"""Vòng gửi chung của call / chat: build(key, fallback) → (headers, data). Trả thân dict của lượt 200; lỗi → LLMError
	theo _classify, retry 5 s / 20 s cho 429 / 5xx / quá giờ, gọi lại một lần không kèm fallback khi tổ chức chưa có
	beta đó (lần này không tính vào retry)."""
	fallback = model in FALLBACK_MODELS
	waits = list(RETRY_WAITS)
	lan = 0
	while True:
		headers, data = build(key, fallback)
		status, body, text = _send(headers, data, timeout)
		lan += 1
		if status == 200:
			if body is None:
				raise LLMError("http", "máy chủ trả 200 nhưng thân không phải JSON")
			return body
		kind, retry, msg = _classify(status, body, text)
		if fallback and status == 400 and kind == "http" and _nhac_fallback(msg):
			fallback = False   # tổ chức chưa có beta fallback: gọi lại một lần không kèm header + trường đó
			continue
		if retry and waits:
			sleep(waits.pop(0))
			continue
		raise LLMError(kind, msg + (f" (đã thử {lan} lần)" if lan > 1 else ""))


def call(model: str, system: str, user: str, schema_name: str, schema: dict, max_tokens: int = 16000,
		timeout: int = 300) -> dict:
	"""Một lượt gọi Claude (xem bc.ai.llm.call). `schema_name` không dùng — Messages API không đặt tên schema."""
	body = _post(_key(), model, timeout,
		lambda k, fb: _request(k, model, system, user, schema, max_tokens, fb))
	return _parse(body, model)


# ─── chat: một lượt gọi CÓ công cụ (P3 hỏi đáp) ─────────────────────────────────────────────────────────────────
TOOL_CHOICE_NONE = {"type": "none"}


def _chat_args_error(messages, tools, tool_choice):
	"""Lời báo (không chép nội dung) khi tham số của chat sai dạng, None nếu đúng. tool_choice chỉ None hoặc đúng
	{"type": "none"} — "any" / "tool" bị 400 trên model mới, "auto" là mặc định nên không gửi."""
	if tool_choice is not None and tool_choice != TOOL_CHOICE_NONE:
		return 'tool_choice chỉ nhận None hoặc {"type": "none"}'
	if not isinstance(messages, list) or not messages:
		return "messages phải là danh sách khác rỗng"
	for i, m in enumerate(messages):
		if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") \
				or not isinstance(m.get("content"), (str, list)):
			return f"messages[{i}] sai dạng (role user / assistant, content chuỗi hoặc danh sách khối)"
	if messages[0].get("role") != "user":
		return "messages phải bắt đầu bằng tin user"
	if not isinstance(tools, list) or not all(isinstance(t, dict) and isinstance(t.get("name"), str)
			and isinstance(t.get("input_schema"), dict) for t in tools):
		return "tools phải là danh sách {name, description, input_schema}"
	return None


def _chat_request(key: str, model: str, system: str, messages: list, tools: list, max_tokens: int, tool_choice,
		fallback: bool) -> tuple:
	"""(headers, thân bytes UTF-8) của một lượt chat. messages / tools đi NGUYÊN (json.dumps không sửa đối tượng)."""
	headers = {"x-api-key": key, "anthropic-version": VERSION, "content-type": "application/json"}
	body = {"model": model, "max_tokens": int(max_tokens), "messages": messages,
		"cache_control": {"type": "ephemeral"}, "output_config": {"effort": EFFORT}}
	if system:
		body["system"] = system
	if tools:
		body["tools"] = tools
		if tool_choice is not None:
			body["tool_choice"] = tool_choice
	if fallback:
		headers["anthropic-beta"] = BETA_FALLBACK
		body["fallbacks"] = "default"
	return headers, json.dumps(body, ensure_ascii=False).encode("utf-8", "replace")


def _chat_parse(body: dict, model: str) -> dict:
	"""Thân trả lời 200 → kết quả chat; từ chối / thân sai dạng → ném LLMError (mang token đã tính tiền)."""
	stop = body.get("stop_reason")
	if stop == "refusal":   # xét TRƯỚC content (rỗng hoặc dở; tool_use dở không được chạy)
		cat = (body.get("stop_details") or {}).get("category") if isinstance(body.get("stop_details"), dict) else None
		raise _fail("refusal", "mô hình từ chối trả lời" + (f" (loại: {cat})" if isinstance(cat, str) else ""),
			body, model)
	content = body.get("content")
	if not isinstance(content, list) or not all(isinstance(b, dict) for b in content):
		raise _fail("schema", "trả lời không có danh sách khối content", body, model)
	if not isinstance(stop, str) or not stop:
		raise _fail("schema", "trả lời thiếu stop_reason", body, model)
	vao, ra = _usage(body.get("usage"))
	return {"content": content, "stop_reason": stop, "tokens_in": vao, "tokens_out": ra,
		"cost_tokens_in": _cost_in(body.get("usage")), "model": str(body.get("model") or model)}


def chat(model: str, system: str, messages: list, tools: list, max_tokens: int = 2000, timeout: int = 60,
		tool_choice=None) -> dict:
	"""Một lượt gọi Claude có công cụ (xem bc.ai.llm.chat). Tham số sai dạng → LLMError http, không gọi mạng."""
	loi = _chat_args_error(messages, tools, tool_choice)
	if loi:
		raise LLMError("http", loi)
	body = _post(_key(), model, timeout,
		lambda k, fb: _chat_request(k, model, system, messages, tools, max_tokens, tool_choice, fb))
	return _chat_parse(body, model)
