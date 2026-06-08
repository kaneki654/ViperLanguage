from lark import Lark
from lark.indenter import Indenter

VIPER_GRAMMAR = r"""
    start: (_NL | stmt)*

    ?stmt: simple_stmt
         | compound_stmt

    simple_stmt: small_stmt _NL
    ?small_stmt: import_stmt
               | let_stmt
               | assign_stmt
               | return_stmt
               | break_stmt
               | continue_stmt
               | pass_stmt
               | expr_stmt

    ?compound_stmt: if_stmt
                  | while_stmt
                  | for_stmt
                  | match_stmt
                  | fn_def
                  | spawn_stmt

    import_stmt: "import" dotted_name ("," dotted_name)*        -> import_plain
               | "from" dotted_name "import" import_targets      -> import_from
    import_targets: "*"                                          -> import_star
                  | NAME ("," NAME)*
    dotted_name: NAME ("." NAME)*

    let_stmt: "let" NAME (":" type)? "=" expr
    assign_stmt: NAME "=" expr
    expr_stmt: expr
    return_stmt: "return" expr?
    break_stmt: "break"
    continue_stmt: "continue"
    pass_stmt: "pass"

    if_stmt: "if" expr ":" suite elif_clause* else_clause?
    elif_clause: "elif" expr ":" suite
    else_clause: "else" ":" suite
    while_stmt: "while" expr ":" suite
    for_stmt: "for" pattern "in" expr ":" suite
    match_stmt: "match" expr ":" _NL INDENT match_case+ DEDENT
    match_case: "case" pattern ("if" expr)? ":" suite
    fn_def: "fn" NAME "(" param_list? ")" ("->" type)? ":" suite
    spawn_stmt: "spawn" ":" suite

    param_list: param ("," param)* ("," "...")?
    param: NAME (":" type)? ("=" expr)?

    suite: simple_stmt | _NL INDENT stmt+ DEDENT

    ?expr: pipe_expr
    pipe_expr: ternary ("|>" ternary)*
    ?ternary: or_expr ("if" or_expr "else" or_expr)?    -> conditional
    ?or_expr: and_expr ("or" and_expr)*
    ?and_expr: not_expr ("and" not_expr)*
    ?not_expr: "not" not_expr                            -> logical_not
             | comparison
    ?comparison: arith (comp_op arith)*
    !comp_op: "<" | "<=" | ">" | ">=" | "==" | "!=" | "is" | "is" "not" | "in" | "not" "in"
    ?arith: term (add_op term)*
    !add_op: "+" | "-"
    ?term: factor (mul_op factor)*
    !mul_op: "*" | "/" | "//" | "%"
    ?factor: unary_op factor                             -> unary
           | power
    !unary_op: "+" | "-"
    ?power: postfix ("**" factor)?

    ?postfix: atom trailer*
    trailer: "(" arg_list? ")"                           -> call_trailer
           | "[" expr "]"                                -> index_trailer
           | "." NAME                                    -> attr_trailer

    ?atom: NUMBER                                        -> number
         | STRING                                        -> string
         | NAME                                          -> name
         | "True"                                        -> const_true
         | "False"                                       -> const_false
         | "None"                                        -> const_none
         | "fn" "(" param_list? ")" "->" expr            -> lambda_expr
         | "(" expr ")"                                  -> group
         | "[" list_items? "]"                           -> list_literal
         | "{" dict_items? "}"                           -> dict_literal

    list_items: expr ("," expr)* ","?
    dict_items: key_value ("," key_value)* ","?
    key_value: expr ":" expr
    arg_list: argument ("," argument)* ","?
    argument: NAME "=" expr                              -> kwarg
            | expr                                       -> posarg

    pattern: NAME                                        -> pat_capture
           | NUMBER                                      -> pat_number
           | STRING                                      -> pat_string
           | "_"                                         -> pat_wildcard
           | "(" pattern ")"                             -> pat_group
           | "[" (pattern ("," pattern)*)? "]"           -> pat_sequence

    type: NAME ("[" type ("," type)* "]")?

    %import common.CNAME -> NAME
    %import common.NUMBER
    %import common.WS_INLINE
    %import common.ESCAPED_STRING -> STRING
    %ignore WS_INLINE
    %declare INDENT DEDENT

    _NL: /(\r?\n[\t ]*)+/
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
