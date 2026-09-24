"""Write ILAMB site-collection observation NetCDF files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from .time_utils import CALENDAR, TIME_UNITS


def write_site_netcdf(
    output_path: Path,
    variable_name: str,
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    time: np.ndarray,
    time_bounds: np.ndarray,
    site_names: list[str],
    units: str = "g m-2 d-1",
    fill_value: float = -9999.0,
) -> None:
    """Write (time, data) site NetCDF benchmark file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ntime, nsite = data.shape

    with Dataset(output_path, "w", format="NETCDF4") as ds:
        ds.createDimension("time", ntime)
        ds.createDimension("data", nsite)
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
        la[:] = lat
        la.units = "degrees_north"
        lo[:] = lon
        lo.units = "degrees_east"
        var[:] = np.ma.masked_invalid(data).filled(fill_value)
        var.units = units
        var.long_name = variable_name

        ds.site_name = ",".join(site_names)
        ds.title = f"SiteRuns observation benchmark: {variable_name}"


def read_site_netcdf(path: Path, variable_name: str | None = None) -> dict:
    with Dataset(path, "r") as ds:
        var_name = variable_name
        if var_name is None:
            candidates = [v for v in ds.variables if v not in ("time", "time_bounds", "lat", "lon")]
            var_name = candidates[0]
        site_names = []
        if "site_name" in ds.ncattrs():
            site_names = ds.site_name.split(",")
        return {
            "variable": var_name,
            "data": ds.variables[var_name][:],
            "lat": ds.variables["lat"][:],
            "lon": ds.variables["lon"][:],
            "time": ds.variables["time"][:],
            "time_bounds": ds.variables["time_bounds"][:],
            "site_names": site_names,
            "units": ds.variables[var_name].units,
        }
