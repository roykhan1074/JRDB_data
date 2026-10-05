# -*- coding: utf-8 -*-
"""調教SP 上位条件の分解（研究用）。追切/仕上の順位×調教矢印などの年別の実回収率"""
import sys, os
sys.argv=['x']
src=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'chokyo_sp_wf.py'),encoding='utf-8').read().split('CUR = [')[0]
exec(src)
YRS=range(2020,2027)
def show(m,lab):
    s=v[m]
    if len(s)==0: return
    print(f"{lab}: n={len(s)}(年{len(s)/7:.0f}) 単勝{s.win.mean():.1f}% 複勝{s.place.mean():.1f}% 3着内{(s.fin<=3).mean()*100:.0f}% オッズ中央{s.odds.median():.1f} 単差{s.win_x.mean():+.1f} 複差{s.place_x.mean():+.1f} 1%除外 単{trim_mean(s.win)-s.win_bt.mean():+.1f} 複{trim_mean(s.place)-s.place_bt.mean():+.1f}")
    print("    年別 単/複: "+"  ".join(f"{Y}:{s[s.y==Y].win.mean():.0f}/{s[s.y==Y].place.mean():.0f}" for Y in YRS))
both1=(v.oi_rk==1)&(v.sh_rk==1)
show(both1,"追切1位×仕上1位")
for y in ["1","2","3","4"]: show(both1&(v.yaji==y),f"  ×矢印{y}")
show(both1&(v.zPt==0)&v.yaji.isin(["1","2"])&v.hob.isin(["A","B"]),"  ×矢印↑/↑↑×放牧先A/B")
show((v.oi_rk<=2)&(v.sh_rk<=2)&(v.yaji=="1"),"追切2位以内×仕上2位以内×矢印↑↑")
show((v.oi_rk<=3)&(v.sh_rk<=3)&(v.yaji=="1"),"追切3位以内×仕上3位以内×矢印↑↑")
show((v.yaji=="1"),"矢印↑↑（全体）")
show((v.oi_rk==1)&(v.yaji=="1"),"追切1位×矢印↑↑")
show((v.sh_rk==1)&(v.yaji=="1"),"仕上1位×矢印↑↑")

# 新方式（現行5要素）上位1%の中身
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chokyo_sp_wf.py'), encoding='utf-8').read().split('CUR = [')[1].join(['CUR = [', '']).split('# 下見')[0])
def wf_score2(feats, k=300):
    s = pd.Series(np.nan, index=v.index)
    for Y in [2022, 2023, 2024, 2025, 2026]:
        tr = v.y < Y; te = v.y == Y; tot = np.zeros(te.sum())
        for f in feats:
            g = v[tr].groupby(f).place_x.agg(["mean", "size"]); dev = (g["mean"] * g["size"] / (g["size"] + k)).to_dict()
            tot += v.loc[te, f].map(dev).fillna(0).to_numpy()
        s[te] = tot
    return s
v["s_cur"] = wf_score2(CUR)
t = v[v.y >= 2022].copy()
t["pct"] = t.s_cur.groupby(t.y).rank(ascending=False, pct=True)
top = t[t.pct <= .01]
print("\n上位1%の頭数", len(top), " 同点の数（その年の最高点と同じ点の頭数）:", t.groupby("y").apply(lambda s: (s.s_cur == s.s_cur.max()).sum()).to_dict())
print(top.groupby(["f_oi_rk", "f_sh_rk", "f_zpt", "f_yaji", "f_hob"]).size().sort_values(ascending=False).head(8))
for Y in range(2022, 2027):
    s = top[top.y == Y]; print(Y, len(s), f"単{s.win.mean():.0f} 複{s.place.mean():.0f}")
