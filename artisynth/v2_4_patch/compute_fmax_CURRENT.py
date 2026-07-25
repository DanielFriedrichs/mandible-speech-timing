#!/usr/bin/env python3
"""Compute canonical feasibility and strict-prefix fmax independently.

There is no two-failure, gap-recovery, highest-feasible-anywhere, smoothing, or
monotonicity option. Stored cell flags are ignored and recomputed from metrics.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from artisynth_common_CURRENT import (
    AMPLITUDES,
    FREQUENCIES,
    GAIN_MAX,
    GAIN_MIN,
    MODES,
    PEAK_EXCITATION_MAX,
    RMSE_MAX_MM,
    SCALES,
    SPEC_VERSION,
    SUCCESS,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    canonical_cell_parameters,
    feasibility,
    parse_float,
    read_csv_rows,
    sha256_file,
    utc_now,
)

SCRIPT_PATH = Path(__file__).resolve()

CELL_COLUMNS = [
    "run_id", "mode", "scale", "freq_hz", "target_amp_p2p_mm",
    "tracking_rmse_mm", "peak_excitation", "amplitude_gain",
    "rmse_ok_recomputed", "peak_excitation_ok_recomputed",
    "amplitude_gain_ok_recomputed", "cell_feasible_recomputed",
    "failed_criteria_recomputed", "prefix_eligible",
    "series_first_failed_frequency_hz", "series_first_failed_criterion",
    "series_fmax_hz", "feasible_after_first_failure",
    "source_long_table", "source_long_table_sha256", "fmax_script_sha256",
    "spec_version",
]

SUMMARY_COLUMNS = [
    "mode", "scale", "target_amp_p2p_mm", "n_tested", "n_cell_feasible",
    "n_prefix_feasible", "fmax_hz", "first_failed_frequency_hz",
    "first_failed_criterion", "all_frequencies_feasible",
    "n_feasible_after_first_failure", "locally_nonmonotonic_feasibility",
    "rmse_max_mm", "peak_excitation_max", "gain_min", "gain_max",
    "prefix_rule_id", "source_long_table", "source_long_table_sha256",
    "fmax_script_sha256", "spec_version",
]


def read_mode(path: Path, expected_mode: str) -> list[dict[str, str]]:
    rows = read_csv_rows(path)
    if len(rows) != 342:
        raise ValueError(f"{expected_mode}: expected 342 rows, got {len(rows)}")
    for row in rows:
        if row.get("mode") != expected_mode:
            raise ValueError(f"{expected_mode}: row has mode={row.get('mode')!r}")
        if row.get("return_status") != SUCCESS:
            raise ValueError(f"{expected_mode}: technical failure in {row.get('run_id')}: {row.get('return_status')}")
    return rows


def compute(rows_with_source: list[tuple[dict[str, str], Path]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, float, float], list[tuple[dict[str, str], Path]]] = defaultdict(list)
    for row, source in rows_with_source:
        key = (row["mode"], float(row["scale"]), float(row["target_amp_p2p_mm"]))
        groups[key].append((row, source))
    expected_keys = {(m, float(s), float(a)) for m in MODES for s in SCALES for a in AMPLITUDES}
    if set(groups) != expected_keys:
        missing = sorted(expected_keys - set(groups))
        extra = sorted(set(groups) - expected_keys)
        raise ValueError(f"series-key mismatch; missing={missing[:10]}, extra={extra[:10]}")

    script_hash = sha256_file(SCRIPT_PATH)
    cell_out: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for mode in MODES:
        for scale_dec in SCALES:
            for amp_dec in AMPLITUDES:
                key = (mode, float(scale_dec), float(amp_dec))
                entries = sorted(groups[key], key=lambda x: float(x[0]["freq_hz"]))
                freqs = [float(row["freq_hz"]) for row, _ in entries]
                expected_freqs = [float(x) for x in FREQUENCIES]
                if freqs != expected_freqs:
                    raise ValueError(f"{key}: frequency grid/order mismatch: {freqs}")
                annotations: list[dict[str, Any]] = []
                first_fail_freq: float | None = None
                first_fail_criterion = ""
                prefix_open = True
                fmax: float | None = None
                n_feasible = 0
                n_prefix = 0
                n_after = 0
                for row, source in entries:
                    rmse = parse_float(row["tracking_rmse_mm"], "tracking_rmse_mm")
                    peak = parse_float(row["peak_excitation"], "peak_excitation")
                    gain = parse_float(row["amplitude_gain"], "amplitude_gain")
                    rmse_ok, peak_ok, gain_ok, feasible_cell, failed = feasibility(rmse, peak, gain)
                    if feasible_cell:
                        n_feasible += 1
                    prefix_eligible = prefix_open and feasible_cell
                    if prefix_eligible:
                        fmax = float(row["freq_hz"])
                        n_prefix += 1
                    elif prefix_open:
                        prefix_open = False
                        first_fail_freq = float(row["freq_hz"])
                        first_fail_criterion = failed
                    elif feasible_cell:
                        n_after += 1
                    annotations.append({
                        "run_id": row["run_id"], "mode": mode, "scale": float(scale_dec),
                        "freq_hz": float(row["freq_hz"]), "target_amp_p2p_mm": float(amp_dec),
                        "tracking_rmse_mm": rmse, "peak_excitation": peak, "amplitude_gain": gain,
                        "rmse_ok_recomputed": rmse_ok,
                        "peak_excitation_ok_recomputed": peak_ok,
                        "amplitude_gain_ok_recomputed": gain_ok,
                        "cell_feasible_recomputed": feasible_cell,
                        "failed_criteria_recomputed": failed,
                        "prefix_eligible": prefix_eligible,
                        "source_long_table": str(source),
                        "source_long_table_sha256": sha256_file(source),
                        "fmax_script_sha256": script_hash,
                        "spec_version": SPEC_VERSION,
                    })
                all_feasible = first_fail_freq is None
                for annotation in annotations:
                    annotation["series_first_failed_frequency_hz"] = first_fail_freq
                    annotation["series_first_failed_criterion"] = first_fail_criterion
                    annotation["series_fmax_hz"] = fmax
                    annotation["feasible_after_first_failure"] = (
                        (first_fail_freq is not None) and
                        annotation["freq_hz"] > first_fail_freq and
                        annotation["cell_feasible_recomputed"]
                    )
                    cell_out.append(annotation)
                source = entries[0][1]
                summaries.append({
                    "mode": mode, "scale": float(scale_dec),
                    "target_amp_p2p_mm": float(amp_dec), "n_tested": 19,
                    "n_cell_feasible": n_feasible, "n_prefix_feasible": n_prefix,
                    "fmax_hz": fmax, "first_failed_frequency_hz": first_fail_freq,
                    "first_failed_criterion": first_fail_criterion,
                    "all_frequencies_feasible": all_feasible,
                    "n_feasible_after_first_failure": n_after,
                    "locally_nonmonotonic_feasibility": n_after > 0,
                    "rmse_max_mm": RMSE_MAX_MM,
                    "peak_excitation_max": PEAK_EXCITATION_MAX,
                    "gain_min": GAIN_MIN, "gain_max": GAIN_MAX,
                    "prefix_rule_id": "STRICT_ALL_LOWER_AND_SELF_FEASIBLE_V1",
                    "source_long_table": str(source),
                    "source_long_table_sha256": sha256_file(source),
                    "fmax_script_sha256": script_hash,
                    "spec_version": SPEC_VERSION,
                })
    if len(cell_out) != 684 or len(summaries) != 36:
        raise AssertionError(f"internal output count error: cells={len(cell_out)}, summaries={len(summaries)}")
    return cell_out, summaries


def self_test() -> None:
    # Inclusive boundaries must pass.
    assert feasibility(0.5, 0.95, 0.7)[3]
    assert feasibility(0.5, 0.95, 1.3)[3]
    assert not feasibility(math.nextafter(0.5, math.inf), 0.95, 1.0)[3]
    assert not feasibility(0.5, math.nextafter(0.95, math.inf), 1.0)[3]
    assert not feasibility(0.5, 0.95, math.nextafter(0.7, -math.inf))[3]
    assert not feasibility(0.5, 0.95, math.nextafter(1.3, math.inf))[3]
    # A single failure at 2 Hz permanently closes the prefix despite 2.5-Hz recovery.
    feasibility_by_freq = {1.0: True, 1.5: True, 2.0: False, 2.5: True}
    prefix_open, fmax = True, None
    for freq in sorted(feasibility_by_freq):
        ok = feasibility_by_freq[freq]
        if prefix_open and ok:
            fmax = freq
        elif prefix_open:
            prefix_open = False
    assert fmax == 1.5
    print("compute_fmax_CURRENT.py self-test: PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed", type=Path)
    parser.add_argument("--force-scaled", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        if not any((args.fixed, args.force_scaled, args.out_dir)):
            return 0
    if not (args.fixed and args.force_scaled and args.out_dir):
        parser.error("--fixed, --force-scaled, and --out-dir are required unless only --self-test is used")
    try:
        fixed = args.fixed.expanduser().resolve()
        force = args.force_scaled.expanduser().resolve()
        rows = [(r, fixed) for r in read_mode(fixed, "fixed_force")]
        rows += [(r, force) for r in read_mode(force, "force_capacity_s2")]
        cells, summaries = compute(rows)
        out = args.out_dir.expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(out / "artisynth_cells_feasibility_CURRENT.csv", cells, CELL_COLUMNS)
        atomic_write_csv(out / "artisynth_fmax_CURRENT.csv", summaries, SUMMARY_COLUMNS)
        metadata = {
            "spec_version": SPEC_VERSION,
            "generated_utc": utc_now(),
            "script": str(SCRIPT_PATH), "script_sha256": sha256_file(SCRIPT_PATH),
            "fixed": str(fixed), "fixed_sha256": sha256_file(fixed),
            "force_scaled": str(force), "force_scaled_sha256": sha256_file(force),
            "n_cell_rows": len(cells), "n_series_rows": len(summaries),
            "thresholds": {"rmse_max_mm": RMSE_MAX_MM, "peak_excitation_max": PEAK_EXCITATION_MAX,
                           "gain_min": GAIN_MIN, "gain_max": GAIN_MAX},
            "prefix_rule": "A frequency is eligible only when it and every lower tested frequency are feasible.",
        }
        atomic_write_json(out / "ARTISYNTH_FMAX_PROVENANCE_CURRENT.json", metadata)
        md = [
            "# Corrected ArtiSynth strict-prefix fmax",
            "",
            "This output recomputes all cell criteria from the corrected long-form metrics.",
            "No stored feasibility flag, two-failure rule, gap recovery, or monotonicity assumption is used.",
            "",
            f"- Cell annotations: {len(cells)}",
            f"- Series summaries: {len(summaries)}",
            f"- Inclusive thresholds: RMSE <= {RMSE_MAX_MM} mm; peak excitation <= {PEAK_EXCITATION_MAX}; gain in [{GAIN_MIN}, {GAIN_MAX}]",
        ]
        atomic_write_text(out / "ARTISYNTH_FMAX_README_CURRENT.md", "\n".join(md) + "\n")
        print(json.dumps({"cells": len(cells), "series": len(summaries), "out_dir": str(out)}, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
