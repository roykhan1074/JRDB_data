# -*- coding: utf-8 -*-
"""
EX指数を「同じオッズ帯の平均より回収率を押し上げているか」で公平に再評価（研究用）
- holdout版: T_ANABA_SCORE_HO（2023年までのデータのみで集計したファクターで2024年以降を採点）
- 先読みあり版: T_ANABA_SCORE（全期間集計、参考）
- 対象: 2024-2026、芝ダ、新馬除外、基準オッズ10倍以上（EX指数の想定対象）
"""
import sys, io, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 220)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
HO_TBL = sys.argv[1] if len(sys.argv) > 1 else "T_ANABA_SCORE_HO"
FROM_YMD = sys.argv[2] if len(sys.argv) > 2 else "20240101"
e = {}
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); e[k] = v
conn = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
J = lambda a: f"{a}.course_code=k.course_code AND {a}.year_code=k.year_code AND {a}.kai=k.kai AND {a}.day_code=k.day_code AND {a}.race_num=k.race_num"
df = pd.read_sql(f"""
SELECT LEFT(b.ymd,4) AS year, CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) AS odds, TRIM(k.in_idm) AS in_idm,
       ho.course_score AS ex_ho, lk.course_score AS ex_lk,
       CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win) AS UNSIGNED),0) ELSE 0 END AS win_pay,
       CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED),0) ELSE 0 END AS place_pay
FROM T_KYI k
JOIN T_BAC b ON {J('b')}
JOIN T_SED s ON {J('s')} AND s.umaban=k.uma_num
JOIN {HO_TBL} ho ON {J('ho')} AND ho.uma_num=k.uma_num
LEFT JOIN T_ANABA_SCORE lk ON {J('lk')} AND lk.uma_num=k.uma_num
WHERE b.ymd >= '{FROM_YMD}' AND TRIM(b.tds_code) IN ('1','2') AND TRIM(b.`class`)<>'A1'
  AND TRIM(s.order_of_finish) <> '' AND TRIM(k.kijun_odds)<>'' AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) BETWEEN 10 AND 999
""", conn)
conn.close()
df["odds"] = df.odds.astype(float)
df["ob"] = pd.cut(df.odds, [10, 15, 30, 50, 1000], right=False, labels=["10-15倍", "15-30倍", "30-50倍", "50倍+"])
# オッズ帯ごとの平均回収率（＝その帯の馬を全部買った場合）を基準にし、各馬の「基準値」とする
for p in ("win_pay", "place_pay"):
    df[p + "_base"] = df.groupby("ob", observed=True)[p].transform("mean")
BANDS = [-1e9, 0, 25, 50, 100, 1e9]; LBL = ["0未満", "0-25", "25-50", "50-100", "100以上"]


def table(col, title):
    d = df[df[col].notna()].copy()
    d["b"] = pd.cut(d[col], BANDS, labels=LBL, right=False)
    print(f"\n### {title}（{FROM_YMD[:4]}年以降・基準オッズ10倍以上）")
    print("帯 | 頭数 | 単勝回収率 | 同オッズ構成の平均 | 差 | 複勝回収率 | 同平均 | 差 | 単勝 2024/2025/2026")
    for b, x in d.groupby("b", observed=True):
        yr = "/".join(f"{x[x.year == y].win_pay.mean():.0f}" for y in ("2024", "2025", "2026"))
        print(f"{b} | {len(x):,} | {x.win_pay.mean():.1f}% | {x.win_pay_base.mean():.1f}% | {x.win_pay.mean()-x.win_pay_base.mean():+.1f} | "
              f"{x.place_pay.mean():.1f}% | {x.place_pay_base.mean():.1f}% | {x.place_pay.mean()-x.place_pay_base.mean():+.1f} | {yr}")


print("オッズ帯ごとの平均回収率（基準）:")
print(df.groupby("ob", observed=True)[["win_pay", "place_pay"]].mean().round(1).to_string())
table("ex_ho", "EX指数(コース) holdout版＝先読みなし")
table("ex_lk", "EX指数(コース) 全期間集計版＝先読みあり（参考）")
