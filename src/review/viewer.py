"""OS default viewer integration for review engine."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_in_default_viewer(path: Path) -> bool:
    """Open media in default OS viewer and wait for user return when possible."""
    try:
        if sys.platform == "darwin":
            completed = subprocess.run(["open", "-W", str(path)], check=False)
            return completed.returncode == 0

        if sys.platform.startswith("win"):
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Start-Process -FilePath '{str(path)}' -Wait",
            ]
            completed = subprocess.run(command, check=False)
            return completed.returncode == 0

        completed = subprocess.run(["xdg-open", str(path)], check=False)
        return completed.returncode == 0
    except Exception:
        return False
