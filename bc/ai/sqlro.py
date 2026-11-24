# -*- coding: utf-8 -*-
"""bc.ai.sqlro — kết nối MariaDB CHỈ ĐỌC cho công cụ run_select của hỏi đáp (SPEC_bc_ai_p3 §2.2, §5, §7).

Nơi DUY NHẤT trong bc đọc `bc_ai_ro_user` / `bc_ai_ro_password` (site_config.json). Hai giá trị đọc NGAY TRONG hàm
mở kết nối, chuyển thẳng cho frappe.database.get_db (lối vào kết nối thứ hai của Frappe v16 — cùng hàm frappe.connect
và connect_replica dùng, xem frappe/database/__init__.py bản version-16) rồi bỏ; không trả ra, không ghi log, không
nằm trong lời báo lỗi nào. Không import driver CSDL trực tiếp.

Mở kết nối (__enter__):
1. Nối bằng tài khoản chỉ đọc vào đúng CSDL của site (frappe.conf db_name / db_socket / db_host / db_port).
2. SHOW GRANTS: mỗi dòng phải là GRANT chỉ gồm USAGE / SELECT / SHOW VIEW; quyền khác SELECT / SHOW VIEW chỉ được trên
   CSDL của site (`<db>`.* hoặc bảng của nó — không *.*, không mẫu % / _); không WITH GRANT OPTION, không vai trò
   (GRANT `role` TO …), không PROXY. Sai một dòng → NotReadOnly, đóng kết nối.
3. Chốt phiên (sql_mode đặt TRƯỚC bước 2): sql_mode cố định (không ANSI_QUOTES / NO_BACKSLASH_ESCAPES — bộ tách từ của sqlguard đọc chuỗi giống
   hệt MariaDB), giao dịch READ ONLY (lớp chặn thứ ba: câu ghi lọt cả hai lớp trên vẫn lỗi 1792), max_statement_time.
4. Đọc tên cột thật của tabEmployee / tabUser (gộp vào luật 5 của sqlguard).

select(sql): sqlguard.check → wrap (trần 10 giây, LIMIT) → chạy → gọt kết quả (≤ 200 dòng, ô chuỗi ≤ 200 ký tự, tổng
≤ 40.000 ký tự JSON, Decimal → float, ngày → ISO, cờ "cut"). Mọi lỗi → SqlRefused(.reason ngắn, an toàn: không mật
khẩu, không traceback, không chữ của driver ngoài tên cột / bảng sai).
"""

from __future__ import annotations

import datetime
import decimal
import json

import frappe

from bc.ai import sqlguard

LIMIT = 200          # dòng
CELL = 200           # ký tự mỗi ô chuỗi (gửi mô hình)
RAW_CELL = 4000      # select(cell=RAW_CELL): ô còn gần nguyên cho nơi gọi che tên TRƯỚC rồi mới cắt về CELL (qa.gon_sql)
TOTAL = 40_000       # ký tự JSON của cả kết quả
SECONDS = 10         # max_statement_time của mỗi câu
QUYEN_DOC = frozenset({"USAGE", "SELECT", "SHOW VIEW"})
SQL_MODE = "STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION"
_CAM_MODE = ("ANSI_QUOTES", "NO_BACKSLASH_ESCAPES", "ANSI", "ORACLE", "MSSQL", "DB2", "POSTGRESQL", "MAXDB")


class SqlRefused(Exception):
	"""Câu không chạy (bị soát chặn, quá giờ, lỗi SQL). .reason an toàn để gửi mô hình / hiện cho quản trị."""

	def __init__(self, reason: str):
		super().__init__(reason)
		self.reason = reason


class NotReadOnly(Exception):
	"""Tài khoản chỉ đọc chưa khai / không nối được / có quyền ngoài SELECT — không dùng run_select."""


def available() -> bool:
	"""Đã khai đủ hai giá trị trong site_config.json (không nối thử)."""
	return bool(frappe.conf.get("bc_ai_ro_user")) and bool(frappe.conf.get("bc_ai_ro_password"))


def _bo_nhay(ten: str) -> str:
	"""`db` → db (`` → `); bỏ thoát \\_ \\% của tên CSDL trong SHOW GRANTS."""
	ten = ten.strip()
	if len(ten) >= 2 and ten[0] == ten[-1] and ten[0] in "`\"":
		ten = ten[1:-1].replace(ten[0] * 2, ten[0])
	return ten


def _tach_dich(dich: str) -> tuple:
	"""'`db`.*' / '`db`.`tbl`' / '*.*' → (db, bảng) — chia ở dấu '.' nằm ngoài `…`."""
	trong = False
	for i, c in enumerate(dich):
		if c in "`\"":
			trong = not trong
		elif c == "." and not trong:
			return dich[:i], dich[i + 1:]
	return dich, ""


def grants_ok(lines, db_name: str) -> bool:
	"""Mọi dòng SHOW GRANTS chỉ cho đọc, và quyền đọc chỉ trên CSDL `db_name` (hàm thuần — bộ thử gọi thẳng)."""
	if not lines or not db_name:
		return False
	for raw in lines:
		s = " ".join(str(raw).split())
		up = s.upper()
		if not up.startswith("GRANT ") or " ON " not in up or " TO " not in up:
			return False                                  # vai trò (GRANT `r` TO u), SET DEFAULT ROLE, dòng lạ
		if "WITH GRANT OPTION" in up or up.startswith("GRANT PROXY"):
			return False
		on = up.index(" ON ")
		quyen = s[6:on]
		# bỏ danh sách cột: SELECT (`a`, `b`)
		sach, sau = [], 0
		for c in quyen:
			if c == "(":
				sau += 1
			elif c == ")":
				sau -= 1
			elif sau == 0:
				sach.append(c)
		ds = {" ".join(q.split()).upper() for q in "".join(sach).split(",")}
		if not ds or not ds <= QUYEN_DOC:
			return False
		if ds == {"USAGE"}:
			continue
		dich = s[on + 4:up.index(" TO ", on)].strip()
		if dich.upper().startswith(("PROCEDURE ", "FUNCTION ", "PACKAGE ")):
			return False
		db, _bang = _tach_dich(dich)
		db = _bo_nhay(db)
		# Tên CSDL trong GRANT: '_' trần là ký tự đại diện của MariaDB — nhận đúng tên site (viết trần hoặc đã thoát
		# \_), không nhận *, %, tên khác.
		if db not in (db_name, db_name.replace("_", "\\_")):
			return False
	return True


def _o(v, cell=CELL):
	"""Một ô kết quả → giá trị JSON được (bool cắt: chuỗi dài hơn `cell`)."""
	if v is None or isinstance(v, (bool, int)):
		return v, False
	if isinstance(v, float):
		return (v if v == v and v not in (float("inf"), float("-inf")) else None), False
	if isinstance(v, decimal.Decimal):
		return (float(v) if v.is_finite() else None), False
	if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
		return v.isoformat(), False
	if isinstance(v, datetime.timedelta):
		return str(v), False
	if isinstance(v, (bytes, bytearray, memoryview)):
		v = bytes(v).decode("utf-8", "replace")
	v = str(v)
	if len(v) > cell:
		return v[:cell - 1] + "…", True
	return v, False


def _ly_do(e: Exception) -> str:
	"""Lỗi driver → lý do ngắn. Chỉ dùng MÃ lỗi (+ tên cột / bảng sai trích từ lời MariaDB) — không lấy nguyên lời."""
	ma = e.args[0] if getattr(e, "args", None) and isinstance(e.args[0], int) else None
	loi = str(e.args[1]) if ma is not None and len(e.args) > 1 else ""

	def trich():
		a = loi.find("'")
		b = loi.find("'", a + 1) if a >= 0 else -1
		ten = loi[a + 1:b] if 0 <= a < b else ""
		ten = ten.rsplit(".", 1)[-1]
		return ten if 0 < len(ten) <= 64 and ten.isprintable() else ""

	if ma == 1969:
		return f"câu chạy quá {SECONDS} giây — thu hẹp điều kiện / bớt JOIN"
	if ma == 1060:
		return f"trùng tên cột {trich()!r} — đặt bí danh (AS) khác nhau cho từng cột"
	if ma == 1054:
		return f"cột không tồn tại: {trich()!r}"
	if ma == 1146:
		return f"bảng không tồn tại: {trich()!r}"
	if ma in (1064, 1149):
		return "câu SQL sai cú pháp MariaDB"
	if ma in (1044, 1142, 1143, 1227, 1792):
		return "tài khoản chỉ đọc không được phép làm việc này"
	if ma in (2006, 2013):
		return "mất kết nối CSDL"
	if ma is not None:
		return f"lỗi MariaDB {ma}"
	return "lỗi khi chạy câu SQL"


class ReadOnly:
	"""with ReadOnly() as ro: ro.select("SELECT …") — một kết nối cho một câu hỏi, đóng khi ra khỏi khối."""

	def __init__(self):
		self._conn = None
		self.columns: dict = {}
		self.doctypes: dict = {}     # {tên DocType (dạng so sánh): phân hệ} — luật 4b

	def __enter__(self) -> "ReadOnly":
		if not available():
			raise NotReadOnly("chưa khai tài khoản chỉ đọc (bc_ai_ro_user / bc_ai_ro_password)")
		db_name = frappe.conf.get("db_name")
		if not db_name:
			raise NotReadOnly("site chưa có db_name")
		try:
			from frappe.database import get_db
			db = get_db(socket=frappe.conf.get("db_socket"), host=frappe.conf.get("db_host"),
				port=frappe.conf.get("db_port"), user=frappe.conf.get("bc_ai_ro_user"),
				password=frappe.conf.get("bc_ai_ro_password"), cur_db_name=db_name)
			try:
				self._conn = db.get_connection()
			finally:
				db.password = None
				del db
		except Exception:  # noqa: BLE001 — lời driver có thể nhắc tên tài khoản; không chuyển tiếp
			self._conn = None
			raise NotReadOnly("không nối được bằng tài khoản chỉ đọc") from None
		try:
			cur = self._conn.cursor()
			# sql_mode trước: SHOW GRANTS dưới ANSI_QUOTES in tên bằng "…" thay vì `…`
			cur.execute(f"SET SESSION sql_mode = '{SQL_MODE}'")
			cur.execute("SHOW GRANTS")
			dong = [r[0] for r in cur.fetchall()]
			if not grants_ok(dong, db_name):
				raise NotReadOnly("tài khoản chỉ đọc có quyền ngoài SELECT / SHOW VIEW trên CSDL của site")
			cur.execute("SET SESSION TRANSACTION READ ONLY")
			cur.execute(f"SET SESSION max_statement_time = {SECONDS}")
			cur.execute("SELECT @@SESSION.sql_mode, @@SESSION.tx_read_only")
			mode, ro = cur.fetchone()
			if any(m in str(mode or "").upper().split(",") for m in _CAM_MODE) or not int(ro or 0):
				raise NotReadOnly("không chốt được phiên chỉ đọc")
			self._conn.autocommit(True)
			cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = DATABASE() "
				"AND table_name IN ('tabEmployee', 'tabUser')")
			for bang, cot in cur.fetchall():
				self.columns.setdefault(str(bang), set()).add(str(cot))
			cur.execute("SELECT name, module FROM `tabDocType`")
			self.doctypes = {sqlguard.key(ten): str(mod or "") for ten, mod in cur.fetchall()}
			cur.close()
		except NotReadOnly:
			self._dong()
			raise
		except Exception:  # noqa: BLE001
			self._dong()
			raise NotReadOnly("không kiểm được quyền của tài khoản chỉ đọc") from None
		return self

	def select(self, sql: str, cell: int = CELL) -> dict:
		"""→ {"columns": [...], "rows": [[...]], "cut": bool}; câu bị chặn / lỗi → SqlRefused. cell: ô chuỗi cắt ở bao
		nhiêu ký tự (mặc định CELL; qa truyền RAW_CELL để che tên trước khi cắt) — trần tổng TOTAL luôn tính như ô đã cắt
		về CELL (đúng cỡ sau khi nơi gọi cắt)."""
		cell = max(CELL, min(int(cell), RAW_CELL))
		if self._conn is None:
			raise SqlRefused("chưa mở kết nối chỉ đọc")
		ok, ly_do, sach = sqlguard.check(sql, self.columns)
		if not ok:
			raise SqlRefused(ly_do)
		self._soat_phan_he(sach)
		cau = sqlguard.wrap(sach, limit=LIMIT + 1, seconds=SECONDS)
		try:
			cur = self._conn.cursor()
			try:
				cur.execute(cau)
				cot = [str(d[0]) for d in (cur.description or ())]
				dong = cur.fetchmany(LIMIT + 1) if cur.description else []
			finally:
				cur.close()
		except Exception as e:  # noqa: BLE001
			raise SqlRefused(_ly_do(e)) from None
		cut = len(dong) > LIMIT
		tong = len(json.dumps(cot, ensure_ascii=False))
		rows = []
		for r in dong[:LIMIT]:
			hang = []
			for v in r:
				o, cat = _o(v, cell)
				cut = cut or cat
				hang.append(o)
			dai = len(json.dumps([x[:CELL] if isinstance(x, str) else x for x in hang], ensure_ascii=False)) + 1
			if tong + dai > TOTAL:
				cut = True
				break
			tong += dai
			rows.append(hang)
		return {"columns": cot, "rows": rows, "cut": cut}

	def _soat_phan_he(self, sach: str) -> None:
		"""Luật 4b (lớp cấu trúc): mọi bảng `tab…` phải là bảng của một DocType trên site và không thuộc phân hệ cấm
		(sqlguard.MODULE_CAM). Bảng có danh sách cột riêng (tabEmployee, tabUser) được miễn — luật 5 quản cột."""
		mien = {sqlguard.key(k) for k in sqlguard.ALLOWED_COLUMNS}
		for bang in sqlguard.tables(sach):
			if sqlguard.key(bang) in mien:
				continue
			mod = self.doctypes.get(sqlguard.key(bang[3:]))
			if mod is None:
				raise SqlRefused(f"bảng {bang!r} không phải bảng của một DocType trên site")
			if not sqlguard.module_allowed(mod):
				raise SqlRefused(f"bảng {bang!r} thuộc phân hệ {mod} (hệ thống / tích hợp / nhân sự) — không được đọc")

	def _dong(self):
		try:
			if self._conn is not None:
				self._conn.close()
		except Exception:  # noqa: BLE001
			pass
		self._conn = None

	def __exit__(self, *a) -> None:
		self._dong()
