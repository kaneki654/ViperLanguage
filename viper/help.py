"""`viper help <topic>` — concise reference for Viper language features."""
from ._ansi import header, dim

TOPICS = {
    "let": (
        "Bind a value to a name. Use 'let' the first time you introduce a name; "
        "you can add an optional type. Reassign later with plain '='.",
        'let x = 10\nlet name: str = "Viper"\nx = x + 1',
    ),
    "fn": (
        "Define a function with 'fn'. Parameters may have types and defaults; "
        "an optional '-> type' annotates the return. Mutable defaults like "
        "'x=[]' are rejected (use None instead).",
        "fn add(a: int, b: int = 1) -> int:\n    return a + b",
    ),
    "if": (
        "Conditional branching. 'elif' and 'else' are optional. There is also "
        "an inline form:  value if cond else other.",
        'if score > 90:\n    print("A")\nelif score > 80:\n    print("B")\nelse:\n    print("C")',
    ),
    "for": (
        "Iterate over any iterable (lists, ranges, strings, dict keys...).",
        "for n in [1, 2, 3]:\n    print(n)",
    ),
    "while": (
        "Loop while a condition holds. 'break' and 'continue' work as expected.",
        "let i = 0\nwhile i < 3:\n    print(i)\n    i = i + 1",
    ),
    "match": (
        "Pattern matching. Cases can be literals, capture names, '_' wildcard, "
        "or sequence patterns, with an optional 'if' guard.",
        'match cmd:\n    case "go":\n        print("moving")\n    case _:\n        print("unknown")',
    ),
    "pipe": (
        "The pipe operator '|>' feeds a value into a function as its argument. "
        "'x |> f |> g' is the same as 'g(f(x))' but reads left-to-right.",
        "let nums = [3, 1, 2]\nprint(nums |> sorted)\nprint(16 |> float |> int)",
    ),
    "lambda": (
        "Anonymous functions use the same 'fn' keyword with an arrow expression.",
        "let square = fn(x) -> x * x\nprint(square(5))",
    ),
    "dict": (
        "Dictionaries map keys to values; index with [key].",
        'let user = {"name": "Ada", "age": 36}\nprint(user["name"])',
    ),
    "list": (
        "Ordered collections. Index, iterate, and pipe into builtins.",
        "let xs = [5, 2, 8]\nprint(xs[0])\nprint(xs |> len)",
    ),
    "import": (
        "Viper connects to Python's whole module ecosystem. Import any Python "
        "module and use it directly.",
        "import math\nprint(math.sqrt(16))\nfrom math import pi",
    ),
    "spawn": (
        "Run a block concurrently in a background thread (fire-and-forget).",
        'spawn:\n    print("running in the background")',
    ),
    "types": (
        "Type annotations are optional and pass straight through to Python. "
        "They document intent and work with Python tooling; Viper does not yet "
        "type-check them.",
        "let count: int = 0\nfn greet(name: str) -> str:\n    return \"hi \" + name",
    ),
}

ALIASES = {
    "|>": "pipe",
    "def": "fn",
    "func": "fn",
    "function": "fn",
    "dictionary": "dict",
    "array": "list",
    "elif": "if",
    "else": "if",
    "case": "match",
    "type": "types",
}


def show_topic(name: str) -> int:
    key = ALIASES.get(name, name)
    if key not in TOPICS:
        print(f"unknown topic: {name!r}\n")
        list_topics()
        return 1
    explain, example = TOPICS[key]
    print(header(f"viper · {key}"))
    print()
    print(explain)
    print()
    print(dim("example:"))
    for line in example.splitlines():
        print("    " + line)
    return 0


def list_topics() -> int:
    print(header("available topics"))
    print()
    names = sorted(TOPICS)
    for i in range(0, len(names), 4):
        print("  " + "  ".join(f"{n:<10}" for n in names[i:i + 4]).rstrip())
    print()
    print(dim("use:  viper help <topic>   (e.g. viper help match)"))
    return 0
