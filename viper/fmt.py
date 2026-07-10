"""viper fmt — a conservative, always-safe formatter (v1).

What it does: strips trailing whitespace, converts leading tabs to 4 spaces,
collapses 3+ blank lines to 2, and guarantees exactly one trailing newline.
It refuses to write anything unless (a) the result still parses and (b) the
transpiled Python of before/after is byte-identical — so it can never change
what a program does.
"""
import re

from .codegen import transpile
from .errors import ViperError


def format_source(source: str) -> str:
    lines = []
    for line in source.splitlines():
        # leading tabs -> 4 spaces (only in the indentation, not inside strings)
        m = re.match(r"[\t ]*", line)
        indent = m.group(0).replace("\t", "    ")
        lines.append(indent + line[m.end():].rstrip())
    out = "\n".join(lines)
    out = re.sub(r"\n{4,}", "\n\n\n", out)          # max 2 consecutive blanks
    out = out.strip("\n") + "\n" if out.strip() else ""
    return out


def format_file(path: str, check: bool = False) -> bool:
    """Returns True when the file is (or now is) clean.

    check=True: report without writing (exit code for CI).
    """
    with open(path, "r", encoding="utf-8-sig") as f:   # tolerate a BOM
        original = f.read()

    formatted = format_source(original)
    if formatted == original:
        return True

    # Safety gate: formatting must not change the transpiled program.
    before, _ = transpile(original, path)
    after, _ = transpile(formatted, path)
    if before != after:
        raise ViperError(
            f"fmt aborted for {path!r}: formatting would change the program.\n"
            "hint: this is a formatter bug — please report it. File left untouched."
        )

    if check:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(formatted)
    return True
