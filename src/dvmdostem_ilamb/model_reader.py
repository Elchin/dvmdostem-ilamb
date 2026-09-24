"""Read DVMDOSTEM site run NetCDF outputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from .time_utils import fill_continuous_monthly_series


def find_model_file(output_dir: Path, filenames: list[str], variable: str) -> Path | None:
    for name in filenames:
        path = output_dir / name
        if path.exists():
            return path
    candidates = sorted(output_dir.glob(f"{variable}_monthly*.nc"))
    if not candidates:
        candidates = sorted(output_dir.glob(f"*{variable}*monthly*.nc"))
    if not candidates:
        return None
    transient = [p for p in candidates if "_tr" in p.name]
    return transient[0] if transient else candidates[0]


def _find_time_name(ds: xr.Dataset) -> str:
    for candidate in ("time", "Time", "TIME"):
        if candidate in ds.coords or candidate in ds.variables:
            return candidate
    for name in list(ds.coords) + list(ds.dims):
        if "time" in name.lower():
            return name
    raise RuntimeError("No time coordinate found")


def _find_var_name(ds: xr.Dataset, expected: str) -> str:
    for name in (expected, expected.upper(), expected.lower()):
        if name in ds.data_vars:
            return name
    for var in ds.data_vars:
        if var.lower() == expected.lower():
            return var
    raise RuntimeError(f"Variable {expected} not found in {list(ds.data_vars)}")


def read_run_mask(run_mask_path: Path) -> tuple[np.ndarray, np.ndarray]:
    with Dataset(run_mask_path, "r") as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
    return lat, lon


def extract_series_from_grid(
    values: np.ndarray,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    tower_lat: float,
    tower_lon: float,
    grid_mode: str = "nearest_tower",
) -> float | np.ndarray:
    if values.ndim == 1:
        return values
    if values.ndim == 2 and values.size == 1:
        return float(values.ravel()[0])
    if grid_mode == "mean_for_10x10":
        return float(np.nanmean(values))
    dist = (lat_grid - tower_lat) ** 2 + (lon_grid - tower_lon) ** 2
    idx = np.unravel_index(np.nanargmin(dist), dist.shape)
    return float(values[idx])


def read_model_monthly_series(
    nc_path: Path,
    nc_var: str,
    run_mask_path: Path,
    tower_lat: float,
    tower_lon: float,
    grid_mode: str = "nearest_tower",
    model_origin: str = "1901-01-01",
) -> pd.DataFrame:
    try:
        time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
        ds = xr.open_dataset(nc_path, decode_times=time_coder)
    except Exception:
        ds = xr.open_dataset(nc_path, decode_times=True)

    time_name = _find_time_name(ds)
    var_name = _find_var_name(ds, nc_var)
    da = ds[var_name].transpose(time_name, ...)
    lat_grid, lon_grid = read_run_mask(run_mask_path)

    times = da[time_name].values
    rows = []
    origin = datetime.strptime(model_origin, "%Y-%m-%d")

    for i, tval in enumerate(times):
        if hasattr(tval, "year"):
            year, month = int(tval.year), int(tval.month)
        else:
            dt = origin + timedelta(days=int(round(float(tval))))
            year, month = dt.year, dt.month

        arr = np.asarray(da.isel({time_name: i}).values, dtype=float)
        value = extract_series_from_grid(
            arr, lat_grid, lon_grid, tower_lat, tower_lon, grid_mode=grid_mode
        )
        rows.append({"year": year, "month": month, "value": value})

    ds.close()
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return (
        out.groupby(["year", "month"], as_index=False)["value"]
        .mean()
        .sort_values(["year", "month"])
        .reset_index(drop=True)
    )


def model_series_to_ilamb_time(
    df: pd.DataFrame,
    time_origin: str = "1850-01-01",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    df = df.dropna(subset=["year", "month"]).copy()
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df = (
        df.groupby(["year", "month"], as_index=False)["value"]
        .mean()
        .sort_values(["year", "month"])
        .reset_index(drop=True)
    )
    return fill_continuous_monthly_series(
        df["year"].tolist(),
        df["month"].tolist(),
        df["value"].tolist(),
        time_origin=time_origin,
    )
