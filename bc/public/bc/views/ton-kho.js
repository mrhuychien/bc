// #/ton-kho — Tồn kho. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Tồn kho', message: 'Đang xây dựng' });
}
