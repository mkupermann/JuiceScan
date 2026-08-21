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


def test_is_silver_film_detects_correlated_ir():
    rng = np.random.default_rng(1)
    pattern = rng.integers(30, 220, (64, 64), dtype=np.uint8)
    vis = np.stack([pattern] * 3, axis=-1)
    ir = pattern.copy()                      # IR spiegelt die Dichte
    assert descratch.is_silver_film(vis, ir)


def test_is_silver_film_negative_on_dye_film():
    vis, ir = _synthetic()                   # IR fast leer, nur Kratzer
    assert not descratch.is_silver_film(vis, ir)


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


def test_invert_neutralizes_color_cast():
    rng = np.random.default_rng(3)
    base = rng.integers(60, 200, (40, 40), dtype=np.uint8).astype(np.int16)
    arr = np.stack([np.clip(base - 40, 0, 255),
                    base,
                    np.clip(base + 20, 0, 255)], axis=-1).astype(np.uint8)
    out = scan8600.invert_negative(arr)
    means = out.reshape(-1, 3).mean(axis=0)
    assert max(means) - min(means) < 12


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


def test_silver_detection_accepts_single_channel():
    import numpy as np
    import descratch
    rng = np.random.default_rng(0)
    vis = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    ir = vis.copy()
    # Sichtbar und IR identisch: das ist der Silberfilm-Fall.
    assert descratch.is_silver_film(vis, ir) is True


def test_flat_infrared_stops_inpainting_instead_of_inviting_it():
    # Frueher meldete is_silver_film bei unbrauchbarem IR-Pass False,
    # was "kein Silberfilm, ruhig uebermalen" heisst. Die Fehlerrichtung
    # war damit falsch herum.
    import numpy as np
    import descratch
    rng = np.random.default_rng(1)
    vis = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    flat_ir = np.full((64, 64), 200, dtype=np.uint8)
    assert descratch.ir_usable(flat_ir) is False
    assert descratch.skip_reason(vis, flat_ir) == descratch.FLAT_IR_HINT


def test_silver_film_is_still_reported_as_such():
    import numpy as np
    import descratch
    rng = np.random.default_rng(2)
    vis = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    assert descratch.skip_reason(vis, vis.copy()) == descratch.SILVER_HINT


def test_usable_and_uncorrelated_infrared_lets_inpainting_run():
    import numpy as np
    import descratch
    rng = np.random.default_rng(3)
    vis = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    ir = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    assert descratch.skip_reason(vis, ir) is None
