# -*- coding: utf-8 -*-
"""bc.api.share — Chia sẻ báo cáo cho lãnh đạo: tài khoản xem + link/QR tự đăng nhập.

Luồng:
1. System Manager tạo tài khoản lãnh đạo (Website User + role BC Viewer — chặn Desk từ
   tầng auth) và cấp link. Link = {site}/bc?k=<token 48 ký tự>; QR mã hoá đúng link này.
2. Lãnh đạo quét QR / bấm link → login(token) → đăng nhập + đặt cookie "bc_key" 400 ngày
   (httponly). Phiên Frappe hết hạn (session_expiry) → vào /bc, www/bc.py thấy cookie →
   login() đăng nhập lại im lặng ⇒ "giữ trạng thái đăng nhập".
3. Thu hồi: xoá dòng link (token hết hiệu lực, thiết bị đó bị đăng xuất). Khoá tài khoản:
   tắt User → mọi link vô hiệu.

An toàn: chỉ lưu sha256(token) (BC Settings.share_links, permlevel 1 — BC Viewer không
đọc được); token gốc chỉ trả về 1 lần lúc cấp. Không bao giờ tự đăng nhập tài khoản có
System Manager / Administrator. login() giới hạn 30 lần/phút/IP.
"""

from __future__ import annotations

import datetime
import hashlib
import re
import secrets
import unicodedata
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_url, now_datetime

LINK_DT = "BC Share Link"
PARENT = "BC Settings"
VIEW_ROLE = "BC Viewer"
COOKIE = "bc_key"
COOKIE_DAYS = 400
_PW_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
_SYNTH_DOMAIN = "bc.local"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{40,64}$")


# ─── Quyền ──────────────────────────────────────────────────────────────────
def _admin_guard():
	"""Chỉ System Manager quản lý chia sẻ. Gọi ở DÒNG ĐẦU mọi method quản trị."""
	if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
		frappe.throw(_("Chỉ quản trị (System Manager) được chia sẻ báo cáo."), frappe.PermissionError)


def _is_leader(user: str | None) -> bool:
	"""Tài khoản được phép tự đăng nhập bằng link: có BC Viewer, KHÔNG phải quản trị."""
	if not user or user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles(user))
	return VIEW_ROLE in roles and "System Manager" not in roles


def _hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def _link_url(token: str) -> str:
	return get_url(f"/bc?k={token}")


# ─── Cấp / thu hồi link ─────────────────────────────────────────────────────
def _issue(user: str, label: str | None = None) -> dict:
	token = frappe.generate_hash(length=48)
	idx = cint(frappe.db.sql("SELECT MAX(idx) FROM `tabBC Share Link` WHERE parent=%s", PARENT)[0][0]) + 1
	row = frappe.get_doc({
		"doctype": LINK_DT,
		"name": frappe.generate_hash(length=12),
		"parent": PARENT,
		"parenttype": PARENT,
		"parentfield": "share_links",
		"idx": idx,
		"user": user,
		"label": (label or "").strip()[:140] or None,
		"enabled": 1,
		"token_hash": _hash(token),
		"created_on": now_datetime(),
		"login_count": 0,
	})
	# Ghi thẳng dòng con, KHÔNG save cả BC Settings (save sẽ xoá cache báo cáo).
	row.db_insert()
	return {"link": row.name, "url": _link_url(token), "user": user, "label": row.label}


@frappe.whitelist()
def list_leaders():
	"""Tài khoản lãnh đạo (có BC Viewer) + các link đã cấp (không bao giờ trả token)."""
	_admin_guard()
	users = frappe.db.sql(
		"""SELECT u.name AS user, u.full_name, u.mobile_no, u.enabled, u.user_type, u.last_active
		   FROM `tabUser` u
		   WHERE u.name NOT IN ('Administrator', 'Guest')
		     AND EXISTS (SELECT 1 FROM `tabHas Role` r WHERE r.parent = u.name AND r.parenttype = 'User'
		                 AND r.role = %(role)s)
		   ORDER BY u.enabled DESC, u.full_name""",
		{"role": VIEW_ROLE},
		as_dict=True,
	)
	links = frappe.get_all(LINK_DT, filters={"parent": PARENT, "parenttype": PARENT},
		fields=["name", "user", "label", "enabled", "created_on", "last_login", "login_count"],
		order_by="created_on desc")
	by_user: dict = {}
	for lk in links:
		by_user.setdefault(lk.user, []).append({
			"link": lk.name, "label": lk.label, "enabled": cint(lk.enabled),
			"created_on": str(lk.created_on or "")[:16], "last_login": str(lk.last_login or "")[:16] or None,
			"login_count": cint(lk.login_count),
		})
	out = []
	for u in users:
		out.append({
			"user": u.user, "full_name": u.full_name or u.user, "mobile_no": u.mobile_no,
			"enabled": cint(u.enabled), "is_admin": not _is_leader(u.user),
			"last_active": str(u.last_active or "")[:16] or None,
			"links": by_user.get(u.user, []),
		})
	return {"leaders": out}


def _norm_mobile(mobile: str | None) -> str | None:
	m = re.sub(r"[\s.\-()]+", "", mobile or "")
	if not m:
		return None
	if m.startswith("+84"):
		m = "0" + m[3:]
	elif m.startswith("84") and len(m) >= 10:
		m = "0" + m[2:]
	if not re.match(r"^0\d{9,10}$", m):
		frappe.throw(_("Số điện thoại không hợp lệ: {0}").format(mobile))
	return m


def _slug(name: str) -> str:
	s = unicodedata.normalize("NFD", name.lower())
	s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
	return re.sub(r"[^a-z0-9]+", ".", s).strip(".") or "lanhdao"


@frappe.whitelist()
def create_leader(full_name, mobile=None, email=None, label=None):
	"""Tạo tài khoản CHỈ XEM cho lãnh đạo (Website User + BC Viewer) và cấp link/QR đầu tiên.

	Không cần mật khẩu: lãnh đạo vào bằng link/QR. Mật khẩu ngẫu nhiên vẫn được đặt
	(không trả về) vì User bắt buộc có; quên link → quản trị cấp link mới.
	"""
	_admin_guard()
	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Thiếu họ tên"))
	mobile = _norm_mobile(mobile)
	if mobile and frappe.db.exists("User", {"mobile_no": mobile}):
		frappe.throw(_("Số điện thoại đã có tài khoản: {0}").format(mobile))
	email = (email or "").strip().lower()
	if email:
		if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
			frappe.throw(_("Email không hợp lệ: {0}").format(email))
	else:
		base = mobile or _slug(full_name)
		email, n = f"{base}@{_SYNTH_DOMAIN}", 1
		while frappe.db.exists("User", email):
			n += 1
			email = f"{base}{n}@{_SYNTH_DOMAIN}"
	if frappe.db.exists("User", email):
		frappe.throw(_("Email đã có tài khoản: {0} — dùng nút \"Thêm user có sẵn\".").format(email))

	doc = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": full_name,
		"mobile_no": mobile,
		"user_type": "Website User",  # không có Desk — chặn từ tầng auth
		"enabled": 1,
		"send_welcome_email": 0,
		"new_password": "".join(secrets.choice(_PW_ALPHABET) for _ in range(16)),
		"roles": [{"role": VIEW_ROLE}],
	})
	doc.flags.no_welcome_mail = True
	doc.insert(ignore_permissions=True)  # sau _admin_guard
	return {"full_name": doc.full_name, **_issue(email, label)}


@frappe.whitelist()
def grant_existing(user, label=None):
	"""Cho 1 user CÓ SẴN quyền xem báo cáo (thêm BC Viewer) + cấp link.

	Tài khoản quản trị (System Manager) vẫn được thêm quyền xem nhưng KHÔNG cấp link tự
	đăng nhập (link bị lộ = lộ quyền quản trị) — họ đăng nhập bằng mật khẩu như thường.
	"""
	_admin_guard()
	if not frappe.db.exists("User", user) or user in ("Administrator", "Guest"):
		frappe.throw(_("Không tìm thấy user: {0}").format(user))
	if VIEW_ROLE not in frappe.get_roles(user):
		u = frappe.get_doc("User", user)
		u.append("roles", {"role": VIEW_ROLE})
		u.save(ignore_permissions=True)
	if not _is_leader(user):
		return {"user": user, "url": None, "message": _("Đã cấp quyền xem. Tài khoản quản trị không được cấp link tự đăng nhập.")}
	return _issue(user, label)


@frappe.whitelist()
def issue_link(user, label=None):
	"""Cấp thêm 1 link/QR cho lãnh đạo (vd thiết bị khác, hoặc lỡ mất link cũ)."""
	_admin_guard()
	if not _is_leader(user):
		frappe.throw(_("Chỉ cấp link cho tài khoản lãnh đạo (có BC Viewer, không phải quản trị)."))
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(_("Tài khoản đang bị khoá."))
	return _issue(user, label)


@frappe.whitelist()
def revoke_link(link):
	"""Thu hồi 1 link: xoá token + đăng xuất các phiên của tài khoản đó.

	Thiết bị dùng link khác của cùng người sẽ tự đăng nhập lại bằng cookie của nó.
	"""
	_admin_guard()
	user = frappe.db.get_value(LINK_DT, {"name": link, "parent": PARENT}, "user")
	if not user:
		frappe.throw(_("Không tìm thấy link"))
	frappe.db.delete(LINK_DT, {"name": link, "parent": PARENT})
	from frappe.sessions import clear_sessions

	clear_sessions(user, force=True)
	return {"ok": True}


@frappe.whitelist()
def set_enabled(user, enabled):
	"""Khoá / mở tài khoản lãnh đạo. Khoá = mọi link vô hiệu + đăng xuất ngay."""
	_admin_guard()
	if not _is_leader(user):
		frappe.throw(_("Chỉ áp dụng cho tài khoản lãnh đạo."))
	enabled = 1 if cint(enabled) else 0
	frappe.db.set_value("User", user, "enabled", enabled)
	if not enabled:
		from frappe.sessions import clear_sessions

		clear_sessions(user, force=True)
	return {"user": user, "enabled": enabled}


# ─── Đăng nhập bằng link (guest) ────────────────────────────────────────────
def _find_link(token: str):
	if not token or not _TOKEN_RE.match(token):
		return None
	row = frappe.db.get_value(LINK_DT, {"token_hash": _hash(token), "parent": PARENT},
		["name", "user", "enabled"], as_dict=True)
	if not row or not cint(row.enabled):
		return None
	if not frappe.db.get_value("User", row.user, "enabled") or not _is_leader(row.user):
		return None
	return row


def _redirect(location: str):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = location


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=30, seconds=60, methods=["GET"])
def login(token=None):
	"""Đích của link/QR (và của lần tự đăng nhập lại bằng cookie bc_key).

	Hợp lệ → đăng nhập + gia hạn cookie bc_key 400 ngày → /bc. Không hợp lệ (thu hồi,
	khoá, sai) → xoá cookie → trang đăng nhập thường.
	"""
	from_cookie = not token
	token = str(token or unquote(frappe.request.cookies.get(COOKIE, "") if frappe.request else ""))
	row = _find_link(token)
	if not row:
		frappe.local.cookie_manager.delete_cookie(COOKIE)
		_redirect("/login?redirect-to=%2Fbc" + ("" if from_cookie else "&bc_link=invalid"))
		return
	if frappe.session.user != row.user:
		frappe.local.login_manager.login_as(row.user)
	frappe.local.cookie_manager.set_cookie(
		COOKIE, token, max_age=COOKIE_DAYS * 86400,
		expires=datetime.datetime.now() + datetime.timedelta(days=COOKIE_DAYS), httponly=True)
	frappe.db.sql(
		"""UPDATE `tabBC Share Link` SET last_login = %s, login_count = IFNULL(login_count, 0) + 1
		   WHERE name = %s""", (now_datetime(), row.name))
	frappe.local.flags.commit = True  # GET không tự commit
	_redirect("/bc")


@frappe.whitelist(methods=["GET", "POST"])
def logout():
	"""Đăng xuất HẲN trên thiết bị này: xoá cookie bc_key (không tự đăng nhập lại) + đăng xuất."""
	frappe.local.cookie_manager.delete_cookie(COOKIE)
	frappe.local.login_manager.logout()
	frappe.local.flags.commit = True
	_redirect("/login?redirect-to=%2Fbc")
