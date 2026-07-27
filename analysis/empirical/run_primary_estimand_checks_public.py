#!/usr/bin/env python3
"""Run the required mandibular-length primary-estimand checks.

This script locates the exact canonical 8,123-row timing dataset by SHA256,
then fits participant-clustered Gaussian identity-link GEE models with an
independence working correlation and robust sandwich covariance.

It produces:
  * comparison.csv
  * all_coefficients.csv
  * run_log.md
  * summary.md

The script is read-only with respect to the research project. It never
modifies the input dataset or existing analysis outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as ilm
import json
import math
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy.stats import norm
import statsmodels
import statsmodels.api as sm
import statsmodels.formula.api as smf

CANONICAL_DATA_SHA256 = "4492e389789b7126c2b9f15588b682871f374cf917aa6006134c3090bffcf9ed"
CANONICAL_BASENAME = "analysis_dataset_clean.csv"
Z975 = float(norm.ppf(0.975))


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    outcome: str
    data_subset: str
    formula: str
    sequence_reference: str
    include_height: bool


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package_version(name: str) -> str:
    try:
        return ilm.version(name)
    except Exception:
        return "unavailable"


def software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
        "patsy": package_version("patsy"),
    }


def find_canonical_dataset(project_root: Path, explicit_data: Path | None) -> tuple[Path, list[Path]]:
    if explicit_data is not None:
        p = explicit_data.expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Explicit data file does not exist: {p}")
        digest = sha256(p)
        if digest != CANONICAL_DATA_SHA256:
            raise RuntimeError(
                "Explicit data file has the wrong SHA256.\n"
                f"Expected: {CANONICAL_DATA_SHA256}\n"
                f"Observed: {digest}\n"
                f"File: {p}"
            )
        return p, [p]

    candidates: list[Path] = []
    for p in project_root.rglob(CANONICAL_BASENAME):
        if not p.is_file():
            continue
        try:
            if sha256(p) == CANONICAL_DATA_SHA256:
                candidates.append(p.resolve())
        except OSError:
            continue

    if not candidates:
        raise FileNotFoundError(
            f"No {CANONICAL_BASENAME} with canonical SHA256 {CANONICAL_DATA_SHA256} "
            f"was found under {project_root}."
        )

    candidates = sorted(set(candidates), key=lambda p: (len(p.parts), str(p)))
    return candidates[0], candidates


def normalize_rate(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "habitual": "normal",
            "habit": "normal",
            "maximum": "fast",
            "maximal": "fast",
            "max": "fast",
        })
    )


def normalize_sequence(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def prepare_data(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    required = {
        "participant_id",
        "rate",
        "sequence",
        "co_me_mean_mm",
        "height_cm",
        "speechrate",
        "articulationrate",
    }
    missing = sorted(required.difference(d.columns))
    if missing:
        raise KeyError(f"Canonical dataset is missing required columns: {missing}")

    d = d.copy()
    d["participant_id"] = d["participant_id"].astype(str)
    d["rate"] = normalize_rate(d["rate"])
    d["sequence"] = normalize_sequence(d["sequence"])
    d["co_me_mean_mm"] = pd.to_numeric(d["co_me_mean_mm"], errors="coerce")
    d["co_me_mean_mm_10"] = d["co_me_mean_mm"] / 10.0
    d["height_cm"] = pd.to_numeric(d["height_cm"], errors="coerce")
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean(skipna=True))
    d["speechrate"] = pd.to_numeric(d["speechrate"], errors="coerce")
    d["articulationrate"] = pd.to_numeric(d["articulationrate"], errors="coerce")
    d.loc[d["speechrate"] <= 0, "speechrate"] = np.nan
    d.loc[d["articulationrate"] <= 0, "articulationrate"] = np.nan
    d["log_speechrate"] = np.log(d["speechrate"])
    d["log_articulationrate"] = np.log(d["articulationrate"])
    return d


def fit_gee(data: pd.DataFrame, formula: str):
    model = smf.gee(
        formula=formula,
        groups="participant_id",
        data=data,
        cov_struct=sm.cov_struct.Independence(),
        family=sm.families.Gaussian(sm.families.links.Identity()),
        missing="drop",
    )
    return model.fit(cov_type="robust")


def transform_log_effect(beta: float, lo: float, hi: float) -> tuple[float, float, float]:
    return (
        100.0 * (math.exp(beta) - 1.0),
        100.0 * (math.exp(lo) - 1.0),
        100.0 * (math.exp(hi) - 1.0),
    )


def make_model_specs(shared_sequences: list[str]) -> list[ModelSpec]:
    if "bibibi" not in shared_sequences:
        shared_reference = "kutapi" if "kutapi" in shared_sequences else shared_sequences[0]
    else:
        shared_reference = "bibibi"

    specs: list[ModelSpec] = []
    for outcome in ("log_speechrate", "log_articulationrate"):
        for include_height in (False, True):
            suffix = "height_adjusted" if include_height else "no_height"
            height_term = " + height_cm_c" if include_height else ""
            specs.append(
                ModelSpec(
                    model_id=f"full_{suffix}_{outcome}",
                    outcome=outcome,
                    data_subset="all_eligible_trials",
                    formula=(
                        f"{outcome} ~ C(rate, Treatment(reference='fast')) + "
                        f"C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10{height_term}"
                    ),
                    sequence_reference="bibibi",
                    include_height=include_height,
                )
            )
            specs.append(
                ModelSpec(
                    model_id=f"shared_six_{suffix}_{outcome}",
                    outcome=outcome,
                    data_subset="six_sequences_shared_by_rate_conditions",
                    formula=(
                        f"{outcome} ~ C(rate, Treatment(reference='fast')) + "
                        f"C(sequence, Treatment(reference='{shared_reference}')) + co_me_mean_mm_10{height_term}"
                    ),
                    sequence_reference=shared_reference,
                    include_height=include_height,
                )
            )
    return specs


def coefficient_rows(result: Any, spec: ModelSpec, data_sha: str, script_sha: str) -> list[dict[str, Any]]:
    ci = result.conf_int()
    n_obs = int(result.nobs)
    n_speakers = int(len(result.model.group_labels))
    rows: list[dict[str, Any]] = []
    for term in result.params.index:
        beta = float(result.params[term])
        se = float(result.bse[term])
        lo = float(ci.loc[term, 0])
        hi = float(ci.loc[term, 1])
        effect, effect_lo, effect_hi = transform_log_effect(beta, lo, hi)
        rows.append(
            {
                "model_id": spec.model_id,
                "data_subset": spec.data_subset,
                "outcome": spec.outcome,
                "include_height": spec.include_height,
                "formula": spec.formula,
                "sequence_reference": spec.sequence_reference,
                "term": term,
                "beta": beta,
                "robust_se": se,
                "ci_lower_beta": lo,
                "ci_upper_beta": hi,
                "wald_z": float(result.tvalues[term]),
                "p_value": float(result.pvalues[term]),
                "transformed_effect_percent": effect,
                "transformed_ci_lower_percent": effect_lo,
                "transformed_ci_upper_percent": effect_hi,
                "n_observations": n_obs,
                "n_speakers": n_speakers,
                "working_correlation": "independence",
                "covariance_estimator": "robust sandwich",
                "family": "Gaussian",
                "link": "identity",
                "cluster": "participant_id",
                "data_sha256": data_sha,
                "script_sha256": script_sha,
            }
        )
    return rows


def compact_comparison(all_rows: pd.DataFrame, co_me_sd_mm: float) -> pd.DataFrame:
    d = all_rows[all_rows["term"].eq("co_me_mean_mm_10")].copy()
    d["effect_per_sample_sd_percent"] = 100.0 * (
        np.exp(d["beta"] * (co_me_sd_mm / 10.0)) - 1.0
    )
    d["effect_per_sample_sd_ci_lower_percent"] = 100.0 * (
        np.exp(d["ci_lower_beta"] * (co_me_sd_mm / 10.0)) - 1.0
    )
    d["effect_per_sample_sd_ci_upper_percent"] = 100.0 * (
        np.exp(d["ci_upper_beta"] * (co_me_sd_mm / 10.0)) - 1.0
    )
    keep = [
        "model_id",
        "data_subset",
        "outcome",
        "include_height",
        "formula",
        "sequence_reference",
        "beta",
        "robust_se",
        "ci_lower_beta",
        "ci_upper_beta",
        "wald_z",
        "p_value",
        "transformed_effect_percent",
        "transformed_ci_lower_percent",
        "transformed_ci_upper_percent",
        "effect_per_sample_sd_percent",
        "effect_per_sample_sd_ci_lower_percent",
        "effect_per_sample_sd_ci_upper_percent",
        "n_observations",
        "n_speakers",
        "working_correlation",
        "covariance_estimator",
        "data_sha256",
        "script_sha256",
    ]
    return d[keep].sort_values(["outcome", "data_subset", "include_height"], kind="stable")


def fmt_effect(row: pd.Series) -> str:
    return (
        f"{row['transformed_effect_percent']:+.3f}% "
        f"[{row['transformed_ci_lower_percent']:+.3f}%, "
        f"{row['transformed_ci_upper_percent']:+.3f}%], "
        f"P={row['p_value']:.6g}, N={int(row['n_observations'])}/{int(row['n_speakers'])}"
    )


def write_decision_summary(
    compact: pd.DataFrame,
    output_path: Path,
    chosen_data: Path,
    co_me_mean: float,
    co_me_sd: float,
    co_me_range: tuple[float, float],
    shared_sequences: list[str],
) -> None:
    lines: list[str] = []
    lines.append("# Primary estimand comparison — decision summary")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "This report compares the association of bilateral mean Co–Me with the two primary "
        "DDK outcomes before and after adjustment for height. It also repeats both models in "
        "the six sequences shared by the habitual and fast conditions. The models use the "
        "specified participant-clustered independence-GEE specification with robust "
        "sandwich covariance."
    )
    lines.append("")
    lines.append("## Canonical input")
    lines.append("")
    lines.append(f"- File: `{chosen_data}`")
    lines.append(f"- SHA256: `{CANONICAL_DATA_SHA256}`")
    lines.append(f"- Co–Me mean: {co_me_mean:.6f} mm")
    lines.append(f"- Co–Me sample SD: {co_me_sd:.6f} mm")
    lines.append(f"- Co–Me range: {co_me_range[0]:.6f}–{co_me_range[1]:.6f} mm")
    lines.append(f"- Shared sequences: {', '.join(shared_sequences)}")
    lines.append("")
    lines.append("## Full dataset")
    lines.append("")
    for outcome in ("log_speechrate", "log_articulationrate"):
        lines.append(f"### {outcome}")
        lines.append("")
        subset = compact[(compact["outcome"] == outcome) & (compact["data_subset"] == "all_eligible_trials")]
        for _, row in subset.sort_values("include_height").iterrows():
            label = "Height-adjusted" if bool(row["include_height"]) else "No height"
            lines.append(f"- **{label}:** {fmt_effect(row)}")
        no_h = subset[~subset["include_height"]].iloc[0]
        h = subset[subset["include_height"]].iloc[0]
        delta = float(h["transformed_effect_percent"] - no_h["transformed_effect_percent"])
        ratio = abs(float(h["beta"])) / abs(float(no_h["beta"])) if float(no_h["beta"]) != 0 else float("inf")
        lines.append(
            f"- Adjustment change: {delta:+.3f} percentage points in the transformed +10-mm effect; "
            f"|beta_adjusted| / |beta_unadjusted| = {ratio:.3f}."
        )
        lines.append("")
    lines.append("## Shared-six-sequence sensitivity")
    lines.append("")
    for outcome in ("log_speechrate", "log_articulationrate"):
        lines.append(f"### {outcome}")
        lines.append("")
        subset = compact[(compact["outcome"] == outcome) & (compact["data_subset"] == "six_sequences_shared_by_rate_conditions")]
        for _, row in subset.sort_values("include_height").iterrows():
            label = "Height-adjusted" if bool(row["include_height"]) else "No height"
            lines.append(f"- **{label}:** {fmt_effect(row)}")
        lines.append("")
    lines.append("## Interpretation guardrails")
    lines.append("")
    lines.append(
        "1. The no-height model estimates the association with absolute measured Co–Me under "
        "the specified task controls. The height-adjusted model estimates a contrast between "
        "speakers who differ in Co–Me at the same modeled stature. These are different estimands."
    )
    lines.append(
        "2. A larger adjusted coefficient can reflect suppression or relative-proportion structure; "
        "it does not by itself establish that height adjustment removes confounding or isolates a "
        "jaw-specific causal effect."
    )
    lines.append(
        "3. These normal-reference robust-GEE intervals are intended for the estimand decision. "
        "They do not replace the existing CR2, cluster-bootstrap, wild-cluster, equal-weight, and "
        "leave-one-speaker-out checks. If the no-height model becomes the primary specification, "
        "the same small-cluster procedures should be rerun for that specification."
    )
    lines.append(
        "4. The shared-six analysis is a focused design sensitivity. It should not be described as "
        "independent replication."
    )
    lines.append("")
    lines.append("## Interpretation selected for the manuscript")
    lines.append("")
    lines.append(
        "The manuscript uses external mandibular length conditional on modeled stature as the primary "
        "construct and reports the absolute-length model as the principal estimand comparison."
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runlog(
    output_path: Path,
    project_root: Path,
    chosen_data: Path,
    all_matches: list[Path],
    compact: pd.DataFrame,
    started: datetime,
    ended: datetime,
    script_path: Path,
) -> None:
    versions = software_versions()
    lines = [
        "# Primary estimand checks — run log",
        "",
        f"- Start UTC: {started.isoformat()}",
        f"- End UTC: {ended.isoformat()}",
        f"- Project root: `{project_root}`",
        f"- Selected canonical data: `{chosen_data}`",
        f"- Canonical data SHA256: `{sha256(chosen_data)}`",
        f"- Script: `{script_path}`",
        f"- Script SHA256: `{sha256(script_path)}`",
        f"- Software: `{json.dumps(versions, sort_keys=True)}`",
        "- Estimator: participant-clustered Gaussian identity-link GEE; independence working correlation; robust sandwich covariance.",
        "- Intervals: two-sided 95% normal-reference Wald intervals.",
        "",
        "## All matching canonical copies found",
        "",
    ]
    for p in all_matches:
        lines.append(f"- `{p}`")
    lines.extend([
        "",
        "## Output summary",
        "",
        f"- Compact Co–Me rows: {len(compact)}",
        f"- Full data models: {int((compact['data_subset'] == 'all_eligible_trials').sum())}",
        f"- Shared-six models: {int((compact['data_subset'] == 'six_sequences_shared_by_rate_conditions').sum())}",
        "",
        "## Scope limitation",
        "",
        "This run addresses the required primary-estimand and shared-sequence comparisons only. It does not alter any existing output and does not rerun CR2, bootstrap, wild-cluster, equal-weight, or LOOSO procedures.",
    ])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True, help="SpeechRateAndMandible project root")
    parser.add_argument("--data-file", type=Path, default=None, help="Optional explicit canonical analysis_dataset_clean.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="New output directory")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    project_root = args.project_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not project_root.is_dir():
        raise NotADirectoryError(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    chosen_data, all_matches = find_canonical_dataset(project_root, args.data_file)
    data_sha = sha256(chosen_data)
    script_path = Path(__file__).resolve()
    script_sha = sha256(script_path)
    data = prepare_data(chosen_data)

    rate_sequences = {
        rate: set(g["sequence"].dropna().astype(str))
        for rate, g in data.groupby("rate", observed=True)
    }
    if not {"normal", "fast"}.issubset(rate_sequences):
        raise RuntimeError(f"Expected normal and fast rates; observed {sorted(rate_sequences)}")
    shared_sequences = sorted(rate_sequences["normal"].intersection(rate_sequences["fast"]))
    if len(shared_sequences) != 6:
        raise RuntimeError(
            f"Expected six sequences shared by normal and fast conditions, observed {len(shared_sequences)}: {shared_sequences}"
        )
    shared = data[data["sequence"].isin(shared_sequences)].copy()

    model_data = {
        "all_eligible_trials": data,
        "six_sequences_shared_by_rate_conditions": shared,
    }
    rows: list[dict[str, Any]] = []
    for spec in make_model_specs(shared_sequences):
        dat = model_data[spec.data_subset]
        result = fit_gee(dat, spec.formula)
        rows.extend(coefficient_rows(result, spec, data_sha, script_sha))

    all_df = pd.DataFrame(rows)
    all_path = output_dir / "all_coefficients.csv"
    all_df.to_csv(all_path, index=False, float_format="%.17g")

    speaker_values = data[["participant_id", "co_me_mean_mm"]].drop_duplicates("participant_id")
    co_mean = float(speaker_values["co_me_mean_mm"].mean())
    co_sd = float(speaker_values["co_me_mean_mm"].std(ddof=1))
    co_range = (float(speaker_values["co_me_mean_mm"].min()), float(speaker_values["co_me_mean_mm"].max()))

    compact = compact_comparison(all_df, co_sd)
    compact_path = output_dir / "comparison.csv"
    compact.to_csv(compact_path, index=False, float_format="%.17g")

    summary_path = output_dir / "summary.md"
    write_decision_summary(compact, summary_path, chosen_data, co_mean, co_sd, co_range, shared_sequences)

    ended = datetime.now(timezone.utc)
    runlog_path = output_dir / "run_log.md"
    write_runlog(runlog_path, project_root, chosen_data, all_matches, compact, started, ended, script_path)

    print("PRIMARY ESTIMAND CHECKS: PASS")
    print(f"Canonical data: {chosen_data}")
    print(f"Data SHA256: {data_sha}")
    print(f"Shared sequences: {', '.join(shared_sequences)}")
    print(f"Output directory: {output_dir}")
    for p in [compact_path, all_path, summary_path, runlog_path]:
        print(f"Created: {p}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
