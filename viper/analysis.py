"""Editor intelligence for Viper — pure logic, no LSP types.

Everything the language server needs to answer completion / hover /
signature-help / definition / outline requests lives here in plain data
structures, so it can be unit-tested without pygls and reused by other tools.

Design notes (what makes this feel fast and smart):
- One parse per buffer state: analysis results are memoized per document, so
  the didChange validation and any number of completion/hover requests on the
  same text share a single parse.
- Never goes dark: when the buffer doesn't parse (mid-keystroke, or a file
  using unsupported syntax), a line-scanner still extracts fn/class/let/import
  symbols, merged with the last successful full analysis.
- Ranked results: completions carry a sort_group so the editor shows your own
  variables and functions before builtins, and keywords last (the same
  prioritization Pylance uses for Python).
- Type inference: `let s = "hi"` makes `s.` complete str methods; classes
  infer through constructor calls and annotated params; `self.` knows the
  enclosing class's methods and attributes.
- Auto-import completions: top-level symbols of workspace .vp modules are
  offered even before you import them, with the `from x import y` line
  inserted automatically.

Note on imports: dot-completion for Python modules imports them (normal
Python import semantics — module top-level code runs, exactly as it would
when the program itself does `import x`). Viper modules (.vp) are only
*parsed*, never executed, when analyzed.
"""
from __future__ import annotations

import builtins as _py_builtins
import importlib
import importlib.util
import inspect
import os
import re
import sys
from dataclasses import dataclass, field

from lark import Tree, Token
from lark.exceptions import UnexpectedInput

from .parser import parser
from .keywords import KEYWORDS, BUILTINS

_PRELUDE_DOCS = {
    "pp": ("pp(obj)", "Pretty-print any object (Viper prelude)."),
    "read_file": ("read_file(path, encoding='utf-8') -> str", "Read a whole file as text (Viper prelude)."),
    "write_file": ("write_file(path, text, encoding='utf-8') -> int", "Write text to a file (Viper prelude)."),
    "clamp": ("clamp(x, lo, hi)", "Clamp x into the range [lo, hi] (Viper prelude)."),
}


def _rule(node) -> str:
    data = node.data
    return data.value if isinstance(data, Token) else data


# ------------------------------------------------------------------ results

# sort groups: lower shows first in the editor (Pylance-style priorities)
GROUP_LOCAL = 0      # parameters, inferred members, self.
GROUP_DOCUMENT = 1   # fns / classes / lets defined in this file
GROUP_MEMBER = 2     # imported module members, module names
GROUP_BUILTIN = 3    # builtins + prelude
GROUP_KEYWORD = 4    # language keywords
GROUP_AUTOIMPORT = 5 # workspace symbols not imported yet
GROUP_SNIPPET = 6    # statement templates


@dataclass
class Completion:
    label: str
    kind: str = "text"        # keyword | function | class | variable | module | method | property | snippet
    detail: str = ""
    documentation: str = ""
    sort_group: int = GROUP_BUILTIN
    insert_text: str | None = None      # LSP snippet syntax when snippet=True
    snippet: bool = False
    extra_edit: tuple[int, str] | None = None  # (line, text) inserted at line start


@dataclass
class Signature:
    label: str
    parameters: list[str] = field(default_factory=list)
    active_parameter: int = 0
    documentation: str = ""


@dataclass
class FnSymbol:
    name: str
    params: list[str] = field(default_factory=list)
    return_type: str | None = None
    doc: str = ""
    is_async: bool = False
    line: int = 0
    end_line: int = 0

    def signature(self) -> str:
        kw = "async fn" if self.is_async else "fn"
        arrow = f" -> {self.return_type}" if self.return_type else ""
        return f"{kw} {self.name}({', '.join(self.params)}){arrow}"


@dataclass
class ClassSymbol:
    name: str
    methods: dict[str, FnSymbol] = field(default_factory=dict)
    attrs: dict[str, int] = field(default_factory=dict)          # self.x -> line
    doc: str = ""
    line: int = 0
    end_line: int = 0


@dataclass
class DocumentInfo:
    fns: dict[str, FnSymbol] = field(default_factory=dict)
    classes: dict[str, ClassSymbol] = field(default_factory=dict)
    lets: dict[str, int] = field(default_factory=dict)          # name -> line
    imports: dict[str, str] = field(default_factory=dict)       # alias -> dotted module
    from_imports: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (module, original)


@dataclass
class Symbol:
    """Outline entry (LSP documentSymbol), lines 0-based."""
    name: str
    kind: str                 # function | class | method | variable
    line: int
    end_line: int
    detail: str = ""
    children: list[Symbol] = field(default_factory=list)


# ----------------------------------------------------------------- caching
# One parse per buffer state: every request on unchanged text is a dict hit.

_LAST_GOOD: dict[str, DocumentInfo] = {}                 # last clean parse
_ANALYSIS: dict[str, tuple[int, DocumentInfo]] = {}      # key -> (hash, info)
_TOLERANT: dict[str, tuple[int, DocumentInfo]] = {}
_MODULE_MEMBERS: dict[str, list[Completion]] = {}        # python modules
_VP_MEMBERS: dict[str, tuple[float, DocumentInfo]] = {}  # path -> (mtime, info)
_TYPE_MEMBERS: dict[str, list[Completion]] = {}          # 'str' -> methods
_STDLIB_NAMES: list[Completion] | None = None
_BUILTIN_CACHE: list[Completion] | None = None


# ------------------------------------------------------------ tree walking

def _params_of(param_list: Tree | None) -> list[str]:
    if param_list is None:
        return []
    out = []
    for p in param_list.children:
        if not (isinstance(p, Tree) and _rule(p) == "param"):
            continue
        name = p.children[0].value
        ptype = default = None
        for c in p.children[1:]:
            if isinstance(c, Tree) and _rule(c) == "type":
                base = c.children[0].value
                args = [t.children[0].value for t in c.children[1:] if isinstance(t, Tree)]
                ptype = f"{base}[{', '.join(args)}]" if args else base
            else:
                default = "…"
        piece = name
        if ptype:
            piece += f": {ptype}"
        if default:
            piece += f" = {default}"
        out.append(piece)
    return out


def _docstring(suite: Tree | None) -> str:
    """First statement of a suite, if it's a plain string literal."""
    if suite is None:
        return ""
    for stmt in suite.children:
        if not isinstance(stmt, Tree):
            continue
        node = stmt
        while isinstance(node, Tree) and _rule(node) in ("simple_stmt", "expr_stmt", "pipe_expr", "conditional"):
            kids = [c for c in node.children if isinstance(c, Tree)]
            if not kids:
                return ""
            node = kids[0]
        if isinstance(node, Tree) and _rule(node) == "string":
            raw = node.children[0].value
            return raw.strip("\"'")
        return ""
    return ""


def _fn_symbol(node: Tree, is_async: bool = False) -> FnSymbol:
    ch = [c for c in node.children
          if not (isinstance(c, Tree) and _rule(c) == "decorator")]
    name = ch[0].value
    params: list[str] = []
    ret = None
    suite = None
    for c in ch[1:]:
        if isinstance(c, Tree) and _rule(c) == "param_list":
            params = _params_of(c)
        elif isinstance(c, Tree) and _rule(c) == "type":
            base = c.children[0].value
            args = [t.children[0].value for t in c.children[1:] if isinstance(t, Tree)]
            ret = f"{base}[{', '.join(args)}]" if args else base
        elif isinstance(c, Tree) and _rule(c) == "suite":
            suite = c
    return FnSymbol(name=name, params=params, return_type=ret,
                    doc=_docstring(suite), is_async=is_async,
                    line=node.meta.line, end_line=getattr(node.meta, "end_line", node.meta.line))


def _collect_names(node) -> list[str]:
    out: list[str] = []
    def walk(n):
        if isinstance(n, Tree):
            if _rule(n) == "name":
                out.append(n.children[0].value)
                return
            for c in n.children:
                walk(c)
    walk(node)
    return out


_RE_SELF_ATTR = re.compile(r"\bself\.(\w+)\s*=[^=]")


def _collect_class_attrs(info: DocumentInfo, source: str) -> None:
    """self.x = ... assignments inside each class's line range."""
    lines = source.splitlines()
    for cls in info.classes.values():
        end = max([cls.end_line] + [m.end_line for m in cls.methods.values()])
        cls.end_line = max(end, cls.line)
        for i in range(cls.line - 1, min(cls.end_line, len(lines))):
            for m in _RE_SELF_ATTR.finditer(lines[i]):
                cls.attrs.setdefault(m.group(1), i + 1)


def _build_info(tree: Tree, source: str) -> DocumentInfo:
    info = DocumentInfo()

    def visit(node: Tree, in_class: ClassSymbol | None = None):
        for stmt in node.children:
            if not isinstance(stmt, Tree):
                continue
            r = _rule(stmt)
            if r == "simple_stmt":
                inner = next((c for c in stmt.children if isinstance(c, Tree)), None)
                if inner is not None:
                    visit_simple(inner)
            elif r == "fn_def":
                sym = _fn_symbol(stmt)
                if in_class is not None:
                    in_class.methods[sym.name] = sym
                else:
                    info.fns[sym.name] = sym
                suite = next((c for c in stmt.children if isinstance(c, Tree) and _rule(c) == "suite"), None)
                if suite is not None:
                    visit(suite, None)
            elif r == "async_stmt":
                tail = next((c for c in stmt.children
                             if isinstance(c, Tree) and _rule(c).startswith("async_")), None)
                if tail is not None and _rule(tail) == "async_fn_tail":
                    sym = _fn_symbol(tail, is_async=True)
                    sym.line = stmt.meta.line
                    sym.end_line = getattr(stmt.meta, "end_line", stmt.meta.line)
                    if in_class is not None:
                        in_class.methods[sym.name] = sym
                    else:
                        info.fns[sym.name] = sym
                suite = next((c for c in (tail.children if tail is not None else [])
                              if isinstance(c, Tree) and _rule(c) == "suite"), None)
                if suite is not None:
                    visit(suite, None)
            elif r == "class_def":
                ch = [c for c in stmt.children
                      if not (isinstance(c, Tree) and _rule(c) == "decorator")]
                cname = ch[0].value
                csym = ClassSymbol(name=cname, line=stmt.meta.line,
                                   end_line=getattr(stmt.meta, "end_line", stmt.meta.line))
                suite = next((c for c in ch if isinstance(c, Tree) and _rule(c) == "suite"), None)
                csym.doc = _docstring(suite)
                if suite is not None:
                    visit(suite, csym)
                info.classes[cname] = csym
            else:
                # every other compound statement: descend into its suites
                for c in stmt.children:
                    if isinstance(c, Tree) and _rule(c) in ("suite", "elif_clause",
                                                            "else_clause", "except_clause",
                                                            "finally_clause", "match_case"):
                        visit(c, in_class)

    def visit_simple(inner: Tree):
        r = _rule(inner)
        if r == "let_stmt":
            for name in _collect_names(inner.children[0]):
                info.lets[name] = inner.meta.line
        elif r == "import_plain":
            for imp in inner.children:
                dotted = ".".join(t.value for t in imp.children[0].children)
                alias = imp.children[1].value if len(imp.children) == 2 else dotted.split(".")[0]
                info.imports[alias] = dotted if len(imp.children) == 2 else dotted.split(".")[0]
        elif r == "import_from":
            module = ".".join(t.value for t in inner.children[0].children)
            targets = inner.children[1]
            if _rule(targets) != "import_star":
                for tgt in targets.children:
                    orig = tgt.children[0].value
                    local = tgt.children[1].value if len(tgt.children) == 2 else orig
                    info.from_imports[local] = (module, orig)

    visit(tree)
    _collect_class_attrs(info, source)
    return info


def analyze(source: str, cache_key: str | None = None) -> DocumentInfo:
    h = hash(source)
    if cache_key is not None:
        hit = _ANALYSIS.get(cache_key)
        if hit is not None and hit[0] == h:
            return hit[1]
    try:
        tree = parser.parse(source)
    except Exception:
        if cache_key is not None and cache_key in _LAST_GOOD:
            return _LAST_GOOD[cache_key]
        return DocumentInfo()
    info = _build_info(tree, source)
    if cache_key is not None:
        _LAST_GOOD[cache_key] = info
        _ANALYSIS[cache_key] = (h, info)
        _TOLERANT[cache_key] = (h, info)
    return info


def parse_error(source: str, cache_key: str | None = None) -> UnexpectedInput | None:
    """Single-parse validation for the LSP: returns the syntax error (or None)
    and feeds the analysis caches so the completion that follows is free."""
    h = hash(source)
    if cache_key is not None:
        hit = _ANALYSIS.get(cache_key)
        if hit is not None and hit[0] == h:
            return None
    try:
        tree = parser.parse(source)
    except UnexpectedInput as e:
        return e
    except Exception:
        return None  # exotic buffer: never crash, just don't report
    info = _build_info(tree, source)
    if cache_key is not None:
        _LAST_GOOD[cache_key] = info
        _ANALYSIS[cache_key] = (h, info)
        _TOLERANT[cache_key] = (h, info)
    return None


# ----------------------------------------------- fallback line-scan analysis
# When the buffer doesn't parse (mid-keystroke, or syntax this grammar doesn't
# know), completions must not go dark: scan lines for definitions instead.

_RE_FN = re.compile(r"^(\s*)(async\s+)?fn\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^:]+))?:")
_RE_CLASS = re.compile(r"^(\s*)class\s+(\w+)")
_RE_LET = re.compile(r"^\s*let\s+(\w+(?:\s*,\s*\w+)*)\s*=")
_RE_IMPORT = re.compile(r"^\s*import\s+([\w.]+)(?:\s+as\s+(\w+))?\s*$")
_RE_FROM = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+([\w, ]+)$")


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """1-based last line of the block opened at lines[start-1] with `indent`."""
    end = start
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not s:
            continue
        if len(lines[j]) - len(lines[j].lstrip()) <= indent:
            break
        end = j + 1
    return end


def _scan_fallback(source: str) -> DocumentInfo:
    info = DocumentInfo()
    lines = source.splitlines()
    cur_class: tuple[ClassSymbol, int] | None = None
    for i, ln in enumerate(lines, start=1):
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip())
        if cur_class is not None and indent <= cur_class[1]:
            cur_class = None
        m = _RE_FN.match(ln)
        if m:
            params = [p.strip() for p in m.group(4).split(",") if p.strip()]
            ret = m.group(5).strip() if m.group(5) else None
            sym = FnSymbol(name=m.group(3), params=params, return_type=ret,
                           is_async=bool(m.group(2)), line=i,
                           end_line=_block_end(lines, i, indent))
            if cur_class is not None and indent > cur_class[1]:
                cur_class[0].methods[sym.name] = sym
            else:
                info.fns[sym.name] = sym
            continue
        m = _RE_CLASS.match(ln)
        if m:
            csym = ClassSymbol(name=m.group(2), line=i,
                               end_line=_block_end(lines, i, indent))
            info.classes[csym.name] = csym
            cur_class = (csym, indent)
            continue
        m = _RE_LET.match(ln)
        if m:
            for name in m.group(1).split(","):
                info.lets.setdefault(name.strip(), i)
            continue
        m = _RE_IMPORT.match(ln)
        if m:
            dotted, alias = m.group(1), m.group(2)
            info.imports[alias or dotted.split(".")[0]] = dotted if alias else dotted.split(".")[0]
            continue
        m = _RE_FROM.match(ln)
        if m:
            for part in m.group(2).split(","):
                name = part.strip()
                if name:
                    info.from_imports[name] = (m.group(1), name)
    _collect_class_attrs(info, source)
    return info


def _merge_info(base: DocumentInfo, extra: DocumentInfo) -> DocumentInfo:
    """base wins (richer docs/positions); extra fills what base lacks."""
    out = DocumentInfo(fns=dict(base.fns), classes=dict(base.classes),
                       lets=dict(base.lets), imports=dict(base.imports),
                       from_imports=dict(base.from_imports))
    for name, fn in extra.fns.items():
        out.fns.setdefault(name, fn)
    for name, cls in extra.classes.items():
        out.classes.setdefault(name, cls)
    for name, line in extra.lets.items():
        out.lets.setdefault(name, line)
    for k, v in extra.imports.items():
        out.imports.setdefault(k, v)
    for k, v in extra.from_imports.items():
        out.from_imports.setdefault(k, v)
    return out


def _analyze_tolerant(source: str, line: int, cache_key: str | None) -> DocumentInfo:
    """Best-possible DocumentInfo for a buffer that may be broken mid-keystroke:
    clean parse -> parse with cursor line blanked -> line-scan merged with the
    last good parse. Memoized per buffer state."""
    h = hash(source)
    if cache_key is not None:
        hit = _TOLERANT.get(cache_key)
        if hit is not None and hit[0] == h:
            return hit[1]
    info: DocumentInfo | None = None
    try:
        info = _build_info(parser.parse(source), source)
        if cache_key is not None:
            _LAST_GOOD[cache_key] = info
            _ANALYSIS[cache_key] = (h, info)
    except Exception:
        lines = source.splitlines()
        if 0 <= line < len(lines):
            patched = "\n".join(lines[:line] + [""] + lines[line + 1:])
            try:
                info = _build_info(parser.parse(patched), patched)
            except Exception:
                pass
        if info is None:
            info = _scan_fallback(source)
        last = _LAST_GOOD.get(cache_key) if cache_key is not None else None
        if last is not None:
            info = _merge_info(last, info)
    if cache_key is not None:
        _TOLERANT[cache_key] = (h, info)
    return info


# --------------------------------------------------------- module members

def _vp_module_path(name: str, workspace_dirs) -> str | None:
    if "." in name:
        return None
    for d in workspace_dirs:
        cand = os.path.join(d, name + ".vp")
        if os.path.isfile(cand):
            return cand
    return None


def _vp_module_info(path: str) -> DocumentInfo | None:
    """Parse (never execute) a workspace .vp module, cached by mtime."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _VP_MEMBERS.get(path)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return None
    try:
        info = _build_info(parser.parse(source), source)
    except Exception:
        info = _scan_fallback(source)
    _VP_MEMBERS[path] = (mtime, info)
    return info


def _vp_module_members(path: str) -> list[Completion]:
    info = _vp_module_info(path)
    if info is None:
        return []
    out = []
    for name, fn in info.fns.items():
        out.append(Completion(name, "function", fn.signature(), fn.doc, GROUP_MEMBER))
    for name, cls in info.classes.items():
        out.append(Completion(name, "class", f"class {name}", cls.doc, GROUP_MEMBER))
    for name in info.lets:
        out.append(Completion(name, "variable", "let (module-level)", "", GROUP_MEMBER))
    return out


def _resolve_python(dotted: str):
    """Import the base module and getattr down the chain. None on any failure."""
    parts = dotted.split(".")
    try:
        if importlib.util.find_spec(parts[0]) is None:
            return None
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    try:
        obj = importlib.import_module(parts[0])
    except BaseException:
        return None
    for attr in parts[1:]:
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            # maybe it's a submodule that isn't imported yet (e.g. os.path is,
            # but importlib.util isn't until you import it)
            try:
                obj = importlib.import_module(".".join(parts[:parts.index(attr) + 1]))
            except BaseException:
                return None
        except BaseException:
            return None
    return obj


def _doc_head(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.split("\n\n")[0][:500]


def _py_signature(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except (ValueError, TypeError):
        return "(…)"


def _classify(name: str, obj, group: int = GROUP_MEMBER) -> Completion:
    if inspect.ismodule(obj):
        return Completion(name, "module", "module", _doc_head(obj), group)
    if inspect.isclass(obj):
        return Completion(name, "class", f"class {name}{_py_signature(obj)}", _doc_head(obj), group)
    if callable(obj):
        return Completion(name, "function", f"{name}{_py_signature(obj)}", _doc_head(obj), group)
    return Completion(name, "variable", type(obj).__name__, "", group)


def module_members(dotted: str, workspace_dirs=()) -> list[Completion]:
    vp = _vp_module_path(dotted, workspace_dirs)
    if vp is not None:
        return _vp_module_members(vp)
    cached = _MODULE_MEMBERS.get(dotted)
    if cached is not None:
        return cached
    obj = _resolve_python(dotted)
    if obj is None:
        return []
    out = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(obj, name)
        except BaseException:
            continue
        out.append(_classify(name, attr))
    _MODULE_MEMBERS[dotted] = out
    return out


def module_names(workspace_dirs=()) -> list[Completion]:
    global _STDLIB_NAMES
    if _STDLIB_NAMES is None:
        _STDLIB_NAMES = [Completion(m, "module", "stdlib module", "", GROUP_MEMBER)
                         for m in sorted(sys.stdlib_module_names) if not m.startswith("_")]
    out = list(_STDLIB_NAMES)
    for d in workspace_dirs:
        try:
            for f in sorted(os.listdir(d)):
                if f.endswith(".vp"):
                    out.append(Completion(f[:-3], "module", "Viper module (.vp)", "", GROUP_MEMBER))
        except OSError:
            pass
    return out


# ---------------------------------------------------------- type inference

# what calling a builtin gives you (enough for method completion on the result)
_CALL_RESULT_TYPES = {
    "int": "int", "float": "float", "str": "str", "bool": "bool",
    "list": "list", "dict": "dict", "set": "set", "tuple": "tuple",
    "len": "int", "sum": "int", "sorted": "list", "input": "str",
    "repr": "str", "hex": "str", "bin": "str", "oct": "str", "chr": "str",
    "ord": "int", "hash": "int", "read_file": "str",
}

_RE_LET_TYPED = re.compile(r"^\s*let\s+(\w+)\s*(?::\s*([\w\[\]., ]+?)\s*)?=\s*(.+?)\s*$")
_RE_PARAM = re.compile(r"^\s*(\w+)\s*:\s*([\w\[\]., ]+?)\s*(?:=.*)?$")


def _infer_expr_type(rhs: str, info: DocumentInfo) -> str | None:
    rhs = rhs.strip()
    if re.match(r"""^(?:[frbu]{1,2})?["']""", rhs, re.IGNORECASE):
        return "str"
    if re.match(r"^-?(?:\d+\.\d*|\.\d+|\d+[eE][-+]?\d+)", rhs):
        return "float"
    if re.match(r"^-?\d+$", rhs):
        return "int"
    if rhs.startswith("["):
        return "list"
    if rhs.startswith("{"):
        head = rhs[1:rhs.find("}")] if "}" in rhs else rhs[1:]
        return "dict" if (":" in head or not head.strip()) else "set"
    if rhs.startswith("("):
        return "tuple"
    if re.match(r"^(True|False)\b", rhs):
        return "bool"
    m = re.match(r"^(\w+)\s*\(", rhs)
    if m:
        callee = m.group(1)
        if callee in info.classes:
            return callee
        if callee in _CALL_RESULT_TYPES:
            return _CALL_RESULT_TYPES[callee]
        fn = info.fns.get(callee)
        if fn is not None and fn.return_type:
            return fn.return_type.split("[")[0].strip()
    return None


def _local_types(source: str, line: int, info: DocumentInfo) -> dict[str, str]:
    """name -> type for everything inferable in scope at `line` (0-based)."""
    types: dict[str, str] = {}
    for ln in source.splitlines():
        m = _RE_LET_TYPED.match(ln)
        if m is None:
            continue
        name, annot, rhs = m.groups()
        t = annot.split("[")[0].strip() if annot else _infer_expr_type(rhs, info)
        if t:
            types[name] = t
    fn = _enclosing_fn(info, line)
    if fn is not None:
        for p in fn.params:
            m = _RE_PARAM.match(p)
            if m:
                types[m.group(1)] = m.group(2).split("[")[0].strip()
    return types


def _enclosing_fn(info: DocumentInfo, line: int) -> FnSymbol | None:
    cands = list(info.fns.values())
    for cls in info.classes.values():
        cands.extend(cls.methods.values())
    best = None
    for fn in cands:
        if fn.line - 1 <= line <= fn.end_line - 1:
            if best is None or fn.line > best.line:
                best = fn
    return best


def _enclosing_class(info: DocumentInfo, line: int) -> ClassSymbol | None:
    best = None
    for cls in info.classes.values():
        if cls.line - 1 <= line <= cls.end_line - 1:
            if best is None or cls.line > best.line:
                best = cls
    return best


def _class_member_completions(cls: ClassSymbol) -> list[Completion]:
    out = []
    for name, m in cls.methods.items():
        shown = FnSymbol(name=m.name, params=[p for p in m.params if p.split(":")[0].strip() != "self"],
                         return_type=m.return_type, is_async=m.is_async)
        out.append(Completion(name, "method", shown.signature(), m.doc, GROUP_LOCAL))
    for name in cls.attrs:
        if name not in cls.methods:
            out.append(Completion(name, "property", f"attribute of {cls.name}", "", GROUP_LOCAL))
    return out


def _type_member_completions(tname: str, info: DocumentInfo) -> list[Completion]:
    if tname in info.classes:
        return _class_member_completions(info.classes[tname])
    cached = _TYPE_MEMBERS.get(tname)
    if cached is not None:
        return cached
    pytype = getattr(_py_builtins, tname, None)
    if not isinstance(pytype, type):
        return []
    out = []
    for name in dir(pytype):
        if name.startswith("_"):
            continue
        try:
            member = getattr(pytype, name)
        except BaseException:
            continue
        c = _classify(name, member, GROUP_LOCAL)
        c.kind = "method" if callable(member) else "property"
        c.detail = f"{tname}.{c.label}{_py_signature(member) if callable(member) else ''}"
        out.append(c)
    _TYPE_MEMBERS[tname] = out
    return out


# --------------------------------------------------- auto-import completions

def _auto_import_completions(source: str, info: DocumentInfo,
                             workspace_dirs, cache_key: str | None) -> list[Completion]:
    """Pylance-style: offer top-level symbols of workspace .vp modules that
    aren't imported yet; picking one inserts the `from x import y` line."""
    own = os.path.basename(cache_key or "")
    own = own[:-3] if own.endswith(".vp") else own.split(".")[0]
    in_scope = (set(info.fns) | set(info.classes) | set(info.lets)
                | set(info.imports) | set(info.from_imports))
    # insert new imports right after the last existing top-level import
    insert_at = 0
    for i, ln in enumerate(source.splitlines()):
        if re.match(r"^(import|from)\s", ln):
            insert_at = i + 1
    out: list[Completion] = []
    seen: set[str] = set()
    for d in workspace_dirs:
        try:
            files = sorted(os.listdir(d))
        except OSError:
            continue
        for f in files:
            if not f.endswith(".vp"):
                continue
            mod = f[:-3]
            if mod == own or mod in info.imports:
                continue
            minfo = _vp_module_info(os.path.join(d, f))
            if minfo is None:
                continue
            for name, fn in minfo.fns.items():
                if name in in_scope or name in seen:
                    continue
                seen.add(name)
                out.append(Completion(
                    name, "function", f"{fn.signature()} — auto-import from {mod}",
                    fn.doc, GROUP_AUTOIMPORT,
                    extra_edit=(insert_at, f"from {mod} import {name}\n")))
            for name, cls in minfo.classes.items():
                if name in in_scope or name in seen:
                    continue
                seen.add(name)
                out.append(Completion(
                    name, "class", f"class {name} — auto-import from {mod}",
                    cls.doc, GROUP_AUTOIMPORT,
                    extra_edit=(insert_at, f"from {mod} import {name}\n")))
    return out


# ------------------------------------------------------------- completions

_ASYNC_FOLLOWERS = ["fn", "for", "with"]

_SNIPPETS = [
    ("fn", "fn definition", "fn ${1:name}(${2:params}):\n\t${0:pass}"),
    ("async fn", "async fn definition", "async fn ${1:name}(${2:params}):\n\t${0:pass}"),
    ("if", "if block", "if ${1:condition}:\n\t${0:pass}"),
    ("for", "for loop", "for ${1:item} in ${2:iterable}:\n\t${0:pass}"),
    ("while", "while loop", "while ${1:condition}:\n\t${0:pass}"),
    ("class", "class definition",
     "class ${1:Name}:\n\tfn __init__(self${2}):\n\t\t${0:pass}"),
    ("match", "match statement", "match ${1:value}:\n\tcase ${2:pattern}:\n\t\t${0:pass}"),
    ("try", "try/except block", "try:\n\t${1:pass}\nexcept ${2:Exception} as e:\n\t${0:pass}"),
]


def _in_comment_or_string(prefix: str) -> bool:
    in_str = None
    escape = False
    for ch in prefix:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("\"", "'"):
            in_str = ch
        elif ch == "#":
            return True
    return in_str is not None


def _resolve_chain_to_module(chain: str, info: DocumentInfo) -> str | None:
    """'np.linalg' with 'import numpy as np' -> 'numpy.linalg'."""
    parts = chain.split(".")
    base = parts[0]
    if base in info.imports:
        return ".".join([info.imports[base]] + parts[1:])
    if base in info.from_imports:
        module, orig = info.from_imports[base]
        return ".".join([module, orig] + parts[1:])
    # not imported (yet) — try it as a module path anyway ('sys.' just works)
    return chain


def keyword_completions() -> list[Completion]:
    return [Completion(kw, "keyword", sort_group=GROUP_KEYWORD) for kw in KEYWORDS]


def builtin_completions() -> list[Completion]:
    global _BUILTIN_CACHE
    if _BUILTIN_CACHE is None:
        out = []
        for name in BUILTINS:
            if name in _PRELUDE_DOCS:
                sig, doc = _PRELUDE_DOCS[name]
                out.append(Completion(name, "function", sig, doc, GROUP_BUILTIN))
                continue
            obj = getattr(_py_builtins, name, None)
            if obj is None:
                continue
            out.append(_classify(name, obj, GROUP_BUILTIN))
        _BUILTIN_CACHE = out
    return list(_BUILTIN_CACHE)


def snippet_completions() -> list[Completion]:
    return [Completion(label, "snippet", detail, f"```viper\n{body.replace(chr(9), '    ')}\n```",
                       GROUP_SNIPPET, insert_text=body, snippet=True)
            for label, detail, body in _SNIPPETS]


def document_completions(info: DocumentInfo, line: int) -> list[Completion]:
    out = []
    for name, fn in info.fns.items():
        out.append(Completion(name, "function", fn.signature(), fn.doc, GROUP_DOCUMENT))
        if fn.line - 1 <= line <= fn.end_line - 1:   # cursor inside this fn
            for p in fn.params:
                out.append(Completion(p.split(":")[0].split("=")[0].strip(),
                                      "variable", f"parameter of {name}", "", GROUP_LOCAL))
    for name, cls in info.classes.items():
        out.append(Completion(name, "class", f"class {name}", cls.doc, GROUP_DOCUMENT))
        for m in cls.methods.values():
            if m.line - 1 <= line <= m.end_line - 1:
                for p in m.params:
                    out.append(Completion(p.split(":")[0].split("=")[0].strip(),
                                          "variable", f"parameter of {name}.{m.name}",
                                          "", GROUP_LOCAL))
    for name in info.lets:
        out.append(Completion(name, "variable", "let", "", GROUP_DOCUMENT))
    for alias, module in info.imports.items():
        out.append(Completion(alias, "module", f"import {module}", "", GROUP_DOCUMENT))
    for local, (module, orig) in info.from_imports.items():
        out.append(Completion(local, "variable", f"from {module} import {orig}", "", GROUP_DOCUMENT))
    return out


def complete(source: str, line: int, character: int,
             workspace_dirs=(), cache_key: str | None = None) -> list[Completion]:
    lines = source.splitlines()
    prefix = lines[line][:character] if 0 <= line < len(lines) else ""

    if _in_comment_or_string(prefix):
        return []

    info = _analyze_tolerant(source, line, cache_key)

    m = re.search(r"\bfrom\s+([\w.]+)\s+import\s+\w*$", prefix)
    if m:
        return module_members(m.group(1), workspace_dirs)
    if re.search(r"\b(import|from)\s+[\w.]*$", prefix):
        return module_names(workspace_dirs)
    m = re.search(r"([\w.]+)\.\w*$", prefix)
    if m:
        chain = m.group(1)
        if "." not in chain:
            if chain == "self":
                cls = _enclosing_class(info, line)
                if cls is not None:
                    return _class_member_completions(cls)
            tname = _local_types(source, line, info).get(chain)
            if tname:
                members = _type_member_completions(tname, info)
                if members:
                    return members
        dotted = _resolve_chain_to_module(chain, info)
        return module_members(dotted, workspace_dirs) if dotted else []
    if re.search(r"\basync\s+\w*$", prefix):
        return [Completion(k, "keyword", sort_group=GROUP_KEYWORD) for k in _ASYNC_FOLLOWERS]

    out = document_completions(info, line)
    out += _auto_import_completions(source, info, workspace_dirs, cache_key)
    out += builtin_completions()
    out += keyword_completions()
    if prefix.strip() == "" or re.fullmatch(r"\s*[A-Za-z_]\w*", prefix):
        out += snippet_completions()   # statement position: offer templates
    return out


# ---------------------------------------------------------- signature help

def _find_call(text: str) -> tuple[str, int] | None:
    """Scan back from the cursor for the innermost unclosed call.
    Returns (callee_chain, active_parameter)."""
    depth = 0
    commas = 0
    in_str = None
    i = len(text) - 1
    while i >= 0:
        ch = text[i]
        if in_str:
            if ch == in_str and (i == 0 or text[i - 1] != "\\"):
                in_str = None
        elif ch in ("\"", "'"):
            in_str = ch
        elif ch in ")]}":
            depth += 1
        elif ch in "([{":
            if depth == 0 and ch == "(":
                m = re.search(r"([\w.]+)\s*$", text[:i])
                if m:
                    return m.group(1), commas
                return None
            depth -= 1
        elif ch == "," and depth == 0:
            commas += 1
        i -= 1
    return None


def _sig_for_name(name: str, info: DocumentInfo, workspace_dirs=()) -> Signature | None:
    if name in info.fns:
        fn = info.fns[name]
        return Signature(fn.signature(), fn.params, documentation=fn.doc)
    if name in info.classes:
        cls = info.classes[name]
        init = cls.methods.get("__init__")
        params = [p for p in init.params if not p.startswith("self")] if init else []
        return Signature(f"class {name}({', '.join(params)})", params, documentation=cls.doc)
    if name in _PRELUDE_DOCS:
        sig, doc = _PRELUDE_DOCS[name]
        inner = sig[sig.index("(") + 1:sig.rindex(")")]
        params = [p.strip() for p in inner.split(",")] if inner else []
        return Signature(sig, params, documentation=doc)
    if "." in name:
        base = name.split(".")[0]
        # method call on a user class instance: p.dist( with let p = Point(...)
        cls_name = None
        if base in info.classes:
            cls_name = base
        if cls_name is None:
            # via inferred local; scan without cursor context (line unknown here)
            pass
        dotted = _resolve_chain_to_module(name, info)
        obj = _resolve_python(dotted) if dotted else None
    else:
        obj = getattr(_py_builtins, name, None)
        if obj is None and name in info.imports:
            obj = _resolve_python(info.imports[name])
        if obj is None and name in info.from_imports:
            module, orig = info.from_imports[name]
            obj = _resolve_python(f"{module}.{orig}")
    if obj is not None and callable(obj):
        sig = _py_signature(obj)
        inner = sig[1:-1] if sig.startswith("(") else ""
        params = [p.strip() for p in inner.split(",")] if inner.strip() else []
        return Signature(f"{name.split('.')[-1]}{sig}", params, documentation=_doc_head(obj))
    return None


def signature_help(source: str, line: int, character: int,
                   workspace_dirs=(), cache_key: str | None = None) -> Signature | None:
    lines = source.splitlines()
    if not (0 <= line < len(lines)):
        return None
    text = "\n".join(lines[:line] + [lines[line][:character]])
    found = _find_call(text)
    if found is None:
        return None
    callee, active = found
    info = _analyze_tolerant(source, line, cache_key)
    sig = _sig_for_name(callee, info, workspace_dirs)
    if sig is None and "." in callee:
        # method on an inferred local: p.translate( / s.upper(
        base, _, meth = callee.partition(".")
        tname = None
        if base == "self":
            cls = _enclosing_class(info, line)
            tname = cls.name if cls is not None else None
        else:
            tname = _local_types(source, line, info).get(base)
        if tname and "." not in meth:
            if tname in info.classes:
                m = info.classes[tname].methods.get(meth)
                if m is not None:
                    params = [p for p in m.params if p.split(":")[0].strip() != "self"]
                    sig = Signature(f"{meth}({', '.join(params)})", params, documentation=m.doc)
            else:
                pytype = getattr(_py_builtins, tname, None)
                member = getattr(pytype, meth, None) if isinstance(pytype, type) else None
                if member is not None and callable(member):
                    s = _py_signature(member)
                    inner = s[1:-1] if s.startswith("(") else ""
                    params = [p.strip() for p in inner.split(",")] if inner.strip() else []
                    params = [p for p in params if p not in ("self", "/")]
                    sig = Signature(f"{meth}({', '.join(params)})", params,
                                    documentation=_doc_head(member))
    if sig is not None:
        sig.active_parameter = min(active, max(len(sig.parameters) - 1, 0))
    return sig


# ------------------------------------------------------------------- hover

def hover(source: str, line: int, character: int,
          workspace_dirs=(), cache_key: str | None = None) -> str | None:
    lines = source.splitlines()
    if not (0 <= line < len(lines)):
        return None
    text = lines[line]
    # expand a dotted chain around the cursor
    start = character
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "._"):
        start -= 1
    end = character
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    chain = text[start:end]
    if not chain or chain[0].isdigit():
        return None

    info = _analyze_tolerant(source, line, cache_key)

    if chain in KEYWORDS:
        return f"```viper\n{chain}\n```\nViper keyword — see `viper help {chain}`."
    sig = _sig_for_name(chain, info, workspace_dirs)
    if sig is not None:
        body = f"```viper\n{sig.label}\n```"
        if sig.documentation:
            body += f"\n\n{sig.documentation}"
        return body
    if chain in info.lets:
        tname = _local_types(source, line, info).get(chain)
        typed = f": {tname}" if tname else ""
        return f"```viper\nlet {chain}{typed}\n```\ndefined at line {info.lets[chain]}"
    if chain in info.imports:
        obj = _resolve_python(info.imports[chain])
        doc = _doc_head(obj) if obj else ""
        return f"```viper\nimport {info.imports[chain]}\n```" + (f"\n\n{doc}" if doc else "")
    # plain python object (module attr, builtin constant, …)
    dotted = _resolve_chain_to_module(chain, info) if "." in chain else None
    obj = _resolve_python(dotted) if dotted else None
    if obj is not None:
        c = _classify(chain.split(".")[-1], obj)
        body = f"```viper\n{c.detail or c.label}\n```"
        if c.documentation:
            body += f"\n\n{c.documentation}"
        return body
    return None


# --------------------------------------------- outline + go-to-definition

def document_symbols(source: str, cache_key: str | None = None) -> list[Symbol]:
    """Outline of the file (LSP documentSymbol), lines 0-based."""
    info = _analyze_tolerant(source, 0, cache_key)
    out: list[Symbol] = []
    for name, fn in info.fns.items():
        out.append(Symbol(name, "function", fn.line - 1, max(fn.end_line, fn.line) - 1,
                          fn.signature()))
    for name, cls in info.classes.items():
        kids = [Symbol(m.name, "method", m.line - 1, max(m.end_line, m.line) - 1, m.signature())
                for m in cls.methods.values()]
        out.append(Symbol(name, "class", cls.line - 1, max(cls.end_line, cls.line) - 1,
                          f"class {name}", kids))
    for name, ln in info.lets.items():
        out.append(Symbol(name, "variable", ln - 1, ln - 1, "let"))
    out.sort(key=lambda s: s.line)
    return out


def definition(source: str, line: int, character: int,
               workspace_dirs=(), cache_key: str | None = None) -> tuple[str | None, int] | None:
    """(file_path | None for current document, 0-based line) of the symbol
    under the cursor, or None if unknown."""
    lines = source.splitlines()
    if not (0 <= line < len(lines)):
        return None
    text = lines[line]
    start = character
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "._"):
        start -= 1
    end = character
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    chain = text[start:end]
    if not chain or chain[0].isdigit():
        return None

    info = _analyze_tolerant(source, line, cache_key)

    if "." in chain:
        base, _, member = chain.partition(".")
        if base == "self":
            cls = _enclosing_class(info, line)
            if cls is not None:
                if member in cls.methods:
                    return None, cls.methods[member].line - 1
                if member in cls.attrs:
                    return None, cls.attrs[member] - 1
            return None
        module = info.imports.get(base, base)
        path = _vp_module_path(module, workspace_dirs)
        if path is not None and "." not in member:
            minfo = _vp_module_info(path)
            if minfo is not None:
                if member in minfo.fns:
                    return path, minfo.fns[member].line - 1
                if member in minfo.classes:
                    return path, minfo.classes[member].line - 1
                if member in minfo.lets:
                    return path, minfo.lets[member] - 1
            return path, 0
        return None

    if chain in info.fns:
        return None, info.fns[chain].line - 1
    if chain in info.classes:
        return None, info.classes[chain].line - 1
    if chain in info.lets:
        return None, info.lets[chain] - 1
    cls = _enclosing_class(info, line)
    if cls is not None and chain in cls.methods:
        return None, cls.methods[chain].line - 1
    if chain in info.from_imports:
        module, orig = info.from_imports[chain]
        path = _vp_module_path(module, workspace_dirs)
        if path is not None:
            minfo = _vp_module_info(path)
            if minfo is not None:
                if orig in minfo.fns:
                    return path, minfo.fns[orig].line - 1
                if orig in minfo.classes:
                    return path, minfo.classes[orig].line - 1
            return path, 0
    if chain in info.imports:
        path = _vp_module_path(info.imports[chain], workspace_dirs)
        if path is not None:
            return path, 0
    return None
