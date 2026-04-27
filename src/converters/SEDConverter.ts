import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'SED';

const FIELDS: readonly FieldDef[] = [
  // レースキー
  { name: 'course_code',       start:   0, len:  2 }, // 場コード
  { name: 'year_code',         start:   2, len:  2 }, // 年
  { name: 'kai',               start:   4, len:  1 }, // 回
  { name: 'day_code',          start:   5, len:  1 }, // 日（16進数）
  { name: 'race_num',          start:   6, len:  2 }, // R
  // 基本情報
  { name: 'umaban',            start:   8, len:  2 }, // 馬番
  // 競走成績キー
  { name: 'blood_num',         start:  10, len:  8 }, // 血統登録番号
  { name: 'ymd',               start:  18, len:  8 }, // 年月日 YYYYMMDD
  // レース情報
  { name: 'horse_name',        start:  26, len: 36 }, // 馬名（全角18文字）
  { name: 'distance',          start:  62, len:  4 }, // 距離
  { name: 'tds_code',          start:  66, len:  1 }, // 芝ダ障害コード
  { name: 'migihidari',        start:  67, len:  1 }, // 右左
  { name: 'naigai',            start:  68, len:  1 }, // 内外
  { name: 'baba_cond',         start:  69, len:  2 }, // 馬場状態
  { name: 'syubetsu',          start:  71, len:  2 }, // 種別
  { name: 'class',             start:  73, len:  2 }, // 条件
  { name: 'kigou',             start:  75, len:  3 }, // 記号
  { name: 'weight',            start:  78, len:  1 }, // 重量
  { name: 'grade',             start:  79, len:  1 }, // グレード
  { name: 'race_name',         start:  80, len: 50 }, // レース名（全角25文字）
  { name: 'heads',             start: 130, len:  2 }, // 頭数
  { name: 'race_name_ryaku',   start: 132, len:  8 }, // レース名略称
  // 馬成績
  { name: 'order_of_finish',   start: 140, len:  2 }, // 着順
  { name: 'ijou_kubun',        start: 142, len:  1 }, // 異常区分
  { name: 'finish_time',       start: 143, len:  4 }, // タイム
  { name: 'kinryou',           start: 147, len:  3 }, // 斤量
  { name: 'jockey_name',       start: 150, len: 12 }, // 騎手名（全角6文字）
  { name: 'trainer_name',      start: 162, len: 12 }, // 調教師名（全角6文字）
  { name: 'win_odds',          start: 174, len:  6 }, // 確定単勝オッズ
  { name: 'win_odds_rank',     start: 180, len:  2 }, // 確定単勝人気順位
  // JRDBデータ
  { name: 'idm',               start: 182, len:  3 }, // IDM
  { name: 'soten',             start: 185, len:  3 }, // 素点
  { name: 'baba_diff',         start: 188, len:  3 }, // 馬場差
  { name: 'pace',              start: 191, len:  3 }, // ペース
  { name: 'deokure',           start: 194, len:  3 }, // 出遅
  { name: 'ichidori',          start: 197, len:  3 }, // 位置取
  { name: 'furi',              start: 200, len:  3 }, // 不利
  { name: 'mae_furi',          start: 203, len:  3 }, // 前不利
  { name: 'naka_furi',         start: 206, len:  3 }, // 中不利
  { name: 'ushiro_furi',       start: 209, len:  3 }, // 後不利
  { name: 'race',              start: 212, len:  3 }, // レース
  { name: 'course_posi',       start: 215, len:  1 }, // コース取り
  { name: 'up_code',           start: 216, len:  1 }, // 上昇度コード
  { name: 'class_code',        start: 217, len:  2 }, // クラスコード
  { name: 'batai_code',        start: 219, len:  1 }, // 馬体コード
  { name: 'kehai_code',        start: 220, len:  1 }, // 気配コード
  { name: 'race_pace',         start: 221, len:  1 }, // レースペース
  { name: 'horse_pace',        start: 222, len:  1 }, // 馬ペース
  { name: 'first_half_idx',    start: 223, len:  5 }, // テン指数
  { name: 'latter_half_idx',   start: 228, len:  5 }, // 上がり指数
  { name: 'pace_idx',          start: 233, len:  5 }, // ペース指数
  { name: 'race_pace_idx',     start: 238, len:  5 }, // レースP指数
  { name: 'win_horse_name',    start: 243, len: 12 }, // 1(2)着馬名（全角6文字）
  { name: 'win_diff',          start: 255, len:  3 }, // 1(2)着タイム差
  { name: 'first_half_time',   start: 258, len:  3 }, // 前3F
  { name: 'latter_half_time',  start: 261, len:  3 }, // 後3F
  { name: 'place_odds',        start: 290, len:  6 }, // 確定複勝オッズ下
  { name: 'win_odds_10',       start: 296, len:  6 }, // 10時単勝オッズ
  { name: 'place_odds_10',     start: 302, len:  6 }, // 10時複勝オッズ
  { name: 'corner_1',          start: 308, len:  2 }, // コーナー順位1
  { name: 'corner_2',          start: 310, len:  2 }, // コーナー順位2
  { name: 'corner_3',          start: 312, len:  2 }, // コーナー順位3
  { name: 'corner_4',          start: 314, len:  2 }, // コーナー順位4
  { name: 'first_half_diff',   start: 316, len:  3 }, // 前3F先頭差
  { name: 'latter_half_diff',  start: 319, len:  3 }, // 後3F先頭差
  { name: 'jockey_code',       start: 322, len:  5 }, // 騎手コード
  { name: 'trainer_code',      start: 327, len:  5 }, // 調教師コード
  { name: 'horse_weight',      start: 332, len:  3 }, // 馬体重
  { name: 'horse_weight_diff', start: 335, len:  3 }, // 馬体重増減
  { name: 'weather_code',      start: 338, len:  1 }, // 天候コード
  { name: 'course_abcd',       start: 339, len:  1 }, // コース
  { name: 'race_kyakushitsu',  start: 340, len:  1 }, // レース脚質
  // 払戻データ
  { name: 'win',               start: 341, len:  7 }, // 単勝
  { name: 'place',             start: 348, len:  7 }, // 複勝
  // その他
  { name: 'hon_syoukin',       start: 355, len:  5 }, // 本賞金
  { name: 'syutoku_syokin',    start: 360, len:  5 }, // 収得賞金
  { name: 'race_pace_stream',  start: 365, len:  2 }, // レースペース流れ
  { name: 'horse_pace_stream', start: 367, len:  2 }, // 馬ペース流れ
  { name: 'corner_4_posi',     start: 369, len:  1 }, // 4角コース取り
];

export const convertSED    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertSEDAll = ()            => convertAll(PREFIX, FIELDS);
