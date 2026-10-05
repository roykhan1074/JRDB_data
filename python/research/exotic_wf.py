# -*- coding: utf-8 -*-
"""
馬連・三連複の買い方ルールの回収率検証（研究用・DB書き込みなし）

- 各馬の1着確率: walk-forward予測（prob_wf.py の出力。予測年より前のデータのみで学習）
- 組み合わせ確率: Harville式（1着確率から2着・3着を順に条件付きで計算）
    モデル版  : モデルの1着確率から
    市場版    : 確定単勝オッズの逆数（レース内正規化）から
- 外れ組み合わせのオッズは無いため、「レース前に決まるルールで買う組み合わせを決め、
  当たればT_HJCの払戻、外れれば0」で回収率を計算する。
"""
import sys, io, os, itertools
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np
import pandas as pd
import mysql.connector

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
PRED = sys.argv[1] if len(sys.argv) > 1 else "prob_pred.pkl"


def env():
    e = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); e[k] = v
    return e


def load_hjc():
    cache = os.path.join(ROOT, ".scratch", "hjc.pkl")
    if os.path.exists(cache):
        return pd.read_pickle(cache)
    e = env()
    conn = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"],
                                   password=e["DB_PASS"], database=e["DB_NAME"])
    cols = ",".join([f"umaren_umaban_{i}, umaren_payout_{i}" for i in (1, 2, 3)] +
                    [f"sanrenpuku_umaban_{i}, sanrenpuku_payout_{i}" for i in (1, 2, 3)])
    h = pd.read_sql(f"SELECT CONCAT(course_code,year_code,kai,day_code,race_num) AS race_id, {cols} FROM T_HJC", conn)
    conn.close()
    h.to_pickle(cache)
    return h


def parse(h):
    um, sp = {}, {}
    for r in h.itertuples(index=False):
        d = r._asdict()
        a = {}
        for i in (1, 2, 3):
            s = str(d[f"umaren_umaban_{i}"] or "").strip()
            p = int(d[f"umaren_payout_{i}"] or 0)
            if len(s) == 4 and s != "0000" and p > 0:
                a[frozenset((int(s[:2]), int(s[2:])))] = p
        um[d["race_id"]] = a
        b = {}
        for i in (1, 2, 3):
            s = str(d[f"sanrenpuku_umaban_{i}"] or "").strip()
            p = int(d[f"sanrenpuku_payout_{i}"] or 0)
            if len(s) == 6 and s != "000000" and p > 0:
                b[frozenset((int(s[:2]), int(s[2:4]), int(s[4:])))] = p
        sp[d["race_id"]] = b
    return um, sp


def harville_pairs(p):
    n = len(p)
    out = {}
    for i, j in itertools.combinations(range(n), 2):
        out[(i, j)] = p[i] * p[j] / (1 - p[i]) + p[j] * p[i] / (1 - p[j])
    return out


def harville_trios(p):
    n = len(p)
    out = {}
    for i, j, k in itertools.combinations(range(n), 3):
        s = 0.0
        for a, b, c in itertools.permutations((i, j, k)):
            s += p[a] * p[b] / (1 - p[a]) * p[c] / (1 - p[a] - p[b])
        out[(i, j, k)] = s
    return out


def main():
    df = pd.read_pickle(os.path.join(ROOT, ".scratch", PRED))
    df = df[df["mkt_final"].notna()].copy()
    um, sp = parse(load_hjc())

    recs_u, recs_s = [], []
    for rid, g in df.groupby("race_id"):
        if rid not in um or not um[rid] or len(g) < 5:
            continue
        g = g.sort_values("uma_num")
        nums = g["uma_num"].astype(int).to_numpy()
        pm = g["p_y_win"].to_numpy(); pm = pm / pm.sum()
        pk = g["mkt_final"].to_numpy(); pk = pk / pk.sum()
        year = int(g["year"].iloc[0])
        # 市場の人気順（確定オッズ）
        rank_k = (-pk).argsort().argsort() + 1
        hm, hk = harville_pairs(pm), harville_pairs(pk)
        for (i, j), qm in hm.items():
            key = frozenset((nums[i], nums[j]))
            recs_u.append((rid, year, qm, hk[(i, j)], int(min(rank_k[i], rank_k[j])), int(max(rank_k[i], rank_k[j])),
                           um[rid].get(key, 0)))
        tm, tk = harville_trios(pm), harville_trios(pk)
        for (i, j, k), qm in tm.items():
            key = frozenset((nums[i], nums[j], nums[k]))
            rr = sorted((rank_k[i], rank_k[j], rank_k[k]))
            recs_s.append((rid, year, qm, tk[(i, j, k)], int(rr[0]), int(rr[1]), int(rr[2]), sp.get(rid, {}).get(key, 0)))

    U = pd.DataFrame(recs_u, columns=["race_id", "year", "q_model", "q_mkt", "r1", "r2", "pay"])
    S = pd.DataFrame(recs_s, columns=["race_id", "year", "q_model", "q_mkt", "r1", "r2", "r3", "pay"])
    for X in (U, S):
        X["ratio"] = X["q_model"] / X["q_mkt"]
        X["rk_model"] = X.groupby("race_id")["q_model"].rank(ascending=False, method="first")
        X["rk_mkt"] = X.groupby("race_id")["q_mkt"].rank(ascending=False, method="first")
    U.to_pickle(os.path.join(ROOT, ".scratch", "umaren_combos.pkl"))
    S.to_pickle(os.path.join(ROOT, ".scratch", "sanrenpuku_combos.pkl"))
    print(f"馬連 組み合わせ数={len(U):,} レース={U.race_id.nunique():,} / 三連複 組み合わせ数={len(S):,}")


if __name__ == "__main__":
    main()
