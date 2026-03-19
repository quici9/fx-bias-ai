"""
Publication lag rules for FX Bias AI pipeline.

Single source of truth for how much lag each data series has
before it becomes publicly available. Prevents look-ahead bias
in feature engineering and model training.

Reference: System Design Section 5.2
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

PUBLICATION_LAG = {
    "cpi": {"unit": "month", "lag": -2},
    "gdp": {"unit": "quarter", "lag": -1},
    "pmi": {"unit": "month", "lag": -1},
    "policy_rate": {"unit": "month", "lag": 0},
    "cot": {"unit": "day", "lag": -3},
    "price": {"unit": "day", "lag": 0},
    "yield_10y": {"unit": "day", "lag": 0},
}

SUPPORTED_SERIES_TYPES = frozenset(PUBLICATION_LAG.keys())


def get_valid_date_for(series_type: str, as_of: date) -> date:
    """
    Return the latest date for which data of `series_type` is publicly
    available as of `as_of`, accounting for publication lag.

    This prevents look-ahead bias by ensuring we never use data that
    would not have been available at the time of prediction.

    Args:
        series_type: One of PUBLICATION_LAG keys (cpi, gdp, pmi, etc.)
        as_of: The reference date (typically the prediction date)

    Returns:
        The latest date for which the data is available

    Raises:
        ValueError: If series_type is not recognized
    """
    if series_type not in PUBLICATION_LAG:
        raise ValueError(
            f"Unknown series_type '{series_type}'. "
            f"Supported: {sorted(SUPPORTED_SERIES_TYPES)}"
        )

    rule = PUBLICATION_LAG[series_type]
    unit = rule["unit"]
    lag = rule["lag"]

    if unit == "month":
        return as_of + relativedelta(months=lag)
    elif unit == "quarter":
        return as_of + relativedelta(months=lag * 3)
    elif unit == "day":
        return as_of + timedelta(days=lag)
    else:
        raise ValueError(f"Unsupported unit '{unit}' for series '{series_type}'")


def get_lag_description(series_type: str) -> str:
    """Return a human-readable description of the lag rule for a series."""
    if series_type not in PUBLICATION_LAG:
        raise ValueError(f"Unknown series_type '{series_type}'")

    rule = PUBLICATION_LAG[series_type]
    lag = rule["lag"]
    unit = rule["unit"]

    if lag == 0:
        return f"{series_type}: real-time (no lag)"

    abs_lag = abs(lag)
    if unit == "quarter":
        return f"{series_type}: {abs_lag} quarter(s) lag"

    return f"{series_type}: {abs_lag} {unit}(s) lag"
