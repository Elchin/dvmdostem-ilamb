"""Runtime patches for ILAMB compatibility with site-scale DVMDOSTEM outputs."""

from __future__ import annotations


def apply_patches() -> None:
    """Apply minimal ILAMB patches needed for site-format model files."""
    # ModelResult.extractTimeSeries assumes var.area is always set.
    # Upstream fix applied in local ILAMB checkout (area None guard).
    # This function is a hook for future runtime patches if needed.
    return None
