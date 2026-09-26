import pytest

from heatprint import carbon
from heatprint import constants as C


def test_uk_gas_conversion():
    assert C.uk_gas_kwh_per_m3() == pytest.approx(11.22, abs=0.01)


def test_gas_for_heat():
    assert carbon.gas_m3_for_heat(9769 * 0.9, eff=0.9) == pytest.approx(1000, rel=1e-4)


def test_all_electric_saving_formula():
    heat = 10_000.0
    r = carbon.scenario_heat_pump(heat, 1.0, scop=4.0, ef_elec=0.5, ef_gas=2.0, eff=0.9)
    gas = heat / 0.9 / C.NL_GAS_KWH_PER_M3.value * 2.0
    assert r["gas_boiler_kg"] == pytest.approx(gas)
    assert r["with_hp_kg"] == pytest.approx(heat / 4.0 * 0.5)
    assert r["saving_kg"] == pytest.approx(gas - heat / 4.0 * 0.5)


def test_hybrid_between_extremes():
    heat = 10_000.0
    gas_only = carbon.scenario_heat_pump(heat, 0.0)["with_hp_kg"]
    full = carbon.scenario_heat_pump(heat, 1.0)["with_hp_kg"]
    half = carbon.scenario_heat_pump(heat, 0.5)["with_hp_kg"]
    assert min(gas_only, full) <= half <= max(gas_only, full)


def test_scale_up():
    rows = carbon.scale_up(100.0, adoption=(0.1,))
    assert rows[0]["kt_co2_per_year"] == pytest.approx(C.nl_gas_using_dwellings() * 0.1 * 100 / 1e6)


def test_nl_gas_dwellings():
    assert C.nl_gas_using_dwellings() == pytest.approx(8.3e6 * 0.851)


def test_jevons_reader_dominates():
    j = carbon.jevons(10.0)
    assert j["reader_kwh"] == pytest.approx(8.76)
    assert j["compute_kg"] < 1e-3 < j["reader_kg"]
