"""Physical, emission and policy constants used by HeatPrint.

Every value carries its unit and source. ``verified=False`` marks values that are
engineering assumptions without a primary source; they surface as
[needs verification] in the report and the fact sheet.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Const:
    value: float
    unit: str
    source: str
    note: str = ""
    verified: bool = True


# --- Gas energy content -----------------------------------------------------
UK_GAS_CV = Const(
    39.5, "MJ/m3 (gross)",
    "https://www.gov.uk/guidance/gas-meter-readings-and-bill-calculation",
    "Typical UK calorific value; transporters keep it within 38-41 MJ/m3. "
    "The SMETER dataset does not report the CV of the supplied gas.",
)
UK_VOLUME_CORRECTION = Const(
    1.02264, "-",
    "https://www.gov.uk/guidance/gas-meter-readings-and-bill-calculation",
    "Prescribed by the Gas (Calculation of Thermal Energy) Regulations 1996.",
)
NL_GAS_KWH_PER_M3 = Const(
    9.769, "kWh/m3 (upper value, 35.17 MJ/m3)",
    "https://pure-energie.nl/kennisbank/calorische-waarde-van-gas/",
    "Upper (gross) value of Groningen-quality gas used on Dutch energy bills.",
)

# --- Emission factors (co2emissiefactoren.nl, 2025 list) ----------------------
GAS_CO2_WTW = Const(
    2.134, "kg CO2-eq/m3",
    "https://co2emissiefactoren.nl/factoren/2025/27/135/brandstoffen-energieopwekking-gasvormige-brandstoffen-aardgas-g-gas/",
    "Natural gas (G-gas), well-to-wheel (combustion + supply chain).",
)
GAS_CO2_TTW = Const(
    1.779, "kg CO2/m3",
    "https://co2emissiefactoren.nl/factoren/2025/27/135/brandstoffen-energieopwekking-gasvormige-brandstoffen-aardgas-g-gas/",
    "Natural gas (G-gas), combustion only.",
)
ELEC_CO2_GREY = Const(
    0.497, "kg CO2-eq/kWh",
    "https://co2emissiefactoren.nl/factoren/2025/11/elektriciteit/?unit=kwh",
    "Grey electricity 2025, chain emissions included (footprint convention).",
)
ELEC_CO2_NL_MIX = Const(
    0.209, "kg CO2/kWh",
    "https://ned.nl/nl/achtergrond/jaaroverzicht-2025",
    "Average Dutch production mix 2025 (Nationaal Energie Dashboard).",
)

# --- Dutch housing stock (CBS) ----------------------------------------------
NL_DWELLINGS = Const(
    8.3e6, "dwellings (1 Jan 2025)",
    "https://www.clo.nl/indicatoren/nl216606-woningvoorraad-naar-bouwjaar-en-woningtype-2025",
    "'Bijna 8,3 miljoen woningen'.",
)
NL_SHARE_GAS_FREE = Const(
    0.112, "share of dwellings (2024)",
    "https://www.cbs.nl/nl-nl/nieuws/2025/50/steeds-meer-woningen-aardgasvrij",
)
NL_SHARE_HYBRID = Const(
    0.037, "share of dwellings (2024)",
    "https://www.cbs.nl/nl-nl/nieuws/2025/50/steeds-meer-woningen-aardgasvrij",
    "Nearly gas-free, mostly hybrid heat pumps.",
)

# --- Heating design (ISSO 51) ------------------------------------------------
DESIGN_TE = Const(
    -10.0, "degC",
    "https://www.vitec-vabi.com/nieuws/isso-51-effectenstudie-2017-vs-2023/",
    "ISSO 51 base design outdoor temperature; the time-constant correction can "
    "raise it to -6 degC for heavy, well-insulated dwellings.",
)
DESIGN_TE_CORRECTED = Const(
    -6.0, "degC",
    "https://www.vitec-vabi.com/nieuws/isso-51-effectenstudie-2017-vs-2023/",
    "Upper bound after the ISSO 51 time-constant correction (up to 4 K).",
)
DESIGN_TI = Const(
    20.0, "degC",
    "https://www.vitec-vabi.com/nieuws/isso-51-effectenstudie-2017-vs-2023/",
    "ISSO 51:2017 default for habitable rooms (the 2023 edition uses 22 degC).",
)

# --- Heat emitters and boilers -----------------------------------------------
RADIATOR_EXPONENT = Const(
    1.3, "-",
    "EN 442 radiator characteristic",
    "Typical exponent for panel radiators; model-specific values vary.",
    verified=False,
)
RADIATOR_NOMINAL_DT = Const(
    49.83, "K",
    "EN 442 rating point 75/65/20 degC",
    "Log-mean temperature difference at the EN 442 rating point.",
)
FLOW_RETURN_SPLIT = Const(
    10.0, "K",
    "Modelling assumption",
    "Flow minus return temperature held constant when solving for flow temperature.",
    verified=False,
)
CONDENSING_RETURN_MAX = Const(
    55.0, "degC",
    "https://zetmop60.nl/veelgestelde-vragen/",
    "Return temperature below which flue-gas water vapour condenses; Dutch "
    "sources quote roughly 55-58 degC, the lower bound is used.",
    verified=False,
)
NL_BOILER_EFF = Const(
    0.897, "- (gross, winter seasonal)",
    "SMETER P2 DwellingInfo (SAP winter seasonal efficiency, Vaillant ecoTEC pro)",
    "Applied to the synthetic Dutch demo home; Dutch boiler stock not verified.",
    verified=False,
)
SCOP_AIR_WATER = Const(
    3.5, "-",
    "https://www.warmtepompkenner.nl/rendement",
    "Sector sources give 3-4.5 for air-to-water heat pumps in the Netherlands.",
    verified=False,
)
NL_DEGREE_DAY_BASE = Const(
    18.0, "degC",
    "Dutch degree-day convention (graaddagen)",
    "Base temperature below which space heating is assumed to be required.",
    verified=False,
)
DEFAULT_DHW_M3_PER_DAY = Const(
    0.3, "m3 gas/day",
    "Modelling assumption for hot-water gas use",
    "Used only when the data contain no summer days to estimate the baseline.",
    verified=False,
)
P1_READER_POWER = Const(
    1.0, "W",
    "Assumption for a P1-port reader running continuously",
    "Only relevant when no supplier data export is used.",
    verified=False,
)

# --- Published savings for lowering the boiler flow temperature ---------------
ZET_M_OP_60_KG = Const(
    (94.0 + 140.0) / 2, "kg CO2/yr",
    "https://zetmop60.nl/veelgestelde-vragen/",
    "Campaign FAQ: 94-140 kg CO2 per year per participant for 80 -> 60 degC.",
)
ZET_M_OP_60_LOW = 94.0
ZET_M_OP_60_HIGH = 140.0

# Rule of thumb for heat-pump sizing from annual gas use (Nefit Bosch):
# kW = m3/yr * 8 / 1650
NEFIT_RULE_SOURCE = "https://www.nefit-bosch.nl/producten/warmtepompen/benodigde-vermogen-warmtepomp-berekenen/"


def uk_gas_kwh_per_m3() -> float:
    """kWh per m3 for UK meter readings (GOV.UK formula)."""
    return UK_VOLUME_CORRECTION.value * UK_GAS_CV.value / 3.6


def nl_gas_using_dwellings() -> float:
    """Dwellings still using natural gas as main heat source (own calculation)."""
    return NL_DWELLINGS.value * (1 - NL_SHARE_GAS_FREE.value - NL_SHARE_HYBRID.value)


ALL = {
    name: obj for name, obj in globals().items() if isinstance(obj, Const)
}
