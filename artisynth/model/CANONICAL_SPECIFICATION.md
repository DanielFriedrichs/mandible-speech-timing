# ArtiSynth model specification

- Geometry fixed.
- Gravity disabled.
- Mandibular mass multiplier: `s^3`.
- Rotational-inertia multiplier: `s^5`.
- Fixed-force mode: muscle-force multiplier `1`.
- Force-capacity mode: maximum muscle force multiplier `s^2`.
- Scale grid: 0.80 to 1.20 in 0.05 steps.
- Target-frequency grid: 1.0 to 10.0 Hz in 0.5-Hz steps.
- Peak-to-peak amplitudes: 1.0 and 1.5 mm.
- Technical grid size: 342 cells per mode, 684 total.
- Feasibility: tracking RMSE <= 0.5 mm, peak excitation <= 0.95, and amplitude gain in [0.7, 1.3].
- Endpoint rule: strict feasible prefix, stopping at the first infeasible frequency.

The target-velocity expression is the exact derivative of the active target-position expression.
