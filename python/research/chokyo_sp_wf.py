# -*- coding: utf-8 -*-
"""
調教SPの改良案を walk-forward で比較（研究用・DB書き込みなし）
- 調教SP2: 調教まわりの各要素の「同年・同基準オッズ帯平均との差（複勝）」を、毎年その年より前のデータで集計し
  縮小推定(n/(n+300))して足し合わせる（EX/本命指数の新方式と同じ考え方）
- 比較: 現行の調教SP（固定ルール）と同じ頭数の割合（A/B/C/D/E）で区切り、実際の回収率・同オッズ差を年別に見る
入力はすべてレース前に確定（T_CYB・T_KYI）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chokyo_sp_eval.py"), encoding="utf-8").read().split("YRS = range")[0])
from kyusha_multi_screen import conn, ROOT  # noqa

CACHE2 = os.path.join(ROOT, ".scratch", "cyb_extra.pkl")
if os.path.exists(CACHE2):
    cy = pd.read_pickle(CACHE2)
else:
    cy = pd.read_sql("""SELECT CONCAT(course_code,year_code,kai,day_code,race_num) AS rid, CAST(uma_num AS UNSIGNED) AS uma,
        TRIM(chokyo_type) AS c_type, TRIM(chokyo_course_type) AS c_ctype, TRIM(course_saka) AS c_saka, TRIM(course_w) AS c_w,
        TRIM(course_pool) AS c_pool, TRIM(course_poly) AS c_poly, TRIM(chokyo_kyori) AS c_kyori, TRIM(chokyo_juten) AS c_juten,
        TRIM(chokyo_ryo_hyoka) AS c_ryo, TRIM(shiage_index_henka) AS c_henka, TRIM(isshuumae_oi_index) AS c_isshu
        FROM T_CYB""", conn())
    cy.to_pickle(CACHE2)
d = d.merge(cy.drop_duplicates(["rid", "uma"]), on=["rid", "uma"], how="left")
d["c_isshu"] = pd.to_numeric(d.c_isshu, errors="coerce")

v = d[d.grade != "なし"].copy().reset_index(drop=True)
cat = lambda s: s.fillna("NA").astype(str).replace("", "NA")
rk = lambda r: np.select([r == 1, r == 2, r == 3, r <= 6], ["1", "2", "3", "4-6"], "7~")
zb = lambda z: np.select([z < -1.5, z < -0.5, z < 0.5, z < 1.5], ["<-1.5", "-1.5~-0.5", "±0.5", "0.5~1.5"], "1.5~")
v["f_oi_rk"] = rk(v.oi_rk); v["f_sh_rk"] = rk(v.sh_rk)
v["f_oi_z"] = zb(np.where(v.oi_sd > 0, (v.oi0 - v.oi_m) / v.oi_sd, 0))
v["f_sh_z"] = zb(np.where(v.sh_sd > 0, (v.sh0 - v.sh_m) / v.sh_sd, 0))
v["f_zpt"] = v.zPt.clip(-4, 0).astype(int).astype(str)
v["f_yaji"] = cat(v.yaji); v["f_hob"] = cat(v.hob)
for c in ("c_type", "c_ctype", "c_saka", "c_w", "c_pool", "c_poly", "c_kyori", "c_juten", "c_ryo", "c_henka"):
    v["f_" + c] = cat(v[c])
dd = v.oi0 - v.c_isshu
v["f_isshu"] = np.select([v.c_isshu.isna() | (v.c_isshu <= 0), dd >= 8, dd >= 3, dd > -3, dd > -8], ["NA", "+8~", "+3~8", "±3", "-3~-8"], "-8以下")
v["f_nyu"] = np.select([v.nyu_d.isna() | (v.nyu_d <= 0), v.nyu_d <= 14, v.nyu_d <= 28, v.nyu_d <= 49], ["NA", "~14日", "15-28日", "29-49日"], "50日~")

CUR = ["f_oi_rk", "f_sh_rk", "f_zpt", "f_yaji", "f_hob"]
NEW = CUR + ["f_oi_z", "f_sh_z", "f_c_type", "f_c_ctype", "f_c_saka", "f_c_w", "f_c_pool", "f_c_poly", "f_c_kyori",
             "f_c_juten", "f_c_ryo", "f_c_henka", "f_isshu", "f_nyu"]
YEARS = [2022, 2023, 2024, 2025, 2026]

# 下見: 各要素の値ごとの同オッズ差（2020〜2026）と、毎年同じ向きか
print("## 下見（2020〜2026、各要素の値ごとの複勝の同オッズ差、n≥1000）")
for f in NEW:
    t = v.groupby(f).agg(n=("place", "size"), 複勝=("place", "mean"), 差=("place_x", "mean"))
    yr = v.groupby([f, "y"]).place_x.mean().unstack()
    t["+年"] = (yr > 0).sum(axis=1); t["-年"] = (yr < 0).sum(axis=1)
    t = t[t.n >= 1000]
    print(f"{f}: " + " / ".join(f"{k}:{r.差:+.1f}({int(r['+年'])}+{int(r['-年'])}-,n={int(r.n)})" for k, r in t.iterrows()))


def wf_score(feats, k=300):
    v["s"] = np.nan
    for Y in YEARS:
        tr = (v.y < Y).to_numpy(); te = (v.y == Y).to_numpy()
        tot = np.zeros(te.sum())
        for f in feats:
            g = v[tr].groupby(f).place_x.agg(["mean", "size"])
            dev = (g["mean"] * g["size"] / (g["size"] + k)).to_dict()
            tot += v.loc[te, f].map(dev).fillna(0).to_numpy()
        v.loc[te, "s"] = tot
    return v["s"].copy()


v["s_cur"] = wf_score(CUR)
v["s_new"] = wf_score(NEW)
t = v[v.y.isin(YEARS)].copy()
share = t.grade.value_counts(normalize=True)
cum = {"A": share["A"], "B": share["A"] + share["B"], "C": share["A"] + share["B"] + share["C"], "D": 1 - share["E"]}


def grade_by_share(col):
    rng = np.random.default_rng(0)
    pct = (t[col] + rng.normal(0, 1e-9, len(t))).groupby(t.y).rank(ascending=False, pct=True)
    return np.select([pct <= cum["A"], pct <= cum["B"], pct <= cum["C"], pct <= cum["D"]], ["A", "B", "C", "D"], "E")


t["g_cur_wf"] = grade_by_share("s_cur"); t["g_new"] = grade_by_share("s_new")
print(f"\n## グレード別比較（2022〜2026、各案とも現行と同じ頭数の割合で A〜E に区切る: A {share['A']*100:.1f}% / B {share['B']*100:.1f}% / ...）")
for col, lab in (("grade", "現行 調教SP（固定ルール）"), ("g_cur_wf", "現行5要素を新方式で"), ("g_new", "調教SP2（全要素・新方式）")):
    rows = []
    for gr in "ABCDE":
        s = t[t[col] == gr]
        r = {"グレード": gr, "n": len(s), "単勝": s.win.mean(), "複勝": s.place.mean(), "3着内率": (s.fin <= 3).mean() * 100,
             "オッズ中央": s.odds.median(), "単差": s.win_x.mean(), "複差": s.place_x.mean()}
        for Y in YEARS:
            r[f"複{str(Y)[2:]}"] = s[s.y == Y].place_x.mean()
        rows.append(r)
    print(f"\n### {lab}"); print(pd.DataFrame(rows).round(1).to_string(index=False))
    a = t[t[col] == "A"]
    print("  A の実際の回収率 年別(単/複): " + "  ".join(f"{Y}:{a[a.y==Y].win.mean():.0f}/{a[a.y==Y].place.mean():.0f}" for Y in YEARS))
# 最上位の細かい帯
print("\n## 上位の細かい帯（2022〜2026）")
for col, lab in (("s_cur", "現行5要素・新方式"), ("s_new", "調教SP2")):
    pct = t[col].groupby(t.y).rank(ascending=False, pct=True)
    for lo, hi in ((0, .01), (.01, .03), (.03, .05), (.05, .10)):
        s = t[(pct > lo) & (pct <= hi)]
        print(f"{lab} 上位{lo*100:.0f}-{hi*100:.0f}%: n={len(s)} 単勝{s.win.mean():.1f}% 複勝{s.place.mean():.1f}% 単差{s.win_x.mean():+.1f} 複差{s.place_x.mean():+.1f} オッズ中央{s.odds.median():.1f}")
gpct = t.sp.rank(ascending=False, pct=True)
