"""Trợ lý AI — kiểm TĨNH (không DB, không chạy lượt nào): luật mà bộ thử chạy không nhìn thấy (đặc tả §6, §9, §14).

1. Mạng / khoá: MỌI file .py dưới bc/ (không riêng bc/ai) — chỉ bc/ai/llm/ được import requests / socket / http /
   urllib (trừ urllib.parse: chỉ xử lý chuỗi), nhắc tên khoá bc_ai_*key, đọc frappe.conf; ngoài llm/ chỉ các file
   trong DANH SÁCH CHO PHÉP đọc frappe.conf (cờ cấu hình không phải khoá).
2. collect.py chỉ import frappe, bc.api.*, thư viện chuẩn (không bc.ai.*: gói số chỉ lấy từ màn bc).
3. DocType JSON: mọi field ai_* của BC Settings (và mọi field từ ai_section trở xuống) permlevel 1; BC AI Insight /
   BC AI Run chỉ System Manager; Select đúng đặc tả §6.1–6.2 (và khớp hằng số của store).
4. bc/hooks.py: mọi chuỗi dạng "bc.x.y" (scheduler, after_install, after_migrate…) phân giải được thành hàm.
5. install.SEED_AI: che tên mặc định BẬT, trần 90 USD, 40 tín hiệu, tên model — khớp bc.ai mặc định.

Chạy: python3 -B test_ai_tinh.py   (BC_APP_ROOT=<bản sao> để soát một bản khác)
"""
import ast
import importlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import BC_ROOT  # noqa: E402

sys.path.insert(0, BC_ROOT)
import frappe  # noqa: E402,F401  (giả — chỉ để import module của bc)


class Check:
	def __init__(self):
		self.ok = self.bad = 0

	def __call__(self, label, cond, detail=""):
		if cond:
			self.ok += 1
			print(f"  ✓ {label}")
		else:
			self.bad += 1
			print(f"  ✗ {label}  {detail}")

	def done(self):
		print(f"\n{self.ok} đạt, {self.bad} trượt")
		sys.exit(1 if self.bad else 0)


c = Check()
PKG = os.path.join(BC_ROOT, "bc")


def rel(p):
	return os.path.relpath(p, PKG).replace(os.sep, "/")


def imports_of(tree):
	out = []
	for n in ast.walk(tree):
		if isinstance(n, ast.Import):
			out += [a.name for a in n.names]
		elif isinstance(n, ast.ImportFrom):
			out.append("." * n.level + (n.module or ""))
	return out


def strings_of(node):
	return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


FILES = sorted(os.path.join(d, f) for d, _s, fs in os.walk(PKG) if "__pycache__" not in d for f in fs
	if f.endswith(".py"))
TREES = {rel(p): ast.parse(open(p, encoding="utf-8").read()) for p in FILES}

# ═══════════════════════════════════════════════════════════════════════════
print("1. Mạng / khoá trên MỌI file .py dưới bc/")
c("soát đủ cây bc/ (api, ai, www, install, hooks, doctype)", len(TREES) >= 40 and {"api/ai.py", "api/vc.py",
	"ai/pipeline.py", "ai/llm/anthropic.py", "hooks.py", "install.py", "www/bc.py"} <= set(TREES), len(TREES))
LLM = {k for k in TREES if k.startswith("ai/llm/")}
NGOAI = {k: t for k, t in TREES.items() if k not in LLM}
CAM = ("requests", "socket", "http", "urllib", "urllib3", "httpx", "aiohttp", "ssl", "ftplib", "smtplib", "telnetlib",
	"subprocess", "xmlrpc", "websocket", "websockets")
DUOC_IMPORT = {"urllib.parse"}     # chỉ xử lý chuỗi URL, không ra mạng


def cam(m):
	return m.split(".")[0] in CAM and m not in DUOC_IMPORT


lo_net = [(k, m) for k, t in NGOAI.items() for m in imports_of(t) if cam(m)]
lo_net += [(k, ast.unparse(n)[:60]) for k, t in NGOAI.items() for n in ast.walk(t) if isinstance(n, ast.Call)
	and (getattr(n.func, "attr", "") or getattr(n.func, "id", "")) in ("__import__", "import_module")
	and n.args and isinstance(n.args[0], ast.Constant) and cam(str(n.args[0].value))]
c("ngoài bc/ai/llm/: không import requests / socket / http / urllib (trừ urllib.parse) / subprocess", not lo_net,
	lo_net)
c("luật mạng không rỗng nghĩa: bc/ai/llm/anthropic.py import requests",
	"requests" in imports_of(TREES.get("ai/llm/anthropic.py", ast.parse(""))))
c("luật mạng không rỗng nghĩa (P2): bc/ai/llm/openai.py import requests",
	"requests" in imports_of(TREES.get("ai/llm/openai.py", ast.parse(""))))
KHOA = re.compile(r"bc_ai_\w*key")
lo_khoa = [k for k, t in NGOAI.items() if any(KHOA.search(s) for s in strings_of(t))]
c("ngoài bc/ai/llm/: không chuỗi tên khoá bc_ai_*key", not lo_khoa, lo_khoa)
c("luật tên khoá không rỗng nghĩa: llm/ có nhắc bc_ai_anthropic_key", any(KHOA.search(s) for k in LLM
	for s in strings_of(TREES[k])))
# Đọc site config: frappe.conf / frappe.get_conf / frappe.get_site_config / frappe.local.conf.
CONF_ALLOW = {"api/ns.py": {"ns_tinh_lai_salaryday"}}   # cờ cấu hình nghiệp vụ, không phải khoá


def conf_reads(t):
	"""[(tên khoá đọc | None khi không xác định, đoạn code)] của mọi lần chạm site config."""
	out = []
	for n in ast.walk(t):
		ten = None
		if isinstance(n, ast.Attribute) and n.attr in ("conf", "get_conf", "get_site_config"):
			v = n.value
			if (isinstance(v, ast.Name) and v.id == "frappe") or (isinstance(v, ast.Attribute) and v.attr == "local"):
				ten = n
		elif isinstance(n, ast.Name) and n.id in ("get_site_config", "get_conf"):
			ten = n
		if ten is not None:
			out.append(ten)
	return out


def khoa_doc(t, node):
	"""Tên khoá của frappe.conf.get("x") / frappe.conf["x"] / frappe.conf.x quanh node (None nếu không rõ)."""
	for n in ast.walk(t):
		if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.value is node and n.args \
				and isinstance(n.args[0], ast.Constant):
			return str(n.args[0].value)
		if isinstance(n, ast.Subscript) and n.value is node and isinstance(n.slice, ast.Constant):
			return str(n.slice.value)
		if isinstance(n, ast.Attribute) and n.value is node and n.attr not in ("get",):
			return n.attr
	return None


lo_conf = []
for k, t in NGOAI.items():
	for node in conf_reads(t):
		ten = khoa_doc(t, node)
		if ten is None or ten not in CONF_ALLOW.get(k, set()):
			lo_conf.append((k, ten, ast.unparse(node)))
c("ngoài bc/ai/llm/: chỉ đọc frappe.conf theo danh sách cho phép (api/ns.py: ns_tinh_lai_salaryday)", not lo_conf,
	lo_conf)
c("danh sách cho phép còn đúng (mỗi mục vẫn được đọc — xoá mục cũ khi code đổi)", all(
	{khoa_doc(TREES[k], n) for n in conf_reads(TREES[k])} >= v for k, v in CONF_ALLOW.items() if k in TREES), CONF_ALLOW)
# Biến cấp module giữ khoá / config: không gán frappe.conf… ở cấp module (kể cả llm/: khoá đọc lúc gọi, không cache).
lo_mod = [(k, ast.unparse(n)[:60]) for k, t in TREES.items() for n in t.body if isinstance(n, (ast.Assign,
	ast.AnnAssign)) and any(conf_reads(n))]
c("không file nào giữ site config vào biến cấp module", not lo_mod, lo_mod)

# ═══════════════════════════════════════════════════════════════════════════
print("2. collect.py: import chỉ frappe / bc.api.* / thư viện chuẩn")
imp = imports_of(TREES["ai/collect.py"])
bad = [m for m in imp if m.startswith(".") or not (m.split(".")[0] == "frappe" or m == "bc.api"
	or m.startswith("bc.api.") or m.split(".")[0] in sys.stdlib_module_names)]
c("collect.py: không import bc.ai.* / module ngoài / import tương đối", not bad, bad)
c("collect.py: có import frappe (luật không rỗng nghĩa)", "frappe" in imp, imp)
dyn = [ast.unparse(n)[:80] for n in ast.walk(TREES["ai/collect.py"]) if isinstance(n, ast.Call)
	and getattr(n.func, "attr", "") == "import_module"]
c("collect.py: import động chỉ dưới bc.api.", dyn and all("bc.api." in d for d in dyn), dyn)

# ═══════════════════════════════════════════════════════════════════════════
print("3. DocType JSON")
DT = os.path.join(PKG, "bc", "doctype")


def dt(name):
	return json.load(open(os.path.join(DT, name, name + ".json"), encoding="utf-8"))


st = dt("bc_settings")
fs = st["fields"]
names = [f["fieldname"] for f in fs]
ai = [f for f in fs if f["fieldname"].startswith("ai_") or f["fieldname"] in ("column_break_ai",)]
c("BC Settings có đủ ô AI (≥ 16 mục ai_*)", len(ai) >= 16 and "ai_section" in names, len(ai))
lo_pl = [f["fieldname"] for f in ai if f.get("permlevel") != 1]
c("BC Settings: mọi field ai_* permlevel 1 (người xem đọc BC Settings ở permlevel 0)", not lo_pl, lo_pl)
sau = fs[names.index("ai_section"):] if "ai_section" in names else []
lo_sau = [f["fieldname"] for f in sau if f.get("permlevel") != 1]
c("BC Settings: mọi field từ ai_section trở xuống permlevel 1", sau and not lo_sau, lo_sau)
c("BC Settings: field_order khớp fields", st.get("field_order") == names)
pl1 = [p for p in st.get("permissions", []) if p.get("permlevel") == 1]
c("BC Settings permlevel 1: chỉ System Manager đọc / ghi", [p.get("role") for p in pl1 if p.get("read")
	or p.get("write")] == ["System Manager"], pl1)
for name, label in (("bc_ai_insight", "BC AI Insight"), ("bc_ai_run", "BC AI Run"), ("bc_ai_brief", "BC AI Brief")):
	d = dt(name)
	roles = sorted({p.get("role") for p in d.get("permissions", [])})
	c(f"{label}: DocPerm chỉ System Manager", roles == ["System Manager"], d.get("permissions"))
	c(f"{label}: không cho quyền theo owner / share / chia sẻ ra ngoài", not any(p.get(x) for p in d.get("permissions", [])
		for x in ("if_owner", "share", "export", "report", "print", "email")), d.get("permissions"))
	c(f"{label}: autoname hash, không istable / issingle", (d.get("autoname"), bool(d.get("istable")),
		bool(d.get("issingle"))) == ("hash", False, False), (d.get("autoname"), d.get("istable"), d.get("issingle")))


def sel(d):
	return {f["fieldname"]: (f.get("options") or "").split("\n") for f in d["fields"] if f["fieldtype"] == "Select"}


from bc.ai import registry, store  # noqa: E402

si, sr = sel(dt("bc_ai_insight")), sel(dt("bc_ai_run"))
c("Insight.status = mo / dang-xu-ly / bo-qua / dong", si.get("status") == ["mo", "dang-xu-ly", "bo-qua", "dong"],
	si.get("status"))
c("Insight.severity = do / vang (= registry.SEVERITIES)", si.get("severity") == ["do", "vang"]
	and tuple(si["severity"]) == registry.SEVERITIES, si.get("severity"))
c("Insight.audience = lanh-dao / quan-tri (= registry.AUDIENCES)", si.get("audience") == ["lanh-dao", "quan-tri"]
	and tuple(si["audience"]) == registry.AUDIENCES, si.get("audience"))
c("Insight.source = quy-tac / ai", si.get("source") == ["quy-tac", "ai"], si.get("source"))
c("Insight.review_verdict = (trống) / dong-y / nghi-ngo", si.get("review_verdict") == ["", "dong-y", "nghi-ngo"],
	si.get("review_verdict"))
c("Run.run_type = ngay / tuan / tay / hoi-dap / thang (= store.RUN_TYPES)", sr.get("run_type") == ["ngay", "tuan", "tay",
	"hoi-dap", "thang"] and tuple(sr["run_type"]) == store.RUN_TYPES, sr.get("run_type"))
c("Run.status = ok / loi / het-credit / vuot-tran / tat / khong-khoa (= store.RUN_STATUSES)", sr.get("status") == [
	"ok", "loi", "het-credit", "vuot-tran", "tat", "khong-khoa"] and tuple(sr["status"]) == store.RUN_STATUSES,
	sr.get("status"))
c("Insight: signal_key unique + reqd", any(f["fieldname"] == "signal_key" and f.get("unique") and f.get("reqd")
	for f in dt("bc_ai_insight")["fields"]))

# ═══════════════════════════════════════════════════════════════════════════
print("4. bc/hooks.py: mọi đường dẫn hàm phân giải được")
hooks = TREES["hooks.py"]
DUONG = re.compile(r"^bc(\.[A-Za-z_][A-Za-z0-9_]*)+$")
dds = sorted({s for s in strings_of(hooks) if DUONG.match(s)})
c("hooks.py có đường dẫn để soát (after_install, after_migrate, cron 5:30)", {"bc.install.after_install",
	"bc.install.after_migrate", "bc.ai.jobs.daily"} <= set(dds), dds)


def giai(dotted):
	mod, fn = dotted.rsplit(".", 1)
	try:
		return callable(getattr(importlib.import_module(mod), fn, None))
	except Exception as e:  # noqa: BLE001
		return f"{type(e).__name__}: {e}"


lo_hook = [(d, giai(d)) for d in dds if giai(d) is not True]
c("mọi đường dẫn bc.* trong hooks.py là hàm có thật", not lo_hook, lo_hook)
ns = {}
exec(compile(open(os.path.join(PKG, "hooks.py"), encoding="utf-8").read().replace("from . import __version__ as "
	"app_version", "app_version = ''"), "hooks.py", "exec"), ns)
c("scheduler 5:30 hằng ngày gọi bc.ai.jobs.daily", "bc.ai.jobs.daily" in (ns.get("scheduler_events", {})
	.get("cron", {}).get("30 5 * * *") or []), ns.get("scheduler_events"))
_cron = ns.get("scheduler_events", {}).get("cron", {})
c("P2: thứ Hai 06:00 gọi bc.ai.jobs.weekly, 07:00 ngày 2 gọi bc.ai.jobs.monthly", "bc.ai.jobs.weekly" in (_cron.get(
	"0 6 * * 1") or []) and "bc.ai.jobs.monthly" in (_cron.get("0 7 2 * *") or []), _cron)

# ═══════════════════════════════════════════════════════════════════════════
print("5. install.SEED_AI — mặc định khi cài / migrate")
from bc import ai as bc_ai, install  # noqa: E402

S = install.SEED_AI
c("ai_mask_parties = 1 (che tên khách / NCC mặc định BẬT)", S.get("ai_mask_parties") == 1, S.get("ai_mask_parties"))
c("trần chi: ai_cap_claude_usd = ai_cap_openai_usd = 90", (S.get("ai_cap_claude_usd"), S.get("ai_cap_openai_usd"))
	== (90, 90), S)
c("ai_max_signals = 40 (= bc.ai.DEFAULT_MAX_SIGNALS)", S.get("ai_max_signals") == 40 == bc_ai.DEFAULT_MAX_SIGNALS, S)
c("model: claude-sonnet-5-5 hằng ngày (= bc.ai.DEFAULT_CLAUDE_MODEL), claude-opus-5-5 phân tích sâu",
	(S.get("ai_claude_model"), S.get("ai_claude_model_deep")) == ("claude-sonnet-5-5", "claude-opus-5-5")
	and S.get("ai_claude_model") == bc_ai.DEFAULT_CLAUDE_MODEL, S)
c("ngày chốt kỳ = 1", (S.get("ai_cycle_day_claude"), S.get("ai_cycle_day_openai")) == (1, 1), S)
c("ai_openai_model mặc định trống (phản biện OpenAI tắt tới khi quản trị đặt model)", not S.get("ai_openai_model"), S)
c("ai_enabled KHÔNG có trong SEED_AI (cài xong AI vẫn tắt tới khi quản trị bật)", "ai_enabled" not in S, S)
c("mọi khoá SEED_AI là field có thật của BC Settings", set(S) <= set(names), set(S) - set(names))
c("giá khởi tạo có cho model mặc định", set(install.SEED_AI_PRICES) >= {S.get("ai_claude_model"),
	S.get("ai_claude_model_deep")}, install.SEED_AI_PRICES)
src = ast.unparse(next(n for n in TREES["install.py"].body if isinstance(n, ast.FunctionDef)
	and n.name == "seed_settings"))
c("seed_settings dùng SEED_AI và chỉ điền ô chưa từng lưu (_chua_luu)", "SEED_AI" in src and "_chua_luu" in src)

# ═══════════════════════════════════════════════════════════════════════════
print("6. Detector chỉ SELECT, quy tắc không SQL (mọi file dưới bc/ai/detectors, bc/ai/rules — kể cả P2)")
_CAM = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|REPLACE|TRUNCATE|CREATE|GRANT)\b", re.I)
_GHI = {"set_value", "delete", "insert", "commit", "save", "db_set", "set_single_value", "rollback"}
for thu_muc, la_rule in (("detectors", False), ("rules", True)):
	for f in sorted(os.listdir(os.path.join(BC_ROOT, "bc", "ai", thu_muc))):
		if not f.endswith(".py") or f == "__init__.py":
			continue
		tree = ast.parse(open(os.path.join(BC_ROOT, "bc", "ai", thu_muc, f), encoding="utf-8").read())
		doc = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
			and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
		chuoi = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
			and id(n) not in doc] + [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
		sql = [x for x in chuoi if re.search(r"\bSELECT\b|\bFROM\s+`tab", x)]
		ghi = sorted({n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in _GHI})
		if la_rule:
			c(f"rules/{f}: không SQL, không frappe.db (quy tắc thuần)", not sql and not any(isinstance(n, ast.Attribute)
				and n.attr == "db" for n in ast.walk(tree)) and not ghi, (sql[:2], ghi))
		else:
			c(f"detectors/{f}: SQL chỉ SELECT, không NOW() / CURDATE(), không gọi ghi DB", not [x for x in sql
				if _CAM.search(x) or re.search(r"NOW\(|CURDATE|SYSDATE|CURRENT_(DATE|TIME)", x, re.I)] and not ghi,
				([x[:50] for x in sql if _CAM.search(x)], ghi))

c.done()
