"""`viper help` with no topic — a short interactive tour of the language.

Each lesson explains a feature, shows a runnable example, and runs it live so
you see real output before moving on.
"""
from ._ansi import header, bold, dim
from .errors import ViperError
from .runtime import run_source

LESSONS = [
    {
        "title": "1. Printing",
        "explain": "Every language starts with hello. 'print' shows a value.",
        "code": 'print("Hello from Viper!")',
    },
    {
        "title": "2. Let bindings (with optional types)",
        "explain": "Introduce a name with 'let'. You may add a type; it is "
                   "optional and just documents your intent.",
        "code": 'let name: str = "Ada"\nlet year = 1815\nprint(name)\nprint(year)',
    },
    {
        "title": "3. Functions",
        "explain": "Define functions with 'fn'. Parameters can have types and "
                   "defaults, and '-> type' annotates what you return.",
        "code": "fn add(a: int, b: int = 1) -> int:\n    return a + b\nprint(add(10))\nprint(add(10, 5))",
    },
    {
        "title": "4. Conditionals",
        "explain": "Branch with if / elif / else.",
        "code": 'let score = 85\nif score > 90:\n    print("A")\nelif score > 80:\n    print("B")\nelse:\n    print("C")',
    },
    {
        "title": "5. Loops over lists",
        "explain": "Lists hold ordered values; 'for' walks through them.",
        "code": "let nums = [1, 2, 3]\nfor n in nums:\n    print(n * n)",
    },
    {
        "title": "6. While loops",
        "explain": "Repeat while a condition holds.",
        "code": "let i = 0\nwhile i < 3:\n    print(i)\n    i = i + 1",
    },
    {
        "title": "7. Pattern matching",
        "explain": "'match' compares a value against patterns — literals, a "
                   "capture name, or '_' for anything.",
        "code": 'let cmd = "go"\nmatch cmd:\n    case "go":\n        print("moving!")\n    case _:\n        print("unknown command")',
    },
    {
        "title": "8. Pipes, lambdas, dicts, and Python modules",
        "explain": "'|>' pipes a value into a function (x |> f means f(x)). "
                   "'fn(x) -> expr' makes a quick lambda. You can import ANY "
                   "Python module and use it directly.",
        "code": 'import math\nlet square = fn(x) -> x * x\nprint(square(6))\nprint([3, 1, 2] |> sorted)\nprint(math.sqrt(144) |> int)',
    },
    {
        "title": "9. Viper catches footguns",
        "explain": "Viper turns some of Python's silent traps into clear errors. "
                   "A mutable default argument like 'x=[]' is rejected before it "
                   "can bite you — watch:",
        "code": "fn bad(x=[]):\n    return x",
        "expect_error": True,
    },
]


def _run_example(code: str, expect_error: bool = False) -> None:
    print(dim("  code:"))
    for line in code.splitlines():
        print(dim("    " + line))
    print(dim("  output:"))
    try:
        run_source(code, "<tutorial>")
        if expect_error:
            print("    (no error — unexpected)")
    except ViperError as e:
        for line in str(e).splitlines():
            print("    " + line)


def _prompt_continue() -> bool:
    try:
        answer = input("\n" + dim("Press Enter to continue, or 'q' to quit: "))
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() != "q"


def run_tutorial() -> int:
    print(header("Welcome to Viper — a 5-minute tour"))
    print()
    print("Viper transpiles to Python, so it speaks to every Python module,")
    print("while aiming to be clearer and friendlier than Python itself.")
    print()
    if not _prompt_continue():
        print("\nNo problem — come back any time with " + bold("viper help") + ".")
        return 0

    for lesson in LESSONS:
        print()
        print(header(lesson["title"]))
        print(lesson["explain"])
        print()
        _run_example(lesson["code"], lesson.get("expect_error", False))
        if lesson is not LESSONS[-1]:
            if not _prompt_continue():
                print("\nStopped early — run " + bold("viper help") + " to resume.")
                return 0

    print()
    print(header("That's the tour!"))
    print("Next steps:")
    print("  " + bold("viper repl") + "                 play interactively")
    print("  " + bold("viper run yourfile.vp") + "      run a program")
    print("  " + bold("viper help <topic>") + "         quick reference (try: viper topics)")
    return 0
