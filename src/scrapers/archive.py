import re
from pathlib import Path

from src.core.network import NetworkManager
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, parse_html

_ARCH_SUFFIX = re.compile(r"-(?:all|arm64-v8a|arm-v7a)\.(?:apk|apkm|xapk)$")


class ArchiveError(Exception):
    pass

class ArchiveScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._file_list: list[str] = []
        self._pkg_name: str = ""
        self._base_url: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        self._base_url = url.rstrip("/")
        self._pkg_name = self._base_url.split("/")[-1]
        soup = parse_html(self.net.get(url))
        self._file_list = [
            a["href"] for a in soup.find_all("a", href=True)
            if not a["href"].startswith(("?", "/", "http"))
        ]
        prefix = f"{self._pkg_name}-"
        versions = dict.fromkeys(
            ver for f in self._file_list
            if f.startswith(prefix) and (ver := _ARCH_SUFFIX.sub("", f[len(prefix):]))
        )
        return AppMetadata(pkg_name=self._pkg_name, versions=list(versions))

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        version = version.replace(" ", "").lstrip("v")
        expected_prefix = f"{self._pkg_name}-{version}-{arch.replace(' ', '')}"
        if not (match := next((f for f in self._file_list if f.startswith(expected_prefix)), None)):
            raise ArchiveError(f"Archive: no file matching version='{version}' arch='{arch}' in {url}")

        is_bundle = match.endswith((".apkm", ".xapk"))
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(f"{self._base_url}/{match}", out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)