"""Annual tree-cover reconstruction from Hansen Global Forest Change v1.13 (2000-2025).

GFC gives treecover2000 (%), lossyear (1-25 => 2001-2025) and gain. Combining them
yields a per-pixel, per-year forest/non-forest label at 30 m -- the standard evidence
for VM0047's "non-forest for the past ten years" test and for the VCS Standard's
no-conversion-of-native-ecosystems-within-10-years rule.

Tiles are 10x10 degree, named by TOP-LEFT corner, striped (not COG) but readable
by window over /vsicurl.
"""
from __future__ import annotations

import math
import numpy as np
import rasterio
from rasterio.windows import from_bounds

BASE = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13"
VERSION = "GFC-2025-v1.13"
LAYERS = ("treecover2000", "lossyear", "gain", "datamask")


def tile_name(lon: float, lat: float) -> str:
    """Top-left corner of the 10x10 deg tile containing (lon, lat)."""
    top = math.ceil(lat / 10.0) * 10
    left = math.floor(lon / 10.0) * 10
    ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
    ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
    return f"{ns}_{ew}"


def tiles_for_bbox(bbox):
    w, s, e, n = bbox
    out = []
    lat = s
    while lat <= n + 1e-9:
        lon = w
        while lon <= e + 1e-9:
            t = tile_name(lon, lat)
            if t not in out:
                out.append(t)
            lon += 10.0
        lat += 10.0
    # include the exact corners
    for lon, lat in ((w, n), (e, n), (w, s), (e, s)):
        t = tile_name(lon, lat)
        if t not in out:
            out.append(t)
    return out


def read_layers(bbox, layers=LAYERS):
    """Windowed read of GFC layers over bbox, mosaicking across tiles when the AOI
    straddles a 10-degree boundary (common for real project polygons)."""
    tiles = tiles_for_bbox(bbox)
    if len(tiles) == 1:
        out, profile = {}, None
        for lyr in layers:
            url = f"/vsicurl/{BASE}/Hansen_{VERSION}_{lyr}_{tiles[0]}.tif"
            with rasterio.open(url) as src:
                win = from_bounds(*bbox, src.transform)
                out[lyr] = src.read(1, window=win)
                if profile is None:
                    profile = dict(transform=src.window_transform(win), crs=src.crs,
                                   tile=tiles[0])
        return out, profile

    # Multi-tile: build the destination grid from the bbox on the native GFC
    # resolution (40000 px per 10 deg = 0.00025 deg) and paste each tile's window in.
    w, s_, e, n = bbox
    res = 10.0 / 40000.0
    width = int(round((e - w) / res))
    height = int(round((n - s_) / res))
    transform = rasterio.transform.from_origin(w, n, res, res)

    out = {}
    for lyr in layers:
        dest = np.zeros((height, width), dtype="uint8")
        for tile in tiles:
            url = f"/vsicurl/{BASE}/Hansen_{VERSION}_{lyr}_{tile}.tif"
            with rasterio.open(url) as src:
                tb = src.bounds
                ow, oe = max(w, tb.left), min(e, tb.right)
                os_, on = max(s_, tb.bottom), min(n, tb.top)
                if ow >= oe or os_ >= on:
                    continue
                win = from_bounds(ow, os_, oe, on, src.transform)
                data = src.read(1, window=win)
                col = int(round((ow - w) / res))
                row = int(round((n - on) / res))
                h, wd = data.shape
                h = min(h, height - row); wd = min(wd, width - col)
                if h > 0 and wd > 0:
                    dest[row:row + h, col:col + wd] = data[:h, :wd]
        out[lyr] = dest
    return out, dict(transform=transform, crs=rasterio.crs.CRS.from_epsg(4326),
                     tile="+".join(tiles))


def annual_forest(bbox, years, canopy_threshold=30):
    """Per-year boolean forest mask and tree-cover stats.

    canopy_threshold: crown-cover % of the HOST COUNTRY forest definition. VM0047
    defers to the national definition, so this must be set per country, not assumed.
    Gain (2000-2012, undated) is credited from 2013 onward only where no later loss.
    """
    lyr, profile = read_layers(bbox)
    tc0 = lyr["treecover2000"].astype("float32")
    loss = lyr["lossyear"].astype("int16")      # 0 = none, 1..25 => 2001..2025
    gain = lyr["gain"].astype(bool)
    data = lyr["datamask"].astype("int16")      # 1 = land, 2 = water

    base_forest = tc0 >= canopy_threshold
    n_land = max(1, int((data == 1).sum()))
    results = {}
    for y in years:
        yi = y - 2000
        lost = (loss > 0) & (loss <= min(yi, 25))
        forest = base_forest & ~lost
        if y >= 2013:
            regrown = gain & ~lost
            forest = forest | regrown
        forest = forest & (data == 1)
        # Area of loss dated to THIS year, as a fraction of land area. A pixel-count
        # test is meaningless at AOI scale (almost any 10x10 km box has a few loss
        # pixels), so the screening test downstream works on area, not presence.
        yr_loss = (loss == yi) & (data == 1) if 1 <= yi <= 25 else np.zeros_like(lost)
        results[y] = dict(
            forest_frac=float(forest.mean()),
            loss_frac=float(yr_loss.sum() / n_land),
            forest_mask=forest,
        )
    return results, dict(
        profile=profile,
        treecover2000_mean=float(np.nanmean(tc0)),
        loss_years=sorted({2000 + int(v) for v in np.unique(loss) if v > 0}),
        gain_frac=float(gain.mean()),
        water_frac=float((data == 2).mean()),
        canopy_threshold=canopy_threshold,
        n_pixels=int(tc0.size),
        n_land=n_land,
        loss_frac_by_year={y: results[y]["loss_frac"] for y in years},
    )
