"""Programmatic Tool Calling (run_code) with a bounded async AST interpreter."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import math
import operator
import re
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, CancellationToken, ToolExecutionContext, ToolResult

MAX_PTC_AST_STEPS = 200_000
MAX_PTC_CALL_DEPTH = 32
MAX_PTC_PRINT_CHARS = 200_000
MAX_PTC_SLEEP_SECONDS = 5.0

BLOCKED_NESTED_PTC_TOOLS: frozenset[str] = frozenset(
    {
        "run_code",
        "ask_user_question",
        "ask_user_form",
        "enter_plan_mode",
        "exit_plan_mode",
        "brief",
    }
)


class RunCodeInput(BaseModel):
    """Input schema for executing a programmatic tool-calling script."""

    code: str = Field(
        ...,
        min_length=1,
        description=(
            "Restricted async Python script that orchestrates registered tools via "
            "`await tools.<tool_name>(**kwargs)` or `await call_tool(name, args_dict)` "
            "and `await gather(...)` / `await asyncio.gather(...)`. "
            "Use `print(...)`, `inspect(path_or_value, label=...)`, assign `result = ...`, "
            "or return from top-level / `main()`."
        ),
    )
    mode: str = Field(
        default="script",
        description="Execution mode: 'script' (stateless) or 'scoped_repl' (persists variables across calls for state_owner).",
    )
    state_owner: str | None = Field(
        default=None,
        description="Optional state owner key when mode='scoped_repl'. Defaults to session/cwd scope.",
    )
    reset_state: bool = Field(
        default=False,
        description="When True, clears any persisted scoped_repl state for state_owner before running.",
    )
    read_only_only: bool = Field(
        default=False,
        description="When True, restricts nested tool calls strictly to read-only tools.",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=180.0,
        description="Maximum wall-clock runtime in seconds for the entire script.",
    )
    max_tool_calls: int = Field(
        default=40,
        ge=1,
        le=100,
        description="Maximum number of nested tool invocations allowed in this run.",
    )
    max_concurrency: int = Field(
        default=6,
        ge=1,
        le=12,
        description="Maximum concurrent nested tool invocations via gather().",
    )


@dataclass(frozen=True)
class PtcToolOutput:
    """Result object returned to PTC scripts for each nested tool call."""

    tool_name: str
    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    structured_data: Any = None

    @property
    def data(self) -> Any:
        """Return structured output if available, or parsed JSON when valid, else raw text."""
        if self.structured_data is not None:
            return self.structured_data
        if isinstance(self.metadata, dict) and "structured_output" in self.metadata:
            return self.metadata["structured_output"]
        text = (self.output or "").strip()
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except Exception:
                pass
        return self.output

    def json(self) -> Any:
        """Parse ``output`` as JSON."""
        if self.structured_data is not None:
            return self.structured_data
        return json.loads(self.output)

    def lines(self) -> list[str]:
        """Return output split into non-empty stripped lines or raw lines."""
        return self.output.splitlines()

    def __str__(self) -> str:
        return self.output

    def __len__(self) -> int:
        val = self.data
        if isinstance(val, (dict, list, tuple, set, str)):
            return len(val)
        return len(self.output or "")

    def __getitem__(self, key: Any) -> Any:
        val = self.data
        if isinstance(val, (dict, list, tuple)) and not isinstance(key, slice):
            try:
                return val[key]
            except (KeyError, IndexError, TypeError):
                if isinstance(val, dict) and key == "output":
                    return self.output
                raise
        return (self.output or "")[key]

    def __contains__(self, item: Any) -> bool:
        val = self.data
        if isinstance(val, (dict, list, tuple, set)):
            return item in val
        return str(item) in (self.output or "")

    def __iter__(self):
        val = self.data
        if isinstance(val, (list, tuple, dict, set)):
            return iter(val)
        return iter(self.lines())

    def __bool__(self) -> bool:
        return not self.is_error and bool((self.output or "").strip() or self.structured_data is not None)


class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        super().__init__("return")
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class _Scope:
    def __init__(self, values: dict[str, Any] | None = None, parent: "_Scope | None" = None) -> None:
        self.values: dict[str, Any] = dict(values or {})
        self.parent = parent

    def get(self, name: str) -> Any:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.values:
                return scope.values[name]
            scope = scope.parent
        raise NameError(f"name '{name}' is not defined")

    def set(self, name: str, value: Any) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        if name in self.values:
            del self.values[name]
            return
        raise NameError(f"name '{name}' is not defined")


class _SafeModuleProxy:
    """Expose an explicit allowlist of safe read-only module attributes."""

    def __init__(self, name: str, attrs: dict[str, Any]) -> None:
        self._ptc_name = name
        self._ptc_attrs = attrs

    def get_attr(self, attr: str) -> Any:
        if attr in self._ptc_attrs:
            return self._ptc_attrs[attr]
        raise AttributeError(f"module '{self._ptc_name}' has no allowed attribute '{attr}'")

    def __repr__(self) -> str:
        return f"<safe module '{self._ptc_name}'>"


class _ToolsNamespace:
    """Dynamic `tools.<tool_name>(**kwargs)` proxy exposed inside PTC scripts."""

    def __init__(self, invoker: Callable[[str, dict[str, Any]], Awaitable[PtcToolOutput]]) -> None:
        self._invoker = invoker

    def call_method(self, tool_name: str) -> Callable[..., Coroutine[Any, Any, PtcToolOutput]]:
        if tool_name.startswith("_"):
            raise AttributeError(f"Access to private attribute '{tool_name}' is denied")

        async def _caller(*args: Any, **kwargs: Any) -> PtcToolOutput:
            if args:
                if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                    return await self._invoker(tool_name, dict(args[0]))
                raise TypeError(
                    f"tools.{tool_name}() accepts keyword arguments or a single dict argument"
                )
            return await self._invoker(tool_name, dict(kwargs))

        return _caller


_SAFE_TYPES_FOR_ISINSTANCE = (
    str,
    int,
    float,
    bool,
    list,
    dict,
    set,
    tuple,
    PtcToolOutput,
)

_SAFE_COLLECTION_METHODS: dict[type, frozenset[str]] = {
    str: frozenset(
        {
            "capitalize",
            "casefold",
            "count",
            "endswith",
            "find",
            "format",
            "isalnum",
            "isalpha",
            "isascii",
            "isdigit",
            "islower",
            "isnumeric",
            "isspace",
            "istitle",
            "isupper",
            "join",
            "ljust",
            "lower",
            "lstrip",
            "partition",
            "removeprefix",
            "removesuffix",
            "replace",
            "rfind",
            "rjust",
            "rpartition",
            "rsplit",
            "rstrip",
            "split",
            "splitlines",
            "startswith",
            "strip",
            "swapcase",
            "title",
            "upper",
            "zfill",
        }
    ),
    list: frozenset({"append", "clear", "copy", "count", "extend", "index", "insert", "pop", "remove", "reverse", "sort"}),
    dict: frozenset({"clear", "copy", "get", "items", "keys", "pop", "popitem", "setdefault", "update", "values"}),
    set: frozenset(
        {
            "add",
            "clear",
            "copy",
            "difference",
            "discard",
            "intersection",
            "isdisjoint",
            "issubset",
            "issuperset",
            "pop",
            "remove",
            "symmetric_difference",
            "union",
            "update",
        }
    ),
    tuple: frozenset({"count", "index"}),
}

_SAFE_REGEX_MATCH_ATTRS = frozenset({"group", "groups", "groupdict", "span", "start", "end"})
_SAFE_REGEX_PATTERN_ATTRS = frozenset({"search", "match", "fullmatch", "findall", "finditer", "sub", "split", "pattern"})
_SAFE_PTC_RESULT_ATTRS = frozenset({"tool_name", "output", "is_error", "metadata", "structured_data", "data", "json", "lines"})

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.BitAnd: operator.and_,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}

_ALLOWED_IMPORTS = frozenset({"json", "re", "math", "asyncio"})

_SCOPED_REPL_STATES: dict[str, dict[str, Any]] = {}


def reset_ptc_state(state_owner: str | None = None) -> None:
    """Reset persisted `scoped_repl` state for *state_owner* (or all owners if None)."""
    if state_owner is None:
        _SCOPED_REPL_STATES.clear()
    else:
        _SCOPED_REPL_STATES.pop(str(state_owner), None)


def generate_tool_sdk_stubs(registry: Any) -> str:
    """Generate concise typed Python stub signatures for registered tools usable in `run_code`."""
    if registry is None or not hasattr(registry, "list_tools"):
        return ""
    lines = ["# Available `tools.<name>(**kwargs)` SDK Signatures:"]
    for tool in registry.list_tools():
        if tool.name in BLOCKED_NESTED_PTC_TOOLS:
            continue
        schema = tool.to_api_schema().get("input_schema", {})
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", ())) if isinstance(schema, dict) else set()
        params: list[str] = []
        for pname, pspec in props.items():
            ptype = pspec.get("type", "Any") if isinstance(pspec, dict) else "Any"
            if pname in required:
                params.append(f"{pname}: {ptype}")
            else:
                params.append(f"{pname}: {ptype} = ...")
        out_schema = tool.output_schema() if hasattr(tool, "output_schema") else None
        ret_hint = "PtcToolOutput[Structured]" if out_schema else "PtcToolOutput"
        lines.append(f"async def tools.{tool.name}({', '.join(params)}) -> {ret_hint}: ...")
    return "\n".join(lines)


def _safe_builtins(
    *,
    tools_ns: _ToolsNamespace,
    call_tool_fn: Callable[[str, dict[str, Any] | None], Coroutine[Any, Any, PtcToolOutput]],
    gather_fn: Callable[..., Coroutine[Any, Any, list[Any]]],
    sleep_fn: Callable[[float], Coroutine[Any, Any, None]],
    print_buffer: list[str],
    print_size_state: list[int],
    inspect_fn: Callable[..., Any] | None = None,
    tools_help_fn: Callable[[], str] | None = None,
) -> dict[str, Any]:
    json_proxy = _SafeModuleProxy("json", {"loads": json.loads, "dumps": json.dumps})
    re_proxy = _SafeModuleProxy(
        "re",
        {
            "search": re.search,
            "match": re.match,
            "fullmatch": re.fullmatch,
            "findall": re.findall,
            "finditer": re.finditer,
            "sub": re.sub,
            "split": re.split,
            "compile": re.compile,
            "escape": re.escape,
            "IGNORECASE": re.IGNORECASE,
            "I": re.I,
            "MULTILINE": re.MULTILINE,
            "M": re.M,
            "DOTALL": re.DOTALL,
            "S": re.S,
        },
    )
    math_proxy = _SafeModuleProxy(
        "math",
        {
            "ceil": math.ceil,
            "floor": math.floor,
            "sqrt": math.sqrt,
            "fabs": math.fabs,
            "log": math.log,
            "log10": math.log10,
            "pow": math.pow,
            "pi": math.pi,
            "e": math.e,
            "inf": math.inf,
            "isnan": math.isnan,
            "isinf": math.isinf,
        },
    )
    asyncio_proxy = _SafeModuleProxy("asyncio", {"gather": gather_fn, "sleep": sleep_fn})

    def _safe_print(*args: Any, sep: str = " ", end: str = "\n") -> None:
        chunk = sep.join(str(arg) for arg in args) + end
        next_size = print_size_state[0] + len(chunk)
        if next_size > MAX_PTC_PRINT_CHARS:
            remaining = max(0, MAX_PTC_PRINT_CHARS - print_size_state[0])
            if remaining > 0:
                print_buffer.append(chunk[:remaining])
            print_size_state[0] = MAX_PTC_PRINT_CHARS
            raise RuntimeError(f"print output exceeded {MAX_PTC_PRINT_CHARS} chars")
        print_size_state[0] = next_size
        print_buffer.append(chunk)

    def _safe_isinstance(obj: Any, classinfo: Any) -> bool:
        if isinstance(classinfo, tuple):
            if any(item not in _SAFE_TYPES_FOR_ISINSTANCE for item in classinfo):
                raise PermissionError("isinstance() only permits safe built-in data types in run_code")
            return isinstance(obj, classinfo)
        if classinfo not in _SAFE_TYPES_FOR_ISINSTANCE:
            raise PermissionError("isinstance() only permits safe built-in data types in run_code")
        return isinstance(obj, classinfo)

    def _safe_sorted(iterable: Any, *, key: Callable[[Any], Any] | None = None, reverse: bool = False) -> list[Any]:
        return sorted(iterable, key=key, reverse=reverse)

    return {
        "tools": tools_ns,
        "call_tool": call_tool_fn,
        "gather": gather_fn,
        "asyncio": asyncio_proxy,
        "json": json_proxy,
        "re": re_proxy,
        "math": math_proxy,
        "print": _safe_print,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "sorted": _safe_sorted,
        "reversed": reversed,
        "min": min,
        "max": max,
        "sum": sum,
        "any": any,
        "all": all,
        "abs": abs,
        "round": round,
        "pow": pow,
        "divmod": divmod,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "isinstance": _safe_isinstance,
        "True": True,
        "False": False,
        "None": None,
        "Exception": Exception,
        "ValueError": ValueError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "TypeError": TypeError,
        "RuntimeError": RuntimeError,
        "PermissionError": PermissionError,
        "ZeroDivisionError": ZeroDivisionError,
        "PtcToolOutput": PtcToolOutput,
        "inspect": inspect_fn or (lambda x, label="": x),
        "tools_help": tools_help_fn or (lambda: ""),
    }


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Yield, ast.YieldFrom)):
            raise PermissionError(f"AST construct '{type(node).__name__}' is not permitted in run_code")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise PermissionError(f"Access to private/dunder attribute '{node.attr}' is denied")
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id != "_":
            raise PermissionError(f"Access to private/dunder identifier '{node.id}' is denied")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in _ALLOWED_IMPORTS:
                    raise PermissionError(
                        f"Import '{alias.name}' is not permitted in run_code (allowed: {sorted(_ALLOWED_IMPORTS)})"
                    )
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".", 1)[0]
            if node.level or mod not in _ALLOWED_IMPORTS:
                raise PermissionError(
                    f"Import from '{node.module}' is not permitted in run_code (allowed: {sorted(_ALLOWED_IMPORTS)})"
                )


class _SafeAsyncInterpreter:
    """Step-budgeted, cancellation-aware AST interpreter for PTC scripts."""

    def __init__(
        self,
        *,
        globals_dict: dict[str, Any],
        module_proxies: dict[str, _SafeModuleProxy],
        cancellation_token: CancellationToken | None = None,
        max_steps: int = MAX_PTC_AST_STEPS,
    ) -> None:
        self.root_scope = _Scope(globals_dict)
        self.module_proxies = module_proxies
        self.cancellation_token = cancellation_token
        self.max_steps = max_steps
        self.steps = 0
        self.call_depth = 0
        self.defined_functions: dict[str, Any] = {}

    def _tick(self) -> None:
        if self.cancellation_token is not None and self.cancellation_token.is_cancelled():
            reason = self.cancellation_token.reason or "cancelled"
            raise asyncio.CancelledError(reason)
        self.steps += 1
        if self.steps > self.max_steps:
            raise RuntimeError(f"Script exceeded step limit ({self.max_steps})")

    def _resolve_attr(self, obj: Any, attr: str) -> Any:
        if attr.startswith("_"):
            raise PermissionError(f"Access to private attribute '{attr}' is denied")
        if isinstance(obj, _SafeModuleProxy):
            return obj.get_attr(attr)
        if isinstance(obj, _ToolsNamespace):
            return obj.call_method(attr)
        if isinstance(obj, PtcToolOutput):
            if attr not in _SAFE_PTC_RESULT_ATTRS:
                raise AttributeError(f"PtcToolOutput has no allowed attribute '{attr}'")
            return getattr(obj, attr)
        if isinstance(obj, re.Match):
            if attr not in _SAFE_REGEX_MATCH_ATTRS:
                raise AttributeError(f"Match has no allowed attribute '{attr}'")
            return getattr(obj, attr)
        if isinstance(obj, re.Pattern):
            if attr not in _SAFE_REGEX_PATTERN_ATTRS:
                raise AttributeError(f"Pattern has no allowed attribute '{attr}'")
            return getattr(obj, attr)
        for cls, allowed in _SAFE_COLLECTION_METHODS.items():
            if isinstance(obj, cls):
                if attr not in allowed:
                    raise AttributeError(f"'{cls.__name__}' attribute '{attr}' is not allowed in run_code")
                return getattr(obj, attr)
        raise AttributeError(f"Attribute access '{attr}' on {type(obj).__name__} is not permitted in run_code")

    async def run(self, code: str) -> Any:
        tree = ast.parse(code, mode="exec")
        _validate_ast(tree)

        last_expr_value: Any = None
        try:
            for stmt in tree.body:
                if isinstance(stmt, ast.Expr):
                    val = await self._eval(stmt.value, self.root_scope)
                    if not (
                        isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Name)
                        and stmt.value.func.id == "print"
                    ):
                        last_expr_value = val
                else:
                    await self._exec_stmt(stmt, self.root_scope)
        except _ReturnSignal as ret:
            return ret.value

        if "result" in self.root_scope.values:
            return self.root_scope.values["result"]
        if last_expr_value is not None:
            return last_expr_value
        main_fn = self.defined_functions.get("main")
        if main_fn is not None and self.steps < self.max_steps:
            result = main_fn()
            if inspect.isawaitable(result):
                return await result
            return result
        return None

    async def _exec_block(self, stmts: list[ast.stmt], scope: _Scope) -> None:
        for stmt in stmts:
            await self._exec_stmt(stmt, scope)

    async def _exec_stmt(self, stmt: ast.stmt, scope: _Scope) -> None:
        self._tick()
        if isinstance(stmt, ast.Pass):
            return
        if isinstance(stmt, ast.Expr):
            await self._eval(stmt.value, scope)
            return
        if isinstance(stmt, ast.Assign):
            value = await self._eval(stmt.value, scope)
            for target in stmt.targets:
                await self._assign_target(target, value, scope)
            return
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None:
                value = await self._eval(stmt.value, scope)
                await self._assign_target(stmt.target, value, scope)
            return
        if isinstance(stmt, ast.AugAssign):
            current = await self._eval_target_value(stmt.target, scope)
            rhs = await self._eval(stmt.value, scope)
            updated = _BIN_OPS[type(stmt.op)](current, rhs)
            await self._assign_target(stmt.target, updated, scope)
            return
        if isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                await self._delete_target(target, scope)
            return
        if isinstance(stmt, ast.If):
            cond = await self._eval(stmt.test, scope)
            await self._exec_block(stmt.body if cond else stmt.orelse, scope)
            return
        if isinstance(stmt, ast.For):
            iterable = await self._eval(stmt.iter, scope)
            completed_normally = True
            for item in iterable:
                self._tick()
                await self._assign_target(stmt.target, item, scope)
                try:
                    await self._exec_block(stmt.body, scope)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    completed_normally = False
                    break
            if completed_normally and stmt.orelse:
                await self._exec_block(stmt.orelse, scope)
            return
        if isinstance(stmt, ast.AsyncFor):
            iterable = await self._eval(stmt.iter, scope)
            completed_normally = True
            async for item in iterable:
                self._tick()
                await self._assign_target(stmt.target, item, scope)
                try:
                    await self._exec_block(stmt.body, scope)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    completed_normally = False
                    break
            if completed_normally and stmt.orelse:
                await self._exec_block(stmt.orelse, scope)
            return
        if isinstance(stmt, ast.While):
            completed_normally = True
            while await self._eval(stmt.test, scope):
                self._tick()
                try:
                    await self._exec_block(stmt.body, scope)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    completed_normally = False
                    break
            if completed_normally and stmt.orelse:
                await self._exec_block(stmt.orelse, scope)
            return
        if isinstance(stmt, ast.Break):
            raise _BreakSignal()
        if isinstance(stmt, ast.Continue):
            raise _ContinueSignal()
        if isinstance(stmt, ast.Return):
            value = await self._eval(stmt.value, scope) if stmt.value is not None else None
            raise _ReturnSignal(value)
        if isinstance(stmt, ast.Raise):
            if stmt.exc is None:
                raise
            exc = await self._eval(stmt.exc, scope)
            raise exc
        if isinstance(stmt, ast.Assert):
            ok = await self._eval(stmt.test, scope)
            if not ok:
                msg = await self._eval(stmt.msg, scope) if stmt.msg is not None else "AssertionError"
                raise AssertionError(msg)
            return
        if isinstance(stmt, ast.Try):
            await self._exec_try(stmt, scope)
            return
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = await self._make_function(stmt, scope)
            scope.set(stmt.name, fn)
            if scope is self.root_scope:
                self.defined_functions[stmt.name] = fn
            return
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                root = alias.name.split(".", 1)[0]
                bind = alias.asname or root
                scope.set(bind, self.module_proxies[root])
            return
        if isinstance(stmt, ast.ImportFrom):
            mod = (stmt.module or "").split(".", 1)[0]
            proxy = self.module_proxies[mod]
            for alias in stmt.names:
                if alias.name == "*":
                    raise PermissionError("Wildcard imports are not supported in run_code")
                scope.set(alias.asname or alias.name, proxy.get_attr(alias.name))
            return
        raise PermissionError(f"Statement '{type(stmt).__name__}' is not supported in run_code")

    async def _exec_try(self, stmt: ast.Try, scope: _Scope) -> None:
        ran_except = False
        try:
            await self._exec_block(stmt.body, scope)
        except (_ReturnSignal, _BreakSignal, _ContinueSignal, asyncio.CancelledError):
            raise
        except Exception as exc:
            matched = False
            for handler in stmt.handlers:
                if handler.type is None:
                    matched = True
                else:
                    handler_type = await self._eval(handler.type, scope)
                    matched = isinstance(exc, handler_type)
                if matched:
                    ran_except = True
                    if handler.name:
                        scope.set(handler.name, exc)
                    await self._exec_block(handler.body, scope)
                    break
            if not matched:
                raise
        finally:
            if stmt.finalbody:
                await self._exec_block(stmt.finalbody, scope)
        if not ran_except and stmt.orelse:
            await self._exec_block(stmt.orelse, scope)

    async def _make_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, closure_scope: _Scope) -> Any:
        if node.decorator_list:
            raise PermissionError("Function decorators are not supported in run_code")
        is_async = isinstance(node, ast.AsyncFunctionDef)
        arg_spec = node.args
        defaults = [await self._eval(d, closure_scope) for d in arg_spec.defaults]
        kw_defaults = [
            (await self._eval(d, closure_scope) if d is not None else None)
            for d in arg_spec.kw_defaults
        ]

        async def _call_async(*args: Any, **kwargs: Any) -> Any:
            self.call_depth += 1
            if self.call_depth > MAX_PTC_CALL_DEPTH:
                self.call_depth -= 1
                raise RecursionError(f"Maximum function call depth ({MAX_PTC_CALL_DEPTH}) exceeded")
            try:
                fn_scope = _Scope(parent=closure_scope)
                _bind_call_args(arg_spec, defaults, kw_defaults, args, kwargs, fn_scope)
                try:
                    await self._exec_block(node.body, fn_scope)
                except _ReturnSignal as ret:
                    return ret.value
                return None
            finally:
                self.call_depth -= 1

        if is_async:
            return _call_async
        # Sync helper functions defined inside script become awaitable coroutines unless pure lambda.
        # Returning async wrapper handles nested awaits seamlessly; raise clear error if called without await?
        # Even better: store marker or make pure sync statements run when called via sync loop helper if no await exists!
        if _contains_await(node.body):
            return _call_async
        return _call_async

    async def _eval_target_value(self, target: ast.AST, scope: _Scope) -> Any:
        if isinstance(target, ast.Name):
            return scope.get(target.id)
        if isinstance(target, ast.Subscript):
            obj = await self._eval(target.value, scope)
            key = await self._eval_slice(target.slice, scope)
            return obj[key]
        raise PermissionError(f"Unsupported assignment target '{type(target).__name__}'")

    async def _assign_target(self, target: ast.AST, value: Any, scope: _Scope) -> None:
        if isinstance(target, ast.Name):
            if target.id != "_":
                scope.set(target.id, value)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            items = list(value)
            starred_idx = next((i for i, elt in enumerate(target.elts) if isinstance(elt, ast.Starred)), None)
            if starred_idx is None:
                if len(items) != len(target.elts):
                    raise ValueError(f"cannot unpack {len(items)} values into {len(target.elts)} targets")
                for elt, item in zip(target.elts, items):
                    await self._assign_target(elt, item, scope)
                return
            before = target.elts[:starred_idx]
            after = target.elts[starred_idx + 1 :]
            if len(items) < len(before) + len(after):
                raise ValueError("not enough values to unpack")
            for elt, item in zip(before, items[: len(before)]):
                await self._assign_target(elt, item, scope)
            mid_end = len(items) - len(after)
            star_node = target.elts[starred_idx]
            assert isinstance(star_node, ast.Starred)
            await self._assign_target(star_node.value, items[len(before) : mid_end], scope)
            for elt, item in zip(after, items[mid_end:]):
                await self._assign_target(elt, item, scope)
            return
        if isinstance(target, ast.Subscript):
            obj = await self._eval(target.value, scope)
            key = await self._eval_slice(target.slice, scope)
            obj[key] = value
            return
        raise PermissionError(f"Unsupported assignment target '{type(target).__name__}'")

    async def _delete_target(self, target: ast.AST, scope: _Scope) -> None:
        if isinstance(target, ast.Name):
            scope.delete(target.id)
            return
        if isinstance(target, ast.Subscript):
            obj = await self._eval(target.value, scope)
            key = await self._eval_slice(target.slice, scope)
            del obj[key]
            return
        raise PermissionError(f"Unsupported delete target '{type(target).__name__}'")

    async def _eval_slice(self, node: ast.AST, scope: _Scope) -> Any:
        if isinstance(node, ast.Slice):
            lower = await self._eval(node.lower, scope) if node.lower is not None else None
            upper = await self._eval(node.upper, scope) if node.upper is not None else None
            step = await self._eval(node.step, scope) if node.step is not None else None
            return slice(lower, upper, step)
        return await self._eval(node, scope)

    async def _eval(self, node: ast.AST, scope: _Scope) -> Any:
        self._tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return scope.get(node.id)
        if isinstance(node, ast.List):
            return await self._eval_sequence(node.elts, scope, list)
        if isinstance(node, ast.Tuple):
            return await self._eval_sequence(node.elts, scope, tuple)
        if isinstance(node, ast.Set):
            return await self._eval_sequence(node.elts, scope, set)
        if isinstance(node, ast.Dict):
            out: dict[Any, Any] = {}
            for key_node, val_node in zip(node.keys, node.values):
                if key_node is None:
                    mapping = await self._eval(val_node, scope)
                    out.update(mapping)
                else:
                    k = await self._eval(key_node, scope)
                    v = await self._eval(val_node, scope)
                    out[k] = v
            return out
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value_node in node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    parts.append(value_node.value)
                elif isinstance(value_node, ast.FormattedValue):
                    val = await self._eval(value_node.value, scope)
                    if value_node.conversion == 114:
                        val = repr(val)
                    elif value_node.conversion == 115:
                        val = str(val)
                    elif value_node.conversion == 97:
                        val = ascii(val)
                    spec = ""
                    if value_node.format_spec is not None:
                        spec = str(await self._eval(value_node.format_spec, scope))
                    parts.append(format(val, spec))
            return "".join(parts)
        if isinstance(node, ast.Subscript):
            obj = await self._eval(node.value, scope)
            key = await self._eval_slice(node.slice, scope)
            return obj[key]
        if isinstance(node, ast.Attribute):
            obj = await self._eval(node.value, scope)
            return self._resolve_attr(obj, node.attr)
        if isinstance(node, ast.BinOp):
            left = await self._eval(node.left, scope)
            right = await self._eval(node.right, scope)
            return _BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            operand = await self._eval(node.operand, scope)
            return _UNARY_OPS[type(node.op)](operand)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for val_node in node.values:
                    result = await self._eval(val_node, scope)
                    if not result:
                        return result
                return result
            result = False
            for val_node in node.values:
                result = await self._eval(val_node, scope)
                if result:
                    return result
            return result
        if isinstance(node, ast.Compare):
            left = await self._eval(node.left, scope)
            for op_node, comp_node in zip(node.ops, node.comparators):
                right = await self._eval(comp_node, scope)
                if not _compare_values(op_node, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            cond = await self._eval(node.test, scope)
            return await self._eval(node.body if cond else node.orelse, scope)
        if isinstance(node, ast.NamedExpr):
            val = await self._eval(node.value, scope)
            scope.set(node.target.id, val)
            return val
        if isinstance(node, ast.Lambda):
            defaults = [await self._eval(d, scope) for d in node.args.defaults]
            kw_defaults = [
                (await self._eval(d, scope) if d is not None else None)
                for d in node.args.kw_defaults
            ]
            # Use synchronous call only when lambda body needs no await
            if _contains_await(node.body):
                async def _async_lambda(*args: Any, **kwargs: Any) -> Any:
                    fn_scope = _Scope(parent=scope)
                    _bind_call_args(node.args, defaults, kw_defaults, args, kwargs, fn_scope)
                    return await self._eval(node.body, fn_scope)
                return _async_lambda
            # Evaluate small sync lambda via temporary sync runner only if safe:
            # Since sorted(..., key=lambda x: ...) expects sync return values, evaluate sync AST expressions!
            def _sync_lambda(*args: Any, **kwargs: Any) -> Any:
                fn_scope = _Scope(parent=scope)
                _bind_call_args(node.args, defaults, kw_defaults, args, kwargs, fn_scope)
                return self._eval_sync_expr(node.body, fn_scope)
            return _sync_lambda
        if isinstance(node, ast.ListComp):
            return await self._eval_comp(node.elt, node.generators, scope, list)
        if isinstance(node, ast.SetComp):
            return await self._eval_comp(node.elt, node.generators, scope, set)
        if isinstance(node, ast.DictComp):
            items: list[tuple[Any, Any]] = []
            async for comp_scope in self._iter_comprehensions(node.generators, scope):
                k = await self._eval(node.key, comp_scope)
                v = await self._eval(node.value, comp_scope)
                items.append((k, v))
            return dict(items)
        if isinstance(node, ast.GeneratorExp):
            return await self._eval_comp(node.elt, node.generators, scope, list)
        if isinstance(node, ast.Call):
            fn = await self._eval(node.func, scope)
            pos_args: list[Any] = []
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    pos_args.extend(await self._eval(arg.value, scope))
                else:
                    pos_args.append(await self._eval(arg, scope))
            kw_args: dict[str, Any] = {}
            for kw in node.keywords:
                if kw.arg is None:
                    kw_args.update(await self._eval(kw.value, scope))
                else:
                    kw_args[kw.arg] = await self._eval(kw.value, scope)
            return fn(*pos_args, **kw_args)
        if isinstance(node, ast.Await):
            val = await self._eval(node.value, scope)
            if inspect.isawaitable(val):
                return await val
            return val
        raise PermissionError(f"Expression '{type(node).__name__}' is not supported in run_code")

    def _eval_sync_expr(self, node: ast.AST, scope: _Scope) -> Any:
        """Evaluate pure synchronous AST expressions (used by sync `lambda` keys)."""
        self._tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return scope.get(node.id)
        if isinstance(node, ast.List):
            return [self._eval_sync_expr(elt, scope) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_sync_expr(elt, scope) for elt in node.elts)
        if isinstance(node, ast.Subscript):
            obj = self._eval_sync_expr(node.value, scope)
            if isinstance(node.slice, ast.Slice):
                lower = self._eval_sync_expr(node.slice.lower, scope) if node.slice.lower else None
                upper = self._eval_sync_expr(node.slice.upper, scope) if node.slice.upper else None
                step = self._eval_sync_expr(node.slice.step, scope) if node.slice.step else None
                return obj[slice(lower, upper, step)]
            return obj[self._eval_sync_expr(node.slice, scope)]
        if isinstance(node, ast.Attribute):
            return self._resolve_attr(self._eval_sync_expr(node.value, scope), node.attr)
        if isinstance(node, ast.BinOp):
            return _BIN_OPS[type(node.op)](
                self._eval_sync_expr(node.left, scope),
                self._eval_sync_expr(node.right, scope),
            )
        if isinstance(node, ast.UnaryOp):
            return _UNARY_OPS[type(node.op)](self._eval_sync_expr(node.operand, scope))
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                res: Any = True
                for item in node.values:
                    res = self._eval_sync_expr(item, scope)
                    if not res:
                        return res
                return res
            res = False
            for item in node.values:
                res = self._eval_sync_expr(item, scope)
                if res:
                    return res
            return res
        if isinstance(node, ast.Compare):
            left = self._eval_sync_expr(node.left, scope)
            for op_node, comp_node in zip(node.ops, node.comparators):
                right = self._eval_sync_expr(comp_node, scope)
                if not _compare_values(op_node, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self._eval_sync_expr(
                node.body if self._eval_sync_expr(node.test, scope) else node.orelse,
                scope,
            )
        if isinstance(node, ast.Call):
            fn = self._eval_sync_expr(node.func, scope)
            args = [self._eval_sync_expr(arg, scope) for arg in node.args if not isinstance(arg, ast.Starred)]
            kwargs = {kw.arg: self._eval_sync_expr(kw.value, scope) for kw in node.keywords if kw.arg}
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise RuntimeError("Synchronous lambda cannot call async functions; use async def instead")
            return result
        raise PermissionError(f"Unsupported expression in sync lambda: {type(node).__name__}")

    async def _eval_sequence(self, elts: list[ast.expr], scope: _Scope, factory: type) -> Any:
        out: list[Any] = []
        for elt in elts:
            if isinstance(elt, ast.Starred):
                out.extend(await self._eval(elt.value, scope))
            else:
                out.append(await self._eval(elt, scope))
        return factory(out)

    async def _iter_comprehensions(self, generators: list[ast.comprehension], scope: _Scope):
        if not generators:
            yield scope
            return
        gen = generators[0]
        iterable = await self._eval(gen.iter, scope)
        if gen.is_async:
            async for item in iterable:
                self._tick()
                next_scope = _Scope(parent=scope)
                await self._assign_target(gen.target, item, next_scope)
                ok = True
                for cond in gen.ifs:
                    if not await self._eval(cond, next_scope):
                        ok = False
                        break
                if ok:
                    async for sub_scope in self._iter_comprehensions(generators[1:], next_scope):
                        yield sub_scope
        else:
            for item in iterable:
                self._tick()
                next_scope = _Scope(parent=scope)
                await self._assign_target(gen.target, item, next_scope)
                ok = True
                for cond in gen.ifs:
                    if not await self._eval(cond, next_scope):
                        ok = False
                        break
                if ok:
                    async for sub_scope in self._iter_comprehensions(generators[1:], next_scope):
                        yield sub_scope

    async def _eval_comp(
        self,
        elt: ast.expr,
        generators: list[ast.comprehension],
        scope: _Scope,
        factory: type,
    ) -> Any:
        collected = []
        async for comp_scope in self._iter_comprehensions(generators, scope):
            collected.append(await self._eval(elt, comp_scope))
        return factory(collected)


def _contains_await(node: ast.AST | list[ast.stmt]) -> bool:
    nodes = node if isinstance(node, list) else [node]
    for root in nodes:
        for child in ast.walk(root):
            if isinstance(child, (ast.Await, ast.AsyncFor)):
                return True
    return False


def _compare_values(op_node: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op_node, ast.Eq):
        return left == right
    if isinstance(op_node, ast.NotEq):
        return left != right
    if isinstance(op_node, ast.Lt):
        return left < right
    if isinstance(op_node, ast.LtE):
        return left <= right
    if isinstance(op_node, ast.Gt):
        return left > right
    if isinstance(op_node, ast.GtE):
        return left >= right
    if isinstance(op_node, ast.Is):
        return left is right
    if isinstance(op_node, ast.IsNot):
        return left is not right
    if isinstance(op_node, ast.In):
        return left in right
    if isinstance(op_node, ast.NotIn):
        return left not in right
    raise PermissionError(f"Unsupported comparison operator: {type(op_node).__name__}")


def _bind_call_args(
    arg_spec: ast.arguments,
    defaults: list[Any],
    kw_defaults: list[Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    scope: _Scope,
) -> None:
    positional_params = list(arg_spec.posonlyargs) + list(arg_spec.args)
    remaining_kwargs = dict(kwargs)
    num_positional = len(positional_params)
    num_defaults = len(defaults)
    first_default_idx = num_positional - num_defaults

    for idx, param in enumerate(positional_params):
        if idx < len(args):
            if param.arg in remaining_kwargs and param not in arg_spec.posonlyargs:
                raise TypeError(f"got multiple values for argument '{param.arg}'")
            scope.set(param.arg, args[idx])
        elif param.arg in remaining_kwargs and idx >= len(arg_spec.posonlyargs):
            scope.set(param.arg, remaining_kwargs.pop(param.arg))
        elif idx >= first_default_idx:
            scope.set(param.arg, defaults[idx - first_default_idx])
        else:
            raise TypeError(f"missing required positional argument: '{param.arg}'")

    if len(args) > num_positional:
        if arg_spec.vararg is None:
            raise TypeError(f"expected at most {num_positional} positional arguments, got {len(args)}")
        scope.set(arg_spec.vararg.arg, tuple(args[num_positional:]))
    elif arg_spec.vararg is not None:
        scope.set(arg_spec.vararg.arg, ())

    for kw_param, kw_default in zip(arg_spec.kwonlyargs, kw_defaults):
        if kw_param.arg in remaining_kwargs:
            scope.set(kw_param.arg, remaining_kwargs.pop(kw_param.arg))
        elif kw_default is not None:
            scope.set(kw_param.arg, kw_default)
        else:
            raise TypeError(f"missing required keyword-only argument: '{kw_param.arg}'")

    if arg_spec.kwarg is not None:
        scope.set(arg_spec.kwarg.arg, remaining_kwargs)
    elif remaining_kwargs:
        unexpected = next(iter(remaining_kwargs))
        raise TypeError(f"got an unexpected keyword argument '{unexpected}'")


def _format_return_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, PtcToolOutput):
        return value.output
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


class RunCodeTool(BaseTool):
    """Execute a bounded Python script that programmatically batches tool calls."""

    name = "run_code"
    display_name = "Programmatic Tool Calling"
    default_start_message = "Running programmatic tool-calling script"
    description = (
        "Run a safe Python script that orchestrates multiple registered tool calls in one turn "
        "with loops, conditionals, `await gather(...)`, filtering, and aggregation, returning only "
        "the distilled result to your context window. "
        "Inside the script: use `await tools.<tool_name>(**kwargs)` or `await call_tool(name, args)` "
        "and `await gather(...)` / `json` / `re` / `math` / `print(...)`. "
        "Every nested tool call runs through normal OpenHarness validation, permissions, and workspace guards."
    )
    input_model = RunCodeInput
    parallel_safe = False
    execution_group = "ptc"

    def is_read_only(self, arguments: RunCodeInput) -> bool:
        # The AST interpreter itself is side-effect free; `parallel_safe = False`
        # prevents concurrent batch execution, and every nested tool invocation
        # is checked individually by `ptc_tool_runner` and `read_only_only`.
        del arguments
        return True

    async def execute(self, arguments: RunCodeInput, context: ToolExecutionContext) -> ToolResult:
        runner = context.metadata.get("ptc_tool_runner")
        if runner is None:
            return ToolResult(
                output="run_code is unavailable: nested tool runner is not configured in this context.",
                is_error=True,
            )

        tool_registry = context.metadata.get("tool_registry")
        started = time.monotonic()
        semaphore = asyncio.Semaphore(arguments.max_concurrency)
        call_lock = asyncio.Lock()
        subcalls: list[dict[str, Any]] = []
        inspected_images: list[Any] = []
        inspected_contexts: list[str] = []
        parent_tool_use_id = str(context.metadata.get("tool_use_id") or "ptc")

        async def _invoke_nested_tool(tool_name: str, tool_args: dict[str, Any] | None = None) -> PtcToolOutput:
            normalized = (tool_name or "").strip()
            if normalized in BLOCKED_NESTED_PTC_TOOLS:
                raise PermissionError(
                    f"Tool '{normalized}' cannot be called recursively or interactively from inside run_code."
                )
            if arguments.read_only_only and tool_registry is not None and hasattr(tool_registry, "get"):
                target_tool = tool_registry.get(normalized)
                if target_tool is not None:
                    try:
                        validated_args = target_tool.input_model.model_validate(dict(tool_args or {}))
                        is_ro = target_tool.is_read_only(validated_args)
                    except Exception:
                        is_ro = False
                    if not is_ro:
                        raise PermissionError(
                            f"Tool '{normalized}' is not read-only and is blocked because read_only_only=True."
                        )

            async with call_lock:
                if len(subcalls) >= arguments.max_tool_calls:
                    raise RuntimeError(
                        f"Exceeded max_tool_calls limit ({arguments.max_tool_calls}) inside run_code"
                    )
                call_index = len(subcalls) + 1
                nested_id = f"{parent_tool_use_id}_ptc_{call_index}_{uuid4().hex[:6]}"
                entry = {"index": call_index, "tool_name": normalized, "is_error": False}
                subcalls.append(entry)

            if context.progress_callback is not None:
                await context.progress_callback(
                    {
                        "phase": "ptc_subcall",
                        "status": "running",
                        "message": f"[run_code #{call_index}] Calling {normalized}",
                        "detail": normalized,
                    }
                )

            async with semaphore:
                result_block = await runner(normalized, nested_id, dict(tool_args or {}))

            entry["is_error"] = bool(result_block.is_error)
            meta = dict(result_block.result_metadata or {})
            if getattr(result_block, "images", None):
                inspected_images.extend(result_block.images)
            return PtcToolOutput(
                tool_name=normalized,
                output=result_block.content,
                is_error=bool(result_block.is_error),
                metadata=meta,
                structured_data=meta.get("structured_output"),
            )

        def _safe_inspect(target: Any, label: str = "") -> Any:
            tag = f" ({label})" if label else ""
            if isinstance(target, str):
                candidate = (context.cwd / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
                if candidate.is_file():
                    try:
                        from openharness.engine.messages import ImageBlock

                        img_block = ImageBlock.from_path(candidate)
                        inspected_images.append(img_block)
                        inspected_contexts.append(f"[PTC Inspect Image{tag}: {candidate}]")
                        return target
                    except Exception:
                        pass
            preview = _format_return_value(target)
            if len(preview) > 2000:
                preview = preview[:2000] + "... [truncated]"
            inspected_contexts.append(f"[PTC Inspect{tag}]\n{preview}")
            return target

        def _tools_help() -> str:
            return generate_tool_sdk_stubs(tool_registry)

        async def _safe_gather(*awaitables: Any, return_exceptions: bool = False) -> list[Any]:
            if not awaitables:
                return []
            if len(awaitables) == 1 and isinstance(awaitables[0], (list, tuple)) and not inspect.isawaitable(awaitables[0]):
                awaitables = tuple(awaitables[0])
            results = await asyncio.gather(*awaitables, return_exceptions=return_exceptions)
            return list(results)

        async def _safe_sleep(seconds: float) -> None:
            delay = max(0.0, min(MAX_PTC_SLEEP_SECONDS, float(seconds)))
            await asyncio.sleep(delay)

        print_buffer: list[str] = []
        print_size_state = [0]
        tools_ns = _ToolsNamespace(_invoke_nested_tool)
        builtins_ns = _safe_builtins(
            tools_ns=tools_ns,
            call_tool_fn=_invoke_nested_tool,
            gather_fn=_safe_gather,
            sleep_fn=_safe_sleep,
            print_buffer=print_buffer,
            print_size_state=print_size_state,
            inspect_fn=_safe_inspect,
            tools_help_fn=_tools_help,
        )
        builtin_keys = frozenset(builtins_ns.keys())
        owner_key = str(arguments.state_owner or context.metadata.get("session_id") or context.cwd)
        if arguments.reset_state:
            reset_ptc_state(owner_key)
        if arguments.mode == "scoped_repl" and owner_key in _SCOPED_REPL_STATES:
            for k, v in _SCOPED_REPL_STATES[owner_key].items():
                if k not in builtin_keys:
                    builtins_ns[k] = v

        module_proxies = {
            name: builtins_ns[name]
            for name in ("json", "re", "math", "asyncio")
        }
        interpreter = _SafeAsyncInterpreter(
            globals_dict=builtins_ns,
            module_proxies=module_proxies,
            cancellation_token=context.cancellation_token,
        )

        try:
            return_value = await asyncio.wait_for(
                interpreter.run(arguments.code),
                timeout=arguments.timeout_seconds,
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            stdout_text = "".join(print_buffer).strip()
            parts = [f"run_code timed out after {arguments.timeout_seconds:.1f}s."]
            if stdout_text:
                parts.append(f"Partial stdout:\n{stdout_text}")
            return ToolResult(
                output="\n\n".join(parts),
                is_error=True,
                metadata={
                    "tool_calls_count": len(subcalls),
                    "tool_names_used": sorted({item["tool_name"] for item in subcalls}),
                    "error_count": sum(1 for item in subcalls if item["is_error"]),
                    "duration_ms": elapsed_ms,
                },
            )
        except asyncio.CancelledError:
            raise
        except SyntaxError as exc:
            return ToolResult(
                output=f"SyntaxError in run_code script (line {exc.lineno}): {exc.msg}",
                is_error=True,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            stdout_text = "".join(print_buffer).strip()
            parts = [f"{type(exc).__name__}: {exc}"]
            if stdout_text:
                parts.append(f"Stdout before error:\n{stdout_text}")
            return ToolResult(
                output="\n\n".join(parts),
                is_error=True,
                metadata={
                    "tool_calls_count": len(subcalls),
                    "tool_names_used": sorted({item["tool_name"] for item in subcalls}),
                    "error_count": sum(1 for item in subcalls if item["is_error"]),
                    "duration_ms": elapsed_ms,
                },
            )

        if arguments.mode == "scoped_repl":
            persisted = {
                k: v
                for k, v in interpreter.root_scope.values.items()
                if k not in builtin_keys and not k.startswith("_") and not callable(v)
            }
            _SCOPED_REPL_STATES[owner_key] = persisted

        elapsed_ms = int((time.monotonic() - started) * 1000)
        stdout_text = "".join(print_buffer).strip()
        formatted_return = _format_return_value(return_value).strip()
        sections: list[str] = []
        if stdout_text:
            sections.append(stdout_text)
        if formatted_return and formatted_return != stdout_text:
            sections.append(formatted_return)
        if not sections:
            sections.append("(run_code completed with no output)")

        tool_names_used = sorted({item["tool_name"] for item in subcalls})
        error_count = sum(1 for item in subcalls if item["is_error"])
        summary_line = (
            f"[run_code completed in {elapsed_ms}ms | nested_calls={len(subcalls)}"
            + (f" | tools={', '.join(tool_names_used)}" if tool_names_used else "")
            + (f" | nested_errors={error_count}" if error_count else "")
            + "]"
        )
        sections.append(summary_line)

        return ToolResult(
            output="\n\n".join(sections),
            is_error=False,
            images=inspected_images,
            additional_contexts=inspected_contexts,
            metadata={
                "tool_calls_count": len(subcalls),
                "tool_names_used": tool_names_used,
                "error_count": error_count,
                "duration_ms": elapsed_ms,
                "ast_steps": interpreter.steps,
                "mode": arguments.mode,
                "inspected_count": len(inspected_contexts) + len(inspected_images),
            },
        )
