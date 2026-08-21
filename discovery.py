#!/usr/bin/env python3
"""Scanner discovery and device database for SANE-supported scanners."""
import os
import subprocess
import json
import pathlib
import re
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ScannerDevice:
    """Represents a detected scanner device."""
    name: str
    vendor: str
    model: str
    type: str
    backend: str
    device_file: str
    support_status: str = "untested"
    
    def __str__(self):
        return f"{self.vendor} {self.model} ({self.backend})"
    
    def to_dict(self):
        return {
            "name": self.name,
            "vendor": self.vendor,
            "model": self.model,
            "type": self.type,
            "backend": self.backend,
            "device_file": self.device_file,
            "support_status": self.support_status,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(**data)


@dataclass 
class ScannerOption:
    """Represents a SANE option for a scanner."""
    name: str
    title: str
    desc: str
    type: str  # bool, int, fixed, string, button
    unit: str = ""
    possible_values: List[str] = field(default_factory=list)
    value: str = ""
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    
    def __str__(self):
        if self.possible_values:
            return f"{self.name}: {self.title} ({self.type}, values: {self.possible_values})"
        elif self.min_val is not None and self.max_val is not None:
            return f"{self.name}: {self.title} ({self.type}, range: {self.min_val}-{self.max_val})"
        else:
            return f"{self.name}: {self.title} ({self.type})"


class ScannerDiscovery:
    """Discovers and manages SANE scanners."""
    
    # Path to scanimage executable
    SCANIMAGE = "scanimage"
    
    def __init__(self, scanimage_path: Optional[str] = None):
        # Try to use SCANIMAGE from environment (set by scan8600)
        if scanimage_path:
            self.SCANIMAGE = scanimage_path
        elif os.environ.get("SCANIMAGE"):
            self.SCANIMAGE = os.environ["SCANIMAGE"]
        else:
            # Try to find in PATH
            import shutil
            self.SCANIMAGE = shutil.which("scanimage") or "scanimage"
    
    def list_devices(self) -> List[ScannerDevice]:
        """List all available SANE scanner devices."""
        devices = []
        try:
            # Build environment with SANE_CONFIG_DIR
            env = os.environ.copy()
            # Try to get SANE_CONFIG_DIR from parent or set based on SCANIMAGE path
            if "SANE_CONFIG_DIR" not in env and self.SCANIMAGE != "scanimage":
                # If SCANIMAGE is a path, try to find etc/sane.d relative to it
                scanimage_dir = os.path.dirname(self.SCANIMAGE)
                prefix = os.path.dirname(scanimage_dir)
                sane_dir = os.path.join(prefix, "etc", "sane.d")
                if os.path.exists(sane_dir):
                    env["SANE_CONFIG_DIR"] = sane_dir
            
            result = subprocess.run(
                [self.SCANIMAGE, "-L"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            if result.returncode == 0:
                devices = self._parse_scanimage_list(result.stdout)
        except Exception as e:
            print(f"Error listing devices: {e}")
        return devices
    
    def _parse_scanimage_list(self, output: str) -> List[ScannerDevice]:
        """Parse scanimage -L output to extract device information."""
        devices = []
        
        # Example output:
        # device `hpaio:/usb/DeskJet_2540_series?serial=CN7CH1S1V506BR' is a Hewlett-Packard DeskJet_2540_series all-in-one
        # device `genesys:libusb:001:014' is a Plustek OpticFilm 8200i film scanner
        
        device_pattern = re.compile(
            r"device\s+`([^']+)'\s+is\s+a\s+(.+?)(\s+\(([^)]+)\))?\s*$",
            re.MULTILINE
        )
        
        for match in device_pattern.finditer(output):
            device_file = match.group(1)
            device_desc = match.group(2).strip()
            backend_match = match.group(4)
            
            # Parse device description (e.g., "Hewlett-Packard DeskJet_2540_series")
            # Try to extract vendor and model
            parts = device_desc.split()
            if len(parts) >= 2:
                vendor = parts[0]
                model = " ".join(parts[1:])
            else:
                vendor = "Unknown"
                model = device_desc
            
            # Extract backend from device_file (e.g., "genesys:libusb:001:014" -> "genesys")
            if backend_match:
                backend = backend_match
            else:
                backend = device_file.split(":")[0] if ":" in device_file else "unknown"
            
            # Determine device type
            device_type = "flatbed"
            if "film" in device_desc.lower() or "slide" in device_desc.lower():
                device_type = "film"
            
            # Check support status from device database
            support_status = self._get_support_status(vendor, model, backend)
            
            devices.append(ScannerDevice(
                name=f"{vendor} {model}",
                vendor=vendor,
                model=model,
                type=device_type,
                backend=backend,
                device_file=device_file,
                support_status=support_status,
            ))
        
        return devices
    
    def _get_support_status(self, vendor: str, model: str, backend: str) -> str:
        """Get support status from SANE backend database."""
        # For now, return "untested" for all devices except CanoScan 8600F
        if vendor == "Canon" and "8600F" in model:
            return "complete"
        return "untested"
    
    def get_device_info(self, device_file: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific device."""
        try:
            env = os.environ.copy()
            # Try to get SANE_CONFIG_DIR from parent or set based on SCANIMAGE path
            if "SANE_CONFIG_DIR" not in env and self.SCANIMAGE != "scanimage":
                scanimage_dir = os.path.dirname(self.SCANIMAGE)
                prefix = os.path.dirname(scanimage_dir)
                sane_dir = os.path.join(prefix, "etc", "sane.d")
                if os.path.exists(sane_dir):
                    env["SANE_CONFIG_DIR"] = sane_dir
            
            result = subprocess.run(
                [self.SCANIMAGE, "-A", "-d", device_file],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            if result.returncode == 0:
                info = self._parse_device_info(result.stdout)
                # Rohtext mitgeben: scanoptions.parse ist der getestete
                # Parser, die GUI baut ihre Regler daraus.
                info["raw"] = result.stdout
                return info
        except Exception as e:
            print(f"Error getting device info: {e}")
        return None
    
    def _parse_device_info(self, output: str) -> Dict[str, Any]:
        """Parse scanimage -A output to extract device options."""
        info = {
            "options": {},
            "resolutions": [],
            "sources": [],
            "modes": [],
        }
        
        current_section = None
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # Skip separator lines
            if line.startswith("-" * 20):
                continue
            
            # Check for option sections
            if line.startswith("Main options:"):
                current_section = "main"
                continue
            elif line.startswith("Geometry options:"):
                current_section = "geometry"
                continue
            elif line.startswith("Enhancement options:"):
                current_section = "enhancement"
                continue
            elif line.startswith("Color correction options:"):
                current_section = "color"
                continue
            elif line.startswith("Miscellaneous options:"):
                current_section = "misc"
                continue
            
            # Parse option lines
            # Format: --resolution 100|200|300|600 [100]
            # Format: --mode Color|Gray [Color]
            # Format: --source Flatbed|Transparency [Flatbed]
            option_match = re.match(
                r"(--\w+)\s+(.+?)(?:\s+\[(.+?)\])?\s*$",
                line
            )
            if option_match:
                option_name = option_match.group(1).lstrip("-")
                option_desc = option_match.group(2).strip()
                default_value = option_match.group(3)
                
                # Parse possible values
                possible_values = []
                if "|" in option_desc:
                    possible_values = [v.strip() for v in option_desc.split("|")]
                
                # Create option object
                option = ScannerOption(
                    name=option_name,
                    title=option_name.replace("-", " ").title(),
                    desc=option_desc,
                    type=self._detect_option_type(option_desc),
                    possible_values=possible_values,
                    value=default_value or (possible_values[0] if possible_values else ""),
                )
                
                # Categorize option
                if option_name == "source":
                    info["sources"] = possible_values
                elif option_name == "mode":
                    info["modes"] = possible_values
                elif option_name == "resolution":
                    info["resolutions"] = [int(v) for v in possible_values if v.isdigit()]
                
                info["options"][option_name] = option
        
        return info
    
    def _detect_option_type(self, desc: str) -> str:
        """Detect the type of a SANE option from its description."""
        if "|" in desc:
            return "string"
        if re.search(r"\d+\.\d+\.\d+\.\d+", desc):  # IP address format
            return "string"
        if re.search(r"[\-\d\.]+", desc):
            return "int"
        return "string"
    
    def get_default_device(self) -> Optional[ScannerDevice]:
        """Get the default (first available) scanner device."""
        devices = self.list_devices()
        return devices[0] if devices else None


# Singleton instance
_discovery: Optional[ScannerDiscovery] = None


def get_discovery() -> ScannerDiscovery:
    """Get the global ScannerDiscovery instance."""
    global _discovery
    if _discovery is None:
        # Immer den gebündelten Treiber-Stack nutzen, nicht den PATH.
        # In der installierten App gibt es kein scanimage im PATH.
        import scan8600
        _discovery = ScannerDiscovery(scanimage_path=str(scan8600.SCANIMAGE))
    return _discovery


def list_scanners() -> List[ScannerDevice]:
    """Convenience function to list all available scanners."""
    return get_discovery().list_devices()


def get_default_scanner() -> Optional[ScannerDevice]:
    """Convenience function to get the default scanner."""
    return get_discovery().get_default_device()


if __name__ == "__main__":
    # Test the discovery
    disc = ScannerDiscovery()
    devices = disc.list_devices()
    
    print(f"Found {len(devices)} scanner(s):")
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device}")
        print(f"   Device file: {device.device_file}")
        print(f"   Support: {device.support_status}")
        
        # Get device info
        info = disc.get_device_info(device.device_file)
        if info:
            print(f"   Sources: {info.get('sources', [])}")
            print(f"   Modes: {info.get('modes', [])}")
            print(f"   Resolutions: {info.get('resolutions', [])}")
