#!/bin/sh
# Install the `viper` command and editor support.
# Tries pipx (clean, global, isolated); falls back to a project venv + symlink.
# Safe to re-run.
set -e

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PYGLS='pygls>=2.1,<3'

have() { command -v "$1" >/dev/null 2>&1; }

echo "Installing Viper from $SCRIPT_DIR"
echo

# --- Install the CLI: prefer pipx, else venv + symlink ----------------------
if have pipx; then
    echo "==> pipx found — installing globally"
    pipx install --force "$SCRIPT_DIR"
    # pipx installs base deps only; add the LSP extra so `viper --lsp` works.
    pipx inject viper-lang "$PYGLS"
    VIPER_NOTE="'viper' is on your PATH via pipx."
else
    echo "==> pipx not found — using a project virtualenv"
    VENV="$SCRIPT_DIR/.venv"
    [ -d "$VENV" ] || python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip >/dev/null
    "$VENV/bin/pip" install -e "$SCRIPT_DIR[lsp]"
    mkdir -p "$HOME/.local/bin"
    ln -sf "$VENV/bin/viper" "$HOME/.local/bin/viper"
    VIPER_NOTE="symlinked to ~/.local/bin/viper — make sure ~/.local/bin is on your PATH."
fi

# --- Install editor files (Vim + Neovim) ------------------------------------
echo
echo "==> Installing editor support"

# Vim
mkdir -p "$HOME/.vim/ftdetect" "$HOME/.vim/syntax"
cp "$SCRIPT_DIR/editor/ftdetect/viper.vim" "$HOME/.vim/ftdetect/viper.vim"
cp "$SCRIPT_DIR/editor/syntax/viper.vim"   "$HOME/.vim/syntax/viper.vim"

# Neovim
NVIM="$HOME/.config/nvim"
mkdir -p "$NVIM/ftdetect" "$NVIM/syntax" "$NVIM/ftplugin"
cp "$SCRIPT_DIR/editor/ftdetect/viper.vim" "$NVIM/ftdetect/viper.vim"
cp "$SCRIPT_DIR/editor/syntax/viper.vim"   "$NVIM/syntax/viper.vim"
cp "$SCRIPT_DIR/editor/ftplugin/viper.lua" "$NVIM/ftplugin/viper.lua"

# --- Done -------------------------------------------------------------------
echo
echo "Done. $VIPER_NOTE"
echo
echo "Try it:"
echo "  viper help                    # 5-minute interactive tutorial"
echo "  viper repl                    # interactive prompt"
echo "  viper run $SCRIPT_DIR/examples/hello.vp"
echo
echo "Editing: open a .vp file in Neovim (>= 0.8) for autocomplete + live errors."
echo "Classic Vim 8 users: see $SCRIPT_DIR/editor/README.md for the LSP setup."
