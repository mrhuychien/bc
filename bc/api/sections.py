# -*- coding: utf-8 -*-
"""bc.api.sections — ẩn / hiện mảng báo cáo với người xem (CHỈ System Manager).

Mảng = một màn của /bc (SECTIONS trong _common). Mảng bị ẩn: người xem (BC Viewer) không thấy trong menu,
gõ thẳng đường dẫn bị đưa về trang đầu, và MÁY CHỦ chặn mọi method của mảng đó (_guard("<mảng>")) — ẩn thật,
không chỉ giấu nút. Quản trị vẫn thấy hết (menu đánh dấu "đang ẩn") để kiểm tra trước khi mở lại.
Lưu ở BC Settings.hidden_sections (permlevel 1, mỗi dòng một mã) — sửa được cả trên Desk.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from bc.api._common import HIDDEN_SECTIONS_FIELD, SECTIONS, hidden_sections, is_admin, parse_sections


def _admin_guard():
	"""Chỉ System Manager. Gọi ở DÒNG ĐẦU mọi method."""
	if not is_admin():
		frappe.throw(_("Chỉ quản trị (System Manager) được ẩn / hiện mảng báo cáo."), frappe.PermissionError)


def _keys(sections) -> list[str]:
	"""'cong-no' | '["cong-no","phai-tra"]' | list → list mã; mã lạ → ValidationError (không lưu nhầm)."""
	if isinstance(sections, str):
		s = sections.strip()
		try:
			sections = json.loads(s) if s.startswith("[") else [s]
		except ValueError:
			frappe.throw(_("Danh sách mảng báo cáo không đọc được."))
	keys = [str(x).strip() for x in (sections or [])]
	bad = [k for k in keys if k not in SECTIONS]
	if bad or not keys:
		frappe.throw(_("Mảng báo cáo không hợp lệ: {0}").format(", ".join(bad) or "—"))
	return keys


def _save(hidden: set[str]) -> list[str]:
	value = "\n".join(k for k in SECTIONS if k in hidden)
	frappe.db.set_single_value("BC Settings", HIDDEN_SECTIONS_FIELD, value)
	if hasattr(frappe, "clear_document_cache"):  # get_cached_doc / form Desk thấy giá trị mới
		frappe.clear_document_cache("BC Settings", "BC Settings")
	return parse_sections(value)


@frappe.whitelist()
def get_hidden():
	"""{sections: mọi mã máy chủ biết (đúng thứ tự menu), hidden: mã đang ẩn}."""
	_admin_guard()
	h = hidden_sections()
	return {"sections": list(SECTIONS), "hidden": [k for k in SECTIONS if k in h]}


@frappe.whitelist(methods=["POST"])
def set_hidden(sections, hidden=1):
	"""Ẩn (hidden=1) hoặc hiện lại (hidden=0) một hay nhiều mảng — idempotent. Trả danh sách đang ẩn mới."""
	_admin_guard()
	keys = _keys(sections)
	cur = hidden_sections()
	if cint(hidden):
		cur |= set(keys)
	else:
		cur -= set(keys)
	return {"hidden": _save(cur)}
