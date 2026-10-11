# -*- coding: utf-8 -*-
"""
騎手指数の使い道の検証（研究用）。前提: kishu_index_wf.py の出力 .scratch/kishu_wf.pkl
1) 補正の入れ方を変えた版の比較（毎年同じ向きだった補正を固定で入れる、重みは毎年 walk-forward）
2) sc への組み込み（騎手指数の上位/下位に加点・減点。点数は毎年その年より前のデータで決定）
   騎手×調教師（s_combo）を置き換える版も比べる。最新 sc と同じ頭数・同点の乱数30通りで比較
3) 消し: 穴馬（基準10倍以上）のうち騎手指数の下位25%
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kishu_index_wf import fit_weights, band_table, YEARS, YEARS_F, ROOT
pd.set_option("display.width", 250)

d = pd.read_pickle(os.path.join(ROOT, ".scratch", "kishu_wf.pkl"))
F = d[[c for c in d.columns if c.startswith("f_")]].rename(columns=lambda c: c[2:])
F["base"] = d["idx_base"]
TGT = "place_x"

# ===== 1. 固定で補正を入れる版
print("## 1. 補正を固定で入れた版（重みは毎年その年より前のデータで推定）")
VARS = {
    "A 土台＋テン順位": ["c_テン順位"],
    "B 土台＋テン順位・クラス・父系統": ["c_テン順位", "c_クラス", "c_父系統"],
    "C B＋人気帯・関係・種牡馬": ["c_テン順位", "c_クラス", "c_父系統", "c_人気帯", "c_関係", "c_種牡馬"],
}
ev_cols = {}
for lab, extra in VARS.items():
    col = "v_" + lab[0]
    d[col] = np.nan
    ws = []
    for Y in YEARS:
        prev = [y for y in YEARS_F if y < Y]
        cols = ["base"] + extra
        w, t = fit_weights(F, d, cols, TGT, prev)
        m = d.y == Y
        d.loc[m, col] = sum(w[i] * F.loc[m, c] for i, c in enumerate(cols))
        ws.append(f"{Y}:" + ",".join(f"{w[i]:.2f}" for i in range(len(cols))))
    print(f"  {lab} 重み " + " / ".join(ws))
    ev_cols[lab] = col
ev = d[d.y.isin(YEARS)].copy()
for lab, col in ev_cols.items():
    band_table(ev, col, label=lab)

# ===== 2. sc への組み込み
print("\n## 2. sc への組み込み")
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))[["rid", "uma", "sc", "s_combo", "shinba"]]
t = d.merge(sc, on=["rid", "uma"], how="inner")
t = t[t.shinba == 0].reset_index(drop=True)
print(f"  結合 {len(t)} 頭（新馬除外）")
t["sc_nocombo"] = t.sc - t.s_combo
# 騎手指数の年内順位（その年の中での相対位置。各馬の値自体はその年より前のデータで決まっている）
for col in ("idx_base", "v_B"):
    t[col + "_pct"] = t.groupby("y")[col].rank(pct=True)


def build(base_col, cands):
    Xs = pd.get_dummies(t[base_col].clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
    FF = [c.astype(float).to_numpy() for c in cands.values()]
    out = np.full(len(t), np.nan); log = {}
    for Y in YEARS:
        tr = (t.y < Y).values
        X = np.column_stack([np.ones(len(t)), Xs] + FF)
        beta, *_ = np.linalg.lstsq(X[tr], t.loc[tr, TGT].to_numpy(), rcond=None)
        pts = [(int(np.round(b / 4)) if abs(b) >= 2 else 0) for b in beta[-len(FF):]]
        m = (t.y == Y).values
        out[m] = t.loc[m, base_col].to_numpy() + sum(p * f[m] for p, f in zip(pts, FF))
        log[Y] = dict(zip(cands, pts))
    return out, log


P = t["idx_base_pct"]; PB = t["v_B_pct"]
V = {
    "上位5%に加点・下位25%に減点": ("sc", {"騎手上位5%": P > 0.95, "騎手下位25%": P <= 0.25}),
    "上位25%に加点・下位25%に減点": ("sc", {"騎手上位25%": P > 0.75, "騎手下位25%": P <= 0.25}),
    "下位25%に減点のみ": ("sc", {"騎手下位25%": P <= 0.25}),
    "版B 上位25%加点・下位25%減点": ("sc", {"騎手上位25%": PB > 0.75, "騎手下位25%": PB <= 0.25}),
    "騎手×調教師を外して置き換え": ("sc_nocombo", {"騎手上位25%": P > 0.75, "騎手下位25%": P <= 0.25}),
}
for lab, (base, cands) in V.items():
    t["v2_" + lab], log = build(base, cands)
    print(f"  [{lab}] 点数 " + " / ".join(f"{Y}:{','.join(f'{k}{v:+d}' for k, v in log[Y].items())}" for Y in YEARS))
te = t[t.y.isin(YEARS)].copy()
print("\n### 最新 sc と同じ頭数で比較（同点の乱数30通りの平均と幅、2022〜2026）")
cols = [("sc", "最新 sc")] + [("v2_" + k, k) for k in V]
for N in (5, 6, 7, 8, 9):
    res = {lab: [] for _, lab in cols}
    for seed in range(30):
        te["tie"] = np.random.default_rng(seed).random(len(te))
        for col, lab in cols:
            parts = []
            for Y in YEARS:
                ty = te[te.y == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            xx = pd.concat(parts)
            res[lab].append((xx.place_x.mean(), xx.place.mean(), xx.win.mean(), xx.win_x.mean(), len(xx),
                             *[xx[xx.y == Y].place_x.mean() for Y in YEARS]))
    print(f"\n sc≥{N}相当")
    for lab, v in res.items():
        a = np.array(v)
        yr = " / ".join(f"{a[:, 5 + i].mean():+.1f}" for i in range(len(YEARS)))
        print(f"   {lab}: 頭数{int(a[0, 4])} 複勝{a[:, 1].mean():.1f}% 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 年別[{yr}] 単勝{a[:, 2].mean():.1f}% 単差{a[:, 3].mean():+.1f}")

# ===== 3. 消し
print("\n## 3. 消し: 穴馬（基準10倍以上・新馬除外）")
a = te[te.odds >= 10].copy()
a["騎手下位25%"] = a.idx_base_pct <= 0.25
for (lo, hi) in ((10, 20), (20, 50), (50, 1000), (10, 1000)):
    g = a[(a.odds >= lo) & (a.odds < hi)]
    for flag, gg in g.groupby("騎手下位25%"):
        yr = gg.groupby("y").apply(lambda z: z.place.mean() - z.place_b.mean())
        yw = gg.groupby("y").apply(lambda z: z.win.mean() - z.win_b.mean())
        print(f"  {lo}〜{hi}倍 {'騎手下位25%' if flag else 'それ以外  '}: {len(gg):6d}頭 複勝{gg.place.mean():5.1f}% 差{(gg.place - gg.place_b).mean():+5.1f} 年別[{' / '.join(f'{v:+.1f}' for v in yr.values)}]"
              f" | 単勝{gg.win.mean():5.1f}% 差{(gg.win - gg.win_b).mean():+5.1f} 年別[{' / '.join(f'{v:+.1f}' for v in yw.values)}]")
# sc 上位から騎手下位25%を除く
print("\n  sc上位から騎手下位25%を除いた場合")
for N in (6, 7, 9):
    g = te[te.sc >= N]
    for lab, gg in (("そのまま", g), ("騎手下位25%を除く", g[g.idx_base_pct > 0.25]), ("騎手下位25%だけ", g[g.idx_base_pct <= 0.25])):
        yr = gg.groupby("y").apply(lambda z: z.place.mean() - z.place_b.mean())
        print(f"   sc≥{N} {lab}: {len(gg):5d}頭 複勝{gg.place.mean():5.1f}% 差{(gg.place - gg.place_b).mean():+5.1f} 年別[{' / '.join(f'{v:+.1f}' for v in yr.values)}] 単勝{gg.win.mean():5.1f}%")

# ===== 4. 実例（2026年の騎手指数 上位・下位、芝ダ別）
print("\n## 4. 実例: 2026年に使われた土台の値（騎手×芝ダ、2025年までのデータで集計）")
x = d[d.y == 2026].groupby(["kname", "tds"]).agg(base=("idx_base", "first"), n=("place", "size"),
                                                 複勝=("place", "mean"), 平均=("place_b", "mean")).reset_index()
x = x[x.n >= 60]
x["2026実績の差"] = x.複勝 - x.平均
x["tds"] = x.tds.map({"1": "芝", "2": "ダ"})
print(" 上位10"); print(x.sort_values("base", ascending=False).head(10).round(1).to_string(index=False))
print(" 下位10"); print(x.sort_values("base").head(10).round(1).to_string(index=False))
