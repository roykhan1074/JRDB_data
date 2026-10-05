# -*- coding: utf-8 -*-
"""
指数の差・市場評価とのずれを sc に加えると上位が良くなるかを検証する（研究用）。
- 新シグナルのしきい値（上位20%の境目）と点数は、毎年 Y について Y年より前のデータだけで決める
  点数 = 「現行 sc の各点数をダミーにした回帰」に新シグナルを加えたときの正味の効果 ÷ 4 を四捨五入（sc の+1 ≒ 複勝+4pt）
- 比較: しきい値そのもの（sc≥N）と、現行 sc≥N と同じ頭数（同点の乱数を30通り変えた平均と幅）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import prob_wf as P
ROOT = P.ROOT

d = P.prepare(P.fetch())
d = d[(d.shinba == 0) & (d.year >= 2021)].copy()
d["place"] = pd.to_numeric(d.place_pay, errors="coerce").fillna(0)
d["win"] = pd.to_numeric(d.win_pay, errors="coerce").fillna(0)
bad = ~d.ijou.isin(["0", ""])
d.loc[bad, ["place", "win"]] = 0
d["ob"] = pd.cut(d.kijun_odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["year", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]
g = d.groupby("race_id")
for c in ("idm", "ten_index", "agari_index"):
    top2 = g[c].transform(lambda s: s.nlargest(2).iloc[-1] if s.notna().sum() >= 2 else np.nan)
    d[f"{c}_lead"] = np.where(d[f"{c}_rk"] == 1, d[c] - top2, np.nan)
d["ninki_gap"] = d.kijun_ninki - d.idm_rk

sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf3.json"))))[["rid", "uma", "sc"]]
d = d.merge(sc, left_on=["race_id", "uma_num"], right_on=["rid", "uma"], how="inner")
d = d[d.kijun_odds.between(1, 999)].reset_index(drop=True)

NEW = {"テン抜け": "ten_index_lead", "上がり抜け": "agari_index_lead", "IDM抜け": "idm_lead", "人気<IDM": "ninki_gap"}
YEARS = [2022, 2023, 2024, 2025, 2026]
for lab in NEW:
    d["f_" + lab] = 0
d["sc_new"] = np.nan
log = {}
for Y in YEARS:
    tr = d.y if False else None
    trm = (d.year < Y).values
    flags = {}
    for lab, col in NEW.items():
        thr = d.loc[trm, col].quantile(0.8)        # その年より前のデータで上位20%の境目
        flags[lab] = (d[col] >= thr).astype(float).fillna(0).to_numpy()
    Xs = pd.get_dummies(d.sc.clip(-2, 10).astype(int).astype(str), prefix="sc").astype(float)
    X = np.column_stack([np.ones(len(d)), Xs.to_numpy()] + [flags[k] for k in NEW])
    beta, *_ = np.linalg.lstsq(X[trm], d.loc[trm, "place_x"].to_numpy(), rcond=None)
    eff = dict(zip(NEW, beta[-len(NEW):]))
    pts = {k: int(np.round(max(v, 0) / 4)) for k, v in eff.items()}   # マイナス効果のものは加点しない
    m = (d.year == Y).values
    d.loc[m, "sc_new"] = d.loc[m, "sc"] + sum(pts[k] * flags[k][m] for k in NEW)
    log[Y] = {k: (round(float(thr), 1) if False else None, round(float(eff[k]), 1), pts[k]) for k, thr in zip(NEW, [0] * 4)}
    print(f"{Y}: 正味の効果(pt)と加点 " + ", ".join(f"{k} {eff[k]:+.1f}→+{pts[k]}" for k in NEW), flush=True)

t = d[d.year.isin(YEARS)].copy()


def stats(x):
    hits = x.place[x.place > 0].sort_values(ascending=False); k = int(len(hits) * 0.01)
    return dict(n=len(x), 複勝=x.place.mean(), 差=x.place_x.mean(), 一pct除外=(x.place.sum() - hits.iloc[:k].sum()) / len(x) - x.place_b.mean(),
                単勝=x.win.mean(), 単勝差=x.win_x.mean(), 三着内率=(x.fin <= 3).mean() * 100, オッズ中央値=x.kijun_odds.median(),
                年別=" / ".join(f"{x[x.year == Y].place_x.mean():+.1f}" for Y in YEARS))


print("\n### しきい値そのもので比較（2022〜2026）")
for N in (6, 7, 8, 9, 10):
    for col, lab in (("sc", "現行 sc"), ("sc_new", "新 sc")):
        s = stats(t[t[col] >= N])
        print(f"{lab} ≥{N}: n={s['n']:,} 複勝{s['複勝']:.1f}% 差{s['差']:+.1f} [{s['年別']}] 1%除外{s['一pct除外']:+.1f} | 単勝{s['単勝']:.1f}% 差{s['単勝差']:+.1f} | 3着内率{s['三着内率']:.1f}% オッズ中央値{s['オッズ中央値']:.1f}")

print("\n### 現行 sc≥N と同じ頭数で比較（同点の乱数30通りの平均と幅）")
for N in (6, 7, 8):
    res = {"現行 sc": [], "新 sc": []}
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        for col, lab in (("sc", "現行 sc"), ("sc_new", "新 sc")):
            parts = []
            for Y in YEARS:
                ty = t[t.year == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            x = pd.concat(parts)
            res[lab].append((x.place_x.mean(), x.place.mean(), x.win.mean(), (x.fin <= 3).mean() * 100))
    for lab, v in res.items():
        a = np.array(v)
        print(f"sc≥{N}相当 {lab}: 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 複勝{a[:, 1].mean():.1f}% 単勝{a[:, 2].mean():.1f}% 3着内率{a[:, 3].mean():.1f}%")
