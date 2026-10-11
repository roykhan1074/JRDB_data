# -*- coding: utf-8 -*-
"""
騎手指数の検証（研究用、DB書き込みなし）。
土台 = 騎手×芝ダの「複勝回収率の同オッズ帯平均との差」（縮小推定、平均=0へ寄せる）
補正 = 条件ごとの「騎手×芝ダ×条件」の値を土台へ寄せた上での、土台からの上下
walk-forward: 年 Y の値は Y 年より前のデータだけで集計。補正の採否と重みも毎年 Y 年より前の
              walk-forward 値で決め直す（2021年の値は2020年だけ、2022年の重みは2021年だけで決まる）。
出力: .scratch/kishu_wf.pkl（各馬の指数）
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, ".scratch", "kishu_base.pkl")
K = 300          # 縮小推定の強さ
YEARS_F = [2021, 2022, 2023, 2024, 2025, 2026]   # walk-forward 値を作る年
YEARS = [2022, 2023, 2024, 2025, 2026]           # 評価する年


def load():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    e = {}
    for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        l = l.strip()
        if l and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); e[k] = v
    c = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
    J = lambda a: f"{a}.course_code=k.course_code AND {a}.year_code=k.year_code AND {a}.kai=k.kai AND {a}.day_code=k.day_code AND {a}.race_num=k.race_num"
    d = pd.read_sql(f"""
      SELECT b.ymd, CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, CAST(k.uma_num AS UNSIGNED) AS uma,
             k.course_code AS cc, TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist, TRIM(b.`class`) AS cls,
             CAST(TRIM(b.heads) AS UNSIGNED) AS heads,
             TRIM(k.kishu_code) AS kc, TRIM(k.kishu_name) AS kname, TRIM(k.trainer_code) AS tc, TRIM(k.umanushi_name) AS own,
             TRIM(k.blood_reg_num) AS blood, TRIM(k.kijun_odds) AS odds, TRIM(k.kyakushitsu) AS kya,
             TRIM(k.ten_index_juni) AS ten_r, TRIM(k.agari_index_juni) AS agari_r, TRIM(k.waku_num) AS waku,
             TRIM(k.minarai_kubun) AS minarai, TRIM(k.kishu_index) AS jrdb_kishu, TRIM(k.prev1_seiseki_key) AS p1key,
             TRIM(u.chichi_uma_name) AS sire, TRIM(u.chichi_keitou_code) AS keitou,
             TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou, TRIM(s.win) AS win, TRIM(s.place) AS place,
             TRIM(s.baba_cond) AS baba
      FROM T_KYI k JOIN T_BAC b ON {J('b')} JOIN T_SED s ON {J('s')} AND s.umaban=k.uma_num
      LEFT JOIN T_UKC u ON u.blood_reg_num = TRIM(k.blood_reg_num)
      WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(k.kishu_code) <> ''
    """, c)
    sed = pd.read_sql("SELECT CONCAT(TRIM(blood_num), TRIM(ymd)) AS skey, TRIM(jockey_code) AS p_kc FROM T_SED", c)
    c.close()
    d = d.merge(sed.drop_duplicates("skey"), left_on="p1key", right_on="skey", how="left").drop(columns="skey")
    d.to_pickle(CACHE)
    return d


def prep(d):
    d = d.copy()
    for col in ("odds", "fin", "win", "place", "ten_r", "agari_r", "waku", "jrdb_kishu"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d[d.fin.notna() & (d.fin > 0) & d.odds.between(1, 999)].copy()
    normal = d.ijou.isin(["0", ""])
    d["win"] = np.where(normal, d.win.fillna(0), 0.0)
    d["place"] = np.where(normal, d.place.fillna(0), 0.0)
    d["y"] = d.ymd.str[:4].astype(int)
    d["date"] = pd.to_datetime(d.ymd)
    d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
        d[p + "_x"] = d[p] - d[p + "_b"]
    # --- 条件（すべてレース前に分かる値。馬場だけは当日の発表値）
    d["db"] = pd.cut(d.dist, [0, 1400, 1800, 2200, 9999], labels=["~1400", "~1800", "~2200", "2201~"]).astype(str)
    d["c_コース"] = d.cc + "_" + d.db
    d["c_距離帯"] = d.db
    d["c_クラス"] = d.cls.replace({"A2": "A3"})
    d["c_人気帯"] = pd.cut(d.odds, [1, 3, 7, 15, 50, 1000], right=False, labels=["~3", "3~7", "7~15", "15~50", "50~"]).astype(str)
    d["c_脚質"] = d.kya.replace("", "不明")
    rb = lambda r: np.select([r.isna(), r == 1, r <= 3, r <= 6], ["不明", "1", "2-3", "4-6"], default="7~")
    d["c_テン順位"] = rb(d.ten_r); d["c_上がり順位"] = rb(d.agari_r)
    m = d.date.dt.month
    d["c_季節"] = np.select([m.isin([12, 1, 2]), m.isin([3, 4, 5]), m.isin([6, 7, 8])], ["冬", "春", "夏"], default="秋")
    d["c_馬場"] = np.where(d.baba.fillna("").str[:1] == "1", "良", np.where(d.baba.fillna("") == "", "不明", "稍重以上"))
    d["c_父系統"] = d.keitou.fillna("").replace("", "不明")
    d["c_種牡馬"] = d.sire.fillna("").replace("", "不明")
    d["c_調教師"] = d.tc
    d["c_馬主"] = d.own
    d["c_枠"] = np.select([d.waku <= 3, d.waku <= 5], ["内1-3", "中4-5"], default="外6-8")
    d["c_頭数"] = pd.cut(d.heads, [0, 12, 15, 99], labels=["~12", "13-15", "16~"]).astype(str)
    # 遠征: 開催場の地域（東・西・北海道）
    d["region"] = d.cc.map(lambda x: "北" if x in ("01", "02") else ("東" if x in ("03", "04", "05", "06") else "西"))
    # この馬との関係（DB上の過去騎乗で判定）
    d = d.sort_values(["ymd", "rid", "uma"]).reset_index(drop=True)
    ridden = d.groupby(["blood", "kc"]).cumcount() > 0
    d["c_関係"] = np.select([d.p_kc.isna(), d.p_kc == d.kc, ridden], ["前走不明", "継続騎乗", "乗り戻り"], default="テン乗り")
    return d


COND = ["c_コース", "c_距離帯", "c_クラス", "c_人気帯", "c_脚質", "c_テン順位", "c_上がり順位", "c_季節", "c_馬場",
        "c_父系統", "c_種牡馬", "c_調教師", "c_馬主", "c_枠", "c_頭数", "c_遠征", "c_関係"]
NUM = ["n_乗り替わり差", "n_直近90日"]


def shrink0(tr, keys, tgt):
    g = tr.groupby(keys)[tgt].agg(["sum", "count"])
    return (g["sum"] / (g["count"] + K)).rename("v")


def recent90(d, tgt):
    """騎手ごとの直近90日（当日を含まない）の同オッズ平均との差、縮小 k=100"""
    daily = d.groupby(["kc", "date"])[tgt].agg(["sum", "count"]).reset_index().sort_values(["kc", "date"])
    out = []
    for kc, g in daily.groupby("kc", sort=False):
        g = g.set_index("date")
        r = g[["sum", "count"]].rolling("90D", closed="left").sum().fillna(0)
        r["kc"] = kc
        out.append(r.reset_index())
    r = pd.concat(out)
    r["v"] = r["sum"] / (r["count"] + 100)
    return d[["kc", "date"]].merge(r[["kc", "date", "v"]], on=["kc", "date"], how="left")["v"].fillna(0).to_numpy()


def build_features(d, tgt):
    F = pd.DataFrame(index=d.index)
    F["base"] = 0.0
    for c in COND + NUM:
        F[c] = 0.0
    d["c_遠征"] = "不明"   # 各年の値はその年より前のデータで決める（2020年は判定不能）
    for Y in YEARS_F:
        tr = d[d.y < Y]; m = d.y == Y
        te = d[m]
        base = shrink0(tr, ["kc", "tds"], tgt)
        bmap = te.set_index(["kc", "tds"]).index.map(base).fillna(0).to_numpy()
        F.loc[m, "base"] = bmap
        # 遠征（その年より前で最も多く乗った地域と違う地域か）
        main = tr.groupby(["kc", "region"]).size().reset_index(name="n").sort_values("n").drop_duplicates("kc", keep="last").set_index("kc").region
        mr = te.kc.map(main)
        d.loc[m, "c_遠征"] = np.select([mr.isna(), mr == te.region], ["不明", "地元"], default="遠征")
        te = d[m]
        for c in COND:
            g = tr.groupby(["kc", "tds", c])[tgt].agg(["sum", "count"]).reset_index()
            g["par"] = g.set_index(["kc", "tds"]).index.map(base).fillna(0).to_numpy()
            g["dev"] = (g["sum"] + K * g.par) / (g["count"] + K) - g.par
            dv = te[["kc", "tds", c]].merge(g[["kc", "tds", c, "dev"]], on=["kc", "tds", c], how="left")["dev"].fillna(0).to_numpy()
            F.loc[m, c] = dv
        # 乗り替わり差: 今回騎手の土台 − 前走騎手の土台（騎手×芝ダ）
        pk = te.set_index(["p_kc", "tds"]).index.map(base).fillna(0).to_numpy()
        F.loc[m, "n_乗り替わり差"] = np.where(te.p_kc.notna() & (te.p_kc != te.kc), bmap - pk, 0.0)
    F["n_直近90日"] = recent90(d, tgt)
    # 直近90日は「長期の土台からの上下」として使う
    F["n_直近90日"] = F["n_直近90日"] - F["base"]
    return F


def fit_weights(F, d, cols, tgt, years_tr, lam=1.0):
    m = d.y.isin(years_tr).values
    X = np.column_stack([np.ones(m.sum())] + [F.loc[m, c].to_numpy() for c in cols])
    y = d.loc[m, tgt].to_numpy()
    sd = X[:, 1:].std(axis=0); sd[sd == 0] = 1
    Xs = X.copy(); Xs[:, 1:] /= sd
    A = Xs.T @ Xs + lam * len(y) * 1e-4 * np.diag([0] + [1] * len(cols))
    b = np.linalg.solve(A, Xs.T @ y)
    resid = y - Xs @ b
    s2 = resid.var()
    cov = s2 * np.linalg.inv(A)
    t = b / np.sqrt(np.diag(cov))
    return b[1:] / sd, t[1:]


def band_table(t, col, tgt_sfx="", label=""):
    t = t.copy()
    t["q"] = t.groupby("y")[col].transform(lambda s: pd.qcut(s.rank(method="first"), [0, .25, .5, .75, .95, 1],
                                                              labels=["下位25%", "25-50%", "50-75%", "75-95%", "上位5%"]))
    # 公平な集中度チェック: 年×オッズ帯ごとに、当たり（払戻>0）の上位1%を母集団全体から除外し、平均も除外後で取り直す
    for p in ("win", "place"):
        hit = t[p] > 0
        thr = t[hit].groupby(["y", "ob"])[p].transform(lambda s: s.quantile(0.99))
        t[p + "_keep"] = True
        t.loc[thr.index[t.loc[thr.index, p] > thr], p + "_keep"] = False
        kept = t[t[p + "_keep"]]
        t[p + "_b2"] = t.set_index(["y", "ob"]).index.map(kept.groupby(["y", "ob"])[p].mean()).to_numpy()
    rows = []
    for q, g in t.groupby("q", observed=True):
        r = {"区分": q, "頭数": len(g)}
        for p, lab in (("win", "単"), ("place", "複")):
            r[f"{lab}勝回収"] = g[p].mean(); r[f"{lab}平均"] = g[p + "_b"].mean()
            r[f"{lab}差"] = r[f"{lab}勝回収"] - r[f"{lab}平均"]
            gk = g[g[p + "_keep"]]
            r[f"{lab}差_除外後"] = gk[p].mean() - gk[p + "_b2"].mean()
            yr = g.groupby("y").apply(lambda z: z[p].mean() - z[p + "_b"].mean())
            r[f"{lab}差_年別"] = " / ".join(f"{v:+.1f}" for v in yr.values)
        rows.append(r)
    out = pd.DataFrame(rows).set_index("区分")
    print(f"\n### {label}")
    print(out[["頭数", "単勝回収", "単平均", "単差", "単差_除外後", "複勝回収", "複平均", "複差", "複差_除外後"]].round(1).to_string())
    print(out[["単差_年別", "複差_年別"]].to_string())
    return t


if __name__ == "__main__":
    d = prep(load())
    print("rows", len(d), d.y.min(), d.y.max())
    TGT = "place_x"
    F = build_features(d, TGT)

    # ===== 1. 補正を1つずつ: 土台に1つだけ加えたときの係数（年別に、その年のデータで推定）
    print("\n## 1. 補正の単独の効き（土台＋その補正だけで、各年のデータで係数を推定。1=集計どおりに効く、0=効かない）")
    rows = []
    for c in COND + NUM:
        r = {"補正": c[2:]}
        for Y in YEARS:
            w, t = fit_weights(F, d, ["base", c], TGT, [Y])
            r[str(Y)] = w[1]
        w, t = fit_weights(F, d, ["base", c], TGT, YEARS)
        r["5年まとめ"] = w[1]; r["t値"] = t[1]
        # 得意(上位10%) vs 苦手(下位10%) の複勝差（5年）
        e = d.y.isin(YEARS) & (F[c] != 0)
        v = F.loc[e, c]; lo, hi = v.quantile(0.1), v.quantile(0.9)
        r["得意10%の差"] = d.loc[e & (F[c] >= hi), TGT].mean(); r["苦手10%の差"] = d.loc[e & (F[c] <= lo), TGT].mean()
        rows.append(r)
    print(pd.DataFrame(rows).set_index("補正").round(2).to_string())

    # ===== 2. 指数 = 土台＋採用した補正（採否と重みは毎年その年より前の walk-forward 値で決める）
    print("\n## 2. 指数の組み立て（毎年選び直し）")
    d["idx_base"] = F["base"]
    d["idx"] = np.nan
    for Y in YEARS:
        prev = [y for y in YEARS_F if y < Y]
        sel = []
        for c in COND + NUM:
            w, t = fit_weights(F, d, ["base", c], TGT, prev)
            if w[1] > 0 and t[1] >= 2.0:
                sel.append(c)
        cols = ["base"] + sel
        w, t = fit_weights(F, d, cols, TGT, prev)
        m = d.y == Y
        d.loc[m, "idx"] = sum(w[i] * F.loc[m, c] for i, c in enumerate(cols))
        print(f"  {Y}: 採用 " + ", ".join(f"{c[2:] if c != 'base' else '土台'}×{w[i]:.2f}" for i, c in enumerate(cols)))
    for c in COND + NUM:
        d["f_" + c] = F[c]
    ev = d[d.y.isin(YEARS)].copy()
    band_table(ev, "idx_base", label="土台のみ（騎手×芝ダ）")
    band_table(ev, "idx", label="騎手指数（土台＋採用した補正）")
    ev2 = ev[ev.jrdb_kishu.notna()]
    band_table(ev2, "jrdb_kishu", label="参考: JRDBの騎手指数（T_KYI.kishu_index）")
    ana = ev[ev.odds >= 10]
    band_table(ana, "idx", label="穴馬（基準10倍以上）だけで見た騎手指数")
    d.to_pickle(os.path.join(ROOT, ".scratch", "kishu_wf.pkl"))
