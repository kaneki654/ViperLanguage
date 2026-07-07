"""Viper diagnostics — clearer than a raw Python traceback."""
from lark.exceptions import UnexpectedInput, UnexpectedToken, UnexpectedCharacters


class ViperError(Exception):
    """A Viper-level error meant to be shown to the user, not as a traceback."""


def _caret_block(source: str, line: int, column: int, filename: str, message: str,
                 hint: str | None = None) -> str:
    lines = source.splitlines()
    src_line = lines[line - 1] if 0 < line <= len(lines) else ""
    num = str(line)
    pad = " " * len(num)
    caret = " " * (max(column, 1) - 1) + "^"
    out = [
        f"error: {message}",
        f" --> {filename}:{line}:{column}",
        f"{pad} |",
        f"{num} | {src_line}",
        f"{pad} | {caret}",
    ]
    if hint:
        out.append(f"hint: {hint}")
    return "\n".join(out)


def format_parse_error(e: UnexpectedInput, source: str, filename: str) -> str:
    line = getattr(e, "line", 1) or 1
    column = getattr(e, "column", 1) or 1

    if isinstance(e, UnexpectedToken):
        expected = sorted(e.expected) if e.expected else []
        if e.token is not None and e.token.type in _TOKEN_NAMES:
            message = f"unexpected {_TOKEN_NAMES[e.token.type]}"
        elif e.token is None:
            message = "unexpected end of input"
        else:
            message = f"unexpected '{e.token.value}'"
        hint = None
        if expected:
            readable = ", ".join(_humanize(t) for t in expected[:8])
            hint = f"expected one of: {readable}"
        return _caret_block(source, line, column, filename, message, hint)

    if isinstance(e, UnexpectedCharacters):
        ch = source[e.pos_in_stream] if e.pos_in_stream < len(source) else "?"
        return _caret_block(source, line, column, filename,
                            f"unexpected character {ch!r}")

    return _caret_block(source, line, column, filename, str(e).splitlines()[0])


_TOKEN_NAMES = {
    "_NL": "newline",
    "INDENT": "indented block",
    "DEDENT": "end of block",
    "NAME": "a name",
    "NUMBER": "a number",
    "STRING": "a string",
    "RPAR": "')'",
    "LPAR": "'('",
    "LSQB": "'['",
    "RSQB": "']'",
    "LBRACE": "'{'",
    "RBRACE": "'}'",
    "COLON": "':'",
    "COMMA": "','",
    "EQUAL": "'='",
    "MINUS": "'-'",
    "PLUS": "'+'",
    "FN": "'fn'",
    "FALSE": "'False'",
    "TRUE": "'True'",
    "NONE": "'None'",
}


def _humanize(token_type: str) -> str:
    if token_type in _TOKEN_NAMES:
        return _TOKEN_NAMES[token_type]
    if token_type.isupper():
        return f"'{token_type.lower()}'"
    return token_type


def format_runtime_error(exc: BaseException, source: str, filename: str,
                         line_map: dict[int, int]) -> str:
    """Render a Viper traceback: every frame that lives in a transpiled .vp
    file is mapped back to its Viper line; the innermost one gets a caret."""
    import traceback
    from . import sourcemap

    frames = []
    for fr in traceback.extract_tb(exc.__traceback__):
        reg = sourcemap.lookup(fr.filename)
        if reg is None:
            if fr.filename == filename:
                reg = (source, line_map)
            else:
                continue  # internal / library frame — hide it
        vsrc, vmap = reg
        frames.append((fr.filename, sourcemap.map_line(vmap, fr.lineno),
                       fr.name, vsrc))

    etype = type(exc).__name__
    msg = str(exc)
    if not frames:
        return f"error: {etype}: {msg}"

    out = []
    if len(frames) > 1:
        out.append("traceback (most recent call last):")
        for fname, vline, func, _ in frames[:-1]:
            where = "" if func == "<module>" else f" in {func}"
            out.append(f"  at {fname}:{vline}{where}")
    fname, vline, func, vsrc = frames[-1]
    out.append(_caret_block(vsrc, vline, 1, fname, f"{etype}: {msg}"))
    return "\n".join(out)
