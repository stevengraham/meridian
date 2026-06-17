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
        Copy of *df* with added column(s) named ``{field}_auto`` (for
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

    # Pre-resolve altitude to a per-row array (avoids repeated isinstance checks)
    if alt_m is not None:
        if isinstance(alt_m, str):
            alt_arr = df[alt_m].to_numpy() / 1000.0
        else:
            scalar_km = float(alt_m) / 1000.0
            alt_arr = [scalar_km] * len(df)
    elif isinstance(alt_km, str):
        alt_arr = df[alt_km].to_numpy()
    else:
        scalar_km = float(alt_km)
        alt_arr = [scalar_km] * len(df)

    lat_arr = df[lat].to_numpy()
    lon_arr = df[lon].to_numpy()
    date_arr = df[date].astype(str).to_numpy()

    # Single pass over rows, computing all requested models per row
    results: dict[str, list] = {m: [] for m in model_list}

    for lat_v, lon_v, date_v, h in zip(lat_arr, lon_arr, date_arr, alt_arr):
        lat_f, lon_f, h_f = float(lat_v), float(lon_v), float(h)
        for model_name in model_list:
            if model_name == "auto":
                mdl = model_for_date(date_v)
            else:
                mdl = get_model(model_name)
            res: MagResult = mdl.compute(lat_f, lon_f, h_f, date_v)
            results[model_name].append(getattr(res, field))

    for model_name in model_list:
        col = f"{field}_auto" if model_name == "auto" else f"{field}_{model_name}"
        df[col] = results[model_name]

    return df
