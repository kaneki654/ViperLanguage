import pytest
from viper.errors import ViperError
from viper.codegen import transpile


def parse(src: str):
    return transpile(src + "\n", "<e>")


def test_parse_error_let_eq_1():
    with pytest.raises(ViperError, match="unexpected"):
        parse("let = 1")


def test_unclosed_bracket():
    with pytest.raises(ViperError):
        parse("let x = [1, 2")


def test_bare_except_rejected():
    with pytest.raises(ViperError, match="bare 'except"):
        parse("try:\n    pass\nexcept:\n    pass")


def test_none_compare_rejected():
    with pytest.raises(ViperError, match="is None"):
        parse("let x = None\nprint(x == None)")


def test_shadow_builtin_let():
    with pytest.raises(ViperError, match="shadows the builtin"):
        parse("let list = 1")


def test_mutable_default_rejected():
    with pytest.raises(ViperError, match="footgun"):
        parse("fn f(x=[]):\n    return x")

