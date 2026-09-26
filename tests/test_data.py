import pandas as pd
import pytest

from heatprint import data, htc, pipeline, synth

needs_smeter = pytest.mark.skipif(not data.SMETER_DIR.exists(), reason="SMETER data not downloaded")
needs_knmi = pytest.mark.skipif(not data.KNMI_ZIP.exists(), reason="KNMI data not downloaded")


@needs_smeter
def test_dwelling_info():
    di = data.load_dwelling_info()
    assert len(di) == 30
    assert di["htc_coheat"].between(100, 300).all()
    hh04 = di[di["hid"] == "HH04"].iloc[0]
    assert hh04["eff_winter_after"] == pytest.approx(0.867)


@needs_smeter
def test_smeter_home_columns():
    df = data.load_smeter_home("HH01")
    assert list(df.columns) == ["gas_kwh", "elec_kwh", "ti", "te", "solar"]
    assert (df["gas_kwh"].dropna() >= 0).all()


@needs_knmi
def test_knmi_units():
    w = data.load_knmi()
    assert w["te"].between(-25, 40).all()
    assert w["solar"].dropna().between(0, 1200).all()


def test_p1_csv_requires_columns(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"timestamp": ["2024-01-01 00:00"], "gas_m3": [0.1]}).to_csv(p, index=False)
    with pytest.raises(ValueError):
        data.load_p1_csv(p)


@needs_knmi
def test_demo_home_recovered(tmp_path):
    home = synth.DemoHome()
    path = synth.write_demo_csv(tmp_path / "demo.csv", home)
    d = htc.daily(data.load_p1_csv(path), home.eff)
    f = htc.fit_weekly(d)
    assert f.passed
    assert f.htc == pytest.approx(home.htc_true, rel=0.05)


@needs_knmi
def test_analyse_outputs_consistent(tmp_path):
    home = synth.DemoHome()
    path = synth.write_demo_csv(tmp_path / "demo.csv", home)
    r = pipeline.analyse(data.load_p1_csv(path), "t", phi_nom_w=9000, eff=home.eff,
                         out_dir=tmp_path, make_figures=False)
    assert r["passed"]
    assert 30 < r["flow_design"] < 90
    assert r["co2"]["all_electric_grey_kg"] < r["co2"]["gas_boiler_kg"]
    assert r["design_kw_corrected"] < r["design_kw"]
