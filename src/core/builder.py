import base64
import os
import shutil
import tempfile
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from src.core.config import BUILD_DIR, TEMP_DIR, AppEntry, Config
from src.core.logger import epr, pr, wpr
from src.core.network import NetworkError, NetworkManager
from src.core.patcher import PatcherCLI, PatcherError, SignatureError
from src.core.prebuilts import APKSIGNER, Prebuilts, fetch_prebuilts, get_highest_ver
from src.scrapers.base import BaseScraper, DownloadResult, ScraperError


class BuilderError(Exception):
    pass

def _make_scraper(source: str, net: NetworkManager) -> BaseScraper:
    from src.scrapers.apkmirror import APKMirrorScraper
    from src.scrapers.github import GitHubScraper
    from src.scrapers.uptodown import UptodownScraper
    match source:
        case "apkmirror":
            return APKMirrorScraper(net)
        case "github":
            return GitHubScraper(net)
        case "uptodown":
            return UptodownScraper(net)
        case _:
            raise ValueError(f"Unknown APK source: {source!r}")

def _find_pkg_name(entry: AppEntry, scrapers: dict[str, BaseScraper]) -> tuple[str, str]:
    for src, url in entry.dl_urls.items():
        try:
            metadata = scrapers[src].cached_metadata(url)
            pr(f"Package name of '{entry.table}' is '{metadata.pkg_name}'")
            return metadata.pkg_name, src
        except (NetworkError, ScraperError) as exc:
            epr(f"Could not find '{entry.table}' in '{src}': {exc}")

    raise BuilderError("Package name not found")

def _resolve_version(entry: AppEntry, patcher: PatcherCLI, list_patches: str, pkg_name: str, dl_from: str, scrapers: dict[str, BaseScraper]) -> tuple[str, bool]:
    if entry.version not in ("auto", "latest"):
        pr(f"Choosing version '{entry.version}' for '{entry.table}'")
        return entry.version, True

    if entry.version == "auto" and (v := patcher.get_last_supported_version(list_patches, pkg_name, entry.included_patches)):
        pr(f"Choosing version '{v}' for '{entry.table}'")
        return v, False

    versions = scrapers[dl_from].cached_metadata(entry.dl_urls[dl_from]).versions
    version = get_highest_ver(versions) if versions else ""
    if not version:
        raise BuilderError("Could not determine version")

    pr(f"Choosing version '{version}' for '{entry.table}'")
    return version, entry.version != "auto"

def _download_apk(entry: AppEntry, version: str, arch: str, pkg_name: str, scrapers: dict[str, BaseScraper]) -> DownloadResult:
    arch_f = arch.replace(" ", "")
    version_f = version.replace(" ", "").lstrip("v")
    base_name = f"{pkg_name}-{version_f}-{arch_f}.apk"
    stock_apk = TEMP_DIR / base_name
    if stock_apk.exists():
        return DownloadResult(path=stock_apk, is_bundle=False)

    stock_apkm = TEMP_DIR / f"{base_name}.apkm"
    if stock_apkm.exists():
        return DownloadResult(path=stock_apkm, is_bundle=True)

    for src, url in entry.dl_urls.items():
        pr(f"Downloading '{entry.table}' from '{src}'")
        try:
            return scrapers[src].download(url, version, stock_apk, arch, entry.dpi)
        except (NetworkError, ScraperError) as exc:
            epr(f"Failed to fetch '{entry.table}' from '{src}' (version='{version}', arch='{arch}'): {exc}")

    raise BuilderError("Stock APK not found")

def _extract_base_apk(apkm: Path, pkg_name: str, dest_dir: Path) -> Path:
    with zipfile.ZipFile(apkm, "r") as zf:
        for name in ("base.apk", f"{pkg_name}.apk"):
            if name in zf.namelist():
                zf.extract(name, dest_dir)
                return dest_dir / name

    raise BuilderError(f"Neither 'base.apk' nor '{pkg_name}.apk' found inside {apkm.name}")

def _verify_sig(dl_result: DownloadResult, pkg_name: str, patcher: PatcherCLI, table: str, skip_sigcheck: bool, strict_sigcheck: bool) -> None:
    if skip_sigcheck:
        wpr(f"Skipping APK signature verification for '{table}'")
        return

    if not patcher.has_signature(pkg_name):
        msg = f"No signature entry found in sig.txt for '{pkg_name}'"
        if strict_sigcheck:
            raise SignatureError(msg)
        wpr(f"{msg}, skipping it")
        return

    if not dl_result.is_bundle:
        if not patcher.check_signature(dl_result.path, pkg_name):
            raise SignatureError("APK signature mismatch")
        return

    with tempfile.TemporaryDirectory(dir=TEMP_DIR) as tmp_dir:
        apk_path = _extract_base_apk(dl_result.path, pkg_name, Path(tmp_dir))
        if not patcher.check_signature(apk_path, pkg_name):
            raise SignatureError("Bundle APK signature mismatch")

def _apply_patch(entry: AppEntry, arch: str, version: str, force: bool, patcher: PatcherCLI, list_patches: str, dl_result: DownloadResult) -> Path:
    arch_f = arch.replace(" ", "")
    version_f = version.replace(" ", "").lstrip("v")
    auto_patches = patcher.resolve_auto_patches(list_patches)
    final_args = patcher.build_patch_args(included_patches=entry.included_patches, excluded_patches=entry.excluded_patches, exclusive=entry.exclusive_patches, extra_args=entry.patcher_args, arch=arch, auto_patches=auto_patches, force=force)
    base_name = f"{entry.app_name.lower().replace(" ", "-")}-{entry.brand.lower().replace(" ", "-")}"
    patched_apk = TEMP_DIR / f"{base_name}-{version_f}-{arch_f}.apk"

    pr(f"Building '{entry.table}'")
    patcher.patch(dl_result.path, patched_apk, final_args)
    apk_output = BUILD_DIR / f"{base_name}-v{version_f}-{arch_f}.apk"
    shutil.move(patched_apk, apk_output)
    return apk_output

def _build_single(entry: AppEntry, arch: str, label: str, net: NetworkManager, patcher: PatcherCLI, strict_sigcheck: bool) -> str | None:
    try:
        scrapers = {src: _make_scraper(src, net) for src in entry.dl_urls}
        pkg_name, dl_from = _find_pkg_name(entry, scrapers)
        list_patches = patcher.list_patches(pkg_name)
        version, force = _resolve_version(entry, patcher, list_patches, pkg_name, dl_from, scrapers)
        dl_result = _download_apk(entry, version, arch, pkg_name, scrapers)
        _verify_sig(dl_result, pkg_name, patcher, label, entry.skip_sigcheck, strict_sigcheck)
        apk_output = _apply_patch(entry, arch, version, force, patcher, list_patches, dl_result)
        pr(f"Built {label}: '{apk_output}'")
        if os.getenv("GITHUB_ACTIONS") == "true":
            return f"- 🟢 » {label}: [`{version}`](../../releases/download/{{TAG}}/{apk_output.name})"
        return f"- 🟢 » {label}: `{version}`"
    except (BuilderError, PatcherError, ScraperError, NetworkError) as exc:
        epr(f"Building '{label}' failed! {exc}")
        return None

def _submit_entries(entries: list[AppEntry], pool: ThreadPoolExecutor, net: NetworkManager, ks_path: Path | None, strict_sigcheck: bool) -> list[Future[str | None]]:
    futures: list[Future[str | None]] = []
    build_cache: dict[tuple[str, str, str, str], tuple[Prebuilts, PatcherCLI]] = {}
    for entry in entries:
        if not entry.dl_from:
            epr(f"No 'dlurl' option was set for '{entry.table}'")
            continue

        key = (entry.cli_source, entry.cli_version, entry.patches_source, entry.patches_version)
        if key not in build_cache:
            try:
                prebuilts = fetch_prebuilts(cli_src=entry.cli_source, cli_ver=entry.cli_version, patches_src=entry.patches_source, patches_ver=entry.patches_version, net=net)
                build_cache[key] = (prebuilts, PatcherCLI(prebuilts.cli_jar, prebuilts.patches_mpp, APKSIGNER, ks_path=ks_path))
            except Exception as exc:
                epr(f"Could not get prebuilts for '{entry.table}': {exc}")
                continue

        _, patcher = build_cache[key]
        arches = ("arm64-v8a", "armeabi-v7a") if entry.arch == "both" else (entry.arch,)
        for arch in arches:
            label = entry.table if entry.arch == "all" else f"{entry.table} ({arch})"
            futures.append(pool.submit(_build_single, entry, arch, label, net, patcher, strict_sigcheck))

    return futures

def run_build(entries: list[AppEntry], config: Config, net: NetworkManager) -> bool:
    if not entries:
        epr("No entries to build")
        return False

    ks_path: Path | None = None
    if ks_b64 := os.getenv("KEYSTORE_BASE64", ""):
        with tempfile.NamedTemporaryFile(dir=TEMP_DIR, suffix=".keystore", delete=False) as tf:
            tf.write(base64.b64decode(ks_b64))
            ks_path = Path(tf.name)

    try:
        with ThreadPoolExecutor(max_workers=config.parallel_jobs) as pool:
            futures = _submit_entries(entries, pool, net, ks_path, config.strict_sigcheck)
    finally:
        if ks_path:
            ks_path.unlink(missing_ok=True)

    for tmp in TEMP_DIR.rglob("tmp*"):
        shutil.rmtree(tmp, ignore_errors=True)

    log_lines: list[str] = []
    for fut in as_completed(futures):
        if r := fut.result():
            log_lines.append(r)

    if not log_lines:
        epr("All builds failed")
        return False

    changelogs = "".join(cl.read_text(encoding="utf-8") for cl in sorted(TEMP_DIR.glob("*/changelog.md")))
    microg_line = "▶️ » Install [MicroG-RE](https://github.com/MorpheApp/MicroG-RE/releases) to enable Google account sign-in for supported apps\n"
    Path("build.md").write_text("\n".join([*log_lines, "", microg_line, changelogs]), encoding="utf-8")
    pr("Done")
    return True