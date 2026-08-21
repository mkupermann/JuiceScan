## 2026-08-21 — Verdict: Scan-Abbrüche und stockender Motor

- **Verdikt:** PASS (Abbruchursache gefunden und behoben), NULL (H1
  Pipe-Rückstau als Ursache des Stockens), PASS (Ursache des Stockens
  gemessen: Lampen-Warmlauf im Treiber, nicht der Host).
- **Abbruch, bestätigt:** die GUI schickte SANE-Optionen ungeprüft an
  scanimage. `sharpness` gibt es im genesys-Backend nicht; `scanimage`
  bricht bei einer unbekannten Option ab, nachdem es das Gerät schon
  geöffnet hat - Schlitten fährt an, bleibt stehen, kein Bild. Slider
  liefen -1000..1000, der Treiber erlaubt -100..100. In der gespeicherten
  Config stand `brightness: -119`, genau der Wert aus der Fehlermeldung.
  Optionen werden jetzt vor dem Scan gegen `scanimage -A` geprüft
  (`filter_sane_opts`), die Regler bauen ihre Bereiche aus dem Gerät.
  Gegentest auf Hardware: derselbe Aufruf mit `sharpness=50` und
  `brightness=-119` läuft durch, beide Fälle als Warnung sichtbar.
- **H1 (Pipe-Rückstau), NULL:** Vermutung war, dass `capture_output=True`
  den Schreiber blockiert, `sane_read` aussetzt und der Schlitten deshalb
  ab 2400 dpi stehen bleibt (ACDCDIS, kein Backtracking). Die
  Fortschrittsspur widerlegt das: der Datentransfer eines 40x40mm/300dpi
  Scans dauert 3,1 s ohne ein einziges Plateau über 2 s. Der
  Datei-Zweig wurde nach dem NULL wieder entfernt, keine Schwelle
  nachjustiert.
- **Eigentliche Ursache, gemessen:** `SANE_DEBUG_GENESYS=4` zeigt den
  Zeitverlauf eines Passes: 0,0-1,0 s open plus Kalibrier-Cache-Treffer,
  **1,0-18,7 s `genesys_warmup_lamp`** (16 Durchläufe, der Schlitten
  scannt dieselbe Zeile immer wieder), 18,7-28,7 s eigentlicher Scan und
  Parken. Zwei Drittel der Wandzeit sind Warmlauf. Er fällt pro
  scanimage-Prozess an, und die App startet zwei pro Scan (Probe plus
  Pass), drei mit Descratch, vier und mehr im Film-Workflow, 2N im Batch.
  Drei Läufe hintereinander: 32 s, 25 s, 7,3 s bis zum ersten Byte - der
  Warmlauf konvergiert, sobald die Lampe warm ist.
- **Messtechnik, bleibt:** `-p` an scanimage, stderr-Reader mit
  Zeitstempeln, Stufenzeiten über `stage()`, Log neben der Ausgabedatei.
  Wichtig: der Fortschritt wird einmal pro `sane_read` gedruckt, die
  Puffergröße ist also die Messauflösung. Mit den 4 MB aus dem
  Regelbetrieb bekommt man bei kleinen Scans genau einen Messpunkt.
  `JUICESCAN_BUFFER_KB=32` für Messläufe. Das ist kein Widerspruch zur
  Buffer-NULL vom 2026-08-17: dort war die Puffergröße der
  Behandlungsfaktor, hier ist sie die Auflösung des Messgeräts.
- **Nebenbefunde:** `np` war weder in `scan8600.py` noch in `gui.py` ein
  Modul-Global; `_save_array` und `_blend_exposures` sind zwingend mit
  NameError gestorben (jeder Save ausser Plain-TIFF, jeder HDR-Merge).
  `scanoptions._RANGE` kannte die Treiberform
  `-100..100 (in steps of 1)` nicht und hat brightness und contrast
  komplett aus der Liste fallen lassen - ohne Fix hätte die neue
  Validierung sie fälschlich verworfen. Auf echter Hardware gefunden,
  nicht am Quelltext.
- **Offen:** Der Warmlauf pro Prozess ist der eigentliche Hebel, nicht
  die Datenrate. Die GUI-Option "Lamp Warm-up" schläft vor dem Öffnen
  des Geräts und wärmt daher nichts, blockiert aber bis zu 60 s die
  Oberfläche. Ebenfalls offen, aber unbelegt: der Speicherverbrauch des
  Pipe-Wegs bei 4800 dpi (mehrere GB, transiente 2x-Spitze) - eigene
  Messung nötig, nicht mit H1 vermischen.

## 2026-08-17 — Verdict: JuiceScan v1.1 field day

- **Verdict:** PASS overall (core stack, high-res transparency), PARTIAL
  (frame auto-detection → assisted editor; IR descratch limited by
  silver-film physics; color casts from cold lamp), NULL (exposure-based
  speed experiment: predicted ~2x, measured none, motor-bound, reverted).
- **Evidence:** 48 tests green; TA ladder 300–4800 dpi verified on
  hardware (row/col metrics 7–35); scan 40x30mm@2400 ≈ 2 min regardless
  of buffer; exposure 24000: 202s vs baseline 133s.
- **Prediction check:** three misses recorded (calibration-slot symptom
  misread as driver bug; exposure≠throughput; libtool install names
  untrustworthy). Mental-model fixes in IMprovement-roadmap.md.
- **Honesty checks:** experiment reverted after NULL, no threshold moved
  post-hoc; 300-dpi-cap release was published on a wrong diagnosis and
  explicitly corrected; scope change on frame detection recorded as
  PARTIAL, not PASS.
- **Learned:** physical light path first; option order is API; verify
  shipped binaries, never trust relink; UI strings in comparisons are API.
- **Next:** notarized signing, lamp warm-up guard, multi-exposure
  (see docs/IMprovement-roadmap.md).
