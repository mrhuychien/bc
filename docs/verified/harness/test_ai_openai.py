"""Trợ lý AI — cửa ra OpenAI (bc.ai.llm.call("openai", …) + bc.ai.llm.openai, Responses API) và nút Thử kết nối.

KHÔNG RA MẠNG: (1) chặn ở tầng socket — mọi lời nối không phải socket unix của MariaDB và mọi lượt tra DNS đều ném
lỗi; (2) tên `requests` của adapter thay bằng bản giả chạy theo kịch bản, hết kịch bản mà còn bị gọi thì ném lỗi và
đếm. Định dạng yêu cầu / trả lời / mã lỗi đối chiếu với tài liệu OpenAI hiện hành (developers.openai.com/api:
reference responses/create, guides structured-outputs, guides error-codes). Số kỳ vọng tính tay (ghi trong comment).
"""
import ast
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

from seed import Check, bc_settings, child, reset, single  # noqa: E402
from paths import BC_ROOT, DB  # noqa: E402

import frappe  # noqa: E402
import requests as real_requests  # noqa: E402

from bc.ai import llm, review  # noqa: E402
from bc.ai.llm import anthropic, openai  # noqa: E402

c = Check()
OKEY = "sk-proj-Ab3dEf_GhIjK-lMnOpQrStUv0123456789"   # khoá dạng OpenAI (tiền tố proj)
AKEY = "KHOA/claude+mat==bc.0123456789"
SVC = "sk-svcacct-Zz9_Yy8-Xx7Ww6Vv5Uu4"              # khoá OpenAI KHÔNG khai trong site: chỉ bị xoá nhờ mẫu
ADM = "sk-admin-Qq1Rr2Ss3Tt4Uu5Vv6"
SYSTEM = "Bạn là người phản biện. Viết ngắn."
USER = json.dumps({"nhom": "tai-chinh", "du_lieu": {"pack": {"cong-no": {"r": {"overdue_pct": 27.5}}}},
	"nhan_dinh": [{"id": "N1", "muc": "vang", "tieu_de": "x", "noi_dung": "y", "khuyen_nghi": []}]}, ensure_ascii=False)
GOOD = {"reviews": [{"id": "N1", "verdict": "nghi-ngo", "note": "Chưa có số cho thấy nguyên nhân."},
	{"id": "N2", "verdict": "dong-y", "note": ""}]}
SLEEPS: list = []
MODEL = "gpt-6.2-astra"


class FakeResp:
	def __init__(self, status, body, headers=None):
		self.status_code = status
		self.text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
		self.headers = headers or {}


class FakeRequests:
	"""Lớp chặn 2: `requests` giả chạy theo kịch bản. Hết kịch bản mà còn bị gọi → ném lỗi + đếm."""
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


def msg(*parts, status="completed"):
	return {"type": "message", "id": "msg_1", "status": status, "role": "assistant", "content": list(parts)}


def txt(data=None, text=None):
	return {"type": "output_text", "annotations": [], "logprobs": [],
		"text": text if text is not None else json.dumps(GOOD if data is None else data, ensure_ascii=False)}


def ok(data=None, text=None, model=MODEL, usage=None, status="completed", output=None, **extra):
	"""Thân 200 đúng dạng Response object của tài liệu (id, object, status, model, output[], usage{…})."""
	if output is None:
		output = [{"type": "reasoning", "id": "rs_1", "summary": []}, msg(txt(data, text))]
	return FakeResp(200, {"id": "resp_67ccd3a9", "object": "response", "created_at": 1741476542, "status": status,
		"error": None, "incomplete_details": None, "model": model, "output": output, "store": False,
		"usage": usage if usage is not None else {"input_tokens": 328, "input_tokens_details": {"cached_tokens": 100},
			"output_tokens": 52, "output_tokens_details": {"reasoning_tokens": 30}, "total_tokens": 380}, **extra})


def loi(status, message, etype=None, code=None, headers=None):
	return FakeResp(status, {"error": {"message": message, "type": etype, "param": None, "code": code}}, headers)


def goi(script, model=MODEL, schema=None, provider="openai", **kw):
	"""llm.call("openai", …) với `requests` giả theo kịch bản → (kết quả | None, LLMError | None, bản giả, lần ngủ)."""
	fake = FakeRequests(script)
	openai.requests = fake
	del SLEEPS[:]
	out = err = None
	try:
		out = llm.call(provider, model, SYSTEM, USER, review.SCHEMA_NAME, review.SCHEMA if schema is None else schema,
			**kw)
	except llm.LLMError as e:
		err = e
	return out, err, fake, list(SLEEPS)


def than(call):
	return json.loads(call["data"].decode("utf-8"))


def lo_khoa(*things):
	"""Khoá (hoặc 10 ký tự đầu của nó) có nằm trong bất kỳ thứ gì đưa vào không."""
	blob = " ".join(repr(t) + str(t) for t in things)
	return any(k in blob or k[:10] in blob for k in (OKEY, AKEY))


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


reset(only={"BC AI Run", "BC AI Model Price", "BC Tet Date"})
bc_settings()
openai.sleep = SLEEPS.append
anthropic.sleep = SLEEPS.append
BAY = FakeRequests()          # bẫy cho adapter Claude: bộ thử này không được gọi Claude lần nào
anthropic.requests = BAY
openai.requests = FakeRequests()
frappe.conf.clear()

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[1] Không có khoá / khoá sai dạng / model trống → không gọi mạng")
out, err, fake, sl = goi([])
c("openai chưa khai khoá → no_key, không POST, không ngủ", err is not None and err.kind == "no_key"
	and fake.calls == [] and fake.unexpected == 0 and sl == [], err)
for nhan, k in (("toàn dấu cách", "  \n "), ("có dấu cách ở giữa", "sk-proj-abc def123456"),
		("xuống dòng giữa khoá", "sk-proj-abc\ndef123456"), ("ký tự ngoài ASCII", "sk-proj-abcđef123456")):
	frappe.conf["bc_ai_openai_key"] = k
	out, err, fake, sl = goi([ok()])
	c(f"khoá {nhan} → no_key, không POST (khoá sai dạng = chưa có khoá)", err is not None and err.kind == "no_key"
		and fake.calls == [] and llm.has_key("openai") is False, err)
	c(f"… lời lỗi không chép khoá sai dạng ({nhan})", not k.strip() or k.strip()[:8] not in err.message, err.message)
frappe.conf["bc_ai_openai_key"] = "sk-proj-abc def123456"
c("khoá sai dạng: key_malformed True (màn quản trị nói rõ)", llm.key_malformed("openai") is True)
err = None
try:
	openai.call(MODEL, SYSTEM, USER, "phan_bien", review.SCHEMA)
except llm.LLMError as e:
	err = e
c("gọi thẳng adapter với khoá sai dạng → no_key", err is not None and err.kind == "no_key")
frappe.conf["bc_ai_openai_key"] = OKEY
for m in ("", "   ", None):
	out, err, fake, sl = goi([ok()], model=m)
	c(f"model trống ({m!r}) → http, không POST", err is not None and err.kind == "http" and fake.calls == [], err)
c("có khoá: has_key True, key_malformed False", llm.has_key("openai") is True and llm.key_malformed("openai") is False)
c("điều phối: claude không có khoá vẫn no_key (không chạm adapter OpenAI)", (lambda r: r[1] is not None
	and r[1].kind == "no_key" and r[2].calls == [])(goi([ok()], provider="claude")))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[2] Lượt gọi thường: URL, header, thân đúng tài liệu")
out, err, fake, sl = goi([ok()])
c("trả đúng 4 khoá: data / tokens_in / tokens_out / model", err is None and out == {"data": GOOD, "tokens_in": 328,
	"tokens_out": 52, "model": MODEL}, out or err)
c("một lượt POST, không ngủ", len(fake.calls) == 1 and sl == [])
g = fake.calls[0]
c("URL Responses API", g["url"] == "https://api.openai.com/v1/responses", g["url"])
c("chỉ truyền headers / data / timeout / allow_redirects", set(g) == {"url", "headers", "data", "timeout",
	"allow_redirects"}, set(g))
c("KHÔNG theo chuyển hướng (Authorization không bị chép sang máy chủ khác)", g["allow_redirects"] is False)
c("header đúng hai trường: Authorization Bearer <khoá>, Content-Type application/json",
	g["headers"] == {"Authorization": f"Bearer {OKEY}", "Content-Type": "application/json"}, list(g["headers"]))
b = than(g)
c("thân đúng từng trường: model, input [system, user], max_output_tokens 16000, store false, text.format json_schema "
	"(name, schema, strict true)", b == {"model": MODEL, "input": [{"role": "system", "content": SYSTEM},
		{"role": "user", "content": USER}], "max_output_tokens": 16000, "store": False,
		"text": {"format": {"type": "json_schema", "name": "phan_bien", "schema": review.SCHEMA, "strict": True}}}, b)
c("store là false (boolean) — mặc định của API là true (OpenAI lưu câu trả lời)", b["store"] is False)
c("KHÔNG temperature / top_p / reasoning / instructions / tools / stream / background / previous_response_id",
	not ({"temperature", "top_p", "reasoning", "instructions", "tools", "tool_choice", "stream", "background",
		"previous_response_id", "max_tokens", "response_format", "messages"} & set(b)), set(b))
c("timeout: nối 10 s, đọc 300 s", g["timeout"] == (10, 300), g["timeout"])
c("thân là bytes UTF-8, tiếng Việt giữ nguyên (không \\u)", isinstance(g["data"], bytes)
	and "Bạn là người phản biện" in g["data"].decode("utf-8"))
out, err, fake, sl = goi([ok()], max_tokens=2048, timeout=60)
c("max_tokens / timeout truyền vào được dùng", than(fake.calls[0])["max_output_tokens"] == 2048
	and fake.calls[0]["timeout"] == (10, 60))
fake = FakeRequests([ok()])
openai.requests = fake
llm.call("openai", MODEL, "", USER, "ket_noi", review.SCHEMA)
c("system rỗng → input chỉ có tin user", than(fake.calls[0])["input"] == [{"role": "user", "content": USER}])
frappe.conf["bc_ai_openai_key"] = f"  {OKEY}\n"
out, err, fake, sl = goi([ok()])
c("khoá khai thừa dấu cách / xuống dòng hai đầu: header gửi khoá đã gọt", err is None
	and fake.calls[0]["headers"]["Authorization"] == f"Bearer {OKEY}")
frappe.conf["bc_ai_openai_key"] = OKEY

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[3] Đọc trả lời: theo type, usage, model thực trả lời")
khac = {"reviews": [{"id": "N9", "verdict": "dong-y", "note": "khác"}]}
out, err, fake, sl = goi([ok(output=[{"type": "reasoning", "id": "rs", "summary": []},
	msg(txt(GOOD), txt(khac)), msg(txt(khac))])])
c("mục reasoning đứng trước: lấy phần output_text ĐẦU TIÊN của mục message", err is None and out["data"] == GOOD,
	out or err)
out, err, fake, sl = goi([ok(output=[{"type": "web_search_call", "content": [txt(khac)]}, msg(txt(GOOD))])])
c("mục không phải message (dù có content) bị bỏ qua", err is None and out["data"] == GOOD, out or err)
out, err, fake, sl = goi([ok(model="gpt-6.2-astra-2026-09-30")])
c("model = model THỰC trả lời (bản chụp có hậu tố ngày)", out["model"] == "gpt-6.2-astra-2026-09-30")
out, err, fake, sl = goi([ok(model=None)])
c("trả lời thiếu model → model đã yêu cầu", out["model"] == MODEL)
# input_tokens 328 đã gồm 100 token đọc cache (input_tokens_details là bảng chia nhỏ) → 328; output 52 đã gồm suy luận
c("token = usage.input_tokens / output_tokens (không cộng lại cached / reasoning)", (out["tokens_in"], out["tokens_out"])
	== (328, 52), out)
out, err, fake, sl = goi([ok(usage={"input_tokens": None, "output_tokens": "9"})])
c("usage sai kiểu → 0 / 0, không lỗi", err is None and (out["tokens_in"], out["tokens_out"]) == (0, 0), out or err)
out, err, fake, sl = goi([ok(usage={})])
c("usage rỗng → 0 / 0", err is None and (out["tokens_in"], out["tokens_out"]) == (0, 0))
out, err, fake, sl = goi([ok(data={"reviews": []})])
c("reviews rỗng là hợp lệ", err is None and out["data"] == {"reviews": []})

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[4] Hết credit / chạm trần chi / hạn mức → credit, KHÔNG retry")
for nhan, resp in (
		("429 credit_balance_exhausted", loi(429, "You have no credits.", "insufficient_quota", "credit_balance_exhausted")),
		("429 organization_spend_limit_exceeded", loi(429, "Spend limit.", "insufficient_quota",
			"organization_spend_limit_exceeded")),
		("429 project_spend_limit_exceeded", loi(429, "Project spend limit.", None, "project_spend_limit_exceeded")),
		("429 organization_usage_limit_exceeded", loi(429, "Usage limit.", None, "organization_usage_limit_exceeded")),
		("429 type insufficient_quota (code trống)", loi(429, "You exceeded your current quota.", "insufficient_quota")),
		("429 code insufficient_quota", loi(429, "quota", "requests", "insufficient_quota")),
		("429 credit kèm Retry-After 1 s (vẫn không retry)", loi(429, "x", None, "credit_balance_exhausted",
			{"Retry-After": "1"}))):
	out, err, fake, sl = goi([resp, ok()])
	c(f"{nhan} → credit, 1 lượt POST, không ngủ", err is not None and err.kind == "credit" and len(fake.calls) == 1
		and len(fake.script) == 1 and sl == [], (err and err.kind, len(fake.calls), sl))
c("… trạng thái Run = het-credit", err is not None and llm.run_status(err.kind) == "het-credit")
out, err, fake, sl = goi([loi(429, "spend", "insufficient_quota", "credit_balance_exhausted")])
c("message nêu type + code để quản trị biết lý do", "credit_balance_exhausted" in err.message
	and "HTTP 429" in err.message, err.message)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[5] Retry: tối đa 2 lần, 5 s rồi 20 s; Retry-After < 60 s thì theo nó")
RL = lambda h=None: loi(429, "Rate limit reached for requests", "requests", "rate_limit_exceeded", h)  # noqa: E731
out, err, fake, sl = goi([RL(), RL(), RL(), ok()])
c("429 × 3 → rate sau 3 lượt POST, ngủ [5, 20], không gọi lượt 4", err is not None and err.kind == "rate"
	and len(fake.calls) == 3 and sl == [5, 20] and len(fake.script) == 1, (err and err.kind, len(fake.calls), sl))
c("… message ghi số lần đã thử", "đã thử 3 lần" in err.message, err.message)
out, err, fake, sl = goi([loi(429, "Slow down", "rate_limit_error", "slow_down"), ok()])
c("429 slow_down → retry, thành công, ngủ [5]", err is None and sl == [5] and len(fake.calls) == 2, (err, sl))
for status, etype, code in ((500, "server_error", None), (503, "service_unavailable_error", "server_is_overloaded"),
		(502, None, None)):
	out, err, fake, sl = goi([loi(status, "Overloaded", etype, code)] * 3 + [ok()])
	c(f"{status} × 3 → http sau 3 lượt, ngủ [5, 20]", err is not None and err.kind == "http" and len(fake.calls) == 3
		and sl == [5, 20], (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([loi(500, "x", "server_error"), loi(503, "x", None, "server_is_overloaded"), ok()])
c("500 → 503 → 200: thành công ở lượt 3", err is None and len(fake.calls) == 3 and sl == [5, 20])
out, err, fake, sl = goi([RL({"Retry-After": "2"}), RL({"retry-after": "7.5"}), ok()])
c("Retry-After 2 rồi 7.5 (chữ thường) → ngủ [2, 7.5] thay cho [5, 20]", err is None and sl == [2.0, 7.5], sl)
out, err, fake, sl = goi([RL({"Retry-After": "60"}), RL({"Retry-After": "3600"}), ok()])
c("Retry-After ≥ 60 s → chờ theo mặc định [5, 20] (không treo job)", err is None and sl == [5, 20], sl)
out, err, fake, sl = goi([RL({"Retry-After": "bậy"}), RL({"Retry-After": "-3"}), ok()])
c("Retry-After không đọc được / âm → mặc định", err is None and sl == [5, 20], sl)
out, err, fake, sl = goi([loi(503, "x", None, "server_is_overloaded", {"Retry-After": "0"}), ok()])
c("Retry-After 0 → ngủ 0 rồi thử lại", err is None and sl == [0.0], sl)
c("retry_after: ngày HTTP 30 s sau → 30", openai.retry_after("Wed, 21 Oct 2026 07:28:30 GMT",
	now=1792567680.0) == 30.0, openai.retry_after("Wed, 21 Oct 2026 07:28:30 GMT", now=1792567680.0))
c("retry_after: ngày HTTP đã qua → 0; None / rác → None", openai.retry_after("Wed, 21 Oct 2026 07:28:30 GMT",
	now=1792567780.0) == 0.0 and openai.retry_after(None) is None and openai.retry_after("abc") is None
	and openai.retry_after("nan") is None and openai.retry_after("inf") is None)
E = real_requests.exceptions
for nhan, exc in (("ReadTimeout", E.ReadTimeout("read timed out")), ("ConnectTimeout", E.ConnectTimeout("x")),
		("ConnectionError", E.ConnectionError("aborted")), ("ChunkedEncodingError", E.ChunkedEncodingError("x"))):
	out, err, fake, sl = goi([exc, exc, exc, ok()])
	c(f"{nhan} × 3 → timeout sau 3 lượt, ngủ [5, 20]", err is not None and err.kind == "timeout"
		and len(fake.calls) == 3 and sl == [5, 20], (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([E.ReadTimeout("x"), ok()])
c("timeout rồi 200 → thành công, ngủ [5]", err is None and sl == [5])
for status, etype in ((400, "invalid_request_error"), (401, None), (403, None), (404, "invalid_request_error"),
		(413, None)):
	out, err, fake, sl = goi([loi(status, "nope", etype, None, {"Retry-After": "1"}), ok()])
	c(f"{status} → http, KHÔNG retry", err is not None and err.kind == "http" and len(fake.calls) == 1 and sl == []
		and f"HTTP {status}" in err.message, (err and err.kind, len(fake.calls), sl))
out, err, fake, sl = goi([FakeResp(200, "<html>proxy</html>"), ok()])
c("200 nhưng thân không phải JSON → http, không retry", err.kind == "http" and len(fake.calls) == 1)
out, err, fake, sl = goi([FakeResp(429, "<html>Too Many</html>"), ok()])
c("429 thân không phải JSON → rate (retry)", err is None and sl == [5])
out, err, fake, sl = goi([E.InvalidURL("bad"), ok()])
c("lỗi gửi không phải lỗi nối (InvalidURL) → http, không retry", err.kind == "http" and len(fake.calls) == 1 and sl == [])

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[6] Từ chối, dở dang, thất bại — mang token đã tính tiền")
U = {"input_tokens": 900, "output_tokens": 40}
out, err, fake, sl = goi([ok(output=[msg({"type": "refusal", "refusal": "I can't help with that."})], usage=U), ok()])
c("phần content type refusal → refusal, không retry", err is not None and err.kind == "refusal"
	and len(fake.calls) == 1 and sl == [], err and err.kind)
c("… token đã tính tiền + model (900 / 40)", (err.tokens_in, err.tokens_out, err.model) == (900, 40, MODEL))
c("… message không chép lời từ chối của mô hình", "can't help" not in err.message, err.message)
out, err, fake, sl = goi([ok(output=[msg(txt(GOOD), {"type": "refusal", "refusal": "no"})])])
c("refusal đi kèm output_text (đủ JSON) → vẫn refusal", err is not None and err.kind == "refusal")
out, err, fake, sl = goi([ok(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
	text='{"reviews": [{"id": "N1", "verd', usage={"input_tokens": 1000, "output_tokens": 16000}), ok()])
c("status incomplete (max_output_tokens) → schema, không retry", err is not None and err.kind == "schema"
	and len(fake.calls) == 1, err and err.kind)
c("… token (1000 / 16000) + lý do trong message", (err.tokens_in, err.tokens_out) == (1000, 16000)
	and "max_output_tokens" in err.message, (err.tokens_in, err.tokens_out, err.message))
out, err, fake, sl = goi([ok(status="incomplete", incomplete_details={"reason": "max_output_tokens"})])
c("incomplete mà JSON tình cờ đủ → vẫn schema (đầu ra có thể thiếu)", err is not None and err.kind == "schema")
out, err, fake, sl = goi([ok(status="incomplete", incomplete_details={"reason": "content_filter"}, output=[])])
c("incomplete content_filter → refusal", err is not None and err.kind == "refusal", err and err.kind)
out, err, fake, sl = goi([ok(status="failed", error={"code": "server_error", "message": "BÍ MẬT gói số"},
	output=[], usage={"input_tokens": 5, "output_tokens": 0})])
c("status failed → http, không chép error.message, mang token", err is not None and err.kind == "http"
	and "BÍ MẬT" not in err.message and "server_error" in err.message and err.tokens_in == 5, err and err.message)
for st in ("in_progress", "queued", "cancelled", None):
	out, err, fake, sl = goi([ok(status=st)])
	c(f"status {st!r} → http (không coi là xong)", err is not None and err.kind == "http", err and err.kind)
for nhan, resp in (
		("output_text không phải JSON", ok(text="Xin lỗi, tôi không thể.")),
		("JSON là mảng", ok(text="[1, 2]")),
		("không có mục message", ok(output=[{"type": "reasoning", "id": "rs", "summary": []}])),
		("output rỗng", ok(output=[])),
		("message không có output_text", ok(output=[msg()])),
		("output_text rỗng", ok(text="  ")),
		("verdict ngoài enum", ok(data={"reviews": [{**GOOD["reviews"][0], "verdict": "sai"}]})),
		("thiếu note", ok(data={"reviews": [{"id": "N1", "verdict": "dong-y"}]})),
		("thừa khoá lạ", ok(data={"reviews": [{**GOOD["reviews"][0], "x": 1}]})),
		("reviews không phải mảng", ok(data={"reviews": "không"})),
		("thiếu reviews", ok(data={"ket_qua": []}))):
	out, err, fake, sl = goi([resp, ok()])
	c(f"{nhan} → schema, không retry", err is not None and err.kind == "schema" and len(fake.calls) == 1 and sl == [],
		(out, err and err.kind))
out, err, fake, sl = goi([ok(data={"reviews": [{**GOOD["reviews"][0], "verdict": "sai"}]},
	usage={"input_tokens": 700, "output_tokens": 80})])
c("sai schema: chỉ ra VỊ TRÍ, mang token (700 / 80), không chép giá trị", "$.reviews[0].verdict" in err.message
	and (err.tokens_in, err.tokens_out) == (700, 80) and "sai" not in err.message.split("tại")[-1], err.message)
out, err, fake, sl = goi([ok(text="BÍ MẬT-GÓI-SỐ 1.250.000")])
c("đầu ra không phải JSON: message không chép lời của mô hình", "BÍ MẬT" not in err.message
	and "1.250.000" not in err.message, err.message)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[7] Schema phan_bien đúng luật strict của structured outputs")


def strict_ok(s, path="$"):
	"""Mọi object: additionalProperties False + required = đủ mọi khoá; gốc là object, không anyOf ở gốc."""
	bad = []
	if s.get("type") == "object":
		if s.get("additionalProperties") is not False:
			bad.append(f"{path}: additionalProperties")
		if sorted(s.get("required") or []) != sorted(s.get("properties") or {}):
			bad.append(f"{path}: required")
		for k, v in (s.get("properties") or {}).items():
			bad += strict_ok(v, f"{path}.{k}")
	if s.get("type") == "array" and isinstance(s.get("items"), dict):
		bad += strict_ok(s["items"], f"{path}[]")
	for v in s.get("anyOf") or []:
		bad += strict_ok(v, path)
	return bad


c("review.SCHEMA: gốc object, mọi object strict (additionalProperties false, required đủ)",
	review.SCHEMA.get("type") == "object" and "anyOf" not in review.SCHEMA and strict_ok(review.SCHEMA) == [],
	strict_ok(review.SCHEMA))
c("review.SCHEMA: verdict enum đúng (dong-y, nghi-ngo); không min/max/pattern", review.SCHEMA["properties"]["reviews"]
	["items"]["properties"]["verdict"] == {"type": "string", "enum": ["dong-y", "nghi-ngo"]}
	and not any(k in json.dumps(review.SCHEMA) for k in ("minLength", "maxLength", "minItems", "pattern")))
from bc.api import ai as api  # noqa: E402
c("schema Thử kết nối (bc.api.ai.TEST_SCHEMA) cũng strict", strict_ok(api.TEST_SCHEMA) == [], strict_ok(api.TEST_SCHEMA))
c("tên schema hợp lệ theo tài liệu (a-z A-Z 0-9 _ -, ≤ 64)", all(len(n) <= 64 and all(ch.isascii() and
	(ch.isalnum() or ch in "_-") for ch in n) for n in (review.SCHEMA_NAME, "ket_noi")))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[8] Khoá không lọt ra đâu cả")
del frappe.LOGGED[:]
THU = []
out, err, fake, sl = goi([ok()])
c("kết quả thành công không chứa khoá", not lo_khoa(out, json.dumps(out, ensure_ascii=False)))
out, err, fake, sl = goi([E.InvalidHeader(f"Invalid return character or leading space in header: Authorization "
	f"{'Bearer ' + OKEY!r}"), ok()])
THU.append(err)
c("InvalidHeader chứa khoá → http, message chỉ còn tên loại ngoại lệ", err.kind == "http"
	and err.message == "không gửi được yêu cầu (InvalidHeader)", err.message)
c("… khoá không có trong str / repr / args / vết lỗi; không kéo ngoại lệ gốc", not lo_khoa(str(err), repr(err),
	err.args, vet(err)) and err.__context__ is None and err.__cause__ is None)
kh = khung_llm(err)
c("… vết lỗi chỉ còn MỘT khung của bc.ai.llm (call của cửa); biến cục bộ sạch", [k[0] for k in kh] == ["call"]
	and not lo_khoa(kh) and SYSTEM not in repr(kh) and "overdue_pct" not in repr(kh)
	and not ({"system", "user", "schema", "key", "headers", "data"} & set(kh[0][1])), (kh and sorted(kh[0][1])))
exc = E.ConnectionError(f"HTTPSConnectionPool(host='api.openai.com'): Authorization: Bearer {OKEY}")
out, err, fake, sl = goi([exc, exc, exc])
THU.append(err)
c("lỗi nối chứa khoá × 3 → timeout, khoá không lọt", err.kind == "timeout" and not lo_khoa(str(err), repr(err),
	vet(err)) and "***" in err.message, err.message)
out, err, fake, sl = goi([loi(401, f"Incorrect API key provided: {OKEY}. You can find your API key at …",
	"invalid_request_error", "invalid_api_key")])
THU.append(err)
c("401 chép lại khoá trong thân lỗi → message đã xoá khoá", err.kind == "http" and not lo_khoa(str(err), repr(err))
	and "***" in err.message and "invalid_api_key" in err.message, err.message)
out, err, fake, sl = goi([FakeResp(403, f"<html>Forbidden {OKEY}</html>")])
THU.append(err)
c("thân lỗi không phải JSON chứa khoá → đã xoá", not lo_khoa(str(err), repr(err)), err.message)
out, err, fake, sl = goi([loi(401, "x" * 260 + OKEY + " đuôi" * 50, None, "invalid_api_key")])
THU.append(err)
c("message cắt 300 ký tự SAU khi xoá khoá (khoá vắt qua mốc 300 không lọt nửa đầu)", len(err.message) == 300
	and "sk-proj" not in err.message, err.message[250:])
goc_req = openai._request


def _no(*a, **k):
	raise RuntimeError(f"hỏng khi dựng yêu cầu {OKEY} / {a[0]}")


openai._request = _no
out, err, fake, sl = goi([ok()])
openai._request = goc_req
THU.append(err)
c("lỗi lập trình trong adapter → cửa bọc thành http, khoá không lọt, nêu [file:dòng]", err.kind == "http"
	and not lo_khoa(str(err), repr(err), vet(err)) and "RuntimeError" in err.message
	and "[test_ai_openai.py:" in err.message, err.message)
sach = True
for e in THU + [goi([ok(output=[msg({"type": "refusal", "refusal": "no"})])])[1], goi([ok(text="không JSON")])[1],
		goi([ok(data={"reviews": "sai"})])[1], goi([loi(429, "x", None, "credit_balance_exhausted")])[1],
		goi([ok(status="incomplete", incomplete_details={"reason": "max_output_tokens"})])[1]]:
	kh = khung_llm(e)
	if [k[0] for k in kh] != ["call"] or lo_khoa(kh) or "overdue_pct" in repr(kh) or SYSTEM in repr(kh):
		sach = False
		print("    lộ:", e.kind, [k[0] for k in kh])
c("mọi loại LLMError ra khỏi cửa: vết chỉ có khung call, biến sạch", sach)
c("không lời gọi frappe.log_error nào mang khoá", not lo_khoa(frappe.LOGGED))
c("không ngoại lệ nào thu được mang khoá (kể cả thuộc tính)", not lo_khoa(*[vars(x) for x in THU]))
bien = {f"{m.__name__}.{k}": v for m in (llm, openai, review) for k, v in vars(m).items()
	if k != "requests" and not k.startswith("__") and not callable(v) and not isinstance(v, type(os))}
c("không biến cấp module nào giữ khoá sau các lượt gọi", not lo_khoa(*bien.values()),
	[k for k, v in bien.items() if lo_khoa(v)])

print("\n[8b] clean(): khoá dạng OpenAI (proj, svcacct, admin, cũ) bị xoá dù không khai trong site")
frappe.conf["bc_ai_openai_key"] = ""
for nhan, k in (("sk-proj-…", OKEY), ("sk-svcacct-…", SVC), ("sk-admin-…", ADM), ("sk-… cũ 48 ký tự",
		"sk-" + "A1b2C3d4E5" * 4 + "F6g7h8"), ("sk-None-…", "sk-None-abcDEF123_456")):
	s = llm.clean(f"key={k}; Bearer {k}, '{k}' \"{k}\"")
	c(f"clean() xoá {nhan} ở mọi vị trí", k not in s and s == "key=***; Bearer ***, '***' \"***\"", s)
c("clean(): không bắt nhầm chữ thường (task-, risk-, desk-top)", llm.clean("task-budgets risk-adjusted desk-top-01")
	== "task-budgets risk-adjusted desk-top-01")
e2 = llm.LLMError("http", f"lỗi {SVC} và {ADM}")
c("LLMError tự xoá khoá dạng OpenAI", e2.message == "lỗi *** và ***", e2.message)
frappe.conf["bc_ai_openai_key"] = "khoa-la/KHONG+dang+sk==123456"
c("khoá khai không theo dạng sk-: vẫn bị xoá vì so đúng chuỗi", llm.clean("a khoa-la/KHONG+dang+sk==123456 b")
	== "a *** b")
frappe.conf["bc_ai_openai_key"] = OKEY

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[9] Thử kết nối OpenAI (bc.api.ai.test_connection) trên adapter thật + HTTP giả")
RUN = "BC AI Run"
frappe.session.user = "Administrator"
frappe.db.sql(f"DELETE FROM `tab{RUN}`")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [
	{"model": "gpt-6.2-astra", "price_in": 1.25, "price_out": 10}])
single("BC Settings", ai_openai_model="gpt-6.2-astra")
frappe.clear_document_cache("BC Settings", "BC Settings")


def run_cuoi():
	return frappe.db.sql(f"SELECT * FROM `tab{RUN}` ORDER BY creation DESC, name DESC LIMIT 1", as_dict=True)[0]


fake = FakeRequests([ok(data={"ok": True}, usage={"input_tokens": 120, "output_tokens": 30})])
openai.requests = fake
t = api.test_connection("openai")
r = run_cuoi()
# cost = (120 × 1,25 + 30 × 10) / 1e6 = (150 + 300) / 1e6 = 0,00045
c("thành công → ok True, model thực, Run tay/test/openai ok, token + chi phí (0,00045)", (t, r.run_type, r.step,
	r.provider, r.status, r.tokens_in, r.tokens_out, round(float(r.cost_usd), 6)) == ({"ok": True, "model": MODEL,
	"error": ""}, "tay", "test", "openai", "ok", 120, 30, 0.00045), (t, dict(r)))
b = than(fake.calls[0])
c("… đúng MỘT POST, schema ket_noi strict, max_output_tokens 2048, timeout đọc 60 s, store false", len(fake.calls) == 1
	and b["text"]["format"] == {"type": "json_schema", "name": "ket_noi", "schema": api.TEST_SCHEMA, "strict": True}
	and b["max_output_tokens"] == 2048 and fake.calls[0]["timeout"] == (10, 60) and b["store"] is False, b)
openai.requests = FakeRequests([ok(data={"ok": True}, model=MODEL + "-2026-09-30",
	usage={"input_tokens": 120, "output_tokens": 30})])
t = api.test_connection("openai")
r = run_cuoi()
c("model trả lời là bản chụp có hậu tố ngày (chưa khai giá) → chi phí theo giá model đã yêu cầu (0,00045), đã biết giá",
	(t["model"], r.model, round(float(r.cost_usd or 0), 6), r.cost_known) == (MODEL + "-2026-09-30",
	MODEL + "-2026-09-30", 0.00045, 1), (t, dict(r)))
openai.requests = FakeRequests([loi(429, f"no credit {OKEY}", "insufficient_quota", "credit_balance_exhausted")])
t = api.test_connection("openai")
r = run_cuoi()
c("hết credit → ok False, Run het-credit, không retry", (t["ok"], r.status) == (False, "het-credit")
	and openai.requests.calls and len(openai.requests.calls) == 1, (t, r.status))
c("… khoá không có trong kết quả lẫn Run.error", not lo_khoa(t, dict(r)), (t, r.error))
openai.requests = FakeRequests([ok(output=[msg({"type": "refusal", "refusal": "no"})],
	usage={"input_tokens": 10, "output_tokens": 2})])
t = api.test_connection("openai")
r = run_cuoi()
c("từ chối → Run loi, token đã tính tiền ghi vào Run (10 / 2)", (t["ok"], r.status, r.tokens_in, r.tokens_out)
	== (False, "loi", 10, 2), (t, dict(r)))
openai.requests = FakeRequests([ok(data={"ok": False})])
t = api.test_connection("openai")
c("mô hình trả ok false → ok False", t["ok"] is False and run_cuoi().status == "ok")
frappe.conf["bc_ai_openai_key"] = "sk-proj-abc def"
openai.requests = FakeRequests([])
t = api.test_connection("openai")
c("khoá sai dạng → khong-khoa, không POST", (t["ok"], run_cuoi().status) == (False, "khong-khoa")
	and openai.requests.calls == [] and openai.requests.unexpected == 0, t)
frappe.conf["bc_ai_openai_key"] = OKEY
c("không dòng Run nào chứa khoá", not lo_khoa(frappe.db.sql(f"SELECT * FROM `tab{RUN}`", as_dict=True)))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("\n[10] Bộ thử không thể ra mạng; tĩnh")
truoc = len(BLOCKED)
toi_noi = True
try:
	real_requests.post("https://api.openai.com/v1/responses", data=b"{}", timeout=3)
except Exception:
	toi_noi = False
c("requests THẬT bị chặn ở tầng socket", not toi_noi and len(BLOCKED) > truoc, BLOCKED[-3:])
out, err, fake, sl = goi([])
c("bản giả hết kịch bản mà bị gọi → ném lỗi + đếm", fake.unexpected == 1 and err is not None and err.kind == "http")
c("bẫy Claude chưa hề bị chạm (bộ thử này không gọi Claude)", BAY.unexpected == 0 and BAY.calls == [])
c("ngủ luôn là bản giả", openai.sleep == SLEEPS.append)
src = open(os.path.join(BC_ROOT, "bc", "ai", "llm", "openai.py"), encoding="utf-8").read()
mods = set()
for n in ast.walk(ast.parse(src)):
	if isinstance(n, ast.Import):
		mods |= {a.name.split(".")[0] for a in n.names}
	elif isinstance(n, ast.ImportFrom):
		mods.add((n.module or "").split(".")[0])
c("AST openai.py: chỉ import thư viện chuẩn + frappe + requests + bc (không urllib / http.client / socket / httpx)",
	mods <= {"__future__", "email", "json", "time", "frappe", "requests", "bc"}, mods)
c("openai.py không gửi tham số lấy mẫu (không có chữ temperature / top_p trong mã)", "temperature" not in
	src.split('"""', 2)[2] and "top_p" not in src.split('"""', 2)[2])
rv = open(os.path.join(BC_ROOT, "bc", "ai", "review.py"), encoding="utf-8").read()
c("review.py không đọc khoá / site_config, không import requests", "bc_ai_" not in rv and ".conf." not in rv
	and "site_config" not in rv and "requests" not in rv)

frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
