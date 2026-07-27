# Mandibular length and rapid syllable timing

Code, minimized deidentified derived data, validated outputs, and figure-generation
materials for the study *External mandibular length at a given stature is linked to slower syllable repetition*.

## Study scope

The human analysis is observational and cross-sectional. The primary anatomical sample
contains 28 speakers and 8,123 repeated diadochokinetic trials. The primary estimand is
the association of bilateral mean external condylion-menton distance (Co-Me) with speech
rate and articulation rate at a given modeled stature. Secondary kinematic and acoustic
analyses use smaller overlapping subsets.

The ArtiSynth analysis is a separate model sensitivity analysis. Across the tested grid,
all 684 cells met the specified tracking, excitation, and amplitude-gain criteria through
10 Hz, the highest tested frequency. The simulation does not establish a human mechanism
or physical maximum.

## Repository contents

- `analysis/`: empirical analysis, finite-cluster checks, and figure-generation code;
- `data/derived/`: minimized deidentified model-stage inputs;
- `results/`: retained numerical outputs and table sources;
- `figures/`: publication figures in PDF and PNG format;
- `artisynth/`: model code, validated long tables, and table-level validation;
- `docs/`: analysis hierarchy, provenance, limitations, output map, and reproduction commands;
- `environment/`: recorded software environments.

Raw audio, EMA, EEG/BDF, imaging, direct identifiers, and unrelated participant metadata
are not included.

## Verify and reproduce

Create the documented Python environments, then run:

```bash
python analysis/verify_repository_inputs.py
```

Reproduction commands for the retained analyses and figures are listed in
[`docs/REPRODUCTION_COMMANDS.md`](docs/REPRODUCTION_COMMANDS.md).

The completed validation summary is in [`REPRODUCIBILITY_VALIDATION.md`](REPRODUCIBILITY_VALIDATION.md). File sizes and SHA256 values are recorded in `REPOSITORY_MANIFEST.tsv`.

## Data source

The analyses used Version 1.2 of *A multimodal speech-production dataset with time-aligned
articulography, EEG, audio, and vocal-tract anatomy*:

- version DOI: `10.48656/vc7s-pt02`
- canonical DOI: `10.48656/6y1s-px92`

The dataset is distributed under CC BY 4.0. See
[`DATA_LICENSE_AND_ATTRIBUTION.md`](DATA_LICENSE_AND_ATTRIBUTION.md).

## Citation

Use [`CITATION.cff`](CITATION.cff) for the software package and cite the associated
manuscript and dataset. The all-versions Zenodo record is
`https://doi.org/10.5281/zenodo.21545601`; the release-specific DOI is shown on the
corresponding Zenodo version record.

## License

Original code and documentation are released under the MIT License. Dataset-derived
materials retain the source dataset's CC BY 4.0 attribution requirements. Third-party
software remains under its own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
