"""CF calendar utilities for ILAMB-compatible monthly time axes."""

from __future__ import annotations

import calendar
from datetime import datetime

import cftime
import numpy as np

TIME_UNITS = "days since 1850-01-01"
CALENDAR = "noleap"


def _origin_offset_days(time_origin: str) -> float:
    origin = datetime.strptime(time_origin, "%Y-%m-%d")
    ref = datetime(1850, 1, 1)
    return float((origin - ref).days)


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def month_starts_from_period(start: datetime, end: datetime) -> list[datetime]:
    import pandas as pd

    periods = pd.period_range(
        start.replace(day=1),
        end.replace(day=1),
        freq="MS",
    )
    return [p.to_timestamp().to_pydatetime() for p in periods]


def month_bounds(year: int, month: int, time_origin: str = "1850-01-01") -> tuple[float, float, float]:
    """Return (time_center, bound_start, bound_end) in days since 1850-01-01."""
    offset = _origin_offset_days(time_origin)
    start = datetime(year, month, 1)
    dim = days_in_month(year, month)
    end = datetime(year, month, dim, 23, 59, 59)
    t0 = (start - datetime(1850, 1, 1)).days - offset
    t1 = (end - datetime(1850, 1, 1)).days + 1 - offset
    tmid = 0.5 * (t0 + t1)
    return float(tmid), float(t0), float(t1)


def build_monthly_time_axis(
    dates: list[datetime],
    time_origin: str = "1850-01-01",
) -> tuple[np.ndarray, np.ndarray]:
    """Build ILAMB monthly time and time_bounds from datetime month starts."""
    if not dates:
        return np.array([]), np.zeros((0, 2))

    unique = sorted({datetime(d.year, d.month, 1) for d in dates})
    times = []
    bounds = []
    for dt in unique:
        tmid, t0, t1 = month_bounds(dt.year, dt.month, time_origin=time_origin)
        times.append(tmid)
        bounds.append([t0, t1])
    return np.asarray(times, dtype=float), np.asarray(bounds, dtype=float)


def fill_continuous_monthly_series(
    years: list[int],
    months: list[int],
    values: list[float],
    time_origin: str = "1850-01-01",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expand sparse monthly values to a gap-free calendar axis for ILAMB."""
    import pandas as pd

    if not years:
        return np.array([]), np.zeros((0, 2)), np.array([])

    df = pd.DataFrame({"year": years, "month": months, "value": values})
    df = df.groupby(["year", "month"], as_index=False)["value"].mean()
    start = datetime(int(df["year"].min()), int(df["month"].min()), 1)
    end = datetime(int(df["year"].max()), int(df["month"].max()), 1)
    full_index = pd.period_range(start, end, freq="M")
    lookup = {(int(r.year), int(r.month)): r.value for r in df.itertuples()}
    filled_years = []
    filled_months = []
    filled_values = []
    for period in full_index:
        key = (period.year, period.month)
        filled_years.append(key[0])
        filled_months.append(key[1])
        filled_values.append(lookup.get(key, np.nan))
    time, bounds = build_monthly_time_axis(
        [datetime(y, m, 1) for y, m in zip(filled_years, filled_months)],
        time_origin=time_origin,
    )
    return time, bounds, np.asarray(filled_values, dtype=float)


def datetime_to_cftime(values) -> list:
    out = []
    for value in values:
        if hasattr(value, "year"):
            out.append(
                cftime.DatetimeNoLeap(value.year, value.month, value.day)
            )
        else:
            out.append(value)
    return out


def model_index_to_year_month(
    time_values,
    model_origin: str = "1901-01-01",
) -> list[tuple[int, int]]:
    """Map model monthly timesteps to calendar year/month using ~31-day steps."""
    origin = datetime.strptime(model_origin, "%Y-%m-%d")
    result = []
    for tval in time_values:
        if hasattr(tval, "year"):
            result.append((int(tval.year), int(tval.month)))
            continue
        days = float(tval)
        dt = origin + __import__("datetime").timedelta(days=int(round(days)))
        result.append((dt.year, dt.month))
    return result
