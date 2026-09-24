#!/usr/bin/env python3
"""Stage 1: Convert ABCFlux and fallback observations to ILAMB site NetCDF."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .abcflux_reader import extract_abcflux_for_site, prepare_abcflux
from .config_loader import load_config
from .fallback_reader import load_fallback_observations
from .ilamb_site_nc import write_site_netcdf
from .site_registry import SiteRecord, build_registry
from .time_utils import build_monthly_time_axis
from .units import monthly_total_to_daily_rate


VAR_MAP = {
    "gpp": "GPP_obs",
    "reco": "RECO_obs",
    "nee": "NEE_obs",
    "npp": "NPP_obs",
}


def _load_yaml_config(path: Path) -> dict:
    cfg = load_config(path)
    for key in (
        "site_runs_root",
        "community_descriptions",
        "abcflux_csv",
        "fallback_observations_root",
        "output_root",
    ):
        cfg[key] = Path(cfg[key])
    return cfg


def _collect_site_obs(
    cfg: dict, records: list[SiteRecord]
) -> tuple[list[SiteRecord], list[pd.DataFrame], list[dict]]:
    abcflux = prepare_abcflux(
        cfg["abcflux_csv"],
        cfg.get("encodings", ["utf-8", "cp1252", "latin1"]),
        sign_mode=cfg.get("abcflux_sign", "abs"),
    )
    obs_frames = []
    summaries = []

    for record in records:
        if record.obs_source == "abcflux" and record.site_reference:
            obs = extract_abcflux_for_site(abcflux, record.site_reference)
            source = "ABCFlux"
            status = "OK" if not obs.empty else "NO_ABCFLUX_ROWS"
        else:
            obs = load_fallback_observations(
                cfg["fallback_observations_root"],
                record.cmt,
                cfg.get("fallback_cmt_map", {}),
                cfg.get("fallback_catalog_prefixes", {}),
                record.input_catalog,
                cfg.get("encodings", ["utf-8", "cp1252", "latin1"]),
            )
            source = "Fallback"
            status = "OK" if not obs.empty else "NO_FALLBACK_OBS"

        if cfg.get("derive_npp", True) and not obs.empty:
            if not obs["NPP_obs"].notna().any() and obs["GPP_obs"].notna().any() and obs["RECO_obs"].notna().any():
                obs["NPP_obs"] = obs["GPP_obs"] - obs["RECO_obs"]
        if cfg.get("derive_nee", True) and not obs.empty:
            if not obs["NEE_obs"].notna().any() and obs["GPP_obs"].notna().any() and obs["RECO_obs"].notna().any():
                obs["NEE_obs"] = obs["RECO_obs"] - obs["GPP_obs"]

        obs_frames.append(obs)
        summaries.append(
            {
                "CMT": record.cmt,
                "site_name": record.site_name,
                "observation_source": source,
                "status": status,
                "n_months": len(obs),
            }
        )

    return records, obs_frames, summaries


def convert_observations(cfg: dict) -> pd.DataFrame:
    site_runs_root = cfg["site_runs_root"] / "Site_Runs"
    if not site_runs_root.exists():
        site_runs_root = cfg["site_runs_root"]
    records = build_registry(
        cfg["community_descriptions"],
        site_runs_root,
        cfg.get("cmt_include") or None,
    )
    records, obs_frames, summaries = _collect_site_obs(cfg, records)

    all_dates: set[datetime] = set()
    for obs in obs_frames:
        if obs.empty:
            continue
        all_dates.update(pd.to_datetime(obs["date"]).dt.to_pydatetime())

    if not all_dates:
        raise RuntimeError("No observation data found for any site.")

    unique_months = sorted({datetime(d.year, d.month, 1) for d in all_dates})
    time, time_bounds = build_monthly_time_axis(
        unique_months,
        time_origin=cfg.get("time_origin", "1850-01-01"),
    )
    month_index = {(dt.year, dt.month): i for i, dt in enumerate(unique_months)}

    lat = np.array([r.lat for r in records], dtype=np.float32)
    lon = np.array([r.lon for r in records], dtype=np.float32)
    site_names = [r.cmt for r in records]
    benchmark = cfg.get("benchmark_name", "SiteRuns_Obs")
    output_root = cfg["output_root"]
    variables = cfg.get("variables", list(VAR_MAP.keys()))
    output_units = cfg.get("output_units", "g m-2 d-1")

    for var in variables:
        col = VAR_MAP[var]
        data = np.full((len(time), len(records)), np.nan, dtype=float)
        for j, (record, obs) in enumerate(zip(records, obs_frames)):
            if obs.empty:
                continue
            for _, row in obs.iterrows():
                dt = pd.to_datetime(row["date"])
                key = (dt.year, dt.month)
                if key not in month_index:
                    continue
                ti = month_index[key]
                val = row.get(col, np.nan)
                if pd.notna(val):
                    daily = float(val) / __import__("calendar").monthrange(key[0], key[1])[1]
                    data[ti, j] = daily

        out_path = output_root / var / benchmark / f"{var}.nc"
        write_site_netcdf(
            out_path,
            var,
            data,
            lat,
            lon,
            time,
            time_bounds,
            site_names,
            units=output_units,
        )

    summary_df = pd.DataFrame(summaries)
    diag_dir = output_root.parent / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(diag_dir / "obs_conversion_summary.csv", index=False)
    return summary_df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="/mnt/disks/wiemip-data/dvmdostem-ilamb/configs/abcflux_to_ilamb.yaml",
    )
    args = parser.parse_args(argv)
    cfg = _load_yaml_config(Path(args.config))
    summary = convert_observations(cfg)
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
