#!/usr/bin/env python3
"""run_audio_envelope_from_sweeps_v2.py

Compute per-trial audio envelope metrics directly from sweep WAV files
(using trial timing info in ema_trial_alignment.csv).

Key improvements vs v1:
- Outputs all trials (missing wavs remain as rows with flags + NaNs)
- Merge-safe keys (trial_index vs index vs block_num/trial_in_block)
- Fixed analysis window from trial onset, optionally capped by next trial onset/cue
- No need for EEG_responses wavs/TextGrids

Typical usage:
  python mandible_rate_analysis/run_audio_envelope_from_sweeps_v2.py \
    --dataset_root "/path/to/Data" \
    --tables_dir "/path/to/outputs/tables" \
    --out_dir "/path/to/outputs/audio_envelope_sweeps_v2" \
    --fixed_window_s 6.0 \
    --trim_edge_s 0.25 \
    --cap_to_next both \
    --min_analysis_s 2.0
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import soundfile as sf
from scipy.signal import hilbert, find_peaks, welch, resample_poly


def pick_col(df: pd.DataFrame, candidates: List[str], *, required: bool = True) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise KeyError(f"None of these columns found: {candidates}\nAvailable: {list(df.columns)}")
    return None


def choose_key_cols(df: pd.DataFrame) -> List[str]:
    """Choose a stable key for trial-level merges."""
    if "participant_id" not in df.columns:
        raise KeyError("alignment table must contain participant_id")

    if "trial_index" in df.columns and df["trial_index"].notna().any():
        if "sweep_number" in df.columns:
            return ["participant_id", "sweep_number", "trial_index"]
        return ["participant_id", "trial_index"]

    if "index" in df.columns and df["index"].notna().any():
        return ["participant_id", "index"]

    if all(c in df.columns for c in ["participant_id", "block_num", "trial_in_block"]):
        return ["participant_id", "block_num", "trial_in_block"]

    raise KeyError("Could not determine key columns (need trial_index or index or block_num+trial_in_block).")


def find_audio_dir(dataset_root: Path, participant_id: str) -> Path:
    p = dataset_root / participant_id / "Audio" / "wav"
    if p.exists():
        return p
    p2 = dataset_root / participant_id / "Audio"
    if p2.exists():
        return p2
    return p


def _regex_for_sweep(sweep_number: int) -> re.Pattern:
    sn = int(sweep_number)
    return re.compile(rf"(^|[^0-9])0*{sn}([^0-9]|$)", flags=re.IGNORECASE)


def find_sweep_wav(audio_dir: Path, participant_id: str, sweep_number: int, file_cache: Dict[str, List[Path]]) -> Optional[Path]:
    key = str(audio_dir)
    if key not in file_cache:
        if audio_dir.exists():
            file_cache[key] = sorted([p for p in audio_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".wav"])
        else:
            file_cache[key] = []

    files = file_cache[key]
    if not files:
        return None

    r_num = _regex_for_sweep(sweep_number)

    cands = [p for p in files if ("sweep" in p.name.lower() and r_num.search(p.name))]
    if not cands:
        cands = [p for p in files if r_num.search(p.name)]
    if not cands:
        return None

    def score(p: Path) -> Tuple[int, int, int, int]:
        name = p.name.lower()
        s1 = 1 if participant_id.lower() in name else 0
        s2 = 1 if "sweep" in name else 0
        s3 = -len(name)
        s4 = -len(p.parts)
        return (s1, s2, s3, s4)

    return sorted(cands, key=score, reverse=True)[0]


@dataclass
class SweepCacheItem:
    path: Path
    sr: int
    y: np.ndarray


class SweepAudioCache:
    def __init__(self, max_items: int = 2):
        self.max_items = max_items
        self._cache: Dict[str, SweepCacheItem] = {}

    def get(self, wav_path: Path) -> SweepCacheItem:
        key = str(wav_path)
        if key in self._cache:
            return self._cache[key]
        y, sr = sf.read(str(wav_path), always_2d=False)
        y = np.asarray(y, dtype=np.float32)
        if y.ndim == 2:
            y = y.mean(axis=1)
        item = SweepCacheItem(path=wav_path, sr=int(sr), y=y)
        if len(self._cache) >= self.max_items:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = item
        return item


def compute_envelope_metrics(x: np.ndarray, sr: int, *, mod_band: Tuple[float, float], peak_min_dist_s: float) -> Dict[str, float]:
    if x.size == 0:
        return {"audio_rms": np.nan, "audio_env_peak_rate_hz": np.nan, "audio_mod_dom_hz": np.nan, "audio_mod_dom_power": np.nan}

    rms = float(np.sqrt(np.mean(x**2)))

    env = np.abs(hilbert(x))
    win = max(1, int(round(0.02 * sr)))  # 20 ms smoothing
    kernel = np.ones(win, dtype=np.float32) / float(win)
    env_s = np.convolve(env, kernel, mode="same")

    min_dist = max(1, int(round(peak_min_dist_s * sr)))
    prom = 0.5 * np.median(env_s)
    peaks, _ = find_peaks(env_s, distance=min_dist, prominence=prom)
    dur_s = x.size / float(sr)
    peak_rate = float(len(peaks) / dur_s) if dur_s > 0 else np.nan

    env_ds = env_s
    fs_ds = sr
    target_fs = 200
    if sr > target_fs * 2:
        env_ds = resample_poly(env_s, up=target_fs, down=sr).astype(np.float32)
        fs_ds = target_fs

    f, pxx = welch(env_ds, fs=fs_ds, nperseg=min(len(env_ds), int(fs_ds * 4)))
    lo, hi = mod_band
    m = (f >= lo) & (f <= hi)
    if not np.any(m):
        dom_f = np.nan
        dom_p = np.nan
    else:
        idx = int(np.argmax(pxx[m]))
        dom_f = float(f[m][idx])
        dom_p = float(pxx[m][idx])

    return {"audio_rms": rms, "audio_env_peak_rate_hz": peak_rate, "audio_mod_dom_hz": dom_f, "audio_mod_dom_power": dom_p}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_root", required=True, type=str)
    ap.add_argument("--tables_dir", required=True, type=str)
    ap.add_argument("--out_dir", required=True, type=str)
    ap.add_argument("--fixed_window_s", default=6.0, type=float)
    ap.add_argument("--trim_edge_s", default=0.25, type=float)
    ap.add_argument("--cap_to_next", choices=["none", "onset", "cue", "both"], default="both")
    ap.add_argument("--min_analysis_s", default=2.0, type=float)
    ap.add_argument("--mod_band_lo_hz", default=2.0, type=float)
    ap.add_argument("--mod_band_hi_hz", default=10.0, type=float)
    ap.add_argument("--peak_min_dist_s", default=0.08, type=float)
    ap.add_argument("--max_cache_items", default=2, type=int)
    args = ap.parse_args()

    dataset_root = Path(args.dataset_root)
    tables_dir = Path(args.tables_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    align_path = tables_dir / "ema_trial_alignment.csv"
    if not align_path.exists():
        print(f"[ERROR] Missing {align_path}", file=sys.stderr)
        return 2

    align = pd.read_csv(align_path)

    sweep_col = pick_col(align, ["sweep_number", "sweep"], required=False)
    cue_col = pick_col(
        align,
        ["cue_time_in_sweep_ema_s", "cue_time_sweep_sec", "cue_time_in_sweep_sec", "cue_time_in_sweep_s"],
        required=False,
    )
    onset_col = pick_col(
        align,
        ["move_onset_in_sweep_ema_s", "trial_start_in_sweep_sec", "trial_start_in_sweep_ema_s", "trial_start_sweep_sec", "trial_start_in_sweep_s"],
    )

    key_cols = choose_key_cols(align)

    sort_cols = ["participant_id"]
    if sweep_col is not None:
        sort_cols.append(sweep_col)
    sort_cols.append(onset_col)

    a = align.sort_values(sort_cols).copy()
    gb_cols = ["participant_id"]
    if sweep_col is not None:
        gb_cols.append(sweep_col)

    a["next_onset_sweep_s"] = a.groupby(gb_cols)[onset_col].shift(-1)
    a["next_cue_sweep_s"] = a.groupby(gb_cols)[cue_col].shift(-1) if cue_col is not None else np.nan

    a["seg_start_s"] = a[onset_col] + float(args.trim_edge_s)
    a["seg_end_s"] = a["seg_start_s"] + float(args.fixed_window_s)

    if args.cap_to_next in ("onset", "both"):
        a["seg_end_s"] = np.where(
            a["next_onset_sweep_s"].notna(),
            np.minimum(a["seg_end_s"], a["next_onset_sweep_s"] - float(args.trim_edge_s)),
            a["seg_end_s"],
        )
    if args.cap_to_next in ("cue", "both") and cue_col is not None:
        a["seg_end_s"] = np.where(
            a["next_cue_sweep_s"].notna(),
            np.minimum(a["seg_end_s"], a["next_cue_sweep_s"] - float(args.trim_edge_s)),
            a["seg_end_s"],
        )

    a["seg_len_s"] = a["seg_end_s"] - a["seg_start_s"]
    a["seg_ok"] = a["seg_len_s"] >= float(args.min_analysis_s)

    out_rows = []
    file_cache: Dict[str, List[Path]] = {}
    sweep_cache = SweepAudioCache(max_items=args.max_cache_items)

    group_cols = ["participant_id"]
    if sweep_col is not None:
        group_cols.append(sweep_col)

    for gkey, g in a.groupby(group_cols, sort=False):
        if isinstance(gkey, tuple):
            pid = str(gkey[0])
            sweep_no = int(gkey[1]) if sweep_col is not None else None
        else:
            pid = str(gkey)
            sweep_no = None

        audio_dir = find_audio_dir(dataset_root, pid)

        wav_path = None
        if sweep_col is not None and sweep_no is not None:
            wav_path = find_sweep_wav(audio_dir, pid, sweep_no, file_cache)

        sweep_item = None
        if wav_path is not None:
            try:
                sweep_item = sweep_cache.get(wav_path)
            except Exception:
                sweep_item = None

        for _, row in g.iterrows():
            row_out = {c: row[c] for c in key_cols if c in row.index}
            row_out["participant_id"] = pid
            if sweep_col is not None and sweep_col in row.index:
                row_out["sweep_number"] = int(row[sweep_col])

            for c in ["sequence", "rate", "block_num", "trial_in_block", "index", "trial_index"]:
                if c in row.index:
                    row_out[c] = row[c]

            row_out["seg_start_s"] = float(row["seg_start_s"])
            row_out["seg_end_s"] = float(row["seg_end_s"])
            row_out["seg_len_s"] = float(row["seg_len_s"])
            row_out["seg_ok"] = bool(row["seg_ok"])
            row_out["sweep_wav_path"] = str(wav_path) if wav_path is not None else ""
            row_out["sweep_wav_found"] = bool(wav_path is not None)

            feats = {"audio_rms": np.nan, "audio_env_peak_rate_hz": np.nan, "audio_mod_dom_hz": np.nan, "audio_mod_dom_power": np.nan}

            if row_out["seg_ok"] and sweep_item is not None:
                sr = sweep_item.sr
                y = sweep_item.y
                s0 = int(round(row_out["seg_start_s"] * sr))
                s1 = int(round(row_out["seg_end_s"] * sr))
                s0 = max(0, min(s0, y.size))
                s1 = max(0, min(s1, y.size))
                if s1 > s0:
                    x = y[s0:s1]
                    feats = compute_envelope_metrics(
                        x,
                        sr,
                        mod_band=(float(args.mod_band_lo_hz), float(args.mod_band_hi_hz)),
                        peak_min_dist_s=float(args.peak_min_dist_s),
                    )

            row_out.update(feats)
            out_rows.append(row_out)

    out_df = pd.DataFrame(out_rows)

    out_csv = out_dir / "audio_trial_envelope.csv"
    out_df.to_csv(out_csv, index=False)
    print(f"[DONE] Wrote {out_csv} (rows={len(out_df)})")

    summ = out_df.groupby("participant_id", as_index=False).agg(
        n_trials_total=("participant_id", "size"),
        n_seg_ok=("seg_ok", "sum"),
        n_sweep_wav_found=("sweep_wav_found", "sum"),
        audio_mod_dom_hz_median=("audio_mod_dom_hz", "median"),
        audio_env_peak_rate_hz_median=("audio_env_peak_rate_hz", "median"),
    )
    summ["missing_sweep_wav"] = summ["n_trials_total"] - summ["n_sweep_wav_found"]
    summ["missing_sweep_wav_rate"] = summ["missing_sweep_wav"] / summ["n_trials_total"].clip(lower=1)

    summ_csv = out_dir / "audio_summary_by_participant.csv"
    summ.to_csv(summ_csv, index=False)
    print(f"[DONE] Wrote {summ_csv}")

    n_missing = int((~out_df["sweep_wav_found"]).sum())
    if n_missing:
        print(f"[WARN] Missing sweep wav for {n_missing} trials. Check Data/<sub>/Audio/wav naming.")
    n_bad = int((~out_df["seg_ok"]).sum())
    if n_bad:
        print(f"[WARN] {n_bad} trials have seg_len_s < {args.min_analysis_s}. They remain in the CSV with NaNs.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
