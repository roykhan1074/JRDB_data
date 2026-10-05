# -*- coding: utf-8 -*-
"""
新EX指数（改良4: 複勝・オッズ帯補正・縮小k=300・コース別なし・調教評価照合修正）を
walk-forward（毎年直前年まで集計）で2024-2026に付け、旧EX指数と同じ目盛りに換算して
研究用テーブル T_ANABA_SCORE_WF2 に書き込む。sc の再検証（sc_wf.js wf2）に使う。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd, mysql.connector
import ex_improve_wf as M

# 新スコア(生値) → 旧EX指数の目盛り への換算点（2024-26で「旧EX指数がその値以上の馬の割合」が一致する新スコア）
KNOTS = [(4.08, 0.0), (8.47, 15.0), (18.27, 50.0), (31.11, 100.0)]


def to_ex_scale(raw):
    raw = np.asarray(raw, dtype=float)
    xs = [k[0] for k in KNOTS]; ys = [k[1] for k in KNOTS]
    out = np.interp(raw, xs, ys)
    lo_slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
    hi_slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
    out = np.where(raw < xs[0], ys[0] + (raw - xs[0]) * lo_slope, out)
    out = np.where(raw > xs[-1], ys[-1] + (raw - xs[-1]) * hi_slope, out)
    return np.round(out, 1)


if __name__ == "__main__":
    d = M.prep(M.load())
    kw = dict(target="place", shrink_k=300, excess=True, use_course=False, chk_mode="fix")
    t = pd.concat([M.score_year(d, Y, **kw) for Y in range(2021, 2027)])
    t["ex"] = to_ex_scale(t["score"])
    e = {}
    for l in open(os.path.join(M.ROOT, ".env"), encoding="utf-8"):
        l = l.strip()
        if l and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); e[k] = v
    c = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
    cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS T_ANABA_SCORE_WF2")
    cur.execute("CREATE TABLE T_ANABA_SCORE_WF2 LIKE T_ANABA_SCORE")
    rows = [(r.course_code, r.year_code, r.kai, r.day_code, r.race_num, r.uma_num, float(r.ex), float(r.ex))
            for r in t.itertuples()]
    for i in range(0, len(rows), 5000):
        cur.executemany("INSERT INTO T_ANABA_SCORE_WF2 (course_code,year_code,kai,day_code,race_num,uma_num,overall_score,course_score) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows[i:i + 5000])
    c.commit()
    cur.execute("SELECT year_code, COUNT(*) FROM T_ANABA_SCORE_WF2 GROUP BY year_code")
    print(cur.fetchall())
    # 換算後の帯ごとの成績（同オッズ帯平均との差）
    for p in ("win", "place"):
        t[p + "_b"] = t.groupby(["year", "ob"])[p].transform("mean")
    t["band"] = pd.cut(t.ex, [-1e9, 0, 15, 50, 100, 1e9], right=False, labels=["0未満", "0-15", "15-50", "50-100", "100以上"])
    print("\n新EX指数（換算後）の帯別：2024/2025/2026 の複勝回収率の同オッズ帯平均との差、3年計、単勝差")
    for b, x in t.groupby("band", observed=True):
        yr = " / ".join(f"{(x[x.year == Y].place.mean() - x[x.year == Y].place_b.mean()):+.1f}" for Y in [2024, 2025, 2026])
        print(f"{b}: n={len(x):,} 複勝{x.place.mean():.1f}%（平均{x.place_b.mean():.1f}、差{x.place.mean()-x.place_b.mean():+.1f}）年別[{yr}] 単勝差{x.win.mean()-x.win_b.mean():+.1f}")
