# -*- coding: utf-8 -*-
"""Route handler cho www page /bc — vỏ SPA Báo cáo Ban lãnh đạo.

Guest → /login. Đăng nhập nhưng không có BC Viewer/System Manager → trang
"Không có quyền" (không render shell, không lộ import map/context).
"""

from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe import _

from bc.api._common import has_access

no_cache = 1

# PHẢI khớp BUILD trong public/bc/shell.js (phát hiện shell cũ do cache CDN).
SHELL_BUILD = "bc-p3-r2"


def get_context(context):
	# Link/QR chia sẻ: /bc?k=<token> → bc.api.share.login (đăng nhập + nhớ thiết bị).
	token = frappe.form_dict.get("k")
	if token:
		frappe.local.flags.redirect_location = f"/api/method/bc.api.share.login?token={quote(str(token))}"
		raise frappe.Redirect
	if frappe.session.user == "Guest":
		# Thiết bị đã từng vào bằng link (cookie bc_key) → tự đăng nhập lại im lặng.
		has_key = bool(frappe.request and frappe.request.cookies.get("bc_key"))
		frappe.local.flags.redirect_location = (
			"/api/method/bc.api.share.login" if has_key else "/login?redirect-to=/bc")
		raise frappe.Redirect

	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.title = _("Báo cáo điều hành")
	if not has_access():
		context.no_access = True
		return context

	from bc.api.common import build_context_meta

	roles = set(frappe.get_roles())
	full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	bc_context = build_context_meta()
	bc_context.update(
		{
			"user": frappe.session.user,
			"fullName": full_name,
			"isSysManager": "System Manager" in roles,
			"assetVersion": frappe.utils.now().replace(" ", "T").replace(":", "-"),
			"csrfToken": frappe.sessions.get_csrf_token(),
			"shellBuild": SHELL_BUILD,
		}
	)
	context.no_access = False
	context.bc_context = bc_context
	context.shell_build = SHELL_BUILD
	return context
