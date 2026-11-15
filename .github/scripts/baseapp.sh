#!/usr/bin/env bash
# Copyright (c) 2026 Aptix Bio. All rights reserved.
#
# The BaseApp's build for one architecture, a phase per step of
# .github/workflows/_build.yml, so the compiler cache is restored before the
# build and saved right after it (ci_runners.md):
#
#   baseapp.sh <x86_64|aarch64> packages | cache-restore | build | cache-save | check | bundle
#
# cache-restore and cache-save take the cache access, `quarantine` (pull
# requests: read main's, write under pr/) or `write` (release.yml on main), and
# need WPE_GCS_TOKEN (the _cloud action). Runs outside a runner too, from the
# repository's root, with flatpak and flatpak-builder installed (packages is
# the runner's own setup, Ubuntu 24.04's).
set -euo pipefail

arch=${1:?architecture: x86_64 or aarch64} phase=${2:?phase}
case $arch in x86_64|aarch64) ;; *) echo "baseapp.sh: unknown architecture $arch" >&2; exit 2 ;; esac

id=com.aptixbio.WPEWebKit.BaseApp
manifest=$id.yml
release=$(tr -d '[:space:]' < RELEASE)
branch=$(sed -n "s/^branch: '\(.*\)'$/\1/p" "$manifest")
: "${branch:?$manifest names no branch}"
work=${WORK:-$PWD/_work}
state=$work/state builddir=$work/build repo=$work/repo out=$PWD/out
bundle=$out/$id-$release-$arch.flatpak
# Flathub's flatpak-builder, pinned by commit per architecture (flatpak
# remote-info flathub org.flatpak.Builder, both dated 2026-11-04, read 2026-11-15).
declare -A builder_commit=(
    [x86_64]=50461ee00afa8ae6b133762447dcff6348781568ebebaf0293eed8242f79f20a
    [aarch64]=407fe008ab96d6b9e199d01c95523bef08341090be6e300f2717d7858890db57
)
# In a session bus of its own: the builder is sandboxed and installs the SDK
# through D-Bus, and a runner has no session bus ("Cannot autolaunch D-Bus
# without X11 $DISPLAY", the first run, 2026-11-15; reproduced here with
# DBUS_SESSION_BUS_ADDRESS unset, and gone under dbus-run-session).
builder=(dbus-run-session -- flatpak run --user org.flatpak.Builder)
# The compiler cache, one archive per architecture in the build-cache bucket;
# a pull request's under pr/, which main and releases never read and the
# bucket deletes after 7 days (Iris-Core's tools/cloud_federation.sh).
bucket=iris-core-sccache object=wpe/ccache-$arch.tar.zst
# The build tree reached 3.7 GB halfway (measured 2026-11-14), the SDK and its
# LLVM extension add about 3 GB, the cache and the bundle about 3 GB more.
needed_gb=25

# apt with one retry through a mirror outside ubuntu.com, as Eclipse2's
# release_target.sh does after a runner's DNS resolved no *.ubuntu.com host for
# over an hour (2026-11-11). kernel.org carries no ubuntu-ports, so an arm64
# runner's ports.ubuntu.com source stays as it is.
fallback_mirror=http://mirrors.edge.kernel.org/ubuntu/
apt_try() { sudo apt-get update -q && sudo apt-get install -y --no-install-recommends "$@"; }
apt_install() {
    apt_try "$@" && return
    [ "$arch" = x86_64 ] || return 1
    echo "baseapp.sh: apt failed through Ubuntu's mirrors; retrying through $fallback_mirror" >&2
    sudo sed -i -E "s#^URIs: .*#URIs: $fallback_mirror#" /etc/apt/sources.list.d/ubuntu.sources
    apt_try "$@"
}

gcs() {   # method, URL, curl's other arguments...; prints the HTTP status
    local method=$1 url=$2; shift 2
    curl -sS -X "$method" -o "${GCS_OUT:-/dev/null}" -w '%{http_code}' \
        -H "Authorization: Bearer ${WPE_GCS_TOKEN:?the _cloud action signs in first}" "$@" "$url"
}
fetch() {   # object, file: 0 fetched, 1 absent; anything else fails loudly
    local status
    status=$(GCS_OUT=$2 gcs GET "https://storage.googleapis.com/storage/v1/b/$bucket/o/${1//\//%2F}?alt=media")
    case $status in
        200) return 0 ;;
        404) rm -f "$2"; return 1 ;;
        *) echo "baseapp.sh: reading gs://$bucket/$1 returned HTTP $status" >&2; exit 1 ;;
    esac
}
access_prefix() {
    case ${1:?access: quarantine or write} in
        quarantine) echo pr/ ;; write) echo "" ;;
        *) echo "baseapp.sh: access is '$1'; expected quarantine or write" >&2; exit 2 ;;
    esac
}

case $phase in
packages)
    # Room for WebKit: the runner's preinstalled toolchains the build never uses.
    sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL /usr/local/share/boost
    apt_install flatpak dbus-daemon   # dbus-daemon: dbus-run-session, for the builder
    # Ubuntu 24.04 confines unprivileged user namespaces through AppArmor,
    # which flatpak-builder's bubblewrap sandbox needs.
    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install --user --noninteractive flathub org.flatpak.Builder
    flatpak update --user --noninteractive --commit="${builder_commit[$arch]}" org.flatpak.Builder
    free -m
    available=$(df --output=avail -BG "$PWD" | tail -1 | tr -dc 0-9)
    echo "baseapp.sh: ${available} GB free, $(nproc) processors"
    [ "$available" -ge "$needed_gb" ] || { echo "baseapp.sh: ${available} GB free; WebKit needs ${needed_gb} GB" >&2; exit 1; } ;;
cache-restore)
    prefix=$(access_prefix "${3:-}")
    mkdir -p "$state/ccache"
    # main's first, then a pull request's own newer work over it.
    for source in "$object" ${prefix:+"$prefix$object"}; do
        if fetch "$source" "$work/ccache.tar.zst"; then
            tar --zstd -xf "$work/ccache.tar.zst" -C "$state/ccache" && rm "$work/ccache.tar.zst"
            echo "baseapp.sh: restored gs://$bucket/$source"
        else
            echo "baseapp.sh: no gs://$bucket/$source yet"
        fi
    done
    # Bounded, so the archive stays a few GB; WebKit's objects compressed fill about 1 to 2.
    printf 'max_size = 4G\n' > "$state/ccache/ccache.conf" ;;
build)
    "${builder[@]}" --version
    "${builder[@]}" --user --install-deps-from=flathub --ccache --force-clean --disable-rofiles-fuse \
        --state-dir="$state" --repo="$repo" --jobs="$(nproc)" "$builddir" "$manifest" ;;
cache-save)
    prefix=$(access_prefix "${3:-}")
    [ -d "$state/ccache" ] || { echo "baseapp.sh: no compiler cache at $state/ccache" >&2; exit 1; }
    tar --zstd -cf "$work/ccache.tar.zst" -C "$state/ccache" .
    status=$(gcs POST "https://storage.googleapis.com/upload/storage/v1/b/$bucket/o?uploadType=media&name=${prefix//\//%2F}${object//\//%2F}" \
        -H "Content-Type: application/zstd" --data-binary "@$work/ccache.tar.zst")
    [ "$status" = 200 ] || { echo "baseapp.sh: writing gs://$bucket/$prefix$object returned HTTP $status" >&2; exit 1; }
    echo "baseapp.sh: saved gs://$bucket/$prefix$object, $(du -h "$work/ccache.tar.zst" | cut -f1)" ;;
check)
    python3 tests/check_baseapp.py "$builddir" "$arch" RELEASE ;;
bundle)
    mkdir -p "$out"
    flatpak build-bundle --arch="$arch" "$repo" "$bundle" "$id" "$branch"
    # A Release asset is at most 2 GiB (Eclipse2's release_export.sh checks the same).
    size=$(stat -c %s "$bundle")
    [ "$size" -gt 0 ] && [ "$size" -lt $((2 << 30)) ] || { echo "baseapp.sh: $bundle is $size bytes" >&2; exit 1; }
    (cd "$out" && sha256sum "$(basename "$bundle")" > "$(basename "$bundle").sha256")
    ls -l "$out" ;;
*) echo "baseapp.sh: unknown phase $phase (packages, cache-restore, build, cache-save, check, bundle)" >&2; exit 2 ;;
esac
