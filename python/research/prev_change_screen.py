# -*- coding: utf-8 -*-
"""
前走からの変化の下見（研究用）。
今走: T_KYI（出走前データ）、前走: T_SED（前走成績キー = 血統登録番号8桁 + 前走年月日8桁 で結合）。
前走の情報はレース前に確定しているので先読みにはならない。馬体重の増減（今走の T_SED）は当日発表の情報として別扱い。
各要素を区分し、複勝回収率の「同じ年・同じオッズ帯の平均との差」を年ごと（2021-2026）に見る。
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, ".scratch", "prev_base.pkl")
CLS_ORDER = {"A1": 0, "A2": 0, "A3": 0, "05": 1, "10": 2, "16": 3, "OP": 4}


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
    cur = pd.read_sql(f"""
      SELECT b.ymd, CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, k.course_code,
             CAST(k.uma_num AS UNSIGNED) AS uma, TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist,
             TRIM(b.`class`) AS cls, TRIM(k.kishu_code) AS kishu_code, TRIM(k.futan_juryo) AS futan, TRIM(k.idm) AS idm,
             TRIM(k.kijun_odds) AS odds, TRIM(k.prev1_seiseki_key) AS p1key, TRIM(k.prev2_seiseki_key) AS p2key,
             TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou, TRIM(s.win) AS win, TRIM(s.place) AS place,
             TRIM(s.horse_weight) AS bw, TRIM(s.horse_weight_diff) AS bw_diff
      FROM T_KYI k JOIN T_BAC b ON {J('b')} JOIN T_SED s ON {J('s')} AND s.umaban=k.uma_num
      WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(b.`class`) <> 'A1'
    """, c)
    sed = pd.read_sql("""
      SELECT CONCAT(TRIM(blood_num), TRIM(ymd)) AS skey, TRIM(course_code) AS p_course, CAST(TRIM(distance) AS UNSIGNED) AS p_dist,
             TRIM(tds_code) AS p_tds, TRIM(`class`) AS p_cls, TRIM(heads) AS p_heads, TRIM(order_of_finish) AS p_fin,
             TRIM(ijou_kubun) AS p_ijou, TRIM(win_odds_rank) AS p_ninki, TRIM(win_diff) AS p_diff, TRIM(kinryou) AS p_kin,
             TRIM(jockey_code) AS p_jockey, TRIM(idm) AS p_idm, TRIM(furi) AS p_furi, TRIM(deokure) AS p_deokure,
             TRIM(corner_4) AS p_c4, TRIM(baba_cond) AS p_baba
      FROM T_SED
    """, c)
    c.close()
    sed = sed.drop_duplicates("skey")
    d = cur.merge(sed, left_on="p1key", right_on="skey", how="left")
    d.to_pickle(CACHE)
    return d


def num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.strip(), errors="coerce")


def prep(d):
    d = d.copy()
    for col in ("odds", "fin", "win", "place", "futan", "idm", "bw_diff", "p_heads", "p_fin", "p_ninki", "p_diff", "p_kin", "p_idm", "p_c4"):
        d[col] = num(d[col]).to_numpy()
    d = d[d.fin.notna() & (d.fin > 0) & d.odds.between(1, 999)].copy()
    normal = d.ijou.isin(["0", ""])
    d["win"] = np.where(normal, d.win.fillna(0), 0.0)
    d["place"] = np.where(normal, d.place.fillna(0), 0.0)
    d["y"] = d.ymd.str[:4].astype(int)
    d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
        d[p + "_x"] = d[p] - d[p + "_b"]
    has = d.skey.notna()
    d["前走あり"] = has
    # --- 前走の内容
    d["f_前走着順"] = np.select([~has, d.p_fin == 1, d.p_fin <= 3, d.p_fin <= 5, d.p_fin <= 9], ["前走なし", "1着", "2-3着", "4-5着", "6-9着"], default="10着以下")
    gap = d.p_ninki - d.p_fin   # プラス = 人気より上の着順
    d["f_人気−着順"] = np.select([~has | gap.isna(), gap >= 5, gap >= 2, gap >= -1, gap >= -4], ["NA", "人気より5以上上", "2〜4上", "ほぼ人気通り", "2〜4下"], default="人気より5以上下")
    d["f_1着との差"] = np.select([~has | d.p_diff.isna(), d.p_fin == 1, d.p_diff <= 2, d.p_diff <= 5, d.p_diff <= 10], ["NA", "勝ち", "0.2秒以内", "0.5秒以内", "1.0秒以内"], default="1.0秒超")
    d["f_前走不利"] = np.where(~has, "NA", np.where(d.p_furi.fillna("").isin(["", "0"]), "なし", "あり"))
    d["f_前走出遅れ"] = np.where(~has, "NA", np.where(d.p_deokure.fillna("").isin(["", "0"]), "なし", "あり"))
    c4r = d.p_c4 / d.p_heads
    d["f_前走4角位置"] = np.select([~has | c4r.isna(), c4r <= 0.2, c4r <= 0.5, c4r <= 0.8], ["NA", "前(上位20%)", "中団前", "中団後"], default="後方")
    idm_gap = d.idm - d.p_idm
    d["f_今回IDM−前走IDM"] = np.select([~has | idm_gap.isna(), idm_gap >= 5, idm_gap >= 1, idm_gap > -1, idm_gap > -5], ["NA", "+5以上", "+1〜5", "±1", "−1〜5"], default="−5以下")
    # --- 条件の変化
    dd = d.dist - d.p_dist
    d["f_距離変更"] = np.select([~has | dd.isna(), dd <= -400, dd < 0, dd == 0, dd < 400], ["NA", "400m以上短縮", "短縮", "同距離", "延長"], default="400m以上延長")
    d["f_芝ダ替わり"] = np.where(~has, "NA", np.where(d.tds == d.p_tds, "同じ", np.where(d.tds == "1", "ダ→芝", "芝→ダ")))
    co = d.cls.map(CLS_ORDER); po = d.p_cls.map(CLS_ORDER)
    d["f_クラス変化"] = np.select([~has | co.isna() | po.isna(), co > po, co < po], ["NA", "昇級", "降級"], default="同クラス")
    d["f_競馬場替わり"] = np.where(~has, "NA", np.where(d.course_code == d.p_course, "同じ", "替わり"))
    # --- 陣営の変化
    d["f_乗り替わり"] = np.where(~has | d.p_jockey.isna(), "NA", np.where(d.kishu_code == d.p_jockey, "継続騎乗", "乗り替わり"))
    kin = d.futan / 10 - d.p_kin / 10 if d.futan.median() > 100 else d.futan - d.p_kin
    d["kin_diff"] = kin
    d["f_斤量変化"] = np.select([~has | kin.isna(), kin <= -2, kin < 0, kin == 0, kin < 2], ["NA", "2kg以上減", "減", "同じ", "増"], default="2kg以上増")
    # --- 当日情報
    d["f_馬体重増減(当日)"] = np.select([d.bw_diff.isna(), d.bw_diff <= -10, d.bw_diff <= -4, d.bw_diff < 4, d.bw_diff < 10], ["NA", "−10kg以下", "−4〜−9", "±3", "+4〜+9"], default="+10kg以上")
    return d


FEATS = ["f_前走着順", "f_人気−着順", "f_1着との差", "f_前走不利", "f_前走出遅れ", "f_前走4角位置", "f_今回IDM−前走IDM",
         "f_距離変更", "f_芝ダ替わり", "f_クラス変化", "f_競馬場替わり", "f_乗り替わり", "f_斤量変化", "f_馬体重増減(当日)"]
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]

if __name__ == "__main__":
    raw = load()
    print("斤量の単位確認: 今走", raw.futan.head(3).tolist(), "前走", raw.p_kin.head(3).tolist(), "  1着との差の例", raw.p_diff.dropna().head(5).tolist())
    d = prep(raw)
    d.to_pickle(os.path.join(ROOT, ".scratch", "prev_prepped.pkl"))
    x = d[d.y >= 2021]
    print(f"対象 {len(x):,}頭（芝ダ・新馬除外、2021〜2026）、前走あり {x['前走あり'].mean()*100:.1f}%")
    for f in FEATS:
        t = x.groupby(f).agg(n=("place", "size"), 複勝=("place", "mean"), 差=("place_x", "mean"))
        for Y in YEARS:
            t[str(Y)] = x[x.y == Y].groupby(f).place_x.mean()
        s = np.sign(t[[str(Y) for Y in YEARS]])
        t["毎年同じ向き"] = (s == 1).all(axis=1) | (s == -1).all(axis=1)
        print(f"\n### {f[2:]}")
        print(t.round(1).to_string())
