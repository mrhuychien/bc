// #/nhap-tp — Nhập TP & giá vốn. ĐANG XÂY.

import { emptyState } from '../components/empty-state.js';

export async function render({ container }) {
    container.innerHTML = emptyState({ icon: '🚧', title: 'Nhập TP & giá vốn', message: 'Đang xây dựng' });
}
