from lark import Lark
from lark.indenter import Indenter

VIPER_GRAMMAR = r"""
    start: (_NL | stmt)*

    ?stmt: simple_stmt
         | compound_stmt

    simple_stmt: small_stmt _NL
    ?small_stmt: import_stmt
               | let_stmt
               | const_stmt
               | assign_stmt
               | aug_assign_stmt
               | return_stmt
               | break_stmt
               | continue_stmt
               | pass_stmt
               | raise_stmt
               | del_stmt
               | assert_stmt
               | global_stmt
               | nonlocal_stmt
               | yield_stmt
               | expr_stmt

    ?compound_stmt: if_stmt
                  | while_stmt
                  | for_stmt
                  | match_stmt
                  | fn_def
                  | class_def
                  | try_stmt
                  | spawn_stmt
                  | with_stmt
                  | async_stmt

    import_stmt: "import" import_name ("," import_name)*        -> import_plain
               | "from" dotted_name "import" import_targets      -> import_from
    import_name: dotted_name ("as" NAME)?
    import_targets: "*"                                          -> import_star
                  | import_target ("," import_target)*
    import_target: NAME ("as" NAME)?
    dotted_name: NAME ("." NAME)*

    // --- assignment / let / const / aug ------------------------------------
    let_stmt: "let" target_list (":" type)? "=" expr
    const_stmt: "const" NAME (":" type)? "=" expr
    assign_stmt: target_list ("=" target_list)* "=" expr
    aug_assign_stmt: postfix aug_op expr
    !aug_op: "+=" | "-=" | "*=" | "/=" | "//=" | "%=" | "**="
    expr_stmt: expr

    target_list: target ("," target)* ","?
    ?target: star_target | postfix
    star_target: "*" target

    return_stmt: "return" expr?
    break_stmt: "break"
    continue_stmt: "continue"
    pass_stmt: "pass"
    raise_stmt: "raise" (expr ("from" expr)?)?
    del_stmt: "del" expr
    assert_stmt: "assert" expr ("," expr)?
    global_stmt: "global" NAME ("," NAME)*
    nonlocal_stmt: "nonlocal" NAME ("," NAME)*

    if_stmt: "if" namedexpr ":" suite elif_clause* else_clause?
    elif_clause: "elif" namedexpr ":" suite
    else_clause: "else" ":" suite
    while_stmt: "while" namedexpr ":" suite else_clause?
    for_stmt: "for" target_list "in" expr ":" suite else_clause?
    match_stmt: "match" expr ":" _NL INDENT match_case+ DEDENT
    match_case: "case" pattern ("if" expr)? ":" suite

    fn_def: decorator* "fn" NAME "(" param_list? ")" ("->" type)? ":" suite
    class_def: decorator* "class" NAME ("(" arg_list? ")")? ":" suite
    try_stmt: "try" ":" suite except_clause+ else_clause? finally_clause?
            | "try" ":" suite finally_clause
    except_clause: "except" (expr ("as" NAME)?)? ":" suite
    finally_clause: "finally" ":" suite
    spawn_stmt: "spawn" ":" suite

    with_stmt: "with" with_item ("," with_item)* ":" suite
    with_item: expr ("as" target)?

    yield_stmt: "yield" "from" expr                      -> yield_from_stmt
              | "yield" expr?

    async_stmt: decorator* "async" async_tail
    async_tail: "fn" NAME "(" param_list? ")" ("->" type)? ":" suite  -> async_fn_tail
              | "for" target_list "in" expr ":" suite else_clause?    -> async_for_tail
              | "with" with_item ("," with_item)* ":" suite           -> async_with_tail

    decorator: "@" dotted_name ("(" arg_list? ")")? _NL

    param_list: param ("," param)* ("," "...")?
    param: NAME (":" type)? ("=" expr)?

    suite: simple_stmt | _NL INDENT stmt+ DEDENT

    // --- expressions: walrus -> pipe -> ternary -> or/and -> not -> cmp ----
    // --- -> bitor -> bitxor -> bitand -> shift -> arith -> term -> factor --
    ?namedexpr: NAME WALRUS expr                         -> walrus
              | expr
    ?expr: pipe_expr
    pipe_expr: ternary (PIPE_FORWARD ternary)*
    ?ternary: or_expr ("if" or_expr "else" or_expr)?    -> conditional
    ?or_expr: and_expr ("or" and_expr)*
    ?and_expr: not_expr ("and" not_expr)*
    ?not_expr: "not" not_expr                            -> logical_not
             | comparison
    ?comparison: bitor_expr (comp_op bitor_expr)*
    !comp_op: "<" | "<=" | ">" | ">=" | "==" | "!=" | "is" | "is" "not" | "in" | "not" "in"

    ?bitor_expr:  bitxor_expr (_PIPE_OP bitxor_expr)*
    ?bitxor_expr: bitand_expr (_CARET    bitand_expr)*
    ?bitand_expr: shift_expr  (_AMP      shift_expr)*
    ?shift_expr:  arith       (shift_op  arith)*
    !shift_op: "<<" | ">>"

    ?arith: term (add_op term)*
    !add_op: "+" | "-"
    ?term: factor (mul_op factor)*
    !mul_op: "*" | "/" | "//" | "%"
    ?factor: unary_op factor                             -> unary
           | "await" factor                              -> await_expr
           | power
    !unary_op: "+" | "-" | "~"
    ?power: postfix ("**" factor)?

    ?postfix: atom trailer*
    trailer: "(" arg_list? ")"                           -> call_trailer
           | "[" expr "]"                                -> index_trailer
           | "[" slice_part "]"                          -> slice_trailer
           | "." NAME                                    -> attr_trailer

    // slice_part: always has at least one COLON so it's distinct from index_trailer
    slice_part: expr? COLON expr? (COLON expr?)?
    COLON: ":"

    ?atom: NUMBER                                        -> number
         | STRING                                        -> string
         | FSTRING                                       -> fstring
         | NAME                                          -> name
         | "True"                                        -> const_true
         | "False"                                       -> const_false
         | "None"                                        -> const_none
         | "fn" "(" param_list? ")" "->" expr            -> lambda_expr
         | "(" NAME WALRUS expr ")"                      -> walrus_group
         | "(" expr ")"                                  -> group
         | "(" expr ("," expr)+ ","? ")"                 -> tuple_literal
         | "(" expr comp_clauses ")"                     -> generator_exp
         | "(" ")"                                       -> empty_tuple
         | "[" list_body? "]"                            -> list_atom
         | "{" brace_body? "}"                           -> brace_atom

    // factored bodies so dict/set/comp disambiguate on a single lookahead
    list_body: expr "for" target_list "in" or_expr comp_if*  -> list_comp_body
             | expr ("," expr)* ","?                         -> list_items_body
    brace_body: key_value "for" target_list "in" or_expr comp_if*  -> dict_comp_body
              | key_value ("," key_value)* ","?                     -> dict_items_body
              | expr "for" target_list "in" or_expr comp_if*        -> set_comp_body
              | expr ("," expr)+ ","?                               -> set_items_body
              | expr                                                -> set_singleton_body

    comp_clauses: comp_for+
    comp_for: "for" target_list "in" or_expr comp_if*
    comp_if: "if" or_expr

    key_value: expr ":" expr
    arg_list: argument ("," argument)* ","?
    argument: NAME "=" expr                              -> kwarg
            | "*" expr                                   -> star_arg
            | "**" expr                                  -> double_star_arg
            | expr                                       -> posarg

    pattern: or_pattern
    or_pattern: as_pattern ("|" as_pattern)*
    as_pattern: inner_pattern ("as" NAME)?
    ?inner_pattern: NAME                                 -> pat_capture
                  | NUMBER                               -> pat_number
                  | STRING                               -> pat_string
                  | "True"                               -> pat_true
                  | "False"                              -> pat_false
                  | "None"                               -> pat_none
                  | "_"                                  -> pat_wildcard
                  | "(" inner_pattern ")"                -> pat_group
                  | "[" (inner_pattern ("," inner_pattern)*)? "]" -> pat_sequence
                  | "(" (inner_pattern ("," inner_pattern)+ ","?) ")" -> pat_tuple
                  | NAME "(" (kw_pattern ("," kw_pattern)*)? ")"     -> pat_class
    kw_pattern: NAME "=" inner_pattern

    type: NAME ("[" type ("," type)* "]")?

    // --- terminals — priorities matter -------------------------------------
    PIPE_FORWARD.2: "|>"
    WALRUS.2:       ":="
    _PIPE_OP:       "|"
    _CARET:         "^"
    _AMP:           "&"

    FSTRING: /f"[^"\\]*(?:\\.[^"\\]*)*"/
           | /f'[^'\\]*(?:\\.[^'\\]*)*'/
    // Hex / octal / binary / float / int — hex&friends first so 0x0A wins.
    // Underscores allowed as digit separators, like Python (1_000_000).
    NUMBER: /0[xX][0-9a-fA-F](_?[0-9a-fA-F])*|0[oO][0-7](_?[0-7])*|0[bB][01](_?[01])*|((\d(_?\d)*\.(\d(_?\d)*)?|\.\d(_?\d)*|\d(_?\d)*)([eE][+-]?\d(_?\d)*)?[jJ]?)/
    // Strings: double OR single quoted, like Python. f-strings handled above.
    // Optional prefixes: r (raw), b (bytes), and rb/br combos — pass straight
    // through to Python, so b"\x00" and r"\d+" mean exactly what they do there.
    STRING: /([rR]|[bB]|[rR][bB]|[bB][rR])?"[^"\\]*(?:\\.[^"\\]*)*"/
          | /([rR]|[bB]|[rR][bB]|[bB][rR])?'[^'\\]*(?:\\.[^'\\]*)*'/
    %import common.CNAME -> NAME
    %import common.WS_INLINE
    %ignore WS_INLINE
    %ignore /#[^\n]*/
    %declare INDENT DEDENT

    // A newline, its indentation, and any comment-only lines in between.
    // Swallowing comment lines here means a full-line comment inside a block
    // can't split the newline token and confuse the indenter.
    _NL: /(\r?\n[\t ]*(#[^\n]*)?)+/
"""


class ViperIndenter(Indenter):
    NL_type = "_NL"
    OPEN_PAREN_types = ["LPAR", "LSQB", "LBRACE"]
    CLOSE_PAREN_types = ["RPAR", "RSQB", "RBRACE"]
    INDENT_type = "INDENT"
    DEDENT_type = "DEDENT"
    tab_len = 8


class ViperParser:
    def __init__(self):
        self.parser = Lark(
            VIPER_GRAMMAR,
            parser="lalr",
            start="start",
            postlex=ViperIndenter(),
            lexer="contextual",
            propagate_positions=True,
        )

    def parse(self, source: str):
        if not source.endswith("\n"):
            source += "\n"
        return self.parser.parse(source)


parser = ViperParser()
