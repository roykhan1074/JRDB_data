# -*- coding: utf-8 -*-
"""
本命指数の改良案を walk-forward（毎年、直前の年までの全データで集計し直す）で比較する（研究用・DB書き込みなし）
対象: T_HONMEI_RACE_LOG（基準オッズ10倍未満・芝ダ・新馬除外）
手法は ex_improve_wf.py（EX指数）と同じ。ファクターは本命指数の14種。
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, ".scratch", "honmei_log.pkl")
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
ODDS_EDGES = [0, 1.5, 2, 2.5, 3, 4, 5, 7, 10]


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
      SELECT l.*, TRIM(k.kijun_odds) AS kijun_odds, TRIM(k.chokyo_yajirushi) AS chokyo_yajirushi
      FROM T_HONMEI_RACE_LOG l
      JOIN T_KYI k ON k.course_code=l.course_code AND k.year_code=l.year_code AND k.kai=l.kai
        AND k.day_code=l.day_code AND k.race_num=l.race_num AND k.uma_num=l.uma_num
      WHERE l.finish_order IS NOT NULL AND l.ijou_kubun IN ('0','')
    """, conn)
    conn.close()
    df.to_pickle(CACHE)
    return df


def num(s):
    return pd.to_numeric(s.astype(str).str.strip(), errors="coerce")


def prep(df):
    d = df.copy()
    d["year"] = d["ymd"].str[:4].astype(int)
    d["odds"] = num(d["kijun_odds"])
    d = d[(d.odds > 0) & (d.odds < 10)].copy()
    d["win"] = d["win_payout"].astype(float)
    d["place"] = d["place_payout"].astype(float)
    dist = num(d["distance"])
    d["dist_band"] = pd.cut(dist, [0, 1200, 1400, 1600, 2000, 2400, 9999], labels=["~1200", "1201~1400", "1401~1600", "1601~2000", "2001~2400", "2401~"]).astype(str)
    d["tds"] = d["tds_code"].str.strip()

    def rank4(c):
        v = num(d[c])
        return np.select([v == 1, v.between(2, 3), v.between(4, 6), v >= 7], ["1", "2~3", "4~6", "7~"], default="NA")
    d["f_ten"] = rank4("ten_index_juni"); d["f_agari"] = rank4("agari_index_juni")
    d["f_ichi"] = rank4("ichi_index_juni"); d["f_goal"] = rank4("goal_juni")
    d["f_combo"] = np.select([d.is_dual_top == 1, d.is_sen_oki == 1, d.is_hana_iki == 1, d.is_mid_chaser == 1],
                             ["dual_top", "sen_oki", "hana_iki", "mid_chaser"], default="other")
    idm = num(d["idm"])
    d["f_idm"] = np.select([idm.isna() | (idm <= 0), idm < 30, idm < 40, idm < 50, idm < 60, idm < 70], ["NA", "~30", "30~40", "40~50", "50~60", "60~70"], default="70~")
    jo = num(d["joho_index"])
    d["f_joho"] = np.select([jo.isna() | (jo < 0), jo < 30, jo < 50, jo < 70], ["NA", "~30", "30~50", "50~70"], default="70~")
    ky = num(d["kyusha_index"])
    d["f_kyu"] = np.select([ky.isna() | (ky <= 0), ky < 20, ky < 30, ky < 40], ["NA", "~20", "20~30", "30~40"], default="40~")
    d["f_chk_agg"] = d["chokyo_hyoka"].fillna("").astype(str).str.strip().replace("", "NA")
    d["f_chk_yaji"] = d["chokyo_yajirushi"].fillna("").astype(str).str.strip().replace("", "NA")
    for c, s in [("f_kya", "kyakushitsu"), ("f_jos", "joshodo"), ("f_kyo", "kyori_tekisei"),
                 ("f_chi", "chichi_keitou_code"), ("f_hah", "hahachichi_keitou_code")]:
        d[c] = d[s].fillna("").astype(str).str.strip().replace("", "NA")
    d["ob"] = pd.cut(d.odds, ODDS_EDGES, right=False).astype(str)
    return d


OVERALL = ["f_ten", "f_agari", "f_ichi", "f_goal", "f_combo", "f_idm", "f_joho", "f_kyu", "f_kya", "f_jos", "f_kyo", "f_chi", "f_hah"]
COURSE_FINE = ["f_ten", "f_agari", "f_ichi", "f_goal", "f_combo"]


def score_year(d, Y, target="win", shrink_k=0, excess=False, use_course=True, chk_mode="bug"):
    tr = d[d.year < Y].copy()
    te = d[d.year == Y].copy()
    tr["y"] = tr[target] - tr.groupby("ob")[target].transform("mean") if excess else tr[target]
    base = tr["y"].mean()

    def dev(keys, fac, min_n):
        g = tr.groupby(keys + [fac])["y"].agg(["mean", "size"]).reset_index()
        g = g[g["size"] >= min_n]
        if keys:
            b = tr.groupby(keys)["y"].agg(["mean", "size"]).reset_index().rename(columns={"mean": "bmean", "size": "bn"})
            b = b[b.bn >= 50]
            g = g.merge(b, on=keys, how="left"); g["bmean"] = g["bmean"].fillna(base)
        else:
            g["bmean"] = base
        g["dev"] = g["mean"] - g["bmean"]
        if shrink_k:
            g["dev"] = g["dev"] * g["size"] / (g["size"] + shrink_k)
        return g[keys + [fac, "dev"]]

    total = np.zeros(len(te))
    for f in OVERALL:
        od = dev([], f, 1).rename(columns={"dev": "od"})
        x = te[[f]].merge(od, on=f, how="left")["od"].fillna(0).to_numpy()
        if use_course and f in COURSE_FINE:
            cd = dev(["course_code", "tds", "dist_band"], f, 50).rename(columns={"dev": "cd"})
            c = te[["course_code", "tds", "dist_band", f]].merge(cd, on=["course_code", "tds", "dist_band", f], how="left")["cd"].to_numpy()
            x = np.where(np.isnan(c), x, c)
        elif use_course and f == "f_kya":
            cd = dev(["course_code", "tds"], f, 20).rename(columns={"dev": "cd"})
            c = te[["course_code", "tds", f]].merge(cd, on=["course_code", "tds", f], how="left")["cd"].to_numpy()
            x = np.where(np.isnan(c), x, c)
        elif use_course and f in ("f_chi", "f_hah"):
            g = tr.groupby(["tds", f])["y"].agg(["mean", "size"]).reset_index()
            g = g[g["size"] >= 20]; g["cd"] = g["mean"] - base
            if shrink_k: g["cd"] = g["cd"] * g["size"] / (g["size"] + shrink_k)
            c = te[["tds", f]].merge(g[["tds", f, "cd"]], on=["tds", f], how="left")["cd"].to_numpy()
            x = np.where(np.isnan(c), x, c)
        total += x
    if chk_mode != "drop":
        agg_key = "f_chk_agg" if chk_mode == "bug" else "f_chk_yaji"
        g = tr.groupby(agg_key)["y"].agg(["mean", "size"]).reset_index()
        g["dev"] = g["mean"] - base
        if shrink_k: g["dev"] = g["dev"] * g["size"] / (g["size"] + shrink_k)
        total += te["f_chk_yaji"].map(dict(zip(g[agg_key], g["dev"]))).fillna(0).to_numpy()
    te["score"] = total
    return te


def evaluate(d, label, **kw):
    t = pd.concat([score_year(d, Y, **kw) for Y in TEST_YEARS])
    for p in ("win", "place"):
        t[p + "_b"] = t.groupby(["year", "ob"])[p].transform("mean")
    t["pct"] = t.groupby("year")["score"].rank(pct=True)
    rows = []
    for name, lo, hi in [("上位5%", .95, 1.01), ("上位5-10%", .90, .95), ("上位10-25%", .75, .90), ("中位25-75%", .25, .75), ("下位25%", 0, .25)]:
        x = t[(t.pct > lo) & (t.pct <= hi)]
        r = {"案": label, "帯": name, "頭数": len(x)}
        for p, nm in (("win", "単勝"), ("place", "複勝")):
            r[nm + "差"] = x[p].mean() - x[p + "_b"].mean()
            for Y in TEST_YEARS:
                xy = x[x.year == Y]
                r[f"{nm}差{str(Y)[2:]}"] = xy[p].mean() - xy[p + "_b"].mean()
        for p, nm in (("win", "単勝"), ("place", "複勝")):
            s = x[p].sort_values(ascending=False)
            r[nm + "差_上位10除外"] = s.iloc[10:].sum() / len(x) - x[p + "_b"].mean()
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    d = prep(load())
    print(f"対象 {len(d):,}頭（基準オッズ10倍未満・芝ダ・新馬除外）")
    variants = [
        ("現行(単勝・コース別あり)", dict(target="win")),
        ("現行+調教照合修正", dict(target="win", chk_mode="fix")),
        ("改良1:複勝で集計", dict(target="place", chk_mode="fix")),
        ("改良2:複勝+縮小k=300", dict(target="place", shrink_k=300, chk_mode="fix")),
        ("改良3:複勝+オッズ帯補正+縮小", dict(target="place", shrink_k=300, excess=True, chk_mode="fix")),
        ("改良4:改良3+コース別なし", dict(target="place", shrink_k=300, excess=True, use_course=False, chk_mode="fix")),
        ("改良4単勝版", dict(target="win", shrink_k=300, excess=True, use_course=False, chk_mode="fix")),
    ]
    out = pd.concat([evaluate(d, lab, **kw) for lab, kw in variants])
    out.to_pickle(os.path.join(ROOT, ".scratch", "honmei_improve_result.pkl"))
    cols = ["案", "帯", "頭数", "単勝差", "単勝差_上位10除外", "複勝差", "複勝差_上位10除外", "複勝差22", "複勝差23", "複勝差24", "複勝差25", "複勝差26", "単勝差22", "単勝差23", "単勝差24", "単勝差25", "単勝差26"]
    print(out[cols].round(1).to_string(index=False))
