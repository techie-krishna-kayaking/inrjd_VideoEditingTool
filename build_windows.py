"""Build Windows standalone executable with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent
    entry = project_root / "main.py"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "iskcon-video-editor",
        "--onefile",
        str(entry),
    ]

    completed = subprocess.run(command, cwd=project_root, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
