import { escapeHtml } from '../lib/format.js';

export function emptyState({ icon = '📭', title = 'Không có dữ liệu', message = '', action = '' } = {}) {
    return `<div class="bc-empty">
        <div class="bc-empty-icon">${icon}</div>
        <div class="bc-empty-title">${escapeHtml(title)}</div>
        ${message ? `<div class="bc-text-sm">${escapeHtml(message)}</div>` : ''}
        ${action || ''}
    </div>`;
}

/** Empty-state cho lỗi API. Thiếu ngày Tết → System Manager có link mở BC Settings. */
export function errorState(err, title = 'Không tải được dữ liệu') {
    const msg = err?.message || String(err || '');
    const missingTet = /ngày Tết/i.test(msg);
    const action = missingTet && window.BC_CONTEXT?.isSysManager
        ? '<a class="bc-btn bc-btn-primary bc-mt-2" href="/app/bc-settings" target="_blank" rel="noopener"><i class="fas fa-gear"></i> Mở BC Settings</a>'
        : '';
    return emptyState({ icon: missingTet ? '🧧' : '⚠️', title: missingTet ? 'Thiếu cấu hình ngày Tết' : title, message: msg, action });
}
