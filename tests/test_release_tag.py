# Copyright (c) 2026 Aptix Bio. All rights reserved.
""".github/scripts/release_tag.sh, run in a scratch repository: the WPE version
read from the manifest's pinned tarball, and the next release tag counted from
the tags already made (run as python3 -m unittest discover -s tests)."""

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github/scripts/release_tag.sh"
MANIFEST = "com.aptixbio.WPEWebKit.BaseApp.yml"


def manifest(branch: str = "2.54", version: str = "2.54.2") -> str:
    return (f"id: com.aptixbio.WPEWebKit.BaseApp\nbranch: '{branch}'\nmodules:\n  - name: wpewebkit\n    sources:\n"
            f"      - type: archive\n        url: https://wpewebkit.org/releases/wpewebkit-{version}.tar.xz\n")


class ReleaseTag(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.git("init", "-q")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "first")
        self.write()

    def tearDown(self) -> None:
        self.scratch.cleanup()

    def git(self, *arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=self.root, check=True)

    def write(self, **fields: str) -> None:
        (self.root / MANIFEST).write_text(manifest(**fields))

    def tag(self, *names: str) -> None:
        for name in names:
            self.git("tag", name)

    def run_script(self, mode: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), mode], cwd=self.root, capture_output=True, text=True)

    def test_the_version_is_the_pinned_tarballs(self) -> None:
        self.assertEqual(self.run_script("version").stdout.strip(), "2.54.2")

    def test_the_first_build_of_a_version_is_1(self) -> None:
        self.tag("v2.54.1-4")
        self.assertEqual(self.run_script("next").stdout.strip(), "v2.54.2-1")

    def test_the_next_build_counts_from_the_highest_of_that_version(self) -> None:
        self.tag("v2.54.2-1", "v2.54.2-3", "v2.54.1-9", "v2.54.2-x", "v2.54.20-7")
        self.assertEqual(self.run_script("next").stdout.strip(), "v2.54.2-4")

    def test_a_branch_other_than_the_versions_line_fails(self) -> None:
        self.write(branch="2.52")
        result = self.run_script("next")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("2.52", result.stderr)

    def test_a_manifest_with_no_pinned_tarball_fails(self) -> None:
        (self.root / MANIFEST).write_text("id: com.aptixbio.WPEWebKit.BaseApp\nbranch: '2.54'\n")
        result = self.run_script("version")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wpewebkit", result.stderr)

    def test_an_unknown_mode_fails(self) -> None:
        self.assertEqual(self.run_script("release").returncode, 2)


if __name__ == "__main__":
    unittest.main()
