-- ============================================================
-- 期待値指数（EV指数）テーブル
-- 出馬表で「このレースの軸/消し」を判断するための、レース内相対順位指数。
-- 計算はpython/ev_index_etl.pyが行い、このテーブルへ書き込む（atomic RENAME方式）。
-- 先読みバイアス防止: モデルはT_SEDで結果が確定した過去レースのみで学習し、
-- スコアリングはT_KYI×T_BACのみ（結果未確定の出走予定レースにも対応）で行う。
-- ============================================================
CREATE TABLE IF NOT EXISTS T_EV_SCORE (
  course_code       CHAR(2)      NOT NULL,
  year_code         CHAR(2)      NOT NULL,
  kai               CHAR(1)      NOT NULL,
  day_code          CHAR(1)      NOT NULL,
  race_num          CHAR(2)      NOT NULL,
  uma_num           CHAR(2)      NOT NULL,

  pred_place_prob   DECIMAL(5,4)          COMMENT 'モデル予測複勝確率(0-1)',
  market_place_prob DECIMAL(5,4)          COMMENT '市場インプライド複勝確率(1/複勝基準オッズ)',
  ev_index          DECIMAL(7,2)          COMMENT '期待値指数 = (pred/market - 1) * 100。プラスが大きいほど市場の過小評価',
  race_rank         TINYINT               COMMENT 'レース内順位（1=最有力・軸候補）',
  race_rank_from_last TINYINT             COMMENT 'レース内下位からの順位（1=最下位・消し候補）',
  heads             TINYINT               COMMENT 'そのレースの頭数（順位の分母）',

  model_version     VARCHAR(20)           COMMENT '学習に使ったモデルのバージョン識別（学習期間の終端日等）',
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
  INDEX idx_ev_race_rank (race_rank),
  INDEX idx_ev_race (course_code, year_code, kai, day_code, race_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='期待値指数（レース内相対順位・軸/消し判定用）';
