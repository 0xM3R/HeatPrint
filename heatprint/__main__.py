"""HeatPrint command line.

    python -m heatprint download        fetch SMETER + KNMI data
    python -m heatprint validate        30-home validation vs co-heating
    python -m heatprint demo            synthetic Dutch home + HTML report
    python -m heatprint analyse FILE    analyse your own P1 export
    python -m heatprint measure         EnergiBridge footprint of `analyse`
    python -m heatprint all             everything above, in order
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import constants as C
from . import data, figures, pipeline


def _validate(m):
    print("validation ...")
    m["validation"] = pipeline.run_validation()
    t = m["validation"]["test"]
    print(f"  test homes gated {t['gated']}/{t['homes']}, MAPE {t['heatprint']['mape']:.1f}%")


def _demo(m):
    print("demo home ...")
    m["demo"] = pipeline.run_demo()
    d = m["demo"]
    print(f"  HTC {d['htc']:.1f} W/K (true {d['truth']['htc_true']}), flow {d['flow_setting']:.0f} degC")


def _measure(m):
    if pipeline.energibridge_path() is None:
        print("EnergiBridge not found (set HEATPRINT_ENERGIBRIDGE or put it on PATH); skipping")
        return
    print("EnergiBridge measurement (about 2 minutes) ...")
    m["energibridge"] = pipeline.measure()
    print(f"  gross {m['energibridge']['gross_j_mean']:.1f} J per analyse run")


def _carbon(m):
    m["carbon"] = pipeline.carbon_summary(m["demo"], m.get("energibridge"))
    m["constants"] = pipeline.constants_table()
    j = m["carbon"].get("jevons")
    if j:
        figures.jevons_fig([
            ("HeatPrint compute (12 runs/yr)", j["compute_only_kg"], "cost"),
            ("P1 reader, 1 W always on", j["reader_kg"], "cost"),
            ("Boiler 80 → 60 °C (low estimate)", C.ZET_M_OP_60_LOW, "saving"),
            ("Right-sized heat pump (demo)", m["demo"]["co2"]["all_electric_saving_kg"], "saving"),
        ], pipeline.FIG / "jevons.png")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="heatprint")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download")
    sub.add_parser("validate")
    sub.add_parser("demo")
    sub.add_parser("measure")
    a = sub.add_parser("all")
    a.add_argument("--skip-measure", action="store_true")
    an = sub.add_parser("analyse")
    an.add_argument("csv", type=Path)
    an.add_argument("--radiator-w", type=float, default=None,
                    help="total nominal radiator output at 75/65/20 degC (W)")
    an.add_argument("--annual-gas", type=float, default=None, help="annual gas use (m3)")
    an.add_argument("--out", type=Path, default=pipeline.RESULTS / "analyse")
    an.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "download":
        data.download()
        return
    if args.cmd == "analyse":
        r = pipeline.analyse(data.load_p1_csv(args.csv), args.csv.name, args.radiator_w,
                             args.annual_gas, out_dir=args.out,
                             make_figures=not args.no_figures)
        if r["passed"]:
            print(f"HTC {r['htc']:.0f} W/K  (95% {r['htc_ci'][0]:.0f}-{r['htc_ci'][1]:.0f}); "
                  f"max flow {r['flow_setting']:.0f} degC; heat pump {r['design_kw']:.1f} kW")
        else:
            print(f"insufficient data (R2 = {r['r2']:.2f}, weeks = {r['n_weeks']})")
        return

    m = pipeline.load_metrics()
    if args.cmd in ("validate", "all"):
        if args.cmd == "all":
            data.download()
        _validate(m)
    if args.cmd in ("demo", "all"):
        _demo(m)
    if args.cmd == "measure" or (args.cmd == "all" and not args.skip_measure):
        _measure(m)
    if "demo" in m:
        _carbon(m)
    pipeline.save_metrics(m)


if __name__ == "__main__":
    main()
