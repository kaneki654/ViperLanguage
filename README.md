# Viper Language

A clean, Python-connected scripting language. Write `.vp`, run Python.

```
let name = "world"
print(f"Hello, {name}!")
```

Viper transpiles to Python, so every Python module works out of the box — `import math`, `import os`, anything.

---

## Changelog

### ALPHA-0.0.2-1 *(current)*

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

---

## Language Reference

### Variables

```
let x = 10
let name: str = "Viper"
x += 1
x *= 2
```

`let` introduces a name. Reassign later with plain `=` or augmented operators.

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
```

`x |> f` means `f(x)`. Chains left to right.

### Comprehensions and slices

```
let evens = [x for x in range(20) if x % 2 == 0]
let first5 = evens[0:5]
let every_other = evens[::2]
```

### Tuples and sets

```
let point = (3.0, 4.0)
let (px, py) = point

let unique = {1, 2, 3, 2, 1}
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
