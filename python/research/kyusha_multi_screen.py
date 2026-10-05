# -*- coding: utf-8 -*-
"""
厩舎指数の多角的な下見（研究用・DB書き込みなし）
基準: 同じ年・同じ基準オッズ帯の全馬の平均（複勝・単勝）との差（pt）。年ごと（2021-2026）に向きがそろうかを見る。
入力はすべて出走前に確定する値（T_KYI・T_CYB・前走のT_KYI/T_SED）。「調教師にしては高い」は前年までの平均と比べる（先読みなし）。
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, ".scratch", "kyusha_multi.pkl")
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]


def conn():
    e = {}
    for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        l = l.strip()
        if l and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); e[k] = v
    return mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])


def load():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    c = conn()
    J = lambda a: f"{a}.course_code=k.course_code AND {a}.year_code=k.year_code AND {a}.kai=k.kai AND {a}.day_code=k.day_code AND {a}.race_num=k.race_num"
    d = pd.read_sql(f"""
      SELECT b.ymd, CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, k.course_code,
             TRIM(k.blood_reg_num) AS horse, CAST(k.uma_num AS UNSIGNED) AS uma, TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist,
             TRIM(b.`class`) AS cls, TRIM(k.trainer_code) AS trainer, HEX(TRIM(k.trainer_belong)) AS belong,
             TRIM(k.kyusha_index) AS ki, TRIM(k.kyusha_hyoka) AS ky_hyoka, TRIM(k.kyusha_rank) AS ky_rank, TRIM(k.in_kyusha) AS in_ky,
             TRIM(k.idm) AS idm, TRIM(k.kijun_odds) AS odds, TRIM(k.kijun_ninki) AS ninki,
             TRIM(k.rotation) AS rot, TRIM(k.nyukyu_hashiri) AS nyu_n, TRIM(k.nyukyu_nichi_mae) AS nyu_d,
             TRIM(k.hohbokusaki_rank) AS hob, TRIM(k.yuso_kubun) AS yuso, TRIM(k.kyuyo_riyuu_code) AS kyuyo,
             TRIM(k.chokyo_yajirushi) AS yaji, TRIM(c.oi_index) AS oi, TRIM(c.shiage_index) AS shiage,
             TRIM(k.prev1_race_key) AS p1race, TRIM(k.prev1_seiseki_key) AS p1key,
             TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou, TRIM(s.win) AS win, TRIM(s.place) AS place
      FROM T_KYI k JOIN T_BAC b ON {J('b')} JOIN T_SED s ON {J('s')} AND s.umaban=k.uma_num
      LEFT JOIN T_CYB c ON {J('c')} AND c.uma_num=k.uma_num
      WHERE TRIM(b.tds_code) IN ('1','2')
    """, c)
    sed = pd.read_sql("""SELECT CONCAT(TRIM(blood_num), TRIM(ymd)) AS p1key, TRIM(order_of_finish) AS p_fin,
                                TRIM(win_odds_rank) AS p_ninki FROM T_SED""", c).drop_duplicates("p1key")
    c.close()
    d = d.merge(sed, on="p1key", how="left")
    # 前走時の厩舎指数（前走の T_KYI 行 = 前走レースキー + 血統登録番号）
    prev = d[["rid", "horse", "ki"]].rename(columns={"rid": "p1race", "ki": "p_ki"})
    prev["p1race"] = prev.p1race.str[:8]
    d["p1race"] = d.p1race.str[:8]
    d = d.merge(prev.drop_duplicates(["p1race", "horse"]), on=["p1race", "horse"], how="left")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    d.to_pickle(CACHE)
    return d


def num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.strip(), errors="coerce").to_numpy()


def prep(d):
    d = d.copy()
    for col in ("ki", "idm", "odds", "ninki", "rot", "nyu_n", "nyu_d", "oi", "shiage", "fin", "win", "place", "p_fin", "p_ninki", "p_ki"):
        d[col] = num(d[col])
    d = d[(d.fin > 0) & (d.odds >= 1) & (d.odds < 999)].copy()
    ok = d.ijou.isin(["0", ""])
    d["win"] = np.where(ok, np.nan_to_num(d.win), 0.0)
    d["place"] = np.where(ok, np.nan_to_num(d.place), 0.0)
    d["y"] = d.ymd.str[:4].astype(int)
    d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100, 1000], right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_x"] = d[p] - d.groupby(["y", "ob"])[p].transform("mean")
    g = d.groupby("rid")
    d["heads"] = g.ki.transform("size")
    d["ki_rank"] = g.ki.rank(ascending=False, method="min")
    d["idm_rank"] = g.idm.rank(ascending=False, method="min")
    d["oi_rank"] = g.oi.rank(ascending=False, method="min")
    d["ki_dev"] = d.ki - g.ki.transform("mean")
    srt = g.ki.transform(lambda v: v.nlargest(2).iloc[-1] if len(v) > 1 else np.nan)
    d["ki_lead"] = np.where(d.ki_rank == 1, d.ki - srt, np.nan)
    # 調教師にしては高いか（前年までのその調教師の平均厩舎指数との差）
    ym = d.groupby(["trainer", "y"]).ki.agg(["sum", "count"]).reset_index().sort_values(["trainer", "y"])
    ym["cs"] = ym.groupby("trainer")["sum"].cumsum() - ym["sum"]
    ym["cc"] = ym.groupby("trainer")["count"].cumsum() - ym["count"]
    ym["tmean"] = np.where(ym.cc >= 50, ym.cs / ym.cc, np.nan)
    d = d.merge(ym[["trainer", "y", "tmean"]], on=["trainer", "y"], how="left")
    d["ki_vs_tr"] = d.ki - d.tmean
    d["shinba"] = d.cls == "A1"
    return d


def show(x, col, title, min_n=300):
    t = x.groupby(col).agg(n=("place", "size"), 複勝=("place", "mean"), 複差=("place_x", "mean"), 単差=("win_x", "mean"))
    for Y in YEARS:
        t[str(Y)[2:]] = x[x.y == Y].groupby(col).place_x.mean()
    s = np.sign(t[[str(Y)[2:] for Y in YEARS]])
    t["複向き"] = (s == 1).sum(axis=1).astype(str) + "+/" + (s == -1).sum(axis=1).astype(str) + "-"
    tw = x.groupby([col, "y"]).win_x.mean().unstack()
    t["単勝+年数"] = (tw > 0).sum(axis=1)
    t = t[t.n >= min_n]
    print(f"\n### {title}")
    print(t.round(1).to_string())


def cut(v, edges, labels):
    return pd.cut(v, edges, labels=labels, right=False).astype(str)


if __name__ == "__main__":
    d = prep(load())
    x = d[d.y >= 2021].copy()
    print(f"対象 {len(x):,}頭（芝ダ、2021〜2026、新馬含む）。差 = 同年・同基準オッズ帯の平均との差(pt)。複向き = 6年中プラス/マイナスの年数")
    x["f_band"] = cut(x.ki, [-99, -10, 0, 10, 20, 30, 99], ["<-10", "-10~0", "0~10", "10~20", "20~30", "30~"])
    x["f_rank"] = np.select([x.ki_rank == 1, x.ki_rank <= 3, x.ki_rank <= 6], ["1位", "2-3位", "4-6位"], "7位~")
    x["f_lead"] = np.select([x.ki_lead >= 15, x.ki_lead >= 10, x.ki_lead >= 5, x.ki_lead >= 0], ["1位・2位と15+", "10-15", "5-10", "0-5"], "1位以外")
    x["f_dev"] = cut(x.ki_dev, [-99, -15, -5, 5, 15, 25, 99], ["<-15", "-15~-5", "±5", "5~15", "15~25", "25~"])
    gap = x.ninki - x.ki_rank
    x["f_ninki_gap"] = np.select([gap >= 8, gap >= 5, gap >= 3, gap > -3, gap > -5], ["人気より厩舎8+上", "5-7上", "3-4上", "±2", "3-4下"], "5+下")
    gi = x.idm_rank - x.ki_rank
    x["f_idm_gap"] = np.select([gi >= 8, gi >= 5, gi >= 3, gi > -3, gi > -5], ["IDMより厩舎8+上", "5-7上", "3-4上", "±2", "3-4下"], "5+下")
    dk = x.ki - x.p_ki
    x["f_dki"] = np.select([x.p_ki.isna(), dk >= 15, dk >= 5, dk > -5, dk > -15], ["前走なし", "+15以上", "+5~15", "±5", "-5~-15"], "-15以下")
    x["f_vs_tr"] = np.select([x.ki_vs_tr.isna(), x.ki_vs_tr >= 20, x.ki_vs_tr >= 10, x.ki_vs_tr >= 0, x.ki_vs_tr >= -10], ["NA", "自分の平均+20", "+10~20", "0~10", "-10~0"], "<-10")
    for col, title in [("f_band", "厩舎指数の帯"), ("f_rank", "厩舎指数のレース内順位"), ("f_lead", "1位の馬の2位との差"),
                       ("f_dev", "レース平均との差"), ("f_ninki_gap", "人気順位−厩舎指数順位"), ("f_idm_gap", "IDM順位−厩舎指数順位"),
                       ("f_dki", "前走時からの厩舎指数の増減"), ("f_vs_tr", "その調教師の過去平均との差"),
                       ("ky_hyoka", "厩舎評価コード"), ("ky_rank", "厩舎ランク"), ("in_ky", "厩舎印")]:
        show(x, col, title)

    # 条件との組み合わせ: 厩舎指数レース内上位(1〜3位) と 下位(7位〜)
    x["ctx_cls"] = x.cls.map(lambda c: {"A1": "新馬", "A3": "未勝利", "A2": "未勝利"}.get(c, c))
    x["ctx_rest"] = np.select([x.rot.isna() & x.p_fin.isna(), x.rot >= 10, x.rot >= 5], ["初出走", "休み明け(10週+)", "5-9週"], "4週以内")
    x["ctx_nyu"] = np.select([x.nyu_n == 1, x.nyu_n == 2, x.nyu_n >= 3], ["入厩1走目", "2走目", "3走目~"], "NA")
    x["ctx_odds"] = cut(x.odds, [1, 3, 7, 15, 30, 1000], ["~3倍", "3-7", "7-15", "15-30", "30~"])
    x["ctx_pfin"] = np.select([x.p_fin.isna(), x.p_fin <= 3, x.p_fin <= 5, x.p_fin <= 9], ["前走なし", "前走1-3着", "4-5着", "6-9着"], "10着~")
    x["ctx_dist"] = x.tds.map({"1": "芝", "2": "ダ"}) + cut(x.dist, [0, 1400, 1800, 9999], ["~1400", "1401-1800", "1801~"])
    x["ctx_heads"] = cut(x.heads, [0, 11, 15, 99], ["~10頭", "11-14頭", "15頭~"])
    x["ctx_yaji"] = x.yaji.fillna("NA")
    top = x[x.ki_rank <= 3]
    bot = x[x.ki_rank >= 7]
    for ctx, title in [("ctx_cls", "クラス"), ("ctx_rest", "間隔"), ("ctx_nyu", "入厩何走目"), ("hob", "放牧先ランク"),
                       ("yuso", "輸送区分"), ("belong", "所属(HEX)"), ("ctx_odds", "オッズ帯"), ("ctx_pfin", "前走着順"),
                       ("ctx_dist", "芝ダ×距離"), ("ctx_heads", "頭数"), ("ctx_yaji", "調教矢印"), ("kyuyo", "休養理由")]:
        show(top, ctx, f"厩舎指数レース内1〜3位 × {title}", min_n=400)
        show(bot, ctx, f"厩舎指数レース内7位以下 × {title}", min_n=400)
