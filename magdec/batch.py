"""
Batch magnetic declination calculation for pandas DataFrames.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from ._wmm import MagResult
from ._registry import model_for_date, get_model, available_models


def declination_batch(
    df: "pd.DataFrame",
    lat: str,
    lon: str,
    date: str,
    alt_km: str | float = 0.0,
    alt_m: str | float | None = None,
    models: list[str] | str = "auto",
    field: str = "D",
) -> "pd.DataFrame":
    """
    Add magnetic field column(s) to *df* and return the modified copy.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    lat : str
        Column name containing geodetic latitude (degrees).
    lon : str
        Column name containing longitude (degrees).
    date : str
        Column name containing ISO date strings ('YYYY-MM-DD').
    alt_km : str or float
        Column name or scalar altitude above WGS-84 ellipsoid in km.
        Default 0.0.  Ignored if *alt_m* is supplied.
    alt_m : str or float or None
        Column name or scalar altitude in metres.  Takes precedence over
        *alt_km* when provided.
    models : list[str] or 'auto' or 'all'
        - ``'auto'``  (default): choose the best bundled model per row date.
        - ``'all'``:  run every available model, adding one column each.
        - list of names: e.g. ``['WMM2020', 'WMM2015v2']``.
    field : str
        Which component to return when adding columns.  One of
        ``'D'`` (declination), ``'I'``, ``'H'``, ``'X'``, ``'Y'``,
        ``'Z'``, ``'F'``.  Default ``'D'``.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with added column(s) named ``declination`` (for
        ``'auto'``) or ``{field}_{model_name}`` (for multi-model runs).
    """
    try:
        import pandas as _pd
    except ImportError as e:
        raise ImportError("pandas is required for batch processing") from e

    df = df.copy()

    if models == "all":
        model_list = available_models()
    elif models == "auto":
        model_list = ["auto"]
    elif isinstance(models, str):
        model_list = [models]
    else:
        model_list = list(models)

    for model_name in model_list:
        col = "declination" if model_name == "auto" else f"{field}_{model_name}"
        results = []
        for _, row in df.iterrows():
            lat_v  = float(row[lat])
            lon_v  = float(row[lon])
            date_v = str(row[date])

            if alt_m is not None:
                h = float(row[alt_m]) / 1000.0 if isinstance(alt_m, str) else float(alt_m) / 1000.0
            elif isinstance(alt_km, str):
                h = float(row[alt_km])
            else:
                h = float(alt_km)

            if model_name == "auto":
                mdl = model_for_date(date_v)
            else:
                mdl = get_model(model_name)

            res: MagResult = mdl.compute(lat_v, lon_v, h, date_v)
            results.append(getattr(res, field))

        df[col] = results

    return df
