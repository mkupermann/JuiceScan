import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import gui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    # Persistente Einstellungen aus der echten Config wuerden die
    # Default-Tests verfaelschen. Jeder Test bekommt eine leere Config.
    import pathlib
    original = gui.CONFIG_FILE
    gui.CONFIG_FILE = pathlib.Path(tmp_path) / "juicescan.json"
    yield
    gui.CONFIG_FILE = original


def test_defaults_flatbed(app):
    w = gui.MainWindow()
    a = w.build_args()
    assert a.mode == "flatbed" and a.dpi == 300
    assert a.format == "tiff" and not a.gray
    assert not a.descratch and not a.split


def test_film_mode_enables_descratch_and_dpi(app):
    w = gui.MainWindow()
    w.rb_film.setChecked(True)
    assert w.ck_descratch.isEnabled()
    a = w.build_args()
    assert a.mode == "film" and a.dpi == 2400


def test_descratch_disabled_on_flatbed(app):
    w = gui.MainWindow()
    w.rb_film.setChecked(True)
    w.ck_descratch.setChecked(True)
    w.rb_flatbed.setChecked(True)
    assert not w.ck_descratch.isChecked()
    assert not w.ck_descratch.isEnabled()


def test_split_requires_autocrop(app):
    w = gui.MainWindow()
    assert not w.ck_split.isEnabled()
    w.ck_autocrop.setChecked(True)
    assert w.ck_split.isEnabled()


def test_grayscale_selection_sets_gray(app):
    w = gui.MainWindow()
    w.cb_color.setCurrentText("Grayscale")
    assert w.build_args().gray
    w.cb_color.setCurrentText("Color")
    assert not w.build_args().gray
