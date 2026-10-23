# -*- coding: utf-8 -*-
"""BC Settings — cấu hình trung tâm (năm TC, nhóm hàng, ngày Tết, cache). Single."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class BCSettings(Document):
	def validate(self):
		for field in ("fy_start_month", "tet_season_start_month", "sx_season_end_month"):
			v = self.get(field)
			if v and not 1 <= int(v) <= 12:
				frappe.throw(_("{0} phải trong khoảng 1–12.").format(self.meta.get_label(field)))
		if self.cache_ttl is not None and int(self.cache_ttl) < 0:
			frappe.throw(_("Thời gian cache không được âm."))
		years = [int(r.year) for r in self.tet_dates]
		if len(years) != len(set(years)):
			frappe.throw(_("Mỗi năm chỉ khai báo một ngày Tết."))
		for r in self.tet_dates:
			if frappe.utils.getdate(r.tet_date).year != int(r.year):
				frappe.throw(_("Ngày Tết {0} không thuộc năm {1}.").format(r.tet_date, r.year))
		if self.sx_default_from and self.sx_default_to and self.sx_default_from > self.sx_default_to:
			frappe.throw(_("Khoảng SX mặc định: 'từ ngày' phải trước 'đến ngày'."))

	def on_update(self):
		# Cấu hình đổi → số liệu cache cũ có thể sai mốc: xoá toàn bộ cache bc.
		from bc.api._common import clear_cache

		clear_cache()
