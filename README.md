# DVMDOSTEM → ILAMB Processing Pipeline

Convert [Site-Runs_Sep2026](../Site-Runs_Sep2026) DVMDOSTEM site outputs and ABCFlux/fallback
observations into ILAMB-compatible NetCDF, validate conversions, and run ILAMB benchmarking.

## Setup

```bash
cd /mnt/disks/wiemip-data/dvmdostem-ilamb
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -e ../ILAMB   # requires mpi4py; use conda if needed
```

Set the ILAMB data root for all stages:

```bash
export ILAMB_ROOT=/mnt/disks/wiemip-data/dvmdostem-ilamb/outputs
```

## Stages

### Stage 1 — Observations → ILAMB NetCDF

```bash
./scripts/run_stage1.sh
# or: .venv/bin/dvmdostem-convert-obs --config configs/abcflux_to_ilamb.yaml
```

Customize inputs in [`configs/abcflux_to_ilamb.yaml`](configs/abcflux_to_ilamb.yaml):
- ABCFlux CSV path, fallback CSV map, CMT filter, variables, units, sign handling

Outputs: `outputs/DATA/{gpp,reco,nee,npp}/SiteRuns_Obs/*.nc`

### Stage 2 — Model → ILAMB NetCDF

```bash
./scripts/run_stage2.sh
# or: .venv/bin/dvmdostem-convert-model --config configs/model_to_ilamb.yaml
```

Customize [`configs/model_to_ilamb.yaml`](configs/model_to_ilamb.yaml):
- Site runs root, variable file mapping, grid extraction mode (`nearest_tower` for 10×10 sites)

Outputs: `outputs/MODELS/DVMDOSTEM-SiteRuns/{var}/{var}_CMTxx.nc`

### Stage 3 — Validate conversions

```bash
./scripts/run_stage3.sh
```

Produces:
- `outputs/diagnostics/conversion_report.json`
- `outputs/diagnostics/conversion_check.png`
- Summary CSVs for obs and model conversion

### Stage 4/5 — ILAMB run + scoreboard

```bash
./scripts/run_ilamb.sh
```

Produces HTML scoreboard at `outputs/_build/index.html`.

View locally:

```bash
python -m http.server --directory outputs/_build 8080
```

## Configuration files

| File | Purpose |
|------|---------|
| `configs/abcflux_to_ilamb.yaml` | Stage 1 obs conversion |
| `configs/model_to_ilamb.yaml` | Stage 2 model conversion |
| `configs/check_conversions.yaml` | Stage 3 validation |
| `configs/site_runs_ilamb.cfg` | Stage 4 ILAMB confrontations |

## Notes

- Observation and model fluxes are stored as **g m-2 d-1** (converted from monthly g/m² totals).
- ABCFlux GPP/RECO signs use `abs()` by default (matching `compareall.py`).
- CMTs without observations are masked in the benchmark NetCDF; see Stage 3 report for overlap counts.
- ILAMB requires MPI; `run_ilamb.sh` uses `mpirun -n 1` when available.
- Model outputs for ILAMB are **combined multi-site NetCDF** files (`gpp.nc`, `reco.nc`, etc.) under each variable directory. Per-CMT archives are not placed under `MODELS/` (ILAMB would treat them as separate conflicting time axes).
- A one-line guard patch was applied to local ILAMB [`ModelResult.py`](../ILAMB/src/ILAMB/ModelResult.py) so site-format model files with `area=None` do not crash extraction.
