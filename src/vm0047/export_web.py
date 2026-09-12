"""Turn the screening outputs into web-map assets: per-year PNG overlays + index.json."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path("out")
WEB = Path("site/map")


def ndfi_rgba(a):
    """Diverging ramp: red (bare/degraded) -> sand -> deep green (closed canopy)."""
    stops = np.array([
        [-1.0, 0xB4, 0x46, 0x2F],
        [-0.3, 0xD9, 0x8A, 0x5B],
        [ 0.1, 0xE8, 0xD8, 0xA8],
        [ 0.5, 0x7A, 0xA8, 0x67],
        [ 1.0, 0x1B, 0x4D, 0x3E],
    ], dtype="float64")
    finite = np.isfinite(a)
    x = np.clip(np.where(finite, a, 0.0).astype("float64"), -1, 1)
    rgb = np.stack([np.interp(x, stops[:, 0], stops[:, i + 1]) for i in range(3)], axis=-1)
    rgb = np.where(finite[..., None], rgb, 0.0)      # keep the cast defined on nodata
    alpha = np.where(finite, 205, 0)
    return np.dstack([rgb, alpha]).astype("uint8")


def forest_rgba(mask):
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype="uint8")
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 0x23, 0x8C, 0x5A
    rgba[..., 3] = np.where(mask.astype(bool), 190, 0)
    return rgba


def save_png(rgba, path, max_dim=900):
    img = Image.fromarray(rgba, mode="RGBA")
    if max(img.size) > max_dim:
        s = max_dim / max(img.size)
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return img.size


def export():
    WEB.mkdir(exist_ok=True)
    aois = []
    for rep_path in sorted(OUT.glob("*_report.json")):
        key = rep_path.name.replace("_report.json", "")
        stack_path = OUT / f"{key}_stack.npz"
        if not stack_path.exists():
            print(f"skip {key}: no stack"); continue
        rep = json.loads(rep_path.read_text())
        z = np.load(stack_path, allow_pickle=True)
        bbox = [float(v) for v in z["bbox"]]
        years = [int(y) for y in z["years"]]

        layers = {"ndfi": {}, "forest": {}}
        for y in years:
            if f"ndfi_{y}" in z:
                a = z[f"ndfi_{y}"]
                save_png(ndfi_rgba(a), WEB / "data" / key / f"ndfi_{y}.png")
                layers["ndfi"][y] = f"data/{key}/ndfi_{y}.png"
            if f"forest_{y}" in z:
                m = z[f"forest_{y}"]
                save_png(forest_rgba(m), WEB / "data" / key / f"forest_{y}.png")
                layers["forest"][y] = f"data/{key}/forest_{y}.png"

        f = rep["findings"]
        aois.append(dict(
            key=key,
            country=rep["aoi_meta"]["country"],
            note=rep["aoi_meta"]["note"],
            region="Southeast Asia" if key.split("-")[0] in (
                "id", "kh", "vn", "my", "th", "la", "ph", "mm", "bn", "tl", "sg")
                   else "Africa",
            bbox=bbox,
            centre=[(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2],
            t0=rep["t0"], years=years,
            triage=rep["triage"],
            season=rep["aoi_meta"]["season"],
            canopy_threshold=rep["aoi_meta"]["canopy_threshold"],
            si=rep["si_series"], forest=rep["forest_fraction"],
            trend=dict(slope=f["si_trend"].get("slope"), p=f["si_trend"].get("p_value"),
                       r2=f["si_trend"].get("r2"),
                       significant_negative=f["si_trend"].get("significant_negative")),
            loss_years=f["no_recent_clearing"].get("material_loss_years",
                       f["no_recent_clearing"].get("loss_years_detected", [])),
            cum_loss=f["no_recent_clearing"].get("cumulative_loss_fraction"),
            loss_by_year=f["no_recent_clearing"].get("loss_fraction_by_year", {}),
            max_forest=f["non_forest_10yr"].get("max_forest_fraction"),
            scenes={int(k): v.get("n_scenes") for k, v in rep.get("composites", {}).items()},
            clear={int(k): v.get("clear_frac") for k, v in rep.get("composites", {}).items()},
            findings={k: dict(test=v["test"], passes=v.get("passes"), note=v.get("note"))
                      for k, v in f.items()},
            layers=layers,
        ))
        print(f"exported {key}: {len(layers['ndfi'])} ndfi + {len(layers['forest'])} forest frames")

    order = {"P": 0, "C": 1, "F": 2}
    aois.sort(key=lambda a: (a["region"] != "Southeast Asia",
                             order.get(a["triage"][0], 3), a["country"]))

    (WEB / "data").mkdir(parents=True, exist_ok=True)
    (WEB / "data" / "index.json").write_text(json.dumps(
        dict(generated="2026-09-12", aois=aois), indent=1))
    print(f"\nwrote web/data/index.json with {len(aois)} AOIs")
    return aois


if __name__ == "__main__":
    export()
