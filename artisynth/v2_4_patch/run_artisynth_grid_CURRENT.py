#!/usr/bin/env python3
"""Run one complete 342-cell canonical ArtiSynth grid.

Both modes use this single driver. The only permitted cross-mode difference is
maximum-force scaling: fixed_force uses multiplier 1 without touching force
capacity; force_capacity_s2 touches/scales maximum force by s^2.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from artisynth_common_CURRENT import (
    MODEL_CLASS,
    OUTPUT_COLUMNS,
    SCALES,
    FREQUENCIES,
    AMPLITUDES,
    SPEC_VERSION,
    SUCCESS,
    aggregate_hash,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    canonical_json_bytes,
    command_text,
    empty_output_row,
    environment_snapshot,
    executable_version,
    expected_cells,
    read_csv_rows,
    sha256_bytes,
    sha256_file,
    sha256_tree,
    utc_now,
)

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_DIR = SCRIPT_PATH.parent
CASE_RUNNER = PACKAGE_DIR / "run_artisynth_case_CURRENT.py"
COMMON_MODULE = PACKAGE_DIR / "artisynth_common_CURRENT.py"


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


def build_grid_config(args: argparse.Namespace) -> dict[str, Any]:
    artisynth_bin = require_file(args.artisynth_bin, "ArtiSynth launcher", executable=True)
    classes_dir = require_dir(args.classes_dir, "isolated corrected classes directory")
    base_classes_dir = require_dir(args.base_classes_dir, "ArtiSynth models base classes directory")
    source_java = require_file(args.source_java, "corrected Java source")
    play_script = require_file(args.play_script, "headless play script")
    java_home = require_dir(args.java_home, "Java home")
    java_executable = require_file(java_home / "bin/java", "selected Java executable", executable=True)
    arch_executable = None
    if args.arch_mode == "x86_64":
        arch_executable = require_file(Path("/usr/bin/arch"), "macOS architecture launcher", executable=True)
    require_file(CASE_RUNNER, "CURRENT case runner")
    require_file(COMMON_MODULE, "CURRENT common module")
    class_file = classes_dir / "artisynth/models/dynjaw/MandibleScalingInverseDDK_CURRENT.class"
    if not class_file.is_file():
        raise ValueError(f"compiled corrected model class is missing: {class_file}")

    hashes = {
        "model_source_sha256": sha256_file(source_java),
        "compiled_model_sha256": sha256_tree(classes_dir, suffixes=(".class",)),
        "case_runner_sha256": sha256_file(CASE_RUNNER),
        "grid_runner_sha256": sha256_file(SCRIPT_PATH),
        "common_module_sha256": sha256_file(COMMON_MODULE),
        "play_script_sha256": sha256_file(play_script),
        "artisynth_launcher_sha256": sha256_file(artisynth_bin),
        "java_executable_sha256": sha256_file(java_executable),
        "arch_executable_sha256": sha256_file(arch_executable) if arch_executable else "native",
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "base_jawdemo_class_sha256": sha256_file(
            base_classes_dir / "artisynth/models/dynjaw/JawDemo.class"),
        "base_jawmodel_class_sha256": sha256_file(
            base_classes_dir / "artisynth/models/dynjaw/JawModel.class"),
    }
    for field, value in hashes.items():
        if field == "arch_executable_sha256" and args.arch_mode == "native":
            continue
        if len(value) != 64:
            raise ValueError(f"could not establish required grid identity hash {field}")
    hashes["code_bundle_sha256"] = aggregate_hash(hashes)
    cells = expected_cells(args.mode)
    return {
        "spec_version": SPEC_VERSION,
        "mode": args.mode,
        "model_class": MODEL_CLASS,
        "n_expected_cells": len(cells),
        "grid": {
            "scales": [float(x) for x in SCALES],
            "frequencies_hz": [float(x) for x in FREQUENCIES],
            "target_amplitudes_p2p_mm": [float(x) for x in AMPLITUDES],
            "order": "scale, amplitude, frequency",
            "no_dynamic_early_stopping": True,
        },
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
            "case_runner": str(CASE_RUNNER),
            "grid_runner": str(SCRIPT_PATH),
            "common_module": str(COMMON_MODULE),
        },
        "runtime": {"arch_mode": args.arch_mode, "cell_timeout_s": float(args.timeout_s)},
        "hashes": hashes,
    }


def verify_existing_grid(mode_dir: Path, config: Mapping[str, Any], config_sha: str) -> list[dict[str, str]]:
    config_path = mode_dir / "grid_configuration.json"
    long_csv = mode_dir / f"artisynth_{config['mode']}_runs_long_CURRENT.csv"
    if not config_path.is_file() or not long_csv.is_file():
        raise RuntimeError("resume refused: grid configuration or long table is missing")
    if sha256_file(config_path) != config_sha:
        raise RuntimeError("resume refused: stored grid configuration hash differs")
    stored = json.loads(config_path.read_text(encoding="utf-8"))
    if canonical_json_bytes(stored) != canonical_json_bytes(config):
        raise RuntimeError("resume refused: stored grid configuration content differs")
    rows = read_csv_rows(long_csv)
    if len(rows) != 342:
        raise RuntimeError(f"resume refused: long table has {len(rows)} rows, expected 342")
    ids = [r.get("run_id", "") for r in rows]
    expected_ids = [c["run_id"] for c in expected_cells(str(config["mode"]))]
    if ids != expected_ids:
        raise RuntimeError("resume refused: long-table order/keys differ from canonical expected grid")
    return rows


def read_cell_result(path: Path, expected_id: str) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"cell result missing: {path}")
    rows = read_csv_rows(path)
    if len(rows) != 1:
        raise RuntimeError(f"cell result must have one row: {path}")
    row = rows[0]
    if row.get("run_id") != expected_id:
        raise RuntimeError(f"cell run_id mismatch in {path}")
    if list(row.keys()) != OUTPUT_COLUMNS:
        raise RuntimeError(f"cell result schema mismatch in {path}")
    return row


def case_command(args: argparse.Namespace, config: Mapping[str, Any], cell: Mapping[str, Any], cells_root: Path) -> list[str]:
    cmd = [
        str(Path(sys.executable).resolve()), str(CASE_RUNNER),
        "--mode", str(cell["mode"]),
        "--scale", format(float(cell["scale"]), ".17g"),
        "--freq-hz", format(float(cell["freq_hz"]), ".17g"),
        "--amp-p2p-mm", format(float(cell["target_amp_p2p_mm"]), ".17g"),
        "--out-dir", str(cells_root),
        "--artisynth-bin", config["paths"]["artisynth_bin"],
        "--classes-dir", config["paths"]["classes_dir"],
        "--base-classes-dir", config["paths"]["base_classes_dir"],
        "--source-java", config["paths"]["source_java"],
        "--play-script", config["paths"]["play_script"],
        "--java-home", config["paths"]["java_home"],
        "--arch-mode", config["runtime"]["arch_mode"],
        "--model-class", MODEL_CLASS,
        "--timeout-s", format(float(config["runtime"]["cell_timeout_s"]), ".17g"),
        "--grid-runner-sha256", config["hashes"]["grid_runner_sha256"],
        "--resume" if args.resume else "--fresh",
    ]
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixed_force", "force_capacity_s2"), required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--artisynth-bin", type=Path, required=True)
    parser.add_argument("--classes-dir", type=Path, required=True)
    parser.add_argument("--base-classes-dir", type=Path, required=True)
    parser.add_argument("--source-java", type=Path, required=True)
    parser.add_argument("--play-script", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--arch-mode", choices=("x86_64", "native"), required=True)
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--continue-after-technical-failure", action="store_true",
                        help="Continue later cells after a technical failure. Default is fail-fast; the 342-row table remains populated with not_attempted rows.")
    policy = parser.add_mutually_exclusive_group(required=True)
    policy.add_argument("--fresh", action="store_true")
    policy.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout_s) or args.timeout_s <= 0:
        parser.error("--timeout-s must be finite and >0")

    try:
        config = build_grid_config(args)
        config_sha = sha256_bytes(canonical_json_bytes(config))
        out_root = args.out_root.expanduser().resolve()
        mode_dir = out_root / args.mode
        cells_root = mode_dir / "cells"
        invocation_dir = mode_dir / "case_runner_invocations"
        long_csv = mode_dir / f"artisynth_{args.mode}_runs_long_CURRENT.csv"
        expected = expected_cells(args.mode)

        if args.fresh:
            if mode_dir.exists():
                raise RuntimeError(f"--fresh refuses existing mode directory: {mode_dir}")
            mode_dir.mkdir(parents=True, exist_ok=False)
            cells_root.mkdir()
            invocation_dir.mkdir()
            rows: list[dict[str, Any]] = [empty_output_row(cell) for cell in expected]
            atomic_write_json(mode_dir / "grid_configuration.json", config)
            grid_env = environment_snapshot(
                java_executable=Path(config["paths"]["java_executable"]),
                artisynth_bin=Path(config["paths"]["artisynth_bin"]),
                arch_mode=config["runtime"]["arch_mode"],
            )
            env = os.environ.copy()
            env["JAVA_HOME"] = config["paths"]["java_home"]
            env["PATH"] = str(Path(config["paths"]["java_home"]) / "bin") + os.pathsep + env.get("PATH", "")
            artisynth_version_cmd = [config["paths"]["artisynth_bin"], "-version"]
            if config["runtime"]["arch_mode"] == "x86_64":
                artisynth_version_cmd = [config["paths"]["arch_executable"], "-x86_64"] + artisynth_version_cmd
            grid_env["artisynth_version_probe"] = executable_version(
                artisynth_version_cmd, env=env, timeout=30.0)
            grid_env["grid_configuration_sha256"] = config_sha
            atomic_write_json(mode_dir / "grid_environment.json", grid_env)
            atomic_write_csv(long_csv, rows, OUTPUT_COLUMNS)
        else:
            rows = verify_existing_grid(mode_dir, config, config_sha)
            cells_root.mkdir(exist_ok=True)
            invocation_dir.mkdir(exist_ok=True)

        index = {str(row["run_id"]): i for i, row in enumerate(rows)}
        manifest_rows: list[dict[str, Any]] = []
        manifest_path = mode_dir / "grid_invocation_manifest.csv"
        started_grid = utc_now()
        technical_failures = 0
        skipped_success = 0

        for ordinal, cell in enumerate(expected, start=1):
            rid = str(cell["run_id"])
            cmd = case_command(args, config, cell, cells_root)
            stdout_path = invocation_dir / f"{rid}.stdout.log"
            stderr_path = invocation_dir / f"{rid}.stderr.log"
            command_path = invocation_dir / f"{rid}.command.txt"
            atomic_write_text(command_path, command_text(cmd))
            t0 = time.monotonic()
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            elapsed = time.monotonic() - t0
            atomic_write_text(stdout_path, proc.stdout or "")
            atomic_write_text(stderr_path, proc.stderr or "")
            result_path = cells_root / rid / "result.csv"
            try:
                result = read_cell_result(result_path, rid)
            except Exception as exc:
                result = {k: str(v) for k, v in empty_output_row(cell, status="case_runner_missing_result", reason=str(exc)).items()}
                result["return_code"] = str(proc.returncode)
                result["grid_runner_sha256"] = config["hashes"]["grid_runner_sha256"]
            rows[index[rid]] = result
            atomic_write_csv(long_csv, rows, OUTPUT_COLUMNS)

            status = result.get("return_status", "")
            if status != SUCCESS:
                technical_failures += 1
            elif args.resume and "result.csv" in (proc.stdout or "") and elapsed < 2.0:
                # Diagnostic only; skip identity is independently checked by the case runner.
                skipped_success += 1
            manifest_rows.append({
                "ordinal": ordinal,
                "run_id": rid,
                "case_runner_return_code": proc.returncode,
                "return_status": status,
                "elapsed_seconds": format(elapsed, ".9g"),
                "command_path": str(command_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "result_path": str(result_path) if result_path.is_file() else "",
            })
            atomic_write_csv(
                manifest_path,
                manifest_rows,
                ["ordinal", "run_id", "case_runner_return_code", "return_status", "elapsed_seconds",
                 "command_path", "stdout_path", "stderr_path", "result_path"],
            )
            print(f"[{ordinal:03d}/342] {rid}: {status}", flush=True)
            if status != SUCCESS and not args.continue_after_technical_failure:
                print("Technical failure: stopping grid. Re-run with --resume after resolving the cause.", file=sys.stderr)
                break

        success_count = sum(1 for row in rows if row.get("return_status") == SUCCESS)
        not_attempted = sum(1 for row in rows if row.get("return_status") == "not_attempted")
        summary = {
            "spec_version": SPEC_VERSION,
            "mode": args.mode,
            "grid_configuration_sha256": config_sha,
            "started_utc": started_grid,
            "finished_utc": utc_now(),
            "expected_cells": 342,
            "successful_cells": success_count,
            "technical_failure_cells": 342 - success_count - not_attempted,
            "not_attempted_cells": not_attempted,
            "resume_skip_diagnostic_count": skipped_success,
            "long_table": str(long_csv),
            "long_table_sha256": sha256_file(long_csv),
            "complete_technical_grid": success_count == 342,
        }
        atomic_write_json(mode_dir / "grid_run_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if success_count == 342 else 20
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
