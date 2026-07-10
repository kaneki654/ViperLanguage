"""Static type checking for Viper — make `let x: int = ...` mean something.

This is the pass that turns Viper's type annotations from decoration into a
guarantee: `let x: int = "hello"` is now a *transpile-time error*, not a silent
lie. It runs on the parse tree, so `viper run`, `viper build`, and the editor
(as live diagnostics) all catch the same mistakes.

Design rule: **conservative**. A type checker that cries wolf is worse than
none, so we only report a mismatch when the value's type is definitely known
(a literal, a call whose return type we know, or a variable we already typed)
AND definitely incompatible with the annotation. Anything uncertain — a custom
class that might subclass the annotation, an unknown call, arithmetic — is left
alone. False negatives are fine; false positives are not.

What is checked today:
  - `let name: T = value`      annotation vs the value's inferred type
  - `fn f(...) -> T: return v` declared return type vs each returned value
  - inference flows through:   literals, bytes/raw strings, True/False/None,
                               list/dict/set/tuple, typed `let`s and params,
                               builtin calls (str(), len(), ...) and the whole
                               stdlib prelude (sha256() -> str, ...), and calls
                               to user `fn`s that declare a return type.
"""
from lark import Tree, Token

from .errors import ViperError, _caret_block
from .parser import parser


def _rule(node) -> str:
    data = node.data
    return data.value if isinstance(data, Token) else data


# annotation base type -> the set of concrete value types it accepts.
# Mirrors Python's assignment compatibility (float accepts int; int accepts
# bool, since bool is an int subclass).
ACCEPTS = {
    "int": {"int", "bool"},
    "float": {"float", "int", "bool"},
    "bool": {"bool"},
    "str": {"str"},
    "bytes": {"bytes"},
    "list": {"list"},
    "dict": {"dict"},
    "set": {"set"},
    "tuple": {"tuple"},
}

# value types we trust ourselves to have inferred exactly. A custom class is
# deliberately NOT here: it might subclass the annotation, so we never flag it.
# NoneType cannot be subclassed, so flagging a stray None is always safe.
CONCRETE = set(ACCEPTS) | {"None"}


class TypeIssue:
    """A single type error: 1-based line/column and a message + hint."""
    def __init__(self, line: int, column: int, message: str, hint: str = ""):
        self.line = line
        self.column = column
        self.message = message
        self.hint = hint


def _stdlib_returns() -> dict:
    """name -> return type for prelude helpers, from their real annotations."""
    from . import std
    type_name = {str: "str", int: "int", float: "float", bool: "bool",
                 bytes: "bytes", list: "list", dict: "dict", set: "set",
                 tuple: "tuple", type(None): "None"}
    out = {}
    for name, fn in std.PRELUDE.items():
        ret = getattr(fn, "__annotations__", {}).get("return")
        if ret in type_name:
            out[name] = type_name[ret]
    return out


# return types of common Python builtins (only the unambiguous ones).
_BUILTIN_RETURNS = {
    "str": "str", "repr": "str", "hex": "str", "bin": "str", "oct": "str",
    "chr": "str", "input": "str", "format": "str",
    "int": "int", "len": "int", "ord": "int", "id": "int", "hash": "int",
    "float": "float",
    "bool": "bool", "isinstance": "bool", "issubclass": "bool",
    "callable": "bool", "hasattr": "bool", "any": "bool", "all": "bool",
    "list": "list", "sorted": "list", "dict": "dict", "set": "set",
    "tuple": "tuple", "bytes": "bytes",
}


def _peel(node):
    """Drop single-child pipe/conditional wrappers the grammar leaves around."""
    while isinstance(node, Tree) and _rule(node) in ("pipe_expr", "conditional") \
            and len(node.children) == 1:
        node = node.children[0]
    return node


def _num_type(text: str) -> str | None:
    s = text.replace("_", "")
    low = s.lower()
    if low.endswith("j"):
        return None  # complex — not something we annotate against
    if low.startswith(("0x", "0o", "0b")):
        return "int"
    if "." in s or "e" in low:
        return "float"
    return "int"


def _str_type(tokval: str) -> str:
    i = 0
    while i < len(tokval) and tokval[i] not in "\"'":
        i += 1
    return "bytes" if "b" in tokval[:i].lower() else "str"


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


class _Checker:
    def __init__(self, source: str):
        self.source = source
        self.issues: list[TypeIssue] = []
        self.fn_returns: dict[str, str] = {}    # user fn name -> return base
        self.classes: set[str] = set()
        self.consts: dict[str, int] = {}        # const name -> declaration line
        self.call_returns = dict(_BUILTIN_RETURNS)
        self.call_returns.update(_stdlib_returns())

    # -- inference ---------------------------------------------------------
    def infer(self, node, env: dict) -> str | None:
        """Best concrete type name for an expression, or None if unknown."""
        node = _peel(node)
        if not isinstance(node, Tree):
            return None
        r = _rule(node)
        if r == "number":
            return _num_type(node.children[0].value)
        if r == "string":
            return _str_type(node.children[0].value)
        if r == "fstring":
            return "str"
        if r == "const_true" or r == "const_false":
            return "bool"
        if r == "const_none":
            return "None"
        if r == "list_atom":
            return "list"
        if r == "tuple_literal" or r == "empty_tuple":
            return "tuple"
        if r == "brace_atom":
            if not node.children:
                return "dict"
            body = _rule(node.children[0])
            return "dict" if body in ("dict_items_body", "dict_comp_body") else "set"
        if r == "group":
            return self.infer(node.children[0], env)
        if r == "unary":
            op = node.children[0].children[0].value
            inner = self.infer(node.children[1], env)
            if op == "~":
                return "int" if inner in ("int", "bool") else None
            if op in ("+", "-"):
                return inner if inner in ("int", "float") else None
            return None
        if r == "name":
            return env.get(node.children[0].value)
        if r == "postfix":
            # a call: atom is a bare name and the last trailer is a call
            kids = node.children
            if len(kids) == 2 and _rule(kids[1]) == "call_trailer" \
                    and isinstance(kids[0], Tree) and _rule(kids[0]) == "name":
                callee = kids[0].children[0].value
                if callee in self.classes:
                    return callee               # a user-class instance
                if callee in self.fn_returns:
                    return self.fn_returns[callee]   # user fn's declared return
                return self.call_returns.get(callee)
            return None
        return None

    # -- reporting ---------------------------------------------------------
    def _check_assign(self, annot_base: str, value_node, env: dict,
                      line: int, column: int, what: str):
        if annot_base not in ACCEPTS:
            return  # not a builtin type we know how to check
        inferred = self.infer(value_node, env)
        if inferred not in CONCRETE:
            return  # unknown, or a custom class that might subclass — stay quiet
        if inferred in ACCEPTS[annot_base]:
            return  # compatible
        got = "None" if inferred == "None" else f"{_article(inferred)} {inferred}"
        self.issues.append(TypeIssue(
            line, column,
            f"{what} is annotated '{annot_base}' but the value is {got}",
            hint=f"use {_article(annot_base)} {annot_base} value, "
                 f"or change the annotation to '{inferred}'"
            if inferred != "None" else
            f"a plain '{annot_base}' can't be None — give it a real {annot_base}",
        ))

    # -- collection pass ---------------------------------------------------
    def collect(self, node):
        if not isinstance(node, Tree):
            return
        r = _rule(node)
        if r == "fn_def":
            name, _, ret = self._fn_parts(node.children)
            if ret is not None:
                self.fn_returns[name] = ret
        elif r == "async_stmt":
            tail = next((c for c in node.children
                         if isinstance(c, Tree) and _rule(c) == "async_fn_tail"), None)
            if tail is not None:
                name, _, ret = self._fn_parts(tail.children)
                if ret is not None:
                    self.fn_returns[name] = ret
        elif r == "class_def":
            ch = [c for c in node.children
                  if not (isinstance(c, Tree) and _rule(c) == "decorator")]
            self.classes.add(ch[0].value)
        elif r == "const_stmt":
            name = node.children[0].value
            if name in self.consts:
                self.issues.append(TypeIssue(
                    node.meta.line, node.meta.column,
                    f"'{name}' is already declared const at line {self.consts[name]}",
                    hint="a const is bound exactly once — pick a new name"))
            else:
                self.consts[name] = node.meta.line
        for c in node.children:
            self.collect(c)

    def scan_reassign(self, node):
        """Flag any statement that reassigns, rebinds, or aug-assigns a const —
        the guarantee that makes `const` more than a naming convention."""
        if not isinstance(node, Tree):
            return
        r = _rule(node)
        if r == "assign_stmt":
            for tl in node.children[:-1]:
                self._flag_const(self._single_name(tl), node)
        elif r == "aug_assign_stmt":
            # mutating an attr/index of a const object is fine (const binds the
            # NAME, not the object); only a bare-name aug-assign rebinds it.
            self._flag_const(self._bare_name(node.children[0]), node)
        elif r == "let_stmt":
            self._flag_const(self._single_name(node.children[0]), node, verb="rebind")
        for c in node.children:
            self.scan_reassign(c)

    def _flag_const(self, name, node, verb="reassign"):
        if name is not None and name in self.consts:
            self.issues.append(TypeIssue(
                node.meta.line, node.meta.column,
                f"cannot {verb} '{name}' — it is a const "
                f"(bound at line {self.consts[name]})",
                hint=f"use 'let {name}' instead of 'const' if it must change, "
                     f"or mutate in place (const binds the name, not the object)"))

    def _bare_name(self, node):
        if isinstance(node, Tree) and _rule(node) == "name":
            return node.children[0].value
        if isinstance(node, Tree) and _rule(node) == "postfix" and len(node.children) == 1:
            inner = node.children[0]
            if isinstance(inner, Tree) and _rule(inner) == "name":
                return inner.children[0].value
        return None

    def _fn_parts(self, children):
        ch = [c for c in children
              if not (isinstance(c, Tree) and _rule(c) == "decorator")]
        name = ch[0].value
        params = next((c for c in ch if isinstance(c, Tree) and _rule(c) == "param_list"), None)
        ret_type = next((c for c in ch if isinstance(c, Tree) and _rule(c) == "type"), None)
        ret = ret_type.children[0].value if ret_type is not None else None
        return name, params, ret

    def _param_types(self, param_list) -> dict:
        env = {}
        if param_list is None:
            return env
        for p in param_list.children:
            if not (isinstance(p, Tree) and _rule(p) == "param"):
                continue
            tnode = next((c for c in p.children[1:]
                          if isinstance(c, Tree) and _rule(c) == "type"), None)
            if tnode is not None:
                env[p.children[0].value] = tnode.children[0].value
        return env

    # -- checking walk -----------------------------------------------------
    def walk(self, node, env: dict, ret: str | None):
        for stmt in node.children:
            if not isinstance(stmt, Tree):
                continue
            r = _rule(stmt)
            if r == "simple_stmt":
                inner = next((c for c in stmt.children if isinstance(c, Tree)), None)
                if inner is not None:
                    self._simple(inner, env, ret)
            elif r == "fn_def":
                name, params, rtype = self._fn_parts(stmt.children)
                child = dict(env)
                child.update(self._param_types(params))
                suite = self._suite_of(stmt)
                if suite is not None:
                    self.walk(suite, child, rtype)
            elif r == "async_stmt":
                tail = next((c for c in stmt.children
                             if isinstance(c, Tree) and _rule(c) == "async_fn_tail"), None)
                if tail is not None:
                    name, params, rtype = self._fn_parts(tail.children)
                    child = dict(env)
                    child.update(self._param_types(params))
                    suite = self._suite_of(tail)
                    if suite is not None:
                        self.walk(suite, child, rtype)
                else:
                    self._descend(stmt, env, ret)
            elif r == "class_def":
                suite = self._suite_of(stmt)
                if suite is not None:
                    self.walk(suite, dict(env), None)  # method returns handled per-fn
            elif r == "return_stmt":
                if ret in ACCEPTS and stmt.children:
                    self._check_assign(ret, stmt.children[0], env,
                                       stmt.meta.line, stmt.meta.column, "this function's return")
            else:
                self._descend(stmt, env, ret)

    def _simple(self, inner, env, ret):
        r = _rule(inner)
        if r == "let_stmt":
            self._let(inner, env)
        elif r == "const_stmt":
            self._const(inner, env)
        elif r == "assign_stmt":
            self._assign(inner, env)
        elif r == "return_stmt":
            if ret in ACCEPTS and inner.children:
                self._check_assign(ret, inner.children[0], env,
                                   inner.meta.line, inner.meta.column, "this function's return")

    def _let(self, node, env):
        tl = node.children[0]
        type_node = node.children[1] if (len(node.children) == 3
                                         and isinstance(node.children[1], Tree)
                                         and _rule(node.children[1]) == "type") else None
        value = node.children[-1]
        name = self._single_name(tl)
        if type_node is not None and name is not None:
            annot = type_node.children[0].value
            self._check_assign(annot, value, env, node.meta.line, node.meta.column,
                               f"'{name}'")
            env[name] = annot                       # trust the declared type
        elif name is not None:
            env[name] = self.infer(value, env)      # remember what we inferred

    def _const(self, node, env):
        name = node.children[0].value               # NAME token
        type_node = node.children[1] if (len(node.children) == 3
                                         and isinstance(node.children[1], Tree)
                                         and _rule(node.children[1]) == "type") else None
        value = node.children[-1]
        if type_node is not None:
            annot = type_node.children[0].value
            self._check_assign(annot, value, env, node.meta.line, node.meta.column,
                               f"'{name}'")
            env[name] = annot
        else:
            env[name] = self.infer(value, env)

    def _assign(self, node, env):
        # target_list ("=" target_list)* "=" expr — update the type we track
        value = node.children[-1]
        inferred = self.infer(value, env)
        for tl in node.children[:-1]:
            name = self._single_name(tl)
            if name is not None:
                env[name] = inferred

    def _descend(self, node, env, ret):
        for c in node.children:
            if isinstance(c, Tree) and _rule(c) in (
                    "suite", "elif_clause", "else_clause", "except_clause",
                    "finally_clause", "match_case", "async_for_tail", "async_with_tail"):
                self.walk(c, env, ret)

    def _suite_of(self, node):
        return next((c for c in node.children
                     if isinstance(c, Tree) and _rule(c) == "suite"), None)

    def _single_name(self, target_list):
        """The bound name if this target is exactly one plain name, else None."""
        if _rule(target_list) != "target_list" or len(target_list.children) != 1:
            return None
        t = target_list.children[0]
        if isinstance(t, Tree) and _rule(t) == "name":
            return t.children[0].value
        if isinstance(t, Tree) and _rule(t) == "postfix" and len(t.children) == 1:
            inner = t.children[0]
            if isinstance(inner, Tree) and _rule(inner) == "name":
                return inner.children[0].value
        return None


def check_tree(tree, source: str) -> list[TypeIssue]:
    """All type issues in a parsed Viper program (empty list if clean)."""
    c = _Checker(source)
    c.collect(tree)              # fn returns, classes, const declarations
    c.scan_reassign(tree)        # const immutability
    c.walk(tree, env={}, ret=None)   # annotation / return type checks
    c.issues.sort(key=lambda i: (i.line, i.column))
    return c.issues


def check_source(source: str) -> list[TypeIssue]:
    """Parse then type-check. Returns [] if the source doesn't parse (parse
    errors are reported elsewhere)."""
    try:
        tree = parser.parse(source)
    except Exception:
        return []
    return check_tree(tree, source)


def raise_first(tree, source: str, filename: str) -> None:
    """Raise a ViperError for the first type issue, formatted like a parse
    error (caret block). No-op if the program type-checks."""
    issues = check_tree(tree, source)
    if not issues:
        return
    first = issues[0]
    raise ViperError(_caret_block(source, first.line, first.column, filename,
                                  first.message, first.hint or None))
