"""Fast VM0047 pre-check for a point or polygon, sized for a chat round-trip.

Uses the Hansen GFC reconstruction only (no Landsat compositing), because a full
stocking-index series takes minutes. That is enough to answer the two questions
that disqualify most land: was it forest during the look-back, and was it cleared.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

# vm0047.hansen lives beside this file in the container image and under src/ in the
# repo. Probe defensively: .parents[n] raises IndexError near the filesystem root,
# so build the candidate list rather than indexing eagerly.
_HERE = Path(__file__).resolve().parent
_candidates = [_HERE, _HERE.parent]
for _n in (1, 2):
    if len(_HERE.parents) > _n:
        _candidates.append(_HERE.parents[_n] / "src")
for _c in _candidates:
    if (_c / "vm0047").is_dir():
        sys.path.insert(0, str(_c))
        break

os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("CPL_VSIL_CURL_CACHE_SIZE", "200000000")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

import numpy as np                        # noqa: E402
import rasterio.features                  # noqa: E402

from vm0047.hansen import annual_forest, read_layers  # noqa: E402

HISTORIC_YEARS = 10
WOODY_LIMIT = 0.10
LOSS_LIMIT = 0.01
MIN_CONTEXT_M = 150          # never read a window smaller than this; Hansen is 30 m

# --- result cache -------------------------------------------------------------
# The underlying Hansen GFC release is a fixed annual product, so a result for a
# given window cannot change until the dataset version does. Keying on the dataset
# version means a future v1.14 invalidates everything automatically.
CACHE_PATH = Path(os.environ.get("CACHE_PATH")
                  or (_HERE.parents[1] / "out" / "elig_cache.json"
                      if len(_HERE.parents) > 1 else Path("elig_cache.json")))
CACHE_MAX = 5000
_cache: dict = {}
_cache_lock = threading.Lock()
_cache_loaded = False


def _dataset_version() -> str:
    from vm0047.hansen import VERSION
    return VERSION


def _load_cache() -> None:
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    try:
        raw = json.loads(CACHE_PATH.read_text())
        if raw.get("dataset") == _dataset_version():
            _cache = raw.get("entries", {})
    except Exception:
        _cache = {}
    _cache_loaded = True


def _save_cache() -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"dataset": _dataset_version(), "entries": _cache}))
        tmp.replace(CACHE_PATH)                      # atomic; never a half-written cache
    except Exception:
        pass


def _key(kind: str, payload, t0: int, canopy: int) -> str:
    blob = json.dumps([kind, payload, t0, canopy], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:20]


def _normalise(r: dict) -> dict:
    """JSON turns int dict keys into strings; put them back."""
    if isinstance(r.get("forest_by_year"), dict):
        r["forest_by_year"] = {int(k): v for k, v in r["forest_by_year"].items()}
    return r


def cache_get(key: str):
    _load_cache()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        hit["ts"] = time.time()                      # touch for LRU pruning
        return _normalise(dict(hit["r"]))


def cache_put(key: str, result: dict) -> None:
    _load_cache()
    with _cache_lock:
        _cache[key] = {"r": result, "ts": time.time()}
        if len(_cache) > CACHE_MAX:                  # drop least-recently-used
            for k, _ in sorted(_cache.items(), key=lambda kv: kv[1]["ts"])[:len(_cache) - CACHE_MAX]:
                _cache.pop(k, None)
        _save_cache()


def cache_stats() -> dict:
    _load_cache()
    return {"entries": len(_cache), "dataset": _dataset_version()}


def point_key(lat: float, lon: float, area_ha: float, t0: int = 2026, canopy: int = 10) -> str:
    """Key on the derived window, rounded to ~1 m, so the same spot and size always
    hits regardless of float noise from the Telegram payload."""
    w, s_, e, n = bbox_from_point(lat, lon, area_ha)
    return _key("bbox", [round(v, 5) for v in (w, s_, e, n)], t0, canopy)


def polygon_key(coords, t0: int = 2026, canopy: int = 10) -> str:
    return _key("poly", [[round(c[0], 5), round(c[1], 5)] for c in coords], t0, canopy)


def bbox_from_point(lat: float, lon: float, area_ha: float) -> tuple:
    """Square bbox of the stated area centred on the point, with a context floor."""
    side_m = max(math.sqrt(max(area_ha, 0.01) * 10_000), MIN_CONTEXT_M * 2)
    half = side_m / 2.0
    dlat = half / 111_320.0
    dlon = half / (111_320.0 * max(0.15, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def pad_bbox(bbox, min_side_m: float) -> tuple:
    """Grow a bbox so it is at least min_side_m across. Hansen is 30 m, so a
    smallholder plot can otherwise read back as a zero-size window."""
    w, s, e, n = bbox
    clat = (s + n) / 2.0
    dlat = min_side_m / 111_320.0
    dlon = min_side_m / (111_320.0 * max(0.15, math.cos(math.radians(clat))))
    if (e - w) < dlon:
        cx = (w + e) / 2.0
        w, e = cx - dlon / 2, cx + dlon / 2
    if (n - s) < dlat:
        cy = (s + n) / 2.0
        s, n = cy - dlat / 2, cy + dlat / 2
    return (w, s, e, n)


def bbox_from_polygon(coords) -> tuple:
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def polygon_area_ha(coords) -> float:
    """Spherical excess is overkill at field scale; equirectangular is fine here."""
    if len(coords) < 3:
        return 0.0
    lat0 = sum(c[1] for c in coords) / len(coords)
    k = math.cos(math.radians(lat0))
    pts = [(c[0] * 111_320.0 * k, c[1] * 110_540.0) for c in coords]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 10_000.0


def check(bbox, t0: int = 2026, canopy_threshold: int = 10, use_cache: bool = True) -> dict:
    """Blocking. Call from a worker thread."""
    ck = _key("bbox", [round(v, 5) for v in bbox], t0, canopy_threshold)
    if use_cache:
        hit = cache_get(ck)
        if hit is not None:
            return {**hit, "cached": True}
    years = list(range(t0 - HISTORIC_YEARS, t0 + 1))
    res, meta = annual_forest(bbox, years, canopy_threshold=canopy_threshold)

    forest = {y: v["forest_frac"] for y, v in res.items()}
    max_forest = max(forest.values())
    loss_by_year = meta.get("loss_frac_by_year", {})
    cum_loss = float(sum(loss_by_year.values()))
    material = sorted(y for y, v in loss_by_year.items() if v >= LOSS_LIMIT / 2)

    non_forest_ok = max_forest < WOODY_LIMIT
    clearing_ok = cum_loss < LOSS_LIMIT

    if non_forest_ok and clearing_ok:
        verdict, headline = "PASS", "Looks eligible on the land-history tests"
    elif not non_forest_ok and not clearing_ok:
        verdict, headline = "FAIL", "Recently forested land that was cleared"
    elif not non_forest_ok:
        verdict, headline = "CONDITIONAL", "Tree cover above the non-forest limit"
    else:
        verdict, headline = "CONDITIONAL", "Clearing detected in the last 10 years"

    out = dict(
        verdict=verdict, headline=headline,
        max_forest=max_forest, cum_loss=cum_loss,
        material_loss_years=material,
        forest_by_year={int(y): round(v, 4) for y, v in forest.items()},
        canopy_threshold=canopy_threshold,
        water_frac=meta.get("water_frac", 0.0),
        t0=t0, years=[years[0], years[-1]],
        non_forest_ok=non_forest_ok, clearing_ok=clearing_ok,
    )
    if use_cache:
        cache_put(ck, out)
    return {**out, "cached": False}


def check_polygon(coords, t0: int = 2026, canopy_threshold: int = 10,
                  use_cache: bool = True) -> dict:
    """Same tests as check(), but restricted to the drawn polygon rather than its
    bounding box -- otherwise drawing an irregular field would tell you nothing the
    point-and-area estimate did not. Blocking; call from a worker thread."""
    pk = polygon_key(coords, t0, canopy_threshold)
    if use_cache:
        hit = cache_get(pk)
        if hit is not None:
            return {**hit, "cached": True}

    bbox = pad_bbox(bbox_from_polygon(coords), MIN_CONTEXT_M)
    years = list(range(t0 - HISTORIC_YEARS, t0 + 1))

    lyr, profile = read_layers(bbox)
    tc0 = lyr["treecover2000"].astype("float32")
    loss = lyr["lossyear"].astype("int16")
    gain = lyr["gain"].astype(bool)
    data = lyr["datamask"].astype("int16")

    if tc0.size == 0 or min(tc0.shape) == 0:        # window degenerate even after padding
        return {**check(pad_bbox(bbox, MIN_CONTEXT_M * 2), t0, canopy_threshold),
                "subpixel": True}

    geom = {"type": "Polygon", "coordinates": [[list(c) for c in coords] + [list(coords[0])]]}
    inside = rasterio.features.geometry_mask(
        [geom], out_shape=tc0.shape, transform=profile["transform"], invert=True)
    land = inside & (data == 1)
    n = int(land.sum())
    if n == 0:                              # plot smaller than one 30 m pixel
        return {**check(bbox, t0, canopy_threshold), "subpixel": True}

    base_forest = tc0 >= canopy_threshold
    forest_by_year, loss_frac = {}, {}
    for y in years:
        yi = min(y - 2000, 25)
        lost = (loss > 0) & (loss <= yi)
        f = base_forest & ~lost
        if y >= 2013:
            f = f | (gain & ~lost)
        forest_by_year[y] = float((f & land).sum() / n)
        loss_frac[y] = float((((loss == yi) if 1 <= yi <= 25 else np.zeros_like(lost)) & land).sum() / n)

    max_forest = max(forest_by_year.values())
    cum_loss = float(sum(loss_frac.values()))
    material = sorted(y for y, v in loss_frac.items() if v >= LOSS_LIMIT / 2)
    non_forest_ok = max_forest < WOODY_LIMIT
    clearing_ok = cum_loss < LOSS_LIMIT

    if non_forest_ok and clearing_ok:
        verdict, headline = "PASS", "Looks eligible on the land-history tests"
    elif not non_forest_ok and not clearing_ok:
        verdict, headline = "FAIL", "Recently forested land that was cleared"
    elif not non_forest_ok:
        verdict, headline = "CONDITIONAL", "Tree cover above the non-forest limit"
    else:
        verdict, headline = "CONDITIONAL", "Clearing detected in the last 10 years"

    out = dict(
        verdict=verdict, headline=headline, max_forest=max_forest, cum_loss=cum_loss,
        material_loss_years=material,
        forest_by_year={int(y): round(v, 4) for y, v in forest_by_year.items()},
        canopy_threshold=canopy_threshold, water_frac=float((data == 2).mean()),
        t0=t0, years=[years[0], years[-1]],
        non_forest_ok=non_forest_ok, clearing_ok=clearing_ok,
        pixels_in_plot=n, subpixel=False,
    )
    if use_cache:
        cache_put(pk, out)
    return {**out, "cached": False}
