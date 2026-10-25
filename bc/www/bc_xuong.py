# -*- coding: utf-8 -*-
"""www /bc_xuong — sơ đồ xưởng 3D (three.js) nhúng trong tab "Thời gian thực" của /bc.

Trang HTML độc lập (không extends web.html — mô hình 3D cần toàn khung, CSS riêng).
Cùng quyền với /bc (BC Viewer / System Manager); số liệu sống KHÔNG nằm ở đây: SPA cha
gửi xuống qua postMessage (cùng origin), bridge.js gắn lên từng phòng.
"""

from __future__ import annotations

import frappe

from bc.api._common import has_access

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.authorized = 0 if frappe.session.user == "Guest" else int(has_access())
	context.v = frappe.utils.now().replace(" ", "T").replace(":", "-")
	return context
