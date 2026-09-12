"""Annual, season-matched surface-reflectance composites from open STAC archives.

VM0047 requires the SI time series to control for seasonality ("setting a target data
collection period at the project start and collecting all monitoring imagery from
within that period"), so every year is composited from the SAME month window.
"""
from __future__ import annotations

import os
import time

import numpy as np

# Long multi-year runs hit transient blob-store errors and SAS-token edges; let GDAL
# retry at the HTTP layer before we retry at the scene layer.
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
import planetary_computer as pc
import pystac_client
from odc.stac import load as odc_load

PC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Landsat Collection 2 Level-2 is the backbone: 30 m (exactly VM0047's resolution
# floor for donor-pool layers), uniform global coverage 2013->present, so a full
# t-10 -> t=0 window is available everywhere in both regions.
LANDSAT = dict(
    collection="landsat-c2-l2",
    assets={"blue": "blue", "green": "green", "red": "red",
            "nir": "nir08", "swir1": "swir16", "swir2": "swir22", "qa": "qa_pixel"},
    resolution=30,
    deg=0.00027,                   # ~30 m in degrees
    scale=2.75e-05, offset=-0.2,   # C2 SR -> reflectance
)
# Sentinel-2 L2A: 10 m, 2016->present on Planetary Computer (note: the AWS
# Collection-1 mirror does NOT carry 2016-2017, so PC is the right source here).
SENTINEL2 = dict(
    collection="sentinel-2-l2a",
    assets={"blue": "B02", "green": "B03", "red": "B04",
            "nir": "B08", "swir1": "B11", "swir2": "B12", "qa": "SCL"},
    resolution=10,
    deg=0.00009,                   # ~10 m in degrees
    scale=1e-4, offset=0.0,
)
SENSORS = {"landsat": LANDSAT, "sentinel2": SENTINEL2}

SEASON_ANCHOR = "season"


def season_range(year: int, months: tuple[int, int]) -> tuple[str, str]:
    """Month window, wrapping across the new year when start > end (dry seasons do)."""
    m0, m1 = months
    if m0 <= m1:
        start, end_y, end_m = f"{year}-{m0:02d}-01", year, m1
    else:
        start, end_y, end_m = f"{year - 1}-{m0:02d}-01", year, m1
    last = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
            7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[end_m]
    if end_m == 2 and end_y % 4 == 0 and (end_y % 100 != 0 or end_y % 400 == 0):
        last = 29
    return start, f"{end_y}-{end_m:02d}-{last:02d}"


def _landsat_clear(qa):
    """QA_PIXEL: drop dilated cloud(1), cirrus(2), cloud(3), shadow(4), snow(5)."""
    q = qa.astype("uint16")
    bad = np.zeros(q.shape, dtype=bool)
    for bit in (1, 2, 3, 4, 5):
        bad |= ((q >> bit) & 1).astype(bool)
    return (~bad) & (q != 0)


def _s2_clear(scl):
    """SCL: keep vegetation(4), bare(5), water(6), unclassified(7)."""
    return np.isin(scl.astype("uint8"), [4, 5, 6, 7])


def annual_composite(bbox, year, months, sensor="landsat", max_cloud=80, chunk=2048,
                     max_scenes=12):
    """Cloud-masked median reflectance composite (x10000) for one season-year.

    Returns (bands_dict, meta). bands_dict values are float32 arrays; meta carries
    scene count, clear-pixel fraction and the exact date window (audit trail).
    """
    cfg = SENSORS[sensor]
    start, end = season_range(year, months)
    cat = pystac_client.Client.open(PC_URL, modifier=pc.sign_inplace)
    items = list(cat.search(
        collections=[cfg["collection"]], bbox=bbox, datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).items())
    n_found = len(items)
    # Composite the least-cloudy scenes in the window. Caps cost for portfolio-scale
    # screening; a median over ~12 clear scenes is stable. Raise for validation runs.
    items = sorted(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:max_scenes]
    meta = dict(year=year, window=f"{start}..{end}", n_found=n_found,
                n_scenes=len(items), sensor=sensor,
                scene_cloud=[round(i.properties.get("eo:cloud_cover", float("nan")), 1)
                             for i in items])
    if not items:
        return None, meta

    ds, last_err = None, None
    for attempt in range(3):
        try:
            ds = odc_load(
                items, bbox=bbox, bands=list(cfg["assets"].values()),
                resolution=cfg["deg"], crs="EPSG:4326",
                chunks={"x": chunk, "y": chunk}, groupby="solar_day",
            ).compute()
            break
        except Exception as exc:                      # transient blob/COG read failures
            last_err = exc
            time.sleep(3 * (attempt + 1))
            # Re-sign: SAS tokens can expire during a long multi-year run.
            cat = pystac_client.Client.open(PC_URL, modifier=pc.sign_inplace)
            items = list(cat.search(
                collections=[cfg["collection"]], bbox=bbox, datetime=f"{start}/{end}",
                query={"eo:cloud_cover": {"lt": max_cloud}},
            ).items())
            items = sorted(items, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:max_scenes]
            if attempt == 1 and len(items) > 3:
                items = items[:max(3, len(items) // 2)]   # shed the likely-bad scene
    if ds is None:
        meta["error"] = f"{type(last_err).__name__}: {str(last_err)[:160]}"
        return None, meta

    qa_name = cfg["assets"]["qa"]
    qa = ds[qa_name].values
    clear = _landsat_clear(qa) if sensor == "landsat" else _s2_clear(qa)
    meta["clear_frac"] = float(clear.mean())

    bands = {}
    for name, asset in cfg["assets"].items():
        if name == "qa":
            continue
        raw = ds[asset].values.astype("float32")
        raw[raw == 0] = np.nan
        refl = raw * cfg["scale"] + cfg["offset"]
        refl = np.where(clear, refl, np.nan)
        with np.errstate(invalid="ignore"):
            bands[name] = np.nanmedian(refl, axis=0).astype("float32") * 10000.0
    meta["valid_frac"] = float(np.isfinite(bands["red"]).mean())
    # odc-stac names geographic dims latitude/longitude, projected ones y/x.
    ydim = "latitude" if "latitude" in ds.coords else "y"
    xdim = "longitude" if "longitude" in ds.coords else "x"
    ys, xs = ds[ydim].values, ds[xdim].values
    half = cfg["deg"] / 2.0
    grid = dict(crs="EPSG:4326", shape=[len(ys), len(xs)],
                bounds=[float(xs.min() - half), float(ys.min() - half),
                        float(xs.max() + half), float(ys.max() + half)])
    return bands, {**meta, "grid": grid}


def month_availability(bbox, years, sensor="landsat", max_cloud=100):
    """Scene count and mean cloud cover by calendar month -- evidence for choosing
    the season window VM0047 asks you to fix at project start."""
    cfg = SENSORS[sensor]
    cat = pystac_client.Client.open(PC_URL, modifier=pc.sign_inplace)
    items = list(cat.search(
        collections=[cfg["collection"]], bbox=bbox,
        datetime=f"{min(years)}-01-01/{max(years)}-12-31",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).items())
    per = {m: [] for m in range(1, 13)}
    for it in items:
        m = int(it.properties["datetime"][5:7])
        per[m].append(it.properties.get("eo:cloud_cover", np.nan))
    return {m: dict(n=len(v), mean_cloud=float(np.nanmean(v)) if v else float("nan"))
            for m, v in per.items()}
