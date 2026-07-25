#!/usr/bin/env python3
"""
run_ema_trial_kinematics.py

Purpose
-------
Compute EMA jaw/tongue kinematics per DDK trial using *EEG Status triggers* as the primary
segmentation/alignment mechanism.

Alignment strategy (publication-safe)
------------------------------------
1) Parse EEG Status channel:
   - TTL start/stop bits define EMA sweep boundaries in EEG time.
   - Task/event codes inside each sweep define trial onsets (stimulus codes) and (for habitual)
     go-cue onsets (code 9).

2) Pair TTL-defined sweeps to EMA sweep numbers using docs/session_index.csv
   (normal_block_1..9 and fast_block_1..6 -> sweep_number).

3) Map EEG time within sweep -> EMA time within sweep via a linear time-warp:
   t_ema = t_eeg * (duration_ema / duration_eeg)

   We estimate duration_ema from the sweep audio duration if available; otherwise from
   EMA sample count / default_ema_fs.

4) Compute kinematics from EMA directly inside trial windows.
   Cycle metrics are computed from jaw-opening cycles detected in EMA (no TextGrid needed).

Optional audio QC
-----------------
If --audio_qc is enabled and sweep audio exists, we compute simple energy/QC metrics
for each trial window (and optionally an envelope-based cross-correlation sanity check).

Outputs
-------
<out_dir>/tables/
  - ema_trial_alignment.csv : one row per trial (timing, indices, QC)
  - ema_trial_kinematics.csv : one row per trial (kinematics + merged praat/meta/anatomy if provided)
  - ema_cycle_kinematics.csv : one row per detected jaw cycle (cycle-level metrics)

<out_dir>/figures/
  - trial_*.png : per-trial diagnostic plots (first --plot_n trials)
  - summary_alignment_qc.png : summary QC plot (if audio_qc)

Notes
-----
- This script assumes the dataset folder structure from SWISSUbase.
- It only needs the per-trial acoustic metrics from praat_info_corpus_ema-eeg.csv for merging,
  not for timing. Timing comes from EEG triggers.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# Matplotlib: use non-interactive backend for batch runs (important on macOS/headless)
import matplotlib
matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

try:
    import mne  # noqa: E402
except Exception as e:  # pragma: no cover
    raise ImportError(
        "This script requires 'mne' to read BioSemi .bdf files.\n"
        "Install with: pip install mne"
    ) from e

try:
    from scipy.signal import butter, filtfilt, find_peaks  # noqa: E402
except Exception as e:  # pragma: no cover
    raise ImportError(
        "This script requires 'scipy' for filtering and peak detection.\n"
        "Install with: pip install scipy"
    ) from e

import wave


# ----------------------------
# Constants / dataset specifics
# ----------------------------

# EEG Status bit masks (BioSemi Status channel)
MASK_TTL_START = 1 << 6   # 64
MASK_TTL_STOP  = 1 << 7   # 128
MASK_CORE      = (1 << 6) - 1  # 63 (bits 0..5)

# DDK stimulus codes (habitual + fast)
HABITUAL_CODES = set(range(11, 20))     # 11..19 (includes voiced)
FAST_CODES     = set(range(31, 37))     # 31..36
GO_CUE_CODE    = 9

# Channels -> sensor labels (from paper)
# (This is stable across subjects in your dataset, and avoids reliance on columns.txt.)
SENSOR_CHANNELS: Dict[str, int] = {
    "BP_L": 1,
    "BP_M": 2,
    "BP_R": 3,
    "REF_L": 4,
    "REF_R": 5,
    "REF_N": 6,
    "UL": 16,
    "LL": 17,
    "LC": 18,
    "UI": 19,
    "LI": 20,
    "TD": 21,
    "TB": 22,
    "TT": 23,
    "PT": 24,
}

DEFAULT_EMA_FS_HZ = 200.0  # fallback; we try to estimate per-sweep from sweep audio duration
TRIALS_PER_BLOCK  = 20


# ----------------------------
# Utilities
# ----------------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def zfill_sub(pid: str) -> str:
    """Normalize participant id to 'sub-XYZ'."""
    pid = str(pid)
    if pid.startswith("sub-"):
        return "sub-" + pid.split("-", 1)[1].zfill(3)
    m = re.fullmatch(r"(\d+)", pid.strip())
    if m:
        return "sub-" + m.group(1).zfill(3)
    return pid

def read_wav_duration_sec(wav_path: Path) -> Optional[float]:
    """Read WAV duration without loading samples. Returns None if unreadable."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            n_frames = wf.getnframes()
            fs = wf.getframerate()
            if fs <= 0:
                return None
            return float(n_frames) / float(fs)
    except Exception:
        return None

def robust_numeric(x) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")

def deriv(x: np.ndarray, fs: float, axis: int = 0) -> np.ndarray:
    """Time-derivative using numpy.gradient along axis. Works for 1D or 2D arrays."""
    if fs <= 0:
        raise ValueError("fs must be positive")
    return np.gradient(x, 1.0 / fs, axis=axis).astype(np.float32)

def vecnorm(x: np.ndarray, axis: int = -1) -> np.ndarray:
    return np.linalg.norm(x, axis=axis)

def butter_lowpass(x: np.ndarray, fs: float, cutoff_hz: float, order: int = 4) -> np.ndarray:
    if fs <= 0:
        return x
    nyq = 0.5 * fs
    cutoff = min(max(cutoff_hz, 0.1), nyq * 0.99)
    b, a = butter(order, cutoff / nyq, btype="low")
    # filtfilt expects finite values
    x2 = np.asarray(x, dtype=float)
    if not np.isfinite(x2).all():
        # simple fill
        x2 = pd.Series(x2).interpolate(limit_direction="both").to_numpy()
    return filtfilt(b, a, x2)

def safe_int(x, default: int = -1) -> int:
    try:
        return int(x)
    except Exception:
        return default


# ----------------------------
# Praat CSV parsing (acoustic metrics)
# ----------------------------

_PRAAT_RE = re.compile(
    r"^(?:sub-)?(?P<num>\d+)-(?P<seq>[A-Za-z]+)-(?P<rate>[A-Za-z]+)-(?P<idx>\d+)$"
)

def parse_praat_csv(praat_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(praat_csv)
    if "soundname" not in df.columns:
        raise ValueError("praat_csv must contain a 'soundname' column.")
    m = df["soundname"].astype(str).str.extract(_PRAAT_RE)
    if m.isna().all().all():
        raise ValueError(
            "Could not parse 'soundname' in praat_csv. Expected pattern like "
            "'055-bibibi-normal-10' or 'sub-055-bibibi-normal-10'."
        )
    out = df.copy()
    out["participant_id"] = "sub-" + m["num"].astype(str).str.zfill(3)
    out["sequence"] = m["seq"].astype(str).str.lower()
    out["rate"] = m["rate"].astype(str).str.lower()
    out["index"] = pd.to_numeric(m["idx"], errors="coerce").astype("Int64")
    return out


# ----------------------------
# docs tables: event_codes, session_index, metadata, anatomy
# ----------------------------

def load_event_code_map(event_codes_csv: Path) -> Dict[int, Dict[str, str]]:
    """
    Returns mapping:
      code -> {"label":..., "sequence":..., "rate":..., "kind": "stim"|"go"|"other"}
    """
    ev = pd.read_csv(event_codes_csv)
    if not {"code", "label"}.issubset(set(ev.columns)):
        raise ValueError("event_codes.csv must have columns: code,label")
    mapping: Dict[int, Dict[str, str]] = {}
    for _, row in ev.iterrows():
        code = safe_int(row["code"])
        label = str(row["label"])
        seq = None
        rate = None
        kind = "other"
        # Examples:
        #   AMR_habitual_kukuku
        #   SMR_fast_pitaku
        #   go
        l = label.lower()
        if l == "go" or l.endswith("_go"):
            kind = "go"
            seq = None
            rate = None
        else:
            # parse rate
            if "habitual" in l:
                rate = "normal"
            elif "fast" in l:
                rate = "fast"
            # parse sequence at end
            # take last underscore group
            parts = l.split("_")
            if len(parts) >= 2:
                seq = parts[-1]
            # stimulus codes
            if (code in HABITUAL_CODES) or (code in FAST_CODES):
                kind = "stim"
        mapping[code] = {"label": label, "sequence": (seq or ""), "rate": (rate or ""), "kind": kind}
    return mapping

def load_session_index(session_index_csv: Path, participant_id: str) -> pd.DataFrame:
    si = pd.read_csv(session_index_csv)
    if "participant_id" not in si.columns:
        raise ValueError("session_index.csv must contain participant_id column")
    si["participant_id"] = si["participant_id"].astype(str).map(zfill_sub)
    si = si[si["participant_id"] == participant_id].copy()
    if si.empty:
        raise ValueError(f"No session_index rows for {participant_id}")
    return si

def ddk_targets_from_session_index(si: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (normal_blocks_df, fast_blocks_df) with columns: block_idx, sweep_number."""
    if "task" not in si.columns or "sweep_number" not in si.columns:
        raise ValueError("session_index needs columns task and sweep_number")
    # task example: normal_block_1
    normal = si[si["task"].astype(str).str.match(r"^normal_block_\d+$", case=False)].copy()
    fast = si[si["task"].astype(str).str.match(r"^fast_block_\d+$", case=False)].copy()
    if normal.empty and fast.empty:
        return normal, fast
    def block_idx(task: str) -> int:
        m = re.search(r"(\d+)$", str(task))
        return int(m.group(1)) if m else -1
    for df in (normal, fast):
        df["block_idx"] = df["task"].astype(str).map(block_idx)
        df["sweep_number"] = pd.to_numeric(df["sweep_number"], errors="coerce").astype("Int64")
        df.dropna(subset=["sweep_number"], inplace=True)
        df.sort_values(["block_idx"], inplace=True)
    return normal, fast

def load_metadata(metadata_csv: Path) -> pd.DataFrame:
    md = pd.read_csv(metadata_csv)
    if "participant_id" in md.columns:
        md["participant_id"] = md["participant_id"].astype(str).map(zfill_sub)
    return md

def load_anatomy_wide(anatomy_csv: Path) -> pd.DataFrame:
    """
    anatomy_measurements.csv columns (your dataset):
      participant_id, measure, side, value_mm, value_in, value_kg, value_lb
    We pivot value_mm and keep side where present. Adds mean across L/R for symmetric measures.
    """
    a = pd.read_csv(anatomy_csv)
    if not {"participant_id", "measure"}.issubset(a.columns):
        raise ValueError("anatomy_measurements.csv must have participant_id and measure columns")
    a["participant_id"] = a["participant_id"].astype(str).map(zfill_sub)
    a["measure"] = a["measure"].astype(str)
    # choose value_mm if present, otherwise first numeric column
    value_col = None
    for c in ["value_mm", "value_in", "value_kg", "value_lb"]:
        if c in a.columns:
            value_col = c
            break
    if value_col is None:
        raise ValueError("anatomy_measurements.csv must contain a value_* column (e.g., value_mm).")
    a[value_col] = pd.to_numeric(a[value_col], errors="coerce")
    if "side" in a.columns:
        a["side"] = a["side"].astype(str).replace({"nan": "", "None": ""})
        a["key"] = np.where(a["side"].astype(str).str.len() > 0, a["measure"] + "_" + a["side"], a["measure"])
    else:
        a["key"] = a["measure"]
    wide = a.pivot_table(index="participant_id", columns="key", values=value_col, aggfunc="mean").reset_index()
    # add L/R means for measures where both exist
    cols = list(wide.columns)
    base_measures = set()
    for c in cols:
        if c.endswith("_L") or c.endswith("_R"):
            base_measures.add(c[:-2])
    for base in sorted(base_measures):
        L = base + "_L"
        R = base + "_R"
        if L in wide.columns and R in wide.columns:
            wide[base + "_mean"] = wide[[L, R]].mean(axis=1)
    return wide


# ----------------------------
# EEG decoding (Status channel) -> TTL sweeps and events
# ----------------------------

@dataclass
class TTLSweep:
    eeg_start_sample: int
    eeg_stop_sample: int
    kind: str = "unknown"           # 'normal'|'fast'|'unknown'
    ema_sweep_number: Optional[int] = None
    block_idx: Optional[int] = None # block idx within kind from session_index (1..9 or 1..6)

def _find_status_channel(raw) -> str:
    # Common BioSemi names: 'Status' or 'STI 014'
    for cand in ["Status", "STI 014", "STATUS", "status"]:
        if cand in raw.ch_names:
            return cand
    # fallback: look for a channel with integer-like values name containing 'status' or 'sti'
    for name in raw.ch_names:
        ln = name.lower()
        if "status" in ln or "sti" in ln:
            return name
    raise ValueError(f"Could not find a Status channel in BDF. Channels: {raw.ch_names[:20]}...")

def decode_ttl_sweeps_and_events(bdf_path: Path) -> Tuple[float, List[TTLSweep], List[Dict]]:
    """
    Returns: (fs_eeg, sweeps, events)
    events are dicts with keys: type ('task'), sample, core_code
    """
    raw = mne.io.read_raw_bdf(str(bdf_path), preload=True, verbose="ERROR")
    fs_eeg = float(raw.info["sfreq"])
    status_name = _find_status_channel(raw)
    status = raw.get_data(picks=[status_name]).squeeze()
    # BioSemi Status channel is stored as float; convert to int
    status = np.asarray(np.round(status), dtype=np.int64)

    start_edges = np.where(np.diff((status & MASK_TTL_START) > 0, prepend=False))[0]
    stop_edges  = np.where(np.diff((status & MASK_TTL_STOP)  > 0, prepend=False))[0]
    # keep rising edges only: where previous is False and current is True
    start_edges = start_edges[(status[start_edges] & MASK_TTL_START) > 0]
    stop_edges  = stop_edges[(status[stop_edges]  & MASK_TTL_STOP)  > 0]

    n = min(len(start_edges), len(stop_edges))
    start_edges = start_edges[:n]
    stop_edges = stop_edges[:n]

    sweeps: List[TTLSweep] = [TTLSweep(int(s0), int(s1)) for s0, s1 in zip(start_edges, stop_edges)]

    core = status & MASK_CORE
    # detect any change in core code
    chg = np.where(np.diff(core, prepend=core[0]))[0]
    events: List[Dict] = []
    for i in chg:
        c = int(core[i])
        if c != 0:
            events.append({"type": "task", "sample": int(i), "core_code": c})
    return fs_eeg, sweeps, events

def classify_sweep_kind(sw: TTLSweep, events: List[Dict]) -> str:
    """Classify a TTL sweep as normal/fast based on stimulus codes within sweep window."""
    codes = [e["core_code"] for e in events
             if e["type"] == "task" and sw.eeg_start_sample <= e["sample"] < sw.eeg_stop_sample]
    if any(c in FAST_CODES for c in codes):
        return "fast"
    if any(c in HABITUAL_CODES for c in codes):
        return "normal"
    return "unknown"

def pair_sweeps_to_session_index(
    sweeps: List[TTLSweep],
    events: List[Dict],
    normal_blocks: pd.DataFrame,
    fast_blocks: pd.DataFrame,
) -> List[TTLSweep]:
    """
    Assign ema_sweep_number and block_idx to each TTL sweep (normal/fast) by chronological order.

    We expect the number of TTL sweeps classified as normal/fast to match the number of
    normal/fast blocks in session_index. If mismatch, we warn and pair by min-count.
    """
    # classify
    for sw in sweeps:
        sw.kind = classify_sweep_kind(sw, events)

    sweeps_normal = [sw for sw in sweeps if sw.kind == "normal"]
    sweeps_fast   = [sw for sw in sweeps if sw.kind == "fast"]

    sweeps_normal.sort(key=lambda s: s.eeg_start_sample)
    sweeps_fast.sort(key=lambda s: s.eeg_start_sample)

    normal_targets = [(int(r["block_idx"]), int(r["sweep_number"])) for _, r in normal_blocks.iterrows()]
    fast_targets   = [(int(r["block_idx"]), int(r["sweep_number"])) for _, r in fast_blocks.iterrows()]

    if len(sweeps_normal) != len(normal_targets):
        warnings.warn(
            f"[WARN] EEG TTL normal sweep count ({len(sweeps_normal)}) != session_index normal blocks ({len(normal_targets)}). "
            f"Pairing by chronological order up to min count."
        )
    if len(sweeps_fast) != len(fast_targets):
        warnings.warn(
            f"[WARN] EEG TTL fast sweep count ({len(sweeps_fast)}) != session_index fast blocks ({len(fast_targets)}). "
            f"Pairing by chronological order up to min count."
        )

    for sw, (bidx, sn) in zip(sweeps_normal, normal_targets):
        sw.block_idx = bidx
        sw.ema_sweep_number = sn
    for sw, (bidx, sn) in zip(sweeps_fast, fast_targets):
        sw.block_idx = bidx
        sw.ema_sweep_number = sn

    # return only mapped DDK sweeps
    mapped = [sw for sw in sweeps if sw.ema_sweep_number is not None]
    return mapped


# ----------------------------
# EMA reading
# ----------------------------

_EMA_COL_RE = re.compile(r"^Ch(?P<ch>\d+)_(?P<feat>[A-Za-z]+)$")

def read_ema_sweep_txt(txt_path: Path) -> pd.DataFrame:
    """
    Read EMA sweep .txt (tab-separated) and canonicalize columns.
    Canonical columns: Ch{n}_{x|y|z|phi|theta|rms|extra}
    """
    df = pd.read_csv(txt_path, sep=r"\t", engine="python")
    rename = {}
    for c in df.columns:
        mc = _EMA_COL_RE.match(str(c).strip())
        if not mc:
            continue
        ch = int(mc.group("ch"))
        feat = mc.group("feat").lower()
        # normalize some common variants
        if feat == "rms":
            feat = "rms"
        if feat == "extra":
            feat = "extra"
        if feat in {"x", "y", "z", "phi", "theta", "rms", "extra"}:
            rename[c] = f"Ch{ch}_{feat}"
    df = df.rename(columns=rename)
    return df

def extract_channel_xyz(df: pd.DataFrame, ch: int) -> np.ndarray:
    cols = [f"Ch{ch}_x", f"Ch{ch}_y", f"Ch{ch}_z"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing EMA columns for channel {ch}: {missing}")
    arr = df[cols].to_numpy(dtype=np.float32)
    return arr


# ----------------------------
# Trial building from EEG events
# ----------------------------

@dataclass
class TrialDef:
    participant_id: str
    rate: str
    sequence: str
    index: int  # within-rate index from block_idx & trial_in_block (should match praat 'index')
    block_idx: int
    trial_in_block: int
    sweep_number: int

    eeg_stim_sample: int
    eeg_go_sample: Optional[int]
    eeg_sweep_start: int
    eeg_sweep_stop: int

def _sequence_from_code(code: int, event_map: Dict[int, Dict[str, str]]) -> str:
    d = event_map.get(code, {})
    return (d.get("sequence") or "").lower()

def _rate_from_code(code: int, event_map: Dict[int, Dict[str, str]]) -> str:
    d = event_map.get(code, {})
    return (d.get("rate") or "").lower()

def build_trials_for_sweep(
    participant_id: str,
    sw: TTLSweep,
    events: List[Dict],
    event_map: Dict[int, Dict[str, str]],
) -> List[TrialDef]:
    if sw.ema_sweep_number is None or sw.block_idx is None:
        return []
    sweep_number = int(sw.ema_sweep_number)
    block_idx = int(sw.block_idx)
    kind = sw.kind  # 'normal'|'fast'
    rate = "normal" if kind == "normal" else "fast" if kind == "fast" else "unknown"

    stim_codes = HABITUAL_CODES if rate == "normal" else FAST_CODES if rate == "fast" else set()

    # events in sweep
    ev_in = [e for e in events if sw.eeg_start_sample <= e["sample"] < sw.eeg_stop_sample]
    stim = [e for e in ev_in if e["type"] == "task" and int(e["core_code"]) in stim_codes]
    stim.sort(key=lambda e: e["sample"])

    go = [e for e in ev_in if e["type"] == "task" and int(e["core_code"]) == GO_CUE_CODE]
    go.sort(key=lambda e: e["sample"])

    trials: List[TrialDef] = []
    for j, se in enumerate(stim):
        stim_sample = int(se["sample"])
        stim_code = int(se["core_code"])
        seq = _sequence_from_code(stim_code, event_map)
        # assign go-cue for habitual: first go after stim but before next stim
        go_sample = None
        if rate == "normal" and len(go) > 0:
            next_stim_sample = stim[j + 1]["sample"] if (j + 1) < len(stim) else sw.eeg_stop_sample
            # find first go between stim and next_stim
            candidates = [g["sample"] for g in go if stim_sample < g["sample"] < next_stim_sample]
            if candidates:
                go_sample = int(candidates[0])

        trial_in_block = j + 1
        # within-rate index: (block_idx-1)*20 + trial_in_block
        idx_within_rate = (block_idx - 1) * TRIALS_PER_BLOCK + trial_in_block

        trials.append(
            TrialDef(
                participant_id=participant_id,
                rate=rate,
                sequence=seq,
                index=int(idx_within_rate),
                block_idx=int(block_idx),
                trial_in_block=int(trial_in_block),
                sweep_number=int(sweep_number),
                eeg_stim_sample=int(stim_sample),
                eeg_go_sample=go_sample,
                eeg_sweep_start=int(sw.eeg_start_sample),
                eeg_sweep_stop=int(sw.eeg_stop_sample),
            )
        )
    return trials

def build_all_trials(
    participant_id: str,
    mapped_sweeps: List[TTLSweep],
    events: List[Dict],
    event_map: Dict[int, Dict[str, str]],
) -> List[TrialDef]:
    trials: List[TrialDef] = []
    mapped_sweeps_sorted = sorted(mapped_sweeps, key=lambda s: (int(s.ema_sweep_number or 999999), s.eeg_start_sample))
    for sw in mapped_sweeps_sorted:
        trials.extend(build_trials_for_sweep(participant_id, sw, events, event_map))
    return trials


# ----------------------------
# Kinematics computation
# ----------------------------

@dataclass
class KinematicsResult:
    # trial window
    trial_start_sec: float
    trial_end_sec: float
    ema_fs_hz: float

    # movement window
    mov_onset_sec: float
    mov_offset_sec: float

    # jaw / tongue summary metrics
    jaw_open_mean_mm: float
    jaw_open_p2p_mm: float
    jaw_speed_peak_mm_s: float

    tt_speed_peak_mm_s: float
    td_speed_peak_mm_s: float

    cycle_count: int
    cycle_rate_hz: float
    cycle_dur_mean_s: float
    cycle_dur_cv: float

def compute_trial_kinematics(
    ema_df: pd.DataFrame,
    fs_ema: float,
    t0: float,
    t1: float,
) -> Tuple[KinematicsResult, pd.DataFrame]:
    """
    Compute trial-level kinematics and cycle table inside [t0, t1] (seconds within sweep).
    Cycle detection is based on jaw-opening (UI-LI distance).
    Returns: (trial_summary, cycle_df)
    """
    n = len(ema_df)
    if n < 5:
        raise ValueError("EMA sweep too short")

    # convert to indices
    i0 = max(0, min(n - 2, int(round(t0 * fs_ema))))
    i1 = max(i0 + 2, min(n - 1, int(round(t1 * fs_ema))))
    seg = ema_df.iloc[i0:i1].copy()
    t = (np.arange(len(seg), dtype=np.float32) / fs_ema) + (i0 / fs_ema)

    # positions relative to UI (remove rigid head translation)
    UI = extract_channel_xyz(seg, SENSOR_CHANNELS["UI"])
    LI = extract_channel_xyz(seg, SENSOR_CHANNELS["LI"])
    TT = extract_channel_xyz(seg, SENSOR_CHANNELS["TT"])
    TD = extract_channel_xyz(seg, SENSOR_CHANNELS["TD"])

    LI_rel = LI - UI
    TT_rel = TT - UI
    TD_rel = TD - UI

    jaw_open = vecnorm(LI_rel, axis=1)  # mm (assuming EMA coords in mm)
    jaw_open_f = butter_lowpass(jaw_open, fs_ema, cutoff_hz=12.0, order=4)

    LI_vel = deriv(LI_rel, fs_ema, axis=0)
    TT_vel = deriv(TT_rel, fs_ema, axis=0)
    TD_vel = deriv(TD_rel, fs_ema, axis=0)
    jaw_speed = vecnorm(LI_vel, axis=1)
    tt_speed = vecnorm(TT_vel, axis=1)
    td_speed = vecnorm(TD_vel, axis=1)

    # movement onset/offset via jaw speed threshold
    sp = jaw_speed
    sp_peak = float(np.nanmax(sp)) if len(sp) else float("nan")
    thr = max(5.0, 0.10 * sp_peak) if np.isfinite(sp_peak) else 5.0
    above = np.where(sp > thr)[0]
    if len(above) >= int(0.10 * fs_ema):  # at least 100ms worth
        onset_i = int(above[0])
        offset_i = int(above[-1])
    else:
        onset_i = 0
        offset_i = len(seg) - 1

    mov_onset_sec = float(t[onset_i] - t[0])
    mov_offset_sec = float(t[offset_i] - t[0])

    # cycle detection on jaw_open_f inside movement window
    jaw_cycle = jaw_open_f[onset_i:offset_i + 1]
    t_cycle = t[onset_i:offset_i + 1]

    cycle_rows = []
    cycle_count = 0
    cycle_rate_hz = float("nan")
    cycle_dur_mean_s = float("nan")
    cycle_dur_cv = float("nan")

    if len(jaw_cycle) >= int(0.40 * fs_ema):  # need at least 400ms segment
        # detect minima (closing points)
        min_dist = max(8, int(round(0.08 * fs_ema)))  # >=80ms between cycles
        # prominence based on robust range
        rng = float(np.nanpercentile(jaw_cycle, 95) - np.nanpercentile(jaw_cycle, 5))
        prom = max(0.3, 0.10 * rng) if np.isfinite(rng) else 0.3
        mins, _ = find_peaks(-jaw_cycle, distance=min_dist, prominence=prom)

        if len(mins) >= 2:
            # build cycles between consecutive minima
            for k in range(len(mins) - 1):
                a = int(mins[k])
                b = int(mins[k + 1])
                if b <= a + 2:
                    continue
                seg_vals = jaw_cycle[a:b + 1]
                peak_i = int(np.argmax(seg_vals))
                peak_val = float(seg_vals[peak_i])
                trough_val = float(np.min(seg_vals))
                amp = peak_val - trough_val
                dur = float((b - a) / fs_ema)
                cycle_rows.append({
                    "cycle_index": k + 1,
                    "cycle_start_sec": float(t_cycle[a]),
                    "cycle_end_sec": float(t_cycle[b]),
                    "cycle_dur_sec": dur,
                    "jaw_open_amp_mm": float(amp),
                    "jaw_open_peak_mm": peak_val,
                    "jaw_open_trough_mm": trough_val,
                    "jaw_speed_peak_mm_s": float(np.max(sp[onset_i + a:onset_i + b + 1])),
                    "tt_speed_peak_mm_s": float(np.max(tt_speed[onset_i + a:onset_i + b + 1])),
                    "td_speed_peak_mm_s": float(np.max(td_speed[onset_i + a:onset_i + b + 1])),
                })

            if cycle_rows:
                cycle_df = pd.DataFrame(cycle_rows)
                cycle_count = len(cycle_df)
                durs = cycle_df["cycle_dur_sec"].to_numpy(float)
                cycle_dur_mean_s = float(np.nanmean(durs))
                cycle_dur_cv = float(np.nanstd(durs, ddof=1) / cycle_dur_mean_s) if cycle_count >= 2 and cycle_dur_mean_s > 0 else float("nan")
                cycle_rate_hz = float(1.0 / cycle_dur_mean_s) if cycle_dur_mean_s > 0 else float("nan")
        else:
            cycle_df = pd.DataFrame(columns=[
                "cycle_index","cycle_start_sec","cycle_end_sec","cycle_dur_sec","jaw_open_amp_mm",
                "jaw_open_peak_mm","jaw_open_trough_mm","jaw_speed_peak_mm_s","tt_speed_peak_mm_s","td_speed_peak_mm_s"
            ])
    else:
        cycle_df = pd.DataFrame(columns=[
            "cycle_index","cycle_start_sec","cycle_end_sec","cycle_dur_sec","jaw_open_amp_mm",
            "jaw_open_peak_mm","jaw_open_trough_mm","jaw_speed_peak_mm_s","tt_speed_peak_mm_s","td_speed_peak_mm_s"
        ])

    res = KinematicsResult(
        trial_start_sec=float(t0),
        trial_end_sec=float(t1),
        ema_fs_hz=float(fs_ema),
        mov_onset_sec=float(mov_onset_sec),
        mov_offset_sec=float(mov_offset_sec),
        jaw_open_mean_mm=float(np.nanmean(jaw_open_f)),
        jaw_open_p2p_mm=float(np.nanpercentile(jaw_open_f, 95) - np.nanpercentile(jaw_open_f, 5)),
        jaw_speed_peak_mm_s=float(np.nanmax(jaw_speed)),
        tt_speed_peak_mm_s=float(np.nanmax(tt_speed)),
        td_speed_peak_mm_s=float(np.nanmax(td_speed)),
        cycle_count=int(cycle_count),
        cycle_rate_hz=float(cycle_rate_hz),
        cycle_dur_mean_s=float(cycle_dur_mean_s),
        cycle_dur_cv=float(cycle_dur_cv),
    )
    return res, cycle_df


# ----------------------------
# Plotting
# ----------------------------

def plot_trial(
    fig_path: Path,
    t_rel: np.ndarray,
    jaw_open: np.ndarray,
    jaw_speed: np.ndarray,
    tt_speed: np.ndarray,
    title: str,
    vlines: List[Tuple[float, str]],
    cycles: Optional[pd.DataFrame] = None,
) -> None:
    plt.figure(figsize=(12, 7))
    ax1 = plt.gca()
    ax1.plot(t_rel, jaw_open, label="Jaw opening (UI–LI dist)", linewidth=1.6)
    ax1.set_xlabel("Time relative to trial start (s)")
    ax1.set_ylabel("Jaw opening (mm)")
    ax1.grid(True, alpha=0.25)

    # second axis for speeds
    ax2 = ax1.twinx()
    ax2.plot(t_rel, jaw_speed, label="Jaw speed", alpha=0.6)
    ax2.plot(t_rel, tt_speed, label="Tongue tip speed", alpha=0.6)
    ax2.set_ylabel("Speed (mm/s)")

    # vertical lines
    for x, lab in vlines:
        ax1.axvline(x, linestyle="--", alpha=0.6)
        ax1.text(x, ax1.get_ylim()[1], " " + lab, rotation=90, va="top", ha="left", alpha=0.8)

    # cycles
    if cycles is not None and len(cycles) > 0:
        for _, r in cycles.iterrows():
            xs = float(r["cycle_start_sec"]) - float(cycles["cycle_start_sec"].min())
            xe = float(r["cycle_end_sec"]) - float(cycles["cycle_start_sec"].min())
            ax1.axvspan(xs, xe, alpha=0.08)

    # legends: combine
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    plt.title(title)
    plt.tight_layout()
    plt.savefig(fig_path, dpi=200)
    plt.close()


# ----------------------------
# Main pipeline
# ----------------------------

def collect_participants(dataset_root: Path, participants_arg: str) -> List[str]:
    if participants_arg.strip().lower() in {"all", "*"}:
        pids = sorted([p.name for p in dataset_root.glob("sub-*") if p.is_dir()])
        return pids
    parts = []
    for tok in re.split(r"[,\s]+", participants_arg.strip()):
        if tok:
            parts.append(zfill_sub(tok))
    return parts

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_root", type=str, required=True, help="Path to dataset root (contains sub-*/ and docs/).")
    ap.add_argument("--out_dir", type=str, required=True, help="Output directory.")
    ap.add_argument("--participants", type=str, default="all", help="Comma/space-separated list (e.g., 'sub-055 sub-105') or 'all'.")
    ap.add_argument("--praat_csv", type=str, default="", help="Path to praat_info_corpus_ema-eeg.csv (optional).")
    ap.add_argument("--exclude_nsyll0", action="store_true", help="If praat_csv is provided: drop trials where nsyll==0.")
    ap.add_argument("--max_trials", type=int, default=0, help="Process at most N trials per participant (0=all).")
    ap.add_argument("--plot_n", type=int, default=0, help="Save plots for first N processed trials per participant.")
    ap.add_argument("--audio_qc", action="store_true", help="Compute simple sweep-audio energy QC per trial (if sweep wav exists).")
    ap.add_argument("--default_ema_fs", type=float, default=DEFAULT_EMA_FS_HZ, help="Fallback EMA fs if sweep wav missing.")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    args = ap.parse_args()

    dataset_root = Path(args.dataset_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    tables_dir = out_dir / "tables"
    figs_dir = out_dir / "figures"
    ensure_dir(tables_dir)
    ensure_dir(figs_dir)

    # docs
    docs_dir = dataset_root / "docs"
    event_codes_csv = docs_dir / "event_codes.csv"
    session_index_csv = docs_dir / "session_index.csv"
    metadata_csv = docs_dir / "metadata.csv"
    anatomy_csv = docs_dir / "anatomy_measurements.csv"

    if not event_codes_csv.exists():
        raise FileNotFoundError(f"Missing {event_codes_csv}")
    if not session_index_csv.exists():
        raise FileNotFoundError(f"Missing {session_index_csv}")
    if not metadata_csv.exists():
        warnings.warn(f"[WARN] missing {metadata_csv}; metadata columns will be absent.")
    if not anatomy_csv.exists():
        warnings.warn(f"[WARN] missing {anatomy_csv}; anatomy columns will be absent.")

    event_map = load_event_code_map(event_codes_csv)
    md = load_metadata(metadata_csv) if metadata_csv.exists() else pd.DataFrame()
    anat_wide = load_anatomy_wide(anatomy_csv) if anatomy_csv.exists() else pd.DataFrame()

    praat_df = None
    if args.praat_csv:
        praat_path = Path(args.praat_csv).expanduser().resolve()
        if not praat_path.exists():
            raise FileNotFoundError(f"praat_csv not found: {praat_path}")
        praat_df = parse_praat_csv(praat_path)

    participants = collect_participants(dataset_root, args.participants)

    all_align_rows = []
    all_trial_rows = []
    all_cycle_rows = []

    for pid in participants:
        subj_dir = dataset_root / pid
        if not subj_dir.exists():
            warnings.warn(f"[WARN] {pid}: directory not found; skipping")
            continue

        # EEG BDF
        bdf_path = subj_dir / "EEG" / "raw" / f"{pid}.bdf"
        if not bdf_path.exists():
            # try any .bdf in EEG/raw
            candidates = list((subj_dir / "EEG" / "raw").glob("*.bdf"))
            if candidates:
                bdf_path = candidates[0]
            else:
                warnings.warn(f"[WARN] {pid}: missing EEG .bdf; skipping")
                continue

        # session_index and DDK target sweeps
        try:
            si = load_session_index(session_index_csv, pid)
            normal_blocks, fast_blocks = ddk_targets_from_session_index(si)
        except Exception as e:
            warnings.warn(f"[WARN] {pid}: failed reading session_index: {e}; skipping")
            continue

        if normal_blocks.empty and fast_blocks.empty:
            warnings.warn(f"[WARN] {pid}: no DDK blocks found in session_index; skipping")
            continue

        # parse EEG status
        try:
            fs_eeg, ttl_sweeps, events = decode_ttl_sweeps_and_events(bdf_path)
        except Exception as e:
            warnings.warn(f"[WARN] {pid}: failed decoding EEG status: {e}; skipping")
            continue

        mapped_sweeps = pair_sweeps_to_session_index(ttl_sweeps, events, normal_blocks, fast_blocks)
        if not mapped_sweeps:
            warnings.warn(f"[WARN] {pid}: no mapped DDK TTL sweeps; skipping")
            continue

        # build trials
        trials = build_all_trials(pid, mapped_sweeps, events, event_map)

        # join to praat if provided
        if praat_df is not None:
            psub = praat_df[praat_df["participant_id"] == pid].copy()
            if psub.empty:
                warnings.warn(f"[WARN] {pid}: no trials found in praat_csv; skipping")
                continue
            # map by (rate,index)
            psub_keyed = psub.set_index(["rate", "index"], drop=False)
        else:
            psub_keyed = None

        # create a chronological list using EEG anchor sample
        trial_rows = []
        for tr in trials:
            # attach praat row
            praat_row = None
            if psub_keyed is not None:
                key = (tr.rate, tr.index)
                if key in psub_keyed.index:
                    praat_row = psub_keyed.loc[key]
                    # if duplicate index, loc returns DataFrame
                    if isinstance(praat_row, pd.DataFrame):
                        praat_row = praat_row.iloc[0]
                else:
                    praat_row = None

            # exclude nsyll==0
            if args.exclude_nsyll0 and praat_row is not None and "nsyll" in praat_row.index:
                try:
                    if float(praat_row["nsyll"]) == 0.0:
                        continue
                except Exception:
                    pass

            anchor_sample = tr.eeg_go_sample if tr.eeg_go_sample is not None else tr.eeg_stim_sample
            trial_rows.append((anchor_sample, tr, praat_row))

        if not trial_rows:
            warnings.warn(f"[WARN] {pid}: no trials after filtering; skipping")
            continue

        # sort by anchor sample (true recording order)
        trial_rows.sort(key=lambda x: x[0])

        if args.max_trials and args.max_trials > 0:
            trial_rows = trial_rows[: args.max_trials]

        print(f"[INFO] {pid}: processing {len(trial_rows)} trials")

        # cache EMA sweeps
        ema_cache: Dict[int, Tuple[pd.DataFrame, float, float]] = {}  # sweep -> (df, fs_ema, duration_sec)
        sweep_audio_cache: Dict[int, Optional[float]] = {}

        # for plots
        plotted = 0

        processed_trials = 0
        seq_mismatch = 0

        start_align_len = len(all_align_rows)
        for anchor_sample, tr, praat_row in trial_rows:
            sweep_no = tr.sweep_number
            # load EMA sweep
            if sweep_no not in ema_cache:
                sweep_txt = subj_dir / "EMA" / "pos" / f"{pid}-sweep-{sweep_no:04d}.txt"
                if not sweep_txt.exists():
                    warnings.warn(f"[WARN] {pid}: missing EMA sweep txt: {sweep_txt.name}; skipping trial idx={tr.index}")
                    continue
                try:
                    ema_df = read_ema_sweep_txt(sweep_txt)
                except Exception as e:
                    warnings.warn(f"[WARN] {pid}: failed reading {sweep_txt.name}: {e}; skipping trial idx={tr.index}")
                    continue

                # estimate EMA fs from sweep wav duration if possible
                sweep_wav = subj_dir / "Audio" / "wav" / f"{pid}-sweep-{sweep_no:04d}.wav"
                dur_wav = read_wav_duration_sec(sweep_wav) if sweep_wav.exists() else None
                if dur_wav is None:
                    fs_ema = float(args.default_ema_fs)
                    dur_sec = float(len(ema_df) / fs_ema)
                else:
                    dur_sec = float(dur_wav)
                    fs_ema = float(len(ema_df) / dur_sec) if dur_sec > 0 else float(args.default_ema_fs)

                ema_cache[sweep_no] = (ema_df, fs_ema, dur_sec)
                sweep_audio_cache[sweep_no] = dur_wav

            ema_df, fs_ema, dur_sec = ema_cache[sweep_no]

            # map EEG times within sweep -> EMA seconds
            eeg_dur_sec = float((tr.eeg_sweep_stop - tr.eeg_sweep_start) / fs_eeg) if fs_eeg > 0 else float("nan")
            if not np.isfinite(eeg_dur_sec) or eeg_dur_sec <= 0:
                warnings.warn(f"[WARN] {pid}: invalid EEG sweep duration for sweep {sweep_no}; skipping")
                continue
            scale = float(dur_sec / eeg_dur_sec) if dur_sec > 0 else 1.0

            stim_rel_eeg = float((tr.eeg_stim_sample - tr.eeg_sweep_start) / fs_eeg)
            go_rel_eeg = float((tr.eeg_go_sample - tr.eeg_sweep_start) / fs_eeg) if tr.eeg_go_sample is not None else float("nan")

            stim_sec = stim_rel_eeg * scale
            go_sec = go_rel_eeg * scale if np.isfinite(go_rel_eeg) else float("nan")
            anchor_sec = go_sec if np.isfinite(go_sec) else stim_sec

            # determine trial end using next trial anchor within same sweep
            # find next trial with same sweep in our sorted list
            # (we can do a cheap search in trial_rows because max_trials is small for smoke tests;
            #  for full runs it's still fine, but could be optimized if needed.)
            next_anchor_sec = None
            for a2, tr2, _ in trial_rows:
                if tr2.sweep_number != sweep_no:
                    continue
                a2_sample = tr2.eeg_go_sample if tr2.eeg_go_sample is not None else tr2.eeg_stim_sample
                if a2_sample > anchor_sample:
                    # map a2 to ema sec
                    a2_rel_eeg = float((a2_sample - tr.eeg_sweep_start) / fs_eeg)
                    next_anchor_sec = a2_rel_eeg * scale
                    break
            if next_anchor_sec is None:
                trial_end_sec = float(dur_sec - 0.05)
            else:
                trial_end_sec = float(max(anchor_sec + 0.20, next_anchor_sec - 0.05))

            trial_start_sec = float(max(0.0, anchor_sec - 0.05))  # tiny pre-pad
            trial_end_sec = float(min(trial_end_sec, dur_sec - 0.01))
            if trial_end_sec <= trial_start_sec + 0.10:
                warnings.warn(f"[WARN] {pid}: tiny trial window (start={trial_start_sec:.3f}, end={trial_end_sec:.3f}) idx={tr.index}; skipping")
                continue

            # praat mismatch check
            praat_seq = None
            praat_rate = None
            if praat_row is not None:
                praat_seq = str(praat_row.get("sequence", "")).lower()
                praat_rate = str(praat_row.get("rate", "")).lower()
                if praat_seq and praat_seq != tr.sequence:
                    seq_mismatch += 1
                    warnings.warn(
                        f"[WARN] {pid} idx={tr.index}: praat sequence '{praat_seq}' != EEG code sequence '{tr.sequence}'. "
                        "Continuing, but check mapping if this is frequent."
                    )
                if praat_rate and praat_rate != tr.rate:
                    warnings.warn(
                        f"[WARN] {pid} idx={tr.index}: praat rate '{praat_rate}' != EEG code rate '{tr.rate}'. "
                        "Continuing, but check mapping if this is frequent."
                    )

            # compute kinematics
            try:
                kin, cycle_df = compute_trial_kinematics(ema_df, fs_ema, trial_start_sec, trial_end_sec)
            except Exception as e:
                warnings.warn(f"[WARN] {pid}: kinematics failed for sweep {sweep_no} idx={tr.index}: {e}")
                continue

            processed_trials += 1

            # alignment/QC row
            align_row = {
                "participant_id": pid,
                "sequence": tr.sequence,
                "rate": tr.rate,
                "index": tr.index,
                "block_idx": tr.block_idx,
                "trial_in_block": tr.trial_in_block,
                "sweep_number": sweep_no,
                "eeg_sweep_start_sample": tr.eeg_sweep_start,
                "eeg_sweep_stop_sample": tr.eeg_sweep_stop,
                "eeg_stim_sample": tr.eeg_stim_sample,
                "eeg_go_sample": tr.eeg_go_sample if tr.eeg_go_sample is not None else np.nan,
                "stim_in_sweep_sec": stim_sec,
                "go_in_sweep_sec": go_sec,
                "trial_start_in_sweep_sec": kin.trial_start_sec,
                "trial_end_in_sweep_sec": kin.trial_end_sec,
                "ema_fs_hz": kin.ema_fs_hz,
            }

            # simple audio QC: energy in trial window (if sweep wav exists)
            if args.audio_qc:
                sweep_wav = subj_dir / "Audio" / "wav" / f"{pid}-sweep-{sweep_no:04d}.wav"
                if sweep_wav.exists():
                    try:
                        # read a small segment using wave (still lightweight)
                        with wave.open(str(sweep_wav), "rb") as wf:
                            fs_a = wf.getframerate()
                            n_ch = wf.getnchannels()
                            # convert trial window to frames
                            f0 = int(max(0, math.floor(kin.trial_start_sec * fs_a)))
                            f1 = int(min(wf.getnframes(), math.ceil(kin.trial_end_sec * fs_a)))
                            wf.setpos(f0)
                            raw_bytes = wf.readframes(max(0, f1 - f0))
                        # bytes -> int16
                        x = np.frombuffer(raw_bytes, dtype=np.int16)
                        if n_ch > 1:
                            x = x.reshape(-1, n_ch).mean(axis=1)
                        x = x.astype(np.float32)
                        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else float("nan")
                        align_row["sweep_audio_rms"] = rms
                    except Exception:
                        align_row["sweep_audio_rms"] = np.nan
                else:
                    align_row["sweep_audio_rms"] = np.nan

            all_align_rows.append(align_row)

            # trial kinematics row (merge praat + meta + anatomy)
            trial_row = dict(align_row)
            trial_row.update({
                "mov_onset_sec": kin.mov_onset_sec,
                "mov_offset_sec": kin.mov_offset_sec,
                "jaw_open_mean_mm": kin.jaw_open_mean_mm,
                "jaw_open_p2p_mm": kin.jaw_open_p2p_mm,
                "jaw_speed_peak_mm_s": kin.jaw_speed_peak_mm_s,
                "tt_speed_peak_mm_s": kin.tt_speed_peak_mm_s,
                "td_speed_peak_mm_s": kin.td_speed_peak_mm_s,
                "cycle_count": kin.cycle_count,
                "cycle_rate_hz": kin.cycle_rate_hz,
                "cycle_dur_mean_s": kin.cycle_dur_mean_s,
                "cycle_dur_cv": kin.cycle_dur_cv,
            })

            if praat_row is not None:
                # keep the identifying praat fields explicitly (so you can QC mapping later)
                trial_row["praat_soundname"] = str(praat_row.get("soundname", ""))
                trial_row["praat_sequence"] = str(praat_row.get("sequence", "")).lower()
                trial_row["praat_rate"] = str(praat_row.get("rate", "")).lower()
                trial_row["praat_index"] = int(praat_row.get("index")) if pd.notna(praat_row.get("index")) else np.nan

                # add remaining praat columns, avoiding duplicates / ID columns
                skip_cols = {"participant_id", "sequence", "rate", "index", "soundname"}
                for c in praat_row.index:
                    if c in skip_cols or c in trial_row:
                        continue
                    trial_row[c] = praat_row[c]

            # metadata merge
            if not md.empty and "participant_id" in md.columns:
                md_row = md[md["participant_id"] == pid]
                if not md_row.empty:
                    r0 = md_row.iloc[0]
                    for c in md_row.columns:
                        if c == "participant_id" or c in trial_row:
                            continue
                        trial_row[c] = r0[c]

            # anatomy merge
            if not anat_wide.empty and "participant_id" in anat_wide.columns:
                a_row = anat_wide[anat_wide["participant_id"] == pid]
                if not a_row.empty:
                    r0 = a_row.iloc[0]
                    for c in a_row.columns:
                        if c == "participant_id" or c in trial_row:
                            continue
                        trial_row[c] = r0[c]

            all_trial_rows.append(trial_row)

            # cycle table rows
            if cycle_df is not None and len(cycle_df) > 0:
                for _, r in cycle_df.iterrows():
                    crow = {
                        "participant_id": pid,
                        "sequence": tr.sequence,
                        "rate": tr.rate,
                        "index": tr.index,
                        "block_idx": tr.block_idx,
                        "trial_in_block": tr.trial_in_block,
                        "sweep_number": sweep_no,
                        "trial_start_in_sweep_sec": kin.trial_start_sec,
                        "trial_end_in_sweep_sec": kin.trial_end_sec,
                    }
                    for c in cycle_df.columns:
                        crow[c] = r[c]
                    all_cycle_rows.append(crow)

            # plots: reconstruct signals for display (cheap but okay for plot_n)
            if args.plot_n and plotted < args.plot_n:
                # pull raw signals again within trial window
                ema_df_full, fs_ema_full, _ = ema_cache[sweep_no]
                n_full = len(ema_df_full)
                i0 = max(0, min(n_full - 2, int(round(kin.trial_start_sec * fs_ema_full))))
                i1 = max(i0 + 2, min(n_full - 1, int(round(kin.trial_end_sec * fs_ema_full))))
                seg = ema_df_full.iloc[i0:i1].copy()
                UI = extract_channel_xyz(seg, SENSOR_CHANNELS["UI"])
                LI = extract_channel_xyz(seg, SENSOR_CHANNELS["LI"])
                TT = extract_channel_xyz(seg, SENSOR_CHANNELS["TT"])
                LI_rel = LI - UI
                TT_rel = TT - UI
                jaw_open = vecnorm(LI_rel, axis=1)
                jaw_open_f = butter_lowpass(jaw_open, fs_ema_full, cutoff_hz=12.0, order=4)
                jaw_speed = vecnorm(deriv(LI_rel, fs_ema_full, axis=0), axis=1)
                tt_speed = vecnorm(deriv(TT_rel, fs_ema_full, axis=0), axis=1)
                t_rel = np.arange(len(seg), dtype=np.float32) / fs_ema_full

                fig_name = f"trial_{pid}_sweep-{sweep_no:04d}_{tr.rate}_{tr.sequence}_{tr.index:03d}.png"
                title = f"{pid} | sweep {sweep_no:04d} | {tr.sequence} | {tr.rate} | idx {tr.index} (block {tr.block_idx}, trial {tr.trial_in_block})"
                vlines = []
                # mark stim/go relative to trial_start
                vlines.append((max(0.0, stim_sec - kin.trial_start_sec), "stim"))
                if np.isfinite(go_sec):
                    vlines.append((max(0.0, go_sec - kin.trial_start_sec), "go"))

                plot_trial(figs_dir / fig_name, t_rel, jaw_open_f, jaw_speed, tt_speed, title, vlines, cycles=cycle_df)
                plotted += 1

        # QC: within-sweep gaps (should be comfortably > ~1s for this paradigm)
        try:
            _align_pid = pd.DataFrame(all_align_rows[start_align_len:])
            if not _align_pid.empty:
                _align_pid = _align_pid.sort_values(["sweep_number", "trial_start_in_sweep_sec"])
                _gaps = _align_pid.groupby("sweep_number")["trial_start_in_sweep_sec"].diff()
                _min_gaps = _gaps.groupby(_align_pid["sweep_number"]).min()
                if len(_min_gaps) > 0:
                    print(f"[QC] {pid}: min within-sweep inter-trial gap = {float(_min_gaps.min()):.3f} s")
        except Exception:
            pass

        print(f"[INFO] {pid}: processed {processed_trials} trials (sequence mismatches={seq_mismatch})")

    # write outputs
    align_df = pd.DataFrame(all_align_rows)
    trial_df = pd.DataFrame(all_trial_rows)
    cycle_df = pd.DataFrame(all_cycle_rows)

    align_path = tables_dir / "ema_trial_alignment.csv"
    trial_path = tables_dir / "ema_trial_kinematics.csv"
    cycle_path = tables_dir / "ema_cycle_kinematics.csv"

    if (not args.overwrite) and (align_path.exists() or trial_path.exists() or cycle_path.exists()):
        raise FileExistsError(
            f"Output files already exist in {tables_dir}. Use --overwrite to overwrite."
        )

    align_df.to_csv(align_path, index=False)
    trial_df.to_csv(trial_path, index=False)
    cycle_df.to_csv(cycle_path, index=False)

    print(f"[DONE] Wrote tables to: {tables_dir}")
    print(f"       - {align_path.name} ({len(align_df)} rows)")
    print(f"       - {trial_path.name} ({len(trial_df)} rows)")
    print(f"       - {cycle_path.name} ({len(cycle_df)} rows)")
    print(f"[DONE] Wrote figures to: {figs_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())