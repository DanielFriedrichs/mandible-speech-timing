#!/usr/bin/env python3
"""Run one canonical corrected ArtiSynth cell with complete provenance.

The script never overwrites a prior cell. --fresh requires an absent cell
directory. --resume skips only a technically successful cell whose canonical
configuration, code/runtime hashes, raw Java row, and artifact hashes all match;
matching failed attempts are archived and rerun, while any mismatch is refused.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from artisynth_common_CURRENT import (
    BOOL_FIELDS,
    COLLISION_SETTING,
    CONTROLLER_ARCHITECTURE_ID,
    FLOAT_FIELDS,
    JAVA_REQUIRED_COLUMNS,
    MODEL_CLASS,
    OUTPUT_COLUMNS,
    PATH_FIELDS,
    POSITION_FORMULA_ID,
    SHA_FIELDS,
    SPEC_VERSION,
    SUCCESS,
    TMJ_SETTING,
    VELOCITY_FORMULA_ID,
    aggregate_hash,
    archive_existing,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    canonical_cell_parameters,
    canonical_json_bytes,
    close,
    command_text,
    empty_output_row,
    environment_snapshot,
    feasibility,
    parse_bool,
    parse_float,
    parse_int,
    read_csv_rows,
    sha256_bytes,
    sha256_file,
    sha256_tree,
    utc_now,
)

SCRIPT_PATH = Path(__file__).resolve()
COMMON_PATH = SCRIPT_PATH.with_name("artisynth_common_CURRENT.py")


class CaseError(RuntimeError):
    def __init__(self, status: str, message: str, return_code: int | None = None):
        super().__init__(message)
        self.status = status
        self.return_code = return_code


def require_file(path: Path, label: str, *, executable: bool = False) -> Path:
    p = path.expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"{label} is not a file: {p}")
    if executable and not os.access(p, os.X_OK):
        raise ValueError(f"{label} is not executable: {p}")
    return p


def require_dir(path: Path, label: str) -> Path:
    p = path.expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"{label} is not a directory: {p}")
    return p


def class_file_hash(base: Path, relative: str) -> str:
    return sha256_file(base / relative)


def create_identity(args: argparse.Namespace, cell: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    artisynth_bin = require_file(args.artisynth_bin, "ArtiSynth launcher", executable=True)
    classes_dir = require_dir(args.classes_dir, "isolated corrected classes directory")
    base_classes_dir = require_dir(args.base_classes_dir, "ArtiSynth models base classes directory")
    source_java = require_file(args.source_java, "corrected Java source")
    play_script = require_file(args.play_script, "headless play script")
    java_home = require_dir(args.java_home, "Java home")
    java_executable = require_file(java_home / "bin" / "java", "selected Java executable", executable=True)
    arch_executable = None
    if args.arch_mode == "x86_64":
        arch_executable = require_file(Path("/usr/bin/arch"), "macOS architecture launcher", executable=True)

    expected_class = classes_dir / "artisynth/models/dynjaw/MandibleScalingInverseDDK_CURRENT.class"
    if not expected_class.is_file():
        raise ValueError(f"compiled corrected model class is missing: {expected_class}")

    hashes = {
        "model_source_sha256": sha256_file(source_java),
        "compiled_model_sha256": sha256_tree(classes_dir, suffixes=(".class",)),
        "case_runner_sha256": sha256_file(SCRIPT_PATH),
        "grid_runner_sha256": args.grid_runner_sha256 or "",
        "common_module_sha256": sha256_file(COMMON_PATH),
        "play_script_sha256": sha256_file(play_script),
        "artisynth_launcher_sha256": sha256_file(artisynth_bin),
        "java_executable_sha256": sha256_file(java_executable),
        "arch_executable_sha256": sha256_file(arch_executable) if arch_executable else "native",
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "base_jawdemo_class_sha256": class_file_hash(
            base_classes_dir, "artisynth/models/dynjaw/JawDemo.class"),
        "base_jawmodel_class_sha256": class_file_hash(
            base_classes_dir, "artisynth/models/dynjaw/JawModel.class"),
    }
    required_nonempty = [
        "model_source_sha256", "compiled_model_sha256", "case_runner_sha256",
        "common_module_sha256", "play_script_sha256", "artisynth_launcher_sha256",
        "java_executable_sha256", "python_executable_sha256",
        "base_jawdemo_class_sha256", "base_jawmodel_class_sha256",
    ]
    for field in required_nonempty:
        if len(hashes[field]) != 64:
            raise ValueError(f"could not establish required hash {field}")
    if args.arch_mode == "x86_64" and len(hashes["arch_executable_sha256"]) != 64:
        raise ValueError("could not establish required hash arch_executable_sha256")
    hashes["code_bundle_sha256"] = aggregate_hash(hashes)

    config = {
        "spec_version": SPEC_VERSION,
        "model_class": args.model_class,
        "cell": dict(cell),
        "paths": {
            "artisynth_bin": str(artisynth_bin),
            "classes_dir": str(classes_dir),
            "base_classes_dir": str(base_classes_dir),
            "source_java": str(source_java),
            "play_script": str(play_script),
            "java_home": str(java_home),
            "java_executable": str(java_executable),
            "arch_executable": str(arch_executable) if arch_executable else "",
            "python_executable": str(Path(sys.executable).resolve()),
        },
        "runtime": {
            "arch_mode": args.arch_mode,
            "timeout_s": float(args.timeout_s),
        },
        "hashes": hashes,
    }
    return config, hashes


def build_command(config: Mapping[str, Any], raw_java_csv: Path) -> tuple[list[str], dict[str, str]]:
    cell = config["cell"]
    paths = config["paths"]
    classpath = os.pathsep.join([paths["classes_dir"], paths["base_classes_dir"]])
    cmd = [
        paths["artisynth_bin"],
        "-noGui",
        "-cp", classpath,
        "-model", config["model_class"],
        "[",
        "--mode", str(cell["mode"]),
        "--scale", format(float(cell["scale"]), ".17g"),
        "--freq_hz", format(float(cell["freq_hz"]), ".17g"),
        "--amp_p2p_mm", format(float(cell["target_amp_p2p_mm"]), ".17g"),
        "--mass_exp", format(float(cell["mass_exp"]), ".17g"),
        "--inertia_exp", format(float(cell["inertia_exp"]), ".17g"),
        "--force_exp", format(float(cell["force_exp"]), ".17g"),
        "--force_multiplier", format(float(cell["effective_force_multiplier"]), ".17g"),
        "--duration_s", format(float(cell["duration_s"]), ".17g"),
        "--settle_s", format(float(cell["settle_s"]), ".17g"),
        "--target_weight", format(float(cell["target_weight"]), ".17g"),
        "--l2_regularization", format(float(cell["l2_regularization"]), ".17g"),
        "--excitation_damping", format(float(cell["excitation_damping"]), ".17g"),
        "--frame_damping", format(float(cell["frame_damping"]), ".17g"),
        "--rotary_damping", format(float(cell["rotary_damping"]), ".17g"),
        "--max_step_s", format(float(cell["max_step_s"]), ".17g"),
        "--open_gap_mm", format(float(cell["open_gap_mm"]), ".17g"),
        "--gravity", str(cell["gravity_state"]),
        "--out", str(raw_java_csv),
        "--verbose",
        "]",
        "-script", paths["play_script"],
    ]
    env = os.environ.copy()
    env["JAVA_HOME"] = paths["java_home"]
    env["PATH"] = str(Path(paths["java_home"]) / "bin") + os.pathsep + env.get("PATH", "")
    if config["runtime"]["arch_mode"] == "x86_64":
        cmd = [paths["arch_executable"], "-x86_64"] + cmd
    return cmd, env


def normalize_java_row(raw: Mapping[str, str], cell: Mapping[str, Any]) -> dict[str, Any]:
    missing = [c for c in JAVA_REQUIRED_COLUMNS if c not in raw]
    if missing:
        raise CaseError("malformed_output", f"Java CSV missing fields: {missing}")
    if any(c is None for c in raw):
        raise CaseError("malformed_output", "Java CSV contains a malformed extra-column record")

    row: dict[str, Any] = {}
    string_fields = set(JAVA_REQUIRED_COLUMNS) - FLOAT_FIELDS - BOOL_FIELDS - {
        "n_force_scaled", "collision_behaviors_disabled", "tmj_connectors_found",
        "tmj_connectors_modified", "n_rest_lengths_reset", "n_exciters", "n_samples",
    }
    for field in JAVA_REQUIRED_COLUMNS:
        value = raw[field]
        if field in BOOL_FIELDS:
            row[field] = parse_bool(value, field)
        elif field in {
            "n_force_scaled", "collision_behaviors_disabled", "tmj_connectors_found",
            "tmj_connectors_modified", "n_rest_lengths_reset", "n_exciters", "n_samples",
        }:
            row[field] = parse_int(value, field)
        elif field in FLOAT_FIELDS:
            row[field] = parse_float(value, field)
        elif field in string_fields:
            row[field] = str(value)
        else:
            row[field] = str(value)

    expected_strings = {
        "spec_version": SPEC_VERSION,
        "mode": cell["mode"],
        "gravity_state": "disabled",
        "target_position_formula_id": POSITION_FORMULA_ID,
        "target_velocity_formula_id": VELOCITY_FORMULA_ID,
        "controller_architecture_id": CONTROLLER_ARCHITECTURE_ID,
        "collision_setting": COLLISION_SETTING,
        "tmj_joint_setting": TMJ_SETTING,
    }
    for field, expected in expected_strings.items():
        if row[field] != expected:
            raise CaseError("malformed_output", f"{field}: expected {expected!r}, got {row[field]!r}")

    expected_numbers = {
        key: value for key, value in cell.items()
        if key in {
            "scale", "freq_hz", "target_amp_p2p_mm", "mass_exp", "inertia_exp",
            "mass_multiplier", "inertia_multiplier", "force_exp",
            "effective_force_multiplier", "duration_s", "settle_s", "open_gap_mm",
            "gravity_x", "gravity_y", "gravity_z", "target_weight",
            "l2_regularization", "excitation_damping", "frame_damping",
            "rotary_damping", "max_step_s",
        }
    }
    for field, expected in expected_numbers.items():
        if not close(row[field], expected, atol=1e-8, rtol=1e-8):
            raise CaseError("malformed_output", f"{field}: expected {expected}, got {row[field]}")

    if row["gravity_enabled"]:
        raise CaseError("malformed_output", "gravity_enabled must be false")
    if row["geometry_scaled"]:
        raise CaseError("malformed_output", "geometry_scaled must be false")
    if not row["collision_api_success"]:
        raise CaseError("malformed_output", "collision disabling was not verified")
    if row["tmj_connectors_found"] != 2 or row["tmj_connectors_modified"] != 2:
        raise CaseError("malformed_output", "two TMJ connectors were not found and modified")
    for field in ("rest_lengths_reset", "hybrid_solves_disabled", "input_probes_removed", "output_probes_removed"):
        if not row[field]:
            raise CaseError("malformed_output", f"effective invariant failed: {field}")
    if row["n_exciters"] <= 0 or row["n_rest_lengths_reset"] <= 0 or row["n_samples"] <= 0:
        raise CaseError("malformed_output", "nonpositive exciter/rest-length/sample count")
    if not row["target_marker_name"].strip():
        raise CaseError("malformed_output", "blank target marker name")
    if row["model_units"] not in {"mm", "m"}:
        raise CaseError("malformed_output", f"unexpected model_units={row['model_units']!r}")
    if cell["mode"] == "fixed_force" and row["n_force_scaled"] != 0:
        raise CaseError("malformed_output", "fixed_force must have n_force_scaled=0")
    if cell["mode"] == "force_capacity_s2" and row["n_force_scaled"] <= 0:
        raise CaseError("malformed_output", "force_capacity_s2 must have n_force_scaled>0")

    target_tolerance = max(0.005, 0.01 * float(cell["target_amp_p2p_mm"]))
    if abs(row["actual_target_amp_p2p_mm"] - float(cell["target_amp_p2p_mm"])) > target_tolerance:
        raise CaseError(
            "malformed_output",
            "actual target peak-to-peak amplitude differs from requested amplitude by more than "
            f"{target_tolerance:g} mm",
        )
    for field in (
        "actual_source_amp_p2p_mm", "actual_target_amp_p2p_mm", "amplitude_gain",
        "tracking_rmse_mm", "peak_excitation", "mean_summed_squared_excitation",
    ):
        if not math.isfinite(float(row[field])):
            raise CaseError("malformed_output", f"nonfinite metric: {field}")
    return row


def read_and_validate_java_csv(path: Path, cell: Mapping[str, Any]) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise CaseError("missing_output", f"missing or empty Java output: {path}")
    try:
        rows = read_csv_rows(path)
    except Exception as exc:
        raise CaseError("malformed_output", f"could not parse Java output: {type(exc).__name__}: {exc}") from exc
    if len(rows) != 1:
        raise CaseError("malformed_output", f"Java output must contain exactly one row; got {len(rows)}")
    return normalize_java_row(rows[0], cell)


def verify_resume(cell_dir: Path, config: Mapping[str, Any], config_sha: str) -> tuple[str, dict[str, str]]:
    config_path = cell_dir / "configuration.json"
    result_csv = cell_dir / "result.csv"
    if not config_path.is_file() or not result_csv.is_file():
        raise CaseError("resume_refused", "resume directory lacks configuration.json or result.csv")
    if sha256_file(config_path) != config_sha:
        raise CaseError("resume_refused", "stored configuration hash does not match current corrected configuration")
    try:
        stored_config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CaseError("resume_refused", f"stored configuration is unreadable: {exc}") from exc
    if canonical_json_bytes(stored_config) != canonical_json_bytes(config):
        raise CaseError("resume_refused", "stored configuration content does not match current corrected configuration")
    rows = read_csv_rows(result_csv)
    if len(rows) != 1:
        raise CaseError("resume_refused", "stored result.csv must contain exactly one row")
    row = rows[0]
    if row.get("configuration_sha256", "") != config_sha:
        raise CaseError("resume_refused", "stored row configuration_sha256 mismatch")

    # Every stored source/runtime identity must match the current configuration.
    for field, expected in config["hashes"].items():
        if field in row and row.get(field, "") != expected:
            raise CaseError("resume_refused", f"stored identity mismatch for {field}")

    # Artifacts that are created for every completed wrapper attempt, including
    # technical failures, must always exist and match their stored hashes.
    required_artifact_pairs = {
        "raw_stdout_path": "raw_stdout_sha256",
        "raw_stderr_path": "raw_stderr_sha256",
        "raw_run_log_path": "raw_run_log_sha256",
        "command_path": "command_sha256",
        "environment_path": "environment_sha256",
        "result_json_path": "result_json_sha256",
    }
    for path_field, hash_field in required_artifact_pairs.items():
        artifact = Path(row.get(path_field, ""))
        expected = row.get(hash_field, "")
        if not artifact.is_file() or not expected or sha256_file(artifact) != expected:
            raise CaseError("resume_refused", f"stored artifact/hash mismatch: {path_field}")

    status = row.get("return_status", "")
    raw_java = Path(row.get("raw_java_csv_path", ""))
    raw_java_hash = row.get("raw_java_csv_sha256", "")
    if status == SUCCESS:
        if not raw_java.is_file() or not raw_java_hash or sha256_file(raw_java) != raw_java_hash:
            raise CaseError("resume_refused", "stored artifact/hash mismatch: raw_java_csv_path")
        read_and_validate_java_csv(raw_java, config["cell"])
        return "skip_success", row

    # A legitimate technical failure may occur before Java creates its output.
    # In that case both the file and stored hash are absent, which is compatible
    # with archiving and rerunning the failed attempt. A partial or untracked
    # Java artifact remains a hard mismatch.
    if raw_java_hash:
        if not raw_java.is_file() or sha256_file(raw_java) != raw_java_hash:
            raise CaseError("resume_refused", "stored artifact/hash mismatch: raw_java_csv_path")
    elif raw_java.is_file():
        raise CaseError(
            "resume_refused",
            "raw Java output exists for a failed attempt but has no stored hash",
        )
    return "rerun_failed", row


def finalize_row(
    *,
    row: dict[str, Any],
    cell_dir: Path,
    config: Mapping[str, Any],
    config_sha: str,
    hashes: Mapping[str, str],
    paths: Mapping[str, Path],
    started: str,
    finished: str,
    elapsed: float,
) -> dict[str, Any]:
    row.update({
        "cell_directory": str(cell_dir),
        "raw_java_csv_path": str(paths["raw_java_csv"]),
        "raw_stdout_path": str(paths["stdout"]),
        "raw_stderr_path": str(paths["stderr"]),
        "raw_run_log_path": str(paths["combined"]),
        "command_path": str(paths["command"]),
        "configuration_path": str(paths["configuration"]),
        "environment_path": str(paths["environment"]),
        "result_json_path": str(paths["result_json"]),
        "result_csv_path": str(paths["result_csv"]),
        "configuration_sha256": config_sha,
        "started_utc": started,
        "finished_utc": finished,
        "elapsed_seconds": elapsed,
    })
    row.update(hashes)
    artifact_hashes = {
        "raw_java_csv_sha256": sha256_file(paths["raw_java_csv"]),
        "raw_stdout_sha256": sha256_file(paths["stdout"]),
        "raw_stderr_sha256": sha256_file(paths["stderr"]),
        "raw_run_log_sha256": sha256_file(paths["combined"]),
        "command_sha256": sha256_file(paths["command"]),
        "environment_sha256": sha256_file(paths["environment"]),
    }
    row.update(artifact_hashes)
    result_document = {
        "spec_version": SPEC_VERSION,
        "configuration_sha256": config_sha,
        "row_without_result_json_hash": row,
    }
    atomic_write_json(paths["result_json"], result_document)
    row["result_json_sha256"] = sha256_file(paths["result_json"])
    return {c: row.get(c, "") for c in OUTPUT_COLUMNS}


def run_case(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    cell = canonical_cell_parameters(args.mode, args.scale, args.freq_hz, args.amp_p2p_mm)
    if args.model_class != MODEL_CLASS:
        raise ValueError(f"canonical model class is {MODEL_CLASS}; got {args.model_class}")
    out_root = args.out_dir.expanduser().resolve()
    cell_dir = out_root / cell["run_id"]

    config, hashes = create_identity(args, cell)
    config_sha = sha256_bytes(canonical_json_bytes(config))

    if args.fresh:
        if cell_dir.exists():
            raise CaseError("resume_refused", f"--fresh refuses existing cell directory: {cell_dir}")
    elif args.resume:
        if cell_dir.exists():
            action, stored_row = verify_resume(cell_dir, config, config_sha)
            if action == "skip_success":
                print(str(cell_dir / "result.csv"))
                return dict(stored_row), 0
            archive_root = out_root / "_attempt_archive"
            archive_existing(cell_dir, archive_root, "failed_matching_configuration")
    else:
        raise ValueError("exactly one of --fresh or --resume is required")

    cell_dir.mkdir(parents=True, exist_ok=False)
    paths = {
        "raw_java_csv": cell_dir / "raw_java_result.csv",
        "stdout": cell_dir / "stdout.log",
        "stderr": cell_dir / "stderr.log",
        "combined": cell_dir / "run.log",
        "command": cell_dir / "command.txt",
        "configuration": cell_dir / "configuration.json",
        "environment": cell_dir / "environment.json",
        "result_json": cell_dir / "result.json",
        "result_csv": cell_dir / "result.csv",
    }
    atomic_write_json(paths["configuration"], config)
    env_snapshot = environment_snapshot(
        java_executable=Path(config["paths"]["java_executable"]),
        artisynth_bin=Path(config["paths"]["artisynth_bin"]),
        arch_mode=config["runtime"]["arch_mode"],
    )
    atomic_write_json(paths["environment"], env_snapshot)
    cmd, env = build_command(config, paths["raw_java_csv"])
    atomic_write_text(paths["command"], command_text(cmd))

    started = utc_now()
    t0 = time.monotonic()
    stdout_text = ""
    stderr_text = ""
    status = SUCCESS
    failure_reason = ""
    return_code: int | str = ""
    java_row: dict[str, Any] = {}

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=float(args.timeout_s),
            check=False,
        )
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        return_code = proc.returncode
        if proc.returncode != 0:
            raise CaseError("launcher_nonzero", f"ArtiSynth launcher returned {proc.returncode}", proc.returncode)
        java_row = read_and_validate_java_csv(paths["raw_java_csv"], cell)
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        failure_reason = f"ArtiSynth exceeded timeout {args.timeout_s:g} s"
        return_code = ""
        stdout_text = (exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout) or ""
        stderr_text = (exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr) or ""
    except CaseError as exc:
        status = exc.status
        failure_reason = str(exc)
        if exc.return_code is not None:
            return_code = exc.return_code
    except Exception as exc:
        status = "internal_error"
        failure_reason = f"{type(exc).__name__}: {exc}"

    elapsed = time.monotonic() - t0
    finished = utc_now()
    atomic_write_text(paths["stdout"], stdout_text)
    atomic_write_text(paths["stderr"], stderr_text)
    combined = (
        "===== STDOUT =====\n" + stdout_text +
        ("\n" if stdout_text and not stdout_text.endswith("\n") else "") +
        "===== STDERR =====\n" + stderr_text +
        ("\n" if stderr_text and not stderr_text.endswith("\n") else "")
    )
    atomic_write_text(paths["combined"], combined)

    row = empty_output_row(cell, status=status, reason=failure_reason or "")
    row["return_code"] = return_code
    if status == SUCCESS:
        row.update(java_row)
        rmse_ok, peak_ok, gain_ok, feasible_flag, failed = feasibility(
            float(row["tracking_rmse_mm"]), float(row["peak_excitation"]), float(row["amplitude_gain"])
        )
        row.update({
            "return_status": SUCCESS,
            "failure_reason": "",
            "rmse_ok": rmse_ok,
            "peak_excitation_ok": peak_ok,
            "amplitude_gain_ok": gain_ok,
            "is_feasible": feasible_flag,
            "failed_criteria": failed,
            "play_time_s": cell["play_time_s"],
        })
    else:
        row.update({
            "return_status": status,
            "failure_reason": failure_reason,
            "failed_criteria": "technical_run_failure",
            "play_time_s": cell["play_time_s"],
        })

    row = finalize_row(
        row=row, cell_dir=cell_dir, config=config, config_sha=config_sha,
        hashes=hashes, paths=paths, started=started, finished=finished, elapsed=elapsed,
    )
    atomic_write_csv(paths["result_csv"], [row], OUTPUT_COLUMNS)
    print(str(paths["result_csv"]))
    return row, (0 if status == SUCCESS else 20)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixed_force", "force_capacity_s2"), required=True)
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--freq-hz", dest="freq_hz", type=float, required=True)
    parser.add_argument("--amp-p2p-mm", dest="amp_p2p_mm", type=float, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--artisynth-bin", type=Path, required=True)
    parser.add_argument("--classes-dir", type=Path, required=True)
    parser.add_argument("--base-classes-dir", type=Path, required=True)
    parser.add_argument("--source-java", type=Path, required=True)
    parser.add_argument("--play-script", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--arch-mode", choices=("x86_64", "native"), required=True)
    parser.add_argument("--model-class", default=MODEL_CLASS)
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--grid-runner-sha256", dest="grid_runner_sha256", default="")
    policy = parser.add_mutually_exclusive_group(required=True)
    policy.add_argument("--fresh", action="store_true")
    policy.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout_s) or args.timeout_s <= 0:
        parser.error("--timeout-s must be finite and >0")
    if args.grid_runner_sha256 and len(args.grid_runner_sha256) != 64:
        parser.error("--grid-runner-sha256 must be empty or 64 lowercase hex characters")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        _, code = run_case(args)
        return code
    except CaseError as exc:
        print(f"ERROR [{exc.status}]: {exc}", file=sys.stderr)
        return 11
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
