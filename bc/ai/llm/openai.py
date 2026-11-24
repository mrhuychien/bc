# -*- coding: utf-8 -*-
"""bc.ai.llm.openai — OpenAI qua Responses API (phản biện, P2) bằng `requests` (không thêm dependency). Nơi duy nhất
gọi mạng tới OpenAI và đọc khoá bc_ai_openai_key. Chỉ gọi qua bc.ai.llm.call("openai", …).

Định dạng lấy từ tài liệu OpenAI hiện hành (developers.openai.com/api: reference responses/create, guides
structured-outputs, guides error-codes — đọc 11/2026), không code theo trí nhớ:
- POST https://api.openai.com/v1/responses; header Authorization: Bearer <khoá>, Content-Type: application/json.
- Thân: model, input = [{"role": "system", "content": …}, {"role": "user", "content": …}] (EasyInputMessage: content
  là chuỗi), max_output_tokens (tính cả token suy luận), store false (mặc định của API là true = OpenAI LƯU câu trả
  lời để lấy lại sau — đề bài mang số liệu kinh doanh, không để lưu), text.format = {"type": "json_schema", "name",
  "schema", "strict": true} (strict: mọi object additionalProperties false + mọi khoá trong required — nơi gọi lo).
  KHÔNG gửi temperature / top_p / reasoning / instructions / tools (mô hình suy luận từ chối tham số lấy mẫu; không gì
  tuỳ chọn mà tài liệu không bắt buộc).
- Trả lời: `status` (completed | incomplete | failed | …); `output[]` gồm mục type "reasoning" và mục type "message"
  có `content[]` là phần type "output_text" (`text`) hoặc "refusal" (`refusal`) — đọc theo type, không theo vị trí.
  Có phần refusal → LLMError("refusal"); status incomplete: incomplete_details.reason content_filter → refusal, còn lại
  (max_output_tokens …) → schema (JSON có thể dở); status khác completed → http.
- Token: usage.input_tokens (đã gồm phần đọc cache — input_tokens_details chỉ là bảng chia nhỏ), usage.output_tokens
  (đã gồm token suy luận). `model` trả về = model THỰC trả lời (có thể là tên bản chụp có hậu tố ngày).

Lỗi (LLMError.kind), thân lỗi {"error": {"message", "type", "param", "code"}}:
- credit (KHÔNG retry — tài liệu: thử lại lỗi tiền / trần chi / hạn mức không mở lại được): error.code ∈ CREDIT_CODES
  (credit_balance_exhausted, organization_spend_limit_exceeded, project_spend_limit_exceeded,
  organization_usage_limit_exceeded) hoặc error.type / error.code = insufficient_quota.
- rate: 429 khác (giới hạn tốc độ, slow_down), sau khi retry.   - http: 5xx (500, 503 server_is_overloaded …) sau khi
  retry; 4xx khác (400, 401, 403, 404, 413) không retry.   - timeout: quá thời gian / lỗi nối, sau khi retry.
Retry tối đa 2 lần, chờ 5 s rồi 20 s; header Retry-After (giây hoặc ngày HTTP) ngắn hơn 60 s thì chờ đúng theo nó.
`sleep` và `http_post` là tên cấp module để bộ thử thay.
"""

from __future__ import annotations

import email.utils
import json
import time

import frappe
import requests

from bc.ai.llm import PROVIDERS, LLMError, key_ok

URL = "https://api.openai.com/v1/responses"
RETRY_WAITS = (5, 20)     # giây chờ trước lần thử lại thứ 1, thứ 2
RETRY_AFTER_MAX = 60      # Retry-After ngắn hơn chừng này giây → chờ đúng theo nó; dài hơn → chờ theo RETRY_WAITS
CONNECT_TIMEOUT = 10      # giây chờ nối; chờ đọc = tham số timeout của call
CREDIT_CODES = frozenset({"credit_balance_exhausted", "organization_spend_limit_exceeded",
	"project_spend_limit_exceeded", "organization_usage_limit_exceeded", "insufficient_quota"})
_NET_ERRORS = (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
	requests.exceptions.ChunkedEncodingError)

sleep = time.sleep


def http_post(url: str, headers: dict, data: bytes, timeout):
	"""MỘT lượt POST. Bộ thử thay hàm này (hoặc cả tên `requests` của module) bằng bản giả — không test nào ra mạng.
	Không theo chuyển hướng: requests chép header tự đặt (Authorization) sang máy chủ được chuyển tới."""
	return requests.post(url, headers=headers, data=data, timeout=timeout, allow_redirects=False)


def _request(key: str, model: str, system: str, user: str, schema_name: str, schema: dict, max_tokens: int) -> tuple:
	"""(headers, thân JSON dạng bytes UTF-8) của một lượt gọi."""
	headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
	vao = [{"role": "system", "content": system}] if system else []
	vao.append({"role": "user", "content": user})
	body = {"model": model, "input": vao, "max_output_tokens": int(max_tokens), "store": False,
		"text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}}
	return headers, json.dumps(body, ensure_ascii=False).encode("utf-8", "replace")


def _header(r, name: str):
	"""Giá trị header (không phân biệt hoa thường) của trả lời, hoặc None."""
	h = getattr(r, "headers", None)
	if not h:
		return None
	try:
		for k, v in h.items():
			if str(k).lower() == name:
				return v
	except Exception:
		return None
	return None


def _send(headers: dict, data: bytes, timeout) -> tuple:
	"""Một lượt gửi → (status, thân dict | None, chữ, Retry-After thô | None). status 0: quá thời gian / lỗi nối (thử
	lại được); -1: lỗi gửi khác (không thử lại) — chỉ ghi TÊN loại ngoại lệ (lời của nó có thể chép nguyên header mang
	khoá). Chữ của lỗi mạng có thể chứa khoá — chỉ đi tiếp vào LLMError (tự làm sạch)."""
	try:
		r = http_post(URL, headers, data, (CONNECT_TIMEOUT, timeout))
		status, text = int(r.status_code), str(r.text or "")
		ra = _header(r, "retry-after")
	except _NET_ERRORS as e:
		return 0, None, f"{type(e).__name__}: {e}", None
	except Exception as e:
		return -1, None, type(e).__name__, None
	try:
		body = json.loads(text)
	except ValueError:
		body = None
	return status, body if isinstance(body, dict) else None, text, ra


def retry_after(value, now: float | None = None):
	"""Retry-After (số giây, hoặc ngày HTTP) → số giây chờ (float ≥ 0) hoặc None khi không đọc được."""
	if value is None:
		return None
	s = str(value).strip()
	try:
		n = float(s)
		return n if n >= 0 and n == n and n != float("inf") else None
	except ValueError:
		pass
	try:
		d = email.utils.parsedate_to_datetime(s)
	except (TypeError, ValueError, IndexError):
		return None
	if d is None or d.tzinfo is None:
		return None
	return max(0.0, d.timestamp() - (time.time() if now is None else now))


def _classify(status: int, body, text: str) -> tuple:
	"""Lượt hỏng → (kind, thử_lại_được, message)."""
	if status == 0:
		return "timeout", True, f"không nối được máy chủ OpenAI hoặc quá thời gian chờ ({text})"
	if status < 0:
		return "http", False, f"không gửi được yêu cầu ({text})"
	err = (body or {}).get("error")
	err = err if isinstance(err, dict) else {}
	etype, ecode = str(err.get("type") or ""), str(err.get("code") or "")
	emsg = str(err.get("message") or "")
	nhan = " ".join(x for x in (etype, f"({ecode})" if ecode else "") if x)
	msg = f"HTTP {status} {nhan}: {emsg}" if (nhan or emsg) else f"HTTP {status}: {text[:200]}"
	if 400 <= status < 500 and (ecode in CREDIT_CODES or etype == "insufficient_quota"):
		return "credit", False, msg
	if status == 429:
		return "rate", True, msg
	if status >= 500:
		return "http", True, msg
	return "http", False, msg


def _n(v) -> int:
	return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _usage(usage) -> tuple:
	"""(token vào, token ra) của lượt gọi: usage.input_tokens / usage.output_tokens (thiếu / sai kiểu → 0)."""
	usage = usage if isinstance(usage, dict) else {}
	return _n(usage.get("input_tokens")), _n(usage.get("output_tokens"))


def _fail(kind: str, message: str, body: dict, model: str) -> LLMError:
	"""LLMError của một lượt máy chủ ĐÃ trả lời (đã tính tiền): mang theo token + model để nơi gọi ghi chi phí."""
	err = LLMError(kind, message)
	err.tokens_in, err.tokens_out = _usage(body.get("usage"))
	err.model = str(body.get("model") or model)
	return err


def _parts(body: dict) -> list:
	"""Mọi phần content của các mục output type "message", theo thứ tự."""
	out = []
	for item in body.get("output") if isinstance(body.get("output"), list) else []:
		if isinstance(item, dict) and item.get("type") == "message" and isinstance(item.get("content"), list):
			out += [p for p in item["content"] if isinstance(p, dict)]
	return out


def _parse(body: dict, model: str) -> dict:
	"""Thân trả lời 200 → dict kết quả; từ chối / dở / không phải JSON → ném LLMError (không chép lời mô hình)."""
	status = body.get("status")
	parts = _parts(body)
	if any(p.get("type") == "refusal" for p in parts):   # xét TRƯỚC khi đọc chữ (có thể đi kèm chữ dở)
		raise _fail("refusal", "mô hình từ chối trả lời", body, model)
	if status == "incomplete":
		det = body.get("incomplete_details") if isinstance(body.get("incomplete_details"), dict) else {}
		why = str(det.get("reason") or "")[:40]
		if why == "content_filter":
			raise _fail("refusal", "đầu ra bị bộ lọc nội dung chặn", body, model)
		raise _fail("schema", "đầu ra dở dang" + (f" ({why})" if why else ""), body, model)
	if status != "completed":
		err = body.get("error") if isinstance(body.get("error"), dict) else {}
		ma = str(err.get("code") or "")
		raise _fail("http", f"lượt trả lời không hoàn tất (status {str(status)[:30]}"
			+ (f", {ma[:60]}" if ma else "") + ")", body, model)
	text = next((p.get("text") for p in parts if p.get("type") == "output_text"), None)
	if not isinstance(text, str) or not text.strip():
		raise _fail("schema", "trả lời không có phần output_text", body, model)
	try:
		data = json.loads(text)
	except ValueError:
		data = None
	if not isinstance(data, dict):
		raise _fail("schema", "đầu ra của mô hình không phải JSON hợp lệ", body, model)
	vao, ra = _usage(body.get("usage"))
	return {"data": data, "tokens_in": vao, "tokens_out": ra, "model": str(body.get("model") or model)}


def call(model: str, system: str, user: str, schema_name: str, schema: dict, max_tokens: int = 16000,
		timeout: int = 300) -> dict:
	"""Một lượt gọi OpenAI → {"data": dict theo schema, "tokens_in": int, "tokens_out": int, "model": str (mô hình thực
	trả lời)} — cùng dạng anthropic.call. schema_name = tên của json_schema (vd "phan_bien"; a-z, A-Z, 0-9, _ -, ≤ 64).
	Lỗi → LLMError(kind)."""
	key = str(frappe.conf.get(PROVIDERS["openai"]) or "").strip()   # chỉ sống trong hàm này
	if not key:
		raise LLMError("no_key", f"chưa khai {PROVIDERS['openai']} trong site_config")
	if not key_ok(key):   # dấu cách / xuống dòng ở giữa: thư viện HTTP sẽ chép khoá vào lời lỗi — không gửi
		raise LLMError("no_key", f"{PROVIDERS['openai']} khai sai dạng (có dấu cách / xuống dòng / ký tự lạ)")
	headers, data = _request(key, model, system, user, schema_name, schema, max_tokens)
	waits = list(RETRY_WAITS)
	lan = 0
	while True:
		status, body, text, ra = _send(headers, data, timeout)
		lan += 1
		if status == 200:
			if body is None:
				raise LLMError("http", "máy chủ trả 200 nhưng thân không phải JSON")
			return _parse(body, model)
		kind, retry, msg = _classify(status, body, text)
		if retry and waits:
			cho = waits.pop(0)
			s = retry_after(ra)
			sleep(s if s is not None and s < RETRY_AFTER_MAX else cho)
			continue
		raise LLMError(kind, msg + (f" (đã thử {lan} lần)" if lan > 1 else ""))
