"""Heat transfer coefficient (HTC, W/K) estimation from in-use data.

Selected estimator (chosen on the development homes only, see validate.py):
weekly energy-signature regression over heating days,

    eta*Q_gas + Q_elec = HTC*(Ti - Te) + g*I_sol + c

with weekly means of daily values. The slope is the HTC. The intercept c absorbs
roughly constant terms (hot-water gas use, metabolic gains); g captures solar
gains. A fit is reported only when it passes the quality gate (R2 >= 0.5,
HTC > 0); otherwise the home is flagged "insufficient data".
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

MIN_COVERAGE = 0.9        # share of samples per day that must be present
HEATING_TE_MAX = 12.0     # degC, daily mean outdoor temperature
HEATING_DT_MIN = 5.0      # K, daily mean indoor-outdoor difference
MIN_DAYS_PER_WEEK = 5
MIN_WEEKS = 4
R2_GATE = 0.5


@dataclass
class Fit:
    htc: float
    solar_coef: float
    intercept: float
    r2: float
    n_points: int
    htc_se: float
    level: str            # "weekly" or "daily"

    @property
    def passed(self) -> bool:
        return self.htc > 0 and self.r2 >= R2_GATE

    def as_dict(self):
        d = asdict(self)
        d["passed"] = self.passed
        return d


def efficiency_series(index: pd.DatetimeIndex, eff: float,
                      eff_after: float | None = None,
                      change_date: pd.Timestamp | None = None) -> pd.Series:
    s = pd.Series(eff, index=index, dtype=float)
    if eff_after is not None and not pd.isna(eff_after) and change_date is not None:
        s[index >= change_date] = eff_after
    return s


def daily(df: pd.DataFrame, eff: float | pd.Series) -> pd.DataFrame:
    """Aggregate a sub-daily series (gas_kwh, elec_kwh, ti, te, solar) to days."""
    step = df.index.to_series().diff().median()
    per_day = int(round(pd.Timedelta("1D") / step))
    need = int(np.ceil(MIN_COVERAGE * per_day))
    g = df.resample("D")
    counts = g.count()
    d = pd.DataFrame({
        "gas_kwh": g["gas_kwh"].sum(min_count=need),
        "elec_kwh": g["elec_kwh"].sum(min_count=need),
        "ti": g["ti"].mean(),
        "te": g["te"].mean(),
        "solar": g["solar"].mean(),
    })
    ok = (counts[["gas_kwh", "elec_kwh", "ti", "te"]] >= need).all(axis=1)
    d = d[ok].copy()
    d["solar"] = d["solar"].fillna(0.0)
    if isinstance(eff, pd.Series):
        e = eff.resample("D").mean().reindex(d.index).ffill().bfill()
    else:
        e = pd.Series(eff, index=d.index)
    d["eff"] = e
    d["q_gas_w"] = d["gas_kwh"] * 1000.0 / 24.0
    d["q_heat_w"] = d["eff"] * d["q_gas_w"]
    d["q_elec_w"] = d["elec_kwh"] * 1000.0 / 24.0
    d["q_tot_w"] = d["q_heat_w"] + d["q_elec_w"]
    d["dt"] = d["ti"] - d["te"]
    return d.dropna(subset=["q_tot_w", "dt"])


def heating_days(d: pd.DataFrame) -> pd.DataFrame:
    m = (d["te"] <= HEATING_TE_MAX) & (d["dt"] >= HEATING_DT_MIN) & (d["gas_kwh"] > 0)
    return d[m]


def weekly(h: pd.DataFrame) -> pd.DataFrame:
    """Weekly means of heating days; weeks with fewer than 5 heating days dropped."""
    g = h.resample("W")
    n = g["dt"].count()
    w = g[["q_tot_w", "q_heat_w", "q_elec_w", "dt", "solar", "te", "ti"]].mean()
    return w[n >= MIN_DAYS_PER_WEEK].dropna()


def _ols(points: pd.DataFrame, level: str) -> Fit | None:
    if len(points) < (MIN_WEEKS if level == "weekly" else 14):
        return None
    X = np.column_stack([points["dt"].values, points["solar"].values,
                         np.ones(len(points))])
    y = points["q_tot_w"].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(len(points) - X.shape[1], 1)
    cov = (resid @ resid / dof) * np.linalg.pinv(X.T @ X)
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot if ss_tot > 0 else float("nan")
    return Fit(float(beta[0]), float(beta[1]), float(beta[2]), float(r2),
               int(len(points)), float(np.sqrt(max(cov[0, 0], 0.0))), level)


def fit_weekly(d: pd.DataFrame) -> Fit | None:
    """Primary estimator: weekly energy signature of heating days."""
    return _ols(weekly(heating_days(d)), "weekly")


def fit_daily(d: pd.DataFrame) -> Fit | None:
    """Daily energy signature (used only in the method comparison)."""
    return _ols(heating_days(d), "daily")


def bootstrap_ci(d: pd.DataFrame, n: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% interval for the weekly HTC by resampling weeks."""
    w = weekly(heating_days(d))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        f = _ols(w.iloc[rng.integers(0, len(w), len(w))], "weekly")
        if f is not None and np.isfinite(f.htc):
            vals.append(f.htc)
    if len(vals) < n // 2:
        return float("nan"), float("nan")
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def window_estimates(d: pd.DataFrame, weeks: int, n_windows: int = 20,
                     seed: int = 0) -> list[float]:
    """Weekly-method HTC from random contiguous windows of `weeks` heating weeks.

    Only windows whose fit passes the quality gate are returned.
    """
    w = weekly(heating_days(d))
    if len(w) < weeks:
        return []
    rng = np.random.default_rng(seed)
    starts = np.arange(0, len(w) - weeks + 1)
    picks = rng.choice(starts, size=min(n_windows, len(starts)), replace=False)
    out = []
    for s in sorted(picks):
        f = _ols(w.iloc[s:s + weeks], "weekly")
        if f is not None and f.passed:
            out.append(f.htc)
    return out
