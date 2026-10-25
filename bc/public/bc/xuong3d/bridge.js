// Cầu nối số liệu sống: SPA cha (/bc #/thoi-gian-thuc) gửi postMessage {type:'bc-live', rooms, ticker, headline}
// → gắn bảng số liệu nổi + vòng sáng nhấp nháy lên đúng phòng của mô hình 3D (window.__RVHG do app.js
// công bố). Không sửa lõi 3D. Chỉ nhận message cùng origin.

import * as THREE from 'three';

const LIVE = { labels: [], rings: [], data: {}, tickerIdx: 0, ticker: [] };
const COLORS = { hot: '#f59e0b', ok: '#10b981', warn: '#ef4444', idle: '#64748b' };

function waitScene() {
    return new Promise((resolve) => {
        const tick = () => (window.__RVHG?.scene ? resolve(window.__RVHG) : setTimeout(tick, 120));
        tick();
    });
}

function liveLabel(lines, level) {
    const can = document.createElement('canvas');
    can.width = 512; can.height = 150;
    const ctx = can.getContext('2d');
    const color = COLORS[level] || COLORS.hot;
    ctx.fillStyle = 'rgba(16,43,56,.95)';
    ctx.beginPath(); ctx.roundRect(4, 4, 504, 142, 18); ctx.fill();
    ctx.lineWidth = 6; ctx.strokeStyle = color; ctx.stroke();
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(40, 46, 12, 0, Math.PI * 2); ctx.fill();
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#cfe3e8'; ctx.font = '600 32px Arial'; ctx.textAlign = 'left';
    ctx.fillText(String(lines[0] || ''), 66, 47, 430);
    ctx.fillStyle = '#ffffff'; ctx.font = '800 48px Arial'; ctx.textAlign = 'center';
    ctx.fillText(String(lines[1] || ''), 256, 106, 480);
    const tex = new THREE.CanvasTexture(can);
    tex.colorSpace = THREE.SRGBColorSpace;
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    sp.scale.set(25, 25 * 150 / 512, 1);
    sp.renderOrder = 30;
    return sp;
}

function ring(room, level) {
    const r = Math.max(2.5, Math.min(room.w, room.d) * 0.42);
    const geo = new THREE.RingGeometry(r * 0.82, r, 48);
    const m = new THREE.MeshBasicMaterial({ color: COLORS[level] || COLORS.hot, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false, toneMapped: false });
    const mesh = new THREE.Mesh(geo, m);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(room.x, 0.45, room.z);
    mesh.renderOrder = 15;
    return mesh;
}

function clear(scene) {
    for (const o of [...LIVE.labels, ...LIVE.rings]) {
        scene.remove(o);
        o.material.map?.dispose();
        o.material.dispose();
        o.geometry?.dispose?.();
    }
    LIVE.labels = []; LIVE.rings = [];
}

function apply(api, msg) {
    const { scene, rooms } = api;
    clear(scene);
    LIVE.data = msg.rooms || {};
    for (const [id, info] of Object.entries(LIVE.data)) {
        const room = rooms.find((r) => r.id === id);
        if (!room || !info?.lines) continue;
        const sp = liveLabel(info.lines, info.level);
        sp.position.set(room.x, 12 + (Number(info.lift) || 0), room.z);
        scene.add(sp); LIVE.labels.push(sp);
        if (info.level === 'hot' || info.level === 'warn') {
            const rg = ring(room, info.level);
            scene.add(rg); LIVE.rings.push(rg);
        }
    }
    LIVE.ticker = msg.ticker || [];
    const head = document.querySelector('.header-middle');
    if (head && msg.headline) head.innerHTML = `<span class="bc-live-dot"></span>${msg.headline}`;
    decorateSelection(api);
}

/** Phòng đang chọn có số liệu sống → thêm thẻ số vào bảng chi tiết của mô hình. */
function decorateSelection(api) {
    const sel = api.selected;
    const room = sel?.room ?? sel;
    const meta = document.getElementById('selection-meta');
    if (!meta) return;
    meta.querySelectorAll('.bc-live-meta').forEach((e) => e.remove());
    const info = room && LIVE.data[room.id];
    if (!info) return;
    (info.detail || [info.lines.join(': ')]).forEach((t) => {
        const s = document.createElement('span');
        s.className = 'bc-live-meta';
        s.textContent = t;
        meta.appendChild(s);
    });
}

function rotateTicker() {
    const el = document.getElementById('bc-live-ticker');
    if (!el) return;
    if (!LIVE.ticker.length) { el.textContent = ''; return; }
    LIVE.tickerIdx = (LIVE.tickerIdx + 1) % LIVE.ticker.length;
    el.style.opacity = '0';
    setTimeout(() => { el.innerHTML = LIVE.ticker[LIVE.tickerIdx]; el.style.opacity = '1'; }, 300);
}

const api = await waitScene();
window.addEventListener('message', (e) => {
    if (e.origin !== location.origin || e.data?.type !== 'bc-live') return;
    apply(api, e.data);
});
// app.js phát sự kiện TRƯỚC khi ghi lại #selection-meta → đợi 1 nhịp rồi mới thêm thẻ số.
window.addEventListener('rvhg:selection', () => setTimeout(() => decorateSelection(api), 0));
// Nhịp sáng cho vòng phòng đang hoạt động (độc lập với nút tạm dừng chuyển động minh hoạ).
(function pulse(t) {
    requestAnimationFrame(pulse);
    const k = 1 + 0.18 * Math.sin(t / 380);
    for (const r of LIVE.rings) { r.scale.set(k, k, 1); r.material.opacity = 0.35 + 0.25 * Math.sin(t / 380 + 1); }
})(0);
setInterval(rotateTicker, 4500);
// Bắt tay: báo sẵn sàng; chưa nhận được số liệu thì hỏi lại (tối đa ~10 lần, mỗi 1,5s).
let asks = 0;
(function askData() {
    if (window.parent === window || Object.keys(LIVE.data).length || asks++ >= 10) return;
    window.parent.postMessage({ type: 'bc-3d-ready' }, location.origin);
    setTimeout(askData, 1500);
})();
