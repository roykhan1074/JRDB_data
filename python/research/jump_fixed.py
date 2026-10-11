# -*- coding: utf-8 -*-
"""
障害指数の固定ルール（jump_wf.py の最新年=2026年の選定結果）で全年を採点し、点数ごとの成績を出す（研究用）。
2021〜2025年は要素の選定に使ったデータそのものなので先読みを含む参考値。2026年だけは選定に使っていない（先読みなし）。
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 260)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jump_screen import load, candidates
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
chosen = pd.read_pickle(os.path.join(ROOT, ".scratch", "jump_chosen.pkl"))
rule = chosen[max(chosen)]
d = load(); C = candidates(d)
d["pts"] = 0
print(f"## 固定ルール（{max(chosen)}年時点の選定、{len(rule)}要素）")
for k, eff in sorted(rule.items(), key=lambda kv: -kv[1]):
    p = int(np.sign(eff) * (1 if abs(eff) < 10 else 2))
    d["pts"] += C[k].astype(int) * p
    print(f"  {p:+d}点  {k[1]}（選定時の複勝の同オッズ差 {eff:+.1f}pt）")
if len(sys.argv) > 1:   # 指定日の全馬の点数を JSON で出す（本番 API との突き合わせ用）
    import json
    t = d[d.ymd == sys.argv[1]]
    print("JSON " + json.dumps({f"{r.rid}-{int(r.uma)}": int(r.pts) for r in t.itertuples()}))
    sys.exit()
d = d[d.y >= 2021]
d.to_pickle(os.path.join(ROOT, ".scratch", "jump_fixed_scored.pkl"))
nr = d.rid.nunique()
print("\n点数の分布", d.pts.value_counts().sort_index().to_dict())


def tab(t, title, years):
    rows = []
    B = [(-99, -6, "−6以下"), (-5, -4, "−5〜−4"), (-3, -2, "−3〜−2"), (-1, -1, "−1"), (0, 0, "0"), (1, 1, "+1"), (2, 2, "+2"), (3, 3, "+3"), (4, 99, "+4以上")]
    for lo, hi, lab in B:
        s = t[t.pts.between(lo, hi)]
        if not len(s):
            continue
        hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
        r = dict(点数=lab, n=len(s), 一R平均=len(s) / t.rid.nunique(), オッズ中央=s.kijun_odds.median(), 三着内率=s.top3.mean() * 100,
                 中止率=s.chushi.mean() * 100, 複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / len(s),
                 単勝=s.win.mean(), 単差=s.win_x.mean())
        for Y in years:
            r[f"複勝{Y % 100}"] = s[s.y == Y].place.mean()
        rows.append(r)
    print(f"\n## {title}"); print(pd.DataFrame(rows).round(1).to_string(index=False))


tab(d, "全期間 2021〜2026（2021〜2025は先読みを含む参考値）", [2021, 2022, 2023, 2024, 2025, 2026])
tab(d[d.y == 2026], "2026年のみ（選定に使っていない＝先読みなし）", [2026])
