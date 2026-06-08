"""Viper Language Server — gives editors completion and live error diagnostics.

Requires the optional 'pygls' dependency:  pip install 'viper-lang[lsp]'
Launched via `viper --lsp` (speaks LSP over stdio).
"""
from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from lark.exceptions import UnexpectedInput

from .parser import parser
from .keywords import KEYWORDS, BUILTINS

server = LanguageServer("viper-lsp", "v0.2")


@server.feature(lsp.TEXT_DOCUMENT_COMPLETION)
def completions(params: lsp.CompletionParams) -> lsp.CompletionList:
    items = [
        lsp.CompletionItem(label=kw, kind=lsp.CompletionItemKind.Keyword)
        for kw in KEYWORDS
    ] + [
        lsp.CompletionItem(label=fn, kind=lsp.CompletionItemKind.Function)
        for fn in BUILTINS
    ]
    return lsp.CompletionList(is_incomplete=False, items=items)


def _validate(ls: LanguageServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    diagnostics: list[lsp.Diagnostic] = []
    try:
        parser.parse(doc.source)
    except UnexpectedInput as e:
        last_line = max(len(doc.source.splitlines()) - 1, 0)
        line = min(max((getattr(e, "line", 1) or 1) - 1, 0), last_line)
        col = max((getattr(e, "column", 1) or 1) - 1, 0)
        diagnostics.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=line, character=col),
                    end=lsp.Position(line=line, character=col + 1),
                ),
                message=str(e).splitlines()[0],
                severity=lsp.DiagnosticSeverity.Error,
                source="viper",
            )
        )
    # Always publish: an empty list clears stale errors after a fix.
    ls.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: lsp.DidOpenTextDocumentParams) -> None:
    _validate(ls, params.text_document.uri)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: lsp.DidChangeTextDocumentParams) -> None:
    _validate(ls, params.text_document.uri)


def start() -> None:
    server.start_io()
