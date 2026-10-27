// Âm lịch Việt Nam — thuật toán Hồ Ngọc Đức (múi giờ +7). Một bản duy nhất dùng
// chung cho lịch KD và SX (gộp 2 bản cũ).

const TZ = 7;
const INT = Math.floor;
const PI = Math.PI;

function jdFromDate(dd, mm, yy) {
    const a = INT((14 - mm) / 12);
    const y = yy + 4800 - a;
    const m = mm + 12 * a - 3;
    let jd = dd + INT((153 * m + 2) / 5) + 365 * y + INT(y / 4) - INT(y / 100) + INT(y / 400) - 32045;
    if (jd < 2299161) jd = dd + INT((153 * m + 2) / 5) + 365 * y + INT(y / 4) - 32083;
    return jd;
}

function newMoonDay(k) {
    const T = k / 1236.85, T2 = T * T, T3 = T2 * T, dr = PI / 180;
    let Jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * T2 - 0.000000155 * T3;
    Jd1 += 0.00033 * Math.sin((166.56 + 132.87 * T - 0.009173 * T2) * dr);
    const M = 359.2242 + 29.10535608 * k - 0.0000333 * T2 - 0.00000347 * T3;
    const Mpr = 306.0253 + 385.81691806 * k + 0.0107306 * T2 + 0.00001236 * T3;
    const F = 21.2964 + 390.67050646 * k - 0.0016528 * T2 - 0.00000239 * T3;
    let C1 = (0.1734 - 0.000393 * T) * Math.sin(M * dr) + 0.0021 * Math.sin(2 * dr * M);
    C1 = C1 - 0.4068 * Math.sin(Mpr * dr) + 0.0161 * Math.sin(dr * 2 * Mpr);
    C1 = C1 - 0.0004 * Math.sin(dr * 3 * Mpr);
    C1 = C1 + 0.0104 * Math.sin(dr * 2 * F) - 0.0051 * Math.sin(dr * (M + Mpr));
    C1 = C1 - 0.0074 * Math.sin(dr * (M - Mpr)) + 0.0004 * Math.sin(dr * (2 * F + M));
    C1 = C1 - 0.0004 * Math.sin(dr * (2 * F - M)) - 0.0006 * Math.sin(dr * (2 * F + Mpr));
    C1 = C1 + 0.0010 * Math.sin(dr * (2 * F - Mpr)) + 0.0005 * Math.sin(dr * (2 * Mpr + M));
    const deltat = T < -11
        ? 0.001 + 0.000839 * T + 0.0002261 * T2 - 0.00000845 * T3 - 0.000000081 * T * T3
        : -0.000278 + 0.000265 * T + 0.000262 * T2;
    return INT(Jd1 + C1 - deltat + 0.5 + TZ / 24);
}

function sunLongitude(jdn) {
    const T = (jdn - 2451545.5 - TZ / 24) / 36525, T2 = T * T, dr = PI / 180;
    const M = 357.52910 + 35999.05030 * T - 0.0001559 * T2 - 0.00000048 * T * T2;
    const L0 = 280.46645 + 36000.76983 * T + 0.0003032 * T2;
    let DL = (1.914600 - 0.004817 * T - 0.000014 * T2) * Math.sin(dr * M);
    DL += (0.019993 - 0.000101 * T) * Math.sin(dr * 2 * M) + 0.000290 * Math.sin(dr * 3 * M);
    let L = (L0 + DL) * dr;
    L -= PI * 2 * INT(L / (PI * 2));
    return INT(L / PI * 6);
}

function lunarMonth11(yy) {
    const off = jdFromDate(31, 12, yy) - 2415021;
    const k = INT(off / 29.530588853);
    let nm = newMoonDay(k);
    if (sunLongitude(nm) >= 9) nm = newMoonDay(k - 1);
    return nm;
}

function leapMonthOffset(a11) {
    const k = INT((a11 - 2415021.076998695) / 29.530588853 + 0.5);
    let last, i = 1;
    let arc = sunLongitude(newMoonDay(k + i));
    do {
        last = arc;
        i++;
        arc = sunLongitude(newMoonDay(k + i));
    } while (arc !== last && i < 14);
    return i - 1;
}

const _memo = new Map();

/** Dương → âm: { day, month, year, leap }. */
export function solarToLunar(dd, mm, yy) {
    const key = yy * 10000 + mm * 100 + dd;
    if (_memo.has(key)) return _memo.get(key);
    const dayNumber = jdFromDate(dd, mm, yy);
    const k = INT((dayNumber - 2415021.076998695) / 29.530588853);
    let monthStart = newMoonDay(k + 1);
    if (monthStart > dayNumber) monthStart = newMoonDay(k);
    let a11 = lunarMonth11(yy), b11 = a11, lunarYear;
    if (a11 >= monthStart) {
        lunarYear = yy;
        a11 = lunarMonth11(yy - 1);
    } else {
        lunarYear = yy + 1;
        b11 = lunarMonth11(yy + 1);
    }
    const lunarDay = dayNumber - monthStart + 1;
    const diff = INT((monthStart - a11) / 29);
    let leap = 0, lunarMonth = diff + 11;
    if (b11 - a11 > 365) {
        const leapDiff = leapMonthOffset(a11);
        if (diff >= leapDiff) {
            lunarMonth = diff + 10;
            if (diff === leapDiff) leap = 1;
        }
    }
    if (lunarMonth > 12) lunarMonth -= 12;
    if (lunarMonth >= 11 && diff < 4) lunarYear -= 1;
    const out = { day: lunarDay, month: lunarMonth, year: lunarYear, leap };
    _memo.set(key, out);
    return out;
}

/** Nhãn ngắn cho ô lịch: "1/1" ở mùng 1 hoặc ngày đầu ô; còn lại chỉ ngày. */
export function lunarLabel(dd, mm, yy, forceMonth = false) {
    const l = solarToLunar(dd, mm, yy);
    return (l.day === 1 || forceMonth) ? `${l.day}/${l.month}${l.leap ? 'N' : ''}` : String(l.day);
}

/** Mùng 1–3 Tết âm lịch? */
export function isTetHoliday(dd, mm, yy) {
    const l = solarToLunar(dd, mm, yy);
    return l.month === 1 && !l.leap && l.day <= 3;
}

/** Mùng 1–3 Tết theo BC Settings (nguồn duy nhất, BC_CONTEXT.tetDates); năm chưa khai → thuật toán âm lịch.
 * Tết luôn rơi 21/01–20/02 nên mùng 1–3 không vắt qua năm dương — tra theo `yy` là đủ. */
export function isTetDay(dd, mm, yy, tetDates = window.BC_CONTEXT?.tetDates) {
    const t = tetDates?.[String(yy)];
    if (!t) return isTetHoliday(dd, mm, yy);
    const [ty, tm, td] = t.split('-').map(Number);
    const diff = (Date.UTC(yy, mm - 1, dd) - Date.UTC(ty, tm - 1, td)) / 86400000;
    return diff >= 0 && diff <= 2;
}
