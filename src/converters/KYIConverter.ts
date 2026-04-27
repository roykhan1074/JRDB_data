import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'KYI';

const FIELDS: readonly FieldDef[] = [
  // レースキー
  { name: 'course_code',          start:   0, len:  2 }, // 場コード
  { name: 'year_code',            start:   2, len:  2 }, // 年
  { name: 'kai',                  start:   4, len:  1 }, // 回
  { name: 'day_code',             start:   5, len:  1 }, // 日（16進数）
  { name: 'race_num',             start:   6, len:  2 }, // R
  // 基本情報
  { name: 'uma_num',              start:   8, len:  2 }, // 馬番
  { name: 'blood_reg_num',        start:  10, len:  8 }, // 血統登録番号
  { name: 'uma_name',             start:  18, len: 36 }, // 馬名（全角18文字）
  // 指数情報
  { name: 'idm',                  start:  54, len:  5 }, // IDM
  { name: 'kishu_index',          start:  59, len:  5 }, // 騎手指数
  { name: 'joho_index',           start:  64, len:  5 }, // 情報指数
  { name: 'sogo_index',           start:  84, len:  5 }, // 総合指数
  // 馬質情報
  { name: 'kyakushitsu',          start:  89, len:  1 }, // 脚質
  { name: 'kyori_tekisei',        start:  90, len:  1 }, // 距離適性
  { name: 'joshodo',              start:  91, len:  1 }, // 上昇度
  { name: 'rotation',             start:  92, len:  3 }, // ローテーション
  // オッズ・人気
  { name: 'kijun_odds',           start:  95, len:  5 }, // 基準オッズ
  { name: 'kijun_ninki',          start: 100, len:  2 }, // 基準人気順位
  { name: 'kijun_fukusho_odds',   start: 102, len:  5 }, // 基準複勝オッズ
  { name: 'kijun_fukusho_ninki',  start: 107, len:  2 }, // 基準複勝人気順位
  // 特定情報（専門紙印数）
  { name: 'tokutei_honmei',       start: 109, len:  3 }, // 特定◎
  { name: 'tokutei_taikou',       start: 112, len:  3 }, // 特定○
  { name: 'tokutei_tanana',       start: 115, len:  3 }, // 特定▲
  { name: 'tokutei_rengai',       start: 118, len:  3 }, // 特定△
  { name: 'tokutei_batsu',        start: 121, len:  3 }, // 特定×
  // 総合情報
  { name: 'sogo_honmei',          start: 124, len:  3 }, // 総合◎
  { name: 'sogo_taikou',          start: 127, len:  3 }, // 総合○
  { name: 'sogo_tanana',          start: 130, len:  3 }, // 総合▲
  { name: 'sogo_rengai',          start: 133, len:  3 }, // 総合△
  { name: 'sogo_batsu',           start: 136, len:  3 }, // 総合×
  // その他指数
  { name: 'ninki_index',          start: 139, len:  5 }, // 人気指数
  { name: 'chokyo_index',         start: 144, len:  5 }, // 調教指数
  { name: 'kyusha_index',         start: 149, len:  5 }, // 厩舎指数
  // 第3版
  { name: 'chokyo_yajirushi',     start: 154, len:  1 }, // 調教矢印コード
  { name: 'kyusha_hyoka',         start: 155, len:  1 }, // 厩舎評価コード
  { name: 'kishu_renntai_rate',   start: 156, len:  4 }, // 騎手期待連対率
  { name: 'gekiso_index',         start: 160, len:  3 }, // 激走指数
  { name: 'hizume_code',          start: 163, len:  2 }, // 蹄コード
  { name: 'omo_tekisei',          start: 165, len:  1 }, // 重適正コード
  { name: 'class_code',           start: 166, len:  2 }, // クラスコード
  // 第4版
  { name: 'blinker',              start: 170, len:  1 }, // ブリンカー
  { name: 'kishu_name',           start: 171, len: 12 }, // 騎手名（全角6文字）
  { name: 'futan_juryo',          start: 183, len:  3 }, // 負担重量（0.1kg単位）
  { name: 'minarai_kubun',        start: 186, len:  1 }, // 見習い区分
  { name: 'trainer_name',         start: 187, len: 12 }, // 調教師名（全角6文字）
  { name: 'trainer_belong',       start: 199, len:  4 }, // 調教師所属
  // 前走リンクキー
  { name: 'prev1_seiseki_key',    start: 203, len: 16 }, // 前走1競走成績キー
  { name: 'prev2_seiseki_key',    start: 219, len: 16 }, // 前走2競走成績キー
  { name: 'prev3_seiseki_key',    start: 235, len: 16 }, // 前走3競走成績キー
  { name: 'prev4_seiseki_key',    start: 251, len: 16 }, // 前走4競走成績キー
  { name: 'prev5_seiseki_key',    start: 267, len: 16 }, // 前走5競走成績キー
  { name: 'prev1_race_key',       start: 283, len:  8 }, // 前走1レースキー
  { name: 'prev2_race_key',       start: 291, len:  8 }, // 前走2レースキー
  { name: 'prev3_race_key',       start: 299, len:  8 }, // 前走3レースキー
  { name: 'prev4_race_key',       start: 307, len:  8 }, // 前走4レースキー
  { name: 'prev5_race_key',       start: 315, len:  8 }, // 前走5レースキー
  { name: 'waku_num',             start: 323, len:  1 }, // 枠番
  // 第5版（印コード）
  { name: 'in_sogo',              start: 326, len:  1 }, // 総合印
  { name: 'in_idm',               start: 327, len:  1 }, // IDM印
  { name: 'in_joho',              start: 328, len:  1 }, // 情報印
  { name: 'in_kishu',             start: 329, len:  1 }, // 騎手印
  { name: 'in_kyusha',            start: 330, len:  1 }, // 厩舎印
  { name: 'in_chokyo',            start: 331, len:  1 }, // 調教印
  { name: 'in_gekiso',            start: 332, len:  1 }, // 激走印
  { name: 'shiba_tekisei',        start: 333, len:  1 }, // 芝適性コード
  { name: 'dirt_tekisei',         start: 334, len:  1 }, // ダ適性コード
  { name: 'kishu_code',           start: 335, len:  5 }, // 騎手コード
  { name: 'trainer_code',         start: 340, len:  5 }, // 調教師コード
  // 第6版
  { name: 'prize_earned',         start: 346, len:  6 }, // 獲得賞金（万円）
  { name: 'prize_shu',            start: 352, len:  5 }, // 収得賞金（万円）
  { name: 'joken_class',          start: 357, len:  1 }, // 条件クラス
  { name: 'ten_index',            start: 358, len:  5 }, // テン指数
  { name: 'pace_index',           start: 363, len:  5 }, // ペース指数
  { name: 'agari_index',          start: 368, len:  5 }, // 上がり指数
  { name: 'ichi_index',           start: 373, len:  5 }, // 位置指数
  { name: 'pace_yoso',            start: 378, len:  1 }, // ペース予想
  { name: 'michunaka_juni',       start: 379, len:  2 }, // 道中順位
  { name: 'michunaka_sa',         start: 381, len:  2 }, // 道中差
  { name: 'michunaka_naigai',     start: 383, len:  1 }, // 道中内外
  { name: 'ato3f_juni',           start: 384, len:  2 }, // 後3F順位
  { name: 'ato3f_sa',             start: 386, len:  2 }, // 後3F差
  { name: 'ato3f_naigai',         start: 388, len:  1 }, // 後3F内外
  { name: 'goal_juni',            start: 389, len:  2 }, // ゴール順位
  { name: 'goal_sa',              start: 391, len:  2 }, // ゴール差
  { name: 'goal_naigai',          start: 393, len:  1 }, // ゴール内外
  { name: 'tenkai_kigo',          start: 394, len:  1 }, // 展開記号
  // 第6a版
  { name: 'kyori_tekisei2',       start: 395, len:  1 }, // 距離適性2
  { name: 'waku_weight',          start: 396, len:  3 }, // 枠確定馬体重
  { name: 'waku_weight_diff',     start: 399, len:  3 }, // 枠確定馬体重増減
  // 第7版
  { name: 'torikeshi_flag',       start: 402, len:  1 }, // 取消フラグ
  { name: 'seibetsu_code',        start: 403, len:  1 }, // 性別コード
  { name: 'umanushi_name',        start: 404, len: 40 }, // 馬主名（全角20文字）
  { name: 'umanushi_code',        start: 444, len:  2 }, // 馬主会コード
  { name: 'uma_kigo_code',        start: 446, len:  2 }, // 馬記号コード
  { name: 'gekiso_juni',          start: 448, len:  2 }, // 激走順位
  { name: 'ls_index_juni',        start: 450, len:  2 }, // LS指数順位
  { name: 'ten_index_juni',       start: 452, len:  2 }, // テン指数順位
  { name: 'pace_index_juni',      start: 454, len:  2 }, // ペース指数順位
  { name: 'agari_index_juni',     start: 456, len:  2 }, // 上がり指数順位
  { name: 'ichi_index_juni',      start: 458, len:  2 }, // 位置指数順位
  // 第8版
  { name: 'kishu_tansho_rate',    start: 460, len:  4 }, // 騎手期待単勝率
  { name: 'kishu_3uchi_rate',     start: 464, len:  4 }, // 騎手期待3着内率
  { name: 'yuso_kubun',           start: 468, len:  1 }, // 輸送区分
  // 第9版
  { name: 'soho',                 start: 469, len:  8 }, // 走法
  { name: 'taigata',              start: 477, len: 24 }, // 体型
  { name: 'taigata_sogo1',        start: 501, len:  3 }, // 体型総合1
  { name: 'taigata_sogo2',        start: 504, len:  3 }, // 体型総合2
  { name: 'taigata_sogo3',        start: 507, len:  3 }, // 体型総合3
  { name: 'uma_tokki1',           start: 510, len:  3 }, // 馬特記1
  { name: 'uma_tokki2',           start: 513, len:  3 }, // 馬特記2
  { name: 'uma_tokki3',           start: 516, len:  3 }, // 馬特記3
  { name: 'uma_start_index',      start: 519, len:  4 }, // 馬スタート指数
  { name: 'uma_okure_rate',       start: 523, len:  4 }, // 馬出遅率
  { name: 'sankosaki_mae',        start: 527, len:  2 }, // 参考前走
  { name: 'sankosaki_kishu_code', start: 529, len:  5 }, // 参考前走騎手コード
  { name: 'manbaken_index',       start: 534, len:  3 }, // 万券指数
  { name: 'manbaken_in',          start: 537, len:  1 }, // 万券印
  // 第10版
  { name: 'kokyuu_flag',          start: 538, len:  1 }, // 降級フラグ
  { name: 'gekiso_type',          start: 539, len:  2 }, // 激走タイプ
  { name: 'kyuyo_riyuu_code',     start: 541, len:  2 }, // 休養理由分類コード
  // 第11版
  { name: 'flag',                 start: 543, len: 16 }, // フラグ
  { name: 'nyukyu_hashiri',       start: 559, len:  2 }, // 入厩何走目
  { name: 'nyukyu_ymd',           start: 561, len:  8 }, // 入厩年月日
  { name: 'nyukyu_nichi_mae',     start: 569, len:  3 }, // 入厩何日前
  { name: 'hohbokusaki',          start: 572, len: 50 }, // 放牧先
  { name: 'hohbokusaki_rank',     start: 622, len:  1 }, // 放牧先ランク
  { name: 'kyusha_rank',          start: 623, len:  1 }, // 厩舎ランク
];

export const convertKYI    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertKYIAll = ()            => convertAll(PREFIX, FIELDS);
