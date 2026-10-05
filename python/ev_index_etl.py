# -*- coding: utf-8 -*-
"""
期待値指数（EV指数）ETL

出馬表で「このレースの軸/消し」を判断するための、レース内相対順位指数を計算し、
T_EV_SCOREテーブルへ書き込む。

先読みバイアス防止の設計（CLAUDE.md「指数/スコアETL実装時の必須チェック」参照）:
- モデルの学習は T_KYI×T_BAC×T_SED（結果が確定した過去レースのみ）で行う。
- スコアリング（点数を付ける対象）は T_KYI×T_BAC のみ（T_SED不要）で行うため、
  結果未確定の出走予定レース（今日これから行われるレース）にもスコアが付く。
- ライブテーブルへの書き込みは「別名で新規構築→完成後に原子的にRENAMEで差し替え」方式
  （sql/blinker_index.sql等と同じ設計。ETL実行中のクラッシュでライブテーブルが壊れることを防ぐ）。

実行方法: python python/ev_index_etl.py
"""
import sys
import os
import io
import warnings

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
import mysql.connector
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import cross_val_predict, KFold
from sklearn.preprocessing import OrdinalEncoder
from datetime import datetime, date

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

CAT_COLS = ["course_code", "tds_code", "kyakushitsu", "joshodo", "kyori_tekisei", "omo_tekisei",
            "dirt_tekisei", "shiba_tekisei", "chokyo_yajirushi", "kyusha_hyoka", "blinker", "waku_num"]
NUM_COLS = ["distance", "ten_juni", "agari_juni", "ichi_juni", "goal_juni", "idm", "gekiso_index",
            "manbaken_index", "heads", "joho_index", "kyusha_index", "oi_index", "shiage_index"]

MODEL_PARAMS = dict(
    max_iter=300, max_depth=4, learning_rate=0.04, min_samples_leaf=200,
    l2_regularization=1.0, validation_fraction=0.15, n_iter_no_change=20, random_state=42,
)

# 基準複勝オッズ帯（"期待値"計算の分母である市場想定確率が、この帯によって
# モデルの予測確率と系統的にズレる＝ミスキャリブレーションが起きるため、
# 帯ごとに別々のisotonic回帰で較正する。2026-09-27導入。
ODDS_BINS = [0, 1.5, 2, 3, 5, 8, 15, 30, 10**9]
ODDS_LABELS = ["~1.5", "1.5-2", "2-3", "3-5", "5-8", "8-15", "15-30", "30+"]
MIN_CALIB_SAMPLES = 200


def load_env():
    env = {}
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v
    return env


def connect(env):
    return mysql.connector.connect(
        host=env.get("DB_HOST", "localhost"),
        port=int(env.get("DB_PORT", 3306)),
        user=env.get("DB_USER", "root"),
        password=env.get("DB_PASS", ""),
        database=env.get("DB_NAME", "racing"),
    )


RAW_FIELDS_SQL = """
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  TRIM(b.tds_code) AS tds_code, CAST(TRIM(b.distance) AS UNSIGNED) AS distance,
  CAST(TRIM(b.heads) AS UNSIGNED) AS heads,
  TRIM(k.ten_index_juni)   AS ten_juni_raw, TRIM(k.agari_index_juni) AS agari_juni_raw,
  TRIM(k.ichi_index_juni)  AS ichi_juni_raw, TRIM(k.goal_juni) AS goal_juni_raw,
  TRIM(k.idm) AS idm_raw, TRIM(k.gekiso_index) AS gekiso_raw, TRIM(k.manbaken_index) AS manbaken_raw,
  TRIM(k.kyakushitsu) AS kyakushitsu, TRIM(k.joshodo) AS joshodo,
  TRIM(k.kyori_tekisei) AS kyori_tekisei, TRIM(k.omo_tekisei) AS omo_tekisei,
  TRIM(k.dirt_tekisei) AS dirt_tekisei, TRIM(k.shiba_tekisei) AS shiba_tekisei,
  TRIM(k.chokyo_yajirushi) AS chokyo_yajirushi, TRIM(k.kyusha_hyoka) AS kyusha_hyoka,
  TRIM(k.blinker) AS blinker, TRIM(k.waku_num) AS waku_num,
  TRIM(k.joho_index) AS joho_raw, TRIM(k.kyusha_index) AS kyusha_idx_raw,
  TRIM(c.oi_index) AS oi_raw, TRIM(c.shiage_index) AS shiage_raw
"""

# T_CYB(調教印テーブル)は追切指数/仕上指数の取得元。LEFT JOINで欠損可(未計測馬あり)。
CYB_JOIN_SQL = """
    LEFT JOIN T_CYB c ON c.course_code=k.course_code AND c.year_code=k.year_code
      AND c.kai=k.kai AND c.day_code=k.day_code AND c.race_num=k.race_num AND c.uma_num=k.uma_num
"""


# 基準複勝オッズにはJRDBの「999.9」(データなし)のようなセンチネル値が稀に混入する
# （実データ確認: 309,024件中45件が999.9、1件が99.9。実際の複勝オッズはほぼ全て90倍未満）。
# これを実オッズとして扱うと期待値比率が桁違いに暴走するため、90倍以上はNULL(欠損)扱いにする。
FUKUSHO_ODDS_EXPR = """
  CASE WHEN TRIM(k.kijun_fukusho_odds)<>''
        AND CAST(TRIM(k.kijun_fukusho_odds) AS DECIMAL(6,1)) < 90
       THEN CAST(TRIM(k.kijun_fukusho_odds) AS DECIMAL(6,1)) ELSE NULL END
"""


def fetch_training_data(conn):
    """学習用: 結果が確定した過去レースのみ（T_SED INNER JOIN）"""
    sql = f"""
    SELECT {RAW_FIELDS_SQL},
      {FUKUSHO_ODDS_EXPR} AS fukusho_odds,
      CASE WHEN s.ijou_kubun IN ('0','') AND TRIM(s.order_of_finish)<>''
           THEN CAST(TRIM(s.order_of_finish) AS UNSIGNED) ELSE NULL END AS finish_order
    FROM T_KYI k
    INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code
      AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
    INNER JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code
      AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
    {CYB_JOIN_SQL}
    WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(b.`class`) <> 'A1'
      AND s.order_of_finish IS NOT NULL
    """
    return pd.read_sql(sql, conn)


def fetch_scoring_population(conn):
    """採点対象: 結果の有無を問わず全出走予定馬（T_SED不要、先読みなし）"""
    sql = f"""
    SELECT {RAW_FIELDS_SQL},
      {FUKUSHO_ODDS_EXPR} AS fukusho_odds
    FROM T_KYI k
    INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code
      AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
    {CYB_JOIN_SQL}
    WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(b.`class`) <> 'A1'
    """
    return pd.read_sql(sql, conn)


def build_features(df):
    def to_num(s):
        return pd.to_numeric(s, errors="coerce")

    df["ten_juni"] = to_num(df["ten_juni_raw"])
    df["agari_juni"] = to_num(df["agari_juni_raw"])
    df["ichi_juni"] = to_num(df["ichi_juni_raw"])
    df["goal_juni"] = to_num(df["goal_juni_raw"])
    df["idm"] = to_num(df["idm_raw"])
    df["gekiso_index"] = to_num(df["gekiso_raw"])
    df["manbaken_index"] = to_num(df["manbaken_raw"])
    df["heads"] = to_num(df["heads"])
    df["joho_index"] = to_num(df["joho_raw"])
    df["kyusha_index"] = to_num(df["kyusha_idx_raw"])
    df["oi_index"] = to_num(df["oi_raw"])
    df["shiage_index"] = to_num(df["shiage_raw"])

    for c in ["ten_juni", "agari_juni", "ichi_juni", "goal_juni"]:
        df[c] = df[c].fillna(99)
    df["idm"] = df["idm"].fillna(0)
    df["gekiso_index"] = df["gekiso_index"].fillna(0)
    df["manbaken_index"] = df["manbaken_index"].fillna(0)
    df["heads"] = df["heads"].fillna(df["heads"].median())
    # joho_indexの-1(非開示)は特別な意味を持つ値のため0で潰さず保持する。真の欠損のみ0埋め。
    df["joho_index"] = df["joho_index"].fillna(0)
    df["kyusha_index"] = df["kyusha_index"].fillna(0)
    df["oi_index"] = df["oi_index"].fillna(0)
    df["shiage_index"] = df["shiage_index"].fillna(0)

    for c in CAT_COLS:
        df[c] = df[c].fillna("NA").replace("", "NA")

    return df


def main():
    print(f"[開始] {datetime.now().isoformat()}")
    env = load_env()
    conn = connect(env)

    print("[Step1] 学習データ取得中（結果確定済みレースのみ）...")
    train_df = fetch_training_data(conn)
    train_df = build_features(train_df)
    train_df["place"] = (train_df["finish_order"] <= 3).astype(int)
    print(f"[Step1] 完了: 学習データ n={len(train_df)}")

    print("[Step2] 採点母集団取得中（出走予定の全馬、結果未確定含む）...")
    score_df = fetch_scoring_population(conn)
    score_df = build_features(score_df)
    score_df = score_df.dropna(subset=["fukusho_odds"])
    score_df = score_df[score_df["fukusho_odds"] > 0]
    print(f"[Step2] 完了: 採点対象 n={len(score_df)}")

    # カテゴリカルのエンコードは学習データで fit し、採点データに transform（一貫性を保つ）
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    enc.fit(train_df[CAT_COLS])

    def make_X(df):
        X_cat = pd.DataFrame(enc.transform(df[CAT_COLS]), columns=CAT_COLS, index=df.index)
        X = pd.concat([X_cat, df[NUM_COLS]], axis=1)
        return X

    cat_idx = list(range(len(CAT_COLS)))

    print("[Step3] モデル学習中（HistGradientBoostingClassifier）...")
    X_train = make_X(train_df)
    model = HistGradientBoostingClassifier(categorical_features=cat_idx, **MODEL_PARAMS)
    model.fit(X_train, train_df["place"])
    print("[Step3] 完了")

    # 2026-09-27追加: オッズ帯別isotonic較正
    # 生の予測確率は基準オッズが高い(人気薄の)馬ほど実測より過大評価する系統的な
    # ミスキャリブレーションがあり、これをそのまま(予測/市場)の期待値比率に使うと
    # 穴馬側で意味のない超高スコアが発生する。学習データのout-of-fold予測を使い、
    # オッズ帯ごとに別々のisotonic回帰で「較正後の確率」を作ってから期待値を計算する。
    print("[Step3b] オッズ帯別較正器を学習中（5-fold out-of-fold予測）...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_pred = cross_val_predict(
        HistGradientBoostingClassifier(categorical_features=cat_idx, **MODEL_PARAMS),
        X_train, train_df["place"], cv=kf, method="predict_proba", n_jobs=1,
    )[:, 1]
    train_calib_df = train_df.copy()
    train_calib_df["oof_pred"] = oof_pred
    train_calib_df = train_calib_df.dropna(subset=["fukusho_odds"])
    train_calib_df = train_calib_df[train_calib_df["fukusho_odds"] > 0]
    train_calib_df["odds_b"] = pd.cut(train_calib_df["fukusho_odds"], ODDS_BINS, labels=ODDS_LABELS, right=False)

    calibrators = {}
    for b in ODDS_LABELS:
        sub = train_calib_df[train_calib_df["odds_b"] == b]
        if len(sub) < MIN_CALIB_SAMPLES:
            continue
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(sub["oof_pred"], sub["place"])
        calibrators[b] = iso
    print(f"[Step3b] 完了: 較正器 {len(calibrators)}/{len(ODDS_LABELS)} 帯で作成")

    print("[Step4] 全馬を採点中...")
    X_score = make_X(score_df)
    score_df["pred_raw"] = model.predict_proba(X_score)[:, 1]
    score_df["odds_b"] = pd.cut(score_df["fukusho_odds"], ODDS_BINS, labels=ODDS_LABELS, right=False)

    calibrated = score_df["pred_raw"].copy()
    for b, iso in calibrators.items():
        mask = score_df["odds_b"] == b
        if mask.any():
            calibrated.loc[mask] = iso.predict(score_df.loc[mask, "pred_raw"])
    # isotonic回帰は帯内の学習サンプルが薄いと境界で厳密に0.0/1.0を出すことがある
    # （＝「複勝確率100%確定」という非現実的な断定）。実運用上あり得る範囲にクリップする。
    score_df["pred_place_prob"] = calibrated.clip(lower=0.01, upper=0.95)

    score_df["market_place_prob"] = 1.0 / score_df["fukusho_odds"]
    ev_raw = (score_df["pred_place_prob"] / score_df["market_place_prob"] - 1.0) * 100.0
    # 基準オッズ30倍以上の帯は較正器の学習サンプルが薄く、isotonic回帰が粗い階段状の
    # 出力になりやすい。それを極小の市場確率で割ると、個々の予測の粗さがそのまま
    # 桁違いのev_indexとして増幅される（実データで+1000%超えの値を複数確認）。
    # ウォークフォワード検証で ev_raw>=50 の集団(n=28)は複勝回収率27.1%と、
    # 検証済みの他の上位帯(20~50:82.3%等)より明確に悪く「最上位」として扱うのは誤り。
    # 単純に数値をクリップするだけでは同じ「最上位色」に分類され続けてしまうため、
    # 検証済みの範囲を超える行はスコア自体をNULL化し、表示上「対象外」に落とす
    # （厩指穴信頼グレード等、他の指数のn不足時の扱いと同じ方針）。
    UNRELIABLE_EV_THRESHOLD = 50.0
    score_df["ev_index"] = ev_raw.clip(lower=-100.0, upper=UNRELIABLE_EV_THRESHOLD)
    unreliable_mask = ev_raw >= UNRELIABLE_EV_THRESHOLD
    score_df.loc[unreliable_mask, "ev_index"] = None
    score_df.loc[unreliable_mask, "pred_place_prob"] = None
    print(f"[Step4] 検証範囲外(ev_raw>={UNRELIABLE_EV_THRESHOLD})につきスコア対象外: {int(unreliable_mask.sum())}件")

    # 対象外(NULL)行はレース内順位の計算対象から外れる(NaNのまま残る)ため、
    # DB書き込み時にNone変換する（Int64=pandasのnull許容整数型を使用）。
    race_key_cols = ["course_code", "year_code", "kai", "day_code", "race_num"]
    score_df["race_rank"] = score_df.groupby(race_key_cols)["pred_place_prob"].rank(ascending=False, method="first").astype("Int64")
    score_df["race_rank_from_last"] = score_df.groupby(race_key_cols)["pred_place_prob"].rank(ascending=True, method="first").astype("Int64")
    print(f"[Step4] 完了: n={len(score_df)}")

    model_version = date.today().isoformat()

    print("[Step5] DBへ書き込み中（別名テーブル作成→原子的RENAME）...")
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS T_EV_SCORE_NEW")
    cur.execute("""
        CREATE TABLE T_EV_SCORE_NEW LIKE T_EV_SCORE
    """)

    insert_sql = """
        INSERT INTO T_EV_SCORE_NEW
          (course_code, year_code, kai, day_code, race_num, uma_num,
           pred_place_prob, market_place_prob, ev_index, race_rank, race_rank_from_last, heads, model_version)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    rows = []
    for _, r in score_df.iterrows():
        rows.append((
            r["course_code"], r["year_code"], r["kai"], r["day_code"], r["race_num"], r["uma_num"],
            round(float(r["pred_place_prob"]), 4) if pd.notna(r["pred_place_prob"]) else None,
            round(float(r["market_place_prob"]), 4),
            round(float(r["ev_index"]), 2) if pd.notna(r["ev_index"]) else None,
            int(r["race_rank"]) if pd.notna(r["race_rank"]) else None,
            int(r["race_rank_from_last"]) if pd.notna(r["race_rank_from_last"]) else None,
            int(r["heads"]) if pd.notna(r["heads"]) else None, model_version,
        ))
    batch = 2000
    for i in range(0, len(rows), batch):
        cur.executemany(insert_sql, rows[i:i + batch])
    conn.commit()

    cur.execute("DROP TABLE IF EXISTS T_EV_SCORE_OLD")
    cur.execute("RENAME TABLE T_EV_SCORE TO T_EV_SCORE_OLD, T_EV_SCORE_NEW TO T_EV_SCORE")
    cur.execute("DROP TABLE T_EV_SCORE_OLD")
    conn.commit()
    print("[Step5] 完了（原子的差し替え済み）")

    cur.execute("SELECT COUNT(*) FROM T_EV_SCORE")
    (cnt,) = cur.fetchone()
    print(f"[完了] T_EV_SCORE 総件数: {cnt}")

    cur.close()
    conn.close()
    print(f"[終了] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
