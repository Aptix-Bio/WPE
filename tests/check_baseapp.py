# Copyright (c) 2026 Aptix Bio. All rights reserved.
"""The BaseApp as flatpak-builder left it, checked before it is bundled, so a
build that exits 0 with something wrong in it fails (ci_runners.md: fail
loudly):

    python3 tests/check_baseapp.py <build folder> <x86_64|aarch64> <WPE version>

(the version the manifest pins: .github/scripts/release_tag.sh version)

- its metadata names this BaseApp on the Freedesktop 26.08 runtime of the
  architecture it was built for;
- libWPEWebKit-2.0.so.1 resolves to a file, stripped (a later module's cleanup
  once deleted it and left its links: Iris-Core's Flatpak, 2026-11-14);
- on aarch64 it is not marked for BTI, whose landing pads JavaScriptCore's
  interpreter lacks (SIGILL on its first indirect branch, measured 2026-11-14);
- it and WPEWebProcess need no X11 or XCB library: Iris Slide Viewer is
  Wayland only;
- the headers and pkg-config files the app builds against are there, at the
  version the manifest pins;
- the build-only modules, libyaml and Ruby, left nothing.
"""

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ID = "com.aptixbio.WPEWebKit.BaseApp"
RUNTIME = "org.freedesktop.Platform/{arch}/26.08"
ARCHES = ("x86_64", "aarch64")
LIBRARY = "files/lib/libWPEWebKit-2.0.so.1"
WEB_PROCESS = "files/libexec/wpe-webkit-2.0/WPEWebProcess"
PKG_CONFIG = ("wpe-webkit-2.0", "wpe-platform-2.0")
HEADERS = "files/include/wpe-webkit-2.0"
# Stripped, 2.54.2 is 132 MB on aarch64 (Iris-Core's Flatpak, 2026-11-14) and
# 1.7 GB with its debug information: bounds that hold a release or two of growth.
LIBRARY_BYTES = (40 << 20, 600 << 20)
X11 = re.compile(r"\[(libX11|libxcb|libXext|libGLX)[^]]*\]")
BUILD_ONLY = ("files/bin/ruby", "files/lib/libruby*", "files/lib/libyaml*", "files/include/yaml.h")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")

# readelf, given an option and a binary, returning what it printed.
Readelf = Callable[[str, Path], str]


def readelf_at(program: str) -> Readelf:
    def run(option: str, binary: Path) -> str:
        return subprocess.run([program, option, str(binary)], check=True, capture_output=True, text=True).stdout

    return run


def problems(root: Path, arch: str, version: str, readelf: Readelf) -> list[str]:
    """Everything wrong with the BaseApp in `root`, each a sentence; none when it is whole."""
    found: list[str] = []
    if arch not in ARCHES:
        return [f"architecture '{arch}' is not one of {', '.join(ARCHES)}"]
    if VERSION.match(version) is None:
        return [f"the WPE version is '{version}', not x.y.z, e.g. 2.54.2"]

    metadata = root / "metadata"
    text = metadata.read_text() if metadata.is_file() else ""
    lines = text.splitlines()
    for line in (f"name={ID}", f"runtime={RUNTIME.format(arch=arch)}"):
        if line not in lines:
            key = line.split("=")[0] + "="
            said = [entry for entry in lines if entry.startswith(key)] or ["nothing"]
            found.append(f"{metadata} lacks '{line}'; it says {', '.join(said)}")

    library = root / LIBRARY
    if not library.resolve().is_file():
        found.append(f"{LIBRARY} resolves to no file ({library.resolve()})")
    else:
        size = library.resolve().stat().st_size
        low, high = LIBRARY_BYTES
        if not low <= size <= high:
            found.append(f"{LIBRARY} is {size >> 20} MB, outside {low >> 20} to {high >> 20} MB: unstripped, or not WebKit")
        if arch == "aarch64" and "BTI" in readelf("--notes", library):
            found.append(f"{LIBRARY} is marked for BTI: build it with -mbranch-protection=pac-ret")
        for binary in (library, root / WEB_PROCESS):
            if binary.is_file():
                found.extend(f"{binary.name} needs {name}: Iris Slide Viewer is Wayland only"
                             for name in X11.findall(readelf("--dynamic", binary)))
    if not (root / WEB_PROCESS).is_file():
        found.append(f"{WEB_PROCESS} is missing")

    for name in PKG_CONFIG:
        pc = root / "files/lib/pkgconfig" / f"{name}.pc"
        if not pc.is_file():
            found.append(f"{pc.name} is missing: the app builds against it")
            continue
        versions = re.findall(r"^Version:\s*(\S+)", pc.read_text(), re.MULTILINE)
        if versions != [version]:
            found.append(f"{pc.name} says version {versions}; the manifest pins {version}")
    if not (root / HEADERS).is_dir():
        found.append(f"{HEADERS} is missing: the app builds against it")

    for pattern in BUILD_ONLY:
        found.extend(f"{path.relative_to(root)} is left from a build-only module (ruby, libyaml)"
                     for path in root.glob(pattern))
    return found


def main(arguments: list[str]) -> int:
    if len(arguments) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    root, arch, version = Path(arguments[0]), arguments[1], arguments[2]
    found = problems(root, arch, version, readelf_at("readelf"))
    for problem in found:
        print(f"check_baseapp: {problem}", file=sys.stderr)
    if not found:
        print(f"check_baseapp: {root} is {ID} with WPE {version} for {arch}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
