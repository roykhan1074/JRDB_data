# -*- coding: utf-8 -*-
"""
初ブリンカーの仮説を広く検証する（研究用・DB書き込みなし）
- 仮説ごとに「初装着×条件」の単勝・複勝回収率を、同じ年・同じ基準オッズ帯の全馬平均と比べる
- 同じ条件のブリンカーなしの馬とも比べ、ブリンカー特有の上乗せかを見る
- 頑健性: 年別の向き、ブートストラップ95%区間、的中の払戻上位5%を除いた差（比較基準も同じ割合で除く）
- 最後に、単独条件と2条件の組み合わせから毎年その年より前のデータだけで選び直す walk-forward
対象: 芝ダ・新馬除外・完走（T_KYI×T_BAC×T_SED）、2020〜2026
"""
import sys, io, os, warnings, itertools
warnings.filterwarnings("ignore")
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 1000)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, ".scratch", "blinker_wide.pkl")
OB_EDGES = [1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100, 1000]
YEARS = list(range(2020, 2027))
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
COURSE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京", "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


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
      SELECT b.ymd, k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num, k.blood_reg_num,
             k.blinker, k.kijun_odds, k.kijun_ninki, b.tds_code, TRIM(b.distance) AS distance, TRIM(b.class) AS cls,
             b.syubetsu, b.heads, b.course_abcd,
             k.kyakushitsu, k.seibetsu_code, k.waku_num, k.rotation, k.idm, k.ten_index_juni, k.agari_index_juni,
             k.ichi_index_juni, k.pace_yoso, k.gekiso_index, k.manbaken_index, k.kishu_renntai_rate, k.minarai_kubun,
             k.futan_juryo, k.joho_index, k.chokyo_yajirushi, k.kyusha_hyoka, k.trainer_code, k.kishu_code, k.uma_start_index, k.uma_okure_rate,
             (k.prev1_seiseki_key IS NOT NULL AND TRIM(k.prev1_seiseki_key)<>'') + (k.prev2_seiseki_key IS NOT NULL AND TRIM(k.prev2_seiseki_key)<>'')
             + (k.prev3_seiseki_key IS NOT NULL AND TRIM(k.prev3_seiseki_key)<>'') + (k.prev4_seiseki_key IS NOT NULL AND TRIM(k.prev4_seiseki_key)<>'')
             + (k.prev5_seiseki_key IS NOT NULL AND TRIM(k.prev5_seiseki_key)<>'') AS career5,
             k.idm_rank_all, k.ten_rank_all,
             s.order_of_finish AS fin, s.win AS win_pay, s.place AS place_pay,
             p.order_of_finish AS prev_fin, p.heads AS prev_heads, p.win_diff AS prev_diff, p.tds_code AS prev_tds,
             TRIM(p.distance) AS prev_dist, p.win_odds_rank AS prev_ninki, p.deokure AS prev_deokure, p.corner_4 AS prev_c4,
             p.furi AS prev_furi, p.jockey_code AS prev_jockey, p.race_kyakushitsu AS prev_kyaku, p.class AS prev_cls
      FROM (SELECT k0.*,
              RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY CAST(NULLIF(TRIM(idm),'') AS DECIMAL(6,1)) DESC) AS idm_rank_all,
              RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY CAST(NULLIF(TRIM(ten_index),'') AS DECIMAL(6,1)) DESC) AS ten_rank_all
            FROM T_KYI k0) k
      JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
      JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code
                  AND s.race_num=k.race_num AND s.umaban=k.uma_num AND s.ijou_kubun IN ('0','')
      LEFT JOIN T_SED p ON p.blood_num = LEFT(k.prev1_seiseki_key, 8) AND p.ymd = SUBSTRING(k.prev1_seiseki_key, 9, 8)
      WHERE b.tds_code IN ('1','2') AND TRIM(b.class) <> 'A1'
    """, conn)
    conn.close()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_pickle(CACHE)
    return df


def num(s):
    return pd.to_numeric(s, errors="coerce")


def trim_mean(v, p):
    """的中の払戻上位 p を除いた平均（頭数はそのまま）"""
    v = pd.Series(v)
    hits = v[v > 0].sort_values(ascending=False)
    cut = int(np.ceil(len(hits) * p))
    return hits.iloc[cut:].sum() / len(v) if len(v) else np.nan


def cut(s, edges, labels):
    return pd.cut(s, edges, right=False, labels=labels).astype(str)


def prep(df):
    d = df.copy()
    d["year"] = d.ymd.str[:4].astype(int)
    d["race"] = d.course_code + d.year_code + d.kai + d.day_code + d.race_num
    d["odds"] = num(d.kijun_odds)
    d = d[d.odds.between(1, 999)].copy()
    d["win"] = num(d.win_pay).fillna(0)
    d["place"] = num(d.place_pay).fillna(0)
    d["ob"] = pd.cut(d.odds, OB_EDGES, right=False).astype(str)
    d["bl"] = d.blinker.fillna("").str.strip()
    for c in ("win", "place"):
        g = d.groupby(["year", "ob"])[c]
        d[c + "_b"] = g.transform("mean")
        d[c + "_b5"] = g.transform(lambda v: trim_mean(v, .05))
        d[c + "_x"] = d[c] - d[c + "_b"]

    H = {}   # 仮説: 名前 -> 区分の Series
    age = d.year - (2000 + num(d.blood_reg_num.str[:2]))
    H["年齢"] = cut(age, [2, 3, 4, 5, 99], ["2歳", "3歳", "4歳", "5歳以上"])
    H["年齢×時期"] = np.where(age == 3, np.where(num(d.ymd.str[4:6]) <= 6, "3歳1-6月", "3歳7-12月"), H["年齢"])
    H["クラス"] = d.cls.map({"A3": "未勝利", "05": "1勝", "10": "2勝", "16": "3勝", "OP": "OP"}).fillna("他")
    H["芝ダ"] = d.tds_code.str.strip().map({"1": "芝", "2": "ダ"})
    dist = num(d.distance)
    H["距離"] = cut(dist, [0, 1400, 1800, 2200, 9999], ["~1300", "1400-1700", "1800-2100", "2200~"])
    H["芝ダ×距離"] = H["芝ダ"] + H["距離"]
    waku = num(d.waku_num)
    H["枠"] = waku.astype("Int64").astype(str)
    H["枠(内中外)"] = cut(waku, [1, 4, 6, 9], ["内1-3", "中4-5", "外6-8"])
    H["芝ダ×枠(内中外)"] = H["芝ダ"] + H["枠(内中外)"]
    heads = num(d.heads); uma = num(d.uma_num)
    H["大外"] = np.where(uma == heads, "大外", "大外以外")
    H["頭数"] = cut(heads, [1, 11, 15, 99], ["~10頭", "11-14頭", "15頭~"])
    H["性別"] = d.seibetsu_code.str.strip().map({"1": "牡", "2": "牝", "3": "セン"})
    H["脚質(JRDB)"] = d.kyakushitsu.str.strip().map({"1": "逃げ", "2": "先行", "3": "差し", "4": "追込", "5": "好位差", "6": "自在"}).fillna("他")
    ten = num(d.ten_rank_all).where(num(d.idm).notna())
    rk = lambda r: cut(r, [1, 2, 4, 7, 99], ["1位", "2-3位", "4-6位", "7位~"])
    H["テン指数順位"] = rk(ten)
    H["上がり指数順位"] = rk(num(d.agari_index_juni).replace(0, np.nan))
    H["位置指数順位"] = rk(num(d.ichi_index_juni).replace(0, np.nan))
    H["IDM順位"] = rk(num(d.idm_rank_all).where(num(d.idm).notna()))
    H["基準人気"] = cut(num(d.kijun_ninki), [1, 2, 4, 7, 10, 99], ["1人気", "2-3人気", "4-6人気", "7-9人気", "10人気~"])
    H["基準オッズ"] = d.ob
    H["人気−IDM順位"] = cut(num(d.kijun_ninki) - num(d.idm_rank_all), [-99, -2, 1, 3, 99], ["<=-3", "-2~0", "1-2", ">=3"])
    H["キャリア"] = d.career5.astype(int).map({0: "0", 1: "1戦", 2: "2戦", 3: "3戦", 4: "4戦", 5: "5戦以上"})
    rot = num(d.rotation)
    H["間隔"] = cut(rot, [0, 3, 5, 9, 13, 999], ["1-2週", "3-4週", "5-8週", "9-12週", "13週~"])
    pf = num(d.prev_fin)
    H["前走着順"] = cut(pf, [1, 4, 6, 10, 99], ["1-3着", "4-5着", "6-9着", "10着~"])
    H["前走着差"] = cut(num(d.prev_diff), [-99, 0.5, 1.0, 2.0, 99], ["0.5秒内", "0.5-1.0", "1.0-2.0", "2.0秒~"])
    pn = num(d.prev_ninki)
    H["前走人気−着順"] = cut(pn - pf, [-99, -5, 0, 99], ["人気より5着以上負け", "人気より0-4着負け", "人気以上"])
    H["前走出遅れ"] = np.where(num(d.prev_deokure).fillna(0) > 0, "あり", "なし")
    c4 = num(d.prev_c4); ph = num(d.prev_heads)
    H["前走4角位置"] = cut(c4 / ph, [0, .34, .67, 9], ["前1/3", "中", "後1/3"])
    H["前走不利"] = np.where(num(d.prev_furi).fillna(0) > 0, "あり", "なし")
    H["前走実脚質"] = d.prev_kyaku.str.strip().map({"1": "逃げ", "2": "先行", "3": "差し", "4": "追込"}).fillna("他")
    pdist = num(d.prev_dist)
    H["距離変更"] = np.select([pdist.isna(), dist - pdist >= 200, dist - pdist <= -200], ["不明", "延長", "短縮"], "同距離")
    H["芝ダ替わり"] = np.where(d.prev_tds.isna(), "不明", np.where(d.prev_tds.str.strip() == d.tds_code.str.strip(), "同", "替"))
    H["騎手乗り替わり"] = np.where(d.prev_jockey.isna(), "不明", np.where(d.prev_jockey.str.strip() == d.kishu_code.str.strip(), "継続騎乗", "乗り替わり"))
    H["減量騎手"] = np.where(d.minarai_kubun.fillna("").str.strip().isin(["1", "2", "3"]), "減量", "なし")
    H["騎手連対率"] = cut(num(d.kishu_renntai_rate), [0, 10, 20, 999], ["~10%", "10-20%", "20%~"])
    H["激走指数順位"] = rk(num(d.gekiso_index).groupby(d.race).rank(ascending=False, method="min"))
    H["万券指数"] = cut(num(d.manbaken_index), [-999, 50, 70, 999], ["~49", "50-69", "70~"])
    H["調教矢印"] = d.chokyo_yajirushi.str.strip().map({"1": "1最上", "2": "2上昇", "3": "3平行", "4": "4下降", "5": "5劣"}).fillna("他")
    H["厩舎評価"] = d.kyusha_hyoka.fillna("").str.strip().replace("", "他")
    H["出遅れ率"] = cut(num(d.uma_okure_rate), [0, 0.0001, 10, 999], ["0", "~10%", "10%~"])
    H["競馬場"] = d.course_code.map(COURSE).fillna("他")
    H["季節"] = num(d.ymd.str[4:6]).map(lambda m: {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏"}.get(m, "秋"))
    H["調教師の過去初B"] = trainer_history(d)
    for k, v in H.items():
        d["h_" + k] = pd.Series(v, index=d.index).astype(str)
    return d, list(H.keys())


def trainer_history(d):
    """調教師がその日より前に初ブリンカーを使った回数と、その複勝の同オッズ平均との差（先読みなし）"""
    b = d[d.bl == "1"].assign(t=lambda x: x.ymd.astype(int))
    day = b.groupby(["trainer_code", "t"]).place_x.agg(["sum", "size"]).reset_index().sort_values(["trainer_code", "t"])
    day["cs2"] = day.groupby("trainer_code")["sum"].cumsum(); day["cn2"] = day.groupby("trainer_code")["size"].cumsum()
    q = d[["trainer_code"]].assign(t=d.ymd.astype(int)).reset_index()
    # 前日までの累計（当日は含めない）
    q = pd.merge_asof(q.sort_values("t"), day.sort_values("t")[["trainer_code", "t", "cs2", "cn2"]].rename(columns={"t": "t_h"}),
                      left_on="t", right_on="t_h", by="trainer_code", allow_exact_matches=False).set_index("index").reindex(d.index)
    cn, cs = q.cn2.fillna(0).to_numpy(), q.cs2.fillna(0).to_numpy()
    mean = np.where(cn > 0, cs / np.maximum(cn, 1), np.nan)
    return np.select([cn == 0, cn < 10, mean > 0], ["経験なし", "1-9回", "10回以上・好"], "10回以上・不振")


POOL = {}


def build_pool(d):
    """同年・同オッズ帯の全馬の払戻（比較用の無作為抽出に使う）"""
    for key in ("win", "place"):
        POOL[key] = {k: g.to_numpy() for k, g in d.groupby(["year", "ob"])[key]}


def matched_trim(x, key, p=.05, draws=40):
    """x と同じ年×オッズ帯の構成で全馬から無作為に選んだ集団に、同じ『的中上位p除外』をした平均（の平均）"""
    rng = np.random.default_rng(0)
    cells = list(zip(x.year, x.ob))
    from collections import Counter
    cnt = Counter(cells)
    vals = []
    for _ in range(draws):
        s = np.concatenate([rng.choice(POOL[key][c], n) for c, n in cnt.items()])
        vals.append(trim_mean(s, p))
    return float(np.mean(vals))


def stat(x, key):
    """同オッズ平均との差・年別・95%区間・5%除外差（比較基準も同じオッズ構成で同じ除外をした値）"""
    r = {"頭数": len(x), "的中": int((x[key] > 0).sum()), "回収": x[key].mean(), "平均": x[key + "_b"].mean()}
    r["差"] = r["回収"] - r["平均"]
    yy = []
    for Y in YEARS:
        xy = x[x.year == Y]
        v = (xy[key].mean() - xy[key + "_b"].mean()) if len(xy) >= 15 else np.nan
        r[str(Y)[2:]] = v
        if not np.isnan(v): yy.append(v)
    r["+年"] = f"{sum(v > 0 for v in yy)}/{len(yy)}"
    r["5%除外差"] = trim_mean(x[key], .05) - matched_trim(x, key) if len(x) else np.nan
    diff = x[key + "_x"].to_numpy()
    rng = np.random.default_rng(0)
    bs = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(400)]
    r["95%下"], r["95%上"] = np.percentile(bs, [2.5, 97.5])
    return r


def screen(d, hyps, group="1", min_n=150):
    """仮説ごとの初装着成績と、同条件のブリンカーなしとの比較"""
    tgt = d[d.bl == group]
    non = d[d.bl == ""]
    re_ = d[d.bl == "2"]
    rows = []
    for key in ("win", "place"):
        for h in hyps:
            col = "h_" + h
            nd = non.groupby(col)[key + "_x"].mean()
            rd = re_.groupby(col)[key + "_x"].agg(["mean", "size"])
            for v, x in tgt.groupby(col):
                if v in ("nan", "他", "不明", "<NA>") or len(x) < min_n:
                    continue
                r = stat(x, key)
                r.update({"券": "単" if key == "win" else "複", "仮説": h, "区分": v, "なし同条件差": nd.get(v, np.nan),
                          "再装着差": rd["mean"].get(v, np.nan), "再頭数": rd["size"].get(v, 0)})
                r["上乗せ"] = r["差"] - r["なし同条件差"]
                rows.append(r)
    return pd.DataFrame(rows)


COLS = ["券", "仮説", "区分", "頭数", "的中", "回収", "平均", "差", "なし同条件差"] + [str(y)[2:] for y in YEARS] + ["+年", "5%除外差", "95%下", "95%上", "再装着差", "再頭数"]


def wf_select(d, hyps, key, group="1", min_prior=150, pairs=True, top_pairs_from=None):
    """毎年 Y: Y年より前の初装着データで、単独条件・2条件の組み合わせの中から
       『前年までの各年の差の最悪値』が最も高いものを選び、Y年で答え合わせ"""
    tgt = d[d.bl == group].copy()
    cols = ["h_" + h for h in hyps]
    rows, picked = [], []
    for Y in TEST_YEARS:
        tr = tgt[tgt.year < Y]
        cand = []
        for c in cols:
            for v in tr[c].unique():
                if v in ("nan", "他", "不明", "<NA>"): continue
                cand.append(((c, v),))
        if pairs:
            # 組み合わせは、前年までのデータで単独の差がプラスの区分どうしに限る（候補の爆発を防ぐ）
            singles = []
            for (cv,) in cand:
                x = tr[tr[cv[0]] == cv[1]]
                if len(x) >= min_prior and x[key + "_x"].mean() > 0:
                    singles.append(cv)
            for a, b in itertools.combinations(singles, 2):
                if a[0] != b[0]:
                    cand.append((a, b))
        best, bestv, bestn = None, -1e9, 0
        for cs in cand:
            m = np.ones(len(tr), bool)
            for c, v in cs:
                m &= (tr[c] == v).to_numpy()
            x = tr[m]
            if len(x) < min_prior: continue
            yr = x.groupby("year")[key + "_x"].mean()
            if len(yr) < Y - 2020: continue      # 前年までの全年にデータがあること
            v = yr.min()
            if v > bestv:
                best, bestv, bestn = cs, v, len(x)
        te = tgt[tgt.year == Y]
        m = np.ones(len(te), bool)
        for c, v in best:
            m &= (te[c] == v).to_numpy()
        x = te[m]
        picked.append(x)
        rows.append({"年": Y, "選んだ条件": " × ".join(f"{c[2:]}={v}" for c, v in best), "候補数": len(cand),
                     "前年までの頭数": bestn, "前年までの最悪年差": round(bestv, 1), "頭数": len(x), "的中": int((x[key] > 0).sum()),
                     "回収": round(x[key].mean(), 1), "同オッズ平均": round(x[key + "_b"].mean(), 1), "差": round(x[key + "_x"].mean(), 1)})
    return pd.DataFrame(rows), pd.concat(picked)


def wf_index(d, hyps, key, k, groups=("1",), exclude=()):
    """全仮説の区分ごとの効果（同オッズ平均との差の、初装着全体からの上乗せ）を縮小推定し足し合わせた点数。
       毎年その年より前のデータだけで効果を推定し直す"""
    cols = ["h_" + h for h in hyps if h not in exclude]
    tr_all = d[d.bl.isin(groups)]
    tgt = d[d.bl == "1"]
    parts = []
    for Y in TEST_YEARS:
        tr = tr_all[tr_all.year < Y]
        base = tr[key + "_x"].mean()
        te = tgt[tgt.year == Y].copy()
        s = np.zeros(len(te))
        for c in cols:
            a = tr.groupby(c)[key + "_x"].agg(["sum", "size"])
            eff = (a["sum"] - a["size"] * base) / (a["size"] + k)
            s += te[c].map(eff).fillna(0).to_numpy()
        te["score"] = s
        parts.append(te)
    t = pd.concat(parts)
    rng = np.random.default_rng(1)
    pct = (t.score + rng.normal(0, 1e-9, len(t))).groupby(t.year).rank(pct=True)
    bands = [("上位5%", pct > .95), ("上位10%", pct > .90), ("上位25%", pct > .75), ("中位25-75%", (pct > .25) & (pct <= .75)), ("下位25%", pct <= .25)]
    return t, bands


if __name__ == "__main__":
    d, hyps = prep(load())
    build_pool(d)
    print(f"対象 {len(d):,}頭（{d.year.min()}〜{d.year.max()}）初装着 {(d.bl == '1').sum():,} / 再装着 {(d.bl == '2').sum():,}")
    what = sys.argv[1] if len(sys.argv) > 1 else "S"
    if "S" in what:
        res = screen(d, hyps)
        res.to_pickle(os.path.join(ROOT, ".scratch", "blinker_wide_screen.pkl"))
        print("\n## 初装着 × 仮説ごとの区分（全区分）")
        print(res[COLS].round(1).to_string(index=False))
    if "I" in what:
        cols = ["案", "帯", "頭数", "的中", "回収", "平均", "差"] + [str(y)[2:] for y in TEST_YEARS] + ["+年", "5%除外差", "95%下", "95%上"]
        for key, lab in (("place", "複勝"), ("win", "単勝")):
            rows = []
            for name, kk, gr, ex in [("全仮説 k1000", 1000, ("1",), ()), ("全仮説 k3000", 3000, ("1",), ()),
                                     ("全仮説 k1000 初+再で推定", 1000, ("1", "2"), ()),
                                     ("全仮説−人気IDMずれ k1000", 1000, ("1",), ("人気−IDM順位",))]:
                t, bands = wf_index(d, hyps, key, kk, gr, ex)
                for bn, m in bands:
                    r = stat(t[m], key); r.update({"案": name, "帯": bn}); rows.append(r)
            print(f"\n## 指数案（{lab}で効果を推定し{lab}で評価、初装着 2022-2026、毎年その年より前で推定）")
            res = pd.DataFrame(rows)
            for Y in TEST_YEARS: res[str(Y)[2:]] = res[str(Y)[2:]]
            print(res[[c for c in cols if c in res.columns]].round(1).to_string(index=False))
    if "W" in what:
        for key, lab in (("win", "単勝"), ("place", "複勝")):
            for pairs in (False, True):
                t, x = wf_select(d, hyps, key, pairs=pairs)
                print(f"\n## walk-forward 条件選択（{lab}、{'単独+2条件' if pairs else '単独条件のみ'}、初装着）")
                print(t.to_string(index=False))
                r = stat(x, key)
                print(f"通算 {r['頭数']}頭 的中{r['的中']} 回収{r['回収']:.1f}% 平均{r['平均']:.1f}% 差{r['差']:+.1f} 5%除外差{r['5%除外差']:+.1f} 95%[{r['95%下']:.1f},{r['95%上']:.1f}]")
