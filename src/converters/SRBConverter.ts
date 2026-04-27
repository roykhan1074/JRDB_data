import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'SRB';

// Record size: 852 bytes (850 data + CRLF)
// One record per race (not per horse)
const FIELDS: readonly FieldDef[] = [
  // レースキー
  { name: 'course_code',    start:   0, len:  2 }, // 場コード
  { name: 'year_code',      start:   2, len:  2 }, // 年
  { name: 'kai',            start:   4, len:  1 }, // 回
  { name: 'day_code',       start:   5, len:  1 }, // 日（16進数）
  { name: 'race_num',       start:   6, len:  2 }, // R
  // 数値データ（集計・払戻情報等）
  { name: 'numeric_data',   start:   8, len: 54 }, // 未定義数値データ
  // コーナー通過順位テキスト
  { name: 'corner_order_1', start:  62, len: 64 }, // コーナー通過順位1
  { name: 'corner_order_2', start: 126, len: 64 }, // コーナー通過順位2
  { name: 'corner_order_3', start: 190, len: 64 }, // コーナー通過順位3
  { name: 'corner_order_4', start: 254, len: 64 }, // コーナー通過順位4
  // フラグ
  { name: 'indicator',      start: 318, len:  1 }, // インジケータ
  { name: 'flag_field',     start: 319, len: 23 }, // フラグフィールド
  // レースコメント（Shift-JIS）
  { name: 'commentary',     start: 342, len: 508 }, // レースコメント
];

export const convertSRB    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertSRBAll = ()            => convertAll(PREFIX, FIELDS);
