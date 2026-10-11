# -*- coding: utf-8 -*-
"""
障害戦: ファクターの下見（研究用）。
評価: 単勝・複勝回収率の「同じ基準オッズ帯の平均との差」（障害戦の中で、2020-2026年をまとめた帯別平均。年ごとの帯別平均は頭数が少なく不安定なため）、
      年別（2021-2026）のプラス年数、当たりの払戻上位1%を除いた複勝回収率、3着内率、競走中止率。
入力はすべてレース前に分かる値（今走の T_KYI/T_BAC/T_CYB、今走より前の T_SED）。結果は今走の T_SED のみ。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 1000)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]
BANDS = [1, 3, 5, 10, 20, 50, 1000]


def load():
    d = pd.read_pickle(os.path.join(ROOT, ".scratch", "jump_base.pkl"))
    d["ob"] = pd.cut(d.kijun_odds, BANDS, right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_b"] = d.groupby("ob")[p].transform("mean")
        d[p + "_x"] = d[p] - d[p + "_b"]
    num = lambda s: pd.to_numeric(s, errors="coerce")
    d["rot"] = num(d.rotation)
    for col, asc in (("idm", False), ("sogo_index", False), ("gekiso_index", False), ("joho_index", False), ("kyusha_index", False),
                     ("chokyo_index", False), ("oi_index", False), ("shiage_index", False), ("jidm_max", False), ("jidm_last", False),
                     ("futan_juryo", False), ("kijun_odds", True), ("kishu_index", False)):
        d[f"r_{col}"] = d.groupby("rid")[col].rank(ascending=asc, method="min")
    d["idm_gap"] = d.groupby("rid").idm.transform(lambda s: s.max() - s.nlargest(2).iloc[-1] if s.notna().sum() >= 2 else np.nan)
    d["j_rate"] = d.jockey_t3 / d.jockey_n
    d["j_chushi"] = d.jockey_ch / d.jockey_n
    d["j_plrr"] = d.jockey_pl / d.jockey_n
    d["t_rate"] = d.trainer_t3 / d.trainer_n
    d["t_plrr"] = d.trainer_pl / d.trainer_n
    d["gap_days"] = (pd.to_datetime(d.ymd, format="%Y%m%d") - pd.to_datetime(d.prev_ymd, format="%Y%m%d", errors="coerce")).dt.days
    d["c_sho_n"] = num(d.c_sho); d["c_saka_n"] = num(d.c_saka); d["c_w_n"] = num(d.c_w)
    d["bw_n"] = num(d.bw)
    return d


def candidates(d):
    C = {}
    first = d.c_jump.fillna(0) == 0
    pj = d.prev_tds == "3"; pf = d.prev_tds.isin(["1", "2"])
    pfin = d.prev_fin; pch = d.prev_ijou == "3"
    # ===== 市場
    M = "1.市場"
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        C[(M, f"基準オッズ{lo}〜{hi}倍")] = d.kijun_odds.between(lo, hi - 0.01)
    C[(M, "1番人気")] = d.r_kijun_odds == 1
    # ===== 能力（JRDB）
    A = "2.能力(JRDB)"
    for k in (1, 2, 3):
        C[(A, f"IDMレース内{k}位")] = d.r_idm == k
    C[(A, "IDM1位で2位と2以上の差")] = (d.r_idm == 1) & (d.idm_gap >= 2)
    C[(A, "IDM下位(レース内で下から3頭)")] = d.r_idm >= d.heads - 2
    C[(A, "総合指数1位")] = d.r_sogo_index == 1
    C[(A, "激走指数1位")] = d.r_gekiso_index == 1
    C[(A, "激走指数レース内3位以内")] = d.r_gekiso_index <= 3
    C[(A, "情報指数1位")] = d.r_joho_index == 1
    C[(A, "厩舎指数1位")] = d.r_kyusha_index == 1
    C[(A, "調教指数1位")] = d.r_chokyo_index == 1
    C[(A, "騎手指数1位")] = d.r_kishu_index == 1
    rk = d.r_kijun_odds
    C[(A, "人気順位−IDM順位≥3(IDMの割に人気薄)")] = (rk - d.r_idm) >= 3
    C[(A, "人気順位−IDM順位≤−3(IDMの割に人気)")] = (rk - d.r_idm) <= -3
    C[(A, "障害での最高IDMがレース内1位")] = d.r_jidm_max == 1
    C[(A, "障害での前回IDMがレース内1位")] = d.r_jidm_last == 1
    C[(A, "障害での前回IDMがレース内3位以内")] = d.r_jidm_last <= 3
    # ===== 障害の経験・適性
    E = "3.障害の経験"
    C[(E, "初障害")] = first
    C[(E, "障害2戦目")] = d.c_jump == 1
    C[(E, "障害3〜5戦目")] = d.c_jump.between(2, 4)
    C[(E, "障害6〜9戦目")] = d.c_jump.between(5, 8)
    C[(E, "障害10戦以上")] = d.c_jump >= 9
    C[(E, "障害で3着内経験あり")] = d.cj_top3 >= 1
    C[(E, "障害経験3戦以上で3着内なし")] = (d.c_jump >= 3) & (d.cj_top3 == 0)
    C[(E, "障害で勝利経験あり")] = d.cj_win1 >= 1
    C[(E, "障害で競走中止の経験あり")] = d.cj_chushi >= 1
    C[(E, "同じ競馬場の障害で3着内経験あり")] = d.cjc_top3 >= 1
    C[(E, "同じ競馬場の障害が初めて(障害経験あり)")] = (d.c_jump >= 1) & (d.cjc_n == 0)
    C[(E, "平地で3勝クラス以上を走った")] = d.flat_cls_max >= 3
    C[(E, "平地で2勝クラス以上を走った")] = d.flat_cls_max >= 2
    C[(E, "平地は未勝利のみ")] = d.flat_cls_max == 0
    C[(E, "平地で勝利経験あり")] = d.cf_win1 >= 1
    C[(E, "初障害×平地2勝クラス以上")] = first & (d.flat_cls_max >= 2)
    C[(E, "初障害×平地未勝利のみ")] = first & (d.flat_cls_max == 0)
    # ===== 前走
    P = "4.前走"
    C[(P, "前走障害で1着")] = pj & (pfin == 1)
    C[(P, "前走障害で2着")] = pj & (pfin == 2)
    C[(P, "前走障害で3着")] = pj & (pfin == 3)
    C[(P, "前走障害で4〜5着")] = pj & pfin.between(4, 5)
    C[(P, "前走障害で6着以下")] = pj & (pfin >= 6)
    C[(P, "前走障害で競走中止")] = pj & pch
    C[(P, "前走平地(障害経験あり)")] = pf & (d.c_jump >= 1)
    C[(P, "前走平地(初障害)")] = pf & first
    C[(P, "前走障害で着差0.5秒以内の負け")] = pj & (pfin >= 2) & (d.prev_wdiff <= 5)
    C[(P, "前走障害で2秒以上負け")] = pj & (d.prev_wdiff >= 20)
    C[(P, "前走障害勝ち→今回OP(昇級初戦)")] = pj & (pfin == 1) & (d.cls == "OP") & (d.prev_cls != "OP")
    C[(P, "前走と同じ競馬場")] = pj & (d.prev_course == d.course)
    C[(P, "2走前障害3着内→前走障害4着以下")] = (d.prev2_tds == "3") & (d.prev2_fin <= 3) & pj & (pfin >= 4)
    # ===== 状態（間隔・調教）
    S = "5.状態"
    for lo, hi, lab in ((0, 0, "連闘"), (1, 2, "中1〜2週"), (3, 5, "中3〜5週"), (6, 9, "中6〜9週"), (10, 19, "中10〜19週"), (20, 999, "中20週以上")):
        C[(S, lab)] = d.rot.between(lo, hi)
    C[(S, "追切指数1位")] = d.r_oi_index == 1
    C[(S, "仕上指数1位")] = d.r_shiage_index == 1
    C[(S, "追切指数レース内下位(下から3頭)")] = d.r_oi_index >= d.heads - 2
    C[(S, "調教矢印↑(1,2)")] = d.yaji.isin(["1", "2"])
    C[(S, "調教矢印↓(4,5)")] = d.yaji.isin(["4", "5"])
    C[(S, "調教量評価A")] = d.ryo == "A"
    C[(S, "調教量評価C/D")] = d.ryo.isin(["C", "D"])
    for k in (1, 2, 3):
        C[(S, f"障害練習{k}回以上")] = d.c_sho_n >= k
    C[(S, "障害練習なし")] = d.c_sho_n.fillna(0) == 0
    C[(S, "坂路調教あり")] = d.c_saka_n >= 1
    C[(S, "ウッド調教あり")] = d.c_w_n >= 1
    C[(S, "厩舎評価1・2(強気)")] = d.kyu_hyoka.isin(["1", "2"])
    C[(S, "厩舎評価4(弱気)")] = d.kyu_hyoka == "4"
    C[(S, "放牧先A")] = d.hob_r == "A"
    C[(S, "入厩1走目")] = pd.to_numeric(d.nyu_n, errors="coerce") == 1
    # ===== 騎手・厩舎（その日より前の障害成績）
    J = "6.騎手・厩舎"
    C[(J, "騎手の障害騎乗200回以上")] = d.jockey_n >= 200
    C[(J, "騎手の障害騎乗50回未満")] = d.jockey_n < 50
    C[(J, "騎手の障害3着内率30%以上(50回以上)")] = (d.jockey_n >= 50) & (d.j_rate >= 0.30)
    C[(J, "騎手の障害3着内率20%未満(50回以上)")] = (d.jockey_n >= 50) & (d.j_rate < 0.20)
    C[(J, "騎手の障害中止率6%以上(50回以上)")] = (d.jockey_n >= 50) & (d.j_chushi >= 0.06)
    C[(J, "騎手の障害中止率3%未満(50回以上)")] = (d.jockey_n >= 50) & (d.j_chushi < 0.03)
    C[(J, "騎手の障害複勝回収率90%以上(50回以上)")] = (d.jockey_n >= 50) & (d.j_plrr >= 90)
    C[(J, "見習い騎手")] = d.minarai.notna()
    C[(J, "厩舎の障害出走50回以上")] = d.trainer_n >= 50
    C[(J, "厩舎の障害3着内率30%以上(30回以上)")] = (d.trainer_n >= 30) & (d.t_rate >= 0.30)
    C[(J, "厩舎の障害複勝回収率90%以上(30回以上)")] = (d.trainer_n >= 30) & (d.t_plrr >= 90)
    C[(J, "厩舎の障害出走10回未満")] = d.trainer_n.fillna(0) < 10
    # ===== 馬・レース条件
    H = "7.馬・レース条件"
    for lo, hi, lab in ((3, 3, "3歳"), (4, 4, "4歳"), (5, 5, "5歳"), (6, 6, "6歳"), (7, 7, "7歳"), (8, 99, "8歳以上")):
        C[(H, lab)] = d.age.between(lo, hi)
    C[(H, "牝馬")] = d.sex == "2"
    C[(H, "せん馬")] = d.sex == "3"
    C[(H, "斤量がレース内で最も重い")] = d.r_futan_juryo == 1
    C[(H, "ブリンカー着用")] = d.blinker.notna()
    C[(H, "内枠(1〜2枠)")] = d.waku <= 2
    C[(H, "外枠(7〜8枠)")] = d.waku >= 7
    C[(H, "障害未勝利戦")] = d.cls.isin(["A1", "A2", "A3"])
    # 2026-10-12 修正: T_BAC.grade は 1〜3=G1〜G3, 4=重賞, 5=特別。以前は 5（OP特別）も重賞に数えていた
    jusho = d.grade.isin(["1", "2", "3", "4"])
    C[(H, "障害OP(重賞以外)")] = (d.cls == "OP") & ~jusho
    C[(H, "障害重賞")] = (d.cls == "OP") & jusho
    for cc, nm in (("06", "中山"), ("08", "京都"), ("05", "東京"), ("04", "新潟"), ("10", "小倉"), ("03", "福島"), ("09", "阪神"), ("07", "中京")):
        C[(H, f"{nm}")] = d.course == cc
    C[(H, "距離3000m以上")] = d.dist >= 3000
    C[(H, "11頭以上")] = d.heads >= 11
    C[(H, "脚質 逃げ")] = d.kya == "1"
    C[(H, "脚質 先行")] = d.kya == "2"
    C[(H, "脚質 差し・追込")] = d.kya.isin(["3", "4"])
    return {k: v.fillna(False).astype(bool) for k, v in C.items()}


def stats(s):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    yr = s.groupby("y").place_x.mean().reindex(YEARS6); yw = s.groupby("y").win_x.mean().reindex(YEARS6)
    return dict(n=len(s), 三着内率=s.top3.mean() * 100, 中止率=s.chushi.mean() * 100, 複勝=s.place.mean(), 複差=s.place_x.mean(),
                複除外=(s.place.sum() - hit.head(k).sum()) / len(s), 複正年=int((yr > 0).sum()), 単勝=s.win.mean(), 単差=s.win_x.mean(),
                単正年=int((yw > 0).sum()), **{f"複{Y % 100}": yr[Y] for Y in YEARS6})


if __name__ == "__main__":
    d = load()
    x = d[d.y >= 2021]
    print("障害戦全体（2021-2026）: 頭数", len(x), " 複勝回収率", round(x.place.mean(), 1), " 単勝回収率", round(x.win.mean(), 1), " 中止率", round(x.chushi.mean() * 100, 1), "%")
    C = candidates(d)
    rows = []
    for (th, nm), m in C.items():
        s = x[m.loc[x.index]]
        if len(s) >= 150:
            rows.append(dict(観点=th, 要素=nm, **stats(s)))
    r = pd.DataFrame(rows)
    r.to_pickle(os.path.join(ROOT, ".scratch", "jump_screen.pkl"))
    for th in r.観点.unique():
        print(f"\n## {th}")
        print(r[r.観点 == th].drop(columns="観点").round(1).to_string(index=False))
