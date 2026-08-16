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
                               QSpinBox,
                               QVBoxLayout, QWidget)

import autocrop
import scan8600
from frameeditor import FrameEditor

RESOLUTIONS = {"flatbed": [300, 600, 1200],
               "film": [300, 600, 1200, 2400, 4800]}
DEFAULT_RES = {"flatbed": "300", "film": "2400"}


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

        out_box = QGroupBox("Destination")
        of = QHBoxLayout(out_box)
        self.ed_dir = QLineEdit(str(pathlib.Path.home() / "Pictures"))
        btn_dir = QPushButton("…")
        btn_dir.clicked.connect(self.pick_dir)
        of.addWidget(self.ed_dir)
        of.addWidget(btn_dir)
        left.addWidget(out_box)

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
        left.addStretch()
        root.addLayout(left, 0)

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
        self.sp_frames.setEnabled(m == "film")
        if m != "film":
            self.ck_negative.setChecked(False)
            self.sp_frames.setValue(0)
        if m != "film":
            self.ck_descratch.setChecked(False)
        self.sync_split()

    def sync_depth16(self):
        # 16 Bit liefert das rohe Treiber-TIFF, jede Nachbearbeitung
        # würde auf 8 Bit reduzieren. Beides zugleich geht nicht.
        processing = (self.ck_descratch.isChecked()
                      or self.ck_negative.isChecked()
                      or self.ck_autocrop.isChecked())
        self.ck_depth16.setEnabled(not processing)
        if self.ck_depth16.isChecked():
            for w in (self.ck_descratch, self.ck_negative,
                      self.ck_autocrop, self.ck_split):
                w.setChecked(False)
                w.setEnabled(False)
            self.cb_format.setCurrentText("tiff")
            self.cb_format.setEnabled(False)
        else:
            self.cb_format.setEnabled(True)
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
            depth16=self.ck_depth16.isChecked(),
            frames=self.sp_frames.value(),
        )

    # --- Scan-Ablauf ------------------------------------------------------
    def start_scan(self):
        self.btn_scan.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Scanning… (first run calibrates and takes longer)")
        a = self.build_args()
        self._wanted = a
        if a.mode == "film" and not a.depth16:
            # Filmscan liefert erst den Rohstreifen. Zuschnitt und
            # Umkehrung passieren nach der Rahmenwahl im Editor.
            import tempfile
            raw = tempfile.NamedTemporaryFile(suffix=".tiff", delete=False)
            a = argparse.Namespace(**vars(a))
            a.autocrop = a.split = a.negative = False
            a.format = "tiff"
            a.output = raw.name
            self._raw_path = raw.name
        else:
            self._raw_path = None
        self.worker = ScanWorker(a)
        self.worker.done.connect(self.scan_done)
        self.worker.failed.connect(self.scan_failed)
        self.worker.start()

    def scan_done(self, paths):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.btn_scan.setEnabled(True)
        if self._raw_path:
            self._show_editor(self._raw_path)
            return
        self.status.setText(f"Done ({len(paths)} image"
                            + ("s" if len(paths) != 1 else "") + "):\n"
                            + "\n".join(paths))
        self.editor_hint.hide()
        self.preview.set_image(QPixmap(
            self._contact_sheet(paths) if len(paths) > 1 else paths[0]))

    def _show_editor(self, raw_path):
        import numpy as np
        from PIL import Image
        arr = np.array(Image.open(raw_path).convert("RGB"))
        self.preview.set_image(QPixmap(raw_path))
        self.preview.clear_frames()
        expected = self.sp_frames.value()
        self.preview.set_frames(
            autocrop.detect_film_frames(arr, expected or None))
        self.editor_hint.show()
        self.btn_save.setEnabled(True)
        self.status.setText(
            "Check the frames or draw your own, then save the crops.")

    def save_frames(self):
        import numpy as np
        from PIL import Image
        rects = self.preview.frames()
        if not rects or not self._raw_path:
            self.status.setText("No frames marked.")
            return
        arr = np.array(Image.open(self._raw_path).convert("RGB"))
        a = self._wanted
        ext = {"tiff": "tiff", "png": "png", "jpeg": "jpg"}[a.format]
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        outs = []
        h, w = arr.shape[:2]
        for i, (x, y, rw, rh) in enumerate(rects, 1):
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(w, x + rw), min(h, y + rh)
            if x1 <= x0 or y1 <= y0:
                continue
            crop = arr[y0:y1, x0:x1]
            if a.negative:
                crop = scan8600.invert_negative(crop)
            p = pathlib.Path(self.ed_dir.text()) / f"scan_{stamp}_{i}.{ext}"
            img = Image.fromarray(crop)
            if a.format == "jpeg":
                img.save(p, quality=95)
            else:
                img.save(p)
            outs.append(str(p))
        self.status.setText(f"{len(outs)} image"
                            + ("s" if len(outs) != 1 else "")
                            + " saved:\n" + "\n".join(outs))

    @staticmethod
    def _contact_sheet(paths):
        # Übersicht aller erkannten Bilder nebeneinander.
        import tempfile

        from PIL import Image
        thumbs = []
        for p in paths:
            im = Image.open(p).convert("RGB")
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

    def scan_failed(self, msg):
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
    w = MainWindow()
    w.resize(900, 640)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
