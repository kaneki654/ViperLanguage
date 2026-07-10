"""`const` — compile-time-enforced immutable bindings (Python can't do this)."""
import pytest

from viper.codegen import transpile
from viper.errors import ViperError
from viper.runtime import run_source
from viper.typecheck import check_source


def bad(src):
    return len(check_source(src)) > 0


# --------------------------------------------------- immutability enforced

@pytest.mark.parametrize("src,frag", [
    ("const K = 1\nK = 2", "cannot reassign"),
    ("const K = 1\nK += 1", "cannot reassign"),
    ("const K = 1\nlet K = 2", "cannot rebind"),
    ("const K = 1\nconst K = 2", "already declared const"),
])
def test_reassignment_is_an_error(src, frag):
    issues = check_source(src)
    assert issues and frag in issues[0].message
    assert "line 1" in issues[0].message or "declared const" in issues[0].message


def test_reassignment_across_scopes_flagged():
    assert bad("const A = 1\nfn f():\n    A = 2\n")
    assert bad("const A = 1\nfn f():\n    const A = 2\n")


# -------------------------------------------- but mutation is still allowed

def test_object_mutation_is_allowed():
    # const freezes the NAME, not the object it points at
    assert check_source("const xs = []\nxs.append(1)\nxs[0] = 9") == []
    assert check_source('const cfg = {}\ncfg["a"] = 1') == []


def test_const_participates_in_type_checking():
    assert bad('const n: int = "no"')
    assert check_source('const n: int = 5') == []
    # a const's inferred type flows onward
    assert bad('const s = "hi"\nlet x: int = s')


# ------------------------------------------------------------ end to end

def test_const_transpiles_to_plain_binding():
    out, _ = transpile("const PI = 3.14159\n")
    assert "PI = 3.14159" in out
    out2, _ = transpile("const K: str = \"x\"\n")
    assert 'K: str = "x"' in out2


def test_const_runs(capsys):
    run_source('const GREETING = "hi"\nprint(GREETING)\n')
    assert "hi" in capsys.readouterr().out


def test_reassign_blocks_run():
    with pytest.raises(ViperError) as e:
        run_source("const K = 1\nK = 2\n")
    assert "cannot reassign" in str(e.value)


def test_const_shadowing_builtin_is_rejected():
    with pytest.raises(ViperError) as e:
        transpile("const int = 5\n")
    assert "shadows the builtin" in str(e.value)


# --------------------------------------------------------- editor support

def test_const_appears_in_completions_labelled():
    from viper import analysis
    items = {c.label: c for c in analysis.complete("const MAX = 100\nMA", 1, 2)}
    assert "MAX" in items
    assert items["MAX"].detail == "const"


def test_const_hover_says_const():
    from viper import analysis
    h = analysis.hover('const KEY = "s"\nprint(KEY)', 1, 6)
    assert h is not None and "const KEY" in h
