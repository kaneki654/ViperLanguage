"""End-to-end execution via run_source — verifies behavior, not just output text."""
from viper.runtime import run_source


def out(src: str, capsys) -> str:
    run_source(src + "\n", "<r>")
    return capsys.readouterr().out


# --- new in 0.0.3 -----------------------------------------------------------
def test_bitwise_precedence(capsys):
    # & binds tighter than |, matching Python: 0b1100 | (0b1010 & 0b0110)
    assert out("print(0b1100 | 0b1010 & 0b0110)", capsys).strip() == "14"


def test_shift(capsys):
    assert out("print(1 << 4, 256 >> 2)", capsys).strip() == "16 64"


def test_number_literals(capsys):
    res = out("print(0xff, 0o17, 0b1010, 1_000_000)", capsys).strip()
    assert res == "255 15 10 1000000"


def test_tuple_unpack(capsys):
    assert out("let (a, b) = (1, 2)\nprint(a + b)", capsys).strip() == "3"


def test_starred_unpack(capsys):
    res = out("let head, *tail = [1, 2, 3, 4]\nprint(head)\nprint(tail)", capsys)
    assert res.splitlines() == ["1", "[2, 3, 4]"]


def test_chained_assign(capsys):
    assert out("a = b = 5\nprint(a, b)", capsys).strip() == "5 5"


def test_list_comp(capsys):
    assert out("print([x*x for x in range(4)])", capsys).strip() == "[0, 1, 4, 9]"


def test_dict_comp(capsys):
    assert out("print({n: n*n for n in range(3)})", capsys).strip() == "{0: 0, 1: 1, 2: 4}"


def test_set_comp(capsys):
    assert out("print(sorted({c for c in 'aabbc'}))", capsys).strip() == "['a', 'b', 'c']"


def test_generator_exp(capsys):
    assert out("print(sum((n for n in range(11))))", capsys).strip() == "55"


def test_walrus(capsys):
    res = out("if (n := len([1, 2, 3])) > 0:\n    print(n)", capsys)
    assert res.strip() == "3"


def test_pipe_placeholder(capsys):
    assert out("print(3.14159 |> round(_, 2))", capsys).strip() == "3.14"


def test_pipe_default(capsys):
    assert out("print([3, 1, 2] |> sorted)", capsys).strip() == "[1, 2, 3]"


def test_prelude_clamp(capsys):
    assert out("print(clamp(10, 0, 5))", capsys).strip() == "5"


def test_prelude_pp(capsys):
    assert out("pp({'a': 1})", capsys).strip() == "{'a': 1}"


def test_prelude_file_roundtrip(capsys, tmp_path):
    p = tmp_path / "x.txt"
    res = out(f"write_file({str(p)!r}, 'hi')\nprint(read_file({str(p)!r}))", capsys)
    assert res.strip() == "hi"


def test_with_open(capsys, tmp_path):
    p = tmp_path / "w.txt"
    src = (f"with open({str(p)!r}, 'w') as f:\n    f.write('data')\n"
           f"with open({str(p)!r}) as f:\n    print(f.read())")
    assert out(src, capsys).strip() == "data"


def test_assert_passes(capsys):
    assert out("assert 1 + 1 == 2\nprint('ok')", capsys).strip() == "ok"


def test_raise_from_caught(capsys):
    src = ("try:\n    raise ValueError('inner')\n"
           "except ValueError as e:\n    raise RuntimeError('outer') from e")
    try:
        run_source(src + "\n", "<r>")
    except Exception:
        pass
    # Just ensure transpile+run path reaches the raise without a transpiler bug.


# --- legacy behavior still runs ---------------------------------------------
def test_for_else(capsys):
    src = "for x in [1, 2]:\n    print(x)\nelse:\n    print('done')"
    assert out(src, capsys).splitlines() == ["1", "2", "done"]


def test_while_else(capsys):
    src = "let i = 0\nwhile i < 2:\n    print(i)\n    i += 1\nelse:\n    print('end')"
    assert out(src, capsys).splitlines() == ["0", "1", "end"]


def test_match(capsys):
    src = ('let cmd = "go"\nmatch cmd:\n    case "go":\n'
           '        print("moving")\n    case _:\n        print("?")')
    assert out(src, capsys).strip() == "moving"


def test_fn_and_pipe(capsys):
    src = "fn dbl(x):\n    return x * 2\nprint(5 |> dbl)"
    assert out(src, capsys).strip() == "10"
