#!/usr/bin/env python3
"""Generate V8 main Figures 1-2, Table 1, and reproducible figure data products.

The script implements the author-approved participant-clustered Gaussian
identity-link GEE models with an independence working correlation and robust
sandwich covariance. It never plots trial-level clouds. Speaker summaries are
strictly descriptive; model lines are standardized predictions.

All input and output paths are explicit command-line arguments. A fixed seed is
required and set even though the current design uses no random jitter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any, Iterable

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import patsy
from scipy.stats import norm
import scipy
import statsmodels
import statsmodels.api as sm
import statsmodels.formula.api as smf

PRIMARY_SHA256 = "25aaddf2ac0894b19bab058afe1fbe153b5e81b3ed4f744813e4e03c72094084"
SECONDARY_SHA256 = "252915545c66ca6489e863057d8931aa1e05aa6c84577247c4b2595520c31598"
SHARED_SEQUENCES = ("kukuku", "pipipi", "tatata", "kutapi", "pitaku", "takupi")
RATE_ORDER = ("normal", "fast")
RATE_LABEL = {"normal": "Habitual", "fast": "Maximally fast"}
RATE_COLOR = {"normal": "#0072B2", "fast": "#D55E00"}  # Okabe-Ito blue / vermillion
RATE_MARKER = {"normal": "o", "fast": "^"}
RATE_LINESTYLE = {"normal": "-", "fast": "--"}
Z975 = float(norm.ppf(0.975))

PRIMARY_OUTCOMES = {
    "log_speechrate": {
        "raw": "speechrate",
        "panel": "A",
        "label": "Speech rate",
        "ylabel": "Speech rate (syllables/s)",
        "unit": "syllables/s",
    },
    "log_articulationrate": {
        "raw": "articulationrate",
        "panel": "B",
        "label": "Articulation rate",
        "ylabel": "Articulation rate (syllables/s)",
        "unit": "syllables/s",
    },
}

SECONDARY_OUTCOMES = {
    "ema_cycle_rate_hz": {
        "panel": "A",
        "label": "Jaw-cycle rate",
        "ylabel": "Jaw-cycle rate (Hz)",
        "unit": "Hz",
        "effect_digits": 3,
    },
    "jaw_open_amp_median_mm": {
        "panel": "B",
        "label": "Scalar jaw-opening excursion",
        "ylabel": "Scalar jaw-opening excursion (mm)",
        "unit": "mm",
        "effect_digits": 3,
    },
    "audio_mod_dom_hz": {
        "panel": "C",
        "label": "Dominant envelope modulation",
        "ylabel": "Dominant envelope modulation (Hz)",
        "unit": "Hz",
        "effect_digits": 3,
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_rate(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.lower()
        .replace({"habitual": "normal", "habit": "normal", "maximum": "fast", "maximal": "fast", "max": "fast"})
    )


def normalize_sequence(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()


def fit_gee(data: pd.DataFrame, formula: str):
    model = smf.gee(
        formula=formula,
        groups="participant_id",
        data=data,
        cov_struct=sm.cov_struct.Independence(),
        family=sm.families.Gaussian(sm.families.links.Identity()),
    )
    return model.fit(cov_type="robust")


def prep_primary(path: Path) -> pd.DataFrame:
    if sha256(path) != PRIMARY_SHA256:
        raise ValueError(f"Wrong primary-data hash for {path}; expected {PRIMARY_SHA256}")
    d = pd.read_csv(path)
    if len(d) != 8123 or d["participant_id"].nunique() != 28:
        raise ValueError(f"Primary data must contain 8,123 rows and 28 speakers; found {len(d)} and {d['participant_id'].nunique()}")
    d["rate"] = normalize_rate(d["rate"])
    d["sequence"] = normalize_sequence(d["sequence"])
    d["co_me_mean_mm_10"] = pd.to_numeric(d["co_me_mean_mm"], errors="raise") / 10.0
    d["height_cm"] = pd.to_numeric(d["height_cm"], errors="raise")
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean())
    d["log_speechrate"] = np.log(pd.to_numeric(d["speechrate"], errors="raise"))
    d["log_articulationrate"] = np.log(pd.to_numeric(d["articulationrate"], errors="raise"))
    if d.groupby("participant_id")["co_me_mean_mm"].nunique().max() != 1:
        raise ValueError("Co--Me is not constant within primary-data speaker")
    if d.groupby("participant_id")["height_cm"].nunique().max() != 1:
        raise ValueError("Height is not constant within primary-data speaker")
    shared = d[d["sequence"].isin(SHARED_SEQUENCES)]
    if len(shared) != 6456 or shared["participant_id"].nunique() != 28:
        raise ValueError(f"Shared-six primary subset must contain 6,456 rows and 28 speakers; found {len(shared)} and {shared['participant_id'].nunique()}")
    return d


def prep_secondary(path: Path) -> pd.DataFrame:
    if sha256(path) != SECONDARY_SHA256:
        raise ValueError(f"Wrong secondary-data hash for {path}; expected {SECONDARY_SHA256}")
    d = pd.read_csv(path)
    if len(d) != 6134 or d["participant_id"].nunique() != 23:
        raise ValueError(f"Secondary parent table must contain 6,134 rows and 23 speakers; found {len(d)} and {d['participant_id'].nunique()}")
    d["rate"] = normalize_rate(d["rate"])
    d["sequence"] = normalize_sequence(d["sequence"])
    d["co_me_mean_mm_10"] = pd.to_numeric(d["co_me_mean_mm"], errors="raise") / 10.0
    d["height_cm"] = pd.to_numeric(d["height_m"], errors="raise") * 100.0
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean())
    if d.groupby("participant_id")["co_me_mean_mm"].nunique().max() != 1:
        raise ValueError("Co--Me is not constant within secondary-data speaker")
    if d.groupby("participant_id")["height_cm"].nunique().max() != 1:
        raise ValueError("Height is not constant within secondary-data speaker")
    expected = {
        "analysis_ok_true": (int(d["analysis_ok"].sum()), int(d.loc[d["analysis_ok"], "participant_id"].nunique()), 6056, 23),
        "ema_cycle_rate_hz": (int(d["ema_cycle_rate_hz"].notna().sum()), int(d.loc[d["ema_cycle_rate_hz"].notna(), "participant_id"].nunique()), 3323, 22),
        "jaw_open_amp_median_mm": (int(d["jaw_open_amp_median_mm"].notna().sum()), int(d.loc[d["jaw_open_amp_median_mm"].notna(), "participant_id"].nunique()), 3323, 22),
        "audio_mod_dom_hz": (int(d["audio_mod_dom_hz"].notna().sum()), int(d.loc[d["audio_mod_dom_hz"].notna(), "participant_id"].nunique()), 5572, 23),
    }
    for name, (nobs, nspk, exp_obs, exp_spk) in expected.items():
        if (nobs, nspk) != (exp_obs, exp_spk):
            raise ValueError(f"Secondary count mismatch for {name}: found {nobs}/{nspk}; expected {exp_obs}/{exp_spk}")
    return d


def fit_primary_models(d: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for outcome in PRIMARY_OUTCOMES:
        specs = [
            (f"full_no_height_{outcome}", d, "bibibi", False),
            (f"full_height_adjusted_{outcome}", d, "bibibi", True),
            (f"shared_six_no_height_{outcome}", d[d["sequence"].isin(SHARED_SEQUENCES)].copy(), "kutapi", False),
            (f"shared_six_height_adjusted_{outcome}", d[d["sequence"].isin(SHARED_SEQUENCES)].copy(), "kutapi", True),
        ]
        for model_id, dat, seq_ref, include_height in specs:
            formula = (
                f"{outcome} ~ C(rate, Treatment(reference='fast')) + "
                f"C(sequence, Treatment(reference='{seq_ref}')) + co_me_mean_mm_10"
            )
            if include_height:
                formula += " + height_cm_c"
            out[model_id] = fit_gee(dat, formula)
    return out


def fit_secondary_models(d: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for outcome in SECONDARY_OUTCOMES:
        formula = f"{outcome} ~ C(rate) + C(sequence) + co_me_mean_mm_10 + height_cm_c"
        out[outcome] = fit_gee(d, formula)
    return out


def compare_result_to_primary_canonical(result: Any, canonical: pd.DataFrame, model_id: str) -> dict[str, float]:
    c = canonical[canonical["model_id"].eq(model_id)].copy()
    if c.empty:
        raise ValueError(f"No canonical primary coefficients for {model_id}")
    c = c.set_index("term")
    missing = set(result.params.index) ^ set(c.index)
    if missing:
        raise ValueError(f"Primary coefficient-term mismatch for {model_id}: {sorted(missing)}")
    ci = result.conf_int()
    return {
        "max_abs_beta_diff": float(np.max(np.abs(result.params - c.loc[result.params.index, "beta"]))),
        "max_abs_se_diff": float(np.max(np.abs(result.bse - c.loc[result.params.index, "robust_se"]))),
        "max_abs_ci_lower_diff": float(np.max(np.abs(ci.iloc[:, 0] - c.loc[result.params.index, "ci_lower_beta"]))),
        "max_abs_ci_upper_diff": float(np.max(np.abs(ci.iloc[:, 1] - c.loc[result.params.index, "ci_upper_beta"]))),
        "max_abs_p_diff": float(np.max(np.abs(result.pvalues - c.loc[result.params.index, "p_value"]))),
    }


def compare_result_to_secondary_canonical(
    result: Any,
    canonical: pd.DataFrame,
    outcome: str,
    co_me_center_10: float,
) -> dict[str, float]:
    """Compare after the canonical secondary intercept reparameterization.

    The retained secondary coefficient table centers Co--Me at the parent-table
    mean but retains the generic term label ``co_me_mean_mm_10``. The refit used
    for plotting is algebraically equivalent and uses the uncentered predictor.
    Transforming the intercept and covariance makes every coefficient directly
    comparable without changing fitted values or the +10-mm slope.
    """
    c = canonical[(canonical["outcome"].eq(outcome)) & (canonical["model"].eq("height"))].copy().set_index("term")
    if c.empty:
        raise ValueError(f"No canonical secondary coefficients for {outcome}")
    names = list(result.params.index)
    missing = set(names) ^ set(c.index)
    if missing:
        raise ValueError(f"Secondary coefficient-term mismatch for {outcome}: {sorted(missing)}")
    T = np.eye(len(names))
    i0 = names.index("Intercept")
    ic = names.index("co_me_mean_mm_10")
    T[i0, ic] = float(co_me_center_10)
    beta = T @ np.asarray(result.params, dtype=float)
    cov = T @ np.asarray(result.cov_params(), dtype=float) @ T.T
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    lo = beta - Z975 * se
    hi = beta + Z975 * se
    z = np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)
    p = 2.0 * norm.sf(np.abs(z))
    c = c.loc[names]
    return {
        "max_abs_beta_diff": float(np.max(np.abs(beta - c["estimate"].to_numpy()))),
        "max_abs_se_diff": float(np.max(np.abs(se - c["se"].to_numpy()))),
        "max_abs_ci_lower_diff": float(np.max(np.abs(lo - c["ci_low"].to_numpy()))),
        "max_abs_ci_upper_diff": float(np.max(np.abs(hi - c["ci_high"].to_numpy()))),
        "max_abs_p_diff": float(np.max(np.abs(p - c["p"].to_numpy()))),
    }


def design_matrix(result: Any, new_data: pd.DataFrame) -> np.ndarray:
    info = result.model.data.design_info
    return np.asarray(patsy.build_design_matrices([info], new_data, return_type="dataframe")[0], dtype=float)


def prediction_rows(
    *,
    result: Any,
    outcome_id: str,
    figure: str,
    panel: str,
    x_values: np.ndarray,
    transform_exp: bool,
    n_obs: int,
    n_spk: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cov = np.asarray(result.cov_params(), dtype=float)
    beta = np.asarray(result.params, dtype=float)
    for rate in RATE_ORDER:
        for x_mm in x_values:
            new = pd.DataFrame(
                {
                    "rate": [rate] * len(SHARED_SEQUENCES),
                    "sequence": list(SHARED_SEQUENCES),
                    "co_me_mean_mm_10": [float(x_mm) / 10.0] * len(SHARED_SEQUENCES),
                    "height_cm_c": [0.0] * len(SHARED_SEQUENCES),
                }
            )
            X = design_matrix(result, new)
            eta = X @ beta
            if transform_exp:
                mu_seq = np.exp(eta)
                pred = float(mu_seq.mean())
                weights = mu_seq / mu_seq.sum()
                grad_log = weights @ X
                se_log = math.sqrt(max(float(grad_log @ cov @ grad_log.T), 0.0))
                lo = pred * math.exp(-Z975 * se_log)
                hi = pred * math.exp(Z975 * se_log)
                modeled_scale = "log outcome; response-scale mean across shared sequences"
            else:
                xbar = X.mean(axis=0)
                pred = float(xbar @ beta)
                se = math.sqrt(max(float(xbar @ cov @ xbar.T), 0.0))
                lo = pred - Z975 * se
                hi = pred + Z975 * se
                modeled_scale = "identity outcome; arithmetic mean across shared sequences"
            rows.append(
                {
                    "figure": figure,
                    "panel": panel,
                    "outcome_id": outcome_id,
                    "rate": rate,
                    "rate_label": RATE_LABEL[rate],
                    "co_me_mean_mm": float(x_mm),
                    "height_cm_c": 0.0,
                    "prediction": pred,
                    "ci_lower": lo,
                    "ci_upper": hi,
                    "prediction_standardization": "mean centered height; standardized over kukuku, pipipi, tatata, kutapi, pitaku, takupi",
                    "modeled_scale": modeled_scale,
                    "n_observations": n_obs,
                    "n_speakers": n_spk,
                    "working_correlation": "independence",
                    "covariance_estimator": "robust sandwich",
                }
            )
    return rows


def make_primary_speaker_summaries(d: pd.DataFrame) -> pd.DataFrame:
    s = d[d["sequence"].isin(SHARED_SEQUENCES)].copy()
    g = (
        s.groupby(["participant_id", "rate"], as_index=False)
        .agg(
            co_me_mean_mm=("co_me_mean_mm", "first"),
            height_cm=("height_cm", "first"),
            n_observations=("participant_id", "size"),
            n_sequences=("sequence", "nunique"),
            speechrate=("speechrate", "mean"),
            articulationrate=("articulationrate", "mean"),
        )
    )
    pieces: list[pd.DataFrame] = []
    for outcome_id, spec in PRIMARY_OUTCOMES.items():
        raw = spec["raw"]
        q = g[["participant_id", "rate", "co_me_mean_mm", "height_cm", "n_observations", "n_sequences", raw]].copy()
        q = q.rename(columns={raw: "speaker_mean"})
        q.insert(0, "figure", "Figure 1")
        q.insert(1, "panel", spec["panel"])
        q.insert(2, "outcome_id", outcome_id)
        q.insert(3, "outcome_label", spec["label"])
        q["outcome_unit"] = spec["unit"]
        q["rate_label"] = q["rate"].map(RATE_LABEL)
        q["sequence_scope"] = "six sequences shared by both instructed-rate conditions"
        q["descriptive_summary"] = "arithmetic mean across available trials within speaker and rate"
        pieces.append(q)
    out = pd.concat(pieces, ignore_index=True)
    if out.duplicated(["outcome_id", "participant_id", "rate"]).any():
        raise ValueError("Figure 1 speaker summaries contain duplicate speaker-rate rows")
    return out.sort_values(["panel", "participant_id", "rate"]).reset_index(drop=True)


def make_secondary_speaker_summaries(d: pd.DataFrame) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for outcome_id, spec in SECONDARY_OUTCOMES.items():
        s = d[d[outcome_id].notna()].copy()
        g = (
            s.groupby(["participant_id", "rate"], as_index=False)
            .agg(
                co_me_mean_mm=("co_me_mean_mm", "first"),
                height_cm=("height_cm", "first"),
                n_observations=("participant_id", "size"),
                n_sequences=("sequence", "nunique"),
                speaker_mean=(outcome_id, "mean"),
            )
        )
        g.insert(0, "figure", "Figure 2")
        g.insert(1, "panel", spec["panel"])
        g.insert(2, "outcome_id", outcome_id)
        g.insert(3, "outcome_label", spec["label"])
        g["outcome_unit"] = spec["unit"]
        g["rate_label"] = g["rate"].map(RATE_LABEL)
        g["sequence_scope"] = "all outcome-complete cases; model lines standardized over the shared six sequences"
        g["descriptive_summary"] = "arithmetic mean across outcome-complete trials within speaker and rate"
        if g.duplicated(["participant_id", "rate"]).any():
            raise ValueError(f"Figure 2 {outcome_id} summaries contain duplicate speaker-rate rows")
        pieces.append(g)
    return pd.concat(pieces, ignore_index=True).sort_values(["panel", "participant_id", "rate"]).reset_index(drop=True)


def canonical_effect_rows(primary_comp: pd.DataFrame, secondary_effects: pd.DataFrame) -> pd.DataFrame:
    p = primary_comp.copy()
    p_out: list[dict[str, Any]] = []
    for r in p.itertuples(index=False):
        outcome_label = "Speech rate" if r.outcome == "log_speechrate" else "Articulation rate"
        p_out.append(
            {
                "tier": "Primary",
                "domain": "DDK timing",
                "outcome_id": r.outcome,
                "outcome_label": outcome_label,
                "data_subset": r.data_subset,
                "specification": "Height conditioned" if bool(r.include_height) else "No height",
                "model_id": r.model_id,
                "beta": r.beta,
                "robust_se": r.robust_se,
                "effect": r.transformed_effect_percent,
                "ci_lower": r.transformed_ci_lower_percent,
                "ci_upper": r.transformed_ci_upper_percent,
                "p_value": r.p_value,
                "effect_unit": "% change per +10 mm Co--Me",
                "n_speakers": r.n_speakers,
                "n_observations": r.n_observations,
                "used_in_figure_1c": bool(r.data_subset == "all_eligible_trials"),
                "used_in_figure_2": False,
                "used_in_table_1": bool(r.data_subset == "all_eligible_trials" and r.include_height),
                "authority": "PRIMARY_ESTIMAND_COMPARISON_CURRENT.csv; primary data hash verified",
            }
        )
    s = secondary_effects[(secondary_effects["outcome"].isin(SECONDARY_OUTCOMES))].copy()
    for r in s.itertuples(index=False):
        spec = SECONDARY_OUTCOMES[r.outcome]
        p_out.append(
            {
                "tier": "Secondary",
                "domain": "EMA" if r.domain == "ema" else "Audio",
                "outcome_id": r.outcome,
                "outcome_label": spec["label"],
                "data_subset": "outcome-complete cases",
                "specification": "Height conditioned" if r.model == "height" else "No height",
                "model_id": f"{r.outcome}_{r.model}",
                "beta": r.beta,
                "robust_se": r.se,
                "effect": r.effect_units,
                "ci_lower": r.effect_units_ci_low,
                "ci_upper": r.effect_units_ci_high,
                "p_value": r.p,
                "effect_unit": f"{spec['unit']} per +10 mm Co--Me",
                "n_speakers": r.n_participants,
                "n_observations": r.nobs,
                "used_in_figure_1c": False,
                "used_in_figure_2": bool(r.model == "height"),
                "used_in_table_1": bool(r.model == "height"),
                "authority": "effect_sizes_per_10mm.csv verified against V4 exact Co--Me values and canonical data",
            }
        )
    out = pd.DataFrame(p_out)
    return out.sort_values(["tier", "outcome_label", "data_subset", "specification"]).reset_index(drop=True)


def style_axes(ax: Any) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)
    ax.tick_params(axis="both", width=0.7, length=3, pad=2)
    ax.grid(axis="y", color="0.92", linewidth=0.6, zorder=0)


def panel_label(ax: Any, letter: str) -> None:
    ax.text(-0.16, 1.06, letter, transform=ax.transAxes, fontsize=10.5, fontweight="bold", va="top")


def draw_speaker_panel(
    ax: Any,
    summaries: pd.DataFrame,
    predictions: pd.DataFrame,
    ylabel: str,
    title: str,
) -> None:
    # Light connectors link two repeated instructed-rate summaries of one anatomical unit.
    wide = summaries.pivot(index="participant_id", columns="rate", values=["co_me_mean_mm", "speaker_mean"])
    for _, row in wide.iterrows():
        if ("speaker_mean", "normal") in row.index and ("speaker_mean", "fast") in row.index:
            if pd.notna(row[("speaker_mean", "normal")]) and pd.notna(row[("speaker_mean", "fast")]):
                x = float(row[("co_me_mean_mm", "normal")])
                ax.plot(
                    [x, x],
                    [row[("speaker_mean", "normal")], row[("speaker_mean", "fast")]],
                    color="0.78",
                    linewidth=0.55,
                    alpha=0.8,
                    zorder=1,
                )
    for rate in RATE_ORDER:
        q = summaries[summaries["rate"].eq(rate)]
        ax.scatter(
            q["co_me_mean_mm"],
            q["speaker_mean"],
            s=27,
            marker=RATE_MARKER[rate],
            facecolor=RATE_COLOR[rate],
            edgecolor="white",
            linewidth=0.55,
            alpha=0.9,
            zorder=3,
        )
        p = predictions[predictions["rate"].eq(rate)].sort_values("co_me_mean_mm")
        ax.fill_between(
            p["co_me_mean_mm"], p["ci_lower"], p["ci_upper"],
            color=RATE_COLOR[rate], alpha=0.14, linewidth=0, zorder=1,
        )
        ax.plot(
            p["co_me_mean_mm"], p["prediction"],
            color=RATE_COLOR[rate], linestyle=RATE_LINESTYLE[rate], linewidth=1.55, zorder=2,
        )
    ax.set_title(title, pad=5, fontweight="semibold")
    ax.set_xlabel("Bilateral mean external Co-Me (mm)")
    ax.set_ylabel(ylabel)
    style_axes(ax)


def figure1(
    summaries: pd.DataFrame,
    predictions: pd.DataFrame,
    effects: pd.DataFrame,
    out_pdf: Path,
    out_png: Path,
) -> None:
    fig = plt.figure(figsize=(7.45, 3.25))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.05, 0.90], left=0.075, right=0.985, bottom=0.18, top=0.84, wspace=0.40)
    for i, (outcome_id, spec) in enumerate(PRIMARY_OUTCOMES.items()):
        ax = fig.add_subplot(gs[0, i])
        panel_summaries = summaries[summaries["outcome_id"].eq(outcome_id)]
        panel_predictions = predictions[predictions["outcome_id"].eq(outcome_id)]
        draw_speaker_panel(
            ax,
            panel_summaries,
            panel_predictions,
            spec["ylabel"],
            spec["label"],
        )
        n_speakers = int(panel_predictions["n_speakers"].iloc[0])
        ax.text(
            0.98,
            0.97,
            f"N = {n_speakers} speakers",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=6.7,
            bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor="none", alpha=0.82),
            zorder=5,
        )
        panel_label(ax, spec["panel"])
    # Panel C: full-data estimand comparison only.
    ax = fig.add_subplot(gs[0, 2])
    style_axes(ax)
    ax.grid(False)
    ax.axvline(0, color="0.35", linewidth=0.8, linestyle=":", zorder=0)
    y_base = {"Speech rate": 1.0, "Articulation rate": 0.0}
    styles = {
        "Height conditioned": dict(marker="s", facecolor="0.15", edgecolor="0.15", color="0.15", label="Height conditioned"),
        "No height": dict(marker="D", facecolor="white", edgecolor="0.45", color="0.45", label="No height"),
    }
    offsets = {"Height conditioned": -0.11, "No height": 0.11}
    c = effects[(effects["tier"].eq("Primary")) & (effects["data_subset"].eq("all_eligible_trials"))]
    for spec_name in ["No height", "Height conditioned"]:
        q = c[c["specification"].eq(spec_name)]
        st = styles[spec_name]
        for r in q.itertuples(index=False):
            y = y_base[r.outcome_label] + offsets[spec_name]
            ax.errorbar(
                r.effect,
                y,
                xerr=np.array([[r.effect - r.ci_lower], [r.ci_upper - r.effect]]),
                fmt=st["marker"],
                markersize=5.0,
                markerfacecolor=st["facecolor"],
                markeredgecolor=st["edgecolor"],
                color=st["color"],
                elinewidth=1.1,
                capsize=2.2,
                capthick=0.8,
                zorder=3,
            )
    ax.set_yticks([0, 1], ["Articulation rate", "Speech rate"])
    ax.set_xlabel("Percent change per +10 mm Co-Me")
    ax.set_title("Full-data effect comparison", pad=5, fontweight="semibold")
    panel_label(ax, "C")
    xmin = float(c["ci_lower"].min()) - 0.8
    xmax = max(2.0, float(c["ci_upper"].max()) + 0.8)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(-0.45, 1.45)
    ax.text(0.98, 0.97, "N = 28 speakers", transform=ax.transAxes, ha="right", va="top", fontsize=7.2)
    ax.legend(
        handles=[
            Line2D([0], [0], marker="s", color="0.15", markerfacecolor="0.15", markersize=5, linestyle="none", label="Height conditioned"),
            Line2D([0], [0], marker="D", color="0.45", markerfacecolor="white", markersize=5, linestyle="none", label="No height"),
        ],
        loc="lower left",
        frameon=False,
        fontsize=7.0,
        handletextpad=0.4,
        borderaxespad=0.2,
    )
    fig.legend(
        handles=[
            Line2D([0], [0], marker=RATE_MARKER[r], color=RATE_COLOR[r], linestyle=RATE_LINESTYLE[r], markerfacecolor=RATE_COLOR[r], markeredgecolor="white", linewidth=1.4, markersize=5, label=RATE_LABEL[r])
            for r in RATE_ORDER
        ],
        loc="upper center",
        bbox_to_anchor=(0.34, 0.995),
        ncol=2,
        frameon=False,
        columnspacing=1.4,
        handlelength=2.2,
    )
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


def format_effect_annotation(effect: float, lo: float, hi: float, unit: str, nspk: int, nobs: int) -> str:
    return (
        f"Co-Me: {effect:.3f} {unit} per +10 mm\n"
        f"95% CI [{lo:.3f}, {hi:.3f}]\n"
        f"N = {nspk} speakers; {nobs:,} observations"
    )


def figure2(
    summaries: pd.DataFrame,
    predictions: pd.DataFrame,
    effects: pd.DataFrame,
    out_pdf: Path,
    out_png: Path,
) -> None:
    fig = plt.figure(figsize=(7.45, 3.25))
    gs = fig.add_gridspec(1, 3, left=0.075, right=0.988, bottom=0.18, top=0.82, wspace=0.38)
    for i, (outcome_id, spec) in enumerate(SECONDARY_OUTCOMES.items()):
        ax = fig.add_subplot(gs[0, i])
        s = summaries[summaries["outcome_id"].eq(outcome_id)]
        p = predictions[predictions["outcome_id"].eq(outcome_id)]
        draw_speaker_panel(ax, s, p, spec["ylabel"], spec["label"])
        panel_label(ax, spec["panel"])
        e = effects[(effects["outcome_id"].eq(outcome_id)) & (effects["specification"].eq("Height conditioned"))].iloc[0]
        ax.text(
            0.03,
            0.97,
            format_effect_annotation(float(e.effect), float(e.ci_lower), float(e.ci_upper), spec["unit"], int(e.n_speakers), int(e.n_observations)),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.7,
            linespacing=1.25,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="0.75", linewidth=0.5, alpha=0.90),
            zorder=5,
        )
    fig.legend(
        handles=[
            Line2D([0], [0], marker=RATE_MARKER[r], color=RATE_COLOR[r], linestyle=RATE_LINESTYLE[r], markerfacecolor=RATE_COLOR[r], markeredgecolor="white", linewidth=1.4, markersize=5, label=RATE_LABEL[r])
            for r in RATE_ORDER
        ],
        loc="upper center",
        bbox_to_anchor=(0.50, 0.995),
        ncol=2,
        frameon=False,
        columnspacing=1.4,
        handlelength=2.2,
    )
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


def math_signed_tex(x: float, digits: int, percent: bool = False) -> str:
    sign = "-" if x < 0 else "+" if x > 0 else ""
    suffix = r"\%" if percent else ""
    return f"${sign}{abs(x):.{digits}f}{suffix}$"


def tex_count(n: int) -> str:
    return f"{int(n):,}".replace(",", "{,}")


def write_table1(effects: pd.DataFrame, path: Path) -> None:
    rows: list[str] = []
    primary_order = ["Speech rate", "Articulation rate"]
    secondary_order = [
        ("Jaw-cycle rate", "Jaw-cycle rate (Hz)"),
        ("Scalar jaw-opening excursion", "Scalar jaw-opening excursion (mm)"),
        ("Dominant envelope modulation", "Dominant envelope modulation (Hz)"),
    ]
    used = effects[effects["used_in_table_1"]].copy()
    for label in primary_order:
        r = used[(used["outcome_label"].eq(label)) & (used["tier"].eq("Primary"))].iloc[0]
        rows.append(
            f"Primary & {label} & {math_signed_tex(float(r.effect), 2, percent=True)} & "
            f"[{math_signed_tex(float(r.ci_lower), 2, percent=True)}, {math_signed_tex(float(r.ci_upper), 2, percent=True)}] & "
            f"{float(r.p_value):.4f} & {int(r.n_speakers)} & {tex_count(int(r.n_observations))} \\\\"
        )
    rows.append(r"\hline")
    for source_label, display_label in secondary_order:
        r = used[(used["outcome_label"].eq(source_label)) & (used["tier"].eq("Secondary"))].iloc[0]
        p_digits = 5
        rows.append(
            f"Secondary & {display_label} & {math_signed_tex(float(r.effect), 3)} & "
            f"[{math_signed_tex(float(r.ci_lower), 3)}, {math_signed_tex(float(r.ci_upper), 3)}] & "
            f"{float(r.p_value):.{p_digits}f} & {int(r.n_speakers)} & {tex_count(int(r.n_observations))} \\\\"
        )
    text = r"""\begingroup
\makeatletter
\setlength{\@fptop}{0pt}
\setlength{\@fpbot}{0pt plus 1fil}
\makeatother
\clearpage
\endgroup
\begin{table}[t]
\centering
\caption{\textbf{Primary and principal secondary Co--Me associations.} Effects are per +10~mm bilateral mean Co--Me at a given modeled stature. Models controlled for instructed rate condition and syllable sequence and used participant-clustered Gaussian identity-link GEE with an independence working correlation and robust sandwich covariance.}
\label{tab:effects}
\small
\setlength{\tabcolsep}{4.0pt}
\resizebox{\textwidth}{!}{%
\begin{tabular}{llcccrr}
\hline
Tier & Outcome & Effect per +10~mm & 95\% CI & $P$ & $N_{\mathrm{spk}}$ & $N_{\mathrm{obs}}$ \\
\hline
""" + "\n".join(rows) + r"""
\hline
\end{tabular}%
}
\par\vspace{3pt}
\begin{minipage}{0.98\textwidth}
\footnotesize\textit{Note.} $N_{\mathrm{spk}}$ is the number of independent anatomical units (speakers); $N_{\mathrm{obs}}$ is the number of repeated within-speaker observations included in the outcome-specific model. Primary DDK rate effects are percent changes from log-outcome models; secondary effects are in the stated outcome units.
\end{minipage}
\end{table}
"""
    path.write_text(text, encoding="utf-8")


def verify_speaker_means(primary: pd.DataFrame, secondary: pd.DataFrame, s1: pd.DataFrame, s2: pd.DataFrame) -> dict[str, float]:
    diffs: dict[str, float] = {}
    p_shared = primary[primary["sequence"].isin(SHARED_SEQUENCES)]
    for outcome_id, spec in PRIMARY_OUTCOMES.items():
        recalculated = p_shared.groupby(["participant_id", "rate"])[spec["raw"]].mean()
        stored = s1[s1["outcome_id"].eq(outcome_id)].set_index(["participant_id", "rate"])["speaker_mean"]
        diffs[f"Figure1_{outcome_id}"] = float((recalculated.sort_index() - stored.sort_index()).abs().max())
    for outcome_id in SECONDARY_OUTCOMES:
        d = secondary[secondary[outcome_id].notna()]
        recalculated = d.groupby(["participant_id", "rate"])[outcome_id].mean()
        stored = s2[s2["outcome_id"].eq(outcome_id)].set_index(["participant_id", "rate"])["speaker_mean"]
        diffs[f"Figure2_{outcome_id}"] = float((recalculated.sort_index() - stored.sort_index()).abs().max())
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary-data", type=Path, required=True)
    ap.add_argument("--secondary-data", type=Path, required=True)
    ap.add_argument("--primary-estimand-comparison", type=Path, required=True)
    ap.add_argument("--primary-all-coefficients", type=Path, required=True)
    ap.add_argument("--secondary-effects", type=Path, required=True)
    ap.add_argument("--secondary-coefficients", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260722)
    args = ap.parse_args()

    np.random.seed(args.seed)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.8,
            "axes.titlesize": 8.5,
            "axes.labelsize": 7.8,
            "xtick.labelsize": 7.1,
            "ytick.labelsize": 7.1,
            "legend.fontsize": 7.1,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.transparent": False,
        }
    )

    primary = prep_primary(args.primary_data.resolve())
    secondary = prep_secondary(args.secondary_data.resolve())
    primary_comp = pd.read_csv(args.primary_estimand_comparison)
    primary_canonical = pd.read_csv(args.primary_all_coefficients)
    secondary_effects = pd.read_csv(args.secondary_effects)
    secondary_canonical = pd.read_csv(args.secondary_coefficients)

    primary_models = fit_primary_models(primary)
    secondary_models = fit_secondary_models(secondary)

    model_validation: dict[str, dict[str, float]] = {}
    for model_id, result in primary_models.items():
        model_validation[model_id] = compare_result_to_primary_canonical(result, primary_canonical, model_id)
    secondary_co_me_center_10 = float(secondary["co_me_mean_mm_10"].mean())
    for outcome_id, result in secondary_models.items():
        model_validation[f"secondary_height_{outcome_id}"] = compare_result_to_secondary_canonical(
            result, secondary_canonical, outcome_id, secondary_co_me_center_10
        )

    max_beta_diff = max(v["max_abs_beta_diff"] for v in model_validation.values())
    if max_beta_diff > 1e-10:
        raise ValueError(f"Material coefficient mismatch: maximum absolute difference {max_beta_diff:.17g}")

    s1 = make_primary_speaker_summaries(primary)
    s2 = make_secondary_speaker_summaries(secondary)
    effects = canonical_effect_rows(primary_comp, secondary_effects)

    pred_rows: list[dict[str, Any]] = []
    p_x = np.linspace(float(primary["co_me_mean_mm"].min()), float(primary["co_me_mean_mm"].max()), 181)
    for outcome_id, spec in PRIMARY_OUTCOMES.items():
        res = primary_models[f"full_height_adjusted_{outcome_id}"]
        pred_rows.extend(
            prediction_rows(
                result=res,
                outcome_id=outcome_id,
                figure="Figure 1",
                panel=spec["panel"],
                x_values=p_x,
                transform_exp=True,
                n_obs=int(res.nobs),
                n_spk=int(len(res.model.group_labels)),
            )
        )
    for outcome_id, spec in SECONDARY_OUTCOMES.items():
        res = secondary_models[outcome_id]
        complete = secondary[secondary[outcome_id].notna()]
        x = np.linspace(float(complete["co_me_mean_mm"].min()), float(complete["co_me_mean_mm"].max()), 181)
        pred_rows.extend(
            prediction_rows(
                result=res,
                outcome_id=outcome_id,
                figure="Figure 2",
                panel=spec["panel"],
                x_values=x,
                transform_exp=False,
                n_obs=int(res.nobs),
                n_spk=int(len(res.model.group_labels)),
            )
        )
    predictions = pd.DataFrame(pred_rows)

    # Data-product verification before writing.
    speaker_mean_diffs = verify_speaker_means(primary, secondary, s1, s2)
    if max(speaker_mean_diffs.values()) > 1e-12:
        raise ValueError(f"Speaker-mean verification failed: {speaker_mean_diffs}")
    for df, keys, name in [
        (s1, ["outcome_id", "participant_id", "rate"], "Figure 1"),
        (s2, ["outcome_id", "participant_id", "rate"], "Figure 2"),
    ]:
        if df.duplicated(keys).any():
            raise ValueError(f"{name} contains more than one row per speaker/rate/outcome")

    s1.to_csv(out / "FIGURE1_SPEAKER_SUMMARIES_V8.csv", index=False, float_format="%.17g")
    s2.to_csv(out / "FIGURE2_SPEAKER_SUMMARIES_V8.csv", index=False, float_format="%.17g")
    predictions.to_csv(out / "FIGURE_MODEL_PREDICTIONS_V8.csv", index=False, float_format="%.17g")
    effects.to_csv(out / "FIGURE_EFFECT_ESTIMATES_V8.csv", index=False, float_format="%.17g")

    figure1(
        s1,
        predictions[predictions["figure"].eq("Figure 1")],
        effects,
        out / "Figure1_V8_PRIMARY.pdf",
        out / "Figure1_V8_PRIMARY.png",
    )
    figure2(
        s2,
        predictions[predictions["figure"].eq("Figure 2")],
        effects,
        out / "Figure2_V8_SECONDARY.pdf",
        out / "Figure2_V8_SECONDARY.png",
    )
    write_table1(effects, out / "Table1_V8.tex")

    summary = {
        "seed": args.seed,
        "random_jitter_used": False,
        "primary_sha256": sha256(args.primary_data.resolve()),
        "secondary_sha256": sha256(args.secondary_data.resolve()),
        "primary_rows": len(primary),
        "primary_speakers": int(primary["participant_id"].nunique()),
        "shared_six_rows": int(primary["sequence"].isin(SHARED_SEQUENCES).sum()),
        "secondary_parent_rows": len(secondary),
        "secondary_parent_speakers": int(secondary["participant_id"].nunique()),
        "secondary_canonical_co_me_center_10": secondary_co_me_center_10,
        "model_validation": model_validation,
        "maximum_absolute_coefficient_difference": max_beta_diff,
        "speaker_mean_maximum_absolute_differences": speaker_mean_diffs,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
            "patsy": patsy.__version__,
            "matplotlib": mpl.__version__,
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
