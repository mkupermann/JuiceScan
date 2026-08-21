import scan8600


def test_default_dpi_flatbed():
    a = scan8600.parse_args(["--mode", "flatbed"])
    assert a.dpi == 300 and a.format == "tiff" and not a.gray


def test_default_dpi_film():
    a = scan8600.parse_args(["--mode", "film"])
    assert a.dpi == 2400


def test_build_command_flatbed_color():
    a = scan8600.parse_args(["--mode", "flatbed", "--dpi", "600"])
    cmd = scan8600.build_command(a, source_name=None)
    assert cmd[0] == str(scan8600.SCANIMAGE)
    assert "--format=tiff" in cmd and "--resolution" in cmd
    assert cmd[cmd.index("--resolution") + 1] == "600"
    assert cmd[cmd.index("--mode") + 1] == "Color"
    assert "--source" not in cmd


def test_build_command_film_gray_sets_source():
    a = scan8600.parse_args(["--mode", "film", "--gray"])
    cmd = scan8600.build_command(a, source_name="Transparency Adapter")
    assert cmd[cmd.index("--source") + 1] == "Transparency Adapter"
    assert cmd[cmd.index("--mode") + 1] == "Gray"
    # Quelle muss vor der Auflösung stehen, sonst rundet scanimage die
    # Auflösung gegen die Flachbett-Liste ab.
    assert cmd.index("--source") < cmd.index("--resolution")


def test_sane_opt_passthrough():
    a = scan8600.parse_args(["--mode", "flatbed",
                             "--sane-opt", "brightness=10",
                             "--sane-opt", "l=5"])
    cmd = scan8600.build_command(a, source_name=None)
    assert cmd[cmd.index("--brightness") + 1] == "10"
    assert cmd[cmd.index("-l") + 1] == "5"


def test_default_output_name_has_extension():
    a = scan8600.parse_args(["--mode", "flatbed", "--format", "png"])
    assert scan8600.default_output(a).endswith(".png")


# --- Optionsvalidierung gegen das Gerät ---------------------------------
#
# scanimage bricht bei einer unbekannten Option ab, nachdem es das Gerät
# schon geöffnet hat: der Schlitten fährt an und bleibt stehen, ohne dass
# ein Bild entsteht. Deshalb wird vorher gefiltert.

DEVICE_OPTS = """
Options specific to device `genesys:libusb:002:001':
  Enhancement:
    --brightness -100..100% [0]
        Controls the brightness of the acquired image.
    --contrast -100..100% [0]
        Controls the contrast of the acquired image.
  Geometry:
    -l 0..70mm [0]
        Top-left x position of scan area.
"""


def test_progress_flag_is_passed_to_scanimage():
    a = scan8600.parse_args(["--mode", "flatbed"])
    assert "-p" in scan8600.build_command(a, source_name=None)


def test_unsupported_option_is_dropped_with_warning():
    scan8600.LAST_WARNINGS.clear()
    kept = scan8600.filter_sane_opts(["sharpness=50"], DEVICE_OPTS)
    assert kept == []
    assert any("sharpness" in w for w in scan8600.LAST_WARNINGS)


def test_out_of_range_value_is_clamped_with_warning():
    scan8600.LAST_WARNINGS.clear()
    kept = scan8600.filter_sane_opts(["brightness=-119"], DEVICE_OPTS)
    assert kept == ["brightness=-100"]
    assert any("clamped" in w for w in scan8600.LAST_WARNINGS)


def test_value_inside_range_is_untouched():
    scan8600.LAST_WARNINGS.clear()
    kept = scan8600.filter_sane_opts(["brightness=-50", "l=5.0"], DEVICE_OPTS)
    assert kept == ["brightness=-50", "l=5.0"]
    assert scan8600.LAST_WARNINGS == []


def test_unparsable_option_text_lets_everything_through():
    # Ohne verwertbare Optionsliste nicht auf Verdacht wegwerfen.
    scan8600.LAST_WARNINGS.clear()
    assert scan8600.filter_sane_opts(["sharpness=50"], "") == ["sharpness=50"]


def test_save_array_handles_16bit(tmp_path):
    # Regression: numpy war in _save_array nicht im Namensraum, jeder Save
    # außerhalb des Plain-TIFF-Schnellpfads ist mit NameError gestorben.
    import numpy as np
    a = scan8600.parse_args(["--mode", "flatbed", "--depth16"])
    p = tmp_path / "x.tiff"
    scan8600._save_array(np.zeros((4, 4), dtype=np.uint16), a, p)
    assert p.exists()


def test_save_array_handles_8bit_rgb(tmp_path):
    import numpy as np
    a = scan8600.parse_args(["--mode", "flatbed"])
    p = tmp_path / "y.tiff"
    scan8600._save_array(np.zeros((4, 4, 3), dtype=np.uint8), a, p)
    assert p.exists()


# --- Warmlauf sichtbar machen, Geräte-Öffnungen reduzieren ---------------


def test_options_are_probed_once_per_device(monkeypatch):
    calls = []

    def fake_probe(retries=3):
        calls.append("no-device")
        return DEVICE_OPTS

    scan8600.clear_options_cache()
    monkeypatch.setattr(scan8600, "_probe_options", fake_probe)
    scan8600.setup_logging(scan8600.parse_args(["--mode", "flatbed"]))
    assert scan8600.probe_options() == DEVICE_OPTS
    assert scan8600.probe_options() == DEVICE_OPTS
    assert len(calls) == 1
    scan8600.clear_options_cache()
    assert scan8600.probe_options() == DEVICE_OPTS
    assert len(calls) == 2


def test_scan_run_reports_progress(tmp_path):
    # Der Fortschritt ist das einzige Signal, das den Warmlauf vom
    # eigentlichen Scan trennt: vor dem ersten Prozentwert kommen keine
    # Bilddaten, obwohl der Schlitten fährt.
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    scan8600.setup_logging(a)
    seen = []
    fake = ["python3", "-c",
            "import sys\n"
            "for p in (10.0, 55.5, 100.0):\n"
            "    sys.stderr.write('Progress: %5.1f%%\\r' % p)\n"
            "    sys.stderr.flush()\n"
            "sys.stdout.buffer.write(b'DATA')\n"]
    rc, payload, err = scan8600.scan_run(fake, on_progress=lambda p, t: seen.append(p))
    assert rc == 0 and payload == b"DATA"
    assert [p for p in seen] == [10.0, 55.5, 100.0]
    # Progress darf nicht im Fehlertext landen.
    assert err == ""


def test_progress_callback_errors_do_not_kill_the_scan(tmp_path):
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    scan8600.setup_logging(a)
    fake = ["python3", "-c",
            "import sys; sys.stderr.write('Progress:  50.0%\\r'); "
            "sys.stderr.flush(); sys.stdout.buffer.write(b'DATA')\n"]

    def boom(percent, elapsed):
        raise RuntimeError("callback exploded")

    rc, payload, _ = scan8600.scan_run(fake, on_progress=boom)
    assert rc == 0 and payload == b"DATA"


# --- Graustufen bleiben einkanalig --------------------------------------


def _tiff_bytes(mode, size=(40, 30)):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new(mode, size, 128 if mode == "L" else (128, 90, 60)).save(buf, "TIFF")
    return buf.getvalue()


def test_grayscale_scan_is_not_inflated_to_rgb(tmp_path):
    # Ein Graustufen-Scan hat einen Kanal. Ihn auf RGB aufzublasen
    # verdreifacht Datei und Arbeitsspeicher ohne Informationsgewinn.
    from PIL import Image
    out = tmp_path / "gray.tiff"
    a = scan8600.parse_args(["--mode", "flatbed", "--gray", "--negative",
                             "--output", str(out)])
    scan8600.setup_logging(a)
    scan8600._finalize(_tiff_bytes("L"), None, a, out)
    assert Image.open(out).mode == "L"


def test_colour_scan_still_lands_as_rgb(tmp_path):
    from PIL import Image
    out = tmp_path / "colour.tiff"
    a = scan8600.parse_args(["--mode", "flatbed", "--negative",
                             "--output", str(out)])
    scan8600.setup_logging(a)
    scan8600._finalize(_tiff_bytes("RGB"), None, a, out)
    assert Image.open(out).mode == "RGB"


def test_grayscale_output_is_a_third_of_the_size(tmp_path):
    out_g = tmp_path / "g.tiff"
    out_c = tmp_path / "c.tiff"
    ag = scan8600.parse_args(["--mode", "flatbed", "--gray", "--negative",
                              "--output", str(out_g)])
    ac = scan8600.parse_args(["--mode", "flatbed", "--negative",
                              "--output", str(out_c)])
    scan8600.setup_logging(ag)
    scan8600._finalize(_tiff_bytes("L"), None, ag, out_g)
    scan8600._finalize(_tiff_bytes("RGB"), None, ac, out_c)
    assert out_g.stat().st_size * 2 < out_c.stat().st_size


# --- Abbrechen -----------------------------------------------------------


def test_cancel_terminates_the_running_pass(tmp_path):
    # Ohne Abbruch blieb nur, die App zu beenden - und das liess
    # scanimage als Waise weiterlaufen, mit dem Geraet in der Hand.
    import threading
    import time
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    scan8600.setup_logging(a)
    scan8600.begin_scan_session()
    slow = ["python3", "-c", "import time; time.sleep(30)"]

    def stopper():
        for _ in range(100):
            if scan8600._RUNNING["proc"] is not None:
                break
            time.sleep(0.02)
        scan8600.cancel_scan(kill_after=5.0)

    t = threading.Thread(target=stopper)
    t.start()
    started = time.monotonic()
    rc, payload, _ = scan8600.scan_run(slow)
    t.join()
    assert time.monotonic() - started < 10, "Abbruch hat nicht gegriffen"
    assert rc != 0
    assert scan8600.scan_was_cancelled()


def test_cancel_without_a_running_scan_is_harmless():
    scan8600.begin_scan_session()
    assert scan8600.cancel_scan() is False


def test_a_new_session_clears_the_cancel_flag():
    scan8600.begin_scan_session()
    scan8600.cancel_scan()
    assert scan8600.scan_was_cancelled()
    scan8600.begin_scan_session()
    assert not scan8600.scan_was_cancelled()


def test_the_process_registry_is_empty_after_a_pass(tmp_path):
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    scan8600.setup_logging(a)
    scan8600.begin_scan_session()
    scan8600.scan_run(["python3", "-c", "pass"])
    assert scan8600._RUNNING["proc"] is None


def test_buffer_default_keeps_cancelling_quick(monkeypatch):
    # Der Puffer bestimmt die Abbruchdauer: gemessen 8,3 s bei 256 KB
    # gegen 37,3 s bei 4 MB. Deshalb ist der Standard klein.
    monkeypatch.delenv("JUICESCAN_BUFFER_KB", raising=False)
    assert scan8600.buffer_kb() == 256
    monkeypatch.setenv("JUICESCAN_BUFFER_KB", "32")
    assert scan8600.buffer_kb() == 32
    monkeypatch.setenv("JUICESCAN_BUFFER_KB", "unsinn")
    assert scan8600.buffer_kb() == 256


def test_cancel_without_waiting_returns_at_once(tmp_path):
    # Die Oberflaeche und ein Signalhandler duerfen hier nicht
    # stehenbleiben: der Treiber braucht Sekunden zum Parken.
    import time
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    scan8600.setup_logging(a)
    scan8600.begin_scan_session()
    import subprocess as sp
    proc = sp.Popen(["python3", "-c", "import time; time.sleep(30)"])
    with scan8600._RUNNING_LOCK:
        scan8600._RUNNING["proc"] = proc
    t0 = time.monotonic()
    assert scan8600.cancel_scan(wait=False) is True
    assert time.monotonic() - t0 < 1.0, "cancel_scan hat blockiert"
    proc.wait(timeout=10)
    with scan8600._RUNNING_LOCK:
        scan8600._RUNNING["proc"] = None


def test_cli_installs_handlers_that_release_the_scanner():
    # Ein Signal an die CLI beendete frueher nur Python und liess
    # scanimage als Waise mit dem Geraet in der Hand zurueck.
    import signal
    old = {s: signal.getsignal(s)
           for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        scan8600.install_signal_handlers()
        scan8600.begin_scan_session()
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)          # kein laufender Scan
        assert scan8600.scan_was_cancelled()
    finally:
        for s, h in old.items():
            signal.signal(s, h)
        scan8600.begin_scan_session()


def test_grace_depends_on_whether_data_is_flowing():
    # Laeuft der Scan, wirkt SIGTERM und man wartet gern. Steckt der
    # Treiber noch in sane_start, ist der Abbruch verloren - nachgemessen
    # mit 200 s Geduld ohne Ende. Dort ist Warten nur Verzoegerung.
    assert scan8600.KILL_AFTER_WHILE_WARMING < 15.0
    assert scan8600.KILL_AFTER_WHILE_SCANNING > 40.0
    scan8600.begin_scan_session()
    assert scan8600._RUNNING["got_data"] is False
