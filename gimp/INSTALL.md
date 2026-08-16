# GIMP-Plugin installieren

Das Plugin braucht GIMP 3 und den installierten Treiber-Stack.
macOS: erst die DMG installieren (install.sh). Windows: erst das
Windows-Paket entpacken und SCAN8600_PREFIX auf den prefix-Ordner setzen.

Status: mangels GIMP-Installation auf dem Entwicklungsrechner ungetestet.
Die Options-Logik dahinter ist über Unit-Tests abgedeckt.

## macOS

    PLUGDIR=~/Library/Application\ Support/GIMP/3.0/plug-ins/scan8600_gimp
    mkdir -p "$PLUGDIR"
    cp gimp/scan8600_gimp.py scanoptions.py "$PLUGDIR/"
    chmod +x "$PLUGDIR/scan8600_gimp.py"

GIMP neu starten. Der Eintrag erscheint unter Datei > Erstellen >
CanoScan 8600F.

## Windows 11

1. Ordner anlegen:
   `%APPDATA%\GIMP\3.0\plug-ins\scan8600_gimp\`
2. `gimp\scan8600_gimp.py` und `scanoptions.py` hineinkopieren.
3. Umgebungsvariable `SCAN8600_PREFIX` auf den prefix-Ordner des
   entpackten Windows-Pakets setzen.
4. GIMP neu starten.

## Was das Plugin kann

Standard-Seite: Quelle (Flachbett, Durchlicht, Durchlicht-Infrarot),
Auflösung, Farbe, Kratzerentfernung, Größenerkennung.
Erweitert-Seite: alle übrigen Treiberoptionen, direkt aus dem Treiber
ausgelesen. Was der Treiber kann, zeigt das Plugin an.
