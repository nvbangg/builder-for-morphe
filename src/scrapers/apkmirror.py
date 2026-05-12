import re
from pathlib import Path

from src.core.network import NetworkManager
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, parse_html


class APKMirrorError(Exception):
    pass

class APKMirrorScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._resp_html = ""
        self._category = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        self._resp_html = self.net.get(url)
        self._category = url.rstrip("/").split("/")[-1]
        if not (m := re.search(r"play\.google\.com/store/apps/details\?id=([\w.]+)", self._resp_html)):
            raise APKMirrorError("APKMirror: package name not found in page")

        soup = parse_html(self.net.get(f"https://www.apkmirror.com/uploads/?appcategory={self._category}"))
        versions_raw = [v for val in soup.select("span.infoSlide-name + span.infoSlide-value") if (v := val.get_text(strip=True))]
        versions = [v for v in versions_raw if not re.search(r"beta|alpha", v, re.I)]
        return AppMetadata(pkg_name=m.group(1), versions=versions)

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if arch == "arm-v7a":
            arch = "armeabi-v7a"

        soup = parse_html(self._resp_html)
        h1 = soup.select_one("h1.marginZero")
        apkmname = re.sub(r"[^a-z0-9-]", "", (h1.get_text(strip=True).lower() if h1 else "").replace(" ", "-"))
        ver_dashed = version.replace(".", "-").replace(" ", "-")
        resp = self.net.get(f"{url.rstrip('/')}/{apkmname}-{ver_dashed}-release/")
        is_bundle = False
        soup_release = parse_html(resp)
        if soup_release.select_one("div.table-row.headerFont:last-child"):
            dl_url = self._pick_variant(soup_release, dpi, arch)
            if dl_url is None:
                raise APKMirrorError(f"APKMirror: no matching variant for {version}/{arch}")
            resp = self.net.get(dl_url[0])
            is_bundle = dl_url[1] == "BUNDLE"

        soup_dl = parse_html(resp)
        if not (btn := soup_dl.select_one("a.btn")) or not btn.get("href"):
            raise APKMirrorError("APKMirror: download button not found")

        soup_final = parse_html(self.net.get(_absolute(str(btn["href"]))))
        if not (a_tag := soup_final.select_one("span > a[rel=nofollow]")) or not a_tag.get("href"):
            raise APKMirrorError("APKMirror: final download link not found")

        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(_absolute(str(a_tag["href"])), out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _pick_variant(self, soup, dpi: str, arch: str) -> tuple[str, str] | None:
        rows = soup.select("div.table-row.headerFont")
        for bt in ("APK", "BUNDLE"):
            if url_found := self._search(rows, dpi, arch, bt):
                return url_found, bt

        for row in reversed(rows):
            if not (link := row.select_one("div.table-cell:first-child > a")) or not link.get("href"):
                continue
            badge = row.select_one(".apkm-badge")
            b_type = badge.get_text(strip=True).upper() if badge else "APK"
            return _absolute(str(link["href"])), b_type
        return None

    def _search(self, rows: list, dpi: str, arch: str, bundle_type: str) -> str:
        apparch = {"universal", "noarch", "arm64-v8a + armeabi-v7a"} | ({arch} if arch != "all" else set())
        appdpi = {"nodpi", "anydpi", "120-640dpi"} | ({dpi} if dpi else set())
        for row in reversed(rows):
            if not (link := row.select_one("div.table-cell:first-child > a")) or not link.get("href"):
                continue
            spans = [c for c in row.children if getattr(c, "name", None) == "span"]
            span_texts = [s.get_text(strip=True) for s in spans[2:]]
            if len(span_texts) >= 4 and span_texts[2] == bundle_type and span_texts[3] in appdpi and span_texts[1] in apparch:
                return _absolute(str(link["href"]))
        return ""

def _absolute(href: str) -> str:
    return href if href.startswith(("http://", "https://")) else f"https://www.apkmirror.com{href}"