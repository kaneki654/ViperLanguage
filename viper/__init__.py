# single source of truth is pyproject.toml; read the installed metadata, but
# fall back if it's missing or unreadable (bare checkout, patched metadata).
_FALLBACK_VERSION = "1.7.0b1"
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("viper-lang") or _FALLBACK_VERSION
except Exception:
    __version__ = _FALLBACK_VERSION
from .parser import parser
from .codegen import transpile
from .runtime import run_source
from .cli import main
__all__ = ["main", "parser", "transpile", "run_source"]
