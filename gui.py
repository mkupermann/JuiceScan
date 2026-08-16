#!/usr/bin/env python3
"""scan8600 GUI - PySide6-Oberfläche für Flachbett- und Durchlicht-Scans."""
import argparse
import datetime
import pathlib
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                               QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget)

import scan8600

RESOLUTIONS = {"flatbed": [300, 600, 1200],
               "film": [300, 600, 1200, 2400, 4800]}
DEFAULT_RES = {"flatbed": "300", "film": "1200"}


class ScanWorker(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, args):
        super().__init__()
        self.args = args

    def run(self):
        try:
            self.done.emit([str(p) for p in scan8600.run_scan(self.args)])
        except scan8600.ScanError as e:
            self.failed.emit(str(e))
        except Exception as e:  # Treiber-/IO-Fehler sichtbar machen
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CanoScan 8600F")
        self.worker = None
        root = QHBoxLayout(self)

        # Linke Spalte: Einstellungen
        left = QVBoxLayout()
        mode_box = QGroupBox("Modus")
        mb = QHBoxLayout(mode_box)
        self.rb_flatbed = QRadioButton("Flachbett")
        self.rb_film = QRadioButton("Durchlicht (Film/Dia)")
        self.rb_flatbed.setChecked(True)
        mb.addWidget(self.rb_flatbed)
        mb.addWidget(self.rb_film)
        left.addWidget(mode_box)

        form_box = QGroupBox("Einstellungen")
        form = QFormLayout(form_box)
        self.cb_dpi = QComboBox()
        self.cb_color = QComboBox()
        self.cb_color.addItems(["Farbe", "Graustufen"])
        self.cb_format = QComboBox()
        self.cb_format.addItems(["tiff", "png", "jpeg"])
        form.addRow("Auflösung (dpi)", self.cb_dpi)
        form.addRow("Farbe", self.cb_color)
        form.addRow("Format", self.cb_format)
        left.addWidget(form_box)

        opt_box = QGroupBox("Verarbeitung")
        ob = QVBoxLayout(opt_box)
        self.ck_descratch = QCheckBox("Kratzer entfernen (Infrarot)")
        self.ck_negative = QCheckBox("Negativ umkehren")
        self.ck_autocrop = QCheckBox("Größe automatisch erkennen")
        self.ck_split = QCheckBox("Fotos einzeln speichern")
        ob.addWidget(self.ck_negative)
        ob.addWidget(self.ck_descratch)
        ob.addWidget(self.ck_autocrop)
        ob.addWidget(self.ck_split)
        left.addWidget(opt_box)

        out_box = QGroupBox("Ziel")
        of = QHBoxLayout(out_box)
        self.ed_dir = QLineEdit(str(pathlib.Path.home() / "Pictures"))
        btn_dir = QPushButton("…")
        btn_dir.clicked.connect(self.pick_dir)
        of.addWidget(self.ed_dir)
        of.addWidget(btn_dir)
        left.addWidget(out_box)

        self.btn_scan = QPushButton("Scannen")
        self.btn_scan.setObjectName("scanButton")
        self.btn_scan.setMinimumHeight(44)
        self.btn_scan.clicked.connect(self.start_scan)
        left.addWidget(self.btn_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        left.addWidget(self.progress)
        self.status = QLabel("Bereit.")
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        left.addStretch()
        root.addLayout(left, 0)

        # Rechte Spalte: Vorschau
        self.preview = QLabel("Vorschau")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 560)
        self.preview.setStyleSheet(
            "QLabel { border: 1px solid palette(mid); }")
        root.addWidget(self.preview, 1)

        self.rb_flatbed.toggled.connect(self.sync_mode)
        self.ck_autocrop.toggled.connect(self.sync_split)
        self.sync_mode()

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
        if m != "film":
            self.ck_negative.setChecked(False)
        if m != "film":
            self.ck_descratch.setChecked(False)
        self.sync_split()

    def sync_split(self):
        self.ck_split.setEnabled(self.ck_autocrop.isChecked())
        if not self.ck_autocrop.isChecked():
            self.ck_split.setChecked(False)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Zielordner", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def build_args(self):
        fmt = self.cb_format.currentText()
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[fmt]
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = pathlib.Path(self.ed_dir.text()) / f"scan_{stamp}.{ext}"
        return argparse.Namespace(
            mode=self.mode(),
            dpi=int(self.cb_dpi.currentText()),
            format=fmt,
            output=str(out),
            gray=self.cb_color.currentText() == "Graustufen",
            descratch=self.ck_descratch.isChecked(),
            negative=self.ck_negative.isChecked(),
            autocrop=self.ck_autocrop.isChecked(),
            split=self.ck_split.isChecked(),
        )

    # --- Scan-Ablauf ------------------------------------------------------
    def start_scan(self):
        self.btn_scan.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Scanne… (erster Lauf kalibriert, dauert länger)")
        self.worker = ScanWorker(self.build_args())
        self.worker.done.connect(self.scan_done)
        self.worker.failed.connect(self.scan_failed)
        self.worker.start()

    def scan_done(self, paths):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_scan.setEnabled(True)
        self.status.setText("Fertig:\n" + "\n".join(paths))
        pix = QPixmap(paths[0])
        if not pix.isNull():
            self.preview.setPixmap(pix.scaled(
                self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def scan_failed(self, msg):
        self.progress.setRange(0, 1)
        self.btn_scan.setEnabled(True)
        self.status.setText("Fehler.")
        QMessageBox.critical(self, "Scan fehlgeschlagen", msg)


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
    w = MainWindow()
    w.resize(900, 640)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
