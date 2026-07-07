"""Global registry of every transpiled .vp file.

Lets format_runtime_error map Python tracebacks back to Viper source in ANY
module, not just the entry file. The importer and runtime both register here.
"""

_REGISTRY: dict[str, tuple[str, dict[int, int]]] = {}


def register(filename: str, source: str, line_map: dict[int, int]) -> None:
    _REGISTRY[filename] = (source, line_map)


def lookup(filename: str) -> tuple[str, dict[int, int]] | None:
    return _REGISTRY.get(filename)


def map_line(line_map: dict[int, int], py_line: int) -> int:
    """Exact match, else the nearest emitted line above (e.g. inside a suite)."""
    if py_line in line_map:
        return line_map[py_line]
    best = None
    for k in line_map:
        if k <= py_line and (best is None or k > best):
            best = k
    return line_map[best] if best is not None else py_line
