"""frappe.database giả — chỉ lối vào kết nối thứ hai mà bc.ai.sqlro dùng.

Như Frappe v16 (frappe/database/__init__.py, nhánh version-16): get_db(socket, host, user, password, port,
cur_db_name) → đối tượng MariaDBDatabase; get_connection() (MariaDBConnectionUtil) trả kết nối DB-API mở bằng đúng
thông tin đó (charset utf8mb4, local_infile tắt, không multi_statements). Bản giả nối MariaDB THẬT qua pymysql (như
bản v16 dùng pymysql khi use_mysqlclient = 0); cấu hình kiểu dữ liệu mặc định của pymysql (Decimal, date, datetime,
timedelta) — sqlro tự quy đổi nên bản mysqlclient (NEWDECIMAL → float) cũng ra cùng kết quả.
"""
from __future__ import annotations

CALLS: list = []   # bộ thử đếm lời gọi (chỉ tên tài khoản + CSDL, không mật khẩu)
INIT_COMMAND = None  # bộ thử giả "máy chủ có sql_mode mặc định khác" (vd ANSI_QUOTES) — câu chạy ngay khi nối


class MariaDBDatabase:
	def __init__(self, socket=None, host=None, user=None, password=None, port=None, cur_db_name=None):
		self.socket, self.host, self.port = socket, host, port
		self.user, self.password, self.cur_db_name = user, password, cur_db_name
		self._conn = None

	def get_connection_settings(self) -> dict:
		s = {"user": self.user, "charset": "utf8mb4", "use_unicode": True, "local_infile": False}
		if self.cur_db_name:
			s["database"] = self.cur_db_name
		if self.socket:
			s["unix_socket"] = self.socket
		else:
			s["host"] = self.host or "localhost"
			if self.port:
				s["port"] = int(self.port)
		if self.password:
			s["password"] = self.password
		if INIT_COMMAND:
			s["init_command"] = INIT_COMMAND
		return s

	def get_connection(self):
		import pymysql
		CALLS.append((self.user, self.cur_db_name))
		conn = pymysql.connect(**self.get_connection_settings())
		return conn

	def connect(self):
		self._conn = self.get_connection()

	def close(self):
		if self._conn:
			self._conn.close()
			self._conn = None


def get_db(socket=None, host=None, user=None, password=None, port=None, cur_db_name=None):
	return MariaDBDatabase(socket, host, user, password, port, cur_db_name)
