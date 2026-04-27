import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'CYB';

const FIELDS: readonly FieldDef[] = [
  // レースキー
  { name: 'course_code',       start:  0, len:  2 }, // 場コード
  { name: 'year_code',         start:  2, len:  2 }, // 年
  { name: 'kai',               start:  4, len:  1 }, // 回
  { name: 'day_code',          start:  5, len:  1 }, // 日（16進数）
  { name: 'race_num',          start:  6, len:  2 }, // R
  // 基本情報
  { name: 'uma_num',           start:  8, len:  2 }, // 馬番
  { name: 'chokyo_type',       start: 10, len:  2 }, // 調教タイプ
  { name: 'chokyo_course_type',start: 12, len:  1 }, // 調教コース種別
  // 調教コース種類
  { name: 'course_saka',       start: 13, len:  2 }, // 坂
  { name: 'course_w',          start: 15, len:  2 }, // W（ウッドコース）
  { name: 'course_da',         start: 17, len:  2 }, // ダ
  { name: 'course_shiba',      start: 19, len:  2 }, // 芝
  { name: 'course_pool',       start: 21, len:  2 }, // プ（プール）
  { name: 'course_sho',        start: 23, len:  2 }, // 障
  { name: 'course_poly',       start: 25, len:  2 }, // ポ（ポリトラック）
  // 調教分析情報
  { name: 'chokyo_kyori',      start: 27, len:  1 }, // 調教距離
  { name: 'chokyo_juten',      start: 28, len:  1 }, // 調教重点
  { name: 'oi_index',          start: 29, len:  3 }, // 追切指数
  { name: 'shiage_index',      start: 32, len:  3 }, // 仕上指数
  { name: 'chokyo_ryo_hyoka',  start: 35, len:  1 }, // 調教量評価
  { name: 'shiage_index_henka',start: 36, len:  1 }, // 仕上指数変化
  { name: 'chokyo_comment',    start: 37, len: 40 }, // 調教コメント（全角20文字）
  { name: 'comment_ymd',       start: 77, len:  8 }, // コメント年月日
  { name: 'chokyo_hyoka',      start: 85, len:  1 }, // 調教評価
  { name: 'isshuumae_oi_index',start: 86, len:  3 }, // 一週前追切指数
  { name: 'isshuumae_oi_course',start: 89, len:  2 }, // 一週前追切コース
];

export const convertCYB    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertCYBAll = ()            => convertAll(PREFIX, FIELDS);
