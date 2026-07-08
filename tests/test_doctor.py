import json
import os
import subprocess
import sys


def test_doctor_runs_and_reports():
    r = subprocess.run([sys.executable, "-m", "viper.cli", "doctor"],
                       capture_output=True, text=True)
    assert "viper doctor" in r.stdout
    assert "Python" in r.stdout and "lark" in r.stdout and "pygls" in r.stdout
    assert r.returncode in (0, 1)   # 1 is fine on machines missing PATH/extension


def _doctor_with_home(home):
    env = os.environ.copy()
    env["HOME"] = str(home)          # POSIX
    env["USERPROFILE"] = str(home)   # Windows
    return subprocess.run([sys.executable, "-m", "viper.cli", "doctor"],
                          capture_output=True, text=True, env=env)


def _fake_extension(tmp_path, registered):
    """A home dir whose Cursor has the extension folder; maybe registered."""
    home = tmp_path / "home"
    folder = "viper-lang.viper-lang-9.9.9"
    ext = home / ".cursor" / "extensions" / folder
    (ext / "out").mkdir(parents=True)
    (ext / "package.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
    (ext / "out" / "extension.js").write_text("", encoding="utf-8")
    entries = [{"identifier": {"id": "viper-lang.viper-lang"}, "version": "9.9.9",
                "relativeLocation": folder}] if registered else []
    (home / ".cursor" / "extensions" / "extensions.json").write_text(
        json.dumps(entries), encoding="utf-8")
    return home


def test_doctor_flags_unregistered_extension(tmp_path):
    # folder present but missing from extensions.json — the editor silently
    # ignores it (no completions); doctor must catch that, not report OK
    r = _doctor_with_home(_fake_extension(tmp_path, registered=False))
    assert "[FAIL] cursor extension registered" in r.stdout
    assert r.returncode == 1


def test_doctor_accepts_registered_extension(tmp_path):
    r = _doctor_with_home(_fake_extension(tmp_path, registered=True))
    assert "[OK  ] cursor extension registered" in r.stdout


def test_doctor_in_help():
    r = subprocess.run([sys.executable, "-m", "viper.cli", "--help"],
                       capture_output=True, text=True)
    assert "doctor" in r.stdout
