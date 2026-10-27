#!/usr/bin/env bash
# Lấy DocType JSON của ERPNext v16 + Frappe v16 (sparse, chỉ file JSON) vào .src/ cho schema.py.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .src && cd .src
[ -d erpnext ] || git clone -q --depth 1 --filter=blob:none --sparse -b version-16 https://github.com/frappe/erpnext
(cd erpnext && git sparse-checkout set --no-cone '**/doctype/*/*.json')
[ -d frappe ] || git clone -q --depth 1 --filter=blob:none --sparse -b version-16 https://github.com/frappe/frappe
(cd frappe && git sparse-checkout set --no-cone 'frappe/core/doctype/*/*.json' 'frappe/desk/doctype/*/*.json' 'frappe/website/doctype/*/*.json')
echo "schema nguồn: $(find . -path '*/doctype/*/*.json' | wc -l) file"
