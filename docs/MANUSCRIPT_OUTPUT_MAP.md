# Manuscript output map

| V12 output | Retained repository asset | Reproduction script | Model/data source |
|---|---|---|---|
| Main Figure 1 | `figures/Figure1_V8_PRIMARY.*` | `analysis/empirical/make_main_figures_REPOSITORY_V13.py` wrapping unchanged `make_main_figures_V8.py` | minimized primary projection, primary-estimand outputs, V8 CSVs |
| Main Figure 2 | `figures/Figure2_V8_SECONDARY.*` | same V8 wrapper/canonical pair | minimized secondary parent projection, filtered secondary model sources, V8 CSVs |
| Main Table 1 | `results/table_sources/Table1_V8.tex` and `TABLE1_PRIMARY_SECONDARY_EFFECTS_V13.csv` | same V8 wrapper/canonical pair | `FIGURE_EFFECT_ESTIMATES_V8.csv` |
| Table S1 | `results/table_sources/TABLE_S1_SMALL_CLUSTER_V13.csv` | `primary_effects_small_sample_robustness.py` | minimized primary projection |
| Table S2 | `results/table_sources/TABLE_S2_ESTIMAND_COMPARISON_V13.csv` | `run_primary_estimand_checks_REPOSITORY_V13.py` wrapping unchanged canonical checker | minimized primary projection |
| Table S3 | `results/table_sources/TABLE_S3_SENSITIVITIES_V13.csv` | retained-model runner plus accepted compact sensitivity sources | minimized primary/secondary/read projections and current outputs |
| Table S4 | `results/table_sources/TABLE_S4_INTERACTIONS_UPPER_TAIL_V13.csv` | retained-model runner; `run_upper_tail_models_V13.py` | canonical primary interaction subset; speaker upper-tail table |
| Fig. S1 | `figures/SuppPub2_CURRENT.*` | corrected V2.4/Phase C validation code | two validated 342-cell long tables |
| Fig. S2 | `figures/SuppPub1_read_speech_independence_CURRENT.*` | canonical independence-GEE figure package | minimized read-speech/anatomy projections and current read-speech output |

The V12 manuscript source, PDF, and bibliography are intentionally absent. Phase, coupling, trade-off, example, old simulation, and obsolete figure materials are also absent. The exact canonical broad empirical generator is retained because it is a mandatory provenance component, but phase/coupling data and outputs are not packaged.
