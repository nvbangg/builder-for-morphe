## [nvbangg/builder-for-morphe](https://github.com/nvbangg/builder-for-morphe)

<div align="center">
Here you will find a step-by-step technical guide on how to set up your environment, run the patching script, customize the build configuration, and contribute to the project's development.
</div>

## 🔄 Sync Upstream

The [Sync upstream workflow](../../actions/workflows/sync.yml) keeps your fork up to date with the upstream repository to pull in bug fixes and new features while preserving your own configuration. It merges new commits automatically or opens a Pull Request if there are unresolvable conflicts.

**[Optional]** You can customize the sync behavior by adding the following variables and secrets to your repository:

| Name | Type | Description | Default |
|:---:|:---:|:---:|:---:|
| `IGNORE_SYNC_FILES` | [Variable](../../settings/variables/actions) | Space-separated list of file paths to preserve during sync. Example: `None` to sync everything; `config.toml sig.txt .github/workflows` to not sync workflow changes. | `config.toml sig.txt` |
| `UPSTREAM_URL` | [Variable](../../settings/variables/actions) | Overrides the upstream repository URL. | *Auto-detects fork parent* |
| `PAT_TOKEN` | [Secret](../../settings/secrets/actions) | Enables automatic syncing of changes in `.github/workflows/`. | *None* |

<details>
<summary>How to create and add the <code>PAT_TOKEN</code></summary>

By default, GitHub does not allow syncing changes in workflows, and you will have to `Sync fork` manually. If you still want to automatically sync these changes, you need to follow these steps:

1. Go to [**Fine-grained personal access tokens**](https://github.com/settings/personal-access-tokens) and click `Generate new token`.
2. Set **Token name** to `PAT_TOKEN`, set an appropriate **Expiration**, and under **Repository access**, select **Only select repositories** and choose your fork.
3. Grant these **Permissions**: `Contents` (Read and write), `Pull requests` (Read and write), `Workflows` (Read and write).
4. Click `Generate token` and copy the token value immediately.
5. In your fork, go to **Settings** → **Secrets and variables** → **Actions** → [**Secrets**](../../settings/secrets/actions) tab.
6. Click `New repository secret`, name it `PAT_TOKEN`, paste the token, and click `Add secret`.
</details>

---

## 💻 Build Locally

1. 📋 **Requirements**:

- [Git](https://git-scm.com/downloads)
- [Python](https://www.python.org/downloads/latest/python3.13)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Java](https://adoptium.net/temurin/releases?version=21&os=any&arch=any)

2. 📥 **Installation**:

```bash
git clone --depth 1 https://github.com/nvbangg/builder-for-morphe.git
cd builder-for-morphe
```

No further setup needed, as `uv` handles the Python environment and dependencies automatically.

3. ▶️ **Running**:

```bash
uv run main.py # build all apps
uv run main.py SomeApp # build a specific app
uv run main.py SomeApp arm64-v8a # build with arch override
uv run main.py clear # remove build/, temp/ and build.md
```

Output APKs are saved to `build/`.

## ⚙️ Configuration

All configuration lives in `config.toml` in the project root. Top-level keys define defaults inherited by every app entry. Each app is a TOML table.

```toml
[SomeApp]
apkmirror-dlurl = "https://www.apkmirror.com/apk/inc/app"
# uptodown-dlurl = "https://app.en.uptodown.com/android"
# github-dlurl = "https://github.com/owner/repo/releases/tag/app"

[SomeApp.patches]
# Simple form - fetches latest version, applies listed patches
"github:owner/some-patches" = ["Patch name A", "Patch name B"]

# Full form - pin a specific version and/or list patches to include
"github:owner/some-other-patches" = { version = "v1.2.3", include = ["Patch name C"] }
```

1. 📱 **Available options**:

| 🔑 Key | 📝 Description | 🔤 Default | 📌 Scope |
|:------:|:--------------:|:----------:|:--------:|
| `parallel-jobs` | Number of concurrent builds | `CPU count` | Global |
| `brand` | Used in output filenames | `Morphe` | Global / Per-app |
| `cli-version` | CLI version to fetch (`latest`, `dev`, or a specific version string) | `latest` | Global / Per-app |
| `cli-source` | GitHub or GitLab repo for CLI (`github:owner/repo` or `gitlab:owner/repo`) | `github:MorpheApp/morphe-cli` | Global / Per-app |
| `strict-sigcheck` | Fail the build if an app is missing from `sig.txt` (see note below) | `true` | **Global only** |
| `app-name` | Display name used in output filename | `table name` | Per-app |
| `arch` | Target architecture (`all`, `both`, `arm64-v8a`, `armeabi-v7a`, `x86_64`, `x86`) | `all` | Per-app |
| `version` | Target version (`auto`, `latest`, or a specific version string) | `auto` | Per-app |
| `changelog-keywords` | List of keywords used to detect if this app was updated in the release notes | `[]` | Per-app |
| `apkmirror-dlurl` | APKMirror page URL | `-` | Per-app |
| `uptodown-dlurl` | Uptodown page URL | `-` | Per-app |
| `github-dlurl` | GitHub Releases page URL | `-` | Per-app |
| `exclusive-patches` | Only apply patches listed in `[AppName.patches]`, exclude everything else | `false` | Per-app |
| `patcher-args` | Extra arguments passed directly to Morphe CLI | `-` | Per-app |
| `skip-sigcheck` | Completely bypasses signature checks for this app (see note below) | `false` | **Per-app only** |
| `enabled` | Set to `false` to skip this entry | `true` | Per-app |

**`[AppName.patches]` table** - defines which patch bundles to use and which patches to apply from each:

| Field | Description | Default |
|:-----:|:-----------:|:-------:|
| key | Patch source (`github:owner/repo` or `gitlab:owner/repo`) | - |
| `version` | Version to fetch (`latest`, `dev`, or a specific tag) | `latest` |
| `include` | List of patch names to apply from this source. Empty list applies all patches | `[]` |
| `exclude` | List of patch names to explicitly disable from this source | `[]` |

Each patch source is fetched exactly once and reused across all apps that reference the same `(source, version)` pair.

2. 🔏 **Signature verification flags**:

The build system includes two independent flags for controlling APK signature verification.

* `strict-sigcheck` **(Global root level only | Default: `true`)**  
Controls the strict requirement for `sig.txt`:
> - When set to `false`, the build will not fail if an app is missing from `sig.txt` (useful for forks and local testing). If a signature entry does exist, it is still verified normally.

* `skip-sigcheck` **(Per-app [AppName] level only | Default: `false`)**  
Acts as a total bypass of signature verification for one specific app.
> - When set to `true`, the build completely ignores `sig.txt` and native APK certificate checks for that app. Use this only for pre-modified APKs (e.g. with PairIP removed) where the original certificate is gone.


**How to add a signature entry to `sig.txt`** (only needed when `skip-sigcheck` is `false`):

> * **Method 1 (Quick):** Copy the original SHA-256 fingerprint directly from a trusted source like **APKMirror** (listed on every APK download page).
> * **Method 2 (Manual):** Use the provided toolchain on the original, unmodified APK: `java -jar apksigner.jar verify --print-certs <app.apk>`
> 
> Format for `sig.txt`: `<sha256-fingerprint>  <package.name>`

3. 🤖 **Smart Build**:

When `changelog-keywords` are defined for an application, the CI will only build that app if its keywords are found in the upstream patch release notes.

* `changelog-keywords` **(Per-app level only | Default: `[]`)**  
A list of keyword strings to search for in the release notes. If not specified, the app will always be built regardless of changelog content.

4. ➕ **Adding a new patch source**:

- Add your app entries to `config.toml` with a `[AppName.patches]` table pointing to your patch repo, and set `brand` accordingly (see the configuration table above for all available options).

5. 🔑 **Keystore**:

To sign APKs with a custom keystore, create a `.env` file in the project root:

```env
KEYSTORE_BASE64=<base64-encoded keystore>
KEYSTORE_PASS=<keystore password>
KEYSTORE_ALIAS=<keystore alias>
```

To encode an existing keystore:

```bash
base64 -w 0 my.keystore
```

On **GitHub Actions**, set `KEYSTORE_BASE64`, `KEYSTORE_PASS` and `KEYSTORE_ALIAS` as repository secrets under **Settings → Secrets and variables → Actions** instead of a `.env` file, as they are passed to the build automatically.

If no keystore is configured, `morphe.keystore` is used as a fallback if it exists in the project root. If neither is present, the CLI signs with its built-in debug keystore. On **GitHub Actions** this means every release will have a different signature, making app updates **impossible**.

## 🤝 Contributing

1. 🐞 **Bug reports**:

For bugs in the **build script itself**, use the [Script Bug Report](https://github.com/krvstek/uni-apks/issues/new?template=script.yml) template. For bugs in **patched applications**, use the [Build Result Bug Report](https://github.com/krvstek/uni-apks/issues/new?template=build.yml) template.

2. **💡 Suggestions**:

Feature ideas belong in the [Discussions](https://github.com/krvstek/uni-apks/discussions) tab, as this keeps the issue tracker focused on bugs.

3. **🛠️ Pull Requests**:

Pull requests are welcome. AI-assisted contributions are accepted, but all changes must be manually reviewed before submitting, as you are responsible for every line you put your name on. I reserve the right to reject any contribution that does not align with the project's vision.

---

<p align="center"><i>Maintained with ❤️ by <a href="https://github.com/krvstek">krvstek</a> and <a href="https://github.com/nvbangg">nvbangg</a></i></p>
