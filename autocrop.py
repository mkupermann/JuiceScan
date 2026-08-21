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


def _as_gray(img):
    """Graukanal, egal ob RGB oder bereits einkanalig hereinkommt.

    Ein Graustufen-Scan hat keine drei Kanäle. cvtColor(RGB2GRAY) wirft
    darauf, deshalb hier die Fallunterscheidung statt beim Aufrufer.
    """
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def detect_regions(img_rgb):
    gray = _as_gray(img_rgb)
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


# --- Film: Rahmenerkennung im Durchlicht ------------------------------
# Beim Filmscan ist die Umgebung dunkel, das Durchlichtfenster mit der
# Filmbasis hell, und die belichteten Frames sind dunkler als die Basis.
# Anteil des Fensters, den ein Frame mindestens belegen muss.
MIN_FRAME_FRAC = 0.02


def film_window(img_rgb):
    gray = _as_gray(img_rgb)
    _, bright = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    if n < 2:
        return 0, 0, img_rgb.shape[1], img_rgb.shape[0]
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = (stats[best, cv2.CC_STAT_LEFT],
                  stats[best, cv2.CC_STAT_TOP],
                  stats[best, cv2.CC_STAT_WIDTH],
                  stats[best, cv2.CC_STAT_HEIGHT])
    return x, y, x + w, y + h


def _content_span(means, base):
    # Reine Filmbasis (hell) am Anfang und Ende abschneiden.
    content = means < base * 0.92
    idx = np.where(content)[0]
    if len(idx) == 0:
        return None
    return int(idx[0]), int(idx[-1]) + 1


def detect_film_frames(img_rgb, expected=None):
    # Profil längs der Streifenachse. Drei Zeilenklassen: helle Filmbasis
    # (Lücke), fast schwarzer Halter-Steg, Bildinhalt (mittlere Helligkeit
    # oder hohe Varianz). Zusammenhängende Inhaltsläufe sind die Frames.
    x0, y0, x1, y1 = film_window(img_rgb)
    win = _as_gray(img_rgb[y0:y1, x0:x1])
    if win.size == 0:
        return []
    vertical = win.shape[0] >= win.shape[1]
    axis = 1 if vertical else 0
    means = win.mean(axis=axis)
    base = float(np.percentile(means, 90))
    span = _content_span(means, base)
    if span is None:
        return []
    lo, hi = span

    def box(a, b):
        if vertical:
            return (x0, y0 + a, x1 - x0, b - a)
        return (x0 + a, y0, b - a, y1 - y0)

    # Vorgegebene Bildanzahl: Inhaltsbereich gleichmäßig teilen. Das ist
    # robust, wenn Frames ohne helle Basis-Lücke aneinanderstoßen
    # (dichter Himmel im Negativ sieht aus wie ein Trennsteg).
    if expected and expected > 0:
        step = (hi - lo) / expected
        return [box(int(lo + i * step), int(lo + (i + 1) * step))
                for i in range(expected)]

    # Automatik: helle Basis-Lücken innerhalb des Inhaltsbereichs trennen.
    axis_len = len(means)
    min_len = max(30, int(0.08 * axis_len))
    is_gap = means[lo:hi] >= base * 0.92
    frames = []
    start = lo
    i = lo
    while i < hi:
        if is_gap[i - lo]:
            j = i
            while j < hi and is_gap[j - lo]:
                j += 1
            if j - i >= max(6, int(0.005 * axis_len)):
                if i - start >= min_len:
                    frames.append(box(start, i))
                start = j
            i = j
        else:
            i += 1
    if hi - start >= min_len:
        frames.append(box(start, hi))
    return frames


def split_film_frames(img_rgb, expected=None):
    crops = []
    for x, y, w, h in detect_film_frames(img_rgb, expected):
        x0, y0, x1, y1 = _pad_box(x, y, w, h, img_rgb.shape)
        crops.append(img_rgb[y0:y1, x0:x1])
    return crops
