"""Execute transpiled Viper code."""
from .codegen import transpile
from .errors import ViperError, format_runtime_error


def _fresh_namespace() -> dict:
    return {"__name__": "__main__", "__builtins__": __builtins__}


def run_source(source: str, filename: str = "<viper>", namespace: dict | None = None) -> dict:
    """Transpile and execute Viper source. Returns the namespace it ran in.

    Raises ViperError (already formatted) on parse or runtime failure.
    """
    py_source, line_map = transpile(source, filename)
    ns = namespace if namespace is not None else _fresh_namespace()
    try:
        code = compile(py_source, filename, "exec")
        exec(code, ns)
    except ViperError:
        raise
    except SyntaxError as e:
        # A transpiler bug produced invalid Python; surface it honestly.
        raise ViperError(f"internal transpile error: {e}") from None
    except BaseException as e:
        raise ViperError(format_runtime_error(e, source, filename, line_map)) from None
    return ns


def run_repl_line(source: str, namespace: dict) -> None:
    """Run one REPL entry. A lone expression has its value printed."""
    stripped = source.strip()
    if not stripped:
        return

    py_source, line_map = transpile(source, "<repl>")
    py_source = py_source.rstrip("\n")

    # If the whole entry is a single expression, echo its repr like Python's REPL.
    is_expr = "\n" not in py_source
    if is_expr:
        try:
            compiled = compile(py_source, "<repl>", "eval")
        except SyntaxError:
            is_expr = False

    try:
        if is_expr:
            value = eval(compiled, namespace)
            if value is not None:
                print(repr(value))
        else:
            exec(compile(py_source, "<repl>", "exec"), namespace)
    except ViperError:
        raise
    except BaseException as e:
        raise ViperError(format_runtime_error(e, source, "<repl>", line_map)) from None
