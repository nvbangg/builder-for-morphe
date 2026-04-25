import json
import re
from pathlib import Path

from src.core.config import load_toml, parse_config, parse_app_entries
from src.core.logger import abort, epr

_RE_CLI_START = re.compile(r"^>.*CLI:")
_RE_CHANGELOG_END = re.compile(r"^\[.*Changelog\]")
CONFIG_PATH: Path = Path("config.toml")


def get_matrix(source: str) -> None:
    try:
        data: dict[str, object] = load_toml(CONFIG_PATH)
    except FileNotFoundError:
        abort(f"Config file not found: '{CONFIG_PATH}'")
    except ValueError as exc:
        abort(str(exc))

    main_cfg = parse_config(data)
    source_lower = source.lower()
    include: list[dict[str, str]] = []

    for entry in parse_app_entries(data, main_cfg):
        if not entry.enabled or entry.brand.lower() != source_lower:
            continue

        if entry.arch == "both":
            include.extend(({"id": entry.table, "arch": "arm64-v8a"}, {"id": entry.table, "arch": "arm-v7a"}))
        else:
            include.append({"id": entry.table})

    if not include:
        abort(f"No apps found for patch source '{source}'")

    print(json.dumps({"include": include}, ensure_ascii=False))

def combine_logs(logs_dir: Path | str) -> None:
    if not (logs := sorted(Path(logs_dir).rglob("build.md"))):
        return

    green_lines: list[str] = []
    microg_line: str = ""
    collected: list[str] = []

    for log in logs:
        capturing = False

        with log.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("🟢"):
                    green_lines.append(line)
                elif not microg_line and line.startswith("-") and "MicroG" in line:
                    microg_line = line

                if _RE_CLI_START.match(line):
                    capturing = True
                elif _RE_CHANGELOG_END.match(line):
                    collected.append(line)
                    collected.append("")
                    capturing = False
                    continue

                if capturing:
                    collected.append(line)

        if capturing:
            epr(f"Warning: unclosed CLI section in '{log}' - changelog end marker not found")

    if green_lines:
        print("\n".join(green_lines))
        print()
    if microg_line:
        print(microg_line, end="\n\n")
    if unique := list(dict.fromkeys(collected)):
        print("\n".join(unique))
