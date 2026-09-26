"""Static figures for the validation results and the HTML home report."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reference palette (dataviz skill), light mode; validated with validate_palette.js
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#c9c8c3"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
BLUE_LIGHT = "#86b6ef"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#ecebe7", "grid.linewidth": 0.8, "lines.linewidth": 2,
    "font.family": "DejaVu Sans",
})


def pct(v: float) -> str:
    """Percent label that never rounds a value below 100% up to '100%'."""
    return f"{v * 100:.0f}%" if v * 100 < 99.5 or v >= 1.0 else f"{v * 100:.1f}%"


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def validation_scatter(res: pd.DataFrame, path: Path) -> Path:
    t = res[(res["split"] == "test") & res["passed"]]
    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    lim = (90, 320)
    x = np.linspace(*lim, 50)
    ax.fill_between(x, 0.8 * x, 1.2 * x, color="#f0efec", zorder=0, label="±20% band")
    ax.plot(x, x, color=INK2, lw=1, ls="--", zorder=1)
    ax.text(300, 306, "1:1", color=INK2, fontsize=10)
    ax.scatter(t["htc_coheat"], t["htc_rdsap"], s=70, marker="s", color=ORANGE,
               edgecolor=SURFACE, linewidth=2, zorder=3, label="RdSAP survey calculation")
    ax.scatter(t["htc_coheat"], t["htc_heatprint"], s=80, marker="o", color=BLUE,
               edgecolor=SURFACE, linewidth=2, zorder=4, label="HeatPrint (smart-meter data)")
    placed = []
    for _, r in t.sort_values("htc_coheat").iterrows():
        x0, y0 = r["htc_coheat"], r["htc_heatprint"]
        crowded = any(abs(x0 - x1) < 8 and abs(y0 - y1) < 8 for x1, y1 in placed)
        ax.annotate(r["hid"], (x0, y0), xytext=(-38, 6) if crowded else (6, -12),
                    textcoords="offset points", fontsize=8, color=INK2)
        placed.append((x0, y0))
    ax.set_xlim(*lim)
    ax.set_ylim(*lim)
    ax.set_xlabel("Measured HTC, co-heating test (W/K)")
    ax.set_ylabel("Estimated HTC (W/K)")
    ax.set_title(f"Held-out test homes (n = {len(t)})")
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    return _save(fig, path)


def bland_altman(res: pd.DataFrame, m: dict, path: Path) -> Path:
    ok = res[res["passed"]]
    mean = (ok["htc_heatprint"] + ok["htc_coheat"]) / 2
    diff = ok["htc_heatprint"] - ok["htc_coheat"]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.scatter(mean, diff, s=60, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    for y, lab in ((m["bias_wk"], "bias"), (m["loa_lo_wk"], "−1.96 SD"), (m["loa_hi_wk"], "+1.96 SD")):
        ax.axhline(y, color=INK2, lw=1, ls="--" if lab != "bias" else "-")
        ax.text(mean.max() + 5, y + 1.5, f"{lab}: {y:.0f} W/K", va="bottom", fontsize=9, color=INK2)
    ax.set_xlim(right=mean.max() + 45)
    ax.set_xlabel("Mean of HeatPrint and co-heating HTC (W/K)")
    ax.set_ylabel("HeatPrint − co-heating (W/K)")
    ax.set_title(f"Agreement, all gated homes (n = {len(ok)})")
    return _save(fig, path)


def signature(d_weekly: pd.DataFrame, fit, hid: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.scatter(d_weekly["dt"], d_weekly["q_tot_w"] / 1000, s=60, color=BLUE,
               edgecolor=SURFACE, linewidth=2, zorder=3, label="one heating week")
    xs = np.linspace(d_weekly["dt"].min() - 1, d_weekly["dt"].max() + 1, 20)
    ys = (fit.htc * xs + fit.solar_coef * d_weekly["solar"].mean() + fit.intercept) / 1000
    ax.plot(xs, ys, color=INK, lw=2, zorder=2)
    ax.text(xs[-1], ys[-1], f"  slope = HTC ≈ {fit.htc:.0f} W/K", va="center", fontsize=11)
    ax.set_xlabel("Indoor − outdoor temperature, weekly mean (K)")
    ax.set_ylabel("Heat input: gas × efficiency + electricity (kW)")
    ax.set_title(f"Energy signature, dwelling {hid}")
    ax.set_xlim(right=xs[-1] + 6)
    return _save(fig, path)


def data_length(curve: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(curve["weeks"], curve["median_ape"], color=BLUE, marker="o", ms=8, zorder=3)
    ax.plot(curve["weeks"], curve["p75_ape"], color=BLUE_LIGHT, marker="o", ms=8, ls="--", zorder=2)
    last = curve.iloc[-1]
    ax.text(last["weeks"] + 0.4, last["median_ape"], "median error", va="center", color=INK, fontsize=10)
    ax.text(last["weeks"] + 0.4, last["p75_ape"], "75th percentile", va="center", color=INK2, fontsize=10)
    ax.set_xlim(3, 21)
    ax.set_ylim(0, max(curve["p75_ape"].max() * 1.1, 10))
    ax.set_xlabel("Heating weeks of data used")
    ax.set_ylabel("Absolute error vs co-heating (%)")
    ax.set_title("How much data does the estimate need?")
    return _save(fig, path)


def heating_curve_fig(curve: pd.DataFrame, flow_design: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.axhspan(0, 65, color="#e7f0fb", zorder=0)
    ax.text(14.8, 63, "condensing zone (return < 55 °C)", ha="right", va="top", fontsize=9, color=INK2)
    ax.axhline(80, color=INK2, lw=1, ls="--")
    ax.text(14.8, 81, "typical factory setting 80 °C", ha="right", fontsize=9, color=INK2)
    ax.plot(curve["te"], curve["t_flow"], color=BLUE, zorder=3)
    ax.scatter([-10], [flow_design], s=70, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=4)
    ax.annotate(f"design day −10 °C → {flow_design:.1f} °C", (-10, flow_design), xytext=(8, 8),
                textcoords="offset points", fontsize=10)
    ax.set_ylim(20, 90)
    ax.set_xlim(-11, 15.5)
    ax.set_xlabel("Outdoor temperature (°C)")
    ax.set_ylabel("Required boiler flow temperature (°C)")
    ax.set_title("Recommended heating curve, demo home")
    return _save(fig, path)


def hybrid_fig(cov: pd.DataFrame, design_kw: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    labels = [f"{s:g} kW" for s in cov["size_kw"]]
    bars = ax.bar(labels, cov["coverage"] * 100, color=BLUE, width=0.6, zorder=3)
    for b, v in zip(bars, cov["coverage"]):
        ax.text(b.get_x() + b.get_width() / 2, v * 100 + 1.5, pct(v), ha="center", fontsize=10)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Share of annual space heat (%)")
    ax.set_title(f"Heat-pump size vs share of heat covered (design load {design_kw:.1f} kW)")
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def co2_fig(items: list[tuple[str, float]], path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    names = [n for n, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    colors = [MUTED if i == len(vals) - 1 else BLUE for i in range(len(vals))]
    bars = ax.barh(names, vals, color=colors, height=0.55, zorder=3)
    for b, v in zip(bars, vals):
        ax.text(v + max(vals) * 0.01, b.get_y() + b.get_height() / 2, f"{v:,.0f} kg",
                va="center", fontsize=10)
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("Space-heating CO₂ per year (kg CO₂-eq)")
    ax.set_title("Demo home: annual CO₂ by option")
    ax.grid(axis="y", visible=False)
    return _save(fig, path)


def jevons_fig(items: list[tuple[str, float, str]], path: Path) -> Path:
    """Log-scale comparison of footprint vs savings (kg CO2 per home per year)."""
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    names = [n for n, _, _ in items][::-1]
    vals = [v for _, v, _ in items][::-1]
    kinds = [k for _, _, k in items][::-1]
    colors = [ORANGE if k == "cost" else BLUE for k in kinds]
    bars = ax.barh(names, vals, color=colors, height=0.55, zorder=3)
    ax.set_xscale("log")
    for b, v in zip(bars, vals):
        label = f"{v * 1000:.3f} g" if v < 0.1 else f"{v:,.1f} kg" if v < 10 else f"{v:,.0f} kg"
        ax.text(v * 1.4, b.get_y() + b.get_height() / 2, label, va="center", fontsize=10)
    ax.set_xlim(min(vals) / 3, max(vals) * 30)
    ax.set_xlabel("kg CO₂ per home per year (log scale)")
    ax.set_title("Footprint (orange) vs savings (blue)")
    ax.grid(axis="y", visible=False)
    return _save(fig, path)
