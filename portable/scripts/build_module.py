#!/usr/bin/env python3
"""Build a Magisk installer from reviewed sources and *trusted* local Android JARs."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "portable"
MOD = ROOT / "magisk"

def check_jar(path: Path, name: str) -> bytes:
    path = path.expanduser().resolve()
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise SystemExit(f"{name}: expected a real, trusted Java JAR at {path}")
    data = path.read_bytes()
    if not 1024 <= len(data) <= 16 * 1024 * 1024:
        raise SystemExit(f"{name}: unexpected JAR size")
    return data

def insert(zf: zipfile.ZipFile, name: str, raw: bytes, executable=False):
    entry = zipfile.ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = ((0o100755 if executable else 0o100644) << 16)
    entry.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(entry, raw)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--display-jar", type=Path, default=ROOT / "core" / "display-engine.jar", help="Trusted display-engine.jar")
    p.add_argument("--ui-jar", type=Path, default=ROOT / "core" / "ui-v2.jar", help="Trusted ui-v2.jar")
    p.add_argument("--output", type=Path, default=Path(f"codaki-portable-use-{(ROOT / 'VERSION').read_text(encoding='ascii').strip()}-android.zip"))
    args = p.parse_args()
    dj = check_jar(args.display_jar, "display-engine.jar")
    uj = check_jar(args.ui_jar, "ui-v2.jar")
    if not PKG.is_dir():
        p.error("Missing source package")
    dest = args.output.expanduser().resolve()
    if dest.exists():
        p.error(f"Refusing to overwrite existing {dest}")
    dest.parent.mkdir(parents=True,exist_ok=True)
    sources = sorted(PKG.glob("*.py"))
    if not {"__main__.py", "engine.py", "android.py", "legacy_display.py"}.issubset({f.name for f in sources}):
        p.error("Incomplete Python runtime")
    files = ["module.prop", "customize.sh", "service.sh", "stop.sh", "uninstall.sh", "agent.example.json"]
    for name in files:
        if not (MOD / name).is_file():
            p.error(f"Missing Magisk file: {name}")
    with zipfile.ZipFile(dest, "x") as zf:
        for name in files:
            insert(zf, name, (MOD / name).read_bytes(), name.endswith(".sh"))
        insert(zf, "skip_mount", b"")
        for source in sources:
            insert(zf, "runtime/portable/" + source.name, source.read_bytes())
        tools = ROOT / "src" / "shared" / "tools.json"
        if tools.is_file():
            insert(zf, "runtime/shared/tools.json", tools.read_bytes())
        insert(zf, "core/display-engine.jar", dj)
        insert(zf, "core/ui-v2.jar", uj)
    with zipfile.ZipFile(dest) as zf:
        assert zf.testzip() is None
        print(f"ZIP ready: {dest} ({len(zf.namelist())} entries)")
    print("Before installation, back up device data; installing over an existing instance is intentionally blocked.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
