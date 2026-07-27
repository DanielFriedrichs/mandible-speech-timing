# ArtiSynth sensitivity analysis

This directory contains the model implementation and table-level validation materials for
the supplementary mass-and-inertia sensitivity analysis.

- `model/` contains the Java model and the Python grid, feasibility, and validation code.
- `validated/` contains two 342-cell long tables and the 18-row endpoint comparison.
- `validation/validate_phase_c_tables.py` independently recomputes feasibility and strict-prefix endpoints from the included tables.

The dynamic model requires a separate ArtiSynth installation and the dynamic-jaw model
classes. ArtiSynth itself is not redistributed. The included table validator does not launch
the dynamic model.

Across the included grid, all 684 cells were technically successful and met the tracking,
peak-excitation, and amplitude-gain criteria through 10 Hz, the highest tested frequency.
No first failure was observed, and the fixed-force and force-capacity endpoints were equal.
This model sensitivity result does not establish a human mechanism or physical maximum.
