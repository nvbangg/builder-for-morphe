import json
from pathlib import Path

from bs4 import BeautifulSoup

from src.core.network import NetworkManager
from src.scrapers.base import AppMetadata, BaseScraper, DownloadResult, ScraperError


def _parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

class UptodownError(ScraperError):
    pass

class UptodownScraper(BaseScraper):
    def __init__(self, net: NetworkManager) -> None:
        super().__init__(net)
        self._resp_html: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        self._resp_html = self.net.get(f"{url}/versions")
        pkg_html = self.net.get(f"{url}/download")
        
        try:
            btn = _parse_html(pkg_html).select_one("#gplay-button")
            pkg_name = btn["data-url"].split("?id=")[-1]
        except (AttributeError, KeyError, IndexError):
            raise UptodownError("Package name not found") from None

        soup_ver = _parse_html(self._resp_html)
        versions: list[str] = []
        for el in soup_ver.select(".version"):
            if text := el.get_text(strip=True):
                if "." in text:
                    versions.append(text)

        return AppMetadata(pkg_name=pkg_name, versions=versions)

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if not self._resp_html:
            self._resp_html = self.net.get(f"{url}/versions")

        apparch = {"arm64-v8a, armeabi-v7a, x86_64", "arm64-v8a, armeabi-v7a, x86, x86_64", "arm64-v8a, armeabi-v7a"}
        if arch != "all":
            apparch.add(arch)

        soup = _parse_html(self._resp_html)
        data_code = str(soup.select_one("#detail-app-name")["data-code"])
        version_url_data = self._find_version_url(url, data_code, version)
        ver_url = f"{version_url_data.get('url', '')}/{version_url_data.get('extraURL', '')}/{version_url_data.get('versionID', '')}"
        is_bundle = version_url_data.get("kindFile") == "xapk"
        soup_ver = _parse_html(self.net.get(ver_url))
        btn_variants = soup_ver.select_one(".button.variants")
        if btn_variants and (data_version := btn_variants.get("data-version")):
            resp, is_bundle = self._pick_variant_file(url, data_code, str(data_version), apparch)
            soup_ver = _parse_html(resp)

        dl_url = soup_ver.select_one("#detail-download-button")["data-url"]
        out_path = dest.with_suffix(".apkm") if is_bundle else dest
        self.net.download(f"https://dw.uptodown.com/dwn/{dl_url}", out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _find_version_url(self, url: str, data_code: str, version: str) -> dict:
        for i in range(1, 21):
            payload = json.loads(self.net.get(f"{url}/apps/{data_code}/versions/{i}"))
            data = payload.get("data")
            if not data:
                break

            for entry in data:
                if entry.get("version") != version:
                    continue
                ver_url_dict = entry.get("versionURL") or {}
                return ver_url_dict | {"kindFile": entry.get("kindFile", "")}

        raise UptodownError("Version not found")

    def _pick_variant_file(self, url: str, data_code: str, data_version: str, apparch: set[str]) -> tuple[str, bool]:
        base_url = url.rsplit("/", 1)[0]
        files_html = json.loads(self.net.get(f"{base_url}/app/{data_code}/version/{data_version}/files")).get("content", "")
        soup = _parse_html(files_html)
        content = soup.select_one(".content")
        node_arch = ""
        for child in content.children:
            if not getattr(child, "name", None):
                continue

            if "variant" not in child.get("class", []):
                node_arch = child.get_text(strip=True)
                continue

            if not node_arch or node_arch not in apparch:
                continue

            file_type_tag = child.select_one(".v-file > span")
            is_bundle = file_type_tag.get_text(strip=True) == "xapk" if file_type_tag else False
            try:
                file_id = child.select_one(".v-report")["data-file-id"]
                return self.net.get(f"{url}/download/{file_id}-x"), is_bundle
            except (TypeError, KeyError):
                continue

        raise UptodownError("No matching variant found")