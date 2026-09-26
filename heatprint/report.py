"""One-page HTML home report (the demo artefact)."""
from __future__ import annotations

import base64
import html
from pathlib import Path

from .figures import pct


def _img(path: Path) -> str:
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<img alt="{html.escape(Path(path).stem)}" src="data:image/png;base64,{b64}">'


def render(r: dict, figs: dict[str, Path], out: Path) -> Path:
    if not r["passed"]:
        body = f"""
        <section class="card warn"><h2>Not enough usable data yet</h2>
        <p>The weekly energy signature did not pass the quality gate
        (R² = {r['r2']:.2f}, {r['n_weeks']} heating weeks). HeatPrint needs at least one
        heating season of hourly gas and indoor-temperature data.</p></section>"""
    else:
        hyb = "".join(f"<tr><td>{c['size_kw']:g} kW</td><td>{pct(c['coverage'])}</td></tr>"
                      for c in r["hybrid"])
        fixed = "".join(f"<tr><td>{x['flow']:.0f} °C</td><td>{x['te_min']:.1f} °C</td>"
                        f"<td>{x['hours_share']*100:.1f}%</td></tr>" for x in r["fixed_flow_limits"])
        body = f"""
        <section class="tiles">
          <div class="tile"><span class="lab">Heat loss (HTC)</span>
            <span class="val">{r['htc']:.0f} W/K</span>
            <span class="sub">95% interval {r['htc_ci'][0]:.0f}–{r['htc_ci'][1]:.0f} W/K</span></div>
          <div class="tile"><span class="lab">Max boiler flow temperature</span>
            <span class="val">{r['flow_setting']:.0f} °C</span>
            <span class="sub">enough on a −10 °C day; factory setting is often 80 °C</span></div>
          <div class="tile"><span class="lab">Heat-pump size (all-electric)</span>
            <span class="val">{r['design_kw']:.1f} kW</span>
            <span class="sub">{r['design_kw_corrected']:.1f} kW with ISSO 51 time-constant correction</span></div>
          <div class="tile"><span class="lab">Gas-use rule of thumb</span>
            <span class="val">{r['nefit_kw']:.1f} kW</span>
            <span class="sub">m³ × 8 / 1650 on {r['annual_gas_m3']:.0f} m³/yr</span></div>
        </section>
        <section class="card"><h2>1 · Lower your boiler temperature</h2>
          <p>Your radiators deliver the design-day heat load at a flow temperature of
          <b>{r['flow_design']:.1f} °C</b>. On a weather-compensated curve, the modelled return
          water stays below 55 °C in <b>{r['condensing_share']*100:.1f}%</b> of heating hours
          (KNMI De Bilt, 2021–2025). A fixed setting works too:</p>
          <table><tr><th>Fixed flow setting</th><th>Warm enough down to</th><th>Heating hours covered</th></tr>{fixed}</table>
          {_img(figs['heating_curve'])}</section>
        <section class="card"><h2>2 · Heat-pump readiness</h2>
          <p>Measured design load: <b>{r['design_kw']:.1f} kW</b> at −10 °C. A hybrid heat pump
          covers this share of your annual space heat:</p>
          <table><tr><th>Heat-pump size</th><th>Share of heat</th></tr>{hyb}</table>
          {_img(figs['hybrid'])}</section>
        <section class="card"><h2>3 · CO₂ per option</h2>{_img(figs['co2'])}
          <p class="note">Space heating only; factors from co2emissiefactoren.nl (2025).
          Heat-pump SCOP {r['scop']} is an indicative assumption.</p></section>"""
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>HeatPrint home report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{ --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3de; --bg:#fcfcfb; --accent:#2a78d6; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:28px 20px 40px; }}
header h1 {{ margin:0; font-size:26px; }} header p {{ margin:4px 0 20px; color:var(--ink2); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; }}
.tile {{ border:1px solid var(--line); border-radius:10px; padding:14px; background:#fff; display:flex; flex-direction:column; }}
.lab {{ font-size:12px; color:var(--ink2); text-transform:uppercase; letter-spacing:.04em; }}
.val {{ font-size:28px; font-weight:700; margin:4px 0; }} .sub {{ font-size:12px; color:var(--ink2); }}
.card {{ border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-top:16px; background:#fff; }}
.card h2 {{ margin:0 0 8px; font-size:18px; }} .card img {{ width:100%; max-width:720px; display:block; margin-top:8px; }}
.warn {{ border-color:#eda100; }} table {{ border-collapse:collapse; margin:6px 0; }}
td,th {{ border-bottom:1px solid var(--line); padding:4px 14px 4px 0; text-align:left; }}
.note {{ font-size:12px; color:var(--ink2); }} footer {{ margin-top:20px; font-size:12px; color:var(--ink2); }}
</style></head><body><main>
<header><h1>HeatPrint · home report</h1>
<p>{html.escape(r['label'])} · {r['period'][0]} to {r['period'][1]} · {r['n_weeks']} heating weeks ·
fit R² = {r['r2']:.2f}</p></header>
{body}
<footer>Computed locally from smart-meter (P1) gas and electricity, indoor temperature and KNMI
De Bilt weather. Method: weekly energy-signature regression, validated on 30 UK homes with
co-heating tests (SMETER TEST Phase 2).</footer>
</main></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
