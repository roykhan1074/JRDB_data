# -*- coding: utf-8 -*-
"""
factor-recovery.html に載せる「EX指数・本命指数・sc の帯別成績」（先読みなしの検証値）を作る（研究用）。
- EX指数・本命指数: 毎年、直前の年までのデータで集計し直した版（T_ANABA_SCORE_WF2 / T_HONMEI_SCORE_WF2）
- sc: 同じ EX/本命指数と、騎手×厩舎・厩舎成績はその日より前の結果だけで計算（sc_wf.js wf4 の出力）
- 期間 2022〜2026、芝ダ、新馬除外。同じオッズ帯の平均 = 同じ年・同じ基準オッズ帯の全馬の平均
出力: .scratch/factor_recovery_rows.json（HTML の tbody に入れる行）
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]

d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))
d = d[(d.y >= 2022) & (d.shinba == 0) & d.odds.between(1, 999)].copy()
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False)
d["place_b"] = d.groupby(["y", "ob"], observed=True).place.transform("mean")
d["fin"] = pd.to_numeric(d.fin, errors="coerce")


def rr_class(v):
    return "rr-100up" if v >= 100 else "rr-90up" if v >= 90 else "rr-80up" if v >= 80 else "rr-low"


def rows(groups, order):
    out = []
    for lab in order:
        if lab not in groups:
            continue
        x = groups[lab]
        diff = x.place.mean() - x.place_b.mean()
        yr = []
        for Y in YEARS:
            xy = x[x.y == Y]
            yr.append(f"{xy.place.mean() - xy.place_b.mean():+.1f}" if len(xy) else "—")
        out.append(dict(label=lab, n=len(x), win_rate=(x.fin == 1).mean() * 100, place_rate=(x.fin <= 3).mean() * 100,
                        win_rr=x.win.mean(), place_rr=x.place.mean(), base=x.place_b.mean(), diff=diff, years=yr))
    return out


def to_html(rs):
    h = []
    for r in rs:
        yrs = "".join(f"<td>{v}</td>" for v in r["years"])
        h.append(f'<tr><td class="label-cell">{r["label"]}</td><td>{r["n"]:,}</td><td>{r["win_rate"]:.1f}%</td><td>{r["place_rate"]:.1f}%</td>'
                 f'<td><span class="{rr_class(r["win_rr"])}">{r["win_rr"]:.1f}%</span></td>'
                 f'<td><span class="{rr_class(r["place_rr"])}">{r["place_rr"]:.1f}%</span></td>'
                 f'<td>{r["base"]:.1f}%</td><td><b>{r["diff"]:+.1f}</b></td>{yrs}</tr>')
    return "\n".join(h)


# --- EX指数（基準オッズ10倍以上） / 本命指数（10倍未満）: sc の出力に入っている検証用の値（ex, hm）を使う
ex = d[d.odds >= 10].dropna(subset=["ex"]).copy()
ex["band"] = pd.cut(ex.ex, [-1e9, 0, 15, 50, 100, 1e9], right=False, labels=["0未満", "0〜15", "15〜50", "50〜100", "100以上"]).astype(str)
hm = d[d.odds < 10].dropna(subset=["hm"]).copy()
hm["band"] = pd.cut(hm.hm, [-1e9, 0, 10, 30, 50, 1e9], right=False, labels=["0未満", "0〜10", "10〜30", "30〜50", "50以上"]).astype(str)
sc = d.copy()
sc["band"] = sc.sc.clip(-1, 12).astype(int).map(lambda v: "−1以下" if v == -1 else ("12以上" if v == 12 else str(v)))

res = {
    "ex": to_html(rows(dict(tuple(ex.groupby("band"))), ["0未満", "0〜15", "15〜50", "50〜100", "100以上"])),
    "honmei": to_html(rows(dict(tuple(hm.groupby("band"))), ["0未満", "0〜10", "10〜30", "30〜50", "50以上"])),
    "sc": to_html(rows(dict(tuple(sc.groupby("band"))), ["−1以下"] + [str(i) for i in range(0, 12)] + ["12以上"])),
}
json.dump(res, open(os.path.join(ROOT, ".scratch", "factor_recovery_rows.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in res.items():
    print(f"== {k}: {v.count('<tr>')}行")
print(res["ex"].split("\n")[-1])
