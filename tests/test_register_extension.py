"""The editor extension must be copied AND registered in extensions.json —
modern VS Code/Cursor silently ignore unregistered extension folders, which
shows up to users as "autocompletion stopped working"."""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "editor" / "vscode" / "register_extension.py"
EXT_VERSION = json.loads(
    (REPO / "editor" / "vscode" / "viper" / "package.json").read_text(encoding="utf-8")
)["version"]
EXT_FOLDER = f"viper-lang.viper-lang-{EXT_VERSION}"


def make_home(tmp_path, extensions_json=None, obsolete=None, editor=".cursor"):
    home = tmp_path / "home"
    ext_root = home / editor / "extensions"
    ext_root.mkdir(parents=True)
    if extensions_json is not None:
        (ext_root / "extensions.json").write_text(extensions_json, encoding="utf-8")
    if obsolete is not None:
        (ext_root / ".obsolete").write_text(obsolete, encoding="utf-8")
    return home, ext_root


def run_script(home):
    env = os.environ.copy()
    env["HOME"] = str(home)          # POSIX
    env["USERPROFILE"] = str(home)   # Windows
    return subprocess.run([sys.executable, str(SCRIPT)],
                          capture_output=True, text=True, env=env)


def viper_entries(ext_root):
    entries = json.loads((ext_root / "extensions.json").read_text(encoding="utf-8"))
    return [e for e in entries
            if e["identifier"]["id"].lower().startswith("viper-lang.")]


def test_fresh_install_copies_and_registers(tmp_path):
    home, ext_root = make_home(tmp_path)
    r = run_script(home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (ext_root / EXT_FOLDER / "out" / "extension.js").is_file()
    (entry,) = viper_entries(ext_root)
    assert entry["identifier"]["id"] == "viper-lang.viper-lang"
    assert entry["version"] == EXT_VERSION
    assert entry["relativeLocation"] == EXT_FOLDER
    assert entry["location"]["path"].endswith("/" + EXT_FOLDER)


def test_installs_into_antigravity(tmp_path):
    # Antigravity (like Windsurf/VSCodium) is a VS Code fork with the same
    # <home>/<dir>/extensions layout — the installer must cover it too.
    home, ext_root = make_home(tmp_path, editor=".antigravity-ide")
    r = run_script(home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (ext_root / EXT_FOLDER / "out" / "extension.js").is_file()
    (entry,) = viper_entries(ext_root)
    assert entry["version"] == EXT_VERSION


def test_replaces_stale_entry_and_cleans_obsolete(tmp_path):
    stale = [
        {"identifier": {"id": "ms-python.python"}, "version": "1.0.0",
         "location": {"$mid": 1, "path": "/x/ms-python.python-1.0.0", "scheme": "file"},
         "relativeLocation": "ms-python.python-1.0.0"},
        # the bug this repo shipped: registry points at a folder that was deleted
        {"identifier": {"id": "viper-lang.viper-lang"}, "version": "1.0.0",
         "location": {"$mid": 1, "path": "/x/viper-lang.viper-1.0.0", "scheme": "file"},
         "relativeLocation": "viper-lang.viper-1.0.0"},
    ]
    home, ext_root = make_home(
        tmp_path,
        extensions_json=json.dumps(stale),
        obsolete=json.dumps({EXT_FOLDER: True, "other.ext-1.0.0": True}),
    )
    # an old unversioned, unregistered copy must be swept away too
    (ext_root / "viper-lang.viper").mkdir()

    r = run_script(home)
    assert r.returncode == 0, r.stdout + r.stderr

    (entry,) = viper_entries(ext_root)  # exactly one viper entry survives
    assert entry["relativeLocation"] == EXT_FOLDER
    all_ids = [e["identifier"]["id"]
               for e in json.loads((ext_root / "extensions.json").read_text(encoding="utf-8"))]
    assert "ms-python.python" in all_ids  # other extensions untouched
    assert not (ext_root / "viper-lang.viper").exists()
    obsolete = json.loads((ext_root / ".obsolete").read_text(encoding="utf-8"))
    assert EXT_FOLDER not in obsolete       # or the editor deletes our folder
    assert obsolete.get("other.ext-1.0.0")  # other flags untouched


def test_corrupt_registry_is_left_alone(tmp_path):
    home, ext_root = make_home(tmp_path, extensions_json="{not json")
    r = run_script(home)
    assert r.returncode == 1
    # never guess-rewrite: clobbering it would unregister every other extension
    assert (ext_root / "extensions.json").read_text(encoding="utf-8") == "{not json"
