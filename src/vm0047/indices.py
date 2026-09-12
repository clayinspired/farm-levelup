"""Stocking-index candidates.

VM0047 leaves the stocking index (SI) unspecified but names NDFI (Souza et al. 2005,
from Landsat) as an acceptable example, and requires the chosen metric to have a
published correlation with aboveground biomass plus local field validation.
We compute several so the proponent can pick and defend one.
"""
import numpy as np

# Souza et al. (2005) generic endmembers, reflectance x 10000,
# ordered [blue, green, red, nir, swir1, swir2].
ENDMEMBERS = {
    "gv":    [500, 900, 400, 6100, 3000, 1000],
    "npv":   [1400, 1700, 2200, 3000, 5500, 3000],
    "soil":  [2000, 3000, 3400, 5800, 6000, 5800],
    "cloud": [9000, 9600, 8000, 7800, 7200, 6500],
}
SMA_ORDER = ["gv", "npv", "soil", "cloud"]


def normalized_difference(a, b):
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(denom) > 1e-9, (a - b) / denom, np.nan)


def unmix(refl):
    """Linear spectral mixture analysis.

    refl: array (6, ...) of reflectance x 10000 in ENDMEMBERS band order.
    Returns dict of fractions incl. 'shade' (1 - sum of the rest).

    Uses a sum-to-one constrained least squares solved by augmentation, then
    clips to [0, 1]. This is the fast screening variant; for a validation-grade
    run swap in per-pixel NNLS (scipy.optimize.nnls) -- see README.
    """
    E = np.array([ENDMEMBERS[k] for k in SMA_ORDER], dtype="float64").T  # (6, 4)
    weight = 1e3  # sum-to-one constraint weight
    A = np.vstack([E, np.full((1, E.shape[1]), weight)])                 # (7, 4)

    flat = refl.reshape(refl.shape[0], -1).astype("float64")             # (6, N)
    b = np.vstack([flat, np.full((1, flat.shape[1]), weight)])           # (7, N)
    valid = np.isfinite(b).all(axis=0)

    frac = np.full((len(SMA_ORDER), flat.shape[1]), np.nan)
    if valid.any():
        sol, *_ = np.linalg.lstsq(A, b[:, valid], rcond=None)
        frac[:, valid] = sol
    frac = np.clip(frac, 0.0, 1.0)

    shape = refl.shape[1:]
    out = {k: frac[i].reshape(shape) for i, k in enumerate(SMA_ORDER)}
    out["shade"] = np.clip(1.0 - frac.sum(axis=0), 0.0, 1.0).reshape(shape)
    return out


def ndfi(refl):
    """Normalized Difference Fraction Index (Souza et al. 2005). Range [-1, 1].

    NDFI = (GVs - (NPV + Soil)) / (GVs + NPV + Soil), GVs = GV / (1 - shade).
    ~1 = intact closed canopy; low/negative = bare soil, senesced grass, degraded.
    """
    f = unmix(refl)
    with np.errstate(divide="ignore", invalid="ignore"):
        gvs = np.where(f["shade"] < 0.999, f["gv"] / (1.0 - f["shade"]), np.nan)
    denom = gvs + f["npv"] + f["soil"]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom > 1e-6, (gvs - (f["npv"] + f["soil"])) / denom, np.nan)


def all_indices(bands):
    """bands: dict of 2-D reflectance x 10000 arrays keyed blue/green/red/nir/swir1/swir2."""
    b = {k: bands[k].astype("float32") for k in ("blue", "green", "red", "nir", "swir1", "swir2")}
    stack = np.stack([b["blue"], b["green"], b["red"], b["nir"], b["swir1"], b["swir2"]])
    f = unmix(stack)
    return {
        "ndvi": normalized_difference(b["nir"], b["red"]),
        "ndmi": normalized_difference(b["nir"], b["swir1"]),   # canopy moisture
        "nbr":  normalized_difference(b["nir"], b["swir2"]),   # burn / clearing
        "ndfi": ndfi(stack),
        "gv_shade": np.where(f["shade"] < 0.999, f["gv"] / (1.0 - f["shade"]), np.nan),
        "soil_frac": f["soil"],
        "npv_frac": f["npv"],
    }
