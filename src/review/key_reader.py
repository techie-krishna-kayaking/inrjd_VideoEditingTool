"""Low-level single-key reader for interactive CLI workflows."""

from __future__ import annotations

import sys


def read_key() -> str:
    """Read one key press and normalize special keys."""
    if sys.platform.startswith("win"):
        return _read_key_windows()
    return _read_key_posix()


def _read_key_windows() -> str:
    """Read one key on Windows using msvcrt."""
    import msvcrt

    key = msvcrt.getwch()
    if key in {"\r", "\n"}:
        return "enter"
    if key == " ":
        return " "
    if key == "\x1b":
        return "esc"

    if key in {"\x00", "\xe0"}:
        special = msvcrt.getwch()
        mapping = {
            "H": "up",
            "P": "down",
            "K": "left",
            "M": "right",
        }
        return mapping.get(special, special)

    return key


def _read_key_posix() -> str:
    """Read one key on POSIX systems using termios/tty."""
    import termios
    import tty

    stream = sys.stdin
    fd = stream.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = stream.read(1)
        if first in {"\r", "\n"}:
            return "enter"
        if first == " ":
            return " "
        if first == "\x1b":
            second = stream.read(1)
            if second != "[":
                return "esc"
            third = stream.read(1)
            mapping = {
                "A": "up",
                "B": "down",
                "C": "right",
                "D": "left",
            }
            return mapping.get(third, "esc")
        return first
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
