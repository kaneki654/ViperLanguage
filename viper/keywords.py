"""Shared Viper vocabulary — the single source of truth for the LSP completion
list and the Vim syntax file. Keep editor/syntax/viper.vim in sync with this."""

KEYWORDS = [
    "let", "fn", "if", "elif", "else", "while", "for", "in", "match", "case",
    "return", "break", "continue", "pass", "import", "from", "spawn",
    "and", "or", "not", "is", "True", "False", "None",
    # New in upgrade
    "class", "try", "except", "finally", "raise", "del", "as",
]

BUILTINS = [
    "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
    "set", "tuple", "sum", "min", "max", "abs", "sorted", "enumerate", "zip",
    "map", "filter", "input", "round", "type", "repr",
    # Common extras
    "isinstance", "issubclass", "hasattr", "getattr", "setattr", "delattr",
    "iter", "next", "open", "reversed", "any", "all", "id", "hex", "bin",
    "oct", "ord", "chr", "hash", "vars", "dir", "callable", "super",
    "staticmethod", "classmethod", "property",
]
