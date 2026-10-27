// isTetDay: ngày Tết theo BC Settings (BC_CONTEXT.tetDates) đè thuật toán âm lịch. node lunar_check.mjs
import { readFileSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
const root = process.env.BC_APP_ROOT || join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const tmp = join(tmpdir(), `bc-lunar-${process.pid}.mjs`);  // .js của app không phải module với Node → chép ra .mjs
writeFileSync(tmp, readFileSync(join(root, 'bc/public/bc/lib/lunar.js')));
const { isTetDay, isTetHoliday } = await import(tmp);
const D = { '2027': '2027-02-07' };
const ok = [
    ['BC 2027: 07/02 là mùng 1', isTetDay(7, 2, 2027, D) === true],
    ['BC 2027: 09/02 là mùng 3', isTetDay(9, 2, 2027, D) === true],
    ['BC 2027: 06/02 không phải (BC đè thuật toán)', isTetDay(6, 2, 2027, D) === false],
    ['BC 2027: 10/02 không phải', isTetDay(10, 2, 2027, D) === false],
    ['Năm chưa khai → thuật toán (17/02/2026)', isTetDay(17, 2, 2026, D) === isTetHoliday(17, 2, 2026) && isTetHoliday(17, 2, 2026)],
];
let bad = 0;
for (const [l, v] of ok) { console.log(v ? '  ✓' : '  ✗', l); if (!v) bad++; }
console.log(`${ok.length - bad} đạt, ${bad} trượt`);
process.exit(bad ? 1 : 0);
