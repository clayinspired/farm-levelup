# farm-levelup — VM0047 land screening

Can a piece of land earn reforestation carbon credits under **Verra VM0047**? This
answers that from ten years of satellite history, across Southeast Asia and Africa.

A Telegram bot takes a location and answers with an eligibility verdict and an honest
estimate of what the carbon is actually worth; a companion site carries the screening map
and a page for drawing a field boundary.

Deployment hostnames are not in this repo — they live in `.env` and `site/config.js`,
both gitignored. See `.env.example` and `site/config.example.js`.

- **Mirrors:** two remotes — `origin`, the public copy under a neutral name, and
  `forgejo`, the private copy named to the house `YYYY-MM-DD_<domain>` convention. Keep
  them in step with `git push origin master && git push forgejo master`; history is
  deliberately a single commit, so both are amend-and-force.
- **Catalogue:** [DATA_CATALOG.md](DATA_CATALOG.md) — the dataset survey and why each
  source was chosen or rejected against the methodology's hard constraints

## Layout

```
src/vm0047/      research pipeline: annual composites, NDFI, Hansen, screening tests
gee/             Earth Engine script for portfolio-scale screening
service/         deployed Fly app: Telegram bot + plot store (one process)
site/            static site (landing, screening map, drawing page)
scripts/         deploy + local serve
```

`src/vm0047` is the single source for the Hansen reconstruction — the container image
copies it in rather than keeping a second copy, so the bot and the pipeline cannot drift.

## Run

```bash
uv sync

# research: screen a site and rebuild the map data
uv run python src/vm0047/run.py --aoi ne-zinder --t0 2026 --years 10
uv run python src/vm0047/export_web.py          # -> site/map/data/

./scripts/serve-local.sh                        # review the site locally / on the tailnet
./scripts/deploy-site.sh                        # -> Cloudflare Pages
./scripts/deploy-service.sh                     # -> Fly (bot + plot store)

# see what farmers actually submit
./scripts/watch-plots.py                        # follow new fields live
./scripts/watch-plots.py --all                  # everything stored
./scripts/watch-plots.py --geojson > plots.geojson
```

## Editing on a remote machine

The pipeline needs the machine's own network and disk, so it is usually edited in place
over SSH rather than cloned. In VS Code, install **Remote - SSH**, add a host entry:

```
Host farm
  HostName <host or private-network address>
  User <user>
```

then **Remote-SSH: Connect to Host…** and open the repo directory.

## Sample-set results (t0 = 2026, 19 sites)

```
Country       Site                   maxForest  cleared   SIslope      p crown  verdict
Burkina Faso  bf-centre                   0.5%    0.04%   +0.0068  0.002   10%  PASS
Ethiopia      et-tigray                   0.1%    0.00%   +0.0211  0.011   10%  PASS
Ghana         gh-northern                 0.0%    0.01%   -0.0009  0.877   30%  PASS
Indonesia     id-sumba                    9.7%    0.27%   +0.0020  0.912   10%  PASS
Laos          la-savannakhet              6.2%    0.89%   +0.0165  0.023   10%  PASS
Myanmar       mm-magway                   0.1%    0.00%   +0.0111  0.337   10%  PASS
Niger         ne-zinder                   0.0%    0.00%   +0.0128  0.001   10%  PASS
Senegal       sn-kaffrine                 0.0%    0.00%   +0.0014  0.366   10%  PASS
South Africa  za-limpopo                  0.1%    0.00%   +0.0337  0.154   10%  PASS
Tanzania      tz-tabora                   0.1%    0.61%   +0.0176  0.154   30%  PASS
Tanzania      tz-shinyanga                5.2%    0.03%   +0.0239  0.065   10%  PASS
Thailand      th-isaan                    0.3%    0.03%   +0.0179  0.047   10%  PASS
Vietnam       vn-ninh-thuan               2.3%    0.47%   +0.0291  0.073   10%  PASS
Cambodia      kh-mondulkiri              70.4%   19.60%   -0.0026  0.650   30%  CONDITIONAL
Indonesia     id-east-kalimantan         50.5%   30.54%   -0.0064  0.446   30%  FAIL
Kenya         ke-makueni                 31.9%    0.51%   +0.0277  0.281   10%  CONDITIONAL
Kenya         ke-western                 29.1%    2.66%   +0.0210  0.160   30%  CONDITIONAL
Mozambique    mz-zambezia                61.5%    7.51%   +0.0126  0.448   30%  CONDITIONAL
Vietnam       vn-central-highlands       39.0%    8.75%   +0.0047  0.485   30%  CONDITIONAL
```

13 eligible, 5 conditional, 1 fail. The eligible set is dominated by dryland and savanna
systems — Sahel parkland, miombo enclosures, semi-arid scrub, and Southeast Asia's dry
corridor. That is not an accident of site selection: humid-tropical candidates fail either on
residual forest cover or on cloud, which is the central practical finding of this exercise.

Niger/Zinder is worth a look as a sanity check — it returns a significantly **positive** SI
trend (+0.0128/yr, p = 0.001) over land with 0% forest cover and zero detected clearing,
which is the well-documented farmer-managed natural regeneration re-greening showing up
independently in the imagery.

## Economics, and where the numbers come from

`service/app/revenue.py` holds every assumption in one place. They are indicative, not
quotes, and they are deliberately sourced rather than guessed:

| Input | Value (low / central / high) | Basis |
|---|---|---|
| Removal rate, agroforestry | 3 / 6 / 10 tCO₂e/ha/yr | published tropical ARR 11.7–36.6 tCO₂e/ha/yr; agroforestry 10.8–15.6 over the first 20 years; 10 widely used as a planning baseline |
| Removal rate, leaf-intensive | 0.5 / 1.2 / 2.5 | repeated coppicing retains little standing stock |
| Price | $12 / $28 / $45 per tCO₂e | Sylvera H1 2026: BBB-or-higher ARR averaged $28.55 against $9.12 for BB-or-lower; top-rated ARR quoted €25–45. VM0047 v1.1 is the first ARR methodology with the ICVCM CCP label |
| Buffer | 15% | VCS non-permanence pool |
| Developer share | 30–65% | typical grouped-project splits |
| Certification | ~$345k over 30 years | PDD, validation and ~7 verifications |

Which lands at roughly **$70 per hectare per year** to the farmer, break-even near
**81 hectares**, and about **$35,000 a year** across a 500-hectare group.

Two things worth keeping honest when these are revised: moringa leaf and seed income
(~$1,200/ha/yr central) dwarfs the carbon, and leaf-intensive management cuts the carbon
by roughly five times. The tool is built to say both out loud.

## Two design decisions worth knowing

**The clearing test is area-based, not presence-based.** Hansen GFC marks a handful of loss
pixels in almost any 10 × 10 km box on Earth, so a test that fires on *any* loss pixel fails
every site and carries zero information — the first version of this tool did exactly that and
returned CONDITIONAL for seven sites out of seven. The test now compares cumulative loss area
over the window against a de-minimis threshold (`LOSS_AREA_LIMIT`, default 1% of the AOI) and
reports the per-year loss fraction, which is also what §4 #13 is actually about: removal of
woody biomass serving a purpose comparable to the plantings.

**Set `--canopy-threshold` to the host country's forest definition.** This single number
decides the non-forest test, and the default of 30% is a placeholder, not a recommendation.
Many African and Asian definitions use the FAO 10% crown-cover minimum; screening a dryland
site at 30% will call almost anything non-forest and manufacture a pass. The dryland sites in
the sample set are deliberately run at `--canopy-threshold 10` so their result survives the
stricter definition.

## Scope and limits — read before using this on a real deal

This is a **screening** tool. It narrows a pipeline to sites worth paying for a feasibility
study. It is not a validation-grade eligibility determination. Before anything is
representable to a VVB you still need:

1. **The host-country forest definition** (crown cover, minimum height, minimum area). The
   `--canopy-threshold` default of 30% is a placeholder, and minimum-height and
   minimum-area criteria are not implemented at all.
2. **Field validation of the stocking index.** §10.5 requires the SI to have a published
   AGB correlation *and* be validated against direct measurements from within the project
   ecoregion. NDFI has the literature; the local validation is on you.
3. **The host-country minimum height and minimum area criteria.** Only crown cover is
   implemented.
4. **Land tenure and policy-environment layers** (Table A1) — these must come from official
   government sources and gate the donor pool. Not implemented.
5. **Mangrove and peat screening** (§4 #4/#5) — Global Mangrove Watch and a peat map.
   Currently reported as MANUAL.
6. **The donor pool and matching** itself (App. 1 Steps 1–3: 100 km radius, ecoregion, k-NN
   on the SI covariate vector, standardised-difference match quality). This repo builds the
   SI time series those steps consume, but does not run the matching.

The SMA unmixing behind NDFI uses a fast sum-to-one constrained least squares with clipping
rather than per-pixel NNLS. Fine for triage; swap in `scipy.optimize.nnls` for a defensible run.

Hansen GFC v1.13 loss data ends in **2025**, so a `t0` of 2026 has a one-year tail that the
forest reconstruction cannot see. The imagery-based SI series does cover it.

**The season auto-picker fights the stocking index in deciduous systems.** `best_season`
minimises cloud, which in savanna and dry-forest lands on the peak dry season — exactly when
the canopy is senesced or burnt. The Ghana Guinea-savanna site returns a mean NDFI of −0.83
in its Dec–Feb window: that is a real measurement of a real dry-season surface, but it tracks
phenology and fire, not standing biomass. VM0047 §10.5 asks for a window with *minimal
seasonal phenological variation* **and** low cloud; where those conflict, cloud should not win
automatically. For deciduous sites, set `--season` by hand to a green-up window and accept the
cloud penalty, or use a phenology-robust index (canopy height, SAR backscatter) instead.

## Layout

```
src/vm0047/
  aois.py      sample AOIs across SE Asia + Africa (replace with real polygons)
  stac.py      season-matched annual composites from Planetary Computer
  indices.py   NDVI / NDMI / NBR / NDFI (Souza et al. 2005 spectral unmixing)
  hansen.py    annual forest/non-forest from Hansen GFC v1.13
  screen.py    the VM0047 test battery
  run.py       CLI
```

## References

- VM0047 Afforestation, Reforestation and Revegetation — v1.0 (2023-09-21), v1.1 (2025-05-14), Verra
- Souza et al. (2005), *Remote Sensing of Environment* 98(2–3):329–343 — NDFI
- Hansen et al. (2013), *Science* 342:850–853 — Global Forest Change
