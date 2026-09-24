"""Unit conversions for carbon flux variables."""

from __future__ import annotations

from .time_utils import days_in_month


def monthly_total_to_daily_rate(
    values,
    years,
    months,
) -> list[float]:
    """Convert g/m2/month totals to g m-2 d-1."""
    out = []
    for value, year, month in zip(values, years, months):
        if value is None or (isinstance(value, float) and __import__("math").isnan(value)):
            out.append(float("nan"))
            continue
        dim = days_in_month(int(year), int(month))
        out.append(float(value) / dim)
    return out


def apply_sign(values, mode: str = "abs") -> list[float]:
    if mode == "raw":
        return [float(v) if v == v else float("nan") for v in values]
    return [abs(float(v)) if v == v else float("nan") for v in values]
