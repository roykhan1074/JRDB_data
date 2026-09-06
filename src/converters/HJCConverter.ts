import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'HJC';

// Record size: 444 bytes (442 data + CRLF)
// One record per race。JRDB「成績払戻データ仕様書」第８版に準拠。
// 券種ごとに OCC 個の (組番, 払戻金) ペアが繰り返される（同着による複数配当に対応）。
function payoutGroup(
  namePrefix: string,
  start: number,
  occ: number,
  comboLen: number,
  payoutLen: number,
): FieldDef[] {
  const fields: FieldDef[] = [];
  const slotLen = comboLen + payoutLen;
  for (let i = 1; i <= occ; i++) {
    const slotStart = start + (i - 1) * slotLen;
    fields.push({ name: `${namePrefix}_umaban_${i}`, start: slotStart, len: comboLen });
    fields.push({ name: `${namePrefix}_payout_${i}`, start: slotStart + comboLen, len: payoutLen });
  }
  return fields;
}

const FIELDS: readonly FieldDef[] = [
  // レースキー
  { name: 'course_code', start: 0, len: 2 }, // 場コード
  { name: 'year_code',   start: 2, len: 2 }, // 年
  { name: 'kai',         start: 4, len: 1 }, // 回
  { name: 'day_code',    start: 5, len: 1 }, // 日（16進数）
  { name: 'race_num',    start: 6, len: 2 }, // R
  // 払戻データ（相対位置は仕様書の1始まり表記から-1したバイトオフセット）
  ...payoutGroup('tansho',     8,   3, 2, 7), // 単勝払戻       3件 × 9  = 27 byte
  ...payoutGroup('fukusho',    35,  5, 2, 7), // 複勝払戻       5件 × 9  = 45 byte
  ...payoutGroup('wakuren',    80,  3, 2, 7), // 枠連払戻       3件 × 9  = 27 byte
  ...payoutGroup('umaren',     107, 3, 4, 8), // 馬連払戻       3件 × 12 = 36 byte
  ...payoutGroup('wide',       143, 7, 4, 8), // ワイド払戻     7件 × 12 = 84 byte
  ...payoutGroup('umatan',     227, 6, 4, 8), // 馬単払戻       6件 × 12 = 72 byte
  ...payoutGroup('sanrenpuku', 299, 3, 6, 8), // 3連複払戻      3件 × 14 = 42 byte
  ...payoutGroup('sanrentan',  341, 6, 6, 9), // 3連単払戻      6件 × 15 = 90 byte
  // 予備1(10) + 予備2(1) は未使用のため取り込まない
];

export const convertHJC    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertHJCAll = ()            => convertAll(PREFIX, FIELDS);
