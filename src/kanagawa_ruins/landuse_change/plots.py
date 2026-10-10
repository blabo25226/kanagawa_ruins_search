"""Static figures (matplotlib, PNG). Palette: reference dataviz palette (blue sequential,
blue<->red diverging with a gray midpoint). Region identity is shown by outlines and
direct labels, not by fill colour."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
import numpy as np  # noqa: E402

from .codes import GROUP_LABELS  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e4e3df"
NODATA = "#d9d8d4"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SEQ = ["#f0efec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV = ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f3b0ae", "#e66767", "#b02b2a"]
SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ)
DIV_CMAP = LinearSegmentedColormap.from_list("div_blue_red", DIV)


def setup_fonts():
    for name in ["Noto Sans CJK JP", "Noto Serif CJK JP", "IPAexGothic", "TakaoGothic"]:
        if any(name == f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT2,
            "xtick.color": TEXT2,
            "ytick.color": TEXT2,
            "text.color": TEXT,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "font.size": 9,
            "savefig.dpi": 150,
        }
    )


def _short(g):
    return GROUP_LABELS.get(g, g).split("（")[0]


def heatmap(matrix, path, title, note):
    m = matrix.copy()
    labels = [_short(g) for g in m.index]
    vals = m.to_numpy(float)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw=dict(wspace=0.35))
    row = vals / np.where(vals.sum(axis=1, keepdims=True) > 0, vals.sum(axis=1, keepdims=True), np.nan)
    off = row.copy()
    np.fill_diagonal(off, np.nan)
    for ax, data, sub, fmt in [
        (axes[0], np.log10(np.where(vals > 0, vals, np.nan)), "面積 (km², 色はlog10)", lambda v, i, j: f"{vals[i, j]:.2f}" if vals[i, j] >= 0.005 else ""),
        (axes[1], off * 100, "行（2014年分類）に対する転換割合 % （対角＝存続は除外）", lambda v, i, j: f"{off[i, j] * 100:.1f}" if np.isfinite(off[i, j]) and off[i, j] >= 0.001 else ""),
    ]:
        im = ax.imshow(data, cmap=SEQ_CMAP, aspect="auto")
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        ax.set_yticks(range(len(labels)), labels)
        ax.set_xlabel("2021年")
        ax.set_ylabel("2014年")
        ax.set_title(sub, fontsize=9, color=TEXT2, loc="left")
        finite = data[np.isfinite(data)]
        mid = np.nanmedian(finite) if finite.size else 0
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                s = fmt(data[i, j], i, j)
                if s:
                    ax.text(j, i, s, ha="center", va="center", fontsize=6.5, color="white" if np.isfinite(data[i, j]) and data[i, j] > mid + (np.nanmax(finite) - mid) * 0.35 else TEXT)
        for side in ax.spines.values():
            side.set_visible(False)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle(title, x=0.01, ha="left", fontsize=11)
    fig.text(0.01, -0.1, note, fontsize=7, color=TEXT2)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def mesh_map(mesh_gdf, column, path, title, note, outline=None, labels=None, diverging=False, vmax=None, coverage_outline=None, uncovered=None):
    fig, ax = plt.subplots(figsize=(9, 7.2))
    if uncovered is not None:
        uncovered.plot(ax=ax, color=NODATA, edgecolor="none")
    data = mesh_gdf[mesh_gdf[column].notna()]
    nod = mesh_gdf[mesh_gdf[column].isna()]
    if len(nod):
        nod.plot(ax=ax, color="#efeeea", edgecolor="none")
    if diverging:
        v = vmax or float(np.nanquantile(np.abs(data[column]), 0.98)) or 1.0
        data.plot(ax=ax, column=column, cmap=DIV_CMAP, norm=TwoSlopeNorm(0, -v, v), legend=True, legend_kwds=dict(shrink=0.6), edgecolor="none")
    else:
        v = vmax or float(np.nanquantile(data[column], 0.98)) or 1.0
        data.plot(ax=ax, column=column, cmap=SEQ_CMAP, vmin=0, vmax=v, legend=True, legend_kwds=dict(shrink=0.6), edgecolor="none")
    if outline is not None:
        outline.boundary.plot(ax=ax, color=TEXT2, linewidth=0.6)
    if coverage_outline is not None:
        coverage_outline.boundary.plot(ax=ax, color="#b02b2a", linewidth=0.8, linestyle="--")
    if labels is not None:
        for _, r in labels.iterrows():
            ax.annotate(r["label"], (r.geometry.x, r.geometry.y), fontsize=8, ha="center", color=TEXT, bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none", alpha=0.8))
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=11)
    fig.text(0.01, 0.01, note, fontsize=7, color=TEXT2)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
FOLDED = [
    ("農地", ["agri"]),
    ("森林", ["forest"]),
    ("荒地", ["wasteland"]),
    ("建物用地", ["building"]),
    ("交通・その他・ゴルフ場", ["transport", "other", "golf"]),
    ("水域・海浜", ["water", "beach"]),
]


def region_composition(region_agg, labels, path, note):
    """Stacked 100% bars; six folded classes in the validated categorical slot order."""
    regs = list(region_agg.index)
    fig, ax = plt.subplots(figsize=(10, 0.5 * len(regs) * 2 + 1.8))
    ypos, ylab = [], []
    y = 0
    for r in regs:
        for yr in ("2014", "2021"):
            left = 0
            for (name, gs), color in zip(FOLDED, CATEGORICAL):
                w = sum(region_agg.loc[r, f"{g}_{yr}_share"] for g in gs)
                ax.barh(y, w, left=left, color=color, edgecolor=SURFACE, linewidth=2, height=0.8, label=name if (r == regs[0] and yr == "2014") else None)
                left += w
            ypos.append(y)
            ylab.append(f"{labels.get(r, r)} {yr}")
            y += 1
        y += 0.5
    ax.set_yticks(ypos, ylab)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("陸域面積に対する構成比")
    ax.legend(ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
    ax.set_title("地域別の土地利用構成（2014年・2021年、収録範囲内の陸域）", loc="left", fontsize=11)
    fig.text(0.01, -0.03, note, fontsize=7, color=TEXT2)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def distance_rates(table, rate, order, path, title, note, strata_labels, min_denom_km2=0.5):
    """Point + interval per distance bin; bins whose base-class area is below min_denom_km2 are omitted."""
    t = table[(table.rate == rate) & (table.denom_km2 >= min_denom_km2)]
    strata = [s for s in strata_labels if s in set(t.stratum)]
    fig, axes = plt.subplots(1, len(strata), figsize=(2.9 * len(strata), 3.3), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, s in zip(axes, strata):
        g = t[t.stratum == s].set_index("dist_bin").reindex([o for o in order if o in set(t[t.stratum == s].dist_bin)])
        x = np.arange(len(g))
        ax.vlines(x, g.ci_low * 100, g.ci_high * 100, color=SERIES[0], linewidth=2)
        ax.plot(x, g.estimate * 100, "o", color=SERIES[0], markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.set_xticks(x, g.index, rotation=45, ha="right", fontsize=7)
        ax.set_xlim(-0.5, len(order) - 0.5)
        ax.set_title(strata_labels[s], fontsize=8, loc="left")
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("%")
    axes[0].set_ylim(bottom=0)
    fig.suptitle(title, x=0.01, ha="left", fontsize=10, y=1.04)
    fig.text(0.01, -0.12, note + f" 点＝推定値、縦線＝空間ブロック・ブートストラップ95%区間。基準面積{min_denom_km2} km²未満の距離帯は省略。", fontsize=7, color=TEXT2)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
