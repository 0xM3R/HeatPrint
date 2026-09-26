"""CO2 scenarios, Dutch scale-up and the Jevons check."""
from __future__ import annotations

from . import constants as C


def gas_m3_for_heat(heat_kwh: float, eff: float = C.NL_BOILER_EFF.value) -> float:
    return heat_kwh / eff / C.NL_GAS_KWH_PER_M3.value


def scenario_heat_pump(heat_kwh: float, coverage: float = 1.0,
                       scop: float = C.SCOP_AIR_WATER.value,
                       ef_elec: float = C.ELEC_CO2_GREY.value,
                       ef_gas: float = C.GAS_CO2_WTW.value,
                       eff: float = C.NL_BOILER_EFF.value) -> dict:
    """Annual space-heating CO2 for gas boiler vs (hybrid) heat pump.

    `coverage` is the share of heat supplied by the heat pump (1.0 = all-electric).
    """
    gas_only = gas_m3_for_heat(heat_kwh, eff) * ef_gas
    hp_part = coverage * heat_kwh / scop * ef_elec
    gas_part = gas_m3_for_heat((1 - coverage) * heat_kwh, eff) * ef_gas
    with_hp = hp_part + gas_part
    return {"gas_boiler_kg": gas_only, "with_hp_kg": with_hp,
            "saving_kg": gas_only - with_hp,
            "saving_share": (gas_only - with_hp) / gas_only if gas_only else 0.0}


def scale_up(per_home_kg: float, adoption=(0.01, 0.05, 0.10)) -> list[dict]:
    homes = C.nl_gas_using_dwellings()
    return [{"adoption": a, "homes": homes * a,
             "kt_co2_per_year": homes * a * per_home_kg / 1e6} for a in adoption]


def jevons(energy_j_per_run: float, runs_per_year: float = 12.0,
           include_p1_reader: bool = True,
           ef_elec: float = C.ELEC_CO2_GREY.value) -> dict:
    """Operational footprint of HeatPrint for one household per year."""
    compute_kwh = energy_j_per_run * runs_per_year / 3.6e6
    reader_kwh = C.P1_READER_POWER.value * 8760 / 1000.0 if include_p1_reader else 0.0
    compute_kg = compute_kwh * ef_elec
    reader_kg = reader_kwh * ef_elec
    return {"compute_kwh": compute_kwh, "compute_kg": compute_kg,
            "reader_kwh": reader_kwh, "reader_kg": reader_kg,
            "total_kg": compute_kg + reader_kg}
