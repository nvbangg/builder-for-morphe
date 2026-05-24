import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.core.network import NetworkManager, ResourceNotFoundError
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, ScraperError

APK_MIRROR_BASE = "https://www.apkmirror.com"


def _parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

class APKMirrorError(ScraperError):
    pass

class APKMirrorScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._resp_html: str = ""
        self._category: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        self._resp_html = self.net.get(url)
        self._category = url.rstrip("/").split("/")[-1]
        m = re.search(r"play\.google\.com/store/apps/details\?id=([\w.]+)", self._resp_html)
        if not m:
            raise APKMirrorError("Package name not found")

        soup = _parse_html(self.net.get(f"{APK_MIRROR_BASE}/uploads/?appcategory={self._category}"))
        versions: list[str] = []
        for val in soup.select("span.infoSlide-name + span.infoSlide-value"):
            v = val.get_text(strip=True)
            if v:
                versions.append(v)

        versions = [v for v in versions if not re.search(r"beta|alpha", v, re.I)]
        return AppMetadata(pkg_name=m.group(1), versions=versions)

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        soup = _parse_html(self._resp_html)
        h1 = soup.select_one("h1.marginZero")
        apkmname = re.sub(r"[^a-z0-9-]", "", (h1.get_text(strip=True).lower() if h1 else "").replace(" ", "-"))
        ver_dashed = version.replace(".", "-").replace(" ", "-")
        try:
            release_html = self.net.get(f"{url.rstrip('/')}/{apkmname}-{ver_dashed}-release/")
        except ResourceNotFoundError:
            raise APKMirrorError("Version not found") from None

        is_bundle = False
        soup_release = _parse_html(release_html)
        if soup_release.select_one("div.table-row.headerFont:last-child"):
            dl_url = self._pick_variant(soup_release, dpi, arch)
            if dl_url is None:
                raise APKMirrorError("No matching variant found")
            release_html = self.net.get(dl_url[0])
            is_bundle = dl_url[1] == "BUNDLE"

        soup_dl = _parse_html(release_html)
        btn = soup_dl.select_one("a.btn")
        btn_url = urljoin(APK_MIRROR_BASE, btn["href"])
        soup_final = _parse_html(self.net.get(btn_url))
        dl_link = soup_final.select_one("span > a[rel=nofollow]")
        final_url = urljoin(APK_MIRROR_BASE, dl_link["href"])
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(final_url, out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _pick_variant(self, soup, dpi: str, arch: str) -> tuple[str, str] | None:
        rows = soup.select("div.table-row.headerFont")
        for bt in ("APK", "BUNDLE"):
            url_found = self._search(rows, dpi, arch, bt)
            if url_found:
                return url_found, bt
        return None

    def _search(self, rows: list, dpi: str, arch: str, bundle_type: str) -> str:
        apparch = {"universal", "noarch", "arm64-v8a + armeabi-v7a"}
        if arch != "all":
            apparch.add(arch)

        appdpi = {"nodpi", "anydpi", "120-640dpi"}
        if dpi:
            appdpi.add(dpi)

        for row in reversed(rows):
            link = row.select_one("div.table-cell:first-child > a")
            if not link or not link.get("href"):
                continue

            cells = row.select("div.table-cell")
            if len(cells) < 4:
                continue

            badge = cells[0].select_one(".apkm-badge")
            b_type = badge.get_text(strip=True).upper() if badge else "APK"
            arch_text = cells[1].get_text(strip=True)
            dpi_text = cells[3].get_text(strip=True)
            if b_type == bundle_type and dpi_text in appdpi and arch_text in apparch:
                return urljoin(APK_MIRROR_BASE, str(link["href"]))

        return ""