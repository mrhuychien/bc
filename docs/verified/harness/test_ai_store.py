"""Trợ lý AI — bc.ai.store (vòng đời BC AI Insight, nhật ký BC AI Run, dọn) và bc.ai.collect (gói số từ bc.api.*).

Đặc tả §3, §4 (vòng đời), §6.1, §6.2, §9.2 + AST của collect; hợp đồng chung §1 mục 6, 10, 11 và §2. Kỳ vọng TÍNH TAY
(phép tính / lần vết ghi trong comment), không chép từ đầu ra của code. Phần A (store) chạy trên hai bảng BC AI *;
phần B (collect) chạy trên seed gộp của bộ thử giao diện (seed_ui2: SX + công nợ + ATTP + vận chuyển + nhân sự + bán
hàng), gọi bc.api.* THẬT. Không phần nào đụng mạng (store / collect không import requests — AST chặn ở collect).

Chạy: BC_TEST_DB=bc_test_ai_store python3 -B test_ai_store.py
"""
import ast
import datetime
import importlib
import inspect
import json
import os
import re
import sys

from seed import Check, insert, reset, single
from paths import BC_ROOT

import frappe  # noqa: E402  (giả)
import ai_testlib  # noqa: E402

from bc.ai import collect, registry, store  # noqa: E402

c = Check()
D = datetime.datetime
ADMIN, VIEWER = "Administrator", "viewer@example.com"
INSIGHT, RUN = "BC AI Insight", "BC AI Run"
DEM0 = {"new": 0, "kept": 0, "reopened": 0, "closed": 0, "muted": 0}


def sig(key, severity="vang", section="cong-no", title=None, **kw):
	"""Một tín hiệu ĐÃ dựng lời như bc.ai.pipeline sẽ đưa cho store.sync_signals."""
	base = {"key": key, "rule": key.split(":")[0], "section": section, "audience": "lanh-dao", "severity": severity,
		"route": f"#/{section}", "title": title or f"Lời {key}", "body": f"Thân {key}", "paths": [f"{section}.x.y"],
		"sections_used": [section], "documents": []}
	base.update(kw)
	return base


def R(key):
	"""Dòng Insight theo khoá (so nhị phân — không theo collation) hoặc None."""
	r = frappe.db.sql(f"SELECT * FROM `tab{INSIGHT}` WHERE BINARY signal_key = %s", (key,), as_dict=True)
	return r[0] if r else None


def run_row(name):
	return frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE name = %s", (name,), as_dict=True)[0]


def dem(kq):
	"""Phần đếm của kết quả sync_signals (bỏ names)."""
	return {k: v for k, v in kq.items() if k != "names"}


def so(doctype=INSIGHT, where="1=1"):
	return frappe.db.sql(f"SELECT COUNT(*) FROM `tab{doctype}` WHERE {where}")[0][0]


def xoa():
	frappe.db.sql(f"DELETE FROM `tab{INSIGHT}`")
	frappe.db.sql(f"DELETE FROM `tab{RUN}`")


def dat(key, **fields):
	"""Sửa thẳng một dòng như quản trị bấm trên màn (bc.api.ai.set_status) — store không có hàm này."""
	frappe.db.set_value(INSIGHT, R(key).name, fields)


def nem(fn, loi):
	try:
		fn()
	except loi:
		return True
	except Exception:  # noqa: BLE001
		return False
	return False


# ═══════════════════════════════════════════════════════════════════════════
print("A. bc.ai.store")
reset(only={INSIGHT, RUN})
frappe.session.user = ADMIN

print("A1. Mới → còn → hết thì đóng → xuất hiện lại thì mở; quy tắc không chạy được thì giữ nguyên")
A, B, C = "cn.qua_han_ty_le", "attp.den_do:QC", "vc.cho_qua_han"
RAN = {"cn.qua_han_ty_le", "attp.den_do", "vc.cho_qua_han", "kho.ton_am"}   # kho.ton_am chạy, không có tín hiệu
sA = sig(A, title="Nợ quá hạn chiếm 25,0% phải thu", body="Tổng quá hạn 55 triệu.",
	paths=["cong-no.receivables.kpis.overdue_pct"], documents=[{"doctype": "Sales Invoice", "name": "INV2"}])
sB = sig(B, "do", "attp", title="Lĩnh vực Kiểm nghiệm đang đỏ")
sC = sig(C, section="van-chuyen")
T1 = D(2026, 10, 27, 5, 30)
kq = store.sync_signals([sA, sB, sC], RAN, T1)
c("lượt đầu: 3 mới, không gì khác", dem(kq) == {**DEM0, "new": 3}, kq)
a = R(A)
c("names: đủ 3 khoá, trỏ đúng dòng", set(kq["names"]) == {A, B, C} and kq["names"][A] == a.name
	and kq["names"][C] == R(C).name, kq["names"])
c("mới: status mo, first_seen = last_seen = text_at = now, seen_count 1, chưa đóng, chưa xếp hạng",
	(a.status, a.first_seen, a.last_seen, a.text_at, a.seen_count, a.closed_on, a.mute_until, a["rank"])
	== ("mo", T1, T1, T1, 1, None, None, 0), a)
c("mới: lời quy tắc — source quy-tac, title = rule_title, advice rỗng, needs_check 0, priority 0",
	(a.source, a.title, a.rule_title, a.body, a.advice, a.needs_check, a.priority) == ("quy-tac",
	"Nợ quá hạn chiếm 25,0% phải thu", "Nợ quá hạn chiếm 25,0% phải thu", "Tổng quá hạn 55 triệu.", "", 0, 0), a)
c("mới: rule / section / audience / severity / route đúng như tín hiệu",
	(a.rule, a.section, a.audience, a.severity, a.route) == (A, "cong-no", "lanh-dao", "vang", "#/cong-no"), a)
c("field JSON là CHUỖI json (list tự dump): paths, documents", isinstance(a.paths, str)
	and json.loads(a.paths) == ["cong-no.receivables.kpis.overdue_pct"]
	and json.loads(a.documents) == [{"doctype": "Sales Invoice", "name": "INV2"}], (a.paths, a.documents))
c("khoá có đối tượng: rule là phần trước dấu ':' như nơi gọi đưa", R(B).rule == "attp.den_do" and R(B).severity == "do")

# Lượt 2 CÙNG NGÀY (quản trị bấm "Chạy ngay" lúc 15:00): tín hiệu A lên đỏ, lời + path đổi.
T1b = D(2026, 10, 27, 15, 0)
sA2 = sig(A, "do", title="Nợ quá hạn chiếm 40,0% phải thu", body="Tổng quá hạn 88 triệu.",
	paths=["cong-no.receivables.kpis.overdue_pct", "cong-no.receivables.kpis.overdue"])
kq = store.sync_signals([sA2, sB, sC], RAN, T1b)
a = R(A)
c("còn: 3 giữ, không tạo dòng mới", dem(kq) == {**DEM0, "kept": 3} and so() == 3, kq)
c("còn: cập nhật last_seen, severity, paths, lời (title + rule_title + body), text_at",
	(a.last_seen, a.severity, json.loads(a.paths), a.title, a.rule_title, a.body, a.text_at) == (T1b, "do",
	["cong-no.receivables.kpis.overdue_pct", "cong-no.receivables.kpis.overdue"], "Nợ quá hạn chiếm 40,0% phải thu",
	"Nợ quá hạn chiếm 40,0% phải thu", "Tổng quá hạn 88 triệu.", T1b), a)
c("còn: first_seen giữ nguyên; chạy lần 2 trong ngày KHÔNG tăng seen_count (vẫn 1)",
	(a.first_seen, a.seen_count) == (T1, 1), (a.first_seen, a.seen_count))

# Ngày 28: C hết (quy tắc vc.cho_qua_han có chạy) → đóng. A, B còn → seen_count 2 (ngày 27, 28).
T2 = D(2026, 10, 28, 5, 30)
kq = store.sync_signals([sA2, sB], RAN, T2)
c("ngày 2: 2 giữ, 1 đóng", dem(kq) == {**DEM0, "kept": 2, "closed": 1}, kq)
c("ngày 2: seen_count A = B = 2", (R(A).seen_count, R(B).seen_count) == (2, 2))
x = R(C)
c("hết tín hiệu, quy tắc đã chạy → dong, closed_on = now; last_seen / seen_count giữ như lần cuối còn thấy",
	(x.status, x.closed_on, x.last_seen, x.seen_count) == ("dong", T2, T1b, 1), x)
T2b = D(2026, 10, 28, 9, 0)
kq = store.sync_signals([sA2, sB], RAN, T2b)
c("lượt thứ ba trong ngày 28: seen_count vẫn 2; dòng đã đóng không bị đóng lại (closed_on giữ)",
	dem(kq) == {**DEM0, "kept": 2} and R(A).seen_count == 2 and R(C).closed_on == T2, kq)

# Ngày 30 (ngày 29 không chạy): C xuất hiện lại; attp.den_do KHÔNG chạy được (khối nguồn _error → không nằm trong ran).
T3 = D(2026, 10, 30, 5, 30)
kq = store.sync_signals([sA2, sig(C, section="van-chuyen", title="Lại có đơn chờ quá hạn")], RAN - {"attp.den_do"}, T3)
c("ngày 30: 1 giữ, 1 mở lại, không đóng gì", dem(kq) == {**DEM0, "kept": 1, "reopened": 1}, kq)
c("seen_count đếm NGÀY thấy: A = 3 (27, 28, 30)", R(A).seen_count == 3, R(A).seen_count)
x = R(C)
c("dong rồi xuất hiện lại → mo, first_seen = now, seen_count về 1, closed_on xoá, lời mới",
	(x.status, x.first_seen, x.last_seen, x.seen_count, x.closed_on, x.title)
	== ("mo", T3, T3, 1, None, "Lại có đơn chờ quá hạn"), x)
x = R(B)
c("quy tắc không chạy được → Insight GIỮ NGUYÊN (không đóng, không đổi last_seen / seen_count)",
	(x.status, x.last_seen, x.seen_count, x.closed_on) == ("mo", T2b, 2, None), x)
c("mở lại dùng đúng dòng cũ (không tạo dòng thứ hai)", so() == 3 and kq["names"][C] == R(C).name, kq["names"])

# Ngày 31: quy tắc cn.qua_han_ty_le bị TẮT → vẫn nằm trong ran, không sinh tín hiệu → Insight của nó đóng.
T4 = D(2026, 10, 31, 5, 30)
kq = store.sync_signals([], {"cn.qua_han_ty_le"}, T4)
c("quy tắc tắt (có trong ran, không tín hiệu) → đóng đúng 1", dem(kq) == {**DEM0, "closed": 1}
	and (R(A).status, R(A).closed_on) == ("dong", T4), kq)
c("quy tắc ngoài ran: B, C không bị đụng", (R(B).status, R(B).last_seen, R(C).status, R(C).last_seen)
	== ("mo", T2b, "mo", T3))
kq = store.sync_signals([], set(), D(2026, 11, 1, 5, 30))
c("ran rỗng + không tín hiệu → không đổi gì", dem(kq) == DEM0 and kq["names"] == {} and R(B).status == "mo", kq)
kq = store.sync_signals([], ["attp.den_do", "vc.cho_qua_han"], D(2026, 11, 2, 5, 30))   # ran dạng list
c("ran là list cũng được: đóng nốt B, C", dem(kq) == {**DEM0, "closed": 2} and so(where="status = 'dong'") == 3, kq)

print("A2. dang-xu-ly giữ trạng thái khi tín hiệu còn")
xoa()
X = "cn.dso_cao"
store.sync_signals([sig(X)], {X}, D(2026, 10, 27, 5, 30))
dat(X, status="dang-xu-ly", admin_note="Kế toán đang đòi")
kq = store.sync_signals([sig(X, title="DSO vẫn cao")], {X}, D(2026, 10, 28, 5, 30))
x = R(X)
c("còn tín hiệu: vẫn dang-xu-ly, lời cập nhật, seen_count 2, ghi chú quản trị còn",
	dem(kq) == {**DEM0, "kept": 1} and (x.status, x.title, x.seen_count, x.admin_note)
	== ("dang-xu-ly", "DSO vẫn cao", 2, "Kế toán đang đòi"), x)
kq = store.sync_signals([], {X}, D(2026, 10, 29, 5, 30))
c("hết tín hiệu: dang-xu-ly → dong", dem(kq) == {**DEM0, "closed": 1} and R(X).status == "dong", kq)
kq = store.sync_signals([sig(X)], {X}, D(2026, 11, 5, 5, 30))
x = R(X)
c("xuất hiện lại: mo (không còn dang-xu-ly), first_seen mới, ghi chú quản trị vẫn giữ",
	dem(kq) == {**DEM0, "reopened": 1} and (x.status, x.first_seen, x.seen_count, x.admin_note)
	== ("mo", D(2026, 11, 5, 5, 30), 1, "Kế toán đang đòi"), x)

print("A3. bo-qua: còn hạn không tự đóng / mở; hết hạn còn tín hiệu → mo, hết tín hiệu → dong; bỏ qua hẳn")
xoa()
M1, M2, M3, M4 = "kho.ton_am", "kho.het_han", "kho.can_date", "kho.ton_chet"
RAN3 = {M1, M2, M3}   # quy tắc của M4 (kho.ton_chet) không chạy được suốt đoạn này
T0 = D(2026, 11, 1, 5, 30)
store.sync_signals([sig(k, section="han-dung") for k in (M1, M2, M3, M4)], RAN3 | {M4}, T0)
HAN = datetime.date(2026, 11, 5)
dat(M1, status="bo-qua", mute_until=HAN)      # bỏ qua tới hết 05/11, tín hiệu CÒN suốt
dat(M2, status="bo-qua", mute_until=HAN)      # bỏ qua tới hết 05/11, tín hiệu HẾT
dat(M3, status="bo-qua", mute_until=None)     # bỏ qua hẳn
dat(M4, status="bo-qua", mute_until=HAN)      # quy tắc không chạy
m1v2 = sig(M1, "do", "han-dung", title="Tồn âm tăng")
m3v2 = sig(M3, section="han-dung", title="Cận date tăng")
N3 = D(2026, 11, 3, 5, 30)
kq = store.sync_signals([m1v2, m3v2], RAN3, N3)
x = R(M1)
c("còn hạn + còn tín hiệu: đếm vào muted, không mở, không đóng", dem(kq) == {**DEM0, "muted": 2}, kq)
c("… vẫn bo-qua, mute_until giữ; lời + severity + last_seen cập nhật; seen_count 2 (01/11, 03/11)",
	(x.status, x.mute_until, x.title, x.severity, x.last_seen, x.seen_count, x.first_seen)
	== ("bo-qua", HAN, "Tồn âm tăng", "do", N3, 2, T0), x)
x = R(M2)
c("còn hạn + HẾT tín hiệu (quy tắc đã chạy): không tự đóng", (x.status, x.closed_on, x.last_seen, x.mute_until)
	== ("bo-qua", None, T0, HAN), x)
kq = store.sync_signals([m1v2, m3v2], RAN3, D(2026, 11, 5, 23, 0))
c("đúng ngày mute_until (05/11, 23:00): VẪN còn hạn", dem(kq) == {**DEM0, "muted": 2}
	and (R(M1).status, R(M1).seen_count, R(M2).status) == ("bo-qua", 3, "bo-qua"), kq)
N6 = D(2026, 11, 6, 5, 30)
kq = store.sync_signals([m1v2, m3v2], RAN3, N6)
c("06/11: M1 mở lại, M3 vẫn tắt, M2 đóng", dem(kq) == {**DEM0, "reopened": 1, "muted": 1, "closed": 1}, kq)
x = R(M1)
c("hết hạn + còn tín hiệu → mo, mute_until xoá, GIỮ first_seen (việc kéo dài từ 01/11), seen_count 4",
	(x.status, x.mute_until, x.first_seen, x.seen_count, x.last_seen) == ("mo", None, T0, 4, N6), x)
x = R(M2)
c("hết hạn + hết tín hiệu → dong, closed_on = now, mute_until xoá", (x.status, x.closed_on, x.mute_until)
	== ("dong", N6, None), x)
x = R(M4)
c("bo-qua hết hạn nhưng quy tắc KHÔNG chạy → giữ nguyên", (x.status, x.mute_until, x.last_seen)
	== ("bo-qua", HAN, T0), x)
kq = store.sync_signals([], RAN3, D(2027, 1, 1, 5, 30))
c("bỏ qua hẳn (mute_until trống) + hết tín hiệu: KHÔNG bao giờ tự đóng (chỉ M1 đóng)",
	dem(kq) == {**DEM0, "closed": 1} and (R(M3).status, R(M3).closed_on) == ("bo-qua", None), kq)
kq = store.sync_signals([m3v2], RAN3, D(2027, 1, 2, 5, 30))
c("bỏ qua hẳn + tín hiệu còn sau 2 tháng: vẫn bo-qua", dem(kq) == {**DEM0, "muted": 1}
	and (R(M3).status, R(M3).last_seen) == ("bo-qua", D(2027, 1, 2, 5, 30)), kq)
kq = store.sync_signals([sig(M4, section="han-dung")], {M4}, D(2027, 1, 3, 5, 30))
c("M4: quy tắc chạy lại, hạn đã qua, còn tín hiệu → mo", dem(kq) == {**DEM0, "reopened": 1}
	and (R(M4).status, R(M4).mute_until) == ("mo", None), kq)
c("tín hiệu bo-qua không gửi mô hình: open_for_llm chỉ thấy M4", [r["signal_key"]
	for r in store.open_for_llm(("han-dung",), 40)] == [M4])

print("A4. Khoá, độ dài, JSON, sections_used")
xoa()
TA = D(2026, 10, 27, 5, 30)
K150 = "t.dai:" + "x" * 144                       # 6 + 144 = 150 ký tự
kq = store.sync_signals([sig(K150, rule="t.dai")], set(), TA)
x = R(K150[:140])
c("signal_key cắt 140; names vẫn theo khoá GỐC nơi gọi đưa", x is not None and len(x.signal_key) == 140
	and kq["names"] == {K150: x.name}, kq)
kq = store.sync_signals([sig(K150, rule="t.dai")], set(), D(2026, 10, 28, 5, 30))
c("lượt sau cùng khoá dài: nhận ra dòng cũ (kept), không chèn dòng thứ hai", dem(kq) == {**DEM0, "kept": 1}
	and so() == 1 and kq["names"][K150] == x.name, kq)
K151 = K150 + "y"                                   # khác K150 ở ký tự thứ 151 → trùng sau khi cắt
kq = store.sync_signals([sig("t.trung", title="đầu"), sig("t.trung", title="sau"),
	sig(K150, rule="t.dai", title="dài đầu"), sig(K151, rule="t.dai", title="dài sau")], set(), D(2026, 10, 28, 6, 0))
c("trùng khoá trong một lượt (kể cả trùng sau khi cắt): mục ĐẦU thắng", dem(kq) == {**DEM0, "new": 1, "kept": 1}
	and R("t.trung").title == "đầu" and R(K150[:140]).title == "dài đầu" and so() == 2
	and kq["names"][K151] == kq["names"][K150], kq)
store.sync_signals([sig("t.hoa:ABC", rule="t.hoa")], set(), TA)
kq = store.sync_signals([sig("t.hoa:abc", rule="t.hoa", title="chữ thường")], set(), D(2026, 10, 28, 5, 30))
x = R("t.hoa:ABC")
c("khoá chỉ khác HOA / thường (cột unique so không phân biệt): cập nhật dòng cũ, không chèn trùng",
	dem(kq) == {**DEM0, "kept": 1} and so(where="rule = 't.hoa'") == 1 and x.title == "chữ thường"
	and kq["names"] == {"t.hoa:abc": x.name}, kq)
kq = store.sync_signals([sig("t.dau:Miền", rule="t.dau", title="có dấu"), sig("t.dau:mien", rule="t.dau")], set(), TA)
c("hai khoá chỉ khác dấu trong CÙNG một lượt: một dòng, mục đầu thắng", dem(kq) == {**DEM0, "new": 1}
	and so(where="rule = 't.dau'") == 1 and R("t.dau:Miền").title == "có dấu"
	and kq["names"]["t.dau:mien"] == kq["names"]["t.dau:Miền"], kq)
kq = store.sync_signals([sig("", rule="t.rong"), sig("   ", rule="t.rong")], set(), TA)
c("khoá trống bị bỏ qua", dem(kq) == DEM0 and so(where="rule = 't.rong'") == 0, kq)
DOCS = [{"doctype": "Sales Invoice", "name": f"SI-{i:02d}"} for i in range(25)]
store.sync_signals([sig("t.cat", title="T" * 250, documents=DOCS, paths=["a.b", "a.b", "c.d", "tồn-kho.x"],
	section="attp", sections_used=["cong-no", "phai-tra", "cong-no"]),
	sig("ht.error_log", "do", "he-thong", audience="quan-tri", route="", sections_used=[])], set(), TA)
x = R("t.cat")
c("title và rule_title cắt 200 ký tự", (len(x.title), len(x.rule_title), x.title) == (200, 200, "T" * 200))
c("documents giữ 20 chứng từ đầu", [d["name"] for d in json.loads(x.documents)] == [f"SI-{i:02d}" for i in range(20)])
c("paths bỏ trùng, giữ thứ tự, giữ chữ có dấu (không \\u)", json.loads(x.paths) == ["a.b", "c.d", "tồn-kho.x"]
	and "tồn-kho" in x.paths, x.paths)
c("sections_used: mỗi dòng một mã, bỏ trùng, luôn gồm mảng chính", x.sections_used == "cong-no\nphai-tra\nattp",
	repr(x.sections_used))
x = R("ht.error_log")
c("tín hiệu hệ thống: audience quan-tri, route rỗng, sections_used = mảng chính",
	(x.audience, x.route, x.sections_used, x.section) == ("quan-tri", "", "he-thong", "he-thong"), x)

print("A5. Khớp với bc.ai.registry.run_rules: _error → không trong ran → giữ; tắt → trong ran → đóng")
xoa()
ai_testlib.chi_module()   # không nạp module quy tắc nào (agent khác đang viết) — đăng ký một quy tắc thử ngay đây


@registry.rule("thu.qua_han", section="cong-no", sources="cong-no.receivables", vang=20, do=35)
def _thu(pack, cfg):
	muc = cfg.muc(pack["cong-no"]["receivables"]["kpis"]["overdue_pct"])
	return [cfg.signal(muc, "Quá hạn {{cong-no.receivables.kpis.overdue_pct|pct}}")] if muc else []


def chay_quy_tac(pack, now, overrides=None):
	rr = registry.run_rules(pack, overrides, only={"thu.qua_han"})
	items = [{"key": s.key, "rule": s.rule, "section": s.section, "audience": s.audience, "severity": s.severity,
		"route": s.route, "title": s.title, "body": s.detail, "paths": s.paths,
		"sections_used": sorted({registry.section_of(p) for p in s.paths}), "documents": s.documents} for s in rr.signals]
	return rr, store.sync_signals(items, rr.ran, now)


def goi_so(pct):
	return {"cong-no": {"receivables": {"kpis": {"overdue_pct": pct}}}}


rr, kq = chay_quy_tac(goi_so(40), D(2026, 10, 27, 5, 30))   # 40 > 35 → đỏ
x = R("thu.qua_han")
c("quy tắc thật sinh tín hiệu đỏ → Insight mo, route mặc định của mảng", dem(kq) == {**DEM0, "new": 1}
	and (x.status, x.severity, x.route, x.sections_used) == ("mo", "do", "#/cong-no", "cong-no"), x)
rr, kq = chay_quy_tac({"cong-no": {"receivables": {"_error": True}}}, D(2026, 10, 28, 5, 30))
x = R("thu.qua_han")
c("khối nguồn _error: quy tắc không trong ran → Insight giữ nguyên", "thu.qua_han" not in rr.ran
	and dem(kq) == DEM0 and (x.status, x.last_seen, x.seen_count) == ("mo", D(2026, 10, 27, 5, 30), 1), (rr, kq))
rr, kq = chay_quy_tac(goi_so(40), D(2026, 10, 29, 5, 30), {"thu.qua_han": {"disabled": True}})
c("quy tắc bị tắt: có trong ran, không tín hiệu → Insight đóng", "thu.qua_han" in rr.ran and rr.signals == []
	and dem(kq) == {**DEM0, "closed": 1} and R("thu.qua_han").status == "dong", (rr, kq))
rr, kq = chay_quy_tac(goi_so(25), D(2026, 10, 30, 5, 30))   # 20 < 25 ≤ 35 → vàng
c("bật lại, còn vượt ngưỡng vàng → mở lại với mức vàng", dem(kq) == {**DEM0, "reopened": 1}
	and (R("thu.qua_han").status, R("thu.qua_han").severity) == ("mo", "vang"), kq)
rr, kq = chay_quy_tac(goi_so(10), D(2026, 10, 31, 5, 30))   # 10 ≤ 20 → chạy, không tín hiệu
c("chạy được, dưới ngưỡng → đóng", dem(kq) == {**DEM0, "closed": 1} and R("thu.qua_han").status == "dong", kq)

print("A6. open_for_llm: lọc + thứ tự (đỏ trước, rồi first_seen MỚI trước) + giới hạn")
xoa()
NHOM = ("cong-no", "phai-tra")
for key, muc, mang, ngay in (("cn.a", "vang", "cong-no", 1), ("cn.b", "do", "phai-tra", 5), ("cn.c", "do", "cong-no", 10),
		("cn.g", "vang", "cong-no", 15), ("cn.e", "do", "cong-no", 21), ("cn.f", "do", "cong-no", 22),
		("ns.a", "do", "nhan-su", 23)):
	store.sync_signals([sig(key, muc, mang, paths=[f"{mang}.p1", f"{mang}.p2"])], set(), D(2026, 10, ngay, 5, 30))
store.sync_signals([sig("cn.h"), sig("cn.d")], set(), D(2026, 10, 20, 5, 30))   # cùng mức, cùng first_seen
dat("cn.e", status="bo-qua", mute_until=None)
store.sync_signals([], {"cn.f"}, D(2026, 10, 24, 5, 30))                          # cn.f đóng
dat("cn.g", status="dang-xu-ly", admin_note="Kế toán đang đối chiếu")
store.sync_ai_free(NHOM, [{"key": "ai:cong-no.receivables.kpis.total", "section": "cong-no", "route": "#/cong-no",
	"severity": "do", "priority": 1, "title": "Tự do", "body": "", "advice": [], "paths": [], "sections_used": []}],
	D(2026, 10, 25, 5, 30))
ds = store.open_for_llm(NHOM, 40)
# đỏ: cn.c (10/10) rồi cn.b (05/10); vàng: cn.d, cn.h (20/10, cùng lúc → theo khoá), cn.g (15/10), cn.a (01/10).
# Không có: cn.e (bo-qua), cn.f (dong), ai:… (nhận định tự do), ns.a (mảng ngoài nhóm).
c("đỏ trước, trong mức thì first_seen mới trước, cùng lúc theo khoá; bỏ bo-qua / dong / ai / mảng khác",
	[r["signal_key"] for r in ds] == ["cn.c", "cn.b", "cn.d", "cn.h", "cn.g", "cn.a"], [r["signal_key"] for r in ds])
c("giới hạn 3 → 3 dòng đầu", [r["signal_key"] for r in store.open_for_llm(NHOM, 3)] == ["cn.c", "cn.b", "cn.d"])
g = next(r for r in ds if r["signal_key"] == "cn.g")
c("mỗi dòng đúng 9 khoá của hợp đồng", set(g) == {"name", "signal_key", "rule", "section", "severity", "status",
	"first_seen", "admin_note", "paths"}, sorted(g))
c("giá trị một dòng: dang-xu-ly, ghi chú quản trị, first_seen, paths là LIST", g == {"name": R("cn.g").name,
	"signal_key": "cn.g", "rule": "cn.g", "section": "cong-no", "severity": "vang", "status": "dang-xu-ly",
	"first_seen": D(2026, 10, 15, 5, 30), "admin_note": "Kế toán đang đối chiếu",
	"paths": ["cong-no.p1", "cong-no.p2"]}, g)
c("limit 0 / âm → rỗng; nhóm rỗng → rỗng; nhóm khác → tín hiệu của nhóm đó", store.open_for_llm(NHOM, 0) == []
	and store.open_for_llm(NHOM, -1) == [] and store.open_for_llm((), 40) == []
	and [r["signal_key"] for r in store.open_for_llm(["nhan-su"], 40)] == ["ns.a"]
	and store.open_for_llm(("he-thong",), 40) == [])

print("A7. apply_ai (mô hình không hạ được đỏ; paths / sections_used = HỢP) và mark_rejected")
xoa()
TA = D(2026, 10, 27, 5, 30)
P_QT = ["cong-no.receivables.kpis.overdue_pct", "cong-no.receivables.kpis.overdue"]
quy_tac = [sig("cn.p1", "vang", title="Lời quy tắc P1", body="Thân quy tắc P1", paths=P_QT),
	sig("cn.p2", "do", title="Lời quy tắc P2"), sig("cn.p3", "vang", title="Lời quy tắc P3", body="Thân quy tắc P3")]
ten = store.sync_signals(quy_tac, set(), TA)["names"]
store.mark_rejected(ten["cn.p1"])   # lượt trước lời AI của P1 bị loại → apply_ai phải xoá cờ
TB = D(2026, 10, 27, 5, 31)
store.apply_ai(ten["cn.p1"], title="Nợ quá hạn tăng nhanh", body="Thân AI",
	advice=["Kế toán: gọi 3 khách lớn nhất.", "Kinh doanh:\n tạm dừng giao", "  ", "Kế toán: gọi 3 khách lớn nhất."],
	severity="do", priority=7, paths=["cong-no.receivables.kpis.overdue", "phai-tra.payables.cash.total"],
	sections_used=["phai-tra", "cong-no"], now=TB)
x = R("cn.p1")
c("lời AI: title, body, source ai, text_at = now, needs_check 0, priority",
	(x.title, x.body, x.source, x.text_at, x.needs_check, x.priority)
	== ("Nợ quá hạn tăng nhanh", "Thân AI", "ai", TB, 0, 7), x)
c("advice: mỗi dòng một khuyến nghị (xuống dòng bên trong gộp lại, bỏ mục trống / trùng)",
	x.advice == "Kế toán: gọi 3 khách lớn nhất.\nKinh doanh: tạm dừng giao", repr(x.advice))
c("mô hình NÂNG vàng → đỏ được", x.severity == "do", x.severity)
# quy tắc [overdue_pct, overdue] ∪ AI [overdue, cash.total] = 3 path, thứ tự quy tắc trước
c("paths = hợp của quy tắc và lời AI", json.loads(x.paths) == [*P_QT, "phai-tra.payables.cash.total"], x.paths)
c("sections_used = hợp: cong-no (quy tắc) + phai-tra (AI)", x.sections_used == "cong-no\nphai-tra", repr(x.sections_used))
c("rule_title vẫn là lời quy tắc; trạng thái / first_seen / seen_count không đổi",
	(x.rule_title, x.status, x.first_seen, x.last_seen, x.seen_count) == ("Lời quy tắc P1", "mo", TA, TA, 1), x)
kw = dict(title="AI P2", body="b", advice=[], priority=1, paths=[], sections_used=[], now=TB)
store.apply_ai(ten["cn.p2"], severity="vang", **kw)
c("mô hình hạ đỏ → vàng: VẪN đỏ", R("cn.p2").severity == "do" and R("cn.p2").source == "ai", R("cn.p2").severity)
store.apply_ai(ten["cn.p2"], severity="xanh", **kw)
store.apply_ai(ten["cn.p3"], severity="xanh", **{**kw, "title": "A" * 250})
c("mức lạ từ mô hình: giữ mức đang có (đỏ vẫn đỏ, vàng vẫn vàng)", (R("cn.p2").severity, R("cn.p3").severity)
	== ("do", "vang"))
c("title lời AI cắt 200", R("cn.p3").title == "A" * 200, len(R("cn.p3").title))
c("apply_ai không đụng paths / sections_used của quy tắc khi lời AI không thêm gì",
	(json.loads(R("cn.p2").paths), R("cn.p2").sections_used) == (["cong-no.x.y"], "cong-no"), R("cn.p2").paths)
c("apply_ai vào Insight không tồn tại → DoesNotExistError, không tạo dòng",
	nem(lambda: store.apply_ai("KHONG-CO", severity="do", **kw), frappe.DoesNotExistError) and so() == 3)
# Lời bị loại: tín hiệu giữ lời quy tắc, chỉ bật cờ.
store.sync_signals([quy_tac[2]], set(), D(2026, 10, 27, 6, 0))   # P3 về lời quy tắc
store.mark_rejected(ten["cn.p3"])
x = R("cn.p3")
c("mark_rejected: needs_check 1, lời quy tắc giữ nguyên (title, body, source)",
	(x.needs_check, x.title, x.body, x.source) == (1, "Lời quy tắc P3", "Thân quy tắc P3", "quy-tac"), x)
# Lượt chạy hôm sau: mọi tín hiệu về lời quy tắc trước khi mô hình viết lại.
T_SAU = D(2026, 10, 28, 5, 30)
store.sync_signals(quy_tac, set(), T_SAU)
x = R("cn.p1")
c("lượt sau: về lời quy tắc — source quy-tac, title, body, advice rỗng, priority 0, text_at mới",
	(x.source, x.title, x.body, x.advice, x.priority, x.text_at)
	== ("quy-tac", "Lời quy tắc P1", "Thân quy tắc P1", "", 0, T_SAU), x)
c("lượt sau: mức về mức QUY TẮC (vàng), paths / sections_used về của quy tắc",
	(x.severity, json.loads(x.paths), x.sections_used) == ("vang", P_QT, "cong-no"), x)
c("lượt sau: cờ needs_check của lượt trước được xoá", R("cn.p3").needs_check == 0)

print("A8. sync_ai_free: nhận định tự do chỉ sống khi lượt gọi gần nhất nêu lại")
xoa()
F1K, F2K, G1K = "ai:cong-no.receivables.kpis.total", "ai:phai-tra.payables.cash.total", "ai:ton-kho.overview.value"
F1 = {"key": F1K, "section": "cong-no", "route": "#/cong-no", "severity": "vang", "priority": 3,
	"title": "Phải thu tăng", "body": "Thân F1", "advice": ["Kế toán: rà soát.", "Kinh doanh: nhắc khách."],
	"paths": ["cong-no.receivables.kpis.total"], "sections_used": ["cong-no"]}
F2 = {"key": F2K, "section": "phai-tra", "route": "#/phai-tra", "severity": "do", "priority": 5, "title": "Quỹ mỏng",
	"body": "Thân F2", "advice": [], "paths": ["phai-tra.payables.cash.total", "cong-no.receivables.kpis.total"],
	"sections_used": ["phai-tra", "cong-no"]}
G1 = {**F1, "key": G1K, "section": "ton-kho", "route": "#/ton-kho", "paths": ["ton-kho.overview.value"],
	"sections_used": ["ton-kho"]}
store.sync_signals([sig("cn.s")], set(), D(2026, 10, 27, 5, 30))            # tín hiệu quy tắc cùng mảng
store.sync_ai_free(("ton-kho", "han-dung"), [G1], D(2026, 10, 27, 5, 34))   # nhận định tự do của nhóm khác
F_T1 = D(2026, 10, 27, 5, 35)
kq = store.sync_ai_free(NHOM, [F1, F2], F_T1)
c("lượt đầu: trả đúng 3 khoá {new 2, kept 0, closed 0}", kq == {"new": 2, "kept": 0, "closed": 0}, kq)
x = R(F1K)
c("nhận định tự do: rule ai, source ai, audience lanh-dao, status mo, rule_title rỗng",
	(x.rule, x.source, x.audience, x.status, x.rule_title, x.needs_check) == ("ai", "ai", "lanh-dao", "mo", "", 0), x)
c("… lời + mức + ưu tiên + advice mỗi dòng một mục + mốc thời gian",
	(x.title, x.body, x.severity, x.priority, x.advice, x.first_seen, x.last_seen, x.text_at, x.seen_count, x.route,
	x.section) == ("Phải thu tăng", "Thân F1", "vang", 3, "Kế toán: rà soát.\nKinh doanh: nhắc khách.", F_T1, F_T1,
	F_T1, 1, "#/cong-no", "cong-no"), x)
x = R(F2K)
c("… paths JSON, sections_used mỗi dòng một mã, documents []", (json.loads(x.paths), x.sections_used,
	json.loads(x.documents)) == (["phai-tra.payables.cash.total", "cong-no.receivables.kpis.total"],
	"phai-tra\ncong-no", []), x)
F_T2 = D(2026, 10, 28, 5, 35)
kq = store.sync_ai_free(NHOM, [{**F1, "title": "Phải thu tăng tiếp", "severity": "do", "priority": 9}], F_T2)
x = R(F1K)
c("lượt sau nêu lại F1, không nêu F2: kept 1, closed 1", kq == {"new": 0, "kept": 1, "closed": 1}, kq)
c("F1 cập nhật lời / mức / ưu tiên, seen_count 2, first_seen giữ", (x.title, x.severity, x.priority, x.seen_count,
	x.first_seen, x.last_seen) == ("Phải thu tăng tiếp", "do", 9, 2, F_T1, F_T2), x)
c("F2 không được nêu lại → dong, closed_on = now", (R(F2K).status, R(F2K).closed_on) == ("dong", F_T2), R(F2K))
c("không đụng nhận định tự do của nhóm khác, không đụng tín hiệu quy tắc cùng mảng",
	(R(G1K).status, R("cn.s").status, R("cn.s").last_seen) == ("mo", "mo", D(2026, 10, 27, 5, 30)))
kq = store.sync_ai_free(NHOM, [{**F1, "title": "Phải thu tăng tiếp"}], D(2026, 10, 28, 9, 0))
c("gọi lại trong ngày: seen_count vẫn 2", kq == {"new": 0, "kept": 1, "closed": 0} and R(F1K).seen_count == 2, kq)
F_T3 = D(2026, 10, 29, 5, 35)
kq = store.sync_ai_free(NHOM, [], F_T3)
c("lượt gọi không thành công (items rỗng): đóng mọi nhận định tự do đang mở của nhóm",
	kq == {"new": 0, "kept": 0, "closed": 1} and (R(F1K).status, R(F1K).closed_on) == ("dong", F_T3)
	and R(G1K).status == "mo" and R("cn.s").status == "mo", kq)
F_T4 = D(2026, 10, 30, 5, 35)
kq = store.sync_ai_free(NHOM, [F2], F_T4)
x = R(F2K)
c("đã đóng rồi được nêu lại → một đợt mới (đếm vào new): mo, first_seen = now, seen_count 1",
	kq == {"new": 1, "kept": 0, "closed": 0} and (x.status, x.first_seen, x.seen_count, x.closed_on)
	== ("mo", F_T4, 1, None) and so(where="rule = 'ai'") == 3, kq)
dat(F2K, status="bo-qua", mute_until=datetime.date(2026, 11, 10))
kq = store.sync_ai_free(NHOM, [], D(2026, 10, 31, 5, 35))
c("bo-qua còn hạn: không được nêu vẫn GIỮ (không đóng)", kq == {"new": 0, "kept": 0, "closed": 0}
	and R(F2K).status == "bo-qua", kq)
kq = store.sync_ai_free(NHOM, [{**F2, "title": "Quỹ mỏng hơn"}], D(2026, 11, 1, 5, 35))
c("bo-qua còn hạn được nêu lại: vẫn bo-qua, lời cập nhật (đếm vào kept)", kq == {"new": 0, "kept": 1, "closed": 0}
	and (R(F2K).status, R(F2K).title) == ("bo-qua", "Quỹ mỏng hơn"), kq)
kq = store.sync_ai_free(NHOM, [], D(2026, 11, 11, 5, 35))
c("bo-qua hết hạn (11/11 > 10/11) + không được nêu → dong", kq == {"new": 0, "kept": 0, "closed": 1}
	and R(F2K).status == "dong", kq)
kq = store.sync_signals([], {"ai", "khong.co"}, D(2026, 11, 12, 5, 30))
c("sync_signals không bao giờ đóng nhận định tự do, kể cả khi 'ai' lọt vào ran", dem(kq) == DEM0
	and R(G1K).status == "mo", kq)
c("nhóm rỗng: không làm gì", store.sync_ai_free((), [], D(2026, 11, 12, 5, 35)) == {"new": 0, "kept": 0, "closed": 0}
	and R(G1K).status == "mo")
kq = store.sync_ai_free(["ton-kho"], [], D(2026, 11, 12, 5, 36))
c("đóng theo đúng mảng của nhóm được gọi", kq == {"new": 0, "kept": 0, "closed": 1} and R(G1K).status == "dong", kq)

print("A8b. blocked_paths (D10): path chủ đề đang bo-qua còn hạn / tín hiệu quy tắc đang mở → tự do không nêu lại")
xoa()
N0, NAY = D(2026, 10, 27, 5, 30), D(2026, 10, 27, 10, 30)
store.sync_signals([sig("bp.mo", paths=["cong-no.a.b[0].c", "cong-no.k"]), sig("bp.xl", paths=["cong-no.xl"]),
	sig("bp.bq", paths=["cong-no.bq[2].v", "cong-no.k"]), sig("bp.bq_het", paths=["cong-no.het"]),
	sig("bp.bq_han", paths=["cong-no.han"]), sig("bp.dong", paths=["cong-no.dong"]),
	sig("bp.khac", section="phai-tra", paths=["phai-tra.p[0]"])], set(), N0)
dat("bp.xl", status="dang-xu-ly")
dat("bp.bq", status="bo-qua", mute_until=None)                  # bỏ qua hẳn
dat("bp.bq_het", status="bo-qua", mute_until="2026-10-26")      # hết hạn hôm qua → không chặn
dat("bp.bq_han", status="bo-qua", mute_until="2026-10-27")      # tới hết hôm nay → còn chặn
dat("bp.dong", status="dong")


def tu_do(key, path):
	return {"key": key, "section": "cong-no", "route": "#/cong-no", "severity": "vang", "priority": 1, "title": "T",
		"body": "B", "advice": [], "paths": [path], "sections_used": ["cong-no"]}


store.sync_ai_free(["cong-no"], [tu_do("ai:cong-no.f", "cong-no.f[1]"), tu_do("ai:cong-no.g", "cong-no.g")], N0)
dat("ai:cong-no.f", status="bo-qua", mute_until=None)           # quản trị bỏ qua một nhận định TỰ DO
bp = store.blocked_paths(["cong-no"], NAY)
# mo / dang-xu-ly (rule ≠ ai) → "mo"; bo-qua còn hạn (mọi rule, kể cả ai) → "bo-qua"; cong-no.k có cả hai → bo-qua;
# bỏ chỉ số mảng; không: bo-qua hết hạn, dong, mảng khác, nhận định tự do đang mở (cong-no.g)
c("blocked_paths: đúng tập path + loại, đã bỏ chỉ số", bp == {"cong-no.a.b.c": "mo", "cong-no.k": "bo-qua",
	"cong-no.xl": "mo", "cong-no.bq.v": "bo-qua", "cong-no.han": "bo-qua", "cong-no.f": "bo-qua"}, bp)
c("blocked_paths: hằng số loại = store.BO_QUA / store.DANG_MO", (store.BO_QUA, store.DANG_MO) == ("bo-qua", "mo"))
c("blocked_paths: mảng khác chỉ thấy tín hiệu của mảng đó", store.blocked_paths(("phai-tra",), NAY)
	== {"phai-tra.p": "mo"}, store.blocked_paths(("phai-tra",), NAY))
c("blocked_paths: không mảng nào → {} (không truy vấn IN rỗng)", store.blocked_paths([], NAY) == {}
	and store.blocked_paths(["", None], NAY) == {})
bp2 = store.blocked_paths(["cong-no", "phai-tra"], D(2026, 10, 28, 0, 1))
c("hôm sau (28/10): bo-qua tới 27/10 hết hạn → cong-no.han không còn chặn; hai mảng cùng lúc",
	"cong-no.han" not in bp2 and bp2.get("phai-tra.p") == "mo" and bp2.get("cong-no.bq.v") == "bo-qua", bp2)
dat("bp.bq", status="mo")
c("đổi bo-qua → mo: cong-no.bq.v thành 'mo', cong-no.k vẫn 'mo' (không còn ai bỏ qua)",
	(store.blocked_paths(["cong-no"], NAY).get("cong-no.bq.v"), store.blocked_paths(["cong-no"], NAY).get(
	"cong-no.k")) == ("mo", "mo"))
xoa()

print("A9. rerank: đỏ trước, priority cao trước, first_seen cũ trước, rồi signal_key")
xoa()
store.rerank()
c("bảng trống: không lỗi", so() == 0)
for key, muc, ngay in (("r.1", "do", 1), ("r.2", "do", 10), ("r.3", "vang", 2), ("r.6", "do", 8), ("r.b", "do", 4),
		("r.d", "do", 5)):
	store.sync_signals([sig(key, muc)], set(), D(2026, 10, ngay, 5, 30))
store.sync_signals([sig("r.5"), sig("r.4")], set(), D(2026, 10, 3, 5, 30))    # cùng mức, cùng ưu tiên, cùng lúc
for key, uu_tien in (("r.2", 5), ("r.3", 9), ("r.6", 5), ("r.b", 9), ("r.d", 9)):
	dat(key, priority=uu_tien)
dat("r.6", status="dang-xu-ly")
dat("r.b", status="bo-qua", rank=3)                                            # rank cũ còn sót
store.sync_signals([], {"r.d"}, D(2026, 10, 11, 5, 30))
dat("r.d", rank=7)
store.rerank()
# đỏ: r.6 (ưu tiên 5, 08/10) → r.2 (5, 10/10) → r.1 (0). vàng: r.3 (9) → r.4, r.5 (0, cùng 03/10 → theo khoá).
c("thứ tự toàn cục 1..6; dang-xu-ly cũng được xếp", {k: R(k)["rank"] for k in ("r.6", "r.2", "r.1", "r.3", "r.4", "r.5")}
	== {"r.6": 1, "r.2": 2, "r.1": 3, "r.3": 4, "r.4": 5, "r.5": 6},
	{k: R(k)["rank"] for k in ("r.6", "r.2", "r.1", "r.3", "r.4", "r.5")})
c("bo-qua / dong không được xếp: rank về 0", (R("r.b")["rank"], R("r.d")["rank"]) == (0, 0))
store.sync_signals([], {"r.1"}, D(2026, 10, 12, 5, 30))
store.rerank()
c("một dòng đóng → các dòng sau dồn lên, dòng đóng về 0", {k: R(k)["rank"] for k in ("r.6", "r.2", "r.1", "r.3", "r.4",
	"r.5")} == {"r.6": 1, "r.2": 2, "r.1": 0, "r.3": 3, "r.4": 4, "r.5": 5})

print("A10. BC AI Run: start_run / finish_run")
xoa()
S1, S2 = D(2026, 10, 27, 5, 30), D(2026, 10, 27, 5, 33, 20)
tong = store.start_run("ngay", "tong", now=S1)
x = run_row(tong)
c("dòng tổng: run_id = chính nó, started = now, chưa finished", (x.run_type, x.step, x.run_id, x.started, x.finished,
	x.provider, x.model) == ("ngay", "tong", tong, S1, None, None, None), x)
c("dòng chưa chốt tự nói là lỗi (job chết giữa chừng không bị đọc thành ok), số đếm 0",
	(x.status, x.error, x.tokens_in, x.tokens_out, x.cost_usd, x.cost_known, x.signals, x.insights_ai, x.rejected, x.kpis)
	== ("loi", "chưa hoàn tất", 0, 0, 0, 0, 0, 0, 0, None), x)
con = store.start_run("ngay", "tai-chinh", provider="claude", model="claude-sonnet-5-5", now=S1, run_id=tong)
x = run_row(con)
c("dòng con: run_id = name dòng tổng, có provider + model", con != tong and (x.step, x.run_id, x.provider, x.model)
	== ("tai-chinh", tong, "claude", "claude-sonnet-5-5"), x)
store.finish_run(con, status="ok", now=S2, tokens_in=1200, tokens_out=300, cost_usd=0.0081, insights_ai=4,
	rejected=1, model="claude-sonnet-5-5-20261001")
x = run_row(con)
c("chốt dòng con: status, finished, token, chi phí (cost_known 1), số lời, model thật, xoá lời 'chưa kết thúc'",
	(x.status, x.finished, x.tokens_in, x.tokens_out, float(x.cost_usd), x.cost_known, x.insights_ai, x.rejected,
	x.model, x.error, x.run_id) == ("ok", S2, 1200, 300, 0.0081, 1, 4, 1, "claude-sonnet-5-5-20261001", None, tong), x)
con2 = store.start_run("ngay", "kho-sx", provider="claude", model="claude-sonnet-5-5", now=S1, run_id=tong)
store.finish_run(con2, status="loi", now=S2, tokens_in=500, error="E" * 500)
x = run_row(con2)
c("cost_usd None = chưa khai giá: cost_usd 0 + cost_known 0; error cắt 300; model giữ khi không truyền",
	(x.status, float(x.cost_usd), x.cost_known, x.error, x.tokens_in, x.model)
	== ("loi", 0.0, 0, "E" * 300, 500, "claude-sonnet-5-5"), (x.cost_usd, x.cost_known, len(x.error or "")))
con3 = store.start_run("ngay", "nhan-su", provider="claude", model="m", now=S1, run_id=tong)
store.finish_run(con3, status="ok", now=S2, cost_usd=0)
c("cost_usd 0 (đã khai giá, lượt gọi 0 đồng) khác None: cost_known 1", run_row(con3).cost_known == 1)
# lượt gọi mô hình hỏng vẫn ghi token đã tốn: hết credit giữa chừng, model thật trả về, lời lỗi ghi rõ
con4 = store.start_run("ngay", "attp", provider="claude", model="claude-sonnet-5-5", now=S1, run_id=tong)
store.finish_run(con4, status="het-credit", now=S2, tokens_in=900, tokens_out=40, cost_usd=0.0033,
	model="claude-sonnet-5-5-x", error="credit")
x = run_row(con4)
c("lượt gọi hỏng (het-credit) vẫn ghi token / chi phí / model thật; lời 'chưa hoàn tất' bị thay",
	(x.status, x.finished, x.tokens_in, x.tokens_out, float(x.cost_usd), x.cost_known, x.model, x.error, x.run_id)
	== ("het-credit", S2, 900, 40, 0.0033, 1, "claude-sonnet-5-5-x", "credit", tong), x)
ai = store.start_run("ngay", "ai", provider="claude", now=S1, run_id=tong)
store.finish_run(ai, status="tat", now=S2)
x = run_row(ai)
c("dòng step 'ai' khi cả bước AI bị bỏ: status tat, có provider, không token", (x.step, x.status, x.provider, x.model,
	x.tokens_in, x.tokens_out, x.run_id, x.error) == ("ai", "tat", "claude", None, 0, 0, tong, None), x)
KPI = {"cong-no.receivables.kpis.receivable": 220000000.0, "ton-kho.overview.value.total": 1500000000, "nhãn": "Tồn"}
store.finish_run(tong, status="ok", now=S2, signals=7, insights_ai=4, rejected=1, kpis=KPI)
x = run_row(tong)
c("chốt dòng tổng: kpis là chuỗi JSON đọc lại đúng (giữ chữ có dấu), signals, run_id vẫn là chính nó",
	isinstance(x.kpis, str) and json.loads(x.kpis) == KPI and "nhãn" in x.kpis and (x.status, x.signals, x.run_id,
	x.finished, x.error) == ("ok", 7, tong, S2, None), x)
c("kpis không truyền → để trống (dòng con)", run_row(con).kpis is None)
le = store.start_run("tay", "thu-ket-noi", provider="claude", model="m")
store.finish_run(le, status="khong-khoa")
x = run_row(le)
c("now mặc định = frappe.utils.now_datetime() (27/10/2026 10:30); dòng lẻ không thuộc lượt nào: run_id trống",
	(x.started, x.finished, x.run_id, x.run_type, x.status) == (D(2026, 10, 27, 10, 30), D(2026, 10, 27, 10, 30), None,
	"tay", "khong-khoa"), x)
tong2 = store.start_run("tay", "tong", now=S1, run_id="KHAC")
c("dòng tổng luôn mang run_id của chính nó dù nơi gọi truyền gì", run_row(tong2).run_id == tong2)
n_run = so(RUN)
c("run_type lạ → ValueError, không ghi dòng", nem(lambda: store.start_run("nam", "tong"), ValueError) and so(RUN) == n_run)
c("status lạ → ValueError, dòng không đổi", nem(lambda: store.finish_run(tong, status="xong"), ValueError)
	and run_row(tong).status == "ok")
dai = store.start_run("ngay", "s" * 200, provider="p" * 200, model="m" * 200, now=S1, run_id=tong)
c("field Data cắt 140 (site thật báo lỗi nếu dài hơn)", [len(run_row(dai)[k]) for k in ("step", "provider", "model")]
	== [140, 140, 140])
c("Run không có cột nào chứa đề bài / gói số", not {"prompt", "pack", "system", "user", "request", "response"}
	& set(frappe.db.get_table_columns(RUN)), frappe.db.get_table_columns(RUN))

print("A11. cleanup: giữ đúng 180 ngày lịch")
xoa()
NOW = D(2026, 10, 27, 5, 30)
# 27/10 lùi 180 ngày: 27 (→ 30/9) + 30 (→ 31/8) + 31 (→ 31/7) + 31 (→ 30/6) + 30 (→ 31/5) + 31 (→ 30/4) = 180
# → mốc 30/04/2026 00:00: đóng TRƯỚC mốc (từ 29/04 về trước = quá 180 ngày) thì xoá; đúng 30/04 (180 ngày) còn giữ.
for name, status, closed_on, modified in (
		("I-180-dau", "dong", "2026-04-30 00:00:00", None),        # đúng 180 ngày, đầu ngày → giữ
		("I-180-cuoi", "dong", "2026-04-30 23:59:59", None),       # đúng 180 ngày, cuối ngày → giữ
		("I-181", "dong", "2026-04-29 23:59:59", None),            # 181 ngày → xoá
		("I-cu", "dong", "2025-12-01 08:00:00", None),             # rất cũ → xoá
		("I-moi", "dong", "2026-10-26 05:30:00", None),            # mới đóng → giữ
		("I-mo-cu", "mo", None, "2025-01-01 00:00:00"),            # đang mở từ lâu → giữ
		("I-boqua-cu", "bo-qua", None, "2025-01-01 00:00:00"),     # bỏ qua từ lâu → giữ
		("I-xuly-cu", "dang-xu-ly", "2025-01-01 00:00:00", None),  # không phải dong → giữ
		("I-dong-tay-cu", "dong", None, "2025-06-01 00:00:00"),    # đóng tay, thiếu closed_on → theo modified → xoá
		("I-dong-tay-moi", "dong", None, "2026-10-01 00:00:00")):  # đóng tay gần đây → giữ
	insert(INSIGHT, name=name, signal_key=name, rule="t", status=status, closed_on=closed_on, modified=modified,
		first_seen="2025-01-01 00:00:00")
for name, started in (("R-180", "2026-04-30 00:00:00"), ("R-181", "2026-04-29 23:59:59"), ("R-moi", "2026-10-26 05:30:00"),
		("R-cu", "2025-10-27 05:30:00")):
	insert(RUN, name=name, run_type="ngay", step="tong", run_id=name, started=started, status="ok")
kq = store.cleanup(NOW)
c("trả số dòng đã xoá: 3 Insight, 2 Run", kq == {"insights": 3, "runs": 2}, kq)
con_lai = sorted(frappe.db.sql_list(f"SELECT name FROM `tab{INSIGHT}`"))
c("Insight: xoá đúng 3 dòng dong quá 180 ngày; đúng 180 ngày + mọi dòng chưa đóng còn nguyên",
	con_lai == sorted(["I-180-dau", "I-180-cuoi", "I-moi", "I-mo-cu", "I-boqua-cu", "I-xuly-cu", "I-dong-tay-moi"]), con_lai)
c("Run: còn dòng đúng 180 ngày và dòng mới", sorted(frappe.db.sql_list(f"SELECT name FROM `tab{RUN}`"))
	== ["R-180", "R-moi"])
c("chạy lại: không còn gì để xoá", store.cleanup(NOW) == {"insights": 0, "runs": 0})
c("sang 28/10 (mốc 01/05): hai dòng đóng ngày 30/04 thành 181 ngày → xoá", store.cleanup(D(2026, 10, 28, 0, 0, 1))
	== {"insights": 2, "runs": 1}, so())
c("hằng số giữ 180 ngày như đặc tả", (store.KEEP_CLOSED_DAYS, store.KEEP_RUN_DAYS) == (180, 180))


# ═══════════════════════════════════════════════════════════════════════════
print("B. bc.ai.collect")
# Bảng §3 của đặc tả CHÉP TAY (độc lập với collect.CALLS): (mảng, tên, module, method, tham số ngoài refresh).
# Hôm nay giả 27/10/2026 → năm 2026, tháng 10.
BANG = [
	("tong-quan", "summary", "kd", "get_summary", {}),
	("tong-quan", "channels", "kd", "get_channels", {}),
	("tong-quan", "item_groups", "kd", "get_item_groups", {}),
	("tong-quan", "top_customers", "kd", "get_top_customers", {}),
	("ngay", "daily", "kd", "get_daily", {"year": 2026, "month": 10}),
	("thang", "monthly", "kd", "get_monthly", {}),
	("tet", "npp_growth", "tet", "get_npp_growth", {}),
	("tet", "items", "tet", "get_items", {}),
	("tinh-thanh", "provinces", "kd", "get_provinces", {}),
	("san-pham", "top_products", "kd", "get_top_products", {"group": "all"}),
	("san-xuat", "overview", "sx_hop", "get_overview", {}),
	("san-xuat", "compare", "sx_hop", "get_compare", {}),
	("sx-tet", "items", "sx", "get_items", {}),
	("sx-tet", "daily", "sx", "get_daily_summary", {"year": 2026, "month": 10}),
	("ton-kho", "overview", "kho_ton", "get_overview", {}),
	("ton-kho", "trend", "kho_ton", "get_trend", {}),
	("han-dung", "overview", "kho_han", "get_overview", {}),
	("kiem-ke", "overview", "kho_kk", "get_overview", {}),
	("nhap-tp", "overview", "kho_nhap", "get_overview", {}),
	("van-chuyen", "overview", "vc", "get_overview", {}),
	# D13: tháng TRƯỚC hôm nay (27/10 → 2026-09) — chỉ quy tắc cước đọc, không gửi mô hình (registry.NO_SEND)
	("van-chuyen", "overview_truoc", "vc", "get_overview", {"thang": "2026-09"}),
	("cong-no", "receivables", "cn", "get_receivables", {}),
	("phai-tra", "payables", "cn", "get_payables", {}),
	("nhan-su", "overview", "ns", "get_overview", {}),
	("attp", "overview", "attp", "get_overview", {}),
	("attp", "report", "attp", "get_report", {}),
]
# Tham số KHÔNG truyền phải có đúng mặc định này trong chữ ký thật (đọc bc/api/*.py): kỳ mặc định = tháng / mùa này.
MAC_DINH = {("kd", "get_top_customers"): {"limit": 8}, ("sx", "get_items"): {"from_date": None, "to_date": None},
	("sx_hop", "get_overview"): {"thang": None}, ("sx_hop", "get_compare"): {"thang": None},
	("kho_kk", "get_overview"): {"thang": None}, ("kho_nhap", "get_overview"): {"thang": None},
	("vc", "get_overview"): {"thang": None}, ("attp", "get_report"): {"thang": None}}
COLLECT_PY = os.path.join(BC_ROOT, "bc", "ai", "collect.py")
API_DIR = os.path.join(BC_ROOT, "bc", "api")


def api(mod):
	return importlib.import_module(f"bc.api.{mod}")


def whitelisted():
	"""{(module, hàm): mảng trong _guard("<mảng>") ở dòng đầu | None} cho mọi hàm @frappe.whitelist của bc/api."""
	out = {}
	for f in sorted(os.listdir(API_DIR)):
		if not f.endswith(".py"):
			continue
		for node in ast.parse(open(os.path.join(API_DIR, f), encoding="utf-8").read()).body:
			if not isinstance(node, ast.FunctionDef) or not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
				continue
			body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
			st, mang = (body[0] if body else None), None
			if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and getattr(st.value.func, "id", "") == "_guard":
				a = st.value.args
				mang = a[0].value if a and isinstance(a[0], ast.Constant) else ""
			out[(f[:-3], node.name)] = mang
	return out


print("B1. AST: collect.py chỉ import frappe, bc.api.*, thư viện chuẩn; không SQL, không frappe.db / get_all")
src = open(COLLECT_PY, encoding="utf-8").read()
tree = ast.parse(src)
imports = []
for node in ast.walk(tree):
	if isinstance(node, ast.Import):
		imports += [a.name for a in node.names]
	elif isinstance(node, ast.ImportFrom):
		imports.append("." * node.level + (node.module or ""))


def import_ok(m):
	if m.startswith("."):
		return False
	goc = m.split(".")[0]
	return goc == "frappe" or m == "bc.api" or m.startswith("bc.api.") or goc in sys.stdlib_module_names


c("import tĩnh chỉ gồm frappe / bc.api.* / thư viện chuẩn", imports and all(import_ok(m) for m in imports), imports)
dong_import = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
	and (getattr(n.func, "attr", "") or getattr(n.func, "id", "")) in ("import_module", "__import__", "get_attr",
	"get_module", "call", "get_doc", "exec", "eval")]


def tien_to_bc_api(n):
	"""Tham số đầu của import động phải bắt đầu bằng chuỗi cố định 'bc.api.'."""
	a = n.args[0] if n.args else None
	if isinstance(a, ast.Constant):
		return isinstance(a.value, str) and a.value.startswith("bc.api.")
	return (isinstance(a, ast.JoinedStr) and a.values and isinstance(a.values[0], ast.Constant)
		and str(a.values[0].value).startswith("bc.api."))


c("import động (importlib) chỉ nạp module 'bc.api.<…>', không exec / eval / frappe.call / get_doc",
	[getattr(n.func, "attr", "") or getattr(n.func, "id", "") for n in dong_import] == ["import_module"]
	and all(tien_to_bc_api(n) for n in dong_import), [ast.unparse(n) for n in dong_import])
CAM = {"db", "qb", "get_all", "get_list", "get_doc", "get_value", "get_cached_doc", "get_cached_value", "get_single",
	"get_meta", "new_doc", "delete_doc", "cache", "set_user", "enqueue", "conf", "get_traceback"}
dung_frappe = sorted({n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
	and isinstance(n.value, ast.Name) and n.value.id == "frappe"})
c("không frappe.db / get_all / get_doc / cache / set_user / conf / get_traceback (traceback có thể chứa số liệu)",
	not (set(dung_frappe) & CAM), dung_frappe)
c("thuộc tính frappe được dùng: đúng 3 thứ (clear_last_message, log_error, utils)",
	dung_frappe == ["clear_last_message", "log_error", "utils"], dung_frappe)
SQL = re.compile(r"(?is)\b(select\b.+\bfrom\b|insert\s+into|delete\s+from|update\s+`?tab|alter\s+table|drop\s+table)"
	r"|`tab|\btab[A-Z]")
chuoi = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
c("không chuỗi nào là SQL / tên bảng tab…", not [s for s in chuoi if SQL.search(s)], [s for s in chuoi if SQL.search(s)])
c("không import requests / đọc khoá API", "requests" not in src and "bc_ai_" not in src and "_key" not in src)

print("B2. CALLS đúng bảng §3: tên method, tên tham số, mặc định (đối chiếu chữ ký thật), mảng của _guard")
goi = [(s, n, *d.split("."), f(datetime.date(2026, 10, 27))) for s, n, d, f in collect.CALLS]
c("CALLS = 26 lời gọi (25 của bảng đặc tả + vc tháng trước), đúng thứ tự và tham số", goi == BANG,
	[x for x in goi if x not in BANG])
c("26 cặp (mảng, tên) không trùng", len({(s, n) for s, n, *_ in BANG}) == 26 == len(collect.CALLS))
NS = registry.NO_SEND - {(registry.TRO_LY, "kpi")}   # P2: khối lịch sử KPI của detector (không do collect dựng)
c("khối không gửi mô hình (registry.NO_SEND) = đúng van-chuyen.overview_truoc, và nó có trong CALLS",
	NS == {("van-chuyen", "overview_truoc")} and NS <= {(s, n) for s, n, *_ in BANG})
f_truoc = next((f for s, n, d, f in collect.CALLS if (s, n) == ("van-chuyen", "overview_truoc")), None)
c("tháng trước: 27/10/2026 → 2026-09; 01/11 → 2026-10; 15/01/2026 → 2025-12 (qua năm); 31/03 → 2026-02",
	f_truoc is not None and [f_truoc(datetime.date(*x))["thang"] for x in ((2026, 10, 27), (2026, 11, 1), (2026, 1, 15), (2026, 3, 31))]
	== ["2026-09", "2026-10", "2025-12", "2026-02"])
c("mảng trong pack = mọi mảng của các nhóm gọi mô hình (trừ he-thong); không thoi-gian-thuc, không tro-ly",
	{s for s, *_ in goi} == {s for g, d in registry.GROUPS.items() if g not in (registry.HE_THONG, registry.KIEM_SOAT)
		for s in d["sections"]}   # kiem-soat (P2): mảng tro-ly do detector đổ vào, không do collect
	and not {s for s, *_ in goi} & {"thoi-gian-thuc", "tro-ly"})
wl = whitelisted()
c("mỗi method là @frappe.whitelist của bc.api và _guard ĐÚNG mảng mà pack đặt số vào (ẩn mảng ↔ ẩn số)",
	all(wl.get((m, f)) == s for s, n, m, f, kw in goi), [(s, m, f, wl.get((m, f))) for s, n, m, f, kw in goi
	if wl.get((m, f)) != s])
sai = []
for s, n, m, f, kw in BANG:
	sg = inspect.signature(getattr(api(m), f))
	try:
		sg.bind(refresh=1, **kw)
	except TypeError as e:
		sai.append((m, f, str(e)))
		continue
	con_lai = {k: p.default for k, p in sg.parameters.items() if k not in kw and k != "refresh"}
	if con_lai != {k: v for k, v in MAC_DINH.get((m, f), {}).items() if k not in kw} \
			or sg.parameters["refresh"].default != 0:
		sai.append((m, f, con_lai))
c("tham số truyền khớp chữ ký thật; tham số bỏ trống có đúng mặc định đã đọc trong code", not sai, sai)

# Thay MỌI method whitelisted của bc.api bằng máy ghi → biết chính xác collect gọi gì, với tham số gì.
frappe.session.user = ADMIN
da_goi, goc = [], {}
for (m, f) in wl:
	try:
		mod = api(m)
	except Exception:  # noqa: BLE001 — module của agent khác đang viết dở (bc.api.ai)
		continue
	goc[(m, f)] = getattr(mod, f)
	setattr(mod, f, (lambda m=m, f=f: lambda *a, **kw: da_goi.append((m, f, a, kw)) or {"tu": f"{m}.{f}"})())
try:
	pack = collect.build()
finally:
	for (m, f), fn in goc.items():
		setattr(api(m), f, fn)
c("gọi đúng 26 lời gọi của bảng, theo thứ tự, MỌI lời gọi refresh=1, tham số theo tên (không vị trí)",
	da_goi == [(m, f, (), {"refresh": 1, **kw}) for s, n, m, f, kw in BANG], [x for x in da_goi][:30])
c("không gọi live.get_snapshot (thoi-gian-thuc) hay method nào ngoài bảng", ("live", "get_snapshot") in goc
	and not [x for x in da_goi if (x[0], x[1]) not in {(m, f) for s, n, m, f, kw in BANG}])
mong = {}
for s, n, m, f, kw in BANG:
	mong.setdefault(s, {})[n] = {"tu": f"{m}.{f}"}
c("pack[mảng][tên] = payload của đúng method đó", pack == mong, pack)

print("B3. Trên DB có số (seed gộp), dưới Administrator: đủ 26 khối với payload thật")
import seed_ui2  # noqa: E402,F401  (reset + seed SX, công nợ, ATTP, vận chuyển, nhân sự, bán hàng)

frappe.session.user = ADMIN
frappe.LOGGED.clear()
dem_clear = {"collect": 0, "khac": 0}
frappe.local.message_log = []


def clear_gia():
	"""Như v16 frappe.utils.messages.clear_last_message + đếm theo module gọi."""
	noi = sys._getframe(1).f_globals.get("__name__")
	dem_clear["collect" if noi == "bc.ai.collect" else "khac"] += 1
	if frappe.local.message_log:
		frappe.local.message_log = frappe.local.message_log[:-1]


frappe.clear_last_message = clear_gia


def bo_meta(p):
	"""Payload bỏ dấu thời gian sinh (hai lượt gọi liên tiếp chỉ khác chỗ này)."""
	if isinstance(p, dict):
		return {k: bo_meta(v) for k, v in p.items() if k not in ("generated_at", "cached")}
	return [bo_meta(x) for x in p] if isinstance(p, list) else p


def loi_cua(pack):
	return sorted((s, n) for s, d in pack.items() for n, p in d.items() if isinstance(p, dict) and p.get("_error"))


pack = collect.build()
c("đủ mọi (mảng, tên) của bảng, không thừa", {(s, n) for s, d in pack.items() for n in d}
	== {(s, n) for s, n, *_ in BANG} and len(pack) == 17, sorted(pack))
c("không khối nào _error; collect không gọi clear_last_message; không ghi Error Log",
	loi_cua(pack) == [] and dem_clear["collect"] == 0 and not [x for x in frappe.LOGGED if "collect" in str(x)],
	(loi_cua(pack), dem_clear, frappe.LOGGED[:3]))
khac = [(s, n) for s, n, m, f, kw in BANG if bo_meta(pack[s][n]) != bo_meta(getattr(api(m), f)(refresh=1, **kw))]
c("mỗi khối = đúng payload method đó trả khi gọi thẳng (AI thấy đúng cái màn hình thấy)", not khac, khac)
# Số tính tay từ seed (test_cn.seed): phải thu NPP-A 80 + NPP-B 80 + DL-1 20 + MT 40 = 220 triệu; quá hạn 40 + 30 +
# 20 + 30 (MT) = 120 → 120 / 220 = 54,5%; phải trả PI1 30 + PI2 15 = 45; quỹ tiền mặt 100 − 20 = 80, ngân hàng 500.
M = 1_000_000
k = pack["cong-no"]["receivables"]["kpis"]
c("cong-no.receivables.kpis: phải thu 220 triệu, quá hạn 120 triệu = 54,5%", (k["receivable"], k["overdue"],
	k["overdue_pct"]) == (220 * M, 120 * M, 54.5), k)
c("cong-no.receivables.top_overdue[0]: NPP-A quá hạn 40 triệu, xa nhất 26 ngày (path có chỉ số dùng được)",
	(registry.resolve(pack, "cong-no.receivables.top_overdue[0].overdue"),
	registry.resolve(pack, "cong-no.receivables.top_overdue[0].max_days")) == (40 * M, 26))
p = pack["phai-tra"]["payables"]
c("phai-tra.payables: phải trả 45 triệu, quỹ 80 + 500 = 580 triệu", (p["ap"]["total"], p["cash"]["cash"],
	p["cash"]["bank"], p["cash"]["total"]) == (45 * M, 80 * M, 500 * M, 580 * M), (p["ap"]["total"], p["cash"]))
# seed_ui.sales(): ngày 27/10 có 5 hoá đơn (mỗi kênh một): 90 + 45 + 12 + 6 + 2 = 155 triệu; seed khác không có 27/10.
d = pack["ngay"]["daily"]
h27 = next(r for r in d["rows"] if r["date"] == "2026-10-27")
c("ngay.daily: đúng tháng 10/2026; ngày 27/10 bán 155 triệu / 5 đơn", (d["meta"]["year"], d["meta"]["month"],
	d["meta"]["start"], d["meta"]["end"], h27["sales"], h27["orders"]) == (2026, 10, "2026-10-01", "2026-10-31",
	155 * M, 5), (d["meta"], h27))
c("sx-tet.daily: tháng 10/2026", (pack["sx-tet"]["daily"]["meta"]["year"], pack["sx-tet"]["daily"]["meta"]["month"])
	== (2026, 10))
# seed_ui.sales(): 35 hoá đơn đánh số n = 1..35 (5 kênh × 7 ngày), 10 hộp / hoá đơn, n lẻ → TET1, n chẵn → TRAD1.
# Trong năm TC nay là 5 ngày đầu của mỗi kênh: n = 1–5, 8–12, 15–19, 22–26, 29–33 → lẻ 3 + 2 + 3 + 2 + 3 = 13 hoá đơn
# (130 hộp TET1), chẵn 12 hoá đơn (120 hộp TRAD1). Nhóm "all" → có CẢ hai nhóm hàng, cửa sổ năm tài chính.
t = pack["san-pham"]["top_products"]
c("san-pham.top_products nhóm all: TET1 130 hộp + TRAD1 120 hộp, cửa sổ năm tài chính",
	[(r["item_code"], r["qty"]) for r in t["rows"]] == [("TET1", 130.0), ("TRAD1", 120.0)]
	and (t["meta"]["window"], t["meta"]["group"]) == ("fy", "all"), t)
c("kỳ mặc định = tháng này: san-xuat / kiem-ke / nhap-tp / van-chuyen đều 2026-10",
	[pack[s]["overview"]["meta"]["thang"] for s in ("san-xuat", "kiem-ke", "nhap-tp", "van-chuyen")] == ["2026-10"] * 4)
c("khối có 'available' đều True trên seed này (payload thật, không phải khối tắt)",
	all(pd.get("available", True) is True for dd in pack.values() for pd in dd.values()))
c("pack gọn trong JSON được (gửi mô hình / ghi cache)", len(json.dumps(pack, ensure_ascii=False, default=str)) > 50000)

print("B4. refresh=1: tính lại + làm ấm cache cho buổi sáng")
single("BC Settings", cache_ttl=300)
pack = collect.build()                                  # làm ấm
insert("Sales Invoice", name="SI-MOI", docstatus=1, posting_date="2026-10-27", posting_time="10:00:00", customer="C-MOI",
	customer_name="C-MOI", customer_group="NPP", net_total=7 * M, grand_total=7 * M, is_return=0, is_opening="No",
	company="HGC")
frappe.session.user = VIEWER
cu = api("kd").get_daily()
c("(đối chứng) người xem đọc cache: chưa thấy hoá đơn mới, meta.cached = True",
	next(r for r in cu["rows"] if r["date"] == "2026-10-27")["sales"] == 155 * M and cu["meta"]["cached"] is True, cu["meta"])
frappe.session.user = ADMIN
pack = collect.build()                                  # cache đang ấm — collect vẫn phải TÍNH LẠI
h27 = next(r for r in pack["ngay"]["daily"]["rows"] if r["date"] == "2026-10-27")
c("collect bỏ qua cache: thấy hoá đơn mới — 155 + 7 = 162 triệu / 6 đơn", (h27["sales"], h27["orders"]) == (162 * M, 6), h27)
c("mọi khối trong pack đều vừa tính (meta.cached = False)", [(s, n) for s, dd in pack.items() for n, pd in dd.items()
	if (pd.get("meta") or {}).get("cached") is not False] == [])
frappe.session.user = VIEWER
nguoi_xem = {(m, f): getattr(api(m), f)(**kw) for s, n, m, f, kw in BANG}
c("sau collect, người xem mở màn (gọi mặc định, không refresh) trúng cache ở CẢ 26 lời gọi",
	[k2 for k2, v in nguoi_xem.items() if (v.get("meta") or {}).get("cached") is not True] == [])
c("… kể cả khi màn gọi không tham số: kd.get_daily(), sx.get_daily_summary(), kd.get_top_products()",
	all(x["meta"]["cached"] is True for x in (api("kd").get_daily(), api("sx").get_daily_summary(),
	api("kd").get_top_products())))
c("… và người xem thấy đúng số collect vừa tính (162 triệu)",
	next(r for r in api("kd").get_daily()["rows"] if r["date"] == "2026-10-27")["sales"] == 162 * M)
single("BC Settings", cache_ttl=0)
frappe.cache().store.clear()

print("B5. Tham số `today`: năm + tháng của kd.get_daily / sx.get_daily_summary")
frappe.session.user = ADMIN
pack = collect.build(today="2026-09-15")
# seed_ui.sales(): 15/09 cũng 5 hoá đơn 155 triệu; các khối khác vẫn theo kỳ mặc định của method (tháng này).
d = pack["ngay"]["daily"]
c("today = 15/09/2026 → ngay.daily + sx-tet.daily của tháng 9; 15/09 bán 155 triệu",
	(d["meta"]["month"], d["meta"]["year"], pack["sx-tet"]["daily"]["meta"]["month"],
	next(r for r in d["rows"] if r["date"] == "2026-09-15")["sales"]) == (9, 2026, 9, 155 * M), d["meta"])
c("… khối không nhận tháng vẫn theo hôm nay (kiem-ke 2026-10)", pack["kiem-ke"]["overview"]["meta"]["thang"] == "2026-10")
c("… vc tháng trước theo `today`: 15/09 → van-chuyen.overview_truoc tháng 2026-08, overview vẫn 2026-10",
	(pack["van-chuyen"]["overview_truoc"]["meta"]["thang"], pack["van-chuyen"]["overview"]["meta"]["thang"])
	== ("2026-08", "2026-10"), pack["van-chuyen"]["overview_truoc"].get("meta"))
pack = collect.build(today=datetime.date(2025, 12, 31))
c("today là date, năm khác: 12/2025", (pack["ngay"]["daily"]["meta"]["year"], pack["ngay"]["daily"]["meta"]["month"],
	pack["sx-tet"]["daily"]["meta"]["year"]) == (2025, 12, 2025))
c("… vc tháng trước = 2025-11", pack["van-chuyen"]["overview_truoc"]["meta"]["thang"] == "2025-11",
	pack["van-chuyen"]["overview_truoc"].get("meta"))
frappe.utils.FAKE_TODAY = datetime.date(2026, 11, 3)
pack = collect.build()
c("today bỏ trống = hôm nay của máy chủ (03/11/2026 → tháng 11), không khối nào lỗi",
	(pack["ngay"]["daily"]["meta"]["month"], pack["sx-tet"]["daily"]["meta"]["month"], loi_cua(pack)) == (11, 11, []),
	(pack["ngay"]["daily"]["meta"], loi_cua(pack)))
frappe.utils.FAKE_TODAY = datetime.date(2026, 10, 27)

print("B6. Một lời gọi lỗi → chỉ mục đó _error; lời lỗi không lọt ra ngoài, Error Log không có dữ liệu")
BI_MAT = "KHÁCH BÍ MẬT 987654321 nợ 123456789 đồng"
tot = collect.build()
goc_cn, goc_tb = api("cn").get_receivables, frappe.get_traceback


def hong(refresh=0):
	frappe.local.message_log.append({"message": BI_MAT})     # như frappe.throw của v16: lời lỗi vào message_log
	raise frappe.ValidationError(BI_MAT)


api("cn").get_receivables = hong
frappe.get_traceback = lambda *a, **k: "TRACEBACK " + BI_MAT   # nếu collect ghi traceback thì lộ ngay
frappe.LOGGED.clear()
frappe.local.message_log = []
dem_clear.update(collect=0, khac=0)
try:
	pack = collect.build()
finally:
	api("cn").get_receivables, frappe.get_traceback = goc_cn, goc_tb
c("không ném lỗi; mục hỏng = ĐÚNG {'_error': True}", pack["cong-no"]["receivables"] == {"_error": True},
	pack["cong-no"]["receivables"])
c("chỉ mục đó lỗi — 24 mục còn lại vẫn nguyên số (kể cả phai-tra cùng module cn)", loi_cua(pack)
	== [("cong-no", "receivables")] and all(bo_meta(pack[s][n]) == bo_meta(tot[s][n]) for s, n, *_ in BANG
	if (s, n) != ("cong-no", "receivables")), loi_cua(pack))
c("frappe.clear_last_message() được collect gọi đúng 1 lần cho 1 lỗi; lời lỗi không còn trong message_log",
	dem_clear["collect"] == 1 and frappe.local.message_log == [], (dem_clear, frappe.local.message_log))
log = [x for x in frappe.LOGGED if "bc.ai collect" in str(x)]
c("Error Log: đúng 1 dòng cho mục hỏng, nêu tên method", len(log) == 1 and "cn.get_receivables" in str(log[0]), log)
c("Error Log KHÔNG chứa lời của lỗi, không traceback, không số liệu", BI_MAT not in str(frappe.LOGGED)
	and "987654321" not in str(frappe.LOGGED) and "TRACEBACK" not in str(frappe.LOGGED), frappe.LOGGED)
a_log, k_log = log[0] if log else ((), {})
tin = k_log.get("message") or (a_log[1] if len(a_log) > 1 else "")
c("… chỉ có tên loại lỗi + vị trí dòng code, một dòng, truyền qua `message` (v16: thiếu message là tự chụp traceback"
	" kèm biến)", bool(re.fullmatch(r"ValidationError tại [\w.]+\.py:\d+ \w+( <- [\w.]+\.py:\d+ [\w<>]+)*", tin)), tin)
c("pack không chứa lời lỗi", BI_MAT not in json.dumps(pack, ensure_ascii=False, default=str))

# Method trả thứ không phải dict / module không import được → cũng chỉ mục đó lỗi.
goc_ns = api("ns").get_overview
api("ns").get_overview = lambda refresh=0: ["không", "phải", "dict"]
goc_calls = collect.CALLS
collect.CALLS = (*goc_calls, ("attp", "khong_co", "khong_co_module.get_x", lambda today: {}))
try:
	pack = collect.build()
finally:
	api("ns").get_overview, collect.CALLS = goc_ns, goc_calls
c("payload không phải dict / module không nạp được → _error riêng mục đó", loi_cua(pack) == [("attp", "khong_co"),
	("nhan-su", "overview")] and pack["nhan-su"]["overview"] == {"_error": True}, loi_cua(pack))

print("B7. Dưới người xem: mảng đang ẩn → _error ở các mục của mảng đó, không ném lỗi")
single("BC Settings", hidden_sections="cong-no\nattp")
frappe.session.user = VIEWER
frappe.LOGGED.clear()
dem_clear.update(collect=0, khac=0)
pack = collect.build()
c("người xem + ẩn cong-no, attp: đúng 3 mục _error (receivables, attp.overview, attp.report), 22 mục còn lại có số",
	loi_cua(pack) == [("attp", "overview"), ("attp", "report"), ("cong-no", "receivables")]
	and pack["attp"] == {"overview": {"_error": True}, "report": {"_error": True}}
	and bo_meta(pack["phai-tra"]["payables"]) == bo_meta(tot["phai-tra"]["payables"]), loi_cua(pack))
c("… 3 lần clear_last_message, 3 dòng Error Log chỉ ghi PermissionError", dem_clear["collect"] == 3
	and sorted(str(x[1].get("title")) for x in frappe.LOGGED if "bc.ai collect" in str(x))
	== ["bc.ai collect attp.get_overview", "bc.ai collect attp.get_report", "bc.ai collect cn.get_receivables"]
	and all(str(x[1].get("message")).startswith("PermissionError tại ") for x in frappe.LOGGED
	if "bc.ai collect" in str(x)), (dem_clear, frappe.LOGGED))
frappe.session.user = ADMIN
pack = collect.build()
c("Administrator qua _guard kể cả mảng đang ẩn: đủ 26 khối có số", loi_cua(pack) == []
	and pack["cong-no"]["receivables"]["kpis"]["receivable"] == 220 * M, loi_cua(pack))
frappe.session.user = "nguoi-la@example.com"            # không có vai BC Viewer / System Manager
pack = collect.build()
c("người không có quyền: cả 26 mục _error, vẫn không ném lỗi", len(loi_cua(pack)) == 26
	and all(pd == {"_error": True} for dd in pack.values() for pd in dd.values()), loi_cua(pack))
frappe.session.user = VIEWER
single("BC Settings", hidden_sections="")

c.done()
