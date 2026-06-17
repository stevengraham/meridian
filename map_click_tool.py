from qgis.gui import QgsMapTool
from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsProject


class NorthClickTool(QgsMapTool):
    """
    Map click tool: user clicks the canvas, the point is back-projected to
    WGS84 and returned via callback(lon, lat).

    Full wiring implemented in Block 3.
    """

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self._callback = callback

    def canvasReleaseEvent(self, event):
        point_canvas = event.mapPoint()
        canvas_crs = self.canvas().mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        xf = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
        point_wgs84 = xf.transform(point_canvas)
        self._callback(point_wgs84.x(), point_wgs84.y())  # lon, lat
