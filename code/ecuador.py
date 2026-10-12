"""Ecuador: the Napo / Orellana enforcement (Sept 2023), compared with the Peru and Brazil areas. DRAFT, team must review.

WHY AMW: MapBiomas Ecuador is not in our pack and the Peru-style steps (event study from 2011, model ladder) need a pre-period
of 10 years. Amazon Mining Watch (AMW) starts in 2018 (2018 = stock), so ALL steps here use AMW and the windows are short:
pre = 2020-22, post = 2023-24 (primary, confirmed) and 2023-25 (2025 is PROVISIONAL).

Inputs  data_raw/amw/amw_ecuador.geojson      AMW patches in a lon/lat box around Ecuador (made by code/clip_amw_ecuador.py
                                              from the full file; same sha256 as the team's 2026-10-10 download)
        data_raw/geoboundaries/*ADM1/ADM2*   province and canton borders (geoBoundaries, simplified)
        data_intermediate/amw_candidates_*   Peru / Brazil areas already built by the team (same AMW file)
        data_intermediate/ecuador_operations_coded.csv   enforcement reports we opened (and some we did not)
Outputs data_intermediate/ecuador_province_year.csv, ecuador_canton_year.csv; output/ecuador_*.csv, fig_ecuador_*.png,
        output/numbers_ecuador.csv (ids prefixed ec_).

CLAIM TYPE: everything here is DESCRIPTION. The Ecuador operations FOLLOWED the 2023 surge (reverse causation), the control
provinces are weak (national programme from Oct 2024, own surges), and AMW cannot see dredges. No causal sentence is justified.
"""
from __future__ import annotations
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, OUT, Numbers, style_axes, finish_figure

RAW, INTER = ROOT / "data_raw", ROOT / "data_intermediate"
AMW = RAW / "amw/amw_ecuador.geojson"
ADM1 = RAW / "geoboundaries/geoBoundaries-ECU-ADM1_simplified.geojson"
ADM2 = RAW / "geoboundaries/geoBoundaries-ECU-ADM2_simplified.geojson"
CRS_AREA = "ESRI:102033"
YEARS = list(range(2018, 2027))
PRE, POST, POST_P = (2020, 2021, 2022), (2023, 2024), (2023, 2024, 2025)
OP_EC = 2023            # Sept 2023 (Primicias); one May-2023 report conflicts (see ecuador_operations_coded.csv)
T1 = ["Napo", "Orellana"]
POOL = ["Zamora Chinchipe", "Morona Santiago", "Sucumbios"]
PROV_LABEL = {"Sucumbios": "Sucumbíos"}
SRC = ("Amazon Mining Watch (Earth Genome), CC-BY-4.0, clipped to Ecuador with code/clip_amw_ecuador.py; borders: geoBoundaries "
       "ADM1/ADM2; operations: data_intermediate/ecuador_operations_coded.csv")
NOTE = ("AMW = mining scars on land (480 m patches, upper bound); 2018 is a stock; 2025 provisional; no river dredges, no mercury. "
        "Patches are assigned to provinces by their centroid with simplified borders. Description only.")
COL = {"treated": "#eb6834", "pool": "#2a78d6", "other": "#7d7c78"}


# --------------------------------------------------------------------------- build intermediates
def build():
    import geopandas as gpd
    from spatial import yearly_new_ha
    p = gpd.read_file(AMW)
    p["geometry"] = p.geometry.make_valid()
    cen = gpd.GeoDataFrame(geometry=p.to_crs(CRS_AREA).geometry.centroid, crs=CRS_AREA, index=p.index).to_crs(4326)
    a1 = gpd.read_file(ADM1)[["shapeName", "geometry"]]
    a2 = gpd.read_file(ADM2)[["shapeName", "geometry"]].rename(columns={"shapeName": "canton"})
    j1 = gpd.sjoin(cen, a1, how="left", predicate="within")
    j2 = gpd.sjoin(cen, a2, how="left", predicate="within")
    p["province_adm1"] = j1.shapeName.groupby(level=0).first()
    p["canton"] = j2.canton.groupby(level=0).first()
    # The simplified ADM1 and ADM2 borders disagree along the Napo/Orellana line (41 patches in Napo by ADM1 lie in Orellana canton
    # by ADM2). The canton is the finer unit, so the province is the majority ADM1 label of the canton's patches.
    maj = p.dropna(subset=["canton"]).groupby("canton").province_adm1.agg(lambda x: x.mode().iat[0])
    p["province"] = p.canton.map(maj)
    n_moved = int((p.province.notna() & (p.province != p.province_adm1)).sum())
    n_all, n_in = len(p), int(p.province.notna().sum())
    pa = p.to_crs(CRS_AREA)
    ins = pa[pa.province.notna()]

    def table(col):
        rows = []
        for k, g in ins.groupby(col):
            d = yearly_new_ha(g)
            for y in YEARS:
                rows.append(dict(unit=k, year=y, new_ha=d.get(y, 0.0), n_patches=int((g.onset_year == y).sum())))
        return pd.DataFrame(rows)
    prov = table("province")
    prov = prov.merge(ins.groupby("province").canton.first().rename("x"), left_on="unit", right_index=True, how="left").drop(columns="x")
    cant = table("canton")
    cant["province"] = cant.unit.map(ins.groupby("canton").province.first())
    prov.to_csv(INTER / "ecuador_province_year.csv", index=False)
    cant.to_csv(INTER / "ecuador_canton_year.csv", index=False)
    prov.attrs["n_moved"] = n_moved
    return prov, cant, n_all, n_in


def load_or_build():
    f1, f2 = INTER / "ecuador_province_year.csv", INTER / "ecuador_canton_year.csv"
    if AMW.exists():
        prov, cant, n_all, n_in = build()
    elif f1.exists() and f2.exists():
        warnings.warn("ecuador: raw AMW extract missing, reading intermediates")
        prov, cant, n_all, n_in = pd.read_csv(f1), pd.read_csv(f2), np.nan, np.nan
    else:
        return None
    return prov, cant, n_all, n_in


# --------------------------------------------------------------------------- helpers
def mean_ha(s: pd.Series, yrs) -> float:
    return float(s.loc[list(yrs)].mean())


def lnchg(s: pd.Series, pre=PRE, post=POST, floor=20.0):
    a, b = mean_ha(s, pre), mean_ha(s, post)
    return (np.log(b / a) if a >= floor and b > 0 else np.nan), a, b


def series_table(prov: pd.DataFrame) -> pd.DataFrame:
    w = prov.pivot(index="year", columns="unit", values="new_ha").fillna(0.0)
    g = pd.DataFrame(index=w.index)
    g["Napo + Orellana (operation Sept 2023)"] = w[T1].sum(axis=1)
    g["Napo"], g["Orellana"] = w["Napo"], w["Orellana"]
    g["Pool: Zamora Ch. + Morona S. + Sucumbíos"] = w[POOL].sum(axis=1)
    for k in POOL:
        g[PROV_LABEL.get(k, k)] = w[k]
    g["Ecuador total (Amazon basin patches)"] = w.sum(axis=1)
    return g


# --------------------------------------------------------------------------- comparison tables
def window_table(g: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for k in g:
        l, a, b = lnchg(g[k]); _, _, b3 = lnchg(g[k], post=POST_P)
        rows.append(dict(area=k, pre_mean_2020_22=a, post_mean_2023_24=b, post_mean_2023_25_prov=mean_ha(g[k], POST_P),
                         change_pct_2023_24=100 * (b / a - 1) if a > 0 else np.nan, ln_change=l,
                         ha_per_year_change=b - a))
    return pd.DataFrame(rows)


def gap_table(g: pd.DataFrame) -> pd.DataFrame:
    """Treated (Napo+Orellana) minus pool, in ln points, for several windows and leave-one-out pools."""
    t, pool = g.iloc[:, 0], g["Pool: Zamora Ch. + Morona S. + Sucumbíos"]
    rows = []

    def add(label, tt, pp, pre, post):
        lt, _, _ = lnchg(tt, pre, post); lp, _, _ = lnchg(pp, pre, post)
        rows.append(dict(spec=label, treated_ln=lt, pool_ln=lp, gap_ln_points=lt - lp,
                         treated_pct=100 * (np.exp(lt) - 1), pool_pct=100 * (np.exp(lp) - 1)))
    add("Primary: pre 2020-22, post 2023-24", t, pool, PRE, POST)
    add("Provisional: post 2023-25", t, pool, PRE, POST_P)
    add("Shorter pre 2021-22", t, pool, (2021, 2022), POST)
    for k in ("Zamora Ch.", "Morona S.", "Sucumbíos"):
        name = {"Zamora Ch.": "Zamora Chinchipe", "Morona S.": "Morona Santiago", "Sucumbíos": "Sucumbíos"}[k]
        rest = g[[c for c in ("Zamora Chinchipe", "Morona Santiago", "Sucumbíos") if c != name]].sum(axis=1)
        add(f"Leave out {name} from pool", t, rest, PRE, POST)
    add("Placebo in time: fake start 2021 (pre 2019-20, post 2021-22)", t, pool, (2019, 2020), (2021, 2022))
    return pd.DataFrame(rows)


def cross_area():
    """Same calendar windows (pre 2020-22 -> post 2023-24) for Ecuador, Peru and Brazil areas from ONE AMW file."""
    import brazil_stagger as bs
    u = pd.read_csv(INTER / "amw_candidates_units.csv").set_index("unit_id")
    w = pd.read_csv(INTER / "amw_candidates_year.csv").pivot(index="year", columns="unit_id", values="new_ha")
    g, _, pool, wb = bs.load()
    rows = []

    def add(country, area, s, own_op, stock=np.nan):
        l, a, b = lnchg(s)
        rows.append(dict(country=country, area=area, own_operation_in_2023_24=own_op, pre_mean_2020_22=a, post_mean_2023_24=b,
                         change_pct=100 * (b / a - 1) if a > 0 else np.nan, ln_change=l,
                         ratio_2025_prov_to_2023_24=float(s.loc[2025] / b) if b > 0 else np.nan,
                         stock_2018_ha=stock, post_pct_of_2018_stock_per_year=100 * b / stock if stock > 0 else np.nan))
    return u, w, g, pool, wb, add, rows


def build_cross(ec: pd.DataFrame):
    import brazil_stagger as bs
    u, w, g, pool, wb, add, rows = cross_area()
    add("Ecuador", "Napo + Orellana", ec["Napo + Orellana (operation Sept 2023)"], "yes: Sept 2023", ec.iloc[:, 0].loc[2018])
    add("Ecuador", "Napo", ec["Napo"], "yes: Sept 2023", ec["Napo"].loc[2018])
    add("Ecuador", "Orellana", ec["Orellana"], "yes: Sept 2023", ec["Orellana"].loc[2018])
    add("Ecuador", "Pool (Zamora, Morona, Sucumbíos)", ec["Pool: Zamora Ch. + Morona S. + Sucumbíos"], "no dated before 2025 (not searched = not none)", ec["Pool: Zamora Ch. + Morona S. + Sucumbíos"].loc[2018])
    add("Peru", "Tambopata buffer zone", w["PE-BZ-RN09"], "yes: emergency Apr 2023 (and Mercurio 2019)", w["PE-BZ-RN09"].loc[2018])
    add("Peru", "Amarakaeri buffer zone", w["PE-BZ-RC03"], "partly: emergency districts Apr 2023", w["PE-BZ-RC03"].loc[2018])
    add("Brazil", "Yanomami", g["Yanomami"], "yes: Feb 2023", wb[bs.GROUPS["Yanomami"]].loc[2018].sum())
    add("Brazil", "Munduruku + Sai-Cinza", g["Munduruku + Sai-Cinza"], "yes: Aug 2023", wb[bs.GROUPS["Munduruku + Sai-Cinza"]].loc[2018].sum())
    add("Brazil", "Kayapó", g["Kayapó"], "operation 2024 (inside post window)", wb[bs.GROUPS["Kayapó"]].loc[2018].sum())
    add("Brazil", "Sararé", g["Sararé"], "operation 2024 (inside post window)", wb[bs.GROUPS["Sararé"]].loc[2018].sum())
    add("Brazil", "No-operation pool", g[bs.POOL], "none found", wb[pool].loc[2018].sum())
    add("Brazil", "Amanã (rule-based twin of Tambopata)", w["RAISG-434"], "none found 2017-21", w["RAISG-434"].loc[2018]) if "RAISG-434" in w else None
    return pd.DataFrame(rows), w, u


def space_placebo(ec: pd.DataFrame, w: pd.DataFrame, u: pd.DataFrame, floor=100.0):
    """Rank of Napo+Orellana's ln change among ALL AMW candidate areas (Peru, Brazil, ... 1,174) with pre mean >= floor ha.
    Areas overlap (protected areas, territories, buffer zones), so this is a ranking, not a sample."""
    t, _, _ = lnchg(ec["Napo + Orellana (operation Sept 2023)"])
    vals = {}
    for c in w.columns:
        a, b = mean_ha(w[c], PRE), mean_ha(w[c], POST)
        if a >= floor and b > 0:
            vals[c] = np.log(b / a)
    s = pd.Series(vals).sort_values(ascending=False)
    rank = int((s > t).sum()) + 1
    return t, s, rank, u


def stock_rank(ec, w, u, floor_stock=100.0):
    """Napo+Orellana's mean 2023-24 new mining as % of its own 2018 AMW stock, ranked among all candidate areas with a 2018 stock
    >= floor_stock ha. Scale-free, so a small base does not by itself make the number large. Areas overlap."""
    t = ec.iloc[:, 0]
    mine = 100 * mean_ha(t, POST) / t.loc[2018]
    v = {c: 100 * mean_ha(w[c], POST) / w[c].loc[2018] for c in w.columns if w[c].loc[2018] >= floor_stock}
    s = pd.Series(v).sort_values(ascending=False)
    return mine, s, int((s > mine).sum()) + 1


def index_table(ec):
    """New mining per year, 2020-22 mean = 100, for the operation provinces and the pool (reads the event-study-like picture)."""
    cols = {"Napo + Orellana": ec.iloc[:, 0], "Pool": ec["Pool: Zamora Ch. + Morona S. + Sucumbíos"]}
    return pd.DataFrame({k: 100 * v / mean_ha(v, PRE) for k, v in cols.items()}).loc[2019:2025]


# --------------------------------------------------------------------------- figures
def fig_main(ec: pd.DataFrame, ops: pd.DataFrame):
    cols = ["Napo", "Orellana", "Zamora Chinchipe", "Morona Santiago", "Sucumbíos", "Ecuador total (Amazon basin patches)"]
    kind = ["treated", "treated", "pool", "pool", "pool", "other"]
    yrs = list(range(2019, 2026))
    fig, axes = plt.subplots(1, 6, figsize=(14, 3.9), sharex=True)
    for ax, c, kd in zip(axes, cols, kind):
        for y in yrs:
            prov = y == 2025
            ax.bar(y, ec.loc[y, c], 0.75, color=COL[kd], alpha=0.45 if prov else 1, hatch="///" if prov else None,
                   edgecolor=COL[kd] if prov else "white", linewidth=0.5)
        if kd == "treated":
            ax.axvline(OP_EC - 0.5 + 8 / 12, color="black", lw=1.4)
            ax.annotate("operation\nSept 2023", (OP_EC + 0.17, ax.get_ylim()[1] * 0.97), xytext=(3, 0),
                        textcoords="offset points", fontsize=7, va="top")
        ax.axvline(2024.75, color="#9aa5a8", ls="--", lw=0.9)           # Oct 2024: national CONIM programme
        a, b = mean_ha(ec[c], PRE), mean_ha(ec[c], POST)
        sub = f"avg {a:,.0f} → {b:,.0f} ha/yr"
        ax.set_title(f"{c.split(" (")[0].replace("Ecuador total","All Ecuador")}\n{sub}", loc="left", fontsize=8.2)
        style_axes(ax)
        ax.set_xticks(yrs); ax.set_xticklabels([f"'{str(y)[2:]}" for y in yrs], fontsize=7.5)
    axes[0].set_ylabel("New mining detected (ha)")
    fig.legend(handles=[Line2D([], [], color="black", lw=1.4, label="Sept 2023 operation (Napo, Orellana)"),
                        Line2D([], [], color="#9aa5a8", ls="--", label="Oct 2024: national CONIM programme starts"),
                        Patch(facecolor="#bbbbbb", hatch="///", edgecolor="#888888", label="2025 provisional")],
               loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 0.1))
    fig.suptitle("Ecuador: mining in Napo and Orellana jumped in 2023 and stayed high after the September 2023 operation",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    finish_figure(fig, f"Source: {SRC}. {NOTE} Y-axes differ. Orange = operation provinces, blue = comparison provinces (their own raids "
                       "are mostly 2025 in our searches; not searched is not none).", OUT / "fig_ecuador_main.png", rect_bottom=0.2,
                  event_note=False)


def fig_cross(cross: pd.DataFrame):
    d = cross.dropna(subset=["ln_change"]).copy()
    d = d[~d.area.isin(["Napo", "Orellana"])].sort_values("ln_change")
    colmap = {"Ecuador": "#eb6834", "Peru": "#2a78d6", "Brazil": "#1baf7a"}
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(d) + 1.6))
    y = np.arange(len(d))
    ax.barh(y, 100 * (np.exp(d.ln_change) - 1), color=[colmap[c] for c in d.country], height=0.65)
    ax.axvline(0, color="black", lw=0.8)
    for yi, r in zip(y, d.itertuples()):
        v = 100 * (np.exp(r.ln_change) - 1)
        ax.text(v + (8 if v >= 0 else -8), yi, f"{v:+,.0f}%  ({r.pre_mean_2020_22:,.0f}→{r.post_mean_2023_24:,.0f} ha/yr)", va="center",
                ha="left" if v >= 0 else "right", fontsize=7.5)
    ax.set_xlabel("Change in mean yearly new mining, 2020-22 → 2023-24 (%)")
    ax.margins(x=0.45)
    style_axes(ax)
    ax.set_yticks(y); ax.set_yticklabels([f"{r.area} ({r.country})" for r in d.itertuples()], fontsize=8.5)
    ax.set_title("Same two windows, one satellite dataset:\nNapo + Orellana grew most; Brazil's operation areas fell",
                 loc="left", fontsize=10, fontweight="bold")
    finish_figure(fig, "Source: Amazon Mining Watch (Earth Genome), CC-BY-4.0; teams' area definitions (data_intermediate/amw_candidates_*), "
                       "Ecuador from this step. Operations fall in different years and months, so this is a calendar comparison, not an "
                       "effect. Areas with < 20 ha/yr before are omitted. AMW sees mining on land, not dredges. Description.",
                  OUT / "fig_ecuador_cross_area.png", rect_bottom=0.12, event_note=False)


# --------------------------------------------------------------------------- run
def run(reg: Numbers):
    print("\n== Ecuador: Napo / Orellana vs comparison provinces vs Peru and Brazil (AMW) ==")
    res = load_or_build()
    if res is None:
        warnings.warn("ecuador: no data (data_raw/amw/amw_ecuador.geojson or intermediates); skipping"); return
    prov, cant, n_all, n_in = res
    ec = series_table(prov)
    ec.round(1).to_csv(OUT / "ecuador_series_amw.csv")
    print(ec.round(0).to_string())

    wt = window_table(ec); wt.round(2).to_csv(OUT / "ecuador_windows.csv", index=False)
    gt = gap_table(ec); gt.round(3).to_csv(OUT / "ecuador_gap_specs.csv", index=False)
    print(wt.round(1).to_string(index=False)); print(gt.round(2).to_string(index=False))

    cross, w, u = build_cross(ec)
    cross.round(2).to_csv(OUT / "ecuador_cross_area.csv", index=False)
    print(cross.round(1).to_string(index=False))
    t, s, rank, u = space_placebo(ec, w, u)
    ctry = u.loc[s.index, "country"]
    s_df = pd.DataFrame({"unit_id": s.index, "country": ctry.values, "name": u.loc[s.index, "name"].values,
                         "ln_change": s.values}).head(25)
    s_df.round(3).to_csv(OUT / "ecuador_space_placebo_top25.csv", index=False)
    print(f"Napo+Orellana ln change {t:.2f}; rank {rank} of {len(s) + 1} areas (Peru/Brazil/... with >=100 ha/yr before)")

    # cantons: where inside the operation provinces?
    c = cant[cant.province.isin(T1)].pivot(index="unit", columns="year", values="new_ha").fillna(0)
    c["pre_2020_22"] = c[list(PRE)].mean(axis=1); c["post_2023_24"] = c[list(POST)].mean(axis=1)
    c["share_of_post_2023_24"] = c.post_2023_24 / c.post_2023_24.sum()
    c = c.sort_values("post_2023_24", ascending=False)
    c.round(2).to_csv(OUT / "ecuador_cantons_operation_provinces.csv")
    print(c[[2022, 2023, 2024, 2025, "pre_2020_22", "post_2023_24", "share_of_post_2023_24"]].head(8).round(2).to_string())

    idx = index_table(ec); idx.round(1).to_csv(OUT / "ecuador_index_2020_22_eq_100.csv")
    st_mine, st_s, st_rank = stock_rank(ec, w, u)
    pd.DataFrame({"unit_id": st_s.index, "name": u.loc[st_s.index, "name"].values, "country": u.loc[st_s.index, "country"].values,
                  "post_pct_of_2018_stock": st_s.values}).head(15).round(1).to_csv(OUT / "ecuador_stock_rank_top15.csv", index=False)
    print(f"Napo+Orellana: 2023-24 new mining = {st_mine:.0f}% of its 2018 stock per year; rank {st_rank} of {len(st_s) + 1}")
    pr_ = pd.read_csv(ROOT / "data/prices_annual.csv").set_index("year")["gold"]
    gold = 100 * (pr_.loc[list(POST)].mean() / pr_.loc[list(PRE)].mean() - 1)
    print(f"gold price (nominal USD/oz) mean 2023-24 vs 2020-22: {gold:+.0f}%")
    ops = pd.read_csv(INTER / "ecuador_operations_coded.csv")
    fig_main(ec, ops); fig_cross(cross)

    # ---- numbers
    T = ec.iloc[:, 0]; P = ec["Pool: Zamora Ch. + Morona S. + Sucumbíos"]
    pr = " (PROVISIONAL)"
    for y in (2019, 2020, 2021, 2022, 2023, 2024, 2025):
        reg.add(f"ec_t1_new_ha_{y}", T.loc[y], "ha", f"AMW new mining {y}, Napo + Orellana" + (pr if y == 2025 else ""), "description", SRC)
        reg.add(f"ec_pool_new_ha_{y}", P.loc[y], "ha", f"AMW new mining {y}, Zamora Ch. + Morona S. + Sucumbíos" + (pr if y == 2025 else ""),
                "description", SRC)
    r = wt.set_index("area")
    reg.add("ec_t1_pre_mean", r.iloc[0].pre_mean_2020_22, "ha/yr", "Napo + Orellana mean new mining 2020-22 (AMW)", "description", SRC)
    reg.add("ec_t1_post_mean", r.iloc[0].post_mean_2023_24, "ha/yr", "Napo + Orellana mean new mining 2023-24 (AMW)", "description", SRC)
    reg.add("ec_pool_pre_mean", r.loc["Pool: Zamora Ch. + Morona S. + Sucumbíos"].pre_mean_2020_22, "ha/yr", "Pool mean new mining 2020-22", "description", SRC)
    reg.add("ec_pool_post_mean", r.loc["Pool: Zamora Ch. + Morona S. + Sucumbíos"].post_mean_2023_24, "ha/yr", "Pool mean new mining 2023-24", "description", SRC)
    gg = gt.set_index("spec")
    reg.add("ec_gap_primary_lnpts", gg.iloc[0].gap_ln_points, "log points", "Napo+Orellana minus pool, ln(post 2023-24 / pre 2020-22)", "description", SRC)
    reg.add("ec_gap_prov_lnpts", gg.iloc[1].gap_ln_points, "log points", "Same, post 2023-25 (2025 provisional)", "description", SRC)
    reg.add("ec_placebo_2021_lnpts", gg.iloc[-1].gap_ln_points, "log points", "Placebo in time: fake start 2021", "description", SRC)
    reg.add("ec_gap_loo_min", gg.iloc[3:6].gap_ln_points.min(), "log points", "Smallest gap when one pool province is left out", "description", SRC)
    reg.add("ec_gap_loo_max", gg.iloc[3:6].gap_ln_points.max(), "log points", "Largest gap when one pool province is left out", "description", SRC)
    reg.add("ec_space_rank", rank, "rank", f"Rank of Napo+Orellana's ln change among {len(s) + 1} AMW areas with >=100 ha/yr in 2020-22 (1 = largest growth); areas overlap", "description", SRC)
    reg.add("ec_space_n", len(s) + 1, "count", "Areas in that ranking, incl. Napo+Orellana", "description", SRC)
    reg.add("ec_n_patches_clip", 0 if np.isnan(n_all) else n_all, "count", "AMW patches in the Ecuador clip file (box, incl. Colombia/Peru slivers)", "description", SRC)
    reg.add("ec_n_patches_moved_adm1_to_adm2", prov.attrs.get("n_moved", 0), "count", "Patches whose province changes when it is taken from the canton (ADM2) instead of ADM1 (border mismatch)", "description", SRC)
    reg.add("ec_n_patches_in_ecuador", n_in if not np.isnan(n_in) else 0, "count", "Of those, with centroid inside an Ecuador province", "description", SRC)
    top = c.index[0]
    reg.add("ec_top_canton_share_2023_24", c.iloc[0].share_of_post_2023_24, "share", f"Share of Napo+Orellana new mining 2023-24 in its largest canton ({top})", "description", SRC)
    reg.add("ec_ecuador_total_2024", ec["Ecuador total (Amazon basin patches)"].loc[2024], "ha", "AMW new mining 2024, all Ecuador", "description", SRC)
    reg.add("ec_ecuador_total_2020_22", ec["Ecuador total (Amazon basin patches)"].loc[list(PRE)].mean(), "ha/yr", "AMW new mining mean 2020-22, all Ecuador", "description", SRC)
    cr = cross.set_index("area")
    for key, area in (("tamb", "Tambopata buffer zone"), ("amar", "Amarakaeri buffer zone"), ("yan", "Yanomami"), ("mun", "Munduruku + Sai-Cinza")):
        reg.add(f"ec_x_{key}_change_pct", cr.loc[area].change_pct, "percent", f"Same windows (2020-22 -> 2023-24), AMW: {area}", "description", SRC)
    reg.add("ec_x_t1_change_pct", cr.loc["Napo + Orellana"].change_pct, "percent", "Same windows, AMW: Napo + Orellana", "description", SRC)
    reg.add("ec_x_pool_change_pct", cr.loc["Pool (Zamora, Morona, Sucumbíos)"].change_pct, "percent", "Same windows, AMW: Ecuador pool", "description", SRC)
    for key, area in (("t1", "Napo + Orellana"), ("pool", "Pool (Zamora, Morona, Sucumbíos)"), ("tamb", "Tambopata buffer zone"),
                      ("yan", "Yanomami"), ("bpool", "No-operation pool")):
        reg.add(f"ec_x_{key}_ratio_2025", cr.loc[area].ratio_2025_prov_to_2023_24, "ratio",
                f"AMW new mining 2025 (PROVISIONAL) / mean 2023-24: {area}", "description", SRC)
    reg.add("ec_did_ha", (r.iloc[0].post_mean_2023_24 - r.iloc[0].pre_mean_2020_22)
            - (r.loc["Pool: Zamora Ch. + Morona S. + Sucumbíos"].post_mean_2023_24 - r.loc["Pool: Zamora Ch. + Morona S. + Sucumbíos"].pre_mean_2020_22),
            "ha/yr", "Gap change (2x2): (Napo+Orellana post - pre) minus (pool post - pre), 2023-24 vs 2020-22, AMW", "description", SRC)
    reg.add("ec_gold_change_pct", gold, "percent", "Nominal gold price, mean 2023-24 vs mean 2020-22 (World Bank, course data)", "description", "data/prices_annual.csv")
    reg.add("ec_stock_2018_t1", ec.iloc[:, 0].loc[2018], "ha", "AMW mining stock (onset 2018) in Napo + Orellana", "description", SRC)
    reg.add("ec_stock_2018_pool", ec["Pool: Zamora Ch. + Morona S. + Sucumbíos"].loc[2018], "ha", "AMW mining stock (onset 2018) in the pool", "description", SRC)
    reg.add("ec_t1_pct_of_stock", st_mine, "percent", "Napo+Orellana mean new mining 2023-24 as % of its 2018 AMW stock, per year", "description", SRC)
    reg.add("ec_t1_stock_rank", st_rank, "rank", f"Rank of that share among {len(st_s) + 1} AMW areas with >=100 ha stock in 2018 (areas overlap)", "description", SRC)
    for key, area in (("tamb", "Tambopata buffer zone"), ("yan", "Yanomami"), ("mun", "Munduruku + Sai-Cinza"), ("pool", "Pool (Zamora, Morona, Sucumbíos)")):
        reg.add(f"ec_x_{key}_pct_of_stock", cr.loc[area].post_pct_of_2018_stock_per_year, "percent",
                f"Mean new mining 2023-24 as % of own 2018 AMW stock per year: {area}", "description", SRC)
    sub = pd.DataFrame(reg.rows.values()); sub = sub[sub.id.str.startswith("ec_")]
    sub.to_csv(OUT / "numbers_ecuador.csv", index=False)
    return dict(ec=ec, wt=wt, gt=gt, cross=cross, cantons=c, rank=rank)


if __name__ == "__main__":
    r = Numbers(); run(r)
