import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

import frameeditor


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pixmap(w=200, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    return QPixmap.fromImage(img)


def test_set_and_get_frames(app):
    ed = frameeditor.FrameEditor()
    ed.set_image(_pixmap())
    ed.set_frames([(10, 20, 100, 150), (30, 200, 120, 160)])
    frames = ed.frames()
    assert len(frames) == 2
    assert frames[0][:2] == (10, 20)
    assert frames[1][2] >= 118 and frames[1][3] >= 158


def test_clear_frames(app):
    ed = frameeditor.FrameEditor()
    ed.set_image(_pixmap())
    ed.set_frames([(0, 0, 50, 50)])
    ed.clear_frames()
    assert ed.frames() == []


def test_frames_sorted_top_to_bottom(app):
    ed = frameeditor.FrameEditor()
    ed.set_image(_pixmap())
    ed.set_frames([(0, 300, 50, 50), (0, 10, 50, 50)])
    frames = ed.frames()
    assert frames[0][1] < frames[1][1]
