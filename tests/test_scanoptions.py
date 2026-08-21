import scanoptions

SAMPLE = """
Options specific to device `genesys:libusb:002:001':
  Scan Mode:
    --mode Color|Gray [Gray]
        Selects the scan mode.
    --source Flatbed|Transparency Adapter|Transparency Adapter Infrared [Flatbed]
        Selects the scan source.
    --resolution 4800|2400|1200|600|300dpi [300]
        Sets the resolution of the scanned image.
    --preview[=(yes|no)] [no]
        Request a preview-quality scan.
  Geometry:
    -l 0..70mm [0]
        Top-left x position of scan area.
    -t 0..230mm [0]
        Top-left y position of scan area.
  Enhancement:
    --brightness -100..100% [0]
        Controls the brightness of the acquired image.
    --custom-gamma[=(yes|no)] [no]
        Determines whether a builtin or a custom gamma-table is used.
"""


def _by_name(opts):
    return {o.name: o for o in opts}


def test_parses_choice_options():
    o = _by_name(scanoptions.parse(SAMPLE))["--mode"]
    assert o.kind == "choice"
    assert o.choices == ["Color", "Gray"]
    assert o.default == "Gray"


def test_strips_unit_from_choices():
    o = _by_name(scanoptions.parse(SAMPLE))["--resolution"]
    assert o.choices == ["4800", "2400", "1200", "600", "300"]
    assert o.default == "300" and o.unit == "dpi"


def test_parses_range_with_negative():
    o = _by_name(scanoptions.parse(SAMPLE))["--brightness"]
    assert o.kind == "range"
    assert (o.lo, o.hi) == (-100.0, 100.0)
    assert o.unit == "%"


def test_parses_bool():
    o = _by_name(scanoptions.parse(SAMPLE))["--custom-gamma"]
    assert o.kind == "bool" and o.default == "no"


def test_parses_short_geometry_options():
    opts = _by_name(scanoptions.parse(SAMPLE))
    assert opts["-l"].kind == "range" and opts["-l"].hi == 70.0


def test_source_choices_keep_spaces():
    o = _by_name(scanoptions.parse(SAMPLE))["--source"]
    assert "Transparency Adapter Infrared" in o.choices


# Genau so gibt der genesys-Treiber des CanoScan 8600F seine Bereiche aus.
HARDWARE = """
Options specific to device `genesys:libusb:000:002':
  Enhancement:
    --brightness -100..100 (in steps of 1) [0]
        Controls the brightness of the acquired image.
  Extras:
    --expiration-time -1..30000 (in steps of 1) [60]
        Time (in minutes) before a cached calibration expires.
"""


def test_parses_quantised_range():
    o = _by_name(scanoptions.parse(HARDWARE))["--brightness"]
    assert o.kind == "range"
    assert (o.lo, o.hi) == (-100.0, 100.0)
    assert o.default == "0"


def test_parses_quantised_range_with_negative_lower_bound():
    o = _by_name(scanoptions.parse(HARDWARE))["--expiration-time"]
    assert (o.lo, o.hi) == (-1.0, 30000.0)
