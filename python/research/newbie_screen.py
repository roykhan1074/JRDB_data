# -*- coding: utf-8 -*-
"""
新馬戦: ファクターの下見（研究用）。
評価: 単勝・複勝回収率の「同じ年・同じ基準オッズ帯の平均との差」（新馬戦の中で）、年別（2021-2026）のプラス年数、
      当たりの払戻上位1%を除いた複勝回収率、3着内率。
入力はすべてレース前に分かる値（今走の T_KYI/T_BAC/T_CYB/T_UKC、今走より前の T_SED）。結果は今走の T_SED のみ。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 1000)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]
BANDS = [1, 2, 3, 5, 10, 20, 50, 1000]
CLUBS = ("サンデーレーシング", "キャロットファーム", "シルクレーシング", "東京ホースレーシング", "社台レースホース", "ＤＭＭドリームクラブ",
         "ＧⅠレーシング", "ラフィアン", "ノルマンディーサラブレッドレーシング", "ウイン", "ライオンレースホース", "ユニオンオーナーズクラブ",
         "大樹レーシングクラブ", "広尾レース", "ローレルレーシング", "ターフ・スポート", "ロードホースクラブ", "インゼルレーシング")


def load():
    d = pd.read_pickle(os.path.join(ROOT, ".scratch", "newbie_base.pkl"))
    d["ob"] = pd.cut(d.kijun_odds, BANDS, right=False).astype(str)
    for p in ("win", "place"):
        d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
        d[p + "_x"] = d[p] - d[p + "_b"]
    num = lambda s: pd.to_numeric(s, errors="coerce")
    for col in ("idm", "joho_index", "kyusha_index", "chokyo_index", "gekiso_index", "sogo_index", "kishu_index", "ten_index", "agari_index",
                "oi_index", "shiage_index", "oi_1w", "manbaken_index"):
        d[f"r_{col}"] = d.groupby("rid")[col].rank(ascending=False, method="min")
    d["r_odds"] = d.groupby("rid").kijun_odds.rank(method="min")
    d["idm_gap"] = d.groupby("rid").idm.transform(lambda s: s.max() - s.nlargest(2).iloc[-1] if s.notna().sum() >= 2 else np.nan)
    for p in ("s", "ds", "t", "j", "b", "o"):
        d[f"{p}_rate"] = d[f"{p}_t3"] / d[f"{p}_n"]
        d[f"{p}_plrr"] = d[f"{p}_pl"] / d[f"{p}_n"]
    d["sib_rate"] = d.sib_t3 / d.sib_n
    d["nyu_d_n"] = num(d.nyu_d)
    for col in ("c_saka", "c_w", "c_poly", "c_da", "c_shiba"):
        d[col + "_n"] = num(d[col])
    d["month"] = d.ymd.str[4:6].astype(int)
    d["club"] = d.owner_name.fillna("").apply(lambda s: any(k in s for k in CLUBS))
    return d


def candidates(d):
    C = {}
    M = "1.市場"
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        C[(M, f"基準オッズ{lo}〜{hi}倍")] = d.kijun_odds.between(lo, hi - 0.01)
    C[(M, "1番人気")] = d.r_odds == 1
    A = "2.JRDB指数"
    for col, nm in (("idm", "IDM"), ("joho_index", "情報指数"), ("sogo_index", "総合指数"), ("chokyo_index", "調教指数"), ("kyusha_index", "厩舎指数"),
                    ("gekiso_index", "激走指数"), ("kishu_index", "騎手指数"), ("ten_index", "テン指数"), ("agari_index", "上がり指数"), ("manbaken_index", "万券指数")):
        C[(A, f"{nm}1位")] = d[f"r_{col}"] == 1
        C[(A, f"{nm}レース内3位以内")] = d[f"r_{col}"] <= 3
        C[(A, f"{nm}レース内下位(下から3頭)")] = d[f"r_{col}"] >= d.heads - 2
    C[(A, "IDM1位で2位と3以上の差")] = (d.r_idm == 1) & (d.idm_gap >= 3)
    C[(A, "人気順位−IDM順位≥3(IDMの割に人気薄)")] = (d.r_odds - d.r_idm) >= 3
    C[(A, "人気順位−IDM順位≤−3(IDMの割に人気)")] = (d.r_odds - d.r_idm) <= -3
    C[(A, "人気順位−情報指数順位≥3")] = (d.r_odds - d.r_joho_index) >= 3
    C[(A, "情報指数マイナス(−1=非開示含む)")] = d.joho_index < 0
    C[(A, "総合印◎(in_sogo=1)")] = d.in_sogo == "1"
    C[(A, "JRDB総合印なし")] = d.in_sogo.isna()
    S = "3.調教"
    C[(S, "追切指数1位")] = d.r_oi_index == 1
    C[(S, "追切指数レース内3位以内")] = d.r_oi_index <= 3
    C[(S, "追切指数レース内下位(下から3頭)")] = d.r_oi_index >= d.heads - 2
    C[(S, "仕上指数1位")] = d.r_shiage_index == 1
    C[(S, "仕上指数レース内下位(下から3頭)")] = d.r_shiage_index >= d.heads - 2
    C[(S, "1週前追切がレース内1位")] = d.r_oi_1w == 1
    C[(S, "最終追切が1週前より+10以上")] = (d.oi_index - d.oi_1w) >= 10
    C[(S, "調教矢印↑(1,2)")] = d.yaji.isin(["1", "2"])
    C[(S, "調教矢印↓(4,5)")] = d.yaji.isin(["4", "5"])
    C[(S, "調教量評価A")] = d.ryo == "A"
    C[(S, "調教量評価C/D")] = d.ryo.isin(["C", "D"])
    C[(S, "坂路調教あり")] = d.c_saka_n >= 1
    C[(S, "坂路調教なし")] = d.c_saka_n.fillna(0) == 0
    C[(S, "ウッド調教あり")] = d.c_w_n >= 1
    C[(S, "ポリトラック調教あり")] = d.c_poly_n >= 1
    C[(S, "入厩30日以内")] = d.nyu_d_n <= 30
    C[(S, "入厩31〜60日")] = d.nyu_d_n.between(31, 60)
    C[(S, "入厩61日以上")] = d.nyu_d_n >= 61
    C[(S, "放牧先A")] = d.hob_r == "A"
    C[(S, "放牧先D/E")] = d.hob_r.isin(["D", "E"])
    C[(S, "厩舎評価1・2(強気)")] = d.kyu_hyoka.isin(["1", "2"])
    C[(S, "厩舎評価4(弱気)")] = d.kyu_hyoka == "4"
    B = "4.血統"
    C[(B, "父の新馬3着内率35%以上(30走以上)")] = (d.s_n >= 30) & (d.s_rate >= 0.35)
    C[(B, "父の新馬3着内率15%未満(30走以上)")] = (d.s_n >= 30) & (d.s_rate < 0.15)
    C[(B, "父の新馬複勝回収率90%以上(30走以上)")] = (d.s_n >= 30) & (d.s_plrr >= 90)
    C[(B, "父の新馬複勝回収率60%未満(30走以上)")] = (d.s_n >= 30) & (d.s_plrr < 60)
    C[(B, "父の新馬出走が10走未満(新種牡馬など)")] = d.s_n.fillna(0) < 10
    C[(B, "母父の新馬3着内率35%以上(30走以上)")] = (d.ds_n >= 30) & (d.ds_rate >= 0.35)
    C[(B, "母父の新馬複勝回収率90%以上(30走以上)")] = (d.ds_n >= 30) & (d.ds_plrr >= 90)
    C[(B, "芝適性A/B(芝のレース)")] = (d.tds == "1") & d.shiba_tek.isin(["1", "2"])
    C[(B, "ダート適性A/B(ダートのレース)")] = (d.tds == "2") & d.dirt_tek.isin(["1", "2"])
    Sb = "5.兄姉"
    C[(Sb, "兄姉の出走なし")] = d.sib_n.fillna(0) == 0
    C[(Sb, "兄姉に勝利あり")] = d.sib_w >= 1
    C[(Sb, "兄姉の3着内率40%以上(5走以上)")] = (d.sib_n >= 5) & (d.sib_rate >= 0.40)
    C[(Sb, "兄姉の3着内率15%未満(5走以上)")] = (d.sib_n >= 5) & (d.sib_rate < 0.15)
    C[(Sb, "兄姉がOP到達")] = d.sib_cls_max >= 4
    C[(Sb, "兄姉が2勝クラス以上到達")] = d.sib_cls_max >= 2
    C[(Sb, "兄姉が未勝利どまり(5走以上)")] = (d.sib_n >= 5) & (d.sib_cls_max == 0)
    J = "6.陣営"
    for p, nm, nmin in (("t", "厩舎", 30), ("j", "騎手", 50), ("b", "生産者", 50), ("o", "馬主", 30)):
        C[(J, f"{nm}の新馬3着内率35%以上({nmin}走以上)")] = (d[f"{p}_n"] >= nmin) & (d[f"{p}_rate"] >= 0.35)
        C[(J, f"{nm}の新馬3着内率15%未満({nmin}走以上)")] = (d[f"{p}_n"] >= nmin) & (d[f"{p}_rate"] < 0.15)
        C[(J, f"{nm}の新馬複勝回収率90%以上({nmin}走以上)")] = (d[f"{p}_n"] >= nmin) & (d[f"{p}_plrr"] >= 90)
        C[(J, f"{nm}の新馬複勝回収率60%未満({nmin}走以上)")] = (d[f"{p}_n"] >= nmin) & (d[f"{p}_plrr"] < 60)
    C[(J, "ノーザンファーム生産")] = d.breeder == "ノーザンファーム"
    C[(J, "社台ファーム・追分・白老生産")] = d.breeder.isin(["社台ファーム", "追分ファーム", "社台コーポレーション白老ファーム"])
    C[(J, "クラブ馬")] = d.club
    C[(J, "美浦所属")] = d.belong.fillna("").str.contains("美浦")
    C[(J, "栗東所属")] = d.belong.fillna("").str.contains("栗東")
    C[(J, "見習い騎手")] = d.minarai.notna()
    H = "7.馬"
    C[(H, "牡馬")] = d.sex == "1"
    C[(H, "牝馬")] = d.sex == "2"
    C[(H, "牝馬が混合戦")] = (d.sex == "2") & (d.kigou.fillna("").str[1:2] != "2")
    for lo, hi, nm in ((1, 2, "1〜2月生まれ"), (3, 3, "3月生まれ"), (4, 4, "4月生まれ"), (5, 12, "5月以降生まれ")):
        C[(H, nm)] = d.birth_m.between(lo, hi)
    C[(H, "3歳の新馬戦")] = d.age == 3
    C[(H, "ブリンカー着用")] = d.blinker.notna()
    C[(H, "出遅れ率が高い(JRDB出遅率10%以上)")] = d.uma_okure_rate >= 10
    R = "8.レース条件"
    C[(R, "芝")] = d.tds == "1"
    C[(R, "ダート")] = d.tds == "2"
    C[(R, "1400m以下")] = d.dist <= 1400
    C[(R, "1600〜1800m")] = d.dist.between(1600, 1800)
    C[(R, "2000m以上")] = d.dist >= 2000
    C[(R, "中央4場(東京・中山・京都・阪神)")] = d.course.isin(["05", "06", "08", "09"])
    C[(R, "6〜7月(開幕直後)")] = d.month.isin([6, 7])
    C[(R, "8〜9月")] = d.month.isin([8, 9])
    C[(R, "10〜12月")] = d.month.isin([10, 11, 12])
    C[(R, "1〜3月(3歳新馬含む)")] = d.month.isin([1, 2, 3])
    C[(R, "16頭以上")] = d.heads >= 16
    C[(R, "内枠(1〜2枠)")] = d.waku <= 2
    C[(R, "外枠(7〜8枠)")] = d.waku >= 7
    C[(R, "ダートの外枠(7〜8枠)")] = (d.tds == "2") & (d.waku >= 7)
    C[(R, "ダートの内枠(1〜2枠)")] = (d.tds == "2") & (d.waku <= 2)
    C[(R, "脚質予想 逃げ")] = d.kya == "1"
    C[(R, "脚質予想 差し・追込")] = d.kya.isin(["3", "4"])
    return {k: v.fillna(False).astype(bool) for k, v in C.items()}


def stats(s):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    yr = s.groupby("y").place_x.mean().reindex(YEARS6); yw = s.groupby("y").win_x.mean().reindex(YEARS6)
    return dict(n=len(s), 三着内率=s.top3.mean() * 100, 複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / len(s),
                複正年=int((yr > 0).sum()), 単勝=s.win.mean(), 単差=s.win_x.mean(), 単正年=int((yw > 0).sum()), **{f"複{Y % 100}": yr[Y] for Y in YEARS6})


if __name__ == "__main__":
    d = load()
    x = d[d.y >= 2021]
    print("新馬戦全体（2021-2026）: 頭数", len(x), " 複勝回収率", round(x.place.mean(), 1), " 単勝回収率", round(x.win.mean(), 1))
    C = candidates(d)
    rows = []
    for (th, nm), m in C.items():
        s = x[m.loc[x.index]]
        if len(s) >= 300:
            rows.append(dict(観点=th, 要素=nm, **stats(s)))
    r = pd.DataFrame(rows)
    r.to_pickle(os.path.join(ROOT, ".scratch", "newbie_screen.pkl"))
    for th in r.観点.unique():
        print(f"\n## {th}")
        print(r[r.観点 == th].drop(columns="観点").round(1).to_string(index=False))
