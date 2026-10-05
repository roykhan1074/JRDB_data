# -*- coding: utf-8 -*-
"""
着順確率モデル（1着/2着以内/3着以内）の walk-forward 検証（研究用・DB書き込みなし）

CLAUDE.md の教訓に基づく設計:
- 先読み禁止: 年Yの予測には「Y年より前」のデータだけで学習したモデルを使う（年ごとに再学習）。
- 特徴量は全てレース前に確定している値（T_KYI/T_CYB/T_BAC）。全期間集計テーブル(T_*_FACTOR_AGG等)は使わない。
  騎手・調教師の成績は「その開催日より前」の累積のみから計算する（同日リーク防止）。
- 数字の意味を先に決める: 出力は確率。レース内で 1着確率の合計=1, 2着以内=2, 3着以内=3 に正規化する。
- 評価: 年ごとに LogLoss を市場（基準オッズ / 確定オッズ由来の確率）と比較し、較正（予測X%→実測X%か）を確認。

実行: python python/research/prob_wf.py
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
import mysql.connector
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, ".scratch", "prob_base.pkl")


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


NUM_RAW = [
    "idm", "kishu_index", "joho_index", "sogo_index", "ninki_index", "chokyo_index", "kyusha_index",
    "gekiso_index", "manbaken_index", "ten_index", "pace_index", "agari_index", "ichi_index",
    "ten_index_juni", "agari_index_juni", "ichi_index_juni", "goal_juni", "michunaka_juni", "gekiso_juni",
    "kijun_odds", "kijun_ninki", "kijun_fukusho_odds", "futan_juryo", "rotation",
    "kishu_renntai_rate", "kishu_tansho_rate", "kishu_3uchi_rate", "uma_start_index", "uma_okure_rate",
    "prize_earned", "nyukyu_nichi_mae", "waku_num", "uma_num",
]
CAT_RAW = ["kyakushitsu", "kyori_tekisei", "joshodo", "chokyo_yajirushi", "kyusha_hyoka", "omo_tekisei",
           "shiba_tekisei", "dirt_tekisei", "blinker", "minarai_kubun", "seibetsu_code",
           "in_idm", "in_joho", "in_sogo", "in_kishu", "in_kyusha", "in_chokyo"]


def fetch():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    env = load_env()
    conn = mysql.connector.connect(host=env["DB_HOST"], port=int(env["DB_PORT"]), user=env["DB_USER"],
                                   password=env["DB_PASS"], database=env["DB_NAME"])
    cols = ",".join(f"TRIM(k.{c}) AS {c}" for c in NUM_RAW + CAT_RAW)
    sql = f"""
    SELECT b.ymd, k.course_code, k.year_code, k.kai, k.day_code, k.race_num,
           TRIM(b.tds_code) AS tds_code, TRIM(b.distance) AS distance, TRIM(b.heads) AS heads,
           TRIM(b.`class`) AS cls, k.kishu_code, k.trainer_code,
           {cols},
           TRIM(c.oi_index) AS oi_index, TRIM(c.shiage_index) AS shiage_index,
           TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou,
           TRIM(s.win_odds) AS final_win_odds, TRIM(s.win) AS win_pay, TRIM(s.place) AS place_pay
    FROM T_KYI k
    JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai
      AND b.day_code=k.day_code AND b.race_num=k.race_num
    LEFT JOIN T_CYB c ON c.course_code=k.course_code AND c.year_code=k.year_code AND c.kai=k.kai
      AND c.day_code=k.day_code AND c.race_num=k.race_num AND c.uma_num=k.uma_num
    JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai
      AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
    WHERE TRIM(b.tds_code) IN ('1','2')
    """
    df = pd.read_sql(sql, conn)
    conn.close()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df


def prepare(df):
    df = df.copy()
    for c in NUM_RAW + ["oi_index", "shiage_index", "distance", "heads", "final_win_odds", "win_pay", "place_pay"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fin"] = pd.to_numeric(df["fin"], errors="coerce")
    # 取消・除外など（着順なし）は除外。中止・失格等は着外扱い（買った馬券は外れる）
    df = df[df["fin"].notna() & (df["fin"] > 0)].copy()
    df["race_id"] = df["course_code"] + df["year_code"] + df["kai"] + df["day_code"] + df["race_num"]
    df["year"] = df["ymd"].str[:4].astype(int)
    df["shinba"] = (df["cls"] == "A1").astype(int)
    # センチネル値（999.9等）は欠損扱い
    df.loc[df["kijun_odds"] >= 999, "kijun_odds"] = np.nan
    df.loc[df["kijun_fukusho_odds"] >= 90, "kijun_fukusho_odds"] = np.nan
    df.loc[df["final_win_odds"] <= 0, "final_win_odds"] = np.nan

    df["y_win"] = (df["fin"] == 1).astype(int)
    df["y_top2"] = (df["fin"] <= 2).astype(int)
    df["y_top3"] = (df["fin"] <= 3).astype(int)

    g = df.groupby("race_id")
    df["n_run"] = g["fin"].transform("size")
    # 市場の勝率（基準オッズ由来=レース前に入手可能 / 確定オッズ由来=参考の最強ベースライン）
    for src, col in [("kijun", "kijun_odds"), ("final", "final_win_odds")]:
        inv = 1.0 / df[col]
        df[f"mkt_{src}"] = inv / inv.groupby(df["race_id"]).transform("sum")
    # レース内相対特徴量
    for c in ["idm", "sogo_index", "kishu_index", "joho_index", "ten_index", "agari_index", "ichi_index",
              "chokyo_index", "kyusha_index", "oi_index", "shiage_index", "ninki_index"]:
        df[f"{c}_rk"] = g[c].rank(ascending=False, method="min")
        df[f"{c}_dmax"] = df[c] - g[c].transform("max")
        df[f"{c}_z"] = (df[c] - g[c].transform("mean")) / g[c].transform("std").replace(0, np.nan)
    df["mkt_kijun_rk"] = g["mkt_kijun"].rank(ascending=False, method="min")
    return df


def add_trailing(df):
    """騎手・調教師・騎手×調教師の成績を『その開催日より前』の累積だけで計算（同日リーク防止）。
    小サンプル対策として全体平均へ縮小推定（k=50）。"""
    df = df.sort_values(["ymd", "race_id"]).copy()
    prior_win = df["y_win"].mean()
    prior_top3 = df["y_top3"].mean()
    K = 50
    for key_name, keys in [("jk", ["kishu_code"]), ("tr", ["trainer_code"]), ("jt", ["kishu_code", "trainer_code"])]:
        daily = df.groupby(keys + ["ymd"]).agg(n=("y_win", "size"), w=("y_win", "sum"), t3=("y_top3", "sum")).reset_index()
        daily = daily.sort_values(keys + ["ymd"])
        gg = daily.groupby(keys)
        # 当日分を含めない累積（shiftで前日までにする）
        for c in ["n", "w", "t3"]:
            daily[f"c_{c}"] = gg[c].cumsum() - daily[c]
        daily[f"{key_name}_n"] = daily["c_n"]
        daily[f"{key_name}_win"] = (daily["c_w"] + K * prior_win) / (daily["c_n"] + K)
        daily[f"{key_name}_top3"] = (daily["c_t3"] + K * prior_top3) / (daily["c_n"] + K)
        df = df.merge(daily[keys + ["ymd", f"{key_name}_n", f"{key_name}_win", f"{key_name}_top3"]], on=keys + ["ymd"], how="left")
    return df


def feature_cols(df):
    base = [c for c in NUM_RAW if c not in ("uma_num",)] + ["oi_index", "shiage_index", "distance", "heads", "n_run", "shinba"]
    rel = [c for c in df.columns if c.endswith(("_rk", "_dmax", "_z"))]
    trail = [c for c in df.columns if c.startswith(("jk_", "tr_", "jt_"))]
    mkt = []
    MARKET = {"kijun_odds","kijun_ninki","kijun_fukusho_odds","ninki_index","ninki_index_rk","ninki_index_dmax","ninki_index_z","mkt_kijun_rk"}
    return [c for c in base + rel + trail + mkt if c not in MARKET], CAT_RAW + ["course_code", "tds_code"]


def normalize_in_race(df, col, total):
    """レース内で確率の合計を total(1/2/3) に揃える（各頭は最大1にクリップ）"""
    p = df[col].clip(1e-6, 1 - 1e-6)
    for _ in range(5):
        s = p.groupby(df["race_id"]).transform("sum")
        p = (p * (np.minimum(total, df["n_run"]) / s)).clip(upper=0.999)
    return p


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main():
    print("データ取得...")
    raw = fetch()
    df = prepare(raw)
    df = add_trailing(df)
    num, cat = feature_cols(df)
    for c in cat:
        df[c] = df[c].fillna("NA").replace("", "NA").astype("category")
    X_cols = num + cat
    print(f"n={len(df)} races={df['race_id'].nunique()} 特徴量={len(X_cols)}")

    results = []
    preds = []
    for Y in range(2022, 2027):
        tr = df[df["year"] < Y]
        te = df[df["year"] == Y].copy()
        for tgt, total in [("y_win", 1), ("y_top2", 2), ("y_top3", 3)]:
            m = HistGradientBoostingClassifier(max_iter=400, max_depth=6, learning_rate=0.05,
                                               min_samples_leaf=200, l2_regularization=1.0,
                                               categorical_features="from_dtype", random_state=42,
                                               early_stopping=True, validation_fraction=0.1, n_iter_no_change=30)
            m.fit(tr[X_cols], tr[tgt])
            te[f"p_{tgt}"] = m.predict_proba(te[X_cols])[:, 1]
            te[f"p_{tgt}"] = normalize_in_race(te, f"p_{tgt}", total)
        preds.append(te)
        ok = te["mkt_final"].notna() & te["mkt_kijun"].notna()
        t = te[ok]
        results.append(dict(
            year=Y, n=len(t),
            ll_model=logloss(t["y_win"], t["p_y_win"]),
            ll_kijun=logloss(t["y_win"], t["mkt_kijun"]),
            ll_final=logloss(t["y_win"], t["mkt_final"]),
        ))
        print(f"{Y}: 1着LogLoss モデル={results[-1]['ll_model']:.5f} 基準オッズ={results[-1]['ll_kijun']:.5f} 確定オッズ={results[-1]['ll_final']:.5f}")

    out = pd.concat(preds)
    out.to_pickle(os.path.join(ROOT, ".scratch", "prob_pred_fund.pkl"))

    print("\n較正（1着確率）: 予測帯ごとの実測勝率")
    out["pb"] = pd.cut(out["p_y_win"], [0, .02, .05, .1, .15, .2, .3, .4, .6, 1])
    print(out.groupby("pb", observed=True).agg(n=("y_win", "size"), pred=("p_y_win", "mean"), act=("y_win", "mean")).round(4))
    print("\n較正（3着以内確率）")
    out["pb3"] = pd.cut(out["p_y_top3"], [0, .05, .1, .2, .3, .4, .5, .6, .8, 1])
    print(out.groupby("pb3", observed=True).agg(n=("y_top3", "size"), pred=("p_y_top3", "mean"), act=("y_top3", "mean")).round(4))


if __name__ == "__main__":
    main()
