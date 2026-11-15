# CI Runners — WPE WebKit BaseApp

Ryan's rules for runners (`../Arbiter/directives/ci_runners.md`, applied as
Eclipse2-Digital-Edition and Iris-Core apply them), restated here so this
repository stands alone, each with where it lives in `.github/`. Read this
before writing or changing a workflow.

This repository is public, partly so its standard GitHub-hosted runners are
free (Ryan, 2026-11-15; it holds nothing proprietary): 4
CPUs, 16 GB of memory and a 14 GB SSD, x86_64 (`ubuntu-24.04`) and arm64
(`ubuntu-24.04-arm`) (GitHub's runner reference and billing pages, read
2026-11-15). A runner still does only work whose result is wanted, and never
the same work twice: one WebKit build takes hours.

## When a runner runs

| Rule | Here |
|---|---|
| Only where a result is wanted: non-draft pull requests, releases, by hand. Never on a branch push or for documents only | `ci.yml`: `pull_request` (not drafts) and `workflow_dispatch`; its `changes` job builds nothing for a change to documents alone, and `ci-result` reports either way. `release.yml` is the only way a release builds: by hand, from `main` |
| A new commit cancels its pull request's running run | `ci.yml` `concurrency` |
| Serialize only what must be | `release.yml`: the `release` group on the `tag` job only |
| Cheapest first | Both cells are Linux at the same price, so they run side by side; the package check's own tests run before either (`ci.yml` `tests`), since a broken check would pass a broken build |
| Prove it locally first, and check that the local run can fail as the runner would | The manifest's aarch64 build was proven on an Arch Linux ARM machine (Iris-Core's Flatpak, 2026-11-14), where it also failed as a runner would: out of memory at three jobs, a BTI fault, a deleted library. x86_64 cannot be built locally there, so `tests/check_baseapp.py` asserts what matters directly on every build: the library a file and stripped, no BTI on aarch64, no X11, the headers and pkg-config files at RELEASE's version. Its rules are tested on fake folders (`tests/test_check_baseapp.py`) |

## Workflows are modules

| Rule | Here |
|---|---|
| A module (`workflow_call` only) starts with `_`; an entry point does not | `_build.yml` is the module; `ci.yml` and `release.yml` are entry points. Composite actions are modules too: `.github/actions/_cloud` |
| One reusable workflow per build, called per architecture | `_build.yml`, called by `ci.yml` and `release.yml` once per architecture, with what differs as inputs (the cache's access, the bundle's retention) |
| Commands in a script, not YAML | `.github/scripts/baseapp.sh`, one phase a step (`packages`, `cache-restore`, `build`, `cache-save`, `check`, `bundle`); shellcheck-clean, runnable outside a runner |
| Prebuilt over built | The Freedesktop SDK, its LLVM extension and Flathub's `org.flatpak.Builder` come prebuilt; WPE is built here precisely so Iris-Core's builds get it prebuilt |

## Caches

| Rule | Here |
|---|---|
| Shared caches in a bucket, not GitHub's | The compiler cache (ccache, through flatpak-builder) is one archive per architecture in `gs://iris-core-sccache/wpe/`, behind the same workload identity federation as Iris-Core's caches (`_cloud`). Pull requests write only under `pr/`, which `main` and releases never read; only `release.yml` on `main` writes `wpe/` |
| Restore first, save as soon as filled; partial work with `always()` | `_build.yml`: restored before the build; saved right after it under `always()`, after a second sign-in (the first token lasts an hour). The build step's timeout (300 minutes) is shorter than the job's (345), so a build that runs long still saves what it compiled |
| Keys from content | A WPE pin bump changes the sources ccache hashes; ccache itself keys each object by its preprocessed source and flags, so one archive per architecture serves every release |
| Keep what passed, briefly; every upload names its retention | A pull request's bundles: 2 days. A release's: 1 day, until the Release has them |

## Robustness

| Rule | Here |
|---|---|
| Pin what can move | Runner images (`ubuntu-24.04`, `ubuntu-24.04-arm`); actions by commit SHA, updated by Dependabot; `org.flatpak.Builder` by Flathub commit per architecture; WPE, Ruby and libyaml by version and SHA-256 |
| Survive a mirror outage | `baseapp.sh` `apt_install`: one retry through kernel.org's Ubuntu mirror (x86_64; kernel.org has no ubuntu-ports) |
| Bound everything | A timeout on every job and on the build step; `WEBKIT_NINJA_LINK_MAX=1`, one WebKit link at a time in 16 GB; `packages` fails unless 25 GB of disk is free |
| Fail loudly | `check_baseapp.py` before bundling; the bundle must be non-empty and under GitHub's 2 GiB asset limit; `release.yml` checks both architectures and their SHA-256s before it publishes, and refuses a RELEASE already tagged |
