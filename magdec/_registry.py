"""
Model registry: maps a date string to the correct WMM epoch and returns a
cached model instance.
"""

import os
from functools import lru_cache
from ._wmm import WMM, _decimal_year, _DATA_DIR

# Each entry: (epoch_start_inclusive, epoch_end_exclusive, model_name, cof_filename)
# Ordered newest first so the first match wins.
_EPOCHS = [
    (2025.0, 2030.0, "WMMHR2025", "WMMHR.COF"),     # high-resolution variant
    (2025.0, 2030.0, "WMM2025",   "WMM2025.COF"),   # standard variant
    (2020.0, 2025.0, "WMM2020",   "WMM2020.COF"),
    (2015.0, 2020.0, "WMM2015v2", "WMM2015v2.COF"),
    (2010.0, 2015.0, "WMM2010",   "WMM2010.COF"),
]

# Only keep epochs whose COF file is present
_AVAILABLE = [
    e for e in _EPOCHS
    if os.path.exists(os.path.join(_DATA_DIR, e[3]))
]

if not _AVAILABLE:
    raise RuntimeError(
        f"No WMM COF files found in {_DATA_DIR}. "
        "Place at least one WMM*.COF file there."
    )

_model_names = [e[2] for e in _AVAILABLE]


@lru_cache(maxsize=8)
def _get_model(cof_filename: str) -> WMM:
    return WMM(os.path.join(_DATA_DIR, cof_filename))


def available_models() -> list[str]:
    """Names of all bundled WMM models, newest first."""
    return list(_model_names)


def model_for_date(date_str: str) -> WMM:
    """Return the WMM model appropriate for *date_str* ('YYYY-MM-DD')."""
    dy = _decimal_year(date_str)
    for start, end, name, fname in _AVAILABLE:
        if start <= dy < end:
            return _get_model(fname)
    # Fall back to the nearest available model rather than raising
    if dy >= _AVAILABLE[0][1]:         # beyond the newest epoch end
        return _get_model(_AVAILABLE[0][3])
    return _get_model(_AVAILABLE[-1][3])  # before the oldest epoch


def get_model(name: str) -> WMM:
    """Return a specific model by name, e.g. 'WMM2020'."""
    for start, end, mname, fname in _AVAILABLE:
        if mname.lower() == name.lower():
            return _get_model(fname)
    raise ValueError(
        f"Model '{name}' not available. "
        f"Available: {_model_names}"
    )
