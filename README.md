i build a programming language that is connected to python modules
**(ALPHA-0.0.1)**

it transpiles .vp -> Python, runs files and a REPL, has clear errors, pipes, match, lamdas, and  a mutable-default guard (all verified). The gap is that it doesn't yet
**FEEL** like a real, installable language:
- it only runs via .venv/bin/viper there's no install flow that puts **viper** on your PATH
- Editing .vp in Vim gives no help no syntax highlighting, no autocomplete, no live error checking
 
**(ALPHA-0.0.2)**
For the Goal (ALPHA-0.0.2): an install.sh that makes viper global, a real LSP Server (viper --lsp) so vim/Neovim get autocomplete + diagnostics, and a viper help that runs
an interactive tutorial plus **Decisions made with you:** install = script that tries pipx, falls back to venv+symlink; autocomplete = full LSP server; help = both interactive
tutorial AND topic reference.
**Approach**
viper/keywords.py (new) — shared vocabulary

     - KEYWORDS = the 23 grammar keywords (let fn if elif else while for in match case return break continue pass import from spawn and or not is True False None).
     - BUILTINS = curated runnable subset (print len range int float str bool list dict set tuple sum min max abs sorted enumerate zip map filter input round type repr).
     - Used by both lsp.py and the Vim syntax file (keep them in sync).

viper/lsp.py (new) — pygls v2 server (imported only on --lsp)

     - from lsprotocol import types as lsp; from pygls.lsp.server import LanguageServer; from lark.exceptions import UnexpectedInput; from .parser import parser; from .keywords import
     KEYWORDS, BUILTINS.
     - server = LanguageServer("viper-lsp", "v0.2").
     - @server.feature(lsp.TEXT_DOCUMENT_COMPLETION) → CompletionList(is_incomplete=False, items=...): keywords (CompletionItemKind.Keyword) + builtins (CompletionItemKind.Function).
     - _validate(ls, uri): doc = ls.workspace.get_text_document(uri); parser.parse(doc.source); on UnexpectedInput: line=max((e.line or 1)-1,0), col=max((e.column or 1)-1,0), clamp line to
     last source line; build Diagnostic(range=Range(Position(line,col),Position(line,col+1)), message=str(e).splitlines()[0], severity=DiagnosticSeverity.Error, source="viper"). Always publish
      (empty list clears stale errors) via ls.text_document_publish_diagnostics(PublishDiagnosticsParams(uri=uri, diagnostics=...)).
     - @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN) and TEXT_DOCUMENT_DID_CHANGE → call _validate.
     - start() → server.start_io().

viper/tutorial.py (new) — interactive ~5-min tour

     - LESSONS: ~8 entries {title, explain, code} covering: print, let+types, fn+return, if/elif/else, for+lists, while, match/case, then pipe |> + lambdas + dicts + import math, plus a
     mutable-default footgun demo showing the friendly error.
     - _run_example(code): print the source (dimmed), run it live via runtime.run_source(code, "<tutorial>") in a fresh namespace, show output; catch ViperError and print its formatted message
      (so the footgun lesson renders nicely).
     - run_tutorial() -> int: banner → per-lesson title/explain/example/live-output → input("Press Enter to continue / q to quit: "); q quits; wrap in try/except (EOFError, KeyboardInterrupt)
     for clean exit. Ends with "try viper repl".

viper/help.py (new) — topic reference

     - TOPICS: dict[str,str] (concise paragraph + tiny non-executed example) for let fn if for while match pipe lambda dict list import spawn types.
     - ALIASES ("|>"→"pipe", "def"→"fn").
     - show_topic(name) -> int (unknown → message + list_topics(), return 1) and list_topics() -> int.

viper/_ansi.py (new, tiny)

     - supports_ansi() (sys.stdout.isatty()), header(), dim(), bold() — ANSI when supported, plain otherwise. Used by tutorial + help.

viper/cli.py (modify) — dispatch + REPL tab-complete

     - Add top-level --lsp flag (works with no subcommand).
     - Add subparsers: help (optional topic arg) and topics.
     - Dispatch: --lsp → _start_lsp(); run → existing; help no-arg → run_tutorial(); help <topic> → show_topic(); topics / help topics → list_topics(); default → repl().
     - _start_lsp(): try: from . import lsp except ImportError: print install with: pip install 'viper-lang[lsp]' (stderr, return 1); else lsp.start().
     - REPL win (guarded): try: import readline + completer over KEYWORDS + BUILTINS + list(ns), parse_and_bind("tab: complete"), wrapped in try/except ImportError: pass.

     Editor files (new, under editor/)

     - editor/ftdetect/viper.vim: au BufRead,BufNewFile *.vp set filetype=viper.
     - editor/syntax/viper.vim: syn keyword for keywords + builtins (mirror keywords.py), string region, number match, syn match for |>; no comment rule (grammar has none); hi def link to
     standard groups. Guard with b:current_syntax.
     - editor/ftplugin/viper.lua (Neovim): vim.filetype.add({extension={vp="viper"}}) then, guarded by vim.fn.executable("viper")==1, vim.lsp.start({name="viper-lsp", cmd={"viper","--lsp"},
     root_dir=...vim.fs.find{"pyproject.toml",".git"}...}).
     - editor/README.md: classic Vim 8 fallback snippet using prabirshrestha/vim-lsp.

install.sh (new, project root, POSIX sh, set -e, idempotent)

     1. Resolve SCRIPT_DIR; helper have() { command -v "$1" >/dev/null 2>&1; }.
     2. Pick best install: if have pipx → pipx install --force "$SCRIPT_DIR" then pipx inject viper-lang "pygls>=2.1,<3" (so --lsp works). Else → create/reuse .venv, pip install -e
     "$SCRIPT_DIR[lsp]", ln -sf .venv/bin/viper ~/.local/bin/viper, print PATH note.
     3. Install editor files (both branches): mkdir -p + cp ftdetect/syntax into ~/.vim/ and ~/.config/nvim/, and the lua ftplugin into ~/.config/nvim/ftplugin/.
     4. Print next-steps (viper help, viper repl, viper run examples/hello.vp, PATH + nvim notes).
     - POSIX-only (no [[ ]], no arrays); all steps re-runnable.


