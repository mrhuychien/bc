// #/tinh-thanh — bản đồ doanh số theo tỉnh (Leaflet nạp lazy CHỈ ở view này) +
// bảng tỉnh phân trang 10. Bán kính marker 6→28 theo doanh số, màu theo ngưỡng.

import * as api from '../lib/api.js';
import { fill } from '../lib/dom.js';
import { escapeHtml, fmtMoney, fmtNum, fmtPct, salesBasisNote } from '../lib/format.js';
import { loadLeaflet } from '../lib/leaflet.js';
import { PROVINCE_COORDS, VN_CENTER, VN_ZOOM } from '../lib/provinces.js';
import { dataTable } from '../components/data-table.js';
import { skeleton } from '../components/skeleton.js';
import { errorState } from '../components/empty-state.js';

const TILES = {
    map: ['https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }],
    sat: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: '© Esri' }],
};
const LEVELS = [
    [5e9, '#6d28d9', '≥ 5 tỷ'],
    [1e9, '#db2777', '1 – 5 tỷ'],
    [5e8, '#f59e0b', '500 tr – 1 tỷ'],
    [0, '#10b981', '< 500 tr'],
];
let map = null;
let tile = null;

const colorOf = (v) => LEVELS.find(([t]) => v >= t)[1];

function destroyMap() {
    if (map) { try { map.remove(); } catch { /* đã gỡ */ } }
    map = null;
    tile = null;
}

function setTile(L, kind) {
    if (tile) map.removeLayer(tile);
    tile = L.tileLayer(TILES[kind][0], TILES[kind][1]).addTo(map);
}

async function drawMap(rows) {
    const L = await loadLeaflet();
    const el = document.getElementById('tt-map');
    if (!el) return;
    destroyMap();
    map = L.map(el, { zoomControl: true, attributionControl: true }).setView(VN_CENTER, VN_ZOOM);
    setTile(L, 'map');
    const max = Math.max(...rows.map((r) => r.sales), 1);
    rows.forEach((r) => {
        const c = PROVINCE_COORDS[r.province];
        if (!c || r.sales <= 0) return;
        const radius = 6 + 22 * Math.sqrt(r.sales / max);
        L.circleMarker(c, { radius, color: '#fff', weight: 1.5, fillColor: colorOf(r.sales), fillOpacity: 0.78 })
            .bindPopup(`<b>${escapeHtml(r.province)}</b><br>${fmtNum(r.sales)} ₫<br>${fmtPct(r.pct)} tổng`)
            .bindTooltip(`${escapeHtml(r.province)}: ${fmtMoney(r.sales)}`)
            .addTo(map);
    });
    document.getElementById('tt-tools')?.addEventListener('click', (e) => {
        const b = e.target.closest('[data-tt]');
        if (!b || !map) return;
        if (b.dataset.tt === 'reset') map.setView(VN_CENTER, VN_ZOOM);
        else setTile(L, b.dataset.tt);
    });
    setTimeout(() => map && map.invalidateSize(), 50);
}

export async function render({ container, isCurrent }) {
    destroyMap();
    const fy = window.BC_CONTEXT?.fy;
    container.innerHTML = `
        <div class="bc-view-banner">
            <div><div class="bc-view-banner-title">Doanh số theo tỉnh thành</div>
                <div class="bc-view-banner-sub">Năm tài chính ${escapeHtml(fy?.label || '')} · 34 tỉnh/thành sau sáp nhập</div></div>
            <span class="bc-view-banner-badge">🗺️ Bản đồ</span>
        </div>
        <div class="bc-card">
            <div class="bc-card-head"><div class="bc-card-title">Bản đồ doanh số</div>
                <div class="bc-map-tools" id="tt-tools">
                    <button type="button" class="bc-btn bc-btn-sm" data-tt="map"><i class="fas fa-map"></i> Bản đồ</button>
                    <button type="button" class="bc-btn bc-btn-sm" data-tt="sat"><i class="fas fa-satellite"></i> Vệ tinh</button>
                    <button type="button" class="bc-btn bc-btn-sm" data-tt="reset"><i class="fas fa-crosshairs"></i> Toàn quốc</button>
                </div></div>
            <div class="bc-map" id="tt-map">${skeleton(380, 1, 0)}</div>
            <div class="bc-legend">${LEVELS.map(([, c, l]) => `<span><i style="background:${c}"></i>${l}</span>`).join('')}</div>
        </div>
        <div class="bc-card bc-mt-3"><div class="bc-card-head"><div class="bc-card-title">Bảng tỉnh</div><div class="bc-card-sub" id="tt-src"></div></div>
            <div id="tt-table">${skeleton(220)}</div></div>
        ${salesBasisNote()}`;
    let res;
    try {
        res = await api.kd.provinces();
    } catch (err) {
        fill('tt-map', errorState(err));
        fill('tt-table', '');
        return;
    }
    if (!isCurrent()) return;
    fill('tt-src', `Tổng ${fmtMoney(res.meta.total)} · nguồn tỉnh: ${escapeHtml(res.meta.source)}`);
    fill('tt-table', dataTable({
        rows: res.rows, sortKey: 'sales', emptyMessage: 'Chưa có doanh số',
        columns: [
            { key: 'province', label: 'Tỉnh / thành', align: 'left' },
            { key: 'sales', label: 'Doanh số', render: (r) => fmtNum(r.sales) },
            { key: 'pct', label: '% tổng', render: (r) => fmtPct(r.pct) },
        ],
    }));
    const mapEl = document.getElementById('tt-map');
    if (mapEl) mapEl.innerHTML = '';
    try {
        await drawMap(res.rows);
    } catch (err) {
        fill('tt-map', errorState(err, 'Không tải được bản đồ'));
    }
}
