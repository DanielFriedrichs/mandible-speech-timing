#!/usr/bin/env python3
"""
Small-sample robustness checks for the two primary mandibular-length effects.

This script re-analyses the two primary DDK timing outcomes:

    1. log(speech rate)
    2. log(articulation rate)

using the same fixed-effect structure as the manuscript:

    outcome ~ rate condition + sequence + Co--Me/10 mm + centered height

The original manuscript estimates are reproduced as an OLS/GEE-independence
coefficient with participant-cluster sandwich standard errors and normal-theory
Wald tests. Because Co--Me varies only between speakers, the script adds three
speaker-level small-sample checks:

    A. CR0 cluster-robust t test with df = number of speakers - 1
    B. CR2/Bell--McCaffrey cluster correction with Satterthwaite df
    C. Speaker-cluster bootstrap percentile CI, resampling speakers with replacement
    D. Optional restricted-null wild-cluster bootstrap-t p value using CR2 t statistics

Why OLS appears here although the manuscript says GEE:
    For a Gaussian identity-link GEE with an independence working correlation,
    the point estimates and CR0 sandwich standard errors are the same as the
    corresponding linear model with participant-cluster sandwich SEs. The current
    manuscript values in effect_sizes_per_10mm.csv match this independence-GEE / OLS
    calculation. The bootstrap and CR2 checks therefore use the same mean model,
    but make the small number of independent speaker clusters explicit.

Typical use from the project root:

    python primary_effects_small_sample_robustness.py

For a longer bootstrap run:

    python primary_effects_small_sample_robustness.py --n-cluster-boot 19999 --n-wild-boot 9999

For a quick test run:

    python primary_effects_small_sample_robustness.py --n-cluster-boot 999 --n-wild-boot 999

Outputs:
    primary_effects_small_sample_robustness.csv
    primary_effects_small_sample_robustness_summary.txt
    primary_effects_cluster_bootstrap_draws.csv.gz
    primary_effects_wild_cluster_t_draws.csv.gz  (unless --skip-wild)

Author: prepared for Daniel Friedrichs' mandibular anatomy / DDK manuscript.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PRIMARY_OUTCOMES: Tuple[Tuple[str, str], ...] = (
    ("log_speechrate", "Speech rate"),
    ("log_articulationrate", "Articulation rate"),
)

SIZE_TERM = "co_me_mean_mm_10"
CLUSTER_COL = "participant_id"

DEFAULT_DATA_CANDIDATES: Tuple[str, ...] = (
    "analysis_dataset_clean.csv",
    "outputs/analysis_dataset_clean.csv",
    "outputs_rate/analysis_dataset_clean.csv",
    "outputs_paper_v1/speechrate_analysis/analysis_dataset_clean.csv",
    "outputs_strategy1/derived/speechrate_analysis/analysis_dataset_clean.csv",
)


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------


def pct_from_log_beta(beta):
    """Convert a coefficient on log(rate) into percent change."""
    return 100.0 * (np.exp(beta) - 1.0)


def as_float(x: object) -> float:
    """Convert numpy scalar / pandas scalar / Python scalar to float."""
    if x is None:
        return float("nan")
    return float(np.asarray(x))


def find_default_data_file(project_root: Path) -> Path:
    """Find analysis_dataset_clean.csv in common project locations."""
    for rel in DEFAULT_DATA_CANDIDATES:
        candidate = project_root / rel
        if candidate.exists():
            return candidate
    msg = [
        "Could not find analysis_dataset_clean.csv in the default locations:",
        *[f"  - {project_root / rel}" for rel in DEFAULT_DATA_CANDIDATES],
        "",
        "Run again with --data-file /path/to/analysis_dataset_clean.csv",
    ]
    raise FileNotFoundError("\n".join(msg))


def default_out_dir(project_root: Path) -> Path:
    """Choose a sensible output directory without assuming one exact pipeline layout."""
    if (project_root / "outputs_strategy1").exists():
        return project_root / "outputs_strategy1" / "primary_effect_small_sample_robustness"
    if (project_root / "outputs_paper_v1").exists():
        return project_root / "outputs_paper_v1" / "primary_effect_small_sample_robustness"
    if (project_root / "outputs").exists():
        return project_root / "outputs" / "primary_effect_small_sample_robustness"
    return project_root / "primary_effect_small_sample_robustness"


def load_and_prepare_data(data_file: Path) -> pd.DataFrame:
    """Load the primary DDK timing table and derive model columns."""
    df = pd.read_csv(data_file)

    required = {
        "participant_id",
        "rate",
        "sequence",
        "speechrate",
        "articulationrate",
        "co_me_mean_mm",
        "height_cm",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            "The input file is missing required columns: " + ", ".join(missing)
        )

    df = df.copy()

    # Keep the same cleaned analysis set if the table contains an explicit QC flag.
    # In the current analysis_dataset_clean.csv this should leave N unchanged.
    if "qc_exclude" in df.columns:
        df = df[~df["qc_exclude"].astype(bool)].copy()

    df = df.dropna(
        subset=[
            "participant_id",
            "rate",
            "sequence",
            "speechrate",
            "articulationrate",
            "co_me_mean_mm",
            "height_cm",
        ]
    ).copy()
    df = df[(df["speechrate"] > 0) & (df["articulationrate"] > 0)].copy()

    # Fixed effect variables as categorical strings with stable category sets.
    df["participant_id"] = df["participant_id"].astype(str)
    df["rate"] = df["rate"].astype(str)
    df["sequence"] = df["sequence"].astype(str)

    df[SIZE_TERM] = df["co_me_mean_mm"] / 10.0
    df["height_cm_c"] = df["height_cm"] - df["height_cm"].mean()
    df["log_speechrate"] = np.log(df["speechrate"])
    df["log_articulationrate"] = np.log(df["articulationrate"])

    return df


def build_design(df: pd.DataFrame, outcome: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str], str]:
    """Build a fixed design matrix for one outcome.

    This function avoids relying on patsy/statsmodels formula parsing, so the
    script remains portable. It implements the manuscript model space directly:
    intercept + rate-condition fixed effects + sequence fixed effects +
    Co--Me/10 mm + centered height. The first alphabetically sorted level of
    each categorical factor is used as the reference. The Co--Me coefficient is
    invariant to the reference level choice because the same fixed-effect space
    is fitted.
    """
    model_df = df[[outcome, CLUSTER_COL, "rate", "sequence", SIZE_TERM, "height_cm_c"]].dropna().copy()

    rate_levels = sorted(model_df["rate"].astype(str).unique().tolist())
    sequence_levels = sorted(model_df["sequence"].astype(str).unique().tolist())

    X_parts: List[object] = []
    X_parts.append(pd.Series(1.0, index=model_df.index, name="Intercept"))

    rate_cat = pd.Categorical(model_df["rate"].astype(str), categories=rate_levels)
    rate_dummies = pd.get_dummies(rate_cat, prefix="rate", drop_first=True, dtype=float)
    rate_dummies.index = model_df.index
    X_parts.append(rate_dummies)

    seq_cat = pd.Categorical(model_df["sequence"].astype(str), categories=sequence_levels)
    seq_dummies = pd.get_dummies(seq_cat, prefix="sequence", drop_first=True, dtype=float)
    seq_dummies.index = model_df.index
    X_parts.append(seq_dummies)

    X_parts.append(model_df[[SIZE_TERM, "height_cm_c"]].astype(float))
    x_df = pd.concat(X_parts, axis=1)

    y = model_df[outcome].to_numpy(dtype=float)
    X = x_df.to_numpy(dtype=float)
    clusters = model_df[CLUSTER_COL].astype(str).to_numpy()
    columns = list(x_df.columns)

    if SIZE_TERM not in columns:
        raise RuntimeError(f"Could not find {SIZE_TERM} in design matrix columns: {columns}")

    formula = (
        f"{outcome} ~ rate + sequence + {SIZE_TERM} + height_cm_c "
        f"(reference rate={rate_levels[0]!r}; reference sequence={sequence_levels[0]!r})"
    )
    return y, X, clusters, columns, formula


# -----------------------------------------------------------------------------
# Linear-model and cluster-robust covariance helpers
# -----------------------------------------------------------------------------


def ols_fit(X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return beta, residuals, and (X'X)^-1 using a stable pseudo-inverse."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    return beta, resid, XtX_inv


def symmetric_sqrt_psd(A: np.ndarray) -> np.ndarray:
    """Symmetric square root of a positive semi-definite matrix."""
    vals, vecs = np.linalg.eigh((A + A.T) / 2.0)
    vals = np.clip(vals, 0.0, None)
    return (vecs * np.sqrt(vals)) @ vecs.T


def cluster_cr0_cov(
    X: np.ndarray,
    resid: np.ndarray,
    clusters: np.ndarray,
    XtX_inv: np.ndarray,
) -> np.ndarray:
    """CR0 cluster sandwich covariance: (X'X)^-1 sum_g Xg'eg eg'Xg (X'X)^-1."""
    p = X.shape[1]
    meat = np.zeros((p, p), dtype=float)
    for g in np.unique(clusters):
        ix = np.flatnonzero(clusters == g)
        Xg = X[ix, :]
        eg = resid[ix]
        ug = Xg.T @ eg
        meat += np.outer(ug, ug)
    return XtX_inv @ meat @ XtX_inv


@dataclass
class CR2Cache:
    """Precomputed quantities for fast CR2 standard errors across repeated fits."""

    X: np.ndarray
    clusters: np.ndarray
    XtX_inv: np.ndarray
    contrast: np.ndarray
    coef_idx: int
    cluster_parts: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]


def make_cr2_cache(X: np.ndarray, clusters: np.ndarray, coef_idx: int) -> CR2Cache:
    """Precompute low-rank CR2 adjustment matrices for each speaker cluster.

    For OLS, CR2 applies A_g = (I - H_g)^(-1/2) to the residual vector in each
    cluster, where H_g = X_g (X'X)^-1 X_g'. Rather than eigendecomposing an
    n_g x n_g matrix, this function uses the low-rank representation of H_g;
    only p x p eigendecompositions are needed.
    """
    XtX_inv = np.linalg.pinv(X.T @ X)
    XtX_inv_sqrt = symmetric_sqrt_psd(XtX_inv)
    contrast = np.zeros(X.shape[1], dtype=float)
    contrast[coef_idx] = 1.0

    parts: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for g in np.unique(clusters):
        ix = np.flatnonzero(clusters == g)
        Xg = X[ix, :]
        Z = Xg @ XtX_inv_sqrt
        small = (Z.T @ Z + (Z.T @ Z).T) / 2.0
        vals, vecs = np.linalg.eigh(small)
        keep = vals > 1e-10
        if np.any(keep):
            vals_keep = np.clip(vals[keep], 0.0, 1.0 - 1e-10)
            vecs_keep = vecs[:, keep]
            U = Z @ vecs_keep / np.sqrt(vals_keep)[None, :]
            factors = 1.0 / np.sqrt(1.0 - vals_keep) - 1.0
        else:
            U = np.zeros((len(ix), 0), dtype=float)
            factors = np.zeros(0, dtype=float)
        parts.append((ix, Xg, U, factors))

    return CR2Cache(
        X=X,
        clusters=clusters,
        XtX_inv=XtX_inv,
        contrast=contrast,
        coef_idx=coef_idx,
        cluster_parts=parts,
    )


def cr2_from_residuals(
    cache: CR2Cache,
    beta: np.ndarray,
    resid: np.ndarray,
) -> Tuple[float, float, float, Tuple[float, float]]:
    """Compute CR2 SE, Satterthwaite df, t statistic, and 95% CI for one coefficient."""
    p = cache.X.shape[1]
    meat = np.zeros((p, p), dtype=float)
    q_values: List[float] = []

    for ix, Xg, U, factors in cache.cluster_parts:
        eg = resid[ix]
        if U.shape[1] > 0:
            Aeg = eg + U @ (factors * (U.T @ eg))
        else:
            Aeg = eg
        ug = Xg.T @ Aeg
        meat += np.outer(ug, ug)
        q_values.append(float(cache.contrast @ cache.XtX_inv @ ug))

    cov = cache.XtX_inv @ meat @ cache.XtX_inv
    var = max(float(cov[cache.coef_idx, cache.coef_idx]), 0.0)
    se = math.sqrt(var)

    q = np.asarray(q_values, dtype=float)
    denom = float(np.sum(q**4))
    if denom <= 0 or not np.isfinite(denom):
        df = float(len(np.unique(cache.clusters)) - 1)
    else:
        df = float(2.0 * (np.sum(q**2) ** 2) / denom)

    t_stat = float(beta[cache.coef_idx] / se)
    tcrit = float(stats.t.ppf(0.975, df))
    ci = (
        float(beta[cache.coef_idx] - tcrit * se),
        float(beta[cache.coef_idx] + tcrit * se),
    )
    return se, df, t_stat, ci


# -----------------------------------------------------------------------------
# Bootstrap helpers
# -----------------------------------------------------------------------------


def speaker_cluster_bootstrap_betas(
    X: np.ndarray,
    y: np.ndarray,
    clusters: np.ndarray,
    coef_idx: int,
    n_boot: int,
    seed: int,
) -> np.ndarray:
    """Speaker-cluster bootstrap by resampling speakers with replacement.

    The implementation precomputes X_g'X_g and X_g'y_g for each speaker and then
    draws multinomial speaker counts. This is exactly equivalent to concatenating
    resampled speaker blocks, but much faster.
    """
    rng = np.random.default_rng(seed)
    unique_clusters = np.unique(clusters)
    G = len(unique_clusters)
    p = X.shape[1]

    XtX_by_cluster = np.zeros((G, p, p), dtype=float)
    Xty_by_cluster = np.zeros((G, p), dtype=float)
    for i, g in enumerate(unique_clusters):
        ix = np.flatnonzero(clusters == g)
        Xg = X[ix, :]
        yg = y[ix]
        XtX_by_cluster[i, :, :] = Xg.T @ Xg
        Xty_by_cluster[i, :] = Xg.T @ yg

    probs = np.ones(G, dtype=float) / G
    draws = np.empty(n_boot, dtype=float)

    for b in range(n_boot):
        counts = rng.multinomial(G, probs)
        XtX_star = np.tensordot(counts, XtX_by_cluster, axes=(0, 0))
        Xty_star = np.tensordot(counts, Xty_by_cluster, axes=(0, 0))
        try:
            beta_star = np.linalg.solve(XtX_star, Xty_star)
        except np.linalg.LinAlgError:
            beta_star = np.linalg.pinv(XtX_star) @ Xty_star
        draws[b] = beta_star[coef_idx]

    return draws


def wild_cluster_bootstrap_t(
    X: np.ndarray,
    y: np.ndarray,
    clusters: np.ndarray,
    coef_idx: int,
    cache: CR2Cache,
    n_boot: int,
    seed: int,
) -> Tuple[float, np.ndarray]:
    """Restricted-null Rademacher wild-cluster bootstrap-t p value.

    The null model removes the Co--Me column. Residuals from that restricted
    model are multiplied by one Rademacher weight per speaker cluster. Each
    bootstrap sample is refit with the full model, and the bootstrap test
    statistic is the CR2 t statistic for the Co--Me coefficient.
    """
    rng = np.random.default_rng(seed)

    beta_full, resid_full, _ = ols_fit(X, y)
    _, _, t_obs, _ = cr2_from_residuals(cache, beta_full, resid_full)

    keep_cols = [j for j in range(X.shape[1]) if j != coef_idx]
    X_restricted = X[:, keep_cols]
    beta_restricted, resid_restricted, _ = ols_fit(X_restricted, y)
    fitted_restricted = X_restricted @ beta_restricted

    unique_clusters = np.unique(clusters)
    cluster_to_index: Dict[str, int] = {g: i for i, g in enumerate(unique_clusters)}
    row_cluster_index = np.asarray([cluster_to_index[g] for g in clusters], dtype=int)

    t_draws = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        weights = rng.choice(np.array([-1.0, 1.0]), size=len(unique_clusters), replace=True)
        y_star = fitted_restricted + weights[row_cluster_index] * resid_restricted
        beta_star, resid_star, _ = ols_fit(X, y_star)
        _, _, t_star, _ = cr2_from_residuals(cache, beta_star, resid_star)
        t_draws[b] = t_star

    p_value = float((1.0 + np.sum(np.abs(t_draws) >= abs(t_obs))) / (n_boot + 1.0))
    return p_value, t_draws


# -----------------------------------------------------------------------------
# Reporting helpers
# -----------------------------------------------------------------------------


def add_result_row(
    rows: List[Dict[str, object]],
    *,
    outcome: str,
    outcome_label: str,
    method: str,
    n_obs: int,
    n_speakers: int,
    beta: float,
    se: Optional[float],
    df: Optional[float],
    statistic: Optional[float],
    p_value: Optional[float],
    ci_low: Optional[float],
    ci_high: Optional[float],
    n_boot: Optional[int],
    seed: Optional[int],
    note: str,
) -> None:
    """Append one formatted result row."""
    beta_f = as_float(beta)
    ci_low_f = None if ci_low is None else as_float(ci_low)
    ci_high_f = None if ci_high is None else as_float(ci_high)
    rows.append(
        {
            "outcome": outcome,
            "outcome_label": outcome_label,
            "method": method,
            "n_obs": n_obs,
            "n_speakers": n_speakers,
            "beta_log_per_10mm": beta_f,
            "se_log": None if se is None else as_float(se),
            "df": None if df is None else as_float(df),
            "statistic": None if statistic is None else as_float(statistic),
            "p": None if p_value is None else as_float(p_value),
            "ci_low_log": ci_low_f,
            "ci_high_log": ci_high_f,
            "effect_pct_per_10mm": as_float(pct_from_log_beta(beta_f)),
            "effect_pct_ci_low": None if ci_low_f is None else as_float(pct_from_log_beta(ci_low_f)),
            "effect_pct_ci_high": None if ci_high_f is None else as_float(pct_from_log_beta(ci_high_f)),
            "n_boot": n_boot,
            "seed": seed,
            "note": note,
        }
    )


def format_pct(x: object, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return "NA"
    return f"{float(x):+.{digits}f}%"


def format_num(x: object, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)) or pd.isna(x):
        return "NA"
    return f"{float(x):.{digits}g}"


def write_summary(
    out_file: Path,
    results: pd.DataFrame,
    data_file: Path,
    formula_by_outcome: Dict[str, str],
) -> None:
    """Write a compact text summary for copy-paste into manuscript notes."""
    lines: List[str] = []
    lines.append("Small-sample robustness checks for primary Co--Me effects")
    lines.append("=" * 72)
    lines.append(f"Input data: {data_file}")
    lines.append("")
    lines.append("Model formulae:")
    for outcome, formula in formula_by_outcome.items():
        lines.append(f"  {outcome}: {formula}")
    lines.append("")

    for outcome, label in PRIMARY_OUTCOMES:
        sub = results[results["outcome"] == outcome].copy()
        if sub.empty:
            continue
        n_obs = int(sub["n_obs"].iloc[0])
        n_speakers = int(sub["n_speakers"].iloc[0])
        lines.append(f"{label} ({outcome}; N={n_obs}, speakers={n_speakers})")
        lines.append("-" * 72)
        for _, row in sub.iterrows():
            ci_txt = ""
            if pd.notna(row["effect_pct_ci_low"]) and pd.notna(row["effect_pct_ci_high"]):
                ci_txt = (
                    f", 95% CI [{format_pct(row['effect_pct_ci_low'])}, "
                    f"{format_pct(row['effect_pct_ci_high'])}]"
                )
            p_txt = "NA" if pd.isna(row["p"]) else f"{float(row['p']):.4g}"
            df_txt = "" if pd.isna(row["df"]) else f", df={float(row['df']):.2f}"
            lines.append(
                f"  {row['method']}: {format_pct(row['effect_pct_per_10mm'])} per 10 mm"
                f"{ci_txt}, p={p_txt}{df_txt}"
            )
        lines.append("")

    lines.append("Interpretation note:")
    lines.append(
        "  The manuscript GEE-independence row reproduces the existing normal-theory "
        "cluster-sandwich result. The CR2 row is the most conservative single-row "
        "small-sample correction because it uses a leverage-adjusted cluster "
        "sandwich SE and Satterthwaite degrees of freedom. The speaker-cluster "
        "bootstrap row gives a nonparametric speaker-resampling percentile CI. "
        "The wild-cluster row gives a restricted-null bootstrap-t p value."
    )
    lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")


# -----------------------------------------------------------------------------
# Main analysis
# -----------------------------------------------------------------------------


def run_analysis(
    data_file: Path,
    out_dir: Path,
    n_cluster_boot: int,
    n_wild_boot: int,
    seed: int,
    run_wild: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_prepare_data(data_file)

    results_rows: List[Dict[str, object]] = []
    cluster_boot_draw_rows: List[pd.DataFrame] = []
    wild_draw_rows: List[pd.DataFrame] = []
    formula_by_outcome: Dict[str, str] = {}

    for outcome_i, (outcome, label) in enumerate(PRIMARY_OUTCOMES):
        y, X, clusters, columns, formula = build_design(df, outcome)
        formula_by_outcome[outcome] = formula
        coef_idx = columns.index(SIZE_TERM)
        n_obs = int(len(y))
        n_speakers = int(len(np.unique(clusters)))

        beta, resid, XtX_inv = ols_fit(X, y)
        beta_size = float(beta[coef_idx])

        # Manuscript-equivalent CR0 sandwich + normal Wald test.
        cov_cr0 = cluster_cr0_cov(X, resid, clusters, XtX_inv)
        se_cr0 = math.sqrt(max(float(cov_cr0[coef_idx, coef_idx]), 0.0))
        z_stat = beta_size / se_cr0
        p_norm = float(2.0 * stats.norm.sf(abs(z_stat)))
        ci_norm = (beta_size - 1.96 * se_cr0, beta_size + 1.96 * se_cr0)
        add_result_row(
            results_rows,
            outcome=outcome,
            outcome_label=label,
            method="manuscript_GEE_independence_CR0_z",
            n_obs=n_obs,
            n_speakers=n_speakers,
            beta=beta_size,
            se=se_cr0,
            df=None,
            statistic=z_stat,
            p_value=p_norm,
            ci_low=ci_norm[0],
            ci_high=ci_norm[1],
            n_boot=None,
            seed=None,
            note=(
                "Gaussian identity-link GEE with independence working correlation; "
                "equivalent to OLS coefficient with CR0 participant-cluster sandwich SE; "
                "normal-theory Wald CI/p."
            ),
        )

        # Same CR0 SE, but use t_{G-1}; useful as a transparent df-only correction.
        df_cluster = float(n_speakers - 1)
        t_stat_cr0 = beta_size / se_cr0
        p_t_cr0 = float(2.0 * stats.t.sf(abs(t_stat_cr0), df_cluster))
        tcrit_cr0 = float(stats.t.ppf(0.975, df_cluster))
        ci_cr0_t = (beta_size - tcrit_cr0 * se_cr0, beta_size + tcrit_cr0 * se_cr0)
        add_result_row(
            results_rows,
            outcome=outcome,
            outcome_label=label,
            method="CR0_cluster_t_df_Gminus1",
            n_obs=n_obs,
            n_speakers=n_speakers,
            beta=beta_size,
            se=se_cr0,
            df=df_cluster,
            statistic=t_stat_cr0,
            p_value=p_t_cr0,
            ci_low=ci_cr0_t[0],
            ci_high=ci_cr0_t[1],
            n_boot=None,
            seed=None,
            note="Same CR0 SE as manuscript row, but p/CI use t distribution with speakers-1 df.",
        )

        # CR2/Bell-McCaffrey correction with Satterthwaite df.
        cr2_cache = make_cr2_cache(X, clusters, coef_idx)
        se_cr2, df_cr2, t_cr2, ci_cr2 = cr2_from_residuals(cr2_cache, beta, resid)
        p_cr2 = float(2.0 * stats.t.sf(abs(t_cr2), df_cr2))
        add_result_row(
            results_rows,
            outcome=outcome,
            outcome_label=label,
            method="CR2_BellMcCaffrey_Satterthwaite",
            n_obs=n_obs,
            n_speakers=n_speakers,
            beta=beta_size,
            se=se_cr2,
            df=df_cr2,
            statistic=t_cr2,
            p_value=p_cr2,
            ci_low=ci_cr2[0],
            ci_high=ci_cr2[1],
            n_boot=None,
            seed=None,
            note=(
                "Python implementation of an OLS CR2/Bell-McCaffrey leverage adjustment "
                "with Satterthwaite df; conceptually closest to an R clubSandwich CR2 check."
            ),
        )

        # Speaker-cluster bootstrap percentile CI.
        boot_seed = seed + 1000 * outcome_i
        boot_betas = speaker_cluster_bootstrap_betas(
            X=X,
            y=y,
            clusters=clusters,
            coef_idx=coef_idx,
            n_boot=n_cluster_boot,
            seed=boot_seed,
        )
        boot_ci = np.percentile(boot_betas, [2.5, 97.5])
        boot_se = float(np.std(boot_betas, ddof=1))
        # Two-sided sign/bootstrap p with a +1 finite-simulation adjustment.
        p_lower = (1.0 + np.sum(boot_betas <= 0.0)) / (n_cluster_boot + 1.0)
        p_upper = (1.0 + np.sum(boot_betas >= 0.0)) / (n_cluster_boot + 1.0)
        p_boot = float(min(1.0, 2.0 * min(p_lower, p_upper)))
        add_result_row(
            results_rows,
            outcome=outcome,
            outcome_label=label,
            method="speaker_cluster_bootstrap_percentile",
            n_obs=n_obs,
            n_speakers=n_speakers,
            beta=beta_size,
            se=boot_se,
            df=None,
            statistic=None,
            p_value=p_boot,
            ci_low=float(boot_ci[0]),
            ci_high=float(boot_ci[1]),
            n_boot=n_cluster_boot,
            seed=boot_seed,
            note="Nonparametric speaker-cluster bootstrap; speakers resampled with replacement; percentile CI.",
        )

        cluster_boot_draw_rows.append(
            pd.DataFrame(
                {
                    "outcome": outcome,
                    "outcome_label": label,
                    "draw": np.arange(1, n_cluster_boot + 1, dtype=int),
                    "beta_log_per_10mm": boot_betas,
                    "effect_pct_per_10mm": pct_from_log_beta(boot_betas),
                    "seed": boot_seed,
                }
            )
        )

        # Optional wild-cluster bootstrap-t p value.
        if run_wild:
            wild_seed = seed + 500_000 + 1000 * outcome_i
            p_wild, t_draws = wild_cluster_bootstrap_t(
                X=X,
                y=y,
                clusters=clusters,
                coef_idx=coef_idx,
                cache=cr2_cache,
                n_boot=n_wild_boot,
                seed=wild_seed,
            )
            add_result_row(
                results_rows,
                outcome=outcome,
                outcome_label=label,
                method="wild_cluster_bootstrap_t_CR2_null",
                n_obs=n_obs,
                n_speakers=n_speakers,
                beta=beta_size,
                se=se_cr2,
                df=df_cr2,
                statistic=t_cr2,
                p_value=p_wild,
                ci_low=None,
                ci_high=None,
                n_boot=n_wild_boot,
                seed=wild_seed,
                note=(
                    "Restricted-null Rademacher wild-cluster bootstrap-t p value; "
                    "test statistic is the CR2 t statistic. CI not computed by test inversion."
                ),
            )
            wild_draw_rows.append(
                pd.DataFrame(
                    {
                        "outcome": outcome,
                        "outcome_label": label,
                        "draw": np.arange(1, n_wild_boot + 1, dtype=int),
                        "t_star": t_draws,
                        "abs_t_star": np.abs(t_draws),
                        "t_observed_CR2": t_cr2,
                        "seed": wild_seed,
                    }
                )
            )

    results = pd.DataFrame(results_rows)

    # Stable ordering for readability.
    method_order = {
        "manuscript_GEE_independence_CR0_z": 0,
        "CR0_cluster_t_df_Gminus1": 1,
        "CR2_BellMcCaffrey_Satterthwaite": 2,
        "speaker_cluster_bootstrap_percentile": 3,
        "wild_cluster_bootstrap_t_CR2_null": 4,
    }
    results["method_order"] = results["method"].map(method_order).fillna(99)
    results = results.sort_values(["outcome", "method_order"]).drop(columns=["method_order"])

    results_file = out_dir / "primary_effects_small_sample_robustness.csv"
    summary_file = out_dir / "primary_effects_small_sample_robustness_summary.txt"
    cluster_draws_file = out_dir / "primary_effects_cluster_bootstrap_draws.csv.gz"
    wild_draws_file = out_dir / "primary_effects_wild_cluster_t_draws.csv.gz"

    results.to_csv(results_file, index=False)
    pd.concat(cluster_boot_draw_rows, ignore_index=True).to_csv(
        cluster_draws_file, index=False, compression="gzip"
    )
    if wild_draw_rows:
        pd.concat(wild_draw_rows, ignore_index=True).to_csv(
            wild_draws_file, index=False, compression="gzip"
        )

    write_summary(summary_file, results, data_file, formula_by_outcome)

    print("\nSmall-sample robustness checks completed.")
    print(f"Input data: {data_file}")
    print(f"Output directory: {out_dir}")
    print(f"\nMain results CSV: {results_file}")
    print(f"Summary TXT:      {summary_file}")
    print(f"Bootstrap draws:  {cluster_draws_file}")
    if wild_draw_rows:
        print(f"Wild t draws:     {wild_draws_file}")
    print("\nKey rows:")
    display_cols = [
        "outcome_label",
        "method",
        "effect_pct_per_10mm",
        "effect_pct_ci_low",
        "effect_pct_ci_high",
        "p",
        "df",
    ]
    with pd.option_context("display.max_colwidth", 48, "display.width", 180):
        print(results[display_cols].to_string(index=False))


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Small-sample cluster-robustness checks for the two primary Co--Me effects."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root. Default: current working directory.",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=None,
        help="Path to analysis_dataset_clean.csv. Default: search common project locations.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Default: a primary_effect_small_sample_robustness folder under outputs*/ or project root.",
    )
    parser.add_argument(
        "--n-cluster-boot",
        type=int,
        default=9999,
        help="Number of speaker-cluster bootstrap draws. Default: 9999.",
    )
    parser.add_argument(
        "--n-wild-boot",
        type=int,
        default=9999,
        help="Number of wild-cluster bootstrap-t draws. Default: 9999.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260420,
        help="Base random seed. Default: 20260420.",
    )
    parser.add_argument(
        "--skip-wild",
        action="store_true",
        help="Skip the wild-cluster bootstrap-t p value. CR2 and speaker-cluster bootstrap still run.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    project_root = args.project_root.resolve()
    data_file = args.data_file.resolve() if args.data_file is not None else find_default_data_file(project_root)
    out_dir = args.out_dir.resolve() if args.out_dir is not None else default_out_dir(project_root)

    if args.n_cluster_boot < 99:
        raise ValueError("Use at least 99 cluster bootstrap draws; 9999 is recommended for final results.")
    if not args.skip_wild and args.n_wild_boot < 99:
        raise ValueError("Use at least 99 wild bootstrap draws; 9999 is recommended for final results.")

    run_analysis(
        data_file=data_file,
        out_dir=out_dir,
        n_cluster_boot=args.n_cluster_boot,
        n_wild_boot=args.n_wild_boot,
        seed=args.seed,
        run_wild=not args.skip_wild,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
