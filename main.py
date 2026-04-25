import os
import shutil
import signal
import sys
from pathlib import Path

from src.core.builder import run_build
from src.core.config import BUILD_DIR, TEMP_DIR, VALID_ARCHES, load_toml, parse_config
from src.core.gh_utils import combine_logs, get_matrix
from src.core.logger import BuildAbortError, abort, epr, pr
from src.core.network import NetworkError, NetworkManager
from src.core.patcher import PatcherError
from src.core.prebuilts import PrebuiltsError
from src.scrapers.apkmirror import APKMirrorError
from src.scrapers.archive import ArchiveError
from src.scrapers.uptodown import UptodownError

CONFIG_PATH: Path = Path("config.toml")
_KNOWN_ERRORS = (NetworkError, PrebuiltsError, PatcherError, APKMirrorError, ArchiveError, UptodownError)

def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def _build(target_app: str | None = None, arch_override: str | None = None) -> int:
    try:
        data = load_toml(CONFIG_PATH)
    except FileNotFoundError:
        abort(f"Config file not found: '{CONFIG_PATH}'")
    except ValueError as exc:
        abort(str(exc))

    main_cfg = parse_config(data)
    pr(f"Loaded config '{CONFIG_PATH}'")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    for cl in TEMP_DIR.glob("*/changelog.md"):
        cl.write_text("", encoding="utf-8")
    Path("build.md").write_text("", encoding="utf-8")

    with NetworkManager() as net:
        success = run_build(data, main_cfg, net, target_app=target_app, arch_override=arch_override)

    return 0 if success else 1

def _clean() -> int:
    for directory in (TEMP_DIR, BUILD_DIR):
        if directory.exists():
            shutil.rmtree(directory)
            pr(f"Removed '{directory}'")
        else:
            pr(f"'{directory}' already clean")
    if (build_md := Path("build.md")).exists():
        build_md.unlink()
        pr("Removed 'build.md'")
    return 0

def _sigint_handler(sig: int, frame: object) -> None:
    epr("Interrupted by user")
    for tmp in TEMP_DIR.rglob("tmp.*"):
        shutil.rmtree(tmp, ignore_errors=True)
    os._exit(130)

def _require_ci(cmd: str) -> None:
    if os.getenv("GITHUB_ACTIONS") != "true":
        epr(f"'{cmd}' is only available in GitHub Actions")
        sys.exit(1)

def main() -> None:
    signal.signal(signal.SIGINT, _sigint_handler)

    _load_dotenv()
    argv = sys.argv[1:]
    try:
        match argv:
            case []:
                sys.exit(_build())
            case ["get-matrix", *source]:
                _require_ci("get-matrix")
                get_matrix(source[0] if source else "morphe")
            case ["clean"]:
                sys.exit(_clean())
            case ["combine-logs", *dir]:
                _require_ci("combine-logs")
                combine_logs(logs_dir=Path(dir[0] if dir else "logs"))
            case [target, *rest] if not rest or rest[0] in VALID_ARCHES:
                sys.exit(_build(target_app=target, arch_override=rest[0] if rest else None))
            case [_, arch]:
                epr(f"Unknown arch '{arch}'. Valid: {', '.join(sorted(VALID_ARCHES))}")
                sys.exit(1)
            case _:
                epr(f"Unknown command: {' '.join(argv)}")
                epr("Usage: main.py [target] [arch] | clean")
                sys.exit(1)
    except BuildAbortError:
        sys.exit(1)
    except _KNOWN_ERRORS as exc:
        epr(str(exc))
        sys.exit(1)

if __name__ == "__main__":
    main()