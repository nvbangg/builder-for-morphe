import os
import threading
import time
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.requests import exceptions as req_exc

from src.core.logger import epr


class NetworkError(Exception):
    pass

class ResourceNotFoundError(NetworkError):
    """Raised when a remote resource returns HTTP 404."""

class NetworkManager:
    def __init__(self) -> None:
        self.session = requests.Session(impersonate="firefox147")
        token = os.getenv("GITHUB_TOKEN")
        self._gh_headers: dict[str, str] = {"Authorization": f"token {token}"} if token else {}
        self._domain_locks: dict[str, threading.Lock] = {}
        self._domain_locks_mu = threading.Lock()
        self._dest_locks: dict[Path, threading.Lock] = {}
        self._dest_locks_mu = threading.Lock()

    def _get_domain_lock(self, url: str) -> threading.Lock:
        domain = urlparse(url).netloc
        with self._domain_locks_mu:
            return self._domain_locks.setdefault(domain, threading.Lock())

    def _get_dest_lock(self, dest: Path) -> threading.Lock:
        with self._dest_locks_mu:
            return self._dest_locks.setdefault(dest, threading.Lock())

    def get(self, url: str, headers: dict[str, str] | None = None) -> str:
        try:
            with self._get_domain_lock(url):
                time.sleep(0.5)
                resp = self.session.get(url, timeout=(5, 10), allow_redirects=True, headers=headers, verify=True)

            if resp.status_code == 404:
                raise ResourceNotFoundError(f"Not found (404): {url}")

            if resp.status_code >= 400:
                epr(f"HTTP {resp.status_code} for {url}")
                resp.raise_for_status()

            return resp.text
        except req_exc.RequestException:
            raise NetworkError(f"Request failed: {url}") from None

    def gh_get(self, url: str) -> str:
        return self.get(url, headers=self._gh_headers)

    def download(self, url: str, dest: Path, headers: dict[str, str] | None = None) -> None:
        if dest.exists():
            return

        with self._get_dest_lock(dest):
            if dest.exists():
                return

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f"tmp.{dest.name}")
            tmp.unlink(missing_ok=True)
            try:
                with self._get_domain_lock(url):
                    time.sleep(0.5)
                    resp = self.session.get(url, timeout=(5, 300), stream=True, allow_redirects=True, headers=headers, verify=True)
                    resp.raise_for_status()

                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1048576):
                        fh.write(chunk)
                tmp.replace(dest)
            except req_exc.RequestException:
                raise NetworkError(f"Download failed: {url}") from None
            finally:
                tmp.unlink(missing_ok=True)

    def gh_download(self, url: str, dest: Path) -> None:
        self.download(url, dest, headers=self._gh_headers | {"Accept": "application/octet-stream"})

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.session.close()