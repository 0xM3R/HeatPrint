import numpy as np
import pandas as pd
import pytest

from heatprint import advice


def test_lmtd_rating_point():
    assert advice.lmtd(75, 65, 20) == pytest.approx(49.83, abs=0.01)


def test_radiator_nominal_output():
    assert advice.radiator_output_w(5000, 75, 20) == pytest.approx(5000, rel=1e-3)


def test_min_flow_temp_meets_load():
    phi = 8000.0
    load = 5000.0
    tf = advice.min_flow_temp(load, phi)
    assert advice.radiator_output_w(phi, tf, 20) == pytest.approx(load, rel=1e-3)
    assert advice.min_flow_temp(6000.0, phi) > tf        # more load needs hotter water


def test_min_flow_temp_insufficient_radiators():
    assert np.isnan(advice.min_flow_temp(50_000, 2000))


def test_design_load():
    assert advice.design_load_w(200) == pytest.approx(200 * 30)


def test_phi_nom_round_trip():
    phi = advice.phi_nom_from_design(6000, 80, 60)
    dt = advice.lmtd(80, 60, 20)
    assert phi * (dt / 49.83) ** 1.3 == pytest.approx(6000, rel=1e-6)


def test_fixed_flow_limits_ordering():
    te = pd.Series(np.linspace(-10, 20, 1000), index=pd.date_range("2024-01-01", periods=1000, freq="h"))
    lim = advice.fixed_flow_limits(200, 8000, te)
    assert lim[0]["te_min"] < lim[1]["te_min"] < lim[2]["te_min"]    # 60 < 55 < 50 degC
    assert lim[0]["hours_share"] >= lim[2]["hours_share"]


def test_hybrid_coverage_monotonic():
    q = pd.Series(np.abs(np.sin(np.arange(24 * 365) / 500.0)) * 6,
                  index=pd.date_range("2023-01-01", periods=24 * 365, freq="h"))
    cov = advice.hybrid_coverage(q)["coverage"].values
    assert np.all(np.diff(cov) >= 0) and cov[-1] <= 1.0


def test_nefit_rule():
    assert advice.nefit_rule_kw(1650) == pytest.approx(8.0)
