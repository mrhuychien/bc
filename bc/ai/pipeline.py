# -*- coding: utf-8 -*-
"""bc.ai.pipeline — một lượt chạy của Trợ lý AI (đặc tả §2).

  1 collect   bc.ai.collect.build: payload của chính các method bc.api.* (Administrator, refresh=1)
  2 detect    detector hệ thống → pack["he-thong"]
  3 signals   quy tắc đọc pack → [Signal]
  4 upsert    BC AI Insight theo signal_key: mới / còn / hết → đóng (lời quy tắc đã thay số)
  5 write     (ai_enabled, có khoá, chưa chạm trần) Claude, một lượt gọi / nhóm
  6 render    placeholder → số thật; còn số trần / path sai → bỏ lời AI, giữ lời quy tắc (needs_check)
  8 log       BC AI Run: dòng tổng + một dòng / lượt gọi (token, chi phí, trạng thái), ảnh chụp KPI

Bước 5–6 lỗi bất kỳ chỉ ghi vào BC AI Run — KHÔNG làm hỏng bước 1–4 và 8: tắt AI / hết credit / API lỗi thì màn vẫn
hiện tín hiệu với lời theo quy tắc. Không lưu, không log đề bài hay gói số. Lời AI chỉ được lưu sau khi máy chủ thay
số và kiểm (bc.ai.render).

Đề bài một nhóm: KHÔNG gồm mảng đang ẩn với người xem (số lẫn tín hiệu; quy tắc vẫn chạy trên đủ gói), không gồm khối
registry.NO_SEND; mã giả đặt lại cho từng nhóm (mask.begin — mã không có trong đề bài này thì không thành tên); kèm
"kieu" (registry.kind_map). Lời AI lưu với sections_used = mảng của placeholder ∪ mọi mảng mô hình đã thấy (ẩn một mảng
sau lượt chạy → lời đó ẩn với người xem tới lượt sau). Nhận định tự do trên số của chủ đề đang bo-qua → loại; trùng
tín hiệu quy tắc đang mở → bỏ (store.blocked_paths).

Dòng tổng (step "tong"): status ok = bước quy tắc xong (kể cả khi AI tắt / lỗi); loi = lượt chạy hỏng (error = TÊN
loại lỗi). error của dòng tổng ok liệt kê quy tắc không chạy được. Bước AI:
- cả bước bị bỏ → MỘT dòng step "ai" (tat | khong-khoa | vuot-tran; vượt trần vì 30 lượt / ngày thì error "quá số
  lượt gọi trong ngày"), hoặc loi khi chính bước AI hỏng trước lượt gọi đầu;
- còn lại một dòng / nhóm đã tới lượt: ok | loi | het-credit (lượt gọi), vuot-tran / loi "hết thời gian lượt chạy"
  (dừng giữa chừng, không gọi). Sau het-credit / vuot-tran / hết giờ: các nhóm sau không gọi, không có dòng.
- lỗi không lường trong một nhóm (không phải LLMError) → dòng nhóm đó loi, error "lỗi không lường: <loại>", nhóm sau
  vẫn được gọi.
Nhóm không gọi được (bỏ / lỗi / dừng) → nhận định tự do cũ của nhóm bị đóng (đặc tả: chỉ sống khi lượt gọi gần nhất
nêu lại). Error Log của module này chỉ có tên loại lỗi + vị trí dòng code — không lời lỗi (có thể chứa khoá / số
liệu), không biến cục bộ.
"""

from __future__ import annotations

import time
import traceback

import frappe
from frappe.utils import cint, getdate, now_datetime

from bc.ai import DEFAULT_MAX_SIGNALS, conf, daily_model
from bc.ai import registry
from bc.ai.jobs import JOB_TIMEOUT, LOCK_KEY, LOCK_TTL

PROVIDER = "claude"
MAX_FREE = 3             # nhận định tự do tối đa / nhóm / lượt
CALL_TIMEOUT = 300       # giây / lượt gọi
MARGIN = 240             # giây chừa lại cuối job cho bước 8
SO_NGAY_KEY = "so_ngay"
HET_GIO = "hết thời gian lượt chạy"
QUA_LUOT = "quá số lượt gọi trong ngày"


def _ghi_loi(title: str, e: BaseException) -> None:
	"""Error Log KHÔNG dữ liệu: tên loại lỗi + các dòng code. Không str(e) (lỗi từ thư viện HTTP / bản giả có thể chứa
	khoá), không get_traceback (developer_mode kèm biến cục bộ = đề bài, gói số). message luôn khác rỗng — log_error
	của v16 nhận message rỗng thì tự lấy get_traceback(with_context=True)."""
	try:
		noi = " <- ".join(f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno} {f.name}"
			for f in reversed(traceback.extract_tb(e.__traceback__)[-8:]))
		frappe.log_error(title=title, message=f"{type(e).__name__} tại {noi or '?'}")
		frappe.clear_last_message()
	except Exception:   # ghi nhật ký hỏng không được làm hỏng lượt chạy
		pass


def run_daily(run_type: str = "ngay") -> dict:
	"""Chạy một lượt (scheduler: "ngay"; nút Chạy ngay: "tay"). Trả tóm tắt {status, run, signals, ai…}.

	Chạy dưới Administrator (qua _guard của mảng đang ẩn — job do quản trị bấm cũng vậy), trả lại user cũ khi xong.
	Đang có lượt khác giữ khoá → {"status": "dang-chay"}, không ghi gì, không đụng khoá. Lỗi ngoài dự kiến: dòng tổng
	status loi (error = tên loại lỗi) + Error Log, nhả khoá, KHÔNG ném tiếp → {"status": "loi", "run"}."""
	from bc.ai import store

	cache = frappe.cache()
	if cache.get_value(LOCK_KEY):
		return {"status": "dang-chay"}
	cache.set_value(LOCK_KEY, 1, expires_in_sec=LOCK_TTL)
	cu = getattr(getattr(frappe, "session", None), "user", None)
	run = None
	try:
		t0 = time.monotonic()
		frappe.set_user("Administrator")
		now = now_datetime()
		run = store.start_run(run_type, "tong", now=now)
		frappe.db.commit()   # dòng tổng phải còn sau rollback ở nhánh lỗi
		out = _run(run, run_type, now, t0)
		frappe.db.commit()
		return out
	except Exception as e:
		_that_bai(run, e)
		return {"status": "loi", "run": run}
	finally:
		cache.delete_value(LOCK_KEY)
		if cu and cu != "Administrator":
			try:
				frappe.set_user(cu)
			except Exception:
				pass


def _that_bai(run, e: BaseException) -> None:
	"""Lượt chạy hỏng: bỏ phần ghi dở, Error Log, chốt dòng tổng loi. Không ném."""
	from bc.ai import store
	try:
		frappe.db.rollback()
	except Exception:
		pass
	_ghi_loi("bc.ai run_daily", e)
	if not run:
		return
	try:
		store.finish_run(run, status="loi", now=now_datetime(), error=type(e).__name__)
		frappe.db.commit()
	except Exception as e2:
		_ghi_loi("bc.ai run_daily (chốt dòng tổng)", e2)


def _run(run: str, run_type: str, now, t0: float) -> dict:
	from bc.ai import collect, store

	today = getdate(now)
	pack = collect.build(today)                                   # 1
	pack[registry.HE_THONG] = registry.run_detectors(now)         # 2
	rr = registry.run_rules(pack, registry.overrides_from_settings())   # 3
	items, sigs = _rule_items(pack, rr)
	stats = store.sync_signals(items, rr.ran, now)                # 4
	frappe.db.commit()
	names = stats.get("names") or {}
	by_name = {names[k]: s for k, s in sigs.items() if names.get(k)}
	ai = _write(pack, by_name, run, run_type, now, t0)            # 5–6 (không bao giờ ném)
	store.rerank()
	store.cleanup(now)
	store.finish_run(run, status="ok", now=now_datetime(), signals=len(items), insights_ai=ai["accepted"],
		rejected=ai["rejected"], kpis=registry.snapshot_kpis(pack),                                    # 8
		error=("quy tắc không chạy được: " + ", ".join(sorted(rr.not_run)))[:300] if rr.not_run else None)
	return {"status": "ok", "run": run, "signals": len(items), "not_run": dict(rr.not_run), "ai": ai["status"],
		"accepted": ai["accepted"], "rejected": ai["rejected"], **{k: stats.get(k) for k in ("new", "closed")}}


def _rule_items(pack: dict, rr) -> tuple:
	"""Tín hiệu → dict đã dựng lời quy tắc cho store.sync_signals. Quy tắc có lời không dựng được (sai kiểu số) bị coi
	là KHÔNG chạy được: bỏ mọi tín hiệu của nó, tín hiệu cũ giữ nguyên. Trả (items, {key: Signal})."""
	from bc.ai import render

	hong, tam = set(), []
	for s in rr.signals:
		r = render.render_rule(s.title, s.detail, pack)
		if not r["ok"]:
			hong.add(s.rule)
			frappe.log_error(title="bc.ai lời quy tắc không dựng được",
				message=f"{s.rule}: {', '.join(r['errors'])[:200]}")
			continue
		tam.append((s, r))
	for k in hong:
		rr.ran.discard(k)
		rr.not_run[k] = "loi-loi"
	items, sigs = [], {}
	for s, r in tam:
		if s.rule in hong:
			continue
		sigs[s.key] = s
		items.append({"key": s.key, "rule": s.rule, "section": s.section, "audience": s.audience,
			"severity": s.severity, "route": s.route, "title": r["title"], "body": r["body"], "paths": r["paths"],
			"sections_used": r["sections_used"] or [s.section], "documents": s.documents})
	return items, sigs


# ─── Bước 5–6: mô hình viết lời ──────────────────────────────────────────────
def _write(pack: dict, by_name: dict, run: str, run_type: str, now, t0: float) -> dict:
	"""Gọi mô hình cho từng nhóm và gắn lời đã kiểm. by_name = {tên Insight: Signal của lượt này}. Mọi lỗi ở đây chỉ
	thành trạng thái trong BC AI Run."""
	from bc.ai import store

	out = {"status": "ok", "accepted": 0, "rejected": 0}
	try:
		skip, why = _skip_reason(getdate(now))
		if skip:
			_close_all_free(now)
			row = store.start_run(run_type, "ai", provider=PROVIDER, now=now_datetime(), run_id=run)
			store.finish_run(row, status=skip, now=now_datetime(), error=why or None)
			frappe.db.commit()
			out["status"] = skip
			return out
		_write_groups(pack, by_name, run, run_type, now, t0, out)
	except Exception as e:
		# Hỏng ngoài một nhóm (dựng mã giả / đề bài, ghi Run): bỏ phần ghi dở, đóng lời tự do, một dòng "ai" loi.
		try:
			frappe.db.rollback()
		except Exception:
			pass
		_ghi_loi("bc.ai bước AI", e)
		out["status"] = "loi"
		try:
			_close_all_free(now)
			row = store.start_run(run_type, "ai", provider=PROVIDER, now=now_datetime(), run_id=run)
			store.finish_run(row, status="loi", now=now_datetime(), error=f"lỗi bước AI: {type(e).__name__}")
			frappe.db.commit()
		except Exception as e2:
			_ghi_loi("bc.ai bước AI (ghi nhật ký)", e2)
	return out


def _skip_reason(today) -> tuple:
	"""Lý do bỏ cả bước AI → (status | None, error | None): 'tat' | 'khong-khoa' | 'vuot-tran'."""
	from bc.ai import budget, llm

	if not cint(conf("ai_enabled", 0)):
		return "tat", None
	if not llm.has_key(PROVIDER):
		return "khong-khoa", None
	ok, why = budget.can_call(PROVIDER, today)
	if not ok:
		return "vuot-tran", (QUA_LUOT if why == "qua-so-luot" else None)
	return None, None


def _close_all_free(now) -> None:
	from bc.ai import store
	for g in registry.GROUPS.values():
		store.sync_ai_free(g["sections"], [], now)


def _goi_duoc(pack: dict, sections, an: set) -> dict:
	"""Bản gói số GỬI mô hình của một nhóm: bỏ mảng đang ẩn với người xem (an), mảng không có số dùng được và các khối
	registry.NO_SEND (kỳ trước — chỉ quy tắc đọc). Bản sao nông: pack gốc không đổi (render vẫn phân giải trên đó)."""
	out = {}
	for s in sections:
		if s in an or not _co_so(pack.get(s)):
			continue
		khoi = {k: v for k, v in pack[s].items() if (s, k) not in registry.NO_SEND}
		if _co_so(khoi):
			out[s] = khoi
	return out


def _write_groups(pack: dict, by_name: dict, run: str, run_type: str, now, t0: float, out: dict) -> None:
	from bc.ai import budget, llm, prompt, redact, store
	from bc.api._common import hidden_sections

	today = getdate(now)
	model = daily_model()
	limit = cint(conf("ai_max_signals")) or DEFAULT_MAX_SIGNALS
	mask = redact.build(bool(cint(conf("ai_mask_parties", 1))))
	system = prompt.system_prompt(today)
	kinds = registry.kind_map(by_name.values())   # kiểu đúng của số (KPIS + lời quy tắc lượt này) — chỉ xét lời mô hình
	an = hidden_sections()   # bộ quản trị đặt (đọc thẳng tabSingles, không theo người gọi)
	dung = None    # lý do dừng gọi tiếp (hết credit / mất khoá / vượt trần / hết giờ): nhóm còn lại chỉ đóng lời cũ
	for group, g in registry.GROUPS.items():
		sections = g["sections"]
		if dung:
			store.sync_ai_free(sections, [], now)
			continue
		# lọc theo tín hiệu CỦA LƯỢT NÀY (tín hiệu cũ của quy tắc không chạy được không gửi) rồi mới cắt `limit`;
		# mảng đang ẩn: không gửi số, không gửi tín hiệu (giữ lời quy tắc — chỉ quản trị thấy)
		rows = [r for r in store.open_for_llm(sections, 10 ** 6) if r["name"] in by_name
			and r["section"] not in an][:limit]
		pack_group = _goi_duoc(pack, sections, an)
		if not rows and (group == registry.HE_THONG or not pack_group):
			store.sync_ai_free(sections, [], now)    # nhóm không có gì để nói → không tốn lượt gọi
			continue
		con = JOB_TIMEOUT - MARGIN - (time.monotonic() - t0)
		ok, why = budget.can_call(PROVIDER, today)
		if con < 60 or not ok:
			dung = "vuot-tran" if not ok else "loi"
			row = store.start_run(run_type, group, provider=PROVIDER, model=model, now=now_datetime(), run_id=run)
			store.finish_run(row, status=dung, now=now_datetime(),
				error=(QUA_LUOT if why == "qua-so-luot" else None) if not ok else HET_GIO)
			store.sync_ai_free(sections, [], now)
			frappe.db.commit()
			out["status"] = dung
			continue
		row = store.start_run(run_type, group, provider=PROVIDER, model=model, now=now_datetime(), run_id=run)
		frappe.db.commit()   # dòng của lượt gọi còn lại dù phần sau bị rollback
		st = _goi_nhom(group, sections, rows, by_name, pack, pack_group, mask, system, model, row, con, now, today,
			out, kinds)
		frappe.db.commit()
		if st in ("het-credit", "khong-khoa"):
			dung = st


def _goi_nhom(group, sections, rows, by_name, pack, pack_group, mask, system, model, row, con, now, today,
		out, kinds=None) -> str:
	"""Một lượt gọi cho một nhóm + gắn lời → status của dòng Run (đã chốt). Không ném."""
	from bc.ai import llm, prompt, store

	res = None
	try:
		by_id = {f"S{i}": r for i, r in enumerate(rows, 1)}
		mask.begin()   # chỉ mã giả phát ra cho ĐỀ BÀI NÀY mới được đổi lại thành tên (mã nhóm trước → mã lạ)
		tin_hieu = [_ctx(sid, r, by_name[r["name"]], today, mask) for sid, r in by_id.items()]
		user, notes = prompt.build_user(group, mask.mask(pack_group), mask.mask(tin_hieu), kinds=kinds)
		# Một lượt gọi tệ nhất = 3 lần POST × (10 s nối + timeout) + 25 s chờ → chia thời gian còn lại cho vừa.
		res = llm.call(PROVIDER, model, system, user, prompt.SCHEMA_NAME, prompt.SCHEMA,
			timeout=max(30, min(CALL_TIMEOUT, int((con - 60) / 3))))
		del user
		ti, to = cint(res.get("tokens_in")), cint(res.get("tokens_out"))
		served = res.get("model") or model
		data = res.get("data")
		# mảng mô hình đã thấy = mảng của gói gửi đi + mảng của tín hiệu gửi đi (lời AI gắn với TẤT CẢ: ẩn một mảng
		# sau lượt chạy thì lời AI của nhóm đó ẩn với người xem tới lượt sau)
		da_thay = [*pack_group, *(r["section"] for r in rows)]
		acc, rej = _apply(group, sections, data if isinstance(data, dict) else {}, by_id, pack, mask, now,
			kinds=kinds, da_thay=da_thay)
	except llm.LLMError as e:
		st = llm.run_status(e.kind)
		# Lượt bị từ chối / cắt cụt / sai schema vẫn bị tính tiền → ghi token + chi phí nếu máy chủ đã trả lời.
		ti, to = cint(getattr(e, "tokens_in", 0)), cint(getattr(e, "tokens_out", 0))
		served = llm.clean(getattr(e, "model", "") or "")[:140]
		store.finish_run(row, status=st, now=now_datetime(), signals=len(rows),
			error=llm.clean(e.message) or e.kind, tokens_in=ti, tokens_out=to, model=served or model,
			cost_usd=_cost(served, model, ti, to) if (ti or to) else 0.0)
		store.sync_ai_free(sections, [], now)
		out["status"] = st
		return st
	except Exception as e:   # lỗi lập trình / đầu ra lạ: bỏ phần lời ghi dở của nhóm này, nhóm sau vẫn gọi
		try:
			frappe.db.rollback()
		except Exception:
			pass
		_ghi_loi(f"bc.ai bước AI nhóm {group}", e)
		ti = cint(res.get("tokens_in")) if isinstance(res, dict) else 0
		to = cint(res.get("tokens_out")) if isinstance(res, dict) else 0
		served = (res.get("model") if isinstance(res, dict) else None) or model
		store.finish_run(row, status="loi", now=now_datetime(), signals=len(rows), tokens_in=ti, tokens_out=to,
			model=served, cost_usd=_cost(served, model, ti, to) if (ti or to) else 0.0,
			error=f"lỗi không lường: {type(e).__name__}")
		store.sync_ai_free(sections, [], now)
		out["status"] = "loi"
		return "loi"
	out["accepted"] += acc
	out["rejected"] += rej
	store.finish_run(row, status="ok", now=now_datetime(), tokens_in=ti, tokens_out=to, model=served,
		signals=len(rows), insights_ai=acc, rejected=rej, cost_usd=_cost(served, model, ti, to),
		error="; ".join(notes)[:300] if notes else None)
	return "ok"


def _cost(served: str | None, requested: str, tokens_in: int, tokens_out: int):
	"""Chi phí theo giá mô hình THỰC trả lời; mô hình đó chưa khai giá (vd mô hình dự phòng khi bị từ chối) → ước theo
	giá mô hình đã yêu cầu để trần chi vẫn đếm; cả hai chưa khai → None (chưa khai giá)."""
	from bc.ai import budget
	c = budget.cost(served, tokens_in, tokens_out) if served else None
	return c if c is not None else budget.cost(requested, tokens_in, tokens_out)


def _co_so(block) -> bool:
	"""Mảng có ít nhất một payload dùng được (không _error, không available False)."""
	if not isinstance(block, dict):
		return False
	return any(isinstance(v, dict) and not v.get("_error") and v.get("available") is not False
		for k, v in block.items() if k != "_ai")


def _ctx(sid: str, row: dict, sig, today, mask) -> dict:
	"""Một tín hiệu trong đề bài. Lời quy tắc gửi đi CÒN placeholder (lời đã thay số có thể chứa tên khách thật).
	Chữ tự do (ghi chú của quản trị, lời quy tắc) → mask_text che tên khách / NCC xuất hiện giữa câu (mask.mask chỉ
	thay chuỗi bằng đúng một tên). Không gửi chứng từ, tên Insight, signal_key."""
	fs = row.get("first_seen")
	return {"id": sid, "rule": row["rule"], "muc": row["severity"],
		"loi_quy_tac": mask.mask_text(sig.title + (" — " + sig.detail if sig.detail else "")),
		"paths": list(sig.paths), SO_NGAY_KEY: max(0, (today - getdate(fs)).days) if fs else 0,
		"trang_thai": row["status"], "ghi_chu_quan_tri": mask.mask_text(row.get("admin_note") or "")}


def _apply(group: str, sections, data: dict, by_id: dict, pack: dict, mask, now, kinds=None, da_thay=()) -> tuple:
	"""Xử lý đầu ra của mô hình cho một nhóm (đặc tả §5.3 bước 4–7) → (số lời nhận, số lời loại).

	sections: mọi mảng của nhóm (nhận định tự do cũ của chúng không được nêu lại → đóng). da_thay: mảng mô hình đã
	thấy trong lượt gọi (gói + tín hiệu gửi đi; không gồm mảng đang ẩn) → lời chỉ được trích số của các mảng này, và
	sections_used của MỌI lời AI lưu cộng thêm chúng (lời không placeholder vẫn có thể kể số của mảng khác). Trống →
	mọi mảng của nhóm. kinds: kiểu đúng của số (registry.kind_map) — lời sai kiểu bị loại. Nhận định tự do trên path
	đang bo-qua (store.blocked_paths) → loại; chỉ lặp một tín hiệu quy tắc đang mở → bỏ qua lặng lẽ."""
	from bc.ai import render, store

	acc = rej = 0
	da_gan, free = set(), {}
	thay = list(dict.fromkeys(str(s) for s in da_thay if s))
	duoc = {s for s in sections if s in thay} if thay else set(sections)
	chan = store.blocked_paths(duoc, now)
	ds = data.get("insights")
	for ins in (ds if isinstance(ds, list) else []):
		if not isinstance(ins, dict):
			continue
		raw = {"title": ins.get("title") or "", "body": ins.get("body") or "", "advice": ins.get("advice") or []}
		sev = ins.get("severity") if ins.get("severity") in registry.SEVERITIES else "vang"
		prio = max(0, min(5, cint(ins.get("priority"))))   # schema không ràng khoảng → kẹp (5 = đáng chú ý nhất)
		sid = ins.get("signal")
		if sid:
			sid = str(sid).strip()
			row = by_id.get(sid)
			if not row or sid in da_gan:      # S lạ / trùng → lấy cái đầu
				continue
			da_gan.add(sid)
			r = render.render_insight(raw, pack, duoc, mask, kinds=kinds)
			if r["ok"]:
				store.apply_ai(row["name"], title=r["title"], body=r["body"], advice=r["advice"], severity=sev,
					priority=prio, paths=r["paths"], sections_used=[*r["sections_used"], *thay], now=now)
				acc += 1
			else:
				store.mark_rejected(row["name"])
				rej += 1
			continue
		if group == registry.HE_THONG:       # nhóm hệ thống không nhận nhận định tự do
			continue
		r = render.render_insight(raw, pack, duoc, mask, kinds=kinds)
		body = raw["body"] if isinstance(raw["body"], str) else ""
		dau = next((p for p, _ in registry.placeholders(body)), None) or (r["paths"][0] if r["paths"] else None)
		if not r["ok"] or not dau:            # nhận định tự do phải trích ít nhất một số trong gói
			rej += 1
			continue
		goc = registry.strip_index(dau)
		if chan.get(goc) == store.BO_QUA:     # chủ đề quản trị đã bỏ qua → không cho quay lại qua lời tự do
			rej += 1
			continue
		if goc in chan:                       # trùng tín hiệu quy tắc đang mở → thừa
			continue
		key = ("ai:" + goc)[:140]
		if key in free:
			continue
		sec = registry.section_of(dau)
		free[key] = {"key": key, "section": sec, "route": f"#/{sec}", "severity": sev, "priority": prio,
			"title": r["title"], "body": r["body"], "advice": r["advice"], "paths": r["paths"],
			"sections_used": list(dict.fromkeys([*r["sections_used"], *thay]))}
	chon = sorted(free.values(), key=lambda x: (x["severity"] != "do", -x["priority"]))[:MAX_FREE]
	store.sync_ai_free(sections, chon, now)
	return acc + len(chon), rej
