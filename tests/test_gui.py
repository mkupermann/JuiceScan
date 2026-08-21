import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Kein scanimage -A aus den Tests heraus: jeder Aufruf öffnet das
# Gerät und bewegt den Schlitten.
os.environ.setdefault("JUICESCAN_NO_PROBE", "1")

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


DEVICE_OPTS = """
Options specific to device `genesys:libusb:002:001':
  Enhancement:
    --brightness -100..100% [0]
        Controls the brightness of the acquired image.
    --contrast -100..100% [0]
        Controls the contrast of the acquired image.
"""


def _window_with_fake_device(dev="test:fake:0"):
    import scanoptions
    w = gui.MainWindow()
    # Erst das Fenster bauen: refresh_devices im Konstruktor leert den
    # Cache absichtlich, damit ein Geraetewechsel nicht gegen alte
    # Optionen validiert.
    gui.DEVICE_OPTS_CACHE[dev] = {o.name: o
                                  for o in scanoptions.parse(DEVICE_OPTS)}
    w.cb_device.clear()
    w.cb_device.addItem("Fake scanner", userData=dev)
    w.cb_device.setCurrentIndex(0)
    w._sync_advanced_to_device()
    return w


def test_slider_ranges_come_from_the_driver(app):
    w = _window_with_fake_device()
    assert w.slider_brightness.minimum() == -100
    assert w.slider_brightness.maximum() == 100
    assert w.slider_contrast.minimum() == -100


def test_option_the_scanner_lacks_is_disabled(app):
    # sharpness kennt der genesys-Treiber nicht. Früher ging sie trotzdem
    # raus und scanimage brach ab, nachdem der Schlitten schon lief.
    w = _window_with_fake_device()
    assert not w.slider_sharpness.isEnabled()
    assert w.slider_sharpness.value() == 0
    a = w.build_args()
    assert not any(o.startswith("sharpness") for o in a.sane_opt)


def test_out_of_range_setting_is_clamped_to_the_driver(app):
    w = _window_with_fake_device()
    w.slider_brightness.setValue(-119)
    assert w.slider_brightness.value() == -100


def test_hdr_exposures_stay_inside_driver_range(app):
    w = _window_with_fake_device()
    w.slider_brightness.setValue(80)
    w.slider_hdr_comp.setValue(100)
    first, second = w._get_hdr_exposures()
    assert first == 80 and second == 100


def test_blend_exposures_runs(app):
    # Regression: numpy war in _blend_exposures nicht im Namensraum, jeder
    # HDR-Merge ist mit NameError gestorben - auf dem Main-Thread, also
    # ungefangen.
    import numpy as np
    w = gui.MainWindow()
    dark = np.zeros((2, 2, 3), dtype=np.uint8)
    bright = np.full((2, 2, 3), 255, dtype=np.uint8)
    out = w._blend_exposures(dark, bright)
    assert out.shape == (2, 2, 3) and out.dtype == np.uint8
    assert int(out[0, 0, 0]) == 127


def test_progress_switches_the_bar_from_spinner_to_percent(app):
    w = gui.MainWindow()
    w.progress.setRange(0, 0)          # der bisherige Endlos-Spinner
    w._scan_had_data = False
    w.scan_progress(42.0, 7.0)
    assert w.progress.maximum() == 100
    assert w.progress.value() == 42
    assert w._scan_had_data
    assert "42" in w.status.text()


def test_warmup_message_appears_only_after_a_few_seconds(app):
    # Vor dem ersten Byte fährt der Schlitten, ohne dass ein Bild
    # entsteht. Die Oberfläche hat dazu "Scanning…" behauptet.
    w = gui.MainWindow()
    w.worker = object()
    w._scan_had_data = False
    w._warmup_seconds = 0
    w.status.setText("start")
    w._tick_warmup()
    assert w.status.text() == "start"      # 1 s: noch nichts sagen
    w._tick_warmup()
    w._tick_warmup()
    assert "lamp" in w.status.text().lower()
    assert "3 s" in w.status.text()


def test_warmup_ticker_stops_once_data_arrives(app):
    w = gui.MainWindow()
    w.worker = object()
    w._scan_had_data = True
    w.status.setText("unchanged")
    w._tick_warmup()
    assert w.status.text() == "unchanged"


def test_lamp_warmup_control_is_gone(app):
    # Die Option hat vor dem Oeffnen des Geraets geschlafen und damit
    # nichts gewaermt, dafuer die Oberflaeche bis zu 60 s blockiert.
    w = gui.MainWindow()
    for attr in ("ck_lamp_warmup", "sp_lamp_duration", "toggle_lamp_warmup"):
        assert not hasattr(w, attr), f"{attr} lebt noch"


def test_start_scan_does_not_sleep_on_the_gui_thread():
    import inspect
    src = inspect.getsource(gui.MainWindow.start_scan)
    assert "sleep" not in src


def test_open_scan_keeps_a_grayscale_file_single_channel(tmp_path):
    from PIL import Image
    p = tmp_path / "g.tiff"
    Image.new("L", (20, 10), 100).save(p)
    assert gui.open_scan(p).mode == "L"
    p2 = tmp_path / "c.tiff"
    Image.new("RGB", (20, 10), (1, 2, 3)).save(p2)
    assert gui.open_scan(p2).mode == "RGB"
