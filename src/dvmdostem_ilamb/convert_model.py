#!/usr/bin/env python3
"""Stage 2: Convert DVMDOSTEM site runs to ILAMB model NetCDF."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config_loader import load_config
from .site_registry import SiteRecord
from .ilamb_site_nc import write_site_netcdf
from .model_reader import find_model_file, model_series_to_ilamb_time, read_model_monthly_series
from .site_registry import build_registry, canonical_cmt
from .units import monthly_total_to_daily_rate


def _load_yaml_config(path: Path) -> dict:
    cfg = load_config(path)
    cfg["site_runs_root"] = Path(cfg["site_runs_root"])
    cfg["community_descriptions"] = Path(cfg["community_descriptions"])
    cfg["output_root"] = Path(cfg["output_root"])
    return cfg


def convert_model(cfg: dict) -> pd.DataFrame:
    site_runs_root = cfg["site_runs_root"]
    output_root = cfg["output_root"]
    variables = cfg["variables"]
    grid_mode = cfg.get("grid_mode", "nearest_tower")
    time_origin = cfg.get("time_origin", "1850-01-01")
    output_units = cfg.get("output_units", "g m-2 d-1")
    fill_value = float(cfg.get("fill_value", -9999.0))
    run_mask_name = cfg.get("run_mask_name", "run-mask.nc")

    records = build_registry(
        cfg["community_descriptions"],
        site_runs_root,
        cfg.get("cmt_include") or None,
    )

    summaries = []
    combined_series: dict[str, list[tuple[SiteRecord, pd.DataFrame]]] = {
        var: [] for var in variables if "derive_from" not in variables[var]
    }
    combined_series.update({var: [] for var, spec in variables.items() if "derive_from" in spec})

    for record in records:
        site_dir = site_runs_root / record.cmt
        output_dir = site_dir / "output"
        run_mask = site_dir / run_mask_name
        status = "OK"
        note = ""

        if not output_dir.exists():
            status = "NO_OUTPUT_DIR"
            summaries.append({"CMT": record.cmt, "status": status, "note": note})
            continue
        if not run_mask.exists():
            status = "NO_RUN_MASK"
            summaries.append({"CMT": record.cmt, "status": status, "note": note})
            continue

        site_series: dict[str, pd.DataFrame] = {}

        for var_name, spec in variables.items():
            if "derive_from" in spec:
                continue
            nc_var = spec["nc_var"]
            files = spec.get("files", [])
            nc_path = find_model_file(output_dir, files, nc_var)
            if nc_path is None:
                note = f"missing {var_name}"
                continue
            try:
                df = read_model_monthly_series(
                    nc_path,
                    nc_var,
                    run_mask,
                    record.lat,
                    record.lon,
                    grid_mode=grid_mode,
                )
                site_series[var_name] = df
            except Exception as exc:
                status = "READ_ERROR"
                note = str(exc)
                break

        if status != "OK" and not site_series:
            summaries.append({"CMT": record.cmt, "status": status, "note": note})
            continue

        # Derived variables
        for var_name, spec in variables.items():
            if "derive_from" not in spec:
                continue
            deps = spec["derive_from"]
            if not all(d in site_series for d in deps):
                continue
            merged = site_series[deps[0]][["year", "month", "value"]].rename(columns={"value": deps[0]})
            for dep in deps[1:]:
                merged = merged.merge(
                    site_series[dep][["year", "month", "value"]].rename(columns={"value": dep}),
                    on=["year", "month"],
                    how="inner",
                )
            if var_name == "nee":
                merged["value"] = merged["reco"] - merged["gpp"]
            else:
                merged["value"] = np.nan
            site_series[var_name] = merged[["year", "month", "value"]]

        for var_name, df in site_series.items():
            combined_series.setdefault(var_name, []).append((record, df.copy()))

        summaries.append(
            {
                "CMT": record.cmt,
                "status": status,
                "note": note,
                "variables_written": ",".join(sorted(site_series.keys())),
                "n_months": max((len(df) for df in site_series.values()), default=0),
            }
        )

    # Combined multi-site files for ILAMB (shared time axis across all CMTs).
    if combined_series:
        all_dates = []
        for entries in combined_series.values():
            for _, df in entries:
                for _, row in df.iterrows():
                    all_dates.append(datetime(int(row.year), int(row.month), 1))
        if all_dates:
            from .time_utils import build_monthly_time_axis

            unique_months = sorted({datetime(d.year, d.month, 1) for d in all_dates})
            time, time_bounds = build_monthly_time_axis(
                unique_months, time_origin=time_origin
            )
            month_index = {(dt.year, dt.month): i for i, dt in enumerate(unique_months)}
            ordered_records = [r for r in records]
            lat = np.array([r.lat for r in ordered_records], dtype=np.float32)
            lon = np.array([r.lon for r in ordered_records], dtype=np.float32)
            site_names = [r.cmt for r in ordered_records]

            for var_name in variables:
                entries = combined_series.get(var_name, [])
                if not entries:
                    continue
                lookup = {rec.cmt: df for rec, df in entries}
                data = np.full((len(time), len(ordered_records)), np.nan, dtype=float)
                for j, rec in enumerate(ordered_records):
                    df = lookup.get(rec.cmt)
                    if df is None or df.empty:
                        continue
                    daily = monthly_total_to_daily_rate(
                        df["value"].tolist(),
                        df["year"].tolist(),
                        df["month"].tolist(),
                    )
                    for (_, row), value in zip(df.iterrows(), daily):
                        key = (int(row.year), int(row.month))
                        if key in month_index and value == value:
                            data[month_index[key], j] = value
                out_path = output_root / var_name / f"{var_name}.nc"
                write_site_netcdf(
                    out_path,
                    var_name,
                    data,
                    lat,
                    lon,
                    time,
                    time_bounds,
                    site_names,
                    units=output_units,
                    fill_value=fill_value,
                )

    summary_df = pd.DataFrame(summaries)
    diag_dir = output_root.parent / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(diag_dir / "model_conversion_summary.csv", index=False)
    return summary_df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="/mnt/disks/wiemip-data/dvmdostem-ilamb/configs/model_to_ilamb.yaml",
    )
    args = parser.parse_args(argv)
    cfg = _load_yaml_config(Path(args.config))
    summary = convert_model(cfg)
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
