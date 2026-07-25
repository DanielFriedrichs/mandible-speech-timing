#!/usr/bin/env python3
"""
build_analysis_dataset.py

Merge:
  1) EMA trial metrics (derived from cycles)
  2) Audio trial envelope metrics (derived from sweep-aligned wavs)
  3) Anatomy / size measures (CSV long-form or JSON dict)

Outputs a single trial-level CSV suitable for statistical analysis and plotting.

Designed for the SpeechRateAndMandible paper pipeline.

Example:
  python mandible_rate_analysis/build_analysis_dataset.py \
    --ema_trial_metrics   "$OUT/ema_cycle_metrics/ema_trial_metrics_from_cycles.csv" \
    --audio_trial_metrics "$OUT/audio_envelope_sweeps/audio_trial_envelope.csv" \
    --anatomy_csv         "$DOCS/anatomy_measurements.csv" \
    --out_csv             "$OUT/analysis_ready_trials.csv"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# -------------------------
# Helpers
# -------------------------

def best_common_key(left: pd.DataFrame, right: pd.DataFrame) -> List[str]:
    """Pick a stable merge key. Prefer full DDK trial key if available."""
    preferred = ["participant_id", "sequence", "rate", "index"]
    if all(c in left.columns for c in preferred) and all(c in right.columns for c in preferred):
        return preferred

    # Fallbacks (avoid participant_id+index only; it's not unique across sequence/rate)
    candidates = [
        ["participant_id", "sweep_number", "trial_index"],
        ["participant_id", "sweep_number", "trial_in_block"],
        ["participant_id", "trial_index"],
    ]
    for cand in candidates:
        if all(c in left.columns for c in cand) and all(c in right.columns for c in cand):
            return cand

    common = [c for c in preferred if c in left.columns and c in right.columns]
    if common:
        return common

    raise ValueError(
        "Could not determine a merge key. "
        f"Left cols sample={list(left.columns)[:25]} ... Right cols sample={list(right.columns)[:25]} ..."
    )


def load_anatomy_from_json(path: Path) -> pd.DataFrame:
    """
    Expect a JSON dict keyed by participant_id (e.g., {"sub-055": {...}, ...}).
    Values may be nested; we keep them as flat columns when possible.
    """
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    rows = []
    for pid, rec in d.items():
        if isinstance(rec, dict):
            row = {"participant_id": pid}
            row.update(rec)
            rows.append(row)
        else:
            rows.append({"participant_id": pid, "anatomy_value": rec})
    return pd.DataFrame(rows)


def load_anatomy_from_csv(path: Path) -> pd.DataFrame:
    """
    Supports two CSV layouts:
    A) Long-form (recommended): columns include participant_id, measure, side, value_mm and/or value_kg/value_lb.
    B) Wide-form: already one row per participant_id with measure columns.

    Returns a wide-form dataframe keyed by participant_id with *_mm / *_kg columns.
    """
    df = pd.read_csv(path)

    if "participant_id" not in df.columns:
        raise ValueError(f"Anatomy CSV must contain 'participant_id'. Found columns: {list(df.columns)}")

    # Wide-form: already one row per participant
    if "measure" not in df.columns:
        # Ensure unique participant rows if possible
        if df.duplicated(["participant_id"]).any():
            raise ValueError(
                "Anatomy CSV appears wide-form but has multiple rows per participant_id. "
                "Please provide long-form anatomy_measurements.csv or aggregate it first."
            )
        return df

    # Long-form pivot
    # Decide numeric value per row
    def pick_value(row) -> Optional[float]:
        m = str(row.get("measure", "")).strip().lower()
        if m == "weight":
            if "value_kg" in row and pd.notna(row["value_kg"]):
                return float(row["value_kg"])
            if "value_lb" in row and pd.notna(row["value_lb"]):
                return float(row["value_lb"]) * 0.45359237
            return None
        # height, mandible measures
        for col in ["value_mm", "value", "mm"]:
            if col in row and pd.notna(row[col]):
                return float(row[col])
        return None

    df = df.copy()
    df["value_num"] = df.apply(pick_value, axis=1)

    # Build a column name for pivot
    def out_col(row) -> str:
        m = str(row.get("measure", "")).strip().lower()
        side = row.get("side", None)
        side = None if (pd.isna(side) or side == "") else str(side).strip().upper()
        if m == "weight":
            # no side expected
            return "weight_kg"
        unit = "mm"
        if side in ("L", "R"):
            return f"{m}_{side}_{unit}"
        return f"{m}_{unit}"

    df["col"] = df.apply(out_col, axis=1)

    wide = (
        df.pivot_table(index="participant_id", columns="col", values="value_num", aggfunc="mean")
          .reset_index()
    )

    # Add mean across L/R for common bilateral measures
    for m in ["co_go", "co_me", "go_me"]:
        l = f"{m}_L_mm"
        r = f"{m}_R_mm"
        if l in wide.columns and r in wide.columns:
            wide[f"{m}_mean_mm"] = wide[[l, r]].mean(axis=1, skipna=True)

    # Optional: derive a simple composite mandible size index (mean of available mandible measures)
    mand_cols = [c for c in ["co_go_mean_mm", "co_me_mean_mm", "go_me_mean_mm"] if c in wide.columns]
    if mand_cols:
        wide["mandible_size_mean_mm"] = wide[mand_cols].mean(axis=1, skipna=True)

    # Height helpers
    if "height_mm" in wide.columns:
        wide["height_m"] = wide["height_mm"] / 1000.0

    # BMI if possible
    if "weight_kg" in wide.columns and "height_m" in wide.columns:
        wide["bmi"] = wide["weight_kg"] / (wide["height_m"] ** 2)

    return wide


def ensure_unique(df: pd.DataFrame, key: List[str], name: str) -> None:
    if df.duplicated(key).any():
        n = int(df.duplicated(key).sum())
        example = df.loc[df.duplicated(key, keep=False), key].head(10)
        raise ValueError(
            f"{name} is not unique on key {key}. Duplicates={n}.\n"
            f"Example duplicate keys:\n{example.to_string(index=False)}"
        )


# -------------------------
# Main
# -------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ema_trial_metrics", required=True, help="CSV from derive_ema_cycle_metrics*.py")
    ap.add_argument("--audio_trial_metrics", default="", help="CSV from run_audio_envelope_from_sweeps*.py")
    ap.add_argument("--anatomy_csv", default="", help="Anatomy measurements CSV (long-form recommended).")
    ap.add_argument("--anatomy_json", default="", help="Anatomy measurements JSON dict.")
    ap.add_argument("--out_csv", required=True, help="Output CSV path.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    ema_path = Path(args.ema_trial_metrics)
    if not ema_path.exists():
        raise SystemExit(f"[ERROR] Missing EMA metrics CSV: {ema_path}")
    ema = pd.read_csv(ema_path)

    # Base output is EMA metrics
    df = ema.copy()

    # --- Merge audio ---
    if args.audio_trial_metrics:
        audio_path = Path(args.audio_trial_metrics)
        if not audio_path.exists():
            raise SystemExit(f"[ERROR] Missing audio metrics CSV: {audio_path}")
        audio = pd.read_csv(audio_path)

        key = best_common_key(df, audio)
        print(f"[INFO] Using merge key: {key}")

        ensure_unique(df, key, "EMA metrics")
        ensure_unique(audio, key, "Audio metrics")

        # Keep a compact but useful audio subset
        keep_audio: List[str] = list(key)
        for c in [
            "sweep_number",
            "trial_in_block",
            "trial_start_in_sweep_sec",
            "analysis_start_sweep_s",
            "analysis_end_sweep_s",
            "analysis_len_s",
            "analysis_ok",
            "seg_len_s",
            "wav_path",
        ]:
            if c in audio.columns and c not in keep_audio:
                keep_audio.append(c)

        keep_audio += [c for c in audio.columns if c.startswith("audio_") and c not in keep_audio]

        # Merge; overlapping non-key columns from audio get _audio suffix
        df = df.merge(audio[keep_audio], on=key, how="left", validate="m:1", suffixes=("", "_audio"))

        # Report missing audio
        audio_metric_cols = [c for c in df.columns if c.startswith("audio_")]
        if audio_metric_cols:
            missing_audio = int(df[audio_metric_cols].isna().all(axis=1).sum())
        else:
            # fallback: missing wav_path
            missing_audio = int(df.get("wav_path", pd.Series([pd.NA] * len(df))).isna().sum())
        print(f"[INFO] Missing audio rows after merge: {missing_audio}/{len(df)}")

    else:
        print("[WARN] No audio metrics provided; output will not contain audio measures.")

    # --- Merge anatomy ---
    if args.anatomy_csv and args.anatomy_json:
        print("[WARN] Both --anatomy_csv and --anatomy_json provided; using CSV and ignoring JSON.")

    if args.anatomy_csv:
        anat_path = Path(args.anatomy_csv)
        if not anat_path.exists():
            raise SystemExit(f"[ERROR] Missing anatomy CSV: {anat_path}")
        anat_df = load_anatomy_from_csv(anat_path)
        if anat_df.duplicated(["participant_id"]).any():
            raise SystemExit("[ERROR] Anatomy table is not unique per participant_id after processing.")
        df = df.merge(anat_df, on="participant_id", how="left", validate="m:1")
        print(f"[INFO] Merged anatomy from CSV (participants={anat_df['participant_id'].nunique()})")

    elif args.anatomy_json:
        anat_path = Path(args.anatomy_json)
        if not anat_path.exists():
            raise SystemExit(f"[ERROR] Missing anatomy JSON: {anat_path}")
        anat_df = load_anatomy_from_json(anat_path)
        if anat_df.duplicated(["participant_id"]).any():
            raise SystemExit("[ERROR] Anatomy JSON produced duplicate participant_id rows.")
        df = df.merge(anat_df, on="participant_id", how="left", validate="m:1")
        print(f"[INFO] Merged anatomy from JSON (participants={anat_df['participant_id'].nunique()})")

    else:
        print("[WARN] No anatomy provided; output will not contain size measures.")

    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"[DONE] Wrote {out_path} (rows={len(df)}, cols={len(df.columns)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
