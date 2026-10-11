# -*- coding: utf-8 -*-
"""
新馬戦の指数: walk-forward 検証（研究用）。jump_wf.py と同じ点数方式。
- 候補は newbie_screen.candidates()（市場=オッズ帯そのものは除く）。
- 毎年 Y について、学習期間 = 2021年〜Y-1年（2020年は父・厩舎などの累積成績がまだ少ないので使わない）。
- 点数方式: 学習期間で「複勝の同オッズ帯平均との差」の絶対値が MIN_EFF 以上、n≥300、学習期間の各年で向きが揃っている
  （2年以下なら全年、3年以上ならマイナスの年が1年以下）候補を選び、|差|<10 → ±1点、≥10 → ±2点。
  しきい値違いの候補（名前の数字だけ違うもの）は同じ概念として、重なりがあれば最も効果の大きい1つだけ使う。
- 比較: リッジ回帰版（全候補を一度に推定）。
- 評価: Y年の馬について、点数別・レース内1位別の単勝・複勝回収率と同オッズ帯平均との差。
"""
import sys, io, os, re
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newbie_screen import load, candidates
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
MIN_EFF = float(os.environ.get("MIN_EFF", "4"))
ALPHA = float(os.environ.get("ALPHA", "300"))


def summarize(s, lab):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    whit = s[s.win > 0].win.sort_values(ascending=False); kw = max(1, round(len(whit) * .01))
    r = dict(区分=lab, n=len(s), 年平均=len(s) / len(YEARS), オッズ中央=s.kijun_odds.median(), 三着内率=s.top3.mean() * 100, 勝率=(s.fin == 1).mean() * 100,
             複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / max(len(s), 1),
             単勝=s.win.mean(), 単差=s.win_x.mean(), 単除外=(s.win.sum() - whit.head(kw).sum()) / max(len(s), 1))
    for Y in YEARS:
        r[f"複勝{Y % 100}"] = s[s.y == Y].place.mean()
    for Y in YEARS:
        r[f"単勝{Y % 100}"] = s[s.y == Y].win.mean()
    return r


if __name__ == "__main__":
    d = load()
    C = {k: v.to_numpy() for k, v in candidates(d).items() if not k[0].startswith("1.")}
    fam = {}
    for k in C:
        fam.setdefault(k[0] + ":" + re.sub(r"[0-9.]+", "N", k[1]), []).append(k)
    y = d.y.to_numpy(); px = d.place_x.to_numpy()
    d["pts"] = np.nan; d["ridge"] = np.nan
    chosen = {}
    names = list(C)
    X = np.column_stack([C[k].astype(np.float32) for k in names])
    for Y in YEARS:
        tr = (y >= 2021) & (y < Y)
        prior = sorted(set(y[tr]))
        sel = {}
        for k, m in C.items():
            mm = m & tr
            if mm.sum() < 300:
                continue
            eff = px[mm].mean()
            if abs(eff) < MIN_EFF:
                continue
            signs = [np.sign(px[mm & (y == p)].mean()) for p in prior if (mm & (y == p)).sum() > 0]
            opp = sum(s != np.sign(eff) for s in signs)
            if (len(prior) <= 2 and opp > 0) or opp > 1:
                continue
            sel[k] = eff
        # しきい値違い（同じ概念）で重なるものは効果の大きい1つだけ
        final = {}
        for f, ks in fam.items():
            cand = sorted([k for k in ks if k in sel], key=lambda k: -abs(sel[k]))
            used = np.zeros(len(d), bool)
            for k in cand:
                if (C[k] & used & tr).any():
                    continue
                final[k] = sel[k]; used |= C[k]
        score = np.zeros(len(d))
        for k, eff in final.items():
            score += C[k] * np.sign(eff) * (1 if abs(eff) < 10 else 2)
        te = y == Y
        d.loc[te, "pts"] = score[te]
        chosen[Y] = final
        # リッジ
        mu = px[tr].mean(); Xt = X[tr]
        b = np.linalg.solve(Xt.T @ Xt + ALPHA * np.eye(X.shape[1]), Xt.T @ (px[tr] - mu))
        d.loc[te, "ridge"] = X[te] @ b
    print(f"## 毎年採用された要素と点数（その年より前の2021年以降のデータで選択、カッコは選んだ時点の複勝の同オッズ差pt）MIN_EFF={MIN_EFF}")
    allk = sorted({k for Y in YEARS for k in chosen[Y]}, key=lambda k: (k[0], k[1]))
    for k in allk:
        cells = []
        for Y in YEARS:
            if k in chosen[Y]:
                e = chosen[Y][k]; cells.append(f"{int(np.sign(e) * (1 if abs(e) < 10 else 2)):+d}({e:+.0f})")
            else:
                cells.append("  —   ")
        print(f"{k[0][:6]} {k[1]:<34} " + " ".join(f"{c:>9}" for c in cells))
    d.to_pickle(os.path.join(ROOT, ".scratch", "newbie_scored.pkl"))
    pd.to_pickle(chosen, os.path.join(ROOT, ".scratch", "newbie_chosen.pkl"))   # 年ごとの採用要素（本番の固定ルール = 最新年の選定結果）
    t = d[d.y.isin(YEARS)].copy()
    print("\n## 点数別（2022-2026）")
    rows = [summarize(t[t.pts <= -3], "−3以下")] + [summarize(t[t.pts == k], f"{k:+d}") for k in range(-2, 3)] + [summarize(t[t.pts >= 3], "+3以上"), summarize(t[t.pts >= 4], "+4以上")]
    print(pd.DataFrame(rows).round(1).to_string(index=False))
    for col, lab in (("pts", "点数"), ("ridge", "リッジ")):
        t["pct"] = t.groupby("y")[col].rank(pct=True, method="average")
        t["rk"] = t.groupby("rid")[col].rank(ascending=False, method="first")
        bands = [("上位10%", .9, 1.01), ("上位10〜25%", .75, .9), ("中位25〜50%", .5, .75), ("下位25〜50%", .25, .5), ("下位25%", 0, .25)]
        rows = [summarize(t[(t.pct > lo) & (t.pct <= hi)], b) for b, lo, hi in bands] + [summarize(t[t.rk == 1], "レース内1位"), summarize(t[t.rk <= 2], "レース内2位以内")]
        print(f"\n## {lab}の帯別（各年の順位％。同点は平均順位）")
        print(pd.DataFrame(rows).round(1).to_string(index=False))
