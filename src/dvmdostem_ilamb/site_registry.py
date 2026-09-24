"""Site registry from Community_Descriptions and Site_Runs directories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_site_reference(value) -> str:
    value = normalize_text(value)
    return re.sub(r"\s+", " ", value).lower()


def normalize_column_name(value) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def canonical_cmt(value) -> str | None:
    if pd.isna(value):
        return None
    match = re.search(r"(\d+)", str(value))
    if not match:
        return None
    return f"CMT{int(match.group(1)):02d}"


@dataclass
class SiteRecord:
    cmt: str
    site_name: str
    community_type: str
    site_reference: str
    lat: float
    lon: float
    input_catalog: str
    obs_source: str  # abcflux | fallback | none


def load_community_descriptions(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        df = pd.read_csv(path, sep=None, engine="python")
    except Exception:
        df = pd.read_csv(path, sep="\t")
    df.columns = [str(c).strip() for c in df.columns]
    df["CMT_canonical"] = df["CMT"].apply(canonical_cmt)
    return df


def discover_site_runs(site_runs_root: Path) -> list[str]:
    cmts = []
    for path in sorted(site_runs_root.iterdir()):
        if path.is_dir() and canonical_cmt(path.name):
            cmts.append(canonical_cmt(path.name))
    return cmts


def build_registry(
    community_path: Path,
    site_runs_root: Path,
    cmt_include: list[str] | None = None,
) -> list[SiteRecord]:
    df = load_community_descriptions(community_path)
    available = set(discover_site_runs(site_runs_root))
    include = {canonical_cmt(c) for c in cmt_include} if cmt_include else available

    records: list[SiteRecord] = []
    for _, row in df.iterrows():
        cmt = row.get("CMT_canonical")
        if cmt not in available or cmt not in include:
            continue
        site_ref = normalize_text(row.get("site_reference", ""))
        obs_source = "abcflux" if site_ref else "fallback"
        records.append(
            SiteRecord(
                cmt=cmt,
                site_name=normalize_text(row.get("Site Name", "")),
                community_type=normalize_text(row.get("Community Type", "")),
                site_reference=site_ref,
                lat=float(row["Lat"]),
                lon=float(row["Lon"]),
                input_catalog=normalize_text(row.get("input-catalog", "")),
                obs_source=obs_source,
            )
        )
    return records
