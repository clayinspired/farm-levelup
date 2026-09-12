# Satellite data for VM0047 land-eligibility screening — SE Asia & Africa

Scope: annual (1-year increment) coverage for a 10-year look-back window, both regions,
verified available as of 2026-09-12.

## What VM0047 actually forces on the data choice

These are not preferences — they are constraints from the methodology text
(v1.0 §4, §8, App. 1 Tables A1/A2; v1.1 dated 2025-05-14):

| Requirement | Source | Consequence for data |
|---|---|---|
| Geospatial layers for donor-pool delineation **no coarser than 30 × 30 m** | App. 1, Table A1 | Rules out MODIS (250–500 m), ESA CCI LC (300 m), most global biomass products |
| SI at **≥3 time points**, one in `[t−10, t−8]`, one at `t=0`; monitored **at least annually** | Table A2, §10.5 | Needs a *uniform* archive spanning the full decade — a sensor that starts mid-window can't anchor `t−10` |
| **Seasonality must be minimised** — fix a target collection period at project start, prefer lowest-cloud months | §10.5 | Composite the *same month window* every year; per-month cloud statistics needed to choose it |
| SI must be a metric with **published correlation to AGB**, validated with local field data | §10.5 QA/QC | NDFI (the methodology's own example), canopy height, or % canopy cover — not an arbitrary index |
| Significant **negative SI slope** `t−10 → t=0` ⇒ prior clearing ⇒ justify or **ineligible** | §8 | The 10-year series is itself a disqualification test, not just context |
| Plot polygons **0.09 ha (30×30 m) to 10 ha**, equal size | §10.5 | 30 m pixels are the natural minimum unit |
| Census route: **non-forest for 10 years, <10% woody cover** | §4 #11a | Needs an annual forest/non-forest label, per *host-country* forest definition |
| Ineligible if comparable woody biomass **removed in last 10 years** | §4 #13 | Needs annual disturbance dates |
| **No tidal wetlands**; no organic soils/wetlands with water-table manipulation | §4 #4, #5 | Needs mangrove + peat layers; not decidable from optical imagery |

Note the v1.0 → v1.1 change: the blanket "non-forest for 10 years" rule is an applicability
condition of the **census-based** approach. v1.1 permits **area-based** activities on forested
land provided it "has not been managed for wood products." So a forested AOI is not
automatically dead — it changes which route you can take.

## Recommended stack

### Tier 1 — the 10-year backbone

**Landsat Collection 2 Level-2 (surface reflectance), 30 m, 2013–present.**
This is the primary recommendation. It is the *only* free optical archive that covers the
entire `t−10 → t=0` window uniformly across both regions, and 30 m is exactly VM0047's
resolution floor. Verified scene counts over test AOIs: ~45–70 scenes/AOI/year, every year
2016–2026, in both Indonesia and Kenya.

- Planetary Computer STAC: `landsat-c2-l2` @ `https://planetarycomputer.microsoft.com/api/stac/v1` (anonymous)
- AWS Earth Search: `landsat-c2-l2` @ `https://earth-search.aws.element84.com/v1/search` (anonymous)
- Earth Engine: `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2`, `LANDSAT/LE07/C02/T1_L2`
- Supports NDFI directly — Souza et al. (2005) defined it on Landsat, and VM0047 cites that paper.

### Tier 2 — higher resolution, shorter or patchier history

**Sentinel-2 L2A, 10 m, 2016–present.** Use for `t−8 → t=0` detail and for sub-hectare
plot delineation. Source matters:
- **Planetary Computer `sentinel-2-l2a` — has 2016 and 2017.** Verified.
- **AWS `sentinel-2-c1-l2a` — does NOT have 2016–2017** (returns zero scenes for both test
  AOIs). Use PC if you need the early years.

**Planet NICFI basemaps, 4.77 m, Dec 2015 – Aug 2026.** Free for non-commercial tropical
forest monitoring, sign-up required. Biannual mosaics 2015-2020, monthly from Sep 2020.
Covers both regions exactly (`projects/planet-nicfi/assets/basemaps/asia` and `/africa` in
Earth Engine). Best product for visual confirmation of pre-existing woody biomass and for
the "pre-project photos" style evidence VM0047 §4 #13 asks for. Contrary to widely-repeated
claims that the programme ended Jan 2025, the Earth Engine collections are still being
updated through Aug 2026 — but treat continuity as a programme risk, not a guarantee.

**Sentinel-1 SAR GRD, 10 m, 2014–present.** Not optional in Southeast Asia. Measured mean
cloud cover over the Kalimantan test AOI is 57–71% in *every* month — there is no clear
season. C-band backscatter (VV/VH) is cloud-independent and VH correlates with AGB in the
low-biomass range that ARR projects live in. Note the S1B failure (Dec 2021–2023) thinned
revisit before S1C.

### Tier 3 — annual forest/non-forest labels (the eligibility test itself)

**Hansen Global Forest Change v1.13 (2000–2025), 30 m.** The workhorse. `treecover2000` +
`lossyear` (1–25 ⇒ 2001–2025) + `gain` reconstructs a per-year forest mask at any crown-cover
threshold, so you can apply the *host-country* forest definition rather than a global default.
Tiles are 10°×10°, named by **top-left** corner, striped GeoTIFF — windowed HTTP reads work
over `/vsicurl` without downloading the full ~200 MB tile.
`https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/`
Caveat: loss ends 2025, so a 2026 project start has a 1-year tail to fill from imagery.

**JRC Tropical Moist Forest v1.2025, 30 m, 1990–2025.** `projects/JRC/TMF/v1_2025/AnnualChanges`.
Better than Hansen for the *degradation vs. deforestation* distinction and for regrowth dating,
and it explicitly reaches back 35 years — useful for showing land was non-forest well before
`t−10`. Pan-tropical, so it covers both regions but **only the moist forest domain** — it does
not cover the Guinea savanna, miombo, or dryland Africa sites where a lot of ARR happens.

**GLAD Global Land Cover & Land Use, 30 m.** Two products worth separating:
- **GLCLUC2020 (2000–2020)** — 5-year epochs (2000/2005/2010/2015/2020), 30 m, includes a
  **forest height** layer calibrated to GEDI. Not annual, but the height layer is directly
  usable as a VM0047 stocking index (canopy height is one of the methodology's named
  acceptable metrics) and is the cleanest evidence for "<10% pre-existing woody biomass."
  `https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/download.html`
- **GLCLU v2 — annual maps, 30 m, 2000–2020 only.** Genuinely annual land cover, verified
  live as STAC collection `glad-glclu2020-v2` at `https://stac.maap-project.org` (temporal
  extent confirmed 2000-01-01 → 2020-12-31). Best annual ≤30 m land-cover record for the
  **non-moist-forest** parts of Africa — Guinea savanna, miombo, Sahel — where JRC TMF has no
  coverage at all. **Caveat: it stops at 2020.** For a 2026 project start it covers only
  `t−10 … t−6`, so it supplements Hansen for the early half of the window and cannot carry
  the recent years. Do not treat it as a full-decade source.

**ESA WorldCover, 10 m, 2020 and 2021 only.** Two snapshots, not a time series. Use as an
independent cross-check on the land-cover class, not as the annual record.

**Dynamic World, 10 m, 2015–present, near-real-time.** Per-Sentinel-2-scene land cover
probabilities; take the annual mode for a 10 m annual series. Noisier than Hansen year to
year but 10 m and genuinely annual.

### Tier 4 — the exclusion layers you cannot get from optical imagery

- **Global Mangrove Watch (v3+, 1996–2020, 25 m)** — tidal wetlands, VM0047 §4 #4. Mandatory
  screen for coastal SE Asia and East/West Africa.
- **SoilGrids 2.0 / Global Peatland Map / PEATMAP** — organic soils, §4 #5.
- **RESOLVE Ecoregions 2017** — biome-level ecoregion for donor-pool exclusion (Table A1) and
  for the ecoregion within which SI field validation must be collected.
- **GADM / national admin boundaries** — but Table A1 requires an *official government source*
  for the jurisdictional boundary, so GADM is for prototyping only.
- **Verra / Gold Standard registry KMLs** — optional exclusion of existing AFOLU projects.
- **Canopy height**: Potapov et al. 2021 (30 m, GEDI+Landsat), Lang et al. 2022 (10 m),
  Tolan et al. 2023 (1 m, Meta/WRI). Canopy height is one of VM0047's named acceptable SI
  metrics and is the cleanest way to evidence "<10% pre-existing woody biomass."

## What to skip and why

| Dataset | Why not |
|---|---|
| MODIS VCF / MOD13 | 250–500 m, below the Table A1 floor |
| ESA CCI Land Cover | 300 m, below the floor |
| Global Forest Watch "integrated alerts" | Sub-annual alerts, not an annual state record; useful for monitoring, not for the historic baseline |
| Commercial VHR archives (Maxar, Airbus) | Excellent for a final visual check but unaffordable for portfolio screening and no free 10-year annual stack |
| GEDI L4A footprints | Sparse samples, not wall-to-wall; useful for *validating* an SI, not for the series itself |

## Access paths, ranked by friction

1. **STAC + COG windowed reads (no account at all).** Planetary Computer and AWS Earth Search
   are anonymous. This is what the pipeline in this repo uses — it worked from a cold start
   with zero credentials.
2. **Google Earth Engine.** Best for continent-scale screening and the only easy route to
   NICFI and JRC TMF. Requires a registered Cloud project; noncommercial is free, commercial
   use needs a paid plan — relevant, since a carbon project is commercial.
3. **Direct HTTPS** for Hansen GFC tiles. No account.
4. **openEO / Copernicus Data Space** as a Sentinel fallback if PC quotas bite.

## Regional gotchas found in testing

- **Southeast Asia is cloud-limited, not data-limited.** Kalimantan test AOI: mean cloud
  57–71% in all 12 months. Annual optical composites will have gaps in bad years; budget for
  Sentinel-1 fusion or accept wider (5–6 month) windows and document the seasonality trade-off.
- **East Africa has a usable dry season.** Kenya test AOI: 25–30% mean cloud in Dec–Feb.
  A 3-month window is comfortable.
- **Hansen tiles are named by top-left corner**, so an AOI at 0.5°N sits in `10N_110E`, not
  `00N_110E`. Easy and silent way to read an all-nodata window.
- **Hansen `gain` is undated (2000–2012)** — it cannot be assigned to a year, so it can't
  support a precise "non-forest in year X" claim on its own.
