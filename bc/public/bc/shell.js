import * as router from './lib/router.js';
import * as api from './lib/api.js';
import { escapeHtml, daysBetween, todayISO } from './lib/format.js';
import { showToast } from './components/toast.js';
import { showModal, closeModal } from './components/modal.js';

// Dấu vết build — PHẢI khớp SHELL_BUILD trong www/bc.py. Gõ `BC.build` trong Console.
const BUILD = 'bc-p2-r3';
const CTX = window.BC_CONTEXT || {};
if (!window.BC_CONTEXT) console.error('[BC] window.BC_CONTEXT missing — kiểm tra www/bc.html');
console.log(`[BC] shell build=${BUILD} · assetVersion=${CTX.assetVersion || '?'}`);

// ─── Views: 1 file = 1 route, code-split + cache-bust theo assetVersion ─────
const ASSET_V = encodeURIComponent(CTX.assetVersion || '');
const withV = (p) => (ASSET_V ? `${p}?v=${ASSET_V}` : p);
const VIEW_MODULES = {
    '/tong-quan': () => import(withV('./views/tong-quan.js')),
    '/ngay': () => import(withV('./views/ngay.js')),
    '/thang': () => import(withV('./views/thang.js')),
    '/tet': () => import(withV('./views/tet.js')),
    '/tinh-thanh': () => import(withV('./views/tinh-thanh.js')),
    '/san-pham': () => import(withV('./views/san-pham.js')),
    '/sx-tet': () => import(withV('./views/sx-tet.js')),
};

// Nhóm điều hướng — mở sẵn chỗ cho module sau (Kho, Công nợ, Nhân sự, ATTP).
const NAV_GROUPS = [
    { title: 'Kinh doanh', items: [
        { route: '/tong-quan', label: 'Tổng quan', icon: 'fa-chart-pie' },
        { route: '/ngay', label: 'Theo ngày', icon: 'fa-calendar-day' },
        { route: '/thang', label: 'Theo tháng', icon: 'fa-chart-column' },
        { route: '/tet', label: 'Hàng Tết', icon: 'fa-gift' },
        { route: '/tinh-thanh', label: 'Tỉnh thành', icon: 'fa-map-location-dot' },
        { route: '/san-pham', label: 'Sản phẩm', icon: 'fa-box' },
    ] },
    { title: 'Sản xuất', items: [
        { route: '/sx-tet', label: 'SX Hàng Tết', icon: 'fa-industry' },
    ] },
    { title: 'Kho', items: [] },
    { title: 'Công nợ', items: [] },
    { title: 'Nhân sự', items: [] },
    { title: 'ATTP', items: [] },
];
const ALL_ITEMS = NAV_GROUPS.flatMap((g) => g.items).filter((it) => VIEW_MODULES[it.route]);
const TITLES = Object.fromEntries(ALL_ITEMS.map((it) => [it.route, it.label]));
const BOTTOM = ['/tong-quan', '/ngay', '/tet', '/sx-tet'].filter((r) => VIEW_MODULES[r]);

// ─── Header: badge năm TC + đếm ngược Tết ──────────────────────────────────
function paintHeader() {
    const fy = document.getElementById('bc-fy-badge');
    if (fy) fy.textContent = CTX.fy ? `NTC ${CTX.fy.label}` : '';
    const tc = document.getElementById('bc-tet-count');
    if (tc) {
        const next = CTX.tet?.nextDate;
        const n = next ? daysBetween(todayISO(), next) : null;
        const wide = window.innerWidth >= 900;
        tc.textContent = n === null ? '' : (n === 0 ? '🧧 Mùng 1 Tết' : (wide ? `🧧 Tết còn ${n} ngày` : `🧧 ${n} ngày`));
        tc.hidden = n === null;
        if (next) tc.title = `Mùng 1 Tết: ${next}`;
    }
}

function setStatus(text) {
    const el = document.getElementById('bc-header-status');
    if (el) el.textContent = text;
}

// ─── Điều hướng: sidebar (desktop) + bottom-nav 5 ô (mobile) + sheet "Thêm" ─
function buildNav() {
    const side = document.getElementById('bc-sidebar');
    if (side) {
        side.innerHTML = NAV_GROUPS.map((g) => {
            const items = g.items.filter((it) => VIEW_MODULES[it.route]);
            return `<div class="bc-side-group"><div class="bc-side-title">${escapeHtml(g.title)}</div>
                ${items.length ? items.map((it) => `<a class="bc-side-link" href="#${it.route}" data-route="${it.route}">
                    <i class="fas ${it.icon}"></i>${escapeHtml(it.label)}</a>`).join('')
                : '<div class="bc-side-soon"><span>Sắp có</span><span>⏳</span></div>'}</div>`;
        }).join('');
    }
    const bottom = document.getElementById('bc-bottom-nav');
    if (bottom) {
        bottom.innerHTML = BOTTOM.map((r) => {
            const it = ALL_ITEMS.find((x) => x.route === r);
            return `<a href="#${r}" class="bc-nav-item" data-route="${r}"><i class="fas ${it.icon}"></i><span>${escapeHtml(it.label)}</span></a>`;
        }).join('') + '<button type="button" class="bc-nav-item" id="bc-nav-more" data-route="__more"><i class="fas fa-bars"></i><span>Thêm</span></button>';
        bottom.style.gridTemplateColumns = `repeat(${BOTTOM.length + 1}, 1fr)`;
        document.getElementById('bc-nav-more').addEventListener('click', openMoreSheet);
    }
}

function openMoreSheet() {
    const body = NAV_GROUPS.map((g) => {
        const items = g.items.filter((it) => VIEW_MODULES[it.route]);
        return `<div class="bc-menu-group-title">${escapeHtml(g.title)}</div>
            <div class="bc-menu-grid">${items.length ? items.map((it) => `<a class="bc-menu-tile" href="#${it.route}">
                <i class="fas ${it.icon}"></i>${escapeHtml(it.label)}</a>`).join('')
            : '<div class="bc-menu-tile bc-disabled"><i class="fas fa-hourglass-half"></i>Sắp có</div>'}</div>`;
    }).join('');
    const el = showModal({ title: 'Tất cả báo cáo', body });
    el?.addEventListener('click', (e) => { if (e.target.closest('a')) closeModal(); });
}

function highlight(path) {
    const inBottom = BOTTOM.includes(path);
    document.querySelectorAll('[data-route]').forEach((a) => {
        const on = a.dataset.route === path || (a.dataset.route === '__more' && !inBottom);
        a.classList.toggle('bc-active', on);
    });
}

// ─── Render route ──────────────────────────────────────────────────────────
let renderSeq = 0;
async function renderRoute(route, query) {
    const seq = ++renderSeq;
    const view = document.getElementById('bc-view');
    view.innerHTML = '<div class="bc-skeleton" style="height:120px;margin-bottom:12px"></div><div class="bc-skeleton" style="height:260px"></div>';
    document.getElementById('bc-header-title').textContent = TITLES[route] || 'Báo cáo';
    document.title = `${TITLES[route] || 'Báo cáo'} · BC`;
    highlight(route);
    setStatus('Đang tải…');
    const t0 = performance.now();
    try {
        const mod = await VIEW_MODULES[route]();
        if (typeof mod.render !== 'function') throw new Error(`View ${route} thiếu render()`);
        await mod.render({ container: view, query, isCurrent: () => seq === renderSeq });
        if (seq === renderSeq) setStatus(`Hoàn thành – ${((performance.now() - t0) / 1000).toFixed(2)} s`);
    } catch (err) {
        console.error(err);
        if (seq !== renderSeq) return;
        setStatus('Lỗi tải dữ liệu');
        view.innerHTML = `<div class="bc-empty"><div class="bc-empty-icon">⚠️</div>
            <div class="bc-empty-title">Lỗi tải trang</div><div class="bc-text-sm">${escapeHtml(err.message)}</div></div>`;
        showToast(err.message, 'error');
    } finally {
        if (seq === renderSeq) api.setRefresh(false);
    }
}

Object.keys(VIEW_MODULES).forEach((r) => router.add(r, ({ query }) => renderRoute(r, query)));
router.add('/', () => router.navigate('/tong-quan', true));

// ─── Làm mới: tải lại mốc thời gian + view hiện tại với refresh=1 ──────────
document.getElementById('bc-btn-refresh')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.classList.add('bc-spin');
    api.setRefresh(true);
    try {
        const meta = await api.common.contextMeta();
        if (meta) { Object.assign(CTX, meta); paintHeader(); }
        await router.reload();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.classList.remove('bc-spin');
        api.setRefresh(false);
    }
});

// ─── Tài khoản ─────────────────────────────────────────────────────────────
(function setupAccount() {
    const btn = document.getElementById('bc-btn-account');
    if (!btn) return;
    const menu = document.createElement('div');
    menu.className = 'bc-acct-menu';
    menu.hidden = true;
    menu.innerHTML = `<div class="bc-acct-name">${escapeHtml(CTX.fullName || CTX.user || '')}</div>
        <div class="bc-acct-sub">${escapeHtml(CTX.user || '')}</div>
        ${CTX.isSysManager ? '<a class="bc-acct-link" href="/app/bc-settings" target="_blank" rel="noopener"><i class="fas fa-gear"></i> BC Settings</a>' : ''}
        <button type="button" class="bc-acct-logout"><i class="fas fa-right-from-bracket"></i> Đăng xuất</button>`;
    document.body.appendChild(menu);
    btn.addEventListener('click', (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; });
    document.addEventListener('click', (e) => { if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true; });
    menu.querySelector('.bc-acct-logout').addEventListener('click', () => { location.href = '/api/method/logout'; });
})();

paintHeader();
buildNav();
router.start();
window.BC = { router, api, showToast, build: BUILD };
