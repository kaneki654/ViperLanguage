"""The `viper` command-line interface."""
import argparse
import sys

from . import __version__
from .errors import ViperError
from .runtime import run_source, run_repl_line, _fresh_namespace


def run_file(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        print(f"error: cannot read {path!r}: {e}", file=sys.stderr)
        return 1

    try:
        run_source(source, filename=path)
    except ViperError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _needs_continuation(buffer: str) -> bool:
    """True while a block is open (unbalanced brackets or last non-blank line ends in ':').

    This is much more reliable than the old heuristic that only checked for ':'.
    We also track open brackets so multi-line expressions work correctly.
    """
    # Count unbalanced brackets — open means we're in the middle of an expression
    opens = {"(": ")", "[": "]", "{": "}"}
    closes = set(opens.values())
    stack = []
    in_string = None
    escape = False

    for ch in buffer:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ('"', "'"):
            in_string = ch
            continue
        if ch in opens:
            stack.append(opens[ch])
        elif ch in closes:
            if stack and stack[-1] == ch:
                stack.pop()

    if stack:  # Unbalanced brackets
        return True

    # Check if last non-empty line ends with a block-opening colon
    lines = [ln for ln in buffer.splitlines() if ln.strip()]
    if not lines:
        return False
    last = lines[-1].rstrip()
    # Strip inline comments before checking
    if "#" in last:
        last = last[:last.index("#")].rstrip()
    return last.endswith(":")


def _install_repl_completion(ns: dict) -> None:
    """Tab-completion over keywords, builtins, and live names. Best-effort."""
    try:
        import readline
    except ImportError:
        return
    from .keywords import KEYWORDS, BUILTINS

    def completer(text, state):
        options = [w for w in KEYWORDS + BUILTINS + list(ns)
                   if w.startswith(text)]
        return options[state] if state < len(options) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def repl() -> int:
    print(f"Viper {__version__} — type Ctrl-D to exit.")
    ns = _fresh_namespace()
    _install_repl_completion(ns)
    buffer = ""
    while True:
        prompt = "... " if buffer else ">>> "
        try:
            line = input(prompt)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\n(interrupted)")
            buffer = ""
            continue

        # An empty line after a block flushes the buffer
        if not line.strip() and buffer:
            try:
                run_repl_line(buffer, ns)
            except ViperError as e:
                print(str(e), file=sys.stderr)
            buffer = ""
            continue

        buffer = buffer + line + "\n" if buffer else line + "\n"

        if _needs_continuation(buffer):
            continue

        # Only flush if the block is closed (blank line or no open colon)
        if buffer.rstrip().endswith(":"):
            # Still opening a block — keep reading
            continue

        try:
            run_repl_line(buffer, ns)
        except ViperError as e:
            print(str(e), file=sys.stderr)
        buffer = ""


def _start_lsp() -> int:
    try:
        from . import lsp
    except ImportError:
        print("the Viper language server needs the optional 'pygls' dependency.",
              file=sys.stderr)
        print("install it with:  pip install 'viper-lang[lsp]'", file=sys.stderr)
        return 1
    lsp.start()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="viper", description="The Viper language.")
    ap.add_argument("--version", action="version",
                    version=f"viper {__version__}")
    ap.add_argument("--lsp", action="store_true",
                    help="run the Viper language server (for editors)")
    sub = ap.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="run a .vp file")
    run_p.add_argument("file")

    sub.add_parser("repl", help="start the interactive REPL")

    help_p = sub.add_parser("help", help="interactive tutorial, or reference for a topic")
    help_p.add_argument("topic", nargs="?", help="a topic, e.g. match, pipe, fn")

    sub.add_parser("topics", help="list the available help topics")

    args = ap.parse_args(argv)

    if args.lsp:
        return _start_lsp()
    if args.command == "run":
        return run_file(args.file)
    if args.command == "help":
        if args.topic in (None, "topics"):
            if args.topic == "topics":
                from .help import list_topics
                return list_topics()
            from .tutorial import run_tutorial
            return run_tutorial()
        from .help import show_topic
        return show_topic(args.topic)
    if args.command == "topics":
        from .help import list_topics
        return list_topics()
    return repl()


if __name__ == "__main__":
    sys.exit(main())
