// Leaflet lazy-load — CHỈ nạp khi vào #/tinh-thanh (CSS + JS từ CDN, 1 lần).

const CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
const JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
let loading = null;

export function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = CSS;
        document.head.appendChild(link);
        const s = document.createElement('script');
        s.src = JS;
        s.onload = () => resolve(window.L);
        s.onerror = () => { loading = null; reject(new Error('Không tải được bản đồ Leaflet')); };
        document.head.appendChild(s);
    });
    return loading;
}
