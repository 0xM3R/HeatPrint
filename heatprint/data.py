"""Data acquisition and parsing: SMETER Phase 2 (ReShare 856978), KNMI hourly
weather, and generic smart-meter CSV files."""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import constants as C

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

SMETER_URL = "https://reshare.ukdataservice.ac.uk/856978/1/856978_data_and_documentation.zip"
KNMI_URL = ("https://cdn.knmi.nl/knmi/map/page/klimatologie/gegevens/uurgegevens/"
            "uurgeg_260_2021-2030.zip")
SMETER_ZIP = RAW / "smeter_856978.zip"
KNMI_ZIP = RAW / "knmi_uurgeg_260_2021-2030.zip"
SMETER_DIR = RAW / "smeter" / "856978_data_and_documentation"

# Physically implausible half-hourly gas volume for a 28 kW combi boiler
# (28 kW * 0.5 h / 11.2 kWh/m3 ~ 1.25 m3); larger values are meter catch-up spikes.
MAX_GAS_M3_PER_HALF_HOUR = 1.6


def download(force: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for url, dest in ((SMETER_URL, SMETER_ZIP), (KNMI_URL, KNMI_ZIP)):
        if dest.exists() and not force:
            continue
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, dest)
    if not SMETER_DIR.exists():
        with zipfile.ZipFile(SMETER_ZIP) as z:
            z.extractall(RAW / "smeter")


# ---------------------------------------------------------------- SMETER -----
def _parse_date(s) -> pd.Timestamp | None:
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return pd.to_datetime(s.strip(), format="%d/%m/%Y")
    except ValueError:
        return None


def load_dwelling_info() -> pd.DataFrame:
    """One row per dwelling with co-heating HTC, RdSAP HTC and boiler efficiency.

    HH04 had its boiler replaced on 06/11/2020; both efficiencies are kept.
    """
    di = pd.read_csv(SMETER_DIR / "SMETER_P2_DwellingInfo.csv", encoding="latin1")
    di["hid"] = di["House_ID"].str.slice(0, 4)
    post = di[di["House_ID"].str.contains("post", na=False)]
    di = di[~di["House_ID"].str.contains("post", na=False)].copy()
    di["eff_winter"] = di["Boiler_efficiency_Winter seasonal"] / 100.0
    di["eff_winter_after"] = np.nan
    di["eff_change_date"] = pd.NaT
    if len(post):
        i = di.index[di["hid"] == "HH04"][0]
        di.loc[i, "eff_winter_after"] = post["Boiler_efficiency_Winter seasonal"].iloc[0] / 100.0
        di.loc[i, "eff_change_date"] = pd.Timestamp("2020-11-06")
    di["occupied_from"] = di["Self-reported permanent occupation date (from interview)"].map(_parse_date)
    di["withdrawn"] = di["Voluntary_withdrawal_date"].map(_parse_date)
    out = pd.DataFrame({
        "hid": di["hid"],
        "htc_coheat": di["Co-heating HTC"],
        "htc_coheat_lo": di["Co-heating CI Lower including seasonal uncertainty"],
        "htc_coheat_hi": di["Co-heating CI Upper including seasonal uncertainty"],
        "htc_rdsap": di["RdSAP HTC - Average (W/K)"],
        "floor_area": di["Total Floor Area (m2) - measured by TEST team (not Halton survey)"],
        "dwelling_type": di["Dwelling type"],
        "eff_winter": di["eff_winter"],
        "eff_winter_after": di["eff_winter_after"],
        "eff_change_date": di["eff_change_date"],
        "occupied_from": di["occupied_from"],
        "withdrawn": di["withdrawn"],
        "occupants": di["Number of permanent occupants"],
    })
    return out.reset_index(drop=True)


def load_smeter_home(hid: str) -> pd.DataFrame:
    """Half-hourly series with columns gas_kwh, elec_kwh, ti, te, solar."""
    with zipfile.ZipFile(SMETER_DIR / "SMETER_P2_Energy_Temp_RH_Weather_30homes.zip") as z:
        df = pd.read_csv(z.open(f"Meter_TemperatureRH_Weather_30homes/{hid}_all.csv"),
                         low_memory=False)
    df.index = pd.to_datetime(df.iloc[:, 0], format="%d/%m/%Y %H:%M")
    df = df.drop(columns=df.columns[0])
    gas = df["Gas m3"].where((df["Gas m3"] >= 0) & (df["Gas m3"] <= MAX_GAS_M3_PER_HALF_HOUR))
    temp_cols = [c for c in df.columns if c.endswith("_temp")]
    return pd.DataFrame({
        "gas_kwh": gas * C.uk_gas_kwh_per_m3(),
        "elec_kwh": df["Elec kWh"].where(df["Elec kWh"] >= 0),
        "ti": df[temp_cols].mean(axis=1),
        "te": df["Air temp (degC)"],
        "solar": df["Solar_vert_south (W/m2)"],
    })


# ------------------------------------------------------------------ KNMI -----
def load_knmi() -> pd.DataFrame:
    """Hourly De Bilt weather: te (degC) and solar (global horizontal, W/m2).

    KNMI hour HH covers (HH-1, HH] in UT; the timestamp is the end of the hour.
    """
    with zipfile.ZipFile(KNMI_ZIP) as z:
        name = [n for n in z.namelist() if n.endswith(".txt")][0]
        text = z.read(name).decode("latin1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("# STN"))
    header = [h.strip() for h in lines[start].lstrip("#").split(",")]
    body = "\n".join(l for l in lines[start + 1:] if l.strip())
    df = pd.read_csv(io.StringIO(body), names=header, skipinitialspace=True,
                     na_values=["", " "])
    ts = (pd.to_datetime(df["YYYYMMDD"].astype(str), format="%Y%m%d")
          + pd.to_timedelta(df["HH"], unit="h"))
    out = pd.DataFrame({
        "te": df["T"] / 10.0,
        "solar": df["Q"] * 10000.0 / 3600.0,   # J/cm2 per hour -> W/m2
    })
    out.index = ts
    return out.sort_index()


# ------------------------------------------------------- generic P1 CSV -------
REQUIRED = ("timestamp", "gas_m3", "elec_kwh", "t_indoor")


def load_p1_csv(path: str | Path, gas_kwh_per_m3: float | None = None) -> pd.DataFrame:
    """Read a Dutch smart-meter export (hourly or finer).

    Required columns: timestamp, gas_m3, elec_kwh, t_indoor.
    Optional: t_outdoor, solar_wm2. Missing weather is joined from KNMI De Bilt.
    """
    raw = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    raw.index = pd.to_datetime(raw["timestamp"])
    k = gas_kwh_per_m3 or C.NL_GAS_KWH_PER_M3.value
    df = pd.DataFrame({
        "gas_kwh": raw["gas_m3"].where(raw["gas_m3"] >= 0) * k,
        "elec_kwh": raw["elec_kwh"].where(raw["elec_kwh"] >= 0),
        "ti": raw["t_indoor"],
    })
    if "t_outdoor" in raw.columns and "solar_wm2" in raw.columns:
        df["te"] = raw["t_outdoor"]
        df["solar"] = raw["solar_wm2"]
    else:
        w = load_knmi().reindex(df.index, method="nearest", tolerance=pd.Timedelta("1h"))
        df["te"] = w["te"].values
        df["solar"] = w["solar"].values
    return df
