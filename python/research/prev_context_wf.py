# -*- coding: utf-8 -*-
"""
前走の「状況」（展開との噛み合い・不利の程度・出遅れの程度・叩き2戦目・2走前→前走の流れ）の検証（研究用）。
1) 下見: 各要素の複勝回収率の同オッズ帯平均との差を年ごと（2021-2026）に見る
2) sc（最新版）に加点/減点して上位が良くなるかを walk-forward で検証（点数は毎年その年より前のデータで決定）
前走・2走前は T_KYI.prev1/prev2_seiseki_key（血統登録番号8桁+年月日8桁）で T_SED と結合。いずれもレース前に確定した情報。
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
pd.set_option("display.width", 250)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS6 = [2021, 2022, 2023, 2024, 2025, 2026]
YEARS = [2022, 2023, 2024, 2025, 2026]

d = pd.read_pickle(os.path.join(ROOT, ".scratch", "prev_prepped.pkl"))
CACHE = os.path.join(ROOT, ".scratch", "sed_ext.pkl")
if os.path.exists(CACHE):
    sed = pd.read_pickle(CACHE)
else:
    e = {}
    for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        l = l.strip()
        if l and "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); e[k] = v
    c = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
    sed = pd.read_sql("""
      SELECT CONCAT(TRIM(blood_num), TRIM(ymd)) AS skey, TRIM(ymd) AS s_ymd, TRIM(race_pace) AS s_rpace,
             TRIM(race_kyakushitsu) AS s_kya, TRIM(furi) AS s_furi, TRIM(mae_furi) AS s_mae, TRIM(naka_furi) AS s_naka,
             TRIM(ushiro_furi) AS s_ushiro, TRIM(deokure) AS s_deo, TRIM(order_of_finish) AS s_fin, TRIM(idm) AS s_idm
      FROM T_SED""", c)
    c.close()
    sed = sed.drop_duplicates("skey")
    sed.to_pickle(CACHE)
p1 = sed.add_prefix("p1_").rename(columns={"p1_skey": "p1key"})
p2 = sed[["skey", "s_ymd", "s_fin", "s_idm"]].add_prefix("p2_").rename(columns={"p2_skey": "p2key"})
d = d.merge(p1, on="p1key", how="left").merge(p2, on="p2key", how="left")
num = lambda s: pd.to_numeric(s.astype(str).str.strip(), errors="coerce")
for c in ("p1_s_furi", "p1_s_mae", "p1_s_naka", "p1_s_ushiro", "p1_s_deo", "p1_s_fin", "p1_s_idm", "p2_s_fin", "p2_s_idm"):
    d[c] = num(d[c])
has1 = d.p1_s_ymd.notna()
has2 = d.p2_s_ymd.notna()
dt = lambda s: pd.to_datetime(s, format="%Y%m%d", errors="coerce")
gap_now = (dt(d.ymd) - dt(d.p1_s_ymd)).dt.days
gap_prev = (dt(d.p1_s_ymd) - dt(d.p2_s_ymd)).dt.days
front = d.p1_s_kya.isin(["1", "2"]); back = d.p1_s_kya.isin(["3", "4"])
lost = d.p1_s_fin >= 4; good = d.p1_s_fin <= 3

# --- 要素
d["f_前走展開"] = np.select(
    [~has1 | d.p1_s_rpace.isna() | d.p1_s_kya.isna(),
     (d.p1_s_rpace == "H") & front & lost, (d.p1_s_rpace == "S") & back & lost,
     (d.p1_s_rpace == "H") & back & good, (d.p1_s_rpace == "S") & front & good],
    ["NA", "Hペース先行で負け", "Sペース差しで負け", "Hペース差しで好走", "Sペース先行で好走"], default="その他")
furi_max = d[["p1_s_furi", "p1_s_mae", "p1_s_naka", "p1_s_ushiro"]].max(axis=1)
d["f_不利の程度"] = np.select([~has1, furi_max.isna() | (furi_max == 0), furi_max == 1, furi_max == 2], ["NA", "なし", "1", "2"], default="3以上")
d["f_不利×着順"] = np.select([~has1, furi_max.fillna(0) == 0, lost], ["NA", "不利なし", "不利で負け"], default="不利でも好走")
d["f_出遅れの程度"] = np.select([~has1, d.p1_s_deo.isna() | (d.p1_s_deo == 0), d.p1_s_deo == 1], ["NA", "なし", "1"], default="2以上")
d["f_叩き"] = np.select([~has1 | gap_now.isna(), gap_now >= 70, has2 & (gap_prev >= 70) & (gap_now <= 42)],
                        ["NA", "休み明け初戦", "叩き2戦目"], default="その他")
fin_tr = d.p2_s_fin - d.p1_s_fin   # プラス = 前走の方が着順が良い
d["f_着順の流れ"] = np.select([~(has1 & has2) | fin_tr.isna(), fin_tr >= 3, fin_tr <= -3], ["NA", "上昇(3着以上良化)", "悪化(3着以上)"], default="横ばい")
idm_tr = d.p1_s_idm - d.p2_s_idm
d["f_IDMの流れ"] = np.select([~(has1 & has2) | idm_tr.isna(), idm_tr >= 5, idm_tr <= -5], ["NA", "上昇(+5以上)", "低下(−5以下)"], default="横ばい")

FEATS = ["f_前走展開", "f_不利の程度", "f_不利×着順", "f_出遅れの程度", "f_叩き", "f_着順の流れ", "f_IDMの流れ"]
x = d[d.y >= 2021]
print("## 1. 下見（複勝回収率の同オッズ帯平均との差、年別）")
for f in FEATS:
    t = x.groupby(f).agg(n=("place", "size"), 複勝=("place", "mean"), 差=("place_x", "mean"))
    for Y in YEARS6:
        t[str(Y)] = x[x.y == Y].groupby(f).place_x.mean()
    s = np.sign(t[[str(Y) for Y in YEARS6]])
    t["毎年同じ向き"] = (s == 1).all(axis=1) | (s == -1).all(axis=1)
    print(f"\n### {f[2:]}")
    print(t.round(1).to_string())

# --- 2. sc に加える（walk-forward）
sc = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))[["rid", "uma", "sc"]]
d = d.merge(sc, on=["rid", "uma"], how="inner")
d = d[d.y >= 2021].reset_index(drop=True)
CAND = {f"{f[2:]}={v}": (d[f] == v) for f in FEATS for v in d[f].unique() if v not in ("NA", "その他", "なし", "横ばい", "不利なし")}
F = {k: v.astype(float).to_numpy() for k, v in CAND.items()}
Xs = pd.get_dummies(d.sc.clip(-2, 12).astype(int).astype(str), prefix="sc").astype(float).to_numpy()
d["sc_ctx"] = np.nan
print("\n## 2. sc への加点・減点（毎年その年より前のデータで決定）")
for Y in YEARS:
    tr = (d.y < Y).values
    X = np.column_stack([np.ones(len(d)), Xs] + [F[k] for k in CAND])
    beta, *_ = np.linalg.lstsq(X[tr], d.loc[tr, "place_x"].to_numpy(), rcond=None)
    eff = dict(zip(CAND, beta[-len(CAND):]))
    pts = {k: (int(np.round(v / 4)) if abs(v) >= 2 else 0) for k, v in eff.items()}
    m = (d.y == Y).values
    d.loc[m, "sc_ctx"] = d.loc[m, "sc"] + sum(pts[k] * F[k][m] for k in CAND)
    print(f"{Y}: " + ", ".join(f"{k} {pts[k]:+d}" for k in CAND if pts[k] != 0), flush=True)

t = d[d.y.isin(YEARS)].copy()
print("\n### 最新 sc と同じ頭数で比較（同点の乱数30通りの平均と幅、2022〜2026）")
for N in (6, 7, 8, 9):
    res = {"最新 sc": [], "sc＋前走の状況": []}
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        for col, lab in (("sc", "最新 sc"), ("sc_ctx", "sc＋前走の状況")):
            parts = []
            for Y in YEARS:
                ty = t[t.y == Y]; k = int((ty.sc >= N).sum())
                parts.append(ty.sort_values([col, "tie"], ascending=False).head(k))
            xx = pd.concat(parts)
            res[lab].append((xx.place_x.mean(), xx.place.mean(), xx.win.mean(), (xx.fin <= 3).mean() * 100,
                             *[xx[xx.y == Y].place_x.mean() for Y in YEARS]))
    for lab, v in res.items():
        a = np.array(v)
        yr = " / ".join(f"{a[:, 4 + i].mean():+.1f}" for i in range(len(YEARS)))
        print(f"sc≥{N}相当 {lab}: 差{a[:, 0].mean():+.1f}（幅{a[:, 0].min():+.1f}〜{a[:, 0].max():+.1f}） 年別[{yr}] 複勝{a[:, 1].mean():.1f}% 単勝{a[:, 2].mean():.1f}% 3着内率{a[:, 3].mean():.1f}%")
