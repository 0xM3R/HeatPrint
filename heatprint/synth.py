"""Synthetic Dutch demo home: a single-zone (1R1C) thermal model driven by real
KNMI De Bilt hourly weather. It produces a P1-style hourly CSV with a known HTC,
so the pipeline can be checked end to end. All parameters are illustrative
assumptions, not measurements of a real dwelling."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import constants as C
from .data import load_knmi


@dataclass
class DemoHome:
    htc_true: float = 220.0          # W/K
    htc_calculated: float = 264.0    # W/K, assumed design calculation 20% above true
    tau_h: float = 40.0              # thermal time constant, hours
    setpoint_day: float = 20.0       # degC, 07:00-23:00 local time
    setpoint_night: float = 16.0
    boiler_max_w: float = 24000.0
    ctrl_gain_w_per_k: float = 3000.0
    elec_base_w: float = 250.0
    elec_evening_w: float = 400.0    # extra 17:00-22:00
    occupants: int = 2
    metabolic_w: float = 80.0        # per occupant at home (assumption)
    solar_aperture_m2: float = 3.0
    dhw_m3_per_day: float = 0.35
    eff: float = C.NL_BOILER_EFF.value
    start: str = "2024-11-01"
    end: str = "2025-03-31"
    seed: int = 42

    def as_dict(self):
        return asdict(self)


def simulate(home: DemoHome = DemoHome()) -> pd.DataFrame:
    w = load_knmi()
    w = w[(w.index > pd.Timestamp(home.start)) &
          (w.index <= pd.Timestamp(home.end) + pd.Timedelta("1D"))].copy()
    w["te"] = w["te"].interpolate(limit=3)
    w["solar"] = w["solar"].fillna(0.0)
    rng = np.random.default_rng(home.seed)
    cap = home.htc_true * home.tau_h * 3600.0     # J/K
    sub = 6                                       # 10-minute substeps
    dt_s = 3600.0 / sub
    ti = home.setpoint_day
    kwh = C.NL_GAS_KWH_PER_M3.value
    rows = []
    for ts, r in w.iterrows():
        # KNMI stamps the end of the hour in UT; the hour start in local winter
        # time (UT+1) therefore has the same clock hour as the stamp.
        local_hour = ts.hour
        day = 7 <= local_hour < 23
        setp = home.setpoint_day if day else home.setpoint_night
        elec_w = home.elec_base_w + (home.elec_evening_w if 17 <= local_hour < 22 else 0.0)
        people_w = home.occupants * home.metabolic_w * (1.0 if (local_hour >= 17 or local_hour < 8) else 0.3)
        sol_w = home.solar_aperture_m2 * r["solar"]
        heat_j = 0.0
        ti_acc = 0.0
        for _ in range(sub):
            q_heat = float(np.clip(home.ctrl_gain_w_per_k * (setp - ti), 0.0, home.boiler_max_w))
            dti = (q_heat + elec_w + people_w + sol_w - home.htc_true * (ti - r["te"])) / cap
            ti += dti * dt_s
            heat_j += q_heat * dt_s
            ti_acc += ti
        dhw = 0.0
        if local_hour == 7:
            dhw = 0.6 * home.dhw_m3_per_day
        elif local_hour == 19:
            dhw = 0.4 * home.dhw_m3_per_day
        gas_m3 = heat_j / 3.6e6 / home.eff / kwh + dhw
        rows.append({
            "timestamp": ts,
            "gas_m3": round(gas_m3, 3),
            "elec_kwh": round(elec_w / 1000.0, 3),
            "t_indoor": round(ti_acc / sub + rng.normal(0, 0.2), 2),
        })
    return pd.DataFrame(rows)


def write_demo_csv(path: Path, home: DemoHome = DemoHome()) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    simulate(home).to_csv(path, index=False)
    return path
