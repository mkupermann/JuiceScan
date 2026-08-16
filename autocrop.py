"""Automatische Erkennung von Fotos/Dokumenten auf dem Flachbett.

Grenze: weisses Dokument auf weissem Hintergrund ist unzuverlässig —
kontrastreiche Auflage (z. B. schwarzes Tonpapier hinter dem Dokument)
verbessert die Erkennung deutlich.
"""
import cv2
import numpy as np

# Regionen kleiner als dieser Anteil der Scanfläche sind Staub/Rauschen.
MIN_AREA_FRAC = 0.005
# Rand in Pixeln, der um erkannte Regionen herum erhalten bleibt.
PAD = 8


def detect_regions(img_rgb):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    min_area = MIN_AREA_FRAC * img_rgb.shape[0] * img_rgb.shape[1]
    regions = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h >= min_area:
            regions.append((x, y, w, h))
    return sorted(regions, key=lambda r: (r[1], r[0]))


def _pad_box(x, y, w, h, shape):
    x0 = max(0, x - PAD)
    y0 = max(0, y - PAD)
    x1 = min(shape[1], x + w + PAD)
    y1 = min(shape[0], y + h + PAD)
    return x0, y0, x1, y1


def crop_to_content(img_rgb):
    regions = detect_regions(img_rgb)
    if not regions:
        return img_rgb
    x0 = min(x for x, y, w, h in regions)
    y0 = min(y for x, y, w, h in regions)
    x1 = max(x + w for x, y, w, h in regions)
    y1 = max(y + h for x, y, w, h in regions)
    x0, y0, x1, y1 = _pad_box(x0, y0, x1 - x0, y1 - y0, img_rgb.shape)
    return img_rgb[y0:y1, x0:x1]


def split_regions(img_rgb):
    crops = []
    for x, y, w, h in detect_regions(img_rgb):
        x0, y0, x1, y1 = _pad_box(x, y, w, h, img_rgb.shape)
        crops.append(img_rgb[y0:y1, x0:x1])
    return crops
