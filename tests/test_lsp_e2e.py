"""End-to-end test: spawn the real server, speak LSP over stdio."""
import json
import subprocess
import sys

import pytest

pytest.importorskip("pygls")


def _frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def _read_message(stdout) -> dict:
    headers = {}
    while True:
        line = stdout.readline().decode()
        if line in ("\r\n", "\n", ""):
            break
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    length = int(headers["content-length"])
    return json.loads(stdout.read(length))


def _read_response(stdout, want_id):
    for _ in range(50):                    # skip notifications (diagnostics, logs)
        msg = _read_message(stdout)
        if msg.get("id") == want_id:
            return msg
    raise AssertionError("no response with id %r" % want_id)


def test_lsp_end_to_end(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "-m", "viper.cli", "--lsp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        uri = (tmp_path / "t.vp").as_uri()
        src = "import math\n\nfn add(a, b):\n    return a + b\n\nmath.\n"

        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"processId": None, "rootUri": None,
                                            "capabilities": {}}}))
        proc.stdin.flush()
        init = _read_response(proc.stdout, 1)
        caps = init["result"]["capabilities"]
        assert "." in caps["completionProvider"]["triggerCharacters"]
        assert "signatureHelpProvider" in caps and "hoverProvider" in caps
        assert "definitionProvider" in caps and "documentSymbolProvider" in caps

        proc.stdin.write(_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
        proc.stdin.write(_frame({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                                 "params": {"textDocument": {
                                     "uri": uri, "languageId": "viper",
                                     "version": 1, "text": src}}}))
        proc.stdin.flush()

        # completion after "math."
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 2,
                                 "method": "textDocument/completion",
                                 "params": {"textDocument": {"uri": uri},
                                            "position": {"line": 5, "character": 6}}}))
        proc.stdin.flush()
        resp = _read_response(proc.stdout, 2)
        items = resp["result"]["items"]
        labels = {i["label"] for i in items}
        assert "sqrt" in labels
        assert all("sortText" in i for i in items)   # ranked results

        # hover over fn add
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 3,
                                 "method": "textDocument/hover",
                                 "params": {"textDocument": {"uri": uri},
                                            "position": {"line": 2, "character": 4}}}))
        proc.stdin.flush()
        resp = _read_response(proc.stdout, 3)
        assert "fn add(" in resp["result"]["contents"]["value"]

        # go to definition of add() from its call site
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 4,
                                 "method": "textDocument/definition",
                                 "params": {"textDocument": {"uri": uri},
                                            "position": {"line": 2, "character": 4}}}))
        proc.stdin.flush()
        resp = _read_response(proc.stdout, 4)
        assert resp["result"]["range"]["start"]["line"] == 2

        # document outline
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 5,
                                 "method": "textDocument/documentSymbol",
                                 "params": {"textDocument": {"uri": uri}}}))
        proc.stdin.flush()
        resp = _read_response(proc.stdout, 5)
        assert any(s["name"] == "add" for s in resp["result"])

        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 9, "method": "shutdown", "params": None}))
        proc.stdin.write(_frame({"jsonrpc": "2.0", "method": "exit", "params": None}))
        proc.stdin.flush()
    finally:
        proc.kill()
