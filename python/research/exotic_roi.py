# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import pandas as pd, numpy as np
pd.set_option("display.width", 200)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
U = pd.read_pickle(os.path.join(ROOT, ".scratch", "umaren_combos.pkl"))
S = pd.read_pickle(os.path.join(ROOT, ".scratch", "sanrenpuku_combos.pkl"))
YEARS = [2022, 2023, 2024, 2025, 2026]


def roi_table(X, groups, label):
    """回収率(%) = 払戻合計 / (点数×100円)。グループ×年"""
    t = X.groupby(groups + ["year"], observed=True)["pay"].mean().unstack().reindex(columns=YEARS).round(1)
    t["全体"] = X.groupby(groups, observed=True)["pay"].mean().round(1)
    t["点数"] = X.groupby(groups, observed=True)["pay"].size()
    t["的中率%"] = (X.assign(h=X.pay > 0).groupby(groups, observed=True)["h"].mean() * 100).round(2)
    print(f"\n### {label}")
    print(t.to_string())


def rule(X, mask, label):
    d = X[mask]
    per = d.groupby("year")["pay"].mean().reindex(YEARS).round(1)
    races = d.race_id.nunique()
    print(f"{label:<48} " + " ".join(f"{v:>6}" for v in per.values) +
          f" | 全体{d.pay.mean():6.1f}% 点数{len(d):>8,} レース{races:>6,} 1レース平均{len(d)/max(races,1):.1f}点")


# 1) 値付けの癖: 人気の組み合わせ別（確定単勝オッズの人気順）
U["pop"] = U["r1"].clip(upper=6).astype(str) + "-" + pd.cut(U["r2"], [0, 2, 3, 4, 5, 6, 8, 10, 99], labels=["2", "3", "4", "5", "6", "7-8", "9-10", "11+"]).astype(str)
roi_table(U[U.r1 <= 3], ["r1", pd.cut(U[U.r1 <= 3]["r2"], [0, 2, 3, 4, 5, 6, 8, 10, 99])], "馬連: 人気の組み合わせ別 回収率（1頭目の人気 × 2頭目の人気）")

U["qb"] = pd.cut(U["q_mkt"], [0, .002, .005, .01, .02, .04, .07, .1, .15, 1])
roi_table(U, ["qb"], "馬連: 単勝オッズから計算した組み合わせ確率（市場）の帯別 回収率")
S["qb"] = pd.cut(S["q_mkt"], [0, .0005, .001, .002, .005, .01, .02, .04, .08, 1])
roi_table(S, ["qb"], "三連複: 単勝オッズから計算した組み合わせ確率（市場）の帯別 回収率")

# 2) モデルで選ぶ買い方
print("\n### 買い方ルール別 回収率（2022 2023 2024 2025 2026）")
for K in (1, 3, 5, 10):
    rule(U, U.rk_model <= K, f"馬連: モデル確率の上位{K}点")
    rule(U, U.rk_mkt <= K, f"馬連: 市場（単勝オッズ）確率の上位{K}点")
for r in (1.2, 1.5, 2.0):
    rule(U, (U.ratio >= r) & (U.rk_model <= 10), f"馬連: モデル上位10点のうち モデル/市場≥{r}")
    rule(U, (U.ratio >= r) & (U.q_model >= 0.02), f"馬連: モデル確率≥2% かつ モデル/市場≥{r}")
for K in (1, 5, 10, 20, 35):
    rule(S, S.rk_model <= K, f"三連複: モデル確率の上位{K}点")
    rule(S, S.rk_mkt <= K, f"三連複: 市場確率の上位{K}点")
for r in (1.2, 1.5, 2.0):
    rule(S, (S.ratio >= r) & (S.rk_model <= 20), f"三連複: モデル上位20点のうち モデル/市場≥{r}")
    rule(S, (S.ratio >= r) & (S.q_model >= 0.005), f"三連複: モデル確率≥0.5% かつ モデル/市場≥{r}")
