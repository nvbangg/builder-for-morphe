## [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe)

<div align="center">

[![Typing SVG](https://readme-typing-svg.demolab.com/?font=Google+Sans&size=25&duration=3000&pause=2000&color=&center=true&vCenter=true&random=false&width=550&lines=%F0%9F%93%A6+Build+APKs+from+Morphe+patch+sources)](#-build-your-own-apks)<br>
You can use [this repository](https://github.com/nvbangg/builder-for-morphe) to automatically build patched APKs from [Morphe](https://morphe.software) patch sources on every new update.

</div>

<details>
<summary id="features"><b>🔥 Features</b></summary>

- 🚀 **Easy to use:** easily [build your own APKs](#-build-your-own-apks) just by customizing [`config.toml`](config.toml) (no extra setup required).
- 🧩 **Many pre-configured apps:** just set `enabled = true` for the apps you want.
- 🏗️ **Template support:** use this repository as a [template](https://github.com/new?template_name=builder-for-morphe&template_owner=nvbangg) for private builds or personal development.
- 🔁 **[Automatic upstream sync](CONTRIBUTING.md#-sync-upstream):** pull in bug fixes and new features while still preserving your own configuration.
- 🔄 **Auto-updates:** supports automatic updates through [Obtainium](https://github.com/ImranR98/Obtainium) using releases from your own fork.
- ✨ **And much more!**
</details>

## 🤖 Build Your Own APKs

1. 🍴 `Fork` [this repo](https://github.com/nvbangg/builder-for-morphe) (don't forget to ⭐ `Star` and 👀 `Watch` it)
    - ⚙️ **[Optional]** Customize the apps you want in [`config.toml`](config.toml)
2. 🚀 Run the [CI workflow](../../actions/workflows/ci.yml) (make sure workflows are enabled first)
3. ⬇️ Download your APKs from [Releases](../../releases)

## 📚 Documentation & Contributing

For full configuration reference, setup and contributing guide, see [CONTRIBUTING.md](CONTRIBUTING.md).

For all Morphe resources, patches and community projects, visit [nvbangg/awesome-morphe](https://github.com/nvbangg/awesome-morphe).

---

<div align="center">

**[github.com/nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe)**  
⭐ Star this repo if you find it useful!  
Maintained with ❤️ by **[@nvbangg](https://github.com/nvbangg)** (syncing upstream from [krvstek/uni-apks](https://github.com/krvstek/uni-apks) with the changes mentioned in the [Features](#features) section)

</div>

<details>
<summary><h3>⚖️ License & Copyright</h3></summary>

This project is open-source and distributed under the **[GNU GPLv3](LICENSE)** license. You are free to use, modify, and redistribute this software, but you **must** keep all original and new copyright notices intact.

> **Copyright (C) 2026 [nvbangg](https://github.com/nvbangg)** (for all [modifications](https://github.com/nvbangg/builder-for-morphe/commits/main/?author=nvbangg) by nvbangg in [builder-for-morphe](https://github.com/nvbangg/builder-for-morphe), and those in [contributions](https://github.com/krvstek/uni-apks/commits/main/?author=nvbangg) and [co-authored commits](https://github.com/search?q=repo%3Akrvstek%2Funi-apks+Co-authored-by%3A+nvbangg&type=commits))  
> **Copyright (C) 2026 [krvstek](https://github.com/krvstek)** (for the original [uni-apks](https://github.com/krvstek/uni-apks) codebase)  
> **Authors:** See the list of [Contributors](https://github.com/nvbangg/builder-for-morphe/graphs/contributors) for their source code contributions, and see [icons/README.md](icons/README.md) for asset sources.

</details>

<details>
<summary><h3>⚠️ Disclaimer</h3></summary>

- [This project](https://github.com/nvbangg/builder-for-morphe) is not affiliated with [Morphe](https://morphe.software/) or any authors mentioned here.
- This project is intended for educational and research purposes only, and is not responsible for any issues arising from its use.
- All builds are done using publicly available tools. This repository simply automates the process for convenience.
- This repository does not provide pre-patched APKs. Releases only contain unmodified APKs used for building.
- Everything happens through public GitHub Actions to ensure security and transparency.
</details>
