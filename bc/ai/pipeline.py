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

Dòng tổng (step "tong"): status ok = bước quy tắc xong (kể cả khi AI tắt / lỗi); loi = lượt chạy hỏng. Bước AI: một
dòng / nhóm đã gọi (ok | loi | het-credit | vuot-tran), hoặc MỘT dòng step "ai" khi cả bước bị bỏ (tat | khong-khoa |
vuot-tran).
"""

from __future__ import annotations

import time

import frappe
from frappe.utils import cint, getdate, now_datetime

from bc.ai import DEFAULT_CLAUDE_MODEL, DEFAULT_MAX_SIGNALS, conf
from bc.ai import registry
from bc.ai.jobs import JOB_TIMEOUT, LOCK_KEY, LOCK_TTL

PROVIDER = "claude"
MAX_FREE = 3             # nhận định tự do tối đa / nhóm / lượt
CALL_TIMEOUT = 300       # giây / lượt gọi
MARGIN = 240             # giây chừa lại cuối job cho bước 8
SO_NGAY_KEY = "so_ngay"


def run_daily(run_type: str = "ngay") -> dict:
	"""Chạy một lượt (scheduler: "ngay"; nút Chạy ngay: "tay"). Trả tóm tắt {status, run, signals, ai…}.

	Luôn chạy dưới Administrator (qua _guard của mảng đang ẩn — job do quản trị bấm cũng vậy). Đang có lượt khác giữ
	khoá → bỏ qua. Lỗi ngoài dự kiến: ghi dòng tổng status loi + Error Log (chỉ traceback), không ném tiếp."""
	from bc.ai import store

	cache = frappe.cache()
	if cache.get_value(LOCK_KEY):
		return {"status": "dang-chay"}
	cache.set_value(LOCK_KEY, 1, expires_in_sec=LOCK_TTL)
	t0 = time.monotonic()
	frappe.set_user("Administrator")
	now = now_datetime()
	run = store.start_run(run_type, "tong", now=now)
	try:
		out = _run(run, run_type, now, t0)
		frappe.db.commit()
		return out
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "bc.ai run_daily")
		frappe.clear_last_message()
		store.finish_run(run, status="loi", now=now_datetime(), error=type(e).__name__)
		frappe.db.commit()
		return {"status": "loi", "run": run}
	finally:
		cache.delete_value(LOCK_KEY)


def _run(run: str, run_type: str, now, t0: float) -> dict:
	from bc.ai import collect, store

	today = getdate(now)
	pack = collect.build(today)                                   # 1
	pack[registry.HE_THONG] = registry.run_detectors(now)         # 2
	rr = registry.run_rules(pack, registry.overrides_from_settings())   # 3
	items, sigs = _rule_items(pack, rr)
	stats = store.sync_signals(items, rr.ran, now)                # 4
	frappe.db.commit()
	ai = _write(pack, sigs, run, run_type, now, t0)               # 5–6 (không bao giờ ném)
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
			frappe.log_error(f"{s.key}: {', '.join(r['errors'])[:200]}", "bc.ai lời quy tắc không dựng được")
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
def _write(pack: dict, sigs: dict, run: str, run_type: str, now, t0: float) -> dict:
	"""Gọi mô hình cho từng nhóm và gắn lời đã kiểm. Mọi lỗi ở đây chỉ thành trạng thái trong BC AI Run."""
	from bc.ai import store

	out = {"status": "ok", "accepted": 0, "rejected": 0}
	try:
		skip = _skip_reason(getdate(now))
		if skip:
			_close_all_free(now)
			row = store.start_run(run_type, "ai", provider=PROVIDER, now=now_datetime(), run_id=run)
			store.finish_run(row, status=skip, now=now_datetime())
			out["status"] = skip
			return out
		_write_groups(pack, sigs, run, run_type, now, t0, out)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc.ai bước AI")
		frappe.clear_last_message()
		out["status"] = "loi"
	return out


def _skip_reason(today) -> str | None:
	"""Lý do bỏ cả bước AI: 'tat' | 'khong-khoa' | 'vuot-tran' | None."""
	from bc.ai import budget, llm

	if not cint(conf("ai_enabled", 0)):
		return "tat"
	if not llm.has_key(PROVIDER):
		return "khong-khoa"
	if not budget.can_call(PROVIDER, today)[0]:
		return "vuot-tran"
	return None


def _close_all_free(now) -> None:
	from bc.ai import store
	for g in registry.GROUPS.values():
		store.sync_ai_free(g["sections"], [], now)


def _write_groups(pack: dict, sigs: dict, run: str, run_type: str, now, t0: float, out: dict) -> None:
	from bc.ai import budget, llm, prompt, redact, store

	today = getdate(now)
	model = conf("ai_claude_model") or DEFAULT_CLAUDE_MODEL
	limit = cint(conf("ai_max_signals")) or DEFAULT_MAX_SIGNALS
	mask = redact.build(bool(cint(conf("ai_mask_parties", 1))))
	system = prompt.system_prompt(today)
	dung = None    # lý do dừng gọi tiếp (hết credit / mất khoá / vượt trần / hết giờ): các nhóm còn lại chỉ đóng lời cũ
	for group, g in registry.GROUPS.items():
		sections = g["sections"]
		if dung:
			store.sync_ai_free(sections, [], now)
			continue
		rows = [r for r in store.open_for_llm(sections, limit) if r["signal_key"] in sigs]
		pack_group = {s: pack[s] for s in sections if _co_so(pack.get(s))}
		if not rows and (group == registry.HE_THONG or not pack_group):
			store.sync_ai_free(sections, [], now)    # nhóm không có gì để nói → không tốn lượt gọi
			continue
		con = JOB_TIMEOUT - MARGIN - (time.monotonic() - t0)
		ok, why = budget.can_call(PROVIDER, today)
		if con < 60 or not ok:
			dung = "vuot-tran" if not ok else "loi"
			row = store.start_run(run_type, group, provider=PROVIDER, model=model, now=now_datetime(), run_id=run)
			store.finish_run(row, status=dung, now=now_datetime(),
				error=("quá số lượt gọi trong ngày" if why == "qua-so-luot" else None) if not ok else "hết thời gian lượt chạy")
			store.sync_ai_free(sections, [], now)
			out["status"] = dung
			continue
		by_id = {f"S{i}": r for i, r in enumerate(rows, 1)}
		tin_hieu = [_ctx(sid, r, sigs[r["signal_key"]], today) for sid, r in by_id.items()]
		user, notes = prompt.build_user(group, mask.mask(pack_group), mask.mask(tin_hieu))
		row = store.start_run(run_type, group, provider=PROVIDER, model=model, now=now_datetime(), run_id=run)
		try:
			res = llm.call(PROVIDER, model, system, user, prompt.SCHEMA_NAME, prompt.SCHEMA,
				timeout=max(30, min(CALL_TIMEOUT, int(con / 3))))
		except llm.LLMError as e:
			st = llm.run_status(e.kind)
			store.finish_run(row, status=st, now=now_datetime(), signals=len(rows), error=e.message)
			store.sync_ai_free(sections, [], now)
			out["status"] = st
			if e.kind in ("credit", "no_key"):
				dung = st
			frappe.db.commit()
			continue
		acc, rej = _apply(group, sections, res.get("data") or {}, by_id, pack, mask, now)
		out["accepted"] += acc
		out["rejected"] += rej
		store.finish_run(row, status="ok", now=now_datetime(), tokens_in=cint(res.get("tokens_in")),
			tokens_out=cint(res.get("tokens_out")), model=res.get("model") or model, signals=len(rows), insights_ai=acc,
			rejected=rej, cost_usd=budget.cost(res.get("model") or model, cint(res.get("tokens_in")),
				cint(res.get("tokens_out"))), error="; ".join(notes)[:300] if notes else None)
		frappe.db.commit()


def _co_so(block) -> bool:
	"""Mảng có ít nhất một payload dùng được (không _error, không available False)."""
	if not isinstance(block, dict):
		return False
	return any(isinstance(v, dict) and not v.get("_error") and v.get("available") is not False
		for k, v in block.items() if k != "_ai")


def _ctx(sid: str, row: dict, sig, today) -> dict:
	"""Một tín hiệu trong đề bài. Lời quy tắc gửi đi CÒN placeholder (lời đã thay số có thể chứa tên khách thật)."""
	fs = row.get("first_seen")
	return {"id": sid, "rule": row["rule"], "muc": row["severity"],
		"loi_quy_tac": (sig.title + (" — " + sig.detail if sig.detail else "")), "paths": list(sig.paths),
		SO_NGAY_KEY: max(0, (today - getdate(fs)).days) if fs else 0, "trang_thai": row["status"],
		"ghi_chu_quan_tri": row.get("admin_note") or ""}


def _apply(group: str, sections, data: dict, by_id: dict, pack: dict, mask, now) -> tuple:
	"""Xử lý đầu ra của mô hình cho một nhóm (đặc tả §5.3 bước 4–7) → (số lời nhận, số lời loại)."""
	from bc.ai import render, store

	acc = rej = 0
	da_gan, free = set(), {}
	for ins in (data.get("insights") or []):
		if not isinstance(ins, dict):
			continue
		raw = {"title": ins.get("title") or "", "body": ins.get("body") or "", "advice": ins.get("advice") or []}
		sev = ins.get("severity") if ins.get("severity") in registry.SEVERITIES else "vang"
		prio = cint(ins.get("priority"))
		sid = ins.get("signal")
		if sid:
			row = by_id.get(str(sid))
			if not row or sid in da_gan:      # S lạ / trùng → lấy cái đầu
				continue
			da_gan.add(sid)
			r = render.render_insight(raw, pack, set(sections), mask)
			if r["ok"]:
				store.apply_ai(row["name"], title=r["title"], body=r["body"], advice=r["advice"], severity=sev,
					priority=prio, paths=r["paths"], sections_used=r["sections_used"], now=now)
				acc += 1
			else:
				store.mark_rejected(row["name"])
				rej += 1
			continue
		if group == registry.HE_THONG:       # nhóm hệ thống không nhận nhận định tự do
			continue
		r = render.render_insight(raw, pack, set(sections), mask)
		dau = next((p for p, _ in registry.placeholders(raw["body"])), None) or (r["paths"][0] if r["paths"] else None)
		if not r["ok"] or not dau:            # nhận định tự do phải trích ít nhất một số trong gói
			rej += 1
			continue
		key = ("ai:" + registry.strip_index(dau))[:140]
		if key in free:
			continue
		sec = registry.section_of(dau)
		free[key] = {"key": key, "section": sec, "route": f"#/{sec}", "severity": sev, "priority": prio,
			"title": r["title"], "body": r["body"], "advice": r["advice"], "paths": r["paths"],
			"sections_used": r["sections_used"]}
	chon = sorted(free.values(), key=lambda x: (x["severity"] != "do", -x["priority"]))[:MAX_FREE]
	store.sync_ai_free(sections, chon, now)
	return acc + len(chon), rej
