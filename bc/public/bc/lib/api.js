// Gọi whitelisted method bc.api.* — mọi method có _guard() phía server (quyền thật
// kiểm ở server). Dùng fetch POST /api/method (tương đương frappe.call, không bật
// hộp thoại msgprint của web template). Client KHÔNG cache: "Làm mới" bật cờ refresh
// → mọi call trong lượt render kế tiếp gửi refresh=1 để server bỏ cache.

let refreshMode = false;
export function setRefresh(on) { refreshMode = !!on; }

function serverMessage(data) {
    try {
        const msgs = JSON.parse(data._server_messages || '[]');
        const first = msgs.map((m) => { try { return JSON.parse(m).message; } catch { return m; } }).filter(Boolean)[0];
        if (first) return String(first).replace(/<[^>]+>/g, '');
    } catch { /* ignore */ }
    if (data.exception) return String(data.exception).split(':').slice(1).join(':').trim() || data.exception;
    return null;
}

export async function call(method, args = {}) {
    const body = new URLSearchParams();
    const payload = refreshMode ? { ...args, refresh: 1 } : args;
    for (const [k, v] of Object.entries(payload)) {
        if (v === undefined || v === null) continue;
        body.append(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
    }
    const res = await fetch(`/api/method/${method}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Accept': 'application/json',
            'X-Frappe-CSRF-Token': window.BC_CONTEXT?.csrfToken || window.frappe?.csrf_token || '',
        },
        body,
    });
    let data = {};
    try { data = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok) {
        const err = new Error(serverMessage(data) || `Lỗi máy chủ (${res.status})`);
        err.status = res.status;
        err.excType = data.exc_type;
        throw err;
    }
    return data.message;
}

export const kd = {
    summary:      ()             => call('bc.api.kd.get_summary'),
    channels:     ()             => call('bc.api.kd.get_channels'),
    monthly:      ()             => call('bc.api.kd.get_monthly'),
    daily:        (year, month)  => call('bc.api.kd.get_daily', { year, month }),
    orders:       (date)         => call('bc.api.kd.get_orders', { date }),
    provinces:    ()             => call('bc.api.kd.get_provinces'),
    itemGroups:   ()             => call('bc.api.kd.get_item_groups'),
    topCustomers: (limit = 8)    => call('bc.api.kd.get_top_customers', { limit }),
    topProducts:  (group = 'all') => call('bc.api.kd.get_top_products', { group }),
};

export const tet = {
    nppGrowth: () => call('bc.api.tet.get_npp_growth'),
    nppDetail: () => call('bc.api.tet.get_npp_detail'),
    mtDetail:  () => call('bc.api.tet.get_mt_detail'),
    items:     () => call('bc.api.tet.get_items'),
};

export const sx = {
    items:        (from_date, to_date) => call('bc.api.sx.get_items', { from_date, to_date }),
    dailySummary: (year, month)        => call('bc.api.sx.get_daily_summary', { year, month }),
    dailyDetail:  (date)               => call('bc.api.sx.get_daily_detail', { date }),
};

// Báo cáo sản xuất: số hộp QC ghi theo ngày ở phần Ghi hộp của app sx (refresh = 1 → máy chủ bỏ cache).
export const sxHop = {
    overview: (thang, refresh) => call('bc.api.sx_hop.get_overview', { thang, refresh: refresh ? 1 : undefined }),
    // since = meta.generated_at của overview đang hiện: bản cache của ngày cũ hơn thì máy chủ tính lại.
    day:      (date, refresh, since) => call('bc.api.sx_hop.get_day', { date, refresh: refresh ? 1 : undefined, since: since || undefined }),
};

export const cn = {
    receivables: () => call('bc.api.cn.get_receivables'),
    payables:    () => call('bc.api.cn.get_payables'),
};

export const attp = {
    overview: ()      => call('bc.api.attp.get_overview'),
    report:   (thang) => call('bc.api.attp.get_report', { thang }),
};

export const vc = {
    overview: (thang) => call('bc.api.vc.get_overview', { thang }),
};

export const ns = {
    overview: () => call('bc.api.ns.get_overview'),
};

export const kho = {
    ton:    ()      => call('bc.api.kho_ton.get_overview'),
    trend:  ()      => call('bc.api.kho_ton.get_trend'),
    han:    ()      => call('bc.api.kho_han.get_overview'),
    kiemKe: (thang) => call('bc.api.kho_kk.get_overview', { thang }),
    nhapTp: (thang) => call('bc.api.kho_nhap.get_overview', { thang }),
};

export const ai = {
    feed:      (closed)                              => call('bc.api.ai.get_feed', { closed: closed ? 1 : undefined }),
    badge:     ()                                    => call('bc.api.ai.get_badge'),
    admin:     ()                                    => call('bc.api.ai.get_admin'),
    runNow:    ()                                    => call('bc.api.ai.run_now'),
    runBrief:  (kind)                                => call('bc.api.ai.run_brief', { kind }),
    setStatus: (insight, status, mute_days, note)    => call('bc.api.ai.set_status', { insight, status, mute_days, note }),
    setRule:   (rule_key, disabled, threshold, threshold_red) => call('bc.api.ai.set_rule', { rule_key, disabled, threshold, threshold_red }),
    test:      (provider)                            => call('bc.api.ai.test_connection', { provider }),
    // Hỏi đáp (P3): ask là POST có lời từ chối (417) — lịch sử là ≤ 3 lượt {q, a} của phiên trình duyệt (gửi JSON)
    qa:        ()                                    => call('bc.api.ai.get_qa'),
    ask:       (question, history)                   => call('bc.api.ai.ask', { question, history }),
    answer:    (id)                                  => call('bc.api.ai.get_answer', { id }),
};

export const common = {
    contextMeta: () => call('bc.api.common.get_context_meta'),
};

export const share = {
    list:          ()                                  => call('bc.api.share.list_leaders'),
    create:        (full_name, mobile, email, label)  => call('bc.api.share.create_leader', { full_name, mobile, email, label }),
    grantExisting: (user, label)                       => call('bc.api.share.grant_existing', { user, label }),
    issue:         (user, label)                       => call('bc.api.share.issue_link', { user, label }),
    revoke:        (link)                              => call('bc.api.share.revoke_link', { link }),
    setEnabled:    (user, enabled)                     => call('bc.api.share.set_enabled', { user, enabled: enabled ? 1 : 0 }),
};

export const sections = {
    get: ()               => call('bc.api.sections.get_hidden'),
    set: (keys, hidden)   => call('bc.api.sections.set_hidden', { sections: keys, hidden: hidden ? 1 : 0 }),
};

export const hidden = {
    list:   ()                 => call('bc.api.hidden.list_hidden'),
    search: (q)                => call('bc.api.hidden.search_items', { q }),
    hide:   (item_code, note)  => call('bc.api.hidden.hide_item', { item_code, note }),
    unhide: (item_code)        => call('bc.api.hidden.unhide_item', { item_code }),
};
