"""Trợ lý AI — bc.ai.pipeline.run_daily ĐẦU-CUỐI trên bảng thật (đặc tả §2, §5, §9; hợp đồng §1 mục 9–12).

Mọi module THẬT: collect (bc.api.* thật trên seed gộp seed_ui2: SX + công nợ + ATTP + vận chuyển + nhân sự + bán
hàng), registry + mọi quy tắc + detector hệ thống, store, render, redact, budget, prompt, jobs. Chỉ thay CỬA MẠNG:
bc.ai.llm.call (has_key, LLMError, clean, run_status vẫn thật; khoá giả đặc biệt trong frappe.conf). Socket ra
ngoài (AF_INET / AF_INET6, DNS) bị chặn cả bộ thử: lỡ ra mạng là nổ.

Giả lập sát Frappe v16 thật hơn bộ giả chung (chỉ trong file này):
- GIAO DỊCH THẬT: kết nối MariaDB tắt autocommit; frappe.db.commit / rollback = COMMIT / ROLLBACK thật (bộ giả chung
  autocommit nên rollback không làm gì — lỗi "dòng tổng mất theo rollback" không bao giờ lộ).
- frappe.get_traceback như v16 (traceback.format_exception; with_context kèm biến cục bộ như developer_mode) và
  frappe.log_error như v16 (message rỗng → tự lấy get_traceback(with_context=True)) — để soát lộ khoá / đề bài.

Số kỳ vọng TÍNH TAY từ seed (test_cn: phải thu 220 tr, quá hạn 120 tr, ứng trước 10 tr; test_vc: 28 đơn chờ quá 3
ngày; …) — phép tính ghi trong comment. Hôm nay giả 27/10/2026 10:30 (đổi ở phần vòng đời).

Chạy: BC_TEST_DB=bc_test_ai_pipeline python3 -B test_ai_pipeline.py
"""
import ast
import datetime
import json
import os
import re
import socket
import sys
import tempfile
import traceback as _tb

from seed import Check, child, insert, single
from paths import BC_ROOT

import frappe  # noqa: E402  (giả)

c = Check()
D = datetime.datetime
INSIGHT, RUN = "BC AI Insight", "BC AI Run"
KEY = "sk-ant-api03-KHOAGIA-pipeline-7Qz9XwV2mN"      # khoá giả đặc biệt
GIA = {"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15}   # USD / 1 triệu token


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


# ═══════════════════════════════════════════════════════════════════════════
print("A. AST — luật §9 trên toàn cây bc/ai")
AI_DIR = os.path.join(BC_ROOT, "bc", "ai")
FILES = sorted(os.path.join(d, f) for d, _s, fs in os.walk(AI_DIR) if "__pycache__" not in d for f in fs
	if f.endswith(".py"))


def rel(p):
	return os.path.relpath(p, os.path.join(BC_ROOT, "bc", "ai")).replace(os.sep, "/")


def imports_of(tree):
	out = []
	for n in ast.walk(tree):
		if isinstance(n, ast.Import):
			out += [a.name for a in n.names]
		elif isinstance(n, ast.ImportFrom):
			out.append("." * n.level + (n.module or ""))
	return out


def strings_of(node):
	"""Mọi hằng chuỗi (kể cả phần tĩnh của f-string) trong node."""
	return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


TREES = {rel(p): ast.parse(open(p, encoding="utf-8").read()) for p in FILES}
c("thấy đủ các module chính của bc/ai", {"collect.py", "pipeline.py", "llm/__init__.py", "llm/anthropic.py",
	"rules/cn.py", "detectors/he_thong.py"} <= set(TREES), sorted(TREES))

# 1. collect.py chỉ import frappe, bc.api.*, thư viện chuẩn (đặc tả §3 — KHÔNG bc.ai.*; soát rộng ở test_ai_tinh.py).
bad = [m for m in imports_of(TREES["collect.py"]) if m.startswith(".") or not (m.split(".")[0] == "frappe"
	or m == "bc.api" or m.startswith("bc.api.") or m.split(".")[0] in sys.stdlib_module_names)]
c("collect.py: import chỉ frappe / bc.api.* / thư viện chuẩn", not bad, bad)

# 2. Chỉ bc/ai/llm/* import requests, đọc bc_ai_*_key, đọc frappe.conf.
NGOAI_LLM = {k: t for k, t in TREES.items() if not k.startswith("llm/")}
lo_req = [k for k, t in NGOAI_LLM.items() if any(m.split(".")[0] == "requests" for m in imports_of(t))]
c("ngoài llm/: không import requests", not lo_req, lo_req)
lo_khoa = [k for k, t in NGOAI_LLM.items() if any(re.search(r"bc_ai_\w*key", s) for s in strings_of(t))]
c("ngoài llm/: không chuỗi bc_ai_anthropic_key / bc_ai_openai_key", not lo_khoa, lo_khoa)
lo_conf = [k for k, t in NGOAI_LLM.items() for n in ast.walk(t) if isinstance(n, ast.Attribute) and n.attr == "conf"
	and isinstance(n.value, ast.Name) and n.value.id == "frappe" and k != "sqlro.py"]   # P3: sqlro — khoá đọc soát ở test_ai_tinh
c("ngoài llm/ (trừ sqlro.py — tài khoản chỉ đọc): không đọc frappe.conf", not lo_conf, lo_conf)
c("llm/ có đọc khoá (bc_ai_anthropic_key) — luật trên không rỗng nghĩa", any("bc_ai_anthropic_key" in strings_of(t)
	for k, t in TREES.items() if k.startswith("llm/")))

# 3. rules/*: không frappe.db / get_all / get_list / SQL.
SQL_RX = re.compile(r"\b(select|insert|update|delete)\b.*\b(from|into|set)\b|`tab", re.I | re.S)
lo_rule = []
for k, t in TREES.items():
	if not k.startswith("rules/"):
		continue
	for n in ast.walk(t):
		if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "frappe" \
				and n.attr in ("db", "get_all", "get_list", "get_doc", "get_value", "qb"):
			lo_rule.append((k, n.attr))
		if isinstance(n, ast.Attribute) and n.attr in ("sql", "sql_list"):
			lo_rule.append((k, n.attr))
	lo_rule += [(k, s[:40]) for s in strings_of(t) if SQL_RX.search(s)]
c("rules/*: không frappe.db / get_all / SQL", not lo_rule, lo_rule)
c("rules/* có đủ 6 module", {f"rules/{m}.py" for m in ("kd", "kho", "cn", "vc", "ns", "attp")} <= set(TREES))

# 4. detectors/*: chuỗi SQL chỉ SELECT.
GHI = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|REPLACE|CREATE|GRANT)\b", re.I)
sql_det, lo_det = [], []
for k, t in TREES.items():
	if not k.startswith("detectors/"):
		continue
	for n in ast.walk(t):
		if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("sql", "sql_list") and n.args:
			s = " ".join(strings_of(n.args[0]))
			sql_det.append(s)
			if GHI.search(s):
				lo_det.append((k, s[:60]))
c("detectors/*: có câu SQL để soát (luật không rỗng nghĩa)", len(sql_det) >= 5, len(sql_det))
c("detectors/*: SQL không INSERT / UPDATE / DELETE / ALTER / DROP / TRUNCATE", not lo_det, lo_det)
c("detectors/*: mọi câu SQL bắt đầu bằng SELECT", all(s.strip().upper().startswith("SELECT") for s in sql_det),
	[s[:40] for s in sql_det if not s.strip().upper().startswith("SELECT")])

# 5. Ngoài llm/: không socket / urllib / http / subprocess / requests.
CAM = ("socket", "urllib", "http", "subprocess", "requests", "httpx", "aiohttp", "ssl", "ftplib", "smtplib")
lo_net = [(k, m) for k, t in NGOAI_LLM.items() for m in imports_of(t) if m.split(".")[0] in CAM]
lo_net += [(k, ast.unparse(n)[:50]) for k, t in NGOAI_LLM.items() for n in ast.walk(t) if isinstance(n, ast.Call)
	and (getattr(n.func, "attr", "") or getattr(n.func, "id", "")) in ("__import__", "import_module")
	and n.args and isinstance(n.args[0], ast.Constant) and str(n.args[0].value).split(".")[0] in CAM]
c("ngoài llm/: không mở socket / urllib / http / subprocess", not lo_net, lo_net)

# 6. pyproject.toml: dependencies vẫn rỗng; mọi package có __init__.py.
pp = open(os.path.join(BC_ROOT, "pyproject.toml"), encoding="utf-8").read()
m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", pp, re.M | re.S)
c("pyproject.toml: dependencies = []", bool(m) and m.group(1).strip() == "", m and m.group(0))
pkg = [d for d, _s, fs in os.walk(AI_DIR) if "__pycache__" not in d and any(f.endswith(".py") for f in fs)]
thieu = [rel(d) for d in pkg if not os.path.isfile(os.path.join(d, "__init__.py"))]
c("mọi thư mục package dưới bc/ai có __init__.py", len(pkg) >= 4 and not thieu, (pkg, thieu))


# ═══════════════════════════════════════════════════════════════════════════
print("B. Dựng: seed gộp, giao dịch thật, chặn mạng, khoá giả, mô hình giả")
import seed_ui2  # noqa: E402,F401  (reset + seed SX, công nợ, ATTP, vận chuyển, nhân sự, bán hàng)

frappe.session.user = "viewer@example.com"
SITE = tempfile.mkdtemp(prefix="bc_ai_pl_site_")
os.makedirs(os.path.join(SITE, "private", "backups"))      # thư mục backup RỖNG → ht.backup_cu đỏ (chưa có bản)
frappe.FAKE_SITE_PATH = SITE
# Tên hiển thị khác mã: NPP-A = "Đại lý Minh Phát" (cong-no.receivables.top_overdue[0].customer hiện tên này).
frappe.db.sql("UPDATE `tabCustomer` SET customer_name = 'Đại lý Minh Phát' WHERE name = 'NPP-A'")
# Khách / NCC thêm: KHÔNG có trong số liệu — vẫn phải không lọt (soát mọi Customer / Supplier của DB).
insert("Customer", name="KH-XUAN-HOA", customer_name="Siêu thị Xuân Hoa")
insert("Supplier", name="NCC-HUONG-QUE", supplier_name="Công ty Hương Quê")
single("BC Settings", ai_enabled=0, ai_mask_parties=1, ai_cap_claude_usd=90)
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [GIA])
# ht.dia_day đọc dung lượng ổ THẬT của máy chạy thử → tắt (đường ghi đè thật của BC Settings) cho kết quả ổn định.
child("BC Settings", "BC Settings", "BC AI Rule", "ai_rules", [{"rule_key": "ht.dia_day", "disabled": 1}])

# Giao dịch thật.
frappe.db._cur()
frappe.db.conn.autocommit(False)
GD = {"commit": 0, "rollback": 0}


def _commit(*a, **k):
	GD["commit"] += 1
	frappe.db.conn.commit()


def _rollback(*a, **k):
	GD["rollback"] += 1
	frappe.db.conn.rollback()


frappe.db.commit, frappe.db.rollback = _commit, _rollback
_commit()


def luu():
	frappe.db.conn.commit()


# get_traceback / log_error như v16.
def _get_tb(with_context=False, *a, **k):
	et, ev, tb = sys.exc_info()
	if et is None:
		return ""
	s = "".join(_tb.format_exception(et, ev, tb))
	if with_context:          # developer_mode: kèm biến cục bộ từng khung
		t = tb
		while t is not None:
			try:
				s += "\n" + repr(dict(t.tb_frame.f_locals))
			except Exception:  # noqa: BLE001
				pass
			t = t.tb_next
	return s


LOG = []


def _log_error(title=None, message=None, *a, **k):
	rec = [title, message, *a, *k.values()]
	if not message:              # v16 utils/error.py: message rỗng → traceback = get_traceback(with_context=True)
		rec.append(_get_tb(with_context=True))
	LOG.append(rec)


frappe.get_traceback, frappe.log_error = _get_tb, _log_error

# Chặn mạng: mọi kết nối AF_INET / AF_INET6 và phân giải DNS (MariaDB qua unix socket vẫn chạy).
MANG = []


class MangBiChan(RuntimeError):
	pass


_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			MANG.append(addr)
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


def _dns(*a, **k):
	MANG.append(a[:2])
	raise MangBiChan(f"bộ thử chặn DNS: {a[:2]}")


socket.socket.connect, socket.socket.connect_ex = _chan(_connect), _chan(_connect_ex)
socket.getaddrinfo = socket.create_connection = _dns


def nem(fn, loi=Exception):
	try:
		fn()
	except loi:
		return True
	except BaseException:  # noqa: BLE001
		return False
	return False


import urllib.request  # noqa: E402

c("chặn mạng: urlopen tới api.anthropic.com nổ", nem(lambda: urllib.request.urlopen(
	"https://api.anthropic.com/v1/messages", timeout=2), MangBiChan))
_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
c("chặn mạng: socket AF_INET connect nổ", nem(lambda: _s.connect(("127.0.0.1", 9)), MangBiChan))
_s.close()
c("chặn mạng: MariaDB (unix socket) vẫn chạy", frappe.db.sql("SELECT 1")[0][0] == 1)
MANG.clear()

frappe.conf["bc_ai_anthropic_key"] = KEY

from bc.ai import llm, pipeline, registry, store  # noqa: E402
from bc.ai.jobs import LOCK_KEY  # noqa: E402

CALL_THAT = llm.call
GOI = []          # mọi lời gọi mô hình giả: {nhom, system, user, obj, model, timeout}
KICH_BAN = {}     # nhóm → hàm(obj) → kết quả | ném
KQ = []           # mọi giá trị run_daily trả


def fake_call(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	GOI.append({"nhom": obj["nhom"], "system": system, "user": user, "obj": obj, "model": model,
		"timeout": timeout, "provider": provider, "schema_name": schema_name})
	f = KICH_BAN.get(obj["nhom"])
	if f is None:
		return {"data": {"insights": []}, "tokens_in": 1000, "tokens_out": 100, "model": model}
	return f(obj)


llm.call = fake_call
c("chỉ thay llm.call: has_key / LLMError / clean / run_status vẫn là bản thật",
	llm.has_key("claude") and llm.run_status("credit") == "het-credit" and llm.LLMError.__module__ == "bc.ai.llm"
	and KEY not in llm.clean("x" + KEY) and CALL_THAT is not fake_call)


def tl(insights, tin=1000, tout=100, model=None):
	"""Một câu trả lời của mô hình giả (1000 token vào, 100 ra mặc định)."""
	return lambda obj: {"data": {"insights": insights(obj) if callable(insights) else insights}, "tokens_in": tin,
		"tokens_out": tout, "model": model or "claude-sonnet-5-5"}


def S(obj, rule, co=None):
	"""id S… của tín hiệu có rule (và loi_quy_tac chứa `co`) trong đề bài."""
	for t in obj["tin_hieu"]:
		if t["rule"] == rule and (co is None or co in t["loi_quy_tac"]):
			return t["id"]
	raise KeyError((rule, co))


def ins(signal, title, body, advice=(), severity="vang", priority=3):
	return {"signal": signal, "severity": severity, "priority": priority, "title": title, "body": body,
		"advice": list(advice)}


def chay(run_type=None, **kich_ban):
	GOI.clear()
	KICH_BAN.clear()
	KICH_BAN.update(kich_ban)
	out = pipeline.run_daily(run_type) if run_type else pipeline.run_daily()
	KQ.append(out)
	return out


def cai(**kw):
	single("BC Settings", **kw)
	luu()


def bo_cai(*fields):
	for f in fields:
		frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = %s", (f,))
	luu()


def R(key):
	r = frappe.db.sql(f"SELECT * FROM `tab{INSIGHT}` WHERE BINARY signal_key = %s", (key,), as_dict=True)
	return r[0] if r else None


def rows_of(run):
	return frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE run_id = %s ORDER BY name", (run,), as_dict=True)


def tong(run):
	return frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE name = %s", (run,), as_dict=True)[0]


def con(run):
	return [r for r in rows_of(run) if r.step != "tong"]


def xoa_run():
	frappe.db.sql(f"DELETE FROM `tab{RUN}`")
	luu()


def free_rows(status=None):
	q = f"SELECT * FROM `tab{INSIGHT}` WHERE rule = 'ai'" + (" AND status = %s" if status else "")
	return frappe.db.sql(q, (status,) if status else None, as_dict=True)


def tao_free(sections, key, path, now=D(2026, 10, 26, 5, 30)):
	"""Nhận định tự do của một lượt TRƯỚC (như lượt gọi hôm qua đã nêu)."""
	sec = registry.section_of(path)
	store.sync_ai_free(sections, [{"key": key, "section": sec, "route": f"#/{sec}", "severity": "vang", "priority": 2,
		"title": "Lời tự do cũ", "body": "Số cũ của hôm qua", "advice": [], "paths": [path], "sections_used": [sec]}],
		now)
	luu()


# Tín hiệu tính tay trên seed (test_cn / test_vc / test_ns / test_attp + thư mục backup rỗng).
KEYS = {"cn.qua_han_ty_le", "cn.vuot_han_muc", "cn.dso_cao", "cn.phai_tra_qua_han", "vc.cho_qua_han",
	"vc.chua_xep_chuyen", "vc.su_co_mo", "vc.cuoc_canh_bao:tra_bat_thuong", "vc.cuoc_canh_bao:tra_chuyen_huy",
	"vc.cuoc_canh_bao:sua_tay", "vc.xe_qua_han", "ns.bhxh_rui_ro", "ns.giay_to:hd", "ns.giay_to:ksk",
	"ns.giay_to:attp", "ns.viec_ton:luong_trung", "attp.den_do:vong_kiem", "attp.den_do:su_co",
	"attp.den_do:khac_phuc", "attp.den_do:khieu_nai", "attp.den_do:xuat_xuong", "attp.den_do:truy_xuat",
	"ht.backup_cu"}
NHOM = [g for g in registry.GROUPS if g != registry.KIEM_SOAT]   # thứ tự gọi (kiểm soát: chưa có detector → không gọi)
CO_TIN = {"van-chuyen", "tai-chinh", "nhan-su", "attp", "he-thong"}


# ═══════════════════════════════════════════════════════════════════════════
print("C. AI tắt (ai_enabled = 0): không gọi mô hình, bước 1–4 + 8 vẫn chạy, lời quy tắc")
tao_free(("cong-no", "phai-tra"), "ai:cong-no.receivables.kpis.net", "cong-no.receivables.kpis.net")
out = chay()
run1 = out["run"]
eq("không một lời gọi mô hình", len(GOI), 0)
eq("trả: status ok, ai tat", (out["status"], out["ai"]), ("ok", "tat"))
t = tong(run1)
eq("dòng tổng: step tong, status ok, run_type ngay, run_id = chính nó", (t.step, t.status, t.run_type, t.run_id),
	("tong", "ok", "ngay", run1))
eq("dòng tổng: signals = 23 tín hiệu tính tay", t.signals, len(KEYS))
cc = con(run1)
eq("đúng MỘT dòng con: step ai, status tat, provider claude, không token / chi phí",
	[(r.step, r.status, r.provider, r.tokens_in, r.tokens_out, r.cost_usd) for r in cc], [("ai", "tat", "claude", 0, 0, 0)])
mo = {r.signal_key for r in frappe.db.sql(f"SELECT signal_key FROM `tab{INSIGHT}` WHERE status = 'mo' AND rule != 'ai'",
	as_dict=True)}
eq("tín hiệu mở = đúng 23 khoá tính tay", mo, KEYS)
a = R("cn.qua_han_ty_le")
# 120 tr / 220 tr = 54,545…% → "54,5%"; 120.000.000 ≥ 1e8 → "120 triệu"; 220.000.000 → "220 triệu"
eq("lời quy tắc thay số kiểu VN (54,5% · 120 triệu · 220 triệu)", (a.source, a.title, a.severity),
	("quy-tac", "Nợ quá hạn chiếm 54,5% tổng phải thu", "do"))
c("thân: quá hạn 120 triệu, tổng phải thu 220 triệu", "120 triệu" in a.body and "220 triệu" in a.body, a.body)
eq("vc.cho_qua_han: 28 đơn chờ giao quá 3 ngày (seed test_vc)", R("vc.cho_qua_han").title, "28 đơn chờ giao quá 3 ngày")
eq("cn.phai_tra_qua_han: 30.000.000 ≥ 1e6 → '30 triệu'", R("cn.phai_tra_qua_han").title,
	"30 triệu tiền hàng nhà cung cấp đã quá hạn chưa trả")
con_ngoac = frappe.db.sql(f"""SELECT signal_key FROM `tab{INSIGHT}` WHERE LOCATE('{{{{', CONCAT(IFNULL(title, ''),
	IFNULL(body, ''), IFNULL(rule_title, ''))) > 0""")
eq("không còn '{{' trong title / body / rule_title", con_ngoac, ())
eq("mọi tín hiệu: source quy-tac", frappe.db.sql(f"SELECT DISTINCT source FROM `tab{INSIGHT}` WHERE rule != 'ai'"),
	(("quy-tac",),))
eq("nhận định tự do của lượt trước → dong", R("ai:cong-no.receivables.kpis.net").status, "dong")
k = json.loads(t.kpis)
eq("kpis: phải thu 220.000.000, quá hạn 54,5 (bước 8 chạy)", (k.get("cong-no.receivables.kpis.receivable"),
	k.get("cong-no.receivables.kpis.overdue_pct")), (220000000.0, 54.5))
c("lock nhả sau lượt chạy", frappe.cache().get_value(LOCK_KEY) is None)
c("user trả về như cũ sau lượt chạy", frappe.session.user == "viewer@example.com", frappe.session.user)
eq("rank 1 là tín hiệu đỏ", R(frappe.db.sql(f"SELECT signal_key FROM `tab{INSIGHT}` WHERE `rank` = 1")[0][0]).severity,
	"do")


# ═══════════════════════════════════════════════════════════════════════════
print("D. Lượt đầy đủ với mô hình giả (run_type tay)")
xoa_run()
cai(ai_enabled=1)


def tai_chinh(obj):
	s1 = S(obj, "cn.qua_han_ty_le")
	return [
		ins(s1, "Nợ quá hạn {{cong-no.receivables.kpis.overdue_pct|pct}}",
			"Quá hạn {{cong-no.receivables.kpis.overdue|tien}}, tổng phải thu {{cong-no.receivables.kpis.receivable|tien}}, "
			"phải trả quá hạn {{phai-tra.payables.ap.due.overdue_total|tien}}.",
			["Kế toán: thúc thu trong 7 ngày."], severity="vang", priority=9),                 # hạ đỏ → vàng, prio 9
		ins(s1, "Lời thứ hai", "Bị bỏ vì trùng {{cong-no.receivables.kpis.net|tien}}."),         # trùng S → bỏ
		ins("S99", "Tín hiệu lạ", "Không có {{cong-no.receivables.kpis.net|tien}}."),            # S lạ → bỏ
		ins(S(obj, "cn.dso_cao"), "Thu tiền chậm", "Bình quân {{cong-no.receivables.kpis.dso.dso|so}} ngày.",
			priority=-3),
		ins(None, "Tổng phải trả", "Tổng phải trả {{phai-tra.payables.ap.total|tien}}.", priority=3),        # F_d
		ins(None, "Quỹ so với {{phai-tra.payables.ap.total|tien}} phải trả", "Quỹ hiện có "
			"{{phai-tra.payables.cash.total|tien}}.", priority=4),     # F_c: khoá theo path đầu của THÂN, không của title
		ins(None, "Số trần", "Khách trả chậm 1.250.000 đ, ròng {{cong-no.receivables.kpis.net|tien}}.", priority=5),
		ins(None, "Phải thu ròng", "Phải thu ròng {{cong-no.receivables.kpis.net|tien}} sau ứng trước.",
			priority=5),                                                                                       # F_b
		ins(None, "Khoản lớn nhất", "Khoản quá hạn lớn nhất {{cong-no.receivables.top_overdue[0].overdue|tien}}.",
			severity="do", priority=1),                                                                        # F_a
	]


def van_chuyen(obj):
	return [
		ins(S(obj, "vc.cho_qua_han"), "Đơn chờ", "Có 1.250.000 đơn chờ {{van-chuyen.overview.giao.total|so}}."),
		ins(S(obj, "vc.chua_xep_chuyen"), "Chưa xếp", "Chiếm 35% {{van-chuyen.overview.giao.xep.chua_xep|so}} đơn."),
		ins(S(obj, "vc.su_co_mo"), "Sự cố", "Thiệt hại 2 tỷ, {{van-chuyen.overview.su_co.mo_qua_n|so}} sự cố."),
		ins(S(obj, "vc.cuoc_canh_bao", "tra_bat_thuong"), "Cước", "Có {{van-chuyen.overview.khong_co|so}} chuyến."),
		ins(S(obj, "vc.cuoc_canh_bao", "sua_tay"), "Sửa tay",
			"Hình thức {{van-chuyen.overview.giao.cho_qua_han.rows[0].hinh_thuc|tien}}."),             # sai kiểu
		ins(S(obj, "vc.cuoc_canh_bao", "tra_chuyen_huy"), "Huỷ", "Nợ {{cong-no.receivables.kpis.overdue|tien}}."),
		ins(S(obj, "vc.xe_qua_han"), "Xe", "Giao {{van-chuyen.overview.giao.total|so}} đơn, xếp xe trong 7 ngày.",
			["Vận chuyển: xếp lịch đăng kiểm trong 7 ngày."]),                                         # hợp lệ
	]


def he_thong(obj):
	return [ins(S(obj, "ht.backup_cu"), "Chưa sao lưu", "Lỗi hệ thống 24 giờ: {{he-thong.error_log.tong|so}}.",
		["Quản trị: bật sao lưu."], severity="do", priority=5),
		ins(None, "Tự do hệ thống", "Hàng đợi {{he-thong.hang_doi.cho|so}} việc.", priority=5)]   # nhóm hệ thống: bỏ


out = chay("tay", **{"tai-chinh": tl(tai_chinh), "van-chuyen": tl(van_chuyen), "he-thong": tl(he_thong)})
run2 = out["run"]
eq("gọi đủ 7 nhóm theo đúng thứ tự (kinh-doanh, kho-sx có số nhưng chưa tín hiệu → vẫn gọi để nêu tự do)",
	[g["nhom"] for g in GOI], NHOM)
eq("mọi lời gọi: provider claude, model mặc định claude-sonnet-5-5, schema ghi_nhan_dinh",
	{(g["provider"], g["model"], g["schema_name"]) for g in GOI}, {("claude", "claude-sonnet-5-5", "ghi_nhan_dinh")})
c("timeout mỗi lời gọi trong [30, 300]", all(30 <= g["timeout"] <= 300 for g in GOI), [g["timeout"] for g in GOI])
eq("kinh-doanh / kho-sx: không tín hiệu trong đề bài", [len(g["obj"]["tin_hieu"]) for g in GOI[:2]], [0, 0])
eq("số tín hiệu gửi mỗi nhóm = số tín hiệu mở của nhóm (vc 7, tc 4, ns 5, attp 6, ht 1)",
	[len(g["obj"]["tin_hieu"]) for g in GOI[2:]], [7, 4, 5, 6, 1])
tt = tong(run2)
eq("run_type tay lưu ở dòng tổng và mọi dòng con", {r.run_type for r in rows_of(run2)}, {"tay"})
a = R("cn.qua_han_ty_le")
eq("S1: lời AI, số thật (54,5% · 120 triệu · 220 triệu · 30 triệu)", (a.source, a.title, a.body),
	("ai", "Nợ quá hạn 54,5%", "Quá hạn 120 triệu, tổng phải thu 220 triệu, phải trả quá hạn 30 triệu."))
eq("S1: mô hình hạ đỏ → vàng: vẫn đỏ", a.severity, "do")
eq("S1: priority 9 → kẹp 5", a.priority, 5)
eq("S1: advice 'trong 7 ngày' được giữ", a.advice, "Kế toán: thúc thu trong 7 ngày.")
eq("S1: rule_title giữ lời quy tắc", a.rule_title, "Nợ quá hạn chiếm 54,5% tổng phải thu")
c("S1: paths gồm path của lời AI (phai-tra…overdue_total)", "phai-tra.payables.ap.due.overdue_total"
	in json.loads(a.paths) and "cong-no.receivables.kpis.overdue_pct" in json.loads(a.paths), a.paths)
eq("S1: sections_used = cong-no + phai-tra", set(a.sections_used.splitlines()), {"cong-no", "phai-tra"})
c("S1: text_at = now, needs_check 0", (a.text_at, a.needs_check) == (D(2026, 10, 27, 10, 30), 0), a.text_at)
c("trùng S: lời thứ hai không thắng", "Lời thứ hai" not in (a.title + a.body))
eq("S lạ (S99): không tạo / không gắn gì", frappe.db.sql(f"SELECT COUNT(*) FROM `tab{INSIGHT}` WHERE title = "
	"'Tín hiệu lạ'")[0][0], 0)
d = R("cn.dso_cao")
eq("dso: priority −3 → kẹp 0, 244,9 ngày (208 tr / 310 tr × 365)", (d.source, d.priority, d.body),
	("ai", 0, "Bình quân 244,9 ngày."))
fr = {r.signal_key: r for r in free_rows("mo")}
eq("tự do: giữ 3 (đỏ trước, rồi priority cao): F_a, F_b, F_c", set(fr), {
	"ai:cong-no.receivables.top_overdue.overdue", "ai:cong-no.receivables.kpis.net", "ai:phai-tra.payables.cash.total"})
fa = fr.get("ai:cong-no.receivables.top_overdue.overdue")
c("tự do: khoá = 'ai:' + path đầu của thân bỏ chỉ số [0]; mảng cong-no; đỏ; source ai", fa is not None
	and (fa.section, fa.route, fa.severity, fa.source, fa.audience) == ("cong-no", "#/cong-no", "do", "ai",
	"lanh-dao") and "{{" not in fa.body and ("triệu" in fa.body or " đ" in fa.body), fa)
eq("tự do F_b: phải thu ròng 220 − 10 = 210 triệu", fr["ai:cong-no.receivables.kpis.net"].body,
	"Phải thu ròng 210 triệu sau ứng trước.")
eq("tự do F_c: mảng phai-tra, route #/phai-tra", (fr["ai:phai-tra.payables.cash.total"].section,
	fr["ai:phai-tra.payables.cash.total"].route), ("phai-tra", "#/phai-tra"))
c("tự do F_d (priority 3, thứ 4) bị cắt, không tạo dòng", R("ai:phai-tra.payables.ap.total") is None)
c("tự do của nhóm he-thong bị bỏ", R("ai:he-thong.hang_doi.cho") is None and not frappe.db.sql(
	f"SELECT name FROM `tab{INSIGHT}` WHERE rule = 'ai' AND section = 'he-thong'"))
h = R("ht.backup_cu")
eq("he-thong: tín hiệu nhận lời AI (0 lỗi 24 giờ)", (h.source, h.body), ("ai", "Lỗi hệ thống 24 giờ: 0."))
# Lời bị loại: lời quy tắc giữ nguyên, needs_check 1.
LOAI = {"vc.cho_qua_han": "28 đơn chờ giao quá 3 ngày", "vc.chua_xep_chuyen": "3 đơn tự giao chưa được xếp lên chuyến xe",
	"vc.su_co_mo": "3 sự cố vận chuyển mở quá 7 ngày chưa xử lý",
	"vc.cuoc_canh_bao:tra_bat_thuong": "1 chuyến ghi đã trả cước mà phiếu chi chưa duyệt",
	"vc.cuoc_canh_bao:sua_tay": "1 chuyến có cước sửa tay trong tháng",
	"vc.cuoc_canh_bao:tra_chuyen_huy": "1 chuyến đã huỷ nhưng tiền cước vẫn đã chi"}
for k, tieu_de in LOAI.items():
	r = R(k)
	eq(f"loại ({k}): needs_check 1, source quy-tac, lời quy tắc", (r.needs_check, r.source, r.title), (1, "quy-tac",
		tieu_de))
x = R("vc.xe_qua_han")
eq("vc.xe_qua_han: 'trong 7 ngày' hợp lệ → nhận", (x.source, x.needs_check, x.advice),
	("ai", 0, "Vận chuyển: xếp lịch đăng kiểm trong 7 ngày."))
cc = {r.step: r for r in con(run2)}
eq("một dòng / nhóm đã gọi, đủ 7, đều ok", {s: r.status for s, r in cc.items()}, {g: "ok" for g in NHOM})
eq("dòng nhóm: rejected / insights_ai (vc 6/1, tc 1/5, ht 0/1)", [(cc[g].rejected, cc[g].insights_ai) for g in
	("van-chuyen", "tai-chinh", "he-thong")], [(6, 1), (1, 5), (0, 1)])
eq("dòng tổng: insights_ai = 1 + 5 + 1 = 7, rejected = 6 + 1 = 7", (tt.status, tt.insights_ai, tt.rejected),
	("ok", 7, 7))
eq("trả về khớp dòng tổng", (out["accepted"], out["rejected"], out["ai"], out["signals"]), (7, 7, "ok", 23))
# 1000 × 3 + 100 × 15 = 4.500 USD / 1e6 = 0,0045 USD / lượt
eq("chi phí mỗi lượt gọi 0,0045 USD, cost_known 1, token 1000 / 100", {(r.tokens_in, r.tokens_out,
	round(float(r.cost_usd), 6), r.cost_known) for r in cc.values()}, {(1000, 100, 0.0045, 1)})
eq("dòng con: provider claude, run_id = dòng tổng", {(r.provider, r.run_id) for r in cc.values()}, {("claude", run2)})
eq("dòng con: signals = số tín hiệu đã gửi", [cc[g].signals for g in NHOM], [0, 0, 7, 4, 5, 6, 1])
k = json.loads(tt.kpis)
PATHS = {p for p, _k, _l in registry.KPIS}
c("kpis: JSON {path KPI: số}, mọi khoá thuộc registry.KPIS, mọi giá trị là số",
	k and set(k) <= PATHS and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in k.values()), k)
# ứng trước 10 tr → ròng 210 tr; 4 khách quá hạn; DSO 244,9; 1 hoá đơn mua quá hạn 30 tr
eq("kpis: số tính tay", [k.get(p) for p in ("cong-no.receivables.kpis.net", "cong-no.receivables.kpis.overdue_customers",
	"cong-no.receivables.kpis.dso.dso", "phai-tra.payables.ap.due.overdue_total", "phai-tra.payables.ap.due.overdue_count",
	"van-chuyen.overview.giao.cho_qua_han.qua_n")], [210000000.0, 4, 244.9, 30000000.0, 1, 28])
eq("dòng tổng: error trống khi mọi quy tắc chạy được", tt.error, None)

print("D2. Lượt sau (cùng ngày, 15:00): tự do không nêu lại → dong; bo-qua không gửi; dang-xu-ly gửi kèm trạng thái")
frappe.db.set_value(INSIGHT, R("cn.dso_cao").name, {"status": "bo-qua", "mute_until": None})
frappe.db.set_value(INSIGHT, R("cn.vuot_han_muc").name, {"status": "dang-xu-ly"})
luu()
seen_truoc = R("cn.qua_han_ty_le").seen_count
frappe.utils.FAKE_NOW_TIME = datetime.time(15, 0)
out = chay(**{"tai-chinh": tl(lambda o: [ins(None, "Phải thu ròng", "Ròng {{cong-no.receivables.kpis.net|tien}}.",
	priority=2)])})
frappe.utils.FAKE_NOW_TIME = datetime.time(10, 30)
g_tc = next(g for g in GOI if g["nhom"] == "tai-chinh")
rules_tc = {t["rule"]: t for t in g_tc["obj"]["tin_hieu"]}
c("bo-qua (cn.dso_cao) không gửi mô hình", "cn.dso_cao" not in rules_tc, list(rules_tc))
eq("dang-xu-ly (cn.vuot_han_muc) gửi kèm trang_thai dang-xu-ly", rules_tc.get("cn.vuot_han_muc", {}).get("trang_thai"),
	"dang-xu-ly")
eq("dang-xu-ly giữ trạng thái", R("cn.vuot_han_muc").status, "dang-xu-ly")
eq("tự do không nêu lại → dong (F_a, F_c); nêu lại → mo (F_b)", (R("ai:cong-no.receivables.top_overdue.overdue").status,
	R("ai:phai-tra.payables.cash.total").status, R("ai:cong-no.receivables.kpis.net").status), ("dong", "dong", "mo"))
eq("F_b: lời mới của lượt này", R("ai:cong-no.receivables.kpis.net").body, "Ròng 210 triệu.")
eq("lượt sau cùng ngày: seen_count không tăng", R("cn.qua_han_ty_le").seen_count, seen_truoc)
eq("lượt sau không nhận lời AI cho S1 → về lời quy tắc", (R("cn.qua_han_ty_le").source, R("cn.qua_han_ty_le").title),
	("quy-tac", "Nợ quá hạn chiếm 54,5% tổng phải thu"))
eq("so_ngay của tín hiệu mới hôm nay = 0", rules_tc["cn.qua_han_ty_le"]["so_ngay"], 0)
frappe.db.set_value(INSIGHT, R("cn.dso_cao").name, {"status": "mo"})
frappe.db.set_value(INSIGHT, R("cn.vuot_han_muc").name, {"status": "mo"})
luu()


# ═══════════════════════════════════════════════════════════════════════════
print("E. Mã giả: không tên / mã khách, NCC nào trong đề bài; lời lưu có tên thật")
xoa_run()
DOI_TAC = [(n, t) for n, t in frappe.db.sql("SELECT name, customer_name FROM `tabCustomer`")] + \
	[(n, t) for n, t in frappe.db.sql("SELECT name, supplier_name FROM `tabSupplier`")]
TEN = sorted({x for p in DOI_TAC for x in p if x})
c("DB có đủ khách / NCC để soát (6 khách, 3 NCC)", len(DOI_TAC) == 9, DOI_TAC)
# Khách theo name: COOP-1, DL-1, KH-ADV, KH-XUAN-HOA, NPP-A → KH#0005; NCC theo name: "NCC Bao bì" < "NCC Đường"
# (B < Đ) < "NCC-HUONG-QUE" ("-" > " ") → NCC Đường = NCC#0002.
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"admin_note":
	"Đã gọi Đại lý Minh Phát và NPP-B hôm qua; NCC Đường đòi tiền."})
luu()
# Chứng từ kèm tín hiệu (chỉ quản trị thấy): seed hiện không quy tắc nào kèm chứng từ → bọc run_rules THÊM chứng từ
# vào tín hiệu cn.qua_han_ty_le cho ca này (luồng còn lại vẫn thật).
_rr = registry.run_rules


def _rr_chung_tu(pack, overrides=None, only=None):
	out = _rr(pack, overrides, only)
	for s in out.signals:
		if s.key == "cn.qua_han_ty_le":
			s.documents = [{"doctype": "Sales Invoice", "name": "ACC-SINV-BIMAT-00042"}]
	return out


registry.run_rules = _rr_chung_tu


def tc_mask(obj):
	return [ins(S(obj, "cn.qua_han_ty_le"), "Khách {{cong-no.receivables.top_overdue[0].customer|chu}} nợ lâu",
		"KH#0005 nợ quá hạn nhiều nhất, NCC#0002 chờ thanh toán {{phai-tra.payables.ap.due.overdue_total|tien}}.",
		["Kinh doanh: làm việc với KH#0005."])]


out = chay(**{"tai-chinh": tl(tc_mask)})
registry.run_rules = _rr
eq("lượt có mã giả: 7 lời gọi", len(GOI), 7)
lo = [(g["nhom"], x) for g in GOI for x in TEN if x in g["user"] or x in g["system"]]
eq("không tên / mã khách, NCC nào (mọi Customer + Supplier của DB) trong user / system", lo, [])
g_tc = next(g for g in GOI if g["nhom"] == "tai-chinh")
t_tc = next(t for t in g_tc["obj"]["tin_hieu"] if t["rule"] == "cn.qua_han_ty_le")
eq("ghi chú quản trị: tên giữa câu bị che (Đại lý Minh Phát → KH#0005, NPP-B → KH#0006, NCC Đường → NCC#0002)", t_tc["ghi_chu_quan_tri"],
	"Đã gọi KH#0005 và KH#0006 hôm qua; NCC#0002 đòi tiền.")
pk = g_tc["obj"]["pack"]
eq("gói số: top_overdue[0].customer = mã giả KH#0005 (Đại lý Minh Phát = NPP-A)",
	pk["cong-no"]["receivables"]["top_overdue"][0]["customer"], "KH#0005")
a = R("cn.qua_han_ty_le")
eq("lời lưu: mã giả + placeholder chu → tên thật", (a.source, a.title, a.body, a.advice), ("ai",
	"Khách Đại lý Minh Phát nợ lâu", "Đại lý Minh Phát nợ quá hạn nhiều nhất, NCC Đường chờ thanh toán 30 triệu.",
	"Kinh doanh: làm việc với Đại lý Minh Phát."))
names_ins = [r[0] for r in frappe.db.sql(f"SELECT name FROM `tab{INSIGHT}`")]
docs = [d["name"] for r in frappe.db.sql(f"SELECT documents FROM `tab{INSIGHT}`") for d in json.loads(r[0] or "[]")]
c("chứng từ có thật trên Insight (ca này)", "ACC-SINV-BIMAT-00042" in docs, docs)
lo2 = [x for g in GOI for x in [*names_ins, *docs] if x in g["user"]]
eq("tên Insight, chứng từ không có trong user", lo2, [])
c("user không có khoá documents / admin_note / review_note / signal_key / needs_check", not any(
	f'"{f}"' in g["user"] for g in GOI for f in ("documents", "admin_note", "review_note", "signal_key", "needs_check")))
c("ghi chú quản trị gốc (chưa che) không có trong user", not any("Đại lý Minh Phát và" in g["user"] for g in GOI))

print("E2. ai_mask_parties = 0 → tên thật được gửi")
cai(ai_mask_parties=0)
out = chay()
g_tc = next(g for g in GOI if g["nhom"] == "tai-chinh")
c("tắt mã giả: tên thật có trong user (Đại lý Minh Phát, NCC Đường)", "Đại lý Minh Phát" in g_tc["user"]
	and "NCC Đường" in g_tc["user"] and "KH#0" not in g_tc["user"])
cai(ai_mask_parties=1)
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"admin_note": None})
luu()


# ═══════════════════════════════════════════════════════════════════════════
print("F. Bỏ cả bước AI: không khoá / vượt trần / trần 0 / 30 lượt — bước 1–4 + 8 vẫn chạy")


def ca_bo(nhan, status, error=None):
	tao_free(("nhan-su",), "ai:nhan-su.overview.bhxh.rui_ro", "nhan-su.overview.bhxh.rui_ro")
	frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"source": "ai", "title": "Lời AI hôm qua"})
	luu()
	out = chay(**{g: (lambda o: (_ for _ in ()).throw(AssertionError("không được gọi"))) for g in NHOM})
	run = out["run"]
	eq(f"{nhan}: không lời gọi mô hình", len(GOI), 0)
	eq(f"{nhan}: một dòng step ai status {status}", [(r.step, r.status, r.provider, r.error) for r in con(run)],
		[("ai", status, "claude", error)])
	t = tong(run)
	eq(f"{nhan}: dòng tổng ok, 23 tín hiệu, có kpis", (t.status, t.signals, bool(json.loads(t.kpis or "{}"))),
		("ok", 23, True))
	eq(f"{nhan}: lời quy tắc (source quy-tac, số đã thay)", (R("cn.qua_han_ty_le").source,
		R("cn.qua_han_ty_le").title), ("quy-tac", "Nợ quá hạn chiếm 54,5% tổng phải thu"))
	eq(f"{nhan}: tự do cũ → dong", R("ai:nhan-su.overview.bhxh.rui_ro").status, "dong")
	eq(f"{nhan}: trả ai = {status}", out["ai"], status)
	return out


del frappe.conf["bc_ai_anthropic_key"]
ca_bo("không khoá", "khong-khoa")
frappe.conf["bc_ai_anthropic_key"] = "   "
ca_bo("khoá chỉ có dấu cách", "khong-khoa")
frappe.conf["bc_ai_anthropic_key"] = KEY
xoa_run()
cai(ai_cap_claude_usd=0)
ca_bo("trần 0", "vuot-tran")
cai(ai_cap_claude_usd=0.01)
insert(RUN, run_type="ngay", step="kinh-doanh", provider="claude", status="ok", started=D(2026, 10, 3, 5, 30),
	cost_usd=0.01, cost_known=1, tokens_in=0, tokens_out=0, signals=0, insights_ai=0, rejected=0)
luu()
ca_bo("đã chi 0,01 ≥ trần 0,01 trong kỳ", "vuot-tran")
xoa_run()
cai(ai_cap_claude_usd=90)
for i in range(30):
	insert(RUN, run_type="ngay", step="tai-chinh", provider="claude", status="ok", started=D(2026, 10, 27, 1, 0),
		cost_usd=0, cost_known=1, tokens_in=0, tokens_out=0, signals=0, insights_ai=0, rejected=0)
luu()
ca_bo("30 lượt gọi hôm nay", "vuot-tran", "quá số lượt gọi trong ngày")
xoa_run()
cai(ai_enabled=0)
ca_bo("ai_enabled = 0 (lần 2, có lời AI cũ)", "tat")
cai(ai_enabled=1)


# ═══════════════════════════════════════════════════════════════════════════
print("G. Lỗi của mô hình")


def nem_loi(kind, msg="", tin=0, tout=0, model=""):
	def f(obj):
		e = llm.LLMError(kind, msg)
		e.tokens_in, e.tokens_out, e.model = tin, tout, model
		raise e
	return f


def nem_thuong(msg):
	def f(obj):
		raise RuntimeError(msg)
	return f


xoa_run()
tao_free(("cong-no", "phai-tra"), "ai:cong-no.receivables.kpis.net", "cong-no.receivables.kpis.net")
out = chay(**{"kinh-doanh": nem_loi("credit", "credit balance too low " + KEY), "kho-sx": tl([])})
run = out["run"]
eq("credit: đúng MỘT lời gọi (nhóm đầu), không gọi thêm", [g["nhom"] for g in GOI], ["kinh-doanh"])
eq("credit: dòng nhóm het-credit, không dòng nhóm nào khác", [(r.step, r.status) for r in con(run)],
	[("kinh-doanh", "het-credit")])
eq("credit: dòng tổng vẫn ok; trả ai het-credit", (tong(run).status, out["status"], out["ai"]), ("ok", "ok",
	"het-credit"))
c("credit: khoá không có trong error của dòng", KEY not in (con(run)[0].error or ""), con(run)[0].error)
eq("credit: nhóm còn lại giữ lời quy tắc; tự do cũ của tai-chinh → dong", (R("cn.qua_han_ty_le").source,
	R("ai:cong-no.receivables.kpis.net").status), ("quy-tac", "dong"))

xoa_run()
tao_free(("cong-no", "phai-tra"), "ai:cong-no.receivables.kpis.net", "cong-no.receivables.kpis.net")
# Mô hình giả: rate / timeout (không token), schema (đã tính tiền 500 / 50), refusal trả từ mô hình dự phòng CHƯA
# khai giá (ước theo giá mô hình đã yêu cầu), Exception thường chứa khoá, http chứa khoá, he-thong ok.
out = chay(**{"kinh-doanh": nem_loi("rate", "429"), "kho-sx": nem_loi("timeout", "đọc quá 300 s"),
	"van-chuyen": nem_loi("schema", "sai cấu trúc", 500, 50, "claude-sonnet-5-5"),
	"tai-chinh": nem_loi("refusal", "từ chối", 800, 0, "claude-du-phong-x"),
	"nhan-su": nem_thuong("hỏng " + KEY + " " + "x" * 50), "attp": nem_loi("http", "401 khoá " + KEY + " sai")})
run = out["run"]
eq("rate / timeout / schema / refusal / lỗi thường / http: nhóm sau VẪN được gọi (đủ 7)", [g["nhom"] for g in GOI],
	NHOM)
cc = {r.step: r for r in con(run)}
eq("trạng thái từng dòng", {g: cc[g].status for g in NHOM}, {"kinh-doanh": "loi", "kho-sx": "loi", "van-chuyen": "loi",
	"tai-chinh": "loi", "nhan-su": "loi", "attp": "loi", "he-thong": "ok"})
# schema: 500 × 3 + 50 × 15 = 2.250 / 1e6 = 0,00225; refusal: 800 × 3 / 1e6 = 0,0024 (giá của mô hình đã yêu cầu)
eq("lượt hỏng đã tính tiền: token + chi phí ghi lại", [(cc[g].tokens_in, cc[g].tokens_out, round(float(cc[g].cost_usd), 6),
	cc[g].cost_known) for g in ("van-chuyen", "tai-chinh")], [(500, 50, 0.00225, 1), (800, 0, 0.0024, 1)])
eq("refusal: model = mô hình thực trả lời", cc["tai-chinh"].model, "claude-du-phong-x")
eq("rate / timeout: 0 token, chi phí 0 đã biết", [(cc[g].tokens_in, cc[g].cost_usd, cc[g].cost_known) for g in
	("kinh-doanh", "kho-sx")], [(0, 0, 1), (0, 0, 1)])
eq("lỗi thường (không phải LLMError): dòng loi, error chỉ tên loại", cc["nhan-su"].error, "lỗi không lường: RuntimeError")
c("http có khoá: error đã xoá khoá", KEY not in (cc["attp"].error or "") and "401" in (cc["attp"].error or ""),
	cc["attp"].error)
eq("dòng tổng vẫn ok, lời quy tắc giữ, tự do cũ → dong", (tong(run).status, R("cn.qua_han_ty_le").source,
	R("ai:cong-no.receivables.kpis.net").status), ("ok", "quy-tac", "dong"))
c("lỗi thường: có Error Log, không khoá trong đó", any(r[0] == "bc.ai bước AI nhóm nhan-su" for r in LOG), LOG[-3:])

print("G2. Lỗi khi XỬ LÝ lời (sau lượt gọi đã tính tiền): rollback phần ghi dở, nhóm sau vẫn gọi")
# Ép lỗi lập trình: render.render_insight ném ở insight THỨ HAI của nhóm tai-chinh (insight đầu đã ghi).
from bc.ai import render  # noqa: E402
_ri = render.render_insight
dem_ri = {"n": 0}


def _ri_hong(raw, pack, sections, mask=None, kinds=None, nguon=None):
	if "cong-no" in sections:
		dem_ri["n"] += 1
		if dem_ri["n"] == 2:
			raise ZeroDivisionError("hỏng giữa chừng")
	return _ri(raw, pack, sections, mask, kinds=kinds, nguon=nguon)


render.render_insight = _ri_hong
xoa_run()
out = chay(**{"tai-chinh": tl(lambda o: [ins(S(o, "cn.qua_han_ty_le"), "Lời một {{cong-no.receivables.kpis.net|tien}}",
	"Thân {{cong-no.receivables.kpis.net|tien}}."), ins(S(o, "cn.dso_cao"), "Lời hai", "Thân {{cong-no.receivables."
	"kpis.dso.dso|so}}.")], 700, 70)})
render.render_insight = _ri
cc = {r.step: r for r in con(out["run"])}
eq("nhóm hỏng khi xử lý: dòng loi, token 700 / 70 + chi phí ghi lại", (cc["tai-chinh"].status, cc["tai-chinh"].error,
	cc["tai-chinh"].tokens_in, round(float(cc["tai-chinh"].cost_usd), 6)), ("loi", "lỗi không lường: ZeroDivisionError", 700,
	0.00315))   # 700 × 3 + 70 × 15 = 3.150 / 1e6
eq("lời đã gắn cho S1 trước khi hỏng bị ROLLBACK (về lời quy tắc)", R("cn.qua_han_ty_le").source, "quy-tac")
eq("nhóm sau (nhan-su, attp, he-thong) vẫn được gọi", [g["nhom"] for g in GOI][-3:], ["nhan-su", "attp", "he-thong"])

print("G3. Mô hình chưa khai giá → cost_known 0")
xoa_run()
cai(ai_claude_model="claude-chua-khai-gia")
out = chay()
eq("mọi dòng gọi: cost_known 0, cost 0, model claude-chua-khai-gia", {(r.cost_known, r.cost_usd, r.model) for r in
	con(out["run"])}, {(0, 0, "claude-chua-khai-gia")})
bo_cai("ai_claude_model")

print("G4. Quy tắc không chạy được (khối nguồn _error): tín hiệu cũ còn mở nhưng KHÔNG gửi mô hình (số đã cũ)")
import bc.api.cn as _cn  # noqa: E402
_gr = _cn.get_receivables


def _gr_hong(*a, **k):
	raise RuntimeError("nguồn công nợ hỏng")


xoa_run()
_cn.get_receivables = _gr_hong
out = chay()
_cn.get_receivables = _gr
g_tc = next((g for g in GOI if g["nhom"] == "tai-chinh"), None)
eq("tai-chinh vẫn gọi (phai-tra còn số), chỉ gửi tín hiệu của lượt này: cn.phai_tra_qua_han",
	g_tc and [t["rule"] for t in g_tc["obj"]["tin_hieu"]], ["cn.phai_tra_qua_han"])
eq("cn.qua_han_ty_le cũ vẫn mở (không đóng)", R("cn.qua_han_ty_le").status, "mo")
c("gói số gửi đi không có khối cong-no hỏng", g_tc and "cong-no" not in g_tc["obj"]["pack"], g_tc and list(g_tc["obj"]["pack"]))


# ═══════════════════════════════════════════════════════════════════════════
print("H. Trần chạm GIỮA lượt; 30 lượt / ngày giữa lượt; hết thời gian")
xoa_run()
cai(ai_cap_claude_usd=0.004)     # lượt 1: đã chi 0 < 0,004 → gọi; sau đó 0,0045 ≥ 0,004 → dừng
out = chay()
eq("trần chạm sau nhóm đầu: chỉ gọi kinh-doanh", [g["nhom"] for g in GOI], ["kinh-doanh"])
eq("dòng: kinh-doanh ok, kho-sx vuot-tran, không dòng nào sau", [(r.step, r.status, r.error) for r in con(out["run"])],
	[("kinh-doanh", "ok", None), ("kho-sx", "vuot-tran", None)])
eq("dòng tổng ok; trả ai vuot-tran", (tong(out["run"]).status, out["ai"]), ("ok", "vuot-tran"))
cai(ai_cap_claude_usd=90)
xoa_run()
for i in range(29):
	insert(RUN, run_type="ngay", step="tai-chinh", provider="claude", status="loi", started=D(2026, 10, 27, 1, 0),
		cost_usd=0, cost_known=1, tokens_in=0, tokens_out=0, signals=0, insights_ai=0, rejected=0)
luu()
out = chay()
eq("29 lượt sẵn: gọi đúng 1 lượt nữa", [g["nhom"] for g in GOI], ["kinh-doanh"])
eq("lượt thứ 31 bị chặn: dòng vuot-tran 'quá số lượt gọi trong ngày'", [(r.step, r.status, r.error)
	for r in con(out["run"])], [("kinh-doanh", "ok", None), ("kho-sx", "vuot-tran", "quá số lượt gọi trong ngày")])

xoa_run()
_time = pipeline.time


class _Dong:
	"""time.monotonic giả: lần đầu (t0) 0, sau đó 1.501 giây → còn 1800 − 240 − 1501 = 59 s < 60."""
	n = 0

	@classmethod
	def monotonic(cls):
		cls.n += 1
		return 0.0 if cls.n == 1 else 1501.0


pipeline.time = _Dong
out = chay()
pipeline.time = _time
eq("hết thời gian (còn 59 s < 60): không gọi", len(GOI), 0)
eq("một dòng nhóm đầu: loi 'hết thời gian lượt chạy'", [(r.step, r.status, r.error) for r in con(out["run"])],
	[("kinh-doanh", "loi", "hết thời gian lượt chạy")])
eq("dòng tổng vẫn ok", tong(out["run"]).status, "ok")


# ═══════════════════════════════════════════════════════════════════════════
print("I. Vòng đời qua nhiều ngày (AI tắt)")
cai(ai_enabled=0)
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}`")
xoa_run()
K = "cn.qua_han_ty_le"
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 28)
chay()
r = R(K)
eq("28/10: mới → mo, seen 1, first_seen 28/10 10:30", (r.status, r.seen_count, r.first_seen), ("mo", 1,
	D(2026, 10, 28, 10, 30)))
frappe.utils.FAKE_NOW_TIME = datetime.time(16, 0)
chay()
r = R(K)
eq("28/10 lượt 2: seen vẫn 1, last_seen 16:00", (r.seen_count, r.last_seen), (1, D(2026, 10, 28, 16, 0)))
frappe.utils.FAKE_NOW_TIME = datetime.time(10, 30)
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 29)
chay()
r = R(K)
eq("29/10: còn → seen 2, first_seen giữ 28/10", (r.status, r.seen_count, r.first_seen), ("mo", 2,
	D(2026, 10, 28, 10, 30)))
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 30)
_cn.get_receivables = _gr_hong
out = chay()
_cn.get_receivables = _gr
r = R(K)
eq("30/10 khối nguồn _error: KHÔNG đóng, seen giữ 2", (r.status, r.seen_count), ("mo", 2))
c("dòng tổng ok, error liệt kê cn.qua_han_ty_le không chạy", tong(out["run"]).status == "ok"
	and K in (tong(out["run"]).error or "") and (tong(out["run"]).error or "").startswith("quy tắc không chạy được"),
	tong(out["run"]).error)
c("trả not_run có cn.qua_han_ty_le", K in out["not_run"], out["not_run"])
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 31)
child("BC Settings", "BC Settings", "BC AI Rule", "ai_rules", [{"rule_key": K, "disabled": 0, "threshold": 90,
	"threshold_red": 95}])
frappe.db.sql("UPDATE `tabBC AI Rule` SET idx = 2 WHERE rule_key = %s", (K,))
luu()
chay()
r = R(K)
eq("31/10 ngưỡng 90 / 95 (54,5 không vượt): dong, closed_on 31/10", (r.status, r.closed_on), ("dong",
	D(2026, 10, 31, 10, 30)))
frappe.db.sql("DELETE FROM `tabBC AI Rule` WHERE rule_key = %s", (K,))
luu()
frappe.utils.FAKE_TODAY = datetime.date(2026, 11, 1)
chay()
r = R(K)
eq("1/11 xuất hiện lại: mo, first_seen 1/11, seen 1", (r.status, r.first_seen, r.seen_count), ("mo",
	D(2026, 11, 1, 10, 30), 1))
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 27)


# ═══════════════════════════════════════════════════════════════════════════
print("J. Khoá chống chạy trùng; lỗi giữa lượt")
n_run = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]
frappe.cache().set_value(LOCK_KEY, 7)
out = chay()
eq("khoá đang giữ → dang-chay", out, {"status": "dang-chay"})
eq("không dòng Run mới", frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0], n_run)
eq("khoá không bị đụng", frappe.cache().get_value(LOCK_KEY), 7)
frappe.cache().delete_value(LOCK_KEY)

from bc.ai import collect  # noqa: E402
_build = collect.build


def _build_hong(today=None):
	frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET title = 'GHI DỞ' WHERE signal_key = %s", (K,))   # ghi dở → rollback
	raise ValueError("collect hỏng " + KEY)


collect.build = _build_hong
n_log = len(LOG)
try:
	out = chay()
	nem_ra = False
except Exception:  # noqa: BLE001
	nem_ra = True
collect.build = _build
c("lỗi giữa lượt: không ném ra cho nơi gọi", not nem_ra)
eq("trả status loi + run", (out.get("status"), bool(out.get("run"))), ("loi", True))
t = tong(out["run"])
eq("dòng tổng loi, error = tên loại lỗi, có finished", (t.status, t.error, t.finished is not None),
	("loi", "ValueError", True))
c("dòng tổng còn sau ROLLBACK (đã commit trước)", t.name == out["run"])
eq("phần ghi dở bị rollback", R(K).title, "Nợ quá hạn chiếm 54,5% tổng phải thu")
c("có Error Log bc.ai run_daily", any(r[0] == "bc.ai run_daily" for r in LOG[n_log:]), LOG[n_log:])
c("khoá được nhả", frappe.cache().get_value(LOCK_KEY) is None)
out = chay()
eq("lượt sau chạy bình thường", (out["status"], tong(out["run"]).status), ("ok", "ok"))

_finish = store.rerank


def _rerank_hong():
	raise KeyError("rerank")


store.rerank = _rerank_hong
out = chay()
store.rerank = _finish
eq("lỗi SAU bước 4 (rerank): dòng tổng loi KeyError, tín hiệu đã lưu còn", (tong(out["run"]).status,
	tong(out["run"]).error, R(K).status), ("loi", "KeyError", "mo"))
c("khoá được nhả", frappe.cache().get_value(LOCK_KEY) is None)


# ═══════════════════════════════════════════════════════════════════════════
print("K. Lộ khoá / đề bài")
# Đề bài của một lượt gọi có số (tai-chinh) và system prompt: lấy đoạn dài, đặc trưng.
cai(ai_enabled=1)
xoa_run()
out = chay(**{"nhan-su": nem_thuong("lỗi chứa khoá " + KEY), "attp": nem_loi("http", "khoá " + KEY)})
mau_user = [g["user"][40:160] for g in GOI if len(g["user"]) > 200]
mau_sys = GOI[0]["system"][300:420]
c("có mẫu đề bài để soát", len(mau_user) >= 5 and len(mau_sys) > 100)


def cot(doctype):
	return [" ".join("" if v is None else str(v) for v in r) for r in frappe.db.sql(f"SELECT * FROM `tab{doctype}`")]


TAT_CA = cot(RUN) + cot(INSIGHT)
eq("khoá không có trong cột nào của BC AI Run / BC AI Insight", [x[:80] for x in TAT_CA if KEY in x], [])
eq("khoá không có trong tham số log_error nào", [str(r)[:80] for r in LOG if KEY in str(r)], [])
eq("khoá không có trong giá trị trả của run_daily", [o for o in KQ if KEY in json.dumps(o, default=str)], [])
eq("đề bài (user) không lưu ở đâu", [m[:30] for m in mau_user if any(m in x for x in TAT_CA)
	or any(m in str(r) for r in LOG)], [])
eq("system prompt không lưu ở đâu", any(mau_sys in x for x in TAT_CA) or any(mau_sys in str(r) for r in LOG), False)
eq("không một lần ra mạng trong cả bộ thử", MANG, [])


# ═══════════════════════════════════════════════════════════════════════════
print("L. Model hằng ngày một nơi (D15); che tên mặc định khi ô chưa từng lưu (P6); gói gửi đi bỏ NO_SEND; kieu (D8)")
import bc.api.vc as _vc  # noqa: E402
import bc.api.ai as API  # noqa: E402

_gov = _vc.get_overview
VC_GOI = []


def _gov_ghi(*a, **k):
	VC_GOI.append(dict(k))
	return _gov(*a, **k)


xoa_run()
cai(ai_enabled=1, ai_claude_model="   ")          # chỉ dấu cách = để trống
bo_cai("ai_mask_parties")                         # chưa từng lưu (site cũ chưa migrate)
_vc.get_overview = _gov_ghi
out = chay()
_vc.get_overview = _gov
c("(tiền đề) ô ai_mask_parties không có dòng trong tabSingles; ô model chỉ có dấu cách", not frappe.db.sql(
	"SELECT 1 FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'ai_mask_parties'")
	and frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'ai_claude_model'")
	[0][0].strip() == "")
eq("model trống → mọi lời gọi dùng bc.ai.daily_model() = claude-sonnet-5-5", {g["model"] for g in GOI},
	{"claude-sonnet-5-5"})
eq("… dòng Run ghi đúng model đó (màn quản trị và lượt chạy nói cùng một model)", {r.model for r in con(out["run"])},
	{"claude-sonnet-5-5"})
# Mọi tên đối tác: hồ sơ Customer / Supplier + tên chép trên hoá đơn đã duyệt (khách chỉ có trên hoá đơn cũng là khách).
TEN_HD = sorted({x for q in ("SELECT customer, customer_name FROM `tabSales Invoice` WHERE docstatus = 1",
	"SELECT supplier, supplier_name FROM `tabPurchase Invoice` WHERE docstatus = 1") for r in frappe.db.sql(q)
	for x in r if x} | set(TEN))
c("(tiền đề) có tên để soát: hồ sơ + tên trên hoá đơn (NPP Hà Nội, Co.op Mart …)", len(TEN_HD) >= 12
	and "NPP Hà Nội" in TEN_HD, TEN_HD)
eq("che tên chưa từng lưu = BẬT: không tên khách / NCC nào trong user", [(g["nhom"], x) for g in GOI for x in TEN_HD
	if x in g["user"]], [])
c("… mà đề bài vẫn có mã giả (che thật, không phải bỏ khối)", any("KH#" in g["user"] for g in GOI))
eq("collect gọi vc.get_overview của tháng này VÀ tháng trước (2026-09)", sorted(str(k.get("thang")) for k in VC_GOI),
	["2026-09", "None"])
g_vc = next(g for g in GOI if g["nhom"] == "van-chuyen")
eq("gói vận chuyển gửi đi: overview (+ _ai số quy tắc tự tính), KHÔNG overview_truoc (registry.NO_SEND)",
	sorted(g_vc["obj"]["pack"]["van-chuyen"]), ["_ai", "overview"])
eq("không đề bài nào nhắc overview_truoc", [g["nhom"] for g in GOI if "overview_truoc" in g["user"]], [])
g_tc = next(g for g in GOI if g["nhom"] == "tai-chinh")
kieu = g_tc["obj"].get("kieu") or {}
c("tai-chinh: 'kieu' có kiểu đúng của số (overdue_pct pct, overdue tien, overdue_customers so)",
	(kieu.get("cong-no.receivables.kpis.overdue_pct"), kieu.get("cong-no.receivables.kpis.overdue"),
	kieu.get("cong-no.receivables.kpis.overdue_customers")) == ("pct", "tien", "so"), kieu)
c("… chỉ path của mảng trong gói nhóm này (cong-no / phai-tra)", kieu and all(p.split(".")[0] in ("cong-no", "phai-tra")
	for p in kieu), sorted(kieu)[:5])
bo_cai("ai_claude_model")
cai(ai_mask_parties=1)


# ═══════════════════════════════════════════════════════════════════════════
print("M. Sang tháng: cảnh báo trả cước KHÔNG tự đóng ngày 1 (D13 — collect lấy thêm tháng trước)")
cai(ai_enabled=0)
xoa_run()
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 31)
chay()
CUOC = ("vc.cuoc_canh_bao:tra_bat_thuong", "vc.cuoc_canh_bao:tra_chuyen_huy", "vc.cuoc_canh_bao:sua_tay")
eq("31/10: ba cảnh báo cước đang mở", [R(k).status for k in CUOC], ["mo", "mo", "mo"])
frappe.utils.FAKE_TODAY = datetime.date(2026, 11, 1)
frappe.utils.FAKE_NOW_TIME = datetime.time(5, 30)
out = chay()
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 27)
frappe.utils.FAKE_NOW_TIME = datetime.time(10, 30)
c("01/11 05:30: quy tắc cước CHẠY được (có số tháng trước), không nằm trong not_run",
	"vc.cuoc_canh_bao" not in out["not_run"], out["not_run"])
eq("… trả cước bất thường / chuyến huỷ đã chi: vẫn mở, last_seen 01/11 05:30 (tháng trước góp số)",
	[(R(k).status, R(k).last_seen) for k in CUOC[:2]], [("mo", D(2026, 11, 1, 5, 30))] * 2)
c("… lời nói rõ 'tính cả tháng này và tháng trước'", all("tháng này và tháng trước" in (R(k).body or "")
	for k in CUOC[:2]), [R(k).body for k in CUOC[:2]])
eq("… cước sửa tay vẫn theo tháng: tháng 11 chưa có → dong", R(CUOC[2]).status, "dong")
cai(ai_enabled=1)


# ═══════════════════════════════════════════════════════════════════════════
print("N. Mảng đang ẩn (P10, D5): lượt chạy dưới người xem vẫn thu số; mô hình không thấy; lời AI theo mọi mảng đã thấy")
xoa_run()
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE rule = 'ai'")
luu()
cai(hidden_sections="cong-no")
frappe.session.user = "viewer@example.com"


def tc_an(obj):
	return [ins(S(obj, "cn.phai_tra_qua_han"), "Phải trả quá hạn", "Phải thu ròng {{cong-no.receivables.kpis.net|tien}}."),
		ins(None, "Quỹ", "Quỹ hiện có {{phai-tra.payables.cash.total|tien}}.", priority=2)]


out = chay(**{"tai-chinh": tl(tc_an)})
c("user trả về người xem sau lượt chạy", frappe.session.user == "viewer@example.com", frappe.session.user)
eq("lượt chạy dưới người xem, cong-no ĐANG ẨN: mọi quy tắc chạy được (collect dưới Administrator)", out["not_run"], {})
eq("… ba tín hiệu cong-no vẫn mở và vừa được thấy lại lúc 10:30", [(R(k).status, R(k).last_seen) for k in
	("cn.qua_han_ty_le", "cn.vuot_han_muc", "cn.dso_cao")], [("mo", D(2026, 10, 27, 10, 30))] * 3)
g_tc = next(g for g in GOI if g["nhom"] == "tai-chinh")
eq("tai-chinh: gói gửi đi chỉ phai-tra; tín hiệu gửi đi chỉ cn.phai_tra_qua_han", (list(g_tc["obj"]["pack"]),
	[t["rule"] for t in g_tc["obj"]["tin_hieu"]]), (["phai-tra"], ["cn.phai_tra_qua_han"]))
eq("không đề bài nào có số / path / khoá của mảng cong-no", [g["nhom"] for g in GOI if "cong-no" in g["user"]
	or "receivables" in g["user"]], [])
eq("lời AI trích số của mảng đang ẩn → loại (giữ lời quy tắc, needs_check 1)", (R("cn.phai_tra_qua_han").source,
	R("cn.phai_tra_qua_han").needs_check), ("quy-tac", 1))
fq = R("ai:phai-tra.payables.cash.total")
eq("tự do của mảng đang hiện: tạo, sections_used chỉ phai-tra (gói chỉ có phai-tra)", fq and (fq.status,
	set(fq.sections_used.splitlines())), ("mo", {"phai-tra"}))
frappe.session.user = "Administrator"
ad = {i["id"] for i in API.get_feed()["insights"]}
frappe.session.user = "viewer@example.com"
vw = API.get_feed()["insights"]
c("quản trị thấy tín hiệu cong-no; người xem không thấy thẻ nào của cong-no", R("cn.qua_han_ty_le").name in ad
	and not [i for i in vw if i["section"] == "cong-no"], [i["title"] for i in vw if i["section"] == "cong-no"])

# Lời AI viết khi cong-no còn hiện → quản trị ẩn cong-no SAU lượt chạy → người xem không còn thấy lời đó.
cai(hidden_sections="")


def tc_hien(obj):
	return [ins(S(obj, "cn.phai_tra_qua_han"), "Tiền hàng NCC quá hạn",
		"Còn {{phai-tra.payables.ap.due.overdue_total|tien}} chưa trả, khách lớn đang chậm trả nên tiền về chậm."),
		ins(None, "Quỹ", "Quỹ hiện có {{phai-tra.payables.cash.total|tien}}.", priority=2)]


out = chay(**{"tai-chinh": tl(tc_hien)})
p2, fq = R("cn.phai_tra_qua_han"), R("ai:phai-tra.payables.cash.total")
eq("lời AI (không placeholder cong-no) gắn sections_used = mọi mảng của gói đã gửi (cong-no + phai-tra)",
	(p2.source, set(p2.sections_used.splitlines())), ("ai", {"cong-no", "phai-tra"}))
eq("tự do cũng vậy", set(fq.sections_used.splitlines()), {"cong-no", "phai-tra"})
cai(hidden_sections="cong-no")                    # quản trị ẩn SAU lượt chạy, chưa chạy lại
frappe.session.user = "Administrator"
ad = {i["id"] for i in API.get_feed()["insights"]}
frappe.session.user = "viewer@example.com"
vw = {i["id"] for i in API.get_feed()["insights"]}
c("người xem: không còn thấy lời AI viết khi đã thấy số cong-no (tín hiệu + tự do)", p2.name not in vw
	and fq.name not in vw, vw & {p2.name, fq.name})
c("quản trị vẫn thấy cả hai", {p2.name, fq.name} <= ad)
out = chay(**{"tai-chinh": tl(tc_hien)})          # lượt sau (cong-no vẫn ẩn) viết lại → hiện lại
vw = {i["id"] for i in API.get_feed()["insights"]}
eq("lượt sau viết lại khi cong-no ẩn: sections_used chỉ phai-tra → người xem thấy lại", (set(R("cn.phai_tra_qua_han")
	.sections_used.splitlines()), p2.name in vw, fq.name in vw), ({"phai-tra"}, True, True))
cai(hidden_sections="")


# ═══════════════════════════════════════════════════════════════════════════
print("O. Một lượt đầy đủ trên dữ liệu khó: tiêu đề Error Log (S1), tên cũ trên hoá đơn (S2), tên NCC giữa câu (S3),")
print("   mã của nhóm khác (S4), sai kiểu số (N2), chủ đề bỏ qua quay lại qua lời tự do (N4)")
BI_MAT = ["tran.thi.b@hgc.vn", "0912345678", "Nguyễn Văn Tèo", "tran.thi.b", "Duplicate entry", "lehoa@x.vn",
	"NPP Hà Nội", "NPP Thăng Long", "Cát Vàng Sông Hồng"]
for i, (t, n) in enumerate((("(1062, \"Duplicate entry 'tran.thi.b@hgc.vn' for key 'email'\")", 3),
		("frappe.exceptions.ValidationError: Khách Nguyễn Văn Tèo vượt hạn mức, gọi 0912345678", 2),
		("tran.thi.b locked", 2), ("KeyError: 'lehoa@x.vn'", 1), ("frappe.exceptions.ValidationError", 1))):
	for j in range(n):
		insert("Error Log", method=t[:140], error="Traceback (most recent call last): ...",
			creation=D(2026, 10, 27, 9, i * 5 + j))
# Đổi tên khách kiểu ERPNext: Link si.customer đổi, si.customer_name (ảnh chụp) giữ tên cũ.
insert("Customer", name="NPP Thăng Long", customer_name="NPP Thăng Long")
frappe.db.sql("UPDATE `tabSales Invoice` SET customer = 'NPP Thăng Long' WHERE customer = 'NPP Hà Nội'")
# Nguồn cát ATTP là một NCC có thật: tên nằm GIỮA câu "Nguồn: …".
insert("Supplier", name="NCC-CAT-01", supplier_name="Công ty Cát Vàng Sông Hồng")
insert("SX Nhat Ky Cat", ngay="2026-10-20", viec="Nhập cát", ncc_cat="NCC-CAT-01", ten_ncc="Công ty Cát Vàng Sông Hồng",
	doi_nguon=1, kln="", luu_lo_mau=0, so_cu=0, creation=D(2026, 10, 20, 8, 0))
insert("SX Nhat Ky Cat", ngay="2026-10-21", viec="Rang khô đưa dùng", ncc_cat="NCC-CAT-01",
	ten_ncc="Công ty Cát Vàng Sông Hồng", doi_nguon=0, so_cu=0, creation=D(2026, 10, 21, 8, 0))
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"status": "bo-qua", "mute_until": None})   # bỏ qua hẳn
luu()
MA = {}


def kd_o(obj):
	rows = obj["pack"]["tong-quan"]["top_customers"]["rows"]
	MA["kd"] = rows[0]["customer"]
	return [ins(None, "Khách lớn nhất", "Khách " + rows[0]["customer"]
		+ " mua nhiều nhất từ đầu năm: {{tong-quan.top_customers.rows[0].amount|tien}}.", priority=3)]


def tc_o(obj):
	MA["tc"] = obj["pack"]["cong-no"]["receivables"]["top_overdue"][0]["customer"]
	return [ins(S(obj, "cn.dso_cao"), "Khách quá hạn", "Có {{cong-no.receivables.kpis.overdue_customers|pct}} khách."),
		ins(None, "Nợ quá hạn cao", "Nợ quá hạn chiếm {{cong-no.receivables.kpis.overdue_pct|pct}}.", priority=5),
		ins(None, "Phải trả quá hạn", "Phải trả quá hạn {{phai-tra.payables.ap.due.overdue_total|tien}}.", priority=4),
		ins(None, "Quỹ", "Quỹ hiện có {{phai-tra.payables.cash.total|tien}}.", priority=3)]


def ns_o(obj):
	t = obj["tin_hieu"][0]
	MA["ns_user"] = json.dumps(obj, ensure_ascii=False)
	return [ins(t["id"], "Nhân sự", t["loi_quy_tac"].split(" — ")[0] + ". Khách " + MA["tc"] + " cũng cần lưu ý.")]


def attp_o(obj):
	m = re.search(r"Nguồn:? (NCC#\d+)", json.dumps(obj, ensure_ascii=False))
	MA["attp"] = m and m.group(1)
	t = obj["tin_hieu"][0]
	MA["attp_rule"] = t["rule"]
	return [ins(t["id"], "Nguồn cát", t["loi_quy_tac"].split(" — ")[0] + ". Nguồn cát " + str(MA["attp"])
		+ " vừa đổi, cần kiểm kim loại nặng.")]


xoa_run()
out = chay(**{"kinh-doanh": tl(kd_o), "tai-chinh": tl(tc_o), "nhan-su": tl(ns_o), "attp": tl(attp_o)})
U = {g["nhom"]: g["user"] for g in GOI}
eq("(tiền đề) đủ 7 nhóm được gọi", list(U), NHOM)
eq("S1/S2/S3: không e-mail / SĐT / tên trong tiêu đề Error Log, không tên khách cũ / mới, không tên NCC cát trong user",
	[(n, x) for n, u in U.items() for x in BI_MAT if x in u], [])
c("S1: he-thong vẫn gửi nhóm lỗi dưới nhãn an toàn (tên lớp lỗi / '(khác)')", '"(khác)"' in U["he-thong"]
	and "ValidationError" in U["he-thong"], U["he-thong"][:300])
c("S3: câu ATTP có nguồn cát mang mã giả NCC#…", bool(MA.get("attp")), MA.get("attp"))
TAT_CA = cot(RUN) + cot(INSIGHT)
eq("S1: không chuỗi nào của tiêu đề Error Log trong BC AI Run / Insight", [x for x in ("tran.thi.b", "0912345678",
	"Nguyễn Văn Tèo", "lehoa@x.vn", "Duplicate entry") if any(x in y for y in TAT_CA)], [])
fk = R("ai:tong-quan.top_customers.rows.amount")
c("S2: lời lưu có TÊN THẬT của khách lớn nhất (mã giả đã đổi lại), không còn mã", fk is not None and "KH#" not in fk.body
	and any(x in fk.body for x in ("NPP Hà Nội", "NPP Thăng Long")), fk and fk.body)
at = frappe.db.sql(f"SELECT body, source FROM `tab{INSIGHT}` WHERE rule = %s AND source = 'ai'", (MA.get("attp_rule"),),
	as_dict=True)
c("S3: lời ATTP lưu có tên NCC thật 'Công ty Cát Vàng Sông Hồng', không còn mã", at and "Công ty Cát Vàng Sông Hồng"
	in at[0].body and "NCC#" not in at[0].body, at)
c("S4: (tiền đề) mã khách của nhóm tai-chinh không có trong đề bài nhan-su", MA.get("tc") and MA["tc"].startswith("KH#")
	and MA["tc"] not in MA.get("ns_user", ""), MA.get("tc"))
ns_ai = frappe.db.sql(f"SELECT signal_key, source, needs_check, body FROM `tab{INSIGHT}` WHERE section = 'nhan-su' "
	"AND needs_check = 1", as_dict=True)
eq("S4: lời nhan-su nhắc mã của nhóm khác → loại (lời quy tắc, needs_check 1), không thành tên thật",
	[(r.source, r.needs_check) for r in ns_ai], [("quy-tac", 1)])
eq("S4: tên thật của mã đó (Đại lý Minh Phát) không nằm trong lời nhân sự nào", [r.signal_key for r in
	frappe.db.sql(f"SELECT signal_key, body, title FROM `tab{INSIGHT}` WHERE section = 'nhan-su'", as_dict=True)
	if "Minh Phát" in (r.body or "") + (r.title or "")], [])
eq("N2: số đếm (overdue_customers) viết |pct → loại", (R("cn.dso_cao").source, R("cn.dso_cao").needs_check),
	("quy-tac", 1))
eq("N4: tự do trên số của chủ đề đang bỏ qua (overdue_pct) → không tạo", R("ai:cong-no.receivables.kpis.overdue_pct"),
	None)
eq("N4: tự do chỉ lặp tín hiệu quy tắc đang mở (phải trả quá hạn) → không tạo", R(
	"ai:phai-tra.payables.ap.due.overdue_total"), None)
eq("N4: tự do khác (quỹ) vẫn nhận", R("ai:phai-tra.payables.cash.total").status, "mo")
cc = {r.step: r for r in con(out["run"])}
eq("dòng tai-chinh: rejected 2 (sai kiểu + chủ đề bỏ qua; lặp tín hiệu không tính), insights_ai 1",
	(cc["tai-chinh"].rejected, cc["tai-chinh"].insights_ai), (2, 1))
eq("cn.qua_han_ty_le vẫn bo-qua", R("cn.qua_han_ty_le").status, "bo-qua")
frappe.session.user = "viewer@example.com"
vw = API.get_feed()["insights"]
eq("người xem: không thẻ nào nói tỷ lệ nợ quá hạn 54,5%", [i["title"] for i in vw if "54,5" in i["title"] + i["body"]],
	[])
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"status": "mo"})
luu()


# ═══════════════════════════════════════════════════════════════════════════
print("P. Quy tắc ném lỗi / lời không dựng được (P7): tín hiệu đang mở GIỮ nguyên, quy tắc vào not_run")
cai(ai_enabled=0)
xoa_run()
chay()
truoc = R("cn.dso_cao")
eq("(tiền đề) cn.dso_cao đang mở", truoc.status, "mo")
RD = registry.RULES["cn.dso_cao"]
_fn = RD.fn


def _ne(pack, cfg):
	raise ZeroDivisionError("quy tắc hỏng")


RD.fn = _ne
out = chay()
RD.fn = _fn
sau = R("cn.dso_cao")
eq("quy tắc ném lỗi: not_run[cn.dso_cao] = loi", out["not_run"].get("cn.dso_cao"), "loi")
eq("… tín hiệu cũ vẫn mở, lời giữ nguyên (không đóng như đã hết)", (sau.status, sau.title, sau.closed_on),
	("mo", truoc.title, None))
c("… dòng tổng ok, error kể cn.dso_cao", tong(out["run"]).status == "ok" and "cn.dso_cao" in (tong(out["run"]).error
	or ""), tong(out["run"]).error)


def _sai_kieu(pack, cfg):
	out = list(_fn(pack, cfg))
	for s in out:
		s.title = "{{cong-no.receivables.top_overdue[0].customer|tien}} trả chậm"    # chuỗi mà ghi |tien
	return out


RD.fn = _sai_kieu
out = chay()
RD.fn = _fn
sau = R("cn.dso_cao")
eq("lời quy tắc không dựng được (sai kiểu): not_run[cn.dso_cao] = loi-loi", out["not_run"].get("cn.dso_cao"), "loi-loi")
eq("… tín hiệu cũ vẫn mở, lời cũ giữ", (sau.status, sau.title, sau.closed_on), ("mo", truoc.title, None))
out = chay()
eq("quy tắc lành lại: chạy bình thường, vẫn mở", (out["not_run"].get("cn.dso_cao"), R("cn.dso_cao").status),
	(None, "mo"))
cai(ai_enabled=1)


# ═══════════════════════════════════════════════════════════════════════════
print("Q. Đợt sửa 2 qua lượt chạy thật: E5 lời quy tắc dùng lại nguyên văn, E7 mã của dòng bị cắt, E8 chủ đề bỏ qua ở")
print("   path bất kỳ, E1 số trong ngoặc nhọn, E2 đơn giá / khoá không xếp được, E6 tên NCC chỉ còn trong ảnh chụp sx")
from bc.ai import collect as _collect, redact as _redact, render as _render  # noqa: E402

# E5 — mô hình "dùng lại được" lời quy tắc: trả NGUYÊN loi_quy_tac (tiêu đề / chi tiết) của MỌI tín hiệu → 0 bị loại.
# Thêm tín hiệu hệ thống có lời số đếm: lỗi tăng vọt (ht.error_log), đăng nhập sai (ht.dang_nhap_sai).
for j in range(14):
	insert("Error Log", method="frappe.exceptions.ValidationError", error="Traceback", creation=D(2026, 10, 27, 9, 30 + j))
insert("User", name="kt.q@example.com", enabled=1, first_name="Kế Toán")
for k in range(12):
	insert("Activity Log", creation=D(2026, 10, 27, 8, k), modified=D(2026, 10, 27, 8, k), user="kt.q@example.com",
		operation="Login", status="Failed")
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE rule = 'ai'")
xoa_run()
GUI_E5 = []


def echo(obj):
	out = []
	for t in obj["tin_hieu"]:
		tt, _, bd = t["loi_quy_tac"].partition(" — ")
		GUI_E5.append((obj["nhom"], t["rule"]))
		out.append({"signal": t["id"], "severity": t["muc"], "priority": 3, "title": tt, "body": bd or tt, "advice": []})
	return {"data": {"insights": out}, "tokens_in": 1000, "tokens_out": 100, "model": "claude-sonnet-5-5"}


out = chay(**{n: echo for n in NHOM})
rr5 = {r.step: (r.insights_ai, r.rejected) for r in con(out["run"])}
c("E5 (tiền đề): echo đủ mọi nhóm có tín hiệu, có ht.error_log và ht.dang_nhap_sai", {"ht.error_log", "ht.dang_nhap_sai"}
	<= {r for _n, r in GUI_E5} and len(GUI_E5) >= 20, (len(GUI_E5), sorted({r for _n, r in GUI_E5})))
eq("E5: lời quy tắc trả lại nguyên văn → lượt chạy loại 0, nhận đúng số tín hiệu đã gửi", (out["rejected"],
	out["accepted"]), (0, len(GUI_E5)))
eq("E5: không dòng Run nào có lời bị loại", {k: v for k, v in rr5.items() if v[1]}, {})
eq("E5: không tín hiệu nào needs_check 1 (lời AI đã thay lời quy tắc)", [r.signal_key for r in frappe.db.sql(
	f"SELECT signal_key FROM `tab{INSIGHT}` WHERE needs_check = 1 AND status IN ('mo', 'dang-xu-ly')", as_dict=True)], [])

# Gói thêm (bọc collect.build, mọi bước khác thật):
# E7: tong-quan.top_customers có 8 + 40 = 48 dòng → đề bài giữ 30; khách "Bí Mật Số 35" nằm ở dòng bị cắt.
# E2: đơn giá sổ han-dung.overview.am.ds[*].rate (như seed Kho) + một lá không xếp được kiểu ton-kho.overview.zz_moi.
# E6: một dòng chuỗi MT không gán chuỗi → nhãn "Chưa gán chuỗi" (cn.py) — nhãn cố định, gửi nguyên.
for i in range(1, 41):
	insert("Customer", name=f"KH-DAI-{i:02d}", customer_name=f"Nhà phân phối Bí Mật Số {i:02d}")
_build = _collect.build
GIA_SO = {}


def build_q(today=None):
	pack = _build(today)
	rows = pack["tong-quan"]["top_customers"]["rows"]
	for i in range(1, 41):
		rows.append({"customer": f"Nhà phân phối Bí Mật Số {i:02d}", "customer_id": f"KH-DAI-{i:02d}",
			"amount": 1000000.0 * (50 - i)})
	ds = pack["han-dung"]["overview"].setdefault("am", {}).setdefault("ds", [])
	ds.append({"item_code": "HAN-NL", "qty": -5.0, "rate": 30000.0, "value_abs": 150000.0})
	GIA_SO["i"] = len(ds) - 1
	pack["ton-kho"]["overview"]["zz_moi"] = 7
	pack["cong-no"]["receivables"]["mt"]["chains"].append({"chain": "Chưa gán chuỗi", "amount": 5000000.0,
		"overdue": 0.0, "count": 1, "unknown_term": 0, "einv_pending": 0.0})
	GIA_SO["pack"] = pack
	return pack


# E6: NCC cát đổi tên SAU khi nhật ký cát (phần O) chép tên → tên cũ chỉ còn trong ảnh chụp sx (ten_ncc); thêm một
# phiếu đánh giá NCC chờ QC của NCC không có hồ sơ Supplier (tên chỉ có trong SX Danh Gia NCC.ten_ncc).
frappe.db.sql("UPDATE `tabSupplier` SET supplier_name = 'Công ty TNHH Cát Sạch Miền Bắc' WHERE name = 'NCC-CAT-01'")
insert("SX Danh Gia NCC", supplier="NCC-DG-01", ten_ncc="Xưởng Bao Bì Kín Tiếng", trang_thai="Chờ QC", ngay="2026-10-25",
	danh_gia_luc=D(2026, 10, 25, 9, 0), creation=D(2026, 10, 25, 9, 0))
# E8: chủ đề tỷ lệ nợ quá hạn bị bỏ qua hẳn (paths overdue_pct, overdue, receivable).
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"status": "bo-qua", "mute_until": None})
luu()
MA35 = _redact.build(True)._ma["Nhà phân phối Bí Mật Số 35"]
LAY = {}
KN = "cong-no.receivables.kpis."


def kd_q(obj):
	rows = obj["pack"]["tong-quan"]["top_customers"]["rows"]
	LAY["n_rows"] = len(rows)
	LAY["giu"] = rows[0]["customer"]
	# mã của dòng bị cắt trước (bị loại), mã của dòng giữ lại sau (cùng khoá tự do → nhận)
	return [ins(None, "Khách cần chăm sóc", "Khách " + MA35 + " cần chăm sóc thêm; khách lớn nhất đạt "
		"{{tong-quan.top_customers.rows[0].amount|tien}}.", priority=5),
		ins(None, "Khách lớn nhất", "Khách " + rows[0]["customer"] + " mua nhiều nhất: "
		"{{tong-quan.top_customers.rows[0].amount|tien}}.", priority=4)]


def tc_q(obj):
	return [
		# E8 a: path bỏ qua ở VỊ TRÍ THỨ HAI của thân
		ins(None, "Nợ ròng", "Trên tổng phải thu ròng {{" + KN + "net|tien}}, nợ quá hạn chiếm {{" + KN
			+ "overdue_pct|pct}}.", priority=5),
		# E8 b: path bỏ qua chỉ ở tiêu đề
		ins(None, "Nợ quá hạn {{" + KN + "overdue|tien}}", "Tiền ứng trước {{" + KN + "advances|tien}}.", priority=5),
		# E8 c: path bỏ qua chỉ ở lời khuyên
		ins(None, "Phải trả", "Tổng phải trả {{phai-tra.payables.ap.total|tien}}.",
			["Thu phải thu {{" + KN + "receivable|tien}} trước."], priority=5),
		# E8 e: path đầu lặp tín hiệu quy tắc đang mở (phải trả quá hạn) → bỏ lặng lẽ (không tính loại)
		ins(None, "Phải trả quá hạn", "Phải trả quá hạn {{phai-tra.payables.ap.due.overdue_total|tien}}.", priority=5),
		# E8 f: path đầu tự do, path SAU thuộc tín hiệu đang mở (không bỏ qua) → vẫn nhận (chỉ xét lặp ở path đầu)
		ins(None, "Chưa phân bổ", "Phải thu chưa phân bổ {{" + KN + "unallocated|tien}}, có {{" + KN
			+ "over_limit|so}} khách vượt hạn mức.", priority=2),
		# E8 d: đối chứng
		ins(None, "Quỹ", "Quỹ hiện có {{phai-tra.payables.cash.total|tien}}.", priority=1),
		# E1: số trong ngoặc nhọn — tự do và gắn tín hiệu
		ins(None, "Quỹ ngân hàng", "Quỹ ngân hàng {{phai-tra.payables.cash.bank|tien}}, còn <b 1.250.000 đ> chưa ghi.",
			severity="do", priority=5),
		ins(S(obj, "cn.dso_cao"), "Thu tiền chậm", "Còn <khoảng 350 triệu> chưa thu được."),
		ins(S(obj, "cn.vuot_han_muc"), "Vượt hạn mức", "Có {{" + KN + "over_limit|so}} khách vượt hạn mức."),
	]


def kho_q(obj):
	gp = "han-dung.overview.am.ds[" + str(GIA_SO["i"]) + "].rate"
	return [ins(None, "Đơn giá sổ", "Nguyên liệu HAN-NL có đơn giá sổ {{" + gp + "|pct}}.", priority=5),
		ins(None, "Đơn giá sổ", "Nguyên liệu HAN-NL có đơn giá sổ {{" + gp + "|tien}}.", priority=4),
		ins(None, "Chỉ số mới", "Chỉ số mới chiếm {{ton-kho.overview.zz_moi|pct}}.", priority=3),
		ins(None, "Chỉ số mới", "Chỉ số mới đạt {{ton-kho.overview.zz_moi|so}}.", priority=2)]


xoa_run()
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE rule = 'ai'")
luu()
_collect.build = build_q
try:
	out = chay(**{"kinh-doanh": tl(kd_q), "tai-chinh": tl(tc_q), "kho-sx": tl(kho_q)})
finally:
	_collect.build = _build
U = {g["nhom"]: g["user"] for g in GOI}
cc = {r.step: r for r in con(out["run"])}
TEXT_AI = [(r.signal_key, (r.title or "") + " " + (r.body or "") + " " + (r.advice or "")) for r in frappe.db.sql(
	f"SELECT signal_key, title, body, advice FROM `tab{INSIGHT}`", as_dict=True)]

# E7
c("E7 (tiền đề): gói có 48 khách lớn, đề bài kinh-doanh giữ 30; mã của 'Bí Mật Số 35' KHÔNG có trong đề bài",
	len(GIA_SO["pack"]["tong-quan"]["top_customers"]["rows"]) == 48 and LAY.get("n_rows") == 30
	and MA35.startswith("KH#") and MA35 not in U.get("kinh-doanh", ""), (LAY.get("n_rows"), MA35))
eq("E7: lời nêu mã của dòng bị cắt → loại (dòng kinh-doanh rejected 1), không thành tên thật",
	(cc["kinh-doanh"].rejected, [k for k, t in TEXT_AI if "Bí Mật Số 35" in t]), (1, []))
fk = R("ai:tong-quan.top_customers.rows.amount")
c("E7: lời nêu mã của dòng CÓ trong đề bài vẫn nhận và có tên thật (restrict không cắt quá tay)", fk is not None
	and fk.status == "mo" and LAY.get("giu", "").startswith("KH#") and "KH#" not in fk.body
	and "Khách cần chăm sóc" not in (fk.title or "") and "Bí Mật" not in fk.body, fk and (fk.title, fk.body))
frappe.session.user = "viewer@example.com"
vw = API.get_feed()["insights"]
eq("E7: người xem không thấy tên của dòng bị cắt", [i["title"] for i in vw if "Bí Mật Số 35" in i["title"] + i["body"]],
	[])

# E8
eq("E8: tự do có path bỏ qua ở vị trí 2 / tiêu đề / lời khuyên → không tạo", [R("ai:" + KN + "net"),
	R("ai:" + KN + "advances"), R("ai:phai-tra.payables.ap.total")], [None, None, None])
eq("E8: tự do lặp tín hiệu đang mở ở path đầu → không tạo (bỏ lặng lẽ)", R("ai:phai-tra.payables.ap.due.overdue_total"),
	None)
eq("E8: path SAU thuộc tín hiệu đang mở (không bỏ qua) và đối chứng → vẫn tạo", [(R(k) or {}).get("status") for k in
	("ai:" + KN + "unallocated", "ai:phai-tra.payables.cash.total")], ["mo", "mo"])
eq("E8+E1: dòng tai-chinh rejected 5 (3 bỏ qua + 2 ngoặc nhọn; lặp không tính), insights_ai 3",
	(cc["tai-chinh"].rejected, cc["tai-chinh"].insights_ai), (5, 3))
eq("E8: không lời AI nào mang số của chủ đề bỏ qua (54,5% / 120 triệu / 220 triệu)", [k for k, t in TEXT_AI
	if k.startswith("ai:") and any(x in t for x in ("54,5", "120 triệu", "220 triệu"))], [])
eq("E8: người xem không thấy thẻ tự do nào nói số bị bỏ qua", [i["title"] for i in vw if i["source"] == "ai"
	and any(x in i["title"] + i["body"] for x in ("54,5", "120 triệu", "220 triệu"))], [])

# E1
eq("E1: tự do có số trong ngoặc nhọn → không tạo", R("ai:phai-tra.payables.cash.bank"), None)
eq("E1: lời gắn tín hiệu có '<khoảng 350 triệu>' → loại (lời quy tắc, needs_check 1)", (R("cn.dso_cao").source,
	R("cn.dso_cao").needs_check), ("quy-tac", 1))
eq("E1: đối chứng — lời sạch của tín hiệu khác vẫn nhận", (R("cn.vuot_han_muc").source, R("cn.vuot_han_muc").needs_check),
	("ai", 0))
eq("E1: không chuỗi '350 triệu' / '1.250.000' nào được lưu", [k for k, t in TEXT_AI if "350 triệu" in t
	or "1.250.000" in t], [])

# E2
gp = "han-dung.overview.am.ds[" + str(GIA_SO["i"]) + "].rate"
_kieu = getattr(_render, "kieu_cua", lambda *a, **k: "chưa có kieu_cua")
c("E2 (tiền đề): kiểu của đơn giá sổ là tien; zz_moi không xếp được", _kieu(GIA_SO["pack"], gp) == "tien"
	and _kieu(GIA_SO["pack"], "ton-kho.overview.zz_moi") is None,
	(_kieu(GIA_SO["pack"], gp), _kieu(GIA_SO["pack"], "ton-kho.overview.zz_moi")))
fg, fz = R("ai:han-dung.overview.am.ds.rate"), R("ai:ton-kho.overview.zz_moi")
c("E2: đơn giá |pct loại, |tien nhận (lời lưu là bản |tien: '30.000 đ')", fg is not None and fg.status == "mo"
	and "30.000" in fg.body and "%" not in fg.body, fg and fg.body)
c("E2: khoá không xếp được |pct loại, |so nhận", fz is not None and fz.status == "mo" and "%" not in fz.body
	and "đạt" in fz.body, fz and fz.body)
eq("E2: dòng kho-sx rejected 2, insights_ai 2", (cc["kho-sx"].rejected, cc["kho-sx"].insights_ai), (2, 2))

# E6
SNAP = json.dumps(GIA_SO["pack"], ensure_ascii=False, default=str)
# (phiếu đánh giá NCC hiện không vào gói AI — mảng attp chỉ có các lĩnh vực ATTP; giữ "Kín Tiếng" để canh khi có)
c("E6 (tiền đề): gói THÔ có tên NCC cũ (ảnh chụp nhật ký cát), hồ sơ Supplier đã mang tên mới",
	"Cát Vàng Sông Hồng" in SNAP and frappe.db.sql("SELECT supplier_name FROM `tabSupplier` WHERE name = 'NCC-CAT-01'")
	[0][0] == "Công ty TNHH Cát Sạch Miền Bắc", "Cát Vàng Sông Hồng" in SNAP)
eq("E6: không đề bài nào có tên NCC cũ / mới / tên chỉ có trong phiếu đánh giá", [(n, x) for n, u in U.items()
	for x in ("Cát Vàng Sông Hồng", "Cát Sạch Miền Bắc", "Kín Tiếng") if x in u], [])
c("E6: câu ATTP vẫn mang mã NCC giả thay tên", bool(re.search(r"Nguồn:? NCC#\d+", U.get("attp", ""))),
	"Nguồn" in U.get("attp", ""))     # không in đề bài ra log
c("E6: nhãn cố định 'Chưa gán chuỗi' gửi nguyên; chuỗi thật (Saigon Co.op) vẫn mang mã", '"Chưa gán chuỗi"'
	in U.get("tai-chinh", "") and "Saigon Co.op" not in U.get("tai-chinh", ""), "Chưa gán chuỗi" in U.get("tai-chinh", ""))
frappe.db.set_value(INSIGHT, R("cn.qua_han_ty_le").name, {"status": "mo"})
luu()

# ═══════════════════════════════════════════════════════════════════════════
print("R. Vòng sửa 4 — H5: mã trong lời phải có NGUYÊN VĂN trong đề bài cuối đã gửi (pipeline truyền nguon = user)")
# Gói thêm một danh sách 40 dòng có mã (không phải tên khách / NCC: không bị che) → đề bài giữ 30 dòng đầu.
# MA-005 có trong đề bài; MA-035 ở dòng bị cắt; KH-0099 / AB12 bịa; SL-350 là mã dùng làm số lượng.
NGUON_R = {}
_ri_r = render.render_insight


def _ri_ghi(raw, pack, sections, mask=None, kinds=None, nguon=None):
	NGUON_R.setdefault("nguon", []).append(nguon)
	return _ri_r(raw, pack, sections, mask, kinds=kinds, nguon=nguon)


def build_r(today=None):
	pack = _build(today)
	pack["ton-kho"]["overview"]["zz_ma"] = [{"ma": f"MA-{i:03d}", "qty": i, "value": 1000.0 * i} for i in range(1, 41)]
	return pack


ZQ = "{{ton-kho.overview.zz_ma[4].qty|so}}"


def kho_r(obj):
	NGUON_R["n_rows"] = len(obj["pack"]["ton-kho"]["overview"]["zz_ma"])
	return [ins(None, "Mã có trong đề bài", "Mã MA-005 còn tồn " + ZQ + " đơn vị.", priority=5),
		ins(None, "Mã của dòng bị cắt", "Mã MA-035 còn tồn " + ZQ + " đơn vị.", priority=4),
		ins(None, "Mã bịa", "Khách KH-0099 và mã AB12 còn tồn " + ZQ + " đơn vị.", priority=3),
		ins(None, "Mã làm số lượng", "Tồn " + ZQ + " đơn vị, nằm ở SL-350 khách nhỏ.", priority=2)]


xoa_run()
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE rule = 'ai'")
luu()
_collect.build, render.render_insight = build_r, _ri_ghi
try:
	out = chay(**{"kho-sx": tl(kho_r)})
finally:
	_collect.build, render.render_insight = _build, _ri_r
U_R = {g["nhom"]: g["user"] for g in GOI}
cc = {r.step: r for r in con(out["run"])}
c("H5 (tiền đề): đề bài kho-sx giữ 30 / 40 dòng: có 'MA-005', không có 'MA-035', 'KH-0099', 'AB12', 'SL-350'",
	NGUON_R.get("n_rows") == 30 and "MA-005" in U_R.get("kho-sx", "") and not any(x in U_R.get("kho-sx", "") for x in
	("MA-035", "KH-0099", "AB12", "SL-350")), NGUON_R.get("n_rows"))
c("H5: pipeline truyền nguon = đúng chuỗi đề bài đã gửi ở mọi lần gọi render_insight", bool(NGUON_R.get("nguon"))
	and all(x == U_R.get("kho-sx") for x in NGUON_R["nguon"]), len(NGUON_R.get("nguon", [])))
fr = R("ai:ton-kho.overview.zz_ma.qty")
c("H5: mã CÓ trong đề bài được nhận (lưu nguyên 'MA-005')", fr is not None and fr.status == "mo"
	and fr.body == "Mã MA-005 còn tồn 5 đơn vị.", fr and fr.body)
eq("H5: mã của dòng bị cắt / mã bịa / mã dùng làm số lượng → loại (kho-sx rejected 3, insights_ai 1)",
	(cc["kho-sx"].rejected, cc["kho-sx"].insights_ai), (3, 1))
eq("H5: không lời nào lưu 'MA-035' / 'KH-0099' / 'AB12' / 'SL-350'", [r.signal_key for r in frappe.db.sql(
	f"SELECT signal_key, body FROM `tab{INSIGHT}`", as_dict=True) if any(x in (r.body or "") for x in ("MA-035", "KH-0099",
	"AB12", "SL-350"))], [])
eq("H5: sau lượt chạy, render không còn giữ đề bài trong bộ nhớ (pipeline gọi forget_source sau mỗi lượt gọi)",
	render._nguon.cache_info().currsize, 0)
eq("không một lần ra mạng (cả phần L–R)", MANG, [])

c.done()
