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
        self._resp_pkg_html: str = ""

    def fetch_metadata(self, url: str) -> AppMetadata:
        self._resp_html = self.net.get(f"{url}/versions")
        self._resp_pkg_html = self.net.get(f"{url}/download")
        soup_pkg = _parse_html(self._resp_pkg_html)
        if not (td := soup_pkg.select_one("tr.full:nth-child(1) > td:nth-child(3)")):
            raise UptodownError("Package name not found")

        soup_ver = _parse_html(self._resp_html)
        return AppMetadata(pkg_name=td.get_text(strip=True), versions=[el.get_text(strip=True) for el in soup_ver.select(".version") if el.get_text(strip=True)])

    def download(self, url: str, version: str, dest: Path, arch: str, dpi: str) -> DownloadResult:
        if arch == "arm-v7a":
            arch = "armeabi-v7a"

        apparch = ["arm64-v8a, armeabi-v7a, x86_64", "arm64-v8a, armeabi-v7a, x86, x86_64", "arm64-v8a, armeabi-v7a"] + ([arch] if arch != "all" else [])
        soup = _parse_html(self._resp_html)
        data_code = str(soup.select_one("#detail-app-name")["data-code"])
        version_url_data = self._find_version_url(url, data_code, version)
        ver_url = f"{version_url_data['url']}/{version_url_data['extraURL']}/{version_url_data['versionID']}"
        is_bundle = version_url_data.get("kindFile") == "xapk"
        soup_ver = _parse_html(self.net.get(ver_url))
        if (btn_variants := soup_ver.select_one(".button.variants")) and (data_version := btn_variants.get("data-version")):
            resp, is_bundle = self._pick_variant_file(url, data_code, str(data_version), apparch)
            soup_ver = _parse_html(resp)

        out_path = dest.with_name(f"{dest.name}{'.apkm' if is_bundle else ''}")
        self.net.download(f"https://dw.uptodown.com/dwn/{soup_ver.select_one('#detail-download-button')['data-url']}", out_path)
        return DownloadResult(path=out_path, is_bundle=is_bundle)

    def _find_version_url(self, url: str, data_code: str, version: str) -> dict:
        for i in range(1, 21):
            payload = json.loads(self.net.get(f"{url}/apps/{data_code}/versions/{i}"))
            if not (data := payload.get("data")):
                break

            if match := next((e for e in data if e.get("version") == version), None):
                return match["versionURL"] | {"kindFile": match.get("kindFile", "")}

        raise UptodownError("Version not found")

    def _pick_variant_file(self, url: str, data_code: str, data_version: str, apparch: list[str]) -> tuple[str, bool]:
        base_url = url.rsplit("/", 1)[0]
        files_html = json.loads(self.net.get(f"{base_url}/app/{data_code}/version/{data_version}/files")).get("content", "")
        content = _parse_html(files_html).select_one(".content")
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
            return self.net.get(f"{url}/download/{child.select_one('.v-report')['data-file-id']}-x"), is_bundle

        raise UptodownError("No matching variant")