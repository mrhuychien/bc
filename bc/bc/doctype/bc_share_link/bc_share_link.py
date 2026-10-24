# -*- coding: utf-8 -*-
"""BC Share Link — link/QR tự đăng nhập của 1 lãnh đạo (dòng con của BC Settings).

Chỉ lưu HASH sha256 của token; token gốc chỉ hiện 1 lần lúc tạo (bc.api.share).
"""

from frappe.model.document import Document


class BCShareLink(Document):
	pass
