#!/usr/bin/env python3
"""Bewertet einen Durchlicht-Testscan: echtes Bild oder Streifen-Müll.

Streifen-Müll hat praktisch die gesamte Varianz im Spaltenprofil und
keine Zeilenstruktur. Ein echtes Bild hat beides. Ausgabe: GOOD/BAD
plus Kennzahl, Exit-Code 0 bei GOOD, 1 bei BAD (bisect-tauglich).
"""
import sys

import numpy as np
from PIL import Image


def ratio(path):
    a = np.array(Image.open(path).convert("L")).astype(np.float32)
    col = a.mean(axis=0)
    row = a.mean(axis=1)
    col_var = float(col.var())
    row_var = float(row.var())
    if col_var < 1e-6:
        return 99.0
    return row_var / col_var


if __name__ == "__main__":
    r = ratio(sys.argv[1])
    good = r > 0.15
    print(f"{'GOOD' if good else 'BAD'} row/col-var-ratio={r:.4f}")
    sys.exit(0 if good else 1)
