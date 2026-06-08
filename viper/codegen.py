"""Transpile a Viper parse tree into Python source.

We walk the lark Tree directly, emitting Python line-by-line while recording a
line_map (python_line -> viper_line) so runtime errors can point back at the
original .vp source.
"""
from lark import Tree, Token

from .errors import ViperError, format_parse_error
from .parser import parser


def _rule(node) -> str:
    """The rule/alias name of a Tree node."""
    data = node.data
    return data.value if isinstance(data, Token) else data


def _peel(node):
    """Unwrap single-child collapsible wrappers (pipe_expr/conditional)."""
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

    # -- statements --------------------------------------------------------
    def gen_suite(self, suite: Tree, indent: int):
        body = [c for c in suite.children if isinstance(c, Tree)]
        if not body:
            self.emit("pass", indent)
            return
        for stmt in body:
            self.gen_stmt(stmt, indent)

    def gen_stmt(self, node: Tree, indent: int):
        rule = _rule(node)
        if rule == "simple_stmt":
            inner = next(c for c in node.children if isinstance(c, Tree))
            self.gen_stmt(inner, indent)
            return
        handler = getattr(self, f"_stmt_{rule}", None)
        if handler is None:
            raise ViperError(f"internal: no codegen for statement {rule!r}")
        handler(node, indent)

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

    def _stmt_let_stmt(self, node, indent):
        name = node.children[0].value
        self._let_names.add(name)
        expr = node.children[-1]
        self.emit(f"{name} = {self.gen_expr(expr)}", indent, node.meta.line)

    def _stmt_assign_stmt(self, node, indent):
        name = node.children[0].value
        expr = node.children[1]
        self.emit(f"{name} = {self.gen_expr(expr)}", indent, node.meta.line)

    def _stmt_aug_assign_stmt(self, node, indent):
        name = node.children[0].value
        op_node = node.children[1]
        op = op_node.children[0].value
        expr = node.children[2]
        self.emit(f"{name} {op} {self.gen_expr(expr)}", indent, node.meta.line)

    def _stmt_expr_stmt(self, node, indent):
        self.emit(self.gen_expr(node.children[0]), indent, node.meta.line)

    def _stmt_return_stmt(self, node, indent):
        if node.children:
            self.emit(f"return {self.gen_expr(node.children[0])}", indent, node.meta.line)
        else:
            self.emit("return", indent, node.meta.line)

    def _stmt_break_stmt(self, node, indent):
        self.emit("break", indent, node.meta.line)

    def _stmt_continue_stmt(self, node, indent):
        self.emit("continue", indent, node.meta.line)

    def _stmt_pass_stmt(self, node, indent):
        self.emit("pass", indent, node.meta.line)

    def _stmt_raise_stmt(self, node, indent):
        if node.children:
            self.emit(f"raise {self.gen_expr(node.children[0])}", indent, node.meta.line)
        else:
            self.emit("raise", indent, node.meta.line)

    def _stmt_del_stmt(self, node, indent):
        self.emit(f"del {self.gen_expr(node.children[0])}", indent, node.meta.line)

    def _stmt_if_stmt(self, node, indent):
        cond = node.children[0]
        suite = node.children[1]
        self.emit(f"if {self.gen_expr(cond)}:", indent, node.meta.line)
        self.gen_suite(suite, indent + 1)
        for clause in node.children[2:]:
            if _rule(clause) == "elif_clause":
                self.emit(f"elif {self.gen_expr(clause.children[0])}:", indent,
                          clause.meta.line)
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
        target = self.gen_pattern(node.children[0])
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
            children = case.children
            pat = self.gen_pattern(children[0])
            rest = children[1:]
            guard = None
            suite = rest[-1]
            if len(rest) == 2:
                guard = self.gen_expr(rest[0])
            head = f"case {pat}" + (f" if {guard}" if guard else "") + ":"
            self.emit(head, indent + 1, case.meta.line)
            self.gen_suite(suite, indent + 2)

    def _stmt_fn_def(self, node, indent):
        children = list(node.children)
        # Collect decorators
        decorators = []
        while children and isinstance(children[0], Tree) and _rule(children[0]) == "decorator":
            decorators.append(children.pop(0))
        for dec in decorators:
            self.emit(self._gen_decorator(dec), indent, dec.meta.line)

        name = children[0].value
        params, suite, ret_type = "", None, None
        for child in children[1:]:
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
            arg_list = node.children[1]
            parts.append(f"({self.gen_arglist(arg_list)})")
        return "@" + "".join(parts)

    def _stmt_class_def(self, node, indent):
        children = list(node.children)
        decorators = []
        while children and isinstance(children[0], Tree) and _rule(children[0]) == "decorator":
            decorators.append(children.pop(0))
        for dec in decorators:
            self.emit(self._gen_decorator(dec), indent, dec.meta.line)

        name = children[0].value
        bases = ""
        suite = None
        for child in children[1:]:
            if isinstance(child, Tree) and _rule(child) == "arg_list":
                bases = f"({self.gen_arglist(child)})"
            elif isinstance(child, Tree) and _rule(child) == "suite":
                suite = child
        self.emit(f"class {name}{bases}:", indent, node.meta.line)
        if suite:
            self.gen_suite(suite, indent + 1)
        else:
            self.emit("pass", indent + 1)

    def _stmt_try_stmt(self, node, indent):
        self.emit("try:", indent, node.meta.line)
        children = list(node.children)
        # First child is always the try suite
        self.gen_suite(children[0], indent + 1)
        for clause in children[1:]:
            rule = _rule(clause)
            if rule == "except_clause":
                self._gen_except_clause(clause, indent)
            elif rule == "else_clause":
                self.emit("else:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)
            elif rule == "finally_clause":
                self.emit("finally:", indent, clause.meta.line)
                self.gen_suite(clause.children[0], indent + 1)

    def _gen_except_clause(self, node: Tree, indent: int):
        children = list(node.children)
        suite = children[-1]
        exc_children = children[:-1]
        if not exc_children:
            self.emit("except:", indent, node.meta.line)
        elif len(exc_children) == 1:
            exc_type = self.gen_expr(exc_children[0])
            self.emit(f"except {exc_type}:", indent, node.meta.line)
        else:
            exc_type = self.gen_expr(exc_children[0])
            alias = exc_children[1].value
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

    # -- params / types ----------------------------------------------------
    def gen_params(self, param_list: Tree) -> str:
        parts = []
        for param in param_list.children:
            if not (isinstance(param, Tree) and _rule(param) == "param"):
                continue
            name = param.children[0].value
            ptype = default = None
            for c in param.children[1:]:
                if isinstance(c, Tree) and _rule(c) == "type":
                    ptype = self.gen_type(c)
                else:
                    default = c
            piece = name
            if ptype:
                piece += f": {ptype}"
            if default is not None:
                self._check_mutable_default(name, default)
                piece += (f" = {self.gen_expr(default)}" if ptype
                          else f"={self.gen_expr(default)}")
            parts.append(piece)
        return ", ".join(parts)

    def _check_mutable_default(self, name, default):
        peeled = _peel(default)
        if isinstance(peeled, Tree) and _rule(peeled) in ("list_literal", "dict_literal",
                                                           "set_literal"):
            kind = _rule(peeled).replace("_literal", "")
            raise ViperError(
                f"mutable default argument '{name}=<{kind}>' is a footgun in Viper.\n"
                f"hint: use '{name}=None' and create the {kind} inside the function."
            )

    def gen_type(self, node: Tree) -> str:
        base = node.children[0].value
        args = [self.gen_type(c) for c in node.children[1:]
                if isinstance(c, Tree) and _rule(c) == "type"]
        return f"{base}[{', '.join(args)}]" if args else base

    # -- patterns ----------------------------------------------------------
    def gen_pattern(self, node: Tree) -> str:
        rule = _rule(node)
        if rule == "pattern":
            return self.gen_pattern(node.children[0])
        if rule == "or_pattern":
            if len(node.children) == 1:
                return self.gen_pattern(node.children[0])
            return " | ".join(self.gen_pattern(c) for c in node.children)
        if rule == "as_pattern":
            inner = self.gen_pattern(node.children[0])
            if len(node.children) == 2:
                return f"{inner} as {node.children[1].value}"
            return inner
        if rule == "pat_capture":
            return node.children[0].value
        if rule == "pat_number":
            return node.children[0].value
        if rule == "pat_string":
            return node.children[0].value
        if rule == "pat_true":
            return "True"
        if rule == "pat_false":
            return "False"
        if rule == "pat_none":
            return "None"
        if rule == "pat_wildcard":
            return "_"
        if rule == "pat_group":
            return self.gen_pattern(node.children[0])
        if rule == "pat_sequence":
            inner = ", ".join(self.gen_pattern(c) for c in node.children)
            return f"[{inner}]"
        if rule == "pat_tuple":
            inner = ", ".join(self.gen_pattern(c) for c in node.children)
            return f"({inner},)" if len(node.children) == 1 else f"({inner})"
        if rule == "pat_class":
            cls_name = node.children[0].value
            kw_pats = []
            for kw in node.children[1:]:
                k = kw.children[0].value
                v = self.gen_pattern(kw.children[1])
                kw_pats.append(f"{k}={v}")
            return f"{cls_name}({', '.join(kw_pats)})"
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

    def _expr_conditional(self, node):
        if len(node.children) == 1:
            return self.gen_expr(node.children[0])
        value, cond, alt = node.children
        return (f"({self.gen_expr(value)} if {self.gen_expr(cond)} "
                f"else {self.gen_expr(alt)})")

    def _expr_pipe_expr(self, node):
        if len(node.children) == 1:
            return self.gen_expr(node.children[0])
        result = self.gen_expr(node.children[0])
        for fn in node.children[1:]:
            result = f"{self.gen_expr(fn)}({result})"
        return result

    def _expr_or_expr(self, node):
        return " or ".join(self.gen_expr(c) for c in node.children)

    def _expr_and_expr(self, node):
        return " and ".join(self.gen_expr(c) for c in node.children)

    def _expr_logical_not(self, node):
        return f"not {self.gen_expr(node.children[0])}"

    def _expr_comparison(self, node):
        out = []
        for c in node.children:
            if isinstance(c, Tree) and _rule(c) == "comp_op":
                out.append(" ".join(t.value for t in c.children))
            else:
                out.append(self.gen_expr(c))
        return " ".join(out)

    def _binop(self, node):
        out = []
        for c in node.children:
            if isinstance(c, Tree) and _rule(c) in ("add_op", "mul_op", "unary_op"):
                out.append(c.children[0].value)
            else:
                out.append(self.gen_expr(c))
        return " ".join(out)

    _expr_arith = _binop
    _expr_term = _binop

    def _expr_unary(self, node):
        op = node.children[0].children[0].value
        return f"{op}{self.gen_expr(node.children[1])}"

    def _expr_power(self, node):
        base = self.gen_expr(node.children[0])
        return f"{base} ** {self.gen_expr(node.children[1])}"

    def _expr_postfix(self, node):
        result = self.gen_expr(node.children[0])
        for trailer in node.children[1:]:
            rule = _rule(trailer)
            if rule == "call_trailer":
                args = ""
                if trailer.children:
                    args = self.gen_arglist(trailer.children[0])
                result = f"{result}({args})"
            elif rule == "index_trailer":
                slice_node = trailer.children[0]
                result = f"{result}[{self.gen_slice(slice_node)}]"
            elif rule == "attr_trailer":
                result = f"{result}.{trailer.children[0].value}"
        return result

    def gen_slice(self, node: Tree) -> str:
        rule = _rule(node)
        if rule == "index_expr":
            return self.gen_expr(node.children[0])
        # slice: expr (":" expr? (":" expr?)?)?
        parts = []
        for c in node.children:
            if isinstance(c, Tree):
                parts.append(self.gen_expr(c))
            elif isinstance(c, Token) and c.value == ":":
                parts.append(":")
        return "".join(parts)

    def gen_arglist(self, arg_list: Tree) -> str:
        parts = []
        for arg in arg_list.children:
            rule = _rule(arg)
            if rule == "kwarg":
                key = arg.children[0].value
                parts.append(f"{key}={self.gen_expr(arg.children[1])}")
            elif rule == "star_arg":
                parts.append(f"*{self.gen_expr(arg.children[0])}")
            elif rule == "double_star_arg":
                parts.append(f"**{self.gen_expr(arg.children[0])}")
            else:  # posarg
                parts.append(self.gen_expr(arg.children[0]))
        return ", ".join(parts)

    def _expr_lambda_expr(self, node):
        params, body = "", node.children[-1]
        if isinstance(node.children[0], Tree) and _rule(node.children[0]) == "param_list":
            params = self.gen_params(node.children[0])
        return f"(lambda {params}: {self.gen_expr(body)})"

    def _expr_group(self, node):
        return f"({self.gen_expr(node.children[0])})"

    def _expr_tuple_literal(self, node):
        items = ", ".join(self.gen_expr(c) for c in node.children)
        return f"({items},)" if len(node.children) == 1 else f"({items})"

    def _expr_empty_tuple(self, node):
        return "()"

    def _expr_list_literal(self, node):
        if not node.children:
            return "[]"
        items = self.gen_items(node.children[0])
        return f"[{items}]"

    def _expr_set_literal(self, node):
        if not node.children:
            return "set()"
        items_node = node.children[0]
        items = ", ".join(self.gen_expr(c) for c in items_node.children)
        return "{" + items + "}"

    def _expr_list_comp(self, node):
        expr = self.gen_expr(node.children[0])
        pattern = self.gen_pattern(node.children[1])
        iterable = self.gen_expr(node.children[2])
        if len(node.children) == 4:
            cond = self.gen_expr(node.children[3])
            return f"[{expr} for {pattern} in {iterable} if {cond}]"
        return f"[{expr} for {pattern} in {iterable}]"

    def _expr_dict_literal(self, node):
        if not node.children:
            return "{}"
        pairs = node.children[0]
        out = []
        for kv in pairs.children:
            k = self.gen_expr(kv.children[0])
            v = self.gen_expr(kv.children[1])
            out.append(f"{k}: {v}")
        return "{" + ", ".join(out) + "}"

    def gen_items(self, items: Tree) -> str:
        return ", ".join(self.gen_expr(c) for c in items.children)

    def _expr_name(self, node):
        return node.children[0].value

    def _expr_number(self, node):
        return node.children[0].value

    def _expr_string(self, node):
        return node.children[0].value

    def _expr_fstring(self, node):
        # Pass f-strings through verbatim — they are valid Python
        return node.children[0].value

    def _expr_const_true(self, node):
        return "True"

    def _expr_const_false(self, node):
        return "False"

    def _expr_const_none(self, node):
        return "None"


def transpile(source: str, filename: str = "<viper>") -> tuple[str, dict]:
    """Viper source -> (python_source, line_map). Raises ViperError on failure."""
    from lark.exceptions import UnexpectedInput

    try:
        tree = parser.parse(source)
    except UnexpectedInput as e:
        raise ViperError(format_parse_error(e, source, filename)) from None

    cg = _Codegen(source, filename)
    for stmt in tree.children:
        if isinstance(stmt, Tree):
            cg.gen_stmt(stmt, 0)

    header = []
    if cg.needs_threading:
        header.append("import threading")
    body = "\n".join(cg.lines)
    if header:
        offset = len(header)
        cg.line_map = {k + offset: v for k, v in cg.line_map.items()}
        body = "\n".join(header) + "\n" + body
    return body + ("\n" if body else ""), cg.line_map
