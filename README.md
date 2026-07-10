# Viper Language

**The batteries-included scripting language.** Write `.vp`, run Python — but the
automation and security glue that takes five imports and a dozen lines in Python
is a one-liner in Viper.

```
# no imports needed — this is the whole program
let body = http_get("https://example.com")
print(sha256(body))
print(hexdump(unb64("ZmxhZ3tva30=")))
```

Viper transpiles to Python, so every Python module still works out of the box —
`import math`, `import os`, anything. What Viper adds on top is the thing Python
makes you assemble yourself every time: a curated standard library that's always
in scope (hashing, encoding, HMAC, HTTP, shell, JSON, files), a left-to-right
pipe operator (`|>`), clearer error messages, and footgun guards.

**One-liners, too:**

```
viper -c 'print(sha256("hunter2"))'
echo '{"a":1}' | viper -
```

### Why Viper instead of Python?

Three things Python won't do for you:

1. **Batteries included.** The 20-line-with-5-imports automation/security script
   is the common case, and in Viper it's 5 lines with none — hashing, encoding,
   HTTP, shell, JSON, XOR, and URL parsing are always in scope, and `|>` makes
   pipelines read left-to-right.
2. **Annotations that mean something.** `let x: int = "hello"` is a *transpile-time
   error* in Viper — Python happily runs that lie. Viper checks what it can know
   for certain and stays quiet when it can't, so types are a real guardrail.
3. **Real constants.** `const K = 1` can never be reassigned — a *compile-time*
   guarantee. Python has no such thing (its "constants" are ALL-CAPS on the honor
   system).

Note the honest ceiling: Viper transpiles *to* Python, so it can't be faster
than Python or escape the GIL — it inherits the runtime. It wins on *ergonomics
and safety for small programs*, not raw capability. If you're building a large
application, use Python. Viper is sharpest for pipelines, CTF tooling, and ops
glue — where you want to move fast with a guardrail or two.

---

## Changelog

### BETA-1.7.0b1 *(current)* — built-in linter

Viper now ships a linter — the kind of thing Python makes you install `flake8`
for. It rides on the same static analysis as the type checker.

- **Unused-import warnings** — `import os` you never use is flagged. The scan is
  whole-source and textual, so a name used only inside an f-string still counts
  as used: it never cries wolf on a real use.
- **`viper lint file.vp`** — reports type errors *and* lint warnings, flake8-style
  (`file.vp:3:1: warning: 'os' is imported but never used`). Errors exit 1;
  warnings don't. Wire it into CI.
- **Live in the editor** — warnings show as yellow squiggles, errors as red, via
  the same LSP. Warnings never block `run`/`build`. +11 tests (202 → 213).

### BETA-1.6.0b1 — call into C

Viper can now **drop down to C** ergonomically, when you need the metal (a fast
native crypto routine, a raw syscall, an existing C library). Built on `ctypes`,
so it needs no compiler and no dependency — Viper inherits Python's C interop.

- **`clib(name)`** loads a C shared library (`.dll`/`.so`/`.dylib` or a system
  name like `"msvcrt"`). Two ways to call:
  - quick: `lib.SomeFunc(a, b)` — int in/out, Python `str` auto-encoded;
  - typed: `f = lib.func("name", "double", ["int"])` then `f(3)` — declared
    signature with friendly type names (`int str double ptr size_t` …), `str`
    args auto-encoded and `str` returns decoded.
- **`abi="win"`** for Win32 stdcall APIs: `clib("kernel32", abi="win").GetTickCount()`.
- New [examples/ffi.vp](examples/ffi.vp) (cross-platform), `viper help ffi`, +8 tests.

**Honest scope:** this is *call into C*, not *become C*. You get C libraries;
you don't get manual memory, pointers, or native speed for Viper code itself —
that's still Python's runtime underneath. It's the right tool when the metal
lives in a C library you can call, which covers most "I need C for this" cases
in security and systems glue.

### BETA-1.5.0b1 — const + more batteries

**`const` — real, compile-time-enforced immutability** (something Python can't
do):

- `const K = 1` binds a name once. Reassigning it (`K = 2`), aug-assigning
  (`K += 1`), rebinding with `let`, or re-declaring `const` is a **transpile-time
  error**, caught by `run`/`build` and shown live in the editor.
- It freezes the *name*, not the object — `const xs = []` still allows
  `xs.append(1)`. `const` values are type-checked and inferred just like `let`,
  and show as `const` in completion and hover.

**More stdlib** (crypto / web, for the CTF and pentest niche):

- `xor(data, key)` — repeating-key XOR, the classic CTF crypto primitive.
- `url_parse(url)` — split a URL into scheme/host/port/path/query/fragment.
- `qs_parse` / `qs_build` — query strings ↔ dicts.
- `json_get(obj, "a.b.0", default)` — safe nested access by dotted path.

**Honesty note in the docs:** a transpiler cannot beat Python at everything —
it *is* Python at runtime. Viper's edge is ergonomics and static safety for
small scripts, not speed or new runtime powers. The README now says so plainly.

**Tests:** +17 (const enforcement across scopes, object-mutation-still-allowed,
type-flow, editor labelling; crypto/web helpers). 193 total.

### BETA-1.4.0b1 — types that mean something

Viper's type annotations stop being decoration. `let x: int = "hello"` is now a
**transpile-time error** — caught by `viper run`, `viper build`, and live in the
editor — not a silent lie that blows up later (or never).

**Type checking:**

- **Checked `let` annotations** — `let n: int = "no"` fails to compile, with a
  caret-pointed error just like a syntax error. Widening is respected
  (`let x: float = 5` is fine); `bool`/`int` compatibility follows Python.
- **Checked return types** — `fn f() -> int: return "no"` is an error too.
- **Type inference flows** through literals, bytes/raw strings, `True/False/None`,
  list/dict/set/tuple, typed variables and parameters, builtin calls
  (`len()` → int), the whole stdlib prelude (`sha256()` → str), and your own
  `fn ... -> T`. So `let d = sha256(x)` then `let n: int = d` is caught.
- **Conservative by design** — Viper only flags a mismatch when the value's type
  is *definitely* known and *definitely* incompatible. Custom classes (which
  might subclass the annotation), arithmetic, and unknown calls are left alone.
  A checker that cries wolf is worse than none; false positives are the enemy.
- **Live in the editor** — mismatches show as red squiggles as you type, via the
  same LSP that powers completion.
- **New module** `viper/typecheck.py` (pure, tree-based) + **38 tests**.

### BETA-1.3.0b1 — batteries included

Viper gets a real standard library and the ergonomics to be a language you reach
for. Everything below is backed by the Python standard library — no third-party
dependencies, cross-platform.

**Standard prelude** (no import needed, in every run — `viper help std`):

- **Hashing** — `sha256` `sha1` `sha512` `md5` `hmac256` `file_sha256`
- **Encoding** — `b64` `unb64` `to_hex` `from_hex` `url_quote` `url_unquote`
- **Randomness** — `rand_token` `rand_int` `uuid4` (crypto-strong)
- **HTTP** — `http_get` `http_post` `http_status` `download`
- **Shell** — `sh` `sh_out` `which`
- **JSON / files** — `json_parse` `json_str` `read_json` `write_json` `read_lines` `ls` `exists` `env`
- **Data** — `hexdump` `sleep` `now` `port_open`

Each one shows its signature and docs on hover and in completion. Security helpers
(hashing, HMAC verify, hexdump, checksums, a single TCP reachability check) are the
ordinary plumbing of CTF challenges, authorized testing, and defensive tooling.

**Language:**

- **Bytes and raw string literals** — `b"\x00\xff"` and `r"\d+"` now parse and pass
  straight through to Python. Essential for binary and security work.

**CLI:**

- **`viper -c CODE`** runs a snippet; **`viper -`** runs Viper from stdin. Viper is
  now a first-class tool for one-off scripts and pipelines.
- **`viper help <name>`** documents any stdlib helper, e.g. `viper help hmac256`.

**Tooling:**

- **`viper build`** output is still fully self-contained — the stdlib helpers'
  actual source is inlined, so a built `.py` needs no `viper-lang` install.
- **New examples** — `examples/security.vp` (offline CTF helpers) and
  `examples/automation.vp` (checksum-a-folder glue script).
- **34 new tests** covering the stdlib, bytes/raw literals, self-contained builds,
  the `-c` CLI, and editor awareness of the prelude.

**Roadmap (the next reason to switch):** make `let` and type annotations *mean*
something — single-assignment enforcement and light type checking at transpile
time, so `let x: int` becomes a guarantee, not decoration. The analysis engine
that already powers completion will power the checker.

### BETA-1.2.0b1 — Python-grade completions

A rewritten analysis engine: per-keystroke caching (warm completions answer in
well under a millisecond), Pylance-style ranking, type inference for `let`
bindings and `self.`, auto-import completions from workspace `.vp` files, go-to-
definition, and a document outline. Completions keep working even while the
current line doesn't parse.

### BETA-1.1.0b1

Python-grade editor intelligence. Viper autocompletion in VS Code and Cursor now behaves like Python's, not like a static word list.

**Editor (VS Code + Cursor):**

- **Bundled LSP client** — the extension now launches `viper --lsp` automatically for `.vp` files (single-file bundle, no npm install needed). If Viper isn't on PATH it shows a friendly fix-it message instead of failing silently. New setting: `viper.lspPath`.
- **Smart completions** — real symbols from your file (every `fn` with its full signature, classes, `let` bindings, parameters when the cursor is inside their function), not just keywords.
- **Dot-completion** — `math.` lists the real members of `math` with signatures and docs; works through aliases (`import collections as coll` → `coll.` works) and for **Viper modules** (`import utils` → `utils.` lists what utils.vp defines — parsed, never executed).
- **Context awareness** — `import `/`from ` complete module names (stdlib + workspace `.vp` files), `from math import ` completes members, `async ` suggests only `fn`/`for`/`with`, and nothing pops up inside strings or comments.
- **Signature help** — parameter hints with the active argument highlighted while typing a call, for Viper functions, classes (`Point(` shows `__init__`'s params), builtins, and imported Python functions.
- **Hover docs** — signature + docstring for the symbol under the cursor; keywords point at `viper help <topic>`.
- **Broken-buffer tolerance** — mid-keystroke code that doesn't parse still completes, using the cursor-line-blanked retry or the last good analysis.

**Language:**

- **`import x as y` / `from m import a as b`** — import aliases now parse and transpile (they were missing; dot-completion made the gap obvious).

**Internals:**

- New `viper/analysis.py` — all editor intelligence as a pure, LSP-free module; `viper/lsp.py` is now a thin adapter over it.
- **16 new tests**, including a true end-to-end test that spawns `viper --lsp` and speaks LSP over stdio.

**1.1.1 follow-up (the vanished-completions fix):**

- **`viper doctor`** — one command that checks Python, lark, pygls, PATH, and the editor extensions, and prints exactly what to fix.
- **Extension fallback completions** — if the language server can't start (e.g. pygls missing), the extension now registers built-in keyword/builtin/buffer-word suggestions and offers a one-click "Run viper doctor" — completions can never fully disappear again.
- **Hardened installer** — `install.ps1` force-installs pygls, cleans up old extension copies, and finishes by running `viper doctor`.

### BETA-1.0.0b1

The first Beta. Viper graduates from a single-file toy to a language you can build real projects in: multi-file programs, generators, async, a compiler command, a formatter, and error messages that stay in Viper-land even across files.

**Language:**

- **Generators — `yield` and `yield from`** — any `fn` containing `yield` becomes a generator, exactly like Python. `yield from` delegates to another generator. (Limitation: `yield` is statement-only for now, so the `let x = yield` / `.send()` protocol isn't supported yet.)
- **Async — `async fn`, `await`, `async for`, `async with`** — the full asyncio ecosystem now works from Viper. `await` is an expression, so `let r = await fetch(url)` works anywhere an expression does. Decorators work on `async fn`.

**Multi-file programs:**

- **Viper-to-Viper imports** — `import utils` now finds `utils.vp` next to your script (or anywhere on `sys.path`), transpiles it on the fly, and caches it like a normal module. `from utils import helper` works too. Split your project into as many `.vp` files as you like.
- **Cross-file source-mapped tracebacks** — a runtime error anywhere in a multi-file program prints a full *Viper* call stack: every frame is mapped back to its `.vp` file and line, the innermost frame gets the caret block, and internal Python machinery is hidden.

**Tooling:**

- **`viper build file.vp`** — transpiles to a standalone `file.py` (the prelude is inlined, so the output runs on any machine with plain Python — no Viper install needed). `-o out.py` picks the destination.
- **`viper fmt file.vp ...`** — conservative formatter: strips trailing whitespace, converts leading tabs to 4 spaces, collapses 3+ blank lines, guarantees a single trailing newline. It refuses to write unless the transpiled Python is byte-identical before and after, so it can never change what your program does. `--check` reports without writing (exit 1 if dirty — ideal for CI).
- **Shebang / direct run** — `viper script.vp` now works without the `run` subcommand, so `#!/usr/bin/env viper` works as the first line of an executable `.vp` file.
- **PyPI-ready packaging** — proper PEP 440 beta version, MIT license, classifiers; `pip install viper-lang` gives everyone (including Windows) the `viper` command with no `install.sh`.
- **7 new tests** covering generators, async, `.vp` imports, `build`, and `fmt`.

### ALPHA-0.0.3

Python parity, Viper-only superpowers, and a real test suite.

**Python parity — these now parse and run:**

- **Tuple & starred unpacking** — `let (a, b) = pair`, `let head, *tail = xs`
- **Chained assignment** — `a = b = 1`
- **`with` statement** — `with open("f") as f:`
- **`assert`** — `assert x > 0, "must be positive"`
- **`global` / `nonlocal`**
- **`raise … from`** — exception chaining
- **Dict / set / generator comprehensions** — `{k: v for …}`, `{x for …}`, `(x for …)`
- **Bitwise & shift operators** — `|`, `^`, `&`, `<<`, `>>` (full Python precedence)
- **Walrus `:=`** — in `if` / `elif` / `while` conditions and parenthesized expressions
- **Number literals** — hex `0xff`, octal `0o17`, binary `0b1010`, underscores `1_000_000`, scientific `1e9`
- **Single-quoted strings** — `'hi'` and `f'{x}'` (double quotes still work too)

**Viper superpowers:**

- **Pipe placeholder `_`** — pipe into any argument: `3.14159 |> round(_, 2)` becomes `round(3.14159, 2)`
- **Built-in stdlib prelude** (no import needed): `pp` (pretty-print), `read_file(path)`, `write_file(path, text)`, `clamp(x, lo, hi)`
- **More footgun guards** — bare `except:`, `== None` / `!= None`, and `let` shadowing a builtin are all rejected with a helpful hint

**Tooling:**

- **Full pytest suite** — `pip install -e ".[test]"` then `pytest`
- New help topics: `with`, `assert`, `comprehension`, `walrus`, `bitwise`, `unpack`, `prelude`, `global`, `nonlocal`, `raise`

### ALPHA-0.0.2-1

Added in this upgrade (on top of 0.0.2):

- **f-strings** — `f"hello, {name}!"`
- **Classes** — `class Point:` with optional base classes and decorators
- **`try`/`except`/`finally`** — full error handling
- **Augmented assignment** — `x += 1`, `x *= 2`, etc.
- **Tuples** — `(1, 2, 3)`, `()`, unpacking
- **Set literals** — `{1, 2, 3}`
- **List comprehensions** — `[x * x for x in range(10) if x % 2 == 0]`
- **Slices** — `xs[0:5]`, `xs[::2]`
- **Decorators** — `@lru_cache(maxsize=128)` on `fn` and `class`
- **`raise` / `del`** statements
- **`for`/`while` `else`** clauses
- **`|` alternation in `match`** — `case "a" | "b":`
- **`as` pattern binding** — `case _ as val:`
- **Tuple and class patterns** in `match`
- **`*args` / `**kwargs`** at call sites
- **Smarter REPL continuation** — tracks unbalanced brackets, not just trailing `:`
- **Expanded builtins list** — `isinstance`, `super`, `property`, `any`, `all`, and more
- **`README.md`** — this file (the repo had none)
- **Mutable-default guard** extended to sets

### ALPHA-0.0.2

- `install.sh` — makes `viper` global via pipx (falls back to venv + symlink to `~/.local/bin`)
- `viper --lsp` — pygls v2 Language Server: autocomplete (keywords + builtins) and live error diagnostics
- `viper help` — interactive 5-minute tutorial that runs code live
- `viper help <topic>` — topic reference (let, fn, match, pipe, spawn, …)
- `viper topics` — list all reference topics
- REPL tab-completion (readline, keywords + builtins + live names)
- Vim/Neovim editor support: `ftdetect`, `syntax`, `ftplugin/viper.lua` (auto-starts LSP)

### ALPHA-0.0.1

- `.vp` → Python transpiler via lark LALR parser
- `viper run <file>` and `viper repl`
- Rust-style error messages with source carets
- `let`, `fn`, `if`/`elif`/`else`, `for`, `while`, `match`/`case`
- `|>` pipe operator
- Lambda expressions: `fn(x) -> x * x`
- Mutable-default-argument footgun guard
- `spawn` for fire-and-forget concurrency (threading)
- Type annotations (optional, pass-through to Python)

---

## Install

**From PyPI (all platforms, including Windows):**

```sh
pip install viper-lang
```

**From source (Windows):**

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Fully automatic: installs the `viper` command (pipx if available, else pip --user), **adds it to your PATH** (persistently, no admin needed — works immediately in the same window), and installs the VS Code / Cursor extension.

**From source (Linux / macOS):**

```sh
./install.sh
```

Requires **Python 3.10+**. Dependencies: `lark>=1.1.0`. Optional LSP: `pygls>=2.1,<3`.

The script tries `pipx` first (clean, isolated, global). Falls back to a project venv with a symlink to `~/.local/bin/viper`.

---

## Usage

```sh
viper run hello.vp        # run a .vp file
viper hello.vp            # same thing (enables #!/usr/bin/env viper shebangs)
viper -c 'print(sha256("hi"))'   # run a one-liner
echo 'print(now())' | viper -    # run Viper from stdin (pipelines)
viper repl                # interactive prompt
viper build hello.vp      # transpile to a standalone hello.py (-o out.py to choose)
viper fmt src.vp          # format .vp files in place (--check for CI)
viper lint src.vp         # report type errors + unused-import warnings
viper doctor              # diagnose installation / editor problems
viper help                # 5-minute interactive tutorial
viper help match          # quick reference for a topic
viper topics              # list all reference topics
viper --lsp               # start the language server (for editors)
viper --version
```

Run the test suite:

```sh
pip install -e ".[test]"
pytest
```

---

## Language Reference

### Variables

```
let x = 10
let name: str = "Viper"
x += 1
x *= 2

let (a, b) = (1, 2)          # tuple unpacking
let head, *tail = [1, 2, 3]  # starred catch-all
a = b = 0                    # chained assignment

const PI = 3.14159           # immutable — reassigning PI is a compile error
```

`let` introduces a name. Reassign later with plain `=` or augmented operators. Number literals can be decimal, hex (`0xff`), octal (`0o17`), binary (`0b1010`), or use `_` separators (`1_000_000`). Strings use single or double quotes, and support `b"…"` (bytes) and `r"…"` (raw) prefixes.

### Constants and checked types

`const` binds a name that can never be reassigned — a compile-time guarantee Python doesn't offer. Type annotations are checked at transpile time, so a mismatch is an error, not a silent lie:

```
const KEY: str = "s3cret"
# KEY = "other"          # error: cannot reassign a const
const cfg = {}
cfg["a"] = 1             # fine — const freezes the name, not the object

let n: int = 5           # ok
# let n: int = "five"    # error: 'n' is annotated 'int' but the value is a str
```

Checking is conservative: Viper only flags a mismatch when the value's type is *definitely* known (literals, typed variables, and calls whose return type it knows) and *definitely* incompatible — it never cries wolf. Errors show live in the editor and block `run`/`build`.

### Functions

```
fn greet(name: str) -> str:
    return "Hello, " + name + "!"

fn add(a: int, b: int = 1) -> int:
    return a + b

let square = fn(x) -> x * x
```

### Classes

```
class Point:
    fn __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    fn __repr__(self) -> str:
        return f"Point({self.x}, {self.y})"

let p = Point(3.0, 4.0)
print(p)
```

### Decorators

```
from functools import lru_cache

@lru_cache(maxsize=128)
fn fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
```

### Error handling

```
try:
    let result = int("not a number")
except ValueError as e:
    print(f"Caught: {e}")
finally:
    print("done")
```

### Pattern matching

```
match cmd:
    case "quit" | "exit":
        print("goodbye")
    case ["move", x, y]:
        print(f"moving to {x}, {y}")
    case _ as unknown:
        print(f"unknown: {unknown}")
```

### Pipes and lambdas

```
import math

print([3, 1, 2] |> sorted)
print(math.sqrt(144) |> int)
print(3.14159 |> round(_, 2))   # placeholder: round(3.14159, 2)
```

`x |> f` means `f(x)`, chaining left to right. Use `_` as a placeholder to pipe the value into a specific argument: `x |> f(_, 2)` becomes `f(x, 2)`.

### Comprehensions and slices

```
let evens = [x for x in range(20) if x % 2 == 0]   # list
let vowels = {c for c in "hello" if c in "aeiou"}  # set
let squares = {n: n * n for n in range(5)}         # dict
let lazy = (x for x in range(10))                  # generator

let first5 = evens[0:5]
let every_other = evens[::2]
```

### Tuples and sets

```
let point = (3.0, 4.0)
let (px, py) = point

let unique = {1, 2, 3, 2, 1}
```

### Walrus, with, and assert

```
if (n := len(evens)) > 0:
    print(f"got {n} evens")

with open("data.txt") as f:
    print(f.read())

assert n > 0, "expected at least one even"
```

### Bitwise operators

```
print(0b1010 | 0b0101)   # 15
print(0xff & 0x0f)       # 15
print(1 << 4)            # 16
```

### Built-in prelude (batteries included)

A curated standard library is in scope in every Viper program — no import needed. All of it is backed by the Python standard library (no third-party deps), and each helper shows its signature and docs on hover. `viper help std` lists everything; the highlights:

```
# hashing / encoding / crypto
print(sha256("hunter2"))
print(b64("data") |> unb64 |> bytes.decode(_))
print(hmac256("key", "message"))
print(to_hex(xor("secret", "k")))            # repeating-key XOR

# http / shell / json / files
let body = http_get("https://example.com")
let out  = sh_out("git status")
let data = read_json("config.json")
print(json_get(data, "server.port", 8080))   # safe nested access

# web
let u = url_parse("https://ex.com:8443/p?a=1")
print(u["host"], u["port"])

# classic
pp({"name": "viper", "items": [1, 2, 3]})     # pretty-print
print(clamp(10, 0, 5))                        # 5
```

Groups: **hashing** (`sha256` `md5` `hmac256` `file_sha256` …), **encoding** (`b64` `to_hex` `url_quote` …), **randomness** (`rand_token` `uuid4` …), **http** (`http_get` `http_post` `download` …), **shell** (`sh` `sh_out` `which`), **json/files** (`json_parse` `read_json` `read_lines` `ls` `env` …), **data** (`hexdump` `now` `port_open` …), **crypto/web** (`xor` `url_parse` `qs_parse` `json_get`).

### Calling into C

When you need the metal — a native crypto routine, a raw syscall, an existing C library — `clib()` calls into C via `ctypes` (no compiler, no dependency):

```
const libc = clib("msvcrt")                       # or a .so / .dll / .dylib path
const strlen = libc.func("strlen", "int", ["str"])  # declared signature
print(strlen("viper"))                            # -> 5, str auto-encoded

const k = clib("kernel32", abi="win")             # Win32 stdcall APIs
print(k.GetTickCount())                           # quick path: int in/out
```

This is *call into C*, not *become C*: you get C libraries, not manual memory or native speed for Viper itself. See `viper help ffi`.

### Footgun guards

Viper turns a few of Python's silent traps into clear errors:

```
fn bad(x=[]):        # rejected: mutable default argument
    return x

if x == None:        # rejected: use 'is None'
    pass

try:
    risky()
except:              # rejected: name the exception, e.g. 'except Exception:'
    pass

let list = [1, 2]    # rejected: shadows the builtin 'list'
```

### Generators

```
fn counter(n):
    let i = 0
    while i < n:
        yield i
        i += 1

fn doubled(n):
    yield from counter(n)   # delegate to another generator
    yield 99

print(list(doubled(3)))     # [0, 1, 2, 99]
```

Any `fn` containing `yield` becomes a generator — it produces values lazily, one at a time, and keeps its state between calls. Use `yield from` to delegate to another generator. Generators work everywhere Python's do: `for` loops, `list()`, `sum()`, `next()`, comprehensions.

> Limitation: `yield` is statement-only. `let x = yield` (the `.send()` protocol) isn't supported yet.

### Async / await

```
import asyncio

async fn fetch(x):
    await asyncio.sleep(0.1)     # await is an expression
    return x * 2

async fn main():
    let r = await fetch(21)
    print(f"got {r}")            # got 42

asyncio.run(main())
```

`async fn` defines a coroutine; `await` suspends until it finishes. Because `await` is an expression, it works anywhere: `let r = await f()`, `print(await g())`, even inside pipes. `async for` and `async with` are also supported, so async iterators and async context managers (aiohttp sessions, database pools, …) work as expected. Decorators work on `async fn`.

Entry point rule is the same as Python's: kick things off with `asyncio.run(main())`.

### Spawn

```
spawn:
    print("running in the background")
```

Runs the block in a daemon thread (fire-and-forget). For structured concurrency, prefer `async fn` + `asyncio`.

### Imports

```
import math                        # any Python module
from os import path
from collections import defaultdict

import utils                       # finds utils.vp next to your script!
from helpers import shortcut       # helpers.vp works too
```

Any Python module works — and as of Beta 1.0, so does any **Viper module**. `import utils` looks for `utils.vp` in the running script's directory (and the rest of `sys.path`), transpiles it on the fly, and caches it like a normal module. Split your program into as many `.vp` files as you like; the prelude (`pp`, `read_file`, …) is available in every one of them.

### Error messages that stay in Viper

Parse errors have always pointed at your `.vp` source with a caret. As of Beta 1.0, *runtime* errors do too — across files. A crash three modules deep prints a full Viper call stack:

```
traceback (most recent call last):
  at main.vp:4
error: ZeroDivisionError: division by zero
 --> mathutils.vp:5:1
  |
5 |     return 1 / 0
  | ^
```

Every frame is mapped back to its `.vp` file and line; Python's internal machinery is hidden.

### Building standalone Python files

```sh
viper build script.vp            # writes script.py
viper build script.vp -o app.py  # choose the output name
```

The output is plain, dependency-free Python — the Viper prelude is inlined at the top — so it runs anywhere Python 3.10+ runs, with no Viper installation. Use it to ship code to people who don't have Viper, or to inspect exactly what your program transpiles to.

### Formatting

```sh
viper fmt src.vp            # fix in place
viper fmt --check src.vp    # report only; exit 1 if anything would change
```

The v1 formatter is deliberately conservative: it strips trailing whitespace, converts leading tabs to 4 spaces, collapses runs of blank lines, and ensures a single trailing newline. Safety gate: it refuses to write unless the transpiled Python is byte-identical before and after — it can never change what your program does. Wire `--check` into CI to keep a codebase clean.

---

## Editor Support

**VS Code & Cursor:** run `install.ps1` (Windows) or copy `editor/vscode/viper/` into `~/.vscode/extensions/` / `~/.cursor/extensions/` — syntax highlighting **plus Python-grade smarts via the bundled LSP client**: context-aware autocompletion with signatures and docs, dot-completion for Python *and* Viper modules, signature help, hover docs, and live error squiggles. Needs `pip install \"viper-lang[lsp]\"` (the installers do this for you). Details in `editor/vscode/README.md`.

**Neovim ≥ 0.8:** after running `install.sh`, open a `.vp` file — syntax highlighting and LSP autocomplete + live errors start automatically.

**Vim 8 users:** see `editor/README.md` for the `prabirshrestha/vim-lsp` setup snippet.

---

## File Extension

`.vp`

---

## License

MIT — see `LICENSE`.

*(Formerly: "wala license ginawa ko lang kasi gusto ko" — retired in Beta 1.0 so PyPI tooling doesn't choke.)*
