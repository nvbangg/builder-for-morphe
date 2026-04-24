import os
import re
import shlex
import subprocess
import threading
import zipfile
from pathlib import Path

from src.core.config import TEMP_DIR
from src.core.logger import pr, wpr
from src.core.prebuilts import get_highest_ver


class PatcherError(Exception):
    pass

def _parse_args(s: str) -> list[str]:
    try:
        return shlex.split(s)
    except ValueError as e:
        raise PatcherError(f"Error parsing patch arguments: {e}")

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
    if block_match := re.search(rf"Name: {re.escape(patch_name)}\n.*?(?=\n\n|\Z)", output, re.DOTALL | re.IGNORECASE):
        if vers_match := re.search(r"Compatible versions:\s*\n(.*?)$", block_match.group(0), re.DOTALL):
            return [v.strip() for v in vers_match.group(1).splitlines() if v.strip()]
    return []

def _parse_versions_output(output: str) -> list[str]:
    matches = [m for line in output.splitlines() if (m := re.search(r"^(.*?)\s*\((\d+)\s+patch", line.strip()))]
    if not matches:
        return []
    target = matches[0].group(2)
    return [m.group(1).strip() for m in matches if m.group(2) == target and m.group(1).strip()]

class PatcherCLI:
    def __init__(self, cli_jar: Path, patches_mpp: Path, apksigner: Path, ks_path: Path | None = None, sig_file: Path = Path("sig.txt")) -> None:
        self.cli_jar = cli_jar
        self.patches_mpp = patches_mpp
        self.apksigner = apksigner
        self.ks_path = ks_path
        self._sig_content: str = sig_file.read_text(encoding="utf-8") if sig_file.exists() else ""

    def list_patches(self, pkg_name: str) -> str:
        return _run_java("-jar", self.cli_jar, "list-patches", "--patches", self.patches_mpp, "-f", pkg_name, "-v", "-p")

    def list_versions(self, pkg_name: str) -> str:
        return _run_java("-jar", self.cli_jar, "list-versions", self.patches_mpp, "-f", pkg_name)

    def get_last_supported_version(self, list_patches_output: str, pkg_name: str, included_patches: list[str]) -> str | None:
        if included_patches:
            all_vers = [v for p in included_patches for v in _parse_patch_block(list_patches_output, p)]
            if all_vers:
                return get_highest_ver(all_vers)

        versions_output = self.list_versions(pkg_name)
        if "Any" in versions_output:
            return None
        if not (versions := _parse_versions_output(versions_output)):
            raise PatcherError(f"No patches found for '{pkg_name}' in patches '{self.patches_mpp}'")
        return get_highest_ver(versions)

    def resolve_auto_patches(self, list_patches_output: str) -> tuple[str, str]:
        lines = list_patches_output.splitlines()
        microg = next((L.removeprefix("Name: ") for L in lines if re.match(r"^Name: .*(gmscore|microg)", L, re.I)), "")
        disable_psu = next((L.removeprefix("Name: ") for L in lines if re.match(r"^Name: .*disable play store updates", L, re.I)), "")
        return microg, disable_psu

    def build_patch_args(self, included_patches: list[str], excluded_patches: list[str], exclusive: bool, extra_args: str, arch: str, auto_patches: list[str], force: bool = False) -> list[str]:
        p_args: list[str] = []
        if force:
            p_args.append("-f")
        for p in excluded_patches:
            p_args += ["-d", p]
        for p in included_patches:
            p_args += ["-e", p]
        if exclusive:
            p_args.append("--exclusive")

        for auto_p in (p for p in auto_patches if p):
            filtered: list[str] = []
            it = iter(range(len(p_args)))
            for i in it:
                arg = p_args[i]
                if arg in ("-e", "-d") and i + 1 < len(p_args):
                    nxt = p_args[i + 1]
                    if nxt == auto_p:
                        wpr(f"You can't include/exclude '{auto_p}' patch as that's done by builder automatically")
                        next(it)
                        continue
                filtered.append(arg)
            p_args = filtered

        if extra_args.strip():
            p_args += shlex.split(extra_args)

        final_args = list(p_args)
        for auto_p in (p for p in auto_patches if p):
            final_args += ["-e", auto_p]
        final_args += ["--striplibs", _arch_to_libs(arch)]
        return final_args

    def patch(self, stock_apk: Path, output_apk: Path, patch_args: list[str]) -> None:
        base_cmd = ["-jar", self.cli_jar, "patch", stock_apk, "--purge", "-o", output_apk, "-p", self.patches_mpp]
        ks_args: list[str] = []

        if self.ks_path and (ks_pass := os.getenv("KEYSTORE_PASS", "")):
            ks_args = [f"--keystore={self.ks_path}", f"--keystore-entry-password={ks_pass}", f"--keystore-password={ks_pass}", "--signer=krvstek", "--keystore-entry-alias=krvstek"]
        elif Path("morphe.keystore").exists():
            ks_args = ["--keystore=morphe.keystore"]

        pr(" ".join(str(a) for a in ["java", *base_cmd, *ks_args, *patch_args]))
        try:
            _run_java(*base_cmd, *ks_args, *patch_args, capture=False)
        except PatcherError:
            output_apk.unlink(missing_ok=True)
            raise PatcherError(f"Patching '{stock_apk.name}' failed")

        if not output_apk.exists():
            raise PatcherError(f"Patching '{stock_apk.name}' failed - output not created")

    def check_signature(self, apk: Path, pkg_name: str) -> bool:
        if not self._sig_content or pkg_name not in self._sig_content:
            return True

        expected = next((line.split()[0].lower() for line in self._sig_content.splitlines() if line.endswith(pkg_name)), None)
        if expected is None:
            return True

        tmp_apk: Path | None = None
        try:
            with zipfile.ZipFile(apk, "r") as zf:
                names = zf.namelist()
                if inner := next((n for n in ("base.apk", f"{pkg_name}.apk") if n in names), None):
                    tmp_apk = TEMP_DIR / f"tmp_{os.getpid()}_{threading.get_ident()}_base.apk"
                    tmp_apk.write_bytes(zf.read(inner))
                    apk = tmp_apk
        except zipfile.BadZipFile:
            pass

        try:
            output = _run_java("--enable-native-access=ALL-UNNAMED", "-jar", self.apksigner, "verify", "--print-certs", apk)
            actual_hashes = [line.split()[-1].lower() for line in output.splitlines() if "SHA-256 digest:" in line]
            return bool(actual_hashes) and expected in actual_hashes
        except PatcherError:
            return False
        finally:
            if tmp_apk:
                tmp_apk.unlink(missing_ok=True)
