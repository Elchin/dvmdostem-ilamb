#!/usr/bin/env python3
"""Stage 3: Validate ILAMB conversions and produce diagnostic figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config_loader import load_config
from .ilamb_site_nc import read_site_netcdf
from .site_registry import build_registry


def _month_key_from_time(tmid: float) -> tuple[int, int]:
    dt = pd.Timestamp("1850-01-01") + pd.Timedelta(days=float(tmid))
    return dt.year, dt.month


def validate_conversions(cfg: dict) -> dict:
    ilamb_root = Path(cfg["ilamb_root"])
    benchmark = cfg.get("benchmark_name", "SiteRuns_Obs")
    model_name = cfg.get("model_name", "DVMDOSTEM-SiteRuns")
    variables = cfg.get("variables", ["gpp", "reco", "nee", "npp"])
    tol = float(cfg.get("latlon_tolerance_deg", 0.5))
    site_runs_root = Path(cfg["site_runs_root"])
    records = build_registry(Path(cfg["community_descriptions"]), site_runs_root, None)

    report = {
        "critical_failures": [],
        "warnings": [],
        "sites": [],
        "overlap_months": {},
    }

    obs_data = {}
    for var in variables:
        obs_path = ilamb_root / "DATA" / var / benchmark / f"{var}.nc"
        if not obs_path.exists():
            report["critical_failures"].append(f"Missing observation file: {obs_path}")
            continue
        obs_data[var] = read_site_netcdf(obs_path, var)

    model_data = {}
    for var in variables:
        model_path = ilamb_root / "MODELS" / model_name / var / f"{var}.nc"
        if not model_path.exists():
            report["critical_failures"].append(f"Missing combined model file: {model_path}")
            continue
        combined = read_site_netcdf(model_path, var)
        model_data[var] = combined

    if report["critical_failures"]:
        return report

    site_names = obs_data[variables[0]]["site_names"]
    if len(site_names) != len(records):
        report["warnings"].append(
            f"Site count mismatch: registry={len(records)} obs={len(site_names)}"
        )

    obs_site_index = {name: i for i, name in enumerate(site_names)}

    for record in records:
        site_report = {"CMT": record.cmt, "obs_source": record.obs_source, "checks": []}
        if record.cmt not in obs_site_index:
            report["overlap_months"][record.cmt] = 0
            site_report["overlap_months_gpp"] = 0
            report["sites"].append(site_report)
            continue
        j = obs_site_index[record.cmt]
        if "gpp" in obs_data:
            olat = float(obs_data["gpp"]["lat"][j])
            olon = float(obs_data["gpp"]["lon"][j])
            if abs(olat - record.lat) > tol or abs(olon - record.lon) > tol:
                report["warnings"].append(
                    f"{record.cmt}: obs lat/lon differs from registry"
                )
        if "gpp" in model_data:
            site_names = model_data["gpp"]["site_names"]
            if record.cmt in site_names:
                mj = site_names.index(record.cmt)
                ml_lat = float(model_data["gpp"]["lat"][mj])
                ml_lon = float(model_data["gpp"]["lon"][mj])
                if abs(ml_lat - record.lat) > tol or abs(ml_lon - record.lon) > tol:
                    report["warnings"].append(
                        f"{record.cmt}: model lat/lon differs from registry"
                    )

        overlap = 0
        if "gpp" in obs_data and "gpp" in model_data:
            site_names = model_data["gpp"]["site_names"]
            if record.cmt not in site_names:
                report["overlap_months"][record.cmt] = 0
                site_report["overlap_months_gpp"] = 0
                report["sites"].append(site_report)
                continue
            mj = site_names.index(record.cmt)
            obs_ts = obs_data["gpp"]["data"][:, j]
            mod_ts = model_data["gpp"]["data"][:, mj]
            for i in range(len(obs_data["gpp"]["time"])):
                ov = obs_ts[i]
                mv = mod_ts[i]
                if np.isfinite(ov) and np.isfinite(mv):
                    overlap += 1
        report["overlap_months"][record.cmt] = overlap
        site_report["overlap_months_gpp"] = overlap
        report["sites"].append(site_report)

    if sum(report["overlap_months"].values()) == 0:
        report["critical_failures"].append("Zero overlapping site-months across all CMTs")

    return report


def plot_diagnostics(cfg: dict, report: dict, records) -> Path:
    diag_dir = Path(cfg.get("diagnostics_dir", Path(cfg["ilamb_root"]) / "diagnostics"))
    diag_dir.mkdir(parents=True, exist_ok=True)
    out_png = diag_dir / "conversion_check.png"

    ilamb_root = Path(cfg["ilamb_root"])
    benchmark = cfg.get("benchmark_name", "SiteRuns_Obs")
    model_name = cfg.get("model_name", "DVMDOSTEM-SiteRuns")
    example_cmts = cfg.get("example_cmts", ["CMT05", "CMT04", "CMT90"])

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Panel 1: site map
    ax = axes[0, 0]
    colors = {"abcflux": "tab:blue", "fallback": "tab:orange", "none": "gray"}
    for record in records:
        c = colors.get(record.obs_source, "gray")
        ax.scatter(record.lon, record.lat, c=c, s=40, edgecolors="k", linewidths=0.3)
        ax.annotate(record.cmt, (record.lon, record.lat), fontsize=6, alpha=0.8)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Site locations (blue=ABCFlux, orange=fallback)")
    ax.grid(True, alpha=0.3)

    # Panel 2: example time series for GPP
    ax = axes[0, 1]
    obs_gpp = read_site_netcdf(ilamb_root / "DATA/gpp" / benchmark / "gpp.nc", "gpp")
    site_to_idx = {name: i for i, name in enumerate(obs_gpp["site_names"])}
    mod_gpp = read_site_netcdf(ilamb_root / "MODELS" / model_name / "gpp" / "gpp.nc", "gpp")
    mod_site_to_idx = {name: i for i, name in enumerate(mod_gpp["site_names"])}
    for cmt in example_cmts:
        if cmt not in site_to_idx:
            continue
        j = site_to_idx[cmt]
        obs_ts = obs_gpp["data"][:, j]
        obs_times = [pd.Timestamp("1850-01-01") + pd.Timedelta(days=float(t)) for t in obs_gpp["time"]]
        ax.plot(obs_times, obs_ts, label=f"{cmt} obs", alpha=0.8)
        if cmt in mod_site_to_idx:
            mj = mod_site_to_idx[cmt]
            mod_times = [pd.Timestamp("1850-01-01") + pd.Timedelta(days=float(t)) for t in mod_gpp["time"]]
            ax.plot(mod_times, mod_gpp["data"][:, mj], "--", label=f"{cmt} model", alpha=0.8)
    ax.set_title("GPP time series (examples)")
    ax.set_ylabel("g m-2 d-1")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # Panel 3: scatter obs vs model GPP
    ax = axes[1, 0]
    xs, ys = [], []
    for record in records:
        if record.cmt not in site_to_idx or record.cmt not in mod_site_to_idx:
            continue
        j = site_to_idx[record.cmt]
        mj = mod_site_to_idx[record.cmt]
        for i in range(len(obs_gpp["time"])):
            ov = obs_gpp["data"][i, j]
            mv = mod_gpp["data"][i, mj]
            if np.isfinite(ov) and np.isfinite(mv):
                xs.append(ov)
                ys.append(mv)
    if xs:
        ax.scatter(xs, ys, alpha=0.35, s=12)
        lim = max(max(xs), max(ys)) * 1.05
        ax.plot([0, lim], [0, lim], "k--", alpha=0.5)
    ax.set_xlabel("Obs GPP (g m-2 d-1)")
    ax.set_ylabel("Model GPP (g m-2 d-1)")
    ax.set_title("All-site GPP overlap scatter")
    ax.grid(True, alpha=0.3)

    # Panel 4: overlap bar chart
    ax = axes[1, 1]
    cmts = list(report.get("overlap_months", {}).keys())
    vals = [report["overlap_months"][c] for c in cmts]
    ax.bar(range(len(cmts)), vals, color="steelblue")
    ax.set_xticks(range(len(cmts)))
    ax.set_xticklabels(cmts, rotation=90, fontsize=6)
    ax.set_ylabel("Overlap months (GPP)")
    ax.set_title("Obs-model temporal overlap by CMT")
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    return out_png


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="/mnt/disks/wiemip-data/dvmdostem-ilamb/configs/check_conversions.yaml",
    )
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    site_runs_root = Path(cfg["site_runs_root"])
    records = build_registry(Path(cfg["community_descriptions"]), site_runs_root, None)

    report = validate_conversions(cfg)
    diag_dir = Path(cfg.get("diagnostics_dir", Path(cfg["ilamb_root"]) / "diagnostics"))
    diag_dir.mkdir(parents=True, exist_ok=True)
    report_path = diag_dir / "conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    png_path = plot_diagnostics(cfg, report, records)
    print(f"Wrote {report_path}")
    print(f"Wrote {png_path}")
    if report.get("critical_failures"):
        print("CRITICAL FAILURES:")
        for item in report["critical_failures"]:
            print(f"  - {item}")
        if cfg.get("fail_on_critical", True):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
