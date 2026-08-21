#!/usr/bin/env python3
"""scan8600 GUI - PySide6-Oberfläche für Flachbett- und Durchlicht-Scans."""
import argparse
import datetime
import json
import pathlib
import shutil
import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea,
                               QSlider, QSpinBox, QInputDialog,
                               QVBoxLayout, QWidget)

import autocrop
import scan8600
from frameeditor import FrameEditor

# Config Datei
CONFIG_FILE = pathlib.Path.home() / ".juicescan_config.json"

# Presets
PRESETS = {
    "Photo (Color, 300dpi)": {
        "mode": "flatbed",
        "dpi": "300",
        "color": "Color",
        "format": "jpeg",
        "autocrop": True,
        "split": True,
    },
    "Document (Grayscale, 300dpi)": {
        "mode": "flatbed",
        "dpi": "300",
        "color": "Grayscale",
        "format": "png",
        "autocrop": True,
        "split": True,
    },
    "Film Color (2400dpi, Descratch)": {
        "mode": "film",
        "dpi": "2400",
        "color": "Color",
        "format": "tiff",
        "descratch": True,
        "negative": True,
    },
    "Film B/W (2400dpi, Grayscale)": {
        "mode": "film",
        "dpi": "2400",
        "color": "Grayscale",
        "format": "tiff",
        "negative": True,
    },
}

RESOLUTIONS = {"flatbed": [300, 600, 1200],
               "film": [300, 600, 1200, 2400, 4800]}
DEFAULT_RES = {"flatbed": "300", "film": "2400"}


PREVIEW_DPI = 300


def open_scan(path):
    """Bild in seiner natürlichen Kanalzahl öffnen.

    Ein Graustufen-Scan hat einen Kanal. Ihn auf RGB aufzublasen
    verdreifacht Datei und Arbeitsspeicher, ohne ein Bit Information
    hinzuzufügen - bei 4800 dpi ist eine Seite schon über ein Gigabyte.
    """
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = scan8600.MAX_PIXELS
    img = Image.open(path)
    return img.convert("L" if img.mode in ("L", "1") else "RGB")


def app_icon_path():
    """Symbol der App. Im gebauten Paket liegt es neben den Ressourcen,
    im Repo unter assets/."""
    base = getattr(sys, "_MEIPASS", None)
    candidates = []
    if base:
        candidates.append(pathlib.Path(base) / "assets" / "juicescan-mark-512.png")
    here = pathlib.Path(__file__).resolve().parent
    candidates += [here / "assets" / "juicescan-mark-512.png",
                   here / "assets" / "JuiceScan.icns"]
    for c in candidates:
        if c.exists():
            return c
    return None

# Optionsliste je Gerät, prozessweit gecacht: jedes scanimage -A öffnet
# das Gerät und bewegt den Schlitten, das soll genau einmal passieren.
DEVICE_OPTS_CACHE = {}

# Grenzen des Durchlichtfensters in mm (aus scanimage -A des 8600F).
FILM_MAX_X, FILM_MAX_Y = 70.0, 230.0


class ScanWorker(QThread):
    done = Signal(list)
    failed = Signal(str)
    # Prozent, Sekunden seit Start des Passes.
    progress = Signal(float, float)

    def __init__(self, args):
        super().__init__()
        self.args = args

    def run(self):
        try:
            paths = scan8600.run_scan(self.args, on_progress=self._progress)
            self.done.emit([str(p) for p in paths])
        except scan8600.ScanError as e:
            self.failed.emit(str(e))
        except Exception as e:  # Treiber-/IO-Fehler sichtbar machen
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _progress(self, percent, elapsed):
        # Läuft im Reader-Thread von scan_run, nicht im QThread selbst.
        # Signal ist der einzige zulässige Weg zur Oberfläche.
        self.progress.emit(percent, elapsed)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JuiceScan by kupermann.com")
        self.worker = None
        self.crop_worker = None
        self._device_opts = {}
        self._scan_had_data = False
        self._warmup_seconds = 0
        self._warmup_timer = QTimer(self)
        self._warmup_timer.timeout.connect(self._tick_warmup)
        root = QHBoxLayout(self)

        # Linke Spalte: Einstellungen in ScrollArea
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        
        # Enable scrolling for left panel
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setMinimumWidth(280)
        root.addWidget(left_scroll, 0)
        
        # ===== DEVICE SELECTION =====
        device_box = QGroupBox("Scanner Device")
        device_layout = QVBoxLayout(device_box)
        
        # Device selection combo box
        self.cb_device = QComboBox()
        self.btn_refresh_devices = QPushButton("Refresh")
        self.btn_refresh_devices.clicked.connect(self.refresh_devices)
        
        device_top_layout = QHBoxLayout()
        device_top_layout.addWidget(self.cb_device, 1)
        device_top_layout.addWidget(self.btn_refresh_devices)
        device_layout.addLayout(device_top_layout)
        
        # Device info label
        self.lbl_device_info = QLabel("No scanner detected")
        self.lbl_device_info.setWordWrap(True)
        device_layout.addWidget(self.lbl_device_info)
        
        left.addWidget(device_box)
        
        # ===== PRESETS =====
        presets_box = QGroupBox("Presets")
        presets_layout = QHBoxLayout(presets_box)
        self.cb_presets = QComboBox()
        self.cb_presets.addItems(["Custom"] + list(PRESETS.keys()))
        self.btn_save_preset = QPushButton("Save")
        self.btn_delete_preset = QPushButton("Delete")
        self.cb_presets.currentTextChanged.connect(self.apply_preset)
        self.btn_save_preset.clicked.connect(self.save_current_as_preset)
        self.btn_delete_preset.clicked.connect(self.delete_preset)
        presets_layout.addWidget(self.cb_presets)
        presets_layout.addWidget(self.btn_save_preset)
        presets_layout.addWidget(self.btn_delete_preset)
        left.addWidget(presets_box)
        
        mode_box = QGroupBox("Mode")
        mb = QHBoxLayout(mode_box)
        self.rb_flatbed = QRadioButton("Flatbed")
        self.rb_film = QRadioButton("Transparency (film/slides)")
        self.rb_flatbed.setChecked(True)
        mb.addWidget(self.rb_flatbed)
        mb.addWidget(self.rb_film)
        left.addWidget(mode_box)

        form_box = QGroupBox("Settings")
        form = QFormLayout(form_box)
        self.cb_dpi = QComboBox()
        self.cb_color = QComboBox()
        self.cb_color.addItems(["Color", "Grayscale"])
        self.cb_format = QComboBox()
        self.cb_format.addItems(["tiff", "png", "jpeg"])
        form.addRow("Resolution (dpi)", self.cb_dpi)
        form.addRow("Color", self.cb_color)
        form.addRow("Format", self.cb_format)
        left.addWidget(form_box)

        opt_box = QGroupBox("Processing")
        ob = QVBoxLayout(opt_box)
        self.ck_descratch = QCheckBox("Remove scratches (infrared)")
        self.ck_negative = QCheckBox("Invert negative")
        self.ck_autocrop = QCheckBox("Detect size automatically")
        self.ck_split = QCheckBox("Save photos separately")
        self.ck_depth16 = QCheckBox("16-bit archival TIFF (no post-processing)")
        ob.addWidget(self.ck_negative)
        ob.addWidget(self.ck_descratch)
        ob.addWidget(self.ck_autocrop)
        ob.addWidget(self.ck_split)
        ob.addWidget(self.ck_depth16)
        fr = QHBoxLayout()
        fr.addWidget(QLabel("Frames in holder (0 = automatic)"))
        self.sp_frames = QSpinBox()
        self.sp_frames.setRange(0, 12)
        fr.addWidget(self.sp_frames)
        ob.addLayout(fr)
        left.addWidget(opt_box)
        
        # ===== SCAN AREA (Flatbed only) =====
        self.area_box = QGroupBox("Scan Area (Flatbed)")
        self.area_box.setVisible(False)
        area_form = QFormLayout(self.area_box)
        
        self.ck_custom_area = QCheckBox("Custom scan area")
        self.ck_custom_area.stateChanged.connect(self.toggle_custom_area)
        area_form.addRow(self.ck_custom_area)
        
        self.sp_area_left = QDoubleSpinBox()
        self.sp_area_left.setRange(0, 216)
        self.sp_area_left.setSuffix(" mm")
        self.sp_area_left.setDecimals(1)
        self.sp_area_top = QDoubleSpinBox()
        self.sp_area_top.setRange(0, 297)
        self.sp_area_top.setSuffix(" mm")
        self.sp_area_top.setDecimals(1)
        self.sp_area_width = QDoubleSpinBox()
        self.sp_area_width.setRange(1, 216)
        self.sp_area_width.setSuffix(" mm")
        self.sp_area_width.setDecimals(1)
        self.sp_area_height = QDoubleSpinBox()
        self.sp_area_height.setRange(1, 297)
        self.sp_area_height.setSuffix(" mm")
        self.sp_area_height.setDecimals(1)
        
        area_form.addRow("Left:", self.sp_area_left)
        area_form.addRow("Top:", self.sp_area_top)
        area_form.addRow("Width:", self.sp_area_width)
        area_form.addRow("Height:", self.sp_area_height)
        left.addWidget(self.area_box)

        out_box = QGroupBox("Destination")
        of = QHBoxLayout(out_box)
        self.ed_dir = QLineEdit(str(pathlib.Path.home() / "Pictures"))
        btn_dir = QPushButton("…")
        btn_dir.clicked.connect(self.pick_dir)
        of.addWidget(self.ed_dir)
        of.addWidget(btn_dir)
        left.addWidget(out_box)

        # ===== ADVANCED OPTIONS =====
        adv_box = QGroupBox("Advanced Options")
        adv_layout = QVBoxLayout(adv_box)
        
        # Brightness
        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("Brightness:"))
        self.slider_brightness = QSlider(Qt.Horizontal)
        self.slider_brightness.setRange(-1000, 1000)
        self.slider_brightness.setValue(0)
        self.lbl_brightness = QLabel("0")
        self.lbl_brightness.setMinimumWidth(40)
        brightness_layout.addWidget(self.slider_brightness)
        brightness_layout.addWidget(self.lbl_brightness)
        self.slider_brightness.valueChanged.connect(
            lambda v: self.lbl_brightness.setText(str(v))
        )
        adv_layout.addLayout(brightness_layout)
        
        # Contrast
        contrast_layout = QHBoxLayout()
        contrast_layout.addWidget(QLabel("Contrast:"))
        self.slider_contrast = QSlider(Qt.Horizontal)
        self.slider_contrast.setRange(-1000, 1000)
        self.slider_contrast.setValue(0)
        self.lbl_contrast = QLabel("0")
        self.lbl_contrast.setMinimumWidth(40)
        contrast_layout.addWidget(self.slider_contrast)
        contrast_layout.addWidget(self.lbl_contrast)
        self.slider_contrast.valueChanged.connect(
            lambda v: self.lbl_contrast.setText(str(v))
        )
        adv_layout.addLayout(contrast_layout)
        
        # Sharpness
        sharpness_layout = QHBoxLayout()
        sharpness_layout.addWidget(QLabel("Sharpness:"))
        self.slider_sharpness = QSlider(Qt.Horizontal)
        self.slider_sharpness.setRange(0, 100)
        self.slider_sharpness.setValue(0)
        self.lbl_sharpness = QLabel("0")
        self.lbl_sharpness.setMinimumWidth(40)
        sharpness_layout.addWidget(self.slider_sharpness)
        sharpness_layout.addWidget(self.lbl_sharpness)
        self.slider_sharpness.valueChanged.connect(
            lambda v: self.lbl_sharpness.setText(str(v))
        )
        adv_layout.addLayout(sharpness_layout)
        
        # Denoise
        denoise_layout = QHBoxLayout()
        denoise_layout.addWidget(QLabel("Denoise:"))
        self.slider_denoise = QSlider(Qt.Horizontal)
        self.slider_denoise.setRange(0, 100)
        self.slider_denoise.setValue(0)
        self.lbl_denoise = QLabel("0")
        self.lbl_denoise.setMinimumWidth(40)
        denoise_layout.addWidget(self.slider_denoise)
        denoise_layout.addWidget(self.lbl_denoise)
        self.slider_denoise.valueChanged.connect(
            lambda v: self.lbl_denoise.setText(str(v))
        )
        adv_layout.addLayout(denoise_layout)
        
        left.addWidget(adv_box)
        
        # ===== CALIBRATION CACHE =====
        cache_box = QGroupBox("Calibration")
        cache_layout = QHBoxLayout(cache_box)
        self.btn_clear_cache = QPushButton("Clear Cache")
        self.btn_clear_cache.clicked.connect(self.clear_calibration_cache)
        cache_layout.addWidget(self.btn_clear_cache)
        left.addWidget(cache_box)
        
        # ===== BATCH SCAN =====
        batch_box = QGroupBox("Batch Scan")
        batch_layout = QHBoxLayout(batch_box)
        self.ck_batch_mode = QCheckBox("Enable")
        self.ck_batch_mode.stateChanged.connect(self.toggle_batch_mode)
        batch_layout.addWidget(self.ck_batch_mode)
        batch_layout.addWidget(QLabel("Scans:"))
        self.sp_batch_count = QSpinBox()
        self.sp_batch_count.setRange(1, 10)
        self.sp_batch_count.setValue(1)
        batch_layout.addWidget(self.sp_batch_count)
        left.addWidget(batch_box)
        
        # Frueher stand hier eine Option "Lamp Warm-up". Sie hat vor dem
        # Oeffnen des Geraets geschlafen - da war die Lampe noch gar
        # nicht bestromt, geheizt hat sie also nichts, und die
        # Oberflaeche stand bis zu 60 s. Den Warmlauf macht der Treiber
        # selbst bei jedem sane_start, sichtbar in der Statuszeile.

        # ===== HDR SCANNING =====
        hdr_box = QGroupBox("HDR (Multi-Exposure)")
        hdr_layout = QVBoxLayout(hdr_box)
        self.ck_hdr_mode = QCheckBox("Enable HDR (2 exposures)")
        self.ck_hdr_mode.stateChanged.connect(self.toggle_hdr_mode)
        hdr_layout.addWidget(self.ck_hdr_mode)
        
        # Exposure compensation for the second exposure
        hdr_comp_layout = QHBoxLayout()
        hdr_comp_layout.addWidget(QLabel("2nd Exposure Comp.:"))
        self.slider_hdr_comp = QSlider(Qt.Horizontal)
        self.slider_hdr_comp.setRange(-100, 100)
        self.slider_hdr_comp.setValue(50)
        self.lbl_hdr_comp = QLabel("+1.5 EV")
        self.lbl_hdr_comp.setMinimumWidth(60)
        hdr_comp_layout.addWidget(self.slider_hdr_comp)
        hdr_comp_layout.addWidget(self.lbl_hdr_comp)
        hdr_layout.addLayout(hdr_comp_layout)
        
        # Connect slider to label
        self.slider_hdr_comp.valueChanged.connect(self.update_hdr_comp_label)
        left.addWidget(hdr_box)

        self.btn_scan = QPushButton("Scan")
        self.btn_scan.setObjectName("scanButton")
        self.btn_scan.setMinimumHeight(44)
        self.btn_scan.clicked.connect(self.start_scan)
        left.addWidget(self.btn_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        left.addWidget(self.progress)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        
        # ===== OUTPUT OPTIONS =====
        # Dateinamen-Vorlage
        filename_box = QGroupBox("Output Filename")
        filename_layout = QFormLayout(filename_box)
        self.ed_filename_pattern = QLineEdit("scan_{datetime}")
        filename_layout.addRow("Pattern:", self.ed_filename_pattern)
        self.lbl_pattern_help = QLabel(
            "Variables: {datetime}, {frame}, {mode}, {dpi}, {color}"
        )
        self.lbl_pattern_help.setWordWrap(True)
        filename_layout.addRow(self.lbl_pattern_help)
        self.lbl_filename_preview = QLabel("Preview: scan_20260817_143000.tiff")
        filename_layout.addRow(self.lbl_filename_preview)
        self.ed_filename_pattern.textChanged.connect(self.update_filename_preview)
        left.addWidget(filename_box)
        
        # Rotation & Mirror
        transform_box = QGroupBox("Transform")
        transform_layout = QHBoxLayout(transform_box)
        transform_layout.addWidget(QLabel("Rotation:"))
        self.cb_rotation = QComboBox()
        self.cb_rotation.addItems(["0°", "90°", "180°", "270°"])
        transform_layout.addWidget(self.cb_rotation)
        left.addWidget(transform_box)
        
        mirror_box = QGroupBox("Mirror")
        mirror_layout = QHBoxLayout(mirror_box)
        self.ck_mirror_horizontal = QCheckBox("Horizontal")
        self.ck_mirror_vertical = QCheckBox("Vertical")
        mirror_layout.addWidget(self.ck_mirror_horizontal)
        mirror_layout.addWidget(self.ck_mirror_vertical)
        left.addWidget(mirror_box)
        
        left.addStretch()

        # Rechte Spalte: Vorschau
        right = QVBoxLayout()
        self.preview = FrameEditor()
        self.preview.setMinimumSize(420, 520)
        right.addWidget(self.preview, 1)
        self.editor_hint = QLabel(
            "Draw frames with the mouse, drag to move, "
            "Backspace deletes the selected frame.")
        self.editor_hint.setWordWrap(True)
        self.editor_hint.hide()
        right.addWidget(self.editor_hint)
        self.btn_save = QPushButton("Save crops")
        self.btn_save.clicked.connect(self.save_frames)
        self.btn_save.setEnabled(False)
        right.addWidget(self.btn_save)
        root.addLayout(right, 1)
        self._raw_path = None

        self.rb_flatbed.toggled.connect(self.sync_mode)
        self.ck_autocrop.toggled.connect(self.sync_split)
        self.ck_depth16.toggled.connect(self.sync_depth16)
        for w in (self.ck_descratch, self.ck_negative, self.ck_autocrop):
            w.toggled.connect(self.sync_depth16)
        
        # Geräte laden
        self.refresh_devices()
        
        # Einstellungen laden und Preset anwenden
        self.load_settings()
        # sync_mode muss nach load_settings aufgerufen werden, da DPI-Optionen vom Modus abhängen
        self.sync_mode()
        # Preset anwenden (kann Modus ändern, also nach sync_mode)
        self.apply_preset(self.cb_presets.currentText())

    # --- UI-Logik ---------------------------------------------------------
    def mode(self):
        return "flatbed" if self.rb_flatbed.isChecked() else "film"

    def sync_mode(self):
        m = self.mode()
        self.cb_dpi.clear()
        self.cb_dpi.addItems([str(r) for r in RESOLUTIONS[m]])
        self.cb_dpi.setCurrentText(DEFAULT_RES[m])
        self.ck_descratch.setEnabled(m == "film")
        self.ck_negative.setEnabled(m == "film")
        self.sp_frames.setEnabled(m == "film")
        self.area_box.setVisible(m == "flatbed")
        if m != "film":
            self.ck_negative.setChecked(False)
            self.sp_frames.setValue(0)
        if m != "film":
            self.ck_descratch.setChecked(False)
        self.sync_split()
    
    def refresh_devices(self):
        """Aktualisiert die Liste der verfügbaren Scanner."""
        # USB-Adressen wandern. Beide Optionscaches verwerfen, sonst
        # validiert der naechste Scan gegen ein Geraet von vorhin.
        DEVICE_OPTS_CACHE.clear()
        scan8600.clear_options_cache()
        try:
            from discovery import list_scanners
            devices = list_scanners()
            
            self.cb_device.clear()
            if not devices:
                self.cb_device.addItem("No scanners found")
                self.lbl_device_info.setText("No SANE scanners detected. "
                                          "Please install SANE drivers and connect a scanner.")
                return
            
            for device in devices:
                status = f" ({device.support_status})" if device.support_status != "untested" else ""
                self.cb_device.addItem(f"{device.name}{status}", userData=device.device_file)
            
            # Setze erstes Gerät als Standard
            if devices:
                self.cb_device.setCurrentIndex(0)
                self._update_device_info(devices[0])
            self._sync_advanced_to_device()

        except Exception as e:
            self.cb_device.addItem("Error loading scanners")
            self.lbl_device_info.setText(f"Error: {e}")
    
    # --- Regler aus den echten Geräteoptionen ---------------------------
    #
    # Vorher hingen hier feste Bereiche (-1000..1000) und ein Sharpness-
    # Regler, den der genesys-Treiber gar nicht kennt. scanimage bricht bei
    # einer unbekannten Option ab, nachdem es das Gerät schon geöffnet
    # hat: der Schlitten fährt an, bleibt stehen, kein Bild. Deshalb wird
    # die Oberfläche jetzt aus der Optionsliste des Geräts gebaut - so,
    # wie es das GIMP-Plugin seit jeher tut.

    ADVANCED_SLIDERS = (
        ("--brightness", "slider_brightness", "lbl_brightness"),
        ("--contrast", "slider_contrast", "lbl_contrast"),
        ("--sharpness", "slider_sharpness", "lbl_sharpness"),
    )

    def _current_device(self):
        if self.cb_device.count() > 0 and self.cb_device.currentIndex() >= 0:
            return self.cb_device.currentData()
        return None

    def _device_option_index(self, device_file):
        """{Optionsname: Option} für ein Gerät, gecacht."""
        if device_file in DEVICE_OPTS_CACHE:
            return DEVICE_OPTS_CACHE[device_file]
        import os
        if os.environ.get("JUICESCAN_NO_PROBE"):
            # Tests sollen das Gerät nicht anfassen.
            return {}
        index = {}
        try:
            import scanoptions
            from discovery import ScannerDiscovery
            disc = ScannerDiscovery(str(scan8600.SCANIMAGE))
            info = disc.get_device_info(device_file) or {}
            index = {o.name: o for o in scanoptions.parse(info.get("raw", ""))}
        except Exception as e:
            print(f"Error reading device options: {e}")
        DEVICE_OPTS_CACHE[device_file] = index
        return index

    def _sync_advanced_to_device(self):
        """Bereiche der Enhancement-Regler aus dem Gerät übernehmen und
        nicht vorhandene Optionen abschalten."""
        device_file = self._current_device()
        if not device_file:
            return
        index = self._device_option_index(device_file)
        if not index:
            # Ohne verwertbare Liste nichts anfassen, sonst sperren wir
            # Regler auf Verdacht.
            return
        self._device_opts = index
        for flag, slider_name, label_name in self.ADVANCED_SLIDERS:
            slider = getattr(self, slider_name)
            label = getattr(self, label_name)
            opt = index.get(flag)
            name = flag.lstrip("-")
            if opt is None or opt.kind != "range" or opt.hi <= opt.lo:
                slider.blockSignals(True)
                slider.setValue(0)
                slider.blockSignals(False)
                slider.setEnabled(False)
                slider.setToolTip(
                    f"This scanner has no '{name}' option, so it is disabled.")
                label.setText("n/a")
                continue
            lo, hi = int(opt.lo), int(opt.hi)
            slider.setEnabled(True)
            slider.setToolTip(f"{name}: {lo}..{hi} (from the driver)")
            value = min(max(slider.value(), lo), hi)
            slider.setRange(lo, hi)
            slider.setValue(value)
            label.setText(str(slider.value()))

    def _update_device_info(self, device):
        """Aktualisiert die Geräteinformationen."""
        info_parts = [
            f"Backend: {device.backend}",
            f"Type: {device.type}",
            f"Status: {device.support_status}",
        ]
        self.lbl_device_info.setText(" | ".join(info_parts))
    
    def toggle_custom_area(self, state):
        """Zeigt/versteckt die manuellen Bereichs-Einstellungen."""
        for widget in [self.sp_area_left, self.sp_area_top, 
                      self.sp_area_width, self.sp_area_height]:
            widget.setEnabled(state == Qt.Checked)
    
    def toggle_batch_mode(self, state):
        """Aktiviert/Deaktiviert den Batch-Modus."""
        self.sp_batch_count.setEnabled(state == Qt.Checked)
    
    def toggle_hdr_mode(self, state):
        """Aktiviert/Deaktiviert den HDR-Modus."""
        self.slider_hdr_comp.setEnabled(state == Qt.Checked)
        self.lbl_hdr_comp.setEnabled(state == Qt.Checked)
    
    def update_hdr_comp_label(self, value):
        """Aktualisiert das EV-Label basierend auf dem Slider-Wert."""
        # Map slider value (-100 to 100) to EV (-3 to +3)
        ev = value / 100 * 3
        self.lbl_hdr_comp.setText(f"{ev:+.1f} EV")

    def sync_depth16(self):
        # 16 Bit kann nun mit Nachbearbeitung kombiniert werden,
        # aber nur für TIFF-Format (JPEG/PNG unterstützen kein 16-Bit)
        if self.ck_depth16.isChecked():
            # Erzwinge TIFF-Format
            self.cb_format.setCurrentText("tiff")
            self.cb_format.setEnabled(False)
        else:
            self.cb_format.setEnabled(True)
        
        # Aktualisiere die Verfügbarkeit der Verarbeitungsoptionen
        m = self.mode()
        self.ck_descratch.setEnabled(m == "film")
        self.ck_negative.setEnabled(m == "film")
        self.ck_autocrop.setEnabled(True)
        self.sync_split()

    def sync_split(self):
        self.ck_split.setEnabled(self.ck_autocrop.isChecked())
        if not self.ck_autocrop.isChecked():
            self.ck_split.setChecked(False)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Destination folder", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def build_args(self):
        fmt = self.cb_format.currentText()
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
        
        # Benutzerdefiniertes Dateinamen-Muster
        pattern = self.ed_filename_pattern.text()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = pattern.format(
            datetime=stamp,
            frame=1,
            mode=self.mode(),
            dpi=self.cb_dpi.currentText(),
            color=self.cb_color.currentText().lower()
        )
        out = pathlib.Path(self.ed_dir.text()) / f"{filename}.{ext}"
        
        # SANE-Optionen sammeln
        sane_opts = []
        if self.slider_brightness.value() != 0:
            sane_opts.append(f"brightness={self.slider_brightness.value()}")
        if self.slider_contrast.value() != 0:
            sane_opts.append(f"contrast={self.slider_contrast.value()}")
        if self.slider_sharpness.value() != 0:
            sane_opts.append(f"sharpness={self.slider_sharpness.value()}")
        
        # Custom Scan Area (nur für Flachbett)
        if self.ck_custom_area.isChecked() and self.mode() == "flatbed":
            sane_opts.extend([
                f"l={self.sp_area_left.value():.1f}",
                f"t={self.sp_area_top.value():.1f}",
                f"x={self.sp_area_width.value():.1f}",
                f"y={self.sp_area_height.value():.1f}",
            ])
        
        # Geräteauswahl
        device = None
        if self.cb_device.count() > 0 and self.cb_device.currentIndex() >= 0:
            device = self.cb_device.currentData()
        
        return argparse.Namespace(
            mode=self.mode(),
            dpi=int(self.cb_dpi.currentText()),
            format=fmt,
            output=str(out),
            gray=self.cb_color.currentText() == "Grayscale",
            descratch=self.ck_descratch.isChecked(),
            negative=self.ck_negative.isChecked(),
            autocrop=self.ck_autocrop.isChecked(),
            split=self.ck_split.isChecked(),
            depth16=self.ck_depth16.isChecked(),
            frames=self.sp_frames.value(),
            sane_opt=sane_opts,
            denoise=self.slider_denoise.value(),
            device=device,
        )
    
    # --- PERSISTENCE ------------------------------------------------------------
    def load_settings(self):
        """Lädt Einstellungen aus der Config-Datei."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    settings = json.load(f)
                
                # Geräteauswahl (wird nach dem Laden der Geräte angewendet)
                selected_device = settings.get("device")
                
                # Grundeinstellungen
                if "mode" in settings:
                    if settings["mode"] == "film":
                        self.rb_film.setChecked(True)
                    else:
                        self.rb_flatbed.setChecked(True)
                
                if "color" in settings:
                    self.cb_color.setCurrentText(settings["color"])
                if "format" in settings:
                    self.cb_format.setCurrentText(settings["format"])
                if "output_dir" in settings:
                    self.ed_dir.setText(settings["output_dir"])
                if "filename_pattern" in settings:
                    self.ed_filename_pattern.setText(settings["filename_pattern"])
                
                # Verarbeitungsoptionen
                if "descratch" in settings:
                    self.ck_descratch.setChecked(settings["descratch"])
                if "negative" in settings:
                    self.ck_negative.setChecked(settings["negative"])
                if "autocrop" in settings:
                    self.ck_autocrop.setChecked(settings["autocrop"])
                if "split" in settings:
                    self.ck_split.setChecked(settings["split"])
                if "depth16" in settings:
                    self.ck_depth16.setChecked(settings["depth16"])
                if "frames" in settings:
                    self.sp_frames.setValue(settings["frames"])
                
                # SANE-Optionen
                if "brightness" in settings:
                    self.slider_brightness.setValue(settings["brightness"])
                if "contrast" in settings:
                    self.slider_contrast.setValue(settings["contrast"])
                if "sharpness" in settings:
                    self.slider_sharpness.setValue(settings["sharpness"])
                if "denoise" in settings:
                    self.slider_denoise.setValue(settings["denoise"])
                
                # Transform
                if "rotation" in settings:
                    self.cb_rotation.setCurrentIndex(settings["rotation"])
                if "mirror_horizontal" in settings:
                    self.ck_mirror_horizontal.setChecked(settings["mirror_horizontal"])
                if "mirror_vertical" in settings:
                    self.ck_mirror_vertical.setChecked(settings["mirror_vertical"])
                
                # Batch Scan
                if "batch_mode" in settings:
                    self.ck_batch_mode.setChecked(settings["batch_mode"])
                if "batch_count" in settings:
                    self.sp_batch_count.setValue(settings["batch_count"])
                
                # Lamp Warm-up
                
                # HDR
                if "hdr_mode" in settings:
                    self.ck_hdr_mode.setChecked(settings["hdr_mode"])
                if "hdr_comp" in settings:
                    self.slider_hdr_comp.setValue(settings["hdr_comp"])
                
                # Scan Area
                if "custom_area" in settings:
                    self.ck_custom_area.setChecked(settings["custom_area"])
                if "area_left" in settings:
                    self.sp_area_left.setValue(settings["area_left"])
                if "area_top" in settings:
                    self.sp_area_top.setValue(settings["area_top"])
                if "area_width" in settings:
                    self.sp_area_width.setValue(settings["area_width"])
                if "area_height" in settings:
                    self.sp_area_height.setValue(settings["area_height"])
                
                # Preset
                if "preset" in settings:
                    preset_name = settings["preset"]
                    if preset_name in PRESETS or preset_name == "Custom":
                        self.cb_presets.setCurrentText(preset_name)
                
            except Exception as e:
                print(f"Error loading settings: {e}")
    
    def showEvent(self, event):
        """Wird aufgerufen, wenn das Fenster angezeigt wird."""
        # Geräteauswahl nach dem Laden aller Einstellungen setzen
        if hasattr(self, '_pending_device') and self._pending_device:
            self._select_device(self._pending_device)
            del self._pending_device
        super().showEvent(event)
    
    def _select_device(self, device_file):
        """Wählt ein Gerät aus der Dropdown-Liste aus."""
        if not device_file:
            return
        for i in range(self.cb_device.count()):
            if self.cb_device.itemData(i) == device_file:
                self.cb_device.setCurrentIndex(i)
                # Update device info
                from discovery import list_scanners
                devices = list_scanners()
                for dev in devices:
                    if dev.device_file == device_file:
                        self._update_device_info(dev)
                        break
                self._sync_advanced_to_device()
                return
    
    def save_settings(self):
        """Speichert Einstellungen in die Config-Datei."""
        # Geräteauswahl speichern
        device = None
        if self.cb_device.count() > 0 and self.cb_device.currentIndex() >= 0:
            device = self.cb_device.currentData()
        
        settings = {
            "mode": self.mode(),
            "color": self.cb_color.currentText(),
            "dpi": self.cb_dpi.currentText(),
            "format": self.cb_format.currentText(),
            "output_dir": self.ed_dir.text(),
            "filename_pattern": self.ed_filename_pattern.text(),
            "descratch": self.ck_descratch.isChecked(),
            "device": device,
            "negative": self.ck_negative.isChecked(),
            "autocrop": self.ck_autocrop.isChecked(),
            "split": self.ck_split.isChecked(),
            "depth16": self.ck_depth16.isChecked(),
            "frames": self.sp_frames.value(),
            "brightness": self.slider_brightness.value(),
            "contrast": self.slider_contrast.value(),
            "sharpness": self.slider_sharpness.value(),
            "denoise": self.slider_denoise.value(),
            "rotation": self.cb_rotation.currentIndex(),
            "mirror_horizontal": self.ck_mirror_horizontal.isChecked(),
            "mirror_vertical": self.ck_mirror_vertical.isChecked(),
            "batch_mode": self.ck_batch_mode.isChecked(),
            "batch_count": self.sp_batch_count.value(),
            "hdr_mode": self.ck_hdr_mode.isChecked(),
            "hdr_comp": self.slider_hdr_comp.value(),
            "custom_area": self.ck_custom_area.isChecked(),
            "area_left": self.sp_area_left.value(),
            "area_top": self.sp_area_top.value(),
            "area_width": self.sp_area_width.value(),
            "area_height": self.sp_area_height.value(),
            "preset": self.cb_presets.currentText(),
        }
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def closeEvent(self, event):
        """Speichert Einstellungen beim Schließen."""
        self.save_settings()
        super().closeEvent(event)
    
    # --- PRESETS ----------------------------------------------------------------
    def apply_preset(self, preset_name):
        """Wendet ein Preset an."""
        if preset_name == "Custom" or preset_name not in PRESETS:
            return
        
        preset = PRESETS[preset_name]
        
        # Modus zuerst setzen (könnte sync_mode auslösen)
        if "mode" in preset:
            if preset["mode"] == "film":
                self.rb_film.setChecked(True)
            else:
                self.rb_flatbed.setChecked(True)
        
        # Anderes
        if "color" in preset:
            self.cb_color.setCurrentText(preset["color"])
        if "dpi" in preset:
            # Warten bis sync_mode die DPI-Optionen gesetzt hat
            QApplication.processEvents()
            self.cb_dpi.setCurrentText(str(preset["dpi"]))
        if "format" in preset:
            self.cb_format.setCurrentText(preset["format"])
        if "descratch" in preset:
            self.ck_descratch.setChecked(preset["descratch"])
        if "negative" in preset:
            self.ck_negative.setChecked(preset["negative"])
        if "autocrop" in preset:
            self.ck_autocrop.setChecked(preset["autocrop"])
        if "split" in preset:
            self.ck_split.setChecked(preset["split"])
        if "depth16" in preset:
            self.ck_depth16.setChecked(preset["depth16"])
    
    def save_current_as_preset(self):
        """Speichert aktuelle Einstellungen als neues Preset."""
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name and name.strip():
            PRESETS[name] = self._get_current_settings()
            self.cb_presets.addItem(name)
            self.cb_presets.setCurrentText(name)
            self.save_settings()
    
    def delete_preset(self):
        """Löscht ein Preset."""
        name = self.cb_presets.currentText()
        if name != "Custom" and name in PRESETS:
            if QMessageBox.question(self, "Delete Preset", 
                                  f"Delete preset '{name}'?", 
                                  QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                del PRESETS[name]
                self.cb_presets.removeItem(self.cb_presets.currentIndex())
    
    def _get_current_settings(self):
        """Gibt die aktuellen Einstellungen als Dictionary zurück."""
        return {
            "mode": self.mode(),
            "dpi": self.cb_dpi.currentText(),
            "color": self.cb_color.currentText(),
            "format": self.cb_format.currentText(),
            "descratch": self.ck_descratch.isChecked(),
            "negative": self.ck_negative.isChecked(),
            "autocrop": self.ck_autocrop.isChecked(),
            "split": self.ck_split.isChecked(),
            "depth16": self.ck_depth16.isChecked(),
        }
    
    # --- CALIBRATION CACHE ------------------------------------------------------
    def _check_needs_calibration(self, args):
        """Prüft, ob für diese Parameter bereits Kalibrierung existiert."""
        cache_dir = pathlib.Path.home() / ".sane" / "genesys"
        if not cache_dir.exists():
            return True
        
        # SANE speichert Kalibrierung als calibration-{source}-{resolution}-{depth}-{mode}.dat
        # oder ähnlich. Wir prüfen einfach, ob die cache_dir Dateien hat.
        calibration_files = list(cache_dir.glob("calibration-*.dat"))
        if not calibration_files:
            return True
        
        # Probiere, die spezifische Kalibrierungsdatei zu finden
        depth = 8 if args.gray else 24
        source = "film" if args.mode == "film" else "flatbed"
        calibration_file = cache_dir / f"calibration-*-{source}-{args.dpi}-{depth}-*.dat"
        specific_files = list(cache_dir.glob(f"calibration-*-{source}-{args.dpi}-{depth}-*.dat"))
        
        return len(specific_files) == 0
    
    def clear_calibration_cache(self):
        """Löscht den SANE-Kalibrierungs-Cache."""
        cache_dir = pathlib.Path.home() / ".sane" / "genesys"
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
                self.status.setText("✓ Calibration cache cleared.")
                QMessageBox.information(self, "Cache Cleared", 
                                       "Scanner calibration cache has been cleared.")
            except Exception as e:
                self.status.setText(f"✗ Error clearing cache: {e}")
                QMessageBox.critical(self, "Error", f"Failed to clear cache: {e}")
        else:
            self.status.setText("No cache found.")
    
    # --- FILENAME PATTERN --------------------------------------------------------
    def update_filename_preview(self):
        """Aktualisiert die Vorschau des Dateinamens."""
        pattern = self.ed_filename_pattern.text()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            preview = pattern.format(
                datetime=stamp,
                frame=1,
                mode=self.mode(),
                dpi=self.cb_dpi.currentText(),
                color=self.cb_color.currentText().lower()
            )
            fmt = self.cb_format.currentText()
            ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
            self.lbl_filename_preview.setText(f"Preview: {preview}.{ext}")
        except Exception as e:
            self.lbl_filename_preview.setText(f"Preview: ERROR ({e})")

    # --- Scan-Ablauf ------------------------------------------------------
    def start_scan(self):
        self.btn_scan.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.progress.setRange(0, 0)
        
        a = self.build_args()
        self._wanted = a
        
        # HDR-Modus?
        if self.ck_hdr_mode.isChecked():
            if self.ck_depth16.isChecked():
                QMessageBox.warning(
                    self, "HDR and 16 bit",
                    "The driver applies brightness only to 8-bit scans, so "
                    "both HDR exposures would come back identical. Turn off "
                    "16 bit or turn off HDR.")
                self.btn_scan.setEnabled(True)
                self.progress.setRange(0, 1)
                return
            self._hdr_index = 0
            self._hdr_total = 2
            self._hdr_results = []
            self._hdr_exposures = self._get_hdr_exposures()
            self._start_next_hdr_scan()
        # Batch-Modus oder Einzel-Scan?
        elif self.ck_batch_mode.isChecked() and self.sp_batch_count.value() > 1:
            self._batch_index = 0
            self._batch_total = self.sp_batch_count.value()
            self._batch_results = []
            self._start_next_batch_scan()
        else:
            # Einzel-Scan
            self._do_single_scan(a)
    
    def _do_single_scan(self, a):
        """Startet einen einzelnen Scan."""
        # Prüfen, ob Kalibrierung benötigt wird
        needs_calibration = self._check_needs_calibration(a)
        if needs_calibration:
            self.status.setText(
                "Calibrating scanner… (first time for this resolution/color mode, "
                "then it is cached)")
        else:
            self.status.setText(
                "Scanning… (using cached calibration for this resolution/color mode)")
        
        if a.mode == "film" and not a.depth16:
            # Zweistufig wie SilverFast: schneller Vorschau-Scan bei
            # 300 dpi, Rahmen setzen, dann scannt nur noch der
            # Rahmenbereich in der gewählten Auflösung.
            import tempfile
            raw = tempfile.NamedTemporaryFile(suffix=".tiff", delete=False)
            a = argparse.Namespace(**vars(a))
            a.autocrop = a.split = a.negative = a.descratch = False
            a.format = "tiff"
            a.dpi = PREVIEW_DPI
            a.output = raw.name
            self._raw_path = raw.name
        else:
            self._raw_path = None
        self.worker = ScanWorker(a)
        self.worker.done.connect(self.scan_done)
        self.worker.failed.connect(self.scan_failed)
        self.worker.progress.connect(self.scan_progress)
        self._scan_had_data = False
        self._warmup_timer.start(1000)
        self._warmup_seconds = 0
        self.worker.start()

    # --- Warmlauf sichtbar machen ---------------------------------------
    #
    # Gemessen: bis zu 20 s vergehen zwischen sane_start und dem ersten
    # Byte. In der Zeit faehrt der Schlitten hin und her, ohne dass ein
    # Bild entsteht - der Treiber scannt dieselbe Zeile, bis sich die
    # Lampenhelligkeit stabilisiert hat. Die Oberflaeche hat dazu bisher
    # "Scanning…" behauptet und einen Spinner ohne Ende gezeigt. Das
    # liest sich als Absturz.

    def _tick_warmup(self):
        if self._scan_had_data or self.worker is None:
            self._warmup_timer.stop()
            return
        self._warmup_seconds += 1
        if self._warmup_seconds < 3:
            return
        self.status.setText(
            f"Preparing the scanner… {self._warmup_seconds} s\n"
            "The driver is warming up the lamp: the carriage moves back "
            "and forth over the same line until the brightness is stable. "
            "No image data yet. Cold lamp takes 15-20 s, a second scan "
            "right after usually takes one.")

    def scan_progress(self, percent, elapsed):
        if not self._scan_had_data:
            self._scan_had_data = True
            self._warmup_timer.stop()
        self.progress.setRange(0, 100)
        self.progress.setValue(int(percent))
        self.status.setText(f"Scanning… {percent:.0f}% ({elapsed:.0f} s)")

    def _get_hdr_exposures(self):
        """Berechnet die Belichtungswerte für die HDR-Scans.

        Der Regelbereich kommt vom Treiber, nicht aus einer Wunschzahl.
        Früher wurde hier fest auf +-300 gerechnet - außerhalb der
        genesys-Spanne von -100..100. scanimage kappt das still, beide
        Belichtungen landen auf demselben Wert und HDR tut gar nichts.
        """
        lo = self.slider_brightness.minimum()
        hi = self.slider_brightness.maximum()
        base = min(max(self.slider_brightness.value(), lo), hi)
        comp_value = self.slider_hdr_comp.value()
        comp_offset = int(comp_value / 100.0 * (hi - lo) / 2.0)
        second = min(max(base + comp_offset, lo), hi)
        if second == base:
            self.status.setText(
                "HDR: both exposures land on the same brightness value "
                f"({base}); the driver range is {lo}..{hi}.")
        return [base, second]
    
    def _start_next_hdr_scan(self):
        """Startet den nächsten Scan im HDR-Modus."""
        self._hdr_index += 1
        hdr_num = self._hdr_index
        hdr_total = self._hdr_total
        
        # Status aktualisieren
        self.status.setText(
            f"HDR scan: {hdr_num}/{hdr_total} - "
            f"Scanning… (using cached calibration)")
        self.progress.setRange(0, hdr_total)
        self.progress.setValue(hdr_num)
        
        # Belichtungswert für diesen Scan
        exposure_brightness = self._hdr_exposures[hdr_num - 1]
        
        # Neue Datei für diesen Scan
        a = self.build_args()
        
        # Belichtung anpassen
        a.sane_opt = [opt for opt in a.sane_opt if not opt.startswith('brightness=')]
        a.sane_opt.append(f"brightness={exposure_brightness}")
        
        # Dateinamen anpassen mit HDR-Index
        import datetime
        fmt = self.cb_format.currentText()
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
        
        pattern = self.ed_filename_pattern.text()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = pattern.format(
            datetime=stamp,
            frame=hdr_num,
            mode=self.mode(),
            dpi=self.cb_dpi.currentText(),
            color=self.cb_color.currentText().lower()
        )
        out = pathlib.Path(self.ed_dir.text()) / f"{filename}.{ext}"
        a.output = str(out)
        
        self._wanted = a
        self._do_single_scan(a)
    
    def _merge_hdr_scans(self):
        """Vereinigt die HDR-Scans zu einem einzigen Bild."""
        import numpy as np
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = scan8600.MAX_PIXELS
        import tempfile
        
        if len(self._hdr_results) < 2:
            self.status.setText("Error: Not enough HDR images to merge")
            del self._hdr_index
            del self._hdr_total
            del self._hdr_results
            del self._hdr_exposures
            self.btn_scan.setEnabled(True)
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            return
        
        # Lade die beiden Bilder
        try:
            arr1 = np.array(open_scan(self._hdr_results[0]))
            arr2 = np.array(open_scan(self._hdr_results[1]))
        except Exception as e:
            self.status.setText(f"Error loading HDR images: {e}")
            del self._hdr_index
            del self._hdr_total
            del self._hdr_results
            del self._hdr_exposures
            self.btn_scan.setEnabled(True)
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            return
        
        # Einfaches Exposure Blending (könnte verbessert werden)
        # Hier verwenden wir eine einfache gewichtete Mittelwertbildung
        # basierend auf der Belichtung
        merged = self._blend_exposures(arr1, arr2)
        
        # Speichern des vereinigten Bildes
        a = self._wanted
        fmt = self.cb_format.currentText()
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
        
        pattern = self.ed_filename_pattern.text()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = pattern.format(
            datetime=stamp,
            frame=1,
            mode=self.mode(),
            dpi=self.cb_dpi.currentText(),
            color=self.cb_color.currentText().lower()
        )
        # Füge HDR-Suffix hinzu
        filename = filename.replace("scan_", "scan_hdr_")
        out = pathlib.Path(self.ed_dir.text()) / f"{filename}.{ext}"
        
        img = Image.fromarray(merged)
        if a.format == "jpeg":
            img.save(str(out), quality=95)
        else:
            img.save(str(out))
        
        # Aufräumen
        del self._hdr_index
        del self._hdr_total
        del self._hdr_results
        del self._hdr_exposures
        
        # Status aktualisieren und Ergebnis anzeigen
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_scan.setEnabled(True)
        self.status.setText(f"HDR scan complete: {out}")
        self.editor_hint.hide()
        self.preview.set_image(QPixmap(str(out)))
        
        # Temporary files löschen
        for p in self._hdr_results:
            try:
                pathlib.Path(p).unlink()
            except:
                pass
    
    def _blend_exposures(self, arr1, arr2):
        """Vereinigt zwei Belichtungen mit einfachem Blending."""
        import numpy as np

        # Konvertiere zu Float für die Berechnungen
        arr1_f = arr1.astype(np.float32) / 255.0
        arr2_f = arr2.astype(np.float32) / 255.0
        
        # Einfache gewichtete Mittelwertbildung
        # Bewahrt Details aus beiden Belichtungen
        # Hier verwenden wir 50/50 für Einfachheit
        # (könnte durch intelligentes Blending basierend auf Luminanz verbessert werden)
        merged = (arr1_f + arr2_f) / 2.0
        
        # Tonwertanpassung um Kontrast zu erhalten
        merged = np.clip(merged, 0, 1)
        
        # Konvertiere zurück zu uint8
        return (merged * 255).astype(np.uint8)
    
    def _start_next_batch_scan(self):
        """Startet den nächsten Scan im Batch-Modus."""
        self._batch_index += 1
        batch_num = self._batch_index
        batch_total = self._batch_total
        
        # Status aktualisieren
        self.status.setText(
            f"Batch scan: {batch_num}/{batch_total} - "
            f"Scanning… (using cached calibration)")
        self.progress.setRange(0, batch_total)
        self.progress.setValue(batch_num)
        
        # Neue Datei für diesen Scan
        a = self.build_args()
        # Dateinamen anpassen mit Batch-Nummer
        import datetime
        fmt = self.cb_format.currentText()
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
        
        pattern = self.ed_filename_pattern.text()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = pattern.format(
            datetime=stamp,
            frame=batch_num,
            mode=self.mode(),
            dpi=self.cb_dpi.currentText(),
            color=self.cb_color.currentText().lower()
        )
        out = pathlib.Path(self.ed_dir.text()) / f"{filename}.{ext}"
        a.output = str(out)
        
        self._wanted = a
        self._do_single_scan(a)
    
    def scan_done(self, paths):
        # HDR-Modus: sammle Ergebnisse und starte nächsten Scan oder merge
        if hasattr(self, '_hdr_index') and hasattr(self, '_hdr_total'):
            self._hdr_results.extend(paths)
            hdr_num = self._hdr_index
            hdr_total = self._hdr_total
            
            if hdr_num < hdr_total:
                # Noch ein Scan im HDR-Modus
                self._start_next_hdr_scan()
                return
            else:
                # HDR abgeschlossen - Scans mergen
                self._merge_hdr_scans()
                return
        # Batch-Modus: sammle Ergebnisse und starte nächsten Scan
        elif hasattr(self, '_batch_index') and hasattr(self, '_batch_total'):
            self._batch_results.extend(paths)
            batch_num = self._batch_index
            batch_total = self._batch_total
            
            if batch_num < batch_total:
                # Noch weitere Scans in der Batch
                self._start_next_batch_scan()
                return
            else:
                # Batch abgeschlossen
                paths = self._batch_results
                del self._batch_index
                del self._batch_total
                del self._batch_results
        
        self._warmup_timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_scan.setEnabled(True)
        if self._raw_path:
            self._show_editor(self._raw_path)
            return
        self._set_status_with_notes(
            f"Done ({len(paths)} image"
            + ("s" if len(paths) != 1 else "") + "):\n"
            + "\n".join(paths))
        self.editor_hint.hide()
        self.preview.set_image(QPixmap(
            self._contact_sheet(paths) if len(paths) > 1 else paths[0]))

    def _show_editor(self, raw_path):
        import numpy as np
        arr = np.array(open_scan(raw_path))
        self.preview.set_image(QPixmap(raw_path))
        self.preview.clear_frames()
        expected = self.sp_frames.value()
        self.preview.set_frames(
            autocrop.detect_film_frames(arr, expected or None))
        self.editor_hint.show()
        self.btn_save.setEnabled(True)
        self._set_status_with_notes(
            "Check the frames or draw your own, then save the crops.")

    def save_frames(self):
        # Ein einziger Scan über die Gesamtfläche aller Rahmen. Jede neue
        # Fenstergeometrie kostet einen vollen Kalibrierzyklus (Motor
        # fährt mehrfach dunkel hin und her), deshalb nicht pro Rahmen
        # scannen, sondern einmal scannen und in Software zuschneiden.
        rects = self.preview.frames()
        if not rects or not self._raw_path:
            self.status.setText("No frames marked.")
            return
        # Einstellungen jetzt lesen, nicht die vom Vorschau-Klick. Der
        # zweite Durchgang ist der Punkt, an dem man nach dem Blick auf
        # die Vorschau ueber die Aufloesung entscheidet - genau diese
        # Entscheidung ging vorher verloren, samt Farbe und Format.
        a = self.build_args()
        a.mode = self._wanted.mode
        self._wanted = a
        mm = 25.4 / PREVIEW_DPI
        ux0 = max(0, min(r[0] for r in rects))
        uy0 = max(0, min(r[1] for r in rects))
        ux1 = max(r[0] + r[2] for r in rects)
        uy1 = max(r[1] + r[3] for r in rects)
        # Waagerecht wird NICHT eingeschraenkt. Der genesys-Treiber
        # liefert auf dem Durchlichtaufsatz eine falsche
        # Shading-Korrektur, sobald die Scanbreite kleiner als das ganze
        # Fenster ist: jede Sensorspalte bekommt den Faktor einer
        # anderen, das Bild wird zu senkrechten Streifen. Gemessen bei
        # 300 dpi Grau, ganzes Fenster sauber, x=59.44 kaputt, und zwar
        # unabhaengig von l und t. Senkrecht einschraenken ist harmlos
        # und spart die meiste Zeit, also nur das.
        left = 0.0
        width = FILM_MAX_X
        top = min(uy0 * mm, FILM_MAX_Y)
        height = min((uy1 - uy0) * mm, FILM_MAX_Y - top)
        if height <= 1:
            self.status.setText("No usable frames.")
            return
        import tempfile
        job = argparse.Namespace(**vars(a))
        job.autocrop = job.split = job.negative = False
        job.frames = 0
        job.format = "tiff"
        job.sane_opt = [f"l={left:.2f}", f"t={top:.2f}",
                        f"x={width:.2f}", f"y={height:.2f}"]
        job.output = tempfile.NamedTemporaryFile(suffix=".tiff",
                                                 delete=False).name
        # Der Scan beginnt jetzt am linken Fensterrand, der waagerechte
        # Nullpunkt der Zuschnitte ist also 0 und nicht mehr ux0.
        self._union_px = (0, uy0)
        self._crop_rects = rects
        self.btn_save.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText(
            f"Scanning selection at {a.dpi} dpi (one pass)…")
        self.crop_worker = ScanWorker(job)
        self.crop_worker.done.connect(self._crops_scan_done)
        self.crop_worker.failed.connect(self.scan_failed)
        self.crop_worker.progress.connect(self.scan_progress)
        self._scan_had_data = False
        self._warmup_seconds = 0
        self.worker = self.crop_worker
        self._warmup_timer.start(1000)
        self.crop_worker.start()

    def _crops_scan_done(self, paths):
        import numpy as np
        from PIL import Image
        a = self._wanted
        arr = np.array(open_scan(paths[0]))
        scale = a.dpi / PREVIEW_DPI
        ux0, uy0 = self._union_px
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        h, w = arr.shape[:2]
        outs = []
        for i, (x, y, rw, rh) in enumerate(self._crop_rects, 1):
            x0 = max(0, int((x - ux0) * scale))
            y0 = max(0, int((y - uy0) * scale))
            x1 = min(w, int((x - ux0 + rw) * scale))
            y1 = min(h, int((y - uy0 + rh) * scale))
            if x1 <= x0 or y1 <= y0:
                continue
            crop = arr[y0:y1, x0:x1]
            if a.negative:
                crop = scan8600.invert_negative(crop)
            
            # Transformationen anwenden
            crop = self._apply_transformations(crop)
            
            p = pathlib.Path(self.ed_dir.text()) / f"scan_{stamp}_{i}.{ext}"
            img = Image.fromarray(crop)
            if a.format == "jpeg":
                img.save(p, quality=95)
            else:
                img.save(p)
            outs.append(str(p))
        self.crops_done(outs)
    
    def _apply_transformations(self, arr):
        """Wendet Rotation und Spiegelung auf das Bild an."""
        import numpy as np
        
        # Rotation
        rotation_index = self.cb_rotation.currentIndex()
        if rotation_index > 0:
            arr = np.rot90(arr, k=rotation_index)
        
        # Spiegelung
        if self.ck_mirror_horizontal.isChecked():
            arr = np.fliplr(arr)
        if self.ck_mirror_vertical.isChecked():
            arr = np.flipud(arr)
        
        return arr

    def crops_done(self, outs):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_scan.setEnabled(True)
        self.btn_save.setEnabled(True)
        self._set_status_with_notes(
            f"{len(outs)} image" + ("s" if len(outs) != 1 else "")
            + " saved:\n" + "\n".join(outs))
        self.editor_hint.hide()
        if outs:
            self.preview.clear_frames()
            self.preview.set_image(QPixmap(
                self._contact_sheet(outs) if len(outs) > 1 else outs[0]))

    @staticmethod
    def _contact_sheet(paths):
        # Übersicht aller erkannten Bilder nebeneinander.
        import tempfile

        from PIL import Image
        # Increase Pillow's image size limit to handle high-DPI scans
        Image.MAX_IMAGE_PIXELS = scan8600.MAX_PIXELS
        thumbs = []
        for p in paths:
            im = open_scan(p).convert("RGB")
            im.thumbnail((360, 360))
            thumbs.append(im)
        gap = 12
        w = sum(t.width for t in thumbs) + gap * (len(thumbs) + 1)
        h = max(t.height for t in thumbs) + 2 * gap
        sheet = Image.new("RGB", (w, h), (48, 48, 48))
        x = gap
        for t in thumbs:
            sheet.paste(t, (x, gap + (h - 2 * gap - t.height) // 2))
            x += t.width + gap
        out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        sheet.save(out.name)
        return out.name

    def _set_status_with_notes(self, text):
        """Statuszeile plus Treiberwarnungen plus Pfad zum Messlog.

        Die Warnungen waren bisher nur im Editor- und Crop-Pfad sichtbar,
        beim einfachen Flachbett-Scan sind sie stillschweigend verfallen.
        """
        if scan8600.LAST_WARNINGS:
            text += "\n\n" + "\n".join(scan8600.LAST_WARNINGS)
        if getattr(scan8600, "LAST_LOG_PATH", None):
            text += f"\n\nScan log: {scan8600.LAST_LOG_PATH}"
        self.status.setText(text)

    def scan_failed(self, msg):
        self._warmup_timer.stop()
        self.progress.setRange(0, 1)
        self.btn_scan.setEnabled(True)
        self.status.setText("Error.")
        QMessageBox.critical(self, "Scan failed", msg)


STYLE = """
QGroupBox { font-weight: 600; margin-top: 12px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; }
QPushButton#scanButton {
    background: #0a84ff; color: white; border: none;
    border-radius: 8px; font-size: 15px; font-weight: 600;
}
QPushButton#scanButton:hover { background: #339cff; }
QPushButton#scanButton:disabled { background: palette(mid); }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    icon = app_icon_path()
    if icon:
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.resize(900, 640)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
