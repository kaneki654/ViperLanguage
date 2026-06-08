# Viper editor support

`install.sh` copies these files into `~/.vim/` and `~/.config/nvim/` for you.
This directory contains:

- `ftdetect/viper.vim` — recognise `*.vp` files as Viper.
- `syntax/viper.vim` — syntax highlighting (keywords, builtins, strings, numbers, `|>`).
- `ftplugin/viper.lua` — **Neovim** language-server client (autocomplete + live errors).

## Neovim (recommended)

Needs Neovim ≥ 0.8 and the `viper` command on your PATH, installed with the LSP
extra so `viper --lsp` works:

```sh
pipx install . && pipx inject viper-lang 'pygls>=2.1,<3'
# or:  pip install 'viper-lang[lsp]'
```

Open any `.vp` file — completion (`<C-x><C-o>` or your completion plugin) and
inline diagnostics start automatically. Check the client with `:LspInfo`.

## Classic Vim 8

Stock Vim has no built-in LSP client. Syntax highlighting works out of the box.
For autocomplete + diagnostics, install [`prabirshrestha/vim-lsp`] and add to your
`.vimrc`:

```vim
if executable('viper')
  au User lsp_setup call lsp#register_server({
    \ 'name': 'viper-lsp',
    \ 'cmd': {server_info->['viper', '--lsp']},
    \ 'allowlist': ['viper'],
    \ })
endif
```

[`prabirshrestha/vim-lsp`]: https://github.com/prabirshrestha/vim-lsp
