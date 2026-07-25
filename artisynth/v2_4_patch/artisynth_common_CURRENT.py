#!/usr/bin/env python3
"""Shared constants and integrity helpers for the corrected ArtiSynth rerun.

This module contains no simulation results. It centralizes the canonical grid,
configuration identity, output schema, feasibility rules, and hashing logic used
by all CURRENT scripts.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SPEC_VERSION = "ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2"
MODEL_CLASS = "artisynth.models.dynjaw.MandibleScalingInverseDDK_CURRENT"
POSITION_FORMULA_ID = "P2P_ONE_SIDED_SIN_ACTIVE_V1"
VELOCITY_FORMULA_ID = "P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1"
CONTROLLER_ARCHITECTURE_ID = "TrackingController_point_target_LI_L2_excitation_damping_V1"

MODES = ("fixed_force", "force_capacity_s2")
SCALES = tuple(Decimal(x) for x in ("0.80", "0.85", "0.90", "0.95", "1.00", "1.05", "1.10", "1.15", "1.20"))
FREQUENCIES = tuple(Decimal("1.0") + Decimal("0.5") * i for i in range(19))
AMPLITUDES = (Decimal("1.0"), Decimal("1.5"))

MASS_EXP = 3.0
INERTIA_EXP = 5.0
DURATION_S = 4.0
SETTLE_S = 0.5
PLAY_TIME_S = 4.8
TARGET_WEIGHT = 100.0
L2_REGULARIZATION = 0.01
EXCITATION_DAMPING = 0.1
FRAME_DAMPING = 2.0
ROTARY_DAMPING = 4.0
MAX_STEP_S = 0.00025
OPEN_GAP_MM = 0.0
RMSE_MAX_MM = 0.5
PEAK_EXCITATION_MAX = 0.95
GAIN_MIN = 0.7
GAIN_MAX = 1.3
COLLISION_SETTING = "disabled"
TMJ_SETTING = "unilateral_false"
GRAVITY_STATE = "disabled"
GRAVITY_VECTOR = (0.0, 0.0, 0.0)

SUCCESS = "success"
FAILURE_STATUSES = {
    "not_attempted",
    "timeout",
    "launcher_nonzero",
    "missing_output",
    "malformed_output",
    "internal_error",
    "case_runner_missing_result",
    "resume_refused",
}

OUTPUT_COLUMNS = [
    "run_id", "spec_version", "mode", "scale", "freq_hz", "target_amp_p2p_mm",
    "mass_exp", "inertia_exp", "mass_multiplier", "inertia_multiplier",
    "force_exp", "effective_force_multiplier", "n_force_scaled",
    "duration_s", "settle_s", "play_time_s", "open_gap_mm",
    "gravity_state", "gravity_enabled", "gravity_x", "gravity_y", "gravity_z",
    "target_position_formula_id", "target_velocity_formula_id", "target_marker_name",
    "controller_architecture_id", "target_weight", "l2_regularization",
    "excitation_damping", "frame_damping", "rotary_damping", "max_step_s",
    "collision_setting", "collision_api_success", "collision_behaviors_disabled",
    "tmj_joint_setting", "tmj_connectors_found", "tmj_connectors_modified",
    "rest_lengths_reset", "n_rest_lengths_reset", "n_exciters",
    "hybrid_solves_disabled", "input_probes_removed", "output_probes_removed",
    "geometry_scaled", "model_units",
    "return_status", "return_code", "failure_reason", "n_samples",
    "actual_source_amp_p2p_mm", "actual_target_amp_p2p_mm", "amplitude_gain",
    "tracking_rmse_mm", "peak_excitation", "mean_summed_squared_excitation",
    "rmse_ok", "peak_excitation_ok", "amplitude_gain_ok", "is_feasible",
    "failed_criteria", "cell_directory", "raw_java_csv_path", "raw_stdout_path",
    "raw_stderr_path", "raw_run_log_path", "command_path", "configuration_path",
    "environment_path", "result_json_path", "result_csv_path",
    "model_source_sha256", "compiled_model_sha256", "case_runner_sha256",
    "grid_runner_sha256", "common_module_sha256", "play_script_sha256",
    "artisynth_launcher_sha256", "java_executable_sha256", "python_executable_sha256",
    "base_jawdemo_class_sha256", "base_jawmodel_class_sha256", "code_bundle_sha256",
    "configuration_sha256", "raw_java_csv_sha256", "raw_stdout_sha256",
    "raw_stderr_sha256", "raw_run_log_sha256", "command_sha256",
    "environment_sha256", "result_json_sha256", "started_utc", "finished_utc",
    "elapsed_seconds",
]

JAVA_REQUIRED_COLUMNS = [
    "spec_version", "mode", "scale", "freq_hz", "target_amp_p2p_mm",
    "mass_exp", "inertia_exp", "mass_multiplier", "inertia_multiplier",
    "force_exp", "effective_force_multiplier", "n_force_scaled",
    "duration_s", "settle_s", "open_gap_mm", "gravity_state", "gravity_enabled",
    "gravity_x", "gravity_y", "gravity_z", "target_position_formula_id",
    "target_velocity_formula_id", "target_marker_name", "controller_architecture_id",
    "target_weight", "l2_regularization", "excitation_damping", "frame_damping",
    "rotary_damping", "max_step_s", "collision_setting", "collision_api_success",
    "collision_behaviors_disabled", "tmj_joint_setting", "tmj_connectors_found",
    "tmj_connectors_modified", "rest_lengths_reset", "n_rest_lengths_reset",
    "n_exciters", "hybrid_solves_disabled", "input_probes_removed",
    "output_probes_removed", "geometry_scaled", "model_units", "n_samples",
    "actual_source_amp_p2p_mm", "actual_target_amp_p2p_mm", "amplitude_gain",
    "tracking_rmse_mm", "peak_excitation", "mean_summed_squared_excitation",
]

BOOL_FIELDS = {
    "gravity_enabled", "collision_api_success", "rest_lengths_reset",
    "hybrid_solves_disabled", "input_probes_removed", "output_probes_removed",
    "geometry_scaled", "rmse_ok", "peak_excitation_ok", "amplitude_gain_ok",
    "is_feasible",
}
INT_FIELDS = {
    "n_force_scaled", "collision_behaviors_disabled", "tmj_connectors_found",
    "tmj_connectors_modified", "n_rest_lengths_reset", "n_exciters",
    "return_code", "n_samples",
}
FLOAT_FIELDS = {
    "scale", "freq_hz", "target_amp_p2p_mm", "mass_exp", "inertia_exp",
    "mass_multiplier", "inertia_multiplier", "force_exp", "effective_force_multiplier",
    "duration_s", "settle_s", "play_time_s", "open_gap_mm", "gravity_x",
    "gravity_y", "gravity_z", "target_weight", "l2_regularization",
    "excitation_damping", "frame_damping", "rotary_damping", "max_step_s",
    "actual_source_amp_p2p_mm", "actual_target_amp_p2p_mm", "amplitude_gain",
    "tracking_rmse_mm", "peak_excitation", "mean_summed_squared_excitation",
    "elapsed_seconds",
}
SHA_FIELDS = {c for c in OUTPUT_COLUMNS if c.endswith("_sha256")}
PATH_FIELDS = {
    "cell_directory", "raw_java_csv_path", "raw_stdout_path", "raw_stderr_path",
    "raw_run_log_path", "command_path", "configuration_path", "environment_path",
    "result_json_path", "result_csv_path",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, *, missing: str = "") -> str:
    p = Path(path)
    if not p.is_file():
        return missing
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_tree(root: Path | str, *, suffixes: Sequence[str] | None = None) -> str:
    root = Path(root)
    if not root.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        if suffixes and p.suffix not in suffixes:
            continue
        rel = p.relative_to(root).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(8, "big")); h.update(rel)
        digest = bytes.fromhex(sha256_file(p))
        h.update(digest)
    return h.hexdigest()


def aggregate_hash(named_hashes: Mapping[str, str]) -> str:
    clean = {str(k): str(v) for k, v in sorted(named_hashes.items())}
    return sha256_bytes(canonical_json_bytes(clean))


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def atomic_write_text(path: Path | str, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path | str, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def atomic_write_csv(path: Path | str, rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: serialize_cell(row.get(c, "")) for c in columns})
            fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def serialize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(value, ".17g")
    return str(value)


def parse_bool(value: Any, field: str = "boolean") -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    raise ValueError(f"{field}: expected boolean, got {value!r}")


def parse_float(value: Any, field: str, *, finite: bool = True) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: expected number, got {value!r}") from exc
    if finite and not math.isfinite(x):
        raise ValueError(f"{field}: non-finite value {value!r}")
    return x


def parse_int(value: Any, field: str) -> int:
    try:
        x = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: expected integer, got {value!r}") from exc
    return x


def close(a: float, b: float, *, atol: float = 1e-9, rtol: float = 1e-9) -> bool:
    return math.isclose(float(a), float(b), abs_tol=atol, rel_tol=rtol)


def decimal_token(value: Decimal | float | str, places: int) -> str:
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return f"{d:.{places}f}".replace(".", "p")


def run_id(mode: str, scale: Decimal | float | str, freq: Decimal | float | str, amp: Decimal | float | str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return f"{mode}__s{decimal_token(scale,2)}__f{decimal_token(freq,1)}__A{decimal_token(amp,1)}"


def expected_cells(mode: str) -> list[dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    out: list[dict[str, Any]] = []
    force_exp = 0.0 if mode == "fixed_force" else 2.0
    for scale in SCALES:
        for amp in AMPLITUDES:
            for freq in FREQUENCIES:
                sf, ff, af = float(scale), float(freq), float(amp)
                out.append({
                    "run_id": run_id(mode, scale, freq, amp),
                    "mode": mode,
                    "scale": sf,
                    "freq_hz": ff,
                    "target_amp_p2p_mm": af,
                    "mass_exp": MASS_EXP,
                    "inertia_exp": INERTIA_EXP,
                    "mass_multiplier": sf ** MASS_EXP,
                    "inertia_multiplier": sf ** INERTIA_EXP,
                    "force_exp": force_exp,
                    "effective_force_multiplier": 1.0 if mode == "fixed_force" else sf ** 2,
                })
    return out


def canonical_cell_parameters(mode: str, scale: float, freq_hz: float, amp_mm: float) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    def match(value: float, grid: Sequence[Decimal], label: str) -> float:
        observed = float(value)
        for item in grid:
            candidate = float(item)
            if close(observed, candidate, atol=1e-9, rtol=1e-9):
                return candidate
        raise ValueError(f"{label} is outside canonical grid: {value}")
    scale = match(float(scale), SCALES, "scale")
    freq_hz = match(float(freq_hz), FREQUENCIES, "frequency")
    amp_mm = match(float(amp_mm), AMPLITUDES, "amplitude")
    force_exp = 0.0 if mode == "fixed_force" else 2.0
    return {
        "spec_version": SPEC_VERSION,
        "run_id": run_id(mode, scale, freq_hz, amp_mm),
        "mode": mode,
        "scale": float(scale),
        "freq_hz": float(freq_hz),
        "target_amp_p2p_mm": float(amp_mm),
        "mass_exp": MASS_EXP,
        "inertia_exp": INERTIA_EXP,
        "mass_multiplier": float(scale) ** MASS_EXP,
        "inertia_multiplier": float(scale) ** INERTIA_EXP,
        "force_exp": force_exp,
        "effective_force_multiplier": 1.0 if mode == "fixed_force" else float(scale) ** force_exp,
        "duration_s": DURATION_S,
        "settle_s": SETTLE_S,
        "play_time_s": PLAY_TIME_S,
        "open_gap_mm": OPEN_GAP_MM,
        "gravity_state": GRAVITY_STATE,
        "gravity_enabled": False,
        "gravity_x": 0.0, "gravity_y": 0.0, "gravity_z": 0.0,
        "target_position_formula_id": POSITION_FORMULA_ID,
        "target_velocity_formula_id": VELOCITY_FORMULA_ID,
        "controller_architecture_id": CONTROLLER_ARCHITECTURE_ID,
        "target_weight": TARGET_WEIGHT,
        "l2_regularization": L2_REGULARIZATION,
        "excitation_damping": EXCITATION_DAMPING,
        "frame_damping": FRAME_DAMPING,
        "rotary_damping": ROTARY_DAMPING,
        "max_step_s": MAX_STEP_S,
        "collision_setting": COLLISION_SETTING,
        "tmj_joint_setting": TMJ_SETTING,
    }


def feasibility(rmse: float, peak: float, gain: float) -> tuple[bool, bool, bool, bool, str]:
    rmse_ok = math.isfinite(rmse) and rmse <= RMSE_MAX_MM
    peak_ok = math.isfinite(peak) and peak <= PEAK_EXCITATION_MAX
    gain_ok = math.isfinite(gain) and GAIN_MIN <= gain <= GAIN_MAX
    failed = []
    if not rmse_ok: failed.append("tracking_rmse_mm")
    if not peak_ok: failed.append("peak_excitation")
    if not gain_ok: failed.append("amplitude_gain")
    return rmse_ok, peak_ok, gain_ok, (rmse_ok and peak_ok and gain_ok), ";".join(failed)


def empty_output_row(cell: Mapping[str, Any], *, status: str = "not_attempted", reason: str = "not attempted") -> dict[str, Any]:
    row = {c: "" for c in OUTPUT_COLUMNS}
    row.update(canonical_cell_parameters(str(cell["mode"]), float(cell["scale"]), float(cell["freq_hz"]), float(cell["target_amp_p2p_mm"])))
    row.update({
        "return_status": status,
        "return_code": "",
        "failure_reason": reason,
        "rmse_ok": False,
        "peak_excitation_ok": False,
        "amplitude_gain_ok": False,
        "is_feasible": False,
        "failed_criteria": "technical_run_failure",
        "geometry_scaled": False,
    })
    return row


def command_text(cmd: Sequence[str]) -> str:
    import shlex
    return " ".join(shlex.quote(str(x)) for x in cmd) + "\n"


def executable_version(command: Sequence[str], *, env: Mapping[str, str] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(list(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              timeout=timeout, env=dict(env) if env is not None else None, check=False)
        return {"command": list(command), "returncode": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as exc:
        return {"command": list(command), "error": f"{type(exc).__name__}: {exc}"}


def environment_snapshot(*, java_executable: Path, artisynth_bin: Path, arch_mode: str) -> dict[str, Any]:
    env = os.environ.copy()
    java_cmd = [str(java_executable), "-version"]
    if arch_mode == "x86_64":
        java_cmd = ["/usr/bin/arch", "-x86_64", str(java_executable), "-version"]
    return {
        "captured_utc": utc_now(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "java_executable": str(java_executable),
        "java_executable_sha256": sha256_file(java_executable),
        "java_version": executable_version(java_cmd, env=env),
        "arch_mode": arch_mode,
        "artisynth_bin": str(artisynth_bin),
        "artisynth_launcher_sha256": sha256_file(artisynth_bin),
        "artisynth_version_probe_policy": (
            "Not launched per cell. Capture the ArtiSynth version/build once in the grid-level "
            "environment record and preserved command logs."
        ),
        "java_binary_file_report": executable_version(["/usr/bin/file", str(java_executable)], env=env),
        "selected_environment": {k: env.get(k, "") for k in ("JAVA_HOME", "PATH", "ARTISYNTH_HOME")},
    }


def ensure_sha256(value: str, field: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(value)):
        raise ValueError(f"{field}: expected SHA256 hex, got {value!r}")


def archive_existing(path: Path, archive_root: Path, label: str) -> Path:
    archive_root.mkdir(parents=True, exist_ok=True)
    dest = archive_root / f"{path.name}.{label}.{utc_now().replace(':','').replace('-','')}"
    if dest.exists():
        raise RuntimeError(f"archive destination already exists: {dest}")
    shutil.move(str(path), str(dest))
    return dest
