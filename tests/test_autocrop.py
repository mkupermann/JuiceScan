import numpy as np

import autocrop
import scan8600


def _bed_with_photos():
    # Heller Scanner-Deckel (240), zwei dunklere "Fotos"
    img = np.full((400, 300, 3), 240, np.uint8)
    img[40:160, 30:130] = 90     # Foto 1: 120x100
    img[220:360, 150:270] = 60   # Foto 2: 140x120
    return img


def test_detect_regions_finds_both_photos():
    regions = autocrop.detect_regions(_bed_with_photos())
    assert len(regions) == 2
    areas = sorted(w * h for x, y, w, h in regions)
    assert areas[0] >= 100 * 120 * 0.9
    assert areas[1] >= 120 * 140 * 0.9


def test_detect_regions_ignores_specks():
    img = np.full((400, 300, 3), 240, np.uint8)
    img[10:13, 10:13] = 0        # Staubkorn, kein Foto
    assert autocrop.detect_regions(img) == []


def test_crop_to_content_returns_union_bbox():
    img = _bed_with_photos()
    out = autocrop.crop_to_content(img)
    # Union beider Fotos: Zeilen 40..360, Spalten 30..270 (+/- Rand)
    assert 300 <= out.shape[0] <= 340
    assert 220 <= out.shape[1] <= 260


def test_crop_to_content_no_regions_returns_input():
    img = np.full((100, 100, 3), 240, np.uint8)
    out = autocrop.crop_to_content(img)
    assert out.shape == img.shape


def test_cli_flags_parse():
    a = scan8600.parse_args(["--mode", "flatbed", "--autocrop", "--split"])
    assert a.autocrop and a.split


def test_split_requires_autocrop():
    import pytest
    with pytest.raises(SystemExit):
        scan8600.parse_args(["--mode", "flatbed", "--split"])
