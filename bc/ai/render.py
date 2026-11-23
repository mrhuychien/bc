# -*- coding: utf-8 -*-
"""bc.ai.render — placeholder → số thật, định dạng kiểu VN, lint "số trần" (đặc tả §5.3). Hàm thuần, không DB.

Luật số: mô hình KHÔNG được viết số liệu — mọi số trong lời là `{{path|kiểu}}` trỏ vào gói số; ở đây thay bằng số
thật rồi mới lưu. Lời còn số trần → `ok = False` → nơi gọi bỏ lời AI, giữ lời quy tắc.

Kiểu và định dạng (fmt):
- tien : như fmtMoney của lib/format.js nhưng VIẾT ĐỦ đơn vị: |n| ≥ 1e9 → "1,6 tỷ" (1 số lẻ, bỏ ",0"); ≥ 1e8 →
         "250 triệu" (nguyên); ≥ 1e6 → "33 triệu" / "1,5 triệu" (1 số lẻ, bỏ ",0"); < 1e6 → "450.000 đ" (nhóm nghìn).
         Số âm giữ dấu "-".
- so   : nhóm nghìn kiểu VN ("12.345"); số không nguyên → 1 số lẻ, dấu phẩy ("12,5").
- pct  : giá trị ĐÃ nhân 100 → 1 số lẻ + "%" ("35,2%").
- ngay : ngày ISO / date / datetime → "d/m/yyyy".
- chu  : chuỗi ≤ 120 ký tự (dài hơn → lỗi kiểu).
Giá trị không khớp kiểu (tien/so/pct cần int/float không phải bool; ngay cần ngày; chu cần str) → ValueError.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Filled:
	text: str = ""                                   # lời đã thay số (placeholder lỗi để nguyên)
	paths: list = field(default_factory=list)        # path đã dùng, theo thứ tự, không trùng
	sections_used: list = field(default_factory=list)  # khoá cấp 1 của các path, theo thứ tự, không trùng
	errors: list = field(default_factory=list)       # "path:<p>" | "kieu:<p>" | "ngoai-nhom:<p>" | "cu-phap"


def fmt(value, kind: str) -> str:
	"""Định dạng `value` theo `kind` (xem docstring module). Sai kiểu → ValueError."""
	raise NotImplementedError


def fill(text: str, pack: dict, sections=None) -> Filled:
	"""Thay mọi `{{path|kiểu}}` trong `text` bằng giá trị đã định dạng lấy từ `pack` (bc.ai.registry.resolve).

	`sections`: tập khoá cấp 1 được phép (None = mọi mảng) — path ngoài tập → lỗi "ngoai-nhom:<p>".
	Path không có → "path:<p>"; kiểu lạ / không khớp giá trị → "kieu:<p>"; còn "{{" hoặc "}}" sau khi thay (placeholder
	viết hỏng) → "cu-phap"."""
	raise NotImplementedError


def strip_placeholders(text: str) -> str:
	"""Lời đã BỎ mọi placeholder hợp lệ (thay bằng một dấu cách) — đầu vào của lint."""
	raise NotImplementedError


def lint(text: str) -> list:
	"""Các mẩu "số trần" trong lời đã bỏ placeholder (rỗng = sạch). Bắt (đặc tả §5.3 bước 3):
	- dãy ≥ 3 chữ số không dính liền chữ cái đứng TRƯỚC (kể cả có dấu nhóm nghìn: "1.250.000", "1,250");
	- số (kể cả 1–2 chữ số, có thể có phần lẻ) đứng trước đơn vị: %, đ, ₫, k, tr, triệu, tỷ, nghìn ("35%", "2 tỷ",
	  "1,5 triệu", "50k").
	Ngoại lệ được giữ: năm 20xx; ngày d/m hoặc d/m/yyyy; mã có chữ đứng liền trước ("SR900"); số chỉ thời hạn ≤ 2 chữ
	số không kèm đơn vị trên ("trong 7 ngày", "30 ngày")."""
	raise NotImplementedError


def render_rule(title: str, detail: str, pack: dict) -> dict:
	"""Lời QUY TẮC → {"ok", "title" (≤ 200 ký tự), "body", "paths", "sections_used", "errors"} (không lint — lời do
	code viết). ok = False khi có lỗi placeholder (quy tắc viết sai path)."""
	raise NotImplementedError


def render_insight(raw: dict, pack: dict, sections, mask=None) -> dict:
	"""Lời của MÔ HÌNH cho một nhận định → {"ok", "title", "body", "advice": [str], "paths", "sections_used", "errors"}.

	raw = {"title", "body", "advice": [str]} (đầu ra mô hình, còn placeholder và có thể còn mã giả KH#/NCC#).
	1. fill từng phần với `sections` = các mảng của NHÓM (path ngoài nhóm → lỗi);
	2. lint trên lời đã bỏ placeholder VÀ đã bỏ mã giả hợp lệ (mask.strip) — mã giả lạ (mô hình bịa) còn lại sẽ bị bắt;
	3. hoàn nguyên mã giả → tên thật (mask.unmask) trên lời đã thay số;
	4. title cắt 200 ký tự; advice bỏ dòng rỗng, tối đa 3.
	ok = False khi có bất kỳ lỗi nào (errors ghi lý do: lỗi của fill, "so-tran:<mẩu>", "rong" khi title / body rỗng)."""
	raise NotImplementedError
