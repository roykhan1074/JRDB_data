# -*- coding: utf-8 -*-
"""
追切指数・仕上指数（T_CYB）の検証（研究用）。
1) 下見: 各見方（順位・最高値との差・1位の抜け幅・偏差・値そのもの・組み合わせ）の複勝回収率の
   同オッズ帯平均との差を年ごと（2021-2026）に見る
2) 最新 sc に加点/減点して上位が良くなるかを walk-forward で検証（点数は毎年その年より前のデータで決定）。
   現行の「追切上位25% +1」を外して置き換える版も比べる
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import prob_wf as P
pd.set_option("display.width", 250)
ROOT = P.ROOT
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]
YEARS = [2022, 2023, 2024, 2025, 2026]

d = P.prepare(P.fetch())
d = d[(d.shinba == 0) & (d.year >= 2021)].copy()
d["place"] = pd.to_numeric(d.place_pay, errors="coerce").fillna(0)
d["win"] = pd.to_numeric(d.win_pay, errors="coerce").fillna(0)
d.loc[~d.ijou.isin(["0", ""]), ["place", "win"]] = 0
d["ob"] = pd.cut(d.kijun_odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["year", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]
# 0 以下は未計測（prob_wf の prepare は数値化のみなので、ここで欠損扱いにして順位等を作り直す）
for c in ("oi_index", "shiage_index"):
    d[c] = d[c].where(d[c] > 0)
    g = d.groupby("race_id")[c]
    d[c + "_rk"] = g.rank(ascending=False, method="min")
    d[c + "_dmax"] = d[c] - g.transform("max")
    d[c + "_z"] = (d[c] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
    top2 = g.transform(lambda s: s.nlargest(2).iloc[-1] if s.notna().sum() >= 2 else np.nan)
    d[c + "_lead"] = np.where(d[c + "_rk"] == 1, d[c] - top2, np.nan)
    d[c + "_cnt"] = g.transform("count")

def rank_b(r, n):
    return np.select([r.isna(), r == 1, r <= 3, r <= np.ceil(n * 0.25), r > np.ceil(n * 0.75)], ["未計測", "1位", "2-3位", "上位25%", "下位25%"], default="中位")

d["f_追切_順位"] = rank_b(d.oi_index_rk, d.oi_index_cnt)
d["f_仕上_順位"] = rank_b(d.shiage_index_rk, d.shiage_index_cnt)
for c, lab in (("oi_index", "追切"), ("shiage_index", "仕上")):
    d[f"f_{lab}_偏差"] = pd.cut(d[c + "_z"], [-99, -1, -0.3, 0.3, 1, 1.5, 99], labels=["−1未満", "−1〜−0.3", "±0.3", "0.3〜1", "1〜1.5", "1.5以上"]).astype(str)
    d[f"f_{lab}_抜け幅"] = pd.cut(d[c + "_lead"], [-0.01, 1, 3, 5, 99], labels=["1以下", "1〜3", "3〜5", "5超"]).astype(str)
    d[f"f_{lab}_値"] = pd.qcut(d[c], 5, duplicates="drop").astype(str)
both = (d.oi_index_rk <= 3) & (d.shiage_index_rk <= 3)
d["f_追切仕上_組合せ"] = np.select([d.oi_index.isna() | d.shiage_index.isna(), both, (d.oi_index_rk <= 3) | (d.shiage_index_rk <= 3)],
                                   ["未計測", "両方3位以内", "片方だけ3位以内"], default="どちらも4位以下")

FEATS = ["f_追切_順位", "f_仕上_順位", "f_追切_偏差", "f_仕上_偏差", "f_追切_抜け幅", "f_仕上_抜け幅", "f_追切_値", "f_仕上_値", "f_追切仕上_組合せ"]
SHOW = False
if SHOW: print("## 1. 下見（複勝回収率の同オッズ帯平均との差、年別）")
for f in (FEATS if SHOW else []):
    t = d.groupby(f).agg(n=("place", "size"), 複勝=("place", "mean"), 差=("place_x", "mean"))
    for Y in YEARS6:
        t[str(Y)] = d[d.year == Y].groupby(f).place_x.mean()
    s = np.sign(t[[str(Y) for Y in YEARS6]])
    t["毎年同じ向き"] = (s == 1).all(axis=1) | (s == -1).all(axis=1)
    print(f"\n### {f[2:]}")
    print(t.round(1).to_string())

# --- 2. sc に加える
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))[["rid", "uma", "sc", "s_oi"]]
d = d.merge(sc, left_on=["race_id", "uma_num"], right_on=["rid", "uma"], how="inner").reset_index(drop=True)
CAND = {f"{f[2:]}={v}": (d[f].map(str) == v) for f in FEATS for v in sorted(set(map(str, d[f].tolist())))
        if v not in ("未計測", "中位", "nan", "±0.3", "どちらも4位以下") and not f.endswith("_値")}
F = {k: v.astype(float).to_numpy() for k, v in CAND.items()}


def build(base_col, label):
    Xs = pd.get_dummies(d[base_col].clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
    out = np.full(len(d), np.nan)
    for Y in YEARS:
        tr = (d.year < Y).values
        X = np.column_stack([np.ones(len(d)), Xs] + [F[k] for k in CAND])
        beta, *_ = np.linalg.lstsq(X[tr], d.loc[tr, "place_x"].to_numpy(), rcond=None)
        eff = dict(zip(CAND, beta[-len(CAND):]))
        pts = {k: (int(np.round(v / 4)) if abs(v) >= 2 else 0) for k, v in eff.items()}
        m = (d.year == Y).values
        out[m] = d.loc[m, base_col].to_numpy() + sum(pts[k] * F[k][m] for k in CAND)
        if Y in (2022, 2026):
            print(f"  [{label}] {Y}: " + ", ".join(f"{k} {pts[k]:+d}" for k in CAND if pts[k] != 0))
    return out


print("\n## 2. sc への加点・減点（毎年その年より前のデータで決定）")
d["sc_noi"] = d.sc - d.s_oi
d["v_add"] = build("sc", "最新sc＋調教")
d["v_rep"] = build("sc_noi", "現行の追切+1を外して置き換え")
t = d[d.year.isin(YEARS)].copy()
print("\n### 最新 sc と同じ頭数で比較（同点の乱数30通りの平均と幅、2022〜2026）")
for N in (6, 7, 8, 9):
    res = {"最新 sc": [], "最新sc＋調教": [], "追切+1を置き換え": []}
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        for col, lab in (("sc", "最新 sc"), ("v_add", "最新sc＋調教"), ("v_rep", "追切+1を置き換え")):
            parts = []
            for Y in YEARS:
                ty = t[t.year == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            xx = pd.concat(parts)
            res[lab].append((xx.place_x.mean(), xx.place.mean(), xx.win.mean(), (xx.fin <= 3).mean() * 100,
                             *[xx[xx.year == Y].place_x.mean() for Y in YEARS]))
    for lab, v in res.items():
        a = np.array(v)
        yr = " / ".join(f"{a[:, 4 + i].mean():+.1f}" for i in range(len(YEARS)))
        print(f"sc≥{N}相当 {lab}: 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 年別[{yr}] 複勝{a[:, 1].mean():.1f}% 単勝{a[:, 2].mean():.1f}% 3着内率{a[:, 3].mean():.1f}%")


# ===== 3. 下見で効いたものを1つずつ加える（多数の重なる候補を一度に入れると点数が不安定になるため）=====
def build_small(base_col, cands):
    Xs = pd.get_dummies(d[base_col].clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
    FF = [c.astype(float).to_numpy() for c in cands.values()]
    out = np.full(len(d), np.nan); pts_log = {}
    for Y in YEARS:
        tr = (d.year < Y).values
        X = np.column_stack([np.ones(len(d)), Xs] + FF)
        beta, *_ = np.linalg.lstsq(X[tr], d.loc[tr, "place_x"].to_numpy(), rcond=None)
        pts = [(int(np.round(b / 4)) if abs(b) >= 2 else 0) for b in beta[-len(FF):]]
        m = (d.year == Y).values
        out[m] = d.loc[m, base_col].to_numpy() + sum(p * f[m] for p, f in zip(pts, FF))
        pts_log[Y] = dict(zip(cands, pts))
    return out, pts_log


oi_r, sh_r = d.oi_index_rk, d.shiage_index_rk
oi_n = d.oi_index_cnt; sh_n = d.shiage_index_cnt
V = {
    "A 両方3位以内": ("sc", {"両方3位以内": (oi_r <= 3) & (sh_r <= 3)}),
    "B 追切1位・仕上1位": ("sc", {"追切1位": oi_r == 1, "仕上1位": sh_r == 1}),
    "C 下位25%に減点": ("sc", {"追切下位25%": oi_r > np.ceil(oi_n * 0.75), "仕上下位25%": sh_r > np.ceil(sh_n * 0.75)}),
    "D 追切+1を追切3位以内に置換": ("sc_noi", {"追切3位以内": oi_r <= 3}),
    "A+C": ("sc", {"両方3位以内": (oi_r <= 3) & (sh_r <= 3), "追切下位25%": oi_r > np.ceil(oi_n * 0.75), "仕上下位25%": sh_r > np.ceil(sh_n * 0.75)}),
}
for lab, (base, cands) in V.items():
    d["v_" + lab], log = build_small(base, cands)
    print(f"  [{lab}] 点数 " + " / ".join(f"{Y}:{','.join(f'{k}{v:+d}' for k, v in log[Y].items())}" for Y in YEARS))
t = d[d.year.isin(YEARS)].copy()
print("\n### 1つずつ加えた版を最新 sc と同じ頭数で比較（同点の乱数30通り）")
for N in (6, 7, 8, 9):
    cols = [("sc", "最新 sc")] + [("v_" + k, k) for k in V]
    res = {lab: [] for _, lab in cols}
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        for col, lab in cols:
            parts = []
            for Y in YEARS:
                ty = t[t.year == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            xx = pd.concat(parts)
            res[lab].append((xx.place_x.mean(), xx.place.mean(), xx.win.mean(), (xx.fin <= 3).mean() * 100,
                             *[xx[xx.year == Y].place_x.mean() for Y in YEARS]))
    for lab, v in res.items():
        a = np.array(v)
        yr = " / ".join(f"{a[:, 4 + i].mean():+.1f}" for i in range(len(YEARS)))
        print(f"sc≥{N}相当 {lab}: 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 年別[{yr}] 複勝{a[:, 1].mean():.1f}% 単勝{a[:, 2].mean():.1f}% 3着内率{a[:, 3].mean():.1f}%")
