"""End-to-end pipeline: validation, demo home, carbon model, EnergiBridge
measurement and metrics.json."""
from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import advice, carbon, data, figures, htc, report, synth, validate
from . import constants as C

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIG = RESULTS / "figures"
METRICS = RESULTS / "metrics.json"
DEMO_CSV = RESULTS / "demo_home_p1.csv"
HYBRID_SIZE_KW = 3.0
WEATHER_YEARS = ("2021-01-01", "2025-12-31")


def energibridge_path() -> Path | None:
    """EnergiBridge binary from $HEATPRINT_ENERGIBRIDGE or PATH."""
    env = os.environ.get("HEATPRINT_ENERGIBRIDGE")
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("energibridge")
    return Path(found) if found else None


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    raise TypeError(type(o))


def load_metrics() -> dict:
    return json.loads(METRICS.read_text()) if METRICS.exists() else {}


def save_metrics(m: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(m, indent=2, sort_keys=True, default=_json_default))


def weather_years() -> pd.DataFrame:
    """KNMI De Bilt hourly te and solar over the reference years."""
    w = data.load_knmi()
    w = w[(w.index >= WEATHER_YEARS[0]) & (w.index <= WEATHER_YEARS[1])]
    return w.interpolate(limit=3).dropna()


# ------------------------------------------------------------- analysis ------
def dhw_estimate_m3_per_day(d: pd.DataFrame, kwh_per_m3: float) -> tuple[float, str]:
    """Hot-water gas from summer days if the data contain them, else the default."""
    summer = d[d["te"] >= 15.0]
    if len(summer) >= 14:
        return float(summer["gas_kwh"].median() / kwh_per_m3), "summer baseline"
    return C.DEFAULT_DHW_M3_PER_DAY.value, "default assumption"


def analyse(p1: pd.DataFrame, label: str, phi_nom_w: float | None = None,
            annual_gas_m3: float | None = None, eff: float = C.NL_BOILER_EFF.value,
            out_dir: Path = RESULTS, make_figures: bool = True,
            dhw_m3_per_day: float | None = None) -> dict:
    d = htc.daily(p1, eff)
    fit = htc.fit_weekly(d)
    r = {"label": label, "period": [str(p1.index.min().date()), str(p1.index.max().date())],
         "passed": bool(fit and fit.passed), "r2": fit.r2 if fit else float("nan"),
         "n_weeks": fit.n_points if fit else 0}
    if not r["passed"]:
        if make_figures:
            report.render(r, {}, out_dir / "home_report.html")
        return r
    lo, hi = htc.bootstrap_ci(d)
    weather = weather_years()
    te = weather["te"]
    design_w = advice.design_load_w(fit.htc)
    if phi_nom_w is None:  # assumption: radiators sized with a 20% margin at 80/60
        phi_nom_w = advice.phi_nom_from_design(1.2 * design_w)
    curve = advice.heating_curve(fit.htc, phi_nom_w)
    flow_design = advice.min_flow_temp(design_w, phi_nom_w)
    kwh_m3 = C.NL_GAS_KWH_PER_M3.value
    if dhw_m3_per_day is None:
        dhw, dhw_src = dhw_estimate_m3_per_day(d, kwh_m3)
    else:
        dhw, dhw_src = dhw_m3_per_day, "user input"
    h = htc.heating_days(d)
    q_hourly = advice.hourly_demand_kw(fit, float(h["ti"].mean()), float(h["q_elec_w"].mean()),
                                       eff * dhw * kwh_m3 * 1000 / 24, weather)
    heat_kwh = advice.annual_space_heat_kwh(q_hourly)
    space_gas = carbon.gas_m3_for_heat(heat_kwh, eff)
    gas_for_rule = annual_gas_m3 if annual_gas_m3 else space_gas + dhw * 365
    cov = advice.hybrid_coverage(q_hourly)
    hyb_share = float(cov.loc[cov["size_kw"] == HYBRID_SIZE_KW, "coverage"].iloc[0])
    all_el = carbon.scenario_heat_pump(heat_kwh, 1.0, eff=eff)
    all_el_mix = carbon.scenario_heat_pump(heat_kwh, 1.0, ef_elec=C.ELEC_CO2_NL_MIX.value, eff=eff)
    hybrid = carbon.scenario_heat_pump(heat_kwh, hyb_share, eff=eff)
    r.update({
        "htc": fit.htc, "htc_ci": [lo, hi], "solar_coef": fit.solar_coef,
        "design_kw": design_w / 1000,
        "design_kw_corrected": advice.design_load_w(fit.htc, te=C.DESIGN_TE_CORRECTED.value) / 1000,
        "phi_nom_w": phi_nom_w, "flow_design": flow_design,
        "flow_setting": float(np.ceil(flow_design)),
        "condensing_share": advice.condensing_share(curve, te),
        "fixed_flow_limits": advice.fixed_flow_limits(fit.htc, phi_nom_w, te),
        "annual_heat_kwh": heat_kwh, "space_heat_gas_m3": space_gas,
        "dhw_m3_per_day": dhw, "dhw_source": dhw_src,
        "peak_demand_kw_model": float(q_hourly.max()),
        "annual_gas_m3": gas_for_rule, "nefit_kw": advice.nefit_rule_kw(gas_for_rule),
        "hybrid": cov.to_dict(orient="records"), "hybrid_size_kw": HYBRID_SIZE_KW,
        "hybrid_share": hyb_share, "scop": C.SCOP_AIR_WATER.value,
        "co2": {"gas_boiler_kg": all_el["gas_boiler_kg"], "hybrid_kg": hybrid["with_hp_kg"],
                "all_electric_grey_kg": all_el["with_hp_kg"],
                "all_electric_mix_kg": all_el_mix["with_hp_kg"],
                "hybrid_saving_kg": hybrid["saving_kg"], "all_electric_saving_kg": all_el["saving_kg"],
                "all_electric_saving_share": all_el["saving_share"],
                "all_electric_mix_saving_kg": all_el_mix["saving_kg"]},
    })
    if make_figures:
        figs = {
            "heating_curve": figures.heating_curve_fig(curve, flow_design, FIG / "heating_curve_demo.png"),
            "hybrid": figures.hybrid_fig(cov, r["design_kw"], FIG / "hybrid_coverage_demo.png"),
            "co2": figures.co2_fig([
                ("Gas boiler (today)", r["co2"]["gas_boiler_kg"]),
                (f"Hybrid {HYBRID_SIZE_KW:g} kW ({hyb_share*100:.0f}% heat pump)", r["co2"]["hybrid_kg"]),
                ("All-electric, grey electricity", r["co2"]["all_electric_grey_kg"]),
                ("All-electric, NL grid mix 2025", r["co2"]["all_electric_mix_kg"]),
            ], FIG / "co2_options_demo.png"),
        }
        report.render(r, figs, out_dir / "home_report.html")
    return r


def run_validation() -> dict:
    res, out = validate.run()
    RESULTS.mkdir(parents=True, exist_ok=True)
    res.round(3).to_csv(RESULTS / "validation.csv", index=False)
    out["grid"].round(3).to_csv(RESULTS / "method_grid_dev.csv", index=False)
    m = out["metrics"]
    figures.validation_scatter(res, FIG / "validation_scatter.png")
    figures.bland_altman(res, m["all"]["heatprint"], FIG / "bland_altman.png")
    figures.data_length(pd.DataFrame(m["data_length_curve"]), FIG / "data_length.png")
    # example energy signature: first test home (ID order) that passes the gate
    ex = res[(res["split"] == "test") & res["passed"]].iloc[0]["hid"]
    _, days = validate.load_daily_all()
    d = days[ex]
    figures.signature(htc.weekly(htc.heating_days(d)), htc.fit_weekly(d), ex, FIG / "signature_example.png")
    m["example_home"] = ex
    return m


def run_demo() -> dict:
    home = synth.DemoHome()
    synth.write_demo_csv(DEMO_CSV, home)
    p1 = data.load_p1_csv(DEMO_CSV)
    phi_nom = advice.phi_nom_from_design(advice.design_load_w(home.htc_calculated))
    r = analyse(p1, "Synthetic Dutch demo home (De Bilt weather, winter 2024-25)",
                phi_nom_w=phi_nom, eff=home.eff)
    r["truth"] = home.as_dict()
    r["htc_error_pct"] = (r["htc"] - home.htc_true) / home.htc_true * 100
    # reference: the same simulated home run over the full 2021-2025 weather record
    full = synth.simulate(synth.DemoHome(start=WEATHER_YEARS[0], end=WEATHER_YEARS[1]))
    years = (pd.Timestamp(WEATHER_YEARS[1]) - pd.Timestamp(WEATHER_YEARS[0])) / pd.Timedelta(days=365.25)
    true_space_gas = (full["gas_m3"].sum() - home.dhw_m3_per_day * 365.25 * years) / years
    r["true_space_heat_gas_m3"] = float(true_space_gas)
    r["space_heat_gas_error_pct"] = (r["space_heat_gas_m3"] - true_space_gas) / true_space_gas * 100
    r["phi_nom_basis"] = "radiators sized for 80/60 degC at the calculated HTC (assumption)"
    r["calculated_design_kw"] = advice.design_load_w(home.htc_calculated) / 1000
    return r


# ------------------------------------------------------------- carbon --------
def carbon_summary(demo: dict, energy: dict | None) -> dict:
    mid = C.ZET_M_OP_60_KG.value
    out = {
        "flow_temp_saving_kg": {"low": C.ZET_M_OP_60_LOW, "high": C.ZET_M_OP_60_HIGH, "mid": mid},
        "nl_gas_using_dwellings": C.nl_gas_using_dwellings(),
        "scale_up_flow_temp": carbon.scale_up(mid),
        "scale_up_flow_temp_low": carbon.scale_up(C.ZET_M_OP_60_LOW),
        "scale_up_flow_temp_high": carbon.scale_up(C.ZET_M_OP_60_HIGH),
    }
    if energy:
        # Net energy per run is within measurement noise, so the gross energy
        # (idle system power included) is used as a conservative upper bound.
        j = carbon.jevons(energy["gross_j_mean"])
        j_nor = carbon.jevons(energy["gross_j_mean"], include_p1_reader=False)
        out["jevons"] = {
            **j,
            "energy_basis": "gross J per run (upper bound)",
            "compute_only_kg": j_nor["total_kg"],
            "ratio_saving_to_footprint_low": C.ZET_M_OP_60_LOW / j["total_kg"],
            "ratio_saving_to_compute_low": C.ZET_M_OP_60_LOW / j_nor["total_kg"],
            "runs_per_year": 12,
        }
    return out


# ------------------------------------------------------- EnergiBridge --------
_EB_RE = re.compile(r"Energy consumption in joules: ([0-9.eE+-]+) for ([0-9.eE+-]+) sec")


def _eb_run(eb: Path, cmd: list[str], out_csv: Path) -> tuple[float, float]:
    p = subprocess.run([str(eb), "--summary", "-o", str(out_csv), "--"] + cmd,
                       capture_output=True, text=True, cwd=ROOT, check=True)
    m = _EB_RE.search(p.stdout + p.stderr)
    if not m:
        raise RuntimeError("EnergiBridge summary not found:\n" + p.stdout + p.stderr)
    return float(m.group(1)), float(m.group(2))


def measure(reps: int = 10, cooldown_s: float = 3.0) -> dict:
    """Net energy of one `analyse` run = E(run) - idle power x duration."""
    eb = energibridge_path()
    if eb is None:
        raise FileNotFoundError("EnergiBridge not found; set HEATPRINT_ENERGIBRIDGE")
    eb_dir = RESULTS / "energibridge"
    eb_dir.mkdir(parents=True, exist_ok=True)
    analyse_cmd = [sys.executable, "-m", "heatprint", "analyse", str(DEMO_CSV),
                   "--out", str(eb_dir / "scratch"), "--no-figures"]
    runs, idles = [], []
    for i in range(reps):
        e, t = _eb_run(eb, analyse_cmd, eb_dir / f"analyse_{i:02d}.csv")
        runs.append((e, t))
        time.sleep(cooldown_s)
        dur = statistics.mean(x[1] for x in runs)
        e0, t0 = _eb_run(eb, ["sleep", f"{dur:.2f}"], eb_dir / f"idle_{i:02d}.csv")
        idles.append((e0, t0))
        time.sleep(cooldown_s)
    idle_w = statistics.mean(e / t for e, t in idles)
    net = [e - idle_w * t for e, t in runs]
    return {
        "reps": reps, "idle_power_w": idle_w,
        "gross_j_mean": statistics.mean(e for e, _ in runs),
        "duration_s_mean": statistics.mean(t for _, t in runs),
        "net_j_per_run": statistics.mean(net), "net_j_sd": statistics.stdev(net),
        "note": "Whole-system energy (EnergiBridge SYSTEM_POWER on macOS) minus idle baseline.",
    }


def constants_table() -> dict:
    return {k: {"value": v.value, "unit": v.unit, "source": v.source, "note": v.note,
                "verified": v.verified} for k, v in C.ALL.items()}
