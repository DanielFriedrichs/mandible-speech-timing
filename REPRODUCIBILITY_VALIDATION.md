# Reproducibility validation

The release was validated from the bundled minimized derived inputs using the documented
software environments.

## Input integrity and retained sample sizes

- primary DDK table: 8,123 rows / 28 speakers;
- aligned EMA/audio parent table: 6,134 rows / 23 speakers;
- complete jaw-cycle and excursion rows: 3,323 / 22 speakers;
- complete envelope-modulation rows: 5,572 / 23 speakers;
- read-speech, anatomy, upper-tail, and both 342-cell ArtiSynth tables matched their
  recorded SHA256 values.

## Empirical analyses

- primary no-height and stature-conditioned GEE models reproduced all coefficients,
  standard errors, intervals, P values, and sample counts;
- 9,999 participant-cluster bootstrap resamples and 9,999 restricted-null
  wild-cluster bootstrap-t draws reproduced the retained small-cluster table;
- demographic, availability, acoustic-band, rate-interaction, read-speech, and
  speaker-level upper-tail outputs reproduced the bundled numerical values;
- the two primary and three secondary figure models reproduced the stored coefficients;
  the maximum absolute coefficient difference was 1.23e-15;
- every displayed speaker-level mean reproduced exactly.

## Figures

Running the documented figure commands reproduced all eight bundled PDF/PNG figure files
byte-for-byte. The PDF files contain vector text and graphics; the PNG copies are retained
for convenient preview and interoperability.

## ArtiSynth tables

Independent recomputation from the two long tables confirmed:

- 342 unique successful fixed-force cells and 342 unique successful force-capacity cells;
- 684/684 cells meeting the tracking-RMSE, peak-excitation, and amplitude-gain criteria;
- all 36 mode-by-scale-by-amplitude series feasible through 10 Hz, the highest tested
  frequency;
- all 18 force-capacity minus fixed-force endpoint differences equal to zero.

The table validation does not relaunch the dynamic ArtiSynth model. Dynamic reproduction
requires the separate ArtiSynth installation and jaw-model classes described in
`artisynth/README.md` and `environment/simulation_environment.txt`.

## Public-package scan

A case-insensitive byte and text scan found no conversational-AI product identifiers or absolute workstation paths. Local build reports, machine-specific records, and obsolete publication templates are not included.
