# -*- coding: utf-8 -*-
"""
プラス一変スコアの walk-forward 検証（研究用）。
理論的な根拠のある「概念」ごとに、しきい値の候補をいくつか用意しておき、毎年 Y について Y年より前の穴馬だけで
  - 各候補の複勝の同オッズ平均との差（全期間平均）と、年ごとのプラス年数を出し
  - 「差が +3pt 以上 かつ 前の年のうちマイナスの年が1年以下」を満たす候補のうち差が最大のものを、その概念の採用候補にする
スコア = 採用された概念のうち当てはまる数（重み1）。Y年の馬に付けて、スコア別の成績を見る。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ippen_plus_screen import load, candidates
import re
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
MIN_GAIN = float(os.environ.get("MIN_GAIN", "3"))
POOL = os.environ.get("POOL", "theory")   # theory = 下見で選んだ概念のみ / full = 下見の全候補（マイナスだったものも含む）
WEIGHT = os.environ.get("WEIGHT", "count")   # count = 1個1点 / gain = 選んだ時点の差pt÷5を四捨五入（最低1点）


def concepts_full(d):
    """下見（ippen_plus_screen）の全候補。名前の数字だけ違う候補（しきい値違い）は同じ概念にまとめる。"""
    out = {}
    for (th, nm), m in candidates(d).items():
        key = th[0] + ":" + re.sub(r"[0-9.]+", "N", nm)
        out.setdefault(key, {})[nm] = m.to_numpy()
    return out


def concepts(d):
    if POOL == "full":
        return concepts_full(d)
    num = lambda s: pd.to_numeric(s, errors="coerce")
    lost = d.x1_fin >= 4; bad = d.x1_fin >= 6
    front = d.x1_rkya.isin(["1", "2"])
    rot = num(d.rotation); nn, nd = num(d.nyu_n), num(d.nyu_d)
    dk = d.kyusha_index - d.q_kyusha_index
    dd = d.dist - d.x1_dist
    ok = d.lvl_n >= 5
    K = {
        "前走ハイペースを先行して負け": {"4着以下": (d.x1_rpace == "H") & front & lost, "6着以下": (d.x1_rpace == "H") & front & bad},
        "前走4角で外を回って負け": {"外〜大外": d.x1_c4posi.isin(["4", "5"]) & lost, "大外": (d.x1_c4posi == "5") & lost},
        "前走で不利": {"1段階以上": d.p1_furi_max >= 1, "2段階以上": d.p1_furi_max >= 2, "3段階以上": d.p1_furi_max >= 3},
        "前走がハイレベル戦で負け": {f"同走馬の次走3着内率{int(r*100)}%以上": ok & (d.lvl_rate >= r) & lost for r in (0.25, 0.30, 0.35, 0.40)},
        "実績のある芝ダに戻る": {"3着内あり・前走は別の芝ダ": (d.h_tds_top3 >= 1) & (d.x1_tds != d.tds)},
        "実績のある距離に戻る": {"距離帯で3着内あり・前走6着以下": (d.h_dist_top3 >= 1) & bad,
                          "距離帯で3着内あり・前走は別距離帯": (d.h_dist_top3 >= 1) & ((d.x1_dist // 200) != (d.dist // 200))},
        "実績のある回りに戻る": {"回りで3着内あり・前走逆回りで6着以下": (d.h_lr_top3 >= 1) & (d.x1_lr != d.lr) & bad},
        "ハンデ戦で斤量減": {"2kg以上減": (d.kin_diff <= -2) & (d.wtype == "1"), "1kg以上減": (d.kin_diff <= -1) & (d.wtype == "1")},
        "外厩で整えた休み明け": {"中8〜11週×放牧先A": rot.between(8, 11) & (d.hob_r == "A"),
                         "入厩1走目×入厩15〜28日×放牧先A": (nn == 1) & nd.between(15, 28) & (d.hob_r == "A"),
                         "中10〜11週": rot.between(10, 11), "中8〜11週": rot.between(8, 11)},
        "厩舎指数の良化": {"+10〜15": (dk >= 10) & (dk < 15), "+10〜20": (dk >= 10) & (dk < 20)},
        "砂を被らない外枠へ(ダート)": {"内枠→外枠": (d.tds == "2") & (d.q_waku <= 3) & (d.waku >= 6)},
        "芝で内枠へ": {"外枠→内枠": (d.tds == "1") & (d.q_waku >= 6) & (d.waku <= 3)},
        "前走が稍重": {"稍重": d.x1_baba.fillna("").str[:1] == "2"},
        "距離短縮": {"100m以上": dd <= -100, "200m以上": dd <= -200, "400m以上": dd <= -400},
        "ブリンカー再装着": {"再装着": d.blinker == "2"},
    }
    return {c: {k: v.fillna(False).astype(bool).to_numpy() for k, v in opts.items()} for c, opts in K.items()}


def summarize(s, lab):
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    whit = s[s.win > 0].win.sort_values(ascending=False); kw = max(1, round(len(whit) * .01))
    r = dict(区分=lab, n=len(s), 年平均=len(s) / len(YEARS), オッズ中央=s.odds.median(), 三着内率=(s.fin <= 3).mean() * 100,
             複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / max(len(s), 1),
             単勝=s.win.mean(), 単差=s.win_x.mean(), 単除外=(s.win.sum() - whit.head(kw).sum()) / max(len(s), 1))
    for Y in YEARS:
        r[f"複勝{Y % 100}"] = s[s.y == Y].place.mean()
    for Y in YEARS:
        r[f"単勝{Y % 100}"] = s[s.y == Y].win.mean()
    return r


if __name__ == "__main__":
    d = load()
    K = concepts(d)
    ana = (d.odds >= 10).to_numpy()
    y = d.y.to_numpy(); px = d.place_x.to_numpy()
    d["plus"] = np.nan
    chosen = {}
    for Y in YEARS:
        prior = sorted(set(y[(y < Y)]))
        score = np.zeros(len(d))
        ch = {}
        for c, opts in K.items():
            best = None
            for k, m in opts.items():
                mm = m & ana & (y < Y)
                if mm.sum() < 300:
                    continue
                gain = px[mm].mean()
                neg = sum(px[mm & (y == p)].mean() < 0 for p in prior)
                if gain >= MIN_GAIN and neg <= 1 and (best is None or gain > best[1]):
                    best = (k, gain)
            if best:
                ch[c] = best
                score += opts[best[0]] * (1 if WEIGHT == "count" else max(1, round(best[1] / 5)))
        te = y == Y
        d.loc[te, "plus"] = score[te]
        chosen[Y] = ch
    print(f"## 毎年採用された要素（その年より前の穴馬で選択、カッコは選んだ時点の複勝の同オッズ差pt）MIN_GAIN={MIN_GAIN}")
    for c in K:
        if not any(c in chosen[Y] for Y in YEARS):
            continue
        print(f"{c:　<14}: " + " / ".join(f"{Y}:{chosen[Y][c][0]}({chosen[Y][c][1]:+.1f})" if c in chosen[Y] else f"{Y}:—" for Y in YEARS))
    d.to_pickle(os.path.join(ROOT, ".scratch", f"ippen_plus_scored_{WEIGHT}_{POOL}.pkl"))
    for title, pm in (("穴馬（基準10倍以上）", d.odds >= 10), ("基準20倍以上", d.odds >= 20), ("基準10倍未満", d.odds < 10)):
        t = d[d.y.isin(YEARS) & pm]
        if WEIGHT == "count":
            rows = [summarize(t[t.plus == k], f"{k}個") for k in range(0, 4)] + [summarize(t[t.plus >= 4], "4個以上"), summarize(t[t.plus >= 5], "5個以上")]
        else:
            rows = [summarize(t[t.plus == 0], "0点")] + [summarize(t[(t.plus >= lo) & (t.plus <= hi)], f"{lo}〜{hi}点") for lo, hi in ((1, 2), (3, 4), (5, 6), (7, 8))] + [summarize(t[t.plus >= 9], "9点以上"), summarize(t[t.plus >= 11], "11点以上")]
        print(f"\n## {title}: 当てはまるプラス要素の数別（2022-2026）")
        print(pd.DataFrame(rows).round(1).to_string(index=False))
