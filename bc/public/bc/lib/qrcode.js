// QR code — lazy-load qrcodejs từ CDN 1 lần (chỉ màn Chia sẻ). CDN lỗi → vẫn còn link.

const SRC = 'https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js';
let loading = null;

export function loadQr() {
    if (window.QRCode) return Promise.resolve(window.QRCode);
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = SRC;
        s.onload = () => resolve(window.QRCode);
        s.onerror = () => { loading = null; reject(new Error('Không tải được thư viện QR')); };
        document.head.appendChild(s);
    });
    return loading;
}

/** Vẽ QR vào el (xoá nội dung cũ). Trả về true nếu vẽ được. */
export async function drawQr(el, text, size = 220) {
    if (!el) return false;
    try {
        const QRCode = await loadQr();
        el.innerHTML = '';
        new QRCode(el, { text, width: size, height: size, correctLevel: QRCode.CorrectLevel.M });
        return true;
    } catch (e) {
        el.innerHTML = `<div class="bc-muted bc-text-sm">${e.message}</div>`;
        return false;
    }
}
