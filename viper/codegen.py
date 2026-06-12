"""Transpile a Viper parse tree into Python source.

Walks the lark Tree, emitting Python line-by-line and recording a line_map
(python_line -> viper_line) so runtime errors can point back at the .vp source.
"""
from lark import Tree, Token

from .errors import ViperError, format_parse_error
from .parser import parser
from .keywords import BUILTINS

# ---- footgun guard config ---------------------------------------------------
# Viper's stdlib prelude helpers live in BUILTINS for editor completion, but are
# plain namespace names users may freely shadow — keep them out of the guard set.
_PRELUDE_NAMES = {"pp", "read_file", "write_file", "clamp"}
_BUILTIN_NAMES = set(BUILTINS) - _PRELUDE_NAMES


def _rule(node) -> str:
    data = node.data
    return data.value if isinstance(data, Token) else data


def _peel(node):
    while isinstance(node, Tree) and _rule(node) in ("pipe_expr", "conditional") \
            and len(node.children) == 1:
        node = node.children[0]
    return node


class _Codegen:
    def __init__(self, source: str, filename: str):
        self.source = source
        self.filename = filename
        self.lines: list[str] = []
        self.line_map: dict[int, int] = {}
        self.needs_threading = False
        self._spawn_counter = 0
        self._let_names: set[str] = set()

    # -- emission helpers --------------------------------------------------
    def emit(self, text: str, indent: int, viper_line: int | None = None):
        self.lines.append("    " * indent + text)
        if viper_line is not None:
            self.line_map[len(self.lines)] = viper_line

    # -- top-level dispatch -----------------------------------------------
    def gen_suite(self, suite: Tree, indent: int):
        body = [c for c in suite.children if isinstance(c, Tree)]
        if not body:
            self.emit("pass", indent); return
        for stmt in body:
            self.gen_stmt(stmt, indent)

    def gen_stmt(self, node: Tree, indent: int):
        rule = _rule(node)
        if rule == "simple_stmt":
            inner = next(c for c in node.children if isinstance(c, Tree))
            self.gen_stmt(inner, indent); return
        handler = getattr(self, f"_stmt_{rule}", None)
        if handler is None:
            raise ViperError(f"internal: no codegen for statement {rule!r}")
        handler(node, indent)

    # -- imports -----------------------------------------------------------
    def _stmt_import_plain(self, node, indent):
        names = [".".join(t.value for t in dn.children) for dn in node.children]
        self.emit("import " + ", ".join(names), indent, node.meta.line)

    def _stmt_import_from(self, node, indent):
        module = ".".join(t.value for t in node.children[0].children)
        targets = node.children[1]
        if _rule(targets) == "import_star":
            self.emit(f"from {module} import *", indent, node.meta.line)
        else:
            names = ", ".join(t.value for t in targets.children)
            self.emit(f"from {module} import {names}", indent, node.meta.line)

    # -- let / assign / aug -----------------------------------------------
    def _stmt_let_stmt(self, node, indent):
        tl = node.children[0]
        type_node = None
        if len(node.children) == 3 and isinstance(node.children[1], Tree) \
                and _rule(node.children[1]) == "type":
            type_node = node.children[1]
        expr = node.children[-1]

        bound = self._collect_target_names(tl)
        for name in bound:
            if name in _BUILTIN_NAMES:
                raise ViperError(
                    f"'let {name}' shadows the builtin '{name}'.\n"
                    f"hint: pick another name (e.g. '{name}_' or 'my_{name}')."
                )
            self._let_names.add(name)

        target = self.gen_target_list(tl)
        if type_node is not None:
            if not (len(tl.children) == 1 and self._is_bare_name(tl.children[0])):
                raise ViperError(
                    "type annotation in 'let' is only allowed on a single name.\n"
                    "hint: drop the ': type' or split the binding."
                )
            self.emit(f"{target}: {self.gen_type(type_node)} = {self.gen_expr(expr)}",
                      indent, node.meta.line)
        else:
            self.emit(f"{target} = {self.gen_expr(expr)}", indent, node.meta.line)

    def _stmt_assign_stmt(self, node, indent):
        # children: target_list* "=" expr  (zero or more intermediate target_lists)
        targets = [self.gen_target_list(c) for c in node.children[:-1]]
        rhs = self.gen_expr(node.children[-1])
        self.emit(" = ".join(targets) + f" = {rhs}", indent, node.meta.line)

    def _stmt_aug_assign_stmt(self, node, indent):
        lhs = self.gen_expr(node.children[0])
        op = node.children[1].children[0].value
        rhs = self.gen_expr(node.children[2])
        self.emit(f"{lhs} {op} {rhs}", indent, node.meta.line)

    def _stmt_expr_stmt(self, node, indent):
        expr = node.children[0]
        self.emit(self.gen_expr(expr), indent, node.meta.line)

    # -- targets -----------------------------------------------------------
    def _is_bare_name(self, t):
        # ?target/?postfix inline to a bare `name` atom when there are no trailers,
        # so a single name can appear either directly or wrapped in a postfix.
        if isinstance(t, Tree) and _rule(t) == "name":
            return True
        if isinstance(t, Tree) and _rule(t) == "postfix" and len(t.children) == 1:
            inner = t.children[0]
            return isinstance(inner, Tree) and _rule(inner) == "name"
        return False

    def _collect_target_names(self, node) -> list[str]:
        out: list[str] = []
        def walk(n):
            if isinstance(n, Tree):
                r = _rule(n)
                if r == "name":
                    out.append(n.children[0].value); return
                for c in n.children:
                    walk(c)
        walk(node)
        return out

    def gen_target_list(self, node) -> str:
        if _rule(node) != "target_list":
            return self.gen_target(node)
        parts = [self.gen_target(c) for c in node.children]
        if len(parts) == 1:
            return parts[0]
        return ", ".join(parts)

    def gen_target(self, node) -> str:
        if isinstance(node, Token):
            return node.value
        r = _rule(node)
        if r == "star_target":
            return "*" + self.gen_target(node.children[0])
        # Strip parentheses from tuple targets: (a, b) = x  ->  a, b = x
        if r == "group":
            inner = node.children[0]
            # If inner is a target_list-like thing (tuple_literal), unpack it
            ir = _rule(inner)
            if ir == "tuple_literal":
                return ", ".join(self.gen_target(c) for c in inner.children)
            return self.gen_target(inner)
        if r == "tuple_literal":
            return ", ".join(self.gen_target(c) for c in node.children)
        # postfix — reuse expression generator
        return self.gen_expr(node)

    # -- simple stmts ------------------------------------------------------
    def _stmt_return_stmt(self, node, indent):
        if node.children:
            self.emit(f"return {self.gen_expr(node.children[0])}", indent, node.meta.line)
        else:
            self.emit("return", indent, node.meta.line)

    def _stmt_break_stmt(self, node, indent):    self.emit("break", indent, node.meta.line)
    def _stmt_continue_stmt(self, node, indent): self.emit("continue", indent, node.meta.line)
    def _stmt_pass_stmt(self, node, indent):     self.emit("pass", indent, node.meta.line)

    def _stmt_raise_stmt(self, node, indent):
        if not node.children:
            self.emit("raise", indent, node.meta.line); return
        if len(node.children) == 1:
            self.emit(f"raise {self.gen_expr(node.children[0])}", indent, node.meta.line)
        else:
            exc = self.gen_expr(node.children[0])
            cause = self.gen_expr(node.children[1])
            self.emit(f"raise {exc} from {cause}", indent, node.meta.line)

    def _stmt_del_stmt(self, node, indent):
        self.emit(f"del {self.gen_expr(node.children[0])}", indent, node.meta.line)

    def _stmt_assert_stmt(self, node, indent):
        if len(node.children) == 2:
            self.emit(f"assert {self.gen_expr(node.children[0])}, "
                      f"{self.gen_expr(node.children[1])}",
                      indent, node.meta.line)
        else:
            self.emit(f"assert {self.gen_expr(node.children[0])}",
                      indent, node.meta.line)

    def _stmt_global_stmt(self, node, indent):
        self.emit("global " + ", ".join(t.value for t in node.children),
                  indent, node.meta.line)

    def _stmt_nonlocal_stmt(self, node, indent):
        self.emit("nonlocal " + ", ".join(t.value for t in node.children),
                  indent, node.meta.line)

    # -- control flow ------------------------------------------------------
    def _stmt_if_stmt(self, node, indent):
        cond = node.children[0]
        suite = node.children[1]
        self.emit(f"if {self.gen_expr(cond)}:", indent, node.meta.line)
        self.gen_suite(suite, indent + 1)
        for clause in node.children[2:]:
            if _rule(clause) == "elif_clause":
                self.emit(f"elif {self.gen_expr(clause.children[0])}:",
                          indent, clause.meta.line)
                self.gen_suite(clause.children[1], indent + 1)
            elif _rule(clause) == "else_clause":
                self.emit("else:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)

    def _stmt_while_stmt(self, node, indent):
        self.emit(f"while {self.gen_expr(node.children[0])}:", indent, node.meta.line)
        self.gen_suite(node.children[1], indent + 1)
        for clause in node.children[2:]:
            if _rule(clause) == "else_clause":
                self.emit("else:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)

    def _stmt_for_stmt(self, node, indent):
        target = self.gen_target_list(node.children[0])
        iterable = self.gen_expr(node.children[1])
        self.emit(f"for {target} in {iterable}:", indent, node.meta.line)
        self.gen_suite(node.children[2], indent + 1)
        for clause in node.children[3:]:
            if _rule(clause) == "else_clause":
                self.emit("else:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)

    def _stmt_match_stmt(self, node, indent):
        subject = self.gen_expr(node.children[0])
        self.emit(f"match {subject}:", indent, node.meta.line)
        for case in node.children[1:]:
            if not (isinstance(case, Tree) and _rule(case) == "match_case"):
                continue
            kids = case.children
            pat = self.gen_pattern(kids[0])
            rest = kids[1:]
            guard = None
            suite = rest[-1]
            if len(rest) == 2:
                guard = self.gen_expr(rest[0])
            head = f"case {pat}" + (f" if {guard}" if guard else "") + ":"
            self.emit(head, indent + 1, case.meta.line)
            self.gen_suite(suite, indent + 2)

    # -- fn / class --------------------------------------------------------
    def _stmt_fn_def(self, node, indent):
        ch = list(node.children)
        decorators = []
        while ch and isinstance(ch[0], Tree) and _rule(ch[0]) == "decorator":
            decorators.append(ch.pop(0))
        for dec in decorators:
            self.emit(self._gen_decorator(dec), indent, dec.meta.line)
        name = ch[0].value
        params, suite, ret_type = "", None, None
        for child in ch[1:]:
            if isinstance(child, Tree) and _rule(child) == "param_list":
                params = self.gen_params(child)
            elif isinstance(child, Tree) and _rule(child) == "type":
                ret_type = self.gen_type(child)
            elif isinstance(child, Tree) and _rule(child) == "suite":
                suite = child
        arrow = f" -> {ret_type}" if ret_type else ""
        self.emit(f"def {name}({params}){arrow}:", indent, node.meta.line)
        self.gen_suite(suite, indent + 1)

    def _gen_decorator(self, node: Tree) -> str:
        parts = [".".join(t.value for t in node.children[0].children)]
        if len(node.children) > 1 and isinstance(node.children[1], Tree):
            parts.append(f"({self.gen_arglist(node.children[1])})")
        return "@" + "".join(parts)

    def _stmt_class_def(self, node, indent):
        ch = list(node.children)
        decorators = []
        while ch and isinstance(ch[0], Tree) and _rule(ch[0]) == "decorator":
            decorators.append(ch.pop(0))
        for dec in decorators:
            self.emit(self._gen_decorator(dec), indent, dec.meta.line)
        name = ch[0].value
        bases, suite = "", None
        for child in ch[1:]:
            if isinstance(child, Tree) and _rule(child) == "arg_list":
                bases = f"({self.gen_arglist(child)})"
            elif isinstance(child, Tree) and _rule(child) == "suite":
                suite = child
        self.emit(f"class {name}{bases}:", indent, node.meta.line)
        if suite: self.gen_suite(suite, indent + 1)
        else:     self.emit("pass", indent + 1)

    # -- try / spawn / with ------------------------------------------------
    def _stmt_try_stmt(self, node, indent):
        self.emit("try:", indent, node.meta.line)
        kids = list(node.children)
        self.gen_suite(kids[0], indent + 1)
        for clause in kids[1:]:
            r = _rule(clause)
            if r == "except_clause":
                self._gen_except_clause(clause, indent)
            elif r == "else_clause":
                self.emit("else:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)
            elif r == "finally_clause":
                self.emit("finally:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)

    def _gen_except_clause(self, node: Tree, indent: int):
        kids = list(node.children)
        suite = kids[-1]
        exc_kids = kids[:-1]
        if not exc_kids:
            raise ViperError(
                "bare 'except:' swallows every error (including KeyboardInterrupt).\n"
                "hint: write 'except Exception:' or name the exception you mean."
            )
        elif len(exc_kids) == 1:
            self.emit(f"except {self.gen_expr(exc_kids[0])}:", indent, node.meta.line)
        else:
            exc_type = self.gen_expr(exc_kids[0])
            alias = exc_kids[1].value
            self.emit(f"except {exc_type} as {alias}:", indent, node.meta.line)
        self.gen_suite(suite, indent + 1)

    def _stmt_spawn_stmt(self, node, indent):
        self.needs_threading = True
        self._spawn_counter += 1
        fname = f"__viper_spawn_{self._spawn_counter}"
        self.emit(f"def {fname}():", indent, node.meta.line)
        self.gen_suite(node.children[0], indent + 1)
        self.emit(f"__import__('threading').Thread(target={fname}, daemon=True).start()",
                  indent, node.meta.line)

    def _stmt_with_stmt(self, node, indent):
        items, suite = [], None
        for c in node.children:
            if isinstance(c, Tree) and _rule(c) == "with_item":
                ex = self.gen_expr(c.children[0])
                if len(c.children) == 2:
                    items.append(f"{ex} as {self.gen_target(c.children[1])}")
                else:
                    items.append(ex)
            elif isinstance(c, Tree) and _rule(c) == "suite":
                suite = c
        self.emit(f"with {', '.join(items)}:", indent, node.meta.line)
        self.gen_suite(suite, indent + 1)

    # -- params / types ----------------------------------------------------
    def gen_params(self, param_list: Tree) -> str:
        parts = []
        for p in param_list.children:
            if not (isinstance(p, Tree) and _rule(p) == "param"): continue
            name = p.children[0].value
            ptype = default = None
            for c in p.children[1:]:
                if isinstance(c, Tree) and _rule(c) == "type":
                    ptype = self.gen_type(c)
                else:
                    default = c
            piece = name
            if ptype: piece += f": {ptype}"
            if default is not None:
                self._check_mutable_default(name, default)
                piece += (f" = {self.gen_expr(default)}" if ptype
                          else f"={self.gen_expr(default)}")
            parts.append(piece)
        return ", ".join(parts)

    def _check_mutable_default(self, name, default):
        peeled = _peel(default)
        if isinstance(peeled, Tree) and _rule(peeled) in ("list_atom", "brace_atom"):
            inner = peeled.children[0] if peeled.children else None
            if inner is not None and isinstance(inner, Tree) and _rule(inner) in (
                    "list_items_body", "dict_items_body",
                    "set_items_body", "set_singleton_body"):
                kind = ("list" if _rule(inner) == "list_items_body"
                        else "dict" if _rule(inner) == "dict_items_body"
                        else "set")
                raise ViperError(
                    f"mutable default argument '{name}=<{kind}>' is a footgun in Viper.\n"
                    f"hint: use '{name}=None' and build the {kind} inside the function."
                )
            if inner is None and _rule(peeled) == "list_atom":
                raise ViperError(
                    f"mutable default argument '{name}=[]' is a footgun in Viper.\n"
                    f"hint: use '{name}=None' and build the list inside the function."
                )

    def gen_type(self, node: Tree) -> str:
        base = node.children[0].value
        args = [self.gen_type(c) for c in node.children[1:]
                if isinstance(c, Tree) and _rule(c) == "type"]
        return f"{base}[{', '.join(args)}]" if args else base

    # -- patterns ----------------------------------------------------------
    def gen_pattern(self, node: Tree) -> str:
        rule = _rule(node)
        if rule == "pattern":     return self.gen_pattern(node.children[0])
        if rule == "or_pattern":
            if len(node.children) == 1: return self.gen_pattern(node.children[0])
            return " | ".join(self.gen_pattern(c) for c in node.children)
        if rule == "as_pattern":
            inner = self.gen_pattern(node.children[0])
            return f"{inner} as {node.children[1].value}" if len(node.children) == 2 else inner
        if rule == "pat_capture":  return node.children[0].value
        if rule == "pat_number":   return node.children[0].value
        if rule == "pat_string":   return node.children[0].value
        if rule == "pat_true":     return "True"
        if rule == "pat_false":    return "False"
        if rule == "pat_none":     return "None"
        if rule == "pat_wildcard": return "_"
        if rule == "pat_group":    return self.gen_pattern(node.children[0])
        if rule == "pat_sequence":
            inner = ", ".join(self.gen_pattern(c) for c in node.children)
            return f"[{inner}]"
        if rule == "pat_tuple":
            inner = ", ".join(self.gen_pattern(c) for c in node.children)
            return f"({inner},)" if len(node.children) == 1 else f"({inner})"
        if rule == "pat_class":
            cls = node.children[0].value
            kws = []
            for kw in node.children[1:]:
                k = kw.children[0].value
                v = self.gen_pattern(kw.children[1])
                kws.append(f"{k}={v}")
            return f"{cls}({', '.join(kws)})"
        raise ViperError(f"internal: no codegen for pattern {rule!r}")

    # -- expressions -------------------------------------------------------
    def gen_expr(self, node) -> str:
        if isinstance(node, Token):
            return node.value
        rule = _rule(node)
        method = getattr(self, f"_expr_{rule}", None)
        if method is None:
            raise ViperError(f"internal: no codegen for expression {rule!r}")
        return method(node)

    # walrus
    def _expr_walrus(self, node):
        name = node.children[0].value
        rhs = self.gen_expr(node.children[2])
        return f"({name} := {rhs})"

    def _expr_walrus_group(self, node):
        return self._expr_walrus(node)

    # pipe + placeholder
    def _expr_pipe_expr(self, node):
        stages = [c for c in node.children if isinstance(c, Tree)]
        if len(stages) == 1:
            return self.gen_expr(stages[0])
        result = self.gen_expr(stages[0])
        for stage in stages[1:]:
            result = self._pipe_apply(stage, result)
        return result

    def _pipe_apply(self, stage, piped: str) -> str:
        """If stage is f(..., _, ...), substitute piped for _. Otherwise f(piped)."""
        peeled = _peel(stage)
        if isinstance(peeled, Tree) and _rule(peeled) == "postfix" \
                and len(peeled.children) >= 2 \
                and _rule(peeled.children[-1]) == "call_trailer":
            call = peeled.children[-1]
            if call.children:
                arg_list = call.children[0]
                if self._has_placeholder(arg_list):
                    # Always build head from all children except the last call_trailer
                    head = self.gen_expr(Tree("postfix", peeled.children[:-1], peeled.meta))
                    args = self._render_args_with_placeholder(arg_list, piped)
                    return f"{head}({args})"
        return f"({self.gen_expr(stage)})({piped})"

    def _has_placeholder(self, arg_list: Tree) -> bool:
        for arg in arg_list.children:
            if _rule(arg) == "posarg":
                if self._is_underscore(arg.children[0]):
                    return True
        return False

    def _is_underscore(self, node) -> bool:
        peeled = _peel(node)
        # bare name node (after ? transparent rules)
        if isinstance(peeled, Tree) and _rule(peeled) == "name":
            return peeled.children[0].value == "_"
        # postfix wrapping a name node
        if isinstance(peeled, Tree) and _rule(peeled) == "postfix" \
                and len(peeled.children) == 1:
            atom = peeled.children[0]
            if isinstance(atom, Tree) and _rule(atom) == "name":
                return atom.children[0].value == "_"
        return False

    def _render_args_with_placeholder(self, arg_list: Tree, piped: str) -> str:
        out = []
        for arg in arg_list.children:
            r = _rule(arg)
            if r == "posarg":
                e = arg.children[0]
                peeled = _peel(e)
                is_underscore = self._is_underscore(e)
                out.append(piped if is_underscore else self.gen_expr(e))
            elif r == "kwarg":
                out.append(f"{arg.children[0].value}={self.gen_expr(arg.children[1])}")
            elif r == "star_arg":
                out.append(f"*{self.gen_expr(arg.children[0])}")
            elif r == "double_star_arg":
                out.append(f"**{self.gen_expr(arg.children[0])}")
        return ", ".join(out)

    def _expr_conditional(self, node):
        if len(node.children) == 1: return self.gen_expr(node.children[0])
        body, cond, alt = node.children
        return f"({self.gen_expr(body)} if {self.gen_expr(cond)} else {self.gen_expr(alt)})"

    def _expr_or_expr(self, node):  return " or ".join(self.gen_expr(c) for c in node.children)
    def _expr_and_expr(self, node): return " and ".join(self.gen_expr(c) for c in node.children)
    def _expr_logical_not(self, node):
        return f"(not {self.gen_expr(node.children[0])})"

    def _expr_comparison(self, node):
        out = [self.gen_expr(node.children[0])]
        i = 1
        while i < len(node.children):
            op_node = node.children[i]
            op = " ".join(t.value for t in op_node.children)
            rhs = node.children[i + 1]
            lhs_node = node.children[i - 1] if i > 0 else None
            if op in ("==", "!=") and self._is_none_literal(rhs):
                arrow = "is" if op == "==" else "is not"
                raise ViperError(
                    f"compare against None with '{arrow}', not '{op}'.\n"
                    f"hint: write 'x {arrow} None'."
                )
            if lhs_node is not None and op in ("==", "!=") and self._is_none_literal(lhs_node):
                arrow = "is" if op == "==" else "is not"
                raise ViperError(
                    f"compare against None with '{arrow}', not '{op}'.\n"
                    f"hint: write 'x {arrow} None'."
                )
            out.append(op); out.append(self.gen_expr(rhs))
            i += 2
        return "(" + " ".join(out) + ")"

    def _is_none_literal(self, n):
        peeled = _peel(n)
        # Direct const_none (after transparent ? rules collapsed the tree)
        if isinstance(peeled, Tree) and _rule(peeled) == "const_none":
            return True
        # Wrapped in a single-child postfix
        return isinstance(peeled, Tree) and _rule(peeled) == "postfix" \
            and len(peeled.children) == 1 \
            and isinstance(peeled.children[0], Tree) \
            and _rule(peeled.children[0]) == "const_none"

    # bitwise + shift cascade
    def _binop(self, node, sep):
        if len(node.children) == 1:
            return self.gen_expr(node.children[0])
        parts = [self.gen_expr(node.children[0])]
        i = 1
        while i < len(node.children):
            c = node.children[i]
            if isinstance(c, Tree) and _rule(c) == "shift_op":
                op = c.children[0].value
                parts.extend([op, self.gen_expr(node.children[i + 1])])
                i += 2
            else:
                parts.extend([sep, self.gen_expr(c)])
                i += 1
        return "(" + " ".join(parts) + ")"

    def _expr_bitor_expr(self, node):  return self._binop(node, "|")
    def _expr_bitxor_expr(self, node): return self._binop(node, "^")
    def _expr_bitand_expr(self, node): return self._binop(node, "&")
    def _expr_shift_expr(self, node):  return self._binop(node, "")

    def _expr_arith(self, node):
        parts = [self.gen_expr(node.children[0])]
        i = 1
        while i < len(node.children):
            op = node.children[i].children[0].value
            parts.extend([op, self.gen_expr(node.children[i + 1])])
            i += 2
        return "(" + " ".join(parts) + ")"

    _expr_term = _expr_arith

    def _expr_unary(self, node):
        op = node.children[0].children[0].value
        return f"({op}{self.gen_expr(node.children[1])})"

    def _expr_power(self, node):
        if len(node.children) == 1: return self.gen_expr(node.children[0])
        return f"({self.gen_expr(node.children[0])} ** {self.gen_expr(node.children[1])})"

    def _expr_postfix(self, node):
        result = self.gen_expr(node.children[0])
        for tr in node.children[1:]:
            r = _rule(tr)
            if r == "call_trailer":
                args = self.gen_arglist(tr.children[0]) if tr.children else ""
                result = f"{result}({args})"
            elif r == "index_trailer":
                result = f"{result}[{self.gen_expr(tr.children[0])}]"
            elif r == "slice_trailer":
                result = f"{result}[{self._gen_slice_part(tr.children[0])}]"
            elif r == "attr_trailer":
                result = f"{result}.{tr.children[0].value}"
            else:
                raise ViperError(f"internal: no codegen for trailer {r!r}")
        return result

    def _gen_slice_part(self, node: Tree) -> str:
        # node is slice_part: expr? COLON expr? (COLON expr?)?
        # children are a mix of Tree (expr) and Token (COLON)
        parts = []
        for c in node.children:
            if isinstance(c, Token):        # COLON terminal
                parts.append(":")
            elif isinstance(c, Tree):
                parts.append(self.gen_expr(c))
        return "".join(parts)

    def gen_arglist(self, node) -> str:
        out = []
        for arg in node.children:
            r = _rule(arg)
            if r == "kwarg":
                out.append(f"{arg.children[0].value}={self.gen_expr(arg.children[1])}")
            elif r == "star_arg":
                out.append(f"*{self.gen_expr(arg.children[0])}")
            elif r == "double_star_arg":
                out.append(f"**{self.gen_expr(arg.children[0])}")
            else:
                out.append(self.gen_expr(arg.children[0]))
        return ", ".join(out)

    # atoms ---------------------------------------------------------------
    def _expr_number(self, n):     return n.children[0].value
    def _expr_string(self, n):     return n.children[0].value
    def _expr_fstring(self, n):    return n.children[0].value
    def _expr_name(self, n):       return n.children[0].value
    def _expr_const_true(self, n): return "True"
    def _expr_const_false(self, n):return "False"
    def _expr_const_none(self, n): return "None"

    def _expr_lambda_expr(self, n):
        params = ""; body = None
        for c in n.children:
            if isinstance(c, Tree) and _rule(c) == "param_list":
                params = self.gen_params(c)
            else:
                body = c
        return f"(lambda {params}: {self.gen_expr(body)})"

    def _expr_group(self, n):        return f"({self.gen_expr(n.children[0])})"
    def _expr_empty_tuple(self, n):  return "()"
    def _expr_tuple_literal(self, n):
        inner = ", ".join(self.gen_expr(c) for c in n.children)
        return f"({inner})" if len(n.children) > 1 else f"({inner},)"

    def _expr_list_atom(self, n):
        if not n.children: return "[]"
        body = n.children[0]
        r = _rule(body)
        if r == "list_items_body":
            return "[" + ", ".join(self.gen_expr(c) for c in body.children) + "]"
        if r == "list_comp_body":
            return "[" + self._render_comp_inner(body) + "]"
        raise ViperError(f"internal: list body {r!r}")

    def _expr_brace_atom(self, n):
        if not n.children: return "{}"
        body = n.children[0]
        r = _rule(body)
        if r == "dict_items_body":
            parts = []
            for kv in body.children:
                parts.append(f"{self.gen_expr(kv.children[0])}: {self.gen_expr(kv.children[1])}")
            return "{" + ", ".join(parts) + "}"
        if r == "set_items_body":
            return "{" + ", ".join(self.gen_expr(c) for c in body.children) + "}"
        if r == "set_singleton_body":
            return "{" + self.gen_expr(body.children[0]) + "}"
        if r == "dict_comp_body":
            kv = body.children[0]
            head = f"{self.gen_expr(kv.children[0])}: {self.gen_expr(kv.children[1])}"
            tail = self._render_comp_tail(body, skip_first=True)
            return "{" + head + " " + tail + "}"
        if r == "set_comp_body":
            return "{" + self._render_comp_inner(body) + "}"
        raise ViperError(f"internal: brace body {r!r}")

    def _render_comp_inner(self, body) -> str:
        head = self.gen_expr(body.children[0])
        tail = self._render_comp_tail(body, skip_first=True)
        return head + " " + tail

    def _render_comp_tail(self, body, skip_first: bool) -> str:
        idx = 1 if skip_first else 0
        target = self.gen_target_list(body.children[idx])
        iterable = self.gen_expr(body.children[idx + 1])
        ifs = []
        for c in body.children[idx + 2:]:
            if isinstance(c, Tree) and _rule(c) == "comp_if":
                ifs.append("if " + self.gen_expr(c.children[0]))
        return f"for {target} in {iterable}" + (" " + " ".join(ifs) if ifs else "")

    def _expr_generator_exp(self, n):
        head = self.gen_expr(n.children[0])
        clauses = n.children[1]
        parts = [head]
        for cf in clauses.children:
            target = self.gen_target_list(cf.children[0])
            iterable = self.gen_expr(cf.children[1])
            ifs = []
            for c in cf.children[2:]:
                if isinstance(c, Tree) and _rule(c) == "comp_if":
                    ifs.append("if " + self.gen_expr(c.children[0]))
            parts.append(f"for {target} in {iterable}")
            parts.extend(ifs)
        return "(" + " ".join(parts) + ")"

    def _guard_none_compare(self, node, line):
        return


def transpile(source: str, filename: str = "<viper>") -> tuple[str, dict]:
    try:
        tree = parser.parse(source)
    except Exception as e:
        raise ViperError(format_parse_error(e, source, filename)) from None
    cg = _Codegen(source, filename)
    for stmt in [c for c in tree.children if isinstance(c, Tree)]:
        cg.gen_stmt(stmt, 0)
    return "\n".join(cg.lines) + "\n", cg.line_map
