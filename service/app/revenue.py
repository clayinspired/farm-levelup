"""Indicative moringa + VM0047 carbon revenue model.

Deliberately conservative. The purpose of this module is to stop a smallholder
walking away with an inflated number in their head, so every figure is a range,
the fixed costs of certification are always shown, and the break-even area is
computed rather than hidden.

Nothing here is a quote, an offer, or financial advice.
"""
from __future__ import annotations

from dataclasses import dataclass

ACRE_HA = 0.40468564224

# --- Carbon accumulation -----------------------------------------------------
# Moringa oleifera is fast-growing but LOW density wood (~0.25-0.35 g/cm3) and
# short-lived (~20 yr). Long-term standing stock is modest, and the usual moringa
# business (leaf/pod harvest with repeated coppicing) removes biomass before it
# can accumulate. Credits come from stock that STAYS in the field.
#   "woodlot"     : planted for biomass/pods, minimal coppicing, stock builds
#   "agroforestry": dispersed trees in cropland, moderate pruning
#   "leaf_intensive": cut back several times a year for leaf powder -- near-zero
#                     net long-term stock, which is the honest answer most
#                     moringa growers do not expect
# Published ARR removal rates: 3.2-10 tC/ha/yr in the tropics (~11.7-36.6 tCO2e),
# agroforestry 10.8-15.6 tCO2e/ha/yr over the first 20 years, with 10 tCO2e/ha/yr
# used widely as a planning baseline. Earlier values here sat well below all of it.
TCO2E_PER_HA_YR = {
    "woodlot":        (5.0, 9.0, 14.0),   # low / central / high
    "agroforestry":   (3.0, 6.0, 10.0),
    "leaf_intensive": (0.5, 1.2, 2.5),    # cut back for leaves: little stock is retained
}

# Sylvera, H1 2026: BBB-or-higher ARR averaged USD 28.55 against USD 9.12 for
# BB-or-lower. Top-rated ARR is quoted EUR 25-45. VM0047 v1.1 is the first ARR
# methodology to carry the ICVCM CCP label, so it prices in the upper tier.
PRICE_USD_PER_TCO2E = (12.0, 28.0, 45.0)
BUFFER_SHARE = 0.15                        # VCS non-permanence pooled buffer
REGISTRY_FEE_PER_CREDIT = 0.25             # Verra issuance levy, approx
DEVELOPER_SHARE = (0.30, 0.50, 0.65)       # typical project-developer revenue share

# --- Fixed certification costs (whole project, not per hectare) ---------------
PDD_VALIDATION_USD = (50_000, 100_000, 180_000)
VERIFICATION_USD = (20_000, 35_000, 60_000)   # per verification event
VERIFICATIONS_PER_30YR = 7                     # roughly every 4-5 years


@dataclass
class Estimate:
    area_ha: float
    management: str
    annual_tco2e: tuple
    annual_gross_usd: tuple
    annual_net_to_farmer_usd: tuple
    lifetime_net_to_farmer_usd: tuple
    fixed_cost_usd: tuple
    breakeven_ha: float
    viable_standalone: bool


def estimate(area_ha: float, management: str = "agroforestry", years: int = 30) -> Estimate:
    lo_r, mid_r, hi_r = TCO2E_PER_HA_YR.get(management, TCO2E_PER_HA_YR["agroforestry"])
    lo_p, mid_p, hi_p = PRICE_USD_PER_TCO2E

    # issued credits after the buffer pool
    issued = tuple(r * area_ha * (1 - BUFFER_SHARE) for r in (lo_r, mid_r, hi_r))
    gross = (issued[0] * lo_p, issued[1] * mid_p, issued[2] * hi_p)

    # farmer keeps what is left after the developer share and registry fees
    net = (
        gross[0] * (1 - DEVELOPER_SHARE[2]) - issued[0] * REGISTRY_FEE_PER_CREDIT,
        gross[1] * (1 - DEVELOPER_SHARE[1]) - issued[1] * REGISTRY_FEE_PER_CREDIT,
        gross[2] * (1 - DEVELOPER_SHARE[0]) - issued[2] * REGISTRY_FEE_PER_CREDIT,
    )
    net = tuple(max(0.0, v) for v in net)

    fixed = tuple(PDD_VALIDATION_USD[i] + VERIFICATION_USD[i] * VERIFICATIONS_PER_30YR
                  for i in range(3))

    # hectares needed before lifetime gross revenue covers central fixed costs
    per_ha_lifetime_gross = mid_r * (1 - BUFFER_SHARE) * mid_p * years
    breakeven = fixed[1] / per_ha_lifetime_gross if per_ha_lifetime_gross > 0 else float("inf")

    return Estimate(
        area_ha=area_ha,
        management=management,
        annual_tco2e=issued,
        annual_gross_usd=gross,
        annual_net_to_farmer_usd=net,
        lifetime_net_to_farmer_usd=tuple(v * years for v in net),
        fixed_cost_usd=fixed,
        breakeven_ha=breakeven,
        viable_standalone=area_ha >= breakeven,
    )


def moringa_crop_income(area_ha: float) -> tuple:
    """Indicative NON-carbon moringa income, for honest comparison.

    Leaf powder and seed/oil are where moringa money actually is. Wide ranges:
    yields and farmgate prices vary enormously by country and buyer access.
    """
    return (300 * area_ha, 1200 * area_ha, 3500 * area_ha)   # USD/ha/yr


def fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1000:
        return f"${v/1000:.1f}k"
    return f"${v:.0f}"


def fmt_range(t: tuple, unit: str = "") -> str:
    return f"{fmt_usd(t[0])}–{fmt_usd(t[2])}{unit} (central {fmt_usd(t[1])}{unit})"


def per_hectare(management: str = "agroforestry") -> dict:
    """Headline numbers quoted per hectare, so a farmer can scale them mentally
    without being asked for a plot size first."""
    e = estimate(1.0, management)
    leaf = estimate(1.0, "leaf_intensive")
    crop = moringa_crop_income(1.0)
    return dict(
        tco2e=e.annual_tco2e,
        usd_ha=e.annual_net_to_farmer_usd,
        usd_acre=tuple(v * ACRE_HA for v in e.annual_net_to_farmer_usd),
        leaf_usd_ha=leaf.annual_net_to_farmer_usd,
        crop_usd_ha=crop,
        breakeven_ha=e.breakeven_ha,
        fixed_cost=e.fixed_cost_usd,
    )
