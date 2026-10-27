// #/han-dung — Hạn dùng & tồn âm. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Hạn dùng & tồn âm', message: 'Đang xây dựng' });
}
