"""Viper's batteries-included standard prelude.

This is Viper's reason to exist for scripting, automation, and security work:
the tasks that need five imports and a dozen lines of ceremony in Python are
one plain call here, and every one is available with no import at all.

    let digest = sha256("hello")
    let body   = http_get("https://example.com")
    let flag   = unb64("ZmxhZ3toaX0=") |> bytes.decode(_)

Everything is backed by the Python standard library (hashlib, hmac, base64,
secrets, urllib, subprocess, json, socket, ...) — no third-party dependencies,
works everywhere CPython does. Heavy imports live *inside* each function so
importing this module stays cheap (the editor's analysis loads it) and so
`viper build` can inline each helper's source into a self-contained .py.

Security helpers here (hashing, HMAC, encoding, hexdump, checksums, a single
TCP reachability check) are the ordinary plumbing of CTF challenges, authorized
testing, and defensive tooling — the same primitives Python itself ships.

Names are grouped only for reading; at runtime they are all flat, top-level,
and freely shadowable (Viper does not guard them the way it guards builtins).
"""
import inspect


# ------------------------------------------------------------ shared support
# Inlined ahead of the public helpers by `viper build`; keep dependency-free.

def _as_bytes(data) -> bytes:
    """Coerce str (utf-8) or bytes-like into bytes."""
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


# ------------------------------------------------------------------ hashing

def sha256(data) -> str:
    """SHA-256 hex digest of a str or bytes."""
    import hashlib
    return hashlib.sha256(_as_bytes(data)).hexdigest()


def sha1(data) -> str:
    """SHA-1 hex digest of a str or bytes."""
    import hashlib
    return hashlib.sha1(_as_bytes(data)).hexdigest()


def sha512(data) -> str:
    """SHA-512 hex digest of a str or bytes."""
    import hashlib
    return hashlib.sha512(_as_bytes(data)).hexdigest()


def md5(data) -> str:
    """MD5 hex digest of a str or bytes (legacy checksums / CTF only)."""
    import hashlib
    return hashlib.md5(_as_bytes(data)).hexdigest()


def hmac256(key, data) -> str:
    """HMAC-SHA256 hex digest — verify or sign a message with a shared key."""
    import hashlib
    import hmac as _hmac
    return _hmac.new(_as_bytes(key), _as_bytes(data), hashlib.sha256).hexdigest()


def file_sha256(path) -> str:
    """SHA-256 hex digest of a file, streamed (safe for large files)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------- encoding

def b64(data) -> str:
    """Base64-encode a str or bytes, returning ASCII text."""
    import base64
    return base64.b64encode(_as_bytes(data)).decode("ascii")


def unb64(text) -> bytes:
    """Decode Base64 text into bytes (padding fixed up automatically)."""
    import base64
    s = text if isinstance(text, str) else bytes(text).decode("ascii")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def to_hex(data) -> str:
    """Hex-encode a str or bytes (e.g. 'hi' -> '6869')."""
    return _as_bytes(data).hex()


def from_hex(text) -> bytes:
    """Decode a hex string into bytes (whitespace ignored)."""
    return bytes.fromhex("".join(str(text).split()))


def url_quote(text) -> str:
    """Percent-encode a string for safe use in a URL."""
    import urllib.parse
    return urllib.parse.quote(str(text), safe="")


def url_unquote(text) -> str:
    """Decode a percent-encoded URL string."""
    import urllib.parse
    return urllib.parse.unquote(str(text))


# ------------------------------------------------------- randomness / tokens

def rand_token(nbytes: int = 16) -> str:
    """Cryptographically strong random hex token (for keys, nonces, IDs)."""
    import secrets
    return secrets.token_hex(nbytes)


def rand_int(lo: int, hi: int) -> int:
    """Uniform random integer in [lo, hi], from a secure source."""
    import secrets
    if hi < lo:
        lo, hi = hi, lo
    return lo + secrets.randbelow(hi - lo + 1)


def uuid4() -> str:
    """A random UUID version 4, as a string."""
    import uuid
    return str(uuid.uuid4())


# --------------------------------------------------------------------- http

def http_get(url, headers=None) -> str:
    """HTTP GET a URL and return the response body as text."""
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "viper/std"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")


def http_post(url, data=None, headers=None) -> str:
    """HTTP POST to a URL. data may be a dict (form-encoded), str, or bytes."""
    import urllib.parse
    import urllib.request
    if isinstance(data, dict):
        payload = urllib.parse.urlencode(data).encode("utf-8")
    elif isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = data
    req = urllib.request.Request(url, data=payload,
                                 headers=headers or {"User-Agent": "viper/std"},
                                 method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")


def http_status(url) -> int:
    """Return the HTTP status code for a URL (e.g. 200, 404)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "viper/std"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def download(url, path) -> int:
    """Download a URL to a file; return the number of bytes written."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "viper/std"})
    with urllib.request.urlopen(req) as resp, open(path, "wb") as out:
        data = resp.read()
        out.write(data)
        return len(data)


# ------------------------------------------------------------ shell / procs

def sh(cmd) -> int:
    """Run a shell command, streaming its output; return the exit code."""
    import subprocess
    return subprocess.run(cmd, shell=True).returncode


def sh_out(cmd) -> str:
    """Run a shell command and return its captured stdout as text."""
    import subprocess
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def which(name) -> str | None:
    """Full path of an executable on PATH, or None if not found."""
    import shutil
    return shutil.which(name)


# ------------------------------------------------------------- json / files

def json_parse(text):
    """Parse a JSON string into Viper values."""
    import json
    return json.loads(text)


def json_str(obj, indent: int = 2) -> str:
    """Serialize a value to a JSON string (pretty-printed by default)."""
    import json
    return json.dumps(obj, indent=indent, ensure_ascii=False)


def read_json(path):
    """Read and parse a JSON file."""
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj) -> int:
    """Write a value to a file as pretty JSON; return bytes written."""
    import json
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        return f.write(text)


def read_lines(path, encoding: str = "utf-8") -> list:
    """Read a text file into a list of lines, newlines stripped."""
    from pathlib import Path
    return Path(path).read_text(encoding=encoding).splitlines()


def ls(path: str = ".") -> list:
    """List the entries of a directory (names only), sorted."""
    import os
    return sorted(os.listdir(path))


def exists(path) -> bool:
    """True if a file or directory exists at path."""
    import os
    return os.path.exists(path)


def env(name, default=None):
    """Value of an environment variable, or default if unset."""
    import os
    return os.environ.get(name, default)


# ------------------------------------------------------------- data / misc

def hexdump(data, width: int = 16) -> str:
    """Classic offset / hex / ASCII dump of bytes or text (great for CTF)."""
    raw = _as_bytes(data)
    out = []
    for off in range(0, len(raw), width):
        chunk = raw[off:off + width]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{off:08x}  {hexs:<{width * 3}}  |{text}|")
    return "\n".join(out)


def sleep(seconds) -> None:
    """Pause execution for a number of seconds (float allowed)."""
    import time
    time.sleep(seconds)


def now() -> str:
    """Current local time as an ISO-8601 string (second precision)."""
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def port_open(host, port, timeout: float = 1.0) -> bool:
    """True if a TCP connection to host:port succeeds (single reachability
    check — for confirming your own service is up, or a CTF target)."""
    import socket
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


# ------------------------------------------------------ crypto / web helpers

def xor(data, key) -> bytes:
    """Repeating-key XOR of data with key (str or bytes) — classic CTF crypto."""
    d = _as_bytes(data)
    k = _as_bytes(key)
    if not k:
        return d
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(d))


def url_parse(url) -> dict:
    """Split a URL into scheme, host, port, path, query (dict), and fragment."""
    import urllib.parse
    p = urllib.parse.urlsplit(url)
    return {"scheme": p.scheme, "host": p.hostname, "port": p.port,
            "path": p.path, "query": dict(urllib.parse.parse_qsl(p.query)),
            "fragment": p.fragment}


def qs_parse(query) -> dict:
    """Parse a query string ('a=1&b=2') into a dict."""
    import urllib.parse
    return dict(urllib.parse.parse_qsl(str(query)))


def qs_build(params) -> str:
    """Build a query string from a dict ({'a': 1} -> 'a=1')."""
    import urllib.parse
    return urllib.parse.urlencode(params)


def json_get(obj, path, default=None):
    """Safely read a nested value by dotted path ('a.b.0'); default if missing."""
    cur = obj
    for part in str(path).split("."):
        try:
            cur = cur[int(part)] if isinstance(cur, (list, tuple)) else cur[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    return cur


# ---------------------------------------------------- classic prelude (kept)

def pp(*objs) -> None:
    """Pretty-print one or more objects."""
    import pprint
    for obj in objs:
        pprint.pprint(obj)


def read_file(path, encoding: str = "utf-8") -> str:
    """Read a whole file as text."""
    from pathlib import Path
    return Path(path).read_text(encoding=encoding)


def write_file(path, text, encoding: str = "utf-8") -> int:
    """Write text to a file, replacing it; return bytes written."""
    from pathlib import Path
    return Path(path).write_text(text, encoding=encoding)


def clamp(x, lo, hi):
    """Clamp x into the range [lo, hi]."""
    return lo if x < lo else hi if x > hi else x


# ------------------------------------------------------------------ registry

# Support helpers inlined (in order) ahead of the public ones by `viper build`.
PRELUDE_SUPPORT = [_as_bytes]

# Everything a Viper program gets for free, name -> callable.
PRELUDE = {
    fn.__name__: fn
    for fn in (
        # hashing
        sha256, sha1, sha512, md5, hmac256, file_sha256,
        # encoding
        b64, unb64, to_hex, from_hex, url_quote, url_unquote,
        # randomness
        rand_token, rand_int, uuid4,
        # http
        http_get, http_post, http_status, download,
        # shell
        sh, sh_out, which,
        # json / files
        json_parse, json_str, read_json, write_json, read_lines, ls, exists, env,
        # data / misc
        hexdump, sleep, now, port_open,
        # crypto / web
        xor, url_parse, qs_parse, qs_build, json_get,
        # classic prelude
        pp, read_file, write_file, clamp,
    )
}

STD_NAMES = list(PRELUDE)

# name -> (signature, one-line doc); single source of truth for editor
# completion, hover, and signature help. Derived from the functions above.
STD_DOCS = {
    name: (f"{name}{inspect.signature(fn)}",
           (inspect.getdoc(fn) or "").split("\n")[0])
    for name, fn in PRELUDE.items()
}

__all__ = STD_NAMES
