import subprocess
import sys
import textwrap

from viper.runtime import run_source
from viper.codegen import transpile


def test_yield_generator():
    ns = run_source(textwrap.dedent("""\
        fn counter(n):
            let i = 0
            while i < n:
                yield i
                i += 1
        let out = list(counter(3))
    """))
    assert ns["out"] == [0, 1, 2]


def test_yield_from():
    ns = run_source(textwrap.dedent("""\
        fn inner():
            yield 1
            yield 2
        fn outer():
            yield from inner()
            yield 3
        let out = list(outer())
    """))
    assert ns["out"] == [1, 2, 3]


def test_async_fn_await():
    ns = run_source(textwrap.dedent("""\
        import asyncio
        async fn double(x):
            await asyncio.sleep(0)
            return x * 2
        let out = asyncio.run(double(21))
    """))
    assert ns["out"] == 42


def test_async_fn_transpiles_to_async_def():
    py, _ = transpile("async fn f():\n    pass\n")
    assert "async def f():" in py


def test_vp_import(tmp_path):
    (tmp_path / "mod.vp").write_text("fn triple(x):\n    return x * 3\n")
    (tmp_path / "main.vp").write_text("import mod\nlet out = mod.triple(4)\n")
    r = subprocess.run([sys.executable, "-m", "viper.cli", "run",
                        str(tmp_path / "main.vp")], capture_output=True, text=True)
    assert r.returncode == 0


def test_build(tmp_path):
    src = tmp_path / "x.vp"
    src.write_text('print("hi")\n')
    r = subprocess.run([sys.executable, "-m", "viper.cli", "build", str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    out = tmp_path / "x.py"
    assert out.exists()
    r2 = subprocess.run([sys.executable, str(out)], capture_output=True, text=True)
    assert r2.stdout.strip() == "hi"


def test_fmt(tmp_path):
    f = tmp_path / "m.vp"
    f.write_text("let x = 1   \n\n\n\n\nprint(x)\n")
    r = subprocess.run([sys.executable, "-m", "viper.cli", "fmt", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert f.read_text() == "let x = 1\n\n\nprint(x)\n"
