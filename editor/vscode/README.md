# Viper for VS Code and Cursor

Full language support for `.vp` files: syntax highlighting **and** Python-grade
editor intelligence via the bundled LSP client (Cursor is a VS Code fork, so
the same extension works in both).

## Features

- **Smart autocompletion** — real symbols from your file: every `fn` with its
  signature (`fn add(a: int, b: int = 1) -> int`), classes, `let` bindings,
  parameters when the cursor is inside their function — plus keywords, builtins,
  and the Viper prelude, each with docs
- **Ranked suggestions** — your own variables and functions first, then
  imports, builtins, and keywords last (the same prioritization Pylance
  uses for Python)
- **Type inference** — `let name = "hi"` makes `name.` complete str methods
  with signatures; works for list/dict/set/tuple/int/float literals, annotated
  params (`fn f(msg: str)` → `msg.`), constructor calls (`let p = Point(1, 2)`
  → `p.` lists Point's methods and attributes), and `self.` inside a class
- **Auto-import completions** — top-level `fn`s and classes from other `.vp`
  files in your workspace are suggested before you import them; accepting one
  inserts the `from module import name` line for you
- **Go to definition** (F12) — jumps to `fn` / `class` / `let` definitions,
  including into other `.vp` modules
- **Outline & breadcrumbs** — functions, classes, methods, and module-level
  `let`s in the Explorer outline (Ctrl+Shift+O)
- **Statement snippets** — `fn`, `class`, `for`, `match`, `try` templates with
  tab-stops
- **Never goes dark** — while a line is half-typed (or uses syntax Viper
  doesn't know), completions still work: a fallback scanner keeps your
  symbols available until the buffer parses again
- **Fast** — analysis is cached per keystroke; repeat requests answer in
  well under a millisecond, so the popup always wins the race
- **Dot-completion** — `math.` lists real members with signatures and
  documentation; import aliases work (`import collections as coll` → `coll.`),
  and so do **Viper modules** (`import utils` → `utils.` lists what `utils.vp`
  defines — parsed, never executed)
- **Context awareness** — `import ` / `from ` complete module names,
  `from math import ` completes members, `async ` suggests only `fn`/`for`/`with`,
  and nothing pops up inside strings or comments
- **Signature help** — parameter hints with the active argument highlighted,
  for Viper functions, classes, builtins, and imported Python functions
- **Hover docs** — signature + docstring for the symbol under the cursor
- **Live diagnostics** — parse errors as you type
- Comment toggling (Ctrl+/), auto-closing pairs, auto-indent after `:`
- Custom Viper file icon

## Requirements

The language server ships with Viper: `pip install "viper-lang[lsp]"` —
`install.ps1` and `install.sh` handle this automatically. The extension runs
`viper --lsp` from your PATH; point `viper.lspPath` (Settings) at the
executable if yours lives somewhere unusual.

## Install (automatic, Windows)

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Install (manual)

```
python editor/vscode/register_extension.py
```

then fully quit and reopen the editor. The script copies the extension into
`~/.vscode/extensions/` and `~/.cursor/extensions/` **and registers it in each
editor's `extensions.json`**. Just copying the folder there by hand is not
enough — modern VS Code and Cursor silently ignore extension folders that
aren't listed in `extensions.json`, so you'd get no completions and no
diagnostics with no error anywhere.

## Troubleshooting

Run `viper doctor` first — it checks the interpreter, the language server,
PATH, and that the extension is both installed **and registered** with each
editor, and prints the exact fix for whatever it finds.

If you see "couldn't start the language server": Viper isn't on PATH or pygls
is missing. Run the installer again (it fixes PATH and installs the `[lsp]`
extra), then restart the editor.

If completions vanish after reinstalling/updating: the extension folder was
probably replaced without updating the editor's `extensions.json` registry.
Run `python editor/vscode/register_extension.py` and fully quit and reopen
the editor (a plain Reload Window can miss registry changes).
