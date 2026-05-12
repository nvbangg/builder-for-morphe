import os
import threading
from pathlib import Path
from typing import Self

from curl_cffi import requests
from curl_cffi.requests import exceptions as req_exc

from src.core.logger import epr, pr


class NetworkError(Exception):
    pass

class NetworkManager:
    def __init__(self) -> None:
        self.session = requests.Session(impersonate="firefox147")
        token = os.getenv("GITHUB_TOKEN")
        self._gh_headers: dict[str, str] = {"Authorization": f"token {token}"} if token else {}
        self._request_lock = threading.Lock()
        self._dest_locks: dict[Path, threading.Lock] = {}
        self._dest_locks_mu = threading.Lock()

    def _get_dest_lock(self, dest: Path) -> threading.Lock:
        with self._dest_locks_mu:
            if dest not in self._dest_locks:
                self._dest_locks[dest] = threading.Lock()
            return self._dest_locks[dest]

    def get(self, url: str, headers: dict[str, str] | None = None) -> str:
        try:
            with self._request_lock:
                resp = self.session.get(url, timeout=(5, 10), allow_redirects=True, headers=headers, verify=True)
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
                with self._request_lock:
                    resp = self.session.get(url, timeout=(5, 300), stream=True, allow_redirects=True, headers=headers, verify=True)
                    resp.raise_for_status()

                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=131072):
                        fh.write(chunk)
                tmp.replace(dest)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise NetworkError(f"Download failed: {url}") from None

    def gh_download(self, url: str, dest: Path) -> None:
        pr(f"Getting '{dest.name}' from '{url}'")
        self.download(url, dest, headers=self._gh_headers | {"Accept": "application/octet-stream"})

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.session.close()