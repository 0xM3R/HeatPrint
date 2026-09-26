"""Validation against co-heating HTCs of the 30 SMETER Phase 2 dwellings.

Protocol
--------
* Homes with odd ID numbers form the development set, even IDs the test set.
* Estimator variants are compared on the development set only. Selection rule:
  lowest development MAPE among variants that give a gated estimate for at
  least 80% of development homes. The test set is not fully blind: test-home
  errors were visible during method development (stated in the report).
* Test-set metrics are reported for the selected variant and for the RdSAP
  (survey-based calculation) HTC on the same homes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data, htc

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "processed" / "smeter_daily.csv"
MIN_DEV_COVERAGE = 0.8


def split_of(hid: str) -> str:
    return "dev" if int(hid[2:]) % 2 == 1 else "test"


def load_daily_all() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    info = data.load_dwelling_info()
    if CACHE.exists():
        allx = pd.read_csv(CACHE, index_col=0, parse_dates=True)
        return info, {h: g.drop(columns="hid") for h, g in allx.groupby("hid")}
    days = {}
    for _, r in info.iterrows():
        df = data.load_smeter_home(r.hid)
        if pd.notna(r.occupied_from):
            df = df[df.index >= r.occupied_from]
        if pd.notna(r.withdrawn):
            df = df[df.index < r.withdrawn]
        change = r.eff_change_date if pd.notna(r.eff_change_date) else None
        eff = htc.efficiency_series(df.index, r.eff_winter, r.eff_winter_after, change)
        days[r.hid] = htc.daily(df, eff)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([d.assign(hid=h) for h, d in days.items()]).to_csv(CACHE)
    return info, days


# ------------------------------------------------------------ variants -------
def _ols_generic(points: pd.DataFrame, cols: list[str]) -> tuple[float, float]:
    X = np.column_stack([points[c].values for c in cols] + [np.ones(len(points))])
    y = points["q_tot_w"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    ss = ((y - y.mean()) ** 2).sum()
    return float(beta[0]), float(1 - res @ res / ss) if ss > 0 else float("nan")


def _huber(points: pd.DataFrame, cols: list[str], k: float = 1.345) -> tuple[float, float]:
    X = np.column_stack([points[c].values for c in cols] + [np.ones(len(points))])
    y = points["q_tot_w"].values
    wts = np.ones(len(y))
    beta = np.zeros(X.shape[1])
    for _ in range(50):
        sw = np.sqrt(wts)
        beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        r = y - X @ beta
        s = np.median(np.abs(r - np.median(r))) / 0.6745 + 1e-9
        u = np.abs(r) / (k * s)
        wts = np.where(u <= 1, 1.0, 1.0 / u)
    res = y - X @ beta
    ss = ((y - y.mean()) ** 2).sum()
    return float(beta[0]), float(1 - res @ res / ss) if ss > 0 else float("nan")


def _cold(d, te_max):
    return d[(d["te"] <= te_max) & (d["dt"] >= htc.HEATING_DT_MIN) & (d["gas_kwh"] > 0)]


def _weekly_all(d):
    g = d.resample("W")
    n = g["dt"].count()
    w = g[["q_tot_w", "dt", "solar", "te"]].mean()[n >= htc.MIN_DAYS_PER_WEEK].dropna()
    return w[(w["te"] <= htc.HEATING_TE_MAX) & (w["dt"] >= htc.HEATING_DT_MIN)]


BASE_VARIANTS = {
    "daily": lambda d: _ols_generic(htc.heating_days(d), ["dt", "solar"]),
    "daily_huber": lambda d: _huber(htc.heating_days(d), ["dt", "solar"]),
    "daily_te10": lambda d: _ols_generic(_cold(d, 10.0), ["dt", "solar"]),
    "daily_nosolar": lambda d: _ols_generic(htc.heating_days(d), ["dt"]),
    "weekly": lambda d: _ols_generic(htc.weekly(htc.heating_days(d)), ["dt", "solar"]),
    "weekly_allweeks": lambda d: _ols_generic(_weekly_all(d), ["dt", "solar"]),
}
GATES = (0.0, 0.3, 0.5)


def _errors(est: dict[str, tuple[float, float]], ref: pd.Series, ids, gate) -> np.ndarray:
    e = []
    for h in ids:
        v, r2 = est[h]
        if np.isfinite(v) and v > 0 and np.isfinite(r2) and r2 >= gate:
            e.append((v - ref[h]) / ref[h] * 100.0)
    return np.array(e)


def summarise(err_pct: np.ndarray, est: np.ndarray | None = None,
              ref: np.ndarray | None = None) -> dict:
    out = {
        "n": int(len(err_pct)),
        "mape": float(np.mean(np.abs(err_pct))) if len(err_pct) else float("nan"),
        "median_ape": float(np.median(np.abs(err_pct))) if len(err_pct) else float("nan"),
        "bias_pct": float(np.mean(err_pct)) if len(err_pct) else float("nan"),
        "within_10": float(np.mean(np.abs(err_pct) <= 10)) if len(err_pct) else float("nan"),
        "within_20": float(np.mean(np.abs(err_pct) <= 20)) if len(err_pct) else float("nan"),
    }
    if est is not None and ref is not None and len(est) > 1:
        diff = est - ref
        out["mae_wk"] = float(np.mean(np.abs(diff)))
        out["bias_wk"] = float(np.mean(diff))
        out["loa_lo_wk"] = float(np.mean(diff) - 1.96 * np.std(diff, ddof=1))
        out["loa_hi_wk"] = float(np.mean(diff) + 1.96 * np.std(diff, ddof=1))
        out["pearson_r"] = float(np.corrcoef(est, ref)[0, 1])
    return out


def run() -> tuple[pd.DataFrame, dict]:
    info, days = load_daily_all()
    info = info.set_index("hid")
    ref = info["htc_coheat"]
    dev = [h for h in info.index if split_of(h) == "dev"]
    test = [h for h in info.index if split_of(h) == "test"]

    # 1. variant grid on development homes
    grid = []
    for name, fn in BASE_VARIANTS.items():
        est = {}
        for h, d in days.items():
            try:
                est[h] = fn(d)
            except (ValueError, np.linalg.LinAlgError, ZeroDivisionError):
                est[h] = (float("nan"), float("nan"))
        for gate in GATES:
            e = _errors(est, ref, dev, gate)
            grid.append({"variant": name, "gate_r2": gate,
                         "dev_coverage": len(e) / len(dev), **summarise(e)})
    grid = pd.DataFrame(grid)
    eligible = grid[grid["dev_coverage"] >= MIN_DEV_COVERAGE]
    best = eligible.sort_values("mape").iloc[0]
    selected = f"{best['variant']}@{best['gate_r2']}"
    matches_package = (best["variant"] == "weekly" and best["gate_r2"] == htc.R2_GATE)

    # 2. per-home results with the package estimator
    rows = []
    for h in info.index:
        d = days[h]
        f = htc.fit_weekly(d)
        lo, hi = htc.bootstrap_ci(d) if f is not None else (np.nan, np.nan)
        rows.append({
            "hid": h, "split": split_of(h),
            "htc_coheat": ref[h],
            "coheat_lo": info.loc[h, "htc_coheat_lo"], "coheat_hi": info.loc[h, "htc_coheat_hi"],
            "htc_rdsap": info.loc[h, "htc_rdsap"],
            "htc_heatprint": f.htc if f else np.nan,
            "r2": f.r2 if f else np.nan,
            "n_weeks": f.n_points if f else 0,
            "passed": bool(f.passed) if f else False,
            "boot_lo": lo, "boot_hi": hi,
            "floor_area": info.loc[h, "floor_area"],
            "dwelling_type": info.loc[h, "dwelling_type"],
        })
    res = pd.DataFrame(rows)
    res["err_heatprint_pct"] = (res["htc_heatprint"] - res["htc_coheat"]) / res["htc_coheat"] * 100
    res["err_rdsap_pct"] = (res["htc_rdsap"] - res["htc_coheat"]) / res["htc_coheat"] * 100
    res["in_coheat_ci"] = (res["htc_heatprint"] >= res["coheat_lo"]) & (res["htc_heatprint"] <= res["coheat_hi"])

    def block(sub):
        ok = sub[sub["passed"]]
        hp = summarise(ok["err_heatprint_pct"].values, ok["htc_heatprint"].values, ok["htc_coheat"].values)
        rd_same = summarise(ok["err_rdsap_pct"].values, ok["htc_rdsap"].values, ok["htc_coheat"].values)
        rd_all = summarise(sub["err_rdsap_pct"].values, sub["htc_rdsap"].values, sub["htc_coheat"].values)
        return {"homes": int(len(sub)), "gated": int(len(ok)),
                "coverage": len(ok) / len(sub),
                "in_coheat_ci": float(ok["in_coheat_ci"].mean()) if len(ok) else float("nan"),
                "heatprint": hp, "rdsap_same_homes": rd_same, "rdsap_all_homes": rd_all}

    # 3. data-length curve (all homes, gated windows)
    curve = []
    for weeks in (4, 6, 8, 10, 12, 16):
        errs, tried, passed = [], 0, 0
        for h in info.index:
            wts = htc.weekly(htc.heating_days(days[h]))
            if len(wts) < weeks:
                continue
            est = htc.window_estimates(days[h], weeks, n_windows=20, seed=int(h[2:]))
            n_starts = min(20, len(wts) - weeks + 1)
            tried += n_starts
            passed += len(est)
            errs += [abs(v - ref[h]) / ref[h] * 100 for v in est]
        curve.append({"weeks": weeks, "windows": tried, "gated_share": passed / tried if tried else np.nan,
                      "median_ape": float(np.median(errs)) if errs else np.nan,
                      "p75_ape": float(np.percentile(errs, 75)) if errs else np.nan})
    curve = pd.DataFrame(curve)

    metrics = {
        "protocol": {"dev_ids": dev, "test_ids": test, "selection_rule":
                     "lowest development MAPE among variants covering >= 80% of development homes",
                     "selected": selected, "selected_matches_package": bool(matches_package)},
        "test": block(res[res["split"] == "test"]),
        "dev": block(res[res["split"] == "dev"]),
        "all": block(res),
        "rdsap_vs_coheat_all30": summarise(res["err_rdsap_pct"].values, res["htc_rdsap"].values,
                                           res["htc_coheat"].values),
        "rdsap_overestimates_share": float((res["htc_rdsap"] > res["htc_coheat"]).mean()),
        "coheat_htc_range": [float(ref.min()), float(ref.max())],
        "data_length_curve": curve.to_dict(orient="records"),
    }
    return res, {"metrics": metrics, "grid": grid}
