"""Tiny ANSI helpers that degrade to plain text when stdout isn't a terminal."""
import sys


def supports_ansi() -> bool:
    return sys.stdout.isatty()


def header(text: str) -> str:
    return f"\033[1;36m{text}\033[0m" if supports_ansi() else text


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if supports_ansi() else text


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if supports_ansi() else text
