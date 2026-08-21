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
