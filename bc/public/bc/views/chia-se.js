// #/chia-se — Chia sẻ báo cáo cho lãnh đạo (CHỈ System Manager; server guard mọi method).
// Tạo tài khoản chỉ-xem + cấp link/QR tự đăng nhập. Lãnh đạo quét QR / bấm link là vào
// thẳng /bc và thiết bị được nhớ đăng nhập (cookie 400 ngày). Token chỉ hiện 1 LẦN lúc cấp.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtNum } from '../lib/format.js';
import { drawQr } from '../lib/qrcode.js';
import { showModal } from '../components/modal.js';
import { showToast } from '../components/toast.js';
import { skeleton } from '../components/skeleton.js';
import { emptyState, errorState } from '../components/empty-state.js';

function fmtDT(s) {
    if (!s) return '—';
    const [d, t] = String(s).split(' ');
    const [y, m, dd] = d.split('-');
    return `${dd}/${m}/${y}${t ? ' ' + t.slice(0, 5) : ''}`;
}

function leaderCard(l) {
    const links = l.links.length ? l.links.map((k) => `
        <div class="bc-share-link">
            <div style="min-width:0">
                <div class="bc-bold bc-text-sm">🔗 ${escapeHtml(k.label || 'Link đăng nhập')}</div>
                <div class="bc-muted" style="font-size:.72rem">Tạo ${fmtDT(k.created_on)} · ${k.last_login ? `vào gần nhất ${fmtDT(k.last_login)} · ${fmtNum(k.login_count)} lần` : 'chưa dùng'}</div>
            </div>
            <button type="button" class="bc-btn bc-btn-sm" data-revoke="${escapeHtml(k.link)}" title="Thu hồi link này">Thu hồi</button>
        </div>`).join('')
        : `<div class="bc-muted bc-text-sm">${l.is_admin ? 'Tài khoản quản trị — đăng nhập bằng mật khẩu, không cấp link.' : 'Chưa có link nào.'}</div>`;
    return `<div class="bc-card bc-share-card ${l.enabled ? '' : 'bc-share-off'}">
        <div class="bc-card-head">
            <div style="min-width:0">
                <div class="bc-card-title">${escapeHtml(l.full_name)} ${l.enabled ? '' : '<span class="bc-badge bc-badge-danger">Đã khoá</span>'}${l.is_admin ? ' <span class="bc-badge bc-badge-muted">Quản trị</span>' : ''}</div>
                <div class="bc-card-sub">${l.mobile_no ? `📱 ${escapeHtml(l.mobile_no)} · ` : ''}${escapeHtml(l.user)}${l.last_active ? ` · hoạt động ${fmtDT(l.last_active)}` : ''}</div>
            </div>
            ${l.is_admin ? '' : `<div class="bc-flex bc-gap-2 bc-wrap">
                ${l.enabled ? `<button type="button" class="bc-btn bc-btn-sm bc-btn-primary" data-issue="${escapeHtml(l.user)}" data-name="${escapeHtml(l.full_name)}"><i class="fas fa-qrcode"></i> Cấp link / QR</button>` : ''}
                <button type="button" class="bc-btn bc-btn-sm" data-toggle="${escapeHtml(l.user)}" data-enabled="${l.enabled}">${l.enabled ? 'Khoá' : 'Mở khoá'}</button>
            </div>`}
        </div>
        ${links}
    </div>`;
}

async function loadList() {
    fill('cs-list', skeleton(110, 3, 10));
    try {
        const res = await api.share.list();
        fill('cs-list', res.leaders.length ? res.leaders.map(leaderCard).join('')
            : emptyState({ icon: '👥', title: 'Chưa có tài khoản lãnh đạo', message: 'Tạo tài khoản ở khung phía trên.' }));
    } catch (err) {
        fill('cs-list', errorState(err));
    }
}

/** Hiện QR + link vừa cấp (token chỉ thấy 1 lần) — copy / chia sẻ / tải ảnh QR. */
async function showLink(res, name) {
    if (!res.url) { showToast(res.message || 'Đã cấp quyền xem', 'success'); return; }
    const body = showModal({
        title: `Link đăng nhập · ${name || res.user}`,
        body: `<div class="bc-share-qr-wrap">
            <div id="cs-qr" class="bc-share-qr">${skeleton(220, 1, 0)}</div>
            <div class="bc-share-url" id="cs-url">${escapeHtml(res.url)}</div>
            <div class="bc-flex bc-gap-2 bc-wrap" style="justify-content:center">
                <button type="button" class="bc-btn bc-btn-primary" id="cs-copy"><i class="fas fa-copy"></i> Sao chép link</button>
                ${navigator.share ? '<button type="button" class="bc-btn" id="cs-share"><i class="fas fa-share-nodes"></i> Gửi (Zalo…)</button>' : ''}
                <button type="button" class="bc-btn" id="cs-dl"><i class="fas fa-download"></i> Tải ảnh QR</button>
            </div>
            <div class="bc-alert bc-mt-3" style="text-align:left">
                <b>Link chỉ hiện 1 lần</b> — gửi ngay cho lãnh đạo (Zalo / tin nhắn) hoặc cho quét QR.
                Quét / bấm là vào thẳng báo cáo, điện thoại được <b>nhớ đăng nhập</b>.
                Ai có link đều xem được báo cáo → lộ thì bấm <b>Thu hồi</b>.
                Trên iPhone nên mở bằng Safari (không mở trong khung xem của Zalo).
            </div>
        </div>`,
    });
    await drawQr(body?.querySelector('#cs-qr'), res.url, 220);
    body?.querySelector('#cs-copy')?.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(res.url); showToast('Đã sao chép link', 'success'); }
        catch { window.getSelection().selectAllChildren(body.querySelector('#cs-url')); showToast('Bấm giữ để sao chép', 'info'); }
    });
    body?.querySelector('#cs-share')?.addEventListener('click', () => {
        navigator.share({ title: 'Báo cáo điều hành RVHG', text: `Link xem báo cáo cho ${name || ''}`, url: res.url }).catch(() => {});
    });
    body?.querySelector('#cs-dl')?.addEventListener('click', () => {
        const src = body.querySelector('#cs-qr canvas')?.toDataURL() || body.querySelector('#cs-qr img')?.src;
        if (!src) return;
        const a = document.createElement('a');
        a.href = src;
        a.download = `QR-bao-cao-${(name || 'lanh-dao').replace(/\s+/g, '-')}.png`;
        a.click();
    });
}

async function onCreate(e) {
    const btn = e.currentTarget;
    const v = (id) => document.getElementById(id)?.value.trim() || '';
    const name = v('cs-name');
    if (!name) { showToast('Nhập họ tên lãnh đạo', 'warning'); return; }
    btn.disabled = true;
    try {
        const res = await api.share.create(name, v('cs-mobile'), v('cs-email'), v('cs-label'));
        ['cs-name', 'cs-mobile', 'cs-email', 'cs-label'].forEach((id) => { const el = document.getElementById(id); if (el) el.value = ''; });
        await showLink(res, res.full_name);
        loadList();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function onGrant(e) {
    const btn = e.currentTarget;
    const user = document.getElementById('cs-existing')?.value.trim();
    if (!user) { showToast('Nhập email / tài khoản có sẵn', 'warning'); return; }
    btn.disabled = true;
    try {
        const res = await api.share.grantExisting(user, document.getElementById('cs-label')?.value.trim());
        await showLink(res, user);
        loadList();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function onListClick(e) {
    const issue = e.target.closest('[data-issue]');
    const revoke = e.target.closest('[data-revoke]');
    const toggle = e.target.closest('[data-toggle]');
    try {
        if (issue) {
            const label = window.prompt('Ghi chú cho link (vd: "iPhone anh Hùng", bỏ trống cũng được):', '');
            if (label === null) return;
            issue.disabled = true;
            await showLink(await api.share.issue(issue.dataset.issue, label), issue.dataset.name);
            loadList();
        } else if (revoke) {
            if (!window.confirm('Thu hồi link này? Thiết bị đang dùng link sẽ bị đăng xuất.')) return;
            await api.share.revoke(revoke.dataset.revoke);
            showToast('Đã thu hồi link', 'success');
            loadList();
        } else if (toggle) {
            const on = toggle.dataset.enabled !== '1';
            if (!on && !window.confirm('Khoá tài khoản? Mọi link của người này ngừng hoạt động.')) return;
            await api.share.setEnabled(toggle.dataset.toggle, on);
            showToast(on ? 'Đã mở khoá' : 'Đã khoá tài khoản', 'success');
            loadList();
        }
    } catch (err) {
        showToast(err.message, 'error');
        if (issue) issue.disabled = false;
    }
}

export async function render({ container }) {
    if (!window.BC_CONTEXT?.isSysManager) {
        container.innerHTML = emptyState({ icon: '🔒', title: 'Chỉ dành cho quản trị' });
        return;
    }
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Chia sẻ báo cáo cho lãnh đạo</div>
                <div class="bc-view-banner-sub">Tạo tài khoản chỉ xem · gửi link hoặc QR · quét là vào, điện thoại nhớ đăng nhập</div></div>
            <span class="bc-view-banner-badge">🔗 QR</span>
        </div>
        <div class="bc-card">
            <div class="bc-card-head"><div class="bc-card-title">➕ Tạo tài khoản lãnh đạo</div></div>
            <div class="bc-share-form">
                <label>Họ tên *<input class="bc-input" id="cs-name" placeholder="Nguyễn Văn A" autocomplete="off"></label>
                <label>Số điện thoại<input class="bc-input" id="cs-mobile" type="tel" placeholder="09xxxxxxxx" autocomplete="off"></label>
                <label>Email (tuỳ chọn)<input class="bc-input" id="cs-email" type="email" placeholder="không bắt buộc" autocomplete="off"></label>
                <label>Ghi chú link<input class="bc-input" id="cs-label" placeholder="vd: iPhone anh A" autocomplete="off"></label>
            </div>
            <button type="button" class="bc-btn bc-btn-primary bc-mt-3" id="cs-create"><i class="fas fa-user-plus"></i> Tạo tài khoản + QR</button>
            <div class="bc-note">Tài khoản chỉ xem được báo cáo /bc (không vào được ERPNext). Không cần mật khẩu — vào bằng link/QR.</div>
            <div class="bc-share-or">hoặc cấp quyền cho tài khoản có sẵn</div>
            <div class="bc-flex bc-gap-2 bc-wrap">
                <input class="bc-input bc-search" id="cs-existing" placeholder="email tài khoản ERPNext có sẵn" autocomplete="off">
                <button type="button" class="bc-btn" id="cs-grant"><i class="fas fa-user-check"></i> Cấp quyền xem</button>
            </div>
        </div>
        <div class="bc-section-title">Tài khoản được xem báo cáo</div>
        <div id="cs-list"></div>`;
    document.getElementById('cs-create').addEventListener('click', onCreate);
    document.getElementById('cs-grant').addEventListener('click', onGrant);
    document.getElementById('cs-list').addEventListener('click', onListClick);
    await loadList();
}
