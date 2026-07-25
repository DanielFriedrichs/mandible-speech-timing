#!/usr/bin/env python3
"""
Mandible dimensions vs syllable production rate
===============================================

Goal
----
Estimate whether between-speaker differences in *mandible size* (caliper measures)
are associated with differences in *syllable production rate* in DDK tasks.

This script is designed for your dataset organisation (Data folder containing the CSVs)
and produces:

- a cleaned, merged analysis dataset
- descriptive tables
- high-quality figures (PNG + PDF)
- cluster-robust regression results (GEE) for inference

Why GEE (Generalized Estimating Equations)?
------------------------------------------
Pure-Python mixed-effects fits can be fragile for this kind of design
(many trials, small N participants, strong within-subject factors).
GEE provides participant-cluster-robust standard errors and is stable in statsmodels.

Inputs (expected in --data_dir)
-------------------------------
- praat_info_corpus_ema-eeg.csv
- anatomy_measurements.csv
- metadata.csv

Outputs (written to --out_dir)
------------------------------
- analysis_dataset_clean.csv
- tables/*.csv
- models/<outcome>/*.txt + tidy coefficient tables
- figures/*.png and figures/*.pdf

"""

from __future__ import annotations

import argparse
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

import statsmodels.api as sm
import statsmodels.formula.api as smf
import patsy


# -----------------------------
# Plot style
# -----------------------------

def set_plot_style() -> None:
    """Set a clean, publication-friendly matplotlib style."""
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.size": 12,
        "axes.titlesize": 13,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def save_fig(fig: plt.Figure, out_path_no_suffix: Path) -> None:
    out_path_no_suffix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path_no_suffix.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(out_path_no_suffix.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def find_in_data_dir(data_dir: Path, filename: str) -> Path:
    """Locate a metadata file either directly in data_dir or in data_dir/docs.

    Your SWISSUbase dataset layout uses dataset_root/docs/ for metadata tables,
    but during development you may also keep copies directly in the data_dir.
    """
    p1 = data_dir / filename
    if p1.exists():
        return p1
    p2 = data_dir / "docs" / filename
    if p2.exists():
        return p2
    raise FileNotFoundError(
        f"Could not find '{filename}' in '{data_dir}' or '{data_dir / 'docs'}'. "
        "If you copied the full dataset, pass --data_dir pointing to the dataset root."
    )


# -----------------------------
# soundname parsing
# -----------------------------

@dataclass(frozen=True)
class ParsedSoundname:
    speaker: str
    sequence: str
    rate: str
    trial: int

    @property
    def participant_id(self) -> str:
        return f"sub-{self.speaker.zfill(3)}"


SOUNDNAME_RE = re.compile(
    r"^(?P<speaker>\d+)-(?P<sequence>.+?)-(?P<rate>normal|fast)-(?P<trial>\d+)$"
)


def parse_soundname(soundname: str) -> ParsedSoundname:
    """Parse soundname like: 055-bibibi-normal-10."""
    m = SOUNDNAME_RE.match(soundname)
    if not m:
        raise ValueError(
            f"soundname does not match expected pattern '<ID>-<sequence>-<normal|fast>-<number>': {soundname}"
        )
    return ParsedSoundname(
        speaker=m.group("speaker"),
        sequence=m.group("sequence"),
        rate=m.group("rate"),
        trial=int(m.group("trial")),
    )


# -----------------------------
# Loading
# -----------------------------

def load_praat_info(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "soundname", "nsyll", "npause", "dur", "phonationtime",
        "speechrate", "articulationrate", "asd"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")

    parsed = df["soundname"].apply(parse_soundname)
    df["speaker"] = parsed.apply(lambda p: p.speaker)
    df["participant_id"] = parsed.apply(lambda p: p.participant_id)
    df["sequence"] = parsed.apply(lambda p: p.sequence).astype("category")
    df["rate"] = pd.Categorical(parsed.apply(lambda p: p.rate), categories=["normal", "fast"], ordered=True)
    df["trial"] = parsed.apply(lambda p: p.trial).astype(int)

    # Make sure numeric cols are numeric (defensive)
    num_cols = ["nsyll", "npause", "dur", "phonationtime", "speechrate", "articulationrate"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # asd sometimes contains '--undefined--' when nsyll==0; keep it but don't rely on it automatically.
    return df


def load_anatomy_long(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"participant_id", "measure", "side", "value_mm", "value_in", "value_kg", "value_lb"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
    return df


def anatomy_to_wide(anat_long: pd.DataFrame) -> pd.DataFrame:
    """
    Convert long-format anatomy table to wide per-participant table + derived variables.

    Mandible measures:
      - co_go (L/R)
      - go_me (L/R)
      - co_me (L/R)  <-- main 'mandible length' predictor (Co–Me)
    """
    df = anat_long.copy()
    df["side_filled"] = df["side"].fillna("NA")

    wide = df.pivot_table(
        index="participant_id",
        columns=["measure", "side_filled"],
        values=["value_mm", "value_kg"],
        aggfunc="first",
    )
    wide.columns = ["_".join(col) for col in wide.columns.to_flat_index()]
    wide = wide.reset_index()

    # Unit conversions / convenience columns
    if "value_mm_height_NA" in wide.columns:
        wide["height_cm"] = wide["value_mm_height_NA"] / 10.0
    if "value_mm_head_circumference_NA" in wide.columns:
        wide["head_circumference_cm"] = wide["value_mm_head_circumference_NA"] / 10.0
    if "value_mm_ear_to_ear_NA" in wide.columns:
        wide["ear_to_ear_cm"] = wide["value_mm_ear_to_ear_NA"] / 10.0
    if "value_mm_nasion_inion_NA" in wide.columns:
        wide["nasion_inion_cm"] = wide["value_mm_nasion_inion_NA"] / 10.0
    if "value_kg_weight_NA" in wide.columns:
        wide = wide.rename(columns={"value_kg_weight_NA": "weight_kg"})

    # Mandible-derived features (mean across sides + asymmetry)
    for m in ["co_go", "go_me", "co_me"]:
        L = f"value_mm_{m}_L"
        R = f"value_mm_{m}_R"
        if L in wide.columns and R in wide.columns:
            wide[f"{m}_mean_mm"] = wide[[L, R]].mean(axis=1)
            wide[f"{m}_diff_LminusR_mm"] = wide[L] - wide[R]
            wide[f"{m}_absdiff_mm"] = (wide[L] - wide[R]).abs()

    return wide


def load_metadata(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "participant_id" not in df.columns:
        raise ValueError(f"{path.name} must contain a 'participant_id' column.")
    return df


# -----------------------------
# QC + helpers
# -----------------------------

def basic_qc(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Basic QC for trial-level data.

    Exclusions:
    - nsyll == 0  (typically placeholder / non-response; rates are 0)
    - non-positive durations
    - missing numeric values in core columns
    """
    d = df.copy()

    core_numeric = ["nsyll", "dur", "phonationtime", "speechrate", "articulationrate"]
    for c in core_numeric:
        d[f"qc_missing_{c}"] = d[c].isna()

    d["qc_exclude_nsyll0"] = d["nsyll"] == 0
    d["qc_exclude_bad_durations"] = (d["dur"] <= 0) | (d["phonationtime"] <= 0)
    d["qc_exclude_bad_rates"] = (d["articulationrate"] <= 0) | (d["speechrate"] <= 0)

    d["qc_exclude"] = d[
        ["qc_exclude_nsyll0", "qc_exclude_bad_durations", "qc_exclude_bad_rates"]
        + [f"qc_missing_{c}" for c in core_numeric]
    ].any(axis=1)

    cleaned = d.loc[~d["qc_exclude"]].copy()

    qc = d.groupby("participant_id", observed=True).agg(
        n_trials_total=("soundname", "size"),
        n_trials_excluded=("qc_exclude", "sum"),
        n_trials_kept=("qc_exclude", lambda s: (~s).sum()),
        kept_fast=("rate", lambda s: (s == "fast").sum()),
        kept_normal=("rate", lambda s: (s == "normal").sum()),
        kept_sequences=("sequence", "nunique"),
    ).reset_index()
    qc["pct_excluded"] = 100.0 * qc["n_trials_excluded"] / qc["n_trials_total"]
    return cleaned, qc


def sequences_with_both_rates(df_clean: pd.DataFrame) -> List[str]:
    tmp = df_clean.groupby("sequence", observed=True)["rate"].nunique()
    both = tmp[tmp == 2].index.astype(str).tolist()
    return both


def _ols_line_with_ci(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit OLS y ~ x and return grid + mean prediction + half-width 95% CI."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()

    xg = np.linspace(x.min(), x.max(), 200)
    Xg = sm.add_constant(xg)
    pred = model.get_prediction(Xg).summary_frame(alpha=0.05)
    yhat = pred["mean"].to_numpy()
    lo = pred["mean_ci_lower"].to_numpy()
    hi = pred["mean_ci_upper"].to_numpy()
    ci = (hi - lo) / 2.0
    return xg, yhat, ci


# -----------------------------
# Participant summaries
# -----------------------------

def participant_level_summary(
    df_clean: pd.DataFrame,
    anatomy_wide: pd.DataFrame,
    metadata: pd.DataFrame,
    seq_both_rates: List[str],
    outcomes: List[str],
) -> pd.DataFrame:
    """
    One row per participant with:
      - anatomy (incl. mandible measures)
      - metadata (sex, age, etc.)
      - participant means for each outcome in normal and fast conditions
        (restricted to sequences that have both rates).
    """
    d = df_clean[df_clean["sequence"].astype(str).isin(seq_both_rates)].copy()

    out = pd.DataFrame({"participant_id": sorted(d["participant_id"].unique())})

    # Compute mean outcome per participant and condition
    for outcome in outcomes:
        if outcome not in d.columns:
            continue

        means = (
            d.groupby(["participant_id", "rate"], observed=True)[outcome]
            .mean()
            .unstack("rate")
            .rename(columns={"normal": f"mean_{outcome}_normal", "fast": f"mean_{outcome}_fast"})
            .reset_index()
        )
        out = out.merge(means, on="participant_id", how="left")

        # log-means (useful for partial plots / models)
        d[f"log_{outcome}"] = np.log(d[outcome])
        log_means = (
            d.groupby(["participant_id", "rate"], observed=True)[f"log_{outcome}"]
            .mean()
            .unstack("rate")
            .rename(columns={"normal": f"mean_log_{outcome}_normal", "fast": f"mean_log_{outcome}_fast"})
            .reset_index()
        )
        out = out.merge(log_means, on="participant_id", how="left")

    out = out.merge(anatomy_wide, on="participant_id", how="left")
    out = out.merge(metadata, on="participant_id", how="left", suffixes=("", "_meta"))

    if "co_me_mean_mm" in out.columns:
        out["co_me_c_mm"] = out["co_me_mean_mm"] - out["co_me_mean_mm"].mean()
    if "height_cm" in out.columns:
        out["height_c_cm"] = out["height_cm"] - out["height_cm"].mean()

    return out


# -----------------------------
# Models (GEE)
# -----------------------------

def fit_gee_models_for_outcome(
    df_clean: pd.DataFrame,
    seq_both_rates: List[str],
    outcome: str,
    out_dir_models: Path,
) -> pd.DataFrame:
    """
    Fit a small model set for one outcome. Saves text summaries and returns tidy coefficients.

    Outcome is modelled on the log scale:
      log(outcome) ~ co_me + height + condition + sequence
    """
    out_dir_models.mkdir(parents=True, exist_ok=True)

    d = df_clean[df_clean["sequence"].astype(str).isin(seq_both_rates)].copy()
    if isinstance(d["sequence"].dtype, pd.CategoricalDtype):
        d["sequence"] = d["sequence"].cat.remove_unused_categories()

    d["rate"] = pd.Categorical(d["rate"].astype(str), categories=["normal", "fast"], ordered=True)

    if outcome not in d.columns:
        raise ValueError(f"Outcome '{outcome}' not found in dataframe columns.")

    # Defensive: ensure strictly positive
    if (d[outcome] <= 0).any():
        raise ValueError(f"Outcome '{outcome}' contains non-positive values after QC; cannot log-transform safely.")

    d["log_y"] = np.log(d[outcome])

    d["co_me_c_mm"] = d["co_me_mean_mm"] - d["co_me_mean_mm"].mean()
    d["height_c_cm"] = d["height_cm"] - d["height_cm"].mean()

    models = {
        "A_basic": "log_y ~ co_me_c_mm + rate + C(sequence)",
        "B_plus_height": "log_y ~ co_me_c_mm + height_c_cm + rate + C(sequence)",
        "C_interaction": "log_y ~ co_me_c_mm * rate + height_c_cm + C(sequence)",
    }

    rows = []
    for tag, formula in models.items():
        gee = smf.gee(
            formula=formula,
            groups="participant_id",
            data=d,
            cov_struct=sm.cov_struct.Exchangeable(),
            family=sm.families.Gaussian(),
        ).fit()

        (out_dir_models / f"{outcome}_{tag}.txt").write_text(str(gee.summary()), encoding="utf-8")

        conf = gee.conf_int()
        for term in gee.params.index:
            rows.append({
                "outcome": outcome,
                "model": tag,
                "term": term,
                "coef": float(gee.params[term]),
                "se": float(gee.bse[term]),
                "p": float(gee.pvalues[term]),
                "ci_low": float(conf.loc[term, 0]),
                "ci_high": float(conf.loc[term, 1]),
            })

    coef_table = pd.DataFrame(rows)
    coef_table.to_csv(out_dir_models / f"{outcome}_gee_coefficients_tidy.csv", index=False)

    return coef_table


def gee_effect_size_per_10mm(coef_row: pd.Series) -> Dict[str, float]:
    """Convert a log-scale per-mm coefficient into percent change per +10 mm."""
    b = float(coef_row["coef"])
    lo = float(coef_row["ci_low"])
    hi = float(coef_row["ci_high"])
    pct = (np.exp(b * 10.0) - 1.0) * 100.0
    pct_lo = (np.exp(lo * 10.0) - 1.0) * 100.0
    pct_hi = (np.exp(hi * 10.0) - 1.0) * 100.0
    return {"pct_10mm": pct, "pct_10mm_ci_low": pct_lo, "pct_10mm_ci_high": pct_hi}


# -----------------------------
# Figures
# -----------------------------

def plot_rate_by_sequence(df_clean: pd.DataFrame, out_dir_fig: Path) -> None:
    """Boxplots of articulation rate by sequence and condition (plus a normal-only panel)."""
    d = df_clean.copy()
    d["sequence_str"] = d["sequence"].astype(str)
    d["rate_str"] = d["rate"].astype(str)

    seq_both = sequences_with_both_rates(d)
    seq_normal_only = sorted(set(d["sequence_str"].unique()) - set(seq_both))

    # sequences with both rates
    if seq_both:
        d1 = d[d["sequence_str"].isin(seq_both)].copy()
        order = sorted(seq_both)

        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.set_title("Articulation rate by sequence and condition (sequences with both rates)")
        ax.set_ylabel("Articulation rate (syll/s)")
        ax.set_xlabel("Sequence")

        positions, labels, data = [], [], []
        pos = 1.0
        gap = 1.2
        width = 0.35

        for seq in order:
            for rate in ["normal", "fast"]:
                series = d1[(d1["sequence_str"] == seq) & (d1["rate_str"] == rate)]["articulationrate"].to_numpy()
                data.append(series)
                positions.append(pos)
                labels.append(f"{seq}\n{rate}")
                pos += width
            pos += gap

        ax.boxplot(data, positions=positions, widths=0.30, showfliers=False)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=0, ha="center")
        ax.grid(True, axis="y", alpha=0.3)
        save_fig(fig, out_dir_fig / "fig01_artic_rate_boxplot_sequences_with_fast")

    # normal-only sequences
    if seq_normal_only:
        d2 = d[(d["sequence_str"].isin(seq_normal_only)) & (d["rate_str"] == "normal")].copy()
        order = seq_normal_only

        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.set_title("Articulation rate by sequence (normal-only sequences)")
        ax.set_ylabel("Articulation rate (syll/s)")
        ax.set_xlabel("Sequence (normal condition only)")

        data = [d2[d2["sequence_str"] == seq]["articulationrate"].to_numpy() for seq in order]
        ax.boxplot(data, tick_labels=order, showfliers=False)
        ax.grid(True, axis="y", alpha=0.3)
        save_fig(fig, out_dir_fig / "fig02_artic_rate_boxplot_normal_only_sequences")


def plot_scatter_fast_vs_mandible(
    part_sum: pd.DataFrame,
    out_dir_fig: Path,
    outcome: str,
    y_label: str,
) -> None:
    """
    For a given outcome, produce:
      - raw scatter: participant mean FAST outcome vs mandible length
      - partial scatter: residualised for height (FAST only)
    """
    d = part_sum.copy()
    y_col = f"mean_{outcome}_fast"
    if y_col not in d.columns or "co_me_mean_mm" not in d.columns or "height_cm" not in d.columns:
        return

    d = d.dropna(subset=[y_col, "co_me_mean_mm", "height_cm"]).copy()

    # ---- raw scatter ----
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.set_title(f"Fast {y_label} vs mandible length (participant means)")
    ax.set_xlabel("Mandible length Co–Me (mean of L/R; mm)")
    ax.set_ylabel(f"Mean {y_label} (fast)")

    if "sex" in d.columns:
        males = d[d["sex"] == "male"]
        females = d[d["sex"] == "female"]
        ax.scatter(females["co_me_mean_mm"], females[y_col], marker="o", label="female", alpha=0.85)
        ax.scatter(males["co_me_mean_mm"], males[y_col], marker="^", label="male", alpha=0.85)
        ax.legend(frameon=False)
    else:
        ax.scatter(d["co_me_mean_mm"], d[y_col], alpha=0.85)

    xg, yhat, ci = _ols_line_with_ci(d["co_me_mean_mm"].to_numpy(), d[y_col].to_numpy())
    ax.plot(xg, yhat, linewidth=2)
    ax.fill_between(xg, yhat - ci, yhat + ci, alpha=0.2)

    ax.grid(True, alpha=0.3)
    save_fig(fig, out_dir_fig / f"fig03_scatter_fast_{outcome}_vs_mandible_raw")

    # ---- partial (control height) ----
    # residualise log(y) and x with respect to height
    Xh = sm.add_constant(d["height_cm"].to_numpy(dtype=float))
    res_y = sm.OLS(np.log(d[y_col].to_numpy(dtype=float)), Xh).fit().resid
    res_x = sm.OLS(d["co_me_mean_mm"].to_numpy(dtype=float), Xh).fit().resid

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.set_title(f"Fast {y_label} vs mandible length (partial; controlling for height)")
    ax.set_xlabel("Mandible length residual (mm; height regressed out)")
    ax.set_ylabel(f"log(Mean fast {y_label}) residual")

    ax.scatter(res_x, res_y, alpha=0.85)

    xg, yhat, ci = _ols_line_with_ci(res_x, res_y)
    ax.plot(xg, yhat, linewidth=2)
    ax.fill_between(xg, yhat - ci, yhat + ci, alpha=0.2)

    r, p = stats.pearsonr(res_x, res_y)
    ax.text(
        0.02, 0.98,
        f"partial r = {r:.3f}\n(p = {p:.3g})",
        transform=ax.transAxes,
        ha="left",
        va="top",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.8, linewidth=0.0),
    )

    ax.grid(True, alpha=0.3)
    save_fig(fig, out_dir_fig / f"fig04_scatter_fast_{outcome}_partial_height")


def plot_predicted_effect_from_gee(
    df_clean: pd.DataFrame,
    seq_both_rates: List[str],
    out_dir_fig: Path,
    outcome: str,
    y_label: str,
) -> None:
    """
    Fit the height-adjusted GEE model and plot predicted outcome vs mandible length,
    with separate curves for normal vs fast.
    """
    d = df_clean[df_clean["sequence"].astype(str).isin(seq_both_rates)].copy()
    if isinstance(d["sequence"].dtype, pd.CategoricalDtype):
        d["sequence"] = d["sequence"].cat.remove_unused_categories()
    d["rate"] = pd.Categorical(d["rate"].astype(str), categories=["normal", "fast"], ordered=True)

    if outcome not in d.columns:
        return
    if (d[outcome] <= 0).any():
        return

    d["log_y"] = np.log(d[outcome])
    d["co_me_c_mm"] = d["co_me_mean_mm"] - d["co_me_mean_mm"].mean()
    d["height_c_cm"] = d["height_cm"] - d["height_cm"].mean()

    formula = "log_y ~ co_me_c_mm + height_c_cm + rate + C(sequence)"
    gee = smf.gee(
        formula=formula,
        groups="participant_id",
        data=d,
        cov_struct=sm.cov_struct.Exchangeable(),
        family=sm.families.Gaussian(),
    ).fit()

    design_info = gee.model.data.design_info
    cov = gee.cov_params()

    sequences = list(d["sequence"].cat.categories.astype(str))
    rates = ["normal", "fast"]

    co_me_grid = np.linspace(d["co_me_mean_mm"].min(), d["co_me_mean_mm"].max(), 80)
    co_me_c = co_me_grid - d["co_me_mean_mm"].mean()
    height_c = 0.0  # hold at mean height

    pred_rows = []
    for rate in rates:
        for cm, cm_raw in zip(co_me_c, co_me_grid):
            seq_mus = []
            seq_vars = []
            for seq in sequences:
                row = pd.DataFrame({
                    "co_me_c_mm": [cm],
                    "height_c_cm": [height_c],
                    "rate": pd.Categorical([rate], categories=["normal", "fast"], ordered=True),
                    "sequence": pd.Categorical([seq], categories=sequences, ordered=False),
                })
                exog = patsy.build_design_matrices([design_info], row)[0]
                mu = float((np.asarray(exog) @ gee.params.to_numpy()).squeeze().item())
                var = float((np.asarray(exog) @ cov.to_numpy() @ np.asarray(exog).T).squeeze().item())
                seq_mus.append(mu)
                seq_vars.append(var)

            mu_avg = float(np.mean(seq_mus))
            se_avg = float(np.sqrt(np.mean(seq_vars)))
            pred_rows.append({
                "rate": rate,
                "co_me_mean_mm": float(cm_raw),
                "pred_log": mu_avg,
                "se_log": se_avg,
            })

    pred = pd.DataFrame(pred_rows)
    pred["pred"] = np.exp(pred["pred_log"])
    pred["ci_low"] = np.exp(pred["pred_log"] - 1.96 * pred["se_log"])
    pred["ci_high"] = np.exp(pred["pred_log"] + 1.96 * pred["se_log"])

    for col in ["co_me_mean_mm", "pred", "ci_low", "ci_high"]:
        pred[col] = pd.to_numeric(pred[col], errors="coerce")

    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.set_title(f"Model-predicted {y_label} vs mandible length\n(GEE; adjusted for height + sequence)")
    ax.set_xlabel("Mandible length Co–Me (mean of L/R; mm)")
    ax.set_ylabel(f"Predicted {y_label}")

    for rate in rates:
        pr = pred[pred["rate"] == rate].sort_values("co_me_mean_mm")
        ax.plot(pr["co_me_mean_mm"].to_numpy(dtype=float), pr["pred"].to_numpy(dtype=float), linewidth=2, label=rate)
        ax.fill_between(
            pr["co_me_mean_mm"].to_numpy(dtype=float),
            pr["ci_low"].to_numpy(dtype=float),
            pr["ci_high"].to_numpy(dtype=float),
            alpha=0.2,
        )

    ax.legend(frameon=False, title="Condition")
    ax.grid(True, alpha=0.3)
    save_fig(fig, out_dir_fig / f"fig05_model_predicted_effect_{outcome}")


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse mandible dimensions vs syllable production rate."
    )
    parser.add_argument(
        "--data_dir", type=str, required=True,
        help="Path to the Data folder containing the CSV files."
    )
    parser.add_argument(
        "--out_dir", type=str, required=True,
        help="Output directory (will be created if missing)."
    )
    parser.add_argument(
        "--outcomes", nargs="+", default=["articulationrate", "speechrate"],
        help="Outcome columns to analyse (default: articulationrate speechrate)."
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    set_plot_style()

    # Silence a common, harmless pandas warning about categorical casting that can clutter logs
    warnings.filterwarnings("ignore", category=RuntimeWarning, message="invalid value encountered in cast")

    # Input files
    praat_file = data_dir / "praat_info_corpus_ema-eeg.csv"
    anatomy_file = find_in_data_dir(data_dir, "anatomy_measurements.csv")
    metadata_file = find_in_data_dir(data_dir, "metadata.csv")
    for p in [praat_file, anatomy_file, metadata_file]:
        if not p.exists():
            raise FileNotFoundError(f"Missing required file: {p}")

    # Load
    praat = load_praat_info(praat_file)
    anat_long = load_anatomy_long(anatomy_file)
    anat_wide = anatomy_to_wide(anat_long)
    meta = load_metadata(metadata_file)

    # Merge trial-level dataset
    df = praat.merge(anat_wide, on="participant_id", how="left").merge(meta, on="participant_id", how="left")

    # QC
    df_clean, qc = basic_qc(df)
    seq_both = sequences_with_both_rates(df_clean)

    # Save merged + QC outputs
    (out_dir / "tables").mkdir(exist_ok=True)
    (out_dir / "models").mkdir(exist_ok=True)
    (out_dir / "figures").mkdir(exist_ok=True)

    df_clean.to_csv(out_dir / "analysis_dataset_clean.csv", index=False)
    qc.to_csv(out_dir / "tables" / "qc_summary_by_participant.csv", index=False)

    # Overview text
    overview_lines = []
    overview_lines.append("=== DATA OVERVIEW ===")
    overview_lines.append(f"Data dir: {data_dir}")
    overview_lines.append(f"Trials (raw): {len(df):,}")
    overview_lines.append(f"Trials (after QC): {len(df_clean):,}")
    overview_lines.append(f"Participants (raw): {df['participant_id'].nunique()}")
    overview_lines.append(f"Participants (after QC): {df_clean['participant_id'].nunique()}")
    overview_lines.append(f"Sequences (after QC): {df_clean['sequence'].nunique()}")
    overview_lines.append(f"Sequences with both rates (after QC): {seq_both}")
    overview_lines.append("")

    zero_kept = qc.loc[qc["n_trials_kept"] == 0, "participant_id"].tolist()
    if zero_kept:
        overview_lines.append(f"Participants with zero usable trials after QC: {zero_kept}")
        overview_lines.append("These will not contribute to analyses.")
        overview_lines.append("")

    # Participants without fast tokens in seq_both subset
    if seq_both:
        dsub = df_clean[df_clean["sequence"].astype(str).isin(seq_both)]
        has_fast = dsub.groupby("participant_id", observed=True)["rate"].apply(lambda s: (s == "fast").any())
        no_fast = has_fast[~has_fast].index.tolist()
        if no_fast:
            overview_lines.append(f"Participants with NO usable FAST tokens (within seq_both subset): {no_fast}")
            overview_lines.append("They contribute to NORMAL-only estimates, but not to FAST effects.")
            overview_lines.append("")

    overview_text = "\n".join(overview_lines)
    print(overview_text)
    (out_dir / "tables" / "data_overview.txt").write_text(overview_text, encoding="utf-8")

    # Participant-level summary
    outcomes = list(args.outcomes)
    part_sum = participant_level_summary(df_clean, anat_wide, meta, seq_both, outcomes)
    part_sum.to_csv(out_dir / "tables" / "participant_level_summary.csv", index=False)

    # Figures: distributions + per-outcome scatter + per-outcome predicted effects
    plot_rate_by_sequence(df_clean, out_dir / "figures")

    outcome_labels = {
        "articulationrate": "articulation rate (syll/s; pauses excluded)",
        "speechrate": "speech rate (syll/s; pauses included)",
    }

    for outcome in outcomes:
        ylab = outcome_labels.get(outcome, outcome)
        plot_scatter_fast_vs_mandible(part_sum, out_dir / "figures", outcome=outcome, y_label=ylab)
        if seq_both:
            plot_predicted_effect_from_gee(df_clean, seq_both, out_dir / "figures", outcome=outcome, y_label=ylab)

    # Models
    all_coef = []
    for outcome in outcomes:
        coef = fit_gee_models_for_outcome(
            df_clean=df_clean,
            seq_both_rates=seq_both,
            outcome=outcome,
            out_dir_models=out_dir / "models",
        )
        all_coef.append(coef)

    coef_all = pd.concat(all_coef, ignore_index=True) if all_coef else pd.DataFrame()
    coef_all.to_csv(out_dir / "tables" / "gee_coefficients_tidy_all_outcomes.csv", index=False)

    # Effect-size summary (per +10 mm, height-adjusted model B)
    eff_rows = []
    for outcome in outcomes:
        sel = coef_all[(coef_all["outcome"] == outcome) & (coef_all["model"] == "B_plus_height") & (coef_all["term"] == "co_me_c_mm")]
        if len(sel) == 1:
            eff = gee_effect_size_per_10mm(sel.iloc[0])
            eff_rows.append({"outcome": outcome, **eff})

    if eff_rows:
        eff_df = pd.DataFrame(eff_rows)
        eff_df.to_csv(out_dir / "tables" / "effect_size_per_10mm.csv", index=False)

        # Also write a human-readable txt summary
        lines = ["=== EFFECT SIZE SUMMARY (height-adjusted GEE; per +10 mm Co–Me) ==="]
        for _, r in eff_df.iterrows():
            lines.append(
                f"{r['outcome']}: {r['pct_10mm']:.2f}%  (95% CI [{r['pct_10mm_ci_low']:.2f}%, {r['pct_10mm_ci_high']:.2f}%])"
            )
        lines.append("Negative values mean longer mandibles are associated with lower rates.")
        msg = "\n".join(lines) + "\n"
        print(msg)
        (out_dir / "tables" / "effect_size_summary.txt").write_text(msg, encoding="utf-8")

    print(f"Done. Outputs written to: {out_dir}")


if __name__ == "__main__":
    main()
