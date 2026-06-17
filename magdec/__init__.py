"""
magdec — offline magnetic declination for single points and DataFrames.

Bundled models: WMM2010, WMM2015v2, WMM2020, WMMHR2025 (high-resolution,
n=133, default for 2025–2030).  Additional epochs can be added by placing
a WMM*.COF file in magdec/data/ — see data/WMM2025.md.

Quick start
-----------
>>> import magdec
>>> magdec.declination(-31.95, 115.86, '2024-06-17')     # Perth, WA
1.76...
>>> magdec.declination(-31.95, 115.86, '2024-06-17', model='all')
{'WMMHR2025': ..., 'WMM2020': 1.76..., 'WMM2015v2': ..., 'WMM2010': ...}
>>> result = magdec.components(-31.95, 115.86, '2024-06-17')
>>> result.D, result.F
(1.76..., 57234.3...)

Batch (pandas)
--------------
>>> out = magdec.declination_batch(df, lat='lat', lon='lon', date='date')
# adds column 'D_auto'; use field='F' etc. for other components
"""

from ._wmm import MagResult
from ._registry import available_models, model_for_date, get_model
from .batch import declination_batch

__all__ = [
    "declination",
    "components",
    "declination_batch",
    "available_models",
    "MagResult",
]

__version__ = "0.1.0"


def declination(
    lat: float,
    lon: float,
    date: str,
    *,
    alt_km: float = 0.0,
    alt_m: float | None = None,
    model: str = "auto",
) -> float | dict[str, float]:
    """
    Magnetic declination at a single point.

    Parameters
    ----------
    lat : float   Geodetic latitude, degrees (−90 … +90).
    lon : float   Longitude, degrees (−180 … +180).
    date : str    ISO date string, e.g. ``'2024-06-17'``.
    alt_km : float
        Altitude above WGS-84 ellipsoid in km.  Default sea level (0.0).
    alt_m : float or None
        Altitude in metres.  Takes precedence over *alt_km* when given.
    model : str
        ``'auto'``  — pick the best bundled model for the date (default).
        ``'all'``   — return a ``dict`` of ``{model_name: declination}``
                      for every available model.
        Model name  — e.g. ``'WMM2020'``, ``'WMM2015v2'``.

    Returns
    -------
    float
        Declination in degrees east (positive = east of true north).
        Returns a ``dict[str, float]`` when ``model='all'``.
    """
    h = _resolve_alt(alt_km, alt_m)
    if model == "all":
        return {
            name: get_model(name).compute(lat, lon, h, date).D
            for name in available_models()
        }
    mdl = model_for_date(date) if model == "auto" else get_model(model)
    return mdl.compute(lat, lon, h, date).D


def components(
    lat: float,
    lon: float,
    date: str,
    *,
    alt_km: float = 0.0,
    alt_m: float | None = None,
    model: str = "auto",
) -> MagResult:
    """
    All magnetic field components at a single point.

    Returns a :class:`MagResult` with attributes
    ``D``, ``I``, ``H``, ``X``, ``Y``, ``Z``, ``F``, ``model``, ``date``.

    Parameters are identical to :func:`declination`.
    """
    h = _resolve_alt(alt_km, alt_m)
    mdl = model_for_date(date) if model == "auto" else get_model(model)
    return mdl.compute(lat, lon, h, date)


def _resolve_alt(alt_km: float, alt_m: float | None) -> float:
    if alt_m is not None:
        return alt_m / 1000.0
    return alt_km
