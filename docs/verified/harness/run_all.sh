#!/usr/bin/env bash
# Chạy toàn bộ kiểm thử bc trên MariaDB (không cần bench). Cần: mariadb-server đang chạy, pip pymysql,
# DocType JSON v16 (./fetch_schema.sh). Giao diện: node + playwright (thiếu thì bỏ qua).
set -uo pipefail
cd "$(dirname "$0")"
[ -d .src/erpnext ] || ./fetch_schema.sh
python3 -B extract_cf.py >/dev/null
fail=0
for t in test_sx.py test_channel.py test_cn.py test_attp.py test_tet_source.py; do
	echo "═══ $t"; python3 -B "$t" | tail -1 || fail=1
	python3 -B "$t" >/dev/null 2>&1 || fail=1
done
echo "═══ lunar_check.mjs"; node lunar_check.mjs | tail -1 || fail=1
if node -e "require('playwright')" 2>/dev/null; then
	python3 -B seed_ui2.py >/dev/null && (python3 -B server.py 8124 > /tmp/bc-ui-server.log 2>&1 &) && sleep 1
	echo "═══ ui_check.mjs"; node ui_check.mjs http://127.0.0.1:8124 | tail -1 || fail=1
	pkill -f '^python3 -B server.py 8124' || true
else
	echo "BỎ QUA giao diện: không có playwright"
fi
exit $fail
