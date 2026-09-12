"""End-to-end: pull 10+ years of season-matched imagery for an AOI and screen it."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vm0047.aois import SAMPLE_AOIS
from vm0047.hansen import annual_forest
from vm0047.indices import all_indices
from vm0047.stac import annual_composite, month_availability


def best_season(bbox, years, sensor="landsat", length=3):
    """Pick the contiguous month window with the lowest mean cloud -- the evidence
    base for fixing the target collection period VM0047 requires."""
    av = month_availability(bbox, years, sensor=sensor)
    best, best_score = None, np.inf
    for m0 in range(1, 13):
        months = [((m0 - 1 + i) % 12) + 1 for i in range(length)]
        vals = [av[m]["mean_cloud"] for m in months if av[m]["n"] > 0]
        if len(vals) < length:
            continue
        score = float(np.mean(vals))
        if score < best_score:
            best, best_score = (months[0], months[-1]), score
    return best, best_score, av


def run_aoi(key, aoi, t0, n_years=10, sensor="landsat", canopy_threshold=30,
            season=None, outdir=Path("out"), max_scenes=12):
    years = list(range(t0 - n_years, t0 + 1))
    bbox = aoi["bbox"]
    print(f"\n=== {key} ({aoi['country']}) bbox={bbox} t0={t0} ===", flush=True)

    if season is None:
        season, cloud, _ = best_season(bbox, years, sensor=sensor)
        print(f"  season window auto-selected: months {season} (mean cloud {cloud:.0f}%)", flush=True)

    cache = outdir / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    print(f"  Hansen GFC v1.13 annual forest reconstruction (canopy >= {canopy_threshold}%)...", flush=True)
    forest, gfc_meta = annual_forest(bbox, years, canopy_threshold=canopy_threshold)
    forest_frac = {y: v["forest_frac"] for y, v in forest.items()}

    si_series, comp_meta, layers, grid = {}, {}, {}, None
    for y in years:
        tag = f"{key}_{sensor}_{season[0]}-{season[1]}_{max_scenes}_{y}"
        cf = cache / f"{tag}.npz"
        if cf.exists():
            z = np.load(cf, allow_pickle=True)
            meta = json.loads(str(z["meta"]))
            # Trust the arrays, not the scene count: a year whose scenes were found but
            # whose reads all failed caches metadata with n_scenes > 0 and no arrays.
            if all(k in z.files for k in ("ndfi", "ndvi", "ndmi")):
                layers[y] = {k: z[k] for k in ("ndfi", "ndvi", "ndmi")}
                si_series[y] = float(np.nanmean(layers[y]["ndfi"]))
                grid = grid or meta.get("grid")
            else:
                si_series[y] = np.nan
            comp_meta[y] = {k: v for k, v in meta.items() if k != "grid"}
            print(f"  {y}: cached  NDFI={si_series[y]:+.3f}  forest={forest_frac[y]:.3f}", flush=True)
            continue

        bands, meta = annual_composite(bbox, y, season, sensor=sensor, max_scenes=max_scenes)
        if bands is None:
            print(f"  {y}: no scenes in window", flush=True)
            comp_meta[y] = meta
            si_series[y] = np.nan
            np.savez_compressed(cf, meta=json.dumps(meta, default=str))
            continue
        idx = all_indices(bands)
        si_series[y] = float(np.nanmean(idx["ndfi"]))
        layers[y] = {k: idx[k].astype("float32") for k in ("ndfi", "ndvi", "ndmi")}
        grid = grid or meta.get("grid")
        comp_meta[y] = {k: v for k, v in meta.items() if k != "grid"}
        np.savez_compressed(cf, meta=json.dumps(meta, default=str), **layers[y])
        print(f"  {y}: {meta['n_scenes']:2d}/{meta.get('n_found',0):3d} scenes  "
              f"clear={meta.get('clear_frac',0):.2f}  valid={meta.get('valid_frac',0):.2f}  "
              f"NDFI={si_series[y]:+.3f}  NDVI={np.nanmean(idx['ndvi']):+.3f}  "
              f"forest={forest_frac[y]:.3f}", flush=True)

    from vm0047.screen import screen
    report = screen(key, years, t0, forest_frac, si_series,
                    meta=dict(gfc=gfc_meta, composites=comp_meta,
                              season_window=f"months {season[0]}-{season[1]}"))
    report["aoi_meta"] = dict(country=aoi["country"], note=aoi["note"], bbox=list(bbox),
                              sensor=sensor, canopy_threshold=canopy_threshold,
                              season=list(season))
    report["gfc"] = {k: v for k, v in gfc_meta.items() if k != "profile"}
    report["composites"] = {int(y): m for y, m in comp_meta.items()}
    report["grid"] = grid

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{key}_report.json").write_text(json.dumps(report, indent=2, default=str))

    # Georeferenced stack for the map: NDFI + Hansen forest mask, per year.
    stack = {f"ndfi_{y}": layers[y]["ndfi"] for y in layers}
    stack.update({f"forest_{y}": forest[y]["forest_mask"].astype("uint8") for y in years})
    np.savez_compressed(outdir / f"{key}_stack.npz",
                        bbox=np.array(bbox, dtype="float64"),
                        grid=json.dumps(grid or {}), years=np.array(years), **stack)
    print(f"  -> {report['triage']}", flush=True)
    for name, f in report["findings"].items():
        mark = {True: "PASS", False: "FAIL", None: "MANUAL"}[f.get("passes")]
        print(f"     [{mark:6s}] {name}", flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description="VM0047 land-eligibility screening")
    ap.add_argument("--aoi", nargs="*", default=list(SAMPLE_AOIS), help="AOI keys")
    ap.add_argument("--t0", type=int, default=2026, help="project start year")
    ap.add_argument("--years", type=int, default=10, help="historic years before t0")
    ap.add_argument("--sensor", default="landsat", choices=["landsat", "sentinel2"])
    ap.add_argument("--canopy-threshold", type=int, default=30,
                    help="host-country forest definition crown cover %%")
    ap.add_argument("--season", type=int, nargs=2, default=None, metavar=("M0", "M1"))
    ap.add_argument("--max-scenes", type=int, default=12,
                    help="least-cloudy scenes per year to composite")
    ap.add_argument("--outdir", type=Path, default=Path("out"))
    a = ap.parse_args()

    reports = []
    for key in a.aoi:
        if key not in SAMPLE_AOIS:
            print(f"unknown AOI {key}", file=sys.stderr); continue
        reports.append(run_aoi(key, SAMPLE_AOIS[key], a.t0, a.years, a.sensor,
                               a.canopy_threshold, tuple(a.season) if a.season else None,
                               a.outdir, a.max_scenes))
    (a.outdir / "summary.json").write_text(json.dumps(
        [{k: r[k] for k in ("aoi", "triage", "si_series", "forest_fraction")} for r in reports],
        indent=2))
    print(f"\nWrote {len(reports)} reports to {a.outdir}/")


if __name__ == "__main__":
    main()
