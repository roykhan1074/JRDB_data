import { convertFile, convertAll, FieldDef } from './FixedLengthConverter';

const PREFIX = 'UKC';

const FIELDS: readonly FieldDef[] = [
  // 基本情報
  { name: 'blood_reg_num',    start:   0, len:  8 }, // 血統登録番号
  { name: 'uma_name',         start:   8, len: 36 }, // 馬名（全角18文字）
  { name: 'seibetsu_code',    start:  44, len:  1 }, // 性別コード
  { name: 'moke_code',        start:  45, len:  2 }, // 毛色コード
  { name: 'uma_kigo_code',    start:  47, len:  2 }, // 馬記号コード
  // 血統情報
  { name: 'chichi_uma_name',  start:  49, len: 36 }, // 父馬名（全角18文字）
  { name: 'haha_uma_name',    start:  85, len: 36 }, // 母馬名（全角18文字）
  { name: 'hahachichi_name',  start: 121, len: 36 }, // 母父馬名（全角18文字）
  // 生年月日
  { name: 'birthdate',        start: 157, len:  8 }, // 生年月日 YYYYMMDD
  // 第2版
  { name: 'chichi_birth_year',start: 165, len:  4 }, // 父馬生年（血統キー用）
  { name: 'haha_birth_year',  start: 169, len:  4 }, // 母馬生年
  { name: 'hahachichi_birth_year', start: 173, len: 4 }, // 母父馬生年
  { name: 'umanushi_name',    start: 177, len: 40 }, // 馬主名（全角20文字）
  { name: 'umanushi_code',    start: 217, len:  2 }, // 馬主会コード
  { name: 'seisansha_name',   start: 219, len: 40 }, // 生産者名（全角20文字）
  { name: 'sanchi_name',      start: 259, len:  8 }, // 産地名（全角4文字）
  { name: 'massho_flag',      start: 267, len:  1 }, // 登録抹消フラグ
  { name: 'data_ymd',         start: 268, len:  8 }, // データ年月日 YYYYMMDD
  // 第3版
  { name: 'chichi_keitou_code',start: 276, len: 4 }, // 父系統コード
  { name: 'hahachichi_keitou_code', start: 280, len: 4 }, // 母父系統コード
];

export const convertUKC    = (ymd: string) => convertFile(PREFIX, ymd, FIELDS);
export const convertUKCAll = ()            => convertAll(PREFIX, FIELDS);
