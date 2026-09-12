"""VM0047 land-eligibility screening tests.

SCREENING ONLY. These tests narrow a portfolio to sites worth a full feasibility
study; they do not constitute a validation-grade eligibility determination, which
requires the host-country forest definition, land tenure and policy layers, field
validation of the stocking index, and a VVB.

Grounded in VM0047 v1.0/v1.1:
  - Applicability #11a (census): non-forest for the past ten years, <10% pre-existing
    woody biomass cover.
  - Applicability #13 (census): ineligible if comparable woody biomass was removed
    within the last ten years.
  - Applicability #4, #5: no tidal wetlands; no organic soils/wetlands with water
    table manipulation.
  - Section 8 (pre-existing woody biomass): a significant NEGATIVE slope of the
    stocking-index regression from t=-10 to t=0 indicates clearing -> the proponent
    must justify it or the project is ineligible.
  - Appendix 1 Table A2: SI at >=3 time points, one in [t-10, t-8], one at t=0.
  - Appendix 1 Table A1: donor-pool GIS layers no coarser than 30 x 30 m.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

MIN_RESOLUTION_M = 30.0        # Table A1 hard floor
HISTORIC_YEARS = 10            # t = -10 .. 0
WOODY_COVER_LIMIT = 0.10       # Applicability #11a
LOSS_AREA_LIMIT = 0.01         # de-minimis clearing, fraction of AOI over the window


def si_trend(years, si):
    """OLS of SI on year over the historic window. Returns slope, p, r2, n."""
    y = np.asarray(years, dtype="float64")
    v = np.asarray(si, dtype="float64")
    ok = np.isfinite(v)
    if ok.sum() < 3:
        return dict(slope=np.nan, p_value=np.nan, r2=np.nan, n=int(ok.sum()))
    r = stats.linregress(y[ok], v[ok])
    return dict(slope=float(r.slope), p_value=float(r.pvalue),
                r2=float(r.rvalue ** 2), n=int(ok.sum()))


def check_time_points(years, si, t0):
    """Table A2: need a value in [t0-10, t0-8], one between t0-8 and t0-1, and at t0."""
    have = {int(y) for y, v in zip(years, si) if np.isfinite(v)}
    early = any(t0 - 10 <= y <= t0 - 8 for y in have)
    mid = any(t0 - 8 < y < t0 for y in have)
    now = t0 in have
    return dict(early_window=early, mid_window=mid, at_t0=now,
                passes=bool(early and mid and now), n_points=len(have))


def screen(aoi_key, years, t0, forest_frac, si_series, meta,
           forest_threshold=WOODY_COVER_LIMIT, si_name="ndfi",
           loss_threshold=LOSS_AREA_LIMIT):
    """Run the screening battery. Returns a dict of findings + an overall triage flag.

    forest_frac : {year: fraction of AOI meeting the national forest definition}
    si_series   : {year: AOI-mean stocking index}
    meta        : dict with gfc (Hansen metadata) and composites (per-year QA)
    """
    hist = [y for y in years if t0 - HISTORIC_YEARS <= y <= t0]
    si = [si_series.get(y, np.nan) for y in hist]
    ff = [forest_frac.get(y, np.nan) for y in hist]

    trend = si_trend(hist, si)
    tp = check_time_points(hist, si, t0)

    gfc = meta.get("gfc", {})
    loss_in_window = [y for y in gfc.get("loss_years", []) if t0 - HISTORIC_YEARS <= y <= t0]
    max_ff = float(np.nanmax(ff)) if np.any(np.isfinite(ff)) else np.nan

    findings = {}

    findings["non_forest_10yr"] = dict(
        test="Applicability #11a - non-forest throughout t-10..t0",
        max_forest_fraction=max_ff,
        threshold=forest_threshold,
        passes=bool(np.isfinite(max_ff) and max_ff < forest_threshold),
        note=("Census-based approach requires non-forest + <10% woody cover for 10 yr. "
              "Area-based approach may include forested land under v1.1 provided it was "
              "not managed for wood products, so a fail here is disqualifying only for "
              "the census route."),
    )

    # Area-based, not presence-based: nearly every 10 x 10 km box on Earth contains a
    # few Hansen loss pixels, so a presence test would fail every site and carry no
    # information. The methodology's concern is removal of woody biomass serving a
    # purpose comparable to the plantings, which is an area question.
    lf = {int(k): float(v) for k, v in (gfc.get("loss_frac_by_year") or {}).items()}
    lf_window = {y: v for y, v in lf.items() if t0 - HISTORIC_YEARS <= y <= t0}
    cum_loss = float(sum(lf_window.values()))
    material_years = sorted(y for y, v in lf_window.items() if v >= loss_threshold / 2)
    findings["no_recent_clearing"] = dict(
        test="Applicability #13 / VCS no-conversion rule - clearing within t-10..t0",
        cumulative_loss_fraction=round(cum_loss, 5),
        threshold=loss_threshold,
        loss_fraction_by_year={y: round(v, 5) for y, v in sorted(lf_window.items())},
        material_loss_years=material_years,
        loss_years_detected=loss_in_window,
        passes=bool(cum_loss < loss_threshold),
        note=("Hansen GFC loss area inside the 10-yr window, as a fraction of the AOI. "
              "Exceeding the threshold does not auto-disqualify: VM0047 allows "
              "justification (natural disturbance, unrelated actors, or carbon finance "
              "post-dating the clearing). Without evidence -> ineligible."),
    )

    neg_sig = bool(np.isfinite(trend["slope"]) and trend["slope"] < 0
                   and np.isfinite(trend["p_value"]) and trend["p_value"] < 0.05)
    findings["si_trend"] = dict(
        test="Section 8 - significant negative SI slope indicates prior clearing",
        index=si_name, **trend,
        significant_negative=neg_sig,
        passes=not neg_sig,
        note="Significant negative slope t-10..t0 requires the justification in Sec. 8 or the project is ineligible.",
    )

    findings["time_points"] = dict(
        test="Appendix 1 Table A2 - >=3 SI time points incl. [t-10,t-8] and t0",
        **tp,
    )

    comps = meta.get("composites", {})
    weak = sorted(y for y, m in comps.items()
                  if m.get("valid_frac") is not None and m["valid_frac"] < 0.5)
    findings["data_sufficiency"] = dict(
        test="Seasonality-controlled composite quality (SI data/parameter QA/QC)",
        season_window=meta.get("season_window"),
        years_below_50pct_valid=weak,
        passes=not weak,
        note="VM0047 requires a fixed seasonal window; persistently cloudy years need SAR or a wider window.",
    )

    findings["wetland_exclusion"] = dict(
        test="Applicability #4/#5 - tidal wetlands and organic soils",
        water_fraction=gfc.get("water_frac"),
        passes=None,
        note=("NOT decidable from optical imagery alone. Screen against Global Mangrove "
              "Watch (tidal wetlands) and SoilGrids/peat maps (organic soils) before "
              "committing. Flagged as manual."),
    )

    hard_fails = [k for k, v in findings.items() if v.get("passes") is False]
    justifiable = {"no_recent_clearing", "si_trend", "non_forest_10yr"}
    blocking = [k for k in hard_fails if k not in justifiable]

    if not hard_fails:
        triage = "PASS - proceed to feasibility"
    elif blocking:
        triage = "FAIL - data or methodology gate not met"
    else:
        triage = "CONDITIONAL - eligible only with documented justification"

    return dict(aoi=aoi_key, t0=t0, historic_window=[hist[0], hist[-1]],
                triage=triage, findings=findings,
                si_series={int(y): (None if not np.isfinite(v) else round(float(v), 4))
                           for y, v in zip(hist, si)},
                forest_fraction={int(y): (None if not np.isfinite(v) else round(float(v), 4))
                                 for y, v in zip(hist, ff)})
