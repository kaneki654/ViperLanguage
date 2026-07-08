# single source of truth is pyproject.toml; read the installed metadata
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("viper-lang")
except Exception:                       # running from a bare checkout
    __version__ = "1.3.0b1"
from .parser import parser
from .codegen import transpile
from .runtime import run_source
from .cli import main
__all__ = ["main", "parser", "transpile", "run_source"]
