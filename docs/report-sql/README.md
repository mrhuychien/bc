# SQL gốc của 15 Query Report

Thư mục này được điền bởi:

```bash
bench --site a.rongvanghoanggia.com execute bc.scripts.dump_report_sql.run
```

Mỗi report → 1 file `.sql` (kèm method `bc.api.*` đích). Commit các file này để
review port 1:1 (join, điều kiện kênh/tỉnh, loại trả hàng) với SQL trong `bc/api/`.
