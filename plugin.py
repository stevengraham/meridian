import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class MeridianPlugin:
    def __init__(self, iface):
        self.iface = iface
        self._action = None
        self._dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self._action = QAction(icon, "Meridian…", self.iface.mainWindow())
        self._action.setToolTip("Add magnetic declination and grid convergence to a layer")
        self._action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self._action)
        self.iface.addPluginToVectorMenu("&Meridian", self._action)

    def unload(self):
        self.iface.removePluginVectorMenu("&Meridian", self._action)
        self.iface.removeToolBarIcon(self._action)
        if self._dialog is not None:
            self._dialog.close()
            self._dialog = None

    def run(self):
        if self._dialog is None:
            from .dialog import MeridianDialog
            self._dialog = MeridianDialog(self.iface, parent=self.iface.mainWindow())
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
