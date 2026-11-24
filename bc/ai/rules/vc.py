# -*- coding: utf-8 -*-
"""bc.ai.rules.vc — quy tắc nhóm Vận chuyển (đặc tả §4.1). Hàm THUẦN trên gói số: không SQL, không frappe.

Nguồn đã đối chiếu code bc.api.vc.get_overview và view van-chuyen.js. Pack gọi không tham số → tháng này cắt ở hôm
nay. Cả trang `available: False` khi chưa cài vanchuyen; từng khối giao / cuoc / su_co / xe có thể
`{available: False}` (thiếu bảng / cột, hoặc lỗi — safe_block) → `sources` khai sâu tới khối:
- giao.cho_qua_han{qua_n, so_ngay (= 3), rows[{hinh_thuc, cho, qua_n}] xếp qua_n giảm dần} — ảnh chụp hôm nay;
- giao.xep{chua_xep, mot_phan, da_xep} | None (thiếu bảng chuyến) — ảnh chụp hôm nay, chỉ đơn Tự vận chuyển;
- giao.lan_dau{so_don, da_giao, khach_hen, hoan, ty_le (đã ×100, None khi 0 đơn)} | None — theo tháng;
- su_co{mo_qua_n, so_ngay (= 7), …}; xe{can_xu_ly[{xe (biển số), qua_han (bool), viec[…]}] quá hạn trước};
- cuoc{an, tra_bat_thuong, tra_chuyen_huy, tra_chuyen_huy_tien, sua_tay, …}: `an: True` (tháng < K lái xe) thì
  mọi số TIỀN đã None — quy tắc không bao giờ nêu tiền cước khi `an`.
- van-chuyen.overview_truoc = get_overview(thang=<tháng trước>) — CHỈ vc.cuoc_canh_bao đọc (cộng cảnh báo trả cước
  của tháng trước để tín hiệu không tự đóng ngày 1); KHÔNG khai trong `sources` (thiếu / hỏng → chạy trên tháng này,
  riêng ca dễ đóng nhầm thì NotRunnable); pipeline không gửi khối này cho mô hình (registry.NO_SEND).

Luật: giá trị None / thiếu / không phải số → không tín hiệu, không ném lỗi. Mọi số / tên từ dữ liệu trong lời là
placeholder; số tự tính trong `tinh`. Không tên lái xe / khách (payload vốn không có).
"""

from __future__ import annotations

import math

from bc.ai.registry import NotRunnable, ph, resolve, rule, source_ok

O = "van-chuyen.overview"
G, CUOC, SC, XE = f"{O}.giao", f"{O}.cuoc", f"{O}.su_co", f"{O}.xe"
CUOC_TRUOC = "van-chuyen.overview_truoc.cuoc"     # tháng trước — chỉ vc.cuoc_canh_bao đọc

LAN_DAU_TOI_THIEU = 10   # vc.giao_lan_dau: chỉ xét khi tháng có từ ngần này đơn đã chạy chuyến (tránh báo ảo đầu tháng)
NEU_XE = 3               # vc.xe_qua_han: số biển số nêu trong lời
CANH_BAO_CUOC = ("tra_bat_thuong", "tra_chuyen_huy", "sua_tay")   # đúng 3 cảnh báo màn Vận chuyển hiện
CONG_THANG_TRUOC = ("tra_bat_thuong", "tra_chuyen_huy")            # trạng thái chứng từ → cộng cả tháng trước


def _so(v):
	"""Số thật (int / float hữu hạn, không phải bool) → chính nó; còn lại → None."""
	if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
		return None
	return v


def _chu(v) -> bool:
	return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 120


def _num(pack, path):
	return _so(resolve(pack, path, None))


# ─── Giao hàng ───────────────────────────────────────────────────────────────
@rule("vc.cho_qua_han", section="van-chuyen", sources=[G], vang=0, do=10, unit="đơn", label="Đơn chờ giao quá hạn")
def cho_qua_han(pack, cfg):
	"""Đơn chờ giao quá 3 ngày: > 0 (vàng) / > 10 (đỏ)."""
	ch = f"{G}.cho_qua_han"
	muc = cfg.muc(_num(pack, f"{ch}.qua_n"))
	if not muc:
		return []
	ngay = f"quá {ph(f'{ch}.so_ngay', 'so')} ngày" if _num(pack, f"{ch}.so_ngay") is not None else "quá hạn"
	detail = "Khách chờ lâu dễ huỷ đơn hoặc phàn nàn, bộ phận vận chuyển cần ưu tiên giao ngay."
	r0 = resolve(pack, f"{ch}.rows[0]", None)
	if isinstance(r0, dict) and _chu(r0.get("hinh_thuc")) and (_so(r0.get("qua_n")) or 0) > 0:
		detail = (f"Dồn nhiều nhất ở {ph(f'{ch}.rows[0].hinh_thuc', 'chu')} với {ph(f'{ch}.rows[0].qua_n', 'so')} "
			"đơn, khách chờ lâu dễ huỷ đơn hoặc phàn nàn.")
	return [cfg.signal(muc, f"{ph(f'{ch}.qua_n', 'so')} đơn chờ giao {ngay}", detail=detail)]


@rule("vc.chua_xep_chuyen", section="van-chuyen", sources=[G], vang=0, do=10, unit="đơn",
	label="Đơn tự giao chưa xếp chuyến")
def chua_xep_chuyen(pack, cfg):
	"""Đơn Tự vận chuyển chưa giao mà chưa lên chuyến nào: > 0 (vàng) / > 10 (đỏ)."""
	x = f"{G}.xep"
	muc = cfg.muc(_num(pack, f"{x}.chua_xep"))
	if not muc:
		return []
	detail = "Đơn chưa xếp chuyến thì chưa ai đi giao, bộ phận điều phối cần xếp xe."
	if (_num(pack, f"{x}.mot_phan") or 0) > 0:
		detail = (f"Đơn chưa xếp chuyến thì chưa ai đi giao (thêm {ph(f'{x}.mot_phan', 'so')} đơn mới xếp một phần), "
			"bộ phận điều phối cần xếp xe.")
	return [cfg.signal(muc, f"{ph(f'{x}.chua_xep', 'so')} đơn tự giao chưa được xếp lên chuyến xe", detail=detail)]


@rule("vc.giao_lan_dau", section="van-chuyen", sources=[G], vang=90, do=80, unit="%", lower=True,
	label="Tỷ lệ giao được ngay lần đầu")
def giao_lan_dau(pack, cfg):
	"""Tỷ lệ đơn giao được ngay lần đầu trong tháng dưới 90% (vàng) / 80% (đỏ) — chỉ khi đủ 10 đơn."""
	ld = f"{G}.lan_dau"
	so_don = _num(pack, f"{ld}.so_don")
	if so_don is None or so_don < LAN_DAU_TOI_THIEU:
		return []
	muc = cfg.muc(_num(pack, f"{ld}.ty_le"))
	if not muc:
		return []
	detail = "Giao lại tốn thêm cước và thời gian, bộ phận vận chuyển cần xem lý do khách không nhận."
	if all(_num(pack, f"{ld}.{k}") is not None for k in ("khach_hen", "hoan")):
		detail = (f"Trong {ph(f'{ld}.so_don', 'so')} đơn đã chạy chuyến tháng này có {ph(f'{ld}.khach_hen', 'so')} "
			f"đơn khách hẹn lại và {ph(f'{ld}.hoan', 'so')} đơn hoàn, giao lại tốn thêm cước và thời gian.")
	return [cfg.signal(muc, f"Chỉ {ph(f'{ld}.ty_le', 'pct')} đơn giao được ngay lần đầu", detail=detail)]


# ─── Sự cố ───────────────────────────────────────────────────────────────────
@rule("vc.su_co_mo", section="van-chuyen", sources=[SC], vang=0, unit="sự cố", label="Sự cố vận chuyển mở lâu")
def su_co_mo(pack, cfg):
	"""Có sự cố vận chuyển mở quá 7 ngày (> 0 sự cố)."""
	muc = cfg.muc(_num(pack, f"{SC}.mo_qua_n"))
	if not muc:
		return []
	ngay = f"quá {ph(f'{SC}.so_ngay', 'so')} ngày" if _num(pack, f"{SC}.so_ngay") is not None else "lâu ngày"
	return [cfg.signal(muc, f"{ph(f'{SC}.mo_qua_n', 'so')} sự cố vận chuyển mở {ngay} chưa xử lý",
		detail="Sự cố để lâu khó đòi bồi thường và khách mất lòng tin, bộ phận vận chuyển cần chốt hướng xử lý.")]


# ─── Cước ────────────────────────────────────────────────────────────────────
@rule("vc.cuoc_canh_bao", section="van-chuyen", sources=[CUOC], vang=0, unit="chuyến",
	label="Cảnh báo trả cước xe nhà")
def cuoc_canh_bao(pack, cfg):
	"""Mỗi cảnh báo trả cước của màn (> 0 chuyến) một tín hiệu `vc.cuoc_canh_bao:<trường>`. Tháng `an` không nêu tiền.

	tra_bat_thuong / tra_chuyen_huy là TRẠNG THÁI chứng từ nhưng API đếm theo tháng giao → cộng tháng trước (nếu
	overview_truoc dùng được) để tín hiệu không tự đóng ngày 1. Tiền chuyến huỷ chỉ nêu khi KHÔNG tháng nào `an`.
	overview_truoc hỏng và tháng này không đủ báo một cảnh báo được cộng → NotRunnable (giữ tín hiệu cũ)."""
	an = resolve(pack, f"{CUOC}.an", None) is not False   # thiếu cờ → coi như đang ẩn tiền (an toàn)
	co_truoc = source_ok(pack, CUOC_TRUOC)
	an_truoc = co_truoc and resolve(pack, f"{CUOC_TRUOC}.an", None) is not False
	if not co_truoc and any(not cfg.muc(_num(pack, f"{CUOC}.{k}")) for k in CONG_THANG_TRUOC):
		raise NotRunnable("thieu-thang-truoc")
	out = []
	for k in CANH_BAO_CUOC:
		p = f"{CUOC}.{k}"
		nay = _num(pack, p)
		truoc = _num(pack, f"{CUOC_TRUOC}.{k}") if co_truoc and k in CONG_THANG_TRUOC else None
		tong = None if nay is None and truoc is None else (nay or 0) + (truoc or 0)
		muc = cfg.muc(tong)
		if not muc:
			continue
		hai = bool(truoc)             # tháng trước góp vào số
		ca = "tính cả tháng này và tháng trước, " if hai else ""
		tinh = {"so": tong}
		paths = [p]          # không trỏ overview_truoc: khối đó không gửi mô hình (NO_SEND)
		if k == "tra_bat_thuong":
			title = "{{@so|so}} chuyến ghi đã trả cước mà phiếu chi chưa duyệt"
			detail = (f"{ca}phiếu chi chưa duyệt hoặc đã huỷ thì sổ sách không khớp tiền đã trả, kế toán cần "
				"kiểm lại.")
		elif k == "tra_chuyen_huy":
			title = "{{@so|so}} chuyến đã huỷ nhưng tiền cước vẫn đã chi"
			tien_nay = _num(pack, f"{CUOC}.tra_chuyen_huy_tien")
			tien_truoc = _num(pack, f"{CUOC_TRUOC}.tra_chuyen_huy_tien") if hai else 0
			if not an and not an_truoc and tien_nay is not None and tien_truoc is not None:
				tinh["tien"] = round(tien_nay + tien_truoc, 2)
				detail = (f"{ca}tiền cước đã chi cho các chuyến này là {{{{@tien|tien}}}}, kế toán cần thu hồi hoặc "
					"huỷ phiếu chi.")
			else:
				detail = f"{ca}tiền đã chi cho chuyến không chạy, kế toán cần thu hồi hoặc huỷ phiếu chi."
		else:
			title = "{{@so|so}} chuyến có cước sửa tay trong tháng"
			detail = "Cước sửa tay không theo bảng giá, người phụ trách vận chuyển cần duyệt lại."
		detail = detail[0].upper() + detail[1:]
		out.append(cfg.signal(muc, title, detail=detail, obj=k, paths=paths, tinh=tinh))
	return out


# ─── Xe ──────────────────────────────────────────────────────────────────────
@rule("vc.xe_qua_han", section="van-chuyen", sources=[XE], vang=0, do=0, unit="xe",
	label="Xe quá hạn hoặc sắp đến hạn đăng kiểm, bảo dưỡng")
def xe_qua_han(pack, cfg):
	"""Xe đang dùng quá hạn (đỏ) / sắp đến hạn (vàng) đăng kiểm, thay dầu, bảo dưỡng → GỘP 1 tín hiệu."""
	rows = resolve(pack, f"{XE}.can_xu_ly", None)
	if not isinstance(rows, list):
		return []
	xe = [(i, r.get("qua_han") is True) for i, r in enumerate(rows) if isinstance(r, dict)]
	qua = sum(1 for _i, q in xe if q)
	sap = len(xe) - qua
	if cfg.do is not None and qua > cfg.do:
		muc = "do"
	elif cfg.vang is not None and len(xe) > cfg.vang:
		muc = "vang"
	else:
		return []
	# Biển số của nhóm đang báo: có xe quá hạn → chỉ nêu xe quá hạn; không thì xe sắp đến hạn (thứ tự gốc).
	# G2: mỗi biển số có chữ "xe" đứng trước (biển số tận cùng bằng chữ số — hai placeholder không chỉ cách dấu phẩy)
	bien = ["xe " + ph(f"{XE}.can_xu_ly[{i}].xe", "chu") for i, q in xe if q == (qua > 0)
		and _chu(rows[i].get("xe"))][:NEU_XE]
	if qua:
		title = "{{@qua_han|so}} xe quá hạn đăng kiểm, thay dầu hoặc bảo dưỡng"
		them = "thêm {{@sap_den|so}} xe sắp đến hạn" if sap else ""
		duoi = "xe quá hạn đăng kiểm chạy đường bị phạt, bộ phận vận chuyển cần đưa xe đi làm ngay."
	else:
		title = "{{@sap_den|so}} xe sắp đến hạn đăng kiểm, thay dầu hoặc bảo dưỡng"
		them, duoi = "", "bộ phận vận chuyển cần xếp lịch đưa xe đi làm trước hạn."
	dau = ", ".join(x for x in (f"Gồm {', '.join(bien)}" if bien else "", them) if x)
	detail = f"{dau}; {duoi}" if dau else duoi
	detail = detail[0].upper() + detail[1:]
	return [cfg.signal(muc, title, detail=detail, paths=[f"{XE}.can_xu_ly[{i}].qua_han" for i, _q in xe[:NEU_XE]],
		tinh={"qua_han": qua, "sap_den": sap})]
