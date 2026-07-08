import textwrap
import time

from viper.analysis import (
    analyze, complete, signature_help, hover, module_members,
    definition, document_symbols, parse_error,
    GROUP_LOCAL, GROUP_DOCUMENT, GROUP_BUILTIN, GROUP_KEYWORD, GROUP_AUTOIMPORT,
)

SRC = textwrap.dedent('''\
    import math
    import collections as coll
    from functools import lru_cache as cache

    fn add(a: int, b: int = 1) -> int:
        "add two numbers"
        return a + b

    async fn fetch(url):
        return url

    class Point:
        fn __init__(self, x, y):
            self.x = x
            self.y = y

    let total = add(2, 3)
''')

L = SRC.count("\n")     # line index of anything appended to SRC


def test_document_symbols():
    info = analyze(SRC)
    assert info.fns["add"].signature() == "fn add(a: int, b: int = …) -> int"
    assert info.fns["add"].doc == "add two numbers"
    assert info.fns["fetch"].is_async
    assert "Point" in info.classes
    assert "__init__" in info.classes["Point"].methods
    assert "total" in info.lets
    assert info.imports["math"] == "math"
    assert info.imports["coll"] == "collections"          # import ... as
    assert info.from_imports["cache"] == ("functools", "lru_cache")


def test_default_completions_include_document_fns():
    labels = {c.label: c for c in complete(SRC, 16, 0)}
    assert "add" in labels and labels["add"].detail.startswith("fn add(")
    assert "Point" in labels and labels["Point"].kind == "class"
    assert "total" in labels
    assert "let" in labels          # keywords still present
    assert "print" in labels        # builtins still present
    assert "pp" in labels           # prelude documented
    assert "pretty-print" in labels["pp"].documentation.lower()
    assert "sha256" in labels        # batteries-included stdlib present


def test_dot_completion_python_module():
    src = SRC + "math."
    items = {c.label: c for c in complete(src, L, 5)}
    assert "sqrt" in items
    assert "square root" in items["sqrt"].documentation.lower()


def test_dot_completion_respects_import_alias():
    src = SRC + "coll."
    items = {c.label for c in complete(src, L, 5)}
    assert "OrderedDict" in items and "defaultdict" in items


def test_dot_completion_vp_module(tmp_path):
    (tmp_path / "helpers.vp").write_text(
        "fn shortcut(x):\n    return x\n\nclass Tool:\n    pass\n")
    src = "import helpers\nhelpers."
    items = {c.label: c for c in complete(src, 1, 8, workspace_dirs=[str(tmp_path)])}
    assert items["shortcut"].detail == "fn shortcut(x)"
    assert items["Tool"].kind == "class"


def test_from_import_member_completion():
    src = SRC + "from math import s"
    labels = {c.label for c in complete(src, L, 18)}
    assert "sqrt" in labels


def test_import_context_lists_modules():
    src = SRC + "import js"
    labels = {c.label for c in complete(src, L, 9)}
    assert "json" in labels


def test_async_context():
    src = SRC + "async "
    labels = [c.label for c in complete(src, L, 6)]
    assert labels == ["fn", "for", "with"]


def test_no_completions_in_comments_or_strings():
    assert complete(SRC + "# math.", L, 7) == []
    assert complete(SRC + 'let s = "math.', L, 14) == []


def test_signature_help_viper_fn_broken_buffer():
    src = SRC + "add(1, "
    sig = signature_help(src, L, 7)
    assert sig is not None
    assert sig.label.startswith("fn add(")
    assert sig.active_parameter == 1


def test_signature_help_python_fn():
    src = SRC + "math.sqrt("
    sig = signature_help(src, L, 10)
    assert sig is not None
    assert "sqrt" in sig.label


def test_signature_help_class_init():
    src = SRC + "Point(3, "
    sig = signature_help(src, L, 9)
    assert sig is not None
    assert sig.label == "class Point(x, y)"
    assert sig.active_parameter == 1


def test_hover_viper_fn_and_import():
    h = hover(SRC, 16, 13)          # over 'add' in let total = add(2, 3)
    assert "fn add(" in h and "add two numbers" in h
    h2 = hover(SRC, 0, 8)           # over 'math'
    assert "import math" in h2


def test_hover_keyword():
    src = "spawn:\n    pass\n"
    h = hover(src, 0, 2)
    assert "viper help spawn" in h


def test_module_members_never_crashes_on_junk():
    assert module_members("no_such_module_xyz") == []
    assert module_members("....") == []


# ------------------------------------------------------- 1.2.0b1 features

def test_ranking_locals_before_builtins_before_keywords():
    items = complete(SRC, 16, 0)
    group = {c.label: c.sort_group for c in items if c.kind != "snippet"}
    assert group["add"] == GROUP_DOCUMENT
    assert group["total"] == GROUP_DOCUMENT
    assert group["print"] == GROUP_BUILTIN
    assert group["while"] == GROUP_KEYWORD
    assert group["add"] < group["print"] < group["while"]


def test_inferred_str_dot_completion():
    src = SRC + 'let name = "viper"\nname.'
    items = {c.label: c for c in complete(src, L + 1, 5)}
    assert "upper" in items and "split" in items
    assert items["upper"].kind == "method"
    assert items["upper"].sort_group == GROUP_LOCAL


def test_inferred_list_and_dict_dot_completion():
    src = SRC + "let xs = [1, 2]\nxs."
    assert "append" in {c.label for c in complete(src, L + 1, 3)}
    src = SRC + 'let d = {"a": 1}\nd.'
    assert "items" in {c.label for c in complete(src, L + 1, 2)}


def test_inferred_class_instance_dot_completion():
    src = SRC + "let p = Point(1, 2)\np."
    items = {c.label: c for c in complete(src, L + 1, 2)}
    assert "x" in items and items["x"].kind == "property"     # self.x in __init__
    assert "__init__" in items or "x" in items


def test_annotated_param_dot_completion():
    src = textwrap.dedent('''\
        fn shout(msg: str):
            msg.
            pass
    ''')
    assert "upper" in {c.label for c in complete(src, 1, 8)}


def test_self_dot_completion_inside_class():
    src = textwrap.dedent('''\
        class Greeter:
            fn __init__(self, name):
                self.name = name
            fn greet(self):
                self.
    ''')
    items = {c.label: c for c in complete(src, 4, 13)}
    assert "name" in items and items["name"].kind == "property"
    assert "greet" in items and items["greet"].kind == "method"


def test_method_signature_help_on_inferred_local():
    src = SRC + 'let name = "viper"\nname.replace('
    sig = signature_help(src, L + 1, 13)
    assert sig is not None and "replace" in sig.label


def test_broken_buffer_still_completes_own_symbols():
    # """docstrings""" are not Viper syntax: the file never parses, but the
    # line-scan fallback must still find the user's definitions
    src = textwrap.dedent('''\
        fn greet(name):
            """python-style docstring that Viper cannot parse"""
            return name

        class Widget:
            fn render(self):
                pass

        let counter = 0
    ''')
    assert parse_error(src) is not None      # sanity: really is a broken file
    labels = {c.label for c in complete(src + "\ngre", src.count("\n") + 1, 3)}
    assert "greet" in labels and "Widget" in labels and "counter" in labels


def test_auto_import_completion_from_workspace(tmp_path):
    (tmp_path / "shapes.vp").write_text(
        "fn area(w, h):\n    return w * h\n\nclass Circle:\n    pass\n")
    src = "import math\n\nar"
    items = {c.label: c for c in complete(src, 2, 2, workspace_dirs=[str(tmp_path)],
                                          cache_key="file:///proj/main.vp")}
    assert "area" in items
    c = items["area"]
    assert c.sort_group == GROUP_AUTOIMPORT
    assert "auto-import from shapes" in c.detail
    line, text = c.extra_edit
    assert line == 1 and text == "from shapes import area\n"    # after import math


def test_auto_import_skips_already_imported(tmp_path):
    (tmp_path / "shapes.vp").write_text("fn area(w, h):\n    return w\n")
    src = "from shapes import area\n\nar"
    items = {c.label: c for c in complete(src, 2, 2, workspace_dirs=[str(tmp_path)])}
    assert items["area"].sort_group == GROUP_DOCUMENT      # in scope, not auto-import


def test_snippets_offered_at_statement_position():
    items = {c.label: c for c in complete(SRC, 16, 0)}
    assert "fn" in items                                   # plain keyword
    fn_snip = [c for c in complete(SRC, 16, 0) if c.kind == "snippet" and c.label == "fn"]
    assert fn_snip and fn_snip[0].snippet and "${1:name}" in fn_snip[0].insert_text


def test_document_symbols_outline():
    syms = {s.name: s for s in document_symbols(SRC)}
    assert syms["add"].kind == "function" and syms["add"].line == 4      # 0-based
    assert syms["Point"].kind == "class"
    assert [c.name for c in syms["Point"].children] == ["__init__"]
    assert syms["total"].kind == "variable"


def test_definition_in_document():
    src = SRC + "add(1, 2)"
    assert definition(src, L, 1) == (None, 4)              # fn add at line 4
    src = SRC + "Point(1, 2)"
    assert definition(src, L, 2) == (None, 11)             # class Point at line 11


def test_definition_across_vp_modules(tmp_path):
    (tmp_path / "helpers.vp").write_text("fn shortcut(x):\n    return x\n")
    src = "import helpers\nhelpers.shortcut(1)"
    path, line = definition(src, 1, 10, workspace_dirs=[str(tmp_path)])
    assert path.endswith("helpers.vp") and line == 0
    src = "from helpers import shortcut\nshortcut(1)"
    path, line = definition(src, 1, 3, workspace_dirs=[str(tmp_path)])
    assert path.endswith("helpers.vp") and line == 0


def test_completion_is_fast_when_buffer_unchanged():
    big = SRC + "\n".join(f"fn f{i}(a, b):\n    return a" for i in range(150))
    key = "file:///perf.vp"
    complete(big, 3, 0, cache_key=key)                     # cold: parse once
    t0 = time.perf_counter()
    for _ in range(20):
        complete(big, 3, 0, cache_key=key)                 # warm: cache hits
    per_request = (time.perf_counter() - t0) / 20
    assert per_request < 0.05, f"warm completion too slow: {per_request*1000:.1f}ms"
