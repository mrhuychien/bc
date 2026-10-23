// Toạ độ trung tâm hành chính 34 tỉnh/thành (sau sáp nhập 07/2025). Tên PHẢI khớp
// tên chuẩn hoá phía server (bc/api/_provinces.py). Tỉnh không có toạ độ (vd "Khác")
// chỉ hiện trong bảng, không vẽ marker.
// [VERIFY] SPEC yêu cầu chép nguyên PROVINCE_COORDS từ file dashboard cũ — file đó
// không có trong phiên build; bảng dưới lập lại theo toạ độ thủ phủ.

export const PROVINCE_COORDS = {
    'Hà Nội': [21.028, 105.854],
    'Huế': [16.463, 107.590],
    'Lai Châu': [22.396, 103.458],
    'Điện Biên': [21.386, 103.023],
    'Sơn La': [21.327, 103.914],
    'Lạng Sơn': [21.853, 106.761],
    'Quảng Ninh': [20.959, 107.042],
    'Thanh Hóa': [19.807, 105.776],
    'Nghệ An': [18.679, 105.681],
    'Hà Tĩnh': [18.342, 105.906],
    'Cao Bằng': [22.666, 106.258],
    'Tuyên Quang': [21.823, 105.214],
    'Lào Cai': [21.705, 104.875],
    'Thái Nguyên': [21.594, 105.848],
    'Phú Thọ': [21.322, 105.402],
    'Bắc Ninh': [21.273, 106.195],
    'Hưng Yên': [20.646, 106.051],
    'Hải Phòng': [20.844, 106.688],
    'Ninh Bình': [20.251, 105.975],
    'Quảng Trị': [17.468, 106.622],
    'Đà Nẵng': [16.054, 108.202],
    'Quảng Ngãi': [15.120, 108.792],
    'Gia Lai': [13.776, 109.224],
    'Khánh Hòa': [12.238, 109.197],
    'Lâm Đồng': [11.940, 108.458],
    'Đắk Lắk': [12.667, 108.038],
    'TP. Hồ Chí Minh': [10.776, 106.700],
    'Đồng Nai': [10.957, 106.843],
    'Tây Ninh': [10.536, 106.413],
    'Cần Thơ': [10.045, 105.746],
    'Vĩnh Long': [10.254, 105.972],
    'Đồng Tháp': [10.360, 106.360],
    'Cà Mau': [9.177, 105.150],
    'An Giang': [10.012, 105.081],
};

export const VN_CENTER = [16.0, 106.5];
export const VN_ZOOM = 5;
