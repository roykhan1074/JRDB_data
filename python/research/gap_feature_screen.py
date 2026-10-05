# -*- coding: utf-8 -*-
"""
指数の差・クラス基準との差・市場評価とのずれ 等の要素の下見（研究用）。
各要素を5段階に分け、複勝回収率の「同じ年・同じオッズ帯の平均との差」を年ごと（2021-2026）に見る。
※ 採用判断ではなく候補の洗い出し。採用は毎年選び直す方式で別途検証する。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import prob_wf as P   # データ取得と基本の前処理（レース内順位・最高値との差・偏差）を流用
pd.set_option("display.width", 250)

d = P.prepare(P.fetch())
d = d[(d.shinba == 0) & (d.year >= 2020)].copy()
d["place"] = pd.to_numeric(d.place_pay, errors="coerce").fillna(0)
d.loc[~d.ijou.isin(["0", ""]), "place"] = 0
d["ob"] = pd.cut(d.kijun_odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
d["place_x"] = d.place - d.groupby(["year", "ob"]).place.transform("mean")

g = d.groupby("race_id")
# 1位の馬が2位をどれだけ離しているか（1位の馬だけ値を持つ。他は NaN）
for c in ("idm", "ten_index", "agari_index"):
    top2 = g[c].transform(lambda s: s.nlargest(2).iloc[-1] if s.notna().sum() >= 2 else np.nan)
    d[f"{c}_lead"] = np.where(d[f"{c}_rk"] == 1, d[c] - top2, np.nan)
# クラス・芝ダの基準との差（その年より前の平均を使う＝先読みなし）
d["cls_key"] = d.cls.astype(str) + "_" + d.tds_code.astype(str)
d["idm_cls_dev"] = np.nan
for Y in range(2021, 2027):
    ref = d[d.year < Y].groupby("cls_key").idm.mean()
    m = d.year == Y
    d.loc[m, "idm_cls_dev"] = d.loc[m, "idm"] - d.loc[m, "cls_key"].map(ref)
# 市場評価とのずれ: 人気順位 − IDM順位（プラス＝人気より能力が上）
d["ninki_minus_idmrk"] = d.kijun_ninki - d.idm_rk
d["futan_dev"] = d.futan_juryo - g.futan_juryo.transform("mean")

FEATS = {
    "IDM 最高値との差": "idm_dmax", "IDM 偏差": "idm_z", "IDM 1位の抜け幅": "idm_lead", "IDM クラス基準との差": "idm_cls_dev",
    "テン指数 最高値との差": "ten_index_dmax", "テン指数 1位の抜け幅": "ten_index_lead",
    "上がり指数 最高値との差": "agari_index_dmax", "上がり指数 1位の抜け幅": "agari_index_lead",
    "位置指数 最高値との差": "ichi_index_dmax", "総合指数 最高値との差": "sogo_index_dmax",
    "人気順位−IDM順位": "ninki_minus_idmrk", "斤量 レース平均との差": "futan_dev", "ローテーション": "rotation",
}
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
x = d[d.year >= 2021]
for lab, col in FEATS.items():
    v = x[col]
    if v.notna().sum() < 1000:
        continue
    try:
        b = pd.qcut(v, 5, duplicates="drop")
    except ValueError:
        continue
    t = x.groupby(b, observed=True).agg(n=("place", "size"), 複勝=("place", "mean"), 差=("place_x", "mean"))
    for Y in YEARS:
        t[str(Y)] = x[x.year == Y].groupby(b[x.year == Y], observed=True).place_x.mean()
    signs = np.sign(t[[str(Y) for Y in YEARS]])
    t["毎年同じ向き"] = (signs.abs().sum(axis=1) == 6) & ((signs == 1).all(axis=1) | (signs == -1).all(axis=1))
    print(f"\n### {lab}（{col}）")
    print(t.round(1).to_string())
