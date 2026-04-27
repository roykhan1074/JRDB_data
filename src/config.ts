import path from 'path';
import dotenv from 'dotenv';

dotenv.config();

export const JRDB_BASE_URL = process.env.JRDB_BASE_URL ?? 'https://www.jrdb.com/member/datazip';
export const JRDB_USER     = process.env.JRDB_USER ?? '';
export const JRDB_PASS     = process.env.JRDB_PASS ?? '';
export const DATA_DIR      = process.env.DATA_DIR
  ? path.resolve(process.env.DATA_DIR)
  : path.resolve(__dirname, '..', 'data');

/**
 * JRDBのファイル種別定義
 *
 * key   : グループ名（任意）
 * label : 説明
 * dirs  : JRDBサーバー上のフォルダ名（先頭大文字がJRDB仕様）
 *         ファイル名はフォルダ名を大文字にしたものになる
 *
 * 新しいファイル種別を追加する場合はここに追加するだけでOK
 */
export interface FileGroupDef {
  label: string;
  dirs: string[];
}

export const FILE_GROUPS: Record<string, FileGroupDef> = {
  race_before: {
    label: '出走前データ (BAC/KYI/CYB)',
    dirs: ['Bac', 'Kyi', 'Cyb'],
  },
  race_result: {
    label: '成績データ (SED)',
    dirs: ['Sed'],
  },
  horse_master: {
    label: '馬マスター (UKC)',
    dirs: ['Ukc'],
  },
  jockey_master: {
    label: '騎手マスター (KS)',
    dirs: ['Ks'],
  },
  trainer_master: {
    label: '調教師マスター (CS)',
    dirs: ['Cs'],
  },
};

/** ダウンロード対象グループ（省略時は全グループ） */
export const DEFAULT_GROUPS = Object.keys(FILE_GROUPS);
