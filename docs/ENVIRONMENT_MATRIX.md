# Environment matrix

| Stage | Exact/current environment | Reproduction status | Limitation |
|---|---|---|---|
| Historical extraction | Not fully recoverable | Documented, not rerun | raw signals, cycle-aggregation script, and complete run records absent |
| Empirical model | Python 3.13.5; NumPy 2.3.5; pandas 2.2.3; SciPy 1.17.0; statsmodels 0.14.6; Patsy 1.0.2 | V13 rerun from canonical derived inputs | results in other environments may vary at floating precision |
| V8 figures | empirical stack + Matplotlib 3.10.8 | regenerated and validated | PDF byte hashes can differ because of metadata while PNG/data are identical |
| Corrected dynamic simulation | macOS 26.5.1 arm64; x86_64 Temurin Java 8 1.8.0_472; Python 3.12.7; ArtiSynth 3.9 installation | author workstation run validated | exact semantic ArtiSynth build identifier unavailable |
| V13 Phase C table validation | Python 3.13.5; NumPy 2.3.5; pandas 2.2.3 | independently rerun | does not relaunch ArtiSynth dynamics |
