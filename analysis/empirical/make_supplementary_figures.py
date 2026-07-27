#!/usr/bin/env python3
"""Generate publication-ready supplementary figures from preserved derived data.

This script changes only presentation. It refits the documented read-speech GEE
and visualizes the preserved ArtiSynth long tables without changing any value,
model, threshold, or feasibility classification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import hashlib
import math

import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.colors import LogNorm
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_anatomy(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(path)
    co = (
        d[d["measure"].eq("co_me")]
        .groupby("participant_id", as_index=False)["value_mm"]
        .mean()
        .rename(columns={"value_mm": "co_me_mean_mm"})
    )
    ht = (
        d[d["measure"].eq("height")]
        .groupby("participant_id", as_index=False)["value_mm"]
        .mean()
        .rename(columns={"value_mm": "height_mm"})
    )
    return co, ht


def make_read_speech(read_path: Path, anatomy_path: Path, effects_path: Path,
                     out_pdf: Path, out_png: Path) -> None:
    read = pd.read_csv(read_path)
    read = read[read["status"].astype(str).str.strip().str.lower().eq("ok")].copy()
    co, ht = load_anatomy(anatomy_path)
    d = read.merge(co, on="participant_id", how="inner", validate="m:1").merge(
        ht, on="participant_id", how="inner", validate="m:1"
    )
    d["co_me_mean_mm_10"] = d["co_me_mean_mm"] / 10.0
    d["height_cm"] = d["height_mm"] / 10.0
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean())

    formula = (
        "audio_mod_dom_hz ~ "
        "C(task, Treatment(reference='passage_baseline_noEMA')) + "
        "co_me_mean_mm_10 + height_cm_c"
    )
    model = smf.gee(
        formula=formula,
        groups="participant_id",
        data=d,
        family=sm.families.Gaussian(),
        cov_struct=sm.cov_struct.Independence(),
    )
    result = model.fit()

    eff = pd.read_csv(effects_path)
    row = eff[eff["term"].eq("co_me_mean_mm_10")].iloc[0]
    for key, value in {
        "beta": result.params["co_me_mean_mm_10"],
        "robust_se": result.bse["co_me_mean_mm_10"],
    }.items():
        if not np.isclose(float(row[key]), float(value), atol=1e-10, rtol=0):
            raise ValueError(f"Read-speech model mismatch for {key}: {value} vs {row[key]}")

    x = np.linspace(float(d["co_me_mean_mm"].min()), float(d["co_me_mean_mm"].max()), 200)
    tasks = sorted(d["task"].unique())
    design_info = result.model.data.design_info
    design_rows = []
    for xv in x:
        nd = pd.DataFrame({
            "task": tasks,
            "co_me_mean_mm_10": [xv / 10.0] * len(tasks),
            "height_cm_c": [0.0] * len(tasks),
        })
        X = np.asarray(patsy.build_design_matrices([design_info], nd)[0], dtype=float)
        design_rows.append(X.mean(axis=0))
    Xbar = np.vstack(design_rows)
    beta = np.asarray(result.params, dtype=float)
    cov = np.asarray(result.cov_params(), dtype=float)
    pred = Xbar @ beta
    var = np.einsum("ij,jk,ik->i", Xbar, cov, Xbar)
    se = np.sqrt(np.maximum(var, 0.0))
    lo = pred - 1.959963984540054 * se
    hi = pred + 1.959963984540054 * se

    means = d.groupby("participant_id", as_index=False).agg(
        co_me_mean_mm=("co_me_mean_mm", "first"),
        participant_mean=("audio_mod_dom_hz", "mean"),
    )

    mpl.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8.4,
        "axes.labelsize": 8.8,
        "xtick.labelsize": 7.8,
        "ytick.labelsize": 7.8,
        "legend.fontsize": 7.7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig, ax = plt.subplots(figsize=(7.45, 4.45))
    ax.scatter(d["co_me_mean_mm"], d["audio_mod_dom_hz"], s=15, color="0.75", alpha=0.55,
               edgecolors="none", label="Recording", zorder=1)
    ax.scatter(means["co_me_mean_mm"], means["participant_mean"], s=35, color="0.12",
               edgecolors="white", linewidths=0.45, label="Participant mean", zorder=3)
    ax.fill_between(x, lo, hi, color="0.25", alpha=0.18, label="95% robust CI", zorder=1)
    ax.plot(x, pred, color="0.10", linewidth=1.7, label="Task-averaged model fit", zorder=2)
    ax.set_xlabel("Bilateral mean external Co-Me (mm)")
    ax.set_ylabel("Dominant envelope modulation (Hz)")
    ax.grid(True, alpha=0.22, linewidth=0.55)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    annotation = (
        f"Co-Me: {float(row['beta']):+.3f} Hz per +10 mm\n"
        f"95% CI [{float(row['ci_lower']):+.3f}, {float(row['ci_upper']):+.3f}]\n"
        f"P = {float(row['p_value']):.3f}; N = {int(row['n_observations'])} recordings / "
        f"{int(row['n_speakers'])} speakers"
    )
    ax.text(0.02, 0.98, annotation, transform=ax.transAxes, va="top", ha="left", fontsize=7.8,
            bbox=dict(boxstyle="round,pad=0.32", facecolor="white", edgecolor="0.65", alpha=0.94))
    ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="0.78")
    fig.tight_layout()
    pdf_meta = {
        "Title": "Supplementary Figure 2 - exploratory read-speech analysis",
        "Author": "Daniel Friedrichs and Volker Dellwo",
        "Creator": "Matplotlib",
        "Subject": "Exploratory read-speech analysis",
        "CreationDate": None,
        "ModDate": None,
    }
    png_meta = {
        "Title": "Supplementary Figure 2 - exploratory read-speech analysis",
        "Author": "Daniel Friedrichs and Volker Dellwo",
        "Software": "Matplotlib",
    }
    fig.savefig(out_pdf, bbox_inches="tight", metadata=pdf_meta)
    fig.savefig(out_png, dpi=300, bbox_inches="tight", metadata=png_meta)
    plt.close(fig)


def make_artisynth(fixed_path: Path, force_path: Path, out_pdf: Path, out_png: Path) -> None:
    fixed = pd.read_csv(fixed_path)
    force = pd.read_csv(force_path)
    d = pd.concat([fixed, force], ignore_index=True)
    expected_scales = np.round(np.arange(0.80, 1.2001, 0.05), 2)
    expected_freqs = np.round(np.arange(1.0, 10.0001, 0.5), 1)
    expected_amps = [1.0, 1.5]
    if len(d) != 684 or d["run_id"].nunique() != 684:
        raise ValueError("Expected 684 unique ArtiSynth cells")
    if not d["return_status"].eq("success").all() or not d["is_feasible"].astype(str).str.lower().eq("true").all():
        raise ValueError("All public ArtiSynth cells must be successful and feasible")
    if not np.allclose(sorted(d["scale"].unique()), expected_scales):
        raise ValueError("Unexpected scale grid")
    if not np.allclose(sorted(d["freq_hz"].unique()), expected_freqs):
        raise ValueError("Unexpected frequency grid")
    if not np.allclose(sorted(d["target_amp_p2p_mm"].unique()), expected_amps):
        raise ValueError("Unexpected amplitude grid")

    mpl.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 7.5,
        "axes.titlesize": 8.3,
        "axes.labelsize": 7.6,
        "xtick.labelsize": 6.8,
        "ytick.labelsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    fig = plt.figure(figsize=(8.55, 9.0))
    gs = fig.add_gridspec(
        4, 3, width_ratios=[0.72, 1.0, 1.0], left=0.035, right=0.86,
        bottom=0.07, top=0.965, hspace=0.58, wspace=0.25
    )
    row_specs = [
        ("fixed_force", "peak_excitation", "Fixed force\nPeak excitation", "peak"),
        ("fixed_force", "mean_summed_squared_excitation", "Fixed force\nMean summed-squared\nexcitation", "effort"),
        ("force_capacity_s2", "peak_excitation", "$s^2$ force capacity\nPeak excitation", "peak"),
        ("force_capacity_s2", "mean_summed_squared_excitation", "$s^2$ force capacity\nMean summed-squared\nexcitation", "effort"),
    ]
    axes = np.empty((4, 2), dtype=object)
    peak_image = None
    effort_image = None
    for row, (mode, metric, row_label, kind) in enumerate(row_specs):
        label_ax = fig.add_subplot(gs[row, 0])
        label_ax.axis("off")
        label_ax.text(0.02, 0.5, row_label, ha="left", va="center",
                      fontsize=7.4, fontweight="semibold", linespacing=1.18)
        for col, amp in enumerate(expected_amps):
            ax = fig.add_subplot(gs[row, col + 1])
            axes[row, col] = ax
            sub = d[(d["mode"].eq(mode)) & np.isclose(d["target_amp_p2p_mm"], amp)]
            piv = sub.pivot(index="freq_hz", columns="scale", values=metric).sort_index().sort_index(axis=1)
            arr = piv.to_numpy()
            if kind == "peak":
                im = ax.imshow(arr, origin="lower", aspect="auto", cmap="viridis", vmin=0, vmax=0.95)
                peak_image = im
            else:
                im = ax.imshow(arr, origin="lower", aspect="auto", cmap="magma",
                               norm=LogNorm(vmin=3e-5, vmax=0.2))
                effort_image = im
            ax.set_xticks(range(len(piv.columns)))
            ax.set_xticklabels([f"{v:.2f}" for v in piv.columns], rotation=45, ha="right")
            y_positions = [i for i, f in enumerate(piv.index) if np.isclose(f % 1.0, 0.0)]
            ax.set_yticks(y_positions)
            ax.set_yticklabels([f"{piv.index[i]:.0f}" for i in y_positions])
            ax.set_xlabel("Scale $s$")
            ax.set_ylabel("Target frequency (Hz)")
            if row == 0:
                ax.set_title(f"A = {amp:.1f} mm peak-to-peak", pad=4)
            yy, xx = np.indices(arr.shape)
            ax.scatter(xx.ravel(), yy.ravel(), s=2.2, c="white", alpha=0.33, linewidths=0)
            for spine in ax.spines.values():
                spine.set_linewidth(0.65)

    if peak_image is None or effort_image is None:
        raise RuntimeError("Missing color images")
    cax1 = fig.add_axes([0.895, 0.545, 0.018, 0.315])
    cb1 = fig.colorbar(peak_image, cax=cax1)
    cb1.set_label("Peak excitation\n(feasibility threshold 0.95)", fontsize=7.2)
    cb1.ax.tick_params(labelsize=6.5)
    cax2 = fig.add_axes([0.895, 0.115, 0.018, 0.315])
    cb2 = fig.colorbar(effort_image, cax=cax2)
    cb2.set_label("Mean summed-squared excitation\n(log scale)", fontsize=7.2)
    cb2.ax.tick_params(labelsize=6.5)
    pdf_meta = {
        "Title": "Supplementary Figure 1 - ArtiSynth excitation landscapes",
        "Author": "Daniel Friedrichs and Volker Dellwo",
        "Creator": "Matplotlib",
        "Subject": "ArtiSynth mass-and-inertia sensitivity analysis",
        "CreationDate": None,
        "ModDate": None,
    }
    png_meta = {
        "Title": "Supplementary Figure 1 - ArtiSynth excitation landscapes",
        "Author": "Daniel Friedrichs and Volker Dellwo",
        "Software": "Matplotlib",
    }
    fig.savefig(out_pdf, bbox_inches="tight", metadata=pdf_meta)
    fig.savefig(out_png, dpi=300, bbox_inches="tight", metadata=png_meta)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-speech", type=Path, required=True)
    ap.add_argument("--anatomy", type=Path, required=True)
    ap.add_argument("--read-effects", type=Path, required=True)
    ap.add_argument("--artisynth-fixed", type=Path, required=True)
    ap.add_argument("--artisynth-force", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    make_read_speech(
        args.read_speech.resolve(), args.anatomy.resolve(), args.read_effects.resolve(),
        out / "FigureS2_ReadSpeech.pdf",
        out / "FigureS2_ReadSpeech.png",
    )
    make_artisynth(
        args.artisynth_fixed.resolve(), args.artisynth_force.resolve(),
        out / "FigureS1_ArtiSynth.pdf", out / "FigureS1_ArtiSynth.png",
    )
    manifest = pd.DataFrame([
        {"file": p.name, "size_bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(out.iterdir()) if p.is_file()
    ])
    manifest.to_csv(out / "supplementary_figure_manifest.tsv", sep="\t", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
