#!/usr/bin/env bash
# Chạy toàn bộ kiểm thử bc trên MariaDB (không cần bench). Cần: mariadb-server đang chạy, pip pymysql,
# DocType JSON v16 (./fetch_schema.sh). Giao diện: node + playwright (thiếu thì bỏ qua).
set -uo pipefail
cd "$(dirname "$0")"
[ -d .src/erpnext ] && [ -d .src/frappe/frappe/email/doctype ] || ./fetch_schema.sh
python3 -B extract_cf.py >/dev/null
fail=0
for t in test_sx.py test_channel.py test_cn.py test_attp.py test_tet_source.py test_vc.py test_ns.py test_sections.py \
		test_kho_ton.py test_kho_han.py test_kho_kk.py test_kho_nhap.py test_kho_nen.py; do
	echo "═══ $t"; python3 -B "$t" | tail -1 || fail=1
	python3 -B "$t" >/dev/null 2>&1 || fail=1
done
# Trợ lý AI: mỗi bộ thử một DB riêng; LLM giả, không bộ nào ra mạng
for t in render redact llm store rules_kd rules_kho rules_cn rules_vc rules_ns he_thong api pipeline tinh \
		p2_nen openai review ks kpi brief p2_e2e chat sql qa p3_e2e; do
	echo "═══ test_ai_$t.py"; out=$(BC_TEST_DB=bc_test_ai_$t python3 -B "test_ai_$t.py" 2>&1); rc=$?
	echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
done
echo "═══ lunar_check.mjs"; node lunar_check.mjs | tail -1 || fail=1
if node -e "require('playwright')" 2>/dev/null; then
	pkill -f '^python3 -B server.py 812' || true; sleep 0.5  # server cũ còn giữ cổng = code + cache cũ
	python3 -B seed_ui2.py >/dev/null && (env -u BC_OLD_PUBLIC python3 -B server.py 8124 > /tmp/bc-ui-server.log 2>&1 &) && sleep 1
	echo "═══ ui_check.mjs"; node ui_check.mjs http://127.0.0.1:8124 | tail -1 || fail=1
	(env -u BC_OLD_PUBLIC BC_UI_USER=Administrator python3 -B server.py 8126 > /tmp/bc-ui-server-admin.log 2>&1 &) && sleep 1
	echo "═══ sections_check.mjs"; node sections_check.mjs http://127.0.0.1:8124 http://127.0.0.1:8126 | tail -1 || fail=1
	pkill -f '^python3 -B server.py 8124' || true
	pkill -f '^python3 -B server.py 8126' || true
	# Nhóm Kho: số liệu trên seed sổ kho riêng (DB khác) — 4 màn so với API
	pkill -f '^python3 -B server.py 8127' || true; sleep 0.5
	BC_TEST_DB=bc_test_kho_ui python3 -B seed_ui_kho.py >/dev/null \
		&& (env -u BC_OLD_PUBLIC BC_TEST_DB=bc_test_kho_ui python3 -B server.py 8127 > /tmp/bc-ui-server-kho.log 2>&1 &) && sleep 1
	for u in ui_kho_ton.mjs ui_kho_han.mjs ui_kho_kk.mjs ui_kho_nhap.mjs; do
		echo "═══ $u"; out=$(node "$u" http://127.0.0.1:8127 2>&1); rc=$?
		echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
	done
	# Thời gian thực trên seed có sổ kho: số mã có tồn từng kho (danh sách kho rỗng thì trượt)
	echo "═══ ui_check.mjs /thoi-gian-thuc (seed Kho)"; out=$(BC_UI_KHO=1 node ui_check.mjs http://127.0.0.1:8127 /thoi-gian-thuc 2>&1); rc=$?
	echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
	# Hạn dùng — lượt phụ (seed lại cùng DB, sau mọi kiểm trên seed gộp): bật cache, sổ chỉ còn lô thu hồi + phần âm, sổ rỗng
	for pass in cache thu-hoi empty; do
		BC_TEST_DB=bc_test_kho_ui python3 -B test_kho_han.py seed-$pass >/dev/null || fail=1
		echo "═══ ui_kho_han.mjs $pass"; out=$(node ui_kho_han.mjs http://127.0.0.1:8127 $pass 2>&1); rc=$?
		echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
	done
	pkill -f '^python3 -B server.py 8127' || true
	# Trợ lý AI: #/tro-ly + #/ai (LLM giả, hàng đợi giả, chặn mạng) — 2 lượt seed riêng (fresh / stale)
	for pass in fresh stale; do
		pkill -f 'seed_ui_ai.py serve 812[89]' || true; sleep 0.5
		BC_TEST_DB=bc_test_ai_ui python3 -B seed_ui_ai.py $pass >/dev/null || fail=1
		(env -u BC_OLD_PUBLIC BC_TEST_DB=bc_test_ai_ui python3 -B seed_ui_ai.py serve 8128 > /tmp/bc-ui-ai-v.log 2>&1 &)
		(env -u BC_OLD_PUBLIC BC_TEST_DB=bc_test_ai_ui BC_UI_USER=Administrator python3 -B seed_ui_ai.py serve 8129 > /tmp/bc-ui-ai-a.log 2>&1 &)
		sleep 1.5
		echo "═══ ui_ai.mjs $pass"; out=$(node ui_ai.mjs http://127.0.0.1:8128 http://127.0.0.1:8129 $pass 2>&1); rc=$?
		echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
	done
	pkill -f 'seed_ui_ai.py serve 812[89]' || true
	# Hỏi đáp (P3): #/hoi-dap hai vai — API thật (guard), máy hỏi đáp theo kịch bản (seed_ui_qa.py); seed lại mỗi lượt
	pkill -f 'seed_ui_qa.py serve 815[01]' || true; sleep 0.5
	rm -f /tmp/bc-ui-qa-mode.json
	BC_TEST_DB=bc_test_ai_qa_ui python3 -B seed_ui_qa.py seed >/dev/null || fail=1
	(env -u BC_OLD_PUBLIC BC_TEST_DB=bc_test_ai_qa_ui BC_UI_QA_MODE=/tmp/bc-ui-qa-mode.json python3 -B seed_ui_qa.py serve 8150 > /tmp/bc-ui-qa-v.log 2>&1 &)
	(env -u BC_OLD_PUBLIC BC_TEST_DB=bc_test_ai_qa_ui BC_UI_QA_MODE=/tmp/bc-ui-qa-mode.json BC_UI_USER=Administrator python3 -B seed_ui_qa.py serve 8151 > /tmp/bc-ui-qa-a.log 2>&1 &)
	sleep 1.5
	echo "═══ ui_qa.mjs"; out=$(node ui_qa.mjs http://127.0.0.1:8150 http://127.0.0.1:8151 /tmp/bc-ui-qa-mode.json 2>&1); rc=$?
	echo "$out" | tail -1; [ $rc -eq 0 ] || fail=1
	pkill -f 'seed_ui_qa.py serve 815[01]' || true
	if [ -n "${BC_OLD_PUBLIC:-}" ]; then  # public/bc của bản đang chạy trên site trước deploy
		(BC_OLD_PUBLIC="$BC_OLD_PUBLIC" python3 -B server.py 8125 > /tmp/bc-ui-server-old.log 2>&1 &) && sleep 1
		echo "═══ old_tab_check.mjs"; node old_tab_check.mjs http://127.0.0.1:8125 | tail -1 || fail=1
		pkill -f '^python3 -B server.py 8125' || true
	fi
else
	echo "BỎ QUA giao diện: không có playwright"
fi
exit $fail
