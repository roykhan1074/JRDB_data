# -*- coding: utf-8 -*-
"""
新本命指数（複勝・オッズ帯補正・縮小k=300・コース別なし・調教照合修正）を walk-forward（毎年直前年まで集計）で
2024-2026に付け、旧本命指数と同じ割合の目盛りに換算して研究用テーブル T_HONMEI_SCORE_WF2 に書き込む。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd, mysql.connector
import honmei_improve_wf as H

# 新スコア(生値) → 旧本命指数の目盛り（2024-26で旧本命指数がその値以上の馬の割合と同じ割合になる新スコア）
KNOTS = [(0.19, 0.0), (2.61, 10.0), (6.56, 30.0), (9.73, 50.0)]


def to_scale(raw):
    raw = np.asarray(raw, dtype=float)
    xs = [k[0] for k in KNOTS]; ys = [k[1] for k in KNOTS]
    out = np.interp(raw, xs, ys)
    lo = (ys[1] - ys[0]) / (xs[1] - xs[0]); hi = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
    out = np.where(raw < xs[0], ys[0] + (raw - xs[0]) * lo, out)
    out = np.where(raw > xs[-1], ys[-1] + (raw - xs[-1]) * hi, out)
    return np.round(out, 1)


if __name__ == "__main__":
    d = H.prep(H.load())
    kw = dict(target="place", shrink_k=300, excess=True, use_course=False, chk_mode="fix")
    t = pd.concat([H.score_year(d, Y, **kw) for Y in range(2021, 2027)])
    t["hm"] = to_scale(t["score"])
    e = {}
    for l in open(os.path.join(H.ROOT, ".env"), encoding="utf-8"):
        l = l.strip()
        if l and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); e[k] = v
    c = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
    cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS T_HONMEI_SCORE_WF2")
    cur.execute("CREATE TABLE T_HONMEI_SCORE_WF2 LIKE T_HONMEI_SCORE")
    rows = [(r.course_code, r.year_code, r.kai, r.day_code, r.race_num, r.uma_num, float(r.hm), float(r.hm)) for r in t.itertuples()]
    for i in range(0, len(rows), 5000):
        cur.executemany("INSERT INTO T_HONMEI_SCORE_WF2 (course_code,year_code,kai,day_code,race_num,uma_num,overall_score,course_score) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows[i:i + 5000])
    c.commit()
    cur.execute("SELECT year_code, COUNT(*) FROM T_HONMEI_SCORE_WF2 GROUP BY year_code"); print(cur.fetchall())
    for p in ("win", "place"):
        t[p + "_b"] = t.groupby(["year", "ob"])[p].transform("mean")
    t["band"] = pd.cut(t.hm, [-1e9, 0, 10, 30, 50, 1e9], right=False, labels=["0未満", "0-10", "10-30", "30-50", "50以上"])
    print("\n新本命指数（換算後）の帯別：同オッズ帯平均との差（年別 2024/2025/2026）")
    for b, x in t.groupby("band", observed=True):
        f = lambda p: " / ".join(f"{(x[x.year == Y][p].mean() - x[x.year == Y][p + '_b'].mean()):+.1f}" for Y in [2024, 2025, 2026])
        ws = x.win.sort_values(ascending=False)
        print(f"{b}: n={len(x):,} 単勝{x.win.mean():.1f}%（平均{x.win_b.mean():.1f}、差{x.win.mean()-x.win_b.mean():+.1f}、上位10除外{ws.iloc[10:].sum()/len(x):.1f}）[{f('win')}]"
              f" 複勝{x.place.mean():.1f}%（平均{x.place_b.mean():.1f}、差{x.place.mean()-x.place_b.mean():+.1f}）[{f('place')}]")
