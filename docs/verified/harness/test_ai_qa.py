"""Trợ lý AI P3 — hỏi đáp (bc.ai.qa + bc.api.ai.get_qa / ask / get_answer), SPEC_bc_ai_p3 §10 điểm 2, 5, 6, 7.

Mọi câu hỏi đi ĐÚNG đường thật: bc.api.ai.ask (guard) → qa.start → frappe.enqueue (bộ thử chạy thẳng job, hoặc giữ lại
khi ENQUEUE_RUN = False) → qa.run dưới người hỏi → bc.api.ai.get_answer. Module thật: collect.CALLS, bc.api.* (seed gộp
seed_ui2), redact, prompt, budget, store, sqlguard, sqlro (tài khoản MariaDB chỉ đọc THẬT tạo cho bộ thử, xoá khi xong).
Chỉ thay cửa mạng bc.ai.llm.chat bằng mô hình giả chạy theo kịch bản và CHÉP mọi request (bản sao sâu). Socket ra ngoài
bị chặn.

Phần:
  A dựng     B danh mục + kiểm tham số + mô tả công cụ theo vai / mảng ẩn     C vòng lặp (khối gửi lại nguyên, mọi
  tool_result trong MỘT tin, ≤ 6 bước, ≤ 7 lượt, buộc trả lời, 150 giây, lỗi)     D đối chiếu số (bảng ≥ 40 dòng + qua
  câu hỏi thật)     E che tên (khách / NCC / người, tên gõ trong câu hỏi, tên một từ ngắn, lịch sử, bối cảnh)     F
  quản trị: get_schema / run_select (chỉ đọc thật, cột người → NV#, câu bị chặn, tài khoản có quyền ghi)     G giới hạn +
  mọi lý do từ chối     H riêng tư (không gì của câu hỏi / câu trả lời / kết quả trong bảng / log; khoá + mật khẩu không
  lọt; người khác không đọc được câu trả lời; 30 phút)     I lượt gọi hỏi đáp không ăn 30 lượt / ngày của lượt sáng.

Chạy: BC_TEST_DB=bc_test_ai_qa python3 -B test_ai_qa.py
"""
import copy
import datetime
import itertools
import json
import re
import socket
import time as _time
import types

# ─── Chặn mạng (trước mọi import có thể nối) ───────────────────────────────
MANG = []
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo


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

c = Check()
RUN = "BC AI Run"
KEY = "sk-ant-api03-KHOAGIA-p3qa-Hq72Lm"
MODEL = "claude-sonnet-5-5"
VIEWER, VIEWER2, VIEWER3, ADMIN = "viewer@example.com", "viewer2.qa@example.com", "viewer3.qa@example.com", "Administrator"
RO_USER, RO_PASS = "bc_ai_ro_p3g", "RoPass-p3g-Zq81Xw"
RW_USER, RW_PASS = "bc_ai_rw_p3g", "RwPass-p3g-Kk55Pt"
KH_DAI, KH_DAI_ID = "Công ty Tân Phát Lộc", "KH-TAN-PHAT"
KH_NGAN, KH_NGAN_ID = "Tâm", "KH-TAM"                  # tên khách MỘT từ ngắn
KH_SO, KH_SO_ID = "Đại lý 365", "KH-365"               # tên khách có chữ số
NCC_TEN, NCC_ID = "Nhà cung cấp Hoà Bình Xanh", "NCC-HOA-BINH"
NGUOI, NGUOI_TEN = "ke.toan.qa@hgc.vn", "Trần Thị Kế Toán"
NV_TEN = "Phạm Văn Kiểm Định"
MARK_Q, MARK_A = "MARKQ7731", "MARKA5512"           # dấu của câu hỏi / câu trả lời — không được nằm trong bảng / log


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


# ═══════════════════════════════════════════════════════════════════════════
print("A. Dựng: seed gộp, khách / NCC / người có tên riêng, mô hình giả, đồng hồ giả")
import seed_ui2  # noqa: E402,F401

insert("Customer", name=KH_DAI_ID, customer_name=KH_DAI, customer_group="NPP", owner=NGUOI, modified_by=NGUOI)
insert("Customer", name=KH_NGAN_ID, customer_name=KH_NGAN, customer_group="NPP", owner=NGUOI)
insert("Customer", name=KH_SO_ID, customer_name=KH_SO, customer_group="NPP", owner=NGUOI)
insert("Supplier", name=NCC_ID, supplier_name=NCC_TEN)
NGUOI_LA = "nguoi.la@ngoai.vn"                       # người KHÔNG có tài khoản / hồ sơ: chỉ luật theo tên cột che được
insert("Customer", name="KH-LA", customer_name="Khách Lạ Phương Xa", customer_group="NPP", modified_by=NGUOI_LA)
insert("User", name=NGUOI, enabled=1, first_name="Trần Thị", last_name="Kế Toán", full_name=NGUOI_TEN)
insert("Employee", name="HR-EMP-QA1", employee_name=NV_TEN, first_name="Phạm", status="Active", department="Kho")
frappe.ROLES[VIEWER2] = ["BC Viewer"]
frappe.ROLES[VIEWER3] = ["BC Viewer"]
single("BC Settings", ai_qa_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, hidden_sections="",
	ai_claude_model=MODEL, ai_context=f"Khách lớn nhất là {KH_DAI}; chú ý {KH_NGAN}.")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [{"model": MODEL, "price_in": 3, "price_out": 15}])
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.conf["db_name"] = DB
frappe.conf["db_socket"] = SOCK

from bc.ai import budget, collect, llm, qa, store  # noqa: E402
from bc.api import ai as api  # noqa: E402
IN_KEY = getattr(qa, "IN_KEY", "bcai:qa:in")   # getattr: bộ thử chạy được trên bản trước khi sửa (BC_APP_ROOT) để thấy đỏ

# Đồng hồ giả của qa (monotonic: hạn 150 giây; time: hạn cache 30 phút / khoá đang hỏi)
LECH = {"mono": 0.0, "time": 0.0, "dung": False}   # dung: đồng hồ monotonic chỉ chạy theo LECH (đo chính xác)
qa.time = types.SimpleNamespace(monotonic=lambda: (0.0 if LECH["dung"] else _time.monotonic()) + LECH["mono"],
	time=lambda: _time.time() + LECH["time"])

REQ = []          # mọi request gửi "mô hình" (bản sao sâu)
KB = {"f": None}  # kịch bản hiện tại
_ID = itertools.count(1)


def fake_chat(provider, model, system, messages, tools, max_tokens=2000, timeout=60, tool_choice=None, retries=None):
	REQ.append(copy.deepcopy({"provider": provider, "model": model, "system": system, "messages": messages,
		"tools": tools, "max_tokens": max_tokens, "timeout": timeout, "tool_choice": tool_choice, "retries": retries}))
	return KB["f"](REQ[-1])


llm.chat = fake_chat


def tu(name, inp):
	return {"type": "tool_use", "id": f"toolu_{next(_ID):04d}", "name": name, "input": inp}


def dung(*uses, truoc=(), ti=1000, to=50):
	"""Lượt mô hình xin tra (các khối tool_use, có thể kèm khối trước)."""
	return {"content": [*copy.deepcopy(list(truoc)), *uses], "stop_reason": "tool_use", "tokens_in": ti, "tokens_out": to,
		"cost_tokens_in": float(ti), "model": MODEL}


def tra(text, ti=1000, to=50):
	return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "tokens_in": ti, "tokens_out": to,
		"cost_tokens_in": float(ti), "model": MODEL}


def kb(*buoc):
	"""Kịch bản: mỗi phần tử là response hoặc hàm(req) → response / ném."""
	it = iter(buoc)

	def f(req):
		try:
			b = next(it)
		except StopIteration:
			raise RuntimeError("kịch bản hết mà mô hình còn bị gọi")
		return b(req) if callable(b) else b
	KB["f"] = f


def kq(req, i=0):
	"""Khối tool_result thứ i của tin user cuối trong request."""
	return req["messages"][-1]["content"][i]


def kq_json(req, i=0):
	return json.loads(kq(req, i)["content"])


def as_user(u, fn, *a, **k):
	cu = frappe.session.user
	frappe.session.user = u
	try:
		return fn(*a, **k)
	finally:
		frappe.session.user = cu


def hoi(user, q, *buoc, history=None):
	"""Một câu hỏi trọn vẹn qua API → (kết quả ask, get_answer, các request của câu này)."""
	kb(*buoc)
	n0 = len(REQ)
	r = as_user(user, api.ask, q, json.dumps(history) if history is not None else None)
	a = as_user(user, api.get_answer, r["id"])
	return r, a, REQ[n0:]


def tu_choi(user, q, history=None):
	"""ask bị từ chối → lời báo (None nếu không bị từ chối)."""
	try:
		as_user(user, api.ask, q, history)
	except frappe.ValidationError as e:
		return str(e)
	return None


def chu(a):
	return "".join(s["t"] for s in a.get("segments") or [])


def chua_kiem(a):
	return [s["t"] for s in a.get("segments") or [] if s["u"]]


def run_row(qid):
	r = frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE name = %s", (qid,), as_dict=True)
	return r[0] if r else None


def vn(x, d=1):
	return f"{x:.{d}f}".replace(".", ",")


def trieu(v):
	return f"{round(v / 1e6)} triệu"


# Gián điệp trên mọi method của danh mục: ghi kwargs (soát refresh), cho phép ném lỗi
GOI_API = []
LOI_API = {}
for (s, n), dotted in qa.catalog().items():
	mod_name, fn_name = dotted.split(".")
	mod = __import__(f"bc.api.{mod_name}", fromlist=[fn_name])
	goc = getattr(mod, fn_name)
	if getattr(goc, "_gian_diep", False):
		continue

	def boc(*a, _goc=goc, _d=dotted, **k):
		GOI_API.append((_d, frappe.session.user, dict(k)))
		if _d in LOI_API:
			raise LOI_API[_d]
		return _goc(*a, **k)
	boc._gian_diep = True
	setattr(mod, fn_name, boc)

c("không mạng khi dựng", not MANG, MANG)

# ═══════════════════════════════════════════════════════════════════════════
print("B. Danh mục công cụ, kiểm tham số, mô tả theo vai / mảng ẩn")
cat = qa.catalog()
eq("danh mục = collect.CALLS bỏ khối kỳ trước (25 khối, đúng method)", cat,
	{(s, n): d for s, n, d, _f in collect.CALLS if (s, n) != ("van-chuyen", "overview_truoc")})
eq("25 khối, 17 mảng", (len(cat), len({s for s, _ in cat})), (25, 17))
SAI = [
	(("cong-no", "receivables"), {"refresh": 1}), (("tong-quan", "summary"), {"refresh": 0}),
	(("tong-quan", "top_customers"), {"limit": 0}), (("tong-quan", "top_customers"), {"limit": 21}),
	(("tong-quan", "top_customers"), {"limit": "5"}), (("tong-quan", "top_customers"), {"limit": True}),
	(("tong-quan", "top_customers"), {"limit": 5.0}), (("tong-quan", "top_customers"), {"limit": 5, "refresh": 1}),
	(("ngay", "daily"), {"year": 1999}), (("ngay", "daily"), {"year": 2101}), (("ngay", "daily"), {"month": 0}),
	(("ngay", "daily"), {"month": 13}), (("ngay", "daily"), {"month": "10"}), (("ngay", "daily"), {"day": 1}),
	(("san-pham", "top_products"), {"group": ""}), (("san-pham", "top_products"), {"group": "x" * 61}),
	(("san-pham", "top_products"), {"group": 5}), (("san-pham", "top_products"), {"group": "Hàng Tết"}),
	(("san-pham", "top_products"), {"group": "TET"}), (("sx-tet", "items"), {"from_date": "2027-06-01"}),
	(("sx-tet", "items"), {"to_date": "2020-01-01"}), (("sx-tet", "items"), {"from_date": "2020-01-01", "to_date": "2026-10-01"}),
	(("sx-tet", "items"), {"from_date": "2024-01-01", "to_date": "2026-01-02"}), (("sx-tet", "items"), {"from_date": "2026-13-01"}),
	(("sx-tet", "items"), {"from_date": "26-1-1"}), (("sx-tet", "items"), {"to_date": "2026-02-30"}),
	(("sx-tet", "items"), {"from_date": "2026-03-01", "to_date": "2026-02-01"}),
	(("kiem-ke", "overview"), {"thang": "2026-13"}), (("kiem-ke", "overview"), {"thang": "2026-1"}),
	(("san-xuat", "overview"), {"thang": "2026-10-01"}), (("san-xuat", "overview"), {"date": "2026-10-01"}),
	(("san-xuat", "compare"), {"thang": "2026-13"}), (("san-xuat", "compare"), {"refresh": 1}),
	(("san-xuat", "compare"), {"date": "2026-10-01"}), (("san-xuat", "compare"), {"thang": "2099-01"}),
	(("van-chuyen", "overview"), {"thang": 202610}), (("attp", "report"), {"thang": "10/2026"}),
	(("tong-quan", "summary"), []), (("tong-quan", "summary"), "limit=5"), (("cong-no", "receivables"), {"thang": "2026-10"}),
]
lot = [(k, ts) for k, ts in SAI if qa.check_params(k, ts)[0] is not None]
eq(f"{len(SAI)} bộ tham số lạ / sai kiểu / ngoài khoảng / có refresh bị từ chối (có lời)", lot, [])
c("lời từ chối không rỗng", all(qa.check_params(k, ts)[1] for k, ts in SAI))
DUNG = [
	(("tong-quan", "summary"), None, {}), (("tong-quan", "summary"), {}, {}),
	(("tong-quan", "top_customers"), {"limit": 20}, {"limit": 20}), (("tong-quan", "top_customers"), {"limit": 1}, {"limit": 1}),
	(("ngay", "daily"), {"year": 2026, "month": 10}, {"year": 2026, "month": 10}),
	(("san-pham", "top_products"), {"group": " tet "}, {"group": "tet"}),
	(("san-pham", "top_products"), {"group": "traditional"}, {"group": "traditional"}),
	(("sx-tet", "items"), {"from_date": "2024-01-01", "to_date": "2026-01-01"}, {"from_date": "2024-01-01", "to_date": "2026-01-01"}),
	(("sx-tet", "items"), {"from_date": "2025-08-01", "to_date": "2026-02-28"}, {"from_date": "2025-08-01", "to_date": "2026-02-28"}),
	(("kiem-ke", "overview"), {"thang": "2026-09"}, {"thang": "2026-09"}),
	(("san-xuat", "overview"), {"thang": "2026-09"}, {"thang": "2026-09"}),
	(("san-xuat", "compare"), {"thang": "2026-09"}, {"thang": "2026-09"}), (("san-xuat", "compare"), {}, {}),
	(("attp", "report"), {"thang": "2026-10"}, {"thang": "2026-10"}),
]
eq("tham số hợp lệ được nhận đúng (chuỗi đã gọt)", [qa.check_params(k, ts) for k, ts, _w in DUNG], [(w, "") for _k, _t, w in DUNG])

T_VIEW = as_user(VIEWER, lambda: qa.tools(qa.visible_sections(VIEWER)))
eq("người xem: chỉ công cụ xem_mang", [t["name"] for t in T_VIEW], ["xem_mang"])
c("mô tả công cụ nêu mọi mảng của danh mục khi không ẩn gì", all(f"mang={s} " in T_VIEW[0]["description"]
	for s, _ in cat) and T_VIEW[0]["input_schema"]["properties"]["mang"]["enum"] == list(dict.fromkeys(s for s, _ in cat)))
single("BC Settings", hidden_sections="cong-no\nnhan-su")
T_AN = as_user(VIEWER, lambda: qa.tools(qa.visible_sections(VIEWER)))
T_AN_ADMIN = as_user(ADMIN, lambda: qa.tools(qa.visible_sections(ADMIN)))
c("người xem có mảng ẩn: mô tả + enum KHÔNG nêu mảng đó", "mang=cong-no" not in T_AN[0]["description"]
	and "mang=nhan-su" not in T_AN[0]["description"] and not {"cong-no", "nhan-su"}
	& set(T_AN[0]["input_schema"]["properties"]["mang"]["enum"]) and "mang=phai-tra" in T_AN[0]["description"])
c("quản trị (cùng cài đặt ẩn): vẫn nêu mọi mảng — như màn quản trị thấy", "mang=cong-no" in T_AN_ADMIN[0]["description"]
	and "mang=nhan-su" in T_AN_ADMIN[0]["description"])
single("BC Settings", hidden_sections="")
c("mô tả công cụ không có chữ refresh", "refresh" not in json.dumps(T_VIEW, ensure_ascii=False))
c("mô tả công cụ: group của top_products là all | tet | traditional, sx-tet nêu luật hai ngày", "group: một trong all | tet | "
	"traditional" in T_VIEW[0]["description"] and "≤ 731 ngày" in T_VIEW[0]["description"])
n_log = len(frappe.LOGGED)
LOI_API["kd.get_top_products"] = frappe.ValidationError("Nhóm không hợp lệ")
cau_ = qa._Cau("x", VIEWER, False)
x_ = as_user(VIEWER, qa._xem_mang, cau_, "t1", {"mang": "san-pham", "ten": "top_products"}, ["san-pham"], None)
LOI_API.clear()
c("method từ chối tham số (ValidationError) → 'tham số không hợp lệ' cho mô hình, KHÔNG Error Log, không 'màn đang lỗi'",
	x_.get("is_error") and "tham số không hợp lệ" in x_["content"] and len(frappe.LOGGED) == n_log, (x_, frappe.LOGGED[n_log:]))

# ═══════════════════════════════════════════════════════════════════════════
print("C. Một câu hỏi trọn vẹn (người xem) + tham số sai tới tận mô hình")
GOI_API.clear()
r, a, rq = hoi(VIEWER, f"Phải thu hiện bao nhiêu? {MARK_Q}",
	dung(tu("xem_mang", {"mang": "cong-no", "ten": "receivables", "tham_so": {"refresh": 1}})),
	dung(tu("xem_mang", {"mang": "tong-quan", "ten": "top_customers", "tham_so": {"limit": 99}}),
		tu("xem_mang", {"mang": "khong-co", "ten": "x"}), tu("xem_he_thong", {"lenh": "ls"})),
	dung(tu("xem_mang", {"mang": "cong-no", "ten": "receivables"})),
	lambda req: tra(f"Phải thu {trieu(kq_json(req)['kpis']['receivable'])}, quá hạn "
		f"{vn(kq_json(req)['kpis']['overdue_pct'])}%. {MARK_A}"))
eq("ask → {id, status cho}", sorted(r), ["id", "status"])
eq("trạng thái xong", a["status"], "xong")
eq("4 lượt gọi", len(rq), 4)
k1 = kq(rq[1])
c("tham số refresh → tool_result is_error, có lời", k1.get("is_error") is True and "refresh" in k1["content"], k1)
k2 = rq[2]["messages"][-1]["content"]
eq("lượt có 3 khối tool_use → MỘT tin user với 3 tool_result, đúng thứ tự id, đều lỗi",
	[(x["type"], x["tool_use_id"], x.get("is_error")) for x in k2],
	[("tool_result", b["id"], True) for b in rq[2]["messages"][-2]["content"]])
eq("method thật chỉ được gọi cho lượt tham số đúng, KHÔNG BAO GIỜ có refresh",
	[(d, u, kw) for d, u, kw in GOI_API], [("cn.get_receivables", VIEWER, {})])
K = kq_json(rq[3])
c("kết quả công cụ là payload của màn (đã cắt / che), có kpis", "kpis" in K and "receivable" in K["kpis"], sorted(K)[:8])
eq("không số nào chưa kiểm (số chép từ kết quả, đã làm tròn)", chua_kiem(a), [])
c("lời giữ nguyên chữ của mô hình", chu(a).startswith("Phải thu ") and chu(a).endswith(MARK_A), chu(a))
eq("nguồn đã tra: Phải thu → #/cong-no", a["sources"], [{"section": "cong-no", "label": "Phải thu", "route": "#/cong-no"}])
eq("bước: chỉ bước đã chạy, người xem không có sql", [(s["tool"], s["label"], "sql" in s) for s in a["steps"]],
	[("xem_mang", "Phải thu", False)])
row = run_row(r["id"])
eq("dòng Run: hoi-dap / hoi-dap / claude / ok, signals = 5 bước, 4 lượt gọi, 2 số đã kiểm, 0 chưa kiểm, owner",
	(row.run_type, row.step, row.provider, row.status, row.signals, json.loads(row.kpis), row.insights_ai, row.rejected,
		row.owner, row.model), ("hoi-dap", "hoi-dap", "claude", "ok", 5, {"goi": 4}, 2, 0, VIEWER, MODEL))
eq("dòng Run: token cộng dồn 4 lượt, chi phí theo giá model", (row.tokens_in, row.tokens_out, round(float(row.cost_usd), 6),
	row.cost_known), (4000, 200, round((4000 * 3 + 200 * 15) / 1e6, 6), 1))
eq("dòng Run không lời lỗi", row.error, None)
eq("job xếp hàng default, timeout 300, CHỈ qid + user (câu hỏi / lịch sử không nằm trong tham số job — RQ giữ tham "
	"số 10 phút / 7 ngày, màn RQ Job hiện chúng)", (frappe.ENQUEUED[-1][0], frappe.ENQUEUED[-1][1]["queue"],
	frappe.ENQUEUED[-1][1]["timeout"], sorted(frappe.ENQUEUED[-1][2])), ("bc.ai.qa.run", "default", 300, ["qid", "user"]))
c("không chữ nào của câu hỏi trong mọi tham số job đã xếp", not any(MARK_Q in json.dumps(kw, ensure_ascii=False)
	for _m, _c, kw in frappe.ENQUEUED))
c("câu hỏi chờ job nằm trong cache đã bị job xoá ngay khi đọc", not any(k.startswith(IN_KEY) for k in frappe.cache().store))
R0 = rq[0]
eq("request: provider claude, model của ngày (ai_qa_model trống), max_tokens 6000 (gồm phần suy nghĩ), tool_choice auto",
	(R0["provider"], R0["model"], R0["max_tokens"], R0["tool_choice"]), ("claude", MODEL, 6000, None))
c("đề bài hệ thống: luật trả lời + ngày + năm tài chính, không số liệu kinh doanh", "LUẬT TRẢ LỜI" in R0["system"]
	and "27/10/2026" in R0["system"] and "Năm tài chính" in R0["system"] and str(int(K["kpis"]["receivable"]))
	not in R0["system"])
eq("tin đầu = câu hỏi (chuỗi)", R0["messages"], [{"role": "user", "content": f"Phải thu hiện bao nhiêu? {MARK_Q}"}])
c("timeout mỗi lượt ≤ 60 giây", all(0 < q["timeout"] <= 60 for q in rq), [q["timeout"] for q in rq])

single("BC Settings", ai_qa_model="claude-opus-5-5")
_r, _a, rq2 = hoi(VIEWER, "Doanh số?", tra("Không có số liệu."))
eq("ai_qa_model đặt → dùng model đó", [q["model"] for q in rq2], ["claude-opus-5-5"])
single("BC Settings", ai_qa_model="")

# ═══════════════════════════════════════════════════════════════════════════
print("C2. Khối của lượt trước gửi lại NGUYÊN; ≤ 6 bước; ≤ 7 lượt; buộc trả lời bằng tool_choice none")
THINK = {"type": "thinking", "thinking": "Cần tra phải thu.", "signature": "c2lnbmF0dXJl=="}
LA = {"type": "text", "text": "Để tôi tra.", "citations": None}
b1 = tu("xem_mang", {"mang": "phai-tra", "ten": "payables"})
b1["caller"] = {"type": "direct"}
_r, a, rq = hoi(VIEWER, "Phải trả?", dung(b1, truoc=(THINK, LA)), tra("Xong."))
eq("lượt sau gửi lại NGUYÊN mọi khối của assistant (thinking, text, tool_use kèm trường lạ)",
	rq[1]["messages"][1], {"role": "assistant", "content": [THINK, LA, b1]})
eq("rồi MỘT tin user chỉ gồm tool_result", [x["type"] for x in rq[1]["messages"][2]["content"]], ["tool_result"])

bs = [dung(tu("xem_mang", {"mang": "tong-quan", "ten": "summary"})) for _ in range(6)]
_r, a, rq = hoi(VIEWER, "Tra mãi", *bs, tra("Trả lời bằng số đã có."))
eq("6 lượt xin tra rồi lượt 7 bị buộc trả lời: tool_choice none đúng ở lượt 7", [q["tool_choice"] for q in rq],
	[None] * 6 + [{"type": "none"}])
eq("lượt buộc trả lời VẪN gửi đủ công cụ", [t["name"] for t in rq[-1]["tools"]], ["xem_mang"])
row = run_row(_r["id"])
eq("Run: 6 bước, 7 lượt gọi, ok", (row.signals, json.loads(row.kpis), row.status), (6, {"goi": 7}, "ok"))

_r, a, rq = hoi(VIEWER, "Tra song song", dung(*[tu("xem_mang", {"mang": "tong-quan", "ten": n}) for n in
	("summary", "channels", "item_groups", "top_customers")]), dung(*[tu("xem_mang", {"mang": "thang", "ten": "monthly"})
	for _ in range(4)]), tra("Đủ."))
eq("4 + 4 khối: 6 bước chạy, 2 khối thừa nhận lỗi 'hết lượt tra cứu', lượt kế bị buộc trả lời",
	([x.get("is_error", False) for x in rq[2]["messages"][-1]["content"]], rq[2]["tool_choice"], run_row(_r["id"]).signals),
	([False, False, True, True], {"type": "none"}, 6))
c("lời lỗi hết lượt nói rõ", "hết 6 lượt tra cứu" in rq[2]["messages"][-1]["content"][3]["content"])

_r, a, rq = hoi(VIEWER, "Cứng đầu", *[dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})) for _ in range(7)])
eq("mô hình vẫn xin tra ở lượt bị buộc (không chữ) → loi, đúng 7 lượt, không quá", (a["status"], len(rq)), ("loi", 7))
eq("lời báo: không đưa ra câu trả lời", a["message"], qa.M_KHONG_LOI)

print("C3. 150 giây toàn câu")


def cham(resp, giay):
	def f(req):
		LECH["mono"] += giay
		return resp
	return f


LECH["mono"], LECH["dung"] = 0.0, True
_r, a, rq = hoi(VIEWER, "Chậm", cham(dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), 50),
	cham(dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), 50),
	cham(dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), 50), tra("muộn"))
LECH["mono"], LECH["dung"] = 0.0, False
eq("mỗi lượt gọi 50 giây: gọi được 3 lượt, dừng trước lượt 4 (không còn đủ giờ), loi quá giờ", (a["status"],
	a.get("message"), len(rq)), ("loi", qa.M_GIO, 3))
eq("chờ đọc từng lượt: (chờ nối 10 + T) vừa phần còn lại trừ 5 s, tối đa 60", [q["timeout"] for q in rq], [60, 60, 35])
eq("hỏi đáp gọi mô hình KHÔNG thử lại (retries = 0) ở mọi lượt", sorted({q["retries"] for q in rq}), [0])
_t, _da = [], 0.0
for q, giay in zip(rq, (50, 50, 50)):
	_t.append(_da + qa.LAN_THU * (q["timeout"] + qa.CHO_NOI) + qa.CHO_THU_LAI)
	_da += giay
c("mọi lượt gọi, kể cả khi chạm hết thời gian chờ, xong trước 150 giây kể từ lúc hỏi", all(x <= qa.TOTAL_SECONDS - 5 for x in _t), _t)
from bc.ai.llm import anthropic as _anth  # noqa: E402
eq("hằng số lượt tệ nhất của qa khớp bc.ai.llm.anthropic (CONNECT_TIMEOUT; không thử lại: 1 lần thử, không chờ)",
	tuple(getattr(qa, x, None) for x in ('CHO_NOI', 'CHO_THU_LAI', 'LAN_THU', 'RETRIES')),
	(_anth.CONNECT_TIMEOUT, sum(_anth.RETRY_WAITS[:qa.RETRIES]), qa.RETRIES + 1, 0))
CL = "cho.lau@x.vn"
frappe.ROLES[CL] = ["BC Viewer"]
frappe.ENQUEUE_RUN = False
_r = as_user(CL, api.ask, "Chờ lâu trong hàng đợi")
frappe.ENQUEUE_RUN = True
LECH["time"] = 140                      # job bắt đầu 140 giây sau khi hỏi (hàng đợi đông)
kb(tra("muộn"))
n0 = len(REQ)
frappe.get_attr(frappe.ENQUEUED[-1][0])(**frappe.ENQUEUED[-1][2])
LECH["time"] = 0.0
eq("hạn 150 giây tính từ lúc HỎI: chờ hàng đợi 140 giây → quá giờ, không gọi mô hình", (as_user(CL, api.get_answer,
	_r["id"]).get("message"), len(REQ) - n0), (qa.M_GIO, 0))
frappe.ENQUEUE_RUN = False
_r = as_user(CL, api.ask, "Mất câu hỏi trong cache")
frappe.ENQUEUE_RUN = True
frappe.cache().delete_value(f"{IN_KEY}:{CL}:{_r['id']}")
n0 = len(REQ)
frappe.get_attr(frappe.ENQUEUED[-1][0])(**frappe.ENQUEUED[-1][2])
eq("câu hỏi mất khỏi cache (quá hạn) → loi 'không chạy xong', không gọi mô hình, Run loi", (as_user(CL, api.get_answer,
	_r["id"]).get("message"), len(REQ) - n0, run_row(_r["id"]).status), (qa.M_CHET, 0, "loi"))
LECH["mono"], LECH["dung"] = 0.0, True
GOI_API.clear()
_r, a, rq = hoi(CL, "Công cụ chậm", dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})),
	cham(dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), 147), tra("muộn"))
LECH["mono"], LECH["dung"] = 0.0, False
eq("hết giờ giữa chừng (lượt 2 trả về ở giây 147): công cụ xin sau hạn KHÔNG chạy, rồi dừng quá giờ",
	(a.get("message"), len(rq), [d for d, _u, _k in GOI_API]), (qa.M_GIO, 2, ["kd.get_monthly"]))
eq("Run loi, lời lỗi ngắn cố định", (run_row(_r["id"]).status, run_row(_r["id"]).error), ("loi", "quá giờ"))

print("C4. Lỗi của mô hình / công cụ → trạng thái có lời, job không bao giờ ném")


def nem(kind, ti=0):
	def f(req):
		e = llm.LLMError(kind, f"lỗi {kind}")
		e.tokens_in, e.tokens_out, e.cost_tokens_in, e.model = ti, 7 if ti else 0, float(ti), MODEL if ti else ""
		raise e
	return f


for kind, st, msg in (("credit", "het-credit", qa.M_CREDIT), ("refusal", "loi", qa.M_TU_CHOI),
		("rate", "loi", qa.M_MO_HINH), ("timeout", "loi", qa.M_GIO), ("no_key", "khong-khoa", qa.M_KHOA)):
	_r, a, rq = hoi(VIEWER, f"Hỏi {kind}", dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), nem(kind, 500))
	row = run_row(_r["id"])
	eq(f"LLMError {kind} → get_answer loi + lời, Run {st}, token đã tính tiền cộng vào", (a["status"], a["message"],
		row.status, row.tokens_in, json.loads(row.kpis), row.error), ("loi", msg, st, 1500, {"goi": 2}, f"lỗi gọi mô hình: {kind}"))
n_log = len(frappe.LOGGED)
_r, a, rq = hoi(VIEWER, f"Hỏi lỗi lạ {MARK_Q}", lambda req: (_ for _ in ()).throw(RuntimeError(f"lời có {MARK_Q}")))
eq("lỗi không lường trong job → loi, Run loi 'lỗi không lường: RuntimeError'", (a["status"], a["message"],
	run_row(_r["id"]).status, run_row(_r["id"]).error), ("loi", qa.M_LOI, "loi", "lỗi không lường: RuntimeError"))
moi = json.dumps(frappe.LOGGED[n_log:], ensure_ascii=False, default=str)
c("Error Log có tên loại lỗi, KHÔNG lời lỗi / câu hỏi", "RuntimeError" in moi and MARK_Q not in moi, moi[:300])
LOI_API["kd.get_monthly"] = ValueError(f"chứa số liệu {MARK_A}")
_r, a, rq = hoi(VIEWER, "Theo tháng?", dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), tra("Không có số liệu."))
LOI_API.clear()
c("method của màn ném lỗi → tool_result lỗi (không lời gốc), vòng lặp đi tiếp, xong", a["status"] == "xong"
	and kq(rq[1]).get("is_error") and MARK_A not in kq(rq[1])["content"], kq(rq[1]))
c("bước lỗi ghi ok False, không thành nguồn", a["steps"] == [{"tool": "xem_mang", "label": "Theo tháng", "ok": False}]
	and a["sources"] == [], a)

# ═══════════════════════════════════════════════════════════════════════════
print("C5. Người xem bị ẩn mảng: công cụ từ chối, không số nào của mảng đó rời máy chủ")
CN_ADMIN = as_user(ADMIN, lambda: __import__("bc.api.cn", fromlist=["x"]).get_receivables(refresh=1))
PT_ADMIN = as_user(ADMIN, lambda: __import__("bc.api.cn", fromlist=["x"]).get_payables(refresh=1))


def la_so(v, out):
	if isinstance(v, dict):
		for x in v.values():
			la_so(x, out)
	elif isinstance(v, (list, tuple)):
		for x in v:
			la_so(x, out)
	elif isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000:
		out.add(v)
	return out


SO_CN = la_so(CN_ADMIN, set()) - la_so(PT_ADMIN, set())
c("có số đặc trưng của mảng Phải thu để soát", len(SO_CN) >= 3, sorted(SO_CN)[:5])
X_CN = max(SO_CN)
single("BC Settings", hidden_sections="cong-no")
GOI_API.clear()
_r, a, rq = hoi(VIEWER, "Phải thu bao nhiêu?", dung(tu("xem_mang", {"mang": "cong-no", "ten": "receivables"})),
	dung(tu("xem_mang", {"mang": "phai-tra", "ten": "payables"})), tra(f"Phải thu {trieu(X_CN)}."))
eq("tool_result cho mảng ẩn: is_error, lời 'đang ẩn'", (kq(rq[1]).get("is_error"), "ẩn" in kq(rq[1])["content"]), (True, True))
eq("method của mảng ẩn KHÔNG được gọi (chặn trước); mảng khác vẫn gọi", [d for d, _u, _k in GOI_API], ["cn.get_payables"])
blob = json.dumps(rq, ensure_ascii=False)
eq("không request nào chứa số đặc trưng của Phải thu", sorted(x for x in SO_CN if re.search(r"(?<![\d.])" +
	re.escape(json.dumps(x)) + r"(?![\d])", blob)), [])
c("mô tả công cụ không nêu mảng ẩn", all("mang=cong-no" not in q["tools"][0]["description"] for q in rq))
eq("số của mảng ẩn trong câu trả lời → chưa kiểm", chua_kiem(a), [trieu(X_CN)])
eq("nguồn chỉ còn Phải trả", [s["section"] for s in a["sources"]], ["phai-tra"])
# lớp thứ hai: danh sách thấy được lỡ còn mảng ẩn → _guard của method vẫn chặn
cau = qa._Cau("x", VIEWER, False)
x = as_user(VIEWER, qa._xem_mang, cau, "t1", {"mang": "cong-no", "ten": "receivables"}, ["cong-no"], None)
c("lớp hai: _guard của method chặn người xem dù danh sách thấy được lỡ có mảng ẩn", x.get("is_error") is True
	and not cau.results, x)
GOI_API.clear()
_r, a, rq = hoi(ADMIN, "Phải thu?", dung(tu("xem_mang", {"mang": "cong-no", "ten": "receivables"})), tra("Có số."))
c("quản trị (mảng đang ẩn) vẫn tra được", not kq(rq[1]).get("is_error") and [d for d, _u, _k in GOI_API] ==
	["cn.get_receivables"])
single("BC Settings", hidden_sections="tro-ly")
try:
	as_user(VIEWER, api.ask, "Có gì mới?")
	c("ẩn mảng Trợ lý AI → người xem mất luôn hỏi đáp (PermissionError)", False)
except frappe.PermissionError:
	c("ẩn mảng Trợ lý AI → người xem mất luôn hỏi đáp (PermissionError)", True)
for fn, arg in ((api.get_qa, ()), (api.get_answer, ("x",))):
	try:
		as_user(VIEWER, fn, *arg)
		c(f"ẩn Trợ lý AI: {fn.__name__} chặn người xem", False)
	except frappe.PermissionError:
		c(f"ẩn Trợ lý AI: {fn.__name__} chặn người xem", True)
single("BC Settings", hidden_sections="")

# ═══════════════════════════════════════════════════════════════════════════
print("C6. Kết quả công cụ đã cắt (30 phần tử, _cat, ≤ 40.000 ký tự) và che tên")
cat_obj, cat_txt = qa.gon({"ds": [{"customer": KH_DAI, "v": i} for i in range(75)], "ghi": f"Giao cho {KH_DAI}"},
	__import__("bc.ai.redact", fromlist=["x"]).build(True))
eq("danh sách 75 → 30 phần tử + _cat 45", (len(cat_obj["ds"]), cat_obj.get("_cat")), (30, {"ds": 45}))
c("tên khách trong ô và giữa câu đã thành mã", KH_DAI not in cat_txt and "KH#" in cat_txt, cat_txt[:200])
to_obj, to_txt = qa.gon({"a": ["x" * 900] * 30, "b": ["y" * 900] * 30}, None)
c("JSON > 40.000 ký tự → cắt đôi tiếp danh sách dài nhất tới khi vừa", len(to_txt) <= 40_000 and to_obj["_cat"], len(to_txt))
c("không cắt được (chuỗi đơn quá dài) → lỗi, không gửi", qa.gon({"a": "z" * 50_000}, None)[0] is None)

# ═══════════════════════════════════════════════════════════════════════════
print("D. Đối chiếu số — bảng (lời còn mã giả, kết quả tra cứu của lượt này)")
KQ = [{"doanh_so": 1_612_345_678, "tien": 250_960_000, "ty_le": 35.21, "ty_le2": 0.0987, "so": 62, "dong": 1_250_000,
	"nho": 7, "le": 3.14159, "am": -12.34, "lon": 12_345_678_901, "ngan": 4_500, "nua": 0.5, "rows": [{"x": 99}],
	"chuoi": "123456", "co": True, "ngay": "2026-11-05"}]
BANG = [
	("Doanh số 1,6 tỷ.", []), ("Doanh số 1,61 tỷ", []), ("Doanh số 1,62 tỷ", ["1,62 tỷ"]), ("Doanh số 1,7 tỷ", ["1,7 tỷ"]),
	("Còn 251 triệu", []), ("Còn 250 triệu", ["250 triệu"]), ("Tỷ lệ 35,2%", []), ("Tỷ lệ 35,3%", ["35,3%"]),
	("Tỷ lệ 35,2 phần trăm", []), ("Tỷ trọng 9,9%", []), ("Tỷ trọng 9,8%", ["9,8%"]), ("Có 62 khách", []),
	("Có 63 khách", ["63"]), ("Giá 1.250.000 đ", []), ("Giá 1.250.001 đ", ["1.250.001 đ"]), ("Giá 1.250.000đ.", []),
	("Giá 1.300.000đ", ["1.300.000đ"]), ("Tồn 4.500 hộp", []), ("Tồn 4,5 nghìn hộp", []), ("Tổng 12,3 tỷ", []),
	("Giảm 12,3 điểm", []), ("Năm 2026 tốt", []), ("Lãi 2026 tỷ", ["2026 tỷ"]), ("Ngày 5/11/2026", []),
	("Ngày 2026-11-05", []), ("Tháng 10/2026", []), ("Ngày 05.11.2026", []), ("Ngày 5/11 giao", []),
	("Khách KH#0007 nợ", []), ("Chứng từ SINV-2026-00012", []), ("Phiếu KK-2026-002", []), ("Quý Q3/2026", []),
	("Do NV#01 lập", []), ("1. Doanh số ổn\n2. Phải thu ổn", []), ("Tổng 1.863 triệu (tự tính)", ["1.863 triệu"]),
	("Tỷ số 6,4", ["6,4"]), ("Doanh thu 1,250,000", []), ("Số pi 3,14", []), ("Số 3,15", ["3,15"]), ("Có 99 dòng", []),
	("Mã số 123456", []), ("Một nửa 0,5", []), ("Đạt 50%", []), ("Trong 7 ngày", []), ("Trong 8 ngày", ["8"]),
	("Khoảng 10-15%", ["10-15%"]), ("Niên vụ 2025/26", []), ("Lúc 8:30", []), ("Giảm -35,2%", []),
	("Tổng 12.345.678.901 đồng", []), ("Tổng 12 tỷ 345 triệu", ["345 triệu"]), ("Mã hàng T10 bán", []),
	("Tăng 1,6tỷ", []), ("Còn 5 khách", ["5"]), ("Còn 0 khách", []),
	("KH#0003 mua 1,6 tỷ, KH#0004 mua 251 triệu, bịa 999 triệu.", ["999 triệu"]),
	# soát chéo P3 — đơn vị viết tắt dính liền / cách: tr, k; "2tỷ5" = 2,5 tỷ; đuôi chữ khác kiểm như số trần
	("Còn 251tr", []), ("Còn 250tr", ["250tr"]), ("Còn 251 tr", []), ("Còn 250 tr.", ["250 tr"]), ("Tồn 4,5k hộp", []),
	("Quá hạn 999k", ["999k"]), ("Lãi 1tỷ6", []), ("Lãi 1tỷ7", ["1tỷ7"]), ("Tổng 12tỷ3", []), ("Tổng 12TR", ["12TR"]),
	("Nặng 62kg", []), ("Nặng 63kg", ["63kg"]), ("Lớp 10A1", ["10A1"]), ("Lúc 8h30", []),
	# khoảng: gạch ngang dài / "đến" / "tới" — đầu dưới dùng chung đơn vị với đầu trên
	("Mỗi khoản 7–251 triệu", ["7–251 triệu"]), ("Mỗi khoản từ 7 đến 251 triệu", ["7"]), ("Từ 7 tới 251tr", ["7"]),
	("Từ 1,6 tỷ đến 12,3 tỷ", []), ("Khoảng 1,6–12,3 tỷ", []), ("Từ 7 - 251 triệu", ["7"]), ("Năm 2025–2026 ổn", []),
	# ngày: d/m và ngày đủ năm so với ngày trong kết quả (ISO); tháng / năm và năm vẫn không tính
	("Hạn ngày 9/1", ["9/1"]), ("Hạn ngày 30/11/2026", ["30/11/2026"]), ("Hạn ngày 5/11/2025", ["5/11/2025"]),
	("Hạn ngày 5/11", []), ("Hạn 5-11-2026", []), ("Hạn ngày 45/13/2026", ["45/13/2026"]),
	# "%": chỉ so với lá tỷ lệ (khoá ty_le / pct / rate / growth…, don_vi "%") hoặc thang 0–1 — không với số đếm / ngày
	("Chiếm 62%", ["62%"]), ("Chiếm 7%", ["7%"]), ("Chiếm 99 phần trăm", ["99 phần trăm"]),
]
sai = []
for text, want in BANG:
	segs = qa.verify(text, KQ)
	if "".join(s["t"] for s in segs) != text or [s["t"] for s in segs if s["u"]] != want:
		sai.append((text, [s["t"] for s in segs if s["u"]], want))
eq(f"bảng đối chiếu {len(BANG)} dòng: số đã kiểm / chưa kiểm đúng, ghép lại đúng nguyên văn", sai, [])
c("bảng ≥ 40 dòng", len(BANG) >= 40, len(BANG))
eq("cùng lời, kết quả của câu hỏi KHÁC (không có số đó) → chưa kiểm", [s["t"] for s in qa.verify("Doanh số 1,6 tỷ.",
	[{"x": 250_960_000}]) if s["u"]], ["1,6 tỷ"])
eq("không kết quả tra cứu nào → mọi số / ngày chưa kiểm, năm / tháng / mã vẫn không tính", [s["t"] for s in qa.verify(
	"Năm 2026, tháng 10/2026, ngày 5/11/2026, KH#0001 mua 3 lần, 1,6 tỷ.", []) if s["u"]], ["5/11/2026", "3", "1,6 tỷ"])
KQ2 = [{"bang": [{"chi_tieu": "Đạt chuẩn", "gia_tri": 12.5, "don_vi": "%"}, {"chi_tieu": "Số mẫu", "gia_tri": 26,
	"don_vi": "mẫu"}], "growth": {"sales": 248.0}, "days_overdue": 26, "rows": [{"qty_no_rate": 30, "return_rate": 1.1}]}]
eq("%: lá có don_vi '%' / khoá growth, rate được nhận; số đếm (26 ngày, 26 mẫu, qty_no_rate 30) không xác nhận %",
	[s["t"] for s in qa.verify("Đạt 12,5%, tăng 248%, trả 1,1%, quá hạn 26%, chiếm 30%, có 26 mẫu.", KQ2) if s["u"]],
	["26%", "30%"])
eq("bool không phải số (True ≠ 1)", [s["t"] for s in qa.verify("Có 1 khách", [{"a": True}]) if s["u"]], ["1"])
eq("segments liền nhau u False được gộp, không đoạn rỗng", qa.verify("A 1,6 tỷ B 9 C", KQ),
	[{"t": "A 1,6 tỷ B ", "u": False}, {"t": "9", "u": True}, {"t": " C", "u": False}])

def la_max(obj):
	return max(la_so(obj, set()))


def qa_kh(req):
	return re.search(r"KH#\d+", req["messages"][-3]["content"]).group(0)


print("D2. Đối chiếu qua câu hỏi thật: số đúng, số bịa, số của câu trước, số tự tính; tên có chữ số không bị tính")
r1, a1, rq = hoi(VIEWER, "Phải trả?", dung(tu("xem_mang", {"mang": "phai-tra", "ten": "payables"})),
	lambda req: tra(f"Phải trả {trieu(la_max(kq_json(req)))}."))

PT = kq_json(rq[1])
eq("câu 1: số đúng → đã kiểm", (a1["status"], chua_kiem(a1)), ("xong", []))
v1, v2 = sorted(la_so(PT, set()))[-2:]
_r, a2, rq = hoi(VIEWER, f"Còn {KH_SO} thì sao?", dung(tu("xem_mang", {"mang": "tong-quan", "ten": "summary"})),
	lambda req: tra(f"Theo câu trước phải trả {trieu(la_max(PT))}; {qa_kh(req)} tự tính tổng {trieu(v1 + v2 + 7e6)}; "
		f"bịa 98.765.432 đ; năm 2026, hôm nay {qa._hom_nay().day}/{qa._hom_nay().month}/{qa._hom_nay().year}."),
	history=[{"q": "Phải trả?", "a": chu(a1)}])

eq("số của câu trước, số tự tính, số bịa → chưa kiểm; năm không tính; ngày hôm nay (đề bài hệ thống) đã kiểm", chua_kiem(a2),
	[trieu(la_max(PT)), trieu(v1 + v2 + 7e6), "98.765.432 đ"])
c("tên khách có chữ số đã đổi lại trong lời (sau khi chia đoạn) và chữ số của tên KHÔNG bị đánh dấu", KH_SO in chu(a2)
	and "365" not in "".join(chua_kiem(a2)), a2["segments"])
eq("Run: số đã kiểm (ngày hôm nay) / chưa kiểm", (run_row(_r["id"]).insights_ai, run_row(_r["id"]).rejected), (1, 3))
eq("get_answer.unverified = số đoạn chưa kiểm", a2["unverified"], 3)

# ═══════════════════════════════════════════════════════════════════════════
print("E. Che tên: câu hỏi (tên dài, tên một từ ngắn, NCC, người), lịch sử, bối cảnh, kết quả công cụ")
TEN_DOI_TAC = sorted({x for r in frappe.db.sql("SELECT name, customer_name FROM `tabCustomer`") for x in r if x}
	| {x for r in frappe.db.sql("SELECT name, supplier_name FROM `tabSupplier`") for x in r if x})
NGUOI_DS = sorted({x for r in frappe.db.sql("""SELECT name, full_name FROM `tabUser` WHERE name NOT IN
	('Administrator', 'Guest')""") for x in r if x and len(x) >= 5} | {x for (x,) in frappe.db.sql(
	"SELECT employee_name FROM `tabEmployee`") if x and len(x) >= 5})
c("có tên để soát (luật không rỗng nghĩa)", KH_DAI in TEN_DOI_TAC and KH_NGAN in TEN_DOI_TAC and NGUOI_TEN in NGUOI_DS
	and NV_TEN in NGUOI_DS, (len(TEN_DOI_TAC), NGUOI_DS[:5]))
CAU = f"{KH_DAI}, {KH_NGAN} và {NCC_TEN} ra sao? {NGUOI_TEN} và {NV_TEN} báo gì? Hỏi thêm {KH_NGAN}."
LS = [{"q": f"Còn {KH_NGAN}?", "a": f"{KH_DAI} nợ nhiều, {NGUOI_TEN} theo dõi."}]
_r, a, rq = hoi(VIEWER, CAU, dung(tu("xem_mang", {"mang": "tong-quan", "ten": "top_customers", "tham_so": {"limit": 20}}),
	tu("xem_mang", {"mang": "phai-tra", "ten": "payables"})),
	lambda req: tra("Trả lời: " + " ".join(re.findall(r"(?:KH|NCC|NV)#\d+", req["messages"][-3]["content"]))
		+ " — KH#9999 bịa."), history=LS)
gui = [q["system"] + json.dumps(q["messages"], ensure_ascii=False) + json.dumps(q["tools"], ensure_ascii=False) for q in rq]
eq("không tên khách / NCC (≥ 5 ký tự) nào trong mọi request", sorted({t for g in gui for t in TEN_DOI_TAC if len(t) >= 5
	and t in g}), [])
tu_nguoi = [q["system"] + "".join(m["content"] for m in q["messages"] if isinstance(m["content"], str)) for q in rq]
c("tên khách MỘT từ ngắn không còn (đứng riêng thành từ) trong đề bài / câu hỏi / lịch sử", not any(re.search(
	r"(?<!\w)" + KH_NGAN + r"(?!\w)", g) for g in tu_nguoi), [g[:200] for g in tu_nguoi])
eq("không tên người / email nào trong mọi request", sorted({t for g in gui for t in NGUOI_DS if t in g}), [])
m0 = rq[0]["messages"]
c("câu hỏi + lịch sử thành mã KH# / NCC# / NV#", "KH#" in m0[-1]["content"] and "NCC#" in m0[-1]["content"]
	and "NV#" in m0[-1]["content"] and "KH#" in m0[0]["content"] and "NV#" in m0[1]["content"], m0)
eq("lịch sử = các lượt user / assistant xen kẽ trước câu hỏi", [m["role"] for m in m0], ["user", "assistant", "user"])
c("bối cảnh công ty trong đề bài hệ thống đã che (cả tên ngắn)", "BỐI CẢNH CÔNG TY" in rq[0]["system"] and KH_DAI not in
	rq[0]["system"] and not re.search(r"(?<!\w)" + KH_NGAN + r"(?!\w)", rq[0]["system"]))
top = kq_json(rq[1], 0)
c("kết quả top_customers gửi đi: chỉ mã khách", "KH#" in json.dumps(top) and not any(t in json.dumps(top, ensure_ascii=False)
	for t in TEN_DOI_TAC if len(t) >= 5), json.dumps(top, ensure_ascii=False)[:300])
c("câu trả lời hiển thị: mã đã gửi đổi lại thành tên thật (khách, NCC, người), mã bịa giữ nguyên", all(t in chu(a) for t in
	(KH_DAI, KH_NGAN, NCC_TEN, NGUOI_TEN, NV_TEN)) and "KH#9999" in chu(a), chu(a))
import unicodedata  # noqa: E402


def bo_dau(x):
	return "".join(ch for ch in unicodedata.normalize("NFD", x) if not unicodedata.combining(ch)).replace("đ", "d").replace(
		"Đ", "D")


CAU2 = (f"{KH_DAI.lower()} và {KH_DAI.upper()}, {unicodedata.normalize('NFD', KH_DAI)}; {NCC_TEN.upper()}; "
	f"{bo_dau(KH_DAI).lower()}; {KH_NGAN.upper()} ở trung tâm; {NGUOI_TEN.lower()} báo")
LS2 = [{"q": f"còn {KH_DAI.lower()}?", "a": f"{NCC_TEN.lower()} nợ nhiều."}]
frappe.ROLES["che.ten@x.vn"] = ["BC Viewer"]
_r, a, rq = hoi("che.ten@x.vn", CAU2, tra("ok"), history=LS2)
g2 = unicodedata.normalize("NFC", json.dumps(rq[0]["messages"], ensure_ascii=False))
eq("tên gõ chữ thường / VIẾT HOA / NFD trong câu hỏi + lịch sử → không còn (so không phân biệt hoa thường)",
	sorted({t for t in TEN_DOI_TAC + NGUOI_DS if len(t) >= 5 and unicodedata.normalize("NFC", t).casefold() in g2.casefold()}),
	[])
c("tên khách ≥ 2 từ gõ không dấu → không còn", bo_dau(KH_DAI).lower() not in bo_dau(g2).lower(), g2[:300])
c("tên khách một từ ngắn VIẾT HOA → mã; chữ thường trùng tên ('trung tâm') giữ nguyên",
	KH_NGAN.upper() not in g2 and "trung tâm" in g2, g2[:400])
single("BC Settings", ai_mask_parties=0)
_r, a, rq = hoi(VIEWER, f"Còn {KH_DAI}?", tra("Không có số liệu."))
c("tắt che tên (ai_mask_parties 0) → không che khách (như lượt ngày)", KH_DAI in rq[0]["messages"][-1][
	"content"])
single("BC Settings", ai_mask_parties=1)

# ═══════════════════════════════════════════════════════════════════════════
print("F. Quản trị: get_schema / run_select trên tài khoản MariaDB chỉ đọc THẬT")


def root_sql(q):
	frappe.db.sql(q)


root_sql(f"DROP USER IF EXISTS '{RO_USER}'@'localhost'")
root_sql(f"DROP USER IF EXISTS '{RW_USER}'@'localhost'")
if True:   # tài khoản được xoá ở cuối bộ thử (và DROP IF EXISTS ở đầu phần này cho lần chạy hỏng trước)
	root_sql(f"CREATE USER '{RO_USER}'@'localhost' IDENTIFIED BY '{RO_PASS}'")
	root_sql(f"GRANT SELECT ON `{DB}`.* TO '{RO_USER}'@'localhost'")
	root_sql(f"CREATE USER '{RW_USER}'@'localhost' IDENTIFIED BY '{RW_PASS}'")
	root_sql(f"GRANT ALL PRIVILEGES ON `{DB}`.* TO '{RW_USER}'@'localhost'")
	from bc.ai import sqlro
	eq("get_qa.sql: chưa khai tài khoản → False (cả quản trị)", as_user(ADMIN, api.get_qa)["sql"], False)
	frappe.conf["bc_ai_ro_user"], frappe.conf["bc_ai_ro_password"] = RO_USER, RO_PASS
	eq("get_qa.sql: quản trị True, người xem False", (as_user(ADMIN, api.get_qa)["sql"], as_user(VIEWER, api.get_qa)["sql"]),
		(True, False))
	_r, a, rq = hoi(VIEWER, "Chạy SQL giúp", dung(tu("run_select", {"sql": "SELECT name FROM `tabCustomer`"}),
		tu("get_schema", {"doctype": "Customer"})), tra("Không được."))
	eq("người xem: chỉ xem_mang; gọi run_select / get_schema → 'công cụ không tồn tại'", ([t["name"] for t in rq[0]["tools"]],
		[x["content"] for x in rq[1]["messages"][-1]["content"]]), (["xem_mang"], ["Lỗi: công cụ không tồn tại"] * 2))
	SQL1 = "SELECT name, customer_name, owner FROM `tabCustomer` WHERE owner IS NOT NULL ORDER BY name"
	SQL2 = "SELECT owner AS nguoi_tao, modified_by FROM `tabCustomer` WHERE owner IS NOT NULL AND modified_by IS NOT NULL"
	SQL3 = "SELECT employee_name, department FROM `tabEmployee` WHERE department = 'Kho'"
	_r, a, rq = hoi(ADMIN, "Khách nào do ai tạo?",
		dung(tu("get_schema", {"doctype": "Customer"}), tu("get_schema", {"doctype": "Salary Slip"}),
			tu("get_schema", {"doctype": "Employee"})),
		dung(tu("run_select", {"sql": SQL1}), tu("run_select", {"sql": SQL2}), tu("run_select", {"sql": SQL3})),
		lambda req: tra("Kết quả: " + " ".join(sorted(set(re.findall(r"(?:KH|NCC|NV)#\d+", json.dumps(req["messages"],
			ensure_ascii=False)))))))
	eq("quản trị + tài khoản chỉ đọc: có get_schema, run_select", [t["name"] for t in rq[0]["tools"]],
		["xem_mang", "get_schema", "run_select"])
	sc = rq[1]["messages"][-1]["content"]
	S0 = json.loads(sc[0]["content"])
	c("get_schema(Customer): fieldname / fieldtype / label / options, bảng tabCustomer", S0["table"] == "tabCustomer" and any(
		f["fieldname"] == "customer_name" and set(f) == {"fieldname", "fieldtype", "label", "options"} for f in S0["fields"]))
	c("get_schema(Salary Slip) bị từ chối", sc[1].get("is_error") is True, sc[1])
	# luật 4b: DocType thuộc phân hệ hệ thống (không có trong danh sách tên cấm) cũng không xem được cấu trúc
	from bc.ai import sqlguard as _sg
	_meta_goc = frappe.get_meta
	frappe.get_meta = lambda dt, *a, **k: type("M", (), {"name": dt, "module": {"ToDo": "Desk", "File": "Core"}.get(dt, "Selling"),
		"fields": [{"fieldname": "x", "fieldtype": "Data", "label": "X", "options": None}]})()
	_cau_4b = type("C", (), {"buoc": []})()
	try:
		kq_4b = [qa._get_schema(_cau_4b, "t1", {"doctype": d}, None, None) for d in ("ToDo", "File", "Customer")]
	finally:
		frappe.get_meta = _meta_goc
	c("get_schema: DocType phân hệ Desk / Core bị từ chối theo phân hệ (luật 4b), DocType nghiệp vụ thì được",
		[bool(x.get("is_error")) for x in kq_4b] == [True, True, False] and _sg.doctype_allowed("ToDo"), kq_4b)
	S2 = json.loads(sc[2]["content"]) if not sc[2].get("is_error") else {"fields": []}
	from bc.ai import sqlguard
	c("get_schema(Employee): chỉ cột được phép", S2["fields"] and {f["fieldname"] for f in S2["fields"]}
		<= set(sqlguard.ALLOWED_COLUMNS["tabEmployee"]), [f["fieldname"] for f in S2["fields"]])
	sq = rq[2]["messages"][-1]["content"]
	c("ba câu SELECT chạy được", not any(x.get("is_error") for x in sq), sq)
	Q1, Q2, Q3 = (json.loads(x["content"]) if not x.get("is_error") else {"columns": [], "rows": [[""]]} for x in sq)
	eq("run_select: cột + 3 dòng; tên / mã khách → KH#, owner → NV#", (Q1["columns"], len(Q1["rows"]),
		all(re.fullmatch(r"KH#\d+", v) for r_ in Q1["rows"] for v in r_[:2]), {r_[2] for r_ in Q1["rows"]}),
		(["name", "customer_name", "owner"], 3, True, {"NV#01"}))
	eq("bí danh cột (owner AS nguoi_tao) vẫn che: email người đã biết → NV#", Q2["rows"], [["NV#01", "NV#01"]])
	c("employee_name → NV#", re.fullmatch(r"NV#\d+", Q3["rows"][0][0]) and Q3["rows"][0][1] == "Kho", Q3)
	blob = json.dumps(rq, ensure_ascii=False)
	eq("không tên khách / người nào trong request của quản trị", sorted({t for t in TEN_DOI_TAC + NGUOI_DS if len(t) >= 5
		and t in blob}), [])
	c("câu trả lời của quản trị: NV# đổi lại thành người thật, KH# thành tên", NGUOI in chu(a) and KH_DAI in chu(a)
		and KH_SO in chu(a) and NV_TEN in chu(a), chu(a))
	sqls = [s.get("sql") for s in a["steps"] if s["tool"] == "run_select"]
	eq("quản trị: bước run_select kèm câu SQL", (sqls, [s["ok"] for s in a["steps"] if s["tool"] == "run_select"]),
		([SQL1, SQL2, SQL3], [True, True, True]))
	c("bước get_schema bị từ chối không ghi thành bước", [s["label"] for s in a["steps"] if s["tool"] == "get_schema"] ==
		["Cấu trúc Customer", "Cấu trúc Employee"])
	_gm = frappe.get_meta
	frappe.get_meta = lambda dt, cached=True: _gm({"employee": "Employee", "EMPLOYEE": "Employee", "user": "User"}.get(dt, dt))
	_r, a, rq = hoi(ADMIN, "Cấu trúc?", dung(tu("get_schema", {"doctype": "employee"}), tu("get_schema", {"doctype": "EMPLOYEE"}),
		tu("get_schema", {"doctype": "user"})), tra("ok"))
	frappe.get_meta = _gm
	sc = [json.loads(x["content"]) if not x.get("is_error") else {"fields": [{"fieldname": "LỖI"}]} for x in
		rq[1]["messages"][-1]["content"]]
	c("get_schema('employee' / 'EMPLOYEE' / 'user' — meta nạp không phân biệt hoa thường như MariaDB) vẫn chỉ cột được phép",
		all(x["fields"] for x in sc) and all({f["fieldname"] for f in x["fields"]} <= set(sqlguard.ALLOWED_COLUMNS[T])
		for x, T in zip(sc, ("tabEmployee", "tabEmployee", "tabUser"))), [[f["fieldname"] for f in x["fields"]][:8] for x in sc])
	SQL4 = (f"SELECT CONCAT(REPEAT('x', 185), ', ', customer_name, ', abc') AS ghep, UPPER(customer_name) AS hoa, "
		f"LOWER(customer_name) AS thuong, CONCAT(REPEAT('y', 195), ' ', customer_name) AS sat FROM `tabCustomer` WHERE name = '{KH_DAI_ID}'")
	_r, a, rq = hoi(ADMIN, "Ghép chuỗi", dung(tu("run_select", {"sql": SQL4})), tra("ok"))
	o4 = rq[1]["messages"][-1]["content"][0]
	t4 = unicodedata.normalize("NFC", o4["content"]).casefold()
	c("ô SQL: che tên TRƯỚC rồi mới cắt 200 ký tự (tên nằm ở chỗ cắt không lọt nửa tên); UPPER / LOWER(tên) vẫn che",
		not o4.get("is_error") and not any(x in t4 for x in ("tân phát", "công ty tân", "phát lộc", "công ty")) and "kh#" in t4,
		o4["content"][:600])
	c("ô SQL sau khi che vẫn ≤ 200 ký tự", all(len(v) <= 200 for v in json.loads(o4["content"])["rows"][0]),
		[len(v) for v in json.loads(o4["content"])["rows"][0]])
	_r, a, rq = hoi(ADMIN, "Xoá giúp",
		dung(tu("run_select", {"sql": f"DELETE FROM `tabCustomer` WHERE name = '{KH_DAI_ID}'"}),
			tu("run_select", {"sql": "SELECT * FROM `tabEmployee`"}), tu("run_select", {"sql": "SELECT 1; SELECT 2"}),
			tu("run_select", {"sql": "SELECT modified_by FROM `tabCustomer` WHERE modified_by LIKE '%ngoai%'"})),
		tra("Không được."))
	bad = rq[1]["messages"][-1]["content"][:3]
	la = rq[1]["messages"][-1]["content"][3]
	eq("cột người có giá trị KHÔNG thuộc tài khoản / nhân viên nào → vẫn NV# (luật theo tên cột)",
		json.loads(la["content"])["rows"] if not la.get("is_error") else la, [["NV#01"]])
	c("người lạ không lọt vào request", NGUOI_LA not in json.dumps(rq, ensure_ascii=False))
	c("câu ghi / SELECT * tabEmployee / nhiều câu lệnh → tool_result lỗi có lý do", all(x.get("is_error")
		and len(x["content"]) > 5 for x in bad), bad)
	eq("bước bị từ chối vẫn hiện câu SQL cho quản trị, ok False", [(s.get("sql") is not None, s["ok"]) for s in a["steps"]],
		[(True, False)] * 3 + [(True, True)])
	c("bảng không bị đụng (lớp chặn chỉ đọc)", frappe.db.sql("SELECT COUNT(*) FROM `tabCustomer` WHERE name = %s",
		(KH_DAI_ID,))[0][0] == 1)
	c("mật khẩu chỉ đọc không nằm trong request / câu trả lời", RO_PASS not in blob and RO_PASS not in json.dumps(a))
	frappe.conf["bc_ai_ro_user"], frappe.conf["bc_ai_ro_password"] = RW_USER, RW_PASS
	eq("tài khoản có quyền ghi: get_qa.sql False", as_user(ADMIN, api.get_qa)["sql"], False)
	_r, a, rq = hoi(ADMIN, "SQL?", tra("Không có số liệu."))
	eq("tài khoản có quyền ghi: không công cụ SQL nào", [t["name"] for t in rq[0]["tools"]], ["xem_mang"])
	frappe.conf["bc_ai_ro_user"], frappe.conf["bc_ai_ro_password"] = RO_USER, RO_PASS

# ═══════════════════════════════════════════════════════════════════════════
print("G. Giới hạn và mọi lý do từ chối")
eq("get_qa người xem", as_user(VIEWER3, api.get_qa), {"enabled": True, "limit": 20, "used": 0, "remaining": 20,
	"sql": False, "max_question": 500})
eq("câu rỗng / chỉ dấu cách", (tu_choi(VIEWER3, ""), tu_choi(VIEWER3, "   ")), (qa.M_TRONG, qa.M_TRONG))
eq("câu 501 ký tự", tu_choi(VIEWER3, "a" * 501), qa.M_DAI)
_r, a, _rq = hoi(VIEWER3, "b" * 500, tra("ok"))
eq("câu đúng 500 ký tự được hỏi", a["status"], "xong")
for i in range(19):
	hoi(VIEWER3, f"Câu {i + 2}", tra("ok"))
g = as_user(VIEWER3, api.get_qa)
eq("sau 20 câu: used 20, remaining 0", (g["used"], g["remaining"]), (20, 0))
eq("câu thứ 21 trong ngày bị từ chối", tu_choi(VIEWER3, "Câu 21"), qa.M_HET_LUOT.format(n=20))
c("người khác vẫn hỏi được", hoi(VIEWER2, "Tôi hỏi", tra("ok"))[1]["status"] == "xong")
single("BC Settings", ai_qa_per_day=21)
c("tăng ai_qa_per_day → hỏi tiếp được", hoi(VIEWER3, "Câu 21", tra("ok"))[1]["status"] == "xong")
single("BC Settings", ai_qa_per_day=0)
eq("ai_qa_per_day 0 / trống → 20", as_user(VIEWER3, api.get_qa)["limit"], 20)
single("BC Settings", ai_qa_per_day=20)
eq("hôm qua không tính: dời các câu của VIEWER3 sang hôm qua → used 0", (frappe.db.sql(f"""UPDATE `tab{RUN}` SET started =
	DATE_SUB(started, INTERVAL 1 DAY) WHERE owner = %s AND run_type = 'hoi-dap'""", (VIEWER3,)),
	as_user(VIEWER3, api.get_qa)["used"])[1], 0)

frappe.ENQUEUE_RUN = False
i0 = len(frappe.ENQUEUED)
r_cho = as_user(VIEWER2, api.ask, "Câu đầu chưa xong")
eq("job chưa chạy → get_answer cho", as_user(VIEWER2, api.get_answer, r_cho["id"]), {"status": "cho"})
eq("câu thứ hai khi câu đầu chưa xong bị từ chối", tu_choi(VIEWER2, "Câu thứ hai"), qa.M_BAN)
c("người khác không bị khoá", tu_choi(VIEWER3, "Tôi khác") is None)
frappe.ENQUEUE_RUN = True


def chay_treo(i0):
	"""Chạy các job đã xếp mà chưa chạy (ENQUEUE_RUN = False) từ chỉ số i0."""
	treo = frappe.ENQUEUED[i0:]
	for m_, _c, kw_ in treo:
		kb(tra("Xong."))
		frappe.get_attr(m_)(**kw_)
	return len(treo)


eq("hai job treo", chay_treo(i0), 2)
eq("job chạy xong → get_answer xong", as_user(VIEWER2, api.get_answer, r_cho["id"])["status"], "xong")
kb(tra("ok"))
eq("hết khoá → hỏi tiếp được", tu_choi(VIEWER2, "Câu kế"), None)
frappe.ENQUEUE_RUN = False
i0 = len(frappe.ENQUEUED)
r_chet = as_user(VIEWER2, api.ask, "Job sẽ chết")
LECH["time"] = qa.LOCK_TTL + 5
eq("job chết: quá hạn khoá → get_answer loi + lời, hỏi lại được", (as_user(VIEWER2, api.get_answer, r_chet["id"])["status"],
	as_user(VIEWER2, api.get_answer, r_chet["id"]).get("message"), tu_choi(VIEWER2, "Hỏi lại")), ("loi", qa.M_CHET, None))
LECH["time"] = 0.0
frappe.ENQUEUE_RUN = True
eq("dọn hai job treo", chay_treo(i0), 2)

SS = "song.song@x.vn"
frappe.ROLES[SS] = ["BC Viewer"]
_goc_can = budget.can_call_qa
TRONG = []
CHEN = {}


def _chen(*a_, **k_):
	"""Yêu cầu song song của CÙNG người lọt vào đúng giữa lúc yêu cầu đầu đang đếm giới hạn (nhiều worker gunicorn)."""
	if not CHEN.get("da"):
		CHEN["da"] = True
		TRONG.extend(tu_choi(SS, f"Câu song song {i}") for i in range(4))
	return _goc_can(*a_, **k_)


budget.can_call_qa = _chen
frappe.ENQUEUE_RUN = False
i0 = len(frappe.ENQUEUED)
try:
	as_user(SS, api.ask, "Câu đầu song song")
finally:
	budget.can_call_qa = _goc_can
	frappe.ENQUEUE_RUN = True
eq("4 yêu cầu cùng người chen vào lúc yêu cầu đầu đang kiểm → đều 'đang có câu khác' (khoá giữ NGUYÊN TỬ trước khi đếm)",
	TRONG, [qa.M_BAN] * 4)
eq("… chỉ 1 dòng Run hoi-dap của người đó", frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}` WHERE owner = %s AND run_type = "
	"'hoi-dap'", (SS,))[0][0], 1)
eq("dọn job treo", chay_treo(i0), 1)
import pymysql  # noqa: E402  (phiên MariaDB thứ hai: giữ khoá đếm như một yêu cầu khác đang đếm)
_khac = pymysql.connect(user="root", unix_socket=SOCK, charset="utf8mb4", autocommit=True)
_kc = _khac.cursor()
_kc.execute("SELECT GET_LOCK(%s, 0)", (f"bcai_qa_{DB}"[:64],))
qa.START_LOCK_WAIT = 1
KD = "khoa.dem@x.vn"
frappe.ROLES[KD] = ["BC Viewer"]
n_run = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]
eq("khoá đếm toàn site đang bị phiên khác giữ → chờ rồi từ chối 'đang nhận nhiều câu', không ghi Run",
	(tu_choi(KD, "Khi khoá đếm bị giữ"), frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]), (getattr(qa, 'M_DONG', 'M_DONG'), n_run))
_kc.execute("SELECT RELEASE_LOCK(%s)", (f"bcai_qa_{DB}"[:64],))
_khac.close()
qa.START_LOCK_WAIT = 5
c("từ chối đó nhả khoá 'đang hỏi' của người hỏi → hỏi lại được", hoi(KD, "Hỏi lại sau khoá", tra("ok"))[1]["status"] == "xong")

single("BC Settings", ai_qa_enabled=0)
eq("AI hỏi đáp tắt → từ chối; get_qa.enabled False", (tu_choi(VIEWER2, "Có gì?"), as_user(VIEWER2, api.get_qa)["enabled"]),
	(qa.M_TAT, False))
single("BC Settings", ai_qa_enabled=1)
frappe.conf.pop("bc_ai_anthropic_key")
eq("thiếu khoá → từ chối; get_qa.enabled False", (tu_choi(VIEWER2, "Có gì?"), as_user(VIEWER2, api.get_qa)["enabled"]),
	(qa.M_KHOA, False))
frappe.conf["bc_ai_anthropic_key"] = "sk-ant lẫn dấu cách"
eq("khoá sai dạng → như thiếu khoá", tu_choi(VIEWER2, "Có gì?"), qa.M_KHOA)
frappe.conf["bc_ai_anthropic_key"] = KEY
single("BC Settings", ai_cap_claude_usd=0)
eq("trần chi 0 → vượt trần", tu_choi(VIEWER2, "Có gì?"), qa.M_TRAN)
S = budget.spent("claude")
single("BC Settings", ai_cap_claude_usd=S + 0.005)
_r, a, rq = hoi(VIEWER2, "Chạm trần giữa chừng", dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})),
	dung(tu("xem_mang", {"mang": "thang", "ten": "monthly"})), tra("muộn"))
eq("chạm trần giữa chừng (chi phí ghi sau MỖI lượt gọi) → dừng trước lượt 3, Run vuot-tran", (a["status"], a["message"],
	len(rq), run_row(_r["id"]).status), ("loi", qa.M_TRAN, 2, "vuot-tran"))
single("BC Settings", ai_cap_claude_usd=90)

now = frappe.utils.now_datetime()
SITE = [insert(RUN, run_type="hoi-dap", step="hoi-dap", provider="claude", status="ok", started=now, finished=now,
	owner=f"u{i}@x.vn", kpis=json.dumps({"goi": 1})) for i in range(200 - qa._dem())]
eq("200 câu / ngày toàn site → từ chối (người chưa hỏi câu nào cũng vậy)", (qa._dem(), tu_choi("nguoi.moi@x.vn", "Có gì?")
	if frappe.ROLES.setdefault("nguoi.moi@x.vn", ["BC Viewer"]) else None), (200, qa.M_HET_SITE))
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE name IN %s", (tuple(SITE),))
QA_NOW = budget.qa_calls_today()
GIU = [insert(RUN, run_type="hoi-dap", step="hoi-dap", provider="claude", status="ok", started=now, finished=now,
	owner="khac@x.vn", kpis=json.dumps({"goi": 300 - 6 - QA_NOW}))]
eq("lượt gọi hỏi đáp hôm nay 294 → câu mới (giữ chỗ 7) bị từ chối", (budget.qa_calls_today(), tu_choi(VIEWER2, "Có gì?")),
	(294, qa.M_QUA_GOI))
frappe.db.sql(f"UPDATE `tab{RUN}` SET kpis = %s WHERE name = %s", (json.dumps({"goi": 300 - 7 - QA_NOW}), GIU[0]))
eq("293 → vừa đủ 7 lượt, hỏi được", hoi(VIEWER2, "Vừa đủ", tra("ok"))[1]["status"], "xong")
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE name IN %s", (tuple(GIU),))
frappe.ENQUEUE_RUN = False
r_g = as_user(VIEWER2, api.ask, "Giữ chỗ")
eq("câu chưa xong giữ chỗ 7 lượt gọi (kpis.goi chưa có)", budget.qa_calls_today() - QA_NOW, 1 + 7)
frappe.ENQUEUE_RUN = True
kb(tra("ok"))
frappe.get_attr(frappe.ENQUEUED[-1][0])(**frappe.ENQUEUED[-1][2])

print("G2. Câu trả lời chỉ người hỏi lấy được, 30 phút")
single("BC Settings", ai_qa_per_day=200)   # người xem chính đã hỏi nhiều câu ở các phần trên
r_x, a_x, _rq = hoi(VIEWER, f"Câu riêng {MARK_Q}", tra(f"Trả lời riêng {MARK_A}"))
eq("người hỏi lấy được", a_x["status"], "xong")
khac = as_user(VIEWER2, api.get_answer, r_x["id"])
eq("người khác (cùng mã câu hỏi) → không tìm thấy", (khac["status"], khac["message"]), ("loi", qa.M_KHONG_THAY))
eq("quản trị cũng không đọc được câu của người khác", as_user(ADMIN, api.get_answer, r_x["id"])["status"], "loi")
c("không lọt chữ của câu trả lời ra người khác", MARK_A not in json.dumps(khac, ensure_ascii=False))
eq("mã câu hỏi rác / quá dài → không tìm thấy", [as_user(VIEWER, api.get_answer, x)["status"] for x in
	("", "../x", "a" * 65, None, r_x["id"] + "x")], ["loi"] * 5)
LECH["time"] = 1799
eq("29 phút 59 giây: còn", as_user(VIEWER, api.get_answer, r_x["id"])["status"], "xong")
LECH["time"] = 1801
eq("quá 30 phút: không tìm thấy", as_user(VIEWER, api.get_answer, r_x["id"])["status"], "loi")
LECH["time"] = 0.0
k_ = next(k for k in frappe.cache().store if k.startswith(qa.ANS_KEY) and k.endswith(r_x["id"]))
eq("khoá cache gắn với người hỏi, không tiền tố bc:", k_, f"{qa.ANS_KEY}:{VIEWER}:{r_x['id']}")

# ═══════════════════════════════════════════════════════════════════════════
print("H. Riêng tư: không gì của câu hỏi / câu trả lời / kết quả tra cứu trong bảng, log; khoá + mật khẩu không lọt")
BANG_DB = {}
for (t,) in frappe.db.sql("SHOW TABLES"):
	rows = frappe.db.sql(f"SELECT * FROM `{t}` LIMIT 20000", as_dict=True)
	if rows:
		BANG_DB[t] = rows
TXT = json.dumps(BANG_DB, ensure_ascii=False, default=str)
TXT_LOG = json.dumps(frappe.LOGGED, ensure_ascii=False, default=str)
MAU = [MARK_Q, MARK_A, "Phải thu hiện bao nhiêu", "LUẬT TRẢ LỜI", "tool_result", '"buckets"', "Không có số liệu.",
	"Trả lời riêng", "Câu riêng"]
eq(f"không mẩu câu hỏi / câu trả lời / đề bài / kết quả trong {len(BANG_DB)} bảng có dữ liệu", [m for m in MAU if m in TXT],
	[])
eq("… và trong Error Log (frappe.log_error)", [m for m in MAU if m in TXT_LOG], [])
c("bộ dò bảng có hiệu lực (dòng Run hỏi đáp có trong ảnh chụp)", '"hoi-dap"' in TXT)
SECRET = [KEY, "sk-ant", RO_PASS, RW_PASS]
OUT = json.dumps([as_user(u, api.get_qa) for u in (VIEWER, ADMIN)] + [as_user(VIEWER, api.get_answer, r_x["id"])],
	ensure_ascii=False)
eq("khoá / mật khẩu không trong bảng, log, kết quả API, request, cache", [s for s in SECRET if s in TXT or s in TXT_LOG
	or s in OUT or s in json.dumps(REQ, ensure_ascii=False) or s in json.dumps(frappe.cache().store, ensure_ascii=False)], [])
eq("lỗi trong dòng Run hỏi đáp chỉ là lời cố định", sorted({r[0] for r in frappe.db.sql(f"""SELECT DISTINCT error FROM
	`tab{RUN}` WHERE run_type = 'hoi-dap' AND error IS NOT NULL""")}), sorted({"quá giờ", "lỗi gọi mô hình: credit",
	"lỗi gọi mô hình: refusal", "lỗi gọi mô hình: rate", "lỗi gọi mô hình: timeout", "lỗi gọi mô hình: no_key",
	"lỗi không lường: RuntimeError", "mô hình không trả lời", "đã chi tới trần kỳ này", "mất câu hỏi trong hàng đợi"}))
c("cache 'cho' / khoá đang hỏi không chứa câu hỏi", not any(MARK_Q in v for k, v in frappe.cache().store.items()
	if k.startswith(qa.LOCK_KEY)))

# ═══════════════════════════════════════════════════════════════════════════
print("I. Lượt gọi hỏi đáp KHÔNG ăn 30 lượt / ngày của lượt chạy sáng")
THEM = [insert(RUN, run_type="hoi-dap", step="hoi-dap", provider="claude", status="ok", started=now, finished=now,
	owner="khac@x.vn", kpis=json.dumps({"goi": 2})) for _ in range(30)]
n_qa = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}` WHERE run_type = 'hoi-dap' AND started >= %s", (str(now.date()),))[0][0]
c("hôm nay đã có ≥ 30 câu hỏi đáp (đủ để làm tràn 30 nếu bị tính)", n_qa >= 30, n_qa)
eq("budget.calls_today(claude) = 0 (chỉ lượt sáng / bản tin / thử kết nối)", budget.calls_today("claude"), 0)
eq("budget.can_call(claude) vẫn được", budget.can_call("claude"), (True, ""))
NGAY = [insert(RUN, run_type="ngay", step="kd", provider="claude", status="ok", started=now, finished=now)
	for _ in range(30)]
eq("đối chứng: 30 lượt của lượt sáng → can_call chặn (qua-so-luot)", budget.can_call("claude"), (False, "qua-so-luot"))
c("… nhưng hỏi đáp vẫn hỏi được (giới hạn riêng)", hoi(VIEWER2, "Sau 30 lượt sáng", tra("ok"))[1]["status"] == "xong")
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE name IN %s", (tuple(NGAY + THEM),))
eq("budget.MAX_QA_CALLS_PER_DAY = 300, MAX_CALLS_PER_DAY vẫn 30", (budget.MAX_QA_CALLS_PER_DAY, budget.MAX_CALLS_PER_DAY),
	(300, 30))
c("không mạng suốt bộ thử", not MANG, MANG)

# ─── Dọn: tài khoản MariaDB + CSDL ───────────────────────────────────────────
for u in (RO_USER, RW_USER):
	frappe.db.sql(f"DROP USER IF EXISTS '{u}'@'localhost'")
frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
