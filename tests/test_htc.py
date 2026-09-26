import numpy as np
import pandas as pd
import pytest

from heatprint import htc


def _synthetic_daily(true_htc=180.0, weeks=20, noise_w=40.0, seed=1):
    """Hourly series whose daily energy balance follows the signature model."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-11-01", periods=weeks * 7 * 24, freq="h")
    days = len(idx) // 24
    te_day = 6 + 5 * np.sin(np.linspace(0, 3 * np.pi, days)) + rng.normal(0, 2, days)
    sol_day = np.clip(40 + 25 * rng.standard_normal(days), 0, None)
    ti_day = np.full(days, 20.0)
    elec_w = 300.0
    q_heat = true_htc * (ti_day - te_day) - 2.0 * sol_day - 150.0 - elec_w + rng.normal(0, noise_w, days)
    eff = 0.9
    gas_kwh_day = np.clip(q_heat, 0, None) / eff * 24 / 1000
    rep = lambda a: np.repeat(a, 24)  # noqa: E731
    return pd.DataFrame({
        "gas_kwh": rep(gas_kwh_day / 24), "elec_kwh": elec_w / 1000.0,
        "ti": rep(ti_day), "te": rep(te_day), "solar": rep(sol_day),
    }, index=idx), eff


def test_weekly_fit_recovers_known_htc():
    df, eff = _synthetic_daily()
    d = htc.daily(df, eff)
    f = htc.fit_weekly(d)
    assert f is not None and f.passed
    assert f.htc == pytest.approx(180.0, rel=0.05)
    lo, hi = htc.bootstrap_ci(d, n=300)
    assert lo < 180.0 < hi


def test_quality_gate_rejects_unrelated_gas():
    df, eff = _synthetic_daily(seed=3)
    rng = np.random.default_rng(7)
    days = len(df) // 24
    df["gas_kwh"] = np.repeat(rng.uniform(1.0, 3.0, days), 24)   # gas independent of weather
    f = htc.fit_weekly(htc.daily(df, eff))
    assert f is not None and not f.passed


def test_daily_requires_coverage():
    df, eff = _synthetic_daily(weeks=3)
    df.iloc[:20, df.columns.get_loc("gas_kwh")] = np.nan   # first day loses 20 of 24 hours
    d = htc.daily(df, eff)
    assert df.index[0].normalize() not in d.index


def test_efficiency_series_switch():
    idx = pd.date_range("2020-11-01", periods=10, freq="D")
    s = htc.efficiency_series(idx, 0.898, 0.867, pd.Timestamp("2020-11-06"))
    assert s.iloc[0] == 0.898 and s.iloc[-1] == 0.867
