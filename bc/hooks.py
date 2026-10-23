# -*- coding: utf-8 -*-
"""Frappe hooks for bc — Báo cáo điều hành cho Ban lãnh đạo RVHG."""

from . import __version__ as app_version  # noqa: F401

app_name = "bc"
app_title = "BC Ban lãnh đạo"
app_publisher = "Hoang Giang JSC"
app_description = "Báo cáo điều hành cho Ban lãnh đạo RVHG (chỉ đọc)"
app_email = "chien@1nguoi.com"
app_license = "MIT"

# Assets của SPA nạp riêng trong www/bc.html (import map) — không nhồi vào desk/web.
app_include_css = []
app_include_js = []
web_include_css = []
web_include_js = []

# Fixtures: chỉ Role "BC Viewer". Quyền BC Settings nằm trong DocPerm chuẩn của
# DocType JSON (System Manager đọc/ghi, BC Viewer đọc) — không Custom DocPerm.
fixtures = [
	{"doctype": "Role", "filters": [["name", "in", ["BC Viewer"]]]},
]

# Seed mặc định BC Settings (ngày Tết, nhóm hàng) — idempotent, không làm chết install.
after_install = "bc.install.after_install"
