# -*- coding: utf-8 -*-
"""
傾向点の改良版: 「位置取りの要素（枠番・内外・脚質・脚質×内外）だけコース別に見る」（研究用）。
指数の順位・適性・血統は芝ダ×距離帯で見る。クラス差あり/なしの2通り。
毎年 Y について Y年より前のデータだけで推定（walk-forward）。tendency_wf.py の関数を流用。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import tendency_wf as TW

POS = {"f_waku", "f_pos", "f_kya", "f_kya_pos"}


def score_mixed(tr, te, use_class):
    T = np.zeros(len(te))
    for f in TW.FACTORS:
        course = f in POS
        E = TW.effects(tr, f, use_course=course, use_class=use_class)
        base = te[[f]].merge(E["g0"], left_on=f, right_index=True, how="left")["g0"].fillna(0).to_numpy()
        v1 = te[["seg1", f]].merge(E["g1"], on=["seg1", f], how="left")["g1"].to_numpy()
        val = np.where(np.isnan(v1), base, v1)
        if course:
            v2 = te[["seg2", f]].merge(E["g2"], on=["seg2", f], how="left")["g2"].to_numpy()
            val = np.where(np.isnan(v2), val, v2)
        if use_class:
            vc = te[["segc", f]].merge(E["gc"], on=["segc", f], how="left")["gc"].to_numpy()
            val = val + np.nan_to_num(vc)
        T += val
    return T


if __name__ == "__main__":
    d = pd.read_pickle(os.path.join(TW.ROOT, ".scratch", "tendency_scored.pkl"))
    for lab, use_class in (("T位置のみコース別", False), ("T位置のみコース別+クラス", True)):
        d[lab] = np.nan
        for Y in TW.TEST_YEARS:
            m = (d.y == Y).values
            d.loc[m, lab] = score_mixed(d[d.y < Y], d[m], use_class)
        print(lab, "計算済み", flush=True)
    d.to_pickle(os.path.join(TW.ROOT, ".scratch", "tendency_scored.pkl"))
