"""Trợ lý AI P3 — llm.chat: một lượt Messages API CÓ công cụ (bc.ai.llm.chat + bc.ai.llm.anthropic.chat).

KHÔNG RA MẠNG: chặn ở tầng socket (mọi lời nối không phải socket unix, mọi lượt tra DNS đều ném lỗi) + tên `requests`
của adapter thay bằng bản giả chạy theo kịch bản (hết kịch bản mà còn bị gọi → ném lỗi và đếm). Không cần bảng nào:
chỉ dùng frappe.conf giả.

Định dạng đối chiếu với tài liệu Claude API bản 2026-10-21 (curl/examples.md: Tool Use, Required Headers;
shared/tool-use-concepts.md: định nghĩa công cụ, tool_choice — "any" / "tool" bị 400 trên model mới, "auto" / "none"
vẫn dùng được; vòng thủ công: gửi lại NGUYÊN response.content, mọi tool_result trong MỘT tin user, is_error;
shared/prompt-caching.md: cache_control cấp trên, usage.cache_creation_input_tokens / cache_read_input_tokens, giá ghi
1,25× / đọc 0,1×; shared/model-migration.md: stop_reason refusal xét trước content, fallbacks "default" + header beta,
khối fallback, usage.iterations, thinking gửi lại không sửa; shared/error-codes.md). Số kỳ vọng tính tay.
"""
import copy
import json
import os
import socket
import traceback

# ─── Lớp chặn 1: socket (đặt TRƯỚC mọi import có thể nối mạng) ───────────────────────────────────────────────
BLOCKED: list = []
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo


def _cam_noi(self, address, *a):
	if self.family != socket.AF_UNIX:
		BLOCKED.append(("connect", address))
		raise OSError(f"bộ thử: cấm ra mạng ({address})")
	return _connect(self, address, *a)


def _cam_dns(host, *a, **k):
	BLOCKED.append(("dns", host))
	raise OSError(f"bộ thử: cấm tra DNS ({host})")


socket.socket.connect = _cam_noi
socket.getaddrinfo = _cam_dns

from seed import Check  # noqa: E402

import frappe  # noqa: E402
import requests as real_requests  # noqa: E402

from bc.ai import llm  # noqa: E402
from bc.ai.llm import anthropic  # noqa: E402

c = Check()
KEY = "KHOA/bi+mat==bc.0123456789"          # không có dạng sk-…: chỉ bị xoá nhờ so đúng chuỗi với khoá đang khai
SYSTEM = "Bạn là trợ lý số liệu của công ty. Chỉ dùng số trong kết quả tra cứu."
QUESTION = "Phải thu quá hạn của KH#0007 tháng này bao nhiêu? CAUHOI-BIMAT"
TOOL_OUT = '{"overdue": 1612345678, "ghi_chu": "KETQUA-BIMAT"}'
TOOLS = [
	{"name": "xem_mang", "description": "Đọc một khối số của màn báo cáo. Gọi khi cần số liệu để trả lời.",
		"input_schema": {"type": "object", "properties": {
			"mang": {"type": "string", "enum": ["cong-no", "ton-kho"], "description": "Mảng"},
			"ten": {"type": "string", "description": "Tên khối"},
			"tham_so": {"type": "object", "description": "Tham số"}}, "required": ["mang", "ten"]}},
	{"name": "run_select", "description": "Chạy một câu SELECT chỉ đọc.",
		"input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}]
FB_MODEL = "claude-sonnet-5-5"     # nằm trong FALLBACK_MODELS → gửi fallbacks "default" + header beta
PLAIN_MODEL = "claude-haiku-5-5"   # không nằm trong FALLBACK_MODELS
SLEEPS: list = []

# Khối của một lượt assistant xin tra (thinking có chữ ký, chữ, hai tool_use song song, một loại khối lạ):
THINK = {"type": "thinking", "thinking": "", "signature": "EqQBCkgIARABGAIiQL+sig/AbC=="}
TU1 = {"type": "tool_use", "id": "toolu_01A", "name": "xem_mang",
	"input": {"mang": "cong-no", "ten": "receivables", "tham_so": {}}}
TU2 = {"type": "tool_use", "id": "toolu_01B", "name": "xem_mang", "input": {"mang": "ton-kho", "ten": "overview"}}
LA = {"type": "khoi_moi_chua_biet", "data": {"x": [1, 2.50, None, True]}, "z": "ü ạ  "}
ASSISTANT_1 = [THINK, {"type": "text", "text": "Để tôi tra số phải thu."}, TU1, TU2, LA]


class FakeResp:
	def __init__(self, status, body):
		self.status_code = status
		self.text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
		self.headers = {}


class FakeRequests:
	"""Lớp chặn 2: `requests` giả chạy theo kịch bản (FakeResp hoặc ngoại lệ). Hết kịch bản mà còn bị gọi → ném lỗi."""
	exceptions = real_requests.exceptions

	def __init__(self, script=()):
		self.script, self.calls, self.unexpected = list(script), [], 0

	def post(self, url, **kw):
		if not self.script:
			self.unexpected += 1
			raise AssertionError("bộ thử: gọi mạng ngoài ý muốn")
		self.calls.append({"url": url, **kw})
		step = self.script.pop(0)
		if isinstance(step, BaseException):
			raise step
		return step


def ok(content=None, stop="end_turn", model=FB_MODEL, usage=None, **extra):
	if content is None:
		content = [{"type": "text", "text": "Phải thu quá hạn là 1,6 tỷ."}]
	return FakeResp(200, {"id": "msg_01", "type": "message", "role": "assistant", "model": model, "content": content,
		"stop_reason": stop, "stop_sequence": None, "usage": usage or {"input_tokens": 1000, "output_tokens": 50},
		**extra})


def loi(status, etype, message, **details):
	e = {"type": etype, "message": message}
	if details:
		e["details"] = details
	return FakeResp(status, {"type": "error", "error": e, "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"})


def msgs1():
	return [{"role": "user", "content": QUESTION}]


def msgs2():
	return msgs1() + [{"role": "assistant", "content": copy.deepcopy(ASSISTANT_1)},
		{"role": "user", "content": [
			{"type": "tool_result", "tool_use_id": "toolu_01A", "content": TOOL_OUT},
			{"type": "tool_result", "tool_use_id": "toolu_01B", "content": "mảng đang ẩn", "is_error": True}]}]


def hoi(script, messages=None, model=FB_MODEL, provider="claude", tools=None, **kw):
	"""llm.chat với `requests` giả → (kết quả | None, LLMError | None, bản giả, các lần ngủ)."""
	fake = FakeRequests(script)
	anthropic.requests = fake
	del SLEEPS[:]
	out = err = None
	try:
		out = llm.chat(provider, model, SYSTEM, msgs1() if messages is None else messages,
			TOOLS if tools is None else tools, **kw)
	except llm.LLMError as e:
		err = e
	return out, err, fake, list(SLEEPS)


def than(call):
	return json.loads(call["data"].decode("utf-8"))


def lo_khoa(*things):
	blob = " ".join(repr(t) + str(t) for t in things)
	return KEY in blob or KEY[:8] in blob


def vet(err):
	return "".join(traceback.format_exception(type(err), err, err.__traceback__))


def khung_llm(err):
	out, tb = [], err.__traceback__
	while tb is not None:
		f = tb.tb_frame
		if os.sep + os.path.join("bc", "ai", "llm") + os.sep in f.f_code.co_filename:
			out.append((f.f_code.co_name, dict(f.f_locals)))
		tb = tb.tb_next
	return out


anthropic.sleep = SLEEPS.append
anthropic.requests = FakeRequests()
frappe.conf.clear()

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[1] Không khoá / khoá sai dạng / tham số sai → lỗi, KHÔNG gọi mạng")
out, err, fake, sl = hoi([ok()])
c("chưa khai khoá → no_key, không POST", err is not None and err.kind == "no_key" and fake.calls == [], err)
for nhan, k in (("toàn dấu cách", "  \n "), ("xuống dòng ở giữa", "abc123\nDEF456"), ("dấu cách ở giữa", "abc 123xyz"),
		("ký tự ngoài 0x21–0x7E", "abc 123")):
	frappe.conf["bc_ai_anthropic_key"] = k
	out, err, fake, sl = hoi([ok()])
	c(f"khoá {nhan} = chưa có khoá → no_key, không POST", err is not None and err.kind == "no_key" and fake.calls == []
		and len(fake.script) == 1, err and (err.kind, err.message))
frappe.conf["bc_ai_anthropic_key"] = "abc123\nDEF456ghi"
fake = FakeRequests([ok()])
anthropic.requests, err = fake, None
try:
	anthropic.chat(FB_MODEL, SYSTEM, msgs1(), TOOLS)
except llm.LLMError as e:
	err = e
c("gọi thẳng adapter với khoá sai dạng → cũng no_key, không POST", err is not None and err.kind == "no_key"
	and fake.calls == [], err)
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.conf["bc_ai_openai_key"] = "khoa-openai-123456"
out, err, fake, sl = hoi([ok()], provider="openai")
c("provider openai (có khoá) → http 'chỉ hỗ trợ claude', không POST", err is not None and err.kind == "http"
	and fake.calls == [] and "claude" in err.message, err)
out, err, fake, sl = hoi([ok()], provider="gemini")
c("provider lạ → http, không POST", err is not None and err.kind == "http" and fake.calls == [])
for m in ("", "  ", None):
	out, err, fake, sl = hoi([ok()], model=m)
	c(f"model trống ({m!r}) → http, không POST", err is not None and err.kind == "http" and fake.calls == [])
for tc in ({"type": "any"}, {"type": "tool", "name": "xem_mang"}, {"type": "auto"}, "none", {"type": "none", "x": 1}):
	out, err, fake, sl = hoi([ok()], tool_choice=tc)
	c(f"tool_choice {tc!r} → http (chỉ nhận None / {{'type': 'none'}}), không POST", err is not None
		and err.kind == "http" and fake.calls == [], err and err.message)
for nhan, ms in (("rỗng", []), ("không phải list", "câu hỏi"), ("role system", [{"role": "system", "content": "x"}]),
		("content số", [{"role": "user", "content": 5}]), ("bắt đầu bằng assistant",
		[{"role": "assistant", "content": "a"}, {"role": "user", "content": "b"}])):
	out, err, fake, sl = hoi([ok()], messages=ms)
	c(f"messages {nhan} → http, không POST", err is not None and err.kind == "http" and fake.calls == [], err)
out, err, fake, sl = hoi([ok()], tools=[{"name": "x"}])
c("tools thiếu input_schema → http, không POST", err is not None and err.kind == "http" and fake.calls == [])
c("lời báo tham số sai không chép câu hỏi", all(QUESTION not in str(e) for e in [err]))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[2] Lượt đầu: thân + header đúng từng trường")
out, err, fake, sl = hoi([ok()])
c("thành công, một POST, không ngủ", err is None and len(fake.calls) == 1 and sl == [], err)
g = fake.calls[0]
c("URL Messages API", g["url"] == "https://api.anthropic.com/v1/messages", g["url"])
c("requests.post chỉ nhận headers / data / timeout / allow_redirects=False", set(g) == {"url", "headers", "data",
	"timeout", "allow_redirects"} and g["allow_redirects"] is False, sorted(g))
c("timeout = (nối 10 s, đọc 60 s mặc định)", g["timeout"] == (10, 60), g["timeout"])
c("header ĐÚNG: x-api-key, anthropic-version 2026-10-21, content-type, anthropic-beta fallback (model có fallback)",
	g["headers"] == {"x-api-key": KEY, "anthropic-version": "2026-10-21", "content-type": "application/json",
	"anthropic-beta": "server-side-fallback-2026-07-01"}, {k: v for k, v in g["headers"].items() if k != "x-api-key"})
b = than(g)
c("thân ĐÚNG từng trường (không thừa, không thiếu)", b == {"model": FB_MODEL, "max_tokens": 2000,
	"messages": [{"role": "user", "content": QUESTION}], "tools": TOOLS, "system": SYSTEM,
	"cache_control": {"type": "ephemeral"}, "output_config": {"effort": "medium"}, "fallbacks": "default"}, b)
c("cache_control ở CẤP TRÊN, không chèn vào khối / công cụ / system", b.get("cache_control") == {"type": "ephemeral"}
	and all("cache_control" not in t for t in b["tools"]) and isinstance(b["system"], str))
c("không tool_choice (auto là mặc định), không thinking, không tham số lấy mẫu, không output_config.format",
	not {"tool_choice", "thinking", "temperature", "top_p", "top_k", "stop_sequences", "stream"} & set(b)
	and set(b["output_config"]) == {"effort"})
c("thân là JSON UTF-8 thật (chữ Việt không bị \\u-escape)", QUESTION.encode("utf-8") in g["data"])
out, err, fake, sl = hoi([ok(model=PLAIN_MODEL)], model=PLAIN_MODEL, max_tokens=1234, timeout=45)
g, b = fake.calls[0], than(fake.calls[0])
c("model không thuộc FALLBACK_MODELS → không header beta, không trường fallbacks", "anthropic-beta" not in g["headers"]
	and "fallbacks" not in b and set(g["headers"]) == {"x-api-key", "anthropic-version", "content-type"}, g["headers"])
c("max_tokens / timeout truyền đúng", b["max_tokens"] == 1234 and g["timeout"] == (10, 45))
out, err, fake, sl = hoi([ok()], tools=[])
c("tools rỗng → không gửi trường tools", err is None and "tools" not in than(fake.calls[0]))
out, err, fake, sl = hoi([ok()], tools=[], tool_choice={"type": "none"})
c("tools rỗng + tool_choice none → không gửi tool_choice (không có công cụ nào để cấm)",
	err is None and "tool_choice" not in than(fake.calls[0]))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[3] Lượt gửi kết quả công cụ: khối của lượt trước đi NGUYÊN, tool_result trong MỘT tin user")
ms = msgs2()
truoc = copy.deepcopy(ms)
out, err, fake, sl = hoi([ok()], messages=ms)
b = than(fake.calls[0])
c("messages trong thân == đúng messages đã đưa (thinking + chữ ký, text, 2 tool_use, khối lạ, 2 tool_result)",
	err is None and b["messages"] == truoc, b.get("messages"))
c("không sửa đối tượng messages của nơi gọi", ms == truoc)
raw = fake.calls[0]["data"].decode("utf-8")
c("từng khối assistant nằm NGUYÊN trong thân (chuỗi JSON của khối khớp từng ký tự, đúng thứ tự)",
	all(json.dumps(x, ensure_ascii=False) in raw for x in ASSISTANT_1)
	and raw.index('"type": "thinking"') < raw.index('"toolu_01A"') < raw.index('"toolu_01B"') < raw.index("khoi_moi"))
c("khối thinking rỗng + chữ ký gửi lại, không bị bỏ / sửa", b["messages"][1]["content"][0] == THINK)
c("hai tool_result trong MỘT tin user, is_error giữ nguyên", [m["role"] for m in b["messages"]] == ["user", "assistant",
	"user"] and [x["tool_use_id"] for x in b["messages"][2]["content"]] == ["toolu_01A", "toolu_01B"]
	and b["messages"][2]["content"][1]["is_error"] is True)
c("tools, system, cache_control, effort, fallbacks giữ nguyên qua các lượt", b["tools"] == TOOLS
	and b["system"] == SYSTEM and b.get("cache_control") == {"type": "ephemeral"}
	and b["output_config"] == {"effort": "medium"} and b.get("fallbacks") == "default" and "tool_choice" not in b)
c("system trống → không gửi trường system", "system" not in than(
	(lambda f: (llm.chat("claude", FB_MODEL, "", msgs1(), TOOLS), f)[1])(
		setattr(anthropic, "requests", FakeRequests([ok()])) or anthropic.requests).calls[0]))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[4] Lượt cuối tool_choice none (hết lượt tra → buộc trả lời bằng số đã có)")
out, err, fake, sl = hoi([ok()], messages=msgs2(), tool_choice={"type": "none"})
b = than(fake.calls[0])
c("tool_choice = {'type': 'none'} đúng nguyên dạng, tools VẪN gửi (lịch sử có tool_use)", err is None
	and b.get("tool_choice") == {"type": "none"} and b["tools"] == TOOLS, b.get("tool_choice"))
c("… phần còn lại của thân y như lượt không tool_choice", {k: v for k, v in b.items() if k != "tool_choice"}
	== than(hoi([ok()], messages=msgs2())[2].calls[0]))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[5] Trả lời: content NGUYÊN, mọi stop_reason")
FB_BLOCK = {"type": "fallback", "from": {"model": "claude-sonnet-5-5"}, "to": {"model": "claude-opus-4-8"}}
resp_content = [THINK, {"type": "text", "text": "Tôi sẽ tra.", "citations": None}, TU1, LA]
out, err, fake, sl = hoi([ok(content=copy.deepcopy(resp_content), stop="tool_use")])
c("stop_reason tool_use → trả về (không lỗi), đúng 6 khoá", err is None and set(out) == {"content", "stop_reason",
	"tokens_in", "tokens_out", "cost_tokens_in", "model"} and out["stop_reason"] == "tool_use", out or err)
c("content == đúng các khối API trả (thinking, text kèm trường null, tool_use, khối lạ) — không lọc, không đổi",
	out["content"] == resp_content, out["content"])
for stop in ("end_turn", "max_tokens", "pause_turn", "stop_sequence", "model_context_window_exceeded", "khac_moi"):
	out, err, fake, sl = hoi([ok(stop=stop, content=[{"type": "text", "text": "x"}])])
	c(f"stop_reason {stop} → trả nguyên cho nơi gọi xử lý", err is None and out["stop_reason"] == stop, err)
out, err, fake, sl = hoi([ok(stop="max_tokens", content=[])])
c("max_tokens với content rỗng (chưa viết được gì) → vẫn trả, không lỗi", err is None and out["content"] == [])
for nhan, cont in (("thiếu content", None), ("content là chuỗi", "chữ"), ("content có phần tử không phải dict",
		[{"type": "text", "text": "a"}, "b"])):
	resp = ok(stop="end_turn")
	body = json.loads(resp.text)
	if cont is None:
		body.pop("content")
	else:
		body["content"] = cont
	out, err, fake, sl = hoi([FakeResp(200, body)])
	c(f"{nhan} → schema, mang token đã tính tiền", err is not None and err.kind == "schema" and err.tokens_in == 1000
		and err.tokens_out == 50, err and (err.kind, err.tokens_in))
for nhan, stop in (("thiếu stop_reason", None), ("stop_reason rỗng", ""), ("stop_reason số", 3)):
	out, err, fake, sl = hoi([ok(stop=stop)])
	c(f"{nhan} → schema", err is not None and err.kind == "schema", err)
out, err, fake, sl = hoi([FakeResp(200, "<html>proxy</html>"), ok()])
c("200 nhưng thân không phải JSON → http, không retry", err is not None and err.kind == "http" and len(fake.calls) == 1)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[6] Từ chối, fallback đã trả lời")
U = {"input_tokens": 1500, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 2000, "output_tokens": 7}
out, err, fake, sl = hoi([ok(stop="refusal", content=[], usage=U, stop_details={"type": "refusal",
	"category": "cyber", "explanation": None}), ok()])
# token vào = 1500 + 400 + 2000 = 3900; cost = 1500 + 1,25×400 + 0,1×2000 = 1500 + 500 + 200 = 2200
c("refusal (content rỗng) → LLMError refusal, KHÔNG retry", err is not None and err.kind == "refusal"
	and len(fake.calls) == 1 and sl == [], err)
c("… lời có loại (cyber), mang token đã tính tiền + cost + model", err is not None and "cyber" in err.message and err.tokens_in == 3900
	and err.tokens_out == 7 and abs(err.cost_tokens_in - 2200.0) < 1e-9 and err.model == FB_MODEL,
	err and (err.message, err.tokens_in, err.cost_tokens_in))
out, err, fake, sl = hoi([ok(stop="refusal", content=[{"type": "text", "text": "Tôi sẽ"}, {"type": "tool_use",
	"id": "toolu_X", "name": "run_select", "input": {}}], stop_details=None)])
c("refusal giữa chừng có tool_use dở (stop_details null) → vẫn refusal (tool dở không đến tay nơi gọi)",
	err is not None and err.kind == "refusal" and out is None, err)
c("… lời không chép phần chữ dở của mô hình", err is not None and "Tôi sẽ" not in err.message, err and err.message)
# Fallback đã trả lời: không lỗi, model = model thực, khối fallback giữ đúng chỗ, token cộng qua usage.iterations
UF = {"input_tokens": 900, "output_tokens": 60, "cache_read_input_tokens": 100, "iterations": [
	{"type": "message", "input_tokens": 1200, "cache_creation_input_tokens": 800, "output_tokens": 0},
	{"type": "fallback_message", "input_tokens": 900, "cache_read_input_tokens": 100, "output_tokens": 60}]}
cont_fb = [FB_BLOCK, {"type": "thinking", "thinking": "", "signature": "sigOpus48=="}, {"type": "text",
	"text": "Phải thu quá hạn 1,6 tỷ."}]
out, err, fake, sl = hoi([ok(content=copy.deepcopy(cont_fb), model="claude-opus-4-8", usage=UF)])
# token vào = (1200 + 800) + (900 + 100) = 3000; ra = 60; cost = 1200 + 900 + 1,25×800 + 0,1×100 = 2100 + 1000 + 10
c("fallback đã trả lời (stop end_turn) → kết quả bình thường, model = model thực trả lời", err is None
	and out["model"] == "claude-opus-4-8" and out["stop_reason"] == "end_turn", out or err)
c("… content giữ khối fallback ĐẦU danh sách, nguyên dạng", out["content"] == cont_fb)
c("… token = cộng mọi mục usage.iterations (3000 vào / 60 ra), cost 3110", out["tokens_in"] == 3000
	and out["tokens_out"] == 60 and abs(out["cost_tokens_in"] - 3110.0) < 1e-9, out)
ms3 = msgs1() + [{"role": "assistant", "content": out["content"]}, {"role": "user", "content": "Còn tồn kho?"}]
out2, err, fake, sl = hoi([ok()], messages=ms3)
b = than(fake.calls[0])
c("lượt sau gửi lại lượt có fallback NGUYÊN (khối fallback đúng vị trí, thinking của model fallback giữ nguyên), "
	"model yêu cầu + fallbacks vẫn như cũ", err is None and b["messages"][1]["content"] == cont_fb
	and b["model"] == FB_MODEL and b.get("fallbacks") == "default", b["messages"][1])
out, err, fake, sl = hoi([ok(stop="refusal", content=[FB_BLOCK], model="claude-opus-4-8", usage=UF)])
c("cả chuỗi fallback từ chối (refusal sau khối fallback) → refusal, token của mọi lượt thử", err is not None
	and err.kind == "refusal" and err.tokens_in == 3000 and err.model == "claude-opus-4-8", err)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[7] Phân loại lỗi + retry (như call)")
for nhan, resp in (
		("402 billing_error", loi(402, "billing_error", "Billing problem")),
		("402 thân không phải JSON", FakeResp(402, "<html>Payment Required</html>")),
		("429 enforced_spend_limit_reached", loi(429, "rate_limit_error", "spend", error_code="enforced_spend_limit_reached")),
		("400 'credit balance'", loi(400, "invalid_request_error", "Your credit balance is too low to access the API."))):
	out, err, fake, sl = hoi([resp, ok()])
	c(f"{nhan} → credit, 1 POST, không ngủ", err is not None and err.kind == "credit" and len(fake.calls) == 1
		and sl == [], (err and err.kind, len(fake.calls), sl))
RL = lambda: loi(429, "rate_limit_error", "Number of requests has exceeded your rate limit")  # noqa: E731
out, err, fake, sl = hoi([RL(), RL(), RL(), ok()])
c("429 × 3 → rate sau 3 POST, ngủ [5, 20], không lượt thứ 4", err is not None and err.kind == "rate"
	and len(fake.calls) == 3 and sl == [5, 20] and len(fake.script) == 1 and "đã thử 3 lần" in err.message,
	(err and err.kind, len(fake.calls), sl))
out, err, fake, sl = hoi([RL(), ok()])
c("429 rồi 200 → thành công, ngủ [5]", err is None and sl == [5] and len(fake.calls) == 2)
c("… lượt thử lại gửi đúng cùng thân", than(fake.calls[0]) == than(fake.calls[1]))
for status, etype in ((529, "overloaded_error"), (500, "api_error"), (503, "api_error"), (504, "timeout_error")):
	out, err, fake, sl = hoi([loi(status, etype, "x")] * 3 + [ok()])
	c(f"{status} × 3 → http sau 3 POST, ngủ [5, 20]", err is not None and err.kind == "http" and len(fake.calls) == 3
		and sl == [5, 20], (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = hoi([loi(500, "api_error", "x"), loi(529, "overloaded_error", "x"), ok()])
c("500 → 529 → 200: thành công ở lượt 3", err is None and len(fake.calls) == 3 and sl == [5, 20])
E = real_requests.exceptions
for nhan, exc in (("ReadTimeout", E.ReadTimeout("read timed out")), ("ConnectTimeout", E.ConnectTimeout("x")),
		("ConnectionError", E.ConnectionError("aborted")), ("ChunkedEncodingError", E.ChunkedEncodingError("x"))):
	out, err, fake, sl = hoi([exc, exc, exc, ok()])
	c(f"{nhan} × 3 → timeout sau 3 POST, ngủ [5, 20]", err is not None and err.kind == "timeout"
		and len(fake.calls) == 3 and sl == [5, 20], (err and err.kind, len(fake.calls)))
for status, etype in ((401, "authentication_error"), (403, "permission_error"), (404, "not_found_error"),
		(400, "invalid_request_error"), (413, "request_too_large")):
	out, err, fake, sl = hoi([loi(status, etype, "nope"), ok()])
	c(f"{status} → http, KHÔNG retry, lời nêu mã", err is not None and err.kind == "http" and len(fake.calls) == 1
		and sl == [] and f"HTTP {status}" in err.message, (err and err.kind, len(fake.calls)))
c("lỗi HTTP (không có lượt trả lời) → token 0", err is not None and err.tokens_in == 0 and err.tokens_out == 0 and err.cost_tokens_in == 0)
out, err, fake, sl = hoi([loi(400, "invalid_request_error", "tool_choice: type \"tool\" and \"any\" are not supported "
	"for this model.")])
c("400 tool_choice (nếu xảy ra) → http, không retry", err.kind == "http" and len(fake.calls) == 1)
out, err, fake, sl = hoi([loi(400, "invalid_request_error", "fallbacks: unexpected parameter (missing anthropic-beta)"),
	ok()])
c("400 nhắc fallbacks / anthropic-beta → gọi lại MỘT lần không kèm, thành công, không ngủ", err is None
	and len(fake.calls) == 2 and sl == [] and "fallbacks" in than(fake.calls[0])
	and "fallbacks" not in than(fake.calls[1]) and "anthropic-beta" not in fake.calls[1]["headers"])
c("… lượt gọi lại giữ nguyên messages / tools / cache_control", {k: v for k, v in than(fake.calls[1]).items()}
	== {k: v for k, v in than(fake.calls[0]).items() if k != "fallbacks"})
out, err, fake, sl = hoi([loi(400, "invalid_request_error", "fallbacks bad"), loi(400, "invalid_request_error",
	"fallbacks bad"), ok()])
c("… lần thứ hai vẫn 400 → http, không gọi thêm", err is not None and err.kind == "http" and len(fake.calls) == 2)
out, err, fake, sl = hoi([loi(400, "invalid_request_error", "fallbacks"), RL(), ok()])
c("… gọi lại không fallback rồi 429 → vẫn còn đủ 2 lần retry (lượt bỏ fallback không tính)", err is None
	and len(fake.calls) == 3 and sl == [5])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[8] Khoá, câu hỏi, kết quả công cụ không lọt ra lỗi / vết lỗi")
THU = []
out, err, fake, sl = hoi([E.InvalidHeader(f"Invalid return character in header value: {KEY!r}"), ok()],
	messages=msgs2())
THU.append(err)
c("InvalidHeader chứa khoá → http, không retry, lời chỉ còn tên loại", err is not None and err.kind == "http" and len(fake.calls) == 1
	and err.message == "không gửi được yêu cầu (InvalidHeader)", err and err.message)
exc = E.ConnectionError(f"HTTPSConnectionPool(host='api.anthropic.com'): x-api-key: {KEY}")
out, err, fake, sl = hoi([exc, exc, exc], messages=msgs2())
THU.append(err)
c("lỗi nối chứa khoá × 3 → timeout, khoá không lọt", err is not None and err.kind == "timeout" and not lo_khoa(str(err), repr(err),
	err.args, vet(err)))
out, err, fake, sl = hoi([loi(401, "authentication_error", f"invalid x-api-key: {KEY}")], messages=msgs2())
THU.append(err)
c("API chép khoá trong thân 401 → đã xoá", err is not None and err.kind == "http" and not lo_khoa(str(err)) and "***" in err.message)
out, err, fake, sl = hoi([RuntimeError(f"bug {KEY}")], messages=msgs2())
THU.append(err)
out, err, fake, sl = hoi([ok(stop="refusal", content=[])], messages=msgs2())
THU.append(err)
out, err, fake, sl = hoi([ok(content="x")], messages=msgs2())
THU.append(err)
out, err, fake, sl = hoi([loi(402, "billing_error", "x")], messages=msgs2())
THU.append(err)
real_req = anthropic._chat_request


def _hong(*a, **k):
	raise RuntimeError(f"hỏng khi dựng yêu cầu {KEY} {a[3]!r}")


anthropic._chat_request = _hong
out, err, fake, sl = hoi([ok()], messages=msgs2())
anthropic._chat_request = real_req
THU.append(err)
c("lỗi lập trình trong adapter → cửa bọc thành http, nêu loại + [file:dòng], khoá không lọt", err is not None
	and err.kind == "http" and "RuntimeError" in err.message and "[test_ai_chat.py:" in err.message
	and not lo_khoa(str(err), vet(err)) and err.__context__ is None and err.__cause__ is None, err and err.message)
sach, chi_tiet = True, []
for e in THU:
	if e is None:
		sach = False
		chi_tiet.append("không có lỗi")
		continue
	kh = khung_llm(e)
	blob = repr(kh) + vet(e) + str(e) + repr(vars(e))
	if [k[0] for k in kh] != ["chat"] or lo_khoa(blob) or e.__context__ is not None or e.__cause__ is not None \
			or SYSTEM in blob or "CAUHOI-BIMAT" in blob or "KETQUA-BIMAT" in blob or "toolu_01A" in blob:
		sach = False
		chi_tiet.append((e.kind, [k[0] for k in kh], sorted(kh[0][1]) if kh else None))
c("mọi LLMError ra khỏi chat (mạng, 401, 402, từ chối, sai dạng, lỗi lập trình): vết chỉ còn khung chat, không "
	"kéo ngoại lệ gốc, không khoá / đề bài / câu hỏi / kết quả công cụ trong lời, vết, biến cục bộ, thuộc tính",
	sach and len(THU) == 8, chi_tiet)
c("không lời gọi frappe.log_error nào mang khoá", not lo_khoa(frappe.LOGGED))
bien = {f"{m.__name__}.{k}": v for m in (llm, anthropic) for k, v in vars(m).items()
	if k != "requests" and not k.startswith("__") and not callable(v) and not isinstance(v, type(os))}
c("không biến cấp module nào giữ khoá / câu hỏi sau các lượt gọi", not lo_khoa(*bien.values())
	and "CAUHOI-BIMAT" not in repr(bien))
out, err, fake, sl = hoi([ok()])
c("kết quả thành công không chứa khoá", not lo_khoa(out, json.dumps(out, ensure_ascii=False)))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[9] Số token (prompt caching)")
for nhan, usage, vao, ra, cost in (
		# 1000 + 2000 + 30000 = 33000; cost = 1000 + 1,25×2000 + 0,1×30000 = 1000 + 2500 + 3000 = 6500
		("vào + ghi cache + đọc cache", {"input_tokens": 1000, "cache_creation_input_tokens": 2000,
			"cache_read_input_tokens": 30000, "output_tokens": 400}, 33000, 400, 6500.0),
		("chỉ vào thường", {"input_tokens": 777, "output_tokens": 3}, 777, 3, 777.0),
		# 0 + 0 + 12345 = 12345; cost = 1234,5
		("toàn đọc cache", {"input_tokens": 0, "cache_read_input_tokens": 12345, "output_tokens": 1}, 12345, 1, 1234.5),
		# 8 + 8 = 16; cost = 8 + 10 = 18
		("toàn ghi cache (lượt đầu)", {"input_tokens": 8, "cache_creation_input_tokens": 8, "output_tokens": 0}, 16, 0,
			18.0),
		("trường null / chuỗi / bool bị bỏ qua", {"input_tokens": 10, "cache_creation_input_tokens": None,
			"cache_read_input_tokens": "50", "output_tokens": True}, 10, 0, 10.0),
		("iterations không mang số → dùng usage cấp trên", {"input_tokens": 100, "cache_read_input_tokens": 1000,
			"output_tokens": 9, "iterations": [{"type": "message"}]}, 1100, 9, 200.0)):
	out, err, fake, sl = hoi([ok(usage=usage)])
	c(f"{nhan}: vào {vao}, ra {ra}, cost {cost}", err is None and (out["tokens_in"], out["tokens_out"]) == (vao, ra)
		and abs(out["cost_tokens_in"] - cost) < 1e-9 and isinstance(out["cost_tokens_in"], float),
		out and (out["tokens_in"], out["tokens_out"], out["cost_tokens_in"]))
body = json.loads(ok().text)
body.pop("usage")
out, err, fake, sl = hoi([FakeResp(200, body)])
c("thiếu usage → 0 / 0 / 0.0, không lỗi", err is None and (out["tokens_in"], out["tokens_out"], out["cost_tokens_in"])
	== (0, 0, 0.0))
out, err, fake, sl = hoi([ok(model="")])
c("thân không nêu model → model đã yêu cầu", err is None and out["model"] == FB_MODEL)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[10] Bộ thử không thể ra mạng; call() vẫn như cũ sau khi tách vòng gửi chung")
c("không lượt nối / tra DNS nào bị chặn ở tầng socket (mọi lượt đi qua bản giả)", BLOCKED == [], BLOCKED)
anthropic.requests = real_requests
anthropic.sleep = SLEEPS.append
del SLEEPS[:]
out, err = None, None
try:
	llm.chat("claude", PLAIN_MODEL, SYSTEM, msgs1(), TOOLS)
except llm.LLMError as e:
	err = e
c("requests THẬT + socket bị chặn → timeout sau 3 lượt (không thoát ra mạng)", err is not None and err.kind == "timeout"
	and len(BLOCKED) >= 3 and SLEEPS == [5, 20], (err and err.kind, len(BLOCKED)))
c("… khoá không lọt qua lỗi nối thật", err is not None and not lo_khoa(str(err), vet(err)))
anthropic.requests = FakeRequests([ok(content=[{"type": "text", "text": json.dumps({"a": 1})}])])
r = anthropic.call(PLAIN_MODEL, SYSTEM, "x", "s", {"type": "object"})
c("call() sau khi tách _post: vẫn đọc JSON từ khối text (test_ai_llm.py kiểm đầy đủ)", r["data"] == {"a": 1})

c.done()
