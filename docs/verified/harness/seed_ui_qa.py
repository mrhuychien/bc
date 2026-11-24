"""Seed + server thử cho màn Hỏi đáp (ui_qa.mjs): #/hoi-dap (người xem + quản trị) và nút "Hỏi trợ lý" trên #/tro-ly.

BC_TEST_DB=bc_test_ai_qa_ui python3 -B seed_ui_qa.py seed            nạp dữ liệu (= seed_ui_ai fresh — #/tro-ly vẽ được)
BC_TEST_DB=bc_test_ai_qa_ui BC_UI_QA_MODE=<file.json> [BC_UI_USER=Administrator] python3 -B seed_ui_qa.py serve <port>
	= seed_ui_ai serve (chặn mạng, khoá giả, hàng đợi giả) + ba hàm của bc.ai.qa THAY BẰNG KỊCH BẢN: method thật
	bc.api.ai.get_qa / ask / get_answer vẫn chạy (kể cả _guard("tro-ly")), chỉ phần máy (qa.status / start / answer)
	là giả — không gọi mô hình, không ghi gì vào CSDL.

File chế độ (ui_qa.mjs ghi, server đọc mỗi lượt gọi): {"enabled": bool, "limit": int, "gen": int}. gen đổi → server xoá
số câu đã hỏi + câu đang chờ (bắt đầu lại sạch).

Kịch bản theo chữ trong câu hỏi (mỗi câu "xong" sau 3 lượt get_answer — tức ~6 giây với nhịp 2 giây):
	mặc định   xong: đoạn đã kiểm + đoạn CHƯA kiểm (u) + xuống dòng, nguồn Phải thu / Tồn kho (+ một nguồn route
	           "javascript:" không được thành link), bước SQL có câu lệnh (gửi cho CẢ người xem — giao diện phải tự giấu)
	[html]     xong, lời chứa thẻ HTML / chuỗi XSS (phải hiện thành chữ)
	[dai]      xong, lời + câu SQL rất dài không có dấu cách (390 px không cuộn ngang)
	[loi]      loi: "Trợ lý từ chối <b>câu này</b>"
	[tuchoi]   ask bị từ chối (417) "Trợ lý đã dùng hết ngân sách kỳ này — báo quản trị."
	[cham]     không bao giờ xong (màn phải báo hết giờ sau 150 giây)
Hết lượt (used ≥ limit) → ask 417 "Bạn đã hỏi đủ n câu hôm nay"; đang có câu chờ → 417 "đang có một câu hỏi".
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

XSS = "<img src=x onerror=window.__xss=1>"
LONG = "X" * 600
MODE = os.environ.get("BC_UI_QA_MODE", "/tmp/bc_ui_qa_mode.json")


def _mode():
	try:
		with open(MODE, encoding="utf-8") as f:
			return json.load(f)
	except (OSError, ValueError):
		return {"enabled": False, "limit": 0, "gen": 0}


def _answer(kind, admin):
	"""Câu trả lời đã xong theo kịch bản (dạng get_answer của hợp đồng P3)."""
	steps = [{"tool": "xem_mang", "label": "Phải thu"}, {"tool": "xem_mang", "label": "Tồn kho"},
		{"tool": "run_select", "label": "Truy vấn SQL",
			"sql": "SELECT customer, SUM(outstanding_amount) FROM `tabSales Invoice` WHERE docstatus = 1 AND x < 5 GROUP BY customer"}]
	sources = [{"section": "cong-no", "label": "Phải thu", "route": "#/cong-no"},
		{"section": "ton-kho", "label": "Tồn kho", "route": "#/ton-kho"},
		{"section": "xau", "label": "Nguồn lạ", "route": "javascript:alert(1)"}]
	if kind == "html":
		segs = [{"t": f"Lời có thẻ {XSS} và <b>đậm</b> & ký tự \"lạ\".\nDòng hai: ", "u": False},
			{"t": "<i>12 tỷ</i>", "u": True}]
	elif kind == "dai":
		segs = [{"t": "Mã rất dài: " + LONG + "\nHết.", "u": False}]
		steps = [{"tool": "run_select", "label": "Truy vấn SQL", "sql": "SELECT " + "a" * 900 + " FROM `tabItem`"}]
	else:
		segs = [{"t": "Phải thu quá hạn hiện là ", "u": False}, {"t": "1,6 tỷ", "u": False},
			{"t": ", tăng ", "u": False}, {"t": "251 triệu", "u": True}, {"t": " so với tháng trước (tự tính).\n- Khách lớn nhất: Công ty Mẫu\n- Tồn kho: ", "u": False},
			{"t": "35,2%", "u": False}, {"t": " là hàng Tết.", "u": False}]
	return {"status": "xong", "segments": segs, "unverified": sum(1 for s in segs if s["u"]), "sources": sources,
		"steps": steps}


def install_fakes():
	"""Thay qa.status / start / answer bằng kịch bản (giữ method API + guard thật)."""
	import frappe
	from bc.ai import qa

	st = {"gen": None, "used": 0, "q": {}, "seq": 0}

	def sync():
		m = _mode()
		if m.get("gen") != st["gen"]:
			st.update(gen=m.get("gen"), used=0, q={}, seq=0)
		return m

	def admin():
		return "System Manager" in frappe.get_roles()

	def con(m):
		limit = int(m.get("limit") or 0)
		return {"used": st["used"], "remaining": max(0, limit - st["used"])}

	def status(user=None):
		m = sync()
		return {"enabled": bool(m.get("enabled")), "limit": int(m.get("limit") or 0), **con(m), "sql": admin(),
			"max_question": 500}

	def start(question, history=None):
		m = sync()
		q = str(question or "").strip()
		if not q:
			frappe.throw("Câu hỏi trống.")
		if len(q) > 500:
			frappe.throw("Câu hỏi dài quá 500 ký tự.")
		if not m.get("enabled"):
			frappe.throw(qa.M_TAT)
		if any(not v.get("xong") for v in st["q"].values()):
			frappe.throw(qa.M_BAN)
		if st["used"] >= int(m.get("limit") or 0):
			frappe.throw(qa.M_HET_LUOT.format(n=int(m.get("limit") or 0)))
		if "[tuchoi]" in q:
			frappe.throw(qa.M_TRAN)
		kind = next((k for k in ("html", "dai", "loi", "cham") if f"[{k}]" in q), "mac-dinh")
		st["used"] += 1
		st["seq"] += 1
		qid = f"QA{st['gen']}-{st['seq']}"
		hist = json.loads(history) if isinstance(history, str) and history else (history or [])
		st["q"][qid] = {"kind": kind, "polls": 0, "history": hist}
		print("ask", qid, kind, "history", len(hist), flush=True)
		return {"id": qid, "status": "cho"}

	def answer(qid):
		m = sync()
		v = st["q"].get(str(qid))
		if not v:
			return {"status": "loi", "message": qa.M_KHONG_THAY, **con(m)}
		v["polls"] += 1
		if v["kind"] == "cham" or v["polls"] < 3:
			return {"status": "cho"}
		v["xong"] = True
		if v["kind"] == "loi":
			return {"status": "loi", "message": "Trợ lý từ chối <b>câu này</b>", **con(m)}
		return {**_answer(v["kind"], admin()), **con(m)}

	qa.status, qa.start, qa.answer = status, start, answer


def serve(port):
	import server  # noqa: F401 — đặt đường dẫn app bc (BC_APP_ROOT) trước khi nạp bc.ai.qa
	import seed_ui_ai
	install_fakes()
	seed_ui_ai.serve(port)


if __name__ == "__main__":
	cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
	if cmd == "serve":
		serve(int(sys.argv[2]))
	elif cmd == "seed":
		import seed_ui_ai
		seed_ui_ai.seed("fresh")
	else:
		sys.exit("dùng: seed_ui_qa.py seed|serve <port>")
