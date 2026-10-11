# -*- coding: utf-8 -*-
"""
一変指数: トリガー候補の下見（研究用）。
各トリガーについて、単勝・複勝回収率の「同じ年・同じ基準オッズ帯の平均との差」を年別（2021-2026）に出す。
母集団: (1) 前走あり全体 (2) 穴馬 = 基準オッズ10倍以上 (3) 穴馬かつ前走6着以下（巻き返し）
入力はすべてレース前に確定する値（今走と前走の T_KYI/T_CYB、前走の T_SED）。結果は今走の T_SED のみ。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]
CENTRAL = {"05", "06", "08", "09"}
LEFT = {"04", "05", "07"}


def triggers(d):
    """一変トリガー候補（bool列の dict）。前走が無い馬はすべて False。"""
    has = d["前走あり"] & d.q_uma.notna()
    num = lambda s: pd.to_numeric(s, errors="coerce")
    rot = num(d.rotation)
    dd = d.dist - d.p_dist
    T = {}
    # --- A. 条件替わり
    T["芝→ダ"] = (d.tds == "2") & (d.p_tds == "1")
    T["ダ→芝"] = (d.tds == "1") & (d.p_tds == "2")
    T["距離400m以上短縮"] = dd <= -400
    T["距離200m短縮"] = (dd < 0) & (dd > -400)
    T["距離200m延長"] = (dd > 0) & (dd < 400)
    T["距離400m以上延長"] = dd >= 400
    T["競馬場替わり"] = d.course_code != d.p_course
    T["回り替わり"] = d.course_code.isin(LEFT) != d.p_course.isin(LEFT)
    T["ローカル→中央"] = d.course_code.isin(CENTRAL) & ~d.p_course.isin(CENTRAL)
    T["中央→ローカル"] = ~d.course_code.isin(CENTRAL) & d.p_course.isin(CENTRAL)
    pb = d.p_baba.fillna("").str[:1]
    T["前走 重・不良"] = pb.isin(["3", "4"])
    T["前走 稍重"] = pb == "2"
    T["頭数4頭以上減"] = (d.p_heads - d.heads) >= 4
    T["頭数4頭以上増"] = (d.heads - d.p_heads) >= 4
    T["外枠→内枠"] = (d.q_waku >= 6) & (d.waku <= 3)
    T["内枠→外枠"] = (d.q_waku <= 3) & (d.waku >= 6)
    T["降級"] = d["f_クラス変化"] == "降級"
    T["昇級"] = d["f_クラス変化"] == "昇級"
    # --- B. 陣営の変化
    T["転厩"] = d.trainer.notna() & d.q_trainer.notna() & (d.trainer != d.q_trainer)
    T["馬主変更"] = d.owner.notna() & d.q_owner.notna() & (d.owner != d.q_owner)
    T["乗り替わり"] = d["f_乗り替わり"] == "乗り替わり"
    jd = d.j_win - d.q_j_win
    T["騎手強化(勝率+5pt以上)"] = T["乗り替わり"] & (jd >= 5)
    T["騎手弱化(勝率−5pt以下)"] = T["乗り替わり"] & (jd <= -5)
    T["見習い騎手を新たに起用"] = d.minarai.notna() & d.q_minarai.isna()
    T["去勢明け"] = (d.sex == "3") & (d.q_sex == "1")
    T["ブリンカー初装着"] = d.blinker == "1"
    T["ブリンカー再装着"] = d.blinker == "2"
    T["ブリンカーを外した"] = d.blinker.isna() & d.q_blinker.isin(["1", "2", "3"])
    T["斤量2kg以上減"] = d.kin_diff <= -2
    T["斤量2kg以上増"] = d.kin_diff >= 2
    # --- C. 休み・ローテ・放牧
    T["連闘"] = rot == 0
    T["中1〜2週"] = rot.between(1, 2)
    T["休み明け(中8〜11週)"] = rot.between(8, 11)
    T["休み明け(中12〜23週)"] = rot.between(12, 23)
    T["休み明け(中24週以上)"] = rot >= 24
    T["休養理由 放牧"] = d.kyuyo == "01"
    T["休養理由 故障・不安など"] = d.kyuyo.isin(["02", "03", "04", "07"])
    T["休養理由 調整"] = num(d.kyuyo) >= 11
    nyu_n = num(d.nyu_n); nyu_d = num(d.nyu_d)
    T["入厩2走目"] = nyu_n == 2
    T["入厩3走目"] = nyu_n == 3
    T["入厩4走目以上"] = nyu_n >= 4
    T["入厩1走目 入厩14日以内"] = (nyu_n == 1) & (nyu_d <= 14)
    T["入厩1走目 入厩15〜28日"] = (nyu_n == 1) & nyu_d.between(15, 28)
    T["入厩1走目 入厩29日以上"] = (nyu_n == 1) & (nyu_d >= 29)
    T["放牧先ランクA(入厩1走目)"] = (nyu_n == 1) & (d.hob_r == "A")
    T["放牧先ランクD/E(入厩1走目)"] = (nyu_n == 1) & d.hob_r.isin(["D", "E"])
    RK = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
    hr = d.hob_r.map(RK); qhr = d.q_hob_r.map(RK)
    T["放牧先ランク上昇"] = (hr - qhr) >= 1
    T["放牧先が変わった(入厩1走目)"] = (nyu_n == 1) & d.hob.notna() & d.q_hob.notna() & (d.hob != d.q_hob) & (d.hob != "情報無し") & (d.q_hob != "情報無し")
    # --- D. 指数の良化
    dk = d.kyusha_index - d.q_kyusha_index
    T["厩舎指数 +10以上良化"] = (dk >= 10) & (dk < 20)
    T["厩舎指数 +20以上良化"] = dk >= 20
    T["厩舎指数 −10以下悪化"] = dk <= -10
    dc = d.chokyo_index - d.q_chokyo_index
    T["調教指数 +10以上良化"] = (dc >= 10) & (dc < 20)
    T["調教指数 +20以上良化"] = dc >= 20
    T["調教指数 −10以下悪化"] = dc <= -10
    jo, qjo = d.joho_index.where(d.joho_index >= 0), d.q_joho_index.where(d.q_joho_index >= 0)
    dj = jo - qjo
    T["情報指数 +1.5以上良化"] = (dj >= 1.5) & (dj < 3)
    T["情報指数 +3以上良化"] = dj >= 3
    T["情報指数 −1.5以下悪化"] = dj <= -1.5
    do = d.oi_index - d.q_oi_index
    T["追切指数 +10以上良化"] = do >= 10
    T["追切指数 −10以下悪化"] = do <= -10
    ds = d.shiage_index - d.q_shiage_index
    T["仕上指数 +5以上良化"] = ds >= 5
    T["仕上指数 −5以下悪化"] = ds <= -5
    for v in ("1", "2", "3", "4"):
        T[f"仕上指数変化コード{v}"] = d.shiage_henka == v
    T["調教量評価A"] = d.ryo == "A"
    T["調教量評価D"] = d.ryo == "D"
    yk = pd.to_numeric(d.yaji, errors="coerce"); qyk = pd.to_numeric(d.q_yaji, errors="coerce")
    T["調教矢印 前走より良化"] = (yk < qyk)
    T["調教矢印 前走より悪化"] = (yk > qyk)
    kh = pd.to_numeric(d.kyu_hyoka, errors="coerce"); qkh = pd.to_numeric(d.q_kyu_hyoka, errors="coerce")
    T["厩舎評価 前走より良化"] = (kh < qkh)
    T["調教コース替わり"] = d.ctype.notna() & d.q_ctype.notna() & (d.ctype != d.q_ctype)
    T["最終追切が1週前より+10以上"] = (d.oi_index - d.oi_1w) >= 10
    T["騎手指数 +0.5以上"] = (d.kishu_index - d.q_kishu_index) >= 0.5
    dsg = d.sogo_index - d.q_sogo_index
    T["総合指数 +10以上良化"] = dsg >= 10
    T["総合印が新たに付いた"] = d.in_sogo.notna() & d.q_in_sogo.isna()
    T["上昇度コード 前走より良化"] = pd.to_numeric(d.joshodo, errors="coerce") > pd.to_numeric(d.q_joshodo, errors="coerce")
    # --- E. 前走の内容（巻き返しの余地）
    T["前走不利3段階以上"] = d.get("p1_furi_max", pd.Series(np.nan, index=d.index)) >= 3
    T["前走出遅れ"] = d["f_前走出遅れ"] == "あり"
    T["前走10着以下"] = d.p_fin >= 10
    T["前走1秒超負け"] = d["f_1着との差"] == "1.0秒超"
    T["前走は人気より5着以上下"] = d["f_人気−着順"] == "人気より5以上下"
    return {k: (v.fillna(False).astype(bool) & has) for k, v in T.items()}


def load():
    d = pd.read_pickle(os.path.join(ROOT, ".scratch", "ippen_base.pkl"))
    sed = pd.read_pickle(os.path.join(ROOT, ".scratch", "sed_ext.pkl"))[["skey", "s_furi", "s_mae", "s_naka", "s_ushiro"]]
    for c in ("s_furi", "s_mae", "s_naka", "s_ushiro"):
        sed[c] = pd.to_numeric(sed[c], errors="coerce")
    sed["p1_furi_max"] = sed[["s_furi", "s_mae", "s_naka", "s_ushiro"]].max(axis=1)
    d = d.merge(sed[["skey", "p1_furi_max"]].rename(columns={"skey": "p1key"}), on="p1key", how="left")
    return d


if __name__ == "__main__":
    d = load()
    T = triggers(d)
    x = d[d.y >= 2021]
    pops = {"前走あり全体": x["前走あり"] & x.q_uma.notna(),
            "穴馬(基準10倍以上)": x["前走あり"] & x.q_uma.notna() & (x.odds >= 10),
            "穴馬×前走6着以下": x["前走あり"] & x.q_uma.notna() & (x.odds >= 10) & (x.p_fin >= 6)}
    rows = []
    for pname, pm in pops.items():
        for k, m in T.items():
            mm = (m.loc[x.index] & pm)
            s = x[mm]
            if len(s) < 300:
                continue
            yr = s.groupby("y").place_x.mean().reindex(YEARS6)
            yw = s.groupby("y").win_x.mean().reindex(YEARS6)
            rows.append(dict(母集団=pname, トリガー=k, n=len(s), 複勝=s.place.mean(), 複差=s.place_x.mean(),
                             複_正年=int((yr > 0).sum()), 単勝=s.win.mean(), 単差=s.win_x.mean(), 単_正年=int((yw > 0).sum()),
                             **{f"複{Y % 100}": yr[Y] for Y in YEARS6}))
    r = pd.DataFrame(rows)
    pd.to_pickle(r, os.path.join(ROOT, ".scratch", "ippen_screen.pkl"))
    for pname in pops:
        print(f"\n## {pname}（2021-2026、差=同オッズ帯平均との差pt、正年=6年中プラスの年数）")
        print(r[r.母集団 == pname].drop(columns="母集団").sort_values("複差", ascending=False).round(1).to_string(index=False))
