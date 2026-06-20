# patchpile

Automated builds of patched Android apps, published as GitHub releases and served through a small [download site](https://github.com/mahfujarr/patchpile) on top.

Forked from [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe), which does the heavy lifting — this fork just runs it on a schedule and points the output at a static front end.

## What's built

| App | Patch source | Notes |
|---|---|---|
| YouTube | [morphe](https://github.com/MorpheApp/morphe-patches) | No ads, background play, SponsorBlock |
| YT Music | [morphe](https://github.com/MorpheApp/morphe-patches) | Background audio, no ads |
| Google Photos | [de-vanced](https://github.com/RookieEnough/De-Vanced) | Unlimited backup tier, ads stripped |
| Instagram | [piko](https://github.com/crimera/piko) | Ad-free feed, story/reel downloads |

All builds are `arm64-v8a` only. Each app patches against a different upstream source, so they ship as separate GitHub releases rather than one combined build.

## Getting the APKs

Grab them from the [Releases](https://github.com/mahfujarr/patchpile/releases) page, or use the download site, which pulls the latest version and file size live from the GitHub API on load instead of hardcoding them.

Most of these patched apps need [MicroG-RE](https://github.com/MorpheApp/MicroG-RE/releases) installed alongside them for Google sign-in to work.

## How it works

This repo doesn't contain a patcher — it's a thin CI wrapper:

1. `config.toml` lists which apps to build and which patch source to use for each
2. A GitHub Actions workflow ([`ci.yml`](.github/workflows/ci.yml)) runs the upstream Python CLI (`MorpheApp/morphe-cli`) against that config
3. The CLI downloads the original APK, applies the patches, signs it, and the workflow uploads the result as a release asset

Build status and logs live under [Actions](https://github.com/mahfujarr/patchpile/actions).

## Building your own

For maximum trust, don't take pre-built APKs from anyone — build your own:

1. Fork [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe) (star + watch it if you find it useful)
2. Edit `config.toml` to pick which apps/patches you want — see [`CONTRIBUTING.md`](CONTRIBUTING.md)
3. Run the CI workflow under the Actions tab (enable workflows first if it's your first run)
4. Download the output from your fork's own Releases page

## Disclaimer

- Not affiliated with Google, Meta, Instagram, or any of the patch creators listed above.
- Builds run entirely through public GitHub Actions for transparency — nothing is built or signed outside that pipeline.
- For personal and educational use. If a build breaks after an upstream app update, it's a patch-source issue, not something this fork controls — check the linked patch repos above for status.
- Source license: GPL-3.0, inherited from upstream.

## Credits

- [krvstek/uni-apks](https://github.com/krvstek/uni-apks) — original base
- [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe) — the fork this repo builds on, maintained by [krvstek](https://github.com/krvstek) and [nvbangg](https://github.com/nvbangg)
- [j-hc](https://github.com/j-hc) — original build script foundation
- [MorpheApp](https://github.com/MorpheApp), [RookieEnough](https://github.com/RookieEnough), [crimera](https://github.com/crimera) — patch sources used above
