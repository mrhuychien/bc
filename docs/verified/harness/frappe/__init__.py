"""Frappe giả TỐI GIẢN cho test bc.api.* — SQL chạy THẬT trên MariaDB (schema sinh từ DocType JSON v16).

Chỉ giả những gì bc dùng: db.sql/sql_list/escape/has_column/table_exists/exists/get_value/
get_single_value/set_value, get_all, get_cached_doc/get_single (BC Settings + bảng con), cache(),
session/get_roles, throw/whitelist/_dict. Hôm nay điều khiển bằng frappe.utils.FAKE_TODAY.
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import types

import pymysql
import pymysql.converters

from frappe import utils  # noqa: E402  (frappe.utils.*)


class _dict(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError:
			return None

	def __setattr__(self, k, v):
		self[k] = v

	def copy(self):
		return _dict(self)


class ValidationError(Exception):
	pass


class PermissionError(Exception):  # noqa: A001
	pass


class DoesNotExistError(ValidationError):
	pass


class Redirect(Exception):
	pass


def _(s, *a, **k):
	return s


def throw(msg, exc=ValidationError, title=None, **kw):
	raise exc(msg)


def whitelist(*a, **k):
	if a and callable(a[0]) and not k:
		return a[0]
	return lambda fn: fn


def log_error(*a, **k):
	LOGGED.append((a, k))


LOGGED: list = []


def clear_last_message():
	pass


def get_traceback(*a, **k):
	return ""


def generate_hash(*a, length=10, **k):
	import secrets
	return secrets.token_hex(length)[:length]


session = _dict(user="viewer@example.com")
ROLES = {"viewer@example.com": ["BC Viewer"], "Administrator": ["System Manager"]}
INSTALLED_APPS = ["frappe", "erpnext", "bc", "sx", "ketoan", "pkd", "npp", "salep", "vanchuyen", "ns"]
conf = _dict()
local = types.SimpleNamespace(flags=_dict(), response=_dict(), conf=conf)
form_dict = _dict()
request = None


def get_roles(user=None):
	return list(ROLES.get(user or session.user, []))


def get_installed_apps(*a, **k):
	return list(INSTALLED_APPS)


# ─── DB ────────────────────────────────────────────────────────────────────
class _DB:
	def __init__(self):
		self.conn = None
		self.queries: list[str] = []

	def connect(self, db=None):
		from paths import DB, SOCK
		self.conn = pymysql.connect(user="root", unix_socket=SOCK, charset="utf8mb4", database=db or DB, autocommit=True)

	def _cur(self):
		if not self.conn:
			self.connect()
		return self.conn.cursor()

	def sql(self, query, values=None, as_dict=False, as_list=False, pluck=False, debug=False, **kw):
		cur = self._cur()
		self.queries.append(query)
		# Frappe v16 chuyển values qua pymysql y hệt (pyformat %(k)s / %s; tuple → (a,b)).
		if values in (None, (), {}):
			cur.execute(query)
		else:
			cur.execute(query, values)
		rows = cur.fetchall() if cur.description else ()
		if pluck:
			return [r[0] for r in rows]
		if as_dict:
			cols = [d[0] for d in cur.description]
			return [_dict(zip(cols, r)) for r in rows]
		if as_list:
			return [list(r) for r in rows]
		return tuple(rows)

	def sql_list(self, query, values=None, **kw):
		return [r[0] for r in self.sql(query, values)]

	def escape(self, s, percent=True):
		s = pymysql.converters.escape_string(str(s))
		if percent:
			s = s.replace("%", "%%")
		return "'" + s + "'"

	def table_exists(self, doctype, cached=True):
		return bool(self.sql("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
			(f"tab{doctype}",)))

	def has_column(self, doctype, column):
		return bool(self.sql("""SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE()
			AND table_name = %s AND column_name = %s""", (f"tab{doctype}", column)))

	def get_table_columns(self, doctype):
		return [r[0] for r in self.sql("""SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE()
			AND table_name = %s ORDER BY ordinal_position""", (f"tab{doctype}",))]

	def _where(self, filters):
		conds, vals = [], []
		if isinstance(filters, str):
			return "`name` = %s", [filters]
		items = filters.items() if isinstance(filters, dict) else [(f[0], tuple(f[1:])) if len(f) == 3 else (f[1], tuple(f[2:])) for f in (filters or [])]
		for k, v in items:
			if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) and v[0].lower() in (
					"=", "!=", "in", "not in", "like", "not like", ">", "<", ">=", "<=", "is", "between"):
				op, val = v[0].lower(), v[1]
				if op in ("in", "not in"):
					val = tuple(val) or ("\x00",)
					conds.append(f"`{k}` {op} %s"); vals.append(val)
				elif op == "is":
					conds.append(f"IFNULL(`{k}`, '') {'!=' if val == 'set' else '='} ''")
				elif op == "between":
					conds.append(f"`{k}` BETWEEN %s AND %s"); vals += list(val)
				else:
					conds.append(f"`{k}` {op} %s"); vals.append(val)
			else:
				conds.append(f"`{k}` = %s"); vals.append(v)
		return (" AND ".join(conds) or "1=1"), vals

	def exists(self, doctype, filters=None, cache=False):
		if filters is None and isinstance(doctype, dict):
			filters = dict(doctype); doctype = filters.pop("doctype")
		if doctype == "DocType" and isinstance(filters, str):
			r = self.sql("SELECT name FROM `tabDocType` WHERE name = %s", (filters,))
			return r[0][0] if r else None
		if not self.table_exists(doctype):
			return None
		where, vals = self._where(filters if filters is not None else {})
		r = self.sql(f"SELECT name FROM `tab{doctype}` WHERE {where} LIMIT 1", vals)
		return r[0][0] if r else None

	def get_value(self, doctype, filters=None, fieldname="name", as_dict=False, **kw):
		if self._is_single(doctype):
			if isinstance(fieldname, (list, tuple)):
				d = _dict({f: self.get_single_value(doctype, f) for f in fieldname})
				return d if as_dict else tuple(d.values())
			return self.get_single_value(doctype, fieldname)
		where, vals = self._where(filters if filters is not None else {})
		fields = fieldname if isinstance(fieldname, (list, tuple)) else [fieldname]
		sel = ", ".join(f if "(" in f or " " in f else f"`{f}`" for f in fields)
		r = self.sql(f"SELECT {sel} FROM `tab{doctype}` WHERE {where} LIMIT 1", vals, as_dict=as_dict)
		if not r:
			return None
		if as_dict:
			return r[0]
		return r[0] if isinstance(fieldname, (list, tuple)) else r[0][0]

	def _is_single(self, doctype):
		r = self.sql("SELECT issingle FROM `tabDocType` WHERE name = %s", (doctype,))
		return bool(r and r[0][0])

	def get_single_value(self, doctype, field, cache=True):
		if not self._is_single(doctype):
			raise ValidationError(f"{doctype} is not a single")
		# Như v16 database.get_single_value: field không có trong meta → frappe.throw.
		from schema import doctype_files
		meta = doctype_files()[doctype][1]
		if field not in {f.get("fieldname") for f in meta.get("fields") or []} | {"name", "modified", "creation", "owner"}:
			throw(f"Field {field} does not exist on {doctype}")
		r = self.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s", (doctype, field))
		return r[0][0] if r else None

	def set_single_value(self, doctype, field, value):
		self.sql("DELETE FROM `tabSingles` WHERE doctype = %s AND field = %s", (doctype, field))
		self.sql("INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)", (doctype, field, value))

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		if isinstance(field, dict):
			for k, v in field.items():
				self.sql(f"UPDATE `tab{doctype}` SET `{k}` = %s WHERE name = %s", (v, name))
		else:
			self.sql(f"UPDATE `tab{doctype}` SET `{field}` = %s WHERE name = %s", (value, name))

	def delete(self, doctype, filters=None):
		where, vals = self._where(filters or {})
		self.sql(f"DELETE FROM `tab{doctype}` WHERE {where}", vals)

	def count(self, doctype, filters=None):
		where, vals = self._where(filters or {})
		return self.sql(f"SELECT COUNT(*) FROM `tab{doctype}` WHERE {where}", vals)[0][0]


db = _DB()


def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None, limit=None, limit_page_length=None,
		or_filters=None, group_by=None, **kw):
	where, vals = db._where(filters or {})
	if pluck:
		fields = [pluck]
	fields = fields or ["name"]
	sel = ", ".join(f if ("(" in f or " " in f or "`" in f or f == "*") else f"`{f}`" for f in fields)
	q = f"SELECT {sel} FROM `tab{doctype}` WHERE {where}"
	if group_by:
		q += f" GROUP BY {group_by}"
	if order_by:
		q += f" ORDER BY {order_by}"
	lim = limit or limit_page_length
	if lim:
		q += f" LIMIT {int(lim)}"
	rows = db.sql(q, vals, as_dict=True)
	if pluck:
		return [r[pluck] for r in rows]
	return rows


get_list = get_all


def _child_rows(parent_dt, parent_name, child_dt, parentfield=None):
	if not db.table_exists(child_dt):
		return []
	q = f"SELECT * FROM `tab{child_dt}` WHERE parent = %s AND parenttype = %s"
	vals = [parent_name, parent_dt]
	if parentfield:
		q += " AND parentfield = %s"; vals.append(parentfield)
	return db.sql(q + " ORDER BY idx", vals, as_dict=True)


def get_single(doctype):
	"""Single doc: giá trị từ tabSingles (ép kiểu theo meta JSON) + bảng con."""
	from schema import doctype_files  # harness
	f, meta = doctype_files()[doctype]
	d = _dict(doctype=doctype, name=doctype)
	for fld in meta.get("fields") or []:
		fn, ft = fld.get("fieldname"), fld.get("fieldtype")
		if not fn:
			continue
		if ft in ("Table", "Table MultiSelect"):
			d[fn] = _child_rows(doctype, doctype, fld["options"], fn)
			continue
		v = db.get_single_value(doctype, fn)
		if ft in ("Int", "Check"):
			v = int(float(v)) if v not in (None, "") else 0
		elif ft in ("Float", "Currency", "Percent"):
			v = float(v) if v not in (None, "") else 0.0
		d[fn] = v
	d.get = lambda k, default=None: dict.get(d, k, default)  # type: ignore
	return d


class _Meta:
	def __init__(self, doctype):
		from schema import doctype_files
		self.doctype = doctype
		self._cols = set(db.get_table_columns(doctype)) if not db._is_single(doctype) else set()
		f = doctype_files().get(doctype)
		self.fields = [_dict(x) for x in (f[1].get("fields") or [])] if f else []

	def has_field(self, fieldname):
		return fieldname in self._cols or any(x.fieldname == fieldname for x in self.fields)

	def get_field(self, fieldname):
		return next((x for x in self.fields if x.fieldname == fieldname), None)


def get_meta(doctype, cached=True):
	return _Meta(doctype)


def get_cached_doc(doctype, name=None):
	if name is None or name == doctype:
		return get_single(doctype)
	raise NotImplementedError


get_doc = get_cached_doc


# ─── Cache ─────────────────────────────────────────────────────────────────
class _Cache:
	def __init__(self):
		self.store = {}

	def get_value(self, key, *a, **k):
		return json.loads(self.store[key]) if key in self.store else None

	def set_value(self, key, value, expires_in_sec=None, **k):
		self.store[key] = json.dumps(value, default=str)

	def delete_keys(self, prefix):
		for k in list(self.store):
			if k.startswith(prefix):
				del self.store[k]

	def delete_value(self, key):
		self.store.pop(key, None)

	def hget(self, *a, **k):
		return None

	def hset(self, *a, **k):
		pass


_cache = _Cache()


def cache():
	return _cache
