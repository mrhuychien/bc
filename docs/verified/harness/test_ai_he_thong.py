"""Trợ lý AI — detector hệ thống + quy tắc ht.* (bc.ai.detectors.he_thong, đặc tả §4.2).

A: detector SQL trên MariaDB thật (bảng Error Log / Scheduled Job Log / Email Queue / Activity Log / BC AI Run sinh
từ DocType JSON v16): seed tay, mốc "24 giờ" = (now − 24 giờ, now] với ca đúng biên. B: detector hệ điều hành (sao
lưu, đĩa, hàng đợi) với thư mục tạm / disk_usage giả / hàng đợi giả. C: chạy trọn run_detectors → run_rules trên pack
thật. D: quy tắc trên pack dựng tay (biên, ghi đè, tắt, nguồn lỗi). E: AST (chỉ SELECT, không NOW()), gói số không
traceback / nội dung / tên tài khoản. Số kỳ vọng TÍNH TAY.

Chạy: BC_TEST_DB=bc_test_ai_rnsht python3 -B test_ai_he_thong.py
"""
import ast
import collections
import copy
import datetime
import json
import os
import re
import shutil
import tempfile
import time
from zoneinfo import ZoneInfo

from seed import Check, insert, reset
from paths import BC_ROOT

import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.detectors.he_thong")

import frappe  # noqa: E402
import frappe.utils  # noqa: E402
from frappe.utils import background_jobs as BJ  # noqa: E402
from bc.ai import render  # noqa: E402
from bc.ai.detectors import he_thong as HT  # noqa: E402

c = Check()
H = "he-thong"
RULES = ("ht.error_log", "ht.job_that_bai", "ht.email_loi", "ht.hang_doi", "ht.backup_cu", "ht.dia_day",
	"ht.dang_nhap_sai", "ht.ai_loi")
MOI = []
NOW = frappe.utils.now_datetime()          # 27/10/2026 10:30:00 (FAKE_TODAY + FAKE_NOW_TIME)
CTX = {"now": NOW, "today": NOW.date()}
TB = "Traceback (most recent call last): File SECRET-TRACE line 1"
TMP = tempfile.mkdtemp(prefix="bc_ht_")
frappe.FAKE_SITE_PATH = TMP


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def P(path, kind):
	return "{{" + f"{path}|{kind}" + "}}"


def t(**kw):
	"""Thời điểm = NOW + timedelta(**kw)."""
	return NOW + datetime.timedelta(**kw)


def chay(pack, only=RULES, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def muc_all(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return "KHONG-CHAY" if key not in run.ran else {s.key: s.severity for s in run.signals}


def mot(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


# ═══ A. Detector SQL ═════════════════════════════════════════════════════════
print("A. Detector SQL — now = 27/10/2026 10:30, cửa sổ (26/10 10:30, 27/10 10:30]")
reset()
eq("now của bộ thử", NOW, datetime.datetime(2026, 10, 27, 10, 30))


def el(when, method):
	insert("Error Log", creation=when, modified=when, method=method, error=TB, seen=0)


# 24 giờ: kd ×5 (một cái đúng lúc now), sx ×4, method NULL ×1, a, b, c ×1 → 13; nhóm theo NHÃN (D1): bc.api.kd 5,
# sx.job 4 (sx là app đã cài của site giả), a / b / c không phải tên an toàn → "(khác)" 3, NULL → "(không ghi)" 1.
for i in range(4):
	el(t(hours=-i - 1), "bc.api.kd")
el(NOW, "bc.api.kd")
for i in range(4):
	el(t(minutes=-30 * (i + 1)), "sx.job")
for m in (None, "c", "b", "a"):
	el(t(hours=-20), m)
el(t(minutes=1), "tuong.lai")                       # sau now → không tính
el(t(hours=-24), "bien.24h")                         # đúng 24 giờ trước → thuộc 7 ngày trước, không thuộc 24 giờ
for i in range(33):                                  # + 33 cái trong (19/10 10:30, 26/10 10:30) → 7 ngày trước = 34
	el(t(days=-2, hours=-i * 3), "cu")
el(t(days=-8), "bien.8ngay")                         # đúng 8 ngày trước → ngoài cả hai cửa sổ
d = HT.d_error_log(CTX)
eq("error_log: tong 13, tb = 34 / 7 = 4,857 → 4,9; top 5 nhóm theo số rồi tên", d, {"tong": 13, "tb_ngay": 4.9,
	"nhom": [{"method": "bc.api.kd", "so": 5}, {"method": "sx.job", "so": 4}, {"method": "(khác)", "so": 3},
	{"method": "(không ghi)", "so": 1}]})

# D1: tiêu đề Error Log của v16 là str(exception) / dòng cuối traceback → chỉ nhãn an toàn vào pack.
BI_MAT = ("tran.thi.b", "hgc.vn", "Minh Phát", "0912345678", "le.van.c", "Phúc Lộc", "0903", "congty", "Duplicate",
	"locked", "khoá", "Traceback", "SECRET", "cust_9")
TIEU_DE = [
	("(1062, \"Duplicate entry 'tran.thi.b@hgc.vn' for key 'email'\")", 3),
	("frappe.exceptions.ValidationError: Khách hàng Đại lý Minh Phát vượt hạn mức, liên hệ 0912345678", 2),
	("frappe.exceptions.ValidationError", 1),
	("KeyError: 'le.van.c@hgc.vn'", 2),
	("Không tìm thấy Khách hàng: Đại lý Phúc Lộc (0903 123 456)", 1),
	("User nguyen.van.a@congty.vn bị khoá", 1),
	("tran.thi.b locked", 2),
	("Đại lý Minh Phát", 1),
	("0912345678", 1),
	("erpnext.selling.doctype.x.make\nTraceback (most recent call last): SECRET", 1),
	("bc.api.kd.get_overview(cust_9)", 1),
	("bc." + "a" * 80 + ".x", 1),                 # dài quá 80 ký tự → (khác)
	("Sx[cust_9]", 1),
	("tran.thi.b", 1),
]
frappe.db.sql("DELETE FROM `tabError Log`")
for ti, n in TIEU_DE:
	for i in range(n):
		el(t(hours=-1, minutes=-i), ti)
d = HT.d_error_log(CTX)
eq("D1: tiêu đề có email / tên khách / số điện thoại / bộ SQL / tài khoản → nhãn an toàn", d, {"tong": 19,
	"tb_ngay": 0.0, "nhom": [{"method": "(khác)", "so": 12}, {"method": "frappe.exceptions.ValidationError", "so": 3},
	{"method": "KeyError", "so": 2}, {"method": "bc.api.kd.get_overview", "so": 1},
	{"method": "erpnext.selling.doctype.x.make", "so": 1}]})
eq("D1: gói số không còn mảnh tiêu đề nào", [x for x in BI_MAT if x in json.dumps(d, ensure_ascii=False)], [])
eq("D1: nhãn từng loại", [HT._nhan(x, {"frappe", "bc"}) for x in (None, "", "  ", "ValueError", "a.b.CustomException",
	"bc.tasks.daily", "frappe", "SystemExit", "KeyboardInterrupt", "x.DeprecationWarning", "khach.hang", "bc.x y",
	"bc.x:y", "bc.x[0]", "bc..x", "1bc.x")], ["(không ghi)", "(không ghi)", "(không ghi)", "ValueError",
	"a.b.CustomException", "bc.tasks.daily", "(khác)", "SystemExit", "KeyboardInterrupt", "x.DeprecationWarning", "(khác)",
	"bc.x", "bc.x", "bc.x", "(khác)", "(khác)"])
_apps_goc = frappe.get_installed_apps
frappe.get_installed_apps = lambda *a, **k: 1 / 0
try:
	eq("D1: get_installed_apps lỗi → chỉ frappe / erpnext / bc", [HT._nhan(x, HT._apps()) for x in ("sx.job",
		"bc.api.kd", "erpnext.x", "frappe.y")], ["(khác)", "bc.api.kd", "erpnext.x", "frappe.y"])
finally:
	frappe.get_installed_apps = _apps_goc
_p = {H: {"error_log": d}}
_r = chay(_p, only=("ht.error_log",))
eq("D1: nhóm đầu là (khác) → lời không nêu tên nhóm, không mảnh tiêu đề",
	[render.fill(x.title + " | " + x.detail, _p).text for x in _r.signals],
	["Lỗi hệ thống trong ngày qua: 19 lần, trung bình 0 lần | Quản trị cần xem Error Log trước khi lỗi ảnh hưởng "
	"người dùng."])
frappe.db.sql("DELETE FROM `tabError Log`")
el(t(hours=-1), "KeyError: 'le.van.c@hgc.vn'")
eq("D1: một dòng lỗi (quy tắc không nổ) vẫn không lộ email", HT.d_error_log(CTX)["nhom"], [{"method": "KeyError", "so": 1}])
# trả lại dữ liệu ca chung cho phần C
frappe.db.sql("DELETE FROM `tabError Log`")
for i in range(4):
	el(t(hours=-i - 1), "bc.api.kd")
el(NOW, "bc.api.kd")
for i in range(4):
	el(t(minutes=-30 * (i + 1)), "sx.job")
for m in (None, "c", "b", "a"):
	el(t(hours=-20), m)
el(t(minutes=1), "tuong.lai")
el(t(hours=-24), "bien.24h")
for i in range(33):
	el(t(days=-2, hours=-i * 3), "cu")
el(t(days=-8), "bien.8ngay")
eq("dữ liệu ca chung trả lại như trước", HT.d_error_log(CTX)["tong"], 13)

# Scheduled Job Log: Failed trong 24 giờ: bc.tasks.daily ×2, frappe.x ×1; Complete không tính; Failed đúng 24 giờ trước
# và Failed 2 ngày trước không tính.
for j, st, when in [("bc.tasks.daily", "Failed", t(hours=-1)), ("bc.tasks.daily", "Failed", t(hours=-23, minutes=-59)),
		("frappe.x", "Failed", t(hours=-5)), ("bc.tasks.daily", "Complete", t(hours=-2)), ("z.ok", "Complete", t(hours=-3)),
		("old.job", "Failed", t(hours=-24)), ("old.job", "Failed", t(days=-2))]:
	insert("Scheduled Job Log", creation=when, modified=when, scheduled_job_type=j, status=st, details=TB)
eq("job_that_bai: 3 lượt, 2 loại, lỗi nhiều nhất bc.tasks.daily 2", HT.d_job_that_bai(CTX), {"tong": 3, "so_loai": 2,
	"loai": [{"job": "bc.tasks.daily", "so": 2}, {"job": "frappe.x", "so": 1}]})

# Email Queue: Error trong 24 giờ ×2; Sent ×1; Error 2 ngày trước ×1 → 2.
for st, when in [("Error", t(hours=-1)), ("Error", t(hours=-10)), ("Sent", t(hours=-2)), ("Error", t(days=-2))]:
	insert("Email Queue", creation=when, modified=when, status=st, message="NOI-DUNG-THU-BI-MAT",
		error="SMTP SECRET-ERR", sender="kt.bimat@hgc.vn")
eq("email_loi: 2 thư lỗi trong 24 giờ", HT.d_email_loi(CTX), {"so": 2})

# Activity Log: Login Failed trong 24 giờ: ghost (không có User) 12, kt 11, ab 10 (+ 1 đúng 24 giờ trước — không tính);
# Login Success của kt, Logout Failed không tính.
insert("User", name="kt.bimat@hgc.vn", enabled=1, first_name="Kế Toán Bí Mật")
insert("User", name="ab.bimat@hgc.vn", enabled=1, first_name="AB Bí Mật")


def al(user, n, status="Failed", op="Login", h=-1):
	for i in range(n):
		w = t(hours=h, minutes=-i)
		insert("Activity Log", creation=w, modified=w, user=user, operation=op, status=status,
			subject="Incorrect password", full_name="Tên Người Dùng Bí Mật", ip_address="10.9.8.7")


al("ghost.bimat@x.vn", 12)
al("kt.bimat@hgc.vn", 11)
al("ab.bimat@hgc.vn", 10)
al("ab.bimat@hgc.vn", 1, h=-24)
al("kt.bimat@hgc.vn", 5, status="Success")
al("kt.bimat@hgc.vn", 4, op="Logout")
d = HT.d_dang_nhap_sai(CTX)
eq("dang_nhap_sai: 3 tài khoản, 33 lần, nhiều nhất 12 — chỉ số", d, {"so_tk": 3, "tong": 33, "max_lan": 12,
	"lan": [12, 11, 10], "moc": "2026-10-27 10:30:00"})
eq("dang_nhap_sai: tên tài khoản chỉ ở bộ nhớ module, chỉ User có thật", HT._TK,
	{"moc": "2026-10-27 10:30:00", "tk": [("kt.bimat@hgc.vn", 11), ("ab.bimat@hgc.vn", 10)]})


# BC AI Run: R0 (20/10, tổng loi) cũ hơn 3 lượt; R1 (24/10) tổng ok, mô hình loi + het-credit → hỏng; R2 (25/10) tổng loi
# → hỏng; R3 (26/10) tổng ok, mô hình ok + loi → KHÔNG hỏng; R4 (27/10) đang chạy (loi, "chưa hoàn tất", finished
# trống) → bỏ; R5 hỏi đáp → bỏ.
def run(name, started, status, finished=True, run_type="ngay", con=(), error=None):
	base = dict(run_type=run_type, cost_usd=0, cost_known=1, tokens_in=0, tokens_out=0, signals=0, insights_ai=0,
		rejected=0)
	insert("BC AI Run", name=name, step="tong", run_id=name, status=status, started=started, creation=started,
		finished=started + datetime.timedelta(minutes=5) if finished else None, error=error, **base)
	for i, (step, st) in enumerate(con):
		insert("BC AI Run", name=f"{name}-{i}", step=step, run_id=name, status=st, started=started, creation=started,
			finished=started, provider="claude", model="claude-sonnet-5-5", **base)


D = lambda day, h=6: datetime.datetime(2026, 10, day, h, 0)  # noqa: E731
run("R0", D(20), "loi")
run("R1", D(24), "ok", con=[("kinh-doanh", "loi"), ("tai-chinh", "het-credit")])
run("R2", D(25), "loi")
run("R3", D(26), "ok", con=[("kinh-doanh", "ok"), ("tai-chinh", "loi")])
run("R4", D(27), "loi", finished=False, error="chưa hoàn tất")
run("R5", D(27, 9), "loi", run_type="hoi-dap")
eq("ai_loi: 3 lượt đã xong (R3, R2, R1), hỏng 2 (R1 mọi lượt gọi hỏng, R2 tổng loi), hết credit 1",
	HT.d_ai_loi(CTX), {"so_luot": 3, "that_bai": 2, "het_credit": 1})
frappe.db.sql("UPDATE `tabBC AI Run` SET status = 'loi' WHERE name = 'R3-0'")
eq("R3 mọi lượt gọi đều loi → hỏng 3", HT.d_ai_loi(CTX)["that_bai"], 3)
frappe.db.sql("UPDATE `tabBC AI Run` SET status = 'ok' WHERE name = 'R3-0'")
run("R6", D(26, 8), "ok", con=[("ai", "tat")])     # AI tắt: không có lượt gọi mô hình → không hỏng
eq("lượt chỉ có dòng 'ai' (tắt) không tính là hỏng; R6 đẩy R1 ra", HT.d_ai_loi(CTX),
	{"so_luot": 3, "that_bai": 1, "het_credit": 0})
frappe.db.sql("DELETE FROM `tabBC AI Run` WHERE name LIKE 'R6%%'")
eq("ai_loi trước now: chỉ lượt bắt đầu ≤ now", HT.d_ai_loi({"now": D(25, 12), "today": D(25).date()}),
	{"so_luot": 3, "that_bai": 3, "het_credit": 1})
eq("ai_loi ít hơn 3 lượt", HT.d_ai_loi({"now": D(24, 12), "today": D(24).date()}),
	{"so_luot": 2, "that_bai": 2, "het_credit": 1})

# ═══ B. Detector hệ điều hành ════════════════════════════════════════════════
print("\nB. Sao lưu, đĩa, hàng đợi")
BK = os.path.join(TMP, "private", "backups")
eq("không có thư mục sao lưu → chưa có bản nào", HT.d_backup_cu(CTX), {"co_ban": False, "gio": None, "moi_nhat": None})
os.makedirs(BK)
eq("thư mục rỗng → chưa có bản nào", HT.d_backup_cu(CTX)["co_ban"], False)


def bk(name, hours):
	"""File sao lưu cũ `hours` giờ — NOW là giờ ngây thơ theo múi của SITE (như now_datetime v16)."""
	p = os.path.join(BK, name)
	open(p, "w").close()
	ts = (NOW.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone())) - datetime.timedelta(hours=hours)).timestamp()
	os.utime(p, (ts, ts))


bk("a-database.sql.gz", 40)
bk("b-database.sql.gz", 26)
os.makedirs(os.path.join(BK, "thu_muc_con"))         # thư mục con (mtime = bây giờ thật) không phải bản sao lưu
eq("bản mới nhất đúng 26 giờ", HT.d_backup_cu(CTX), {"co_ban": True, "gio": 26.0, "moi_nhat": "2026-10-26 08:30:00"})
bk("c-files.tar", 26.1)
eq("thêm bản cũ hơn không đổi kết quả", HT.d_backup_cu(CTX)["gio"], 26.0)

# D11: giờ của file đổi sang múi của site — máy chạy UTC / Los Angeles / cùng múi đều ra 20 giờ, không báo.
BK2 = os.path.join(TMP, "bk2")
os.makedirs(os.path.join(BK2, "private", "backups"))
_tz_goc = os.environ.get("TZ")
_site_goc = frappe.FAKE_SITE_PATH
frappe.FAKE_SITE_PATH = BK2
_f = os.path.join(BK2, "private", "backups", "x-database.sql.gz")
open(_f, "w").close()
_ts = (NOW.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")) - datetime.timedelta(hours=20)).timestamp()
os.utime(_f, (_ts, _ts))
_kq = {}
try:
	for tz in ("UTC", "America/Los_Angeles", "Asia/Ho_Chi_Minh"):
		os.environ["TZ"] = tz
		time.tzset()
		_d = HT.d_backup_cu(CTX)
		_kq[tz] = (_d["gio"], _d["moi_nhat"], muc_all({H: {"backup_cu": _d}}, "ht.backup_cu"))
	eq("D11: file 20 giờ tuổi, máy ở UTC / Los Angeles / Hồ Chí Minh → 20 giờ, không báo", _kq,
		{tz: (20.0, "2026-10-26 14:30:00", {}) for tz in ("UTC", "America/Los_Angeles", "Asia/Ho_Chi_Minh")})
	_z = frappe.utils.FAKE_SYSTEM_TZ
	frappe.utils.FAKE_SYSTEM_TZ = "Khong/Co"           # múi sai → giờ máy (máy đang ở Hồ Chí Minh)
	try:
		eq("D11: tên múi sai → dùng giờ máy, không ném lỗi", HT.d_backup_cu(CTX)["gio"], 20.0)
	finally:
		frappe.utils.FAKE_SYSTEM_TZ = _z
finally:
	if _tz_goc is None:
		os.environ.pop("TZ", None)
	else:
		os.environ["TZ"] = _tz_goc
	time.tzset()
	frappe.FAKE_SITE_PATH = _site_goc

Usage = collections.namedtuple("Usage", "total used free")
DU = {"u": Usage(1000, 851, 149), "goi": []}
_goc = shutil.disk_usage


def du_gia(p):
	DU["goi"].append(p)
	return DU["u"]


shutil.disk_usage = du_gia
try:
	eq("dia_day: 851 / 1000 = 85,1%; còn 149 B; gọi trên thư mục site", (HT.d_dia_day(CTX), DU["goi"]),
		({"pct": 85.1, "con_trong_gb": 0.0}, [frappe.utils.get_site_path()]))
	DU["u"] = Usage(0, 0, 0)
	eq("tổng 0 → không dùng được", HT.d_dia_day(CTX), {"available": False})
	DU["u"] = Usage(2_000_000_000_000, 1_900_000_000_000, 100_000_000_000)
	eq("1,9 / 2 TB = 95%, còn 100 GB", HT.d_dia_day(CTX), {"pct": 95.0, "con_trong_gb": 100.0})
finally:
	shutil.disk_usage = _goc

BJ.FAKE_QUEUES = [BJ.FakeQueue("default", 30), BJ.FakeQueue("long", 21), BJ.FakeQueue("short", 0)]
eq("hang_doi: 30 + 21 + 0 = 51 việc, 3 hàng", HT.d_hang_doi(CTX), {"cho": 51, "so_hang": 3})

# ═══ C. Trọn chuỗi: run_detectors → run_rules ════════════════════════════════
print("\nC. run_detectors → run_rules trên pack thật")
DU["u"] = Usage(1000, 931, 69)
shutil.disk_usage = du_gia
try:
	PACK = {H: registry.run_detectors(NOW)}
finally:
	shutil.disk_usage = _goc
eq("đủ 8 detector, không lỗi", sorted(k for k, v in PACK[H].items() if "_error" not in v),
	sorted(["error_log", "job_that_bai", "email_loi", "hang_doi", "backup_cu", "dia_day", "dang_nhap_sai", "ai_loi"]))
p1 = copy.deepcopy(PACK)
r = chay(p1)
sig = {s.key: s for s in r.signals}
eq("chạy đủ 8 quy tắc", (sorted(r.ran), r.not_run), (sorted(RULES), {}))
eq("tín hiệu + mức (ngưỡng mặc định)", {k: s.severity for k, s in sig.items()}, {
	"ht.error_log": "vang",        # 13 ≥ 10 và 13 > 2 × 4,9 = 9,8
	"ht.job_that_bai": "vang",     # 3 > 0
	"ht.email_loi": "vang",        # 2 > 0
	"ht.hang_doi": "vang",         # 51 > 50, ≤ 200
	# backup: 26,0 giờ, không > 26 → không báo
	"ht.dia_day": "do",            # 93,1% > 93
	"ht.dang_nhap_sai": "vang",    # 12, 11 > 10 → 2 tài khoản
	# ai_loi: 2 / 3 lượt hỏng → không báo
})
s = sig["ht.dang_nhap_sai"]
eq("dang_nhap_sai: 2 tài khoản quá 10 lần; documents chỉ User có thật > 10 lần (kt)", (s.tinh, s.documents),
	({"so_tk": 2, "nguong": 10}, [{"doctype": "User", "name": "kt.bimat@hgc.vn"}]))
eq("dang_nhap_sai: lời đã thay số", render.fill(s.title, p1).text, "2 tài khoản đăng nhập sai quá 10 lần trong ngày qua")
s = sig["ht.error_log"]
eq("error_log: lời đã thay số + nhóm nhiều nhất", render.fill(s.title + " | " + s.detail, p1).text,
	"Lỗi hệ thống trong ngày qua: 13 lần, trung bình 4,9 lần | Nhiều nhất là bc.api.kd với 5 lần, quản trị cần xem "
	"Error Log trước khi lỗi ảnh hưởng người dùng.")
eq("job_that_bai: nêu job lỗi nhiều nhất", render.fill(sig["ht.job_that_bai"].detail, p1).text.startswith(
	"Lỗi nhiều nhất ở bc.tasks.daily với 2 lượt"), True)
eq("mọi tín hiệu: quản trị, mảng he-thong, không route", {(s.audience, s.section, s.route) for s in sig.values()},
	{("quan-tri", H, "")})
eq("mọi lời dựng được", {k: ai_testlib.kiem_loi(s, p1) for k, s in sig.items() if ai_testlib.kiem_loi(s, p1)}, {})
dump = json.dumps(PACK, ensure_ascii=False, default=str)
eq("gói số không traceback / nội dung thư / lỗi SMTP / tên, email tài khoản / IP", [x for x in ("Traceback", "SECRET",
	"NOI-DUNG", "bimat", "Bí Mật", "10.9.8.7", "Incorrect password") if x in dump], [])

# Redis lỗi → detector _error → ht.hang_doi không chạy, quy tắc khác vẫn chạy.
BJ.FAKE_REDIS_DOWN = True
try:
	DU["u"] = Usage(1000, 500, 500)
	shutil.disk_usage = du_gia
	p2 = {H: registry.run_detectors(NOW)}
finally:
	BJ.FAKE_REDIS_DOWN = False
	shutil.disk_usage = _goc
eq("Redis lỗi → hang_doi = {_error: True}", p2[H]["hang_doi"], {"_error": True})
r2 = chay(p2)
eq("Redis lỗi → ht.hang_doi không chạy, 7 quy tắc còn lại chạy", (sorted(r2.not_run), len(r2.ran)), (["ht.hang_doi"], 7))
# Bảng thiếu → available False → quy tắc không chạy.
frappe.db.sql("DROP TABLE `tabEmail Queue`")
eq("bảng Email Queue thiếu → available False → ht.email_loi không chạy", (HT.d_email_loi(CTX),
	muc_all({H: {"email_loi": HT.d_email_loi(CTX)}}, "ht.email_loi")), ({"available": False}, "KHONG-CHAY"))

# ═══ D. Quy tắc trên pack dựng tay ═══════════════════════════════════════════
print("\nD. Quy tắc trên pack dựng tay")
EL = lambda tong, tb, nhom=None: {H: {"error_log": {"tong": tong, "tb_ngay": tb,  # noqa: E731
	"nhom": [{"method": "m", "so": 3}] if nhom is None else nhom}}}
K = "ht.error_log"
eq("error_log: đúng 2× trung bình (10 vs 5) → không; 11 → vàng", (muc_all(EL(10, 5), K), muc_all(EL(11, 5), K)),
	({}, {K: "vang"}))
eq("error_log: tb 0 — 9 không (< 10), 10 vàng (≥ 10)", (muc_all(EL(9, 0), K), muc_all(EL(10, 0), K)), ({}, {K: "vang"}))
eq("error_log: ghi đè vàng 3, đỏ 5: 16 vs 5 → vàng; 26 → đỏ; 15 → không",
	[muc_all(EL(v, 5), K, {"vang": 3, "do": 5}) for v in (16, 26, 15)], [{K: "vang"}, {K: "do"}, {}])
_, sg, pk = mot(EL(20, 1, nhom=[]), K)
eq("error_log: không nhóm → lời chung", (sg[K].detail, ai_testlib.kiem_loi(sg[K], pk)),
	("Quản trị cần xem Error Log trước khi lỗi ảnh hưởng người dùng.", []))
eq("error_log: None / thiếu / chuỗi → không", [muc_all(x, K) for x in (EL(None, 1), EL(20, None), EL("20", 1))],
	[{}, {}, {}])
K = "ht.job_that_bai"
JB = lambda n, loai=None: {H: {"job_that_bai": {"tong": n, "so_loai": 1, "loai": loai or []}}}  # noqa: E731
eq("job_that_bai: 0 không, 1 vàng; ghi đè đỏ 4: 5 đỏ", (muc_all(JB(0), K), muc_all(JB(1), K),
	muc_all(JB(5), K, {"do": 4})), ({}, {K: "vang"}, {K: "do"}))
K = "ht.email_loi"
eq("email_loi: 0 không, 1 vàng; tắt", (muc_all({H: {"email_loi": {"so": 0}}}, K),
	muc_all({H: {"email_loi": {"so": 1}}}, K), muc_all({H: {"email_loi": {"so": 9}}}, K, {"disabled": True})),
	({}, {K: "vang"}, {}))
K = "ht.hang_doi"
HD = lambda n: {H: {"hang_doi": {"cho": n, "so_hang": 2}}}  # noqa: E731
eq("hang_doi: 50 không, 51 vàng, 200 vàng, 201 đỏ", [muc_all(HD(v), K) for v in (50, 51, 200, 201)],
	[{}, {K: "vang"}, {K: "vang"}, {K: "do"}])
K = "ht.backup_cu"
BU = lambda co, gio: {H: {"backup_cu": {"co_ban": co, "gio": gio, "moi_nhat": None}}}  # noqa: E731
eq("backup_cu: 26 không, 26,1 đỏ, chưa có bản nào đỏ, ghi đè đỏ 48: 30 không",
	[muc_all(BU(True, 26.0), K), muc_all(BU(True, 26.1), K), muc_all(BU(False, None), K),
	muc_all(BU(True, 30), K, {"do": 48})], [{}, {K: "do"}, {K: "do"}, {}])
eq("backup_cu: co_ban None / gio None → không", (muc_all(BU(None, 99), K), muc_all(BU(True, None), K)), ({}, {}))
K = "ht.dia_day"
DD = lambda v: {H: {"dia_day": {"pct": v, "con_trong_gb": 12.5}}}  # noqa: E731
eq("dia_day: 85 không, 85,1 vàng, 93 vàng, 93,1 đỏ", [muc_all(DD(v), K) for v in (85, 85.1, 93, 93.1)],
	[{}, {K: "vang"}, {K: "vang"}, {K: "do"}])
K = "ht.dang_nhap_sai"
DN = lambda lan, moc="2000-01-01 00:00:00": {H: {"dang_nhap_sai": {"so_tk": len(lan), "tong": sum(lan),  # noqa: E731
	"max_lan": max(lan) if lan else 0, "lan": lan, "moc": moc}}}
eq("dang_nhap_sai: 10 không (ngặt), 11 vàng; ghi đè vàng 5 đỏ 20: [6, 21] đỏ", (muc_all(DN([10, 3]), K),
	muc_all(DN([11]), K), muc_all(DN([6, 21]), K, {"vang": 5, "do": 20})), ({}, {K: "vang"}, {K: "do"}))
_, sg, pk = mot(DN([30, 25, 11, 2]), K, {"vang": 20})
eq("dang_nhap_sai: ngưỡng ghi đè → đếm lại theo ngưỡng mới; pack khác lượt → không documents",
	(sg[K].tinh, sg[K].documents), ({"so_tk": 2, "nguong": 20}, []))
_, sg, pk = mot(DN([12, 11, 10], moc="2026-10-27 10:30:00"), K, {"vang": 11})
eq("dang_nhap_sai: cùng lượt detector → documents theo ngưỡng (> 11: không ai có thật)", sg[K].documents, [])
_, sg, pk = mot(DN([12, 11, 10], moc="2026-10-27 10:30:00"), K, {"vang": 9})
eq("dang_nhap_sai: > 9 → kt + ab", sg[K].documents, [{"doctype": "User", "name": "kt.bimat@hgc.vn"},
	{"doctype": "User", "name": "ab.bimat@hgc.vn"}])
eq("dang_nhap_sai: lan rỗng / rác → không", (muc_all(DN([]), K), muc_all({H: {"dang_nhap_sai": {"lan": None}}}, K),
	muc_all({H: {"dang_nhap_sai": {"lan": ["99", None, True]}}}, K)), ({}, {}, {}))
K = "ht.ai_loi"
AI = lambda n, h, hc=0: {H: {"ai_loi": {"so_luot": n, "that_bai": h, "het_credit": hc}}}  # noqa: E731
eq("ai_loi: 3/3 vàng; 2/3 không; 2/2 (ít lượt) không", (muc_all(AI(3, 3), K), muc_all(AI(3, 2), K),
	muc_all(AI(2, 2), K)), ({K: "vang"}, {}, {}))
_, sg, pk = mot(AI(3, 3, 2), K)
eq("ai_loi: có hết credit → lời nêu số lượt hết credit", render.fill(sg[K].detail, pk).text.startswith(
	"Có 2 lượt hết credit"), True)
eq("mọi nguồn _error / available False / thiếu → không chạy", sorted({k for k in RULES for blk in ({"_error": True},
	{"available": False}, None) if muc_all({H: {registry.RULES[k].sources[0].split(".")[1]: blk}} if blk else {H: {}}, k)
	!= "KHONG-CHAY"}), [])

# ═══ E. AST, riêng tư, lời ═══════════════════════════════════════════════════
print("\nE. AST, riêng tư, lời")
src = open(os.path.join(BC_ROOT, "bc", "ai", "detectors", "he_thong.py"), encoding="utf-8").read()
tree = ast.parse(src)
CAM = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|REPLACE|TRUNCATE|CREATE|GRANT)\b", re.I)
doc = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
	and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
sql = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
	and id(n) not in doc and re.search(r"\bSELECT\b", n.value)]
sql += [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) and "SELECT" in ast.unparse(n)]
c("có chuỗi SQL để soát (≥ 7)", len(sql) >= 7, len(sql))
eq("chuỗi SQL chỉ SELECT", [s[:50] for s in sql if CAM.search(s)], [])
eq("không NOW() / CURDATE() / SYSDATE trong SQL", [s[:50] for s in sql if re.search(r"NOW\(|CURDATE|SYSDATE|CURRENT_",
	s, re.I)], [])
eq("không đọc cột error / message / traceback / full_name / ip", [s[:60] for s in sql if re.search(
	r"\b(error|message|details|debug_log|full_name|ip_address|subject|content)\b", s.replace("Error Log", "").replace(
	"`tabError", ""))], [])
eq("không gọi db ghi (set_value / delete / insert / commit)", sorted({n.attr for n in ast.walk(tree)
	if isinstance(n, ast.Attribute) and n.attr in ("set_value", "delete", "insert", "commit", "save", "get_doc")}), [])
ht_fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("r_")]
eq("8 quy tắc r_* thuần: không frappe / os / shutil", (len(ht_fns), sorted({x.id for f in ht_fns for x in ast.walk(f)
	if isinstance(x, ast.Name) and x.id in ("frappe", "os", "shutil")})), (8, []))
c("có đủ ca để soát chung", len(MOI) > 30 and {s.rule for s, _ in MOI} == set(RULES), (len(MOI), {s.rule for s, _ in MOI}))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("lời / tinh không có tên tài khoản, email", sorted({bo_ph(s) for s, _ in MOI if re.search(r"bimat|@|Bí Mật", bo_ph(s))}
	| {f"{s.key}.{k}" for s, _ in MOI for k, v in s.tinh.items() if not isinstance(v, (int, float)) or isinstance(v, bool)}),
	[])
eq("documents chỉ ở ht.dang_nhap_sai, chỉ doctype User", sorted({(s.rule, d["doctype"]) for s, _ in MOI
	for d in s.documents}), [("ht.dang_nhap_sai", "User")])
eq("mọi lời dựng được trên pack của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, p)}" for s, p in MOI
	if ai_testlib.kiem_loi(s, p)}), [])
tu = lambda x: len(registry.PLACEHOLDER.sub("X", x).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khai báo quy tắc", {k: (r.section, r.sources, r.vang, r.do, r.audience, r.route) for k, r in registry.RULES.items()}, {
	"ht.error_log": (H, (f"{H}.error_log",), 2, None, "quan-tri", ""),
	"ht.job_that_bai": (H, (f"{H}.job_that_bai",), 0, None, "quan-tri", ""),
	"ht.email_loi": (H, (f"{H}.email_loi",), 0, None, "quan-tri", ""),
	"ht.hang_doi": (H, (f"{H}.hang_doi",), 50, 200, "quan-tri", ""),
	"ht.backup_cu": (H, (f"{H}.backup_cu",), None, 26, "quan-tri", ""),
	"ht.dia_day": (H, (f"{H}.dia_day",), 85, 93, "quan-tri", ""),
	"ht.dang_nhap_sai": (H, (f"{H}.dang_nhap_sai",), 10, None, "quan-tri", ""),
	"ht.ai_loi": (H, (f"{H}.ai_loi",), None, None, "quan-tri", "")})
eq("đủ 8 detector đăng ký", sorted(registry.DETECTORS), sorted(["error_log", "job_that_bai", "email_loi", "hang_doi",
	"backup_cu", "dia_day", "dang_nhap_sai", "ai_loi"]))

shutil.rmtree(TMP, ignore_errors=True)
c.done()
