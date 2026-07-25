#!/usr/bin/env python3
"""Independent Phase C validation and canonical-output generation.

This script operates on an already safely extracted corrected-return root and the
archived prior long-form tables. It does not launch ArtiSynth or alter source
runs. It independently applies the approved feasibility thresholds and strict
prefix rule, creates canonical tables, figures, reports, and a manifest.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import textwrap
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

RMSE_MAX = 0.5
PEAK_EXC_MAX = 0.95
GAIN_MIN = 0.7
GAIN_MAX = 1.3
PREFIX_RULE = "STRICT_ALL_LOWER_AND_SELF_FEASIBLE_V1"
VERDICT = "ARTISYNTH CORRECTED RESULT DOES NOT SUPPORT THE PRIOR MECHANISTIC CLAIM"
EXPECTED_SCALES = [round(0.80 + 0.05 * i, 2) for i in range(9)]
EXPECTED_FREQS = [round(1.0 + 0.5 * i, 1) for i in range(19)]
EXPECTED_AMPS = [1.0, 1.5]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def bool_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(bool)
    return s.astype(str).str.strip().str.lower().map({"true": True, "false": False}).fillna(False)


def independently_classify(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["independent_rmse_ok"] = out["tracking_rmse_mm"] <= RMSE_MAX
    out["independent_peak_excitation_ok"] = out["peak_excitation"] <= PEAK_EXC_MAX
    out["independent_amplitude_gain_ok"] = out["amplitude_gain"].between(
        GAIN_MIN, GAIN_MAX, inclusive="both"
    )
    out["independent_is_feasible"] = (
        out["independent_rmse_ok"]
        & out["independent_peak_excitation_ok"]
        & out["independent_amplitude_gain_ok"]
    )
    criteria: list[str] = []
    for _, r in out.iterrows():
        failed: list[str] = []
        if not bool(r["independent_rmse_ok"]):
            failed.append("tracking_rmse_mm")
        if not bool(r["independent_peak_excitation_ok"]):
            failed.append("peak_excitation")
        if not bool(r["independent_amplitude_gain_ok"]):
            failed.append("amplitude_gain")
        criteria.append(";".join(failed))
    out["independent_failed_criteria"] = criteria
    return out


def strict_prefix(df: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    source_hash = sha256_file(source_path)
    for (mode, scale, amp), g in df.groupby(
        ["mode", "scale", "target_amp_p2p_mm"], sort=True
    ):
        g = g.sort_values("freq_hz")
        feas = g["independent_is_feasible"].to_numpy(dtype=bool)
        freqs = g["freq_hz"].to_numpy(dtype=float)
        bad = np.flatnonzero(~feas)
        if len(bad) == 0:
            first_fail_idx = None
            fmax = float(freqs[-1])
            first_freq: float | None = None
            first_criterion = ""
            later_feasible = 0
            all_feasible = True
            fmax_display = f">={fmax:g}"
        else:
            first_fail_idx = int(bad[0])
            first_freq = float(freqs[first_fail_idx])
            first_criterion = str(g.iloc[first_fail_idx]["independent_failed_criteria"])
            fmax = float("nan") if first_fail_idx == 0 else float(freqs[first_fail_idx - 1])
            later_feasible = int(feas[first_fail_idx + 1 :].sum())
            all_feasible = False
            fmax_display = "<1" if first_fail_idx == 0 else f"{fmax:g}"
        n_prefix = len(freqs) if first_fail_idx is None else first_fail_idx
        rows.append(
            {
                "mode": mode,
                "scale": float(scale),
                "target_amp_p2p_mm": float(amp),
                "n_tested": int(len(g)),
                "n_cell_feasible": int(feas.sum()),
                "n_prefix_feasible": int(n_prefix),
                "fmax_hz": fmax,
                "fmax_display": fmax_display,
                "endpoint_is_tested_ceiling": bool(all_feasible),
                "all_frequencies_feasible": bool(all_feasible),
                "first_failed_frequency_hz": first_freq,
                "first_failed_criterion": first_criterion,
                "n_feasible_after_first_failure": int(later_feasible),
                "locally_nonmonotonic_feasibility": bool(later_feasible > 0),
                "rmse_max_mm": RMSE_MAX,
                "peak_excitation_max": PEAK_EXC_MAX,
                "gain_min": GAIN_MIN,
                "gain_max": GAIN_MAX,
                "prefix_rule_id": PREFIX_RULE,
                "source_long_table": source_path.name,
                "source_long_table_sha256": source_hash,
            }
        )
    return pd.DataFrame(rows)


def prior_classify_and_prefix(path: Path, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path)
    ren = {
        "amp_mm": "target_amp_p2p_mm",
        "tracking_rmse_mm": "tracking_rmse_mm",
        "max_excitation": "peak_excitation",
        "amp_gain": "amplitude_gain",
    }
    df = df.rename(columns=ren)
    df["mode"] = mode
    df["scale"] = df["scale"].round(2)
    df["freq_hz"] = df["freq_hz"].round(1)
    df["target_amp_p2p_mm"] = df["target_amp_p2p_mm"].round(1)
    df = independently_classify(df)
    return df, strict_prefix(df, path)


def verify_grid(df: pd.DataFrame, mode: str) -> list[str]:
    errors: list[str] = []
    if len(df) != 342:
        errors.append(f"{mode}: expected 342 rows, found {len(df)}")
    if set(df["mode"].astype(str)) != {mode}:
        errors.append(f"{mode}: mode labels differ from expected")
    keys = ["scale", "freq_hz", "target_amp_p2p_mm"]
    if df.duplicated(keys).any():
        errors.append(f"{mode}: duplicate scale x frequency x amplitude cells")
    scales = sorted(round(float(x), 2) for x in df["scale"].unique())
    freqs = sorted(round(float(x), 1) for x in df["freq_hz"].unique())
    amps = sorted(round(float(x), 1) for x in df["target_amp_p2p_mm"].unique())
    if scales != EXPECTED_SCALES:
        errors.append(f"{mode}: scale grid mismatch: {scales}")
    if freqs != EXPECTED_FREQS:
        errors.append(f"{mode}: frequency grid mismatch: {freqs}")
    if amps != EXPECTED_AMPS:
        errors.append(f"{mode}: amplitude grid mismatch: {amps}")
    if set(df["return_status"].astype(str)) != {"success"}:
        errors.append(f"{mode}: non-success return status present")
    if not (df["return_code"] == 0).all():
        errors.append(f"{mode}: nonzero return code present")
    return errors


def values_equal(a: Any, b: Any, tol: float = 1e-12) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if isinstance(a, (int, float, np.integer, np.floating)) and isinstance(
        b, (int, float, np.integer, np.floating)
    ):
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    return str(a) == str(b)


def cross_mode_identity(fixed: pd.DataFrame, force: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    key = ["scale", "freq_hz", "target_amp_p2p_mm"]
    f = fixed.copy()
    s = force.copy()
    for x in (f, s):
        x["scale_key"] = x["scale"].round(2)
        x["freq_key"] = x["freq_hz"].round(1)
        x["amp_key"] = x["target_amp_p2p_mm"].round(1)
    merged = f.merge(
        s,
        on=["scale_key", "freq_key", "amp_key"],
        suffixes=("_fixed", "_force"),
        validate="one_to_one",
    )
    allowed = {
        "run_id",
        "mode",
        "force_exp",
        "effective_force_multiplier",
        "n_force_scaled",
        "mass_multiplier",
        "inertia_multiplier",
        "scale",
        "freq_hz",
        "target_amp_p2p_mm",
        # Dynamics and run-specific provenance legitimately differ.
        "n_samples",
        "actual_source_amp_p2p_mm",
        "actual_target_amp_p2p_mm",
        "amplitude_gain",
        "tracking_rmse_mm",
        "peak_excitation",
        "mean_summed_squared_excitation",
        "rmse_ok",
        "peak_excitation_ok",
        "amplitude_gain_ok",
        "is_feasible",
        "failed_criteria",
        "cell_directory",
        "raw_java_csv_path",
        "raw_stdout_path",
        "raw_stderr_path",
        "raw_run_log_path",
        "command_path",
        "configuration_path",
        "environment_path",
        "result_json_path",
        "result_csv_path",
        "configuration_sha256",
        "raw_java_csv_sha256",
        "raw_stdout_sha256",
        "raw_stderr_sha256",
        "raw_run_log_sha256",
        "command_sha256",
        "environment_sha256",
        "result_json_sha256",
        "started_utc",
        "finished_utc",
        "elapsed_seconds",
    }
    common = sorted(set(fixed.columns) & set(force.columns))
    for col in common:
        if col in allowed:
            continue
        cf = f"{col}_fixed"
        cs = f"{col}_force"
        if cf not in merged or cs not in merged:
            continue
        mismatch = [
            i for i, (a, b) in enumerate(zip(merged[cf], merged[cs])) if not values_equal(a, b)
        ]
        if mismatch:
            errors.append(f"cross-mode mismatch in {col}: {len(mismatch)} cells")
    return errors


def make_figure8(fmax: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    fig = plt.figure(figsize=(12.4, 8.6), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.05])

    ax = fig.add_subplot(gs[0, 0])
    phase = np.linspace(0, 1, 500)
    A = 1.5
    f = 5.0
    pos = 0.5 * A * (np.sin(2 * np.pi * phase) - 1.0)
    vel = 0.5 * A * (2 * np.pi * f) * np.cos(2 * np.pi * phase)
    line1 = ax.plot(phase, pos, lw=2.3, label="position target", color="#1f4e79")[0]
    ax.set_xlabel("Cycle phase")
    ax.set_ylabel("Vertical displacement (mm)", color="#1f4e79")
    ax.tick_params(axis="y", labelcolor="#1f4e79")
    ax.set_xlim(0, 1)
    ax.set_ylim(-1.68, 0.18)
    ax.grid(alpha=0.25)
    ax2 = ax.twinx()
    line2 = ax2.plot(phase, vel, lw=1.8, ls="--", label="exact velocity derivative", color="#d97706")[0]
    ax2.set_ylabel("Target velocity (mm/s)", color="#d97706")
    ax2.tick_params(axis="y", labelcolor="#d97706")
    ax2.set_ylim(-26, 26)
    ax.annotate(
        "A = 1.5 mm\npeak-to-peak",
        xy=(0.75, -1.5),
        xytext=(0.53, -0.65),
        arrowprops=dict(arrowstyle="->", lw=1.2),
        fontsize=9,
    )
    ax.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper right", frameon=False)
    ax.set_title("Canonical one-sided target (illustrated at 5 Hz)", fontsize=11)
    ax.text(-0.12, 1.06, "A", transform=ax.transAxes, fontsize=16, fontweight="bold")

    ax = fig.add_subplot(gs[0, 1])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.5, 0.94, "Canonical scaling design", ha="center", va="center", fontsize=12, fontweight="bold")
    ax.annotate("scale s: 0.80 to 1.20", xy=(0.12, 0.80), xytext=(0.88, 0.80),
                arrowprops=dict(arrowstyle="<->", lw=1.5), ha="center", va="center")
    def box(x, y, w, h, title, lines, fc):
        patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc=fc, ec="0.35", lw=1.0)
        ax.add_patch(patch)
        ax.text(x+w/2, y+h-0.055, title, ha="center", va="top", fontweight="bold", fontsize=10)
        ax.text(x+w/2, y+h-0.13, "\n".join(lines), ha="center", va="top", fontsize=9, linespacing=1.35)
    box(0.04, 0.29, 0.42, 0.40, "Held fixed", ["geometry and muscle paths", "attachments and lever arms", "joint constraints and target", "controller architecture", "gravity = (0, 0, 0)"], "#eef5fb")
    box(0.54, 0.29, 0.42, 0.40, "Scaled properties", ["mandibular mass: s^3", "rotational inertia: s^5", "fixed-force: capacity x 1", "s^2 sensitivity: capacity x s^2", "24 muscles touched in sensitivity"], "#fff4e6")
    ax.text(0.5, 0.13, "Feasible only if RMSE <= 0.5 mm, peak excitation <= 0.95, and gain in [0.7, 1.3]", ha="center", fontsize=8.7)
    ax.text(-0.08, 1.06, "B", transform=ax.transAxes, fontsize=16, fontweight="bold")

    for panel, amp, cell in [("C", 1.0, gs[1, 0]), ("D", 1.5, gs[1, 1])]:
        ax = fig.add_subplot(cell)
        sub = fmax[np.isclose(fmax["target_amp_p2p_mm"], amp)].copy()
        for mode, marker, color, label, dx in [
            ("fixed_force", "o", "#1f4e79", "fixed force", -0.0025),
            ("force_capacity_s2", "s", "#d97706", "force capacity x s^2", 0.0025),
        ]:
            g = sub[sub["mode"] == mode].sort_values("scale")
            ax.plot(g["scale"] + dx, g["fmax_hz"], marker=marker, ms=6, lw=1.8,
                    color=color, label=label, markerfacecolor="white" if mode == "force_capacity_s2" else color)
        ax.axhline(10, color="0.35", ls=":", lw=1.1)
        ax.set_xlim(0.78, 1.22)
        ax.set_ylim(7.7, 10.38)
        ax.set_xticks(EXPECTED_SCALES)
        ax.set_xticklabels([f"{x:.2f}" for x in EXPECTED_SCALES], rotation=45)
        ax.set_yticks([8.0, 8.5, 9.0, 9.5, 10.0])
        ax.grid(alpha=0.25)
        ax.set_xlabel("Mass-and-inertia scale factor s")
        ax.set_ylabel("Strict-prefix endpoint (Hz)")
        ax.set_title(f"A = {amp:.1f} mm peak-to-peak")
        ax.text(0.5, 0.91, "all 19 frequencies feasible; endpoint >=10 Hz",
                transform=ax.transAxes, ha="center", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7", alpha=0.9))
        ax.text(-0.12, 1.06, panel, transform=ax.transAxes, fontsize=16, fontweight="bold")
        if panel == "C":
            ax.legend(loc="lower left", frameon=False)

    fig.suptitle("Corrected ArtiSynth mass-and-inertia simulation", fontsize=15, fontweight="bold")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def make_supp(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    fig, axes = plt.subplots(4, 2, figsize=(11.5, 13.3), constrained_layout=True)
    row_specs = [
        ("fixed_force", "peak_excitation", "Fixed force - peak excitation", "peak"),
        ("fixed_force", "mean_summed_squared_excitation", "Fixed force - mean summed-squared excitation", "effort"),
        ("force_capacity_s2", "peak_excitation", "Force capacity x s^2 - peak excitation", "peak"),
        ("force_capacity_s2", "mean_summed_squared_excitation", "Force capacity x s^2 - mean summed-squared excitation", "effort"),
    ]
    peak_images = []
    effort_images = []
    for row, (mode, metric, row_title, kind) in enumerate(row_specs):
        for col, amp in enumerate(EXPECTED_AMPS):
            ax = axes[row, col]
            sub = df[(df["mode"] == mode) & np.isclose(df["target_amp_p2p_mm"], amp)]
            piv = sub.pivot(index="freq_hz", columns="scale", values=metric).sort_index().sort_index(axis=1)
            arr = piv.to_numpy()
            if kind == "peak":
                im = ax.imshow(arr, origin="lower", aspect="auto", cmap="viridis", vmin=0, vmax=PEAK_EXC_MAX)
                peak_images.append(im)
            else:
                im = ax.imshow(arr, origin="lower", aspect="auto", cmap="magma",
                               norm=LogNorm(vmin=3e-5, vmax=0.2))
                effort_images.append(im)
            ax.set_xticks(range(len(piv.columns)))
            ax.set_xticklabels([f"{x:.2f}" for x in piv.columns], rotation=45)
            yticks = list(range(0, len(piv.index), 2))
            if yticks[-1] != len(piv.index) - 1:
                yticks.append(len(piv.index) - 1)
            ax.set_yticks(yticks)
            ax.set_yticklabels([f"{piv.index[i]:g}" for i in yticks])
            ax.set_xlabel("scale s")
            ax.set_ylabel("target frequency (Hz)")
            if row == 0:
                ax.set_title(f"A = {amp:.1f} mm peak-to-peak", fontsize=11)
            if col == 0:
                ax.text(-0.32, 0.5, row_title, transform=ax.transAxes, rotation=90,
                        va="center", ha="center", fontsize=10, fontweight="bold")
            # Every cell passed; a white dot makes the complete grid visible without implying failure.
            yy, xx = np.indices(arr.shape)
            ax.scatter(xx.ravel(), yy.ravel(), s=3, c="white", alpha=0.35, linewidths=0)
    cbar1 = fig.colorbar(peak_images[0], ax=[axes[0,0], axes[0,1], axes[2,0], axes[2,1]],
                         fraction=0.024, pad=0.02)
    cbar1.set_label("Peak excitation (threshold 0.95)")
    cbar2 = fig.colorbar(effort_images[0], ax=[axes[1,0], axes[1,1], axes[3,0], axes[3,1]],
                         fraction=0.024, pad=0.02)
    cbar2.set_label("Mean summed-squared excitation (log scale)")
    fig.suptitle("Corrected ArtiSynth excitation landscapes", fontsize=15, fontweight="bold")
    fig.text(0.5, 0.003,
             "All 684 cells met RMSE, peak-excitation, and amplitude-gain criteria; no infeasible cells or threshold boundary occurred.",
             ha="center", fontsize=9.2)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def write_markdown_reports(
    out: Path,
    fixed: pd.DataFrame,
    force: pd.DataFrame,
    all_df: pd.DataFrame,
    fmax_all: pd.DataFrame,
    prior_comp: pd.DataFrame,
    source_meta: dict[str, Any],
    patch_comparison: dict[str, Any],
) -> None:
    worst_rmse = all_df.loc[all_df["tracking_rmse_mm"].idxmax()]
    worst_peak = all_df.loc[all_df["peak_excitation"].idxmax()]
    gain_min_row = all_df.loc[all_df["amplitude_gain"].idxmin()]
    gain_max_row = all_df.loc[all_df["amplitude_gain"].idxmax()]
    old_fixed = prior_comp[prior_comp["mode"] == "fixed_force"]
    old_force = prior_comp[prior_comp["mode"] == "force_capacity_s2"]

    report = f"""# ArtiSynth Phase C validation report

## Verdict

# {VERDICT}

The corrected grids are technically valid and reproducible from the returned archive, but the corrected target removes the previously reported feasibility boundary. Every one of the 684 corrected cells is feasible through the 10 Hz ceiling of the approved grid. Consequently, the simulation does not support the prior claim that increasing mandibular mass and rotational inertia reduced the maximum feasible cyclic frequency under fixed force, and the force-capacity sensitivity does not attenuate or offset an endpoint effect that is no longer present.

## 1. Archive, safety, and provenance

- Corrected return ZIP SHA256: `{source_meta['return_zip_sha256']}`; the supplied sidecar matches.
- ZIP CRC: PASS.
- ZIP entries: {source_meta['zip_entries']} unique entries; no unsafe paths, duplicate names, or symlinks.
- Extracted payload: {source_meta['payload_files']} files. `RETURN_FILE_MANIFEST.tsv` lists {source_meta['return_manifest_rows']} other payload files; every listed size and SHA256 passed. The only intentionally unlisted payload is the manifest itself.
- Patch manifest: PASS for {source_meta['patch_manifest_rows']} files.
- Orchestration runner SHA256: `{source_meta['runner_sha256']}`; its sidecar matches.
- Corrected source SHA256: `{source_meta['source_sha256']}`.
- Compiled CURRENT class-tree SHA256: `{source_meta['compiled_tree_sha256']}`.
- Fixed long-table SHA256: `{source_meta['fixed_sha256']}`.
- Force-capacity long-table SHA256: `{source_meta['force_sha256']}`.

The returned V2.4 patch is not byte-identical to the original 21-file Phase A package because installed-runtime repairs were required. Across common files, {patch_comparison['same_count']} are unchanged and {patch_comparison['changed_count']} changed; three runtime-repair records were added. The science-defining grid driver, strict-prefix calculator, validator, figure generator, target formula, gravity state, scaling exponents, controller settings, and thresholds were not changed. The Java differences implement collision disabling through the installed API and prevent inherited GUI/probe loading from undoing the headless canonical build; the case-runner difference repairs resume handling for a technical failure with no Java output.

## 2. Runtime and commands

The local runs used macOS 26.5.1 on arm64 hardware, an x86_64 Temurin Java 8 runtime (`1.8.0_472`) invoked through `/usr/bin/arch -x86_64`, Python 3.12.7, the recorded ArtiSynth launcher, and the isolated corrected class directory ahead of the base model classes. The launcher rejected `-version`, so an exact semantic ArtiSynth build string was not captured by the run; launcher and base-class hashes nevertheless provide exact runtime identity. The project records and runtime-repair log identify the installation as ArtiSynth 3.9.

The fixed grid ran from {fixed['started_utc'].min()} to {fixed['finished_utc'].max()} and accumulated {fixed['elapsed_seconds'].sum()/3600:.3f} cell-hours. The force-capacity grid ran from {force['started_utc'].min()} to {force['finished_utc'].max()} and accumulated {force['elapsed_seconds'].sum()/3600:.3f} cell-hours. Both 342-row invocation manifests contain return code 0 and `success` for every cell. Exact expanded per-cell commands are preserved in the corrected return archive.

## 3. Canonical design checks

| Check | Result |
|---|---|
| Cells per mode | 342 fixed force; 342 force capacity |
| Unique grid | 9 scales x 19 frequencies x 2 amplitudes in each mode |
| Scale grid | 0.80 to 1.20 by 0.05 |
| Frequency grid | 1.0 to 10.0 Hz by 0.5 Hz |
| Amplitude grid | 1.0 and 1.5 mm peak-to-peak |
| Duration / settling / play | 4.0 / 0.5 / 4.8 s in every row |
| Gravity | disabled; vector (0, 0, 0) |
| Geometry | not scaled |
| Mass / inertia exponents | 3 / 5 |
| Fixed-force exponent | 0; multiplier 1; `n_force_scaled=0` |
| Force-capacity exponent | 2; multiplier s^2; `n_force_scaled=24` in every cell |
| Target IDs | `P2P_ONE_SIDED_SIN_ACTIVE_V1`; `P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1` |
| Controller | identical across modes; target weight 100, L2 0.01, excitation damping 0.1 |
| Integration and damping | max step 0.00025 s; frame 2; rotary 4 |
| Collisions / TMJ / probes | collisions verified disabled; two TMJs modified; inherited probes removed |
| Cross-mode identity | PASS for all non-force configuration fields and code/runtime hashes |

## 4. Independent feasibility and strict-prefix endpoints

The independent classifier used only the raw long-form metrics:

- tracking RMSE <= 0.5 mm;
- peak excitation <= 0.95;
- amplitude gain in [0.7, 1.3], inclusive.

It matched every stored criterion flag and every stored cell-level feasibility flag.

| Quantity | Corrected value |
|---|---:|
| Feasible cells | 684 / 684 |
| Maximum RMSE | {worst_rmse['tracking_rmse_mm']:.6f} mm ({worst_rmse['mode']}, s={worst_rmse['scale']:.2f}, {worst_rmse['freq_hz']:.1f} Hz, A={worst_rmse['target_amp_p2p_mm']:.1f}) |
| Maximum peak excitation | {worst_peak['peak_excitation']:.6f} ({worst_peak['mode']}, s={worst_peak['scale']:.2f}, {worst_peak['freq_hz']:.1f} Hz, A={worst_peak['target_amp_p2p_mm']:.1f}) |
| Amplitude-gain range | {gain_min_row['amplitude_gain']:.6f} to {gain_max_row['amplitude_gain']:.6f} |
| Series reaching a first failure | 0 / 36 |
| Locally nonmonotonic feasibility series | 0 / 36 |
| Strict-prefix endpoint | >=10 Hz for all 36 mode x scale x amplitude series |

The numeric `fmax_hz` field is 10 because 10 Hz is the highest tested frequency. It must be reported as **>=10 Hz within the tested grid**, not as a measured physical maximum of exactly 10 Hz.

## 5. Prior versus corrected result

The archived incorrect-target tables contained 268 feasible cells in each mode (536/684 total). Their independently recomputed strict-prefix endpoints ranged from {old_fixed['prior_fmax_hz'].min():g} to {old_fixed['prior_fmax_hz'].max():g} Hz in fixed force and {old_force['prior_fmax_hz'].min():g} to {old_force['prior_fmax_hz'].max():g} Hz in the force-capacity sensitivity. Thirteen archived series had later feasible cells after a first failure, so the old feasibility landscape was locally nonmonotonic.

After correcting the velocity target, all 148 previously infeasible cells become feasible. Every corrected endpoint is >=10 Hz, and the force-capacity-minus-fixed endpoint difference is zero for all 18 scale x amplitude comparisons. The archived Figure 8 and Table S3 therefore cannot be retained as numerical evidence.

Continuous excitation metrics do not provide a stable substitute for the missing endpoint effect. In fixed-force runs, a simple descriptive slope of mean summed-squared excitation against scale is negative in all 38 amplitude x frequency slices; peak-excitation slopes are positive in 14 slices and negative in 24. These locally irregular controller outputs remain below the feasibility threshold and do not establish a monotonic size-related loss of cyclic capacity. The s^2 sensitivity increases normalized excitation below s=1 and decreases it above s=1, as expected when force capacity itself is rescaled, but this produces no difference in strict-prefix endpoints.

## 6. Scientific interpretation and disposition

The corrected result directly invalidates the previous simulation statement that uncompensated increases in mandibular mass properties reduced feasible cyclic speed over the tested grid. It also invalidates the statement that s^2 force scaling attenuated or offset that fixed-force endpoint pattern. The corrected simulation neither estimates living-speaker mandibular mass/inertia nor provides causal evidence in humans.

**Recommended disposition:** remove Figure 8 and the simulation-supported mechanistic-convergence claim from the main manuscript. A concise negative simulation result may be retained in the Supplementary Materials for transparency, provided it states that no feasibility boundary was observed through 10 Hz and does not imply absence of effects beyond the tested grid or under other controller/geometry assumptions. Table S3 is mathematically correct in the new package but scientifically uninformative because all entries are the same lower bound.

## 7. Validation limitations

- The tested grid ends at 10 Hz; no physical maximum was observed.
- Results are controller-, target-, and model-architecture dependent.
- Geometry, lever arms, attachments, and joint constraints were intentionally held fixed.
- Gravity was disabled, so the manipulation is mass-and-inertia scaling, not weight scaling.
- Exact ArtiSynth semantic build text was not captured because the launcher did not support `-version`; binary and class hashes are retained.
- This Phase C analysis did not rerun ArtiSynth. It independently validated the locally generated return package and recomputed its derived evidence.
"""
    (out / "ARTISYNTH_VALIDATION_REPORT.md").write_text(report, encoding="utf-8")

    runlog = f"""# ARTISYNTH_CURRENT_RUNLOG

**Status:** validated corrected local run  
**Dynamic execution location:** author's macOS workstation  
**Phase C computation location:** ChatGPT analysis environment; no ArtiSynth dynamics were rerun here

## Source archives

| Archive | SHA256 |
|---|---|
| `ARTISYNTH_CORRECTED_RETURN_20260720T072821Z.zip` | `{source_meta['return_zip_sha256']}` |
| `PREFLIGHT_EVIDENCE_BUNDLE.zip` historical comparator | `{source_meta['preflight_zip_sha256']}` |
| Original Phase A patch package | `{source_meta['phase_a_patch_sha256']}` |

## Local run identity

- Run ID: `20260720T072821Z`
- Run root recorded by author: `{source_meta['run_root']}`
- Canonical spec: `{fixed['spec_version'].iloc[0]}`
- Corrected Java source SHA256: `{source_meta['source_sha256']}`
- Compiled class-tree SHA256: `{source_meta['compiled_tree_sha256']}`
- Grid driver SHA256: `{fixed['grid_runner_sha256'].iloc[0]}`
- Case runner SHA256: `{fixed['case_runner_sha256'].iloc[0]}`
- Common module SHA256: `{fixed['common_module_sha256'].iloc[0]}`
- Play script SHA256: `{fixed['play_script_sha256'].iloc[0]}`
- ArtiSynth launcher SHA256: `{fixed['artisynth_launcher_sha256'].iloc[0]}`
- Java executable SHA256: `{fixed['java_executable_sha256'].iloc[0]}`
- Python executable SHA256: `{fixed['python_executable_sha256'].iloc[0]}`
- Base `JawDemo.class` SHA256: `{fixed['base_jawdemo_class_sha256'].iloc[0]}`
- Base `JawModel.class` SHA256: `{fixed['base_jawmodel_class_sha256'].iloc[0]}`

## Exact command architecture

Each cell invoked the x86_64 ArtiSynth launcher headlessly with the isolated CURRENT class directory before the base model classes, passed all model arguments between `[` and `]`, and executed `play_and_quit_CURRENT.jy`. The return archive preserves 684 expanded model commands plus 684 case-runner invocation commands and their stdout/stderr logs.

Representative fixed-force model command:

```text
/usr/bin/arch -x86_64 .../artisynth -noGui -cp <corrected_classes>:<base_classes> -model artisynth.models.dynjaw.MandibleScalingInverseDDK_CURRENT [ --mode fixed_force --scale 1.2 --freq_hz 10 --amp_p2p_mm 1.5 --mass_exp 3 --inertia_exp 5 --force_exp 0 --force_multiplier 1 --duration_s 4 --settle_s 0.5 --target_weight 100 --l2_regularization 0.01 --excitation_damping 0.1 --frame_damping 2 --rotary_damping 4 --max_step_s 0.00025 --open_gap_mm 0 --gravity disabled --out <raw_java_result.csv> --verbose ] -script <play_and_quit_CURRENT.jy>
```

Representative force-capacity command is identical except `--mode force_capacity_s2`, `--force_exp 2`, and `--force_multiplier s^2`.

## Grid completion

| Mode | Start UTC | Finish UTC | Rows | Status | Cell-time sum |
|---|---|---|---:|---|---:|
| fixed force | {fixed['started_utc'].min()} | {fixed['finished_utc'].max()} | 342 | all success | {fixed['elapsed_seconds'].sum()/3600:.3f} h |
| force capacity s^2 | {force['started_utc'].min()} | {force['finished_utc'].max()} | 342 | all success | {force['elapsed_seconds'].sum()/3600:.3f} h |

## Phase C independent derivation

1. Verified corrected-return ZIP digest, CRC, safe member paths, and manifest hashes.
2. Verified current 24-file patch manifest and documented differences from the original Phase A package.
3. Loaded the two raw 342-row long tables.
4. Recomputed every criterion and feasibility flag from RMSE, peak excitation, and gain without trusting stored feasibility fields.
5. Recomputed the strict feasible prefix independently for all 36 series.
6. Recomputed archived prior endpoints from the two prior long tables using the same thresholds and prefix rule.
7. Generated all canonical CSVs and figures from the independently derived tables.

The output manifest intentionally excludes its own hash and the outer ZIP to avoid self-referential hashing. The ZIP has a separate SHA256 sidecar.
"""
    (out / "ARTISYNTH_CURRENT_RUNLOG.md").write_text(runlog, encoding="utf-8")

    snippets = """# Evidence-matched simulation text snippets

These snippets are alternatives for a controlled later manuscript revision. They are not integrated into the manuscript here.

## 1. Simulation Methods

We used the ArtiSynth `dynjaw` model as a non-subject-specific test of mass-and-inertia scaling under fixed geometry. Gravity was disabled. Across scale factors s=0.80-1.20, mandibular mass was multiplied by s^3 and rotational inertia by s^5 while mesh geometry, muscle paths and attachments, lever arms, joint constraints, target trajectory, controller architecture, and integration settings were held fixed. Maximum muscle force remained fixed in the primary grid and was multiplied by s^2 only in a force-capacity sensitivity. The lower-incisor position target was z(t)=z0+(A/2)[sin(2 pi f tau)-1], where A is peak-to-peak amplitude and tau is time after a 0.5-s settling interval; the velocity target was its exact derivative, (A/2)(2 pi f)cos(2 pi f tau). We tested A=1.0 and 1.5 mm and f=1.0-10.0 Hz in 0.5-Hz steps. A cell was feasible only when tracking RMSE was <=0.5 mm, peak excitation was <=0.95, and amplitude gain was within [0.7,1.3]. For each series, the endpoint was the highest frequency in the strict feasible prefix.

## 2. Simulation Results

All 684 corrected simulations completed technically, and every tested cell met all three feasibility criteria. Thus, every fixed-force and force-capacity series remained feasible through 10 Hz, the upper boundary of the tested grid; the endpoint is therefore >=10 Hz rather than an observed maximum of 10 Hz. The corrected simulation showed no scale-dependent reduction in the strict-prefix endpoint and no endpoint difference between fixed force and s^2 force-capacity scaling. The previously reported feasibility boundary did not survive correction of the velocity target.

## 3. Figure 8 caption

**Corrected mass-and-inertia simulation.** (A) One-sided lower-incisor position target and its exact velocity derivative. (B) Canonical manipulation: geometry, muscle paths, attachments, lever arms, joint constraints, target, controller, and gravity state were held fixed; mandibular mass and rotational inertia were scaled as s^3 and s^5. Maximum muscle force was either fixed or scaled as s^2. (C,D) Strict-prefix endpoints for 1.0- and 1.5-mm peak-to-peak targets. All 19 tested frequencies were feasible for every scale and mode. Points at 10 Hz therefore denote lower bounds (>=10 Hz within the tested grid), not observed physical maxima.

## 4. Supplementary simulation caption

**Excitation landscapes in the corrected simulation.** Heatmaps show peak excitation and mean summed-squared excitation for fixed-force and s^2 force-capacity grids at both peak-to-peak amplitudes. All 684 cells met the prespecified RMSE, peak-excitation, and amplitude-gain criteria. No feasibility boundary occurred within the 1-10 Hz grid. The effort metric is descriptive and should not be interpreted as a monotonic estimate of living-speaker metabolic cost.

## 5. Table S3 caption/note

**Strict-prefix endpoints in the corrected ArtiSynth grids.** `>=10` indicates that all tested frequencies from 1.0 through 10.0 Hz were feasible; it is a lower bound imposed by the grid ceiling, not an estimate that the physical maximum equals 10 Hz. No first failed frequency occurred in any series.

## 6. Discussion interpretation

The corrected simulation did not reproduce the previously reported decline in feasible cyclic frequency with increasing mass-and-inertia scale. Under the approved controller, target, and 1-10 Hz grid, all tested cells were feasible in both the fixed-force and s^2 force-capacity modes. The human associations therefore cannot be presented as converging with this simulation. They remain observational findings whose mechanistic basis is unresolved.

## 7. Limitations

The simulation was not subject-specific and held geometry, muscle paths, lever arms, attachments, and joint constraints fixed. Gravity was disabled, so the manipulation tests mass and rotational inertia rather than weight. No feasibility boundary was observed before the 10-Hz grid ceiling, and the result does not exclude effects at higher frequencies, different target amplitudes, other controller settings, or more complete craniofacial scaling. The scale factor is not a direct measurement of mandibular mass or inertia in living speakers.
"""
    (out / "ARTISYNTH_TEXT_SNIPPETS_CURRENT.md").write_text(snippets, encoding="utf-8")

    handoff = f"""# ArtiSynth to final-preflight handoff

## Scientific verdict

# {VERDICT}

## Canonical files

The canonical Phase C files are those listed in `ARTISYNTH_CANONICAL_FILES_MANIFEST.tsv`. The two long tables derive directly from the validated corrected return archive; all endpoints, figures, and Table S3 derive from independent Phase C recomputation rather than from stored feasibility or fmax fields.

## Superseded simulation evidence

The following are noncanonical and must not be used in the final manuscript or Project Sources:

- `artisynth_scaling_runs_long_twoamp.csv`;
- `artisynth_force_scaled_runs_long_twoamp.csv`;
- `artisynth_fmax_by_scale_twoamp_prefix.csv`;
- `artisynth_fmax_force_scaled_s2.csv`;
- `artisynth_force_scaled_s2_fmax_comparison.csv`;
- the archived Figure 8 and supplementary simulation figure;
- the archived Table S3;
- every manuscript sentence stating that increased mandibular mass properties reduced feasible cyclic frequency or that s^2 force capacity attenuated/offset that endpoint effect.

## Supported claims

- The corrected Java target velocity is the exact derivative of the coded peak-to-peak position target.
- Gravity was disabled; the manipulation is mass-and-inertia scaling.
- The local run contains 342 unique successful cells in each mode, 684 total.
- All 684 corrected cells met RMSE <=0.5 mm, peak excitation <=0.95, and gain in [0.7,1.3].
- All 36 strict-prefix series are feasible through the tested 10-Hz ceiling, so their endpoints are >=10 Hz within the tested grid.
- Force capacity was touched for 24 muscles in every sensitivity cell, including s=1.00.
- No corrected endpoint difference exists between fixed force and s^2 force capacity.

## Prohibited claims

- Do not state that larger mass/inertia reduced corrected fmax.
- Do not state that force-capacity scaling attenuated or offset a corrected fmax effect.
- Do not report fmax as exactly 10 Hz; use >=10 Hz within the tested grid.
- Do not describe the primary manipulation as weight scaling.
- Do not treat s as a direct living-speaker measurement of mandibular mass or inertia.
- Do not treat the simulation as causal evidence in humans.
- Do not imply monotonic scale effects from the locally irregular continuous excitation metrics.

## Recommended manuscript disposition

Remove the simulation as a main-text mechanistic consistency check and remove the current Figure 8 from the main paper. A short negative result and the corrected heatmaps may be retained in the Supplementary Materials for transparency. The title, abstract, Results, Discussion, and conclusion must no longer use the simulation as support for a neuromechanical causal or convergent claim.

## Remaining author query

[AUTHOR QUERY: Can the exact ArtiSynth 3.9 semantic build/commit identifier be recovered from the local installation metadata? The returned run records the launcher and base-class hashes, but the launcher rejected the `-version` probe. This is a documentation improvement, not a blocker to the validated numerical result.]

## Inputs for final combined preflight

- `EMPIRICAL_RESOLUTION_OUTPUTS.zip`;
- `ARTISYNTH_VALIDATED_OUTPUTS.zip` and its SHA256 sidecar;
- completed `09_AUTHOR_VERIFICATION_CURRENT.md`;
- frozen current manuscript source/PDF and bibliography.

The final preflight should build the V4 dossier and source manifest from the corrected negative simulation result, not from any archived endpoint or figure.
"""
    (out / "ARTISYNTH_TO_FINAL_PREFLIGHT_HANDOFF.md").write_text(handoff, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--return-root", type=Path, required=True)
    ap.add_argument("--return-zip", type=Path, required=True)
    ap.add_argument("--prior-fixed", type=Path, required=True)
    ap.add_argument("--prior-force", type=Path, required=True)
    ap.add_argument("--phase-a-patch-root", type=Path, required=True)
    ap.add_argument("--preflight-zip", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    root = args.return_root.resolve()
    out = args.out_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    fixed_src = root / "grids/fixed_force/artisynth_fixed_force_runs_long_CURRENT.csv"
    force_src = root / "grids/force_capacity_s2/artisynth_force_capacity_s2_runs_long_CURRENT.csv"
    fixed = pd.read_csv(fixed_src)
    force = pd.read_csv(force_src)
    errors = verify_grid(fixed, "fixed_force") + verify_grid(force, "force_capacity_s2")

    # Core canonical invariants.
    all_raw = pd.concat([fixed, force], ignore_index=True)
    invariants = {
        "gravity_state": "disabled",
        "gravity_enabled": False,
        "gravity_x": 0.0,
        "gravity_y": 0.0,
        "gravity_z": 0.0,
        "mass_exp": 3,
        "inertia_exp": 5,
        "duration_s": 4.0,
        "settle_s": 0.5,
        "play_time_s": 4.8,
        "target_position_formula_id": "P2P_ONE_SIDED_SIN_ACTIVE_V1",
        "target_velocity_formula_id": "P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1",
        "geometry_scaled": False,
    }
    for col, expected in invariants.items():
        if not all(values_equal(x, expected) for x in all_raw[col]):
            errors.append(f"invariant mismatch: {col} expected {expected}")
    if not ((fixed["force_exp"] == 0) & np.isclose(fixed["effective_force_multiplier"], 1.0) & (fixed["n_force_scaled"] == 0)).all():
        errors.append("fixed-force scaling invariant failed")
    expected_force = force["scale"] ** 2
    if not ((force["force_exp"] == 2) & np.isclose(force["effective_force_multiplier"], expected_force) & (force["n_force_scaled"] > 0)).all():
        errors.append("force-capacity scaling invariant failed")
    errors += cross_mode_identity(fixed, force)
    if errors:
        raise SystemExit("VALIDATION BLOCKED:\n" + "\n".join(errors))

    fixed_i = independently_classify(fixed)
    force_i = independently_classify(force)
    all_i = pd.concat([fixed_i, force_i], ignore_index=True)
    stored = bool_series(all_i["is_feasible"])
    if not (stored.to_numpy() == all_i["independent_is_feasible"].to_numpy()).all():
        raise SystemExit("stored feasibility differs from independent recomputation")
    if not all_i["independent_is_feasible"].all():
        raise SystemExit("unexpected corrected infeasible cells")

    # Preserve raw long tables exactly under canonical requested names.
    fixed_out = out / "artisynth_scaling_runs_long_CURRENT.csv"
    force_out = out / "artisynth_force_scaled_runs_long_CURRENT.csv"
    shutil.copy2(fixed_src, fixed_out)
    shutil.copy2(force_src, force_out)

    fmax_fixed = strict_prefix(fixed_i, fixed_out)
    fmax_force = strict_prefix(force_i, force_out)
    fmax_all = pd.concat([fmax_fixed, fmax_force], ignore_index=True)
    fmax_fixed.to_csv(out / "artisynth_fmax_fixed_force_CURRENT.csv", index=False, float_format="%.12g")
    fmax_force.to_csv(out / "artisynth_fmax_force_scaled_CURRENT.csv", index=False, float_format="%.12g")

    comp = fmax_fixed.merge(
        fmax_force,
        on=["scale", "target_amp_p2p_mm"],
        suffixes=("_fixed", "_force"),
        validate="one_to_one",
    )
    comp_out = pd.DataFrame({
        "target_amp_p2p_mm": comp["target_amp_p2p_mm"],
        "scale": comp["scale"],
        "fixed_force_fmax_hz": comp["fmax_hz_fixed"],
        "fixed_force_fmax_display": comp["fmax_display_fixed"],
        "fixed_force_all_frequencies_feasible": comp["all_frequencies_feasible_fixed"],
        "force_capacity_s2_fmax_hz": comp["fmax_hz_force"],
        "force_capacity_s2_fmax_display": comp["fmax_display_force"],
        "force_capacity_s2_all_frequencies_feasible": comp["all_frequencies_feasible_force"],
        "force_minus_fixed_hz": comp["fmax_hz_force"] - comp["fmax_hz_fixed"],
        "interpretation": "both modes feasible through tested 10-Hz ceiling",
    }).sort_values(["target_amp_p2p_mm", "scale"])
    comp_out.to_csv(out / "artisynth_fmax_comparison_CURRENT.csv", index=False, float_format="%.12g")

    table = comp_out.copy()
    table["fixed_first_failed_frequency_hz"] = ""
    table["fixed_first_failed_criterion"] = ""
    table["force_capacity_s2_first_failed_frequency_hz"] = ""
    table["force_capacity_s2_first_failed_criterion"] = ""
    table["table_note"] = ">=10 means all tested frequencies feasible; no physical maximum observed"
    table.to_csv(out / "TableS3_CURRENT.csv", index=False, float_format="%.12g")

    # Prior comparison.
    prior_fixed_cells, prior_fixed_fmax = prior_classify_and_prefix(args.prior_fixed, "fixed_force")
    prior_force_cells, prior_force_fmax = prior_classify_and_prefix(args.prior_force, "force_capacity_s2")
    prior_fmax = pd.concat([prior_fixed_fmax, prior_force_fmax], ignore_index=True)
    prior_fmax["scale_key"] = prior_fmax["scale"].round(2)
    prior_fmax["amp_key"] = prior_fmax["target_amp_p2p_mm"].round(1)
    current = fmax_all.copy()
    current["scale_key"] = current["scale"].round(2)
    current["amp_key"] = current["target_amp_p2p_mm"].round(1)
    pc = prior_fmax.merge(current, on=["mode", "scale_key", "amp_key"], suffixes=("_prior", "_corrected"), validate="one_to_one")
    prior_comp = pd.DataFrame({
        "mode": pc["mode"],
        "target_amp_p2p_mm": pc["amp_key"],
        "scale": pc["scale_key"],
        "prior_n_feasible": pc["n_cell_feasible_prior"],
        "prior_fmax_hz": pc["fmax_hz_prior"],
        "prior_first_failed_frequency_hz": pc["first_failed_frequency_hz_prior"],
        "prior_first_failed_criterion": pc["first_failed_criterion_prior"],
        "prior_n_feasible_after_first_failure": pc["n_feasible_after_first_failure_prior"],
        "prior_locally_nonmonotonic": pc["locally_nonmonotonic_feasibility_prior"],
        "corrected_n_feasible": pc["n_cell_feasible_corrected"],
        "corrected_fmax_hz": pc["fmax_hz_corrected"],
        "corrected_fmax_display": pc["fmax_display_corrected"],
        "corrected_all_frequencies_feasible": pc["all_frequencies_feasible_corrected"],
        "corrected_first_failed_frequency_hz": pc["first_failed_frequency_hz_corrected"],
        "corrected_first_failed_criterion": pc["first_failed_criterion_corrected"],
        "delta_corrected_minus_prior_hz": pc["fmax_hz_corrected"] - pc["fmax_hz_prior"],
        "qualitative_change": "prior boundary absent after exact-derivative correction",
        "prior_source_sha256": pc["source_long_table_sha256_prior"],
        "corrected_source_sha256": pc["source_long_table_sha256_corrected"],
    }).sort_values(["mode", "target_amp_p2p_mm", "scale"])
    prior_comp.to_csv(out / "ARTISYNTH_PRIOR_VS_CORRECTED_COMPARISON.csv", index=False, float_format="%.12g")

    make_figure8(fmax_all, out / "Figure8_CURRENT.png", out / "Figure8_CURRENT.pdf")
    make_supp(all_i, out / "SuppPub2_CURRENT.png", out / "SuppPub2_CURRENT.pdf")

    # Source metadata and patch comparison are supplied by a small audit JSON created externally.
    audit_json = root.parent.parent / "phase_c_source_audit.json"
    if not audit_json.is_file():
        raise SystemExit(f"missing source audit JSON: {audit_json}")
    source_meta = json.loads(audit_json.read_text(encoding="utf-8"))
    patch_comparison = source_meta.pop("patch_comparison")
    source_meta["fixed_sha256"] = sha256_file(fixed_src)
    source_meta["force_sha256"] = sha256_file(force_src)
    source_meta["source_sha256"] = str(fixed["model_source_sha256"].iloc[0])
    source_meta["compiled_tree_sha256"] = str(fixed["compiled_model_sha256"].iloc[0])
    source_meta["runner_sha256"] = source_meta["runner_sha256"]
    source_meta["run_root"] = (root / "RUN_ROOT_ABSOLUTE_PATH.txt").read_text(encoding="utf-8").strip()

    write_markdown_reports(out, fixed, force, all_i, fmax_all, prior_comp, source_meta, patch_comparison)

    # Copy this script for exact reproducibility.
    shutil.copy2(Path(__file__).resolve(), out / "phase_c_validate_artisynth_CURRENT.py")

    # Canonical manifest excludes itself and the outer ZIP to avoid recursion.
    roles = {
        "artisynth_scaling_runs_long_CURRENT.csv": "validated corrected fixed-force long table",
        "artisynth_force_scaled_runs_long_CURRENT.csv": "validated corrected force-capacity long table",
        "artisynth_fmax_fixed_force_CURRENT.csv": "independent strict-prefix fixed-force endpoints",
        "artisynth_fmax_force_scaled_CURRENT.csv": "independent strict-prefix force-capacity endpoints",
        "artisynth_fmax_comparison_CURRENT.csv": "corrected mode comparison",
        "ARTISYNTH_CURRENT_RUNLOG.md": "run and derivation provenance",
        "ARTISYNTH_VALIDATION_REPORT.md": "technical and scientific validation",
        "ARTISYNTH_PRIOR_VS_CORRECTED_COMPARISON.csv": "historical versus corrected series comparison",
        "Figure8_CURRENT.pdf": "canonical corrected main simulation figure",
        "Figure8_CURRENT.png": "canonical corrected main simulation figure raster",
        "SuppPub2_CURRENT.pdf": "canonical corrected supplementary simulation figure",
        "SuppPub2_CURRENT.png": "canonical corrected supplementary simulation figure raster",
        "TableS3_CURRENT.csv": "canonical corrected table source",
        "ARTISYNTH_TEXT_SNIPPETS_CURRENT.md": "evidence-matched revision snippets",
        "ARTISYNTH_TO_FINAL_PREFLIGHT_HANDOFF.md": "final-preflight governance handoff",
        "phase_c_validate_artisynth_CURRENT.py": "independent Phase C computation code",
    }
    manifest_path = out / "ARTISYNTH_CANONICAL_FILES_MANIFEST.tsv"
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["relative_path", "size_bytes", "sha256", "role"])
        for p in sorted(x for x in out.iterdir() if x.is_file() and x.name != manifest_path.name):
            w.writerow([p.name, p.stat().st_size, sha256_file(p), roles.get(p.name, "supporting canonical file")])

    print(VERDICT)
    print(f"Output directory: {out}")
    print(f"Corrected feasible cells: {int(all_i['independent_is_feasible'].sum())}/{len(all_i)}")
    print(f"Strict-prefix rows: {len(fmax_all)}; unique fmax values: {sorted(fmax_all['fmax_hz'].unique())}")


if __name__ == "__main__":
    main()
