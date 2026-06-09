"""`viper help <topic>` — concise reference for Viper language features."""
from ._ansi import header, dim

TOPICS = {
    "let": (
        "Bind a value to a name. Use 'let' the first time; reassign with '='. "
        "Supports tuple and starred unpacking: 'let (a, b) = pair', "
        "'let a, *rest = xs'.",
        'let x = 10\nlet name: str = "Viper"\nlet a, b = (1, 2)',
    ),
    "fn": (
        "Define a function with 'fn'. Parameters may have types and defaults; "
        "an optional '-> type' annotates the return. Mutable defaults like "
        "'x=[]' are rejected (use None instead).",
        "fn add(a: int, b: int = 1) -> int:\n    return a + b",
    ),
    "if": (
        "Branching. 'elif' and 'else' are optional. Inline form: "
        "value if cond else other. The walrus ':=' is allowed in conditions.",
        'if (n := len(xs)) > 0:\n    print(n)',
    ),
    "for": (
        "Iterate over any iterable. Supports tuple/starred targets and "
        "'for ... else'.",
        "for k, v in items:\n    print(k, v)",
    ),
    "while": (
        "Loop while a condition holds. Supports 'else' and walrus.",
        "while (line := input()) != \"q\":\n    print(line)",
    ),
    "match": (
        "Pattern matching with literals, captures, '_' wildcard, sequences, "
        "tuples, class patterns, '|' alternation, 'as' bindings, and 'if' guards.",
        'match cmd:\n    case ["go", x, y] if x > 0:\n        print("moving")',
    ),
    "pipe": (
        "'|>' feeds a value into a function: 'x |> f' is 'f(x)'. "
        "Use '_' as a placeholder to pipe into a specific argument:\n"
        "  3.14159 |> round(_, 2)   means   round(3.14159, 2)",
        "let nums = [3, 1, 2]\nprint(nums |> sorted)\n"
        "print(3.14159 |> round(_, 2))",
    ),
    "lambda": (
        "Anonymous functions: 'fn(x) -> expr'.",
        "let square = fn(x) -> x * x",
    ),
    "dict": (
        "Dictionaries map keys to values. '{}' is an empty dict; comprehensions "
        "supported: '{k: v for k, v in items}'.",
        'let scores = {n: n*n for n in range(5)}',
    ),
    "list": (
        "Ordered collections. List comps, slices, and pipes all work.",
        "let evens = [x for x in range(10) if x % 2 == 0]",
    ),
    "import": (
        "Viper speaks Python's whole ecosystem. Import any Python module.",
        "import math\nfrom os import path",
    ),
    "spawn": (
        "Run a block in a background daemon thread.",
        'spawn:\n    print("hi from a thread")',
    ),
    "types": (
        "Type annotations pass through to Python; not yet checked by Viper.",
        "let n: int = 0",
    ),
    "with": (
        "Context managers — auto-cleanup on scope exit.",
        'with open("data.txt") as f:\n    print(f.read())',
    ),
    "assert": (
        "Cheap runtime checks. Optional message after a comma.",
        'assert x > 0, "x must be positive"',
    ),
    "comprehension": (
        "List / set / dict / generator comprehensions, all uniform.",
        "let xs = [x*x for x in range(10) if x % 2 == 0]\n"
        "let s  = {c for c in \"hello\"}\n"
        "let d  = {n: n*n for n in range(5)}\n"
        "let g  = (x for x in range(10))",
    ),
    "walrus": (
        "':=' binds and returns a value. Allowed in if/elif/while and in "
        "parenthesized atoms.",
        'if (n := len(line)) > 80:\n    print("too long:", n)',
    ),
    "bitwise": (
        "Bitwise '|' '^' '&', shifts '<<' '>>'. Precedence matches Python. "
        "(Note '|>' is the pipe operator, not bitor.)",
        "print(0b1010 | 0b0101)\nprint(1 << 4)",
    ),
    "unpack": (
        "Tuple/list unpacking with optional starred catch-all.",
        "let (a, b, c) = (1, 2, 3)\nlet head, *tail = [1, 2, 3, 4]",
    ),
    "prelude": (
        "Built into every Viper run: pp (pretty-print), read_file(path), "
        "write_file(path, text), clamp(x, lo, hi).",
        'write_file("hi.txt", "hello")\nprint(read_file("hi.txt"))',
    ),
    "global": (
        "Declare module-level bindings inside a function.",
        "let counter = 0\nfn bump():\n    global counter\n    counter += 1",
    ),
    "nonlocal": (
        "Rebind an enclosing function's local from a nested function.",
        "fn make_counter():\n    let n = 0\n    fn inc():\n        nonlocal n\n        n += 1\n        return n\n    return inc",
    ),
    "raise": (
        "Raise an exception, optionally chaining a cause with 'from'.",
        'try:\n    int("nope")\nexcept ValueError as e:\n    raise RuntimeError("bad input") from e',
    ),
}

ALIASES = {
    "|>": "pipe",
    ":=": "walrus",
    "def": "fn", "func": "fn", "function": "fn",
    "dictionary": "dict", "array": "list",
    "elif": "if", "else": "if",
    "case": "match",
    "type": "types",
    "comp": "comprehension", "genexp": "comprehension",
    "stdlib": "prelude",
}


def show_topic(name: str) -> int:
    key = ALIASES.get(name, name)
    if key not in TOPICS:
        print(f"unknown topic: {name!r}\n"); list_topics(); return 1
    explain, example = TOPICS[key]
    print(header(f"viper · {key}")); print()
    print(explain); print()
    print(dim("example:"))
    for line in example.splitlines():
        print("    " + line)
    return 0


def list_topics() -> int:
    print(header("available topics")); print()
    names = sorted(TOPICS)
    for i in range(0, len(names), 4):
        print("  " + "  ".join(f"{n:<14}" for n in names[i:i + 4]).rstrip())
    print()
    print(dim("use:  viper help <topic>   (e.g. viper help walrus)"))
    return 0

