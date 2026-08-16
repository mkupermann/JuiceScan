# Windows 11 Setup

Status: auf macOS entwickelt und dokumentiert, auf Windows-Hardware
**ungetestet**. Der Weg ist Standard (MSYS2 + libusb + Zadig), aber der
erste Lauf braucht ggf. Nacharbeit.

## Warum so

Canon liefert für den CanoScan 8600F keinen Windows-11-Treiber mehr. Statt
des Canon-Treibers bindet Zadig den generischen **WinUSB**-Treiber an das
Gerät. Darüber spricht libusb den Scanner direkt an, mit demselben
selbst kompilierten genesys-Backend wie auf dem Mac.

## Schritte

1. MSYS2 von https://www.msys2.org installieren, **MINGW64**-Shell öffnen.
2. Repo klonen und bauen:

       git clone <repo-url> canoscan && cd canoscan
       ./build_sane_win.sh

3. Treiber-Bindung: Zadig (https://zadig.akeo.ie) starten →
   Options → List All Devices → "CanoScan" (USB-ID `04A9:2229`) wählen →
   Treiber **WinUSB** installieren.
   Rückgängig machen: Geräte-Manager → Gerät → Treiber deinstallieren.
4. Python ≥3.13 von https://python.org, dann (PowerShell im Repo):

       py -m venv .venv
       .venv\Scripts\pip install pytest pillow numpy opencv-python

5. Scannen:

       .venv\Scripts\python scan8600.py --mode flatbed
       .venv\Scripts\python scan8600.py --mode film --dpi 1200 --descratch

## Bekannte Punkte

- `scan8600.py` findet unter Windows automatisch `prefix/bin/scanimage.exe`.
- Der erste Scan kalibriert und dauert länger. Kalibrierdaten liegen unter
  `%USERPROFILE%/.sane`.
- Falls `scanimage -L` nichts findet: Zadig-Bindung prüfen (WinUSB, richtige
  USB-ID) und Scanner neu einstecken.
