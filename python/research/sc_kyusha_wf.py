# -*- coding: utf-8 -*-
"""
厩舎指数のシグナルを sc（現行・先読みなし版 .scratch/sc_wf_wf4.json）に加えると上位が良くなるかを検証（研究用）。
- 候補は1つずつ加える（重なる候補を同時に入れると点数が不安定になるため）
- 点数は毎年 Y について Y年より前のデータだけで決める:
  「現行 sc の各点数をダミーにした回帰」に候補を加えたときの正味の効果 ÷ 4 を四捨五入（sc の+1 ≒ 複勝+4pt）
- 比較: 現行 sc≥N と同じ頭数（同点の乱数30通りの平均と幅）、しきい値そのもの
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import load, prep, ROOT  # noqa
import numpy as np, pandas as pd

k = prep(load())[["rid", "uma", "ki", "ki_rank", "ninki", "idm_rank", "ki_dev", "ky_hyoka", "ky_rank", "p_ki"]]
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))
d = sc[(sc.shinba == 0) & (sc.y >= 2021) & sc.odds.between(1, 999)].merge(k, on=["rid", "uma"], how="left").reset_index(drop=True)
print(f"結合 {len(d):,}頭（厩舎指数あり {d.ki.notna().mean()*100:.1f}%）")
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]

CANDS = {
    "IDMも厩舎も人気より3上": ((d.ninki - d.idm_rank) >= 3) & ((d.ninki - d.ki_rank) >= 3),
    "前走から厩舎指数-15以下": (d.ki - d.p_ki) <= -15,
    "【減点】厩舎指数がレース平均-15以下": d.ki_dev < -15,
    "【減点】厩舎ランク8": d.ky_rank == "8",
    "【減点】厩舎評価4": d.ky_hyoka == "4",
}
YEARS = [2022, 2023, 2024, 2025, 2026]


def add_signal(flag):
    f = flag.fillna(False).astype(float).to_numpy()
    new = d.sc.astype(float).copy()
    info = []
    for Y in YEARS:
        trm = (d.y < Y).to_numpy()
        Xs = pd.get_dummies(d.sc.clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
        X = np.column_stack([Xs, f])
        beta, *_ = np.linalg.lstsq(X[trm], d.place_x.to_numpy()[trm], rcond=None)
        pts = int(np.round(beta[-1] / 4))
        m = (d.y == Y).to_numpy()
        new[m] = d.sc[m] + pts * f[m]
        info.append(f"{Y}:{beta[-1]:+.1f}→{pts:+d}")
    return new, " ".join(info)


def top_same_n(t, col, N, seeds=30):
    out = []
    for seed in range(seeds):
        tie = np.random.default_rng(seed).random(len(t))
        tt = t.assign(tie=tie)
        parts = []
        for Y in YEARS:
            ty = tt[tt.y == Y]; n = int((ty.sc >= N).sum())
            parts.append(ty.sort_values([col, "tie"], ascending=False).head(n))
        x = pd.concat(parts)
        out.append((x.place_x.mean(), x.place.mean(), x.win.mean(), x.win_x.mean(),
                    *[x[x.y == Y].place_x.mean() for Y in YEARS]))
    return np.array(out)


t = d[d.y.isin(YEARS)].copy()
for lab, flag in CANDS.items():
    f = flag.fillna(False)
    ft = f[t.index]
    print(f"\n## 候補: {lab}（2022〜26 該当 {int(ft.sum()):,}頭、複勝差 {t[ft].place_x.mean():+.1f}）")
    # 現行 sc の点数別に、候補あり/なしの差（sc に無い上乗せがあるか）
    rows = []
    for lo, hi in ((-9, 2), (3, 5), (6, 8), (9, 99)):
        m = t.sc.between(lo, hi)
        rows.append(f"sc{lo if lo > -9 else '≤'}{'' if lo == -9 else '〜'}{hi if hi < 99 else '+'}: あり{t[m & ft].place_x.mean():+.1f}(n={int((m & ft).sum())}) なし{t[m & ~ft].place_x.mean():+.1f}")
    print("  sc点数帯ごとの複勝差 → " + " / ".join(rows))
    newsc, info = add_signal(flag)
    print("  毎年の正味効果と加点: " + info)
    t["sc_new"] = newsc[t.index]
    for N in (6, 7, 8, 9):
        a = top_same_n(t, "sc", N); b = top_same_n(t, "sc_new", N)
        print(f"  sc≥{N}相当: 現行 差{a[:,0].mean():+.1f}（幅{a[:,0].min():+.1f}〜{a[:,0].max():+.1f}）複勝{a[:,1].mean():.1f}% 単勝{a[:,2].mean():.1f}%"
              f" ｜ 新 差{b[:,0].mean():+.1f}（幅{b[:,0].min():+.1f}〜{b[:,0].max():+.1f}）複勝{b[:,1].mean():.1f}% 単勝{b[:,2].mean():.1f}%"
              f" ｜ 新の年別 " + "/".join(f"{v:+.1f}" for v in b[:, 4:].mean(axis=0)))
