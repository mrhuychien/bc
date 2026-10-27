// #/kiem-ke — Kiểm kê & điều chỉnh. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Kiểm kê & điều chỉnh', message: 'Đang xây dựng' });
}
