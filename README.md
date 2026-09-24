# DVMDOSTEM → ILAMB Processing Pipeline

Convert Site-Runs DVMDOSTEM site outputs and
ABCFlux/fallback observations into ILAMB-compatible NetCDF, validate conversions, and run ILAMB
benchmarking.

## Quick start

Edit the YAML configs under [`configs/`](configs/) so paths point at your Site-Runs data, then run:

```bash
cd /path/to/dvmdostem-ilamb
./scripts/run_all.sh
```

This script:

1. Creates `.venv` and installs this package
2. Clones [ILAMB](https://github.com/rubisco-sfa/ILAMB) into `vendor/ILAMB` (override with `ILAMB_DIR`)
3. Applies a small ILAMB patch needed for site-format model files
4. Runs all conversion, validation, and ILAMB stages
5. Writes the HTML scoreboard to `outputs/_build/index.html`

View the scoreboard locally:

```bash
python -m http.server --directory outputs/_build 8080
```

Re-run stages only (skip setup):

```bash
./scripts/run_all.sh --skip-setup
```

## Prerequisites

- Python 3.9+
- Git
- Site-Runs input data (see config paths below)
- OpenMPI (`mpirun`) for the ILAMB stage
- ILAMB Python dependencies (`mpi4py`, `cartopy`, etc.); use conda/mamba if pip install fails

## Setup (manual)

```bash
cd /path/to/dvmdostem-ilamb
python3 -m venv .venv
.venv/bin/pip install -e .

# Clone ILAMB anywhere you like (not required to live next to this repo):
export ILAMB_DIR=/path/to/ILAMB
git clone https://github.com/rubisco-sfa/ILAMB.git "$ILAMB_DIR"
.venv/bin/pip install -e "$ILAMB_DIR"
```

If ILAMB crashes on site-format model files, apply the guard patch in
`$ILAMB_DIR/src/ILAMB/ModelResult.py` (or let `run_all.sh` apply it automatically):

```python
# change:
if not np.allclose(var.area.shape, [var.lat.size, var.lon.size]):
# to:
if var.area is not None and not np.allclose(var.area.shape, [var.lat.size, var.lon.size]):
```

Set the ILAMB data root for all stages:

```bash
export ILAMB_ROOT=/path/to/dvmdostem-ilamb/outputs
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

Outputs: combined multi-site files `outputs/MODELS/DVMDOSTEM-SiteRuns/{var}/{var}.nc`

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

## Configuration files

| File | Purpose |
|------|---------|
| `configs/abcflux_to_ilamb.yaml` | Stage 1 obs conversion |
| `configs/model_to_ilamb.yaml` | Stage 2 model conversion |
| `configs/check_conversions.yaml` | Stage 3 validation |
| `configs/site_runs_ilamb.cfg` | Stage 4 ILAMB confrontations |

Update the absolute paths in the first three YAML files to match your Site-Runs checkout.

## Notes

- Observation and model fluxes are stored as **g m-2 d-1** (converted from monthly g/m² totals).
- ABCFlux GPP/RECO signs use `abs()` by default (matching `compareall.py`).
- CMTs without observations are masked in the benchmark NetCDF; see Stage 3 report for overlap counts.
- ILAMB requires MPI; `run_ilamb.sh` uses `mpirun -n 1` when available.
- Model outputs for ILAMB are **combined multi-site NetCDF** files (`gpp.nc`, `reco.nc`, etc.) under each variable directory. Per-CMT archives are not placed under `MODELS/` (ILAMB would treat them as separate conflicting time axes).
- ILAMB is cloned into `vendor/ILAMB` by default (`ILAMB_DIR` overrides this). It is listed in `.gitignore`.
