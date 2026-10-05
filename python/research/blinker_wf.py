# -*- coding: utf-8 -*-
"""
ブリンカー指数のブラッシュアップ検証（研究用・DB書き込みなし）
- 評価: 回収率を「同じ年・同じ基準オッズ帯の全馬の平均」と比べた差（pt）
- 頑健性: 的中の払戻上位1%を除いた差、ブートストラップ95%区間、年別の向き
- 指数案は walk-forward（毎年 Y について Y年より前の全データで集計し直し、Y年を採点）
対象: 芝ダ・新馬除外・完走（T_KYI×T_BAC×T_SED）
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE = os.path.join(ROOT, ".scratch", "blinker_base2.pkl")
OB_EDGES = [1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100, 1000]
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]


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
      SELECT b.ymd, k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
             k.blinker, k.kijun_odds, k.kijun_ninki, b.tds_code, TRIM(b.distance) AS distance, TRIM(b.class) AS cls,
             k.kyakushitsu, k.seibetsu_code, k.waku_num, k.rotation, k.idm, k.ten_index_juni, k.agari_index_juni,
             k.joho_index, k.kyusha_index, k.chokyo_yajirushi, k.joshodo, k.trainer_code, k.kishu_code,
             s.order_of_finish AS fin, s.win AS win_pay, s.place AS place_pay,
             p.order_of_finish AS prev_fin, p.heads AS prev_heads, p.win_diff AS prev_diff,
             p.tds_code AS prev_tds, TRIM(p.distance) AS prev_dist,
             k.idm_rank_all, k.kyusha_rank_all
      FROM (SELECT k0.*,
              -- レース内順位は結果を使わないよう、完走馬だけでなく出走予定の全馬で数える
              RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY CAST(NULLIF(TRIM(idm),'') AS DECIMAL(6,1)) DESC) AS idm_rank_all,
              RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY CAST(NULLIF(TRIM(kyusha_index),'') AS DECIMAL(6,1)) DESC) AS kyusha_rank_all
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


def prep(df):
    d = df.copy()
    d["year"] = d["ymd"].str[:4].astype(int)
    d["race"] = d.course_code + d.year_code + d.kai + d.day_code + d.race_num
    d["odds"] = num(d.kijun_odds)
    d = d[d.odds.between(1, 999)].copy()
    d["win"] = num(d.win_pay).fillna(0)
    d["place"] = num(d.place_pay).fillna(0)
    d["ob"] = pd.cut(d.odds, OB_EDGES, right=False).astype(str)
    d["bl"] = d.blinker.fillna("").str.strip()
    # 同年・同オッズ帯の全馬平均（比較基準）
    for c in ("win", "place"):
        d[c + "_b"] = d.groupby(["year", "ob"])[c].transform("mean")
        d[c + "_bt"] = d.groupby(["year", "ob"])[c].transform(trim_mean)
        d[c + "_x"] = d[c] - d[c + "_b"]
    # 要素
    dist = num(d.distance)
    d["f_coursefit"] = d.tds_code.str.strip() + "_" + pd.cut(dist, [0, 1400, 1800, 2200, 9999], right=False, labels=["S", "M", "I", "L"]).astype(str)
    d["f_tds"] = d.tds_code.str.strip()
    d["f_class"] = d.cls
    d["f_kyaku"] = d.kyakushitsu.str.strip()
    d["f_sex"] = d.seibetsu_code.str.strip()
    rot = num(d.rotation)
    d["f_rotation"] = pd.cut(rot, [-1, 2, 8, 999], labels=["~2週", "3-8週", "9週+"]).astype(str)
    d["f_waku"] = num(d.waku_num).astype("Int64").astype(str)
    d["idm_n"] = num(d.idm)
    d["idm_rank"] = num(d.idm_rank_all).where(d.idm_n.notna())
    rk = lambda r: pd.cut(r, [0, 1, 3, 6, 99], labels=["1", "2-3", "4-6", "7+"]).astype(str)
    d["f_idm"] = rk(d.idm_rank)
    d["f_ten"] = rk(num(d.ten_index_juni).replace(0, np.nan))
    d["f_agari"] = rk(num(d.agari_index_juni).replace(0, np.nan))
    d["f_odds"] = d.ob
    d["ninki"] = num(d.kijun_ninki)
    d["f_ninki_idm"] = pd.cut(d.ninki - d.idm_rank, [-99, -3, 2, 99], labels=["人気>能力", "並", "人気<能力"]).astype(str)
    pf, ph = num(d.prev_fin), num(d.prev_heads)
    d["f_prev_fin"] = pd.cut(pf, [0, 3, 5, 9, 99], labels=["1-3着", "4-5着", "6-9着", "10着+"]).astype(str)
    d.loc[pf.isna(), "f_prev_fin"] = "nan"
    d["f_prev_diff"] = pd.cut(num(d.prev_diff), [-99, 0.5, 1.0, 2.0, 99], labels=["0.5秒内", "0.5-1.0", "1.0-2.0", "2.0+"]).astype(str)
    pdist = num(d.prev_dist)
    d["f_dist_chg"] = np.select([pdist.isna(), dist - pdist >= 200, dist - pdist <= -200], ["nan", "延長", "短縮"], "同距離")
    d["f_surf_chg"] = np.where(d.prev_tds.isna(), "nan", np.where(d.prev_tds.str.strip() == d.tds_code.str.strip(), "同", "替"))
    d["f_yaji"] = d.chokyo_yajirushi.str.strip()
    d["f_joshodo"] = d.joshodo.str.strip()
    d["f_kyusha_rank"] = rk(num(d.kyusha_rank_all).where(num(d.kyusha_index).notna()))
    d["gap"] = d.ninki - d.idm_rank       # 人気順位 − IDM順位（大きいほど「能力の割に人気がない」）
    return d


def trim_mean(v):
    """的中の払戻上位1%を除いた平均（頭数はそのまま）"""
    v = pd.Series(v)
    hits = v[v > 0].sort_values(ascending=False)
    cut = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[cut:].sum() / len(v) if len(v) else np.nan


def stat_row(x, label, years, key="place"):
    r = {"区分": label, "頭数": len(x), "回収": x[key].mean(), "平均": x[key + "_b"].mean()}
    r["差"] = r["回収"] - r["平均"]
    for Y in years:
        xy = x[x.year == Y]
        r[str(Y)[2:]] = (xy[key].mean() - xy[key + "_b"].mean()) if len(xy) >= 20 else np.nan
    r["1%除外差"] = trim_mean(x[key]) - x[key + "_bt"].mean()
    diff = x[key + "_x"].to_numpy()
    rng = np.random.default_rng(0)
    bs = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(500)]
    r["95%下"], r["95%上"] = np.percentile(bs, [2.5, 97.5])
    yy = [r[str(Y)[2:]] for Y in years if not np.isnan(r[str(Y)[2:]])]
    r["同向"] = f"{max(sum(v > 0 for v in yy), sum(v < 0 for v in yy))}/{len(yy)}"
    return r


FACTORS = ["f_tds", "f_coursefit", "f_class", "f_kyaku", "f_sex", "f_rotation", "f_waku", "f_idm", "f_ten", "f_agari",
           "f_odds", "f_ninki_idm", "f_prev_fin", "f_prev_diff", "f_dist_chg", "f_surf_chg", "f_yaji", "f_joshodo", "f_kyusha_rank"]
BASE9 = ["f_coursefit", "f_class", "f_kyaku", "f_sex", "f_rotation", "f_waku", "f_idm", "f_ten", "f_agari"]


def section_overall(d):
    years = list(range(2020, 2027))
    rows = []
    for key in ("win", "place"):
        for lab, m in [("初装着", d.bl == "1"), ("再装着", d.bl == "2"), ("継続", d.bl == "3"), ("なし", d.bl == "")]:
            r = stat_row(d[m], lab, years, key); r["券種"] = "単" if key == "win" else "複"; rows.append(r)
    print("\n## A. ブリンカー区分ごとの成績（同年・同オッズ帯の全馬平均との差、pt）")
    out = pd.DataFrame(rows)
    print(out[["券種", "区分", "頭数", "回収", "平均", "差"] + [str(y)[2:] for y in years] + ["同向", "1%除外差", "95%下", "95%上"]].round(1).to_string(index=False))
    # オッズ帯別
    rows = []
    for key in ("win", "place"):
        for bl, bn in [("1", "初"), ("2", "再")]:
            for ob in sorted(d.ob.unique(), key=lambda s: float(s.split(",")[0][1:])):
                x = d[(d.bl == bl) & (d.ob == ob)]
                if len(x) >= 100:
                    r = stat_row(x, f"{bn} {ob}", years, key); r["券種"] = "単" if key == "win" else "複"; rows.append(r)
    print("\n## A2. 初装着/再装着 × 基準オッズ帯")
    out = pd.DataFrame(rows)
    print(out[["券種", "区分", "頭数", "回収", "平均", "差"] + [str(y)[2:] for y in years] + ["同向", "1%除外差", "95%下", "95%上"]].round(1).to_string(index=False))


def section_screen(d):
    """初装着・再装着（合算）の中での要素別の差。全7年で同じ向きか"""
    years = list(range(2020, 2027))
    b = d[d.bl.isin(["1", "2"])]
    rows = []
    for key in ("place", "win"):
        for f in FACTORS:
            for v, x in b.groupby(f):
                if v == "nan" or len(x) < 300:
                    continue
                r = stat_row(x, f"{f[2:]}={v}", years, key); r["券種"] = "複" if key == "place" else "単"
                r["ブリンカー全体比"] = r["差"] - (b[key + "_x"].mean())
                rows.append(r)
    out = pd.DataFrame(rows)
    print("\n## B. 初装着+再装着の中での要素別（同オッズ帯平均との差。'全体比'=ブリンカー馬全体の差からの上乗せ）")
    cols = ["券種", "区分", "頭数", "回収", "差", "ブリンカー全体比"] + [str(y)[2:] for y in years] + ["同向", "1%除外差", "95%下", "95%上"]
    print(out[cols].round(1).to_string(index=False))


# ---------------- C. walk-forward 指数案 ----------------
def factor_effects(tr, factors, key, k, by_type):
    """学習データから要素ごとの上乗せ（同オッズ帯平均との差の、ブリンカー馬全体平均からの上乗せ）を縮小推定"""
    eff = {}
    groups = [("1", tr[tr.bl == "1"]), ("2", tr[tr.bl == "2"])] if by_type else [("*", tr)]
    for t, g in groups:
        base = g[key + "_x"].mean()
        eff[(t, "base")] = base
        for f in factors:
            a = g.groupby(f)[key + "_x"].agg(["sum", "size"])
            a = a[a.index != "nan"]
            # 縮小: (sum - n*base) / (n + k)
            eff[(t, f)] = ((a["sum"] - a["size"] * base) / (a["size"] + k)).to_dict()
    return eff


def score_wf(d, factors, key="place", k=300, by_type=False, recent=None):
    b = d[d.bl.isin(["1", "2"])]
    parts = []
    for Y in TEST_YEARS:
        tr = b[b.year < Y]
        if recent:
            tr = tr[tr.year >= Y - recent]
        te = b[b.year == Y].copy()
        eff = factor_effects(tr, factors, key, k, by_type)
        s = np.zeros(len(te))
        tkey = te.bl.to_numpy() if by_type else np.array(["*"] * len(te))
        for f in factors:
            vals = te[f].to_numpy()
            s += np.array([eff[(t, f)].get(v, 0.0) for t, v in zip(tkey, vals)])
        te["score"] = s
        parts.append(te)
    return pd.concat(parts)


def pct_bands(t):
    rng = np.random.default_rng(1)
    sc = t.score + rng.normal(0, 1e-9, len(t))
    pct = sc.groupby(t.year).rank(pct=True)
    return [("上位10%", pct > .90), ("上位10-25%", (pct > .75) & (pct <= .90)), ("上位25%計", pct > .75),
            ("中位25-75%", (pct > .25) & (pct <= .75)), ("下位25%", pct <= .25)]


def section_index(d):
    b = d[d.bl.isin(["1", "2"])]
    print(f"\n## C. walk-forward 指数案（採点対象: 初装着+再装着 {len(b[b.year >= 2022]):,}頭 2022-2026、年ごとにその年より前で集計）")
    print(f"   参考: 初+再 全体の差 複勝 {b[b.year >= 2022].place_x.mean():+.1f}pt / 単勝 {b[b.year >= 2022].win_x.mean():+.1f}pt")
    variants = [
        ("旧設計相当(単勝・9要素・縮小なし・種別別)", BASE9, "win", 1e-9, True, None),
        ("案1 複勝・9要素・k300・合算", BASE9, "place", 300, False, None),
        ("案2 複勝・9要素・k300・種別別", BASE9, "place", 300, True, None),
        ("案3 複勝・9要素+オッズ帯・k300", BASE9 + ["f_odds"], "place", 300, False, None),
        ("案4 複勝・全19要素・k300", FACTORS, "place", 300, False, None),
        ("案5 複勝・全19要素・k1000", FACTORS, "place", 1000, False, None),
        ("案6 単勝・全19要素・k1000", FACTORS, "win", 1000, False, None),
        ("案7 複勝・ずれ以外18要素・k1000", [f for f in FACTORS if f != "f_ninki_idm"], "place", 1000, False, None),
    ]
    cols = ["案", "帯", "頭数", "回収", "平均", "差"] + [str(y)[2:] for y in TEST_YEARS] + ["同向", "1%除外差", "95%下", "95%上"]
    for lab, fs, key, k, bt, rec in variants:
        t = score_wf(d, fs, key, k, bt, rec)
        rows = []
        for ek in ("place", "win"):
            for name, m in pct_bands(t):
                r = stat_row(t[m], name, TEST_YEARS, ek); r["案"] = f"{lab} →評価{'複' if ek == 'place' else '単'}"; r["帯"] = name; rows.append(r)
        print(pd.DataFrame(rows)[cols].round(1).to_string(index=False))


def section_contrast(d):
    """B で毎年同じ向きだった条件が、ブリンカー特有か（なし・継続の馬でも同じか）"""
    years = list(range(2020, 2027))
    conds = [("人気<能力(人気順位-IDM順位>=3)", d.f_ninki_idm == "人気<能力"),
             ("間隔3-8週", d.f_rotation == "3-8週"),
             ("前走と同じ芝ダ", d.f_surf_chg == "同"),
             ("前走から芝ダ替わり", d.f_surf_chg == "替"),
             ("ダート", d.f_tds == "2"),
             ("上がり指数4-6位", d.f_agari == "4-6"),
             ("4枠", d.f_waku == "4"),
             ("脚質=差し", d.f_kyaku == "3"),
             ("芝1800-2200", d.f_coursefit == "1_I")]
    rows = []
    for key in ("place", "win"):
        for lab, m in conds:
            for gl, gm in [("初+再", d.bl.isin(["1", "2"])), ("初", d.bl == "1"), ("再", d.bl == "2"), ("継続", d.bl == "3"), ("なし", d.bl == "")]:
                x = d[m & gm]
                r = stat_row(x, f"{lab} [{gl}]", years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
    print("\n## D. 条件がブリンカー特有か（同じ条件を ブリンカーなし・継続 の馬と比べる）")
    print(pd.DataFrame(rows)[["券種", "区分", "頭数", "回収", "差"] + [str(y)[2:] for y in years] + ["同向", "1%除外差", "95%下", "95%上"]].round(1).to_string(index=False))


def section_gap(d):
    """人気順位−IDM順位のずれ × ブリンカー区分。しきい値の周辺・オッズ帯・間隔との組み合わせ・walk-forward でのしきい値選択"""
    years = list(range(2020, 2027))
    cols = ["券種", "区分", "頭数", "回収", "差"] + [str(y)[2:] for y in years] + ["同向", "1%除外差", "95%下", "95%上"]
    groups = [("初+再", d.bl.isin(["1", "2"])), ("初", d.bl == "1"), ("再", d.bl == "2"), ("継続", d.bl == "3"), ("なし", d.bl == "")]
    rows = []
    for key in ("place", "win"):
        for gl, gm in groups:
            for th in (1, 2, 3, 4, 5, 6):
                x = d[gm & (d.gap >= th)]
                r = stat_row(x, f"[{gl}] ずれ>={th}", years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
            x = d[gm & (d.gap <= -3)]
            r = stat_row(x, f"[{gl}] ずれ<=-3", years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
    print("\n## E1. 人気順位−IDM順位のずれ（しきい値の周辺）× ブリンカー区分")
    print(pd.DataFrame(rows)[cols].round(1).to_string(index=False))

    b = d[d.bl.isin(["1", "2"]) & (d.gap >= 3)]
    rows = []
    for key in ("place", "win"):
        for ob in sorted(b.ob.unique(), key=lambda s: float(s.split(",")[0][1:])):
            x = b[b.ob == ob]
            if len(x) >= 60:
                r = stat_row(x, f"オッズ{ob}", years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
        for lab, m in [("IDM1位", b.idm_rank == 1), ("IDM2-3位", b.idm_rank.between(2, 3)), ("IDM4位以下", b.idm_rank >= 4),
                       ("間隔3-8週", b.f_rotation == "3-8週"), ("間隔3-8週以外", b.f_rotation != "3-8週"),
                       ("芝", b.f_tds == "1"), ("ダート", b.f_tds == "2")]:
            r = stat_row(b[m], lab, years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
    print("\n## E2. 初+再 × ずれ>=3 の内訳")
    print(pd.DataFrame(rows)[cols].round(1).to_string(index=False))

    # 間隔3-8週 × 初装着（単勝）のしきい値まわり
    rows = []
    rot = num(d.rotation)
    for key in ("win", "place"):
        for gl, gm in groups[:3]:
            for lo, hi in [(1, 2), (3, 4), (5, 8), (3, 8), (9, 12), (13, 99)]:
                x = d[gm & rot.between(lo, hi)]
                r = stat_row(x, f"[{gl}] 間隔{lo}-{hi}週", years, key); r["券種"] = "複" if key == "place" else "単"; rows.append(r)
    print("\n## E3. 前走からの間隔（週）× ブリンカー区分")
    print(pd.DataFrame(rows)[cols].round(1).to_string(index=False))

    # walk-forward: 毎年その年より前のデータで「ずれ>=th」の th を選ぶ（初+再、複勝の差が最大、頭数200以上）
    rows = []
    bb = d[d.bl.isin(["1", "2"])]
    for Y in TEST_YEARS:
        tr = bb[bb.year < Y]
        best = max((th for th in range(1, 7) if (tr.gap >= th).sum() >= 200), key=lambda th: tr[tr.gap >= th].place_x.mean())
        te = bb[(bb.year == Y) & (bb.gap >= best)]
        rows.append({"年": Y, "選んだしきい値": best, "頭数": len(te), "複勝": te.place.mean(), "平均": te.place_b.mean(),
                     "差": te.place_x.mean(), "単勝": te.win.mean(), "単平均": te.win_b.mean(), "単差": te.win_x.mean()})
    w = pd.DataFrame(rows)
    print("\n## E4. walk-forward（毎年その年より前のデータでしきい値を選び直し）初+再 × ずれ>=しきい値")
    print(w.round(1).to_string(index=False))
    tot = pd.concat([bb[(bb.year == r["年"]) & (bb.gap >= r["選んだしきい値"])] for r in rows])
    print("通算", stat_row(tot, "通算", TEST_YEARS, "place"))
    print("通算(単)", stat_row(tot, "通算", TEST_YEARS, "win"))


def section_rule_wf(d):
    """候補ルール（ずれ×間隔×区分）を毎年その年より前のデータだけで選び直して、その年で答え合わせ"""
    rot = num(d.rotation)
    groups = {"初+再": d.bl.isin(["1", "2"]), "初": d.bl == "1", "再": d.bl == "2"}
    intervals = {"間隔問わず": pd.Series(True, index=d.index), "間隔3-8週": rot.between(3, 8), "間隔3-12週": rot.between(3, 12)}
    cands = {}
    for gl, gm in groups.items():
        for il, im in intervals.items():
            for th in (0, 1, 2, 3, 4, 5):   # th=0 は「ずれ条件なし」
                m = gm & im & ((d.gap >= th) if th else True)
                cands[f"{gl}・{il}・" + (f"ずれ>={th}" if th else "ずれ問わず")] = m
    for key, lab in (("place", "複勝"), ("win", "単勝")):
        rows, picked = [], []
        for Y in TEST_YEARS:
            tr = d.year < Y
            # その年より前の全年で、同オッズ帯平均との差の「最悪年」が最も高いものを選ぶ（頭数は前年までで200以上）
            best, bestv = None, -1e9
            for name, m in cands.items():
                x = d[m & tr]
                if len(x) < 200:
                    continue
                yr = x.groupby("year")[key + "_x"].mean()
                v = yr.min()
                if v > bestv:
                    best, bestv = name, v
            te = d[cands[best] & (d.year == Y)]
            picked.append(te)
            rows.append({"年": Y, "選んだ条件": best, "前年までの最悪年差": bestv, "頭数": len(te), "的中率": (te[key] > 0).mean() * 100,
                         "回収": te[key].mean(), "同オッズ平均": te[key + "_b"].mean(), "差": te[key + "_x"].mean()})
        print(f"\n## F. walk-forward ルール選択（{lab}、毎年その年より前のデータで最悪年が最も良い条件を選ぶ）")
        print(pd.DataFrame(rows).round(1).to_string(index=False))
        tot = pd.concat(picked)
        r = stat_row(tot, "通算", TEST_YEARS, key)
        print(f"通算 {r['頭数']}頭 回収{r['回収']:.1f}% 平均{r['平均']:.1f}% 差{r['差']:+.1f} 1%除外差{r['1%除外差']:+.1f} 95%[{r['95%下']:.1f},{r['95%上']:.1f}]")

    # 固定ルールの中身：初+再 × ずれ>=3 × 間隔3-8週
    m = d.bl.isin(["1", "2"]) & (d.gap >= 3) & rot.between(3, 8)
    x = d[m].copy()
    print("\n## F2. 初+再 × ずれ>=3 × 間隔3-8週 の年別（2020-2026）")
    g = x.groupby("year").agg(頭数=("place", "size"), 複勝的中=("place", lambda v: (v > 0).sum()), 複勝回収=("place", "mean"),
                              同オッズ平均=("place_b", "mean"), 単勝的中=("win", lambda v: (v > 0).sum()), 単勝回収=("win", "mean"))
    g["差"] = g.複勝回収 - g.同オッズ平均
    print(g.round(1).to_string())
    print("基準オッズの分布:", x.ob.value_counts().sort_index().to_dict())
    print("複勝払戻の上位10件:", sorted(x.place[x.place > 0], reverse=True)[:10], " 的中数", (x.place > 0).sum())
    ex = x[x.year >= 2025].sort_values("ymd").tail(15)
    print("\n直近の実例（2025-2026、最後の15頭）")
    print(ex[["ymd", "course_code", "race_num", "uma_num", "bl", "odds", "ninki", "idm_rank", "rotation", "fin", "place", "win"]].to_string(index=False))


if __name__ == "__main__":
    d = prep(load())
    print(f"対象 {len(d):,}頭（{d.year.min()}〜{d.year.max()}）初装着 {(d.bl=='1').sum():,} / 再装着 {(d.bl=='2').sum():,} / 継続 {(d.bl=='3').sum():,}")
    what = sys.argv[1] if len(sys.argv) > 1 else "ABC"
    if "A" in what: section_overall(d)
    if "B" in what: section_screen(d)
    if "C" in what: section_index(d)
    if "D" in what: section_contrast(d)
    if "E" in what: section_gap(d)
    if "F" in what: section_rule_wf(d)
