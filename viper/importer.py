"""Import .vp files with a plain `import` statement.

Installs a MetaPathFinder so `import utils` finds utils.vp on sys.path
(the running script's directory is added by the CLI). Transpiles on import,
registers a sourcemap so runtime errors point at .vp lines, and injects the
Viper prelude (pp, read_file, ...) into the module namespace.
"""
import importlib.abc
import importlib.util
import os
import sys


class ViperLoader(importlib.abc.Loader):
    def __init__(self, path: str):
        self.path = path

    def create_module(self, spec):
        return None  # default module creation

    def exec_module(self, module):
        from .codegen import transpile
        from .runtime import _PRELUDE
        from . import sourcemap

        with open(self.path, "r", encoding="utf-8") as f:
            source = f.read()
        py_source, line_map = transpile(source, self.path)
        sourcemap.register(self.path, source, line_map)
        module.__dict__.update(_PRELUDE)
        code = compile(py_source, self.path, "exec")
        exec(code, module.__dict__)


class ViperFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        name = fullname.rpartition(".")[2]
        search = path if path is not None else sys.path
        for entry in search:
            candidate = os.path.join(entry or ".", name + ".vp")
            if os.path.isfile(candidate):
                return importlib.util.spec_from_loader(
                    fullname, ViperLoader(candidate), origin=candidate)
        return None


def install() -> None:
    if not any(isinstance(f, ViperFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, ViperFinder())
