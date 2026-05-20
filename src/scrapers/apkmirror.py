import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.core.network import NetworkManager, ResourceNotFoundError
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, ScraperError


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
        if not (m := re.search(r"play\.google\.com/store/apps/details\?id=([\w.]+)", self._resp_html)):
            raise APKMirrorError("Package name not found")

        soup = _parse_html(self.net.get(f"https://www.apkmirror.com/uploads/?appcategory={self._category}"))
        versions_raw = [v for val in soup.select("span.infoSlide-name + span.infoSlide-value") if (v := val.get_text(strip=True))]
        versions = [v for v in versions_raw if not re.search(r"beta|alpha", v, re.I)]
        return AppMetadata(pkg_name=m.group(1), versions=versions)

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if arch == "arm-v7a":
            arch = "armeabi-v7a"

        soup = _parse_html(self._resp_html)
        h1 = soup.select_one("h1.marginZero")
        apkmname = re.sub(r"[^a-z0-9-]", "", (h1.get_text(strip=True).lower() if h1 else "").replace(" ", "-"))
        ver_dashed = version.replace(".", "-").replace(" ", "-")
        try:
            resp = self.net.get(f"{url.rstrip('/')}/{apkmname}-{ver_dashed}-release/")
        except ResourceNotFoundError:
            raise APKMirrorError("Version not found") from None

        is_bundle = False
        soup_release = _parse_html(resp)
        if soup_release.select_one("div.table-row.headerFont:last-child"):
            dl_url = self._pick_variant(soup_release, dpi, arch)
            if dl_url is None:
                raise APKMirrorError("No matching variant")
            resp = self.net.get(dl_url[0])
            is_bundle = dl_url[1] == "BUNDLE"

        soup_dl = _parse_html(resp)
        soup_final = _parse_html(self.net.get(self._absolute(str(soup_dl.select_one("a.btn")["href"]))))
        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(self._absolute(str(soup_final.select_one("span > a[rel=nofollow]")["href"])), out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _pick_variant(self, soup, dpi: str, arch: str) -> tuple[str, str] | None:
        rows = soup.select("div.table-row.headerFont")
        for bt in ("APK", "BUNDLE"):
            if url_found := self._search(rows, dpi, arch, bt):
                return url_found, bt
        return None

    def _search(self, rows: list, dpi: str, arch: str, bundle_type: str) -> str:
        apparch = {"universal", "noarch", "arm64-v8a + armeabi-v7a"} | ({arch} if arch != "all" else set())
        appdpi = {"nodpi", "anydpi", "120-640dpi"} | ({dpi} if dpi else set())
        for row in reversed(rows):
            if not (link := row.select_one("div.table-cell:first-child > a")) or not link.get("href"):
                continue

            cells = row.select("div.table-cell")
            if len(cells) < 4:
                continue

            badge = cells[0].select_one(".apkm-badge")
            b_type = badge.get_text(strip=True).upper() if badge else "APK"
            arch_text = cells[1].get_text(strip=True)
            dpi_text = cells[3].get_text(strip=True)
            if b_type == bundle_type and dpi_text in appdpi and arch_text in apparch:
                return self._absolute(str(link["href"]))
        return ""

    def _absolute(self, href: str) -> str:
        return href if href.startswith(("http://", "https://")) else f"https://www.apkmirror.com{href}"