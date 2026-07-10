"""C FFI via clib() — call into C libraries from Viper (built on ctypes)."""
import ctypes.util
import sys

import pytest

from viper import std
from viper.runtime import run_source


def _c_stdlib():
    """The C standard library on this OS, as a loaded CLib."""
    if sys.platform == "win32":
        return std.clib("msvcrt")
    name = ctypes.util.find_library("c")
    if not name:
        pytest.skip("no C standard library found")
    return std.clib(name)


def test_typed_call_strlen_with_auto_encoding():
    strlen = _c_stdlib().func("strlen", "int", ["str"])
    assert strlen("viper") == 5           # Python str auto-encoded to char*
    assert strlen(b"abc") == 3            # bytes pass through unchanged


def test_str_return_is_decoded():
    getenv = _c_stdlib().func("getenv", "str", ["str"])
    got = getenv("PATH")
    assert got is None or isinstance(got, str)   # char* decoded to str


def test_double_math_from_c():
    # pow(double, double) -> double exercises non-int arg/return types
    lib = _c_stdlib()
    cpow = lib.func("pow", "double", ["double", "double"])
    assert cpow(2.0, 10.0) == pytest.approx(1024.0)


def test_unknown_type_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown C type"):
        _c_stdlib().func("strlen", "frobnicate", [])


def test_missing_function_is_a_clear_error():
    with pytest.raises(AttributeError, match="not found"):
        _c_stdlib().func("no_such_c_function_xyz", "int", [])


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 API")
def test_win32_stdcall_quick_path():
    k = std.clib("kernel32", abi="win")
    assert isinstance(k.GetTickCount(), int) and k.GetTickCount() > 0


def test_clib_is_in_prelude_and_documented():
    assert "clib" in std.STD_NAMES
    sig, doc = std.STD_DOCS["clib"]
    assert sig.startswith("clib(")
    assert "C shared library" in doc


def test_clib_end_to_end_through_viper(capsys):
    name = "msvcrt" if sys.platform == "win32" else (ctypes.util.find_library("c") or "")
    if not name:
        pytest.skip("no C standard library found")
    run_source(
        f'const libc = clib("{name}")\n'
        'const strlen = libc.func("strlen", "int", ["str"])\n'
        'print("len", strlen("viper"))\n'
    )
    assert "len 5" in capsys.readouterr().out
