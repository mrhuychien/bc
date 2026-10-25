// Cầu nối số liệu sống cho sơ đồ xưởng 3D (nhúng trong /bc #/thoi-gian-thuc). Không sửa lõi 3D:
// dùng window.__RVHG (scene, camera, renderer, rooms, select) do app.js công bố.
//
// - Báo danh sách khu (id, tên, nhóm) cho SPA cha → cha dựng số liệu theo từng khu, gửi lại
//   bằng postMessage {type:'bc-live', zones:{id: info}, ticker, stamp} (cùng origin).
// - Mặc định KHÔNG vẽ khung số liệu đè lên sơ đồ: chỉ chấm sáng nhỏ + vòng sáng ở khu đang hoạt
//   động. Bấm vào khu (sàn, máy) hoặc chấm sáng → card chi tiết của mô hình hiện thêm khối
//   "Số liệu trực tiếp" của khu đó. Nút "Số liệu" trên thanh điều khiển bật/tắt khung nổi.
// - Mọi chuỗi từ SPA được gắn bằng textContent (không innerHTML) — trừ dòng tin chạy (ticker)
//   là HTML đã escape ở SPA.

import * as THREE from 'three';

const COLORS = { hot: '#f59e0b', ok: '#10b981', warn: '#ef4444', idle: '#94a3b8' };
const S = { zones: {}, stamp: '', pins: [], rings: [], labels: [], showLabels: false, ticker: [], tIdx: 0, got: false };
const $ = (id) => document.getElementById(id);

function waitScene() {
    return new Promise((resolve) => {
        const tick = () => (window.__RVHG?.scene && window.__RVHG?.renderer ? resolve(window.__RVHG) : setTimeout(tick, 120));
        tick();
    });
}

// ─── Đồ hoạ: chấm sáng, vòng sáng, khung nổi (khi bật "Số liệu") ─────────────
function canvasSprite(draw, w, h, scale, order) {
    const can = document.createElement('canvas');
    can.width = w; can.height = h;
    draw(can.getContext('2d'));
    const tex = new THREE.CanvasTexture(can);
    tex.colorSpace = THREE.SRGBColorSpace;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    sp.scale.set(scale, scale * h / w, 1);
    sp.renderOrder = order;
    return sp;
}

function pinSprite(level) {
    const c = COLORS[level] || COLORS.hot;
    return canvasSprite((ctx) => {
        ctx.fillStyle = c; ctx.globalAlpha = 0.28;
        ctx.beginPath(); ctx.arc(64, 64, 60, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        ctx.beginPath(); ctx.arc(64, 64, 34, 0, Math.PI * 2); ctx.fill();
        ctx.lineWidth = 6; ctx.strokeStyle = '#ffffff'; ctx.stroke();
        ctx.fillStyle = '#ffffff';
        ctx.beginPath(); ctx.arc(64, 64, 12, 0, Math.PI * 2); ctx.fill();
    }, 128, 128, 3.4, 31);
}

function labelSprite(title, value, level) {
    const c = COLORS[level] || COLORS.hot;
    return canvasSprite((ctx) => {
        ctx.fillStyle = 'rgba(16,43,56,.95)';
        ctx.beginPath(); ctx.roundRect(4, 4, 504, 142, 18); ctx.fill();
        ctx.lineWidth = 6; ctx.strokeStyle = c; ctx.stroke();
        ctx.fillStyle = c; ctx.beginPath(); ctx.arc(40, 46, 12, 0, Math.PI * 2); ctx.fill();
        ctx.textBaseline = 'middle';
        ctx.fillStyle = '#cfe3e8'; ctx.font = '600 32px Arial'; ctx.textAlign = 'left';
        ctx.fillText(String(title || ''), 66, 47, 430);
        ctx.fillStyle = '#ffffff'; ctx.font = '800 48px Arial'; ctx.textAlign = 'center';
        ctx.fillText(String(value || ''), 256, 106, 480);
    }, 512, 150, 25, 30);
}

function ringMesh(room, level) {
    const r = Math.max(2.5, Math.min(room.w, room.d) * 0.42);
    const m = new THREE.MeshBasicMaterial({ color: COLORS[level] || COLORS.hot, transparent: true, opacity: 0.5,
        side: THREE.DoubleSide, depthWrite: false, toneMapped: false });
    const mesh = new THREE.Mesh(new THREE.RingGeometry(r * 0.82, r, 48), m);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(room.x, 0.45, room.z);
    mesh.renderOrder = 15;
    return mesh;
}

function dispose(scene, list) {
    for (const o of list) {
        scene.remove(o);
        o.material.map?.dispose();
        o.material.dispose();
        if (!o.isSprite) o.geometry?.dispose();
    }
    list.length = 0;
}

function rebuildMarkers(api) {
    const { scene, rooms } = api;
    dispose(scene, S.pins); dispose(scene, S.rings); dispose(scene, S.labels);
    for (const [id, info] of Object.entries(S.zones)) {
        if (!info?.pin || !info.level || info.level === 'idle') continue;
        const room = rooms.find((r) => r.id === id);
        if (!room) continue;
        const pin = pinSprite(info.level);
        pin.position.set(room.x, 4.2, room.z);
        pin.userData.bcRoom = room;
        scene.add(pin); S.pins.push(pin);
        if (info.level === 'hot' || info.level === 'warn') { const rg = ringMesh(room, info.level); scene.add(rg); S.rings.push(rg); }
        if (S.showLabels) {
            const lb = labelSprite(info.title || room.title, info.headline, info.level);
            lb.position.set(room.x, 12 + (Number(info.lift) || 0), room.z);
            lb.userData.bcRoom = room;
            scene.add(lb); S.labels.push(lb);
        }
    }
}

// ─── Card chi tiết: khối "Số liệu trực tiếp" của khu đang chọn ──────────────
function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
}

function renderPanel(api) {
    const card = $('selection-card');
    if (!card) return;
    card.querySelector('#bc-live-panel')?.remove();
    const sel = api.selected;
    const room = sel?.room ?? sel;
    const info = room && S.zones[room.id];
    card.classList.toggle('bc-has-live', !!info);
    if (!info) return;
    const panel = el('div'); panel.id = 'bc-live-panel';
    const head = el('div', 'bc-lp-head');
    head.append(el('span', 'bc-live-dot'), el('span', 'bc-lp-head-text', info.scope || 'Số liệu trực tiếp'), el('span', 'bc-lp-time', S.stamp));
    panel.append(head);
    if (info.tiles?.length) {
        const grid = el('div', 'bc-lp-tiles');
        for (const t of info.tiles) {
            const tile = el('div', 'bc-lp-tile' + (t.tone ? ` bc-lp-${t.tone}` : ''));
            tile.append(el('span', 'bc-lp-label', t.label), el('b', 'bc-lp-value', t.value));
            if (t.sub) tile.append(el('small', 'bc-lp-sub', t.sub));
            grid.append(tile);
        }
        panel.append(grid);
    }
    for (const list of info.lists || []) {
        const box = el('div', 'bc-lp-list');
        box.append(el('div', 'bc-lp-list-title', list.title));
        if (!list.rows?.length) box.append(el('div', 'bc-lp-empty', list.empty || 'Chưa có dữ liệu'));
        else {
            const ol = el('ol');
            for (const [name, value, tone] of list.rows) {
                const li = el('li', tone ? `bc-lp-${tone}` : '');
                const nm = el('span', '', name);
                nm.title = String(name);
                li.append(nm, el('b', '', value));
                ol.append(li);
            }
            box.append(ol);
        }
        panel.append(box);
    }
    if (info.note) panel.append(el('div', 'bc-lp-note', info.note));
    const desc = $('selection-description');
    (desc?.parentNode === card ? desc : card.lastElementChild).after(panel);
}

// ─── Chạm vào chấm sáng / khung nổi → chọn đúng khu (raycast sprite) ─────────
function bindPinPicking(api) {
    const canvas = api.renderer.domElement;
    const ray = new THREE.Raycaster();
    const p = new THREE.Vector2();
    let down = null;
    canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
    // Đăng ký SAU app.js → chạy sau bộ chọn sàn/máy của mô hình, nên chạm trúng chấm sẽ thắng.
    canvas.addEventListener('pointerup', (e) => {
        if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6 || performance.now() - down.t > 700) return;
        const targets = [...S.pins, ...S.labels];
        if (!targets.length) return;
        const r = canvas.getBoundingClientRect();
        p.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
        ray.setFromCamera(p, api.camera);
        const hit = ray.intersectObjects(targets, false)[0];
        if (hit?.object.userData.bcRoom) api.select(hit.object.userData.bcRoom);
    });
}

// ─── Nút "Số liệu" (bật/tắt khung nổi) + gợi ý chạm ─────────────────────────
function addControls(api) {
    const bar = $('view-controls');
    if (bar && !$('bc-labels-toggle')) {
        const b = el('button');
        b.id = 'bc-labels-toggle';
        b.type = 'button';
        b.title = 'Bật/tắt khung số liệu nổi trên sơ đồ';
        b.setAttribute('aria-pressed', 'false');
        b.append(el('span', '', '▦'), el('span', 'hide-small', 'Số liệu'));
        b.addEventListener('click', () => {
            S.showLabels = !S.showLabels;
            b.setAttribute('aria-pressed', String(S.showLabels));
            b.classList.toggle('active', S.showLabels);
            rebuildMarkers(api);
        });
        bar.append(b);
    }
    const hint = el('div', '', 'Chạm vào một khu vực (hoặc chấm sáng) để xem số liệu');
    hint.id = 'bc-tap-hint';
    $('workspace')?.append(hint);
    setTimeout(() => hint.classList.add('bc-gone'), 9000);
}

function rotateTicker() {
    const t = $('bc-live-ticker');
    if (!t) return;
    if (!S.ticker.length) { t.textContent = ''; return; }
    S.tIdx = (S.tIdx + 1) % S.ticker.length;
    t.style.opacity = '0';
    setTimeout(() => { t.innerHTML = S.ticker[S.tIdx]; t.style.opacity = '1'; }, 300);
}

// ─── Khởi động ──────────────────────────────────────────────────────────────
const api = await waitScene();
// Bỏ "khung trong khung": card chi tiết chỉ hiện khi người xem chạm vào một khu.
if (!api.selected) $('selection-card')?.setAttribute('hidden', '');
addControls(api);
bindPinPicking(api);
// Đánh dấu body khi card đang mở (điện thoại ẩn dải tin chạy để không chồng lên card).
const cardEl = $('selection-card');
if (cardEl) new MutationObserver(() => document.body.classList.toggle('bc-card-open', !cardEl.hidden))
    .observe(cardEl, { attributes: true, attributeFilter: ['hidden'] });

window.addEventListener('message', (e) => {
    if (e.origin !== location.origin || e.data?.type !== 'bc-live') return;
    S.got = true;
    S.zones = e.data.zones || {};
    S.stamp = e.data.stamp || '';
    S.ticker = e.data.ticker || [];
    rebuildMarkers(api);
    renderPanel(api);
});
// app.js phát sự kiện TRƯỚC khi ghi lại nội dung card → đợi 1 nhịp rồi mới chèn khối số liệu.
window.addEventListener('rvhg:selection', () => {
    $('bc-tap-hint')?.classList.add('bc-gone');
    setTimeout(() => renderPanel(api), 0);
});
// Chấm sáng giữ KÍCH THƯỚC CỐ ĐỊNH TRÊN MÀN HÌNH (~26px, đủ cho ngón tay) bất kể thu phóng / điện
// thoại hẹp: quy đổi px → đơn vị cảnh theo khung nhìn camera trực giao hiện tại.
const PIN_PX = 26;
(function pulse(t) {
    requestAnimationFrame(pulse);
    const k = 1 + 0.18 * Math.sin(t / 380);
    for (const r of S.rings) { r.scale.set(k, k, 1); r.material.opacity = 0.32 + 0.22 * Math.sin(t / 380 + 1); }
    if (!S.pins.length) return;
    const cam = api.camera;
    const unitsPerPx = (cam.right - cam.left) / cam.zoom / Math.max(1, api.renderer.domElement.clientWidth);
    const s = PIN_PX * unitsPerPx * (1 + 0.08 * Math.sin(t / 300));
    for (const p of S.pins) p.scale.set(s, s, 1);
})(0);
setInterval(rotateTicker, 4500);

// Bắt tay: gửi danh sách khu; chưa nhận được số liệu thì hỏi lại (tối đa ~10 lần, mỗi 1,5s).
const zonesMeta = api.rooms.map((r) => ({ id: r.id, title: r.title, group: r.group }));
let asks = 0;
(function askData() {
    if (window.parent === window || S.got || asks++ >= 10) return;
    window.parent.postMessage({ type: 'bc-3d-ready', zones: zonesMeta }, location.origin);
    setTimeout(askData, 1500);
})();
