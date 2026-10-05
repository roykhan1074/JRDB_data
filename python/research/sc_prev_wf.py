# -*- coding: utf-8 -*-
"""
前走からの変化を sc（2026-10-04 追加シグナル込みの最新版）に加点・減点として加えると上位が良くなるかを検証する（研究用）。
- 点数は毎年 Y について Y年より前（2021年〜）のデータで、「sc の各点数をダミーにした回帰」に候補を加えたときの正味の効果 ÷ 4 を四捨五入
  （プラスもマイナスも採用。|効果| が 2pt 未満は 0 点）
- 比較: 現行（最新）sc と同じ頭数（同点の乱数30通り）と、しきい値そのもの
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
d = pd.read_pickle(os.path.join(ROOT, ".scratch", "prev_prepped.pkl"))
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))[["rid", "uma", "sc"]]
d = d.merge(sc, on=["rid", "uma"], how="inner")
d = d[d.y >= 2021].reset_index(drop=True)
CAND = {
    "前走不利あり": d.f_前走不利 == "あり",
    "前走4角後方": d.f_前走4角位置 == "後方",
    "前走4角前": d.f_前走4角位置 == "前(上位20%)",
    "芝→ダ": d.f_芝ダ替わり == "芝→ダ",
    "前走6-9着": d.f_前走着順 == "6-9着",
    "IDM急上昇(+5以上)": d["f_今回IDM−前走IDM"] == "+5以上",
    "前走出遅れ": d.f_前走出遅れ == "あり",
    "400m以上延長": d.f_距離変更 == "400m以上延長",
}
F = {k: v.astype(float).to_numpy() for k, v in CAND.items()}
YEARS = [2022, 2023, 2024, 2025, 2026]
Xs = pd.get_dummies(d.sc.clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
d["sc_prev"] = np.nan
for Y in YEARS:
    tr = (d.y < Y).values
    X = np.column_stack([np.ones(len(d)), Xs] + [F[k] for k in CAND])
    beta, *_ = np.linalg.lstsq(X[tr], d.loc[tr, "place_x"].to_numpy(), rcond=None)
    eff = dict(zip(CAND, beta[-len(CAND):]))
    pts = {k: (int(np.round(v / 4)) if abs(v) >= 2 else 0) for k, v in eff.items()}
    m = (d.y == Y).values
    d.loc[m, "sc_prev"] = d.loc[m, "sc"] + sum(pts[k] * F[k][m] for k in CAND)
    print(f"{Y}: " + ", ".join(f"{k} {eff[k]:+.1f}→{pts[k]:+d}" for k in CAND), flush=True)

t = d[d.y.isin(YEARS)].copy()
print("\n### 現行（最新）sc≥N と同じ頭数で比較（同点の乱数30通りの平均と幅、2022〜2026）")
for N in (6, 7, 8, 9):
    res = {"現行 sc": [], "sc＋前走": []}
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        for col, lab in (("sc", "現行 sc"), ("sc_prev", "sc＋前走")):
            parts = []
            for Y in YEARS:
                ty = t[t.y == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            x = pd.concat(parts)
            res[lab].append((x.place_x.mean(), x.place.mean(), x.win.mean(), (x.fin <= 3).mean() * 100,
                             *[x[x.y == Y].place_x.mean() for Y in YEARS]))
    for lab, v in res.items():
        a = np.array(v)
        yr = " / ".join(f"{a[:, 4 + i].mean():+.1f}" for i in range(len(YEARS)))
        print(f"sc≥{N}相当 {lab}: 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 年別[{yr}] 複勝{a[:, 1].mean():.1f}% 単勝{a[:, 2].mean():.1f}% 3着内率{a[:, 3].mean():.1f}%")
