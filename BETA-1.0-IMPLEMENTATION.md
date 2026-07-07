# Viper Beta 1.0 — Implementation Guide

Every change below was prototyped against your actual codebase and verified:
all 59 existing tests still pass, and each new feature was smoke-tested.
Apply them in order — later features build on earlier ones.

**What you get:**

1. `yield` / generators
2. `async` / `await` / `async for` / `async with`
3. Viper-to-Viper imports (`import mymodule` finds `mymodule.vp`)
4. Source-mapped tracebacks across files (new `viper/sourcemap.py`)
5. `viper build`, shebang support, PyPI-ready `pyproject.toml`
6. `viper fmt` (conservative v1 formatter)

---

## 1. `yield` / generators

### `viper/parser.py`

**Edit A** — in `?small_stmt`, add `yield_stmt` before `expr_stmt`:

```
               | nonlocal_stmt
               | yield_stmt
               | expr_stmt
```

**Edit B** — add the rule right after the `with_item` line:

```
    with_item: expr ("as" target)?

    yield_stmt: "yield" "from" expr                      -> yield_from_stmt
              | "yield" expr?
```

### `viper/codegen.py`

Add these two handlers right before the `# -- control flow` comment:

```python
    def _stmt_yield_stmt(self, node, indent):
        if node.children:
            self.emit(f"yield {self.gen_expr(node.children[0])}", indent, node.meta.line)
        else:
            self.emit("yield", indent, node.meta.line)

    def _stmt_yield_from_stmt(self, node, indent):
        self.emit(f"yield from {self.gen_expr(node.children[0])}", indent, node.meta.line)
```

### `viper/keywords.py`

In `KEYWORDS`, after the `"with", "assert", "global", "nonlocal",` line add:

```python
    # New in 1.0.0b1
    "yield", "async", "await",
```

**Known limitation (fine for beta):** `yield` is statement-only — `let x = yield`
(generator `.send()` protocol) isn't supported. Document it.

**Verified:**

```
fn counter(n):
    let i = 0
    while i < n:
        yield i
        i += 1

fn doubled(n):
    yield from counter(n)
    yield 99

print(list(doubled(3)))     # [0, 1, 2, 99]
```

---

## 2. `async` / `await`

Design note: you can't write `async_fn_def: decorator* "async" "fn" ...` as a
sibling of a bare `async for` rule — LALR(1) hits a shift/reduce conflict on
the `async` token (it can't decide whether to reduce the empty `decorator*`).
The fix is one `async_stmt` rule that branches *after* consuming `async`.

### `viper/parser.py`

**Edit A** — in `?compound_stmt`, add after `| with_stmt`:

```
                  | async_stmt
```

**Edit B** — add rules right after the new `yield_stmt` rule:

```
    async_stmt: decorator* "async" async_tail
    async_tail: "fn" NAME "(" param_list? ")" ("->" type)? ":" suite  -> async_fn_tail
              | "for" target_list "in" expr ":" suite else_clause?    -> async_for_tail
              | "with" with_item ("," with_item)* ":" suite           -> async_with_tail
```

**Edit C** — `await` as a prefix expression. Replace the `?factor` rule:

```
    ?factor: unary_op factor                             -> unary
           | "await" factor                              -> await_expr
           | power
```

### `viper/codegen.py`

**Edit A** — refactor `_stmt_fn_def` so async can reuse it. Replace everything
in `_stmt_fn_def` after the decorator-emitting loop (from `name = ch[0].value`
to the end of the method) with:

```python
        self._emit_fn(ch, indent, node.meta.line)

    def _emit_fn(self, ch, indent, line, keyword="def"):
        name = ch[0].value
        params, suite, ret_type = "", None, None
        for child in ch[1:]:
            if isinstance(child, Tree) and _rule(child) == "param_list":
                params = self.gen_params(child)
            elif isinstance(child, Tree) and _rule(child) == "type":
                ret_type = self.gen_type(child)
            elif isinstance(child, Tree) and _rule(child) == "suite":
                suite = child
        arrow = f" -> {ret_type}" if ret_type else ""
        self.emit(f"{keyword} {name}({params}){arrow}:", indent, line)
        self.gen_suite(suite, indent + 1)
```

**Edit B** — add the async statement handler right before the
`# -- params / types` comment:

```python
    def _stmt_async_stmt(self, node, indent):
        ch = list(node.children)
        decorators = []
        while ch and isinstance(ch[0], Tree) and _rule(ch[0]) == "decorator":
            decorators.append(ch.pop(0))
        tail = ch[0]
        r = _rule(tail)
        if r == "async_fn_tail":
            for dec in decorators:
                self.emit(self._gen_decorator(dec), indent, dec.meta.line)
            self._emit_fn(list(tail.children), indent, node.meta.line,
                          keyword="async def")
            return
        if decorators:
            raise ViperError(
                "decorators are only allowed on 'async fn', not on "
                "'async for' / 'async with'."
            )
        if r == "async_for_tail":
            target = self.gen_target_list(tail.children[0])
            iterable = self.gen_expr(tail.children[1])
            self.emit(f"async for {target} in {iterable}:", indent, node.meta.line)
            self.gen_suite(tail.children[2], indent + 1)
            for clause in tail.children[3:]:
                if isinstance(clause, Tree) and _rule(clause) == "else_clause":
                    self.emit("else:", indent, clause.meta.line)
                    self.gen_suite(clause.children[0], indent + 1)
        elif r == "async_with_tail":
            items, suite = [], None
            for c in tail.children:
                if isinstance(c, Tree) and _rule(c) == "with_item":
                    ex = self.gen_expr(c.children[0])
                    if len(c.children) == 2:
                        items.append(f"{ex} as {self.gen_target(c.children[1])}")
                    else:
                        items.append(ex)
                elif isinstance(c, Tree) and _rule(c) == "suite":
                    suite = c
            self.emit(f"async with {', '.join(items)}:", indent, node.meta.line)
            self.gen_suite(suite, indent + 1)
```

**Edit C** — add the await expression right before `_expr_power`:

```python
    def _expr_await_expr(self, node):
        return f"(await {self.gen_expr(node.children[0])})"
```

**Verified:**

```
import asyncio

async fn fetch(x):
    await asyncio.sleep(0)
    return x * 2

async fn main():
    let r = await fetch(21)      # await works in expressions
    print(f"async says {r}")     # -> async says 42

asyncio.run(main())
```

---

## 3. Source-mapped tracebacks (do this before imports — imports depend on it)

Today only the top frame of the entry file gets mapped. This adds a global
registry so *every* transpiled file maps, and renders a full Viper call stack.

### NEW FILE: `viper/sourcemap.py`

```python
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
```

### `viper/errors.py`

Replace the whole `format_runtime_error` function with:

```python
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
```

### `viper/runtime.py`

At the top of `run_source`, before the `transpile` call, register + install:

```python
def run_source(source: str, filename: str = "<viper>", namespace: dict | None = None) -> dict:
    from . import importer, sourcemap
    importer.install()
    py_source, line_map = transpile(source, filename)
    sourcemap.register(filename, source, line_map)
    ...  # rest unchanged
```

(`importer` is created in the next step — add both lines now, it all lands together.)

---

## 4. Viper-to-Viper imports

### NEW FILE: `viper/importer.py`

```python
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
```

### `viper/cli.py`

`run_file` must put the script's directory on `sys.path` so siblings resolve:

```python
def run_file(path: str) -> int:
    import os
    script_dir = os.path.dirname(os.path.abspath(path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        ...  # rest unchanged
```

**Verified** — `main.vp` doing `import mathutils` where `mathutils.vp` divides
by zero produces:

```
traceback (most recent call last):
  at /tmp/proj/main.vp:4
error: ZeroDivisionError: division by zero
 --> /tmp/proj/mathutils.vp:5:1
  |
5 |     return 1 / 0
  | ^
```

Cross-file, correct lines in both files. Python's `.vp`-aware `from mathutils
import triple` also works, since it goes through the same finder.

---

## 5. `viper build`, shebang, PyPI packaging

### `viper/cli.py`

**Edit A** — add above `_needs_continuation`:

```python
_BUILD_HEADER = """\
# Generated by Viper (viper build) — https://pypi.org/project/viper-lang/
# Source: {src}
# This file is self-contained: the Viper prelude is inlined below.
import pprint as _pprint
from pathlib import Path as _Path
pp = _pprint.pprint
def read_file(path, encoding="utf-8"): return _Path(path).read_text(encoding=encoding)
def write_file(path, text, encoding="utf-8"): return _Path(path).write_text(text, encoding=encoding)
def clamp(x, lo, hi): return lo if x < lo else hi if x > hi else x
# --- end prelude ---
"""


def build_file(path: str, output: str | None = None) -> int:
    from .codegen import transpile
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        print(f"error: cannot read {path!r}: {e}", file=sys.stderr)
        return 1
    try:
        py_source, _ = transpile(source, path)
    except ViperError as e:
        print(str(e), file=sys.stderr)
        return 1
    out = output or (path[:-3] + ".py" if path.endswith(".vp") else path + ".py")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_BUILD_HEADER.format(src=path))
        f.write(py_source)
    print(f"wrote {out}")
    return 0
```

**Edit B** — in `main()`, after the `repl` subparser line:

```python
    build_p = sub.add_parser("build", help="transpile a .vp file to a standalone .py file")
    build_p.add_argument("file")
    build_p.add_argument("-o", "--output", help="output path (default: <file>.py)")
```

**Edit C** — dispatch, after the `run` branch:

```python
    if args.command == "build":
        return build_file(args.file, args.output)
```

**Edit D** — shebang / direct-run support. Right before `args = ap.parse_args(argv)`:

```python
    # Shebang / direct-run support: `viper script.vp` == `viper run script.vp`
    raw = sys.argv[1:] if argv is None else list(argv)
    if raw and raw[0].endswith(".vp"):
        return run_file(raw[0])
```

Now `#!/usr/bin/env viper` works as the first line of a `.vp` file (it's
already ignored as a `#` comment).

### `pyproject.toml` — full replacement

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "viper-lang"
version = "1.0.0b1"
description = "Viper — a friendly language that transpiles to Python. Every Python module works out of the box."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "G0Ju.VBS", email = "kaneivbs@gmail.com" }]
keywords = ["language", "transpiler", "python", "compiler"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Compilers",
]
dependencies = ["lark>=1.1.0"]

[project.urls]
Homepage = "https://github.com/YOUR_USERNAME/ViperLanguage"
Issues = "https://github.com/YOUR_USERNAME/ViperLanguage/issues"

[project.scripts]
viper = "viper.cli:main"

[project.optional-dependencies]
lsp = ["pygls>=2.1,<3"]
test = ["pytest>=8"]

[tool.setuptools]
packages = ["viper"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Notes:

- `1.0.0b1` is PEP 440 for "Beta 1" (your current `0.0.3a` barely squeaks by
  as a version; `b1` is the proper beta marker). Ship `1.0.0` as the final.
- The joke license text will make PyPI reject or confuse tooling — pick a
  real one (MIT suggested above; add a `LICENSE` file with the MIT text).
- **Check the name is free first**: search https://pypi.org/project/viper-lang/ —
  if taken, fallbacks: `viperlang`, `viper-language`, `vp-lang`.

### Publishing (once)

```
pip install build twine
python -m build
twine upload dist/*        # needs a PyPI account + API token
```

After that, Windows/Mac/Linux users all just do `pip install viper-lang` and
get the `viper` command — `install.sh` becomes optional.

---

## 6. `viper fmt`

Design: a formatter that rewrites code can destroy comments/alignment. v1 is
deliberately conservative and provably safe — it refuses to write unless the
transpiled Python before/after is byte-identical.

### NEW FILE: `viper/fmt.py`

```python
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
    with open(path, "r", encoding="utf-8") as f:
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
```

### `viper/cli.py`

**Edit A** — add next to `build_file`:

```python
def fmt_files(paths: list[str], check: bool = False) -> int:
    from .fmt import format_file
    dirty = 0
    for path in paths:
        try:
            clean = format_file(path, check=check)
        except (OSError, ViperError) as e:
            print(str(e), file=sys.stderr)
            return 1
        if not clean:
            print(f"would reformat {path}")
            dirty += 1
    if check and dirty:
        print(f"{dirty} file(s) would be reformatted", file=sys.stderr)
        return 1
    return 0
```

**Edit B** — subparser (next to the `build` one):

```python
    fmt_p = sub.add_parser("fmt", help="format .vp files in place")
    fmt_p.add_argument("files", nargs="+")
    fmt_p.add_argument("--check", action="store_true",
                       help="don't write; exit 1 if anything would change")
```

**Edit C** — dispatch:

```python
    if args.command == "fmt":
        return fmt_files(args.files, check=args.check)
```

`viper fmt --check src/*.vp` in CI, `viper fmt src/*.vp` to fix.

---

## 7. Tests to add (`tests/test_beta10.py`)

```python
import subprocess
import sys
import textwrap

from viper.runtime import run_source
from viper.codegen import transpile


def test_yield_generator():
    ns = run_source(textwrap.dedent("""\
        fn counter(n):
            let i = 0
            while i < n:
                yield i
                i += 1
        let out = list(counter(3))
    """))
    assert ns["out"] == [0, 1, 2]


def test_yield_from():
    ns = run_source(textwrap.dedent("""\
        fn inner():
            yield 1
            yield 2
        fn outer():
            yield from inner()
            yield 3
        let out = list(outer())
    """))
    assert ns["out"] == [1, 2, 3]


def test_async_fn_await():
    ns = run_source(textwrap.dedent("""\
        import asyncio
        async fn double(x):
            await asyncio.sleep(0)
            return x * 2
        let out = asyncio.run(double(21))
    """))
    assert ns["out"] == 42


def test_async_fn_transpiles_to_async_def():
    py, _ = transpile("async fn f():\n    pass\n")
    assert "async def f():" in py


def test_vp_import(tmp_path):
    (tmp_path / "mod.vp").write_text("fn triple(x):\n    return x * 3\n")
    (tmp_path / "main.vp").write_text("import mod\nlet out = mod.triple(4)\n")
    r = subprocess.run([sys.executable, "-m", "viper.cli", "run",
                        str(tmp_path / "main.vp")], capture_output=True, text=True)
    assert r.returncode == 0


def test_build(tmp_path):
    src = tmp_path / "x.vp"
    src.write_text('print("hi")\n')
    r = subprocess.run([sys.executable, "-m", "viper.cli", "build", str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    out = tmp_path / "x.py"
    assert out.exists()
    r2 = subprocess.run([sys.executable, str(out)], capture_output=True, text=True)
    assert r2.stdout.strip() == "hi"


def test_fmt(tmp_path):
    f = tmp_path / "m.vp"
    f.write_text("let x = 1   \n\n\n\n\nprint(x)\n")
    r = subprocess.run([sys.executable, "-m", "viper.cli", "fmt", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert f.read_text() == "let x = 1\n\n\nprint(x)\n"
```

---

## 8. Don't forget (small stuff)

- `viper/keywords.py` — `yield`, `async`, `await` added (step 1). Keep
  `editor/syntax/viper.vim` in sync, per the comment in that file.
- Help topics: add `yield`, `async`, `import` entries to `viper/help.py`
  and mention them in `viper topics`.
- README: document the six new features + `pip install viper-lang`.
- Changelog: `BETA-1.0.0b1` section.

## Verification record (what I ran)

- Full existing suite: **59 passed** after all patches.
- Generators, `yield from`, `async fn`/`await` via `asyncio.run`: correct output.
- `.vp` importing `.vp`: works; a `ZeroDivisionError` raised in the imported
  module rendered a two-file Viper traceback with correct line numbers in both.
- `viper build` output ran standalone with no viper installed-dependency.
- `viper fmt` and `fmt --check` behaved as specified (idempotent, exit 1 on dirty).
- Shebang path (`viper file.vp` with no subcommand): runs the file.
