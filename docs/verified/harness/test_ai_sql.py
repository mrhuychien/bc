"""Trợ lý AI P3 — soát câu SQL (bc.ai.sqlguard) và kết nối chỉ đọc (bc.ai.sqlro), SPEC_bc_ai_p3 §2.2, §5, §10.3–4.

1. Luật tĩnh: sqlguard chỉ import thư viện chuẩn; sqlro là file DUY NHẤT của bc/ nhắc bc_ai_ro_user /
   bc_ai_ro_password, không import driver CSDL, đọc site config trong hàm (không ở cấp module).
2. Bộ tách từ: chuỗi hai kiểu nháy + thoát, tên `…` (`` ), số, chú thích / biến / ký tự lạ / chuỗi không đóng.
3. Bộ câu HỢP LỆ (≥ 60: JOIN, CTE, truy vấn con, gộp nhóm, hàm cửa sổ, chuỗi chứa chữ cấm, bảng `có dấu cách`,
   tabEmployee / tabUser với cột cho phép) — check() nhận, và chạy THẬT được qua tài khoản chỉ đọc trên bảng v16.
4. Bộ câu TẤN CÔNG (≥ 120, mỗi luật nhiều cách viết) — check() từ chối, lý do ngắn, không lặp lại câu.
5. wrap() đúng mẫu luật 6; doctype_allowed; grants_ok (hàm thuần) trên các dòng SHOW GRANTS mẫu.
6. MariaDB thật: tài khoản chỉ đọc chạy được; tài khoản có INSERT / SELECT *.* / GRANT OPTION bị từ chối; LIMIT 200 +
   cờ cut; ORDER BY giữ thứ tự; ô / tổng bị cắt; Decimal / ngày quy đổi; max_statement_time cắt câu nặng; câu ghi
   lọt qua lớp soát vẫn hỏng trên kết nối chỉ đọc (lệnh thô); cột thật của tabEmployee gộp vào luật 5; đóng kết nối;
   không mật khẩu / băm mật khẩu trong bất kỳ lỗi, traceback, log, stderr nào.

Chạy: BC_TEST_DB=bc_test_ai_sql python3 -B test_ai_sql.py   (BC_APP_ROOT=<bản sao> để thử đột biến). Tạo và XOÁ hai
tài khoản MariaDB bc_p3f_ro / bc_p3f_rw và CSDL của bộ thử.
"""
import ast
import contextlib
import io
import json
import os
import socket
import sys
import time
import traceback

# ─── Chặn mạng: mọi socket không phải unix (MariaDB) và mọi lượt tra DNS ném lỗi ──────────────────────────────
BLOCKED: list = []
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo


def _cam_noi(self, address, *a):
	if self.family != socket.AF_UNIX:
		BLOCKED.append(("connect", address))
		raise OSError(f"bộ thử: cấm ra mạng ({address})")
	return _connect(self, address, *a)


def _cam_dns(host, *a, **k):
	BLOCKED.append(("dns", host))
	raise OSError(f"bộ thử: cấm tra DNS ({host})")


socket.socket.connect = _cam_noi
socket.getaddrinfo = _cam_dns

from seed import Check, insert, reset  # noqa: E402
from paths import BC_ROOT, DB, SOCK  # noqa: E402

import frappe  # noqa: E402
import pymysql  # noqa: E402  (chỉ bộ thử: tạo / xoá tài khoản bằng root)

from bc.ai import sqlguard, sqlro  # noqa: E402

c = Check()
RO, RW = "bc_p3f_ro", "bc_p3f_rw"
PW_RO = "Mk-p3f.RO#9zQ"          # mật khẩu dạng lạ: chuỗi này không được xuất hiện ở bất kỳ đâu ngoài site config
PW_RW = "Mk-p3f.RW#4xV"
BIG = "tabP3F Big"


def root():
	return pymysql.connect(user="root", unix_socket=SOCK, charset="utf8mb4", autocommit=True)


def rsql(q, args=None):
	con = root()
	try:
		cur = con.cursor()
		cur.execute(q, args)
		return cur.fetchall()
	finally:
		con.close()


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("1. Luật tĩnh")
PKG = os.path.join(BC_ROOT, "bc")


def tree(rel):
	return ast.parse(open(os.path.join(PKG, rel), encoding="utf-8").read())


def imports_of(t):
	out = []
	for n in ast.walk(t):
		if isinstance(n, ast.Import):
			out += [a.name for a in n.names]
		elif isinstance(n, ast.ImportFrom):
			out.append(("." * n.level) + (n.module or ""))
	return out


g_imp = imports_of(tree("ai/sqlguard.py"))
c("sqlguard: chỉ import thư viện chuẩn", g_imp and all(m.split(".")[0] in sys.stdlib_module_names for m in g_imp),
	g_imp)
r_imp = imports_of(tree("ai/sqlro.py"))
c("sqlro: không import driver CSDL (pymysql / MySQLdb / mariadb) — kết nối qua frappe.database.get_db",
	not [m for m in r_imp if m.split(".")[0].lower() in ("pymysql", "mysqldb", "mariadb", "mysql", "_mysql")], r_imp)
src_ro = open(os.path.join(PKG, "ai/sqlro.py"), encoding="utf-8").read()
c("sqlro: mở kết nối bằng frappe.database.get_db (lối vào kết nối thứ hai của Frappe v16)",
	"from frappe.database import get_db" in src_ro)
nhac = []
for d, _s, fs in os.walk(PKG):
	if "__pycache__" in d:
		continue
	for f in fs:
		if f.endswith((".py", ".js", ".json", ".html")):
			p = os.path.join(d, f)
			s = open(p, encoding="utf-8", errors="replace").read()
			if "bc_ai_ro_user" in s or "bc_ai_ro_password" in s:
				nhac.append(os.path.relpath(p, PKG))
c("cả bc/: chỉ ai/sqlro.py nhắc bc_ai_ro_user / bc_ai_ro_password", nhac == ["ai/sqlro.py"], nhac)
t_ro = tree("ai/sqlro.py")
cap_mod = [ast.unparse(n)[:60] for n in t_ro.body if isinstance(n, (ast.Assign, ast.AnnAssign))
	and "conf" in ast.unparse(n)]
c("sqlro: không giữ site config ở biến cấp module (đọc trong hàm)", not cap_mod, cap_mod)

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("2. Bộ tách từ")
T = sqlguard.tach
tk = T("SELECT 'it''s', 'a\\'b -- c', \"x\"\"y\", `ta``b`, 1.5e3, .5, 0x1F, t.col")
c("chuỗi '…' với '' và \\' là MỘT chuỗi", [(t.k, t.v) for t in tk if t.k == "s"][:2] == [("s", "it's"),
	("s", "a'b -- c")], tk)
c("chuỗi \"…\" với \"\"", any(t.k == "s" and t.v == 'x"y' and t.q == '"' for t in tk), tk)
c("tên `…` với ``", any(t.k == "i" and t.v == "ta`b" for t in tk), tk)
c("số 1.5e3 / .5 / 0x1F là số", [t.v for t in tk if t.k == "n"] == ["1.5e3", ".5", "0x1F"], tk)
c("t.col → tên . tên", [t.v for t in tk][-3:] == ["t", ".", "col"], tk)
for q, mo_ta in (("SELECT 'abc", "chuỗi không đóng"), ("SELECT 'abc\\'", "chuỗi kết thúc bằng \\' không đóng"),
		("SELECT \"abc", "chuỗi \" không đóng"), ("SELECT `abc", "tên ` không đóng"), ("SELECT ``", "tên rỗng"),
		("SELECT 1 -- x", "--"), ("SELECT 1 # x", "#"), ("SELECT /* x */ 1", "/* */"), ("SELECT 1 */", "*/ lẻ"),
		("SELECT @a", "@"), ("SELECT a:=1", ":"), ("SELECT ?", "?"), ("SELECT {fn NOW()}", "{ }"),
		("SELECT \\N", "\\"), ("SELECT 1\x00", "NUL"), ("SELECT 1 \U0001F600", "ký tự ngoài BMP")):
	try:
		T(q)
		c(f"tách từ chặn {mo_ta}", False, q)
	except sqlguard._Loi as e:
		c(f"tách từ chặn {mo_ta}", bool(str(e)), q)
c("chữ cấm / chú thích TRONG chuỗi không bị coi là từ", [t.k for t in T("SELECT '-- # /* @x DELETE'")] == ["w", "s"])

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
VALID = [
	"SELECT 1",
	"select 1;",
	"   \n SELECT name FROM `tabCustomer`   ;  ",
	"SELECT name, customer, grand_total FROM `tabSales Invoice` WHERE docstatus = 1",
	"SELECT customer, SUM(grand_total) AS tong FROM `tabSales Invoice` WHERE docstatus = 1 GROUP BY customer "
	"ORDER BY tong DESC LIMIT 10",
	"SELECT DATE_FORMAT(posting_date, '%Y-%m') AS thang, SUM(base_net_total) AS dt FROM `tabSales Invoice` "
	"WHERE docstatus = 1 AND is_return = 0 GROUP BY thang ORDER BY thang",
	"SELECT si.name, sii.item_code, sii.qty, sii.amount FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` sii "
	"ON sii.parent = si.name WHERE si.docstatus = 1",
	"SELECT i.item_group, SUM(sii.amount) AS dt FROM `tabSales Invoice Item` sii INNER JOIN `tabItem` i "
	"ON i.name = sii.item_code GROUP BY i.item_group",
	"SELECT c.customer_group, COUNT(*) AS so FROM `tabCustomer` c GROUP BY c.customer_group HAVING COUNT(*) > 0",
	"WITH t AS (SELECT customer, SUM(grand_total) AS tong FROM `tabSales Invoice` WHERE docstatus = 1 GROUP BY "
	"customer) SELECT customer, tong FROM t WHERE tong > 0 ORDER BY tong DESC",
	"WITH RECURSIVE n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 12) SELECT i FROM n",
	"WITH a AS (SELECT name FROM `tabCustomer`), b AS (SELECT customer FROM `tabSales Invoice`) "
	"SELECT a.name FROM a LEFT JOIN b ON b.customer = a.name WHERE b.customer IS NULL",
	"SELECT name FROM `tabCustomer` WHERE name IN (SELECT customer FROM `tabSales Invoice` WHERE docstatus = 1)",
	"SELECT x.customer, x.n FROM (SELECT customer, COUNT(*) AS n FROM `tabSales Invoice` GROUP BY customer) AS x "
	"WHERE x.n > 1",
	"SELECT customer FROM `tabSales Invoice` si WHERE EXISTS (SELECT 1 FROM `tabSales Invoice Item` sii "
	"WHERE sii.parent = si.name)",
	"(SELECT name FROM `tabCustomer` LIMIT 3) UNION (SELECT name FROM `tabSupplier` LIMIT 3)",
	"SELECT 'DELETE FROM tabSessions; DROP TABLE x' AS ghi_chu",
	"SELECT name FROM `tabItem` WHERE item_name LIKE '%update%' OR description LIKE '%sleep(5)%'",
	"SELECT \"insert into\" AS a, 'it''s' AS b, 'a\\'b' AS c",
	"SELECT CONCAT(customer, ' -- ', name) AS nhan FROM `tabSales Invoice`",
	"SELECT '/* not a comment */' AS a, '#hash' AS b, '@bien' AS d",
	"SELECT 'tabSessions' AS ten_bang, '__Auth' AS b2, 'information_schema.tables' AS b3",
	"SELECT ROUND(SUM(outstanding_amount) / 1000000, 1) AS trieu FROM `tabSales Invoice` WHERE docstatus = 1",
	"SELECT customer, DATEDIFF('2026-11-24', due_date) AS tuoi FROM `tabSales Invoice` WHERE outstanding_amount > 0",
	"SELECT CASE WHEN grand_total > 1000000 THEN 'lon' ELSE 'nho' END AS loai, COUNT(*) AS n "
	"FROM `tabSales Invoice` GROUP BY loai",
	"SELECT customer, grand_total, RANK() OVER (PARTITION BY customer ORDER BY grand_total DESC) AS hang "
	"FROM `tabSales Invoice`",
	"SELECT posting_date, SUM(grand_total) OVER (ORDER BY posting_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) "
	"AS luy_ke FROM `tabSales Invoice`",
	"SELECT warehouse, SUM(actual_qty) AS ton FROM `tabBin` GROUP BY warehouse",
	"SELECT item_code, SUM(actual_qty * valuation_rate) AS gia_tri FROM `tabBin` GROUP BY item_code "
	"ORDER BY gia_tri DESC LIMIT 20",
	"SELECT account, SUM(debit) - SUM(credit) AS so_du FROM `tabGL Entry` WHERE is_cancelled = 0 GROUP BY account",
	"SELECT e.name, e.employee_name, e.department, e.designation FROM `tabEmployee` e WHERE e.status = 'Active'",
	"SELECT department, COUNT(*) AS so_nguoi FROM tabEmployee WHERE status = 'Active' GROUP BY department",
	"SELECT COUNT(*) FROM `tabEmployee` WHERE date_of_joining >= '2026-01-01'",
	"SELECT branch, company, employment_type, vn_contract_type, COUNT(name) AS n FROM tabEmployee "
	"GROUP BY branch, company, employment_type, vn_contract_type",
	"SELECT name, relieving_date FROM tabEmployee WHERE relieving_date IS NOT NULL ORDER BY relieving_date DESC",
	"SELECT `e`.`name`, `e`.`employee` FROM `tabEmployee` AS `e`",
	"SELECT u.name, u.enabled, u.user_type, u.last_login FROM `tabUser` u WHERE u.enabled = 1",
	"SELECT user_type, COUNT(*) AS n FROM tabUser GROUP BY user_type",
	"SELECT name FROM tabUser WHERE last_active < '2026-10-01' AND creation > '2025-01-01'",
	"SELECT e.name, si.name AS hd, si.owner AS nguoi FROM tabEmployee e JOIN `tabSales Invoice` si "
	"ON si.docstatus = 1 LIMIT 5",
	"SELECT e.department, d.department_name FROM tabEmployee e LEFT JOIN `tabDepartment` d ON d.name = e.department",
	"SELECT si.name, si.owner, si.modified_by FROM `tabSales Invoice` si",
	"SELECT `name`, `grand_total` FROM `tabSales Invoice` WHERE `customer` = 'KH 1'",
	"SELECT c.`customer_name` FROM `tabCustomer` AS c ORDER BY c.`customer_name`",
	"SELECT SUBSTRING(name, 1, 5) AS a, UPPER(customer) AS b, LOWER(status) AS c, TRIM(customer) AS d "
	"FROM `tabSales Invoice`",
	"SELECT IFNULL(SUM(grand_total), 0) AS a, COALESCE(MAX(posting_date), '2000-01-01') AS b FROM `tabSales Invoice`",
	"SELECT YEAR(posting_date) AS nam, MONTH(posting_date) AS thang, COUNT(*) AS n FROM `tabSales Invoice` "
	"GROUP BY nam, thang",
	"SELECT name FROM `tabSales Invoice` WHERE posting_date BETWEEN '2026-01-01' AND '2026-12-31' "
	"AND customer NOT IN ('a', 'b')",
	"SELECT 1.5 * 2 AS a, 10 / 3 AS b, 7 % 3 AS c, -5 AS d, 1e3 AS e, .25 AS f, 0x41 AS g",
	"SELECT CAST(grand_total AS DECIMAL(18, 2)) AS gt FROM `tabSales Invoice`",
	"SELECT GROUP_CONCAT(DISTINCT customer ORDER BY customer SEPARATOR ', ') AS ds FROM `tabSales Invoice`",
	"SELECT t.item_code, t.qty FROM (SELECT item_code, SUM(qty) AS qty FROM `tabSales Invoice Item` "
	"GROUP BY item_code) t ORDER BY t.qty DESC LIMIT 5",
	"SELECT a.customer FROM `tabSales Invoice` a LEFT JOIN `tabCustomer` b ON b.name = a.customer WHERE b.name IS NULL",
	"SELECT name FROM `tabItem` i WHERE NOT EXISTS (SELECT 1 FROM `tabBin` b WHERE b.item_code = i.name)",
	"SELECT JSON_OBJECT('n', COUNT(*)) AS j FROM `tabCustomer`",
	"SELECT IF(is_return = 1, 'tra', 'ban') AS loai, SUM(grand_total) AS tong FROM `tabSales Invoice` GROUP BY loai",
	"SELECT supplier, SUM(grand_total) AS tong FROM `tabPurchase Invoice` WHERE docstatus = 1 GROUP BY supplier",
	"SELECT pi.supplier, pii.item_code FROM `tabPurchase Invoice` pi JOIN `tabPurchase Invoice Item` pii "
	"ON pii.parent = pi.name",
	"SELECT territory, COUNT(*) AS n FROM `tabCustomer` GROUP BY territory WITH ROLLUP",
	"SELECT name FROM `tabSales Invoice` ORDER BY posting_date DESC, name LIMIT 10 OFFSET 5",
	"((SELECT name FROM `tabCustomer`))",
	"SELECT DISTINCT customer FROM `tabSales Invoice`",
	"SELECT name FROM `tabSales Invoice` WHERE customer REGEXP '^KH'",
	"SELECT `ta`.`name` FROM `tabSales Invoice` `ta`",
	"SELECT s.name, s.remarks FROM `tabSales Invoice` s WHERE s.remarks LIKE '%@%'",
	"SELECT 'tabEmployee' AS ten, COUNT(*) AS n FROM `tabCustomer`",
	"SELECT * FROM `tabCustomer` LIMIT 5",
	"SELECT c.* FROM `tabCustomer` c LIMIT 5",
	"SELECT si.posting_date, si.grand_total * 1.1 AS co_thue FROM `tabSales Invoice` si",
	"SELECT MAX(modified) AS m FROM `tabSales Invoice`",
	"SELECT name, warehouse_name FROM `tabWarehouse` WHERE is_group = 0",
	"SELECT item_code, warehouse, SUM(actual_qty) AS q FROM `tabStock Ledger Entry` WHERE is_cancelled = 0 "
	"AND posting_date <= '2026-11-24' GROUP BY item_code, warehouse",
	"SELECT name, posting_date FROM `tabSales Invoice` WHERE name = \"SINV-0001\"",
	"SELECT name FROM `tabSales Invoice` WHERE customer = 'Công ty Hà An' AND remarks = 'Đơn bị DELETE, SET lại'",
	"SELECT N'xin chào' AS a, _utf8mb4'abc' AS b, X'41' AS c, B'01' AS d",
	"SELECT si.customer, (SELECT COUNT(*) FROM `tabSales Invoice Item` x WHERE x.parent = si.name) AS so_dong "
	"FROM `tabSales Invoice` si",
	"SELECT name FROM `tabCustomer` WHERE disabled = FALSE AND customer_name IS NOT NULL",
	"SELECT name FROM `tabItem` WHERE item_group IN ('Tết', 'Bánh') ORDER BY name",
	"SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'Overdue' THEN 1 ELSE 0 END) AS qua_han FROM `tabSales Invoice`",
	"SELECT t.customer, t.tong FROM (WITH x AS (SELECT customer, SUM(grand_total) AS tong FROM `tabSales Invoice` "
	"GROUP BY customer) SELECT * FROM x) t",
	"SELECT name FROM `tabSales Invoice` WHERE posting_date > DATE_SUB('2026-11-24', INTERVAL 30 DAY)",
	"SELECT LAG(grand_total) OVER (ORDER BY posting_date) AS truoc, grand_total FROM `tabSales Invoice`",
	# soát chéo P3: bí danh Employee bắt mọi từ đứng sau — cột của bảng khác vẫn dùng được
	"SELECT d.name, d.docstatus FROM `tabDepartment` d JOIN tabEmployee e ON e.department = d.name WHERE e.status = 'Active'",
	"SELECT e.name FROM tabEmployee e WHERE e.status = 'Active' ORDER BY e.name LIMIT 5 OFFSET 0",
]

ATTACK = [
	# ── luật 1: một câu, SELECT / WITH, độ dài, ';'
	("rỗng", ""), ("khoảng trắng", "   \n "), ("SHOW", "SHOW TABLES"), ("DESCRIBE", "DESCRIBE tabUser"),
	("EXPLAIN", "EXPLAIN SELECT 1"), ("UPDATE trong ngoặc", "(UPDATE `tabCustomer` SET disabled = 1)"),
	("VALUES", "VALUES (1)"), ("TABLE", "TABLE `tabCustomer`"), ("HANDLER", "HANDLER tabUser OPEN"),
	("từ lạ trước SELECT", "x SELECT 1"), ("hai câu", "SELECT 1; SELECT 2"), ("';' kép ở cuối", "SELECT 1;;"),
	("'; ;' ở cuối", "SELECT 1 ; ; "), ("câu ghi xếp chồng", "SELECT 1; DROP TABLE tabCustomer"),
	("xếp chồng xuống dòng", "SELECT 1;\nDELETE FROM tabCustomer"), ("';' trong chuỗi rồi câu thứ hai",
		"SELECT ';' AS a; SELECT 2"), ("quá 4.000 ký tự", "SELECT " + "1," * 2100 + "1"),
	("bắt đầu bằng WITH nhưng là DELETE", "WITH x AS (SELECT 1) DELETE FROM `tabCustomer`"),
	# ── chú thích
	("-- cuối câu", "SELECT 1 -- x"), ("-- trần", "SELECT 1 --"), ("--\\n rồi bảng cấm", "SELECT 1 --\nFROM tabSessions"),
	("#", "SELECT 1 # x"), ("# dính", "SELECT name FROM `tabCustomer`#"), ("/* */", "SELECT 1 /* x */"),
	("/*! */ thực thi", "SELECT 1 /*! UNION SELECT sid FROM tabSessions */"),
	("/*M! */ thực thi", "SELECT 1 /*M!100000 , SLEEP(5) */"), ("/* không đóng", "SELECT 1 /* unterminated"),
	("/* lồng */", "SELECT 1 /* /* nested */ */"), ("*/ lẻ", "SELECT 1 */"), ("/**/ thay khoảng trắng",
		"SELECT/**/name/**/FROM/**/tabCustomer"), ("1--1", "SELECT 1--1"), ("/*+ gợi ý */", "SELECT /*+ NO_ICP() */ 1"),
	# ── chuỗi / tên không đóng
	("chuỗi không đóng", "SELECT 'abc"), ("\\' làm chuỗi không đóng", "SELECT 'abc\\'"),
	("\" không đóng", "SELECT \"abc"), ("` không đóng", "SELECT `abc FROM t"),
	# ── biến
	("@a", "SELECT @a"), ("@@version", "SELECT @@version"), ("@@GLOBAL", "SELECT @@GLOBAL.secure_file_priv"),
	("INTO @x", "SELECT name INTO @x FROM tabCustomer"), ("@x :=", "SELECT @x := 1"), ("@ cách", "SELECT 1 WHERE 1 = @ x"),
	("`a`@`b`", "SELECT `a`@`b`"),
	# ── luật 2: từ khoá ghi / điều khiển
	("INTO OUTFILE", "SELECT 1 INTO OUTFILE '/tmp/x'"), ("INTO DUMPFILE", "SELECT name FROM tabCustomer INTO DUMPFILE '/tmp/y'"),
	("INTO OUTFILE nhiều dòng", "SELECT\tname\nFROM\ttabCustomer\nINTO\nOUTFILE\n'/tmp/z'"),
	("FOR UPDATE", "SELECT name FROM tabCustomer FOR UPDATE"), ("for update nowait", "select name from tabCustomer for update nowait"),
	("FoR UpDaTe", "SeLeCt name FrOm tabCustomer fOr UpDaTe"), ("LOCK IN SHARE MODE", "SELECT name FROM tabCustomer LOCK IN SHARE MODE"),
	("FOR UPDATE trong truy vấn con", "SELECT 1 FROM tabCustomer WHERE name IN (SELECT customer FROM `tabSales Invoice` FOR UPDATE)"),
	("WITH … UPDATE", "WITH x AS (SELECT 1) UPDATE tabCustomer SET disabled = 1"), ("REPLACE", "SELECT REPLACE(name, 'a', 'b') FROM tabCustomer"),
	("INSERT trong truy vấn con", "SELECT 1 FROM (INSERT INTO t VALUES (1)) x"), ("PROCEDURE ANALYSE", "SELECT 1 PROCEDURE ANALYSE()"),
	("NEXT VALUE FOR", "SELECT NEXT VALUE FOR s1"), ("NEXTVAL", "SELECT NEXTVAL(s1)"), ("SETVAL", "SELECT SETVAL(s1, 5)"),
	("UNION TABLE", "SELECT 1 UNION TABLE tabCustomer"), ("CHARACTER SET", "SELECT CAST(name AS CHAR CHARACTER SET utf8) FROM tabCustomer"),
	("SET STATEMENT lồng", "SELECT 1 FROM (SET STATEMENT max_statement_time=0 FOR SELECT 1) t"),
	("CALL", "SELECT 1 UNION CALL p()"), ("LOAD DATA", "SELECT 1 FROM t WHERE LOAD DATA"), ("GRANT", "SELECT 1 GRANT"),
	("DO", "SELECT 1 FROM t WHERE DO 1"), ("PREPARE / EXECUTE", "SELECT 1 FROM (SELECT 1) t WHERE EXECUTE s"),
	("USE INDEX", "SELECT name FROM tabCustomer USE INDEX (PRIMARY)"), ("TRUNCATE", "SELECT TRUNCATE(1.5, 0)"),
	# ── luật 2: hàm cấm
	("SLEEP", "SELECT SLEEP(5)"), ("sleep (cách)", "SELECT sleep (5)"), ("SlEeP", "SELECT SlEeP(5)"),
	("SLEEP trong WHERE", "SELECT name FROM tabCustomer WHERE SLEEP(1) = 0"), ("SLEEP trong truy vấn con", "SELECT (SELECT SLEEP(10))"),
	("SLEEP trong CTE", "WITH s AS (SELECT SLEEP(3)) SELECT * FROM s"), ("`sleep`(…)", "SELECT `sleep`(3)"),
	("`SLEEP` (…)", "SELECT `SLEEP` (3)"),
	("BENCHMARK trong truy vấn con", "SELECT 1 FROM tabCustomer WHERE name IN (SELECT name FROM tabCustomer WHERE BENCHMARK(1000000, MD5('a')))"),
	("LOAD_FILE", "SELECT LOAD_FILE('/etc/passwd')"), ("LOAD_FILE hex", "SELECT LOAD_FILE(0x2f6574632f706173737764)"),
	("LOAD_FILE char()", "SELECT LOAD_FILE(CHAR(47,101,116,99,47,112,97,115,115,119,100))"), ("GET_LOCK", "SELECT GET_LOCK('a', 10)"),
	("RELEASE_LOCK", "SELECT RELEASE_LOCK('a')"), ("IS_FREE_LOCK", "SELECT IS_FREE_LOCK('a')"), ("IS_USED_LOCK", "SELECT IS_USED_LOCK('a')"),
	("MASTER_POS_WAIT", "SELECT MASTER_POS_WAIT('x', 1)"),
	# ── luật 3: CSDL khác, tên có tiền tố CSDL
	("information_schema", "SELECT * FROM information_schema.tables"), ("INFORMATION_SCHEMA", "SELECT table_name FROM INFORMATION_SCHEMA.TABLES"),
	("`information_schema`", "SELECT * FROM `information_schema`.`columns`"), ("mysql.user", "SELECT user, password FROM mysql.user"),
	("`mysql`.`global_priv`", "SELECT * FROM `mysql`.`global_priv`"), ("performance_schema", "SELECT * FROM performance_schema.threads"),
	("sys", "SELECT * FROM sys.session"), ("Mysql.User", "SELECT * FROM Mysql.User"), ("mysql . user (cách)", "SELECT * FROM mysql . user"),
	("(information_schema.tables)", "SELECT * FROM (information_schema.tables)"), ("(mysql.user)", "SELECT * FROM (mysql.user)"),
	("UNION information_schema", "SELECT 1 UNION SELECT table_name FROM information_schema.tables"),
	("\"mysql\" kiểu ANSI", "SELECT * FROM \"mysql\".user"),
	("site khác .`tabCustomer`", "SELECT * FROM otherdb.`tabCustomer`"), ("`site_khac`.`tabSales Invoice`", "SELECT * FROM `other_site`.`tabSales Invoice`"),
	("`otherdb`.`tabUser` x", "SELECT x.name FROM `otherdb`.`tabUser` x"), ("a.b.c", "SELECT a.b.c FROM t a"),
	("FROM otherdb.foo", "SELECT * FROM otherdb.foo"), ("JOIN otherdb.cust", "SELECT c.name FROM `tabCustomer` c JOIN otherdb.cust d ON d.name = c.name"),
	("FROM a, otherdb.foo", "SELECT 1 FROM tabCustomer, otherdb.foo"),
	("FROM (otherdb.foo)", "SELECT * FROM (otherdb.foo)"),
	("…ON …, otherdb.foo", "SELECT 1 FROM tabCustomer c JOIN tabItem i ON i.name = c.name, otherdb.foo"),
	("ı không chấm (information_schema)", "SELECT * FROM ınformatıon_schema.tables"),
	("ı không chấm (tabSessions)", "SELECT * FROM `tabSessıons`"),
	("cột Employee có dấu lạ", "SELECT name FROM tabEmployee WHERE `date_of_bírth` > '2000-01-01'"),
	# ── luật 4: bảng cấm
	("__Auth", "SELECT * FROM __Auth"), ("`__Auth`", "SELECT * FROM `__Auth`"), ("`__auth`", "select password from `__auth`"),
	("`__global_search`", "SELECT * FROM `__global_search`"), ("__UserSettings", "SELECT * FROM __UserSettings"),
	("tabSessions", "SELECT sid FROM tabSessions"), ("`tabSessions`", "SELECT * FROM `tabSessions`"), ("`TABSESSIONS`", "SELECT * FROM `TABSESSIONS`"),
	("tabsessions", "SELECT * FROM tabsessions"), ("`tabOAuth Bearer Token`", "SELECT * FROM `tabOAuth Bearer Token`"),
	("`tabOAuth Client`", "SELECT * FROM `tabOAuth Client`"), ("`taboauth authorization code`", "SELECT * FROM `taboauth authorization code`"),
	("`tabToken Cache`", "SELECT * FROM `tabToken Cache`"), ("`tabUser Social Login`", "SELECT * FROM `tabUser Social Login`"),
	("`tabEmail Account`", "SELECT * FROM `tabEmail Account`"), ("tabSingles", "SELECT value FROM tabSingles WHERE doctype = 'BC Settings'"),
	("`tabBC Share Link`", "SELECT * FROM `tabBC Share Link`"), ("`tabError Log`", "SELECT * FROM `tabError Log`"),
	("`tabSalary Slip`", "SELECT * FROM `tabSalary Slip`"), ("`tabSalary Structure Assignment`", "SELECT base FROM `tabSalary Structure Assignment`"),
	("`tabPayroll Entry`", "SELECT * FROM `tabPayroll Entry`"), ("`tabAdditional Salary`", "SELECT * FROM `tabAdditional Salary`"),
	("tabSalaryDay (ns / ketoan)", "SELECT luongthucnhan FROM tabSalaryDay"), ("`tabSalaryProduct`", "SELECT * FROM `tabSalaryProduct`"),
	("`tabSX Phieu Luong`", "SELECT * FROM `tabSX Phieu Luong`"), ("`tabSX Phieu Luong Chi Tiet`", "SELECT * FROM `tabSX Phieu Luong Chi Tiet`"),
	("bảng lương tự tạo", "SELECT * FROM `tabBang Luong Thang`"), ("bảng chấm công tự tạo", "SELECT * FROM `tabCham Cong`"),
	("`tabEmployee Education`", "SELECT * FROM `tabEmployee Education`"),
	("`tabEmployee External Work History`", "SELECT * FROM `tabEmployee External Work History`"),
	("`tabEmployee Internal Work History`", "SELECT * FROM `tabEmployee Internal Work History`"),
	("`tabNS Giay To` (CCCD)", "SELECT so FROM `tabNS Giay To`"),
	("UNION bảng cấm", "SELECT 1 UNION SELECT sid FROM tabSessions"), ("UNION ALL __Auth", "SELECT name FROM tabCustomer UNION ALL SELECT password FROM __Auth"),
	("bảng cấm trong CTE", "WITH a AS (SELECT * FROM `__Auth`) SELECT * FROM a"), ("bảng cấm trong bảng con", "SELECT * FROM (SELECT * FROM tabSessions) t"),
	("bảng cấm trong truy vấn vô hướng", "SELECT (SELECT sessiondata FROM tabSessions LIMIT 1)"),
	("bảng cấm trong IN", "SELECT name FROM tabCustomer WHERE name IN (SELECT user FROM tabSessions)"),
	("JOIN bảng lương", "SELECT c.name FROM `tabCustomer` c JOIN `tabSalary Slip` s ON s.employee = c.name"),
	("\"tabSessions\" kiểu ANSI", "SELECT * FROM \"tabSessions\""), ("bí danh bảng cấm", "SELECT s.sid FROM `tabSessions` AS s"),
	("FROM a, `__Auth`", "SELECT 1 FROM tabCustomer c, `__Auth` a"), ("char() + UNION bảng cấm",
		"SELECT name FROM tabCustomer WHERE name = CHAR(65) UNION SELECT sid FROM tabSessions"),
	("hex + bảng cấm", "SELECT 0x73656c656374 FROM tabSessions"),
	# ── luật 5: tabEmployee / tabUser
	("tabEmployee *", "SELECT * FROM tabEmployee"), ("`tabEmployee` *", "SELECT * FROM `tabEmployee`"), ("e.*", "SELECT e.* FROM tabEmployee e"),
	("`e`.*", "SELECT `e`.* FROM `tabEmployee` `e`"), ("e.* kèm JOIN", "SELECT x.name, e.* FROM tabCustomer x JOIN tabEmployee e ON 1 = 1"),
	("* khi JOIN Employee", "SELECT * FROM tabCustomer c JOIN tabEmployee e ON e.company = c.name"),
	("phép nhân khi có Employee", "SELECT e.name * 2 FROM tabEmployee e"),
	("cột CCCD", "SELECT custom_cccd FROM tabEmployee"), ("e.custom_cccd", "SELECT e.custom_cccd FROM tabEmployee e"),
	("`e`.`custom_cccd`", "SELECT `e`.`custom_cccd` FROM `tabEmployee` AS `e`"), ("tabEmployee.custom_cccd", "SELECT tabEmployee.custom_cccd FROM tabEmployee"),
	("cột cấm trong WHERE", "SELECT name FROM tabEmployee WHERE custom_cccd = '0123'"),
	("cột cấm trong ORDER BY", "SELECT name FROM tabEmployee ORDER BY date_of_birth"),
	("cột cấm trong hàm", "SELECT name FROM tabEmployee WHERE LEFT(cell_number, 3) = '090'"),
	("cột lương có dấu", "SELECT name, `custom_lương_cơ_bản` FROM tabEmployee"), ("e.ctc", "SELECT name FROM tabEmployee e WHERE e.ctc > 1000"),
	("cột cấm trong COUNT … WHERE", "SELECT COUNT(*) FROM tabEmployee WHERE gender = 'Female'"),
	("cột cấm trong GROUP BY", "SELECT name FROM tabEmployee GROUP BY bank_ac_no"),
	("cột cấm trong HAVING", "SELECT e.name FROM tabEmployee e HAVING MAX(e.personal_email) IS NOT NULL"),
	("NATURAL JOIN (khớp ngầm cột chung)", "SELECT e.name FROM tabEmployee e NATURAL JOIN `tabSales Invoice` x"),
	("NATURAL JOIN dò CCCD", "SELECT e.name FROM tabEmployee e NATURAL JOIN (SELECT 'x' AS custom_cccd) z"),
	("USING (cột cấm)", "SELECT e.name FROM tabEmployee e JOIN tabCustomer c USING (custom_cccd)"),
	("(tabEmployee) x", "SELECT x.custom_cccd FROM (tabEmployee) x"),
	("PARTITION (p) e", "SELECT e.custom_cccd FROM tabEmployee PARTITION (p0) e"),
	("`custom_cccd` trong `…`", "SELECT `custom_cccd` FROM tabEmployee"), ("\"custom_cccd\" kiểu ANSI", "SELECT \"custom_cccd\" FROM tabEmployee"),
	("bí danh trùng bảng khác", "SELECT si.custom_cccd FROM tabEmployee si"),
	("bí danh dùng lại ở tầng khác", "SELECT (SELECT si.custom_cccd FROM tabEmployee si LIMIT 1) AS x FROM `tabSales Invoice` si"),
	("cột cấm qua bảng con", "SELECT custom_cccd FROM (SELECT name, custom_cccd FROM tabEmployee) t"),
	("cột cấm qua CTE", "WITH e AS (SELECT name, date_of_birth FROM tabEmployee) SELECT name FROM e"),
	("cột chuẩn không cho phép (owner)", "SELECT name FROM tabEmployee WHERE owner = 'a'"),
	("UNION cột cấm", "SELECT name FROM tabEmployee UNION SELECT custom_cccd FROM tabEmployee"),
	("user_id so với owner", "SELECT e.name FROM tabEmployee e, `tabSales Invoice` s WHERE s.owner = e.user_id"),
	("tabUser *", "SELECT * FROM tabUser"), ("u.*", "SELECT u.* FROM tabUser u"), ("api_key", "SELECT api_key FROM tabUser"),
	("email trong WHERE", "SELECT name FROM tabUser WHERE email LIKE '%a%'"), ("u.full_name", "SELECT u.name, u.full_name FROM tabUser u"),
	("ORDER BY mobile_no", "SELECT name FROM `tabUser` ORDER BY mobile_no"), ("reset_password_key", "SELECT reset_password_key FROM tabUser"),
	("u.last_ip", "SELECT name FROM tabUser u WHERE u.last_ip = '1.2.3.4'"),
	("tabUser trong truy vấn con", "SELECT si.name FROM `tabSales Invoice` si WHERE si.owner IN (SELECT name FROM tabUser WHERE phone = '1')"),
	# ── soát chéo P3: bí danh Employee / User là từ khoá không cấm của MariaDB (END, FULL…) + CTE cùng tên
	("CTE `end` + bí danh end", "WITH `end` AS (SELECT 1 AS x) SELECT end.bank_ac_no FROM tabEmployee end"),
	("CTE `end` + AS end", "WITH `end` AS (SELECT 1 AS x) SELECT `end`.bank_ac_no FROM tabEmployee AS end"),
	("CTE full + bí danh full", "WITH full AS (SELECT 1 AS x) SELECT full.bank_ac_no FROM tabEmployee full"),
	("CTE offset + bí danh offset", "WITH offset AS (SELECT 1 AS x) SELECT offset.bank_ac_no FROM tabEmployee offset"),
	("CTE window + bí danh window", "WITH window AS (SELECT 1 AS x) SELECT window.bank_ac_no FROM tabEmployee window"),
	("CTE + (tabEmployee) e", "WITH e AS (SELECT 1 AS x) SELECT e.bank_ac_no FROM (tabEmployee) e"),
	("CTE + bí danh \"e\"", "WITH e AS (SELECT 1 AS x) SELECT e.bank_ac_no FROM tabEmployee \"e\""),
	("CTE outer + tabUser outer", "WITH outer AS (SELECT 1 AS x) SELECT outer.api_key FROM tabUser AS outer"),
	("bảng con + bí danh end trùng", "SELECT end.api_key FROM (SELECT 1 AS k) end, tabUser AS end"),
	("FOR SYSTEM_TIME với Employee", "SELECT e.bank_ac_no FROM tabEmployee FOR SYSTEM_TIME ALL e"),
	# ── soát chéo P3: bảng chép lại dữ liệu bảng khác (diff / ảnh chụp / log / khoá)
	("tabVersion (diff Employee)", "SELECT ref_doctype, data FROM tabVersion WHERE ref_doctype = 'Employee'"),
	("`tabDeleted Document`", "SELECT data FROM `tabDeleted Document` WHERE deleted_doctype = 'Salary Slip'"),
	("`tabWebhook Header`", "SELECT `key`, value FROM `tabWebhook Header`"), ("`tabWebhook`", "SELECT * FROM `tabWebhook`"),
	("`tabWebhook Data`", "SELECT * FROM `tabWebhook Data`"),
	("`tabBank Account`", "SELECT party, bank_account_no FROM `tabBank Account` WHERE party_type = 'Employee'"),
	("tabComment", "SELECT content FROM tabComment"), ("tabCommunication", "SELECT content FROM tabCommunication"),
	("`tabCommunication Link`", "SELECT * FROM `tabCommunication Link`"), ("`tabActivity Log`", "SELECT * FROM `tabActivity Log`"),
	("`tabAccess Log`", "SELECT * FROM `tabAccess Log`"), ("`tabData Import`", "SELECT * FROM `tabData Import`"),
	("`tabData Import Log`", "SELECT * FROM `tabData Import Log`"), ("`tabPrepared Report`", "SELECT * FROM `tabPrepared Report`"),
	("`tabSubmission Queue`", "SELECT * FROM `tabSubmission Queue`"), ("`tabScheduled Job Log`", "SELECT * FROM `tabScheduled Job Log`"),
	("`tabNotification Log`", "SELECT * FROM `tabNotification Log`"),
	# ── soát chéo P3: thoát lớp bọc bằng ')' thừa; số dính từ khoá (MariaDB tách 1e0 + PROCEDURE)
	("')' thừa thoát lớp bọc", "SELECT 1) AS a JOIN (SELECT name FROM tabCustomer"), ("'(' thừa", "SELECT (1"),
	("1e0procedure", "SELECT name FROM tabCustomer WHERE 1=1e0procedure analyse()"),
	("1.5union", "SELECT 1 FROM tabCustomer WHERE 1=1.5union SELECT 2"),
]

print(f"3. Bộ câu hợp lệ ({len(VALID)})")
c("≥ 60 câu hợp lệ", len(VALID) >= 60, len(VALID))
bi_chan = []
for q in VALID:
	ok, ly_do, sach = sqlguard.check(q)
	if not ok or not sach or sach.endswith(";"):
		bi_chan.append((q[:70], ly_do))
c("mọi câu hợp lệ được nhận (câu đã gọt không còn ';')", not bi_chan, bi_chan)
c("câu đã gọt = bỏ khoảng trắng hai đầu và ';' cuối", sqlguard.check("   \n SELECT name FROM `tabCustomer`   ;  ")[2]
	== "SELECT name FROM `tabCustomer`")

print(f"4. Bộ câu tấn công ({len(ATTACK)})")
c("≥ 120 câu tấn công", len(ATTACK) >= 120, len(ATTACK))
lot = []
for nhan, q in ATTACK:
	ok, ly_do, sach = sqlguard.check(q)
	if ok or not ly_do or sach:
		lot.append((nhan, q[:80]))
c("mọi câu tấn công bị từ chối (ok = False, có lý do, không trả câu)", not lot, lot)
dai = [(n, sqlguard.check(q)[1]) for n, q in ATTACK if len(sqlguard.check(q)[1]) > 300]
c("lý do từ chối ngắn (≤ 300 ký tự — kể cả danh sách cột được dùng)", not dai, dai)
c("check(None) / số → từ chối, không ném lỗi", sqlguard.check(None)[0] is False and sqlguard.check(5)[0] is False)
# columns truyền vào được gộp với danh sách tĩnh
c("cột lạ của tabEmployee chỉ biết lúc chạy (columns=) bị chặn",
	sqlguard.check("SELECT cot_moi_ns FROM tabEmployee")[0] is True
	and sqlguard.check("SELECT cot_moi_ns FROM tabEmployee", {"tabEmployee": {"cot_moi_ns", "name"}})[0] is False)
c("columns= không nới danh sách tĩnh (cột cấm tĩnh vẫn chặn khi columns thiếu nó)",
	sqlguard.check("SELECT custom_cccd FROM tabEmployee", {"tabEmployee": {"name"}})[0] is False)
c("ALLOWED_COLUMNS đúng spec (User)", sqlguard.ALLOWED_COLUMNS["tabUser"] == frozenset({"name", "enabled", "user_type",
	"creation", "last_login", "last_active"}))
c("ALLOWED_COLUMNS Employee: mã, tên, phòng ban, chức danh, chi nhánh, trạng thái, vào / nghỉ, công ty, loại HĐ",
	{"name", "employee_name", "department", "designation", "branch", "status", "date_of_joining", "relieving_date",
	"company"} <= sqlguard.ALLOWED_COLUMNS["tabEmployee"] and not ({"custom_cccd", "ctc", "date_of_birth",
	"cell_number", "personal_email", "bank_ac_no", "user_id"} & sqlguard.ALLOWED_COLUMNS["tabEmployee"]))

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("5. wrap / doctype_allowed / grants_ok")
c("wrap: đúng mẫu luật 6", sqlguard.wrap("SELECT name FROM `tabCustomer`") ==
	"SET STATEMENT max_statement_time=10 FOR SELECT * FROM (SELECT name FROM `tabCustomer`) AS _t LIMIT 200")
c("wrap: ORDER BY tầng ngoài không LIMIT → LIMIT bên trong (giữ thứ tự)",
	sqlguard.wrap("SELECT a FROM t ORDER BY a DESC", limit=201) ==
	"SET STATEMENT max_statement_time=10 FOR SELECT * FROM (SELECT a FROM t ORDER BY a DESC LIMIT 201) AS _t LIMIT 201")
c("wrap: ORDER BY trong ngoặc / đã có LIMIT → không thêm", "LIMIT 200)" not in sqlguard.wrap(
	"SELECT GROUP_CONCAT(a ORDER BY a) FROM t") and sqlguard.wrap("SELECT a FROM t ORDER BY a LIMIT 3").count("LIMIT") == 2)
c("wrap: tham số giờ / dòng", sqlguard.wrap("SELECT 1;", limit=5, seconds=3) ==
	"SET STATEMENT max_statement_time=3 FOR SELECT * FROM (SELECT 1) AS _t LIMIT 5")
for dt, ok in (("Sales Invoice", True), ("Employee", True), ("User", True), ("Customer", True), ("Sessions", False),
		("Salary Slip", False), ("Payroll Entry", False), ("SalaryDay", False), ("SX Phieu Luong Ngay", False),
		("Employee Education", False), ("NS Giay To", False), ("OAuth Client", False), ("Error Log", False),
		("BC Share Link", False), ("Version", False), ("Deleted Document", False), ("Webhook Header", False),
		("Bank Account", False), ("Communication", False), ("", False), (None, False)):
	c(f"doctype_allowed({dt!r}) = {ok}", sqlguard.doctype_allowed(dt) is ok)
U = "GRANT USAGE ON *.* TO `bc_ai_ro`@`localhost` IDENTIFIED BY PASSWORD '*ABC'"
for lines, ok, mo_ta in (
		([U, "GRANT SELECT ON `site_db`.* TO `bc_ai_ro`@`localhost`"], True, "USAGE + SELECT trên CSDL site"),
		([U, "GRANT SELECT, SHOW VIEW ON `site_db`.* TO `bc_ai_ro`@`localhost`"], True, "+ SHOW VIEW"),
		([U, "GRANT SELECT ON `site\\_db`.* TO `bc_ai_ro`@`localhost`"], True, "tên CSDL đã thoát \\_"),
		([U, "GRANT SELECT (`name`, `status`) ON `site_db`.`tabX` TO `bc_ai_ro`@`localhost`"], True, "SELECT theo cột"),
		([U], True, "chỉ USAGE"),
		([U, 'GRANT SELECT ON "site_db".* TO "bc_ai_ro"@"localhost"'], True, 'tên trong "…" (ANSI_QUOTES)'),
		([U, "GRANT SELECT, INSERT ON `site_db`.* TO `bc_ai_ro`@`localhost`"], False, "INSERT"),
		([U, "GRANT ALL PRIVILEGES ON `site_db`.* TO `bc_ai_ro`@`localhost`"], False, "ALL"),
		(["GRANT SELECT ON *.* TO `bc_ai_ro`@`localhost`"], False, "SELECT *.*"),
		([U, "GRANT SELECT ON `site%`.* TO `bc_ai_ro`@`localhost`"], False, "mẫu %"),
		([U, "GRANT SELECT ON `other_db`.* TO `bc_ai_ro`@`localhost`"], False, "CSDL khác"),
		([U, "GRANT SELECT ON `site_db`.* TO `bc_ai_ro`@`localhost` WITH GRANT OPTION"], False, "WITH GRANT OPTION"),
		([U, "GRANT `role_rw` TO `bc_ai_ro`@`localhost`"], False, "vai trò"),
		([U, "SET DEFAULT ROLE `role_rw` FOR `bc_ai_ro`@`localhost`"], False, "SET DEFAULT ROLE"),
		([U, "GRANT PROXY ON ''@'%' TO 'bc_ai_ro'@'localhost'"], False, "PROXY"),
		([U, "GRANT EXECUTE ON PROCEDURE `site_db`.`p` TO `bc_ai_ro`@`localhost`"], False, "EXECUTE thủ tục"),
		([U, "GRANT SELECT, CREATE TEMPORARY TABLES ON `site_db`.* TO `bc_ai_ro`@`localhost`"], False, "TEMPORARY"),
		([U, "GRANT FILE ON *.* TO `bc_ai_ro`@`localhost`"], False, "FILE"),
		([], False, "không dòng nào")):
	c(f"grants_ok: {mo_ta} → {ok}", sqlro.grants_ok(lines, "site_db") is ok, lines)

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
print("6. MariaDB thật")
reset(only={"Sales Invoice", "Sales Invoice Item", "Customer", "Supplier", "Item", "Bin", "GL Entry", "Employee", "User",
	"Department", "Warehouse", "Stock Ledger Entry", "Purchase Invoice", "Purchase Invoice Item"})
for u in (RO, RW):
	rsql(f"DROP USER IF EXISTS '{u}'@'localhost'")
rsql(f"CREATE USER '{RO}'@'localhost' IDENTIFIED BY %s", (PW_RO,))
rsql(f"GRANT SELECT, SHOW VIEW ON `{DB}`.* TO '{RO}'@'localhost'")
rsql(f"CREATE USER '{RW}'@'localhost' IDENTIFIED BY %s", (PW_RW,))
rsql(f"GRANT SELECT, INSERT ON `{DB}`.* TO '{RW}'@'localhost'")
BAM = [r[0] for r in rsql(f"SHOW GRANTS FOR '{RO}'@'localhost'") + rsql(f"SHOW GRANTS FOR '{RW}'@'localhost'")]
BAM = [s[s.index("PASSWORD '") + 10:].rstrip("'") for s in BAM if "PASSWORD '" in s]   # băm mật khẩu trong SHOW GRANTS
BI_MAT = [PW_RO, PW_RW] + BAM
ERR_TEXT: list = []          # mọi lỗi / traceback / stderr gom lại để soát bí mật


def ghi_loi(e):
	ERR_TEXT.append(repr(e) + str(e) + repr(getattr(e, "args", ())) + repr(getattr(e, "reason", "")))
	ERR_TEXT.append("".join(traceback.format_exception(type(e), e, e.__traceback__)))


try:
	frappe.db.sql(f"ALTER TABLE `tabEmployee` ADD COLUMN `employment_type` varchar(140), "
		"ADD COLUMN `cot_moi_ns` varchar(140)")            # HRMS + một Custom Field chỉ có trên site
	frappe.db.sql(f"CREATE TABLE `{BIG}` (x int, nhan varchar(400), tien decimal(21,9), ngay date, gio datetime)")
	frappe.db.sql(f"INSERT INTO `{BIG}` (x, nhan, tien, ngay, gio) WITH RECURSIVE n AS (SELECT 1 AS i UNION ALL "
		"SELECT i + 1 FROM n WHERE i < 500) SELECT i, REPEAT('Đ', 300), i * 1000.5, '2026-11-05', '2026-11-05 08:30:00' "
		"FROM n")
	for i in range(1, 8):
		insert("Customer", name=f"KH {i}", customer_name=f"Khách {i}", customer_group="NPP", territory="HN")
		insert("Sales Invoice", name=f"SINV-000{i}", customer=f"KH {i % 3}", grand_total=1_000_000 * (i * 7 % 5 + 1),
			outstanding_amount=100 * i, posting_date=f"2026-11-0{i}", due_date="2026-11-01", docstatus=1, is_return=0,
			base_net_total=900_000 * i, status="Overdue" if i % 2 else "Paid", remarks="ghi chú")
		insert("Sales Invoice Item", parent=f"SINV-000{i}", parenttype="Sales Invoice", parentfield="items",
			item_code=f"IT{i}", qty=i, amount=1000 * i)
	insert("Employee", name="HR-EMP-0001", employee_name="Nguyễn Văn A", status="Active", department="SX",
		date_of_joining="2026-02-01", custom_cccd="012345678901", company="C", first_name="A", gender="Male",
		date_of_birth="1990-01-01")
	insert("User", name="a@example.com", first_name="A", email="a@example.com", enabled=1, user_type="System User")

	frappe.conf.update({"db_name": DB, "db_socket": SOCK})
	frappe.conf.pop("bc_ai_ro_user", None)
	frappe.conf.pop("bc_ai_ro_password", None)
	c("available(): chưa khai → False", sqlro.available() is False)
	frappe.conf["bc_ai_ro_user"] = RO
	c("available(): thiếu mật khẩu → False", sqlro.available() is False)
	frappe.conf["bc_ai_ro_password"] = ""
	c("available(): mật khẩu rỗng → False", sqlro.available() is False)
	try:
		with sqlro.ReadOnly():
			pass
		c("chưa khai đủ → NotReadOnly", False)
	except sqlro.NotReadOnly as e:
		ghi_loi(e)
		c("chưa khai đủ → NotReadOnly", True)
	frappe.conf["bc_ai_ro_password"] = PW_RO
	c("available(): đủ hai giá trị → True (không nối)", sqlro.available() is True)

	err = io.StringIO()
	with contextlib.redirect_stderr(err):
		# ── tài khoản chỉ đọc
		with sqlro.ReadOnly() as ro:
			r = ro.select("SELECT name, customer, grand_total FROM `tabSales Invoice` WHERE docstatus = 1 ORDER BY name")
			c("chỉ đọc: SELECT chạy được, đúng cột", r["columns"] == ["name", "customer", "grand_total"] and len(r["rows"]) == 7,
				r)
			c("chỉ đọc: kết quả chỉ có columns / rows / cut", set(r) == {"columns", "rows", "cut"} and r["cut"] is False, r)
			c("Decimal → float", isinstance(r["rows"][0][2], float) and r["rows"][0][2] == 3_000_000.0, r["rows"][0])
			r = ro.select(f"SELECT ngay, gio, tien FROM `{BIG}` WHERE x = 3")
			c("ngày / giờ → ISO, Decimal → float", r["rows"] == [["2026-11-05", "2026-11-05T08:30:00", 3001.5]], r)
			r = ro.select(f"SELECT x FROM `{BIG}`")
			c("LIMIT 200: 500 dòng → 200 dòng, cut", len(r["rows"]) == 200 and r["cut"] is True, (len(r["rows"]), r["cut"]))
			r = ro.select(f"SELECT x FROM `{BIG}` WHERE x <= 200")
			c("đúng 200 dòng → không cut", len(r["rows"]) == 200 and r["cut"] is False, (len(r["rows"]), r["cut"]))
			r = ro.select(f"SELECT x FROM `{BIG}` ORDER BY x DESC")
			c("ORDER BY không LIMIT vẫn giữ thứ tự (500, 499, …)", [v[0] for v in r["rows"][:3]] == [500, 499, 498],
				r["rows"][:3])
			r = ro.select("SELECT customer, SUM(grand_total) AS tong FROM `tabSales Invoice` GROUP BY customer "
				"ORDER BY tong DESC")
			c("top theo tổng: thứ tự giảm dần", [v[1] for v in r["rows"]] == sorted((v[1] for v in r["rows"]), reverse=True)
				and len(r["rows"]) == 3, r["rows"])
			r = ro.select(f"SELECT x, nhan FROM `{BIG}` WHERE x = 1")
			c("ô chuỗi cắt ≤ 200 ký tự, cut", len(r["rows"][0][1]) == 200 and r["rows"][0][1].endswith("…") and r["cut"],
				(len(r["rows"][0][1]), r["cut"]))
			r = ro.select(f"SELECT nhan AS a, nhan AS b, x FROM `{BIG}` WHERE x <= 150")
			n = len(json.dumps(r, ensure_ascii=False))
			c("tổng ≤ 40.000 ký tự JSON, cut", n <= 40_000 + 200 and r["cut"] and 0 < len(r["rows"]) < 150,
				(n, len(r["rows"])))
			c("mọi kết quả JSON được (không Decimal / date)", bool(json.dumps(r)))
			# câu hợp lệ của bộ thử chạy được thật
			hong = []
			for q in VALID:
				try:
					ro.select(q)
				except sqlro.SqlRefused as e:
					hong.append((q[:60], e.reason))
			c(f"mọi câu hợp lệ ({len(VALID)}) chạy THẬT được trên bảng v16 qua tài khoản chỉ đọc", not hong, hong)
			# câu tấn công bị chặn trước khi tới CSDL
			lot = []
			for nhan, q in ATTACK:
				try:
					ro.select(q)
					lot.append(nhan)
				except sqlro.SqlRefused as e:
					ghi_loi(e)
			c("select(): mọi câu tấn công → SqlRefused", not lot, lot)
			# cột thật của bảng (cot_moi_ns chỉ có trên site) gộp vào luật 5
			try:
				ro.select("SELECT cot_moi_ns FROM tabEmployee")
				c("cột Employee chỉ có trên site (đọc từ CSDL lúc mở) bị chặn", False)
			except sqlro.SqlRefused as e:
				c("cột Employee chỉ có trên site (đọc từ CSDL lúc mở) bị chặn", "cot_moi_ns" in e.reason, e.reason)
			# lỗi SQL → lý do ngắn
			for q, can, mo_ta in (("SELECT khong_co FROM `tabCustomer`", "khong_co", "cột sai"),
					("SELECT 1 FROM `tabKhong Co`", "tabKhong Co", "bảng sai"),
					("SELECT name, name FROM `tabCustomer`", "bí danh", "trùng tên cột"),
					("SELECT FROM WHERE", "cú pháp", "sai cú pháp")):
				try:
					ro.select(q)
					c(f"lỗi SQL ({mo_ta}) → SqlRefused", False)
				except sqlro.SqlRefused as e:
					ghi_loi(e)
					c(f"lỗi SQL ({mo_ta}) → SqlRefused, lý do ngắn có '{can}'", can in e.reason and len(e.reason) < 120
						and "Traceback" not in e.reason and e.__cause__ is None, e.reason)
			# quá giờ: tích chéo 500⁴ = 62,5 tỷ dòng
			t0 = time.time()
			try:
				ro.select(f"SELECT COUNT(*) FROM `{BIG}` a, `{BIG}` b, `{BIG}` c, `{BIG}` d WHERE a.x + b.x * c.x < d.x")
				c("max_statement_time=10 cắt câu nặng", False, time.time() - t0)
			except sqlro.SqlRefused as e:
				ghi_loi(e)
				dt = time.time() - t0
				c("max_statement_time=10 cắt câu nặng (SqlRefused 'quá 10 giây', 9–16 s)", "quá 10 giây" in e.reason
					and 9 <= dt <= 16, (e.reason, round(dt, 1)))
			r = ro.select("SELECT 1 AS mot")
			c("kết nối dùng tiếp được sau câu quá giờ", r["rows"] == [[1]], r)
			# phiên đã chốt
			cur = ro._conn.cursor()
			cur.execute("SELECT @@SESSION.sql_mode, @@SESSION.tx_read_only, @@SESSION.max_statement_time")
			mode, txro, mst = cur.fetchone()
			c("phiên: không ANSI_QUOTES / NO_BACKSLASH_ESCAPES, READ ONLY, max_statement_time 10",
				"ANSI_QUOTES" not in mode and "NO_BACKSLASH" not in mode and int(txro) == 1 and float(mst) == 10, (mode, txro, mst))
			# máy chủ có sql_mode mặc định ANSI_QUOTES + NO_BACKSLASH_ESCAPES (giả bằng init_command): phiên vẫn chốt lại
			import frappe.database as fdb
			fdb.INIT_COMMAND = "SET SESSION sql_mode = 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'"
			try:
				with sqlro.ReadOnly() as ro3:
					cur3 = ro3._conn.cursor()
					cur3.execute("SELECT @@SESSION.sql_mode")
					mode3 = cur3.fetchone()[0]
					r3 = ro3.select("SELECT \"tabCustomer\" AS a, 'x\\'y' AS b")
				c("máy chủ mặc định ANSI_QUOTES / NO_BACKSLASH_ESCAPES: phiên vẫn đặt lại sql_mode, \"…\" là chuỗi",
					"ANSI_QUOTES" not in mode3 and "NO_BACKSLASH" not in mode3 and r3["rows"] == [["tabCustomer", "x'y"]],
					(mode3, r3))
			except Exception as e:  # noqa: BLE001
				ghi_loi(e)
				c("máy chủ mặc định ANSI_QUOTES / NO_BACKSLASH_ESCAPES: phiên vẫn đặt lại sql_mode", False, repr(e)[:200])
			finally:
				fdb.INIT_COMMAND = None
			# câu ghi LỌT lớp soát (chạy thô trên kết nối) vẫn hỏng
			truoc = frappe.db.sql("SELECT COUNT(*) FROM `tabCustomer`")[0][0]
			for q in ("INSERT INTO `tabCustomer` (name) VALUES ('LOT-1')", "UPDATE `tabCustomer` SET customer_name = 'x'",
					"DELETE FROM `tabCustomer`", "CREATE TABLE `tabP3F Lot` (a int)", "DROP TABLE `tabCustomer`",
					f"SELECT 1 INTO OUTFILE '/tmp/p3f_lot_{os.getpid()}.txt'"):
				try:
					cur.execute(q)
					c(f"lệnh thô '{q[:30]}…' hỏng trên tài khoản chỉ đọc", False)
				except Exception as e:  # noqa: BLE001
					c(f"lệnh thô '{q[:30]}…' hỏng trên tài khoản chỉ đọc", e.args and e.args[0] in (1142, 1044, 1045, 1792,
						1227), e.args)
			cur.close()
			c("dữ liệu không đổi sau các lệnh ghi thô", frappe.db.sql("SELECT COUNT(*) FROM `tabCustomer`")[0][0] == truoc
				and not frappe.db.sql("SHOW TABLES LIKE 'tabP3F Lot'") and not os.path.exists(f"/tmp/p3f_lot_{os.getpid()}.txt"))
			ro_conn = ro._conn
		c("ra khỏi khối: kết nối đã đóng", ro._conn is None and not ro_conn.open)
		time.sleep(0.3)
		c("ra khỏi khối: máy chủ không còn phiên của tài khoản chỉ đọc", not rsql(
			"SELECT id FROM information_schema.processlist WHERE user = %s", (RO,)))
		try:
			ro.select("SELECT 1")
			c("select() sau khi đóng → SqlRefused", False)
		except sqlro.SqlRefused:
			c("select() sau khi đóng → SqlRefused", True)
		ro.__exit__(None, None, None)
		c("__exit__ lần hai không ném lỗi", True)
		# lỗi trong khối vẫn ném ra, kết nối vẫn đóng
		try:
			with sqlro.ReadOnly() as ro2:
				raise KeyError("trong khối")
		except KeyError:
			c("lỗi trong khối được ném tiếp (không nuốt), kết nối đóng", ro2._conn is None)

		# ── tài khoản có quyền ghi / quyền rộng → không dùng
		for cap, grant, mo_ta in (
				(None, None, "SELECT + INSERT"),
				(f"REVOKE INSERT ON `{DB}`.* FROM '{RW}'@'localhost'", f"GRANT SELECT ON *.* TO '{RW}'@'localhost'", "SELECT *.*"),
				(f"REVOKE SELECT ON *.* FROM '{RW}'@'localhost'", f"GRANT SELECT ON `{DB}`.* TO '{RW}'@'localhost' WITH GRANT OPTION",
					"WITH GRANT OPTION"),
				(f"REVOKE GRANT OPTION ON `{DB}`.* FROM '{RW}'@'localhost'", f"GRANT DELETE ON `{DB}`.`tabCustomer` TO '{RW}'@'localhost'",
					"DELETE trên một bảng")):
			if cap:
				rsql(cap)
			if grant:
				rsql(grant)
			frappe.conf.update({"bc_ai_ro_user": RW, "bc_ai_ro_password": PW_RW})
			try:
				with sqlro.ReadOnly() as x:
					x.select("SELECT 1")
				c(f"tài khoản {mo_ta} → NotReadOnly", False)
			except sqlro.NotReadOnly as e:
				ghi_loi(e)
				c(f"tài khoản {mo_ta} → NotReadOnly (trước mọi câu)", "quyền" in str(e), str(e))
		# sai mật khẩu
		frappe.conf.update({"bc_ai_ro_user": RO, "bc_ai_ro_password": PW_RO + "x"})
		try:
			with sqlro.ReadOnly():
				pass
			c("sai mật khẩu → NotReadOnly", False)
		except sqlro.NotReadOnly as e:
			ghi_loi(e)
			c("sai mật khẩu → NotReadOnly, không chuỗi lỗi của driver, không xâu chuỗi lỗi gốc",
				"Access denied" not in str(e) and e.__cause__ is None and e.__suppress_context__, str(e))
		frappe.conf.update({"bc_ai_ro_user": RO, "bc_ai_ro_password": PW_RO, "db_name": DB + "_khong_co"})
		try:
			with sqlro.ReadOnly():
				pass
			c("CSDL khác tên site → NotReadOnly", False)
		except sqlro.NotReadOnly as e:
			ghi_loi(e)
			c("CSDL khác tên site → NotReadOnly", True)
		frappe.conf["db_name"] = DB
	ERR_TEXT.append(err.getvalue())
	ERR_TEXT.append(repr(frappe.LOGGED))
	ERR_TEXT.append(json.dumps(frappe.cache().store, default=str))
	lo = [s for s in BI_MAT if any(s in t for t in ERR_TEXT)]
	c(f"không mật khẩu / băm mật khẩu nào trong {len(ERR_TEXT)} lỗi, traceback, stderr, log, cache", not lo and len(BAM) == 2,
		(len(lo), len(BAM)))
	c("không lượt nối mạng nào", not BLOCKED, BLOCKED)
finally:
	for u in (RO, RW):
		rsql(f"DROP USER IF EXISTS '{u}'@'localhost'")
	rsql(f"DROP DATABASE IF EXISTS `{DB}`")
	frappe.db.conn = None
c("đã xoá hai tài khoản bộ thử", not rsql("SELECT user FROM mysql.user WHERE user IN (%s, %s)", (RO, RW)))
c.done()
