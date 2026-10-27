"""Sinh schema MariaDB từ DocType JSON thật (ERPNext v16 + Frappe core + các app tuỳ biến).

Cách dùng (python3 schema.py) → tạo DB `bc_test` sạch: mọi bảng `tab<DocType>` có đúng cột như
Frappe v16 tạo (bảng loại kiểu theo frappe/database/mariadb), cộng Custom Field từ fixtures các app.
Đọc thêm custom field khai bằng code (install.py) qua EXTRA_CUSTOM_FIELDS.
"""
from __future__ import annotations

import functools
import glob
import json
import os
import sys

import pymysql

from paths import APPS, DB, HERE as SCRATCH, SOCK, SRC

TYPE_MAP = {
	"Currency": "decimal(21,9)", "Int": "int(11)", "Long Int": "bigint(20)", "Float": "decimal(21,9)",
	"Percent": "decimal(21,9)", "Check": "int(1)", "Small Text": "text", "Long Text": "longtext",
	"Code": "longtext", "Text Editor": "longtext", "Markdown Editor": "longtext", "HTML Editor": "longtext",
	"Date": "date", "Datetime": "datetime(6)", "Time": "time(6)", "Text": "text", "Data": "varchar(140)",
	"Link": "varchar(140)", "Dynamic Link": "varchar(140)", "Password": "text", "Select": "varchar(140)",
	"Read Only": "varchar(140)", "Attach": "text", "Attach Image": "text", "Signature": "longtext",
	"Color": "varchar(140)", "Barcode": "longtext", "Geolocation": "longtext", "Duration": "decimal(21,9)",
	"Icon": "varchar(140)", "Phone": "varchar(140)", "Autocomplete": "varchar(140)", "JSON": "json",
	"Rating": "decimal(3,2)",
}
NUMERIC = {"Currency", "Int", "Long Int", "Float", "Percent", "Check", "Duration", "Rating"}


@functools.lru_cache(maxsize=None)
def doctype_files():
	pats = [
		f"{SRC}/erpnext/erpnext/*/doctype/*/*.json",
		f"{SRC}/frappe/frappe/*/doctype/*/*.json",
		f"{APPS}/*/*/*/doctype/*/*.json",      # bc/bc/bc/doctype, ketoan/ketoan/<module>/doctype …
		f"{APPS}/*/*/*/*/doctype/*/*.json",
	]
	seen = {}
	for p in pats:
		for f in glob.glob(p):
			if "/node_modules/" in f:
				continue
			base = os.path.basename(os.path.dirname(f))
			if os.path.basename(f) != base + ".json":
				continue
			try:
				d = json.load(open(f))
			except Exception:
				continue
			if not isinstance(d, dict) or d.get("doctype") != "DocType" or not d.get("name"):
				continue
			seen.setdefault(d["name"], (f, d))
	# DocType chỉ có trên site (tạo tay trên Desk, không nằm trong repo nào) — vd SalaryDay: khai trong
	# site_doctypes.json theo đúng dạng DocType JSON, kèm nguồn suy ra fieldtype.
	extra = os.path.join(SCRATCH, "site_doctypes.json")
	if os.path.exists(extra):
		for d in json.load(open(extra)):
			seen.setdefault(d["name"], (extra, d))
	return seen


def custom_fields():
	out = []
	for f in glob.glob(f"{APPS}/*/*/fixtures/custom_field.json"):
		try:
			for cf in json.load(open(f)):
				out.append(cf)
		except Exception:
			pass
	for name in ("extra_custom_fields.json", "site_custom_fields.json"):  # install.py (sinh) + chỉ có trên site (viết tay)
		extra = os.path.join(SCRATCH, name)
		if os.path.exists(extra):
			out += json.load(open(extra))
	return out


def col(fieldname, fieldtype):
	t = TYPE_MAP.get(fieldtype)
	if not t:
		return None
	if fieldtype in NUMERIC:
		return f"`{fieldname}` {t} NOT NULL DEFAULT 0"
	return f"`{fieldname}` {t} DEFAULT NULL"


def ddl(name, d, extra_fields):
	cols = {
		"name": "`name` varchar(140) NOT NULL",
		"creation": "`creation` datetime(6) DEFAULT NULL",
		"modified": "`modified` datetime(6) DEFAULT NULL",
		"modified_by": "`modified_by` varchar(140) DEFAULT NULL",
		"owner": "`owner` varchar(140) DEFAULT NULL",
		"docstatus": "`docstatus` int(1) NOT NULL DEFAULT 0",
		"idx": "`idx` int(8) NOT NULL DEFAULT 0",
	}
	if d.get("istable"):
		for c in ("parent", "parentfield", "parenttype"):
			cols[c] = f"`{c}` varchar(140) DEFAULT NULL"
	else:
		for c in ("_user_tags", "_comments", "_assign", "_liked_by"):
			cols[c] = f"`{c}` text DEFAULT NULL"
	if d.get("is_tree"):
		for c in ("lft", "rgt"):
			cols[c] = f"`{c}` int(11) NOT NULL DEFAULT 0"
		cols["old_parent"] = "`old_parent` varchar(140) DEFAULT NULL"
	for f in list(d.get("fields") or []) + extra_fields:
		fn, ft = f.get("fieldname"), f.get("fieldtype")
		if not fn or fn in cols:
			continue
		c = col(fn, ft)
		if c:
			cols[fn] = c
	body = ",\n  ".join(list(cols.values()) + ["PRIMARY KEY (`name`)"])
	return f"CREATE TABLE `tab{name}` (\n  {body}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"


def build(db=DB, only=None):
	docs = doctype_files()
	cfs = custom_fields()
	by_dt = {}
	for cf in cfs:
		by_dt.setdefault(cf.get("dt"), []).append(cf)
	conn = pymysql.connect(user="root", unix_socket=SOCK, charset="utf8mb4", autocommit=True)
	cur = conn.cursor()
	cur.execute(f"DROP DATABASE IF EXISTS `{db}`")
	cur.execute(f"CREATE DATABASE `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
	cur.execute(f"USE `{db}`")
	cur.execute("CREATE TABLE `tabSingles` (`doctype` varchar(140), `field` varchar(140), `value` longtext, "
		"KEY (`doctype`, `field`)) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
	made, singles = [], []
	for name, (f, d) in sorted(docs.items()):
		if only and name not in only:
			continue
		if d.get("issingle"):
			singles.append(name)
			continue
		if d.get("is_virtual"):
			continue
		if name == "DocType":
			continue
		try:
			cur.execute(ddl(name, d, by_dt.get(name, [])))
			made.append(name)
		except Exception as e:  # noqa
			print("skip", name, e, file=sys.stderr)
	# Bảng DocType tối giản — frappe.db.exists("DocType", X) chỉ cần name/issingle/istable/module.
	cur.execute("CREATE TABLE `tabDocType` (`name` varchar(140) PRIMARY KEY, `module` varchar(140), "
		"`issingle` int(1) NOT NULL DEFAULT 0, `istable` int(1) NOT NULL DEFAULT 0, `custom` int(1) NOT NULL DEFAULT 0) "
		"DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
	for name, (f, d) in docs.items():
		cur.execute("INSERT INTO `tabDocType` VALUES (%s,%s,%s,%s,0)",
			(name, d.get("module"), int(bool(d.get("issingle"))), int(bool(d.get("istable")))))
	conn.close()
	return made, singles


def doctype_app(name):
	f, _ = doctype_files()[name]
	return f


if __name__ == "__main__":
	made, singles = build()
	print(f"{len(made)} tables, {len(singles)} singles in {DB}")
