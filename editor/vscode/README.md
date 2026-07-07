# Viper for VS Code and Cursor

Syntax highlighting, bracket matching, comment toggling, and auto-indent for `.vp` files. Cursor is a VS Code fork, so the same extension works in both.

## Install (automatic)

Run the repo's Windows installer — it copies the extension into both editors:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Install (manual)

Copy the `viper/` folder from this directory to your editor's extensions folder and restart the editor:

| Editor  | Extensions folder                          |
|---------|--------------------------------------------|
| VS Code | `%USERPROFILE%\.vscode\extensions\`         |
| Cursor  | `%USERPROFILE%\.cursor\extensions\`         |
| VS Code (macOS/Linux) | `~/.vscode/extensions/`       |
| Cursor (macOS/Linux)  | `~/.cursor/extensions/`       |

Rename the copied folder to `viper-lang.viper-1.0.0`.

## What you get

- Highlighting for all Viper keywords (`let`, `fn`, `spawn`, `async`, `yield`, …), builtins, the prelude (`pp`, `clamp`, …), f-strings, numbers (hex/bin/octal/underscores), decorators, and the `|>` pipe operator
- `#` comment toggling (Ctrl+/)
- Auto-closing brackets and quotes
- Auto-indent after a line ending in `:`

## Roadmap

A full LSP client (completions + live diagnostics via `viper --lsp`, like the Neovim setup) is planned for 1.0 final.
