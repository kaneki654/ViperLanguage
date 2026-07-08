"""Unit tests for the batteries-included stdlib prelude (viper/std.py)."""
import hashlib
import hmac
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from viper import std


# ------------------------------------------------------------------ hashing

def test_hashes_match_hashlib_for_str_and_bytes():
    assert std.sha256("abc") == hashlib.sha256(b"abc").hexdigest()
    assert std.sha256(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert std.sha1("abc") == hashlib.sha1(b"abc").hexdigest()
    assert std.sha512("abc") == hashlib.sha512(b"abc").hexdigest()
    assert std.md5("abc") == hashlib.md5(b"abc").hexdigest()


def test_hmac256_matches_and_detects_tamper():
    got = std.hmac256("key", "message")
    assert got == hmac.new(b"key", b"message", hashlib.sha256).hexdigest()
    assert std.hmac256("key", "message") != std.hmac256("key", "message!")


def test_file_sha256_streams_correctly(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"viper" * 100000)
    assert std.file_sha256(str(p)) == hashlib.sha256(b"viper" * 100000).hexdigest()


# ----------------------------------------------------------------- encoding

def test_base64_roundtrip_and_padding():
    assert std.b64("flag{ok}") == "ZmxhZ3tva30="
    assert std.unb64("ZmxhZ3tva30=").decode() == "flag{ok}"
    # missing padding is tolerated
    assert std.unb64("ZmxhZ3tva30").decode() == "flag{ok}"


def test_hex_roundtrip():
    assert std.to_hex("hi") == "6869"
    assert std.from_hex("68 69") == b"hi"
    assert std.from_hex(std.to_hex(b"\x00\xff")) == b"\x00\xff"


def test_url_quote_roundtrip():
    assert std.url_quote("a b/c?") == "a%20b%2Fc%3F"
    assert std.url_unquote("a%20b%2Fc%3F") == "a b/c?"


# ------------------------------------------------------------------- random

def test_rand_token_length_and_hex():
    tok = std.rand_token(8)
    assert len(tok) == 16 and int(tok, 16) >= 0     # 8 bytes -> 16 hex chars


def test_rand_int_in_range_inclusive():
    for _ in range(200):
        assert 5 <= std.rand_int(5, 7) <= 7
    assert std.rand_int(3, 3) == 3


def test_uuid4_shape():
    import uuid
    assert uuid.UUID(std.uuid4()).version == 4


# --------------------------------------------------------------- json/files

def test_json_roundtrip(tmp_path):
    obj = {"a": 1, "b": [1, 2, 3], "c": "x"}
    assert std.json_parse(std.json_str(obj)) == obj
    p = tmp_path / "d.json"
    std.write_json(str(p), obj)
    assert std.read_json(str(p)) == obj
    assert json.loads(p.read_text(encoding="utf-8")) == obj


def test_read_lines_and_ls_and_exists(tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    assert std.read_lines(str(tmp_path / "a.txt")) == ["one", "two", "three"]
    assert std.ls(str(tmp_path)) == ["a.txt", "b.txt"]
    assert std.exists(str(tmp_path / "a.txt"))
    assert not std.exists(str(tmp_path / "nope.txt"))


def test_env(monkeypatch):
    monkeypatch.setenv("VIPER_TEST_VAR", "42")
    assert std.env("VIPER_TEST_VAR") == "42"
    assert std.env("VIPER_MISSING_VAR", "default") == "default"


# ---------------------------------------------------------------- data/misc

def test_hexdump_format():
    dump = std.hexdump(b"ABC\x00\xff")
    assert dump.startswith("00000000  ")
    assert "41 42 43 00 ff" in dump
    assert "|ABC..|" in dump


def test_now_is_isoish():
    n = std.now()
    assert "T" in n and len(n) >= 19


# ------------------------------------------------------------- shell / procs

def test_which_and_sh_out_find_python():
    py = std.which("python") or std.which("python3")
    assert py is not None
    out = std.sh_out(f'"{py}" -c "print(123)"')
    assert "123" in out


def test_sh_returns_exit_code():
    assert std.sh(f'"{sys.executable}" -c "import sys; sys.exit(0)"') == 0
    assert std.sh(f'"{sys.executable}" -c "import sys; sys.exit(3)"') == 3


# -------------------------------------------------------------- http + port
# A throwaway localhost server so the network helpers are tested without
# ever touching the real internet.

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # silence
        pass

    def do_GET(self):
        body = b"hello-get"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"echo:" + data)


@pytest.fixture()
def http_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, port = srv.server_address
    yield f"http://127.0.0.1:{port}", host, port
    srv.shutdown()


def test_http_get_post_status(http_server):
    base, _, _ = http_server
    assert std.http_get(base + "/") == "hello-get"
    assert std.http_post(base + "/", "abc") == "echo:abc"
    assert std.http_post(base + "/", {"k": "v"}) == "echo:k=v"
    assert std.http_status(base + "/") == 200


def test_download(http_server, tmp_path):
    base, _, _ = http_server
    dest = tmp_path / "out.txt"
    n = std.download(base + "/", str(dest))
    assert dest.read_bytes() == b"hello-get" and n == len(b"hello-get")


def test_port_open_true_and_false(http_server):
    _, host, port = http_server
    assert std.port_open(host, port) is True
    # a port nothing is listening on
    assert std.port_open(host, 1, timeout=0.3) is False


# --------------------------------------------------------------- meta/wiring

def test_docs_cover_every_prelude_name():
    assert set(std.STD_DOCS) == set(std.STD_NAMES)
    for name, (sig, doc) in std.STD_DOCS.items():
        assert sig.startswith(name + "(")
        assert doc and not doc.startswith(" ")
