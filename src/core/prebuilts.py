import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from src.core.config import TEMP_DIR
from src.core.logger import pr, wpr
from src.core.network import NetworkManager

APKSIGNER: Path = Path("bin/apksigner.jar")


class PrebuiltsError(Exception):
    pass

@dataclass(slots=True, frozen=True)
class Prebuilts:
    cli_jar: Path
    patches_mpp: Path

def _ver_key(ver: str) -> tuple[int, ...]:
    base = ver.split("-")[0]
    return tuple(int(x) for x in re.findall(r"\d+", base)) or (0,)

def get_highest_ver(versions: list[str]) -> str:
    if not (clean := [v.strip() for v in versions if v.strip()]):
        raise ValueError("Empty version list")

    return max(clean, key=_ver_key)

def fetch_prebuilts(cli_src: str, cli_ver: str, patches_src: str, patches_ver: str, net: NetworkManager) -> Prebuilts:
    patches_org = patches_src.split("/")[0]
    cl_dir = TEMP_DIR / patches_org.lower()
    cl_dir.mkdir(parents=True, exist_ok=True)
    pr(f"Getting prebuilts ({patches_org})")
    specs = [
        (cli_src, "CLI", cli_ver, "cli", "jar"),
        (patches_src, "Patches", patches_ver, "patches", "mpp"),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_fetch_single_asset, *spec, cl_dir=cl_dir, net=net) for spec in specs]
        results = [f.result() for f in futures]

    (cli_jar, cli_changelog), (patches_mpp, patches_changelog) = results
    combined = cli_changelog + patches_changelog
    if combined:
        with (cl_dir / "changelog.md").open("a", encoding="utf-8") as f:
            f.write(combined)

    return Prebuilts(cli_jar=cli_jar, patches_mpp=patches_mpp)

def _fetch_single_asset(src: str, tag: str, ver: str, fprefix: str, ext: str, cl_dir: Path, net: NetworkManager) -> tuple[Path, str]:
    dir_path = TEMP_DIR / src.split("/")[0].lower()
    dir_path.mkdir(parents=True, exist_ok=True)
    base_url = f"https://api.github.com/repos/{src}/releases"
    release = None
    if ver == "dev":
        releases: list[dict] = json.loads(net.gh_get(base_url))
        ver = get_highest_ver([r["tag_name"] for r in releases if r.get("tag_name")])
    elif ver == "latest":
        release = json.loads(net.gh_get(f"{base_url}/latest"))
        ver = release.get("tag_name", "")

    file = _find_cached(dir_path, fprefix, ver, ext, exclude_dev=False)
    is_patches = tag == "Patches"
    tag_name = ""
    changelog = ""

    if file is None:
        if release is None:
            release = json.loads(net.gh_get(f"{base_url}/tags/{ver}"))

        tag_name = release.get("tag_name", "")
        matches = [a for a in release.get("assets", []) if a.get("name", "").endswith(f".{ext}")]
        if len(matches) > 1 and (non_dev := [a for a in matches if "-dev" not in a.get("name", "")]):
            matches = non_dev

        if not matches:
            raise PrebuiltsError(f"No asset (.{ext}) found for {src} @ {ver}")

        if len(matches) > 1:
            wpr("More than 1 asset was found for this release, falling back to the first one found")

        asset = matches[0]
        file = dir_path / asset["name"]
        for old_file in dir_path.glob(f"*{fprefix}-*.{ext}"):
            if old_file.is_file() and not old_file.name.startswith("tmp."):
                old_file.unlink(missing_ok=True)

        pr(f"Getting '{asset['name']}' from '{asset['url']}'")
        net.gh_download(asset["url"], file)
        changelog = f"> ⚙️ » {tag}: `{src.split('/')[0]}/{asset['name']}`  \n"
    else:
        tag_name = _tag_from_filename(file)

    if is_patches and tag_name:
        changelog += f"[🔗 » Changelog](https://github.com/{src}/releases/tag/{tag_name})\n\n"

    return file, changelog

def _find_cached(dir_path: Path, fprefix: str, name_ver: str, ext: str, exclude_dev: bool) -> Path | None:
    pattern = f"*{fprefix}-*.{ext}" if name_ver == "*" else f"*{fprefix}-{name_ver.lstrip('v')}*.{ext}"
    candidates = [f for f in dir_path.glob(pattern) if f.is_file() and not f.name.startswith("tmp.")]
    if exclude_dev:
        candidates = [f for f in candidates if "-dev" not in f.name]

    return max(candidates, key=lambda f: _ver_key(f.name), default=None)

def _tag_from_filename(file: Path) -> str:
    if m := re.search(r"-(\d[\w.]*)(?:-[^.]+)?\.\w+$", file.name):
        return f"v{m.group(1)}"

    return ""