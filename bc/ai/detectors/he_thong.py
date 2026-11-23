# -*- coding: utf-8 -*-
"""bc.ai.detectors.he_thong — detector hệ thống (đặc tả §4.2) + quy tắc ht.* đọc kết quả của chúng.

Detector: hàm(ctx) → dict, ctx = {"now": datetime, "today": date}; kết quả vào pack["he-thong"][<tên>].
SQL CHỈ SELECT, mốc thời gian truyền từ ctx (không NOW() / CURDATE()), bảng đọc mềm (frappe.db.table_exists).
Gói số CHỈ chứa số + tên method / tên job: KHÔNG traceback, KHÔNG nội dung lỗi / email, KHÔNG tên tài khoản.

Cửa sổ "24 giờ" = (now − 24 giờ, now]: bản ghi đúng 24 giờ trước KHÔNG tính.
- error_log: tong = số Error Log trong 24 giờ; tb_ngay = số Error Log trong 7 ngày TRƯỚC đó (now − 8
  ngày, now − 24 giờ] chia 7 (1 số lẻ); nhom = 5 nhãn nhiều nhất [{method, so}]. Cột `method` của v16 là TIÊU ĐỀ
  log (thường là str(exception) — có thể chứa email, tên khách, số điện thoại) → KHÔNG bao giờ vào pack nguyên văn:
  _nhan() rút về nhãn an toàn (tên Python có chấm: lớp lỗi …Error / Exception / Warning / Exit / Interrupt, hoặc
  ≥ 2 đoạn bắt đầu bằng tên app đã cài), còn lại "(khác)", trống "(không ghi)"; đếm theo nhãn bằng Python.
  Không đọc cột error.
- job_that_bai: Scheduled Job Log status Failed trong 24 giờ → tong, so_loai, loai = 5 job nhiều nhất
  [{job, so}].
- email_loi: Email Queue status Error trong 24 giờ → so.
- hang_doi: Σ count của frappe.utils.background_jobs.get_queues() → cho, so_hang. Redis lỗi → ném lỗi →
  bộ chạy ghi {"_error": True} (quy tắc không chạy).
- backup_cu: file mới nhất (mtime) trong get_backups_path() → co_ban, gio (số giờ tới now, 1 số lẻ), moi_nhat
  (ISO). mtime đổi sang giờ theo múi của SITE (get_system_timezone — như now_datetime của v16), không theo múi máy. Thư mục thiếu / không file → co_ban False, gio None (= chưa có bản sao lưu nào → đỏ).
- dia_day: shutil.disk_usage(get_site_path()) → pct (đã dùng / tổng × 100, 1 số lẻ), con_trong_gb.
- dang_nhap_sai: Activity Log operation Login status Failed trong 24 giờ, theo user → so_tk, tong, max_lan,
  lan (số lần mỗi tài khoản, giảm dần, ≤ 20; KHÔNG tên). Tên tài khoản (chỉ tài khoản User có thật) giữ trong
  bộ nhớ module (_TK, khớp theo `moc`) để quy tắc gắn vào Signal.documents — không bao giờ vào pack.
- ai_loi: 3 lượt chạy ĐÃ XONG gần nhất của BC AI Run (dòng tổng step "tong", finished có, run_type ≠ hoi-dap;
  lượt đang chạy — loi / "chưa hoàn tất", finished trống — bị bỏ). Lượt hỏng: dòng tổng loi, hoặc có dòng gọi
  mô hình (step ∉ {tong, ai}) và MỌI dòng đó loi / het-credit → so_luot, that_bai, het_credit.

Quy tắc ht.*: section "he-thong", audience "quan-tri", nguồn "he-thong.<tên>", hàm thuần trên pack.
"""

from __future__ import annotations

import datetime
import math
import os
import re
import shutil
from zoneinfo import ZoneInfo

import frappe

from bc.ai.registry import HE_THONG, detector, ph, resolve, rule

H = HE_THONG
TOP = 5                 # số nhóm method / job đưa vào gói số
TEN_MAX = 120           # cắt tên method / job
LAN_MAX = 20            # số tài khoản tối đa trong danh sách số lần đăng nhập sai
SAN_LOI = 10            # ht.error_log: tổng 24 giờ tối thiểu mới xét
KHONG_GHI = "(không ghi)"
KHAC = "(khác)"         # tiêu đề Error Log không phải tên Python an toàn
NHAN_MAX = 80
_TEN_PY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
_CAT = re.compile(r"[:(\[\s]")
_DUOI_LOI = ("Error", "Exception", "Warning", "Exit", "Interrupt")
APP_MAC_DINH = ("frappe", "erpnext", "bc")
MODEL_LOI = ("loi", "het-credit")
KHONG_GOI = ("tong", "ai")
_TK: dict = {"moc": None, "tk": []}     # [(user, số lần)] của lượt detector gần nhất — KHÔNG vào pack


def _moc(ctx):
	now = frappe.utils.get_datetime(ctx["now"])
	return now, now - datetime.timedelta(hours=24)


def _ten(v) -> str:
	s = str(v or "").strip()
	return s[:TEN_MAX] if s else KHONG_GHI


def _apps() -> set:
	try:
		return {str(a) for a in frappe.get_installed_apps()} or set(APP_MAC_DINH)
	except Exception:
		return set(APP_MAC_DINH)


def _nhan(v, apps) -> str:
	"""Tiêu đề Error Log → nhãn an toàn: chỉ tên lớp lỗi / tên method của app đã cài, còn lại "(khác)"."""
	s = str(v or "").strip()
	if not s:
		return KHONG_GHI
	dau = _CAT.split(s, 1)[0]
	if not dau or len(dau) > NHAN_MAX or not _TEN_PY.fullmatch(dau):
		return KHAC
	doan = dau.split(".")
	if doan[-1].endswith(_DUOI_LOI) or (len(doan) >= 2 and doan[0] in apps):
		return dau
	return KHAC


def _dem(doctype: str, where: str, args: dict) -> int:
	return frappe.utils.cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{doctype}` WHERE {where}", args)[0][0])


# ─── Detector ────────────────────────────────────────────────────────────────
@detector("error_log")
def d_error_log(ctx):
	if not frappe.db.table_exists("Error Log"):
		return {"available": False}
	now, tu = _moc(ctx)
	a = {"now": now, "tu": tu, "tu7": now - datetime.timedelta(days=8)}
	tong = _dem("Error Log", "creation > %(tu)s AND creation <= %(now)s", a)
	truoc = _dem("Error Log", "creation > %(tu7)s AND creation <= %(tu)s", a)
	rows = frappe.db.sql("""SELECT IFNULL(method, '') AS m, COUNT(*) AS n FROM `tabError Log`
		WHERE creation > %(tu)s AND creation <= %(now)s GROUP BY m""", a)
	apps, dem = _apps(), {}
	for m, n in rows:      # gộp theo NHÃN (tiêu đề thô không ra khỏi hàm này)
		k = _nhan(m, apps)
		dem[k] = dem.get(k, 0) + frappe.utils.cint(n)
	nhom = sorted(dem.items(), key=lambda x: (-x[1], x[0]))[:TOP]
	return {"tong": tong, "tb_ngay": round(truoc / 7.0, 1), "nhom": [{"method": k, "so": n} for k, n in nhom]}


@detector("job_that_bai")
def d_job_that_bai(ctx):
	if not frappe.db.table_exists("Scheduled Job Log"):
		return {"available": False}
	now, tu = _moc(ctx)
	rows = frappe.db.sql("""SELECT IFNULL(scheduled_job_type, '') AS j, COUNT(*) AS n FROM `tabScheduled Job Log`
		WHERE status = 'Failed' AND creation > %(tu)s AND creation <= %(now)s GROUP BY j ORDER BY n DESC, j ASC""",
		{"now": now, "tu": tu})
	return {"tong": sum(frappe.utils.cint(n) for _j, n in rows), "so_loai": len(rows),
		"loai": [{"job": _ten(j), "so": frappe.utils.cint(n)} for j, n in rows[:TOP]]}


@detector("email_loi")
def d_email_loi(ctx):
	if not frappe.db.table_exists("Email Queue"):
		return {"available": False}
	now, tu = _moc(ctx)
	return {"so": _dem("Email Queue", "status = 'Error' AND creation > %(tu)s AND creation <= %(now)s",
		{"now": now, "tu": tu})}


@detector("hang_doi")
def d_hang_doi(ctx):
	from frappe.utils.background_jobs import get_queues
	qs = list(get_queues())          # Redis không nối được → ném lỗi → {"_error": True}
	return {"cho": sum(frappe.utils.cint(getattr(q, "count", 0)) for q in qs), "so_hang": len(qs)}


@detector("backup_cu")
def d_backup_cu(ctx):
	now = frappe.utils.get_datetime(ctx["now"])
	thu_muc = frappe.utils.get_backups_path()
	moi = None
	if os.path.isdir(thu_muc):
		for f in os.listdir(thu_muc):
			p = os.path.join(thu_muc, f)
			if os.path.isfile(p):
				t = os.path.getmtime(p)
				moi = t if moi is None or t > moi else moi
	if moi is None:
		return {"co_ban": False, "gio": None, "moi_nhat": None}
	luc = _gio_site(moi)
	return {"co_ban": True, "gio": round((now - luc).total_seconds() / 3600.0, 1),
		"moi_nhat": luc.isoformat(sep=" ", timespec="seconds")}


def _gio_site(ts: float) -> datetime.datetime:
	"""Dấu thời gian → giờ ngây thơ theo múi của site (cùng gốc với now_datetime); lỗi múi → giờ máy."""
	try:
		return datetime.datetime.fromtimestamp(ts, ZoneInfo(frappe.utils.get_system_timezone())).replace(tzinfo=None)
	except Exception:
		return datetime.datetime.fromtimestamp(ts)


@detector("dia_day")
def d_dia_day(ctx):
	u = shutil.disk_usage(frappe.utils.get_site_path())
	if not u.total:
		return {"available": False}
	return {"pct": round(u.used * 100.0 / u.total, 1), "con_trong_gb": round(u.free / 1e9, 1)}


@detector("dang_nhap_sai")
def d_dang_nhap_sai(ctx):
	_TK.update(moc=None, tk=[])
	if not frappe.db.table_exists("Activity Log"):
		return {"available": False}
	now, tu = _moc(ctx)
	rows = frappe.db.sql("""SELECT IFNULL(`user`, '') AS u, COUNT(*) AS n FROM `tabActivity Log`
		WHERE operation = 'Login' AND status = 'Failed' AND creation > %(tu)s AND creation <= %(now)s
		GROUP BY u ORDER BY n DESC, u ASC""", {"now": now, "tu": tu})
	lan = [frappe.utils.cint(n) for _u, n in rows]
	moc = now.isoformat(sep=" ")
	_TK.update(moc=moc, tk=[(u, frappe.utils.cint(n)) for u, n in rows if u and frappe.db.exists("User", u)])
	return {"so_tk": len(rows), "tong": sum(lan), "max_lan": max(lan) if lan else 0, "lan": lan[:LAN_MAX],
		"moc": moc}


@detector("ai_loi")
def d_ai_loi(ctx):
	if not frappe.db.table_exists("BC AI Run"):
		return {"available": False}
	now = frappe.utils.get_datetime(ctx["now"])
	tong = frappe.db.sql("""SELECT name, status FROM `tabBC AI Run`
		WHERE step = 'tong' AND finished IS NOT NULL AND started <= %(now)s AND IFNULL(run_type, '') != 'hoi-dap'
		ORDER BY started DESC, name DESC LIMIT 3""", {"now": now}, as_dict=True)
	that_bai = het = 0
	if tong:
		con: dict = {}
		for r in frappe.db.sql("""SELECT run_id, step, status FROM `tabBC AI Run`
				WHERE run_id IN %(ids)s AND IFNULL(step, '') NOT IN %(bo)s""",
				{"ids": tuple(r.name for r in tong), "bo": KHONG_GOI}, as_dict=True):
			con.setdefault(r.run_id, []).append(r.status)
		for r in tong:
			goi = con.get(r.name, [])
			if r.status == "loi" or (goi and all(s in MODEL_LOI for s in goi)):
				that_bai += 1
			if "het-credit" in goi:
				het += 1
	return {"so_luot": len(tong), "that_bai": that_bai, "het_credit": het}


# ─── Quy tắc ht.* ────────────────────────────────────────────────────────────
def _so(v):
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _n(pack, path):
	return _so(resolve(pack, path, None))


def _chu(v) -> bool:
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= TEN_MAX


def _ht(key, ten, **kw):
	return rule(key, section=H, sources=[f"{H}.{ten}"], audience="quan-tri", **kw)


@_ht("ht.error_log", "error_log", vang=2, unit="lần trung bình",
	label="Lỗi hệ thống 24 giờ tăng vọt so với trung bình 7 ngày (và từ 10 lỗi)")
def r_error_log(pack, cfg):
	"""tong ≥ SAN_LOI và tong > ngưỡng × trung bình 7 ngày (vàng; đỏ nếu đặt ngưỡng đỏ)."""
	b = f"{H}.error_log"
	tong, tb = _n(pack, f"{b}.tong"), _n(pack, f"{b}.tb_ngay")
	if tong is None or tb is None or tong < SAN_LOI:
		return []
	vuot = lambda k: k is not None and tong > k * tb  # noqa: E731
	muc = "do" if vuot(cfg.do) else "vang" if vuot(cfg.vang) else None
	if not muc:
		return []
	nhom = resolve(pack, f"{b}.nhom", None)
	paths = [f"{b}.tong", f"{b}.tb_ngay"]
	if isinstance(nhom, list) and nhom and isinstance(nhom[0], dict) and _chu(nhom[0].get("method")) \
			and nhom[0].get("method") not in (KHAC, KHONG_GHI) and _so(nhom[0].get("so")) is not None:
		detail = (f"Nhiều nhất là {ph(f'{b}.nhom[0].method', 'chu')} với {ph(f'{b}.nhom[0].so', 'so')} lần, "
			"quản trị cần xem Error Log trước khi lỗi ảnh hưởng người dùng.")
	else:
		detail = "Quản trị cần xem Error Log trước khi lỗi ảnh hưởng người dùng."
	return [cfg.signal(muc, f"Lỗi hệ thống trong ngày qua: {ph(f'{b}.tong', 'so')} lần, trung bình "
		f"{ph(f'{b}.tb_ngay', 'so')} lần", detail=detail, paths=paths)]


@_ht("ht.job_that_bai", "job_that_bai", vang=0, unit="lượt", label="Tác vụ định kỳ thất bại trong 24 giờ")
def r_job_that_bai(pack, cfg):
	b = f"{H}.job_that_bai"
	muc = cfg.muc(_n(pack, f"{b}.tong"))
	if not muc:
		return []
	loai = resolve(pack, f"{b}.loai", None)
	if isinstance(loai, list) and loai and isinstance(loai[0], dict) and _chu(loai[0].get("job")) \
			and _so(loai[0].get("so")) is not None:
		detail = (f"Lỗi nhiều nhất ở {ph(f'{b}.loai[0].job', 'chu')} với {ph(f'{b}.loai[0].so', 'so')} lượt, "
			"việc chạy tự động có thể đang bị bỏ sót.")
	else:
		detail = "Việc chạy tự động có thể đang bị bỏ sót, quản trị cần xem nhật ký tác vụ."
	return [cfg.signal(muc, f"{ph(f'{b}.tong', 'so')} lượt tác vụ định kỳ thất bại trong ngày qua",
		detail=detail, paths=[f"{b}.tong"])]


@_ht("ht.email_loi", "email_loi", vang=0, unit="thư", label="Email gửi lỗi trong 24 giờ")
def r_email_loi(pack, cfg):
	p = f"{H}.email_loi.so"
	muc = cfg.muc(_n(pack, p))
	if not muc:
		return []
	return [cfg.signal(muc, f"{ph(p, 'so')} email gửi lỗi trong ngày qua",
		detail="Thư báo cho khách hoặc nội bộ có thể không tới nơi, quản trị cần kiểm tra tài khoản email.",
		paths=[p])]


@_ht("ht.hang_doi", "hang_doi", vang=50, do=200, unit="việc", label="Việc nền đang chờ trong hàng đợi")
def r_hang_doi(pack, cfg):
	p = f"{H}.hang_doi.cho"
	muc = cfg.muc(_n(pack, p))
	if not muc:
		return []
	return [cfg.signal(muc, f"{ph(p, 'so')} việc nền đang xếp hàng chờ chạy",
		detail="Hàng đợi dồn lâu làm báo cáo, email và đồng bộ bị trễ, quản trị cần kiểm tra tiến trình chạy nền.",
		paths=[p])]


@_ht("ht.backup_cu", "backup_cu", do=26, unit="giờ", label="Bản sao lưu mới nhất quá cũ")
def r_backup_cu(pack, cfg):
	b = f"{H}.backup_cu"
	co = resolve(pack, f"{b}.co_ban", None)
	if co is False:
		return [cfg.signal("do", "Không tìm thấy bản sao lưu dữ liệu nào",
			detail="Mất dữ liệu sẽ không khôi phục được, quản trị cần bật và kiểm tra sao lưu ngay.")]
	muc = cfg.muc(_n(pack, f"{b}.gio"))
	if co is not True or not muc:
		return []
	return [cfg.signal(muc, f"Bản sao lưu mới nhất đã cũ {ph(f'{b}.gio', 'so')} giờ",
		detail="Sao lưu tự động có thể đã ngừng, mất dữ liệu sẽ không khôi phục đủ.", paths=[f"{b}.gio"])]


@_ht("ht.dia_day", "dia_day", vang=85, do=93, unit="%", label="Ổ đĩa máy chủ sắp đầy")
def r_dia_day(pack, cfg):
	b = f"{H}.dia_day"
	muc = cfg.muc(_n(pack, f"{b}.pct"))
	if not muc:
		return []
	detail = "Đĩa đầy sẽ làm hệ thống ngừng ghi dữ liệu và sao lưu, quản trị cần dọn hoặc nới ổ đĩa."
	if _n(pack, f"{b}.con_trong_gb") is not None:
		detail = (f"Chỉ còn {ph(f'{b}.con_trong_gb', 'so')} GB trống, đĩa đầy sẽ làm hệ thống ngừng ghi dữ liệu "
			"và sao lưu.")
	return [cfg.signal(muc, f"Ổ đĩa máy chủ đã dùng {ph(f'{b}.pct', 'pct')}", detail=detail, paths=[f"{b}.pct"])]


@_ht("ht.dang_nhap_sai", "dang_nhap_sai", vang=10, unit="lần",
	label="Tài khoản đăng nhập sai nhiều lần trong 24 giờ")
def r_dang_nhap_sai(pack, cfg):
	"""Có tài khoản đăng nhập sai > ngưỡng lần trong 24 giờ → một tín hiệu (tên tài khoản chỉ ở documents)."""
	b = f"{H}.dang_nhap_sai"
	lan = resolve(pack, f"{b}.lan", None)
	if not isinstance(lan, list):
		return []
	so = [x for x in (_so(v) for v in lan) if x is not None]
	vuot = {m: sum(1 for x in so if getattr(cfg, m) is not None and x > getattr(cfg, m)) for m in ("vang", "do")}
	muc = "do" if vuot["do"] else "vang" if vuot["vang"] else None
	if not muc:
		return []
	nguong = cfg.do if muc == "do" else cfg.vang
	docs = []
	if _TK.get("moc") is not None and _TK.get("moc") == resolve(pack, f"{b}.moc", None):
		docs = [{"doctype": "User", "name": u} for u, n in _TK["tk"] if n > nguong]
	paths = [f"{b}.max_lan"] if _n(pack, f"{b}.max_lan") is not None else []
	detail = ("Có thể có người dò mật khẩu, quản trị cần kiểm tra tài khoản và khoá địa chỉ lạ.")
	if paths:
		detail = (f"Nhiều nhất {ph(f'{b}.max_lan', 'so')} lần, có thể có người dò mật khẩu, quản trị cần kiểm "
			"tra tài khoản.")
	return [cfg.signal(muc, "{{@so_tk|so}} tài khoản đăng nhập sai quá {{@nguong|so}} lần trong ngày qua",
		detail=detail, paths=paths, tinh={"so_tk": vuot[muc], "nguong": nguong}, documents=docs)]


@_ht("ht.ai_loi", "ai_loi", unit="lượt", label="Ba lượt chạy Trợ lý AI gần nhất đều lỗi / hết credit")
def r_ai_loi(pack, cfg):
	b = f"{H}.ai_loi"
	n, hong = _n(pack, f"{b}.so_luot"), _n(pack, f"{b}.that_bai")
	if n is None or hong is None or n < 3 or hong < n:
		return []
	detail = "Nhận định AI đang không được cập nhật, quản trị cần xem lỗi ở màn quản trị Trợ lý AI."
	if (_n(pack, f"{b}.het_credit") or 0) > 0:
		detail = (f"Có {ph(f'{b}.het_credit', 'so')} lượt hết credit, quản trị cần nạp thêm hoặc kiểm tra khoá "
			"của nhà cung cấp AI.")
	return [cfg.signal("vang", f"{ph(f'{b}.so_luot', 'so')} lượt chạy Trợ lý AI gần nhất đều lỗi",
		detail=detail, paths=[f"{b}.so_luot", f"{b}.that_bai"])]
