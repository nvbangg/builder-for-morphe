# [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe)

<div align="center">
Here you will find a step-by-step technical guide on how to set up your environment, run the patching script, customize the build configuration, and contribute to the project's development.
</div>

## 📦 Setting up environment

1. 📋 **Requirements**:

- [Git](https://git-scm.com/downloads)
- [Python](https://www.python.org/downloads/) (3.13+)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Java](https://adoptium.net/temurin/releases?version=25&os=any&arch=any) (JDK 25+)
> For Termux users, just use: `pkg install git python uv openjdk-25`

2. 📥 **Installation**:

```bash
git clone --depth 1 https://github.com/nvbangg/builder-for-morphe.git
cd builder-for-morphe
```

No further setup needed - `uv` handles the Python environment and dependencies automatically.

3. ▶️ **Running**:

```bash
uv run main.py                    # build all apps
uv run main.py SomeApp            # build a specific app
uv run main.py SomeApp arm64-v8a  # build with arch override
uv run main.py clear              # remove build/, temp/ and build.md
```

Output APKs are saved to `build/`.

## ⚙️ Configuration

All configuration lives in `config.toml` in the project root. Top-level keys define defaults inherited by every app entry. Each app is a TOML table.

```toml
[SomeApp]
apkmirror-dlurl = "https://www.apkmirror.com/apk/inc/app"
# or uptodown-dlurl = "https://app.en.uptodown.com/android"
# or archive-dlurl = "https://archive.org/details/app"
```

1. 📱 **Available options**:

| 🔑 Key | 📝 Description | 🔤 Default |
|:------:|:--------------:|:----------:|
| `parallel-jobs` | Number of concurrent builds | `CPU count` |
| `brand` | Used in output filenames | `Morphe` |
| `patches-version` | Patches version to fetch | `latest` |
| `cli-version` | CLI version to fetch | `latest` |
| `patches-source` | GitHub repo for patches (`owner/repo`) | `MorpheApp/morphe-patches` |
| `cli-source` | GitHub repo for CLI (`owner/repo`) | `MorpheApp/morphe-cli` |
| `app-name` | Display name used in output filename | `table name` |
| `arch` | Target architecture (`all`, `both`, `arm64-v8a`, `arm-v7a`, `x86_64`, `x86`) | `all` |
| `version` | Target version (`auto`, `latest`, or a specific version string) | `auto` |
| `apkmirror-dlurl` | APKMirror page URL | `-` |
| `uptodown-dlurl` | Uptodown page URL | `-` |
| `archive-dlurl` | Archive.org page URL | `-` |
| `included-patches` | Patches to include - names must be single-quoted | `-` |
| `excluded-patches` | Patches to exclude - names must be single-quoted | `-` |
| `exclusive-patches` | Only apply `included-patches`, exclude everything else | `false` |
| `patcher-args` | Extra arguments passed directly to Morphe CLI | `-` |
| `enabled` | Set to `false` to skip this entry | `true` |

> [!NOTE]
> If a patch name contains a single quote, you must wrap the specific patch name in escaped double quotes.  
> Example: `included-patches = "'Example patch' \"Hide 'Example button'\" 'Another example patch'"`

2. ➕ **Adding a new patch source**:

- Add your app entries to `config.toml` with the appropriate `patches-source` and `brand` fields (see the configuration table above for all available options).

3. 🔑 **Keystore**:

To sign APKs with a custom keystore, create a `.env` file in the project root:

```env
KEYSTORE_BASE64=<base64-encoded keystore>
KEYSTORE_PASS=<keystore password>
```

To encode an existing keystore:

```bash
base64 -w 0 my.keystore
```

On **GitHub Actions**, set `KEYSTORE_BASE64` and `KEYSTORE_PASS` as repository secrets under **Settings → Secrets and variables → Actions** instead of a `.env` file - they are passed to the build automatically.

If no keystore is configured, `morphe.keystore` is used as a fallback if it exists in the project root. If neither is present, the CLI signs with its built-in debug keystore - on **GitHub Actions** this means every release will have a different signature, making app updates **impossible**.

## 🤝 Contributing

1. 🐞 **Bug reports**:

For bugs in the **build script itself**, use the [Script Bug Report](https://github.com/nvbangg/builder-for-morphe/issues/new?template=script.yml) template. For bugs in **patched applications**, use the [Build Result Bug Report](https://github.com/nvbangg/builder-for-morphe/issues/new?template=build.yml) template.

2. **💡 Suggestions**:

Feature ideas belong in the [Discussions](https://github.com/nvbangg/builder-for-morphe/discussions) tab - this keeps the issue tracker focused on bugs.

3. **🛠️ Pull Requests**:

Pull requests are welcome. AI-assisted contributions are accepted, but all changes must be manually reviewed before submitting - you are responsible for every line you put your name on. I reserve the right to reject any contribution that does not align with the project's vision.

---

<p align="center"><i>Maintained with ❤️ by <a href="https://github.com/krvstek">krvstek</a> and <a href="https://github.com/nvbangg">nvbangg</a></i></p>
