// Chart.js (+ plugin datalabels) lazy-load 1 lần từ CDN; registry destroy chart cũ.

const CHART_SRC = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js';
const DATALABELS_SRC = 'https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js';
let loading = null;

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error('Không tải được ' + src));
        document.head.appendChild(s);
    });
}

export function loadChartLib() {
    if (loading) return loading;
    loading = (async () => {
        if (!window.Chart) await loadScript(CHART_SRC);
        if (!window.ChartDataLabels) {
            try { await loadScript(DATALABELS_SRC); } catch (e) { console.warn(e); }
        }
        const Chart = window.Chart;
        if (window.ChartDataLabels) {
            Chart.register(window.ChartDataLabels);
            Chart.defaults.set('plugins.datalabels', { display: false });  // bật riêng từng chart
        }
        Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
        Chart.defaults.color = '#4b5563';
        Chart.defaults.maintainAspectRatio = false;
        return Chart;
    })().catch((e) => { loading = null; throw e; });
    return loading;
}

export function chartRegistry() {
    let list = [];
    return {
        add(c) { list.push(c); return c; },
        destroy() { list.forEach((c) => { try { c.destroy(); } catch { /* đã huỷ */ } }); list = []; },
    };
}

export const PALETTE = ['#7c3aed', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#a855f7', '#ef4444', '#14b8a6', '#6366f1', '#84cc16'];
