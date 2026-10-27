"""Helper nạp dữ liệu thử vào bc_test (bảng thật v16)."""
from __future__ import annotations

import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import BC_ROOT, SOCK, app  # noqa: E402

sys.path.insert(0, BC_ROOT)
for _a in ("sx", "ketoan", "pkd"):  # helper app khác bc gọi thật (đọc mềm)
	sys.path.insert(1, app(_a))

try:  # Không có MariaDB / pymysql → BỎ QUA, không kết luận gì (không đỏ giả)
	import pymysql  # noqa: E402
	pymysql.connect(user="root", unix_socket=SOCK).close()
except Exception as _e:  # noqa: BLE001
	print(f"BỎ QUA: cần MariaDB (socket {SOCK}) + pymysql — {_e}")
	sys.exit(0)

import frappe  # noqa: E402  (fake)
import schema  # noqa: E402

_seq = itertools.count(1)


def reset(only=None):
	schema.build(only=only)
	frappe.db.conn = None
	frappe.cache().store.clear()
	frappe.local.__dict__.pop("sx_nho", None)  # nhớ-theo-request của sx (items_tp…): site thật hết request là mất


def insert(doctype, name=None, **fields):
	name = name or f"{doctype[:4].upper().replace(' ', '')}-{next(_seq):05d}"
	fields = {"name": name, **fields}
	cols = ", ".join(f"`{k}`" for k in fields)
	ph = ", ".join(["%s"] * len(fields))
	frappe.db.sql(f"INSERT INTO `tab{doctype}` ({cols}) VALUES ({ph})", list(fields.values()))
	return name


def single(doctype, **fields):
	for k, v in fields.items():
		frappe.db.set_single_value(doctype, k, v)


def child(parent_dt, parent, child_dt, parentfield, rows):
	for i, r in enumerate(rows, 1):
		insert(child_dt, parent=parent, parenttype=parent_dt, parentfield=parentfield, idx=i, **r)


def drop_doctype(name):
	frappe.db.sql(f"DROP TABLE IF EXISTS `tab{name}`")
	frappe.db.sql("DELETE FROM `tabDocType` WHERE name = %s", (name,))


def drop_column(doctype, col):
	frappe.db.sql(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{col}`")


def bc_settings(**over):
	base = dict(fy_start_month=5, cache_ttl=0, tet_item_group="Hàng Tết", traditional_item_group="Hàng truyền thống",
		tet_target_pct=20, tet_season_start_month=11, tet_compare_mode="calendar", sx_warehouse="Thành phẩm - HGC",
		sx_season_start_month=8, sx_season_end_month=2)
	base.update(over)
	single("BC Settings", **{k: v for k, v in base.items() if v is not None})
	child("BC Settings", "BC Settings", "BC Tet Date", "tet_dates", [
		{"year": 2025, "tet_date": "2025-01-29"}, {"year": 2026, "tet_date": "2026-02-17"},
		{"year": 2027, "tet_date": "2027-02-06"}])


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
