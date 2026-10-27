#!/usr/bin/env bash
# Chạy toàn bộ kiểm thử bc trên MariaDB (không cần bench). Cần: mariadb-server đang chạy, pip pymysql,
# DocType JSON v16 (./fetch_schema.sh). Giao diện: node + playwright (thiếu thì bỏ qua).
set -uo pipefail
cd "$(dirname "$0")"
[ -d .src/erpnext ] || ./fetch_schema.sh
python3 -B extract_cf.py >/dev/null
fail=0
for t in test_sx.py test_channel.py test_cn.py test_attp.py test_tet_source.py test_vc.py test_ns.py; do
	echo "═══ $t"; python3 -B "$t" | tail -1 || fail=1
	python3 -B "$t" >/dev/null 2>&1 || fail=1
done
echo "═══ lunar_check.mjs"; node lunar_check.mjs | tail -1 || fail=1
if node -e "require('playwright')" 2>/dev/null; then
	pkill -f '^python3 -B server.py 812' || true; sleep 0.5  # server cũ còn giữ cổng = code + cache cũ
	python3 -B seed_ui2.py >/dev/null && (env -u BC_OLD_PUBLIC python3 -B server.py 8124 > /tmp/bc-ui-server.log 2>&1 &) && sleep 1
	echo "═══ ui_check.mjs"; node ui_check.mjs http://127.0.0.1:8124 | tail -1 || fail=1
	pkill -f '^python3 -B server.py 8124' || true
	if [ -n "${BC_OLD_PUBLIC:-}" ]; then  # public/bc của bản đang chạy trên site trước deploy
		(BC_OLD_PUBLIC="$BC_OLD_PUBLIC" python3 -B server.py 8125 > /tmp/bc-ui-server-old.log 2>&1 &) && sleep 1
		echo "═══ old_tab_check.mjs"; node old_tab_check.mjs http://127.0.0.1:8125 | tail -1 || fail=1
		pkill -f '^python3 -B server.py 8125' || true
	fi
else
	echo "BỎ QUA giao diện: không có playwright"
fi
exit $fail
