# -*- coding: utf-8 -*-
"""bc.api.sections — ẩn / hiện mảng báo cáo với người xem (CHỈ System Manager).

Mảng = một màn của /bc (SECTIONS trong _common). Mảng bị ẩn: người xem (BC Viewer) không thấy trong menu,
gõ thẳng đường dẫn bị đưa về trang đầu, và MÁY CHỦ chặn mọi method của mảng đó (_guard("<mảng>")) — ẩn thật,
không chỉ giấu nút. Quản trị vẫn thấy hết (menu đánh dấu "đang ẩn") để kiểm tra trước khi mở lại.
Lưu ở BC Settings.hidden_sections (permlevel 1, mỗi dòng một mã) — sửa được cả trên Desk; mỗi lần đổi ghi
Version vào dòng thời gian BC Settings (ai ẩn / mở mảng nào, lúc nào).
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from bc.api._common import HIDDEN_SECTIONS_FIELD, SECTIONS, hidden_sections, is_admin, parse_sections

DT = "BC Settings"


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


def _an(hidden) -> bool:
	"""1 / 0 / true / false (SPA gửi 1/0; frappe.call từ Desk gửi 'true'/'false'; Python True/False). Giá trị
	khác → lỗi, KHÔNG đoán (cint('true') = 0 sẽ mở mảng trong khi người gọi muốn ẩn)."""
	v = str(hidden).strip().lower()
	if v not in ("0", "1", "true", "false"):
		frappe.throw(_("Giá trị ẩn / hiện không hợp lệ (0 hoặc 1)."))
	return v in ("1", "true")


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
	# Site chưa migrate field: lưu được vào tabSingles nhưng lần lưu BC Settings trên Desk kế tiếp (update_single
	# chỉ ghi lại field trong meta) sẽ xoá mất → người xem thấy lại mảng mà không ai mở. Bắt migrate trước.
	if not frappe.get_meta(DT).has_field(HIDDEN_SECTIONS_FIELD):
		frappe.throw(_("Chưa chạy bench migrate cho BC Settings — chưa ẩn / hiện được mảng báo cáo."))
	keys, an = _keys(sections), _an(hidden)
	# Đọc CÓ KHOÁ (SELECT … FOR UPDATE mọi dòng BC Settings): hai quản trị / hai tab / một lần lưu Desk cùng lúc
	# thì chờ nhau — không lần ghi nào đè mất lần kia (đọc thường + DELETE/INSERT của set_single_value thì mất).
	cu = parse_sections(frappe.db.get_singles_dict(DT, for_update=True).get(HIDDEN_SECTIONS_FIELD))
	moi = (set(cu) | set(keys)) if an else (set(cu) - set(keys))
	value = "\n".join(k for k in SECTIONS if k in moi)
	if value != "\n".join(cu):
		frappe.db.set_single_value(DT, HIDDEN_SECTIONS_FIELD, value)  # v16: tự xoá cache doc BC Settings
		# set_single_value bỏ qua ORM (không Version dù BC Settings track_changes) → tự ghi để biết ai ẩn / mở.
		frappe.get_doc({
			"doctype": "Version", "ref_doctype": DT, "docname": DT,
			"data": json.dumps({"added": [], "removed": [], "row_changed": [],
				"changed": [[HIDDEN_SECTIONS_FIELD, "\n".join(cu), value]]}, ensure_ascii=False),
		}).insert(ignore_permissions=True)
	return {"hidden": parse_sections(value)}
