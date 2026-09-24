"""Read fallback site observation CSV files."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .site_registry import canonical_cmt, normalize_column_name


def find_fallback_cmt_directory(observations_root: Path, cmt: str) -> Path | None:
    wanted = canonical_cmt(cmt)
    if not observations_root.exists():
        return None
    for path in observations_root.iterdir():
        if path.is_dir() and canonical_cmt(path.name) == wanted:
            return path
    for path in observations_root.rglob("*"):
        if path.is_dir() and canonical_cmt(path.name) == wanted:
            return path
    return None


def resolve_fallback_files(
    observations_root: Path,
    cmt: str,
    fallback_cmt_map: dict,
    catalog_prefixes: dict,
    input_catalog: str,
) -> list[Path]:
    files: list[Path] = []
    cmt_dir = find_fallback_cmt_directory(observations_root, cmt)
    if cmt_dir is not None:
        files.extend(sorted(cmt_dir.rglob("*.csv")))

    for rel in fallback_cmt_map.get(cmt, []):
        path = Path(rel)
        if not path.is_absolute():
            path = observations_root / rel
        if path.exists():
            files.append(path)

    prefix = catalog_prefixes.get(input_catalog, "")
    if prefix and observations_root.exists():
        for var in ("gpp", "reco", "nee", "npp"):
            candidate = observations_root / f"{prefix}_{var}.csv"
            if candidate.exists():
                files.append(candidate)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for path in files:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def read_fallback_csv(path: Path, encodings: list[str]) -> pd.DataFrame | None:
    for encoding in encodings:
        try:
            df = pd.read_csv(path, encoding=encoding, low_memory=False)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def find_fallback_dates(df: pd.DataFrame) -> pd.Series | None:
    normalized = {col: normalize_column_name(col) for col in df.columns}
    for preferred in ("date", "datetime", "timestamp", "time", "date_time"):
        for col, norm in normalized.items():
            if norm == preferred:
                dates = pd.to_datetime(df[col], errors="coerce")
                if dates.notna().any():
                    return dates.dt.to_period("M").dt.to_timestamp()
    year_col = month_col = None
    for col, norm in normalized.items():
        if norm in ("year", "yr"):
            year_col = col
        elif norm in ("month", "mo"):
            month_col = col
    if year_col and month_col:
        dates = pd.to_datetime(
            {"year": pd.to_numeric(df[year_col], errors="coerce"),
             "month": pd.to_numeric(df[month_col], errors="coerce"),
             "day": 1},
            errors="coerce",
        )
        if dates.notna().any():
            return dates
    return None


def find_fallback_variable_column(df: pd.DataFrame, variable: str) -> str | None:
    normalized = {col: normalize_column_name(col) for col in df.columns}
    aliases = {
        "GPP": {"gpp", "gpp_obs", "gross_primary_productivity"},
        "NPP": {"npp", "npp_obs", "net_primary_productivity"},
        "RECO": {"reco", "reco_obs", "respiration", "ecosystem_respiration", "er"},
        "NEE": {"nee", "nee_obs", "net_ecosystem_exchange"},
    }
    wanted = aliases[variable.upper()]
    for col, norm in normalized.items():
        if norm in wanted:
            return col
    for col, norm in normalized.items():
        if variable.lower() in norm and "error" not in norm and "std" not in norm:
            return col
    return None


def _extract_long_format(df: pd.DataFrame, dates: pd.Series) -> pd.DataFrame | None:
    """Handle measurement/value long-format CSVs."""
    meas_col = val_col = None
    for col in df.columns:
        norm = normalize_column_name(col)
        if norm in ("measurement", "variable"):
            meas_col = col
        if norm in ("value",):
            val_col = col
    if meas_col is None or val_col is None:
        return None

    frames = []
    mapping = {
        "GPP": "GPP_obs",
        "NPP": "NPP_obs",
        "RECO": "RECO_obs",
        "NEE": "NEE_obs",
    }
    meas = df[meas_col].astype(str).str.upper()
    for key, out_col in mapping.items():
        mask = meas.str.contains(key, na=False)
        if not mask.any():
            continue
        sub = pd.DataFrame(
            {
                "date": dates[mask].values,
                out_col: pd.to_numeric(df.loc[mask, val_col], errors="coerce").values,
            }
        )
        frames.append(sub)
    if not frames:
        return None
    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="date", how="outer")
    return out.groupby("date", as_index=False).mean(numeric_only=True)


def load_fallback_observations(
    observations_root: Path,
    cmt: str,
    fallback_cmt_map: dict,
    catalog_prefixes: dict,
    input_catalog: str,
    encodings: list[str],
) -> pd.DataFrame:
    csv_files = resolve_fallback_files(
        observations_root, cmt, fallback_cmt_map, catalog_prefixes, input_catalog
    )
    variable_frames = []
    for path in csv_files:
        df = read_fallback_csv(path, encodings)
        if df is None or df.empty:
            continue
        dates = find_fallback_dates(df)
        if dates is None:
            continue

        long_df = _extract_long_format(df, dates)
        if long_df is not None:
            variable_frames.append(long_df)
            continue

        for var in ("GPP", "NPP", "RECO", "NEE"):
            col = find_fallback_variable_column(df, var)
            if col is None:
                continue
            variable_frames.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        f"{var}_obs": pd.to_numeric(df[col], errors="coerce"),
                    }
                )
            )

    if not variable_frames:
        return pd.DataFrame(columns=["date", "GPP_obs", "RECO_obs", "NPP_obs", "NEE_obs"])

    obs = variable_frames[0]
    for temp in variable_frames[1:]:
        obs = obs.merge(temp, on="date", how="outer")
    obs = obs.groupby("date", as_index=False).mean(numeric_only=True)
    for col in ("GPP_obs", "NPP_obs", "RECO_obs", "NEE_obs"):
        if col not in obs.columns:
            obs[col] = np.nan

    if not obs["NPP_obs"].notna().any() and obs["GPP_obs"].notna().any() and obs["RECO_obs"].notna().any():
        obs["NPP_obs"] = obs["GPP_obs"] - obs["RECO_obs"]
    if not obs["NEE_obs"].notna().any() and obs["GPP_obs"].notna().any() and obs["RECO_obs"].notna().any():
        obs["NEE_obs"] = obs["RECO_obs"] - obs["GPP_obs"]

    obs = obs.dropna(subset=["GPP_obs", "NPP_obs", "RECO_obs", "NEE_obs"], how="all")
    return obs.sort_values("date").reset_index(drop=True)
