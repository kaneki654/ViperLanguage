"""`viper help <topic>` — concise reference for Viper language features."""
from ._ansi import header, dim

TOPICS = {
    "let": (
        "Bind a value to a name. Use 'let' the first time; reassign with '='. "
        "Supports tuple and starred unpacking: 'let (a, b) = pair', "
        "'let a, *rest = xs'. For a binding that must never change, use 'const'.",
        'let x = 10\nlet name: str = "Viper"\nlet a, b = (1, 2)',
    ),
    "const": (
        "Bind a value to a name that can never be reassigned. Rebinding a const "
        "(with '=', '+=', or another 'let'/'const') is a compile-time error — "
        "something Python can't enforce. You can still mutate the object it "
        "points at; const freezes the name, not the value.",
        'const PI = 3.14159\nconst KEY: str = "s3cret"\n# PI = 3  # error: cannot reassign a const',
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
        "Type annotations are checked at transpile time — 'let x: int = \"hi\"' "
        "is an error, not a silent lie. Viper checks what it can know for sure: "
        "literals, typed variables and params, and calls whose return type is "
        "known (builtins, the stdlib, and your own 'fn ... -> T'). It stays "
        "quiet when it can't be certain (custom classes, arithmetic), so it "
        "never cries wolf. Annotations still pass through to Python too.",
        'let n: int = 0\nlet name: str = "Viper"\n# let bad: int = "oops"  # error',
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
        "Batteries included — no import needed, in every Viper run:\n"
        "  hashing   sha256 sha1 sha512 md5 hmac256 file_sha256\n"
        "  encoding  b64 unb64 to_hex from_hex url_quote url_unquote\n"
        "  random    rand_token rand_int uuid4\n"
        "  http      http_get http_post http_status download\n"
        "  shell     sh sh_out which\n"
        "  json/fs   json_parse json_str read_json write_json read_lines ls exists env\n"
        "  data      hexdump sleep now port_open\n"
        "  crypto/web  xor url_parse qs_parse qs_build json_get\n"
        "  native    clib (call into C libraries — see 'viper help ffi')\n"
        "  classic   pp read_file write_file clamp\n"
        "See any one with hover in your editor, or 'viper help <name>'.",
        'let body = http_get("https://example.com")\n'
        'print(sha256(body))\n'
        'print(hexdump(unb64("ZmxhZ3tva30=")))',
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
    "ffi": (
        "Call into C libraries with clib() — built on ctypes, no compiler "
        "needed. 'lib.Name(args)' is the quick path (int in/out, str auto-"
        "encoded); 'lib.func(name, restype, [argtypes])' declares a typed "
        "signature. Types: void bool int uint long short byte float double "
        "size_t str (char*) wstr ptr. Use abi='win' for Win32 APIs. This is "
        "'call into C', not 'become C' — you get C libraries, not native speed.",
        'const libc = clib("msvcrt")\n'
        'const strlen = libc.func("strlen", "int", ["str"])\n'
        'print(strlen("viper"))   # -> 5',
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
    "stdlib": "prelude", "std": "prelude", "batteries": "prelude",
    "clib": "ffi", "c": "ffi", "ctypes": "ffi", "native": "ffi",
}


def show_topic(name: str) -> int:
    key = ALIASES.get(name, name)
    if key not in TOPICS:
        # maybe it's a stdlib prelude helper, e.g. `viper help sha256`
        from .std import STD_DOCS
        if name in STD_DOCS:
            sig, doc = STD_DOCS[name]
            print(header(f"viper · {name}")); print()
            print(doc); print()
            print(dim("signature:")); print("    " + sig)
            return 0
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

