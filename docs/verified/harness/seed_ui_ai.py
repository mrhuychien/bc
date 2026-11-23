"""Seed + server thử cho màn Trợ lý AI (ui_ai.mjs): #/tro-ly (người xem + quản trị) và #/ai (quản trị).

BC_TEST_DB=bc_test_ai_ui python3 -B seed_ui_ai.py fresh|stale     nạp dữ liệu (ghi đè DB đó)
BC_TEST_DB=bc_test_ai_ui [BC_UI_USER=Administrator] python3 -B seed_ui_ai.py serve <port>
	= server.py + bản giả: khoá API giả trong frappe.conf (KHÔNG phải khoá thật), bc.ai.llm.call giả (lượt 1 ok, lượt 2
	lỗi có chứa khoá — máy chủ phải xoá), hàng đợi giả (run_now chỉ ghi lại, KHÔNG chạy pipeline; "đang chạy" RUN_SECS
	giây rồi tự hết), chặn mọi kết nối mạng ra ngoài (socket chỉ cho unix + 127.0.0.1).

fresh: lượt ok mới (05:40 hôm nay giả 27/10/2026), AI bật, có giá model, có việc đỏ (chấm đỏ menu).
stale: lượt ok cuối 25/10 (> 26 giờ), AI tắt, trần 0, chưa khai giá, chỉ việc vàng (không chấm đỏ).
"""
import datetime
import json
import os
import socket
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAKE_KEY = "sk-ant-api03-GIA-chi-de-thu-ui-0a1b2c3d4e5f"   # khoá GIẢ — ui_ai.mjs kiểm chuỗi này không lộ ra trang
RUN_SECS = float(os.environ.get("BC_UI_AI_RUN_SECS", "7"))
D = datetime.datetime
XSS = "<img src=x onerror=window.__xss=1>"
INSIGHT, RUN = "BC AI Insight", "BC AI Run"


def _no_net():
	"""Chặn mọi kết nối TCP ra ngoài 127.0.0.1 (MariaDB dùng unix socket)."""
	orig = socket.socket.connect

	def connect(self, addr):
		if self.family == socket.AF_UNIX or (isinstance(addr, tuple) and addr[0] in ("127.0.0.1", "localhost", "::1")):
			return orig(self, addr)
		raise OSError(f"bộ thử chặn mạng: {addr}")
	socket.socket.connect = connect
	try:
		import requests

		def cam(*a, **k):
			raise OSError("bộ thử chặn requests")
		requests.Session.request = cam
		requests.request = requests.post = requests.get = cam
	except ImportError:
		pass


def seed(kind):
	from seed import bc_settings, child, insert, reset, single
	reset()
	fresh = kind == "fresh"
	bc_settings(ai_enabled=1 if fresh else 0, ai_claude_model="claude-sonnet-5-5", ai_claude_model_deep="claude-opus-5-5",
		ai_openai_model="", ai_cap_claude_usd=50 if fresh else 0, ai_cycle_day_claude=1, ai_max_signals=40,
		ai_mask_parties=1, hidden_sections="phai-tra")
	if fresh:
		child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
			[{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15}])

	def ins(name, **f):
		sec = f.get("section", "cong-no")
		base = {"signal_key": f"k.{name}", "rule": f"r.{name.lower()}", "section": sec, "route": f"#/{sec}",
			"sections_used": sec, "audience": "lanh-dao", "severity": "vang", "status": "mo", "source": "quy-tac",
			"title": f"Việc {name}", "rule_title": f"Việc {name}", "body": f"Nội dung {name}", "advice": "",
			"documents": "[]", "rank": 0, "first_seen": D(2026, 10, 20, 5, 30), "last_seen": D(2026, 10, 27, 5, 30),
			"needs_check": 0, "seen_count": 1, "priority": 0, "admin_note": "", "review_note": "", "review_verdict": ""}
		base.update(f)
		insert(INSIGHT, name, **base)

	if fresh:
		ins("A1", section="cong-no", severity="do", source="ai", rank=1, rule="cn.qua_han",
			title=f"Quá hạn tăng {XSS} **bold**", body=f"Dòng một {XSS}\nDòng hai **bold**",
			advice=f"Gọi khách lớn {XSS}\nKhoá giao hàng nợ quá 90 ngày",
			documents=json.dumps([{"doctype": "Sales Invoice", "name": "SI/2026 0001&x"},
				{"doctype": "Payment Entry", "name": "PE-0002"}]),
			admin_note="Đã nhắc <b>kế toán</b>", review_verdict="nghi-ngo", review_note="Phản biện: số có vẻ cao")
		ins("A2", section="ton-kho", severity="do", status="dang-xu-ly", rank=2, route="javascript:alert(1)",
			first_seen=D(2026, 10, 24, 5, 30))
		ins("A3", section="tong-quan", source="ai", rank=3, needs_check=1, title="Doanh số tháng giảm")
		# lượt ok 27/10 05:30 không làm mới A4 (quy tắc không chạy được) → thẻ "Số ngày 25/10 — chưa cập nhật được"
		ins("A4", section="van-chuyen", rank=4, route="", last_seen=D(2026, 10, 25, 5, 30))
		ins("A5", section="nhan-su", rank=5)
		ins("A6", section="attp", severity="do", rank=6)
		ins("A7", section="ngay", rank=0, first_seen=D(2026, 10, 27, 5, 30))
		ins("H1", section="phai-tra", severity="do", rank=7)                          # mảng ẩn với người xem
		ins("H2", section="tong-quan", sections_used="tong-quan\nphai-tra", rank=8)   # dùng số của mảng ẩn
		ins("S1", section="he-thong", audience="quan-tri", severity="do", rank=9, route="", title="Sao lưu quá 2 ngày")
		ins("M1", section="ton-kho", status="bo-qua", mute_until=datetime.date(2026, 11, 10), needs_check=1)
		ins("M2", section="kiem-ke", status="bo-qua", mute_until=None, title="Kiểm kê lâu chưa làm")
		ins("C1", section="nhap-tp", status="dong", closed_on=D(2026, 10, 20, 5, 30), title="Việc đã đóng gần đây")
		ins("C2", section="nhap-tp", status="dong", closed_on=D(2026, 9, 1, 5, 30), title="Việc đóng lâu rồi")
		runs = [
			("R1", dict(run_type="ngay", step="tong", started=D(2026, 10, 27, 5, 30), finished=D(2026, 10, 27, 5, 40),
				status="ok", signals=12, insights_ai=3, rejected=1)),
			("R2", dict(run_type="ngay", step="tai-chinh", run_id="R1", provider="claude", model="claude-sonnet-5-5",
				started=D(2026, 10, 27, 5, 31), finished=D(2026, 10, 27, 5, 32), status="ok", tokens_in=12000,
				tokens_out=1500, cost_usd=0.0585, cost_known=1, signals=4, insights_ai=2, rejected=1)),
			("R3", dict(run_type="ngay", step="kho-sx", run_id="R1", provider="claude", model="claude-sonnet-5-5",
				started=D(2026, 10, 27, 5, 33), finished=D(2026, 10, 27, 5, 33), status="het-credit",
				error="Tài khoản hết <credit> & dừng")),
			("R6", dict(run_type="ngay", step="ai", run_id="R5", provider="claude", started=D(2026, 10, 26, 5, 35),
				finished=D(2026, 10, 26, 5, 35), status="tat")),
			("R4", dict(run_type="tay", step="test", provider="claude", model="claude-x-moi", started=D(2026, 10, 26, 9, 0),
				finished=D(2026, 10, 26, 9, 0), status="ok", tokens_in=20, tokens_out=5, cost_known=0)),
			("R5", dict(run_type="ngay", step="tong", started=D(2026, 10, 26, 5, 30), finished=D(2026, 10, 26, 5, 41),
				status="ok", signals=10)),
		]
	else:
		ins("B1", section="cong-no", rank=1, title="Quá hạn nhích lên")
		ins("B2", section="ton-kho", rank=2, source="ai", last_seen=D(2026, 10, 24, 5, 30))   # trước lượt ok 25/10 → cũ
		ins("B3", section="he-thong", audience="quan-tri", rank=3, route="", title="Hàng đợi chậm")
		runs = [
			("R1", dict(run_type="ngay", step="tong", started=D(2026, 10, 25, 5, 30), finished=D(2026, 10, 25, 5, 40),
				status="ok", signals=3)),
			("R2", dict(run_type="ngay", step="tong", started=D(2026, 10, 26, 5, 30), finished=D(2026, 10, 26, 5, 31),
				status="loi", error="lỗi đọc số")),
			("R3", dict(run_type="ngay", step="ai", run_id="R1", provider="claude", started=D(2026, 10, 25, 5, 35),
				finished=D(2026, 10, 25, 5, 35), status="tat")),
		]
	for name, f in runs:
		# Như pipeline ghi: dòng không gọi model (tong, ai bỏ qua, lỗi trước khi gọi) không truyền chi phí → cost_known 0
		base = dict(provider=None, model=None, run_id=None, tokens_in=0, tokens_out=0, cost_usd=0,
			cost_known=0 if f.get("step") in ("tong", "ai") or not f.get("tokens_in") else 1,
			signals=0, insights_ai=0, rejected=0, error=None)
		base.update(f)
		insert(RUN, name, **base)
	print(f"seeded ai ui ({kind})")


def serve(port):
	_no_net()
	import server
	import frappe
	from frappe.utils import background_jobs
	import bc.ai.llm as llm
	from bc.ai import jobs

	frappe.conf["bc_ai_anthropic_key"] = FAKE_KEY
	frappe.ENQUEUE_RUN = False          # run_now chỉ ghi lại — không bao giờ chạy pipeline thật
	orig = frappe.enqueue

	def enqueue(method, *a, **k):
		r = orig(method, *a, **k)
		jid = k.get("job_id")
		if jid:
			background_jobs.FAKE_ENQUEUED_IDS.add(jid)
			threading.Timer(RUN_SECS, background_jobs.FAKE_ENQUEUED_IDS.discard, (jid,)).start()
		print("enqueue", method, k.get("run_type"), flush=True)
		return r
	frappe.enqueue = enqueue
	assert jobs.JOB_ID

	n = {"call": 0}

	def call(provider, model, system, user, schema_name, schema, **k):
		n["call"] += 1
		if n["call"] % 2 == 0:
			raise llm.LLMError("http", f"401 sai khoá x-api-key {FAKE_KEY} <b>từ chối</b>")
		return {"data": {"ok": True}, "model": model, "tokens_in": 12, "tokens_out": 3}
	llm.call = call

	frappe.session.user = os.environ.get("BC_UI_USER") or frappe.session.user
	srv = server.serve(port)
	print(f"http://127.0.0.1:{srv.server_address[1]}/bc", flush=True)
	srv.serve_forever()


if __name__ == "__main__":
	cmd = sys.argv[1] if len(sys.argv) > 1 else "fresh"
	if cmd == "serve":
		serve(int(sys.argv[2]))
	elif cmd in ("fresh", "stale"):
		seed(cmd)
	else:
		sys.exit("dùng: seed_ui_ai.py fresh|stale|serve <port>")
