// Danh mục màn báo cáo — MỘT nguồn cho menu (shell.js) và màn quản trị Ẩn / hiện mảng (views/an-mang.js).
// Mã mảng = route bỏ dấu "/" — PHẢI khớp bc.api._common.SECTIONS (máy chủ chặn method theo mã này).
// Nhóm có items rỗng = "Sắp có".

export const NAV_GROUPS = [
    { title: 'Điều hành', items: [
        { route: '/thoi-gian-thuc', label: 'Thời gian thực', icon: 'fa-tower-broadcast' },
    ] },
    { title: 'Kinh doanh', items: [
        { route: '/tong-quan', label: 'Tổng quan', icon: 'fa-chart-pie' },
        { route: '/ngay', label: 'Theo ngày', icon: 'fa-calendar-day' },
        { route: '/thang', label: 'Theo tháng', icon: 'fa-chart-column' },
        { route: '/tet', label: 'Hàng Tết', icon: 'fa-gift' },
        { route: '/tinh-thanh', label: 'Tỉnh thành', icon: 'fa-map-location-dot' },
        { route: '/san-pham', label: 'Sản phẩm', icon: 'fa-box' },
    ] },
    { title: 'Sản xuất', items: [
        { route: '/sx-tet', label: 'SX Hàng Tết', icon: 'fa-industry' },
    ] },
    { title: 'Kho', items: [] },
    { title: 'Vận chuyển', items: [
        { route: '/van-chuyen', label: 'Giao hàng & xe', icon: 'fa-truck-fast' },
    ] },
    { title: 'Công nợ', items: [
        { route: '/cong-no', label: 'Phải thu', icon: 'fa-hand-holding-dollar' },
        { route: '/phai-tra', label: 'Phải trả & quỹ', icon: 'fa-building-columns' },
    ] },
    { title: 'Nhân sự', items: [
        { route: '/nhan-su', label: 'Nhân sự & lương', icon: 'fa-users' },
    ] },
    { title: 'ATTP', items: [
        { route: '/attp', label: 'An toàn thực phẩm', icon: 'fa-shield-halved' },
    ] },
];

export function sectionOf(route) { return String(route || '').replace(/^\//, ''); }
