#!/usr/bin/env python3
"""Table-only validation of the canonical corrected ArtiSynth Phase C outputs.

This script does not launch ArtiSynth. It independently checks the two validated
342-cell long tables, recomputes all feasibility flags from the prespecified
thresholds, derives strict-prefix endpoints, and compares fixed-force and s^2
force-capacity endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RMSE_MAX = 0.5
PEAK_EXC_MAX = 0.95
GAIN_MIN = 0.7
GAIN_MAX = 1.3
EXPECTED_SCALES = [round(0.80 + 0.05 * i, 2) for i in range(9)]
EXPECTED_FREQS = [round(1.0 + 0.5 * i, 1) for i in range(19)]
EXPECTED_AMPS = [1.0, 1.5]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().map({"true": True, "false": False}).fillna(False)


def validate_table(path: Path, expected_mode: str) -> tuple[pd.DataFrame, list[str]]:
    d = pd.read_csv(path)
    errors: list[str] = []
    required = {
        "mode", "scale", "freq_hz", "target_amp_p2p_mm", "return_status", "return_code",
        "tracking_rmse_mm", "peak_excitation", "amplitude_gain", "rmse_ok",
        "peak_excitation_ok", "amplitude_gain_ok", "is_feasible", "mass_exp",
        "inertia_exp", "force_exp", "effective_force_multiplier", "n_force_scaled",
        "gravity_state", "gravity_enabled", "gravity_x", "gravity_y", "gravity_z",
        "geometry_scaled", "target_position_formula_id", "target_velocity_formula_id",
    }
    missing = sorted(required - set(d.columns))
    if missing:
        errors.append(f"{path.name}: missing columns {missing}")
        return d, errors
    if len(d) != 342:
        errors.append(f"{path.name}: expected 342 rows, found {len(d)}")
    if set(d["mode"].astype(str)) != {expected_mode}:
        errors.append(f"{path.name}: mode mismatch {sorted(set(d['mode'].astype(str)))}")
    keys = ["scale", "freq_hz", "target_amp_p2p_mm"]
    if d.duplicated(keys).any():
        errors.append(f"{path.name}: duplicate scale-frequency-amplitude cells")
    scales = sorted(round(float(x), 2) for x in d["scale"].unique())
    freqs = sorted(round(float(x), 1) for x in d["freq_hz"].unique())
    amps = sorted(round(float(x), 1) for x in d["target_amp_p2p_mm"].unique())
    if scales != EXPECTED_SCALES:
        errors.append(f"{path.name}: scale grid mismatch: {scales}")
    if freqs != EXPECTED_FREQS:
        errors.append(f"{path.name}: frequency grid mismatch: {freqs}")
    if amps != EXPECTED_AMPS:
        errors.append(f"{path.name}: amplitude grid mismatch: {amps}")
    if set(d["return_status"].astype(str)) != {"success"} or not (d["return_code"] == 0).all():
        errors.append(f"{path.name}: technical failures present")

    invariant_checks = {
        "mass_exp": 3,
        "inertia_exp": 5,
        "gravity_state": "disabled",
        "gravity_enabled": False,
        "gravity_x": 0,
        "gravity_y": 0,
        "gravity_z": 0,
        "geometry_scaled": False,
        "target_position_formula_id": "P2P_ONE_SIDED_SIN_ACTIVE_V1",
        "target_velocity_formula_id": "P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1",
    }
    for col, value in invariant_checks.items():
        if pd.api.types.is_bool_dtype(d[col]) or isinstance(value, bool):
            ok = as_bool(d[col]).eq(bool(value)).all()
        elif isinstance(value, (int, float)):
            ok = np.isclose(pd.to_numeric(d[col]), float(value), rtol=0, atol=1e-12).all()
        else:
            ok = d[col].astype(str).eq(str(value)).all()
        if not ok:
            errors.append(f"{path.name}: invariant failed for {col}={value}")

    if expected_mode == "fixed_force":
        if not ((d["force_exp"] == 0) & np.isclose(d["effective_force_multiplier"], 1.0) & (d["n_force_scaled"] == 0)).all():
            errors.append(f"{path.name}: fixed-force scaling invariant failed")
    else:
        if not ((d["force_exp"] == 2) & np.isclose(d["effective_force_multiplier"], d["scale"] ** 2) & (d["n_force_scaled"] == 24)).all():
            errors.append(f"{path.name}: s^2 force-capacity invariant failed")

    d = d.copy()
    d["independent_rmse_ok"] = d["tracking_rmse_mm"] <= RMSE_MAX
    d["independent_peak_excitation_ok"] = d["peak_excitation"] <= PEAK_EXC_MAX
    d["independent_amplitude_gain_ok"] = d["amplitude_gain"].between(GAIN_MIN, GAIN_MAX, inclusive="both")
    d["independent_is_feasible"] = d[
        ["independent_rmse_ok", "independent_peak_excitation_ok", "independent_amplitude_gain_ok"]
    ].all(axis=1)
    for stored, independent in [
        ("rmse_ok", "independent_rmse_ok"),
        ("peak_excitation_ok", "independent_peak_excitation_ok"),
        ("amplitude_gain_ok", "independent_amplitude_gain_ok"),
        ("is_feasible", "independent_is_feasible"),
    ]:
        if not np.array_equal(as_bool(d[stored]).to_numpy(), d[independent].to_numpy(dtype=bool)):
            errors.append(f"{path.name}: stored {stored} differs from independent recomputation")
    return d, errors


def strict_prefix(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (mode, scale, amp), g in d.groupby(["mode", "scale", "target_amp_p2p_mm"], sort=True):
        g = g.sort_values("freq_hz")
        feasible = g["independent_is_feasible"].to_numpy(dtype=bool)
        freqs = g["freq_hz"].to_numpy(dtype=float)
        first_bad = np.flatnonzero(~feasible)
        if len(first_bad) == 0:
            endpoint = float(freqs[-1])
            display = f">={endpoint:g}"
            first_fail = np.nan
            prefix_count = len(freqs)
            all_feasible = True
        else:
            i = int(first_bad[0])
            endpoint = np.nan if i == 0 else float(freqs[i - 1])
            display = "<1" if i == 0 else f"{endpoint:g}"
            first_fail = float(freqs[i])
            prefix_count = i
            all_feasible = False
        rows.append({
            "mode": mode,
            "scale": float(scale),
            "target_amp_p2p_mm": float(amp),
            "n_tested": int(len(g)),
            "n_feasible": int(feasible.sum()),
            "strict_prefix_count": int(prefix_count),
            "strict_prefix_endpoint_hz": endpoint,
            "endpoint_display": display,
            "all_frequencies_feasible": all_feasible,
            "first_failed_frequency_hz": first_fail,
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixed", required=True, type=Path)
    ap.add_argument("--force", required=True, type=Path)
    ap.add_argument("--canonical-comparison", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    expected_hashes = {'fixed': '510f2e249fa2dcf62e8437bce17aefa425f999cbbed5efdbfcb2b4d42af8ebad', 'force': '59f84b7d5f8f1b7e7bc4455af6bacee121e278e1c82eb5d56cc9729424b58d02', 'canonical': '44cd194dca713b4e8fbebecaf8f77d72687452f5e8f6bccadcdbc783df645508'}
    for label, path in [('fixed', args.fixed), ('force', args.force), ('canonical', args.canonical_comparison)]:
        if not path.is_file():
            raise FileNotFoundError(path)
        got = sha256(path)
        if got != expected_hashes[label]:
            raise ValueError(f'Wrong {label} hash: {got}; expected {expected_hashes[label]}')
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    fixed, errors_f = validate_table(args.fixed, "fixed_force")
    force, errors_s = validate_table(args.force, "force_capacity_s2")
    errors = errors_f + errors_s
    all_d = pd.concat([fixed, force], ignore_index=True)
    endpoints = strict_prefix(all_d)

    comparison = endpoints.pivot(index=["scale", "target_amp_p2p_mm"], columns="mode", values="strict_prefix_endpoint_hz").reset_index()
    comparison["force_minus_fixed_hz"] = comparison["force_capacity_s2"] - comparison["fixed_force"]
    comparison = comparison.sort_values(["target_amp_p2p_mm", "scale"]).reset_index(drop=True)

    canonical = pd.read_csv(args.canonical_comparison).sort_values(["target_amp_p2p_mm", "scale"]).reset_index(drop=True)
    if len(canonical) != 18:
        errors.append(f"canonical comparison: expected 18 rows, found {len(canonical)}")
    else:
        key_ok = np.allclose(comparison["scale"], canonical["scale"], atol=1e-12, rtol=0) and np.allclose(comparison["target_amp_p2p_mm"], canonical["target_amp_p2p_mm"], atol=1e-12, rtol=0)
        if not key_ok:
            errors.append("canonical comparison keys do not match independent derivation")
        if not np.allclose(comparison["fixed_force"], canonical["fixed_force_fmax_hz"], atol=0, rtol=0):
            errors.append("fixed-force endpoints differ from canonical comparison")
        if not np.allclose(comparison["force_capacity_s2"], canonical["force_capacity_s2_fmax_hz"], atol=0, rtol=0):
            errors.append("force-capacity endpoints differ from canonical comparison")
        if not np.allclose(comparison["force_minus_fixed_hz"], canonical["force_minus_fixed_hz"], atol=0, rtol=0):
            errors.append("endpoint differences differ from canonical comparison")

    endpoints.to_csv(out / "PHASE_C_ENDPOINTS_RECOMPUTED_V13.csv", index=False, float_format="%.12g")
    comparison.to_csv(out / "PHASE_C_MODE_COMPARISON_RECOMPUTED_V13.csv", index=False, float_format="%.12g")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "fixed_file": str(args.fixed),
        "fixed_sha256": sha256(args.fixed),
        "force_file": str(args.force),
        "force_sha256": sha256(args.force),
        "canonical_comparison_file": str(args.canonical_comparison),
        "canonical_comparison_sha256": sha256(args.canonical_comparison),
        "rows_fixed": int(len(fixed)),
        "rows_force_capacity_s2": int(len(force)),
        "unique_cells_fixed": int(fixed[["scale", "freq_hz", "target_amp_p2p_mm"]].drop_duplicates().shape[0]),
        "unique_cells_force_capacity_s2": int(force[["scale", "freq_hz", "target_amp_p2p_mm"]].drop_duplicates().shape[0]),
        "technically_successful_cells": int(((all_d["return_status"] == "success") & (all_d["return_code"] == 0)).sum()),
        "independently_feasible_cells": int(all_d["independent_is_feasible"].sum()),
        "total_cells": int(len(all_d)),
        "series": int(len(endpoints)),
        "series_feasible_through_10_hz": int(endpoints["all_frequencies_feasible"].sum()),
        "endpoint_comparisons": int(len(comparison)),
        "endpoint_differences_zero": int(np.isclose(comparison["force_minus_fixed_hz"], 0, atol=0, rtol=0).sum()),
        "maximum_tracking_rmse_mm": float(all_d["tracking_rmse_mm"].max()),
        "maximum_peak_excitation": float(all_d["peak_excitation"].max()),
        "minimum_amplitude_gain": float(all_d["amplitude_gain"].min()),
        "maximum_amplitude_gain": float(all_d["amplitude_gain"].max()),
        "reporting_constraint": ">=10 Hz within the tested grid; not an observed physical maximum",
    }
    (out / "PHASE_C_TABLE_VALIDATION_V13.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
