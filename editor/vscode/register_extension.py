"""Install (copy + register) the Viper extension into VS Code and Cursor.

Modern VS Code and Cursor no longer load extension folders just because they
sit in ~/.vscode/extensions — every extension must also be listed in that
folder's extensions.json registry, and must not be flagged in the .obsolete
file. Copying the folder alone (what older installers did) leaves the editor
silently ignoring it, which kills autocompletion, hover, and diagnostics.

This script does the whole job for each editor it finds:
  1. copies editor/vscode/viper -> <extensions>/viper-lang.viper-lang-<version>
  2. removes any older viper-lang.* folders
  3. rewrites the viper entry in extensions.json
  4. clears viper-lang.* flags from .obsolete

Run it from anywhere (no arguments); install.ps1 and install.sh call it.
Safe to re-run. Restart the editor afterwards (Reload Window is not always
enough after a registry change — fully quit and reopen).
"""
import json
import os
import shutil
import sys
import time

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viper")
EDITOR_DIRS = (".vscode", ".cursor")


def _location_path(path: str) -> str:
    """extensions.json stores URI-style paths: /c:/Users/... on Windows."""
    path = os.path.abspath(path).replace("\\", "/")
    if not path.startswith("/"):  # windows drive path like C:/Users/...
        path = "/" + path[0].lower() + path[1:]
    return path


def _load_manifest():
    with open(os.path.join(SRC, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    ext_id = f"{pkg['publisher']}.{pkg['name']}"
    return ext_id, pkg["version"]


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def register(ext_root: str, ext_id: str, version: str) -> bool:
    """Copy + register into one editor's extensions dir. True on success."""
    folder = f"{ext_id}-{version}"
    dest = os.path.join(ext_root, folder)
    os.makedirs(ext_root, exist_ok=True)

    # 1+2. fresh copy; drop every older viper folder (any naming scheme)
    for d in os.listdir(ext_root):
        if d.lower().startswith("viper-lang.") and os.path.isdir(os.path.join(ext_root, d)):
            shutil.rmtree(os.path.join(ext_root, d), ignore_errors=True)
    shutil.copytree(SRC, dest)

    # 3. registry: replace any previous viper entry with the current one
    reg_file = os.path.join(ext_root, "extensions.json")
    entries = []
    if os.path.isfile(reg_file):
        try:
            with open(reg_file, encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                raise ValueError("extensions.json is not a list")
        except (OSError, ValueError) as e:
            # never guess-rewrite a corrupt registry: that would unregister
            # every OTHER extension too. Leave it for the editor to repair.
            print(f"  warning: could not update {reg_file} ({e}) — "
                  "reinstall any extension from the editor UI to regenerate it, "
                  "then re-run this script")
            return False
    entries = [e for e in entries
               if not (isinstance(e, dict)
                       and str((e.get("identifier") or {}).get("id", ""))
                       .lower().startswith("viper-lang."))]
    entries.append({
        "identifier": {"id": ext_id},
        "version": version,
        "location": {"$mid": 1, "path": _location_path(dest), "scheme": "file"},
        "relativeLocation": folder,
        "metadata": {
            "installedTimestamp": int(time.time() * 1000),
            "pinned": True,          # local install: never auto-update away
            "source": "vsix",
        },
    })
    _write_json(reg_file, entries)

    # 4. unflag it in .obsolete, or the editor deletes/ignores the folder
    obs_file = os.path.join(ext_root, ".obsolete")
    if os.path.isfile(obs_file):
        try:
            with open(obs_file, encoding="utf-8") as f:
                obsolete = json.load(f)
            if isinstance(obsolete, dict):
                cleaned = {k: v for k, v in obsolete.items()
                           if not k.lower().startswith("viper-lang.")}
                if cleaned != obsolete:
                    _write_json(obs_file, cleaned)
        except (OSError, ValueError):
            pass

    print(f"  installed + registered -> {dest}")
    return True


def main() -> int:
    if not os.path.isfile(os.path.join(SRC, "out", "extension.js")):
        print(f"error: extension not found at {SRC} (out/extension.js missing)")
        return 1
    ext_id, version = _load_manifest()
    home = os.path.expanduser("~")
    installed_any = False
    ok = True
    for editor in EDITOR_DIRS:
        if not os.path.isdir(os.path.join(home, editor)):
            continue  # editor not installed — skip silently
        print(f"{editor[1:]}:")
        if register(os.path.join(home, editor, "extensions"), ext_id, version):
            installed_any = True
        else:
            ok = False
    if installed_any:
        print("restart the editor to load the extension "
              "(fully quit and reopen — a plain Reload Window can miss registry changes).")
    elif ok:
        print("no VS Code or Cursor installation found — nothing to do.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
