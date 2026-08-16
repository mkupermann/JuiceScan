"""IR-basierte Kratzer-/Staubentfernung (Prinzip SilverFast iSRD / FARE)."""
import cv2
import numpy as np


def defect_mask(ir_gray):
    thr, _ = cv2.threshold(ir_gray, 0, 255,
                           cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, mask = cv2.threshold(ir_gray, thr, 255, cv2.THRESH_BINARY_INV)
    # Kratzer und Staub sind klein und schmal. Grosse oder randberührende
    # dunkle Flächen sind Filmhalter, Bildrand oder dichte Negativpartien
    # und dürfen nicht übermalt werden.
    h, w = mask.shape
    max_area = max(400, int(0.01 * h * w))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    out = np.zeros_like(mask)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area > max_area:
            continue
        if x == 0 or y == 0 or x + bw == w or y + bh == h:
            continue
        out[labels == i] = 255
    kernel = np.ones((5, 5), np.uint8)
    return cv2.dilate(out, kernel, iterations=1)


def is_silver_film(visible_rgb, ir_gray):
    """Silberbasierter S/W-Film blockt Infrarot flächig. Das IR-Bild ist
    dann eine Dichtekarte des Motivs statt einer fast leeren Staubkarte,
    und Inpainting würde Bildinhalt zerstören."""
    g = cv2.cvtColor(visible_rgb, cv2.COLOR_RGB2GRAY)
    size = (256, 256)
    sg = cv2.resize(g, size).astype(np.float32).ravel()
    si = cv2.resize(ir_gray, size).astype(np.float32).ravel()
    if si.std() < 5 or sg.std() < 5:
        return False
    corr = float(np.corrcoef(sg, si)[0, 1])
    return corr > 0.6


def remove_defects(visible_rgb, ir_gray):
    if ir_gray.shape[:2] != visible_rgb.shape[:2]:
        ir_gray = cv2.resize(ir_gray,
                             (visible_rgb.shape[1], visible_rgb.shape[0]))
    mask = defect_mask(ir_gray)
    return cv2.inpaint(visible_rgb, mask, 3, cv2.INPAINT_TELEA)
