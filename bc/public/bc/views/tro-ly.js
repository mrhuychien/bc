// #/tro-ly — Trợ lý AI. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Trợ lý AI', message: 'Đang xây dựng' });
}
