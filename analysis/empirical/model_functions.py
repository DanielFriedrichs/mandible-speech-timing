#!/usr/bin/env python3
"""Generate the retained empirical outputs under the specified independence-GEE model.

Repeated-observation continuous models use Gaussian identity-link GEE with
participant clusters, an independence working correlation, and robust sandwich
covariance. Outputs are written to a user-specified directory and existing source files are not modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as ilm
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import scipy
from scipy.stats import norm
import statsmodels
import statsmodels.api as sm
import statsmodels.formula.api as smf

Z975 = float(norm.ppf(0.975))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def package_version(name: str) -> str:
    try:
        return ilm.version(name)
    except Exception:
        return "not-installed-or-unavailable"


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


def normalize_rate(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.lower()
        .replace({"habitual": "normal", "habit": "normal", "maximum": "fast", "maximal": "fast", "max": "fast"})
    )


def normalize_sequence(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()


def fit_gee(data: pd.DataFrame, formula: str, family: Any | None = None):
    fam = family if family is not None else sm.families.Gaussian(sm.families.links.Identity())
    model = smf.gee(
        formula=formula,
        groups="participant_id",
        data=data,
        cov_struct=sm.cov_struct.Independence(),
        family=fam,
    )
    return model.fit(cov_type="robust")


def coding_description(term: str) -> str:
    if term == "Intercept":
        return "Intercept at reference categories and centered height = 0"
    if term == "co_me_mean_mm_10":
        return "Per +10 mm bilateral mean Co--Me"
    if term == "height_cm_c":
        return "Per +1 cm height, centered as documented for the model input"
    if term == "age_years":
        return "Per +1 year age"
    if "sex" in term and "male" in term.lower():
        return "Male minus female"
    if "C(rate" in term and ":" not in term:
        return "Normal minus maximally fast; fast is the reference"
    if "C(sequence" in term:
        level = term.split("[T.")[-1].rstrip("]") if "[T." in term else "nonreference sequence"
        return f"{level} minus the model-specific sequence reference"
    if "C(task" in term:
        level = term.split("[T.")[-1].rstrip("]") if "[T." in term else "nonreference task"
        return f"{level} minus passage_baseline_noEMA"
    if "C(phase" in term and ":" not in term:
        level = term.split("[T.")[-1].split("]")[0] if "[T." in term else "nonreference phase"
        return f"{level} minus the model-specific phase reference"
    if "co_me_mean_mm_10:C(rate" in term or "C(rate" in term and ":co_me_mean_mm_10" in term:
        return "Difference in the Co--Me slope: normal minus fast"
    if "C(phase" in term and "co_me_mean_mm_10" in term and ":" in term:
        return "Difference in the Co--Me slope: second phase minus reference phase"
    if term == "ema_cycle_rate_hz":
        return "Per +1 Hz jaw-cycle rate"
    if term == "articulationrate":
        return "Per +1 syllable/s articulation rate"
    return term


def outcome_unit(outcome: str) -> str:
    units = {
        "log_speechrate": "log(syllables/s)",
        "log_articulationrate": "log(syllables/s)",
        "audio_mod_dom_hz": "Hz",
        "ema_cycle_rate_hz": "Hz",
        "jaw_cycle_rate_hz": "Hz",
        "jaw_open_amp_median_mm": "mm",
        "audio_rms": "waveform RMS units",
        "log_y": "log(outcome)",
    }
    return units.get(outcome, outcome)


def transformed_values(beta: float, lo: float, hi: float, log_outcome: bool) -> tuple[float | None, float | None, float | None, str]:
    if not log_outcome:
        return None, None, None, "not transformed"
    return (
        100.0 * (math.exp(beta) - 1.0),
        100.0 * (math.exp(lo) - 1.0),
        100.0 * (math.exp(hi) - 1.0),
        "percent change",
    )


def model_rows(
    *,
    result: Any,
    data: pd.DataFrame,
    output_name: str,
    analysis_family: str,
    model_id: str,
    outcome: str,
    formula: str,
    input_files: list[Path],
    original_root: Path,
    script_path: Path,
    status: str,
    log_outcome: bool,
    sequence_reference: str,
    rate_reference: str = "fast",
    subset: str = "all eligible observations",
    selection_rule: str = "model complete cases",
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ci = result.conf_int()
    versions = software_versions()
    input_rel = [str(p.relative_to(original_root)) if p.is_relative_to(original_root) else str(p) for p in input_files]
    input_hashes = [sha256(p) for p in input_files]
    script_hash = sha256(script_path)
    n_obs = int(result.nobs)
    n_spk = int(len(result.model.group_labels))
    rows: list[dict[str, Any]] = []
    for term in result.params.index:
        beta = float(result.params[term])
        se = float(result.bse[term])
        lo, hi = (float(ci.loc[term, 0]), float(ci.loc[term, 1]))
        tr, tr_lo, tr_hi, tr_unit = transformed_values(beta, lo, hi, log_outcome)
        row: dict[str, Any] = {
            "output_file": output_name,
            "record_type": "coefficient",
            "analysis_family": analysis_family,
            "model_id": model_id,
            "outcome": outcome,
            "outcome_unit": outcome_unit(outcome),
            "formula": formula,
            "term": term,
            "term_coding": coding_description(term),
            "beta": beta,
            "robust_se": se,
            "ci_lower": lo,
            "ci_upper": hi,
            "test_statistic": float(result.tvalues[term]),
            "test_statistic_type": "Wald z",
            "p_value": float(result.pvalues[term]),
            "transformed_effect": tr,
            "transformed_ci_lower": tr_lo,
            "transformed_ci_upper": tr_hi,
            "transformed_unit": tr_unit,
            "n_observations": n_obs,
            "n_speakers": n_spk,
            "family": "Gaussian",
            "link": "identity",
            "working_correlation": "independence",
            "covariance_estimator": "robust sandwich",
            "cluster": "participant_id",
            "rate_reference": rate_reference,
            "sequence_reference": sequence_reference,
            "subset": subset,
            "selection_rule": selection_rule,
            "software_versions": json.dumps(versions, sort_keys=True),
            "input_files": "; ".join(input_rel),
            "input_sha256": "; ".join(f"{r}={h}" for r, h in zip(input_rel, input_hashes)),
            "script_file": script_path.name,
            "script_sha256": script_hash,
            "status": status,
        }
        if extra:
            row.update(extra)
        rows.append(row)
    return rows


def slope_row(
    *,
    result: Any,
    base_term: str,
    interaction_term: str | None,
    stratum: str,
    outcome: str,
    model_id: str,
    formula: str,
    n_obs: int,
    n_spk: int,
    input_files: list[Path],
    original_root: Path,
    script_path: Path,
    sequence_reference: str,
    stratum_type: str,
    status: str = "VERIFIED_CANONICAL",
) -> dict[str, Any]:
    cov = result.cov_params()
    if interaction_term is None:
        beta = float(result.params[base_term])
        var = float(cov.loc[base_term, base_term])
    else:
        beta = float(result.params[base_term] + result.params[interaction_term])
        var = float(
            cov.loc[base_term, base_term]
            + cov.loc[interaction_term, interaction_term]
            + 2.0 * cov.loc[base_term, interaction_term]
        )
    se = math.sqrt(max(var, 0.0))
    z = beta / se if se > 0 else float("nan")
    lo = beta - Z975 * se
    hi = beta + Z975 * se
    p = 2.0 * norm.sf(abs(z)) if math.isfinite(z) else float("nan")
    is_log = outcome.startswith("log_") or outcome in {"jaw_duration_log", "jaw_peak_speed_log", "envelope_duration_log"}
    tr, tr_lo, tr_hi, tr_unit = transformed_values(beta, lo, hi, is_log)
    input_rel = [str(p.relative_to(original_root)) if p.is_relative_to(original_root) else str(p) for p in input_files]
    input_hashes = [sha256(p) for p in input_files]
    return {
        "record_type": "derived_stratum_slope",
        "analysis_family": f"{stratum_type}_interaction",
        "model_id": model_id,
        "outcome": outcome,
        "formula": formula,
        "stratum_type": stratum_type,
        "stratum": stratum,
        "term": f"Co--Me slope within {stratum}",
        "term_coding": "Per +10 mm bilateral mean Co--Me within the named stratum",
        "beta": beta,
        "robust_se": se,
        "ci_lower": lo,
        "ci_upper": hi,
        "test_statistic": z,
        "test_statistic_type": "Wald z",
        "p_value": p,
        "transformed_effect": tr,
        "transformed_ci_lower": tr_lo,
        "transformed_ci_upper": tr_hi,
        "transformed_unit": tr_unit,
        "n_observations": n_obs,
        "n_speakers": n_spk,
        "family": "Gaussian",
        "link": "identity",
        "working_correlation": "independence",
        "covariance_estimator": "robust sandwich",
        "cluster": "participant_id",
        "sequence_reference": sequence_reference,
        "software_versions": json.dumps(software_versions(), sort_keys=True),
        "input_files": "; ".join(input_rel),
        "input_sha256": "; ".join(f"{r}={h}" for r, h in zip(input_rel, input_hashes)),
        "script_file": script_path.name,
        "script_sha256": sha256(script_path),
        "status": status,
    }


def prep_speech(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d["rate"] = normalize_rate(d["rate"])
    d["sequence"] = normalize_sequence(d["sequence"])
    d["co_me_mean_mm_10"] = pd.to_numeric(d["co_me_mean_mm"], errors="coerce") / 10.0
    d["height_cm"] = pd.to_numeric(d["height_cm"], errors="coerce")
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean(skipna=True))
    d["log_speechrate"] = np.log(pd.to_numeric(d["speechrate"], errors="coerce"))
    d["log_articulationrate"] = np.log(pd.to_numeric(d["articulationrate"], errors="coerce"))
    d["age_years"] = pd.to_numeric(d["age_years"], errors="coerce")
    d["sex_norm"] = (
        d["sex"].astype(str).str.strip().str.lower().replace({"f": "female", "w": "female", "woman": "female", "m": "male", "man": "male"})
    )
    return d


def prep_mechanistic(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d["rate"] = normalize_rate(d["rate"])
    d["sequence"] = normalize_sequence(d["sequence"])
    d["co_me_mean_mm_10"] = pd.to_numeric(d["co_me_mean_mm"], errors="coerce") / 10.0
    if "height_cm" not in d:
        d["height_cm"] = pd.to_numeric(d["height_m"], errors="coerce") * 100.0
    else:
        d["height_cm"] = pd.to_numeric(d["height_cm"], errors="coerce")
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean(skipna=True))
    d["jaw_cycle_rate_hz"] = pd.to_numeric(d["ema_cycle_rate_hz"], errors="coerce")
    return d


def prep_read(read_path: Path, anatomy_path: Path) -> pd.DataFrame:
    d = pd.read_csv(read_path)
    d = d[d["status"].astype(str).str.strip().str.lower().eq("ok")].copy()
    anatomy = pd.read_csv(anatomy_path)
    co = (
        anatomy[anatomy["measure"].eq("co_me")]
        .groupby("participant_id", as_index=False)["value_mm"]
        .mean()
        .rename(columns={"value_mm": "co_me_mean_mm"})
    )
    ht = (
        anatomy[anatomy["measure"].eq("height")]
        .groupby("participant_id", as_index=False)["value_mm"]
        .mean()
        .rename(columns={"value_mm": "height_mm"})
    )
    d = d.merge(co, on="participant_id", how="inner", validate="m:1").merge(ht, on="participant_id", how="inner", validate="m:1")
    d["co_me_mean_mm_10"] = d["co_me_mean_mm"] / 10.0
    d["height_cm"] = d["height_mm"] / 10.0
    d["height_cm_c"] = d["height_cm"] - float(d["height_cm"].mean(skipna=True))
    return d


def write_csv(rows: Iterable[dict[str, Any]], path: Path) -> None:
    df = pd.DataFrame(list(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.17g")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    root = args.original_root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()

    speech_path = root / "analysis/primary/data/analysis_dataset_clean.csv"
    mech_path = root / "analysis/mechanistic/data/analysis_ready_trials.csv"
    phase_path = root / "analysis/phase/data/open_close_trial_metrics.csv"
    read_path = root / "analysis/read_speech/data/read_speech_envelope.csv"
    anatomy_path = root / "analysis/reliability/anatomy_measurements.csv"
    for p in [speech_path, mech_path, phase_path, read_path, anatomy_path]:
        if not p.exists():
            raise FileNotFoundError(p)

    speech = prep_speech(speech_path)
    mech = prep_mechanistic(mech_path)

    # 1) Primary anchors plus demographic and female-only sensitivity models.
    demo_rows: list[dict[str, Any]] = []
    for outcome in ["log_speechrate", "log_articulationrate"]:
        specs = [
            (
                "primary_independence_gee",
                speech,
                f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c",
                "all 28 primary speakers",
            ),
            (
                "sex_age_adjusted_independence_gee",
                speech,
                f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c + C(sex_norm, Treatment(reference='female')) + age_years",
                "all primary speakers with complete demographic covariates",
            ),
            (
                "female_only_independence_gee",
                speech[speech["sex_norm"].eq("female")].copy(),
                f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c",
                "female speakers only",
            ),
        ]
        for model_id, dat, formula, subset in specs:
            res = fit_gee(dat, formula)
            demo_rows.extend(
                model_rows(
                    result=res,
                    data=dat,
                    output_name="demographic_sensitivity.csv",
                    analysis_family="primary_and_demographic_sensitivity",
                    model_id=model_id,
                    outcome=outcome,
                    formula=formula,
                    input_files=[speech_path],
                    original_root=root,
                    script_path=script_path,
                    status="VERIFIED_CANONICAL",
                    log_outcome=True,
                    sequence_reference="bibibi",
                    subset=subset,
                )
            )
    write_csv(demo_rows, out / "demographic_sensitivity.csv")

    # 2) Strict acoustic sensitivity: retain speakers with >=50 usable acoustic trials.
    valid_counts = mech.loc[mech["audio_mod_dom_hz"].notna()].groupby("participant_id").size()
    eligible = sorted(valid_counts[valid_counts >= 50].index.astype(str).tolist())
    strict = mech[mech["participant_id"].isin(eligible)].copy()
    strict_formula = "audio_mod_dom_hz ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c"
    strict_res = fit_gee(strict, strict_formula)
    strict_rows = model_rows(
        result=strict_res,
        data=strict,
        output_name="strict_acoustic_sensitivity.csv",
        analysis_family="strict_acoustic_50trial_sensitivity",
        model_id="audio_modulation_minimum_50_valid_trials_independence_gee",
        outcome="audio_mod_dom_hz",
        formula=strict_formula,
        input_files=[mech_path],
        original_root=root,
        script_path=script_path,
        status="VERIFIED_CANONICAL",
        log_outcome=False,
        sequence_reference="bibibi",
        subset=f"{len(eligible)} speakers with >=50 nonmissing audio_mod_dom_hz values",
        selection_rule="participant retained when count(nonmissing audio_mod_dom_hz) >= 50; model complete cases thereafter",
        extra={"eligible_speakers": ";".join(eligible)},
    )
    write_csv(strict_rows, out / "strict_acoustic_sensitivity.csv")

    # 3) Co--Me x instructed-rate models and rate-specific slopes.
    interaction_rows: list[dict[str, Any]] = []
    slope_rows: list[dict[str, Any]] = []
    interaction_specs = [
        (speech, speech_path, "log_speechrate", False),
        (speech, speech_path, "log_articulationrate", False),
        (mech[mech["analysis_ok"].eq(True) & mech["ema_cycles_ok"].eq(True)].copy(), mech_path, "jaw_cycle_rate_hz", True),
        (mech[mech["analysis_ok"].eq(True) & mech["ema_cycles_ok"].eq(True)].copy(), mech_path, "jaw_open_amp_median_mm", True),
        (mech[mech["analysis_ok"].eq(True) & mech["ema_cycles_ok"].eq(True)].copy(), mech_path, "audio_mod_dom_hz", True),
        (mech[mech["analysis_ok"].eq(True) & mech["ema_cycles_ok"].eq(True)].copy(), mech_path, "audio_rms", True),
    ]
    for dat, input_path, outcome, mechanistic_gate in interaction_specs:
        formula = f"{outcome} ~ C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + co_me_mean_mm_10 + height_cm_c + co_me_mean_mm_10:C(rate, Treatment(reference='fast'))"
        res = fit_gee(dat, formula)
        interaction_rows.extend(
            model_rows(
                result=res,
                data=dat,
                output_name="interaction_models.csv",
                analysis_family="co_me_by_rate_interaction",
                model_id=f"{outcome}_by_rate_independence_gee",
                outcome=outcome,
                formula=formula,
                input_files=[input_path],
                original_root=root,
                script_path=script_path,
                status="VERIFIED_CANONICAL",
                log_outcome=outcome.startswith("log_"),
                sequence_reference="bibibi",
                subset="analysis_ok and ema_cycles_ok" if mechanistic_gate else "all primary timing observations",
                extra={"interaction_type": "Co--Me x instructed rate"},
            )
        )
        interaction_term = [t for t in res.params.index if "co_me_mean_mm_10:C(rate" in t][0]
        nobs = int(res.nobs)
        nspk = int(len(res.model.group_labels))
        slope_rows.append(
            slope_row(
                result=res,
                base_term="co_me_mean_mm_10",
                interaction_term=None,
                stratum="fast",
                outcome=outcome,
                model_id=f"{outcome}_by_rate_independence_gee",
                formula=formula,
                n_obs=nobs,
                n_spk=nspk,
                input_files=[input_path],
                original_root=root,
                script_path=script_path,
                sequence_reference="bibibi",
                stratum_type="instructed_rate",
            )
        )
        slope_rows.append(
            slope_row(
                result=res,
                base_term="co_me_mean_mm_10",
                interaction_term=interaction_term,
                stratum="normal",
                outcome=outcome,
                model_id=f"{outcome}_by_rate_independence_gee",
                formula=formula,
                n_obs=nobs,
                n_spk=nspk,
                input_files=[input_path],
                original_root=root,
                script_path=script_path,
                sequence_reference="bibibi",
                stratum_type="instructed_rate",
            )
        )
    write_csv(interaction_rows, out / "interaction_models.csv")
    write_csv(slope_rows, out / "interaction_slopes_by_rate.csv")

    # 4) Canonical independence phase interactions (paired long format; both phases required).
    phase = pd.read_csv(phase_path)
    phase["rate"] = normalize_rate(phase["rate"])
    phase["sequence"] = normalize_sequence(phase["sequence"])
    phase_specs = [
        ("jaw_duration", "jaw_open_dur_med_s", "jaw_close_dur_med_s", "open", "close"),
        ("jaw_peak_speed", "jaw_open_peak_speed_med_mm_s", "jaw_close_peak_speed_med_mm_s", "open", "close"),
        ("envelope_duration", "env_rise_dur_med_s", "env_fall_dur_med_s", "rise", "fall"),
    ]
    phase_rows: list[dict[str, Any]] = []
    for model_id_base, col_a, col_b, phase_a, phase_b in phase_specs:
        wide = phase.dropna(subset=[col_a, col_b, "participant_id", "rate", "sequence", "co_me_mean_mm_10", "height_cm_c"]).copy()
        long = pd.concat(
            [
                wide[["participant_id", "rate", "sequence", "co_me_mean_mm_10", "height_cm_c"]].assign(phase=phase_a, y=wide[col_a].to_numpy()),
                wide[["participant_id", "rate", "sequence", "co_me_mean_mm_10", "height_cm_c"]].assign(phase=phase_b, y=wide[col_b].to_numpy()),
            ],
            ignore_index=True,
        )
        long = long[long["y"] > 0].copy()
        long["log_y"] = np.log(long["y"])
        formula = (
            f"log_y ~ C(phase, Treatment(reference='{phase_a}')) * co_me_mean_mm_10 + "
            "C(rate, Treatment(reference='fast')) + C(sequence, Treatment(reference='bibibi')) + height_cm_c"
        )
        res = fit_gee(long, formula)
        rows = model_rows(
            result=res,
            data=long,
            output_name="phase_interaction_models.csv",
            analysis_family="phase_by_co_me_interaction",
            model_id=f"{model_id_base}_phase_interaction_independence_gee",
            outcome=f"{model_id_base}_log",
            formula=formula,
            input_files=[phase_path],
            original_root=root,
            script_path=script_path,
            status="VERIFIED_CANONICAL_MODEL_STAGE",
            log_outcome=True,
            sequence_reference="bibibi",
            subset="trials with both paired phase outcomes present",
            extra={"interaction_type": "phase x Co--Me", "phase_reference": phase_a, "paired_wide_observations": len(wide)},
        )
        phase_rows.extend(rows)
        interaction_term = [t for t in res.params.index if "C(phase" in t and "co_me_mean_mm_10" in t and ":" in t][0]
        for phase_name, int_term in [(phase_a, None), (phase_b, interaction_term)]:
            row = slope_row(
                result=res,
                base_term="co_me_mean_mm_10",
                interaction_term=int_term,
                stratum=phase_name,
                outcome=f"{model_id_base}_log",
                model_id=f"{model_id_base}_phase_interaction_independence_gee",
                formula=formula,
                n_obs=int(res.nobs),
                n_spk=int(len(res.model.group_labels)),
                input_files=[phase_path],
                original_root=root,
                script_path=script_path,
                sequence_reference="bibibi",
                stratum_type="phase",
                status="VERIFIED_CANONICAL_MODEL_STAGE",
            )
            row.update({"phase_reference": phase_a, "paired_wide_observations": len(wide)})
            phase_rows.append(row)
    write_csv(phase_rows, out / "phase_interaction_models.csv")

    # 5) Trial-level coupling models, all coefficients and model-specific complete-case Ns.
    speech_merge = speech.copy()
    speech_merge["index"] = pd.to_numeric(speech_merge["trial"], errors="coerce").astype("Int64")
    ema_merge = mech[mech["analysis_ok"].eq(True)].copy()
    ema_merge["index"] = pd.to_numeric(ema_merge["index"], errors="coerce").astype("Int64")
    key = ["participant_id", "rate", "sequence", "index"]
    merged = speech_merge.merge(ema_merge, on=key, how="inner", suffixes=("_speech", "_ema"), validate="m:1")
    for c in ["co_me_mean_mm", "co_me_mean_mm_10", "height_cm", "height_cm_c", "speechrate", "articulationrate"]:
        if c not in merged.columns:
            for suffix in ["_speech", "_ema"]:
                if f"{c}{suffix}" in merged.columns:
                    merged[c] = merged[f"{c}{suffix}"]
                    break
    for c in ["ema_cycle_rate_hz", "audio_mod_dom_hz"]:
        if c not in merged.columns and f"{c}_ema" in merged.columns:
            merged[c] = merged[f"{c}_ema"]
    merged = merged[(pd.to_numeric(merged["speechrate"], errors="coerce") > 0) & (pd.to_numeric(merged["articulationrate"], errors="coerce") > 0)].copy()
    merged["log_articulationrate"] = np.log(pd.to_numeric(merged["articulationrate"], errors="coerce"))
    coupling_rows: list[dict[str, Any]] = []
    for rate in ["normal", "fast"]:
        dat = merged[merged["rate"].eq(rate)].copy()
        seq_ref = "bibibi" if rate == "normal" else "kutapi"
        specs = [
            ("jaw_from_anatomy", "ema_cycle_rate_hz", f"ema_cycle_rate_hz ~ co_me_mean_mm_10 + height_cm_c + C(sequence, Treatment(reference='{seq_ref}'))", False),
            ("articulation_from_jaw_and_anatomy", "log_articulationrate", f"log_articulationrate ~ ema_cycle_rate_hz + co_me_mean_mm_10 + height_cm_c + C(sequence, Treatment(reference='{seq_ref}'))", True),
            ("audio_from_articulation_jaw_and_anatomy", "audio_mod_dom_hz", f"audio_mod_dom_hz ~ articulationrate + ema_cycle_rate_hz + co_me_mean_mm_10 + height_cm_c + C(sequence, Treatment(reference='{seq_ref}'))", False),
        ]
        for model_short, outcome, formula, is_log in specs:
            res = fit_gee(dat, formula)
            coupling_rows.extend(
                model_rows(
                    result=res,
                    data=dat,
                    output_name="coupling_trial_level_models.csv",
                    analysis_family="trial_level_coupling",
                    model_id=f"{rate}_{model_short}_independence_gee",
                    outcome=outcome,
                    formula=formula,
                    input_files=[speech_path, mech_path],
                    original_root=root,
                    script_path=script_path,
                    status="VERIFIED_CANONICAL",
                    log_outcome=is_log,
                    sequence_reference=seq_ref,
                    rate_reference="not applicable; model stratified by rate",
                    subset=f"{rate} trials in the merged timing/EMA/audio table; analysis_ok required upstream",
                    selection_rule="inner merge on participant_id, rate, sequence, index; positive speech/articulation rates; formula-specific complete cases",
                    extra={"rate_stratum": rate, "merged_rows_before_model_complete_cases": len(dat), "merged_total_rows": len(merged), "merged_total_speakers": int(merged["participant_id"].nunique())},
                )
            )
    write_csv(coupling_rows, out / "coupling_trial_level_models.csv")

    # 6) Read-speech model under the same independence-GEE policy.
    read = prep_read(read_path, anatomy_path)
    read_formula = "audio_mod_dom_hz ~ C(task, Treatment(reference='passage_baseline_noEMA')) + co_me_mean_mm_10 + height_cm_c"
    read_res = fit_gee(read, read_formula)
    read_rows = model_rows(
        result=read_res,
        data=read,
        output_name="read_speech_effects.csv",
        analysis_family="read_speech",
        model_id="read_speech_independence_gee",
        outcome="audio_mod_dom_hz",
        formula=read_formula,
        input_files=[read_path, anatomy_path],
        original_root=root,
        script_path=script_path,
        status="VERIFIED_CANONICAL",
        log_outcome=False,
        sequence_reference="not applicable",
        rate_reference="not applicable",
        subset="status == ok and complete anthropometry",
        selection_rule="read-speech rows with status 'ok'; inner merge to finalized Co--Me and height",
        extra={"task_reference": "passage_baseline_noEMA"},
    )
    write_csv(read_rows, out / "read_speech_effects.csv")

    # Run log and output hashes.
    output_files = [
        "demographic_sensitivity.csv",
        "strict_acoustic_sensitivity.csv",
        "interaction_models.csv",
        "interaction_slopes_by_rate.csv",
        "phase_interaction_models.csv",
        "coupling_trial_level_models.csv",
        "read_speech_effects.csv",
    ]
    finished = datetime.now(timezone.utc)
    log_lines = [
        "# Canonical empirical model run log",
        "",
        f"- Start (UTC): {started.isoformat()}",
        f"- End (UTC): {finished.isoformat()}",
        f"- Command: `{' '.join(sys.argv)}`",
        f"- Working directory: `{os.getcwd()}`",
        f"- Script: `{script_path}`",
        f"- Script SHA256: `{sha256(script_path)}`",
        f"- Policy: participant-clustered GEE; independence working correlation; robust sandwich covariance; Gaussian identity link for continuous outcomes.",
        f"- Wald intervals: two-sided 95% normal intervals using z={Z975:.15f}.",
        f"- Environment: `{json.dumps(software_versions(), sort_keys=True)}`",
        "",
        "## Canonical inputs",
    ]
    for p in [speech_path, mech_path, phase_path, read_path, anatomy_path]:
        log_lines.append(f"- `{p.relative_to(root)}` — SHA256 `{sha256(p)}`")
    log_lines += ["", "## Generated outputs"]
    for name in output_files:
        p = out / name
        log_lines.append(f"- `{name}` — {p.stat().st_size} bytes — SHA256 `{sha256(p)}`")
    log_lines += [
        "",
        "## Numerical reproducibility statement",
        "The CSV files record full-precision values produced in this environment. Independent reproductions should agree to approximately 1e-10 absolute for coefficients and standard errors when the model, input, and software versions are otherwise identical. A different working correlation or model class represents a different specification rather than floating-point variation.",
    ]
    (out / "model_run_log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(output_files)} canonical CSV files and run log to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
