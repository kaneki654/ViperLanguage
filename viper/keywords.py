"""Shared Viper vocabulary — keep editor/syntax/viper.vim in sync with this."""

KEYWORDS = [
    "let", "fn", "if", "elif", "else", "while", "for", "in", "match", "case",
    "return", "break", "continue", "pass", "import", "from", "spawn",
    "and", "or", "not", "is", "True", "False", "None",
    "class", "try", "except", "finally", "raise", "del", "as",
    # New in 0.0.3
    "with", "assert", "global", "nonlocal",
    # New in 1.0.0b1
    "yield", "async", "await",
]

BUILTINS = [
    "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
    "set", "tuple", "sum", "min", "max", "abs", "sorted", "enumerate", "zip",
    "map", "filter", "input", "round", "type", "repr",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr", "delattr",
    "iter", "next", "open", "reversed", "any", "all", "id", "hex", "bin",
    "oct", "ord", "chr", "hash", "vars", "dir", "callable", "super",
    "staticmethod", "classmethod", "property",
    # New in 0.0.3 — Viper stdlib prelude
    "pp", "read_file", "write_file", "clamp",
]

