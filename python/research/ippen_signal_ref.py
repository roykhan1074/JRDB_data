# -*- coding: utf-8 -*-
"""
一変シグナル（本番実装と同じ12要素の固定ルール）の参照計算（研究用）。
- 本番（src/server.ts の computeIppenSignals）と同じ定義で、要素の数と内訳を計算する。
- 使い方: python ippen_signal_ref.py           … 個数別の成績（固定ルールを過去に当てた参考値。要素の選定に2026年までのデータを使っているので先読みを含む）
          python ippen_signal_ref.py 20260920  … その日の全馬の個数と内訳を JSON で出す（本番 API との突き合わせ用）
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ippen_plus_screen import load
from ippen_plus_wf import summarize, YEARS

ITEMS = ["前走ハイペースを先行して6着以下", "前走4角で外を回って4着以下", "前走で不利(2段階以上)", "前走がハイレベル戦で4着以下",
         "実績のある芝ダに戻る", "実績のある距離に戻る(前走6着以下)", "実績のある回りに戻る(前走逆回りで6着以下)", "ハンデ戦で斤量2kg以上減",
         "外厩明け(中8〜11週×放牧先A)", "厩舎指数+10〜20良化(前走6着以下)", "前走が稍重", "距離200m以上短縮"]


def signals(d):
    num = lambda s: pd.to_numeric(s, errors="coerce")
    lost = d.x1_fin >= 4; bad = d.x1_fin >= 6
    dk = d.kyusha_index - d.q_kyusha_index
    m = [
        (d.x1_rpace == "H") & d.x1_rkya.isin(["1", "2"]) & bad,
        d.x1_c4posi.isin(["4", "5"]) & lost,
        d.p1_furi_max >= 2,
        (d.lvl_n >= 5) & (d.lvl_rate >= 0.40) & lost,
        (d.h_tds_top3 >= 1) & (d.x1_tds != d.tds),
        (d.h_dist_top3 >= 1) & bad,
        (d.h_lr_top3 >= 1) & (d.x1_lr != d.lr) & bad,
        (d.kin_diff <= -2) & (d.wtype == "1"),
        num(d.rotation).between(8, 11) & (d.hob_r == "A"),
        (dk >= 10) & (dk < 20) & bad,
        d.x1_baba.fillna("").str[:1] == "2",
        (d.dist - d.x1_dist) <= -200,
    ]
    M = np.column_stack([x.fillna(False).astype(bool).to_numpy() for x in m])
    return M


if __name__ == "__main__":
    d = load()
    M = signals(d)
    d["ippen_n"] = M.sum(axis=1)
    if len(sys.argv) > 1:
        t = d[d.ymd == sys.argv[1]]
        out = {f"{r.rid}-{int(r.uma)}": [ITEMS[j] for j in np.where(M[i])[0]] for i, r in zip(t.index, t.itertuples())}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit()
    print("各要素の該当率（穴馬, 2022-2026）")
    a = (d.odds >= 10) & d.y.isin(YEARS)
    for j, nm in enumerate(ITEMS):
        print(f"  {nm}: {M[a.to_numpy(), j].mean() * 100:.1f}%")
    for title, pm in (("穴馬", d.odds >= 10), ("全馬", d.odds > 0)):
        t = d[d.y.isin(YEARS) & pm]
        rows = [summarize(t[t.ippen_n == k], f"{k}個") for k in range(0, 3)] + [summarize(t[t.ippen_n >= 3], "3個以上"), summarize(t[t.ippen_n >= 4], "4個以上")]
        print(f"\n## {title}（固定ルールを過去に当てた参考値）"); print(pd.DataFrame(rows).round(1).to_string(index=False))
