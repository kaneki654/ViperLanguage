"""The stdlib prelude, exercised the way real Viper programs use it:
through transpile/run, the shadow guard, `viper build`, the CLI, and the
editor analysis engine."""
import subprocess
import sys

import pytest

from viper import analysis
from viper.cli import build_file, main
from viper.codegen import transpile
from viper.errors import ViperError
from viper.runtime import run_source


def test_stdlib_available_without_import(capsys):
    run_source('print(sha256("hi"))\nprint(b64("ok"))\nprint(hexdump("AB"))')
    out = capsys.readouterr().out
    assert "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4" in out
    assert "b2s=" in out                       # b64("ok")
    assert "|AB|" in out


def test_bytes_literal_roundtrips_through_stdlib(capsys):
    run_source(r'print(to_hex(b"AB\x00"))' + "\nprint(sha256(b'abc'))")
    out = capsys.readouterr().out
    assert "414200" in out                      # 'A','B',NUL
    # sha256 of the bytes equals sha256 of the str "abc"
    import hashlib
    assert hashlib.sha256(b"abc").hexdigest() in out


def test_pipe_into_stdlib(capsys):
    run_source('print("ZmxhZ3tva30=" |> unb64 |> bytes.decode(_))')
    assert "flag{ok}" in capsys.readouterr().out


def test_stdlib_names_are_shadowable():
    # prelude names are plain namespace entries, not guarded builtins
    py, _ = transpile("let sha256 = 5\nprint(sha256)")
    assert "sha256 = 5" in py


def test_real_builtins_still_guarded():
    with pytest.raises(ViperError) as e:
        transpile("let hash = 1")          # `hash` is a genuine Python builtin
    assert "shadows the builtin" in str(e.value)


def test_build_output_is_self_contained(tmp_path):
    src = tmp_path / "prog.vp"
    src.write_text('print(sha256("hi"))\n', encoding="utf-8")
    out = tmp_path / "prog.py"
    assert build_file(str(src), str(out)) == 0
    text = out.read_text(encoding="utf-8")
    # the helper's real source is inlined, not merely imported
    assert "def sha256(data)" in text
    assert "def _as_bytes(data)" in text
    # and it actually runs as a plain python file
    r = subprocess.run([sys.executable, str(out)], capture_output=True, text=True)
    assert r.returncode == 0
    assert "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4" in r.stdout


def test_cli_dash_c_one_liner(capsys):
    assert main(["-c", 'print(sha256("hi"))']) == 0
    assert "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4" in capsys.readouterr().out


def test_cli_dash_c_missing_arg(capsys):
    assert main(["-c"]) == 2


def test_editor_completes_and_documents_stdlib():
    items = {c.label: c for c in analysis.complete("sha", 0, 3)}
    assert "sha256" in items
    c = items["sha256"]
    assert c.kind == "function"
    assert c.detail.startswith("sha256(")
    assert "SHA-256" in c.documentation


def test_editor_hover_and_signature_for_stdlib():
    h = analysis.hover("let d = sha256(x)", 0, 9)     # over 'sha256'
    assert h is not None and "sha256(" in h
    sig = analysis.signature_help("hmac256(", 0, 8)
    assert sig is not None and sig.label.startswith("hmac256(")
    assert sig.parameters[:2] == ["key", "data"]
