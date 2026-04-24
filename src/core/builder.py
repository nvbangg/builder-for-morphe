import base64
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import replace
from pathlib import Path

from src.core.config import BUILD_DIR, TEMP_DIR, AppEntry, Config, SOURCES, parse_app_entries
from src.core.logger import abort, epr, pr
from src.core.network import NetworkManager
from src.core.patcher import PatcherCLI, PatcherError, _parse_args
from src.core.prebuilts import APKSIGNER, Prebuilts, fetch_prebuilts, get_highest_ver
from src.scrapers.base import BaseScraper


class BuilderError(Exception):
    pass

def _make_scraper(source: str, net: NetworkManager) -> BaseScraper:
    from src.scrapers.apkmirror import APKMirrorScraper
    from src.scrapers.archive import ArchiveScraper
    from src.scrapers.uptodown import UptodownScraper
    match source:
        case "apkmirror":
            return APKMirrorScraper(net)
        case "uptodown":
            return UptodownScraper(net)
        case "archive":
            return ArchiveScraper(net)
        case _:
            raise ValueError(f"Unknown APK source: {source!r}")

def _iter_sources(entry: AppEntry) -> Iterator[tuple[str, str]]:
    return ((src, url) for src in SOURCES if (url := getattr(entry, f"{src}_dlurl", None)))

def _find_pkg_name(entry: AppEntry, table: str, net: NetworkManager) -> tuple[str, str, dict[str, BaseScraper]]:
    scrapers: dict[str, BaseScraper] = {}
    for src, url in _iter_sources(entry):
        scraper = _make_scraper(src, net)
        try:
            scraper.fetch_metadata(url)
            if not (pkg := scraper.get_pkg_name()):
                raise ValueError("Empty package name")
            scrapers[src] = scraper
            pr(f"Package name of '{table}' is '{pkg}'")
            return pkg, src, scrapers
        except Exception as exc:
            epr(f"Could not find {table} in {src}: {exc}")

    raise BuilderError(f"Package name not found for '{table}'")

def _resolve_version(entry: AppEntry, table: str, patcher: PatcherCLI, list_patches: str, pkg_name: str, dl_from: str, scrapers: dict[str, BaseScraper]) -> tuple[str, bool]:
    match entry.version:
        case "auto":
            if ver := patcher.get_last_supported_version(list_patches, pkg_name, _parse_args(entry.included_patches)):
                pr(f"Choosing version '{ver}' for {table}")
                return ver, False
            force, allow_beta = False, False
        case "latest" | "beta" as mode:
            force, allow_beta = True, (mode == "beta")
        case str() as specific_version:
            pr(f"Choosing version '{specific_version}' for {table}")
            return specific_version, True
        case _:
            raise BuilderError(f"Invalid version spec for '{table}': {entry.version!r}")

    if not (scraper := scrapers.get(dl_from)):
        raise BuilderError(f"No scraper for {dl_from!r}")

    pkgvers = scraper.get_versions(allow_beta=allow_beta)
    try:
        version = get_highest_ver(pkgvers)
    except ValueError:
        version = pkgvers[0] if pkgvers else ""

    if not version:
        raise BuilderError(f"Could not determine version for '{table}'")

    pr(f"Choosing version '{version}' for {table}")
    return version, force

def _download_apk(entry: AppEntry, table: str, version: str, arch: str, arch_f: str, pkg_name: str, net: NetworkManager, scrapers: dict[str, BaseScraper]) -> tuple[Path, Path]:
    version_f = version.replace(" ", "").lstrip("v")
    stock_apk = TEMP_DIR / f"{pkg_name}-{version_f}-{arch_f}.apk"
    stock_apkm = stock_apk.with_name(f"{stock_apk.name}.apkm")

    if stock_apk.exists() or stock_apkm.exists():
        return stock_apk, stock_apkm

    for src, url in _iter_sources(entry):
        pr(f"Downloading '{table}' from '{src}'")
        if src not in scrapers:
            try:
                scraper = _make_scraper(src, net)
                scraper.fetch_metadata(url)
                scrapers[src] = scraper
            except Exception as exc:
                epr(f"Could not fetch metadata for '{table}' from '{src}': {exc}")
                continue

        try:
            scrapers[src].download(url, version, stock_apk, arch, entry.dpi)
            if stock_apk.exists() or stock_apkm.exists():
                return stock_apk, stock_apkm
        except Exception as exc:
            epr(f"Could not download '{table}' from '{src}' version='{version}' arch='{arch}': {exc}")

    raise BuilderError(f"Stock APK not found for '{table}'")

def _extract_base_apk(apkm: Path, pkg_name: str, dest_dir: Path) -> Path:
    with zipfile.ZipFile(apkm, "r") as zf:
        names = zf.namelist()
        candidate = next((c for c in ("base.apk", f"{pkg_name}.apk") if c in names), None)
        if candidate is None:
            raise BuilderError(f"Neither 'base.apk' nor '{pkg_name}.apk' found inside {apkm.name}")
        zf.extract(candidate, dest_dir)
        return dest_dir / candidate

def _verify_sig(stock_apk: Path, stock_apkm: Path, pkg_name: str, patcher: PatcherCLI, table: str) -> None:
    try:
        apk_to_check = stock_apk
        if stock_apkm.exists():
            with tempfile.TemporaryDirectory(dir=TEMP_DIR) as tmp_dir:
                apk_to_check = _extract_base_apk(stock_apkm, pkg_name, Path(tmp_dir))
                if patcher.check_signature(apk_to_check, pkg_name):
                    return
        elif patcher.check_signature(stock_apk, pkg_name):
            return
    except BuilderError as exc:
        raise BuilderError(f"Sig check failed for '{table}': {exc}") from exc

    raise BuilderError(f"APK signature mismatch for '{table}'")

def _apply_patch(entry: AppEntry, table: str, arch: str, arch_f: str, app_name_l: str, version: str, version_f: str, force: bool, patcher: PatcherCLI, list_patches: str, stock_apk: Path, stock_apkm: Path) -> Path:
    included = _parse_args(entry.included_patches)
    excluded = _parse_args(entry.excluded_patches)
    microg, disable_psu = patcher.resolve_auto_patches(list_patches)
    brand_f = entry.brand.lower().replace(" ", "-")
    final_args = patcher.build_patch_args(included_patches=included, excluded_patches=excluded, exclusive=entry.exclusive_patches, extra_args=entry.patcher_args, arch=arch, auto_patches=[p for p in (microg, disable_psu) if p], force=force)
    patched_apk = TEMP_DIR / f"{app_name_l}-{brand_f}-{version_f}-{arch_f}.apk"
    stock_input = stock_apkm if stock_apkm.exists() else stock_apk

    if os.getenv("NORB") != "true" or not patched_apk.exists():
        pr(f"Building '{table}'")
        patcher.patch(stock_input, patched_apk, final_args)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    apk_output = BUILD_DIR / f"{app_name_l}-{brand_f}-v{version_f}-{arch_f}.apk"
    shutil.move(patched_apk, apk_output)
    return apk_output

def _build_single(entry: AppEntry, arch: str, table: str, net: NetworkManager, patcher: PatcherCLI) -> str | None:
    for field_name, raw in (("included-patches", entry.included_patches), ("excluded-patches", entry.excluded_patches)):
        if raw and "'" not in raw:
            epr(f"Patch names inside {field_name} must be quoted")
            return None

    try:
        pkg_name, dl_from, scrapers = _find_pkg_name(entry, table, net)
        list_patches = patcher.list_patches(pkg_name)
        version, force = _resolve_version(entry, table, patcher, list_patches, pkg_name, dl_from, scrapers)
        arch_f = arch.replace(" ", "")
        version_f = version.replace(" ", "").lstrip("v")
        app_name_l = entry.app_name.lower().replace(" ", "-")
        stock_apk, stock_apkm = _download_apk(entry, table, version, arch, arch_f, pkg_name, net, scrapers)
        _verify_sig(stock_apk, stock_apkm, pkg_name, patcher, table)
        apk_output = _apply_patch(entry, table, arch, arch_f, app_name_l, version, version_f, force, patcher, list_patches, stock_apk, stock_apkm)
        pr(f"Built {table}: '{apk_output}'")
        return f"🟢 » {table}: `{version}`"

    except (BuilderError, PatcherError, ValueError) as exc:
        epr(f"Building '{table}' failed! {exc}")
        return None

def run_build(data: dict[str, object], config: Config, net: NetworkManager, target_app: str | None = None, arch_override: str | None = None) -> bool:
    entries = [e for e in parse_app_entries(data, config) if e.enabled]

    if target_app and not (entries := [e for e in entries if e.table == target_app]):
        abort(f"App '{target_app}' not found in config")

    if arch_override:
        entries = [replace(e, arch=arch_override) for e in entries]

    build_mode = os.getenv("BUILD_MODE", "")
    prebuilts_cache: dict[tuple[str, str, str, str], Prebuilts] = {}
    futures: list = []
    ks_path: Path | None = None
    if ks_b64 := os.getenv("KEYSTORE_BASE64", ""):
        ks_path = TEMP_DIR / "ks.keystore"
        ks_path.write_bytes(base64.b64decode(ks_b64))

    try:
        with ThreadPoolExecutor(max_workers=config.parallel_jobs) as pool:
            for entry in entries:
                if not entry.dl_from:
                    epr(f"No 'dlurl' option was set for '{entry.table}'")
                    continue

                patches_ver = "dev" if build_mode == "dev" else entry.patches_version
                cache_key = (entry.cli_source, entry.cli_version, entry.patches_source, patches_ver)

                if cache_key not in prebuilts_cache:
                    try:
                        prebuilts_cache[cache_key] = fetch_prebuilts(cli_src=entry.cli_source, cli_ver=entry.cli_version, patches_src=entry.patches_source, patches_ver=patches_ver, net=net)
                    except Exception as exc:
                        epr(f"Could not get prebuilts for '{entry.table}': {exc}")
                        continue

                prebuilts = prebuilts_cache[cache_key]
                patcher = PatcherCLI(prebuilts.cli_jar, prebuilts.patches_mpp, APKSIGNER, ks_path=ks_path)
                arches = ("arm64-v8a", "arm-v7a") if entry.arch == "both" else (entry.arch,)

                for arch in arches:
                    label = entry.table if entry.arch == "all" else f"{entry.table} ({arch})"
                    futures.append(pool.submit(_build_single, entry, arch, label, net, patcher))
    finally:
        if ks_path:
            ks_path.unlink(missing_ok=True)

    for tmp in TEMP_DIR.rglob("tmp.*"):
        shutil.rmtree(tmp, ignore_errors=True)

    log_lines = [r for fut in as_completed(futures) if (r := fut.result())]

    if not log_lines:
        epr("All builds failed")
        return False

    changelogs = "".join(cl.read_text(encoding="utf-8") for cl in sorted(TEMP_DIR.glob("*/changelog.md")))
    Path("build.md").write_text(f"{"\n".join(log_lines)}\n\n- ▶️ » Install [MicroG-RE](https://github.com/MorpheApp/MicroG-RE/releases) for YouTube and YT Music APKs\n{changelogs}", encoding="utf-8")
    pr("Done")
    return True