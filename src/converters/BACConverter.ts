import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'BAC';

const FIELDS: readonly FieldDef[] = [
  { name: 'course_code',     start:   0, len:  2 }, // 場コード
  { name: 'year_code',       start:   2, len:  2 }, // 年
  { name: 'kai',             start:   4, len:  1 }, // 回
  { name: 'day_code',        start:   5, len:  1 }, // 日（16進数）
  { name: 'race_num',        start:   6, len:  2 }, // R
  { name: 'ymd',             start:   8, len:  8 }, // 年月日 YYYYMMDD
  { name: 'start_time',      start:  16, len:  4 }, // 発走時間 HHMM
  { name: 'distance',        start:  20, len:  4 }, // 距離
  { name: 'tds_code',        start:  24, len:  1 }, // 芝ダ障害コード
  { name: 'migihidari',      start:  25, len:  1 }, // 右左
  { name: 'naigai',          start:  26, len:  1 }, // 内外
  { name: 'syubetsu',        start:  27, len:  2 }, // 種別
  { name: 'class',           start:  29, len:  2 }, // 条件
  { name: 'kigou',           start:  31, len:  3 }, // 記号
  { name: 'weight',          start:  34, len:  1 }, // 重量
  { name: 'grade',           start:  35, len:  1 }, // グレード
  { name: 'race_name',       start:  36, len: 50 }, // レース名（全角25文字）
  { name: 'kaisu',           start:  86, len:  8 }, // 回数
  { name: 'heads',           start:  94, len:  2 }, // 頭数
  { name: 'course_abcd',     start:  96, len:  1 }, // コース
  { name: 'kaisai_kubun',    start:  97, len:  1 }, // 開催区分
  { name: 'race_name_short', start:  98, len:  8 }, // レース名短縮（全角4文字）
  { name: 'race_name_9char', start: 106, len: 18 }, // レース名９文字（全角9文字）
  { name: 'data_kubun',      start: 124, len:  1 }, // データ区分
  { name: 'prize_1st',       start: 125, len:  5 }, // 1着賞金（万円）
  { name: 'prize_2nd',       start: 130, len:  5 }, // 2着賞金（万円）
  { name: 'prize_3rd',       start: 135, len:  5 }, // 3着賞金（万円）
  { name: 'prize_4th',       start: 140, len:  5 }, // 4着賞金（万円）
  { name: 'prize_5th',       start: 145, len:  5 }, // 5着賞金（万円）
  { name: 'prize_1st_calc',  start: 150, len:  5 }, // 1着算入賞金（万円）
  { name: 'prize_2nd_calc',  start: 155, len:  5 }, // 2着算入賞金（万円）
  { name: 'baken_flag',      start: 160, len: 16 }, // 馬券発売フラグ
  { name: 'win5_flag',       start: 176, len:  1 }, // WIN5フラグ
];

export const convertBAC    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertBACAll = ()            => convertAll(PREFIX, FIELDS);
