# -*- coding: utf-8 -*-
"""Lưu SQL gốc của 15 Query Report vào docs/report-sql/ để port 1:1 và review.

    bench --site a.rongvanghoanggia.com execute bc.scripts.dump_report_sql.run

Chỉ ĐỌC tabReport (report cũ giữ nguyên trong DB, không xoá/sửa). In bảng các biểu
thức CURDATE()/NOW()/ngày Tết literal để điền docs/tet-curdate-audit.md.
"""

from __future__ import annotations

import os
import re

import frappe

REPORTS = {
	"Dashboard KD Tong Quan": "kd.get_summary",
	"Dashboard KD Kenh Ban": "kd.get_channels",
	"Dashboard KD Thang": "kd.get_monthly",
	"Dashboard KD Ngay": "kd.get_daily",
	"Dashboard KD Don Hang": "kd.get_orders",
	"Dashboard KD Tinh Thanh": "kd.get_provinces",
	"Dashboard KD Nganh Hang": "kd.get_item_groups",
	"Dashboard KD Top KH": "kd.get_top_customers",
	"Dashboard KD Top SP": "kd.get_top_products",
	"Tet NPP Tang Truong": "tet.get_npp_growth",
	"Tet NPP Hang Tet": "tet.get_npp_detail",
	"Tet Sieu thi MT": "tet.get_mt_detail",
	"Tet Ma Hang": "tet.get_items",
	"Quản lý sản xuất Hàng Tết": "sx.get_items",
	"Sản lượng sản xuất theo ngày": "sx.get_daily_summary / sx.get_daily_detail",
}

DATE_EXPR = re.compile(r"(CURDATE\(\)|NOW\(\)|SYSDATE\(\)|'\d{4}-\d{2}-\d{2}'|Hàng T{1,2}ết)", re.I)


def _slug(name: str) -> str:
	return frappe.scrub(name).replace("/", "_")


def run(out_dir: str | None = None):
	out_dir = out_dir or os.path.abspath(frappe.get_app_path("bc", "..", "docs", "report-sql"))
	os.makedirs(out_dir, exist_ok=True)
	audit = []
	for name, method in REPORTS.items():
		row = frappe.db.get_value("Report", name, ["report_type", "query", "ref_doctype", "modified"], as_dict=True)
		if not row:
			print(f"!! Không có report: {name}")
			continue
		path = os.path.join(out_dir, f"{_slug(name)}.sql")
		with open(path, "w", encoding="utf-8") as f:
			f.write(f"-- Report: {name}\n-- Type: {row.report_type} · ref: {row.ref_doctype} · modified: {row.modified}\n")
			f.write(f"-- Port sang: bc.api.{method}\n\n{row.query or ''}\n")
		for i, line in enumerate((row.query or "").splitlines(), 1):
			for m in DATE_EXPR.finditer(line):
				audit.append((name, i, m.group(0), line.strip()))
		print(f"OK  {name} → {path}")
	if audit:
		print("\n| report | dòng | biểu thức | ngữ cảnh |\n|---|---|---|---|")
		for name, i, expr, ctx in audit:
			print(f"| {name} | {i} | `{expr}` | `{ctx[:120]}` |")
	return out_dir
