import math
from qgis.core import QgsPointXY, QgsCoordinateTransform, QgsCoordinateReferenceSystem


def compute_grid_convergence(lon: float, lat: float, layer_crs, project) -> float | None:
    """
    Grid convergence at (lon, lat) for layer_crs — the angle from true north
    to grid north, in degrees east (positive = grid east of true north).

    Returns None when layer_crs is geographic (no grid north concept).

    Uses a numerical approach: projects a point 0.001° true north and measures
    the bearing of that displacement in the projected coordinate system.
    Works for any projected CRS without needing to decode projection parameters.

    Note: QgsCsException from transform() (point outside valid extent) propagates
    to the caller.
    """
    if layer_crs.isGeographic():
        return None

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    to_proj = QgsCoordinateTransform(wgs84, layer_crs, project)
    return _gc_from_transform(lon, lat, to_proj)


def _gc_from_transform(lon: float, lat: float, to_proj) -> float:
    """Compute grid convergence using a pre-built wgs84→layer_crs transform.

    Intended for batch use where the caller constructs *to_proj* once before
    the loop to avoid per-feature CRS/transform construction overhead.
    """
    lat_north = min(lat + 0.001, 89.999)   # clamp to avoid polar singularity
    p       = to_proj.transform(QgsPointXY(lon, lat))
    p_north = to_proj.transform(QgsPointXY(lon, lat_north))
    dE = p_north.x() - p.x()
    dN = p_north.y() - p.y()
    return math.degrees(math.atan2(dE, dN))
