import numpy as np

import descratch
import scan8600

OPTIONS = ("--source Flatbed|Transparency Adapter|"
           "Transparency Adapter Infrared [Flatbed]")


def _synthetic():
    vis = np.full((64, 64, 3), 128, np.uint8)
    ir = np.full((64, 64), 200, np.uint8)
    ir[30:34, 10:50] = 20          # Kratzer blockt IR
    vis[30:34, 10:50] = 255        # sichtbarer weisser Kratzer
    return vis, ir


def test_defect_mask_marks_scratch():
    _, ir = _synthetic()
    m = descratch.defect_mask(ir)
    assert m[32, 30] == 255 and m[5, 5] == 0


def test_remove_defects_inpaints():
    vis, ir = _synthetic()
    out = descratch.remove_defects(vis, ir)
    assert abs(int(out[32, 30, 0]) - 128) < 20
    assert out[5, 5, 0] == 128


def test_find_ir_source():
    assert scan8600.find_ir_source(OPTIONS) == "Transparency Adapter Infrared"
    assert scan8600.find_ir_source("--source Flatbed [Flatbed]") is None


def test_film_source_skips_ir_variant():
    assert scan8600.find_film_source(OPTIONS) == "Transparency Adapter"


def test_invert_negative_brightens_dark():
    arr = np.full((20, 20, 3), 40, np.uint8)
    arr[5:10, 5:10] = 220
    out = scan8600.invert_negative(arr)
    assert out[0, 0, 0] > out[7, 7, 0]


def test_negative_flag_parses():
    a = scan8600.parse_args(["--mode", "film", "--negative"])
    assert a.negative


def test_depth16_adds_depth_flag():
    a = scan8600.parse_args(["--mode", "film", "--depth16"])
    cmd = scan8600.build_command(a, source_name=None)
    assert cmd[cmd.index("--depth") + 1] == "16"


def test_depth16_rejects_postprocessing():
    import pytest
    with pytest.raises(SystemExit):
        scan8600.parse_args(["--mode", "film", "--depth16", "--negative"])


def test_descratch_requires_film_mode():
    import pytest
    with pytest.raises(SystemExit):
        scan8600.parse_args(["--mode", "flatbed", "--descratch"])
