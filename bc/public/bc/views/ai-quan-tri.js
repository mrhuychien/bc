// #/ai — Cấu hình AI. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Cấu hình AI', message: 'Đang xây dựng' });
}
