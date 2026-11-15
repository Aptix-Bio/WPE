#!/usr/bin/env bash
# Copyright (c) 2026 Aptix Bio. All rights reserved.
#
# The release's name, counted, never written by hand (Eclipse2's
# tools/next_release_tag.sh, after Ryan's "We'll want auto-tagging",
# 2026-11-15). The WPE version is the one the manifest pins
# (wpewebkit-<version>.tar.xz), and the build number counts the tags
# v<version>-<n> already made: a WPE bump starts at 1, a rebuild of the same
# WPE (a new runtime, a changed option) takes the next. Run from the
# repository's root, after `git fetch --tags`:
#
#   release_tag.sh version   ->  2.54.2
#   release_tag.sh next      ->  v2.54.2-2   (after v2.54.2-1)
set -euo pipefail

manifest=com.aptixbio.WPEWebKit.BaseApp.yml
version=$(sed -n 's#^ *url: https://wpewebkit.org/releases/wpewebkit-\([0-9]*\.[0-9]*\.[0-9]*\)\.tar\.xz$#\1#p' "$manifest")
[ -n "$version" ] || { echo "release_tag.sh: $manifest pins no wpewebkit-<x.y.z>.tar.xz from wpewebkit.org" >&2; exit 1; }
# The BaseApp's branch is the version's line, which the app's base-version names.
branch=$(sed -n "s/^branch: '\(.*\)'$/\1/p" "$manifest")
[ "$branch" = "${version%.*}" ] || { echo "release_tag.sh: $manifest's branch is '$branch'; WPE $version's line is ${version%.*}" >&2; exit 1; }

case ${1:-} in
version)
    echo "$version" ;;
next)
    highest=$(git tag -l "v$version-*" | awk -v prefix="v$version-" '
        BEGIN { highest = 0 }
        index($0, prefix) == 1 {
            n = substr($0, length(prefix) + 1)
            if (n ~ /^[0-9]+$/ && n + 0 > highest) highest = n + 0
        }
        END { print highest }')
    echo "v$version-$((highest + 1))" ;;
*)
    echo "release_tag.sh: version | next" >&2; exit 2 ;;
esac
