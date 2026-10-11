# -*- coding: utf-8 -*-
"""
一変のプラス要素探し（研究用）。理論的な根拠のある候補を、しきい値を前後に振りながら下見する。
評価: 複勝・単勝回収率の「同じ年・同じ基準オッズ帯の平均との差」、年別（2021-2026）のプラス年数、
      当たりの払戻上位1%を除いた複勝回収率（当たり数に比例した除外）。
母集団: 穴馬（基準10倍以上）と 全馬。前走が分かる馬のみ。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 1000); pd.set_option("display.max_colwidth", 60)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]


def load():
    d = pd.read_pickle(os.path.join(ROOT, ".scratch", "ippen_base2.pkl"))
    d = d[d["前走あり"] & d.x1_srid.notna()].reset_index(drop=True)
    sed = pd.read_pickle(os.path.join(ROOT, ".scratch", "sed_ext.pkl"))[["skey", "s_furi", "s_mae", "s_naka", "s_ushiro"]]
    for c in ("s_furi", "s_mae", "s_naka", "s_ushiro"):
        sed[c] = pd.to_numeric(sed[c], errors="coerce")
    sed["p1_furi_max"] = sed[["s_furi", "s_mae", "s_naka", "s_ushiro"]].max(axis=1)
    return d.merge(sed[["skey", "p1_furi_max"]].rename(columns={"skey": "p1key"}), on="p1key", how="left")


def candidates(d):
    num = lambda s: pd.to_numeric(s, errors="coerce")
    C = {}   # (テーマ, 名前) -> bool
    lost = d.x1_fin >= 4; bad = d.x1_fin >= 6
    front = d.x1_rkya.isin(["1", "2"]); back = d.x1_rkya.isin(["3", "4"])
    # ===== A. 前走の敗因が今回は無い（展開・位置・コース取り・不利）
    A = "A.前走の敗因"
    C[(A, "前走Hペースを先行して4着以下")] = (d.x1_rpace == "H") & front & lost
    C[(A, "前走Hペースを先行して6着以下")] = (d.x1_rpace == "H") & front & bad
    C[(A, "前走Sペースを差して4着以下")] = (d.x1_rpace == "S") & back & lost
    for k in (1, 2, 3):
        C[(A, f"前走 上がり3F{k}位以内で4着以下")] = (d.x1_l3f_rank <= k) & lost
    C[(A, "前走 上がり3F3位以内で6着以下")] = (d.x1_l3f_rank <= 3) & bad
    C[(A, "前走 4角大外(5)で4着以下")] = (d.x1_c4posi == "5") & lost
    C[(A, "前走 4角外〜大外(4,5)で4着以下")] = d.x1_c4posi.isin(["4", "5"]) & lost
    C[(A, "前走 コース取り大外で4着以下")] = (d.x1_cposi == "5") & lost
    for k in (1, 2, 3):
        C[(A, f"前走 不利{k}段階以上")] = d.p1_furi_max >= k
    C[(A, "前走 不利2段階以上で4着以下")] = (d.p1_furi_max >= 2) & lost
    # ===== B. 前走は内容が良かった（着順以上の中身）
    B = "B.前走の中身"
    for s in (2, 3, 5):
        C[(B, f"前走 4着以下で着差0.{s}秒以内")] = lost & (d.x1_wdiff <= s)
    for k in (1, 2, 3):
        C[(B, f"前走 IDMレース内{k}位以内で4着以下")] = (d.x1_idm_rank <= k) & lost
    C[(B, "前走 IDMレース内3位以内で6着以下")] = (d.x1_idm_rank <= 3) & bad
    C[(B, "前走 人気より5着以上下")] = (d.x1_fin - d.x1_ninki) >= 5
    C[(B, "前走 1〜3番人気で6着以下")] = (d.x1_ninki <= 3) & bad
    C[(B, "前走 重賞・OPで4着以下")] = d.x1_cls.isin(["OP"]) & lost & ~d.cls.isin(["OP"])
    # ===== C. 前走のレースレベル（同走馬の次走成績、今走の日付より前に走った分だけ）
    Cc = "C.前走のレベル"
    ok = d.lvl_n >= 5
    for r in (0.25, 0.30, 0.35, 0.40):
        C[(Cc, f"前走メンバーの次走3着内率{int(r*100)}%以上")] = ok & (d.lvl_rate >= r)
        C[(Cc, f"前走メンバーの次走3着内率{int(r*100)}%以上で4着以下")] = ok & (d.lvl_rate >= r) & lost
    C[(Cc, "前走メンバーの次走3着内率15%未満")] = ok & (d.lvl_rate < 0.15)
    # ===== D. 前走だけの凡走（それ以前は走っていた）
    D = "D.一時的な凡走"
    C[(D, "2走前3着内→前走6着以下")] = (d.x2_fin <= 3) & bad
    C[(D, "2走前3着内→前走4着以下")] = (d.x2_fin <= 3) & lost
    C[(D, "2走前2着内→前走6着以下")] = (d.x2_fin <= 2) & bad
    C[(D, "IDM: 2走前より前走が5以上低下")] = (d.x2_idm - d.x1_idm) >= 5
    # ===== E. 適性のある条件に戻る（過去の実績、今走より前の成績のみ）
    E = "E.適性条件に戻る"
    C[(E, "今回の芝ダで3着内あり・前走は別の芝ダ")] = (d.h_tds_top3 >= 1) & (d.x1_tds != d.tds)
    C[(E, "今回のコース(芝ダ)で3着内あり・前走6着以下")] = (d.h_ctds_top3 >= 1) & bad
    C[(E, "今回のコース(芝ダ)で3着内2回以上")] = d.h_ctds_top3 >= 2
    C[(E, "今回の距離帯で3着内あり・前走は別距離帯")] = (d.h_dist_top3 >= 1) & ((d.x1_dist // 200) * 200 != (d.dist // 200) * 200)
    C[(E, "今回の距離帯で3着内あり・前走6着以下")] = (d.h_dist_top3 >= 1) & bad
    C[(E, "今回の回りで3着内あり・前走は逆回りで6着以下")] = (d.h_lr_top3 >= 1) & (d.x1_lr != d.lr) & bad
    C[(E, "同コース同距離帯で3着内あり・前走6着以下")] = (d.h_cdist_top3 >= 1) & bad
    C[(E, "今回の芝ダで3着内率50%以上(3走以上)")] = (d.h_tds_n >= 3) & (d.h_tds_top3 / d.h_tds_n >= 0.5)
    # ===== F. 斤量・相手関係が楽になる
    F = "F.条件が楽に"
    for k in (1, 2, 3, 4):
        C[(F, f"斤量{k}kg以上減")] = d.kin_diff <= -k
    C[(F, "斤量2kg以上減×ハンデ戦")] = (d.kin_diff <= -2) & (d.wtype == "1")
    C[(F, "斤量2kg以上減×ハンデ戦以外")] = (d.kin_diff <= -2) & (d.wtype != "1")
    C[(F, "混合戦→牝馬限定戦(牝馬)")] = (d.kigou.str[1:2] == "2") & (d.x1_kigou.str[1:2] != "2")
    C[(F, "3歳限定→3歳以上(3歳馬)")] = d.syubetsu.isin(["13"]) & (d.x1_syubetsu == "12")
    C[(F, "頭数が4頭以上減")] = (d.x1_heads - d.heads) >= 4
    # ===== G. 距離短縮
    G = "G.距離短縮"
    dd = d.dist - d.x1_dist
    for k in (100, 200, 300, 400, 600):
        C[(G, f"{k}m以上短縮")] = dd <= -k
    C[(G, "短縮・芝")] = (dd < 0) & (d.tds == "1"); C[(G, "短縮・ダート")] = (dd < 0) & (d.tds == "2")
    C[(G, "短縮・前走4角5番手以内で4着以下")] = (dd < 0) & (d.x1_c4 <= 5) & lost
    C[(G, "短縮・前走で前半3F差が速い(先行)")] = (dd < 0) & (d.x1_f3d < 0)
    # ===== H. 休み明け・外厩
    H = "H.休養明け"
    rot = num(d.rotation)
    for lo, hi in ((5, 7), (8, 9), (10, 11), (8, 11), (12, 15), (16, 23)):
        C[(H, f"中{lo}〜{hi}週")] = rot.between(lo, hi)
    nn, nd = num(d.nyu_n), num(d.nyu_d)
    C[(H, "中8〜11週×放牧先A")] = rot.between(8, 11) & (d.hob_r == "A")
    C[(H, "中8〜11週×放牧先B")] = rot.between(8, 11) & (d.hob_r == "B")
    C[(H, "中12〜23週×放牧先A")] = rot.between(12, 23) & (d.hob_r == "A")
    C[(H, "入厩1走目×入厩15〜28日×放牧先A")] = (nn == 1) & nd.between(15, 28) & (d.hob_r == "A")
    # ===== I. 厩舎・調教の気配
    I = "I.陣営の気配"
    dk = d.kyusha_index - d.q_kyusha_index
    for lo, hi in ((5, 10), (10, 15), (15, 20), (10, 20), (20, 30), (30, 99)):
        C[(I, f"厩舎指数 +{lo}〜{hi}良化")] = (dk >= lo) & (dk < hi)
    C[(I, "厩舎指数 +10〜20良化×前走6着以下")] = (dk >= 10) & (dk < 20) & bad
    C[(I, "厩舎評価 4→3以上に改善")] = (d.q_kyu_hyoka == "4") & d.kyu_hyoka.isin(["1", "2", "3"])
    C[(I, "厩舎評価 2(強気)以上・前走は3以下")] = d.kyu_hyoka.isin(["1", "2"]) & d.q_kyu_hyoka.isin(["3", "4"])
    C[(I, "調教量評価A")] = d.ryo == "A"
    C[(I, "ブリンカー再装着")] = d.blinker == "2"
    C[(I, "騎手継続(前走と同じ騎手)")] = d["f_乗り替わり"] == "継続騎乗"
    C[(I, "前走見習い→今走見習い以外")] = d.minarai.isna() & d.q_minarai.notna()
    # ===== J. 枠・コースの物理的な理由
    J = "J.枠・コース"
    C[(J, "ダート 内枠→外枠(砂を被らない)")] = (d.tds == "2") & (d.q_waku <= 3) & (d.waku >= 6)
    C[(J, "芝 内枠→外枠")] = (d.tds == "1") & (d.q_waku <= 3) & (d.waku >= 6)
    C[(J, "芝 外枠→内枠")] = (d.tds == "1") & (d.q_waku >= 6) & (d.waku <= 3)
    C[(J, "前走 重・不良で4着以下")] = d.x1_baba.fillna("").str[:1].isin(["3", "4"]) & lost
    C[(J, "前走 稍重")] = d.x1_baba.fillna("").str[:1] == "2"
    return {k: v.fillna(False).astype(bool) for k, v in C.items()}


def stats(s):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    yr = s.groupby("y").place_x.mean().reindex(YEARS6); yw = s.groupby("y").win_x.mean().reindex(YEARS6)
    return dict(n=len(s), 複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / len(s),
                複正年=int((yr > 0).sum()), 単勝=s.win.mean(), 単差=s.win_x.mean(), 単正年=int((yw > 0).sum()),
                **{f"複{Y % 100}": yr[Y] for Y in YEARS6})


if __name__ == "__main__":
    d = load()
    C = candidates(d)
    x = d.y >= 2021
    rows = []
    for (th, nm), m in C.items():
        for pop, pm in (("穴馬", d.odds >= 10), ("全馬", pd.Series(True, index=d.index))):
            s = d[m & x & pm]
            if len(s) >= 200:
                rows.append(dict(テーマ=th, 要素=nm, 母集団=pop, **stats(s)))
    r = pd.DataFrame(rows)
    r.to_pickle(os.path.join(ROOT, ".scratch", "ippen_plus_screen.pkl"))
    for pop in ("穴馬", "全馬"):
        print(f"\n######## {pop}（2021-2026）")
        for th in r.テーマ.unique():
            print(f"\n## {th}")
            print(r[(r.母集団 == pop) & (r.テーマ == th)].drop(columns=["テーマ", "母集団"]).round(1).to_string(index=False))
