# -*- coding: utf-8 -*-
"""
一変指数の walk-forward 検証（研究用）。
- 前走からの変化・休み明け・放牧先・陣営の変化・指数の変化などを、グループ内で排他的な区分にする（各グループの基準区分は「変化なし」）。
- 毎年 Y について、Y年より前の穴馬（基準オッズ10倍以上）だけで、複勝回収率の同オッズ帯平均との差を
  リッジ回帰で推定し（重なりのある区分どうしの二重計上を防ぐ）、点数 = 推定された上乗せ(pt) の合計とする。
- Y年の全馬に点数を付け、穴馬の点数帯ごとの単勝・複勝回収率を見る。
入力はすべてレース前に確定する値。結果（着順・払戻）は今走の T_SED のみで、採点には使わない。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ippen_screen import load, CENTRAL
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
ALPHA = float(os.environ.get("ALPHA", "3000"))
TARGET = os.environ.get("TARGET", "place_x")
POP = os.environ.get("POP", "ana")   # ana = 穴馬(基準10倍以上)で推定 / all = 全馬で推定


def cut(s, bins, labels):
    return pd.cut(s, bins, labels=labels, right=False).astype(str).replace("nan", "NA")


def groups(d):
    num = lambda s: pd.to_numeric(s, errors="coerce")
    G = {}
    G["芝ダ"] = np.select([(d.tds == "2") & (d.p_tds == "1"), (d.tds == "1") & (d.p_tds == "2")], ["芝→ダ", "ダ→芝"], "同じ")
    dd = d.dist - d.p_dist
    G["距離"] = np.select([dd <= -400, dd < 0, dd >= 400, dd > 0], ["400m以上短縮", "短縮", "400m以上延長", "延長"], "同距離")
    cc, pc = d.course_code.isin(CENTRAL), d.p_course.isin(CENTRAL)
    G["競馬場"] = np.select([d.course_code == d.p_course, cc & ~pc, ~cc & pc], ["同じ", "ローカル→中央", "中央→ローカル"], "別場(同格)")
    pb = d.p_baba.fillna("").str[:1]
    G["前走馬場"] = np.select([pb == "2", pb.isin(["3", "4"])], ["稍重", "重・不良"], "良")
    hd = d.heads - d.p_heads
    G["頭数"] = np.select([hd <= -4, hd >= 4], ["4頭以上減", "4頭以上増"], "同程度")
    G["枠"] = np.select([(d.q_waku >= 6) & (d.waku <= 3), (d.q_waku <= 3) & (d.waku >= 6)], ["外→内", "内→外"], "その他")
    G["クラス"] = np.select([d["f_クラス変化"] == "昇級", d["f_クラス変化"] == "降級"], ["昇級", "降級"], "同クラス")
    G["転厩"] = np.where(d.trainer.notna() & d.q_trainer.notna() & (d.trainer != d.q_trainer), "転厩", "なし")
    G["馬主変更"] = np.where(d.owner.notna() & d.q_owner.notna() & (d.owner != d.q_owner), "変更", "なし")
    G["去勢"] = np.where((d.sex == "3") & (d.q_sex == "1"), "去勢明け", "なし")
    jd = d.j_win - d.q_j_win
    nori = d["f_乗り替わり"] == "乗り替わり"
    G["騎手"] = np.select([nori & (jd >= 5), nori & (jd <= -5), nori], ["乗替・強化", "乗替・弱化", "乗替・同程度"], "継続")
    G["見習い"] = np.where(d.minarai.notna() & d.q_minarai.isna(), "新たに起用", "なし")
    G["ブリンカー"] = np.select([d.blinker == "1", d.blinker == "2", d.blinker.isna() & d.q_blinker.notna()], ["初装着", "再装着", "外した"], "変化なし")
    G["斤量"] = np.select([d.kin_diff <= -2, d.kin_diff >= 2], ["2kg以上減", "2kg以上増"], "同程度")
    rot = num(d.rotation)
    G["間隔"] = np.select([rot == 0, rot <= 2, rot <= 7, rot <= 11, rot <= 23, rot >= 24], ["連闘", "中1〜2週", "中3〜7週", "中8〜11週", "中12〜23週", "中24週以上"], "中3〜7週")
    k = num(d.kyuyo)
    G["休養理由"] = np.select([d.kyuyo == "01", d.kyuyo.isin(["02", "03", "04", "07"]), k >= 11, d.kyuyo.notna()], ["放牧", "故障・不安", "調整", "その他"], "なし")
    nn, nd = num(d.nyu_n), num(d.nyu_d)
    G["入厩"] = np.select([(nn == 1) & (nd <= 14), (nn == 1) & (nd <= 28), (nn == 1) & (nd >= 29), nn == 1, nn == 2, nn == 3, nn >= 4],
                         ["1走目・14日以内", "1走目・15〜28日", "1走目・29日以上", "1走目・日数不明", "2走目", "3走目", "4走目以上"], "不明")
    G["放牧先ランク(入厩1走目)"] = np.where(nn == 1, "1走目_" + d.hob_r.fillna("NA").replace({"E": "DE", "D": "DE"}), "1走目以外")
    RK = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
    hrd = d.hob_r.map(RK) - d.q_hob_r.map(RK)
    G["放牧先ランク変化"] = np.select([hrd >= 1, hrd <= -1], ["上昇", "低下"], "同じ")
    G["厩舎指数の変化"] = cut(d.kyusha_index - d.q_kyusha_index, [-99, -10, 10, 20, 99], ["−10以下", "±10未満", "+10〜20", "+20以上"])
    G["調教指数の変化"] = cut(d.chokyo_index - d.q_chokyo_index, [-99, -10, 10, 20, 99], ["−10以下", "±10未満", "+10〜20", "+20以上"])
    jo, qjo = d.joho_index.where(d.joho_index >= 0), d.q_joho_index.where(d.q_joho_index >= 0)
    G["情報指数の変化"] = cut(jo - qjo, [-99, -1.5, 1.5, 3, 99], ["−1.5以下", "±1.5未満", "+1.5〜3", "+3以上"])
    G["追切指数の変化"] = cut(d.oi_index - d.q_oi_index, [-999, -10, 10, 999], ["−10以下", "±10未満", "+10以上"])
    G["仕上指数の変化"] = cut(d.shiage_index - d.q_shiage_index, [-999, -5, 5, 999], ["−5以下", "±5未満", "+5以上"])
    G["仕上指数変化コード"] = "code" + d.shiage_henka.fillna("NA")
    G["調教量評価"] = "量" + d.ryo.fillna("NA")
    yk, qyk = num(d.yaji), num(d.q_yaji)
    G["調教矢印の変化"] = np.select([yk < qyk, yk > qyk], ["良化", "悪化"], "同じ")
    G["厩舎評価"] = "評価" + d.kyu_hyoka.fillna("NA") + "_前走" + d.q_kyu_hyoka.fillna("NA")
    G["総合印"] = np.select([d.in_sogo.notna() & d.q_in_sogo.isna(), d.in_sogo.isna() & d.q_in_sogo.notna()], ["新たに付いた", "外れた"], "変化なし")
    G["IDMの変化"] = cut(d.idm - d.q_idm, [-999, -5, 5, 999], ["−5以下", "±5未満", "+5以上"])
    G["前走着順"] = d["f_前走着順"].values
    G["前走不利"] = np.select([d.p1_furi_max >= 3, d.p1_furi_max >= 1], ["3段階以上", "1〜2段階"], "なし")
    G["前走出遅れ"] = d["f_前走出遅れ"].values
    G["前走の人気と着順"] = d["f_人気−着順"].values
    return pd.DataFrame({g: pd.Series(np.asarray(v), index=d.index).astype(str) for g, v in G.items()})


BASE = {"芝ダ": "同じ", "距離": "同距離", "競馬場": "同じ", "前走馬場": "良", "頭数": "同程度", "枠": "その他", "クラス": "同クラス",
        "転厩": "なし", "馬主変更": "なし", "去勢": "なし", "騎手": "継続", "見習い": "なし", "ブリンカー": "変化なし", "斤量": "同程度",
        "間隔": "中3〜7週", "休養理由": "なし", "入厩": "4走目以上", "放牧先ランク(入厩1走目)": "1走目以外", "放牧先ランク変化": "同じ",
        "厩舎指数の変化": "±10未満", "調教指数の変化": "±10未満", "情報指数の変化": "±1.5未満", "追切指数の変化": "±10未満",
        "仕上指数の変化": "±5未満", "仕上指数変化コード": "code3", "調教量評価": "量B", "調教矢印の変化": "同じ", "厩舎評価": "評価3_前走3",
        "総合印": "変化なし", "IDMの変化": "±5未満", "前走着順": "4-5着", "前走不利": "なし", "前走出遅れ": "なし", "前走の人気と着順": "ほぼ人気通り"}


def design(G, min_n=200, ref=None):
    cols, names = [], []
    for g in G.columns:
        vc = G[g].value_counts() if ref is None else G.loc[ref, g].value_counts()
        for v in vc.index:
            if v == BASE.get(g) or vc[v] < min_n:
                continue
            cols.append((G[g] == v).to_numpy(np.float32)); names.append(f"{g}={v}")
    return np.column_stack(cols), names


def ridge(X, y, alpha):
    mu = y.mean()
    A = X.T @ X + alpha * np.eye(X.shape[1])
    return mu, np.linalg.solve(A, X.T @ (y - mu))


if __name__ == "__main__":
    d = load()
    d = d[d["前走あり"] & d.q_uma.notna()].reset_index(drop=True)
    G = groups(d)
    ana = (d.odds >= 10).to_numpy() if POP == "ana" else np.ones(len(d), bool)
    d["ippen"] = np.nan
    coefs = {}
    for Y in YEARS:
        tr = (d.y < Y).to_numpy() & ana
        X, names = design(G, ref=tr)
        mu, b = ridge(X[tr], d.loc[tr, TARGET].to_numpy(), ALPHA)
        m = (d.y == Y).to_numpy()
        d.loc[m, "ippen"] = X[m] @ b
        coefs[Y] = pd.Series(b, index=names)
    d.to_pickle(os.path.join(ROOT, ".scratch", f"ippen_scored_{TARGET}_{int(ALPHA)}{'' if POP == 'ana' else '_all'}.pkl"))
    C = pd.DataFrame(coefs).fillna(0)
    print(f"## 区分ごとの点数（毎年その年より前の{'穴馬' if POP == 'ana' else '全馬'}で推定、pt）ALPHA={ALPHA} TARGET={TARGET}")
    C["平均"] = C.mean(axis=1)
    print(C.sort_values("平均").round(1).to_string())

    t = d[d.y.isin(YEARS) & (d.odds >= 10)].copy()
    t["pct"] = t.groupby("y").ippen.rank(pct=True)
    bands = [("上位1%", 0.99, 1.01), ("上位1〜5%", 0.95, 0.99), ("上位5〜10%", 0.90, 0.95), ("上位10〜25%", 0.75, 0.90),
             ("中位25〜75%", 0.25, 0.75), ("下位25%", 0, 0.25)]
    print("\n## 穴馬（基準10倍以上）の一変指数の帯別成績（2022-2026、帯は各年の順位％）")
    rows = []
    for lab, lo, hi in bands:
        s = t[(t.pct > lo) & (t.pct <= hi)]
        # 当たり数に比例した除外: 複勝の当たりの払戻上位1%を除く
        hit = s[s.place > 0].place.sort_values(ascending=False)
        k = max(1, int(round(len(hit) * 0.01)))
        ex = (s.place.sum() - hit.head(k).sum()) / len(s)
        whit = s[s.win > 0].win.sort_values(ascending=False)
        kw = max(1, int(round(len(whit) * 0.01)))
        wex = (s.win.sum() - whit.head(kw).sum()) / len(s)
        yr = s.groupby("y").place_x.mean().reindex(YEARS)
        ywr = s.groupby("y").win_x.mean().reindex(YEARS)
        rows.append(dict(帯=lab, n=len(s), 平均オッズ中央=s.odds.median(), 複勝=s.place.mean(), 複_同オッズ平均=s.place_b.mean(), 複差=s.place_x.mean(),
                         複_上位1pct除外=ex, 単勝=s.win.mean(), 単_同オッズ平均=s.win_b.mean(), 単差=s.win_x.mean(), 単_上位1pct除外=wex,
                         三着内率=(s.fin <= 3).mean() * 100,
                         **{f"複差{Y % 100}": yr[Y] for Y in YEARS}, **{f"単差{Y % 100}": ywr[Y] for Y in YEARS}))
    print(pd.DataFrame(rows).round(1).to_string(index=False))
