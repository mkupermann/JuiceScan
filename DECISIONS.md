## 2026-08-21 — Verdict: senkrechte Streifen im Film-Workflow (#23, #24)

- **Verdikt:** PASS (Ursache isoliert und behoben), NULL (zwei
  Hypothesen unterwegs verworfen).
- **Symptom:** Vorschau sauber, die fertigen Zuschnitte fast weiß mit
  senkrechten Linien. Rohdaten aus den überlebenden Temp-Dateien:
  Streuung längs einer Spalte 9,3 gegen 65,0 bei der Vorschau, Sprung
  zwischen Nachbarspalten p99 244 gegen 8,4. Jede Sensorspalte trägt
  einen konstanten falschen Wert — Shading-Korrektur, nicht Bildinhalt.
  Unsere Invertierung mit 1/99-Perzentil-Streckung verstärkt das nur.
- **H1 (gecachte Kalibrierung), NULL.** Naheliegend, weil wir den Cache
  mit `--expiration-time -1` festnageln. Cache geleert, Streifen
  unverändert. Verworfen.
- **H2 (verdeckter Kalibrierschlitz), NULL.** Steht als bekannte Falle
  im README. Widerlegt durch die Vorschau: sie kalibriert über
  denselben Schlitz und ist sauber.
- **Ursache, isoliert.** Eine Variable nach der anderen, 300 dpi Grau,
  y=20 zum Zeitsparen: ganzes Fenster sauber; nur vertikal versetzt
  (t=14,22, x=70) **sauber**; nur schmaler (x=59,44, l=0) kaputt; l=7,79
  mit rechter Kante am Rand kaputt. **Es ist allein die Breite.** Der
  Treiber legt die Shading-Tabelle waagerecht versetzt an, jede
  Ausgabespalte bekommt den Faktor einer anderen. Flachbett ist bei 216
  und bei 40 mm sauber, also nur der Durchlichtaufsatz.
- **Bitter:** Der Zuschnitt im Scanner war eine bewusste Optimierung —
  einmal über die Gesamtfläche scannen statt pro Rahmen, um
  Kalibrierzyklen zu sparen. Genau diese Optimierung hat das Bild
  zerstört. Jetzt volle Breite, senkrecht einschränken, waagerecht in
  Software zuschneiden. Kostet rund 18 % mehr Daten und keine Qualität.
- **Zweiter Fund, #24.** `save_frames` benutzte die Einstellungen vom
  Vorschau-Klick. Im Panel stand 1200 dpi, gescannt wurde mit 300, die
  Zuschnitte kamen 688 statt 2600 Pixel breit — lautlos. Der zweite
  Durchgang liest die Einstellungen jetzt frisch.
- **Belegt auf Hardware:** derselbe Ausschnitt über die volle Breite,
  Streuung längs Spalte 65,8, Sprung p99 11,1, drei erkennbare 6x6-Bilder.

## 2026-08-21 — Entscheidung: Graustufen bleiben einkanalig, Warmlauf-Option entfernt (#7, #8)

- **#7, PASS.** `_finalize` hat jeden Nicht-16-Bit-Scan mit
  `.convert("RGB")` dekodiert. Ein Graustufen-Scan bekam damit drei
  identische Kanäle: dreifache Datei, dreifacher Arbeitsspeicher in
  jeder Folgestufe, null zusätzliche Information. Jetzt entscheidet die
  Quelle: Modus `L` bleibt `L`. `autocrop` und `descratch` riefen
  `cvtColor(RGB2GRAY)` und wären auf 2D geflogen, beide vertragen jetzt
  beides. Gemessen am gleichen Flachbettbereich: 218 KB statt 653 KB.
- **#8, entfernt statt repariert.** Die Option "Lamp Warm-up" hat vor
  dem Öffnen des Geräts `time.sleep()` gemacht. Zu dem Zeitpunkt ist
  die Lampe nicht bestromt, geheizt hat sie also nichts — dafür stand
  die Oberfläche bis zu 60 Sekunden, weil der Schlaf auf dem Hauptthread
  lag. Reparieren hätte bedeutet, das Gerät offen zu halten; das geht
  nicht, solange jeder Pass ein eigener Prozess ist (siehe #6). Der
  Treiber macht den Warmlauf ohnehin bei jedem `sane_start` selbst, und
  seit v1.3.1 steht er sichtbar in der Statuszeile. Eine Bedienung, die
  eine Fähigkeit verspricht, die sie nicht hat, ist schlechter als
  keine. README entsprechend korrigiert, die Zeile behauptete einen
  "lamp warm-up guard".
- **Nebenher vereinheitlicht:** `MAX_IMAGE_PIXELS` stand an fünf
  Stellen auf 500 Mpx, das Durchlichtfenster bei 4800 dpi hat aber rund
  575 Mpx. Jetzt überall `scan8600.MAX_PIXELS`.

## 2026-08-21 — Verdict: Lampen-Warmlauf, Prozess-Konsolidierung (#6)

- **Verdikt:** NULL (H2: ein Prozess für mehrere Pässe spart den
  Warmlauf), PASS (Ursache der Streuung benannt), PARTIAL (umgesetzt
  wurde, was die Messung hergibt: Probe-Cache und sichtbarer Warmlauf).
- **H2, vorher festgelegt:** In einem scanimage-Prozess zahlt Seite 2
  einen deutlich kürzeren Warmlauf als Seite 1, unter 25 %. PASS hätte
  bedeutet: Batch als ein Prozess bauen.
- **Messung.** Ein Prozess mit drei Seiten: 17 s, 1 s, 1 s. Sieht nach
  PASS aus. Zwei getrennte Prozesse hintereinander: 10 s, 1 s — derselbe
  Effekt ohne Konsolidierung. Und ein Prozess mit zwei Seiten lieferte
  1 s, dann 21 s, also genau andersherum. Die Prozessgrenze erklärt
  nichts; entscheidend ist der zeitliche Abstand zum letzten Scan.
  **H2 verworfen, kein Umbau auf `--batch`.**
- **Warum.** `genesys_warmup_lamp` vergleicht zwei aufeinanderfolgende
  Scans derselben Zeile und bricht ab, sobald die relative Differenz
  unter 0,5 % liegt. Die erste Runde vergleicht immer gegen einen
  Nullpuffer, deshalb sind zwei Durchläufe das Minimum. Die Dauer hängt
  am thermischen Zustand der Lampe, nicht am Prozess. `save_power` und
  `set_powersaving` sind für gl843 leere Funktionen: `--lamp-off-time`
  tut auf dem 8600F nichts, und beim Schließen wird die Lampe nicht
  aktiv abgeschaltet.
- **Auch widerlegt:** die Annahme aus #6, die App zahle den Warmlauf
  2N-mal. Das Sondieren mit `scanimage -A` kostet 0,6 s und löst
  **keinen** Warmlauf aus — der hängt an `sane_start`, nicht am Öffnen.
  Die Zahl der Warmläufe ist die Zahl der echten Scanpässe.
- **Umgesetzt.** Optionen werden einmal pro Prozess und Gerät sondiert
  statt vor jedem Pass (`probe_options`), der Cache wird bei
  Geräte-Refresh verworfen. Der Fortschritt aus scanimage wird bis in
  die Oberfläche gereicht: bestimmter Fortschrittsbalken statt
  Endlos-Spinner, und solange kein Byte da ist, sagt die Statuszeile mit
  laufendem Sekundenzähler, dass der Treiber die Lampe warmfährt und der
  Schlitten deshalb ohne Bild hin und her läuft.
- **Belegt auf Hardware.** Erster Scan 39,5 s, davon 36,7 s vor dem
  ersten Byte. Zweiter Scan direkt hinterher 12,6 s, davon 10,6 s vor
  dem ersten Byte — und ohne Probe-Pass, der Cache greift.
- **Offen.** Die 10-20 s beim ersten Scan nach einer Pause sind
  Treiberverhalten und aus der App heraus nicht wegzubekommen, solange
  jeder Pass ein eigener Prozess ist. Ehrlich benannt statt kaschiert.

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
