"""Read and normalize ABCFlux observations for a site."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .site_registry import normalize_site_reference
from .units import apply_sign


def load_abcflux_csv(path: Path, encodings: list[str]) -> pd.DataFrame:
    errors = []
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise RuntimeError(f"Could not decode ABCFlux CSV: {path}\n" + "\n".join(errors))


def prepare_abcflux(
    path: Path,
    encodings: list[str],
    sign_mode: str = "abs",
) -> pd.DataFrame:
    df = load_abcflux_csv(path, encodings)
    required = ["site_reference", "year", "month", "gpp", "reco"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"ABCFlux missing columns: {missing}")

    df["site_reference_normalized"] = df["site_reference"].apply(normalize_site_reference)
    for col in ["year", "month", "gpp", "reco"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "nee" in df.columns:
        df["nee"] = pd.to_numeric(df["nee"], errors="coerce")

    df["GPP_obs"] = apply_sign(df["gpp"], sign_mode)
    df["RECO_obs"] = apply_sign(df["reco"], sign_mode)
    df["NPP_obs"] = df["GPP_obs"] - df["RECO_obs"]
    if "nee" in df.columns:
        df["NEE_obs"] = pd.to_numeric(df["nee"], errors="coerce")
    else:
        df["NEE_obs"] = df["RECO_obs"] - df["GPP_obs"]

    df["date"] = pd.to_datetime(
        {"year": df["year"], "month": df["month"], "day": 1},
        errors="coerce",
    )
    return df.dropna(subset=["site_reference_normalized", "date"]).copy()


def extract_abcflux_for_site(
    abcflux: pd.DataFrame,
    site_reference: str,
) -> pd.DataFrame:
    key = normalize_site_reference(site_reference)
    subset = abcflux[abcflux["site_reference_normalized"] == key].copy()
    if subset.empty:
        return pd.DataFrame(columns=["date", "GPP_obs", "RECO_obs", "NPP_obs", "NEE_obs"])
    cols = ["date", "GPP_obs", "RECO_obs", "NPP_obs", "NEE_obs"]
    out = (
        subset[cols]
        .groupby("date", as_index=False)
        .mean(numeric_only=True)
        .sort_values("date")
    )
    return out
