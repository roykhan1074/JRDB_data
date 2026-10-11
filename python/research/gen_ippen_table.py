# -*- coding: utf-8 -*-
"""
factor-recovery.html の「一変シグナル」パネルの表（先読みなしの検証値）を作る（研究用）。
- 値は ippen_plus_wf.py（POOL=theory, WEIGHT=count）の walk-forward 結果: 毎年、その年より前のデータだけで
  採用する要素としきい値を選び直し、その年の馬に当てはまる数を付けたもの（.scratch/ippen_plus_scored.pkl）。
- 表示区分は出馬表と同じ: A = 4個以上 / B = 3個 / 2個 / 1個 / 0個
- 期間 2022〜2026、芝ダ、新馬除外、前走がJRAにある馬。同じオッズ帯の平均 = 同じ年・同じ基準オッズ帯の全馬の平均
出力: .scratch/ippen_table_rows.json（HTML の tbody に入れる行。全馬 / 穴馬）
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
ORDER = ["A 4個〜", "B 3個", "2個", "1個", "0個"]


def rr_class(v):   # gen_factor_recovery_tables.py と同じ
    return "rr-100up" if v >= 100 else "rr-90up" if v >= 90 else "rr-80up" if v >= 80 else "rr-low"


def to_html(x):
    h = []
    for lab in ORDER:
        g = x[x.band == lab]
        yrs = "".join(f"<td>{g[g.y == Y].place_x.mean():+.1f}</td>" for Y in YEARS)
        win_rr, place_rr = g.win.mean(), g.place.mean()
        h.append(f'<tr><td class="label-cell">{lab}</td><td>{len(g):,}</td><td>{(g.fin == 1).mean() * 100:.1f}%</td><td>{(g.fin <= 3).mean() * 100:.1f}%</td>'
                 f'<td><span class="{rr_class(win_rr)}">{win_rr:.1f}%</span></td>'
                 f'<td><span class="{rr_class(place_rr)}">{place_rr:.1f}%</span></td>'
                 f'<td>{g.place_b.mean():.1f}%</td><td><b>{g.place_x.mean():+.1f}</b></td>{yrs}</tr>')
    return "\n".join(h)


d = pd.read_pickle(os.path.join(ROOT, ".scratch", "ippen_plus_scored.pkl"))
d = d[d.y.isin(YEARS) & d.plus.notna()].copy()
d["band"] = d.plus.map(lambda v: "A 4個〜" if v >= 4 else "B 3個" if v == 3 else f"{int(v)}個")
res = {"all": to_html(d), "ana": to_html(d[d.odds >= 10])}
json.dump(res, open(os.path.join(ROOT, ".scratch", "ippen_table_rows.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in res.items():
    print(f"== {k}"); print(v)
