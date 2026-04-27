-- ============================================================
-- JRDB データベース テーブル定義
-- 対象ファイル: UKC / KS / CS / BAC / KYI / CYB / SED(速報)
-- ============================================================

-- ============================================================
-- 1. 馬基本データ (UKC)
-- ============================================================
CREATE TABLE m_horses (
    pedigree_no             CHAR(8)         NOT NULL,           -- 血統登録番号
    horse_name              VARCHAR(36)     NOT NULL,           -- 馬名（全角18文字）
    sex_code                SMALLINT,                           -- 性別コード 1:牡 2:牝 3:セン
    coat_color_code         CHAR(2),                            -- 毛色コード
    horse_symbol_code       CHAR(2),                            -- 馬記号コード
    -- 血統情報
    sire_name               VARCHAR(36),                        -- 父馬名
    dam_name                VARCHAR(36),                        -- 母馬名
    broodmare_sire_name     VARCHAR(36),                        -- 母父馬名
    birthdate               DATE,                               -- 生年月日
    -- 血統キー用生年
    sire_birth_year         SMALLINT,                           -- 父馬生年
    dam_birth_year          SMALLINT,                           -- 母馬生年
    bms_birth_year          SMALLINT,                           -- 母父馬生年
    -- 馬主・生産情報
    owner_name              VARCHAR(40),                        -- 馬主名
    owner_assoc_code        CHAR(2),                            -- 馬主会コード（参考）
    breeder_name            VARCHAR(40),                        -- 生産者名
    production_area         VARCHAR(8),                         -- 産地名
    -- 管理情報
    deregistration_flag     SMALLINT        DEFAULT 0,          -- 登録抹消フラグ 0:現役 1:抹消
    data_date               DATE,                               -- データ年月日
    -- 系統コード（前2桁:大系統 後2桁:小系統）
    sire_bloodline_code     CHAR(4),                            -- 父系統コード
    bms_bloodline_code      CHAR(4),                            -- 母父系統コード

    CONSTRAINT pk_m_horses PRIMARY KEY (pedigree_no)
);

-- ============================================================
-- 2. 騎手マスタ (KS / KZA / KSA)
-- ============================================================
CREATE TABLE m_jockeys (
    jockey_code             CHAR(5)         NOT NULL,           -- 騎手コード
    deregistration_flag     SMALLINT        DEFAULT 0,          -- 登録抹消フラグ 1:抹消 0:現役
    deregistration_date     DATE,                               -- 登録抹消年月日
    jockey_name             VARCHAR(12)     NOT NULL,           -- 騎手名（全角6文字）
    jockey_kana             VARCHAR(30),                        -- 騎手カナ（全角15文字）
    jockey_name_short       VARCHAR(6),                         -- 騎手名略称（全角3文字）
    affiliation_code        SMALLINT,                           -- 所属コード 1:関東 2:関西 3:他
    affiliation_area        VARCHAR(4),                         -- 所属地域名（地方の場合）
    birthdate               DATE,                               -- 生年月日
    first_license_year      SMALLINT,                           -- 初免許年
    apprentice_class        SMALLINT,                           -- 見習い区分 1:☆(1K減) 2:△(2K減) 3:▲(3K減)
    stable_trainer_code     CHAR(5),                            -- 所属厩舎（調教師コード）
    comment                 VARCHAR(40),                        -- 騎手コメント
    comment_date            DATE,                               -- コメント入力年月日
    -- 本年成績
    this_year_leading           SMALLINT,                       -- 本年リーディング
    this_year_flat_1st          SMALLINT,                       -- 本年平地1着
    this_year_flat_2nd          SMALLINT,                       -- 本年平地2着
    this_year_flat_3rd          SMALLINT,                       -- 本年平地3着
    this_year_flat_other        SMALLINT,                       -- 本年平地着外
    this_year_obstacle_1st      SMALLINT,                       -- 本年障害1着
    this_year_obstacle_2nd      SMALLINT,                       -- 本年障害2着
    this_year_obstacle_3rd      SMALLINT,                       -- 本年障害3着
    this_year_obstacle_other    SMALLINT,                       -- 本年障害着外
    this_year_special_wins      SMALLINT,                       -- 本年特別勝数
    this_year_stakes_wins       SMALLINT,                       -- 本年重賞勝数
    -- 昨年成績
    last_year_leading           SMALLINT,                       -- 昨年リーディング
    last_year_flat_1st          SMALLINT,                       -- 昨年平地1着
    last_year_flat_2nd          SMALLINT,                       -- 昨年平地2着
    last_year_flat_3rd          SMALLINT,                       -- 昨年平地3着
    last_year_flat_other        SMALLINT,                       -- 昨年平地着外
    last_year_obstacle_1st      SMALLINT,                       -- 昨年障害1着
    last_year_obstacle_2nd      SMALLINT,                       -- 昨年障害2着
    last_year_obstacle_3rd      SMALLINT,                       -- 昨年障害3着
    last_year_obstacle_other    SMALLINT,                       -- 昨年障害着外
    last_year_special_wins      SMALLINT,                       -- 昨年特別勝数
    last_year_stakes_wins       SMALLINT,                       -- 昨年重賞勝数
    -- 通算成績
    total_flat_1st              INTEGER,                        -- 通算平地1着
    total_flat_2nd              INTEGER,                        -- 通算平地2着
    total_flat_3rd              INTEGER,                        -- 通算平地3着
    total_flat_other            INTEGER,                        -- 通算平地着外
    total_obstacle_1st          INTEGER,                        -- 通算障害1着
    total_obstacle_2nd          INTEGER,                        -- 通算障害2着
    total_obstacle_3rd          INTEGER,                        -- 通算障害3着
    total_obstacle_other        INTEGER,                        -- 通算障害着外
    data_date                   DATE,                           -- データ年月日

    CONSTRAINT pk_m_jockeys PRIMARY KEY (jockey_code)
);

-- ============================================================
-- 3. 調教師マスタ (CS / CZA / CSA)
-- ============================================================
CREATE TABLE m_trainers (
    trainer_code            CHAR(5)         NOT NULL,           -- 調教師コード
    deregistration_flag     SMALLINT        DEFAULT 0,          -- 登録抹消フラグ 1:抹消 0:現役
    deregistration_date     DATE,                               -- 登録抹消年月日
    trainer_name            VARCHAR(12)     NOT NULL,           -- 調教師名（全角6文字）
    trainer_kana            VARCHAR(30),                        -- 調教師カナ（全角15文字）
    trainer_name_short      VARCHAR(6),                         -- 調教師名略称（全角3文字）
    affiliation_code        SMALLINT,                           -- 所属コード 1:関東 2:関西 3:他
    affiliation_area        VARCHAR(4),                         -- 所属地域名（地方の場合）
    birthdate               DATE,                               -- 生年月日
    first_license_year      SMALLINT,                           -- 初免許年
    comment                 VARCHAR(40),                        -- 調教師コメント
    comment_date            DATE,                               -- コメント入力年月日
    -- 本年成績
    this_year_leading           SMALLINT,                       -- 本年リーディング
    this_year_flat_1st          SMALLINT,                       -- 本年平地1着
    this_year_flat_2nd          SMALLINT,                       -- 本年平地2着
    this_year_flat_3rd          SMALLINT,                       -- 本年平地3着
    this_year_flat_other        SMALLINT,                       -- 本年平地着外
    this_year_obstacle_1st      SMALLINT,                       -- 本年障害1着
    this_year_obstacle_2nd      SMALLINT,                       -- 本年障害2着
    this_year_obstacle_3rd      SMALLINT,                       -- 本年障害3着
    this_year_obstacle_other    SMALLINT,                       -- 本年障害着外
    this_year_special_wins      SMALLINT,                       -- 本年特別勝数
    this_year_stakes_wins       SMALLINT,                       -- 本年重賞勝数
    -- 昨年成績
    last_year_leading           SMALLINT,                       -- 昨年リーディング
    last_year_flat_1st          SMALLINT,                       -- 昨年平地1着
    last_year_flat_2nd          SMALLINT,                       -- 昨年平地2着
    last_year_flat_3rd          SMALLINT,                       -- 昨年平地3着
    last_year_flat_other        SMALLINT,                       -- 昨年平地着外
    last_year_obstacle_1st      SMALLINT,                       -- 昨年障害1着
    last_year_obstacle_2nd      SMALLINT,                       -- 昨年障害2着
    last_year_obstacle_3rd      SMALLINT,                       -- 昨年障害3着
    last_year_obstacle_other    SMALLINT,                       -- 昨年障害着外
    last_year_special_wins      SMALLINT,                       -- 昨年特別勝数
    last_year_stakes_wins       SMALLINT,                       -- 昨年重賞勝数
    -- 通算成績
    total_flat_1st              INTEGER,                        -- 通算平地1着
    total_flat_2nd              INTEGER,                        -- 通算平地2着
    total_flat_3rd              INTEGER,                        -- 通算平地3着
    total_flat_other            INTEGER,                        -- 通算平地着外
    total_obstacle_1st          INTEGER,                        -- 通算障害1着
    total_obstacle_2nd          INTEGER,                        -- 通算障害2着
    total_obstacle_3rd          INTEGER,                        -- 通算障害3着
    total_obstacle_other        INTEGER,                        -- 通算障害着外
    data_date                   DATE,                           -- データ年月日

    CONSTRAINT pk_m_trainers PRIMARY KEY (trainer_code)
);

-- ============================================================
-- 4. 番組データ (BAC)
-- ============================================================
-- レースキー: venue_code(2) + race_year(2) + kai(1) + nichi(1,hex) + race_no(2)
CREATE TABLE races (
    venue_code          CHAR(2)         NOT NULL,               -- 場コード
    race_year           CHAR(2)         NOT NULL,               -- 年（西暦下2桁）
    kai                 SMALLINT        NOT NULL,               -- 回
    nichi               CHAR(1)         NOT NULL,               -- 日（16進数: 0-9,a-f）
    race_no             SMALLINT        NOT NULL,               -- R（レース番号）
    race_date           DATE,                                   -- 年月日
    post_time           CHAR(4),                                -- 発走時間 HHMM
    -- レース条件
    distance            SMALLINT,                               -- 距離（m）
    track_code          SMALLINT,                               -- 芝ダ障害コード 1:芝 2:ダート 3:障害
    direction_code      SMALLINT,                               -- 右左 1:右 2:左 3:直 9:他
    course_type         SMALLINT,                               -- 内外 1:通常(内) 2:外 3:直ダ 9:他
    horse_category_code CHAR(2),                                -- 種別（4歳以上等）
    condition_code      CHAR(2),                                -- 条件（900万下等）
    symbol_code         CHAR(3),                                -- 記号（○混等）
    weight_type_code    SMALLINT,                               -- 重量（ハンデ等）
    grade_code          SMALLINT,                               -- グレード（G1等）
    -- レース名・開催情報
    race_name           VARCHAR(50),                            -- レース名（全角25文字）
    lap_count           VARCHAR(8),                             -- 回数（全角半角混在）
    entrant_count       SMALLINT,                               -- 頭数
    course_code         CHAR(1),                                -- コース 1:A 2:A1 3:A2 4:B 5:C 6:D
    holding_type        CHAR(1),                                -- 開催区分 1:関東 2:関西 3:ローカル
    race_name_short     VARCHAR(8),                             -- レース名短縮（全角4文字）
    race_name_9char     VARCHAR(18),                            -- レース名9文字
    data_type           CHAR(1),                                -- データ区分 1:特別登録 2:想定確定 3:前日
    -- 賞金（単位：万円）
    prize_1st           SMALLINT,                               -- 1着賞金
    prize_2nd           SMALLINT,                               -- 2着賞金
    prize_3rd           SMALLINT,                               -- 3着賞金
    prize_4th           SMALLINT,                               -- 4着賞金
    prize_5th           SMALLINT,                               -- 5着賞金
    prize_included_1st  SMALLINT,                               -- 1着算入賞金
    prize_included_2nd  SMALLINT,                               -- 2着算入賞金
    -- 馬券発売フラグ（1:発売 0:発売無し）
    ticket_tansho       SMALLINT,                               -- 単勝
    ticket_fukusho      SMALLINT,                               -- 複勝
    ticket_wakuren      SMALLINT,                               -- 枠連
    ticket_umaren       SMALLINT,                               -- 馬連
    ticket_umatan       SMALLINT,                               -- 馬単
    ticket_wide         SMALLINT,                               -- ワイド
    ticket_sanrenpuku   SMALLINT,                               -- 3連複
    ticket_sanrentan    SMALLINT,                               -- 3連単
    win5_flag           SMALLINT,                               -- WIN5フラグ（1〜5）

    CONSTRAINT pk_races PRIMARY KEY (venue_code, race_year, kai, nichi, race_no)
);

-- ============================================================
-- 5. 競走馬データ / 出走表 (KYI)
-- ============================================================
CREATE TABLE race_entries (
    -- レースキー
    venue_code              CHAR(2)         NOT NULL,
    race_year               CHAR(2)         NOT NULL,
    kai                     SMALLINT        NOT NULL,
    nichi                   CHAR(1)         NOT NULL,
    race_no                 SMALLINT        NOT NULL,
    horse_no                SMALLINT        NOT NULL,           -- 馬番
    -- 基本情報
    pedigree_no             CHAR(8),                            -- 血統登録番号
    horse_name              VARCHAR(36),                        -- 馬名（全角18文字）
    -- 指数情報
    idm                     NUMERIC(4,1),                       -- IDM
    jockey_index            NUMERIC(4,1),                       -- 騎手指数
    info_index              NUMERIC(4,1),                       -- 情報指数
    composite_index         NUMERIC(4,1),                       -- 総合指数
    -- 馬質情報
    leg_type                SMALLINT,                           -- 脚質
    distance_aptitude       SMALLINT,                           -- 距離適性
    improvement_level       SMALLINT,                           -- 上昇度
    rotation                SMALLINT,                           -- ローテーション（金曜日数）
    -- オッズ・人気
    base_odds               NUMERIC(4,1),                       -- 基準オッズ
    base_popularity         SMALLINT,                           -- 基準人気順位
    base_place_odds         NUMERIC(4,1),                       -- 基準複勝オッズ
    base_place_popularity   SMALLINT,                           -- 基準複勝人気順位
    -- 特定情報（専門紙・情報の印数）
    specific_honmei         SMALLINT,                           -- 特定情報◎
    specific_honsho         SMALLINT,                           -- 特定情報○
    specific_tanna          SMALLINT,                           -- 特定情報▲
    specific_sankaku        SMALLINT,                           -- 特定情報△
    specific_batsu          SMALLINT,                           -- 特定情報×
    -- 総合情報（専門紙・情報の印数）
    general_honmei          SMALLINT,                           -- 総合情報◎
    general_honsho          SMALLINT,                           -- 総合情報○
    general_tanna           SMALLINT,                           -- 総合情報▲
    general_sankaku         SMALLINT,                           -- 総合情報△
    general_batsu           SMALLINT,                           -- 総合情報×
    -- その他指数
    popularity_index        SMALLINT,                           -- 人気指数
    training_index          NUMERIC(4,1),                       -- 調教指数
    stable_index            NUMERIC(4,1),                       -- 厩舎指数
    -- 第3版追加
    training_arrow_code     SMALLINT,                           -- 調教矢印コード
    stable_eval_code        SMALLINT,                           -- 厩舎評価コード
    jockey_renso_rate       NUMERIC(3,1),                       -- 騎手期待連対率
    gekiso_index            SMALLINT,                           -- 激走指数
    hoof_code               CHAR(2),                            -- 蹄コード
    heavy_aptitude_code     SMALLINT,                           -- 重適正コード
    class_code              CHAR(2),                            -- クラスコード
    -- 第4版追加
    blinker                 CHAR(1),                            -- ブリンカー 1:初装着 2:再装着 3:ブリンカ
    jockey_name             VARCHAR(12),                        -- 騎手名（全角6文字）
    weight_load             SMALLINT,                           -- 負担重量（0.1kg単位）
    apprentice_class        SMALLINT,                           -- 見習い区分
    trainer_name            VARCHAR(12),                        -- 調教師名（全角6文字）
    trainer_affiliation     VARCHAR(4),                         -- 調教師所属（全角2文字）
    -- 他データリンク用キー
    prev_result_key_1       CHAR(16),                           -- 前走1競走成績キー
    prev_result_key_2       CHAR(16),                           -- 前走2競走成績キー
    prev_result_key_3       CHAR(16),                           -- 前走3競走成績キー
    prev_result_key_4       CHAR(16),                           -- 前走4競走成績キー
    prev_result_key_5       CHAR(16),                           -- 前走5競走成績キー
    prev_race_key_1         CHAR(8),                            -- 前走1レースキー
    prev_race_key_2         CHAR(8),                            -- 前走2レースキー
    prev_race_key_3         CHAR(8),                            -- 前走3レースキー
    prev_race_key_4         CHAR(8),                            -- 前走4レースキー
    prev_race_key_5         CHAR(8),                            -- 前走5レースキー
    frame_no                SMALLINT,                           -- 枠番
    -- 第5版追加（印コード）
    mark_composite          SMALLINT,                           -- 総合印
    mark_idm                SMALLINT,                           -- IDM印
    mark_info               SMALLINT,                           -- 情報印
    mark_jockey             SMALLINT,                           -- 騎手印
    mark_stable             SMALLINT,                           -- 厩舎印
    mark_training           SMALLINT,                           -- 調教印
    mark_gekiso             SMALLINT,                           -- 激走印（1:激走馬）
    turf_aptitude_code      CHAR(1),                            -- 芝適性コード 1:◎ 2:○ 3:△
    dirt_aptitude_code      CHAR(1),                            -- ダ適性コード 1:◎ 2:○ 3:△
    jockey_code             CHAR(5),                            -- 騎手コード（騎手マスタとリンク）
    trainer_code            CHAR(5),                            -- 調教師コード（調教師マスタとリンク）
    -- 第6版追加（賞金情報）
    prize_earned            INTEGER,                            -- 獲得賞金（万円、付加賞含む）
    prize_collected         INTEGER,                            -- 収得賞金（万円）
    condition_class         SMALLINT,                           -- 条件クラス
    -- 第6版追加（展開予想データ）
    ten_index               NUMERIC(4,1),                       -- テン指数（予想）
    pace_index              NUMERIC(4,1),                       -- ペース指数（予想）
    agari_index             NUMERIC(4,1),                       -- 上がり指数（予想）
    position_index          NUMERIC(4,1),                       -- 位置指数（予想）
    pace_forecast           CHAR(1),                            -- ペース予想 H/M/S
    middle_rank             SMALLINT,                           -- 道中順位
    middle_diff             SMALLINT,                           -- 道中差（半馬身単位）
    middle_inner_outer      SMALLINT,                           -- 道中内外
    last3f_rank             SMALLINT,                           -- 後3F順位
    last3f_diff             SMALLINT,                           -- 後3F差（半馬身単位）
    last3f_inner_outer      SMALLINT,                           -- 後3F内外
    goal_rank               SMALLINT,                           -- ゴール順位
    goal_diff               SMALLINT,                           -- ゴール差（半馬身単位）
    goal_inner_outer        SMALLINT,                           -- ゴール内外
    development_symbol      CHAR(1),                            -- 展開記号
    -- 第6a版追加
    distance_aptitude2      SMALLINT,                           -- 距離適性2
    frame_weight            SMALLINT,                           -- 枠確定馬体重（kg）
    frame_weight_diff       SMALLINT,                           -- 枠確定馬体重増減（符号付き）
    -- 第7版追加
    cancellation_flag       SMALLINT,                           -- 取消フラグ（1:取消）
    sex_code                SMALLINT,                           -- 性別コード 1:牡 2:牝 3:セン
    owner_name              VARCHAR(40),                        -- 馬主名（全角20文字）
    owner_assoc_code        CHAR(2),                            -- 馬主会コード
    horse_symbol_code       CHAR(2),                            -- 馬記号コード
    gekiso_rank             SMALLINT,                           -- 激走順位
    ls_index_rank           SMALLINT,                           -- LS指数順位
    ten_index_rank          SMALLINT,                           -- テン指数順位
    pace_index_rank         SMALLINT,                           -- ペース指数順位
    agari_index_rank        SMALLINT,                           -- 上がり指数順位
    position_index_rank     SMALLINT,                           -- 位置指数順位
    -- 第8版追加
    jockey_tansho_rate      NUMERIC(3,1),                       -- 騎手期待単勝率
    jockey_3rd_rate         NUMERIC(3,1),                       -- 騎手期待3着内率
    transport_class         CHAR(1),                            -- 輸送区分
    -- 第9版追加
    running_style           CHAR(8),                            -- 走法（コード表参照）
    body_type               CHAR(24),                           -- 体型（コード表参照）
    body_type_summary_1     CHAR(3),                            -- 体型総合1（特記コード）
    body_type_summary_2     CHAR(3),                            -- 体型総合2（特記コード）
    body_type_summary_3     CHAR(3),                            -- 体型総合3（特記コード）
    horse_note_1            CHAR(3),                            -- 馬特記1（特記コード）
    horse_note_2            CHAR(3),                            -- 馬特記2（特記コード）
    horse_note_3            CHAR(3),                            -- 馬特記3（特記コード）
    start_index             NUMERIC(3,1),                       -- 馬スタート指数
    slow_start_rate         NUMERIC(3,1),                       -- 馬出遅率
    ref_prev_race           CHAR(2),                            -- 参考前走（2走分）
    ref_prev_jockey_code    CHAR(5),                            -- 参考前走騎手コード
    mankken_index           SMALLINT,                           -- 万券指数
    mankken_mark            SMALLINT,                           -- 万券印
    -- 第10版追加
    descent_flag            SMALLINT,                           -- 降級フラグ 0:通常 1:降級 2:2段階降級
    gekiso_type             CHAR(2),                            -- 激走タイプ
    rest_reason_code        CHAR(2),                            -- 休養理由分類コード
    -- 第11版追加
    flags                   CHAR(16),                           -- フラグ（初芝・初ダ・初障等）
    stable_entry_nth_run    SMALLINT,                           -- 入厩何走目
    stable_entry_date       DATE,                               -- 入厩年月日
    days_before_stable_entry SMALLINT,                          -- 入厩何日前
    pasture_destination     VARCHAR(50),                        -- 放牧先
    pasture_rank            CHAR(1),                            -- 放牧先ランク（A-E）
    stable_rank             SMALLINT,                           -- 厩舎ランク（1:高〜9:低）

    CONSTRAINT pk_race_entries PRIMARY KEY (venue_code, race_year, kai, nichi, race_no, horse_no),
    CONSTRAINT fk_race_entries_races
        FOREIGN KEY (venue_code, race_year, kai, nichi, race_no)
        REFERENCES races (venue_code, race_year, kai, nichi, race_no),
    CONSTRAINT fk_race_entries_horses
        FOREIGN KEY (pedigree_no) REFERENCES m_horses (pedigree_no),
    CONSTRAINT fk_race_entries_jockeys
        FOREIGN KEY (jockey_code) REFERENCES m_jockeys (jockey_code),
    CONSTRAINT fk_race_entries_trainers
        FOREIGN KEY (trainer_code) REFERENCES m_trainers (trainer_code)
);

-- ============================================================
-- 6. 調教分析データ (CYB)
-- ============================================================
CREATE TABLE training_analysis (
    venue_code              CHAR(2)         NOT NULL,
    race_year               CHAR(2)         NOT NULL,
    kai                     SMALLINT        NOT NULL,
    nichi                   CHAR(1)         NOT NULL,
    race_no                 SMALLINT        NOT NULL,
    horse_no                SMALLINT        NOT NULL,
    -- 調教タイプ・コース
    training_type           CHAR(2),                            -- 調教タイプ（コード化）
    training_course_type    CHAR(1),                            -- 調教コース種別（コード化）
    -- 調教コース種類（01:有り 00:無し）
    course_slope            CHAR(2),                            -- 坂路
    course_wood             CHAR(2),                            -- ウッドコース
    course_dirt             CHAR(2),                            -- ダートコース
    course_turf             CHAR(2),                            -- 芝コース
    course_pool             CHAR(2),                            -- プール調教
    course_obstacle         CHAR(2),                            -- 障害練習
    course_poly             CHAR(2),                            -- ポリトラック
    -- 調教分析
    training_distance       CHAR(1),                            -- 調教距離 1:長め 2:普通 3:短め 4:2本 0:他
    training_focus          CHAR(1),                            -- 調教重点 1:テン 2:中間 3:終い 4:平均 0:他
    oikiri_index            SMALLINT,                           -- 追切指数（※左詰め格納の既知不具合あり）
    finish_index            SMALLINT,                           -- 仕上指数
    training_amount_eval    CHAR(1),                            -- 調教量評価（A/B/C/D）
    finish_index_change     CHAR(1),                            -- 仕上指数変化
    training_comment        VARCHAR(40),                        -- 調教コメント
    comment_date            DATE,                               -- コメント年月日
    training_eval           CHAR(1),                            -- 調教評価 1:◎ 2:○ 3:△
    prev_week_oikiri_index  SMALLINT,                           -- 一週前追切指数
    prev_week_oikiri_course SMALLINT,                           -- 一週前追切コース

    CONSTRAINT pk_training_analysis PRIMARY KEY (venue_code, race_year, kai, nichi, race_no, horse_no),
    CONSTRAINT fk_training_race_entries
        FOREIGN KEY (venue_code, race_year, kai, nichi, race_no, horse_no)
        REFERENCES race_entries (venue_code, race_year, kai, nichi, race_no, horse_no)
);

-- ============================================================
-- 7. 成績データ（速報: SED / 正式: SEC）
-- 速報版（SED）はレース当日に提供。木曜日に正式版（SEC）で上書き。
-- is_sokuho=TRUE の間は一部項目がNULL（仕様書の×項目）。
-- ============================================================
CREATE TABLE race_results (
    venue_code              CHAR(2)         NOT NULL,
    race_year               CHAR(2)         NOT NULL,
    kai                     SMALLINT        NOT NULL,
    nichi                   CHAR(1)         NOT NULL,
    race_no                 SMALLINT        NOT NULL,
    horse_no                SMALLINT        NOT NULL,           -- 馬番
    -- 競走成績キー
    pedigree_no             CHAR(8),                            -- 血統登録番号
    result_date             DATE,                               -- 年月日
    horse_name              VARCHAR(36),                        -- 馬名
    -- レース条件（速報で提供）
    distance                SMALLINT,                           -- 距離
    track_code              SMALLINT,                           -- 芝ダ障害コード
    direction_code          SMALLINT,                           -- 右左
    course_type             SMALLINT,                           -- 内外
    horse_category_code     CHAR(2),                            -- 種別
    condition_code          CHAR(2),                            -- 条件
    symbol_code             CHAR(3),                            -- 記号
    weight_type_code        SMALLINT,                           -- 重量
    grade_code              SMALLINT,                           -- グレード
    race_name               VARCHAR(50),                        -- レース名
    entrant_count           SMALLINT,                           -- 頭数
    race_name_short         VARCHAR(8),                         -- レース名略称
    -- 馬成績（速報で提供）
    finish_order            SMALLINT,                           -- 着順
    abnormal_code           CHAR(1),                            -- 異常区分
    race_time               NUMERIC(6,1),                       -- タイム（秒）
    weight_load             SMALLINT,                           -- 斤量
    jockey_name             VARCHAR(12),                        -- 騎手名
    trainer_name            VARCHAR(12),                        -- 調教師名
    win_odds                NUMERIC(6,1),                       -- 確定単勝オッズ（速報はNULL）
    win_popularity          SMALLINT,                           -- 確定単勝人気順位
    -- JRDBデータ（速報はNULL、正式版(SEC)で更新）
    idm                     NUMERIC(4,1),                       -- IDM
    base_score              NUMERIC(4,1),                       -- 素点
    track_diff              NUMERIC(4,1),                       -- 馬場差
    pace                    NUMERIC(4,1),                       -- ペース
    slow_start              NUMERIC(4,1),                       -- 出遅
    position_taken          NUMERIC(4,1),                       -- 位置取
    handicap                NUMERIC(4,1),                       -- 不利
    front_handicap          NUMERIC(4,1),                       -- 前不利
    mid_handicap            NUMERIC(4,1),                       -- 中不利
    rear_handicap           NUMERIC(4,1),                       -- 後不利
    race_score              NUMERIC(4,1),                       -- レース
    course_taken            SMALLINT,                           -- コース取り
    improvement_code        SMALLINT,                           -- 上昇度コード
    result_class_code       CHAR(2),                            -- クラスコード
    body_condition_code     SMALLINT,                           -- 馬体コード
    spirit_code             SMALLINT,                           -- 気配コード
    race_pace               NUMERIC(4,1),                       -- レースペース
    horse_pace              NUMERIC(4,1),                       -- 馬ペース
    ten_index               NUMERIC(4,1),                       -- テン指数
    agari_index             NUMERIC(4,1),                       -- 上がり指数
    pace_index              NUMERIC(4,1),                       -- ペース指数
    race_p_index            NUMERIC(4,1),                       -- レースP指数
    -- 速報で提供される追加項目
    top2_horse_name         VARCHAR(36),                        -- 1(2)着馬名
    top2_time_diff          NUMERIC(4,1),                       -- 1(2)着タイム差
    front3f                 NUMERIC(4,1),                       -- 前3F（速報はNULL）
    rear3f                  NUMERIC(4,1),                       -- 後3F（速報はNULL）
    corner_order_1          SMALLINT,                           -- コーナー順位1（速報はNULL）
    corner_order_2          SMALLINT,                           -- コーナー順位2（速報はNULL）
    corner_order_3          SMALLINT,                           -- コーナー順位3（速報はNULL）
    corner_order_4          SMALLINT,                           -- コーナー順位4（速報はNULL）
    front3f_lead_diff       NUMERIC(4,1),                       -- 前3F先頭差（速報はNULL）
    rear3f_lead_diff        NUMERIC(4,1),                       -- 後3F先頭差（速報はNULL）
    jockey_code             CHAR(5),                            -- 騎手コード
    trainer_code            CHAR(5),                            -- 調教師コード
    horse_weight            SMALLINT,                           -- 馬体重
    horse_weight_diff       SMALLINT,                           -- 馬体重増減
    weather_code            SMALLINT,                           -- 天候コード（速報はNULL）
    race_leg_type           SMALLINT,                           -- レース脚質（速報はNULL）
    -- 払戻（速報はNULL）
    payout_tansho           INTEGER,                            -- 単勝払戻
    payout_fukusho          INTEGER,                            -- 複勝払戻
    -- 賞金（速報はNULL）
    prize_main              INTEGER,                            -- 本賞金
    prize_collected         INTEGER,                            -- 収得賞金
    race_pace_flow          SMALLINT,                           -- レースペース流れ（速報はNULL）
    horse_pace_flow         SMALLINT,                           -- 馬ペース流れ（速報はNULL）
    final_corner_course     SMALLINT,                           -- 4角コース取り（速報はNULL）
    -- 管理
    is_sokuho               BOOLEAN         DEFAULT TRUE,       -- TRUE:速報 FALSE:SEC正式版

    CONSTRAINT pk_race_results PRIMARY KEY (venue_code, race_year, kai, nichi, race_no, horse_no),
    CONSTRAINT fk_race_results_races
        FOREIGN KEY (venue_code, race_year, kai, nichi, race_no)
        REFERENCES races (venue_code, race_year, kai, nichi, race_no),
    CONSTRAINT fk_race_results_jockeys
        FOREIGN KEY (jockey_code) REFERENCES m_jockeys (jockey_code),
    CONSTRAINT fk_race_results_trainers
        FOREIGN KEY (trainer_code) REFERENCES m_trainers (trainer_code)
);

-- ============================================================
-- インデックス
-- ============================================================

-- races
CREATE INDEX idx_races_date         ON races (race_date);
CREATE INDEX idx_races_venue_date   ON races (venue_code, race_date);

-- race_entries
CREATE INDEX idx_entries_pedigree   ON race_entries (pedigree_no);
CREATE INDEX idx_entries_jockey     ON race_entries (jockey_code);
CREATE INDEX idx_entries_trainer    ON race_entries (trainer_code);
CREATE INDEX idx_entries_date       ON race_entries (venue_code, race_year, nichi);

-- race_results
CREATE INDEX idx_results_pedigree   ON race_results (pedigree_no);
CREATE INDEX idx_results_finish     ON race_results (finish_order);
CREATE INDEX idx_results_jockey     ON race_results (jockey_code);
CREATE INDEX idx_results_trainer    ON race_results (trainer_code);
CREATE INDEX idx_results_sokuho     ON race_results (is_sokuho);

-- training_analysis
CREATE INDEX idx_training_horse     ON training_analysis (venue_code, race_year, kai, nichi, race_no, horse_no);
