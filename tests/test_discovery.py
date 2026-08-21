import pytest
import scan8600

OPTIONS = """
    --source Flatbed|Transparency Adapter [Flatbed]
        Selects the scan source
"""


def test_find_film_source():
    assert scan8600.find_film_source(OPTIONS) == "Transparency Adapter"


def test_find_film_source_missing():
    assert scan8600.find_film_source("--source Flatbed [Flatbed]") is None


def test_run_scan_missing_driver_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(scan8600, "SCANIMAGE",
                        tmp_path / "nope" / "scanimage")
    # Mit --output landet auch das Messlog in tmp_path statt im Repo.
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    with pytest.raises(scan8600.ScanError, match="Install the pkg"):
        scan8600.run_scan(a)


def test_run_scan_device_not_found(monkeypatch, tmp_path):
    def fake_run(cmd, **kw):
        class R:
            returncode = 1
            stderr = b"no SANE devices found"
            stdout = b""
        return R()
    monkeypatch.setattr(scan8600.subprocess, "run", fake_run)
    a = scan8600.parse_args(
        ["--mode", "flatbed", "--output", str(tmp_path / "x.tiff")])
    with pytest.raises(scan8600.ScanError, match="not found"):
        scan8600.run_scan(a)
