# HeatPrint

Measures a home's heat loss (heat transfer coefficient, W/K) from smart-meter gas data, indoor temperature
and KNMI weather. From that number it recommends the lowest boiler flow temperature that still keeps the
home warm and the heat-pump size it needs. Ordinary least squares plus a radiator model; no ML, no cloud.

## Results (`results/`)

| | |
|---|---|
| Validation: 30 UK homes with co-heating tests (SMETER TEST Phase 2) | held-out homes: 11/15 pass the quality gate, MAPE 13.7%, bias −1.9%, 82% within ±20% |
| Same homes, on-site RdSAP survey calculation | MAPE 12.4%: comparable accuracy, HeatPrint needs no site visit |
| Data needed | median error 39% with 4 heating weeks, 19% with 16 weeks: use a full season |
| Synthetic Dutch demo home (De Bilt weather) | HTC 222.7 W/K vs 220 true; max flow 68.5 °C instead of 80 °C; heat pump 6.7 kW |
| CO₂ (demo home, space heating) | 2,294 kg/yr gas boiler → 1,337 kg/yr heat pump on grey electricity |
| Own footprint (EnergiBridge) | ≤ 7.9 J per analysis; savings exceed footprint incl. a 1 W meter reader ≥ 22× |

The method was selected on odd-numbered homes and is reported on even-numbered homes; the test set is not
fully blind (test errors were visible during development). All numbers are in `results/metrics.json`.

## Run

```bash
uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/python -m heatprint all --skip-measure   # download data, validate, demo
.venv/bin/python -m heatprint analyse my_p1.csv --radiator-w 9000
.venv/bin/python -m pytest -q
```

`analyse` reads a CSV with `timestamp, gas_m3, elec_kwh, t_indoor`. For the energy measurement, set
`HEATPRINT_ENERGIBRIDGE=/path/to/energibridge` and run `python -m heatprint measure`.

## Data and licences

SMETER TEST Phase 2 (Allinson et al., UK Data Service, [10.5255/UKDA-SN-856978](https://doi.org/10.5255/UKDA-SN-856978), CC BY 4.0),
KNMI hourly weather De Bilt (open data). Emission factors: co2emissiefactoren.nl 2025. Sources and
unverified assumptions are listed in `heatprint/constants.py`.
