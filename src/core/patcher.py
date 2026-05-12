import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from src.core.config import TEMP_DIR
from src.core.logger import pr, wpr
from src.core.prebuilts import get_highest_ver


class PatcherError(Exception):
    pass

def _arch_to_libs(arch: str) -> str:
    match arch:
        case "arm-v7a":
            return "armeabi-v7a"
        case "arm64-v8a" | "x86" | "x86_64":
            return arch
        case _:
            return "arm64-v8a,armeabi-v7a"

def _run_java(*args: str | Path, capture: bool = True) -> str:
    result = subprocess.run(["java", *(str(a) for a in args)], capture_output=capture, text=True)
    combined = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise PatcherError(combined.strip())
    return combined

def _parse_patch_block(output: str, patch_name: str) -> list[str]:
    if m := re.search(rf"Name:\s*{re.escape(patch_name)}\n.*?Compatible versions:\s*\n(.*?)(?:\n\n|\Z)", output, re.DOTALL | re.IGNORECASE):
        return [v.strip() for v in m.group(1).splitlines() if v.strip()]
    return []

def _parse_versions_output(output: str) -> list[str]:
    if m := re.search(r"Most common compatible versions:\n(.*?)(?:\n\n|\Z)", output, re.DOTALL):
        return [re.sub(r"\s*\(.*?\)", "", v).strip() for v in m.group(1).splitlines() if v.strip()]
    return []

def _redact_args(args: list[str | Path]) -> list[str]:
    redacted = []
    for a in args:
        s = str(a)
        if "keystore-password=" in s or "keystore-entry-password=" in s:
            redacted.append(f"{s.partition('=')[0]}=***")
        elif s.startswith("--keystore="):
            p = Path(s.partition("=")[2])
            redacted.append(f"--keystore={p.parent.name}/{p.name}")
        else:
            redacted.append(s)
    return redacted

class PatcherCLI:
    def __init__(self, cli_jar: Path, patches_mpp: Path, apksigner: Path, ks_path: Path | None = None, sig_file: Path = Path("sig.txt")) -> None:
        self.cli_jar = cli_jar
        self.patches_mpp = patches_mpp
        self.apksigner = apksigner
        self.ks_path = ks_path
        self._signatures: dict[str, str] = {}
        if sig_file.exists():
            for line in sig_file.read_text(encoding="utf-8").splitlines():
                if parts := line.split():
                    self._signatures[parts[-1]] = parts[0].lower()

    def list_patches(self, pkg_name: str) -> str:
        return _run_java("-jar", self.cli_jar, "list-patches", "--patches", self.patches_mpp, "-f", pkg_name, "-v", "-p")

    def list_versions(self, pkg_name: str) -> str:
        return _run_java("-jar", self.cli_jar, "list-versions", "--patches", self.patches_mpp, "-f", pkg_name)

    def get_last_supported_version(self, list_patches_output: str, pkg_name: str, included_patches: list[str]) -> str | None:
        if included_patches and (all_vers := [v for p in included_patches for v in _parse_patch_block(list_patches_output, p)]):
            return get_highest_ver(all_vers)

        versions_output = self.list_versions(pkg_name)
        if "Any" in versions_output:
            return None

        if not (versions := _parse_versions_output(versions_output)):
            raise PatcherError(f"No patches found for '{pkg_name}' in patches '{self.patches_mpp}'")
        return get_highest_ver(versions)

    def resolve_auto_patches(self, list_patches_output: str) -> tuple[str, str]:
        def find(pattern: str) -> str:
            m = re.search(pattern, list_patches_output, re.I | re.M)
            return m.group(1).strip() if m else ""

        return find(r"^Name:\s*(.*(?:gmscore|microg).*)$"), find(r"^Name:\s*(.*disable play store updates.*)$")

    def build_patch_args(self, included_patches: list[str], excluded_patches: list[str], exclusive: bool, extra_args: list[str], arch: str, auto_patches: list[str], force: bool = False) -> list[str]:
        active_auto = {p for p in auto_patches if p}
        p_args: list[str] = ["-f"] if force else []
        for p in excluded_patches:
            if p in active_auto:
                wpr(f"You can't exclude '{p}' patch as that's done by builder automatically")
            else:
                p_args.extend(("-d", p))
        for p in included_patches:
            if p in active_auto:
                wpr(f"You can't include '{p}' patch as that's done by builder automatically")
            else:
                p_args.extend(("-e", p))

        if exclusive:
            p_args.append("--exclusive")

        p_args.extend(extra_args)
        for auto_p in active_auto:
            p_args.extend(("-e", auto_p))
        p_args.extend(("--striplibs", _arch_to_libs(arch)))
        return p_args

    def patch(self, stock_apk: Path, output_apk: Path, patch_args: list[str]) -> None:
        tmp_files_dir = output_apk.parent / f"tmp-{output_apk.stem}"
        base_cmd = ["-jar", self.cli_jar, "patch", stock_apk, "--purge", "-o", output_apk, "-p", self.patches_mpp, "-t", tmp_files_dir]
        ks_args: list[str] = []

        if self.ks_path and (ks_pass := os.getenv("KEYSTORE_PASS", "")):
            ks_args = [f"--keystore={self.ks_path}", f"--keystore-entry-password={ks_pass}", f"--keystore-password={ks_pass}", "--signer=nvbangg", "--keystore-entry-alias=nvbangg"]
        elif Path("morphe.keystore").exists():
            ks_args = ["--keystore=morphe.keystore"]

        pr(" ".join(_redact_args(["java", *base_cmd, *ks_args, *patch_args])))
        try:
            _run_java(*base_cmd, *ks_args, *patch_args, capture=False)
        except PatcherError:
            output_apk.unlink(missing_ok=True)
            raise PatcherError(f"Patching '{stock_apk.name}' failed") from None

        if not output_apk.exists():
            raise PatcherError(f"Patching '{stock_apk.name}' failed - output not created")

    def check_signature(self, apk: Path, pkg_name: str) -> bool:
        if not (expected := self._signatures.get(pkg_name)):
            return True

        tmp_apk: Path | None = None
        try:
            with zipfile.ZipFile(apk, "r") as zf:
                names = zf.namelist()
                if inner := next((n for n in ("base.apk", f"{pkg_name}.apk") if n in names), None):
                    fd, tmp_path = tempfile.mkstemp(dir=TEMP_DIR, suffix=".apk")
                    tmp_apk = Path(tmp_path)
                    with os.fdopen(fd, "wb") as out_f, zf.open(inner) as in_f:
                        shutil.copyfileobj(in_f, out_f)
                    apk = tmp_apk
        except zipfile.BadZipFile:
            pass

        try:
            output = _run_java("--enable-native-access=ALL-UNNAMED", "-jar", self.apksigner, "verify", "--print-certs", apk)
            actual_hashes = [m.lower() for m in re.findall(r"SHA-256 digest:\s*(\S+)", output, re.I)]
            return bool(actual_hashes) and expected in actual_hashes
        except PatcherError:
            return False
        finally:
            if tmp_apk:
                tmp_apk.unlink(missing_ok=True)