"""Trợ lý AI — cửa ra mô hình (bc.ai.llm + bc.ai.llm.anthropic), trần chi (bc.ai.budget), đề bài (bc.ai.prompt).

KHÔNG RA MẠNG: (1) chặn ở tầng socket — mọi lời nối không phải socket unix của MariaDB và mọi lượt tra DNS đều ném
lỗi; (2) tên `requests` của adapter thay bằng bản giả chạy theo kịch bản, hết kịch bản mà còn bị gọi thì ném lỗi và
đếm. Có ca chứng minh cả hai lớp chặn hoạt động.

Số kỳ vọng TÍNH TAY (phép tính ghi trong comment). Hôm nay giả = 27/10/2026. Định dạng yêu cầu / trả lời đối chiếu với
tài liệu Claude API bản 2026-10-21 (structured outputs, server-side fallback, usage.iterations, mã lỗi).
"""
import ast
import datetime
import json
import os
import re
import socket
import traceback
from decimal import Decimal

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

from seed import Check, bc_settings, child, insert, reset, single  # noqa: E402
from paths import BC_ROOT  # noqa: E402

import frappe  # noqa: E402
import requests as real_requests  # noqa: E402

from bc.ai import budget, llm, prompt  # noqa: E402
from bc.ai.llm import anthropic  # noqa: E402

c = Check()
KEY = "KHOA/bi+mat==bc.0123456789"          # KHÔNG có dạng sk-…: phải bị xoá nhờ so đúng chuỗi với khoá đang khai
OKEY = "khoa-openai/BI-MAT.987654321"
SK = "sk-ant-api03-Kh0aCu_dA-thu-h0i-000111"   # khoá KHÔNG khai trong site: chỉ bị xoá nhờ mẫu sk-…
SYSTEM = "Bạn là trợ lý phân tích. Viết ngắn, thẳng."
USER = json.dumps({"nhom": "tai-chinh", "pack": {"cong-no": {"receivables": {"kpis": {"overdue_pct": 27.5}}}},
	"tin_hieu": [{"id": "S1", "rule": "cn.qua_han_ty_le", "muc": "vang"}]}, ensure_ascii=False)
GOOD = {"insights": [
	{"signal": "S1", "severity": "do", "priority": 5, "title": "Nợ quá hạn vượt ngưỡng",
		"body": "Nợ quá hạn chiếm {{cong-no.receivables.kpis.overdue_pct|pct}} phải thu.",
		"advice": ["Kế toán rà soát khách quá hạn trong 7 ngày."]},
	{"signal": None, "severity": "vang", "priority": 2, "title": "Phải thu tập trung",
		"body": "Tỷ lệ quá hạn {{cong-no.receivables.kpis.overdue_pct|pct}}.", "advice": []}]}
SLEEPS: list = []


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


def ok(data=None, text=None, model="claude-sonnet-5-5", usage=None, stop="end_turn", content=None, **extra):
	if content is None:
		content = [{"type": "text", "text": text if text is not None else json.dumps(GOOD if data is None else data,
			ensure_ascii=False)}]
	return FakeResp(200, {"id": "msg_01", "type": "message", "role": "assistant", "model": model, "content": content,
		"stop_reason": stop, "usage": usage or {"input_tokens": 1000, "output_tokens": 500}, **extra})


def loi(status, etype, message, **details):
	e = {"type": etype, "message": message}
	if details:
		e["details"] = details
	return FakeResp(status, {"type": "error", "error": e, "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"})


def goi(script, model="claude-sonnet-5-5", provider="claude", schema=None, **kw):
	"""llm.call với `requests` giả theo kịch bản → (kết quả | None, LLMError | None, bản giả, các lần ngủ)."""
	fake = FakeRequests(script)
	anthropic.requests = fake
	del SLEEPS[:]
	out = err = None
	try:
		out = llm.call(provider, model, SYSTEM, USER, prompt.SCHEMA_NAME, prompt.SCHEMA if schema is None else schema,
			**kw)
	except llm.LLMError as e:
		err = e
	return out, err, fake, list(SLEEPS)


def than(call):
	return json.loads(call["data"].decode("utf-8"))


def lo_khoa(*things):
	"""Khoá (hoặc 8 ký tự đầu của nó) có nằm trong bất kỳ thứ gì đưa vào không."""
	blob = " ".join(repr(t) + str(t) for t in things)
	return any(k in blob or k[:8] in blob for k in (KEY, OKEY))


def vet(err):
	return "".join(traceback.format_exception(type(err), err, err.__traceback__))


def khung_llm(err):
	"""[(tên hàm, biến cục bộ)] của các khung thuộc bc/ai/llm trong vết lỗi — thứ Frappe in ra khi ghi vết KÈM BIẾN."""
	out, tb = [], err.__traceback__
	while tb is not None:
		f = tb.tb_frame
		if os.sep + os.path.join("bc", "ai", "llm") + os.sep in f.f_code.co_filename:
			out.append((f.f_code.co_name, dict(f.f_locals)))
		tb = tb.tb_next
	return out


reset(only={"BC AI Run", "BC AI Model Price", "BC Tet Date"})
bc_settings()
anthropic.sleep = SLEEPS.append
BAY = FakeRequests()          # bẫy: không có kịch bản → mọi lời gọi mạng ngoài ý muốn đều ném lỗi + đếm
anthropic.requests = BAY
frappe.conf.clear()

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[1] Không có khoá → no_key, KHÔNG gọi mạng")
c("chưa khai khoá: has_key sai cho cả hai provider", llm.has_key("claude") is False and llm.has_key("openai") is False)
out, err, fake, sl = goi([])
c("claude không khoá → LLMError no_key", err is not None and err.kind == "no_key", err)
c("… không một lượt POST nào (bẫy không bị chạm), không ngủ", fake.calls == [] and fake.unexpected == 0 and sl == [])
c("… trạng thái Run = khong-khoa", llm.run_status(err.kind) == "khong-khoa")
fake, err = FakeRequests([]), None
anthropic.requests = fake
try:
	anthropic.call("claude-sonnet-5-5", SYSTEM, USER, prompt.SCHEMA_NAME, prompt.SCHEMA)
except llm.LLMError as e:
	err = e
c("gọi thẳng adapter (không qua cửa) khi không khoá → cũng no_key, không gọi mạng", err is not None
	and err.kind == "no_key" and fake.unexpected == 0 and fake.calls == [], err)
frappe.conf["bc_ai_anthropic_key"] = "   \n"
out, err, fake, sl = goi([])
c("khoá chỉ toàn dấu cách → vẫn no_key, không gọi mạng", err.kind == "no_key" and fake.unexpected == 0
	and llm.has_key("claude") is False)
out, err, fake, sl = goi([], provider="openai")
c("openai không khoá → no_key (P2 chưa làm)", err.kind == "no_key" and fake.unexpected == 0)
frappe.conf["bc_ai_openai_key"] = OKEY
out, err, fake, sl = goi([], provider="openai")
c("openai có khoá → http 'chưa hỗ trợ', không gọi mạng", err.kind == "http" and err.message == "chưa hỗ trợ"
	and fake.unexpected == 0 and llm.has_key("openai") is True, err.message)
out, err, fake, sl = goi([], provider="gemini")
c("provider lạ → LLMError http, không gọi mạng", err.kind == "http" and fake.unexpected == 0)
frappe.conf["bc_ai_anthropic_key"] = KEY
for m in ("", "   ", None):
	out, err, fake, sl = goi([], model=m)
	c(f"model trống ({m!r}) → LLMError http, không gọi mạng", err is not None and err.kind == "http"
		and fake.unexpected == 0 and fake.calls == [], err)
c("khai khoá rồi: has_key đúng, chỉ trả bool", llm.has_key("claude") is True)
c("PROVIDERS / KINDS giữ nguyên hợp đồng", llm.PROVIDERS == {"claude": "bc_ai_anthropic_key",
	"openai": "bc_ai_openai_key"} and set(llm.KINDS) == {"no_key", "credit", "rate", "http", "timeout", "schema",
	"refusal"})
c("run_status: credit → het-credit, no_key → khong-khoa, còn lại → loi",
	[llm.run_status(k) for k in ("credit", "no_key", "rate", "http", "timeout", "schema", "refusal")]
	== ["het-credit", "khong-khoa", "loi", "loi", "loi", "loi", "loi"])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[2] Lượt gọi thường: thân + header đúng từng trường")
# token vào = 1000 + 200 (ghi cache) + 34 (đọc cache) = 1234; token ra = 567
out, err, fake, sl = goi([ok(usage={"input_tokens": 1000, "cache_creation_input_tokens": 200,
	"cache_read_input_tokens": 34, "output_tokens": 567})])
c("trả đúng 4 khoá: data / tokens_in / tokens_out / model", err is None and out == {"data": GOOD, "tokens_in": 1234,
	"tokens_out": 567, "model": "claude-sonnet-5-5"}, out or err)
c("đúng một lượt POST, không ngủ", len(fake.calls) == 1 and sl == [])
g = fake.calls[0]
c("URL Messages API", g["url"] == "https://api.anthropic.com/v1/messages", g["url"])
c("chỉ truyền headers / data / timeout / allow_redirects cho requests.post", set(g) == {"url", "headers", "data",
	"timeout", "allow_redirects"}, set(g))
c("KHÔNG theo chuyển hướng (x-api-key không bị chép sang máy chủ khác)", g["allow_redirects"] is False)
c("header: x-api-key, anthropic-version 2026-10-21, content-type, beta fallback (sonnet-5-5 thuộc danh sách)",
	g["headers"] == {"x-api-key": KEY, "anthropic-version": "2026-10-21", "content-type": "application/json",
		"anthropic-beta": "server-side-fallback-2026-07-01"}, g["headers"])
b = than(g)
c("thân đúng từng trường: model, max_tokens 16000, system, messages, output_config (effort medium + json_schema), "
	"fallbacks default", b == {"model": "claude-sonnet-5-5", "max_tokens": 16000, "system": SYSTEM,
		"messages": [{"role": "user", "content": USER}],
		"output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": prompt.SCHEMA}},
		"fallbacks": "default"}, b)
c("KHÔNG có tool_choice / tools / thinking / temperature / top_p / top_k / stream",
	not ({"tool_choice", "tools", "thinking", "temperature", "top_p", "top_k", "stream"} & set(b)))
c("output_config.format là json_schema mang đúng schema ghi_nhan_dinh",
	b["output_config"]["format"] == {"type": "json_schema", "schema": prompt.SCHEMA})
c("timeout: nối 10 s, đọc 300 s", g["timeout"] == (10, 300), g["timeout"])
c("thân là bytes UTF-8, tiếng Việt giữ nguyên (không \\u)", isinstance(g["data"], bytes)
	and "Bạn là trợ lý phân tích" in g["data"].decode("utf-8"))

out, err, fake, sl = goi([ok(model="claude-haiku-5-5")], model="claude-haiku-5-5", max_tokens=2048, timeout=60)
g, b = fake.calls[0], than(fake.calls[0])
c("model ngoài danh sách fallback: không header anthropic-beta, không trường fallbacks",
	g["headers"] == {"x-api-key": KEY, "anthropic-version": "2026-10-21", "content-type": "application/json"}
	and "fallbacks" not in b and set(b) == {"model", "max_tokens", "system", "messages", "output_config"}, (g["headers"], b))
c("max_tokens / timeout truyền vào được dùng", b["max_tokens"] == 2048 and g["timeout"] == (10, 60))
co, khong = [], []
for m in ("claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
		"claude-haiku-5-5", "claude-sonnet-5", "claude-opus-4-8", "claude-sonnet-5-5-20261101", "claude-fable-5"):
	out, err, fake, sl = goi([ok(model=m)], model=m)
	h, b = fake.calls[0]["headers"], than(fake.calls[0])
	if h.get("anthropic-beta") == "server-side-fallback-2026-07-01" and b.get("fallbacks") == "default":
		co.append(m)
	elif "anthropic-beta" not in h and "fallbacks" not in b:
		khong.append(m)
c("fallbacks + header chỉ cho đúng 5 model đã chốt", co == ["claude-fable-5-2", "claude-fable-5-1",
	"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"], co)
c("… 5 model khác không gửi cả hai", khong == ["claude-haiku-5-5", "claude-sonnet-5", "claude-opus-4-8",
	"claude-sonnet-5-5-20261101", "claude-fable-5"], khong)
frappe.conf["bc_ai_anthropic_key"] = f"  {KEY}\n"
out, err, fake, sl = goi([ok()])
c("khoá khai thừa dấu cách / xuống dòng: header gửi khoá đã gọt", err is None
	and fake.calls[0]["headers"]["x-api-key"] == KEY)
frappe.conf["bc_ai_anthropic_key"] = KEY

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[3] Đọc trả lời: khối text đầu tiên, usage, model thực trả lời")
khac = {"insights": [{"signal": None, "severity": "vang", "priority": 1, "title": "Khối sau", "body": "x", "advice": []}]}
out, err, fake, sl = goi([ok(content=[{"type": "thinking", "thinking": "", "signature": "abc"},
	{"type": "text", "text": json.dumps(GOOD, ensure_ascii=False)},
	{"type": "text", "text": json.dumps(khac, ensure_ascii=False)}])])
c("content mở đầu bằng khối thinking: lấy khối text ĐẦU TIÊN (đọc theo type, không theo vị trí)",
	err is None and out["data"] == GOOD, out or err)
# usage.iterations có → cộng mọi lượt thử: vào = (100 + 7) + (110 + 3) = 220; ra = 5 + 50 = 55 (bỏ qua usage cấp trên)
out, err, fake, sl = goi([ok(model="claude-sonnet-5", content=[
	{"type": "fallback", "from": {"model": "claude-sonnet-5-5"}, "to": {"model": "claude-sonnet-5"}},
	{"type": "text", "text": json.dumps(GOOD, ensure_ascii=False)}],
	usage={"input_tokens": 110, "output_tokens": 50, "iterations": [
		{"type": "message", "input_tokens": 100, "cache_read_input_tokens": 7, "output_tokens": 5},
		{"type": "fallback_message", "input_tokens": 110, "cache_creation_input_tokens": 3, "output_tokens": 50}]})])
c("usage.iterations: token = tổng mọi lượt thử (220 vào, 55 ra)", err is None and out["tokens_in"] == 220
	and out["tokens_out"] == 55, out or err)
c("model trả về = model THỰC trả lời (fallback sang claude-sonnet-5)", out["model"] == "claude-sonnet-5")
out, err, fake, sl = goi([ok(usage={"input_tokens": 321, "output_tokens": 45, "iterations": []})])
c("iterations rỗng → dùng usage cấp trên (321 / 45)", out["tokens_in"] == 321 and out["tokens_out"] == 45, out)
out, err, fake, sl = goi([ok(usage={"input_tokens": 50, "cache_read_input_tokens": 4, "output_tokens": 9,
	"iterations": [{"type": "message"}, "rác"]})])
# mục iterations không mang token → usage cấp trên: vào = 50 + 4 = 54; ra = 9
c("iterations có mục nhưng không có số token → usage cấp trên (54 / 9), không báo 0", out["tokens_in"] == 54
	and out["tokens_out"] == 9, out)
out, err, fake, sl = goi([ok(usage={"service_tier": "standard", "input_tokens": None, "output_tokens": "12"})])
c("usage không có số token hợp lệ → 0 / 0, không lỗi", err is None and out["tokens_in"] == 0
	and out["tokens_out"] == 0, out or err)
out, err, fake, sl = goi([ok(usage={"input_tokens": 321, "output_tokens": 45})])
c("không có iterations → usage cấp trên (321 / 45)", out["tokens_in"] == 321 and out["tokens_out"] == 45, out)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[4] Fallback bị từ chối (400 nhắc anthropic-beta / fallbacks) → gọi lại MỘT lần không kèm")
BETA400 = "Unexpected value(s) `server-side-fallback-2026-07-01` for the `anthropic-beta` header."
out, err, fake, sl = goi([loi(400, "invalid_request_error", BETA400), ok()])
c("400 nhắc anthropic-beta → gọi lại, thành công", err is None and out["data"] == GOOD and len(fake.calls) == 2, err)
c("… lượt đầu CÓ header + trường, lượt sau KHÔNG có cả hai", "anthropic-beta" in fake.calls[0]["headers"]
	and than(fake.calls[0]).get("fallbacks") == "default" and "anthropic-beta" not in fake.calls[1]["headers"]
	and "fallbacks" not in than(fake.calls[1]))
c("… lượt sau giữ nguyên phần còn lại của yêu cầu", {k: v for k, v in than(fake.calls[0]).items() if k != "fallbacks"}
	== than(fake.calls[1]) and fake.calls[1]["headers"]["x-api-key"] == KEY)
c("… không ngủ (không phải retry do quá tải)", sl == [])
out, err, fake, sl = goi([loi(400, "invalid_request_error", "fallbacks: Extra inputs are not permitted"), ok()])
c("400 nhắc fallbacks → cũng gọi lại không kèm", err is None and len(fake.calls) == 2
	and "fallbacks" not in than(fake.calls[1]) and "anthropic-beta" not in fake.calls[1]["headers"])
out, err, fake, sl = goi([loi(400, "invalid_request_error", BETA400), loi(400, "invalid_request_error", BETA400), ok()])
c("gọi lại rồi vẫn 400 → http, chỉ gọi lại MỘT lần (2 lượt POST, kịch bản còn thừa 1)", err is not None
	and err.kind == "http" and len(fake.calls) == 2 and len(fake.script) == 1 and sl == [], (err, len(fake.calls)))
out, err, fake, sl = goi([loi(400, "invalid_request_error", BETA400), ok(model="claude-haiku-5-5")],
	model="claude-haiku-5-5")
c("model không gửi fallback mà gặp 400 nhắc anthropic-beta → http, không gọi lại", err is not None
	and err.kind == "http" and len(fake.calls) == 1)
out, err, fake, sl = goi([loi(400, "invalid_request_error", BETA400), loi(429, "rate_limit_error", "chậm lại"),
	loi(429, "rate_limit_error", "chậm lại"), ok()])
c("bỏ fallback không ăn vào số lần retry: 400 → 429 → 429 → 200 vẫn thành công (ngủ 5 s, 20 s)", err is None
	and len(fake.calls) == 4 and sl == [5, 20] and all("fallbacks" not in than(x) for x in fake.calls[1:]), (err, sl))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[5] Hết credit → credit, KHÔNG retry")
CREDIT = "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing."
for nhan, resp in (
		("402 billing_error", loi(402, "billing_error", "Billing problem")),
		("402 thân không phải JSON", FakeResp(402, "<html>Payment Required</html>")),
		("429 error.details.error_code = enforced_spend_limit_reached",
			loi(429, "rate_limit_error", "spend limit", error_code="enforced_spend_limit_reached")),
		("400 message chứa 'credit balance'", loi(400, "invalid_request_error", CREDIT))):
	out, err, fake, sl = goi([resp, ok()])
	c(f"{nhan} → credit, 1 lượt POST, không ngủ, không đụng lượt kế", err is not None and err.kind == "credit"
		and len(fake.calls) == 1 and len(fake.script) == 1 and sl == [], (err and err.kind, len(fake.calls), sl))
c("… trạng thái Run = het-credit", llm.run_status(err.kind) == "het-credit")
out, err, fake, sl = goi([loi(400, "invalid_request_error", "messages: roles must alternate"), ok()])
c("400 thường (không nhắc credit) → http chứ không phải credit", err.kind == "http" and len(fake.calls) == 1)
out, err, fake, sl = goi([loi(429, "rate_limit_error", "x", error_code="khac"), ok()])
c("429 có details nhưng mã khác → vẫn là giới hạn tốc độ (retry được)", err is None and len(fake.calls) == 2
	and sl == [5])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[6] Retry: tối đa 2 lần, chờ 5 s rồi 20 s — chỉ 429 / 5xx / 529 / timeout / lỗi nối")
RL = lambda: loi(429, "rate_limit_error", "Number of requests has exceeded your rate limit")  # noqa: E731
out, err, fake, sl = goi([RL(), RL(), RL(), ok()])
c("429 × 3 → rate sau 3 lượt POST (1 + 2 retry), ngủ [5, 20], không gọi lượt thứ 4", err is not None
	and err.kind == "rate" and len(fake.calls) == 3 and sl == [5, 20] and len(fake.script) == 1,
	(err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([RL(), ok()])
c("429 rồi 200 → thành công, ngủ [5]", err is None and out["data"] == GOOD and sl == [5] and len(fake.calls) == 2)
for status, etype in ((529, "overloaded_error"), (500, "api_error"), (503, "api_error")):
	out, err, fake, sl = goi([loi(status, etype, "Overloaded")] * 3 + [ok()])
	c(f"{status} × 3 → http sau 3 lượt, ngủ [5, 20]", err is not None and err.kind == "http" and len(fake.calls) == 3
		and sl == [5, 20], (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([loi(500, "api_error", "x"), loi(529, "overloaded_error", "x"), ok()])
c("500 → 529 → 200: thành công ở lượt thứ 3, ngủ [5, 20]", err is None and len(fake.calls) == 3 and sl == [5, 20])
E = real_requests.exceptions
for nhan, exc in (("ReadTimeout", E.ReadTimeout("read timed out")), ("ConnectTimeout", E.ConnectTimeout("x")),
		("ConnectionError", E.ConnectionError("Connection aborted")), ("ChunkedEncodingError", E.ChunkedEncodingError("x"))):
	out, err, fake, sl = goi([exc, exc, exc, ok()])
	c(f"{nhan} × 3 → timeout sau 3 lượt, ngủ [5, 20]", err is not None and err.kind == "timeout"
		and len(fake.calls) == 3 and sl == [5, 20], (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([E.ReadTimeout("x"), ok()])
c("timeout rồi 200 → thành công, ngủ [5]", err is None and sl == [5] and len(fake.calls) == 2)
for status, etype in ((401, "authentication_error"), (403, "permission_error"), (404, "not_found_error"),
		(400, "invalid_request_error"), (413, "request_too_large")):
	out, err, fake, sl = goi([loi(status, etype, "nope"), ok()])
	c(f"{status} → http, KHÔNG retry", err is not None and err.kind == "http" and len(fake.calls) == 1 and sl == []
		and f"HTTP {status}" in err.message, (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([FakeResp(200, "<html>proxy</html>"), ok()])
c("200 nhưng thân không phải JSON → http, không retry", err is not None and err.kind == "http" and len(fake.calls) == 1)
out, err, fake, sl = goi([E.InvalidURL("bad"), ok()])
c("lỗi gửi không phải lỗi nối (InvalidURL) → http, không retry", err.kind == "http" and len(fake.calls) == 1 and sl == [])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[7] stop_reason và đầu ra hỏng")
out, err, fake, sl = goi([ok(stop="refusal", content=[], usage={"input_tokens": 900, "output_tokens": 0},
	stop_details={"type": "refusal", "category": "cyber"}), ok()])
c("stop_reason refusal → LLMError refusal, không retry", err is not None and err.kind == "refusal"
	and len(fake.calls) == 1 and sl == [], err and err.kind)
c("… lỗi mang token đã tính tiền + model (900 / 0)", (err.tokens_in, err.tokens_out, err.model)
	== (900, 0, "claude-sonnet-5-5"), (err.tokens_in, err.tokens_out, err.model))
out, err, fake, sl = goi([ok(stop="refusal", text=json.dumps(GOOD))])
c("refusal mà content có JSON dở / đủ → vẫn refusal (xét stop_reason TRƯỚC khi đọc content)", err is not None
	and err.kind == "refusal")
out, err, fake, sl = goi([ok(stop="max_tokens", text='{"insights": [{"signal": "S1", "sev',
	usage={"input_tokens": 1000, "output_tokens": 16000}), ok()])
c("stop_reason max_tokens → schema, không retry", err is not None and err.kind == "schema" and len(fake.calls) == 1)
c("… lỗi mang token đã tính tiền (1000 / 16000)", (err.tokens_in, err.tokens_out) == (1000, 16000))
out, err, fake, sl = goi([ok(stop="max_tokens", text=json.dumps(GOOD))])
c("max_tokens mà JSON tình cờ parse được → vẫn schema (đầu ra có thể thiếu)", err is not None and err.kind == "schema")
for nhan, resp in (
		("text không phải JSON", ok(text="Xin lỗi, tôi không thể.")),
		("JSON là mảng, không phải object", ok(text="[1, 2]")),
		("không có khối text", ok(content=[{"type": "thinking", "thinking": ""}])),
		("content rỗng", ok(content=[])),
		("thiếu khoá bắt buộc (advice)", ok(data={"insights": [{k: v for k, v in GOOD["insights"][0].items()
			if k != "advice"}]})),
		("severity ngoài enum", ok(data={"insights": [{**GOOD["insights"][0], "severity": "xanh"}]})),
		("priority là chuỗi", ok(data={"insights": [{**GOOD["insights"][0], "priority": "5"}]})),
		("thừa khoá lạ", ok(data={"insights": [{**GOOD["insights"][0], "note": "x"}]})),
		("insights không phải mảng", ok(data={"insights": "không"})),
		("thiếu insights", ok(data={"ket_qua": []}))):
	out, err, fake, sl = goi([resp, ok()])
	c(f"{nhan} → schema, không retry", err is not None and err.kind == "schema" and len(fake.calls) == 1 and sl == [],
		(out, err and err.kind))
out, err, fake, sl = goi([ok(data={"insights": [{**GOOD["insights"][0], "severity": "xanh"}]},
	usage={"input_tokens": 700, "output_tokens": 80})])
c("sai schema: lỗi chỉ ra VỊ TRÍ, mang token (700 / 80), không chép giá trị", "$.insights[0].severity" in err.message
	and (err.tokens_in, err.tokens_out) == (700, 80) and "xanh" not in err.message, err.message)
out, err, fake, sl = goi([ok(text="BÍ MẬT-GÓI-SỐ 1.250.000")])
c("đầu ra không phải JSON: message không chép lời của mô hình", "BÍ MẬT" not in err.message
	and "1.250.000" not in err.message, err.message)
out, err, fake, sl = goi([ok(data={"insights": []})])
c("insights rỗng là hợp lệ", err is None and out["data"] == {"insights": []})
S = prompt.SCHEMA
c("schema_error: dữ liệu đúng → None", llm.schema_error(GOOD, S) is None)
c("schema_error: signal null hợp lệ, signal số thì sai", llm.schema_error({"insights": [{**GOOD["insights"][0],
	"signal": None}]}, S) is None and llm.schema_error({"insights": [{**GOOD["insights"][0], "signal": 3}]}, S)
	== "$.insights[0].signal")
c("schema_error: priority True (bool) không phải integer", llm.schema_error({"insights": [{**GOOD["insights"][0],
	"priority": True}]}, S) == "$.insights[0].priority")
c("schema_error: phần tử advice không phải chuỗi → chỉ đúng chỉ số", llm.schema_error({"insights": [GOOD["insights"][0],
	{**GOOD["insights"][1], "advice": ["a", 2]}]}, S) == "$.insights[1].advice[1]")

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[8] Khoá không lọt ra đâu cả")
del frappe.LOGGED[:]
THU = []   # mọi thứ thu được ở mục này → soát khoá một lượt ở cuối
out, err, fake, sl = goi([ok()])
c("kết quả thành công không chứa khoá", not lo_khoa(out, json.dumps(out, ensure_ascii=False)))
out, err, fake, sl = goi([E.InvalidHeader(f"Invalid leading whitespace, reserved character(s), or return "
	f"character(s) in header value: {KEY!r}"), ok()])
THU.append(err)
c("thư viện HTTP ném lỗi chứa khoá (InvalidHeader) → LLMError http, không retry", err is not None and err.kind == "http"
	and len(fake.calls) == 1, err)
c("… khoá không có trong str / repr / args / message", not lo_khoa(str(err), repr(err), err.args, err.message),
	repr(err))
c("… khoá không có trong vết lỗi; lỗi không kéo theo ngoại lệ gốc", not lo_khoa(vet(err)) and err.__context__ is None
	and err.__cause__ is None, vet(err))
# D6: lỗi gửi không phải lỗi mạng → chỉ ghi TÊN loại ngoại lệ (lời của nó có thể chép header mang khoá)
c("… message chỉ còn tên loại ngoại lệ (InvalidHeader), không chép lời của thư viện",
	err.message == "không gửi được yêu cầu (InvalidHeader)", err.message)
kh = khung_llm(err)
c("… vết lỗi chỉ còn MỘT khung của bc.ai.llm (hàm call của cửa) — không còn khung adapter", [k[0] for k in kh]
	== ["call"], [k[0] for k in kh])
c("… biến cục bộ trong vết: không khoá, không đề bài (system), không gói số (user), không schema",
	not lo_khoa(kh) and SYSTEM not in repr(kh) and "overdue_pct" not in repr(kh) and "tin_hieu" not in repr(kh)
	and not ({"system", "user", "schema", "key", "headers", "data"} & set(kh[0][1])), sorted(kh[0][1]))
exc = E.ConnectionError(f"HTTPSConnectionPool(host='api.anthropic.com'): Max retries exceeded (x-api-key: {KEY})")
out, err, fake, sl = goi([exc, exc, exc])
THU.append(err)
c("lỗi nối chứa khoá × 3 → timeout, khoá không lọt (message / vết lỗi)", err.kind == "timeout"
	and not lo_khoa(str(err), repr(err), err.args, vet(err)) and err.__context__ is None, repr(err))
out, err, fake, sl = goi([RuntimeError(f"bug nội bộ {KEY}")])
THU.append(err)
c("ngoại lệ bất kỳ chứa khoá → LLMError http, khoá không lọt", err.kind == "http"
	and not lo_khoa(str(err), repr(err), vet(err)) and err.__context__ is None, repr(err))
out, err, fake, sl = goi([loi(401, "authentication_error", f"invalid x-api-key: {KEY}")])
THU.append(err)
c("API chép lại khoá trong thân lỗi (401) → message đã xoá khoá", err.kind == "http" and not lo_khoa(str(err), repr(err))
	and "***" in err.message and "authentication_error" in err.message, err.message)
out, err, fake, sl = goi([FakeResp(403, f"<html>Forbidden for key {KEY}</html>")])
THU.append(err)
c("thân lỗi không phải JSON chứa khoá → đã xoá", err.kind == "http" and not lo_khoa(str(err), repr(err)), err.message)
# Khoá nằm vắt qua mốc 300 ký tự: "HTTP 401 authentication_error: " dài 31 ký tự + 262 chữ x = 293 → khoá bắt đầu ở
# ký tự 294. Cắt TRƯỚC rồi mới xoá thì 7 ký tự đầu của khoá ("KHOA/bi") lọt; đúng: xoá trước → "…xxx***" dài 296.
out, err, fake, sl = goi([loi(401, "authentication_error", "x" * 262 + KEY + " đuôi" * 50)])
THU.append(err)
c("message cắt 300 ký tự SAU khi xoá khoá (khoá vắt qua mốc 300 không lọt nửa đầu)", len(err.message) == 300
	and "KHOA" not in err.message and err.message[293:296] == "***", (len(err.message), err.message[280:]))
out, err, fake, sl = goi([loi(400, "invalid_request_error", "y" * 5000)])
c("message dài → đúng 300 ký tự", len(err.message) == 300 and len(str(err)) == 300)
real_dispatch = anthropic._request


def _no(*a, **k):
	raise RuntimeError(f"hỏng khi dựng yêu cầu {KEY} / {a[0]}")


anthropic._request = _no
out, err, fake, sl = goi([ok()])
anthropic._request = real_dispatch
THU.append(err)
c("lỗi lập trình trong adapter (không phải LLMError) → cửa bọc thành LLMError http, khoá không lọt, không kéo ngoại "
	"lệ gốc", err is not None and err.kind == "http" and not lo_khoa(str(err), repr(err), vet(err))
	and err.__context__ is None and err.__cause__ is None, repr(err))
c("… message nêu loại lỗi + nơi lỗi [file:dòng] để lần ra (vết bên trong đã bỏ)", "RuntimeError" in err.message
	and "[test_ai_llm.py:" in err.message, err.message)
c("… vết lỗi không còn khung adapter, biến cục bộ sạch", [k[0] for k in khung_llm(err)] == ["call"]
	and not lo_khoa(khung_llm(err)) and "overdue_pct" not in repr(khung_llm(err)))
e2 = llm.LLMError("http", f"tự tạo: {KEY} và {OKEY} và {SK}")
c("LLMError tạo ở bất kỳ đâu cũng tự xoá khoá (cả hai provider + mẫu sk-…)", not lo_khoa(str(e2), e2.message, e2.args)
	and SK not in e2.message and e2.message == "tự tạo: *** và *** và ***", e2.message)
c("clean(): xoá khoá claude, khoá openai, chuỗi dạng sk-…; giữ phần còn lại", llm.clean(f"a {KEY} b {OKEY} c {SK} d")
	== "a *** b *** c *** d", llm.clean(f"a {KEY} b {OKEY} c {SK} d"))
c("clean(): None → '', cắt 300", llm.clean(None) == "" and len(llm.clean("z" * 999)) == 300)
import pickle  # noqa: E402
e3 = pickle.loads(pickle.dumps(llm.LLMError("credit", "hết tiền")))
c("LLMError qua pickle (job nền) giữ đúng kind + message", (e3.kind, e3.message, str(e3)) == ("credit", "hết tiền",
	"hết tiền"), (e3.kind, e3.message))
c("clean(): không bắt nhầm chữ thường có 'sk-' ở giữa (task-budgets…, risk-adjusted…)",
	llm.clean("beta task-budgets-2026-03-13 / risk-adjusted-return") == "beta task-budgets-2026-03-13 / risk-adjusted-return")
c("clean(): khoá dạng sk-… đứng sau dấu : ' \" = đều bị xoá", llm.clean(f"x-api-key:{SK} '{SK}' key={SK}")
	== "x-api-key:*** '***' key=***", llm.clean(f"x-api-key:{SK} '{SK}' key={SK}"))
frappe.conf["bc_ai_anthropic_key"] = f" {KEY}\n"
c("clean(): khoá khai thừa dấu cách — dạng đã gọt cũng bị xoá", llm.clean(f"k={KEY};") == "k=***;", llm.clean(f"k={KEY};"))
frappe.conf["bc_ai_anthropic_key"] = KEY
sach = True
for e in THU + [goi([ok(stop="refusal", content=[])])[1], goi([ok(text="không phải JSON")])[1],
		goi([ok(data={"insights": "sai"})])[1], goi([loi(402, "billing_error", "x")])[1]]:
	kh = khung_llm(e)
	if [k[0] for k in kh] != ["call"] or lo_khoa(kh) or "overdue_pct" in repr(kh) or SYSTEM in repr(kh):
		sach = False
		print("    lộ:", e.kind, [k[0] for k in kh])
c("mọi loại LLMError ra khỏi cửa (mạng, 401, 402, từ chối, sai JSON, sai schema): vết chỉ có khung call, biến sạch", sach)
c("không lời gọi frappe.log_error nào mang khoá", not lo_khoa(frappe.LOGGED), frappe.LOGGED)
c("không ngoại lệ nào thu được ở mục này mang khoá (kể cả thuộc tính)", not lo_khoa(*[vars(x) for x in THU]))
bien = {f"{m.__name__}.{k}": v for m in (llm, anthropic, budget, prompt) for k, v in vars(m).items()
	if k != "requests" and not k.startswith("__") and not callable(v) and not isinstance(v, type(os))}
c("không biến cấp module nào giữ khoá sau các lượt gọi", not lo_khoa(*bien.values()),
	[k for k, v in bien.items() if lo_khoa(v)])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[9] Bộ thử không thể ra mạng")
truoc = len(BLOCKED)
toi_noi = True
try:
	real_requests.post("https://api.anthropic.com/v1/messages", data=b"{}", timeout=3)
except Exception:
	toi_noi = False
c("requests THẬT bị chặn ở tầng socket (ném lỗi, có ghi nhận lượt chặn)", not toi_noi and len(BLOCKED) > truoc, BLOCKED[-3:])
truoc = len(BLOCKED)
try:
	socket.create_connection(("93.184.216.34", 443), timeout=2).close()
	toi_noi = True
except OSError:
	toi_noi = False
c("nối thẳng bằng IP (không qua DNS) cũng bị chặn", not toi_noi and len(BLOCKED) > truoc)
out, err, fake, sl = goi([])
c("bản giả hết kịch bản mà bị gọi → ném lỗi + đếm (lời gọi ngoài ý muốn không trôi qua im lặng)",
	fake.unexpected == 1 and err is not None and err.kind == "http", (fake.unexpected, err))
c("cả bộ thử: bẫy đặt từ đầu chưa hề bị chạm", BAY.unexpected == 0 and BAY.calls == [])
c("ngủ luôn là bản giả (không lượt nào ngủ thật)", anthropic.sleep == SLEEPS.append)
src = {f: open(os.path.join(BC_ROOT, "bc", "ai", *f.split("/")), encoding="utf-8").read()
	for f in ("llm/__init__.py", "llm/anthropic.py", "budget.py", "prompt.py")}


def imports(code):
	out = set()
	for n in ast.walk(ast.parse(code)):
		if isinstance(n, ast.Import):
			out |= {a.name.split(".")[0] for a in n.names}
		elif isinstance(n, ast.ImportFrom):
			out.add((n.module or "").split(".")[0])
	return out


c("AST: chỉ llm/anthropic.py import requests", "requests" in imports(src["llm/anthropic.py"])
	and all("requests" not in imports(src[f]) for f in ("llm/__init__.py", "budget.py", "prompt.py")))
c("AST: không module nào dùng urllib / http.client / socket / httpx để lách",
	not any({"urllib", "urllib3", "http", "socket", "httpx", "aiohttp"} & imports(s) for s in src.values()))
c("budget.py / prompt.py không đọc frappe.conf / site_config, không nhắc tên khoá", all(".conf" not in src[f]
	and "bc_ai_" not in src[f] and "site_config" not in src[f] for f in ("budget.py", "prompt.py")))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[10] Chi phí, giá theo đúng tên model")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [
	{"model": "claude-sonnet-5-5", "price_in": 2, "price_out": 10},
	{"model": " claude-opus-5-5 ", "price_in": 4, "price_out": 20},
	{"model": "chua-khai", "price_in": 0, "price_out": 0},
	{"model": "chi-ra", "price_in": 0, "price_out": 7.5},
	{"model": "le", "price_in": 0.25, "price_out": 0},
	{"model": "trung", "price_in": 1, "price_out": 1},
	{"model": "trung", "price_in": 3, "price_out": 5}])
c("price_of đúng tên → (2, 10)", budget.price_of("claude-sonnet-5-5") == (2.0, 10.0), budget.price_of("claude-sonnet-5-5"))
c("price_of: dấu cách thừa trong ô tên vẫn khớp", budget.price_of("claude-opus-5-5") == (4.0, 20.0))
c("price_of: tên gần giống / khác hoa thường / có hậu tố ngày → None (đúng tên mới tính)",
	[budget.price_of(m) for m in ("claude-sonnet-5", "Claude-Sonnet-5-5", "claude-sonnet-5-5-20261101", "sonnet")]
	== [None] * 4)
c("price_of: dòng giá 0/0 = chưa khai; tên rỗng / None → None", budget.price_of("chua-khai") is None
	and budget.price_of("") is None and budget.price_of(None) is None)
c("price_of: chỉ khai một chiều giá vẫn là đã khai", budget.price_of("chi-ra") == (0.0, 7.5))
c("price_of: khai trùng → dòng sau thắng", budget.price_of("trung") == (3.0, 5.0))
# (12 345 × 2 + 6 789 × 10) / 1 000 000 = (24 690 + 67 890) / 1e6 = 0,09258
c("cost sonnet 12 345 vào / 6 789 ra = 0,09258 USD", budget.cost("claude-sonnet-5-5", 12345, 6789) == 0.09258,
	budget.cost("claude-sonnet-5-5", 12345, 6789))
# 1 000 000 × 4 / 1e6 + 500 000 × 20 / 1e6 = 4 + 10 = 14
c("cost opus 1 triệu vào / 500 nghìn ra = 14 USD", budget.cost("claude-opus-5-5", 1_000_000, 500_000) == 14.0)
# 2 000 × 7,5 / 1e6 = 0,015
c("cost chỉ có giá ra: 1 000 vào / 2 000 ra = 0,015", budget.cost("chi-ra", 1000, 2000) == 0.015)
c("cost model lạ → None; model giá 0/0 → None (chưa khai giá, KHÔNG phải 0)", budget.cost("la", 1000, 1000) is None
	and budget.cost("chua-khai", 1000, 1000) is None)
c("cost model đã khai, 0 token → 0.0 (không phải None)", budget.cost("claude-sonnet-5-5", 0, 0) == 0.0
	and budget.cost("claude-sonnet-5-5", 0, 0) is not None)
# 1 × 2 / 1e6 = 0,000002 ; 3 × 0,25 / 1e6 = 0,00000075 → làm tròn 6 số lẻ = 0,000001
c("cost làm tròn 6 số lẻ", budget.cost("claude-sonnet-5-5", 1, 0) == 0.000002 and budget.cost("le", 3, 0) == 0.000001,
	(budget.cost("claude-sonnet-5-5", 1, 0), budget.cost("le", 3, 0)))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[11] Kỳ credit")
D = datetime.date
c("chưa đặt ngày kỳ → mặc định ngày 1: 27/10 → 1/10", budget.cycle_start("claude") == D(2026, 10, 1),
	budget.cycle_start("claude"))
c("… hôm nay đúng ngày 1 → chính hôm nay", budget.cycle_start("claude", "2026-10-01") == D(2026, 10, 1))
single("BC Settings", ai_cycle_day_claude=15, ai_cycle_day_openai=31)
c("ngày kỳ 15, hôm nay 27/10 → 15/10", budget.cycle_start("claude") == D(2026, 10, 15), budget.cycle_start("claude"))
c("ngày kỳ 15, hôm nay ĐÚNG 15/10 → 15/10 (kỳ mới bắt đầu từ hôm nay)", budget.cycle_start("claude", "2026-10-15")
	== D(2026, 10, 15))
c("ngày kỳ 15, hôm nay 14/10 (chưa tới ngày kỳ) → 15/9 tháng trước", budget.cycle_start("claude", D(2026, 10, 14))
	== D(2026, 9, 15), budget.cycle_start("claude", D(2026, 10, 14)))
c("ngày kỳ 15, hôm nay 10/1/2026 → 15/12/2025 (lùi qua năm)", budget.cycle_start("claude", "2026-01-10")
	== D(2025, 12, 15))
c("nhận cả datetime", budget.cycle_start("claude", datetime.datetime(2026, 10, 27, 23, 59)) == D(2026, 10, 15))
# openai ngày kỳ 31: tháng 11 có 30 ngày → ngày kỳ của tháng 11 là 30/11
c("ngày kỳ 31, hôm nay 30/11 → 30/11 (tháng 30 ngày: ngày cuối tháng)", budget.cycle_start("openai", "2026-11-30")
	== D(2026, 11, 30), budget.cycle_start("openai", "2026-11-30"))
c("ngày kỳ 31, hôm nay 29/11 → 31/10", budget.cycle_start("openai", "2026-11-29") == D(2026, 10, 31))
c("ngày kỳ 31, hôm nay 1/3/2026 → 28/2/2026 (tháng trước ngắn hơn)", budget.cycle_start("openai", "2026-03-01")
	== D(2026, 2, 28), budget.cycle_start("openai", "2026-03-01"))
c("ngày kỳ 31, hôm nay 5/3/2028 → 29/2/2028 (năm nhuận)", budget.cycle_start("openai", "2028-03-05") == D(2028, 2, 29))
c("ngày kỳ 31, hôm nay 31/12 → 31/12", budget.cycle_start("openai", "2026-12-31") == D(2026, 12, 31))
single("BC Settings", ai_cycle_day_openai=30)
c("ngày kỳ 30, hôm nay 28/2/2026 → 28/2 (đã tới ngày cuối tháng 2)", budget.cycle_start("openai", "2026-02-28")
	== D(2026, 2, 28))
c("ngày kỳ 30, hôm nay 27/2/2026 → 30/1", budget.cycle_start("openai", "2026-02-27") == D(2026, 1, 30))
single("BC Settings", ai_cycle_day_openai=0)
c("ngày kỳ 0 → coi như 1", budget.cycle_start("openai") == D(2026, 10, 1))
single("BC Settings", ai_cycle_day_openai=45)
c("ngày kỳ 45 → ngày cuối tháng (27/10 → 30/9)", budget.cycle_start("openai") == D(2026, 9, 30), budget.cycle_start("openai"))
single("BC Settings", ai_cycle_day_openai=1)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[12] Trần mềm: trống → 90, đặt 0 → chặn")
co_dong = frappe.db.sql("SELECT COUNT(*) FROM `tabSingles` WHERE doctype = 'BC Settings' AND field LIKE 'ai_cap%%'")[0][0]
c("(tiền đề) chưa có dòng ai_cap_* nào trong tabSingles; doc đọc ra 0.0", co_dong == 0
	and frappe.get_cached_doc("BC Settings").get("ai_cap_claude_usd") == 0.0)
c("chưa từng đặt trần → 90 USD (không phải 0)", budget.cap("claude") == 90.0 and budget.cap("openai") == 90.0,
	budget.cap("claude"))
c("… chưa chi gì, chưa gọi lượt nào → được gọi", budget.can_call("claude") == (True, ""), budget.can_call("claude"))
single("BC Settings", ai_cap_claude_usd=0)
c("đặt trần 0 → cap = 0", budget.cap("claude") == 0.0, budget.cap("claude"))
c("… trần 0 chặn mọi lượt gọi dù chưa chi đồng nào (vuot-tran)", budget.spent("claude") == 0.0
	and budget.can_call("claude") == (False, "vuot-tran"), budget.can_call("claude"))
c("… provider kia không bị ảnh hưởng", budget.can_call("openai") == (True, ""))
single("BC Settings", ai_cap_claude_usd="0.0")
c("trần lưu dạng '0.0' (Frappe ghi Float) → vẫn là 0, vẫn chặn", budget.cap("claude") == 0.0
	and budget.can_call("claude")[0] is False)
single("BC Settings", ai_cap_claude_usd="")
c("ô trần là chuỗi rỗng → 90", budget.cap("claude") == 90.0)
single("BC Settings", ai_cap_claude_usd=None)
c("ô trần NULL → 90", budget.cap("claude") == 90.0)
single("BC Settings", ai_cap_claude_usd=-5)
c("trần âm → 0 (chặn)", budget.cap("claude") == 0.0)
single("BC Settings", ai_cap_claude_usd=25.5)
c("trần 25,5 → 25,5", budget.cap("claude") == 25.5)
frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'ai_cap_claude_usd'")

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[13] Đã chi trong kỳ, số lượt gọi hôm nay")


def run(started, cost=0, provider="claude", step="kinh-doanh", status="ok"):
	return insert("BC AI Run", provider=provider, step=step, status=status, started=started, cost_usd=cost,
		run_type="ngay")


# Kỳ claude bắt đầu 15/10 (ngày kỳ 15, hôm nay 27/10); openai ngày kỳ 1 → 1/10.
run("2026-10-15 00:00:00", 1.25)                       # đúng 0 giờ ngày đầu kỳ → tính
run("2026-10-14 23:59:59", 100)                        # kỳ trước → không
run("2026-10-27 05:31:00", 0.75)                       # hôm nay → tính (cũng là 1 lượt gọi hôm nay)
run("2026-10-20 05:31:00", 50, provider="openai", step="review")   # provider khác → không vào claude
run("2026-10-20 05:30:00", 9, provider=None, step="tong")          # dòng tổng không provider → không
run("2026-10-28 00:00:00", 7)                          # ngày mai → không ("đến nay")
run("2026-10-20 08:00:00", 0.123456)                   # → tính
# claude: 1,25 + 0,75 + 0,123456 = 2,123456
c("spent claude trong kỳ 15/10 → 27/10 = 2,123456", abs(budget.spent("claude") - 2.123456) < 1e-9, budget.spent("claude"))
c("spent openai (kỳ từ 1/10) = 50", abs(budget.spent("openai") - 50.0) < 1e-9, budget.spent("openai"))
# hôm nay = 14/10 → kỳ 15/9 → 14/10: chỉ có dòng 14/10 23:59:59 (100)
c("spent claude tính tại 14/10 (kỳ trước) = 100", abs(budget.spent("claude", "2026-10-14") - 100.0) < 1e-9,
	budget.spent("claude", "2026-10-14"))
# hôm nay = 28/10: thêm dòng 28/10 00:00 (7) → 2,123456 + 7 = 9,123456
c("spent claude tính tại 28/10 = 9,123456", abs(budget.spent("claude", "2026-10-28") - 9.123456) < 1e-9)
c("spent provider chưa có dòng nào = 0.0 (float)", budget.spent("khac") == 0.0 and isinstance(budget.spent("khac"), float))

run("2026-10-27 05:30:00", step="tong")                                  # dòng tổng → không đếm
run("2026-10-27 05:30:01", step="ai", status="vuot-tran")                # bước AI bị bỏ → không
run("2026-10-27 05:32:00", step="kho-sx", status="loi")                  # đã gọi mạng, lỗi → đếm
run("2026-10-27 05:33:00", step="tai-chinh", status="het-credit")        # đã gọi mạng → đếm
run("2026-10-27 05:34:00", step="nhan-su", status="khong-khoa")          # chưa gọi → không
run("2026-10-27 05:35:00", step="attp", status="tat")                    # chưa gọi → không
run("2026-10-27 05:36:00", step="ai", status="ok")                       # step "ai" → không
run("2026-10-27 00:00:00", step="thu", status="ok")                      # thử kết nối, đúng 0 giờ → đếm
run("2026-10-26 23:59:59", step="kinh-doanh", status="ok")               # hôm qua → không
run("2026-10-27 09:00:00", provider="openai", step="review")             # provider khác
run("2026-10-27 09:01:00", step=None, status="ok")                       # step trống, đã gọi → đếm
run("2026-10-27 09:02:00", step="kinh-doanh", status="vuot-tran")        # trạng thái không gọi mạng → không
# claude hôm nay: 05:31 (ok) + kho-sx (loi) + tai-chinh (het-credit) + thu (00:00) + step trống = 5
c("calls_today claude = 5", budget.calls_today("claude") == 5, budget.calls_today("claude"))
c("calls_today openai = 1", budget.calls_today("openai") == 1, budget.calls_today("openai"))
# 26/10: chỉ dòng 23:59:59 ; 28/10: dòng 00:00 ; 20/10: dòng 08:00 (dòng tổng 05:30 không provider)
c("calls_today theo ngày truyền vào: 26/10 = 1, 28/10 = 1, 20/10 = 1, 25/10 = 0",
	[budget.calls_today("claude", d) for d in ("2026-10-26", "2026-10-28", "2026-10-20", "2026-10-25")] == [1, 1, 1, 0],
	[budget.calls_today("claude", d) for d in ("2026-10-26", "2026-10-28", "2026-10-20", "2026-10-25")])
c("MAX_CALLS_PER_DAY = 30, DEFAULT_CAP_USD = 90", budget.MAX_CALLS_PER_DAY == 30 and budget.DEFAULT_CAP_USD == 90.0)
c("can_call: chi 2,12 < trần 90, 5 lượt < 30 → được", budget.can_call("claude") == (True, ""), budget.can_call("claude"))
single("BC Settings", ai_cap_claude_usd=2.123456)
c("đã chi ĐÚNG BẰNG trần (2,123456) → vuot-tran", budget.can_call("claude") == (False, "vuot-tran"))
single("BC Settings", ai_cap_claude_usd=2.123457)
c("trần nhỉnh hơn đã chi 0,000001 → vẫn được gọi", budget.can_call("claude") == (True, ""))
single("BC Settings", ai_cap_claude_usd=2)
c("đã chi vượt trần (2,12 > 2) → vuot-tran", budget.can_call("claude") == (False, "vuot-tran"))
c("… nhưng tính tại 14/10 thì kỳ trước đã chi 100 > 2 → cũng vuot-tran; openai (50 < 90) → được",
	budget.can_call("claude", "2026-10-14") == (False, "vuot-tran") and budget.can_call("openai") == (True, ""))
single("BC Settings", ai_cap_claude_usd=50)
# trần 50: kỳ này mới chi 2,12 → được; tính tại 14/10 (kỳ trước đã chi 100) → vượt
c("can_call tính theo ngày truyền vào: hôm nay được (2,12 < 50), tại 14/10 vượt (100 ≥ 50)",
	budget.can_call("claude") == (True, "") and budget.can_call("claude", "2026-10-14") == (False, "vuot-tran"),
	(budget.can_call("claude"), budget.can_call("claude", "2026-10-14")))
frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'ai_cap_claude_usd'")
for i in range(24):   # 5 + 24 = 29 lượt, model chưa khai giá nên cost 0
	run(f"2026-10-27 10:{i:02d}:00", step="kinh-doanh", status="ok")
c("29 lượt hôm nay → còn được gọi", budget.calls_today("claude") == 29 and budget.can_call("claude") == (True, ""),
	budget.calls_today("claude"))
run("2026-10-27 11:00:00", step="kinh-doanh", status="loi")
c("30 lượt hôm nay → qua-so-luot (kể cả khi chi phí = 0 vì chưa khai giá)", budget.calls_today("claude") == 30
	and budget.can_call("claude") == (False, "qua-so-luot"), budget.can_call("claude"))
c("… sang ngày 28/10 lại được gọi (1 lượt)", budget.can_call("claude", "2026-10-28") == (True, ""))
single("BC Settings", ai_cap_claude_usd=1)
c("vừa vượt trần vừa quá số lượt → báo vuot-tran trước", budget.can_call("claude") == (False, "vuot-tran"))
frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'ai_cap_claude_usd'")

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[14] Schema đầu ra")
c("SCHEMA_NAME", prompt.SCHEMA_NAME == "ghi_nhan_dinh")
c("SCHEMA đúng hình dạng đặc tả §5.3", prompt.SCHEMA == {
	"type": "object", "additionalProperties": False, "required": ["insights"],
	"properties": {"insights": {"type": "array", "items": {
		"type": "object", "additionalProperties": False,
		"required": ["signal", "severity", "priority", "title", "body", "advice"],
		"properties": {
			"signal": {"anyOf": [{"type": "string"}, {"type": "null"}]},
			"severity": {"type": "string", "enum": ["do", "vang"]},
			"priority": {"type": "integer"},
			"title": {"type": "string"}, "body": {"type": "string"},
			"advice": {"type": "array", "items": {"type": "string"}}}}}}}, prompt.SCHEMA)
CAM = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength", "pattern",
	"minItems", "maxItems", "uniqueItems", "contains", "minProperties", "maxProperties", "patternProperties", "$ref"}
vi_pham = []


def soat(s, path="$"):
	if isinstance(s, dict):
		if CAM & set(s):
			vi_pham.append(f"{path}: từ khoá cấm {CAM & set(s)}")
		if s.get("type") == "object":
			if s.get("additionalProperties") is not False:
				vi_pham.append(f"{path}: thiếu additionalProperties false")
			if sorted(s.get("required") or []) != sorted(s.get("properties") or {}):
				vi_pham.append(f"{path}: required không đủ mọi khoá")
		if isinstance(s.get("type"), list):
			vi_pham.append(f"{path}: type dạng danh sách")
		for k, v in s.items():
			soat(v, f"{path}.{k}")
	elif isinstance(s, list):
		for i, v in enumerate(s):
			soat(v, f"{path}[{i}]")


soat(prompt.SCHEMA)
c("giới hạn structured outputs: mọi object additionalProperties false + required đủ; không min / max / ràng buộc mảng",
	vi_pham == [], vi_pham)
c("schema tuần tự hoá JSON được", json.loads(json.dumps(prompt.SCHEMA)) == prompt.SCHEMA)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[15] System prompt")
single("BC Settings", ai_context="Công ty bán bánh đậu xanh; cao điểm là mùa Tết.", ai_cap_openai_usd=77.77)
run("2026-10-27 12:00:00", 4321.5, provider="openai", step="review")
p = prompt.system_prompt()
c("tiếng Việt, có vai trò", p.startswith("Bạn là trợ lý phân tích số liệu cho Ban lãnh đạo công ty."))
c("nhóm he-thong: người đọc là quản trị", 'nhóm "he-thong"' in p and "khuyến nghị giao cho quản trị" in p)
for nhan, manh in (
		("luật 1: tiêu đề ≤ 12 từ, nội dung ≤ 60 từ, cái gì / bao nhiêu / vì sao", ["không quá 12 từ", "không quá 60 từ",
			"cái gì, bao \nhiêu, vì sao đáng quan tâm".replace("\n", "n")]),
		("luật 2: 1–3 khuyến nghị theo BỘ PHẬN, không tên người", ["1–3 khuyến nghị", "giao theo BỘ PHẬN",
			"không nêu tên người"]),
		("luật 3: mọi số bằng placeholder, 5 kiểu, cấm tự viết / tự tính / tự làm tròn, thời hạn được viết thường",
			["Mọi số liệu viết bằng placeholder {{path|kiểu}}", "tien | so | pct | ngay | chu",
				"Cấm tự viết, tự tính, tự làm tròn số liệu", '("trong 7 ngày") được viết thường']),
		("luật 4: nguyên nhân không có trong số liệu → 'cần kiểm tra: …'", ["Nguyên nhân không có trong số liệu",
			'"cần kiểm tra: …"', "không khẳng định"]),
		("luật 5: dang-xu-ly / kéo dài → nói tiến triển", ['"dang-xu-ly"', "kéo dài nhiều ngày", "tốt lên / xấu đi",
			"không báo như việc mới"]),
		("luật 6: tối đa 3 nhận định thêm, không có thì để trống", ["tối đa 3 nhận định ngoài danh sách tín hiệu",
			"Không có thì để trống", "Không viết cho đủ số lượng"]),
		("luật 7: giọng ngắn, thẳng, không thuật ngữ khó, không cảm thán", ["ngắn, thẳng",
			"không thuật ngữ kế toán khó", "không cảm thán"])):
	c(nhan, all(m in p for m in manh), [m for m in manh if m not in p])
c("đủ 7 luật đánh số 1–7, đúng thứ tự", [p.index(f"\n{i}. ") for i in range(1, 8)] == sorted(p.index(f"\n{i}. ")
	for i in range(1, 8)) and "\n8. " not in p)
from bc.ai import registry  # noqa: E402
c("cú pháp placeholder + MỘT ví dụ mẫu dùng đúng cú pháp của registry", registry.placeholders(p)
	== [("cong-no.receivables.kpis.overdue_pct", "pct"), ("cong-no.receivables.top_overdue[0].overdue", "tien")],
	registry.placeholders(p))
c("giải thích path (dấu chấm, [chỉ số] từ 0) và việc không viết thêm đơn vị", "nối nhau bằng dấu chấm" in p
	and "đếm từ 0" in p and "Không viết thêm đơn vị sau placeholder" in p)
c("giải thích đầu ra: signal / severity / priority / title / body / advice", all(f'"{k}"' in p for k in
	("signal", "severity", "priority", "title", "body", "advice")))
c("dặn về mã giả KH# / NCC# (viết dạng chữ KH#… / NCC#…) và khối _cat", "KH#…" in p and "NCC#…" in p
	and '"_cat"' in p)
# D4: ví dụ trong đề bài không được là một mã có thể hợp lệ (mô hình chép lại → thành tên một khách có thật)
c("[S4] system prompt không chứa mã giả nào có chữ số (KH#<số> / NCC#<số>)",
	not re.search(r"(?:KH|NCC)\s*#\s*\d", p), re.findall(r"(?:KH|NCC)\s*#\s*\S{0,6}", p))
# D8: luật kiểu số theo "kieu" (không thêm chữ số nào — bộ kiểm chữ số ở trên vẫn đúng)
c("[N2] system prompt: giải thích \"kieu\" (path không kèm [chỉ số]) và luật kiểu phải đúng như \"kieu\" ghi",
	'- "kieu" (nếu có): {path: kiểu}' in p and "path viết không kèm [chỉ số]" in p
	and 'có trong "kieu" thì kiểu phải đúng y như "kieu" ghi' in p and "Sai kiểu sẽ bị loại" in p)
# Hai lời dặn khớp bộ kiểm số trần của máy chủ (bc.ai.render): tên có chữ số viết tay và số viết bằng chữ đều bị loại.
c("dặn tên riêng có chữ số (mặt hàng ghi khối lượng, mã chứng từ) phải đưa vào bằng placeholder kiểu chu",
	"Tên riêng có chữ số" in p and "cũng phải đưa vào bằng placeholder kiểu chu — viết tay sẽ bị loại" in p)
c("dặn không viết số bằng chữ, không tự suy tỷ lệ / bội số; số viết thường chỉ cho thời hạn / thứ tự, ≤ hai chữ số",
	"Không viết con số bằng chữ, không tự suy ra tỷ lệ hay bội số" in p and '"gấp đôi"' in p and '"một nửa"' in p
	and "Số viết thường chỉ dùng cho thời hạn hoặc thứ tự, tối đa hai chữ số" in p)
c("dữ liệu không phải chỉ dẫn", "không phải chỉ dẫn" in p)
c("có bối cảnh do quản trị viết (ai_context)", "BỐI CẢNH CÔNG TY (do quản trị viết):\nCông ty bán bánh đậu xanh; cao "
	"điểm là mùa Tết." in p)
c("hôm nay 27/10/2026", "- Hôm nay: 27/10/2026." in p)
# Năm TC bắt đầu tháng 5: 27/10/2026 thuộc 1/5/2026 → 30/4/2027; cùng kỳ: 1/5/2025 → 27/10/2025
c("năm tài chính + cùng kỳ", "- Năm tài chính: 1/5/2026 → 30/4/2027; số luỹ kế tính đến 27/10/2026; cùng kỳ năm trước: "
	"1/5/2025 → 27/10/2025." in p, p[-400:])
# 27/10/2026 < đầu mùa 1/11/2026 → giữa hai mùa: Tết vừa qua = 2026 (17/2/2026); Tết tới 6/2/2027
c("mùa Tết: giữa hai mùa → kết quả Tết 2026, Tết tới 6/2/2027", "- Mùa Tết: đang ở giữa hai mùa — số hàng Tết là kết "
	"quả đã chốt của Tết 2026 (mùng 1: 17/2/2026); Tết tới: 6/2/2027." in p, p[-300:])
p2 = prompt.system_prompt("2026-12-01")
c("1/12/2026: đang trong mùa Tết 2027 (1/11/2026 → 6/2/2027)", "- Mùa Tết 2027: đang trong mùa, từ 1/11/2026 đến mùng "
	"1 Tết (6/2/2027)." in p2 and "- Hôm nay: 1/12/2026." in p2 and "tính đến 1/12/2026; cùng kỳ năm trước: 1/5/2025 → "
	"1/12/2025." in p2, p2[-400:])
p3 = prompt.system_prompt(D(2027, 2, 20))
c("20/2/2027: mùa Tết 2027 đã kết thúc (mùng 1 là 6/2/2027)", "- Mùa Tết 2027: đã kết thúc ở mùng 1 Tết (6/2/2027) — "
	"số hàng Tết đã chốt." in p3 and "1/5/2026 → 30/4/2027; số luỹ kế tính đến 20/2/2027; cùng kỳ năm trước: 1/5/2025 → "
	"20/2/2026." in p3, p3[-400:])
# Không số liệu kinh doanh: ngoài khối mốc thời gian + bối cảnh, chữ số chỉ thuộc luật / cú pháp.
than_luat = p.split("BỐI CẢNH CÔNG TY")[0]

so = set(re.findall(r"\d+", than_luat))
# 1–7: số thứ tự luật, S1 / S2, 1–3 khuyến nghị, tối đa 3, trong 7 ngày, [0] / đếm từ 0, 1 đến 5, luật 6; 12 / 60 từ;
# KH#0001 / NCC#0001
c("phần luật chỉ chứa chữ số của luật / cú pháp (không số liệu kinh doanh)", so <= {"0", "1", "2", "3", "4", "5", "6",
	"7", "12", "60", "0001"}, so)
moc = p.split("MỐC THỜI GIAN:")[1]
# bỏ ngày d/m/yyyy, "Tết <năm>", "mùng 1" → không còn chữ số nào
con = re.sub(r"\d{1,2}/\d{1,2}/\d{4}|Tết \d{4}|mùng 1", "", moc)
c("khối mốc thời gian chỉ có ngày tháng", len(con.strip()) > 50 and not re.search(r"\d", con), con)
c("không chứa trần chi / chi phí / giá model / khoá", all(x not in p for x in ("77.77", "77,77", "4321", "USD", "90",
	KEY, OKEY)))
single("BC Settings", ai_context="   ")
c("ai_context trống → không có mục bối cảnh", "BỐI CẢNH CÔNG TY" not in prompt.system_prompt())
single("BC Settings", ai_context="a" * 5000)
c("ai_context dài 5000 → cắt 4000 ký tự", prompt.system_prompt().count("a" * 4000) == 1
	and "a" * 4001 not in prompt.system_prompt())
single("BC Settings", ai_context="Công ty bán bánh đậu xanh.")
frappe.db.sql("DELETE FROM `tabBC Tet Date`")
p4 = None
try:
	p4 = prompt.system_prompt()
except Exception as e:  # noqa: BLE001
	p4 = None
	print("   ", repr(e))
c("thiếu ngày Tết trong BC Settings → không lỗi, bỏ dòng mùa Tết, các mốc khác còn nguyên", p4 is not None
	and "Mùa Tết" not in p4 and "- Hôm nay: 27/10/2026." in p4 and "- Năm tài chính: 1/5/2026" in p4)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[16] truncate: danh sách > 30 → 30 + _cat ở dict cha")
goc = {"a": {"rows": list(range(35)), "small": [1, 2, 3], "vua": list(range(30)),
		"nested": {"items": [{"sub": list(range(40)), "i": i} for i in range(32)]}},
	"t": tuple(range(31)), "x": "chuỗi", "n": None}
ban, tong = prompt.truncate(goc)
c("rows 35 → 30 phần tử ĐẦU, _cat ghi 5", ban["a"]["rows"] == list(range(30)) and ban["a"]["_cat"] == {"rows": 5}, ban["a"].get("_cat"))
c("danh sách ≤ 30 (3 và đúng 30) giữ nguyên, không ghi _cat cho chúng", ban["a"]["small"] == [1, 2, 3]
	and ban["a"]["vua"] == list(range(30)) and set(ban["a"]["_cat"]) == {"rows"})
c("danh sách lồng: items 32 → 30 (_cat 2), mỗi phần tử sub 40 → 30 (_cat 10)", len(ban["a"]["nested"]["items"]) == 30
	and ban["a"]["nested"]["_cat"] == {"items": 2} and all(x["sub"] == list(range(30)) and x["_cat"] == {"sub": 10}
	and x["i"] == i for i, x in enumerate(ban["a"]["nested"]["items"])))
c("tuple 31 ở gốc → list 30, _cat ghi 1", ban["t"] == list(range(30)) and ban["_cat"] == {"t": 1}, ban.get("_cat"))
# 5 (rows) + 2 (items) + 30 phần tử còn lại × 10 (sub) + 1 (t) = 308
c("tổng số phần tử bị cắt = 308", tong == 308, tong)
c("giá trị thường giữ nguyên", ban["x"] == "chuỗi" and ban["n"] is None)
c("bản gốc KHÔNG bị đổi", len(goc["a"]["rows"]) == 35 and "_cat" not in goc["a"] and "_cat" not in goc
	and len(goc["a"]["nested"]["items"]) == 32 and len(goc["a"]["nested"]["items"][0]["sub"]) == 40
	and isinstance(goc["t"], tuple))
ban2, tong2 = prompt.truncate(ban)
c("cắt lại bản đã cắt: không đổi gì, tổng 0", ban2 == ban and tong2 == 0 and ban2 is not ban)
c("hai danh sách dài cùng một cha → _cat ghi cả hai", prompt.truncate({"a": list(range(31)), "b": list(range(33))})
	== ({"a": list(range(30)), "b": list(range(30)), "_cat": {"a": 1, "b": 3}}, 4))
c("list nằm ngay trong list: vẫn cắt và đếm (không có dict cha để ghi)", prompt.truncate([list(range(33))])
	== ([list(range(30))], 3))
c("max_list truyền vào", prompt.truncate({"x": [1, 2, 3]}, 2) == ({"x": [1, 2], "_cat": {"x": 1}}, 1))
c("hằng số MAX_LIST = 30, MAX_CHARS = 120000", prompt.MAX_LIST == 30 and prompt.MAX_CHARS == 120_000)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[17] build_user")
pack = {"cong-no": {"receivables": {"kpis": {"overdue_pct": 27.5, "as_of": D(2026, 10, 27), "dso": Decimal("41.5")},
	"top_overdue": [{"customer_name": f"KH#{i:04d}", "overdue": 1000 * i} for i in range(1, 36)]}}}
tin = [{"id": "S1", "rule": "cn.qua_han_ty_le", "muc": "vang",
		"loi_quy_tac": "Nợ quá hạn chiếm {{cong-no.receivables.kpis.overdue_pct|pct}} phải thu",
		"paths": ["cong-no.receivables.kpis.overdue_pct"], "so_ngay": 0, "trang_thai": "mo", "ghi_chu_quan_tri": None,
		"name": "INSIGHT-BI-MAT", "documents": [{"doctype": "Sales Invoice", "name": "SI-0001"}]},
	{"id": "S2", "rule": "cn.dso_cao", "muc": "do", "loi_quy_tac": "DSO cao", "paths": [], "so_ngay": 12,
		"trang_thai": "dang-xu-ly", "ghi_chu_quan_tri": "Đã nhắc phòng kế toán"}]
s, notes = prompt.build_user("tai-chinh", pack, tin)
o = json.loads(s)
c("JSON có đúng 3 khoá nhom / pack / tin_hieu", set(o) == {"nhom", "pack", "tin_hieu"} and o["nhom"] == "tai-chinh")
c("pack: danh sách 35 → 30 + _cat 5; ngày → ISO; Decimal → số", o["pack"] == {"cong-no": {"receivables": {
	"kpis": {"overdue_pct": 27.5, "as_of": "2026-10-27", "dso": 41.5},
	"top_overdue": [{"customer_name": f"KH#{i:04d}", "overdue": 1000 * i} for i in range(1, 31)],
	"_cat": {"top_overdue": 5}}}}, o["pack"]["cong-no"]["receivables"].get("_cat"))
c("tin_hieu: chỉ các khoá đã chốt (bỏ name / documents), bỏ ghi chú trống, GIỮ so_ngay = 0", o["tin_hieu"] == [
	{"id": "S1", "rule": "cn.qua_han_ty_le", "muc": "vang",
		"loi_quy_tac": "Nợ quá hạn chiếm {{cong-no.receivables.kpis.overdue_pct|pct}} phải thu",
		"paths": ["cong-no.receivables.kpis.overdue_pct"], "so_ngay": 0, "trang_thai": "mo"},
	{"id": "S2", "rule": "cn.dso_cao", "muc": "do", "loi_quy_tac": "DSO cao", "paths": [], "so_ngay": 12,
		"trang_thai": "dang-xu-ly", "ghi_chu_quan_tri": "Đã nhắc phòng kế toán"}], o["tin_hieu"])
c("lời quy tắc gửi đi còn nguyên placeholder", "{{cong-no.receivables.kpis.overdue_pct|pct}}" in s)
c("không lọt tên Insight / chứng từ", "INSIGHT-BI-MAT" not in s and "SI-0001" not in s)
c("ensure_ascii False (tiếng Việt giữ nguyên), khoá sắp ổn định, không khoảng trắng thừa", "Nợ quá hạn chiếm" in s
	and s == json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	and s.index('"nhom"') < s.index('"pack"') < s.index('"tin_hieu"'))
c("gói vừa → không ghi chú", notes == [])
c("gói gốc không bị đổi", len(pack["cong-no"]["receivables"]["top_overdue"]) == 35
	and "_cat" not in pack["cong-no"]["receivables"] and "name" in tin[0])
c("gọi lại cho cùng đầu vào → cùng chuỗi (ổn định)", prompt.build_user("tai-chinh", pack, tin)[0] == s)
c("không tín hiệu / pack rỗng vẫn dựng được", json.loads(prompt.build_user("attp", {}, [])[0])
	== {"nhom": "attp", "pack": {}, "tin_hieu": []} and json.loads(prompt.build_user("attp", None, None)[0])
	== {"nhom": "attp", "pack": {}, "tin_hieu": []})

print("\n[18] build_user: quá dài → cắt đôi danh sách DÀI NHẤT (theo ký tự) tới khi vừa")
# Mỗi dòng "big": {"t":"x…(100 chữ)…"} = 6 + 100 + 2 = 108 ký tự. 30 dòng: 2 + 30 × 108 + 29 = 3271.
# "a_tiny": 0..29 → 10 số 1 chữ + 20 số 2 chữ = 50 chữ số + 29 dấu phẩy + 2 = 81.
# Cả gói: {"nhom":"g", (12) "pack": (7) {"m": (5) {"k": (5) { (1) "a_tiny": (9) 81 , (1) "big": (6) 3271 }}} (3)
#         ,"tin_hieu":[] (14) } (1) = 12+7+5+5+1+9+81+1+6+3271+3+14+1 = 3416
big = {"m": {"k": {"big": [{"t": "x" * 100} for _ in range(30)], "a_tiny": list(range(30))}}}
s0, n0 = prompt.build_user("g", big, [], max_chars=3416)
c("(tiền đề) gói dài đúng 3416 ký tự; trần 3416 → vừa khít, không cắt", len(s0) == 3416 and n0 == []
	and "_cat" not in json.loads(s0)["pack"]["m"]["k"], (len(s0), n0))
# Trần 2000: cắt đôi "big" (danh sách dài nhất theo ký tự, dù "a_tiny" cũng 30 phần tử và đứng trước) → 15 dòng:
# 2 + 15 × 108 + 14 = 1636; thêm "_cat":{"big":15}, = 6+1+10+1 = 18 → 3416 − 3271 + 1636 + 18 = 1799 ≤ 2000 → dừng.
s1, n1 = prompt.build_user("g", big, [], max_chars=2000)
k1 = json.loads(s1)["pack"]["m"]["k"]
c("trần 2000: 'big' còn 15 dòng ĐẦU, 'a_tiny' giữ nguyên 30", len(k1["big"]) == 15 and k1["a_tiny"] == list(range(30)),
	(len(k1["big"]), len(k1["a_tiny"])))
c("… _cat ở dict cha ghi 15 bị cắt; chuỗi dài đúng 1799", k1["_cat"] == {"big": 15} and len(s1) == 1799, (k1.get("_cat"), len(s1)))
c("… có ghi chú nêu đúng danh sách và số còn lại", n1 == ["gói số quá dài: cắt m.k.big còn 15 phần tử"], n1)
# Trần 1000: 1799 > 1000 → cắt tiếp "big" (1636 > 81) còn 7: 2 + 7 × 108 + 6 = 764; _cat 15 + 8 = 23 (vẫn 2 chữ số)
# → 1799 − 1636 + 764 = 927 ≤ 1000.
s2, n2 = prompt.build_user("g", big, [], max_chars=1000)
k2 = json.loads(s2)["pack"]["m"]["k"]
c("trần 1000: 'big' còn 7, _cat cộng dồn 23, dài 927, một ghi chú với số cuối", len(k2["big"]) == 7
	and k2["_cat"] == {"big": 23} and len(s2) == 927 and n2 == ["gói số quá dài: cắt m.k.big còn 7 phần tử"]
	and k2["a_tiny"] == list(range(30)), (len(k2["big"]), k2.get("_cat"), len(s2), n2))
c("… bản gốc không đổi", len(big["m"]["k"]["big"]) == 30 and "_cat" not in big["m"]["k"])
# Danh sách 35 phần tử to: cắt 30 trước (_cat 5), rồi cắt vì dài: 30 → 15 (_cat 5 + 15 = 20)
# 15 dòng = 1636; {"nhom":"g","pack":{"m":{"k":{"_cat":{"big":20},"big":[…]}}},"tin_hieu":[]}
# = 12+7+5+5+19+6+1636+3+14+1 = 1708
s3, n3 = prompt.build_user("g", {"m": {"k": {"big": [{"t": "x" * 100} for _ in range(35)]}}}, [], max_chars=1800)
k3 = json.loads(s3)["pack"]["m"]["k"]
c("35 dòng to: cắt 30 rồi cắt đôi → 15, _cat = 5 + 15 = 20, dài 1708", len(k3["big"]) == 15 and k3["_cat"] == {"big": 20}
	and len(s3) == 1708 and n3 == ["gói số quá dài: cắt m.k.big còn 15 phần tử"], (k3.get("_cat"), len(s3), n3))
# Một phần tử khổng lồ: 1 → 0
s4, n4 = prompt.build_user("g", {"m": {"k": {"rows": [{"t": "z" * 300}]}}}, [], max_chars=200)
k4 = json.loads(s4)["pack"]["m"]["k"]
c("danh sách một phần tử quá to → cắt còn 0, _cat ghi 1, vừa trần", k4 == {"rows": [], "_cat": {"rows": 1}}
	and len(s4) <= 200 and n4 == ["gói số quá dài: cắt m.k.rows còn 0 phần tử"], (k4, n4))
# Không còn danh sách để cắt: {"nhom":"g","pack":{"m":{"k":{"note":"y…(500)…"}}},"tin_hieu":[]}
# = 12 + 7 + 5 + 5 + 9 ({"note":") + 500 + 2 ("}) + 2 (}}) + 14 + 1 = 557
s5, n5 = prompt.build_user("g", {"m": {"k": {"note": "y" * 500}}}, [], max_chars=100)
c("không còn danh sách để cắt → trả nguyên (557 ký tự) + ghi chú 'vẫn dài'", len(s5) == 557
	and n5 == ["gói số vẫn dài 557 ký tự (trần 100) sau khi cắt hết danh sách"], (len(s5), n5))
c("mặc định trần 120000: gói 3416 ký tự không bị cắt", prompt.build_user("g", big, [])[0] == s0)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[19] build_user: \"kieu\" — kiểu đúng của các con số (D8 / N2)")
KM = {"cong-no.receivables.top_overdue.overdue": "tien", "cong-no.receivables.kpis.overdue_pct": "pct",
	"cong-no.receivables.kpis.overdue_customers": "so", "cong-no.receivables.kpis.as_of": "ngay",
	"tong-quan.summary.rows.sales": "tien", "cong-nox.a": "so"}


def bu(*a, **k):
	try:
		return prompt.build_user(*a, **k)
	except Exception as e:  # noqa: BLE001 — bản trước sửa không nhận kinds
		return repr(e), None


sk, nk = bu("tai-chinh", pack, tin, kinds=KM)
ok_json = nk is not None
ok_k = json.loads(sk) if ok_json else {}
c("[N2] kinds → khoá \"kieu\": chỉ path của mảng có trong gói (bỏ tong-quan, bỏ 'cong-nox' chỉ trùng tiền tố), chỉ "
	"kiểu số (bỏ ngay)", ok_k.get("kieu") == {"cong-no.receivables.kpis.overdue_customers": "so",
	"cong-no.receivables.kpis.overdue_pct": "pct", "cong-no.receivables.top_overdue.overdue": "tien"}, sk[:200])
c("[N2] … \"kieu\" sắp theo path trong chuỗi gửi đi; pack / tin_hieu giữ nguyên như khi không có kinds", ok_json
	and list(ok_k["kieu"]) == sorted(ok_k["kieu"]) and sk.index('"kieu"') < sk.index('"nhom"')
	and {k: v for k, v in ok_k.items() if k != "kieu"} == json.loads(s))
c("[N2] kinds rỗng → \"kieu\": {}; kinds None → không có khoá kieu (như cũ)", ok_json
	and json.loads(bu("tai-chinh", pack, tin, kinds={})[0]).get("kieu") == {} and "kieu" not in json.loads(
	bu("tai-chinh", pack, tin, kinds=None)[0]))
# "kieu" tính vào trần: gói big dài 3416 (vừa khít trần 3416) + kieu {"m.k.big.t":"so"} → phải cắt
sb, nb = bu("g", big, [], max_chars=3416, kinds={"m.k.big.t": "so", "x.y": "pct"})
c("[N2] \"kieu\" tính vào trần ký tự: gói vừa khít trần + kieu → phải cắt danh sách và vẫn ≤ trần", nb is not None
	and len(sb) <= 3416 and json.loads(sb)["kieu"] == {"m.k.big.t": "so"} and len(json.loads(sb)["pack"]["m"]["k"]["big"])
	== 15 and nb == ["gói số quá dài: cắt m.k.big còn 15 phần tử"], (len(sb), nb))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[20] Khoá khai sai dạng (xuống dòng / dấu cách ở giữa) — D6 / S6")
TAIL = "Tk9RvSAFETYtailSECRET0123456789abcdefXYZ-AA"
HEAD = "sk" + "-ant-api03-"
xau = {"xuống dòng \\n": HEAD + "\n" + TAIL, "\\r giữa khoá": HEAD + "\r" + TAIL, "dấu cách": HEAD + " " + TAIL,
	"tab": HEAD + "\t" + TAIL, "ký tự ngoài ASCII": HEAD + "é" + TAIL, "ký tự điều khiển": HEAD + "\x00" + TAIL}
for nhan, k in xau.items():
	frappe.conf["bc_ai_anthropic_key"] = "  " + k + "\n"
	c(f"[S6] has_key False khi khoá có {nhan}", llm.has_key("claude") is False)
	out, err, fake, sl = goi([ok()])
	c(f"[S6] … gọi → no_key (→ khong-khoa), KHÔNG gọi mạng, lời lỗi không mang mảnh nào của khoá ({nhan})",
		err is not None and err.kind == "no_key" and llm.run_status(err.kind) == "khong-khoa" and fake.calls == []
		and all(x not in repr(err) + err.message + vet(err) for x in (TAIL, TAIL[:8], "api03")), err and err.message)
frappe.conf["bc_ai_anthropic_key"] = HEAD + "\n" + TAIL
fake = FakeRequests([ok()])
anthropic.requests = fake
try:
	anthropic.call("claude-sonnet-5-5", SYSTEM, USER, prompt.SCHEMA_NAME, prompt.SCHEMA)
	e4 = None
except llm.LLMError as e:
	e4 = e
c("[S6] anthropic.call gọi thẳng (bỏ qua cửa) với khoá có xuống dòng → no_key, không gửi, không mảnh khoá",
	e4 is not None and e4.kind == "no_key" and fake.calls == [] and TAIL not in str(e4) and "khai sai dạng" in e4.message,
	e4 and e4.message)
c("[S6] khoá chỉ thừa khoảng trắng HAI ĐẦU vẫn dùng được (như cũ)",
	(frappe.conf.__setitem__("bc_ai_anthropic_key", f" {KEY}\n") or llm.has_key("claude")) is True
	and goi([ok()])[1] is None)
# clean(): dạng repr (\\n thành hai ký tự) và từng mảnh ≥ 6 ký tự của khoá khai sai
frappe.conf["bc_ai_anthropic_key"] = HEAD + "\n" + TAIL
k = frappe.conf["bc_ai_anthropic_key"]
cl = llm.clean(f"InvalidHeader: header value: {k!r} / đuôi {TAIL} / đầu {HEAD}x")
c("[S6] clean(): xoá dạng repr của khoá + mọi mảnh ≥ 6 ký tự (đuôi khoá đứng riêng, đầu khoá)", TAIL not in cl
	and "SECRET" not in cl and "api03" not in cl and "InvalidHeader: header value: '***' / đuôi *** / đầu ***x" == cl, cl)
frappe.conf["bc_ai_anthropic_key"] = "abcde\nTAILPART99"
c("[S6] clean(): mảnh < 6 ký tự giữ nguyên (tránh xoá chữ thường), mảnh ≥ 6 bị xoá",
	llm.clean("x abcde y TAILPART99 z") == "x abcde y *** z", llm.clean("x abcde y TAILPART99 z"))
# _send: lỗi gửi không phải lỗi mạng → chỉ tên loại ngoại lệ
frappe.conf["bc_ai_anthropic_key"] = KEY
out, err, fake, sl = goi([ValueError(f"header lạ: {TAIL}")])
c("[S6] _send: lỗi gửi khác (ValueError mang chữ lạ) → message chỉ 'không gửi được yêu cầu (ValueError)'",
	err is not None and err.kind == "http" and err.message == "không gửi được yêu cầu (ValueError)", err and err.message)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[21] Gói phần mềm không chứa chuỗi tiền tố khoá (D16 / P5)")
hits = []
for goc_dir, dirs, files in os.walk(os.path.join(BC_ROOT, "bc")):
	dirs[:] = [d for d in dirs if d != "__pycache__"]
	for f in files:
		try:
			txt = open(os.path.join(goc_dir, f), encoding="utf-8").read()
		except (UnicodeDecodeError, OSError):
			continue
		hits += [f"{os.path.relpath(os.path.join(goc_dir, f), BC_ROOT)}:{i}" for i, ln in
			enumerate(txt.splitlines(), 1) if "sk" + "-" in ln]
c("[P5] grep 'sk-' trong bc/ (trừ __pycache__) rỗng", hits == [], hits)
c("[P5] … mẫu khoá vẫn bắt chuỗi dạng khoá Anthropic không khai trong site", llm.clean(f"k={SK}") == "k=***"
	and llm.clean("risk-adjusted task-budgets") == "risk-adjusted task-budgets")

c.done()
