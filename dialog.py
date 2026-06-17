import os
from datetime import date, datetime

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QDate, QVariant
from qgis.PyQt.QtWidgets import (
    QButtonGroup, QDialog, QTableWidgetItem
)
from qgis.core import (
    QgsProject, QgsWkbTypes, QgsVectorLayer,
    QgsFields, QgsField, QgsFeature, QgsGeometry,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsMemoryProviderUtils, QgsTask, QgsApplication,
)

from . import magdec
from .grid_convergence import compute_grid_convergence
from .map_click_tool import NorthClickTool
from .report import save_report as _save_report_file

UI_FILE = os.path.join(os.path.dirname(__file__), "dialog_base.ui")

_COMP_ATTRS = ("I", "H", "F", "X", "Y", "Z")


def _comp_values(r) -> list:
    if r is None:
        return [None] * 6
    return [r.I, r.H, r.F, r.X, r.Y, r.Z]


def _comp_fields(suffix: str) -> list:
    return [QgsField(f"{a}_{suffix}", QVariant.Double, "double", 12, 4)
            for a in _COMP_ATTRS]


class _ComputeTask(QgsTask):
    """Background task: compute north corrections for all pre-read features."""

    def __init__(
        self, *,
        feat_list,
        out_fields,
        out_name,
        out_wkb_type,
        out_crs,
        fallback_date,
        mode,
        model_names,
        is_polygon,
        layer_crs_authid,
        want_decl,
        want_gc,
        want_gma,
        want_components,
        finished_cb,
    ):
        super().__init__("Meridian: computing…", QgsTask.CanCancel)
        self._feat_list = feat_list
        self._out_fields = out_fields
        self._out_name = out_name
        self._out_wkb_type = out_wkb_type
        self._out_crs = out_crs
        self._fallback_date = fallback_date
        self._mode = mode
        self._model_names = model_names
        self._is_polygon = is_polygon
        self._layer_crs_authid = layer_crs_authid
        self._want_decl = want_decl
        self._want_gc = want_gc
        self._want_gma = want_gma
        self._want_components = want_components
        self._finished_cb = finished_cb
        self._out_feats = []
        self._errors = 0

    def run(self) -> bool:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        layer_crs = QgsCoordinateReferenceSystem(self._layer_crs_authid)
        transform = QgsCoordinateTransform(layer_crs, wgs84, QgsProject.instance())
        total = len(self._feat_list)

        for i, item in enumerate(self._feat_list):
            if self.isCanceled():
                return False

            geom: QgsGeometry = item["geom"]
            attrs = item["attrs"]
            date_val = item["date_val"]

            pt_geom = geom.pointOnSurface() if self._is_polygon else geom
            try:
                pt_wgs84 = transform.transform(pt_geom.asPoint())
            except Exception:
                self._errors += 1
                continue

            lat, lon = pt_wgs84.y(), pt_wgs84.x()

            date_str = self._fallback_date
            if date_val is not None:
                parsed = MeridianDialog._parse_date_value(date_val)
                if parsed:
                    date_str = parsed

            gamma = compute_grid_convergence(lon, lat, layer_crs, QgsProject.instance())

            mode = self._mode
            model_names = self._model_names

            if mode == "auto":
                try:
                    r = magdec.components(lat, lon, date_str, model="auto")
                    decl_auto, actual_model, comps_auto = r.D, r.model, r
                except Exception:
                    decl_auto = actual_model = comps_auto = None
                    self._errors += 1

            elif mode == "all":
                all_d: dict = {}
                comps_all: dict = {}
                for m in model_names:
                    try:
                        if self._want_components:
                            r = magdec.components(lat, lon, date_str, model=m)
                            all_d[m] = r.D
                            comps_all[m] = r
                        else:
                            all_d[m] = magdec.declination(lat, lon, date_str, model=m)
                    except Exception:
                        all_d[m] = None
                        comps_all[m] = None
                        self._errors += 1

            else:  # specific
                m = model_names[0]
                try:
                    if self._want_components:
                        r = magdec.components(lat, lon, date_str, model=m)
                        d_specific, comps_spec = r.D, r
                    else:
                        d_specific = magdec.declination(lat, lon, date_str, model=m)
                        comps_spec = None
                except Exception:
                    d_specific = comps_spec = None
                    self._errors += 1

            new_attrs = list(attrs)

            if self._want_decl:
                if mode == "auto":
                    new_attrs += [decl_auto, actual_model]
                elif mode == "all":
                    new_attrs += [all_d.get(m) for m in model_names]
                else:
                    new_attrs.append(d_specific)

            if self._want_gc:
                new_attrs.append(gamma)

            if self._want_gma:
                if mode == "auto":
                    new_attrs.append(
                        (decl_auto - gamma)
                        if (decl_auto is not None and gamma is not None) else None
                    )
                elif mode == "all":
                    for m in model_names:
                        d = all_d.get(m)
                        new_attrs.append(
                            (d - gamma) if (d is not None and gamma is not None) else None
                        )
                else:
                    new_attrs.append(
                        (d_specific - gamma)
                        if (d_specific is not None and gamma is not None) else None
                    )

            if self._want_components:
                if mode == "auto":
                    new_attrs += _comp_values(comps_auto)
                elif mode == "all":
                    for m in model_names:
                        new_attrs += _comp_values(comps_all.get(m))
                else:
                    new_attrs += _comp_values(comps_spec)

            new_attrs.append(date_str)

            out_feat = QgsFeature(self._out_fields)
            out_feat.setGeometry(QgsGeometry(geom))
            out_feat.setAttributes(new_attrs)
            self._out_feats.append(out_feat)

            self.setProgress(100 * (i + 1) / total)

        return True

    def finished(self, result: bool):
        self._finished_cb(
            self._out_feats, self._errors,
            self._out_name, self._out_fields,
            self._out_wkb_type, self._out_crs, result,
        )


class MeridianDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent, Qt.Window)
        uic.loadUi(UI_FILE, self)
        from qgis.PyQt.QtGui import QIcon
        _icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))
        self.iface = iface
        self._click_tool = None
        self._prev_tool = None
        self._active_task = None
        self._last_result = None   # populated after each manual compute

        for btn in (self.rbLayer, self.rbManual, self.rbPoints, self.rbPolygons):
            btn.setAutoExclusive(False)
        self._source_group = QButtonGroup(self)
        self._source_group.addButton(self.rbLayer)
        self._source_group.addButton(self.rbManual)
        self._geom_group = QButtonGroup(self)
        self._geom_group.addButton(self.rbPoints)
        self._geom_group.addButton(self.rbPolygons)

        self._init_date()
        self._populate_models()
        self._populate_layers()
        self._wire_signals()
        self.rbManual.setChecked(True)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_date(self):
        self.dateEdit.setDate(QDate.currentDate())

    def _populate_models(self):
        self.modelCombo.clear()
        for name in magdec.available_models():
            self.modelCombo.addItem(name)

    def _populate_layers(self):
        self.layerCombo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
                geom_type = layer.geometryType()
                if geom_type in (QgsWkbTypes.PointGeometry, QgsWkbTypes.PolygonGeometry):
                    self.layerCombo.addItem(layer.name(), layer.id())
        active = self.iface.activeLayer()
        if isinstance(active, QgsVectorLayer) and active.isSpatial():
            idx = self.layerCombo.findData(active.id())
            if idx >= 0:
                self.layerCombo.setCurrentIndex(idx)
        self._on_layer_changed()

    def _wire_signals(self):
        self.rbLayer.toggled.connect(self._on_source_mode_changed)
        self.rbManual.toggled.connect(self._on_source_mode_changed)

        self.layerCombo.currentIndexChanged.connect(self._on_layer_changed)

        self.rbSingleDate.toggled.connect(lambda checked: self.dateFieldCombo.setEnabled(not checked))
        self.rbDateField.toggled.connect(lambda checked: self.dateFieldCombo.setEnabled(checked))

        self.rbModelAuto.toggled.connect(lambda _: self._update_wmmhr_warning())
        self.rbModelAll.toggled.connect(lambda _: self._update_wmmhr_warning())
        self.rbModelSpecific.toggled.connect(lambda _: self._update_wmmhr_warning())
        self.rbModelSpecific.toggled.connect(self.modelCombo.setEnabled)
        self.modelCombo.currentTextChanged.connect(lambda _: self._update_wmmhr_warning())

        self.btnPickFromMap.clicked.connect(self._on_pick_from_map)
        self.btnCompute.clicked.connect(self._on_compute)
        self.btnClose.clicked.connect(self.close)
        self.btnSavePdf.clicked.connect(lambda: self._on_save_report("pdf"))
        self.btnSavePng.clicked.connect(lambda: self._on_save_report("png"))

    # ------------------------------------------------------------------
    # UI state callbacks
    # ------------------------------------------------------------------

    def _on_source_mode_changed(self):
        layer_mode = self.rbLayer.isChecked()
        self.layerCombo.setEnabled(layer_mode)
        self.rbPoints.setEnabled(layer_mode)
        self.rbPolygons.setEnabled(layer_mode)
        self.lblGeomType.setEnabled(layer_mode)
        self.spinLat.setEnabled(not layer_mode)
        self.spinLon.setEnabled(not layer_mode)
        self.btnPickFromMap.setEnabled(not layer_mode)
        self.grpResults.setVisible(not layer_mode)
        if layer_mode:
            self.editOutputName.setEnabled(True)
        self.adjustSize()

    def _on_layer_changed(self):
        layer = self._current_layer()
        if layer is None:
            return
        geom_type = layer.geometryType()
        if geom_type == QgsWkbTypes.PolygonGeometry:
            self.rbPolygons.setChecked(True)
        else:
            self.rbPoints.setChecked(True)
        self.dateFieldCombo.clear()
        _EXCLUDE = {"geometry", "binary", "blob", "bytea"}
        for field in layer.fields():
            if field.typeName().lower() not in _EXCLUDE:
                self.dateFieldCombo.addItem(field.name())
        self.editOutputName.setText(f"{layer.name()}_north_corrections")

    def _update_wmmhr_warning(self):
        any_wmmhr = any("WMMHR" in m.upper() for m in magdec.available_models())
        if self.rbModelAuto.isChecked() or self.rbModelAll.isChecked():
            self.lblWmmhrWarning.setVisible(any_wmmhr)
        else:
            self.lblWmmhrWarning.setVisible(
                "WMMHR" in self.modelCombo.currentText().upper()
            )

    def _on_pick_from_map(self, checked: bool):
        if checked:
            canvas = self.iface.mapCanvas()
            self._prev_tool = canvas.mapTool()
            self._click_tool = NorthClickTool(canvas, self._on_map_clicked)
            self._click_tool.deactivated.connect(self._deactivate_click_tool)
            canvas.setMapTool(self._click_tool)
            self.iface.messageBar().pushInfo(
                "Meridian", "Click the map to pick a point."
            )
        else:
            self._deactivate_click_tool()

    def _on_map_clicked(self, lon: float, lat: float):
        self.spinLat.setValue(lat)
        self.spinLon.setValue(lon)
        self._compute_manual()

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def _on_compute(self):
        if self.rbLayer.isChecked():
            self._compute_layer()
        else:
            self._compute_manual()

    def _compute_manual(self):
        lat = self.spinLat.value()
        lon = self.spinLon.value()
        date_str = self.dateEdit.date().toString("yyyy-MM-dd")
        models = self._selected_models()
        want_comps = self.chkComponents.isChecked()

        self.grpResults.setVisible(True)
        self.resultsTable.setRowCount(0)

        if want_comps:
            self.resultsTable.setColumnCount(10)
            self.resultsTable.setHorizontalHeaderLabels([
                "Model", "D (°E)", "γ (°E)", "GMA (°)",
                "I (°)", "H (nT)", "F (nT)", "X (nT)", "Y (nT)", "Z (nT)",
            ])
        else:
            self.resultsTable.setColumnCount(4)
            self.resultsTable.setHorizontalHeaderLabels([
                "Model", "Magnetic Declination (°E)",
                "Grid Convergence (°E)", "Grid Magnetic Angle (°)",
            ])

        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        gamma = compute_grid_convergence(lon, lat, canvas_crs, QgsProject.instance())
        gamma_str = f"{gamma:+.4f}" if gamma is not None else "N/A"

        # First result captured for the report (single-model preferred)
        first_result = None

        for model_name in models:
            try:
                if model_name == "auto" or want_comps:
                    actual_model = model_name if model_name != "auto" else None
                    r = magdec.components(lat, lon, date_str, model=model_name)
                    d = r.D
                    actual_model = r.model
                else:
                    r = None
                    d = magdec.declination(lat, lon, date_str, model=model_name)
                    actual_model = model_name
            except Exception:
                d = float("nan")
                r = None
                actual_model = model_name

            gma = (d - gamma) if (gamma is not None and d == d) else float("nan")
            display_model = actual_model if model_name == "auto" else model_name

            row = self.resultsTable.rowCount()
            self.resultsTable.insertRow(row)
            self.resultsTable.setItem(row, 0, QTableWidgetItem(display_model or ""))
            self.resultsTable.setItem(row, 1, QTableWidgetItem(f"{d:+.4f}"))
            self.resultsTable.setItem(row, 2, QTableWidgetItem(gamma_str))
            self.resultsTable.setItem(row, 3, QTableWidgetItem(
                f"{gma:+.4f}" if gamma is not None else "N/A"
            ))
            if want_comps and r is not None:
                self.resultsTable.setItem(row, 4, QTableWidgetItem(f"{r.I:+.4f}"))
                self.resultsTable.setItem(row, 5, QTableWidgetItem(f"{r.H:.2f}"))
                self.resultsTable.setItem(row, 6, QTableWidgetItem(f"{r.F:.2f}"))
                self.resultsTable.setItem(row, 7, QTableWidgetItem(f"{r.X:.2f}"))
                self.resultsTable.setItem(row, 8, QTableWidgetItem(f"{r.Y:.2f}"))
                self.resultsTable.setItem(row, 9, QTableWidgetItem(f"{r.Z:.2f}"))

            # Capture the first valid result for the report
            if first_result is None and d == d:  # not NaN
                first_result = {
                    "lat": lat,
                    "lon": lon,
                    "date_str": date_str,
                    "model": display_model or model_name,
                    "crs_name": canvas_crs.description() if not canvas_crs.isGeographic()
                                else "",
                    "declination": d,
                    "grid_convergence": gamma,
                    "components": (
                        {"I": r.I, "H": r.H, "F": r.F,
                         "X": r.X, "Y": r.Y, "Z": r.Z}
                        if (want_comps and r is not None) else None
                    ),
                }

        self.resultsTable.resizeColumnsToContents()
        self.adjustSize()

        # Compute annual rate of change of declination (numerical, ±1 year)
        if first_result is not None:
            try:
                from datetime import timedelta
                d1 = datetime.strptime(date_str, "%Y-%m-%d")
                d2 = (d1 + timedelta(days=365)).strftime("%Y-%m-%d")
                decl2 = magdec.declination(
                    lat, lon, d2, model=first_result["model"]
                )
                first_result["annual_rate"] = decl2 - first_result["declination"]
            except Exception:
                first_result["annual_rate"] = None

        self._last_result = first_result
        has_result = first_result is not None
        self.btnSavePdf.setEnabled(has_result)
        self.btnSavePng.setEnabled(has_result)

    def _compute_layer(self):
        from qgis.PyQt.QtWidgets import QMessageBox

        layer = self._current_layer()
        if layer is None:
            QMessageBox.warning(self, "Meridian", "No layer selected.")
            return

        fallback_date = self.dateEdit.date().toString("yyyy-MM-dd")
        use_date_field = self.rbDateField.isChecked()
        date_field_name = self.dateFieldCombo.currentText() if use_date_field else None

        want_decl = self.chkDeclination.isChecked()
        want_gc = self.chkGridConv.isChecked()
        want_gma = self.chkGma.isChecked()
        want_components = self.chkComponents.isChecked()

        if self.rbModelAuto.isChecked():
            mode = "auto"
            model_names = []
        elif self.rbModelAll.isChecked():
            mode = "all"
            model_names = magdec.available_models()
        else:
            mode = "specific"
            model_names = [self.modelCombo.currentText()]

        # Build output field schema
        out_fields = QgsFields()
        for f in layer.fields():
            out_fields.append(f)

        if want_decl:
            if mode == "auto":
                out_fields.append(QgsField("mag_decl_auto", QVariant.Double, "double", 12, 6))
                out_fields.append(QgsField("model_used", QVariant.String, "string", 20))
            elif mode == "all":
                for m in model_names:
                    out_fields.append(QgsField(f"mag_decl_{m}", QVariant.Double, "double", 12, 6))
            else:
                out_fields.append(QgsField(f"mag_decl_{model_names[0]}", QVariant.Double, "double", 12, 6))

        if want_gc:
            out_fields.append(QgsField("grid_conv", QVariant.Double, "double", 12, 6))

        if want_gma:
            if mode == "auto":
                out_fields.append(QgsField("gma_auto", QVariant.Double, "double", 12, 6))
            elif mode == "all":
                for m in model_names:
                    out_fields.append(QgsField(f"gma_{m}", QVariant.Double, "double", 12, 6))
            else:
                out_fields.append(QgsField(f"gma_{model_names[0]}", QVariant.Double, "double", 12, 6))

        if want_components:
            if mode == "auto":
                for f in _comp_fields("auto"):
                    out_fields.append(f)
            elif mode == "all":
                for m in model_names:
                    for f in _comp_fields(m):
                        out_fields.append(f)
            else:
                for f in _comp_fields(model_names[0]):
                    out_fields.append(f)

        out_fields.append(QgsField("decl_date", QVariant.String, "string", 10))

        out_name = self.editOutputName.text().strip() or "north_corrections_output"
        is_polygon = layer.geometryType() == QgsWkbTypes.PolygonGeometry

        # Pre-read features on the main thread
        feat_list = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            date_val = feat[date_field_name] if (use_date_field and date_field_name) else None
            feat_list.append({
                "geom": QgsGeometry(geom),
                "attrs": list(feat.attributes()),
                "date_val": date_val,
            })

        if not feat_list:
            QMessageBox.information(self, "Meridian", "No valid features found.")
            return

        self.btnCompute.setEnabled(False)
        self.iface.messageBar().pushInfo(
            "Meridian",
            f"Computing for {len(feat_list)} features… (see task manager)"
        )

        task = _ComputeTask(
            feat_list=feat_list,
            out_fields=out_fields,
            out_name=out_name,
            out_wkb_type=layer.wkbType(),
            out_crs=layer.crs(),
            fallback_date=fallback_date,
            mode=mode,
            model_names=model_names,
            is_polygon=is_polygon,
            layer_crs_authid=layer.crs().authid(),
            want_decl=want_decl,
            want_gc=want_gc,
            want_gma=want_gma,
            want_components=want_components,
            finished_cb=self._on_layer_compute_finished,
        )
        self._active_task = task
        QgsApplication.taskManager().addTask(task)

    def _on_layer_compute_finished(
        self, out_feats, errors, out_name, out_fields, out_wkb_type, out_crs, success
    ):
        self._active_task = None
        self.btnCompute.setEnabled(True)

        if not success:
            self.iface.messageBar().pushWarning(
                "Meridian", "Computation cancelled."
            )
            return

        out_layer = QgsMemoryProviderUtils.createMemoryLayer(
            out_name, out_fields, out_wkb_type, out_crs
        )
        if not out_layer.isValid():
            self.iface.messageBar().pushCritical(
                "Meridian", "Failed to create output layer."
            )
            return

        out_layer.dataProvider().addFeatures(out_feats)
        out_layer.updateExtents()
        QgsProject.instance().addMapLayer(out_layer)

        msg = f"Added '{out_layer.name()}' with {len(out_feats)} features."
        if errors:
            msg += f" ({errors} skipped due to errors)"
        self.iface.messageBar().pushSuccess("Meridian", msg)

    # ------------------------------------------------------------------
    # Report export
    # ------------------------------------------------------------------

    def _on_save_report(self, fmt: str):
        from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

        if not self._last_result:
            return

        ext = fmt.upper()
        filt = f"{ext} files (*.{fmt})"
        default_name = (
            f"north_corrections"
            f"_{self._last_result['date_str']}"
            f".{fmt}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save {ext} report", default_name, filt
        )
        if not path:
            return

        try:
            _save_report_file(path, fmt, **self._last_result)
            self.iface.messageBar().pushSuccess(
                "Meridian",
                f"Report saved: {path}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Meridian",
                f"Failed to save report:\n{exc}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date_value(value) -> str | None:
        if value is None or value == "":
            return None
        try:
            from qgis.PyQt.QtCore import QDate as _QDate, QDateTime as _QDT
            if isinstance(value, _QDT):
                return value.toString("yyyy-MM-dd") if value.isValid() else None
            if isinstance(value, _QDate):
                return value.toString("yyyy-MM-dd") if value.isValid() else None
        except Exception:
            pass
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        text = str(value).strip()
        if not text or text.lower() in ("null", "none", "nan", ""):
            return None
        _FMTS = [
            "%Y-%m-%d", "%Y/%m/%d",
            "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
            "%m/%d/%Y",
            "%d %b %Y", "%d %B %Y",
            "%b %d, %Y", "%B %d, %Y",
            "%d-%b-%Y", "%d-%B-%Y",
        ]
        for fmt in _FMTS:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        try:
            from dateutil import parser as _dp
            return _dp.parse(text, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            pass
        return None

    def _current_layer(self) -> QgsVectorLayer | None:
        layer_id = self.layerCombo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _selected_models(self) -> list[str]:
        if self.rbModelAuto.isChecked():
            return ["auto"]
        if self.rbModelAll.isChecked():
            return magdec.available_models()
        return [self.modelCombo.currentText()]

    def closeEvent(self, event):
        self._deactivate_click_tool()
        super().closeEvent(event)

    def _deactivate_click_tool(self):
        if self._click_tool is not None:
            canvas = self.iface.mapCanvas()
            canvas.unsetMapTool(self._click_tool)
            if self._prev_tool is not None:
                canvas.setMapTool(self._prev_tool)
                self._prev_tool = None
            self._click_tool = None
        self.btnPickFromMap.setChecked(False)
