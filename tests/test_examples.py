"""Every shipped example must at least transpile; hello.vp must also run."""
import os
import pytest
from viper.codegen import transpile
from viper.runtime import run_source

EX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")


def _every_vp():
    return sorted(f for f in os.listdir(EX) if f.endswith(".vp"))


@pytest.mark.parametrize("name", _every_vp())
def test_examples_transpile(name):
    path = os.path.join(EX, name)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    transpile(src, path)   # must not raise


def test_hello_runs(capsys):
    path = os.path.join(EX, "hello.vp")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    run_source(src, path)
    out = capsys.readouterr().out
    assert "Hello, Viper!" in out
    assert "circle area:" in out
    assert "25" in out  # square(5)

