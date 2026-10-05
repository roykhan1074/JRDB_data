# -*- coding: utf-8 -*-
"""
厩指穴信頼（調教師単位の成績）の改良案を walk-forward で比較する（研究用・DB書き込みなし）
- 毎年 Y について、Y年より前の全データで調教師の成績を集計し直し、Y年の出走馬を採点
- 評価: 複勝回収率を「同じ年・同じ基準オッズ帯の馬の平均」と比べた差（pt）
- 頑健性: 払戻上位1%の的中を除いた差、ブートストラップ95%区間
対象: T_KYUSHA_RACE_LOG（芝ダ・新馬除外・完走）
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, ".scratch", "kyusha_log.pkl")
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
OB_EDGES = [1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100, 1000]


def load():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    e = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); e[k] = v
    conn = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
    df = pd.read_sql("""
      SELECT ymd, course_code, year_code, kai, day_code, race_num, trainer_code, kyusha_index, kijun_odds, tds_code, TRIM(class) AS cls,
             finish_order, win_payout, place_payout
      FROM T_KYUSHA_RACE_LOG
      WHERE finish_order IS NOT NULL AND TRIM(finish_order) <> '' AND ijou_kubun IN ('0','')
        AND TRIM(tds_code) IN ('1','2')
    """, conn)
    conn.close()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df


def prep(df):
    d = df.copy()
    d["year"] = d["ymd"].str[:4].astype(int)
    d["odds"] = pd.to_numeric(d["kijun_odds"], errors="coerce")
    d["ki"] = pd.to_numeric(d["kyusha_index"], errors="coerce")
    d = d[(d.cls != "A1") & d.odds.between(1, 999)].copy()
    d["win"] = d["win_payout"].astype(float)
    d["place"] = d["place_payout"].astype(float)
    d["ob"] = pd.cut(d.odds, OB_EDGES, right=False).astype(str)
    d["seg"] = (d.ki >= 0) & (d.odds >= 15)          # 現行の対象セグメント（厩舎指数≧0×基準オッズ15倍以上）
    d["ana"] = d.odds >= 10
    return d


def trainer_score(tr, mode, k=0, seg=None, recent=None, Y=None):
    """学習データから調教師ごとの点数を作る"""
    t = tr
    if recent:
        t = t[t.year >= Y - recent]
    if seg is not None:
        t = t[t[seg]]
    if mode == "raw":     # 現行: 複勝回収率そのもの
        g = t.groupby("trainer_code")["place"].agg(["mean", "size"])
        return g["mean"], g["size"]
    # 同じオッズ帯平均を上回った分（学習データ内のオッズ帯平均を引く）
    y = t["place"] - t.groupby("ob")["place"].transform("mean")
    g = y.groupby(t["trainer_code"]).agg(["mean", "size"])
    s = g["mean"] * g["size"] / (g["size"] + k) if k else g["mean"]
    return s, g["size"]


def run(d, label, mode, k=0, seg=None, recent=None, min_n=0, eval_pop="seg"):
    parts = []
    for Y in TEST_YEARS:
        tr, te = d[d.year < Y], d[d.year == Y].copy()
        s, n = trainer_score(tr, mode, k, seg, recent, Y)
        te["score"] = te.trainer_code.map(s)
        te["n"] = te.trainer_code.map(n).fillna(0)
        if min_n:
            te.loc[te.n < min_n, "score"] = np.nan
        parts.append(te)
    t = pd.concat(parts)
    t["place_b"] = t.groupby(["year", "ob"])["place"].transform("mean")   # 同年・同オッズ帯の全馬平均
    t["place_bt"] = t.groupby(["year", "ob"])["place"].transform(trim_mean)  # 同・的中上位1%除外後の平均
    t = t[t[eval_pop]] if eval_pop else t
    return t


def trim_mean(v):
    """的中の払戻上位1%を除いた平均（頭数はそのまま）"""
    hits = v[v > 0].sort_values(ascending=False)
    cut = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[cut:].sum() / len(v) if len(v) else np.nan


def summarize(t, label, bands):
    rows = []
    for name, mask in bands(t):
        x = t[mask]
        if len(x) == 0:
            continue
        r = {"案": label, "帯": name, "頭数": len(x), "複勝": x.place.mean(), "平均": x.place_b.mean()}
        r["差"] = r["複勝"] - r["平均"]
        for Y in TEST_YEARS:
            xy = x[x.year == Y]
            r[f"{str(Y)[2:]}"] = xy.place.mean() - xy.place_b.mean() if len(xy) else np.nan
        r["上位1%除外差"] = trim_mean(x.place) - x.place_bt.mean()
        diff = (x.place - x.place_b).to_numpy()
        rng = np.random.default_rng(0)
        bs = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(500)]
        r["95%下"], r["95%上"] = np.percentile(bs, [2.5, 97.5])
        rows.append(r)
    return pd.DataFrame(rows)


def grade_bands(t):   # 現行のS〜Fグレード（n>=20）
    p = t.score
    has = t.n >= 20
    return [("S 130+", has & (p >= 130)), ("A 110-130", has & p.between(110, 130, "left")),
            ("B 100-110", has & p.between(100, 110, "left")), ("C 90-100", has & p.between(90, 100, "left")),
            ("D 80-90", has & p.between(80, 90, "left")), ("E 60-80", has & p.between(60, 80, "left")),
            ("F <60", has & (p < 60)), ("n<20(無印)", ~has)]


def pct_bands(t):     # 年ごとの順位の割合で5帯（同点は乱数で並べる）
    rng = np.random.default_rng(1)
    sc = t.score.fillna(0) + rng.normal(0, 1e-9, len(t))
    pct = sc.groupby(t.year).rank(pct=True)
    return [("上位5%", pct > .95), ("上位5-10%", (pct > .90) & (pct <= .95)), ("上位10-25%", (pct > .75) & (pct <= .90)),
            ("中位25-75%", (pct > .25) & (pct <= .75)), ("下位25%", pct <= .25)]


if __name__ == "__main__":
    d = prep(load())
    print(f"対象 {len(d):,}頭（芝ダ・新馬除外、{d.year.min()}〜{d.year.max()}）、うち現行セグメント {d.seg.sum():,}頭")
    cols = ["案", "帯", "頭数", "複勝", "平均", "差", "22", "23", "24", "25", "26", "上位1%除外差", "95%下", "95%上"]
    out = []
    # 現行グレード（walk-forward 化した版）
    t = run(d, "現行", "raw", seg="seg", eval_pop="seg")
    out.append(summarize(t, "現行(複勝回収率でS〜F)", grade_bands))
    # 帯（割合）で横並び比較：評価母集団 = 現行セグメント
    variants = [
        ("現行(複勝回収率)", dict(mode="raw", seg="seg")),
        ("改良1:同オッズ差", dict(mode="ex", seg="seg")),
        ("改良2:同オッズ差+縮小k100", dict(mode="ex", seg="seg", k=100)),
        ("改良2b:縮小k300", dict(mode="ex", seg="seg", k=300)),
        ("改良3:全オッズで集計+k300", dict(mode="ex", seg=None, k=300)),
        ("改良3b:穴(10倍+)で集計+k300", dict(mode="ex", seg="ana", k=300)),
        ("改良4:直近3年+全オッズk300", dict(mode="ex", seg=None, k=300, recent=3)),
    ]
    for lab, kw in variants:
        out.append(summarize(run(d, lab, eval_pop="seg", **kw), lab, pct_bands))
    res = pd.concat(out)
    print("\n## 評価対象 = 現行セグメント（厩舎指数≧0×基準オッズ15倍以上）")
    print(res[cols].round(1).to_string(index=False))

    # 全馬・穴馬を評価対象にした場合（厩舎の上乗せが穴セグメント以外でも使えるか）
    out2 = []
    for pop in ("ana", None):
        for lab, kw in [("改良3:全オッズで集計+k300", dict(mode="ex", seg=None, k=300)),
                        ("改良4:直近3年+全オッズk300", dict(mode="ex", seg=None, k=300, recent=3))]:
            tt = run(d, lab, eval_pop=pop, **kw)
            out2.append(summarize(tt, f"{lab}／評価={'穴10倍+' if pop else '全馬'}", pct_bands))
    print("\n## 評価対象 = 穴(10倍以上) / 全馬")
    print(pd.concat(out2)[cols].round(1).to_string(index=False))
