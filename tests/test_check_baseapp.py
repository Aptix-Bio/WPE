# Copyright (c) 2026 Aptix Bio. All rights reserved.
"""tests/check_baseapp.py's rules, on fake BaseApp folders, so they are checked
without a WebKit build: `python3 -m unittest discover -s tests`."""

import tempfile
import unittest
from pathlib import Path

import check_baseapp as check

# readelf -n's line for an aarch64 library, as LLVM 23 and binutils 2.46 print
# them (measured 2026-11-15: clang -mbranch-protection=standard, then pac-ret).
NOTES_STANDARD = "      Properties: AArch64 feature: BTI, PAC, GCS\n"
NOTES_PAC_RET = "      Properties: AArch64 feature: PAC\n"
DYNAMIC = (
    " 0x0000000000000001 (NEEDED)             Shared library: [libglib-2.0.so.0]\n"
    " 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]\n"
)
MEGABYTE = 1 << 20


def fake_readelf(notes: str = NOTES_PAC_RET, dynamic: str = DYNAMIC) -> check.Readelf:
    def run(option: str, _binary: Path) -> str:
        return notes if option == "--notes" else dynamic

    return run


def baseapp(root: Path, arch: str = "aarch64", version: str = "2.54.2", library_bytes: int = 130 * MEGABYTE) -> Path:
    """A BaseApp folder as flatpak-builder leaves it, every rule satisfied."""
    (root / "metadata").write_text(
        "[Application]\nname=com.aptixbio.WPEWebKit.BaseApp\n"
        f"runtime=org.freedesktop.Platform/{arch}/26.08\nsdk=org.freedesktop.Sdk/{arch}/26.08\n"
    )
    lib = root / "files/lib"
    (lib / "pkgconfig").mkdir(parents=True)
    with open(lib / "libWPEWebKit-2.0.so.1.11.5", "wb") as library:
        library.truncate(library_bytes)
    (lib / "libWPEWebKit-2.0.so.1").symlink_to("libWPEWebKit-2.0.so.1.11.5")
    for name in ("wpe-webkit-2.0", "wpe-platform-2.0"):
        (lib / "pkgconfig" / f"{name}.pc").write_text(f"Name: {name}\nVersion: {version}\n")
    (root / "files/include/wpe-webkit-2.0").mkdir(parents=True)
    (root / "files/libexec/wpe-webkit-2.0").mkdir(parents=True)
    (root / "files/libexec/wpe-webkit-2.0/WPEWebProcess").write_text("")
    return root


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self) -> None:
        self.folder.cleanup()

    def problems(self, arch: str = "aarch64", version: str = "2.54.2", readelf: check.Readelf | None = None) -> list[str]:
        return check.problems(self.root, arch, version, readelf or fake_readelf())

    def test_a_good_baseapp_passes(self) -> None:
        baseapp(self.root)
        self.assertEqual(self.problems(), [])

    def test_an_aarch64_library_marked_for_bti_fails(self) -> None:
        # JavaScriptCore's interpreter has no BTI landing pads: a BTI library faults (SIGILL).
        baseapp(self.root)
        self.assertTrue(any("BTI" in p for p in self.problems(readelf=fake_readelf(notes=NOTES_STANDARD))))

    def test_bti_is_not_asked_of_x86_64(self) -> None:
        baseapp(self.root, arch="x86_64")
        self.assertEqual(self.problems(arch="x86_64", readelf=fake_readelf(notes="")), [])

    def test_an_x11_library_fails(self) -> None:
        baseapp(self.root)
        dynamic = DYNAMIC + " 0x0000000000000001 (NEEDED)             Shared library: [libX11.so.6]\n"
        self.assertTrue(any("libX11" in p for p in self.problems(readelf=fake_readelf(dynamic=dynamic))))

    def test_a_dangling_library_fails(self) -> None:
        # Iris-Core's Flatpak, 2026-11-14: a later module's cleanup deleted the library, its links left.
        baseapp(self.root)
        (self.root / "files/lib/libWPEWebKit-2.0.so.1.11.5").unlink()
        self.assertTrue(any("libWPEWebKit-2.0.so.1" in p for p in self.problems()))

    def test_an_unstripped_library_fails(self) -> None:
        baseapp(self.root, library_bytes=1700 * MEGABYTE)
        self.assertTrue(any("MB" in p for p in self.problems()))

    def test_missing_headers_or_pkg_config_fail(self) -> None:
        baseapp(self.root)
        (self.root / "files/lib/pkgconfig/wpe-platform-2.0.pc").unlink()
        (self.root / "files/include/wpe-webkit-2.0").rmdir()
        found = self.problems()
        self.assertTrue(any("wpe-platform-2.0.pc" in p for p in found))
        self.assertTrue(any("include" in p for p in found))

    def test_a_version_other_than_the_pinned_one_fails(self) -> None:
        baseapp(self.root, version="2.54.1")
        self.assertTrue(any("2.54.1" in p for p in self.problems()))

    def test_the_wrong_architecture_fails(self) -> None:
        baseapp(self.root, arch="x86_64")
        self.assertTrue(any("x86_64" in p for p in self.problems(arch="aarch64")))

    def test_build_tools_left_behind_fail(self) -> None:
        baseapp(self.root)
        (self.root / "files/bin").mkdir()
        (self.root / "files/bin/ruby").write_text("")
        self.assertTrue(any("ruby" in p for p in self.problems()))

    def test_a_version_that_is_not_x_y_z_fails(self) -> None:
        baseapp(self.root)
        self.assertTrue(any("x.y.z" in p for p in self.problems(version="2.54.2-1")))


if __name__ == "__main__":
    unittest.main()
