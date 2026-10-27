"""Ẩn / hiện mảng báo cáo: bc.api.sections (chỉ quản trị) + _guard("<mảng>") ở MỌI method báo cáo.

Kiểm tĩnh (AST): mọi method @frappe.whitelist của bc.api gọi _guard đúng mảng ở dòng đầu — method mới quên khai
mảng thì đỏ. Kiểm động trên MariaDB: ẩn từng mảng → người xem gọi method của mảng đó bị chặn, quản trị vẫn qua,
mảng khác không bị ảnh hưởng; cache dùng chung không lách được; dữ liệu lưu rác vẫn đọc an toàn.
"""
import ast
import glob
import importlib
import os
import re

from seed import Check, bc_settings, reset, single
from paths import BC_ROOT

import frappe  # noqa: E402

VIEWER, ADMIN = "viewer@example.com", "Administrator"
# method → mảng (route bỏ "/"). Đổi bảng này phải là quyết định có chủ ý.
EXPECTED = {
	"live.get_snapshot": "thoi-gian-thuc",
	"kd.get_summary": "tong-quan", "kd.get_channels": "tong-quan", "kd.get_item_groups": "tong-quan",
	"kd.get_top_customers": "tong-quan", "kd.get_daily": "ngay", "kd.get_orders": "ngay", "kd.get_monthly": "thang",
	"kd.get_provinces": "tinh-thanh", "kd.get_top_products": "san-pham",
	"tet.get_npp_growth": "tet", "tet.get_npp_detail": "tet", "tet.get_mt_detail": "tet", "tet.get_items": "tet",
	"sx.get_items": "sx-tet", "sx.get_daily_summary": "sx-tet", "sx.get_daily_detail": "sx-tet",
	"cn.get_receivables": "cong-no", "cn.get_payables": "phai-tra",
	"attp.get_overview": "attp", "attp.get_report": "attp",
	"vc.get_overview": "van-chuyen", "ns.get_overview": "nhan-su",
}
KHONG_MANG = {"common.get_context_meta", "sections.get_hidden", "sections.set_hidden", "hidden.list_hidden",
	"hidden.search_items", "hidden.hide_item", "hidden.unhide_item", "share.list_leaders", "share.create_leader",
	"share.grant_existing", "share.issue_link", "share.revoke_link", "share.set_enabled", "share.login", "share.logout"}


def whitelisted():
	"""{'mod.fn': first_statement_node} cho mọi hàm @frappe.whitelist trong bc/api."""
	out = {}
	for path in sorted(glob.glob(os.path.join(BC_ROOT, "bc", "api", "*.py"))):
		mod = os.path.basename(path)[:-3]
		for node in ast.parse(open(path, encoding="utf-8").read()).body:
			if not isinstance(node, ast.FunctionDef):
				continue
			if not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
				continue
			body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
			out[f"{mod}.{node.name}"] = body[0] if body else None
	return out


def guard_section(stmt):
	"""'tong-quan' nếu câu đầu là _guard("tong-quan"); '' nếu _guard(); None nếu không phải _guard."""
	if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and getattr(stmt.value.func, "id", "") == "_guard"):
		return None
	a = stmt.value.args
	return a[0].value if a and isinstance(a[0], ast.Constant) else ""


def call(dotted, user):
	mod, fn = dotted.split(".")
	frappe.session.user = user
	try:
		getattr(importlib.import_module(f"bc.api.{mod}"), fn)(refresh=1)
		return None
	except frappe.PermissionError as e:
		return f"PermissionError: {e}"
	except Exception as e:  # noqa: BLE001 — lỗi dữ liệu trống không liên quan việc chặn
		return f"other: {type(e).__name__}"
	finally:
		frappe.session.user = VIEWER


def an(keys):
	frappe.session.user = ADMIN
	try:
		from bc.api import sections
		return sections.set_hidden(keys, 1)["hidden"]
	finally:
		frappe.session.user = VIEWER


def hien_het():
	frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'BC Settings' AND field = 'hidden_sections'")


if __name__ == "__main__":
	c = Check()
	reset(); bc_settings()
	from bc.api import _common, common, sections

	# ── Tĩnh: mọi method báo cáo khai đúng mảng ──
	wl = whitelisted()
	report = {k: guard_section(v) for k, v in wl.items() if k not in KHONG_MANG}
	c("mọi method báo cáo gọi _guard(\"<mảng>\") ở dòng đầu, đúng mảng", report == EXPECTED,
		{k: v for k, v in report.items() if EXPECTED.get(k) != v} or set(EXPECTED) - set(report))
	c("method ngoài mảng chỉ là quản trị / dùng chung (không sót method báo cáo)", set(wl) - set(EXPECTED) == KHONG_MANG,
		set(wl) - set(EXPECTED) ^ KHONG_MANG)
	c("mọi mảng đều có method; không mảng thừa", set(EXPECTED.values()) == set(_common.SECTIONS))
	nav = re.findall(r"route: '/([a-z-]+)'", open(os.path.join(BC_ROOT, "bc/public/bc/lib/nav.js"), encoding="utf-8").read())
	c("lib/nav.js (menu) khớp SECTIONS, đúng thứ tự", nav == list(_common.SECTIONS), nav)
	shell = open(os.path.join(BC_ROOT, "bc/public/bc/shell.js"), encoding="utf-8").read()
	views = re.findall(r"'/([a-z-]+)': \(\) => import\(withV\('\./views/", shell.split("const IS_ADMIN")[0])
	c("shell.js ALL_VIEWS = đúng các mảng", sorted(views) == sorted(_common.SECTIONS), views)

	# ── Mặc định + quyền quản lý ──
	c("mặc định không ẩn gì", _common.hidden_sections() == set() and common.build_context_meta()["hiddenSections"] == [])
	for fn, args in ((sections.get_hidden, ()), (sections.set_hidden, ("cong-no", 1))):
		try:
			fn(*args)
			c(f"người xem không gọi được {fn.__name__}", False)
		except frappe.PermissionError:
			c(f"người xem không gọi được {fn.__name__}", True)
	c("người xem gọi cũng không đổi gì", _common.hidden_sections() == set())

	frappe.session.user = ADMIN
	r1 = sections.set_hidden("cong-no", 1)["hidden"]
	r2 = sections.set_hidden('["attp", "nhan-su"]', "1")["hidden"]
	r3 = sections.set_hidden(["attp"], 1)["hidden"]
	c("quản trị ẩn một / nhiều mảng, lặp lại không đổi, lưu theo thứ tự menu", (r1, r2, r3) == (
		["cong-no"], ["cong-no", "nhan-su", "attp"], ["cong-no", "nhan-su", "attp"]), (r1, r2, r3))
	raw = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype='BC Settings' AND field='hidden_sections'")[0][0]
	c("lưu ở BC Settings.hidden_sections, mỗi dòng một mã", raw == "cong-no\nnhan-su\nattp", repr(raw))
	c("xoá cache doc BC Settings sau khi lưu", ("BC Settings", "BC Settings") in frappe.DOC_CACHE_CLEARED)
	g = sections.get_hidden()
	c("get_hidden: mọi mảng + đang ẩn", g == {"sections": list(_common.SECTIONS), "hidden": ["cong-no", "nhan-su", "attp"]}, g)
	for bad in ("khong-co", '["cong-no", "rac"]', "[sai json", "[]", ""):
		try:
			sections.set_hidden(bad, 1)
			c(f"mã không hợp lệ bị từ chối ({bad!r})", False)
		except frappe.ValidationError:
			c(f"mã không hợp lệ bị từ chối ({bad!r})", True)
	c("mã sai không làm đổi danh sách", _common.hidden_sections() == {"cong-no", "nhan-su", "attp"})
	c("hiện lại một mảng", sections.set_hidden("nhan-su", 0)["hidden"] == ["cong-no", "attp"])
	c("ngữ cảnh trang có danh sách ẩn mới", common.build_context_meta()["hiddenSections"] == ["cong-no", "attp"])
	frappe.session.user = VIEWER

	# ── Động: ẩn từng mảng → đúng method của mảng đó bị chặn với người xem ──
	hien_het()
	sai = []
	for dotted, key in EXPECTED.items():
		hien_het(); an(key)
		v = call(dotted, VIEWER)
		if not (v and v.startswith("PermissionError") and "quản trị ẩn" in v):
			sai.append((dotted, "người xem không bị chặn", v))
		a = call(dotted, ADMIN)
		if a and a.startswith("PermissionError"):
			sai.append((dotted, "quản trị bị chặn", a))
		for other, k2 in EXPECTED.items():
			if k2 != key:
				o = call(other, VIEWER)
				if o and o.startswith("PermissionError"):
					sai.append((other, f"bị chặn khi chỉ ẩn {key}", o))
				break  # một method mảng khác là đủ mỗi vòng (vòng sau quay sang mảng khác)
	c(f"ẩn từng mảng: người xem bị chặn đúng method của mảng đó ({len(EXPECTED)} method), quản trị vẫn xem", not sai, sai)
	hien_het()
	bi_chan = [d for d in EXPECTED if (call(d, VIEWER) or "").startswith("PermissionError")]
	c("không ẩn gì: người xem gọi được mọi method", not bi_chan, bi_chan)

	# ── Cache dùng chung không lách được ──
	single("BC Settings", cache_ttl=300)
	frappe.cache().store.clear()
	v0 = call("cn.get_receivables", VIEWER)  # refresh=1: tính và ghi cache
	c("người xem xem Phải thu (đã vào cache)", not (v0 or "").startswith("Perm"), v0)
	an("cong-no")
	from bc.api import cn
	try:
		cn.get_receivables()  # không refresh → nếu guard nằm sau cache sẽ trả bản cache
		c("ẩn rồi thì bản cache cũng không trả cho người xem", False)
	except frappe.PermissionError:
		c("ẩn rồi thì bản cache cũng không trả cho người xem", True)
	single("BC Settings", cache_ttl=0)
	hien_het()

	# ── Dữ liệu lưu tay / rác ──
	frappe.db.set_single_value("BC Settings", "hidden_sections", " cong-no , rác\r\nnhan-su\n\nCONG-NO\n")
	c("giá trị lưu tay có khoảng trắng, dấu phẩy, mã lạ → chỉ lấy mã hợp lệ", _common.hidden_sections() == {"cong-no", "nhan-su"},
		_common.hidden_sections())
	hien_het()
	try:
		_common._guard("khong-co-mang")
		c("_guard với mảng không tồn tại là lỗi lập trình", False)
	except ValueError:
		c("_guard với mảng không tồn tại là lỗi lập trình", True)

	# ── Sửa trên Desk: controller BC Settings kiểm mã ──
	from bc.bc.doctype.bc_settings.bc_settings import BCSettings
	d = BCSettings({"tet_dates": [], "hidden_sections": "nhan-su, cong-no\ncong-no"})
	d.validate()
	c("Desk: chuẩn hoá về mỗi dòng một mã, đúng thứ tự, không trùng", d.hidden_sections == "cong-no\nnhan-su", repr(d.hidden_sections))
	try:
		BCSettings({"tet_dates": [], "hidden_sections": "cong-no\nkhong-co"}).validate()
		c("Desk: mã sai bị từ chối", False)
	except frappe.ValidationError:
		c("Desk: mã sai bị từ chối", True)
	c.done()
