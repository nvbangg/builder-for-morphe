import json
import re
from pathlib import Path

from src.core.network import NetworkManager, ResourceNotFoundError
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, ScraperError

_ARCH_SUFFIX = re.compile(r"(?:-(all|arm64-v8a|armeabi-v7a|x86_64|x86))?(?:\.apk\.apkm|\.apk|\.apkm)$", re.I)


class GitHubReleasesError(ScraperError):
    pass

class GitHubScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._assets: list[dict] = []
        self._tag: str = ""
        self._pkg_name: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        m = re.search(r"github\.com/([^/]+)/([^/]+)/releases/tag/([^/]+)", url)
        if not m:
            raise GitHubReleasesError(f"Invalid GitHub release URL: {url}")

        owner, repo, tag = m.groups()
        self._tag = tag
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        try:
            release = json.loads(self.net.gh_get(api_url))
        except ResourceNotFoundError:
            raise GitHubReleasesError(f"Release tag '{tag}' not found in '{owner}/{repo}'") from None

        self._pkg_name = release.get("name") or tag
        self._assets = release.get("assets", [])
        prefix = f"{self._pkg_name}-"
        versions: list[str] = []
        for asset in self._assets:
            name = asset.get("name", "")
            if not name.startswith(prefix) or not name.endswith((".apk", ".apkm")):
                continue

            ver = _ARCH_SUFFIX.sub("", name[len(prefix):])
            if ver not in versions:
                versions.append(ver)

        return AppMetadata(pkg_name=self._pkg_name, versions=versions or [self._tag])

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if not self._assets:
            self.fetch_metadata(url)

        version_f = version.replace(" ", "").lstrip("v")
        apk_assets = [a for a in self._assets if a.get("name", "").endswith((".apk", ".apkm"))]
        asset = None
        for a in apk_assets:
            name = a["name"]
            if version_f and version_f not in name:
                continue

            m = _ARCH_SUFFIX.search(name)
            file_arch = m.group(1).lower() if m and m.group(1) else "all"
            if arch in ("all", "both"):
                if file_arch != "all":
                    continue
            else:
                if file_arch not in (arch, "all"):
                    continue

            asset = a
            if file_arch == arch or arch in ("all", "both"):
                break

        if asset is None:
            raise GitHubReleasesError(f"No matching variant found for arch '{arch}'")

        is_bundle = asset["name"].endswith(".apkm")
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.gh_download(asset["browser_download_url"], out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)