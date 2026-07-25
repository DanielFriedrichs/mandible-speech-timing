#!/usr/bin/env python3
"""Validate both corrected ArtiSynth grids and their provenance artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from artisynth_common_CURRENT import (
    BOOL_FIELDS,
    FLOAT_FIELDS,
    JAVA_REQUIRED_COLUMNS,
    MODES,
    OUTPUT_COLUMNS,
    PATH_FIELDS,
    SHA_FIELDS,
    SPEC_VERSION,
    SUCCESS,
    atomic_write_json,
    atomic_write_text,
    canonical_cell_parameters,
    close,
    expected_cells,
    feasibility,
    parse_bool,
    parse_float,
    parse_int,
    read_csv_rows,
    sha256_file,
    utc_now,
)

SCRIPT_PATH = Path(__file__).resolve()


class Issues:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, severity: str, mode: str, run_id: str, field: str, message: str) -> None:
        self.rows.append({
            "severity": severity,
            "mode": mode,
            "run_id": run_id,
            "field": field,
            "message": message,
        })

    @property
    def errors(self) -> int:
        return sum(1 for x in self.rows if x["severity"] == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for x in self.rows if x["severity"] == "WARNING")


def write_tsv(path: Path, rows: list[Mapping[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in columns})
        fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)


def one_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    if len(rows) != 1:
        raise ValueError(f"expected exactly one row in {path}; got {len(rows)}")
    return rows[0]


def check_artifact_hash(row: Mapping[str, str], path_field: str, hash_field: str, issues: Issues) -> None:
    mode, rid = row.get("mode", ""), row.get("run_id", "")
    path = Path(row.get(path_field, ""))
    expected = row.get(hash_field, "")
    if not path.is_file():
        issues.add("ERROR", mode, rid, path_field, f"artifact is missing: {path}")
        return
    observed = sha256_file(path)
    if observed != expected:
        issues.add("ERROR", mode, rid, hash_field, f"hash mismatch: stored={expected}, observed={observed}")


def compare_java_raw(row: Mapping[str, str], issues: Issues) -> None:
    mode, rid = row.get("mode", ""), row.get("run_id", "")
    path = Path(row.get("raw_java_csv_path", ""))
    if not path.is_file():
        return
    try:
        raw = one_row(path)
    except Exception as exc:
        issues.add("ERROR", mode, rid, "raw_java_csv_path", str(exc)); return
    missing = [c for c in JAVA_REQUIRED_COLUMNS if c not in raw]
    if missing:
        issues.add("ERROR", mode, rid, "raw_java_csv_path", f"missing Java fields: {missing}")
        return
    for field in JAVA_REQUIRED_COLUMNS:
        outer = row.get(field, "")
        inner = raw.get(field, "")
        if field in FLOAT_FIELDS:
            try:
                if not close(parse_float(outer, field), parse_float(inner, field), atol=1e-8, rtol=1e-8):
                    issues.add("ERROR", mode, rid, field, f"long/raw Java mismatch: {outer!r} vs {inner!r}")
            except Exception as exc:
                issues.add("ERROR", mode, rid, field, f"numeric comparison failed: {exc}")
        elif field in BOOL_FIELDS:
            try:
                if parse_bool(outer, field) != parse_bool(inner, field):
                    issues.add("ERROR", mode, rid, field, f"long/raw Java mismatch: {outer!r} vs {inner!r}")
            except Exception as exc:
                issues.add("ERROR", mode, rid, field, f"boolean comparison failed: {exc}")
        else:
            if str(outer) != str(inner):
                issues.add("ERROR", mode, rid, field, f"long/raw Java mismatch: {outer!r} vs {inner!r}")


def validate_mode(path: Path, mode: str, issues: Issues) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    try:
        rows = read_csv_rows(path)
    except Exception as exc:
        issues.add("ERROR", mode, "", "input", f"could not read {path}: {exc}")
        return [], {}
    if len(rows) != 342:
        issues.add("ERROR", mode, "", "row_count", f"expected exactly 342 rows; got {len(rows)}")
    if rows and list(rows[0].keys()) != OUTPUT_COLUMNS:
        issues.add("ERROR", mode, "", "schema", "column order/content differs from canonical OUTPUT_COLUMNS")
    expected = expected_cells(mode)
    expected_ids = [str(c["run_id"]) for c in expected]
    ids = [r.get("run_id", "") for r in rows]
    duplicates = [rid for rid, n in Counter(ids).items() if n > 1]
    if duplicates:
        issues.add("ERROR", mode, "", "duplicates", f"duplicate run IDs: {duplicates[:20]}")
    missing = sorted(set(expected_ids) - set(ids))
    extra = sorted(set(ids) - set(expected_ids))
    if missing:
        issues.add("ERROR", mode, "", "missing_cells", f"missing {len(missing)} canonical cells; first={missing[:10]}")
    if extra:
        issues.add("ERROR", mode, "", "extra_cells", f"unexpected {len(extra)} cells; first={extra[:10]}")
    lookup = {r.get("run_id", ""): r for r in rows}

    artifact_pairs = {
        "raw_java_csv_path": "raw_java_csv_sha256",
        "raw_stdout_path": "raw_stdout_sha256",
        "raw_stderr_path": "raw_stderr_sha256",
        "raw_run_log_path": "raw_run_log_sha256",
        "command_path": "command_sha256",
        "configuration_path": "configuration_sha256",
        "environment_path": "environment_sha256",
        "result_json_path": "result_json_sha256",
    }

    for cell in expected:
        rid = str(cell["run_id"])
        row = lookup.get(rid)
        if row is None:
            continue
        if row.get("mode") != mode:
            issues.add("ERROR", mode, rid, "mode", f"stored mode={row.get('mode')!r}")
        if row.get("spec_version") != SPEC_VERSION:
            issues.add("ERROR", mode, rid, "spec_version", f"unexpected {row.get('spec_version')!r}")
        try:
            canonical = canonical_cell_parameters(mode, float(cell["scale"]), float(cell["freq_hz"]), float(cell["target_amp_p2p_mm"]))
        except Exception as exc:
            issues.add("ERROR", mode, rid, "canonical_cell", str(exc)); continue
        for field, expected_value in canonical.items():
            if field not in row:
                issues.add("ERROR", mode, rid, field, "missing field"); continue
            if isinstance(expected_value, bool):
                try:
                    observed = parse_bool(row[field], field)
                    if observed != expected_value:
                        issues.add("ERROR", mode, rid, field, f"expected {expected_value}, got {observed}")
                except Exception as exc:
                    issues.add("ERROR", mode, rid, field, str(exc))
            elif isinstance(expected_value, (float, int)):
                try:
                    observed = parse_float(row[field], field)
                    if not close(observed, float(expected_value), atol=1e-8, rtol=1e-8):
                        issues.add("ERROR", mode, rid, field, f"expected {expected_value}, got {observed}")
                except Exception as exc:
                    issues.add("ERROR", mode, rid, field, str(exc))
            else:
                if str(row[field]) != str(expected_value):
                    issues.add("ERROR", mode, rid, field, f"expected {expected_value!r}, got {row[field]!r}")

        if row.get("return_status") != SUCCESS:
            issues.add("ERROR", mode, rid, "return_status", f"technical cell did not succeed: {row.get('return_status')!r}; {row.get('failure_reason','')}")
            continue
        try:
            if parse_bool(row["gravity_enabled"], "gravity_enabled"):
                issues.add("ERROR", mode, rid, "gravity_enabled", "must be false")
            if parse_bool(row["geometry_scaled"], "geometry_scaled"):
                issues.add("ERROR", mode, rid, "geometry_scaled", "must be false")
            for field in ("collision_api_success", "rest_lengths_reset", "hybrid_solves_disabled", "input_probes_removed", "output_probes_removed"):
                if not parse_bool(row[field], field):
                    issues.add("ERROR", mode, rid, field, "effective invariant is false")
            if parse_int(row["tmj_connectors_found"], "tmj_connectors_found") != 2 or parse_int(row["tmj_connectors_modified"], "tmj_connectors_modified") != 2:
                issues.add("ERROR", mode, rid, "tmj_connectors", "expected two found and two modified")
            n_force = parse_int(row["n_force_scaled"], "n_force_scaled")
            if mode == "fixed_force" and n_force != 0:
                issues.add("ERROR", mode, rid, "n_force_scaled", f"fixed_force requires 0, got {n_force}")
            if mode == "force_capacity_s2" and n_force <= 0:
                issues.add("ERROR", mode, rid, "n_force_scaled", f"force_capacity_s2 requires >0, got {n_force}")
            if parse_int(row["n_exciters"], "n_exciters") <= 0:
                issues.add("ERROR", mode, rid, "n_exciters", "must be >0")
            rmse = parse_float(row["tracking_rmse_mm"], "tracking_rmse_mm")
            peak = parse_float(row["peak_excitation"], "peak_excitation")
            gain = parse_float(row["amplitude_gain"], "amplitude_gain")
            flags = feasibility(rmse, peak, gain)
            expected_flags = {
                "rmse_ok": flags[0], "peak_excitation_ok": flags[1],
                "amplitude_gain_ok": flags[2], "is_feasible": flags[3],
                "failed_criteria": flags[4],
            }
            for field, expected_value in expected_flags.items():
                if isinstance(expected_value, bool):
                    if parse_bool(row[field], field) != expected_value:
                        issues.add("ERROR", mode, rid, field, f"stored/recomputed mismatch; expected {expected_value}")
                elif row[field] != expected_value:
                    issues.add("ERROR", mode, rid, field, f"stored/recomputed mismatch; expected {expected_value!r}")
        except Exception as exc:
            issues.add("ERROR", mode, rid, "row_validation", f"{type(exc).__name__}: {exc}")

        for field in SHA_FIELDS:
            value = row.get(field, "")
            if field == "grid_runner_sha256" and not value:
                issues.add("ERROR", mode, rid, field, "full grid row must record the grid runner hash")
            elif value and not re.fullmatch(r"[0-9a-f]{64}", value):
                issues.add("ERROR", mode, rid, field, f"not a SHA256 value: {value!r}")
        for path_field, hash_field in artifact_pairs.items():
            check_artifact_hash(row, path_field, hash_field, issues)
        compare_java_raw(row, issues)

        config_path = Path(row.get("configuration_path", ""))
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if config.get("spec_version") != SPEC_VERSION:
                    issues.add("ERROR", mode, rid, "configuration_path", "configuration spec_version mismatch")
                if config.get("cell", {}).get("run_id") != rid:
                    issues.add("ERROR", mode, rid, "configuration_path", "configuration run_id mismatch")
                for field, value in config.get("hashes", {}).items():
                    if field in row and row.get(field, "") != value:
                        issues.add("ERROR", mode, rid, field, "row/configuration identity hash mismatch")
            except Exception as exc:
                issues.add("ERROR", mode, rid, "configuration_path", f"unreadable JSON: {exc}")
    return rows, lookup


def validate_cross_mode(fixed: dict[str, dict[str, str]], force: dict[str, dict[str, str]], issues: Issues) -> None:
    shared_exact = [
        "spec_version", "scale", "freq_hz", "target_amp_p2p_mm", "mass_exp", "inertia_exp",
        "mass_multiplier", "inertia_multiplier", "duration_s", "settle_s", "play_time_s",
        "open_gap_mm", "gravity_state", "gravity_enabled", "gravity_x", "gravity_y", "gravity_z",
        "target_position_formula_id", "target_velocity_formula_id", "target_marker_name",
        "controller_architecture_id", "target_weight", "l2_regularization", "excitation_damping",
        "frame_damping", "rotary_damping", "max_step_s", "collision_setting",
        "collision_api_success", "collision_behaviors_disabled", "tmj_joint_setting",
        "tmj_connectors_found", "tmj_connectors_modified", "rest_lengths_reset",
        "n_rest_lengths_reset", "n_exciters", "hybrid_solves_disabled", "input_probes_removed",
        "output_probes_removed", "geometry_scaled", "model_units", "model_source_sha256",
        "compiled_model_sha256", "case_runner_sha256", "grid_runner_sha256", "common_module_sha256",
        "play_script_sha256", "artisynth_launcher_sha256", "java_executable_sha256",
        "python_executable_sha256", "base_jawdemo_class_sha256", "base_jawmodel_class_sha256",
        "code_bundle_sha256",
    ]
    for s in (0.80 + 0.05 * i for i in range(9)):
        for a in (1.0, 1.5):
            for f in (1.0 + 0.5 * i for i in range(19)):
                frid = canonical_cell_parameters("fixed_force", s, f, a)["run_id"]
                srid = canonical_cell_parameters("force_capacity_s2", s, f, a)["run_id"]
                left, right = fixed.get(frid), force.get(srid)
                if left is None or right is None:
                    continue
                for field in shared_exact:
                    lv, rv = left.get(field, ""), right.get(field, "")
                    if field in FLOAT_FIELDS:
                        try:
                            same = close(parse_float(lv, field), parse_float(rv, field), atol=1e-8, rtol=1e-8)
                        except Exception:
                            same = False
                    else:
                        same = lv == rv
                    if not same:
                        issues.add("ERROR", "cross_mode", f"s={s:.2f},f={f:.1f},A={a:.1f}", field,
                                   f"fixed={lv!r}; force_capacity_s2={rv!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed", type=Path, required=True)
    parser.add_argument("--force-scaled", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    issues = Issues()
    fixed_rows, fixed = validate_mode(args.fixed.expanduser().resolve(), "fixed_force", issues)
    force_rows, force = validate_mode(args.force_scaled.expanduser().resolve(), "force_capacity_s2", issues)
    validate_cross_mode(fixed, force, issues)

    out = args.out_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    status = "PASS" if issues.errors == 0 else "FAIL"
    report = {
        "spec_version": SPEC_VERSION,
        "validator_script": str(SCRIPT_PATH),
        "validator_sha256": sha256_file(SCRIPT_PATH),
        "generated_utc": utc_now(),
        "status": status,
        "error_count": issues.errors,
        "warning_count": issues.warnings,
        "fixed_path": str(args.fixed.expanduser().resolve()),
        "fixed_sha256": sha256_file(args.fixed.expanduser().resolve()),
        "fixed_rows": len(fixed_rows),
        "force_scaled_path": str(args.force_scaled.expanduser().resolve()),
        "force_scaled_sha256": sha256_file(args.force_scaled.expanduser().resolve()),
        "force_scaled_rows": len(force_rows),
        "issues": issues.rows,
    }
    atomic_write_json(out / "ARTISYNTH_GRID_VALIDATION_CURRENT.json", report)
    write_tsv(out / "ARTISYNTH_GRID_VALIDATION_ISSUES_CURRENT.tsv", issues.rows,
              ["severity", "mode", "run_id", "field", "message"])
    md = [
        "# ArtiSynth corrected-grid validation",
        "",
        f"**Status:** **{status}**",
        f"**Errors:** {issues.errors}",
        f"**Warnings:** {issues.warnings}",
        f"**Fixed-force rows:** {len(fixed_rows)} / 342",
        f"**Force-capacity rows:** {len(force_rows)} / 342",
        "",
    ]
    if issues.rows:
        md += ["## Issues", "", "| Severity | Mode | Run/cell | Field | Message |", "|---|---|---|---|---|"]
        for x in issues.rows[:500]:
            values = [x[k].replace("|", "\\|").replace("\n", " ") for k in ("severity", "mode", "run_id", "field", "message")]
            md.append("| " + " | ".join(values) + " |")
        if len(issues.rows) > 500:
            md.append(f"\nOnly the first 500 of {len(issues.rows)} issues are shown; see the TSV/JSON report.")
    else:
        md.append("All 684 corrected cells are unique, complete, technically successful, canonically configured, artifact-hash consistent, and cross-mode identical apart from force scaling and resulting dynamics.")
    atomic_write_text(out / "ARTISYNTH_GRID_VALIDATION_CURRENT.md", "\n".join(md) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "error_count", "warning_count", "fixed_rows", "force_scaled_rows")}, indent=2))
    return 0 if status == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
