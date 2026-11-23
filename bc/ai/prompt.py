# -*- coding: utf-8 -*-
"""bc.ai.prompt — đề bài cho mô hình: system prompt, JSON schema đầu ra, gói `user` của từng nhóm (đặc tả §5.2–5.3).

Không gọi mạng, không đọc khoá. Đầu ra mô hình theo schema `ghi_nhan_dinh`:
{"insights": [{"signal": "S3" | null, "severity": "do" | "vang", "priority": int, "title", "body", "advice": [str]}]}
"""

from __future__ import annotations

SCHEMA_NAME = "ghi_nhan_dinh"
SCHEMA: dict = {}   # JSON Schema của đầu ra (mọi object: additionalProperties False + required đủ; không min/max)

MAX_LIST = 30           # danh sách dài hơn → giữ 30 đầu, ghi "_cat": số bị cắt ở dict cha
MAX_CHARS = 120_000     # JSON một nhóm dài hơn → cắt tiếp danh sách dài nhất


def system_prompt(today=None) -> str:
	"""Vai trò + 7 luật viết (đặc tả §5.2) + BC Settings.ai_context + ngày, năm tài chính, mùa Tết. Thiếu ngày Tết
	(tet_season ném lỗi) → bỏ dòng mùa Tết, không lỗi."""
	raise NotImplementedError


def truncate(obj, max_list: int = MAX_LIST):
	"""Bản sao của obj với mọi list > max_list phần tử chỉ giữ max_list đầu; dict CHA của list đó thêm
	"_cat": {tên_khoá: số bị cắt}. Trả (bản sao, tổng số phần tử bị cắt)."""
	raise NotImplementedError


def build_user(group: str, pack_group: dict, signals: list, max_chars: int = MAX_CHARS) -> tuple:
	"""JSON `user` của một nhóm → (chuỗi JSON, ghi_chú: list[str] về việc cắt).

	pack_group = {mảng: {tên: payload}} của nhóm, ĐÃ mã giả (nơi gọi che trước). signals = [{"id": "S1", "rule", "muc",
	"loi_quy_tac", "paths", "so_ngay", "trang_thai", "ghi_chu_quan_tri"}]. JSON: {"nhom", "pack", "tin_hieu"}, khoá
	sắp ổn định, ensure_ascii False. Dài quá max_chars → cắt tiếp danh sách dài nhất tới khi vừa, ghi vào ghi_chú."""
	raise NotImplementedError
