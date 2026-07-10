"""Static type checking: `let x: int = "hello"` is now a transpile-time error.

Split into three groups:
  - mismatches that MUST be caught,
  - valid code that MUST NOT be flagged (false positives are the enemy),
  - end-to-end: the error actually blocks `run`/`build` and reaches the editor.
"""
import pytest

from viper.codegen import transpile
from viper.errors import ViperError
from viper.runtime import run_source
from viper.typecheck import check_source


def issues(src):
    return check_source(src)


def first_msg(src):
    got = check_source(src)
    return got[0].message if got else ""


# ------------------------------------------------------ must be caught

@pytest.mark.parametrize("src,frag", [
    ('let x: int = "hello"', "annotated 'int'"),
    ('let s: str = 42', "annotated 'str'"),
    ('let x: int = 3.14', "value is a float"),
    ('let b: bool = 5', "annotated 'bool'"),
    ('let b: bytes = "x"', "annotated 'bytes'"),
    ('let d: dict = [1, 2]', "value is a list"),
    ('let xs: list = {1: 2}', "value is a dict"),
    ('let t: tuple = [1]', "value is a list"),
    ('let x: int = None', "value is None"),
])
def test_flags_literal_mismatch(src, frag):
    got = check_source(src)
    assert got, f"expected a type error for: {src}"
    assert frag in got[0].message


def test_flags_through_typed_variable():
    # d is inferred str, so assigning it to an int annotation is an error
    assert issues('let d = sha256("a")\nlet n: int = d')
    assert issues('let s: str = "hi"\nlet n: int = s')


def test_flags_stdlib_and_builtin_call_results():
    assert issues('let n: int = sha256("a")')        # sha256 -> str
    assert issues('let s: str = len("a")')            # len -> int
    assert issues('let x: int = b64("a")')            # b64 -> str


def test_flags_user_fn_return_type():
    src = "fn make() -> str:\n    return 1\n"
    assert "return" in first_msg(src)


def test_flags_let_from_user_fn_return():
    src = ("fn tag() -> str:\n    return \"x\"\n"
           "let n: int = tag()\n")
    assert issues(src)


def test_flags_annotated_param_misuse():
    src = "fn f(n: int):\n    let s: str = n\n"
    assert issues(src)


# ------------------------------------------------ must NOT be flagged

@pytest.mark.parametrize("src", [
    'let x: int = 5',
    'let x: float = 5',            # int widens to float
    'let x: int = True',          # bool is an int
    'let x: str = "hi"',
    'let b: bytes = b"\\x00"',
    'let xs: list = [1, 2, 3]',
    'let d: dict = {"a": 1}',
    'let s: set = {1, 2}',
    'let x: int = 2 + 3',          # arithmetic: unknown, left alone
    'let x: int = a + b',          # unknown names
    'let p: Point = Point(1, 2)',  # custom class, matches
    'let p: Animal = make()',      # unknown call, left alone
    'let x: MyType = "anything"',  # unknown annotation, not checked
    'let x: int = foo()',          # unknown fn, left alone
    'let n = 5\nlet m: int = n',   # inferred int -> int, fine
    'let x: float = round(3.14159, 2)',  # round(): unknown return, left alone
    'let x: list = [c for c in "hi"]',   # comprehension -> list
])
def test_does_not_flag_valid(src):
    assert check_source(src) == [], f"false positive on: {src}"


def test_custom_class_return_not_flagged_against_class():
    src = ("class Point:\n    fn __init__(self, x):\n        self.x = x\n"
           "let p: Point = Point(1)\n")
    assert check_source(src) == []


def test_subclass_safety_no_false_positive():
    # a value from an unknown call could be a subclass — never flag it
    src = "fn get() -> int:\n    return 1\nlet x: bool = get()"
    # get() returns int; annotation bool does NOT accept int -> this IS flagged
    assert issues(src)
    # but an *unknown* producer must not be flagged
    assert check_source("let x: bool = mystery()") == []


# ------------------------------------------------ end to end

def test_transpile_raises_on_mismatch():
    with pytest.raises(ViperError) as e:
        transpile('let x: int = "hello"\n')
    text = str(e.value)
    assert "annotated 'int'" in text
    assert "-->" in text and "^" in text        # caret block, like parse errors


def test_run_source_blocks_execution(capsys):
    with pytest.raises(ViperError):
        run_source('print("should not run")\nlet x: int = "no"\n')
    # the print must not have executed — the error is raised before exec
    assert "should not run" not in capsys.readouterr().out


def test_valid_program_still_runs(capsys):
    run_source('let n: int = 3\nlet msg: str = "ok"\nprint(n, msg)\n')
    assert "3 ok" in capsys.readouterr().out


def test_issue_reports_correct_line():
    src = 'let a = 1\nlet b = 2\nlet c: int = "bad"\n'
    got = check_source(src)
    assert got and got[0].line == 3


def test_issues_are_sorted():
    src = 'let a: int = "x"\nlet b: str = 9\n'
    got = check_source(src)
    assert [i.line for i in got] == [1, 2]
