import json
import re
from pathlib import Path
from urllib.parse import urlparse

from src.core.network import NetworkManager, ResourceNotFoundError
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, ScraperError

_ARCH_SUFFIX = re.compile(r"(?:-(?:all|arm64-v8a|arm-v7a|x86_64|x86))?(?:\.apk\.apkm|\.apk|\.apkm)$")


class GitHubReleasesError(ScraperError):
    pass

class GitHubScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._assets: list[dict] = []
        self._tag: str = ""
        self._pkg_name: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        parts = urlparse(url.rstrip("/")).path.split("/")
        owner, repo, tag = parts[1], parts[2], parts[5]
        self._tag = tag
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        try:
            release = json.loads(self.net.gh_get(api_url))
        except ResourceNotFoundError:
            raise GitHubReleasesError(f"Release tag '{tag}' not found in '{owner}/{repo}'") from None

        self._pkg_name = release.get("name", tag)
        self._assets = release.get("assets", [])
        prefix = f"{self._pkg_name}-"
        versions = dict.fromkeys(
            ver for a in self._assets
            if (name := a.get("name", "")).startswith(prefix)
            and name.endswith((".apk", ".apkm"))
            and (ver := _ARCH_SUFFIX.sub("", name[len(prefix):]))
        )
        return AppMetadata(pkg_name=self._pkg_name, versions=list(versions) or [self._tag])

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if not self._assets:
            self.fetch_metadata(url)

        arch_filter = arch if arch not in ("all", "both") else ""
        version_f = version.replace(" ", "").lstrip("v")
        apk_assets = [a for a in self._assets if a.get("name", "").endswith((".apk", ".apkm"))]
        for asset in apk_assets:
            if (not version_f or version_f in asset["name"]) and (not arch_filter or arch_filter in asset["name"]):
                break
        else:
            raise GitHubReleasesError(f"No asset found in release '{self._tag}'")

        is_bundle = asset["name"].endswith(".apkm")
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.gh_download(asset["browser_download_url"], out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)