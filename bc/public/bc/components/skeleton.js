/** Khung shimmer khi đang tải (không để màn trắng). */
export function skeleton(height = 90, count = 1, gap = 10) {
    return Array.from({ length: count },
        () => `<div class="bc-skeleton" style="height:${Number(height) || 90}px;margin-bottom:${gap}px"></div>`).join('');
}

export function skeletonGrid(n = 4, height = 110, cls = 'bc-grid-4') {
    return `<div class="bc-grid ${cls}">${Array.from({ length: n }, () => `<div class="bc-skeleton" style="height:${height}px"></div>`).join('')}</div>`;
}
