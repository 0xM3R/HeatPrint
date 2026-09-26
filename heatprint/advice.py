"""Advice engine: design heat load, minimum boiler flow temperature (EN 442
radiator model), heat-pump size and hybrid coverage from hourly weather."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import constants as C


def design_load_w(htc: float, ti: float = C.DESIGN_TI.value,
                  te: float = C.DESIGN_TE.value) -> float:
    return htc * (ti - te)


def lmtd(t_flow: float, t_return: float, t_room: float) -> float:
    a, b = t_flow - t_room, t_return - t_room
    if a <= 0 or b <= 0:
        return 0.0
    if abs(a - b) < 1e-9:
        return a
    return (a - b) / np.log(a / b)


def radiator_output_w(phi_nom_w: float, t_flow: float, t_room: float,
                      split: float = C.FLOW_RETURN_SPLIT.value,
                      n: float = C.RADIATOR_EXPONENT.value) -> float:
    """EN 442: phi = phi_nom * (LMTD / 49.83)^n, return = flow - split."""
    dt = lmtd(t_flow, t_flow - split, t_room)
    return phi_nom_w * (dt / C.RADIATOR_NOMINAL_DT.value) ** n


def min_flow_temp(load_w: float, phi_nom_w: float, t_room: float = C.DESIGN_TI.value,
                  lo: float = 25.0, hi: float = 90.0) -> float:
    """Lowest flow temperature at which the radiators deliver `load_w`.

    Returns nan if even `hi` is insufficient.
    """
    if load_w <= 0:
        return t_room
    if radiator_output_w(phi_nom_w, hi, t_room) < load_w:
        return float("nan")
    lo = max(lo, t_room + C.FLOW_RETURN_SPLIT.value + 0.1)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if radiator_output_w(phi_nom_w, mid, t_room) >= load_w:
            hi = mid
        else:
            lo = mid
    return hi


def heating_curve(htc: float, phi_nom_w: float, t_room: float = C.DESIGN_TI.value,
                  te_range=np.arange(-10, 16, 1.0)) -> pd.DataFrame:
    """Required flow temperature per outdoor temperature (no gains; conservative)."""
    rows = []
    for te in te_range:
        load = max(htc * (t_room - te), 0.0)
        rows.append({"te": te, "load_w": load,
                     "t_flow": min_flow_temp(load, phi_nom_w, t_room)})
    return pd.DataFrame(rows)


def phi_nom_from_design(load_w: float, t_flow: float = 80.0, t_return: float = 60.0,
                        t_room: float = C.DESIGN_TI.value,
                        n: float = C.RADIATOR_EXPONENT.value) -> float:
    """Nominal (75/65/20) radiator output that delivers `load_w` at t_flow/t_return."""
    dt = lmtd(t_flow, t_return, t_room)
    return load_w / (dt / C.RADIATOR_NOMINAL_DT.value) ** n


def hourly_demand_kw(fit, ti: float, elec_w: float, dhw_heat_w: float,
                     weather: pd.DataFrame) -> pd.Series:
    """Space-heat demand extrapolated from the fitted energy signature.

    Daily demand = HTC*(Ti - Te) + g*I + c - Q_elec - Q_dhw, clipped at zero (the
    model is fitted on daily/weekly means). Each day's energy is spread over its
    hours in proportion to the hourly indoor-outdoor difference.
    """
    counts = weather["te"].groupby(weather.index.floor("D")).transform("count")
    weather = weather[counts >= 24]               # complete days only
    day = weather.resample("D").mean().dropna()
    q_day_w = (fit.htc * (ti - day["te"]) + fit.solar_coef * day["solar"]
               + fit.intercept - elec_w - dhw_heat_w).clip(lower=0)
    diff = (ti - weather["te"]).clip(lower=0.1)
    share = diff / diff.resample("D").transform("sum")
    per_day_kwh = (q_day_w * 24 / 1000).reindex(weather.index.floor("D")).values
    return pd.Series(per_day_kwh * share.values, index=weather.index).fillna(0.0)


def annual_space_heat_kwh(q_hourly_kw: pd.Series) -> float:
    years = (q_hourly_kw.index.max() - q_hourly_kw.index.min()) / pd.Timedelta(days=365.25)
    return float(q_hourly_kw.sum() / years)


def hybrid_coverage(q_hourly_kw: pd.Series, sizes_kw=(2, 3, 4, 5, 6, 8)) -> pd.DataFrame:
    """Share of annual space-heating energy a heat pump of given size can supply
    (capacity treated as constant; derating at low temperature ignored)."""
    q = q_hourly_kw
    total = q.sum()
    return pd.DataFrame({
        "size_kw": list(sizes_kw),
        "coverage": [float(np.minimum(q, s).sum() / total) for s in sizes_kw],
    })


def condensing_share(curve: pd.DataFrame, te_hourly: pd.Series,
                     fixed_flow: float | None = None) -> float:
    """Share of heating hours with return temperature below the condensing limit.

    With `fixed_flow` the boiler runs at that flow temperature; otherwise it follows
    the weather-compensated curve.
    """
    te = te_hourly[te_hourly < C.NL_DEGREE_DAY_BASE.value].clip(lower=-10, upper=15)
    if fixed_flow is not None:
        t_ret = pd.Series(fixed_flow - C.FLOW_RETURN_SPLIT.value, index=te.index)
    else:
        t_ret = np.interp(te.values, curve["te"].values, curve["t_flow"].values) \
            - C.FLOW_RETURN_SPLIT.value
        t_ret = pd.Series(t_ret, index=te.index)
    return float((t_ret < C.CONDENSING_RETURN_MAX.value).mean())


def fixed_flow_limits(htc: float, phi_nom_w: float, te_hourly: pd.Series,
                      flows=(60.0, 55.0, 50.0), t_room: float = C.DESIGN_TI.value) -> list[dict]:
    """For a fixed flow temperature: lowest outdoor temperature at which the
    radiators still meet the load, and the share of heating hours at or above it."""
    heating = te_hourly[te_hourly < C.NL_DEGREE_DAY_BASE.value]
    out = []
    for tf in flows:
        cap = radiator_output_w(phi_nom_w, tf, t_room)
        te_min = t_room - cap / htc
        out.append({"flow": tf, "te_min": te_min,
                    "hours_share": float((heating >= te_min).mean())})
    return out


def nefit_rule_kw(gas_m3_per_year: float) -> float:
    """Gas-use rule of thumb for heat-pump size (Nefit Bosch): m3 * 8 / 1650."""
    return gas_m3_per_year * 8.0 / 1650.0
