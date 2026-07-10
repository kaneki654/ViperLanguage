# Viper Language

Language support for [Viper](https://github.com/kaneki654/ViperLanguage) —
the batteries-included scripting language that transpiles to Python. Works in
VS Code and every VS Code-family editor (Cursor, Windsurf, Antigravity,
VSCodium).

## Features

- **Syntax highlighting** for `.vp` files
- **Smart autocompletion** with signatures and docs — for Viper's always-in-scope
  stdlib, Python modules, *and* your own `.vp` modules (dot-completion included)
- **Live error squiggles** — parse errors, type errors (red) and lint warnings
  (yellow) as you type
- **Hover docs** and **signature help**
- Falls back to keyword/buffer completions if the language server isn't
  available

## Requirements

The smart features need the `viper` command with LSP support:

```
pip install "viper-lang[lsp]"
```

(or `pipx install "viper-lang[lsp]"` / `uv tool install "viper-lang[lsp]"`).

If `viper` is not on your PATH, point the extension at it with the
`viper.lspPath` setting.

## Extension Settings

| Setting | Description |
| --- | --- |
| `viper.lspPath` | Path to the `viper` executable (leave empty to use `viper` from PATH). |

## Getting started with Viper

```
# no imports needed — this is the whole program
let body = http_get("https://example.com")
print(sha256(body))
```

See the [Viper README](https://github.com/kaneki654/ViperLanguage#readme) for
the language tour, or run `viper help` for the interactive tutorial.

## License

MIT
