"""Shared Viper vocabulary — the single source of truth for the LSP completion
list and the Vim syntax file. Keep editor/syntax/viper.vim in sync with this."""

KEYWORDS = [
    "let", "fn", "if", "elif", "else", "while", "for", "in", "match", "case",
    "return", "break", "continue", "pass", "import", "from", "spawn",
    "and", "or", "not", "is", "True", "False", "None",
]

BUILTINS = [
    "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
    "set", "tuple", "sum", "min", "max", "abs", "sorted", "enumerate", "zip",
    "map", "filter", "input", "round", "type", "repr",
]
