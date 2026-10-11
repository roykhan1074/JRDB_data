# -*- coding: utf-8 -*-
"""
一変指数（ippen_wf.py の POP=all, ALPHA=3000, TARGET=place_x 版）の評価（研究用）。
1) 仮説の記述確認: 穴馬で3着内に来た馬は、穴馬全体と比べてどのトリガーを多く持つか
2) オッズ帯別の帯別成績
3) sc との組み合わせ（sc は .scratch/sc_wf_wf4.json、先読みなし）
4) 実例
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ippen_screen import triggers
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
d = pd.read_pickle(os.path.join(ROOT, ".scratch", "ippen_scored_place_x_3000_all.pkl"))
t = d[d.y.isin(YEARS)].copy()
t["pct"] = t.groupby("y").ippen.rank(pct=True)   # 全馬の中での順位（％）


def summarize(s, lab):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    whit = s[s.win > 0].win.sort_values(ascending=False); kw = max(1, round(len(whit) * .01))
    r = dict(区分=lab, n=len(s), オッズ中央=s.odds.median(), 三着内率=(s.fin <= 3).mean() * 100, 勝率=(s.fin == 1).mean() * 100,
             複勝=s.place.mean(), 複_平均=s.place_b.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / len(s),
             単勝=s.win.mean(), 単_平均=s.win_b.mean(), 単差=s.win_x.mean(), 単除外=(s.win.sum() - whit.head(kw).sum()) / len(s))
    for Y in YEARS:
        r[f"複差{Y % 100}"] = s[s.y == Y].place_x.mean()
    r["複差プラス年"] = sum(r[f"複差{Y % 100}"] > 0 for Y in YEARS)
    return r


BANDS = [("上位1%", .99, 1.01), ("上位1〜5%", .95, .99), ("上位5〜10%", .90, .95), ("上位10〜25%", .75, .90), ("中位25〜75%", .25, .75), ("下位25%", 0, .25)]

# 1) 仮説の記述確認
T = triggers(d.loc[t.index])
a = t.odds >= 10
geki = a & (t.fin <= 3)
rows = []
for k, m in T.items():
    m = m.loc[t.index]
    rows.append(dict(トリガー=k, 穴馬全体での割合=m[a].mean() * 100, 穴で3着内の馬での割合=m[geki].mean() * 100))
r = pd.DataFrame(rows)
r["倍率"] = r.穴で3着内の馬での割合 / r.穴馬全体での割合
print("## 1) 穴馬（基準10倍以上）で3着内に来た馬は、どのトリガーを多く持っているか（2022-2026）")
print(r.sort_values("倍率", ascending=False).round(2).to_string(index=False))
anych = np.zeros(len(t), bool)
for k in ("芝→ダ", "ダ→芝", "距離400m以上短縮", "距離200m短縮", "距離200m延長", "距離400m以上延長", "競馬場替わり", "休み明け(中8〜11週)",
          "休み明け(中12〜23週)", "休み明け(中24週以上)", "乗り替わり", "ブリンカー初装着", "転厩", "厩舎指数 +10以上良化", "厩舎指数 +20以上良化",
          "調教指数 +10以上良化", "調教指数 +20以上良化", "情報指数 +1.5以上良化", "情報指数 +3以上良化"):
    anych |= T[k].loc[t.index].to_numpy()
print(f"\n何らかの変化（条件・休み明け・乗り替わり・指数良化など19種のどれか）がある割合: 穴馬全体 {anych[a].mean()*100:.1f}% / 穴で3着内 {anych[geki].mean()*100:.1f}%")

# 2) 帯別（穴馬全体・オッズ帯別・全馬）
for title, base in [("穴馬（基準10倍以上）", t[t.odds >= 10]), ("基準10〜20倍", t[(t.odds >= 10) & (t.odds < 20)]),
                    ("基準20〜50倍", t[(t.odds >= 20) & (t.odds < 50)]), ("基準50倍以上", t[t.odds >= 50]),
                    ("基準10倍未満", t[t.odds < 10]), ("全馬", t)]:
    b = base.copy(); b["p"] = b.groupby("y").ippen.rank(pct=True)
    print(f"\n## 2) {title}（帯はこの中での各年の順位％）")
    print(pd.DataFrame([summarize(b[(b.p > lo) & (b.p <= hi)], lab) for lab, lo, hi in BANDS]).round(1).to_string(index=False))

# 3) sc との組み合わせ
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))[["rid", "uma", "sc"]]
u = t.merge(sc, on=["rid", "uma"], how="inner")
u["ip_lo"] = u.pct <= .25; u["ip_hi"] = u.pct > .75
print(f"\n## 3) sc × 一変指数（sc が付いている {len(u):,}頭、一変の上位/下位は全馬の中での順位）")
rows = []
for N in (4, 6, 7, 9):
    s = u[u.sc >= N]
    rows += [summarize(s, f"sc≥{N} 全体"), summarize(s[~s.ip_lo], f"sc≥{N} 一変下位25%を除く"),
             summarize(s[s.ip_lo], f"sc≥{N} のうち一変下位25%"), summarize(s[s.ip_hi], f"sc≥{N} のうち一変上位25%")]
print(pd.DataFrame(rows).round(1).to_string(index=False))
t.to_pickle(os.path.join(ROOT, ".scratch", "ippen_eval_t.pkl"))
