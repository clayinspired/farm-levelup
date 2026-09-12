"""Annual SI + forest-fraction trajectory charts from the JSON reports."""
import json, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

INK, MUTED, ACCENT, WARN = "#1f2328", "#8b949e", "#2f6f4e", "#b4462f"


def plot_report(path, outdir=Path("out")):
    r = json.loads(Path(path).read_text())
    si = {int(k): v for k, v in r["si_series"].items() if v is not None}
    ff = {int(k): v for k, v in r["forest_fraction"].items() if v is not None}
    yrs = sorted(si)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), dpi=160)
    fig.suptitle(f"{r['aoi']} — {r['aoi_meta']['country']}   ·   {r['triage']}",
                 fontsize=11, fontweight="600", color=INK, y=1.0)

    ax = axes[0]
    v = [si[y] for y in yrs]
    ax.plot(yrs, v, "o-", color=ACCENT, lw=1.8, ms=4)
    if len(yrs) >= 3:
        lr = stats.linregress(yrs, v)
        xs = np.array([min(yrs), max(yrs)])
        neg = lr.slope < 0 and lr.pvalue < 0.05
        ax.plot(xs, lr.intercept + lr.slope * xs, "--", lw=1.4,
                color=WARN if neg else MUTED,
                label=f"slope={lr.slope:+.4f}/yr  p={lr.pvalue:.3f}"
                      + ("  ← clearing indicated" if neg else ""))
        ax.legend(fontsize=7.5, frameon=False)
    ax.set_title("Stocking index (NDFI), season-matched", fontsize=9, color=INK)
    ax.set_ylabel("NDFI", fontsize=8)

    ax = axes[1]
    ax.plot(sorted(ff), [ff[y] for y in sorted(ff)], "o-", color=INK, lw=1.8, ms=4)
    ax.axhline(0.10, ls=":", color=WARN, lw=1.2)
    ax.text(min(ff), 0.105, "10% woody-cover limit (§4 #11a)", fontsize=7, color=WARN)
    ax.set_title(f"Forest fraction, Hansen GFC v1.13 (crown ≥ {r['aoi_meta']['canopy_threshold']}%)",
                 fontsize=9, color=INK)
    ax.set_ylabel("fraction of AOI", fontsize=8)
    ax.set_ylim(0, max(0.15, max(ff.values()) * 1.15))

    for a in axes:
        a.grid(alpha=.25, lw=.6); a.set_xlabel("year", fontsize=8)
        a.tick_params(labelsize=7.5)
        for s in ("top", "right"): a.spines[s].set_visible(False)
    fig.tight_layout()
    out = outdir / f"{r['aoi']}_trajectory.png"
    fig.savefig(out, bbox_inches="tight"); plt.close(fig)
    return out


if __name__ == "__main__":
    for p in (sys.argv[1:] or sorted(Path("out").glob("*_report.json"))):
        print("wrote", plot_report(p))
