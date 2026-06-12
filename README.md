# Viper Language

A clean, Python-connected scripting language. Write `.vp`, run Python.

```
let name = "world"
print(f"Hello, {name}!")
print(3.14159 |> round(_, 2))
```

Viper transpiles to Python, so every Python module works out of the box — `import math`, `import os`, anything. It aims to be a little friendlier than Python: clear error messages, a few footgun guards, a pipe operator with placeholders, and a small built-in stdlib.

---

## Changelog

### ALPHA-0.0.3 *(current)*

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

```sh
./install.sh
```

Requires **Python 3.10+**. Dependencies: `lark>=1.1.0`. Optional LSP: `pygls>=2.1,<3`.

The script tries `pipx` first (clean, isolated, global). Falls back to a project venv with a symlink to `~/.local/bin/viper`.

---

## Usage

```sh
viper run hello.vp        # run a .vp file
viper repl                # interactive prompt
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
```

`let` introduces a name. Reassign later with plain `=` or augmented operators. Number literals can be decimal, hex (`0xff`), octal (`0o17`), binary (`0b1010`), or use `_` separators (`1_000_000`). Strings use single or double quotes.

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

### Built-in prelude

Available in every Viper program — no import needed:

```
pp({"name": "viper", "items": [1, 2, 3]})   # pretty-print
write_file("out.txt", "hello")
print(read_file("out.txt"))
print(clamp(10, 0, 5))                       # 5
```

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

### Spawn

```
spawn:
    print("running in the background")
```

Runs the block in a daemon thread (fire-and-forget).

### Imports

```
import math
from os import path
from collections import defaultdict
```

Any Python module works.

---

## Editor Support

After running `install.sh`, open a `.vp` file in **Neovim ≥ 0.8** — syntax highlighting and LSP autocomplete + live errors start automatically.

**Vim 8 users:** see `editor/README.md` for the `prabirshrestha/vim-lsp` setup snippet.

---

## File Extension

`.vp`

---

## License

"wala license ginawa ko lang kasi gusto ko"
