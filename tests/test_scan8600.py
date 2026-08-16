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
