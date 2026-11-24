# -*- coding: utf-8 -*-
"""bc.ai.sqlguard — soát câu SELECT do mô hình viết trước khi chạy (SPEC_bc_ai_p3 §2.2, luật 1–6). Hàm THUẦN: chỉ thư
viện chuẩn, không đọc CSDL, không đọc cấu hình.

Lớp chặn thật là tài khoản MariaDB chỉ đọc (bc.ai.sqlro); đây là lớp thứ hai và NGHIÊNG VỀ PHÍA CHẶN: chặn nhầm một
câu hợp lệ thì mô hình nhận lời từ chối và viết lại; lọt một câu mới là lỗi.

Cách soát: một bộ TÁCH TỪ nhỏ (lexer) chia câu thành chuỗi ('…' và "…", có thoát bằng \\ và nháy đôi), tên trong
dấu `…` (`` là một dấu `), số, từ, dấu câu — mọi quyết định dựa trên TỪ đã tách, không dùng regex trên chữ thô. Nhờ
vậy chữ cấm nằm trong chuỗi ('Đơn bị DELETE') không bị bắt nhầm, còn tên bảng viết trong `…` vẫn bị bắt.

Luật (spec §2.2):
1. Một câu duy nhất, ≤ 4.000 ký tự, bắt đầu bằng SELECT hoặc WITH (cho phép mở ngoặc trước). Không chú thích (--, #,
   /* */, /*! */ — gặp ở đâu ngoài chuỗi cũng chặn, kể cả "*/" lẻ), không ';' trừ đúng một dấu ở cuối, không biến
   (@x, @@x). Ký tự lạ ngoài chuỗi (: ? { } [ ] \\) cũng chặn. Chuỗi / tên `…` không đóng → chặn.
2. Từ khoá ghi / điều khiển và hàm cấm (TU_CAM, HAM_CAM) ở bất kỳ đâu ngoài chuỗi. Tên `…` trùng hàm cấm đứng trước
   '(' cũng chặn.
3. CSDL khác (information_schema, mysql, performance_schema, sys) — tên ở bất kỳ vị trí nào; tên có tiền tố CSDL:
   chuỗi a.b.c, "FROM / JOIN x.y", hoặc x.y mà y là tên bảng (tab… / __…).
4. Bảng cấm: BANG_CAM (đích danh), mọi bảng __… (bảng hệ thống của Frappe: __Auth, __global_search…), tên bảng tab…
   có chữ lương (MAU_LUONG) hoặc bắt đầu bằng TIEN_TO_CAM (tabOAuth…, tabSalary…, tabPayroll…, bảng con / bảng
   phụ của Employee). So không phân biệt hoa thường, viết trần hay trong `…`. Tên bảng nằm trong chuỗi '…' không phải
   tham chiếu bảng; riêng chuỗi "…" (MariaDB có chế độ ANSI_QUOTES biến "…" thành tên) bằng đúng tên bảng cấm thì
   vẫn chặn.
5. tabEmployee / tabUser: câu có nhắc bảng này thì không được dùng '*' (trừ COUNT(*)), không NATURAL JOIN, và mọi
   tên cột của bảng đó ngoài ALLOWED_COLUMNS bị chặn ở mọi vị trí (SELECT, WHERE, ORDER BY, trong hàm, USING…). Cột
   viết kèm bí danh (e.x): bí danh của Employee / User → x phải nằm trong danh sách cho phép; bí danh chắc chắn của
   bảng / bảng tạm khác → bỏ qua; bí danh không rõ → soát như cột trần.
6. wrap(): SET STATEMENT max_statement_time=10 FOR SELECT * FROM (<câu>) AS _t LIMIT 200. MariaDB bỏ ORDER BY của
   bảng con không có LIMIT, nên câu có ORDER BY ở tầng ngoài mà không LIMIT được thêm "LIMIT <limit>" bên trong để
   giữ thứ tự.
"""

from __future__ import annotations

import unicodedata

MAX_LEN = 4000

# Luật 2 — từ khoá ghi / điều khiển (spec) + vài từ cùng họ (không thể có trong một câu SELECT đọc số liệu).
TU_CAM = frozenset({
	"insert", "update", "delete", "replace", "alter", "drop", "create", "truncate", "grant", "revoke", "set", "call",
	"do", "handler", "load", "lock", "unlock", "rename", "into", "prepare", "execute", "use",
	# thêm: ghi file / thủ tục / điều khiển phiên, giao dịch, máy chủ
	"outfile", "dumpfile", "procedure", "deallocate", "kill", "shutdown", "flush", "reset", "purge", "install",
	"uninstall", "binlog", "signal", "resignal", "declare", "begin", "commit", "rollback", "savepoint", "xa", "show",
	"describe", "explain", "share", "nextval", "setval", "lastval",
	"table",  # UNION TABLE tabEmployee: đọc mọi cột không cần '*'
})
# Luật 2 — hàm cấm (spec) + hàm chờ / khoá cùng họ.
HAM_CAM = frozenset({
	"sleep", "benchmark", "load_file", "get_lock", "release_lock", "release_all_locks", "is_free_lock", "is_used_lock",
	"master_pos_wait", "master_gtid_wait", "source_pos_wait", "wait_for_executed_gtid_set",
	"wait_until_sql_thread_after_gtids",
})
# Luật 3.
CSDL_CAM = frozenset({"information_schema", "mysql", "performance_schema", "sys"})

# Luật 4 — đích danh (chữ thường). Bảng lương của app ns / ketoan / sx: SalaryDay (DocType tạo trên Desk, ns + ketoan
# payroll.js đọc), SalaryProduct (app lam-luong cũ, ns + ketoan đọc), SX Phieu Luong + 3 bảng con (app sx). Bảng con
# của Employee: Employee Education / External Work History / Internal Work History (ERPNext v16 employee.json) và
# NS Giay To (app ns, Custom Field ns_giay_to trên Employee — số CCCD, BHXH).
BANG_CAM = frozenset({
	"tabsessions", "tabtoken cache", "tabuser social login", "tabemail account", "tabsingles", "tabbc share link",
	"taberror log", "tabadditional salary",
	"tabsalaryday", "tabsalaryproduct", "tabsx phieu luong", "tabsx phieu luong chi tiet", "tabsx phieu luong ngay",
	"tabsx phieu luong phat",
	"tabemployee education", "tabemployee external work history", "tabemployee internal work history",
	"tabns giay to",
	# thêm: bảng có thể giữ thông tin đăng nhập / nội dung thô của tích hợp, thư đi
	"tabuser email", "tabintegration request", "tabwebhook request log", "tabemail queue",
	"tabemail queue recipient", "tabsocial login key", "tabconnected app", "taboauth bearer token",
	"tabgratuity", "tabretention bonus", "tabincome tax slab", "tabtaxable salary slab",
	# thêm (soát chéo P3): bảng CHÉP LẠI dữ liệu của bảng khác — ảnh chụp / bản diff / nội dung tự do. Version giữ diff
	# mọi lần sửa Employee / Salary Slip (số TK, lương), Deleted Document giữ nguyên JSON chứng từ đã xoá (phiếu lương),
	# Comment / Communication / log giữ chữ tự do và thư, Prepared Report / Submission Queue / Data Import giữ kết quả
	# hoặc dữ liệu nhập của báo cáo / tác vụ khác; Bank Account giữ số TK nhân viên; Webhook* giữ khoá gọi API.
	"tabversion", "tabdeleted document", "tabbank account", "tabcomment", "tabactivity log", "tabaccess log",
	"tabprepared report", "tabsubmission queue", "tabscheduled job log", "tabnotification log", "tabunhandled email",
	"tabsms log",
})
# Tiền tố bảng cấm (chữ thường). "tabemployee " (có dấu cách): mọi bảng con / bảng phụ của Employee (tabEmployee
# thì được, có danh sách cột riêng).
TIEN_TO_CAM = ("taboauth", "tabsalary", "tabpayroll", "tabemployee ", "tabsx phieu luong", "tabwebhook",
	"tabcommunication", "tabdata import")
# Chữ lương trong tên bảng tab… (chữ thường): bảng lương / chấm công tự tạo trên site.
MAU_LUONG = ("salary", "payroll", "luong", "lương", "chamcong", "cham cong", "chấm công")

# Luật 4b — lớp CẤU TRÚC (không phụ thuộc danh sách tên ở trên): mọi bảng `tab…` trong câu phải là bảng của một DocType
# có trên site, và DocType đó không thuộc phân hệ dưới đây. Danh sách tên luôn sót (bản sao, nhật ký, cấu hình tích
# hợp…); phân hệ thì không: bảng hệ thống / tích hợp / thư / nhân sự bị chặn cả khối. Chạy ở bc.ai.sqlro (cần danh mục
# DocType của site) qua tables() + module_allowed(). Bảng có danh sách cột riêng (ALLOWED_COLUMNS: tabEmployee,
# tabUser) được miễn luật phân hệ — luật 5 đã quản cột của chúng.
MODULE_CAM = frozenset({
	"core", "desk", "email", "integrations", "website", "automation", "custom", "printing", "social", "workflow",
	"portal", "telephony", "contacts",        # Frappe: hệ thống, thư, tích hợp, địa chỉ / người liên hệ
	"hr", "payroll",                          # HRMS
	"ns", "misa integration",                 # app của công ty: nhân sự (hồ sơ cá nhân), tích hợp hoá đơn (nhật ký thô)
})

# Luật 5 — cột được dùng.
ALLOWED_COLUMNS = {
	"tabEmployee": frozenset({
		"name", "employee", "employee_name", "department", "designation", "branch", "status", "date_of_joining",
		"relieving_date", "company", "employment_type", "vn_contract_type",
	}),
	"tabUser": frozenset({"name", "enabled", "user_type", "creation", "last_login", "last_active"}),
}
_COT_CHUAN = ("name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield",
	"parenttype", "_user_tags", "_comments", "_assign", "_liked_by", "_seen")
# Danh sách TĨNH mọi cột đã biết (dùng khi check(columns=None); lúc chạy bc.ai.sqlro gộp thêm cột thật của bảng):
# ERPNext v16 employee.json / Frappe v16 user.json + cột chuẩn + HRMS + Custom Field của site / app ns.
COT_DA_BIET = {
	"tabEmployee": frozenset(_COT_CHUAN + (
		"attendance_device_id", "bank_ac_no", "bank_name", "bio", "blood_group", "branch", "cell_number", "company",
		"company_email", "contract_end_date", "create_user_automatically", "create_user_permission", "ctc",
		"current_accommodation_type", "current_address", "date_of_birth", "date_of_issue", "date_of_joining",
		"date_of_retirement", "department", "designation", "education", "emergency_phone_number", "employee",
		"employee_name", "employee_number", "encashment_date", "external_work_history", "family_background",
		"feedback", "final_confirmation_date", "first_name", "gender", "health_details", "held_on", "holiday_list",
		"iban", "image", "internal_work_history", "last_name", "leave_encashed", "lft", "marital_status",
		"middle_name", "naming_series", "new_workplace", "notice_number_of_days", "old_parent", "passport_number",
		"permanent_accommodation_type", "permanent_address", "person_to_be_contacted", "personal_email",
		"place_of_issue", "prefered_contact_email", "prefered_email", "reason_for_leaving", "relation",
		"relieving_date", "reports_to", "resignation_letter_date", "rgt", "salary_currency", "salary_mode",
		"salutation", "scheduled_confirmation_date", "status", "unsubscribed", "user_id", "valid_upto",
		# HRMS
		"employment_type", "grade", "default_shift", "payroll_cost_center", "expense_approver", "leave_approver",
		"shift_request_approver", "job_applicant", "health_insurance_provider", "health_insurance_no",
		# Custom Field site / app ns
		"custom_cccd", "custom_zalo", "custom_năm_gia_nhập", "custom_lương_cơ_bản", "custom_hỗ_trợ",
		"custom_bảo_hiểm", "custom_lương_tài_khoản", "custom_ăn_ca_tối_tại_công_ty", "custom_bankowner",
		"vn_contract_type", "vn_tax_code", "vn_number_of_dependents", "vn_insurance_salary", "vn_province",
		"ns_dong_bhxh", "ns_so_so_bhxh", "ns_bhxh_tu_ngay", "ns_bhxh_den_ngay", "ns_ly_do_khong_bhxh", "ns_giay_to",
	)),
	"tabUser": frozenset(_COT_CHUAN + (
		"active_sessions", "allowed_in_mentions", "api_key", "api_secret", "banner_image", "bio", "birth_date",
		"block_modules", "bulk_actions", "bypass_restrict_ip_check_if_2fa_enabled", "code_editor_type", "dashboard",
		"default_app", "default_workspace", "defaults", "desk_theme", "dock_mode", "document_follow_frequency",
		"document_follow_notify", "email", "email_signature", "enabled", "first_name", "follow_assigned_documents",
		"follow_commented_documents", "follow_created_documents", "follow_liked_documents",
		"follow_shared_documents", "form_navigation_buttons", "form_sidebar", "full_name", "gender",
		"home_settings", "interest", "language", "last_active", "last_ip", "last_known_versions", "last_login",
		"last_name", "last_password_reset_date", "last_reset_password_key_generated_on", "list_sidebar", "location",
		"login_after", "login_before", "logout_all_sessions", "middle_name", "mobile_no", "module_profile",
		"mute_sounds", "new_password", "notifications", "onboarding_status", "phone", "redirect_url",
		"report_split_view", "reset_password_key", "restrict_ip", "role_profile_name", "role_profiles", "roles",
		"search_bar", "send_me_a_copy", "send_read_receipt", "send_welcome_email",
		"show_absolute_datetime_in_timeline", "show_my_space", "simultaneous_sessions", "social_logins",
		"thread_notify", "time_zone", "timeline", "unsubscribed", "user_emails", "user_image", "user_type",
		"username", "view_switcher",
	)),
}

# Từ không coi là bí danh của bảng / bảng tạm KHÁC (đứng ngay sau tên bảng) — chỉ dùng để bỏ qua cột "x.cột" của bảng
# khác (thiếu một bí danh ở đây chỉ làm chặn nhầm). Bí danh của tabEmployee / tabUser KHÔNG lọc qua danh sách này: từ
# đứng ngay sau hai bảng đó luôn được coi là bí danh (END, FULL… là bí danh hợp lệ của MariaDB — soát chéo P3).
_KHONG_BI_DANH = frozenset({
	"where", "join", "inner", "left", "right", "cross", "straight_join", "natural", "full", "outer", "on", "using",
	"group", "order", "limit", "having", "union", "except", "intersect", "window", "for", "lock", "into",
	"partition", "use", "ignore", "force", "as", "set", "and", "or", "not", "in", "is", "like", "between", "select",
	"from", "with", "offset", "returning", "values", "when", "then", "else", "end", "case",
})
_KHOANG_TRANG = " \t\n\r\f\v"
_DAU = set("(),.;+-*/%=<>!~^&|")


class _Loi(Exception):
	"""Lý do từ chối (tiếng Việt, ngắn, an toàn để gửi mô hình)."""


class _Tu:
	"""Một từ đã tách: k = 'w' từ trần | 'i' tên `…` | 's' chuỗi | 'n' số | 'p' dấu; v = giá trị (tên / chuỗi đã bỏ
	thoát); q = dấu nháy của chuỗi."""
	__slots__ = ("k", "v", "q")

	def __init__(self, k, v, q=""):
		self.k, self.v, self.q = k, v, q

	@property
	def ten(self) -> bool:
		return self.k in ("w", "i")

	@property
	def low(self) -> str:
		return _chuan(self.v)

	def la(self, *tu) -> bool:
		"""Từ trần (không phải tên `…`) bằng một trong các từ (chữ thường)."""
		return self.k == "w" and self.v.lower() in tu

	def __repr__(self):  # pragma: no cover — chỉ để gỡ lỗi
		return f"{self.k}:{self.v!r}"


def _chuan(ten: str) -> str:
	"""Dạng so sánh của tên: chữ thường; tên có chữ ngoài ASCII còn được bỏ dấu (NFKD) và đổi ı → i — MariaDB 10.11
	so tên bảng / cột theo đúng ký tự (đã thử), đây chỉ là phòng xa cho máy chủ so tên lỏng hơn (nghiêng về phía chặn)."""
	t = ten.lower()
	if t.isascii():
		return t
	t = unicodedata.normalize("NFKD", t.casefold().replace("ı", "i"))
	return "".join(ch for ch in t if not unicodedata.combining(ch))


def _ky_tu_ten(c: str) -> bool:
	"""Ký tự của tên không nháy theo MariaDB: [0-9A-Za-z_$] và U+0080…U+FFFF."""
	if c.isascii():
		return c.isalnum() or c in "_$"
	return ord(c) <= 0xFFFF


def tach(sql: str) -> list:
	"""Tách câu thành danh sách _Tu. Gặp chú thích, biến, chuỗi / tên không đóng, ký tự lạ → _Loi."""
	out: list = []
	i, n = 0, len(sql)
	while i < n:
		c = sql[i]
		if c in _KHOANG_TRANG:
			i += 1
			continue
		if c == "#" or sql.startswith("--", i) or sql.startswith("/*", i) or sql.startswith("*/", i):
			raise _Loi("không được có chú thích (--, #, /* */)")
		if c == "@":
			raise _Loi("không được dùng biến (@x, @@x)")
		if c in "'\"":
			j, buf = i + 1, []
			while True:
				if j >= n:
					raise _Loi("chuỗi chưa đóng nháy")
				d = sql[j]
				if d == "\\":
					if j + 1 >= n:
						raise _Loi("chuỗi chưa đóng nháy")
					buf.append(sql[j + 1])
					j += 2
					continue
				if d == c:
					if j + 1 < n and sql[j + 1] == c:
						buf.append(c)
						j += 2
						continue
					break
				buf.append(d)
				j += 1
			out.append(_Tu("s", "".join(buf), c))
			i = j + 1
			continue
		if c == "`":
			j, buf = i + 1, []
			while True:
				k = sql.find("`", j)
				if k < 0:
					raise _Loi("tên trong dấu ` chưa đóng")
				buf.append(sql[j:k])
				if sql[k + 1:k + 2] == "`":
					buf.append("`")
					j = k + 2
					continue
				break
			ten = "".join(buf)
			if not ten.strip():
				raise _Loi("tên rỗng trong dấu `")
			out.append(_Tu("i", ten))
			i = k + 1
			continue
		truoc_la_ten = bool(out) and (out[-1].ten or (out[-1].k == "p" and out[-1].v == ")"))
		if c.isascii() and c.isdigit() or (c == "." and i + 1 < n and sql[i + 1].isascii() and sql[i + 1].isdigit()
				and not truoc_la_ten):
			j = i
			while j < n and sql[j].isascii() and sql[j].isdigit():
				j += 1
			if j < n and sql[j] == "." and not (j + 1 < n and _ky_tu_ten(sql[j + 1]) and not sql[j + 1].isdigit()):
				j += 1
				while j < n and sql[j].isascii() and sql[j].isdigit():
					j += 1
			if j < n and sql[j] in "eE" and j + 1 < n and (sql[j + 1].isdigit() or (sql[j + 1] in "+-" and j + 2 < n
					and sql[j + 2].isdigit())):
				j += 2
				while j < n and sql[j].isascii() and sql[j].isdigit():
					j += 1
			if j < n and _ky_tu_ten(sql[j]):  # 0x1F, 0b01, 1abc: một từ (số hex / tên bắt đầu bằng chữ số)
				if any(ch in ".eE" for ch in sql[i:j]) and sql[i:i + 2].lower() not in ("0x", "0b"):
					# 1e0union / 1.5from: MariaDB tách thành số + từ khoá — bộ tách từ không đoán, chặn
					raise _Loi("số dính liền chữ (viết cách số và từ)")
				while j < n and _ky_tu_ten(sql[j]):
					j += 1
				tu = sql[i:j]
				out.append(_Tu("n" if tu[:2].lower() in ("0x", "0b") else "w", tu))
			else:
				out.append(_Tu("n", sql[i:j]))
			i = j
			continue
		if _ky_tu_ten(c):
			j = i
			while j < n and _ky_tu_ten(sql[j]):
				j += 1
			out.append(_Tu("w", sql[i:j]))
			i = j
			continue
		if c in _DAU:
			out.append(_Tu("p", c))
			i += 1
			continue
		raise _Loi(f"ký tự không được phép ngoài chuỗi: {c!r}" if c.isprintable() else "ký tự không được phép")
	return out


def _bang_cam(ten: str) -> bool:
	"""Tên (đã chữ thường) là bảng cấm theo luật 4."""
	t = ten.strip()
	if t.startswith("__"):
		return True
	if t in BANG_CAM:
		return True
	if t.startswith("tab"):
		if t.startswith(TIEN_TO_CAM):
			return True
		if any(m in t for m in MAU_LUONG):
			return True
	return False


def doctype_allowed(doctype: str) -> bool:
	"""get_schema: DocType có được xem cấu trúc không (cùng danh sách bảng cấm của luật 4)."""
	if not isinstance(doctype, str) or not doctype.strip() or len(doctype) > 140:
		return False
	return not _bang_cam(_chuan("tab" + doctype))


def _bat_dau_select(tus) -> bool:
	for t in tus:
		if t.k == "p" and t.v == "(":
			continue
		return t.la("select", "with")
	return False


def _chuoi_ten(tus, i):
	"""Từ vị trí i (một tên): độ dài chuỗi tên nối bằng '.' (a.b.c → 3)."""
	n = 1
	while i + 2 < len(tus) and tus[i + 1].k == "p" and tus[i + 1].v == "." and tus[i + 2].ten:
		n += 1
		i += 2
	return n


def _la_ten(t) -> bool:
	"""Tên trần / `…`, và cả chuỗi "…" (chế độ ANSI_QUOTES của MariaDB đọc "…" thành tên — nghiêng về phía chặn)."""
	return t.ten or (t.k == "s" and t.q == '"')


def _la_truy_van_con(tus, dong) -> bool:
	"""Dấu ')' ở vị trí `dong` đóng một truy vấn con (… (SELECT / WITH …) x), không phải nhóm tên bảng ((tabX) x)."""
	sau = 0
	for j in range(dong, -1, -1):
		t = tus[j]
		if t.k == "p" and t.v == ")":
			sau += 1
		elif t.k == "p" and t.v == "(":
			sau -= 1
			if sau == 0:
				k = j + 1
				while k < len(tus) and tus[k].k == "p" and tus[k].v == "(":
					k += 1
				return k < len(tus) and tus[k].la("select", "with")
	return False


def _bi_danh_bang(tus, i) -> set:
	"""Bí danh có thể có của tabEmployee / tabUser ở vị trí i — NGHIÊNG VỀ PHÍA CHẶN: tên / chuỗi đứng ngay sau (bỏ ")" của
	nhóm "(tabEmployee) e" và AS) luôn là bí danh, kể cả từ khoá (END, FULL, OFFSET…). Coi thừa chỉ làm chặn nhầm cột
	"x.cột" của từ đó; bỏ sót thì lọt mọi cột (soát chéo P3: WITH `end` AS (…) SELECT end.bank_ac_no FROM tabEmployee end)."""
	n, j = len(tus), i + 1
	while j < n and tus[j].k == "p" and tus[j].v == ")" and not _la_truy_van_con(tus, j):
		j += 1
	if j < n and tus[j].la("for"):   # FOR SYSTEM_TIME … bí danh: không theo dõi được — chặn
		raise _Loi("không dùng FOR SYSTEM_TIME với tabEmployee / tabUser")
	if j < n and tus[j].la("as"):
		j += 1
	if j < n and (tus[j].ten or tus[j].k == "s"):
		return {tus[j].low}
	return set()


def _soat_cot(tus, cols: dict) -> None:
	"""Luật 5 cho tabEmployee / tabUser."""
	co = {}
	for t in tus:
		if _la_ten(t) and t.low in ("tabemployee", "tabuser"):
			co[t.low] = "tabEmployee" if t.low == "tabemployee" else "tabUser"
	if not co:
		return
	bang = set(co.values())
	for i, t in enumerate(tus):
		if t.k == "p" and t.v == "*":
			ok = (0 < i < len(tus) - 1 and tus[i - 1].k == "p" and tus[i - 1].v == "(" and tus[i + 1].k == "p"
				and tus[i + 1].v == ")" and i >= 2 and tus[i - 2].la("count"))
			if not ok:
				raise _Loi("câu có " + " / ".join(sorted(bang)) + ": không dùng * (chỉ COUNT(*)), liệt kê cột cho phép")
		if t.la("natural"):
			raise _Loi("câu có " + " / ".join(sorted(bang)) + ": không dùng NATURAL JOIN")
	# Bí danh: tên bảng tự nó + từ / tên đứng sau (bỏ AS).
	bi_danh = {T: {T.lower()} for T in bang}
	khac: set = set()
	for i, t in enumerate(tus):
		la_bang = t.ten and (i == 0 or not (tus[i - 1].k == "p" and tus[i - 1].v == "."))
		sau_ngoac = t.k == "p" and t.v == ")" and _la_truy_van_con(tus, i)
		if la_bang and t.low in co:
			bi_danh[co[t.low]] |= _bi_danh_bang(tus, i)
			continue
		if not (la_bang or sau_ngoac):
			continue
		j = i + 1
		if j < len(tus) and tus[j].la("as"):
			j += 1
		if j < len(tus) and tus[j].ten and not (tus[j].k == "w" and tus[j].low in _KHONG_BI_DANH) \
				and not (j + 1 < len(tus) and tus[j + 1].k == "p" and tus[j + 1].v in ".("):
			ten = tus[j].low
			if sau_ngoac or (t.ten and t.low.startswith("tab")):
				khac.add(ten)
		# CTE: <tên> AS ( …
		if t.ten and i + 2 < len(tus) and tus[i + 1].la("as") and tus[i + 2].k == "p" and tus[i + 2].v == "(":
			khac.add(t.low)
	tat_ca_cot = {T: {_chuan(c) for c in (COT_DA_BIET.get(T, frozenset()) | set((cols or {}).get(T) or ()))}
		for T in bang}
	cho_phep = {T: {_chuan(c) for c in ALLOWED_COLUMNS[T]} for T in bang}
	for i, t in enumerate(tus):
		if not _la_ten(t):
			continue
		if i + 1 < len(tus) and tus[i + 1].k == "p" and tus[i + 1].v == ".":
			continue  # tiền tố (bí danh / bảng), soát cùng tên đứng sau
		ten = t.low
		if i >= 2 and tus[i - 1].k == "p" and tus[i - 1].v == ".":
			q = tus[i - 2].low if tus[i - 2].ten else ""
			cua = [T for T in bang if q in bi_danh[T]]
			if cua:
				for T in cua:
					if ten not in cho_phep[T]:
						raise _Loi(f"{T}: cột {t.v!r} không được dùng (chỉ: {', '.join(sorted(ALLOWED_COLUMNS[T]))})")
				continue
			if q in khac:   # bí danh chắc chắn của bảng / bảng tạm khác VÀ không phải bí danh Employee / User (xét ở trên)
				continue
		for T in bang:
			if ten in tat_ca_cot[T] and ten not in cho_phep[T]:
				raise _Loi(f"{T}: cột {t.v!r} không được dùng (chỉ: {', '.join(sorted(ALLOWED_COLUMNS[T]))})")


def _soat(sql, columns):
	if not isinstance(sql, str):
		raise _Loi("câu SQL phải là chuỗi")
	if len(sql) > MAX_LEN:
		raise _Loi(f"câu SQL dài quá {MAX_LEN} ký tự")
	sach = sql.strip()
	if not sach:
		raise _Loi("câu SQL rỗng")
	tus = tach(sach)
	# Luật 1: ngoặc phải cân (câu được bọc trong "SELECT * FROM (<câu>) AS _t" — ')' thừa thoát ra khỏi lớp bọc).
	sau = 0
	for t in tus:
		if t.k == "p" and t.v in "()":
			sau += 1 if t.v == "(" else -1
			if sau < 0:
				break
	if sau != 0:
		raise _Loi("ngoặc ( ) không cân")
	# Luật 1: ';' chỉ một dấu, ở cuối.
	cham = [i for i, t in enumerate(tus) if t.k == "p" and t.v == ";"]
	if cham:
		if len(cham) > 1 or cham[0] != len(tus) - 1:
			raise _Loi("chỉ một câu lệnh (không có ';' ở giữa)")
		tus = tus[:-1]
		sach = sach[:sach.rindex(";")].rstrip()
	if not tus or not _bat_dau_select(tus):
		raise _Loi("câu phải bắt đầu bằng SELECT hoặc WITH")
	# Luật 2: từ khoá, hàm cấm.
	for i, t in enumerate(tus):
		if t.k == "w" and t.low in TU_CAM:
			raise _Loi(f"từ khoá {t.v.upper()} không được dùng")
		if t.k == "w" and t.low in HAM_CAM:
			raise _Loi(f"hàm {t.v.upper()} không được dùng")
		if t.k == "i" and t.low in HAM_CAM and i + 1 < len(tus) and tus[i + 1].k == "p" and tus[i + 1].v == "(":
			raise _Loi(f"hàm {t.v.upper()} không được dùng")
		if t.la("next", "previous") and i + 1 < len(tus) and tus[i + 1].la("value"):
			raise _Loi("không dùng sequence (NEXT / PREVIOUS VALUE)")
		if t.la("partition") and not (i + 1 < len(tus) and tus[i + 1].la("by")):
			raise _Loi("chỉ dùng PARTITION BY (hàm cửa sổ)")
	# Luật 3: CSDL khác, tên có tiền tố CSDL.
	for i, t in enumerate(tus):
		if (t.ten or (t.k == "s" and t.q == '"')) and t.low.strip() in CSDL_CAM:
			raise _Loi(f"không được đọc CSDL {t.v}")
		if t.ten and (i == 0 or not (tus[i - 1].k == "p" and tus[i - 1].v == ".")):
			dai = _chuoi_ten(tus, i)
			if dai >= 3:
				raise _Loi("không dùng tên có tiền tố CSDL (a.b.c)")
			if dai == 2:
				sau = tus[i + 2].low
				k = i - 1
				while k >= 0 and tus[k].k == "p" and tus[k].v == "(":   # FROM (db.bang)
					k -= 1
				truoc = tus[k] if k >= 0 else None
				if (sau.startswith(("tab", "__")) and not sau.startswith("table")) or (truoc is not None and (truoc.la("from", "join", "straight_join")
						or (truoc.k == "p" and truoc.v == "," and _trong_from(tus, k + 1)))):
					raise _Loi("không dùng tên bảng có tiền tố CSDL (csdl.bảng)")
	# Luật 4: bảng cấm.
	for t in tus:
		if (t.ten or (t.k == "s" and t.q == '"')) and _bang_cam(t.low):
			raise _Loi(f"bảng {t.v.strip()!r} không được đọc")
	# Luật 5.
	_soat_cot(tus, columns)
	return sach


def _trong_from(tus, i) -> bool:
	"""Vị trí i (sau dấu ',') có nằm trong mệnh đề FROM cùng tầng ngoặc không (đi lùi tới FROM / từ khoá mệnh đề; ON /
	USING vẫn thuộc FROM: "… JOIN b ON a.x = b.x, db.bang")."""
	sau = 0
	for j in range(i - 1, -1, -1):
		t = tus[j]
		if t.k == "p" and t.v == ")":
			sau += 1
		elif t.k == "p" and t.v == "(":
			if sau == 0:
				return False
			sau -= 1
		elif sau == 0 and t.k == "w":
			if t.low == "from":
				return True
			if t.low in ("select", "where", "group", "order", "having", "limit", "union", "with", "window"):
				return False
	return False


def check(sql: str, columns: dict | None = None) -> tuple:
	"""→ (ok, lý do từ chối bằng tiếng Việt ngắn hoặc "", câu đã gọt để chạy — bỏ khoảng trắng hai đầu và ';' cuối).

	columns = {"tabEmployee": {mọi cột của bảng}, "tabUser": {…}} — gộp với danh sách tĩnh COT_DA_BIET (None → chỉ
	danh sách tĩnh). Spec §2.2 luật 1–5."""
	try:
		return True, "", _soat(sql, columns)
	except _Loi as e:
		return False, str(e), ""


def key(ten: str) -> str:
	"""Dạng so sánh của một tên bảng / DocType / phân hệ (chữ thường, bỏ dấu khi có chữ ngoài ASCII)."""
	return _chuan(str(ten or "")).strip()


def tables(sql: str) -> list:
	"""Luật 4b: các tên bảng `tab…` được nhắc trong câu (giữ nguyên chữ, không trùng) — tên trong nháy ` ` bắt đầu
	bằng "tab", hoặc tên trần "tab" + chữ HOA / chữ số ("tabItem"). Tên cột thường ("table_name", "tabs") không tính."""
	out: dict = {}
	for t in tach(str(sql or "").strip()):
		if not t.ten:
			continue
		v = t.v.strip()
		if len(v) > 3 and v[:3].lower() == "tab" and (t.k == "i" or not (v[3].islower() or v[3] == "_")):
			out.setdefault(v)
	return list(out)


def module_allowed(module: str) -> bool:
	"""Luật 4b: phân hệ của DocType có được đọc không (MODULE_CAM)."""
	return key(module) not in MODULE_CAM


def wrap(sql: str, limit: int = 200, seconds: int = 10) -> str:
	"""Luật 6: câu ĐÃ QUA check() → câu chạy thật, có trần thời gian và trần dòng.

	ORDER BY ở tầng ngoài mà không LIMIT → thêm "LIMIT <limit>" vào trong (MariaDB bỏ ORDER BY của bảng con không
	LIMIT — kết quả "top N" sẽ mất thứ tự)."""
	limit, seconds = int(limit), int(seconds)
	if limit < 1 or seconds < 1:
		raise ValueError("limit / seconds phải ≥ 1")
	sach = sql.strip()
	if sach.endswith(";"):
		sach = sach[:-1].rstrip()
	tus = tach(sach)
	sau, co_order, co_limit = 0, False, False
	for i, t in enumerate(tus):
		if t.k == "p" and t.v == "(":
			sau += 1
		elif t.k == "p" and t.v == ")":
			sau -= 1
		elif sau == 0 and t.la("order") and i + 1 < len(tus) and tus[i + 1].la("by"):
			co_order = True
		elif sau == 0 and t.la("limit"):
			co_limit = True
	if co_order and not co_limit:
		sach = f"{sach} LIMIT {limit}"
	return f"SET STATEMENT max_statement_time={seconds} FOR SELECT * FROM ({sach}) AS _t LIMIT {limit}"
