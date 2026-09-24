"""Write ILAMB-compatible single-site model NetCDF files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from .time_utils import CALENDAR, TIME_UNITS


def write_model_netcdf_1x1(
    output_path: Path,
    variable_name: str,
    values: np.ndarray,
    lat: float,
    lon: float,
    time: np.ndarray,
    time_bounds: np.ndarray,
    units: str = "g m-2 d-1",
    fill_value: float = -9999.0,
    site_label: str = "",
) -> None:
    """Write one site as (time, data=1) — ILAMB multi-site run convention."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ntime = len(time)

    with Dataset(output_path, "w", format="NETCDF4") as ds:
        ds.createDimension("time", ntime)
        ds.createDimension("data", 1)
        ds.createDimension("nb", 2)

        t = ds.createVariable("time", "f8", ("time",))
        tb = ds.createVariable("time_bounds", "f8", ("time", "nb"))
        la = ds.createVariable("lat", "f4", ("data",))
        lo = ds.createVariable("lon", "f4", ("data",))
        var = ds.createVariable(
            variable_name,
            "f4",
            ("time", "data"),
            fill_value=fill_value,
            zlib=True,
        )

        t[:] = time
        t.units = TIME_UNITS
        t.calendar = CALENDAR
        t.bounds = "time_bounds"
        tb[:] = time_bounds
        la[:] = [lat]
        la.units = "degrees_north"
        lo[:] = [lon]
        lo.units = "degrees_east"
        var[:, 0] = np.ma.masked_invalid(values).filled(fill_value)
        var.units = units
        var.long_name = variable_name

        if site_label:
            ds.site_name = site_label
        ds.title = f"DVMDOSTEM site run: {variable_name}"


def read_model_netcdf(path: Path, variable_name: str | None = None) -> dict:
    with Dataset(path, "r") as ds:
        var_name = variable_name
        if var_name is None:
            skip = {"time", "time_bounds", "lat", "lon"}
            candidates = [v for v in ds.variables if v not in skip]
            var_name = candidates[0]
        data = ds.variables[var_name][:]
        if data.ndim == 2:
            data = data[:, 0]
        while data.ndim > 1:
            data = np.squeeze(data, axis=-1)
        lat_arr = np.asarray(ds.variables["lat"][:]).ravel()
        lon_arr = np.asarray(ds.variables["lon"][:]).ravel()
        return {
            "variable": var_name,
            "data": data,
            "lat": float(lat_arr[0]),
            "lon": float(lon_arr[0]),
            "time": ds.variables["time"][:],
            "time_bounds": ds.variables["time_bounds"][:],
            "units": ds.variables[var_name].units,
        }
