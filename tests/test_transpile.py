"""Substring checks on transpiler output — fast, no code is executed."""
from viper.codegen import transpile


def py(src: str) -> str:
    return transpile(src + "\n", "<t>")[0]


# --- legacy / 0.0.2 features still work --------------------------------------
def test_let_and_assign():
    out = py("let x = 1\nx = 2")
    assert "x = 1" in out and "x = 2" in out


# --- 1.3.0b1: bytes and raw string literals pass straight through ------------
def test_bytes_literals():
    assert 'b"\\x00AB"' in py(r'let x = b"\x00AB"')
    assert "b'abc'" in py("let x = b'abc'")


def test_raw_string_literals():
    assert 'r"\\d+"' in py(r'let pat = r"\d+"')
    assert "rb'\\x00'" in py(r"let x = rb'\x00'")


def test_aug_assign():
    assert "x += 1" in py("let x = 0\nx += 1")


def test_if_elif_else():
    out = py("if a:\n    pass\nelif b:\n    pass\nelse:\n    pass")
    assert "if " in out and "elif " in out and "else:" in out


def test_while_for_else():
    out = py("while True:\n    pass\nelse:\n    pass\n"
             "for x in xs:\n    pass\nelse:\n    pass")
    assert out.count("else:") == 2


def test_match_patterns():
    out = py('match v:\n    case 1 | 2:\n        pass\n'
             '    case [x, y]:\n        pass\n'
             '    case _ as z:\n        pass')
    assert "match " in out and "case 1 | 2" in out and "case _ as z" in out


def test_fn_typed_decorated():
    out = py("@dec\nfn f(x: int = 1) -> int:\n    return x")
    assert "@dec" in out and "def f(x: int = 1) -> int:" in out


def test_class():
    out = py("class P:\n    pass")
    assert "class P:" in out


def test_try_except_finally():
    out = py("try:\n    pass\nexcept ValueError as e:\n    pass\n"
             "else:\n    pass\nfinally:\n    pass")
    assert "try:" in out and "except ValueError as e:" in out \
        and "finally:" in out


def test_spawn_uses_threading():
    out = py("spawn:\n    pass")
    assert "threading" in out and "Thread" in out


def test_lambda_and_ternary():
    out = py("let f = fn(x) -> x * x\nlet y = 1 if True else 0")
    assert "lambda x" in out and "if True else 0" in out


def test_fstring_and_slices():
    out = py('let n = "x"\nprint(f"hi {n}")\nlet xs = [1,2,3]\n'
             'let s = xs[0:2]\nlet t = xs[::2]')
    assert 'f"hi {n}"' in out and "[0:2]" in out and "[::2]" in out


# --- new in 0.0.3 -----------------------------------------------------------
def test_chained_assign():
    out = py("a = b = 1")
    assert "a = b = 1" in out


def test_subscript_attr_assign():
    out = py("a[0] = 1\nobj.x = 2")
    assert "a[0] = 1" in out and "obj.x = 2" in out


def test_tuple_unpack_let():
    out = py("let (a, b) = (1, 2)")
    assert "a, b = " in out and "(1, 2)" in out


def test_typed_let():
    out = py('let name: str = "Ada"')
    assert 'name: str = "Ada"' in out


def test_starred_unpack():
    out = py("let head, *tail = [1, 2, 3]")
    assert "head, *tail = " in out


def test_with():
    out = py('with open("x") as f:\n    pass')
    assert "with open" in out and "as f:" in out


def test_assert():
    out = py('assert x > 0, "pos"')
    assert "assert " in out and '"pos"' in out


def test_global_nonlocal():
    out = py("global a, b\nnonlocal c")
    assert "global a, b" in out and "nonlocal c" in out


def test_raise_from():
    out = py("raise A() from e")
    assert "raise A() from e" in out


def test_bitwise_shift():
    out = py("let a = 1 | 2 ^ 3 & 4 << 5 >> 6")
    s = out
    assert "|" in s and "^" in s and "&" in s and "<<" in s and ">>" in s


def test_comprehensions():
    out = py(
        "let a = [x for x in r]\n"
        "let b = {x for x in r}\n"
        "let c = {k: v for k, v in items}\n"
        "let d = (x for x in r)"
    )
    assert "[x for x in r]" in out
    assert "{x for x in r}" in out
    assert "{k: v for k, v in items}" in out
    assert "(x for x in r)" in out


def test_walrus_in_if_and_paren():
    out = py("if (n := len(xs)) > 0:\n    print(n)\n"
             "let y = (z := 7)")
    assert "(n := len(xs))" in out and "(z := 7)" in out


def test_pipe_placeholder():
    out = py("let x = 16 |> round(_, 1)")
    assert "round(16, 1)" in out


def test_pipe_default():
    out = py("let x = [3, 1] |> sorted")
    assert "(sorted)" in out and "[3, 1]" in out


def test_number_literals():
    out = py("let a = 0xff\nlet b = 0o17\nlet c = 0b1010\nlet d = 1_000_000\nlet e = 1e9")
    assert "0xff" in out and "0o17" in out and "0b1010" in out \
        and "1_000_000" in out and "1e9" in out

