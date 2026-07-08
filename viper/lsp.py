"""Viper Language Server — smart completion, hover, signature help, go-to-
definition, document outline, and live error diagnostics for editors.

Requires the optional 'pygls' dependency:  pip install 'viper-lang[lsp]'
Launched via `viper --lsp` (speaks LSP over stdio).

All the intelligence lives in viper/analysis.py (pure logic, no LSP types);
this module only translates between LSP and that engine, so it stays thin
and the smarts stay unit-testable.
"""
import logging
import os
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from . import analysis

server = LanguageServer("viper-lsp", "v1.2")


class _DropCancelNoise(logging.Filter):
    """Clients cancel in-flight completion requests on every keystroke; our
    answers are fast enough that the request usually finished already. pygls
    warns each time — pure noise in the editor's output panel."""
    def filter(self, record: logging.LogRecord) -> bool:
        return "Cancel notification for unknown message id" not in record.getMessage()


logging.getLogger("pygls.protocol.json_rpc").addFilter(_DropCancelNoise())

_KIND = {
    "keyword": lsp.CompletionItemKind.Keyword,
    "function": lsp.CompletionItemKind.Function,
    "method": lsp.CompletionItemKind.Method,
    "class": lsp.CompletionItemKind.Class,
    "variable": lsp.CompletionItemKind.Variable,
    "module": lsp.CompletionItemKind.Module,
    "property": lsp.CompletionItemKind.Property,
    "snippet": lsp.CompletionItemKind.Snippet,
    "text": lsp.CompletionItemKind.Text,
}

_SYMBOL_KIND = {
    "function": lsp.SymbolKind.Function,
    "method": lsp.SymbolKind.Method,
    "class": lsp.SymbolKind.Class,
    "variable": lsp.SymbolKind.Variable,
}


def _uri_to_path(uri: str) -> str:
    path = unquote(urlparse(uri).path)
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]  # /C:/Users/... -> C:/Users/...
    return path


def _path_to_uri(path: str) -> str:
    from pathlib import Path
    return Path(path).as_uri()


def _workspace_dirs(ls: LanguageServer, uri: str) -> list[str]:
    """The document's own directory first, then the workspace root."""
    dirs = []
    doc_dir = os.path.dirname(_uri_to_path(uri))
    if doc_dir and os.path.isdir(doc_dir):
        dirs.append(doc_dir)
    root = getattr(ls.workspace, "root_path", None)
    if root and os.path.isdir(root) and root not in dirs:
        dirs.append(root)
    return dirs


@server.feature(
    lsp.TEXT_DOCUMENT_COMPLETION,
    lsp.CompletionOptions(trigger_characters=[".", " "]),
)
def completions(ls: LanguageServer, params: lsp.CompletionParams) -> lsp.CompletionList:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    results = analysis.complete(
        doc.source,
        params.position.line,
        params.position.character,
        workspace_dirs=_workspace_dirs(ls, uri),
        cache_key=uri,
    )
    items = []
    for c in results:
        extra = None
        if c.extra_edit is not None:
            at = lsp.Position(line=c.extra_edit[0], character=0)
            extra = [lsp.TextEdit(range=lsp.Range(start=at, end=at), new_text=c.extra_edit[1])]
        items.append(lsp.CompletionItem(
            label=c.label,
            kind=_KIND.get(c.kind, lsp.CompletionItemKind.Text),
            detail=c.detail or None,
            documentation=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown, value=c.documentation
            ) if c.documentation else None,
            # editors sort by this: locals first, keywords last (Pylance-style)
            sort_text=f"{c.sort_group}_{c.label.lower()}",
            filter_text=c.label,
            insert_text=c.insert_text,
            insert_text_format=(lsp.InsertTextFormat.Snippet if c.snippet
                                else lsp.InsertTextFormat.PlainText),
            additional_text_edits=extra,
        ))
    return lsp.CompletionList(is_incomplete=False, items=items)


@server.feature(
    lsp.TEXT_DOCUMENT_SIGNATURE_HELP,
    lsp.SignatureHelpOptions(trigger_characters=["(", ","]),
)
def signature_help(ls: LanguageServer, params: lsp.SignatureHelpParams) -> lsp.SignatureHelp | None:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    sig = analysis.signature_help(
        doc.source,
        params.position.line,
        params.position.character,
        workspace_dirs=_workspace_dirs(ls, uri),
        cache_key=uri,
    )
    if sig is None:
        return None
    return lsp.SignatureHelp(
        signatures=[lsp.SignatureInformation(
            label=sig.label,
            documentation=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown, value=sig.documentation
            ) if sig.documentation else None,
            parameters=[lsp.ParameterInformation(label=p) for p in sig.parameters],
            active_parameter=sig.active_parameter,
        )],
        active_signature=0,
        active_parameter=sig.active_parameter,
    )


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    text = analysis.hover(
        doc.source,
        params.position.line,
        params.position.character,
        workspace_dirs=_workspace_dirs(ls, uri),
        cache_key=uri,
    )
    if text is None:
        return None
    return lsp.Hover(contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=text))


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(ls: LanguageServer, params: lsp.DefinitionParams) -> lsp.Location | None:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    found = analysis.definition(
        doc.source,
        params.position.line,
        params.position.character,
        workspace_dirs=_workspace_dirs(ls, uri),
        cache_key=uri,
    )
    if found is None:
        return None
    path, line = found
    target = uri if path is None else _path_to_uri(path)
    pos = lsp.Position(line=line, character=0)
    return lsp.Location(uri=target, range=lsp.Range(start=pos, end=pos))


def _to_lsp_symbol(s: analysis.Symbol) -> lsp.DocumentSymbol:
    rng = lsp.Range(start=lsp.Position(line=s.line, character=0),
                    end=lsp.Position(line=s.end_line + 1, character=0))
    sel = lsp.Range(start=lsp.Position(line=s.line, character=0),
                    end=lsp.Position(line=s.line, character=0))
    return lsp.DocumentSymbol(
        name=s.name,
        kind=_SYMBOL_KIND.get(s.kind, lsp.SymbolKind.Variable),
        range=rng,
        selection_range=sel,
        detail=s.detail or None,
        children=[_to_lsp_symbol(c) for c in s.children],
    )


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: LanguageServer, params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    return [_to_lsp_symbol(s)
            for s in analysis.document_symbols(doc.source, cache_key=params.text_document.uri)]


def _validate(ls: LanguageServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    diagnostics: list[lsp.Diagnostic] = []
    try:
        # one parse validates AND fills the analysis caches, so the completion
        # request that follows the keystroke is a cache hit
        err = analysis.parse_error(doc.source, cache_key=uri)
    except Exception:
        err = None  # never crash the server on an exotic buffer
    if err is not None:
        last_line = max(len(doc.source.splitlines()) - 1, 0)
        line = min(max((getattr(err, "line", 1) or 1) - 1, 0), last_line)
        col = max((getattr(err, "column", 1) or 1) - 1, 0)
        diagnostics.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=line, character=col),
                    end=lsp.Position(line=line, character=col + 1),
                ),
                message=str(err).splitlines()[0],
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
