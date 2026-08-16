"""IR-basierte Kratzer-/Staubentfernung (Prinzip SilverFast iSRD / FARE)."""
import cv2
import numpy as np


def defect_mask(ir_gray):
    thr, _ = cv2.threshold(ir_gray, 0, 255,
                           cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, mask = cv2.threshold(ir_gray, thr, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((5, 5), np.uint8)
    return cv2.dilate(mask, kernel, iterations=1)


def remove_defects(visible_rgb, ir_gray):
    if ir_gray.shape[:2] != visible_rgb.shape[:2]:
        ir_gray = cv2.resize(ir_gray,
                             (visible_rgb.shape[1], visible_rgb.shape[0]))
    mask = defect_mask(ir_gray)
    return cv2.inpaint(visible_rgb, mask, 3, cv2.INPAINT_TELEA)
