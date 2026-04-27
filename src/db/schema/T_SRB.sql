CREATE TABLE IF NOT EXISTS T_SRB (
  course_code      CHAR(2)      NOT NULL COMMENT '場コード',
  year_code        CHAR(2)      NOT NULL COMMENT '年',
  kai              CHAR(1)      NOT NULL COMMENT '回',
  day_code         CHAR(1)      NOT NULL COMMENT '日',
  race_num         CHAR(2)      NOT NULL COMMENT 'R',
  numeric_data     CHAR(54)              COMMENT '数値データ',
  corner_order_1   CHAR(64)              COMMENT 'コーナー通過順位1',
  corner_order_2   CHAR(64)              COMMENT 'コーナー通過順位2',
  corner_order_3   CHAR(64)              COMMENT 'コーナー通過順位3',
  corner_order_4   CHAR(64)              COMMENT 'コーナー通過順位4',
  indicator        CHAR(1)               COMMENT 'インジケータ',
  flag_field       CHAR(23)              COMMENT 'フラグフィールド',
  commentary       VARCHAR(508)          COMMENT 'レースコメント',
  load_file        VARCHAR(20)           COMMENT 'ロードファイル',
  last_update      VARCHAR(20)           COMMENT '最終更新',
  PRIMARY KEY (course_code, year_code, kai, day_code, race_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SRB成績速報';
