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
    """Map a Python exception from exec back to the Viper source line."""
    import traceback

    viper_line = None
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if frame.filename == filename:
            viper_line = line_map.get(frame.lineno, frame.lineno)
            break

    etype = type(exc).__name__
    msg = str(exc)
    if viper_line is not None:
        return _caret_block(source, viper_line, 1, filename, f"{etype}: {msg}")
    return f"error: {etype}: {msg}"
