import numpy as np

import autocrop
import scan8600


def _film_strip():
    # Dunkle Umgebung, helles Durchlichtfenster, drei dunklere 6x6-Frames
    img = np.full((400, 160, 3), 12, np.uint8)          # TA-Umgebung
    img[20:380, 40:120] = 230                            # Filmbasis, hell
    for top in (40, 160, 280):
        img[top:top + 90, 48:112] = 70                   # belichtete Frames
    return img


def test_film_window_finds_bright_strip():
    x0, y0, x1, y1 = autocrop.film_window(_film_strip())
    assert x0 <= 40 and x1 >= 120
    assert y0 <= 20 and y1 >= 380


def test_detect_film_frames_finds_three():
    frames = autocrop.detect_film_frames(_film_strip())
    assert len(frames) == 3
    for x, y, w, h in frames:
        assert w >= 55 and h >= 80


def test_detect_film_frames_empty_window():
    img = np.full((200, 100, 3), 12, np.uint8)
    img[10:190, 20:80] = 230
    assert autocrop.detect_film_frames(img) == []


def test_split_film_frames_returns_crops():
    crops = autocrop.split_film_frames(_film_strip())
    assert len(crops) == 3
    assert all(c.shape[0] >= 80 and c.shape[1] >= 55 for c in crops)


def test_expected_frames_splits_evenly():
    # Frames stoßen ohne helle Lücke aneinander, Automatik versagt da.
    img = np.full((400, 160, 3), 12, np.uint8)
    img[20:380, 40:120] = 230
    img[40:340, 48:112] = 70          # ein durchgehender dunkler Block
    frames = autocrop.detect_film_frames(img, expected=2)
    assert len(frames) == 2
    heights = [h for x, y, w, h in frames]
    assert abs(heights[0] - heights[1]) <= 2


def test_film_default_dpi_is_300():
    a = scan8600.parse_args(["--mode", "film"])
    assert a.dpi == 300
