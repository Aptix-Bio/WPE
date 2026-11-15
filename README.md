# WPE WebKit BaseApp

[WPE WebKit](https://wpewebkit.org) with its WPEPlatform, built as the Flatpak
BaseApp `com.aptixbio.WPEWebKit.BaseApp` for x86_64 and aarch64. Iris Slide
Viewer's Linux Flatpak builds on it, so WebKit's hours-long compile happens
here, once per WPE release, instead of in every app build. No Flatpak runtime
carries WPE.

## Releases

Each [Release](../../releases) carries one bundle per architecture,
`com.aptixbio.WPEWebKit.BaseApp-<WPE version>-<build>-<arch>.flatpak`, its SHA-256, and a
build-provenance attestation. To use one:

```bash
flatpak install --user com.aptixbio.WPEWebKit.BaseApp-2.54.2-1-aarch64.flatpak
```

and name it in an app's manifest:

```yaml
base: com.aptixbio.WPEWebKit.BaseApp
base-version: '2.54'
```

The BaseApp keeps WPE's headers and pkg-config files for the app to build
against; the app removes them from what it ships (`cleanup-commands`).

## Building

A release is tagged `v<WPE version>-<build>`, counted, never typed: the version
is the one the manifest pins, and the build number counts that version's tags
(`.github/scripts/release_tag.sh`), so a WPE bump starts at 1 and a rebuild of
the same WPE takes the next. A WPE security release or a change to the build
is a pull request; its CI builds both architectures exactly as the release
will, and `release.yml`, run by hand from `main`, tags the next build, then
builds and publishes it through `_build-release.yml`. How this
repository uses its runners: [development/ci_runners.md](development/ci_runners.md).

Locally, with flatpak-builder and the Flathub remote:

```bash
flatpak-builder --user --install-deps-from=flathub --ccache build com.aptixbio.WPEWebKit.BaseApp.yml
python3 tests/check_baseapp.py build "$(uname -m)" "$(.github/scripts/release_tag.sh version)"
```

WebKit's build needs about 25 GB of disk and several GB of memory per link.

## Licenses

WPE WebKit is LGPL-2.1, with BSD-licensed parts. Each Release is built from the
unmodified source tarball its manifest names, pinned by SHA-256 at the tag.
