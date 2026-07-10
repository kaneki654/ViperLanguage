"""Built-in linter: unused-import warnings (Python needs flake8 for this).

Warnings must never block run/build, and must never fire on a used import —
false positives are the enemy, exactly like the type checker.
"""
import pytest

from viper.cli import lint_file
from viper.codegen import transpile
from viper.runtime import run_source
from viper.typecheck import check_source


def warnings(src):
    return [i for i in check_source(src) if i.severity == "warning"]


# ------------------------------------------------------- flagged (unused)

def test_flags_unused_plain_import():
    w = warnings("import os\nprint(1)\n")
    assert len(w) == 1 and "os" in w[0].message and "never used" in w[0].message


def test_flags_unused_alias():
    assert warnings("import numpy as np\nprint(1)\n")


def test_flags_only_the_unused_from_import():
    w = warnings("from os import getcwd, sep\nprint(getcwd())\n")
    assert len(w) == 1 and "sep" in w[0].message


# --------------------------------------------------- NOT flagged (used)

@pytest.mark.parametrize("src", [
    "import os\nprint(os.getcwd())\n",
    "import math\nprint(f\"{math.pi}\")\n",          # used only in an f-string
    "from os import sep\nprint(sep)\n",
    "import os.path\nprint(os.path.join('a', 'b'))\n",
    "from os import *\nprint(1)\n",                   # star import: untracked
])
def test_does_not_flag_used_imports(src):
    assert warnings(src) == [], f"false positive on: {src}"


# ---------------------------------------------- warnings are non-fatal

def test_warning_does_not_block_transpile_or_run(capsys):
    transpile("import os\nprint(1)\n")               # must not raise
    run_source("import os\nprint('ran')\n")
    assert "ran" in capsys.readouterr().out


def test_unused_import_is_a_warning_not_an_error():
    (issue,) = check_source("import os\nprint(1)\n")
    assert issue.severity == "warning"


# --------------------------------------------------------- lint command

def test_vp_files_tolerate_a_utf8_bom(tmp_path, capsys):
    # Windows editors/tools often save UTF-8 with a BOM; run/build/lint must
    # not choke on it (a leading BOM used to break the parser silently).
    f = tmp_path / "bom.vp"
    f.write_bytes(b"\xef\xbb\xbf" + b"import os\nprint(1)\n")
    assert lint_file(str(f)) == 0
    out = capsys.readouterr().out
    assert "warning" in out and "os" in out       # parsed fine; lint still works

    from viper.cli import run_file
    good = tmp_path / "bom_run.vp"
    good.write_bytes(b"\xef\xbb\xbf" + b"print('bom ok')\n")
    assert run_file(str(good)) == 0
    assert "bom ok" in capsys.readouterr().out


def test_lint_command_reports_and_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.vp"
    good.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    assert lint_file(str(good)) == 0
    assert "clean" in capsys.readouterr().out

    warn = tmp_path / "warn.vp"
    warn.write_text("import os\nprint(1)\n", encoding="utf-8")
    assert lint_file(str(warn)) == 0                 # warnings don't fail
    assert "warning" in capsys.readouterr().out

    err = tmp_path / "err.vp"
    err.write_text('let x: int = "no"\n', encoding="utf-8")
    assert lint_file(str(err)) == 1                  # errors do fail
    assert "error" in capsys.readouterr().out
