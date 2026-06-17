import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


def _icon_path():
    """Path to the plugin icon, preferring the scalable SVG (crisp at any DPI),
    falling back to the raster PNG. Returns None if neither is present."""
    here = os.path.dirname(__file__)
    for name in ("icon.svg", "icon.png"):
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    return None


class MeridianPlugin:
    def __init__(self, iface):
        self.iface = iface
        self._action = None
        self._dialog = None

    def initGui(self):
        icon_path = _icon_path()
        icon = QIcon(icon_path) if icon_path else QIcon()
        self._action = QAction(icon, "Meridian…", self.iface.mainWindow())
        self._action.setToolTip("Add magnetic declination and grid convergence to a layer")
        self._action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self._action)
        self.iface.addPluginToVectorMenu("&Meridian", self._action)

    def unload(self):
        self.iface.removePluginVectorMenu("&Meridian", self._action)
        self.iface.removeToolBarIcon(self._action)
        if self._dialog is not None:
            active = getattr(self._dialog, '_active_task', None)
            if active is not None:
                active.cancel()
                self._dialog._active_task = None
            self._dialog.close()
            self._dialog = None

    def run(self):
        if self._dialog is None:
            from .dialog import MeridianDialog
            self._dialog = MeridianDialog(self.iface, parent=self.iface.mainWindow())
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
