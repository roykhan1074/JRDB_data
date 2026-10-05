# -*- coding: utf-8 -*-
"""
コース・芝ダ・距離・クラスごとの傾向（JRDBの元の要素）を測り、sc に加えると良くなるかを検証する（研究用）。

ユーザーの大原則（memory: feedback_user_key_principles）に従う:
- 毎年 Y について Y年より前のデータだけで傾向を推定し、Y年で答え合わせ（2022〜2026）。固定の探索/確認期間は使わない
- 「全期間（〜Y-1）」版と「直近3年（Y-3〜Y-1）」版を並べる
- 評価は同じ基準オッズ帯の平均との差。頑健性は当たり上位1%除外と信頼区間
- コース固有の傾向（例: 新潟芝1000の枠番）を拾うため、競馬場×芝ダ×距離まで見る。頭数が少ないほど上位区分へ寄せる（縮小推定）
- クラス別の差も見る

傾向の推定（要素 f の値 v ごと、目的変数 = 複勝払戻 − 同じ年・同じオッズ帯の平均）:
  全体        g0 = Σx / (n + K0)
  芝ダ×距離帯  g1 = (Σx + K1·g0) / (n + K1)
  コース       g2 = (Σx + K2·g1) / (n + K2)      コース = 競馬場×芝ダ×距離
  クラス差     gc = (Σx + KC·g1) / (n + KC) − g1  （芝ダ×距離帯×クラス）
  その馬の傾向点 T = Σ_f ( g2 + gc )
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, ".scratch", "tendency_base.pkl")
K0, K1, K2, KC = 300, 500, 500, 500
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]


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
    df = pd.read_sql(f"""
      SELECT b.ymd, k.course_code, CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid,
             CAST(k.uma_num AS UNSIGNED) AS uma, TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist,
             TRIM(b.`class`) AS cls, TRIM(k.waku_num) AS waku, TRIM(k.kyakushitsu) AS kya,
             TRIM(k.ten_index_juni) AS ten_j, TRIM(k.agari_index_juni) AS agari_j, TRIM(k.ichi_index_juni) AS ichi_j,
             TRIM(k.idm) AS idm, TRIM(k.kyori_tekisei) AS kyori_t, TRIM(k.shiba_tekisei) AS shiba_t, TRIM(k.dirt_tekisei) AS dirt_t,
             TRIM(u.chichi_keitou_code) AS chi, TRIM(u.hahachichi_keitou_code) AS hah,
             TRIM(k.kijun_odds) AS odds, TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou,
             TRIM(s.win) AS win, TRIM(s.place) AS place
      FROM T_KYI k
      JOIN T_BAC b ON {J('b')}
      JOIN T_SED s ON {J('s')} AND s.umaban=k.uma_num
      LEFT JOIN T_UKC u ON u.blood_reg_num = TRIM(k.blood_reg_num)
      WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(b.`class`) <> 'A1'
    """, c)
    c.close()
    df.to_pickle(CACHE)
    return df


def prep(df):
    d = df.copy()
    for col in ("odds", "fin", "win", "place", "idm"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d[d.fin.notna() & (d.fin > 0) & d.odds.between(1, 999)].copy()
    normal = d.ijou.isin(["0", ""])
    d["win"] = np.where(normal, d.win.fillna(0), 0.0)
    d["place"] = np.where(normal, d.place.fillna(0), 0.0)
    d["y"] = d.ymd.str[:4].astype(int)
    d["heads"] = d.groupby("rid")["uma"].transform("size")
    d["dband"] = pd.cut(d.dist, [0, 1400, 1800, 2200, 9999], labels=["~1400", "1401-1800", "1801-2200", "2201~"]).astype(str)
    d["seg1"] = d.tds + "_" + d.dband
    d["seg2"] = d.course_code + "_" + d.tds + "_" + d.dist.astype(str)
    d["segc"] = d.seg1 + "_" + d.cls
    d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
        d[p + "_x"] = d[p] - d[p + "_b"]

    def rank4(s):
        v = pd.to_numeric(s, errors="coerce")
        return np.select([v == 1, v.between(2, 3), v.between(4, 6), v >= 7], ["1", "2-3", "4-6", "7+"], default="NA")
    pos = d.uma / d.heads
    d["f_pos"] = np.select([pos <= 1 / 3, pos <= 2 / 3], ["内", "中"], default="外")
    d["f_waku"] = d.waku.replace("", "NA")
    d["f_kya"] = d.kya.replace("", "NA")
    d["f_kya_pos"] = d.f_kya + "×" + d.f_pos
    d["f_ten"] = rank4(d.ten_j); d["f_agari"] = rank4(d.agari_j); d["f_ichi"] = rank4(d.ichi_j)
    d["idm_r"] = d.groupby("rid")["idm"].rank(ascending=False, method="min")
    d["f_idm_r"] = rank4(d.idm_r)
    d["f_kyori"] = d.kyori_t.replace("", "NA")
    d["f_surf_t"] = np.where(d.tds == "1", d.shiba_t, d.dirt_t)
    d["f_surf_t"] = pd.Series(d["f_surf_t"]).fillna("").replace("", "NA").to_numpy()
    d["f_chi"] = d.chi.fillna("").replace("", "NA")
    d["f_hah"] = d.hah.fillna("").replace("", "NA")
    return d


FACTORS = ["f_waku", "f_pos", "f_kya", "f_kya_pos", "f_ten", "f_agari", "f_ichi", "f_idm_r", "f_kyori", "f_surf_t", "f_chi", "f_hah"]


def effects(tr, f, use_course=True, use_class=True):
    """学習データ tr から要素 f の効果表（g0, g1, g2, gc）を作る"""
    a0 = tr.groupby(f)["place_x"].agg(["sum", "size"])
    g0 = (a0["sum"] / (a0["size"] + K0)).rename("g0")
    a1 = tr.groupby(["seg1", f])["place_x"].agg(["sum", "size"]).reset_index().merge(g0, left_on=f, right_index=True, how="left")
    a1["g1"] = (a1["sum"] + K1 * a1["g0"].fillna(0)) / (a1["size"] + K1)
    out = {"g0": g0, "g1": a1[["seg1", f, "g1"]]}
    if use_course:
        a2 = tr.groupby(["seg2", "seg1", f])["place_x"].agg(["sum", "size"]).reset_index().merge(a1[["seg1", f, "g1"]], on=["seg1", f], how="left")
        a2["g2"] = (a2["sum"] + K2 * a2["g1"].fillna(0)) / (a2["size"] + K2)
        out["g2"] = a2[["seg2", f, "g2"]]
    if use_class:
        ac = tr.groupby(["segc", "seg1", f])["place_x"].agg(["sum", "size"]).reset_index().merge(a1[["seg1", f, "g1"]], on=["seg1", f], how="left")
        ac["gc"] = (ac["sum"] + KC * ac["g1"].fillna(0)) / (ac["size"] + KC) - ac["g1"].fillna(0)
        out["gc"] = ac[["segc", f, "gc"]]
    return out


def score(tr, te, use_course=True, use_class=True):
    T = np.zeros(len(te))
    for f in FACTORS:
        E = effects(tr, f, use_course, use_class)
        base = te[[f]].merge(E["g0"], left_on=f, right_index=True, how="left")["g0"].fillna(0).to_numpy()
        v1 = te[["seg1", f]].merge(E["g1"], on=["seg1", f], how="left")["g1"].to_numpy()
        val = np.where(np.isnan(v1), base, v1)
        if use_course:
            v2 = te[["seg2", f]].merge(E["g2"], on=["seg2", f], how="left")["g2"].to_numpy()
            val = np.where(np.isnan(v2), val, v2)
        if use_class:
            vc = te[["segc", f]].merge(E["gc"], on=["segc", f], how="left")["gc"].to_numpy()
            val = val + np.nan_to_num(vc)
        T += val
    return T


if __name__ == "__main__":
    d = prep(load())
    sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf3.json"))))[["rid", "uma", "sc", "s_idx", "s_oi", "s_goal", "s_down"]]
    d = d.merge(sc, on=["rid", "uma"], how="left")
    print(f"対象 {len(d):,}頭（芝ダ・新馬除外）、sc 付き {d.sc.notna().sum():,}頭")
    variants = {"T全期間(コース+クラス)": dict(win=None, use_course=True, use_class=True),
                "T直近3年(コース+クラス)": dict(win=3, use_course=True, use_class=True),
                "T全期間(芝ダ×距離のみ)": dict(win=None, use_course=False, use_class=False)}
    for lab, kw in variants.items():
        d[lab] = np.nan
        for Y in TEST_YEARS:
            lo = Y - kw["win"] if kw["win"] else 0
            tr = d[(d.y < Y) & (d.y >= lo)]
            te_mask = (d.y == Y).values
            d.loc[te_mask, lab] = score(tr, d[te_mask], kw["use_course"], kw["use_class"])
        print(f"{lab} 計算済み")
    d.to_pickle(os.path.join(ROOT, ".scratch", "tendency_scored.pkl"))

    # 例: 新潟芝1000（04_1_1000）の枠番の効果（2025年までのデータで推定）
    tr = d[d.y < 2026]
    E = effects(tr, "f_waku")
    ex = E["g2"][E["g2"].seg2 == "04_1_1000"].sort_values("f_waku")
    raw = tr[tr.seg2 == "04_1_1000"].groupby("f_waku").agg(n=("place", "size"), 複勝回収率=("place", "mean"), 同オッズ平均=("place_b", "mean"))
    print("\n例: 新潟芝1000 の枠番（2020〜2025年のデータ）")
    print(raw.join(ex.set_index("f_waku")["g2"].rename("推定効果(縮小後)")).round(1).to_string())
