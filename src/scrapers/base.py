from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.core.network import NetworkManager


class ScraperError(Exception):
    """Raised for scraper-layer failures: DOM parsing, regex mismatches, missing assets"""

@dataclass(slots=True, frozen=True)
class AppMetadata:
    pkg_name: str
    versions: list[str]

@dataclass(slots=True, frozen=True)
class DownloadResult:
    path: Path
    is_bundle: bool = False

class BaseScraper(ABC):
    def __init__(self, net: NetworkManager) -> None:
        self.net = net
        self._cache: dict[str, AppMetadata] = {}

    def cached_metadata(self, url: str) -> AppMetadata:
        if url not in self._cache:
            self._cache[url] = self.fetch_metadata(url)
        return self._cache[url]

    @abstractmethod
    def fetch_metadata(self, url: str) -> AppMetadata:
        pass

    @abstractmethod
    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        pass