"""Trợ lý AI P3 — hỏi đáp ĐẦU-CUỐI trên một DB: bc.api.ai.get_qa / ask / get_answer → bc.ai.qa → bc.ai.llm.chat THẬT
(dựng thân request, header, retry, phân loại lỗi) → cửa HTTP giả `bc.ai.llm.anthropic.http_post` (mô hình giả theo
kịch bản, đọc chính thân request) — và tài khoản MariaDB CHỈ ĐỌC thật (bc.ai.sqlro + sqlguard) cho quản trị.

Mọi module thật: collect.CALLS + bc.api.* (seed gộp seed_ui2), redact, prompt, budget, store, sqlguard, sqlro, llm.
Socket ra ngoài bị chặn (chỉ socket unix của MariaDB). Hàng đợi: frappe.enqueue giả chạy thẳng job dưới người hỏi
(ENQUEUE_RUN = False để giữ job lại).

Phần:
  A dựng     B người xem: câu cần HAI lần tra (công nợ + tồn kho) → số đã kiểm + một số tự tính "chưa kiểm", mã khách
  đổi lại tên, khối thinking gửi lại nguyên, mọi tool_result trong MỘT tin     C cùng người xem, ẩn mảng Công nợ: mô tả
  công cụ không còn mảng đó, tra vẫn bị chặn, không số nào của mảng đó trong request     D quản trị: get_schema +
  run_select (câu nhận, câu bị chặn rồi mô hình viết lại, bảng cấm), lượt cuối buộc trả lời (tool_choice none), tên
  người / khách trong ô SQL thành mã     E lỗi: từ chối, hết credit (không thử lại), quá giờ (thử lại 5 s / 20 s), quá
  tải, trả lời bị cắt     F giới hạn: rỗng / quá 500 ký tự, đang có câu khác, hết lượt / người, 200 câu / site, trần chi,
  300 lượt gọi / ngày, ≤ 7 lượt gọi     G ai_qa_enabled = 0: mọi lối vào từ chối, job đã xếp không gọi mô hình     H riêng
  tư trên MỌI thân request (không tên khách / NCC / người, không khoá, không mật khẩu chỉ đọc) và trên CẢ CSDL / Error
  Log / cache (không gì của câu hỏi / câu trả lời / kết quả tra cứu ngoài câu trả lời của chính người hỏi).

Chạy: BC_TEST_DB=bc_test_ai_p3e python3 -B test_ai_p3_e2e.py
"""
import copy
import itertools
import json
import re
import socket

# ─── Chặn mạng (trước mọi import có thể nối) ───────────────────────────────
MANG = []
_connect = socket.socket.connect


def _cam_noi(self, address, *a):
	if self.family != socket.AF_UNIX:
		MANG.append(address)
		raise OSError(f"bộ thử: cấm ra mạng ({address})")
	return _connect(self, address, *a)


def _cam_dns(host, *a, **k):
	MANG.append(host)
	raise OSError(f"bộ thử: cấm tra DNS ({host})")


socket.socket.connect = _cam_noi
socket.getaddrinfo = _cam_dns

from seed import Check, child, insert, single  # noqa: E402
from paths import DB, SOCK  # noqa: E402

import frappe  # noqa: E402  (giả)
import requests as real_requests  # noqa: E402

c = Check()
RUN = "BC AI Run"
KEY = "sk-ant-api03-KHOAGIA-p3e2e-Wq55Zr"
MODEL = "claude-sonnet-5-5"
VIEWER, VIEWER2, VIEWER3, ADMIN = "viewer@example.com", "viewer2.p3e@example.com", "viewer3.p3e@example.com", "Administrator"
RO_USER, RO_PASS = "bc_p3i_ro", "RoPass-p3i-Tz41Qe"
RW_USER, RW_PASS = "bc_p3i_rw", "RwPass-p3i-Lm09Vb"
KH_TEN, KH_ID = "Công ty Tân Phát Lộc", "KH-TAN-PHAT"
NCC_TEN, NCC_ID = "Nhà cung cấp Hoà Bình Xanh", "NCC-HOA-BINH"
NGUOI, NGUOI_TEN = "ke.toan.p3e@hgc.vn", "Trần Thị Kế Toán"
NV_TEN = "Phạm Văn Kiểm Định"
MQ, MA, MT = "MARKQzqv", "MARKAzqv", "MARKTzqv"   # dấu câu hỏi / câu trả lời / lỗi công cụ — không được nằm ngoài chỗ cho phép
TU_TINH = "7.777.777.777.777 đ"                    # số "tự tính" — không có trong kết quả tra cứu nào
AN = "cong-no"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


# ═══════════════════════════════════════════════════════════════════════════
print("A. Dựng: seed gộp + khách / NCC / người có tên riêng, khoá giả, tài khoản MariaDB chỉ đọc + có quyền ghi")
import seed_ui2  # noqa: E402,F401

insert("Customer", name=KH_ID, customer_name=KH_TEN, customer_group="NPP", owner=NGUOI, modified_by=NGUOI)
insert("Supplier", name=NCC_ID, supplier_name=NCC_TEN, owner=NGUOI)
insert("User", name=NGUOI, enabled=1, first_name="Trần Thị", last_name="Kế Toán", full_name=NGUOI_TEN)
insert("Employee", name="HR-EMP-P3E", employee_name=NV_TEN, first_name="Phạm", status="Active", department="Kho")
for u in (VIEWER2, VIEWER3):
	frappe.ROLES[u] = ["BC Viewer"]
single("BC Settings", ai_qa_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, hidden_sections="", ai_claude_model=MODEL,
	ai_qa_per_day=20, ai_context=f"Khách lớn nhất là {KH_TEN}; kế toán phụ trách {NGUOI_TEN}.")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [{"model": MODEL, "price_in": 2, "price_out": 10}])
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.conf["db_name"] = DB
frappe.conf["db_socket"] = SOCK
for u in (RO_USER, RW_USER):
	frappe.db.sql(f"DROP USER IF EXISTS '{u}'@'localhost'")
frappe.db.sql(f"CREATE USER '{RO_USER}'@'localhost' IDENTIFIED BY '{RO_PASS}'")
frappe.db.sql(f"GRANT SELECT ON `{DB}`.* TO '{RO_USER}'@'localhost'")
frappe.db.sql(f"CREATE USER '{RW_USER}'@'localhost' IDENTIFIED BY '{RW_PASS}'")
frappe.db.sql(f"GRANT ALL PRIVILEGES ON `{DB}`.* TO '{RW_USER}'@'localhost'")

from bc.ai import llm, qa  # noqa: E402
from bc.ai.llm import anthropic  # noqa: E402
from bc.api import ai as api  # noqa: E402

c("bc.ai.llm.chat là hàm THẬT (bộ thử chỉ thay cửa HTTP)", llm.chat.__module__ == "bc.ai.llm"
	and anthropic.chat.__module__ == "bc.ai.llm.anthropic")


class FakeResp:
	def __init__(self, status, body):
		self.status_code = status
		self.text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
		self.headers = {}


HTTP = []       # {"url", "headers", "data": bytes, "body": dict, "timeout"}
NGU = []        # các lần anthropic.sleep
KB = {"buoc": []}
_ID = itertools.count(1)


def fake_post(url, headers, data, timeout):
	body = json.loads(data.decode("utf-8"))
	HTTP.append({"url": url, "headers": dict(headers), "data": bytes(data), "body": body, "timeout": timeout})
	if not KB["buoc"]:
		raise AssertionError("bộ thử: kịch bản hết mà mô hình còn bị gọi")
	b = KB["buoc"].pop(0)
	b = b(body) if callable(b) else b
	if isinstance(b, BaseException):
		raise b
	return b


anthropic.http_post = fake_post
anthropic.sleep = NGU.append


def usage(ti=1200, to=80, doc=0, ghi=0):
	return {"input_tokens": ti, "output_tokens": to, "cache_read_input_tokens": doc, "cache_creation_input_tokens": ghi}


def resp(content, stop="end_turn", u=None, model=MODEL):
	return FakeResp(200, {"id": f"msg_{next(_ID):04d}", "type": "message", "role": "assistant", "model": model,
		"content": content, "stop_reason": stop, "stop_sequence": None, "usage": u or usage()})


def think():
	return {"type": "thinking", "thinking": "", "signature": f"EqQBSig{next(_ID):04d}+/=="}


def tu(name, inp):
	return {"type": "tool_use", "id": f"toolu_{next(_ID):04d}", "name": name, "input": inp}


def xin(*uses, truoc=True, u=None):
	return resp(([think(), {"type": "text", "text": "Để tôi tra số liệu."}] if truoc else []) + list(uses), "tool_use", u)


def tra(text, u=None):
	return resp([think(), {"type": "text", "text": text}], "end_turn", u)


def ket_qua(body, i=0):
	"""Khối tool_result thứ i của tin user cuối trong thân request."""
	return body["messages"][-1]["content"][i]


def as_user(u, fn, *a, **k):
	cu = frappe.session.user
	frappe.session.user = u
	try:
		return fn(*a, **k)
	finally:
		frappe.session.user = cu


def hoi(user, q, *buoc, history=None):
	"""Một câu hỏi trọn vẹn qua API → (ask, get_answer, các request HTTP của câu này)."""
	KB["buoc"] = list(buoc)
	n0 = len(HTTP)
	r = as_user(user, api.ask, q, json.dumps(history) if history is not None else None)
	a = as_user(user, api.get_answer, r["id"])
	c(f"kịch bản dùng hết ({q[:30]}…)", not KB["buoc"], len(KB["buoc"]))
	return r, a, HTTP[n0:]


def tu_choi(user, q, history=None):
	try:
		as_user(user, api.ask, q, history)
	except frappe.ValidationError as e:
		return str(e)
	return None


def chu(a):
	return "".join(s["t"] for s in a.get("segments") or [])


def run_row(qid):
	r = frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE name = %s", (qid,), as_dict=True)
	return r[0] if r else None


def so(v):
	"""Mọi số trong một đối tượng JSON (bỏ bool)."""
	out = []
	if isinstance(v, dict):
		for x in v.values():
			out += so(x)
	elif isinstance(v, list):
		for x in v:
			out += so(x)
	elif isinstance(v, (int, float)) and not isinstance(v, bool):
		out.append(v)
	return out


def vn_nghin(n: int) -> str:
	return f"{n:,}".replace(",", ".")


TEN_DOI_TAC = sorted({x for r in frappe.db.sql("SELECT name, customer_name FROM `tabCustomer`") for x in r if x}
	| {x for r in frappe.db.sql("SELECT name, supplier_name FROM `tabSupplier`") for x in r if x}
	| {x for (x,) in frappe.db.sql("SELECT DISTINCT custom_mt_chain FROM `tabCustomer`") if x})
TEN_DOI_TAC = [x for x in TEN_DOI_TAC if len(x) >= 5]
NGUOI_DS = sorted({x for r in frappe.db.sql("""SELECT name, full_name FROM `tabUser`
	WHERE name NOT IN ('Administrator', 'Guest')""") for x in r if x and len(x) >= 5}
	| {x for (x,) in frappe.db.sql("SELECT employee_name FROM `tabEmployee`") if x and len(x) >= 5})
c("có tên đối tác / người để soát (luật không rỗng nghĩa)", KH_TEN in TEN_DOI_TAC and NCC_TEN in TEN_DOI_TAC
	and NGUOI_TEN in NGUOI_DS and NV_TEN in NGUOI_DS and NGUOI in NGUOI_DS, (len(TEN_DOI_TAC), NGUOI_DS[:5]))
c("không mạng khi dựng", not MANG, MANG)

# ═══════════════════════════════════════════════════════════════════════════
print("B. Người xem: câu cần hai lần tra → số đã kiểm + số tự tính chưa kiểm")
g = as_user(VIEWER, api.get_qa)
eq("get_qa người xem: bật, 20 câu, còn 20, không SQL, 500 ký tự", g, {"enabled": True, "limit": 20, "used": 0,
	"remaining": 20, "sql": False, "max_question": 500})
B = {}


def b_tra(body):
	"""Lượt 3: đọc hai kết quả tra cứu trong CHÍNH thân request → một số làm tròn (đã kiểm) + mã khách + số tự tính."""
	kq_cn = json.loads(body["messages"][-3]["content"][0]["content"])
	kq_tk = json.loads(ket_qua(body)["content"])
	B["cn"], B["tk"] = kq_cn, kq_tk
	lon = sorted((abs(v) for v in so(kq_cn) if abs(v) >= 2_000_000), reverse=True)
	B["v"] = lon[0] if lon else 0
	B["trieu"] = round(B["v"] / 1e6)
	ma = re.findall(r"KH#\d+", json.dumps(kq_cn, ensure_ascii=False))
	B["ma"] = ma[0] if ma else ""
	return tra(f"- Phải thu: {vn_nghin(B['trieu'])} triệu, lớn nhất {B['ma']}.\n- Cộng với tồn kho (tự tính): {TU_TINH}.\n"
		f"Ghi chú {MA} năm 2026, ngày {NGAY_HN}.", u=usage(1500, 120, doc=900, ghi=300))


_hn = qa._hom_nay()
NGAY_HN = f"{_hn.day}/{_hn.month}/{_hn.year}"   # ngày hôm nay — có trong đề bài hệ thống → ngày đã kiểm


Q_B = f"Phải thu của {KH_TEN} và tồn kho hiện tại thế nào? {MQ}"
rb, ab, hb = hoi(VIEWER, Q_B,
	xin(tu("xem_mang", {"mang": "cong-no", "ten": "receivables"})),
	xin(tu("xem_mang", {"mang": "ton-kho", "ten": "overview"}), truoc=False),
	b_tra)
eq("ask → {id, cho}; get_answer → xong", (rb["status"], ab["status"]), ("cho", "xong"))
eq("ba lượt HTTP tới Messages API", [h["url"] for h in hb], [anthropic.URL] * 3)
c("có số phải thu ≥ 2 triệu và mã khách trong kết quả công nợ (dữ liệu soát không rỗng nghĩa)", B.get("v", 0) >= 2_000_000
	and B.get("ma"), (B.get("v"), B.get("ma")))
h0 = hb[0]
eq("header: x-api-key = khoá, anthropic-version, content-type", (h0["headers"].get("x-api-key"),
	h0["headers"].get("anthropic-version"), h0["headers"].get("content-type")), (KEY, anthropic.VERSION, "application/json"))
eq("thân: model, max_tokens, cache_control cấp trên, effort, không tool_choice / thinking / temperature",
	(h0["body"]["model"], h0["body"]["max_tokens"], h0["body"].get("cache_control"), h0["body"]["output_config"],
		[k for k in ("tool_choice", "thinking", "temperature", "top_p") if k in h0["body"]]),
	(MODEL, qa.MAX_TOKENS, {"type": "ephemeral"}, {"effort": anthropic.EFFORT}, []))
eq("công cụ của người xem: chỉ xem_mang", [t["name"] for t in h0["body"]["tools"]], ["xem_mang"])
c("câu hỏi gửi đi: tên khách đã thành mã KH#, dấu câu hỏi còn", h0["body"]["messages"][-1]["content"].startswith(
	"Phải thu của KH#") and MQ in h0["body"]["messages"][-1]["content"], h0["body"]["messages"][-1]["content"])
c("đề bài hệ thống: bối cảnh công ty đã che tên khách + tên người", "BỐI CẢNH CÔNG TY" in h0["body"]["system"]
	and KH_TEN not in h0["body"]["system"] and NGUOI_TEN not in h0["body"]["system"] and "NV#" in h0["body"]["system"])
h1, h2 = hb[1]["body"], hb[2]["body"]
resp0 = json.loads(json.dumps(h1["messages"][1]["content"]))
eq("lượt 2: khối assistant lượt 1 gửi lại NGUYÊN (thinking + chữ + tool_use, đúng thứ tự, đúng chữ ký)",
	json.dumps(h1["messages"][1], ensure_ascii=False), json.dumps({"role": "assistant", "content": resp0}, ensure_ascii=False))
eq("lượt 2: thinking.signature đúng như mô hình trả", h1["messages"][1]["content"][0]["type"], "thinking")
eq("lượt 2: MỘT tin user gồm tool_result đúng tool_use_id", [(x["type"], x["tool_use_id"]) for x in h1["messages"][2]["content"]],
	[("tool_result", h1["messages"][1]["content"][2]["id"])])
eq("lượt 3: hội thoại đủ 5 tin, xen kẽ user / assistant", [m["role"] for m in h2["messages"]],
	["user", "assistant", "user", "assistant", "user"])
eq("lượt 3: assistant lượt 2 cũng gửi lại nguyên (chỉ tool_use)", [b["type"] for b in h2["messages"][3]["content"]],
	["tool_use"])
eq("sources: Công nợ rồi Tồn kho, route #/<mảng>", [(s["section"], s["route"]) for s in ab["sources"]],
	[("cong-no", "#/cong-no"), ("ton-kho", "#/ton-kho")])
eq("steps người xem: hai bước xem_mang, không SQL", [(s["tool"], s.get("ok"), "sql" in s) for s in ab["steps"]],
	[("xem_mang", True, False), ("xem_mang", True, False)])
chua = [s["t"] for s in ab["segments"] if s["u"]]
eq("đúng một con số chưa kiểm: số tự tính", (chua, ab["unverified"]), ([TU_TINH], 1))
c("số làm tròn từ kết quả tra cứu (… triệu) là số đã kiểm", f"{vn_nghin(B['trieu'])} triệu" in chu(ab) and not any(
	vn_nghin(B["trieu"]) in t for t in chua), chu(ab))
c("năm 2026 không bị tính; ngày hôm nay (có trong đề bài hệ thống) là ngày đã kiểm", "năm 2026" in chu(ab)
	and NGAY_HN in chu(ab) and not any("2026" in t for t in chua))
ten_ma = None
if B.get("ma"):
	ten_ma = next((m for m in TEN_DOI_TAC if m in chu(ab)), None)
c("mã khách trong lời đã đổi lại thành tên thật khi hiển thị (không còn KH#)", ten_ma and "KH#" not in chu(ab), chu(ab))
R_B = run_row(rb["id"])
eq("BC AI Run: hoi-dap / hoi-dap, claude, ok, 2 bước, 3 lượt gọi, 1 số chưa kiểm", (R_B.run_type, R_B.step, R_B.provider,
	R_B.status, R_B.signals, json.loads(R_B.kpis), R_B.rejected), ("hoi-dap", "hoi-dap", "claude", "ok", 2, {"goi": 3}, 1))
c("BC AI Run: ≥ 1 số đã kiểm", R_B.insights_ai >= 1, R_B.insights_ai)
eq("BC AI Run: token = cộng usage (gồm ghi + đọc cache), chi phí theo token thực tế (đọc cache × 0,1, ghi × 1,25)",
	(R_B.tokens_in, R_B.tokens_out, round(float(R_B.cost_usd), 6), R_B.cost_known),
	(1200 * 2 + 1500 + 900 + 300, 80 * 2 + 120, round(((1200 * 2 + 1500 + 0.1 * 900 + 1.25 * 300) * 2
		+ (80 * 2 + 120) * 10) / 1e6, 6), 1))
c("BC AI Run.error trống khi ok (không câu hỏi / câu trả lời)", not R_B.error, R_B.error)
g = as_user(VIEWER, api.get_qa)
eq("get_qa sau một câu: used 1, remaining 19; get_answer cũng mang used / remaining", (g["used"], g["remaining"],
	ab["used"], ab["remaining"]), (1, 19, 1, 19))
a_khac = as_user(VIEWER2, api.get_answer, rb["id"])
eq("người khác hỏi id đó → loi, không segments", (a_khac["status"], "segments" in a_khac), ("loi", False))

# ═══════════════════════════════════════════════════════════════════════════
print(f"C. Cùng người xem, ẩn mảng {AN}")
single("BC Settings", hidden_sections=AN)
TOOL_CN = json.dumps(B["cn"], ensure_ascii=False)
SO_CN = {str(int(abs(v))) for v in so(B["cn"]) if abs(v) >= 100_000} - {str(int(abs(v))) for v in so(B["tk"])}
c("có số đặc trưng của kết quả công nợ để soát (≥ 2)", len(SO_CN) >= 2, sorted(SO_CN)[:5])
rc, ac, hc = hoi(VIEWER, f"Phải thu quá hạn bao nhiêu? {MQ}",
	xin(tu("xem_mang", {"mang": "cong-no", "ten": "receivables"}), tu("xem_mang", {"mang": "ton-kho", "ten": "overview"})),
	tra(f"Không có số liệu phải thu. {MA}"))
t0 = hc[0]["body"]["tools"][0]
c("mô tả công cụ + enum không còn mảng ẩn", AN not in t0["input_schema"]["properties"]["mang"]["enum"]
	and f"mang={AN}" not in t0["description"], t0["input_schema"]["properties"]["mang"]["enum"])
kc = hc[1]["body"]["messages"][-1]["content"]
eq("tra mảng ẩn → tool_result is_error; tồn kho vẫn có số", (kc[0].get("is_error"), kc[1].get("is_error")), (True, None))
eq("không số đặc trưng nào của công nợ trong request của lượt này", sorted(s for h in hc for s in SO_CN
	if re.search(r"(?<!\d)" + s + r"(?!\d)", h["data"].decode("utf-8"))), [])
c("đối chứng: request lượt B CÓ số đặc trưng đó (cách dò bắt được)", any(re.search(r"(?<!\d)" + s + r"(?!\d)",
	hb[2]["data"].decode("utf-8")) for s in SO_CN))
eq("sources chỉ Tồn kho", [s["section"] for s in ac["sources"]], ["ton-kho"])
a_ad = as_user(ADMIN, api.get_qa)
c("quản trị vẫn bật (mảng ẩn không áp cho quản trị)", a_ad["enabled"], a_ad)
single("BC Settings", hidden_sections="")

# ═══════════════════════════════════════════════════════════════════════════
print("D. Quản trị: get_schema + run_select trên tài khoản chỉ đọc thật")
eq("get_qa.sql: chưa khai tài khoản → False", as_user(ADMIN, api.get_qa)["sql"], False)
frappe.conf["bc_ai_ro_user"], frappe.conf["bc_ai_ro_password"] = RW_USER, RW_PASS
eq("get_qa.sql: tài khoản có quyền ghi → False (SHOW GRANTS)", as_user(ADMIN, api.get_qa)["sql"], False)
frappe.conf["bc_ai_ro_user"], frappe.conf["bc_ai_ro_password"] = RO_USER, RO_PASS
eq("get_qa.sql: tài khoản chỉ đọc → quản trị True, người xem False", (as_user(ADMIN, api.get_qa)["sql"],
	as_user(VIEWER, api.get_qa)["sql"]), (True, False))
SQL_BAD = "SELECT customer_group, COUNT(*) AS so_khach FROM `tabCustomer` GROUP BY customer_group -- đếm"
SQL_OK = "SELECT customer_group, COUNT(*) AS so_khach FROM `tabCustomer` GROUP BY customer_group ORDER BY customer_group"
SQL_CAM = "SELECT name, net_pay FROM `tabSalary Slip`"
SQL_TEN = "SELECT name, customer_name, owner FROM `tabCustomer` WHERE owner IS NOT NULL ORDER BY name"
D = {}


def d_viet_lai(body):
	r = ket_qua(body)
	D["loi"] = r
	return xin(tu("run_select", {"sql": SQL_OK}), tu("run_select", {"sql": SQL_CAM}), truoc=False)


def d_tra(body):
	ok = json.loads(body["messages"][-3]["content"][0]["content"])
	D["ok"], D["cam"], D["ten"] = ok, body["messages"][-3]["content"][1], json.loads(ket_qua(body)["content"])
	n = next((r[1] for r in ok["rows"] if r[0] == "NPP"), None)
	D["n"] = n
	nv = sorted({r[2] for r in D["ten"]["rows"]})
	return tra(f"Nhóm NPP có {n} khách; người tạo: {', '.join(nv)}. {MA}")


rd, ad, hd = hoi(ADMIN, f"Nhóm NPP có bao nhiêu khách, ai tạo? {MQ}",
	xin(tu("get_schema", {"doctype": "Customer"}), tu("get_schema", {"doctype": "Salary Slip"})),
	xin(tu("run_select", {"sql": SQL_BAD}), truoc=False),
	d_viet_lai,
	xin(tu("run_select", {"sql": SQL_TEN}), truoc=False),
	d_tra)
eq("quản trị: công cụ xem_mang + get_schema + run_select", [t["name"] for t in hd[0]["body"]["tools"]],
	["xem_mang", "get_schema", "run_select"])
sc = hd[1]["body"]["messages"][-1]["content"]
c("get_schema(Customer) trả field; get_schema(Salary Slip) bị từ chối", not sc[0].get("is_error") and "customer_name"
	in sc[0]["content"] and sc[1].get("is_error") is True, sc)
c("câu có chú thích bị từ chối, lý do gửi mô hình", D["loi"].get("is_error") is True and "Lỗi:" in D["loi"]["content"],
	D["loi"])
c("mô hình viết lại → câu nhận được, có dòng NPP", isinstance(D.get("n"), int) and D["n"] >= 2, D.get("ok"))
c("bảng cấm (tabSalary Slip) bị từ chối", D["cam"].get("is_error") is True, D["cam"])
c("ô SQL: tên khách → KH#, owner → NV#", all(r[1].startswith("KH#") and r[2].startswith("NV#") for r in D["ten"]["rows"])
	and D["ten"]["rows"], D["ten"]["rows"][:3])
eq("6 bước tra = trần → lượt 5 buộc trả lời (tool_choice none), các lượt trước không gửi tool_choice",
	[h["body"].get("tool_choice") for h in hd], [None, None, None, None, {"type": "none"}])
eq("get_answer: xong, không số chưa kiểm (số khách có trong kết quả SQL)", (ad["status"], ad["unverified"]), ("xong", 0))
c("lời hiển thị: NV# đổi lại thành tài khoản thật", NGUOI in chu(ad) and "NV#" not in chu(ad), chu(ad))
eq("steps quản trị: get_schema, (Salary Slip bị chặn trước — không liệt kê), 4 run_select kèm SQL + ok",
	[(s["tool"], s.get("ok"), s.get("sql")) for s in ad["steps"]], [("get_schema", True, None),
		("run_select", False, SQL_BAD), ("run_select", True, SQL_OK), ("run_select", False, SQL_CAM),
		("run_select", True, SQL_TEN)])
R_D = run_row(rd["id"])
eq("Run quản trị: 6 bước, 5 lượt gọi, ok", (R_D.status, R_D.signals, json.loads(R_D.kpis)), ("ok", 6, {"goi": 5}))
frappe.conf.pop("bc_ai_ro_user")
frappe.conf.pop("bc_ai_ro_password")

# ═══════════════════════════════════════════════════════════════════════════
print("E. Lỗi: từ chối, hết credit, quá giờ, quá tải, trả lời bị cắt")


def loi_api(status, etype, msg):
	return FakeResp(status, {"type": "error", "error": {"type": etype, "message": msg}, "request_id": "req_x"})


CASES = [
	("từ chối", [resp([], "refusal", usage(900, 5))], qa.M_TU_CHOI, "loi", 1, []),
	("hết credit (400 credit balance) — không thử lại", [loi_api(400, "invalid_request_error",
		"Your credit balance is too low to access the Anthropic API.")], qa.M_CREDIT, "het-credit", 1, []),
	("quá giờ — hỏi đáp không thử lại", [real_requests.exceptions.ReadTimeout("read timed out")], qa.M_GIO,
		"loi", 1, []),
	("quá tải 529 — hỏi đáp không thử lại", [loi_api(529, "overloaded_error", "Overloaded")], qa.M_MO_HINH, "loi", 1, []),
	("trả lời bị cắt (max_tokens)", [resp([think(), {"type": "text", "text": "Phải thu là 1"}], "max_tokens")], qa.M_CAT,
		"loi", 1, []),
]
E_RUN = {}
for ten, buoc, msg, st, n_http, ngu in CASES:
	NGU.clear()
	r, a, hh = hoi(VIEWER3, f"Câu lỗi {ten} {MQ}", *buoc)
	R = E_RUN[ten] = run_row(r["id"])
	eq(f"{ten}: get_answer loi + lời báo; Run {st}; {n_http} lượt HTTP; chờ {ngu}", (a["status"], a.get("message"), R.status,
		len(hh), NGU), ("loi", msg, st, n_http, ngu))
	c(f"{ten}: Run.error là lời ngắn cố định (không câu hỏi, không chữ của API)", R.error and MQ not in R.error
		and "credit balance" not in R.error and len(R.error) <= 60, R.error)
eq("từ chối: token đã tính tiền vẫn ghi vào Run", (E_RUN["từ chối"].tokens_in, E_RUN["từ chối"].tokens_out), (900, 5))
# công cụ ném lỗi có chữ (chép câu hỏi) → Error Log chỉ tên loại + dòng code
import bc.api.kho_ton as _kt  # noqa: E402
_goc = _kt.get_overview


def _hong(*a, **k):
	raise RuntimeError(f"{MT} {MQ} hỏng")


_kt.get_overview = _hong
n_log = len(frappe.LOGGED)
r, a, hh = hoi(VIEWER3, f"Tồn kho? {MQ}", xin(tu("xem_mang", {"mang": "ton-kho", "ten": "overview"})),
	tra(f"Màn tồn kho đang lỗi. {MA}"))
_kt.get_overview = _goc
eq("công cụ hỏng → tool_result lỗi chung cho mô hình, câu vẫn xong", (ket_qua(hh[1]["body"])["content"], a["status"]),
	("Lỗi: màn báo cáo này đang lỗi — không có số liệu", "xong"))
moi = frappe.LOGGED[n_log:]
c("Error Log: có dòng của công cụ hỏng, chỉ tên loại + dòng code (không chữ của lỗi)", moi and all(
	MT not in json.dumps(x, ensure_ascii=False, default=str) and MQ not in json.dumps(x, ensure_ascii=False, default=str)
	for x in moi) and "RuntimeError" in json.dumps(moi, ensure_ascii=False, default=str), moi)

# ═══════════════════════════════════════════════════════════════════════════
print("F. Giới hạn")
eq("câu rỗng / quá 500 ký tự bị từ chối", (tu_choi(VIEWER2, "   "), tu_choi(VIEWER2, "x" * 501)), (qa.M_TRONG, qa.M_DAI))
frappe.ENQUEUE_RUN = False
i0 = len(frappe.ENQUEUED)
r1 = as_user(VIEWER2, api.ask, f"Câu đầu {MQ}")
eq("câu thứ hai khi câu đầu chưa xong → từ chối", tu_choi(VIEWER2, f"Câu hai {MQ}"), qa.M_BAN)
eq("câu đầu đang chờ → get_answer cho", as_user(VIEWER2, api.get_answer, r1["id"]), {"status": "cho"})
frappe.ENQUEUE_RUN = True
KB["buoc"] = [tra(f"Xong câu đầu. {MA}")]
m, _o, kw = frappe.ENQUEUED[i0]
eq("job: bc.ai.qa.run, hàng default, timeout 300", (m, _o["queue"], _o["timeout"]), ("bc.ai.qa.run", "default", 300))
as_user(VIEWER2, frappe.get_attr(m), **kw)
eq("chạy job → xong; hỏi tiếp được", as_user(VIEWER2, api.get_answer, r1["id"])["status"], "xong")
# 7 lượt gọi tối đa: mô hình xin tra mãi, mỗi lượt một bước
n0 = len(HTTP)


def mai(body):
	if body.get("tool_choice") == {"type": "none"}:
		return tra(f"Hết lượt tra. {MA}")
	return xin(tu("xem_mang", {"mang": "thang", "ten": "monthly"}), truoc=False)


r7, a7, h7 = hoi(VIEWER2, f"Tra mãi {MQ}", *([mai] * 7))
eq("xin tra mãi: đúng 7 lượt gọi, chỉ lượt cuối buộc trả lời; 6 bước", ([h["body"].get("tool_choice") for h in h7],
	run_row(r7["id"]).signals), ([None] * 6 + [{"type": "none"}], 6))
TU4 = [("thang", "monthly"), ("tong-quan", "summary"), ("tong-quan", "channels"), ("tinh-thanh", "provinces")]
r8, a8, h8 = hoi(VIEWER3, f"Tra nhiều một lượt {MQ}",
	xin(*[tu("xem_mang", {"mang": m, "ten": t}) for m, t in TU4], truoc=False),
	xin(*[tu("xem_mang", {"mang": m, "ten": t}) for m, t in TU4], truoc=False),
	tra(f"Đủ rồi. {MA}"))
k8 = h8[2]["body"]["messages"][-1]["content"]
eq("4 + 4 khối tool_use: khối 7, 8 nhận lỗi 'đã hết lượt tra', lượt 3 buộc trả lời, Run 6 bước",
	([x.get("is_error") for x in k8], k8[2]["content"], h8[2]["body"].get("tool_choice"), run_row(r8["id"]).signals),
	([None, None, True, True], f"Lỗi: đã hết {qa.MAX_STEPS} lượt tra cứu — trả lời bằng số đã có", {"type": "none"}, 6))
single("BC Settings", ai_qa_per_day=2)
g = as_user(VIEWER2, api.get_qa)
eq("ai_qa_per_day 2: VIEWER2 đã hỏi 2 câu (câu bị từ chối lúc hỏi không tính) → còn 0, câu thứ 3 bị từ chối",
	(g["used"], g["remaining"], tu_choi(VIEWER2, f"Câu ba {MQ}")), (2, 0, qa.M_HET_LUOT.format(n=2)))
single("BC Settings", ai_qa_per_day=20)
single("BC Settings", ai_cap_claude_usd=0)
eq("trần chi Claude 0 → từ chối", tu_choi(VIEWER2, f"Vượt trần {MQ}"), qa.M_TRAN)
single("BC Settings", ai_cap_claude_usd=90)
nay = __import__("frappe.utils", fromlist=["x"]).now_datetime()   # "hôm nay" của qa (bộ thử có thể đặt ngày giả)
x = insert(RUN, run_type="hoi-dap", step="hoi-dap", provider="claude", status="ok", started=nay, finished=nay,
	owner="khac@example.com", kpis=json.dumps({"goi": 300}))
eq("300 lượt gọi hỏi đáp / ngày đã dùng → từ chối", tu_choi(VIEWER2, f"Quá lượt gọi {MQ}"), qa.M_QUA_GOI)
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE owner = 'khac@example.com'")
co = qa._dem()
for i in range(qa.SITE_PER_DAY - co):
	insert(RUN, run_type="hoi-dap", step="hoi-dap", provider="claude", status="ok", started=nay, finished=nay,
		owner="khac@example.com", kpis=json.dumps({"goi": 0}))
eq("200 câu / ngày toàn site → từ chối", tu_choi(VIEWER2, f"Quá site {MQ}"), qa.M_HET_SITE)
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE owner = 'khac@example.com'")
c("lượt gọi hỏi đáp không ăn 30 lượt / ngày của lượt sáng", __import__("bc.ai.budget", fromlist=["x"]).calls_today(
	"claude") == 0 and __import__("bc.ai.budget", fromlist=["x"]).qa_calls_today() > 0)

# ═══════════════════════════════════════════════════════════════════════════
print("G. ai_qa_enabled = 0: mọi lối vào từ chối, không lượt gọi mô hình nào")
frappe.ENQUEUE_RUN = False
i0 = len(frappe.ENQUEUED)
rg = as_user(VIEWER3, api.ask, f"Câu xếp trước khi tắt {MQ}")
single("BC Settings", ai_qa_enabled=0)
n_http = len(HTTP)
KB["buoc"] = []
eq("get_qa: enabled False (người xem + quản trị)", (as_user(VIEWER3, api.get_qa)["enabled"],
	as_user(ADMIN, api.get_qa)["enabled"]), (False, False))
eq("ask → từ chối 'đang tắt'", (tu_choi(VIEWER, f"Hỏi khi tắt {MQ}"), tu_choi(ADMIN, f"Hỏi khi tắt {MQ}")), (qa.M_TAT,) * 2)
frappe.ENQUEUE_RUN = True
m, _o, kw = frappe.ENQUEUED[i0]
as_user(VIEWER3, frappe.get_attr(m), **kw)
ag = as_user(VIEWER3, api.get_answer, rg["id"])
eq("job đã xếp trước khi tắt → không gọi mô hình, loi 'đang tắt', Run tat", (ag["status"], ag.get("message"),
	run_row(rg["id"]).status), ("loi", qa.M_TAT, "tat"))
eq("get_answer id lạ → loi", as_user(VIEWER3, api.get_answer, "khong-co")["status"], "loi")
eq("không lượt HTTP nào khi tắt", len(HTTP) - n_http, 0)
single("BC Settings", ai_qa_enabled=1)

# ═══════════════════════════════════════════════════════════════════════════
print(f"H. Riêng tư trên MỌI thân request ({len(HTTP)} lượt) và trên CSDL / Error Log / cache")
DATA = [h["data"].decode("utf-8") for h in HTTP]
c("đủ request để soát (≥ 25)", len(DATA) >= 25, len(DATA))
eq("không tên khách / NCC / chuỗi MT", sorted({t for d in DATA for t in TEN_DOI_TAC if t in d}), [])
eq("không tên người / email / nhân viên", sorted({t for d in DATA for t in NGUOI_DS if t in d}), [])
eq("không khoá, không tài khoản / mật khẩu chỉ đọc (cả tài khoản có quyền ghi)", sorted({t for d in DATA
	for t in (KEY, "sk-ant", RO_USER, RO_PASS, RW_USER, RW_PASS) if t in d}), [])
eq("khoá chỉ ở header x-api-key", sorted({k for h in HTTP for k, v in h["headers"].items() if KEY in str(v)}), ["x-api-key"])
c("mã giả có trong request (che tên thật sự chạy)", any("KH#" in d for d in DATA) and any("NV#" in d for d in DATA))
c("không mạng suốt bộ thử", not MANG, MANG)

# CSDL: mọi cột chữ của mọi bảng
cols = frappe.db.sql("""SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = %s
	AND data_type IN ('char', 'varchar', 'text', 'mediumtext', 'longtext', 'tinytext', 'json')""", (DB,))
bang = {}
for t, col in cols:
	bang.setdefault(t, []).append(col)
MAU = [MQ, MA, MT, TU_TINH, KEY, RO_PASS, RW_PASS, "Để tôi tra số liệu", '"tool_use_id"', '"_cat"',
	TOOL_CN[:80], json.dumps(B["tk"], ensure_ascii=False)[:80], SQL_TEN, "BỐI CẢNH CÔNG TY"]
lo = []
for t, cs in bang.items():
	where = " OR ".join(f"`{x}` LIKE %(m)s" for x in cs)
	for m in MAU:
		if frappe.db.sql(f"SELECT COUNT(*) FROM `{t}` WHERE {where}", {"m": "%" + m.replace("%", r"\%").replace("_", r"\_")
				+ "%"})[0][0]:
			lo.append((t, m[:30]))
c("soát đủ bảng (≥ 100 bảng có cột chữ, có tabBC AI Run)", len(bang) >= 100 and "tabBC AI Run" in bang, len(bang))
eq("không câu hỏi / câu trả lời / kết quả tra cứu / đề bài / khoá / mật khẩu trong bảng nào", lo, [])
LOG = json.dumps(frappe.LOGGED, ensure_ascii=False, default=str)
eq("Error Log: không mẩu nào", [m[:30] for m in MAU if m in LOG], [])
# Cache: chỉ câu trả lời của chính người hỏi (khoá bcai:qa:ans:<người hỏi>:<id>) mang chữ trả lời; câu hỏi không ở đâu
store = frappe.cache().store
eq("không khoá cache nào chứa mẩu câu hỏi / trả lời", [k for k in store if any(m in k for m in (MQ, MA, TU_TINH))], [])
eq("không giá trị cache nào chứa câu hỏi / kết quả tra cứu / khoá", sorted({m[:30] for v in store.values()
	for m in (MQ, MT, KEY, RO_PASS, "Để tôi tra số liệu", '"tool_use_id"', TOOL_CN[:80]) if m in v}), [])
co_tra_loi = sorted(k for k, v in store.items() if MA in v)
c("chữ trả lời chỉ nằm dưới khoá bcai:qa:ans:<người hỏi>:<id> của câu đó", co_tra_loi and all(re.fullmatch(
	r"bcai:qa:ans:[^:]+:[\w\-]+", k) for k in co_tra_loi) and f"bcai:qa:ans:{VIEWER}:{rb['id']}" in co_tra_loi,
	co_tra_loi[:4])
c("khoá của câu B mang đúng người hỏi (người khác không có khoá cho id đó)", not any(k.endswith(":" + rb["id"])
	and f":{VIEWER}:" not in k for k in store))

for u in (RO_USER, RW_USER):
	frappe.db.sql(f"DROP USER IF EXISTS '{u}'@'localhost'")
frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
